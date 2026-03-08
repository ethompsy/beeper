# Story 6.1: MTTR Trends Dashboard

Status: ready-for-dev

## Story

As an **SRE Lead**,
I want to view MTTR trends over time,
so that I can measure Beeper's impact and report on reliability improvements.

## Acceptance Criteria

1. **Given** investigations have been resolved, **When** I navigate to the Metrics page, **Then** I see MTTR (Mean Time To Resolution) trends (FR35) **And** the chart shows MTTR over configurable time periods (week, month, quarter).

2. **Given** MTTR data is displayed, **When** I view the dashboard, **Then** I see:
   - Overall MTTR trend line
   - MTTR by service breakdown
   - MTTR by severity level
   - Comparison to baseline (pre-Beeper if available)

3. **Given** I want to drill down, **When** I click on a data point, **Then** I see the investigations that contributed to that MTTR **And** I can navigate to individual investigations.

4. **Given** MTTR is improving, **When** viewing the dashboard, **Then** improvement percentage is highlighted **And** I can export data for leadership reports.

5. **Given** specific services have different MTTR, **When** I filter by service, **Then** I see service-specific MTTR trends **And** I can identify services that need attention.

## Tasks / Subtasks

- [ ] Task 1: Create MetricsService for MTTR data aggregation (AC: 1, 2, 5)
  - [ ] 1.1 Create `ui/beeper_ui/services/metrics_service.py` with `MetricsService` class — lazy-init Qdrant client (follow `InvestigationService` pattern)
  - [ ] 1.2 Add `get_mttr_data(time_period: str = "month", service: str | None = None, severity: str | None = None) -> dict` — scrolls Qdrant `investigations` collection, filters for records with `mttr_seconds IS NOT NULL` and `resolution_outcome IN (resolved, not_an_issue, unresolved)`, groups by time bucket (week/month/quarter), returns aggregated MTTR stats
  - [ ] 1.3 Add `get_mttr_by_service() -> list[dict]` — aggregates MTTR per service from investigations collection
  - [ ] 1.4 Add `get_mttr_by_severity() -> list[dict]` — aggregates MTTR per severity level
  - [ ] 1.5 Add `get_investigations_for_period(start_date: str, end_date: str, service: str | None = None) -> list[dict]` — returns resolved investigations for drill-down view
  - [ ] 1.6 Add `export_mttr_data(time_period: str, format: str = "json") -> str | bytes` — exports MTTR data as JSON or CSV

- [ ] Task 2: Create metrics Flask blueprint and routes (AC: 1, 2, 3, 4, 5)
  - [ ] 2.1 Create `ui/beeper_ui/routes/metrics.py` with `metrics_bp = Blueprint("metrics", __name__, url_prefix="/metrics")`
  - [ ] 2.2 Add `GET /metrics/` route — renders MTTR trends dashboard page with default time period (month)
  - [ ] 2.3 Add `GET /metrics/mttr` HTMX partial route — returns `_mttr_content.html` filtered by query params (`period`, `service`, `severity`) for dynamic filtering without full page reload
  - [ ] 2.4 Add `GET /metrics/mttr/drilldown` route — returns `_drilldown.html` partial listing investigations for a specific time bucket
  - [ ] 2.5 Add `GET /metrics/export` route — returns JSON or CSV file download based on `format` query param
  - [ ] 2.6 Register `metrics_bp` in `ui/beeper_ui/routes/__init__.py`

- [ ] Task 3: Create MTTR dashboard templates (AC: 1, 2, 4)
  - [ ] 3.1 Create `ui/beeper_ui/templates/metrics/mttr.html` — extends `base.html`, full page with filter controls and content area
  - [ ] 3.2 Create `ui/beeper_ui/templates/metrics/_mttr_content.html` — HTMX partial containing: summary cards (overall MTTR, trend direction, improvement %), SVG trend chart, service breakdown bars, severity breakdown bars
  - [ ] 3.3 Trend chart: use server-rendered inline `<svg>` with `<polyline>` for MTTR trend line (no JS library — consistent with project's no-JS philosophy)
  - [ ] 3.4 Service/severity breakdowns: use existing CSS horizontal bar pattern from `learning.html` (`.category-bars`, `.category-bar-track`, `.category-bar-fill`)
  - [ ] 3.5 Filter controls: time period selector (week/month/quarter) using `hx-get="/metrics/mttr"` with `hx-target="#mttr-content"` for HTMX filtering; service dropdown; severity dropdown
  - [ ] 3.6 Export button linking to `/metrics/export?period=X&format=json` (and CSV option)
  - [ ] 3.7 Improvement percentage: green badge when MTTR is decreasing, red when increasing

- [ ] Task 4: Create drill-down template (AC: 3)
  - [ ] 4.1 Create `ui/beeper_ui/templates/metrics/_drilldown.html` — HTMX partial showing list of investigations for a clicked time bucket
  - [ ] 4.2 Each investigation row: ID (linked to `/investigations/<id>`), service badge, severity badge, MTTR formatted via `format_mttr()`, resolved_at date
  - [ ] 4.3 Trend chart data points use `hx-get="/metrics/mttr/drilldown?start=X&end=Y"` with `hx-target="#drilldown-panel"` to load investigation list on click

- [ ] Task 5: Add navigation and CSS (AC: 1)
  - [ ] 5.1 Add "Metrics" link to `base.html` nav: `<a href="/metrics/">Metrics</a>` (after "Health")
  - [ ] 5.2 Add CSS to `main.css` for: `.mttr-summary-cards` grid, `.mttr-trend-chart` SVG container, `.mttr-filter-bar` controls, `.improvement-badge` (green/red), `.drilldown-panel` styles, `.export-btn` styles
  - [ ] 5.3 Reuse existing CSS patterns: `.card`, `.category-bars`, `.category-bar-track`, `.category-bar-fill`, `.service-badge`, `.status-badge`, `.mttr-display`

- [ ] Task 6: Tests (AC: 1, 2, 3, 4, 5)
  - [ ] 6.1 Create `ui/tests/test_metrics.py`
  - [ ] 6.2 Test `MetricsService.get_mttr_data()` with mock Qdrant — returns aggregated data
  - [ ] 6.3 Test `MetricsService.get_mttr_data()` with no resolved investigations — returns empty
  - [ ] 6.4 Test `MetricsService.get_mttr_by_service()` groups correctly
  - [ ] 6.5 Test `MetricsService.get_mttr_by_severity()` groups correctly
  - [ ] 6.6 Test `MetricsService.get_investigations_for_period()` returns filtered list
  - [ ] 6.7 Test `MetricsService.export_mttr_data()` returns valid JSON
  - [ ] 6.8 Test `MetricsService.export_mttr_data()` returns valid CSV
  - [ ] 6.9 Test `GET /metrics/` renders full page with HTMX content area
  - [ ] 6.10 Test `GET /metrics/mttr` with HX-Request header returns partial
  - [ ] 6.11 Test `GET /metrics/mttr?period=week` filters by week
  - [ ] 6.12 Test `GET /metrics/mttr?service=api-gateway` filters by service
  - [ ] 6.13 Test `GET /metrics/mttr/drilldown?start=X&end=Y` returns investigation list
  - [ ] 6.14 Test `GET /metrics/export?format=json` returns JSON download
  - [ ] 6.15 Test `GET /metrics/export?format=csv` returns CSV download
  - [ ] 6.16 Test dashboard with Qdrant unavailable — shows error card gracefully
  - [ ] 6.17 Test improvement percentage calculation (positive and negative trends)

- [ ] Task 7: Integration verification (AC: 1, 2, 3, 4, 5)
  - [ ] 7.1 Run `ruff check` on all new/modified Python files — fix any issues
  - [ ] 7.2 Run `mypy` on all new/modified Python files — fix any issues
  - [ ] 7.3 Run full Python test suite — verify zero regressions
  - [ ] 7.4 Verify navigation link appears in base template
  - [ ] 7.5 Verify SVG trend chart renders with mock data (template inspection)

## Dev Notes

### Architecture Decision: Separate MetricsService + metrics Blueprint

Create a new `MetricsService` class (NOT methods on `InvestigationService`) and a new `metrics_bp` blueprint. This follows the architecture doc's planned `metrics.py` route file (`ui/beeper_ui/routes/metrics.py` — FR35). Metrics is a distinct domain from investigation management.

### Data Source: Qdrant `investigations` Collection

MTTR data lives in the Qdrant `investigations` collection payload, stored by story 4-6's resolution flow:

```python
# Per-investigation payload (set by save_resolution_feedback in 4-6)
{
    "investigation_id": "inv-abc123",
    "service": "payment-service",          # from investigation metadata
    "severity": "high",                     # from investigation metadata
    "resolution_outcome": "resolved",       # resolved|not_an_issue|escalated|unresolved
    "resolved_at": "2026-03-07T14:30:00Z", # ISO 8601
    "mttr_seconds": 3420,                   # int | None
}
```

**Query strategy:** Scroll all points in `investigations` collection with filter `mttr_seconds IS NOT NULL`. Group in Python by time bucket. Qdrant does not support aggregation queries — all grouping/averaging must happen server-side.

**Note:** `escalated` outcome does NOT have `mttr_seconds` set (no `completed_at` on CRD). Only `resolved`, `not_an_issue`, `unresolved` have MTTR data.

### Charting Approach: Server-Rendered Inline SVG (No JS Library)

The project has a strict no-JavaScript philosophy (only HTMX + one inline script for resolution form field toggling). For the MTTR trend line:

- **Trend line chart:** Inline `<svg>` with `<polyline>` points computed server-side in Jinja2. Each point represents average MTTR for a time bucket. SVG viewBox scales dynamically.
- **Service/severity breakdowns:** CSS-only horizontal bar charts using existing `.category-bars` / `.category-bar-track` / `.category-bar-fill` pattern from `learning.html`.
- **Drill-down:** HTMX `hx-get` on SVG data point elements (use `<rect>` overlays for click targets) loading `_drilldown.html` partial.

**DO NOT** add Chart.js, D3, or any JS charting library.

### SVG Trend Chart Implementation Pattern

```html
<svg class="mttr-trend-chart" viewBox="0 0 {{ chart_width }} {{ chart_height }}" preserveAspectRatio="none">
  <!-- Grid lines -->
  {% for y in y_grid_lines %}
  <line x1="0" y1="{{ y }}" x2="{{ chart_width }}" y2="{{ y }}" stroke="#e5e7eb" stroke-width="1"/>
  {% endfor %}
  <!-- Trend line -->
  <polyline points="{{ trend_points }}" fill="none" stroke="#6366f1" stroke-width="2"/>
  <!-- Data points with HTMX drill-down -->
  {% for point in data_points %}
  <circle cx="{{ point.x }}" cy="{{ point.y }}" r="4" fill="#6366f1"
          hx-get="/metrics/mttr/drilldown?start={{ point.start }}&end={{ point.end }}"
          hx-target="#drilldown-panel" hx-swap="innerHTML"/>
  {% endfor %}
</svg>
```

### HTMX Filtering Pattern

```html
<!-- Filter bar -->
<div class="mttr-filter-bar">
  <select name="period" hx-get="/metrics/mttr" hx-target="#mttr-content" hx-swap="innerHTML" hx-include="[name='service'],[name='severity']">
    <option value="week">Weekly</option>
    <option value="month" selected>Monthly</option>
    <option value="quarter">Quarterly</option>
  </select>
  <select name="service" hx-get="/metrics/mttr" hx-target="#mttr-content" hx-swap="innerHTML" hx-include="[name='period'],[name='severity']">
    <option value="">All Services</option>
    {% for svc in services %}
    <option value="{{ svc }}">{{ svc }}</option>
    {% endfor %}
  </select>
</div>
<div id="mttr-content">
  {% include "metrics/_mttr_content.html" %}
</div>
<div id="drilldown-panel"></div>
```

### Existing Code to Reuse (DO NOT RECREATE)

| Component | Location | What to Reuse |
|-----------|----------|---------------|
| Qdrant scroll pattern | `investigation_service.py:229-241` | Scroll investigations collection with Filter |
| `format_mttr()` filter | `investigations.py` (Jinja2 filter) | Already registered — reuse in metrics templates |
| CSS horizontal bars | `learning.html:34-60` | `.category-bars`, `.category-bar-track`, `.category-bar-fill` |
| Card layout | `main.css` | `.card` class |
| Service badge | `main.css` | `.service-badge` |
| Error card pattern | `learning.html:16-20` | Error message card when Qdrant unavailable |
| Blueprint registration | `routes/__init__.py` | Follow pattern for `metrics_bp` |
| Flask test client | `ui/tests/` | pytest fixtures from `conftest.py` |
| Qdrant mock pattern | `test_investigation_service.py` | `MagicMock` for Qdrant client |

### Anti-Patterns to Avoid

- **DO NOT** add Chart.js, D3, or any JavaScript charting library — use inline SVG for trend lines
- **DO NOT** add metrics methods to `InvestigationService` — create separate `MetricsService`
- **DO NOT** create new CSS files — add to existing `main.css`
- **DO NOT** use `url_for()` with hardcoded URLs in templates — always use `url_for()`
- **DO NOT** duplicate `format_mttr()` — it's already a registered Jinja2 filter
- **DO NOT** modify the investigator pipeline or resolution flow — metrics are read-only queries
- **DO NOT** create new Qdrant collections — read from existing `investigations` collection
- **DO NOT** use `with_vectors=True` when scrolling — MTTR queries need payload only
- **DO NOT** use async — Flask routes are synchronous
- **DO NOT** use JavaScript for filter interactions — use HTMX `hx-get` with `hx-include`
- **DO NOT** hardcode SVG dimensions — use dynamic viewBox scaling based on data

### Qdrant Query Pattern for Scrolling All Resolved Investigations

```python
from qdrant_client.models import FieldCondition, Filter, MatchAny, IsNotNull

# Filter: has mttr_seconds AND resolved (non-escalated)
scroll_filter = Filter(
    must=[
        FieldCondition(key="mttr_seconds", match=IsNotNull()),  # Note: Qdrant may not support IsNotNull — use MatchExcept or fetch all and filter in Python
    ]
)

# Scroll all matching points
all_points = []
offset = None
while True:
    results, offset = qdrant_client.scroll(
        collection_name="investigations",
        scroll_filter=scroll_filter,
        limit=100,
        offset=offset,
        with_payload=True,
        with_vectors=False,
    )
    all_points.extend(results)
    if offset is None:
        break
```

**Important:** Qdrant's `IsNotNull` filter may not be available in all versions. Safer approach: scroll all points and filter `mttr_seconds is not None` in Python. The investigations collection is small enough for full scrolling.

### Time Bucket Aggregation Logic

```python
from datetime import datetime, timedelta
from collections import defaultdict

def bucket_key(resolved_at: str, period: str) -> str:
    dt = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
    if period == "week":
        # ISO week start (Monday)
        start = dt - timedelta(days=dt.weekday())
        return start.strftime("%Y-W%V")
    elif period == "month":
        return dt.strftime("%Y-%m")
    elif period == "quarter":
        q = (dt.month - 1) // 3 + 1
        return f"{dt.year}-Q{q}"
    return dt.strftime("%Y-%m")

# Group by bucket
buckets = defaultdict(list)
for point in all_points:
    payload = point.payload
    if payload.get("mttr_seconds") is not None and payload.get("resolved_at"):
        key = bucket_key(payload["resolved_at"], period)
        buckets[key].append(payload["mttr_seconds"])

# Calculate averages
trend_data = [
    {"period": key, "avg_mttr": sum(vals) // len(vals), "count": len(vals)}
    for key, vals in sorted(buckets.items())
]
```

### Improvement Percentage Calculation

Compare current period average MTTR to previous period:
```python
if len(trend_data) >= 2:
    current = trend_data[-1]["avg_mttr"]
    previous = trend_data[-2]["avg_mttr"]
    if previous > 0:
        improvement_pct = ((previous - current) / previous) * 100
        # Positive = improving (MTTR decreased), Negative = worsening
```

### Export Format

**JSON export:**
```json
{
  "period": "month",
  "generated_at": "2026-03-07T14:30:00Z",
  "trend": [{"period": "2026-01", "avg_mttr_seconds": 3420, "count": 15}],
  "by_service": [{"service": "api-gateway", "avg_mttr_seconds": 2100, "count": 8}],
  "by_severity": [{"severity": "high", "avg_mttr_seconds": 5400, "count": 5}]
}
```

**CSV export:** Header row + data rows for trend data.

### Testing Standards

- **Framework**: pytest with Flask test client
- **Mocking**: `unittest.mock.MagicMock` for Qdrant client, `unittest.mock.patch` for service instantiation
- **Test file**: `ui/tests/test_metrics.py` (new file)
- **Qdrant mock data**: Create test points with realistic `mttr_seconds`, `resolved_at`, `service`, `severity`, `resolution_outcome` payloads
- **HTMX testing**: Test both full-page (`GET /metrics/`) and partial (`HX-Request: true` header) responses
- **Error cases**: Qdrant unavailable returns graceful error card
- **Pattern**: Follow `ui/tests/test_learning.py` for test structure and mock helpers

### Project Structure Notes

- **New file**: `ui/beeper_ui/services/metrics_service.py` — MetricsService class
- **New file**: `ui/beeper_ui/routes/metrics.py` — metrics_bp Blueprint
- **New directory**: `ui/beeper_ui/templates/metrics/` — dashboard templates
- **New templates**: `mttr.html`, `_mttr_content.html`, `_drilldown.html`
- **Modify**: `ui/beeper_ui/routes/__init__.py` — register metrics_bp
- **Modify**: `ui/beeper_ui/templates/base.html` — add Metrics nav link
- **Modify**: `ui/beeper_ui/static/css/main.css` — add metrics styles
- **New test**: `ui/tests/test_metrics.py`

### Previous Story Intelligence (from 5-4 and 4-6)

**From 4-6 (Investigation Resolution):**
- MTTR stored in `investigations` Qdrant collection via `save_resolution_feedback()`
- `calculate_mttr()` is a static method on `InvestigationService` — DO NOT recreate
- `format_mttr()` registered as Jinja2 filter — reuse in templates
- Qdrant scroll pattern with `Filter(must=[FieldCondition(...)])` — reuse exact pattern
- Resolution outcomes: `resolved`, `not_an_issue`, `unresolved` have MTTR; `escalated` does NOT

**From 5-4 (Graduated Trust):**
- Trust settings page pattern: full-page with cards, bars, badges — reuse layout approach
- CSS horizontal bar pattern (`.category-bars`) works well for per-service breakdowns
- Non-blocking service calls with try/except for Qdrant errors
- Code review findings: sanitize error messages, validate inputs, log swallowed exceptions

**Recent commit pattern:** All commits prefixed with "MAESTRO:" — follow same convention.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 6, Story 6.1]
- [Source: _bmad-output/planning-artifacts/architecture.md#UI Directory Structure — metrics.py route]
- [Source: ui/beeper_ui/services/investigation_service.py:505-548 — save_resolution_feedback, Qdrant schema]
- [Source: ui/beeper_ui/services/investigation_service.py:483-503 — calculate_mttr static method]
- [Source: ui/beeper_ui/routes/investigations.py — format_mttr Jinja2 filter]
- [Source: ui/beeper_ui/templates/knowledge/learning.html:34-60 — CSS bar chart pattern]
- [Source: ui/beeper_ui/templates/knowledge/trust_settings.html — Trust settings page pattern]
- [Source: ui/beeper_ui/templates/base.html:15-19 — Navigation structure]
- [Source: ui/beeper_ui/routes/__init__.py — Blueprint registration pattern]
- [Source: _bmad-output/implementation-artifacts/4-6-investigation-resolution.md — MTTR data flow and schema]
- [Source: _bmad-output/implementation-artifacts/5-4-graduated-authoring-trust.md — UI page patterns, code review lessons]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created
- New MetricsService + metrics Blueprint architecture (separate from InvestigationService)
- Server-rendered inline SVG for trend lines (no JS charting library — project convention)
- CSS horizontal bars for service/severity breakdowns (reuse existing learning.html pattern)
- HTMX filtering with hx-get + hx-include for dynamic period/service/severity selection
- Drill-down via HTMX partial loading on SVG data point click
- JSON and CSV export for leadership reports
- MTTR data from Qdrant investigations collection (set by story 4-6)
- 7 tasks: service, routes, dashboard templates, drill-down, nav+CSS, tests, integration

### Change Log

### File List
