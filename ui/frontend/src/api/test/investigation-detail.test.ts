/**
 * investigation-detail.test.ts (Task 2.5)
 *
 * Coverage for the dedicated detail REST client
 * (`src/api/investigation-detail.ts`) that Task 2.5 owns and Task 2.6 will
 * reuse for reconnect backfill. Plain `fetch` — stubbed via
 * `vi.stubGlobal`, matching this codebase's existing `vi.fn()` mocking
 * convention (no MSW/fetch-mock dependency added).
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchInvestigationDetail, type InvestigationDetailDto } from '../investigation-detail'

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

describe('fetchInvestigationDetail', () => {
  it('requests the Task 1.6 endpoint with the investigation id path-encoded', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ steps: [], metadata: {} }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchInvestigationDetail('INV 0042/weird')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/investigations/INV%200042%2Fweird',
      undefined,
    )
  })

  it('resolves { kind: "ok", data } on a 200 JSON response', async () => {
    const dto: InvestigationDetailDto = {
      id: 'INV-0042',
      status: 'investigating',
      service: 'checkout-service',
      message: null,
      metadata: {
        id: 'INV-0042',
        status: 'investigating',
        service: 'checkout-service',
        severity: 'High',
        condition: 'HTTP 5xx elevated',
        message: null,
        started_at: '2m ago',
        triggered_at: null,
        completed_at: null,
        workflow_state: 'investigating',
        workflow_state_changed_at: null,
        signal_count: 3,
        job_name: 'job-1',
      },
      steps: [],
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(dto)))

    const result = await fetchInvestigationDetail('INV-0042')

    expect(result).toEqual({ kind: 'ok', data: dto })
  })

  it('resolves { kind: "not-found" } on a 404 response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ error: 'not_found' }, 404)))

    const result = await fetchInvestigationDetail('INV-9999')

    expect(result).toEqual({ kind: 'not-found' })
  })

  it('resolves { kind: "error" } on a non-404 non-2xx response, without throwing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ error: 'operator_unavailable' }, 503)),
    )

    const result = await fetchInvestigationDetail('INV-0042')

    expect(result.kind).toBe('error')
  })

  it('resolves { kind: "error" } when fetch itself rejects (network failure), without throwing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    const result = await fetchInvestigationDetail('INV-0042')

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

    const result = await fetchInvestigationDetail('INV-0042')

    expect(result.kind).toBe('error')
  })
})
