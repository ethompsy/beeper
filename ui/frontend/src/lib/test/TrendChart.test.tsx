/**
 * TrendChart.test.tsx
 *
 * Task 5.4 — direct unit coverage for the SVG line-chart primitive (chart
 * math + click/keyboard drilldown affordance), complementing the
 * page-level coverage in `src/routes/test/MetricsPage.test.tsx`.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TrendChart, type TrendChartPoint } from '../components/TrendChart'

const POINTS: TrendChartPoint[] = [
  { id: 'p1', label: '2026-01', value: 3600, displayValue: '1h' },
  { id: 'p2', label: '2026-02', value: 1800, displayValue: '30m' },
  { id: 'p3', label: '2026-03', value: 7200, displayValue: '2h' },
]

describe('TrendChart — empty state', () => {
  it('renders an explanatory message instead of a blank chart when there are no points', () => {
    render(<TrendChart points={[]} ariaLabel="MTTR trend" />)
    expect(screen.getByText('No trend data to display.')).toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })
})

describe('TrendChart — rendering', () => {
  it('renders the chart with an accessible name', () => {
    render(<TrendChart points={POINTS} ariaLabel="MTTR trend by month" />)
    expect(screen.getByRole('img', { name: 'MTTR trend by month' })).toBeInTheDocument()
  })

  it('renders one data point per input point, each with a label+value accessible title', () => {
    const { container } = render(<TrendChart points={POINTS} ariaLabel="MTTR trend" />)
    const circles = container.querySelectorAll('[data-slot="trend-chart-point"]')
    expect(circles).toHaveLength(3)
    expect(container.querySelector('title')?.textContent).toBe('2026-01: 1h')
  })

  it('renders X-axis tick labels for every point', () => {
    render(<TrendChart points={POINTS} ariaLabel="MTTR trend" />)
    expect(screen.getByText('2026-01')).toBeInTheDocument()
    expect(screen.getByText('2026-02')).toBeInTheDocument()
    expect(screen.getByText('2026-03')).toBeInTheDocument()
  })

  it('formats Y-axis grid tick values via the formatValue callback', () => {
    const formatValue = vi.fn((v: number) => `${Math.round(v)}s`)
    render(<TrendChart points={POINTS} ariaLabel="MTTR trend" formatValue={formatValue} />)
    // Max value is 7200 (top grid line) — its formatted label must appear verbatim.
    expect(screen.getByText('7200s')).toBeInTheDocument()
    expect(formatValue).toHaveBeenCalled()
  })

  it('renders a connecting polyline when there is more than one point', () => {
    const { container } = render(<TrendChart points={POINTS} ariaLabel="MTTR trend" />)
    expect(container.querySelector('polyline')).not.toBeNull()
  })

  it('does not render a polyline for a single point (nothing to connect)', () => {
    const { container } = render(<TrendChart points={[POINTS[0]]} ariaLabel="MTTR trend" />)
    expect(container.querySelector('polyline')).toBeNull()
  })
})

describe('TrendChart — non-interactive mode (no onSelectPoint)', () => {
  it('renders data points with no button role/tabIndex when onSelectPoint is omitted', () => {
    const { container } = render(<TrendChart points={POINTS} ariaLabel="MTTR trend" />)
    const circle = container.querySelector('[data-slot="trend-chart-point"]')
    expect(circle).not.toHaveAttribute('role')
    expect(circle).not.toHaveAttribute('tabindex')
  })
})

describe('TrendChart — click/keyboard drilldown (interactive mode)', () => {
  it('marks each data point as a focusable button with an accessible label', () => {
    render(<TrendChart points={POINTS} ariaLabel="MTTR trend" onSelectPoint={() => {}} />)
    expect(
      screen.getByRole('button', { name: '2026-02: 30m. View investigations.' }),
    ).toBeInTheDocument()
  })

  it('calls onSelectPoint with the clicked point on click', async () => {
    const user = userEvent.setup()
    const onSelectPoint = vi.fn()
    render(<TrendChart points={POINTS} ariaLabel="MTTR trend" onSelectPoint={onSelectPoint} />)

    await user.click(screen.getByRole('button', { name: /2026-03/ }))
    expect(onSelectPoint).toHaveBeenCalledWith(POINTS[2])
  })

  it('calls onSelectPoint on Enter and Space when a point is focused', async () => {
    const user = userEvent.setup()
    const onSelectPoint = vi.fn()
    render(<TrendChart points={POINTS} ariaLabel="MTTR trend" onSelectPoint={onSelectPoint} />)

    const point = screen.getByRole('button', { name: /2026-01/ })
    point.focus()
    await user.keyboard('{Enter}')
    expect(onSelectPoint).toHaveBeenCalledWith(POINTS[0])

    onSelectPoint.mockClear()
    await user.keyboard(' ')
    expect(onSelectPoint).toHaveBeenCalledWith(POINTS[0])
  })

  it('marks the selected point via data-state and aria-pressed', () => {
    render(
      <TrendChart
        points={POINTS}
        ariaLabel="MTTR trend"
        onSelectPoint={() => {}}
        selectedId="p2"
      />,
    )
    const selected = screen.getByRole('button', { name: /2026-02/ })
    expect(selected).toHaveAttribute('data-state', 'selected')
    expect(selected).toHaveAttribute('aria-pressed', 'true')

    const unselected = screen.getByRole('button', { name: /2026-01/ })
    expect(unselected).toHaveAttribute('data-state', 'unselected')
    expect(unselected).toHaveAttribute('aria-pressed', 'false')
  })
})
