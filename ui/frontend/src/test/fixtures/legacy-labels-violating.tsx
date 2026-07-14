/**
 * LINT FIXTURE — deliberately violating component (Task 4.1).
 *
 * This file is NOT compiled into the production bundle and lives outside
 * the legacy-label lint's own scan scope (`SCAN_ROOTS` in
 * `scripts/legacy-label-rules.mjs` only covers `src/routes`,
 * `src/lib/components`, `src/lib/investigations` — never `src/test`).
 *
 * It exists solely so `src/test/legacy-label-lint.test.ts` can assert the
 * scanner actually FAILS (reports violations) on planted legacy strings,
 * proving the lint isn't a no-op. Each line below intentionally reproduces
 * one "current" (legacy) label from docs/design/terminology-glossary.md
 * that should never appear as UI copy in a migrated view.
 */

export function LegacyBadgeExample() {
  return (
    <div>
      {/* §1 — legacy job-phase label, standardized: "Investigating" */}
      <span data-slot="status-badge">In Progress</span>
      {/* §1 — truncated legacy label, standardized: "Awaiting Confirmation" */}
      <span data-slot="status-badge">Awaiting</span>
      {/* §4 — legacy section heading, standardized: "Evidence Timeline" */}
      <h3>Investigation Timeline</h3>
      {/* §7 — legacy sub-header, standardized: "KB Matches" */}
      <h4>Knowledge Base Matches</h4>
    </div>
  )
}
