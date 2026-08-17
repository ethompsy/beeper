/**
 * token-resolution.test.tsx
 *
 * AC [T] #1 — Tailwind theme exposes the dark-first tokens and a sample
 * component resolves them.
 *
 * Strategy: two complementary assertions.
 *
 * 1. CLASS PRESENCE (RTL + jsdom): render TokenSwatch and assert every element
 *    carries the expected Tailwind token class. This proves the component
 *    correctly consumes the design-system token API (bg-surface-base,
 *    text-primary, etc.) — not hardcoded values.
 *
 * 2. CSS VARIABLE PRESENCE (static source): parse the tokens.css file and
 *    assert every required design-system variable is declared with the exact
 *    authoritative hex value from the spec. This is the source-of-truth check:
 *    if a value drifts, the test fails before any component even uses it.
 *
 * Together these prove: (a) the token layer is correctly defined, and
 * (b) components consume the token layer rather than bypassing it.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { TokenSwatch } from '../components/TokenSwatch'

// ─────────────────────────────────────────────────────────────────────────────
// 2. CSS variable presence — parse tokens.css for exact hex values
// ─────────────────────────────────────────────────────────────────────────────

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const tokensPath = resolve(__dirname, '../theme/tokens.css')
const tokensSource = readFileSync(tokensPath, 'utf-8')

/** Pull the first value assigned to a CSS custom property from source text. */
function getTokenValue(source: string, property: string): string | null {
  // Match: --property-name: <value>; (value may be multi-word, no semicolon)
  const re = new RegExp(`${property.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*:\\s*([^;\\n]+)`)
  const m = source.match(re)
  return m ? m[1].trim() : null
}

describe('design-system token CSS variables', () => {
  describe('surface colors', () => {
    it('surface-base is #0f0f1a', () => {
      expect(getTokenValue(tokensSource, '--color-surface-base')).toBe('#0f0f1a')
    })
    it('surface-raised is #1a1a2e', () => {
      expect(getTokenValue(tokensSource, '--color-surface-raised')).toBe('#1a1a2e')
    })
    it('surface-overlay is #252540', () => {
      expect(getTokenValue(tokensSource, '--color-surface-overlay')).toBe('#252540')
    })
  })

  describe('brand / interactive colors', () => {
    // Task 6.0 (WCAG AA color-contrast fix, Q10): #6366f1 -> #8284f4, see
    // src/test/contrast.test.ts for the derived-ratio proof.
    it('primary is #8284f4', () => {
      expect(getTokenValue(tokensSource, '--color-primary')).toBe('#8284f4')
    })
    it('primary-hover is #818cf8', () => {
      expect(getTokenValue(tokensSource, '--color-primary-hover')).toBe('#818cf8')
    })
    it('on-primary is #0f0f1a', () => {
      expect(getTokenValue(tokensSource, '--color-on-primary')).toBe('#0f0f1a')
    })
  })

  describe('status colors', () => {
    it('status-healthy is #22c55e', () => {
      expect(getTokenValue(tokensSource, '--color-status-healthy')).toBe('#22c55e')
    })
    it('status-warning is #f59e0b', () => {
      expect(getTokenValue(tokensSource, '--color-status-warning')).toBe('#f59e0b')
    })
    // Task 6.0: #ef4444 -> #f37373, see src/test/contrast.test.ts.
    it('status-critical is #f37373', () => {
      expect(getTokenValue(tokensSource, '--color-status-critical')).toBe('#f37373')
    })
    // Task 6.0: #6b7280 -> #989ea9, see src/test/contrast.test.ts.
    it('status-muted is #989ea9', () => {
      expect(getTokenValue(tokensSource, '--color-status-muted')).toBe('#989ea9')
    })
  })

  describe('text colors', () => {
    it('text-primary is #f8fafc', () => {
      expect(getTokenValue(tokensSource, '--color-text-primary')).toBe('#f8fafc')
    })
    it('text-secondary is #94a3b8', () => {
      expect(getTokenValue(tokensSource, '--color-text-secondary')).toBe('#94a3b8')
    })
    // Task 6.0: #64748b -> #8391a6, see src/test/contrast.test.ts.
    it('text-muted is #8391a6', () => {
      expect(getTokenValue(tokensSource, '--color-text-muted')).toBe('#8391a6')
    })
  })

  describe('spacing tokens', () => {
    it('space-12 (topbar height) is 48px', () => {
      expect(getTokenValue(tokensSource, '--spacing-12')).toBe('48px')
    })
    it('space-16 (sidebar-collapsed) is 64px', () => {
      expect(getTokenValue(tokensSource, '--spacing-16')).toBe('64px')
    })
    it('space-64 (sidebar-expanded) is 256px', () => {
      expect(getTokenValue(tokensSource, '--spacing-64')).toBe('256px')
    })
  })

  describe('layout tokens', () => {
    it('sidebar-collapsed width is 64px', () => {
      expect(getTokenValue(tokensSource, '--width-sidebar-collapsed')).toBe('64px')
    })
    it('sidebar-expanded width is 256px', () => {
      expect(getTokenValue(tokensSource, '--width-sidebar-expanded')).toBe('256px')
    })
    it('topbar height is 48px', () => {
      expect(getTokenValue(tokensSource, '--height-topbar')).toBe('48px')
    })
  })

  describe('breakpoints', () => {
    it('sm breakpoint is 768px', () => {
      expect(getTokenValue(tokensSource, '--breakpoint-sm')).toBe('768px')
    })
    it('lg breakpoint is 1200px', () => {
      expect(getTokenValue(tokensSource, '--breakpoint-lg')).toBe('1200px')
    })
  })

  describe('motion tokens', () => {
    it('sidebar transition duration is 200ms', () => {
      expect(getTokenValue(tokensSource, '--duration-sidebar')).toBe('200ms')
    })
    it('highlight fade duration is 5000ms', () => {
      expect(getTokenValue(tokensSource, '--duration-highlight')).toBe('5000ms')
    })
    it('emphasis (trust-ignition) duration is 2000ms', () => {
      expect(getTokenValue(tokensSource, '--duration-emphasis')).toBe('2000ms')
    })
    it('sidebar transition easing is ease-in-out', () => {
      expect(getTokenValue(tokensSource, '--ease-sidebar')).toBe('ease-in-out')
    })
  })

  describe('typography tokens', () => {
    it('sans font stack starts with system-ui', () => {
      const val = getTokenValue(tokensSource, '--font-sans') ?? ''
      expect(val).toMatch(/^system-ui/)
    })
    it('mono font stack starts with ui-monospace', () => {
      const val = getTokenValue(tokensSource, '--font-mono') ?? ''
      expect(val).toMatch(/^ui-monospace/)
    })
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 1. Class-presence tests — RTL renders confirm token classes are applied
// ─────────────────────────────────────────────────────────────────────────────

describe('TokenSwatch component consumes token classes', () => {
  describe('surfaces group', () => {
    it('surface-base element carries bg-surface-base class', () => {
      render(<TokenSwatch group="surfaces" />)
      const el = screen.getByTestId('surface-base')
      expect(el).toHaveClass('bg-surface-base')
    })

    it('surface-raised element carries bg-surface-raised class', () => {
      render(<TokenSwatch group="surfaces" />)
      const el = screen.getByTestId('surface-raised')
      expect(el).toHaveClass('bg-surface-raised')
    })

    it('surface-overlay element carries bg-surface-overlay class', () => {
      render(<TokenSwatch group="surfaces" />)
      const el = screen.getByTestId('surface-overlay')
      expect(el).toHaveClass('bg-surface-overlay')
    })
  })

  describe('text group', () => {
    it('primary text element carries text-text-primary class', () => {
      render(<TokenSwatch group="text" />)
      const el = screen.getByTestId('text-primary')
      expect(el).toHaveClass('text-text-primary')
    })

    it('secondary text element carries text-text-secondary class', () => {
      render(<TokenSwatch group="text" />)
      const el = screen.getByTestId('text-secondary')
      expect(el).toHaveClass('text-text-secondary')
    })

    it('muted text element carries text-text-muted class', () => {
      render(<TokenSwatch group="text" />)
      const el = screen.getByTestId('text-muted')
      expect(el).toHaveClass('text-text-muted')
    })

    it('brand primary element carries text-primary class', () => {
      render(<TokenSwatch group="text" />)
      const el = screen.getByTestId('text-brand')
      expect(el).toHaveClass('text-primary')
    })
  })

  describe('status group', () => {
    it('healthy element carries text-status-healthy class', () => {
      render(<TokenSwatch group="status" />)
      expect(screen.getByTestId('status-healthy')).toHaveClass('text-status-healthy')
    })

    it('warning element carries text-status-warning class', () => {
      render(<TokenSwatch group="status" />)
      expect(screen.getByTestId('status-warning')).toHaveClass('text-status-warning')
    })

    it('critical element carries text-status-critical class', () => {
      render(<TokenSwatch group="status" />)
      expect(screen.getByTestId('status-critical')).toHaveClass('text-status-critical')
    })

    it('muted element carries text-status-muted class', () => {
      render(<TokenSwatch group="status" />)
      expect(screen.getByTestId('status-muted')).toHaveClass('text-status-muted')
    })
  })

  describe('motion group', () => {
    it('motion element carries motion-reduce:transition-none (NFR22 / FR51)', () => {
      render(<TokenSwatch group="motion" />)
      const el = screen.getByTestId('swatch-motion')
      // The class list includes the motion-reduce variant class
      expect(el.className).toContain('motion-reduce:transition-none')
    })

    it('motion element carries a transition class alongside the motion-reduce guard', () => {
      render(<TokenSwatch group="motion" />)
      const el = screen.getByTestId('swatch-motion')
      expect(el.className).toContain('transition-')
    })
  })
})
