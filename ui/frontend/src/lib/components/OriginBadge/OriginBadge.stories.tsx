import type { Meta, StoryObj } from '@storybook/react-vite'
import { OriginBadge } from './OriginBadge'

const meta = {
  title: 'Library/OriginBadge',
  component: OriginBadge,
  tags: ['autodocs'],
} satisfies Meta<typeof OriginBadge>

export default meta
type Story = StoryObj<typeof meta>

export const Local: Story = {
  args: { origin: 'local' },
}

export const Scim: Story = {
  args: { origin: 'scim' },
}
