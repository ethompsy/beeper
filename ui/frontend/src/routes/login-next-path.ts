/**
 * `resolveSafeNextPath` — client-side echo of the ADR 0002 §2 same-origin
 * `next=` validation for `/app/login` (Task 8.6).
 *
 * Split out of `LoginPage.tsx` into its own module (not a named export
 * alongside the page component) purely to keep `LoginPage.tsx` a
 * components-only file for React Fast Refresh (oxlint's
 * `react(only-export-components)` rule) — no functional reason beyond
 * that.
 *
 * The server-side authority for `next=` construction/validation is
 * `beeper_ui.middleware.session.build_login_redirect_next()` /
 * `resolve_request_identity()` (both only ever emit a same-origin
 * `/app/...` path). This function is defense in depth: a user can still
 * hand-edit the URL bar, so `LoginPage` must not blindly trust the raw
 * query param. Only a bare `/app` or `/app/...` path is honored; anything
 * else (an absolute URL, a protocol-relative `//host/...`, a bare path
 * outside `/app`, or a malformed percent-encoding) falls back to
 * `DEFAULT_NEXT`.
 */
export const DEFAULT_NEXT = '/app/investigations'

export function resolveSafeNextPath(raw: string | null): string {
  if (!raw) return DEFAULT_NEXT
  let decoded: string
  try {
    decoded = decodeURIComponent(raw)
  } catch {
    return DEFAULT_NEXT
  }
  if (decoded === '/app' || decoded.startsWith('/app/')) return decoded
  return DEFAULT_NEXT
}
