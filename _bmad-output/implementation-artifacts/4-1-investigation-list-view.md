# Story 4.1: Investigation List View

Status: ready-for-dev

## Story

As an **SRE**,
I want to view a list of active investigations,
so that I can see what Beeper is currently working on and prioritize my attention.

## Acceptance Criteria

1. **Given** I navigate to the Investigations page, **When** the page loads, **Then** I see a list of all active investigations (FR31) **And** each investigation shows: ID, status, service, started time, severity.

2. **Given** investigations are in various states, **When** I view the list, **Then** investigations are grouped/sorted by status: `investigating` (in progress), `awaiting_confirmation` (needs human input), `completed` (recently finished).

3. **Given** new investigations start, **When** I am viewing the list, **Then** the list updates via SSE without page refresh **And** new investigations appear at the top.

4. **Given** I want to filter investigations, **When** I use filter controls, **Then** I can filter by: status, service, severity, date range.

## Tasks / Subtasks

- [ ] Task 1: Add Investigation List API endpoint to operator (AC: 1, 2)
  - [ ] 1.1 Add `GET /api/v1/investigations` handler in `operator/src/api.rs` that lists Investigation CRDs via `Api<Investigation>::list()`
  - [ ] 1.2 Create `InvestigationListResponse` struct with fields: `id: String`, `status: String` (phase), `service: String`, `severity: String`, `condition: String`, `started_at: Option<String>`, `completed_at: Option<String>`, `triggered_at: Option<String>`
  - [ ] 1.3 Map `InvestigationPhase` to UI-friendly status strings: `Pending`/`Running` → `investigating`, `Completed` → `completed`, `Failed` → `failed` (note: `awaiting_confirmation` will come from investigator status message in future story 4-5)
  - [ ] 1.4 Support query params for filtering: `?status=investigating&service=payments&severity=high`
  - [ ] 1.5 Register route in `api_router()` alongside existing `/api/v1/sources`, `/api/v1/health/components` routes
  - [ ] 1.6 Return JSON array sorted by: `awaiting_confirmation` first, then `investigating`, then `completed` (most recent first within each group)

- [ ] Task 2: Create InvestigationService in UI (AC: 1, 2, 4)
  - [ ] 2.1 Create `ui/beeper_ui/services/investigation_service.py` following `SourceService` pattern — use `httpx.Client` with connection pooling, lazy initialization
  - [ ] 2.2 Create `Investigation` dataclass: `id: str`, `status: str`, `service: str`, `severity: str`, `condition: str`, `started_at: str | None`, `completed_at: str | None`, `triggered_at: str | None`
  - [ ] 2.3 Add `list_investigations(status: str | None, service: str | None, severity: str | None, date_from: str | None, date_to: str | None) -> list[Investigation]` method
  - [ ] 2.4 Call `GET {OPERATOR_URL}/api/v1/investigations` with query params for filtering
  - [ ] 2.5 Create `InvestigationServiceError` custom exception
  - [ ] 2.6 Handle operator connection errors with graceful degradation (return empty list + log warning, like SourceService pattern)

- [ ] Task 3: Create Investigation List routes (AC: 1, 2, 4)
  - [ ] 3.1 Create `ui/beeper_ui/routes/investigations.py` with `investigations_bp = Blueprint("investigations", __name__, url_prefix="/investigations")`
  - [ ] 3.2 Add `GET /investigations/` route: fetch investigations from `InvestigationService`, detect `HX-Request` header for partial vs full page response
  - [ ] 3.3 Support filter query params: `status`, `service`, `severity`, `date_range` — validate/sanitize using same patterns as KB routes (whitelist status/severity values)
  - [ ] 3.4 Register blueprint in `routes/__init__.py` `register_blueprints()` function
  - [ ] 3.5 Add "Investigations" link to `templates/base.html` navigation

- [ ] Task 4: Create Investigation List templates (AC: 1, 2, 4)
  - [ ] 4.1 Create `ui/beeper_ui/templates/investigations/list.html` — full page extending `base.html`, includes filter panel and list content partial
  - [ ] 4.2 Create `ui/beeper_ui/templates/investigations/_list_content.html` — HTMX partial with investigation table/cards grouped by status
  - [ ] 4.3 Create `ui/beeper_ui/templates/investigations/_filter_panel.html` — filter controls: status dropdown (`investigating`, `awaiting_confirmation`, `completed`, `failed`), service dropdown, severity dropdown (`low`, `medium`, `high`, `critical`), date range dropdown (`today`, `7d`, `30d`, `90d`) — reuse `_filter_panel.html` patterns from knowledge templates
  - [ ] 4.4 Create `ui/beeper_ui/templates/investigations/_investigation_row.html` — single investigation row/card with: severity indicator (color-coded), status badge, service name, condition summary (truncated), started time (relative), ID
  - [ ] 4.5 Add empty state for no investigations ("No active investigations")
  - [ ] 4.6 Add error state for operator connection failure

- [ ] Task 5: Implement SSE endpoint for real-time updates (AC: 3)
  - [ ] 5.1 Create `GET /investigations/stream` SSE endpoint in `investigations.py` — Flask streaming response with `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`
  - [ ] 5.2 Use Python generator yielding `data: {json}\n\n` format — poll operator API at 3-second intervals (MVP polling-backed SSE, per architecture: "Polling acceptable (2-3 second intervals)")
  - [ ] 5.3 Detect changes between polls — only send SSE event when investigation list differs from previous poll (compare by id+status+phase)
  - [ ] 5.4 SSE event types: `investigation-update` (full list refresh), `investigation-new` (new investigation added)
  - [ ] 5.5 Add client-side HTMX SSE integration: use `hx-ext="sse"` with `sse-connect="/investigations/stream"` and `sse-swap="investigation-update"` on the list container — add HTMX SSE extension JS (`htmx-ext-sse`) to static assets
  - [ ] 5.6 Handle SSE connection lifecycle: client disconnect detection (generator cleanup), reconnection via EventSource default behavior

- [ ] Task 6: Add CSS styles for investigation list (AC: 1, 2)
  - [ ] 6.1 Add investigation-specific styles to `static/css/main.css`: `.investigation-row`, `.severity-indicator` (color per severity: low=blue, medium=yellow, high=orange, critical=red), `.status-badge` variants, `.investigation-condition` (truncated text)
  - [ ] 6.2 Add status group headers/dividers for investigation grouping
  - [ ] 6.3 Ensure consistent styling with existing `.entry-type-badge`, `.service-badge`, `.filter-panel` patterns

- [ ] Task 7: Operator API tests (AC: 1, 2)
  - [ ] 7.1 Test `GET /api/v1/investigations` returns empty list when no Investigation CRDs exist
  - [ ] 7.2 Test response includes all required fields (id, status, service, severity, condition, timestamps)
  - [ ] 7.3 Test status mapping: `Running` → `investigating`, `Completed` → `completed`
  - [ ] 7.4 Test filtering by status, service, severity query params
  - [ ] 7.5 Test sort order: awaiting_confirmation > investigating > completed
  - [ ] 7.6 Test response format matches OpenAPI spec patterns (snake_case, ISO 8601 timestamps)

- [ ] Task 8: UI route and service tests (AC: 1, 2, 3, 4)
  - [ ] 8.1 Test `InvestigationService.list_investigations()` calls operator API correctly
  - [ ] 8.2 Test `InvestigationService` handles operator connection error gracefully (returns empty list)
  - [ ] 8.3 Test `GET /investigations/` returns full page HTML (no HX-Request header)
  - [ ] 8.4 Test `GET /investigations/` returns partial HTML (with HX-Request header)
  - [ ] 8.5 Test filter params are passed through to service layer
  - [ ] 8.6 Test `GET /investigations/stream` returns SSE content type
  - [ ] 8.7 Test empty state rendering when no investigations
  - [ ] 8.8 Test error state rendering when operator unavailable
  - [ ] 8.9 Test filter validation (reject invalid status/severity values)

## Dev Notes

### Architecture Decision: SSE via Polling-Backed Generator

The architecture specifies SSE for real-time updates but also notes "Polling acceptable (2-3 second intervals)" for MVP. Implement SSE endpoint that internally polls the operator API every 3 seconds and only pushes events when data changes. This provides the SSE interface for the client (future-proof for NATS JetStream) while keeping the backend simple.

**HTMX SSE Extension:** HTMX does not include SSE support natively — it requires the `htmx-ext-sse` extension. Download from the HTMX extensions CDN or npm package `htmx-ext-sse`. Place in `static/js/`. The extension provides `sse-connect` and `sse-swap` attributes.

### Architecture Decision: Operator API First

The operator must expose `GET /api/v1/investigations` before the UI can consume it. The endpoint should list Investigation CRDs from the Kubernetes API using `Api<Investigation>::list()` — same pattern as `list_sources()` in `api.rs`. Use Axum's query parameter extraction for filtering.

### Design Pattern: Service Layer

Follow existing service layer pattern (SourceService, HealthService, KBService):
- Lazy-initialized `httpx.Client` with connection pooling
- Custom `InvestigationServiceError` exception
- Dataclass for `Investigation` response model
- Graceful degradation on operator connection failure

### Design Pattern: HTMX Request Detection

```python
if request.headers.get("HX-Request"):
    return render_template("investigations/_list_content.html", ...)
return render_template("investigations/list.html", ...)
```

### Design Pattern: Filter Panel

Reuse the KB filter panel pattern with HTMX-driven filtering:
- Dropdown `<select>` elements with `hx-get` + `hx-trigger="change"`
- `hx-include` to collect all filter values
- `hx-target` to replace list content
- Active filters as removable chips

### Investigation Status Mapping

| CRD Phase | UI Status | Display |
|-----------|-----------|---------|
| Pending | investigating | In Progress |
| Running | investigating | In Progress |
| Completed | completed | Completed |
| Failed | failed | Failed |
| (future: from investigator message) | awaiting_confirmation | Awaiting Confirmation |

Note: `awaiting_confirmation` status will be fully implemented in Story 4-5 (Resolution Confirmation). For now, include it in filter options but no investigations will have this status until the investigator pipeline supports it.

### Severity Color Coding

| Severity | Color | CSS Class |
|----------|-------|-----------|
| Low | Blue (#3b82f6) | `.severity-low` |
| Medium | Yellow (#eab308) | `.severity-medium` |
| High | Orange (#f97316) | `.severity-high` |
| Critical | Red (#ef4444) | `.severity-critical` |

### Existing Patterns to Reuse

- **Blueprint registration:** `routes/__init__.py` `register_blueprints()` — add `investigations_bp`
- **Base template nav:** `templates/base.html` — add Investigations link between KB and Sources
- **Filter panel HTML:** `knowledge/_filter_panel.html` — CSS-only accordion pattern
- **Service initialization:** `source_service.py` — lazy httpx.Client with config timeout
- **Date range parsing:** `kb_service.py` `parse_date_range()` — reuse for date filter
- **Query sanitization:** `knowledge.py` `sanitize_query()` — adapt for investigation filters

### Anti-Patterns to Avoid

- **DO NOT** create a new httpx client per request — use lazy singleton with connection pooling
- **DO NOT** use camelCase in JSON responses — always snake_case with `serde(rename_all = "snake_case")`
- **DO NOT** render unsanitized HTML — sanitize investigation conditions with bleach
- **DO NOT** hardcode operator URL — use `current_app.config["OPERATOR_URL"]`
- **DO NOT** use JavaScript frameworks — HTMX + SSE extension only
- **DO NOT** skip error handling — every operator API call must handle connection errors gracefully

### Key File Paths

| Component | Path |
|-----------|------|
| Operator API | `operator/src/api.rs` |
| Investigation CRD | `operator/src/crds/investigation.rs` |
| Operator main | `operator/src/main.rs` |
| UI app factory | `ui/beeper_ui/app.py` |
| UI config | `ui/beeper_ui/config.py` |
| Blueprint registry | `ui/beeper_ui/routes/__init__.py` |
| Sources route (pattern) | `ui/beeper_ui/routes/sources.py` |
| KB route (filter pattern) | `ui/beeper_ui/routes/knowledge.py` |
| Source service (pattern) | `ui/beeper_ui/services/source_service.py` |
| KB service (filter pattern) | `ui/beeper_ui/services/kb_service.py` |
| Base template | `ui/beeper_ui/templates/base.html` |
| CSS styles | `ui/beeper_ui/static/css/main.css` |
| HTMX library | `ui/beeper_ui/static/js/htmx.min.js` |

### Testing Standards

- **Rust (operator):** Use `#[tokio::test]`, mock K8s API with `kube::Client::try_default()` or test fixtures
- **Python (UI routes):** Use pytest with Flask test client from `conftest.py`, `respx` for mocking operator HTTP calls
- **Template tests:** Verify both full-page and HX-Request partial responses
- **Error handling:** Test graceful degradation when operator is unavailable
- **Linting:** Run `ruff check`, `mypy --strict`, `cargo clippy` before marking complete

### Project Structure Notes

- New files follow existing conventions: `snake_case.py`, `snake_case.rs`
- Templates go in `templates/investigations/` subdirectory (matching `templates/sources/`, `templates/knowledge/`)
- Service goes in `services/investigation_service.py` (matching `source_service.py`, `kb_service.py`)
- Route goes in `routes/investigations.py` (matching `sources.py`, `knowledge.py`)
- No new Python dependencies needed (Flask streaming and httpx already available)
- HTMX SSE extension is the only new JS asset needed

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 4, Story 4.1]
- [Source: _bmad-output/planning-artifacts/architecture.md — UI Architecture, API Patterns, SSE]
- [Source: operator/src/api.rs — existing API endpoint patterns]
- [Source: operator/src/crds/investigation.rs — Investigation CRD structure]
- [Source: ui/beeper_ui/routes/sources.py — HTMX polling pattern]
- [Source: ui/beeper_ui/routes/knowledge.py — filter panel pattern]
- [Source: ui/beeper_ui/services/source_service.py — service layer pattern]
- [Source: _bmad-output/implementation-artifacts/epic-3-retro — lessons learned]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created
- SSE polling-backed design chosen for MVP simplicity with future NATS migration path
- Operator API endpoint must be implemented first (Rust) before UI can consume
- HTMX SSE extension required as new static asset

### File List
