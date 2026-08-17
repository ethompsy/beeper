/**
 * no-bare-fetch.test.ts (Task 8.4)
 *
 * AC [T] — "All 8 clients migrated; static-sweep test proves no bare
 * `fetch(` in `src/api/`." Every `src/api/*.ts` module (the 8 REST clients)
 * must route through the shared `apiFetch` seam (`src/api/http.ts`) instead
 * of calling the global `fetch` directly, so a future client can't
 * accidentally bypass the 401/403 auth seam (ADR 0002 §8).
 *
 * Static-source assertion (no JS runner needed beyond Vitest's own Node
 * environment) — reads every top-level `.ts` file directly inside
 * `src/api/` (NOT `src/api/test/`, and not recursively) and regex-scans for
 * a bare `fetch(` call. `http.ts` itself is exempt (it IS the wrapper — it
 * must call the real `fetch`) and is instead asserted to actually export
 * `apiFetch`, so the exemption can't silently swallow a real regression
 * there either.
 *
 * The regex excludes any call immediately preceded by a word character or
 * `.` (so `apiFetch(`, `window.fetch(`, `myFetch(` etc. don't false-positive)
 * — deliberately looser than requiring the exact `apiFetch` name, so it also
 * catches any OTHER wrapper someone might introduce that isn't the sanctioned
 * seam.
 */
import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const API_DIR = resolve(__dirname, '..')

/** Matches a bare `fetch(` call not preceded by a word char or `.` (so it skips `apiFetch(`, `window.fetch(`, etc.). */
const BARE_FETCH_RE = /(?<![.\w])fetch\(/

function topLevelApiClientFiles(): string[] {
  return readdirSync(API_DIR, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith('.ts'))
    .map((entry) => entry.name)
    .sort()
}

describe('src/api/*.ts — no bare fetch() calls (Task 8.4 static sweep)', () => {
  const files = topLevelApiClientFiles()

  it('sanity check: the expected 9 clients + http.ts were actually found', () => {
    expect(files).toEqual([
      'admin-users.ts',
      'http.ts',
      'ingestion-stats.ts',
      'investigation-detail.ts',
      'investigations-list.ts',
      'knowledge-detail.ts',
      'knowledge-list.ts',
      'metrics.ts',
      'sources-list.ts',
      'spending.ts',
    ])
  })

  describe.each(files.filter((f) => f !== 'http.ts'))('%s', (file) => {
    it('imports apiFetch from ./http', () => {
      const source = readFileSync(resolve(API_DIR, file), 'utf-8')
      expect(source, `${file} should import apiFetch from './http'`).toMatch(
        /import\s*\{[^}]*\bapiFetch\b[^}]*\}\s*from\s*'\.\/http'/,
      )
    })

    it('never calls the bare global fetch()', () => {
      const source = readFileSync(resolve(API_DIR, file), 'utf-8')
      expect(BARE_FETCH_RE.test(source), `${file} should not call bare fetch(directly)`).toBe(
        false,
      )
    })
  })

  it('http.ts is the one sanctioned exception and actually exports apiFetch', () => {
    const source = readFileSync(resolve(API_DIR, 'http.ts'), 'utf-8')
    expect(source).toMatch(/export\s+async\s+function\s+apiFetch\b/)
  })
})
