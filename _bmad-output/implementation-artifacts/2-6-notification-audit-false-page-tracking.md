# Story 2.6: Notification Audit & False Page Tracking

Status: done

## Story

As an **admin**,
I want every notification justified with evidence and false pages tracked as bugs,
so that I can measure and improve Beeper's notification accuracy over time.

## Acceptance Criteria

1. **AC1: Audit Records on Delivery**
   **Given** a notification is sent through any channel (Slack, PagerDuty, email, webhook)
   **When** the notification is delivered (or fails)
   **Then** an audit record is stored in the `notification_audit` Qdrant collection with:
   - `channel_type` (slack, pagerduty, email, webhook)
   - `channel_name` (from channel_config)
   - `timestamp` (ISO 8601 delivery time)
   - `investigation_id` (from outbox entry)
   - `evidence_summary` (evidence array from payload)
   - `delivery_status` (delivered, failed, skipped, digest_deferred)
   - `event_type`, `severity`, `service` (from outbox entry)

2. **AC2: False Page Tracking**
   **Given** an SRE marks an investigation as "not_an_issue" (with reason: false_positive, expected_behavior, transient, other) or rates accuracy as "incorrect"
   **When** that investigation had generated notifications (audit records exist for that investigation_id)
   **Then** those audit records are flagged as false pages in the audit trail with `is_false_page: true` and the `false_page_reason`
   **And** the false page count is queryable per service and per time period

3. **AC3: Audit View API**
   **Given** a user calls `GET /api/v1/notifications/audit`
   **When** the request includes optional filters (service, channel_type, date_from, date_to, is_false_page)
   **Then** notification audit history is returned with delivery status, false page flags, and evidence summary
   **And** summary statistics are included (total_notifications, false_page_count, false_page_rate)

## Tasks / Subtasks

- [x] Task 1: Create NotificationAuditService (AC: #1, #2, #3)
  - [x] 1.1: Create `ui/beeper_ui/services/notification_audit_service.py` with `NotificationAuditService` class
  - [x] 1.2: Implement `__init__()` with lazy Qdrant client initialization (follow `InvestigationService` pattern using `QDRANT_HOST`/`QDRANT_PORT` env vars)
  - [x] 1.3: Implement `record_audit(entry, channel_config, delivery_result)` — creates audit record in `notification_audit` Qdrant collection with UUID point ID, all fields from entry + delivery result
  - [x] 1.4: Implement `flag_false_pages(investigation_id, reason)` — queries `notification_audit` for all records matching investigation_id, sets `is_false_page=True` and `false_page_reason` on each
  - [x] 1.5: Implement `query_audit(service, channel_type, date_from, date_to, is_false_page, limit, offset)` — scrolls `notification_audit` with filter conditions, returns list of audit records
  - [x] 1.6: Implement `get_audit_statistics(service, date_from, date_to)` — returns dict with total_notifications, false_page_count, false_page_rate
  - [x] 1.7: Add `NotificationAuditServiceError` exception class

- [x] Task 2: Integrate audit recording into delivery pipeline (AC: #1)
  - [x] 2.1: Modify `deliver_notification()` route in `routes/notifications.py` to call `NotificationAuditService.record_audit()` after successful or failed delivery (before returning response)
  - [x] 2.2: Pass entry, channel_config, and delivery result to `record_audit()`
  - [x] 2.3: Audit recording failures must NOT fail the delivery — wrap in try/except and log warning

- [x] Task 3: Integrate false page flagging into investigation resolution (AC: #2)
  - [x] 3.1: Modify `resolve_investigation_route()` in `routes/investigations.py` — after saving resolution feedback, if outcome is "not_an_issue" OR accuracy_rating is "incorrect", call `NotificationAuditService.flag_false_pages(investigation_id, reason)`
  - [x] 3.2: False page flagging failures must NOT fail the resolution — wrap in try/except and log warning

- [x] Task 4: Add audit query API endpoint (AC: #3)
  - [x] 4.1: Add `GET /api/v1/notifications/audit` route to `routes/notifications.py`
  - [x] 4.2: Accept query parameters: `service`, `channel_type`, `date_from`, `date_to`, `is_false_page`, `limit` (default 50, max 200), `offset` (default 0)
  - [x] 4.3: Return JSON with `records` list and `statistics` dict (total_notifications, false_page_count, false_page_rate)

- [x] Task 5: Write comprehensive tests (AC: #1-#3)
  - [x] 5.1: Unit tests for NotificationAuditService: record_audit() stores correct fields, flag_false_pages() updates matching records, query_audit() with various filters, get_audit_statistics() calculations, Qdrant error handling
  - [x] 5.2: Unit tests for audit recording integration: delivery route calls record_audit on success, on failure, audit error doesn't fail delivery
  - [x] 5.3: Unit tests for false page flagging integration: resolution with not_an_issue calls flag_false_pages, resolution with incorrect accuracy calls flag_false_pages, flagging error doesn't fail resolution
  - [x] 5.4: Unit tests for audit query endpoint: GET returns records with filters, pagination, statistics calculation, empty results
  - [x] 5.5: Regression guard — all existing Python tests (505 investigator + 899 UI) pass unchanged

## Dev Notes

### Architecture Compliance

**File Placement (from architecture.md):**
```
ui/beeper_ui/services/notification_audit_service.py   # New: Audit service with Qdrant CRUD
ui/beeper_ui/routes/notifications.py                  # Modified: add audit query endpoint + audit recording
ui/beeper_ui/routes/investigations.py                 # Modified: add false page flagging on resolution
```
[Source: _bmad-output/planning-artifacts/architecture.md — FR15 maps to notification audit tracking]

**FR to Implementation Mapping:**
- FR15 (false page tracking): `notification_audit_service.py` — audit records + false page flagging
- FR14 (quiet hours / notification justification): Audit records include evidence_summary for justification
[Source: _bmad-output/planning-artifacts/architecture.md#FR to Structure Mapping]

### Implementation Approach

**Key Design Decisions:**

1. **Use Qdrant `notification_audit` collection (payload-only, no vectors):**
   Follows the same pattern as `notification_outbox` (Story 2-1). UUID point IDs, payload-only storage. Fields indexed for filtering: `investigation_id`, `service`, `channel_type`, `delivery_status`, `is_false_page`, `timestamp`.

2. **Audit recording in the delivery route (not the service):**
   Record audit in `deliver_notification()` route handler after `process_outbox_entry()` returns, NOT inside the service methods. This keeps the delivery service pure (single responsibility) and ensures audit captures both success and failure outcomes.

3. **False page flagging via investigation resolution hook:**
   When `resolve_investigation_route()` saves feedback with `outcome == "not_an_issue"` or `accuracy_rating == "incorrect"`, also call `flag_false_pages()`. This is a fire-and-forget operation — failure does not affect the resolution flow.

4. **Existing resolution feedback mechanism (from investigations.py):**
   ```python
   VALID_OUTCOMES = {"resolved", "not_an_issue", "escalated", "unresolved"}
   VALID_ACCURACY_RATINGS = {"correct", "partially_correct", "incorrect"}
   VALID_NOT_AN_ISSUE_REASONS = {"false_positive", "expected_behavior", "transient", "other"}
   ```
   False page flagging triggers when: `outcome == "not_an_issue"` OR `accuracy_rating == "incorrect"`.
   The `false_page_reason` is set to: `not_an_issue_reason` (if outcome is not_an_issue) or `"incorrect_accuracy"` (if accuracy_rating is incorrect).

5. **Audit query returns records + statistics:**
   The `GET /api/v1/notifications/audit` endpoint returns both the paginated audit records and summary statistics in a single response. This avoids needing separate endpoints.

6. **No new pip dependencies:**
   Uses qdrant-client (existing dependency from investigation_service), datetime (stdlib), uuid (stdlib). No new packages needed.

7. **Collection creation handled gracefully:**
   `record_audit()` should create the `notification_audit` collection if it doesn't exist (recreate_collection with payload-only config). Cache the existence check to avoid repeated API calls.

### Qdrant Audit Record Schema

```python
# notification_audit collection — payload-only (no vectors)
{
    "audit_id": str,          # UUID (also used as Qdrant point ID string)
    "investigation_id": str,  # From outbox entry
    "event_type": str,        # investigation_started, resolved, etc.
    "severity": str,          # low, medium, high, critical
    "service": str,           # Service name from outbox entry
    "channel_type": str,      # slack, pagerduty, email, webhook
    "channel_name": str,      # From channel_config.get("name", "")
    "timestamp": str,         # ISO 8601 delivery timestamp
    "delivery_status": str,   # delivered, failed, skipped, digest_deferred
    "delivery_error": str,    # Error message if failed, empty otherwise
    "evidence_summary": list, # Evidence array from payload
    "confidence": float,      # Confidence score from payload
    "is_false_page": bool,    # False until flagged via resolution
    "false_page_reason": str, # Reason when flagged (false_positive, expected_behavior, etc.)
    "false_page_flagged_at": str,  # ISO 8601 when flagged (empty until flagged)
}
```

### Technical Requirements

- **Python 3.11+** — UI code (Flask)
- **qdrant-client** — existing dependency, for audit record storage and querying
- **uuid** — stdlib, for generating audit record IDs
- **datetime** — stdlib, for timestamps
- **No new dependencies required**

### Library & Framework Requirements

- Use `qdrant_client.QdrantClient` with lazy initialization following `InvestigationService` pattern
- Use `qdrant_client.models.Filter`, `FieldCondition`, `MatchValue` for query filters
- Use `qdrant_client.models.Range` for date range filtering on timestamp field
- Use `uuid.uuid4()` for point IDs (convert to string for Qdrant)
- Use `datetime.datetime.now(datetime.timezone.utc).isoformat()` for timestamps
- Mock all Qdrant calls with `unittest.mock.patch` in tests
- Follow Flask blueprint pattern from existing `notifications_bp`

### File Structure Requirements

**New files to create:**
```
ui/beeper_ui/services/notification_audit_service.py    # NotificationAuditService class
ui/tests/test_notification_audit_service.py            # Audit service unit tests
ui/tests/test_notification_audit_routes.py             # Audit route endpoint tests
```

**Files to modify:**
```
ui/beeper_ui/routes/notifications.py                   # Add audit recording + GET audit endpoint
ui/beeper_ui/routes/investigations.py                  # Add false page flagging on resolution
```

### Testing Requirements

- **Framework:** pytest for all Python tests
- **NotificationAuditService tests:** record_audit() with all channel types, flag_false_pages() bulk update, query_audit() with filters, get_audit_statistics() calculations, collection auto-creation, Qdrant error handling
- **Route integration tests:** audit recorded on delivery success/failure, audit errors don't fail delivery, false page flagged on not_an_issue resolution, false page flagged on incorrect accuracy, flagging errors don't fail resolution
- **Audit query endpoint tests:** GET with no filters, GET with each filter type, pagination (limit/offset), statistics in response, empty results
- **Mock all Qdrant calls:** Use `unittest.mock.patch` for `QdrantClient` — never call real Qdrant
- **Regression:** All existing Python tests (505 investigator + 899 UI) must pass unchanged
- **No new test dependencies required** — pytest and unittest.mock already available

### Critical Guardrails

1. **DO NOT add any new pip dependencies.** Use qdrant-client (existing), uuid/datetime (stdlib).
2. **DO NOT modify NotificationDeliveryService.** Audit recording happens in the route handler, not the service.
3. **DO NOT modify the Rust operator code.** Audit is purely a Python UI concern.
4. **DO NOT block delivery on audit failure.** Audit recording must be wrapped in try/except — delivery success/failure takes priority.
5. **DO NOT block investigation resolution on false page flagging.** Flag operation must be wrapped in try/except.
6. **DO NOT create a separate Qdrant client class.** Follow InvestigationService's lazy init pattern.
7. **DO NOT call real Qdrant in tests.** All Qdrant interactions must be mocked.
8. **Use uuid4 string for Qdrant point IDs** — consistent with payload-only collection pattern.
9. **Statistics must handle division by zero** — when total_notifications is 0, false_page_rate should be 0.0.
10. **Date range filtering uses string comparison** — ISO 8601 timestamps are lexicographically sortable.

### Previous Story Intelligence

**Story 2-5 (Email & Webhook Channels) — Most recent reference:**
- Pattern: separate service class, integration via route handler, comprehensive tests
- Test count: 79 new tests (35 email + 30 webhook + 14 service) — expect ~50-70 tests for audit
- No new dependencies added — follow same approach
- Code review found 6 issues — focus on edge cases, type safety, error handling

**Story 2-4 (PagerDuty Bidirectional Integration):**
- Delivery result format: `{"status": "delivered|failed|skipped", "error": "...", "retryable": bool}`
- This result dict is what gets passed to `record_audit()` — capture all fields

**Story 2-1 (NotificationChannel CRD & Durable Outbox) — Foundation:**
- Qdrant payload-only collection pattern established
- OutboxEntry payload structure is the source of audit data

**Existing investigation resolution flow (routes/investigations.py:596-712):**
- `resolve_investigation_route()` already handles outcomes + accuracy ratings
- Integration point: after `svc.save_resolution_feedback()` call
- VALID_OUTCOMES includes "not_an_issue" — trigger false page flagging
- VALID_ACCURACY_RATINGS includes "incorrect" — also trigger false page flagging
- `not_an_issue_reason` from VALID_NOT_AN_ISSUE_REASONS provides the false_page_reason

**Existing Qdrant patterns (investigation_service.py):**
- Lazy QdrantClient init with env vars: `QDRANT_HOST`, `QDRANT_PORT`
- `scroll()` for querying with Filter/FieldCondition/MatchValue
- `set_payload()` for updating existing records
- `upsert()` for creating new records (from other services)
- Error handling: catch Exception, log warning, don't re-raise for non-critical operations

### Git Intelligence

- Recent commits: `c9a36bc` (2-5 done), `c3faa5f` (implement 2-5), `fd3487b` (QA checkpoint)
- All notification infrastructure is complete (outbox, router, 4 channels)
- This story adds the audit/observability layer on top of the delivery pipeline
- Python-only changes — no Rust modifications needed
- Tests consistently at 505 investigator + 899 UI — regression baseline

### Project Structure Notes

- `ui/beeper_ui/services/notification_audit_service.py` follows `services/investigation_service.py` Qdrant pattern
- New service — does NOT extend NotificationDeliveryService
- Route modifications are minimal — add audit hooks to existing handlers
- Audit query endpoint added to existing `notifications_bp` blueprint
- All Python tests use pytest with conftest.py fixtures — follow existing patterns

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.6] — Acceptance criteria and user story
- [Source: _bmad-output/planning-artifacts/architecture.md#Notification Engine Architecture] — Durable outbox pipeline, audit tracking
- [Source: _bmad-output/planning-artifacts/architecture.md#FR to Structure Mapping] — FR15 maps to notification audit
- [Source: _bmad-output/planning-artifacts/prd.md#FR15] — False page tracking as bugs
- [Source: ui/beeper_ui/services/investigation_service.py] — Qdrant client pattern, scroll/set_payload
- [Source: ui/beeper_ui/routes/investigations.py#596-712] — Resolution feedback flow, VALID_OUTCOMES, VALID_NOT_AN_ISSUE_REASONS
- [Source: ui/beeper_ui/routes/notifications.py] — Delivery route handler (audit integration point)
- [Source: ui/beeper_ui/services/notification_service.py] — Delivery result format
- [Source: _bmad-output/implementation-artifacts/2-5-email-webhook-channels.md] — Previous story implementation reference

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Created `NotificationAuditService` with Qdrant payload-only collection (`notification_audit`), lazy client init, UUID point IDs
- Audit records include `timestamp_epoch` (float) field alongside ISO `timestamp` for Qdrant `Range` filter compatibility (Range requires numeric values, not strings)
- Audit recording integrated into `deliver_notification()` route — non-blocking (try/except), captures success + failure + unexpected error outcomes
- False page flagging integrated into `resolve_investigation_route()` — triggers on `outcome == "not_an_issue"` OR `accuracy_rating == "incorrect"`, non-blocking
- `GET /api/v1/notifications/audit` endpoint returns paginated records + statistics (total_notifications, false_page_count, false_page_rate)
- 73 new tests (49 service + 24 route/integration), 972 total UI tests passing, 505 investigator tests passing (no regressions)
- No new pip dependencies — uses qdrant-client (existing), uuid/datetime (stdlib)
- Ruff lint: clean on all new/modified files

### File List

**New files:**
- `ui/beeper_ui/services/notification_audit_service.py` — NotificationAuditService class with Qdrant CRUD
- `ui/tests/test_notification_audit_service.py` — 49 unit tests for audit service
- `ui/tests/test_notification_audit_routes.py` — 24 route/integration tests

**Modified files:**
- `ui/beeper_ui/routes/notifications.py` — Added `_record_audit()` helper, audit recording in delivery route, `GET /audit` endpoint
- `ui/beeper_ui/routes/investigations.py` — Added false page flagging after resolution feedback
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — Updated story 2-6 status
- `_bmad-output/implementation-artifacts/2-6-notification-audit-false-page-tracking.md` — Story file updates
