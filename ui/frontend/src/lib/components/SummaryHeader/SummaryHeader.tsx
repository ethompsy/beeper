import type { HTMLAttributes } from 'react'
import { cn } from '../../utils/cn'
import { StatusBadge, type StatusBadgeVariant } from '../StatusBadge'

/**
 * SummaryHeader — the investigation detail "headline," renders immediately
 * from metadata with no SSE dependency (docs/specs/ux-design-specification.md
 * §4 `summary_header` macro; NFR19 first-seconds triage glance).
 *
 * Task 2.5 wires this up as the real detail-view header: `headingId`
 * carries `useRouteFocusManagement`'s (Task 2.1) `#detail-summary-heading`
 * contract onto the actual `<h1>` below (WCAG 2.4.3 — the hook focuses this
 * id on every detail-route mount, including a cold permalink load).
 */
export interface SummaryHeaderProps extends HTMLAttributes<HTMLElement> {
  /** Service name — rendered as the page `<h1>` (text-lg, font-semibold per spec). */
  serviceName: string
  /** Severity label (Low/Medium/High/Critical). */
  severity: string
  /** Number of correlated signals ("N signals"). */
  signalCount: number
  /** Job-phase status badge variant (Investigating / Awaiting Confirmation / Completed / Analysis Failed / Pending). */
  statusVariant: StatusBadgeVariant
  /** Pre-formatted timestamp string for the relevant lifecycle moment (Started/Completed). */
  timestamp?: string
  /**
   * Problem-state text (FR47 plain-language heuristic, or raw `condition`
   * fallback). Rendered as the header's lead sentence beneath the service
   * name. Left optional here — Task 2.4 owns the heuristic mapping.
   */
  problemState?: string
  /**
   * `id` for the `<h1>` (not the `<header>` wrapper — `...rest` still sets
   * attributes on the wrapper). Pass `"detail-summary-heading"` so
   * `useRouteFocusManagement` can focus it on route entry. Also sets
   * `tabIndex={-1}` on the `<h1>` so it's programmatically focusable
   * (headings aren't focusable by default).
   */
  headingId?: string
}

export function SummaryHeader({
  serviceName,
  severity,
  signalCount,
  statusVariant,
  timestamp,
  problemState,
  headingId,
  className,
  ...rest
}: SummaryHeaderProps) {
  return (
    <header
      data-slot="summary-header"
      className={cn('flex flex-col gap-2 bg-surface-raised p-4', className)}
      {...rest}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h1
          id={headingId}
          tabIndex={headingId != null ? -1 : undefined}
          className="text-lg font-semibold text-text-primary"
        >
          {serviceName}
        </h1>
        <span
          data-field="severity"
          className="rounded-full bg-status-warning/10 px-2 py-0.5 text-xs font-medium text-status-warning"
        >
          {severity}
        </span>
        <StatusBadge variant={statusVariant} />
      </div>
      {problemState != null ? (
        <p data-field="problem-state" className="text-base text-text-primary">
          {problemState}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2 text-sm text-text-secondary">
        <span data-field="signal-count">{signalCount} signals</span>
        {timestamp != null ? (
          <>
            <span aria-hidden="true">&middot;</span>
            <span data-field="timestamp">{timestamp}</span>
          </>
        ) : null}
      </div>
    </header>
  )
}
