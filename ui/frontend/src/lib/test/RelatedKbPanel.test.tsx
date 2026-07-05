/**
 * RelatedKbPanel.test.tsx (Task 2.5) — the `className` prop Task 2.5 added
 * so the detail view can wire the anchored-bottom-bar (>=1200px) vs.
 * inline-below-content (<1200px) responsive behavior (FR26) without this
 * primitive knowing about breakpoints itself.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RelatedKbPanel } from '../components/RelatedKbPanel'

describe('RelatedKbPanel', () => {
  it('merges a caller-provided className onto the root alongside its own token classes', () => {
    render(
      <RelatedKbPanel state="populated" entryCount={2} className="fixed inset-x-0 bottom-0 z-10" />,
    )
    const root = screen.getByText('2 Related KB Entries').closest('[data-slot="related-kb-panel"]')
    expect(root?.className).toMatch(/fixed/)
    expect(root?.className).toMatch(/inset-x-0/)
    expect(root?.className).toMatch(/bottom-0/)
    // Original token classes are preserved (not clobbered by the merge).
    expect(root?.className).toMatch(/bg-surface-raised/)
  })

  it('renders "0 Related KB Entries" when entryCount is 0 (no error text)', () => {
    render(<RelatedKbPanel state="populated" entryCount={0} onExpandedChange={vi.fn()} />)
    expect(screen.getByText('0 Related KB Entries')).toBeVisible()
    expect(screen.queryByText(/error/i)).not.toBeInTheDocument()
  })

  it('renders the loading label distinctly from the zero-entries label', () => {
    render(<RelatedKbPanel state="loading" entryCount={0} />)
    expect(screen.getByText('Checking knowledge base...')).toBeVisible()
    expect(screen.queryByText('0 Related KB Entries')).not.toBeInTheDocument()
  })
})
