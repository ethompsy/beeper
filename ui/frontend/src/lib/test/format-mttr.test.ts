/**
 * format-mttr.test.ts
 *
 * `formatMttr` cases are copied 1:1 from `TestFormatMttr` in
 * `ui/tests/test_investigation_routes.py` (the Python `format_mttr()` this
 * mirrors) so a change to one implementation's behavior is provably
 * detectable against the other's expected outputs.
 */
import { describe, it, expect } from 'vitest'
import { formatMttr, formatResolutionOutcome } from '../metrics/format-mttr'

describe('formatMttr', () => {
  it('formats null/undefined as "N/A"', () => {
    expect(formatMttr(null)).toBe('N/A')
    expect(formatMttr(undefined)).toBe('N/A')
  })

  it('formats sub-minute durations as "<1m"', () => {
    expect(formatMttr(30)).toBe('<1m')
    expect(formatMttr(0)).toBe('<1m')
  })

  it('formats minute durations', () => {
    expect(formatMttr(300)).toBe('5m')
    expect(formatMttr(3420)).toBe('57m')
  })

  it('formats hour durations, omitting minutes when zero', () => {
    expect(formatMttr(3600)).toBe('1h')
    expect(formatMttr(7500)).toBe('2h 5m')
  })

  it('formats day durations, omitting hours when zero', () => {
    expect(formatMttr(86400)).toBe('1d')
    expect(formatMttr(97200)).toBe('1d 3h')
  })
})

describe('formatResolutionOutcome', () => {
  it('title-cases and replaces underscores with spaces', () => {
    expect(formatResolutionOutcome('not_an_issue')).toBe('Not An Issue')
    expect(formatResolutionOutcome('resolved')).toBe('Resolved')
    expect(formatResolutionOutcome('escalated')).toBe('Escalated')
  })

  it('returns an empty string for null/undefined/empty input', () => {
    expect(formatResolutionOutcome(null)).toBe('')
    expect(formatResolutionOutcome(undefined)).toBe('')
    expect(formatResolutionOutcome('')).toBe('')
  })
})
