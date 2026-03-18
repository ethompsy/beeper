# Story 7.7: Investor-Ready Reports

Status: review

## Story

As **Diana** (founder/CEO),
I want investor-ready reports derived from Beeper's operational data,
so that I can demonstrate Beeper's value with real metrics during fundraising conversations.

## Acceptance Criteria

1. **Given** Diana navigates to the reports page (`/reports/executive`), **When** the page loads, **Then** a report is displayed with: total investigations resolved, MTTR improvement percentage, SLO compliance across all services, trust level progression, and false page reduction trend. **And** the report is formatted for presentation (clean layout, exportable).

2. **Given** the executive report, **When** Diana clicks "Export PDF", **Then** a PDF is generated with the current report data, Beeper branding, and date range. **And** the PDF is suitable for investor slide decks.

3. **Given** the executive report, **When** filtered by time period (last 30 days, last 90 days, all time), **Then** all metrics recalculate for the selected period. **And** comparison to previous period is shown (e.g., "MTTR improved 35% vs previous 90 days").

## Tasks / Subtasks

- [x] Task 1: Create `ExecutiveReportService` (AC: #1, #3)
  - [x]1.1 Create `ui/beeper_ui/services/executive_report_service.py`
  - [x]1.2 Implement `compute_executive_metrics(period_days, investigations, slo_services, trust_configs, noise_report)` standalone function
  - [x]1.3 Metrics to compute:
    - `total_investigations_resolved`: count of completed investigations in period
    - `mttr_improvement_pct`: MTTR change vs previous period (negative = improvement)
    - `avg_slo_compliance`: average compliance across all services
    - `trust_progression`: dict with distribution + changes count
    - `false_page_reduction_pct`: false page rate change vs previous period
  - [x]1.4 Implement `compute_period_comparison(current_metrics, previous_metrics)` — returns comparison dict with delta and direction for each metric
  - [x]1.5 Implement `ExecutiveReportService` class with lazy-init `InvestigationService`, `SloService`, `NoiseReportService`, httpx client for trust API. `get_report_data(period_days)` fetches all data, calls compute functions for current AND previous period, returns complete report dict.
  - [x]1.6 Period mapping: "30d" → 30 days, "90d" → 90 days, "all" → None (no cutoff)

- [x]Task 2: Add executive report route (AC: #1, #3)
  - [x]2.1 Add `executive_report()` function to `ui/beeper_ui/routes/reports.py` at route `/executive`
  - [x]2.2 Query params: `period` (30d/90d/all, default: 90d)
  - [x]2.3 Validate period against `_VALID_EXECUTIVE_PERIODS = {"30d", "90d", "all"}`
  - [x]2.4 Factory function `_get_executive_report_service()` using `current_app.config["OPERATOR_URL"]` and timeout
  - [x]2.5 HTMX support: return `_executive_content.html` partial on HX-Request
  - [x]2.6 Error handler returns graceful error template with empty data

- [x]Task 3: Create executive report templates (AC: #1, #2, #3)
  - [x]3.1 Create `ui/beeper_ui/templates/reports/executive.html` extending base.html
  - [x]3.2 Create `ui/beeper_ui/templates/reports/_executive_content.html` with:
    - Period filter buttons (30d, 90d, all) with HTMX `hx-get="/reports/executive?period=X"` targeting `#executive-content`
    - Report header: "Beeper Executive Report" with date range
    - Metric cards row: Total Resolved, MTTR Improvement, SLO Compliance, Trust Progression, False Page Reduction
    - Each card shows metric value + comparison badge ("35% better vs previous period")
    - Sections: MTTR trend summary, SLO compliance summary, Trust level distribution bar, False page trend
  - [x]3.3 CSS-only data visualization following existing bar chart pattern from `_dashboard_content.html`
  - [x]3.4 ARIA region landmarks on each section

- [x]Task 4: Implement PDF export via print (AC: #2)
  - [x]4.1 Add `@media print` CSS rules in `main.css`:
    - Hide nav, header, footer, command palette, filter buttons
    - Show Beeper logo/branding header (hidden in screen mode)
    - Clean margins, page breaks between sections
    - Force white background for readability
    - Show date range in print header
  - [x]4.2 Add "Export PDF" button that calls `window.print()` — hidden in print mode itself
  - [x]4.3 Add `.print-only` class for branding elements visible only in print
  - [x]4.4 Add `.no-print` class for interactive elements hidden in print

- [x]Task 5: Navigation & command palette integration (AC: #1)
  - [x]5.1 Add "Executive Report" entry to COMMANDS array in `command-palette.js` with `href: "/reports/executive"`, `category: "navigation"`, `keywords: ["executive", "investor", "report", "diana", "pdf"]`, `shortcut: "g e"`
  - [x]5.2 Add `e: "/reports/executive/"` to CHORD_SHORTCUTS
  - [x]5.3 Update existing "Reports" command to point to `/reports/executive` instead of `/reports/`
  - [x]5.4 Add "Reports" navigation link to `base.html` nav bar: `<a href="/reports/executive">Reports</a>`

- [x]Task 6: Write comprehensive tests (AC: #1, #2, #3)
  - [x]6.1 Create `ui/tests/test_executive_report.py`
  - [x]6.2 Unit tests for `compute_executive_metrics()`:
    - Empty data returns zeros/None
    - Correct resolved investigation count
    - MTTR improvement calculation
    - SLO compliance averaging
    - Trust progression extraction
    - False page reduction calculation
  - [x]6.3 Unit tests for `compute_period_comparison()`:
    - Improvement direction detection
    - Degradation direction detection
    - No-change handling
    - Zero-denominator edge case
  - [x]6.4 Integration test for `get_report_data()` with mocked services
  - [x]6.5 Route tests:
    - GET /reports/executive returns 200
    - HTMX request returns partial
    - Period filter changes template data
    - Invalid period falls back to default
    - Error fallback renders error template
  - [x]6.6 Template tests:
    - Metric cards render with correct values
    - Comparison badges show correct direction
    - Period buttons have HTMX attributes
    - Export PDF button present
    - Print-only branding elements present
    - ARIA landmarks present

## Dev Notes

### Architecture Compliance

- **Framework:** Flask + HTMX + SSE (no React, no Node.js)
- **Styling:** CSS in `main.css` — CSS-only visualizations (no JS chart libraries)
- **PDF export:** Use `@media print` CSS + `window.print()` — zero new dependencies. This is the pragmatic approach matching "no Node.js in build chain." Server-side PDF (weasyprint/reportlab) would add heavy system dependencies.
- **Data sources:** Reuse existing services — do NOT create new Qdrant queries or API endpoints
- **Service pattern:** Class with lazy-init properties, `close()` method, factory function in routes
- **Route pattern:** Blueprint function, input validation, try/except/finally, HTMX conditional rendering

### Critical Reuse — DO NOT REINVENT

- **MTTR computation:** Reuse `compute_mttr_trends()` and `compute_mttr_change_pct()` from `analytics_service.py` — import directly, do not copy
- **Trust distribution:** Reuse `compute_trust_distribution()` and `compute_trust_changes()` from `analytics_service.py`
- **False page data:** Reuse `NoiseReportService.build_noise_report()` from `noise_report_service.py`
- **SLO compliance:** Reuse `SloService.get_services()` from `slo_service.py`
- **Investigation data:** Reuse `InvestigationService.list_investigations()` from `investigation_service.py`
- **Trust API:** Reuse the `_get_trust_levels()` pattern from `AnalyticsService` (httpx GET to `/api/v1/trust/services`)
- **Timestamp parsing:** Reuse `_parse_dt()` from `analytics_service.py` — import it, do not duplicate

### Previous Story Intelligence (from 7-6)

- `AnalyticsService` pattern: lazy-init with `SloService`, `InvestigationService`, httpx client. `close()` cleans up all three.
- Standalone compute functions at module level (not class methods) — easier to unit test
- HTMX filter buttons MUST preserve all active parameters across swaps (learned from 7-5 review)
- `HTTPException` must be re-raised before generic `except Exception` — otherwise `abort()` is swallowed
- Duplicated `_parse_dt` exists in analytics_service.py and service_health_service.py — import from analytics_service.py for this story
- CSS bar patterns: `.analytics-bar` with `width: {{ value }}%` and background color

### File Structure

- `ui/beeper_ui/services/executive_report_service.py` — NEW service
- `ui/beeper_ui/routes/reports.py` — MODIFY (add executive route + factory)
- `ui/beeper_ui/templates/reports/executive.html` — NEW template
- `ui/beeper_ui/templates/reports/_executive_content.html` — NEW partial
- `ui/beeper_ui/static/css/main.css` — MODIFY (add executive + print styles)
- `ui/beeper_ui/static/js/command-palette.js` — MODIFY (add Executive Report command + g e chord)
- `ui/beeper_ui/templates/base.html` — MODIFY (add Reports nav link)
- `ui/tests/test_executive_report.py` — NEW tests

### Testing Standards

- pytest with Flask test client
- Mock external services (InvestigationService, SloService, NoiseReportService, httpx)
- Use `unittest.mock.patch` for service mocking
- Follow `test_analytics_dashboard.py` patterns for route + template assertions
- Verify HTMX partial rendering separately from full page
- Test edge cases: empty data, zero denominators, missing services

### Existing Service Imports

```python
from beeper_ui.services.investigation_service import (
    Investigation, InvestigationService, InvestigationServiceError,
)
from beeper_ui.services.slo_service import SloService, SloServiceError
from beeper_ui.services.noise_report_service import (
    NoiseReportService, NoiseReportServiceError,
)
from beeper_ui.services.analytics_service import (
    compute_mttr_trends, compute_mttr_change_pct,
    compute_trust_distribution, compute_trust_changes, _parse_dt,
)
```

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-7.7] — AC definitions
- [Source: _bmad-output/planning-artifacts/architecture.md] — Flask+HTMX stack, no Node.js, CSS-only viz
- [Source: ui/beeper_ui/services/analytics_service.py] — Reusable compute functions
- [Source: ui/beeper_ui/services/noise_report_service.py] — False page data
- [Source: ui/beeper_ui/routes/reports.py] — Existing reports blueprint
- [Source: ui/beeper_ui/routes/analytics.py] — Dashboard route pattern
- [Source: ui/beeper_ui/static/js/command-palette.js] — Command registry pattern

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Created `ExecutiveReportService` with `compute_executive_metrics()` and `compute_period_comparison()` standalone functions reusing existing analytics service compute functions
- Added `/reports/executive` route with period filtering (30d/90d/all), HTMX partial rendering, error fallback
- Created `executive.html` and `_executive_content.html` templates with metric cards, comparison badges, trust distribution bar, and trust change timeline
- Implemented PDF export via `@media print` CSS + `window.print()` button — zero new dependencies
- Added "Executive Report" command (g+e chord) to command palette and "Reports" link to nav
- 38 new tests: 7 unit (compute_executive_metrics), 5 unit (compute_period_comparison), 8 direction helpers, 2 integration (service), 6 route, 10 template
- All 2,020 UI tests passing (+38), ruff clean on all new/modified files

### File List

- ui/beeper_ui/services/executive_report_service.py (NEW)
- ui/beeper_ui/routes/reports.py (MODIFIED — added executive route + imports)
- ui/beeper_ui/templates/reports/executive.html (NEW)
- ui/beeper_ui/templates/reports/_executive_content.html (NEW)
- ui/beeper_ui/static/css/main.css (MODIFIED — executive + print styles)
- ui/beeper_ui/static/js/command-palette.js (MODIFIED — Executive Report command + g+e chord)
- ui/beeper_ui/templates/base.html (MODIFIED — Reports nav link)
- ui/tests/test_executive_report.py (NEW — 38 tests)
