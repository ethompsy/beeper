import type { Meta, StoryObj } from '@storybook/react-vite'
import { NotFoundMessage } from './NotFoundMessage'

/**
 * Task 2.5 — invalid investigation id renders "Investigation not found"
 * inside the app shell (sidebar visible), not a generic 404 page.
 */
const meta = {
  title: 'Library/NotFoundMessage',
  component: NotFoundMessage,
  tags: ['autodocs'],
} satisfies Meta<typeof NotFoundMessage>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    investigationId: 'INV-9999',
  },
}
