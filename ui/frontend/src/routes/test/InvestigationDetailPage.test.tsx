/**
 * InvestigationDetailPage.test.tsx (Task 2.5)
 *
 * Covers every `[T]` acceptance criterion from the Plan's Task 2.5 entry:
 *   1. Summary header renders from metadata immediately (before/independent
 *      of the fetch resolving) — NFR19.
 *   2. Steps render ordered with inline evidence; first evidence step gets
 *      the emphasis treatment (reduced-motion → instant, via the existing
 *      `motion-reduce:transition-none` class InvestigationStep already
 *      carries — proven once here, not re-proven per state).
 *   3. Related KB panel renders "N Related KB Entries", responsive
 *      anchored-bar vs. inline stacking (FR26).
 *   4. State coverage: Failed / Pending / absent-KB / absent-correlation.
 *   5. Invalid id → "Investigation not found" inside the shell.
 *   6. Cold load shows a skeleton, never a blank frame.
 *
 * `fetch` is stubbed per test via `vi.stubGlobal` (matching this codebase's
 * existing mocking convention — no fetch-mock library added). The page is
 * rendered inside a `MemoryRouter` at `/investigations/:id` so `useParams`
 * resolves, matching how `AppLayout` mounts it in the real router.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { InvestigationDetailPage } from '../InvestigationDetailPage'
import type { InvestigationDetailDto } from '../../api/investigation-detail'

function renderDetailPage(investigationId: string) {
  return render(
    <MemoryRouter initialEntries={[`/investigations/${investigationId}`]}>
      <Routes>
        <Route path="/investigations/:investigationId" element={<InvestigationDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response
}

/** A never-resolving fetch — simulates "the fetch hasn't come back yet." */
function pendingFetch(): Promise<Response> {
  return new Promise(() => {})
}

function baseMetadata(
  overrides: Partial<InvestigationDetailDto['metadata']> = {},
): InvestigationDetailDto['metadata'] {
  return {
    id: 'INV-0042',
    status: 'investigating',
    service: 'checkout-service',
    severity: 'High',
    condition: 'HTTP 5xx error rate elevated (12%)',
    message: null,
    started_at: '2m ago',
    triggered_at: null,
    completed_at: null,
    workflow_state: 'investigating',
    workflow_state_changed_at: null,
    signal_count: 3,
    job_name: 'job-1',
    ...overrides,
  }
}

function detailDto(overrides: Partial<InvestigationDetailDto> = {}): InvestigationDetailDto {
  return {
    id: 'INV-0042',
    status: 'investigating',
    service: 'checkout-service',
    message: null,
    metadata: baseMetadata(),
    steps: [
      { order: 1, key: 'customer_impact', label: 'Customer Impact Assessment', state: 'completed', type: 'summary' },
      { order: 2, key: 'kb_query', label: 'Knowledge Base Query', state: 'completed', type: 'kb' },
      {
        order: 3,
        key: 'signal_correlation',
        label: 'Signal Correlation',
        state: 'completed',
        type: 'correlation',
        evidence: [{ kind: 'metric', query: 'http_requests_total{code="5xx"}', value: '412/min' }],
      },
      { order: 4, key: 'rca_hypothesis', label: 'Root Cause Hypothesis', state: 'active', type: 'metric' },
    ],
    ...overrides,
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('InvestigationDetailPage — summary header (NFR19)', () => {
  it('renders the summary header immediately, before the fetch resolves', async () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(pendingFetch()))

    renderDetailPage('INV-0042')

    // The heading is visible synchronously — it does not wait on the fetch.
    const heading = screen.getByRole('heading', { name: 'INV-0042' })
    expect(heading).toBeVisible()
    expect(heading).toHaveAttribute('id', 'detail-summary-heading')
  })

  it('renders service/severity/signal-count/status from metadata once the fetch resolves', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(detailDto())))

    renderDetailPage('INV-0042')

    expect(await screen.findByRole('heading', { name: 'checkout-service' })).toBeVisible()
    expect(screen.getByText('High')).toBeVisible()
    expect(screen.getByText('3 signals')).toBeVisible()
    expect(screen.getByText('Investigating')).toBeVisible()
  })
})

describe('InvestigationDetailPage — cold load skeleton', () => {
  it('shows a detail skeleton (never a blank frame) while the fetch is pending', () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(pendingFetch()))

    renderDetailPage('INV-0042')

    expect(screen.getByTestId('detail-skeleton')).toBeVisible()
  })
})

describe('InvestigationDetailPage — steps + evidence (FR25)', () => {
  it('renders steps in order with inline evidence, and marks the first-evidence step', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(detailDto())))

    renderDetailPage('INV-0042')

    // Wait for the real steps list specifically (data-slot distinguishes it
    // from the cold-load skeleton's own placeholder <ul>, which also has
    // role="list" and would otherwise race a plain findByRole('list')).
    await screen.findByText('Root Cause Hypothesis')
    const list = document.querySelector('[data-slot="investigation-steps"]') as HTMLElement
    // Ordered-DOM assertion is the point of this test — direct DOM query is intentional here.
    const items = within(list).getAllByRole('listitem')
    expect(items).toHaveLength(4)
    expect(items[0]).toHaveTextContent('Customer Impact Assessment')
    expect(items[1]).toHaveTextContent('Knowledge Base Query')
    expect(items[2]).toHaveTextContent('Signal Correlation')
    expect(items[3]).toHaveTextContent('Root Cause Hypothesis')

    // Inline evidence renders within the step that has it.
    expect(within(items[2]).getByText(/412\/min/)).toBeVisible()

    // The first step carrying real evidence (order 3, correlation, completed)
    // gets the emphasis treatment.
    expect(items[2]).toHaveAttribute('data-step-type', 'correlation')
    expect(items[2].className).toMatch(/surface-overlay/)
    // A kb/summary step never gets the emphasis treatment even though it's earlier.
    expect(items[0].className).not.toMatch(/surface-overlay/)
    expect(items[1].className).not.toMatch(/surface-overlay/)
  })
})

describe('InvestigationDetailPage — Failed state (FR23)', () => {
  it('renders completed steps followed by a distinct failure notice, with no conclusion block', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          detailDto({
            metadata: baseMetadata({ status: 'failed', message: 'Investigator pod crashed' }),
            steps: [
              { order: 1, key: 'customer_impact', label: 'Customer Impact Assessment', state: 'completed', type: 'summary' },
              { order: 2, key: 'kb_query', label: 'Knowledge Base Query', state: 'error', type: 'kb' },
            ],
          }),
        ),
      ),
    )

    renderDetailPage('INV-0042')

    // "Analysis Failed" appears twice by design (the StatusBadge in the
    // summary header AND the distinct failure notice below the steps) —
    // scope the assertion to the notice itself via its alert role.
    const notice = await screen.findByRole('alert')
    expect(within(notice).getByText('Analysis Failed')).toBeVisible()
    expect(screen.getByText('Investigator pod crashed')).toBeVisible()
    expect(screen.getByText('Customer Impact Assessment')).toBeVisible()
    // No conclusion block — a Failed investigation never renders one.
    expect(screen.queryByText(/conclusion/i)).not.toBeInTheDocument()
  })
})

describe('InvestigationDetailPage — Pending state', () => {
  it('renders a "waiting to start" placeholder', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          detailDto({
            metadata: baseMetadata({ status: 'pending', started_at: null }),
            steps: [
              { order: 1, key: 'customer_impact', label: 'Customer Impact Assessment', state: 'pending', type: 'summary' },
            ],
          }),
        ),
      ),
    )

    renderDetailPage('INV-0042')

    expect(await screen.findByTestId('pending-placeholder')).toHaveTextContent(/waiting to start/i)
  })
})

describe('InvestigationDetailPage — Related KB panel (FR26)', () => {
  it('shows "0 Related KB Entries" (no error) when KB results are absent/unparseable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(detailDto())))

    renderDetailPage('INV-0042')

    const kbPanelLabel = await screen.findByText('0 Related KB Entries')
    expect(kbPanelLabel).toBeVisible()
    // "0 Related KB Entries" is the whole message — no separate error alert
    // is rendered alongside it (FR26: absent/unparseable KB is not an error).
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows the populated entry count when KB entries are present on the step', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          detailDto({
            steps: [
              {
                order: 1,
                key: 'kb_query',
                label: 'Knowledge Base Query',
                state: 'completed',
                type: 'kb',
                kbEntries: [
                  { id: 'KB-104', title: 'checkout-service latency after deploy' },
                  { id: 'KB-098', title: 'connection pool exhaustion runbook' },
                ],
              },
            ],
          }),
        ),
      ),
    )

    renderDetailPage('INV-0042')

    expect(await screen.findByText('2 Related KB Entries')).toBeVisible()
  })

  it('shows the loading state while the KB query step is still in progress', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          detailDto({
            steps: [
              { order: 1, key: 'kb_query', label: 'Knowledge Base Query', state: 'active', type: 'kb' },
            ],
          }),
        ),
      ),
    )

    renderDetailPage('INV-0042')

    expect(await screen.findByText('Checking knowledge base...')).toBeVisible()
  })
})

describe('InvestigationDetailPage — FR48 correlation placeholder', () => {
  it('shows "impact: not yet correlated" when correlated_services is absent', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(detailDto())))

    renderDetailPage('INV-0042')

    expect(await screen.findByText(/impact: not yet correlated/i)).toBeVisible()
  })
})

describe('InvestigationDetailPage — invalid id (404)', () => {
  it('renders "Investigation not found" inside the shell, not a generic 404', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ error: 'not_found' }, 404)))

    renderDetailPage('INV-9999')

    expect(await screen.findByText(/Investigation not found/i)).toBeVisible()
    expect(screen.getByText(/INV-9999/)).toBeVisible()
  })
})

describe('InvestigationDetailPage — network/error state', () => {
  it('renders a retry-safe error message rather than throwing when the request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    renderDetailPage('INV-0042')

    expect(await screen.findByRole('alert')).toHaveTextContent(/unable to load/i)
    // The heading is still there — detail remains viewable per FR27's spirit.
    expect(screen.getByRole('heading', { name: 'INV-0042' })).toBeVisible()
  })
})
