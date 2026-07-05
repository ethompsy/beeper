import type { ReactNode } from 'react'
import { cn } from '../../utils/cn'
import { Sidebar, type SidebarGroupData, type SidebarProps } from '../Sidebar'
import { MenuIcon } from '../Sidebar/icons'

/**
 * AppShell — top bar + sidebar + content slot
 * (docs/specs/ux-design-specification.md "Layout Shell" component; FR40-44).
 *
 * Layout Shell states table (spec) drives the content-area margin:
 *   - Expanded, pushing (≥1200px, sidebar expanded): content margin-left
 *     tracks the sidebar's 256px width.
 *   - Collapsed icon rail (any route/viewport where sidebar isn't
 *     expanded): content margin-left tracks the 64px rail.
 *   - Overlay (manual expand <1200px): content margin-left stays at the
 *     64px rail width — the expanded sidebar floats on top instead of
 *     pushing (FR41's "no width shift").
 *
 * This component is purely presentational — the `expanded`/`isOverlay`
 * booleans it receives come from `useSidebarState` (the route-driven state
 * machine), and `onToggleSidebar` is wired to that hook's `toggle()`.
 */
export interface AppShellProps {
  groups: SidebarGroupData[]
  activeItemId?: string
  expanded: boolean
  isOverlay?: boolean
  onToggleSidebar: () => void
  linkComponent?: SidebarProps['linkComponent']
  /** Breadcrumb slot content — "Section > Item Name" per the spec's top-bar anatomy. */
  breadcrumb?: ReactNode
  children?: ReactNode
}

export function AppShell({
  groups,
  activeItemId,
  expanded,
  isOverlay = false,
  onToggleSidebar,
  linkComponent,
  breadcrumb,
  children,
}: AppShellProps) {
  return (
    <div className="flex min-h-screen flex-col bg-surface-base">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-30 focus:rounded-md focus:bg-surface-overlay focus:px-3 focus:py-2 focus:text-text-primary"
      >
        Skip to main content
      </a>

      <header
        data-slot="top-bar"
        className="flex h-12 shrink-0 items-center gap-3 border-b border-surface-raised bg-surface-base px-4"
      >
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls="sidebar"
          onClick={onToggleSidebar}
          className={cn(
            'flex h-9 w-9 items-center justify-center rounded-md text-text-secondary',
            'transition-colors motion-reduce:transition-none hover:bg-surface-raised hover:text-text-primary',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
          )}
        >
          <MenuIcon className="h-5 w-5" />
          <span className="sr-only">Toggle navigation sidebar</span>
        </button>
        <span className="text-base font-semibold text-text-primary">Beeper</span>
        {breadcrumb != null ? (
          <nav aria-label="Breadcrumb" className="text-sm text-text-secondary">
            {breadcrumb}
          </nav>
        ) : null}
      </header>

      <div className="relative flex flex-1">
        <Sidebar
          groups={groups}
          activeItemId={activeItemId}
          expanded={expanded}
          isOverlay={isOverlay}
          linkComponent={linkComponent}
          className="fixed inset-y-12 left-0 z-20 shrink-0"
        />

        {/*
         * Content-area margin mirrors the spec's "Layout Shell" states
         * table literally: it only grows to the expanded width (256px) when
         * the sidebar is *pushing* (expanded && !isOverlay). Every other
         * combination — collapsed rail, or expanded-but-overlaying — keeps
         * the 64px rail margin, so an overlay expand never shifts content
         * width (FR41).
         */}
        <main
          id="main-content"
          data-slot="content-area"
          data-sidebar-expanded={expanded}
          data-sidebar-overlay={isOverlay}
          className={cn(
            'min-w-0 flex-1 p-6',
            'transition-sidebar motion-reduce:transition-none',
            expanded && !isOverlay ? 'ml-64' : 'ml-16',
          )}
        >
          {children}
        </main>
      </div>
    </div>
  )
}
