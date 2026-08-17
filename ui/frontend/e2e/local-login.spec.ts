import { test, expect, mockCurrentUser, authenticatedUser } from './fixtures/auth'
import AxeBuilder from '@axe-core/playwright'

/**
 * local-login.spec.ts (Task 8.6 — ADR 0002 §6, FR59).
 *
 * AC [T]: "an e2e: unauthenticated `local`-mode visit to a protected view
 * redirects to `/app/login?next=...`, submitting valid creds lands back
 * on `next` (use the 8.4 auth fixture + route mocking)."
 *
 * Runs against the *built* app (`vite preview`, this repo's established
 * e2e convention — no Flask backend), so every `/api/v1/*` call is
 * mocked via `page.route`, matching `investigation-list.spec.ts`'s
 * pattern. Uses the shared Playwright auth fixture
 * (`e2e/fixtures/auth.ts`) for `/api/v1/auth/me` — required by the static
 * guard in `src/test/e2e-auth-fixture-usage.test.ts` for any spec that
 * references the `/me` contract.
 */

const AUTH_REQUIRED_PROBLEM = {
  type: 'https://beeper.dev/errors/authentication-required',
  title: 'Authentication Required',
  status: 401,
  detail: 'A valid session is required to access this resource.',
  instance: '/api/v1/investigations/',
}

async function mockInvestigationsUnauthorized(page: import('@playwright/test').Page) {
  await page.route('**/api/v1/investigations/**', async (route) => {
    await route.fulfill({
      status: 401,
      contentType: 'application/problem+json',
      body: JSON.stringify(AUTH_REQUIRED_PROBLEM),
    })
  })
}

async function mockInvestigationsEmpty(page: import('@playwright/test').Page) {
  await page.route('**/api/v1/investigations/**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
  })
}

async function mockLoginSuccess(page: import('@playwright/test').Page) {
  await page.route('**/api/v1/auth/login', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        authenticated: true,
        auth_mode: 'local',
        user: { user_name: 'alice', display_name: 'Alice Alpha', role: 'admin' },
      }),
    })
  })
}

async function mockLoginFailure(page: import('@playwright/test').Page) {
  await page.route('**/api/v1/auth/login', async (route) => {
    await route.fulfill({
      status: 401,
      contentType: 'application/problem+json',
      body: JSON.stringify({
        type: 'https://beeper.dev/errors/invalid-credentials',
        title: 'Invalid Credentials',
        status: 401,
        detail: 'Invalid username or password.',
        instance: '/api/v1/auth/login',
      }),
    })
  })
}

test.describe('unauthenticated local-mode redirect + login round-trip', () => {
  test.use({
    currentUser: { authenticated: false, auth_mode: 'local', user: null },
  })

  test('visiting a protected view redirects to /app/login?next=..., and a valid login lands back on next', async ({
    page,
  }) => {
    await mockInvestigationsUnauthorized(page)

    await page.goto('/app/investigations')

    // apiFetch's 401 handler resolves the mode via /me (mocked "local",
    // unauthenticated above), then navigates to /app/login?next=<original
    // app path>.
    await page.waitForURL('**/app/login?next=**')
    const url = new URL(page.url())
    expect(url.pathname).toBe('/app/login')
    expect(url.searchParams.get('next')).toBe('/app/investigations')

    await expect(page.getByRole('heading', { name: 'Sign in to Beeper' })).toBeVisible()

    // Flip the mocks to represent a successful login: /login succeeds,
    // /me now reports authenticated, and the investigations list returns
    // real (empty) data instead of 401 — otherwise landing back on
    // /app/investigations would immediately redirect to /login again.
    await mockLoginSuccess(page)
    await mockCurrentUser(
      page,
      authenticatedUser('local', { user_name: 'alice', display_name: 'Alice Alpha', role: 'admin' }),
    )
    await mockInvestigationsEmpty(page)

    await page.getByLabel('Username').fill('alice')
    await page.getByLabel('Password').fill('correct-horse-battery-staple')
    await page.getByRole('button', { name: 'Sign in' }).click()

    await page.waitForURL('**/app/investigations')
    const finalUrl = new URL(page.url())
    expect(finalUrl.pathname).toBe('/app/investigations')
  })

  test('an invalid login shows the uniform error and stays on the login page', async ({
    page,
  }) => {
    await mockLoginFailure(page)
    await page.goto('/app/login')

    await page.getByLabel('Username').fill('nobody')
    await page.getByLabel('Password').fill('wrong-password')
    await page.getByRole('button', { name: 'Sign in' }).click()

    await expect(page.getByRole('alert')).toHaveText('Invalid username or password.')
    expect(new URL(page.url()).pathname).toBe('/app/login')
  })
})

test.describe('login page — direct visit (default currentUser: mode none)', () => {
  test('a next= pointing outside /app falls back after a successful login', async ({ page }) => {
    await mockLoginSuccess(page)
    await mockCurrentUser(
      page,
      authenticatedUser('local', { user_name: 'alice', display_name: 'Alice Alpha', role: 'admin' }),
    )
    await mockInvestigationsEmpty(page)

    await page.goto('/app/login?next=' + encodeURIComponent('https://evil.example.com'))
    await page.getByLabel('Username').fill('alice')
    await page.getByLabel('Password').fill('correct-horse-battery-staple')
    await page.getByRole('button', { name: 'Sign in' }).click()

    await page.waitForURL('**/app/investigations')
  })

  test('axe-clean: loaded state', async ({ page }) => {
    await page.goto('/app/login')
    await expect(page.getByRole('heading', { name: 'Sign in to Beeper' })).toBeVisible()

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze()
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([])
  })

  test('axe-clean: error state', async ({ page }) => {
    await mockLoginFailure(page)
    await page.goto('/app/login')
    await page.getByLabel('Username').fill('nobody')
    await page.getByLabel('Password').fill('wrong-password')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('alert')).toBeVisible()

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze()
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([])
  })
})
