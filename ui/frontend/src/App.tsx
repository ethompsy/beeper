import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom'
import { AppLayout } from './routes/AppLayout'
import { InvestigationListPage } from './routes/InvestigationListPage'
import { InvestigationDetailPage } from './routes/InvestigationDetailPage'

/**
 * App — router root (Task 2.1).
 *
 * `basename: '/app'` matches the Flask BFF's React-shell mount
 * (`ui/beeper_ui/routes/react_shell.py`, `url_prefix="/app"` — "serve
 * index.html so React Router can handle client-side navigation" for any
 * path within `/app/*`). `InvestigationCard`'s existing Storybook fixtures
 * already assume `/app/investigations/<id>` hrefs (Task 1.4), so this
 * mirrors that convention.
 *
 * Route placeholders only (list/detail) — Tasks 2.2/2.5 build the real
 * views. The catch-all "not found" route still renders inside `AppLayout`
 * (sidebar visible), matching Task 2.5's contract that an invalid
 * investigation id degrades to an in-shell message, not a bare 404 page.
 */
const router = createBrowserRouter(
  [
    {
      element: <AppLayout />,
      children: [
        { index: true, element: <Navigate to="/investigations" replace /> },
        { path: 'investigations', element: <InvestigationListPage /> },
        { path: 'investigations/:investigationId', element: <InvestigationDetailPage /> },
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
