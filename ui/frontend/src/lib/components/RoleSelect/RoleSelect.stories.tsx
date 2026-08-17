import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { RoleSelect, type RoleSelectValue } from './RoleSelect'

const meta = {
  title: 'Library/RoleSelect',
  component: RoleSelect,
  tags: ['autodocs'],
} satisfies Meta<typeof RoleSelect>

export default meta
type Story = StoryObj<typeof meta>

export const Admin: Story = {
  args: { id: 'role-select-admin', label: 'Role', value: 'admin', onChange: () => {} },
}

export const User: Story = {
  args: { id: 'role-select-user', label: 'Role', value: 'user', onChange: () => {} },
}

export const Disabled: Story = {
  args: { id: 'role-select-disabled', label: 'Role', value: 'user', onChange: () => {}, disabled: true },
}

/** Wired to real state so the value visibly changes on selection. */
export const Interactive: Story = {
  render: () => {
    function Wrapper() {
      const [value, setValue] = useState<RoleSelectValue>('user')
      return <RoleSelect id="role-select-interactive" label="Role" value={value} onChange={setValue} />
    }
    return <Wrapper />
  },
}
