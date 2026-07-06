import type { Meta, StoryObj } from '@storybook/react-vite'
import { FailureNotice } from './FailureNotice'

/**
 * Task 2.5 — FR23: a Failed investigation renders completed steps followed
 * by this distinct failure notice, never a conclusion block.
 */
const meta = {
  title: 'Library/FailureNotice',
  component: FailureNotice,
  tags: ['autodocs'],
} satisfies Meta<typeof FailureNotice>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {},
}

export const WithMessage: Story = {
  args: {
    message: 'Investigator pod exited unexpectedly while querying the knowledge base.',
  },
}
