import type { Meta, StoryObj } from '@storybook/react-vite'
import { RelatedKbPanel } from './RelatedKbPanel'

/**
 * Skeleton story (Task 1.4) — one story per state (loading/populated/zero).
 * Responsive anchored-bar vs. inline-stack behavior + real expand/collapse
 * state management land in Task 2.1/2.5.
 */
const meta = {
  title: 'Library/RelatedKbPanel',
  component: RelatedKbPanel,
  tags: ['autodocs'],
} satisfies Meta<typeof RelatedKbPanel>

export default meta
type Story = StoryObj<typeof meta>

export const Loading: Story = {
  args: {
    state: 'loading',
    entryCount: 0,
  },
}

export const Populated: Story = {
  args: {
    state: 'populated',
    entryCount: 3,
  },
}

export const PopulatedExpanded: Story = {
  args: {
    state: 'populated',
    entryCount: 3,
    expanded: true,
    children: (
      <ul className="flex flex-col gap-2 text-sm text-text-primary">
        <li>KB-104: checkout-service latency after deploy</li>
        <li>KB-098: connection pool exhaustion runbook</li>
        <li>KB-071: 5xx spike triage steps</li>
      </ul>
    ),
  },
}

export const ZeroEntries: Story = {
  args: {
    state: 'zero',
    entryCount: 0,
  },
}
