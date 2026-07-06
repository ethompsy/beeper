import { useCallback, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  SummaryHeader,
  InvestigationStep,
  RelatedKbPanel,
  StepEvidence,
  FailureNotice,
  NotFoundMessage,
  DetailSkeleton,
  SseConnectionIndicator,
  useIsNarrowViewport,
  useInvestigationEvents,
  useAutoScrollOnAppend,
  type RelatedKbPanelState,
} from '../lib'
import { useInvestigationDetail } from './useInvestigationDetail'
import {
  apiStepTypeToStepType,
  findFirstEvidenceStepOrder,
  mergeBackfilledSteps,
  mergeLiveStepEvents,
  statusToBadgeVariant,
} from './investigation-detail-mappers'
import { fetchInvestigationDetail } from '../api/investigation-detail'
import { deriveProblemState } from '../lib/investigations/problem-state'
import type { InvestigationDetailMetadata, InvestigationStepDto } from '../api/investigation-detail'

/** Stable empty-array reference so `useMemo`'s dep doesn't change identity every render while loading/erroring. */
const EMPTY_STEPS: InvestigationStepDto[] = []

/**
 * InvestigationDetailPage — the investigation-detail "incident hero" (Task 2.5,
 * live-streaming layered on top by Task 2.6a).
 *
 * Renders the INITIAL state from the Task 1.6 one-shot detail fetch
 * (`GET /api/v1/investigations/{id}`, via `useInvestigationDetail` /
 * `src/api/investigation-detail.ts`, which Task 2.5 owns), then layers LIVE
 * updates on top via `useInvestigationEvents` (Task 2.6a), which opens
 * `GET /api/v1/investigations/{id}/events` (Task 1.6 JSON SSE) and streams
 * `{order, key, label, state, type}` step updates. Incoming events are
 * merged into the initial step list by `order` (`mergeLiveStepEvents`,
 * `investigation-detail-mappers.ts`) — a live update never drops the
 * `evidence`/`kbEntries` fields the initial fetch may have populated, since
 * the stream payload doesn't carry those (Q8).
 *
 * The `SummaryHeader`'s `<h1>` carries `headingId="detail-summary-heading"`
 * — the contract `useRouteFocusManagement` (Task 2.1) targets on every
 * detail-route mount, including a cold permalink load. The header renders
 * unconditionally on every render path below (loading/ok/error — everything
 * except the distinct not-found state) using whatever is known
 * synchronously (the `investigationId` URL param as a service-name
 * fallback) merged with fetched metadata once it resolves, so the heading
 * never waits on the network request to paint (NFR19: first-seconds facts
 * visible without interaction; also required so focus management doesn't
 * race the fetch on a cold load).
 *
 * ── Reconnect backfill (Task 2.6b, FR27/NFR9) ──
 *
 * `useInvestigationEvents` fires `onReconnect` exactly once per `disconnected`
 * → reconnect-succeeded transition. This page hangs its backfill off that
 * callback: re-fetch `GET /api/v1/investigations/{id}` (reusing the Task 2.5
 * `fetchInvestigationDetail` client — no new endpoint/client needed) and
 * store the result's `steps` as the new backfill baseline. `mergeBackfilledSteps`
 * (`investigation-detail-mappers.ts`) folds that baseline together with the
 * original one-shot fetch's steps, keyed by `order` via a `Map` — so it is
 * naturally idempotent (re-running with the same snapshot is a no-op) and
 * deduped (one entry per `order`, never a duplicate step). The backfill
 * baseline then flows through the SAME `mergeLiveStepEvents` merge already
 * used for live SSE steps, so a step the backfill returns can never regress
 * one already showing more progress from a live event received in the
 * interim (that function already merges by `order` without dropping fields).
 *
 * The `failed` terminal state (after `MAX_CONSECUTIVE_ERRORS`) needs no page
 * state at all — `SseConnectionIndicator` already renders the "Live updates
 * unavailable — refresh to sync" fallback purely from `connectionState`, and
 * every other block on this page renders unconditionally regardless of
 * `connectionState`, so the header/steps/KB panel stay fully viewable.
 */
export function InvestigationDetailPage() {
  const { investigationId } = useParams<{ investigationId: string }>()
  const query = useInvestigationDetail(investigationId)
  const isNarrowViewport = useIsNarrowViewport()
  const [kbExpanded, setKbExpanded] = useState(false)
  const timelineEndRef = useRef<HTMLLIElement | null>(null)

  // Task 2.6b: the most recent ordered step list re-fetched on reconnect.
  // `null` until the first successful reconnect backfill; once set, it
  // supersedes the original one-shot fetch's steps as the merge baseline
  // (see `mergeBackfilledSteps` below).
  const [backfilledSteps, setBackfilledSteps] = useState<InvestigationStepDto[] | null>(null)

  // `undefined` while not-found/no id — disables the stream entirely rather
  // than opening an EventSource against a route that will never emit steps.
  const streamId = query.status === 'not-found' ? undefined : investigationId

  const handleReconnect = useCallback(() => {
    if (investigationId == null) return
    // Fire-and-forget: a failed backfill fetch simply leaves the previous
    // baseline in place (steps already rendered are never blanked) — the
    // live stream that just reconnected will keep filling in from here
    // regardless, and the next reconnect gets another chance to backfill.
    void fetchInvestigationDetail(investigationId).then((result) => {
      if (result.kind === 'ok') {
        setBackfilledSteps(result.data.steps)
      }
    })
  }, [investigationId])

  const { connectionState, steps: liveStepEvents } = useInvestigationEvents(streamId, {
    onReconnect: handleReconnect,
  })

  const fetchedSteps: InvestigationStepDto[] = query.status === 'ok' ? query.data.steps : EMPTY_STEPS
  // The backfill baseline (once present) supersedes the original fetch's
  // steps, deduped/merged by `order` — never a blind replace, so a step the
  // original fetch already rendered with richer data (e.g. evidence) is
  // preserved if the backfill snapshot happens to omit it.
  const initialSteps = useMemo(
    () => mergeBackfilledSteps(fetchedSteps, backfilledSteps),
    [fetchedSteps, backfilledSteps],
  )
  const steps = useMemo(
    () => mergeLiveStepEvents(initialSteps, liveStepEvents),
    [initialSteps, liveStepEvents],
  )
  const firstEvidenceOrder = useMemo(() => findFirstEvidenceStepOrder(steps), [steps])

  // Auto-scroll rule (UX spec "Real-Time Feedback Patterns"): only scroll to
  // a newly-appended step when the user was already within 100px of the
  // timeline bottom; if they've scrolled up to read earlier evidence, new
  // steps append silently without stealing their scroll position.
  useAutoScrollOnAppend(timelineEndRef, steps.length)

  if (query.status === 'not-found') {
    return <NotFoundMessage investigationId={investigationId ?? ''} />
  }

  const metadata: InvestigationDetailMetadata | null = query.status === 'ok' ? query.data.metadata : null
  const serviceName = metadata?.service ?? investigationId ?? ''
  const severity = metadata?.severity ?? '—'
  const signalCount = metadata?.signal_count ?? 0
  const statusVariant = metadata != null ? statusToBadgeVariant(metadata.status) : 'pending'
  // Task 2.4 (FR47): standardized plain-language problem-state, derived from
  // the raw `condition` field via `deriveProblemState` — falls back to the
  // raw condition text verbatim when no heuristic pattern matches, and to
  // `undefined` only when there is no metadata at all yet (so the header
  // doesn't render a premature "No problem state available" placeholder
  // before the fetch resolves).
  const problemState = metadata?.condition != null ? deriveProblemState(metadata.condition) : undefined
  const timestamp = formatTimestamp(metadata)

  const kbStep = steps.find((step) => step.type === 'kb')
  const kbPanelState: RelatedKbPanelState =
    kbStep != null && kbStep.state !== 'completed' && kbStep.state !== 'error' ? 'loading' : 'populated'
  // "Populated" here still covers the zero-entries case — RelatedKbPanel
  // itself renders "0 Related KB Entries" (not an error) whenever
  // entryCount is 0, exactly matching FR26's "absent/unparseable KB"
  // requirement. `kbEntries` is a forward-compatible field (see
  // src/api/investigation-detail.ts doc) — absent from the Task 1.6
  // payload today, so entryCount is 0 until the backend adds it.
  const kbEntries = kbStep?.kbEntries ?? []

  const isFailed = metadata?.status === 'failed'
  const isPending = metadata?.status === 'pending'

  return (
    <div data-testid="investigation-detail-page" className="flex flex-col gap-6 pb-16">
      <SummaryHeader
        headingId="detail-summary-heading"
        serviceName={serviceName}
        severity={severity}
        signalCount={signalCount}
        statusVariant={statusVariant}
        timestamp={timestamp}
        problemState={problemState}
      />

      {query.status === 'loading' ? (
        <DetailSkeleton />
      ) : query.status === 'error' ? (
        <p role="alert" className="text-base text-status-critical">
          Unable to load this investigation right now.
        </p>
      ) : isPending ? (
        <p data-testid="pending-placeholder" className="text-base text-text-secondary">
          Investigation is waiting to start.
        </p>
      ) : (
        <ol data-slot="investigation-steps" className="flex flex-col gap-2">
          {steps.map((step) => (
            <InvestigationStep
              key={step.order}
              type={apiStepTypeToStepType(step.type)}
              order={step.order}
              description={step.label ?? ''}
              isFirstEvidence={firstEvidenceOrder === step.order}
              evidence={
                step.evidence != null && step.evidence.length > 0 ? (
                  <StepEvidence evidence={step.evidence} />
                ) : undefined
              }
            />
          ))}
          {/*
            Zero-height sentinel — the auto-scroll target (`useAutoScrollOnAppend`,
            Task 2.6a). `InvestigationStep` (Task 1.4 primitive) doesn't forward a
            `ref`, so rather than change that shared library component just for
            this, the timeline carries its own dedicated scroll anchor as the
            list's last child (still valid inside <ol> — a plain <li>).
          */}
          <li ref={timelineEndRef} aria-hidden="true" className="h-0 list-none" />
        </ol>
      )}

      {query.status === 'ok' ? (
        <SseConnectionIndicator connectionState={connectionState} />
      ) : null}

      {query.status === 'ok' && isFailed ? <FailureNotice message={metadata?.message} /> : null}

      {query.status === 'ok' ? (
        <p data-field="correlation-placeholder" className="text-sm text-text-secondary">
          {metadata?.correlated_services != null && metadata.correlated_services.length > 0
            ? `Impact: ${metadata.correlated_services.join(', ')}`
            : 'Impact: not yet correlated'}
        </p>
      ) : null}

      {query.status === 'ok' ? (
        <RelatedKbPanel
          state={kbPanelState}
          entryCount={kbEntries.length}
          expanded={kbExpanded}
          onExpandedChange={setKbExpanded}
          className={
            isNarrowViewport
              ? undefined // Inline, normal document flow (<1200px) — spec's "stacks below investigation content"
              : 'fixed inset-x-0 bottom-0 z-10' // Anchored bottom bar, expands upward (>=1200px)
          }
        >
          {kbEntries.length > 0 ? (
            <ul className="flex flex-col gap-2 text-sm text-text-primary">
              {kbEntries.map((entry) => (
                <li key={entry.id}>{entry.title}</li>
              ))}
            </ul>
          ) : null}
        </RelatedKbPanel>
      ) : null}
    </div>
  )
}

function formatTimestamp(metadata: InvestigationDetailMetadata | null): string | undefined {
  if (metadata == null) return undefined
  if (metadata.status === 'completed' && metadata.completed_at != null) {
    return `Completed ${metadata.completed_at}`
  }
  if (metadata.started_at != null) {
    return `Started ${metadata.started_at}`
  }
  return undefined
}
