import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { ConfirmActionDialog } from './ConfirmActionDialog'

const meta = {
  title: 'Library/ConfirmActionDialog',
  component: ConfirmActionDialog,
  tags: ['autodocs'],
} satisfies Meta<typeof ConfirmActionDialog>

export default meta
type Story = StoryObj<typeof meta>

export const Deactivate: Story = {
  args: {
    open: true,
    onOpenChange: () => {},
    title: 'Deactivate alice@corp.com?',
    description: 'They will immediately lose access. You can reactivate this account at any time.',
    confirmLabel: 'Deactivate',
    destructive: true,
    onConfirm: () => {},
  },
}

export const Loading: Story = {
  args: {
    ...Deactivate.args,
    loading: true,
  },
}

export const LastAdminError: Story = {
  args: {
    ...Deactivate.args,
    error:
      'This is the last active admin. Promote another user to admin before demoting or deactivating this account.',
  },
}

/** Wired to real state so open/close and the confirm click are interactive. */
export const Interactive: Story = {
  render: () => {
    function Wrapper() {
      const [open, setOpen] = useState(true)
      return (
        <>
          <button type="button" className="rounded-md bg-primary px-4 py-2 text-sm text-on-primary" onClick={() => setOpen(true)}>
            Open dialog
          </button>
          <ConfirmActionDialog
            open={open}
            onOpenChange={setOpen}
            title="Reactivate bob@corp.com?"
            description="They will regain access with their existing role."
            confirmLabel="Reactivate"
            onConfirm={() => setOpen(false)}
          />
        </>
      )
    }
    return <Wrapper />
  },
}
