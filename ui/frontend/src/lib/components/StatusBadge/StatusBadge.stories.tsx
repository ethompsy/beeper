import type { Meta, StoryObj } from '@storybook/react-vite'
import { StatusBadge, type StatusBadgeVariant } from './StatusBadge'

/**
 * Skeleton story (Task 1.4) — one story per variant group so `/design-sync`
 * and Storybook reviewers can see every glossary-approved label at a glance.
 * Full interaction/behavior stories are out of scope until Milestone 1.2.
 */
const meta = {
  title: 'Library/StatusBadge',
  component: StatusBadge,
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'select',
      options: [
        'investigating',
        'awaiting-confirmation',
        'completed',
        'analysis-failed',
        'pending',
        'detected',
        'resolved',
        'verified',
        'failed',
        'healthy',
        'warning',
        'critical',
        'warming-up',
        'no-data',
      ] satisfies StatusBadgeVariant[],
    },
  },
} satisfies Meta<typeof StatusBadge>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    variant: 'investigating',
  },
}

/** All job-phase variants (InvestigationPhase). */
export const JobPhaseVariants: Story = {
  args: { variant: 'investigating' },
  render: () => (
    <div className="flex flex-wrap gap-2">
      <StatusBadge variant="investigating" />
      <StatusBadge variant="awaiting-confirmation" />
      <StatusBadge variant="completed" />
      <StatusBadge variant="analysis-failed" />
      <StatusBadge variant="pending" />
    </div>
  ),
}

/** All workflow-state variants (WorkflowState). Note `failed` here renders
 * plain "Failed" — distinct from job-phase `analysis-failed` above. */
export const WorkflowStateVariants: Story = {
  args: { variant: 'detected' },
  render: () => (
    <div className="flex flex-wrap gap-2">
      <StatusBadge variant="detected" />
      <StatusBadge variant="investigating" />
      <StatusBadge variant="resolved" />
      <StatusBadge variant="verified" />
      <StatusBadge variant="failed" />
    </div>
  ),
}

/** Pipeline / diagnostic health variants. */
export const PipelineHealthVariants: Story = {
  args: { variant: 'healthy' },
  render: () => (
    <div className="flex flex-wrap gap-2">
      <StatusBadge variant="healthy" />
      <StatusBadge variant="warning" />
      <StatusBadge variant="critical" />
      <StatusBadge variant="warming-up" />
      <StatusBadge variant="no-data" />
    </div>
  ),
}
