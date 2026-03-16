# Story 3.7: Noise Report Dashboard

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an **admin**,
I want to view a noise report showing signal-to-noise ratio and false page trends,
so that I can measure whether Beeper's alerting is improving and identify noisy services.

## Acceptance Criteria

1. **Given** accumulated investigation feedback data
   **When** an admin navigates to the noise report (`/reports/noise`)
   **Then** the dashboard shows: signal-to-noise ratio (accurate / total), false page rate trend over time, and per-service breakdown
   **And** the page responds within 2 seconds (NFR2)

2. **Given** the noise report dashboard
   **When** filtering by service or time period
   **Then** the metrics recalculate for the filtered view
   **And** the worst-performing services (highest false page rate) are highlighted

3. **Given** the noise report page
   **When** accessed by a user with role "user"
   **Then** the page is visible (read-only) — noise metrics benefit all SREs, not just admins

## Tasks / Subtasks

- [x] Task 1: Create NoiseReportService (AC: #1, #2)
  - [x]1.1 Create `ui/beeper_ui/services/noise_report_service.py` following existing service pattern (lazy QdrantClient, `close()`)
  - [x]1.2 Define `@dataclass ServiceNoiseStats` with fields: `service_name` (str), `total_investigations` (int), `accurate_count` (int), `inaccurate_count` (int), `not_an_issue_count` (int), `signal_to_noise_ratio` (float), `false_page_count` (int), `total_notifications` (int), `false_page_rate` (float), `is_worst_performer` (bool)
  - [x]1.3 Define `@dataclass NoiseReportData` with fields: `overall_signal_to_noise` (float), `overall_false_page_rate` (float), `total_investigations_with_feedback` (int), `total_notifications` (int), `total_false_pages` (int), `per_service` (list[ServiceNoiseStats]), `trend_data` (list[dict]), `selected_service` (str|None), `selected_period` (str)
  - [x]1.4 Implement `get_all_service_feedback()` — paginated Qdrant scroll of `investigations` collection WITHOUT service filter, grouping results by `payload.get("service")` to aggregate feedback across all services in a single pass
  - [x]1.5 Implement `get_false_page_stats(service, date_from, date_to)` — delegate to `NotificationAuditService.get_audit_statistics()` for each service, plus cross-service totals
  - [x]1.6 Implement `get_false_page_trend(service, period)` — query `notification_audit` collection with time-bucketed aggregation (7d/30d/90d periods divided into buckets) to produce trend data points
  - [x]1.7 Implement `build_noise_report(service, period)` — orchestrator that calls 1.4, 1.5, 1.6, computes overall ratios, marks worst performers (highest false page rate), returns `NoiseReportData`
  - [x]1.8 Define `NoiseReportServiceError(Exception)` for service-level failures

- [x] Task 2: Create reports Blueprint and noise route (AC: #1, #2, #3)
  - [x]2.1 Create `ui/beeper_ui/routes/reports.py` with `reports_bp = Blueprint("reports", __name__, url_prefix="/reports")`
  - [x]2.2 Add `_get_noise_report_service()` and `_get_audit_service()` factory helpers
  - [x]2.3 Implement `GET /reports/noise` route — `@require_role("user")` (AC#3: accessible to all SREs), builds report data, returns full page or HTMX partial based on `HX-Request` header
  - [x]2.4 Add service filter from `?service=` query param and period filter from `?period=` query param (default "30d")
  - [x]2.5 Define `VALID_PERIODS = {"7d", "30d", "90d"}` and service name validation regex
  - [x]2.6 Graceful degradation: if Qdrant or audit service fails, render page with error message instead of crashing

- [x] Task 3: Register reports Blueprint (AC: #1)
  - [x]3.1 Add `from beeper_ui.routes.reports import reports_bp` and `app.register_blueprint(reports_bp)` to `ui/beeper_ui/routes/__init__.py`

- [x] Task 4: Create dashboard templates (AC: #1, #2)
  - [x]4.1 Create `ui/beeper_ui/templates/reports/noise.html` — extends `base.html`, page title "Noise Report", includes filter bar and `{% include "reports/_noise_content.html" %}`
  - [x]4.2 Create `ui/beeper_ui/templates/reports/_noise_content.html` — HTMX partial with: summary cards (overall S/N ratio, false page rate, total investigations, total notifications), per-service breakdown table with highlighting, false page trend display
  - [x]4.3 Add HTMX filter controls: service dropdown (`hx-get` to `/reports/noise`, `hx-target="#noise-content"`, `hx-include` all filters), period dropdown (7d/30d/90d)
  - [x]4.4 Per-service table: service name, investigations count, accurate/inaccurate/not-an-issue counts, S/N ratio, false page rate, visual highlighting for worst performers
  - [x]4.5 False page trend: render as text-based percentage values with up/down arrows per bucket (simple approach; SVG sparklines are Phase 3)
  - [x]4.6 Empty state: "No investigation feedback recorded yet." with link to investigations list

- [x] Task 5: Add CSS styles (AC: #1, #2)
  - [x]5.1 Add noise report CSS classes to `ui/beeper_ui/static/css/main.css`: `.noise-summary-cards`, `.noise-summary-card`, `.noise-summary-value`, `.noise-summary-label`, `.noise-table`, `.noise-worst-performer`, `.noise-filter-bar`, `.noise-trend-display`, `.noise-trend-up`, `.noise-trend-down`, `.noise-trend-stable`

- [x] Task 6: Comprehensive testing (AC: #1, #2, #3)
  - [x]6.1 Create `ui/tests/test_noise_report_service.py` — service unit tests: feedback aggregation across all services, per-service grouping, false page stats delegation, trend data computation, worst performer marking, empty data handling, Qdrant failure handling, pagination
  - [x]6.2 Create `ui/tests/test_noise_report_routes.py` — route tests: GET returns 200 for user role (AC#3), GET returns 200 for admin role, HTMX partial response (no `<!DOCTYPE html>`), service filter applied, period filter applied, invalid period defaults to 30d, error state rendering, service close verification
  - [x]6.3 Run full UI test suite — zero regressions
  - [x]6.4 Run ruff lint on all new/modified files — all clean

## Dev Notes

### Architecture Patterns to Follow

**CRITICAL CONTEXT: This story adds a read-only noise report dashboard at `/reports/noise` that aggregates data from two existing Qdrant collections. It does NOT modify any existing data, create new collections, or add write operations. This is purely a visualization/reporting layer.**

**What already exists (DO NOT recreate):**

| Component | Location | Status |
|-----------|----------|--------|
| `NotificationAuditService` | `ui/beeper_ui/services/notification_audit_service.py` | Done (Epic 2) |
| `get_audit_statistics(service, channel_type, date_from, date_to)` | Returns `{total_notifications, false_page_count, false_page_rate}` | Done |
| `query_audit(service, ..., date_from, date_to, is_false_page, limit, offset)` | Returns list of audit record dicts | Done |
| `AUDIT_COLLECTION = "notification_audit"` | Collection with `service`, `is_false_page`, `false_page_reason`, `timestamp_epoch` | Done |
| `AdaptiveThresholdService` | `ui/beeper_ui/services/adaptive_threshold_service.py` | Done (story 3-5) |
| `get_service_feedback_summary(service_name)` | Returns `{total, accurate, inaccurate, not_an_issue}` per service | Done (reuse pattern) |
| `INVESTIGATIONS_COLLECTION = "investigations"` | Collection with `service`, `investigation_feedback` fields | Done |
| Investigation feedback fields | `investigation_feedback` ("accurate"/"inaccurate"/"not_an_issue") in Qdrant | Done (story 3-4) |
| `_iso_to_epoch()` static method | Converts ISO 8601 → epoch float for Qdrant range queries | Done (in NotificationAuditService) |
| SLO dashboard pattern | `ui/beeper_ui/routes/slo.py` + `templates/slo/dashboard.html` + `_content.html` | Done (story 1-7) |
| `@require_role` decorator | `ui/beeper_ui/middleware/permissions.py` | Done |
| CSS summary card classes | `.slo-summary-cards`, `.mttr-summary-cards` patterns in `main.css` | Done |
| CSS table classes | `.investigations-table`, `.slo-table`, `.drilldown-table` patterns | Done |
| CSS filter bar | `.mttr-filter-bar` pattern | Done |
| CSS badge classes | `.badge`, `.status-*`, `.severity-*` patterns | Done |
| `register_blueprints()` | `ui/beeper_ui/routes/__init__.py` | Done |
| `base.html` template | `ui/beeper_ui/templates/base.html` — extends with `{% block content %}` | Done |

**What this story adds:**

| Component | Description |
|-----------|-------------|
| `NoiseReportService` class | New service for aggregating investigation feedback + false page data across all services |
| `ServiceNoiseStats` dataclass | Per-service noise metrics |
| `NoiseReportData` dataclass | Complete report data container |
| `reports_bp` Blueprint | New Blueprint at `/reports` prefix |
| `GET /reports/noise` | Dashboard route with HTMX filter support |
| `reports/noise.html` template | Full page with filter bar |
| `reports/_noise_content.html` template | HTMX partial with summary cards + per-service table + trend |
| CSS noise report classes | `.noise-summary-cards`, `.noise-table`, `.noise-worst-performer`, etc. |

### Service Class Pattern (MUST follow exactly)

```python
class NoiseReportService:
    def __init__(self, host: str | None = None, port: int = 6333) -> None:
        self._host = host
        self._port = port
        self._client: QdrantClient | None = None

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(host=self._host, port=self._port)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
```

Route helpers (in `reports.py`):
```python
def _get_noise_report_service() -> NoiseReportService:
    return NoiseReportService(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )

def _get_audit_service() -> NotificationAuditService:
    return NotificationAuditService()
```

### Qdrant Patterns

**Cross-service feedback aggregation (new — do NOT filter by service):**
```python
INVESTIGATIONS_COLLECTION = "investigations"

def get_all_service_feedback(self) -> dict[str, dict[str, int]]:
    """Aggregate investigation feedback grouped by service."""
    per_service: dict[str, dict[str, int]] = {}
    offset = None
    while True:
        results, offset = self.client.scroll(
            collection_name=INVESTIGATIONS_COLLECTION,
            scroll_filter=None,  # ALL investigations
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in results:
            payload = point.payload or {}
            svc_name = payload.get("service")
            feedback = payload.get("investigation_feedback")
            if not svc_name or not feedback:
                continue
            if feedback not in ("accurate", "inaccurate", "not_an_issue"):
                continue
            if svc_name not in per_service:
                per_service[svc_name] = {"total": 0, "accurate": 0, "inaccurate": 0, "not_an_issue": 0}
            per_service[svc_name][feedback] += 1
            per_service[svc_name]["total"] += 1
        if offset is None:
            break
    return per_service
```

**For filtered queries (single service):** Use the same pattern from `AdaptiveThresholdService.get_service_feedback_summary()` with `Filter(must=[FieldCondition(key="service", match=MatchValue(value=service_name))])`.

**False page statistics:** Delegate to `NotificationAuditService.get_audit_statistics()` which uses `qdrant_client.count()` with filter conditions — already handles service and date range filters.

**False page trend:** Use `NotificationAuditService.query_audit()` with date range filters for each time bucket, or compute from paginated scroll of `notification_audit` collection with `timestamp_epoch` range queries.

### Signal-to-Noise Ratio Formula

```python
# Signal-to-noise ratio = accurate investigations / total investigations with feedback
# Per-service: accurate_count / (accurate_count + inaccurate_count + not_an_issue_count)
# Overall: sum(all accurate) / sum(all with feedback)

def _compute_signal_to_noise(accurate: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(accurate / total, 4)
```

### False Page Rate

```python
# False page rate = false_page_count / total_notifications
# Per-service: from get_audit_statistics(service=name)
# Overall: from get_audit_statistics(service=None)
# Already computed by NotificationAuditService.get_audit_statistics()
```

### Trend Data Pattern

```python
# Divide period into buckets (e.g., 30d = 6 buckets of 5 days each)
# For each bucket: get_audit_statistics(service, date_from=bucket_start, date_to=bucket_end)
# Return list of {period_label: str, false_page_rate: float, total: int}

PERIOD_CONFIG = {
    "7d": {"days": 7, "buckets": 7, "label_format": "%b %d"},
    "30d": {"days": 30, "buckets": 6, "label_format": "%b %d"},
    "90d": {"days": 90, "buckets": 6, "label_format": "%b %d"},
}
```

### Worst Performer Highlighting

```python
# Mark services with the highest false page rate as worst performers
# Strategy: any service with false_page_rate > 2x the average across all services
# OR: top N services by false_page_rate (whichever is more useful)
# Minimum: at least 1 notification to qualify (avoid division by zero edge cases)
```

### Route Pattern (follow SLO dashboard exactly)

```python
reports_bp = Blueprint("reports", __name__, url_prefix="/reports")

@reports_bp.route("/noise")
@require_role("user")  # AC#3: accessible to all SREs, not admin-only
def noise_report() -> str:
    service_filter = request.args.get("service")
    period = request.args.get("period", "30d")
    if period not in VALID_PERIODS:
        period = "30d"

    svc = _get_noise_report_service()
    audit_svc = _get_audit_service()
    try:
        report_data = svc.build_noise_report(
            audit_service=audit_svc,
            service=service_filter,
            period=period,
        )
        template_data = {
            "report": report_data,
            "selected_service": service_filter,
            "selected_period": period,
            "available_services": [s.service_name for s in report_data.per_service],
            "error_message": None,
        }
        if request.headers.get("HX-Request"):
            return render_template("reports/_noise_content.html", **template_data)
        return render_template("reports/noise.html", **template_data)
    except Exception as e:
        logger.exception("Failed to load noise report: %s", e)
        error_data = {
            "error_message": "Unable to load noise report data",
            "report": None,
            "selected_service": service_filter,
            "selected_period": period,
            "available_services": [],
        }
        if request.headers.get("HX-Request"):
            return render_template("reports/_noise_content.html", **error_data)
        return render_template("reports/noise.html", **error_data)
    finally:
        svc.close()
        audit_svc.close()
```

### HTMX Template Patterns

**Full page (`reports/noise.html`):**
```html
{% extends "base.html" %}
{% block title %}Noise Report - Beeper{% endblock %}
{% block content %}
<div class="card">
  <h2>Noise Report</h2>
  <p>Signal-to-noise ratio and false page trends across services.</p>
</div>
<div class="noise-filter-bar">
  <select name="service"
          hx-get="{{ url_for('reports.noise_report') }}"
          hx-target="#noise-content"
          hx-swap="innerHTML"
          hx-include="[name='period']">
    <option value="">All Services</option>
    {% for svc in available_services %}
    <option value="{{ svc }}" {% if svc == selected_service %}selected{% endif %}>{{ svc }}</option>
    {% endfor %}
  </select>
  <select name="period"
          hx-get="{{ url_for('reports.noise_report') }}"
          hx-target="#noise-content"
          hx-swap="innerHTML"
          hx-include="[name='service']">
    <option value="7d" {% if selected_period == "7d" %}selected{% endif %}>Last 7 Days</option>
    <option value="30d" {% if selected_period == "30d" %}selected{% endif %}>Last 30 Days</option>
    <option value="90d" {% if selected_period == "90d" %}selected{% endif %}>Last 90 Days</option>
  </select>
</div>
<div id="noise-content">
  {% include "reports/_noise_content.html" %}
</div>
{% endblock %}
```

**Content partial (`reports/_noise_content.html`):**
```html
{% if error_message %}
<div class="card error-card"><p class="error-text">{{ error_message }}</p></div>
{% elif report %}
<div class="noise-summary-cards">
  <div class="noise-summary-card">
    <div class="noise-summary-value">{{ (report.overall_signal_to_noise * 100)|round(1) }}%</div>
    <div class="noise-summary-label">Signal-to-Noise Ratio</div>
  </div>
  <div class="noise-summary-card">
    <div class="noise-summary-value">{{ (report.overall_false_page_rate * 100)|round(1) }}%</div>
    <div class="noise-summary-label">False Page Rate</div>
  </div>
  <div class="noise-summary-card">
    <div class="noise-summary-value">{{ report.total_investigations_with_feedback }}</div>
    <div class="noise-summary-label">Investigations with Feedback</div>
  </div>
  <div class="noise-summary-card">
    <div class="noise-summary-value">{{ report.total_notifications }}</div>
    <div class="noise-summary-label">Total Notifications</div>
  </div>
</div>
<!-- Per-service breakdown table -->
<div class="card">
  <h3>Per-Service Breakdown</h3>
  <table class="noise-table">
    <thead><tr>
      <th>Service</th><th>Investigations</th><th>Accurate</th><th>Inaccurate</th>
      <th>Not an Issue</th><th>S/N Ratio</th><th>False Page Rate</th>
    </tr></thead>
    <tbody>
    {% for svc in report.per_service %}
    <tr class="{% if svc.is_worst_performer %}noise-worst-performer{% endif %}">
      <td>{{ svc.service_name }}</td>
      <td>{{ svc.total_investigations }}</td>
      <td>{{ svc.accurate_count }}</td>
      <td>{{ svc.inaccurate_count }}</td>
      <td>{{ svc.not_an_issue_count }}</td>
      <td>{{ (svc.signal_to_noise_ratio * 100)|round(1) }}%</td>
      <td>{{ (svc.false_page_rate * 100)|round(1) }}%</td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
</div>
<!-- False Page Trend -->
{% if report.trend_data %}
<div class="card">
  <h3>False Page Rate Trend</h3>
  <div class="noise-trend-display">
    {% for point in report.trend_data %}
    <div class="noise-trend-point">
      <span class="noise-trend-label">{{ point.period_label }}</span>
      <span class="noise-trend-value">{{ (point.false_page_rate * 100)|round(1) }}%</span>
      <span class="noise-trend-count">({{ point.total }} notifications)</span>
    </div>
    {% endfor %}
  </div>
</div>
{% endif %}
{% else %}
<div class="card empty-state">
  <p class="text-muted">No investigation feedback recorded yet. Signal-to-noise data will appear as SREs provide feedback.</p>
  <a href="{{ url_for('investigations.list_investigations') }}" class="btn btn-secondary">View Investigations</a>
</div>
{% endif %}
```

### Permission Model

- `GET /reports/noise` → `@require_role("user")` (AC#3: "noise metrics benefit all SREs, not just admins")
- This is a **read-only** dashboard — no admin-only actions
- Follows precedent of `/notifications/audit` which is also `@require_role("user")`
- DIFFERENT from other Epic 3 settings pages which are admin-only for writes

### Critical Guardrails

- **No new pip dependencies** — use qdrant-client (existing), stdlib only
- **No Tailwind** — use existing `main.css` BEM classes (`.card`, `.badge`, `.table`)
- **No client-side JS** — HTMX handles all filter interaction
- **`os.getenv("QDRANT_HOST", "localhost")` always with default**
- **Service lifecycle** — always `try/finally: service.close()` for ALL service instances (noise report + audit)
- **Mock import paths must match where used** — e.g., `patch("beeper_ui.routes.reports._get_noise_report_service")`
- **Graceful degradation** — if Qdrant or audit service fails, render page with error message; never crash
- **New Blueprint** — create `reports_bp` at `/reports` prefix, register in `__init__.py`
- **No new Qdrant collections** — reads from existing `investigations` and `notification_audit` collections only
- **Ruff lint clean** on all new/modified files
- **Zero regressions** — run full UI test suite
- **Division-by-zero safety** — always check `total > 0` before computing ratios
- **Date range computation** — use `datetime.now(timezone.utc)` minus `timedelta(days=N)` for period boundaries; convert to ISO 8601 for `NotificationAuditService` date params
- **NotificationAuditService instantiation** — `NotificationAuditService()` takes no constructor args (host/port via `os.getenv` internally)
- **`_iso_to_epoch()` is a static method** on `NotificationAuditService` — reuse for any epoch conversions needed
- **Boolean bypass validation** — `isinstance(value, bool)` check before `isinstance(value, (int, float))` for any numeric input
- **Empty data handling** — if no feedback or audit data exists, show empty state, not errors

### Project Structure Notes

- New service: `ui/beeper_ui/services/noise_report_service.py`
- New routes: `ui/beeper_ui/routes/reports.py` (new Blueprint)
- Modified: `ui/beeper_ui/routes/__init__.py` (register `reports_bp`)
- New templates: `ui/beeper_ui/templates/reports/noise.html`, `ui/beeper_ui/templates/reports/_noise_content.html`
- Modified CSS: `ui/beeper_ui/static/css/main.css` (add noise report classes)
- New tests: `ui/tests/test_noise_report_service.py`, `ui/tests/test_noise_report_routes.py`
- Template directory `ui/beeper_ui/templates/reports/` must be created

### Previous Story Intelligence

**From Story 3-6 (Impact-Weighted Escalation Urgency):**
- SSE re-render path needed `urgency_scores={}` — noise report has no SSE, so no concern here
- `finally: svc.close()` was missed in code review — ensure ALL services have `finally: svc.close()`
- Added `logger.warning` to bare `except Exception` — do the same in noise report
- Follow service factory pattern: `_get_noise_report_service()` with `os.getenv` defaults

**From Story 3-5 (Adaptive Alert Threshold Tuning):**
- Code review caught unimplemented HTMX partial (Task 4.2) — verify ALL template partials exist and render correctly
- `get_service_feedback_summary()` in `AdaptiveThresholdService` is the exact pattern for reading feedback from investigations collection — reuse the scroll+filter+aggregate pattern
- `MIN_FEEDBACK_SAMPLE = 10` used for confidence assessment — noise report doesn't gate on minimum, it shows all available data

**From Story 3-4 (One-Click Investigation Feedback):**
- Feedback stored as `investigation_feedback` field in Qdrant `investigations` collection
- Values: `"accurate"`, `"inaccurate"`, `"not_an_issue"` (these are the exact strings)
- `investigation_feedback_at` (ISO 8601) for temporal analysis if needed

**From Story 2-6 (Notification Audit & False Page Tracking):**
- `NotificationAuditService` at `ui/beeper_ui/services/notification_audit_service.py` — has everything needed
- `get_audit_statistics()` returns `{total_notifications, false_page_count, false_page_rate}` — exactly what's needed per-service
- `query_audit()` supports `service`, `date_from`, `date_to`, `is_false_page` filters
- `_iso_to_epoch()` static method for date range queries
- `AUDIT_COLLECTION = "notification_audit"` — payload has `service`, `is_false_page`, `timestamp_epoch`

**From Story 1-7 (SLO Compliance Dashboard):**
- SLO dashboard is the closest existing analog — follow `slo.py` + `slo/dashboard.html` + `slo/_content.html` pattern exactly
- `_build_dashboard_data()` helper function pattern for data transformation
- HTMX detection pattern: `request.headers.get("HX-Request")`
- Error state rendering pattern: `error_data` dict with `error_message` key

### Git Intelligence

Recent commits: `MAESTRO: 3-6 done`, `MAESTRO: implement story 3-6 (Impact-Weighted Escalation Urgency)`. Follow commit pattern: `MAESTRO: implement story 3-7 (Noise Report Dashboard)`. Current test count: UI 1,328 passed. Investigator: 505 passed.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 3, Story 3.7] — User story, acceptance criteria
- [Source: _bmad-output/planning-artifacts/epics.md#FR20] — "Admins can view a noise report showing signal-to-noise ratio and false page trends"
- [Source: ui/beeper_ui/services/notification_audit_service.py] — NotificationAuditService, get_audit_statistics(), query_audit(), AUDIT_COLLECTION
- [Source: ui/beeper_ui/services/adaptive_threshold_service.py] — get_service_feedback_summary() pattern, INVESTIGATIONS_COLLECTION
- [Source: ui/beeper_ui/routes/slo.py] — SLO dashboard route pattern (closest analog)
- [Source: ui/beeper_ui/routes/__init__.py] — Blueprint registration
- [Source: ui/beeper_ui/templates/base.html] — Base template for extending
- [Source: ui/beeper_ui/middleware/permissions.py] — require_role decorator
- [Source: ui/beeper_ui/static/css/main.css] — Existing CSS classes
- [Source: _bmad-output/implementation-artifacts/3-6-impact-weighted-escalation-urgency.md] — Story 3-6 patterns
- [Source: _bmad-output/implementation-artifacts/3-5-adaptive-alert-threshold-tuning.md] — Story 3-5 patterns
- [Source: _bmad-output/implementation-artifacts/3-4-one-click-investigation-feedback.md] — Story 3-4 patterns

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- Fixed ruff import sorting (I001) in `routes/__init__.py` after adding `reports_bp` import
- Fixed ruff line length (E501) in `test_noise_report_routes.py` — wrapped long ternary expression

### Completion Notes List

- 56 new tests (37 service + 19 route), all passing
- Full UI test suite: 1,384 passed, zero regressions (up from 1,328)
- Ruff: all new/modified files clean
- AC#1 verified: dashboard at `/reports/noise` shows S/N ratio, false page rate, per-service breakdown, trend data
- AC#2 verified: service and period filters recalculate metrics; worst performers highlighted via 2x-average threshold
- AC#3 verified: `@require_role("user")` grants access to all SREs (test confirms both user and admin 200)
- Graceful degradation: Qdrant failures render error message instead of crashing
- Service lifecycle: all services closed in `finally` block
- HTMX partial support: `HX-Request` header detection returns partial without `<!DOCTYPE html>`

### File List

- `ui/beeper_ui/services/noise_report_service.py` (NEW) — NoiseReportService, ServiceNoiseStats, NoiseReportData dataclasses, feedback aggregation, false page stats, trend computation
- `ui/beeper_ui/routes/reports.py` (NEW) — reports_bp Blueprint, GET /reports/noise route with HTMX support, service/period filters, graceful error handling
- `ui/beeper_ui/routes/__init__.py` (MODIFIED) — registered reports_bp Blueprint
- `ui/beeper_ui/templates/reports/noise.html` (NEW) — full page template with filter bar
- `ui/beeper_ui/templates/reports/_noise_content.html` (NEW) — HTMX partial with summary cards, per-service table, trend display, empty state
- `ui/beeper_ui/static/css/main.css` (MODIFIED) — noise report CSS classes (.noise-summary-cards, .noise-table, .noise-worst-performer, .noise-filter-bar, .noise-trend-display)
- `ui/tests/test_noise_report_service.py` (NEW) — 37 unit tests
- `ui/tests/test_noise_report_routes.py` (NEW) — 19 route tests
