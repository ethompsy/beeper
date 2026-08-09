/**
 * OriginBadge.test.tsx (Task 8.7 — ADR 0002 §6, FR60).
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { OriginBadge } from '../components/OriginBadge'

describe('OriginBadge', () => {
  it('renders "Local" for origin="local"', () => {
    render(<OriginBadge origin="local" />)
    expect(screen.getByText('Local')).toBeInTheDocument()
  })

  it('renders "SCIM" for origin="scim"', () => {
    render(<OriginBadge origin="scim" />)
    expect(screen.getByText('SCIM')).toBeInTheDocument()
  })

  it('exposes data-origin for styling/testing hooks', () => {
    render(<OriginBadge origin="scim" />)
    expect(screen.getByText('SCIM')).toHaveAttribute('data-origin', 'scim')
  })

  it('merges an external className', () => {
    render(<OriginBadge origin="local" className="ml-2" />)
    expect(screen.getByText('Local')).toHaveClass('ml-2')
  })
})
