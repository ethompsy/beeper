import { cn } from '../../utils/cn'

/**
 * MetricTile — a single Grafana-style stat: small uppercase label, large
 * mono value, and an optional status-colored accent dot (Task 5.2, FR32/
 * FR33 — Ingestion Stats dashboard's "large scannable metric numbers").
 *
 * Ports the Jinja `metric_tile(label, value, status, trend)` macro
 * (`ui/beeper_ui/templates/components/diagnostic.html`) to a React
 * primitive. `status` drives the accent color exactly like the macro's
 * `data-status` branch: healthy/warning/critical/muted color the dot + value
 * text, `neutral` (default) renders no dot and the plain brand color.
 */
export type MetricTileStatus = 'healthy' | 'warning' | 'critical' | 'muted' | 'neutral'

export interface MetricTileProps {
  label: string
  value: string
  status?: MetricTileStatus
  className?: string
}

const ACCENT_TEXT: Record<MetricTileStatus, string> = {
  healthy: 'text-status-healthy',
  warning: 'text-status-warning',
  critical: 'text-status-critical',
  muted: 'text-status-muted',
  neutral: 'text-primary',
}

const ACCENT_DOT: Record<MetricTileStatus, string> = {
  healthy: 'bg-status-healthy',
  warning: 'bg-status-warning',
  critical: 'bg-status-critical',
  muted: 'bg-status-muted',
  neutral: 'bg-primary',
}

export function MetricTile({ label, value, status = 'neutral', className }: MetricTileProps) {
  return (
    <div
      data-slot="metric-tile"
      data-status={status}
      className={cn('flex flex-col gap-1 rounded-lg bg-surface-raised px-4 py-3', className)}
    >
      <div className="flex items-center gap-2">
        {status !== 'neutral' ? (
          <span
            aria-hidden="true"
            className={cn('h-2 w-2 shrink-0 rounded-full', ACCENT_DOT[status])}
          />
        ) : null}
        <span className="text-xs font-medium uppercase tracking-wide text-text-muted">{label}</span>
      </div>
      <span className={cn('font-mono text-3xl font-semibold leading-tight', ACCENT_TEXT[status])}>
        {value}
      </span>
    </div>
  )
}
