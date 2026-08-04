import type { Meta, StoryObj } from '@storybook/react-vite'
import { Sidebar, type SidebarGroupData } from './Sidebar'

/**
 * Sidebar (Task 2.1) — Observe/Learn/Manage navigation, per
 * docs/specs/ux-design-specification.md "Sidebar Group" component.
 * Observe is always first, Investigations is always the first item.
 */
const DEMO_GROUPS: SidebarGroupData[] = [
  {
    id: 'observe',
    label: 'Observe',
    items: [
      { id: 'investigations', label: 'Investigations', href: '/app/investigations' },
      { id: 'sources', label: 'Sources', href: '/app/sources' },
      { id: 'ingestion-stats', label: 'Ingestion Stats', href: '/app/ingestion-stats' },
    ],
  },
  {
    id: 'learn',
    label: 'Learn',
    items: [
      { id: 'knowledge-base', label: 'Knowledge Base', href: '/app/knowledge-base' },
      { id: 'metrics', label: 'Metrics', href: '/app/metrics' },
    ],
  },
  {
    id: 'manage',
    label: 'Manage',
    items: [{ id: 'spending', label: 'Spending', href: '/app/spending' }],
  },
]

const meta = {
  title: 'Library/Sidebar',
  component: Sidebar,
  tags: ['autodocs'],
  args: {
    groups: DEMO_GROUPS,
    activeItemId: 'investigations',
  },
  decorators: [
    (Story) => (
      <div className="h-96">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof Sidebar>

export default meta
type Story = StoryObj<typeof meta>

export const Expanded: Story = {
  args: {
    expanded: true,
  },
}

export const Collapsed: Story = {
  args: {
    expanded: false,
  },
}

export const ExpandedOverlay: Story = {
  args: {
    expanded: true,
    isOverlay: true,
  },
}
