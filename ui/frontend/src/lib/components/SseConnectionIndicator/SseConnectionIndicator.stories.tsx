import type { Meta, StoryObj } from '@storybook/react-vite'
import { SseConnectionIndicator } from './SseConnectionIndicator'

/**
 * Task 2.6a — FR27: the SSE 4-state lifecycle's visible indicator.
 * `connected`/`reconnected` render nothing (spec: "No indicator (default)");
 * only `disconnected` and `failed` are visually distinct.
 */
const meta = {
  title: 'Library/SseConnectionIndicator',
  component: SseConnectionIndicator,
  tags: ['autodocs'],
} satisfies Meta<typeof SseConnectionIndicator>

export default meta
type Story = StoryObj<typeof meta>

export const Connected: Story = {
  args: { connectionState: 'connected' },
}

export const Disconnected: Story = {
  args: { connectionState: 'disconnected' },
}

export const Reconnected: Story = {
  args: { connectionState: 'reconnected' },
}

export const Failed: Story = {
  args: { connectionState: 'failed' },
}
