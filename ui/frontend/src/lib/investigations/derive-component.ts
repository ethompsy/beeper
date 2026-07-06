/**
 * derive-component.ts — best-effort "affected component" derivation from the
 * Investigation CRD's `condition` string (Task 2.3, docs/reqs/main.md R5/D7).
 *
 * There is no dedicated `component` field on the Investigation CRD
 * (`operator/src/crds/investigation.rs` — `InvestigationSpec` has `condition`,
 * `service`, `severity`, timestamps, but nothing naming a subsystem). The
 * anomalous-signal subsystem (metric family / endpoint / container) is only
 * observable today via the free-text `condition` string that the detectors in
 * `operator/src/detection/{metrics,logs}.rs` and `operator/src/slo/burn_rate.rs`
 * format. This module heuristically parses that text back into a short,
 * human-readable component label — mirroring FR47's own per-pattern heuristic
 * approach for problem-state text (a `{pattern → label}` table with a raw
 * fallback), rather than inventing a stricter parser the source strings don't
 * actually support.
 *
 * Condition string shapes this derivation targets (verified against the
 * detector source, not guessed):
 *   - Metric-based:     "Metric {name} spike: {v}, expected {e} ± {sd}"
 *                        "Metric {name} drop: {v}, expected {e} ± {sd}"
 *                        (`operator/src/detection/metrics.rs` `AnomalyEvent.condition`)
 *   - Log-based:         "Error rate spike: {n} errors in window, expected ..."
 *                        (`operator/src/detection/logs.rs` — no metric/endpoint
 *                        name embedded, only an error-rate fact)
 *   - SLO burn-rate:     "SLO burn rate alert: {service} burn rate {x} exceeds ..."
 *                        (`operator/src/slo/burn_rate.rs`)
 *
 * The demo fault scenarios (`make demo-fault FAULT=...` in the repo Makefile:
 * payment-failure, cart-failure, kafka-problems, slow-images, high-cpu) surface
 * through these same three shapes — e.g. `high-cpu` (adHighCpu flag) trips a
 * `cpu*`-named metric spike, `payment-failure`/`cart-failure` trip either an
 * HTTP/gRPC error-rate metric spike or the log-based error-rate detector,
 * `kafka-problems` trips a queue-related metric. There is no separate
 * "scenario name" available at render time — only the resulting condition
 * text — so the mapping below is keyed on metric-name family, not fault name.
 *
 * Unknown/unparseable input degrades gracefully to `null` (component omitted)
 * rather than guessing or crashing — `InvestigationCard`'s `component` slot
 * already renders nothing when given a falsy value (Task 2.2).
 */

/** Ordered metric-name-family -> component label rules (first match wins). */
const METRIC_FAMILY_RULES: ReadonlyArray<{ pattern: RegExp; label: string }> = [
  // HTTP / gRPC / RPC request handling (OTel semantic-convention metric names:
  // http_server_request_duration_seconds, http_client_request_duration_seconds,
  // rpc_server_duration, *_requests_total, etc.)
  { pattern: /^(?:http|rpc|grpc)[_.]/i, label: 'HTTP/RPC request handling' },
  { pattern: /request/i, label: 'HTTP/RPC request handling' },
  // Database / persistence calls (db_client_operation_duration_seconds, sql*, database*)
  { pattern: /^(?:db|sql|database)[_.]/i, label: 'Database calls' },
  // Messaging / queue backlog (kafka*, queue*, message*) — covers the
  // `kafka-problems` demo fault.
  { pattern: /kafka|queue|message/i, label: 'Message queue' },
  // CPU utilization (cpu_usage, cpu, system_cpu_utilization, container_cpu_*,
  // otelcol_process_cpu_seconds_total) — covers the `high-cpu` demo fault.
  { pattern: /cpu/i, label: 'CPU / compute resources' },
  // Memory (memory_usage, *_mem_*, process_runtime_*_memory)
  { pattern: /mem(?:ory)?/i, label: 'Memory usage' },
  // Container/pod-level restarts or resource pressure
  { pattern: /container|pod/i, label: 'Container resources' },
]

/** Humanize a raw metric name we don't recognize a family for: `cpu_usage_ratio` -> "Cpu usage ratio". */
function humanizeMetricName(name: string): string {
  const words = name
    .replace(/[_.]+/g, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
  if (words.length === 0) return name
  return words
    .map((word, index) => (index === 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word))
    .join(' ')
}

/** Map a metric name to a component label via the family rules, falling back to a humanized form of the raw name. */
function labelForMetricName(name: string): string {
  for (const rule of METRIC_FAMILY_RULES) {
    if (rule.pattern.test(name)) return rule.label
  }
  return humanizeMetricName(name)
}

/** Matches `operator/src/detection/metrics.rs`: `Metric {name} spike|drop: ...`. */
const METRIC_CONDITION_RE = /^Metric\s+(\S+)\s+(?:spike|drop)\s*:/i

/** Matches `operator/src/detection/logs.rs`: `Error rate spike: ...`. */
const ERROR_RATE_CONDITION_RE = /^Error rate spike\s*:/i

/** Matches `operator/src/slo/burn_rate.rs`: `SLO burn rate alert: ...`. */
const SLO_BURN_RATE_CONDITION_RE = /^SLO burn rate alert\s*:/i

/**
 * Derive a best-effort "affected component" label from an investigation's raw
 * `condition` string.
 *
 * Pure function, no I/O — safe to unit test directly and to call from the
 * list row-view-model (Task 2.2's designated seam).
 *
 * @param condition Raw `condition` field from the Investigation JSON (may be
 *   `null`/empty/free-text the detectors never produced, e.g. a manually
 *   created CRD or a future detector shape this heuristic doesn't know about).
 * @returns A short human-readable component label, or `null` when the input
 *   is missing or doesn't match any known condition shape (graceful
 *   degradation — never throws, never fabricates a label from nothing).
 */
export function deriveComponent(condition: string | null | undefined): string | null {
  if (!condition) return null
  const trimmed = condition.trim()
  if (!trimmed) return null

  const metricMatch = METRIC_CONDITION_RE.exec(trimmed)
  if (metricMatch) {
    return labelForMetricName(metricMatch[1])
  }

  if (ERROR_RATE_CONDITION_RE.test(trimmed)) {
    return 'Request error rate'
  }

  if (SLO_BURN_RATE_CONDITION_RE.test(trimmed)) {
    return 'SLO burn rate'
  }

  // Unparseable / unrecognized shape (e.g. free-text condition from a
  // manually created CRD, or a future detector this heuristic doesn't know
  // about yet) — degrade gracefully rather than guess.
  return null
}
