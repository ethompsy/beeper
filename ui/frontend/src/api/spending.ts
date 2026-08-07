/**
 * spending.ts — plain-`fetch` client for the Task 5.3 JSON spending
 * dashboard endpoint (`GET /api/v1/spending/`).
 *
 * Deliberately dependency-free (no react-query/swr), matching
 * `investigations-list.ts`'s own no-dependency design (Task 1.6/2.2).
 *
 * Response shape mirrors `spending_json()` in
 * `ui/beeper_ui/routes/spending.py`, which serializes
 * `SpendingService.get_spending_summary()` / `get_cap_status()` /
 * `get_provider_config()` / `get_spending_trend()` exactly as the Jinja
 * dashboard does. `provider_config.api_key_masked` is ALREADY masked
 * server-side (`SpendingService._mask_api_key`, last 4 characters only) —
 * the full API key is never sent to the browser.
 */

export interface SpendingSummary {
  daily_cost_usd: number
  monthly_cost_usd: number
  daily_cap_usd: number | null
  monthly_cap_usd: number | null
  daily_pct: number | null
  monthly_pct: number | null
  projected_monthly_usd: number
  daily_investigation_count: number
  monthly_investigation_count: number
  rate_per_hour: number
  rate_limit: number | null
}

export interface SpendingCapStatus {
  enforcement_active: boolean
  caps_configured: boolean
  warnings: string[]
}

export interface SpendingProviderConfig {
  provider: string | null
  model: string | null
  endpoint: string | null
  /** Masked server-side (e.g. "••••••cdef") — never the raw key. */
  api_key_masked: string | null
  api_key_configured: boolean
  configured: boolean
  daily_cap_usd: number | null
  monthly_cap_usd: number | null
  rate_limit: number | null
}

export interface SpendingTrendPoint {
  period: string
  cost_usd: number
  count: number
}

export interface SpendingDashboardData {
  summary: SpendingSummary
  cap_status: SpendingCapStatus
  provider_config: SpendingProviderConfig
  trend: SpendingTrendPoint[]
}

export class SpendingFetchError extends Error {
  readonly status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'SpendingFetchError'
    this.status = status
  }
}

const SPENDING_ENDPOINT = '/api/v1/spending/'

/**
 * Fetch the spending dashboard data (provider config + spend summary + cap
 * status + trend) from the Task 5.3 JSON API.
 */
export async function fetchSpending(signal?: AbortSignal): Promise<SpendingDashboardData> {
  const response = await fetch(SPENDING_ENDPOINT, { signal })

  if (!response.ok) {
    throw new SpendingFetchError(
      `Failed to fetch spending data (HTTP ${response.status})`,
      response.status,
    )
  }

  const data = (await response.json()) as SpendingDashboardData | { error: string }
  if (!('summary' in data)) {
    throw new SpendingFetchError('Unable to connect to the spending data store.')
  }

  return data
}
