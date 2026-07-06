import { useEffect, useRef } from 'react'

/**
 * useAutoScrollOnAppend — the investigation-detail timeline's auto-scroll
 * rule (Task 2.6a; docs/specs/ux-design-specification.md "Real-Time Feedback
 * Patterns": "If user is within 100px of timeline bottom, auto-scroll to new
 * step. If user is scrolled up, do NOT auto-scroll — user is reading earlier
 * evidence").
 *
 * The page scrolls at the document/window level (see `useScrollRestoration`'s
 * doc comment — `AppShell` uses `min-h-screen` with no bounded/overflow
 * ancestor), so "distance from timeline bottom" is measured against the
 * window viewport via the tracked element's `getBoundingClientRect()`, not a
 * nested container's `scrollTop`.
 *
 * ── Why the threshold is checked BEFORE the DOM updates, not after ──
 *
 * By the time a new step has rendered, the timeline's bottom edge has
 * already moved (it grew); checking "was I within 100px of the bottom" only
 * makes sense against the layout as it existed the instant before the new
 * content arrived. So the caller supplies `itemCount` (the merged step
 * list's length) and this hook captures the near-bottom flag in a
 * `useLayoutEffect`-timed check that runs synchronously before the browser
 * paints the new count, then scrolls in a follow-up effect once the new
 * content has actually laid out.
 */
const AUTO_SCROLL_THRESHOLD_PX = 100

export function useAutoScrollOnAppend(
  containerRef: React.RefObject<HTMLElement | null>,
  itemCount: number,
): void {
  const previousItemCount = useRef(itemCount)
  const wasNearBottomRef = useRef(true)

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (itemCount === previousItemCount.current) return

    const grew = itemCount > previousItemCount.current
    previousItemCount.current = itemCount

    if (!grew) return
    if (!wasNearBottomRef.current) return

    const container = containerRef.current
    if (container == null) {
      window.scrollTo(0, document.documentElement.scrollHeight)
      return
    }
    container.scrollIntoView({ block: 'end' })
  }, [itemCount, containerRef])

  // Tracks "was the user within 100px of the bottom" continuously (cheap
  // scroll-event read, no per-event scrollTo) so the value is fresh the
  // instant a new step arrives — checked BEFORE that arrival grows the
  // page, per the doc comment above.
  useEffect(() => {
    if (typeof window === 'undefined') return

    function updateNearBottom(): void {
      const scrollBottom = window.scrollY + window.innerHeight
      const distanceFromBottom = document.documentElement.scrollHeight - scrollBottom
      wasNearBottomRef.current = distanceFromBottom <= AUTO_SCROLL_THRESHOLD_PX
    }

    updateNearBottom()
    window.addEventListener('scroll', updateNearBottom, { passive: true })
    window.addEventListener('resize', updateNearBottom)
    return () => {
      window.removeEventListener('scroll', updateNearBottom)
      window.removeEventListener('resize', updateNearBottom)
    }
  }, [])
}
