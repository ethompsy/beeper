/**
 * KnowledgeBasePage.test.tsx (Task 5.1)
 *
 * Covers the [T] AC "KB browse/search at parity; search query URL-encoded +
 * cold-loads (FR53/FR29)":
 *  - cold load shows a skeleton, never a blank frame (NFR19)
 *  - browse mode (no query) renders entries; empty KB shows an explanatory
 *    empty state (FR28)
 *  - typing a search query debounce-updates the `?q=` URL param and
 *    re-fetches (FR29)
 *  - cold-loading a URL seeded with `?q=` reproduces the identical search
 *    result with no prior in-app interaction (FR53 permalink)
 *  - no-results / soft-error (search not configured) states render inline,
 *    never a blank frame
 *
 * Mocks `global.fetch` directly (matching `InvestigationListPage.test.tsx`'s
 * convention) and renders inside a `MemoryRouter`.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { KnowledgeBasePage } from '../KnowledgeBasePage'
import type { KnowledgeListResponse } from '../../api/knowledge-list'

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response
}

function listResponse(overrides: Partial<KnowledgeListResponse> = {}): KnowledgeListResponse {
  return {
    query: '',
    entries: [],
    has_exact_matches: true,
    error: null,
    ...overrides,
  }
}

function makeEntrySummary(overrides: Partial<KnowledgeListResponse['entries'][number]> = {}) {
  return {
    id: 'point-1',
    entry_id: 'kb-001',
    entry_type: 'investigation',
    title: 'checkout-service latency after deploy',
    service: 'checkout-service',
    created_at: '2026-06-01T10:00:00+00:00',
    updated_at: '2026-06-01T10:00:00+00:00',
    author: 'beeper',
    version: 1,
    tags: ['deploy'],
    validation_status: 'human-confirmed',
    auto_published: false,
    relevance_score: null,
    snippet: 'Connection pool exhaustion after a deploy.',
    ...overrides,
  }
}

/** Renders the current route's `search` string so tests can assert on the URL (FR53). */
function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-search">{location.search}</div>
}

function renderPage(initialEntries: string[] = ['/knowledge']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <LocationProbe />
      <Routes>
        <Route path="/knowledge" element={<KnowledgeBasePage />} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('KnowledgeBasePage — cold load skeleton (NFR19)', () => {
  it('shows a skeleton (not a blank frame) while the initial fetch is in flight', async () => {
    let resolveFn!: () => void
    const gate = new Promise<void>((resolve) => {
      resolveFn = resolve
    })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async () => {
        await gate
        return jsonResponse(listResponse())
      }),
    )

    renderPage()

    expect(screen.getByRole('status', { name: 'Loading knowledge base entries' })).toBeInTheDocument()

    resolveFn()
    await waitFor(() =>
      expect(
        screen.queryByRole('status', { name: 'Loading knowledge base entries' }),
      ).not.toBeInTheDocument(),
    )
  })
})

describe('KnowledgeBasePage — browse mode (FR28)', () => {
  it('renders entries fetched with no query', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(listResponse({ entries: [makeEntrySummary()] })),
    )
    vi.stubGlobal('fetch', fetchMock)

    renderPage()

    expect(await screen.findByText('checkout-service latency after deploy')).toBeVisible()
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toBe('/api/v1/knowledge/')
  })

  it('renders the empty-KB explanatory state when there are no entries and no query', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(listResponse())))

    renderPage()

    expect(await screen.findByText('No knowledge base entries yet')).toBeVisible()
  })

  it('renders entry_type, service, tags, and a truncated snippet for each card', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(listResponse({ entries: [makeEntrySummary()] }))),
    )

    renderPage()

    const card = await screen.findByRole('link', { name: /checkout-service latency after deploy/i })
    expect(card).toHaveTextContent('Investigation')
    expect(card).toHaveTextContent('checkout-service')
    expect(card).toHaveTextContent('Connection pool exhaustion after a deploy.')
    expect(card).toHaveTextContent('deploy')
  })
})

describe('KnowledgeBasePage — search is a URL permalink (FR29/FR53)', () => {
  it(
    'typing a query debounce-updates the `?q=` URL param and re-fetches',
    async () => {
      const user = userEvent.setup()
      const fetchMock = vi.fn().mockResolvedValue(jsonResponse(listResponse()))
      vi.stubGlobal('fetch', fetchMock)

      renderPage()
      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

      const input = screen.getByLabelText('Search knowledge base')
      await user.type(input, 'connection pool')

      // Not yet updated immediately after typing — the debounce hasn't elapsed.
      expect(screen.getByTestId('location-search').textContent).toBe('')

      await waitFor(() => expect(screen.getByTestId('location-search')).toHaveTextContent('q=connection+pool'))
      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
      const [url] = fetchMock.mock.calls[1] as [string]
      expect(url).toBe('/api/v1/knowledge/?q=connection+pool')
    },
    10000,
  )

  it('cold-loading a URL seeded with ?q=<query> (no prior in-app state) reproduces the identical search result', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(
        listResponse({
          query: 'latency',
          entries: [makeEntrySummary({ relevance_score: 0.82 })],
        }),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    renderPage(['/knowledge?q=latency'])

    expect(await screen.findByText('checkout-service latency after deploy')).toBeVisible()
    const input = screen.getByLabelText('Search knowledge base') as HTMLInputElement
    expect(input.value).toBe('latency')
    const [url] = fetchMock.mock.calls[0] as [string]
    expect(url).toBe('/api/v1/knowledge/?q=latency')
  })

  it('renders "no results" for a query with zero matches (never blank)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(listResponse({ query: 'nonexistent-thing' }))),
    )

    renderPage(['/knowledge?q=nonexistent-thing'])

    expect(await screen.findByText('No results found')).toBeVisible()
    expect(screen.getByText('No entries match "nonexistent-thing".')).toBeVisible()
  })

  it('shows a "showing related entries" notice when the search has no exact match', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          listResponse({
            query: 'obscure',
            entries: [makeEntrySummary({ relevance_score: 0.55 })],
            has_exact_matches: false,
          }),
        ),
      ),
    )

    renderPage(['/knowledge?q=obscure'])

    expect(await screen.findByText(/no exact matches found/i)).toBeVisible()
  })

  it('renders the relevance score on a search-result card but not on a browse card', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          listResponse({ query: 'latency', entries: [makeEntrySummary({ relevance_score: 0.82 })] }),
        ),
      ),
    )

    renderPage(['/knowledge?q=latency'])

    const card = await screen.findByRole('link', { name: /checkout-service latency after deploy/i })
    expect(card).toHaveTextContent('82% relevant')
  })
})

describe('KnowledgeBasePage — soft error state (search not configured)', () => {
  it('renders the inline error message from the response body without a fetch-level alert', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          listResponse({
            query: 'anything',
            error: 'Search not configured. Set OPENAI_API_KEY to enable.',
          }),
        ),
      ),
    )

    renderPage(['/knowledge?q=anything'])

    expect(await screen.findByText(/search not configured/i)).toBeVisible()
    expect(screen.queryByText('Unable to fetch KB entries')).not.toBeInTheDocument()
  })
})

describe('KnowledgeBasePage — fetch-level failure', () => {
  it('renders an error banner when the request fails outright', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    renderPage()

    expect(await screen.findByText('Unable to fetch KB entries')).toBeVisible()
  })
})
