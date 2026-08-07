import type { Meta, StoryObj } from '@storybook/react-vite'
import { KbListSkeleton } from './KbListSkeleton'

const meta = {
  title: 'Library/KbListSkeleton',
  component: KbListSkeleton,
  tags: ['autodocs'],
} satisfies Meta<typeof KbListSkeleton>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {},
}

export const FewRows: Story = {
  args: { rowCount: 2 },
}
