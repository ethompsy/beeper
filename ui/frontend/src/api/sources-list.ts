/**
 * sources-list.ts — plain-`fetch` client for the Task 5.3 JSON sources
 * endpoint (`GET /api/v1/sources/`).
 *
 * Deliberately dependency-free (no react-query/swr), matching
 * `investigations-list.ts`'s own no-dependency design (Task 1.6/2.2).
 *
 * Response shape mirrors `sources_list_json()` in
 * `ui/beeper_ui/routes/sources.py` exactly, which itself is a thin JSON
 * serialization of `SourceService.get_sources()`
 * (`ui/beeper_ui/services/source_service.py`) — including that service's
 * dedup-by-name behavior (NFR12), so no de-duplication is needed here.
 */

export interface SourceErrorDetail {
  type: string
  message: string
  details: string | null
}

export interface SourceListItem {
  name: string
  type: string
  endpoint: string
  /** Raw operator status string — see `deriveSourceStatusVariant` in `SourcesPage.tsx` for the display mapping. */
  status: string
  last_check: string | null
  error: SourceErrorDetail | null
}

export class SourcesListError extends Error {
  readonly status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'SourcesListError'
    this.status = status
  }
}

const SOURCES_ENDPOINT = '/api/v1/sources/'

/**
 * Fetch the configured sources list from the Task 5.3 JSON API.
 */
export async function fetchSources(signal?: AbortSignal): Promise<SourceListItem[]> {
  const response = await fetch(SOURCES_ENDPOINT, { signal })

  if (!response.ok) {
    throw new SourcesListError(`Failed to fetch sources (HTTP ${response.status})`, response.status)
  }

  const data = (await response.json()) as SourceListItem[] | { error: string; message?: string }
  if (!Array.isArray(data)) {
    throw new SourcesListError(
      data.message ?? data.error ?? 'Unable to connect to the Beeper operator.',
    )
  }

  return data
}
