import { cn } from '../../utils/cn'

/**
 * KbEntryNotFound — renders "Entry {id} not found" INSIDE the app shell
 * (sidebar still visible), not a generic 404 (Task 5.1, mirroring
 * `NotFoundMessage`'s exact pattern for investigation detail —
 * docs/specs/ux-design-specification.md "Direct URL" row).
 *
 * Kept as its own component rather than reusing `NotFoundMessage` directly:
 * that component's copy ("Investigation {id} not found") is hardcoded to
 * the investigation domain, and `InvestigationDetailPage.tsx` (a file this
 * task must not touch) is its only current call site — generalizing its
 * prop contract would mean editing that call site too. This mirrors the
 * same UX pattern with KB-appropriate copy instead.
 */
export interface KbEntryNotFoundProps {
  entryId: string
  className?: string
}

export function KbEntryNotFound({ entryId, className }: KbEntryNotFoundProps) {
  return (
    <div data-slot="kb-entry-not-found" className={cn('flex flex-col gap-2 p-4', className)}>
      <h1 className="text-lg font-semibold text-text-primary">Knowledge Base entry not found</h1>
      <p className="text-base text-text-secondary">Entry {entryId} not found.</p>
    </div>
  )
}
