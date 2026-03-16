# Story 3.1: Trust Level Configuration & Persistence

Status: done

## Story

As an **admin**,
I want to configure trust levels (1-5) per service controlling Beeper's autonomy,
so that I can gradually increase Beeper's autonomy as it proves reliable for each service.

## Acceptance Criteria

1. **Given** the existing `service_trust_levels` Qdrant collection
   **When** an admin updates a service's trust level via the API (`PUT /api/v1/trust/services/{name}`)
   **Then** the trust level is stored with the new value (1-5) and an audit timestamp
   **And** the endpoint requires `@require_role("admin")` (NFR12)

2. **Given** trust level definitions: TL1 (advisory only), TL2 (suggest with evidence), TL3 (act with approval), TL4 (act and notify), TL5 (fully autonomous)
   **When** any component queries a service's trust level
   **Then** the behavior boundary is enforced per the trust level definition
   **And** a service without a configured trust level defaults to TL1 (advisory only)

3. **Given** the trust level API
   **When** accessed by a user with role "user"
   **Then** read access is allowed but write access is rejected with HTTP 403
   **And** an RFC 7807 error response is returned

## Tasks / Subtasks

- [x] Task 1: Create TrustLevelService for TL1-5 autonomy management (AC: #1, #2)
  - [x] 1.1 Create `ui/beeper_ui/services/trust_level_service.py` with `TrustLevelService` class
  - [x] 1.2 Define `TrustLevelConfig` dataclass: service_name, trust_level (int 1-5), updated_by, updated_at, reason (optional), previous_level (optional)
  - [x] 1.3 Define `TRUST_LEVEL_DEFINITIONS` dict mapping levels 1-5 to names and behavior descriptions
  - [x] 1.4 Implement `get_service_trust_level(service_name) -> TrustLevelConfig | None` — reads from Qdrant `service_trust_levels` collection, returns None if not found (caller defaults to TL1)
  - [x] 1.5 Implement `get_all_trust_levels() -> list[TrustLevelConfig]` — list all configured service trust levels
  - [x] 1.6 Implement `set_trust_level(service_name, level, updated_by, reason) -> TrustLevelConfig` — upserts to Qdrant with audit timestamp, validates level 1-5
  - [x] 1.7 Implement `get_effective_trust_level(service_name) -> int` — returns configured level or TL1 default
  - [x] 1.8 Add `TrustLevelServiceError` exception class matching existing service patterns

- [x] Task 2: Create trust level API routes (AC: #1, #2, #3)
  - [x] 2.1 Create `ui/beeper_ui/routes/trust_config.py` with `trust_config_bp` Blueprint (url_prefix="/api/v1/trust")
  - [x] 2.2 Add `GET /api/v1/trust/services` route — lists all configured trust levels, decorated with `@require_role("user")`, returns JSON array
  - [x] 2.3 Add `GET /api/v1/trust/services/<name>` route — returns trust config for specific service (or TL1 default), decorated with `@require_role("user")`
  - [x] 2.4 Add `PUT /api/v1/trust/services/<name>` route — updates trust level, decorated with `@require_role("admin")`, accepts JSON body `{"level": int, "reason": str|null}`
  - [x] 2.5 Validate trust level value 1-5 in PUT, return RFC 7807 error for invalid values
  - [x] 2.6 Return HTTP 403 with RFC 7807 body when user role attempts PUT
  - [x] 2.7 Add `GET /api/v1/trust/definitions` route — returns trust level definitions (public reference, `@require_role("user")`)
  - [x] 2.8 Register `trust_config_bp` in `ui/beeper_ui/routes/__init__.py`

- [x] Task 3: Create trust configuration UI page (AC: #1, #2, #3)
  - [x] 3.1 Create `ui/beeper_ui/routes/trust_settings.py` with `trust_settings_bp` Blueprint (url_prefix="/settings/trust") — UI page routes separate from API
  - [x] 3.2 Add `GET /settings/trust/` route — renders trust configuration page showing all services with their trust levels, decorated with `@require_role("user")`
  - [x] 3.3 Handle HTMX partial requests — if `HX-Request` header, render `trust/_service_list.html` partial
  - [x] 3.4 Add `POST /settings/trust/<name>/update` route — form submission to update trust level, decorated with `@require_role("admin")`, renders HTMX partial result
  - [x] 3.5 Register `trust_settings_bp` in `ui/beeper_ui/routes/__init__.py`

- [x] Task 4: Create Jinja2 templates for trust settings (AC: #1, #2, #3)
  - [x] 4.1 Create `ui/beeper_ui/templates/trust/settings.html` — extends `base.html`, page title "Trust Level Configuration", lists all services with trust level cards
  - [x] 4.2 Create `ui/beeper_ui/templates/trust/_service_list.html` — HTMX partial with service trust cards grid
  - [x] 4.3 Each service card shows: service name, current trust level (TL1-5) with badge, level name and behavior description, last updated timestamp, "Configure" controls
  - [x] 4.4 Admin controls: dropdown/select for trust level 1-5, optional reason field, submit button
  - [x] 4.5 Add "Trust" link to navigation in `base.html` (after Notifications)
  - [x] 4.6 Create `ui/beeper_ui/templates/trust/_update_result.html` — HTMX partial for trust level update result (replaces card inline)

- [x] Task 5: Comprehensive testing (AC: #1, #2, #3)
  - [x] 5.1 Create `ui/tests/test_trust_level_service.py` — 31 unit tests for TrustLevelService (get/set/list/defaults, validation, error handling, lifecycle, constants)
  - [x] 5.2 Create `ui/tests/test_trust_config_routes.py` — 24 API route tests (GET list, GET single, PUT update, permission checks, validation, RFC 7807 errors, definitions)
  - [x] 5.3 Create `ui/tests/test_trust_settings_routes.py` — 15 UI page route tests (page render, HTMX partial, admin-only update, user read-only, validation)
  - [x] 5.4 Test default behavior: unconfigured service returns TL1
  - [x] 5.5 Test boundary values: level 0, 6, negative, non-integer, float rejected
  - [x] 5.6 Run full UI test suite — 1100 passed (1030 existing + 70 new), zero regressions
  - [x] 5.7 Run ruff lint + mypy on all new/modified files — all clean

## Dev Notes

### Architecture Patterns to Follow

**IMPORTANT: This is SEPARATE from the existing KB trust system.** The existing `service_trust_levels` collection in `kb_service.py` tracks KB authoring trust ("draft"/"trusted"). Story 3-1 implements the per-service **autonomy** trust levels (TL1-5) which control Beeper's operational autonomy. These are distinct concepts:
- **KB Trust** (existing in kb_service.py): Whether Beeper's KB entries are trusted for a service ("draft" vs "trusted")
- **Autonomy Trust** (this story): How much autonomous action Beeper can take for a service (TL1-5)

**Decision: Use the SAME `service_trust_levels` Qdrant collection** but extend the payload to include the autonomy trust level field. The collection already stores per-service trust data — adding autonomy_level avoids creating a redundant collection.

**Trust Level Definitions:**

| Level | Name | Behavior |
|-------|------|----------|
| TL1 | Advisory Only | No autonomous actions; all outputs advisory |
| TL2 | Suggest with Evidence | Suggest actions with supporting evidence; requires manual approval |
| TL3 | Act with Approval | Take actions after explicit SRE approval; gate by confidence threshold |
| TL4 | Act and Notify | Take actions autonomously; notify admin; gate by confidence threshold |
| TL5 | Fully Autonomous | Full autonomy within configured scope |

**Service pattern** (follow `notification_channel_service.py` / `kb_service.py`):
```python
@dataclass
class TrustLevelConfig:
    service_name: str
    trust_level: int  # 1-5
    updated_by: str
    updated_at: str  # ISO 8601 timestamp
    reason: str | None = None
    previous_level: int | None = None
```

**Route pattern** (follow `notification_config.py` for API routes):
```python
trust_config_bp = Blueprint("trust_config", __name__, url_prefix="/api/v1/trust")

@trust_config_bp.route("/services", methods=["GET"])
@require_role("user")
def list_trust_levels():
    service = _get_trust_level_service()
    try:
        levels = service.get_all_trust_levels()
        return jsonify([asdict(l) for l in levels])
    finally:
        service.close()
```

**Qdrant payload structure** (extending existing collection):
```python
{
    "service_name": "payment-api",
    # Existing KB trust fields (leave untouched)
    "trust_level": "trusted",  # KB trust
    "accuracy_pct": 95.0,
    # NEW: Autonomy trust fields
    "autonomy_level": 3,  # TL1-5
    "autonomy_updated_by": "admin@company.com",
    "autonomy_updated_at": "2026-03-15T10:30:00Z",
    "autonomy_reason": "Demonstrated reliability over 30 days",
    "autonomy_previous_level": 2
}
```

**RFC 7807 error format** (existing pattern in codebase):
```python
{
    "type": "about:blank",
    "title": "Forbidden",
    "status": 403,
    "detail": "Admin role required to modify trust levels"
}
```

### Operator API Response Format

The operator API at `GET /api/v1/slo/services` returns ServiceLevel CRDs. The trust level configuration is NOT stored in the operator — it's stored directly in Qdrant via the UI service layer. This is consistent with the existing KB trust pattern where the UI manages Qdrant directly.

### CSS Classes Available (from main.css)

- `.container` — max-width 1200px centered
- `.card` — white bg, 8px radius, shadow, 20px padding
- `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-sm` — button variants
- `.error-card`, `.error-text` — error styling
- `.badge` — small badges (use for trust level indicator)
- `.status-indicator` — status badges
- `.trust-badge.trust-draft`, `.trust-badge.trust-trusted` — existing trust badge classes (extend with `.trust-tl1` through `.trust-tl5`)
- `.htmx-indicator` — loading state (hidden until HTMX fires)

### Critical Guardrails

- **No new pip dependencies** — use qdrant-client (existing) for Qdrant operations
- **Extend existing collection** — do NOT create a new Qdrant collection; use `service_trust_levels` with new `autonomy_*` fields
- **Follow HTMX patterns** — server renders HTML, HTMX swaps partials, no client-side JS
- **Permission model** — `@require_role("user")` for reading, `@require_role("admin")` for writing
- **Error handling** — Qdrant unreachable should show graceful error, not crash
- **Template directory** — create `ui/beeper_ui/templates/trust/` directory for trust-specific templates
- **No Tailwind** — use existing `main.css` BEM classes
- **Test isolation** — mock all Qdrant calls in tests
- **Default to TL1** — any service without explicit configuration returns TL1 (advisory only)
- **Audit trail** — every trust level change must record who, when, previous value, and optional reason
- **Validate level range** — reject values outside 1-5 with clear error messages

### Project Structure Notes

- All UI route files: `ui/beeper_ui/routes/`
- All service files: `ui/beeper_ui/services/`
- All templates: `ui/beeper_ui/templates/`
- All tests: `ui/tests/`
- Blueprint registration: `ui/beeper_ui/routes/__init__.py`
- App factory: `ui/beeper_ui/app.py`
- Config: `ui/beeper_ui/config.py` (QDRANT_URL, QDRANT_COLLECTION configs)
- Auth decorators: `ui/beeper_ui/auth/decorators.py` (@require_role)
- Existing KB trust service: `ui/beeper_ui/services/kb_service.py` (ServiceTrustLevel dataclass, SERVICE_TRUST_COLLECTION)

### Previous Story Intelligence

**From story 2-7 (Notification Configuration UI):**
- Created separate Blueprint for UI routes vs API routes — follow same pattern
- Service class with httpx.Client lifecycle management (create on demand, explicit close())
- HTMX partial rendering via HX-Request header detection
- 55 new tests with zero regressions on 973 baseline

**From Epic 2 code review findings (recurring):**
- Always put imports at module top (no lazy imports inside functions)
- Mock paths must exactly match where the class is imported, not where it's defined
- Add error context to error returns (tuple with reason string)
- Document payload schemas in comments
- Fix import sort order (ruff isort)

**From story 5-4 (Graduated Authoring Trust) — existing KB trust:**
- ServiceTrustLevel dataclass already exists in kb_service.py
- Collection `service_trust_levels` already created and in use
- get_service_trust/upsert_service_trust/get_all_service_trusts methods exist
- Test patterns in `ui/tests/test_trust.py` (57KB comprehensive)
- The existing trust is "draft"/"trusted" for KB entries — NOT the TL1-5 autonomy system
- **DO NOT modify existing KB trust methods** — add new autonomy-specific methods alongside them

### Git Intelligence

Recent commits follow pattern: `MAESTRO: implement story X-Y (Title)` → `MAESTRO: X-Y done`. Current test counts: 517 investigator (3 skipped), 1030 UI. All Wave 1 tests pass (verified in wave-2 pre-flight).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 3, Story 3.1] — User story, acceptance criteria, BDD scenarios
- [Source: _bmad-output/planning-artifacts/architecture.md] — Trust level definitions TL1-5, Qdrant service_trust_levels collection, confidence gating system, API patterns
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md] — Trust badge components, settings page patterns, progressive disclosure
- [Source: ui/beeper_ui/services/kb_service.py] — Existing ServiceTrustLevel dataclass, SERVICE_TRUST_COLLECTION, Qdrant CRUD patterns
- [Source: ui/beeper_ui/auth/decorators.py] — @require_role("admin") and @require_role("user") decorators
- [Source: ui/beeper_ui/routes/notification_config.py] — Route blueprint pattern, HTMX support, service injection
- [Source: ui/beeper_ui/services/notification_channel_service.py] — Service class pattern with httpx client management
- [Source: ui/tests/test_trust.py] — Existing KB trust test patterns
- [Source: operator/src/crds/notification_channel.rs] — CRD definition pattern (Rust)
- [Source: operator/src/api.rs] — Operator API endpoint patterns

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Created `TrustLevelService` with full CRUD for per-service autonomy trust levels (TL1-5), separate from existing KB trust system
- Uses existing `service_trust_levels` Qdrant collection with `autonomy_*` prefixed fields to avoid conflicts with KB trust fields
- `TrustLevelConfig` dataclass with `from_qdrant()` classmethod for deserialization
- API routes at `/api/v1/trust/services` with RESTful GET/PUT endpoints + `/api/v1/trust/definitions` reference
- UI settings page at `/settings/trust/` with HTMX-powered inline updates via `POST /settings/trust/<name>/update`
- Permission enforcement: `@require_role("user")` for reads, `@require_role("admin")` for writes (NFR12)
- RFC 7807 error responses for validation failures and 403 permission denied
- Unconfigured services default to TL1 (Advisory Only) via `get_effective_trust_level()`
- Every trust level change records: who, when, previous value, and optional reason (audit trail)
- 70 new tests: 31 service unit tests + 24 API route tests + 15 UI page tests
- Full UI suite: 1100 passed (1030 existing + 70 new), zero regressions
- Investigator suite: 517 passed, 3 skipped (no change)
- Ruff lint: all clean on new/modified files
- Mypy: no issues found

### File List

**New files created:**
1. `ui/beeper_ui/services/trust_level_service.py` — TrustLevelService, TrustLevelConfig, TRUST_LEVEL_DEFINITIONS, TrustLevelServiceError
2. `ui/beeper_ui/routes/trust_config.py` — trust_config_bp API Blueprint with GET/PUT endpoints
3. `ui/beeper_ui/routes/trust_settings.py` — trust_settings_bp UI Blueprint with settings page and update form
4. `ui/beeper_ui/templates/trust/settings.html` — Full page trust configuration template
5. `ui/beeper_ui/templates/trust/_service_list.html` — HTMX partial for service trust cards
6. `ui/beeper_ui/templates/trust/_update_result.html` — HTMX partial for update result
7. `ui/tests/test_trust_level_service.py` — 31 unit tests for TrustLevelService
8. `ui/tests/test_trust_config_routes.py` — 24 API route tests
9. `ui/tests/test_trust_settings_routes.py` — 15 UI page route tests

**Files modified:**
1. `ui/beeper_ui/routes/__init__.py` — Register trust_config_bp and trust_settings_bp
2. `ui/beeper_ui/templates/base.html` — Add "Trust" nav link
3. `_bmad-output/implementation-artifacts/sprint-status.yaml` — Epic 3 in-progress, story 3-1 status updates
4. `_bmad-output/implementation-artifacts/3-1-trust-level-configuration-persistence.md` — This story file
