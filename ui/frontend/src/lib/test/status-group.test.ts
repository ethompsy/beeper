/**
 * status-group.test.ts
 *
 * Task 2.2 AC [T] — "the list orders active + high-severity first; the
 * status-group filter (active = Pending/Running, resolved = Completed,
 * failed = Failed) filters correctly" (FR22/FR46).
 *
 * Pure-function tests against `src/lib/investigations/status-group.ts` —
 * no React/DOM required.
 */
import { describe, it, expect } from 'vitest'
import {
  filterByStatusGroup,
  orderInvestigations,
  selectAndOrder,
  severityRank,
  STATUS_GROUPS,
  DEFAULT_STATUS_GROUP,
} from '../investigations/status-group'
import type { InvestigationListItem } from '../../api/investigations-list'

function makeItem(overrides: Partial<InvestigationListItem>): InvestigationListItem {
  return {
    id: 'inv-default',
    status: 'investigating',
    service: 'checkout-service',
    severity: 'medium',
    condition: 'elevated error rate',
    started_at: '2026-07-04T12:00:00Z',
    triggered_at: '2026-07-04T12:00:00Z',
    completed_at: null,
    workflow_state: 'investigating',
    workflow_state_changed_at: null,
    ...overrides,
  }
}

describe('status-group', () => {
  it('DEFAULT_STATUS_GROUP is "active" (FR22: list defaults to active on load)', () => {
    expect(DEFAULT_STATUS_GROUP).toBe('active')
  })

  it('STATUS_GROUPS enumerates active/resolved/failed', () => {
    expect(STATUS_GROUPS).toEqual(['active', 'resolved', 'failed'])
  })

  describe('filterByStatusGroup', () => {
    const items = [
      makeItem({ id: 'a', status: 'investigating' }),
      makeItem({ id: 'b', status: 'awaiting_confirmation' }),
      makeItem({ id: 'c', status: 'completed' }),
      makeItem({ id: 'd', status: 'failed' }),
    ]

    it('"active" includes investigating + awaiting_confirmation (Pending/Running), excludes completed/failed', () => {
      const result = filterByStatusGroup(items, 'active')
      expect(result.map((i) => i.id)).toEqual(['a', 'b'])
    })

    it('"resolved" includes only completed', () => {
      const result = filterByStatusGroup(items, 'resolved')
      expect(result.map((i) => i.id)).toEqual(['c'])
    })

    it('"failed" includes only failed', () => {
      const result = filterByStatusGroup(items, 'failed')
      expect(result.map((i) => i.id)).toEqual(['d'])
    })

    it('returns an empty array when no investigation belongs to the group', () => {
      const onlyCompleted = [makeItem({ id: 'c', status: 'completed' })]
      expect(filterByStatusGroup(onlyCompleted, 'failed')).toEqual([])
    })
  })

  describe('severityRank', () => {
    it('ranks critical > high > medium > low', () => {
      expect(severityRank('critical')).toBeGreaterThan(severityRank('high'))
      expect(severityRank('high')).toBeGreaterThan(severityRank('medium'))
      expect(severityRank('medium')).toBeGreaterThan(severityRank('low'))
    })
  })

  describe('orderInvestigations', () => {
    it('orders active investigations before completed/failed regardless of input order', () => {
      const items = [
        makeItem({ id: 'completed-1', status: 'completed', severity: 'critical' }),
        makeItem({ id: 'active-1', status: 'investigating', severity: 'low' }),
        makeItem({ id: 'failed-1', status: 'failed', severity: 'critical' }),
      ]
      const ordered = orderInvestigations(items)
      // Active (even low severity) sorts ahead of completed/failed (even critical).
      expect(ordered[0].id).toBe('active-1')
    })

    it('within the active tier, orders high-severity first', () => {
      const items = [
        makeItem({ id: 'low', status: 'investigating', severity: 'low' }),
        makeItem({ id: 'critical', status: 'investigating', severity: 'critical' }),
        makeItem({ id: 'medium', status: 'investigating', severity: 'medium' }),
        makeItem({ id: 'high', status: 'investigating', severity: 'high' }),
      ]
      const ordered = orderInvestigations(items)
      expect(ordered.map((i) => i.id)).toEqual(['critical', 'high', 'medium', 'low'])
    })

    it('is stable for equal severity within the same tier (preserves original relative order)', () => {
      const items = [
        makeItem({ id: 'first', status: 'investigating', severity: 'high' }),
        makeItem({ id: 'second', status: 'investigating', severity: 'high' }),
      ]
      const ordered = orderInvestigations(items)
      expect(ordered.map((i) => i.id)).toEqual(['first', 'second'])
    })
  })

  describe('selectAndOrder', () => {
    it('filters to the group then orders active+high-severity-first within it', () => {
      const items = [
        makeItem({ id: 'a-low', status: 'investigating', severity: 'low' }),
        makeItem({ id: 'a-critical', status: 'awaiting_confirmation', severity: 'critical' }),
        makeItem({ id: 'completed', status: 'completed', severity: 'critical' }),
      ]
      const result = selectAndOrder(items, 'active')
      expect(result.map((i) => i.id)).toEqual(['a-critical', 'a-low'])
    })
  })
})
