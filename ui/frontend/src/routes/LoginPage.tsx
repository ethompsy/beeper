import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { LoginForm } from '../lib'
import { apiFetch, navigateTo } from '../api/http'
import { resolveSafeNextPath } from './login-next-path'

/**
 * LoginPage — `/app/login` (Task 8.6, ADR 0002 §6, the first React route
 * with no Jinja ancestor — see `docs/design/route-parity-targets.md` §9).
 *
 * Renders OUTSIDE `AppLayout` (no sidebar/shell chrome — `App.tsx` mounts
 * this as a sibling of the `AppLayout` route tree, not a child of it): a
 * minimal centered card, per ADR §6 ("minimal centered card outside the
 * sidebar shell").
 *
 * Flow: reads `?next=` (validated — see `resolveSafeNextPath` below),
 * posts `{username, password}` to `POST /api/v1/auth/login` via the
 * shared `apiFetch` seam, and on success navigates to `next` (or
 * `/app/investigations`). A full `window.location` navigation
 * (`navigateTo`, not React Router's `useNavigate`) is used deliberately —
 * the freshly-established session cookie needs a real request round-trip
 * to take effect for the rest of the app (SSE connections, the next
 * page's own data fetches), and this mirrors exactly how `apiFetch`'s own
 * 401 -> login redirect already navigates (`src/api/http.ts`'s
 * `goToLogin`) — one full-navigation convention for both directions of
 * this handoff, not two.
 *
 * FR59: the failure message is uniform regardless of cause (unknown
 * username, wrong password, deactivated account) — this page never tries
 * to distinguish them, because the backend response itself doesn't either.
 */
const GENERIC_LOGIN_ERROR = 'Invalid username or password.'
const UNEXPECTED_ERROR = 'Something went wrong. Please try again.'

export function LoginPage() {
  const [searchParams] = useSearchParams()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const next = resolveSafeNextPath(searchParams.get('next'))

  async function handleSubmit({
    username,
    password,
  }: {
    username: string
    password: string
  }) {
    setLoading(true)
    setError(null)
    try {
      const response = await apiFetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      if (!response.ok) {
        setError(GENERIC_LOGIN_ERROR)
        setLoading(false)
        return
      }
      navigateTo(next)
      // Deliberately no `setLoading(false)` here — the page is about to be
      // replaced by the post-login navigation; leaving the form disabled
      // avoids a flash of an interactive-but-about-to-vanish form.
    } catch {
      setError(UNEXPECTED_ERROR)
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-base px-4">
      <div className="w-full max-w-sm rounded-xl border border-surface-overlay bg-surface-raised p-8 shadow-lg">
        <h1 className="mb-6 text-2xl font-semibold text-text-primary">Sign in to Beeper</h1>
        <LoginForm onSubmit={handleSubmit} loading={loading} error={error} />
      </div>
    </div>
  )
}
