import { test, expect } from '@playwright/test'

/**
 * sources-spending.spec.ts
 *
 * Task 5.3 AC [T] real-browser coverage — complements the Vitest/RTL
 * coverage in `src/test/SourcesPage.test.tsx` / `src/test/SpendingPage.test.tsx`
 * with a real network layer (`page.route` intercepting the JSON APIs)
 * against the *built* app, matching `investigation-list.spec.ts`'s
 * established e2e convention (Task 1.7/2.1/2.2).
 *
 * Runs against `vite preview` (no Flask backend) — every test mocks
 * `**\/api/v1/sources/**` / `**\/api/v1/spending/**` via `page.route`.
 */

async function mockSourcesApi(page: import('@playwright/test').Page, data: unknown) {
  await page.route('**/api/v1/sources/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
  })
}

async function mockSpendingApi(page: import('@playwright/test').Page, data: unknown) {
  await page.route('**/api/v1/spending/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
  })
}

const SAMPLE_SPENDING_RESPONSE = {
  summary: {
    daily_cost_usd: 12.34,
    monthly_cost_usd: 150.0,
    daily_cap_usd: 50.0,
    monthly_cap_usd: 500.0,
    daily_pct: 24.7,
    monthly_pct: 30.0,
    projected_monthly_usd: 200.0,
    daily_investigation_count: 15,
    monthly_investigation_count: 200,
    rate_per_hour: 5,
    rate_limit: 100,
  },
  cap_status: { enforcement_active: false, caps_configured: true, warnings: [] },
  provider_config: {
    provider: 'anthropic',
    model: 'claude-sonnet-4',
    endpoint: null,
    api_key_masked: '••••••1234',
    api_key_configured: true,
    configured: true,
    daily_cap_usd: 50.0,
    monthly_cap_usd: 500.0,
    rate_limit: 100,
  },
  trend: [{ period: '2026-05-29', cost_usd: 12.34, count: 15 }],
}

test.describe('Sources view — real browser (FR34)', () => {
  test('renders Prometheus/Loki connection status indicators', async ({ page }) => {
    await mockSourcesApi(page, [
      {
        name: 'prometheus-main',
        type: 'prometheus',
        endpoint: 'http://prometheus:9090',
        status: 'connected',
        last_check: '2026-05-29T12:00:00Z',
        error: null,
      },
      {
        name: 'loki-prod',
        type: 'loki',
        endpoint: 'http://loki:3100',
        status: 'error',
        last_check: '2026-05-29T11:00:00Z',
        error: { type: 'connection_error', message: 'Connection refused', details: null },
      },
    ])
    await page.goto('/app/sources')

    await expect(page.getByRole('heading', { name: 'Data Sources' })).toBeVisible()
    await expect(page.getByText('prometheus-main')).toBeVisible()
    await expect(page.getByText('loki-prod')).toBeVisible()

    const connectedBadge = page.locator('[data-slot="status-badge"][data-variant="connected"]')
    await expect(connectedBadge).toContainText('Connected')

    const disconnectedBadge = page.locator('[data-slot="status-badge"][data-variant="disconnected"]')
    await expect(disconnectedBadge).toContainText('Disconnected')
    await expect(page.getByText('Connection refused')).toBeVisible()
  })

  test('renders an explanatory empty state when no sources are configured, never blank', async ({ page }) => {
    await mockSourcesApi(page, [])
    await page.goto('/app/sources')

    await expect(page.getByText('No data sources configured')).toBeVisible()
  })

  test('renders an explanatory error state when the sources API is unreachable, never blank', async ({ page }) => {
    await page.route('**/api/v1/sources/**', async (route) => {
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'operator_unavailable' }) })
    })
    await page.goto('/app/sources')

    await expect(page.getByText('Unable to fetch sources')).toBeVisible()
  })
})

test.describe('Spending view — real browser (FR35)', () => {
  test('renders LLM provider configuration with a masked API key and spending metrics', async ({ page }) => {
    await mockSpendingApi(page, SAMPLE_SPENDING_RESPONSE)
    await page.goto('/app/spending')

    await expect(page.getByRole('heading', { name: 'LLM Spending' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'LLM Provider Configuration' })).toBeVisible()
    await expect(page.getByText('anthropic')).toBeVisible()
    await expect(page.getByText('claude-sonnet-4')).toBeVisible()
    await expect(page.getByText('••••••1234')).toBeVisible()

    // The raw/unmasked key must never appear anywhere on the page.
    await expect(page.getByText(/sk-live|sk-secret/)).toHaveCount(0)

    // Scoped to the Daily Spend card: the trend chart's y-axis grid line also
    // renders "$12.34" (the max cost), so an unscoped page-wide query would
    // be ambiguous (strict-mode violation).
    const dailySpendCard = page.getByRole('heading', { name: 'Daily Spend', exact: true }).locator('..')
    await expect(dailySpendCard.getByText('$12.34')).toBeVisible()
  })

  test('renders setup guidance when no LLM provider is configured', async ({ page }) => {
    await mockSpendingApi(page, {
      ...SAMPLE_SPENDING_RESPONSE,
      provider_config: {
        provider: null,
        model: null,
        endpoint: null,
        api_key_masked: null,
        api_key_configured: false,
        configured: false,
        daily_cap_usd: null,
        monthly_cap_usd: null,
        rate_limit: null,
      },
    })
    await page.goto('/app/spending')

    await expect(page.getByText(/No LLM provider configured/)).toBeVisible()
  })

  test('renders an explanatory error state when the spending API is unreachable, never blank', async ({ page }) => {
    await page.route('**/api/v1/spending/**', async (route) => {
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'spending_data_unavailable' }) })
    })
    await page.goto('/app/spending')

    await expect(page.getByRole('alert')).toBeVisible()
  })
})
