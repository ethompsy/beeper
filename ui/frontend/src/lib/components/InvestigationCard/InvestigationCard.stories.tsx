import type { Meta, StoryObj } from '@storybook/react-vite'
import { InvestigationCard } from './InvestigationCard'

/**
 * Skeleton story (Task 1.4) — one story per variant (active/completed/failed)
 * per the Task 4.4 design-sync inventory. Real list wiring lands in Task 2.2.
 *
 * Task 4.2 — added `WithComponentAndProblemState` to cover the `component`
 * (Task 2.3) and `problemState` (Task 2.4) subtitle slots, which the
 * variant-only stories above deliberately omit (they demonstrate the
 * minimal-props case without those optional slots rendered).
 */
const meta = {
  title: 'Library/InvestigationCard',
  component: InvestigationCard,
  tags: ['autodocs'],
} satisfies Meta<typeof InvestigationCard>

export default meta
type Story = StoryObj<typeof meta>

export const Active: Story = {
  args: {
    variant: 'active',
    serviceName: 'checkout-service',
    severity: 'High',
    signalCount: 3,
    timestamp: '2m ago',
    statusVariant: 'investigating',
    href: '/app/investigations/demo-active',
  },
}

export const Completed: Story = {
  args: {
    variant: 'completed',
    serviceName: 'payments-api',
    severity: 'Medium',
    signalCount: 5,
    timestamp: '1h ago',
    statusVariant: 'completed',
    href: '/app/investigations/demo-completed',
  },
}

export const Failed: Story = {
  args: {
    variant: 'failed',
    serviceName: 'inventory-worker',
    severity: 'Critical',
    signalCount: 2,
    timestamp: '15m ago',
    statusVariant: 'analysis-failed',
    href: '/app/investigations/demo-failed',
  },
}

export const WithComponentAndProblemState: Story = {
  args: {
    variant: 'active',
    serviceName: 'checkout-service',
    severity: 'High',
    signalCount: 3,
    timestamp: '2m ago',
    statusVariant: 'investigating',
    href: '/app/investigations/demo-active-with-slots',
    problemState: 'High CPU usage (92.0%)',
    component: 'CPU / compute resources',
  },
}
