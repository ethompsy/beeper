import type { IngestionStats } from '../../api/ingestion-stats'
import type { StatusBadgeVariant } from '../components/StatusBadge'
import type { MetricTileStatus } from '../components/MetricTile'

/**
 * pipeline-view.ts — pure view-model derivation for the Ingestion Stats
 * dashboard (Task 5.2, FR32/FR33).
 *
 * Mirrors `_pipeline_view()` in `ui/beeper_ui/routes/health.py` field for
 * field and branch for branch — that function is the Jinja parity target's
 * source of truth for the three-state precedence, so this module is a
 * deliberate line-by-line port, not a reinterpretation:
 *
 *   • no_data  — metrics_received == 0 AND logs_received == 0 (red chip)
 *   • warming  — ewma_warmup_samples < ewma_warmup_minimum   (amber chip + bar)
 *   • active   — samples >= minimum                          (green chip)
 *
 * warmupPct = samples / minimum * 100 (clamped 0-100; 0 when minimum <= 0).
 *
 * Router-agnostic and rendering-agnostic by design (same discipline as
 * `src/lib/investigations/status-group.ts`/`row-view-model.ts`) — the page
 * component is the only thing that knows about fetching/polling; this module
 * is pure data-in/data-out so the precedence logic is unit-testable without
 * mounting any component.
 */

export type PipelineState = 'no_data' | 'warming' | 'active'

export interface PipelineView {
  pipelineState: PipelineState
  /** Raw clamped 0-100 float. Display rounding (floor to whole percent) is `EwmaProgressBar`'s job. */
  warmupPct: number
  isWarming: boolean
}

const NO_DATA_VIEW: PipelineView = { pipelineState: 'no_data', warmupPct: 0, isWarming: false }

/** @param stats `null` while loading/on error — resolves to the same `no_data` view Jinja renders for a missing/failed fetch. */
export function derivePipelineView(stats: IngestionStats | null): PipelineView {
  if (!stats) return NO_DATA_VIEW

  const metricsReceived = stats.metrics_received || 0
  const logsReceived = stats.logs_received || 0
  const samples = stats.ewma_warmup_samples || 0
  const minimum = stats.ewma_warmup_minimum || 0

  let warmupPct = minimum > 0 ? (samples / minimum) * 100 : 0
  warmupPct = Math.max(0, Math.min(100, warmupPct))

  let pipelineState: PipelineState
  if (metricsReceived === 0 && logsReceived === 0) {
    pipelineState = 'no_data'
  } else if (samples < minimum) {
    pipelineState = 'warming'
  } else {
    pipelineState = 'active'
  }

  return { pipelineState, warmupPct, isWarming: pipelineState === 'warming' }
}

/** The tri-state chip's variant + label per state — reuses `StatusBadge`'s
 * doc-blessed "Pipeline / diagnostic health" variants (see StatusBadge.tsx's
 * variant-taxonomy comment) rather than a bespoke chip component; `healthy`'s
 * default "Healthy" label is overridden to the glossary-pinned "Active" copy
 * this dashboard uses (`health/_ingestion_content.html`'s `pipeline_state_chip`
 * macro), the other two states' default StatusBadge labels already match. */
export interface PipelineChipProps {
  variant: StatusBadgeVariant
  label: string
}

const PIPELINE_CHIP: Record<PipelineState, PipelineChipProps> = {
  no_data: { variant: 'no-data', label: 'No Data' },
  warming: { variant: 'warming-up', label: 'Warming Up' },
  active: { variant: 'healthy', label: 'Active' },
}

export function pipelineChipProps(state: PipelineState): PipelineChipProps {
  return PIPELINE_CHIP[state]
}

/** Ingestion tiles (Metrics/Logs Received): critical while no_data, healthy otherwise (`_ingestion_content.html`). */
export function ingestionTileStatus(pipelineState: PipelineState): MetricTileStatus {
  return pipelineState === 'no_data' ? 'critical' : 'healthy'
}

/** Anomalies Detected tile: warning when any anomalies fired this window, muted otherwise. */
export function anomaliesDetectedStatus(count: number): MetricTileStatus {
  return count > 0 ? 'warning' : 'muted'
}

/** Active Metric Detectors tile: healthy once at least one detector is running, muted otherwise. */
export function activeDetectorsStatus(count: number): MetricTileStatus {
  return count > 0 ? 'healthy' : 'muted'
}
