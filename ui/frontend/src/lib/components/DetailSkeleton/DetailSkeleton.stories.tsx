import type { Meta, StoryObj } from '@storybook/react-vite'
import { DetailSkeleton } from './DetailSkeleton'

/**
 * Task 2.5 — cold-load skeleton for the investigation detail view
 * (NFR19: never a blank frame while the one-shot detail fetch is pending).
 */
const meta = {
  title: 'Library/DetailSkeleton',
  component: DetailSkeleton,
  tags: ['autodocs'],
} satisfies Meta<typeof DetailSkeleton>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {},
}
