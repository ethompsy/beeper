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
