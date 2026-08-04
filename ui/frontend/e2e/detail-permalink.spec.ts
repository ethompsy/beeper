import { test, expect, type Page } from '@playwright/test'

/**
 * detail-permalink.spec.ts
 *
 * Task 3.2 AC [T]:
 *   1. A detail URL with `#step-<id>` cold-loads anchored to that step (the
 *      step is scrolled into view).
 *   2. Cold load of a detail URL auto-collapses the sidebar (FR44) and
 *      focuses the summary header (`#detail-summary-heading`) — proven here
 *      specifically for a COLD load (real browser navigation, not a
 *      client-side route transition), and specifically *together with* the
 *      step-anchor scroll, to prove neither behavior silently cancels the
 *      other (see `useStepAnchorScroll`'s doc comment for why they don't
 *      compete: the anchor hook only scrolls, never calls `.focus()`, and
 *      the header's own focus call uses `{ preventScroll: true }`).
 *
 * Runs against the *built* app (`vite preview`, matching the existing e2e
 * convention) — no Flask backend, so the one-shot detail fetch is mocked via
 * `page.route`. The pattern is scoped to the bare
 * `/api/v1/investigations/<id>` path (no trailing segment) so it does NOT
 * intercept the separate `/api/v1/investigations/<id>/events` SSE endpoint
 * (Task 2.6a) — that stream is left alone to fail/degrade on its own
 * against the backend-less preview server, exactly as the existing
 * `sidebar-behavior.spec.ts` / `focus-management.spec.ts` cold-load tests
 * already do; it has no bearing on this task's assertions.
 */

interface MockStep {
  order: number
  key: string | null
  label: string | null
  state: 'completed' | 'active' | 'pending' | 'error'
  type: 'metric' | 'log' | 'deploy' | 'kb' | 'correlation' | 'summary'
}

function makeSteps(count: number): MockStep[] {
  return Array.from({ length: count }, (_, i) => ({
    order: i + 1,
    key: `step-key-${i + 1}`,
    // Padded so each step has enough height that `count` steps overflow a
    // constrained viewport — the point is to force real scrolling.
    label: `Step ${i + 1} of ${count} — investigating checkout-service latency and error rate`,
    state: 'completed',
    type: 'log',
  }))
}

async function mockDetailApi(page: Page, investigationId: string, steps: MockStep[]): Promise<void> {
  // No trailing `/**` — matches only `.../investigations/<investigationId>`,
  // not `.../investigations/<investigationId>/events`.
  await page.route(`**/api/v1/investigations/${investigationId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: investigationId,
        status: 'investigating',
        service: 'checkout-service',
        message: null,
        metadata: {
          id: investigationId,
          status: 'investigating',
          service: 'checkout-service',
          severity: 'High',
          condition: 'HTTP 5xx error rate elevated (12%)',
          message: null,
          started_at: '2m ago',
          triggered_at: null,
          completed_at: null,
          workflow_state: 'investigating',
          workflow_state_changed_at: null,
          signal_count: 3,
          job_name: 'job-1',
        },
        steps,
      }),
    })
  })
}

test.describe('detail permalink — step anchor (Task 3.2, FR53)', () => {
  test('cold-loading a detail URL with #step-<order> scrolls that step into view', async ({ page }) => {
    await mockDetailApi(page, 'INV-0042', makeSteps(20))
    await page.setViewportSize({ width: 1024, height: 600 })

    // Direct navigation with the anchor already in the URL — a fresh page
    // load, not client-side navigation into an already-hydrated app.
    await page.goto('/app/investigations/INV-0042#step-15')

    const target = page.locator('#step-15')
    await expect(target).toBeVisible()
    await expect(target).toBeInViewport()

    // Sanity check that a real scroll actually happened — the first step
    // (far above the 15th in a 20-step list) is no longer in view.
    await expect(page.locator('#step-1')).not.toBeInViewport()
  })

  test('cold-loading a different step anchor on the same investigation scrolls to that one instead', async ({
    page,
  }) => {
    await mockDetailApi(page, 'INV-0042', makeSteps(20))
    await page.setViewportSize({ width: 1024, height: 600 })

    await page.goto('/app/investigations/INV-0042#step-5')

    await expect(page.locator('#step-5')).toBeInViewport()
  })

  test('a stale/invalid step anchor is a silent no-op — the page still loads normally', async ({ page }) => {
    await mockDetailApi(page, 'INV-0042', makeSteps(4))

    await page.goto('/app/investigations/INV-0042#step-999')

    await expect(page.getByRole('heading', { name: 'checkout-service' })).toBeVisible()
    // No error/alert surfaced just because the anchor didn't resolve.
    await expect(page.getByRole('alert')).toHaveCount(0)
  })
})

test.describe('detail permalink — cold-load sidebar collapse + header focus (FR44, WCAG 2.4.3)', () => {
  test('a cold detail permalink load (with a step anchor) collapses the sidebar, focuses the header, AND scrolls to the anchored step — none cancels the others', async ({
    page,
  }) => {
    await mockDetailApi(page, 'INV-0042', makeSteps(20))
    // Wide viewport: at >=1200px the sidebar's viewport-driven `auto` default
    // is EXPANDED — so a collapsed rail here can only be the FR44 detail-route
    // override, not an incidental narrow-viewport default.
    await page.setViewportSize({ width: 1440, height: 900 })

    await page.goto('/app/investigations/INV-0042#step-15')

    // FR44 — auto-collapse.
    const sidebar = page.getByRole('navigation', { name: 'Main navigation' })
    await expect(sidebar).toHaveClass(/w-16/)
    await expect(sidebar).not.toHaveClass(/w-64/)

    // WCAG 2.4.3 — the summary header owns focus on cold load.
    const heading = page.getByRole('heading', { name: 'checkout-service' })
    await expect(heading).toBeVisible()
    await expect(heading).toBeFocused()

    // FR53 — the anchored step is scrolled into view, same load.
    await expect(page.locator('#step-15')).toBeInViewport()
  })

  test('a cold detail permalink load with no step anchor still collapses the sidebar and focuses the header', async ({
    page,
  }) => {
    await mockDetailApi(page, 'INV-0042', makeSteps(4))
    await page.setViewportSize({ width: 1440, height: 900 })

    await page.goto('/app/investigations/INV-0042')

    const sidebar = page.getByRole('navigation', { name: 'Main navigation' })
    await expect(sidebar).toHaveClass(/w-16/)

    const heading = page.getByRole('heading', { name: 'checkout-service' })
    await expect(heading).toBeFocused()
  })
})
