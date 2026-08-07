import type { Meta, StoryObj } from '@storybook/react-vite'
import { EwmaProgressBar } from './EwmaProgressBar'

const meta = {
  title: 'Library/EwmaProgressBar',
  component: EwmaProgressBar,
  tags: ['autodocs'],
  argTypes: {
    status: {
      control: 'select',
      options: ['healthy', 'warning'],
    },
    percentage: {
      control: { type: 'range', min: 0, max: 100, step: 1 },
    },
  },
} satisfies Meta<typeof EwmaProgressBar>

export default meta
type Story = StoryObj<typeof meta>

export const Warming: Story = {
  args: {
    percentage: 45,
    status: 'warning',
  },
}

export const NearlyWarmed: Story = {
  args: {
    percentage: 92,
    status: 'warning',
  },
}

export const Warmed: Story = {
  args: {
    percentage: 100,
    status: 'healthy',
  },
}

/** Values above 100 or below 0 are clamped rather than overflowing the bar. */
export const ClampedOutOfRange: Story = {
  args: {
    percentage: 140,
    status: 'warning',
  },
}
