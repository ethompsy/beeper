import { test, expect } from '@playwright/test'

/**
 * ingestion-stats.spec.ts
 *
 * Task 5.2 [T] real-browser coverage — complements the Vitest/RTL coverage
 * in `src/routes/test/IngestionStatsPage.test.tsx` with the parts that
 * genuinely need a real browser:
 *   - a real network layer (`page.route` intercepting the JSON API) rather
 *     than a `global.fetch` stub, proving the `vite preview`-served build
 *     actually wires the fetch call through correctly end-to-end;
 *   - a real `setInterval`/wall-clock auto-refresh cycle, proving the
 *     polling wiring survives an actual browser round-trip (not just a
 *     fake-timer simulation).
 *
 * Runs against the *built* app (`vite preview`, matching the existing e2e
 * convention in `investigation-list.spec.ts`) — no Flask backend, so every
 * test mocks `**\/api/v1/ingestion/stats**` via `page.route`.
 */

interface MockStats {
  buffer_size: number
  buffered_count: number
  dropped_count: number
  is_full: boolean
  metrics_received: number
  logs_received: number
  anomalies_detected: number
  anomalies_suppressed: number
  active_metric_detectors: number
  ewma_warmup_samples: number
  ewma_warmup_minimum: number
}

function makeStats(overrides: Partial<MockStats> = {}): MockStats {
  return {
    buffer_size: 10000,
    buffered_count: 42,
    dropped_count: 0,
    is_full: false,
    metrics_received: 12904,
    logs_received: 8321,
    anomalies_detected: 3,
    anomalies_suppressed: 1,
    active_metric_detectors: 7,
    ewma_warmup_samples: 100,
    ewma_warmup_minimum: 100,
    ...overrides,
  }
}

async function mockStatsApi(page: import('@playwright/test').Page, data: MockStats) {
  await page.route('**/api/v1/ingestion/stats', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
  })
}

test.describe('ingestion stats — real browser (FR32/FR33)', () => {
  test('renders ingestion + detection tiles with formatted values', async ({ page }) => {
    await mockStatsApi(page, makeStats({ metrics_received: 12904, logs_received: 8321, anomalies_detected: 3 }))
    await page.goto('/app/ingestion-stats')

    await expect(page.getByText('Metrics Received')).toBeVisible()
    await expect(page.getByText('12,904')).toBeVisible()
    await expect(page.getByText('Logs Received')).toBeVisible()
    await expect(page.getByText('8,321')).toBeVisible()
    await expect(page.getByText('Anomalies Detected')).toBeVisible()
    await expect(page.getByText('Active Metric Detectors')).toBeVisible()
  })

  test('renders the red "No Data" chip when no metrics or logs have been received', async ({ page }) => {
    await mockStatsApi(page, makeStats({ metrics_received: 0, logs_received: 0 }))
    await page.goto('/app/ingestion-stats')

    const chip = page.getByText('No Data', { exact: true })
    await expect(chip).toBeVisible()
    await expect(chip).toHaveAttribute('data-variant', 'no-data')
  })

  test('renders the amber "Warming Up" chip with a progress bar while samples < minimum', async ({ page }) => {
    await mockStatsApi(
      page,
      makeStats({ metrics_received: 100, logs_received: 50, ewma_warmup_samples: 45, ewma_warmup_minimum: 100 }),
    )
    await page.goto('/app/ingestion-stats')

    await expect(page.getByText('Warming Up', { exact: true })).toBeVisible()
    const bar = page.getByRole('progressbar', { name: 'EWMA warmup progress' })
    await expect(bar).toBeVisible()
    await expect(bar).toHaveAttribute('aria-valuenow', '45')
    await expect(page.getByText('45 / 100 samples', { exact: false })).toBeVisible()
  })

  test('renders the green "Active" chip and no progress bar once samples >= minimum', async ({ page }) => {
    await mockStatsApi(
      page,
      makeStats({ metrics_received: 100, logs_received: 50, ewma_warmup_samples: 100, ewma_warmup_minimum: 100 }),
    )
    await page.goto('/app/ingestion-stats')

    await expect(page.getByText('Active', { exact: true })).toBeVisible()
    await expect(page.getByRole('progressbar', { name: 'EWMA warmup progress' })).toHaveCount(0)
  })

  test('shows a distinct error state, never a blank frame, when the stats API fails', async ({ page }) => {
    await page.route('**/api/v1/ingestion/stats', async (route) => {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'operator_unavailable' }),
      })
    })
    await page.goto('/app/ingestion-stats')

    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page.getByText('Unable to fetch ingestion stats')).toBeVisible()
    await expect(page.getByText('Metrics Received')).toHaveCount(0)
  })

  test('auto-refreshes the displayed numbers over real wall-clock time, without any manual reload or navigation', async ({
    page,
  }) => {
    let call = 0
    await page.route('**/api/v1/ingestion/stats', async (route) => {
      call += 1
      const data = call === 1 ? makeStats({ metrics_received: 1000 }) : makeStats({ metrics_received: 2000 })
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
    })

    await page.goto('/app/ingestion-stats')
    await expect(page.getByText('1,000')).toBeVisible()

    // Real 5s auto-refresh interval — no page.reload(), no click, no
    // navigation. The default Playwright assertion timeout (5s) plus this
    // wait comfortably covers one interval tick without being flaky.
    await expect(page.getByText('2,000')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('1,000')).toHaveCount(0)
  })
})
