/**
 * ingestion-stats.ts — plain-`fetch` client for the Task 5.2 JSON endpoint
 * (`GET /api/v1/ingestion/stats`).
 *
 * Deliberately dependency-free (no react-query/swr), matching
 * `src/api/investigations-list.ts`'s and `src/api/investigation-detail.ts`'s
 * own no-dependency design so the app doesn't accumulate a second
 * data-fetching convention.
 *
 * Response shape mirrors `ingestion_stats_json()` in
 * `ui/beeper_ui/routes/health.py` exactly (Task 5.2): the 11
 * `IngestionStats` dataclass fields, snake_case, passthrough from the
 * operator — no derived pipeline-state fields (those are computed
 * client-side, see `src/lib/ingestion/pipeline-view.ts`).
 */

export interface IngestionStats {
  buffer_size: number
  buffered_count: number
  dropped_count: number
  is_full: boolean
  /** FR32 */
  metrics_received: number
  /** FR32 */
  logs_received: number
  /** FR33 */
  anomalies_detected: number
  /** FR33 */
  anomalies_suppressed: number
  /** FR33 */
  active_metric_detectors: number
  /** FR33 */
  ewma_warmup_samples: number
  /** FR33 */
  ewma_warmup_minimum: number
}

export class IngestionStatsError extends Error {
  readonly status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'IngestionStatsError'
    this.status = status
  }
}

const STATS_ENDPOINT = '/api/v1/ingestion/stats'

function isErrorBody(data: unknown): data is { error: string } {
  return typeof data === 'object' && data !== null && 'error' in data
}

/**
 * Fetch ingestion/detection pipeline stats from the Task 5.2 JSON API.
 *
 * Used both for the initial one-shot fetch and every subsequent
 * auto-refresh poll (`useAutoRefresh`) — the caller decides how often to
 * call this; the client itself has no polling/caching behavior of its own.
 */
export async function fetchIngestionStats(signal?: AbortSignal): Promise<IngestionStats> {
  const response = await fetch(STATS_ENDPOINT, { signal })

  if (!response.ok) {
    throw new IngestionStatsError(
      `Failed to fetch ingestion stats (HTTP ${response.status})`,
      response.status,
    )
  }

  const data = (await response.json()) as IngestionStats | { error: string }
  if (isErrorBody(data)) {
    throw new IngestionStatsError(data.error || 'Unable to connect to the Beeper operator.')
  }

  return data
}
