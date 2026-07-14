/**
 * legacy-label-lint.test.ts
 *
 * Task 4.1 [T] — "migrated views contain no stray legacy labels": a lint
 * that scans the migrated view source (`src/routes/**`, `src/lib/
 * components/**`, `src/lib/investigations/**` — see `SCAN_ROOTS` in
 * `scripts/legacy-label-rules.mjs`) for disallowed legacy strings (the
 * `docs/design/terminology-glossary.md` "current -> standardized" renames)
 * and fails if any are present.
 *
 * Proof, per the AC:
 *   (1) the scan PASSES (zero violations) on the current, correct code.
 *   (2) the scan FAILS (reports violations) on a deliberately-planted
 *       legacy-label fixture (`fixtures/legacy-labels-violating.tsx`,
 *       which lives under `src/test/` and is therefore outside the real
 *       `SCAN_ROOTS` — proving the fixture doesn't accidentally poison (1)).
 *
 * This suite runs as part of `npm test` (Vitest), which is already in the
 * CI-safety gate — no separate CI step needed. `scripts/check-legacy-
 * labels.mjs` (`npm run lint:terms`) wraps the same engine for standalone/
 * manual use.
 */

import { describe, it, expect } from 'vitest'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  scanFile,
  scanDirectory,
  SCAN_ROOTS,
  formatViolations,
} from '../../scripts/legacy-label-rules.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const FRONTEND_ROOT = resolve(__dirname, '../..')

describe('legacy-label lint — migrated view source contains no stray legacy labels (Task 4.1)', () => {
  it('[T] the real migrated-view scan scope (routes + lib/components + lib/investigations) has zero legacy-label matches', () => {
    const violations = SCAN_ROOTS.flatMap((root) => scanDirectory(resolve(FRONTEND_ROOT, root)))
    expect(violations, formatViolations(violations)).toEqual([])
  })

  it('[T] the scanner FAILS (reports violations) on a deliberately-planted legacy-label fixture', () => {
    const fixture = resolve(__dirname, 'fixtures/legacy-labels-violating.tsx')
    const violations = scanFile(fixture)

    expect(violations.length).toBeGreaterThan(0)

    const matchedIds = violations.map((v) => v.id)
    expect(matchedIds).toContain('phase-in-progress')
    expect(matchedIds).toContain('phase-awaiting-bare')
    expect(matchedIds).toContain('detail-investigation-timeline')
    expect(matchedIds).toContain('findings-knowledge-base-matches')
  })

  it('sanity: the fixture directory itself is outside SCAN_ROOTS (proves (1) and (2) cannot cross-contaminate)', () => {
    const fixtureDir = resolve(__dirname, 'fixtures')
    const scanRootAbsolutePaths = SCAN_ROOTS.map((root) => resolve(FRONTEND_ROOT, root))
    for (const scanRoot of scanRootAbsolutePaths) {
      expect(fixtureDir.startsWith(scanRoot)).toBe(false)
    }
  })
})
