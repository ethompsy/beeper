import type { Meta, StoryObj } from '@storybook/react-vite'
import { InvestigationListSkeleton } from './InvestigationListSkeleton'

const meta = {
  title: 'Library/InvestigationListSkeleton',
  component: InvestigationListSkeleton,
  tags: ['autodocs'],
} satisfies Meta<typeof InvestigationListSkeleton>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {},
}

export const FewRows: Story = {
  args: { rowCount: 2 },
}
