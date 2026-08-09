import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { UserFormDialog } from './UserFormDialog'

const meta = {
  title: 'Library/UserFormDialog',
  component: UserFormDialog,
  tags: ['autodocs'],
} satisfies Meta<typeof UserFormDialog>

export default meta
type Story = StoryObj<typeof meta>

export const Create: Story = {
  args: {
    open: true,
    onOpenChange: () => {},
    mode: 'create',
  },
}

export const CreateWithServerError: Story = {
  args: {
    ...Create.args,
    error: "A user named 'bob' already exists.",
  },
}

export const CreateLoading: Story = {
  args: {
    ...Create.args,
    loading: true,
  },
}

export const ResetPassword: Story = {
  args: {
    open: true,
    onOpenChange: () => {},
    mode: 'reset-password',
    targetUserName: 'alice@corp.com',
  },
}

/** Wired to real state so field entry and cancel/submit are interactive. */
export const Interactive: Story = {
  render: () => {
    function Wrapper() {
      const [open, setOpen] = useState(true)
      return (
        <>
          <button type="button" className="rounded-md bg-primary px-4 py-2 text-sm text-on-primary" onClick={() => setOpen(true)}>
            Open dialog
          </button>
          <UserFormDialog
            open={open}
            onOpenChange={setOpen}
            mode="create"
            onCreateSubmit={() => setOpen(false)}
          />
        </>
      )
    }
    return <Wrapper />
  },
}
