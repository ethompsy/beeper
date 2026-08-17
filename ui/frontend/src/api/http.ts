/**
 * http.ts — shared `apiFetch` wrapper (Task 8.4, ADR 0002 §2/§7/§8 "Frontend
 * seam" — the one seam every `src/api/*.ts` client is migrated onto).
 *
 * `apiFetch` is a drop-in replacement for the browser's `fetch` — same
 * signature, same return type — so migrating a client is a mechanical
 * `fetch(` -> `apiFetch(` rename (see `src/api/test/no-bare-fetch.test.ts`,
 * the static sweep proving that rename actually happened everywhere). It
 * adds exactly three behaviors on top of native `fetch`:
 *
 *  1. **Same-origin credentials by default** (`credentials: 'same-origin'`)
 *     so the identity-only session cookie (Task 8.3) flows on every
 *     `/api/v1/*` call without each client opting in individually. A caller
 *     can still override `credentials` explicitly in `init` — this is a
 *     default, not a hard-coded value.
 *
 *  2. **401 with the `authentication-required` problem type -> mode-aware
 *     login redirect**, as a side effect, then the Response is returned
 *     unchanged so each client's own `!response.ok` handling still runs
 *     (mostly moot, since the browser is about to navigate away) — no
 *     per-client code needed for this case. `apiFetch` doesn't statically
 *     know the auth mode (the 401 body itself doesn't carry it — see
 *     `beeper_ui/middleware/permissions.py::_problem_response()`), so it
 *     resolves it via `GET /api/v1/auth/me` (`fetchCurrentUser()`, cached
 *     per page load — mode is boot-time-immutable config, never changes at
 *     runtime). Mode `none` never actually reaches this branch (Task 8.3's
 *     resolver never emits this 401 there), but if `/me` itself ever
 *     reports `none` this is treated as the ADR's "none -> never redirects"
 *     row, matching `useCurrentUser`'s failure-tolerant default.
 *
 *  3. **403 THROWS a typed `PermissionDeniedError`** instead of returning —
 *     unlike 401, there's nothing to redirect to (the caller IS
 *     authenticated, just not authorized), so the caller needs an explicit,
 *     typed signal to render a permission-denied state instead of a generic
 *     fetch error. This applies uniformly across all 8 clients: ANY
 *     `/api/v1/*` route can 403 today, not only admin-gated ones — the
 *     resolver's `not-provisioned` branch (ADR §7 step 1 "forbidden") can
 *     403 an authenticated-but-unprovisioned caller on any route, on top of
 *     `require_role`'s existing admin-only 403s. Both share one RFC7807
 *     shape (`application/problem+json`), so `apiFetch` does not need to
 *     special-case which `type` produced it — every 403 is a permission
 *     state.
 *
 * Every OTHER status (404/500/503/etc.) passes through untouched — each of
 * the 8 clients keeps its own `!response.ok` handling and error-message
 * conventions for those, unchanged by this migration.
 */

const AUTH_REQUIRED_TYPE = 'https://beeper.dev/errors/authentication-required'
const ME_ENDPOINT = '/api/v1/auth/me'

export type AuthMode = 'none' | 'local' | 'oidc'

/** The `user` object shape from `GET /api/v1/auth/me` (ADR §3) — wire field names, unchanged. */
export interface CurrentUserRecord {
  user_name: string
  display_name: string
  /** `null` only for the SCIM-strict "authenticated but not provisioned" edge case. */
  role: 'admin' | 'user' | null
}

/** `useCurrentUser`'s hydrated shape (minus its own `loading` flag). */
export interface CurrentUserInfo {
  auth_mode: AuthMode
  authenticated: boolean
  user: CurrentUserRecord | null
}

const UNREACHABLE_CURRENT_USER: CurrentUserInfo = {
  auth_mode: 'none',
  authenticated: false,
  user: null,
}

/** Thrown by `apiFetch` on any 403 — callers render a permission-denied state instead of a generic error. */
export class PermissionDeniedError extends Error {
  readonly status = 403 as const
  readonly detail: string

  constructor(detail: string) {
    super(detail)
    this.name = 'PermissionDeniedError'
    this.detail = detail
  }
}

interface ProblemDetails {
  type?: string
  detail?: string
}

interface CurrentUserResponseBody {
  authenticated?: boolean
  auth_mode?: string
  user?: {
    user_name?: string
    display_name?: string
    role?: 'admin' | 'user' | null
  } | null
}

function normalizeAuthMode(value: string | undefined): AuthMode {
  return value === 'local' || value === 'oidc' ? value : 'none'
}

// Cached across `apiFetch` 401s within the page's lifetime: the auth MODE is
// boot-time-immutable backend config, so once known it never needs
// re-probing just to pick a redirect target. Deliberately NOT used to cache
// `authenticated`/`user` — those legitimately change mid-session, which is
// exactly why `recheckAuthAfterStreamFailure` below always probes fresh.
let cachedAuthMode: AuthMode | null = null

function defaultNavigate(url: string): void {
  window.location.href = url
}

let navigateFn: (url: string) => void = defaultNavigate

/** Test seam: substitute the navigation side effect (defaults to `window.location.href = url`). */
export function __setNavigateForTest(fn: (url: string) => void): void {
  navigateFn = fn
}

/**
 * Navigate the browser to `url` — the same indirection this module's own
 * 401-redirect-to-login path uses internally (`goToLogin`/`navigateFn`).
 * Exported (Task 8.6) so `LoginPage.tsx`'s post-login redirect (success ->
 * `next` or `/app/investigations`) shares exactly ONE navigation seam with
 * this module's unauthenticated -> login redirect, rather than each
 * maintaining its own `window.location.href` call site and its own
 * `__setNavigateForTest`-equivalent for tests.
 */
export function navigateTo(url: string): void {
  navigateFn(url)
}

/** Test-only reset — clears the cached mode and restores the default navigate function. */
export function __resetApiFetchForTest(): void {
  cachedAuthMode = null
  navigateFn = defaultNavigate
}

/**
 * Fetch + parse `GET /api/v1/auth/me`. Failure-tolerant by design (`useCurrentUser`'s
 * entire contract, Task 8.4 AC): a network failure, a non-2xx response, or a
 * non-JSON/malformed body all resolve to the `{auth_mode: 'none', authenticated:
 * false, user: null}` fallback rather than throwing — the demo must render with
 * zero auth infrastructure reachable. Always fetches fresh (no caching here;
 * see `cachedAuthMode` above for the narrower, mode-only cache `apiFetch`
 * uses internally).
 */
export async function fetchCurrentUser(): Promise<CurrentUserInfo> {
  let response: Response
  try {
    response = await fetch(ME_ENDPOINT, { credentials: 'same-origin' })
  } catch {
    return UNREACHABLE_CURRENT_USER
  }

  if (!response.ok) return UNREACHABLE_CURRENT_USER

  let body: CurrentUserResponseBody
  try {
    body = (await response.json()) as CurrentUserResponseBody
  } catch {
    return UNREACHABLE_CURRENT_USER
  }

  const mode = normalizeAuthMode(body.auth_mode)
  cachedAuthMode = mode

  const user =
    body.user != null
      ? {
          user_name: body.user.user_name ?? '',
          display_name: body.user.display_name ?? '',
          role: body.user.role ?? null,
        }
      : null

  return { auth_mode: mode, authenticated: Boolean(body.authenticated), user }
}

async function resolveModeForRedirect(): Promise<AuthMode> {
  if (cachedAuthMode != null) return cachedAuthMode
  const info = await fetchCurrentUser()
  return info.auth_mode
}

function loginPathForMode(mode: 'local' | 'oidc'): string {
  return mode === 'oidc' ? '/auth/login' : '/app/login'
}

function currentAppPath(): string {
  return `${window.location.pathname}${window.location.search}${window.location.hash}`
}

function goToLogin(mode: 'local' | 'oidc'): void {
  const next = encodeURIComponent(currentAppPath())
  navigateFn(`${loginPathForMode(mode)}?next=${next}`)
}

async function redirectToLogin(): Promise<void> {
  const mode = await resolveModeForRedirect()
  if (mode === 'none') return // ADR: mode `none` never redirects
  goToLogin(mode)
}

/**
 * Re-check `/api/v1/auth/me` and redirect to login only if the session has
 * genuinely dropped. Used by `useInvestigationEvents`'s `onFailed` callback
 * (see `InvestigationDetailPage`'s doc comment for the full SSE-auth-failure
 * design note) rather than assuming every terminal SSE failure is a 401:
 * the browser's native `EventSource` never exposes the HTTP status code
 * that closed the connection, so a `failed` state is equally consistent
 * with "the session expired" and "the operator/network hiccuped" — this
 * function is the discriminator. Always probes fresh (deliberately bypasses
 * `cachedAuthMode`'s mode-only cache): a still-`authenticated` result means
 * the failure was NOT an auth drop, so it is a no-op and the existing "Live
 * updates unavailable" banner is the correct (and only) UX for that case.
 */
export async function recheckAuthAfterStreamFailure(): Promise<void> {
  const info = await fetchCurrentUser()
  if (info.auth_mode === 'none' || info.authenticated) return
  goToLogin(info.auth_mode)
}

async function parseProblem(response: Response): Promise<ProblemDetails | null> {
  try {
    const clonable = typeof response.clone === 'function' ? response.clone() : response
    return (await clonable.json()) as ProblemDetails
  } catch {
    return null
  }
}

/**
 * Drop-in `fetch` replacement for every `src/api/*.ts` client. See the
 * module doc above for the three behaviors layered on top of native fetch.
 */
export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, { credentials: 'same-origin', ...init })

  if (response.status === 401) {
    const problem = await parseProblem(response)
    if (problem?.type === AUTH_REQUIRED_TYPE) {
      void redirectToLogin()
    }
    return response
  }

  if (response.status === 403) {
    const problem = await parseProblem(response)
    throw new PermissionDeniedError(
      problem?.detail ?? 'You do not have permission to access this resource.',
    )
  }

  return response
}
