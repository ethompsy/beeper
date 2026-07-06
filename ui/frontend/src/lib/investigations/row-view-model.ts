import type { InvestigationCardVariant } from '../components/InvestigationCard'
import type { StatusBadgeVariant } from '../components/StatusBadge'
import type { InvestigationListItem } from '../../api/investigations-list'
import { deriveComponent } from './derive-component'
import { deriveProblemState } from './problem-state'

/**
 * row-view-model.ts — pure mapping from the Task 1.6 JSON API shape to the
 * `InvestigationCard` props used by the list row (Task 2.2).
 *
 * Kept separate from `status-group.ts` (ordering/filtering) and the page
 * component (data fetching) so each concern is independently testable and so
 * Task 2.3 (affected-component derivation) and Task 2.4 (problem-state
 * mapping) have an obvious, narrow seam to extend rather than needing to
 * touch fetch/order/filter logic.
 *
 * Severity label casing: the API returns lowercase severity ('low' | 'medium'
 * | 'high' | 'critical'); the card displays the glossary's title-case label.
 */
const SEVERITY_LABELS: Record<InvestigationListItem['severity'], string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  critical: 'Critical',
}

/**
 * job-phase `status` → `InvestigationCard` left-border variant.
 *
 * Per the glossary (StatusBadge.tsx variant taxonomy doc), "Investigating"
 * badge derivation must come from workflow/pipeline state, NOT `phase ==
 * Running` — but the CARD's variant (border color/opacity) is a coarser,
 * three-way active/completed/failed grouping that mirrors the status-group
 * membership (Task 2.2 AC: active+high-severity first / status-group
 * filter), which IS keyed off job-phase `status`. These are two different
 * axes rendered by two different pieces (card border vs. badge label) — see
 * `toStatusBadgeVariant` below for the badge's derivation.
 */
function toCardVariant(status: InvestigationListItem['status']): InvestigationCardVariant {
  if (status === 'completed') return 'completed'
  if (status === 'failed') return 'failed'
  return 'active'
}

/**
 * job-phase `status` → `StatusBadge` variant.
 *
 * Glossary OD-1 / StatusBadge doc: "Investigating" must derive from
 * workflow/pipeline state, NOT `phase == Running`. This list endpoint's
 * `status` field IS the job-phase axis (`investigating` here means the
 * investigator job is actively running its pipeline, not the workflow-state
 * `investigating` value) — job-phase `investigating` maps to the
 * `investigating` badge variant because for THIS axis (job phase), that is
 * the correct label; `awaiting_confirmation` maps 1:1; job-phase `failed`
 * maps to `analysis-failed` (OD-1: job-phase Failed → "Analysis Failed",
 * distinct from workflow-state Failed).
 *
 * `pending` is not a value the `status` field itself carries — it is
 * distinguished from `investigating` using `workflow_state` (see
 * `resolvePendingState` below), per the AC "Pending rows are visually
 * distinct from Running."
 */
function toStatusBadgeVariant(status: InvestigationListItem['status']): StatusBadgeVariant {
  switch (status) {
    case 'completed':
      return 'completed'
    case 'failed':
      return 'analysis-failed'
    case 'awaiting_confirmation':
      return 'awaiting-confirmation'
    case 'investigating':
    default:
      return 'investigating'
  }
}

/**
 * Pending vs. Running distinction (Task 2.2 AC).
 *
 * The list JSON API doesn't expose a dedicated "pending" job-phase value
 * (`VALID_STATUSES` server-side is investigating/awaiting_confirmation/
 * completed/failed) — an investigation is "Pending" when its `status` is
 * `investigating` but its `workflow_state` hasn't yet advanced past
 * `detected` (i.e. the investigator job hasn't started actively working the
 * pipeline steps yet). Once `workflow_state` reaches `investigating` (or
 * beyond), the row is "Running".
 *
 * This is a best-effort, list-only heuristic scoped to Task 2.2 — it does
 * NOT touch the job-phase/workflow-state StatusBadge taxonomy itself (that's
 * owned by StatusBadge.tsx) and is intentionally narrow: it only decides
 * which of the two *visual* variants (`pending` vs `investigating`) an
 * active-but-not-yet-confirmed row uses.
 */
function isPending(item: InvestigationListItem): boolean {
  return item.status === 'investigating' && (item.workflow_state == null || item.workflow_state === 'detected')
}

/**
 * Resolve the final StatusBadge variant, applying the Pending override for
 * active job-phase rows so Pending is visually distinct from Running
 * (distinct badge color/label, not just the shared "active" card border).
 */
export function resolveStatusBadgeVariant(item: InvestigationListItem): StatusBadgeVariant {
  if (isPending(item)) return 'pending'
  return toStatusBadgeVariant(item.status)
}

/**
 * Format an ISO timestamp as a coarse relative-age string ("Xm/h/d ago").
 * Mirrors the coarseness of `format_mttr` server-side (main age unit only,
 * no seconds precision) since the list row only needs at-a-glance age, not
 * exact duration (FR45/46: "age" is a glance fact).
 */
export function formatAge(isoTimestamp: string | null, now: Date = new Date()): string {
  if (!isoTimestamp) return 'Unknown'
  const then = new Date(isoTimestamp)
  if (Number.isNaN(then.getTime())) return 'Unknown'

  const diffMs = now.getTime() - then.getTime()
  const diffSeconds = Math.max(0, Math.floor(diffMs / 1000))

  if (diffSeconds < 60) return 'Just now'
  const diffMinutes = Math.floor(diffSeconds / 60)
  if (diffMinutes < 60) return `${diffMinutes}m ago`
  const diffHours = Math.floor(diffMinutes / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.floor(diffHours / 24)
  return `${diffDays}d ago`
}

export interface InvestigationRowViewModel {
  id: string
  href: string
  variant: InvestigationCardVariant
  serviceName: string
  severity: string
  statusVariant: StatusBadgeVariant
  timestamp: string
  /**
   * Raw `condition` field, unprocessed. Kept alongside the derived
   * `problemState`/`component` fields below per the glossary (OD-4): the RAW
   * field stays labeled "Condition" and the DERIVED plain-language
   * `problemState` (Task 2.4) coexists with it rather than replacing it.
   */
  condition: string | null
  /**
   * Best-effort "affected component" (Task 2.3), derived from `condition` via
   * `deriveComponent` (src/lib/investigations/derive-component.ts). `null`
   * when the condition text doesn't match any known detector shape — the
   * card's `component` slot omits the line entirely in that case.
   */
  component: string | null
  /**
   * Standardized plain-language "problem state" (Task 2.4, FR47), derived
   * from `condition` via `deriveProblemState`
   * (src/lib/investigations/problem-state.ts). Unlike `component`, this is
   * never null/blank — when no heuristic pattern matches, it falls back to
   * the raw `condition` text verbatim (FR47's explicit fallback rule).
   */
  problemState: string
}

/** Map one API item to the props the list row needs. Pure — no signal count from this endpoint (list-only field; detail view Task 2.5 has it). */
export function toRowViewModel(item: InvestigationListItem, now?: Date): InvestigationRowViewModel {
  const ageSource = item.started_at ?? item.triggered_at
  return {
    id: item.id,
    href: `/investigations/${item.id}`,
    variant: toCardVariant(item.status),
    serviceName: item.service,
    severity: SEVERITY_LABELS[item.severity] ?? item.severity,
    statusVariant: resolveStatusBadgeVariant(item),
    timestamp: formatAge(ageSource, now),
    condition: item.condition,
    component: deriveComponent(item.condition),
    problemState: deriveProblemState(item.condition),
  }
}
