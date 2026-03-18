# Story 7.4: Per-Service Health Feeds

Status: review

## Story

As a **user**,
I want to view per-service health feeds with recent investigations, SLO status, and trends,
so that I can get a complete picture of any service's operational health in one view.

## Acceptance Criteria

1. **Given** a user navigates to a service health page (`/services/{name}`) **When** the page loads **Then** the feed shows: current SLO compliance, active investigations, recent resolved investigations (last 7 days), trust level, and reliability trend **And** the page responds within 2 seconds (NFR2)

2. **Given** the service health feed **When** new investigation events occur for that service **Then** the feed updates via SSE without page reload **And** the feed uses ARIA feed role for accessibility

3. **Given** the service list view (`/services`) **When** the page loads **Then** all services are listed with health summary badges (healthy/warning/critical based on SLO status) **And** services with active investigations are highlighted

## Tasks / Subtasks

- [x] Task 1: Create ServiceHealthService to aggregate per-service data (AC: #1, #3)
  - [x] 1.1 Create `ui/beeper_ui/services/service_health_service.py`. Class `ServiceHealthService` takes `operator_url`, `timeout`, and Qdrant connection params. It orchestrates calls to `SloService`, `InvestigationService`, and `TrustLevelService` to build a unified health view per service.
  - [x] 1.2 Add method `get_service_list() -> list[dict]` that: (a) calls `SloService.get_services()` to get all services with SLO status, (b) calls `InvestigationService.list_investigations()` and groups by service, (c) calls the trust level API to get per-service trust levels, (d) returns list of dicts with: `name`, `condition` (healthy/warning/critical from SLO), `compliance` (float), `burn_rate` (float), `active_investigation_count` (int), `trust_level` (int 1-5), `has_active_investigations` (bool), `error_budget_remaining` (float|None).
  - [x] 1.3 Add method `get_service_detail(name: str) -> dict | None` that: (a) calls `SloService.get_service_detail(name)` for SLO data, (b) calls `SloService.get_service_budget(name)` for error budget, (c) calls `InvestigationService.list_investigations(service=name)` for all investigations, (d) partitions investigations into `active` (status != "completed") and `recent_resolved` (completed within last 7 days), (e) fetches trust level via trust API, (f) returns unified dict or None if service not found.
  - [x] 1.4 Add helper `compute_health_status(condition: str, active_count: int) -> str` that returns "critical" if condition is "critical" or active_count >= 3, "warning" if condition is "warning" or active_count >= 1, else "healthy".
  - [x] 1.5 Add `close()` method that closes all internal service clients.

- [x] Task 2: Create services routes (AC: #1, #2, #3)
  - [x] 2.1 Create `ui/beeper_ui/routes/services.py` with `services_bp = Blueprint("services", __name__, url_prefix="/services")`. Register in `ui/beeper_ui/routes/__init__.py` (follow pattern from `slo_bp`, `trust_bp` registrations).
  - [x] 2.2 Add `GET /services/` route `service_list()` that fetches `get_service_list()`, renders `services/list.html` (full page) or `services/_list_content.html` (HTMX partial if `HX-Request` header present). Sort services by health status (critical first, then warning, then healthy).
  - [x] 2.3 Add `GET /services/<name>` route `service_detail(name: str)` that validates name with regex `^[a-zA-Z0-9_-]+$`, fetches `get_service_detail(name)`, renders `services/detail.html` (full page) or `services/_detail_content.html` (HTMX partial). Return 404 if service not found.
  - [x] 2.4 Add `GET /services/<name>/stream` SSE endpoint `service_health_stream(name: str)` using `stream_with_context()` + `Response(mimetype="text/event-stream")` pattern from investigations. Poll every 3 seconds. Emit `investigation-update` event when active investigation count changes for this service. Render `services/_health_feed_items.html` partial as SSE data.

- [x] Task 3: Create service list template (AC: #3)
  - [x] 3.1 Create `ui/beeper_ui/templates/services/list.html` extending `base.html`. Page title "Services". Include breadcrumbs. Body contains `_list_content.html` include.
  - [x] 3.2 Create `ui/beeper_ui/templates/services/_list_content.html`. Render a card grid (reuse `.trust-grid` / `grid-auto-fill` pattern). Each service card shows: service name (h3 link to `/services/{name}`), health badge (healthy/warning/critical using `.status-badge` + `.status-{condition}` CSS classes), SLO compliance percentage, burn rate, trust level badge (`.trust-tl{n}`), active investigation count (highlighted if > 0). Sort: critical first, then warning, then healthy.
  - [x] 3.3 Add filter bar at top with health status filter buttons (All / Healthy / Warning / Critical) using HTMX `hx-get="/services/?status={filter}"` pattern.

- [x] Task 4: Create service detail template (AC: #1, #2)
  - [x] 4.1 Create `ui/beeper_ui/templates/services/detail.html` extending `base.html`. Page title "{service_name} Health". Include breadcrumbs with link back to `/services`. Body wraps `_detail_content.html` in SSE container: `hx-ext="sse" sse-connect="/services/{name}/stream"`.
  - [x] 4.2 Create `ui/beeper_ui/templates/services/_detail_content.html`. Layout in 3 sections:
    - **Header**: Service name, health badge, trust level badge (TL1-5 with name)
    - **Summary cards row** (reuse `.slo-summary-cards` grid pattern): SLO Compliance %, Burn Rate, Error Budget Remaining %, Active Investigations count
    - **Feed section** with `role="feed"` and `aria-label="Service health feed for {name}"` (ARIA feed role per AC #2)
  - [x] 4.3 Create `ui/beeper_ui/templates/services/_health_feed_items.html` partial for the feed items. Render as `article` elements with `role="article"` inside the feed. Two subsections:
    - **Active Investigations**: List with severity badge, investigation ID (linked to `/investigations/{id}`), status, started_at timestamp. Empty state: "No active investigations"
    - **Recently Resolved** (last 7 days): Same format with completed_at timestamp and workflow state badge. Empty state: "No resolved investigations in the last 7 days"
  - [x] 4.4 The feed section uses HTMX lazy-load: `hx-get="/services/{name}/feed-items"` with `hx-trigger="load"` and SSE swap target `sse-swap="investigation-update"` for real-time updates.

- [x] Task 5: Add feed items partial route (AC: #1, #2)
  - [x] 5.1 In `services.py`, add `GET /services/<name>/feed-items` route that fetches investigations for the service, partitions into active and recently resolved, renders `_health_feed_items.html`.

- [x] Task 6: Add CSS styles for service health pages (AC: #1, #2, #3)
  - [x] 6.1 In `ui/beeper_ui/static/css/main.css`, add `.service-health-card` styles (card with border, padding, hover effect — follow `.trust-card` pattern).
  - [x] 6.2 Add `.health-badge` styles extending `.status-badge`: healthy → green (#22c55e), warning → orange (#f59e0b), critical → red (#ef4444). Use pill shape (border-radius: 9999px).
  - [x] 6.3 Add `.service-summary-cards` grid (reuse `.slo-summary-cards` pattern: `grid-template-columns: repeat(auto-fit, minmax(200px, 1fr))`).
  - [x] 6.4 Add `.health-feed` styles for the ARIA feed container. `.feed-item` article styles with left border accent (green for resolved, blue for active, red for critical). `.investigation-count-highlight` for active investigation count > 0 (bold, red text).
  - [x] 6.5 Add `.service-card-highlighted` class for services with active investigations (subtle yellow/amber left-border accent).

- [x] Task 7: Register blueprint and add navigation (AC: #3)
  - [x] 7.1 Register `services_bp` in `ui/beeper_ui/routes/__init__.py`. Follow existing pattern for other blueprints.
  - [x] 7.2 Add "Services" nav item to the sidebar/navigation in `ui/beeper_ui/templates/base.html`. Place after "SLO" nav item.
  - [x] 7.3 Add "Services Health" command to command palette in `ui/beeper_ui/static/js/command-palette.js` with `g+v` chord shortcut.

- [x] Task 8: Write tests (AC: #1, #2, #3)
  - [x] 8.1 Create `ui/tests/test_service_health.py`. Test `ServiceHealthService.get_service_list()`: mock SloService, InvestigationService, trust API responses; verify aggregated list shape, correct health status computation, proper sorting.
  - [x] 8.2 Test `ServiceHealthService.get_service_detail()`: mock all sub-service responses; verify unified dict includes SLO data, partitioned investigations (active vs recent resolved), trust level, error budget.
  - [x] 8.3 Test `compute_health_status()`: critical condition → "critical"; warning condition → "warning"; healthy with 3+ active → "critical"; healthy with 1 active → "warning"; healthy with 0 active → "healthy".
  - [x] 8.4 Test service list route `GET /services/`: returns 200, renders service cards, shows health badges, highlights services with active investigations.
  - [x] 8.5 Test service detail route `GET /services/{name}`: returns 200, renders SLO summary cards, feed section with ARIA feed role, investigation lists.
  - [x] 8.6 Test service detail 404: `GET /services/nonexistent` returns 404.
  - [x] 8.7 Test service name validation: `GET /services/invalid name!` returns 400 or 404.
  - [x] 8.8 Test feed items partial route `GET /services/{name}/feed-items`: returns 200, contains investigation articles, correctly partitions active vs resolved.
  - [x] 8.9 Test SSE stream `GET /services/{name}/stream`: returns event-stream content type, emits `investigation-update` event.
  - [x] 8.10 Test HTMX partial: `GET /services/` with `HX-Request: true` header returns partial content without base layout.
  - [x] 8.11 Test health status filter: `GET /services/?status=critical` returns only critical services.
  - [x] 8.12 Test empty state: when no services exist, show appropriate empty message.

- [x] Task 9: Run full test suite across all components (AC: all)
  - [x] 9.1 Run investigator tests: `cd investigator && poetry run python -m pytest` — 1,013 passed
  - [x] 9.2 Run investigator linting: `cd investigator && poetry run ruff check .` — clean
  - [x] 9.3 Run investigator type checking: `cd investigator && poetry run mypy .` — clean (41 files)
  - [x] 9.4 Run UI tests: `cd ui && poetry run python -m pytest` — 1,903 passed (+33 new)
  - [x] 9.5 Run operator tests: `cd operator && cargo test` — 538 passed
  - [x] 9.6 Verify no regressions from baseline (3,421 tests) — 3,454 total (+33 new)

## Dev Notes

### Architecture Patterns (CRITICAL -- must follow)

**FR50 maps to:** Per-Service Health Feeds — UI-only feature aggregating data from existing SLO, Investigation, and Trust Level services. No operator/investigator code changes needed. [Source: _bmad-output/planning-artifacts/epics.md#Story 7.4, architecture.md FR50]

**Design Decision: Aggregate existing service data, don't add new collections.** The SLO engine (Wave 1), investigation system (v0.1.0+), and trust level service (Wave 2) already provide all needed data. Story 7-4 creates a new UI aggregation layer that combines these into a unified service health view. No new Qdrant collections or operator API endpoints are needed.

**Data Sources (all already exist):**
- `SloService.get_services()` — SLO compliance, burn rate, condition (healthy/warning/critical), error budget. API: `GET /api/v1/slo/services`
- `SloService.get_service_detail(name)` — Per-service SLO detail. API: `GET /api/v1/slo/services/{name}`
- `SloService.get_service_budget(name)` — Error budget remaining, frozen status. API: `GET /api/v1/slo/services/{name}/budget`
- `InvestigationService.list_investigations(service=name)` — Investigations for a service. API: `GET /api/v1/investigations?service={name}`
- Trust Level API: `GET /api/v1/trust/services` and `GET /api/v1/trust/services/{name}` — Trust level (TL1-5) per service
- `Investigation` dataclass: fields `id`, `status`, `service`, `severity`, `condition`, `started_at`, `completed_at`, `workflow_state`

**Reuse existing patterns:**
- Route blueprint pattern from `slo.py` (SloService instantiation + close in finally block)
- HTMX partial pattern: check `request.headers.get("HX-Request")` → render `_content.html` partial else full page
- SSE streaming pattern from `investigations.py`: `stream_with_context()` + `Response(mimetype="text/event-stream")` + 3s poll
- Card grid layout from `_service_list.html` (trust) and `_content.html` (SLO)
- Summary cards from `.slo-summary-cards` CSS grid
- Status badges from `.status-badge .status-{condition}` CSS classes
- Trust level badges from `.trust-tl{n}` CSS classes
- Service name validation regex from `trust_config.py`: `^[a-zA-Z0-9_-]+$`
- Command palette navigation commands from `command-palette.js`
- Test fixtures using Flask test client with mock operator/Qdrant responses

**DO NOT:**
- Add fields to any CRD — all data comes from existing APIs
- Modify the operator or investigator — this is purely UI
- Create redundant service classes — aggregate using existing `SloService`, `InvestigationService`
- Use JavaScript for feed rendering — use Jinja2 + HTMX + SSE
- Use Flask-SocketIO for this feature — use SSE (SocketIO is for collaboration only)

**ARIA Accessibility (AC #2):**
- Feed container: `role="feed"` + `aria-label="Service health feed for {name}"`
- Feed items: `<article role="article">` elements inside the feed
- Health badges: include `aria-label` describing the status
- Follow WCAG 2.1 AA compliance requirement

### Previous Story Intelligence (Story 7-3)

**Key patterns established in 7-3:**
- HTMX lazy-load partial with SSE swap for real-time updates
- SSE event generation only fires when actual state changes (avoid unnecessary re-renders)
- `compute_*()` helper functions for derived status from raw data
- Template partials with empty state messages

**Issues found in 7-3 code review (avoid repeating):**
- HIGH: Ensure timestamps are available before claiming them in the AC (7-3 had timestamp gap)
- MEDIUM: SSE should only fire on actual state changes, not every poll cycle
- MEDIUM: Don't leave dead template variables
- LOW: Clean up unused code

**Issues from 7-2 review (still relevant):**
- HIGH: Ensure ALL routes claimed as implemented actually exist and work
- HIGH: Ensure ALL template features claimed as implemented actually render
- MEDIUM: Consolidate shared CSS into grouped selectors
- LOW: Use `@require_role("user")` on user-facing routes

### Project Structure Notes

- New route file: `ui/beeper_ui/routes/services.py` (new blueprint)
- New service: `ui/beeper_ui/services/service_health_service.py`
- New templates: `ui/beeper_ui/templates/services/list.html`, `_list_content.html`, `detail.html`, `_detail_content.html`, `_health_feed_items.html`
- Modified: `ui/beeper_ui/routes/__init__.py` (register blueprint), `base.html` (nav), `command-palette.js` (command), `main.css` (styles)
- New tests: `ui/tests/test_service_health.py`
- No operator or investigator changes

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 7.4]
- [Source: _bmad-output/planning-artifacts/architecture.md - FR50, NFR2]
- [Source: ui/beeper_ui/services/slo_service.py - SloService API]
- [Source: ui/beeper_ui/services/investigation_service.py - InvestigationService]
- [Source: ui/beeper_ui/services/trust_level_service.py - TrustLevelService]
- [Source: ui/beeper_ui/routes/slo.py - Route/HTMX patterns]
- [Source: ui/beeper_ui/routes/investigations.py - SSE streaming pattern]
- [Source: ui/beeper_ui/routes/trust_config.py - Trust API and service name validation]
- [Source: _bmad-output/implementation-artifacts/7-3-remediation-progress-tracking.md - Previous story patterns]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References
N/A

### Completion Notes List
- Created `ServiceHealthService` aggregation service that combines SLO, Investigation, and Trust Level data into unified per-service health views
- Added `compute_health_status()` helper: critical if SLO critical or 3+ active investigations, warning if SLO warning or 1+ active, else healthy
- Created `/services/` route with card grid layout, health badges, HTMX filter buttons (All/Healthy/Warning/Critical)
- Created `/services/<name>` detail route with SLO summary cards, ARIA feed role, SSE real-time updates
- Created 5 Jinja2 templates: list.html, _list_content.html, detail.html, _detail_content.html, _health_feed_items.html
- Added SSE streaming endpoint with 3s polling, emits `investigation-update` only when active count changes
- Added comprehensive CSS: health badges, service card grid, summary cards, feed items with color-coded borders, filter bar
- Added "Services" nav link and "Services Health" command palette entry with `g+v` chord shortcut
- 33 new tests covering: compute_health_status (7), service list (3), service detail (3), routes (7+4+3), SSE (2), nav (2), access control (2)
- All 3,454 tests passing (1,013 investigator + 1,903 UI + 538 operator)

### File List
- `ui/beeper_ui/services/service_health_service.py` (created — ServiceHealthService aggregation service)
- `ui/beeper_ui/routes/services.py` (created — services blueprint with list, detail, feed-items, stream routes)
- `ui/beeper_ui/routes/__init__.py` (modified — registered services_bp)
- `ui/beeper_ui/templates/services/list.html` (created — service list page)
- `ui/beeper_ui/templates/services/_list_content.html` (created — service card grid with filter bar)
- `ui/beeper_ui/templates/services/detail.html` (created — service detail page with SSE)
- `ui/beeper_ui/templates/services/_detail_content.html` (created — summary cards + health feed)
- `ui/beeper_ui/templates/services/_health_feed_items.html` (created — feed items with ARIA articles)
- `ui/beeper_ui/templates/base.html` (modified — added Services nav link)
- `ui/beeper_ui/static/js/command-palette.js` (modified — added Services Health command + g+v chord)
- `ui/beeper_ui/static/css/main.css` (modified — service health styles)
- `ui/tests/test_service_health.py` (created — 33 tests)
