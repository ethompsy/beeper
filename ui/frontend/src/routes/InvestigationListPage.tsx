import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  InvestigationCard,
  InvestigationListSkeleton,
  StatusGroupFilter,
  EmptyGroupState,
  useScrollRestoration,
  type StatusGroupFilterOption,
} from '../lib'
import { fetchInvestigations, type InvestigationListItem } from '../api/investigations-list'
import {
  DEFAULT_STATUS_GROUP,
  STATUS_GROUPS,
  STATUS_GROUP_LABELS,
  filterByStatusGroup,
  selectAndOrder,
  type StatusGroup,
} from '../lib/investigations/status-group'
import { toRowViewModel } from '../lib/investigations/row-view-model'
import type { InvestigationCardLinkProps } from '../lib'

/**
 * Adapts React Router's `Link` (which takes `to`) to `InvestigationCard`'s
 * `linkComponent` contract (which takes `href`) — mirrors `AppLayout.tsx`'s
 * `RouterLink` adapter for the sidebar. Passing `Link` here (rather than the
 * default plain `<a>`) makes clicking a row a client-side route transition,
 * which is required for scroll-position restoration to mean anything (a
 * full page reload would re-mount the whole app from scratch).
 */
function InvestigationCardRouterLink({ href, children, ...rest }: InvestigationCardLinkProps) {
  return (
    <Link to={href} {...rest}>
      {children}
    </Link>
  )
}

/**
 * InvestigationListPage — the "first-seconds" triage list (Task 2.2).
 *
 * Fetches `GET /api/v1/investigations` (Task 1.6) via the plain-`fetch`
 * client in `src/api/investigations-list.ts`, then:
 *   - filters to the selected status group (FR22: active/resolved/failed),
 *   - orders active + high-severity investigations first (FR46),
 *   - renders each row as an `InvestigationCard` (FR45/46: service,
 *     component slot, severity, age, status — no horizontal scroll),
 *   - shows a skeleton while the initial fetch is in flight (NFR19),
 *   - shows an explanatory waiting state when the selected group is empty
 *     (FR22), and
 *   - restores scroll position when returning from the detail route (FR22).
 *
 * Filter state is local `useState` for now (Task 3.1 lifts it into the URL
 * query string) — kept as a single `StatusGroup` value passed through pure
 * functions (`status-group.ts`) so that migration is a matter of swapping
 * the state source, not rewriting the filter logic.
 *
 * "Affected component" (Task 2.3) and plain-language "problem state" (Task
 * 2.4, FR47) are both derived from the same raw `condition` field by
 * `toRowViewModel` (see `row-view-model.ts`, `derive-component.ts`,
 * `problem-state.ts`) and passed straight through to `InvestigationCard`'s
 * `component`/`problemState` slots — two distinct first-seconds facts
 * (FR45/46), not a replacement of one for the other.
 */
export function InvestigationListPage() {
  const [investigations, setInvestigations] = useState<InvestigationListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [statusGroup, setStatusGroup] = useState<StatusGroup>(DEFAULT_STATUS_GROUP)

  const isLoading = investigations === null && error === null
  // Scroll restoration must wait until the real content (not the loading
  // skeleton) has rendered — see useScrollRestoration's `ready` doc comment.
  useScrollRestoration('/investigations', !isLoading)

  useEffect(() => {
    const controller = new AbortController()

    fetchInvestigations(undefined, controller.signal)
      .then((data) => {
        setInvestigations(data)
        setError(null)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setError(err instanceof Error ? err.message : 'Unable to connect to the Beeper operator.')
      })

    return () => controller.abort()
  }, [])

  const groupCounts = useMemo(() => {
    const counts: Record<StatusGroup, number> = { active: 0, resolved: 0, failed: 0 }
    if (!investigations) return counts
    for (const group of STATUS_GROUPS) {
      counts[group] = filterByStatusGroup(investigations, group).length
    }
    return counts
  }, [investigations])

  const filterOptions: StatusGroupFilterOption[] = STATUS_GROUPS.map((group) => ({
    id: group,
    label: STATUS_GROUP_LABELS[group],
    count: investigations ? groupCounts[group] : undefined,
  }))

  const rows = useMemo(() => {
    if (!investigations) return []
    return selectAndOrder(investigations, statusGroup).map((inv) => toRowViewModel(inv))
  }, [investigations, statusGroup])

  return (
    <div data-testid="investigation-list-page" className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold text-text-primary">Investigations</h1>
        <StatusGroupFilter options={filterOptions} selectedId={statusGroup} onSelect={(id) => setStatusGroup(id as StatusGroup)} />
      </div>

      {error ? (
        <div
          role="alert"
          className="rounded-md border border-status-critical/30 bg-surface-raised p-4 text-sm text-status-critical"
        >
          <p className="font-semibold">Unable to fetch investigations</p>
          <p className="mt-1 text-text-secondary">{error}</p>
        </div>
      ) : null}

      {isLoading ? <InvestigationListSkeleton /> : null}

      {!isLoading && !error ? (
        rows.length > 0 ? (
          <div data-testid="investigation-list-rows" className="flex flex-col gap-2">
            {rows.map((row) => (
              <InvestigationCard
                key={row.id}
                variant={row.variant}
                serviceName={row.serviceName}
                severity={row.severity}
                statusVariant={row.statusVariant}
                timestamp={row.timestamp}
                component={row.component}
                problemState={row.problemState}
                href={row.href}
                linkComponent={InvestigationCardRouterLink}
              />
            ))}
          </div>
        ) : (
          <EmptyGroupState {...emptyStateCopy(statusGroup)} />
        )
      ) : null}
    </div>
  )
}

function emptyStateCopy(group: StatusGroup): { title: string; description: string } {
  switch (group) {
    case 'resolved':
      return {
        title: 'No resolved investigations',
        description: 'Resolved investigations will appear here once they are completed successfully.',
      }
    case 'failed':
      return {
        title: 'No failed investigations',
        description: 'Failed investigations will appear here when Beeper encounters an error during analysis.',
      }
    case 'active':
    default:
      return {
        title: 'No active investigations',
        description: 'Investigations appear automatically when Beeper detects anomalies in your services.',
      }
  }
}
