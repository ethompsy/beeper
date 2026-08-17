import type { Meta, StoryObj } from '@storybook/react-vite'
import { UserTable, type UserTableRow } from './UserTable'

const meta = {
  title: 'Library/UserTable',
  component: UserTable,
  tags: ['autodocs'],
} satisfies Meta<typeof UserTable>

export default meta
type Story = StoryObj<typeof meta>

const USERS: UserTableRow[] = [
  {
    id: 'user-1',
    user_name: 'alice@corp.com',
    display_name: 'Alice Alpha',
    role: 'admin',
    origin: 'local',
    active: true,
    last_login_at: '2026-08-09T12:00:00+00:00',
  },
  {
    id: 'user-2',
    user_name: 'bob@corp.com',
    display_name: 'Bob Beta',
    role: 'user',
    origin: 'scim',
    active: true,
    last_login_at: null,
  },
  {
    id: 'user-3',
    user_name: 'carol@corp.com',
    display_name: 'Carol Gamma',
    role: 'user',
    origin: 'local',
    active: false,
    last_login_at: '2026-06-01T09:15:00+00:00',
  },
]

const noop = () => {}

export const Default: Story = {
  args: {
    users: USERS,
    onRoleChange: noop,
    onDeactivateRequest: noop,
    onReactivateRequest: noop,
    onResetPasswordRequest: noop,
  },
}

export const ScimOwnedRowReadOnly: Story = {
  args: {
    ...Default.args,
    rowState: { 'user-2': { readOnly: true } },
  },
}

export const RowWithInlineLastAdminError: Story = {
  args: {
    ...Default.args,
    rowState: {
      'user-1': {
        error:
          'This is the last active admin. Promote another user to admin before demoting or deactivating this account.',
      },
    },
  },
}

export const PendingRow: Story = {
  args: {
    ...Default.args,
    rowState: { 'user-1': { pending: true } },
  },
}
