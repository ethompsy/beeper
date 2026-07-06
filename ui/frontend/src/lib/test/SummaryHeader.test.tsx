/**
 * SummaryHeader.test.tsx (Task 2.5) — the `headingId` prop Task 2.5 added
 * so the view can carry `useRouteFocusManagement`'s
 * (`src/lib/hooks/useRouteFocusManagement.ts`) `#detail-summary-heading`
 * contract onto the actual `<h1>` (not the `<header>` wrapper, which
 * `...rest` still targets for any other passed-through attribute).
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SummaryHeader } from '../components/SummaryHeader'

describe('SummaryHeader', () => {
  it('sets the id + tabIndex=-1 on the <h1> when headingId is provided', () => {
    render(
      <SummaryHeader
        headingId="detail-summary-heading"
        serviceName="checkout-service"
        severity="High"
        signalCount={3}
        statusVariant="investigating"
      />,
    )
    const heading = screen.getByRole('heading', { name: 'checkout-service' })
    expect(heading).toHaveAttribute('id', 'detail-summary-heading')
    expect(heading).toHaveAttribute('tabindex', '-1')
  })

  it('does not set an id or tabIndex on the <h1> when headingId is omitted', () => {
    render(
      <SummaryHeader
        serviceName="checkout-service"
        severity="High"
        signalCount={3}
        statusVariant="investigating"
      />,
    )
    const heading = screen.getByRole('heading', { name: 'checkout-service' })
    expect(heading).not.toHaveAttribute('id')
    expect(heading).not.toHaveAttribute('tabindex')
  })

  it('still applies other HTML attributes (via ...rest) to the <header> wrapper, not the <h1>', () => {
    render(
      <SummaryHeader
        data-testid="summary-header-root"
        headingId="detail-summary-heading"
        serviceName="checkout-service"
        severity="High"
        signalCount={3}
        statusVariant="investigating"
      />,
    )
    const root = screen.getByTestId('summary-header-root')
    expect(root.tagName).toBe('HEADER')
    const heading = screen.getByRole('heading', { name: 'checkout-service' })
    expect(heading).not.toBe(root)
  })
})
