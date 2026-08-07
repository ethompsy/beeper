/**
 * knowledge-detail.ts — REST client for `GET /api/v1/knowledge/<entryId>`
 * (Task 5.1). Plain `fetch`, no react-query — matches `investigation-detail.ts`'s
 * no-dependency design and its "never throws, resolves to a discriminated
 * result" contract, so `KnowledgeEntryPage` can follow the exact same
 * loading/ok/not-found/error render pattern as `InvestigationDetailPage`.
 *
 * ── Response shape (Task 5.1) ──────────────────────────────────────────
 * The backend endpoint (`ui/beeper_ui/routes/knowledge.py`,
 * `knowledge_entry_json`) returns:
 *   { entry: { id, entry_id, entry_type, title, service, created_at,
 *              updated_at, author, version, tags, validation_status,
 *              auto_published, relevance_score, content_html,
 *              root_cause, resolution, affected_services },
 *     related_entries: [ <KnowledgeEntrySummary>, ... ],
 *     source_investigation: { investigation_id, relationship } | null,
 *     contributing_investigations: [ { investigation_id, relationship }, ... ] }
 *
 * `content_html` is already-sanitized HTML (server-side `render_markdown()`,
 * the same sanitizer the Jinja `entry.content|markdown` filter uses) — the
 * React view renders it directly rather than shipping a second markdown
 * parser/sanitizer to the client.
 */
import type { KnowledgeEntrySummary } from './knowledge-list'

export interface KnowledgeEntryDetail {
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
  relevance_score: number | null
  /** Sanitized HTML — safe to render via `dangerouslySetInnerHTML` (server already sanitizes via bleach). */
  content_html: string
  /** FR31 structured incident fields — null/empty when the authoring flow didn't populate them. */
  root_cause: string | null
  resolution: string | null
  affected_services: string[]
}

export interface InvestigationLink {
  investigation_id: string
  relationship: string
}

export interface KnowledgeEntryDetailDto {
  entry: KnowledgeEntryDetail
  related_entries: KnowledgeEntrySummary[]
  source_investigation: InvestigationLink | null
  contributing_investigations: InvestigationLink[]
}

export type KnowledgeEntryResult =
  | { kind: 'ok'; data: KnowledgeEntryDetailDto }
  | { kind: 'not-found' }
  | { kind: 'error'; error: unknown }

/**
 * Fetch KB entry detail JSON for `entryId`.
 *
 * Never throws — network failures, non-2xx responses (other than 404), and
 * JSON parse errors all resolve to `{ kind: 'error' }` so the view can
 * render a retry-safe error state instead of an unhandled rejection. A 404
 * resolves to the distinct `{ kind: 'not-found' }` variant so the view can
 * render an in-shell "not found" message (mirrors
 * `fetchInvestigationDetail`'s exact contract).
 */
export async function fetchKnowledgeEntry(
  entryId: string,
  init?: RequestInit,
): Promise<KnowledgeEntryResult> {
  let response: Response
  try {
    response = await fetch(`/api/v1/knowledge/${encodeURIComponent(entryId)}`, init)
  } catch (error) {
    return { kind: 'error', error }
  }

  if (response.status === 404) {
    return { kind: 'not-found' }
  }

  if (!response.ok) {
    return { kind: 'error', error: new Error(`Unexpected status ${response.status}`) }
  }

  try {
    const data = (await response.json()) as KnowledgeEntryDetailDto
    return { kind: 'ok', data }
  } catch (error) {
    return { kind: 'error', error }
  }
}
