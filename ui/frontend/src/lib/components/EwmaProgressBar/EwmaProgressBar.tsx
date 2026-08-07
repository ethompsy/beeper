import { cn } from '../../utils/cn'

/**
 * EwmaProgressBar — the EWMA warmup progress bar (Task 5.2, FR33). Ports the
 * Jinja `ewma_progress(percentage, status)` macro
 * (`ui/beeper_ui/templates/components/diagnostic.html`) to a React
 * primitive.
 *
 * `percentage` is the raw clamped-0-100 value from
 * `derivePipelineView`/`_pipeline_view()` (`warmupPct` —
 * `samples / minimum * 100`); this component floors it to a whole percent
 * for display so the visible "NN%" text, `aria-valuenow`, and the fill
 * bar's width all agree — same floor-before-render discipline the Jinja
 * macro uses (`pct|round(0, 'floor')|int`), just done here instead of by
 * the caller, so every consumer gets the same rounding for free.
 *
 * The fill-width transition respects `prefers-reduced-motion`
 * (`motion-reduce:transition-none`), per FR51/NFR22.
 */
export interface EwmaProgressBarProps {
  /** Raw 0-100 percentage — not pre-floored, this component floors for display. */
  percentage: number
  /** `warning` while warming (amber fill), `healthy` once warmed (green fill). Defaults to `warning`. */
  status?: 'healthy' | 'warning'
  className?: string
}

export function EwmaProgressBar({ percentage, status = 'warning', className }: EwmaProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, percentage))
  const pct = Math.floor(clamped)
  const fill = status === 'healthy' ? 'bg-status-healthy' : 'bg-status-warning'

  return (
    <div data-slot="ewma-progress-bar" data-status={status} className={className}>
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs font-medium text-text-secondary">EWMA Warmup</span>
        <span className="font-mono text-xs text-text-muted">{pct}%</span>
      </div>
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-surface-overlay"
        role="progressbar"
        aria-label="EWMA warmup progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
      >
        <div
          className={cn(
            'h-full rounded-full transition-all duration-sidebar motion-reduce:transition-none',
            fill,
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
