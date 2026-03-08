# Story 6.2: LLM Spending Caps

Status: review

## Story

As an **Admin**,
I want to set spending caps and rate limits for LLM usage,
so that I can control costs and prevent runaway spending.

## Acceptance Criteria

1. **Given** I access the Admin settings, **When** I configure LLM spending controls, **Then** I can set (FR46):
   - Daily spending cap (e.g., $50/day)
   - Monthly spending cap (e.g., $500/month)
   - Rate limit (e.g., max 100 investigations/hour)

2. **Given** spending caps are configured, **When** the cap is approached (80% threshold), **Then** a warning is logged **And** the Admin is notified (via UI alert on the spending dashboard).

3. **Given** spending cap is reached, **When** a new investigation would exceed the cap, **Then** investigation is queued or deprioritized **And** only critical/high-severity investigations proceed **And** clear messaging indicates cap enforcement.

4. **Given** rate limits are configured, **When** investigation rate exceeds limit, **Then** new investigations are throttled **And** backpressure is applied gracefully.

5. **Given** caps are enforced, **When** I view the Admin dashboard, **Then** I see:
   - Current spend vs. cap (progress bar)
   - Projected spend for period
   - Rate of consumption

## Tasks / Subtasks

- [x] Task 1: Add LLM cost tracking to LlmClient (AC: 1, 2, 5)
  - [x]1.1 Create `investigator/beeper_investigator/llm/cost.py` with `LLM_PRICING` dict mapping model names to input/output cost per 1M tokens, a `calculate_call_cost(model, prompt_tokens, completion_tokens) -> float` function, and a `CostTracker` class that accumulates costs with `record_call()`, `get_daily_spend()`, `get_monthly_spend()`, `reset_daily()`, `reset_monthly()` methods
  - [x]1.2 Modify `LlmClient.complete()` and `LlmClient.complete_sync()` in `client.py` to extract `response.usage.prompt_tokens` and `response.usage.completion_tokens` from LiteLLM responses, call `CostTracker.record_call()` to track cost per call, and store cumulative cost data accessible via a new `get_cost_stats() -> dict` method
  - [x]1.3 Add `cost_tracker: CostTracker` attribute to `LlmClient.__init__()` initialized from config; propagate cost stats in `InvestigatorAgent.run()` alongside existing `model_usage` and `cache_stats` metadata via `result.metadata["cost_stats"]`

- [x] Task 2: Implement spending cap enforcement (AC: 1, 3, 4)
  - [x]2.1 Create `investigator/beeper_investigator/llm/spending_cap.py` with `SpendingCapConfig` dataclass (daily_cap_cents, monthly_cap_cents, warning_threshold=0.8, rate_limit_per_hour, enforcement_mode, priority_severities) loaded from env vars (`BEEPER_LLM_DAILY_CAP_CENTS`, `BEEPER_LLM_MONTHLY_CAP_CENTS`, etc.)
  - [x]2.2 Add `SpendingCapEnforcer` class with methods: `check_budget(severity: str) -> CapCheckResult` (returns allow/warn/deny with reason), `check_rate_limit() -> bool`, `record_investigation()` for rate tracking
  - [x]2.3 Integrate into `InvestigatorAgent._initialize()` — before running steps, call `enforcer.check_budget(context.severity)`. If denied and severity not in priority list, set status to "capped" and return early with appropriate `InvestigationResult`. If warning threshold reached, log warning.
  - [x]2.4 Add `CapCheckResult` dataclass with `allowed: bool`, `reason: str`, `warning: bool`, `spend_pct: float` fields

- [x] Task 3: Create spending dashboard service (AC: 5)
  - [x]3.1 Create `ui/beeper_ui/services/spending_service.py` with `SpendingService` class — queries Qdrant `investigations` collection for `cost_stats` payload data, aggregates spend by day/month from investigation `created_at` timestamps and `cost_stats.total_cost` values
  - [x]3.2 Add `get_spending_summary() -> dict` — returns current daily spend, monthly spend, configured caps (from env vars), spend percentages, projected spend (extrapolate from rate), rate of consumption (investigations/hour over last hour)
  - [x]3.3 Add `get_spending_trend(period: str) -> list[dict]` — daily or weekly spend trend data for SVG chart rendering
  - [x]3.4 Add `get_cap_status() -> dict` — returns enforcement state (active/inactive), warnings list, capped investigation count

- [x] Task 4: Create spending dashboard routes and templates (AC: 1, 2, 5)
  - [x]4.1 Create `ui/beeper_ui/routes/spending.py` with `spending_bp = Blueprint("spending", __name__, url_prefix="/spending")` — follow metrics blueprint pattern exactly
  - [x]4.2 Add `GET /spending/` route — renders full spending dashboard page with spend vs cap progress bars, spend trend SVG chart, rate of consumption, cap enforcement status. Support HTMX partial via `HX-Request` header check.
  - [x]4.3 Add `GET /spending/status` HTMX partial route — returns `_spending_status.html` with current spend stats for auto-refresh
  - [x]4.4 Create `ui/beeper_ui/templates/spending/spending.html` — extends `base.html`, full page with: spend vs cap progress bars (daily + monthly), SVG trend chart (reuse `_compute_chart_data` pattern from metrics), rate consumption indicator, cap enforcement alerts, capped investigations list
  - [x]4.5 Create `ui/beeper_ui/templates/spending/_spending_content.html` — HTMX partial with dashboard content: progress bars using CSS (`.spending-progress-bar`, `.spending-progress-fill`), inline SVG spend trend, warning/cap alerts
  - [x]4.6 Register `spending_bp` in `ui/beeper_ui/routes/__init__.py`
  - [x]4.7 Add "Spending" link to `ui/beeper_ui/templates/base.html` nav (after "Metrics")

- [x] Task 5: Add CSS styles for spending dashboard (AC: 5)
  - [x]5.1 Add to `ui/beeper_ui/static/css/main.css`: `.spending-progress-bar` container, `.spending-progress-fill` with color transitions (green < 60%, yellow 60-80%, orange 80-95%, red > 95%), `.spending-cap-alert` warning banner, `.spending-summary-cards` grid, `.spending-rate-indicator`, `.cap-status-badge` (active/inactive/warning)

- [x] Task 6: Tests (AC: 1, 2, 3, 4, 5)
  - [x]6.1 Create `investigator/tests/test_spending_caps.py` — test CostTracker: record_call accumulates costs, get_daily_spend/get_monthly_spend return correct totals, reset clears appropriately
  - [x]6.2 Test `calculate_call_cost()` with known pricing for different models
  - [x]6.3 Test `SpendingCapEnforcer.check_budget()` — allows when under cap, warns at 80%, denies when over cap
  - [x]6.4 Test `SpendingCapEnforcer.check_budget()` — allows critical/high severity even when over cap
  - [x]6.5 Test `SpendingCapEnforcer.check_rate_limit()` — allows when under limit, denies when over
  - [x]6.6 Test LlmClient cost tracking integration — verify `complete_sync()` extracts token usage and records cost
  - [x]6.7 Create `ui/tests/test_spending.py` — test SpendingService with mock Qdrant data
  - [x]6.8 Test `GET /spending/` renders full page with progress bars
  - [x]6.9 Test `GET /spending/` with HX-Request returns partial
  - [x]6.10 Test `GET /spending/status` returns spending status partial
  - [x]6.11 Test spending dashboard with Qdrant unavailable — shows error card gracefully
  - [x]6.12 Test SpendingCapConfig loads from environment variables with defaults

- [x] Task 7: Integration verification (AC: 1, 2, 3, 4, 5)
  - [x]7.1 Run `ruff check` on all new/modified Python files — fix any issues
  - [x]7.2 Run `mypy` on all new/modified Python files — fix any issues
  - [x]7.3 Run full Python test suite — verify zero regressions
  - [x]7.4 Verify navigation link appears in base template
  - [x]7.5 Verify progress bars render with mock data (template inspection)

## Dev Notes

### Architecture Decision: Cost Tracking in LlmClient + SpendingCapEnforcer in Agent

The cost tracking is added directly to `LlmClient` since it already tracks model usage counts. The `CostTracker` accumulates actual dollar costs based on token usage from LiteLLM responses. The `SpendingCapEnforcer` is a separate class integrated at the agent level in `_initialize()` — this keeps cost policy enforcement decoupled from the LLM client itself.

### LLM Cost Data Flow

1. `LlmClient.complete_sync()` calls LiteLLM → extracts `response.usage.prompt_tokens`, `response.usage.completion_tokens`
2. `CostTracker.record_call(model, prompt_tokens, completion_tokens)` calculates and accumulates cost
3. `InvestigatorAgent.run()` calls `llm_client.get_cost_stats()` → stores in `result.metadata["cost_stats"]`
4. Cost stats persisted to Qdrant alongside existing `model_usage` and `cache_stats`
5. `SpendingService` reads cost data from Qdrant for dashboard display

### LLM Pricing Table

```python
LLM_PRICING: dict[str, dict[str, float]] = {
    # Anthropic models (per 1M tokens)
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    "claude-haiku-3.5": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    # OpenAI models (per 1M tokens)
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}
```

Costs stored in cents internally (multiply by 100) to avoid floating-point issues. Unknown models default to 0 cost (logged as warning).

### Spending Cap Configuration (Environment Variables)

```bash
BEEPER_LLM_DAILY_CAP_CENTS=5000          # $50.00 daily cap
BEEPER_LLM_MONTHLY_CAP_CENTS=50000       # $500.00 monthly cap
BEEPER_LLM_CAP_WARNING_THRESHOLD=0.8     # Warn at 80% of cap
BEEPER_INVESTIGATION_RATE_LIMIT=100       # Max investigations per hour
BEEPER_CAP_PRIORITY_SEVERITIES=high,critical  # Bypass cap for these
```

When caps are not configured (env vars not set), enforcement is disabled — all investigations proceed normally.

### Cap Enforcement Integration Point

In `InvestigatorAgent._initialize()`, after existing connectivity checks:

```python
# Check spending cap (Story 6-2)
if self.spending_enforcer:
    check = self.spending_enforcer.check_budget(self.context.severity)
    if check.warning:
        logger.warning("Spending cap warning: %s (%.1f%% of cap)", check.reason, check.spend_pct)
    if not check.allowed:
        logger.warning("Investigation capped: %s", check.reason)
        self.status_updater.set_failed(f"Spending cap reached: {check.reason}")
        raise RuntimeError(f"Spending cap enforcement: {check.reason}")
```

The `SpendingCapEnforcer` is optional — initialized only when cap env vars are set. This keeps existing behavior unchanged when caps aren't configured.

### Rate Limiting Approach

Simple sliding window counter: track investigation timestamps in a deque, count entries within the last `rate_limit_window_seconds` (default 3600). No external dependencies — in-memory tracking scoped to the pod lifecycle (same as cache).

### Dashboard Visualization Pattern

Follow the metrics blueprint pattern exactly:
- **Progress bars**: CSS-only with color transitions based on percentage (green → yellow → orange → red)
- **Spend trend**: Server-rendered inline SVG (reuse `_compute_chart_data` pattern)
- **HTMX**: `hx-get` for partial updates, `HX-Request` header check for full vs partial rendering
- **Error handling**: Graceful error card when Qdrant is unavailable

### Existing Code to Reuse (DO NOT RECREATE)

| Component | Location | What to Reuse |
|-----------|----------|---------------|
| LlmClient model tracking | `llm/client.py:179,268-270,328-330` | `_model_usage` dict pattern, extend for cost |
| Cache stats pattern | `llm/client.py:452-454` | `get_cache_stats()` → model for `get_cost_stats()` |
| Agent metadata propagation | `agent.py:84-85` | `result.metadata["model_usage"]` pattern |
| MetricsService Qdrant scroll | `metrics_service.py:41-72` | Scroll + cache pattern for SpendingService |
| Metrics blueprint pattern | `routes/metrics.py` | Blueprint structure, validation, error handling |
| SVG chart computation | `routes/metrics.py:94-159` | `_compute_chart_data()` for spend trend |
| Blueprint registration | `routes/__init__.py` | Follow pattern for spending_bp |
| CSS bar patterns | `main.css` | `.category-bars`, `.category-bar-track`, `.category-bar-fill` |
| Card/badge patterns | `main.css` | `.card`, `.service-badge`, `.status-badge` |
| Flask test patterns | `ui/tests/test_metrics.py` | Mock patterns, fixtures |
| Qdrant mock pattern | `ui/tests/test_metrics.py` | `MagicMock` for Qdrant |

### Anti-Patterns to Avoid

- **DO NOT** modify `complete_sync()` signature — add cost tracking internally, not as new params
- **DO NOT** use external rate limiting libraries — simple deque-based sliding window is sufficient
- **DO NOT** store caps in a database — env vars are the config source (consistent with all other config)
- **DO NOT** add JavaScript — progress bars use pure CSS width + transitions
- **DO NOT** create a separate CSS file — add styles to existing `main.css`
- **DO NOT** use `float` for money — use integer cents internally
- **DO NOT** block on rate limit check — return immediately with deny/allow
- **DO NOT** modify existing investigation step code — cost tracking is transparent in LlmClient
- **DO NOT** add new Qdrant collections — read/write to existing `investigations` collection
- **DO NOT** use async — Flask routes and spending checks are synchronous

### Project Structure Notes

**New files:**
- `investigator/beeper_investigator/llm/cost.py` — LLM pricing, CostTracker, calculate_call_cost
- `investigator/beeper_investigator/llm/spending_cap.py` — SpendingCapConfig, SpendingCapEnforcer, CapCheckResult
- `ui/beeper_ui/services/spending_service.py` — SpendingService for dashboard data
- `ui/beeper_ui/routes/spending.py` — spending_bp Blueprint
- `ui/beeper_ui/templates/spending/spending.html` — Full spending dashboard page
- `ui/beeper_ui/templates/spending/_spending_content.html` — HTMX partial content
- `investigator/tests/test_spending_caps.py` — Cost tracking + cap enforcement tests
- `ui/tests/test_spending.py` — Spending dashboard tests

**Modified files:**
- `investigator/beeper_investigator/llm/client.py` — Add CostTracker integration to complete/complete_sync
- `investigator/beeper_investigator/agent.py` — Add SpendingCapEnforcer check in _initialize, propagate cost_stats
- `ui/beeper_ui/routes/__init__.py` — Register spending_bp
- `ui/beeper_ui/templates/base.html` — Add Spending nav link
- `ui/beeper_ui/static/css/main.css` — Add spending dashboard styles

### Previous Story Intelligence (from 6-1)

**From 6-1 (MTTR Trends Dashboard):**
- MetricsService + metrics Blueprint pattern established — follow exactly for SpendingService + spending Blueprint
- Server-rendered inline SVG for charts (no JS) — reuse `_compute_chart_data()` pattern
- HTMX filtering with `hx-get` + `hx-target` — follow same pattern
- Input validation with regex patterns — reuse SERVICE_NAME_PATTERN, etc.
- Qdrant scroll with caching per service instance — follow `_cached_points` pattern
- Error card pattern for Qdrant unavailability — reuse exactly
- Code review lessons: validate all inputs, sanitize error messages, cache scroll results, log exceptions

**From 3-9 (Tiered Model Selection):**
- `select_model(tier)` returns model strings — cost calculation needs these model names
- `_model_usage` dict tracks call counts — extend pattern for cost tracking

**From 3-10 (LLM Response Caching):**
- Cached calls tracked with `(cached)` suffix — cached calls have zero additional cost
- Cache stats already propagated to Qdrant — follow same pattern for cost stats

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 6, Story 6.2]
- [Source: investigator/beeper_investigator/llm/client.py — LlmClient, complete_sync, model_usage tracking]
- [Source: investigator/beeper_investigator/agent.py:84-85 — model_usage/cache_stats propagation]
- [Source: ui/beeper_ui/services/metrics_service.py — MetricsService Qdrant scroll pattern]
- [Source: ui/beeper_ui/routes/metrics.py — Blueprint pattern, input validation, chart computation]
- [Source: ui/beeper_ui/templates/metrics/ — SVG chart, HTMX filtering, error card patterns]
- [Source: _bmad-output/implementation-artifacts/6-1-mttr-trends-dashboard.md — Previous story patterns and lessons]
- [Source: _bmad-output/implementation-artifacts/3-9-tiered-llm-model-selection.md — Model tier selection]
- [Source: _bmad-output/implementation-artifacts/3-10-llm-response-caching.md — Cache cost savings]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created
- Cost tracking integrated into LlmClient (token-level tracking from LiteLLM responses)
- SpendingCapEnforcer in agent lifecycle for budget/rate enforcement
- SpendingService + spending Blueprint for admin dashboard (follows metrics pattern)
- SVG spend trend chart, CSS progress bars, HTMX partial updates
- Integer cents for money to avoid floating-point issues
- Cap enforcement optional — disabled when env vars not set
- 7 tasks: cost tracking, cap enforcement, dashboard service, routes+templates, CSS, tests, integration

### Change Log

- 2026-03-07: Implemented LLM Spending Caps — CostTracker, SpendingCapEnforcer, SpendingService, spending blueprint, templates, tests. 28 investigator tests + 9 UI tests pass, ruff clean, mypy clean, 403/403 investigator suite + 604/604 UI suite pass (1007 total).

### File List

**New files:**
- `investigator/beeper_investigator/llm/cost.py` — LLM pricing table, calculate_call_cost, CostTracker
- `investigator/beeper_investigator/llm/spending_cap.py` — SpendingCapConfig, SpendingCapEnforcer, CapCheckResult
- `ui/beeper_ui/services/spending_service.py` — SpendingService for dashboard data aggregation
- `ui/beeper_ui/routes/spending.py` — spending_bp Blueprint with 2 routes
- `ui/beeper_ui/templates/spending/spending.html` — Full spending dashboard page
- `ui/beeper_ui/templates/spending/_spending_content.html` — HTMX partial content
- `investigator/tests/test_spending_caps.py` — 28 tests (cost, caps, rate limits, integration)
- `ui/tests/test_spending.py` — 9 tests (service + routes + error handling)

**Modified files:**
- `investigator/beeper_investigator/llm/client.py` — Added CostTracker integration to complete/complete_sync
- `investigator/beeper_investigator/agent.py` — Added SpendingCapEnforcer check in _initialize, propagate cost_stats
- `ui/beeper_ui/routes/__init__.py` — Registered spending_bp
- `ui/beeper_ui/templates/base.html` — Added Spending nav link
- `ui/beeper_ui/static/css/main.css` — Added spending dashboard styles
