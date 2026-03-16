# Story 4.6: Post-Fix Metric Verification

Status: review

## Story

As the **system**,
I want to verify that a fix resolves the issue by monitoring post-fix metrics,
so that we have evidence-based confirmation that the problem is actually solved.

## Acceptance Criteria

1. **Given** a fix has been applied (either in sandbox or production at TL4-5)
   **When** the post-fix verification window elapses (configurable, default 15 minutes)
   **Then** the system compares pre-fix and post-fix metrics for the affected SLOs
   **And** verification result is: confirmed (metrics improved), inconclusive (no change), degraded (metrics worsened)

2. **Given** post-fix metrics show degradation
   **When** the verification result is "degraded"
   **Then** the autonomous action is rolled back within 60 seconds (NFR16, FR62)
   **And** the SRE is immediately notified with pre-fix and post-fix metric comparison

3. **Given** post-fix metrics confirm resolution
   **When** the verification result is "confirmed"
   **Then** the investigation status moves to "verified" and the fix is marked as proven
   **And** the proven fix is eligible for KB accumulation (Story 4.8)

## Tasks / Subtasks

- [x] Task 1: Create MetricVerifierStep class with constructor and trust gating (AC: #1, #2, #3)
  - [ ] 1.1 Create `investigator/beeper_investigator/remediation/metric_verifier.py` with `MetricVerifierStep` class implementing `InvestigationStep` protocol with `name = "Post-Fix Metric Verification"`
  - [ ] 1.2 Constructor: `__init__(self, llm_client: LlmClient, context: InvestigationContext, status_updater: InvestigationStatusUpdater, pipeline_metadata: dict[str, Any] | None = None, sources: SourceClients | None = None)` — same signature as SandboxExecutorStep (needs Prometheus for metric queries)
  - [ ] 1.3 Add configurable verification window: read `VERIFICATION_WINDOW_MINUTES` env var (default 15). Store as `self._verification_window_minutes: int`
  - [ ] 1.4 Implement trust-level gating in `execute()`: if `context.trust_level < 3`, return `StepResult(success=True, summary="Post-fix verification skipped — trust level {trust_level} below TL3 threshold", data={"verification_executed": False, "skip_reason": "trust_level_insufficient", "trust_level": trust_level})`

- [x] Task 2: Implement prerequisite checks (AC: #1)
  - [ ] 2.1 Check `pipeline_metadata.get("sandbox_executed")` or `pipeline_metadata.get("pr_generated")` — if neither is True, skip with `skip_reason="no_fix_applied"` and summary "No fix applied — metric verification skipped"
  - [ ] 2.2 Check `self.sources` and `self.sources.prometheus` — if Prometheus is not configured, skip with `skip_reason="no_prometheus"` and summary "Prometheus not configured — metric verification skipped"
  - [ ] 2.3 Get `metrics_to_watch` from `pipeline_metadata` — if empty/missing, skip with `skip_reason="no_metrics_to_watch"` and summary "No metrics to watch — metric verification skipped"

- [x] Task 3: Implement metric comparison engine (AC: #1)
  - [ ] 3.1 Create `VerificationResult` dataclass: `metric: str`, `pre_fix_value: float | None`, `post_fix_value: float | None`, `status: str` ("confirmed"|"inconclusive"|"degraded"), `delta_pct: float | None`, `error_message: str | None`
  - [ ] 3.2 Implement `_query_metric_range(metric: str, offset_minutes: int, duration_minutes: int) -> float | None`: query Prometheus with time offset for average value over duration. Use `self.sources.prometheus.query()` with PromQL `avg_over_time({metric}[{duration}m] offset {offset}m)`. Return average value or None on error
  - [ ] 3.3 Implement `_compare_metrics(metrics: list[str]) -> list[VerificationResult]`: for each metric, query pre-fix (offset=verification_window, duration=5min) and post-fix (offset=0, duration=5min), compute delta percentage, classify as confirmed (improvement > 10%), inconclusive (change < 10%), or degraded (worsening > 10%)
  - [ ] 3.4 Implement `_determine_overall_status(results: list[VerificationResult]) -> str`: "confirmed" if all non-error are confirmed, "degraded" if any are degraded, "inconclusive" otherwise

- [x] Task 4: Implement rollback on degradation (AC: #2)
  - [ ] 4.1 Implement `_handle_degradation(results: list[VerificationResult]) -> dict[str, Any]`: when overall status is "degraded", update `self.status_updater.update_message()` with degradation notice including metric comparison summary
  - [ ] 4.2 Set `rollback_recommended: True` in result data for downstream pipeline consumption
  - [ ] 4.3 Include `pre_fix_vs_post_fix` comparison dict in result data for SRE notification: each metric with pre/post values and delta
  - [ ] 4.4 Log warning with metric details for immediate SRE visibility

- [x] Task 5: Implement confirmed verification (AC: #3)
  - [ ] 5.1 Implement `_handle_confirmed(results: list[VerificationResult]) -> dict[str, Any]`: when overall status is "confirmed", update `self.status_updater.update_message("Fix verified — metrics confirm resolution")`
  - [ ] 5.2 Set `fix_verified: True` and `fix_proven: True` in result data for Story 4-8 KB accumulation eligibility
  - [ ] 5.3 Set `verification_status: "verified"` in result data for investigation status tracking

- [x] Task 6: Implement evidence attachment for downstream PR (AC: #1, #2, #3)
  - [ ] 6.1 Return comprehensive `StepResult.data` with: `verification_executed: bool`, `verification_status: str` ("confirmed"|"inconclusive"|"degraded"), `verification_window_minutes: int`, `metrics_compared: int`, `metrics_confirmed: int`, `metrics_degraded: int`, `metrics_inconclusive: int`, `verification_results: list[dict]` (serialized VerificationResult list), `fix_verified: bool`, `fix_proven: bool`, `rollback_recommended: bool`, `verification_model_tier: str`

- [x] Task 7: Update evidence trail formatter for verification results (AC: #1, #2, #3)
  - [ ] 7.1 In `investigator/beeper_investigator/remediation/evidence_trail.py`, add a "Post-Fix Verification" section in `format_pr_body()` after the "Sandbox Test Results" section. Read `pipeline_metadata.get("verification_executed")` — if True, render a section with overall status, verification window, and a table of metric comparisons (Metric, Pre-Fix, Post-Fix, Delta%, Status)
  - [ ] 7.2 If verification was not executed, show skip reason
  - [ ] 7.3 Update audit trail section: verification status now reflects actual verification result instead of sandbox result

- [x] Task 8: Update remediation package exports (AC: #1)
  - [ ] 8.1 Add `MetricVerifierStep` and `VerificationResult` to `investigator/beeper_investigator/remediation/__init__.py` imports and `__all__`

- [x] Task 9: Integrate MetricVerifierStep into agent pipeline (AC: #1)
  - [ ] 9.1 In `investigator/beeper_investigator/agent.py`, add lazy import for `MetricVerifierStep` in `_build_steps()`
  - [ ] 9.2 Insert `MetricVerifierStep` as step 10 (index 9) between `SandboxExecutorStep` (index 8) and `PRGeneratorStep` (moves to index 10). Pass `llm_client`, `context`, `status_updater`, `pipeline_metadata`, and `sources=self.sources` for Prometheus access
  - [ ] 9.3 PRGeneratorStep position moves from index 9 to index 10 — no code change needed, just list order
  - [ ] 9.4 Update step count: 10 → 11

- [x] Task 10: Write comprehensive unit tests (AC: #1, #2, #3)
  - [ ] 10.1 Create `investigator/tests/test_metric_verifier.py` with `_make_step()` factory following established pattern. Factory must accept `pipeline_metadata`, `trust_level`, `sources` overrides. Mock Prometheus via `sources.prometheus`
  - [ ] 10.2 `TestTrustGating`: TL1 skips, TL2 skips, TL3 proceeds, TL4 proceeds, TL5 proceeds
  - [ ] 10.3 `TestPrerequisiteChecks`: no sandbox_executed and no pr_generated → skip, no Prometheus → skip, no metrics_to_watch → skip, sandbox_executed=True proceeds, pr_generated=True proceeds
  - [ ] 10.4 `TestMetricComparison`: metric improved → confirmed, metric unchanged → inconclusive, metric degraded → degraded, Prometheus error → error result, no data returned → inconclusive
  - [ ] 10.5 `TestOverallStatus`: all confirmed → "confirmed", any degraded → "degraded", mix of confirmed/inconclusive → "inconclusive", all inconclusive → "inconclusive"
  - [ ] 10.6 `TestDegradationHandling`: degraded triggers status_updater warning message, rollback_recommended=True set, pre/post comparison dict included
  - [ ] 10.7 `TestConfirmedHandling`: confirmed sets fix_verified=True, fix_proven=True, verification_status="verified", status_updater called
  - [ ] 10.8 `TestVerificationWindow`: default 15 minutes, custom env var override
  - [ ] 10.9 `TestEvidenceAttachment`: result.data has all required keys, verification_results is list of dicts

- [x] Task 11: Write integration tests (AC: #1)
  - [ ] 11.1 Create `investigator/tests/test_agent_metric_verifier_integration.py`: verify `MetricVerifierStep` is at index 9 (step 10) in `_build_steps()`, total pipeline length is 11, verify `PRGeneratorStep` is at index 10 (step 11)
  - [ ] 11.2 Update `investigator/tests/test_agent_pr_integration.py`: PRGeneratorStep is now step 11 (index 10), total steps 11
  - [ ] 11.3 Update `investigator/tests/test_agent_sandbox_integration.py`: total steps 10 → 11
  - [ ] 11.4 Update `investigator/tests/test_agent_runbook_integration.py`: total steps 10 → 11
  - [ ] 11.5 Update `investigator/tests/test_agent_testplan_integration.py`: total steps 10 → 11

- [x] Task 12: Update evidence trail tests (AC: #1, #2, #3)
  - [ ] 12.1 In `investigator/tests/test_evidence_trail.py`, add tests for new verification section: `TestVerificationResultsSection` — verification_executed=True renders table, degraded shows rollback warning, confirmed shows verified badge, verification not executed shows skip reason

- [x] Task 13: Run all investigator tests (AC: #1, #2, #3)
  - [ ] 13.1 Run `cd investigator && python -m pytest tests/ -v` — all existing + new tests pass
  - [ ] 13.2 Run `cd investigator && python -m ruff check .` — no new warnings
  - [ ] 13.3 Run `cd investigator && python -m mypy beeper_investigator/ --strict` — no new errors
  - [ ] 13.4 Verify zero regressions in existing step tests

## Dev Notes

### Architecture Patterns to Follow

**CRITICAL CONTEXT: This story adds the MetricVerifierStep to the investigator pipeline BETWEEN SandboxExecutorStep (step 9) and PRGeneratorStep (now step 11). This step compares pre-fix and post-fix Prometheus metrics for the SLOs affected by the anomaly. It uses `metrics_to_watch` produced by TestPlannerStep (step 8) as the metric list, queries Prometheus for time-offset metric ranges, and produces a verification outcome: confirmed (metrics improved), inconclusive (no significant change), or degraded (metrics worsened). On degradation, it sets `rollback_recommended=True` for downstream action and notifies via status_updater. On confirmation, it sets `fix_proven=True` for Story 4-8 KB accumulation. Results flow downstream to PRGeneratorStep for inclusion in the PR evidence trail.**

**FR28 (post-fix verification)** maps to `investigator/remediation/verifier.py` per architecture.md — use `metric_verifier.py` to follow the established naming convention (`sandbox_executor.py`, `pr_generator.py`, `test_planner.py`).

**What already exists (DO NOT recreate):**

| Component | Location | Status |
|-----------|----------|--------|
| `InvestigationStep` protocol + `StepResult` | `investigator/beeper_investigator/steps/__init__.py` | Done (v0.1.0) |
| 6-step investigation pipeline | `investigator/beeper_investigator/steps/` | Done (v0.1.0) |
| `RunbookExecutorStep` (step 7) | `investigator/beeper_investigator/remediation/runbook_executor.py` | Done (Story 4-2) |
| `TestPlannerStep` (step 8) — produces `metrics_to_watch` | `investigator/beeper_investigator/remediation/test_planner.py` | Done (Story 4-3) |
| `SandboxExecutorStep` (step 9) — produces `sandbox_executed`, `sandbox_overall_status` | `investigator/beeper_investigator/remediation/sandbox_executor.py` | Done (Story 4-5) |
| `PRGeneratorStep` (step 10 → becomes 11) | `investigator/beeper_investigator/remediation/pr_generator.py` | Done (Story 4-4) |
| `EvidenceTrailFormatter` — extend with verification section | `investigator/beeper_investigator/remediation/evidence_trail.py` | Done (Story 4-4/4-5) |
| `remediation/__init__.py` package | `investigator/beeper_investigator/remediation/__init__.py` | Done — add new exports |
| `InvestigatorAgent._build_steps()` | `investigator/beeper_investigator/agent.py` | Done — 10 steps currently, will become 11 |
| `PrometheusClient` with `.query()` method | `investigator/beeper_investigator/sources/prometheus.py` | Done (v0.1.0) |
| `LokiClient` | `investigator/beeper_investigator/sources/loki.py` | Done (v0.1.0) |
| `SourceClients` (prometheus + loki) | `investigator/beeper_investigator/agent.py` | Done — passed to steps as `sources` |
| `InvestigationContext` with `trust_level` | `investigator/beeper_investigator/context.py` | Done (Story 4-2) |
| `InvestigationStatusUpdater` | `investigator/beeper_investigator/k8s/status.py` | Done (v0.1.0) |
| `LlmClient` with `select_model()` | `investigator/beeper_investigator/llm/client.py` | Done (v0.1.0) |

**What this story adds:**

| Component | Description |
|-----------|-------------|
| `remediation/metric_verifier.py` | `MetricVerifierStep` — post-fix metric comparison with confirmed/inconclusive/degraded outcomes |
| `VerificationResult` dataclass | Per-metric comparison result with pre/post values and delta |
| Evidence trail verification section | Verification results rendered in PR body via `EvidenceTrailFormatter` |
| Agent pipeline step 10 | `MetricVerifierStep` wired into `_build_steps()` between SandboxExecutor and PRGenerator |
| Tests | Unit + integration tests for all new components |

### Pipeline Metadata — Data Flow (CRITICAL)

The `pipeline_metadata` dict is shared by reference across all steps. After prior steps run, it contains:

```python
# Available from step 8 (TestPlannerStep) — provides metrics list:
{
    "test_plan_generated": True,
    "metrics_to_watch": ["kube_pod_container_status_restarts_total", "http_request_duration_seconds"],
    "estimated_duration_minutes": 15,
}

# Available from step 9 (SandboxExecutorStep) — indicates fix was tested:
{
    "sandbox_executed": True,          # MetricVerifierStep checks this
    "sandbox_overall_status": "pass",  # Sandbox passed — now verify metrics
}

# OR from step 10 (PRGeneratorStep in old position) — indicates fix was proposed:
# NOTE: In new position, PR comes AFTER verification (step 11)
# So MetricVerifierStep checks sandbox_executed primarily
{
    "pr_generated": True,              # Alternate trigger for verification
}

# MetricVerifierStep will ADD to pipeline_metadata:
{
    "verification_executed": True,                   # PRGeneratorStep reads this
    "verification_status": "confirmed",              # "confirmed"|"inconclusive"|"degraded"
    "verification_window_minutes": 15,
    "metrics_compared": 2,
    "metrics_confirmed": 2,
    "metrics_degraded": 0,
    "metrics_inconclusive": 0,
    "verification_results": [
        {
            "metric": "kube_pod_container_status_restarts_total",
            "pre_fix_value": 5.0,
            "post_fix_value": 0.0,
            "status": "confirmed",
            "delta_pct": -100.0,
            "error_message": None,
        }
    ],
    "fix_verified": True,              # Set when status == "confirmed"
    "fix_proven": True,                # For Story 4-8 KB accumulation
    "rollback_recommended": False,     # True when status == "degraded"
    "verification_model_tier": "remediation",
}
```

### Constructor Signature — MUST Extend SandboxExecutorStep Pattern

Like SandboxExecutorStep, MetricVerifierStep needs access to Prometheus for metric queries. Uses identical `sources: SourceClients` parameter:

```python
from beeper_investigator.agent import SourceClients

class MetricVerifierStep:
    """Verify fix effectiveness by comparing pre/post-fix metrics."""

    name: str = "Post-Fix Metric Verification"

    def __init__(
        self,
        llm_client: LlmClient,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
        pipeline_metadata: dict[str, Any] | None = None,
        sources: SourceClients | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.context = context
        self.status_updater = status_updater
        self.pipeline_metadata = pipeline_metadata if pipeline_metadata is not None else {}
        self.sources = sources
        # Configurable verification window (default 15 minutes per AC#1)
        window_raw = os.environ.get("VERIFICATION_WINDOW_MINUTES", "15")
        try:
            self._verification_window_minutes = max(1, int(window_raw))
        except (ValueError, TypeError):
            self._verification_window_minutes = 15
```

### Metric Comparison Approach

**Pre-fix vs post-fix comparison using Prometheus range queries:**

```python
@dataclass
class VerificationResult:
    metric: str
    pre_fix_value: float | None
    post_fix_value: float | None
    status: str  # "confirmed" | "inconclusive" | "degraded"
    delta_pct: float | None
    error_message: str | None

def _query_metric_range(self, metric: str, offset_minutes: int, duration_minutes: int) -> float | None:
    """Query Prometheus for average metric value over a time range.

    Uses PromQL: avg_over_time({metric}[{duration}m] offset {offset}m)
    Returns average value as float, or None if no data/error.
    """
    query = f"avg_over_time({metric}[{duration_minutes}m] offset {offset_minutes}m)"
    try:
        result = self.sources.prometheus.query(query)
        data = result.get("data", {}).get("result", [])
        if data and len(data) > 0:
            # Extract scalar value from Prometheus result
            value = data[0].get("value", [None, None])
            return float(value[1]) if value[1] is not None else None
    except Exception as exc:
        logger.warning("Prometheus query failed for %s: %s", metric, exc)
    return None

def _compare_metrics(self, metrics: list[str]) -> list[VerificationResult]:
    """Compare pre-fix and post-fix metric values."""
    results = []
    window = self._verification_window_minutes
    for metric in metrics:
        # Pre-fix: average value during window before fix (offset by window + 5min buffer)
        pre_val = self._query_metric_range(metric, offset_minutes=window + 5, duration_minutes=5)
        # Post-fix: average value in last 5 minutes
        post_val = self._query_metric_range(metric, offset_minutes=0, duration_minutes=5)

        if pre_val is None or post_val is None:
            results.append(VerificationResult(
                metric=metric, pre_fix_value=pre_val, post_fix_value=post_val,
                status="inconclusive", delta_pct=None,
                error_message="Incomplete metric data" if pre_val is None and post_val is None else None,
            ))
            continue

        # Calculate percentage change
        if pre_val == 0:
            delta_pct = 0.0 if post_val == 0 else 100.0
        else:
            delta_pct = ((post_val - pre_val) / abs(pre_val)) * 100

        # Classify: error/restart metrics decreasing = good, availability increasing = good
        # Use absolute delta > 10% as threshold for confirmed/degraded
        if abs(delta_pct) < 10:
            status = "inconclusive"
        elif delta_pct < -10:
            status = "confirmed"  # Metric decreased (errors/restarts went down)
        else:
            status = "degraded"  # Metric increased (errors/restarts went up)

        results.append(VerificationResult(
            metric=metric, pre_fix_value=pre_val, post_fix_value=post_val,
            status=status, delta_pct=round(delta_pct, 2), error_message=None,
        ))
    return results
```

### Degradation Handling (NFR16, FR62 — Rollback within 60s)

```python
def _handle_degradation(self, results: list[VerificationResult]) -> None:
    """Notify SRE and flag rollback on metric degradation."""
    degraded = [r for r in results if r.status == "degraded"]
    comparison = "; ".join(
        f"{r.metric}: {r.pre_fix_value} → {r.post_fix_value} ({r.delta_pct:+.1f}%)"
        for r in degraded
    )
    self.status_updater.update_message(
        f"DEGRADATION DETECTED — rollback recommended. {comparison}"
    )
    logger.warning(
        "Post-fix metric degradation detected: %s", comparison
    )
```

### Evidence Trail Enhancement

Add to `EvidenceTrailFormatter.format_pr_body()` after the Sandbox Test Results section:

```python
# Post-Fix Verification
if pipeline_metadata.get("verification_executed"):
    v_status = pipeline_metadata.get("verification_status", "unknown")
    window = pipeline_metadata.get("verification_window_minutes", "N/A")
    v_results = pipeline_metadata.get("verification_results", [])
    sections.append(f"### Post-Fix Verification\n**Overall: {v_status.upper()}** (window: {window}min)\n")
    if v_results:
        sections.append("| Metric | Pre-Fix | Post-Fix | Delta% | Status |")
        sections.append("|--------|---------|----------|--------|--------|")
        for vr in v_results:
            if isinstance(vr, dict):
                sections.append(
                    f"| {vr.get('metric', '?')[:40]} "
                    f"| {vr.get('pre_fix_value', 'N/A')} "
                    f"| {vr.get('post_fix_value', 'N/A')} "
                    f"| {vr.get('delta_pct', 'N/A')}% "
                    f"| {vr.get('status', '?')} |"
                )
    if v_status == "degraded":
        sections.append("\n**ROLLBACK RECOMMENDED** — metrics degraded after fix.\n")
elif pipeline_metadata.get("verification_executed") is False:
    skip_reason = pipeline_metadata.get("skip_reason", "unknown")
    sections.append(f"### Post-Fix Verification\n*Skipped: {skip_reason}*\n")
```

### Trust-Level Gating (follow SandboxExecutorStep pattern exactly)

```python
# In execute():
if self.context.trust_level < 3:
    return StepResult(
        success=True,
        summary=f"Post-fix verification skipped — trust level {self.context.trust_level} below TL3 threshold",
        data={"verification_executed": False, "skip_reason": "trust_level_insufficient", "trust_level": self.context.trust_level},
    )
```

### Critical Guardrails

- **Trust-gated**: TL3+ required for metric verification. TL1-2 skip entirely (advisory-only)
- **Prometheus required**: Cannot verify metrics without Prometheus source. Skip gracefully if not configured
- **No LLM calls needed**: This step queries Prometheus directly — no LLM interpretation. LLM client passed for protocol consistency but not used
- **Non-fatal**: All `StepResult` returns have `success=True` — verification failures are soft (don't crash pipeline)
- **Rollback is advisory**: This step sets `rollback_recommended=True` but does NOT actually perform rollback (that's Story 4-7's responsibility). It notifies via status_updater for SRE visibility
- **10% threshold**: Classification threshold for confirmed/degraded. Configurable via future enhancement but hardcoded for now
- **Metric semantics**: Decreasing error/restart metrics = good ("confirmed"), increasing = bad ("degraded"). This works for most SRE metrics (error rates, latency, restart counts). Edge cases handled as "inconclusive"
- **Pre-fix window**: Queries Prometheus with offset = `verification_window + 5min` buffer, duration = 5min for the pre-fix baseline
- **Post-fix window**: Queries Prometheus for last 5min of data (current state)
- **Graceful degradation**: No metrics_to_watch → skip. No Prometheus → skip. Query failure → mark individual metric as "inconclusive"
- **Pipeline position**: Step 10 (index 9) — between SandboxExecutorStep (9) and PRGeneratorStep (now 11)
- **Zero regressions** — all existing 712 investigator tests must continue passing
- **ruff clean** — no new warnings
- **mypy strict** — must pass strict mode (no new errors)
- **No new dependencies** — Prometheus client already in pyproject.toml via SourceClients

### Test Pattern (follow existing test_sandbox_executor.py)

```python
from beeper_investigator.agent import SourceClients

def _make_step(pipeline_metadata=None, trust_level=3, sources=None, **overrides):
    """Factory for MetricVerifierStep with mocked dependencies."""
    llm = MagicMock(spec=LlmClient)
    ctx = InvestigationContext(
        investigation_id="test-inv-001",
        namespace="default",
        condition="high_error_rate",
        service="payments",
        severity="high",
        trust_level=trust_level,
        confidence_threshold=0.9,
    )
    status = MagicMock(spec=InvestigationStatusUpdater)
    if sources is None:
        sources = SourceClients(prometheus=MagicMock(), loki=MagicMock())
    defaults = {
        "llm_client": llm,
        "context": ctx,
        "status_updater": status,
        "pipeline_metadata": pipeline_metadata or {},
        "sources": sources,
    }
    defaults.update(overrides)
    step = MetricVerifierStep(**defaults)
    return step, defaults


def _sample_pipeline_metadata():
    """Full pipeline_metadata with sandbox results and metrics."""
    return {
        "test_plan_generated": True,
        "metrics_to_watch": ["kube_pod_container_status_restarts_total", "http_request_errors_total"],
        "sandbox_executed": True,
        "sandbox_overall_status": "pass",
    }


def _prometheus_response(value):
    """Mock Prometheus query response with a single result."""
    return {
        "data": {
            "result": [
                {"value": [1234567890, str(value)]}
            ]
        }
    }
```

### Project Structure Notes

- New file: `investigator/beeper_investigator/remediation/metric_verifier.py`
- Modified: `investigator/beeper_investigator/remediation/__init__.py` (add MetricVerifierStep + VerificationResult exports)
- Modified: `investigator/beeper_investigator/remediation/evidence_trail.py` (add verification results section)
- Modified: `investigator/beeper_investigator/agent.py` (insert step 10, PRGeneratorStep moves to 11)
- New test: `investigator/tests/test_metric_verifier.py`
- New test: `investigator/tests/test_agent_metric_verifier_integration.py`
- Modified test: `investigator/tests/test_agent_pr_integration.py` (step count 10 → 11, PR step index 9 → 10)
- Modified test: `investigator/tests/test_agent_sandbox_integration.py` (total steps 10 → 11)
- Modified test: `investigator/tests/test_agent_runbook_integration.py` (total steps 10 → 11)
- Modified test: `investigator/tests/test_agent_testplan_integration.py` (total steps 10 → 11)
- Modified test: `investigator/tests/test_evidence_trail.py` (verification results section tests)

### Previous Story Intelligence

**From Story 4-5 (Sandbox Test Execution):**
- SandboxExecutorStep is at index 8 (step 9) — MetricVerifierStep inserts after it (step 10), PRGeneratorStep moves to step 11
- SandboxExecutorStep produces `sandbox_executed`, `sandbox_overall_status`, `sandbox_test_results` — MetricVerifierStep reads `sandbox_executed` as prerequisite
- Sources pattern: `sources: SourceClients | None = None` with `self.sources.prometheus` and `self.sources.loki` — reuse for Prometheus access
- Code review narrowed except clause in `_check_sandbox_available` — use specific exception handling throughout
- Code review removed dead `_get_model_name()` method from SandboxExecutorStep — do not include unnecessary methods
- 712 passing tests (post code review), 12 pre-existing async failures

**From Story 4-4 (Auto-PR Generation with Evidence Trail):**
- PRGeneratorStep currently at index 9 — moves to index 10 after MetricVerifierStep insertion
- EvidenceTrailFormatter.format_pr_body() has ordered sections — add verification section after sandbox and before audit trail
- Code review removed unused `change_summary` parameter — keep interface clean
- Trust gating at TL3 threshold — reuse exact pattern

**From Story 4-3 (Advisory Test Plan Generation):**
- TestPlannerStep produces `metrics_to_watch` list — MetricVerifierStep reads this as the list of metrics to compare
- `metrics_to_watch` example: `["kube_pod_container_status_restarts_total"]`

### Git Intelligence

Recent commits: `MAESTRO: 4-5 done`, `MAESTRO: implement story 4-5 (Sandbox Test Execution)`, `MAESTRO: fix: QA checkpoint regression — resolve 17 mypy errors`. Follow commit pattern: `MAESTRO: implement story 4-6 (Post-Fix Metric Verification)`. Current test counts: operator 527 passed (4 pre-existing), investigator 712 passed (12 pre-existing async), UI 1,388 passed.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 4, Story 4.6] — User story, acceptance criteria
- [Source: _bmad-output/planning-artifacts/architecture.md#Auto-Remediation Architecture] — FR28: post-fix metric verification, NFR16: rollback within 60s
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Map] — FR28: `investigator/remediation/verifier.py`
- [Source: _bmad-output/planning-artifacts/prd.md#FR28] — System can verify that a fix resolves the issue by monitoring post-fix metrics
- [Source: _bmad-output/planning-artifacts/prd.md#FR62] — System can rollback any autonomous action if post-action metrics show degradation
- [Source: _bmad-output/planning-artifacts/prd.md#NFR16] — Autonomous action rollback within 60 seconds
- [Source: investigator/beeper_investigator/steps/__init__.py] — InvestigationStep protocol, StepResult dataclass
- [Source: investigator/beeper_investigator/remediation/sandbox_executor.py] — SandboxExecutorStep patterns, sources parameter, trust gating
- [Source: investigator/beeper_investigator/remediation/evidence_trail.py] — EvidenceTrailFormatter, format_pr_body() method, section ordering
- [Source: investigator/beeper_investigator/remediation/pr_generator.py] — PRGeneratorStep trust gating, _get_model_name() pattern
- [Source: investigator/beeper_investigator/remediation/test_planner.py] — TestPlannerStep, metrics_to_watch output
- [Source: investigator/beeper_investigator/agent.py] — Agent lifecycle, _build_steps(), SourceClients, pipeline_metadata sharing
- [Source: investigator/beeper_investigator/context.py] — InvestigationContext with trust_level
- [Source: investigator/beeper_investigator/k8s/status.py] — InvestigationStatusUpdater, update_message()
- [Source: investigator/beeper_investigator/sources/prometheus.py] — PrometheusClient.query() method
- [Source: _bmad-output/implementation-artifacts/4-5-sandbox-test-execution.md] — Previous story patterns and lessons

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- All 13 tasks implemented with zero regressions
- 772 tests passing (12 pre-existing async failures unchanged)
- ruff: all checks passed
- mypy: no new errors (8 pre-existing from kubernetes/github/gitlab stubs)
- Fixed 3 test issues during validation: sentinel pattern for sources=None in factory, step count assertions in PR/sandbox integration tests
- MetricVerifierStep inserted at pipeline index 9 (step 10), PRGeneratorStep moved to index 10 (step 11), total 11 steps

### File List

- `investigator/beeper_investigator/remediation/metric_verifier.py` (NEW) — MetricVerifierStep + VerificationResult
- `investigator/beeper_investigator/remediation/evidence_trail.py` (MODIFIED) — Post-Fix Verification section + audit trail update
- `investigator/beeper_investigator/remediation/__init__.py` (MODIFIED) — Added MetricVerifierStep, VerificationResult exports
- `investigator/beeper_investigator/agent.py` (MODIFIED) — Inserted MetricVerifierStep at index 9
- `investigator/tests/test_metric_verifier.py` (NEW) — 47 unit tests across 10 test classes
- `investigator/tests/test_agent_metric_verifier_integration.py` (NEW) — 7 integration tests
- `investigator/tests/test_evidence_trail.py` (MODIFIED) — 6 verification section tests
- `investigator/tests/test_agent_pr_integration.py` (MODIFIED) — Step count 10→11, PR index 9→10
- `investigator/tests/test_agent_sandbox_integration.py` (MODIFIED) — Step count 10→11
- `investigator/tests/test_agent_runbook_integration.py` (MODIFIED) — Step count 10→11
- `investigator/tests/test_agent_testplan_integration.py` (MODIFIED) — Step count 10→11
