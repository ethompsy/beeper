# Terminology Glossary — Investigation List & Detail Views

**Status: DRAFT — awaiting human review (`[H]` criterion, FR52)**
**Scope:** Investigation list view + investigation detail view only.
**Purpose:** Produce the terminology standardization artifact required by FR52 before the React implementations of the list (Task 2.2) and detail (Task 2.5) views are built. Every entry is derived from the literal label strings in the Jinja templates (the authoritative source of current copy) and cross-checked against the Rust CRD enums in `operator/src/crds/investigation.rs`.

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

| Current label | Standardized label | Where it appears | Rationale |
|---|---|---|---|
| **metric** | **Metric** | `_unified_timeline.html` evidence type badge; step border color | KEEP — capitalize for display only; the value `metric` remains in the DOM. |
| **log** | **Log** | `_unified_timeline.html` evidence type badge | KEEP — capitalize for display. |
| **deploy** | **Deploy** | `_unified_timeline.html` evidence type badge | KEEP. |
| **KB** | **KB** | `_unified_timeline.html` evidence type badge | KEEP — already uppercase in the template. |
| **config** | **Config Change** | `_unified_timeline.html` evidence type badge (maps from `config_change`) | Expand the badge text. "config" is ambiguous (is it a config file? a Kubernetes ConfigMap? a feature flag?). "Config Change" matches the section heading "Change Events" and clarifies this is a change event, not a configuration reading. |
| *(no label — `summary` step type)* | *(summary steps render only the step.label text)* | `components/investigation.html` step macro | KEEP — summary steps are prose-labeled by the investigator; no badge needed. |

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

## Source files consulted

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
- `operator/src/crds/investigation.rs` (Severity, InvestigationPhase, WorkflowState enums)
- `docs/reqs/main.md` FR47, FR52, and the SRE-Centric React UI Overhaul section
