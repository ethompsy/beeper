/**
 * pipeline-view.test.ts
 *
 * Task 5.2 [T] coverage for the three-state pipeline precedence
 * (`docs/design/route-parity-targets.md` §3): red "No Data" →
 * amber "Warming Up" → green "Active", each visually distinct (proven here
 * at the data level — a different `variant` + `label` per state — and at
 * the render level in `IngestionStatsPage.test.tsx`).
 *
 * `derivePipelineView` is a line-by-line port of `_pipeline_view()`
 * (`ui/beeper_ui/routes/health.py`) — these tests mirror that function's own
 * doc-comment examples so a future edit to either side can be diffed
 * against the other.
 */
import { describe, it, expect } from 'vitest'
import {
  activeDetectorsStatus,
  anomaliesDetectedStatus,
  derivePipelineView,
  ingestionTileStatus,
  pipelineChipProps,
} from '../ingestion/pipeline-view'
import type { IngestionStats } from '../../api/ingestion-stats'

function makeStats(overrides: Partial<IngestionStats> = {}): IngestionStats {
  return {
    buffer_size: 10000,
    buffered_count: 0,
    dropped_count: 0,
    is_full: false,
    metrics_received: 0,
    logs_received: 0,
    anomalies_detected: 0,
    anomalies_suppressed: 0,
    active_metric_detectors: 0,
    ewma_warmup_samples: 0,
    ewma_warmup_minimum: 0,
    ...overrides,
  }
}

describe('derivePipelineView — three-state precedence', () => {
  it('resolves to no_data when stats is null (loading/error, matches Jinja\'s missing-fetch default)', () => {
    const view = derivePipelineView(null)
    expect(view).toEqual({ pipelineState: 'no_data', warmupPct: 0, isWarming: false })
  })

  it('resolves to no_data when both metrics_received and logs_received are zero — even with nonzero warmup fields', () => {
    // Precedence check: no_data wins even though samples < minimum would
    // otherwise say "warming" — no_data is checked FIRST, matching
    // `_pipeline_view()`'s `if metrics_received == 0 and logs_received == 0`
    // branch order exactly.
    const view = derivePipelineView(
      makeStats({ metrics_received: 0, logs_received: 0, ewma_warmup_samples: 5, ewma_warmup_minimum: 100 }),
    )
    expect(view.pipelineState).toBe('no_data')
    expect(view.isWarming).toBe(false)
  })

  it('resolves to no_data when only one of metrics/logs received is nonzero but not both required — both must be zero for no_data', () => {
    const view = derivePipelineView(makeStats({ metrics_received: 10, logs_received: 0 }))
    expect(view.pipelineState).not.toBe('no_data')
  })

  it('resolves to warming when data is flowing but samples < minimum', () => {
    const view = derivePipelineView(
      makeStats({ metrics_received: 100, logs_received: 50, ewma_warmup_samples: 45, ewma_warmup_minimum: 100 }),
    )
    expect(view.pipelineState).toBe('warming')
    expect(view.isWarming).toBe(true)
    expect(view.warmupPct).toBe(45)
  })

  it('resolves to active when samples >= minimum', () => {
    const view = derivePipelineView(
      makeStats({ metrics_received: 100, logs_received: 50, ewma_warmup_samples: 100, ewma_warmup_minimum: 100 }),
    )
    expect(view.pipelineState).toBe('active')
    expect(view.isWarming).toBe(false)
    expect(view.warmupPct).toBe(100)
  })

  it('resolves to active when samples exceed minimum', () => {
    const view = derivePipelineView(
      makeStats({ metrics_received: 100, logs_received: 50, ewma_warmup_samples: 150, ewma_warmup_minimum: 100 }),
    )
    expect(view.pipelineState).toBe('active')
  })

  it('clamps warmupPct to 100 even when samples exceed minimum', () => {
    const view = derivePipelineView(
      makeStats({ metrics_received: 100, logs_received: 50, ewma_warmup_samples: 300, ewma_warmup_minimum: 100 }),
    )
    expect(view.warmupPct).toBe(100)
  })

  it('warmupPct is 0 when ewma_warmup_minimum is 0 (avoids division by zero, matches Jinja\'s guard)', () => {
    const view = derivePipelineView(
      makeStats({ metrics_received: 10, logs_received: 10, ewma_warmup_samples: 0, ewma_warmup_minimum: 0 }),
    )
    expect(view.warmupPct).toBe(0)
    // samples (0) < minimum (0) is false, so this resolves to active, not warming.
    expect(view.pipelineState).toBe('active')
  })

  it('warmupPct never goes negative even with contrived negative-looking ratios', () => {
    const view = derivePipelineView(
      makeStats({ metrics_received: 10, logs_received: 10, ewma_warmup_samples: 0, ewma_warmup_minimum: 100 }),
    )
    expect(view.warmupPct).toBe(0)
    expect(view.warmupPct).toBeGreaterThanOrEqual(0)
  })
})

describe('pipelineChipProps — each state maps to a distinct variant + label', () => {
  it('no_data → StatusBadge "no-data" variant, label "No Data"', () => {
    expect(pipelineChipProps('no_data')).toEqual({ variant: 'no-data', label: 'No Data' })
  })

  it('warming → StatusBadge "warming-up" variant, label "Warming Up"', () => {
    expect(pipelineChipProps('warming')).toEqual({ variant: 'warming-up', label: 'Warming Up' })
  })

  it('active → StatusBadge "healthy" variant, label overridden to "Active"', () => {
    expect(pipelineChipProps('active')).toEqual({ variant: 'healthy', label: 'Active' })
  })

  it('all three states resolve to distinct variants (visually distinct, per the AC)', () => {
    const variants = new Set(
      (['no_data', 'warming', 'active'] as const).map((state) => pipelineChipProps(state).variant),
    )
    expect(variants.size).toBe(3)
  })
})

describe('tile status helpers — mirror the Jinja metric_tile status branches exactly', () => {
  it('ingestionTileStatus is critical when pipeline is no_data, healthy otherwise', () => {
    expect(ingestionTileStatus('no_data')).toBe('critical')
    expect(ingestionTileStatus('warming')).toBe('healthy')
    expect(ingestionTileStatus('active')).toBe('healthy')
  })

  it('anomaliesDetectedStatus is warning when count > 0, muted at 0', () => {
    expect(anomaliesDetectedStatus(0)).toBe('muted')
    expect(anomaliesDetectedStatus(1)).toBe('warning')
    expect(anomaliesDetectedStatus(50)).toBe('warning')
  })

  it('activeDetectorsStatus is healthy when count > 0, muted at 0', () => {
    expect(activeDetectorsStatus(0)).toBe('muted')
    expect(activeDetectorsStatus(3)).toBe('healthy')
  })
})
