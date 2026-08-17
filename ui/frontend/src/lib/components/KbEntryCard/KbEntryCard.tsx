import type { AnchorHTMLAttributes, ComponentType, ReactNode } from 'react'
import { cn } from '../../utils/cn'

/**
 * KbEntryCard — list-item primitive representing one Knowledge Base entry
 * (Task 5.1). Mirrors `InvestigationCard`'s structure/conventions exactly
 * (`linkComponent` injection, single-link accessible card, token-only
 * styling) so the two list primitives read as one visual system.
 *
 * Reused across three surfaces that all render the same "one KB entry" fact
 * set: the browse list, search results (with `relevanceScore`), and the
 * entry-detail page's "Related Entries" section — the Jinja templates keep
 * these as three separate near-duplicate blocks
 * (`_entry_card.html`/`_search_results.html`/`_related.html`); this
 * component consolidates them into one primitive.
 *
 * `entryType` badge colors mirror the Jinja `kb_type_badge` macro
 * (`ui/beeper_ui/templates/components/kb.html`) exactly — kept as its own
 * badge (not `StatusBadge`) because entry-type is a fourth, distinct
 * taxonomy axis from `StatusBadge`'s three (job phase / workflow state /
 * pipeline health) documented in that component's own header comment; KB
 * entries never carry any of those three.
 */
export interface KbEntryCardLinkProps {
  href: string
  className?: string
  'aria-label'?: string
  'data-slot'?: string
  children?: ReactNode
  [key: string]: unknown
}

export interface KbEntryCardProps extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> {
  /** Entry title (text-base, font-semibold). */
  title: string
  /** KB entry type — `investigation` | `runbook` | `correction` | `proven_fix` | other. */
  entryType: string
  /** Service name, when the entry is scoped to one. Omitted from the DOM entirely when absent. */
  service?: string | null
  /** Pre-formatted display date (e.g. "2026-06-01"). Formatting is a view concern, matching `InvestigationCard`'s `timestamp` prop. */
  date?: string | null
  author?: string | null
  /** Plain-text content preview. Omitted from the DOM entirely when absent. */
  snippet?: string | null
  tags?: string[]
  /**
   * Semantic-search relevance score (0.0–1.0), rendered as a percentage.
   * Omit for browse-mode cards (no query, no score) — mirrors the Jinja
   * search-results-only `relevance-score` span.
   */
  relevanceScore?: number | null
  /** href for the underlying link — the whole card is the click target (a11y: single link, no nested interactive elements). */
  href: string
  /**
   * Render-prop-free link component injection — pass React Router's `Link`
   * for client-side navigation, or omit for a plain `<a>` (default,
   * Storybook-safe). Mirrors `InvestigationCard`'s `linkComponent` contract.
   */
  linkComponent?: ComponentType<KbEntryCardLinkProps>
}

const ENTRY_TYPE_STYLES: Record<string, string> = {
  // Task 6.0: solid `bg-surface-overlay` (not translucent `bg-primary/15`) —
  // this card's own background swaps to `surface-overlay` on hover, and a
  // translucent primary tint blended over THAT (rather than its resting
  // `surface-raised`) drops below 4.5:1. A solid backdrop is immune to the
  // ambient-background shift. See src/test/contrast.test.ts.
  investigation: 'bg-surface-overlay text-primary border border-primary/30',
  runbook: 'bg-status-healthy/15 text-status-healthy border border-status-healthy/30',
  correction: 'bg-status-warning/15 text-status-warning border border-status-warning/30',
  proven_fix: 'bg-status-healthy/15 text-status-healthy border border-status-healthy/30',
}
const DEFAULT_ENTRY_TYPE_STYLE = 'bg-surface-overlay text-text-muted border border-surface-overlay'

/** "proven_fix" -> "Proven fix" — mirrors the Jinja macro's `replace('_', ' ')|capitalize`. */
function formatEntryTypeLabel(entryType: string): string {
  const spaced = entryType.replace(/_/g, ' ')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

function DefaultLink({ href, children, ...rest }: KbEntryCardLinkProps) {
  return (
    <a href={href} {...rest}>
      {children}
    </a>
  )
}

export function KbEntryCard({
  title,
  entryType,
  service,
  date,
  author,
  snippet,
  tags,
  relevanceScore,
  href,
  linkComponent: LinkComponent = DefaultLink,
  className,
  ...rest
}: KbEntryCardProps) {
  const entryTypeLabel = formatEntryTypeLabel(entryType || 'unknown')

  return (
    <LinkComponent
      data-slot="kb-entry-card"
      href={href}
      aria-label={`${title}, ${entryTypeLabel} knowledge base entry${service ? ` for ${service}` : ''}`}
      className={cn(
        'flex flex-col gap-2 rounded-md bg-surface-raised p-4',
        'transition-colors motion-reduce:transition-none hover:bg-surface-overlay',
        className,
      )}
      {...rest}
    >
      <div className="flex items-start justify-between gap-3">
        <span className="min-w-0 truncate text-base font-semibold text-text-primary">{title}</span>
        <span
          data-slot="kb-type-badge"
          data-entry-type={entryType}
          className={cn(
            'inline-flex shrink-0 items-center rounded px-2 py-0.5 text-xs font-medium',
            ENTRY_TYPE_STYLES[entryType] ?? DEFAULT_ENTRY_TYPE_STYLE,
          )}
        >
          {entryTypeLabel}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-xs text-text-secondary">
        {service ? (
          <span data-field="service" className="rounded bg-surface-overlay px-2 py-0.5 font-mono">
            {service}
          </span>
        ) : null}
        {date ? <span data-field="date">{date}</span> : null}
        {author ? <span data-field="author">by {author}</span> : null}
        {relevanceScore != null ? (
          <span data-field="relevance-score" className="font-mono text-text-secondary">
            {Math.round(relevanceScore * 100)}% relevant
          </span>
        ) : null}
      </div>
      {snippet ? (
        <p className="text-sm leading-relaxed text-text-secondary" data-field="snippet">
          {snippet}
        </p>
      ) : null}
      {tags && tags.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {tags.slice(0, 5).map((tag) => (
            <span key={tag} className="rounded bg-surface-overlay px-1.5 py-0.5 text-xs text-text-muted">
              {tag}
            </span>
          ))}
        </div>
      ) : null}
    </LinkComponent>
  )
}
