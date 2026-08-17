import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useState, type FormEvent } from 'react'
import { cn } from '../../utils/cn'
import { RoleSelect, type RoleSelectValue } from '../RoleSelect'

/**
 * UserFormDialog — accessible dialog (Radix `Dialog`) for creating a local
 * user and, in a second mode, resetting an existing user's password (Task
 * 8.7, ADR 0002 §6, FR60).
 *
 * **Design decision (documented per the task instructions):** ONE component
 * with a `mode: 'create' | 'reset-password'` prop, rather than two
 * components — the task explicitly allows either. `mode="create"` renders
 * username/display-name/password/role (`RoleSelect`); `mode="reset-password"`
 * renders a single password field + a confirmation field for an existing
 * `targetUserName`. Sharing one component keeps the dialog chrome (Radix
 * wiring, error slot, footer buttons, loading state) written once; the two
 * modes' field sets are disjoint enough that a shared `mode` switch reads
 * more clearly than prop-drilling optional fields through a single "do
 * everything" shape.
 *
 * `MIN_PASSWORD_LENGTH` is exported here (not hardcoded a second time) and
 * re-used by `AdminUsersPage.tsx` if it needs to reference the same rule —
 * mirrors the backend's `password_hashing.MIN_PASSWORD_LENGTH = 12`
 * (`ui/beeper_ui/services/password_hashing.py`) so the two never drift
 * independently; this is client-side pre-validation only; the backend is
 * still the enforcement boundary and its `422 validation-failed` detail is
 * rendered verbatim via the `error` prop if the client check is ever
 * bypassed or the rule differs.
 *
 * Presentational + controlled, matching this library's split: the PAGE
 * (`AdminUsersPage.tsx`) owns the actual `createUser`/`resetPassword` API
 * call, `loading`, and server-side `error` (rendered inline, dialog stays
 * open — the create-flow ACs for `local-user-creation-unavailable` /
 * `username-already-exists` / `validation-failed` all require this, not a
 * toast).
 */
export const MIN_PASSWORD_LENGTH = 12

export interface CreateUserFormValues {
  user_name: string
  display_name: string
  password: string
  role: RoleSelectValue
}

export type UserFormDialogMode = 'create' | 'reset-password'

export interface UserFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  mode: UserFormDialogMode
  /** `mode="reset-password"` only — whose password is being reset, shown in the title. */
  targetUserName?: string
  /** `mode="create"` only. */
  onCreateSubmit?: (values: CreateUserFormValues) => void
  /** `mode="reset-password"` only. */
  onResetPasswordSubmit?: (password: string) => void
  /** True while the submit request is in flight — disables all fields and both buttons. */
  loading?: boolean
  /** Server-side error (e.g. `AdminUsersError.detail`) rendered verbatim, inline. Dialog stays open. */
  error?: string | null
}

export function UserFormDialog({
  open,
  onOpenChange,
  mode,
  targetUserName,
  onCreateSubmit,
  onResetPasswordSubmit,
  loading = false,
  error = null,
}: UserFormDialogProps) {
  const [userName, setUserName] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [role, setRole] = useState<RoleSelectValue>('user')
  const [clientError, setClientError] = useState<string | null>(null)

  // Reset all local field/validation state whenever the dialog transitions
  // to open — otherwise a re-open (e.g. create -> close -> create again, or
  // reset-password on a different row) would show stale values from the
  // previous open.
  useEffect(() => {
    if (!open) return
    setUserName('')
    setDisplayName('')
    setPassword('')
    setConfirmPassword('')
    setRole('user')
    setClientError(null)
  }, [open])

  function handleOpenChange(next: boolean) {
    if (loading) return
    onOpenChange(next)
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (loading) return
    setClientError(null)

    if (password.length < MIN_PASSWORD_LENGTH) {
      setClientError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`)
      return
    }

    if (mode === 'create') {
      const trimmedUsername = userName.trim()
      if (!trimmedUsername) {
        setClientError('Username is required.')
        return
      }
      onCreateSubmit?.({
        user_name: trimmedUsername,
        display_name: displayName.trim(),
        password,
        role,
      })
      return
    }

    // mode === 'reset-password'
    if (password !== confirmPassword) {
      setClientError('Passwords do not match.')
      return
    }
    onResetPasswordSubmit?.(password)
  }

  const title = mode === 'create' ? 'Create user' : `Reset password${targetUserName ? ` for ${targetUserName}` : ''}`
  const description =
    mode === 'create'
      ? 'Creates a local, password-based account. Local accounts are only usable while SSO is disabled.'
      : 'Sets a new password for this local account. The user will need to sign in with the new password.'
  const submitLabel = mode === 'create' ? 'Create user' : 'Reset password'
  const submitLabelLoading = mode === 'create' ? 'Creating…' : 'Resetting…'
  const visibleError = clientError ?? error

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-surface-base/80 transition-opacity duration-150 motion-reduce:transition-none" />
        <Dialog.Content
          data-slot="user-form-dialog"
          data-mode={mode}
          className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-surface-overlay bg-surface-raised p-6 shadow-lg transition-opacity duration-150 motion-reduce:transition-none focus:outline-none"
        >
          <Dialog.Title className="text-lg font-semibold text-text-primary">{title}</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-text-secondary">{description}</Dialog.Description>

          <form onSubmit={handleSubmit} noValidate className="mt-4 flex flex-col gap-4">
            {mode === 'create' ? (
              <>
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="user-form-username" className="text-sm font-medium text-text-secondary">
                    Username
                  </label>
                  <input
                    id="user-form-username"
                    name="user_name"
                    type="text"
                    autoComplete="off"
                    autoFocus
                    required
                    value={userName}
                    disabled={loading}
                    onChange={(event) => setUserName(event.target.value)}
                    className={inputClassName}
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label htmlFor="user-form-display-name" className="text-sm font-medium text-text-secondary">
                    Display name <span className="text-text-muted">(optional)</span>
                  </label>
                  <input
                    id="user-form-display-name"
                    name="display_name"
                    type="text"
                    autoComplete="off"
                    value={displayName}
                    disabled={loading}
                    onChange={(event) => setDisplayName(event.target.value)}
                    className={inputClassName}
                  />
                </div>
              </>
            ) : null}

            <div className="flex flex-col gap-1.5">
              <label htmlFor="user-form-password" className="text-sm font-medium text-text-secondary">
                {mode === 'create' ? 'Password' : 'New password'}
              </label>
              <input
                id="user-form-password"
                name="password"
                type="password"
                autoComplete="new-password"
                autoFocus={mode === 'reset-password'}
                required
                value={password}
                disabled={loading}
                onChange={(event) => setPassword(event.target.value)}
                className={inputClassName}
              />
              <p className="text-xs text-text-muted">At least {MIN_PASSWORD_LENGTH} characters.</p>
            </div>

            {mode === 'reset-password' ? (
              <div className="flex flex-col gap-1.5">
                <label htmlFor="user-form-confirm-password" className="text-sm font-medium text-text-secondary">
                  Confirm new password
                </label>
                <input
                  id="user-form-confirm-password"
                  name="confirm_password"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={confirmPassword}
                  disabled={loading}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  className={inputClassName}
                />
              </div>
            ) : null}

            {mode === 'create' ? (
              <RoleSelect id="user-form-role" label="Role" value={role} onChange={setRole} disabled={loading} />
            ) : null}

            {visibleError ? (
              <p role="alert" data-slot="user-form-dialog-error" className="text-sm text-status-critical">
                {visibleError}
              </p>
            ) : null}

            <div className="mt-2 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => handleOpenChange(false)}
                disabled={loading}
                className={cn(
                  'rounded-md px-4 py-2 text-sm font-medium text-text-secondary',
                  'transition-colors duration-150 hover:bg-surface-overlay hover:text-text-primary motion-reduce:transition-none',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
                  'disabled:cursor-not-allowed disabled:opacity-60',
                )}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className={cn(
                  'rounded-md bg-primary px-4 py-2 text-sm font-medium text-on-primary',
                  'transition-colors duration-150 hover:bg-primary-hover motion-reduce:transition-none',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
                  'disabled:cursor-not-allowed disabled:opacity-60',
                )}
              >
                {loading ? submitLabelLoading : submitLabel}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

const inputClassName =
  'w-full rounded-lg border border-surface-overlay bg-surface-base px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:opacity-60'
