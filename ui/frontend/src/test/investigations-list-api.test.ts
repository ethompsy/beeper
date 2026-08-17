/**
 * investigations-list-api.test.ts
 *
 * Tests the plain-`fetch` client for the Task 1.6 JSON list endpoint
 * (`src/api/investigations-list.ts`). Mocks `global.fetch` directly (no
 * MSW/react-query — matches the module's own no-dependency design).
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { fetchInvestigations, InvestigationsListError } from '../api/investigations-list'
import { PermissionDeniedError } from '../api/http'

const SAMPLE_ITEM = {
  id: 'inv-1',
  status: 'investigating',
  service: 'checkout-service',
  severity: 'high',
  condition: 'elevated error rate',
  started_at: '2026-07-04T12:00:00Z',
  triggered_at: '2026-07-04T11:59:00Z',
  completed_at: null,
  workflow_state: 'investigating',
  workflow_state_changed_at: null,
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchInvestigations', () => {
  it('fetches the list endpoint with no query string when no params are given', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [SAMPLE_ITEM],
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchInvestigations()

    // Task 8.4: routed through `apiFetch`, which injects `credentials:
    // 'same-origin'` by default on top of the caller's own init.
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/investigations/', {
      credentials: 'same-origin',
      signal: undefined,
    })
    expect(result).toEqual([SAMPLE_ITEM])
  })

  it('builds a query string from status/service/severity params', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
    })
    vi.stubGlobal('fetch', fetchMock)

    await fetchInvestigations({ status: 'completed', service: 'checkout-service', severity: 'high' })

    const [url] = fetchMock.mock.calls[0]
    const parsed = new URL(url, 'http://localhost')
    expect(parsed.pathname).toBe('/api/v1/investigations/')
    expect(parsed.searchParams.get('status')).toBe('completed')
    expect(parsed.searchParams.get('service')).toBe('checkout-service')
    expect(parsed.searchParams.get('severity')).toBe('high')
  })

  it('throws InvestigationsListError on a non-OK HTTP response', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ error: 'operator_unavailable' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchInvestigations()).rejects.toBeInstanceOf(InvestigationsListError)
    await expect(fetchInvestigations()).rejects.toMatchObject({ status: 503 })
  })

  it('throws InvestigationsListError when the API returns a JSON error body with 200 status (defensive)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ error: 'operator_unavailable' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchInvestigations()).rejects.toBeInstanceOf(InvestigationsListError)
  })

  it('passes an AbortSignal through to fetch', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
    })
    vi.stubGlobal('fetch', fetchMock)

    const controller = new AbortController()
    await fetchInvestigations(undefined, controller.signal)

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/investigations/', {
      credentials: 'same-origin',
      signal: controller.signal,
    })
  })

  it('rejects with the shared PermissionDeniedError on a 403 (Task 8.4 apiFetch seam), not InvestigationsListError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        clone() {
          return this
        },
        json: async () => ({
          type: 'https://beeper.dev/errors/not-provisioned',
          detail: 'This account is authenticated but not provisioned for access.',
        }),
      }),
    )

    await expect(fetchInvestigations()).rejects.toBeInstanceOf(PermissionDeniedError)
  })
})
