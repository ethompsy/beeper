import { cn } from '../../utils/cn'

/**
 * NotFoundMessage — renders "Investigation {id} not found" INSIDE the app
 * shell (sidebar still visible), not a generic 404 page
 * (docs/specs/ux-design-specification.md "Direct URL" row: "render
 * 'Investigation INV-0042 not found' in the layout shell with sidebar
 * visible — not a generic 404. User is one click from the investigation
 * list.").
 *
 * This is a page-body message, distinct from `App.tsx`'s catch-all
 * unmatched-route page (which handles genuinely unknown paths) — an
 * investigation detail route that resolves (matches `/investigations/:id`)
 * but whose id the backend doesn't recognize renders this instead.
 */
export interface NotFoundMessageProps {
  investigationId: string
  className?: string
}

export function NotFoundMessage({ investigationId, className }: NotFoundMessageProps) {
  return (
    <div data-slot="investigation-not-found" className={cn('flex flex-col gap-2 p-4', className)}>
      <h1 className="text-lg font-semibold text-text-primary">Investigation not found</h1>
      <p className="text-base text-text-secondary">
        Investigation {investigationId} not found.
      </p>
    </div>
  )
}
