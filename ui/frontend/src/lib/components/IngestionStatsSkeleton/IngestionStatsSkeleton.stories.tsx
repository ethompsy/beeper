import type { Meta, StoryObj } from '@storybook/react-vite'
import { IngestionStatsSkeleton } from './IngestionStatsSkeleton'

const meta = {
  title: 'Library/IngestionStatsSkeleton',
  component: IngestionStatsSkeleton,
  tags: ['autodocs'],
} satisfies Meta<typeof IngestionStatsSkeleton>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {},
}
