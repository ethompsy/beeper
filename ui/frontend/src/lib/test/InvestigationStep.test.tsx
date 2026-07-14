import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { InvestigationStep } from '../components/InvestigationStep'

/**
 * D2 (density audit §15, user-approved 2026-07-13): summary-type steps carry
 * NO evidence-type badge — per the approved glossary, the summary IS the
 * content and a "Summary" label above it is redundant chrome. Every other
 * step type keeps its badge.
 */
describe('InvestigationStep — type badge (D2)', () => {
  it('renders the evidence-type badge for non-summary steps', () => {
    render(
      <ul>
        <InvestigationStep type="metric" order={1} description="cpu_usage = 94.2%" />
      </ul>,
    )
    expect(screen.getByText('Metric Query')).toBeInTheDocument()
  })

  it('renders NO type badge for summary steps (D2: the summary is the content)', () => {
    render(
      <ul>
        <InvestigationStep type="summary" order={7} description="Root cause: payment gateway 5xx" />
      </ul>,
    )
    expect(screen.queryByText('Summary')).not.toBeInTheDocument()
    // The step itself still renders — only the badge is suppressed.
    expect(screen.getByText('Root cause: payment gateway 5xx')).toBeInTheDocument()
  })
})
