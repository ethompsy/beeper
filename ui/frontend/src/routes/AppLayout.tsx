import type { ReactNode } from 'react'
import { Link, Outlet, useLocation, useMatch } from 'react-router-dom'
import {
  AppShell,
  useSidebarState,
  useRouteFocusManagement,
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
 * (Knowledge Base, Metrics), Manage (Spending). `href`s are React Router
 * paths (relative to the router's `/app` basename) — per
 * docs/design/route-parity-targets.md they are client-side route ids, not
 * required to mirror the Jinja URL 1:1 (see that doc's §3/§6 notes on the
 * `ingestion-stats` and `knowledge` hrefs specifically).
 */
const NAV_GROUPS: SidebarGroupData[] = [
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

/** Flattened once at module scope — every nav item across all three groups, in display order. */
const FLAT_NAV_ITEMS: SidebarNavItem[] = NAV_GROUPS.flatMap((group) => group.items)

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
 */
function matchActiveNavItem(pathname: string): SidebarNavItem | undefined {
  let best: SidebarNavItem | undefined
  for (const item of FLAT_NAV_ITEMS) {
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

  // The two detail routes that render "Parent > <id>" breadcrumbs (Task
  // 5.0b generalizes the investigation-only version to also cover
  // Knowledge Base entries, per the plan's breadcrumb contract). Every
  // other route is "flat" and just shows its own nav label.
  const investigationDetailMatch = useMatch('/investigations/:investigationId')
  const knowledgeDetailMatch = useMatch('/knowledge/:entryId')
  const isDetailRoute = investigationDetailMatch !== null

  const sidebarState = useSidebarState(isDetailRoute ? 'collapsed' : 'auto', pathname)
  useRouteFocusManagement(isDetailRoute, pathname)

  const activeNavItem = matchActiveNavItem(pathname)

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
      groups={NAV_GROUPS}
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
