/**
 * e2e/fixtures/auth.ts — the shared Playwright auth fixture (Task 8.4, ADR
 * 0002 §8 "a shared e2e auth fixture mocks `/api/v1/auth/me` for the specs
 * that assert auth states").
 *
 * ── Why this exists ─────────────────────────────────────────────────────
 *
 * All 87 pre-existing specs in this suite run against `vite preview` (the
 * *built* static bundle, no Flask backend — see `playwright.config.ts`'s
 * header comment) with every `/api/v1/*` JSON call mocked per-spec via
 * `page.route`. None of them mock `/api/v1/auth/me`, and none needed to:
 * mode `none` (this repo's only mode until 8.5/8.6 land real login) never
 * emits a 401, `apiFetch` never has a reason to call `/me`, and
 * `useCurrentUser`'s `fetchCurrentUser()` is failure-tolerant by contract
 * (an unmocked `/api/v1/auth/me` 404s against `vite preview`'s static
 * server, which resolves to the same `{auth_mode: 'none', authenticated:
 * false, user: null}` fallback a real mode-`none` deployment would report
 * anyway). So the 87 existing specs stay green completely unmodified —
 * this fixture does not change that.
 *
 * What THIS fixture adds is making that "mode `none`, no auth" baseline
 * EXPLICIT and importable, plus a ready seam for 8.5/8.6: a spec that
 * needs to assert something about auth state (an authenticated nav item,
 * a login redirect, a permission-denied render) imports `test`/`expect`
 * from HERE instead of `@playwright/test` directly, and gets
 * `/api/v1/auth/me` mocked to a known shape automatically. See
 * `src/test/e2e-auth-fixture-usage.test.ts` for the static guard that
 * keeps future auth-asserting specs honest about using it.
 */
import { test as base, expect, type Page } from '@playwright/test'

export type AuthMode = 'none' | 'local' | 'oidc'

export interface CurrentUserFixtureUser {
  user_name: string
  display_name: string
  role: 'admin' | 'user' | null
}

/** Mirrors `GET /api/v1/auth/me`'s response body (ADR 0002 §3/§6) exactly. */
export interface CurrentUserFixtureBody {
  authenticated: boolean
  auth_mode: AuthMode
  user: CurrentUserFixtureUser | null
}

export const ANONYMOUS_NONE: CurrentUserFixtureBody = {
  authenticated: false,
  auth_mode: 'none',
  user: null,
}

/** Convenience builder for 8.5/8.6's authenticated scenarios. */
export function authenticatedUser(
  authMode: 'local' | 'oidc',
  user: CurrentUserFixtureUser,
): CurrentUserFixtureBody {
  return { authenticated: true, auth_mode: authMode, user }
}

/**
 * Mocks `GET /api/v1/auth/me` on `page`, defaulting to the mode-`none`
 * anonymous shape. Exported standalone (not only via the `test` fixture
 * below) so a spec can re-mock mid-test — e.g. simulating a session
 * dropping between two actions — without needing a second Playwright
 * fixture/project.
 */
export async function mockCurrentUser(
  page: Page,
  body: CurrentUserFixtureBody = ANONYMOUS_NONE,
): Promise<void> {
  await page.route('**/api/v1/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
  })
}

/**
 * Drop-in replacement for `@playwright/test`'s `test` — adds one fixture
 * option, `currentUser`, defaulting to `ANONYMOUS_NONE` (mode `none`, the
 * baseline every existing spec already runs under). Override per-test via
 * `test.use({ currentUser: authenticatedUser('local', {...}) })` once
 * 8.5/8.6 have real authenticated scenarios to assert against — no spec
 * needs to hand-roll its own `/api/v1/auth/me` route mock.
 */
export const test = base.extend<{ currentUser: CurrentUserFixtureBody }>({
  currentUser: [ANONYMOUS_NONE, { option: true }],
  page: async ({ page, currentUser }, use) => {
    await mockCurrentUser(page, currentUser)
    await use(page)
  },
})

export { expect }
