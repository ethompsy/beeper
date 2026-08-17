/**
 * spending.test.ts
 *
 * Tests the plain-`fetch` client for the Task 5.3 JSON spending dashboard
 * endpoint (`src/api/spending.ts`). Mocks `global.fetch` directly, matching
 * `investigations-list-api.test.ts`/`sources-list.test.ts`'s conventions.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { fetchSpending, SpendingFetchError } from '../spending'

const SAMPLE_RESPONSE = {
  summary: {
    daily_cost_usd: 12.34,
    monthly_cost_usd: 150.0,
    daily_cap_usd: 50.0,
    monthly_cap_usd: 500.0,
    daily_pct: 24.7,
    monthly_pct: 30.0,
    projected_monthly_usd: 200.0,
    daily_investigation_count: 15,
    monthly_investigation_count: 200,
    rate_per_hour: 5,
    rate_limit: 100,
  },
  cap_status: {
    enforcement_active: false,
    caps_configured: true,
    warnings: [],
  },
  provider_config: {
    provider: 'anthropic',
    model: 'claude-sonnet-4',
    endpoint: null,
    api_key_masked: '••••••1234',
    api_key_configured: true,
    configured: true,
    daily_cap_usd: 50.0,
    monthly_cap_usd: 500.0,
    rate_limit: 100,
  },
  trend: [{ period: '2026-05-29', cost_usd: 3.5, count: 4 }],
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchSpending', () => {
  it('fetches the spending endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => SAMPLE_RESPONSE,
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchSpending()

    // Task 8.4: routed through `apiFetch`, which injects `credentials:
    // 'same-origin'` by default.
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/spending/', {
      credentials: 'same-origin',
      signal: undefined,
    })
    expect(result).toEqual(SAMPLE_RESPONSE)
  })

  it('passes an AbortSignal through to fetch', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => SAMPLE_RESPONSE,
    })
    vi.stubGlobal('fetch', fetchMock)

    const controller = new AbortController()
    await fetchSpending(controller.signal)

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/spending/', {
      credentials: 'same-origin',
      signal: controller.signal,
    })
  })

  it('throws SpendingFetchError on a non-OK HTTP response', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ error: 'spending_data_unavailable' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchSpending()).rejects.toBeInstanceOf(SpendingFetchError)
    await expect(fetchSpending()).rejects.toMatchObject({ status: 503 })
  })

  it('throws SpendingFetchError when the API returns a JSON error body with 200 status (defensive)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ error: 'spending_data_unavailable' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchSpending()).rejects.toBeInstanceOf(SpendingFetchError)
  })

  it('never sees a raw api key field — only the masked provider_config shape', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => SAMPLE_RESPONSE,
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchSpending()
    expect(result.provider_config.api_key_masked).toBe('••••••1234')
    expect(Object.keys(result.provider_config)).not.toContain('api_key')
  })
})
