/**
 * sidebar-reduced-motion.test.tsx
 *
 * AC [T] (Task 2.1) — sidebar transitions honor `prefers-reduced-motion`
 * (0ms under reduce; the 200ms `--duration-sidebar` token otherwise).
 *
 * Mirrors the established project pattern (see `token-resolution.test.tsx`'s
 * "motion group" + `tokens.css`'s NFR22 doc comment): the *mechanism* is the
 * global `@media (prefers-reduced-motion: reduce)` override in tokens.css
 * that forces `transition-duration: 0ms !important`, PLUS the component
 * carrying `motion-reduce:transition-none` directly. This test proves both
 * halves for the sidebar/content-area specifically (not just the
 * TokenSwatch demo element already covered by Task 1.2's tests).
 */
import { describe, it, expect, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { render, screen } from '@testing-library/react'
import { Sidebar } from '../components/Sidebar'
import { AppShell } from '../components/AppShell'
import type { SidebarGroupData } from '../components/Sidebar'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const tokensSource = readFileSync(resolve(__dirname, '../../theme/tokens.css'), 'utf-8')

const GROUPS: SidebarGroupData[] = [
  {
    id: 'observe',
    label: 'Observe',
    items: [{ id: 'investigations', label: 'Investigations', href: '/investigations' }],
  },
]

describe('sidebar reduced-motion (NFR22 / FR51)', () => {
  it('tokens.css defines the sidebar transition at the 200ms duration token', () => {
    expect(tokensSource).toMatch(/--duration-sidebar:\s*200ms/)
    expect(tokensSource).toMatch(
      /--transition-sidebar:\s*width var\(--duration-sidebar\)[\s\S]*margin-left var\(--duration-sidebar\)/,
    )
  })

  it('tokens.css forces 0ms transitions globally under prefers-reduced-motion: reduce', () => {
    expect(tokensSource).toMatch(/prefers-reduced-motion:\s*reduce/)
    expect(tokensSource).toMatch(/transition-duration:\s*0ms\s*!important/)
  })

  it('Sidebar carries transition-sidebar and motion-reduce:transition-none together', () => {
    render(<Sidebar groups={GROUPS} expanded activeItemId="investigations" />)
    const nav = screen.getByRole('navigation', { name: 'Main navigation' })
    expect(nav.className).toContain('transition-sidebar')
    expect(nav.className).toContain('motion-reduce:transition-none')
  })

  it('AppShell content-area carries transition-sidebar and motion-reduce:transition-none together', () => {
    render(
      <AppShell groups={GROUPS} activeItemId="investigations" expanded onToggleSidebar={vi.fn()}>
        <p>content</p>
      </AppShell>,
    )
    const main = document.querySelector('[data-slot="content-area"]')
    expect(main?.className).toContain('transition-sidebar')
    expect(main?.className).toContain('motion-reduce:transition-none')
  })
})
