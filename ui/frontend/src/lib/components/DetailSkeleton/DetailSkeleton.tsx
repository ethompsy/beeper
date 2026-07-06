import { cn } from '../../utils/cn'

/**
 * DetailSkeleton — cold-load placeholder for the investigation detail view
 * (NFR19 triage glance: never a blank frame while the one-shot detail fetch
 * is in flight). Header skeleton + a handful of placeholder step rows,
 * matching `SummaryHeader`/`InvestigationStep`'s surface tokens so the
 * transition from skeleton to real content doesn't jump.
 *
 * `animate-pulse` + `motion-reduce:animate-none` follows the same
 * established pattern as `RelatedKbPanel`'s loading state
 * (`src/lib/components/RelatedKbPanel/RelatedKbPanel.tsx`).
 */
export interface DetailSkeletonProps {
  className?: string
}

export function DetailSkeleton({ className }: DetailSkeletonProps) {
  return (
    <div
      data-testid="detail-skeleton"
      className={cn('flex flex-col gap-4 motion-reduce:animate-none', className)}
    >
      <div className="flex flex-col gap-2 bg-surface-raised p-4 animate-pulse motion-reduce:animate-none">
        <div className="h-5 w-48 rounded-md bg-surface-overlay" />
        <div className="h-4 w-64 rounded-md bg-surface-overlay" />
      </div>
      <ul className="flex flex-col gap-2">
        {[1, 2, 3].map((i) => (
          <li
            key={i}
            className="flex flex-col gap-1 border-l-2 border-l-surface-overlay bg-surface-raised p-3 animate-pulse motion-reduce:animate-none"
          >
            <div className="h-3 w-24 rounded-md bg-surface-overlay" />
            <div className="h-4 w-full rounded-md bg-surface-overlay" />
          </li>
        ))}
      </ul>
    </div>
  )
}
