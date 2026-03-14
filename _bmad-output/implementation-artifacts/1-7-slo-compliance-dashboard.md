# Story 1.7: SLO Compliance Dashboard

Status: done

## Story

As a **user**,
I want to view SLO compliance, burn rate trends, and error budgets on a dashboard,
so that I can understand the reliability posture of all services at a glance.

## Acceptance Criteria

1. **AC1: Service list with live SLO data**
   **Given** services with active ServiceLevel CRDs
   **When** a user navigates to the SLO dashboard (`/slo`)
   **Then** all services are listed with current compliance percentage, burn rate, and error budget remaining
   **And** the page responds within 2 seconds (NFR2)

2. **AC2: Service detail with burn rate and budget breakdown**
   **Given** a specific service on the SLO dashboard
   **When** a user clicks to view service detail (`/slo/services/{name}`)
   **Then** burn rate trends, compliance history, and error budget consumption are displayed
   **And** active investigations related to SLO breaches are linked
   **And** error budget policy status (triggered thresholds, freeze status) is shown

3. **AC3: Read-only access for all authenticated users**
   **Given** the SLO dashboard route
   **When** accessed by any authenticated user (admin or user role)
   **Then** the dashboard is visible (read-only — SLO configuration is admin-only via CRD)

## Tasks / Subtasks

- [x] Task 1: Create `ui/beeper_ui/services/slo_service.py` — SLO data service (AC: #1, #2)
  - [x]1.1: Create `SloService` class following `HealthService` pattern — httpx client with configurable `operator_url` and `timeout`, lazy `client` property, `close()` method
  - [x]1.2: Implement `get_services() -> list[dict]` — calls `GET /api/v1/slo/services`, returns `service_levels` array from `ServiceLevelListResponse`. On error, log and return empty list
  - [x]1.3: Implement `get_service_detail(name: str) -> dict | None` — calls `GET /api/v1/slo/services/{name}`, returns `ServiceLevelDetailResponse` dict. Returns None on 404
  - [x]1.4: Implement `get_service_budget(name: str) -> dict | None` — calls `GET /api/v1/slo/services/{name}/budget`, returns `ErrorBudgetResponse` dict. Returns None on 404
  - [x]1.5: Add helper `format_compliance(value: float | None) -> str` — formats compliance as percentage (e.g., 0.999 → "99.90%"), returns "N/A" for None
  - [x]1.6: Add helper `format_burn_rate(value: float | None) -> str` — formats burn rate with 1 decimal (e.g., 5.2 → "5.2x"), returns "N/A" for None
  - [x]1.7: Add helper `format_budget_remaining(value: float | None) -> str` — formats budget as percentage (e.g., 0.75 → "75.0%"), returns "N/A" for None
  - [x]1.8: Add helper `format_projected_exhaustion(secs: float | None) -> str` — converts seconds to human-readable (e.g., "3d 4h", "2h 30m", "45m"), returns "N/A" for None/zero
  - [x]1.9: Add helper `condition_css_class(condition: str) -> str` — maps condition to CSS class: "healthy" → "status-healthy", "warning" → "status-warning", "critical" → "status-critical", default → "status-neutral"

- [x] Task 2: Create `ui/beeper_ui/routes/slo.py` — SLO dashboard blueprint (AC: #1, #2, #3)
  - [x]2.1: Create `slo_bp = Blueprint("slo", __name__, url_prefix="/slo")` following existing blueprint patterns
  - [x]2.2: Create `get_slo_service() -> SloService` factory function returning new `SloService` instance with `OPERATOR_URL` from config
  - [x]2.3: Implement `GET /slo/` route (`slo_dashboard`) — loads all services via `slo_service.get_services()`, renders `slo/dashboard.html` for full request, `slo/_content.html` for HTMX request (check `HX-Request` header). No `@require_role()` — accessible to both admin and user
  - [x]2.4: Implement `GET /slo/services/<name>` route (`slo_service_detail`) — loads service detail via `slo_service.get_service_detail(name)` and budget via `slo_service.get_service_budget(name)`. Renders `slo/service.html`. Returns 404 if service not found
  - [x]2.5: Pass SloService helper functions to templates via template context or register as Jinja2 template globals/filters
  - [x]2.6: Error handling: wrap service calls in try/except, log exceptions, render error state in template (follow existing patterns from metrics.py)

- [x] Task 3: Register blueprint and add navigation (AC: #1, #3)
  - [x]3.1: Register `slo_bp` in `ui/beeper_ui/routes/__init__.py` following existing blueprint registration pattern
  - [x]3.2: Add "SLO" navigation link to `ui/beeper_ui/templates/base.html` sidebar/navigation, placed after existing nav items

- [x] Task 4: Create SLO dashboard template `ui/beeper_ui/templates/slo/dashboard.html` (AC: #1)
  - [x]4.1: Create `slo/` template directory
  - [x]4.2: Create `dashboard.html` extending `base.html` with title "SLO Compliance - Beeper"
  - [x]4.3: Header section: "SLO Compliance Dashboard" heading with description "Service reliability posture across all monitored services"
  - [x]4.4: Summary cards row: Total Services count, Services Meeting SLO (healthy count), Services At Risk (warning+critical count), Budget Frozen count — using `.card` and grid CSS classes
  - [x]4.5: Services table: columns for Service Name, SLI Type, Target, Compliance, Burn Rate, Error Budget Remaining, Status (condition), Frozen status. Each row links to service detail page. Use status color CSS classes for condition column
  - [x]4.6: Empty state: "No ServiceLevel CRDs configured" message with `.empty-state` class when no services exist
  - [x]4.7: Error state: display error card when API call fails
  - [x]4.8: Extract main content into `_content.html` partial for HTMX updates. Include partial in full page template with `{% include "slo/_content.html" %}`

- [x] Task 5: Create SLO service detail template `ui/beeper_ui/templates/slo/service.html` (AC: #2)
  - [x]5.1: Create `service.html` extending `base.html` with title "{{ service.name }} SLO - Beeper"
  - [x]5.2: Back link to SLO dashboard (`/slo`)
  - [x]5.3: Service header: name, service identifier, SLI type, condition badge with status color
  - [x]5.4: Overview cards row: Compliance (formatted %), Burn Rate (formatted x), Error Budget Remaining (formatted %), Projected Exhaustion (human-readable time)
  - [x]5.5: SLO Configuration card: target, window, SLI details (metric, selectors), burn rate alert thresholds
  - [x]5.6: Error Budget Policy card (if budget data available): budget total, consumed, remaining as progress bar. Freeze status badge. Triggered policy events list with threshold, action, trigger time
  - [x]5.7: Linked Investigations section (placeholder): "Related investigations will be linked when the investigation-SLO correlation is implemented" — display as informational note. The operator API doesn't yet return investigation links from the SLO endpoint
  - [x]5.8: 404 page when service not found

- [x] Task 6: Add CSS styles for SLO dashboard (AC: #1, #2)
  - [x]6.1: Add SLO-specific styles to `ui/beeper_ui/static/css/main.css`: `.slo-summary-cards` grid, `.slo-summary-card` individual cards, `.slo-table` for services table, `.slo-config-section` for detail view config display
  - [x]6.2: Add budget progress bar styles: `.budget-bar`, `.budget-bar-track`, `.budget-bar-fill` with color based on consumption level (green < 50%, amber 50-80%, red > 80%)
  - [x]6.3: Add frozen badge style: `.frozen-badge` with red/critical styling
  - [x]6.4: Reuse existing status classes (`.status-healthy`, `.status-warning`, `.status-critical`, `.status-neutral`) for condition badges

- [x] Task 7: Write comprehensive tests (AC: #1, #2, #3)
  - [x]7.1: Create `ui/tests/test_slo_service.py` — unit tests for `SloService`:
    - `test_get_services_success` — mock API, verify list returned
    - `test_get_services_empty` — mock empty response
    - `test_get_services_api_error` — mock connection error, verify empty list returned
    - `test_get_service_detail_success` — mock API, verify dict returned
    - `test_get_service_detail_not_found` — mock 404, verify None returned
    - `test_get_service_budget_success` — mock API, verify dict returned
    - `test_get_service_budget_not_found` — mock 404, verify None returned
    - `test_format_compliance` — 0.999 → "99.90%", 1.0 → "100.00%", None → "N/A"
    - `test_format_burn_rate` — 5.2 → "5.2x", 0.0 → "0.0x", None → "N/A"
    - `test_format_budget_remaining` — 0.75 → "75.0%", 0.0 → "0.0%", None → "N/A"
    - `test_format_projected_exhaustion` — 259200.0 → "3d 0h", 9000.0 → "2h 30m", 0.0 → "N/A", None → "N/A"
    - `test_condition_css_class` — all mappings
  - [x]7.2: Create `ui/tests/test_slo_routes.py` — route integration tests:
    - `test_slo_dashboard_renders` — GET /slo/, verify 200 and page content
    - `test_slo_dashboard_htmx_partial` — GET /slo/ with HX-Request header, verify partial returned (no base.html wrapping)
    - `test_slo_dashboard_empty_services` — no services configured, verify empty state message
    - `test_slo_dashboard_api_error` — operator unavailable, verify error card
    - `test_slo_dashboard_shows_service_data` — verify compliance, burn rate, budget rendered
    - `test_slo_service_detail_renders` — GET /slo/services/test-slo, verify 200 and detail content
    - `test_slo_service_detail_not_found` — GET /slo/services/nonexistent, verify 404
    - `test_slo_service_detail_with_budget` — verify budget data, freeze status, policy events displayed
    - `test_slo_dashboard_accessible_by_user` — user role can access /slo/
    - `test_slo_dashboard_accessible_by_admin` — admin role can access /slo/
    - `test_slo_navigation_link_present` — verify "SLO" link in base nav
  - [x]7.3: Regression guard — all existing Python tests (482 investigator + 657 UI) must pass

## Dev Notes

### Architecture Compliance

**File Placement (from architecture.md):**
```
ui/beeper_ui/routes/slo.py              # /slo — SLO dashboard, burn rates, error budgets
ui/beeper_ui/services/slo_service.py    # SLO data from operator API
ui/beeper_ui/templates/slo/
    dashboard.html                       # Compliance, burn rates, error budgets
    service.html                         # Per-service SLO detail
    _content.html                        # HTMX partial for dashboard
```
[Source: _bmad-output/planning-artifacts/architecture.md#Component Architecture]

**FR to File Mapping (from architecture.md):**
- FR6 (SLO dashboard): `ui/routes/slo.py`, `ui/services/slo_service.py`, `ui/templates/slo/`
[Source: _bmad-output/planning-artifacts/architecture.md#FR to Structure Mapping]

**API Endpoints Consumed (from operator, Stories 1-3 through 1-6):**
```
GET  /api/v1/slo/services                    # List services with SLO status
GET  /api/v1/slo/services/{name}             # Service SLO detail + burn rate
GET  /api/v1/slo/services/{name}/budget      # Error budget status
```
[Source: _bmad-output/planning-artifacts/architecture.md#API Endpoints]

**Response Shapes from Operator API:**
```
ServiceLevelListResponse:
  service_levels: [{name, service, sli_type, target, window, condition,
                    alerts_registered?, last_evaluated?, compliance?,
                    burn_rate?, error_budget_remaining?, is_frozen?}]

ServiceLevelDetailResponse:
  {name, service, sli: {type, metric, good_selector, total_selector},
   objective: {target, window}, burn_rate_alerts: [{severity, short_window,
   long_window, factor}], condition, alerts_registered?, last_evaluated?,
   error?, compliance?, burn_rate?, error_budget_remaining?, is_frozen?}

ErrorBudgetResponse:
  {name, service, target, error_budget_total, error_budget_remaining,
   error_budget_consumed, burn_rate, projected_exhaustion_secs?,
   is_frozen, triggered_policies: [{threshold, action, triggered_at,
   consumption_at_trigger}]}
```
[Source: operator/src/api.rs]

### Implementation Approach

**Key Design Decisions:**

1. **Service layer calls operator HTTP API (not Qdrant directly):**
   The SLO dashboard reads from the operator's REST API, which serves data from its in-memory `SloCache` and `BudgetPolicyState`. No direct Qdrant queries needed. This follows the same pattern as `HealthService`.

2. **httpx client for API calls (not requests):**
   The project uses `httpx` for HTTP client calls (see `health_service.py`). Use `httpx.Client` with configurable timeout. Mock with `respx` in tests.

3. **Blueprint pattern:**
   Create `slo_bp = Blueprint("slo", __name__, url_prefix="/slo")` matching existing blueprints (metrics, spending, etc.). Register in `routes/__init__.py`.

4. **HTMX partial pattern:**
   Every page route checks `request.headers.get("HX-Request")` — returns full page for initial load, partial `_content.html` for HTMX refreshes. This enables future auto-refresh via `hx-trigger="every 30s"`.

5. **No `@require_role()` decorator:**
   AC3 says both admin and user roles can access the dashboard (read-only). SLO configuration is admin-only via CRD, not via UI. So no role restriction on routes.

6. **Navigation placement:**
   Add "SLO" to the navigation bar in `base.html` after existing items. Follow same `<a>` tag pattern with `url_for('slo.slo_dashboard')`.

7. **Linked investigations (placeholder):**
   The operator API does not currently return investigation links from SLO endpoints. AC2 says "active investigations related to SLO breaches are linked" — for now, show a placeholder note. Full investigation-SLO linkage will come when the investigation list is extended with SLO context.

8. **Error handling:**
   Follow existing patterns: try/except around service calls, log the exception, render template with `error_message` variable. The template shows an error card when `error_message` is set.

9. **CSS approach:**
   Use existing CSS classes from `main.css` where possible (`.card`, `.container`, `.status-healthy`, `.status-warning`, `.status-critical`, `.empty-state`, `.error-card`). Add minimal SLO-specific styles for the summary cards grid, services table, and budget progress bar.

### Technical Requirements

- **Python 3.11+** — all UI code is Python
- **Flask 3.0** — web framework
- **httpx** — HTTP client for operator API calls
- **Jinja2** — templates (via Flask)
- **HTMX** — client-side dynamic updates (already loaded in base.html)
- **No new Python dependencies required** — httpx already in pyproject.toml

### Library & Framework Requirements

- Use `httpx.Client` for operator API calls — NOT `requests`
- Use `respx` for mocking HTTP calls in tests — NOT `responses` or `unittest.mock`
- Use Flask `Blueprint` for route registration — NOT direct app.route
- Use Jinja2 `{% extends "base.html" %}` — NOT standalone HTML
- Use existing CSS classes from `main.css` — do NOT create a separate stylesheet
- Format numbers in Python service helpers — NOT in Jinja2 template logic

### File Structure Requirements

**New files to create:**
```
ui/beeper_ui/services/slo_service.py         # SloService class + format helpers
ui/beeper_ui/routes/slo.py                   # slo_bp blueprint with routes
ui/beeper_ui/templates/slo/dashboard.html    # Full SLO dashboard page
ui/beeper_ui/templates/slo/_content.html     # HTMX partial for dashboard content
ui/beeper_ui/templates/slo/service.html      # Per-service SLO detail page
ui/tests/test_slo_service.py                 # Service unit tests
ui/tests/test_slo_routes.py                  # Route integration tests
```

**Files to modify:**
```
ui/beeper_ui/routes/__init__.py              # Register slo_bp blueprint
ui/beeper_ui/templates/base.html             # Add SLO nav link
ui/beeper_ui/static/css/main.css             # Add SLO-specific styles
```

### Testing Requirements

- **Framework:** pytest with Flask test client
- **HTTP mocking:** `respx` for operator API calls (same as test_routes.py, test_health.py)
- **Qdrant mocking:** Not needed — SLO dashboard reads from operator API only
- **Role testing:** Use `client` (default user), `admin_client`, `user_client` fixtures from conftest.py
- **HTMX testing:** Send `HX-Request: true` header, verify partial template returned
- **Regression:** All existing tests (482 investigator + 657 UI) must pass
- **Test data:** Create mock API responses matching exact operator response shapes

### Critical Guardrails

1. **DO NOT query Qdrant directly.** The SLO dashboard reads from the operator's REST API. The operator handles all Prometheus/Qdrant interactions.
2. **DO NOT add role restrictions.** AC3 explicitly says both admin and user can access. SLO configuration is via CRD, not UI.
3. **DO NOT use `requests` library.** The project uses `httpx` for HTTP calls and `respx` for test mocking.
4. **DO NOT create inline JavaScript for charts.** This story uses static HTML tables and formatted text. Chart visualizations (burn rate trends) will be enhanced in future stories.
5. **DO NOT modify operator code.** This story is UI-only. All operator API endpoints already exist from Stories 1-3 through 1-6.
6. **DO NOT add new Python dependencies.** Everything needed (httpx, Flask, Jinja2) is already in pyproject.toml.
7. **Follow existing Flask blueprint patterns exactly.** Look at `metrics.py`, `spending.py`, `health.py` for reference.
8. **Follow existing CSS patterns.** Reuse `.card`, `.status-*`, `.empty-state`, `.error-card` classes. Add minimal new styles.
9. **Follow existing test patterns.** Use `respx.mock` decorator for HTTP mocking, Flask test client fixtures, check for response content with `assert b"expected" in response.data`.
10. **Register blueprint with correct import pattern.** Follow `routes/__init__.py` existing structure.
11. **Pass format helpers to templates.** Either register as Jinja2 globals or pass in template context dict.
12. **Handle operator unavailability gracefully.** Show error card, don't crash.
13. **HTMX partial must work standalone.** The `_content.html` partial should not depend on variables only set in the full page template.

### Previous Story Intelligence

**Story 1-6 (Error Budget Policies) — direct data source:**
- Created `ErrorBudgetResponse` with `is_frozen`, `triggered_policies`, `projected_exhaustion_secs` — all consumed by this dashboard
- `BudgetPolicyState` is served via API at `GET /api/v1/slo/services/{name}/budget`
- Freeze status visible in both list (`is_frozen: Option<bool>`) and detail responses
- Code review found: unused variable in API handler — ensure clean data usage patterns

**Story 1-5 (Customer Impact Scoring) — related context:**
- Extended API responses with `compliance`, `burn_rate`, `error_budget_remaining` fields
- These fields are `Option<T>` in Rust / may be null in JSON — handle None in Python service

**Story 1-4 (SLO Burn Rate Calculation Engine) — direct data source:**
- Created SloCache and SloCalculationResult — data source for list/detail responses
- `compliance`, `burn_rate`, `error_budget_remaining` populated from 5-second engine cycle
- Fields are `Option<f64>` — can be null when no metrics data available yet

**Story 1-3 (ServiceLevel CRD & Controller) — foundation:**
- Created `GET /api/v1/slo/services` and `GET /api/v1/slo/services/{name}` endpoints
- `ServiceLevelResponse` and `ServiceLevelDetailResponse` structs define response shapes
- `condition` field: "healthy", "warning", "critical", "unknown"
- `sli_type` field: "availability", "latency", "error_rate"

**Existing UI patterns (from codebase exploration):**
- `HealthService` in `health_service.py` — exact httpx pattern to follow
- `MetricsService` in `metrics_service.py` — Qdrant pattern (NOT used here, use httpx)
- `metrics.py` route — HTMX partial pattern, filter bar, error handling
- `spending.py` route — dashboard card layout pattern
- `conftest.py` — `app`, `client`, `admin_client`, `user_client` fixtures
- `test_routes.py` — respx mocking pattern for operator API calls
- `main.css` — ~26KB CSS with `.card`, `.status-*`, grid, table classes

**Code review patterns across stories 1-1 through 1-6:**
- Reviews consistently find 5 issues
- Common Python issues: dead variables, missing type annotations, weak test assertions
- Ensure all functions have return type annotations
- Use exact assertions in tests (not ranges)

### Project Structure Notes

- `slo_service.py` follows the httpx-based service pattern from `health_service.py`, NOT the Qdrant-based pattern from `metrics_service.py`
- `slo.py` blueprint is the 7th route module (after health, investigations, knowledge, metrics, sources, spending)
- Templates go in `slo/` subdirectory matching existing pattern (metrics/, spending/, health/, etc.)
- Tests follow existing `test_*.py` naming in `ui/tests/`
- CSS additions go at the end of `main.css` in a clearly commented SLO section

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Component Architecture] — slo.py, slo_service.py, templates/slo/ file locations
- [Source: _bmad-output/planning-artifacts/architecture.md#FR to Structure Mapping] — FR6 mapping
- [Source: _bmad-output/planning-artifacts/architecture.md#API Endpoints] — SLO API endpoints
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.7] — Acceptance criteria and user story
- [Source: _bmad-output/planning-artifacts/prd.md#FR6] — SLO compliance, burn rate trends, error budgets on dashboard
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#SLO Dashboard] — SLO views: dashboard.html, service.html
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Color System] — Status colors: healthy (green), warning (amber), critical (red)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Navigation] — Sidebar nav, route organization
- [Source: ui/beeper_ui/services/health_service.py] — httpx service pattern
- [Source: ui/beeper_ui/routes/metrics.py] — Blueprint + HTMX partial pattern
- [Source: ui/beeper_ui/routes/__init__.py] — Blueprint registration pattern
- [Source: ui/beeper_ui/templates/base.html] — Base template, navigation links
- [Source: ui/beeper_ui/static/css/main.css] — CSS classes for cards, status, grids
- [Source: ui/tests/conftest.py] — Test fixtures (app, client, admin_client, user_client)
- [Source: ui/tests/test_routes.py] — respx mocking pattern
- [Source: operator/src/api.rs] — API response structs and endpoint handlers

### Git Intelligence

- Recent commits: `8306665` (1-6 done), `b3807b7` (implement 1-6), `a8bc9b6` (1-5 done), `7ec0d58` (implement 1-5)
- All story implementations follow: create service → create routes → create templates → write tests → register blueprint
- This is the first UI-only story in v0.2.0 — all previous stories were Rust operator code
- UI has 657 existing tests — regression guard is critical

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Implemented `SloService` in `slo_service.py` with httpx client (matching HealthService pattern), 3 API methods, `SloServiceError` exception class, and 5 format helpers
- Created `slo_bp` Flask blueprint in `slo.py` with `/slo/` dashboard route and `/slo/services/<name>` detail route, both with HTMX partial support and error handling
- Registered blueprint in `routes/__init__.py`, added SLO nav link to `base.html`, registered format helpers as Jinja2 globals in `app.py`
- Created 3 Jinja2 templates: `dashboard.html` (full page), `_content.html` (HTMX partial with summary cards + services table + empty/error states), `service.html` (detail page with config, budget bar, triggered policies)
- Added SLO-specific CSS to `main.css`: summary cards grid, services table, budget progress bar (green/amber/red), frozen badge
- 42 new tests: 31 service unit tests (7 API, 12 format helpers, 5 condition mapping, 7 projected exhaustion) + 11 route integration tests (dashboard, HTMX, empty, error, detail, 404, budget, config, access control, navigation)
- All 699 UI tests pass (657 existing + 42 new), all 482 investigator tests pass (3 skipped). Ruff clean, mypy clean on new files.

### File List

**New files:**
- `ui/beeper_ui/services/slo_service.py` — SloService class, SloServiceError, format_compliance, format_burn_rate, format_budget_remaining, format_projected_exhaustion, condition_css_class
- `ui/beeper_ui/routes/slo.py` — slo_bp blueprint, slo_dashboard, slo_service_detail, _build_dashboard_data
- `ui/beeper_ui/templates/slo/dashboard.html` — Full SLO dashboard page
- `ui/beeper_ui/templates/slo/_content.html` — HTMX partial (summary cards, services table, empty/error states)
- `ui/beeper_ui/templates/slo/service.html` — Service detail page (config, budget, policies, placeholder investigations)
- `ui/tests/test_slo_service.py` — 31 unit tests for SloService and format helpers
- `ui/tests/test_slo_routes.py` — 11 route integration tests

**Modified files:**
- `ui/beeper_ui/routes/__init__.py` — Added slo_bp import and registration
- `ui/beeper_ui/app.py` — Registered SLO format helpers as Jinja2 globals
- `ui/beeper_ui/templates/base.html` — Added SLO nav link
- `ui/beeper_ui/static/css/main.css` — Added SLO-specific CSS styles (summary cards, table, budget bar, frozen badge)
