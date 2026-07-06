/**
 * StepEvidence.test.tsx (Task 2.5) — FR25 inline evidence rendering:
 * metric values in <code class="font-mono">, log excerpts in
 * <pre class="font-mono ... max-h-32">, per the spec's "Evidence rendering" rule.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StepEvidence } from '../components/StepEvidence'

describe('StepEvidence', () => {
  it('renders a metric value in a <code> element with font-mono styling', () => {
    render(
      <StepEvidence
        evidence={[{ kind: 'metric', query: 'http_request_duration_seconds', value: '1.2s' }]}
      />,
    )
    const code = screen.getByText(/http_request_duration_seconds.*1\.2s/)
    expect(code.tagName).toBe('CODE')
    expect(code.className).toMatch(/font-mono/)
  })

  it('renders a log excerpt in a <pre> element with font-mono + overflow-x-auto + max-h-32', () => {
    render(
      <StepEvidence
        evidence={[
          { kind: 'log', query: '{service="checkout"}', excerpt: 'ERROR connection timeout' },
        ]}
      />,
    )
    const pre = screen.getByText('ERROR connection timeout')
    expect(pre.tagName).toBe('PRE')
    expect(pre.className).toMatch(/font-mono/)
    expect(pre.className).toMatch(/overflow-x-auto/)
    expect(pre.className).toMatch(/max-h-32/)
  })

  it('renders nothing for an empty evidence array', () => {
    const { container } = render(<StepEvidence evidence={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders multiple evidence values in order', () => {
    render(
      <StepEvidence
        evidence={[
          { kind: 'metric', query: 'q1', value: 'v1' },
          { kind: 'log', query: 'q2', excerpt: 'v2' },
        ]}
      />,
    )
    const list = screen.getByText(/q1.*v1/).parentElement
    expect(list?.textContent).toMatch(/q1.*v1.*v2/s)
  })
})
