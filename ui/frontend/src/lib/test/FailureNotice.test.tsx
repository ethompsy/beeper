/**
 * FailureNotice.test.tsx (Task 2.5) — FR23: a Failed investigation renders
 * a visually distinct failure notice (role="alert", critical-status
 * accent), never a conclusion block.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FailureNotice } from '../components/FailureNotice'

describe('FailureNotice', () => {
  it('renders as an alert with the "Analysis Failed" label', () => {
    render(<FailureNotice />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Analysis Failed')
    expect(alert.className).toMatch(/status-critical/)
  })

  it('renders a default message when none is provided', () => {
    render(<FailureNotice />)
    expect(screen.getByText(/could not be completed/i)).toBeVisible()
  })

  it('renders a custom message when provided', () => {
    render(<FailureNotice message="Investigator pod crashed" />)
    expect(screen.getByText('Investigator pod crashed')).toBeVisible()
  })
})
