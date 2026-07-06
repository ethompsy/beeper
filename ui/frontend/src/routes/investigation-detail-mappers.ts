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
