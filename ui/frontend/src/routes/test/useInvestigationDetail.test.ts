/**
 * useInvestigationDetail.test.ts (Task 2.5) — the one-shot fetch lifecycle
 * hook backing the detail view's initial render. LIVE streaming (SSE) is
 * Task 2.6 — this hook only performs the single Task 1.6 REST fetch.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useInvestigationDetail } from '../useInvestigationDetail'
import type { InvestigationDetailDto } from '../../api/investigation-detail'

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response
}

function pendingFetch(): Promise<Response> {
  return new Promise(() => {})
}

const DTO: InvestigationDetailDto = {
  id: 'INV-0042',
  status: 'investigating',
  service: 'checkout-service',
  message: null,
  metadata: {
    id: 'INV-0042',
    status: 'investigating',
    service: 'checkout-service',
    severity: 'High',
    condition: null,
    message: null,
    started_at: null,
    triggered_at: null,
    completed_at: null,
    workflow_state: null,
    workflow_state_changed_at: null,
    signal_count: null,
    job_name: null,
  },
  steps: [],
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useInvestigationDetail', () => {
  it('starts in the "loading" state', () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(pendingFetch()))
    const { result } = renderHook(() => useInvestigationDetail('INV-0042'))
    expect(result.current.status).toBe('loading')
  })

  it('transitions to "ok" with the fetched data on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(DTO)))
    const { result } = renderHook(() => useInvestigationDetail('INV-0042'))

    await waitFor(() => expect(result.current.status).toBe('ok'))
    expect(result.current).toEqual({ status: 'ok', data: DTO })
  })

  it('transitions to "not-found" on a 404', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ error: 'not_found' }, 404)))
    const { result } = renderHook(() => useInvestigationDetail('INV-9999'))

    await waitFor(() => expect(result.current.status).toBe('not-found'))
  })

  it('transitions to "error" on a network failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const { result } = renderHook(() => useInvestigationDetail('INV-0042'))

    await waitFor(() => expect(result.current.status).toBe('error'))
  })

  it('re-fetches when the investigationId changes, ignoring a stale in-flight response', async () => {
    let resolveFirst!: (value: Response) => void
    const firstPromise = new Promise<Response>((resolve) => {
      resolveFirst = resolve
    })
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(firstPromise)
      .mockResolvedValueOnce(jsonResponse({ ...DTO, id: 'INV-9999', service: 'other-service' }))
    vi.stubGlobal('fetch', fetchMock)

    const { result, rerender } = renderHook(
      ({ id }: { id: string }) => useInvestigationDetail(id),
      { initialProps: { id: 'INV-0042' } },
    )
    expect(result.current.status).toBe('loading')

    rerender({ id: 'INV-9999' })
    await waitFor(() => expect(result.current.status).toBe('ok'))
    expect(result.current.status === 'ok' && result.current.data.id).toBe('INV-9999')

    // The stale first request resolving afterward must not clobber state.
    resolveFirst(jsonResponse(DTO))
    await new Promise((r) => setTimeout(r, 0))
    expect(result.current.status === 'ok' && result.current.data.id).toBe('INV-9999')
  })
})
