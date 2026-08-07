import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { TrendChart, type TrendChartPoint } from '../lib'
import {
  fetchMttrData,
  fetchMttrDrilldown,
  type MttrDashboardData,
  type MttrDrilldownData,
  type MttrPeriod,
} from '../api/metrics'
import { formatMttr, formatResolutionOutcome } from '../lib/metrics/format-mttr'

/**
 * MetricsPage — the MTTR (Mean Time To Resolution) Trends Dashboard (Task
 * 5.4), replacing the Task 5.0b placeholder.
 *
 * Parity target (docs/design/route-parity-targets.md §5, pinned by Task
 * 5.0): `templates/metrics/mttr.html` + `_mttr_content.html` +
 * `_drilldown.html` — deliberately no FR id (checked and confirmed absent
 * from docs/reqs/main.md; the template is the sole, complete target).
 * Reproduces:
 *   - period/service/severity-filtered MTTR trend line chart (`TrendChart`)
 *     + Y-axis grid + clickable data points,
 *   - three summary stat cards (overall MTTR, trend vs. previous period,
 *     data-point count),
 *   - MTTR-by-service and MTTR-by-severity horizontal comparison bars,
 *   - a per-time-bucket drilldown (investigation list) reachable by
 *     clicking a chart data point — an expandable inline section per the
 *     parity doc's "nested route or expandable section, implementer's
 *     call" (a path sub-route would require editing the frozen `App.tsx`),
 *   - an export affordance (JSON/CSV) linking directly to the existing
 *     Jinja `/metrics/export` endpoint — no export logic is reimplemented.
 *
 * Filter state (`period`/`service`/`severity`) lives in the URL via
 * `useSearchParams` (FR53, per the parity doc's "encode them anyway"
 * guidance) — same `useSearchParams` + guard-function + no-`useState`-mirror
 * pattern as `InvestigationListPage.tsx`'s `?status=` permalink. Unlike that
 * page, these three params ARE real backend query filters (not a
 * post-fetch client-side grouping), so the data-fetch effect legitimately
 * depends on and refetches when any of them change.
 *
 * The drilldown selection (which time bucket's investigations are showing)
 * is deliberately NOT URL-encoded — the parity doc's permalink-eligible
 * list names only period/service/severity, and the drilldown's own backing
 * query needs a `start`/`end` date pair that only exists once trend data
 * has loaded, so it isn't cold-load-reproducible the same way a filter
 * value is. It resets to closed whenever the filters change (a small,
 * deliberate improvement over the Jinja page, which leaves a stale
 * drilldown panel showing investigations from the *previous* filter
 * selection after a filter change — `#drilldown-panel` sits outside the
 * `hx-target="#mttr-content"` swap boundary in `mttr.html`).
 */

const PERIOD_PARAM = 'period'
const SERVICE_PARAM = 'service'
const SEVERITY_PARAM = 'severity'

const VALID_PERIODS: readonly MttrPeriod[] = ['week', 'month', 'quarter']
const DEFAULT_PERIOD: MttrPeriod = 'month'

function isMttrPeriod(value: string | null): value is MttrPeriod {
  return value != null && (VALID_PERIODS as readonly string[]).includes(value)
}

const PERIOD_LABELS: Record<MttrPeriod, string> = {
  week: 'Weekly',
  month: 'Monthly',
  quarter: 'Quarterly',
}

function capitalize(value: string): string {
  return value.length > 0 ? value[0].toUpperCase() + value.slice(1) : value
}

interface DrilldownSelection {
  periodKey: string
  start: string
  end: string
}

export function MetricsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const rawPeriod = searchParams.get(PERIOD_PARAM)
  const period: MttrPeriod = isMttrPeriod(rawPeriod) ? rawPeriod : DEFAULT_PERIOD
  const service = searchParams.get(SERVICE_PARAM) ?? ''
  const severity = searchParams.get(SEVERITY_PARAM) ?? ''

  const [dashboard, setDashboard] = useState<MttrDashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [drilldown, setDrilldown] = useState<DrilldownSelection | null>(null)
  const [drilldownData, setDrilldownData] = useState<MttrDrilldownData | null>(null)
  const [drilldownError, setDrilldownError] = useState<string | null>(null)

  const isLoading = dashboard === null && error === null

  function updateFilter(key: string, value: string) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (value) next.set(key, value)
        else next.delete(key)
        return next
      },
      { replace: true },
    )
  }

  useEffect(() => {
    const controller = new AbortController()
    setDrilldown(null)

    fetchMttrData({ period, service, severity }, controller.signal)
      .then((data) => {
        setDashboard(data)
        setError(null)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setError(err instanceof Error ? err.message : 'Unable to connect to the metrics data store.')
      })

    return () => controller.abort()
  }, [period, service, severity])

  useEffect(() => {
    if (!drilldown) {
      setDrilldownData(null)
      setDrilldownError(null)
      return
    }

    const controller = new AbortController()
    setDrilldownData(null)
    setDrilldownError(null)

    fetchMttrDrilldown({ start: drilldown.start, end: drilldown.end }, controller.signal)
      .then((data) => setDrilldownData(data))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setDrilldownError(err instanceof Error ? err.message : 'Unable to load investigations for this period.')
      })

    return () => controller.abort()
  }, [drilldown])

  const chartPoints: TrendChartPoint[] = useMemo(
    () =>
      (dashboard?.trend ?? []).map((t) => ({
        id: t.period,
        label: t.period,
        value: t.avg_mttr_seconds,
        displayValue: formatMttr(t.avg_mttr_seconds),
      })),
    [dashboard],
  )

  function handleSelectPoint(point: TrendChartPoint) {
    const trendPoint = dashboard?.trend.find((t) => t.period === point.id)
    if (!trendPoint) return
    setDrilldown((prev) =>
      prev?.periodKey === trendPoint.period
        ? null
        : { periodKey: trendPoint.period, start: trendPoint.start, end: trendPoint.end },
    )
  }

  const exportHref = (format: 'json' | 'csv') => `/metrics/export?period=${period}&format=${format}`

  return (
    <div data-testid="metrics-page" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold text-text-primary">MTTR Trends Dashboard</h1>
        <p className="text-sm text-text-secondary">Mean Time To Resolution trends and service breakdowns</p>
      </div>

      {error ? (
        <div
          role="alert"
          className="rounded-md border border-status-critical/30 bg-surface-raised p-4 text-sm text-status-critical"
        >
          <p className="font-semibold">Unable to load metrics data</p>
          <p className="mt-1 text-text-secondary">{error}</p>
        </div>
      ) : null}

      {isLoading ? <MetricsSkeleton /> : null}

      {!isLoading && !error && dashboard ? (
        <>
          <MetricsFilterBar
            period={period}
            service={service}
            severity={severity}
            services={dashboard.services}
            severities={dashboard.severities}
            onPeriodChange={(value) => updateFilter(PERIOD_PARAM, value)}
            onServiceChange={(value) => updateFilter(SERVICE_PARAM, value)}
            onSeverityChange={(value) => updateFilter(SEVERITY_PARAM, value)}
            exportHref={exportHref}
          />

          {dashboard.total_count === 0 ? (
            <div
              role="status"
              className="rounded-md border border-surface-overlay bg-surface-raised p-8 text-center text-sm text-text-secondary"
            >
              No resolved investigations with MTTR data found. MTTR data is recorded when investigations
              are resolved.
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <SummaryCard label="Overall MTTR" value={formatMttr(dashboard.overall_avg_mttr_seconds)}>
                  {dashboard.total_count} investigations
                </SummaryCard>
                <SummaryCard label="Trend" value={<TrendBadge dashboard={dashboard} />}>
                  {dashboard.improvement_pct == null
                    ? 'Not enough data for trend'
                    : `${dashboard.improving ? 'Improving' : 'Worsening'} vs previous period`}
                </SummaryCard>
                <SummaryCard label="Data Points" value={String(dashboard.trend.length)}>
                  time periods
                </SummaryCard>
              </div>

              {dashboard.trend.length > 0 ? (
                <div className="flex flex-col gap-2 rounded-md border border-surface-overlay bg-surface-raised p-4">
                  <h2 className="text-lg font-semibold text-text-primary">MTTR Trend</h2>
                  <TrendChart
                    points={chartPoints}
                    ariaLabel={`MTTR trend, ${PERIOD_LABELS[period].toLowerCase()}`}
                    formatValue={(value) => formatMttr(value)}
                    selectedId={drilldown?.periodKey ?? null}
                    onSelectPoint={handleSelectPoint}
                  />
                  <p className="text-sm text-text-secondary">Click a data point to view investigations for that period.</p>
                </div>
              ) : null}

              {drilldown ? (
                <DrilldownPanel
                  data={drilldownData}
                  error={drilldownError}
                  onClose={() => setDrilldown(null)}
                />
              ) : null}

              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                {dashboard.by_service.length > 0 ? (
                  <ComparisonBars
                    title="MTTR by Service"
                    rows={dashboard.by_service.map((s) => ({
                      key: s.service,
                      label: s.service,
                      value: s.avg_mttr_seconds,
                      count: s.count,
                    }))}
                  />
                ) : null}

                {dashboard.by_severity.length > 0 ? (
                  <ComparisonBars
                    title="MTTR by Severity"
                    rows={dashboard.by_severity.map((s) => ({
                      key: s.severity,
                      label: capitalize(s.severity),
                      value: s.avg_mttr_seconds,
                      count: s.count,
                    }))}
                  />
                ) : null}
              </div>
            </>
          )}
        </>
      ) : null}
    </div>
  )
}

function MetricsSkeleton() {
  return (
    <div
      data-slot="metrics-skeleton"
      role="status"
      aria-label="Loading metrics"
      className="flex flex-col gap-3"
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {Array.from({ length: 3 }, (_, index) => (
          <div
            key={index}
            className="flex flex-col gap-2 rounded-md border border-surface-overlay bg-surface-raised p-4 animate-pulse motion-reduce:animate-none"
          >
            <div className="h-3 w-20 rounded bg-surface-overlay" />
            <div className="h-6 w-24 rounded bg-surface-overlay" />
          </div>
        ))}
      </div>
      <div className="h-64 rounded-md border border-surface-overlay bg-surface-raised p-4 animate-pulse motion-reduce:animate-none" />
    </div>
  )
}

interface MetricsFilterBarProps {
  period: MttrPeriod
  service: string
  severity: string
  services: string[]
  severities: string[]
  onPeriodChange: (value: string) => void
  onServiceChange: (value: string) => void
  onSeverityChange: (value: string) => void
  exportHref: (format: 'json' | 'csv') => string
}

/** Native `<select>`-driven filter bar — mirrors `mttr.html`'s three `hx-get` selects, now URL-permalinked (FR53). */
function MetricsFilterBar({
  period,
  service,
  severity,
  services,
  severities,
  onPeriodChange,
  onServiceChange,
  onSeverityChange,
  exportHref,
}: MetricsFilterBarProps) {
  const selectClassName =
    'rounded-md border border-surface-overlay bg-surface-base px-2 py-1.5 text-sm text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary'
  const labelClassName = 'text-sm text-text-secondary'

  return (
    <div className="flex flex-wrap items-end gap-4">
      <label className="flex flex-col gap-1">
        <span className={labelClassName}>Period</span>
        <select
          className={selectClassName}
          value={period}
          onChange={(event) => onPeriodChange(event.target.value)}
        >
          {VALID_PERIODS.map((value) => (
            <option key={value} value={value}>
              {PERIOD_LABELS[value]}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className={labelClassName}>Service</span>
        <select
          className={selectClassName}
          value={service}
          onChange={(event) => onServiceChange(event.target.value)}
        >
          <option value="">All Services</option>
          {services.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className={labelClassName}>Severity</span>
        <select
          className={selectClassName}
          value={severity}
          onChange={(event) => onSeverityChange(event.target.value)}
        >
          <option value="">All Severities</option>
          {severities.map((value) => (
            <option key={value} value={value}>
              {capitalize(value)}
            </option>
          ))}
        </select>
      </label>

      <div className="ml-auto flex items-center gap-2">
        <a
          href={exportHref('json')}
          className="rounded-md border border-surface-overlay px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary"
        >
          Export JSON
        </a>
        <a
          href={exportHref('csv')}
          className="rounded-md border border-surface-overlay px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary"
        >
          Export CSV
        </a>
      </div>
    </div>
  )
}

function SummaryCard({
  label,
  value,
  children,
}: {
  label: string
  value: ReactNode
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-1 rounded-md border border-surface-overlay bg-surface-raised p-4">
      <h2 className="text-sm text-text-secondary">{label}</h2>
      <p className="text-2xl font-semibold text-text-primary">{value}</p>
      <p className="text-sm text-text-secondary">{children}</p>
    </div>
  )
}

function TrendBadge({ dashboard }: { dashboard: MttrDashboardData }) {
  if (dashboard.improvement_pct == null) {
    return <span className="text-2xl font-semibold text-text-muted">—</span>
  }
  const magnitude = Math.abs(dashboard.improvement_pct)
  return (
    <span className={dashboard.improving ? 'text-status-healthy' : 'text-status-critical'}>
      {dashboard.improving ? '▼' : '▲'} {magnitude}%
    </span>
  )
}

interface ComparisonRow {
  key: string
  label: string
  value: number
  count: number
}

/** Horizontal comparison bars — reproduces `_mttr_content.html`'s `.category-bars` rows for both by-service and by-severity. */
function ComparisonBars({ title, rows }: { title: string; rows: ComparisonRow[] }) {
  const maxValue = Math.max(...rows.map((r) => r.value)) || 1
  return (
    <div
      data-testid={`comparison-bars-${title}`}
      className="flex flex-col gap-3 rounded-md border border-surface-overlay bg-surface-raised p-4"
    >
      <h2 className="text-lg font-semibold text-text-primary">{title}</h2>
      <div className="flex flex-col gap-2">
        {rows.map((row) => (
          <div key={row.key} className="flex items-center gap-2 text-sm">
            <span className="w-32 shrink-0 truncate text-text-secondary">{row.label}</span>
            <div className="h-2 flex-1 rounded-full bg-surface-overlay">
              <div
                className="h-2 rounded-full bg-primary"
                style={{ width: `${Math.round((row.value / maxValue) * 100)}%` }}
              />
            </div>
            <span className="w-28 shrink-0 text-right text-text-secondary">
              {formatMttr(row.value)} ({row.count})
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function DrilldownPanel({
  data,
  error,
  onClose,
}: {
  data: MttrDrilldownData | null
  error: string | null
  onClose: () => void
}) {
  const isLoading = data === null && error === null

  return (
    <div
      data-testid="drilldown-panel"
      className="flex flex-col gap-3 rounded-md border border-surface-overlay bg-surface-raised p-4"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-text-primary">
          Investigations{data?.period_label ? `: ${data.period_label}` : ''}
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md px-2 py-1 text-sm text-text-secondary hover:bg-surface-overlay hover:text-text-primary"
        >
          Close
        </button>
      </div>

      {error ? (
        <p role="alert" className="text-sm text-status-critical">
          {error}
        </p>
      ) : null}

      {isLoading ? (
        <p role="status" className="text-sm text-text-secondary">
          Loading investigations…
        </p>
      ) : null}

      {!isLoading && !error && data ? (
        data.investigations.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-surface-overlay text-text-secondary">
                  <th className="py-2 pr-4 font-medium">Investigation</th>
                  <th className="py-2 pr-4 font-medium">Service</th>
                  <th className="py-2 pr-4 font-medium">Severity</th>
                  <th className="py-2 pr-4 font-medium">MTTR</th>
                  <th className="py-2 pr-4 font-medium">Resolved</th>
                  <th className="py-2 pr-4 font-medium">Outcome</th>
                </tr>
              </thead>
              <tbody>
                {data.investigations.map((inv) => (
                  <tr key={inv.investigation_id} className="border-b border-surface-overlay last:border-0">
                    <td className="py-2 pr-4">
                      {inv.investigation_id ? (
                        <Link to={`/investigations/${inv.investigation_id}`} className="text-primary hover:underline">
                          {inv.investigation_id}
                        </Link>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="py-2 pr-4 text-text-primary">{inv.service ?? '—'}</td>
                    <td className="py-2 pr-4 text-text-secondary">
                      {inv.severity ? capitalize(inv.severity) : '—'}
                    </td>
                    <td className="py-2 pr-4 text-text-primary">{formatMttr(inv.mttr_seconds)}</td>
                    <td className="py-2 pr-4 text-text-secondary">{inv.resolved_at?.slice(0, 10) ?? ''}</td>
                    <td className="py-2 pr-4 text-text-secondary">
                      {formatResolutionOutcome(inv.resolution_outcome)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p role="status" className="text-sm text-text-secondary">
            No investigations found for this period.
          </p>
        )
      ) : null}
    </div>
  )
}
