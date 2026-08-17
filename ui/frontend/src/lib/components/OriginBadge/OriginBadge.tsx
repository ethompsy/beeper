import { cn } from '../../utils/cn'

/**
 * OriginBadge — small pill distinguishing a `local` (admin-created,
 * password-based) user record from a `scim`-provisioned one (Task 8.7,
 * ADR 0002 §5/§6, FR60).
 *
 * A standalone tiny component rather than a `StatusBadge` variant
 * (design decision, documented per the task instructions): `StatusBadge`'s
 * variant taxonomy is explicitly scoped to *status* axes (job phase,
 * workflow state, pipeline health, connection health) that share one color
 * language (healthy/warning/critical/muted mapped to real operational
 * state). Origin is not a status — it's a provenance label with no
 * good/bad connotation, so forcing it through `StatusBadge`'s
 * healthy/critical color vocabulary would misuse that semantic (a `scim`
 * origin is not "worse" than `local`). This component reuses the exact
 * same visual language (`cn()`-composed pill: rounded-full, tight padding,
 * text-xs font-medium) so it reads as part of the same design system, but
 * keeps origin's own two-way distinction (both `primary`-family and
 * `status-muted`-family tokens — neither implies health) independent of
 * `StatusBadge`'s variant table.
 */
export type OriginBadgeVariant = 'local' | 'scim'

export interface OriginBadgeProps {
  origin: OriginBadgeVariant
  className?: string
}

const LABELS: Record<OriginBadgeVariant, string> = {
  local: 'Local',
  scim: 'SCIM',
}

/** `local` uses the primary/brand token (admin-managed); `scim` uses the neutral muted token (externally provisioned). */
const STYLES: Record<OriginBadgeVariant, string> = {
  local: 'bg-primary/10 text-primary',
  scim: 'bg-surface-overlay text-status-muted',
}

export function OriginBadge({ origin, className }: OriginBadgeProps) {
  return (
    <span
      data-slot="origin-badge"
      data-origin={origin}
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
        STYLES[origin],
        className,
      )}
    >
      {LABELS[origin]}
    </span>
  )
}
