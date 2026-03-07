# Story 4.5: Resolution Confirmation

Status: done

## Story

As an **SRE**,
I want to confirm or reject an Investigator's resolution recommendation,
so that I maintain control over actions taken and my feedback is recorded for Beeper's learning.

## Acceptance Criteria

1. **Given** an investigation has a recommendation awaiting confirmation, **When** I view the investigation, **Then** I see "Confirm" and "Reject" buttons (FR11) **And** the recommendation details are clearly displayed.

2. **Given** I click "Confirm", **When** confirming a resolution, **Then** I can optionally add a comment **And** the confirmation is recorded **And** the investigation status updates to reflect confirmation.

3. **Given** I click "Reject", **When** rejecting a resolution, **Then** I must provide a reason (dropdown + free text) **And** the rejection is recorded **And** the investigation may continue with alternative approaches.

4. **Given** I reject with correction, **When** I provide the correct resolution, **Then** my correction is captured for Beeper learning **And** the investigation can be resolved with my correction.

## Tasks / Subtasks

- [x] Task 1: Add `AwaitingConfirmation` phase to operator CRD and API (AC: 1, 2, 3)
  - [x] 1.1 Add `AwaitingConfirmation` variant to `InvestigationPhase` enum in `operator/src/crds/investigation.rs` — serde renames to `"awaiting_confirmation"`
  - [x] 1.2 Update `phase_to_status()` in `operator/src/api.rs` to map `Some(InvestigationPhase::AwaitingConfirmation) => "awaiting_confirmation".to_string()`
  - [x] 1.3 Add `ResolutionConfirmRequest` and `ResolutionRejectRequest` structs in `operator/src/api.rs` — JSON body schemas for POST endpoints
  - [x] 1.4 Add `POST /api/v1/investigations/:id/confirm` handler — accepts optional `comment: Option<String>`, patches Investigation CRD `status.phase` to `Completed` and sets `status.message` to `"Resolution confirmed by SRE"`
  - [x] 1.5 Add `POST /api/v1/investigations/:id/reject` handler — accepts `reason: String` (rejection category), `reason_details: Option<String>` (free text), `correction: Option<String>` (alternative action). Patches CRD `status.message` to `"Resolution rejected: {reason}"` but keeps phase as `AwaitingConfirmation` (story 4-6 handles final resolution)
  - [x] 1.6 Register new POST routes in `api_router_with_detection()` alongside existing GET routes: `.route("/api/v1/investigations/:id/confirm", post(confirm_investigation))` and `.route("/api/v1/investigations/:id/reject", post(reject_investigation))`
  - [x] 1.7 Add `axum::routing::post` to imports
  - [x] 1.8 Add unit tests: `ResolutionConfirmRequest` serialization, `ResolutionRejectRequest` serialization, `phase_to_status` for `AwaitingConfirmation`, `ProblemDetails` for confirm/reject 404 errors

- [x] Task 2: Extend InvestigationService with confirm/reject methods (AC: 2, 3, 4)
  - [x] 2.1 Add `confirm_resolution(investigation_id: str, comment: str | None = None) -> bool` method to `InvestigationService` — POST to `{operator_url}/api/v1/investigations/{id}/confirm` with JSON body `{"comment": comment}`. Returns True on success (200), False on 404. Raises `InvestigationServiceError` on connection errors
  - [x] 2.2 Add `reject_resolution(investigation_id: str, reason: str, reason_details: str | None = None, correction: str | None = None) -> bool` method — POST to `{operator_url}/api/v1/investigations/{id}/reject` with JSON body. Returns True on success, False on 404
  - [x] 2.3 Add `save_resolution_feedback(investigation_id: str, feedback: dict[str, Any]) -> None` method — upserts feedback dict into Qdrant `investigations` collection payload for the investigation (stores confirmation/rejection data alongside pipeline metadata for future learning in Epic 5)

- [x] Task 3: Add confirm/reject POST routes (AC: 1, 2, 3, 4)
  - [x] 3.1 Add `POST /investigations/<investigation_id>/confirm` route in `investigations.py` — reads `request.form.get("comment")`, calls `svc.confirm_resolution()`, calls `svc.save_resolution_feedback()` to persist feedback dict `{"resolution_action": "confirmed", "comment": comment, "confirmed_at": iso_timestamp, "confirmed_by": "sre"}` to Qdrant. Returns rendered `_confirmation_result.html` partial
  - [x] 3.2 Add `POST /investigations/<investigation_id>/reject` route — reads `request.form.get("rejection_reason")` (dropdown value), `request.form.get("reason_details")` (free text, required), `request.form.get("correction")` (optional alternative action). Validates that `rejection_reason` is in `VALID_REJECTION_REASONS`. Calls `svc.reject_resolution()` and `svc.save_resolution_feedback()` with feedback dict `{"resolution_action": "rejected", "rejection_reason": reason, "reason_details": details, "correction": correction, "rejected_at": iso_timestamp}`. Returns rendered `_confirmation_result.html` partial
  - [x] 3.3 Define `VALID_REJECTION_REASONS = {"hypothesis_incorrect", "insufficient_evidence", "better_alternative", "not_applicable", "other"}` constant for dropdown validation
  - [x] 3.4 Validate `investigation_id` with existing `SERVICE_NAME_PATTERN` check (reuse pattern from other routes)
  - [x] 3.5 Both POST routes return appropriate error partials on failure (operator down, investigation not found, validation error)

- [x] Task 4: Create confirmation form template (AC: 1, 2, 3, 4)
  - [x] 4.1 Create `ui/beeper_ui/templates/investigations/_confirmation_form.html` — HTMX form partial rendered below recommendations when investigation status is `awaiting_confirmation` or `completed` (with recommendations present). Contains two sections: Confirm form and Reject form
  - [x] 4.2 **Confirm section:** `<form hx-post="/investigations/{{ investigation.id }}/confirm" hx-target="#confirmation-result" hx-swap="outerHTML">` with optional textarea `name="comment"` (placeholder "Optional: Add a note about the confirmation..."), submit button "Confirm Resolution" (green, `.btn-confirm`)
  - [x] 4.3 **Reject section:** `<form hx-post="/investigations/{{ investigation.id }}/reject" hx-target="#confirmation-result" hx-swap="outerHTML">` with: (a) `<select name="rejection_reason">` dropdown with options: "Hypothesis incorrect", "Insufficient evidence", "Better alternative exists", "Not applicable", "Other", (b) `<textarea name="reason_details" required>` (placeholder "Explain why this recommendation should be rejected..."), (c) `<textarea name="correction">` (placeholder "Optional: Suggest the correct resolution action..."), submit button "Reject Resolution" (red, `.btn-reject`)
  - [x] 4.4 Both forms use `hx-indicator="#confirmation-loading"` with shared loading spinner
  - [x] 4.5 Wrap entire form in `<div id="confirmation-result">` so the result partial replaces the form on submission
  - [x] 4.6 Show form ONLY when `investigation.status == 'awaiting_confirmation'` — hide form and show status message for already confirmed/rejected states. Check `findings.get('resolution_action')` to detect prior action: if `"confirmed"` show green success banner, if `"rejected"` show amber rejection banner with reason

- [x] Task 5: Create confirmation result template (AC: 2, 3)
  - [x] 5.1 Create `ui/beeper_ui/templates/investigations/_confirmation_result.html` — result partial returned by POST routes, replaces `#confirmation-result` div
  - [x] 5.2 **Success state (confirm):** Green banner with checkmark, "Resolution confirmed" message, optional comment display, timestamp
  - [x] 5.3 **Success state (reject):** Amber banner with reason category, reason details, correction (if provided), "Rejection recorded" message
  - [x] 5.4 **Error state:** Red banner with error message (operator unreachable, investigation not found, validation error)
  - [x] 5.5 Follow existing result partial pattern from `knowledge/_import_result.html` (`.import-result` → `.confirmation-result`)

- [x] Task 6: Integrate confirmation form into detail page (AC: 1)
  - [x] 6.1 Update `_detail_content.html` to add a new card section "Resolution Confirmation" between Findings and Related KB sections: `<div class="card"><h3>Resolution Confirmation</h3><div id="confirmation-result">{% include "investigations/_confirmation_form.html" %}</div></div>`
  - [x] 6.2 Conditionally show the confirmation section: only when `findings.get('recommendations')` is not empty (recommendations must exist to confirm/reject). Hide when investigation status is `investigating` or `failed`
  - [x] 6.3 Add SSE support: `sse-swap="confirmation-update"` on `#confirmation-result` div so status changes propagate in real-time

- [x] Task 7: Add CSS styles for confirmation UI (AC: 1, 2, 3, 4)
  - [x] 7.1 Add `.confirmation-form` styles to `main.css`: card layout, separated confirm/reject sections with subtle divider
  - [x] 7.2 Add `.btn-confirm` styles: green background (`#22c55e`), white text, hover darkens, consistent with confidence-high color
  - [x] 7.3 Add `.btn-reject` styles: red background (`#ef4444`), white text, hover darkens, consistent with confidence-low color
  - [x] 7.4 Add form element styles: `.form-group` wrapper, `textarea` and `select` consistent with existing KB import form styling, `.confirmation-form label` styling
  - [x] 7.5 Add `.confirmation-result` styles: `.confirmation-success` (green tint), `.confirmation-rejected` (amber tint), `.confirmation-error` (red tint) — follow `.import-result` pattern
  - [x] 7.6 Add `.rejection-reason-display` styles: category badge, reason text, correction text (if present)
  - [x] 7.7 Add `.confirmation-status-banner` styles for already-confirmed/rejected display within the form area
  - [x] 7.8 Add `.confirmation-loading` indicator style

- [x] Task 8: Add SSE confirmation update event (AC: 2, 3)
  - [x] 8.1 Update `_generate_detail_sse_events()` in `investigations.py` to detect when `findings.get('resolution_action')` first appears (or changes) in Qdrant metadata — send `confirmation-update` SSE event with rendered `_confirmation_form.html` partial (which will show the confirmed/rejected status banner)
  - [x] 8.2 Track `last_resolution_action` in the SSE generator state alongside existing `last_findings_keys`

- [x] Task 9: Tests for confirmation workflow (AC: 1, 2, 3, 4)
  - [x] 9.1 Test `InvestigationService.confirm_resolution()` calls operator POST correctly and returns True on 200
  - [x] 9.2 Test `InvestigationService.confirm_resolution()` returns False on 404
  - [x] 9.3 Test `InvestigationService.reject_resolution()` calls operator POST with full body and returns True
  - [x] 9.4 Test `InvestigationService.reject_resolution()` returns False on 404
  - [x] 9.5 Test `InvestigationService.save_resolution_feedback()` upserts to Qdrant
  - [x] 9.6 Test `POST /investigations/<id>/confirm` with comment — returns success partial
  - [x] 9.7 Test `POST /investigations/<id>/confirm` without comment — returns success partial
  - [x] 9.8 Test `POST /investigations/<id>/reject` with valid reason and details — returns success partial
  - [x] 9.9 Test `POST /investigations/<id>/reject` with correction — returns success partial with correction displayed
  - [x] 9.10 Test `POST /investigations/<id>/reject` with invalid reason — returns error (validation fail)
  - [x] 9.11 Test `POST /investigations/<id>/reject` without reason_details — returns error (required field)
  - [x] 9.12 Test `POST /investigations/<id>/confirm` when operator is down — returns error partial
  - [x] 9.13 Test `POST /investigations/<id>/confirm` for nonexistent investigation — returns error partial
  - [x] 9.14 Test `GET /investigations/<id>` with `awaiting_confirmation` status shows confirmation form
  - [x] 9.15 Test `GET /investigations/<id>` with `investigating` status hides confirmation form
  - [x] 9.16 Test already-confirmed investigation shows green status banner instead of form
  - [x] 9.17 Test already-rejected investigation shows amber status banner instead of form
  - [x] 9.18 Test SSE `confirmation-update` event fires when resolution_action appears in findings
  - [x] 9.19 Test `investigation_id` validation on POST routes (invalid ID returns 404)

- [x] Task 10: Operator tests for confirm/reject endpoints (AC: 2, 3)
  - [x] 10.1 Test `ResolutionConfirmRequest` serialization with comment
  - [x] 10.2 Test `ResolutionConfirmRequest` serialization without comment (None)
  - [x] 10.3 Test `ResolutionRejectRequest` serialization with all fields
  - [x] 10.4 Test `ResolutionRejectRequest` serialization with minimal fields (just reason)
  - [x] 10.5 Test `phase_to_status` maps `AwaitingConfirmation` to `"awaiting_confirmation"`
  - [x] 10.6 Test `InvestigationPhase::AwaitingConfirmation` serde round-trip

- [x] Task 11: Integration verification (AC: 1, 2, 3, 4)
  - [x] 11.1 Run `ruff check` on all new/modified Python files — fix any issues
  - [x] 11.2 Run `mypy --strict` on all new/modified Python files — fix any issues
  - [x] 11.3 Run full Python test suite — verify zero regressions
  - [x] 11.4 Run `cargo check` on operator changes — verify compilation
  - [x] 11.5 Verify confirmation form renders correctly within investigation detail page (manual template inspection)
  - [x] 11.6 Update sprint-status.yaml: `4-5-resolution-confirmation: in-progress`

## Dev Notes

### Architecture Decision: Full-Stack Confirm/Reject Flow

Story 4-5 requires changes at **all three layers** (operator, service, UI) — unlike stories 4-3/4-4 which were template-only. The flow:

1. **Operator** adds `AwaitingConfirmation` phase to CRD + POST endpoints that patch the CRD status
2. **UI Service** sends POST requests to operator + persists feedback to Qdrant for Epic 5 learning
3. **UI Routes** handle HTMX form submissions and return result partials
4. **Templates** render confirm/reject forms with HTMX `hx-post` pattern

The CRD currently has phases: Pending, Running, Completed, Failed. Adding `AwaitingConfirmation` creates the intermediate state where recommendations exist but SRE hasn't acted. The UI already supports this status (VALID_STATUSES, sort order, CSS class `.investigation-status-awaiting_confirmation`).

### Critical: When Does `AwaitingConfirmation` Activate?

The investigator pipeline currently ends with phase=Completed. For story 4-5 to work, the pipeline (or operator reconciler) needs to set phase=AwaitingConfirmation instead of Completed when recommendations are generated. **However**, modifying the investigator pipeline is out of scope for this story. Instead:

**Pragmatic approach:** The confirmation form appears whenever `findings.get('recommendations')` is not empty AND investigation status is `awaiting_confirmation` OR `completed`. The operator POST endpoints work regardless of current phase. This lets the UI work even before the pipeline is updated to set the `AwaitingConfirmation` phase. A future story or patch can add the automatic phase transition.

### Data Flow: Confirm Action

```
SRE clicks "Confirm" →
  HTMX POST /investigations/<id>/confirm (form data: comment) →
    Flask route:
      1. svc.confirm_resolution(id, comment) → POST operator API
         → Operator patches CRD: phase=Completed, message="Resolution confirmed by SRE"
      2. svc.save_resolution_feedback(id, {...}) → Upsert Qdrant payload
         → Stores: resolution_action, comment, confirmed_at, confirmed_by
      3. Return _confirmation_result.html (success)
    HTMX swaps #confirmation-result with success partial
```

### Data Flow: Reject Action

```
SRE clicks "Reject" →
  HTMX POST /investigations/<id>/reject (form data: reason, details, correction) →
    Flask route:
      1. Validate rejection_reason in VALID_REJECTION_REASONS
      2. svc.reject_resolution(id, reason, details, correction) → POST operator API
         → Operator patches CRD: message="Resolution rejected: {reason}" (phase stays)
      3. svc.save_resolution_feedback(id, {...}) → Upsert Qdrant payload
         → Stores: resolution_action, rejection_reason, reason_details, correction, rejected_at
      4. Return _confirmation_result.html (rejection recorded)
    HTMX swaps #confirmation-result with rejection partial
```

### Qdrant Feedback Storage Schema

Feedback is stored as additional keys in the investigation's Qdrant payload (same document as pipeline metadata):

```python
# Confirm feedback
{
    "resolution_action": "confirmed",        # str: "confirmed" | "rejected"
    "resolution_comment": "Restarted OK",    # str | None
    "resolution_confirmed_at": "2026-03-07T12:30:00Z",  # ISO 8601
    "resolution_confirmed_by": "sre",        # str (hardcoded for MVP)
}

# Reject feedback
{
    "resolution_action": "rejected",
    "rejection_reason": "hypothesis_incorrect",  # str: one of VALID_REJECTION_REASONS
    "rejection_reason_details": "Root cause was actually the cache layer",
    "rejection_correction": "Clear Redis cache and restart service",
    "resolution_rejected_at": "2026-03-07T12:35:00Z",
}
```

These keys coexist with pipeline metadata (`recommendations`, `ranking_rationale`, etc.) in the same Qdrant point. Epic 5 (Living Knowledge) will read this feedback for learning.

### Rejection Reason Categories

```python
VALID_REJECTION_REASONS = {
    "hypothesis_incorrect",      # RCA hypothesis was wrong
    "insufficient_evidence",     # Need more data before acting
    "better_alternative",        # SRE knows a better fix
    "not_applicable",            # Recommendation doesn't apply to this situation
    "other",                     # Free-form — must provide reason_details
}
```

### Existing Patterns to Reuse

- **HTMX form POST pattern:** `knowledge/import.html` and `knowledge/edit.html` — `hx-post`, `hx-target`, `hx-swap="outerHTML"` for result replacement
- **Form styling:** `.form-group`, `textarea`, `select` from KB import form in `main.css`
- **Result partial pattern:** `knowledge/_import_result.html` — success/error banners with icons
- **Input validation:** `VALID_STATUSES`, `SERVICE_NAME_PATTERN` — reuse for rejection reason validation
- **Service error handling:** `InvestigationServiceError` try/except pattern in all route handlers
- **Qdrant upsert:** Follow `KBService` patterns for payload updates via `QdrantClient.set_payload()`
- **SSE event pattern:** `_generate_detail_sse_events()` tracking state changes — add `resolution_action` tracking
- **Badge CSS:** `.impact-badge`, `.confidence-badge`, `.risk-badge` — reuse sizing for rejection reason badges
- **Status badge:** `.investigation-status-awaiting_confirmation` CSS already exists in `main.css`

### Anti-Patterns to Avoid

- **DO NOT** create a new service class — extend existing `InvestigationService`
- **DO NOT** create new CSS files — add to existing `main.css`
- **DO NOT** use JavaScript for form validation — use HTML5 `required` attribute and server-side validation
- **DO NOT** create separate Qdrant collections for feedback — store in existing `investigations` collection payload
- **DO NOT** hardcode operator URLs in templates — use `url_for()` for all form action URLs
- **DO NOT** expose internal error details in error partials — use generic user-facing messages
- **DO NOT** modify the investigator pipeline — out of scope, confirmation works with any investigation that has recommendations
- **DO NOT** create new route files — add to existing `investigations.py`

### Key File Paths

| Component | Path | Action |
|-----------|------|--------|
| Investigation CRD (modify) | `operator/src/crds/investigation.rs` | Add `AwaitingConfirmation` phase |
| Operator API (modify) | `operator/src/api.rs` | Add POST confirm/reject endpoints, update `phase_to_status` |
| Investigation Service (modify) | `ui/beeper_ui/services/investigation_service.py` | Add `confirm_resolution`, `reject_resolution`, `save_resolution_feedback` |
| Investigation Routes (modify) | `ui/beeper_ui/routes/investigations.py` | Add POST routes, SSE event |
| Confirmation form (NEW) | `ui/beeper_ui/templates/investigations/_confirmation_form.html` | Confirm/reject HTMX forms |
| Confirmation result (NEW) | `ui/beeper_ui/templates/investigations/_confirmation_result.html` | Result feedback partials |
| Detail content (modify) | `ui/beeper_ui/templates/investigations/_detail_content.html` | Add confirmation section |
| CSS styles (modify) | `ui/beeper_ui/static/css/main.css` | Add confirmation form/result styles |
| Route tests (modify) | `ui/tests/test_investigation_routes.py` | Add confirmation workflow tests |
| Service tests (modify) | `ui/tests/test_investigation_service.py` | Add confirm/reject service tests |

### Testing Standards

- **pytest** with Flask test client for route tests
- **respx** for mocking operator HTTP POST calls
- **MagicMock** for Qdrant client in feedback persistence tests
- Test both success and error paths for confirm/reject
- Test HTMX partial responses (result partials replace form)
- Test form validation (invalid rejection reason, missing required fields)
- Test SSE `confirmation-update` event generation
- Test already-confirmed/rejected state display
- `ruff check` and `mypy --strict` on all modified Python files

### Previous Story Intelligence (from 4-4)

**Patterns established:**
- HTMX lazy-load pattern with SSE update targets
- KBService resource management with `close()` in `finally` blocks
- Template partials with `_` prefix naming convention
- Defensive dict access with `findings.get('key', default)`
- CSS class hierarchy following BEM-like naming

**Lessons learned (from 4-4 code review):**
- Always close service instances in `finally` blocks (both routes and SSE generators)
- Use `url_for()` instead of hardcoded URLs
- Clean up unused imports
- Type guards on template iteration (`{% if rec is mapping %}`)
- WCAG-compliant badge contrast ratios

**Test patterns:**
- Mock both operator API AND Qdrant returns
- Test full page + HTMX partial responses
- Test error handling: operator down, not found
- Test SSE event rendering and deduplication

### Project Structure Notes

- New templates follow existing `_` prefix partial naming in `templates/investigations/`
- POST routes are new to investigations blueprint — first mutation endpoints
- Qdrant `set_payload` is new to `InvestigationService` — follow `KBService` update patterns
- No new Python dependencies required
- No new JavaScript required — HTMX handles form submission natively

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 4, Story 4.5]
- [Source: operator/src/crds/investigation.rs — InvestigationPhase enum, InvestigationStatus struct]
- [Source: operator/src/api.rs — phase_to_status(), POST endpoint patterns (none exist yet — first mutation)]
- [Source: ui/beeper_ui/routes/investigations.py — existing GET routes, SSE generator, HTMX patterns]
- [Source: ui/beeper_ui/services/investigation_service.py — InvestigationService, Qdrant client]
- [Source: ui/beeper_ui/templates/investigations/_recommendations.html — current recommendation display]
- [Source: ui/beeper_ui/templates/investigations/_detail_content.html — detail page card layout]
- [Source: ui/beeper_ui/templates/knowledge/import.html — HTMX form POST pattern reference]
- [Source: ui/beeper_ui/templates/knowledge/_import_result.html — result partial pattern reference]
- [Source: _bmad-output/implementation-artifacts/4-4-kb-entry-navigation.md — previous story patterns]
- [Source: _bmad-output/implementation-artifacts/4-3-recommendations-confidence-display.md — recommendations data schema]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created
- Full-stack story: operator CRD + API, UI service, routes, templates, CSS
- First mutation (POST) endpoints in both operator and UI investigations
- Qdrant feedback storage coexists with pipeline metadata in same collection
- Rejection reasons: hypothesis_incorrect, insufficient_evidence, better_alternative, not_applicable, other
- Confirmation form uses HTMX hx-post with result partial swap pattern (from KB import)
- SSE confirmation-update event for real-time status propagation
- Previous story 4-4 review fixes inform resource management patterns
- Investigation status `awaiting_confirmation` already supported in UI (CSS, sort order, filters)
- 11 tasks: CRD phase, operator endpoints, service methods, POST routes, form template, result template, detail integration, CSS, SSE event, UI tests, operator tests, integration verification

### Change Log

- Tasks 1-8: Full implementation of operator CRD phase + API endpoints, UI service methods, POST routes, HTMX templates, CSS styles, SSE event
- Tasks 9-10: Added 10 service tests (TestConfirmResolution, TestRejectResolution, TestSaveResolutionFeedback) + 19 route tests (TestResolutionConfirmation)
- Task 11: Integration verification — 385 total tests pass, ruff clean, mypy clean on investigation files

### File List

| File | Action |
|------|--------|
| `operator/src/crds/investigation.rs` | Modified — added `AwaitingConfirmation` phase variant + 2 tests |
| `operator/src/api.rs` | Modified — added POST confirm/reject routes, handlers, request/response structs, phase_to_status mapping, 8 tests |
| `ui/beeper_ui/services/investigation_service.py` | Modified — added `confirm_resolution()`, `reject_resolution()`, `save_resolution_feedback()` methods |
| `ui/beeper_ui/routes/investigations.py` | Modified — added POST confirm/reject routes, `VALID_REJECTION_REASONS`, `REJECTION_REASON_LABELS`, SSE `confirmation-update` event |
| `ui/beeper_ui/templates/investigations/_confirmation_form.html` | Created — HTMX confirm/reject forms + status banners |
| `ui/beeper_ui/templates/investigations/_confirmation_result.html` | Created — result partial (confirmed/rejected/error states) |
| `ui/beeper_ui/templates/investigations/_detail_content.html` | Modified — added Resolution Confirmation card section |
| `ui/beeper_ui/static/css/main.css` | Modified — added ~180 lines for confirmation UI styling |
| `ui/tests/test_investigation_service.py` | Modified — added 10 new tests (TestConfirmResolution, TestRejectResolution, TestSaveResolutionFeedback) |
| `ui/tests/test_investigation_routes.py` | Modified — added 19 new tests (TestResolutionConfirmation) |
