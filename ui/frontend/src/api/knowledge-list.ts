/**
 * knowledge-list.ts — plain-`fetch` client for the Task 5.1 JSON KB
 * browse/search endpoint (`GET /api/v1/knowledge/`).
 *
 * Deliberately dependency-free (no react-query/swr), matching
 * `investigations-list.ts`'s no-dependency design (Task 2.2) — this codebase
 * has no data-fetching library anywhere in the migrated views.
 *
 * Response shape mirrors `knowledge_list_json()` in
 * `ui/beeper_ui/routes/knowledge.py` exactly (Task 5.1): the same endpoint
 * serves both browse (no `q`) and search (`q` present) — the React KB page
 * decides which mode it's in purely from whether `q` is set in the URL
 * (Task 3.1's permalink pattern, `InvestigationListPage.tsx`), not from a
 * separate route (`App.tsx`/`AppLayout.tsx` are final and only register a
 * single `/app/knowledge` route — no `/app/knowledge/search`).
 */

/** One KB entry as summarized for the browse/search list (no full content). */
export interface KnowledgeEntrySummary {
  id: string
  entry_id: string
  entry_type: string
  title: string
  service: string | null
  created_at: string | null
  updated_at: string | null
  author: string | null
  version: number
  tags: string[]
  validation_status: string | null
  auto_published: boolean
  /** Present only when the query was a semantic search (0.0–1.0); null on plain browse. */
  relevance_score: number | null
  /** Plain-text preview (markdown already stripped server-side), truncated to ~200 chars. */
  snippet: string
}

export interface KnowledgeListResponse {
  /** Echoes the sanitized `q` the server actually searched with. */
  query: string
  entries: KnowledgeEntrySummary[]
  /** False when semantic search found no strong (>=0.7 score) match — results shown are "related", not exact. */
  has_exact_matches: boolean
  /** Non-null on a soft/expected condition (e.g. search not configured) — rendered inline, not thrown. */
  error: string | null
}

export interface KnowledgeListParams {
  q?: string
  entry_type?: string
  service?: string
  date_range?: string
}

export class KnowledgeBaseError extends Error {
  readonly status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'KnowledgeBaseError'
    this.status = status
  }
}

const LIST_ENDPOINT = '/api/v1/knowledge/'

function buildQuery(params: KnowledgeListParams | undefined): string {
  if (!params) return ''
  const search = new URLSearchParams()
  if (params.q) search.set('q', params.q)
  if (params.entry_type) search.set('entry_type', params.entry_type)
  if (params.service) search.set('service', params.service)
  if (params.date_range) search.set('date_range', params.date_range)
  const qs = search.toString()
  return qs ? `?${qs}` : ''
}

/**
 * Fetch the KB browse/search list from the Task 5.1 JSON API.
 *
 * Throws `KnowledgeBaseError` only on network/HTTP-level failure (fetch
 * rejects, or a non-2xx response) — mirrors `fetchInvestigations`'s
 * contract exactly. A 200 response whose body carries a non-null `error`
 * (e.g. "Search not configured...") is a normal, successful resolution: the
 * page renders that message inline rather than treating it as a thrown
 * error, matching how the Jinja `kb_search()` route degrades in place.
 */
export async function fetchKnowledgeBase(
  params?: KnowledgeListParams,
  signal?: AbortSignal,
): Promise<KnowledgeListResponse> {
  let response: Response
  try {
    response = await fetch(`${LIST_ENDPOINT}${buildQuery(params)}`, { signal })
  } catch (err) {
    throw new KnowledgeBaseError(
      err instanceof Error ? err.message : 'Unable to connect to the Beeper operator.',
    )
  }

  if (!response.ok) {
    throw new KnowledgeBaseError(
      `Failed to fetch knowledge base entries (HTTP ${response.status})`,
      response.status,
    )
  }

  return (await response.json()) as KnowledgeListResponse
}
