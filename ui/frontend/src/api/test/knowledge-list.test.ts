/**
 * knowledge-list.test.ts (Task 5.1)
 *
 * Coverage for the KB browse/search REST client (`src/api/knowledge-list.ts`).
 * Plain `fetch` — stubbed via `vi.stubGlobal`, matching this codebase's
 * existing mocking convention (see `investigations-list.test.ts` if present,
 * and `investigation-detail.test.ts`).
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchKnowledgeBase, KnowledgeBaseError, type KnowledgeListResponse } from '../knowledge-list'

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchKnowledgeBase', () => {
  it('requests the browse endpoint with no query params when called with no args', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ query: '', entries: [], has_exact_matches: true, error: null }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchKnowledgeBase()

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/knowledge/', { signal: undefined })
  })

  it('URL-encodes the `q` param (FR53/FR29)', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ query: 'connection pool', entries: [], has_exact_matches: true, error: null }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchKnowledgeBase({ q: 'connection pool' })

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/knowledge/?q=connection+pool')
  })

  it('resolves the parsed JSON body on a 200 response', async () => {
    const body: KnowledgeListResponse = {
      query: 'latency',
      entries: [
        {
          id: 'point-1',
          entry_id: 'kb-001',
          entry_type: 'investigation',
          title: 'checkout-service latency',
          service: 'checkout-service',
          created_at: '2026-06-01T10:00:00+00:00',
          updated_at: '2026-06-01T10:00:00+00:00',
          author: 'beeper',
          version: 1,
          tags: ['deploy'],
          validation_status: 'human-confirmed',
          auto_published: false,
          relevance_score: 0.82,
          snippet: 'Connection pool exhaustion after a deploy.',
        },
      ],
      has_exact_matches: true,
      error: null,
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(body)))

    const result = await fetchKnowledgeBase({ q: 'latency' })

    expect(result).toEqual(body)
  })

  it('resolves the body as-is when the server reports a soft error (e.g. search not configured)', async () => {
    const body: KnowledgeListResponse = {
      query: 'latency',
      entries: [],
      has_exact_matches: true,
      error: 'Search not configured. Set OPENAI_API_KEY to enable.',
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(body)))

    const result = await fetchKnowledgeBase({ q: 'latency' })

    expect(result.error).toBe('Search not configured. Set OPENAI_API_KEY to enable.')
  })

  it('throws KnowledgeBaseError on a non-2xx HTTP response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ error: 'kb_unavailable' }, 503)))

    await expect(fetchKnowledgeBase()).rejects.toBeInstanceOf(KnowledgeBaseError)
  })

  it('throws KnowledgeBaseError when fetch itself rejects (network failure)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(fetchKnowledgeBase()).rejects.toBeInstanceOf(KnowledgeBaseError)
  })

  it('forwards an AbortSignal to fetch', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ query: '', entries: [], has_exact_matches: true, error: null }))
    vi.stubGlobal('fetch', fetchMock)
    const controller = new AbortController()

    await fetchKnowledgeBase(undefined, controller.signal)

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(init.signal).toBe(controller.signal)
  })
})
