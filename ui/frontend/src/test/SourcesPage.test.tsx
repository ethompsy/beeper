/**
 * SourcesPage.test.tsx
 *
 * Task 5.3 AC [T] coverage for the Sources half of "Sources status +
 * Spending render at parity (FR34/FR35)":
 *  - cold load shows a skeleton, never a blank frame
 *  - Prometheus/Loki connection status renders with indicators (FR34):
 *    connected → green "Connected" + last-seen; error/disconnected/failed →
 *    red "Disconnected"; anything else → gray "Unknown"
 *  - a source's inline error message + expandable technical details render
 *  - an empty sources list renders an explanatory empty state, never blank
 *  - a fetch failure renders an explanatory error state, never blank
 *  - auto-refresh: refetches every 5s (matching the Jinja `hx-trigger="every 5s"`
 *    partial it replaces), and a failed refresh replaces a prior good render
 *    with the error state (mirrors the HTMX innerHTML-swap semantics)
 *
 * Mocks `global.fetch` directly (matching `sources-list.ts`'s own
 * no-dependency design), following `InvestigationListPage.test.tsx`'s
 * established conventions in this repo.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import { SourcesPage } from '../routes/SourcesPage'

type Source = Record<string, unknown>

function makeSource(overrides: Partial<Source> = {}): Source {
  return {
    name: 'prometheus-main',
    type: 'prometheus',
    endpoint: 'http://prometheus:9090',
    status: 'connected',
    last_check: '2026-05-29T12:00:00Z',
    error: null,
    ...overrides,
  }
}

function mockFetchImmediate(data: unknown, opts: { ok?: boolean; status?: number } = {}) {
  const { ok = true, status = 200 } = opts
  const fetchMock = vi.fn().mockResolvedValue({ ok, status, json: async () => data })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function mockFetchGated(data: unknown, opts: { ok?: boolean; status?: number } = {}) {
  const { ok = true, status = 200 } = opts
  let resolveFn!: () => void
  const gate = new Promise<void>((resolve) => {
    resolveFn = resolve
  })
  const fetchMock = vi.fn().mockImplementation(async () => {
    await gate
    return { ok, status, json: async () => data }
  })
  vi.stubGlobal('fetch', fetchMock)
  return { fetchMock, release: resolveFn }
}

beforeEach(() => {
  vi.useRealTimers()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('SourcesPage — cold load skeleton', () => {
  it('shows a loading skeleton (not a blank frame) while the initial fetch is in flight', async () => {
    const { release } = mockFetchGated([])
    render(<SourcesPage />)

    expect(screen.getByRole('status', { name: 'Loading sources' })).toBeInTheDocument()

    release()
    await waitFor(() =>
      expect(screen.queryByRole('status', { name: 'Loading sources' })).not.toBeInTheDocument(),
    )
  })
})

describe('SourcesPage — connection status indicators (FR34)', () => {
  it('renders a connected Prometheus source with a green "Connected" badge and last-seen timestamp', async () => {
    mockFetchImmediate([
      makeSource({ name: 'prometheus-main', type: 'prometheus', status: 'connected', last_check: '2026-05-29T12:34:00Z' }),
    ])
    render(<SourcesPage />)

    const row = await screen.findByText('prometheus-main')
    const tableRow = row.closest('tr')!
    expect(within(tableRow).getByText('Connected')).toBeInTheDocument()
    expect(within(tableRow).getByText('Connected').closest('[data-slot="status-badge"]')).toHaveAttribute(
      'data-variant',
      'connected',
    )
    expect(within(tableRow).getByText('2026-05-29T12:34:00Z')).toBeInTheDocument()
  })

  it('renders a Loki source reporting "error" as a red "Disconnected" badge', async () => {
    mockFetchImmediate([
      makeSource({
        name: 'loki-prod',
        type: 'loki',
        status: 'error',
        error: { type: 'connection_error', message: 'Connection refused', details: 'dial tcp: refused' },
      }),
    ])
    render(<SourcesPage />)

    const row = await screen.findByText('loki-prod')
    const tableRow = row.closest('tr')!
    const badge = within(tableRow).getByText('Disconnected')
    expect(badge.closest('[data-slot="status-badge"]')).toHaveAttribute('data-variant', 'disconnected')
  })

  it('renders a source reporting "disconnected" as the same red "Disconnected" badge', async () => {
    mockFetchImmediate([makeSource({ name: 'loki-prod', status: 'disconnected' })])
    render(<SourcesPage />)

    const row = await screen.findByText('loki-prod')
    const badge = within(row.closest('tr')!).getByText('Disconnected')
    expect(badge.closest('[data-slot="status-badge"]')).toHaveAttribute('data-variant', 'disconnected')
  })

  it('renders an unrecognized status as a gray "Unknown" badge (never silently blank)', async () => {
    mockFetchImmediate([makeSource({ name: 'mystery-source', status: 'pending_setup' })])
    render(<SourcesPage />)

    const row = await screen.findByText('mystery-source')
    const badge = within(row.closest('tr')!).getByText('Unknown')
    expect(badge.closest('[data-slot="status-badge"]')).toHaveAttribute('data-variant', 'unknown')
  })

  it('falls back to "Never" when a source has no last_check timestamp', async () => {
    mockFetchImmediate([makeSource({ name: 'fresh-source', last_check: null })])
    render(<SourcesPage />)

    const row = await screen.findByText('fresh-source')
    expect(within(row.closest('tr')!).getByText('Never')).toBeInTheDocument()
  })

  it('renders both Prometheus and Loki sources together, each with their type and endpoint', async () => {
    mockFetchImmediate([
      makeSource({ name: 'prometheus-main', type: 'prometheus', endpoint: 'http://prometheus:9090' }),
      makeSource({ name: 'loki-prod', type: 'loki', endpoint: 'http://loki:3100', status: 'connected' }),
    ])
    render(<SourcesPage />)

    await screen.findByText('prometheus-main')
    expect(screen.getByText('loki-prod')).toBeInTheDocument()
    expect(screen.getByText('http://prometheus:9090')).toBeInTheDocument()
    expect(screen.getByText('http://loki:3100')).toBeInTheDocument()
  })
})

describe('SourcesPage — inline error detail (parity with sources/_list_content.html)', () => {
  it('renders the error message and an expandable technical-details block', async () => {
    mockFetchImmediate([
      makeSource({
        name: 'loki-prod',
        status: 'error',
        error: {
          type: 'connection_error',
          message: 'Connection refused',
          details: 'dial tcp: connection refused',
        },
      }),
    ])
    render(<SourcesPage />)

    await screen.findByText('loki-prod')
    expect(screen.getByText('Connection refused')).toBeInTheDocument()
    expect(screen.getByText('Show technical details')).toBeInTheDocument()
    expect(screen.getByText('dial tcp: connection refused')).toBeInTheDocument()
  })

  it('omits the technical-details toggle when the error has no details', async () => {
    mockFetchImmediate([
      makeSource({
        name: 'loki-prod',
        status: 'error',
        error: { type: 'connection_error', message: 'Connection refused', details: null },
      }),
    ])
    render(<SourcesPage />)

    await screen.findByText('Connection refused')
    expect(screen.queryByText('Show technical details')).not.toBeInTheDocument()
  })
})

describe('SourcesPage — empty state (never blank)', () => {
  it('renders an explanatory empty state when no sources are configured', async () => {
    mockFetchImmediate([])
    render(<SourcesPage />)

    await waitFor(() => expect(screen.queryByRole('status', { name: 'Loading sources' })).not.toBeInTheDocument())
    expect(screen.getByText('No data sources configured')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Create a Source custom resource in your Kubernetes cluster to connect Prometheus or Loki and start ingesting telemetry.',
      ),
    ).toBeInTheDocument()
  })
})

describe('SourcesPage — error state (never blank)', () => {
  it('renders an explanatory error state when the fetch fails (non-OK HTTP response)', async () => {
    mockFetchImmediate({ error: 'operator_unavailable' }, { ok: false, status: 503 })
    render(<SourcesPage />)

    expect(await screen.findByText('Unable to fetch sources')).toBeInTheDocument()
    expect(screen.getByText('Failed to fetch sources (HTTP 503)')).toBeInTheDocument()
    expect(screen.getByText('Make sure the Beeper operator is running and accessible.')).toBeInTheDocument()
  })

  it('surfaces the JSON error message when the operator is unreachable (200 status, error body)', async () => {
    mockFetchImmediate({ error: 'operator_unavailable', message: 'Timeout connecting to operator' })
    render(<SourcesPage />)

    expect(await screen.findByText('Unable to fetch sources')).toBeInTheDocument()
    expect(screen.getByText('Timeout connecting to operator')).toBeInTheDocument()
  })
})

describe('SourcesPage — auto-refresh (replaces Jinja hx-trigger="every 5s")', () => {
  it('refetches on a 5s interval', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const fetchMock = mockFetchImmediate([makeSource()])
    render(<SourcesPage />)

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    await vi.advanceTimersByTimeAsync(5_000)
    expect(fetchMock).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(5_000)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('a failed refresh replaces a prior good render with the error state (innerHTML-swap parity)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => [makeSource()] })
      .mockResolvedValueOnce({
        ok: false,
        status: 503,
        json: async () => ({ error: 'operator_unavailable', message: 'Timeout connecting to operator' }),
      })
    vi.stubGlobal('fetch', fetchMock)

    render(<SourcesPage />)
    await vi.waitFor(() => expect(screen.getByText('prometheus-main')).toBeInTheDocument())

    await vi.advanceTimersByTimeAsync(5_000)
    await vi.waitFor(() => expect(screen.getByText('Unable to fetch sources')).toBeInTheDocument())
    expect(screen.queryByText('prometheus-main')).not.toBeInTheDocument()
  })
})
