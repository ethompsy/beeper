import { cn } from '../../utils/cn'

/**
 * IngestionStatsSkeleton — cold-load placeholder for the Ingestion Stats
 * dashboard (Task 5.2). Never a blank frame while the initial fetch is in
 * flight — same "skeleton, not blank" discipline as
 * `InvestigationListSkeleton`/`DetailSkeleton`, shaped like the tile grid
 * this page renders (2-up ingestion row + 3-up detection row) so the
 * skeleton-to-real-content transition doesn't jump.
 *
 * Only shown on the very first load — auto-refresh polls never re-show this
 * (see `IngestionStatsPage`), so it never causes the "flicker on refresh"
 * the AC explicitly rules out.
 */
export interface IngestionStatsSkeletonProps {
  className?: string
}

function TilePlaceholder() {
  return (
    <div className="flex flex-col gap-2 rounded-lg bg-surface-raised px-4 py-3 animate-pulse motion-reduce:animate-none">
      <div className="h-3 w-24 rounded bg-surface-overlay" />
      <div className="h-8 w-16 rounded bg-surface-overlay" />
    </div>
  )
}

export function IngestionStatsSkeleton({ className }: IngestionStatsSkeletonProps) {
  return (
    <div
      role="status"
      aria-label="Loading ingestion stats"
      className={cn('flex flex-col gap-6', className)}
    >
      <div className="h-6 w-32 animate-pulse rounded-md bg-surface-overlay motion-reduce:animate-none" />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <TilePlaceholder />
        <TilePlaceholder />
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <TilePlaceholder />
        <TilePlaceholder />
        <TilePlaceholder />
      </div>
    </div>
  )
}
