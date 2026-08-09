import type { ReactNode } from 'react'
import { Link, Outlet, useLocation, useMatch } from 'react-router-dom'
import {
  AppShell,
  useSidebarState,
  useRouteFocusManagement,
  useCurrentUser,
  type SidebarGroupData,
  type SidebarNavItem,
  type SidebarLinkProps,
} from '../lib'

/**
 * AppLayout — the app-level composition root wiring the `AppShell`/`Sidebar`
 * library primitives to React Router (Task 2.1, generalized in Task 5.0b to
 * cover every Milestone 2.1 destination instead of hardcoding
 * "Investigations").
 *
 * Nav groups mirror docs/specs/ux-design-specification.md's "Sidebar Group"
 * table exactly: Observe (Investigations, Sources, Ingestion Stats), Learn
 * (Knowledge Base, Metrics), Manage (Spending, + Users for admins — Task
 * 8.7). `href`s are React Router paths (relative to the router's `/app`
 * basename) — per docs/design/route-parity-targets.md they are client-side
 * route ids, not required to mirror the Jinja URL 1:1 (see that doc's §3/§6
 * notes on the `ingestion-stats` and `knowledge` hrefs specifically).
 */
const BASE_NAV_GROUPS: SidebarGroupData[] = [
  {
    id: 'observe',
    label: 'Observe',
    items: [
      { id: 'investigations', label: 'Investigations', href: '/investigations' },
      { id: 'sources', label: 'Sources', href: '/sources' },
      { id: 'ingestion-stats', label: 'Ingestion Stats', href: '/ingestion-stats' },
    ],
  },
  {
    id: 'learn',
    label: 'Learn',
    items: [
      { id: 'knowledge', label: 'Knowledge Base', href: '/knowledge' },
      { id: 'metrics', label: 'Metrics', href: '/metrics' },
    ],
  },
  {
    id: 'manage',
    label: 'Manage',
    items: [{ id: 'spending', label: 'Spending', href: '/spending' }],
  },
]

const USERS_NAV_ITEM: SidebarNavItem = { id: 'admin-users', label: 'Users', href: '/admin/users' }

/**
 * Task 8.7 (ADR 0002 §6, FR60): builds the nav groups per-render (rather
 * than the pre-8.7 module-level `NAV_GROUPS` constant) because the Manage
 * group's item list now depends on a hook result — `useCurrentUser()`.
 *
 * **This is a UI affordance only, NOT a security boundary** — hiding the
 * "Users" nav item from a non-admin caller only prevents an accidental
 * click; the actual enforcement is `@require_role("admin")` on every route
 * in `admin_users_api_bp` (`ui/beeper_ui/routes/admin_users.py`), and
 * `AdminUsersPage.tsx` renders its own in-shell 403 state if a non-admin
 * reaches `/app/admin/users` directly (typed URL, bookmark, etc.) — this
 * function hiding the nav item is a courtesy, not a gate.
 */
function buildNavGroups(isAdmin: boolean): SidebarGroupData[] {
  if (!isAdmin) return BASE_NAV_GROUPS
  return BASE_NAV_GROUPS.map((group) =>
    group.id === 'manage' ? { ...group, items: [...group.items, USERS_NAV_ITEM] } : group,
  )
}

/**
 * Resolve which nav item (if any) the current pathname belongs to.
 *
 * Longest-href-prefix match: a pathname matches an item either exactly
 * (`/knowledge` matches `knowledge`) or as a sub-path (`/knowledge/KB-104`
 * also matches `knowledge`, so a detail route highlights its parent list
 * item — same treatment `/investigations/:id` already relied on). Longest
 * match wins so a more specific href never loses to a shorter one that also
 * happens to prefix-match. Returns `undefined` for anything that matches no
 * nav item (the catch-all route) — nothing should be highlighted there.
 *
 * Takes the flattened nav items as a parameter (Task 8.7) rather than
 * closing over a module-level constant — the item set is now role-
 * dependent (`buildNavGroups`), computed per-render inside `AppLayout`.
 */
function matchActiveNavItem(pathname: string, flatNavItems: SidebarNavItem[]): SidebarNavItem | undefined {
  let best: SidebarNavItem | undefined
  for (const item of flatNavItems) {
    const isMatch = pathname === item.href || pathname.startsWith(`${item.href}/`)
    if (isMatch && (best === undefined || item.href.length > best.href.length)) {
      best = item
    }
  }
  return best
}

function RouterLink({ href, children, ...rest }: SidebarLinkProps) {
  return (
    <Link to={href} {...rest}>
      {children}
    </Link>
  )
}

export function AppLayout() {
  const { pathname } = useLocation()

  // Task 8.7 (ADR 0002 §6, FR60): role-gated "Users" nav item — see
  // `buildNavGroups`'s doc comment for why this is a UI affordance only.
  const { user } = useCurrentUser()
  const navGroups = buildNavGroups(user?.role === 'admin')
  const flatNavItems = navGroups.flatMap((group) => group.items)

  // The two detail routes that render "Parent > <id>" breadcrumbs (Task
  // 5.0b generalizes the investigation-only version to also cover
  // Knowledge Base entries, per the plan's breadcrumb contract). Every
  // other route is "flat" and just shows its own nav label.
  const investigationDetailMatch = useMatch('/investigations/:investigationId')
  const knowledgeDetailMatch = useMatch('/knowledge/:entryId')
  const isDetailRoute = investigationDetailMatch !== null

  // Task 5.5 a11y-audit finding: WCAG 2.4.3 focus management (moving focus
  // to the detail `<h1>` on entry, incl. cold permalink load, and back to
  // the active sidebar item on return-to-list) was only wired for the
  // investigation detail route. `KnowledgeEntryPage` is a detail route too
  // (`#detail-summary-heading` on its own `<h1>`, added alongside this fix)
  // and needs the same treatment. Deliberately a SEPARATE boolean from
  // `isDetailRoute` above — that one also drives `useSidebarState`'s
  // force-collapse behavior, which is a Task 2.1 AC scoped to investigation
  // detail specifically (FR41/42/44); extending it to Knowledge Base would
  // be an unrequested layout/behavior change, not an accessibility fix.
  const isFocusManagedDetailRoute = isDetailRoute || knowledgeDetailMatch !== null

  const sidebarState = useSidebarState(isDetailRoute ? 'collapsed' : 'auto', pathname)
  useRouteFocusManagement(isFocusManagedDetailRoute, pathname)

  const activeNavItem = matchActiveNavItem(pathname, flatNavItems)

  let breadcrumb: ReactNode
  if (investigationDetailMatch) {
    // Unchanged from pre-Task-5.0b behavior (Task 2.5/4.1 pinned this exact
    // copy) — do not alter this branch's strings or structure.
    breadcrumb = (
      <>
        <Link to="/investigations" className="text-text-secondary hover:text-text-primary">
          Investigations
        </Link>
        <span aria-hidden="true"> &gt; </span>
        <span className="text-primary">{investigationDetailMatch.params.investigationId}</span>
      </>
    )
  } else if (knowledgeDetailMatch) {
    breadcrumb = (
      <>
        <Link to="/knowledge" className="text-text-secondary hover:text-text-primary">
          Knowledge Base
        </Link>
        <span aria-hidden="true"> &gt; </span>
        <span className="text-primary">{knowledgeDetailMatch.params.entryId}</span>
      </>
    )
  } else if (activeNavItem) {
    breadcrumb = <span>{activeNavItem.label}</span>
  } else {
    // Catch-all / unrecognized route — no nav item to name, so no breadcrumb.
    breadcrumb = undefined
  }

  return (
    <AppShell
      groups={navGroups}
      activeItemId={activeNavItem?.id}
      expanded={sidebarState.expanded}
      isOverlay={sidebarState.isOverlay}
      onToggleSidebar={sidebarState.toggle}
      linkComponent={RouterLink}
      breadcrumb={breadcrumb}
    >
      <Outlet />
    </AppShell>
  )
}
