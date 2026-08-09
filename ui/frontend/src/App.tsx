import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom'
import { AppLayout } from './routes/AppLayout'
import { InvestigationListPage } from './routes/InvestigationListPage'
import { InvestigationDetailPage } from './routes/InvestigationDetailPage'
import { KnowledgeBasePage } from './routes/KnowledgeBasePage'
import { KnowledgeEntryPage } from './routes/KnowledgeEntryPage'
import { IngestionStatsPage } from './routes/IngestionStatsPage'
import { SourcesPage } from './routes/SourcesPage'
import { SpendingPage } from './routes/SpendingPage'
import { MetricsPage } from './routes/MetricsPage'
import { LoginPage } from './routes/LoginPage'
import { AdminUsersPage } from './routes/AdminUsersPage'

/**
 * App — router root (Task 2.1, extended by Task 5.0b).
 *
 * `basename: '/app'` matches the Flask BFF's React-shell mount
 * (`ui/beeper_ui/routes/react_shell.py`, `url_prefix="/app"` — "serve
 * index.html so React Router can handle client-side navigation" for any
 * path within `/app/*`). `InvestigationCard`'s existing Storybook fixtures
 * already assume `/app/investigations/<id>` hrefs (Task 1.4), so this
 * mirrors that convention.
 *
 * Task 5.0b registers every Milestone 2.1 destination up front — one route
 * per downstream task (5.1 Knowledge Base browse+detail, 5.2 Ingestion
 * Stats, 5.3 Sources + Spending, 5.4 Metrics) — as scaffolding so those four
 * tasks, which run concurrently in separate worktrees, only ever need to
 * rewrite their own page file(s) rather than all touching this router.
 * Route paths mirror the canonical React URLs pinned in
 * `docs/design/route-parity-targets.md` (§2–§5) exactly. Every route below
 * except investigations list/detail is still a placeholder — Tasks 5.1–5.4
 * replace their own page component's implementation in place, without
 * editing this file.
 *
 * The catch-all "not found" route still renders inside `AppLayout` (sidebar
 * visible), matching Task 2.5's contract that an invalid investigation id
 * degrades to an in-shell message, not a bare 404 page — and now applies to
 * any unrecognized path, not just investigation ids.
 *
 * Task 8.7 (ADR 0002 §6, FR60): `/app/admin/users` is registered as a
 * CHILD of the `AppLayout` route tree below (NOT a sibling like `login`
 * above) — per the comment `login`'s entry left here, this route IS a
 * Manage-nav destination and needs the authenticated sidebar shell. Role
 * gating (hiding the nav item for non-admins) lives in `AppLayout.tsx`;
 * the route itself is reachable by direct navigation regardless (the page
 * component renders its own in-shell 403 for a non-admin caller — see
 * `AdminUsersPage.tsx`'s doc comment).
 */
const router = createBrowserRouter(
  [
    // Task 8.6 (ADR 0002 §6): `/app/login` is a SIBLING of the `AppLayout`
    // tree, not a child of it — it renders a minimal centered card with
    // NO sidebar/shell chrome (an unauthenticated visitor has no nav to
    // show). This is also the first net-new route with no Jinja ancestor
    // (see docs/design/route-parity-targets.md §9). `/app/admin/users`
    // (Task 8.7, registered below) is the SECOND net-new route (§9b) but
    // does NOT follow this sibling pattern — it IS a Manage-nav
    // destination, so it's a CHILD of the `AppLayout` tree instead (see
    // that route's entry below).
    { path: 'login', element: <LoginPage /> },
    {
      element: <AppLayout />,
      children: [
        { index: true, element: <Navigate to="/investigations" replace /> },
        { path: 'investigations', element: <InvestigationListPage /> },
        { path: 'investigations/:investigationId', element: <InvestigationDetailPage /> },
        { path: 'knowledge', element: <KnowledgeBasePage /> },
        { path: 'knowledge/:entryId', element: <KnowledgeEntryPage /> },
        { path: 'ingestion-stats', element: <IngestionStatsPage /> },
        { path: 'sources', element: <SourcesPage /> },
        { path: 'spending', element: <SpendingPage /> },
        { path: 'metrics', element: <MetricsPage /> },
        // Task 8.7 (ADR 0002 §6, FR60) — a Manage-nav destination, hence a
        // child of `AppLayout` (the authenticated shell), unlike `login`
        // above. See `AdminUsersPage.tsx` for the in-shell 403 state a
        // non-admin caller gets on direct navigation here.
        { path: 'admin/users', element: <AdminUsersPage /> },
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
  { basename: '/app' },
)

function App() {
  return <RouterProvider router={router} />
}

export default App
