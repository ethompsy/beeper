import * as Dialog from '@radix-ui/react-dialog'
import { cn } from '../../utils/cn'

/**
 * ConfirmActionDialog — generic accessible confirm dialog (Task 8.7, ADR
 * 0002 §6, FR60).
 *
 * Built on Radix `Dialog` (focus trap, Escape-to-close, `aria-modal`,
 * portal rendering) rather than hand-rolled, per the task instructions —
 * no accessible dialog primitive existed in this codebase before this
 * task. Used for the deactivate/reactivate confirmation (required by the
 * task's AC) and reused for role-change confirmation
 * (`AdminUsersPage.tsx`'s design decision, documented there) since a role
 * PATCH can also 409 `last-admin` and needs the same inline-error
 * treatment.
 *
 * `error` is the load-bearing prop for the task's explicit AC: "self
 * -demotion blocked by last-admin 409 rendered inline" — the caller
 * catches the thrown `AdminUsersError` from the PATCH call, sets `error`
 * to its `.detail` (rendered verbatim, no re-derived copy), and leaves the
 * dialog OPEN (does not call `onOpenChange(false)`) so the message is
 * visible rather than a toast that could be missed or a silent failure.
 */
export interface ConfirmActionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  confirmLabel?: string
  cancelLabel?: string
  onConfirm: () => void
  /** True while the confirm action's request is in flight — disables both buttons and shows a pending label. */
  loading?: boolean
  /** Inline error slot — a 409 (`last-admin`/`scim-owned-user`) or other failure's `.detail`, rendered verbatim. `null`/omitted renders nothing. */
  error?: string | null
  /** Visually flags the confirm button as destructive (status-critical) — e.g. "Deactivate". Default: primary (e.g. "Reactivate", "Change role"). */
  destructive?: boolean
}

export function ConfirmActionDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onConfirm,
  loading = false,
  error = null,
  destructive = false,
}: ConfirmActionDialogProps) {
  function handleOpenChange(next: boolean) {
    if (loading) return // Radix would otherwise let Escape/overlay-click close mid-request.
    onOpenChange(next)
  }

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-surface-base/80 transition-opacity duration-150 motion-reduce:transition-none" />
        <Dialog.Content
          data-slot="confirm-action-dialog"
          className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-surface-overlay bg-surface-raised p-6 shadow-lg transition-opacity duration-150 motion-reduce:transition-none focus:outline-none"
        >
          <Dialog.Title className="text-lg font-semibold text-text-primary">{title}</Dialog.Title>
          {description ? (
            <Dialog.Description className="mt-2 text-sm text-text-secondary">{description}</Dialog.Description>
          ) : (
            // Radix warns if a Content has no Description — an empty one keeps aria-describedby valid without visible copy.
            <Dialog.Description className="sr-only">{title}</Dialog.Description>
          )}

          {error ? (
            <p role="alert" data-slot="confirm-action-dialog-error" className="mt-3 text-sm text-status-critical">
              {error}
            </p>
          ) : null}

          <div className="mt-6 flex justify-end gap-3">
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
              {cancelLabel}
            </button>
            <button
              type="button"
              onClick={onConfirm}
              disabled={loading}
              className={cn(
                'rounded-md px-4 py-2 text-sm font-medium text-on-primary',
                'transition-colors duration-150 motion-reduce:transition-none',
                destructive ? 'bg-status-critical hover:bg-status-critical/90' : 'bg-primary hover:bg-primary-hover',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
                'disabled:cursor-not-allowed disabled:opacity-60',
              )}
            >
              {loading ? 'Working…' : confirmLabel}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
