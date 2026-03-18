# Story 7.5: Reliability Score per Service

Status: done

## Story

As the **system**,
I want to calculate a reliability score per service as a composite of SLO compliance, incident frequency, and MTTR,
so that leadership can compare service reliability at a glance.

## Acceptance Criteria

1. **Given** a service with SLO data, investigation history, and resolution timestamps, **When** the reliability score is calculated, **Then** the score (0-100) is a weighted composite: SLO compliance (40%), incident frequency trend (30%), MTTR trend (30%) **And** the score is recalculated on a configurable interval (default: hourly).

2. **Given** the service health page, **When** the reliability score is displayed, **Then** it includes the composite score, a trend indicator (improving/stable/declining), and a breakdown of contributing factors **And** the score uses ARIA meter role for accessibility.

3. **Given** the service list view, **When** sorted by reliability score, **Then** services are ranked from lowest to highest reliability **And** services below a configurable threshold (default: 70) are flagged with a warning indicator.

## Tasks / Subtasks

- [x] Task 1: Add `compute_reliability_score()` function to `ServiceHealthService` (AC: #1)
  - [x] 1.1 Add function that takes SLO compliance (0.0-1.0), investigation list, and lookback window (default: 30 days)
  - [x] 1.2 Compute SLO component (40%): compliance * 100 * 0.4
  - [x] 1.3 Compute incident frequency component (30%): normalize incident count over lookback period (0 incidents = 30, max incidents for 0 = configurable, default: 10)
  - [x] 1.4 Compute MTTR component (30%): normalize mean resolution time (0h = 30, 24h+ = 0, linear interpolation)
  - [x] 1.5 Compute trend indicator by comparing current 7-day window vs previous 7-day window (improving if score increased by >5, declining if decreased by >5, else stable)
  - [x] 1.6 Return `ReliabilityScore` dict with: `score` (int 0-100), `trend` (str), `slo_component` (float), `frequency_component` (float), `mttr_component` (float), `below_threshold` (bool)

- [x] Task 2: Integrate reliability score into `get_service_list()` and `get_service_detail()` (AC: #1, #3)
  - [x] 2.1 Call `compute_reliability_score()` for each service in `get_service_list()`, add `reliability_score` key to service dict
  - [x] 2.2 Call `compute_reliability_score()` in `get_service_detail()`, add `reliability_score` key to detail dict
  - [x] 2.3 Add sort-by-reliability option to `get_service_list()` via `sort_by` parameter (default: health_status, option: reliability)

- [x] Task 3: Add reliability score display to service detail page (AC: #2)
  - [x] 3.1 Add reliability score summary card to `_detail_content.html` with `role="meter"`, `aria-valuemin="0"`, `aria-valuemax="100"`, `aria-valuenow="{{ score }}"`
  - [x] 3.2 Add trend indicator badge (improving: green arrow up, stable: gray dash, declining: red arrow down)
  - [x] 3.3 Add contributing factors breakdown section showing SLO/frequency/MTTR component values with visual bars
  - [x] 3.4 Add warning styling when score is below threshold (default: 70)

- [x] Task 4: Add reliability score to service list view (AC: #3)
  - [x] 4.1 Add reliability score metric to each service card in `_list_content.html`
  - [x] 4.2 Add sort-by-reliability button to filter bar using HTMX (`hx-get="/services/?sort=reliability"`)
  - [x] 4.3 Add warning indicator (icon + color) for services below threshold
  - [x] 4.4 Add `aria-label` on score display with descriptive text

- [x] Task 5: Add sort-by-reliability route support (AC: #3)
  - [x] 5.1 Add `sort` query parameter handling in `service_list()` route
  - [x] 5.2 When `sort=reliability`, sort services by `reliability_score.score` ascending (lowest first)
  - [x] 5.3 Pass `current_sort` to template for active button state

- [x] Task 6: Add CSS styles for reliability score components (AC: #2, #3)
  - [x] 6.1 Add `.reliability-score-meter` styles with color gradient (red 0-40, yellow 40-70, green 70-100)
  - [x] 6.2 Add `.reliability-trend` badge styles (improving/stable/declining)
  - [x] 6.3 Add `.reliability-breakdown` factor bar styles
  - [x] 6.4 Add `.reliability-warning` indicator styles for below-threshold services

- [x] Task 7: Write comprehensive tests (AC: #1, #2, #3)
  - [x] 7.1 Test `compute_reliability_score()` with various inputs: perfect score, zero score, mixed scores, edge cases
  - [x] 7.2 Test trend calculation: improving, stable, declining scenarios
  - [x] 7.3 Test `get_service_list()` includes reliability score
  - [x] 7.4 Test `get_service_detail()` includes reliability score
  - [x] 7.5 Test sort-by-reliability route parameter
  - [x] 7.6 Test below-threshold warning indicator in templates
  - [x] 7.7 Test ARIA meter role attributes in detail template
  - [x] 7.8 Test sort button active state in list template

- [x] Task 8: Run full test suite across all components
  - [x] 8.1 Run investigator pytest + ruff + mypy
  - [x] 8.2 Run UI pytest
  - [x] 8.3 Run operator cargo test
  - [x] 8.4 Verify no regressions from existing tests

## Dev Notes

### Architecture Patterns (MUST FOLLOW)

- **Service layer:** Extend existing `ServiceHealthService` in `ui/beeper_ui/services/service_health_service.py` — do NOT create a new service class. The reliability score is a computed aggregate of data already fetched by this service.
- **Route layer:** Extend existing `services_bp` routes in `ui/beeper_ui/routes/services.py` — add `sort` query parameter handling.
- **Template layer:** Modify existing templates in `ui/beeper_ui/templates/services/` — do NOT create new template files for reliability score. It integrates into existing detail and list views.
- **CSS:** Append to existing `ui/beeper_ui/static/css/main.css`.
- **HTMX pattern:** Use `hx-get` with query params, `hx-target` targeting `#services-wrapper`, `hx-swap="innerHTML"` — same pattern as health status filter buttons.

### Data Sources (Already Available)

All data needed for reliability score computation is already available through existing services:

1. **SLO compliance (40%):** `svc.get("compliance")` from `SloService.get_services()` — float 0.0-1.0
2. **Incident frequency (30%):** Count of investigations from `InvestigationService.list_investigations(service=name)` — filter by lookback window using `started_at` timestamp
3. **MTTR (30%):** Compute from resolved investigations — `completed_at - started_at` for investigations where both timestamps exist

### Computation Details

```python
# SLO component: compliance * 100 * 0.4 (max 40 points)
slo_component = (compliance or 0.0) * 100 * 0.4

# Frequency component: fewer incidents = higher score (max 30 points)
# 0 incidents in window → 30, 10+ incidents → 0, linear between
incident_count = len([inv for inv in investigations if inv in lookback_window])
frequency_component = max(0, 30 - (incident_count * 3))

# MTTR component: faster resolution = higher score (max 30 points)
# 0h MTTR → 30, 24h+ MTTR → 0, linear between
# If no resolved investigations, assume neutral (15 points)
if resolved_investigations:
    avg_mttr_hours = mean(resolution_times_in_hours)
    mttr_component = max(0, 30 - (avg_mttr_hours * 30 / 24))
else:
    mttr_component = 15  # neutral when no data

score = round(slo_component + frequency_component + mttr_component)
```

### Trend Calculation

Compare current 7-day window score vs previous 7-day window score:
- **improving:** current_score - previous_score > 5
- **declining:** previous_score - current_score > 5
- **stable:** difference <= 5 in either direction
- If no previous window data exists, trend is "stable"

### ARIA Accessibility Requirements

- Detail page score: `<div role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="75" aria-label="Reliability score: 75 out of 100">`
- Trend indicator: Include `aria-label` with descriptive text (e.g., "Trend: improving")
- Warning indicator: Include `aria-label="Below reliability threshold"`

### Previous Story Intelligence (from 7-4)

- `ServiceHealthService` uses lazy-initialized `SloService` and `InvestigationService` properties
- `compute_health_status()` is a standalone function (follow same pattern for `compute_reliability_score()`)
- Service list sorts by health status with `status_order` dict — add similar `reliability_order` for score sorting
- Service list route fetches all services once, computes counts, then filters — follow same fetch-once pattern for sort
- Template uses `format_compliance()` and `format_burn_rate()` Jinja2 context functions — register new `format_reliability_score()` if needed
- Service name validation: `^[a-zA-Z0-9_-]+$` regex + `len(name) > 100` check
- SSE stream tracks `prev_active_count` for change detection
- Test file: `ui/tests/test_service_health.py` — add new tests here or create `ui/tests/test_reliability_score.py`

### Project Structure Notes

- All UI services in `ui/beeper_ui/services/`
- All UI routes in `ui/beeper_ui/routes/`
- All templates in `ui/beeper_ui/templates/`
- CSS in `ui/beeper_ui/static/css/main.css`
- Tests in `ui/tests/`
- No operator changes needed — all data available through existing APIs

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 7 Story 7.5]
- [Source: ui/beeper_ui/services/service_health_service.py] — existing aggregation service to extend
- [Source: ui/beeper_ui/routes/services.py] — existing routes to extend
- [Source: ui/beeper_ui/templates/services/_detail_content.html] — detail template to modify
- [Source: ui/beeper_ui/templates/services/_list_content.html] — list template to modify
- [Source: _bmad-output/implementation-artifacts/7-4-per-service-health-feeds.md] — previous story patterns

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Story created with comprehensive context from Epic 7 acceptance criteria, architecture analysis, and previous story 7-4 learnings
- All data sources already available — pure UI aggregation, no operator changes needed
- Reliability score integrates into existing service health pages (detail + list views)
- Implemented `compute_reliability_score()` as standalone function following `compute_health_status()` pattern
- Added `sort_by` parameter to `get_service_list()` with "reliability" option
- Added reliability score card with ARIA meter role to service detail page
- Added reliability score metric with trend icon and warning indicator to service list cards
- Added sort-by-reliability and sort-by-status buttons to filter bar
- Added comprehensive CSS for score meter, trend badges, factor breakdown bars, and warning indicators
- 30 new tests covering unit tests, trend calculations, service integration, route handling, and template rendering
- All 3,486 tests passing (1,013 investigator + 1,935 UI + 538 operator)
- ruff clean on all changed files, mypy clean (86 files)

### File List

- `ui/beeper_ui/services/service_health_service.py` (modified — added `compute_reliability_score()`, integrated into `get_service_list()` and `get_service_detail()`)
- `ui/beeper_ui/routes/services.py` (modified — added `sort` query parameter, `current_sort` template var)
- `ui/beeper_ui/templates/services/_detail_content.html` (modified — added reliability score card with ARIA meter, trend, breakdown)
- `ui/beeper_ui/templates/services/_list_content.html` (modified — added reliability score metric, sort buttons, warning indicators)
- `ui/beeper_ui/static/css/main.css` (modified — added reliability score CSS styles)
- `ui/tests/test_reliability_score.py` (created — 30 tests)
