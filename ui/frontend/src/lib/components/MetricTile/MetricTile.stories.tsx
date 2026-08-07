import type { Meta, StoryObj } from '@storybook/react-vite'
import { MetricTile, type MetricTileStatus } from './MetricTile'

const meta = {
  title: 'Library/MetricTile',
  component: MetricTile,
  tags: ['autodocs'],
  argTypes: {
    status: {
      control: 'select',
      options: ['healthy', 'warning', 'critical', 'muted', 'neutral'] satisfies MetricTileStatus[],
    },
  },
} satisfies Meta<typeof MetricTile>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    label: 'Metrics Received',
    value: '1,234',
    status: 'healthy',
  },
}

/** All status variants side by side (Ingestion Stats dashboard, Task 5.2). */
export const AllStatuses: Story = {
  args: { label: 'Metrics Received', value: '1,234' },
  render: () => (
    <div className="grid grid-cols-2 gap-3">
      <MetricTile label="Metrics Received" value="12,904" status="healthy" />
      <MetricTile label="Anomalies Detected" value="3" status="warning" />
      <MetricTile label="Logs Received" value="0" status="critical" />
      <MetricTile label="Anomalies Suppressed" value="1" status="muted" />
      <MetricTile label="Buffered Count" value="42" status="neutral" />
    </div>
  ),
}
