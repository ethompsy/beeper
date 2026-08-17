/**
 * sources-list.test.ts
 *
 * Tests the plain-`fetch` client for the Task 5.3 JSON sources endpoint
 * (`src/api/sources-list.ts`). Mocks `global.fetch` directly (no MSW/
 * react-query — matches the module's own no-dependency design and
 * `investigations-list-api.test.ts`'s conventions).
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { fetchSources, SourcesListError } from '../sources-list'

const SAMPLE_SOURCE = {
  name: 'prometheus-main',
  type: 'prometheus',
  endpoint: 'http://prometheus:9090',
  status: 'connected',
  last_check: '2026-05-29T12:00:00Z',
  error: null,
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchSources', () => {
  it('fetches the sources endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [SAMPLE_SOURCE],
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchSources()

    // Task 8.4: routed through `apiFetch`, which injects `credentials:
    // 'same-origin'` by default.
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/sources/', {
      credentials: 'same-origin',
      signal: undefined,
    })
    expect(result).toEqual([SAMPLE_SOURCE])
  })

  it('passes an AbortSignal through to fetch', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
    })
    vi.stubGlobal('fetch', fetchMock)

    const controller = new AbortController()
    await fetchSources(controller.signal)

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/sources/', {
      credentials: 'same-origin',
      signal: controller.signal,
    })
  })

  it('throws SourcesListError on a non-OK HTTP response', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ error: 'operator_unavailable' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchSources()).rejects.toBeInstanceOf(SourcesListError)
    await expect(fetchSources()).rejects.toMatchObject({ status: 503 })
  })

  it('throws SourcesListError when the API returns a JSON error body with 200 status (defensive)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ error: 'operator_unavailable', message: 'Timeout connecting to operator' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchSources()).rejects.toBeInstanceOf(SourcesListError)
    await expect(fetchSources()).rejects.toThrow('Timeout connecting to operator')
  })

  it('preserves the nested error object on a source element', async () => {
    const withError = {
      ...SAMPLE_SOURCE,
      name: 'loki-prod',
      status: 'error',
      error: { type: 'connection_error', message: 'Connection refused', details: 'dial tcp: refused' },
    }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [withError],
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchSources()
    expect(result[0].error).toEqual(withError.error)
  })
})
