# Story 3.4: One-Click Investigation Feedback

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an **SRE**,
I want to provide one-click feedback on investigation accuracy (accurate / inaccurate / not-an-issue),
so that Beeper can learn from my expertise and improve over time.

## Acceptance Criteria

1. **Given** a completed investigation displayed in the UI
   **When** the SRE clicks one of the feedback buttons (accurate / inaccurate / not-an-issue)
   **Then** the feedback is recorded against the investigation in Qdrant with the user, timestamp, and feedback type
   **And** the interaction is a single click — no modal, no form, no confirmation required

2. **Given** feedback is submitted
   **When** the investigation detail page refreshes
   **Then** the selected feedback is highlighted and changing feedback is allowed (last feedback wins)
   **And** an SSE event updates other viewers in real-time

3. **Given** the feedback endpoint (`POST /investigations/<id>/feedback`)
   **When** accessed by any authenticated user (admin or user)
   **Then** the feedback is accepted (not admin-only — all SREs should provide feedback)

## Tasks / Subtasks

- [x] Task 1: Add feedback constants and route to investigations.py (AC: #1, #3)
  - [x] 1.1 Add `VALID_FEEDBACK_TYPES = {"accurate", "inaccurate", "not_an_issue"}` constant
  - [x] 1.2 Add `FEEDBACK_TYPE_LABELS = {"accurate": "Accurate", "inaccurate": "Inaccurate", "not_an_issue": "Not an Issue"}` constant
  - [x] 1.3 Add `POST /investigations/<id>/feedback` route with `@require_role("user")` decorator
  - [x] 1.4 Validate `investigation_id` against `SERVICE_NAME_PATTERN` (existing pattern)
  - [x] 1.5 Read `feedback_type` from `request.form.get("feedback_type")`
  - [x] 1.6 Validate `feedback_type` against `VALID_FEEDBACK_TYPES` whitelist — return 400 error partial if invalid
  - [x] 1.7 Read user identity from `request.headers.get("X-Beeper-User", "anonymous")` header
  - [x] 1.8 Save feedback via `InvestigationService.save_resolution_feedback()` with keys: `investigation_feedback`, `investigation_feedback_by`, `investigation_feedback_at`
  - [x] 1.9 Return HTMX partial `_feedback_result.html` showing the updated button state

- [x] Task 2: Create feedback HTMX templates (AC: #1, #2)
  - [x] 2.1 Create `ui/beeper_ui/templates/investigations/_feedback_buttons.html` — three buttons (accurate / inaccurate / not-an-issue) with `hx-post` to `/investigations/{{ investigation.id }}/feedback`, `hx-target="#feedback-section"`, `hx-swap="innerHTML"`
  - [x] 2.2 Each button submits a hidden `feedback_type` field via the HTMX `hx-vals` attribute
  - [x] 2.3 Highlight the currently selected feedback type using a CSS class (`.feedback-btn-selected`) when `current_feedback` matches the button's type
  - [x] 2.4 Style: use existing `.btn` classes with color variants — accurate (green/success), inaccurate (red/danger), not-an-issue (gray/secondary)
  - [x] 2.5 No modal, no form fields, no confirmation — single click only
  - [x] 2.6 Create `ui/beeper_ui/templates/investigations/_feedback_result.html` — same buttons layout but with the selected button highlighted, plus a subtle success message

- [x] Task 3: Integrate feedback section into investigation detail page (AC: #1, #2)
  - [x] 3.1 Add "Investigation Feedback" card section in `_detail_content.html` — show for investigations not in `investigating` or `failed` status
  - [x] 3.2 Include `_feedback_buttons.html` partial inside a `div#feedback-section` with `sse-swap="feedback-update"` and `hx-swap="innerHTML"` for real-time updates
  - [x] 3.3 Pass `current_feedback` from `findings.get('investigation_feedback', '')` to template for initial highlight state
  - [x] 3.4 Position the feedback section after the Confidence Gate card and before Resolution Confirmation

- [x] Task 4: Add SSE feedback-update event to investigation stream (AC: #2)
  - [x] 4.1 In `_generate_detail_sse_events()`, add tracking for `investigation_feedback` key changes
  - [x] 4.2 Add `last_investigation_feedback: str | None = None` tracker variable
  - [x] 4.3 When `investigation_feedback` value changes, render `_feedback_buttons.html` with updated `current_feedback`
  - [x] 4.4 Emit `feedback-update` SSE event with the rendered partial

- [x] Task 5: Comprehensive testing (AC: #1, #2, #3)
  - [x] 5.1 Create `ui/tests/test_investigation_feedback.py` — all feedback-related tests:
    - Test POST feedback with "accurate" → 200 + highlighted partial
    - Test POST feedback with "inaccurate" → 200 + highlighted partial
    - Test POST feedback with "not_an_issue" → 200 + highlighted partial
    - Test POST feedback with invalid type → 400 error
    - Test POST feedback with empty type → 400 error
    - Test POST feedback with boolean type → 400 error
    - Test POST feedback for non-existent investigation → saves gracefully (existing save_resolution_feedback pattern)
    - Test POST feedback with invalid investigation ID → 404
    - Test feedback accessible by user role (not admin-only)
    - Test feedback records X-Beeper-User header value
    - Test feedback records timestamp
    - Test changing feedback overwrites previous (last wins)
    - Test detail page includes feedback section for completed investigations
    - Test detail page excludes feedback section for investigating status
    - Test detail page excludes feedback section for failed status
  - [x] 5.2 Run full UI test suite — verify zero regressions
  - [x] 5.3 Run ruff lint on all new/modified files — all clean

## Dev Notes

### Architecture Patterns to Follow

**CRITICAL CONTEXT: This story adds ONE-CLICK feedback — completely separate from the existing confirm/reject/resolve workflow.** The existing resolution workflow (confirm → reject → resolve with outcomes) is a complex multi-step process. Story 3-4 adds a SIMPLE, orthogonal "was this investigation useful?" feedback mechanism for Beeper's learning loop. Both can coexist on the same investigation.

**What already exists (DO NOT recreate):**

| Component | Location | Status |
|-----------|----------|--------|
| `InvestigationService` | `ui/beeper_ui/services/investigation_service.py` | Done (v0.1.0) |
| `save_resolution_feedback(id, dict)` | Upserts arbitrary dict to Qdrant `investigations` collection | Done |
| `get_investigation_findings(id)` | Returns all Qdrant payload for investigation | Done |
| `investigations_bp` Blueprint | `/investigations` URL prefix | Done |
| `_detail_content.html` | Investigation detail page layout with SSE | Done |
| `_generate_detail_sse_events()` | SSE stream with event tracking | Done |
| `SERVICE_NAME_PATTERN` | ID validation regex | Done |
| `@require_role("user")` | Permission decorator | Done |
| `X-Beeper-User` header | User identity pattern | Done |

**What this story adds:**

| Component | Description |
|-----------|-------------|
| `VALID_FEEDBACK_TYPES` constant | `{"accurate", "inaccurate", "not_an_issue"}` |
| `FEEDBACK_TYPE_LABELS` constant | Human-readable labels |
| `POST /investigations/<id>/feedback` route | One-click feedback submission |
| `_feedback_buttons.html` template | HTMX partial with three feedback buttons |
| `_feedback_result.html` template | HTMX partial for post-submission state |
| Feedback section in `_detail_content.html` | Integration with SSE |
| `feedback-update` SSE event | Real-time cross-viewer updates |
| `test_investigation_feedback.py` | Comprehensive test coverage |

**Route Pattern (follow existing confirm/reject routes in `investigations.py`):**
```python
VALID_FEEDBACK_TYPES = {"accurate", "inaccurate", "not_an_issue"}

FEEDBACK_TYPE_LABELS = {
    "accurate": "Accurate",
    "inaccurate": "Inaccurate",
    "not_an_issue": "Not an Issue",
}

@investigations_bp.route("/<investigation_id>/feedback", methods=["POST"])
@require_role("user")
def submit_investigation_feedback(investigation_id: str) -> str | tuple[str, int]:
    """Submit one-click investigation feedback (accurate/inaccurate/not-an-issue)."""
    if not SERVICE_NAME_PATTERN.match(investigation_id):
        abort(404)

    feedback_type = (request.form.get("feedback_type") or "").strip()
    if feedback_type not in VALID_FEEDBACK_TYPES:
        return render_template(
            "investigations/_feedback_result.html",
            error_message="Invalid feedback type.",
            current_feedback="",
            investigation_id=investigation_id,
        ), 400

    user = request.headers.get("X-Beeper-User", "anonymous")
    now = datetime.now(timezone.utc).isoformat()

    svc = get_investigation_service()
    try:
        svc.save_resolution_feedback(investigation_id, {
            "investigation_feedback": feedback_type,
            "investigation_feedback_by": user,
            "investigation_feedback_at": now,
        })
    finally:
        svc.close()

    feedback_label = FEEDBACK_TYPE_LABELS.get(feedback_type, feedback_type)
    return render_template(
        "investigations/_feedback_result.html",
        current_feedback=feedback_type,
        feedback_label=feedback_label,
        investigation_id=investigation_id,
        feedback_by=user,
        feedback_at=now,
    )
```

**HTMX Template Pattern (`_feedback_buttons.html`):**
```html
<div class="feedback-buttons">
    <p class="feedback-prompt">Was this investigation accurate?</p>
    <div class="feedback-btn-group">
        <button class="btn btn-sm feedback-btn feedback-accurate {{ 'feedback-btn-selected' if current_feedback == 'accurate' }}"
                hx-post="/investigations/{{ investigation_id }}/feedback"
                hx-target="#feedback-section"
                hx-swap="innerHTML"
                hx-vals='{"feedback_type": "accurate"}'
                type="button">
            Accurate
        </button>
        <button class="btn btn-sm feedback-btn feedback-inaccurate {{ 'feedback-btn-selected' if current_feedback == 'inaccurate' }}"
                hx-post="/investigations/{{ investigation_id }}/feedback"
                hx-target="#feedback-section"
                hx-swap="innerHTML"
                hx-vals='{"feedback_type": "inaccurate"}'
                type="button">
            Inaccurate
        </button>
        <button class="btn btn-sm feedback-btn feedback-not-an-issue {{ 'feedback-btn-selected' if current_feedback == 'not_an_issue' }}"
                hx-post="/investigations/{{ investigation_id }}/feedback"
                hx-target="#feedback-section"
                hx-swap="innerHTML"
                hx-vals='{"feedback_type": "not_an_issue"}'
                type="button">
            Not an Issue
        </button>
    </div>
</div>
```

**Integration in `_detail_content.html` — add after Confidence Gate, before Resolution Confirmation:**
```html
{# Investigation Feedback (One-Click) #}
{% if investigation.status not in ('investigating', 'failed') %}
<div class="card">
    <h3>Investigation Feedback</h3>
    <div id="feedback-section" sse-swap="feedback-update" hx-swap="innerHTML">
        {% include "investigations/_feedback_buttons.html" %}
    </div>
</div>
{% endif %}
```

**SSE Event Addition (in `_generate_detail_sse_events()`):**
```python
# After existing resolution_outcome tracking block
# Track investigation feedback changes
last_investigation_feedback: str | None = None  # Add as tracker variable at top

# In the findings check section:
current_inv_feedback = str(findings.get("investigation_feedback", "")) or None
if current_inv_feedback != last_investigation_feedback:
    feedback_html = render_template(
        "investigations/_feedback_buttons.html",
        current_feedback=current_inv_feedback or "",
        investigation_id=investigation_id,
    )
    feedback_lines = "\n".join(
        f"data: {line}" for line in feedback_html.split("\n")
    )
    yield f"event: feedback-update\n{feedback_lines}\n\n"
    last_investigation_feedback = current_inv_feedback
```

**Qdrant Payload Keys (stored in `investigations` collection):**
```python
{
    "investigation_feedback": "accurate",        # feedback type
    "investigation_feedback_by": "sre@company.com",  # X-Beeper-User
    "investigation_feedback_at": "2026-03-16T...",    # ISO 8601 timestamp
}
```

### Critical Guardrails

- **No new pip dependencies** — reuse existing InvestigationService
- **No new Blueprints** — add route to existing `investigations_bp`
- **No new service classes** — use existing `InvestigationService.save_resolution_feedback()`
- **No new Qdrant collections** — store feedback in existing `investigations` collection
- **No modals, no forms, no confirmation** — single click only (AC #1)
- **Not admin-only** — `@require_role("user")` (all authenticated users, AC #3)
- **Last feedback wins** — overwrite on each click, no history (AC #2)
- **Follow HTMX patterns** — server renders HTML, HTMX swaps partials, `hx-vals` for form data
- **No Tailwind** — use existing `main.css` BEM classes (`.btn`, `.card`)
- **Test isolation** — mock `InvestigationService.save_resolution_feedback()` and `get_investigation_findings()` in tests
- **ID validation** — use existing `SERVICE_NAME_PATTERN` regex
- **No client-side JS** — HTMX handles everything
- **Separate from resolution workflow** — this is orthogonal to confirm/reject/resolve

### Project Structure Notes

- Investigation routes: `ui/beeper_ui/routes/investigations.py` (modify — add feedback route + constants)
- Investigation templates: `ui/beeper_ui/templates/investigations/` (add new partials)
- Investigation detail layout: `ui/beeper_ui/templates/investigations/_detail_content.html` (modify — add feedback section)
- Investigation service: `ui/beeper_ui/services/investigation_service.py` (DO NOT modify — reuse `save_resolution_feedback()`)
- SSE generator: in `investigations.py` `_generate_detail_sse_events()` (modify — add feedback tracking)
- All tests: `ui/tests/` (add new test file)

### Previous Story Intelligence

**From Story 3-3 (Confidence Gate Threshold Configuration):**
- HTMX lazy-load pattern with `hx-get` + `hx-trigger="load"` for sections
- Card-based UI with `.card` wrapper pattern
- `hx-post` for form submissions, `hx-target` for partial replacement
- Full UI suite at ~1197 tests, zero regressions

**From Story 3-2 (Confidence Gate Engine):**
- SSE event additions: added gate-status lazy-load to `_detail_content.html`
- `sse-swap` attribute for real-time updates on partials
- Pattern for tracking field changes in `_generate_detail_sse_events()`

**From Story 3-1 (Trust Level Configuration):**
- `X-Beeper-User` header for user identity with sensible default
- HTMX partial pattern: `hx-post` → server renders result → `hx-swap="innerHTML"`
- `InvestigationService` lifecycle: create → try/except → finally: svc.close()
- `request.form.get()` for POST data extraction

**From Existing Investigation Routes (confirm/reject/resolve):**
- ID validation pattern: `SERVICE_NAME_PATTERN.match(investigation_id)` → `abort(404)`
- Error handling: return error template with 400/404/503 status codes
- Feedback saved via `save_resolution_feedback(investigation_id, dict)` — upserts to Qdrant
- SSE tracking pattern: `last_*` variables detect changes, render partial, yield event

### Git Intelligence

Recent commits: `MAESTRO: 3-3 done` → `MAESTRO: implement story 3-3 (Confidence Gate Threshold Configuration)`. Follow commit pattern: `MAESTRO: implement story 3-4 (One-Click Investigation Feedback)`. Current test count: UI ~1197 passed. Investigator: 505 passed.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 3, Story 3.4] — User story, acceptance criteria
- [Source: _bmad-output/planning-artifacts/epics.md#FR19] — "Users can provide one-click investigation feedback (accurate / inaccurate / not-an-issue)"
- [Source: _bmad-output/planning-artifacts/architecture.md#FR19] — "ui/routes/investigations.py, ui/templates/investigations/detail.html"
- [Source: ui/beeper_ui/routes/investigations.py] — Existing investigation routes with confirm/reject/resolve patterns
- [Source: ui/beeper_ui/services/investigation_service.py] — InvestigationService with save_resolution_feedback()
- [Source: ui/beeper_ui/templates/investigations/_detail_content.html] — Investigation detail layout with SSE
- [Source: ui/beeper_ui/templates/investigations/detail.html] — Full page with SSE ext
- [Source: ui/beeper_ui/middleware/permissions.py] — Permission model (require_role decorator)
- [Source: _bmad-output/implementation-artifacts/3-3-confidence-gate-threshold-configuration.md] — Story 3-3 patterns
- [Source: _bmad-output/implementation-artifacts/3-2-confidence-gate-engine.md] — Story 3-2 SSE patterns

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Added one-click investigation feedback mechanism — completely orthogonal to existing confirm/reject/resolve workflow
- Created `POST /investigations/<id>/feedback` route with `@require_role("user")` — any authenticated user can provide feedback (AC #3)
- Three feedback types: accurate, inaccurate, not_an_issue — single-click with no modal/form/confirmation (AC #1)
- Feedback stored in Qdrant `investigations` collection via existing `save_resolution_feedback()` with keys: `investigation_feedback`, `investigation_feedback_by`, `investigation_feedback_at`
- Created `_feedback_buttons.html` HTMX partial with three buttons using `hx-vals` for form-less submission
- Created `_feedback_result.html` HTMX partial for post-submission state with highlighted selection and success message
- Integrated feedback section in `_detail_content.html` after Confidence Gate, before Resolution Confirmation
- Feedback section shows for completed/awaiting_confirmation investigations, hidden for investigating/failed (AC #1)
- Existing feedback highlighted via `.feedback-btn-selected` CSS class; last feedback wins on change (AC #2)
- Added `feedback-update` SSE event to `_generate_detail_sse_events()` for real-time cross-viewer updates (AC #2)
- `X-Beeper-User` header for identity tracking; defaults to "anonymous"
- 19 new tests (14 route + 5 integration), all passing
- Full UI suite: 1216 passed (1197 existing + 19 new), zero regressions
- Ruff lint: all clean on new/modified Python files

### File List

**New files created:**
1. `ui/beeper_ui/templates/investigations/_feedback_buttons.html` — HTMX partial with three one-click feedback buttons
2. `ui/beeper_ui/templates/investigations/_feedback_result.html` — HTMX partial for feedback submission result
3. `ui/tests/test_investigation_feedback.py` — 19 tests for feedback route and detail page integration

**Files modified:**
1. `ui/beeper_ui/routes/investigations.py` — Added `VALID_FEEDBACK_TYPES`, `FEEDBACK_TYPE_LABELS` constants, `submit_investigation_feedback()` route, `require_role` import, SSE `feedback-update` event tracking
2. `ui/beeper_ui/templates/investigations/_detail_content.html` — Added "Investigation Feedback" card section with SSE swap
3. `_bmad-output/implementation-artifacts/sprint-status.yaml` — Story 3-4 status updates
4. `_bmad-output/implementation-artifacts/3-4-one-click-investigation-feedback.md` — This story file
