import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { TrendChart, type TrendChartPoint } from './TrendChart'

const meta = {
  title: 'Library/TrendChart',
  component: TrendChart,
  tags: ['autodocs'],
} satisfies Meta<typeof TrendChart>

export default meta
type Story = StoryObj<typeof meta>

const MTTR_POINTS: TrendChartPoint[] = [
  { id: '2026-01', label: '2026-01', value: 7200, displayValue: '2h' },
  { id: '2026-02', label: '2026-02', value: 5400, displayValue: '1h 30m' },
  { id: '2026-03', label: '2026-03', value: 3600, displayValue: '1h' },
  { id: '2026-04', label: '2026-04', value: 2400, displayValue: '40m' },
  { id: '2026-05', label: '2026-05', value: 3000, displayValue: '50m' },
]

const formatSeconds = (value: number) => `${Math.round(value / 60)}m`

export const Default: Story = {
  args: {
    points: MTTR_POINTS,
    ariaLabel: 'MTTR trend by month',
    formatValue: formatSeconds,
  },
}

export const SinglePoint: Story = {
  args: {
    points: [MTTR_POINTS[0]],
    ariaLabel: 'MTTR trend by month',
    formatValue: formatSeconds,
  },
}

export const Empty: Story = {
  args: {
    points: [],
    ariaLabel: 'MTTR trend by month',
  },
}

export const Selected: Story = {
  args: {
    points: MTTR_POINTS,
    ariaLabel: 'MTTR trend by month',
    formatValue: formatSeconds,
    selectedId: '2026-03',
    onSelectPoint: () => {},
  },
}

export const Interactive: Story = {
  render: () => {
    function Wrapper() {
      const [selectedId, setSelectedId] = useState<string | null>(null)
      return (
        <div className="flex flex-col gap-2">
          <TrendChart
            points={MTTR_POINTS}
            ariaLabel="MTTR trend by month"
            formatValue={formatSeconds}
            selectedId={selectedId}
            onSelectPoint={(point) => setSelectedId(point.id)}
          />
          <p className="text-sm text-text-secondary">
            {selectedId ? `Selected: ${selectedId}` : 'Click a data point to select it'}
          </p>
        </div>
      )
    }
    return <Wrapper />
  },
}
