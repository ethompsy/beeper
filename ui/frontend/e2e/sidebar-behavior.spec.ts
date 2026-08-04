import { test, expect } from '@playwright/test'

/**
 * sidebar-behavior.spec.ts
 *
 * Task 2.1 AC [T] — breakpoint push/overlay behavior at the real 1200px
 * boundary (viewport resize in a real browser, complementing the
 * unit-level `useSidebarState.test.ts` matchMedia-mock coverage), the
 * detail-route auto-collapse, and `prefers-reduced-motion` emulation.
 */
test.describe('sidebar breakpoint behavior', () => {
  test('at >=1200px, manually collapsing then re-expanding pushes content (margin changes)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/app/investigations')

    const content = page.locator('[data-slot="content-area"]')
    // >=1200px defaults to expanded/pushing.
    await expect(content).toHaveClass(/ml-64/)

    const toggle = page.getByRole('button', { name: 'Toggle navigation sidebar' })
    await toggle.click()
    await expect(content).toHaveClass(/ml-16/)
    await expect(content).not.toHaveClass(/ml-64/)

    await toggle.click()
    await expect(content).toHaveClass(/ml-64/)
  })

  test('at <1200px, manually expanding overlays content (margin does not change)', async ({ page }) => {
    await page.setViewportSize({ width: 900, height: 800 })
    await page.goto('/app/investigations')

    const content = page.locator('[data-slot="content-area"]')
    // <1200px defaults to collapsed icon rail.
    await expect(content).toHaveClass(/ml-16/)

    const toggle = page.getByRole('button', { name: 'Toggle navigation sidebar' })
    await toggle.click()

    // Sidebar is now expanded (256px) but overlaying — content margin is
    // unchanged (no width shift), per FR41.
    const sidebar = page.getByRole('navigation', { name: 'Main navigation' })
    await expect(sidebar).toHaveClass(/w-64/)
    await expect(content).toHaveClass(/ml-16/)
    await expect(content).not.toHaveClass(/ml-64/)
  })

  test('the detail route auto-collapses the sidebar even at a wide (>=1200px) viewport', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/app/investigations/INV-0042')

    const sidebar = page.getByRole('navigation', { name: 'Main navigation' })
    await expect(sidebar).toHaveClass(/w-16/)
    await expect(sidebar).not.toHaveClass(/w-64/)
  })

  test('navigating back to the list from detail restores the viewport-appropriate default', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/app/investigations/INV-0042')

    const sidebar = page.getByRole('navigation', { name: 'Main navigation' })
    await expect(sidebar).toHaveClass(/w-16/)

    await page.getByRole('link', { name: 'Investigations' }).click()
    await expect(page).toHaveURL(/\/app\/investigations$/)
    // Back on the list route at >=1200px, the auto default is expanded.
    await expect(sidebar).toHaveClass(/w-64/)
  })
})

test.describe('reduced motion (NFR22 / FR51)', () => {
  test.use({ reducedMotion: 'reduce' })

  test('sidebar width transition is effectively instant under prefers-reduced-motion: reduce', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/app/investigations')

    const sidebar = page.getByRole('navigation', { name: 'Main navigation' })
    const transitionDuration = await sidebar.evaluate(
      (el) => window.getComputedStyle(el).transitionDuration,
    )
    // tokens.css's global `prefers-reduced-motion: reduce` override forces
    // `transition-duration: 0ms !important` — every comma-separated value
    // in the computed shorthand collapses to 0s.
    expect(transitionDuration.split(',').every((value) => value.trim() === '0s')).toBe(true)
  })
})
