/**
 * IngestionStatsPage.test.tsx
 *
 * Task 5.2 [T] coverage for the routed Ingestion Stats page — the
 * acceptance criterion this file exists to prove:
 *
 *   "Detection/ingestion fields render and auto-refresh without manual
 *    reload (FR32)" — FR33's detection tiles are part of the same parity
 *    surface.
 *
 * Covered here:
 *  - cold load shows a skeleton, never a blank frame
 *  - all 7 Task 1.4 ingestion/detection fields render with formatted values
 *  - the page auto-refreshes on the polling interval WITHOUT any manual
 *    reload/remount/navigation — a second fetch fires and the displayed
 *    numbers update in place (the direct proof of the [T] criterion)
 *  - the three-state pipeline chip precedence: red "No Data" / amber
 *    "Warming Up" (+ progress bar) / green "Active" (no progress bar),
 *    each visually distinct via `data-variant`
 *  - a failed fetch renders a distinct error state, never a blank frame
 *  - a refresh never re-shows the skeleton (no flicker/layout shift)
 *
 * Mocks `global.fetch` directly (matching every other API client's own
 * no-dependency design) and uses Vitest fake timers to drive the
 * auto-refresh interval deterministically.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { IngestionStatsPage } from '../IngestionStatsPage'

const BASE_STATS = {
  buffer_size: 10000,
  buffered_count: 42,
  dropped_count: 0,
  is_full: false,
  metrics_received: 12904,
  logs_received: 8321,
  anomalies_detected: 3,
  anomalies_suppressed: 1,
  active_metric_detectors: 7,
  ewma_warmup_samples: 100,
  ewma_warmup_minimum: 100,
}

function statsPayload(overrides: Partial<typeof BASE_STATS> = {}) {
  return { ...BASE_STATS, ...overrides }
}

/** Mocks `fetch` to resolve immediately with `data` on every call. */
function mockFetchImmediate(data: unknown, opts: { ok?: boolean; status?: number } = {}) {
  const { ok = true, status = 200 } = opts
  const fetchMock = vi.fn().mockResolvedValue({ ok, status, json: async () => data })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** Mocks `fetch` so the caller controls exactly when the response resolves (for the skeleton test). */
function mockFetchGated(data: unknown) {
  let resolveFn!: () => void
  const gate = new Promise<void>((resolve) => {
    resolveFn = resolve
  })
  const fetchMock = vi.fn().mockImplementation(async () => {
    await gate
    return { ok: true, status: 200, json: async () => data }
  })
  vi.stubGlobal('fetch', fetchMock)
  return { fetchMock, release: resolveFn }
}

/** Mocks `fetch` to return a different payload on each successive call — drives the auto-refresh test. */
function mockFetchSequence(payloads: unknown[]) {
  let call = 0
  const fetchMock = vi.fn().mockImplementation(async () => {
    const data = payloads[Math.min(call, payloads.length - 1)]
    call += 1
    return { ok: true, status: 200, json: async () => data }
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  Object.defineProperty(document, 'hidden', { value: false, writable: true, configurable: true })
})

describe('IngestionStatsPage — cold load skeleton, never a blank frame', () => {
  it('shows a skeleton while the initial fetch is in flight', async () => {
    const { release } = mockFetchGated(statsPayload())
    render(<IngestionStatsPage />)

    expect(screen.getByRole('status', { name: 'Loading ingestion stats' })).toBeInTheDocument()

    release()
    await waitFor(() =>
      expect(screen.queryByRole('status', { name: 'Loading ingestion stats' })).not.toBeInTheDocument(),
    )
  })
})

describe('IngestionStatsPage — all Task 1.4 fields render (FR32/FR33)', () => {
  it('renders both ingestion tiles with thousands-formatted values', async () => {
    mockFetchImmediate(statsPayload({ metrics_received: 12904, logs_received: 8321 }))
    render(<IngestionStatsPage />)

    expect(await screen.findByText('Metrics Received')).toBeInTheDocument()
    expect(screen.getByText('12,904')).toBeInTheDocument()
    expect(screen.getByText('Logs Received')).toBeInTheDocument()
    expect(screen.getByText('8,321')).toBeInTheDocument()
  })

  it('renders all three detection tiles', async () => {
    mockFetchImmediate(
      statsPayload({ anomalies_detected: 3, anomalies_suppressed: 1, active_metric_detectors: 7 }),
    )
    render(<IngestionStatsPage />)

    expect(await screen.findByText('Anomalies Detected')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('Anomalies Suppressed')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('Active Metric Detectors')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
  })

  it('renders the ewma_warmup_samples/minimum fields inside the warmup copy while warming', async () => {
    mockFetchImmediate(statsPayload({ ewma_warmup_samples: 45, ewma_warmup_minimum: 100 }))
    render(<IngestionStatsPage />)

    expect(await screen.findByText(/45 \/ 100 samples/)).toBeInTheDocument()
  })
})

describe('IngestionStatsPage — three-state pipeline chip precedence, each visually distinct', () => {
  it('renders the red "No Data" chip when both metrics_received and logs_received are zero', async () => {
    mockFetchImmediate(statsPayload({ metrics_received: 0, logs_received: 0 }))
    render(<IngestionStatsPage />)

    const chip = await screen.findByText('No Data')
    expect(chip.closest('[data-slot="status-badge"]')).toHaveAttribute('data-variant', 'no-data')
  })

  it('renders the amber "Warming Up" chip with the progress bar when samples < minimum', async () => {
    mockFetchImmediate(
      statsPayload({
        metrics_received: 100,
        logs_received: 50,
        ewma_warmup_samples: 45,
        ewma_warmup_minimum: 100,
      }),
    )
    render(<IngestionStatsPage />)

    const chip = await screen.findByText('Warming Up')
    expect(chip.closest('[data-slot="status-badge"]')).toHaveAttribute('data-variant', 'warming-up')

    const bar = screen.getByRole('progressbar', { name: 'EWMA warmup progress' })
    expect(bar).toHaveAttribute('aria-valuenow', '45')
    expect(screen.getByText('45%')).toBeInTheDocument()
  })

  it('renders the green "Active" chip and no progress bar when samples >= minimum', async () => {
    mockFetchImmediate(
      statsPayload({
        metrics_received: 100,
        logs_received: 50,
        ewma_warmup_samples: 100,
        ewma_warmup_minimum: 100,
      }),
    )
    render(<IngestionStatsPage />)

    const chip = await screen.findByText('Active')
    expect(chip.closest('[data-slot="status-badge"]')).toHaveAttribute('data-variant', 'healthy')

    expect(screen.queryByRole('progressbar', { name: 'EWMA warmup progress' })).not.toBeInTheDocument()
  })
})

describe('IngestionStatsPage — distinct error state, never a blank frame', () => {
  it('renders an explanatory error block when the initial fetch fails', async () => {
    mockFetchImmediate({ error: 'operator_unavailable' })
    render(<IngestionStatsPage />)

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Unable to fetch ingestion stats')).toBeInTheDocument()
    expect(
      screen.getByText('Make sure the Beeper operator is running and accessible.'),
    ).toBeInTheDocument()
    // No tiles rendered alongside the error (matches Jinja's mutually-exclusive branches).
    expect(screen.queryByText('Metrics Received')).not.toBeInTheDocument()
  })

  it('renders an error block on an HTTP failure response too', async () => {
    mockFetchImmediate({ error: 'operator_unavailable' }, { ok: false, status: 503 })
    render(<IngestionStatsPage />)

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Unable to fetch ingestion stats')).toBeInTheDocument()
  })
})

describe('IngestionStatsPage — auto-refresh without manual reload (the [T] AC)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  it('polls the stats endpoint again after the interval elapses and updates the displayed numbers in place', async () => {
    const fetchMock = mockFetchSequence([
      statsPayload({ metrics_received: 1000, anomalies_detected: 1 }),
      statsPayload({ metrics_received: 2000, anomalies_detected: 9 }),
    ])
    render(<IngestionStatsPage />)

    // Initial render reflects the first payload.
    await vi.waitFor(() => expect(screen.getByText('1,000')).toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalledTimes(1)

    // Advance past the 5s auto-refresh interval — no click, no navigation,
    // no remount: this IS "auto-refresh without manual reload".
    await vi.advanceTimersByTimeAsync(5000)

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    await vi.waitFor(() => expect(screen.getByText('2,000')).toBeInTheDocument())
    expect(screen.queryByText('1,000')).not.toBeInTheDocument()
  })

  it('keeps polling on every subsequent interval tick, not just once', async () => {
    const fetchMock = mockFetchSequence([
      statsPayload({ metrics_received: 100 }),
      statsPayload({ metrics_received: 200 }),
      statsPayload({ metrics_received: 300 }),
    ])
    render(<IngestionStatsPage />)

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    await vi.advanceTimersByTimeAsync(5000)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))

    await vi.advanceTimersByTimeAsync(5000)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
    await vi.waitFor(() => expect(screen.getByText('300')).toBeInTheDocument())
  })

  it('a refresh never re-shows the loading skeleton (no flicker/layout shift)', async () => {
    mockFetchSequence([statsPayload({ metrics_received: 100 }), statsPayload({ metrics_received: 200 })])
    render(<IngestionStatsPage />)

    // Wait on real observable content (not just the mock's call count, which
    // increments synchronously before the response/state-update microtask
    // chain has actually settled) so the skeleton-absence check below can't
    // race ahead of the first render.
    await vi.waitFor(() => expect(screen.getByText('100')).toBeInTheDocument())
    expect(screen.queryByRole('status', { name: 'Loading ingestion stats' })).not.toBeInTheDocument()

    await vi.advanceTimersByTimeAsync(5000)
    await vi.waitFor(() => expect(screen.getByText('200')).toBeInTheDocument())

    // Skeleton never reappears during the refresh cycle.
    expect(screen.queryByRole('status', { name: 'Loading ingestion stats' })).not.toBeInTheDocument()
  })

  it('does not fire the auto-refresh poll while the tab is hidden', async () => {
    Object.defineProperty(document, 'hidden', { value: true, writable: true, configurable: true })
    const fetchMock = mockFetchSequence([statsPayload({ metrics_received: 100 })])
    render(<IngestionStatsPage />)

    // Wait on real observable content before asserting call counts (see the
    // "no flicker" test above for why this matters under fake timers).
    await vi.waitFor(() => expect(screen.getByText('100')).toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(20000)
    // Still 1 — the initial mount fetch — no polling while hidden.
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
