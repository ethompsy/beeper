/**
 * story-coverage.test.ts
 *
 * AC [T] (Task 4.2) — "every first-increment component has a Storybook
 * story" (`InvestigationCard`, `StatusBadge`, `InvestigationStep`,
 * `SummaryHeader`, `RelatedKbPanel`, the shell primitives `Sidebar`/
 * `AppShell`, and the 2.5/2.6 state/detail primitives). Prove it with a test
 * that asserts a story file exists for every barrel-exported component,
 * rather than eyeballing the `components/` directory by hand.
 *
 * Strategy: static-source assertions (no JS/Storybook runner — consistent
 * with this repo's client-side test convention). Two layers:
 *
 *  1. Parse `src/lib/index.ts` (the extraction-boundary barrel — see its
 *     header comment: "A component only 'graduates' into the library ...
 *     once it ... [has] a Storybook-documented primitive") for every
 *     `export { X } from './components/Y'` line, then assert each has a
 *     `<Name>.stories.tsx` sibling that (a) declares a Storybook `Meta`
 *     wired to the real component (`component: <Name>`) and (b) exports at
 *     least one story.
 *  2. Defense in depth: walk `src/lib/components/*` directly and assert
 *     every directory on disk has a story file too, so a component that was
 *     scaffolded but never wired into the barrel (and never given a story)
 *     doesn't slip through undetected by check #1 alone.
 *
 * If a future component graduates into the barrel without a story, this
 * test fails immediately naming the missing file — no manual story-map
 * bookkeeping required.
 */
import { describe, it, expect } from 'vitest'
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const LIB_ROOT = resolve(__dirname, '..')
const BARREL_PATH = resolve(LIB_ROOT, 'index.ts')
const COMPONENTS_DIR = resolve(LIB_ROOT, 'components')

const barrelSource = readFileSync(BARREL_PATH, 'utf-8')

/**
 * Extract the set of component names the barrel re-exports from
 * `./components/<Name>` (deliberately excludes `./hooks/*` and
 * `./utils/*` re-exports — hooks/utils aren't Storybook subjects).
 */
function barrelExportedComponents(source: string): string[] {
  const names = new Set<string>()
  const re = /export\s*\{\s*([A-Za-z0-9_]+)\s*\}\s*from\s*'\.\/components\/([A-Za-z0-9_]+)'/g
  let match: RegExpExecArray | null
  while ((match = re.exec(source)) !== null) {
    names.add(match[1])
  }
  return [...names].sort()
}

const barrelComponents = barrelExportedComponents(barrelSource)

describe('component library — Storybook story coverage (Task 4.2)', () => {
  it('the barrel-export parser found the full first-increment component set (sanity check)', () => {
    // Guards against a regex/parser regression silently shrinking the
    // checked set to near-zero and the tests below passing vacuously.
    expect(barrelComponents.length).toBeGreaterThanOrEqual(15)
    for (const name of [
      'InvestigationCard',
      'StatusBadge',
      'InvestigationStep',
      'SummaryHeader',
      'RelatedKbPanel',
      'Sidebar',
      'AppShell',
      'StepEvidence',
      'FailureNotice',
      'NotFoundMessage',
      'DetailSkeleton',
      'SseConnectionIndicator',
      'InvestigationListSkeleton',
      'StatusGroupFilter',
      'EmptyGroupState',
    ]) {
      expect(barrelComponents, `expected barrel to export "${name}"`).toContain(name)
    }
  })

  describe.each(barrelComponents)('%s', (name) => {
    const storyPath = resolve(COMPONENTS_DIR, name, `${name}.stories.tsx`)

    it('has a Storybook story file', () => {
      expect(existsSync(storyPath), `expected ${storyPath} to exist`).toBe(true)
    })

    it('story file wires its Meta to the real component and exports >=1 story', () => {
      const source = readFileSync(storyPath, 'utf-8')
      expect(source, `${name}.stories.tsx should declare component: ${name} in its Meta`).toMatch(
        new RegExp(`component:\\s*${name}\\b`),
      )
      expect(source, `${name}.stories.tsx should declare a Storybook Meta object`).toMatch(
        /satisfies\s+Meta</,
      )
      expect(source, `${name}.stories.tsx should export at least one story`).toMatch(
        /export const \w+: Story\s*=/,
      )
    })
  })

  it('every component directory on disk (not just barrel-exported ones) has a story file', () => {
    const dirs = readdirSync(COMPONENTS_DIR, { withFileTypes: true })
      .filter((d) => d.isDirectory())
      .map((d) => d.name)
      .sort()

    expect(dirs.length).toBeGreaterThanOrEqual(15)

    for (const dir of dirs) {
      const storyPath = resolve(COMPONENTS_DIR, dir, `${dir}.stories.tsx`)
      expect(existsSync(storyPath), `expected ${storyPath} to exist for components/${dir}`).toBe(
        true,
      )
    }
  })
})
