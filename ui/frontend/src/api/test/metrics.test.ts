/**
 * metrics.test.ts
 *
 * Tests the plain-`fetch` client for the Task 5.4 JSON MTTR endpoints
 * (`src/api/metrics.ts`). Mocks `global.fetch` directly — no MSW/react-query
 * — matching `investigations-list-api.test.ts`'s established convention.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  fetchMttrData,
  fetchMttrDrilldown,
  MetricsApiError,
  type MttrDashboardData,
  type MttrDrilldownData,
} from '../metrics'

const SAMPLE_DASHBOARD: MttrDashboardData = {
  period: 'month',
  service: null,
  severity: null,
  services: ['api-gateway', 'payment-service'],
  severities: ['critical', 'high'],
  trend: [
    { period: '2026-01', avg_mttr_seconds: 3600, count: 5, start: '2026-01-01', end: '2026-01-31' },
  ],
  overall_avg_mttr_seconds: 3600,
  total_count: 5,
  improvement_pct: null,
  improving: null,
  by_service: [{ service: 'api-gateway', avg_mttr_seconds: 3600, count: 5 }],
  by_severity: [{ severity: 'high', avg_mttr_seconds: 3600, count: 5 }],
}

const SAMPLE_DRILLDOWN: MttrDrilldownData = {
  period_label: '2026-02-01 to 2026-02-28',
  investigations: [
    {
      investigation_id: 'inv-abc123',
      service: 'api-gateway',
      severity: 'high',
      mttr_seconds: 3420,
      resolved_at: '2026-02-15T14:30:00Z',
      resolution_outcome: 'resolved',
    },
  ],
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchMttrData', () => {
  it('fetches the MTTR endpoint with no query string when no params are given', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => SAMPLE_DASHBOARD })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchMttrData()

    // Task 8.4: routed through `apiFetch`, which injects `credentials:
    // 'same-origin'` by default.
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/metrics/mttr', {
      credentials: 'same-origin',
      signal: undefined,
    })
    expect(result).toEqual(SAMPLE_DASHBOARD)
  })

  it('builds a query string from period/service/severity params', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => SAMPLE_DASHBOARD })
    vi.stubGlobal('fetch', fetchMock)

    await fetchMttrData({ period: 'week', service: 'api-gateway', severity: 'high' })

    const [url] = fetchMock.mock.calls[0]
    const parsed = new URL(url, 'http://localhost')
    expect(parsed.pathname).toBe('/api/v1/metrics/mttr')
    expect(parsed.searchParams.get('period')).toBe('week')
    expect(parsed.searchParams.get('service')).toBe('api-gateway')
    expect(parsed.searchParams.get('severity')).toBe('high')
  })

  it('omits empty-string service/severity from the query string ("All" selection)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => SAMPLE_DASHBOARD })
    vi.stubGlobal('fetch', fetchMock)

    await fetchMttrData({ period: 'month', service: '', severity: '' })

    const [url] = fetchMock.mock.calls[0]
    const parsed = new URL(url, 'http://localhost')
    expect(parsed.searchParams.has('service')).toBe(false)
    expect(parsed.searchParams.has('severity')).toBe(false)
  })

  it('throws MetricsApiError on a non-OK HTTP response', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({ error: 'metrics_unavailable' }) })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchMttrData()).rejects.toBeInstanceOf(MetricsApiError)
    await expect(fetchMttrData()).rejects.toMatchObject({ status: 503 })
  })

  it('throws MetricsApiError when the API returns a JSON error body with 200 status (defensive)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ error: 'metrics_unavailable' }) })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchMttrData()).rejects.toBeInstanceOf(MetricsApiError)
  })

  it('passes an AbortSignal through to fetch', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => SAMPLE_DASHBOARD })
    vi.stubGlobal('fetch', fetchMock)

    const controller = new AbortController()
    await fetchMttrData(undefined, controller.signal)

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/metrics/mttr', {
      credentials: 'same-origin',
      signal: controller.signal,
    })
  })
})

describe('fetchMttrDrilldown', () => {
  it('fetches the drilldown endpoint with start/end query params', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => SAMPLE_DRILLDOWN })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchMttrDrilldown({ start: '2026-02-01', end: '2026-02-28' })

    const [url] = fetchMock.mock.calls[0]
    const parsed = new URL(url, 'http://localhost')
    expect(parsed.pathname).toBe('/api/v1/metrics/mttr/drilldown')
    expect(parsed.searchParams.get('start')).toBe('2026-02-01')
    expect(parsed.searchParams.get('end')).toBe('2026-02-28')
    expect(parsed.searchParams.has('service')).toBe(false)
    expect(result).toEqual(SAMPLE_DRILLDOWN)
  })

  it('includes the optional service param when given', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => SAMPLE_DRILLDOWN })
    vi.stubGlobal('fetch', fetchMock)

    await fetchMttrDrilldown({ start: '2026-02-01', end: '2026-02-28', service: 'api-gateway' })

    const [url] = fetchMock.mock.calls[0]
    const parsed = new URL(url, 'http://localhost')
    expect(parsed.searchParams.get('service')).toBe('api-gateway')
  })

  it('resolves (does not throw) on a 400 invalid-range response, returning the empty-degrade shape', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ period_label: null, investigations: [] }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchMttrDrilldown({ start: '', end: '' })
    expect(result).toEqual({ period_label: null, investigations: [] })
  })

  it('throws MetricsApiError on a non-400 non-OK HTTP response', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ error: 'metrics_unavailable', investigations: [] }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchMttrDrilldown({ start: '2026-02-01', end: '2026-02-28' })).rejects.toBeInstanceOf(
      MetricsApiError,
    )
  })
})
