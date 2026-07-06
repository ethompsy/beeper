import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { StatusGroupFilter } from './StatusGroupFilter'

const meta = {
  title: 'Library/StatusGroupFilter',
  component: StatusGroupFilter,
  tags: ['autodocs'],
} satisfies Meta<typeof StatusGroupFilter>

export default meta
type Story = StoryObj<typeof meta>

const OPTIONS = [
  { id: 'active', label: 'Active', count: 3 },
  { id: 'resolved', label: 'Resolved', count: 12 },
  { id: 'failed', label: 'Failed', count: 1 },
]

export const Active: Story = {
  args: { options: OPTIONS, selectedId: 'active', onSelect: () => {} },
}

export const Interactive: Story = {
  render: () => {
    function Wrapper() {
      const [selected, setSelected] = useState('active')
      return <StatusGroupFilter options={OPTIONS} selectedId={selected} onSelect={setSelected} />
    }
    return <Wrapper />
  },
}
