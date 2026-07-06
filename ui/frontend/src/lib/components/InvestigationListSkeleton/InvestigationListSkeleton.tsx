import { cn } from '../../utils/cn'

/**
 * InvestigationListSkeleton — placeholder rows shown on cold load
 * (Task 2.2, NFR19 / docs/specs/ux-design-specification.md "Loading &
 * Empty" — "Skeleton screens matching layout shape — gray pulsing blocks on
 * `surface-raised`").
 *
 * Renders `rowCount` placeholder blocks shaped like `InvestigationCard` so
 * the loading state never collapses to a blank frame. Purely presentational
 * — the list page decides when to show this (initial fetch in flight, no
 * cached data yet).
 */
export interface InvestigationListSkeletonProps {
  /** Number of placeholder rows to render. Defaults to a typical above-the-fold count. */
  rowCount?: number
}

export function InvestigationListSkeleton({ rowCount = 5 }: InvestigationListSkeletonProps) {
  return (
    <div
      data-slot="investigation-list-skeleton"
      role="status"
      aria-label="Loading investigations"
      className="flex flex-col gap-2"
    >
      {Array.from({ length: rowCount }, (_, index) => (
        <div
          key={index}
          data-slot="investigation-list-skeleton-row"
          className={cn(
            'flex flex-col gap-2 rounded-md border-l-2 border-l-surface-overlay bg-surface-raised p-4',
            'animate-pulse motion-reduce:animate-none',
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <div className="h-4 w-32 rounded bg-surface-overlay" />
            <div className="h-4 w-20 rounded-full bg-surface-overlay" />
          </div>
          <div className="h-3 w-48 rounded bg-surface-overlay" />
        </div>
      ))}
    </div>
  )
}
