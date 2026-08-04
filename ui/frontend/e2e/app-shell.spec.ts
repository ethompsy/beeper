import { test, expect } from '@playwright/test'

/**
 * app-shell.spec.ts
 *
 * Task 1.7 AC [T] — a sample Playwright e2e test runs green in CI against
 * the *built* app, proving the production bundle actually mounts in a real
 * browser. Updated for Task 2.1: the scaffold counter demo (`App.tsx`) was
 * replaced by the real layout shell + router, so this now asserts the
 * shell/list-route content instead.
 *
 * The app's router uses `basename: '/app'` (matching the Flask BFF's React
 * shell mount, `ui/beeper_ui/routes/react_shell.py`) — every navigation in
 * this suite goes to an `/app/*` path, and `vite preview`'s SPA fallback
 * serves `index.html` for any unmatched path so this works without Flask.
 */
test.describe('app shell', () => {
  test('mounts the React root and redirects to the investigation list', async ({ page }) => {
    await page.goto('/app/')

    const root = page.locator('#root')
    await expect(root).toBeVisible()

    // The index route redirects to /app/investigations.
    await expect(page).toHaveURL(/\/app\/investigations$/)
    await expect(page.getByRole('heading', { name: 'Investigations' })).toBeVisible()
  })

  test('renders the Observe/Learn/Manage sidebar with Investigations active', async ({ page }) => {
    await page.goto('/app/investigations')

    await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
    await expect(page.getByText('Observe')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Investigations', exact: true })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  test('navigating to a detail URL renders the shell with the sidebar still visible', async ({ page }) => {
    await page.goto('/app/investigations/INV-0042')

    await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'INV-0042' })).toBeVisible()
  })

  test('an unknown path still renders inside the shell (sidebar visible), not a bare 404', async ({ page }) => {
    await page.goto('/app/nonexistent-route')

    await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
    await expect(page.getByText('Page not found')).toBeVisible()
  })
})
