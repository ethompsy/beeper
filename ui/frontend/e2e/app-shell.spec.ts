import { test, expect } from '@playwright/test'

/**
 * app-shell.spec.ts
 *
 * Task 1.7 AC [T] — a sample Playwright e2e test runs green in CI against
 * the *built* app (served via `vite preview`, per playwright.config.ts
 * `webServer`), proving the production bundle actually mounts in a real
 * browser — not just that Vitest/jsdom is happy with it.
 */
test.describe('app shell', () => {
  test('mounts the React root and renders known scaffold content', async ({ page }) => {
    await page.goto('/')

    // The SPA mounts into #root (see index.html / src/main.tsx).
    const root = page.locator('#root')
    await expect(root).toBeVisible()

    // Known scaffold text (src/App.tsx) — proves React actually rendered
    // into the DOM, not just that the empty shell HTML loaded.
    await expect(page.getByRole('heading', { name: 'Get started' })).toBeVisible()
    await expect(page.getByRole('button', { name: /Count is \d+/ })).toBeVisible()
  })

  test('counter button increments on click', async ({ page }) => {
    await page.goto('/')

    const button = page.getByRole('button', { name: /Count is \d+/ })
    await expect(button).toHaveText('Count is 0')

    await button.click()
    await expect(button).toHaveText('Count is 1')
  })
})
