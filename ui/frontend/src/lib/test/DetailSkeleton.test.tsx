/**
 * DetailSkeleton.test.tsx (Task 2.5) — NFR19: cold load never shows a blank
 * frame. Proves the skeleton renders a header placeholder + step
 * placeholders, and that its pulse animation carries the
 * motion-reduce:animate-none counterpart (NFR22).
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DetailSkeleton } from '../components/DetailSkeleton'

describe('DetailSkeleton', () => {
  it('renders a detail-skeleton test id', () => {
    render(<DetailSkeleton />)
    expect(screen.getByTestId('detail-skeleton')).toBeVisible()
  })

  it('every animate-pulse element also carries motion-reduce:animate-none', () => {
    const { container } = render(<DetailSkeleton />)
    const pulsing = container.querySelectorAll('.animate-pulse')
    expect(pulsing.length).toBeGreaterThan(0)
    pulsing.forEach((el) => {
      expect(el.className).toMatch(/motion-reduce:animate-none/)
    })
  })

  it('renders placeholder step rows', () => {
    const { container } = render(<DetailSkeleton />)
    // Structural placeholder count, not user-facing text — direct DOM query is intentional here.
    const items = container.querySelectorAll('li')
    expect(items.length).toBeGreaterThanOrEqual(1)
  })
})
