# Story 7.3: Remediation Progress Tracking

Status: done

## Story

As a **user**,
I want to track remediation progress from detection through fix verification,
so that I can see at a glance where each incident stands in the fix lifecycle.

## Acceptance Criteria

1. **Given** an investigation with an associated remediation action (auto-PR, runbook, sandbox test) **When** the user views the investigation detail **Then** a progress tracker shows the remediation pipeline: proposed → approved → testing → applied → verifying → verified/rolled-back **And** the current stage is highlighted with timestamps for completed stages

2. **Given** the investigation list view **When** investigations have active remediations **Then** a remediation status badge is visible (e.g., "PR open", "sandbox testing", "verifying") **And** clicking the badge navigates to the remediation detail

3. **Given** a remediation that was rolled back **When** the progress tracker displays **Then** the rollback stage is shown with the reason (metric degradation, manual rollback, timeout) **And** the pre-rollback and post-rollback metric comparison is accessible

## Tasks / Subtasks

- [x] Task 1: Add `remediation_status` field to Investigation dataclass and parse from findings (AC: #1, #2)
  - [x]1.1 In `ui/beeper_ui/services/investigation_service.py`, add a helper function `compute_remediation_status(findings: dict) -> dict | None` that extracts remediation progress from Qdrant `pipeline_metadata` keys. It must return `None` if no remediation was attempted, or a dict with: `stage` (one of: "proposed", "approved", "testing", "applied", "verifying", "verified", "rolled_back", "failed"), `label` (human-readable badge text like "PR Open", "Sandbox Testing", "Verified"), `stages_completed` (list of dicts with `name`, `completed_at` timestamp, `status`), `pr_url` (str|None), `rollback_reason` (str|None), `verification_results` (list|None).
  - [x]1.2 The function reads these existing `pipeline_metadata` keys (already populated by investigator remediation steps): `runbook_found`, `runbook_steps_executed`, `runbook_steps_advisory`, `sandbox_executed`, `sandbox_overall_status`, `sandbox_test_results`, `verification_executed`, `verification_status`, `fix_verified`, `verification_results`, `pr_generated`, `pr_url`, `draft`, `trust_gate_evaluated`, `trust_gate_decisions`, `trust_gate_rollback_paths`, `kb_entry_created`, `proven_fix_entry_id`. Compute stage from these: if `pr_generated` and `draft` → "proposed"; if `pr_generated` and not `draft` → "approved"; if `sandbox_executed` → "testing"; if `verification_executed` and `verification_status == "confirmed"` → "verified"; if `verification_executed` and `verification_status == "degraded"` → "rolled_back"; if `verification_executed` and `verification_status == "pending"` → "verifying"; if none of the above but remediation keys exist → "proposed".
  - [x]1.3 Add `remediation_status: dict | None = None` field to both `Investigation` and `InvestigationDetail` dataclasses. Do NOT populate it in `from_dict()` — it will be set externally after findings are loaded (since findings come from Qdrant, not the operator API response).

- [x] Task 2: Add remediation progress route and service method (AC: #1, #3)
  - [x]2.1 In `ui/beeper_ui/services/investigation_service.py`, add method `get_remediation_progress(investigation_id: str) -> dict | None` that calls `get_investigation_findings()` and then `compute_remediation_status()`, returning the full remediation status dict.
  - [x]2.2 In `ui/beeper_ui/routes/investigations.py`, add a new HTMX partial route `GET /investigations/<investigation_id>/remediation-progress` that returns the rendered `_remediation_progress.html` partial. Use the existing pattern from the urgency/gate-status/linked-kb partial routes (lazy-loaded via `hx-get` + `hx-trigger="load"`).

- [x] Task 3: Create remediation progress tracker template (AC: #1, #3)
  - [x]3.1 Create `ui/beeper_ui/templates/investigations/_remediation_progress.html`. Display a horizontal step timeline (reuse the visual pattern from `_step_progress.html`). The pipeline stages are: Proposed → Approved → Testing → Applied → Verifying → Verified/Rolled Back. Each stage shows: icon (checkmark for completed, spinner for active, circle for pending, X for failed/rolled back), label, timestamp when completed. The current active stage is highlighted.
  - [x]3.2 If `remediation_status` is None (no remediation attempted), show a muted "No remediation actions for this investigation" message.
  - [x]3.3 If stage is "rolled_back", show a rollback details section with: the rollback reason (from `trust_gate_rollback_paths` or `verification_status == "degraded"`), and if `verification_results` exist, show a pre/post metric comparison table (metric name, pre-fix value, post-fix value, delta, status).
  - [x]3.4 If `pr_url` is set, render a "View PR" link button.
  - [x]3.5 If `proven_fix_entry_id` is set, render a "View KB Entry" link to `/knowledge/{id}`.

- [x] Task 4: Integrate remediation progress into investigation detail page (AC: #1)
  - [x]4.1 In `ui/beeper_ui/templates/investigations/_detail_content.html`, add a new "Remediation Progress" card section between the "Investigation Progress" card (line 59) and the "Findings" card (line 67). Use the same lazy-load HTMX pattern: `hx-get="/investigations/{{ investigation.id }}/remediation-progress"` with `hx-trigger="load"` and an SSE swap target `sse-swap="remediation-update"`.
  - [x]4.2 In the SSE event generator `_generate_detail_sse_events()` in `investigations.py`, add a new SSE event `remediation-update` that fires when remediation-related findings keys change (check for changes in: `pr_generated`, `sandbox_executed`, `verification_executed`, `verification_status`, `trust_gate_evaluated`). Render the `_remediation_progress.html` partial and send as SSE data.

- [x] Task 5: Add remediation status badge to investigation list view (AC: #2)
  - [x]5.1 In the investigation list route (`list_investigations()` in `investigations.py`), after fetching investigations, also fetch findings for each investigation via `get_investigation_findings()` and compute `remediation_status` using `compute_remediation_status()`. Attach `remediation_status` to each `Investigation` object. **Performance note:** Only fetch findings for investigations with `workflow_state` in ("investigating", "resolved") to avoid unnecessary Qdrant queries for completed/verified investigations.
  - [x]5.2 In `ui/beeper_ui/templates/investigations/_list_content.html`, add a new "Remediation" column to the investigations table (after the Status column). In the `investigation_row` macro, render: if `inv.remediation_status`, show a clickable badge with `inv.remediation_status.label` text, styled with class `.remediation-badge .remediation-stage-{stage}`. The badge links to `/investigations/{{ inv.id }}#remediation-progress` (anchor to the remediation card on the detail page). If no remediation, show an em-dash.
  - [x]5.3 Update the table header in `investigations_table` macro to include "Remediation" column.

- [x] Task 6: Add CSS styles for remediation progress tracker (AC: #1, #2, #3)
  - [x]6.1 In `ui/beeper_ui/static/css/main.css`, add styles for `.remediation-timeline` (horizontal flexbox layout similar to `.step-timeline` but horizontal), `.remediation-stage` items with states: `.stage-completed` (green), `.stage-active` (blue with pulse animation), `.stage-pending` (gray), `.stage-failed` (red), `.stage-rolled-back` (orange).
  - [x]6.2 Add `.remediation-badge` styles for the list view badges. Color-code by stage: proposed → gray (#94a3b8), approved → blue (#60a5fa), testing → yellow (#fbbf24), applied → teal (#2dd4bf), verifying → purple (#a78bfa), verified → green (#34d399), rolled_back → orange (#fb923c), failed → red (#f87171). Use same badge pattern as workflow state badges (padding: 4px 10px, border-radius: 12px, font-size: 0.75rem, font-weight: 600).
  - [x]6.3 Add `.rollback-details` card styles and `.metric-comparison-table` table styles for the rollback reason and metric comparison display.

- [x] Task 7: Write tests (AC: #1, #2, #3)
  - [x]7.1 Create `ui/tests/test_remediation_progress.py`. Test `compute_remediation_status()` with: no remediation keys → None; PR generated draft → "proposed" stage; PR generated non-draft → "approved"; sandbox executed → "testing"; verification pending → "verifying"; verification confirmed → "verified"; verification degraded → "rolled_back" with reason; full pipeline (all keys present) → correct final stage.
  - [x]7.2 Test `get_remediation_progress()` returns correct dict shape with all required fields.
  - [x]7.3 Test the remediation-progress HTMX partial route: returns 200, contains `.remediation-timeline` markup, shows stages correctly for mock findings data.
  - [x]7.4 Test the investigation list view includes "Remediation" column header and renders remediation badges for investigations with active remediations.
  - [x]7.5 Test rollback details rendering: when stage is "rolled_back", verify rollback reason is displayed and metric comparison table renders with pre/post values.
  - [x]7.6 Test empty state: when no remediation findings exist, verify "No remediation actions" message is displayed.
  - [x]7.7 Test SSE event: verify `remediation-update` event is emitted when remediation keys change in findings.

- [x] Task 8: Run full test suite across all components (AC: all)
  - [x]8.1 Run investigator tests: `cd investigator && poetry run python -m pytest`
  - [x]8.2 Run investigator linting: `cd investigator && poetry run ruff check .`
  - [x]8.3 Run investigator type checking: `cd investigator && poetry run mypy .`
  - [x]8.4 Run UI tests: `cd ui && poetry run python -m pytest`
  - [x]8.5 Run operator tests: `cd operator && cargo test`
  - [x]8.6 Verify no regressions from baseline (3,384 tests)

## Dev Notes

### Architecture Patterns (CRITICAL -- must follow)

**FR49 maps to:** Remediation progress tracking — UI-only feature reading existing remediation pipeline_metadata from Qdrant. No operator/investigator code changes needed. [Source: _bmad-output/planning-artifacts/epics.md#Story 7.3, architecture.md FR49]

**Design Decision: Read existing pipeline_metadata, don't add new fields.** The investigator remediation steps (Epic 4, stories 4-1 through 4-8) already populate comprehensive pipeline_metadata in Qdrant during execution. Story 7-3 is purely a UI presentation layer that reads these existing keys and presents them as a progress tracker. No changes to the operator CRD or investigator pipeline are needed.

**Key pipeline_metadata keys (already populated by investigator remediation steps):**
- `runbook_found`, `runbook_steps_executed`, `runbook_steps_advisory`, `execution_log` — from `remediation/runbook_executor.py`
- `sandbox_executed`, `sandbox_overall_status`, `sandbox_test_results`, `sandbox_namespace` — from `remediation/sandbox_executor.py`
- `verification_executed`, `verification_status`, `fix_verified`, `verification_results` — from `remediation/metric_verifier.py`
- `pr_generated`, `pr_url`, `draft`, `trust_level` — from `remediation/pr_generator.py`
- `trust_gate_evaluated`, `trust_gate_decisions`, `trust_gate_rollback_paths` — from `remediation/trust_gate.py`
- `kb_entry_created`, `proven_fix_entry_id` — from `remediation/proven_fix_accumulator.py`

**Reuse existing patterns:**
- HTMX partial lazy-load pattern from urgency score, gate status, linked-kb cards in `_detail_content.html`
- Step timeline visual pattern from `_step_progress.html` (`.step-timeline`, `.step-item`, `.step-indicator`, `.step-content`)
- SSE event pattern from `_generate_detail_sse_events()` for real-time updates
- Badge pattern from workflow state badges (`.workflow-state-*` classes in main.css)
- Investigation list column pattern from existing severity/urgency/status columns in `_list_content.html`

**DO NOT:**
- Add fields to the Investigation CRD (operator/src/crds/investigation.rs) — remediation data lives in Qdrant
- Modify the investigator remediation pipeline — it already writes all needed metadata
- Create a separate remediation service file — add methods to existing InvestigationService
- Use JavaScript for the progress tracker — use server-rendered Jinja2 + HTMX + SSE

### Previous Story Intelligence (Story 7-2)

**Key patterns established in 7-2:**
- WorkflowState badges with CSS classes `.workflow-state-{state}` — follow same naming for `.remediation-stage-{stage}`
- List view column addition pattern: add to both `investigation_row` macro and `investigations_table` header
- HTMX filter pattern with `hx-get` and query params
- Test fixture pattern using Flask test client with mock operator responses
- SSE event generation pattern for findings changes

**Issues found in 7-2 code review (avoid repeating):**
- HIGH: Ensure all routes claimed as implemented actually exist (7-2 had missing verify route)
- HIGH: Ensure all template features claimed as implemented actually render (7-2 had missing group-by toggle)
- MEDIUM: Use direct matching instead of serde roundtrips for string conversion
- MEDIUM: Consolidate shared CSS properties into grouped selectors
- LOW: Use correct `@require_role("user")` not `@require_role("operator")` on user-facing routes

### Project Structure Notes

- All UI changes in `ui/` directory (Flask + Jinja2 + HTMX + SSE)
- Templates: `ui/beeper_ui/templates/investigations/`
- Routes: `ui/beeper_ui/routes/investigations.py`
- Service: `ui/beeper_ui/services/investigation_service.py`
- CSS: `ui/beeper_ui/static/css/main.css`
- Tests: `ui/tests/`
- No operator or investigator changes needed

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 7.3]
- [Source: _bmad-output/planning-artifacts/architecture.md - Remediation Pipeline]
- [Source: _bmad-output/planning-artifacts/architecture.md - FR49]
- [Source: investigator/beeper_investigator/remediation/ - pipeline_metadata keys]
- [Source: _bmad-output/implementation-artifacts/7-2-investigation-workflow-states.md - Previous story patterns]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6

### Debug Log References
N/A

### Completion Notes List
- Implemented `compute_remediation_status()` function that reads existing Qdrant pipeline_metadata keys to determine remediation stage
- Added `remediation_status` field to `Investigation` and `InvestigationDetail` dataclasses
- Added `get_remediation_progress()` service method and HTMX partial route
- Created horizontal step timeline template with 6 pipeline stages, rollback details, metric comparison table
- Integrated into detail page with lazy-load HTMX + SSE real-time updates
- Added remediation badge column to investigation list view
- Added comprehensive CSS with stage-specific colors and pulse animation
- 34 new tests covering all functionality
- Fixed 4 existing SSE test regressions caused by new `remediation-update` event
- All 3,418 tests passing (1,013 investigator + 1,867 UI + 538 operator)

### Code Review Fixes (2026-03-18)
- **HIGH (deferred)**: AC #1 requires "timestamps for completed stages" but pipeline_metadata uses boolean flags, not timestamps. Per-stage timestamps are unavailable without modifying the investigator pipeline (prohibited by architecture). Tracked as known limitation.
- **MEDIUM**: SSE `remediation-update` now only fires when computed remediation stage actually changes (was firing on every findings key change). Prevents unnecessary DOM re-renders.
- **MEDIUM**: Added "failed" stage to `compute_remediation_status()` — fires when `sandbox_overall_status == "fail"`. Previously unreachable dead code in labels/CSS.
- **MEDIUM**: Added functional SSE test verifying stage change detection logic. Replaced static file scan test.
- **LOW**: Removed dead `is_pending` and `found_active` template variables from `_remediation_progress.html`.
- Updated 4 SSE test event counts to reflect filtered remediation-update behavior.
- Added 3 new tests (sandbox failure, sandbox pass, stage change detection).

### File List
- `ui/beeper_ui/services/investigation_service.py` (modified — added compute_remediation_status, get_remediation_progress, remediation_status field)
- `ui/beeper_ui/routes/investigations.py` (modified — added remediation-progress route, SSE event, list view computation)
- `ui/beeper_ui/templates/investigations/_remediation_progress.html` (created — horizontal timeline template)
- `ui/beeper_ui/templates/investigations/_detail_content.html` (modified — added Remediation Progress card)
- `ui/beeper_ui/templates/investigations/_list_content.html` (modified — added Remediation column)
- `ui/beeper_ui/static/css/main.css` (modified — remediation timeline + badge + rollback CSS)
- `ui/tests/test_remediation_progress.py` (created — 34 tests)
- `ui/tests/test_investigation_routes.py` (modified — fixed 4 SSE test event counts)
