/**
 * format-mttr.ts — pure MTTR duration formatting (Task 5.4).
 *
 * Deliberately mirrors `format_mttr()` in `ui/beeper_ui/routes/investigations.py`
 * output-for-output (same thresholds, same rounding via `Math.floor`, same
 * "Xh Ym"-only-when-Y>0" collapsing). The JSON MTTR API
 * (`GET /api/v1/metrics/mttr`) intentionally returns raw `avg_mttr_seconds`
 * integers rather than pre-formatted strings — same "React formats, backend
 * supplies raw data" split the JSON list API already uses for timestamps —
 * so this is a necessary, not a duplicated, client-side implementation.
 * Test cases in `src/lib/test/format-mttr.test.ts` are copied 1:1 from
 * `ui/tests/test_investigation_routes.py`'s `TestFormatMttr` class to keep
 * the two implementations provably in sync.
 */
export function formatMttr(seconds: number | null | undefined): string {
  if (seconds == null) return 'N/A'
  if (seconds < 60) return '<1m'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600)
    const mins = Math.floor((seconds % 3600) / 60)
    return mins ? `${hours}h ${mins}m` : `${hours}h`
  }
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  return hours ? `${days}d ${hours}h` : `${days}d`
}

/**
 * Format a raw `resolution_outcome` value (e.g. `"not_an_issue"`) for the
 * drilldown table's Outcome column. Mirrors the Jinja drilldown template's
 * transform exactly — `{{ inv.resolution_outcome | default('') | replace('_',
 * ' ') | title }}` (`ui/beeper_ui/templates/metrics/_drilldown.html`) — a
 * plain string transform, not a lookup table (unlike
 * `OUTCOME_LABELS`/`ACCURACY_LABELS` in `investigations.py`, which serve a
 * different, human-authored-copy context on the resolution form).
 */
export function formatResolutionOutcome(outcome: string | null | undefined): string {
  if (!outcome) return ''
  return outcome
    .split('_')
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(' ')
}
