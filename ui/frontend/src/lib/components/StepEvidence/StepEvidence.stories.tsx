import type { Meta, StoryObj } from '@storybook/react-vite'
import { StepEvidence } from './StepEvidence'

/**
 * Task 2.5 — inline evidence rendering (FR25) for the investigation detail
 * timeline. One story per evidence kind plus a mixed multi-value case.
 */
const meta = {
  title: 'Library/StepEvidence',
  component: StepEvidence,
  tags: ['autodocs'],
} satisfies Meta<typeof StepEvidence>

export default meta
type Story = StoryObj<typeof meta>

export const MetricValue: Story = {
  args: {
    evidence: [{ kind: 'metric', query: 'http_request_duration_seconds{quantile="0.99"}', value: '1.2s' }],
  },
}

export const LogExcerpt: Story = {
  args: {
    evidence: [
      {
        kind: 'log',
        query: '{service="checkout-service"} |= "ERROR"',
        excerpt: '2026-07-03T12:00:01Z ERROR checkout-service: connection timeout',
      },
    ],
  },
}

export const Mixed: Story = {
  args: {
    evidence: [
      { kind: 'metric', query: 'http_requests_total{code="5xx"}', value: '412/min (baseline: 12/min)' },
      {
        kind: 'log',
        query: '{service="checkout-service"} |= "ERROR"',
        excerpt: '2026-07-03T12:00:01Z ERROR checkout-service: connection timeout',
      },
    ],
  },
}

export const Empty: Story = {
  args: {
    evidence: [],
  },
}
