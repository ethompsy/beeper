import { test, expect } from '@playwright/test'

/**
 * focus-management.spec.ts
 *
 * Task 2.1 AC [T] — WCAG 2.4.3 focus management on route change, INCLUDING
 * a cold permalink load (navigating directly to a detail URL, not via
 * in-app client-side navigation). This is the half of the AC that an RTL
 * memory-router test cannot prove — it needs the router to actually
 * hydrate from the URL in a real browser (see
 * `src/lib/test/useRouteFocusManagement.test.tsx` for the in-app-nav half).
 */
test.describe('focus management (WCAG 2.4.3)', () => {
  test('cold-loading a detail permalink moves focus to the summary <h1>', async ({ page }) => {
    // Direct navigation — this is a fresh page load, not a client-side
    // route transition from a prior page in the same browsing session.
    await page.goto('/app/investigations/INV-0042')

    const heading = page.getByRole('heading', { name: 'INV-0042' })
    await expect(heading).toBeVisible()
    await expect(heading).toBeFocused()
  })

  test('cold-loading a different detail permalink also focuses its own <h1>', async ({ page }) => {
    await page.goto('/app/investigations/INV-9999')

    const heading = page.getByRole('heading', { name: 'INV-9999' })
    await expect(heading).toBeFocused()
  })

  test('navigating back to the list from detail returns focus to the active sidebar nav item', async ({
    page,
  }) => {
    await page.goto('/app/investigations/INV-0042')
    await expect(page.getByRole('heading', { name: 'INV-0042' })).toBeFocused()

    // Client-side back-navigation via the breadcrumb link (not a reload).
    await page.getByRole('link', { name: 'Investigations' }).click()

    await expect(page).toHaveURL(/\/app\/investigations$/)
    const activeNavItem = page.locator('[data-sidebar-nav-active="true"]')
    await expect(activeNavItem).toBeFocused()
  })
})

/**
 * Task 5.5 a11y-audit finding: this same WCAG 2.4.3 contract (cold-load ->
 * focus the detail `<h1>`; back-to-list -> focus the active sidebar item)
 * was only wired for the investigation detail route — `AppLayout.tsx`'s
 * `isDetailRoute` never covered `/knowledge/:entryId`, so
 * `useRouteFocusManagement` never ran for Knowledge Base entries at all. See
 * `AppLayout.tsx`'s `isFocusManagedDetailRoute` and
 * `KnowledgeEntryPage.tsx`'s always-rendered `<h1 id="detail-summary-heading">`
 * (both doc comments explain the fix and the fetch-timing race it closes).
 *
 * No `page.route` mock needed for the cold-load case — like
 * `InvestigationDetailPage`'s `SummaryHeader`, the heading falls back to the
 * raw entry id synchronously and doesn't wait on the (here, unmocked and
 * therefore failing) fetch to paint or receive focus.
 */
test.describe('focus management (WCAG 2.4.3) — Knowledge Base entry detail', () => {
  test('cold-loading a KB entry permalink moves focus to the entry heading', async ({ page }) => {
    await page.goto('/app/knowledge/kb-001')

    const heading = page.getByRole('heading', { name: 'kb-001' })
    await expect(heading).toBeVisible()
    await expect(heading).toBeFocused()
  })

  test('navigating back to the Knowledge Base list from an entry returns focus to the active sidebar nav item', async ({
    page,
  }) => {
    await page.route('**/api/v1/knowledge/**', async (route) => {
      const url = new URL(route.request().url())
      if (!url.pathname.endsWith('/api/v1/knowledge/') && !url.pathname.endsWith('/api/v1/knowledge')) {
        return route.fallback()
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ query: '', entries: [], has_exact_matches: true, error: null }),
      })
    })
    await page.goto('/app/knowledge/kb-001')
    await expect(page.getByRole('heading', { name: 'kb-001' })).toBeFocused()

    // Client-side back-navigation via the breadcrumb link (not a reload).
    // Scoped to the breadcrumb — unlike investigation detail, KB detail
    // deliberately does NOT force-collapse the sidebar (see
    // `AppLayout.tsx`'s `isFocusManagedDetailRoute` doc comment), so the
    // sidebar's own "Knowledge Base" nav link is also on-screen and would
    // otherwise make this locator ambiguous.
    await page.getByLabel('Breadcrumb').getByRole('link', { name: 'Knowledge Base' }).click()

    await expect(page).toHaveURL(/\/app\/knowledge$/)
    const activeNavItem = page.locator('[data-sidebar-nav-active="true"]')
    await expect(activeNavItem).toBeFocused()
  })
})
