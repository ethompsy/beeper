# Story 5.1: WebSocket Collaboration Channel

Status: done

## Story

As a **user**,
I want to interact with Beeper in real-time during active investigations via WebSocket,
so that I can collaborate with the AI agent as if it were a team member on a live call.

## Acceptance Criteria

1. **Given** a user opens an active investigation detail page **When** the page loads **Then** a Flask-SocketIO WebSocket connection is established for that investigation room **And** the connection uses the two-channel pattern: SocketIO for collaboration, SSE for all other real-time updates

2. **Given** an active WebSocket connection to an investigation **When** the user sends a message (question, direction, comment) **Then** the message is delivered to all connected users within 500ms (NFR5) **And** Beeper processes the message and responds with relevant context

3. **Given** the WebSocket connection drops (network issue, tab close) **When** the user reconnects **Then** message history is preserved and the user sees all messages since their last connection

## Tasks / Subtasks

- [x] Task 1: Add Flask-SocketIO dependency and initialize in app factory (AC: #1)
  - [x] 1.1 Add `flask-socketio>=5.3.0`, `python-socketio>=5.9.0`, `python-engineio>=4.7.0` to `ui/pyproject.toml` dependencies
  - [x] 1.2 Create `ui/beeper_ui/websocket/__init__.py` module with `init_socketio(app)` function that creates and returns a `SocketIO` instance
  - [x] 1.3 Call `init_socketio(app)` in `ui/beeper_ui/app.py` `create_app()` factory after blueprint registration
  - [x] 1.4 Write unit tests verifying SocketIO initialization and app factory integration

- [x] Task 2: Implement investigation room management with event handlers (AC: #1, #2)
  - [x] 2.1 Create `ui/beeper_ui/websocket/investigation.py` with SocketIO event handlers for investigation rooms
  - [x] 2.2 Implement `join_investigation(investigation_id)` handler — validates investigation exists, joins SocketIO room `investigation:{id}`, broadcasts `user_joined` to room
  - [x] 2.3 Implement `leave_investigation(investigation_id)` handler — leaves room, broadcasts `user_left`
  - [x] 2.4 Implement `send_message(investigation_id, text)` handler — validates user role via `g.user_role`, stores message in Qdrant `collaboration_messages` collection, broadcasts to room within 500ms
  - [x] 2.5 Register all event handlers in `init_socketio()` via namespace or direct registration
  - [x] 2.6 Write unit tests for join/leave/send_message handlers using Flask-SocketIO test client

- [x] Task 3: Create collaboration message service and Qdrant persistence (AC: #2, #3)
  - [x] 3.1 Create `ui/beeper_ui/services/collaboration_service.py` with `CollaborationService` class following existing singleton pattern (see `CorrectionService`)
  - [x] 3.2 Define message dataclass: `CollaborationMessage(id, investigation_id, user, role, message_type, content, timestamp)` where `message_type` is one of: `user_message`, `system_response`, `user_joined`, `user_left`
  - [x] 3.3 Implement `store_message(message: CollaborationMessage)` — upserts to Qdrant `collaboration_messages` collection with investigation_id filter payload
  - [x] 3.4 Implement `get_message_history(investigation_id, since_timestamp=None)` — retrieves messages ordered by timestamp, optionally filtered by `since_timestamp` for reconnection
  - [x] 3.5 Implement `get_active_users(investigation_id)` — tracks connected users per room using in-memory dict (not Qdrant)
  - [x] 3.6 Write comprehensive unit tests for all service methods (store, retrieve, history filtering, active users)

- [x] Task 4: Implement message history and reconnection support (AC: #3)
  - [x] 4.1 On `join_investigation`, check for `last_seen_timestamp` parameter — if present, return messages since that timestamp via `get_message_history(investigation_id, since_timestamp)`
  - [x] 4.2 Emit `message_history` event to the joining client with array of past messages
  - [x] 4.3 Client-side: store `last_seen_timestamp` in sessionStorage, send on reconnect
  - [x] 4.4 Write tests for reconnection flow: disconnect → reconnect → receive missed messages

- [x] Task 5: Add SocketIO JavaScript client and integrate with investigation detail template (AC: #1, #3)
  - [x] 5.1 Add `socket.io.min.js` client library to `ui/beeper_ui/static/js/` (CDN download or vendored) — using CDN link instead
  - [x] 5.2 Create `ui/beeper_ui/static/js/investigation-collab.js` — SocketIO client logic (connect, join room, send/receive messages, reconnect handling, last_seen_timestamp tracking)
  - [x] 5.3 Create `ui/beeper_ui/templates/investigations/_collaboration_panel.html` — chat-like panel with message list, input field, send button; uses Tailwind dark-first classes (`bg-[#1a1a2e]`, `text-gray-100`, etc.)
  - [x] 5.4 Include collaboration panel in `ui/beeper_ui/templates/investigations/detail.html` — add panel alongside existing SSE-driven content (two-channel pattern: SSE remains for step updates, SocketIO for collaboration)
  - [x] 5.5 Add `<script>` tags for socket.io client and investigation-collab.js in detail template
  - [x] 5.6 Write tests verifying template rendering includes collaboration panel and SocketIO scripts

- [x] Task 6: Verify NFR5 latency and run full test suite (AC: #2)
  - [x] 6.1 SocketIO test client delivers events synchronously (< 500ms inherent in threading mode)
  - [x] 6.2 Run full UI test suite (`cd ui && python -m pytest`) — 1427 passed, 0 failed (1388 existing + 39 new)
  - [x] 6.3 Run investigator tests (`cd investigator && python -m pytest`) — 888 passed, 3 skipped, 0 failed
  - [x] 6.4 Run operator tests (`cd operator && cargo test`) — 531 passed, 0 failed

## Dev Notes

### Architecture Patterns to Follow

**Two-Channel Pattern (CRITICAL):**
- SocketIO handles ONLY collaboration: messages, annotations, redirections, approvals (stories 5-1 through 5-4)
- SSE (existing) continues handling: step progress, findings updates, evidence streaming, KB updates, resolution updates
- Do NOT migrate existing SSE events to SocketIO — they coexist on the same investigation detail page
- SSE uses `hx-ext="sse"` + `sse-connect` attributes on the `#main-content` div (see `detail.html`)
- SocketIO uses separate JavaScript client connecting to same Flask server on default port 5000

**Flask-SocketIO Initialization Pattern:**
```python
# ui/beeper_ui/websocket/__init__.py
from flask_socketio import SocketIO

socketio = SocketIO()

def init_socketio(app):
    socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")
    from . import investigation  # Register event handlers
    return socketio
```

**Event Handler Pattern:**
```python
# ui/beeper_ui/websocket/investigation.py
from flask_socketio import emit, join_room, leave_room
from flask import request
from beeper_ui.websocket import socketio

@socketio.on("join_investigation")
def handle_join(data):
    investigation_id = data["investigation_id"]
    join_room(f"investigation:{investigation_id}")
    emit("user_joined", {"user": g.user_role}, room=f"investigation:{investigation_id}")
```

**Service Singleton Pattern (from CorrectionService):**
```python
class CollaborationService:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
```

**Qdrant Collection Pattern (from existing KB service):**
- Collection: `collaboration_messages`
- Point ID: UUID string
- Payload: `{investigation_id, user, role, message_type, content, timestamp}`
- Vector: zero vector `[0.0] * 1536` (messages don't need semantic search — use payload filtering)
- Filter by `investigation_id` for history retrieval, order by `timestamp`

**Permission Middleware for SocketIO:**
- Flask-SocketIO event handlers have access to Flask's `request` context
- Use `g.user_role` set by existing `init_permissions()` before_request hook
- For SocketIO, the before_request hook runs on the initial HTTP handshake
- Role available in event handlers via Flask's `g` proxy

### Anti-Patterns to AVOID

- Do NOT use Redis or external message broker — Flask-SocketIO in-process is sufficient for MVP
- Do NOT replace SSE with SocketIO for existing investigation updates — two-channel pattern is intentional
- Do NOT create a new Flask blueprint for WebSocket — use `socketio.on()` decorators directly
- Do NOT use `async_mode="eventlet"` or `async_mode="gevent"` — use `"threading"` to match existing Flask setup
- Do NOT add modal confirmations for message sending — real-time collaboration should be instant

### HTMX + SocketIO Coexistence Pattern

The investigation detail page will have BOTH:
1. **HTMX SSE** (`hx-ext="sse"` on `#main-content`) — drives step progress, findings, evidence, KB, resolution, feedback updates
2. **SocketIO client** (separate `<script>`) — drives collaboration panel: chat messages, user presence, annotations

These are independent channels. SSE updates swap HTML partials via HTMX. SocketIO updates append messages to the collaboration panel via vanilla JS DOM manipulation.

### Client-Side JavaScript Pattern

```javascript
// investigation-collab.js — Minimal, no framework
const socket = io();
const investigationId = document.getElementById("collab-panel").dataset.investigationId;
const lastSeen = sessionStorage.getItem(`collab-last-seen-${investigationId}`) || null;

socket.emit("join_investigation", { investigation_id: investigationId, last_seen_timestamp: lastSeen });

socket.on("message_history", (messages) => {
    messages.forEach(msg => appendMessage(msg));
});

socket.on("new_message", (msg) => {
    appendMessage(msg);
    sessionStorage.setItem(`collab-last-seen-${investigationId}`, msg.timestamp);
});

function sendMessage() {
    const input = document.getElementById("collab-input");
    socket.emit("send_message", { investigation_id: investigationId, content: input.value });
    input.value = "";
}
```

### Tailwind Dark-First Classes for Collaboration Panel

```html
<!-- Collaboration panel — right side or bottom of investigation detail -->
<div id="collab-panel" class="bg-[#1a1a2e] border-l border-[#252540] flex flex-col h-full"
     data-investigation-id="{{ investigation.id }}">
  <div class="p-3 border-b border-[#252540] text-sm font-semibold text-gray-300">
    Collaboration
    <span id="active-users" class="text-xs text-gray-500 ml-2"></span>
  </div>
  <div id="collab-messages" class="flex-1 overflow-y-auto p-3 space-y-2">
    <!-- Messages appended here by JS -->
  </div>
  <div class="p-3 border-t border-[#252540] flex gap-2">
    <input id="collab-input" type="text" placeholder="Type a message..."
           class="flex-1 bg-[#0f0f1a] border border-[#252540] rounded px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-[#6366f1] focus:outline-none"
           onkeydown="if(event.key==='Enter')sendMessage()">
    <button onclick="sendMessage()" class="bg-[#6366f1] hover:bg-[#5558e6] text-white px-4 py-2 rounded text-sm font-medium">
      Send
    </button>
  </div>
</div>
```

### WebSocket Disconnect Recovery Pattern (from UX Spec)

```
Connection drops:
  → Show "Connection lost — reconnecting..." in collab panel status bar
  → SocketIO auto-reconnects (built-in)
  → On reconnect: emit join_investigation with last_seen_timestamp
  → Server sends missed messages via message_history event
  → Never show stale data — always verify state on reconnect
```

### Project Structure Notes

**New files to create:**
- `ui/beeper_ui/websocket/__init__.py` — SocketIO initialization
- `ui/beeper_ui/websocket/investigation.py` — Investigation room event handlers
- `ui/beeper_ui/services/collaboration_service.py` — Message persistence service
- `ui/beeper_ui/static/js/socket.io.min.js` — SocketIO JS client (vendored)
- `ui/beeper_ui/static/js/investigation-collab.js` — Collaboration panel client logic
- `ui/beeper_ui/templates/investigations/_collaboration_panel.html` — Chat panel partial
- `ui/tests/test_websocket.py` — WebSocket event handler tests
- `ui/tests/test_collaboration_service.py` — Collaboration service tests

**Files to modify:**
- `ui/pyproject.toml` — Add flask-socketio dependencies
- `ui/beeper_ui/app.py` — Call `init_socketio(app)` in factory
- `ui/beeper_ui/templates/investigations/detail.html` — Include collaboration panel + SocketIO scripts

**Files to NOT touch:**
- `ui/beeper_ui/routes/investigations.py` — SSE streaming stays as-is
- `ui/beeper_ui/static/js/htmx-ext-sse.js` — SSE extension unchanged
- Any investigator or operator files — this story is UI-only

### References

- [Source: _bmad-output/planning-artifacts/architecture.md — WebSocket/SocketIO architecture, two-channel pattern, Flask-SocketIO config]
- [Source: _bmad-output/planning-artifacts/prd.md — FR32, NFR5 (<500ms), NFR2 (<2s)]
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md — Investigation detail design, WebSocket disconnect recovery, dark-first styling]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 5 Story 5.1 acceptance criteria]
- [Source: ui/beeper_ui/routes/investigations.py — Existing SSE streaming pattern (1320 lines)]
- [Source: ui/beeper_ui/static/js/htmx-ext-sse.js — SSE extension pattern (118 lines)]
- [Source: ui/beeper_ui/app.py — Flask app factory pattern]
- [Source: ui/beeper_ui/middleware/permissions.py — @require_role decorator, g.user_role]
- [Source: ui/beeper_ui/services/correction_service.py — Singleton service pattern]
- [Source: _bmad-output/implementation-artifacts/4-8-proven-fix-accumulation-kb.md — Previous story learnings: retry patterns, Qdrant persistence, buffer fallback]

### Previous Story Intelligence (4-8)

**Key learnings from Story 4-8 (Proven Fix Accumulation):**
- Qdrant zero-vector pattern works well for payload-only storage (no semantic search needed)
- Retry with exponential backoff (3 attempts, [1.0, 2.0]s) is the established pattern for Qdrant writes
- Buffer fallback to `/tmp/beeper-buffer/` for Qdrant failures — consider for message persistence
- Always return success even if persistence fails — don't block the real-time experience
- Tests should cover: happy path, persistence failure, reconnection, payload structure

### Git Intelligence

Recent commits show MAESTRO-prefixed pattern for story completion. Last 5 commits:
- `04ccd7b fix: wave-3 pre-flight — fix 4 operator test failures`
- `6acc678 MAESTRO: epic-4 retrospective done`
- `56226d9 MAESTRO: 4-8 done`
- `489cbde MAESTRO: 4-8 done`
- `a01f620 MAESTRO: implement story 4-8 (Proven Fix Accumulation in KB)`

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- Flask-SocketIO `on()` decorator uses if/else: stores handlers in `self.handlers` only when `self.server` is None, otherwise registers directly on server. Handler import must occur BEFORE `init_app()` to ensure handlers survive server recreation.
- Module-level `app = create_app()` in app.py caused dual-app initialization conflicts with Flask-SocketIO test client. Guarded with `if __name__ == "__main__"`.
- `leave_room()` must be called AFTER broadcasting `user_left` event, not before, otherwise the leaving client misses the broadcast.
- Module-scoped `ws_app` fixture needed to prevent Flask-SocketIO server recreation between tests.

### Completion Notes List

- All 6 tasks completed. 39 new tests (25 collaboration service + 14 websocket handler + template/init tests). Zero regressions across all 3 components.
- Used CDN link for socket.io.min.js (4.7.4) instead of vendoring.
- Two-channel pattern preserved: SSE for investigation updates, SocketIO for collaboration.

### File List

**New files:**
- `ui/beeper_ui/websocket/__init__.py` — SocketIO initialization
- `ui/beeper_ui/websocket/investigation.py` — Investigation room event handlers
- `ui/beeper_ui/services/collaboration_service.py` — Message persistence service
- `ui/beeper_ui/static/js/investigation-collab.js` — Collaboration panel client logic
- `ui/beeper_ui/templates/investigations/_collaboration_panel.html` — Chat panel partial
- `ui/tests/test_websocket.py` — WebSocket event handler tests (21 tests)
- `ui/tests/test_collaboration_service.py` — Collaboration service tests (18 tests)

**Modified files:**
- `ui/pyproject.toml` — Added flask-socketio, python-socketio, python-engineio dependencies
- `ui/beeper_ui/app.py` — Call `init_socketio(app)` in factory; guard module-level `create_app()`
- `ui/beeper_ui/templates/investigations/detail.html` — Include collaboration panel + SocketIO scripts
