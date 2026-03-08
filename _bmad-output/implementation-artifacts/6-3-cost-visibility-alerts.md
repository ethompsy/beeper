# Story 6.3: Cost Visibility & Alerts

Status: done

## Story

As an **Admin**,
I want to see which environments or services drive excessive investigation costs,
so that I can identify noisy systems and optimize Beeper's focus.

## Acceptance Criteria

1. **Given** investigations have run with LLM costs, **When** I view the Cost Insights page, **Then** I see cost breakdown by (FR47):
   - Service/namespace
   - Investigation severity
   - Time period
   - LLM model tier used

2. **Given** a service generates excessive costs, **When** viewing the dashboard, **Then** that service is flagged as "High Cost" **And** I see:
   - Total cost for service
   - Investigation count
   - Cost per investigation
   - Trend (increasing/stable/decreasing)

3. **Given** excessive cost is detected, **When** thresholds are exceeded, **Then** an alert surfaces in the UI **And** a recommendation is provided (e.g., "payments service generated $45 in LLM costs (3x average) — consider tuning anomaly thresholds").

4. **Given** I identify a noisy environment, **When** I want to take action, **Then** I see actionable recommendations:
   - Tune anomaly detection sensitivity for that service (link to sources config)
   - Exclude certain log patterns from investigation
   - Set service-specific rate limits (link to spending caps)

5. **Given** cost data exists, **When** I want to report, **Then** I can export cost reports (CSV, JSON) **And** data includes model usage breakdown.

## Tasks / Subtasks

- [x] Task 1: Extend SpendingService with cost breakdown methods (AC: 1, 2, 3)
  - [x]1.1 Add `get_cost_by_service(period: str = "month") -> list[dict]` to `spending_service.py` — aggregates from cached scroll data: group by `service` field in investigation payloads, return list of `{service, total_cost_usd, investigation_count, cost_per_investigation, model_breakdown: dict}` sorted by total_cost descending
  - [x]1.2 Add `get_cost_by_severity(period: str = "month") -> list[dict]` — group by `severity` field, return `{severity, total_cost_usd, investigation_count, cost_per_investigation}` sorted by total_cost descending
  - [x]1.3 Add `get_cost_by_model(period: str = "month") -> list[dict]` — aggregate from `cost_stats.per_model` nested dict in each investigation's payload, return `{model, total_cost_usd, call_count, total_prompt_tokens, total_completion_tokens}` sorted by total_cost descending
  - [x]1.4 Reuse existing `get_spending_trend(period="daily")` for SVG cost trend chart rendering — filtered by selected period in route. Per-service trend method not needed since template renders single overall trend line.
  - [x]1.5 Add `get_high_cost_services(threshold_multiplier: float = 2.0) -> list[dict]` — identifies services with cost > threshold_multiplier × average per-service cost. Returns list of `{service, total_cost_usd, average_cost_usd, multiplier, investigation_count, cost_per_investigation, trend, recommendation}` where trend is "increasing"/"stable"/"decreasing" and recommendation is actionable text
  - [x]1.6 Add `export_cost_data(period: str = "month", fmt: str = "json") -> str | bytes` — exports cost breakdown as JSON (dict with by_service, by_severity, by_model, high_cost_services, generated_at) or CSV (service rows with cost columns). Follow `MetricsService.export_mttr_data()` pattern exactly.
  - [x]1.7 Add period filtering to `_scroll_investigations_with_costs()` — accept optional `period` param ("week"/"month"/"quarter") to filter investigations by `created_at` date range. Default "month" returns last 30 days. Cache key should include period.

- [x] Task 2: Create cost insights routes (AC: 1, 2, 3, 4, 5)
  - [x]2.1 Add `GET /spending/costs` route to `spending.py` — renders full cost insights page with all breakdowns. Support HTMX partial via `HX-Request` header check. Query params: `period` (week/month/quarter, default month). Follow `spending_dashboard()` pattern exactly.
  - [x]2.2 Add `GET /spending/costs/breakdown` HTMX partial route — returns `spending/_cost_breakdown.html` filtered by `period` query param for dynamic filtering without full page reload
  - [x]2.3 Add `GET /spending/costs/export` route — returns JSON or CSV file download based on `format` query param. Follow `metrics.py` export route pattern exactly (Content-Disposition headers, error handling).
  - [x]2.4 Add input validation: `_validate_cost_filters()` helper — whitelist period values (week/month/quarter), validate format param (json/csv). Follow `_validate_filters()` pattern from metrics.py.

- [x] Task 3: Create cost insights templates (AC: 1, 2, 3, 4)
  - [x]3.1 Create `ui/beeper_ui/templates/spending/costs.html` — extends `base.html`, full page with filter controls (period selector using HTMX `hx-get="/spending/costs/breakdown"` with `hx-target="#cost-breakdown-content"`), content area, export buttons. Follow `metrics/mttr.html` layout pattern.
  - [x]3.2 Create `ui/beeper_ui/templates/spending/_cost_breakdown.html` — HTMX partial containing:
    - High-cost service alerts section (if any services flagged)
    - Cost by service breakdown (category bars with "High Cost" badge for flagged services)
    - Cost by severity breakdown (category bars with severity colors)
    - Cost by model breakdown (category bars)
    - Per-service SVG cost trend chart (top 5 services)
  - [x]3.3 High-cost alerts: For each flagged service, render alert card with: service name, total cost, multiplier vs average, investigation count, actionable recommendation text. Use `.cost-alert-card` styling.
  - [x]3.4 Category bars: Reuse existing `.category-bars`, `.category-bar-track`, `.category-bar-fill` pattern from `_mttr_content.html`. Normalize bars to max value per category.
  - [x]3.5 Export buttons: Link to `/spending/costs/export?period=X&format=json` and CSV variant. Follow `_mttr_content.html` export button pattern.
  - [x]3.6 Service cost detail: Each service bar row shows: service badge, cost bar, `$X.XX (N investigations, $Y.YY avg)` label

- [x] Task 4: Add CSS styles for cost insights (AC: 1, 2, 3)
  - [x]4.1 Add to `main.css`: `.cost-alert-card` (background: `#fef3c7`, border: `1px solid #f59e0b`, padding, margin-bottom, border-radius), `.cost-alert-recommendation` (italic, color: `#92400e`), `.high-cost-badge` (background: `#fee2e2`, color: `#dc2626`, pill shape), `.cost-filter-bar` (follow `.mttr-filter-bar` pattern), `.cost-summary-stat` (large number display), `.cost-model-bar` (colored bar for model costs)
  - [x]4.2 Add `.cost-trend-chart` SVG styling (follow `.spending-trend-chart` pattern — `width: 100%`, `height: 300px`)

- [x] Task 5: Add navigation link (AC: 1)
  - [x]5.1 Add "Cost Insights" link to `base.html` nav after "Spending": `<a href="/spending/costs">Cost Insights</a>`

- [x] Task 6: Tests (AC: 1, 2, 3, 4, 5)
  - [x]6.1 Create `ui/tests/test_cost_insights.py` — test SpendingService cost breakdown methods with mock Qdrant data
  - [x]6.2 Test `get_cost_by_service()` — groups costs correctly by service, returns sorted by total_cost descending
  - [x]6.3 Test `get_cost_by_service()` with no data — returns empty list
  - [x]6.4 Test `get_cost_by_severity()` — groups correctly by severity
  - [x]6.5 Test `get_cost_by_model()` — aggregates from per_model nested dicts correctly
  - [x]6.6 Test `get_cost_by_model()` with missing per_model — handles gracefully (skip or zero)
  - [x]6.7 Test `get_high_cost_services()` — correctly flags services above threshold multiplier
  - [x]6.8 Test `get_high_cost_services()` — with all services at similar cost, none flagged
  - [x]6.9 Test `get_high_cost_services()` — with single service, not flagged (no meaningful average)
  - [x]6.10 Test `get_high_cost_services()` — trend calculation (increasing/stable/decreasing)
  - [x]6.11 Test `export_cost_data()` returns valid JSON with all breakdown sections
  - [x]6.12 Test `export_cost_data()` returns valid CSV with headers and rows
  - [x]6.13 Test `GET /spending/costs` renders full page with breakdown content
  - [x]6.14 Test `GET /spending/costs` with HX-Request returns partial (no `<!DOCTYPE html>`)
  - [x]6.15 Test `GET /spending/costs?period=week` filters correctly
  - [x]6.16 Test `GET /spending/costs/breakdown` HTMX partial returns breakdown content
  - [x]6.17 Test `GET /spending/costs/export?format=json` returns JSON download with Content-Disposition
  - [x]6.18 Test `GET /spending/costs/export?format=csv` returns CSV download
  - [x]6.19 Test cost insights with Qdrant unavailable — shows error card gracefully
  - [x]6.20 Test period filtering — month returns last 30 days data only

- [x] Task 7: Integration verification (AC: 1, 2, 3, 4, 5)
  - [x]7.1 Run `ruff check` on all new/modified Python files — fix any issues
  - [x]7.2 Run `mypy` on all new/modified Python files — fix any issues
  - [x]7.3 Run full Python test suite — verify zero regressions
  - [x]7.4 Verify "Cost Insights" navigation link appears in base template
  - [x]7.5 Verify category bars render with mock data (template inspection)
  - [x]7.6 Verify high-cost alerts render when threshold exceeded

## Dev Notes

### Architecture Decision: Extend SpendingService (NOT New Service)

Cost breakdown methods extend the existing `SpendingService` class because:
1. Cost data comes from the **same Qdrant `investigations` collection** already scrolled by `_scroll_investigations_with_costs()`
2. The cached scroll results can be reused for all breakdown aggregations — no redundant Qdrant queries
3. SpendingService already has the lazy-init Qdrant client pattern, caching, and close() cleanup
4. Creating a separate service would duplicate the entire scroll+cache infrastructure

### Cost Data Available in Qdrant

Each investigation payload (set by story 6-2's CostTracker integration) contains:

```python
{
    "investigation_id": "inv-abc123",
    "service": "payment-service",          # from investigation metadata
    "severity": "high",                     # from investigation metadata
    "created_at": "2026-03-07T14:30:00Z",  # ISO 8601
    "cost_stats": {
        "total_cost_usd": 0.05,            # float — total LLM cost for this investigation
        "total_cost_cents": 5,              # int — same in cents
        "call_count": 3,                    # number of LLM calls
        "total_prompt_tokens": 5000,        # total input tokens
        "total_completion_tokens": 2000,    # total output tokens
        "per_model": {                      # per-model breakdown
            "claude-haiku-3.5": {
                "calls": 2,
                "cost_usd": 0.02,
                "prompt_tokens": 3000,
                "completion_tokens": 1200
            },
            "claude-sonnet-4-20250514": {
                "calls": 1,
                "cost_usd": 0.03,
                "prompt_tokens": 2000,
                "completion_tokens": 800
            }
        }
    }
}
```

### "High Cost" Service Detection Algorithm

```python
def get_high_cost_services(self, threshold_multiplier: float = 2.0) -> list[dict]:
    """Flag services with cost > threshold_multiplier × average per-service cost."""
    by_service = self.get_cost_by_service()
    if len(by_service) < 2:
        return []  # Need at least 2 services for meaningful comparison

    avg_cost = sum(s["total_cost_usd"] for s in by_service) / len(by_service)
    threshold = avg_cost * threshold_multiplier

    flagged = []
    for svc in by_service:
        if svc["total_cost_usd"] > threshold:
            multiplier = svc["total_cost_usd"] / avg_cost if avg_cost > 0 else 0
            flagged.append({
                "service": svc["service"],
                "total_cost_usd": svc["total_cost_usd"],
                "average_cost_usd": round(avg_cost, 4),
                "multiplier": round(multiplier, 1),
                "investigation_count": svc["investigation_count"],
                "cost_per_investigation": svc["cost_per_investigation"],
                "trend": _calculate_service_trend(svc["service"]),
                "recommendation": _generate_recommendation(svc, multiplier),
            })
    return flagged
```

### Trend Calculation for Services

Compare current period cost to previous period:
```python
def _calculate_service_trend(service_costs_current, service_costs_previous):
    if not service_costs_previous:
        return "stable"
    change_pct = ((current - previous) / previous) * 100 if previous > 0 else 0
    if change_pct > 10:
        return "increasing"
    elif change_pct < -10:
        return "decreasing"
    return "stable"
```

### Actionable Recommendations

Recommendations are UI text with contextual links — NOT automated actions:

```python
def _generate_recommendation(svc: dict, multiplier: float) -> str:
    service = svc["service"]
    cost = svc["total_cost_usd"]
    return (
        f"{service} generated ${cost:.2f} in LLM costs "
        f"({multiplier:.1f}x average) — consider tuning anomaly "
        f"detection thresholds or excluding noisy log patterns"
    )
```

The template renders these as alert cards. Actual sensitivity tuning and pattern exclusion are existing features accessible via the Sources page (`/sources/`).

### High Cost Threshold Configuration

```bash
BEEPER_COST_HIGH_THRESHOLD_MULTIPLIER=2.0  # Flag services > 2x average cost
```

Default 2.0 if env var not set. Loaded in `get_high_cost_services()` from env.

### Route Structure (Added to Existing spending_bp)

Routes are added to the existing `spending_bp` Blueprint (url_prefix="/spending"):

| Route | Method | Description |
|-------|--------|-------------|
| `/spending/costs` | GET | Full cost insights page (+ HTMX partial) |
| `/spending/costs/breakdown` | GET | HTMX partial for filtered breakdown |
| `/spending/costs/export` | GET | JSON/CSV export download |

### Template Structure

```
ui/beeper_ui/templates/spending/
├── spending.html              # Existing — spending caps dashboard
├── _spending_content.html     # Existing — spending caps HTMX partial
├── costs.html                 # NEW — cost insights full page
└── _cost_breakdown.html       # NEW — cost insights HTMX partial
```

### HTMX Filtering Pattern (Follow metrics exactly)

```html
<!-- Filter bar in costs.html -->
<div class="cost-filter-bar">
  <select name="period"
          hx-get="/spending/costs/breakdown"
          hx-target="#cost-breakdown-content"
          hx-swap="innerHTML">
    <option value="week">Last Week</option>
    <option value="month" selected>Last Month</option>
    <option value="quarter">Last Quarter</option>
  </select>
  <a href="/spending/costs/export?format=json" class="export-btn">Export JSON</a>
  <a href="/spending/costs/export?format=csv" class="export-btn">Export CSV</a>
</div>
<div id="cost-breakdown-content">
  {% include "spending/_cost_breakdown.html" %}
</div>
```

### Category Bars Pattern (Reuse from metrics)

```html
<!-- Cost by service with High Cost badge -->
<div class="category-bars">
  {% for svc in by_service %}
  <div class="category-bar-row">
    <span class="category-label">
      {{ svc.service }}
      {% if svc.service in high_cost_services %}
      <span class="high-cost-badge">High Cost</span>
      {% endif %}
    </span>
    <div class="category-bar-track">
      <div class="category-bar-fill service-bar"
           style="width: {{ (svc.total_cost_usd / max_service_cost * 100) | round(1) }}%">
      </div>
    </div>
    <span class="category-count">${{ "%.2f"|format(svc.total_cost_usd) }} ({{ svc.investigation_count }} inv)</span>
  </div>
  {% endfor %}
</div>
```

### Export Format

**JSON export:**
```json
{
  "period": "month",
  "generated_at": "2026-03-07T14:30:00Z",
  "by_service": [{"service": "api-gateway", "total_cost_usd": 12.50, "investigation_count": 45, "cost_per_investigation": 0.28}],
  "by_severity": [{"severity": "high", "total_cost_usd": 8.30, "investigation_count": 20}],
  "by_model": [{"model": "claude-sonnet-4-20250514", "total_cost_usd": 15.00, "call_count": 50}],
  "high_cost_services": [{"service": "payments", "total_cost_usd": 45.00, "multiplier": 3.2, "recommendation": "..."}]
}
```

**CSV export:** Header row + data rows for by_service breakdown.

### Existing Code to Reuse (DO NOT RECREATE)

| Component | Location | What to Reuse |
|-----------|----------|---------------|
| SpendingService scroll+cache | `spending_service.py:38-66` | `_scroll_investigations_with_costs()` and `_cached_points` |
| SpendingService Qdrant client | `spending_service.py:20-36` | Lazy-init pattern, `close()` method |
| Spending blueprint pattern | `routes/spending.py` | Blueprint structure, `get_spending_service()`, error handling |
| SVG chart computation | `routes/spending.py:20-82` | `_compute_spend_chart_data()` for cost trend chart |
| Template data loading | `routes/spending.py:85-104` | `_load_spending_template_data()` pattern |
| HTMX partial detection | `routes/spending.py:113` | `request.headers.get("HX-Request")` check |
| Input validation | `routes/metrics.py:27-45` | `_validate_filters()` pattern for period/format validation |
| Export route | `routes/metrics.py:245-283` | Content-Disposition headers, format handling |
| Category bars template | `templates/metrics/_mttr_content.html:65-101` | `.category-bars` HTML structure |
| Severity color bars | `templates/metrics/_mttr_content.html:80-90` | `.severity-bar.severity-{{ sev.severity }}` CSS classes |
| Error card pattern | `templates/spending/_spending_content.html:1-4` | Error message card when Qdrant unavailable |
| CSS bar classes | `main.css` | `.category-bars`, `.category-bar-track`, `.category-bar-fill`, `.category-bar-row`, `.category-label`, `.category-count` |
| CSS severity colors | `main.css` | `.severity-bar.severity-critical`, `.severity-high`, `.severity-medium`, `.severity-low` |
| CSS card/badge | `main.css` | `.card`, `.service-badge`, `.status-badge`, `.export-btn` |
| CSS alert banner | `main.css` | `.spending-cap-alert` — reuse pattern for cost alert cards |
| Flask test patterns | `ui/tests/test_spending.py` | `_make_point()`, mock patterns, HTMX testing |
| Qdrant mock pattern | `ui/tests/test_spending.py:17-37` | `MagicMock` for Qdrant client with `scroll` return tuples |

### Anti-Patterns to Avoid

- **DO NOT** create a new service class — extend existing `SpendingService` with new methods
- **DO NOT** create a new blueprint — add routes to existing `spending_bp`
- **DO NOT** create new Qdrant collections — read from existing `investigations` collection
- **DO NOT** duplicate the scroll+cache infrastructure — reuse `_scroll_investigations_with_costs()`
- **DO NOT** add JavaScript — category bars use pure CSS, filtering uses HTMX
- **DO NOT** create a separate CSS file — add styles to existing `main.css`
- **DO NOT** use `float` for money comparisons — threshold comparison is fine since display only
- **DO NOT** implement automated sensitivity tuning — recommendations are display-only text
- **DO NOT** use async — Flask routes are synchronous
- **DO NOT** modify existing spending routes — add new routes alongside them
- **DO NOT** modify existing templates — create new template files for cost insights
- **DO NOT** modify the investigator pipeline — cost insights are read-only queries on existing data
- **DO NOT** re-register the spending_bp — it's already registered in `__init__.py`

### Project Structure Notes

**New files:**
- `ui/beeper_ui/templates/spending/costs.html` — Full cost insights page
- `ui/beeper_ui/templates/spending/_cost_breakdown.html` — HTMX partial content
- `ui/tests/test_cost_insights.py` — Cost breakdown + route tests

**Modified files:**
- `ui/beeper_ui/services/spending_service.py` — Add cost breakdown methods (get_cost_by_service, get_cost_by_severity, get_cost_by_model, get_high_cost_services, export_cost_data, period filtering)
- `ui/beeper_ui/routes/spending.py` — Add 3 new routes (costs, costs/breakdown, costs/export) + validation helper
- `ui/beeper_ui/templates/base.html` — Add "Cost Insights" nav link
- `ui/beeper_ui/static/css/main.css` — Add cost insights styles

### Previous Story Intelligence (from 6-1 and 6-2)

**From 6-2 (LLM Spending Caps):**
- SpendingService + spending Blueprint pattern established — extend with new methods/routes
- `_scroll_investigations_with_costs()` caches all investigation payloads with cost_stats
- `_compute_spend_chart_data()` generates SVG chart coordinates — reuse for per-service trends
- Progress bar color classes (`.spend-level-warning`, `.spend-level-high`, `.spend-level-critical`) — reuse pattern for cost alert severity
- Code review lessons: always call `update_spend()`, guard against division by zero, use server-side CSS classes not style-based selectors, validate env vars with try/except

**From 6-1 (MTTR Trends Dashboard):**
- MetricsService + metrics Blueprint pattern — category bars, SVG charts, HTMX filtering
- `_validate_filters()` input validation — reuse for cost filter validation
- Export route with Content-Disposition headers — reuse exactly for cost export
- Scroll caching per service instance — already used in SpendingService
- Error card pattern for Qdrant unavailability — reuse exactly
- Code review lessons: validate all inputs, sanitize error messages, cache scroll results, log exceptions

**Common patterns across 6-1 and 6-2:**
- `try/except/finally` with `svc.close()` in routes
- `_load_*_template_data()` helper for centralizing data loading
- HTMX: `request.headers.get("HX-Request")` for full vs partial rendering
- Period validation: whitelist valid periods, default to "month"

### Testing Standards

- **Framework**: pytest with Flask test client
- **Mocking**: `unittest.mock.MagicMock` for Qdrant client, `unittest.mock.patch` for service instantiation
- **Test file**: `ui/tests/test_cost_insights.py` (new file)
- **Qdrant mock data**: Create test points with realistic `cost_stats` including `per_model` nested dicts, varying `service` and `severity` values
- **HTMX testing**: Test both full-page and partial (`HX-Request: true` header) responses
- **Error cases**: Qdrant unavailable returns graceful error card
- **Pattern**: Follow `ui/tests/test_spending.py` for test structure and mock helpers
- **Edge cases**: No data, single service (no high-cost flagging), all same cost, missing per_model field

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 6, Story 6.3]
- [Source: _bmad-output/planning-artifacts/prd.md#FR47 — surface environments with excessive investigation costs]
- [Source: _bmad-output/planning-artifacts/architecture.md#Observability — cost reporting]
- [Source: ui/beeper_ui/services/spending_service.py — SpendingService scroll+cache, aggregation patterns]
- [Source: ui/beeper_ui/routes/spending.py — spending_bp, chart computation, template data loading]
- [Source: ui/beeper_ui/routes/metrics.py — input validation, export route, chart computation]
- [Source: ui/beeper_ui/templates/spending/_spending_content.html — progress bars, alert banners, SVG chart]
- [Source: ui/beeper_ui/templates/metrics/_mttr_content.html — category bars, severity colors]
- [Source: ui/tests/test_spending.py — mock patterns, route testing, HTMX testing]
- [Source: _bmad-output/implementation-artifacts/6-1-mttr-trends-dashboard.md — metrics patterns and lessons]
- [Source: _bmad-output/implementation-artifacts/6-2-llm-spending-caps.md — spending patterns and lessons]
- [Source: investigator/beeper_investigator/llm/cost.py — CostTracker, LLM_PRICING, per_model data]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created
- Extends SpendingService with cost breakdown methods (no new service class)
- Routes added to existing spending_bp Blueprint (3 new routes)
- Cost breakdown by service, severity, and LLM model from existing Qdrant data
- "High Cost" flagging: services > 2x average per-service cost (configurable via env var)
- Actionable recommendations as display text with contextual guidance
- Category bars, SVG trend chart, HTMX filtering — all reuse established patterns
- JSON/CSV export follows metrics export pattern
- 7 tasks: service methods, routes, templates, CSS, nav, tests, integration

### Change Log

- Extended SpendingService with 7 new methods for cost breakdown aggregation
- Added 3 new routes to spending Blueprint (/costs, /costs/breakdown, /costs/export)
- Created cost insights full page template and HTMX partial template
- Added cost insights CSS styles (alert cards, high-cost badges, model bars, trend chart)
- Added "Cost Insights" nav link to base.html
- Created 20 new tests in test_cost_insights.py
- Fixed mypy errors: float() cast in sort lambdas, explicit list type annotations
- Fixed CSV content_type assertion to handle charset suffix

### File List

**New files:**
- `ui/beeper_ui/templates/spending/costs.html` — Full cost insights page with HTMX filter bar
- `ui/beeper_ui/templates/spending/_cost_breakdown.html` — HTMX partial with alerts, breakdowns, trend chart
- `ui/tests/test_cost_insights.py` — 20 tests across 7 test classes

**Modified files:**
- `ui/beeper_ui/services/spending_service.py` — Added: _filter_by_period, get_cost_by_service, get_cost_by_severity, get_cost_by_model, get_high_cost_services, _calculate_service_trend, export_cost_data
- `ui/beeper_ui/routes/spending.py` — Added: _validate_cost_filters, _load_cost_template_data, cost_insights, cost_breakdown_partial, export_costs routes
- `ui/beeper_ui/templates/base.html` — Added "Cost Insights" nav link
- `ui/beeper_ui/static/css/main.css` — Added cost insights styles
