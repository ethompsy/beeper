/**
 * ingestion-stats.test.ts
 *
 * Tests the plain-`fetch` client for the Task 5.2 JSON endpoint
 * (`src/api/ingestion-stats.ts`). Mocks `global.fetch` directly (no MSW/
 * react-query — matches the module's own no-dependency design, same
 * convention as `src/api/test/investigation-detail.test.ts` and
 * `src/test/investigations-list-api.test.ts`).
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { fetchIngestionStats, IngestionStatsError } from '../ingestion-stats'

const SAMPLE_STATS = {
  buffer_size: 10000,
  buffered_count: 42,
  dropped_count: 0,
  is_full: false,
  metrics_received: 1234,
  logs_received: 5678,
  anomalies_detected: 3,
  anomalies_suppressed: 1,
  active_metric_detectors: 7,
  ewma_warmup_samples: 45,
  ewma_warmup_minimum: 100,
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchIngestionStats', () => {
  it('fetches the stats endpoint and returns the parsed JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => SAMPLE_STATS,
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchIngestionStats()

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/ingestion/stats', { signal: undefined })
    expect(result).toEqual(SAMPLE_STATS)
  })

  it('passes an AbortSignal through to fetch', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => SAMPLE_STATS,
    })
    vi.stubGlobal('fetch', fetchMock)

    const controller = new AbortController()
    await fetchIngestionStats(controller.signal)

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/ingestion/stats', { signal: controller.signal })
  })

  it('throws IngestionStatsError on a non-OK HTTP response', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ error: 'operator_unavailable' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchIngestionStats()).rejects.toBeInstanceOf(IngestionStatsError)
    await expect(fetchIngestionStats()).rejects.toMatchObject({ status: 503 })
  })

  it('throws IngestionStatsError when the API returns a JSON error body with 200 status (defensive)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ error: 'operator_unavailable' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchIngestionStats()).rejects.toBeInstanceOf(IngestionStatsError)
    await expect(fetchIngestionStats()).rejects.toMatchObject({
      message: 'operator_unavailable',
    })
  })

  it('propagates a raw network failure (fetch() itself rejecting) as a rejection, not a silent success', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    vi.stubGlobal('fetch', fetchMock)

    // No try/catch wrapper around the raw `fetch()` call in the client —
    // a network-level failure (offline, DNS, CORS) rejects as-is; only
    // non-OK HTTP responses and `{error}` bodies are normalized into
    // IngestionStatsError. The page's own `.catch()` handles both cases
    // uniformly (see IngestionStatsPage.tsx).
    await expect(fetchIngestionStats()).rejects.toThrow('Failed to fetch')
  })
})
