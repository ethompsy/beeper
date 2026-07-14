# Terminology Glossary & Visual-Density Audit — Investigation List & Detail Views

**Status: FULL (Task 4.1) — extends the Task 1.8 draft now that the real list/detail React views exist. `[H]` sign-off is PENDING USER APPROVAL** (FR52). Task 1.8's decisions — including the OD-1..OD-5 resolutions and the "Condition"/job-phase-vs-workflow-"Failed" treatment — are preserved verbatim below; nothing in this pass reopens them.
**Scope:** Investigation list view + investigation detail view only (same scope as 1.8).
**Purpose (1.8, unchanged):** Produce the terminology standardization artifact required by FR52 before the React implementations of the list (Task 2.2) and detail (Task 2.5) views were built. Every §1–§13 entry is derived from the literal label strings in the Jinja templates (the authoritative source of *pre-migration* copy) and cross-checked against the Rust CRD enums in `operator/src/crds/investigation.rs`.
**Purpose (4.1, this pass):** Now that the list (`InvestigationListPage`) and detail (`InvestigationDetailPage`) React views + their `src/lib/components/*` primitives are actually built and merged (Milestones 1.1–1.3), this pass (1) self-reviews every 1.8 entry against the *shipped* component source — reading the rendered JSX/props/label tables directly (this codebase's established verification convention: Tailwind classes and literal label strings **are** the contract, per the client-side test doctrine already in force for this repo) rather than against the pre-implementation Jinja-only prediction; (2) reconciles the handful of places where shipped reality has moved past the 1.8 draft (§9 step types); (3) adds §14 documenting exactly which renames are lexically enforced by the new legacy-label lint and which are deliberately excluded (with rationale); and (4) adds §15, the FR52 visual-density audit, naming the specific elements to remove/de-emphasize per view — or confirming none — grounded in the same shipped source. No 4.2 restyling happens in this task; density findings are recorded for that follow-up.

---

## How to read this table

- **Current label** — the string a user sees today in the rendered HTML (extracted from template text, not CSS class names or enum values).
- **Standardized label** — proposed copy for the React view.
- **Where it appears** — template file(s) and UI location.
- **Rationale** — why it changes (or stays). "KEEP" means the current term is already clear SRE language; no rename recommended.

---

## 1. Investigation Phase (job-level lifecycle)

The CRD defines `InvestigationPhase` as the low-level Kubernetes Job phase: `Pending | Running | AwaitingConfirmation | Completed | Failed`. The templates surface these via the `inv.status` field, with the following display labels:

| Current label | Standardized label | Where it appears | Rationale |
|---|---|---|---|
| **In Progress** | **Investigating** | `components/status.html` status_badge; `_list_content.html` legacy table row; `_filter_panel.html` status filter dropdown | The underlying enum value is `investigating`; the display label "In Progress" is generic. "Investigating" names the actual SRE activity and matches the `WorkflowState.Investigating` business concept, eliminating split vocabulary between the two level systems. |
| **Awaiting** | **Awaiting Confirmation** | `components/status.html` status_badge | Truncated in the badge macro but the filter dropdown already shows the full form. Standardize to the full phrase so the badge is self-explanatory without tooltip. |
| **Awaiting Confirmation** | **Awaiting Confirmation** | `_filter_panel.html` status dropdown | KEEP — already the full form. |
| **Completed** | **Completed** | `components/status.html`; `_filter_panel.html`; `_list_content.html` | KEEP — clear and terminal; matches the CRD enum. |
| **Failed** *(phase)* | **Analysis Failed** | `components/status.html`; `_list_content.html`; `_filter_panel.html` | RENAME (user, OD-1) — the investigator job errored; distinguishes the job-phase failure from the workflow-state "Failed". |
| **Pending** *(shown as started_at fallback)* | **Pending** | `components/cards.html`, `_list_content.html`: `inv.started_at or 'Pending'` in the timestamp slot | KEEP — correct job-phase name when the investigator pod has not yet started. |

---

## 2. Investigation Workflow State (business lifecycle)

The CRD defines `WorkflowState` separately from phase: `Detected | Investigating | Resolved | Verified | Failed`. These are the high-level business states surfaced in the "Workflow State" filter and in the grouped-by-state list view.

| Current label | Standardized label | Where it appears | Rationale |
|---|---|---|---|
| **Detected** | **Detected** | `_list_content.html` group header; `_filter_panel.html` workflow state dropdown | KEEP — unambiguous: the anomaly has fired and a CRD object exists. Matches the CRD enum exactly. |
| **Investigating** | **Investigating** | `_list_content.html` group header; `_filter_panel.html` | KEEP — matches the CRD enum and is the canonical active-triage state. |
| **Resolved** | **Resolved** | `_list_content.html` group header; `_filter_panel.html` | KEEP — conventional SRE close-out term; matches the CRD. |
| **Verified** | **Verified** | `_list_content.html` group header; `_filter_panel.html` | KEEP — the human-confirmed terminal state; "Verified" is stronger and more informative than "Closed." |
| **Failed** *(workflow state context)* | **Failed** | `_list_content.html` group header; `_filter_panel.html` | KEEP — same word as the phase `Failed`, but the context (workflow state filter vs. status badge) disambiguates. The React view should add a subtitle or tooltip clarifying "investigator could not complete" to avoid confusion with workflow-state failures. *(Open decision — see §5.)* |
| **Unknown** *(fallback group)* | **Unknown** | `_list_content.html` state_order fallback group | KEEP for fallback, but the React view should suppress the group header entirely when the count is 0 rather than rendering an empty "Unknown" section. |

---

## 3. List Column Headers

Extracted from the `investigations_table` macro in `_list_content.html` (the legacy table path) and from the card layout in `investigation_card` (`components/cards.html`).

| Current label | Standardized label | Where it appears | Rationale |
|---|---|---|---|
| **Severity** | **Severity** | Table `<th>`; card severity tag; filter dropdown label | KEEP — standard SRE alert field. |
| **Urgency** | **Urgency** | Table `<th>`; `_urgency_card.html` section header ("Escalation Urgency") | KEEP the column header as "Urgency". The section card heading "Escalation Urgency" can shorten to "Urgency" in the React view (the word "Escalation" is redundant when the score itself communicates the escalation need). |
| **Status** | **Status** | Table `<th>`; filter label | KEEP — refers to the job-level phase (Investigating / Awaiting Confirmation / Completed / Failed). |
| **Workflow State** | **State** | Table `<th>`; filter label | Shorten "Workflow State" → "State" in column headers and filter chips; keep the full phrase in the filter panel label where space allows. "State" is the SRE-conventional term in dashboards. |
| **Remediation** | **Remediation** | Table `<th>` | KEEP — describes the active remediation pipeline column. |
| **ID** | **ID** | Table `<th>` | KEEP — CRD resource identifier. |
| **Service** | **Service** | Table `<th>`; card body; filter label | KEEP — matches the CRD `service` field (FR5c normalization). |
| **Condition** | **Condition** *(KEEP)* | Table `<th>`; card body `inv.condition` | KEEP (user, OD-4) — retained as-is. FR47's "Problem state" wording was considered but the team prefers the exact existing term; not renamed. |
| **Started** | **Started** | Table `<th>`; card timestamp | KEEP — conventional column name for incident start time. |

---

## 4. Detail View Section Headers

Extracted from `_detail_content.html` card `<h3>` headings.

| Current label | Standardized label | Where it appears | Rationale |
|---|---|---|---|
| **Investigation Progress** | **Investigation Progress** | `_detail_content.html` section heading | KEEP — clear, accurate, and SRE-conventional. |
| **Remediation Progress** | **Remediation Progress** | `_detail_content.html` card heading | KEEP — names the active remediation pipeline clearly. |
| **Findings** | **Findings** | `_detail_content.html` card heading | KEEP — the standard SRE term for investigation output. |
| **Investigation Timeline** | **Evidence Timeline** | `_detail_content.html` card heading (maps to `_unified_timeline.html`) | "Investigation Timeline" duplicates the page context (this IS an investigation). "Evidence Timeline" names what the section actually contains — the sequence of evidence events (metrics, logs, deploys, KB, config). Clearer for triage. |
| **Deploy Correlation** | **Deploy Correlation** | `_detail_content.html` card heading | KEEP — precise; names the artifact (deploy events) and the analytical act. |
| **Service Dependencies** | **Service Dependencies** | `_detail_content.html` card heading | KEEP — clear and maps directly to the topology data. |
| **Change Event Correlation** | **Change Events** | `_detail_content.html` card heading | Shorten. "Correlation" is implicit in the section context; "Change Events" is the SRE-conventional term (config drifts, restarts, rollouts). |
| **Human Interventions** | **Human Interventions** | `_detail_content.html` card heading | KEEP — accurately describes annotations and redirects entered by on-call engineers. |
| **Confidence Gate** | **Confidence Gate** | `_detail_content.html` card heading | KEEP — domain-specific term defined in the system (auto-action gating). |
| **Investigation Feedback** | **Feedback** | `_detail_content.html` card heading | Shorten. The page context is already "investigation"; "Feedback" is unambiguous and reduces visual repetition. |
| **Resolution Confirmation** | **Resolution Confirmation** | `_detail_content.html` card heading | KEEP — the SRE must explicitly confirm; "Confirmation" is the right action word. |
| **Investigation Resolution** | **Resolution** | `_detail_content.html` card heading | Shorten by dropping the redundant "Investigation" prefix (same page-context rule as Feedback). |
| **Knowledge Created** | **Knowledge Created** | `_detail_content.html` card heading | KEEP — specifically names that KB entries were produced FROM this investigation. |
| **Evidence & Raw Data** | **Evidence & Raw Data** | `_evidence_panel.html` card heading | KEEP — the "Raw Data" qualifier accurately flags this as the lower-level expansion area (vs. the synthesized Findings above). |

---

## 5. Summary Header Fields (detail view hero)

Extracted from the `summary_header` macro in `components/investigation.html`.

| Current label | Standardized label | Where it appears | Rationale |
|---|---|---|---|
| *(service name, no label)* | *(service name, no label)* | Rendered as a chip: `inv.service` | KEEP — the service chip needs no label; the value is self-explanatory at a glance. |
| *(severity tag, no label)* | *(severity tag, no label)* | `inv.severity\|capitalize` chip | KEEP — severity level is instantly recognizable without a field label. |
| *(condition as h2 title)* | *(problem statement as h2 title)* | `inv.condition` rendered as `<h2>` | Rename the display role of this field from "condition name" to "problem statement." The h2 text is already the condition string; the change is to treat it as the FR47 problem-state value (plain language, first-seconds fact). No label word changes — this is a rendering intent note for the React implementation. |
| **signal count** *(no label shown, tooltip only)* | **N signals** | `data-field="signal-count"` span | KEEP the current format (`N signal(s)`). In React, add a visible field label "Signals" next to the count so the stat is self-labeling in the header chip row. |
| **Triggered:** | **Triggered** | `_detail_content.html` timestamp row | KEEP — names the moment the anomaly fired. |
| **Started:** | **Started** | `_detail_content.html` timestamp row | KEEP — names the moment the investigator pod began. |
| **Completed:** | **Completed** | `_detail_content.html` timestamp row | KEEP — names the investigation close time. |

---

## 6. Conclusion Block Fields

Extracted from the `conclusion_block` macro in `components/investigation.html`.

| Current label | Standardized label | Where it appears | Rationale |
|---|---|---|---|
| **Conclusion** *(section heading)* | **Conclusion** | `investigation-conclusion` section `<h3>` | KEEP — a standard incident-report section name. |
| **Root Cause** | **Root Cause** | `data-field="root-cause"` label | KEEP — the canonical SRE/postmortem term. |
| **Affected Services** | **Affected Services** | `data-field="affected-services"` label | KEEP — clear. Gated on RFC 0001 Phase 3 for multi-service population (FR48). |
| **Correlated Signals** | **Signals Correlated** | `data-field="correlated-signals"` label | Minor inversion: "Signals Correlated" reads as a stat label (N things correlated) rather than a section name. Either form is acceptable — flag as open decision. |

---

## 7. Findings Section Sub-Headers

Extracted from `_findings.html`.

| Current label | Standardized label | Where it appears | Rationale |
|---|---|---|---|
| **Customer Impact** | **Customer Impact** | `_findings.html` h4 | KEEP — directly answers the blast-radius question. |
| **Knowledge Base Matches** | **KB Matches** | `_findings.html` h4 | Shorten in the React view. "KB" is the established abbreviation in this codebase; "Knowledge Base Matches" is verbose. |
| **Signal Correlation** | **Signal Correlation** | `_findings.html` h4 | KEEP — correctly names the cross-signal analysis step. |
| **Root Cause Hypothesis** | **Root Cause Hypothesis** | `_findings.html` h4 | KEEP — "Hypothesis" is important: it communicates that this is AI-generated and not yet verified by a human. Removing "Hypothesis" would overstate certainty. |
| **Resolution Recommendations** | **Recommendations** | `_findings.html` h4 | Shorten. "Resolution" is implicit in context (we're in an active investigation). |

---

## 8. Evidence Panel Sub-Headers

Extracted from `_evidence_panel.html` (inside the collapsible "Evidence & Raw Data" card).

| Current label | Standardized label | Where it appears | Rationale |
|---|---|---|---|
| **Raw Signals (N collected)** | **Raw Signals (N)** | `_evidence_panel.html` `<summary>` | Shorten "collected" — it adds no information. The count is self-explanatory. |
| **KB Match Details** | **KB Match Details** | `_evidence_panel.html` `<summary>` | KEEP — concise and accurate. |
| **Correlation & Supporting Evidence** | **Supporting Evidence** | `_evidence_panel.html` `<summary>` | Shorten. "Correlation" is the method; "Supporting Evidence" is what the user is looking for. |
| **Investigation Documentation** | **Documentation** | `_evidence_panel.html` `<summary>` | Shorten. Page context is already the investigation. |

---

## 9. Step Types (Investigation Progress Timeline)

Step types determine the visual accent color of each timeline step. The `.label` field on each step object is already free-text from the investigator pipeline and not templated as a static string. The standardization here is for the step-type identifiers that appear as evidence-type badges in the unified timeline.

**Original (1.8, Jinja-era prediction) table — kept for provenance, superseded by the "Task 4.1 — shipped reality" table immediately below:**

| Current label | Standardized label | Where it appears | Rationale |
|---|---|---|---|
| **metric** | **Metric** | `_unified_timeline.html` evidence type badge; step border color | KEEP — capitalize for display only; the value `metric` remains in the DOM. |
| **log** | **Log** | `_unified_timeline.html` evidence type badge | KEEP — capitalize for display. |
| **deploy** | **Deploy** | `_unified_timeline.html` evidence type badge | KEEP. |
| **KB** | **KB** | `_unified_timeline.html` evidence type badge | KEEP — already uppercase in the template. |
| **config** | **Config Change** | `_unified_timeline.html` evidence type badge (maps from `config_change`) | Expand the badge text. "config" is ambiguous (is it a config file? a Kubernetes ConfigMap? a feature flag?). "Config Change" matches the section heading "Change Events" and clarifies this is a change event, not a configuration reading. |
| *(no label — `summary` step type)* | *(summary steps render only the step.label text)* | `components/investigation.html` step macro | KEEP — summary steps are prose-labeled by the investigator; no badge needed. |

**Task 4.1 — shipped reality** (`ui/frontend/src/lib/components/InvestigationStep/InvestigationStep.tsx`, `STEP_TYPE_LABEL`/`InvestigationStepType`):

| `InvestigationStepType` value | Rendered label | vs. the 1.8 prediction | Status |
|---|---|---|---|
| `metric` | **Metric Query** | 1.8 predicted bare "Metric" | Reality is clearer (names the pipeline action, not just the data kind) — **adopt as the new standardized label**, no fix needed. |
| `log` | **Log Query** | 1.8 predicted bare "Log" | Same reasoning — **adopt as standardized**. |
| `deploy` | **Deploy** | Matches 1.8 exactly | KEEP. |
| `kb` | **KB Query** | 1.8 predicted bare "KB" | Same reasoning as metric/log — **adopt as standardized**. Distinct from the Related-KB-panel's own "N Related KB Entries" wording (§ summary header context), which is unaffected. |
| `correlation` | **Correlation** | Not present in the 1.8 draft at all (the pipeline gained a dedicated correlation step type during Milestone 1.1/1.2 build-out) | New — documented here for the first time; "Correlation" matches §6's "Signals Correlated" business concept. No rename needed. |
| `summary` | **Summary** | 1.8 says summary steps should render **no type-label at all** ("summary steps are prose-labeled by the investigator; no badge needed") | **DISCREPANCY, confirmed during this pass's self-review** — `InvestigationStep.tsx` unconditionally renders `STEP_TYPE_LABEL[type]` for every step, including `summary`, so a "Summary" label currently appears above summary steps' prose. This is recorded as a density finding in §15 (Detail Finding D2) rather than fixed here (scope discipline — no restyling in Task 4.1). |
| *(no `config`/`config_change` value yet)* | — | 1.8's "config" → "Config Change" row | **Not yet implemented.** `InvestigationStepType` has no `config`/`config_change` member today, so there is nothing to rename yet. When this step type ships, the label MUST be **"Config Change"** (never bare "config") per the original 1.8 rationale — carried forward unchanged, and see §14 for why this can't be lint-enforced pre-emptively. |

---

## 10. Remediation Pipeline Stages

Extracted from `_remediation_progress.html`.

| Current label | Standardized label | Where it appears | Rationale |
|---|---|---|---|
| **Proposed** | **Proposed** | Remediation timeline stage | KEEP — clear start state. |
| **Approved** | **Approved** | Remediation timeline stage | KEEP. |
| **Testing** | **Testing** | Remediation timeline stage | KEEP. |
| **Applied** | **Applied** | Remediation timeline stage | KEEP. |
| **Verifying** | **Verifying** | Remediation timeline stage | KEEP. |
| **Verified** | **Verified** | Remediation timeline stage | KEEP. |
| **Rolled Back** | **Rolled Back** | Remediation timeline stage (failure branch) | KEEP. |

---

## 11. Severity Levels

Extracted from `operator/src/crds/investigation.rs` (`Severity` enum) and rendered by `capitalize` filter throughout the templates.

| Current label | Standardized label | Where it appears | Rationale |
|---|---|---|---|
| **Low** | **Low** | Severity tag, filter dropdown | KEEP. |
| **Medium** | **Medium** | Severity tag, filter dropdown | KEEP. |
| **High** | **High** | Severity tag, filter dropdown | KEEP. |
| **Critical** | **Critical** | Severity tag, filter dropdown | KEEP. |

---

## 12. Filter Panel Labels

Extracted from `_filter_panel.html`.

| Current label | Standardized label | Where it appears | Rationale |
|---|---|---|---|
| **Status** *(filter label)* | **Status** | Filter panel | KEEP — matches the column header. |
| **Workflow State** *(filter label)* | **State** | Filter panel chip / column, but **"Workflow State"** in the expanded filter panel where space allows | Shorten in constrained contexts (chips, column headers); use "Workflow State" in the filter panel where the user needs the full context to distinguish it from the job-level Status filter. *(Open decision — see §13.)* |
| **Service** *(filter label)* | **Service** | Filter panel | KEEP. |
| **Severity** *(filter label)* | **Severity** | Filter panel | KEEP. |
| **Date Range** | **Date Range** | Filter panel | KEEP. |
| **Sort by** | **Sort** | Filter panel | Shorten. "Sort" alone is standard. |
| **Urgency (highest)** | **Urgency ↓** | Sort option | Replace the parenthetical with a directional indicator. Consistent with data table conventions. |
| **All statuses** | **All** | Status filter default option | Shorten to "All" when space is constrained; "All statuses" is fine in a full filter panel. |
| **All states** | **All** | Workflow state filter default option | Same rule. |
| **Flat List** / **Group by State** | **Flat List** / **Group by State** | List view toggle buttons | KEEP — the pair is self-explanatory as a toggle. |

---

## 13. Open Decisions — RESOLVED (user review 2026-06-23)

| # | Term / Location | Resolution |
|---|---|---|
| OD-1 | **"Failed" — phase vs. workflow state** | **RESOLVED (user):** rename the job-**phase** failure to **"Analysis Failed"**; the **workflow-state** failure stays **"Failed"**. Removes the same-card collision. |
| OD-2 | **"Workflow State" vs. "State"** in the filter panel | **DEFAULT (applied):** keep **"Workflow State"** in the expanded filter panel (to disambiguate from the "Status" filter); use **"State"** only in chips and column headers. |
| OD-3 | **"Correlated Signals" vs. "Signals Correlated"** | **DEFAULT (applied):** keep **"Correlated Signals"** (heading context). Revisit only if the React layout renders the count as a prominent stat. |
| OD-4 | **"Problem" vs. "Condition" vs. "Problem State"** | **RESOLVED (user):** **keep "Condition"** as-is (no rename). |
| OD-5 | **`investigating` badge — "Investigating" vs. "Running"** | **DEFAULT (applied):** badge reads **"Investigating"**, derived from the workflow/pipeline `investigating` state — **not** from `phase == Running` (which fires first while the pod spins up). Tasks 2.2/2.5 must key the badge off the correct field. |

---

## 14. Lint Coverage (Task 4.1) — enforced vs. documented-only terms

The `[T]` legacy-label lint (`ui/frontend/scripts/legacy-label-rules.mjs`, proven by `ui/frontend/src/test/legacy-label-lint.test.ts`) scans the migrated view source — `src/routes/**`, `src/lib/components/**`, `src/lib/investigations/**` (test files, Storybook stories, and this doc's own fixtures excluded) — for every "current → standardized" **rename** row above (current ≠ standardized) and fails the build if the legacy string reappears. Rows marked **KEEP** (current = standardized) need no rule — there is nothing to forbid.

**Enforced (16 rules, one per rename row):** §1 "In Progress" → Investigating, §1 truncated "Awaiting" → Awaiting Confirmation, §3 "Escalation Urgency" → Urgency, §4 "Investigation Timeline" → Evidence Timeline, §4 "Change Event Correlation" → Change Events, §4 "Investigation Feedback" → Feedback, §4 "Investigation Resolution" → Resolution, §7 "Knowledge Base Matches" → KB Matches, §7 "Resolution Recommendations" → Recommendations, §8 "Raw Signals (N collected)" → Raw Signals (N), §8 "Correlation & Supporting Evidence" → Supporting Evidence, §8 "Investigation Documentation" → Documentation, §12 "Sort by" → Sort, §12 "Urgency (highest)" → Urgency ↓, §12 "All statuses" → All, §12 "All states" → All.

**Deliberately excluded from lexical enforcement** (a plain-text scan cannot safely resolve these without false-positiving on the correct label itself):

| Term | Why it's excluded | How it's actually guarded |
|---|---|---|
| **"Failed"** (job-phase) | Same word as the intentionally-unrenamed workflow-state "Failed" (OD-1 KEEP) — banning the string would ban the correct term too. | Structural, not lexical: `StatusBadge.tsx` encodes them as two separate variants (`analysis-failed` vs. `failed`) with their own label constants, so the two axes can never share a DOM string by construction. |
| **"Workflow State"** (full phrase) | Stays valid verbatim in the *expanded filter panel* per OD-2; only chip/column-header contexts should shorten to "State". A text scan can't tell which context a match is in. | Left as a documented convention; the filter panel doesn't exist yet in the shipped code (nothing to check today) — revisit if a future task adds one and this needs a context-aware rule. |
| **"config"** (bare step-type identifier) | Too common/ambiguous a word in source (`vite.config.ts`, "configuration", etc.) to lex safely. | The `config`/`config_change` `InvestigationStepType` value doesn't exist in the shipped enum yet (§9) — nothing to guard today. Recorded as a build-time reminder: when it ships, the label must be "Config Change", never bare "config". |
| **"Correlated Signals"** | OD-3 keeps this as the default; it's not a rename. | N/A — not a violation to guard against. |

---

## 15. Visual-Density Audit (Task 4.1, FR52)

**Method:** self-review of the actual shipped view source — `InvestigationListPage.tsx` / `InvestigationDetailPage.tsx` and every `src/lib/components/*` primitive they compose — reading the rendered JSX tree, prop tables, and Tailwind utility classes directly (this repo's established convention: token/utility-class strings **are** the contract). Per-element findings are graded against the UX spec's density doctrine ("information density through typography and spacing, not visual noise"; "alert fatigue through visual noise... status colors inform, they don't shout"; "weight communicates hierarchy, not size alone"). Each finding below names a specific element and a specific action; nothing is fixed in this task (scope discipline — 4.2 owns any restyling). `[H]` — this audit's findings are PENDING USER APPROVAL/sign-off, same as the glossary above.

### Investigation List view (`InvestigationListPage.tsx` + `InvestigationCard.tsx`)

**Finding L1 — re-emphasize (not remove): Severity renders as plain secondary-colored text, not a colored chip.** *(DEFERRED — revisit after Task 4.4)*
`InvestigationCard.tsx`'s metadata line renders severity as `<span data-field="severity">{severity}</span>` inside a `flex items-center gap-2 text-sm text-text-secondary` row — identical visual weight to the signal count and timestamp next to it. This is the single most safety-critical list fact (FR46: "high-severity first") yet it carries no color coding, unlike the job-phase `StatusBadge` on the same row (which IS a colored pill) and unlike the original Jinja "card severity tag" this glossary's §3 documents. `StatusBadge.tsx` already reserves a `severity-critical` variant alias for exactly this purpose (its variant-taxonomy doc comment: "only its `critical` value maps onto the shared critical color... `low`/`medium`/`high` map to `muted`/warning-adjacent/`warning`"), but `InvestigationCard` never uses it. **Recommended for 4.2:** render severity as a small colored chip (reusing `StatusBadge`'s color mapping) instead of plain text, so severity reads via color during a scan, not just position in a bullet-separated line.

**Reviewed, confirmed NOT a finding:**
- *Card border color + opacity (`variant`) alongside the `StatusBadge` pill* — two channels encoding the same job-phase state, but this is the UX spec's deliberate "triple-channel status (color + text + icon)" accessibility pattern, not redundant noise. No action.
- *`component` and `problemState` subtitle lines* — both derived from the same raw `condition` field (FR45/46 require them as two distinct first-seconds facts) and already weight-differentiated (`problemState` is `text-text-primary`, `component` is `text-text-secondary`), matching the spec's "weight communicates hierarchy" rule. No action.
- *Signal count in the metadata line* — `InvestigationListPage` never passes `signalCount` to `InvestigationCard` today (the list JSON endpoint doesn't return one; see the component's own doc comment), so the shipped metadata line is only "severity · timestamp" — already lean, not three items.
- *`EmptyGroupState`'s decorative SVG icon* — low-traffic surface (a genuinely empty group), not part of the busy triage scan path; not worth flagging.

### Investigation Detail view (`InvestigationDetailPage.tsx` + `SummaryHeader`/`InvestigationStep`/etc.)

> **Resolutions (user review 2026-07-13):** glossary + audit **approved** `[H]`. **D1 and D2 FIXED** in the same increment (see `InvestigationDetailPage.tsx` — impact line renders only with real `correlated_services`; `InvestigationStep.tsx` — no type badge on `summary` steps; tests updated). **L1 DEFERRED** by user decision — the severity-chip re-emphasis is a visual design call to revisit after the design-sync pass (Task 4.4).

**Finding D1 — remove: the unconditional "Impact: not yet correlated" placeholder line.** *(FIXED)*
`InvestigationDetailPage.tsx` always renders a `data-field="correlation-placeholder"` paragraph reading either `Impact: {services}` or, when there's nothing to show, the literal placeholder **"Impact: not yet correlated"**. Per the component's own doc comments and `docs/specs/ux-design-specification.md`'s first-seconds table (row 4b), cross-service correlation is **gated on RFC 0001 Phase 3 (FR48) and not in the first increment** — meaning, in practice, essentially every investigation today renders this permanent "we don't have this yet" line. This is exactly the kind of non-essential chrome FR52 asks the density audit to name: an always-on disclosure of an unshipped feature's absence, on every single detail view. **Recommended for 4.2:** suppress the line entirely when `correlated_services` is empty (rather than rendering a placeholder sentence), matching the pattern the codebase already uses elsewhere (e.g. `InvestigationCard`'s `component` slot, which omits its line rather than showing an empty one) — restore the paragraph once FR48 ships real data.

**Finding D2 — remove/de-emphasize: `summary`-type steps render a "Summary" type-label, contradicting the glossary's own 1.8 decision.** *(FIXED)*
See §9 above: the 1.8 draft explicitly resolved that summary steps should render "no badge... summary steps are prose-labeled by the investigator." The shipped `InvestigationStep.tsx` renders `STEP_TYPE_LABEL[type]` unconditionally for every step type, including `summary`, so a small "Summary" label currently appears above every summary step's prose body — an extra, always-on line of chrome the team already decided wasn't needed. **Recommended for 4.2:** suppress the type-label specifically for `type === 'summary'`, restoring the previously-agreed density decision (the border-color accent can stay; only the redundant text label goes).

**Reviewed, confirmed NOT a finding:**
- *`SseConnectionIndicator` renders nothing while `connected`* — a positive existing example of the density principle done right (no indicator is the spec's own "default" state); called out here so it isn't mistaken for an oversight.
- *`StatusBadge` "Analysis Failed" (header) + `FailureNotice`'s bold "Analysis Failed" heading (timeline end) both appearing on a failed investigation* — these serve two different scan points (header glance vs. end-of-timeline confirmation after reading the evidence), not a duplicate of the same fact in the same place. No action.
- *`InvestigationStep`'s small step-type label for non-summary types (`Metric Query`, `Log Query`, etc.)* — already de-emphasized (`text-xs text-text-secondary`, one short line above the body) and load-bearing (identifies the evidence kind at a glance); not excessive.

### Out-of-scope observation (flagged separately, not a density item)

While reviewing `SummaryHeader.tsx` for this audit, the severity chip (`data-field="severity"`) was found to be hardcoded to `bg-status-warning/10 text-status-warning` regardless of the actual `severity` value passed in — a Low, Medium, High, or Critical investigation all render the identical amber chip. This is a color-mapping **defect**, not a density/chrome-removal question, so it is out of this task's scope to fix or formally record as a §15 finding; it has been raised to the caller as a follow-up (see the session's spawned-task list) rather than silently left unmentioned.

---

## Source files consulted

**Task 1.8 (Jinja-era, pre-implementation prediction — §1–§13 base content):**

- `ui/beeper_ui/templates/investigations/_list_content.html`
- `ui/beeper_ui/templates/investigations/_detail_content.html`
- `ui/beeper_ui/templates/investigations/_filter_panel.html`
- `ui/beeper_ui/templates/investigations/_evidence_panel.html`
- `ui/beeper_ui/templates/investigations/_findings.html`
- `ui/beeper_ui/templates/investigations/_recommendations.html`
- `ui/beeper_ui/templates/investigations/_step_timeline.html`
- `ui/beeper_ui/templates/investigations/_unified_timeline.html`
- `ui/beeper_ui/templates/investigations/_urgency_card.html`
- `ui/beeper_ui/templates/investigations/_remediation_progress.html`
- `ui/beeper_ui/templates/investigations/_confidence_gate.html`
- `ui/beeper_ui/templates/components/investigation.html`
- `ui/beeper_ui/templates/components/cards.html`
- `ui/beeper_ui/templates/components/status.html`
- `operator/src/crds/investigation.rs` (Severity, InvestigationPhase, WorkflowState enums — re-verified unchanged for this pass)
- `docs/reqs/main.md` FR47, FR52, and the SRE-Centric React UI Overhaul section

**Task 4.1 (this pass — shipped React source, §9/§14/§15 content):**

- `ui/frontend/src/routes/InvestigationListPage.tsx`, `InvestigationDetailPage.tsx`, `investigation-detail-mappers.ts`, `useInvestigationDetail.ts`
- `ui/frontend/src/lib/components/{StatusBadge,InvestigationCard,InvestigationStep,SummaryHeader,RelatedKbPanel,StepEvidence,FailureNotice,NotFoundMessage,SseConnectionIndicator,EmptyGroupState,StatusGroupFilter,InvestigationListSkeleton,DetailSkeleton,Sidebar,AppShell}/*.tsx`
- `ui/frontend/src/lib/investigations/{status-group,row-view-model,problem-state,derive-component}.ts`
- `ui/frontend/src/theme/tokens.css`
- `ui/frontend/src/api/investigations-list.ts`, `investigation-detail.ts`
- `docs/specs/ux-design-specification.md` (density/visual-hierarchy guidance: Color System, "Weight communicates hierarchy," "Alert fatigue through visual noise," first-seconds information model)
- `docs/plans/react-ui.md` Task 4.1 entry (Milestone 1.4)
- Lint implementation: `ui/frontend/scripts/legacy-label-rules.mjs`, `ui/frontend/scripts/check-legacy-labels.mjs`, `ui/frontend/src/test/legacy-label-lint.test.ts`, `ui/frontend/src/test/fixtures/legacy-labels-violating.tsx`
