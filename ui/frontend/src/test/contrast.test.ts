/**
 * contrast.test.ts (Task 6.0 — WCAG AA color-contrast token defect, Q10)
 *
 * Task 5.5's accessibility audit found `--color-primary`, `--color-text-muted`,
 * and `--color-status-critical` fail WCAG AA 4.5:1 against the surface tokens
 * they're actually paired with (`e2e/a11y.spec.ts` had `color-contrast`
 * disabled with the measured ratios as justification — now re-enabled).
 * `--color-status-muted` was found to have the same defect during this task's
 * implementation (reachable via `StatusBadge`'s `completed`/`pending`
 * variants, not just large-text/non-text contexts) and was folded in.
 *
 * This test parses the REAL values out of `theme/tokens.css` (never
 * hardcodes a "the fix" hex here) and computes the WCAG relative-luminance
 * contrast ratio in `wcag-contrast.ts` — a fresh, from-the-spec
 * implementation, not a copy of any browser/library's contrast function —
 * so a future value change that regresses contrast fails this test even if
 * nobody remembers this task's history.
 *
 * Two kinds of pairing are checked, matching how these tokens are actually
 * consumed in `src/`:
 *  1. Direct: token text color rendered directly on a solid surface color
 *     (`text-primary` on `bg-surface-raised`, etc.) — the majority of
 *     real usage (links, badges, labels, nav items).
 *  2. Alpha-blended: a token rendered as its own translucent background
 *     tint via Tailwind's `bg-{token}/NN` opacity modifier, composited over
 *     a real surface it sits on in the app today (`StatusGroupFilter`'s
 *     selected tab, `SpendingPage`'s `EnforcementBadge`) — contrast here
 *     depends on the *blended* pixel color, not the pure token value, so a
 *     token can pass every direct check and still render illegibly here.
 *     (Several other translucent-badge call sites that failed this check
 *     during Task 6.0 were fixed at the component level instead — a solid
 *     `bg-surface-overlay` backdrop, immune to blending — because no single
 *     token value could satisfy both their blended contrast and the
 *     dominant direct-text usage; see the sweep list in the Task 6.0
 *     PR/report. This file intentionally does not re-assert those cases as
 *     token-level blend properties, because they are not true in general —
 *     only the two call sites below still use the translucent pattern.)
 */

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  contrastRatio,
  alphaBlend,
  WCAG_AA_SMALL_TEXT,
  type Hex,
} from './wcag-contrast'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const tokensSource = readFileSync(resolve(__dirname, '../theme/tokens.css'), 'utf-8')

function getToken(property: string): Hex {
  const re = new RegExp(`${property.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*:\\s*(#[0-9a-fA-F]{6})`)
  const m = tokensSource.match(re)
  if (!m) throw new Error(`contrast.test.ts: token ${property} not found in tokens.css`)
  return m[1] as Hex
}

const surfaces = {
  'surface-base': getToken('--color-surface-base'),
  'surface-raised': getToken('--color-surface-raised'),
  'surface-overlay': getToken('--color-surface-overlay'),
} as const

const primary = getToken('--color-primary')
const primaryHover = getToken('--color-primary-hover')
const onPrimary = getToken('--color-on-primary')
const textMuted = getToken('--color-text-muted')
const statusCritical = getToken('--color-status-critical')
const statusMuted = getToken('--color-status-muted')

describe('design tokens meet WCAG AA 4.5:1 against their paired surfaces (Task 6.0)', () => {
  describe.each([
    ['--color-primary', primary],
    ['--color-text-muted', textMuted],
    ['--color-status-critical', statusCritical],
    ['--color-status-muted', statusMuted],
  ])('%s (%s) as text, directly on each surface', (_name, tokenHex) => {
    for (const [surfaceName, surfaceHex] of Object.entries(surfaces)) {
      it(`>= 4.5:1 vs ${surfaceName} (${surfaceHex})`, () => {
        const ratio = contrastRatio(tokenHex, surfaceHex)
        expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_SMALL_TEXT)
      })
    }
  })

  describe('--color-on-primary as text on a solid --color-primary fill (KnowledgeBasePage "Import Runbook" button)', () => {
    // text-text-primary (#f8fafc) on --color-primary is provably infeasible
    // to bring above 4.5:1 simultaneously with the direct-text-on-surface
    // requirement above (lightening primary to satisfy the latter moves the
    // former further from 4.5:1, not closer — see tokens.css's Task 6.0
    // comment) — --color-on-primary is a dedicated dark foreground for this
    // one pairing instead.
    it('resting: on-primary vs primary >= 4.5:1', () => {
      expect(contrastRatio(onPrimary, primary)).toBeGreaterThanOrEqual(WCAG_AA_SMALL_TEXT)
    })
    it('hover: on-primary vs primary-hover >= 4.5:1 (button darkens on hover, contrast must not regress)', () => {
      expect(contrastRatio(onPrimary, primaryHover)).toBeGreaterThanOrEqual(WCAG_AA_SMALL_TEXT)
    })
  })

  describe('translucent badge tints — real call sites that still use bg-{token}/NN over a real surface', () => {
    it('StatusGroupFilter selected tab: primary text on bg-primary/10 over surface-base >= 4.5:1', () => {
      const blended = alphaBlend(primary, 0.1, surfaces['surface-base'])
      expect(contrastRatio(primary, blended)).toBeGreaterThanOrEqual(WCAG_AA_SMALL_TEXT)
    })
    it('SpendingPage EnforcementBadge: status-critical text on bg-status-critical/15 over surface-raised >= 4.5:1', () => {
      const blended = alphaBlend(statusCritical, 0.15, surfaces['surface-raised'])
      expect(contrastRatio(statusCritical, blended)).toBeGreaterThanOrEqual(WCAG_AA_SMALL_TEXT)
    })
  })

  describe('regression guard: previously-failing ratios (pre-Task-6.0 values) are provably below 4.5:1', () => {
    // Sanity check on the calculator itself, using the OLD hex values from
    // the Task 5.5 audit table (e2e/a11y.spec.ts's now-removed disable
    // comment) — if this ever passed, the math above would be suspect.
    it('old primary #6366f1 fails vs surface-overlay', () => {
      expect(contrastRatio('#6366f1', surfaces['surface-overlay'])).toBeLessThan(WCAG_AA_SMALL_TEXT)
    })
    it('old text-muted #64748b fails vs surface-overlay', () => {
      expect(contrastRatio('#64748b', surfaces['surface-overlay'])).toBeLessThan(WCAG_AA_SMALL_TEXT)
    })
    it('old status-critical #ef4444 fails vs surface-overlay', () => {
      expect(contrastRatio('#ef4444', surfaces['surface-overlay'])).toBeLessThan(WCAG_AA_SMALL_TEXT)
    })
  })
})
