# Story 3.5: Cross-Layer Signal Correlation

Status: done

## Story

As an Investigator,
I want to correlate signals across multiple architectural layers,
so that I can identify root causes that span infrastructure, platform, application, and data layers.

## Acceptance Criteria

1. **Given** an investigation is analyzing a condition, **When** the investigator gathers signals, **Then** it queries across architectural layers (FR4): Infrastructure (K8s nodes, resources), Platform (K8s services, deployments), Application (service logs, error rates), Data (database metrics, query patterns).

2. **Given** correlated signals are found, **When** the investigator analyzes them, **Then** temporal correlation is established (what happened when) **And** causal chains are hypothesized (A caused B caused C).

3. **Given** signals span multiple services, **When** correlation completes, **Then** the service dependency chain is documented **And** the originating layer is identified.

4. **Given** signals are ambiguous, **When** correlation is uncertain, **Then** multiple hypotheses are generated **And** each hypothesis includes confidence level.

## Tasks / Subtasks

- [x] Task 1: Create SignalCorrelationStep scaffold with source handling (AC: 1, all)
  - [x] 1.1 Create `steps/signal_correlation.py` with `SignalCorrelationStep` implementing `InvestigationStep`
  - [x] 1.2 Accept `sources: SourceClients`, `llm_client`, `context`, `status_updater` via constructor
  - [x] 1.3 Check source availability at execute start: handle neither/one/both configured
  - [x] 1.4 When no sources configured → `StepResult(success=True)` with `sources_available: {}` and summary "no sources configured"
  - [x] 1.5 Define time window: default 30-minute lookback from now (constant `DEFAULT_LOOKBACK_MINUTES = 30`)

- [x] Task 2: LLM-driven query generation (AC: 1)
  - [x] 2.1 Build system prompt explaining PromQL/LogQL syntax and the 4 architectural layers
  - [x] 2.2 Build user prompt with `condition`, `service`, `severity`, available sources
  - [x] 2.3 LLM returns JSON with queries per layer: `{"layers": {"infrastructure": {"promql": [...]}, "application": {"logql": [...]}, ...}}`
  - [x] 2.4 Parse response with code fence stripping (reuse `_parse_response` pattern)
  - [x] 2.5 On LLM failure → fall back to default template queries (see Dev Notes)
  - [x] 2.6 Validate generated queries: max 3 per layer, reject empty strings

- [x] Task 3: Query execution and signal gathering (AC: 1)
  - [x] 3.1 Execute PromQL queries via `sources.prometheus.query_range()` with computed time window
  - [x] 3.2 Execute LogQL queries via `sources.loki.query_range()` with computed time window
  - [x] 3.3 Structure results as `Signal` dicts: `{"layer": str, "source": str, "query": str, "data": Any, "error": str | None}`
  - [x] 3.4 Handle per-query failures gracefully: log warning, include error in signal entry, continue
  - [x] 3.5 Cap total signals at reasonable limit (e.g., truncate large result sets for LLM prompt)

- [x] Task 4: LLM correlation analysis and hypothesis generation (AC: 2, 3, 4)
  - [x] 4.1 Build system prompt for temporal correlation and causal chain analysis
  - [x] 4.2 Build user prompt with gathered signals summary, investigation context, and available prior research (from pipeline metadata if available)
  - [x] 4.3 LLM returns JSON with hypotheses structure (see Dev Notes for schema)
  - [x] 4.4 Parse response: validate `hypotheses` array, each with `description`, `causal_chain`, `confidence`, `originating_layer`
  - [x] 4.5 Normalize confidence values: "high"/"medium"/"low"/null (same pattern as KBQueryStep)
  - [x] 4.6 On LLM failure → fall back to raw signal summary with "analysis_failed" flag
  - [x] 4.7 Support multiple hypotheses when signals are ambiguous (AC4)

- [x] Task 5: Register step in agent pipeline (AC: all)
  - [x] 5.1 Add `SignalCorrelationStep` to `_build_steps()` in `agent.py` after `KBQueryStep` (lazy import)
  - [x] 5.2 Pass `sources=self.sources`, `llm_client`, `context`, `status_updater`
  - [x] 5.3 Status updater reports "Correlating signals across architectural layers"

- [x] Task 6: Tests (AC: all)
  - [x] 6.1 Create `tests/test_signal_correlation.py` with `_make_step()` helper
  - [x] 6.2 Test signals gathered across all 4 layers (AC1)
  - [x] 6.3 Test temporal correlation established + causal chain hypothesized (AC2)
  - [x] 6.4 Test service dependency chain documented + originating layer identified (AC3)
  - [x] 6.5 Test multiple hypotheses with confidence levels for ambiguous signals (AC4)
  - [x] 6.6 Test no sources configured → graceful skip
  - [x] 6.7 Test Prometheus only (no Loki) → partial correlation
  - [x] 6.8 Test Loki only (no Prometheus) → partial correlation
  - [x] 6.9 Test query execution failure on individual queries → continues with remaining
  - [x] 6.10 Test LLM query generation failure → falls back to default queries
  - [x] 6.11 Test LLM correlation analysis failure → falls back to raw signal summary
  - [x] 6.12 Test malformed LLM JSON → graceful fallback
  - [x] 6.13 Test step data includes all expected schema keys (consistent shape)
  - [x] 6.14 Test step name and status update message

## Dev Notes

### Step Architecture — Accessing Source Clients

This is the **first step that needs `SourceClients`**. Current steps only receive `llm_client`, `context`, `status_updater` (and `kb_client` for KBQueryStep). The `SignalCorrelationStep` constructor adds `sources`:

```python
class SignalCorrelationStep:
    name: str = "Cross-Layer Signal Correlation"

    def __init__(
        self,
        sources: SourceClients,
        llm_client: LlmClient,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
    ) -> None:
        self.sources = sources
        self.llm_client = llm_client
        self.context = context
        self.status_updater = status_updater
```

In `_build_steps()`:
```python
from beeper_investigator.steps.signal_correlation import SignalCorrelationStep

SignalCorrelationStep(
    sources=self.sources,
    llm_client=self.llm_client,
    context=self.context,
    status_updater=self.status_updater,
)
```

### Source Client Method Signatures

Both clients are already implemented and tested (Stories 1.4, 1.5).

**PrometheusClient** (`sources/prometheus.py`):
```python
def query(self, promql: str, time: Optional[str] = None) -> dict[str, Any]
def query_range(self, promql: str, start: str, end: str, step: str = "60s") -> dict[str, Any]
```
- `start`/`end` are ISO 8601 strings or Unix timestamps
- Returns raw Prometheus API response `data` object
- Reads `PROMETHEUS_URL` from env

**LokiClient** (`sources/loki.py`):
```python
def query(self, logql: str, limit: int = 100, time: Optional[str] = None) -> dict[str, Any]
def query_range(self, logql: str, start: str, end: str, limit: int = 1000) -> dict[str, Any]
```
- `start`/`end` are **nanosecond Unix epoch strings** (e.g., `"1706454600000000000"`)
- Returns raw Loki API response `data` object
- Reads `LOKI_URL` from env

**Critical difference:** Prometheus accepts ISO timestamps; Loki needs nanosecond Unix epoch strings. The step must handle this format difference when computing the time window.

### Time Window Computation

Use a default 30-minute lookback from current time:
```python
DEFAULT_LOOKBACK_MINUTES = 30

now = datetime.now(timezone.utc)
start = now - timedelta(minutes=DEFAULT_LOOKBACK_MINUTES)

# Prometheus format: ISO 8601
prom_start = start.isoformat()
prom_end = now.isoformat()

# Loki format: nanosecond Unix epoch
loki_start = str(int(start.timestamp() * 1_000_000_000))
loki_end = str(int(now.timestamp() * 1_000_000_000))
```

### Two-Phase LLM Approach

**Phase 1 — Query Generation** (uses default model, `max_tokens=512`, `temperature=0.0`):

System prompt explains PromQL/LogQL and the 4 layers. User prompt provides condition/service/severity and which sources are available.

Expected LLM response:
```json
{
  "layers": {
    "infrastructure": {
      "promql": ["node_cpu_seconds_total{mode!='idle'}", "node_memory_MemAvailable_bytes"]
    },
    "platform": {
      "promql": ["kube_pod_container_status_restarts_total{namespace='default',container=~'payments.*'}"]
    },
    "application": {
      "logql": ["{namespace='default',container=~'payments.*'} |= \"error\""],
      "promql": ["rate(http_requests_total{service='payments',code=~'5..'}[5m])"]
    },
    "data": {
      "promql": ["pg_stat_activity{datname='payments'}"]
    }
  }
}
```

**Phase 2 — Correlation Analysis** (uses default model, `max_tokens=1024`, `temperature=0.0`):

System prompt explains temporal correlation and causal chain analysis. User prompt provides gathered signals and investigation context.

Expected LLM response:
```json
{
  "signal_summary": "12 signals gathered across infrastructure, platform, and application layers",
  "hypotheses": [
    {
      "description": "Database connection pool exhaustion causing application timeouts",
      "causal_chain": "DB connection limit reached → query timeouts → 5xx responses → user-facing errors",
      "confidence": "high",
      "supporting_signals": ["pg_stat_activity spike at 14:20", "HTTP 5xx spike at 14:22"],
      "originating_layer": "data"
    },
    {
      "description": "Node memory pressure causing OOM kills",
      "causal_chain": "Node memory exhausted → OOM kills → pod restarts → service degradation",
      "confidence": "low",
      "supporting_signals": ["node_memory_MemAvailable low"],
      "originating_layer": "infrastructure"
    }
  ],
  "service_dependency_chain": ["payments-db", "payments", "checkout-frontend"],
  "temporal_summary": "Initial signal at 14:18 (DB layer), cascade to application at 14:22"
}
```

### Default Template Queries (Fallback)

When LLM query generation fails, use these safe defaults:

```python
_DEFAULT_QUERIES: dict[str, dict[str, list[str]]] = {
    "infrastructure": {
        "promql": [
            'node_cpu_seconds_total{{mode!="idle"}}',
            "node_memory_MemAvailable_bytes",
        ],
    },
    "platform": {
        "promql": [
            'kube_pod_container_status_restarts_total{{namespace="{namespace}"}}',
            'kube_deployment_status_replicas_available{{namespace="{namespace}"}}',
        ],
    },
    "application": {
        "logql": [
            '{{namespace="{namespace}"}} |= "error"',
        ],
    },
    "data": {
        "promql": [
            "up",
        ],
    },
}
```

These are intentionally broad — the LLM-generated queries are preferred when available.

### StepResult Data Schema

**Always return these keys** (consistent shape, learned from MEDIUM-3 fix in Story 3-4):

```python
data = {
    "sources_available": {"prometheus": bool, "loki": bool},
    "layers_queried": list[str],       # e.g., ["infrastructure", "platform", "application"]
    "signals_gathered": int,            # Total signal count
    "signal_summary": str,              # Brief text summary
    "hypotheses": list[dict],           # Each: description, causal_chain, confidence, originating_layer
    "service_dependency_chain": list[str] | None,
    "correlation_attempted": bool,      # False if no sources or no signals
}
```

### Graceful Degradation Paths

| Failure | Step Behavior | `success` | Key Data |
|---------|--------------|-----------|----------|
| No sources configured | Skip entirely | `True` | `sources_available: {}, correlation_attempted: false` |
| Prometheus only | Query PromQL, skip LogQL | `True` | Partial layer coverage |
| Loki only | Query LogQL, skip PromQL | `True` | Application layer only |
| LLM query generation fails | Use default template queries | `True` | May have broader/less relevant results |
| Individual query fails | Log warning, continue with remaining | `True` | Partial signals |
| All queries return empty | Report no signals found | `True` | `signals_gathered: 0, hypotheses: []` |
| LLM correlation fails | Return raw signal summary, no hypotheses | `True` | `hypotheses: [], signal_summary: "raw ..."` |

**Key principle (from NFR-R1):** Partial results are always better than no results. Never fail fatally.

### Signal Formatting for LLM Prompt

Signals must be summarized for the LLM — do NOT dump raw Prometheus/Loki JSON. Format signals as:

```
[infrastructure] node_cpu: avg=72% (14:15-14:45), peak=94% at 14:22
[platform] pod_restarts: payments-xyz restarted 3 times (14:20-14:25)
[application] error_logs: 47 errors matching "connection timeout" (14:18-14:30)
[data] pg_connections: active=95/100 at 14:20 (near limit)
```

Keep it concise — the LLM performs better with structured summaries than raw metric dumps. Cap at ~50 signal entries to stay within token limits.

### Existing Code to Modify

| File | Change |
|------|--------|
| `agent.py` | Add `SignalCorrelationStep` to `_build_steps()` (lazy import, after `KBQueryStep`) |

### New Files to Create

| File | Purpose |
|------|---------|
| `beeper_investigator/steps/signal_correlation.py` | `SignalCorrelationStep` implementation |
| `tests/test_signal_correlation.py` | Unit tests for signal correlation step |

### Critical Anti-Patterns to Avoid

1. **Do NOT make the step async.** Agent is synchronous (Story 3-2). Use `complete_sync()` and source client `query_range()`.
2. **Do NOT modify agent state directly.** Return `StepResult`; pipeline aggregates.
3. **Do NOT abort if sources are unavailable.** Graceful degradation — always succeed with partial data.
4. **Do NOT import at module level in `agent.py`.** Use lazy import in `_build_steps()`.
5. **Do NOT dump raw Prometheus/Loki JSON into LLM prompt.** Summarize signals first — raw JSON wastes tokens and reduces quality.
6. **Do NOT hardcode metric names beyond the fallback defaults.** Let the LLM generate context-appropriate queries.
7. **Do NOT create a `correlation/` module.** Architecture planned it but the step pattern (`steps/signal_correlation.py`) is more consistent with the codebase. Extract later if needed.
8. **Do NOT couple to specific metric existence.** Queries may return empty data — that's fine, not an error.
9. **Do NOT use the screening model for correlation.** This is deep analysis — use the default model.
10. **Do NOT pass raw signal data through to Qdrant metadata.** Summarize — raw data would bloat the payload.

### Previous Story Intelligence

**From Story 3-4 (KB Query & Prior Research):**
- Two-phase LLM pattern: generation → analysis is proven and effective
- JSON parsing: strip code fences, `json.loads()`, graceful fallback to defaults
- Confidence normalization: validate against known values, default to `None`
- Independent error handling: wrap each operation separately (learned from MEDIUM-2 fix)
- Consistent data schema: always return all expected keys (learned from MEDIUM-3 fix)
- Config check before API call: check availability before attempting (learned from MEDIUM-1 fix)

**From Story 3-3 (Customer Impact Assessment):**
- Screening model for lightweight tasks; default model for deep analysis
- Case-insensitive normalization for LLM string values
- Status updater called before main logic

**From Story 3-2 (Investigator Agent Scaffold):**
- `SourceClients` dataclass: `prometheus: Optional[PrometheusClient]`, `loki: Optional[LokiClient]`
- Either or both may be None
- Agent passes `self.sources` to steps that need it

### Testing Standards

- Mock `sources.prometheus.query_range()` and `sources.loki.query_range()` — do NOT make real HTTP calls
- Mock `LlmClient.complete_sync()` — do NOT make real LLM calls
- Use `_make_step()` helper with configurable mocks (established pattern)
- Test all graceful degradation paths (see table above)
- Test consistent data schema across all code paths
- Test per-query failure isolation (one query fails, others succeed)
- Set `sources.prometheus = None` / `sources.loki = None` to test missing sources

### Project Structure Notes

```
investigator/beeper_investigator/
├── steps/
│   ├── __init__.py              # No changes (InvestigationStep protocol, StepResult)
│   ├── impact_assessment.py     # No changes (reference for step pattern)
│   ├── kb_query.py              # No changes (reference for two-phase LLM)
│   └── signal_correlation.py    # NEW: SignalCorrelationStep
├── agent.py                     # MODIFY: add SignalCorrelationStep to _build_steps()
├── sources/
│   ├── prometheus.py            # No changes (query/query_range already exist)
│   └── loki.py                  # No changes (query/query_range already exist)
└── ...

investigator/tests/
├── test_signal_correlation.py   # NEW: Signal correlation step tests
└── ... (existing test files unchanged)
```

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic-3, Story 3.5] — FR4, AC1-AC4
- [Source: _bmad-output/planning-artifacts/architecture.md#Investigation-State-Machine] — `correlating_signals` state
- [Source: _bmad-output/planning-artifacts/architecture.md#LLM-Integration] — LiteLLM, tiered models (default for correlation)
- [Source: _bmad-output/planning-artifacts/architecture.md#Data-Flow] — Prometheus/Loki → Investigator → Qdrant
- [Source: _bmad-output/planning-artifacts/architecture.md#Project-Structure] — `correlation/signals.py` planned (but step pattern preferred)
- [Source: _bmad-output/implementation-artifacts/3-4-kb-query-prior-research.md] — Two-phase LLM, degradation fixes, schema consistency
- [Source: _bmad-output/implementation-artifacts/3-3-customer-impact-assessment.md] — Step pattern, screening model, JSON parsing
- [Source: investigator/beeper_investigator/sources/prometheus.py] — `query()`, `query_range()` signatures
- [Source: investigator/beeper_investigator/sources/loki.py] — `query()`, `query_range()` signatures (nanosecond timestamps!)
- [Source: investigator/beeper_investigator/agent.py] — `SourceClients`, `_build_steps()`, `_run_steps()`
- [Source: investigator/beeper_investigator/steps/__init__.py] — `InvestigationStep` protocol, `StepResult`
- [Source: investigator/beeper_investigator/context.py] — `InvestigationContext` fields (no timestamp — use lookback window)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

N/A

### Completion Notes List

- Implemented `SignalCorrelationStep` with two-phase LLM approach: Phase 1 generates PromQL/LogQL queries per architectural layer, Phase 2 analyzes gathered signals for temporal correlation and causal chains
- Handles Prometheus ISO 8601 vs Loki nanosecond epoch timestamp format difference in time window computation
- Default template queries provide fallback when LLM query generation fails; used `str.replace()` instead of `str.format()` to avoid conflicts with PromQL/LogQL curly braces
- 7 graceful degradation paths: no sources, prometheus only, loki only, LLM query gen failure, individual query failure, all queries empty, LLM analysis failure
- Consistent StepResult data schema with all keys always present across all code paths
- Confidence normalization: high/medium/low/null with case-insensitive matching
- Signal formatting summarizes metric values, timestamps, and log samples for LLM rather than dumping raw JSON
- Registered step in agent pipeline after KBQueryStep via lazy import
- 27 tests covering all ACs, degradation paths, schema consistency, prompt content, and edge cases
- Full test suite: 179 passed, 2 pre-existing failures (test_kb_client.py), 3 skipped

### Change Log

- 2026-02-24: Implemented Story 3.5 — Cross-Layer Signal Correlation step with two-phase LLM, multi-source query execution, and 23 unit tests
- 2026-02-24: Code review fixes — Fixed doubled braces in analysis prompt, improved signal formatting with metric values/timestamps, added TYPE_CHECKING for SourceClients type, validated originating_layer, added 4 new tests (prompt content, cap enforcement, layer validation)

### File List

- `investigator/beeper_investigator/steps/signal_correlation.py` (NEW) — SignalCorrelationStep implementation
- `investigator/tests/test_signal_correlation.py` (NEW) — 27 unit tests
- `investigator/beeper_investigator/agent.py` (MODIFIED) — Added SignalCorrelationStep to `_build_steps()`

### Code Review Record

| # | Severity | Description | Status |
|---|----------|-------------|--------|
| M1 | MEDIUM | `_ANALYSIS_SYSTEM_PROMPT` doubled braces — LLM receives malformed JSON example | Fixed |
| M2 | MEDIUM | `_format_signals` count-only summaries — insufficient for temporal correlation | Fixed |
| M3 | MEDIUM | `sources: Any` type — loses type safety, should use `TYPE_CHECKING` | Fixed |
| M4 | MEDIUM | Missing test for LLM prompt content — no verification context reaches LLM | Fixed |
| L1 | LOW | Unused imports in test file (`patch`, `datetime`, `timezone`) | Fixed |
| L2 | LOW | `test_query_validation_max_per_layer` doesn't verify actual cap enforcement | Fixed |
| L3 | LOW | `originating_layer` not validated against `_LAYERS` — arbitrary values pass through | Fixed |
