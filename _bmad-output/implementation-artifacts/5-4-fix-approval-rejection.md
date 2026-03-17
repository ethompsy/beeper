# Story 5.4: Fix Approval & Rejection

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **user**,
I want to approve or reject Beeper-proposed fixes within my permission level,
so that I maintain control over what changes are applied to my services.

## Acceptance Criteria

1. **Given** Beeper proposes a fix for a service at TL3 (act with approval) **When** the fix is presented in the investigation view **Then** "Approve" and "Reject" buttons are displayed with the fix details, evidence, and test plan **And** the approve action uses optimistic UI (immediate visual feedback, server confirmation follows)

2. **Given** a user with role "user" approves a fix **When** the approval is submitted **Then** the fix proceeds to execution (auto-PR, sandbox test, or direct apply per trust level) **And** the approval is logged with user, timestamp, and the fix version approved

3. **Given** a user rejects a fix **When** the rejection is submitted **Then** the investigation records the rejection with optional rejection reason **And** Beeper can propose an alternative approach if the user provides guidance

## Tasks / Subtasks

- [x] Task 1: Add `approve_fix` and `reject_fix` WebSocket event handlers (AC: #1, #2, #3)
  - [x]1.1 In `ui/beeper_ui/websocket/investigation.py`, add `@socketio.on("approve_fix")` handler — validates `investigation_id` field, calls `InvestigationService.approve_fix()`, stores `CollaborationMessage(message_type="fix_approved")` via `CollaborationService`, broadcasts `fix_approved` event to room
  - [x]1.2 Add `@socketio.on("reject_fix")` handler — validates `investigation_id` and optional `reason` field, calls `InvestigationService.reject_fix()`, stores `CollaborationMessage(message_type="fix_rejected")`, broadcasts `fix_rejected` event to room
  - [x]1.3 For both handlers: emit `"error"` event on missing `investigation_id` (follow `handle_annotate` validation pattern), use `_get_user()`, `_room_name()`, `_now_iso()` helpers. Operator calls are non-blocking (try/except, log warning with exc_info=True on failure)
  - [x]1.4 Write tests in `ui/tests/test_websocket.py` — add `TestApproveFix` and `TestRejectFix` classes following existing `TestAnnotateInvestigation` pattern: test missing investigation_id → error, valid approve → stored + broadcast, valid reject with reason → stored + broadcast, valid reject without reason → stored + broadcast, operator failure → still works

- [x] Task 2: Add `approve_fix` and `reject_fix` methods to InvestigationService (AC: #2, #3)
  - [x]2.1 In `ui/beeper_ui/services/investigation_service.py`, add `approve_fix(self, investigation_id: str, user: str) -> bool` — POST to `{operator_url}/api/v1/investigations/{investigation_id}/approve` with JSON `{"user": user}`. Return `False` on 404. Return `False` gracefully on other errors (timeout, HTTP status, connection). Follow `annotate_investigation()` error handling pattern (return False, don't raise).
  - [x]2.2 Add `reject_fix(self, investigation_id: str, user: str, reason: str | None = None) -> bool` — POST to `{operator_url}/api/v1/investigations/{investigation_id}/reject` with JSON `{"user": user, "reason": reason}`. Return `False` on 404. Return `False` gracefully on other errors.
  - [x]2.3 Write unit tests in `ui/tests/test_investigation_service.py` for both methods — mock HTTP calls, test success (200), not-found (404), server error (500), timeout, connection error. Follow existing `TestAnnotateInvestigation`/`TestRedirectInvestigation` pattern.

- [x] Task 3: Add `fix_proposed` and `fix_applied` incoming WebSocket event listeners to JS client (AC: #1)
  - [x]3.1 In `ui/beeper_ui/static/js/investigation-collab.js`, add `socket.on("fix_proposed", ...)` handler — shows the proposed fix in the collaboration panel with details, evidence summary, and confidence score. Calls `appendMessage()` with `message_type="fix_proposed"`. Shows/enables approve and reject buttons in the action bar.
  - [x]3.2 Add `socket.on("fix_applied", ...)` handler — shows fix execution result in collaboration panel. Calls `appendMessage()` with `message_type="fix_applied"`. Disables approve/reject buttons (fix already applied).
  - [x]3.3 Add `socket.on("fix_approved", ...)` handler — displays approval confirmation message in collaboration panel with optimistic UI update (button changes to "Executing..." spinner state). Disables approve/reject buttons.
  - [x]3.4 Add `socket.on("fix_rejected", ...)` handler — displays rejection message with reason in collaboration panel. Keeps buttons available for potential re-proposal.

- [x] Task 4: Add approve/reject submit functions and optimistic UI to JS client (AC: #1, #2, #3)
  - [x]4.1 Add `window.submitApprove()` function — emits `approve_fix` event with `investigation_id`. Implements optimistic UI: immediately changes Approve button text to "Executing..." with spinner CSS class, disables both approve/reject buttons. On server confirmation (`fix_approved` event), shows success state. On error, re-enables buttons.
  - [x]4.2 Add `window.submitReject()` and `window.toggleRejectInput()` and `window.cancelReject()` functions — toggles inline reject reason input, emits `reject_fix` event with `investigation_id` and optional `reason`. Follow existing `submitRedirect()` / `toggleRedirectInput()` pattern.
  - [x]4.3 Extend `appendMessage()` discriminator: `message_type === "fix_proposed"` renders with `collab-fix-proposed` CSS class (blue accent border, "Fix Proposed" label, confidence badge). `message_type === "fix_approved"` renders with `collab-fix-approved` CSS class (green accent, "Approved" label). `message_type === "fix_rejected"` renders with `collab-fix-rejected` CSS class (red accent, "Rejected" label). `message_type === "fix_applied"` renders with `collab-fix-applied` CSS class (green accent, "Fix Applied" label).
  - [x]4.4 Add keyboard shortcuts: `a` key (when not focused on an input) calls `submitApprove()` directly (one-keystroke approve per UX spec). `x` key (not in input) toggles reject reason input. Enter submits reject, Escape cancels.

- [x] Task 5: Update collaboration panel template with approve/reject action buttons (AC: #1)
  - [x]5.1 In `ui/beeper_ui/templates/investigations/_collaboration_panel.html`, add an approval action bar below the existing action bar with "Approve" (primary green button) and "Reject" (secondary outlined button) buttons. Approval bar initially hidden, shown when `fix_proposed` event arrives (JS controls visibility).
  - [x]5.2 Add inline reject reason input area (hidden by default) below the approval bar — follows same pattern as existing annotation/redirect input areas: placeholder "Reason for rejection (optional)...", submit/cancel buttons.
  - [x]5.3 Approve button includes confidence context text when available: "Approve: [action] — [confidence]% confidence" (set dynamically by JS from `fix_proposed` event data). Truncated at 300px with ellipsis, full text in `title` attribute (per UX spec).
  - [x]5.4 Both buttons disabled when investigation status is not `awaiting_approval` or no fix has been proposed — uses data attribute on panel.

- [x] Task 6: Add approve/reject CSS styles (AC: #1, #3)
  - [x]6.1 In `ui/beeper_ui/static/css/main.css`, add styles for: `.collab-fix-proposed` (left border `#3b82f6` blue accent), `.collab-fix-approved` (left border `#22c55e` green accent, like annotation), `.collab-fix-rejected` (left border `#ef4444` red accent), `.collab-fix-applied` (left border `#22c55e` green accent with distinct icon)
  - [x]6.2 Add `.collab-approval-bar` styles — flex container with gap, approval context text, button sizing. `.collab-approve-btn` primary green solid fill, `.collab-reject-btn` secondary outlined style. Follow button hierarchy from UX spec.
  - [x]6.3 Add `.collab-approve-executing` spinner state CSS — button shows inline spinner animation, disabled state styling. Status pill 150ms crossfade transition per UX spec.
  - [x]6.4 Add `.collab-confidence-badge` for inline confidence display in fix_proposed messages.
  - [x]6.5 Template tests verifying: approve/reject buttons present in approval bar, reject reason input area present, approval bar has correct initial visibility state, data attributes set correctly

- [x] Task 7: Run full test suite across all components (AC: all)
  - [x]7.1 Run UI tests: `cd ui && poetry run python -m pytest` — all pass (existing + new)
  - [x]7.2 Run investigator tests: `cd investigator && poetry run python -m pytest` — 888 passed, 3 skipped
  - [x]7.3 Run operator tests: `cargo test` — 531 passed
  - [x]7.4 No regressions found

## Dev Notes

### Architecture Patterns (CRITICAL — must follow)

**Two-Channel Pattern (UNCHANGED):**
- SocketIO handles ONLY collaboration: messages, annotations, redirections, approvals, rejections
- SSE (existing) continues handling: step progress, findings updates, evidence streaming
- Do NOT migrate SSE events to SocketIO — they coexist

**WebSocket Event Contract (from architecture.md — new for 5-4):**
```
# Client → Server (new for 5-4)
approve_fix(investigation_id)              # Approve proposed fix
reject_fix(investigation_id, reason)       # Reject with reason

# Server → Client broadcast (new for 5-4)
fix_proposed(fix_details, confidence)      # Fix ready for review (sent by operator via SSE or WS)
fix_approved(message)                      # Approval broadcast to room
fix_rejected(message)                      # Rejection broadcast to room
fix_applied(result, metrics)               # Fix execution result
```

**Handler Pattern (mirror existing `handle_annotate`):**
```python
@socketio.on("approve_fix")
def handle_approve_fix(data: dict) -> None:
    investigation_id = data.get("investigation_id", "")
    if not investigation_id:
        emit("error", {"message": "investigation_id is required"})
        return
    user = _get_user()
    room = _room_name(investigation_id)
    # 1. Forward to operator (non-blocking)
    try:
        inv_svc = _get_investigation_service()
        inv_svc.approve_fix(investigation_id, user)
    except Exception:
        logger.warning(
            "Failed to forward fix approval to operator for %s",
            investigation_id,
            exc_info=True,
        )
    # 2. Store in collaboration history
    message = CollaborationMessage(
        id=str(uuid.uuid4()),
        investigation_id=investigation_id,
        user=user, role=user,
        message_type="fix_approved",
        content=f"{user} approved the proposed fix",
        timestamp=_now_iso(),
    )
    collab = collab_svc.get_collaboration_service()
    collab.store_message(message)
    # 3. Broadcast to room
    emit("fix_approved", message.to_payload(), room=room)
```

**Reject handler** follows same shape but:
- Accepts optional `reason` field from data
- Uses `message_type="fix_rejected"` and includes reason in content
- Emits `"fix_rejected"` instead of `"fix_approved"`

**Operator API Endpoints (from architecture.md):**
```
POST /api/v1/investigations/{id}/approve    → {"user": "..."}
POST /api/v1/investigations/{id}/reject     → {"user": "...", "reason": "..."}
```
The operator may not have these endpoints fully implemented yet — the UI service methods should handle non-existent endpoints gracefully (return False, log warning, don't crash). The approval/rejection is still persisted in collaboration history and broadcast to the room regardless of operator response.

**InvestigationService method pattern (follow `annotate_investigation()`):**
```python
def approve_fix(self, investigation_id: str, user: str) -> bool:
    try:
        response = self.client.post(
            f"{self.operator_url}/api/v1/investigations/{investigation_id}/approve",
            json={"user": user},
        )
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return True
    except httpx.TimeoutException as e:
        logger.warning("Timeout approving fix %s: %s", investigation_id, e)
        return False
    except httpx.HTTPStatusError as e:
        logger.warning("Operator error approving fix %s: %s", investigation_id, e.response.status_code)
        return False
    except httpx.RequestError as e:
        logger.warning("Connection error approving fix %s: %s", investigation_id, e)
        return False
```

**CollaborationMessage type field — new values:**
- `"fix_approved"` — user approved a proposed fix
- `"fix_rejected"` — user rejected a proposed fix with optional reason
- `"fix_proposed"` — system proposed a fix (incoming event for display)
- `"fix_applied"` — fix execution completed (incoming event for display)
- Existing values: `"user_message"`, `"system_response"`, `"user_joined"`, `"user_left"`, `"annotation"`, `"redirect"`
- No schema change needed — `message_type` is a free string field

**UX Rules (from UX spec — NO EXCEPTIONS):**
- One-click approve — `a` key approves directly (no input toggle needed)
- Reject: inline text input appears for optional reason → submit → status changes
- No modal confirmations for any primary action. Ever.
- Optimistic UI for approve action ONLY (button shows spinner → "Executing..." → streams result)
- All other interactions (reject) use standard server round-trip
- Keyboard shortcuts: `a` for approve, `x` for reject (when not in input)
- Approve button carries context: "Approve: [action] — [confidence]% confidence"
- Primary button (Approve) = solid green fill. Secondary button (Reject) = outlined style.
- Confidence score displayed as composition, not single number
- Disconnect during approval: "Verifying approval status..." → query on reconnect → confirm or offer retry

### Anti-Patterns to AVOID

- Do NOT create a new service class — use existing `InvestigationService` for operator calls and `CollaborationService` for persistence
- Do NOT add new Qdrant collections — approvals/rejections stored in existing `collaboration_messages` collection as `CollaborationMessage` with appropriate `message_type`
- Do NOT create modal dialogs for approve or reject confirmation
- Do NOT replace SSE events with SocketIO for existing investigation updates
- Do NOT add new Flask routes for fix approval/rejection — these are pure WebSocket actions (the existing `/confirm` and `/reject` HTMX routes handle investigation resolution, NOT fix approval)
- Do NOT import or use any new dependencies — everything needed is already installed
- Do NOT confuse fix approval (5-4) with investigation resolution confirmation (v0.1.0). They are different concepts: fix approval gates a specific remediation action; resolution confirmation closes the investigation.

### Distinction: Fix Approval vs Resolution Confirmation

- **Fix Approval (Story 5-4):** User approves/rejects a *proposed fix* (e.g., "restart pods") before Beeper applies it. This is trust-gated — only needed at TL3. The WebSocket events are `approve_fix`/`reject_fix`.
- **Resolution Confirmation (v0.1.0):** User confirms/rejects the investigation's *final resolution*. The HTMX routes are `POST /{id}/confirm` and `POST /{id}/reject`. These already exist in `investigations.py` routes.
- Both coexist — a fix can be approved (5-4), applied, and then the overall investigation resolution can be confirmed (v0.1.0).

### Previous Story Intelligence (5-3)

**Key learnings from Story 5-3 (Investigation Annotation & Redirection):**
- WebSocket handler pattern: validate fields → forward to operator (try/except non-blocking) → store in collaboration history → broadcast to room
- InvestigationService methods return `False` on all errors — intentional, so WS handlers continue broadcasting even if operator unreachable
- `_get_investigation_service()` helper creates InvestigationService via `current_app.config` — SocketIO handlers have Flask app context
- Template tests use `client.get()` to render the page, then assert on HTML content
- CSS follows `.collab-*` namespace pattern with left-border accent colors for message types
- Keyboard shortcuts: global listener on `document`, check `e.target.tagName` to avoid firing in inputs
- `appendMessage()` uses if/else-if discriminator on `msg.message_type` — add new branches for fix_proposed/fix_approved/fix_rejected/fix_applied

**Key learnings from Story 5-2:**
- SSE test regressions caused by new events — check `range()` calls in SSE test assertions if adding new SSE events
- Template partials use `_` prefix naming convention

**Key learnings from Story 5-1:**
- Flask-SocketIO handler import must occur BEFORE `init_app()` — handlers already imported in `websocket/__init__.py`
- Module-scoped `ws_app` fixture needed in test_websocket.py
- SocketIO test client validates events synchronously (< 500ms inherent)

### Project Structure Notes

**Files to modify:**
- `ui/beeper_ui/websocket/investigation.py` — Add `approve_fix` and `reject_fix` event handlers
- `ui/beeper_ui/services/investigation_service.py` — Add `approve_fix()` and `reject_fix()` methods
- `ui/beeper_ui/templates/investigations/_collaboration_panel.html` — Add approval bar with Approve/Reject buttons, reject reason input area
- `ui/beeper_ui/static/js/investigation-collab.js` — Add emit/receive handlers for approve/reject/fix_proposed/fix_applied, optimistic UI, keyboard shortcuts, extended `appendMessage()`
- `ui/beeper_ui/static/css/main.css` — Add fix approval/rejection CSS styles, optimistic UI spinner, confidence badge
- `ui/tests/test_websocket.py` — Add `TestApproveFix` and `TestRejectFix` test classes
- `ui/tests/test_investigation_service.py` — Add approve_fix and reject_fix service tests

**Files to NOT touch:**
- `ui/beeper_ui/websocket/__init__.py` — No changes needed (handler import already set up)
- `ui/beeper_ui/services/collaboration_service.py` — No changes needed (existing `store_message` works for new message types)
- `ui/beeper_ui/routes/investigations.py` — No changes needed (existing confirm/reject routes handle resolution, not fix approval)
- `ui/beeper_ui/app.py` — No changes needed
- Any investigator or operator files — this story is UI-only

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.4] — Acceptance criteria and story statement
- [Source: _bmad-output/planning-artifacts/architecture.md#WebSocket Architecture] — WebSocket event contracts: approve_fix, reject_fix, fix_proposed, fix_applied
- [Source: _bmad-output/planning-artifacts/architecture.md#Operator API] — POST /approve and /reject endpoints
- [Source: _bmad-output/planning-artifacts/architecture.md#Trust System] — TL1-TL5 trust levels, confidence gating, approval requirements
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Keyboard Shortcuts] — a=approve, r=reject, no modals
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Action confirmation] — Optimistic UI for approve only, spinner states, disconnect recovery
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Button Hierarchy] — Primary=green solid approve, Secondary=outlined reject
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Investigation Review Flow] — 30-second scan, approve path, reject/redirect path
- [Source: ui/beeper_ui/websocket/investigation.py] — Existing handler pattern (handle_annotate, handle_redirect, _get_user, _room_name, _now_iso, _get_investigation_service)
- [Source: ui/beeper_ui/services/investigation_service.py] — annotate_investigation() and redirect_investigation() as patterns for approve_fix/reject_fix
- [Source: ui/beeper_ui/services/collaboration_service.py] — CollaborationMessage dataclass, store_message, get_message_history
- [Source: ui/beeper_ui/static/js/investigation-collab.js] — appendMessage() discriminator, socket.emit pattern, keyboard shortcuts, toggle/submit/cancel pattern
- [Source: ui/beeper_ui/templates/investigations/_collaboration_panel.html] — Existing action bar pattern with annotation/redirect buttons and input areas
- [Source: _bmad-output/implementation-artifacts/5-3-investigation-annotation-redirection.md] — Previous story: handler patterns, test fixtures, CSS patterns
- [Source: _bmad-output/implementation-artifacts/5-2-evidence-presentation-references.md] — Previous story: SSE test patterns, template partial conventions

## Dev Agent Record

### Agent Model Used

claude-opus-4-6

### Debug Log References

- InvestigationService `approve_fix()` and `reject_fix()` return `False` on all errors (timeout, HTTP status, connection) — intentional since WebSocket handlers should continue broadcasting to room even if operator unreachable
- Used `/reject-fix` endpoint (not `/reject`) for fix rejection to avoid conflicting with existing resolution rejection endpoint at `/reject`
- Approval bar hidden by default (`style="display:none;"`), shown dynamically by JS when `fix_proposed` event arrives
- Refactored `appendMessage()` to use shared `appendLabeledMessage()` helper function to reduce code duplication across annotation, redirect, and new fix approval/rejection message types
- Keyboard shortcut `x` used for reject (not `r` which is already taken by redirect)

### Completion Notes List

- Added `handle_approve_fix` and `handle_reject_fix` WebSocket event handlers with full validation, operator forwarding (non-blocking), Qdrant persistence, and room broadcasting
- Added `approve_fix()` and `reject_fix()` methods to InvestigationService with graceful error handling (return False, don't crash) following annotate/redirect pattern
- Updated collaboration panel template with approval action bar (Approve green primary + Reject outlined secondary), inline reject reason input area, both hidden by default
- Extended JavaScript client with: `submitApprove()` with optimistic UI (button → "Executing..." → disabled), `submitReject()`/`toggleRejectInput()`/`cancelReject()`, 4 new socket.on listeners (`fix_proposed`, `fix_approved`, `fix_rejected`, `fix_applied`), extended `appendMessage()` with 4 new message type branches, keyboard shortcuts (`a`=approve, `x`=reject)
- Added ~110 lines of CSS for fix approval/rejection styling (`.collab-fix-proposed` blue, `.collab-fix-approved` green, `.collab-fix-rejected` red, `.collab-fix-applied` green), approval bar, approve/reject buttons, executing state
- 27 new tests: 12 WebSocket handler tests (TestApproveFix 5 + TestRejectFix 7), 12 InvestigationService tests (TestApproveFix 6 + TestRejectFix 6), 3 template integration tests (approval bar, reject input, initial hidden state)
- All 1546 UI tests pass, 888 investigator tests pass, 531 operator tests pass — zero regressions

### File List

- `ui/beeper_ui/websocket/investigation.py` (MODIFIED) — Added `handle_approve_fix`, `handle_reject_fix` handlers
- `ui/beeper_ui/services/investigation_service.py` (MODIFIED) — Added `approve_fix()` and `reject_fix()` methods
- `ui/beeper_ui/templates/investigations/_collaboration_panel.html` (MODIFIED) — Added approval bar with Approve/Reject buttons, reject reason input area
- `ui/beeper_ui/static/js/investigation-collab.js` (MODIFIED) — Added approve/reject emit/receive handlers, optimistic UI, keyboard shortcuts, extended appendMessage() with appendLabeledMessage() helper
- `ui/beeper_ui/static/css/main.css` (MODIFIED) — Added fix approval/rejection styles, approval bar styles, executing state CSS
- `ui/tests/test_websocket.py` (MODIFIED) — Added TestApproveFix (5 tests), TestRejectFix (7 tests), 3 template integration tests
- `ui/tests/test_investigation_service.py` (MODIFIED) — Added TestApproveFix (6 tests), TestRejectFix (6 tests)
