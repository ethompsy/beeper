import type { ComponentType, ReactNode, SVGProps } from 'react'
import * as Tooltip from '@radix-ui/react-tooltip'
import { cn } from '../../utils/cn'
import { ObserveIcon, LearnIcon, ManageIcon } from './icons'

/**
 * Sidebar — the Observe/Learn/Manage navigation rail
 * (docs/specs/ux-design-specification.md "Sidebar Group" component; FR40-44).
 *
 * Two visual modes, driven entirely by the `expanded` prop (state machine
 * lives in `useSidebarState`, Task 2.1 — this component is presentational):
 *   - Expanded (256px, `--width-sidebar-expanded`): full group headers +
 *     item labels.
 *   - Collapsed (64px icon rail, `--width-sidebar-collapsed`): one icon per
 *     group, Radix `Tooltip` shows the group label on hover/focus (FR41 —
 *     "never a bare hamburger").
 *
 * Render-agnostic navigation: consumers pass a `LinkComponent` (e.g. React
 * Router's `Link`) so this library primitive has no router dependency —
 * matching the shadcn-style "headless, bring your own routing" posture used
 * elsewhere in `src/lib`.
 */

export interface SidebarNavItem {
  /** Stable id — also used for the `data-sidebar-nav-active` query target. */
  id: string
  label: string
  href: string
}

export interface SidebarGroupData {
  id: 'observe' | 'learn' | 'manage'
  label: string
  items: SidebarNavItem[]
}

/** Observe is always first, Investigations is always the first item (spec, Executive Summary). */
const GROUP_ICONS: Record<SidebarGroupData['id'], ComponentType<SVGProps<SVGSVGElement>>> = {
  observe: ObserveIcon,
  learn: LearnIcon,
  manage: ManageIcon,
}

export interface SidebarLinkProps {
  href: string
  className?: string
  children?: ReactNode
  'data-sidebar-nav-active'?: 'true'
  'aria-current'?: 'page'
}

export interface SidebarProps {
  /** Nav groups, in display order (Observe, Learn, Manage per the spec default). */
  groups: SidebarGroupData[]
  /** The currently active item id (drives `aria-current` + the focus-return target). */
  activeItemId?: string
  /** Resolved expanded/collapsed visual state — from `useSidebarState`. */
  expanded: boolean
  /**
   * True when the expanded sidebar should render as a fixed overlay rather
   * than participating in layout flow (FR41: manual expand below 1200px).
   */
  isOverlay?: boolean
  /**
   * Render-prop-free link component injection — pass `Link` from
   * `react-router-dom` (or a plain `<a>` wrapper) so this primitive stays
   * router-agnostic.
   */
  linkComponent?: ComponentType<SidebarLinkProps>
  className?: string
}

function DefaultLink({ href, children, ...rest }: SidebarLinkProps) {
  return (
    <a href={href} {...rest}>
      {children}
    </a>
  )
}

export function Sidebar({
  groups,
  activeItemId,
  expanded,
  isOverlay = false,
  linkComponent: LinkComponent = DefaultLink,
  className,
}: SidebarProps) {
  return (
    <Tooltip.Provider delayDuration={300}>
      <nav
        id="sidebar"
        aria-label="Main navigation"
        data-slot="sidebar"
        data-expanded={expanded}
        data-overlay={isOverlay}
        className={cn(
          'flex h-full flex-col overflow-y-auto bg-surface-base',
          'transition-sidebar motion-reduce:transition-none',
          expanded ? 'w-64' : 'w-16',
          isOverlay && 'fixed inset-y-0 left-0 z-20 shadow-lg',
          className,
        )}
      >
        {groups.map((group) => (
          <SidebarGroup
            key={group.id}
            group={group}
            expanded={expanded}
            activeItemId={activeItemId}
            LinkComponent={LinkComponent}
          />
        ))}
      </nav>
    </Tooltip.Provider>
  )
}

interface SidebarGroupProps {
  group: SidebarGroupData
  expanded: boolean
  activeItemId?: string
  LinkComponent: ComponentType<SidebarLinkProps>
}

function SidebarGroup({ group, expanded, activeItemId, LinkComponent }: SidebarGroupProps) {
  const Icon = GROUP_ICONS[group.id]
  const isGroupActive = group.items.some((item) => item.id === activeItemId)

  if (!expanded) {
    // Collapsed icon rail: one icon per group, tooltip shows the label,
    // clicking navigates to the group's first item (spec: "Sidebar Group"
    // collapsed-mode interaction).
    const firstItem = group.items[0]
    return (
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <LinkComponent
            href={firstItem?.href ?? '#'}
            aria-current={isGroupActive ? 'page' : undefined}
            data-sidebar-nav-active={isGroupActive ? 'true' : undefined}
            className={cn(
              'flex h-10 w-16 items-center justify-center text-text-secondary',
              'transition-colors motion-reduce:transition-none hover:bg-surface-raised hover:text-text-primary',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
              isGroupActive && 'bg-surface-raised text-primary',
            )}
          >
            <Icon className="h-5 w-5" />
            <span className="sr-only">{group.label}</span>
          </LinkComponent>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            side="right"
            sideOffset={4}
            className="rounded-md bg-surface-overlay px-2 py-1 text-xs text-text-primary"
          >
            {group.label}
            <Tooltip.Arrow className="fill-surface-overlay" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    )
  }

  return (
    <section aria-label={group.label} className="flex flex-col">
      <div className="flex items-center gap-2 px-4 py-2 text-xl text-text-secondary">
        <Icon className="h-5 w-5" />
        <span>{group.label}</span>
      </div>
      <ul className="flex flex-col">
        {group.items.map((item) => {
          const isActive = item.id === activeItemId
          return (
            <li key={item.id}>
              <LinkComponent
                href={item.href}
                aria-current={isActive ? 'page' : undefined}
                data-sidebar-nav-active={isActive ? 'true' : undefined}
                className={cn(
                  'block border-l-2 border-transparent px-4 py-2 text-sm text-text-secondary',
                  'transition-colors motion-reduce:transition-none hover:bg-surface-raised hover:text-text-primary',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
                  isActive && 'border-l-primary bg-surface-raised text-text-primary',
                )}
              >
                {item.label}
              </LinkComponent>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
