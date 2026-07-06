/**
 * problem-state.ts — plain-language "problem state" mapping from the raw
 * Investigation CRD `condition` string (Task 2.4, docs/reqs/main.md FR47).
 *
 * FR47: "Problem state is rendered in standardized plain language. The first
 * increment uses a per-metric heuristic mapping in the frontend (`{metric
 * pattern → template}`, e.g. `http_*_5xx*` → 'HTTP {code} error rate elevated
 * ({value}%)'); when no pattern matches it falls back to the raw anomaly
 * description from the investigation record."
 *
 * Glossary note (docs/design/terminology-glossary.md OD-4 / §3 / §5): the RAW
 * `condition` field keeps its existing label "Condition" (not renamed) — this
 * module produces a DERIVED, separate plain-language value that coexists
 * alongside it. In the list row it is a distinct fact from Task 2.3's
 * "affected component" (FR45/46 lists "component" and "problem state" as two
 * separate first-seconds facts); in the detail view it fills the `h2`
 * "problem statement" role the glossary's §5 rendering-intent note describes
 * for `SummaryHeader`'s `problemState` slot.
 *
 * Condition string shapes this mapping targets (verified against source, not
 * guessed — mirrors `derive-component.ts`'s research):
 *   - Demo/static fixtures (`ui/demo_ui.py`), already near-plain-language:
 *       "High error rate on /checkout endpoint — 5xx at 18%"
 *       "Elevated latency on /oauth/token — p99 > 5s"
 *       "Memory usage above 90% on catalog pods"
 *       "Increased queue depth on email-worker"
 *   - Runtime metric-spike/drop (`operator/src/detection/metrics.rs`):
 *       "Metric {name} spike: {observed}, expected {expected} ± {stddev}"
 *   - Runtime log-based error rate (`operator/src/detection/logs.rs`):
 *       "Error rate spike: {n} errors in window, expected {expected} ± {stddev}"
 *   - Runtime SLO burn-rate (`operator/src/slo/burn_rate.rs`):
 *       "SLO burn rate alert: {service} burn rate {x} exceeds {y}x threshold ..."
 *   - Machine (snake_case) tokens that may appear standalone or embedded in
 *     other systems' condition text: `high_error_rate`, `high_latency`.
 *
 * Ordered `{pattern, template}` rules — first match wins, same shape FR47
 * itself prescribes (`http_*_5xx*` → template) and the same "ordered rule
 * list with a raw fallback" structure `derive-component.ts` established for
 * Task 2.3, so both derivations stay consistent siblings.
 */

interface ProblemStateRule {
  /** Human-readable name for the rule (debugging / test readability only). */
  name: string
  pattern: RegExp
  /**
   * Build the plain-language sentence from the regex match. Receives the
   * `RegExpExecArray` so templates can pull captured values (e.g. a percent
   * or p99 figure) straight out of the source condition text.
   */
  template: (match: RegExpExecArray, condition: string) => string
}

/** Pulls a trailing/embedded numeric-ish value (e.g. "18%", "> 5s", "90%") near a keyword, for interpolation into a template. */
function extractValue(condition: string, near: RegExp): string | null {
  const match = near.exec(condition)
  return match ? match[1].trim() : null
}

const PERCENT_RE = /(\d+(?:\.\d+)?\s*%)/
const LATENCY_RE = /(p99[^,;.]*?\d[^,;.]*|(?:>|>=|above|over)\s*\d+(?:\.\d+)?\s*(?:ms|s|sec|seconds)?)/i

const PROBLEM_STATE_RULES: ReadonlyArray<ProblemStateRule> = [
  // ── HTTP/gRPC 5xx error-rate signals ──────────────────────────────────
  // Covers the demo fixture ("High error rate on /checkout endpoint — 5xx at
  // 18%"), the machine token `high_error_rate`, and any condition text that
  // mentions both an HTTP/RPC family token and "5xx"/"error rate".
  {
    name: 'http-5xx-error-rate',
    pattern: /5xx|http[_.].*5xx|high_error_rate/i,
    template: (_match, condition) => {
      const value = extractValue(condition, PERCENT_RE)
      return value ? `HTTP 5xx error rate elevated (${value})` : 'HTTP 5xx error rate elevated'
    },
  },
  // ── Generic elevated error rate (no explicit "5xx", e.g. logs.rs'
  // "Error rate spike: {n} errors in window, expected {e} ± {sd}") ────────
  {
    name: 'generic-error-rate',
    pattern: /error rate spike|error rate/i,
    template: (_match, condition) => {
      const countMatch = /(\d+)\s+errors?\s+in\s+window/i.exec(condition)
      return countMatch
        ? `Elevated error rate (${countMatch[1]} errors in window)`
        : 'Elevated error rate'
    },
  },
  // ── Latency / p99 ──────────────────────────────────────────────────────
  // Covers the demo fixture ("Elevated latency on /oauth/token — p99 > 5s")
  // and the machine token `high_latency`.
  {
    name: 'latency',
    pattern: /latency|p99|high_latency/i,
    template: (_match, condition) => {
      const value = extractValue(condition, LATENCY_RE)
      return value ? `Elevated latency (${value})` : 'Elevated latency'
    },
  },
  // ── Memory usage ───────────────────────────────────────────────────────
  // Covers the demo fixture ("Memory usage above 90% on catalog pods") and
  // metrics.rs-shaped memory metric names (`Metric process_runtime_memory
  // spike: ...`).
  {
    name: 'memory',
    pattern: /memory|mem_usage|90%/i,
    template: (_match, condition) => {
      const value = extractValue(condition, PERCENT_RE)
      return value ? `High memory usage (${value})` : 'High memory usage'
    },
  },
  // ── CPU utilization ────────────────────────────────────────────────────
  // Metrics.rs-shaped CPU metric names (`Metric cpu_usage spike: ...`) —
  // covers the `high-cpu` demo fault scenario (see derive-component.ts).
  {
    name: 'cpu',
    pattern: /\bcpu[_\s]/i,
    template: (_match, condition) => {
      const observedMatch = /:\s*([\d.]+),\s*expected/i.exec(condition)
      return observedMatch
        ? `High CPU usage (${observedMatch[1]})`
        : 'High CPU usage'
    },
  },
  // ── Queue depth / message backlog ──────────────────────────────────────
  // Covers the demo fixture ("Increased queue depth on email-worker") and
  // kafka/queue-named metrics.rs metric spikes.
  {
    name: 'queue-depth',
    pattern: /queue depth|queue|kafka/i,
    template: () => 'Increased queue depth',
  },
  // ── SLO burn-rate alerts (operator/src/slo/burn_rate.rs) ───────────────
  {
    name: 'slo-burn-rate',
    pattern: /SLO burn rate alert/i,
    template: (_match, condition) => {
      const rateMatch = /burn rate\s+([\d.]+x)/i.exec(condition)
      return rateMatch
        ? `SLO burn rate elevated (${rateMatch[1]})`
        : 'SLO burn rate elevated'
    },
  },
]

/**
 * Derive a standardized plain-language "problem state" sentence from an
 * investigation's raw `condition` string (FR47).
 *
 * Pure function, no I/O — safe to unit test directly and to call from both
 * the list row-view-model (Task 2.2/2.3's designated seam) and the detail
 * view's `SummaryHeader.problemState` slot.
 *
 * @param condition Raw `condition` field from the Investigation JSON. May be
 *   `null`/empty, an already-plain-language demo string, a runtime detector's
 *   formatted string, or free-text this heuristic doesn't recognize.
 * @returns The first matching rule's rendered template, or — critically, per
 *   FR47 — the raw `condition` text itself when no rule matches. Only
 *   returns an empty/placeholder string when `condition` itself is
 *   null/blank (never silently blank otherwise).
 */
export function deriveProblemState(condition: string | null | undefined): string {
  if (!condition) return 'No problem state available'
  const trimmed = condition.trim()
  if (!trimmed) return 'No problem state available'

  for (const rule of PROBLEM_STATE_RULES) {
    const match = rule.pattern.exec(trimmed)
    if (match) return rule.template(match, trimmed)
  }

  // No pattern matched — fall back to the raw anomaly description verbatim
  // (FR47's explicit fallback), never blank.
  return trimmed
}
