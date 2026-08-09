/**
 * LoginForm.test.tsx (Task 8.6 — ADR 0002 §6, FR59).
 *
 * AC [T]: "/app/login renders (form, error, loading states — vitest/RTL)".
 * This file covers the LIBRARY PRIMITIVE's own contract (controlled
 * inputs, submit callback, loading/error rendering); `LoginPage.test.tsx`
 * covers the routed page's network/redirect behavior on top of it.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LoginForm } from '../components/LoginForm'

describe('LoginForm', () => {
  it('renders username and password fields plus a Sign in button', () => {
    render(<LoginForm onSubmit={() => {}} />)
    expect(screen.getByLabelText('Username')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('password field masks input (type="password")', () => {
    render(<LoginForm onSubmit={() => {}} />)
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password')
  })

  it('submit button is disabled until both fields are non-empty', async () => {
    const user = userEvent.setup()
    render(<LoginForm onSubmit={() => {}} />)
    const button = screen.getByRole('button', { name: 'Sign in' })
    expect(button).toBeDisabled()

    await user.type(screen.getByLabelText('Username'), 'alice')
    expect(button).toBeDisabled()

    await user.type(screen.getByLabelText('Password'), 'hunter2')
    expect(button).toBeEnabled()
  })

  it('calls onSubmit with the trimmed username and raw password on submit', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<LoginForm onSubmit={onSubmit} />)

    await user.type(screen.getByLabelText('Username'), '  alice  ')
    await user.type(screen.getByLabelText('Password'), 'hunter2')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({
      username: 'alice',
      password: 'hunter2',
    })
  })

  it('calls onSubmit on Enter key (native form submit)', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<LoginForm onSubmit={onSubmit} />)

    await user.type(screen.getByLabelText('Username'), 'bob')
    await user.type(screen.getByLabelText('Password'), 'secret123{Enter}')

    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({ username: 'bob', password: 'secret123' })
  })

  it('loading=true disables both fields and the button, and shows a busy label', () => {
    render(<LoginForm onSubmit={() => {}} loading />)
    expect(screen.getByLabelText('Username')).toBeDisabled()
    expect(screen.getByLabelText('Password')).toBeDisabled()
    expect(screen.getByRole('button')).toBeDisabled()
    expect(screen.getByRole('button')).toHaveTextContent('Signing in…')
  })

  it('loading=true does not call onSubmit even if the form is somehow submitted', async () => {
    const onSubmit = vi.fn()
    const { container } = render(<LoginForm onSubmit={onSubmit} loading />)
    const form = container.querySelector('form')
    expect(form).not.toBeNull()
    form?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('renders no error text when error is null/omitted', () => {
    render(<LoginForm onSubmit={() => {}} />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('renders the given error message verbatim, in a role="alert" element', () => {
    render(<LoginForm onSubmit={() => {}} error="Invalid username or password." />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Invalid username or password.')
  })

  it('does not distinguish error causes — any string is rendered as-is (FR59 uniform message is a page-level contract)', () => {
    render(<LoginForm onSubmit={() => {}} error="Something went wrong. Please try again." />)
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong. Please try again.')
  })
})
