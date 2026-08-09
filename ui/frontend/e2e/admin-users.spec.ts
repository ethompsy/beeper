import { test, expect, authenticatedUser, type Page } from './fixtures/auth'
import AxeBuilder from '@axe-core/playwright'

/**
 * admin-users.spec.ts (Task 8.7 — ADR 0002 §6, FR60).
 *
 * AC [T]: "e2e: admin sees and uses the view; non-admin gets the in-shell
 * 403; nav item hidden for non-admin (via the auth fixture)." Plus the
 * plan's Task 8.7 AC: "one e2e (seeded admin → create user → self
 * -demotion blocked by last-admin 409 rendered inline)."
 *
 * Runs against the *built* app (`vite preview`, this repo's established
 * e2e convention — no Flask backend), so every `/api/v1/*` call is mocked
 * via `page.route`, matching `local-login.spec.ts`'s pattern. Uses the
 * shared Playwright auth fixture (`e2e/fixtures/auth.ts`) — required by
 * the static guard in `src/test/e2e-auth-fixture-usage.test.ts` for any
 * spec referencing the `/me` contract.
 */

interface MockAdminUser {
  id: string
  user_name: string
  display_name: string
  role: 'admin' | 'user'
  origin: 'local' | 'scim'
  active: boolean
  last_login_at: string | null
}

function seededAdmin(overrides: Partial<MockAdminUser> = {}): MockAdminUser {
  return {
    id: 'user-admin-1',
    user_name: 'admin@corp.com',
    display_name: 'Admin Alpha',
    role: 'admin',
    origin: 'local',
    active: true,
    last_login_at: '2026-08-09T12:00:00+00:00',
    ...overrides,
  }
}

function problem(status: number, type: string, title: string, detail: string, instance: string) {
  return { type: `https://beeper.dev/errors/${type}`, title, status, detail, instance }
}

/** Mocks `GET /api/v1/admin/users/` with a mutable, in-memory user list so PATCH/POST below can reflect back into subsequent GETs. */
async function mockUsersList(page: Page, users: MockAdminUser[]) {
  await page.route('**/api/v1/admin/users/', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(users) })
  })
}

async function mockForbiddenUsersList(page: Page) {
  await page.route('**/api/v1/admin/users/', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    await route.fulfill({
      status: 403,
      contentType: 'application/problem+json',
      body: JSON.stringify(
        problem(403, 'permission-denied', 'Permission Denied', 'Admin role required to access this resource', '/api/v1/admin/users/'),
      ),
    })
  })
}

test.describe('admin-users: admin session', () => {
  test.use({
    currentUser: authenticatedUser('local', {
      user_name: 'admin@corp.com',
      display_name: 'Admin Alpha',
      role: 'admin',
    }),
  })

  test('an admin sees the Users nav item, opens the view, and creates a user', async ({ page }) => {
    const seeded = seededAdmin()
    await mockUsersList(page, [seeded])
    await page.route('**/api/v1/admin/users/', async (route) => {
      if (route.request().method() !== 'POST') return route.fallback()
      const created: MockAdminUser = {
        id: 'user-new-1',
        user_name: 'newbie@corp.com',
        display_name: 'Newbie Newton',
        role: 'user',
        origin: 'local',
        active: true,
        last_login_at: null,
      }
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(created) })
    })

    await page.goto('/app/investigations')
    const usersLink = page.getByRole('link', { name: 'Users' })
    await expect(usersLink).toBeVisible()
    await usersLink.click()

    await page.waitForURL('**/app/admin/users')
    await expect(page.getByRole('heading', { name: 'Users' })).toBeVisible()
    await expect(page.getByText('admin@corp.com')).toBeVisible()

    await page.getByRole('button', { name: 'Create user' }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.getByLabel('Username').fill('newbie@corp.com')
    await page.getByLabel('Password').fill('a-very-long-password')
    await page.getByRole('dialog').getByRole('button', { name: 'Create user' }).click()

    await expect(page.getByRole('dialog')).not.toBeVisible()
    await expect(page.getByText('Newbie Newton')).toBeVisible()
  })

  test('AC: self-demotion is blocked by a 409 last-admin, rendered inline (not silently, not a redirect)', async ({
    page,
  }) => {
    const seeded = seededAdmin()
    await mockUsersList(page, [seeded])
    await page.route('**/api/v1/admin/users/*', async (route) => {
      if (route.request().method() !== 'PATCH') return route.fallback()
      await route.fulfill({
        status: 409,
        contentType: 'application/problem+json',
        body: JSON.stringify(
          problem(
            409,
            'last-admin',
            'Last Admin Protected',
            'This is the last active admin. Promote another user to admin before demoting or deactivating this account.',
            `/api/v1/admin/users/${seeded.id}`,
          ),
        ),
      })
    })

    await page.goto('/app/admin/users')
    await expect(page.getByText('admin@corp.com')).toBeVisible()

    // Self-demotion via the row's role select.
    const row = page.getByTestId(`user-row-${seeded.id}`)
    await row.getByLabel('Role').selectOption('user')

    const alert = page.getByRole('alert')
    await expect(alert).toContainText('This is the last active admin')
    // Page did not navigate away and did not silently drop the error.
    expect(new URL(page.url()).pathname).toBe('/app/admin/users')

    // Same protection surfaces for the deactivate path via the confirm dialog.
    await row.getByRole('button', { name: 'Deactivate' }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Deactivate' }).click()
    await expect(page.getByRole('dialog')).toContainText('This is the last active admin')
    await expect(page.getByRole('dialog')).toBeVisible()
  })

  test('axe-clean: loaded table and an open create dialog', async ({ page }) => {
    await mockUsersList(page, [
      seededAdmin(),
      seededAdmin({ id: 'user-2', user_name: 'bob@corp.com', display_name: 'Bob Beta', role: 'user', origin: 'scim' }),
    ])
    await page.goto('/app/admin/users')
    await expect(page.getByText('admin@corp.com')).toBeVisible()

    const tableResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze()
    expect(tableResults.violations, JSON.stringify(tableResults.violations, null, 2)).toEqual([])

    await page.getByRole('button', { name: 'Create user' }).click()
    await expect(page.getByRole('dialog')).toBeVisible()

    const dialogResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze()
    expect(dialogResults.violations, JSON.stringify(dialogResults.violations, null, 2)).toEqual([])
  })
})

test.describe('admin-users: non-admin session', () => {
  test.use({
    currentUser: authenticatedUser('local', {
      user_name: 'regular@corp.com',
      display_name: 'Regular User',
      role: 'user',
    }),
  })

  test('the Users nav item is hidden for a non-admin caller', async ({ page }) => {
    await page.goto('/app/investigations')
    await expect(page.getByRole('link', { name: 'Users' })).toHaveCount(0)
  })

  test('direct navigation to /app/admin/users renders the in-shell 403 message, not a redirect or blank page', async ({
    page,
  }) => {
    await mockForbiddenUsersList(page)

    await page.goto('/app/admin/users')

    await expect(page.getByText('Admin access required')).toBeVisible()
    // Stayed on the same URL — no redirect (a 403 is an authorization
    // failure for an already-authenticated caller, not a login prompt).
    expect(new URL(page.url()).pathname).toBe('/app/admin/users')
    await expect(page.getByRole('button', { name: 'Create user' })).toHaveCount(0)
  })
})
