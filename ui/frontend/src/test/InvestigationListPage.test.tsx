/**
 * InvestigationListPage.test.tsx
 *
 * Task 2.2 AC [T] coverage for the routed list page itself:
 *  - cold load shows a skeleton, never a blank frame (NFR19)
 *  - rows show service/component/severity/age/status with no horizontal
 *    scroll (FR45/46), ordered active+high-severity first
 *  - status-group filter switches groups correctly; Pending rows are
 *    visually distinct from Running (data-variant on StatusBadge)
 *  - an empty group renders the waiting state, never blank (FR22)
 *  - returning from detail restores list scroll position (FR22)
 *
 * Mocks `global.fetch` directly (matching the api client's own
 * no-dependency design) and renders the page inside a `MemoryRouter` so
 * `InvestigationCard`'s internal `<a>` hrefs don't need a real router.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route, Link, useLocation } from 'react-router-dom'
import { InvestigationListPage } from '../routes/InvestigationListPage'

type Item = Record<string, unknown>

function makeItem(overrides: Partial<Item> = {}): Item {
  return {
    id: 'inv-1',
    status: 'investigating',
    service: 'checkout-service',
    severity: 'medium',
    condition: 'elevated error rate',
    started_at: '2026-07-04T12:45:00Z',
    triggered_at: '2026-07-04T12:44:00Z',
    completed_at: null,
    workflow_state: 'investigating',
    workflow_state_changed_at: null,
    ...overrides,
  }
}

/** Mocks `fetch` to resolve immediately with `data` — the common case. */
function mockFetchImmediate(data: unknown, opts: { ok?: boolean; status?: number } = {}) {
  const { ok = true, status = 200 } = opts
  const fetchMock = vi.fn().mockResolvedValue({ ok, status, json: async () => data })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** Mocks `fetch` so the caller controls exactly when the response resolves (for the skeleton test). */
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

/** Renders the current route's `search` string so tests can assert on the URL (Task 3.1, FR53). */
function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-search">{location.search}</div>
}

function renderListPage(initialEntries: string[] = ['/investigations']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <LocationProbe />
      <Routes>
        <Route path="/investigations" element={<InvestigationListPage />} />
        <Route
          path="/investigations/:id"
          element={
            <div>
              <p>Detail placeholder</p>
              <Link to="/investigations">Back to list</Link>
            </div>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  sessionStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('InvestigationListPage — cold load skeleton (NFR19)', () => {
  it('shows a skeleton (not a blank frame) while the initial fetch is in flight', async () => {
    const { release } = mockFetchGated([])
    renderListPage()

    expect(screen.getByRole('status', { name: 'Loading investigations' })).toBeInTheDocument()

    release()
    await waitFor(() =>
      expect(screen.queryByRole('status', { name: 'Loading investigations' })).not.toBeInTheDocument(),
    )
  })
})

describe('InvestigationListPage — row facts + ordering (FR45/46)', () => {
  it('renders service, derived component, severity, age, and status for each row', async () => {
    mockFetchImmediate([
      makeItem({
        id: 'inv-1',
        service: 'checkout-service',
        severity: 'high',
        // Recognizable detector shape (operator/src/detection/metrics.rs) so
        // the row's derived-component slot (Task 2.3) has something to show.
        condition: 'Metric http_server_request_duration_seconds spike: 900.0, expected 100.0 ± 10.0',
        started_at: new Date(Date.now() - 5 * 60_000).toISOString(),
      }),
    ])
    renderListPage()

    const card = await screen.findByRole('link', { name: /checkout-service investigation/i })
    expect(within(card).getByText('checkout-service')).toBeInTheDocument()
    expect(within(card).getByText('High')).toBeInTheDocument()
    expect(within(card).getByText('HTTP/RPC request handling')).toBeInTheDocument()
    expect(within(card).getByText(/ago|Just now/)).toBeInTheDocument()
  })

  it('renders the plain-language problem-state fact for each row, alongside (not instead of) the derived component (Task 2.4, FR45/46)', async () => {
    mockFetchImmediate([
      makeItem({
        id: 'inv-2',
        service: 'catalog',
        severity: 'medium',
        condition: 'Memory usage above 90% on catalog pods',
      }),
    ])
    renderListPage()

    const card = await screen.findByRole('link', { name: /catalog investigation/i })
    expect(within(card).getByText('High memory usage (90%)')).toBeInTheDocument()
  })

  it('falls back the row problem-state to the raw condition text when no heuristic pattern matches, never blank (Task 2.4, FR47)', async () => {
    mockFetchImmediate([
      makeItem({
        id: 'inv-3',
        service: 'billing',
        severity: 'low',
        condition: 'Unexpected checkout conversion ratio drift',
      }),
    ])
    renderListPage()

    const card = await screen.findByRole('link', { name: /billing investigation/i })
    expect(within(card).getByText('Unexpected checkout conversion ratio drift')).toBeInTheDocument()
  })

  it('orders active + high-severity investigations first', async () => {
    mockFetchImmediate([
      makeItem({ id: 'low-active', service: 'svc-low', severity: 'low', status: 'investigating' }),
      makeItem({ id: 'critical-active', service: 'svc-critical', severity: 'critical', status: 'investigating' }),
      makeItem({ id: 'completed', service: 'svc-completed', severity: 'critical', status: 'completed' }),
    ])
    renderListPage()

    await screen.findByRole('link', { name: /svc-critical investigation/i })
    const cards = screen.getAllByRole('link', { name: /investigation,/ })
    const serviceOrder = cards.map((card) => card.textContent)
    // svc-critical (active, critical) before svc-low (active, low) before svc-completed (not active).
    expect(serviceOrder[0]).toMatch(/svc-critical/)
    expect(serviceOrder[1]).toMatch(/svc-low/)
  })

  it('renders each card with no horizontal-scroll layout (row content wraps, not a fixed-width table)', async () => {
    mockFetchImmediate([makeItem()])
    renderListPage()

    const card = await screen.findByRole('link', { name: /investigation,/ })
    // The card primitive is a flex column with wrapping flex rows, not a
    // wide table — asserting the data-slot confirms it's InvestigationCard
    // (whose className contract has no fixed/overflow-x width per Task 1.4).
    expect(card).toHaveAttribute('data-slot', 'investigation-card')
  })
})

describe('InvestigationListPage — status-group filter + Pending distinctness (FR22)', () => {
  it('defaults to the "active" group on load', async () => {
    mockFetchImmediate([
      makeItem({ id: 'active-1', status: 'investigating' }),
      makeItem({ id: 'completed-1', status: 'completed' }),
    ])
    renderListPage()

    await screen.findByRole('link', { name: /investigation,/ })
    expect(screen.getAllByRole('link', { name: /investigation,/ })).toHaveLength(1)
    expect(screen.getByRole('tab', { name: /Active/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('switching to the "Resolved" group filters to completed investigations only', async () => {
    const user = userEvent.setup()
    mockFetchImmediate([
      makeItem({ id: 'active-1', service: 'svc-active', status: 'investigating' }),
      makeItem({ id: 'completed-1', service: 'svc-completed', status: 'completed' }),
    ])
    renderListPage()

    await screen.findByRole('link', { name: /svc-active investigation/i })
    await user.click(screen.getByRole('tab', { name: /Resolved/ }))

    expect(await screen.findByRole('link', { name: /svc-completed investigation/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /svc-active investigation/i })).not.toBeInTheDocument()
  })

  it('switching to the "Failed" group filters to failed investigations only', async () => {
    const user = userEvent.setup()
    mockFetchImmediate([
      makeItem({ id: 'active-1', service: 'svc-active', status: 'investigating' }),
      makeItem({ id: 'failed-1', service: 'svc-failed', status: 'failed' }),
    ])
    renderListPage()

    await screen.findByRole('link', { name: /svc-active investigation/i })
    await user.click(screen.getByRole('tab', { name: /Failed/ }))

    expect(await screen.findByRole('link', { name: /svc-failed investigation/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /svc-active investigation/i })).not.toBeInTheDocument()
  })

  it('Pending rows render a visually distinct status badge from Running rows', async () => {
    mockFetchImmediate([
      makeItem({ id: 'pending-1', service: 'svc-pending', status: 'investigating', workflow_state: 'detected' }),
      makeItem({ id: 'running-1', service: 'svc-running', status: 'investigating', workflow_state: 'investigating' }),
    ])
    renderListPage()

    const pendingCard = await screen.findByRole('link', { name: /svc-pending investigation/i })
    const runningCard = await screen.findByRole('link', { name: /svc-running investigation/i })

    const pendingBadge = within(pendingCard).getByText('Pending')
    const runningBadge = within(runningCard).getByText('Investigating')

    expect(pendingBadge.closest('[data-slot="status-badge"]')).toHaveAttribute('data-variant', 'pending')
    expect(runningBadge.closest('[data-slot="status-badge"]')).toHaveAttribute('data-variant', 'investigating')
  })
})

describe('InvestigationListPage — status-group filter is a URL permalink (Task 3.1, FR53)', () => {
  it('selecting a filter updates the URL query param', async () => {
    const user = userEvent.setup()
    mockFetchImmediate([
      makeItem({ id: 'active-1', service: 'svc-active', status: 'investigating' }),
      makeItem({ id: 'completed-1', service: 'svc-completed', status: 'completed' }),
    ])
    renderListPage()

    expect(screen.getByTestId('location-search').textContent).toBe('')

    await screen.findByRole('link', { name: /svc-active investigation/i })
    await user.click(screen.getByRole('tab', { name: /Resolved/ }))

    await waitFor(() => expect(screen.getByTestId('location-search')).toHaveTextContent('?status=resolved'))

    await user.click(screen.getByRole('tab', { name: /Failed/ }))
    await waitFor(() => expect(screen.getByTestId('location-search')).toHaveTextContent('?status=failed'))

    await user.click(screen.getByRole('tab', { name: /Active/ }))
    await waitFor(() => expect(screen.getByTestId('location-search')).toHaveTextContent('?status=active'))
  })

  it('cold-loading a URL seeded with ?status=resolved (no prior in-app state) reproduces the Resolved-filtered list and tab selection (FR53)', async () => {
    mockFetchImmediate([
      makeItem({ id: 'active-1', service: 'svc-active', status: 'investigating' }),
      makeItem({ id: 'completed-1', service: 'svc-completed', status: 'completed' }),
    ])
    // Seed the router directly at the query-string URL — never touches the
    // "active" default or clicks any tab first, simulating a pasted link.
    renderListPage(['/investigations?status=resolved'])

    expect(await screen.findByRole('link', { name: /svc-completed investigation/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /svc-active investigation/i })).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Resolved/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('cold-loading a URL seeded with ?status=failed reproduces the Failed-filtered list (FR53)', async () => {
    mockFetchImmediate([
      makeItem({ id: 'active-1', service: 'svc-active', status: 'investigating' }),
      makeItem({ id: 'failed-1', service: 'svc-failed', status: 'failed' }),
    ])
    renderListPage(['/investigations?status=failed'])

    expect(await screen.findByRole('link', { name: /svc-failed investigation/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /svc-active investigation/i })).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Failed/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('an invalid/unknown ?status= value falls back to the default "active" group instead of crashing', async () => {
    mockFetchImmediate([
      makeItem({ id: 'active-1', service: 'svc-active', status: 'investigating' }),
      makeItem({ id: 'completed-1', service: 'svc-completed', status: 'completed' }),
    ])
    renderListPage(['/investigations?status=bogus'])

    expect(await screen.findByRole('link', { name: /svc-active investigation/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Active/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('an absent ?status= param defaults to "active" (unchanged default behavior)', async () => {
    mockFetchImmediate([makeItem({ id: 'active-1', status: 'investigating' })])
    renderListPage(['/investigations'])

    await screen.findByRole('link', { name: /investigation,/ })
    expect(screen.getByRole('tab', { name: /Active/ })).toHaveAttribute('aria-selected', 'true')
  })
})

describe('InvestigationListPage — status-group filter maps to the existing `status` fetch param, no operator change (Task 3.1 AC, R6/D6)', () => {
  it('fetches the investigation list with no `status` filter regardless of the URL status group (post-list filtering, R6/D6)', async () => {
    // `active` genuinely can't narrow (spans 2 job-phase statuses), but this
    // also guards a specific pitfall: `failed` is spelled identically in
    // both the status-*group* vocabulary and the API's raw `status`
    // vocabulary, so a naive `{ status: statusGroup }` pass-through would
    // silently narrow the fetch (and break the sibling groups' counts) the
    // moment the URL says `?status=failed`. Assert it never does, for any
    // of the three groups.
    for (const group of ['active', 'resolved', 'failed']) {
      const fetchMock = mockFetchImmediate([
        makeItem({ id: 'active-1', status: 'investigating' }),
        makeItem({ id: 'failed-1', status: 'failed' }),
      ])
      const { unmount } = renderListPage([`/investigations?status=${group}`])

      await waitFor(() => expect(fetchMock).toHaveBeenCalled())
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/v1/investigations/')
      expect(init.signal).toBeInstanceOf(AbortSignal)

      unmount()
    }
  })

  it('the group-count badges reflect the full cross-group dataset even when a non-active group is selected via cold URL load', async () => {
    mockFetchImmediate([
      makeItem({ id: 'a1', status: 'investigating' }),
      makeItem({ id: 'a2', status: 'awaiting_confirmation' }),
      makeItem({ id: 'r1', status: 'completed' }),
      makeItem({ id: 'f1', status: 'failed' }),
    ])
    renderListPage(['/investigations?status=failed'])

    // Wait for the fetch to resolve and rows/counts to settle.
    await screen.findByRole('link', { name: /investigation,/ })
    await waitFor(() => expect(screen.getByRole('tab', { name: /Failed/ })).toHaveTextContent('(1)'))
    expect(screen.getByRole('tab', { name: /^Active/ })).toHaveTextContent('(2)')
    expect(screen.getByRole('tab', { name: /Resolved/ })).toHaveTextContent('(1)')
  })
})

describe('InvestigationListPage — empty group waiting state (FR22)', () => {
  it('renders an explanatory waiting state when the active group has no investigations, never blank', async () => {
    mockFetchImmediate([])
    renderListPage()

    await waitFor(() => expect(screen.queryByRole('status', { name: 'Loading investigations' })).not.toBeInTheDocument())

    expect(screen.getByText('No active investigations')).toBeInTheDocument()
    expect(
      screen.getByText('Investigations appear automatically when Beeper detects anomalies in your services.'),
    ).toBeInTheDocument()
  })

  it('renders a group-specific waiting state for an empty Resolved group', async () => {
    const user = userEvent.setup()
    mockFetchImmediate([makeItem({ status: 'investigating' })])
    renderListPage()

    await screen.findByRole('link', { name: /investigation,/ })
    await user.click(screen.getByRole('tab', { name: /Resolved/ }))

    expect(await screen.findByText('No resolved investigations')).toBeInTheDocument()
  })
})

describe('InvestigationListPage — scroll restoration (FR22)', () => {
  it('restores the previous window scroll position when returning to the list from a detail route', async () => {
    const many = Array.from({ length: 30 }, (_, i) =>
      makeItem({ id: `inv-${i}`, service: `svc-${i}`, status: 'investigating' }),
    )
    mockFetchImmediate(many)
    renderListPage()

    await screen.findByRole('link', { name: /svc-0 investigation/i })

    // The app shell scrolls at the window/document level (no bounded inner
    // pane — see AppShell.tsx), so scroll restoration tracks
    // `window.scrollY`. jsdom's `window.scrollTo` is a no-op that doesn't
    // update `scrollY` by itself, so stub `scrollY` directly and fire the
    // 'scroll' event the hook listens for.
    Object.defineProperty(window, 'scrollY', { value: 240, writable: true, configurable: true })
    window.dispatchEvent(new Event('scroll'))

    // Navigate to a detail route (unmounts the list page).
    const firstCard = screen.getByRole('link', { name: /svc-0 investigation/i })
    await userEvent.setup().click(firstCard)
    expect(await screen.findByText('Detail placeholder')).toBeInTheDocument()

    // Simulate the browser resetting scroll on navigation (real behavior —
    // the detail route starts at the top), so the restore below is
    // provably the hook's doing, not an artifact of scrollY never changing.
    Object.defineProperty(window, 'scrollY', { value: 0, writable: true, configurable: true })

    const scrollToSpy = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})

    // Navigate back to the list (remounts the list page, refetches).
    await userEvent.setup().click(screen.getByRole('link', { name: 'Back to list' }))
    await screen.findByRole('link', { name: /svc-0 investigation/i })

    await waitFor(() => expect(scrollToSpy).toHaveBeenCalledWith(0, 240))
  })
})
