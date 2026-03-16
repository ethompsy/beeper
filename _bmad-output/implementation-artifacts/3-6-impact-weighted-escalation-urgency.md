# Story 3.6: Impact-Weighted Escalation Urgency

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the **system**,
I want to weight escalation urgency by confirmed customer impact rather than theoretical severity,
so that SREs are interrupted proportionally to actual user impact.

## Acceptance Criteria

1. **Given** an investigation with SLO context (burn_rate, budget_remaining) from Epic 1
   **When** escalation urgency is calculated
   **Then** urgency = f(burn_rate, budget_remaining, affected_users) — NOT static severity mapping
   **And** fast-burning SLO with 10% budget remaining escalates higher than slow-burning with 80% remaining

2. **Given** escalation urgency is calculated for a service with investigation feedback history
   **When** the service has a high "accurate" feedback rate (>80%)
   **Then** urgency is preserved as-is (trusted signal)
   **And** a service with <50% accurate rate has urgency dampened with a "low confidence" flag

3. **Given** the investigation list view
   **When** sorted by urgency
   **Then** impact-weighted urgency score is displayed alongside the investigation
   **And** tooltips explain the urgency calculation factors

## Tasks / Subtasks

- [x] Task 1: Create EscalationUrgencyService (AC: #1, #2)
  - [x] 1.1 Create `ui/beeper_ui/services/escalation_urgency_service.py` following `AdaptiveThresholdService` pattern (lazy QdrantClient, `close()`)
  - [x] 1.2 Define `@dataclass UrgencyScore` with fields: `score` (float 0-100), `confidence` (str: "high"/"moderate"/"low"/"unknown"), `low_confidence` (bool), `factors` (dict: burn_rate_component, budget_component, severity_component, customer_impact_boost, confidence_dampening), `service_name` (str), `investigation_id` (str), `has_slo_data` (bool)
  - [x] 1.3 Define urgency weight constants: `BURN_RATE_WEIGHT = 0.40`, `BUDGET_WEIGHT = 0.35`, `SEVERITY_WEIGHT = 0.25`, severity scores map, `CUSTOMER_IMPACT_BOOST = 1.2`, `LOW_CONFIDENCE_DAMPENING = 0.7`, `ACCURATE_HIGH_RATE = 0.8`, `ACCURATE_LOW_RATE = 0.5`, `MIN_FEEDBACK_FOR_CONFIDENCE = 10`
  - [x] 1.4 Implement `get_service_accuracy_rate(service_name)` — Qdrant scroll + aggregate feedback
  - [x] 1.5 Implement `calculate_urgency(...)` — pure calculation with SLO weighting, customer impact boost, confidence dampening
  - [x] 1.6 Implement `compute_batch_urgency(...)` — batch computation with per-service accuracy caching
  - [x] 1.7 Define `EscalationUrgencyError(Exception)` for Qdrant failures
  - [x] 1.8 Add `default()` classmethod to `UrgencyScore` for fallback scores

- [x] Task 2: Add urgency computation to investigation list route (AC: #1, #3)
  - [x] 2.1 Add `_get_urgency_service()` factory helper in `investigations.py`
  - [x] 2.2 Add `_get_slo_service()` factory helper in `investigations.py`
  - [x] 2.3 Modify `list_investigations()` route with urgency computation, `?sort=urgency` support, `urgency_scores` passed to template
  - [x] 2.4 Ensure SLO/urgency failures are graceful — degraded mode renders list without urgency

- [x] Task 3: Add urgency to investigation detail view (AC: #1, #2, #3)
  - [x] 3.1 Add `GET /investigations/<investigation_id>/urgency` route — returns `_urgency_card.html` HTMX partial
  - [x] 3.2 Route fetches: SLO budget, investigation findings, computes single urgency score
  - [x] 3.3 Pass `urgency_score` (UrgencyScore) to template

- [x] Task 4: Create HTMX templates (AC: #3)
  - [x] 4.1 Modify `_list_content.html` — urgency column with badge, tooltip, low confidence warning
  - [x] 4.2 Create `_urgency_card.html` — urgency detail card with factors table
  - [x] 4.3 Modify `_detail_content.html` — HTMX lazy-load for urgency card
  - [x] 4.4 Add CSS urgency badge classes to `main.css`
  - [x] 4.5 Add sort-by-urgency option to `_filter_panel.html`

- [x] Task 5: Comprehensive testing (AC: #1, #2, #3)
  - [x] 5.1 Create `test_escalation_urgency_service.py` — 29 unit tests covering all urgency scenarios
  - [x] 5.2 Create `test_escalation_urgency_routes.py` — 10 route tests covering list, detail, degradation
  - [x] 5.3 Run full UI test suite — 1,326 passed, zero regressions
  - [x] 5.4 Run ruff lint on all new/modified files — all clean

## Dev Notes

### Architecture Patterns to Follow

**CRITICAL CONTEXT: This story adds impact-weighted urgency scoring that enriches investigations with SLO-derived urgency. It does NOT modify the Rust operator or investigator pipeline — it adds a UI-layer computation that combines existing SLO data (from operator API) with feedback accuracy (from Qdrant) to produce a composite urgency score.**

**What already exists (DO NOT recreate):**

| Component | Location | Status |
|-----------|----------|--------|
| `SloService` | `ui/beeper_ui/services/slo_service.py` | Done (Epic 1) |
| `get_service_budget(name)` | Returns `burn_rate`, `budget_remaining`, `condition` via operator API | Done |
| `InvestigationService` | `ui/beeper_ui/services/investigation_service.py` | Done (v0.1.0) |
| `get_investigation_findings(id)` | Returns Qdrant payload dict for investigation | Done |
| `Investigation` dataclass | `id`, `status`, `service`, `severity`, `condition`, `started_at` | Done |
| `AdaptiveThresholdService` | `ui/beeper_ui/services/adaptive_threshold_service.py` | Done (story 3-5) |
| `get_service_feedback_summary()` | Aggregates feedback from `investigations` collection | Done (reuse pattern) |
| `investigations_bp` Blueprint | `/investigations` URL prefix | Done (v0.1.0) |
| `get_investigation_service()` helper | Service factory in `investigations.py` | Done |
| `_list_content.html` template | Investigation table: Severity, Status, ID, Service, Condition, Started | Done |
| `_detail_content.html` template | Investigation detail with HTMX sections | Done |
| `_filter_panel.html` template | HTMX filter controls | Done |
| Investigation feedback fields | `investigation_feedback` ("accurate"/"inaccurate"/"not_an_issue") in Qdrant | Done (story 3-4) |
| `VALID_FEEDBACK_TYPES` | `{"accurate", "inaccurate", "not_an_issue"}` in `investigations.py` | Done |
| `customer_impacting` field | Boolean in investigation findings payload (from CustomerImpactStep) | Done (v0.1.0) |
| CSS classes | `.badge`, `.badge-{status}`, `.card`, `.table`, `.btn` in `main.css` | Done |

**What this story adds:**

| Component | Description |
|-----------|-------------|
| `EscalationUrgencyService` class | New service for urgency score computation with Qdrant feedback reads |
| `UrgencyScore` dataclass | Score (0-100), confidence level, factors breakdown, low_confidence flag |
| `GET /investigations/<id>/urgency` | HTMX partial route for urgency card on detail view |
| Urgency column in `_list_content.html` | Score badge + tooltip in investigation list table |
| `_urgency_card.html` template | HTMX partial: urgency score with factors breakdown |
| Sort-by-urgency in list view | `?sort=urgency` query param support |
| CSS urgency badge classes | `.urgency-critical`, `.urgency-high`, `.urgency-medium`, `.urgency-low` |

### Service Class Pattern (MUST follow exactly)

```python
class EscalationUrgencyService:
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

Route helpers (add to `investigations.py`):
```python
def _get_urgency_service() -> EscalationUrgencyService:
    return EscalationUrgencyService(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )

def _get_slo_service() -> SloService:
    return SloService(
        operator_url=current_app.config["OPERATOR_URL"],
        timeout=current_app.config.get("OPERATOR_TIMEOUT", 5.0),
    )
```

### Qdrant Patterns

**Reading feedback from `investigations` collection** (reuse pattern from `AdaptiveThresholdService`):
```python
INVESTIGATIONS_COLLECTION = "investigations"

def get_service_accuracy_rate(self, service_name: str) -> dict[str, Any]:
    results, _ = self.client.scroll(
        collection_name=INVESTIGATIONS_COLLECTION,
        scroll_filter=Filter(
            must=[FieldCondition(key="service", match=MatchValue(value=service_name))]
        ),
        limit=100,
        with_payload=True,
        with_vectors=False,
    )
    feedback_entries = [
        r for r in results
        if r.payload and r.payload.get("investigation_feedback")
    ]
    total = len(feedback_entries)
    accurate = sum(1 for e in feedback_entries if e.payload["investigation_feedback"] == "accurate")
    inaccurate = sum(1 for e in feedback_entries if e.payload["investigation_feedback"] == "inaccurate")
    not_an_issue = sum(1 for e in feedback_entries if e.payload["investigation_feedback"] == "not_an_issue")

    accurate_rate = accurate / total if total >= MIN_FEEDBACK_FOR_CONFIDENCE else None
    return {
        "accurate_rate": accurate_rate,
        "total_feedback": total,
        "accurate_count": accurate,
        "inaccurate_count": inaccurate,
        "not_an_issue_count": not_an_issue,
    }
```

### Urgency Algorithm (AC #1, #2)

```python
# Constants
BURN_RATE_WEIGHT = 0.40
BUDGET_WEIGHT = 0.35
SEVERITY_WEIGHT = 0.25
SEVERITY_SCORES = {"critical": 100, "high": 75, "medium": 50, "low": 25}
CUSTOMER_IMPACT_BOOST = 1.2
LOW_CONFIDENCE_DAMPENING = 0.7
ACCURATE_HIGH_RATE = 0.8
ACCURATE_LOW_RATE = 0.5
MIN_FEEDBACK_FOR_CONFIDENCE = 10

def calculate_urgency(self, ...) -> UrgencyScore:
    severity_score = SEVERITY_SCORES.get(severity, 50)

    if burn_rate is not None and budget_remaining is not None:
        # SLO-weighted urgency
        burn_rate_score = min(burn_rate / 5.0, 1.0) * 100
        budget_score = (1.0 - max(0.0, min(1.0, budget_remaining))) * 100
        base_urgency = (
            burn_rate_score * BURN_RATE_WEIGHT
            + budget_score * BUDGET_WEIGHT
            + severity_score * SEVERITY_WEIGHT
        )
        has_slo_data = True
    else:
        # Severity-only fallback
        base_urgency = severity_score
        burn_rate_score = 0.0
        budget_score = 0.0
        has_slo_data = False

    # Customer impact boost
    customer_impact_applied = False
    if customer_impacting:
        base_urgency = min(base_urgency * CUSTOMER_IMPACT_BOOST, 100.0)
        customer_impact_applied = True

    # Confidence dampening (AC #2)
    accurate_rate = accuracy_data.get("accurate_rate")
    confidence_dampening_applied = False
    if accurate_rate is not None:
        if accurate_rate >= ACCURATE_HIGH_RATE:
            confidence = "high"
        elif accurate_rate < ACCURATE_LOW_RATE:
            confidence = "low"
            base_urgency *= LOW_CONFIDENCE_DAMPENING
            confidence_dampening_applied = True
        else:
            confidence = "moderate"
    else:
        confidence = "unknown"

    return UrgencyScore(
        score=round(base_urgency, 1),
        confidence=confidence,
        low_confidence=(confidence == "low"),
        factors={
            "burn_rate_component": round(burn_rate_score * BURN_RATE_WEIGHT, 1) if has_slo_data else 0.0,
            "budget_component": round(budget_score * BUDGET_WEIGHT, 1) if has_slo_data else 0.0,
            "severity_component": round(severity_score * SEVERITY_WEIGHT, 1) if has_slo_data else severity_score,
            "customer_impact_boost": customer_impact_applied,
            "confidence_dampening": confidence_dampening_applied,
        },
        service_name=service_name,
        investigation_id=investigation_id,
        has_slo_data=has_slo_data,
    )
```

### SLO Data Access Pattern

```python
# SloService uses httpx to call operator API
# get_service_budget(name) returns dict | None
# Fields: burn_rate (float), budget_remaining (float 0.0-1.0), condition (str)
# Returns None if service has no SLO configured (404)

from beeper_ui.services.slo_service import SloService, SloServiceError

slo_service = SloService(
    operator_url=current_app.config["OPERATOR_URL"],
    timeout=current_app.config.get("OPERATOR_TIMEOUT", 5.0),
)
try:
    budget = slo_service.get_service_budget(service_name)
    # budget may be None (no SLO), or dict with burn_rate, budget_remaining
except SloServiceError:
    budget = None  # Graceful degradation
finally:
    slo_service.close()
```

### List View Enrichment Pattern

```python
# In list_investigations route handler:
investigations = inv_service.list_investigations(status=status, service=service, severity=severity)

# Batch urgency computation
urgency_scores = {}
try:
    # Collect unique services
    services = {inv.service for inv in investigations}

    # Fetch SLO budgets per service (one HTTP call each)
    slo_budgets = {}
    for svc in services:
        try:
            slo_budgets[svc] = slo_service.get_service_budget(svc)
        except SloServiceError:
            slo_budgets[svc] = None

    # Fetch findings per investigation (one Qdrant call each)
    findings_map = {}
    for inv in investigations:
        try:
            findings_map[inv.id] = inv_service.get_investigation_findings(inv.id)
        except Exception:
            findings_map[inv.id] = {}

    # Compute batch urgency
    urgency_scores = urgency_service.compute_batch_urgency(
        investigations, slo_budgets, findings_map,
    )
except EscalationUrgencyError:
    pass  # Degrade gracefully — render without urgency

# Sort by urgency if requested
sort_by = request.args.get("sort")
if sort_by == "urgency" and urgency_scores:
    investigations.sort(
        key=lambda inv: urgency_scores.get(inv.id, UrgencyScore.default()).score,
        reverse=True,
    )

# Pass to template
return render_template(
    "investigations/_list_content.html" if hx_request else "investigations/list.html",
    investigations=investigations,
    urgency_scores=urgency_scores,
    selected_sort=sort_by,
    ...
)
```

### HTMX Template Patterns

**Urgency column in `_list_content.html`:**
```html
<!-- Add column header after Severity -->
<th>Urgency</th>

<!-- Add cell in row -->
<td>
  {% set urgency = urgency_scores.get(inv.id) if urgency_scores else None %}
  {% if urgency %}
    {% if urgency.score > 80 %}
      {% set urgency_level = "critical" %}
    {% elif urgency.score > 60 %}
      {% set urgency_level = "high" %}
    {% elif urgency.score > 40 %}
      {% set urgency_level = "medium" %}
    {% else %}
      {% set urgency_level = "low" %}
    {% endif %}
    <span class="badge urgency-{{ urgency_level }}"
          title="Burn rate: {{ urgency.factors.burn_rate_component }} | Budget: {{ urgency.factors.budget_component }} | Severity: {{ urgency.factors.severity_component }}{% if urgency.factors.customer_impact_boost %} | Customer impact boost{% endif %}{% if urgency.factors.confidence_dampening %} | Dampened (low confidence){% endif %}">
      {{ urgency.score|round(0)|int }}
    </span>
    {% if urgency.low_confidence %}
      <span class="badge badge-warning" title="Low feedback accuracy (&lt;50%) — urgency dampened">low confidence</span>
    {% endif %}
  {% else %}
    —
  {% endif %}
</td>
```

**Urgency card partial (`_urgency_card.html`):**
```html
{% if error_message %}
<div class="card error-card"><p class="error-text">{{ error_message }}</p></div>
{% elif urgency %}
<div class="card">
  <h3>Escalation Urgency</h3>
  <div class="urgency-score-display">
    {% if urgency.score > 80 %}{% set level = "critical" %}
    {% elif urgency.score > 60 %}{% set level = "high" %}
    {% elif urgency.score > 40 %}{% set level = "medium" %}
    {% else %}{% set level = "low" %}{% endif %}
    <span class="badge urgency-{{ level }} urgency-large">{{ urgency.score|round(0)|int }}</span>
    <span class="badge badge-{{ urgency.confidence }}">{{ urgency.confidence }} confidence</span>
    {% if urgency.low_confidence %}
    <span class="badge badge-warning">Urgency dampened — low feedback accuracy</span>
    {% endif %}
  </div>
  {% if not urgency.has_slo_data %}
  <p class="text-muted">No SLO data available — using severity-only scoring.</p>
  {% endif %}
  <table class="table table-sm">
    <thead><tr><th>Factor</th><th>Score</th></tr></thead>
    <tbody>
      <tr><td>Burn Rate</td><td>{{ urgency.factors.burn_rate_component }}</td></tr>
      <tr><td>Budget Remaining</td><td>{{ urgency.factors.budget_component }}</td></tr>
      <tr><td>Severity</td><td>{{ urgency.factors.severity_component }}</td></tr>
      {% if urgency.factors.customer_impact_boost %}
      <tr><td>Customer Impact</td><td>+20% boost</td></tr>
      {% endif %}
      {% if urgency.factors.confidence_dampening %}
      <tr><td>Confidence Dampening</td><td>-30% (low accuracy)</td></tr>
      {% endif %}
    </tbody>
  </table>
</div>
{% else %}
<div class="card"><p>Urgency score unavailable.</p></div>
{% endif %}
```

### Permission Model

- `GET /investigations/` (list with urgency) → no auth required (existing, unchanged)
- `GET /investigations/<id>/urgency` → no auth required (read-only enrichment, consistent with existing detail routes)
- Urgency is read-only data — no admin actions needed

### Critical Guardrails

- **No new pip dependencies** — use qdrant-client (existing), httpx (existing SloService), stdlib only
- **No Tailwind** — use existing `main.css` BEM classes (`.card`, `.badge`, `.btn`, `.table`)
- **No client-side JS** — HTMX handles all interaction
- **Boolean bypass validation** — `isinstance(value, bool)` check before `isinstance(value, (int, float))` for any numeric input
- **Service lifecycle** — always `try/finally: service.close()` for ALL service instances (urgency, SLO, investigation)
- **`os.getenv("QDRANT_HOST", "localhost")` always with default**
- **Mock import paths must match where used** — e.g., `patch("beeper_ui.routes.investigations._get_urgency_service")`
- **Graceful degradation** — if SloService or urgency computation fails, render investigation list without urgency column data; never crash the list view
- **No new Blueprints** — add urgency route to existing `investigations_bp`
- **No new Qdrant collections** — reads from existing `investigations` collection only
- **Ruff lint clean** on all new/modified files
- **Zero regressions** — run full UI test suite
- **Cap urgency at 100** — after all boosts/multipliers, clamp to 0-100 range
- **SLO budget values** — `budget_remaining` is 0.0-1.0 fraction (not percentage); `burn_rate` is multiplier (>1.0 means burning faster than sustainable)
- **Existing `_list_content.html` SSE swap** — the investigation list refreshes via SSE; ensure `urgency_scores` is available in the SSE re-render path too (pass through `_generate_sse_events`)

### Project Structure Notes

- New service: `ui/beeper_ui/services/escalation_urgency_service.py`
- Modified routes: `ui/beeper_ui/routes/investigations.py` (add urgency computation to list, add urgency detail route, add service factory helpers)
- New templates: `ui/beeper_ui/templates/investigations/_urgency_card.html`
- Modified templates: `ui/beeper_ui/templates/investigations/_list_content.html` (add urgency column), `ui/beeper_ui/templates/investigations/_detail_content.html` (add HTMX urgency card), `ui/beeper_ui/templates/investigations/_filter_panel.html` (add sort-by-urgency)
- Modified CSS: `ui/beeper_ui/static/css/main.css` (add urgency badge classes)
- New tests: `ui/tests/test_escalation_urgency_service.py`, `ui/tests/test_escalation_urgency_routes.py`
- No changes to `routes/__init__.py` (using existing `investigations_bp`)

### Previous Story Intelligence

**From Story 3-5 (Adaptive Alert Threshold Tuning):**
- `get_service_feedback_summary()` in `AdaptiveThresholdService` reads feedback from investigations collection — reuse exact same Qdrant scroll+filter pattern for `get_service_accuracy_rate()`
- `MIN_FEEDBACK_SAMPLE = 10` — reuse same threshold for confidence assessment
- Code review caught unimplemented HTMX partial (Task 4.2) — verify ALL template partials exist
- Code review caught operation ordering bug — ensure any multi-step operations are atomic or ordered correctly

**From Story 3-4 (One-Click Investigation Feedback):**
- Feedback stored as `investigation_feedback` field in Qdrant `investigations` collection
- `VALID_FEEDBACK_TYPES = {"accurate", "inaccurate", "not_an_issue"}`
- SSE `feedback-update` event for real-time cross-viewer updates

**From Story 3-2 (Confidence Gate Engine):**
- `normalize_confidence_score()` in `confidence_gate_service.py` — could be relevant if urgency needs to incorporate confidence scores from gate evaluation
- Boolean bypass pattern: always check for `bool` type before numeric comparison

**From Story 3-1 (Trust Level Configuration):**
- `TrustLevelService.get_effective_trust_level()` — available if urgency ever needs trust-level weighting
- Per-service records in `service_trust_levels` collection with prefixed field names

### Git Intelligence

Recent commits: `MAESTRO: 3-5 done`, `MAESTRO: implement story 3-5 (Adaptive Alert Threshold Tuning)`. Follow commit pattern: `MAESTRO: implement story 3-6 (Impact-Weighted Escalation Urgency)`. Current test count: UI 1,287 passed. Investigator: 517 passed, 3 skipped.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 3, Story 3.6] — User story, acceptance criteria
- [Source: _bmad-output/planning-artifacts/epics.md#FR21] — "Impact-weighted escalation urgency"
- [Source: _bmad-output/planning-artifacts/epics.md#FR4] — "Score anomalies by customer impact using SLO data"
- [Source: ui/beeper_ui/services/slo_service.py] — SloService, get_service_budget(), format functions
- [Source: ui/beeper_ui/services/investigation_service.py] — InvestigationService, get_investigation_findings(), Investigation dataclass
- [Source: ui/beeper_ui/services/adaptive_threshold_service.py] — Feedback aggregation pattern, get_service_feedback_summary()
- [Source: ui/beeper_ui/routes/investigations.py] — investigations_bp, list route, SSE, validation patterns
- [Source: ui/beeper_ui/templates/investigations/_list_content.html] — Current table columns
- [Source: ui/beeper_ui/templates/investigations/_detail_content.html] — Detail view HTMX sections
- [Source: ui/beeper_ui/templates/investigations/_filter_panel.html] — Filter controls
- [Source: ui/beeper_ui/static/css/main.css] — Existing CSS classes
- [Source: ui/beeper_ui/middleware/permissions.py] — require_role decorator
- [Source: _bmad-output/implementation-artifacts/3-5-adaptive-alert-threshold-tuning.md] — Story 3-5 patterns
- [Source: _bmad-output/implementation-artifacts/3-4-one-click-investigation-feedback.md] — Story 3-4 patterns

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- Fixed ruff import sorting (I001) in `investigations.py` after adding new imports
- Fixed Qdrant client property mocking — direct `self.service._client = self.mock_client` injection instead of property mock
- Fixed escape sequence warning `"\u2014"` → `"&mdash;"` in route tests
- Fixed unused imports (F401) in `test_escalation_urgency_service.py` via `ruff --fix`
- Added `_mock_urgency_deps` autouse fixture to existing `TestInvestigationsRoute` and `TestDetailSSEEventGeneration` classes to prevent regressions from new SLO/urgency service dependencies

### Completion Notes List

- 39 new tests (29 service + 10 route), all passing
- Full UI test suite: 1,326 passed, zero regressions (up from 1,287)
- Ruff: all new/modified files clean
- Urgency formula satisfies AC#1: fast-burning 10% budget scores higher than slow-burning 80% budget (verified by test)
- AC#2 verified: >80% accuracy preserves urgency, <50% dampens by 0.7x with low_confidence flag
- Graceful degradation: SloService or urgency failures render list without urgency data

### File List

- `ui/beeper_ui/services/escalation_urgency_service.py` (NEW) — EscalationUrgencyService, UrgencyScore dataclass, urgency calculation
- `ui/beeper_ui/routes/investigations.py` (MODIFIED) — urgency computation in list route, `GET /<id>/urgency` detail route, `_get_slo_service()` / `_get_urgency_service()` helpers
- `ui/beeper_ui/templates/investigations/_urgency_card.html` (NEW) — HTMX partial for urgency detail card
- `ui/beeper_ui/templates/investigations/_list_content.html` (MODIFIED) — urgency column with badge + tooltip
- `ui/beeper_ui/templates/investigations/_detail_content.html` (MODIFIED) — HTMX lazy-load for urgency card
- `ui/beeper_ui/templates/investigations/_filter_panel.html` (MODIFIED) — sort-by-urgency dropdown
- `ui/beeper_ui/static/css/main.css` (MODIFIED) — urgency badge CSS classes
- `ui/tests/test_escalation_urgency_service.py` (NEW) — 29 unit tests
- `ui/tests/test_escalation_urgency_routes.py` (NEW) — 10 route tests
- `ui/tests/test_investigation_routes.py` (MODIFIED) — added `_mock_urgency_deps` autouse fixture for regression prevention
