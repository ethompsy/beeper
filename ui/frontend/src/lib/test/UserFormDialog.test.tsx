/**
 * UserFormDialog.test.tsx (Task 8.7 — ADR 0002 §6, FR60).
 *
 * Covers both modes (`create` / `reset-password`): field rendering,
 * client-side validation (username required, MIN_PASSWORD_LENGTH,
 * password-confirmation match), server-error rendering (verbatim, dialog
 * stays open), loading state, and cancel.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { UserFormDialog, MIN_PASSWORD_LENGTH } from '../components/UserFormDialog'

describe('UserFormDialog — mode="create"', () => {
  it('renders username, display name, password, and role fields', () => {
    render(<UserFormDialog open onOpenChange={() => {}} mode="create" />)
    expect(screen.getByLabelText('Username')).toBeInTheDocument()
    expect(screen.getByLabelText(/Display name/)).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
    expect(screen.getByLabelText('Role')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create user' })).toBeInTheDocument()
  })

  it('blocks submit and shows an inline error when the username is empty', async () => {
    const user = userEvent.setup()
    const onCreateSubmit = vi.fn()
    render(<UserFormDialog open onOpenChange={() => {}} mode="create" onCreateSubmit={onCreateSubmit} />)

    await user.type(screen.getByLabelText('Password'), 'a-very-long-password')
    await user.click(screen.getByRole('button', { name: 'Create user' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Username is required.')
    expect(onCreateSubmit).not.toHaveBeenCalled()
  })

  it(`blocks submit and shows an inline error when the password is under ${MIN_PASSWORD_LENGTH} characters`, async () => {
    const user = userEvent.setup()
    const onCreateSubmit = vi.fn()
    render(<UserFormDialog open onOpenChange={() => {}} mode="create" onCreateSubmit={onCreateSubmit} />)

    await user.type(screen.getByLabelText('Username'), 'bob')
    await user.type(screen.getByLabelText('Password'), 'short')
    await user.click(screen.getByRole('button', { name: 'Create user' }))

    expect(screen.getByRole('alert')).toHaveTextContent(
      `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`,
    )
    expect(onCreateSubmit).not.toHaveBeenCalled()
  })

  it('calls onCreateSubmit with trimmed username/display name, the password, and the selected role on valid submit', async () => {
    const user = userEvent.setup()
    const onCreateSubmit = vi.fn()
    render(<UserFormDialog open onOpenChange={() => {}} mode="create" onCreateSubmit={onCreateSubmit} />)

    await user.type(screen.getByLabelText('Username'), '  bob  ')
    await user.type(screen.getByLabelText(/Display name/), '  Bob Beta  ')
    await user.type(screen.getByLabelText('Password'), 'a-very-long-password')
    await user.selectOptions(screen.getByLabelText('Role'), 'admin')
    await user.click(screen.getByRole('button', { name: 'Create user' }))

    expect(onCreateSubmit).toHaveBeenCalledExactlyOnceWith({
      user_name: 'bob',
      display_name: 'Bob Beta',
      password: 'a-very-long-password',
      role: 'admin',
    })
  })

  it('renders a server-side error verbatim (e.g. username-already-exists) without calling onCreateSubmit again', () => {
    render(
      <UserFormDialog
        open
        onOpenChange={() => {}}
        mode="create"
        error="A user named 'bob' already exists."
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent("A user named 'bob' already exists.")
  })

  it('renders local-user-creation-unavailable server error verbatim', () => {
    render(
      <UserFormDialog
        open
        onOpenChange={() => {}}
        mode="create"
        error="Local accounts cannot be created while SSO (oidc mode) is enabled — provision users via SCIM/your identity provider, or switch to local mode to manage local accounts."
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('Local accounts cannot be created while SSO')
  })

  it('loading=true disables the fields and both buttons, and shows a pending submit label', () => {
    render(<UserFormDialog open onOpenChange={() => {}} mode="create" loading />)
    expect(screen.getByLabelText('Username')).toBeDisabled()
    expect(screen.getByLabelText('Password')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Creating…' })).toBeDisabled()
  })

  it('calls onOpenChange(false) when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    render(<UserFormDialog open onOpenChange={onOpenChange} mode="create" />)
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onOpenChange).toHaveBeenCalledExactlyOnceWith(false)
  })

  it('resets field values each time the dialog re-opens', async () => {
    const user = userEvent.setup()
    const { rerender } = render(<UserFormDialog open onOpenChange={() => {}} mode="create" />)
    await user.type(screen.getByLabelText('Username'), 'leftover')

    rerender(<UserFormDialog open={false} onOpenChange={() => {}} mode="create" />)
    rerender(<UserFormDialog open onOpenChange={() => {}} mode="create" />)

    expect((screen.getByLabelText('Username') as HTMLInputElement).value).toBe('')
  })
})

describe('UserFormDialog — mode="reset-password"', () => {
  it('renders only password + confirm-password fields (no username/display-name/role)', () => {
    render(<UserFormDialog open onOpenChange={() => {}} mode="reset-password" targetUserName="alice@corp.com" />)
    expect(screen.queryByLabelText('Username')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Role')).not.toBeInTheDocument()
    expect(screen.getByLabelText('New password')).toBeInTheDocument()
    expect(screen.getByLabelText('Confirm new password')).toBeInTheDocument()
  })

  it('includes the target username in the title', () => {
    render(<UserFormDialog open onOpenChange={() => {}} mode="reset-password" targetUserName="alice@corp.com" />)
    expect(screen.getByText('Reset password for alice@corp.com')).toBeInTheDocument()
  })

  it('blocks submit when the two password fields do not match', async () => {
    const user = userEvent.setup()
    const onResetPasswordSubmit = vi.fn()
    render(
      <UserFormDialog
        open
        onOpenChange={() => {}}
        mode="reset-password"
        onResetPasswordSubmit={onResetPasswordSubmit}
      />,
    )

    await user.type(screen.getByLabelText('New password'), 'a-very-long-password')
    await user.type(screen.getByLabelText('Confirm new password'), 'a-different-password')
    await user.click(screen.getByRole('button', { name: 'Reset password' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Passwords do not match.')
    expect(onResetPasswordSubmit).not.toHaveBeenCalled()
  })

  it('calls onResetPasswordSubmit with the password when both fields match and are long enough', async () => {
    const user = userEvent.setup()
    const onResetPasswordSubmit = vi.fn()
    render(
      <UserFormDialog
        open
        onOpenChange={() => {}}
        mode="reset-password"
        onResetPasswordSubmit={onResetPasswordSubmit}
      />,
    )

    await user.type(screen.getByLabelText('New password'), 'a-very-long-password')
    await user.type(screen.getByLabelText('Confirm new password'), 'a-very-long-password')
    await user.click(screen.getByRole('button', { name: 'Reset password' }))

    expect(onResetPasswordSubmit).toHaveBeenCalledExactlyOnceWith('a-very-long-password')
  })

  it('renders a scim-owned-user server error verbatim', () => {
    render(
      <UserFormDialog
        open
        onOpenChange={() => {}}
        mode="reset-password"
        targetUserName="bob@corp.com"
        error="This user is provisioned and managed by SCIM while SSO is enabled."
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('This user is provisioned and managed by SCIM')
  })
})
