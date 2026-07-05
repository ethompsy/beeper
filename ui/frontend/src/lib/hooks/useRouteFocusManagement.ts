import { useEffect, useRef } from 'react'

/**
 * useRouteFocusManagement — WCAG 2.4.3 focus management on route change
 * (docs/specs/ux-design-specification.md "Focus management on route-driven
 * collapse" / "Accessibility Implementation Guidelines").
 *
 *   - Entering a detail route (`isDetailRoute: true`) — INCLUDING a cold
 *     permalink load — moves focus to the detail summary `<h1>`
 *     (`detailHeadingSelector`, default `#detail-summary-heading`).
 *   - Navigating back to the list (`isDetailRoute: false` after having been
 *     `true`) moves focus to the currently-active sidebar nav item
 *     (`activeNavSelector`, default `[data-sidebar-nav-active="true"]`).
 *
 * "Cold load" support: this hook runs the same effect on first mount as on
 * subsequent route transitions — there is no special-casing of "was this a
 * client-side navigation or a hard reload." Whichever route the app hydrates
 * on is treated identically, so a permalink cold-load into the detail route
 * focuses the `<h1>` exactly like an in-app link click would.
 *
 * `routeKey` should change on every navigation (e.g. the matched pathname)
 * so the effect re-runs even when `isDetailRoute` stays the same value
 * across two different detail ids (e.g. detail → detail via a related-link).
 */
export function useRouteFocusManagement(isDetailRoute: boolean, routeKey: string): void {
  const wasDetailRoute = useRef<boolean | null>(null)

  useEffect(() => {
    const cameFromDetail = wasDetailRoute.current === true
    wasDetailRoute.current = isDetailRoute

    if (isDetailRoute) {
      const heading = document.getElementById('detail-summary-heading')
      if (heading) {
        if (!heading.hasAttribute('tabindex')) {
          heading.setAttribute('tabindex', '-1')
        }
        heading.focus()
      }
      return
    }

    // Only steer focus to the sidebar when we actually just left a detail
    // route — plain navigation between two non-detail routes (or first
    // mount on a non-detail route) should not steal focus.
    if (cameFromDetail) {
      const activeNavItem = document.querySelector<HTMLElement>(
        '[data-sidebar-nav-active="true"]',
      )
      activeNavItem?.focus()
    }
  }, [isDetailRoute, routeKey])
}
