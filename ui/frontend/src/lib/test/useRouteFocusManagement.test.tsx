/**
 * useRouteFocusManagement.test.tsx
 *
 * AC [T] (Task 2.1, WCAG 2.4.3) — in-app-navigation half: entering a detail
 * route moves focus to the summary `<h1>`; navigating back to the list
 * moves focus to the active sidebar nav item. The cold-permalink-load half
 * is proven separately by `e2e/focus-management.spec.ts` (Playwright, real
 * router hydration), per the task's note that a memory-router RTL test
 * only covers in-app nav.
 *
 * The hook is called once from a persistent layout (mirroring
 * `src/routes/AppLayout.tsx`, which wraps every route via <Outlet/> and
 * calls the hook exactly once) — NOT per-page — since the hook's
 * "did we just come from a detail route" tracking relies on a stable call
 * site that survives across route changes.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route, Link, Outlet, useMatch } from 'react-router-dom'
import { useRouteFocusManagement } from '../hooks/useRouteFocusManagement'

function Layout() {
  const detailMatch = useMatch('/investigations/:id')
  useRouteFocusManagement(detailMatch !== null, detailMatch?.pathname ?? 'list')
  return (
    <div>
      <a href="#" data-sidebar-nav-active="true">
        Investigations (active nav item)
      </a>
      <Outlet />
    </div>
  )
}

function ListPage() {
  return <Link to="/investigations/inv-1">Open INV-1</Link>
}

function DetailPage() {
  return (
    <div>
      <h1 id="detail-summary-heading">inv-1</h1>
      <Link to="/investigations">Back to list</Link>
    </div>
  )
}

function TestApp() {
  return (
    <MemoryRouter initialEntries={['/investigations']}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/investigations" element={<ListPage />} />
          <Route path="/investigations/:id" element={<DetailPage />} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

describe('useRouteFocusManagement (in-app navigation)', () => {
  it('moves focus to the summary <h1> when navigating into a detail route', async () => {
    const user = userEvent.setup()
    render(<TestApp />)

    await user.click(screen.getByRole('link', { name: 'Open INV-1' }))

    const heading = await screen.findByRole('heading', { name: 'inv-1' })
    expect(heading).toHaveFocus()
  })

  it('moves focus back to the active sidebar nav item when navigating back to the list', async () => {
    const user = userEvent.setup()
    render(<TestApp />)

    await user.click(screen.getByRole('link', { name: 'Open INV-1' }))
    await screen.findByRole('heading', { name: 'inv-1' })

    await user.click(screen.getByRole('link', { name: 'Back to list' }))

    const activeNavItem = await screen.findByRole('link', { name: 'Investigations (active nav item)' })
    expect(activeNavItem).toHaveFocus()
  })

  it('does not steal focus when navigating between two non-detail routes (never having visited detail)', async () => {
    function OtherPage() {
      return <button type="button">other page button</button>
    }
    function App() {
      return (
        <MemoryRouter initialEntries={['/investigations']}>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/investigations" element={<Link to="/other">Go to other</Link>} />
              <Route path="/other" element={<OtherPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      )
    }
    const user = userEvent.setup()
    render(<App />)

    const goToOtherLink = screen.getByRole('link', { name: 'Go to other' })
    goToOtherLink.focus()
    await user.click(goToOtherLink)

    await screen.findByRole('button', { name: 'other page button' })
    // The hook only steers focus on a return-from-detail transition — a
    // plain non-detail-to-non-detail navigation must not force focus onto
    // the sidebar nav item.
    const navLink = screen.getByRole('link', { name: 'Investigations (active nav item)' })
    expect(navLink).not.toHaveFocus()
  })

  it('does not force focus onto the nav item on first mount of a non-detail route', () => {
    function App() {
      return (
        <MemoryRouter initialEntries={['/investigations']}>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/investigations" element={<ListPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      )
    }
    render(<App />)
    const navLink = screen.getByRole('link', { name: 'Investigations (active nav item)' })
    expect(navLink).not.toHaveFocus()
  })
})
