import { test, expect, type Page } from '@playwright/test'

/**
 * permalink-chrome-boundary.spec.ts
 *
 * Task 3.3 AC (FR53/NFR24) — proves the content-vs-chrome boundary:
 *   - "content" state (the status-group filter, Task 3.1) is encoded in the
 *     URL, so it rides along with the URL to a brand-new browsing context.
 *   - "chrome" state (sidebar expand/collapse, Task 2.1's `useSidebarState`;
 *     scroll offset, Task 2.2's `useScrollRestoration`) is local to the
 *     tab/session and does NOT ride along, even though the URL is identical.
 *
 * This is deliberately a negative test locking in behavior that already
 * exists (`useSidebarState` keeps its manual override in plain component
 * state, never persisted; `useScrollRestoration` uses `sessionStorage`,
 * which is scoped to the browsing context that wrote it) — see those hooks'
 * doc comments. No source changes are expected; this file only exists to
 * prove the negative and catch a future regression (e.g. someone "fixing" a
 * bug by lifting sidebar/scroll state into the URL or a longer-lived store).
 *
 * ── Why `browser.newContext()`, not just a second `page.goto` ──
 *
 * A same-context reload (`page.goto` again on the *same* `page`) still
 * carries `sessionStorage` forward — that's the existing, legitimate FR22
 * scroll-restoration feature working as designed within one tab/session. It
 * would NOT distinguish "this rode along because it's in the URL" from
 * "this rode along because sessionStorage happens to survive this
 * particular reload." A brand-new `BrowserContext` has no cookies, no
 * `sessionStorage`, and no leftover JS heap from the first context — so
 * anything that reproduces there necessarily came from the URL itself (plus
 * the mocked API), which is exactly the property this task needs to lock in.
 *
 * Runs against the *built* app (`vite preview`), matching the existing e2e
 * convention (`investigation-list.spec.ts`, `detail-permalink.spec.ts`) — no
 * Flask backend, so every test mocks `**\/api/v1/investigations/**` via
 * `page.route`.
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

/** A resolved-group row (`completed`) plus enough active rows that the list overflows a constrained viewport. */
function makeMixedInvestigations(): MockInvestigation[] {
  const activeRows = Array.from({ length: 30 }, (_, i) =>
    makeInvestigation({ id: `active-${i}`, service: `svc-active-${i}`, status: 'investigating' }),
  )
  const resolvedRows = Array.from({ length: 30 }, (_, i) =>
    makeInvestigation({ id: `resolved-${i}`, service: `svc-resolved-${i}`, status: 'completed' }),
  )
  return [...activeRows, ...resolvedRows]
}

async function mockInvestigationsApi(page: Page, data: MockInvestigation[]) {
  await page.route('**/api/v1/investigations/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
  })
}

test.describe('chrome state stays local — sidebar + scroll do not ride along in the permalink (Task 3.3, FR53/NFR24)', () => {
  test('manually expanding the sidebar and scrolling at a narrow viewport does not survive a cold load of the same URL in a fresh context, but the status filter does', async ({
    page,
    browser,
  }) => {
    const data = makeMixedInvestigations()

    // Narrow viewport (<1200px `--breakpoint-lg`): the sidebar's viewport-driven
    // `auto` default is collapsed (icon rail) — see useSidebarState.ts.
    await page.setViewportSize({ width: 900, height: 700 })
    await mockInvestigationsApi(page, data)
    await page.goto('/app/investigations?status=resolved')

    await expect(page.getByRole('tab', { name: /Resolved/ })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByRole('link', { name: /svc-resolved-0 investigation/i })).toBeVisible()

    // Narrow-viewport default: collapsed.
    const sidebar = page.getByRole('navigation', { name: 'Main navigation' })
    await expect(sidebar).toHaveClass(/w-16/)

    // Manually expand (hamburger toggle) — FR41 overlay behavior below 1200px.
    await page.getByRole('button', { name: 'Toggle navigation sidebar' }).click()
    await expect(sidebar).toHaveClass(/w-64/)

    // Scroll the page down.
    await page.mouse.wheel(0, 600)
    await expect(async () => {
      const scrollY = await page.evaluate(() => window.scrollY)
      expect(scrollY).toBeGreaterThan(0)
    }).toPass()

    // ── Fresh browsing context: no cookies, no sessionStorage, no JS heap
    // carried over from the context above. Cold-load the IDENTICAL URL. ──
    const freshContext = await browser.newContext()
    try {
      const freshPage = await freshContext.newPage()
      await freshPage.setViewportSize({ width: 900, height: 700 })
      await mockInvestigationsApi(freshPage, data)
      await freshPage.goto('/app/investigations?status=resolved')

      // Content state (the status-group filter) DID ride along — it's
      // encoded in the URL query string itself (Task 3.1, FR53).
      await expect(freshPage.getByRole('tab', { name: /Resolved/ })).toHaveAttribute('aria-selected', 'true')
      await expect(freshPage.getByRole('link', { name: /svc-resolved-0 investigation/i })).toBeVisible()
      await expect(freshPage.getByRole('link', { name: /svc-active-0 investigation/i })).toHaveCount(0)

      // Chrome state did NOT ride along: the sidebar resets to the
      // viewport-driven default (collapsed, <1200px) rather than resuming
      // the manually-expanded state from the other context.
      const freshSidebar = freshPage.getByRole('navigation', { name: 'Main navigation' })
      await expect(freshSidebar).toHaveClass(/w-16/)
      await expect(freshSidebar).not.toHaveClass(/w-64/)

      // Nor did the scroll offset ride along — the fresh load starts at
      // the top, not at the previously-scrolled position.
      const freshScrollY = await freshPage.evaluate(() => window.scrollY)
      expect(freshScrollY).toBe(0)
    } finally {
      await freshContext.close()
    }
  })
})

test.describe('cold load hydrates purely from the URL + API (Task 3.3 AC)', () => {
  test('a cold page.goto with ?status=resolved, in a brand-new context with no prior app state, renders the resolved-filtered list from the URL alone', async ({
    browser,
  }) => {
    const data = makeMixedInvestigations()

    // A brand-new context/page: nothing has ever run in-app here before —
    // no prior client-side navigation, no prior sessionStorage write. The
    // very first thing this context does is a cold `page.goto` straight to
    // the permalink URL.
    const context = await browser.newContext()
    try {
      const page = await context.newPage()
      await mockInvestigationsApi(page, data)
      await page.goto('/app/investigations?status=resolved')

      await expect(page.getByRole('tab', { name: /Resolved/ })).toHaveAttribute('aria-selected', 'true')
      await expect(page.getByRole('link', { name: /svc-resolved-0 investigation/i })).toBeVisible()
      // The active group's rows are absent — this is the resolved group,
      // filtered purely from the `?status=resolved` URL param plus the
      // mocked API response, not from any in-app navigation state.
      await expect(page.getByRole('link', { name: /svc-active-0 investigation/i })).toHaveCount(0)
    } finally {
      await context.close()
    }
  })
})
