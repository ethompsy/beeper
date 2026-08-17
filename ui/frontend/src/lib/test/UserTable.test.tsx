/**
 * UserTable.test.tsx (Task 8.7 — ADR 0002 §6, FR60).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { UserTable, type UserTableRow } from '../components/UserTable'

function makeUser(overrides: Partial<UserTableRow> = {}): UserTableRow {
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

const noop = () => {}

describe('UserTable — rendering', () => {
  it('renders a row per user with username, display name, origin badge, and last login', () => {
    render(
      <UserTable
        users={[makeUser()]}
        onRoleChange={noop}
        onDeactivateRequest={noop}
        onReactivateRequest={noop}
        onResetPasswordRequest={noop}
      />,
    )
    const row = screen.getByTestId('user-row-user-1')
    expect(within(row).getByText('Alice Alpha')).toBeInTheDocument()
    expect(within(row).getByText('alice@corp.com')).toBeInTheDocument()
    expect(within(row).getByText('Local')).toBeInTheDocument()
    expect(within(row).getByText('2026-08-09T12:00:00+00:00')).toBeInTheDocument()
  })

  it('falls back to "Never" when last_login_at is null', () => {
    render(
      <UserTable
        users={[makeUser({ last_login_at: null })]}
        onRoleChange={noop}
        onDeactivateRequest={noop}
        onReactivateRequest={noop}
        onResetPasswordRequest={noop}
      />,
    )
    expect(within(screen.getByTestId('user-row-user-1')).getByText('Never')).toBeInTheDocument()
  })

  it('renders an Active/Inactive status badge based on the active flag', () => {
    render(
      <UserTable
        users={[makeUser({ active: true }), makeUser({ id: 'user-2', active: false })]}
        onRoleChange={noop}
        onDeactivateRequest={noop}
        onReactivateRequest={noop}
        onResetPasswordRequest={noop}
      />,
    )
    expect(within(screen.getByTestId('user-row-user-1')).getByText('Active')).toBeInTheDocument()
    expect(within(screen.getByTestId('user-row-user-2')).getByText('Inactive')).toBeInTheDocument()
  })

  it('shows "Deactivate" for an active user and "Reactivate" for an inactive user', () => {
    render(
      <UserTable
        users={[makeUser({ active: true }), makeUser({ id: 'user-2', active: false })]}
        onRoleChange={noop}
        onDeactivateRequest={noop}
        onReactivateRequest={noop}
        onResetPasswordRequest={noop}
      />,
    )
    expect(within(screen.getByTestId('user-row-user-1')).getByRole('button', { name: 'Deactivate' })).toBeInTheDocument()
    expect(within(screen.getByTestId('user-row-user-2')).getByRole('button', { name: 'Reactivate' })).toBeInTheDocument()
  })

  it('shows a "Reset password" action only for local-origin rows (SCIM users have no password)', () => {
    render(
      <UserTable
        users={[makeUser({ origin: 'local' }), makeUser({ id: 'user-2', origin: 'scim' })]}
        onRoleChange={noop}
        onDeactivateRequest={noop}
        onReactivateRequest={noop}
        onResetPasswordRequest={noop}
      />,
    )
    expect(within(screen.getByTestId('user-row-user-1')).getByRole('button', { name: 'Reset password' })).toBeInTheDocument()
    expect(within(screen.getByTestId('user-row-user-2')).queryByRole('button', { name: 'Reset password' })).not.toBeInTheDocument()
  })
})

describe('UserTable — role change', () => {
  it('calls onRoleChange with the user id and new role when the row role select changes', async () => {
    const user = userEvent.setup()
    const onRoleChange = vi.fn()
    render(
      <UserTable
        users={[makeUser({ role: 'user' })]}
        onRoleChange={onRoleChange}
        onDeactivateRequest={noop}
        onReactivateRequest={noop}
        onResetPasswordRequest={noop}
      />,
    )
    await user.selectOptions(within(screen.getByTestId('user-row-user-1')).getByLabelText('Role'), 'admin')
    expect(onRoleChange).toHaveBeenCalledExactlyOnceWith('user-1', 'admin')
  })
})

describe('UserTable — row actions', () => {
  it('calls onDeactivateRequest with the user id when Deactivate is clicked', async () => {
    const user = userEvent.setup()
    const onDeactivateRequest = vi.fn()
    render(
      <UserTable
        users={[makeUser({ active: true })]}
        onRoleChange={noop}
        onDeactivateRequest={onDeactivateRequest}
        onReactivateRequest={noop}
        onResetPasswordRequest={noop}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Deactivate' }))
    expect(onDeactivateRequest).toHaveBeenCalledExactlyOnceWith('user-1')
  })

  it('calls onReactivateRequest with the user id when Reactivate is clicked', async () => {
    const user = userEvent.setup()
    const onReactivateRequest = vi.fn()
    render(
      <UserTable
        users={[makeUser({ active: false })]}
        onRoleChange={noop}
        onDeactivateRequest={noop}
        onReactivateRequest={onReactivateRequest}
        onResetPasswordRequest={noop}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Reactivate' }))
    expect(onReactivateRequest).toHaveBeenCalledExactlyOnceWith('user-1')
  })

  it('calls onResetPasswordRequest with the user id when Reset password is clicked', async () => {
    const user = userEvent.setup()
    const onResetPasswordRequest = vi.fn()
    render(
      <UserTable
        users={[makeUser({ origin: 'local' })]}
        onRoleChange={noop}
        onDeactivateRequest={noop}
        onReactivateRequest={noop}
        onResetPasswordRequest={onResetPasswordRequest}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Reset password' }))
    expect(onResetPasswordRequest).toHaveBeenCalledExactlyOnceWith('user-1')
  })
})

describe('UserTable — rowState (pending / error / readOnly)', () => {
  it('disables the role select and action buttons for a pending row', () => {
    render(
      <UserTable
        users={[makeUser({ active: true, origin: 'local' })]}
        onRoleChange={noop}
        onDeactivateRequest={noop}
        onReactivateRequest={noop}
        onResetPasswordRequest={noop}
        rowState={{ 'user-1': { pending: true } }}
      />,
    )
    const row = screen.getByTestId('user-row-user-1')
    expect(within(row).getByLabelText('Role')).toBeDisabled()
    expect(within(row).getByRole('button', { name: 'Deactivate' })).toBeDisabled()
    expect(within(row).getByRole('button', { name: 'Reset password' })).toBeDisabled()
  })

  it('disables the role select and action buttons for a readOnly row (best-effort SCIM-owned UX)', () => {
    render(
      <UserTable
        users={[makeUser({ origin: 'scim' })]}
        onRoleChange={noop}
        onDeactivateRequest={noop}
        onReactivateRequest={noop}
        onResetPasswordRequest={noop}
        rowState={{ 'user-1': { readOnly: true } }}
      />,
    )
    expect(screen.getByLabelText('Role')).toBeDisabled()
  })

  it('renders an inline row error (e.g. a last-admin 409 from a role-change attempt), verbatim, as role="alert"', () => {
    render(
      <UserTable
        users={[makeUser()]}
        onRoleChange={noop}
        onDeactivateRequest={noop}
        onReactivateRequest={noop}
        onResetPasswordRequest={noop}
        rowState={{
          'user-1': {
            error:
              'This is the last active admin. Promote another user to admin before demoting or deactivating this account.',
          },
        }}
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('This is the last active admin')
  })

  it('renders no row error when rowState is omitted', () => {
    render(
      <UserTable
        users={[makeUser()]}
        onRoleChange={noop}
        onDeactivateRequest={noop}
        onReactivateRequest={noop}
        onResetPasswordRequest={noop}
      />,
    )
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
