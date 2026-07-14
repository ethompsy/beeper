/**
 * legacy-label-rules.mjs
 *
 * Task 4.1 [T]: "migrated views contain no stray legacy labels."
 *
 * Shared scan engine + rule table for the legacy-label lint. Consumed by:
 *   - `scripts/check-legacy-labels.mjs` (CLI, `npm run lint:terms`)
 *   - `src/test/legacy-label-lint.test.ts` (the Vitest proof — runs in
 *     `npm test`, which IS part of the CI-safety gate)
 *
 * Lives outside `src/` deliberately (mirrors `scripts/verify-build.mjs`):
 * it is a dev-tool, not app source, so it must never be pulled into the
 * `build:lib` component-library bundle or the `build` app bundle, and it is
 * not subject to `tsconfig.app.json`'s typecheck surface.
 *
 * ── Rule provenance ─────────────────────────────────────────────────────
 * Every rule below is a "Current label -> Standardized label" row from
 * `docs/design/terminology-glossary.md` where the current (legacy) string
 * is a REAL RENAME (current !== standardized) — i.e. a term that must never
 * regress back into migrated view source. Rows marked "KEEP" in the
 * glossary (current === standardized) have no rule here by construction:
 * there is nothing to forbid.
 *
 * A few rename rows are DELIBERATELY EXCLUDED from lexical enforcement —
 * see `EXCLUDED_TERMS` below and the glossary's "Lint Coverage" section for
 * the full rationale (structural collisions that a plain-text scan cannot
 * safely resolve).
 */

import { readFileSync, readdirSync } from 'node:fs'
import { join, extname } from 'node:path'

/**
 * One "must not appear" rule. `pattern` is matched per source line
 * (case-sensitive unless the pattern itself sets the `i` flag) so a hit
 * also reports a useful line number.
 */
export const LEGACY_LABEL_RULES = [
  {
    id: 'phase-in-progress',
    pattern: /\bIn Progress\b/,
    legacy: 'In Progress',
    standardized: 'Investigating',
    glossaryRef: '§1 Investigation Phase',
  },
  {
    id: 'phase-awaiting-bare',
    // Negative lookahead so the CORRECT full phrase "Awaiting Confirmation"
    // never self-triggers this rule.
    pattern: /\bAwaiting\b(?!\s+Confirmation)/,
    legacy: 'Awaiting',
    standardized: 'Awaiting Confirmation',
    glossaryRef: '§1 Investigation Phase',
  },
  {
    id: 'urgency-card-heading',
    pattern: /\bEscalation Urgency\b/,
    legacy: 'Escalation Urgency',
    standardized: 'Urgency',
    glossaryRef: '§3 List Column Headers',
  },
  {
    id: 'detail-investigation-timeline',
    pattern: /\bInvestigation Timeline\b/,
    legacy: 'Investigation Timeline',
    standardized: 'Evidence Timeline',
    glossaryRef: '§4 Detail View Section Headers',
  },
  {
    id: 'detail-change-event-correlation',
    pattern: /\bChange Event Correlation\b/,
    legacy: 'Change Event Correlation',
    standardized: 'Change Events',
    glossaryRef: '§4 Detail View Section Headers',
  },
  {
    id: 'detail-investigation-feedback',
    pattern: /\bInvestigation Feedback\b/,
    legacy: 'Investigation Feedback',
    standardized: 'Feedback',
    glossaryRef: '§4 Detail View Section Headers',
  },
  {
    id: 'detail-investigation-resolution',
    pattern: /\bInvestigation Resolution\b/,
    legacy: 'Investigation Resolution',
    standardized: 'Resolution',
    glossaryRef: '§4 Detail View Section Headers',
  },
  {
    id: 'findings-knowledge-base-matches',
    pattern: /\bKnowledge Base Matches\b/,
    legacy: 'Knowledge Base Matches',
    standardized: 'KB Matches',
    glossaryRef: '§7 Findings Section Sub-Headers',
  },
  {
    id: 'findings-resolution-recommendations',
    pattern: /\bResolution Recommendations\b/,
    legacy: 'Resolution Recommendations',
    standardized: 'Recommendations',
    glossaryRef: '§7 Findings Section Sub-Headers',
  },
  {
    id: 'evidence-raw-signals-collected',
    // "Raw Signals (N collected)" -> "Raw Signals (N)" — N is interpolated,
    // so match the distinguishing "<count> collected)" fragment rather than
    // a fixed count.
    pattern: /\(\s*\d+\s*collected\s*\)/i,
    legacy: 'Raw Signals (N collected)',
    standardized: 'Raw Signals (N)',
    glossaryRef: '§8 Evidence Panel Sub-Headers',
  },
  {
    id: 'evidence-correlation-supporting-evidence',
    pattern: /\bCorrelation & Supporting Evidence\b/,
    legacy: 'Correlation & Supporting Evidence',
    standardized: 'Supporting Evidence',
    glossaryRef: '§8 Evidence Panel Sub-Headers',
  },
  {
    id: 'evidence-investigation-documentation',
    pattern: /\bInvestigation Documentation\b/,
    legacy: 'Investigation Documentation',
    standardized: 'Documentation',
    glossaryRef: '§8 Evidence Panel Sub-Headers',
  },
  {
    id: 'filter-sort-by',
    pattern: /\bSort by\b/i,
    legacy: 'Sort by',
    standardized: 'Sort',
    glossaryRef: '§12 Filter Panel Labels',
  },
  {
    id: 'filter-urgency-highest',
    pattern: /\bUrgency \(highest\)/,
    legacy: 'Urgency (highest)',
    standardized: 'Urgency ↓',
    glossaryRef: '§12 Filter Panel Labels',
  },
  {
    id: 'filter-all-statuses',
    pattern: /\bAll statuses\b/i,
    legacy: 'All statuses',
    standardized: 'All',
    glossaryRef: '§12 Filter Panel Labels',
  },
  {
    id: 'filter-all-states',
    pattern: /\bAll states\b/i,
    legacy: 'All states',
    standardized: 'All',
    glossaryRef: '§12 Filter Panel Labels',
  },
]

/**
 * Renames the glossary documents but does NOT lexically enforce here —
 * kept as a visible constant (not just prose in the .md) so a future editor
 * of this file sees the exclusion list next to the rule table it pairs
 * with. See `docs/design/terminology-glossary.md` §14 "Lint Coverage" for
 * the full per-term rationale.
 */
export const EXCLUDED_TERMS = [
  {
    term: 'Failed (job-phase)',
    reason:
      'Collides lexically with the intentionally-unrenamed workflow-state "Failed" (glossary OD-1 KEEP). Enforced structurally instead, via StatusBadge\'s separate `analysis-failed` vs `failed` variants.',
  },
  {
    term: 'Workflow State',
    reason:
      'Stays valid verbatim in the expanded filter panel (glossary OD-2 default); only the chip/column-header context should shorten to "State". Not statically distinguishable by a text scan.',
  },
  {
    term: 'config (step-type identifier)',
    reason:
      'Bare word is too ambiguous/common in source (file paths, "configuration", etc.) for a safe lexical rule. The `config`/`config_change` step type is not yet implemented in InvestigationStep — flagged as a build-time reminder in the density audit instead.',
  },
  {
    term: 'Correlated Signals',
    reason: 'OD-3 default keeps the current wording; not a rename.',
  },
]

const SCANNABLE_EXTENSIONS = new Set(['.ts', '.tsx'])

/** Directory names never descended into (test-only trees, not migrated UI copy). */
const EXCLUDED_DIR_NAMES = new Set(['test', 'node_modules'])

function isScannableFile(fileName) {
  if (!SCANNABLE_EXTENSIONS.has(extname(fileName))) return false
  if (fileName.endsWith('.stories.tsx')) return false
  if (/\.test\.tsx?$/.test(fileName)) return false
  return true
}

/**
 * Recursively collect scannable `.ts`/`.tsx` files under `rootDir`, skipping
 * `test/` subdirectories, Storybook stories, and `*.test.ts(x)` files (those
 * intentionally reference legacy terms for documentation/fixture purposes
 * and are not migrated UI copy).
 *
 * Manual walk (not `fs.readdirSync(dir, { recursive: true })`) so behavior
 * doesn't depend on a specific Node minor version's recursive-readdir
 * semantics — this repo targets Node 24, but the walk itself has no reason
 * to require it.
 */
export function collectFiles(rootDir) {
  const out = []

  function walk(dir) {
    let entries
    try {
      entries = readdirSync(dir, { withFileTypes: true })
    } catch {
      return
    }
    for (const entry of entries) {
      if (entry.isDirectory()) {
        if (EXCLUDED_DIR_NAMES.has(entry.name)) continue
        walk(join(dir, entry.name))
      } else if (entry.isFile() && isScannableFile(entry.name)) {
        out.push(join(dir, entry.name))
      }
    }
  }

  walk(rootDir)
  return out
}

/**
 * Scan a single file's contents for every `LEGACY_LABEL_RULES` match.
 * Returns one violation per (rule, matching line) — a file with the same
 * legacy term on two lines reports two violations.
 */
export function scanFile(filePath) {
  const content = readFileSync(filePath, 'utf-8')
  const lines = content.split('\n')
  const violations = []

  lines.forEach((line, index) => {
    for (const rule of LEGACY_LABEL_RULES) {
      if (rule.pattern.test(line)) {
        violations.push({
          id: rule.id,
          file: filePath,
          line: index + 1,
          legacy: rule.legacy,
          standardized: rule.standardized,
          glossaryRef: rule.glossaryRef,
          excerpt: line.trim(),
        })
      }
    }
  })

  return violations
}

/** Scan every file under `rootDir` (see `collectFiles`) and flatten violations. */
export function scanDirectory(rootDir) {
  return collectFiles(rootDir).flatMap((file) => scanFile(file))
}

/**
 * The migrated-view source scope for Task 4.1 (relative to `ui/frontend/`):
 * the React routes + the component-library primitives + the pure
 * investigation-domain logic modules that hold rendered label constants
 * (`STATUS_GROUP_LABELS`, `SEVERITY_LABELS`, etc). Mirrors the task's own
 * scope statement ("routes/**" + "src/lib" components).
 */
export const SCAN_ROOTS = [
  'src/routes',
  'src/lib/components',
  'src/lib/investigations',
]

export function formatViolations(violations) {
  if (violations.length === 0) return 'no violations'
  return violations
    .map(
      (v) =>
        `${v.file}:${v.line} — found legacy label "${v.legacy}" (${v.glossaryRef}); use "${v.standardized}" instead\n    ${v.excerpt}`,
    )
    .join('\n')
}
