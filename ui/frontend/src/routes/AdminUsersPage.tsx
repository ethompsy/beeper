import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ConfirmActionDialog,
  EmptyGroupState,
  UserFormDialog,
  UserTable,
  useCurrentUser,
  type CreateUserFormValues,
  type RoleSelectValue,
  type UserTableRowState,
} from '../lib'
import { PermissionDeniedError } from '../api/http'
import {
  AdminUsersError,
  createUser,
  fetchUsers,
  patchUser,
  resetPassword,
  type AdminUserRecord,
} from '../api/admin-users'

/**
 * AdminUsersPage — `/app/admin/users` (Task 8.7, ADR 0002 §6, FR60).
 *
 * Parity target: none — the first net-new React route with no Jinja
 * ancestor, per `docs/design/route-parity-targets.md` §9b. Data comes from
 * `admin_users_api_bp` (`/api/v1/admin/users/*`, `src/api/admin-users.ts`).
 * Registered as a CHILD of the `AppLayout` route tree in `App.tsx` (this
 * IS a Manage-nav destination, unlike `/app/login`) — the Users nav item
 * is gated in `AppLayout.tsx` by `useCurrentUser().user?.role === 'admin'`
 * (a UI affordance only; `require_role("admin")` on every route in
 * `admin_users.py` is the real enforcement boundary).
 *
 * ── States (never blank, per FR22-style contract) ───────────────────────
 *  - **Loading**: skeleton (`AdminUsersSkeleton`, mirrors `SourcesPage`'s
 *    `SourcesSkeleton` pattern — `role="status"`, `aria-label`).
 *  - **Forbidden (403)**: `fetchUsers()` throws the typed
 *    `PermissionDeniedError` (`apiFetch`'s uniform 403 signal) — rendered
 *    in-shell as "Admin access required", NOT a redirect (there is nowhere
 *    useful to redirect a logged-in-but-non-admin caller to), with no
 *    retry action (retrying would just 403 again).
 *  - **Error**: any other fetch failure (network/500) — same visual
 *    language as `SourcesPage.tsx`'s error state.
 *  - **Empty**: defensive only — the current admin is always in the list
 *    in practice — via `EmptyGroupState`.
 *  - **Loaded**: `UserTable` + a "Create user" button opening
 *    `UserFormDialog` (mode="create") + deactivate/reactivate via
 *    `ConfirmActionDialog` + reset-password via `UserFormDialog`
 *    (mode="reset-password").
 *
 * ── Mutation state design decisions (documented per the task) ──────────
 *  - **Role changes are NOT confirmed** (no dialog) — `UserTable`'s
 *    per-row `RoleSelect` fires `patchUser` immediately. If it 409s
 *    `last-admin` (e.g. demoting the sole active admin), the error is
 *    surfaced as an inline per-row banner (`UserTable`'s `rowState.error`)
 *    rather than a toast — the row's role select simply reverts (this
 *    page never optimistically mutates `users` before the PATCH
 *    resolves), so the failed attempt is visually undone AND explained.
 *  - **Deactivate/reactivate IS confirmed** (`ConfirmActionDialog`, per
 *    the task's explicit requirement) — its own `error` slot is where a
 *    `409 last-admin` on THIS path renders, dialog stays open (the
 *    explicit AC: "self-demotion blocked by last-admin 409 rendered
 *    inline").
 *  - **SCIM-owned-row read-only** is computed HERE (this page knows
 *    `useCurrentUser().auth_mode`) and passed to `UserTable` as
 *    `rowState[id].readOnly` — best-effort UX; the `409 scim-owned-user`
 *    response remains the actual backstop (`UserTable`'s own doc comment
 *    has the full trade-off writeup).
 *  - Every successful mutation **optimistically patches local state**
 *    from the response body (each write endpoint returns the full updated
 *    resource) rather than refetching the whole list — simpler and avoids
 *    a race between an in-flight refetch and a second quick mutation.
 */

interface ConfirmState {
  userId: string
  userName: string
  action: 'deactivate' | 'reactivate'
}

type FormDialogState = { mode: 'create' } | { mode: 'reset-password'; userId: string; userName: string } | null

/** Extracts a renderable message from a thrown value — `.detail` for our typed errors (verbatim backend copy), else `.message`, else a generic fallback. */
function describeError(err: unknown, fallback: string): string {
  if (err instanceof AdminUsersError) return err.detail
  if (err instanceof PermissionDeniedError) return err.detail
  if (err instanceof Error) return err.message
  return fallback
}

function replaceUser(users: AdminUserRecord[], updated: AdminUserRecord): AdminUserRecord[] {
  return users.map((user) => (user.id === updated.id ? updated : user))
}

function insertSorted(users: AdminUserRecord[], created: AdminUserRecord): AdminUserRecord[] {
  return [...users, created].sort((a, b) => a.user_name.localeCompare(b.user_name))
}

export function AdminUsersPage() {
  const { auth_mode: authMode } = useCurrentUser()

  const [users, setUsers] = useState<AdminUserRecord[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [forbidden, setForbidden] = useState(false)

  /** Per-row transient mutation state (pending/error) from role-change attempts — keyed by user id. */
  const [mutationState, setMutationState] = useState<Record<string, UserTableRowState>>({})

  const [confirmState, setConfirmState] = useState<ConfirmState | null>(null)
  const [confirmLoading, setConfirmLoading] = useState(false)
  const [confirmError, setConfirmError] = useState<string | null>(null)

  const [formDialogState, setFormDialogState] = useState<FormDialogState>(null)
  const [formLoading, setFormLoading] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchUsers(controller.signal)
      .then((data) => setUsers(data))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        if (err instanceof PermissionDeniedError) {
          setForbidden(true)
          return
        }
        setLoadError(describeError(err, 'Unable to load users.'))
      })
    return () => controller.abort()
  }, [])

  const handleRoleChange = useCallback((userId: string, role: RoleSelectValue) => {
    setMutationState((prev) => ({ ...prev, [userId]: { pending: true, error: null } }))
    patchUser(userId, { role })
      .then((updated) => {
        setUsers((prev) => (prev ? replaceUser(prev, updated) : prev))
        setMutationState((prev) => ({ ...prev, [userId]: {} }))
      })
      .catch((err: unknown) => {
        setMutationState((prev) => ({
          ...prev,
          [userId]: { pending: false, error: describeError(err, 'Unable to change role.') },
        }))
      })
  }, [])

  const handleDeactivateRequest = useCallback(
    (userId: string) => {
      const user = users?.find((u) => u.id === userId)
      if (!user) return
      setConfirmError(null)
      setConfirmState({ userId, userName: user.user_name, action: 'deactivate' })
    },
    [users],
  )

  const handleReactivateRequest = useCallback(
    (userId: string) => {
      const user = users?.find((u) => u.id === userId)
      if (!user) return
      setConfirmError(null)
      setConfirmState({ userId, userName: user.user_name, action: 'reactivate' })
    },
    [users],
  )

  function handleConfirm() {
    if (!confirmState) return
    const { userId, action } = confirmState
    setConfirmLoading(true)
    setConfirmError(null)
    patchUser(userId, { active: action === 'reactivate' })
      .then((updated) => {
        setUsers((prev) => (prev ? replaceUser(prev, updated) : prev))
        setConfirmState(null)
      })
      .catch((err: unknown) => setConfirmError(describeError(err, 'Unable to update this account.')))
      .finally(() => setConfirmLoading(false))
  }

  function handleConfirmOpenChange(open: boolean) {
    if (open) return
    setConfirmState(null)
    setConfirmError(null)
  }

  const handleResetPasswordRequest = useCallback(
    (userId: string) => {
      const user = users?.find((u) => u.id === userId)
      if (!user) return
      setFormError(null)
      setFormDialogState({ mode: 'reset-password', userId, userName: user.user_name })
    },
    [users],
  )

  function openCreateDialog() {
    setFormError(null)
    setFormDialogState({ mode: 'create' })
  }

  function handleFormOpenChange(open: boolean) {
    if (open) return
    setFormDialogState(null)
    setFormError(null)
  }

  function handleCreateSubmit(values: CreateUserFormValues) {
    setFormLoading(true)
    setFormError(null)
    createUser(values)
      .then((created) => {
        setUsers((prev) => (prev ? insertSorted(prev, created) : [created]))
        setFormDialogState(null)
      })
      .catch((err: unknown) => setFormError(describeError(err, 'Unable to create user.')))
      .finally(() => setFormLoading(false))
  }

  function handleResetPasswordSubmit(password: string) {
    if (!formDialogState || formDialogState.mode !== 'reset-password') return
    const { userId } = formDialogState
    setFormLoading(true)
    setFormError(null)
    resetPassword(userId, password)
      .then((updated) => {
        setUsers((prev) => (prev ? replaceUser(prev, updated) : prev))
        setFormDialogState(null)
      })
      .catch((err: unknown) => setFormError(describeError(err, 'Unable to reset password.')))
      .finally(() => setFormLoading(false))
  }

  const tableRowState = useMemo<Record<string, UserTableRowState>>(() => {
    if (!users) return {}
    const merged: Record<string, UserTableRowState> = {}
    for (const user of users) {
      merged[user.id] = {
        ...mutationState[user.id],
        // Best-effort UX only (see doc comment above) — the 409 from the
        // backend is the real gate.
        readOnly: authMode === 'oidc' && user.origin === 'scim',
      }
    }
    return merged
  }, [users, mutationState, authMode])

  const isLoading = users === null && loadError === null && !forbidden
  const canShowCreateButton = !forbidden && !loadError && !isLoading

  return (
    <div data-testid="admin-users-page" className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">Users</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Manage admin and user accounts for local sign-in. Role and status changes take effect within 60 seconds.
          </p>
        </div>
        {canShowCreateButton ? (
          <button
            type="button"
            onClick={openCreateDialog}
            className="shrink-0 rounded-md bg-primary px-4 py-2 text-sm font-medium text-on-primary transition-colors duration-150 hover:bg-primary-hover motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
          >
            Create user
          </button>
        ) : null}
      </div>

      {forbidden ? (
        <div role="status" className="rounded-lg border border-surface-overlay bg-surface-raised p-4">
          <h2 className="text-base font-semibold text-text-primary">Admin access required</h2>
          <p className="mt-1 text-sm text-text-secondary">
            Your account does not have permission to manage users. Contact an administrator if you believe this is a
            mistake.
          </p>
        </div>
      ) : null}

      {!forbidden && loadError ? (
        <div role="alert" className="rounded-lg border border-status-critical/30 bg-surface-raised p-4">
          <h2 className="text-base font-semibold text-status-critical">Unable to fetch users</h2>
          <p className="mt-1 text-sm text-text-secondary">{loadError}</p>
          <p className="mt-1 text-sm text-text-muted">Make sure the Beeper admin API is running and accessible.</p>
        </div>
      ) : null}

      {isLoading ? <AdminUsersSkeleton /> : null}

      {!forbidden && !loadError && !isLoading && users ? (
        users.length > 0 ? (
          <UserTable
            users={users}
            onRoleChange={handleRoleChange}
            onDeactivateRequest={handleDeactivateRequest}
            onReactivateRequest={handleReactivateRequest}
            onResetPasswordRequest={handleResetPasswordRequest}
            rowState={tableRowState}
          />
        ) : (
          <EmptyGroupState
            title="No users yet"
            description="Create the first local user to get started managing access."
          />
        )
      ) : null}

      <ConfirmActionDialog
        open={confirmState !== null}
        onOpenChange={handleConfirmOpenChange}
        title={
          confirmState
            ? `${confirmState.action === 'deactivate' ? 'Deactivate' : 'Reactivate'} ${confirmState.userName}?`
            : ''
        }
        description={
          confirmState?.action === 'deactivate'
            ? 'They will immediately lose access. You can reactivate this account at any time.'
            : 'They will regain access with their existing role.'
        }
        confirmLabel={confirmState?.action === 'deactivate' ? 'Deactivate' : 'Reactivate'}
        destructive={confirmState?.action === 'deactivate'}
        loading={confirmLoading}
        error={confirmError}
        onConfirm={handleConfirm}
      />

      <UserFormDialog
        open={formDialogState !== null}
        onOpenChange={handleFormOpenChange}
        mode={formDialogState?.mode ?? 'create'}
        targetUserName={formDialogState?.mode === 'reset-password' ? formDialogState.userName : undefined}
        onCreateSubmit={handleCreateSubmit}
        onResetPasswordSubmit={handleResetPasswordSubmit}
        loading={formLoading}
        error={formError}
      />
    </div>
  )
}

function AdminUsersSkeleton() {
  return (
    <div
      data-testid="admin-users-skeleton"
      role="status"
      aria-label="Loading users"
      className="flex flex-col gap-2 rounded-lg border border-surface-overlay bg-surface-raised p-4 animate-pulse motion-reduce:animate-none"
    >
      {Array.from({ length: 3 }, (_, index) => (
        <div key={index} className="h-6 rounded bg-surface-overlay" />
      ))}
    </div>
  )
}
