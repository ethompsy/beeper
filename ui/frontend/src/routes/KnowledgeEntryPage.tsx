import { useEffect, useRef } from 'react'
import { Link, useParams } from 'react-router-dom'
import { DetailSkeleton, KbEntryCard, KbEntryNotFound, type KbEntryCardLinkProps } from '../lib'
import { useKnowledgeEntry } from './useKnowledgeEntry'
import type { InvestigationLink } from '../api/knowledge-detail'

/**
 * Demotes headings inside the sanitized markdown body (`content_html`) so
 * they can never collide with the page's own `<h1>` or skip a level
 * relative to it (Task 5.5 a11y-audit finding — axe `heading-order` /
 * WCAG 1.3.1 "Info and Relationships"). Author-supplied runbook/investigation
 * markdown is free to emit any of h1-h6 (`ALLOWED_TAGS` in
 * `ui/beeper_ui/utils/markdown_utils.py`, server-sanitized but NOT
 * level-constrained). This shifts the *shallowest* heading actually present
 * in the content to h2 — nesting immediately under the page's real `<h1>`,
 * matching the "Incident Details"/"Related Entries" sections that already
 * use h2 — and preserves every other heading's depth relative to it,
 * clamped to h6. A DOM pass (not a markdown-source change) because the
 * content arrives pre-rendered HTML; runs client-side only, no BFF/Python
 * change.
 */
function normalizeContentHeadings(container: HTMLElement): void {
  const headings = Array.from(container.querySelectorAll<HTMLHeadingElement>('h1, h2, h3, h4, h5, h6'))
  if (headings.length === 0) return

  const levelOf = (el: HTMLHeadingElement) => Number(el.tagName[1])
  const shift = 2 - Math.min(...headings.map(levelOf))
  if (shift === 0) return

  for (const el of headings) {
    const newLevel = Math.min(6, Math.max(2, levelOf(el) + shift))
    const replacement = document.createElement(`h${newLevel}`)
    replacement.innerHTML = el.innerHTML
    for (const attr of Array.from(el.attributes)) {
      replacement.setAttribute(attr.name, attr.value)
    }
    el.replaceWith(replacement)
  }
}

/** Adapts React Router's `Link` to `KbEntryCard`'s `linkComponent` contract — mirrors `KnowledgeBasePage.tsx`. */
function KbEntryCardRouterLink({ href, children, ...rest }: KbEntryCardLinkProps) {
  return (
    <Link to={href} {...rest}>
      {children}
    </Link>
  )
}

const ENTRY_TYPE_STYLES: Record<string, string> = {
  investigation: 'bg-primary/15 text-primary border border-primary/30',
  runbook: 'bg-status-healthy/15 text-status-healthy border border-status-healthy/30',
  correction: 'bg-status-warning/15 text-status-warning border border-status-warning/30',
  proven_fix: 'bg-status-healthy/15 text-status-healthy border border-status-healthy/30',
}
const DEFAULT_ENTRY_TYPE_STYLE = 'bg-surface-overlay text-text-muted border border-surface-overlay'

function formatEntryTypeLabel(entryType: string): string {
  const spaced = entryType.replace(/_/g, ' ')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

/** "2026-06-01T10:00:00+00:00" -> "2026-06-01 10:00 UTC", mirroring the Jinja `entry.html` date format. */
function formatCreatedAt(isoString: string | null): string | null {
  if (!isoString) return null
  const [datePart, timePart] = isoString.split('T')
  if (!timePart) return datePart
  return `${datePart} ${timePart.slice(0, 5)} UTC`
}

/**
 * KnowledgeEntryPage — the Knowledge Base entry-detail view (Task 5.1,
 * FR31/FR53).
 *
 * Fetches `GET /api/v1/knowledge/<entryId>` (`knowledge_entry_json` in
 * `ui/beeper_ui/routes/knowledge.py`) via `useKnowledgeEntry`, which mirrors
 * `useInvestigationDetail` exactly — same loading/ok/not-found/error state
 * machine, same render pattern as `InvestigationDetailPage.tsx`.
 *
 * ── Scope (deliberate, per docs/design/route-parity-targets.md §2) ──
 * This is a VIEW-only migration (FR31: "Users can view Knowledge Base entry
 * details including past incident context"). The write/action affordances
 * the Jinja `entry.html` also renders — Confirm as Accurate, History, Edit,
 * Suggest Correction, Corrections — all lead to routes explicitly carved out
 * of Task 5.1's scope (`/knowledge/<id>/edit`, `/<id>/history`,
 * `/<id>/corrections*`) and are intentionally NOT reproduced here. FR50's
 * "no capability regression" still holds: those actions remain reachable at
 * their unchanged Jinja URLs (not linked from this page, since surfacing
 * them would mean either building unscoped write flows or linking out to a
 * different visual system mid-page — reported as a follow-up, not papered
 * over).
 *
 * ── Incident details (FR31 "past incident context") ──
 * The FR31 structured fields (`root_cause`/`resolution`/`affected_services`)
 * plus the bi-directional investigation links (`source_investigation`/
 * `contributing_investigations`) render as a labeled "Incident Details"
 * section, exactly mirroring the Jinja `entry.html` `incident-details`
 * block — shown only when at least one of those fields is present. The
 * investigation links use React Router's `Link` (client-side transition
 * into the already-migrated `/app/investigations/:id` detail view — Phase
 * 1), not a full page reload.
 */
export function KnowledgeEntryPage() {
  const { entryId } = useParams<{ entryId: string }>()
  const query = useKnowledgeEntry(entryId)
  const contentRef = useRef<HTMLDivElement>(null)
  const entry = query.status === 'ok' ? query.data.entry : null
  const contentHtml = entry?.content_html ?? null

  useEffect(() => {
    if (contentHtml != null && contentRef.current) {
      normalizeContentHeadings(contentRef.current)
    }
  }, [contentHtml])

  if (query.status === 'not-found') {
    return <KbEntryNotFound entryId={entryId ?? ''} />
  }

  const relatedEntries = query.status === 'ok' ? query.data.related_entries : []
  const sourceInvestigation = query.status === 'ok' ? query.data.source_investigation : null
  const contributingInvestigations = query.status === 'ok' ? query.data.contributing_investigations : []
  const entryTypeLabel = entry ? formatEntryTypeLabel(entry.entry_type || 'unknown') : null
  const hasIncidentDetails =
    entry != null &&
    (Boolean(entry.root_cause) ||
      Boolean(entry.resolution) ||
      entry.affected_services.length > 0 ||
      sourceInvestigation != null ||
      contributingInvestigations.length > 0)

  return (
    <article data-testid="knowledge-entry-page" className="flex max-w-4xl flex-col gap-4">
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          {/*
            `id="detail-summary-heading"` — shared contract with
            `useRouteFocusManagement` (also used by the investigation
            detail's `SummaryHeader`). `AppLayout`'s `isFocusManagedDetailRoute`
            now also covers `/knowledge/:entryId`, so this heading receives
            focus on entry (incl. cold permalink load), same as investigation
            detail (WCAG 2.4.3, Task 5.5 a11y-audit finding). Only one of the
            two detail routes is ever mounted at a time, so the shared id
            never collides in the live DOM.
            Rendered UNCONDITIONALLY across loading/ok/error (title falls
            back to the raw `entryId` before the fetch resolves) — this is
            deliberate, not decorative: `useRouteFocusManagement` fires
            exactly ONCE, in `AppLayout`, right after this route first
            mounts. If the heading only existed once `query.status === 'ok'`
            (its original form), that one-shot effect would run while the
            page was still showing `DetailSkeleton` — before the heading
            existed — and silently no-op, permanently missing the focus
            move on every cold load (caught by
            `e2e/keyboard-navigation.spec.ts`). Mirrors
            `InvestigationDetailPage.tsx`'s `SummaryHeader`, which documents
            this exact same constraint.
          */}
          <h1 id="detail-summary-heading" className="min-w-0 text-xl font-semibold text-text-primary">
            {entry?.title ?? entryId ?? ''}
          </h1>
          {entry ? (
            <span
              data-slot="kb-type-badge"
              data-entry-type={entry.entry_type}
              className={
                'inline-flex shrink-0 items-center rounded px-2 py-0.5 text-xs font-medium ' +
                (ENTRY_TYPE_STYLES[entry.entry_type] ?? DEFAULT_ENTRY_TYPE_STYLE)
              }
            >
              {entryTypeLabel}
            </span>
          ) : null}
        </div>
        {entry ? (
          <div className="flex flex-wrap items-center gap-2 text-xs text-text-secondary">
            {entry.service ? (
              <span data-field="service" className="rounded bg-surface-overlay px-2 py-0.5 font-mono">
                {entry.service}
              </span>
            ) : null}
            {entry.created_at ? (
              <span data-field="created-at" className="text-text-muted">
                Created: {formatCreatedAt(entry.created_at)}
              </span>
            ) : null}
            {entry.author ? (
              <span data-field="author" className="text-text-muted">
                by {entry.author}
              </span>
            ) : null}
            <span data-field="version" className="font-mono text-text-muted">
              v{entry.version}
            </span>
            {entry.validation_status ? (
              <span
                data-field="validation-status"
                className="rounded border border-surface-overlay bg-surface-overlay px-2 py-0.5 font-medium text-text-secondary"
              >
                {entry.validation_status}
              </span>
            ) : null}
            {entry.auto_published ? (
              <span className="rounded border border-primary/30 bg-primary/15 px-2 py-0.5 font-medium text-primary">
                Auto-published
              </span>
            ) : null}
          </div>
        ) : null}
        {entry && entry.tags.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {entry.tags.map((tag) => (
              <span key={tag} className="rounded bg-surface-overlay px-1.5 py-0.5 text-xs text-text-muted">
                {tag}
              </span>
            ))}
          </div>
        ) : null}
      </header>

      {query.status === 'loading' ? <DetailSkeleton /> : null}

      {query.status === 'error' ? (
        <p role="alert" className="text-base text-status-critical">
          Unable to load this Knowledge Base entry right now.
        </p>
      ) : null}

      {entry ? (
        <>
          {hasIncidentDetails ? (
            <section
              aria-label="Incident details"
              className="rounded-lg border border-surface-overlay bg-surface-raised p-4"
            >
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-text-secondary">
                Incident Details
              </h2>
              <dl className="grid grid-cols-1 gap-3">
                {entry.root_cause ? (
                  <div>
                    <dt className="mb-1 text-xs text-text-muted">Root Cause</dt>
                    <dd className="text-sm text-text-primary">{entry.root_cause}</dd>
                  </div>
                ) : null}
                {entry.resolution ? (
                  <div>
                    <dt className="mb-1 text-xs text-text-muted">Resolution</dt>
                    <dd className="text-sm text-text-primary">{entry.resolution}</dd>
                  </div>
                ) : null}
                {entry.affected_services.length > 0 ? (
                  <div>
                    <dt className="mb-1 text-xs text-text-muted">Affected Services</dt>
                    <dd className="flex flex-wrap gap-1.5">
                      {entry.affected_services.map((svc) => (
                        <span
                          key={svc}
                          className="rounded bg-surface-overlay px-2 py-0.5 font-mono text-xs text-text-secondary"
                        >
                          {svc}
                        </span>
                      ))}
                    </dd>
                  </div>
                ) : null}
                {sourceInvestigation != null || contributingInvestigations.length > 0 ? (
                  <div>
                    <dt className="mb-1 text-xs text-text-muted">Source Investigation</dt>
                    <dd className="flex flex-col gap-1.5">
                      {sourceInvestigation != null ? (
                        <InvestigationLinkRow link={sourceInvestigation} label="Source" />
                      ) : null}
                      {contributingInvestigations.map((link) => (
                        <InvestigationLinkRow key={link.investigation_id} link={link} label="Contributing" />
                      ))}
                    </dd>
                  </div>
                ) : null}
              </dl>
            </section>
          ) : null}

          {/*
            content_html is sanitized server-side (render_markdown() ->
            bleach.clean()); see api/knowledge-detail.ts doc. `ref={contentRef}`
            feeds `normalizeContentHeadings` (above) so any h1-h6 the markdown
            source emits gets demoted to nest correctly under the page's own
            `<h1>` — see that function's doc comment.
          */}
          <div
            ref={contentRef}
            data-testid="kb-entry-content"
            className="rounded-lg border border-surface-overlay bg-surface-raised p-4 text-sm leading-relaxed text-text-secondary"
            dangerouslySetInnerHTML={{ __html: entry.content_html }}
          />

          {relatedEntries.length > 0 ? (
            <section aria-label="Related entries" className="mt-2 flex flex-col gap-2">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
                Related Entries
              </h2>
              {relatedEntries.map((related) => (
                <KbEntryCard
                  key={related.entry_id}
                  title={related.title}
                  entryType={related.entry_type}
                  service={related.service}
                  date={related.created_at ? related.created_at.slice(0, 10) : null}
                  href={`/knowledge/${encodeURIComponent(related.entry_id)}`}
                  linkComponent={KbEntryCardRouterLink}
                />
              ))}
            </section>
          ) : null}
        </>
      ) : null}
    </article>
  )
}

function InvestigationLinkRow({ link, label }: { link: InvestigationLink; label: string }) {
  const badgeClass =
    label === 'Source'
      ? 'bg-primary/15 text-primary border border-primary/30'
      : 'bg-surface-overlay text-text-secondary border border-surface-overlay'
  return (
    <span className="flex items-center gap-2">
      <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${badgeClass}`}>
        {label}
      </span>
      <Link
        to={`/investigations/${encodeURIComponent(link.investigation_id)}`}
        className="font-mono text-sm text-primary hover:text-primary-hover"
      >
        {link.investigation_id}
      </Link>
    </span>
  )
}
