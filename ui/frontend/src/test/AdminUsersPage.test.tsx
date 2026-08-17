/**
 * AdminUsersPage.test.tsx (Task 8.7 — ADR 0002 §6, FR60).
 *
 * Mirrors `SourcesPage.test.tsx`'s state-coverage structure (loading /
 * populated / empty / error / never-blank), plus this page's own
 * mutation-flow ACs (create, role-change, deactivate/reactivate incl. the
 * explicit `409 last-admin` inline-error AC, reset-password, and the
 * SCIM-owned `409` inline-error case).
 *
 * Mocks `src/api/admin-users.ts` directly via `vi.mock('../api/admin-users')`
 * (the client module now owns response parsing / the typed `AdminUsersError`
 * — the real `AdminUsersError`/`AdminUserRecord` types are kept via
 * `importOriginal`, only the network functions themselves are replaced),
 * per the task instructions — NOT `global.fetch`. `useCurrentUser` is
 * similarly mocked (via `../lib`) so each test can control the caller's
 * `auth_mode`/role without hitting `/api/v1/auth/me`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AdminUsersPage } from '../routes/AdminUsersPage'
import { PermissionDeniedError } from '../api/http'
import {
  AdminUsersError,
  createUser,
  fetchUsers,
  patchUser,
  resetPassword,
  type AdminUserRecord,
} from '../api/admin-users'
import { useCurrentUser } from '../lib'

vi.mock('../api/admin-users', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/admin-users')>()
  return {
    ...actual,
    fetchUsers: vi.fn(),
    createUser: vi.fn(),
    patchUser: vi.fn(),
    resetPassword: vi.fn(),
  }
})

vi.mock('../lib', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib')>()
  return { ...actual, useCurrentUser: vi.fn() }
})

const mockFetchUsers = vi.mocked(fetchUsers)
const mockCreateUser = vi.mocked(createUser)
const mockPatchUser = vi.mocked(patchUser)
const mockResetPassword = vi.mocked(resetPassword)
const mockUseCurrentUser = vi.mocked(useCurrentUser)

function admin(overrides: Partial<AdminUserRecord> = {}): AdminUserRecord {
  return {
    id: 'user-1',
    user_name: 'alice@corp.com',
    display_name: 'Alice Alpha',
    role: 'admin',
    origin: 'local',
    active: true,
    last_login_at: '2026-08-09T12:00:00+00:00',
    ...overrides,
  }
}

function pending<T>(): { promise: Promise<T>; resolve: (v: T) => void; reject: (e: unknown) => void } {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  mockUseCurrentUser.mockReturnValue({
    loading: false,
    authenticated: true,
    auth_mode: 'local',
    user: { user_name: 'me@corp.com', display_name: 'Me', role: 'admin' },
  })
})

afterEach(() => {
  vi.resetAllMocks()
})

describe('AdminUsersPage — loading', () => {
  it('shows a loading skeleton (not a blank frame) while the initial fetch is in flight', async () => {
    const gate = pending<AdminUserRecord[]>()
    mockFetchUsers.mockReturnValue(gate.promise)
    render(<AdminUsersPage />)

    expect(screen.getByRole('status', { name: 'Loading users' })).toBeInTheDocument()

    gate.resolve([])
    await waitFor(() => expect(screen.queryByRole('status', { name: 'Loading users' })).not.toBeInTheDocument())
  })
})

describe('AdminUsersPage — populated table', () => {
  it('renders a row per user with username/role/origin/status/last-login', async () => {
    mockFetchUsers.mockResolvedValue([
      admin(),
      admin({ id: 'user-2', user_name: 'bob@corp.com', display_name: 'Bob Beta', role: 'user', origin: 'scim', active: false, last_login_at: null }),
    ])
    render(<AdminUsersPage />)

    await screen.findByText('Alice Alpha')
    expect(screen.getByText('Bob Beta')).toBeInTheDocument()
    expect(screen.getByText('SCIM')).toBeInTheDocument()
    expect(screen.getByText('Inactive')).toBeInTheDocument()
    expect(screen.getByText('Never')).toBeInTheDocument()
  })
})

describe('AdminUsersPage — empty state (never blank)', () => {
  it('renders an explanatory empty state when there are no users', async () => {
    mockFetchUsers.mockResolvedValue([])
    render(<AdminUsersPage />)

    expect(await screen.findByText('No users yet')).toBeInTheDocument()
  })
})

describe('AdminUsersPage — fetch-error state (never blank)', () => {
  it('renders an explanatory error block when the initial fetch fails', async () => {
    mockFetchUsers.mockRejectedValue(new Error('Failed to fetch users (HTTP 500)'))
    render(<AdminUsersPage />)

    expect(await screen.findByText('Unable to fetch users')).toBeInTheDocument()
    expect(screen.getByText('Failed to fetch users (HTTP 500)')).toBeInTheDocument()
  })
})

describe('AdminUsersPage — 403 in-shell (non-admin caller)', () => {
  it('renders an in-shell "Admin access required" message, not a redirect or blank page', async () => {
    mockFetchUsers.mockRejectedValue(new PermissionDeniedError('You do not have permission to access this resource.'))
    render(<AdminUsersPage />)

    expect(await screen.findByText('Admin access required')).toBeInTheDocument()
    expect(
      screen.getByText('Your account does not have permission to manage users. Contact an administrator if you believe this is a mistake.'),
    ).toBeInTheDocument()
    // No retry action, no table.
    expect(screen.queryByRole('button', { name: 'Create user' })).not.toBeInTheDocument()
  })
})

describe('AdminUsersPage — create user flow', () => {
  async function openCreateDialog(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole('button', { name: 'Create user' }))
  }

  it('happy path: fills the form, submits, the new row appears, dialog closes', async () => {
    const user = userEvent.setup()
    mockFetchUsers.mockResolvedValue([admin()])
    const created = admin({ id: 'user-2', user_name: 'zoe@corp.com', display_name: 'Zoe Zeta', role: 'user' })
    mockCreateUser.mockResolvedValue(created)
    render(<AdminUsersPage />)
    await screen.findByText('Alice Alpha')

    await openCreateDialog(user)
    await user.type(screen.getByLabelText('Username'), 'zoe@corp.com')
    await user.type(screen.getByLabelText('Password'), 'a-very-long-password')
    await user.click(screen.getByRole('button', { name: 'Create user' }))

    await waitFor(() => expect(mockCreateUser).toHaveBeenCalledExactlyOnceWith({
      user_name: 'zoe@corp.com',
      display_name: '',
      password: 'a-very-long-password',
      role: 'user',
    }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(screen.getByText('Zoe Zeta')).toBeInTheDocument()
  })

  it('local-user-creation-unavailable: renders the server error inline, dialog stays open', async () => {
    const user = userEvent.setup()
    mockFetchUsers.mockResolvedValue([admin()])
    mockCreateUser.mockRejectedValue(
      new AdminUsersError(
        'Local accounts cannot be created while SSO (oidc mode) is enabled — provision users via SCIM/your identity provider, or switch to local mode to manage local accounts.',
        409,
        'local-user-creation-unavailable',
      ),
    )
    render(<AdminUsersPage />)
    await screen.findByText('Alice Alpha')

    await openCreateDialog(user)
    await user.type(screen.getByLabelText('Username'), 'zoe@corp.com')
    await user.type(screen.getByLabelText('Password'), 'a-very-long-password')
    await user.click(screen.getByRole('button', { name: 'Create user' }))

    expect(await screen.findByText(/Local accounts cannot be created while SSO/)).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('username-already-exists: renders the server error inline, dialog stays open', async () => {
    const user = userEvent.setup()
    mockFetchUsers.mockResolvedValue([admin()])
    mockCreateUser.mockRejectedValue(new AdminUsersError("A user named 'zoe' already exists.", 409, 'username-already-exists'))
    render(<AdminUsersPage />)
    await screen.findByText('Alice Alpha')

    await openCreateDialog(user)
    await user.type(screen.getByLabelText('Username'), 'zoe')
    await user.type(screen.getByLabelText('Password'), 'a-very-long-password')
    await user.click(screen.getByRole('button', { name: 'Create user' }))

    expect(await screen.findByText("A user named 'zoe' already exists.")).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('validation-failed (short password rejected server-side): renders the server error inline', async () => {
    // Client-side validation already blocks <12 chars locally, so to reach
    // the server-error render path we simulate the server disagreeing
    // (e.g. a future rule) by rejecting a client-valid submission.
    const user = userEvent.setup()
    mockFetchUsers.mockResolvedValue([admin()])
    mockCreateUser.mockRejectedValue(new AdminUsersError('Password must be at least 12 characters.', 422, 'validation-failed'))
    render(<AdminUsersPage />)
    await screen.findByText('Alice Alpha')

    await openCreateDialog(user)
    await user.type(screen.getByLabelText('Username'), 'zoe')
    await user.type(screen.getByLabelText('Password'), 'a-very-long-password')
    await user.click(screen.getByRole('button', { name: 'Create user' }))

    expect(await screen.findByText('Password must be at least 12 characters.')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})

describe('AdminUsersPage — role-change flow', () => {
  it('changes a row role and reflects the updated record from the server', async () => {
    const user = userEvent.setup()
    mockFetchUsers.mockResolvedValue([admin({ role: 'user' })])
    mockPatchUser.mockResolvedValue(admin({ role: 'admin' }))
    render(<AdminUsersPage />)
    await screen.findByText('Alice Alpha')

    const row = screen.getByTestId('user-row-user-1')
    await user.selectOptions(within(row).getByLabelText('Role'), 'admin')

    await waitFor(() => expect(mockPatchUser).toHaveBeenCalledExactlyOnceWith('user-1', { role: 'admin' }))
    await waitFor(() => expect((within(row).getByLabelText('Role') as HTMLSelectElement).value).toBe('admin'))
  })

  it('a last-admin 409 from a role-change attempt renders inline in the row and reverts the select', async () => {
    const user = userEvent.setup()
    mockFetchUsers.mockResolvedValue([admin({ role: 'admin' })])
    mockPatchUser.mockRejectedValue(
      new AdminUsersError(
        'This is the last active admin. Promote another user to admin before demoting or deactivating this account.',
        409,
        'last-admin',
      ),
    )
    render(<AdminUsersPage />)
    await screen.findByText('Alice Alpha')

    const row = screen.getByTestId('user-row-user-1')
    await user.selectOptions(within(row).getByLabelText('Role'), 'user')

    // The inline row-error banner renders as a sibling <tr>, not nested inside
    // the row's own <tr data-testid="user-row-...">  — scoped to the page.
    expect(await screen.findByRole('alert')).toHaveTextContent('This is the last active admin')
    // The select reverts to the server-confirmed value since local state was never optimistically mutated.
    expect((within(row).getByLabelText('Role') as HTMLSelectElement).value).toBe('admin')
  })
})

describe('AdminUsersPage — deactivate/reactivate flow', () => {
  it('deactivating opens a confirm dialog; confirming applies the change', async () => {
    const user = userEvent.setup()
    mockFetchUsers.mockResolvedValue([admin({ active: true })])
    mockPatchUser.mockResolvedValue(admin({ active: false }))
    render(<AdminUsersPage />)
    await screen.findByText('Alice Alpha')

    await user.click(screen.getByRole('button', { name: 'Deactivate' }))
    expect(screen.getByRole('dialog')).toHaveTextContent('Deactivate alice@corp.com?')

    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Deactivate' }))

    await waitFor(() => expect(mockPatchUser).toHaveBeenCalledExactlyOnceWith('user-1', { active: false }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(screen.getByText('Inactive')).toBeInTheDocument()
  })

  it('AC: self-demotion/deactivation blocked by a 409 last-admin renders inline in the confirm dialog, dialog stays open', async () => {
    const user = userEvent.setup()
    mockFetchUsers.mockResolvedValue([admin({ active: true })])
    mockPatchUser.mockRejectedValue(
      new AdminUsersError(
        'This is the last active admin. Promote another user to admin before demoting or deactivating this account.',
        409,
        'last-admin',
      ),
    )
    render(<AdminUsersPage />)
    await screen.findByText('Alice Alpha')

    await user.click(screen.getByRole('button', { name: 'Deactivate' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Deactivate' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This is the last active admin. Promote another user to admin before demoting or deactivating this account.',
    )
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    // The account was NOT locally marked inactive — the mutation was refused.
    expect(screen.queryByText('Inactive')).not.toBeInTheDocument()
  })

  it('reactivating an inactive user applies the change', async () => {
    const user = userEvent.setup()
    mockFetchUsers.mockResolvedValue([admin({ active: false })])
    mockPatchUser.mockResolvedValue(admin({ active: true }))
    render(<AdminUsersPage />)
    await screen.findByText('Alice Alpha')

    await user.click(screen.getByRole('button', { name: 'Reactivate' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Reactivate' }))

    await waitFor(() => expect(mockPatchUser).toHaveBeenCalledExactlyOnceWith('user-1', { active: true }))
    await waitFor(() => expect(screen.getByText('Active')).toBeInTheDocument())
  })
})

describe('AdminUsersPage — reset-password flow', () => {
  it('opens the reset-password dialog for the target user, submits matching passwords, closes on success', async () => {
    const user = userEvent.setup()
    mockFetchUsers.mockResolvedValue([admin()])
    mockResetPassword.mockResolvedValue(admin())
    render(<AdminUsersPage />)
    await screen.findByText('Alice Alpha')

    await user.click(screen.getByRole('button', { name: 'Reset password' }))
    expect(screen.getByText('Reset password for alice@corp.com')).toBeInTheDocument()

    await user.type(screen.getByLabelText('New password'), 'a-very-long-password')
    await user.type(screen.getByLabelText('Confirm new password'), 'a-very-long-password')
    await user.click(screen.getByRole('button', { name: 'Reset password' }))

    await waitFor(() => expect(mockResetPassword).toHaveBeenCalledExactlyOnceWith('user-1', 'a-very-long-password'))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })
})

describe('AdminUsersPage — SCIM-owned 409 inline error', () => {
  it('a scim-owned-user 409 on reset-password renders inline in the dialog, dialog stays open', async () => {
    const user = userEvent.setup()
    mockFetchUsers.mockResolvedValue([admin({ id: 'user-2', user_name: 'bob@corp.com', origin: 'local' })])
    mockResetPassword.mockRejectedValue(
      new AdminUsersError(
        'This user is provisioned and managed by SCIM while SSO is enabled. Changes must be made in the identity provider; unassign the account there or disable SCIM to edit it here.',
        409,
        'scim-owned-user',
      ),
    )
    render(<AdminUsersPage />)
    await screen.findByText('bob@corp.com')

    await user.click(screen.getByRole('button', { name: 'Reset password' }))
    await user.type(screen.getByLabelText('New password'), 'a-very-long-password')
    await user.type(screen.getByLabelText('Confirm new password'), 'a-very-long-password')
    await user.click(screen.getByRole('button', { name: 'Reset password' }))

    expect(await screen.findByText(/provisioned and managed by SCIM/)).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('a SCIM-owned row is best-effort disabled (role select + actions) while the server is in oidc mode', async () => {
    mockUseCurrentUser.mockReturnValue({
      loading: false,
      authenticated: true,
      auth_mode: 'oidc',
      user: { user_name: 'me@corp.com', display_name: 'Me', role: 'admin' },
    })
    mockFetchUsers.mockResolvedValue([admin({ origin: 'scim' })])
    render(<AdminUsersPage />)
    await screen.findByText('Alice Alpha')

    const row = screen.getByTestId('user-row-user-1')
    expect(within(row).getByLabelText('Role')).toBeDisabled()
    expect(within(row).getByRole('button', { name: 'Deactivate' })).toBeDisabled()
  })
})
