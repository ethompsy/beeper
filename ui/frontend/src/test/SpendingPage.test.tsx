/**
 * SpendingPage.test.tsx
 *
 * Task 5.3 AC [T] coverage for the Spending half of "Sources status +
 * Spending render at parity (FR34/FR35)":
 *  - cold load shows a skeleton, never a blank frame
 *  - LLM provider configuration renders (provider, model, MASKED api key,
 *    endpoint) — and critically, the raw/unmasked key is never present
 *    anywhere in the rendered DOM, even if a test double were to leak it
 *  - the "not configured" guidance renders when no provider is set
 *  - spending metrics render (daily/monthly spend, rate, enforcement state)
 *  - cap warnings render when present
 *  - the daily spend trend chart renders when trend data is present, and is
 *    omitted (not an empty chart) when there is none
 *  - a fetch failure renders an explanatory error state, never blank
 *  - auto-refresh: refetches every 30s (matching the Jinja
 *    `/spending/status` `hx-trigger="every 30s"` partial it replaces)
 *
 * Mocks `global.fetch` directly, following `InvestigationListPage.test.tsx`'s
 * and `SourcesPage.test.tsx`'s established conventions in this repo.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import { SpendingPage } from '../routes/SpendingPage'

/** Finds the metric card whose heading matches `headingText`, scoped for `within()` queries. */
function findCardByHeading(headingText: string): HTMLElement {
  const heading = screen.getByText(headingText)
  return heading.closest('div') as HTMLElement
}

function makeResponse(overrides: Record<string, unknown> = {}) {
  return {
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
    trend: [
      { period: '2026-05-28', cost_usd: 8.84, count: 9 },
      { period: '2026-05-29', cost_usd: 12.34, count: 15 },
    ],
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

describe('SpendingPage — cold load skeleton', () => {
  it('shows a loading skeleton (not a blank frame) while the initial fetch is in flight', async () => {
    const { release } = mockFetchGated(makeResponse())
    render(<SpendingPage />)

    expect(screen.getByRole('status', { name: 'Loading spending data' })).toBeInTheDocument()

    release()
    await waitFor(() =>
      expect(screen.queryByRole('status', { name: 'Loading spending data' })).not.toBeInTheDocument(),
    )
  })
})

describe('SpendingPage — LLM provider configuration (FR35)', () => {
  it('renders provider, model, masked API key, and endpoint', async () => {
    mockFetchImmediate(makeResponse())
    render(<SpendingPage />)

    await screen.findByText('LLM Provider Configuration')
    expect(screen.getByText('anthropic')).toBeInTheDocument()
    expect(screen.getByText('claude-sonnet-4')).toBeInTheDocument()
    expect(screen.getByText('••••••1234')).toBeInTheDocument()
    expect(screen.getByText('Default')).toBeInTheDocument() // no endpoint configured
  })

  it('NEVER renders a raw/unmasked API key value anywhere in the DOM', async () => {
    // Defensive: even though the real BFF always masks server-side, prove
    // the React view itself has no code path that would render a raw
    // `api_key` field if one were ever accidentally present in the payload.
    mockFetchImmediate(
      makeResponse({
        provider_config: {
          provider: 'anthropic',
          model: 'claude-sonnet-4',
          endpoint: null,
          api_key_masked: '••••••wxyz',
          api_key_configured: true,
          configured: true,
          daily_cap_usd: 50.0,
          monthly_cap_usd: 500.0,
          rate_limit: 100,
          // Simulated leak — the view must not read/render this field even
          // if it were present on the payload.
          api_key: 'sk-live-should-never-render-abcdwxyz',
        },
      }),
    )
    render(<SpendingPage />)

    await screen.findByText('••••••wxyz')
    expect(document.body.textContent).not.toContain('sk-live-should-never-render-abcdwxyz')
  })

  it('shows "Not set" when configured but no API key is present', async () => {
    mockFetchImmediate(
      makeResponse({
        provider_config: {
          provider: 'anthropic',
          model: 'claude-sonnet-4',
          endpoint: null,
          api_key_masked: null,
          api_key_configured: false,
          configured: true,
          daily_cap_usd: null,
          monthly_cap_usd: null,
          rate_limit: null,
        },
      }),
    )
    render(<SpendingPage />)

    await screen.findByText('Not set')
  })

  it('renders setup guidance when no LLM provider is configured', async () => {
    mockFetchImmediate(
      makeResponse({
        provider_config: {
          provider: null,
          model: null,
          endpoint: null,
          api_key_masked: null,
          api_key_configured: false,
          configured: false,
          daily_cap_usd: null,
          monthly_cap_usd: null,
          rate_limit: null,
        },
      }),
    )
    render(<SpendingPage />)

    await screen.findByText(/No LLM provider configured/)
    expect(screen.getByText('BEEPER_LLM_PROVIDER')).toBeInTheDocument()
    expect(screen.getByText('BEEPER_LLM_MODEL')).toBeInTheDocument()
  })
})

describe('SpendingPage — spending metrics', () => {
  it('renders daily spend, monthly spend, rate, and enforcement state', async () => {
    mockFetchImmediate(makeResponse())
    render(<SpendingPage />)

    await screen.findByText('Daily Spend')
    // Scoped per-card (not a blanket screen.getByText): the trend chart's
    // y-axis grid line also happens to render "$12.34" (== the max cost),
    // so an unscoped query would be ambiguous.
    expect(within(findCardByHeading('Daily Spend')).getByText('$12.34')).toBeInTheDocument()
    expect(within(findCardByHeading('Monthly Spend')).getByText('$150.00')).toBeInTheDocument()
    expect(within(findCardByHeading('Rate')).getByText('5/hr')).toBeInTheDocument()
    expect(within(findCardByHeading('Enforcement')).getByText('OK')).toBeInTheDocument()
  })

  it('renders "Active" enforcement when a cap has been reached', async () => {
    mockFetchImmediate(
      makeResponse({
        cap_status: { enforcement_active: true, caps_configured: true, warnings: ['Daily cap reached'] },
      }),
    )
    render(<SpendingPage />)

    await screen.findByText('Active')
  })

  it('renders "Not Configured" enforcement when no caps are set', async () => {
    mockFetchImmediate(
      makeResponse({ cap_status: { enforcement_active: false, caps_configured: false, warnings: [] } }),
    )
    render(<SpendingPage />)

    await screen.findByText('Not Configured')
  })

  it('renders cap warnings when present', async () => {
    mockFetchImmediate(
      makeResponse({
        cap_status: { enforcement_active: false, caps_configured: true, warnings: ['Daily spend at 85% of cap'] },
      }),
    )
    render(<SpendingPage />)

    await screen.findByText('Daily spend at 85% of cap')
  })

  it('shows "No daily cap configured" when daily_cap_usd is null', async () => {
    mockFetchImmediate(
      makeResponse({
        summary: {
          daily_cost_usd: 1.0,
          monthly_cost_usd: 1.0,
          daily_cap_usd: null,
          monthly_cap_usd: null,
          daily_pct: null,
          monthly_pct: null,
          projected_monthly_usd: 1.0,
          daily_investigation_count: 1,
          monthly_investigation_count: 1,
          rate_per_hour: 0,
          rate_limit: null,
        },
      }),
    )
    render(<SpendingPage />)

    await screen.findByText('No daily cap configured')
    expect(screen.getByText('No monthly cap configured')).toBeInTheDocument()
    expect(screen.getByText('No rate limit configured')).toBeInTheDocument()
  })
})

describe('SpendingPage — daily spend trend chart', () => {
  it('renders the chart when trend data is present', async () => {
    mockFetchImmediate(makeResponse())
    render(<SpendingPage />)

    await screen.findByText('Daily Spend Trend')
    // Task 5.5 a11y-audit fix: the chart's accessible representation is now
    // an sr-only data table (one row per point) rather than a single
    // role="img" + one-line aria-label on the decorative SVG (which gave
    // assistive tech no way to learn the actual per-day amounts — WCAG
    // 1.1.1). See `SpendingPage.tsx`'s `SpendTrendChart` doc comment.
    expect(screen.getByRole('table', { name: /Daily spend trend/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Date' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Spend (USD)' })).toBeInTheDocument()
  })

  it('omits the chart when there is no trend data', async () => {
    mockFetchImmediate(makeResponse({ trend: [] }))
    render(<SpendingPage />)

    await screen.findByText('Daily Spend') // dashboard has rendered
    expect(screen.queryByText('Daily Spend Trend')).not.toBeInTheDocument()
  })
})

describe('SpendingPage — error state (never blank)', () => {
  it('renders an explanatory error state when the fetch fails', async () => {
    mockFetchImmediate({ error: 'spending_data_unavailable' }, { ok: false, status: 503 })
    render(<SpendingPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent(/Failed to fetch spending data/)
  })
})

describe('SpendingPage — auto-refresh (replaces Jinja /spending/status hx-trigger="every 30s")', () => {
  it('refetches on a 30s interval', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const fetchMock = mockFetchImmediate(makeResponse())
    render(<SpendingPage />)

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    await vi.advanceTimersByTimeAsync(30_000)
    expect(fetchMock).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(30_000)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })
})
