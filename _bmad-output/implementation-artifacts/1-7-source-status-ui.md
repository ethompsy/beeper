# Story 1.7: Source Status UI

Status: done

## Story

As an **Admin**,
I want to view the status of all configured data sources,
So that I can verify Beeper is receiving data and troubleshoot issues.

## Acceptance Criteria

### AC1: Sources List Display
**Given** sources are configured (Source CRDs exist in cluster)
**When** I navigate to the Sources page in the UI
**Then** I see a list of all configured sources (FR28)
**And** each source shows: name, type (prometheus/loki), endpoint URL, connection status
**And** sources are sorted by name alphabetically

### AC2: Source Error Display
**Given** a source has configuration errors (invalid endpoint, auth failure, etc.)
**When** I view the Sources page
**Then** the source shows amber/red status indicator (FR29)
**And** error details are displayed with the specific error message
**And** the error message is actionable (e.g., "Missing metric labels for service discovery", "Connection refused: check endpoint URL")

### AC3: Operator Health Status
**Given** the operator health endpoint exists
**When** I view the operator status section
**Then** I see Beeper's operational health (FR40)
**And** component status is visible: operator running, Qdrant connected, ingestion buffer stats
**And** unhealthy components are highlighted

## Tasks / Subtasks

- [x] Task 1: Create Flask UI project scaffold (AC: #1, #2, #3)
  - [x] 1.1: Create `ui/` directory with `pyproject.toml` (Flask, httpx, pytest dependencies)
  - [x] 1.2: Create `ui/beeper_ui/__init__.py` and `ui/beeper_ui/app.py` (Flask app factory pattern)
  - [x] 1.3: Create `ui/beeper_ui/config.py` with environment-based configuration (OPERATOR_URL, K8S_API_URL)
  - [x] 1.4: Add `.env.example` with configuration variables
  - [x] 1.5: Verify `poetry install` works and Flask runs with hello-world route

- [x] Task 2: Create base templates and HTMX setup (AC: #1, #2, #3)
  - [x] 2.1: Create `ui/beeper_ui/templates/base.html` with HTML5 boilerplate and HTMX include
  - [x] 2.2: Create `ui/beeper_ui/static/css/main.css` with minimal CSS (status colors: green/amber/red)
  - [x] 2.3: Download HTMX to `ui/beeper_ui/static/js/htmx.min.js` (or use CDN)
  - [x] 2.4: Create navigation partial with "Sources" and "Health" links
  - [x] 2.5: Add route for static file serving

- [x] Task 3: Implement Source status service (AC: #1, #2)
  - [x] 3.1: Create `ui/beeper_ui/services/__init__.py` and `ui/beeper_ui/services/source_service.py`
  - [x] 3.2: Implement `SourceService` class that fetches Source CRs from operator API
  - [x] 3.3: Map Source CR status fields to UI-friendly structure (name, type, endpoint, status, error)
  - [x] 3.4: Handle connection errors gracefully (show "Unable to fetch sources" message)
  - [x] 3.5: Add unit tests for service with mocked HTTP responses

- [x] Task 4: Implement Sources list route and template (AC: #1, #2)
  - [x] 4.1: Create `ui/beeper_ui/routes/__init__.py` and `ui/beeper_ui/routes/sources.py`
  - [x] 4.2: Implement `GET /sources` route that fetches sources and renders template
  - [x] 4.3: Create `ui/beeper_ui/templates/sources/list.html` with source table
  - [x] 4.4: Add status indicator styling (green circle = connected, amber = warning, red = error)
  - [x] 4.5: Add expandable error details for sources with errors
  - [x] 4.6: Add HTMX polling (`hx-get`, `hx-trigger="every 5s"`) for auto-refresh

- [x] Task 5: Implement Operator health service (AC: #3)
  - [x] 5.1: Create `ui/beeper_ui/services/health_service.py`
  - [x] 5.2: Implement `HealthService` class that fetches from operator `/api/v1/health/components` endpoint
  - [x] 5.3: Parse health response to extract component statuses (operator, kubernetes, ingestion)
  - [x] 5.4: Add unit tests for health service

- [x] Task 6: Implement Health status route and template (AC: #3)
  - [x] 6.1: Create `ui/beeper_ui/routes/health.py` with `GET /health` route
  - [x] 6.2: Create `ui/beeper_ui/templates/health/status.html` showing component cards
  - [x] 6.3: Display ingestion buffer stats (buffered count, dropped count) from operator metrics
  - [x] 6.4: Add HTMX polling for auto-refresh
  - [x] 6.5: Style unhealthy components with red background/border

- [x] Task 7: Expose operator API for UI consumption (AC: #1, #2, #3)
  - [x] 7.1: Add `GET /api/v1/sources` endpoint to operator health server (returns Source CRs as JSON)
  - [x] 7.2: Add `GET /api/v1/health/components` endpoint with detailed component status
  - [x] 7.3: Add `GET /api/v1/ingestion/stats` endpoint for buffer statistics
  - [x] 7.4: Ensure all endpoints use `snake_case` JSON and RFC 7807 errors
  - [x] 7.5: Add integration tests for new operator endpoints

- [x] Task 8: Add UI integration tests (AC: #1, #2, #3)
  - [x] 8.1: Create `ui/tests/__init__.py` and `ui/tests/conftest.py` with Flask test client fixture
  - [x] 8.2: Test sources list page renders with mock data
  - [x] 8.3: Test error status displays correctly
  - [x] 8.4: Test health page shows component status
  - [x] 8.5: Run `pytest` to verify all tests pass

- [x] Task 9: Documentation and CI setup (AC: #1, #2, #3)
  - [x] 9.1: Create `ui/Dockerfile` for containerized deployment
  - [x] 9.2: Add UI job to `.github/workflows/ci.yml` (lint, test, build)
  - [x] 9.3: Update README with UI development instructions
  - [x] 9.4: Run `poetry run pytest` and `poetry run ruff check` to verify passing

## Dev Notes

### Architecture Compliance

**Source:** [architecture.md - Technology Stack Decisions]

This is the **first UI story** introducing the Flask + HTMX stack:
- **Flask**: Python web framework with app factory pattern
- **HTMX**: Dynamic updates without JavaScript complexity
- **SSE**: Not needed for this story (polling is acceptable for source status)
- **Jinja2**: Template engine (Flask default)

**Source:** [architecture.md - Naming Patterns]

Key conventions to follow:
- API endpoints: `snake_case` query params, plural nouns for resources
- JSON fields: `snake_case` everywhere
- Error responses: RFC 7807 Problem Details format
- File naming: `snake_case.py` for Python files

**Source:** [architecture.md - Project Structure]

UI file structure:
```
ui/
├── pyproject.toml
├── Dockerfile
├── beeper_ui/
│   ├── __init__.py
│   ├── app.py              # Flask app factory
│   ├── config.py           # Configuration from env vars
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── sources.py      # FR28, FR29: Source status views
│   │   └── health.py       # FR40: Operator health views
│   ├── services/
│   │   ├── __init__.py
│   │   ├── source_service.py
│   │   └── health_service.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── sources/
│   │   │   └── list.html
│   │   └── health/
│   │       └── status.html
│   └── static/
│       ├── css/
│       │   └── main.css
│       └── js/
│           └── htmx.min.js
└── tests/
    ├── __init__.py
    ├── conftest.py
    └── test_routes.py
```

### Previous Story Learnings (1-6)

**Source:** [1-6-streaming-data-ingestion.md - Dev Agent Record]

Key patterns to reuse:
- Environment variable configuration with defaults (e.g., `BEEPER_UI_PORT`)
- Separate server approach (UI is its own service, not merged with operator)
- Integration tests using test clients
- Content-type validation for API requests

**Code Review Fixes to Avoid:**
1. Match task descriptions to actual implementation
2. Create tests for all claimed functionality
3. Document environment variables if they exist in code
4. Validate content-types for API endpoints

### Operator API Requirements

The UI needs to fetch data from the operator. New endpoints required:

**GET /api/v1/sources**
Returns list of Source CRs with their status:
```json
{
  "sources": [
    {
      "name": "prometheus-main",
      "type": "prometheus",
      "endpoint": "http://prometheus:9090",
      "status": "connected",
      "last_check": "2026-02-10T12:00:00Z",
      "error": null
    },
    {
      "name": "loki-prod",
      "type": "loki",
      "endpoint": "http://loki:3100",
      "status": "error",
      "last_check": "2026-02-10T12:00:00Z",
      "error": {
        "type": "connection_refused",
        "message": "Connection refused: check endpoint URL",
        "details": "dial tcp 10.0.0.5:3100: connect: connection refused"
      }
    }
  ]
}
```

**GET /api/v1/health/components**
Returns detailed component health:
```json
{
  "components": {
    "operator": {"status": "healthy", "message": "Running"},
    "qdrant": {"status": "healthy", "message": "Connected"},
    "ingestion": {"status": "healthy", "message": "Buffer: 150/10000"}
  },
  "overall": "healthy"
}
```

**GET /api/v1/ingestion/stats**
Returns ingestion buffer statistics:
```json
{
  "buffer_size": 10000,
  "buffered_count": 150,
  "dropped_count": 0,
  "is_full": false
}
```

### Status Indicator Colors

| Status | Color | CSS Class | Description |
|--------|-------|-----------|-------------|
| connected/healthy | Green (#22c55e) | `.status-ok` | Source is working normally |
| warning | Amber (#f59e0b) | `.status-warning` | Degraded but functional |
| error/unhealthy | Red (#ef4444) | `.status-error` | Not working, action required |
| unknown | Gray (#6b7280) | `.status-unknown` | Unable to determine status |

### HTMX Patterns

For auto-refresh without full page reload:
```html
<div hx-get="/sources"
     hx-trigger="every 5s"
     hx-swap="innerHTML">
  <!-- sources list content -->
</div>
```

For expandable error details:
```html
<button hx-get="/sources/{{ source.name }}/error"
        hx-target="#error-{{ source.name }}"
        hx-swap="innerHTML">
  Show Error Details
</button>
<div id="error-{{ source.name }}"></div>
```

### Testing Strategy

**Unit Tests:**
- Mock HTTP responses for source/health services
- Test template rendering with different data states
- Test error handling when operator is unavailable

**Integration Tests:**
- Flask test client for route testing
- Mock operator API responses
- Test HTMX partial responses

### Dependencies to Add

`ui/pyproject.toml`:
```toml
[tool.poetry.dependencies]
python = "^3.11"
flask = "^3.0"
httpx = "^0.27"
python-dotenv = "^1.0"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-flask = "^1.3"
ruff = "^0.5"
respx = "^0.21"  # For mocking httpx
```

### Project Structure Notes

- UI is a separate deployable (not merged with operator or investigator)
- Flask app uses factory pattern for testability
- Services layer abstracts HTTP calls to operator
- Routes handle request/response, services handle business logic

### References

- [Source: architecture.md#Frontend Approach]
- [Source: architecture.md#Project Source Tree]
- [Source: architecture.md#Naming Patterns]
- [Source: epics.md#Story 1.7: Source Status UI]
- [Source: 1-6-streaming-data-ingestion.md#Dev Agent Record]
- [Flask Documentation](https://flask.palletsprojects.com/)
- [HTMX Documentation](https://htmx.org/)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- UI tests: 31 passing (7 app tests, 10 route integration tests, 14 service unit tests)
- Operator tests: 97 passing (including 9 new API module tests)
- Clippy: Clean, no warnings
- Ruff: All checks passed

### Completion Notes List

1. Extended existing UI scaffold from Story 1.1 with Flask app factory pattern
2. Created config.py with environment-based configuration (OPERATOR_URL, OPERATOR_TIMEOUT)
3. Created SourceService and HealthService classes using httpx for API calls
4. Created sources and health routes with HTMX polling support for auto-refresh
5. Created operator API module (`operator/src/api.rs`) with three endpoints:
   - GET /api/v1/sources - Lists Source CRs with status
   - GET /api/v1/health/components - Component health status
   - GET /api/v1/ingestion/stats - Ingestion buffer statistics
6. All API endpoints use snake_case JSON and RFC 7807 Problem Details for errors
7. Added comprehensive tests: 29 UI tests, 9 operator API tests
8. Updated README with UI development instructions and API documentation

### File List

| File | Action | Description |
|------|--------|-------------|
| `ui/pyproject.toml` | Modified | Added httpx, python-dotenv, pytest-flask, respx dependencies |
| `ui/.env.example` | Created | Environment variable configuration template |
| `ui/beeper_ui/app.py` | Modified | Refactored to Flask app factory pattern |
| `ui/beeper_ui/config.py` | Created | Environment-based configuration classes |
| `ui/beeper_ui/routes/__init__.py` | Created | Blueprint registration |
| `ui/beeper_ui/routes/sources.py` | Created | Sources list route with HTMX support |
| `ui/beeper_ui/routes/health.py` | Created | Health status route with HTMX support |
| `ui/beeper_ui/services/__init__.py` | Created | Service exports |
| `ui/beeper_ui/services/source_service.py` | Created | SourceService with httpx client |
| `ui/beeper_ui/services/health_service.py` | Created | HealthService with httpx client |
| `ui/beeper_ui/templates/base.html` | Modified | Added navigation, linked CSS |
| `ui/beeper_ui/templates/sources/list.html` | Created | Sources list page template |
| `ui/beeper_ui/templates/sources/_list_content.html` | Created | Sources partial for HTMX |
| `ui/beeper_ui/templates/health/status.html` | Created | Health status page template |
| `ui/beeper_ui/templates/health/_status_content.html` | Created | Health partial for HTMX |
| `ui/beeper_ui/static/css/main.css` | Created | Status colors, health cards, table styling |
| `ui/tests/conftest.py` | Created | Flask test client fixture |
| `ui/tests/test_app.py` | Modified | Updated for app factory |
| `ui/tests/test_services.py` | Created | Unit tests for services (14 tests) |
| `ui/tests/test_routes.py` | Created | Integration tests for routes (10 tests) |
| `operator/src/api.rs` | Created | API endpoints for UI consumption |
| `operator/src/lib.rs` | Modified | Export api module |
| `operator/src/main.rs` | Modified | Merged API router with health server |
| `README.md` | Modified | Added UI development section and API docs |

## Code Review Record

### Review Agent Model

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Issues Found and Fixed

| Severity | Issue | Fix Applied |
|----------|-------|-------------|
| HIGH | Hardcoded SECRET_KEY with weak default in config.py | Changed to use `secrets.token_hex(32)` for dev, ProductionConfig now raises error if SECRET_KEY not set |
| HIGH | test_app.py tests didn't mock operator API (gave false confidence) | Added proper respx mocks, renamed tests to clarify behavior |
| MEDIUM | ProductionConfig didn't enforce SECRET_KEY | Added `__init__` validation that raises ValueError if SECRET_KEY env var not set |
| MEDIUM | httpx Client created on every request (no connection pooling) | Refactored services to use lazy-initialized client property with connection reuse |
| MEDIUM | Status color indicators not accessible to colorblind users | Added `role="img"` and `aria-label` attributes to status indicators |
| LOW | Unused qdrant-client dependency in pyproject.toml | Not fixed (future story dependency) |
| LOW | operator/examples/ directory not documented in File List | Not fixed (from previous story 1-6) |

### Files Modified During Review

| File | Change |
|------|--------|
| `ui/beeper_ui/config.py` | Secure SECRET_KEY handling, ProductionConfig validation |
| `ui/beeper_ui/services/source_service.py` | Lazy client initialization with connection pooling |
| `ui/beeper_ui/services/health_service.py` | Lazy client initialization with connection pooling |
| `ui/beeper_ui/templates/sources/_list_content.html` | Added ARIA attributes for accessibility |
| `ui/beeper_ui/templates/health/_status_content.html` | Added ARIA attributes for accessibility |
| `ui/tests/test_app.py` | Added proper operator API mocks, 2 new tests |

### Notes for Future Stories

- CSRF protection (Flask-WTF) should be added when forms are introduced (Story 2.5)
- qdrant-client dependency can be removed if not used by Story 2.x

## Change Log

- 2026-02-11: Code review completed - 6 issues fixed (2 HIGH, 3 MEDIUM, 1 LOW skipped), 128 tests passing (97 operator, 31 UI)
- 2026-02-11: Story implementation completed - all 9 tasks implemented, 126 tests passing (97 operator, 29 UI), clippy and ruff clean
