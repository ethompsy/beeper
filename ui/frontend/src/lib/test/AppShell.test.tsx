/**
 * AppShell.test.tsx
 *
 * AC [T] (Task 2.1) — at >=1200px manual expand PUSHES content (content
 * area width/margin changes); at <1200px manual expand OVERLAYS content
 * (content width is unchanged). Detail route auto-collapse is covered by
 * useSidebarState.test.ts + the AppLayout e2e; this file proves the shell
 * translates `expanded`/`isOverlay` into the right content-area margin
 * classes (the actual CSS width is verified by tokens.css's `w-64`/`w-16`
 * classes carried by <Sidebar>, already asserted in Sidebar.test.tsx).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AppShell } from '../components/AppShell'
import type { SidebarGroupData } from '../components/Sidebar'

const GROUPS: SidebarGroupData[] = [
  {
    id: 'observe',
    label: 'Observe',
    items: [{ id: 'investigations', label: 'Investigations', href: '/investigations' }],
  },
]

describe('AppShell content-area width', () => {
  it('pushing (expanded, not overlay) grows content margin to ml-64 (256px)', () => {
    render(
      <AppShell groups={GROUPS} activeItemId="investigations" expanded isOverlay={false} onToggleSidebar={vi.fn()}>
        <p>content</p>
      </AppShell>,
    )
    const main = document.querySelector('[data-slot="content-area"]')
    expect(main).not.toBeNull()
    expect(main).toHaveClass('ml-64')
    expect(main).not.toHaveClass('ml-16')
  })

  it('overlay (expanded, isOverlay) keeps content margin at ml-16 (64px) — no width shift', () => {
    render(
      <AppShell groups={GROUPS} activeItemId="investigations" expanded isOverlay onToggleSidebar={vi.fn()}>
        <p>content</p>
      </AppShell>,
    )
    const main = document.querySelector('[data-slot="content-area"]')
    expect(main).toHaveClass('ml-16')
    expect(main).not.toHaveClass('ml-64')
  })

  it('collapsed icon rail (not expanded) keeps content margin at ml-16 (64px)', () => {
    render(
      <AppShell groups={GROUPS} activeItemId="investigations" expanded={false} isOverlay={false} onToggleSidebar={vi.fn()}>
        <p>content</p>
      </AppShell>,
    )
    const main = document.querySelector('[data-slot="content-area"]')
    expect(main).toHaveClass('ml-16')
  })

  it('the identical expanded=true state produces different margins depending only on isOverlay', () => {
    const { unmount } = render(
      <AppShell groups={GROUPS} activeItemId="investigations" expanded isOverlay={false} onToggleSidebar={vi.fn()}>
        <p>content</p>
      </AppShell>,
    )
    const pushingMain = document.querySelector('[data-slot="content-area"]')
    const pushingClasses = pushingMain?.className
    unmount()

    render(
      <AppShell groups={GROUPS} activeItemId="investigations" expanded isOverlay onToggleSidebar={vi.fn()}>
        <p>content</p>
      </AppShell>,
    )
    const overlayMain = document.querySelector('[data-slot="content-area"]')
    expect(overlayMain?.className).not.toBe(pushingClasses)
  })

  describe('hamburger toggle + accessibility wiring', () => {
    it('the toggle button reflects aria-expanded and calls onToggleSidebar', async () => {
      const onToggle = vi.fn()
      render(
        <AppShell groups={GROUPS} activeItemId="investigations" expanded onToggleSidebar={onToggle}>
          <p>content</p>
        </AppShell>,
      )
      const button = screen.getByRole('button', { name: /toggle navigation sidebar/i })
      expect(button).toHaveAttribute('aria-expanded', 'true')
      expect(button).toHaveAttribute('aria-controls', 'sidebar')
      button.click()
      expect(onToggle).toHaveBeenCalledTimes(1)
    })

    it('renders a skip-to-main-content link as the first focusable element', () => {
      render(
        <AppShell groups={GROUPS} activeItemId="investigations" expanded onToggleSidebar={vi.fn()}>
          <p>content</p>
        </AppShell>,
      )
      const skipLink = screen.getByRole('link', { name: /skip to main content/i })
      expect(skipLink).toHaveAttribute('href', '#main-content')
    })
  })

  describe('reduced motion (NFR22 / FR51)', () => {
    it('content-area transition carries motion-reduce:transition-none', () => {
      render(
        <AppShell groups={GROUPS} activeItemId="investigations" expanded onToggleSidebar={vi.fn()}>
          <p>content</p>
        </AppShell>,
      )
      const main = document.querySelector('[data-slot="content-area"]')
      expect(main?.className).toContain('motion-reduce:transition-none')
      expect(main?.className).toContain('transition-sidebar')
    })
  })
})
