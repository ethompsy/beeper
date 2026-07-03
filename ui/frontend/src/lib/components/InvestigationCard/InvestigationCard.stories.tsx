import type { Meta, StoryObj } from '@storybook/react-vite'
import { InvestigationCard } from './InvestigationCard'

/**
 * Skeleton story (Task 1.4) — one story per variant (active/completed/failed)
 * per the Task 4.4 design-sync inventory. Real list wiring lands in Task 2.2.
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
