#!/usr/bin/env node
/**
 * check-legacy-labels.mjs
 *
 * Task 4.1 [T]: "migrated views contain no stray legacy labels."
 *
 * CLI entry point — run manually or wired into CI as `npm run lint:terms`.
 * The actual proof of the acceptance criterion (passes on current code,
 * fails on a deliberately-planted fixture) lives in the Vitest suite
 * `src/test/legacy-label-lint.test.ts`, which is part of `npm test` (the
 * CI-safety gate already runs that). This script exists so the same check
 * is also runnable/scriptable standalone, matching the
 * `scripts/verify-build.mjs` precedent in this directory.
 *
 * Run: node scripts/check-legacy-labels.mjs
 * Exit 0 = no legacy labels found. Exit 1 = at least one violation.
 */

import { resolve, dirname, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { scanDirectory, SCAN_ROOTS, formatViolations } from './legacy-label-rules.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const FRONTEND_ROOT = resolve(__dirname, '..')

const violations = SCAN_ROOTS.flatMap((root) => scanDirectory(resolve(FRONTEND_ROOT, root)))

if (violations.length === 0) {
  console.log(`legacy-label lint: PASS — scanned ${SCAN_ROOTS.join(', ')}, 0 stray legacy labels found.`)
  process.exit(0)
}

console.error(`legacy-label lint: FAIL — ${violations.length} stray legacy label(s) found:\n`)
console.error(
  formatViolations(
    violations.map((v) => ({ ...v, file: relative(FRONTEND_ROOT, v.file) })),
  ),
)
console.error('\nSee docs/design/terminology-glossary.md for the current -> standardized mapping.')
process.exit(1)
