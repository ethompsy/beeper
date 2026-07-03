import type { AnchorHTMLAttributes } from 'react'
import { cn } from '../../utils/cn'
import { StatusBadge, type StatusBadgeVariant } from '../StatusBadge'

/**
 * InvestigationCard — list-item primitive representing one investigation
 * (docs/specs/ux-design-specification.md §3 `investigation_card` macro).
 *
 * SKELETON (Task 1.4): correct props + token-based styling + Storybook
 * story per variant. Real data wiring, hover/highlight/entrance animation,
 * and scroll-restoration integration land with Task 2.2 (Milestone 1.2).
 */
export type InvestigationCardVariant = 'active' | 'completed' | 'failed'

export interface InvestigationCardProps
  extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> {
  /** Card visual variant — drives left-border color + opacity per the spec's state table. */
  variant: InvestigationCardVariant
  /** Service name (text-base, font-semibold). */
  serviceName: string
  /** Severity label (Low/Medium/High/Critical) rendered as a badge. */
  severity: string
  /** Number of correlated signals. */
  signalCount: number
  /** Pre-formatted relative timestamp string (e.g. "3m ago"). Formatting is a view concern. */
  timestamp: string
  /** Status badge variant for the job-phase status indicator (see StatusBadge). */
  statusVariant: StatusBadgeVariant
  /** href for the underlying `<a>` — the whole card is the click target (a11y: single link, not nested interactive elements). */
  href: string
}

const VARIANT_BORDER: Record<InvestigationCardVariant, string> = {
  active: 'border-l-status-healthy',
  completed: 'border-l-status-muted',
  failed: 'border-l-status-critical',
}

const VARIANT_OPACITY: Record<InvestigationCardVariant, string> = {
  active: 'opacity-100',
  completed: 'opacity-70',
  failed: 'opacity-100',
}

export function InvestigationCard({
  variant,
  serviceName,
  severity,
  signalCount,
  timestamp,
  statusVariant,
  href,
  className,
  ...rest
}: InvestigationCardProps) {
  return (
    <a
      data-slot="investigation-card"
      data-variant={variant}
      href={href}
      aria-label={`${serviceName} investigation, ${severity} severity, ${statusVariant}`}
      className={cn(
        // NOTE: spec calls for a 3px left border; Tailwind's default border-width
        // scale has no `3` step and tokens.css (Task 1.2, not edited here) defines
        // no border-width token. Using the nearest token-safe built-in (`border-l-2`)
        // rather than an arbitrary-value `border-l-[3px]` (blocked by the FR51 lint
        // gate). Revisit if Milestone 1.2 adds a `--border-width-*` token.
        'flex flex-col gap-2 rounded-md border-l-2 bg-surface-raised p-4',
        'transition-colors motion-reduce:transition-none hover:bg-surface-overlay',
        VARIANT_BORDER[variant],
        VARIANT_OPACITY[variant],
        className,
      )}
      {...rest}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-base font-semibold text-text-primary">{serviceName}</span>
        <StatusBadge variant={statusVariant} />
      </div>
      <div className="flex items-center gap-2 text-sm text-text-secondary">
        <span data-field="severity">{severity}</span>
        <span aria-hidden="true">&middot;</span>
        <span data-field="signal-count">{signalCount} signals</span>
        <span aria-hidden="true">&middot;</span>
        <span data-field="timestamp">{timestamp}</span>
      </div>
    </a>
  )
}
