import { useState, type FormEvent } from 'react'
import { cn } from '../../utils/cn'

/**
 * LoginForm — the local-mode username/password login primitive (Task 8.6,
 * ADR 0002 §6, FR59).
 *
 * Presentational + controlled, matching this library's established split
 * (e.g. `StatusGroupFilter`): the page (`LoginPage.tsx`) owns the actual
 * `POST /api/v1/auth/login` call, `loading`/`error` state, and the
 * post-success redirect — this component only owns its two text-input
 * values and calls `onSubmit` with them. That keeps the primitive free of
 * any network/routing dependency, so it can be dropped into a Storybook
 * story (or a future OIDC-adjacent surface) without a backend.
 *
 * `error` is rendered VERBATIM as given — FR59's "login failure responses
 * do not distinguish unknown-user, bad-password, and deactivated" is a
 * backend contract (the uniform 401 body); this component has no opinion
 * on wording, it just surfaces whatever the page passes in.
 */
export interface LoginFormProps {
  /** Called with the trimmed username and raw password on submit (Enter key or the Sign in button). */
  onSubmit: (credentials: { username: string; password: string }) => void
  /** True while a submit is in flight — disables all fields and the submit button. */
  loading?: boolean
  /** Uniform error message to render above the submit button, or `null`/omitted for no error. */
  error?: string | null
}

export function LoginForm({ onSubmit, loading = false, error = null }: LoginFormProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (loading) return
    onSubmit({ username: username.trim(), password })
  }

  const canSubmit = username.trim().length > 0 && password.length > 0 && !loading

  return (
    <form
      onSubmit={handleSubmit}
      data-slot="login-form"
      noValidate
      className="flex flex-col gap-4"
    >
      <div className="flex flex-col gap-1.5">
        <label htmlFor="login-username" className="text-sm font-medium text-text-secondary">
          Username
        </label>
        <input
          id="login-username"
          name="username"
          type="text"
          autoComplete="username"
          autoFocus
          required
          value={username}
          disabled={loading}
          onChange={(event) => setUsername(event.target.value)}
          className="w-full rounded-lg border border-surface-overlay bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:opacity-60"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="login-password" className="text-sm font-medium text-text-secondary">
          Password
        </label>
        <input
          id="login-password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          disabled={loading}
          onChange={(event) => setPassword(event.target.value)}
          className="w-full rounded-lg border border-surface-overlay bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:opacity-60"
        />
      </div>

      {error ? (
        <p
          role="alert"
          data-slot="login-form-error"
          className="text-sm text-status-critical"
        >
          {error}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={!canSubmit}
        className={cn(
          'rounded-md bg-primary px-4 py-2 text-sm font-medium text-on-primary',
          'transition-colors duration-150 hover:bg-primary-hover motion-reduce:transition-none',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
          'disabled:cursor-not-allowed disabled:opacity-60',
        )}
      >
        {loading ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
  )
}
