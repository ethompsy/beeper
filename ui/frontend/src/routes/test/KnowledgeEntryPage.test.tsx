/**
 * KnowledgeEntryPage.test.tsx (Task 5.1)
 *
 * Covers the [T] AC "Entry detail at parity":
 *  - cold load shows a detail skeleton, never a blank frame (NFR19)
 *  - renders title/type/service/meta/tags from the fetched entry
 *  - renders the FR31 "Incident Details" section (root cause, resolution,
 *    affected services, source/contributing investigation links) only when
 *    present — never an empty section
 *  - renders sanitized entry content
 *  - renders related entries when present
 *  - invalid entry id -> in-shell "not found" message (sidebar-compatible,
 *    not a bare 404)
 *  - network/error state renders a retry-safe message rather than throwing
 *
 * `fetch` is stubbed per test via `vi.stubGlobal`, matching
 * `InvestigationDetailPage.test.tsx`'s convention.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { KnowledgeEntryPage } from '../KnowledgeEntryPage'
import type { KnowledgeEntryDetailDto } from '../../api/knowledge-detail'

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response
}

function baseDto(overrides: Partial<KnowledgeEntryDetailDto> = {}): KnowledgeEntryDetailDto {
  return {
    entry: {
      id: 'point-1',
      entry_id: 'kb-001',
      entry_type: 'investigation',
      title: 'checkout-service latency after deploy',
      service: 'checkout-service',
      created_at: '2026-06-01T10:00:00+00:00',
      updated_at: '2026-06-01T10:05:00+00:00',
      author: 'beeper',
      version: 2,
      tags: ['deploy', 'latency'],
      validation_status: 'human-confirmed',
      auto_published: false,
      relevance_score: null,
      content_html: '<h2>Root cause</h2><p>Connection pool exhaustion.</p>',
      root_cause: null,
      resolution: null,
      affected_services: [],
    },
    related_entries: [],
    source_investigation: null,
    contributing_investigations: [],
    ...overrides,
  }
}

function renderEntryPage(entryId: string) {
  return render(
    <MemoryRouter initialEntries={[`/knowledge/${entryId}`]}>
      <Routes>
        <Route path="/knowledge/:entryId" element={<KnowledgeEntryPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('KnowledgeEntryPage — cold load skeleton (NFR19)', () => {
  it('shows a detail skeleton (never a blank frame) while the fetch is pending', () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))

    renderEntryPage('kb-001')

    expect(screen.getByTestId('detail-skeleton')).toBeVisible()
  })
})

describe('KnowledgeEntryPage — entry fields (FR31)', () => {
  it('renders title, entry type, service, author, version, and validation status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(baseDto())))

    renderEntryPage('kb-001')

    expect(await screen.findByText('checkout-service latency after deploy')).toBeVisible()
    expect(screen.getByText('Investigation')).toBeVisible()
    expect(screen.getByText('checkout-service')).toBeVisible()
    expect(screen.getByText('by beeper')).toBeVisible()
    expect(screen.getByText('v2')).toBeVisible()
    expect(screen.getByText('human-confirmed')).toBeVisible()
    expect(screen.getByText('deploy')).toBeVisible()
    expect(screen.getByText('latency')).toBeVisible()
  })

  it('renders the sanitized entry content', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(baseDto())))

    renderEntryPage('kb-001')

    const content = await screen.findByTestId('kb-entry-content')
    expect(content.innerHTML).toContain('<h2>Root cause</h2>')
    expect(content).toHaveTextContent('Connection pool exhaustion.')
  })

  it('renders no "Incident Details" section when no incident fields are present', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(baseDto())))

    renderEntryPage('kb-001')

    await screen.findByText('checkout-service latency after deploy')
    expect(screen.queryByText('Incident Details')).not.toBeInTheDocument()
  })
})

describe('KnowledgeEntryPage — Incident Details section (FR31 "past incident context")', () => {
  it('renders root cause, resolution, and affected services when present', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          baseDto({
            entry: {
              ...baseDto().entry,
              root_cause: 'Connection pool exhaustion',
              resolution: 'Increased pool size and added backpressure',
              affected_services: ['checkout-service', 'frontend'],
            },
          }),
        ),
      ),
    )

    renderEntryPage('kb-001')

    expect(await screen.findByText('Incident Details')).toBeVisible()
    expect(screen.getByText('Root Cause')).toBeVisible()
    expect(screen.getByText('Connection pool exhaustion')).toBeVisible()
    expect(screen.getByText('Resolution')).toBeVisible()
    expect(screen.getByText('Increased pool size and added backpressure')).toBeVisible()
    expect(screen.getByText('Affected Services')).toBeVisible()
    expect(screen.getByText('frontend')).toBeVisible()
  })

  it('renders the source investigation as a client-side link into /investigations/:id', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          baseDto({
            source_investigation: { investigation_id: 'inv-source-abc', relationship: 'source' },
          }),
        ),
      ),
    )

    renderEntryPage('kb-001')

    const link = await screen.findByRole('link', { name: 'inv-source-abc' })
    expect(link).toHaveAttribute('href', '/investigations/inv-source-abc')
    expect(screen.getByText('Source')).toBeVisible()
  })

  it('renders contributing investigations alongside the source investigation', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          baseDto({
            source_investigation: { investigation_id: 'inv-source-abc', relationship: 'source' },
            contributing_investigations: [
              { investigation_id: 'inv-contrib-1', relationship: 'contributing' },
            ],
          }),
        ),
      ),
    )

    renderEntryPage('kb-001')

    expect(await screen.findByRole('link', { name: 'inv-contrib-1' })).toHaveAttribute(
      'href',
      '/investigations/inv-contrib-1',
    )
    expect(screen.getByText('Contributing')).toBeVisible()
  })
})

describe('KnowledgeEntryPage — related entries', () => {
  it('renders related entries when present', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          baseDto({
            related_entries: [
              {
                id: 'point-2',
                entry_id: 'kb-related-1',
                entry_type: 'runbook',
                title: 'Restarting the checkout worker pool',
                service: 'checkout-service',
                created_at: '2026-05-01T00:00:00+00:00',
                updated_at: '2026-05-01T00:00:00+00:00',
                author: 'sre-team',
                version: 1,
                tags: [],
                validation_status: null,
                auto_published: false,
                relevance_score: null,
                snippet: 'Recovery procedure.',
              },
            ],
          }),
        ),
      ),
    )

    renderEntryPage('kb-001')

    expect(await screen.findByText('Related Entries')).toBeVisible()
    const relatedLink = screen.getByRole('link', { name: /Restarting the checkout worker pool/i })
    expect(relatedLink).toHaveAttribute('href', '/knowledge/kb-related-1')
  })

  it('renders no "Related Entries" section when there are none', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(baseDto())))

    renderEntryPage('kb-001')

    await screen.findByText('checkout-service latency after deploy')
    expect(screen.queryByText('Related Entries')).not.toBeInTheDocument()
  })
})

describe('KnowledgeEntryPage — invalid id (404)', () => {
  it('renders "Knowledge Base entry not found" inside the shell, not a generic 404', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ error: 'not_found' }, 404)))

    renderEntryPage('kb-missing')

    expect(await screen.findByText('Knowledge Base entry not found')).toBeVisible()
    expect(screen.getByText(/kb-missing/)).toBeVisible()
  })
})

describe('KnowledgeEntryPage — network/error state', () => {
  it('renders a retry-safe error message rather than throwing when the request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    renderEntryPage('kb-001')

    expect(await screen.findByRole('alert')).toHaveTextContent(/unable to load/i)
  })
})
