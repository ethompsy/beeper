import type { Meta, StoryObj } from '@storybook/react-vite'
import { KbEntryCard } from './KbEntryCard'

/**
 * KbEntryCard stories (Task 5.1) — one story per entry type plus the
 * search-result (relevance score) and related-entries (minimal) variants,
 * covering every context this primitive is reused in: browse list, search
 * results, and the entry-detail "Related Entries" section.
 */
const meta = {
  title: 'Library/KbEntryCard',
  component: KbEntryCard,
  tags: ['autodocs'],
} satisfies Meta<typeof KbEntryCard>

export default meta
type Story = StoryObj<typeof meta>

export const Investigation: Story = {
  args: {
    title: 'checkout-service latency after deploy',
    entryType: 'investigation',
    service: 'checkout-service',
    date: '2026-06-01',
    author: 'beeper',
    snippet: 'Connection pool exhaustion after a deploy caused elevated p99 latency.',
    tags: ['deploy', 'latency'],
    href: '/app/knowledge/kb-001',
  },
}

export const Runbook: Story = {
  args: {
    title: 'Restarting the payments worker pool',
    entryType: 'runbook',
    service: 'payments-api',
    date: '2026-05-20',
    author: 'sre-team',
    snippet: 'Step-by-step recovery procedure for a stuck payments worker pool.',
    href: '/app/knowledge/kb-002',
  },
}

export const Correction: Story = {
  args: {
    title: 'Corrected root cause for inventory-worker OOM',
    entryType: 'correction',
    service: 'inventory-worker',
    date: '2026-04-11',
    href: '/app/knowledge/kb-003',
  },
}

export const ProvenFix: Story = {
  args: {
    title: 'Increase connection pool size',
    entryType: 'proven_fix',
    service: 'checkout-service',
    date: '2026-03-02',
    href: '/app/knowledge/kb-004',
  },
}

export const SearchResultWithRelevance: Story = {
  args: {
    title: 'checkout-service latency after deploy',
    entryType: 'investigation',
    service: 'checkout-service',
    relevanceScore: 0.82,
    snippet: 'Connection pool exhaustion after a deploy caused elevated p99 latency.',
    href: '/app/knowledge/kb-001',
  },
}

export const Minimal: Story = {
  args: {
    title: 'Untitled entry with no metadata',
    entryType: 'unknown',
    href: '/app/knowledge/kb-005',
  },
}
