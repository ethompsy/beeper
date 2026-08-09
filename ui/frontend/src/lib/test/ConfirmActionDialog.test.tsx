/**
 * ConfirmActionDialog.test.tsx (Task 8.7 — ADR 0002 §6, FR60).
 *
 * Coverage: renders title/description, confirm/cancel wiring, loading
 * disables both buttons, the inline error slot (the load-bearing AC —
 * "self-demotion blocked by last-admin 409 rendered inline"), Escape
 * closes (Radix built-in), and focus moves into the dialog on open
 * (Radix focus trap).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConfirmActionDialog } from '../components/ConfirmActionDialog'

describe('ConfirmActionDialog', () => {
  it('does not render when open=false', () => {
    render(
      <ConfirmActionDialog open={false} onOpenChange={() => {}} title="Deactivate user?" onConfirm={() => {}} />,
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders title and description as an accessible dialog when open', () => {
    render(
      <ConfirmActionDialog
        open
        onOpenChange={() => {}}
        title="Deactivate alice?"
        description="They will lose access immediately."
        onConfirm={() => {}}
      />,
    )
    // `role="dialog"` (asserted via getByRole below) plus the focus-trap
    // test further down are this suite's proof of modality — this
    // installed Radix version does not emit a literal `aria-modal`
    // attribute (verified against the rendered DOM), so this test doesn't
    // assert one.
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Deactivate alice?')).toBeInTheDocument()
    expect(screen.getByText('They will lose access immediately.')).toBeInTheDocument()
  })

  it('calls onConfirm when the confirm button is clicked', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    render(
      <ConfirmActionDialog
        open
        onOpenChange={() => {}}
        title="Deactivate user?"
        confirmLabel="Deactivate"
        onConfirm={onConfirm}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Deactivate' }))
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('calls onOpenChange(false) when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    render(<ConfirmActionDialog open onOpenChange={onOpenChange} title="Deactivate user?" onConfirm={() => {}} />)
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onOpenChange).toHaveBeenCalledExactlyOnceWith(false)
  })

  it('loading=true disables both buttons and shows a pending confirm label', () => {
    render(
      <ConfirmActionDialog
        open
        onOpenChange={() => {}}
        title="Deactivate user?"
        confirmLabel="Deactivate"
        onConfirm={() => {}}
        loading
      />,
    )
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Working…' })).toBeDisabled()
  })

  it('renders the inline error verbatim in a role="alert" element, and the dialog stays open (last-admin 409 AC)', () => {
    const onOpenChange = vi.fn()
    render(
      <ConfirmActionDialog
        open
        onOpenChange={onOpenChange}
        title="Deactivate alice?"
        onConfirm={() => {}}
        error="This is the last active admin. Promote another user to admin before demoting or deactivating this account."
      />,
    )
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent(
      'This is the last active admin. Promote another user to admin before demoting or deactivating this account.',
    )
    // Rendering the error is not itself a close — onOpenChange is only called on explicit user action.
    expect(onOpenChange).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('renders no alert when error is null/omitted', () => {
    render(<ConfirmActionDialog open onOpenChange={() => {}} title="Deactivate user?" onConfirm={() => {}} />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('closes on Escape (Radix built-in) when not loading', async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    render(<ConfirmActionDialog open onOpenChange={onOpenChange} title="Deactivate user?" onConfirm={() => {}} />)
    await user.keyboard('{Escape}')
    expect(onOpenChange).toHaveBeenCalledExactlyOnceWith(false)
  })

  it('moves focus into the dialog content on open (Radix focus trap)', () => {
    render(<ConfirmActionDialog open onOpenChange={() => {}} title="Deactivate user?" onConfirm={() => {}} />)
    expect(screen.getByRole('dialog')).toContainElement(document.activeElement as HTMLElement)
  })
})
