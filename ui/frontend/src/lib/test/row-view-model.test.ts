/**
 * row-view-model.test.ts
 *
 * Task 2.2 AC [T] — "Pending rows are visually distinct from Running" and
 * the glossary constraint that "Investigating" badge derivation must come
 * from workflow/pipeline state, NOT `phase == Running` (StatusBadge.tsx
 * variant taxonomy doc / OD-1).
 */
import { describe, it, expect } from 'vitest'
import {
  resolveStatusBadgeVariant,
  toRowViewModel,
  formatAge,
} from '../investigations/row-view-model'
import type { InvestigationListItem } from '../../api/investigations-list'

function makeItem(overrides: Partial<InvestigationListItem>): InvestigationListItem {
  return {
    id: 'inv-1',
    status: 'investigating',
    service: 'checkout-service',
    severity: 'high',
    condition: 'elevated p99 latency',
    started_at: '2026-07-04T12:00:00Z',
    triggered_at: '2026-07-04T11:59:00Z',
    completed_at: null,
    workflow_state: 'investigating',
    workflow_state_changed_at: null,
    ...overrides,
  }
}

describe('resolveStatusBadgeVariant (Pending vs. Running distinction)', () => {
  it('is "pending" when status=investigating and workflow_state has not advanced past detected', () => {
    const item = makeItem({ status: 'investigating', workflow_state: 'detected' })
    expect(resolveStatusBadgeVariant(item)).toBe('pending')
  })

  it('is "pending" when status=investigating and workflow_state is null (job not yet reporting workflow state)', () => {
    const item = makeItem({ status: 'investigating', workflow_state: null })
    expect(resolveStatusBadgeVariant(item)).toBe('pending')
  })

  it('is "investigating" (Running) once workflow_state has advanced beyond detected', () => {
    const item = makeItem({ status: 'investigating', workflow_state: 'investigating' })
    expect(resolveStatusBadgeVariant(item)).toBe('investigating')
  })

  it('produces a DIFFERENT variant for pending vs. running given the same job-phase status', () => {
    const pending = makeItem({ status: 'investigating', workflow_state: 'detected' })
    const running = makeItem({ status: 'investigating', workflow_state: 'investigating' })
    expect(resolveStatusBadgeVariant(pending)).not.toBe(resolveStatusBadgeVariant(running))
  })

  it('maps job-phase completed to the completed badge variant', () => {
    expect(resolveStatusBadgeVariant(makeItem({ status: 'completed' }))).toBe('completed')
  })

  it('maps job-phase failed to "analysis-failed" (glossary OD-1: job-phase Failed -> Analysis Failed), NOT the workflow "failed" variant', () => {
    const variant = resolveStatusBadgeVariant(makeItem({ status: 'failed', workflow_state: 'failed' }))
    expect(variant).toBe('analysis-failed')
    expect(variant).not.toBe('failed')
  })

  it('maps awaiting_confirmation to "awaiting-confirmation"', () => {
    expect(resolveStatusBadgeVariant(makeItem({ status: 'awaiting_confirmation' }))).toBe(
      'awaiting-confirmation',
    )
  })
})

describe('formatAge', () => {
  const now = new Date('2026-07-04T13:00:00Z')

  it('formats sub-minute age as "Just now"', () => {
    expect(formatAge('2026-07-04T12:59:45Z', now)).toBe('Just now')
  })

  it('formats minutes as "Xm ago"', () => {
    expect(formatAge('2026-07-04T12:45:00Z', now)).toBe('15m ago')
  })

  it('formats hours as "Xh ago"', () => {
    expect(formatAge('2026-07-04T10:00:00Z', now)).toBe('3h ago')
  })

  it('formats days as "Xd ago"', () => {
    expect(formatAge('2026-07-01T13:00:00Z', now)).toBe('3d ago')
  })

  it('returns "Unknown" for a null timestamp', () => {
    expect(formatAge(null, now)).toBe('Unknown')
  })

  it('returns "Unknown" for an unparseable timestamp', () => {
    expect(formatAge('not-a-date', now)).toBe('Unknown')
  })
})

describe('toRowViewModel', () => {
  it('maps service/severity/condition/status/age into the InvestigationCard prop shape', () => {
    const now = new Date('2026-07-04T13:00:00Z')
    const row = toRowViewModel(
      makeItem({
        id: 'inv-42',
        service: 'payments-api',
        severity: 'critical',
        condition: 'connection pool exhaustion',
        status: 'investigating',
        workflow_state: 'investigating',
        started_at: '2026-07-04T12:45:00Z',
      }),
      now,
    )

    expect(row).toMatchObject({
      id: 'inv-42',
      href: '/investigations/inv-42',
      variant: 'active',
      serviceName: 'payments-api',
      severity: 'Critical',
      statusVariant: 'investigating',
      timestamp: '15m ago',
      condition: 'connection pool exhaustion',
    })
  })

  it('falls back to triggered_at for age when started_at is absent (still-pending investigation)', () => {
    const now = new Date('2026-07-04T13:00:00Z')
    const row = toRowViewModel(
      makeItem({ started_at: null, triggered_at: '2026-07-04T12:30:00Z' }),
      now,
    )
    expect(row.timestamp).toBe('30m ago')
  })

  it('maps completed status to the completed card variant', () => {
    const row = toRowViewModel(makeItem({ status: 'completed' }))
    expect(row.variant).toBe('completed')
  })

  it('maps failed status to the failed card variant', () => {
    const row = toRowViewModel(makeItem({ status: 'failed' }))
    expect(row.variant).toBe('failed')
  })

  it('derives `component` from a recognizable condition string (Task 2.3)', () => {
    const row = toRowViewModel(
      makeItem({ condition: 'Metric cpu_usage spike: 92.0, expected 15.0 ± 3.0' }),
    )
    expect(row.component).toBe('CPU / compute resources')
  })

  it('falls back to a null `component` when condition is unparseable, without crashing (Task 2.3)', () => {
    const row = toRowViewModel(makeItem({ condition: 'some free-text condition' }))
    expect(row.component).toBeNull()
  })

  it('falls back to a null `component` when condition is null (Task 2.3)', () => {
    const row = toRowViewModel(makeItem({ condition: null }))
    expect(row.component).toBeNull()
  })
})
