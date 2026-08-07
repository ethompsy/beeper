/**
 * chart.test.ts
 *
 * Tests `computeSpendChartData` (`src/lib/spending/chart.ts`) — a direct
 * TypeScript port of `_compute_spend_chart_data()`
 * (`ui/beeper_ui/routes/spending.py`). Pins the same behavior the Python
 * function has, verified against hand-computed expected values so the
 * ported formula can't silently drift from the Jinja chart it replaces.
 */
import { describe, it, expect } from 'vitest'
import { computeSpendChartData } from '../spending/chart'

describe('computeSpendChartData', () => {
  it('returns an empty chart shape for an empty trend', () => {
    const chart = computeSpendChartData([])
    expect(chart).toEqual({
      chartWidth: 800,
      chartHeight: 300,
      dataPoints: [],
      trendPoints: '',
      yGridLines: [],
    })
  })

  it('places a single point at the horizontal center', () => {
    const chart = computeSpendChartData([{ period: '2026-05-29', cost_usd: 10, count: 1 }])
    expect(chart.dataPoints).toHaveLength(1)
    expect(chart.dataPoints[0].x).toBe(400) // chartWidth / 2
    expect(chart.dataPoints[0].period).toBe('2026-05-29')
    expect(chart.dataPoints[0].costUsd).toBe(10)
    expect(chart.dataPoints[0].count).toBe(1)
  })

  it('spreads multiple points evenly across the usable width (padding 60 each side)', () => {
    const chart = computeSpendChartData([
      { period: 'day-1', cost_usd: 0, count: 0 },
      { period: 'day-2', cost_usd: 5, count: 1 },
      { period: 'day-3', cost_usd: 10, count: 2 },
    ])
    // usableWidth = 800 - 2*60 = 680; 3 points at i/(n-1) = 0, 0.5, 1
    expect(chart.dataPoints[0].x).toBe(60)
    expect(chart.dataPoints[1].x).toBe(400) // 60 + 0.5*680
    expect(chart.dataPoints[2].x).toBe(740) // 60 + 680
  })

  it('places the max-cost point at the top (smallest y) and zero-cost at the bottom (largest y)', () => {
    const chart = computeSpendChartData([
      { period: 'day-1', cost_usd: 0, count: 0 },
      { period: 'day-2', cost_usd: 10, count: 1 },
    ])
    // usableHeight = 300 - 2*30 = 240
    expect(chart.dataPoints[0].y).toBe(270) // padding_y + (1 - 0/10)*240 = 30+240
    expect(chart.dataPoints[1].y).toBe(30) // padding_y + (1 - 10/10)*240 = 30+0
  })

  it('treats an all-zero trend as max_cost=1 (avoids divide-by-zero), matching the Python fallback', () => {
    const chart = computeSpendChartData([
      { period: 'day-1', cost_usd: 0, count: 0 },
      { period: 'day-2', cost_usd: 0, count: 0 },
    ])
    // With max_cost forced to 1, cost_usd=0 still yields y at the bottom (padding_y + usableHeight).
    expect(chart.dataPoints[0].y).toBe(270)
    expect(chart.dataPoints[1].y).toBe(270)
  })

  it('builds a space-joined "x,y x,y" polyline points string', () => {
    const chart = computeSpendChartData([
      { period: 'day-1', cost_usd: 0, count: 0 },
      { period: 'day-2', cost_usd: 10, count: 1 },
    ])
    expect(chart.trendPoints).toBe('60,270 740,30')
  })

  it('computes 5 evenly-spaced y-grid-lines from max_cost down to 0', () => {
    const chart = computeSpendChartData([{ period: 'day-1', cost_usd: 100, count: 1 }])
    expect(chart.yGridLines).toHaveLength(5)
    expect(chart.yGridLines[0]).toEqual({ y: 30, value: 100 })
    expect(chart.yGridLines[4]).toEqual({ y: 270, value: 0 })
    // Middle grid line: y = 30 + 0.5*240 = 150; value = 100 - 0.5*100 = 50
    expect(chart.yGridLines[2]).toEqual({ y: 150, value: 50 })
  })

  it('respects custom chartWidth/chartHeight', () => {
    const chart = computeSpendChartData([{ period: 'day-1', cost_usd: 5, count: 1 }], 400, 200)
    expect(chart.chartWidth).toBe(400)
    expect(chart.chartHeight).toBe(200)
    expect(chart.dataPoints[0].x).toBe(200) // custom width / 2
  })
})
