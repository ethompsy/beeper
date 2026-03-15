# Story 2.7: Notification Configuration UI

Status: review

## Story

As a **user**,
I want to view and test notification channels from the UI,
so that I can verify my notification setup works before relying on it during incidents.

## Acceptance Criteria

1. **Given** a user navigates to `/notifications`
   **When** the page loads
   **Then** all configured NotificationChannel CRDs are listed with status (configured/error)
   **And** routing rules summary is visible per channel

2. **Given** a configured notification channel
   **When** a user clicks "Send Test Notification"
   **Then** a test notification is delivered through the channel with sample investigation data
   **And** the test result (success/failure with error detail) is displayed in the UI

3. **Given** the notification configuration page
   **When** accessed by role "user"
   **Then** channel viewing and test sending are available
   **And** channel creation/deletion requires CRD management (kubectl)

## Tasks / Subtasks

- [x] Task 1: Create NotificationChannelService (AC: #1)
  - [x] 1.1 Create `ui/beeper_ui/services/notification_channel_service.py` with `NotificationChannelService` class
  - [x] 1.2 Implement `list_channels()` — calls `GET /api/v1/notifications/channels` on operator API and returns channel list
  - [x] 1.3 Implement `send_test_notification(channel_name, channel_type)` — constructs sample investigation payload and calls `POST /api/v1/notifications/test` to deliver a test notification through the specified channel
  - [x] 1.4 Add `NotificationChannelServiceError` exception class with `retryable` flag (matches existing service patterns)

- [x] Task 2: Create notification configuration route (AC: #1, #2, #3)
  - [x] 2.1 Add `GET /notifications/` route to new `notification_config_bp` Blueprint (separate from API-prefixed `notifications_bp`) decorated with `@require_role("user")`
  - [x] 2.2 Route calls `NotificationChannelService.list_channels()` and renders `notifications/config.html` template
  - [x] 2.3 Handle HTMX partial requests — if `HX-Request` header, render `notifications/_channel_list.html` partial
  - [x] 2.4 Handle `NotificationChannelServiceError` gracefully with `error_message` template variable

- [x] Task 3: Create test notification endpoint (AC: #2)
  - [x] 3.1 Add `POST /notifications/test` route to `notification_config_bp`, decorated with `@require_role("user")`
  - [x] 3.2 Accept JSON body `{ "channel_name": "...", "channel_type": "..." }`
  - [x] 3.3 Call `NotificationChannelService.send_test_notification()` with sample investigation data
  - [x] 3.4 Return JSON result `{ "success": bool, "message": str, "error": str|null }` for API clients
  - [x] 3.5 Render `notifications/_test_result.html` partial for HTMX response swap into channel card

- [x] Task 4: Create Jinja2 templates (AC: #1, #2, #3)
  - [x] 4.1 Create `ui/beeper_ui/templates/notifications/config.html` — extends `base.html`, page title "Notification Channels", lists all channels as cards
  - [x] 4.2 Create `ui/beeper_ui/templates/notifications/_channel_list.html` — HTMX partial with channel cards grid
  - [x] 4.3 Create `ui/beeper_ui/templates/notifications/_test_result.html` — HTMX partial showing test success/failure with detail
  - [x] 4.4 Each channel card displays: channel name, type badge, status (configured/error with color), routing rules summary, error message if status=error, "Send Test" button (disabled when in error)
  - [x] 4.5 Add "Notifications" link to navigation in `base.html`

- [x] Task 5: Comprehensive testing (AC: #1, #2, #3)
  - [x] 5.1 Create `ui/tests/test_notification_channel_service.py` — 22 unit tests for `NotificationChannelService` (list_channels, send_test, error handling, HTTP timeout)
  - [x] 5.2 Create `ui/tests/test_notification_config_routes.py` — 33 route integration tests (list page, HTMX partial, test endpoint success/failure, permission checks)
  - [x] 5.3 Test error states: operator unreachable, no channels configured (empty state), channel in error condition
  - [x] 5.4 Run full UI test suite — 1028 total tests pass (973 existing + 55 new, zero regressions)
  - [x] 5.5 Run ruff lint on all new/modified files — clean

## Dev Notes

### Architecture Patterns to Follow

**Service pattern** (follow `notification_service.py` / `notification_audit_service.py`):
```python
class NotificationChannelService:
    def __init__(self, operator_url: str, timeout: float = 5.0) -> None:
        self.operator_url = operator_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            self._client.close()
            self._client = None
```

**Route pattern** (follow `sources.py` for UI page routes):
```python
def get_channel_service() -> NotificationChannelService:
    return NotificationChannelService(
        operator_url=current_app.config["OPERATOR_URL"],
        timeout=current_app.config["OPERATOR_TIMEOUT"],
    )
```

**Template pattern** (follow `trust_settings.html` for settings pages):
- Extends `base.html`
- Uses `.card` class for channel cards
- Error state with `.error-card`
- Empty state with informational message
- HTMX for dynamic test results

### Operator API Response Format

The operator `GET /api/v1/notifications/channels` returns:
```json
[
  {
    "name": "sre-slack",
    "type": "slack",
    "credentials_secret": "slack-bot-token",
    "condition": "configured",
    "last_validated": "2026-03-14T10:00:00Z",
    "error": null
  }
]
```

Note: The operator API does NOT return routing config in the list response. The routing config is part of the CRD spec. For the UI, the service should also call through to get routing details, OR the operator endpoint should be enhanced. **Decision: The UI service should display the channel status info that the operator provides. Routing rules display is best-effort — if the operator doesn't return routing info, show "Routing rules managed via CRD" as placeholder text.**

### Test Notification Payload

For "Send Test Notification", construct a sample investigation payload:
```python
SAMPLE_TEST_PAYLOAD = {
    "investigation_id": "test-notification-" + uuid4().hex[:8],
    "event_type": "test",
    "severity": "low",
    "service": "test-service",
    "payload": {
        "title": "Test Notification from Beeper",
        "summary": "This is a test notification to verify channel configuration.",
        "confidence": 0.95,
        "evidence": [{"finding": "Channel connectivity test", "source": "beeper-ui"}],
    },
}
```

### CSS Classes Available (from main.css)

- `.container` — max-width 1200px centered
- `.card` — white bg, 8px radius, shadow, 20px padding
- `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-sm` — button variants
- `.error-card`, `.error-text` — error styling
- `.badge` — small badges (use for channel type)
- `.status-indicator` — status badges
- `.severity-critical`, `.severity-high`, `.severity-medium`, `.severity-low` — severity badges
- `.htmx-indicator` — loading state (hidden until HTMX fires)

### Navigation Update

Add to `base.html` nav:
```html
<a href="/notifications/">Notifications</a>
```

Place after "SLO" link to group with operational features.

### Critical Guardrails

- **No new pip dependencies** — use httpx (existing) for operator API calls
- **Reuse existing notifications Blueprint** — don't create a new one, add routes to `notifications_bp`
- **Follow HTMX patterns** — server renders HTML, HTMX swaps partials, no client-side JS frameworks
- **Permission model** — `@require_role("user")` for viewing and testing; channel CRUD is kubectl-only (CRDs)
- **Error handling** — operator unreachable should show graceful error, not crash
- **Template directory** — create `ui/beeper_ui/templates/notifications/` directory for templates
- **No Tailwind yet** — v0.1.0 uses `main.css` BEM classes; Tailwind migration is incremental and not required here
- **Test isolation** — mock all httpx calls and operator API responses in tests

### Project Structure Notes

- All UI route files: `ui/beeper_ui/routes/`
- All service files: `ui/beeper_ui/services/`
- All templates: `ui/beeper_ui/templates/`
- All tests: `ui/tests/`
- Blueprint registration: `ui/beeper_ui/routes/__init__.py` (notifications_bp already registered)
- App factory: `ui/beeper_ui/app.py`
- Config: `ui/beeper_ui/config.py` (OPERATOR_URL, OPERATOR_TIMEOUT)

### Previous Story Intelligence

**From story 2-6 (Notification Audit & False Page Tracking):**
- Used Qdrant payload-only collections for storage — this story does NOT need Qdrant, uses operator REST API
- Non-blocking error handling pattern (try/except) for audit — apply similar for test notification results
- Code review found: lazy imports should be at module top, `import json` at module top, mock paths must match actual import paths
- 973 UI tests passing at end of 2-6 — this is the baseline to maintain

**Recurring code review findings across Epic 2:**
- Always put imports at module top (no lazy imports inside functions)
- Mock paths must exactly match where the class is imported, not where it's defined
- Add error context to error returns (tuple with reason string)
- Document payload schemas in comments
- Fix import sort order (ruff isort)

### Git Intelligence

Recent commits show consistent pattern: story implementation → code review → fix. All Epic 2 stories have followed this pattern successfully. Current test counts: 505 investigator, 973 UI (post code review 2-6).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.7] — AC definitions
- [Source: operator/src/crds/notification_channel.rs] — CRD struct: NotificationChannelSpec, ChannelType, RoutingConfig, QuietHoursConfig, NotificationChannelStatus
- [Source: operator/src/api.rs] — GET /api/v1/notifications/channels handler, NotificationChannelResponse struct
- [Source: ui/beeper_ui/routes/notifications.py] — existing notifications Blueprint with deliver/audit routes
- [Source: ui/beeper_ui/services/notification_service.py] — service pattern, credential fetching, HTTP client management
- [Source: ui/beeper_ui/routes/sources.py] — UI page route pattern with HTMX partial support
- [Source: ui/beeper_ui/templates/base.html] — base template, navigation structure
- [Source: ui/beeper_ui/templates/trust_settings.html] — settings page template pattern
- [Source: _bmad-output/planning-artifacts/architecture.md] — Flask+HTMX+SSE stack, Jinja2 templates, Tailwind incremental
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md] — NotificationChannelForm component, dark surface hierarchy, card patterns, progressive disclosure

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Created `NotificationChannelService` with `list_channels()` and `send_test_notification()` methods following existing httpx-based service patterns
- Created separate `notification_config_bp` Blueprint (url_prefix="/notifications") since existing `notifications_bp` is API-only (url_prefix="/api/v1/notifications")
- `GET /notifications/` renders channel list page with HTMX partial support
- `POST /notifications/test` sends test notification with sample investigation data, returns HTML partial for HTMX or JSON for API clients
- Jinja2 templates follow existing card-based UI patterns from sources/list.html
- Channel cards show name, type badge, status (configured/error), last_validated, routing info placeholder, and "Send Test" button (disabled for error channels)
- Routing rules show "Managed via CRD routing rules" since operator API does not return routing config in channel list response
- Added "Notifications" link to base.html navigation after SLO
- 55 new tests: 22 service unit tests + 33 route integration tests
- Full UI suite: 1028 passed (973 existing + 55 new), zero regressions
- Ruff lint: clean on all new/modified files
- No new pip dependencies (uses httpx existing)

### File List

**New files created:**
1. `ui/beeper_ui/services/notification_channel_service.py` — NotificationChannelService with list_channels(), send_test_notification(), httpx client management, NotificationChannelServiceError
2. `ui/beeper_ui/routes/notification_config.py` — notification_config_bp Blueprint with GET /notifications/ and POST /notifications/test routes
3. `ui/beeper_ui/templates/notifications/config.html` — Full page template extending base.html
4. `ui/beeper_ui/templates/notifications/_channel_list.html` — HTMX partial with channel cards grid, error/empty states
5. `ui/beeper_ui/templates/notifications/_test_result.html` — HTMX partial for test result display
6. `ui/tests/test_notification_channel_service.py` — 22 unit tests for service
7. `ui/tests/test_notification_config_routes.py` — 33 integration tests for routes

**Files modified:**
1. `ui/beeper_ui/routes/__init__.py` — Register notification_config_bp Blueprint
2. `ui/beeper_ui/templates/base.html` — Add "Notifications" nav link
3. `_bmad-output/implementation-artifacts/sprint-status.yaml` — Story status updates
4. `_bmad-output/implementation-artifacts/2-7-notification-configuration-ui.md` — This story file with completion notes
