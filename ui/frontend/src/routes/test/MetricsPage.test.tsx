/**
 * MetricsPage.test.tsx
 *
 * Task 5.4 `[T]` AC coverage: "Metrics view renders the parity target
 * pinned in 5.0" — parity with `templates/metrics/mttr.html` +
 * `_mttr_content.html` + `_drilldown.html`
 * (docs/design/route-parity-targets.md §5). Covers:
 *   - cold-load skeleton, never a blank frame
 *   - the MTTR Trends Dashboard heading/description + 3 summary stat cards
 *   - the trend chart (one data point per trend bucket)
 *   - MTTR-by-service / MTTR-by-severity comparison bars
 *   - the "no MTTR data" empty state and the fetch-failure error state
 *   - period/service/severity filters are real `<select>`-driven queries,
 *     encoded as a URL permalink (FR53) and reproducible on cold load
 *   - clicking a trend chart data point opens the drilldown panel
 *     (investigation list for that time bucket); clicking again / Close
 *     closes it; changing a filter closes it too
 *   - the export affordance links directly to the existing Jinja
 *     `/metrics/export` endpoint with the current period
 *
 * Mocks `global.fetch` directly (matching `InvestigationListPage.test.tsx`'s
 * established convention — no fetch-mock library).
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import { MetricsPage } from '../MetricsPage'

type JsonBody = Record<string, unknown>

function makeDashboard(overrides: Partial<JsonBody> = {}): JsonBody {
  return {
    period: 'month',
    service: null,
    severity: null,
    services: ['api-gateway', 'payment-service'],
    severities: ['critical', 'high'],
    trend: [
      { period: '2026-01', avg_mttr_seconds: 3600, count: 5, start: '2026-01-01', end: '2026-01-31' },
      { period: '2026-02', avg_mttr_seconds: 1800, count: 3, start: '2026-02-01', end: '2026-02-28' },
    ],
    overall_avg_mttr_seconds: 3000,
    total_count: 8,
    improvement_pct: 50,
    improving: true,
    by_service: [
      { service: 'api-gateway', avg_mttr_seconds: 2100, count: 5 },
      { service: 'payment-service', avg_mttr_seconds: 4500, count: 3 },
    ],
    by_severity: [
      { severity: 'critical', avg_mttr_seconds: 5400, count: 2 },
      { severity: 'high', avg_mttr_seconds: 2800, count: 6 },
    ],
    ...overrides,
  }
}

const EMPTY_DASHBOARD: JsonBody = {
  period: 'month',
  service: null,
  severity: null,
  services: [],
  severities: [],
  trend: [],
  overall_avg_mttr_seconds: 0,
  total_count: 0,
  improvement_pct: null,
  improving: null,
  by_service: [],
  by_severity: [],
}

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body }
}

/** Routes `fetch` calls to a dashboard payload or a drilldown payload based on the URL. */
function mockFetchRouting(dashboard: JsonBody, drilldown?: JsonBody) {
  const fetchMock = vi.fn().mockImplementation(async (url: string) => {
    if (url.includes('/mttr/drilldown')) {
      return jsonResponse(drilldown ?? { period_label: null, investigations: [] })
    }
    if (url.includes('/api/v1/metrics/mttr')) {
      return jsonResponse(dashboard)
    }
    throw new Error(`unexpected fetch url in test: ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** A never-resolving fetch — simulates "the fetch hasn't come back yet." */
function pendingFetch() {
  return vi.fn().mockImplementation(() => new Promise(() => {}))
}

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-search">{location.search}</div>
}

function renderMetricsPage(initialEntries: string[] = ['/metrics']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <LocationProbe />
      <Routes>
        <Route path="/metrics" element={<MetricsPage />} />
        <Route path="/investigations/:id" element={<div>Investigation detail placeholder</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('MetricsPage — cold load skeleton', () => {
  it('shows a skeleton (not a blank frame) while the initial fetch is in flight', async () => {
    vi.stubGlobal('fetch', pendingFetch())
    renderMetricsPage()

    expect(screen.getByRole('status', { name: 'Loading metrics' })).toBeInTheDocument()
  })
})

describe('MetricsPage — parity with metrics/mttr.html: heading + summary cards', () => {
  it('renders the MTTR Trends Dashboard heading and description', async () => {
    mockFetchRouting(makeDashboard())
    renderMetricsPage()

    expect(await screen.findByRole('heading', { name: 'MTTR Trends Dashboard' })).toBeInTheDocument()
    expect(screen.getByText('Mean Time To Resolution trends and service breakdowns')).toBeInTheDocument()
  })

  it('renders the Overall MTTR, Trend, and Data Points summary cards', async () => {
    mockFetchRouting(makeDashboard())
    renderMetricsPage()

    await screen.findByRole('heading', { name: 'MTTR Trends Dashboard' })

    expect(screen.getByText('Overall MTTR')).toBeInTheDocument()
    expect(screen.getByText('50m')).toBeInTheDocument() // formatMttr(3000)
    expect(screen.getByText('8 investigations')).toBeInTheDocument()

    expect(screen.getByText('Trend')).toBeInTheDocument()
    expect(screen.getByText('▼ 50%')).toBeInTheDocument()
    expect(screen.getByText('Improving vs previous period')).toBeInTheDocument()

    expect(screen.getByText('Data Points')).toBeInTheDocument()
    expect(screen.getByText('time periods')).toBeInTheDocument()
  })

  it('renders a worsening trend with the up arrow and critical color cue', async () => {
    mockFetchRouting(makeDashboard({ improvement_pct: 12.5, improving: false }))
    renderMetricsPage()

    expect(await screen.findByText('▲ 12.5%')).toBeInTheDocument()
    expect(screen.getByText('Worsening vs previous period')).toBeInTheDocument()
  })

  it('renders "Not enough data for trend" when improvement_pct is null', async () => {
    mockFetchRouting(makeDashboard({ improvement_pct: null, improving: null }))
    renderMetricsPage()

    expect(await screen.findByText('Not enough data for trend')).toBeInTheDocument()
  })
})

describe('MetricsPage — parity with _mttr_content.html: trend chart + comparison bars', () => {
  it('renders one chart data point per trend bucket', async () => {
    mockFetchRouting(makeDashboard())
    const { container } = renderMetricsPage()

    await screen.findByRole('heading', { name: 'MTTR Trend' })
    expect(container.querySelectorAll('[data-slot="trend-chart-point"]')).toHaveLength(2)
  })

  it('renders MTTR by Service and MTTR by Severity comparison bars', async () => {
    mockFetchRouting(makeDashboard())
    renderMetricsPage()

    await screen.findByText('MTTR by Service')
    const byService = screen.getByTestId('comparison-bars-MTTR by Service')
    expect(within(byService).getByText('api-gateway')).toBeInTheDocument()
    expect(within(byService).getByText('payment-service')).toBeInTheDocument()

    const bySeverity = screen.getByTestId('comparison-bars-MTTR by Severity')
    expect(within(bySeverity).getByText('Critical')).toBeInTheDocument()
    expect(within(bySeverity).getByText('High')).toBeInTheDocument()
  })
})

describe('MetricsPage — empty state (no MTTR data), never blank', () => {
  it('renders the explanatory empty state when total_count is 0', async () => {
    mockFetchRouting(EMPTY_DASHBOARD)
    renderMetricsPage()

    expect(
      await screen.findByText(
        'No resolved investigations with MTTR data found. MTTR data is recorded when investigations are resolved.',
      ),
    ).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'MTTR Trend' })).not.toBeInTheDocument()
  })
})

describe('MetricsPage — error state', () => {
  it('renders an explanatory error, never blank, when the fetch fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({ error: 'metrics_unavailable' }) }),
    )
    renderMetricsPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load metrics data')
  })
})

describe('MetricsPage — period/service/severity filters are a URL permalink (FR53)', () => {
  it('selecting a period updates the URL and re-fetches with the new period', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetchRouting(makeDashboard())
    renderMetricsPage()

    await screen.findByRole('heading', { name: 'MTTR Trends Dashboard' })
    expect(screen.getByTestId('location-search').textContent).toBe('')

    await user.selectOptions(screen.getByLabelText('Period'), 'week')

    await waitFor(() => expect(screen.getByTestId('location-search')).toHaveTextContent('?period=week'))
    await waitFor(() => {
      const lastCall = fetchMock.mock.calls.at(-1)?.[0] as string
      expect(new URL(lastCall, 'http://localhost').searchParams.get('period')).toBe('week')
    })
  })

  it('selecting a service and severity updates the URL and re-fetches with both filters', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetchRouting(makeDashboard())
    renderMetricsPage()

    await screen.findByRole('heading', { name: 'MTTR Trends Dashboard' })

    await user.selectOptions(screen.getByLabelText('Service'), 'api-gateway')
    await user.selectOptions(screen.getByLabelText('Severity'), 'high')

    await waitFor(() =>
      expect(screen.getByTestId('location-search')).toHaveTextContent('service=api-gateway'),
    )
    expect(screen.getByTestId('location-search')).toHaveTextContent('severity=high')

    await waitFor(() => {
      const lastCall = fetchMock.mock.calls.at(-1)?.[0] as string
      const params = new URL(lastCall, 'http://localhost').searchParams
      expect(params.get('service')).toBe('api-gateway')
      expect(params.get('severity')).toBe('high')
    })
  })

  it('cold-loading a URL seeded with ?period=week&service=api-gateway&severity=high (no prior in-app state) reproduces the filtered fetch and select values', async () => {
    const fetchMock = mockFetchRouting(makeDashboard({ period: 'week', service: 'api-gateway', severity: 'high' }))
    renderMetricsPage(['/metrics?period=week&service=api-gateway&severity=high'])

    await screen.findByRole('heading', { name: 'MTTR Trends Dashboard' })

    await waitFor(() => {
      const firstCall = fetchMock.mock.calls[0]?.[0] as string
      const params = new URL(firstCall, 'http://localhost').searchParams
      expect(params.get('period')).toBe('week')
      expect(params.get('service')).toBe('api-gateway')
      expect(params.get('severity')).toBe('high')
    })

    expect(screen.getByLabelText('Period')).toHaveValue('week')
    expect(screen.getByLabelText('Service')).toHaveValue('api-gateway')
    expect(screen.getByLabelText('Severity')).toHaveValue('high')
  })

  it('an invalid ?period= value falls back to the default "month" instead of crashing', async () => {
    mockFetchRouting(makeDashboard())
    renderMetricsPage(['/metrics?period=bogus'])

    await screen.findByRole('heading', { name: 'MTTR Trends Dashboard' })
    expect(screen.getByLabelText('Period')).toHaveValue('month')
  })
})

describe('MetricsPage — drilldown (clicking a trend chart data point)', () => {
  it('opens the drilldown panel with the investigation list for the clicked time bucket', async () => {
    const user = userEvent.setup()
    mockFetchRouting(makeDashboard(), {
      period_label: '2026-01-01 to 2026-01-31',
      investigations: [
        {
          investigation_id: 'inv-abc123',
          service: 'api-gateway',
          severity: 'high',
          mttr_seconds: 3420,
          resolved_at: '2026-01-15T14:30:00Z',
          resolution_outcome: 'not_an_issue',
        },
      ],
    })
    renderMetricsPage()

    await screen.findByRole('heading', { name: 'MTTR Trend' })
    await user.click(screen.getByRole('button', { name: /2026-01/ }))

    const panel = await screen.findByTestId('drilldown-panel')
    expect(within(panel).getByText('Investigations: 2026-01-01 to 2026-01-31')).toBeInTheDocument()
    expect(within(panel).getByRole('link', { name: 'inv-abc123' })).toHaveAttribute(
      'href',
      '/investigations/inv-abc123',
    )
    expect(within(panel).getByText('api-gateway')).toBeInTheDocument()
    expect(within(panel).getByText('High')).toBeInTheDocument()
    expect(within(panel).getByText('57m')).toBeInTheDocument() // formatMttr(3420)
    expect(within(panel).getByText('Not An Issue')).toBeInTheDocument()
  })

  it('renders an explanatory message when the drilldown bucket has no investigations', async () => {
    const user = userEvent.setup()
    mockFetchRouting(makeDashboard(), { period_label: '2026-01-01 to 2026-01-31', investigations: [] })
    renderMetricsPage()

    await screen.findByRole('heading', { name: 'MTTR Trend' })
    await user.click(screen.getByRole('button', { name: /2026-01/ }))

    expect(await screen.findByText('No investigations found for this period.')).toBeInTheDocument()
  })

  it('clicking the same data point again closes the drilldown panel', async () => {
    const user = userEvent.setup()
    mockFetchRouting(makeDashboard(), { period_label: '2026-01-01 to 2026-01-31', investigations: [] })
    renderMetricsPage()

    await screen.findByRole('heading', { name: 'MTTR Trend' })
    const point = screen.getByRole('button', { name: /2026-01/ })

    await user.click(point)
    await screen.findByTestId('drilldown-panel')

    await user.click(point)
    await waitFor(() => expect(screen.queryByTestId('drilldown-panel')).not.toBeInTheDocument())
  })

  it('the Close button closes the drilldown panel', async () => {
    const user = userEvent.setup()
    mockFetchRouting(makeDashboard(), { period_label: '2026-01-01 to 2026-01-31', investigations: [] })
    renderMetricsPage()

    await screen.findByRole('heading', { name: 'MTTR Trend' })
    await user.click(screen.getByRole('button', { name: /2026-01/ }))
    const panel = await screen.findByTestId('drilldown-panel')

    await user.click(within(panel).getByRole('button', { name: 'Close' }))
    await waitFor(() => expect(screen.queryByTestId('drilldown-panel')).not.toBeInTheDocument())
  })

  it('changing a filter closes an open drilldown panel', async () => {
    const user = userEvent.setup()
    mockFetchRouting(makeDashboard(), { period_label: '2026-01-01 to 2026-01-31', investigations: [] })
    renderMetricsPage()

    await screen.findByRole('heading', { name: 'MTTR Trend' })
    await user.click(screen.getByRole('button', { name: /2026-01/ }))
    await screen.findByTestId('drilldown-panel')

    await user.selectOptions(screen.getByLabelText('Period'), 'quarter')
    await waitFor(() => expect(screen.queryByTestId('drilldown-panel')).not.toBeInTheDocument())
  })
})

describe('MetricsPage — export affordance (parity: "an equivalent export affordance exists")', () => {
  it('links Export JSON / Export CSV directly to the existing /metrics/export endpoint with the current period', async () => {
    mockFetchRouting(makeDashboard({ period: 'quarter' }))
    renderMetricsPage(['/metrics?period=quarter'])

    await screen.findByRole('heading', { name: 'MTTR Trends Dashboard' })

    expect(screen.getByRole('link', { name: 'Export JSON' })).toHaveAttribute(
      'href',
      '/metrics/export?period=quarter&format=json',
    )
    expect(screen.getByRole('link', { name: 'Export CSV' })).toHaveAttribute(
      'href',
      '/metrics/export?period=quarter&format=csv',
    )
  })
})
