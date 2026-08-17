/**
 * AppLayout.test.tsx (Task 5.0b)
 *
 * Covers the three behaviors Task 5.0b changed in `AppLayout.tsx`:
 *
 *   1. Route-derived active nav item — every one of the six `NAV_GROUPS`
 *      destinations (plus both detail routes, which highlight their parent
 *      list item) resolves `aria-current="page"` on the correct sidebar
 *      link, and the catch-all route highlights nothing.
 *   2. Route-derived breadcrumb — the investigation-detail breadcrumb is a
 *      REGRESSION GUARD (byte-identical structure/copy to the pre-5.0b
 *      hardcoded version); every other route gets its own nav label (detail
 *      routes with a parent list render "Parent > id", flat routes render
 *      just their label), and the catch-all renders no breadcrumb.
 *   3. Every newly-registered placeholder route renders inside the shell
 *      (sidebar present) rather than falling through to the catch-all.
 *
 * `window.matchMedia` is mocked to report a wide (>=1200px) viewport,
 * matching `useSidebarState.test.ts`'s own mock — without it jsdom has no
 * `matchMedia` implementation, `useSidebarState` falls back to treating
 * that as "not narrow" today, but pinning it explicitly keeps this test
 * robust to that fallback ever changing, and (more importantly) keeps the
 * sidebar in its *expanded* visual mode so every nav item renders as its
 * own accessible link (the collapsed icon rail only exposes one link per
 * group, via its first item).
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { AppLayout } from '../AppLayout'
import { IngestionStatsPage } from '../IngestionStatsPage'
import { SourcesPage } from '../SourcesPage'
import { SpendingPage } from '../SpendingPage'
import { MetricsPage } from '../MetricsPage'

function DummyInvestigationList() {
  return <div data-testid="dummy-investigation-list">Investigations List</div>
}

function DummyInvestigationDetail() {
  return <div data-testid="dummy-investigation-detail">Investigation Detail</div>
}

// Task 5.1: KnowledgeBasePage/KnowledgeEntryPage are no longer static
// placeholders — like InvestigationListPage/InvestigationDetailPage before
// them, they now fetch real data on mount. Swapped for lightweight stand-ins
// here for the exact same reason the investigation routes already are (see
// the doc comment below): this suite only cares about route *matching*
// (breadcrumb/active-nav-item/shell wrapping), not page content, which is
// already covered by `KnowledgeBasePage.test.tsx`/`KnowledgeEntryPage.test.tsx`.
function DummyKnowledgeBase() {
  return <div data-testid="dummy-knowledge-base">Knowledge Base</div>
}

function DummyKnowledgeEntry() {
  return <div data-testid="dummy-knowledge-entry">Knowledge Entry</div>
}

/**
 * Mirrors `App.tsx`'s route tree exactly (same paths, same nesting under
 * `AppLayout`), swapping the investigation and knowledge-base routes for
 * lightweight stand-ins so this suite doesn't have to also stub
 * `fetch`/`EventSource` for `InvestigationListPage`/`InvestigationDetailPage`/
 * `KnowledgeBasePage`/`KnowledgeEntryPage` — their own behavior is already
 * covered by their dedicated test files. Only route *matching* (path shape,
 * params) matters here, and that's identical regardless of which element a
 * route renders.
 */
function renderAt(path: string) {
  const router = createMemoryRouter(
    [
      {
        element: <AppLayout />,
        children: [
          { path: 'investigations', element: <DummyInvestigationList /> },
          { path: 'investigations/:investigationId', element: <DummyInvestigationDetail /> },
          { path: 'knowledge', element: <DummyKnowledgeBase /> },
          { path: 'knowledge/:entryId', element: <DummyKnowledgeEntry /> },
          { path: 'ingestion-stats', element: <IngestionStatsPage /> },
          { path: 'sources', element: <SourcesPage /> },
          { path: 'spending', element: <SpendingPage /> },
          { path: 'metrics', element: <MetricsPage /> },
          {
            path: '*',
            element: (
              <div data-testid="not-found-page">
                <h1 className="text-2xl font-semibold text-text-primary">Page not found</h1>
              </div>
            ),
          },
        ],
      },
    ],
    { initialEntries: [path] },
  )
  return render(<RouterProvider router={router} />)
}

/** Minimal MediaQueryList mock — always reports a wide (>=1200px) viewport. */
function installWideViewportMatchMedia() {
  const mql = {
    matches: true,
    media: '(min-width: 1200px)',
    addEventListener: () => {},
    removeEventListener: () => {},
  }
  window.matchMedia = (() => mql) as unknown as typeof window.matchMedia
}

beforeEach(() => {
  installWideViewportMatchMedia()
})

afterEach(() => {
  // @ts-expect-error — deliberately restoring jsdom's absence of matchMedia between tests.
  delete window.matchMedia
})

describe('AppLayout — route-derived active nav item', () => {
  const cases: Array<[path: string, navLabel: string]> = [
    ['/investigations', 'Investigations'],
    ['/sources', 'Sources'],
    ['/ingestion-stats', 'Ingestion Stats'],
    ['/knowledge', 'Knowledge Base'],
    ['/knowledge/KB-104', 'Knowledge Base'],
    ['/metrics', 'Metrics'],
    ['/spending', 'Spending'],
  ]

  it.each(cases)('highlights "%s" -> %s in the sidebar', (path, navLabel) => {
    renderAt(path)

    // Scope to the sidebar nav — a detail route's breadcrumb also renders a
    // link with the same accessible name (e.g. "Knowledge Base"), which
    // must NOT be confused with the sidebar's own active-item link.
    const sidebar = screen.getByRole('navigation', { name: 'Main navigation' })
    const activeLink = within(sidebar).getByRole('link', { name: navLabel })
    expect(activeLink).toHaveAttribute('aria-current', 'page')
    expect(activeLink).toHaveAttribute('data-sidebar-nav-active', 'true')

    // Exactly one sidebar nav item is active at a time.
    const allSidebarLinks = within(sidebar).getAllByRole('link')
    const activeLinks = allSidebarLinks.filter((link) => link.getAttribute('aria-current') === 'page')
    expect(activeLinks).toHaveLength(1)
  })

  it('highlights "Investigations" (via the Observe group\'s icon-rail link) on the investigation-detail route', () => {
    // Unlike every other case above, the investigation-detail route forces
    // the sidebar into its collapsed icon rail regardless of viewport
    // (FR44, pre-existing `useSidebarState` behavior, unchanged by Task
    // 5.0b — see e2e/sidebar-behavior.spec.ts's "auto-collapses... even at
    // a wide viewport" case). Collapsed mode surfaces activation on the
    // GROUP's single icon link (accessible name = the group label
    // "Observe", not the item label "Investigations"), whose href is its
    // first item's href — which happens to be "/investigations".
    renderAt('/investigations/INV-0042')

    const sidebar = screen.getByRole('navigation', { name: 'Main navigation' })
    const activeLink = within(sidebar).getByRole('link', { name: 'Observe' })
    expect(activeLink).toHaveAttribute('aria-current', 'page')
    expect(activeLink).toHaveAttribute('data-sidebar-nav-active', 'true')
    expect(activeLink).toHaveAttribute('href', '/investigations')

    const allSidebarLinks = within(sidebar).getAllByRole('link')
    const activeLinks = allSidebarLinks.filter((link) => link.getAttribute('aria-current') === 'page')
    expect(activeLinks).toHaveLength(1)
  })

  it('highlights "Investigations" in the sidebar (expanded mode) when navigating to the list route', () => {
    renderAt('/investigations')

    const sidebar = screen.getByRole('navigation', { name: 'Main navigation' })
    const activeLink = within(sidebar).getByRole('link', { name: 'Investigations' })
    expect(activeLink).toHaveAttribute('aria-current', 'page')
    expect(activeLink).toHaveAttribute('data-sidebar-nav-active', 'true')
  })

  it('highlights nothing on the catch-all route', () => {
    renderAt('/some-unregistered-path')

    expect(screen.getByTestId('not-found-page')).toBeVisible()
    const sidebar = screen.getByRole('navigation', { name: 'Main navigation' })
    const allSidebarLinks = within(sidebar).getAllByRole('link')
    expect(allSidebarLinks.every((link) => link.getAttribute('aria-current') !== 'page')).toBe(true)
    expect(document.querySelector('[data-sidebar-nav-active="true"]')).toBeNull()
  })
})

describe('AppLayout — breadcrumb', () => {
  it('renders the investigation-detail breadcrumb unchanged: "Investigations > <id>" with a link back to the list', () => {
    renderAt('/investigations/INV-0042')

    const breadcrumb = screen.getByRole('navigation', { name: 'Breadcrumb' })
    const parentLink = within(breadcrumb).getByRole('link', { name: 'Investigations' })
    expect(parentLink).toHaveAttribute('href', '/investigations')
    expect(within(breadcrumb).getByText('INV-0042')).toBeVisible()
    expect(within(breadcrumb).getByText('INV-0042')).toHaveClass('text-primary')
  })

  it('renders "Knowledge Base > <id>" with a link back to the knowledge list on the entry-detail route', () => {
    renderAt('/knowledge/KB-104')

    const breadcrumb = screen.getByRole('navigation', { name: 'Breadcrumb' })
    const parentLink = within(breadcrumb).getByRole('link', { name: 'Knowledge Base' })
    expect(parentLink).toHaveAttribute('href', '/knowledge')
    expect(within(breadcrumb).getByText('KB-104')).toBeVisible()
    expect(within(breadcrumb).getByText('KB-104')).toHaveClass('text-primary')
  })

  const flatCases: Array<[path: string, label: string]> = [
    ['/investigations', 'Investigations'],
    ['/knowledge', 'Knowledge Base'],
    ['/sources', 'Sources'],
    ['/ingestion-stats', 'Ingestion Stats'],
    ['/metrics', 'Metrics'],
    ['/spending', 'Spending'],
  ]

  it.each(flatCases)('renders just "%s" as the breadcrumb on the flat route %s', (path, label) => {
    renderAt(path)

    const breadcrumb = screen.getByRole('navigation', { name: 'Breadcrumb' })
    expect(breadcrumb).toHaveTextContent(label)
    // A flat route's breadcrumb has no link — it's just the current page's label.
    expect(within(breadcrumb).queryByRole('link')).not.toBeInTheDocument()
  })

  it('renders no breadcrumb on the catch-all route', () => {
    renderAt('/some-unregistered-path')

    expect(screen.queryByRole('navigation', { name: 'Breadcrumb' })).not.toBeInTheDocument()
  })
})

describe('AppLayout — placeholder routes render inside the shell', () => {
  // Task 5.1: knowledge/knowledge-base-page dropped from this table — those
  // routes render real (non-placeholder) content now, via the dummy
  // stand-ins in `renderAt` above; their "renders inside the shell" coverage
  // moved to the two cases immediately below instead.
  const placeholderCases: Array<[path: string, testId: string]> = [
    ['/ingestion-stats', 'ingestion-stats-page'],
    ['/sources', 'sources-page'],
    ['/spending', 'spending-page'],
    ['/metrics', 'metrics-page'],
  ]

  it.each(placeholderCases)('renders the %s placeholder for %s, with the sidebar present', (path, testId) => {
    renderAt(path)

    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
    expect(screen.getByTestId(testId)).toBeVisible()
    expect(screen.queryByTestId('not-found-page')).not.toBeInTheDocument()
  })

  it('renders the Knowledge Base route inside the shell (sidebar present)', () => {
    renderAt('/knowledge')

    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
    expect(screen.getByTestId('dummy-knowledge-base')).toBeVisible()
    expect(screen.queryByTestId('not-found-page')).not.toBeInTheDocument()
  })

  it('renders the Knowledge Base entry-detail route inside the shell (sidebar present)', () => {
    renderAt('/knowledge/KB-104')

    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
    expect(screen.getByTestId('dummy-knowledge-entry')).toBeVisible()
    expect(screen.queryByTestId('not-found-page')).not.toBeInTheDocument()
  })
})
