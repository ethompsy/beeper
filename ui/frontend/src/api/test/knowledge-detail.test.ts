/**
 * knowledge-detail.test.ts (Task 5.1)
 *
 * Coverage for the dedicated KB entry-detail REST client
 * (`src/api/knowledge-detail.ts`). Mirrors `investigation-detail.test.ts`'s
 * structure exactly (never-throws discriminated result contract).
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchKnowledgeEntry, type KnowledgeEntryDetailDto } from '../knowledge-detail'

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

function baseDto(): KnowledgeEntryDetailDto {
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
      root_cause: 'Connection pool exhaustion',
      resolution: 'Increased pool size',
      affected_services: ['checkout-service', 'frontend'],
    },
    related_entries: [],
    source_investigation: null,
    contributing_investigations: [],
  }
}

describe('fetchKnowledgeEntry', () => {
  it('requests the Task 5.1 endpoint with the entry id path-encoded', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(baseDto()))
    vi.stubGlobal('fetch', fetchMock)

    await fetchKnowledgeEntry('KB 001/weird')

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/knowledge/KB%20001%2Fweird', undefined)
  })

  it('resolves { kind: "ok", data } on a 200 JSON response', async () => {
    const dto = baseDto()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(dto)))

    const result = await fetchKnowledgeEntry('kb-001')

    expect(result).toEqual({ kind: 'ok', data: dto })
  })

  it('resolves { kind: "not-found" } on a 404 response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ error: 'not_found' }, 404)))

    const result = await fetchKnowledgeEntry('kb-missing')

    expect(result).toEqual({ kind: 'not-found' })
  })

  it('resolves { kind: "error" } on a non-404 non-2xx response, without throwing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ error: 'kb_unavailable' }, 503)))

    const result = await fetchKnowledgeEntry('kb-001')

    expect(result.kind).toBe('error')
  })

  it('resolves { kind: "error" } when fetch itself rejects (network failure), without throwing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    const result = await fetchKnowledgeEntry('kb-001')

    expect(result.kind).toBe('error')
  })

  it('resolves { kind: "error" } when the response body is not valid JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => {
          throw new SyntaxError('Unexpected token')
        },
      } as unknown as Response),
    )

    const result = await fetchKnowledgeEntry('kb-001')

    expect(result.kind).toBe('error')
  })
})
