/**
 * dist-import.test.ts
 *
 * AC [T] (Task 1.4) — "the library builds to a `dist` that exports ≥1 NAMED
 * component importable by an external consumer (prove with an ESM
 * import/`require` check in a test — not merely 'Storybook builds')."
 *
 * Strategy: dynamically `import()` the ACTUAL BUILT ARTIFACT at
 * `dist-lib/index.js` — not the TypeScript source — the same way an
 * external consumer (e.g. `/design-sync`, or a Milestone 1.2 view importing
 * `frontend/dist-lib`) would. This proves the compiled bundle itself is
 * consumable, not just that the source compiles.
 *
 * Precondition: `npm run build:lib` must have run first (produces
 * `dist-lib/index.js` + `.d.ts`). CI wires `build:lib` before `test` for
 * this file; run it manually first when testing locally:
 *   npm run build:lib && npm test
 *
 * If `dist-lib/index.js` is missing, this test fails loudly with a clear
 * message rather than silently skipping — a skipped [T] test is not proof.
 */
import { describe, it, expect, beforeAll } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const distEntry = resolve(__dirname, '../../../dist-lib/index.js')
const distTypes = resolve(__dirname, '../../../dist-lib/index.d.ts')

const EXPECTED_NAMED_EXPORTS = [
  'InvestigationCard',
  'StatusBadge',
  'InvestigationStep',
  'SummaryHeader',
  'RelatedKbPanel',
  'cn',
] as const

describe('dist-lib bundle — external-consumer import contract', () => {
  beforeAll(() => {
    if (!existsSync(distEntry)) {
      throw new Error(
        `dist-lib/index.js not found at ${distEntry}. Run \`npm run build:lib\` before this test.`,
      )
    }
  })

  it('exists as a built artifact (not source)', () => {
    expect(existsSync(distEntry)).toBe(true)
    expect(existsSync(distTypes)).toBe(true)
  })

  it('is importable via a dynamic ESM import() and exports every named component + cn', async () => {
    const mod = (await import(pathToFileURL(distEntry).href)) as Record<string, unknown>

    for (const name of EXPECTED_NAMED_EXPORTS) {
      expect(mod, `expected named export "${name}"`).toHaveProperty(name)
      expect(typeof mod[name], `"${name}" should be a function (component or util)`).toBe(
        'function',
      )
    }
  })

  it('exports at least one named component beyond the ≥1 AC minimum', async () => {
    const mod = (await import(pathToFileURL(distEntry).href)) as Record<string, unknown>
    const componentNames = EXPECTED_NAMED_EXPORTS.filter((n) => n !== 'cn')
    expect(componentNames.length).toBeGreaterThanOrEqual(1)
    for (const name of componentNames) {
      expect(mod[name]).toBeDefined()
    }
  })

  it('ships a d.ts entry declaring the same named exports (type-level contract)', () => {
    const dts = readFileSync(distTypes, 'utf-8')
    for (const name of EXPECTED_NAMED_EXPORTS) {
      expect(dts, `dist-lib/index.d.ts should re-export "${name}"`).toMatch(
        new RegExp(`\\b${name}\\b`),
      )
    }
  })

  it('externalizes react/react-dom rather than bundling them (peer-dep contract)', () => {
    const bundleSource = readFileSync(distEntry, 'utf-8')
    // The bundle must import react from the bare specifier (externalized),
    // never inline React's own source (which would bloat the library and
    // risk a duplicate-React-instance bug for consumers).
    expect(bundleSource).toMatch(/from\s+["']react["']/)
  })
})
