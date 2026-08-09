import { OriginBadge, type OriginBadgeVariant } from '../OriginBadge'
import { RoleSelect, type RoleSelectValue } from '../RoleSelect'
import { StatusBadge } from '../StatusBadge'
import { cn } from '../../utils/cn'

/**
 * UserTable — the admin users list table (Task 8.7, ADR 0002 §6, FR60).
 *
 * Presentational + controlled, matching `LoginForm`/`StatusGroupFilter`'s
 * established split: `AdminUsersPage.tsx` owns the actual API calls,
 * loading state, and dialog open/close state; this component only renders
 * the table and calls back on user intent (role-select change, or a
 * request to open the deactivate/reactivate confirm dialog / the
 * reset-password dialog — the *Request callbacks name that they only ask
 * the page to open a dialog, they never mutate anything themselves).
 *
 * **SCIM-owned-row disabling — documented trade-off (per the task
 * instructions):** this component does NOT know the server's auth mode
 * (`local` vs `oidc`) — it is a plain presentational primitive. The ADR's
 * actual rule (`admin_users.py::_scim_owned_conflict`) is "read-only only
 * while `origin === 'scim'` AND the server is in `oidc` mode" — a
 * SCIM-linked record is still editable from this UI while the server runs
 * in `local` mode (no live SCIM writer to contend with there). So the
 * `readOnly` flag on `rowState` is computed by the PAGE (which does know
 * `useCurrentUser().auth_mode`) and passed in per-row, rather than this
 * component hardcoding `origin === 'scim' => disabled`. This is
 * best-effort UX only — the 409 `scim-owned-user` response is the actual
 * enforcement backstop for any case the client-side flag misses (e.g. a
 * race where SCIM adopts a record between this table's render and the
 * user's click).
 */
export interface UserTableRow {
  id: string
  user_name: string
  display_name: string
  role: RoleSelectValue
  origin: OriginBadgeVariant
  active: boolean
  /** ISO datetime string, or `null` if never logged in — rendered as "Never". */
  last_login_at: string | null
}

export interface UserTableRowState {
  /** True while a mutation for this row (role change / deactivate / reactivate / reset password) is in flight. */
  pending?: boolean
  /** Inline error for this row (e.g. a `409 last-admin` from a role-change attempt) — rendered verbatim, role="alert". */
  error?: string | null
  /** Best-effort client-side disable for a SCIM-owned row in `oidc` mode — see the component doc comment above. */
  readOnly?: boolean
}

export interface UserTableProps {
  users: UserTableRow[]
  onRoleChange: (userId: string, role: RoleSelectValue) => void
  onDeactivateRequest: (userId: string) => void
  onReactivateRequest: (userId: string) => void
  onResetPasswordRequest: (userId: string) => void
  /** Per-row transient UI state, keyed by user id. A row not present here defaults to `{pending: false, error: null, readOnly: false}`. */
  rowState?: Record<string, UserTableRowState>
}

const EMPTY_ROW_STATE: UserTableRowState = {}

export function UserTable({
  users,
  onRoleChange,
  onDeactivateRequest,
  onReactivateRequest,
  onResetPasswordRequest,
  rowState = {},
}: UserTableProps) {
  return (
    <div className="overflow-x-auto rounded-lg border border-surface-overlay bg-surface-raised">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">Beeper admin users, their role, origin, and account status</caption>
        <thead>
          <tr className="border-b border-surface-overlay text-left">
            <th scope="col" className="px-4 py-2.5 font-medium text-text-secondary">
              User
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium text-text-secondary">
              Role
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium text-text-secondary">
              Origin
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium text-text-secondary">
              Status
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium text-text-secondary">
              Last Login
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium text-text-secondary">
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <UserRow
              key={user.id}
              user={user}
              state={rowState[user.id] ?? EMPTY_ROW_STATE}
              onRoleChange={onRoleChange}
              onDeactivateRequest={onDeactivateRequest}
              onReactivateRequest={onReactivateRequest}
              onResetPasswordRequest={onResetPasswordRequest}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function UserRow({
  user,
  state,
  onRoleChange,
  onDeactivateRequest,
  onReactivateRequest,
  onResetPasswordRequest,
}: {
  user: UserTableRow
  state: UserTableRowState
  onRoleChange: UserTableProps['onRoleChange']
  onDeactivateRequest: UserTableProps['onDeactivateRequest']
  onReactivateRequest: UserTableProps['onReactivateRequest']
  onResetPasswordRequest: UserTableProps['onResetPasswordRequest']
}) {
  const controlsDisabled = Boolean(state.pending) || Boolean(state.readOnly)

  return (
    <>
      <tr className="border-b border-surface-overlay/50 last:border-b-0" data-testid={`user-row-${user.id}`}>
        <td className="px-4 py-3 align-top">
          <div className="font-medium text-text-primary">{user.display_name || user.user_name}</div>
          <div className="text-xs text-text-muted">{user.user_name}</div>
        </td>
        <td className="px-4 py-3 align-top">
          <RoleSelect
            id={`role-select-${user.id}`}
            label="Role"
            hideLabel
            value={user.role}
            disabled={controlsDisabled}
            onChange={(role) => onRoleChange(user.id, role)}
          />
        </td>
        <td className="px-4 py-3 align-top">
          <OriginBadge origin={user.origin} />
        </td>
        <td className="px-4 py-3 align-top">
          <StatusBadge variant={user.active ? 'healthy' : 'critical'} label={user.active ? 'Active' : 'Inactive'} />
        </td>
        <td className="whitespace-nowrap px-4 py-3 align-top text-text-muted">{user.last_login_at ?? 'Never'}</td>
        <td className="px-4 py-3 align-top">
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={controlsDisabled}
              onClick={() => (user.active ? onDeactivateRequest(user.id) : onReactivateRequest(user.id))}
              className={cn(
                'rounded-md px-3 py-1.5 text-xs font-medium text-text-secondary',
                'transition-colors duration-150 hover:bg-surface-overlay hover:text-text-primary motion-reduce:transition-none',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
                'disabled:cursor-not-allowed disabled:opacity-60',
              )}
            >
              {user.active ? 'Deactivate' : 'Reactivate'}
            </button>
            {user.origin === 'local' ? (
              <button
                type="button"
                disabled={controlsDisabled}
                onClick={() => onResetPasswordRequest(user.id)}
                className={cn(
                  'rounded-md px-3 py-1.5 text-xs font-medium text-text-secondary',
                  'transition-colors duration-150 hover:bg-surface-overlay hover:text-text-primary motion-reduce:transition-none',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
                  'disabled:cursor-not-allowed disabled:opacity-60',
                )}
              >
                Reset password
              </button>
            ) : null}
          </div>
        </td>
      </tr>
      {state.error ? (
        <tr className="border-b border-surface-overlay/50 last:border-b-0">
          <td colSpan={6} className="px-4 py-2 text-xs text-status-critical" role="alert">
            {state.error}
          </td>
        </tr>
      ) : null}
    </>
  )
}
