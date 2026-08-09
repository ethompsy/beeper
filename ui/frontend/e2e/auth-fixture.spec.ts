import { test, expect, authenticatedUser } from './fixtures/auth'

/**
 * auth-fixture.spec.ts (Task 8.4)
 *
 * Proves the shared `e2e/fixtures/auth.ts` fixture actually intercepts
 * `GET /api/v1/auth/me` as documented — both its default (mode `none`,
 * matching this suite's 87 pre-existing specs) and an overridden
 * authenticated body (the seam 8.5/8.6 will use). No page in this codebase
 * consumes `useCurrentUser` yet (that's 8.5/8.6/8.7's scope), so this
 * asserts the fixture's network-level contract directly via an in-page
 * `fetch`, rather than through UI it doesn't own.
 */
test.describe('shared e2e auth fixture', () => {
  test('defaults to the mode-none anonymous shape (the baseline every existing spec relies on)', async ({
    page,
  }) => {
    await page.goto('/app/')

    const body = await page.evaluate(async () => {
      const res = await fetch('/api/v1/auth/me')
      return res.json()
    })

    expect(body).toEqual({ authenticated: false, auth_mode: 'none', user: null })
  })

  test.describe('with an overridden authenticated local-mode user', () => {
    test.use({
      currentUser: authenticatedUser('local', {
        user_name: 'alice',
        display_name: 'Alice Alpha',
        role: 'admin',
      }),
    })

    test('serves the overridden body — the seam 8.5/8.6 will build on', async ({ page }) => {
      await page.goto('/app/')

      const body = await page.evaluate(async () => {
        const res = await fetch('/api/v1/auth/me')
        return res.json()
      })

      expect(body).toEqual({
        authenticated: true,
        auth_mode: 'local',
        user: { user_name: 'alice', display_name: 'Alice Alpha', role: 'admin' },
      })
    })
  })
})
