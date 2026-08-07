import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { KbEntryCard, KbListSkeleton, EmptyGroupState, type KbEntryCardLinkProps } from '../lib'
import {
  fetchKnowledgeBase,
  KnowledgeBaseError,
  type KnowledgeListResponse,
} from '../api/knowledge-list'

/**
 * Adapts React Router's `Link` to `KbEntryCard`'s `linkComponent` contract —
 * mirrors `InvestigationCardRouterLink` in `InvestigationListPage.tsx`.
 */
function KbEntryCardRouterLink({ href, children, ...rest }: KbEntryCardLinkProps) {
  return (
    <Link to={href} {...rest}>
      {children}
    </Link>
  )
}

/** The search query's URL param name (FR53/FR29). */
const QUERY_PARAM = 'q'

/** Matches the Jinja `hx-trigger="keyup changed delay:300ms"` debounce (`knowledge/index.html`). */
const SEARCH_DEBOUNCE_MS = 300

/**
 * KnowledgeBasePage — the Knowledge Base browse/search view (Task 5.1,
 * FR28/FR29/FR53).
 *
 * A single view serves both modes, distinguished purely by whether `q` is
 * set in the URL — there is no separate `/app/knowledge/search` route
 * (`App.tsx`/`AppLayout.tsx` are final and only register `knowledge` +
 * `knowledge/:entryId`; per `docs/design/route-parity-targets.md` §2 this is
 * an explicitly allowed implementer choice, "query param on /app/knowledge").
 * Both modes hit the same JSON endpoint (`GET /api/v1/knowledge/`,
 * `knowledge_list_json` in `ui/beeper_ui/routes/knowledge.py`), which
 * internally branches on `q` to reuse `KBService.search_semantic` (search)
 * vs. `KBService.list_recent_entries` (browse) — the exact same branch the
 * Jinja `kb_search()`/`kb_index()` routes take.
 *
 * ── Permalink (FR53) ──
 * `q` lives in `?q=` via `useSearchParams` — not local `useState` and not
 * `sessionStorage` — following Task 3.1's `InvestigationListPage.tsx`
 * pattern exactly (URL is the single source of truth; a local `inputValue`
 * mirrors it ONLY so the text box can update on every keystroke without
 * firing a fetch on every keystroke — the URL itself only updates once the
 * user pauses, debounced by `SEARCH_DEBOUNCE_MS`, matching the Jinja app's
 * own 300ms debounce). Cold-loading `/app/knowledge?q=<query>` reproduces
 * the identical filtered result with no prior in-app interaction.
 *
 * ── Empty / error states (never a blank frame) ──
 * - Cold load: `KbListSkeleton` (NFR19).
 * - Fetch-level failure (network/HTTP): an alert banner, mirroring
 *   `InvestigationListPage`'s error box.
 * - Soft/expected condition from the response body (e.g. search not
 *   configured — no OPENAI_API_KEY): an inline notice, matching the Jinja
 *   `_search_results.html` `.search-error` branch.
 * - Zero entries with a query: "No results found" (FR29's negative case).
 * - Zero entries with no query (empty KB): "No knowledge base entries yet"
 *   (mirrors the Jinja `_entry_list.html` `empty_state()` macro).
 */
export function KnowledgeBasePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const urlQuery = searchParams.get(QUERY_PARAM) ?? ''

  const [inputValue, setInputValue] = useState(urlQuery)
  const [response, setResponse] = useState<KnowledgeListResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Keep the text box in sync when the URL changes from outside a keystroke
  // (browser back/forward, a pasted permalink) — without this, navigating
  // back to a `?q=` URL wouldn't repopulate the box.
  useEffect(() => {
    setInputValue(urlQuery)
  }, [urlQuery])

  // Debounce: push the URL 300ms after the user stops typing (not on every
  // keystroke) — this IS the fetch trigger (see the effect below, keyed on
  // `urlQuery`), matching the Jinja `hx-trigger="keyup changed delay:300ms"`.
  useEffect(() => {
    if (inputValue === urlQuery) return
    const timeout = setTimeout(() => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          if (inputValue) next.set(QUERY_PARAM, inputValue)
          else next.delete(QUERY_PARAM)
          return next
        },
        { replace: true },
      )
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timeout)
  }, [inputValue, urlQuery, setSearchParams])

  useEffect(() => {
    const controller = new AbortController()
    setResponse(null)
    setError(null)

    fetchKnowledgeBase(urlQuery ? { q: urlQuery } : undefined, controller.signal)
      .then((data) => {
        setResponse(data)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setError(
          err instanceof KnowledgeBaseError ? err.message : 'Unable to connect to the Beeper operator.',
        )
      })

    return () => controller.abort()
  }, [urlQuery])

  const isLoading = response === null && error === null
  const entries = response?.entries ?? []
  const isSearching = urlQuery.length > 0

  return (
    <div data-testid="knowledge-base-page" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">Knowledge Base</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Browse investigations, runbooks, and corrections
          </p>
        </div>
        {/*
          Plain <a> (full page nav), not React Router `Link`: these three
          affordances lead to Jinja-only routes explicitly out of Task 5.1's
          scope (docs/design/route-parity-targets.md §2 carve-out list —
          /knowledge/import, /knowledge/learning, /knowledge/trust-settings).
          Keeping them as real links (rather than dropping them) preserves
          FR50 "no capability regression" — Jinja still serves these pages
          unchanged, so a full navigation away from the SPA works correctly.
        */}
        <div className="flex flex-wrap items-center gap-2">
          <a
            href="/knowledge/learning"
            className="rounded bg-surface-raised px-3 py-1.5 text-sm font-medium text-text-secondary transition-colors duration-150 hover:bg-surface-overlay hover:text-text-primary motion-reduce:transition-none"
          >
            Learning Insights
          </a>
          <a
            href="/knowledge/trust-settings"
            className="rounded bg-surface-raised px-3 py-1.5 text-sm font-medium text-text-secondary transition-colors duration-150 hover:bg-surface-overlay hover:text-text-primary motion-reduce:transition-none"
          >
            Trust Settings
          </a>
          <a
            href="/knowledge/import"
            className="rounded bg-primary px-3 py-1.5 text-sm font-medium text-text-primary transition-colors duration-150 hover:bg-primary-hover motion-reduce:transition-none"
          >
            Import Runbook
          </a>
        </div>
      </div>

      <div>
        <label htmlFor="kb-search" className="sr-only">
          Search knowledge base
        </label>
        <input
          id="kb-search"
          type="search"
          autoComplete="off"
          value={inputValue}
          onChange={(event) => setInputValue(event.target.value)}
          placeholder="Search knowledge base..."
          // Task 5.5 a11y-audit finding: aligned to the app's established
          // focus-visible convention (Sidebar/AppShell/MetricsFilterBar) —
          // was `focus:ring` (fires on any focus, incl. mouse click) with no
          // `ring-offset-2`.
          className="w-full rounded-lg border border-surface-overlay bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
        />
      </div>

      {error ? (
        <div
          role="alert"
          className="rounded-md border border-status-critical/30 bg-surface-raised p-4 text-sm text-status-critical"
        >
          <p className="font-semibold">Unable to fetch KB entries</p>
          <p className="mt-1 text-text-secondary">{error}</p>
        </div>
      ) : null}

      {isLoading ? <KbListSkeleton /> : null}

      {!isLoading && !error && response?.error ? (
        <div className="rounded-md border border-status-critical/30 bg-surface-raised px-4 py-3 text-sm text-status-critical">
          {response.error}
        </div>
      ) : null}

      {!isLoading && !error && !response?.error ? (
        entries.length > 0 ? (
          <div className="flex flex-col gap-3">
            {isSearching && response && !response.has_exact_matches ? (
              <p className="px-1 text-xs text-text-muted">
                No exact matches found. Showing related entries.
              </p>
            ) : null}
            <div data-testid="kb-entry-list" className="flex flex-col gap-2">
              {entries.map((entry) => (
                <KbEntryCard
                  key={entry.entry_id}
                  title={entry.title}
                  entryType={entry.entry_type}
                  service={entry.service}
                  date={formatDate(entry.created_at)}
                  author={entry.author}
                  snippet={entry.snippet}
                  tags={entry.tags}
                  relevanceScore={isSearching ? entry.relevance_score : null}
                  href={`/knowledge/${encodeURIComponent(entry.entry_id)}`}
                  linkComponent={KbEntryCardRouterLink}
                />
              ))}
            </div>
          </div>
        ) : isSearching ? (
          <EmptyGroupState
            title="No results found"
            description={`No entries match "${urlQuery}".`}
          />
        ) : (
          <EmptyGroupState
            title="No knowledge base entries yet"
            description="Entries appear automatically as Beeper completes investigations. You can also import runbooks to seed the knowledge base."
          />
        )
      ) : null}
    </div>
  )
}

/** "2026-06-01T10:00:00+00:00" -> "2026-06-01" — view-local date formatting, matching `KbEntryCard.date`'s pre-formatted-string contract. */
function formatDate(isoString: string | null): string | null {
  if (!isoString) return null
  return isoString.slice(0, 10)
}
