import type { AnchorHTMLAttributes, ComponentType, ReactNode } from 'react'
import { cn } from '../../utils/cn'
import { StatusBadge, type StatusBadgeVariant } from '../StatusBadge'

/**
 * InvestigationCard — list-item primitive representing one investigation
 * (docs/specs/ux-design-specification.md §3 `investigation_card` macro).
 *
 * SKELETON (Task 1.4): correct props + token-based styling + Storybook
 * story per variant. Real data wiring, hover/highlight/entrance animation,
 * and scroll-restoration integration land with Task 2.2 (Milestone 1.2).
 *
 * `component` (Task 2.2/2.3): an optional subtitle slot rendering the
 * affected-component text (the legacy Jinja `investigation_card` macro
 * renders `inv.condition` here; Task 2.3's `deriveComponent` now feeds this
 * slot). This slot intentionally accepts a pre-derived string — deriving
 * "affected component" from the raw `condition`/anomaly signal is Task 2.3's
 * job; this component stays a dumb presentational primitive that renders
 * whatever string it's given.
 *
 * `problemState` (Task 2.4): a second, separate subtitle line rendering the
 * FR47 plain-language problem-state text (`deriveProblemState`,
 * `src/lib/investigations/problem-state.ts`). FR45/46 list "component" and
 * "problem state" as two distinct first-seconds facts the row must
 * communicate, so this is an additive sibling slot to `component`, not a
 * replacement — both may render at once (e.g. "CPU / compute resources" as
 * the component, "High CPU usage (92.0)" as the problem state).
 *
 * `linkComponent` (Task 2.2): mirrors the `Sidebar`/`AppShell` injectable-link
 * pattern (Task 2.1) so this primitive stays router-agnostic while still
 * supporting real client-side navigation. Without it, the card renders a
 * plain `<a>` (Storybook-safe, matches the original Task 1.4 skeleton).
 * `src/routes/InvestigationListPage.tsx` passes React Router's `Link` so
 * clicking a row is a client-side transition (required for the "flipping
 * pages in a book" list<->detail feel and scroll-position restoration —
 * a plain `<a>` would force a full page reload, discarding SPA state).
 */
export type InvestigationCardVariant = 'active' | 'completed' | 'failed'

export interface InvestigationCardLinkProps {
  href: string
  className?: string
  'aria-label'?: string
  'data-slot'?: string
  'data-variant'?: string
  children?: ReactNode
  [key: string]: unknown
}

export interface InvestigationCardProps
  extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> {
  /** Card visual variant — drives left-border color + opacity per the spec's state table. */
  variant: InvestigationCardVariant
  /** Service name (text-base, font-semibold). */
  serviceName: string
  /** Severity label (Low/Medium/High/Critical) rendered as a badge. */
  severity: string
  /**
   * Number of correlated signals. Optional — the Task 1.6 list JSON API
   * doesn't return a signal count (only the detail endpoint does), so the
   * list row (Task 2.2) omits this prop entirely rather than showing a
   * fabricated "0 signals".
   */
  signalCount?: number
  /** Pre-formatted relative timestamp string (e.g. "3m ago"). Formatting is a view concern. */
  timestamp: string
  /** Status badge variant for the job-phase status indicator (see StatusBadge). */
  statusVariant: StatusBadgeVariant
  /** href for the underlying link — the whole card is the click target (a11y: single link, not nested interactive elements). */
  href: string
  /**
   * Affected component subtitle line (raw or derived — caller's choice).
   * Optional and omitted entirely from the DOM when unset, so callers that
   * have nothing to show yet don't render an empty line.
   */
  component?: string | null
  /**
   * Plain-language problem-state subtitle line (Task 2.4, FR47) — a separate
   * fact from `component` (see class doc above). Optional and omitted
   * entirely from the DOM when unset (matches `component`'s convention), but
   * callers using `toRowViewModel` always have a non-null value to pass
   * (FR47's fallback-to-raw-condition rule means it's never blank in
   * practice).
   */
  problemState?: string | null
  /**
   * Render-prop-free link component injection — pass `Link` from
   * `react-router-dom` for client-side navigation, or omit for a plain
   * `<a>` (default; Storybook-safe).
   */
  linkComponent?: ComponentType<InvestigationCardLinkProps>
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

function DefaultLink({ href, children, ...rest }: InvestigationCardLinkProps) {
  return (
    <a href={href} {...rest}>
      {children}
    </a>
  )
}

export function InvestigationCard({
  variant,
  serviceName,
  severity,
  signalCount,
  timestamp,
  statusVariant,
  href,
  component,
  problemState,
  linkComponent: LinkComponent = DefaultLink,
  className,
  ...rest
}: InvestigationCardProps) {
  return (
    <LinkComponent
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
        {signalCount != null ? (
          <>
            <span aria-hidden="true">&middot;</span>
            <span data-field="signal-count">{signalCount} signals</span>
          </>
        ) : null}
        <span aria-hidden="true">&middot;</span>
        <span data-field="timestamp">{timestamp}</span>
      </div>
      {problemState ? (
        <div className="truncate text-sm text-text-primary" data-field="problem-state">
          {problemState}
        </div>
      ) : null}
      {component ? (
        <div className="truncate text-sm text-text-secondary" data-field="component">
          {component}
        </div>
      ) : null}
    </LinkComponent>
  )
}
