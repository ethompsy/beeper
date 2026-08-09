import { useEffect, useState } from 'react'
import { fetchCurrentUser, type AuthMode, type CurrentUserInfo, type CurrentUserRecord } from '../../api/http'

/**
 * useCurrentUser — hydrates identity/auth-mode from `GET /api/v1/auth/me`
 * (Task 8.4, ADR 0002 §3/§6/§8).
 *
 * **Failure-tolerant by contract** (Task 8.4 AC): an unreachable `/me`, a
 * non-2xx response, or a non-JSON body all resolve to
 * `{auth_mode: 'none', authenticated: false, user: null}` rather than
 * throwing or leaving the caller in a permanent loading state — the demo
 * (`make demo-up`, mode `none`, zero auth infrastructure reachable) must
 * render exactly as it does today. This is `fetchCurrentUser()`'s own
 * contract (`src/api/http.ts`) — this hook is a thin `useEffect` wrapper
 * around it, adding only the `loading` flag for the initial-probe window.
 *
 * Deliberately does NOT retry/poll: the auth mode is boot-time-immutable
 * backend config, and `authenticated`/`user` only need to be current as of
 * mount for this hook's known callers (future nav/login-state affordances,
 * 8.5/8.6/8.7's scope) — a stale-until-next-navigation value is an accepted
 * trade-off, not a bug, matching this codebase's SPA-navigation-remounts
 * model elsewhere.
 */
export type { AuthMode, CurrentUserRecord }

export interface CurrentUserState {
  /** True only while the initial `/me` probe is in flight. */
  loading: boolean
  authenticated: boolean
  auth_mode: AuthMode
  user: CurrentUserRecord | null
}

const INITIAL_STATE: CurrentUserInfo = {
  auth_mode: 'none',
  authenticated: false,
  user: null,
}

export function useCurrentUser(): CurrentUserState {
  const [state, setState] = useState<CurrentUserState>({ loading: true, ...INITIAL_STATE })

  useEffect(() => {
    let cancelled = false

    void fetchCurrentUser().then((info) => {
      if (cancelled) return
      setState({ loading: false, ...info })
    })

    return () => {
      cancelled = true
    }
  }, [])

  return state
}
