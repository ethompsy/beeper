import { useEffect, useRef, useState } from 'react'

/**
 * useInvestigationEvents — live SSE consume for the investigation detail
 * timeline (Task 2.6a, FR24/FR27, NFR21).
 *
 * Consumes the Task 1.6 JSON event stream
 * (`GET /api/v1/investigations/{id}/events`, `text/event-stream`) via the
 * browser's native `EventSource`. Two JSON event types arrive:
 *   - `event: step`     `{ order, key, label, state, type }` — one per
 *                        changed step; applied incrementally by `order`.
 *   - `event: complete` `{ status: "done" | "not_found" }` — terminal;
 *                        the server closes the stream after sending it.
 *
 * ── The 4-state lifecycle (FR27, spec "SSE Lifecycle State Pattern") ──
 *
 * `EventSource` itself only exposes `open`/`error`/`message` — it does not
 * distinguish "still trying the first connection" from "recovered after a
 * drop" from "gave up." This hook builds the spec's explicit 4-state model
 * on top of those primitives:
 *
 *   - **connected**    — default; `onopen` fired and no error since.
 *   - **disconnected**  — `onerror` fired (native `EventSource` already
 *                        auto-retries with its own backoff under the hood;
 *                        this state just reflects "a drop happened, still
 *                        retrying"). Renders the "Reconnecting…" indicator.
 *   - **reconnected**   — `onopen` fires again after a `disconnected`
 *                        state — i.e. the retry succeeded. This is a
 *                        transient signal for the caller (2.6b hangs its
 *                        REST backfill diff off this transition); the hook
 *                        itself settles back to `connected` on the very
 *                        next tick so the indicator doesn't linger.
 *   - **failed**        — after `MAX_CONSECUTIVE_ERRORS` (5, per spec)
 *                        error events with no intervening successful
 *                        `open`, the stream is treated as unrecoverable:
 *                        the `EventSource` is closed (stop the browser's
 *                        own infinite retry) and the state locks at
 *                        `failed`. Rendering the "Live updates unavailable"
 *                        fallback copy is Task 2.6b's concern — this hook
 *                        only exposes the state so 2.6b (and this task's
 *                        indicator) can react to it.
 *
 * ── The clean seam for Task 2.6b (reconnect backfill) ──
 *
 * This hook deliberately does NOT call `fetchInvestigationDetail` itself.
 * `onReconnect` fires exactly once per `disconnected` → `open` transition —
 * 2.6b's backfill (ordered/idempotent re-fetch via
 * `src/api/investigation-detail.ts`, diffed against the steps already
 * merged here) hangs entirely off that callback without this hook needing
 * to know anything about the REST client. Similarly `onFailed` fires once
 * on entering the `failed` state, for 2.6b's "Live updates unavailable"
 * fallback UI to hook into.
 *
 * ── Step merge ──
 *
 * Incoming `step` events are merged into an ordered array keyed by
 * `order`: an existing entry at that order is replaced in place (state
 * transition, e.g. active → completed); a new order is inserted at the
 * correct sorted position (guards against any out-of-order arrival, though
 * today's poll loop emits in order) rather than blindly appended — matching
 * the spec's step-timeline ordering guarantee.
 */

export type InvestigationEventsConnectionState =
  | 'connected'
  | 'disconnected'
  | 'reconnected'
  | 'failed'

export interface InvestigationStepEventPayload {
  order: number
  key: string | null
  label: string | null
  state: string
  type: string
}

interface CompleteEventPayload {
  status: 'done' | 'not_found' | string
}

export interface UseInvestigationEventsOptions {
  /** Called once per `disconnected` → reconnect-succeeded transition. Task 2.6b's backfill seam. */
  onReconnect?: () => void
  /** Called once on entering the terminal `failed` state. Task 2.6b's fallback-UI seam. */
  onFailed?: () => void
}

export interface UseInvestigationEventsResult {
  /** The 4-state connection lifecycle (FR27). */
  connectionState: InvestigationEventsConnectionState
  /** Step events received so far, merged and sorted by `order`. */
  steps: InvestigationStepEventPayload[]
  /** True once the `complete` event has been received (or the id doesn't exist). */
  isComplete: boolean
}

/** Spec: "After 5 consecutive retry failures (EventSource gives up)..." */
const MAX_CONSECUTIVE_ERRORS = 5

/** Injectable so tests can substitute a mock EventSource without touching jsdom globals. */
export type EventSourceFactory = (url: string) => EventSource

function defaultEventSourceFactory(url: string): EventSource {
  return new EventSource(url)
}

function mergeStep(
  steps: InvestigationStepEventPayload[],
  incoming: InvestigationStepEventPayload,
): InvestigationStepEventPayload[] {
  const existingIndex = steps.findIndex((step) => step.order === incoming.order)
  if (existingIndex !== -1) {
    const next = steps.slice()
    next[existingIndex] = incoming
    return next
  }

  // Insert at the sorted position rather than appending, so an
  // out-of-order arrival never breaks the timeline's narrative order.
  const insertAt = steps.findIndex((step) => step.order > incoming.order)
  const next = steps.slice()
  if (insertAt === -1) {
    next.push(incoming)
  } else {
    next.splice(insertAt, 0, incoming)
  }
  return next
}

/**
 * @param investigationId The investigation to stream. `undefined`/`null`
 *   disables streaming entirely (e.g. not-found route state).
 * @param eventSourceFactory Test seam — defaults to the real `EventSource`.
 */
export function useInvestigationEvents(
  investigationId: string | undefined,
  options: UseInvestigationEventsOptions = {},
  eventSourceFactory: EventSourceFactory = defaultEventSourceFactory,
): UseInvestigationEventsResult {
  const [connectionState, setConnectionState] =
    useState<InvestigationEventsConnectionState>('connected')
  const [steps, setSteps] = useState<InvestigationStepEventPayload[]>([])
  const [isComplete, setIsComplete] = useState(false)

  // Latest callbacks in a ref so the connection effect below doesn't need
  // to re-run (and doesn't tear down/reopen the stream) just because the
  // caller passed a new inline function identity on re-render.
  const onReconnectRef = useRef(options.onReconnect)
  onReconnectRef.current = options.onReconnect
  const onFailedRef = useRef(options.onFailed)
  onFailedRef.current = options.onFailed

  useEffect(() => {
    if (investigationId == null) return

    setConnectionState('connected')
    setSteps([])
    setIsComplete(false)

    const source = eventSourceFactory(
      `/api/v1/investigations/${encodeURIComponent(investigationId)}/events`,
    )

    let consecutiveErrors = 0
    let wasDisconnected = false
    let closed = false

    source.onopen = () => {
      consecutiveErrors = 0
      if (wasDisconnected) {
        wasDisconnected = false
        setConnectionState('reconnected')
        onReconnectRef.current?.()
        // Settle back to `connected` right after signaling the transient
        // `reconnected` state, so the indicator doesn't linger once the
        // caller (and 2.6b's backfill) has had a chance to react to it.
        setConnectionState('connected')
      } else {
        setConnectionState('connected')
      }
    }

    source.onerror = () => {
      if (closed) return
      consecutiveErrors += 1

      if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
        closed = true
        setConnectionState('failed')
        onFailedRef.current?.()
        source.close()
        return
      }

      wasDisconnected = true
      setConnectionState('disconnected')
    }

    source.addEventListener('step', (event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data) as InvestigationStepEventPayload
        setSteps((prev) => mergeStep(prev, payload))
      } catch {
        // Malformed payload — ignore this event rather than crash the stream.
      }
    })

    source.addEventListener('complete', (event: MessageEvent<string>) => {
      try {
        JSON.parse(event.data) as CompleteEventPayload
      } catch {
        // Even if the payload doesn't parse, `complete` still means "stop".
      }
      setIsComplete(true)
      closed = true
      source.close()
    })

    return () => {
      closed = true
      source.close()
    }
  }, [investigationId, eventSourceFactory])

  return { connectionState, steps, isComplete }
}
