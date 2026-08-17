import { useEffect, useState } from 'react'
import { StatusBadge, EmptyGroupState, type StatusBadgeVariant } from '../lib'
import { fetchSources, type SourceListItem } from '../api/sources-list'

/**
 * SourcesPage — the Observe > Sources view (Task 5.3, FR34).
 *
 * Parity target: `templates/sources/list.html` +
 * `templates/sources/_list_content.html` (`sources_bp.list_sources`,
 * `ui/beeper_ui/routes/sources.py`), per
 * `docs/design/route-parity-targets.md` §4a. Data comes from
 * `GET /api/v1/sources/` (`src/api/sources-list.ts`), a thin JSON
 * serialization of `SourceService.get_sources()` — including that
 * service's dedup-by-name behavior (NFR12), so nothing is re-deduped here.
 *
 * The Jinja view auto-refreshes via `hx-trigger="every 5s"`
 * (`sources/list.html:12`); this is replaced by a client-side
 * `setInterval` refetch at the same 5s cadence. Each refresh fully replaces
 * the rendered `sources`/`error` state — matching the Jinja partial's own
 * full-innerHTML-swap semantics (a failed refresh shows the error state
 * even if a prior refresh had data, exactly as `hx-swap="innerHTML"` would).
 *
 * No permalink state (§4a: "none") — this view has no user-set filter.
 */

const REFRESH_INTERVAL_MS = 5_000

/**
 * Maps an operator source status string to the `StatusBadge` connection
 * variant, mirroring the Jinja `source_status_badge` macro exactly
 * (`ui/beeper_ui/templates/components/status.html`):
 * `connected` → green; `error`/`disconnected`/`failed` → red; else → gray.
 */
function deriveSourceStatusVariant(status: string): StatusBadgeVariant {
  if (status === 'connected') return 'connected'
  if (status === 'error' || status === 'disconnected' || status === 'failed') return 'disconnected'
  return 'unknown'
}

export function SourcesPage() {
  const [sources, setSources] = useState<SourceListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    function load() {
      fetchSources(controller.signal)
        .then((data) => {
          setSources(data)
          setError(null)
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted) return
          setError(err instanceof Error ? err.message : 'Unable to connect to the Beeper operator.')
        })
    }

    load()
    const intervalId = setInterval(load, REFRESH_INTERVAL_MS)

    return () => {
      controller.abort()
      clearInterval(intervalId)
    }
  }, [])

  const isLoading = sources === null && error === null

  return (
    <div data-testid="sources-page" className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold text-text-primary">Data Sources</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Configured Prometheus and Loki data sources and their live connection status.
        </p>
      </div>

      {/*
        Task 5.5 a11y-audit finding: the skeleton -> data/error transition
        (a 5s `setInterval` refetch, `REFRESH_INTERVAL_MS`) wasn't announced
        to assistive tech at all — the error block below has `role="alert"`
        (implicit assertive live region, so failures already announce), and
        the skeleton has `role="status"` (implicit polite region, so "start
        of loading" announces), but nothing announced when a refresh
        actually finished successfully. This sr-only status text is the
        narrow fix: it only changes text (and therefore only re-announces)
        on a genuine state transition — first load, or a status flip for one
        of the sources (e.g. `connected` -> `disconnected` between polls) —
        not on every identical 5s poll, since unchanged text triggers no DOM
        mutation for the live region to pick up.
      */}
      <p role="status" aria-live="polite" className="sr-only">
        {!isLoading && !error && sources
          ? `${sources.length} source${sources.length === 1 ? '' : 's'} loaded, ${
              sources.filter((s) => s.status === 'connected').length
            } connected.`
          : ''}
      </p>

      {error ? (
        <div role="alert" className="rounded-lg border border-status-critical/30 bg-surface-raised p-4">
          <h2 className="text-base font-semibold text-status-critical">Unable to fetch sources</h2>
          <p className="mt-1 text-sm text-text-secondary">{error}</p>
          <p className="mt-1 text-sm text-text-muted">Make sure the Beeper operator is running and accessible.</p>
        </div>
      ) : null}

      {isLoading ? <SourcesSkeleton /> : null}

      {!isLoading && !error ? (
        sources && sources.length > 0 ? (
          <SourcesTable sources={sources} />
        ) : (
          <EmptyGroupState
            title="No data sources configured"
            description="Create a Source custom resource in your Kubernetes cluster to connect Prometheus or Loki and start ingesting telemetry."
          />
        )
      ) : null}
    </div>
  )
}

function SourcesSkeleton() {
  return (
    <div
      data-testid="sources-skeleton"
      role="status"
      aria-label="Loading sources"
      className="flex flex-col gap-2 rounded-lg border border-surface-overlay bg-surface-raised p-4 animate-pulse motion-reduce:animate-none"
    >
      {Array.from({ length: 3 }, (_, index) => (
        <div key={index} className="h-6 rounded bg-surface-overlay" />
      ))}
    </div>
  )
}

function SourcesTable({ sources }: { sources: SourceListItem[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-surface-overlay bg-surface-raised">
      <table className="w-full border-collapse text-sm">
        {/* Task 5.5 a11y-audit finding: no accessible name for the table (WCAG 1.3.1 / axe `table-fake-caption` context). sr-only — the visible `<h1>` above already names the view. */}
        <caption className="sr-only">Configured data sources and their live connection status</caption>
        <thead>
          <tr className="border-b border-surface-overlay text-left">
            <th scope="col" className="px-4 py-2.5 font-medium text-text-secondary">
              Status
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium text-text-secondary">
              Name
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium text-text-secondary">
              Type
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium text-text-secondary">
              Endpoint
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium text-text-secondary">
              Last Seen
            </th>
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <SourceRow key={source.name} source={source} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SourceRow({ source }: { source: SourceListItem }) {
  return (
    <>
      <tr className="border-b border-surface-overlay/50 last:border-b-0">
        <td className="px-4 py-3 align-top">
          <StatusBadge variant={deriveSourceStatusVariant(source.status)} />
        </td>
        <td className="px-4 py-3 align-top font-medium text-text-primary">{source.name}</td>
        <td className="px-4 py-3 align-top capitalize text-text-secondary">{source.type}</td>
        <td className="px-4 py-3 align-top">
          <code className="rounded bg-surface-base px-1.5 py-0.5 font-mono text-xs text-text-muted">
            {source.endpoint}
          </code>
        </td>
        <td className="whitespace-nowrap px-4 py-3 align-top text-text-muted">
          {source.last_check ?? 'Never'}
        </td>
      </tr>
      {source.error ? (
        <tr className="border-b border-surface-overlay/50 last:border-b-0">
          <td colSpan={5} className="px-4 py-2 text-xs text-status-critical">
            <strong className="font-semibold">Error:</strong> {source.error.message}
            {source.error.details ? (
              <details className="mt-1">
                <summary className="cursor-pointer text-text-muted">Show technical details</summary>
                <pre className="mt-1 overflow-x-auto rounded bg-surface-base p-2 text-text-muted">
                  {source.error.details}
                </pre>
              </details>
            ) : null}
          </td>
        </tr>
      ) : null}
    </>
  )
}
