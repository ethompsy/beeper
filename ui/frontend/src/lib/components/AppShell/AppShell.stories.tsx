import type { Meta, StoryObj } from '@storybook/react-vite'
import { AppShell } from './AppShell'
import type { SidebarGroupData } from '../Sidebar'

/**
 * AppShell (Task 2.1) — layout shell composing the top bar + Sidebar +
 * content slot. Real route-driven state comes from `useSidebarState` in the
 * app; these stories pass fixed booleans to demonstrate each visual mode.
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
  title: 'Library/AppShell',
  component: AppShell,
  tags: ['autodocs'],
  args: {
    groups: DEMO_GROUPS,
    activeItemId: 'investigations',
    onToggleSidebar: () => {},
    children: (
      <p className="text-text-primary">Route content renders here.</p>
    ),
  },
} satisfies Meta<typeof AppShell>

export default meta
type Story = StoryObj<typeof meta>

export const ExpandedPushing: Story = {
  args: {
    expanded: true,
    isOverlay: false,
    breadcrumb: <span>Investigations</span>,
  },
}

export const CollapsedIconRail: Story = {
  args: {
    expanded: false,
    isOverlay: false,
    breadcrumb: <span>Investigations</span>,
  },
}

export const ExpandedOverlay: Story = {
  args: {
    expanded: true,
    isOverlay: true,
    breadcrumb: <span>Investigations</span>,
  },
}

export const DetailBreadcrumb: Story = {
  args: {
    expanded: false,
    isOverlay: false,
    activeItemId: 'investigations',
    breadcrumb: (
      <>
        <a href="/app/investigations" className="text-text-secondary">
          Investigations
        </a>
        <span aria-hidden="true"> &gt; </span>
        <span className="text-primary">INV-0042</span>
      </>
    ),
  },
}
