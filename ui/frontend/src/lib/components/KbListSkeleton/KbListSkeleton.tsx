import { cn } from '../../utils/cn'

/**
 * KbListSkeleton — placeholder rows shown on cold load of the KB browse/
 * search list (Task 5.1, NFR19 — "never a blank frame"). Same visual
 * language as `InvestigationListSkeleton` (gray pulsing blocks on
 * `surface-raised`), kept as its own component rather than reusing that one
 * directly so the `aria-label` accurately says "knowledge base entries"
 * instead of "investigations" for screen-reader users.
 */
export interface KbListSkeletonProps {
  /** Number of placeholder rows to render. Defaults to a typical above-the-fold count. */
  rowCount?: number
}

export function KbListSkeleton({ rowCount = 5 }: KbListSkeletonProps) {
  return (
    <div
      data-slot="kb-list-skeleton"
      role="status"
      aria-label="Loading knowledge base entries"
      className="flex flex-col gap-2"
    >
      {Array.from({ length: rowCount }, (_, index) => (
        <div
          key={index}
          data-slot="kb-list-skeleton-row"
          className={cn(
            'flex flex-col gap-2 rounded-md bg-surface-raised p-4',
            'animate-pulse motion-reduce:animate-none',
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <div className="h-4 w-56 rounded bg-surface-overlay" />
            <div className="h-4 w-20 rounded bg-surface-overlay" />
          </div>
          <div className="h-3 w-32 rounded bg-surface-overlay" />
          <div className="h-3 w-full rounded bg-surface-overlay" />
        </div>
      ))}
    </div>
  )
}
