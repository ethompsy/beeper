/**
 * Sidebar.test.tsx
 *
 * AC [T] (Task 2.1) — collapsed sidebar = a 64px icon rail with per-group
 * tooltips; expanded = 256px with full group/item labels.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Sidebar, type SidebarGroupData } from '../components/Sidebar'

const GROUPS: SidebarGroupData[] = [
  {
    id: 'observe',
    label: 'Observe',
    items: [
      { id: 'investigations', label: 'Investigations', href: '/investigations' },
      { id: 'sources', label: 'Sources', href: '/sources' },
      { id: 'ingestion-stats', label: 'Ingestion Stats', href: '/ingestion-stats' },
    ],
  },
  {
    id: 'learn',
    label: 'Learn',
    items: [
      { id: 'knowledge-base', label: 'Knowledge Base', href: '/knowledge-base' },
      { id: 'metrics', label: 'Metrics', href: '/metrics' },
    ],
  },
  {
    id: 'manage',
    label: 'Manage',
    items: [{ id: 'spending', label: 'Spending', href: '/spending' }],
  },
]

describe('Sidebar', () => {
  describe('group ordering (Observe first, Investigations first item)', () => {
    it('renders Observe/Learn/Manage in order with Investigations as the first Observe item', () => {
      render(<Sidebar groups={GROUPS} expanded activeItemId="investigations" />)
      const nav = screen.getByRole('navigation', { name: 'Main navigation' })
      const text = nav.textContent ?? ''
      const observeIdx = text.indexOf('Observe')
      const learnIdx = text.indexOf('Learn')
      const manageIdx = text.indexOf('Manage')
      const investigationsIdx = text.indexOf('Investigations')
      expect(observeIdx).toBeGreaterThanOrEqual(0)
      expect(observeIdx).toBeLessThan(learnIdx)
      expect(learnIdx).toBeLessThan(manageIdx)
      // "Investigations" (item) appears right after "Observe" (group label),
      // before "Sources"/"Ingestion Stats".
      expect(investigationsIdx).toBeGreaterThan(observeIdx)
      expect(investigationsIdx).toBeLessThan(text.indexOf('Sources'))
    })
  })

  describe('collapsed = 64px icon rail', () => {
    it('carries the w-16 (64px) collapsed-width token class', () => {
      render(<Sidebar groups={GROUPS} expanded={false} activeItemId="investigations" />)
      const nav = screen.getByRole('navigation', { name: 'Main navigation' })
      expect(nav).toHaveClass('w-16')
      expect(nav).not.toHaveClass('w-64')
    })

    it('renders one icon-only link per group (item labels visually hidden)', () => {
      render(<Sidebar groups={GROUPS} expanded={false} activeItemId="investigations" />)
      // Item-level labels ("Sources", "Knowledge Base", etc.) are not
      // rendered as visible list items in collapsed mode — only the group
      // trigger (sr-only label) exists.
      expect(screen.queryByText('Sources')).not.toBeInTheDocument()
      expect(screen.queryByText('Knowledge Base')).not.toBeInTheDocument()
      // Group labels are present as accessible (sr-only) text on the trigger.
      expect(screen.getByText('Observe')).toBeInTheDocument()
      expect(screen.getByText('Learn')).toBeInTheDocument()
      expect(screen.getByText('Manage')).toBeInTheDocument()
    })

    it('collapsed group link navigates to the first item in the group', () => {
      render(<Sidebar groups={GROUPS} expanded={false} activeItemId="investigations" />)
      const observeLink = screen.getByRole('link', { name: 'Observe' })
      expect(observeLink).toHaveAttribute('href', '/investigations')
    })

    it('shows a tooltip with the group label on hover (per-group tooltips)', async () => {
      const user = userEvent.setup()
      render(<Sidebar groups={GROUPS} expanded={false} activeItemId="investigations" />)

      const observeLink = screen.getByRole('link', { name: 'Observe' })
      await user.hover(observeLink)

      const tooltip = await screen.findByRole('tooltip', { name: 'Observe' })
      expect(tooltip).toBeInTheDocument()
    })

    it('marks the active group as the focus-return target (data-sidebar-nav-active)', () => {
      render(<Sidebar groups={GROUPS} expanded={false} activeItemId="investigations" />)
      const observeLink = screen.getByRole('link', { name: 'Observe' })
      expect(observeLink).toHaveAttribute('data-sidebar-nav-active', 'true')
    })
  })

  describe('expanded = 256px with full labels', () => {
    it('carries the w-64 (256px) expanded-width token class', () => {
      render(<Sidebar groups={GROUPS} expanded activeItemId="investigations" />)
      const nav = screen.getByRole('navigation', { name: 'Main navigation' })
      expect(nav).toHaveClass('w-64')
      expect(nav).not.toHaveClass('w-16')
    })

    it('renders full item labels for every group', () => {
      render(<Sidebar groups={GROUPS} expanded activeItemId="investigations" />)
      expect(screen.getByText('Sources')).toBeInTheDocument()
      expect(screen.getByText('Ingestion Stats')).toBeInTheDocument()
      expect(screen.getByText('Knowledge Base')).toBeInTheDocument()
      expect(screen.getByText('Metrics')).toBeInTheDocument()
      expect(screen.getByText('Spending')).toBeInTheDocument()
    })

    it('marks the active item with aria-current and the focus-return marker', () => {
      render(<Sidebar groups={GROUPS} expanded activeItemId="investigations" />)
      const activeLink = screen.getByRole('link', { name: 'Investigations' })
      expect(activeLink).toHaveAttribute('aria-current', 'page')
      expect(activeLink).toHaveAttribute('data-sidebar-nav-active', 'true')
    })
  })

  describe('overlay vs push (no width shift signaling)', () => {
    it('sets data-overlay="true" when isOverlay is passed', () => {
      render(<Sidebar groups={GROUPS} expanded isOverlay activeItemId="investigations" />)
      const nav = screen.getByRole('navigation', { name: 'Main navigation' })
      expect(nav).toHaveAttribute('data-overlay', 'true')
      expect(nav).toHaveClass('fixed')
    })

    it('does not render as a fixed overlay when pushing (isOverlay=false)', () => {
      render(<Sidebar groups={GROUPS} expanded isOverlay={false} activeItemId="investigations" />)
      const nav = screen.getByRole('navigation', { name: 'Main navigation' })
      expect(nav).toHaveAttribute('data-overlay', 'false')
    })
  })

  describe('reduced motion (NFR22 / FR51)', () => {
    it('carries motion-reduce:transition-none alongside the sidebar transition class', () => {
      render(<Sidebar groups={GROUPS} expanded activeItemId="investigations" />)
      const nav = screen.getByRole('navigation', { name: 'Main navigation' })
      expect(nav.className).toContain('motion-reduce:transition-none')
      expect(nav.className).toContain('transition-sidebar')
    })
  })
})
