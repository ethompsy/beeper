import { useCallback, useLayoutEffect, useRef, useEffect } from 'react'

/**
 * useScrollRestoration — restores the page's scroll position when the list
 * route is re-entered after visiting detail (Task 2.2, FR22 /
 * docs/specs/ux-design-specification.md "Scroll preservation": "Investigation
 * list scroll position preserved on back navigation... Session-stored scroll
 * offset, restored on back navigation").
 *
 * Tracks `window.scrollY` (not a nested container's `scrollTop`): the app
 * shell (`AppShell.tsx`, Task 2.1) uses `min-h-screen` with no
 * `overflow-hidden`/fixed-height ancestor, so the page scrolls at the
 * document/window level, not inside a bounded inner pane. This matches the
 * legacy Jinja app's behavior too (plain document scroll).
 *
 * Implementation: `sessionStorage`, keyed by `key` (callers pass something
 * stable like the route pathname), so the offset survives the list route's
 * full unmount/remount when navigating to detail and back (React Router
 * unmounts the list route entirely).
 *
 * `sessionStorage` (not `localStorage`) matches the spec's explicit call-out
 * ("Session-stored scroll offset") and scopes the restoration to the current
 * tab/session rather than persisting indefinitely across browser restarts.
 *
 * ── `history.scrollRestoration = 'manual'` ──
 *
 * The browser has its OWN native scroll restoration on back/forward
 * navigation (restoring scroll position tied to focus/history state), which
 * actively fights this hook: after navigating back to the list, the
 * browser's native restore (and/or its focus-follows-history behavior) can
 * re-apply a stale small offset (e.g. scrolling a previously-focused
 * element into view) AFTER this hook's own restore has already run,
 * clobbering it. Setting `scrollRestoration = 'manual'` opts this SPA out of
 * that native behavior so this hook is the only thing controlling scroll
 * position across route changes — the standard fix used by React Router's
 * own `<ScrollRestoration>` and most SPA routers.
 *
 * `ready` (important): the caller must pass `true` only once the page has
 * rendered its REAL content (not the loading skeleton). On a cold remount,
 * this page fetches investigations again before it has anything to render,
 * so the very first render is short (skeleton). Restoring scroll on that
 * first render would call `window.scrollTo` against a document that isn't
 * tall enough yet, silently clamping to a much smaller offset than the
 * saved one. Waiting for `ready` ensures the restore happens once the full
 * row list (and therefore the full page height) exists.
 *
 * Save timing: scroll position is tracked continuously into a ref on every
 * `scroll` event (cheap — no `sessionStorage` write per event) and flushed
 * to `sessionStorage` from the `useLayoutEffect` cleanup, which fires when
 * this page unmounts (e.g. navigating to the detail route).
 *
 * ── Reapplying the restore on the next animation frame ──
 *
 * The synchronous, during-render restore (below) handles the common case,
 * but on a real browser back-navigation, other browser-native behavior
 * (e.g. restoring focus to the element that triggered the navigation, which
 * scrolls it into view by default) can run AFTER this render and silently
 * override the restored offset before the user sees the page. To win that
 * race deterministically, the restore is re-applied once more on the next
 * `requestAnimationFrame` after `ready` flips true — by then, any
 * navigation-triggered native scroll adjustment has already happened, so
 * this second application is the one that sticks.
 */
export function useScrollRestoration(key: string, ready: boolean): void {
  const storageKey = `beeper:list-scroll:${key}`
  const lastKnownScrollY = useRef(0)
  const hasRestored = useRef(false)

  if (typeof window !== 'undefined' && 'scrollRestoration' in window.history) {
    window.history.scrollRestoration = 'manual'
  }

  const restoreNow = useCallback((): void => {
    if (typeof window === 'undefined') return
    const saved = sessionStorage.getItem(storageKey)
    if (saved != null) {
      window.scrollTo(0, Number(saved))
    }
  }, [storageKey])

  // Restore exactly once, as soon as `ready` first becomes true — during
  // render (not an effect) so the jump to the saved offset happens before
  // the browser paints the just-loaded content, avoiding a visible flash of
  // the top of the page. Guarded by `typeof window` for test/SSR safety.
  if (ready && !hasRestored.current) {
    hasRestored.current = true
    restoreNow()
  }

  // Scroll tracking + save-on-unmount — mounted/torn down exactly once per
  // `storageKey` (NOT re-run when `ready` changes, so the transition to
  // `ready` never triggers this effect's cleanup and its sessionStorage
  // write).
  useLayoutEffect(() => {
    function handleScroll(): void {
      lastKnownScrollY.current = window.scrollY
    }

    window.addEventListener('scroll', handleScroll, { passive: true })

    return () => {
      window.removeEventListener('scroll', handleScroll)
      sessionStorage.setItem(storageKey, String(lastKnownScrollY.current))
    }
  }, [storageKey])

  // Separate, independent effect for the rAF reapply — deliberately split
  // out from the effect above so the `ready` transition doesn't tear down
  // the scroll listener or trigger a premature save.
  useEffect(() => {
    if (!ready) return
    const rafId = requestAnimationFrame(restoreNow)
    return () => cancelAnimationFrame(rafId)
  }, [ready, restoreNow])
}
