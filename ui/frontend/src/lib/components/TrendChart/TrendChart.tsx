import type { KeyboardEvent } from 'react'
import { cn } from '../../utils/cn'

/**
 * TrendChart — a dependency-free inline-SVG line chart with clickable data
 * points (Task 5.4).
 *
 * Reproduces the Jinja MTTR dashboard's trend visualization
 * (`ui/beeper_ui/templates/metrics/_mttr_content.html`'s `<svg
 * class="mttr-trend-chart">`: polyline + Y-axis grid lines + clickable data
 * points that drill down into a time bucket) as a generic, reusable library
 * primitive rather than an MTTR-specific one-off — deliberately generic
 * over `points`/`formatValue` (mirrors `StatusGroupFilter`'s "generic over
 * id/label pairs, no app-domain import" convention) so nothing here imports
 * `src/lib/metrics/format-mttr.ts` or any other MTTR-specific module; the
 * caller (`MetricsPage`) supplies pre-formatted display/tick strings.
 *
 * No chart dependency is added — plain SVG + the same
 * `currentColor`-via-Tailwind-`text-*` technique already used by
 * `EmptyGroupState`'s icon, so every stroke/fill stays token-driven (FR51)
 * without arbitrary hex values.
 *
 * Layout math (padding, point positions, 5 Y-axis grid lines) mirrors
 * `_compute_chart_data()` in `ui/beeper_ui/routes/metrics.py` exactly — kept
 * client-side (not fetched from the JSON API) because it's pure rendering
 * geometry with no data dependency, and computing it client-side means the
 * JSON API (`GET /api/v1/metrics/mttr`) can stay a plain data contract with
 * no SVG-specific fields.
 */
export interface TrendChartPoint {
  /** Stable identity for the point (used for the selected-state comparison and React keys). */
  id: string
  /** X-axis tick label, e.g. "2026-01" or "2026-W03". */
  label: string
  /** Raw numeric value — points/grid lines are scaled relative to the max value across `points`. */
  value: number
  /** Pre-formatted display value for the point's accessible name/tooltip, e.g. "1h 5m". */
  displayValue: string
}

export interface TrendChartProps {
  points: TrendChartPoint[]
  /** Accessible name for the chart as a whole, e.g. "MTTR trend by month". */
  ariaLabel: string
  /** Formats a raw Y-axis grid-line value into a tick label. Defaults to a plain rounded integer. */
  formatValue?: (value: number) => string
  /** The currently-selected point's `id` (e.g. the one driving an open drilldown), if any. */
  selectedId?: string | null
  /** Called when a data point is activated (click, or Enter/Space when focused). Omit to render a non-interactive chart. */
  onSelectPoint?: (point: TrendChartPoint) => void
}

const CHART_WIDTH = 800
const CHART_HEIGHT = 300
const PADDING_X = 60
const PADDING_Y = 30
const GRID_LINE_COUNT = 5

interface PlottedPoint extends TrendChartPoint {
  x: number
  y: number
}

function plotPoints(points: TrendChartPoint[], maxValue: number): PlottedPoint[] {
  const usableWidth = CHART_WIDTH - 2 * PADDING_X
  const usableHeight = CHART_HEIGHT - 2 * PADDING_Y

  return points.map((point, index) => {
    const x =
      points.length > 1 ? PADDING_X + (index / (points.length - 1)) * usableWidth : CHART_WIDTH / 2
    const y = PADDING_Y + (1 - point.value / maxValue) * usableHeight
    return { ...point, x, y }
  })
}

function gridLines(maxValue: number): Array<{ y: number; value: number }> {
  const usableHeight = CHART_HEIGHT - 2 * PADDING_Y
  return Array.from({ length: GRID_LINE_COUNT }, (_, i) => {
    const fraction = i / (GRID_LINE_COUNT - 1)
    return {
      y: PADDING_Y + fraction * usableHeight,
      value: maxValue - fraction * maxValue,
    }
  })
}

const defaultFormatValue = (value: number) => String(Math.round(value))

export function TrendChart({
  points,
  ariaLabel,
  formatValue = defaultFormatValue,
  selectedId = null,
  onSelectPoint,
}: TrendChartProps) {
  if (points.length === 0) {
    return (
      <p data-slot="trend-chart-empty" className="text-sm text-text-secondary">
        No trend data to display.
      </p>
    )
  }

  const maxValue = Math.max(...points.map((p) => p.value)) || 1
  const plotted = plotPoints(points, maxValue)
  const polylinePoints = plotted.map((p) => `${p.x},${p.y}`).join(' ')

  /** Strips the internal `x`/`y` layout fields so callers only ever see the public `TrendChartPoint` shape. */
  function toPublicPoint({ id, label, value, displayValue }: PlottedPoint): TrendChartPoint {
    return { id, label, value, displayValue }
  }

  function handleKeyDown(event: KeyboardEvent<SVGCircleElement>, point: PlottedPoint) {
    if (!onSelectPoint) return
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onSelectPoint(toPublicPoint(point))
    }
  }

  return (
    <div data-slot="trend-chart" className="w-full">
      <svg
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={ariaLabel}
        className="h-auto w-full"
      >
        {/* Y-axis grid lines — quiet, informational only (not a data channel). */}
        <g className="text-surface-overlay">
          {gridLines(maxValue).map((line) => (
            <line
              key={line.y}
              x1={PADDING_X}
              y1={line.y}
              x2={CHART_WIDTH - PADDING_X}
              y2={line.y}
              stroke="currentColor"
              strokeWidth={1}
            />
          ))}
        </g>
        <g className="text-text-muted">
          {gridLines(maxValue).map((line) => (
            <text
              key={line.y}
              x={PADDING_X - 8}
              y={line.y + 4}
              textAnchor="end"
              fontSize={11}
              fill="currentColor"
            >
              {formatValue(line.value)}
            </text>
          ))}
        </g>

        {plotted.length > 1 ? (
          <polyline
            points={polylinePoints}
            fill="none"
            className="text-primary"
            stroke="currentColor"
            strokeWidth={2.5}
            strokeLinejoin="round"
          />
        ) : null}

        {/* Data points — the interactive layer (click/keyboard to drill down). */}
        <g className="text-primary">
          {plotted.map((point) => {
            const isSelected = point.id === selectedId
            return (
              <circle
                key={point.id}
                data-slot="trend-chart-point"
                data-state={isSelected ? 'selected' : 'unselected'}
                cx={point.x}
                cy={point.y}
                r={isSelected ? 7 : 5}
                fill="currentColor"
                className={cn(
                  onSelectPoint && 'cursor-pointer',
                  'transition-opacity motion-reduce:transition-none',
                  isSelected ? 'opacity-100' : 'opacity-85 hover:opacity-100',
                )}
                role={onSelectPoint ? 'button' : undefined}
                tabIndex={onSelectPoint ? 0 : undefined}
                aria-label={onSelectPoint ? `${point.label}: ${point.displayValue}. View investigations.` : undefined}
                aria-pressed={onSelectPoint ? isSelected : undefined}
                onClick={onSelectPoint ? () => onSelectPoint(toPublicPoint(point)) : undefined}
                onKeyDown={onSelectPoint ? (event) => handleKeyDown(event, point) : undefined}
              >
                <title>{`${point.label}: ${point.displayValue}`}</title>
              </circle>
            )
          })}
        </g>

        {/* X-axis tick labels. */}
        <g className="text-text-muted">
          {plotted.map((point) => (
            <text
              key={point.id}
              x={point.x}
              y={CHART_HEIGHT - 5}
              textAnchor="middle"
              fontSize={10}
              fill="currentColor"
            >
              {point.label}
            </text>
          ))}
        </g>
      </svg>
    </div>
  )
}
