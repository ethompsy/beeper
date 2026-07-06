/**
 * problem-state.test.ts
 *
 * Task 2.4 AC [T] — "Plain language for the demo signals — cover payment /
 * cart / cpu / latency / memory patterns" and "No pattern match -> fall back
 * to the raw anomaly description ... never blank (FR47)."
 *
 * Condition string fixtures cover both the static demo fixtures
 * (`ui/demo_ui.py`) and the runtime detector shapes
 * (`operator/src/detection/{metrics,logs}.rs`,
 * `operator/src/slo/burn_rate.rs`), plus the snake_case machine tokens
 * (`high_error_rate`, `high_latency`) called out in the task brief.
 */
import { describe, it, expect } from 'vitest'
import { deriveProblemState } from '../investigations/problem-state'

describe('deriveProblemState — demo fixture condition strings (ui/demo_ui.py)', () => {
  it('maps the payment/checkout 5xx error-rate fixture to a plain-language HTTP 5xx sentence with the percent value', () => {
    const condition = 'High error rate on /checkout endpoint — 5xx at 18%'
    expect(deriveProblemState(condition)).toBe('HTTP 5xx error rate elevated (18%)')
  })

  it('maps the oauth/token latency fixture to a plain-language latency sentence with the p99 value', () => {
    const condition = 'Elevated latency on /oauth/token — p99 > 5s'
    expect(deriveProblemState(condition)).toBe('Elevated latency (p99 > 5s)')
  })

  it('maps the catalog-pods memory fixture to a plain-language memory sentence with the percent value', () => {
    const condition = 'Memory usage above 90% on catalog pods'
    expect(deriveProblemState(condition)).toBe('High memory usage (90%)')
  })

  it('maps the email-worker queue-depth fixture to a plain-language queue-depth sentence', () => {
    const condition = 'Increased queue depth on email-worker'
    expect(deriveProblemState(condition)).toBe('Increased queue depth')
  })
})

describe('deriveProblemState — cart-failure-style error-rate conditions', () => {
  it('maps a cart-service 5xx condition the same way as the payment fixture', () => {
    const condition = 'High error rate on /cart endpoint — 5xx at 22%'
    expect(deriveProblemState(condition)).toBe('HTTP 5xx error rate elevated (22%)')
  })
})

describe('deriveProblemState — runtime metric-spike/drop conditions (operator/src/detection/metrics.rs shape)', () => {
  it('maps a cpu-named metric spike (high-cpu scenario) to a plain-language CPU sentence with the observed value', () => {
    const condition = 'Metric cpu_usage spike: 92.0, expected 15.0 ± 3.0'
    expect(deriveProblemState(condition)).toBe('High CPU usage (92.0)')
  })

  it('maps an otelcol infra cpu metric spike to a plain-language CPU sentence', () => {
    const condition = 'Metric otelcol_process_cpu_seconds_total spike: 5.0, expected 1.0 ± 0.2'
    expect(deriveProblemState(condition)).toBe('High CPU usage (5.0)')
  })

  it('maps a memory-named metric spike to a plain-language memory sentence (no percent value available -> unparameterized template)', () => {
    const condition = 'Metric process_runtime_memory spike: 512.0, expected 128.0 ± 20.0'
    expect(deriveProblemState(condition)).toBe('High memory usage')
  })

  it('maps a kafka-named metric spike (kafka-problems scenario) to the queue-depth sentence', () => {
    const condition = 'Metric kafka_consumer_lag spike: 500.0, expected 10.0 ± 2.0'
    expect(deriveProblemState(condition)).toBe('Increased queue depth')
  })
})

describe('deriveProblemState — runtime log-based error-rate conditions (operator/src/detection/logs.rs shape)', () => {
  it('maps a generic (non-HTTP-labeled) error-rate-spike condition to a plain-language sentence with the error count', () => {
    const condition = 'Error rate spike: 47 errors in window, expected 2.1 ± 1.0'
    expect(deriveProblemState(condition)).toBe('Elevated error rate (47 errors in window)')
  })
})

describe('deriveProblemState — SLO burn-rate conditions (operator/src/slo/burn_rate.rs shape)', () => {
  it('maps an SLO burn-rate-alert condition to a plain-language sentence with the burn-rate multiplier', () => {
    const condition =
      'SLO burn rate alert: checkout burn rate 14.4x exceeds 14.4x threshold (critical). ' +
      'Short window (1h) burn rate: 14.4x, Long window (6h) burn rate: 14.4x. Budget remaining: 0.0%'
    expect(deriveProblemState(condition)).toBe('SLO burn rate elevated (14.4x)')
  })
})

describe('deriveProblemState — snake_case machine tokens', () => {
  it('maps a standalone `high_error_rate` token to the HTTP 5xx sentence (unparameterized, no percent value present)', () => {
    expect(deriveProblemState('high_error_rate')).toBe('HTTP 5xx error rate elevated')
  })

  it('maps a standalone `high_latency` token to the latency sentence (unparameterized, no p99/threshold value present)', () => {
    expect(deriveProblemState('high_latency')).toBe('Elevated latency')
  })
})

describe('deriveProblemState — no pattern match falls back to the raw condition (FR47), never blank', () => {
  it('returns the raw condition text verbatim when it matches no known pattern', () => {
    const condition = 'Manually created investigation for testing'
    expect(deriveProblemState(condition)).toBe('Manually created investigation for testing')
  })

  it('returns the raw condition text verbatim for an already-plain-language string that happens not to match a rule', () => {
    const condition = 'Unexpected checkout conversion ratio drift'
    expect(deriveProblemState(condition)).toBe('Unexpected checkout conversion ratio drift')
  })

  it('falls back rather than throwing for an unrecognized metrics.rs-shaped condition (metric family this heuristic does not know)', () => {
    const condition = 'Metric checkout_conversion_ratio spike: 0.9, expected 0.5 ± 0.1'
    expect(deriveProblemState(condition)).toBe(
      'Metric checkout_conversion_ratio spike: 0.9, expected 0.5 ± 0.1',
    )
  })

  it('never returns a blank string for non-empty unrecognized input', () => {
    expect(deriveProblemState('xyz')).toBe('xyz')
    expect(deriveProblemState('xyz').length).toBeGreaterThan(0)
  })
})

describe('deriveProblemState — graceful degradation on missing/empty input (never blank, FR47)', () => {
  it('returns a non-blank placeholder for null condition', () => {
    const result = deriveProblemState(null)
    expect(result).toBeTruthy()
    expect(result.length).toBeGreaterThan(0)
  })

  it('returns a non-blank placeholder for undefined condition', () => {
    const result = deriveProblemState(undefined)
    expect(result).toBeTruthy()
  })

  it('returns a non-blank placeholder for an empty string', () => {
    const result = deriveProblemState('')
    expect(result).toBeTruthy()
  })

  it('returns a non-blank placeholder for a whitespace-only string', () => {
    const result = deriveProblemState('   ')
    expect(result).toBeTruthy()
  })

  it('does not throw on adversarial/malformed input', () => {
    expect(() => deriveProblemState('Metric')).not.toThrow()
    expect(() => deriveProblemState('Metric :')).not.toThrow()
    expect(deriveProblemState('Metric')).toBe('Metric')
  })
})
