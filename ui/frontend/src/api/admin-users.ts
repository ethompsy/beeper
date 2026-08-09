/**
 * admin-users.ts — typed client for the Task 8.7 admin users API
 * (`GET|POST /api/v1/admin/users/`, `PATCH /api/v1/admin/users/<id>`,
 * `POST /api/v1/admin/users/<id>/reset-password` —
 * `ui/beeper_ui/routes/admin_users.py`, ADR 0002 §6, FR60).
 *
 * Follows `sources-list.ts`'s shape (typed interfaces, a typed `*Error`
 * class, functions that call `apiFetch` and throw on `!response.ok`) with
 * one addition: every write route on this blueprint can 409 with one of
 * several distinct RFC7807 `type` slugs the UI must branch on (`last-admin`,
 * `scim-owned-user`, `local-user-creation-unavailable`,
 * `username-already-exists`) or 422 `validation-failed` — so the thrown
 * error carries a typed `type` slug alongside `.detail` (the exact backend
 * message, rendered verbatim by callers per the task instructions — this
 * client never re-derives copy).
 *
 * `apiFetch` itself already throws a typed `PermissionDeniedError` on any
 * 403 (`src/api/http.ts`) — that is how a non-admin caller's 403 surfaces
 * from every function below; this module does not catch or wrap it.
 */

import { apiFetch } from './http'

export type AdminUserRole = 'admin' | 'user'
export type AdminUserOrigin = 'local' | 'scim'

/** A user resource, per `admin_users.py`'s `_user_to_dict()` — never includes a password field. */
export interface AdminUserRecord {
  id: string
  user_name: string
  display_name: string
  role: AdminUserRole
  origin: AdminUserOrigin
  active: boolean
  /** ISO datetime string, or `null` if the account has never logged in. */
  last_login_at: string | null
}

/**
 * The RFC7807 `type` slugs this module's callers need to branch on
 * (`AdminUsersPage.tsx` / the dialog primitives), per the task's error
 * contract. `'unknown'` covers any other/unparseable problem body (e.g. a
 * plain 500) so callers always get a defined value to switch on instead of
 * `undefined`.
 */
export type AdminUsersErrorType =
  | 'validation-failed'
  | 'username-already-exists'
  | 'local-user-creation-unavailable'
  | 'user-not-found'
  | 'last-admin'
  | 'scim-owned-user'
  | 'unknown'

const KNOWN_ERROR_TYPES: readonly AdminUsersErrorType[] = [
  'validation-failed',
  'username-already-exists',
  'local-user-creation-unavailable',
  'user-not-found',
  'last-admin',
  'scim-owned-user',
]

const ERROR_TYPE_PREFIX = 'https://beeper.dev/errors/'

/**
 * Typed error thrown by every function in this module on a non-ok response.
 * `detail` is the backend's exact human-readable message (RFC7807 `detail`
 * field) — render it verbatim, per the task instructions, rather than
 * re-deriving copy from `type`. `message` mirrors `detail` (standard `Error`
 * contract) so `error.message` works too.
 */
export class AdminUsersError extends Error {
  readonly status: number
  readonly type: AdminUsersErrorType
  readonly detail: string

  constructor(detail: string, status: number, type: AdminUsersErrorType) {
    super(detail)
    this.name = 'AdminUsersError'
    this.status = status
    this.type = type
    this.detail = detail
  }
}

interface ProblemBody {
  type?: string
  detail?: string
}

function slugFromProblemType(type: string | undefined): AdminUsersErrorType {
  if (!type) return 'unknown'
  const slug = type.startsWith(ERROR_TYPE_PREFIX) ? type.slice(ERROR_TYPE_PREFIX.length) : type
  return (KNOWN_ERROR_TYPES as readonly string[]).includes(slug)
    ? (slug as AdminUsersErrorType)
    : 'unknown'
}

/** Parses a non-ok `Response` into a thrown `AdminUsersError`. Never returns. */
async function throwForResponse(response: Response, fallbackDetail: string): Promise<never> {
  let detail = fallbackDetail
  let type: AdminUsersErrorType = 'unknown'
  try {
    const body = (await response.json()) as ProblemBody
    if (body.detail) detail = body.detail
    type = slugFromProblemType(body.type)
  } catch {
    // Non-JSON or empty body (e.g. a plain 500) — fall back to the generic message.
  }
  throw new AdminUsersError(detail, response.status, type)
}

const USERS_ENDPOINT = '/api/v1/admin/users/'

/** `GET /api/v1/admin/users/` — bare array, sorted by username (server-side). */
export async function fetchUsers(signal?: AbortSignal): Promise<AdminUserRecord[]> {
  const response = await apiFetch(USERS_ENDPOINT, { signal })
  if (!response.ok) {
    await throwForResponse(response, `Failed to fetch users (HTTP ${response.status})`)
  }
  return (await response.json()) as AdminUserRecord[]
}

export interface CreateUserInput {
  user_name: string
  display_name?: string
  password: string
  role: AdminUserRole
}

/**
 * `POST /api/v1/admin/users/` — create a local user. Errors: `422
 * validation-failed` (empty username / invalid role / short password),
 * `409 username-already-exists`, `409 local-user-creation-unavailable`
 * (server running in `oidc` mode).
 */
export async function createUser(input: CreateUserInput): Promise<AdminUserRecord> {
  const response = await apiFetch(USERS_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!response.ok) {
    await throwForResponse(response, `Failed to create user (HTTP ${response.status})`)
  }
  return (await response.json()) as AdminUserRecord
}

export interface PatchUserInput {
  role?: AdminUserRole
  active?: boolean
}

/**
 * `PATCH /api/v1/admin/users/<id>` — role change and/or activate/
 * deactivate. Errors: `404 user-not-found`, `422 validation-failed`,
 * `409 last-admin` (refuses demoting/deactivating the last active admin),
 * `409 scim-owned-user` (SCIM-linked record, read-only while in `oidc`
 * mode).
 */
export async function patchUser(id: string, input: PatchUserInput): Promise<AdminUserRecord> {
  const response = await apiFetch(`${USERS_ENDPOINT}${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!response.ok) {
    await throwForResponse(response, `Failed to update user (HTTP ${response.status})`)
  }
  return (await response.json()) as AdminUserRecord
}

/**
 * `POST /api/v1/admin/users/<id>/reset-password`. Errors: `404
 * user-not-found`, `422 validation-failed` (short password), `409
 * scim-owned-user`.
 */
export async function resetPassword(id: string, password: string): Promise<AdminUserRecord> {
  const response = await apiFetch(`${USERS_ENDPOINT}${encodeURIComponent(id)}/reset-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
  if (!response.ok) {
    await throwForResponse(response, `Failed to reset password (HTTP ${response.status})`)
  }
  return (await response.json()) as AdminUserRecord
}
