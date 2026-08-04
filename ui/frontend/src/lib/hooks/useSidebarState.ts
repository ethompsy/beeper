import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

/**
 * useSidebarState — the FR41/42/44 sidebar state machine.
 *
 * docs/specs/ux-design-specification.md "Layout Shell" states table models
 * sidebar state as a three-value enum (`auto` | `collapsed` | `expanded`)
 * rather than a boolean:
 *   - `auto`      — viewport-driven: expanded ≥1200px (`--breakpoint-lg`),
 *                   icon rail below it. This is the default on every route
 *                   except investigation detail.
 *   - `collapsed` — route-driven hard override (FR44): investigation detail
 *                   force-collapses the sidebar to the icon rail regardless
 *                   of viewport. A *previous* route's manual expand does not
 *                   leak in (each route decides its own base mode) — but per
 *                   FR44's final clause ("the user can always manually
 *                   override via the hamburger"), the user CAN still
 *                   manually re-expand on this same route via toggle().
 *   - `expanded`  — reserved for a future route that needs to force the
 *                   sidebar open (spec: "can be set by future routes").
 *
 * On top of the route-driven base mode, the user may manually toggle the
 * sidebar (hamburger button or the `[` key). Manual toggles are scoped to
 * "until next route change" (spec, Navigation Patterns): the override lives
 * in plain component state (not persisted), so it is naturally gone on a
 * cold/hard-reload (Task 3.3's negative test — a manually-expanded sidebar
 * must NOT survive a reload) and is explicitly cleared on every client-side
 * route change so navigating away and back re-applies the route's base mode
 * rather than remembering the prior override.
 *
 * Push vs. overlay (FR41): manually expanding while narrower than
 * `--breakpoint-lg` (1200px) overlays the content (the content area's
 * effective width/margin does NOT change) — only expanding at ≥1200px
 * (which is also the `auto` default there) pushes content. This hook
 * exposes `isOverlay` so the shell can render the sidebar `fixed` instead
 * of adjusting layout flow.
 */

const LG_BREAKPOINT_PX = 1200

export type SidebarRouteMode = 'auto' | 'collapsed' | 'expanded'

export interface SidebarState {
  /** Resolved boolean: is the sidebar currently showing the expanded (256px) panel? */
  expanded: boolean
  /** Is the viewport narrower than the `lg` (1200px) breakpoint? */
  isNarrowViewport: boolean
  /**
   * True when the expanded sidebar should overlay content rather than push
   * it (FR41: manual expand below 1200px). False when expanded+pushing, or
   * when collapsed (icon rail never overlays).
   */
  isOverlay: boolean
  /** Toggle the manual override (hamburger click / `[` key). */
  toggle: () => void
}

function getIsNarrowViewport(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return !window.matchMedia(`(min-width: ${LG_BREAKPOINT_PX}px)`).matches
}

/**
 * @param routeMode The current route's base sidebar mode — pass `'collapsed'`
 *   on the investigation detail route (FR44), `'auto'` everywhere else.
 * @param routeKey A value that changes on every route navigation (e.g. the
 *   matched path or location.key) — clears the manual override so it never
 *   survives a route change, per spec ("Overrides auto state until next
 *   route change").
 */
export function useSidebarState(routeMode: SidebarRouteMode, routeKey: string): SidebarState {
  const [isNarrowViewport, setIsNarrowViewport] = useState(getIsNarrowViewport)
  const [manualOverride, setManualOverride] = useState<boolean | null>(null)
  const previousRouteKey = useRef(routeKey)

  // Track viewport width live (resize) so `auto` mode responds to live resizes.
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const mql = window.matchMedia(`(min-width: ${LG_BREAKPOINT_PX}px)`)
    const handleChange = (): void => setIsNarrowViewport(!mql.matches)
    handleChange()
    mql.addEventListener('change', handleChange)
    return () => mql.removeEventListener('change', handleChange)
  }, [])

  // Clear the manual override on every route change (spec: scoped to the
  // route it was set on) — each newly-entered route starts from its own
  // base mode, not whatever the user last chose on a previous route.
  useEffect(() => {
    if (previousRouteKey.current !== routeKey) {
      previousRouteKey.current = routeKey
      setManualOverride(null)
    }
  }, [routeKey])

  // Global `[` keyboard shortcut toggles the sidebar (spec: Navigation Patterns).
  const toggle = useCallback(() => {
    setManualOverride((prev) => {
      const base = prev !== null ? prev : routeMode !== 'collapsed' && !isNarrowViewport
      return !base
    })
  }, [routeMode, isNarrowViewport])

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key !== '[') return
      const target = event.target as HTMLElement | null
      const tag = target?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || target?.isContentEditable) return
      toggle()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [toggle])

  return useMemo(() => {
    // Route-driven base mode decides the default, but a manual override set
    // on THIS route always wins (FR44: "the user can always manually
    // override via the hamburger" — even on the detail route).
    if (manualOverride !== null) {
      const expanded = manualOverride
      const isOverlay = expanded && isNarrowViewport
      return { expanded, isNarrowViewport, isOverlay, toggle }
    }

    if (routeMode === 'collapsed') {
      return { expanded: false, isNarrowViewport, isOverlay: false, toggle }
    }

    if (routeMode === 'expanded') {
      return {
        expanded: true,
        isNarrowViewport,
        isOverlay: isNarrowViewport,
        toggle,
      }
    }

    // routeMode === 'auto': viewport-driven default.
    const expanded = !isNarrowViewport
    const isOverlay = expanded && isNarrowViewport

    return { expanded, isNarrowViewport, isOverlay, toggle }
  }, [routeMode, isNarrowViewport, manualOverride, toggle])
}
