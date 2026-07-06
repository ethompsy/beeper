import type { Meta, StoryObj } from '@storybook/react-vite'
import { EmptyGroupState } from './EmptyGroupState'

const meta = {
  title: 'Library/EmptyGroupState',
  component: EmptyGroupState,
  tags: ['autodocs'],
} satisfies Meta<typeof EmptyGroupState>

export default meta
type Story = StoryObj<typeof meta>

export const NoActive: Story = {
  args: {
    title: 'No active investigations',
    description: 'Investigations appear automatically when Beeper detects anomalies in your services.',
  },
}

export const NoResolved: Story = {
  args: {
    title: 'No resolved investigations',
    description: 'Resolved investigations will appear here once they are completed successfully.',
  },
}

export const NoFailed: Story = {
  args: {
    title: 'No failed investigations',
    description: 'Failed investigations will appear here when Beeper encounters an error during analysis.',
  },
}
