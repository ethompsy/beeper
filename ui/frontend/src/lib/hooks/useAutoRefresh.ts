import { useEffect, useRef } from 'react'

/**
 * useAutoRefresh — generic client-side polling primitive that replaces the
 * Jinja `hx-trigger="every Ns"` auto-refresh pattern (Task 5.2; route parity
 * doc §3 — "the React target must replace the auto-refresh behavior (poll or
 * SSE, implementer's call)"). Also the natural fit for Task 5.3's
 * Sources/Spending dashboards, which the parity doc's §4a/§4b explicitly
 * call out as needing "the same treatment" (their own `every 5s`/
 * `every 30s` HTMX partials) — kept here as a reusable library hook rather
 * than inlined in `IngestionStatsPage` for that reason.
 *
 * Calls `onTick` every `intervalMs` while the document is visible. Pauses
 * (clears the interval; does not accumulate missed ticks) while the tab is
 * hidden (`document.visibilitychange`) — resumes polling immediately, on a
 * fresh interval, the moment the tab becomes visible again, rather than
 * firing a burst of catch-up calls. This is a deliberate choice, not the
 * only valid one (the AC allows "justified if you choose not to" — pausing
 * was chosen because a hidden ingestion-stats tab has no user watching the
 * live counters, so polling it only spends the operator's request budget
 * and the browser's battery for no visible benefit; nothing here depends on
 * the tab continuing to poll in the background).
 *
 * `onTick` is read from a ref on every fire so callers can pass a fresh
 * inline closure each render without tearing down/recreating the interval —
 * same pattern `useInvestigationEvents` uses for its callback options.
 */
export interface UseAutoRefreshOptions {
  /** Interval in ms between `onTick` calls. */
  intervalMs: number
  /** When `false`, polling is disabled entirely (no interval scheduled). Defaults to `true`. */
  enabled?: boolean
}

export function useAutoRefresh(onTick: () => void, options: UseAutoRefreshOptions): void {
  const { intervalMs, enabled = true } = options

  const onTickRef = useRef(onTick)
  onTickRef.current = onTick

  useEffect(() => {
    if (!enabled) return
    if (typeof window === 'undefined' || typeof document === 'undefined') return

    let intervalId: ReturnType<typeof setInterval> | undefined

    function start() {
      if (intervalId !== undefined) return
      intervalId = setInterval(() => onTickRef.current(), intervalMs)
    }

    function stop() {
      if (intervalId === undefined) return
      clearInterval(intervalId)
      intervalId = undefined
    }

    function handleVisibilityChange() {
      if (document.hidden) {
        stop()
      } else {
        start()
      }
    }

    if (!document.hidden) {
      start()
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      stop()
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [intervalMs, enabled])
}
