/**
 * derive-component.test.ts
 *
 * Task 2.3 AC [T] — "Component is derived from representative demo `condition`
 * strings ... infer the anomalous subsystem" and "Unknown/unparseable input
 * degrades gracefully — no crash; a sensible fallback."
 *
 * Condition string fixtures mirror the exact `format!` shapes the detectors
 * produce (`operator/src/detection/metrics.rs`, `operator/src/detection/logs.rs`,
 * `operator/src/slo/burn_rate.rs`), and metric names realistic for the demo
 * fault scenarios in the repo Makefile (`make demo-fault FAULT=payment-failure
 * | cart-failure | kafka-problems | high-cpu`).
 */
import { describe, it, expect } from 'vitest'
import { deriveComponent } from '../investigations/derive-component'

describe('deriveComponent — metric-based conditions (operator/src/detection/metrics.rs shape)', () => {
  it('maps an HTTP request-duration metric spike (payment-failure-style scenario) to HTTP/RPC request handling', () => {
    const condition =
      'Metric http_server_request_duration_seconds_count spike: 842.0, expected 120.0 ± 15.0'
    expect(deriveComponent(condition)).toBe('HTTP/RPC request handling')
  })

  it('maps an HTTP client request-duration metric drop (cart-failure-style scenario) to HTTP/RPC request handling', () => {
    const condition = 'Metric http_client_request_duration_seconds drop: 0.0, expected 45.0 ± 5.0'
    expect(deriveComponent(condition)).toBe('HTTP/RPC request handling')
  })

  it('maps a gRPC/rpc-named metric spike to HTTP/RPC request handling', () => {
    const condition = 'Metric rpc_server_duration spike: 900.0, expected 100.0 ± 10.0'
    expect(deriveComponent(condition)).toBe('HTTP/RPC request handling')
  })

  it('maps a cpu-named metric spike (high-cpu scenario, adHighCpu flag) to CPU / compute resources', () => {
    const condition = 'Metric cpu_usage spike: 92.0, expected 15.0 ± 3.0'
    expect(deriveComponent(condition)).toBe('CPU / compute resources')
  })

  it('maps an otelcol infra cpu metric spike to CPU / compute resources', () => {
    const condition = 'Metric otelcol_process_cpu_seconds_total spike: 5.0, expected 1.0 ± 0.2'
    expect(deriveComponent(condition)).toBe('CPU / compute resources')
  })

  it('maps a memory-named metric spike to Memory usage', () => {
    const condition = 'Metric process_runtime_memory spike: 512.0, expected 128.0 ± 20.0'
    expect(deriveComponent(condition)).toBe('Memory usage')
  })

  it('maps a database-named metric spike to Database calls', () => {
    const condition = 'Metric db_client_operation_duration_seconds spike: 3.2, expected 0.4 ± 0.1'
    expect(deriveComponent(condition)).toBe('Database calls')
  })

  it('maps a kafka-named metric spike (kafka-problems scenario) to Message queue', () => {
    const condition = 'Metric kafka_consumer_lag spike: 500.0, expected 10.0 ± 2.0'
    expect(deriveComponent(condition)).toBe('Message queue')
  })

  it('maps a container-named metric drop to Container resources', () => {
    const condition = 'Metric container_restarts_total drop: 0.0, expected 2.0 ± 0.5'
    expect(deriveComponent(condition)).toBe('Container resources')
  })

  it('falls back to a humanized form of an unrecognized metric name rather than a generic label', () => {
    const condition = 'Metric checkout_conversion_ratio spike: 0.9, expected 0.5 ± 0.1'
    expect(deriveComponent(condition)).toBe('Checkout conversion ratio')
  })
})

describe('deriveComponent — log-based error-rate conditions (operator/src/detection/logs.rs shape)', () => {
  it('maps an error-rate-spike condition (payment-failure/cart-failure-style scenario) to Request error rate', () => {
    const condition = 'Error rate spike: 47 errors in window, expected 2.1 ± 1.0'
    expect(deriveComponent(condition)).toBe('Request error rate')
  })
})

describe('deriveComponent — SLO burn-rate conditions (operator/src/slo/burn_rate.rs shape)', () => {
  it('maps an SLO burn-rate-alert condition to SLO burn rate', () => {
    const condition =
      'SLO burn rate alert: checkout burn rate 14.4x exceeds 14.4x threshold (critical). ' +
      'Short window (1h) burn rate: 14.4x, Long window (6h) burn rate: 14.4x. Budget remaining: 0.0%'
    expect(deriveComponent(condition)).toBe('SLO burn rate')
  })
})

describe('deriveComponent — graceful degradation on unknown/unparseable input', () => {
  it('returns null for null condition', () => {
    expect(deriveComponent(null)).toBeNull()
  })

  it('returns null for undefined condition', () => {
    expect(deriveComponent(undefined)).toBeNull()
  })

  it('returns null for an empty string', () => {
    expect(deriveComponent('')).toBeNull()
  })

  it('returns null for a whitespace-only string', () => {
    expect(deriveComponent('   ')).toBeNull()
  })

  it('returns null for free-text that matches none of the known detector shapes', () => {
    expect(deriveComponent('Manually created investigation for testing')).toBeNull()
  })

  it('does not throw on adversarial/malformed input', () => {
    expect(() => deriveComponent('Metric')).not.toThrow()
    expect(() => deriveComponent('Metric :')).not.toThrow()
    expect(deriveComponent('Metric')).toBeNull()
  })
})
