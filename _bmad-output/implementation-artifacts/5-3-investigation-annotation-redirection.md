# Story 5.3: Investigation Annotation & Redirection

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **user**,
I want to annotate, redirect, and comment on active investigations,
so that I can steer Beeper's investigation when I have domain knowledge it lacks.

## Acceptance Criteria

1. **Given** an active investigation **When** a user adds an annotation (free-text comment) **Then** the annotation is attached to the current investigation step with user, timestamp, and context **And** all connected users see the annotation in real-time via WebSocket

2. **Given** an active investigation heading in a wrong direction **When** a user sends a redirect command (e.g., "Focus on the database connection pool, not the API gateway") **Then** Beeper acknowledges the redirect, adjusts its investigation focus, and explains what changed **And** the redirect is logged in the investigation timeline as a human intervention

3. **Given** investigation annotations and redirects **When** the investigation is later reviewed **Then** all human interventions are visible in the timeline, distinguished from Beeper's autonomous steps

## Tasks / Subtasks

- [x] Task 1: Add `annotate` and `redirect` WebSocket event handlers (AC: #1, #2)
  - [x] 1.1 In `ui/beeper_ui/websocket/investigation.py`, add `@socketio.on("annotate")` handler — validates `investigation_id` and `text` fields, calls `InvestigationService.annotate_investigation()`, stores `CollaborationMessage(message_type="annotation")` via `CollaborationService`, broadcasts `annotation_added` event to room
  - [x] 1.2 Add `@socketio.on("redirect")` handler — validates `investigation_id` and `instruction` fields, calls `InvestigationService.redirect_investigation()`, stores `CollaborationMessage(message_type="redirect")`, broadcasts `investigation_redirected` event to room
  - [x] 1.3 For both handlers: emit `"error"` event on missing fields (follow `handle_send_message` validation pattern), use `_get_user()`, `_room_name()`, `_now_iso()` helpers
  - [x] 1.4 Write tests in `ui/tests/test_websocket.py` — add `TestAnnotateInvestigation` and `TestRedirectInvestigation` classes following existing `TestSendMessage` pattern: test missing fields → error, valid annotation → stored + broadcast, valid redirect → stored + broadcast, operator failure → still works

- [x] Task 2: Add `annotate_investigation` and `redirect_investigation` methods to InvestigationService (AC: #1, #2)
  - [x] 2.1 In `ui/beeper_ui/services/investigation_service.py`, add `annotate_investigation(self, investigation_id: str, text: str, user: str) -> bool` — POST to `{operator_url}/api/v1/investigations/{investigation_id}/annotate` with JSON `{"text": text, "user": user}`. Return `False` on 404, return `False` gracefully on other errors.
  - [x] 2.2 Add `redirect_investigation(self, investigation_id: str, instruction: str, user: str) -> bool` — POST to `{operator_url}/api/v1/investigations/{investigation_id}/redirect` with JSON `{"instruction": instruction, "user": user}`. Return `False` on 404, return `False` gracefully on other errors.
  - [x] 2.3 Write unit tests in `ui/tests/test_investigation_service.py` for both methods — mock HTTP calls, test success (200), not-found (404), server error (500), payload validation

- [x] Task 3: Update collaboration panel template with annotation/redirect action buttons (AC: #1, #2, #3)
  - [x] 3.1 In `ui/beeper_ui/templates/investigations/_collaboration_panel.html`, add an action bar below the message input with "Annotate" and "Redirect" buttons (inline, no modals per UX spec)
  - [x] 3.2 Annotate button reveals an inline annotation input area (replaces or appears above the standard message input). Redirect button reveals a separate inline redirect instruction input area.
  - [x] 3.3 Each input area has its own placeholder text ("Add annotation..." / "Redirect: describe new investigation focus...") and submit/cancel buttons
  - [x] 3.4 Redirect button disabled when investigation status is not `"investigating"` — uses `data-investigation-status` attribute on `#collab-panel` set from template context

- [x] Task 4: Update JavaScript client with annotation/redirect emit and receive handlers (AC: #1, #2, #3)
  - [x] 4.1 In `ui/beeper_ui/static/js/investigation-collab.js`, add `submitAnnotation()` and `toggleAnnotationInput()` functions that emit `annotate` event
  - [x] 4.2 Add `submitRedirect()` and `toggleRedirectInput()` functions that emit `redirect` event
  - [x] 4.3 Add `socket.on("annotation_added", ...)` handler — calls `appendMessage()` to display annotation in collaboration panel
  - [x] 4.4 Add `socket.on("investigation_redirected", ...)` handler — calls `appendMessage()` to display redirect in collaboration panel
  - [x] 4.5 Extend `appendMessage()` discriminator: `message_type === "annotation"` renders with `collab-annotation` CSS class (distinct styling: left border accent, "Annotation" label). `message_type === "redirect"` renders with `collab-redirect` CSS class (distinct styling: left border accent, "Redirect" label).
  - [x] 4.6 Add keyboard shortcut: `n` key (when not focused on an input) toggles annotation input; `r` key (not in input) toggles redirect input. Enter submits, Escape cancels.

- [x] Task 5: Add annotation/redirect CSS styles and update detail template (AC: #3)
  - [x] 5.1 In `ui/beeper_ui/static/css/main.css`, add styles for `.collab-annotation` (left border `#22c55e` green accent), `.collab-redirect` (left border `#f59e0b` amber accent), `.collab-action-bar`, `.collab-action-input`, base collaboration panel styles, and human interventions review styles
  - [x] 5.2 In `ui/beeper_ui/templates/investigations/_detail_content.html`, add "Human Interventions" section visible when annotations/redirects exist — shows annotation and redirect messages filtered from collaboration history, visually distinguished from Beeper's autonomous steps (AC: #3)
  - [x] 5.3 Template tests verifying: annotation/redirect elements present, redirect button disabled for non-investigating statuses, status data attribute present

- [x] Task 6: Run full test suite across all components (AC: all)
  - [x] 6.1 Run UI tests: `cd ui && poetry run python -m pytest` — 1517 passed (1492 existing + 25 new)
  - [x] 6.2 Run investigator tests: `cd investigator && poetry run python -m pytest` — 888 passed, 3 skipped
  - [x] 6.3 Run operator tests: `cargo test` — 531 passed
  - [x] 6.4 No regressions found

## Dev Notes

### Architecture Patterns (CRITICAL — must follow)

**Two-Channel Pattern:**
- SocketIO handles ONLY collaboration: messages, annotations, redirections, approvals
- SSE (existing) continues handling: step progress, findings updates, evidence streaming
- Do NOT migrate SSE events to SocketIO — they coexist

**WebSocket Event Contract (from architecture.md):**
```
# Client → Server (new for 5-3)
annotate(investigation_id, text)          # Human annotation
redirect(investigation_id, instruction)   # Redirect investigation

# Server → Client broadcast (new for 5-3)
annotation_added(message)                 # Annotation broadcast to room
investigation_redirected(message)         # Redirect broadcast to room
```

**Handler Pattern (mirror existing `handle_send_message`):**
```python
@socketio.on("annotate")
def handle_annotate(data: dict) -> None:
    investigation_id = data.get("investigation_id", "")
    text = data.get("text", "").strip()
    if not investigation_id or not text:
        emit("error", {"message": "investigation_id and text are required"})
        return
    user = _get_user()
    room = _room_name(investigation_id)
    # 1. Call operator API
    svc = InvestigationService.get_instance()
    svc.annotate_investigation(investigation_id, text, user)
    # 2. Store in collaboration history
    message = CollaborationMessage(
        id=str(uuid.uuid4()),
        investigation_id=investigation_id,
        user=user, role=user,
        message_type="annotation",
        content=text,
        timestamp=_now_iso(),
    )
    collab = get_collaboration_service()
    collab.store_message(message)
    # 3. Broadcast to room
    emit("annotation_added", message.to_payload(), room=room)
```

**Redirect handler** follows same shape but:
- Validates investigation status == `"investigating"` before forwarding to operator
- Uses `message_type="redirect"` and `data["instruction"]` field
- Emits `"investigation_redirected"` instead of `"annotation_added"`

**Operator API Endpoints (already specified in architecture):**
```
POST /api/v1/investigations/{id}/annotate    → {"text": "...", "user": "..."}
POST /api/v1/investigations/{id}/redirect    → {"instruction": "...", "user": "..."}
```
The operator may not have these endpoints implemented yet — the UI service methods should handle non-existent endpoints gracefully (log warning, don't crash). The annotation and redirect are still persisted in collaboration history and broadcast to the room regardless of operator response.

**CollaborationMessage type field — new values:**
- `"annotation"` — human annotation on investigation step
- `"redirect"` — human redirect instruction to change investigation focus
- Existing values: `"user_message"`, `"system_response"`, `"user_joined"`, `"user_left"`
- No schema change needed — `message_type` is a free string field

**UX Rules (from UX spec — NO EXCEPTIONS):**
- No modal confirmations for any primary action
- Keyboard shortcuts: `n` for annotate, `r` for redirect (when not in input)
- Reject/redirect: inline text input appears → submit → status changes
- Every primary workflow must be completable via keyboard

### Anti-Patterns to AVOID

- Do NOT create a new service class — use existing `CollaborationService` for persistence and `InvestigationService` for operator calls
- Do NOT add new Qdrant collections — annotations/redirects stored in existing `collaboration_messages` collection as `CollaborationMessage` with appropriate `message_type`
- Do NOT create modal dialogs for annotation or redirect input
- Do NOT replace SSE events with SocketIO for existing investigation updates
- Do NOT add new Flask routes for annotations/redirects — these are pure WebSocket actions
- Do NOT import or use any new dependencies — everything needed is already installed

### SSE Auto-Pickup for Redirects

After a redirect is sent to the operator, the operator changes the investigation pipeline state. The existing SSE stream polls every 3 seconds and automatically picks up new `step_states` and `findings`, pushing `step-update` and `findings-update` events to the UI. No SSE changes are needed for redirect effects to be visible.

### Previous Story Intelligence (5-2)

**Key learnings from Story 5-2 (Evidence Presentation with References):**
- SSE test regressions caused by new events — check `range()` calls in SSE test assertions if adding new SSE events
- Evidence service follows singleton pattern — any new service methods should too
- Template partials use `_` prefix naming convention
- CSS classes follow `.evidence-*` and `.collab-*` namespace patterns
- 42 unit tests + 21 template tests — maintain similar coverage ratio

**Key learnings from Story 5-1 (WebSocket Collaboration Channel):**
- Flask-SocketIO handler import must occur BEFORE `init_app()` — handlers already imported in `websocket/__init__.py`
- `leave_room()` must be called AFTER broadcasting events
- Module-scoped `ws_app` fixture needed in test_websocket.py
- SocketIO test client validates events synchronously (< 500ms inherent)

### Project Structure Notes

**Files to modify:**
- `ui/beeper_ui/websocket/investigation.py` — Add `annotate` and `redirect` event handlers
- `ui/beeper_ui/services/investigation_service.py` — Add `annotate_investigation()` and `redirect_investigation()` methods
- `ui/beeper_ui/templates/investigations/_collaboration_panel.html` — Add action bar with Annotate/Redirect buttons
- `ui/beeper_ui/static/js/investigation-collab.js` — Add emit/receive handlers, keyboard shortcuts, extended `appendMessage()`
- `ui/beeper_ui/static/css/main.css` — Add annotation/redirect CSS styles
- `ui/beeper_ui/templates/investigations/_detail_content.html` — Add annotations section for review view (AC: #3)
- `ui/tests/test_websocket.py` — Add `TestAnnotateInvestigation` and `TestRedirectInvestigation` test classes

**Files to NOT touch:**
- `ui/beeper_ui/websocket/__init__.py` — No changes needed (handler import already set up)
- `ui/beeper_ui/services/collaboration_service.py` — No changes needed (existing `store_message` and `get_message_history` work for new message types)
- `ui/beeper_ui/app.py` — No changes needed
- Any investigator or operator files — this story is UI-only

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.3] — Acceptance criteria and story statement
- [Source: _bmad-output/planning-artifacts/architecture.md#WebSocket Architecture] — Two-channel pattern, annotate/redirect event contracts
- [Source: _bmad-output/planning-artifacts/architecture.md#Operator API] — POST /annotate and /redirect endpoints
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Keyboard Shortcuts] — n=annotate, r=redirect, no modals
- [Source: ui/beeper_ui/websocket/investigation.py] — Existing handler pattern (handle_send_message, _get_user, _room_name, _now_iso)
- [Source: ui/beeper_ui/services/collaboration_service.py] — CollaborationMessage dataclass, store_message, get_message_history
- [Source: ui/beeper_ui/services/investigation_service.py] — InvestigationService singleton, confirm_resolution() HTTP call pattern
- [Source: ui/beeper_ui/static/js/investigation-collab.js] — appendMessage() discriminator, socket.emit pattern
- [Source: ui/beeper_ui/templates/investigations/_collaboration_panel.html] — Existing collaboration panel structure
- [Source: _bmad-output/implementation-artifacts/5-1-websocket-collaboration-channel.md] — Previous story: handler patterns, test fixtures
- [Source: _bmad-output/implementation-artifacts/5-2-evidence-presentation-references.md] — Previous story: SSE test regressions, template patterns

## Dev Agent Record

### Agent Model Used

claude-opus-4-6

### Debug Log References

- `InvestigationService` methods return `False` on all errors (timeout, HTTP status, connection) instead of raising `InvestigationServiceError` — this is intentional since the WebSocket handlers should continue broadcasting to the room even if the operator is unreachable
- Used `_get_investigation_service()` helper in websocket module to create `InvestigationService` via `current_app.config` — SocketIO handlers have Flask app context from the HTTP handshake
- Added `get_collaboration_service` import to `investigations.py` routes to fetch human interventions for the review view
- Collaboration panel base CSS classes (`.collaboration-panel`, `.collab-header`, etc.) were referenced in HTML but never defined in CSS — added comprehensive base styles

### Completion Notes List

- Added `handle_annotate` and `handle_redirect` WebSocket event handlers with full validation, operator forwarding, Qdrant persistence, and room broadcasting
- Added `annotate_investigation()` and `redirect_investigation()` methods to InvestigationService with graceful error handling (return False, don't crash)
- Updated collaboration panel template with inline Annotate/Redirect input areas, action bar, and disabled redirect button for non-investigating status
- Extended JavaScript client with `submitAnnotation()`, `submitRedirect()`, `toggleAnnotationInput()`, `toggleRedirectInput()`, keyboard shortcuts (n/r), and extended `appendMessage()` discriminator for annotation/redirect message types
- Added ~200 lines of CSS for collaboration panel base styles, annotation/redirect styling, action inputs, and human interventions review view
- Added "Human Interventions" section to `_detail_content.html` showing annotations and redirects when reviewing investigations (AC #3)
- Added `human_interventions` context variable to investigation detail route, filtering annotation/redirect messages from collaboration history
- 25 new tests: 12 WebSocket handler tests (TestAnnotateInvestigation + TestRedirectInvestigation), 8 InvestigationService tests, 5 template integration tests
- All 1517 UI tests pass, 888 investigator tests pass, 531 operator tests pass — zero regressions

### File List

- `ui/beeper_ui/websocket/investigation.py` (MODIFIED) — Added `handle_annotate`, `handle_redirect` handlers, `_get_investigation_service` helper, imported InvestigationService and current_app
- `ui/beeper_ui/services/investigation_service.py` (MODIFIED) — Added `annotate_investigation()` and `redirect_investigation()` methods
- `ui/beeper_ui/routes/investigations.py` (MODIFIED) — Added `get_collaboration_service` import, `human_interventions` retrieval in detail route, passed to template context
- `ui/beeper_ui/templates/investigations/_collaboration_panel.html` (MODIFIED) — Added annotation/redirect inline inputs, action bar, status data attribute
- `ui/beeper_ui/static/js/investigation-collab.js` (MODIFIED) — Added annotation/redirect emit/receive handlers, keyboard shortcuts, extended appendMessage()
- `ui/beeper_ui/static/css/main.css` (MODIFIED) — Added collaboration panel base styles, annotation/redirect styles, human interventions review styles
- `ui/beeper_ui/templates/investigations/_detail_content.html` (MODIFIED) — Added "Human Interventions" review section
- `ui/tests/test_websocket.py` (MODIFIED) — Added TestAnnotateInvestigation (6 tests), TestRedirectInvestigation (6 tests), 5 template tests
- `ui/tests/test_investigation_service.py` (MODIFIED) — Added TestAnnotateInvestigation (4 tests), TestRedirectInvestigation (4 tests)
