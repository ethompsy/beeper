# Story 7.6: MTTR, Impact & Trust Trend Dashboards

Status: done

## Story

As a **user**,
I want to view MTTR trends, customer impact trends, and trust progression dashboards,
so that I can measure whether Beeper is making operations better over time.

## Acceptance Criteria

1. **Given** a user navigates to the analytics dashboard (`/analytics`), **When** the page loads, **Then** three dashboard sections are displayed: MTTR trends, customer impact trends, and trust level progression **And** the page responds within 2 seconds (NFR2).

2. **Given** the MTTR trends section, **When** the user views the chart, **Then** MTTR is plotted over time (weekly aggregation) for all services or filtered by service **And** the trend line shows improvement or degradation with percentage change.

3. **Given** the trust progression section, **When** the user views trust level changes, **Then** a timeline shows when services moved between trust levels (TL1→TL2, TL2→TL3, etc.) **And** the dashboard shows the distribution of services across trust levels.

## Tasks / Subtasks

- [x] Task 1: Create `AnalyticsService` in `ui/beeper_ui/services/analytics_service.py` (AC: #1, #2, #3)
  - [x] 1.1 Create `AnalyticsService` class with lazy-init `InvestigationService`, `SloService`, and `httpx.Client` (for trust API) — follow `ServiceHealthService` pattern
  - [x] 1.2 Add `compute_mttr_trends(investigations, num_weeks=12)` standalone function: group resolved investigations by ISO week, compute avg MTTR per week in hours, return list of `{"week": "2026-W12", "avg_mttr_hours": float, "count": int}` sorted chronologically
  - [x] 1.3 Add `compute_mttr_trends_by_service(investigations, num_weeks=12)` standalone function: same as 1.2 but returns `{"service": str, "weeks": [...]}` per service
  - [x] 1.4 Add `compute_impact_trends(slo_services, investigations, num_weeks=12)` standalone function: for each week, aggregate avg SLO compliance across services and total investigation count; return `[{"week": str, "avg_compliance": float, "investigation_count": int}]`
  - [x] 1.5 Add `compute_trust_distribution(trust_configs)` standalone function: count services at each trust level (TL1-TL5); return `{"levels": {1: int, 2: int, 3: int, 4: int, 5: int}, "total": int}`
  - [x] 1.6 Add `compute_trust_changes(trust_configs)` standalone function: filter configs where `previous_level` is not None, sort by `updated_at` desc; return list of `{"service": str, "from_level": int, "to_level": int, "updated_at": str, "reason": str|None}`
  - [x] 1.7 Add `get_dashboard_data(period_weeks=12, service_filter=None)` method: orchestrate fetching from all services, call compute functions, return unified dict with all three dashboard sections
  - [x] 1.8 Add `compute_mttr_change_pct(trends)` standalone function: compare most recent week's avg MTTR vs oldest week's avg MTTR; return percentage change (negative = improvement)

- [x] Task 2: Create analytics routes in `ui/beeper_ui/routes/analytics.py` (AC: #1)
  - [x] 2.1 Create `analytics_bp` Blueprint with `url_prefix="/analytics"`
  - [x] 2.2 Add `_get_analytics_service()` factory function (same pattern as services routes)
  - [x] 2.3 Add `GET /analytics/` route: fetch dashboard data, render `analytics/dashboard.html`; HTMX requests render `analytics/_dashboard_content.html`
  - [x] 2.4 Add `service_filter` query param support: `?service=<name>` filters MTTR and impact data to single service
  - [x] 2.5 Add `period` query param support: `?period=4` (4 weeks), `?period=12` (default), `?period=26` (6 months)

- [x] Task 3: Register blueprint in `ui/beeper_ui/routes/__init__.py` (AC: #1)
  - [x] 3.1 Import `analytics_bp` from `beeper_ui.routes.analytics`
  - [x] 3.2 Register `analytics_bp` with the Flask app

- [x] Task 4: Create templates in `ui/beeper_ui/templates/analytics/` (AC: #1, #2, #3)
  - [x] 4.1 Create `dashboard.html` extending `base.html` with breadcrumb, title, and `#analytics-wrapper` div
  - [x] 4.2 Create `_dashboard_content.html` with three sections: MTTR Trends, Customer Impact Trends, Trust Progression
  - [x] 4.3 MTTR Trends section: CSS horizontal bar chart showing weekly MTTR averages, percentage change badge (green = improvement, red = degradation), HTMX service filter dropdown
  - [x] 4.4 Customer Impact section: weekly investigation count bars + avg SLO compliance line representation using CSS bars, trend indicator
  - [x] 4.5 Trust Progression section: stacked horizontal bar showing distribution across TL1-TL5 (with counts and percentages), recent trust changes timeline list with `"ServiceName: TL{from} → TL{to}"` entries sorted by date
  - [x] 4.6 Add ARIA landmarks: `role="region"` with `aria-label` on each dashboard section
  - [x] 4.7 Add HTMX filter controls: period selector buttons (4w/12w/26w), service filter dropdown; target `#analytics-wrapper`

- [x] Task 5: Add CSS styles in `ui/beeper_ui/static/css/main.css` (AC: #1, #2, #3)
  - [x] 5.1 Add `.analytics-dashboard` layout with `.analytics-section` cards
  - [x] 5.2 Add `.analytics-bar-chart` CSS-only horizontal bar chart (bars are `<div>` elements with percentage-based widths)
  - [x] 5.3 Add `.mttr-change-badge` styles: green for improvement (negative %), red for degradation
  - [x] 5.4 Add `.trust-distribution-bar` stacked bar with TL1-TL5 color segments
  - [x] 5.5 Add `.trust-change-timeline` list styles with arrow indicators
  - [x] 5.6 Add `.analytics-filter-bar` styles matching existing `service-health-filter-bar` pattern
  - [x] 5.7 Add responsive styles with `max-width: calc(100% - 32px)` constraint

- [x] Task 6: Add command palette and navigation (AC: #1)
  - [x] 6.1 Add "Analytics Dashboard" command to `COMMANDS` in `command-palette.js` with `href: "/analytics/"`, category "navigation", keywords `["analytics", "mttr", "trend", "dashboard", "impact", "trust"]`, shortcut `"g a"`
  - [x] 6.2 Add `a: "/analytics/"` to `CHORD_SHORTCUTS` in `command-palette.js`
  - [x] 6.3 Add `<a href="/analytics/">Analytics</a>` to navigation in `base.html`

- [x] Task 7: Write comprehensive tests in `ui/tests/test_analytics_dashboard.py` (AC: #1, #2, #3)
  - [x] 7.1 Test `compute_mttr_trends()`: empty investigations, single week, multiple weeks, only counts completed investigations with both timestamps
  - [x] 7.2 Test `compute_mttr_trends_by_service()`: groups by service correctly, handles missing services
  - [x] 7.3 Test `compute_impact_trends()`: aggregates SLO compliance and investigation counts by week
  - [x] 7.4 Test `compute_trust_distribution()`: all at TL1, mixed distribution, empty
  - [x] 7.5 Test `compute_trust_changes()`: filters to configs with previous_level, sorts by updated_at desc
  - [x] 7.6 Test `compute_mttr_change_pct()`: improvement, degradation, no data, single week
  - [x] 7.7 Test `get_dashboard_data()` integration with mocked services
  - [x] 7.8 Test `GET /analytics/` route: returns 200, contains all three sections
  - [x] 7.9 Test HTMX request returns partial `_dashboard_content.html`
  - [x] 7.10 Test service filter: `?service=api-gateway` filters MTTR/impact data
  - [x] 7.11 Test period filter: `?period=4` limits to 4 weeks
  - [x] 7.12 Test template renders MTTR bar chart with correct week labels
  - [x] 7.13 Test template renders trust distribution with TL counts
  - [x] 7.14 Test template renders trust change timeline entries
  - [x] 7.15 Test MTTR change badge shows percentage
  - [x] 7.16 Test ARIA attributes on dashboard sections
  - [x] 7.17 Test command palette has analytics command with correct attributes
  - [x] 7.18 Test navigation link exists in base template

- [x] Task 8: Run full test suite across all components
  - [x] 8.1 Run investigator pytest + ruff + mypy
  - [x] 8.2 Run UI pytest
  - [x] 8.3 Run operator cargo test
  - [x] 8.4 Verify no regressions from existing tests

## Dev Notes

### Architecture Patterns (MUST FOLLOW)

- **Service layer:** Create NEW `AnalyticsService` in `ui/beeper_ui/services/analytics_service.py` — analytics is a separate aggregation concern from service health. Follow `ServiceHealthService` pattern: lazy-init dependencies, `close()` method, factory function in routes.
- **Standalone compute functions:** `compute_mttr_trends()`, `compute_impact_trends()`, `compute_trust_distribution()`, `compute_trust_changes()` should be module-level standalone functions (not methods) — same pattern as `compute_reliability_score()` and `compute_health_status()`.
- **Route layer:** Create NEW `analytics_bp` Blueprint in `ui/beeper_ui/routes/analytics.py` — separate from services routes. Follow same patterns: `_get_analytics_service()` factory, try/except with close() in finally, HTMX detection via `request.headers.get("HX-Request")`.
- **Template layer:** Create NEW `ui/beeper_ui/templates/analytics/` directory with `dashboard.html` + `_dashboard_content.html`.
- **CSS:** Append to `ui/beeper_ui/static/css/main.css`.
- **HTMX pattern:** Filter buttons use `hx-get="/analytics/?period=X&service=Y"`, `hx-target="#analytics-wrapper"`, `hx-swap="innerHTML"`.
- **No JavaScript charting libraries.** The project uses CSS-only visualizations. Use `<div>` elements with percentage-based `width` for bar charts, matching the `reliability-factor-bar` pattern.

### Data Sources (Already Available)

1. **MTTR data:** `InvestigationService.list_investigations()` → filter to `status == "completed"` with both `started_at` and `completed_at` timestamps. Parse ISO 8601 timestamps, compute `completed_at - started_at` in hours. Group by ISO week using `datetime.isocalendar()`.

2. **Impact data:** `SloService.get_services()` → `compliance` float (0.0-1.0) per service. `InvestigationService.list_investigations()` → count and severity distribution per week.

3. **Trust progression:** `ServiceHealthService._get_trust_levels()` fetches from `GET /api/v1/trust/services`. Each item includes `trust_level`, `previous_level`, `updated_at`, `reason`. For distribution: count services per TL1-TL5. For timeline: filter where `previous_level is not None`, sort by `updated_at` desc.

### Computation Details

```python
# MTTR Weekly Aggregation
def compute_mttr_trends(investigations, num_weeks=12):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(weeks=num_weeks)
    resolved = [inv for inv in investigations
                if inv.status == "completed" and inv.started_at and inv.completed_at]

    weeks: dict[str, list[float]] = {}
    for inv in resolved:
        started = _parse_dt(inv.started_at)
        completed = _parse_dt(inv.completed_at)
        if started and completed and started >= cutoff and completed > started:
            iso_year, iso_week, _ = started.isocalendar()
            week_key = f"{iso_year}-W{iso_week:02d}"
            hours = (completed - started).total_seconds() / 3600
            weeks.setdefault(week_key, []).append(hours)

    return sorted([
        {"week": k, "avg_mttr_hours": round(sum(v)/len(v), 1), "count": len(v)}
        for k, v in weeks.items()
    ], key=lambda x: x["week"])

# MTTR Change Percentage
def compute_mttr_change_pct(trends):
    if len(trends) < 2:
        return None
    oldest = trends[0]["avg_mttr_hours"]
    newest = trends[-1]["avg_mttr_hours"]
    if oldest == 0:
        return None
    return round((newest - oldest) / oldest * 100, 1)
    # Negative = improvement (MTTR decreased)

# Trust Distribution
def compute_trust_distribution(trust_configs):
    levels = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for cfg in trust_configs:
        tl = cfg.get("trust_level", 1)
        if tl in levels:
            levels[tl] += 1
    return {"levels": levels, "total": sum(levels.values())}
```

### ARIA Accessibility Requirements

- Each dashboard section: `<section role="region" aria-label="MTTR Trends">`
- Bar chart bars: `aria-label="Week 2026-W12: 2.5 hours average MTTR"`
- Trust distribution: `aria-label="Trust level distribution"`
- Change badge: `aria-label="MTTR improved by 15.3%"`

### Previous Story Intelligence (from 7-5)

- `compute_reliability_score()` in `service_health_service.py` already computes MTTR components — reuse `_parse_dt()` helper pattern for timestamp parsing
- `ServiceHealthService` uses lazy-initialized `SloService` and `InvestigationService` properties — follow same pattern in `AnalyticsService`
- Service name validation: `^[a-zA-Z0-9_-]+$` regex + `len(name) > 100` — apply to service filter param
- HTMX filter/sort buttons must preserve each other's state (learned from 7-5 code review: filter buttons include sort param and vice versa)
- Tests: use `app.test_client()` with mocked `httpx.Client` responses via `unittest.mock.patch`
- Code review 7-5 found HTMX filter/sort state not being preserved — preventively include all active params in every HTMX button

### Trust Level Service Data Shape

The trust API (`GET /api/v1/trust/services` proxied through `ServiceHealthService._get_trust_levels()`) returns:
```json
[
  {
    "service_name": "api-gateway",
    "trust_level": 3,
    "trust_level_name": "Act with Approval",
    "trust_level_description": "...",
    "updated_by": "admin",
    "updated_at": "2026-03-10T14:30:00+00:00",
    "reason": "Promoted after 30 days stable",
    "previous_level": 2
  }
]
```
For trust changes timeline: filter items where `previous_level is not None`.
For distribution: count items by `trust_level`.

### Project Structure Notes

- All UI services in `ui/beeper_ui/services/`
- All UI routes in `ui/beeper_ui/routes/`
- All templates in `ui/beeper_ui/templates/` (one subdirectory per route blueprint)
- CSS in `ui/beeper_ui/static/css/main.css`
- JS in `ui/beeper_ui/static/js/`
- Tests in `ui/tests/`
- No operator changes needed — all data available through existing APIs
- Blueprint registration in `ui/beeper_ui/routes/__init__.py`

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 7 Story 7.6]
- [Source: ui/beeper_ui/services/service_health_service.py] — pattern reference for aggregation service
- [Source: ui/beeper_ui/services/investigation_service.py] — MTTR data source
- [Source: ui/beeper_ui/services/slo_service.py] — SLO compliance data source
- [Source: ui/beeper_ui/services/trust_level_service.py] — trust level data, TrustLevelConfig with previous_level
- [Source: ui/beeper_ui/routes/services.py] — pattern reference for routes
- [Source: ui/beeper_ui/routes/trust_config.py] — trust API response shape
- [Source: ui/beeper_ui/templates/services/_detail_content.html] — CSS bar chart pattern (reliability-factor-bar)
- [Source: ui/beeper_ui/templates/services/_list_content.html] — HTMX filter/sort button pattern
- [Source: ui/beeper_ui/static/js/command-palette.js] — command palette and chord shortcut registration
- [Source: _bmad-output/implementation-artifacts/7-5-reliability-score-per-service.md] — previous story patterns

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Story created with comprehensive context from Epic 7 acceptance criteria, architecture analysis, and previous story 7-5 learnings
- Created new `AnalyticsService` following `ServiceHealthService` pattern with lazy-init dependencies
- Six standalone compute functions: `compute_mttr_trends()`, `compute_mttr_trends_by_service()`, `compute_mttr_change_pct()`, `compute_impact_trends()`, `compute_trust_distribution()`, `compute_trust_changes()`
- New `analytics_bp` Blueprint with `/analytics/` route, period filter (4w/12w/26w), and service filter with validation
- Added `HTTPException` re-raise pattern (learned from previous code reviews) to prevent `abort()` being swallowed by broad exception handler
- Dashboard template with three sections: MTTR bar chart, Customer Impact bar chart, Trust Level stacked distribution bar + change timeline
- CSS-only visualizations (no JS charting libraries) following existing `reliability-factor-bar` pattern
- HTMX filter buttons preserve all active params (period + service) per 7-5 code review lesson
- Command palette: "Analytics Dashboard" command with `g a` chord shortcut
- Navigation link added to base.html
- 38 new tests covering unit tests, integration, routes, templates, ARIA attributes, command palette
- All 3,531 tests passing (1,013 investigator + 1,980 UI + 538 operator)
- ruff clean, mypy clean (86 files)

### File List

- `ui/beeper_ui/services/analytics_service.py` (created — AnalyticsService + 6 standalone compute functions)
- `ui/beeper_ui/routes/analytics.py` (created — analytics_bp with /analytics/ route, period/service filters)
- `ui/beeper_ui/routes/__init__.py` (modified — registered analytics_bp)
- `ui/beeper_ui/templates/analytics/dashboard.html` (created — extends base.html)
- `ui/beeper_ui/templates/analytics/_dashboard_content.html` (created — 3 dashboard sections with HTMX filters)
- `ui/beeper_ui/static/css/main.css` (modified — analytics dashboard CSS: bar charts, trust distribution, timeline)
- `ui/beeper_ui/static/js/command-palette.js` (modified — added Analytics Dashboard command + g a chord)
- `ui/beeper_ui/templates/base.html` (modified — added Analytics nav link)
- `ui/tests/test_analytics_dashboard.py` (created — 38 tests)
