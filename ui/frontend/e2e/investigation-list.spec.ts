import { test, expect } from '@playwright/test'

/**
 * investigation-list.spec.ts
 *
 * Task 2.2 AC [T] real-browser coverage — complements the Vitest/RTL
 * coverage in `src/test/InvestigationListPage.test.tsx` with the parts that
 * genuinely need a real browser:
 *   - real client-side navigation (clicking a row is a router `Link`, not a
 *     full page reload) combined with real scroll (`page.mouse.wheel` /
 *     `evaluate` scrollTop), proving scroll restoration survives an actual
 *     browser round-trip through the detail route and back (FR22).
 *   - a real network layer (`page.route` intercepting the JSON API) rather
 *     than a `global.fetch` stub, proving the `vite preview`-served build
 *     actually wires the fetch call through correctly end-to-end.
 *
 * Runs against the *built* app (`vite preview`, matching Task 1.7/2.1's e2e
 * convention) — no Flask backend, so every test mocks
 * `**\/api/v1/investigations/**` via `page.route`.
 */

interface MockInvestigation {
  id: string
  status: 'investigating' | 'awaiting_confirmation' | 'completed' | 'failed'
  service: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  condition: string
  started_at: string | null
  triggered_at: string | null
  completed_at: string | null
  workflow_state: 'detected' | 'investigating' | 'resolved' | 'verified' | 'failed' | null
  workflow_state_changed_at: string | null
}

function makeInvestigation(overrides: Partial<MockInvestigation>): MockInvestigation {
  return {
    id: 'inv-default',
    status: 'investigating',
    service: 'checkout-service',
    severity: 'medium',
    condition: 'elevated error rate',
    started_at: new Date().toISOString(),
    triggered_at: new Date().toISOString(),
    completed_at: null,
    workflow_state: 'investigating',
    workflow_state_changed_at: null,
    ...overrides,
  }
}

async function mockInvestigationsApi(page: import('@playwright/test').Page, data: MockInvestigation[]) {
  await page.route('**/api/v1/investigations/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
  })
}

test.describe('investigation list — real browser (FR22/FR45/FR46/NFR19)', () => {
  test('renders investigation rows with service/severity/age/status facts', async ({ page }) => {
    await mockInvestigationsApi(page, [
      makeInvestigation({ id: 'inv-1', service: 'checkout-service', severity: 'high' }),
    ])
    await page.goto('/app/investigations')

    const card = page.getByRole('link', { name: /checkout-service investigation/i })
    await expect(card).toBeVisible()
    await expect(card).toContainText('checkout-service')
    await expect(card).toContainText('High')
  })

  test('orders active + high-severity investigations first', async ({ page }) => {
    await mockInvestigationsApi(page, [
      makeInvestigation({ id: 'low', service: 'svc-low', severity: 'low', status: 'investigating' }),
      makeInvestigation({ id: 'critical', service: 'svc-critical', severity: 'critical', status: 'investigating' }),
      makeInvestigation({ id: 'completed', service: 'svc-completed', severity: 'critical', status: 'completed' }),
    ])
    await page.goto('/app/investigations')

    await expect(page.getByRole('link', { name: /svc-critical investigation/i })).toBeVisible()
    const cards = page.getByRole('link', { name: /investigation,/ })
    await expect(cards.first()).toContainText('svc-critical')
  })

  test('status-group filter switches between active/resolved/failed', async ({ page }) => {
    await mockInvestigationsApi(page, [
      makeInvestigation({ id: 'active-1', service: 'svc-active', status: 'investigating' }),
      makeInvestigation({ id: 'completed-1', service: 'svc-completed', status: 'completed' }),
      makeInvestigation({ id: 'failed-1', service: 'svc-failed', status: 'failed' }),
    ])
    await page.goto('/app/investigations')

    await expect(page.getByRole('link', { name: /svc-active investigation/i })).toBeVisible()

    await page.getByRole('tab', { name: /Resolved/ }).click()
    await expect(page.getByRole('link', { name: /svc-completed investigation/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /svc-active investigation/i })).toHaveCount(0)

    await page.getByRole('tab', { name: /Failed/ }).click()
    await expect(page.getByRole('link', { name: /svc-failed investigation/i })).toBeVisible()
  })

  test('empty active group shows the waiting state, never a blank frame', async ({ page }) => {
    await mockInvestigationsApi(page, [])
    await page.goto('/app/investigations')

    await expect(page.getByText('No active investigations')).toBeVisible()
  })

  test('Pending rows are visually distinct from Running rows', async ({ page }) => {
    await mockInvestigationsApi(page, [
      makeInvestigation({
        id: 'pending-1',
        service: 'svc-pending',
        status: 'investigating',
        workflow_state: 'detected',
      }),
      makeInvestigation({
        id: 'running-1',
        service: 'svc-running',
        status: 'investigating',
        workflow_state: 'investigating',
      }),
    ])
    await page.goto('/app/investigations')

    const pendingCard = page.getByRole('link', { name: /svc-pending investigation/i })
    const runningCard = page.getByRole('link', { name: /svc-running investigation/i })

    await expect(pendingCard.locator('[data-slot="status-badge"]')).toHaveAttribute('data-variant', 'pending')
    await expect(runningCard.locator('[data-slot="status-badge"]')).toHaveAttribute('data-variant', 'investigating')
  })

  test('restores list scroll position after navigating to detail and back', async ({ page }) => {
    const many = Array.from({ length: 40 }, (_, i) =>
      makeInvestigation({ id: `inv-${i}`, service: `svc-${i}`, status: 'investigating' }),
    )
    await mockInvestigationsApi(page, many)

    // Constrain the viewport so the page actually needs to scroll — the app
    // shell has no bounded inner pane (AppShell.tsx uses `min-h-screen` with
    // no overflow constraint), so scroll position lives at the
    // window/document level, not inside a nested container.
    await page.setViewportSize({ width: 1280, height: 500 })

    await page.goto('/app/investigations')
    await expect(page.getByRole('link', { name: /svc-0 investigation/i })).toBeVisible()

    await page.mouse.wheel(0, 600)

    // Playwright's `.click()` auto-scrolls its target into view before
    // clicking, which would change the scroll position out from under this
    // test if the target wasn't already fully visible. Settle on the
    // final pre-click scroll position by explicitly scrolling the target
    // into view first (a no-op if it's already visible), THEN read
    // `scrollY` — so the value we assert on afterward is exactly what the
    // click itself will leave in place, no matter which row is used.
    const targetCard = page.getByRole('link', { name: /svc-20 investigation/i })
    await targetCard.scrollIntoViewIfNeeded()
    const scrollYBeforeNav = await page.evaluate(() => window.scrollY)
    expect(scrollYBeforeNav).toBeGreaterThan(0)

    await targetCard.click()
    await expect(page).toHaveURL(/\/app\/investigations\/inv-20$/)

    // Back-navigation from a detail route: per FR44 the sidebar auto-collapses
    // to the group-level icon rail (Observe/Learn/Manage), so there is no
    // per-item "Investigations" link to click there. Use the browser Back
    // button — the canonical trigger the scroll-restoration feature targets.
    await page.goBack()
    await expect(page).toHaveURL(/\/app\/investigations$/)
    await expect(page.getByRole('link', { name: /svc-0 investigation/i })).toBeVisible()

    await expect(async () => {
      const scrollY = await page.evaluate(() => window.scrollY)
      expect(scrollY).toBe(scrollYBeforeNav)
    }).toPass()
  })
})
