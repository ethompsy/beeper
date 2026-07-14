import type { Meta, StoryObj } from '@storybook/react-vite'
import { InvestigationStep } from './InvestigationStep'

/**
 * Skeleton story (Task 1.4) — one story per step type plus the first-evidence
 * emphasis state. Real SSE append/backfill wiring lands in Task 2.5/2.6a.
 */
const meta = {
  title: 'Library/InvestigationStep',
  component: InvestigationStep,
  tags: ['autodocs'],
} satisfies Meta<typeof InvestigationStep>

export default meta
type Story = StoryObj<typeof meta>

export const MetricQuery: Story = {
  args: {
    type: 'metric',
    order: 1,
    description: 'Queried http_request_duration_seconds for checkout-service',
    evidence: <code className="font-mono text-sm">p99=1.2s (baseline: 180ms)</code>,
  },
}

export const LogQuery: Story = {
  args: {
    type: 'log',
    order: 2,
    description: 'Queried application logs for error spikes',
    evidence: (
      <pre className="max-h-32 overflow-x-auto font-mono text-sm">
        2026-07-03T12:00:01Z ERROR checkout-service: connection timeout
      </pre>
    ),
  },
}

export const KbQuery: Story = {
  args: {
    type: 'kb',
    order: 3,
    description: 'Searched knowledge base for similar incidents',
  },
}

export const Deploy: Story = {
  args: {
    type: 'deploy',
    order: 4,
    description: 'Detected deploy abc123 (checkout-service) 3 minutes before the anomaly',
  },
}

export const Correlation: Story = {
  args: {
    type: 'correlation',
    order: 5,
    description: 'Correlated metric spike with a recent deploy event',
  },
}

export const Summary: Story = {
  args: {
    type: 'summary',
    order: 6,
    description: 'Investigation concluded: elevated latency traced to deploy abc123.',
  },
}

export const FirstEvidence: Story = {
  args: {
    ...MetricQuery.args,
    isFirstEvidence: true,
  },
}
