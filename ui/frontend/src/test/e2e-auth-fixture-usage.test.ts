/**
 * e2e-auth-fixture-usage.test.ts (Task 8.4)
 *
 * AC [T] — "shared e2e auth fixture exists + static assertion that
 * auth-asserting specs use it." Static-source guard (this repo's
 * established client-side test convention — no Playwright run needed):
 * any `e2e/*.spec.ts` file that mocks `/api/v1/auth/me` directly via
 * `page.route`, OR references the `/me` response fields (`auth_mode`,
 * `authenticated`), must import from the shared fixture
 * (`e2e/fixtures/auth.ts`) rather than hand-rolling its own mock — keeping
 * exactly one place that knows the `/me` response shape.
 *
 * As of Task 8.4, zero of the 87 pre-existing specs are "auth-asserting"
 * (mode `none` has no login/session UI yet — that's 8.5/8.6/8.7's scope),
 * so this test passes vacuously today; its job is to fail loudly the
 * moment a future spec starts asserting auth state without the fixture.
 * `auth-fixture.spec.ts` (this task) is the one spec that DOES reference
 * `/api/v1/auth/me` today and IS exempt from its own rule (it's the
 * fixture's own proof-of-mechanism test, imported FROM the fixture file,
 * not a consumer of it).
 */
import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const E2E_DIR = resolve(__dirname, '../../e2e')
const FIXTURE_RELATIVE_PATH = './fixtures/auth'
const FIXTURE_FILE = 'fixtures/auth.ts'

/** True if `source` mocks or references the `/me` auth-probe contract directly. */
function referencesAuthMeContract(source: string): boolean {
  return (
    source.includes('/api/v1/auth/me') ||
    /\bauth_mode\b/.test(source) ||
    /\bauthenticated\s*:/.test(source)
  )
}

function importsSharedFixture(source: string): boolean {
  return source.includes(FIXTURE_RELATIVE_PATH)
}

function specFiles(): string[] {
  return readdirSync(E2E_DIR, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith('.spec.ts'))
    .map((entry) => entry.name)
    .sort()
}

describe('e2e specs — auth-asserting specs must use the shared fixture (Task 8.4)', () => {
  it('sanity check: specs were actually found (guards against a path regression passing vacuously)', () => {
    const files = specFiles()
    expect(files.length).toBeGreaterThanOrEqual(13)
    expect(files).toContain('auth-fixture.spec.ts')
  })

  it('the shared fixture file itself exists', () => {
    expect(() => readFileSync(resolve(E2E_DIR, FIXTURE_FILE), 'utf-8')).not.toThrow()
  })

  describe.each(specFiles())('%s', (file) => {
    it('imports the shared auth fixture if (and only if) it asserts auth state', () => {
      const source = readFileSync(resolve(E2E_DIR, file), 'utf-8')

      if (!referencesAuthMeContract(source)) {
        // Not auth-asserting — nothing to check (this is the expected case
        // for all 87 pre-existing specs today).
        return
      }

      expect(
        importsSharedFixture(source),
        `${file} references the /api/v1/auth/me contract (auth_mode/authenticated) ` +
          `but does not import the shared fixture from '${FIXTURE_RELATIVE_PATH}' — ` +
          `use e2e/fixtures/auth.ts instead of hand-rolling the mock.`,
      ).toBe(true)
    })
  })
})
