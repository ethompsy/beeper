/**
 * investigation-detail-mappers.test.ts (Task 2.5)
 *
 * Unit coverage for the glossary-driven mapping rules that sit between the
 * Task 1.6 API shape and the Task 1.4 library primitives' prop types:
 *   - OD-1: job-phase "failed" → StatusBadge variant "analysis-failed"
 *     (NOT the separate workflow-state "failed" variant).
 *   - OD-5: "investigating" badge comes from the normalized phase string
 *     the JSON API already exposes, not a raw k8s "Running" value.
 *   - First-evidence detection for the InvestigationStep emphasis treatment.
 */
import { describe, it, expect } from 'vitest'
import {
  apiStepTypeToStepType,
  findFirstEvidenceStepOrder,
  mergeBackfilledSteps,
  mergeLiveStepEvents,
  statusToBadgeVariant,
} from '../investigation-detail-mappers'
import type { InvestigationStepDto } from '../../api/investigation-detail'
import type { InvestigationStepEventPayload } from '../../lib'

describe('statusToBadgeVariant', () => {
  it('maps job-phase "failed" to the "analysis-failed" variant (glossary OD-1)', () => {
    expect(statusToBadgeVariant('failed')).toBe('analysis-failed')
  })

  it('maps "investigating" to the "investigating" variant', () => {
    expect(statusToBadgeVariant('investigating')).toBe('investigating')
  })

  it('maps "awaiting_confirmation" to the "awaiting-confirmation" variant', () => {
    expect(statusToBadgeVariant('awaiting_confirmation')).toBe('awaiting-confirmation')
  })

  it('maps "completed" to the "completed" variant', () => {
    expect(statusToBadgeVariant('completed')).toBe('completed')
  })

  it('maps "pending" to the "pending" variant', () => {
    expect(statusToBadgeVariant('pending')).toBe('pending')
  })

  it('falls back to "pending" for an unrecognized status rather than throwing', () => {
    expect(statusToBadgeVariant('some-future-phase')).toBe('pending')
  })
})

describe('apiStepTypeToStepType', () => {
  it.each([
    ['metric', 'metric'],
    ['log', 'log'],
    ['deploy', 'deploy'],
    ['kb', 'kb'],
    ['correlation', 'correlation'],
    ['summary', 'summary'],
  ] as const)('passes through known type %s', (input, expected) => {
    expect(apiStepTypeToStepType(input)).toBe(expected)
  })

  it('falls back to "summary" for an unrecognized type', () => {
    expect(apiStepTypeToStepType('config_change')).toBe('summary')
  })
})

function step(overrides: Partial<InvestigationStepDto>): InvestigationStepDto {
  return {
    order: 1,
    key: 'k',
    label: 'label',
    state: 'completed',
    type: 'summary',
    ...overrides,
  }
}

describe('findFirstEvidenceStepOrder', () => {
  it('returns the order of the first completed metric/log/deploy/correlation step', () => {
    const steps = [
      step({ order: 1, type: 'kb', state: 'completed' }),
      step({ order: 2, type: 'metric', state: 'completed' }),
      step({ order: 3, type: 'log', state: 'completed' }),
    ]
    expect(findFirstEvidenceStepOrder(steps)).toBe(2)
  })

  it('skips a matching-type step that has not completed yet', () => {
    const steps = [
      step({ order: 1, type: 'metric', state: 'active' }),
      step({ order: 2, type: 'log', state: 'completed' }),
    ]
    expect(findFirstEvidenceStepOrder(steps)).toBe(2)
  })

  it('returns null when no step qualifies as evidence', () => {
    const steps = [
      step({ order: 1, type: 'kb', state: 'completed' }),
      step({ order: 2, type: 'summary', state: 'completed' }),
    ]
    expect(findFirstEvidenceStepOrder(steps)).toBeNull()
  })

  it('returns null for an empty step list', () => {
    expect(findFirstEvidenceStepOrder([])).toBeNull()
  })
})

/**
 * mergeBackfilledSteps — Task 2.6b's reconnect-backfill AC:
 * "[T] On reconnect, missed steps backfill in order via
 * GET /api/v1/investigations/{id} ... merged idempotently and deduped by
 * order (no duplicate steps, no regression of already-shown steps)."
 */
describe('mergeBackfilledSteps', () => {
  it('passes the current steps through unchanged when backfill is null (no reconnect yet)', () => {
    const current = [step({ order: 1, label: 'Customer Impact' })]
    expect(mergeBackfilledSteps(current, null)).toBe(current)
  })

  it('passes the current steps through unchanged when the backfill snapshot is empty', () => {
    const current = [step({ order: 1, label: 'Customer Impact' })]
    expect(mergeBackfilledSteps(current, [])).toBe(current)
  })

  it('backfills a step that arrived while disconnected (missing from current steps), inserted in order', () => {
    const current = [
      step({ order: 1, label: 'Customer Impact', state: 'completed' }),
      step({ order: 3, label: 'Root Cause', state: 'active' }),
    ]
    const backfill = [
      step({ order: 1, label: 'Customer Impact', state: 'completed' }),
      step({ order: 2, label: 'Metric Query', state: 'completed', type: 'metric' }),
      step({ order: 3, label: 'Root Cause', state: 'active' }),
    ]

    const merged = mergeBackfilledSteps(current, backfill)

    expect(merged.map((s) => s.order)).toEqual([1, 2, 3])
    expect(merged[1].label).toBe('Metric Query')
  })

  it('is deduped: a step present on both sides at the same order never appears twice', () => {
    const current = [step({ order: 1, label: 'Customer Impact', state: 'completed' })]
    const backfill = [step({ order: 1, label: 'Customer Impact', state: 'completed' })]

    const merged = mergeBackfilledSteps(current, backfill)

    expect(merged).toHaveLength(1)
    expect(merged.filter((s) => s.order === 1)).toHaveLength(1)
  })

  it('is idempotent: applying the same backfill snapshot twice yields the same result both times', () => {
    const current = [step({ order: 1, label: 'Customer Impact', state: 'active' })]
    const backfill = [step({ order: 1, label: 'Customer Impact', state: 'completed' })]

    const once = mergeBackfilledSteps(current, backfill)
    const twice = mergeBackfilledSteps(once, backfill)

    expect(twice).toEqual(once)
  })

  it('does not regress an already-shown step: a stale (less-advanced) backfill state loses to the more-advanced current state', () => {
    // Simulates: a live SSE event already advanced this step to "completed"
    // before the reconnect backfill's slightly-earlier snapshot arrives
    // still showing "active" — the already-shown progress must not be undone.
    const current = [step({ order: 1, label: 'Metric Query', state: 'completed', type: 'metric' })]
    const backfill = [step({ order: 1, label: 'Metric Query', state: 'active', type: 'metric' })]

    const merged = mergeBackfilledSteps(current, backfill)

    expect(merged[0].state).toBe('completed')
  })

  it('applies real forward progress from the backfill (active -> completed)', () => {
    const current = [step({ order: 1, label: 'Metric Query', state: 'active', type: 'metric' })]
    const backfill = [step({ order: 1, label: 'Metric Query', state: 'completed', type: 'metric' })]

    const merged = mergeBackfilledSteps(current, backfill)

    expect(merged[0].state).toBe('completed')
  })

  it('preserves evidence/kbEntries already shown even when the winning side does not carry them', () => {
    const current: InvestigationStepDto[] = [
      {
        order: 1,
        key: 'k',
        label: 'Signal Correlation',
        state: 'completed',
        type: 'correlation',
        evidence: [{ kind: 'metric', query: 'http_requests_total', value: '412/min' }],
      },
    ]
    // Backfill wins on rank (completed >= completed) but its DTO in this
    // test simulates a snapshot without evidence populated — the value
    // already shown must not be dropped.
    const backfill: InvestigationStepDto[] = [
      { order: 1, key: 'k', label: 'Signal Correlation', state: 'completed', type: 'correlation' },
    ]

    const merged = mergeBackfilledSteps(current, backfill)

    expect(merged[0].evidence).toEqual([
      { kind: 'metric', query: 'http_requests_total', value: '412/min' },
    ])
  })

  it('carries evidence/kbEntries newly introduced by the backfill snapshot', () => {
    const current: InvestigationStepDto[] = [step({ order: 1, label: 'KB Query', type: 'kb' })]
    const backfill: InvestigationStepDto[] = [
      {
        order: 1,
        key: 'k',
        label: 'KB Query',
        state: 'completed',
        type: 'kb',
        kbEntries: [{ id: 'KB-1', title: 'runbook' }],
      },
    ]

    const merged = mergeBackfilledSteps(current, backfill)

    expect(merged[0].kbEntries).toEqual([{ id: 'KB-1', title: 'runbook' }])
  })

  it('sorts the merged result by order even when the backfill snapshot arrives out of order', () => {
    const current = [step({ order: 1 })]
    const backfill = [step({ order: 3 }), step({ order: 1 }), step({ order: 2 })]

    const merged = mergeBackfilledSteps(current, backfill)

    expect(merged.map((s) => s.order)).toEqual([1, 2, 3])
  })
})
