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
