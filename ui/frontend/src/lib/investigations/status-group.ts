import type { InvestigationListItem, InvestigationSeverity } from '../../api/investigations-list'

/**
 * status-group.ts — pure ordering/filtering logic for the investigation list
 * (Task 2.2, FR22/FR46).
 *
 * Deliberately pure functions with no React/URL/state dependency: Task 3.1
 * (Milestone 1.3) will lift `StatusGroup` selection into the URL query
 * string, and needs to be able to parse/serialize it without touching this
 * module's ordering/filtering behavior. Keep it that way — no `useState`,
 * `useSearchParams`, or router imports here.
 */

/** UI status-group values (FR22) — mirrors `STATUS_GROUPS` in investigations.py. */
export type StatusGroup = 'active' | 'resolved' | 'failed'

export const STATUS_GROUPS: readonly StatusGroup[] = ['active', 'resolved', 'failed']

/** status-group → constituent job-phase `status` values (mirrors the Python `STATUS_GROUPS` dict exactly). */
const STATUS_GROUP_MEMBERSHIP: Record<StatusGroup, ReadonlySet<InvestigationListItem['status']>> = {
  active: new Set(['investigating', 'awaiting_confirmation']),
  resolved: new Set(['completed']),
  failed: new Set(['failed']),
}

export const DEFAULT_STATUS_GROUP: StatusGroup = 'active'

/** Human-readable labels for the filter control. */
export const STATUS_GROUP_LABELS: Record<StatusGroup, string> = {
  active: 'Active',
  resolved: 'Resolved',
  failed: 'Failed',
}

/** Severity rank for sorting — higher first (FR46: "high-severity first"). */
const SEVERITY_RANK: Record<InvestigationSeverity, number> = {
  critical: 3,
  high: 2,
  medium: 1,
  low: 0,
}

export function severityRank(severity: InvestigationSeverity): number {
  return SEVERITY_RANK[severity] ?? -1
}

/** Filter a list down to the investigations belonging to `group`. */
export function filterByStatusGroup(
  investigations: InvestigationListItem[],
  group: StatusGroup,
): InvestigationListItem[] {
  const allowed = STATUS_GROUP_MEMBERSHIP[group]
  return investigations.filter((inv) => allowed.has(inv.status))
}

/**
 * Order investigations "active + high-severity first" (FR46).
 *
 * Two-tier sort:
 *   1. Active investigations (status group `active`) sort before anything
 *      else — this holds even when the caller passes an unfiltered list
 *      (e.g. a future "all" view), and is a no-op within an
 *      already-single-group list (all rows share tier 0 or 1 together).
 *   2. Within each tier, higher severity sorts first.
 *
 * Sort is stable (`Array.prototype.toSorted`/`sort` in modern engines
 * preserves order of equal elements), so investigations with identical
 * active-tier + severity retain the server's original relative order.
 */
export function orderInvestigations(investigations: InvestigationListItem[]): InvestigationListItem[] {
  const withIndex = investigations.map((inv, index) => ({ inv, index }))

  withIndex.sort((a, b) => {
    const aActive = STATUS_GROUP_MEMBERSHIP.active.has(a.inv.status) ? 0 : 1
    const bActive = STATUS_GROUP_MEMBERSHIP.active.has(b.inv.status) ? 0 : 1
    if (aActive !== bActive) return aActive - bActive

    const severityDiff = severityRank(b.inv.severity) - severityRank(a.inv.severity)
    if (severityDiff !== 0) return severityDiff

    // Stable tie-break on original position.
    return a.index - b.index
  })

  return withIndex.map(({ inv }) => inv)
}

/** Convenience: filter by group, then apply the active+high-severity-first ordering. */
export function selectAndOrder(
  investigations: InvestigationListItem[],
  group: StatusGroup,
): InvestigationListItem[] {
  return orderInvestigations(filterByStatusGroup(investigations, group))
}
