/**
 * admin-users.test.ts (Task 8.7 — ADR 0002 §6, FR60).
 *
 * Coverage for `src/api/admin-users.ts`'s success + every documented error
 * path per endpoint, per `ui/beeper_ui/routes/admin_users.py`. Mocks
 * `global.fetch` directly (matching `sources-list.test.ts`'s convention —
 * `apiFetch` is a thin passthrough over `fetch` for every non-401/403
 * status, so stubbing `fetch` exercises the real `apiFetch` code path
 * rather than bypassing it).
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  AdminUsersError,
  createUser,
  fetchUsers,
  patchUser,
  resetPassword,
  type AdminUserRecord,
} from '../admin-users'

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response
}

function problem(typeSuffix: string, detail: string, status: number): Response {
  return jsonResponse(
    {
      type: `https://beeper.dev/errors/${typeSuffix}`,
      title: 'Problem',
      status,
      detail,
      instance: '/api/v1/admin/users/',
    },
    status,
  )
}

function stubFetch(response: Response) {
  const fetchMock = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const USER: AdminUserRecord = {
  id: 'user-1',
  user_name: 'alice',
  display_name: 'Alice Alpha',
  role: 'admin',
  origin: 'local',
  active: true,
  last_login_at: '2026-08-09T12:00:00+00:00',
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchUsers', () => {
  it('returns the bare array on success', async () => {
    stubFetch(jsonResponse([USER]))
    await expect(fetchUsers()).resolves.toEqual([USER])
  })

  it('calls GET /api/v1/admin/users/', async () => {
    const fetchMock = stubFetch(jsonResponse([]))
    await fetchUsers()
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/users/', expect.objectContaining({}))
  })

  it('throws AdminUsersError with the response status on a generic failure (no JSON body)', async () => {
    stubFetch({ ok: false, status: 500, json: async () => { throw new Error('no body') } } as unknown as Response)
    await expect(fetchUsers()).rejects.toMatchObject({
      name: 'AdminUsersError',
      status: 500,
      type: 'unknown',
    })
  })
})

describe('createUser', () => {
  const input = { user_name: 'bob', display_name: 'Bob', password: 'a-very-long-password', role: 'user' as const }

  it('returns the created user (201) on success', async () => {
    stubFetch(jsonResponse({ ...USER, user_name: 'bob' }, 201))
    await expect(createUser(input)).resolves.toEqual({ ...USER, user_name: 'bob' })
  })

  it('POSTs JSON to /api/v1/admin/users/', async () => {
    const fetchMock = stubFetch(jsonResponse(USER, 201))
    await createUser(input)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/admin/users/',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      }),
    )
  })

  it('throws with type=validation-failed and the verbatim detail on 422', async () => {
    stubFetch(problem('validation-failed', 'Password must be at least 12 characters.', 422))
    const error = await createUser(input).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(AdminUsersError)
    expect(error).toMatchObject({
      status: 422,
      type: 'validation-failed',
      detail: 'Password must be at least 12 characters.',
      message: 'Password must be at least 12 characters.',
    })
  })

  it('throws with type=username-already-exists on 409 duplicate', async () => {
    stubFetch(problem('username-already-exists', "A user named 'bob' already exists.", 409))
    await expect(createUser(input)).rejects.toMatchObject({
      status: 409,
      type: 'username-already-exists',
      detail: "A user named 'bob' already exists.",
    })
  })

  it('throws with type=local-user-creation-unavailable on 409 (server in oidc mode)', async () => {
    stubFetch(
      problem(
        'local-user-creation-unavailable',
        'Local accounts cannot be created while SSO (oidc mode) is enabled — provision users via SCIM/your identity provider, or switch to local mode to manage local accounts.',
        409,
      ),
    )
    await expect(createUser(input)).rejects.toMatchObject({
      status: 409,
      type: 'local-user-creation-unavailable',
    })
  })
})

describe('patchUser', () => {
  it('returns the updated user on success', async () => {
    stubFetch(jsonResponse({ ...USER, role: 'user' }))
    await expect(patchUser('user-1', { role: 'user' })).resolves.toEqual({ ...USER, role: 'user' })
  })

  it('PATCHes JSON to /api/v1/admin/users/<id>', async () => {
    const fetchMock = stubFetch(jsonResponse(USER))
    await patchUser('user-1', { active: false })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/admin/users/user-1',
      expect.objectContaining({
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: false }),
      }),
    )
  })

  it('URL-encodes the user id', async () => {
    const fetchMock = stubFetch(jsonResponse(USER))
    await patchUser('user/weird id', { active: false })
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/v1/admin/users/${encodeURIComponent('user/weird id')}`,
      expect.anything(),
    )
  })

  it('throws with type=user-not-found on 404', async () => {
    stubFetch(problem('user-not-found', "No user with id 'missing' exists.", 404))
    await expect(patchUser('missing', { role: 'admin' })).rejects.toMatchObject({
      status: 404,
      type: 'user-not-found',
    })
  })

  it('throws with type=validation-failed on 422 (empty body / bad role / non-boolean active)', async () => {
    stubFetch(problem('validation-failed', 'At least one of role/active must be supplied.', 422))
    await expect(patchUser('user-1', {})).rejects.toMatchObject({
      status: 422,
      type: 'validation-failed',
    })
  })

  it('throws with type=last-admin on 409 (demote/deactivate the last active admin)', async () => {
    stubFetch(
      problem(
        'last-admin',
        'This is the last active admin. Promote another user to admin before demoting or deactivating this account.',
        409,
      ),
    )
    await expect(patchUser('user-1', { active: false })).rejects.toMatchObject({
      status: 409,
      type: 'last-admin',
      detail: 'This is the last active admin. Promote another user to admin before demoting or deactivating this account.',
    })
  })

  it('throws with type=scim-owned-user on 409 (SCIM-linked record, oidc mode)', async () => {
    stubFetch(
      problem(
        'scim-owned-user',
        'This user is provisioned and managed by SCIM while SSO is enabled. Changes must be made in the identity provider; unassign the account there or disable SCIM to edit it here.',
        409,
      ),
    )
    await expect(patchUser('user-2', { role: 'user' })).rejects.toMatchObject({
      status: 409,
      type: 'scim-owned-user',
    })
  })
})

describe('resetPassword', () => {
  it('returns the updated user on success (no password field)', async () => {
    stubFetch(jsonResponse(USER))
    await expect(resetPassword('user-1', 'a-very-long-password')).resolves.toEqual(USER)
  })

  it('POSTs JSON to /api/v1/admin/users/<id>/reset-password', async () => {
    const fetchMock = stubFetch(jsonResponse(USER))
    await resetPassword('user-1', 'a-very-long-password')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/admin/users/user-1/reset-password',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: 'a-very-long-password' }),
      }),
    )
  })

  it('throws with type=user-not-found on 404', async () => {
    stubFetch(problem('user-not-found', "No user with id 'missing' exists.", 404))
    await expect(resetPassword('missing', 'a-very-long-password')).rejects.toMatchObject({
      status: 404,
      type: 'user-not-found',
    })
  })

  it('throws with type=validation-failed on 422 (short password)', async () => {
    stubFetch(problem('validation-failed', 'Password must be at least 12 characters.', 422))
    await expect(resetPassword('user-1', 'short')).rejects.toMatchObject({
      status: 422,
      type: 'validation-failed',
    })
  })

  it('throws with type=scim-owned-user on 409', async () => {
    stubFetch(problem('scim-owned-user', 'This user is provisioned and managed by SCIM...', 409))
    await expect(resetPassword('user-2', 'a-very-long-password')).rejects.toMatchObject({
      status: 409,
      type: 'scim-owned-user',
    })
  })
})
