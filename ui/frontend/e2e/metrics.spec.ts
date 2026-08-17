import { test, expect, type Page } from '@playwright/test'

/**
 * metrics.spec.ts
 *
 * Task 5.4 AC [T] real-browser coverage — complements the Vitest/RTL
 * coverage in `src/routes/test/MetricsPage.test.tsx` with the parts that
 * genuinely need a real browser/URL: a real cold `page.goto` reproducing a
 * filtered permalink URL end-to-end, and a real click-driven drilldown
 * round trip against two distinct mocked endpoints.
 *
 * Runs against the *built* app (`vite preview`, matching the established
 * e2e convention — Task 1.7/2.1) — no Flask backend, so both JSON MTTR
 * endpoints (`GET /api/v1/metrics/mttr`, `GET /api/v1/metrics/mttr/drilldown`)
 * are mocked via `page.route`.
 */

interface MockTrendPoint {
  period: string
  avg_mttr_seconds: number
  count: number
  start: string
  end: string
}

interface MockDashboard {
  period: string
  service: string | null
  severity: string | null
  services: string[]
  severities: string[]
  trend: MockTrendPoint[]
  overall_avg_mttr_seconds: number
  total_count: number
  improvement_pct: number | null
  improving: boolean | null
  by_service: Array<{ service: string; avg_mttr_seconds: number; count: number }>
  by_severity: Array<{ severity: string; avg_mttr_seconds: number; count: number }>
}

function makeDashboard(overrides: Partial<MockDashboard> = {}): MockDashboard {
  return {
    period: 'month',
    service: null,
    severity: null,
    services: ['checkout-service', 'api-gateway'],
    severities: ['high', 'critical'],
    trend: [
      { period: '2026-01', avg_mttr_seconds: 3600, count: 4, start: '2026-01-01', end: '2026-01-31' },
      { period: '2026-02', avg_mttr_seconds: 1800, count: 6, start: '2026-02-01', end: '2026-02-28' },
    ],
    overall_avg_mttr_seconds: 2700,
    total_count: 10,
    improvement_pct: 50,
    improving: true,
    by_service: [{ service: 'checkout-service', avg_mttr_seconds: 2700, count: 10 }],
    by_severity: [{ severity: 'high', avg_mttr_seconds: 2700, count: 10 }],
    ...overrides,
  }
}

async function mockMttrApi(page: Page, dashboard: MockDashboard): Promise<void> {
  // Trailing `**` is required: `MetricsPage` always includes `?period=...`
  // (the period filter defaults to "month", never an empty string), so a
  // bare `.../mttr` pattern with no trailing wildcard never matches.
  await page.route('**/api/v1/metrics/mttr**', async (route) => {
    // Exclude the drilldown endpoint — its URL also contains "/mttr" as a
    // prefix (`/mttr/drilldown`), so without this guard this broader glob
    // would shadow `mockDrilldownApi`'s own route registration.
    if (route.request().url().includes('/mttr/drilldown')) {
      await route.fallback()
      return
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(dashboard) })
  })
}

async function mockDrilldownApi(
  page: Page,
  payload: { period_label: string | null; investigations: unknown[] },
): Promise<void> {
  await page.route('**/api/v1/metrics/mttr/drilldown**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) })
  })
}

test.describe('metrics dashboard — real browser (Task 5.4 parity)', () => {
  test('renders the MTTR Trends Dashboard with summary cards, chart, and comparison bars', async ({ page }) => {
    await mockMttrApi(page, makeDashboard())
    await page.goto('/app/metrics')

    await expect(page.getByRole('heading', { name: 'MTTR Trends Dashboard' })).toBeVisible()
    await expect(page.getByText('Overall MTTR')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'MTTR Trend', exact: true })).toBeVisible()
    await expect(page.getByText('MTTR by Service')).toBeVisible()
    await expect(page.getByText('MTTR by Severity')).toBeVisible()
  })

  test('cold-loading a filtered permalink URL reproduces the filtered request and select values', async ({
    page,
  }) => {
    let capturedQuery: URLSearchParams | null = null
    await page.route('**/api/v1/metrics/mttr?**', async (route) => {
      capturedQuery = new URL(route.request().url()).searchParams
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeDashboard({ period: 'week', service: 'api-gateway', severity: 'critical' })),
      })
    })

    // Genuine cold load — no prior in-app navigation establishing state.
    await page.goto('/app/metrics?period=week&service=api-gateway&severity=critical')

    await expect(page.getByRole('heading', { name: 'MTTR Trends Dashboard' })).toBeVisible()
    expect(capturedQuery?.get('period')).toBe('week')
    expect(capturedQuery?.get('service')).toBe('api-gateway')
    expect(capturedQuery?.get('severity')).toBe('critical')

    await expect(page.getByLabel('Period')).toHaveValue('week')
    await expect(page.getByLabel('Service')).toHaveValue('api-gateway')
    await expect(page.getByLabel('Severity')).toHaveValue('critical')
  })

  test('selecting a filter updates the address bar to a shareable permalink', async ({ page }) => {
    await mockMttrApi(page, makeDashboard())
    await page.goto('/app/metrics')
    await expect(page.getByRole('heading', { name: 'MTTR Trends Dashboard' })).toBeVisible()

    await page.getByLabel('Period').selectOption('quarter')
    await expect(page).toHaveURL(/[?&]period=quarter/)
  })

  test('clicking a trend chart data point opens the drilldown investigation list', async ({ page }) => {
    await mockMttrApi(page, makeDashboard())
    await mockDrilldownApi(page, {
      period_label: '2026-01-01 to 2026-01-31',
      investigations: [
        {
          investigation_id: 'inv-e2e-001',
          service: 'checkout-service',
          severity: 'high',
          mttr_seconds: 3600,
          resolved_at: '2026-01-20T10:00:00Z',
          resolution_outcome: 'resolved',
        },
      ],
    })
    await page.goto('/app/metrics')
    await expect(page.getByRole('heading', { name: 'MTTR Trend', exact: true })).toBeVisible()

    await page.getByRole('button', { name: /2026-01/ }).click()

    await expect(page.getByTestId('drilldown-panel')).toBeVisible()
    await expect(page.getByText('Investigations: 2026-01-01 to 2026-01-31')).toBeVisible()
    await expect(page.getByRole('link', { name: 'inv-e2e-001' })).toBeVisible()
  })

  test('the export links point at the existing /metrics/export endpoint with the current period', async ({
    page,
  }) => {
    await mockMttrApi(page, makeDashboard({ period: 'week' }))
    await page.goto('/app/metrics?period=week')
    await expect(page.getByRole('heading', { name: 'MTTR Trends Dashboard' })).toBeVisible()

    await expect(page.getByRole('link', { name: 'Export CSV' })).toHaveAttribute(
      'href',
      '/metrics/export?period=week&format=csv',
    )
    await expect(page.getByRole('link', { name: 'Export JSON' })).toHaveAttribute(
      'href',
      '/metrics/export?period=week&format=json',
    )
  })

  test('renders an explanatory empty state, never blank, when there is no MTTR data', async ({ page }) => {
    await mockMttrApi(
      page,
      makeDashboard({
        trend: [],
        total_count: 0,
        overall_avg_mttr_seconds: 0,
        improvement_pct: null,
        improving: null,
        by_service: [],
        by_severity: [],
      }),
    )
    await page.goto('/app/metrics')

    await expect(
      page.getByText('No resolved investigations with MTTR data found. MTTR data is recorded when investigations are resolved.'),
    ).toBeVisible()
  })
})
