import { Link, Outlet, useMatch } from 'react-router-dom'
import {
  AppShell,
  useSidebarState,
  useRouteFocusManagement,
  type SidebarGroupData,
  type SidebarLinkProps,
} from '../lib'

/**
 * AppLayout — the app-level composition root wiring the `AppShell`/`Sidebar`
 * library primitives to React Router (Task 2.1).
 *
 * Nav groups mirror docs/specs/ux-design-specification.md's "Sidebar Group"
 * table exactly: Observe (Investigations, Sources, Ingestion Stats), Learn
 * (Knowledge Base, Metrics), Manage (Spending). Only "Investigations" has a
 * real route in this increment — the rest are placeholders for future
 * milestones and intentionally point at not-yet-built routes.
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
      { id: 'knowledge-base', label: 'Knowledge Base', href: '/knowledge-base' },
      { id: 'metrics', label: 'Metrics', href: '/metrics' },
    ],
  },
  {
    id: 'manage',
    label: 'Manage',
    items: [{ id: 'spending', label: 'Spending', href: '/spending' }],
  },
]

function RouterLink({ href, children, ...rest }: SidebarLinkProps) {
  return (
    <Link to={href} {...rest}>
      {children}
    </Link>
  )
}

export function AppLayout() {
  const detailMatch = useMatch('/investigations/:investigationId')
  const isDetailRoute = detailMatch !== null

  const sidebarState = useSidebarState(isDetailRoute ? 'collapsed' : 'auto', detailMatch?.pathname ?? 'list')
  useRouteFocusManagement(isDetailRoute, detailMatch?.pathname ?? 'list')

  const breadcrumb = isDetailRoute ? (
    <>
      <Link to="/investigations" className="text-text-secondary hover:text-text-primary">
        Investigations
      </Link>
      <span aria-hidden="true"> &gt; </span>
      <span className="text-primary">{detailMatch?.params.investigationId}</span>
    </>
  ) : (
    <span>Investigations</span>
  )

  return (
    <AppShell
      groups={NAV_GROUPS}
      activeItemId="investigations"
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
