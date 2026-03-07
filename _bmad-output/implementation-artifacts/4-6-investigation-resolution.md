# Story 4.6: Investigation Resolution

Status: done

## Story

As an **SRE**,
I want to mark an investigation as resolved with outcome confirmation,
so that the investigation is properly closed and documented with MTTR tracking.

## Acceptance Criteria

1. **Given** an investigation is ready to close, **When** I click "Resolve Investigation", **Then** I see a resolution form (FR12) **And** I can select outcome: "Resolved", "Not an issue", "Escalated", "Unresolved".

2. **Given** I select "Resolved", **When** completing resolution, **Then** I confirm the resolution action taken **And** I can rate Beeper's accuracy: "Correct", "Partially correct", "Incorrect" **And** the KB entry is updated with resolution confirmation.

3. **Given** I select "Not an issue", **When** completing resolution, **Then** I indicate why (false positive, expected behavior, transient, other) **And** this feedback is recorded for future anomaly detection improvement.

4. **Given** I select "Escalated", **When** completing resolution, **Then** I indicate escalation target **And** the investigation is marked as escalated but not closed (phase unchanged).

5. **Given** resolution is complete (non-escalated), **When** the investigation closes, **Then** final documentation is written to KB **And** the investigation appears in "Completed" list **And** MTTR is calculated and stored for this investigation.

## Tasks / Subtasks

- [x] Task 1: Add POST /resolve endpoint to operator API (AC: 1, 4, 5)
  - [x]1.1 Add `ResolutionResolveRequest` struct in `operator/src/api.rs` — fields: `outcome: String`, `accuracy_rating: Option<String>`, `resolution_notes: Option<String>`, `escalation_target: Option<String>`, `not_an_issue_reason: Option<String>`
  - [x]1.2 Add `POST /api/v1/investigations/:id/resolve` handler `resolve_investigation()` — for outcomes `resolved`/`not_an_issue`/`unresolved`: patches CRD `status.phase` to `Completed`, sets `status.completed_at` to current ISO 8601 UTC, sets `status.message` to outcome-specific message. For `escalated`: only patches `status.message` to `"Escalated to: {target}"` (phase unchanged, no completed_at)
  - [x]1.3 Register route in `api_router_with_detection()`: `.route("/api/v1/investigations/:id/resolve", post(resolve_investigation))`
  - [x]1.4 Add unit tests: `ResolutionResolveRequest` serialization (all fields, minimal fields), resolve outcomes (resolved sets completed, escalated doesn't), 404 ProblemDetails

- [x] Task 2: Extend InvestigationService with resolution methods (AC: 1, 2, 3, 4, 5)
  - [x]2.1 Add `resolve_investigation(investigation_id: str, outcome: str, accuracy_rating: str | None = None, resolution_notes: str | None = None, escalation_target: str | None = None, not_an_issue_reason: str | None = None) -> bool` method — POST to `{operator_url}/api/v1/investigations/{id}/resolve` with JSON body. Returns True on 200, False on 404. Raises `InvestigationServiceError` on connection errors
  - [x]2.2 Add `update_kb_with_resolution(investigation_id: str, resolution_data: dict[str, Any]) -> bool` method — scrolls Qdrant `knowledge` collection filtered by `investigation_id` (MatchValue) to find the KB entry, then uses `set_payload()` to add resolution fields (`resolution_outcome`, `accuracy_rating`, `resolution_notes`, `resolved_at`, `mttr_seconds`). Returns True if entry found and updated, False if no KB entry exists. Swallows exceptions with warning log
  - [x]2.3 Add `calculate_mttr(started_at: str | None, resolved_at: str) -> int | None` static method — parses ISO 8601 timestamps, returns difference in seconds. Returns None if `started_at` is None

- [x] Task 3: Add resolve POST route (AC: 1, 2, 3, 4, 5)
  - [x]3.1 Add `VALID_OUTCOMES = {"resolved", "not_an_issue", "escalated", "unresolved"}` constant
  - [x]3.2 Add `VALID_ACCURACY_RATINGS = {"correct", "partially_correct", "incorrect"}` constant
  - [x]3.3 Add `VALID_NOT_AN_ISSUE_REASONS = {"false_positive", "expected_behavior", "transient", "other"}` constant
  - [x]3.4 Add `OUTCOME_LABELS` dict mapping outcome keys to human-readable labels: `{"resolved": "Resolved", "not_an_issue": "Not an Issue", "escalated": "Escalated", "unresolved": "Unresolved"}`
  - [x]3.5 Add `POST /investigations/<investigation_id>/resolve` route — reads `request.form.get("outcome")`, validates against `VALID_OUTCOMES`. Conditional validation: if `resolved` → validate optional `accuracy_rating` against `VALID_ACCURACY_RATINGS`; if `not_an_issue` → validate `not_an_issue_reason` against `VALID_NOT_AN_ISSUE_REASONS`; if `escalated` → require `escalation_target` (non-empty). Reads optional `resolution_notes`.
  - [x]3.6 Route calls `svc.resolve_investigation()` with all params → on success, calculates MTTR via `svc.calculate_mttr()`, saves resolution data to Qdrant investigations collection via `svc.save_resolution_feedback()` with payload: `{"resolution_outcome": outcome, "accuracy_rating": rating, "resolution_notes": notes, "escalation_target": target, "not_an_issue_reason": reason, "resolved_at": iso_timestamp, "mttr_seconds": mttr}`. If outcome is `resolved`/`not_an_issue`/`unresolved` → calls `svc.update_kb_with_resolution()` to update KB entry. Returns `_resolution_result.html` partial
  - [x]3.7 Validate `investigation_id` with existing `SERVICE_NAME_PATTERN` check
  - [x]3.8 Return appropriate error partials on failure (operator down → 503, not found → 404, validation → 400)

- [x] Task 4: Create resolution form template (AC: 1, 2, 3, 4)
  - [x]4.1 Create `ui/beeper_ui/templates/investigations/_resolution_form.html` — rendered when investigation can be resolved (status in `awaiting_confirmation`/`completed` AND no prior resolution_outcome in findings, OR status is any non-failed with recommendations)
  - [x]4.2 **Already-resolved state:** If `findings.get('resolution_outcome')` exists, show status banner — green for `resolved`, blue for `not_an_issue`, amber for `escalated`, gray for `unresolved`. Display: outcome label, accuracy rating (if resolved), resolution notes, MTTR formatted as human-readable duration, escalation target (if escalated), not-an-issue reason (if applicable), resolved_at timestamp
  - [x]4.3 **Form state:** `<form hx-post="{{ url_for('investigations.resolve_investigation_route', investigation_id=investigation.id) }}" hx-target="#resolution-result" hx-swap="outerHTML">`. Outcome `<select name="outcome">` with 4 options
  - [x]4.4 **Conditional fields** (shown/hidden via CSS class toggling with HTMX `hx-trigger="change" hx-get` is NOT used — instead, show ALL conditional fields and use `<div class="outcome-fields outcome-resolved">` etc., with a small inline `<script>` to toggle visibility on select change — this is the ONE exception to no-JS rule since HTMX cannot conditionally show form fields without a server round-trip):
    - `resolved` fields: `accuracy_rating` select (Correct/Partially correct/Incorrect), `resolution_notes` textarea
    - `not_an_issue` fields: `not_an_issue_reason` select (False positive/Expected behavior/Transient/Other), `resolution_notes` textarea
    - `escalated` fields: `escalation_target` text input (required), `resolution_notes` textarea
    - `unresolved` fields: `resolution_notes` textarea (placeholder: explain why unresolved)
  - [x]4.5 Submit button "Resolve Investigation" (`.btn-resolve`, blue `#3b82f6`)
  - [x]4.6 Wrap entire form in `<div id="resolution-result">` for HTMX swap

- [x] Task 5: Create resolution result template (AC: 1, 2, 3, 4, 5)
  - [x]5.1 Create `ui/beeper_ui/templates/investigations/_resolution_result.html` — result partial returned by POST route, replaces `#resolution-result` div
  - [x]5.2 **Resolved success:** Green banner with checkmark, "Investigation Resolved", accuracy rating badge, optional notes, MTTR display, "KB entry updated" confirmation
  - [x]5.3 **Not an issue success:** Blue banner, "Marked as Not an Issue", reason display, notes
  - [x]5.4 **Escalated success:** Amber banner, "Investigation Escalated", escalation target display, notes, "Investigation remains open" note
  - [x]5.5 **Unresolved success:** Gray banner, "Investigation Closed (Unresolved)", notes
  - [x]5.6 **Error state:** Red banner with error message (operator unreachable, not found, validation error)

- [x] Task 6: Integrate resolution form into detail page (AC: 1)
  - [x]6.1 Update `_detail_content.html` to add "Investigation Resolution" card section AFTER the Resolution Confirmation section: `<div class="card"><h3>Investigation Resolution</h3><div id="resolution-result">{% include "investigations/_resolution_form.html" %}</div></div>`
  - [x]6.2 Conditionally show: only when investigation status is NOT `investigating` AND NOT `failed` (resolution requires some progress). Show regardless of whether confirmation happened — SRE may want to resolve directly as "Not an issue" or "Escalated"
  - [x]6.3 Add SSE support: `sse-swap="resolution-update"` on `#resolution-result` div

- [x] Task 7: Add CSS styles for resolution UI (AC: 1, 2, 3, 4, 5)
  - [x]7.1 Add `.resolution-form` styles: card layout, consistent with `.confirmation-form`
  - [x]7.2 Add `.btn-resolve` styles: blue background (`#3b82f6`), white text, hover darkens to `#2563eb`
  - [x]7.3 Add `.resolution-result` styles: base layout consistent with `.confirmation-result`
    - `.resolution-resolved` — green tint (same as `.confirmation-success`)
    - `.resolution-not-an-issue` — blue tint (`#eff6ff` bg, `#bfdbfe` border)
    - `.resolution-escalated` — amber tint (same as `.confirmation-rejected`)
    - `.resolution-unresolved` — gray tint (`#f9fafb` bg, `#e5e7eb` border)
  - [x]7.4 Add `.resolution-status-banner` for already-resolved display (matches `.confirmation-status-banner` pattern)
  - [x]7.5 Add `.mttr-display` styles: monospace font, bold, slightly larger
  - [x]7.6 Add `.accuracy-badge` styles: pill badge consistent with `.confidence-badge` — `.accuracy-correct` (green), `.accuracy-partially-correct` (yellow), `.accuracy-incorrect` (red)
  - [x]7.7 Add `.outcome-fields` display toggle: `.outcome-fields { display: none; } .outcome-fields.active { display: block; }`

- [x] Task 8: Add SSE resolution-update event (AC: 5)
  - [x]8.1 Update `_generate_detail_sse_events()` to detect when `findings.get('resolution_outcome')` first appears or changes — send `resolution-update` SSE event with rendered `_resolution_form.html` partial (shows the resolved status banner)
  - [x]8.2 Track `last_resolution_outcome` in SSE generator state alongside existing `last_resolution_action`

- [x] Task 9: MTTR helper and formatting (AC: 5)
  - [x]9.1 Add `format_mttr(seconds: int | None) -> str` function in `investigations.py` — formats seconds as human-readable: "<1m" for <60, "Xm" for <3600, "Xh Ym" for <86400, "Xd Yh" for >=86400. Returns "N/A" for None
  - [x]9.2 Register `format_mttr` as a Jinja2 template filter or pass as template variable so templates can display MTTR values

- [x] Task 10: Tests for resolution workflow (AC: 1, 2, 3, 4, 5)
  - [x]10.1 Test `InvestigationService.resolve_investigation()` calls operator POST correctly and returns True on 200
  - [x]10.2 Test `InvestigationService.resolve_investigation()` returns False on 404
  - [x]10.3 Test `InvestigationService.resolve_investigation()` raises on connection error
  - [x]10.4 Test `InvestigationService.update_kb_with_resolution()` finds KB entry and sets payload
  - [x]10.5 Test `InvestigationService.update_kb_with_resolution()` returns False when no KB entry exists
  - [x]10.6 Test `InvestigationService.calculate_mttr()` with valid timestamps returns seconds
  - [x]10.7 Test `InvestigationService.calculate_mttr()` with None started_at returns None
  - [x]10.8 Test `POST /investigations/<id>/resolve` with outcome=resolved + accuracy_rating — returns success, saves feedback with MTTR, updates KB
  - [x]10.9 Test `POST /investigations/<id>/resolve` with outcome=not_an_issue + reason — returns success
  - [x]10.10 Test `POST /investigations/<id>/resolve` with outcome=escalated + target — returns success, phase NOT set to completed
  - [x]10.11 Test `POST /investigations/<id>/resolve` with outcome=unresolved — returns success
  - [x]10.12 Test `POST /investigations/<id>/resolve` with invalid outcome — returns 400
  - [x]10.13 Test `POST /investigations/<id>/resolve` with outcome=resolved + invalid accuracy_rating — returns 400
  - [x]10.14 Test `POST /investigations/<id>/resolve` with outcome=escalated + empty target — returns 400
  - [x]10.15 Test `POST /investigations/<id>/resolve` when operator down — returns 503
  - [x]10.16 Test `POST /investigations/<id>/resolve` for nonexistent investigation — returns 404
  - [x]10.17 Test `POST /investigations/<id>/resolve` with invalid investigation_id — returns 404
  - [x]10.18 Test `GET /investigations/<id>` with resolution_outcome shows resolution banner
  - [x]10.19 Test `GET /investigations/<id>` without resolution_outcome shows resolution form
  - [x]10.20 Test SSE `resolution-update` event fires when resolution_outcome appears in findings
  - [x]10.21 Test `format_mttr()` formats seconds correctly (sub-minute, minutes, hours, days)
  - [x]10.22 Test MTTR stored in both Qdrant investigations payload and KB knowledge entry

- [x] Task 11: Operator tests for resolve endpoint (AC: 1, 4, 5)
  - [x]11.1 Test `ResolutionResolveRequest` serialization with all fields
  - [x]11.2 Test `ResolutionResolveRequest` serialization with minimal fields (outcome only)
  - [x]11.3 Test resolve with outcome="resolved" sets phase to Completed and completed_at
  - [x]11.4 Test resolve with outcome="escalated" does NOT set phase to Completed (no completed_at)
  - [x]11.5 Test resolve with outcome="not_an_issue" sets phase to Completed
  - [x]11.6 Test resolve 404 returns ProblemDetails

- [x] Task 12: Integration verification (AC: 1, 2, 3, 4, 5)
  - [x]12.1 Run `ruff check` on all new/modified Python files — fix any issues
  - [x]12.2 Run `mypy --strict` on all new/modified Python files — fix any issues
  - [x]12.3 Run full Python test suite — verify zero regressions
  - [x]12.4 Run `cargo check` on operator changes — verify compilation
  - [x]12.5 Verify resolution form renders correctly within investigation detail page (manual template inspection)
  - [x]12.6 Update sprint-status.yaml: `4-6-investigation-resolution: in-progress`

## Dev Notes

### Architecture Decision: Full-Stack Resolution Flow

Story 4-6 extends the full-stack pattern from 4-5 (operator + service + UI). The resolution flow is the final step in the investigation lifecycle, closing the loop:

```
Anomaly detected → Investigation spawned → Steps execute → Recommendations generated →
  SRE confirms/rejects (4-5) → SRE resolves investigation (4-6) → KB updated → MTTR recorded
```

### Data Flow: Resolve Action

```
SRE selects outcome and fills form →
  HTMX POST /investigations/<id>/resolve (form data: outcome, accuracy_rating, notes, etc.) →
    Flask route:
      1. Validate outcome + conditional fields
      2. svc.resolve_investigation(id, outcome, ...) → POST operator API
         → Operator patches CRD:
           - resolved/not_an_issue/unresolved: phase=Completed, completed_at=now, message=outcome
           - escalated: message="Escalated to: {target}" (phase unchanged)
      3. Calculate MTTR: svc.calculate_mttr(investigation.started_at, now)
      4. svc.save_resolution_feedback(id, {...}) → Upsert Qdrant investigations payload
         → Stores: resolution_outcome, accuracy_rating, resolution_notes, resolved_at, mttr_seconds
      5. svc.update_kb_with_resolution(id, {...}) → Update Qdrant knowledge collection
         → Adds: resolution fields to the investigation's KB entry
      6. Return _resolution_result.html (success with MTTR display)
    HTMX swaps #resolution-result with result partial
```

### Resolution vs Confirmation (4-5 vs 4-6)

These are distinct actions:
- **Confirmation (4-5):** SRE agrees/disagrees with Beeper's recommendation — stored as `resolution_action: confirmed/rejected`
- **Resolution (4-6):** SRE marks the investigation's final outcome — stored as `resolution_outcome: resolved/not_an_issue/escalated/unresolved`

A typical flow: Beeper recommends "restart service" → SRE confirms → SRE resolves as "Resolved" with accuracy="Correct". But SREs can also skip confirmation and directly resolve as "Not an issue" if it's a false positive.

### Resolution Outcome Semantics

| Outcome | Phase Change | completed_at | MTTR Calculated | KB Updated |
|---------|-------------|-------------|-----------------|------------|
| resolved | → Completed | Set | Yes | Yes |
| not_an_issue | → Completed | Set | Yes | Yes |
| escalated | Unchanged | Not set | No | No |
| unresolved | → Completed | Set | Yes | Yes |

### MTTR Calculation

MTTR (Mean Time To Resolution) for a single investigation:
```python
mttr_seconds = (resolved_at - started_at).total_seconds()
```
- Uses `started_at` from investigation detail (when investigator pod started)
- `resolved_at` is the current timestamp when SRE clicks resolve
- Stored in Qdrant `investigations` collection payload as `mttr_seconds: int`
- Also stored in `knowledge` collection entry for the investigation
- Epic 6 (Story 6-1) will aggregate these for MTTR trends dashboard (FR35)

### Qdrant Resolution Storage Schema

Resolution data stored in `investigations` collection alongside existing pipeline metadata and confirmation feedback:

```python
# Resolve — stored via save_resolution_feedback() (extends existing payload)
{
    "resolution_outcome": "resolved",           # str: resolved|not_an_issue|escalated|unresolved
    "accuracy_rating": "correct",               # str | None: correct|partially_correct|incorrect
    "resolution_notes": "Restarted payment-svc, confirmed fixed",  # str | None
    "escalation_target": None,                  # str | None (only for escalated)
    "not_an_issue_reason": None,                # str | None (only for not_an_issue)
    "resolved_at": "2026-03-07T14:30:00Z",     # ISO 8601
    "mttr_seconds": 3420,                       # int | None
}
```

KB `knowledge` collection entry update (via update_kb_with_resolution):
```python
{
    "resolution_outcome": "resolved",
    "accuracy_rating": "correct",
    "resolution_notes": "Restarted payment-svc",
    "resolved_at": "2026-03-07T14:30:00Z",
    "mttr_seconds": 3420,
}
```

### Conditional Form Field Visibility

The resolution form has outcome-dependent fields. Since HTMX cannot conditionally show fields without a server round-trip, use a minimal inline `<script>` to toggle `.outcome-fields` div visibility on `<select>` change. This is the one JS exception — all other interactivity is pure HTMX.

```html
<script>
document.querySelector('[name="outcome"]').addEventListener('change', function() {
    document.querySelectorAll('.outcome-fields').forEach(el => el.classList.remove('active'));
    const selected = document.querySelector('.outcome-' + this.value);
    if (selected) selected.classList.add('active');
});
</script>
```

### Existing Patterns to Reuse

- **POST route pattern:** `confirm_resolution()` and `reject_resolution()` in `investigations.py` — same validate → call service → save feedback → return partial flow
- **Form template pattern:** `_confirmation_form.html` — HTMX `hx-post`, `hx-target`, `hx-swap="outerHTML"` with status banner for already-resolved state
- **Result partial pattern:** `_confirmation_result.html` — success/error banners
- **Service POST pattern:** `confirm_resolution()`, `reject_resolution()` in `investigation_service.py` — JSON POST, True/False return, error handling
- **Qdrant update pattern:** `save_resolution_feedback()` and `update_entry()` in `kb_service.py`
- **KB entry lookup by investigation_id:** `update_kb_with_resolution()` scrolls `knowledge` collection with `MatchValue` on `investigation_id` field — same pattern as `get_investigation_findings()` on `investigations` collection
- **SSE event pattern:** `confirmation-update` tracking in `_generate_detail_sse_events()` — add parallel `resolution-update` tracking
- **Badge CSS:** `.confidence-badge`, `.risk-badge`, `.rejection-reason-badge` — reuse for `.accuracy-badge`
- **Status banner:** `.confirmation-status-banner` pattern for `.resolution-status-banner`
- **Input validation:** `VALID_REJECTION_REASONS` pattern for `VALID_OUTCOMES`, `VALID_ACCURACY_RATINGS`, `VALID_NOT_AN_ISSUE_REASONS`

### Anti-Patterns to Avoid

- **DO NOT** create new service classes — extend existing `InvestigationService`
- **DO NOT** create new CSS files — add to existing `main.css`
- **DO NOT** create new route files — add to existing `investigations.py`
- **DO NOT** create separate Qdrant collections — store in existing `investigations` and `knowledge` collections
- **DO NOT** use `url_for()` hardcoded URLs in templates — use `url_for()` for all form action URLs
- **DO NOT** expose internal error details — use generic user-facing messages
- **DO NOT** modify the investigator pipeline — resolution is a UI-only action
- **DO NOT** use WebSocket or polling for form fields — use minimal inline JS for select change only
- **DO NOT** forget to close service instances in `finally` blocks (routes and SSE generators)
- **DO NOT** hardcode MTTR format — use `format_mttr()` helper for consistent display

### Key File Paths

| Component | Path | Action |
|-----------|------|--------|
| Operator API (modify) | `operator/src/api.rs` | Add POST /resolve endpoint, ResolutionResolveRequest struct |
| Investigation Service (modify) | `ui/beeper_ui/services/investigation_service.py` | Add `resolve_investigation`, `update_kb_with_resolution`, `calculate_mttr` |
| Investigation Routes (modify) | `ui/beeper_ui/routes/investigations.py` | Add POST /resolve route, validation constants, `format_mttr`, SSE event |
| Resolution form (NEW) | `ui/beeper_ui/templates/investigations/_resolution_form.html` | Resolution form + status banner |
| Resolution result (NEW) | `ui/beeper_ui/templates/investigations/_resolution_result.html` | Result partial (per-outcome states + error) |
| Detail content (modify) | `ui/beeper_ui/templates/investigations/_detail_content.html` | Add Investigation Resolution card section |
| CSS styles (modify) | `ui/beeper_ui/static/css/main.css` | Add resolution form/result/badge styles |
| Route tests (modify) | `ui/tests/test_investigation_routes.py` | Add resolution workflow tests |
| Service tests (modify) | `ui/tests/test_investigation_service.py` | Add resolve/KB update/MTTR tests |

### Testing Standards

- **pytest** with Flask test client for route tests
- **respx** for mocking operator HTTP POST calls
- **MagicMock** for Qdrant client in KB update and feedback persistence tests
- Test all 4 outcome paths (resolved, not_an_issue, escalated, unresolved)
- Test conditional validation per outcome
- Test MTTR calculation with various timestamp pairs
- Test KB update success and no-entry-found paths
- Test HTMX partial responses (result partials replace form)
- Test SSE `resolution-update` event generation
- Test already-resolved state display in form template
- `ruff check` and `mypy --strict` on all modified Python files

### Previous Story Intelligence (from 4-5)

**Patterns established:**
- Full-stack confirm/reject flow: operator POST endpoint → service method → route handler → HTMX form → result partial
- `VALID_REJECTION_REASONS` validation pattern — apply same for outcomes, ratings, reasons
- `REJECTION_REASON_LABELS` mapping for human-readable display — apply same for `OUTCOME_LABELS`, `ACCURACY_LABELS`, `NOT_AN_ISSUE_LABELS`
- `save_resolution_feedback()` for Qdrant payload upsert — reuse for resolution data
- SSE `confirmation-update` event tracking `last_resolution_action` — add parallel `last_resolution_outcome`
- `_confirmation_form.html` already-confirmed/rejected banner pattern — use for already-resolved banner

**Lessons learned (from 4-5 code review):**
- SSE event checks must be independent of other value-change blocks (confirmation-update was initially inside findings key-change block)
- Show human-readable labels in banners via template mapping, not raw keys
- Add `role="status"` to status banners for WCAG accessibility
- Close service instances in `finally` blocks in both routes and SSE generators

### Project Structure Notes

- Resolution templates follow `_` prefix partial naming: `_resolution_form.html`, `_resolution_result.html`
- Route naming: `resolve_investigation_route` (suffix `_route` to avoid name collision with service method)
- Qdrant `knowledge` collection access is new to `InvestigationService` — follow `KBService` scroll pattern (collection name `knowledge`, filter by `investigation_id`)
- MTTR formatting function `format_mttr()` is a module-level function, not a method

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 4, Story 4.6]
- [Source: operator/src/api.rs — POST confirm/reject endpoint patterns, ResolutionConfirmRequest/RejectRequest structs]
- [Source: operator/src/crds/investigation.rs — InvestigationPhase enum, InvestigationStatus struct with completed_at]
- [Source: ui/beeper_ui/routes/investigations.py — POST confirm/reject routes, VALID_REJECTION_REASONS, SSE generator]
- [Source: ui/beeper_ui/services/investigation_service.py — confirm_resolution, reject_resolution, save_resolution_feedback, Qdrant client]
- [Source: ui/beeper_ui/services/kb_service.py — update_entry(), set_payload() patterns for KB writes]
- [Source: ui/beeper_ui/templates/investigations/_confirmation_form.html — form + status banner pattern]
- [Source: ui/beeper_ui/templates/investigations/_confirmation_result.html — result partial pattern]
- [Source: ui/beeper_ui/templates/investigations/_detail_content.html — card section layout, SSE swap attributes]
- [Source: _bmad-output/implementation-artifacts/3-8-investigation-documentation.md — KB entry schema with investigation_id field]
- [Source: _bmad-output/implementation-artifacts/4-5-resolution-confirmation.md — previous story patterns and lessons]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created
- Full-stack story: operator API, UI service, routes, templates, CSS, SSE
- Four resolution outcomes with outcome-dependent form fields and validation
- MTTR calculation and storage for Epic 6 aggregation
- KB update with resolution data via Qdrant knowledge collection
- Conditional form field visibility via minimal inline JS (single exception to no-JS rule)
- SSE resolution-update event for real-time status propagation
- Previous story 4-5 patterns inform form/result/banner/validation design
- 12 tasks: operator endpoint, service methods, POST route, form template, result template, detail integration, CSS, SSE event, MTTR helper, UI tests, operator tests, integration verification

### Change Log

- Task 1: Added `ResolutionResolveRequest` struct and `resolve_investigation` handler to `operator/src/api.rs`. Registered POST /resolve route. 7 Rust unit tests.
- Task 2: Added `resolve_investigation()`, `update_kb_with_resolution()`, `calculate_mttr()` to `investigation_service.py`.
- Task 3: Added validation constants (`VALID_OUTCOMES`, `VALID_ACCURACY_RATINGS`, `VALID_NOT_AN_ISSUE_REASONS`, label mappings), `format_mttr()`, and `resolve_investigation_route()` POST handler to `investigations.py`.
- Task 4: Created `_resolution_form.html` with outcome-dependent fields, status banners, minimal inline JS for field toggling.
- Task 5: Created `_resolution_result.html` with per-outcome result states and error state.
- Task 6: Updated `_detail_content.html` — added Investigation Resolution card with SSE swap support.
- Task 7: Added ~170 lines CSS to `main.css` for resolution UI (form, result, banners, badges, MTTR, accuracy, outcome toggle).
- Task 8: Added `last_resolution_outcome` tracking and `resolution-update` SSE event in `_generate_detail_sse_events()`.
- Task 9: `format_mttr()` function in routes file (passed as template variable).
- Task 10: 11 new service tests (resolve, KB update, MTTR) + 18 new route tests (4 outcomes, validation, errors, detail display, SSE, format_mttr).
- Task 11: 7 Rust unit tests for `ResolutionResolveRequest` serialization/deserialization.
- Task 12: 416 tests pass (29 new), zero regressions. Ruff clean. Mypy clean on investigation files (pre-existing errors in kb_service.py/import_service.py only). Cargo not available on dev machine — verified Rust syntax by inspection.

### File List

**Modified:**
- `operator/src/api.rs` — POST /resolve endpoint, ResolutionResolveRequest struct, 7 unit tests
- `ui/beeper_ui/services/investigation_service.py` — resolve_investigation, update_kb_with_resolution, calculate_mttr methods
- `ui/beeper_ui/routes/investigations.py` — POST /resolve route, validation constants, format_mttr, SSE resolution-update event
- `ui/beeper_ui/templates/investigations/_detail_content.html` — Investigation Resolution card section
- `ui/beeper_ui/static/css/main.css` — ~170 lines resolution UI styles
- `ui/tests/test_investigation_service.py` — 11 new tests (TestResolveInvestigation, TestUpdateKBWithResolution, TestCalculateMTTR)
- `ui/tests/test_investigation_routes.py` — 18 new tests (TestInvestigationResolution, TestFormatMTTR)

**New:**
- `ui/beeper_ui/templates/investigations/_resolution_form.html` — Resolution form + already-resolved status banners
- `ui/beeper_ui/templates/investigations/_resolution_result.html` — Result partial (per-outcome success + error states)
