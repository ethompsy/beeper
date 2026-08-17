/**
 * chart.ts — pure SVG coordinate computation for the Spending dashboard's
 * "Daily Spend Trend" chart (Task 5.3, FR35).
 *
 * A direct TypeScript port of `_compute_spend_chart_data()`
 * (`ui/beeper_ui/routes/spending.py`) — same padding constants, same
 * point-placement formula, same rounding — so the React chart renders
 * pixel-equivalent to the Jinja SVG it replaces. Router-agnostic/UI-free by
 * design (mirrors `src/lib/investigations/row-view-model.ts`'s convention):
 * `SpendingPage.tsx` is the only thing that knows this is rendered as an
 * `<svg>`.
 */

export interface SpendTrendPointInput {
  period: string
  cost_usd: number
  count: number
}

export interface SpendChartDataPoint {
  x: number
  y: number
  period: string
  costUsd: number
  count: number
}

export interface SpendChartGridLine {
  y: number
  value: number
}

export interface SpendChartData {
  chartWidth: number
  chartHeight: number
  dataPoints: SpendChartDataPoint[]
  /** Pre-joined `"x,y x,y ..."` string, ready for an SVG `<polyline points>` attribute. */
  trendPoints: string
  yGridLines: SpendChartGridLine[]
}

const PADDING_X = 60
const PADDING_Y = 30
const GRID_LINE_COUNT = 5

function round1(value: number): number {
  return Math.round(value * 10) / 10
}

function round2(value: number): number {
  return Math.round(value * 100) / 100
}

/**
 * Compute chart coordinates from a spend trend series.
 *
 * @param trend Daily spend trend points (period label, cost, investigation count).
 * @param chartWidth SVG viewBox width. Defaults match the Jinja chart's `chart_width`.
 * @param chartHeight SVG viewBox height. Defaults match the Jinja chart's `chart_height`.
 */
export function computeSpendChartData(
  trend: SpendTrendPointInput[],
  chartWidth = 800,
  chartHeight = 300,
): SpendChartData {
  if (trend.length === 0) {
    return { chartWidth, chartHeight, dataPoints: [], trendPoints: '', yGridLines: [] }
  }

  const maxCostRaw = Math.max(...trend.map((point) => point.cost_usd))
  const maxCost = maxCostRaw === 0 ? 1 : maxCostRaw

  const usableWidth = chartWidth - 2 * PADDING_X
  const usableHeight = chartHeight - 2 * PADDING_Y

  const dataPoints: SpendChartDataPoint[] = trend.map((point, index) => {
    const x =
      trend.length > 1 ? PADDING_X + (index / (trend.length - 1)) * usableWidth : chartWidth / 2
    const y = PADDING_Y + (1 - point.cost_usd / maxCost) * usableHeight
    return {
      x: round1(x),
      y: round1(y),
      period: point.period,
      costUsd: point.cost_usd,
      count: point.count,
    }
  })

  const trendPoints = dataPoints.map((point) => `${point.x},${point.y}`).join(' ')

  const yGridLines: SpendChartGridLine[] = Array.from({ length: GRID_LINE_COUNT }, (_, i) => {
    const y = PADDING_Y + (i / (GRID_LINE_COUNT - 1)) * usableHeight
    const value = maxCost - (i / (GRID_LINE_COUNT - 1)) * maxCost
    return { y: round1(y), value: round2(value) }
  })

  return { chartWidth, chartHeight, dataPoints, trendPoints, yGridLines }
}
