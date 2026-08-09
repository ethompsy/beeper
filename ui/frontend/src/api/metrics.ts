/**
 * metrics.ts — plain-`fetch` client for the Task 5.4 JSON MTTR endpoints
 * (`GET /api/v1/metrics/mttr`, `GET /api/v1/metrics/mttr/drilldown`).
 *
 * Deliberately dependency-free (no react-query/swr), matching
 * `src/api/investigations-list.ts`'s established convention for this
 * codebase (Task 2.2's scope-discipline note applies equally here).
 *
 * Response shapes mirror `mttr_json()` / `mttr_drilldown_json()` in
 * `ui/beeper_ui/routes/metrics.py` (Task 5.4) exactly. Both endpoints reuse
 * `MetricsService` server-side — no MTTR aggregation logic is duplicated
 * here, only the fetch/shape contract.
 */

import { apiFetch } from './http'

export type MttrPeriod = 'week' | 'month' | 'quarter'

export interface MttrTrendPoint {
  /** Bucket key, e.g. "2026-01" (month), "2026-W03" (week), "2026-Q1" (quarter). */
  period: string
  avg_mttr_seconds: number
  count: number
  /** ISO date (YYYY-MM-DD) bucket bounds — the drilldown fetch's `start`/`end` params. */
  start: string
  end: string
}

export interface MttrByService {
  service: string
  avg_mttr_seconds: number
  count: number
}

export interface MttrBySeverity {
  severity: string
  avg_mttr_seconds: number
  count: number
}

export interface MttrDashboardData {
  period: MttrPeriod
  service: string | null
  severity: string | null
  /** Full universe of service names (unaffected by the current filter selection — mirrors the Jinja dashboard). */
  services: string[]
  /** Full universe of severity values (unaffected by the current filter selection). */
  severities: string[]
  trend: MttrTrendPoint[]
  overall_avg_mttr_seconds: number
  total_count: number
  improvement_pct: number | null
  improving: boolean | null
  by_service: MttrByService[]
  by_severity: MttrBySeverity[]
}

export interface MttrDrilldownInvestigation {
  investigation_id: string | null
  service: string | null
  severity: string | null
  mttr_seconds: number | null
  resolved_at: string | null
  resolution_outcome: string | null
}

export interface MttrDrilldownData {
  period_label: string | null
  investigations: MttrDrilldownInvestigation[]
}

export class MetricsApiError extends Error {
  readonly status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'MetricsApiError'
    this.status = status
  }
}

const MTTR_ENDPOINT = '/api/v1/metrics/mttr'
const DRILLDOWN_ENDPOINT = '/api/v1/metrics/mttr/drilldown'

export interface MttrParams {
  period?: MttrPeriod
  /** Empty string / omitted means "all services" — matches the Jinja `<select>`'s "All Services" option. */
  service?: string
  /** Empty string / omitted means "all severities" — matches the Jinja `<select>`'s "All Severities" option. */
  severity?: string
}

function buildMttrQuery(params: MttrParams | undefined): string {
  if (!params) return ''
  const search = new URLSearchParams()
  if (params.period) search.set('period', params.period)
  if (params.service) search.set('service', params.service)
  if (params.severity) search.set('severity', params.severity)
  const qs = search.toString()
  return qs ? `?${qs}` : ''
}

/**
 * Fetch the MTTR trend + service/severity breakdown for the current filter
 * selection. Filtering is limited to the server-supported `period`/
 * `service`/`severity` params — same three the Jinja dashboard's `<select>`
 * filters post via `hx-get` (`ui/beeper_ui/templates/metrics/mttr.html`).
 */
export async function fetchMttrData(
  params?: MttrParams,
  signal?: AbortSignal,
): Promise<MttrDashboardData> {
  const response = await apiFetch(`${MTTR_ENDPOINT}${buildMttrQuery(params)}`, { signal })

  if (!response.ok) {
    throw new MetricsApiError(`Failed to fetch MTTR data (HTTP ${response.status})`, response.status)
  }

  const data = (await response.json()) as MttrDashboardData | { error: string }
  if ('error' in data) {
    throw new MetricsApiError(data.error ?? 'Unable to connect to the metrics data store.')
  }

  return data
}

export interface MttrDrilldownParams {
  /** ISO date (YYYY-MM-DD), inclusive. */
  start: string
  /** ISO date (YYYY-MM-DD), inclusive. */
  end: string
  /**
   * Optional service filter. Deliberately NOT wired to the dashboard's
   * current service filter by the caller (`MetricsPage`) — mirrors the
   * Jinja chart's own `hx-get` on each data point
   * (`metrics/_mttr_content.html`), which likewise omits `service` even
   * when a service filter is active. Kept as a real param (not removed)
   * because the JSON API/`MetricsService.get_investigations_for_period`
   * genuinely supports it — a future task can wire it up without an API
   * change.
   */
  service?: string
}

function buildDrilldownQuery(params: MttrDrilldownParams): string {
  const search = new URLSearchParams()
  search.set('start', params.start)
  search.set('end', params.end)
  if (params.service) search.set('service', params.service)
  return `?${search.toString()}`
}

/**
 * Fetch the drill-down investigation list for one trend time bucket
 * (clicking a `TrendChart` data point). A 400 response (invalid/missing
 * date range) still resolves to `{ period_label: null, investigations: [] }`
 * rather than throwing — the backend's own "degrade gracefully" contract —
 * so callers only need to branch on `investigations.length`, not on error
 * vs. empty-success.
 */
export async function fetchMttrDrilldown(
  params: MttrDrilldownParams,
  signal?: AbortSignal,
): Promise<MttrDrilldownData> {
  const response = await apiFetch(`${DRILLDOWN_ENDPOINT}${buildDrilldownQuery(params)}`, { signal })

  const data = (await response.json()) as MttrDrilldownData & { error?: string }

  if (!response.ok && response.status !== 400) {
    throw new MetricsApiError(
      data.error ?? `Failed to fetch drilldown data (HTTP ${response.status})`,
      response.status,
    )
  }

  return { period_label: data.period_label ?? null, investigations: data.investigations ?? [] }
}
