import type { Meta, StoryObj } from '@storybook/react-vite'
import { SummaryHeader } from './SummaryHeader'

/**
 * Skeleton story (Task 1.4). Full focus-management + problem-state heuristic
 * wiring lands in Task 2.1/2.4/2.5.
 */
const meta = {
  title: 'Library/SummaryHeader',
  component: SummaryHeader,
  tags: ['autodocs'],
} satisfies Meta<typeof SummaryHeader>

export default meta
type Story = StoryObj<typeof meta>

export const Investigating: Story = {
  args: {
    serviceName: 'checkout-service',
    severity: 'High',
    signalCount: 3,
    statusVariant: 'investigating',
    timestamp: 'Started 2m ago',
    problemState: 'HTTP 5xx error rate elevated (12%)',
  },
}

export const Completed: Story = {
  args: {
    serviceName: 'payments-api',
    severity: 'Medium',
    signalCount: 5,
    statusVariant: 'completed',
    timestamp: 'Completed 45m ago',
    problemState: 'Latency spike traced to deploy abc123',
  },
}

export const AnalysisFailed: Story = {
  args: {
    serviceName: 'inventory-worker',
    severity: 'Critical',
    signalCount: 2,
    statusVariant: 'analysis-failed',
    timestamp: 'Started 15m ago',
  },
}
