import { useCallback, useEffect, useState } from 'react'
import {
  EwmaProgressBar,
  IngestionStatsSkeleton,
  MetricTile,
  StatusBadge,
  useAutoRefresh,
} from '../lib'
import { fetchIngestionStats, type IngestionStats } from '../api/ingestion-stats'
import {
  activeDetectorsStatus,
  anomaliesDetectedStatus,
  derivePipelineView,
  ingestionTileStatus,
  pipelineChipProps,
} from '../lib/ingestion/pipeline-view'

/**
 * IngestionStatsPage — the pipeline diagnostic dashboard (Task 5.2,
 * `/app/ingestion-stats`, per docs/design/route-parity-targets.md §3).
 *
 * Migrates `ui/beeper_ui/templates/health/ingestion.html` +
 * `_ingestion_content.html`'s parity surface:
 *   - ingestion throughput tiles (FR32: metrics_received, logs_received),
 *   - detection tiles (FR33: anomalies_detected, anomalies_suppressed,
 *     active_metric_detectors),
 *   - the EWMA warmup progress bar (FR33, shown only while warming), and
 *   - the three-state pipeline chip (red "No Data" / amber "Warming Up" /
 *     green "Active"), whose precedence is derived by
 *     `derivePipelineView` — a line-by-line port of `_pipeline_view()`
 *     (`ui/beeper_ui/routes/health.py`).
 *
 * ── Auto-refresh (replaces the Jinja `hx-trigger="every 5s"`) ──
 *
 * Polls `GET /api/v1/ingestion/stats` every 5s via `useAutoRefresh`
 * (`src/lib/hooks/useAutoRefresh.ts`), which pauses while the tab is
 * hidden. Refreshes update the same DOM in place — `isInitialLoad` only
 * ever gates the skeleton on the very first fetch, so a background refresh
 * never re-shows the skeleton, remounts the tile grid, or otherwise causes
 * layout shift; only the numbers/chip/progress-bar content change.
 *
 * ── Error handling (matches the Jinja per-request semantics) ──
 *
 * A failed fetch — initial or a later auto-refresh poll — clears `stats`
 * and shows the distinct error block, exactly mirroring
 * `ingestion_stats()`'s per-request behavior (`ingestion_stats_data = None`
 * on `HealthServiceError`): an HTMX poll that hits a down operator would
 * swap the same error partial in, wiping the tiles until the operator
 * recovers. This is intentional 1:1 parity, not an oversight — the
 * dashboard would otherwise show stale numbers next to no visible
 * indication anything is wrong.
 */
const REFRESH_INTERVAL_MS = 5000

const numberFormatter = new Intl.NumberFormat('en-US')

function formatCount(value: number | undefined): string {
  return numberFormatter.format(value ?? 0)
}

export function IngestionStatsPage() {
  const [stats, setStats] = useState<IngestionStats | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isInitialLoad, setIsInitialLoad] = useState(true)

  const load = useCallback((signal?: AbortSignal) => {
    fetchIngestionStats(signal)
      .then((data) => {
        setStats(data)
        setError(null)
      })
      .catch((err: unknown) => {
        if (signal?.aborted) return
        setStats(null)
        setError(err instanceof Error ? err.message : 'Unable to connect to the Beeper operator.')
      })
      .finally(() => {
        setIsInitialLoad(false)
      })
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  useAutoRefresh(() => load(), { intervalMs: REFRESH_INTERVAL_MS })

  const pipeline = derivePipelineView(stats)
  const chip = pipelineChipProps(pipeline.pipelineState)
  const ingestionStatus = ingestionTileStatus(pipeline.pipelineState)

  return (
    <div data-testid="ingestion-stats-page" className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-text-primary">Ingestion &amp; Detection</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Live pipeline diagnostics — ingestion throughput, anomaly detection, and EWMA warmup
          state.
        </p>
      </div>

      {isInitialLoad ? <IngestionStatsSkeleton /> : null}

      {!isInitialLoad && error ? (
        <div
          role="alert"
          className="rounded-md border-l-2 border-l-status-critical bg-surface-raised px-4 py-3"
        >
          <h2 className="font-medium text-text-primary">Unable to fetch ingestion stats</h2>
          <p className="mt-1 text-sm text-text-secondary">{error}</p>
          <p className="mt-1 text-sm text-text-muted">
            Make sure the Beeper operator is running and accessible.
          </p>
        </div>
      ) : null}

      {!isInitialLoad && stats ? (
        // aria-live="polite" mirrors the Jinja container's own
        // `aria-live="polite"` (`health/ingestion.html`) — auto-refresh
        // content updates are announced to assistive tech without requiring
        // a role="status" on every individual tile/chip.
        <div aria-live="polite" className="flex flex-col gap-6">
          <div className="flex items-center gap-3">
            <span className="text-sm text-text-secondary">Pipeline status</span>
            <StatusBadge variant={chip.variant} label={chip.label} />
          </div>

          <section aria-label="Ingestion throughput" className="flex flex-col gap-2">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              Ingestion
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <MetricTile
                label="Metrics Received"
                value={formatCount(stats.metrics_received)}
                status={ingestionStatus}
              />
              <MetricTile
                label="Logs Received"
                value={formatCount(stats.logs_received)}
                status={ingestionStatus}
              />
            </div>
          </section>

          <section aria-label="Anomaly detection" className="flex flex-col gap-2">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              Detection
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <MetricTile
                label="Anomalies Detected"
                value={formatCount(stats.anomalies_detected)}
                status={anomaliesDetectedStatus(stats.anomalies_detected)}
              />
              <MetricTile
                label="Anomalies Suppressed"
                value={formatCount(stats.anomalies_suppressed)}
                status="muted"
              />
              <MetricTile
                label="Active Metric Detectors"
                value={formatCount(stats.active_metric_detectors)}
                status={activeDetectorsStatus(stats.active_metric_detectors)}
              />
            </div>
          </section>

          {pipeline.isWarming ? (
            <section
              aria-label="EWMA warmup"
              className="max-w-md rounded-lg bg-surface-raised px-4 py-3"
            >
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">
                Warmup
              </h2>
              <EwmaProgressBar percentage={pipeline.warmupPct} status="warning" />
              <p className="mt-2 text-xs text-text-muted">
                {formatCount(stats.ewma_warmup_samples)} / {formatCount(stats.ewma_warmup_minimum)}{' '}
                samples — detectors warming up before anomaly scoring is trusted.
              </p>
            </section>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
