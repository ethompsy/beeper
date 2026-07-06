import type { StatusBadgeVariant, InvestigationStepEventPayload } from '../lib'
import type {
  InvestigationDetailStatus,
  InvestigationStepApiType,
  InvestigationStepDto,
  InvestigationStepState,
} from '../api/investigation-detail'
import type { InvestigationStepType } from '../lib'

/**
 * investigation-detail-mappers.ts — view-layer mapping from the Task 1.6 API
 * shape to the Task 1.4 library primitives' prop types.
 *
 * Keeping this mapping separate from `InvestigationDetailPage.tsx` makes the
 * glossary-driven business rules (job-phase → `StatusBadgeVariant`) unit
 * testable without rendering the page, and keeps `StatusBadge`/
 * `InvestigationStep` (Task 1.4 primitives) free of any CRD-shape knowledge
 * per their own "no business logic" doc comments.
 */

/**
 * Job-phase status (`metadata.status`) → `StatusBadgeVariant`.
 *
 * Glossary OD-1: job-phase "Failed" renders as **"Analysis Failed"**
 * (variant `analysis-failed`) — distinct from workflow-state "Failed".
 * Glossary OD-5: the "Investigating" badge must come from the
 * workflow/pipeline state, not from `phase === 'investigating'` alone,
 * because the underlying Kubernetes Job phase is literally `Running` while
 * the pod is still spinning up (see backend's `InvestigationPhase`) — but
 * the JSON API's `status` field is already the normalized phase string used
 * throughout the codebase (`investigating`, not the raw k8s `Running`), so
 * mapping `status` directly is correct here; this function does not read
 * `workflow_state` for the *job-phase* badge (that would be the separate
 * workflow-state axis, not used on the summary header per the spec).
 */
export function statusToBadgeVariant(status: InvestigationDetailStatus): StatusBadgeVariant {
  switch (status) {
    case 'pending':
      return 'pending'
    case 'investigating':
      return 'investigating'
    case 'awaiting_confirmation':
      return 'awaiting-confirmation'
    case 'completed':
      return 'completed'
    case 'failed':
      return 'analysis-failed'
    default:
      return 'pending'
  }
}

/** API step-type string → `InvestigationStepType` (identity for known values, `summary` fallback for unknown). */
export function apiStepTypeToStepType(type: InvestigationStepApiType): InvestigationStepType {
  switch (type) {
    case 'metric':
    case 'log':
    case 'deploy':
    case 'kb':
    case 'correlation':
    case 'summary':
      return type
    default:
      return 'summary'
  }
}

/**
 * The first step that carries real evidence gets the "trust-ignition"
 * emphasis treatment (spec §Investigation Step, `is_first_evidence`).
 * "Real evidence" here means a completed metric/log/deploy/correlation step
 * — `kb` and `summary` steps are informational/narrative rather than raw
 * evidence, and a `pending`/`active`/`error` step hasn't produced evidence
 * yet, so neither qualifies as the emphasis target.
 */
const EVIDENCE_STEP_TYPES = new Set<InvestigationStepApiType>([
  'metric',
  'log',
  'deploy',
  'correlation',
])

export function findFirstEvidenceStepOrder(steps: InvestigationStepDto[]): number | null {
  const firstEvidence = steps.find(
    (step) => EVIDENCE_STEP_TYPES.has(step.type) && step.state === 'completed',
  )
  return firstEvidence?.order ?? null
}

/**
 * Merge live SSE `step` events (Task 2.6a, `useInvestigationEvents`) into the
 * initial one-shot fetch's ordered step list (Task 2.5, `InvestigationStepDto[]`).
 *
 * Both sides are keyed by `order`, but their shapes differ slightly: the
 * REST DTO carries the forward-compatible `evidence`/`kbEntries` fields
 * (Q8 — not yet populated by the backend; see `src/api/investigation-detail.ts`),
 * while the SSE payload only ever carries `{order, key, label, state, type}`
 * (Task 1.6's `_generate_json_sse_events` doc). So a live update to a step
 * that already exists from the initial fetch REPLACES only the fields the
 * event actually carries (label/state/type) and preserves any `evidence`/
 * `kbEntries` already present — a live update must never regress a step back
 * to "no evidence" just because the stream payload doesn't carry that field.
 *
 * A live event for an `order` not present in the initial fetch (a step that
 * appeared after the initial page load) is inserted at the correct sorted
 * position, never blindly appended — matching the spec's out-of-order-insert
 * rule for the timeline (`docs/specs/ux-design-specification.md` §5,
 * "checks if the order is sequential... inserts at the correct position").
 */
export function mergeLiveStepEvents(
  initialSteps: InvestigationStepDto[],
  liveEvents: InvestigationStepEventPayload[],
): InvestigationStepDto[] {
  if (liveEvents.length === 0) return initialSteps

  const byOrder = new Map<number, InvestigationStepDto>(
    initialSteps.map((step) => [step.order, step]),
  )

  for (const event of liveEvents) {
    const existing = byOrder.get(event.order)
    byOrder.set(event.order, {
      order: event.order,
      key: event.key,
      label: event.label,
      state: event.state as InvestigationStepState,
      type: event.type,
      evidence: existing?.evidence,
      kbEntries: existing?.kbEntries,
    })
  }

  return Array.from(byOrder.values()).sort((a, b) => a.order - b.order)
}

/**
 * Terminal step states, ordered from "no progress yet" to "done" — used by
 * `mergeBackfilledSteps` to decide which side of a merge represents more
 * progress on a given step, per Task 2.6b's "no regression of already-shown
 * steps" AC.
 */
const STEP_STATE_RANK: Record<string, number> = {
  pending: 0,
  active: 1,
  error: 2,
  completed: 2,
}

/**
 * Merge a Task 2.6b reconnect-backfill fetch (a fresh
 * `GET /api/v1/investigations/{id}` ordered step list) into the steps
 * already rendered, keyed by `order`.
 *
 * This is the REST side of the reconnect backfill: `mergeLiveStepEvents`
 * (Task 2.6a, above) already merges live SSE `step` events into the initial
 * fetch by `order`; this function merges a full re-fetched snapshot the
 * same way, so both merges share one dedupe/ordering rule for the whole
 * page (`InvestigationDetailPage.tsx` layers this UNDER `mergeLiveStepEvents`
 * — the backfill becomes the new baseline, live events still apply on top).
 *
 * Two properties the AC requires, both structural rather than incidental:
 *   - **Deduped / no duplicates**: `byOrder` is a `Map` keyed by `order` —
 *     it is structurally impossible to end up with two entries for the same
 *     step, regardless of how many times a backfill snapshot is applied.
 *   - **Idempotent**: applying the exact same backfill snapshot twice (e.g.
 *     two reconnects in a row before any new live event arrives) yields the
 *     same result both times — merging is keyed purely by `order` from the
 *     two inputs, with no mutable/incremental state carried between calls.
 *   - **No regression of already-shown steps**: for a given `order` present
 *     on both sides, the step with the further-along `state` wins (a
 *     backfill snapshot requested slightly before a fast-moving live event
 *     landed could otherwise appear to "undo" that step back to `pending`).
 *     Whichever side wins, `evidence`/`kbEntries` are preserved from
 *     whichever side actually carries them (matching `mergeLiveStepEvents`'s
 *     same rule) since the backfill's REST payload is the only side that
 *     ever carries those forward-compatible fields (Q8).
 *
 * @param currentSteps The steps already rendered (initial fetch, merged with
 *   whatever's already been backfilled/streamed so far).
 * @param backfill The freshly re-fetched ordered step list, or `null` before
 *   the first reconnect has completed (in which case `currentSteps` passes
 *   through unchanged).
 */
export function mergeBackfilledSteps(
  currentSteps: InvestigationStepDto[],
  backfill: InvestigationStepDto[] | null,
): InvestigationStepDto[] {
  if (backfill == null) return currentSteps
  if (backfill.length === 0) return currentSteps

  const byOrder = new Map<number, InvestigationStepDto>(
    currentSteps.map((step) => [step.order, step]),
  )

  for (const incoming of backfill) {
    const existing = byOrder.get(incoming.order)
    if (existing == null) {
      byOrder.set(incoming.order, incoming)
      continue
    }

    const incomingRank = STEP_STATE_RANK[incoming.state] ?? 0
    const existingRank = STEP_STATE_RANK[existing.state] ?? 0
    const winner = incomingRank >= existingRank ? incoming : existing
    const loser = winner === incoming ? existing : incoming

    byOrder.set(incoming.order, {
      ...winner,
      evidence: winner.evidence ?? loser.evidence,
      kbEntries: winner.kbEntries ?? loser.kbEntries,
    })
  }

  return Array.from(byOrder.values()).sort((a, b) => a.order - b.order)
}
