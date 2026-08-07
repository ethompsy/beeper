import { useEffect, useState } from 'react'
import {
  fetchSpending,
  type SpendingCapStatus,
  type SpendingDashboardData,
  type SpendingProviderConfig,
  type SpendingSummary,
} from '../api/spending'
import { computeSpendChartData, type SpendChartData } from '../lib/spending/chart'

/**
 * SpendingPage — the Manage > Spending view (Task 5.3, FR35).
 *
 * Parity target: `templates/spending/spending.html` +
 * `templates/spending/_spending_content.html`
 * (`spending_bp.spending_dashboard`, `ui/beeper_ui/routes/spending.py`),
 * per `docs/design/route-parity-targets.md` §4b. Data comes from
 * `GET /api/v1/spending/` (`src/api/spending.ts`), a JSON serialization of
 * `SpendingService` — the same service the Jinja dashboard reads from.
 *
 * The API key is masked server-side (`SpendingService._mask_api_key`,
 * `ui/beeper_ui/services/spending_service.py`) — the raw key is never sent
 * to the browser; this page only ever sees `provider_config.api_key_masked`.
 *
 * The Jinja view auto-refreshes via `/spending/status`'s
 * `hx-trigger="every 30s"` (`spending/spending.html:12-15`); this is
 * replaced by a client-side `setInterval` refetch at the same 30s cadence,
 * fully replacing the rendered state on every refresh (matching the Jinja
 * partial's innerHTML-swap semantics).
 *
 * `/spending/costs*` (Cost Insights) is explicitly out of scope — a
 * separate §7 nav destination, not this page.
 *
 * No permalink state (§4b: "none") — this dashboard has no user-set
 * filter/selection state.
 */

const REFRESH_INTERVAL_MS = 30_000

function formatUsd(amount: number): string {
  return amount.toFixed(2)
}

function capBarColorClass(pct: number | null | undefined): string {
  const value = pct ?? 0
  if (value >= 95) return 'bg-status-critical'
  if (value >= 80) return 'bg-status-warning'
  return 'bg-status-healthy'
}

export function SpendingPage() {
  const [data, setData] = useState<SpendingDashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    function load() {
      fetchSpending(controller.signal)
        .then((result) => {
          setData(result)
          setError(null)
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted) return
          setError(
            err instanceof Error ? err.message : 'Unable to connect to the spending data store.',
          )
        })
    }

    load()
    const intervalId = setInterval(load, REFRESH_INTERVAL_MS)

    return () => {
      controller.abort()
      clearInterval(intervalId)
    }
  }, [])

  const isLoading = data === null && error === null

  return (
    <div data-testid="spending-page" className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold text-text-primary">LLM Spending</h1>
        <p className="mt-1 text-sm text-text-secondary">
          LLM provider configuration and spending metrics across investigations.
        </p>
      </div>

      {/*
        Task 5.5 a11y-audit finding — same narrow-live-region pattern as
        `SourcesPage.tsx`: the skeleton -> data/error transition wasn't
        announced (errors already are, via the `role="alert"` block below,
        which is an implicit assertive live region). This sr-only status
        only changes text — and therefore only re-announces — when the
        underlying summary actually changes (a genuine spend update at the
        30s refetch cadence, `REFRESH_INTERVAL_MS`), not on every identical
        poll.
      */}
      <p role="status" aria-live="polite" className="sr-only">
        {!isLoading && !error && data
          ? `Spending data loaded. Daily spend $${formatUsd(data.summary.daily_cost_usd)}, monthly spend $${formatUsd(data.summary.monthly_cost_usd)}.`
          : ''}
      </p>

      {error ? (
        <div role="alert" className="rounded-lg border border-status-critical/30 bg-surface-raised p-4">
          <p className="text-sm text-status-critical">{error}</p>
        </div>
      ) : null}

      {isLoading ? <SpendingSkeleton /> : null}

      {!isLoading && !error && data ? <SpendingDashboardContent data={data} /> : null}
    </div>
  )
}

function SpendingSkeleton() {
  return (
    <div
      data-testid="spending-skeleton"
      role="status"
      aria-label="Loading spending data"
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
    >
      {Array.from({ length: 4 }, (_, index) => (
        <div
          key={index}
          className="flex flex-col gap-2 rounded-lg border border-surface-overlay bg-surface-raised p-4 animate-pulse motion-reduce:animate-none"
        >
          <div className="h-3 w-20 rounded bg-surface-overlay" />
          <div className="h-6 w-24 rounded bg-surface-overlay" />
        </div>
      ))}
    </div>
  )
}

function SpendingDashboardContent({ data }: { data: SpendingDashboardData }) {
  const { summary, cap_status: capStatus, provider_config: providerConfig, trend } = data
  const chart = computeSpendChartData(trend)

  return (
    <div className="flex flex-col gap-4">
      {capStatus.warnings.length > 0 ? (
        <div className="rounded-lg border border-status-warning/30 bg-status-warning/10 p-3">
          {capStatus.warnings.map((warning) => (
            <p key={warning} className="text-sm text-status-warning">
              {warning}
            </p>
          ))}
        </div>
      ) : null}

      <ProviderConfigCard providerConfig={providerConfig} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <DailySpendCard summary={summary} />
        <MonthlySpendCard summary={summary} />
        <RateCard summary={summary} />
        <EnforcementCard capStatus={capStatus} />
      </div>

      {chart.dataPoints.length > 0 ? <SpendTrendChart chart={chart} /> : null}
    </div>
  )
}

function ProviderConfigCard({ providerConfig }: { providerConfig: SpendingProviderConfig }) {
  return (
    <div className="rounded-lg border border-surface-overlay bg-surface-raised p-4">
      <h2 className="mb-3 text-base font-semibold text-text-primary">LLM Provider Configuration</h2>
      {providerConfig.configured ? (
        <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <div>
            <dt className="text-xs uppercase tracking-wider text-text-muted">Provider</dt>
            <dd data-field="provider" className="mt-0.5 text-sm font-medium capitalize text-text-primary">
              {providerConfig.provider}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wider text-text-muted">Model</dt>
            <dd data-field="model" className="mt-0.5 font-mono text-sm font-medium text-text-primary">
              {providerConfig.model}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wider text-text-muted">API Key</dt>
            <dd data-field="api-key" className="mt-0.5 font-mono text-sm font-medium text-text-primary">
              {providerConfig.api_key_masked ?? 'Not set'}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wider text-text-muted">Endpoint</dt>
            <dd className="mt-0.5 font-mono text-sm font-medium text-text-primary">
              {providerConfig.endpoint ?? 'Default'}
            </dd>
          </div>
        </dl>
      ) : (
        <p className="text-sm text-text-secondary">
          No LLM provider configured. Set{' '}
          <code className="rounded bg-surface-base px-1.5 py-0.5 font-mono text-text-muted">
            BEEPER_LLM_PROVIDER
          </code>{' '}
          and{' '}
          <code className="rounded bg-surface-base px-1.5 py-0.5 font-mono text-text-muted">
            BEEPER_LLM_MODEL
          </code>{' '}
          to enable investigations.
        </p>
      )}
    </div>
  )
}

function DailySpendCard({ summary }: { summary: SpendingSummary }) {
  return (
    <div className="rounded-lg border border-surface-overlay bg-surface-raised p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">Daily Spend</h3>
      <div className="mt-1 text-2xl font-semibold text-text-primary">${formatUsd(summary.daily_cost_usd)}</div>
      {summary.daily_cap_usd != null ? (
        <>
          <div className="mt-1 text-xs text-text-muted">of ${formatUsd(summary.daily_cap_usd)} cap</div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-base">
            <div
              className={`h-full rounded-full ${capBarColorClass(summary.daily_pct)}`}
              style={{ width: `${Math.min(summary.daily_pct ?? 0, 100)}%` }}
            />
          </div>
          <div className="mt-1 text-xs text-text-secondary">{Math.round(summary.daily_pct ?? 0)}%</div>
        </>
      ) : (
        <div className="mt-1 text-xs text-text-muted">No daily cap configured</div>
      )}
      <div className="mt-2 text-xs text-text-muted">{summary.daily_investigation_count} investigations today</div>
    </div>
  )
}

function MonthlySpendCard({ summary }: { summary: SpendingSummary }) {
  return (
    <div className="rounded-lg border border-surface-overlay bg-surface-raised p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">Monthly Spend</h3>
      <div className="mt-1 text-2xl font-semibold text-text-primary">${formatUsd(summary.monthly_cost_usd)}</div>
      {summary.monthly_cap_usd != null ? (
        <>
          <div className="mt-1 text-xs text-text-muted">of ${formatUsd(summary.monthly_cap_usd)} cap</div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-base">
            <div
              className={`h-full rounded-full ${capBarColorClass(summary.monthly_pct)}`}
              style={{ width: `${Math.min(summary.monthly_pct ?? 0, 100)}%` }}
            />
          </div>
          <div className="mt-1 text-xs text-text-secondary">{Math.round(summary.monthly_pct ?? 0)}%</div>
        </>
      ) : (
        <div className="mt-1 text-xs text-text-muted">No monthly cap configured</div>
      )}
      <div className="mt-2 text-xs text-text-muted">
        {summary.monthly_investigation_count} investigations this month
      </div>
    </div>
  )
}

function RateCard({ summary }: { summary: SpendingSummary }) {
  return (
    <div className="rounded-lg border border-surface-overlay bg-surface-raised p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">Rate</h3>
      <div className="mt-1 text-2xl font-semibold text-text-primary">{summary.rate_per_hour}/hr</div>
      {summary.rate_limit != null ? (
        <div className="mt-1 text-xs text-text-muted">limit: {summary.rate_limit}/hr</div>
      ) : (
        <div className="mt-1 text-xs text-text-muted">No rate limit configured</div>
      )}
      <div className="mt-2 text-xs text-text-muted">
        Projected: ${formatUsd(summary.projected_monthly_usd)}/month
      </div>
    </div>
  )
}

function EnforcementCard({ capStatus }: { capStatus: SpendingCapStatus }) {
  return (
    <div className="rounded-lg border border-surface-overlay bg-surface-raised p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">Enforcement</h3>
      <div className="mt-2">
        <EnforcementBadge capStatus={capStatus} />
      </div>
    </div>
  )
}

function EnforcementBadge({ capStatus }: { capStatus: SpendingCapStatus }) {
  if (!capStatus.caps_configured) {
    return (
      <span className="inline-flex items-center rounded border border-status-muted/30 bg-surface-overlay px-2 py-0.5 text-xs font-medium text-text-muted">
        Not Configured
      </span>
    )
  }
  if (capStatus.enforcement_active) {
    return (
      <span className="inline-flex items-center rounded border border-status-critical/30 bg-status-critical/15 px-2 py-0.5 text-xs font-medium text-status-critical">
        Active
      </span>
    )
  }
  if (capStatus.warnings.length > 0) {
    return (
      <span className="inline-flex items-center rounded border border-status-warning/30 bg-status-warning/15 px-2 py-0.5 text-xs font-medium text-status-warning">
        Warning
      </span>
    )
  }
  return (
    <span className="inline-flex items-center rounded border border-status-healthy/30 bg-status-healthy/15 px-2 py-0.5 text-xs font-medium text-status-healthy">
      OK
    </span>
  )
}

function SpendTrendChart({ chart }: { chart: SpendChartData }) {
  return (
    <div className="rounded-lg border border-surface-overlay bg-surface-raised p-4">
      <h2 className="mb-3 text-base font-semibold text-text-primary">Daily Spend Trend</h2>
      {/*
        Task 5.5 a11y-audit finding: `role="img"` + a single `aria-label`
        summarized the chart as one opaque image with no per-point data —
        assistive tech had no way to learn the actual daily amounts (WCAG
        1.1.1 Non-text Content). Fixed with the standard accessible-chart
        pattern: an sr-only data table carries the real information (one row
        per point, exactly what the SVG plots) and the SVG itself becomes
        `aria-hidden` decoration layered visually alongside it — rather than
        stacking per-point `aria-label`s on the `<circle>` elements, which
        NVDA/VoiceOver do not reliably expose as descendants of a `role=img`
        ancestor (an `img` role collapses its subtree to a single accessible
        node per the ARIA spec).
      */}
      <table className="sr-only">
        <caption>Daily spend trend — one row per day</caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Spend (USD)</th>
          </tr>
        </thead>
        <tbody>
          {chart.dataPoints.map((point) => (
            <tr key={point.period}>
              <td>{point.period}</td>
              <td>${point.costUsd.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <svg
        className="h-72 w-full"
        viewBox={`0 0 ${chart.chartWidth} ${chart.chartHeight}`}
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        {chart.yGridLines.map((line) => (
          <g key={line.y}>
            <line
              x1={60}
              y1={line.y}
              x2={chart.chartWidth - 60}
              y2={line.y}
              className="stroke-surface-overlay"
              strokeWidth={1}
            />
            <text x={55} y={line.y + 4} textAnchor="end" className="fill-text-muted" fontSize={11}>
              ${line.value.toFixed(2)}
            </text>
          </g>
        ))}
        <polyline points={chart.trendPoints} fill="none" className="stroke-primary" strokeWidth={2} />
        {chart.dataPoints.map((point) => (
          <g key={point.period}>
            <circle cx={point.x} cy={point.y} r={4} className="fill-primary" />
            <text x={point.x} y={chart.chartHeight - 5} textAnchor="middle" className="fill-text-muted" fontSize={9}>
              {point.period.slice(-5)}
            </text>
          </g>
        ))}
      </svg>
    </div>
  )
}
