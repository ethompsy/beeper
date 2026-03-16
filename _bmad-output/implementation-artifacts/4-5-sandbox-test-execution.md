# Story 4.5: Sandbox Test Execution

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the **system**,
I want to execute advisory test plan steps in an isolated sandbox environment,
so that fixes are validated safely before reaching production.

## Acceptance Criteria

1. **Given** a sandbox namespace configured with NetworkPolicy isolation (NFR13)
   **When** a fix is ready for testing
   **Then** the fix is deployed to the sandbox namespace and sandbox-specific tests are executed
   **And** the sandbox has no access to production data or services (network-isolated)

2. **Given** sandbox test execution
   **When** the tests run
   **Then** results are captured with pass/fail status, logs, and metric comparisons
   **And** the results are attached to the investigation evidence trail

3. **Given** no sandbox environment is configured
   **When** a fix is generated
   **Then** only the advisory test plan (Story 4.3) is produced
   **And** the investigation notes "No sandbox available — manual verification recommended"

## Tasks / Subtasks

- [x] Task 1: Create SandboxExecutorStep class with sandbox availability check (AC: #1, #3)
  - [x] 1.1 Create `investigator/beeper_investigator/remediation/sandbox_executor.py` with `SandboxExecutorStep` class implementing `InvestigationStep` protocol with `name = "Sandbox Test Execution"`
  - [x] 1.2 Constructor: `__init__(self, llm_client: LlmClient, context: InvestigationContext, status_updater: InvestigationStatusUpdater, pipeline_metadata: dict[str, Any] | None = None)` — same signature as TestPlannerStep/PRGeneratorStep
  - [x] 1.3 Implement `_check_sandbox_available() -> str | None`: check `SANDBOX_NAMESPACE` env var first; if not set, attempt K8s `CoreV1Api().read_namespace("beeper-sandbox")` with lazy init (same pattern as PRGeneratorStep's RepositoryLookup); return namespace name if available, None if not. Wrap K8s call in try/except for ApiException (404 = not found, others = log warning). Use `_get_k8s_core_api()` lazy init helper to avoid K8s config loading in tests
  - [x] 1.4 Implement trust-level gating in `execute()`: if `context.trust_level < 3`, return `StepResult(success=True, summary="Sandbox execution skipped — trust level {trust_level} below TL3 threshold", data={"sandbox_executed": False, "skip_reason": "trust_level_insufficient", "trust_level": trust_level})`

- [x] Task 2: Implement test plan prerequisite check and step execution dispatch (AC: #1, #2)
  - [x] 2.1 Check `pipeline_metadata.get("test_plan_generated")` — if False/missing, skip with `skip_reason="no_test_plan"` and summary "No test plan available — sandbox execution skipped"
  - [x] 2.2 Check `pipeline_metadata.get("promotable_to_sandbox")` — if False, skip with `skip_reason="not_promotable"` and summary "Test plan not promotable to sandbox"
  - [x] 2.3 Implement `_execute_verification_steps(sandbox_namespace: str) -> list[dict]`: iterate `pipeline_metadata["verification_steps"]`, dispatch each step by `verification_type` to appropriate executor method, collect results

- [x] Task 3: Implement per-type verification step executors (AC: #1, #2)
  - [x] 3.1 Define `SandboxStepResult` dataclass: `step_number: int`, `title: str`, `status: str` ("pass"|"fail"|"error"|"skipped"), `verification_type: str`, `expected_outcome: str`, `actual_value: str`, `error_message: str | None`, `duration_seconds: float`
  - [x] 3.2 Implement `_execute_metric_check(step: dict, namespace: str) -> SandboxStepResult`: query Prometheus via `sources.prometheus` (if available) using `metric_or_endpoint` field, compare result against `expected_outcome`, return pass/fail. If no Prometheus source, return status="skipped" with note
  - [x] 3.3 Implement `_execute_api_probe(step: dict, namespace: str) -> SandboxStepResult`: HTTP GET via `httpx.Client` to `metric_or_endpoint` within sandbox namespace, check response status and body against `expected_outcome`, return pass/fail
  - [x] 3.4 Implement `_execute_health_check(step: dict, namespace: str) -> SandboxStepResult`: probe health endpoint at `metric_or_endpoint`, check for 200 OK, return pass/fail
  - [x] 3.5 Implement `_execute_log_inspection(step: dict, namespace: str) -> SandboxStepResult`: query Loki via `sources.loki` (if available) for patterns from `action` field scoped to sandbox namespace, compare against `expected_outcome`, return pass/fail. If no Loki source, return status="skipped" with note
  - [x] 3.6 Implement `_execute_manual_verification(step: dict, namespace: str) -> SandboxStepResult`: return status="skipped" with note "Manual verification required — automated sandbox execution not possible for this step"
  - [x] 3.7 Implement dispatch map: `{"metric_check": _execute_metric_check, "api_probe": _execute_api_probe, "health_check": _execute_health_check, "log_inspection": _execute_log_inspection, "manual_verification": _execute_manual_verification}` with fallback to manual_verification for unknown types

- [x] Task 4: Implement result aggregation and evidence attachment (AC: #2, #3)
  - [x] 4.1 Implement `_aggregate_results(step_results: list[SandboxStepResult]) -> str`: compute overall_status — "pass" if all non-skipped passed, "fail" if any failed, "partial" if mix of pass/fail, "skipped" if all skipped
  - [x] 4.2 Return `StepResult.data` with: `sandbox_executed: bool`, `sandbox_namespace: str`, `sandbox_steps_total: int`, `sandbox_steps_passed: int`, `sandbox_steps_failed: int`, `sandbox_steps_skipped: int`, `sandbox_steps_errored: int`, `sandbox_test_results: list[dict]` (serialized SandboxStepResult list), `sandbox_overall_status: str`, `sandbox_duration_seconds: float`, `sandbox_model_tier: str`
  - [x] 4.3 For AC#3 (no sandbox): return `StepResult(success=True, summary="No sandbox available — manual verification recommended", data={"sandbox_executed": False, "skip_reason": "no_sandbox_configured", "advisory_test_plan_only": True})`

- [x] Task 5: Update evidence trail formatter for sandbox results (AC: #2)
  - [x] 5.1 In `investigator/beeper_investigator/remediation/evidence_trail.py`, add a "Sandbox Test Results" section in `format_pr_body()` after the "Advisory Test Plan" section. Read `pipeline_metadata.get("sandbox_executed")` — if True, render a markdown table with columns: Step #, Title, Status, Expected, Actual, Duration. Include overall_status summary at top
  - [x] 5.2 If `sandbox_executed` is False, show skip reason (e.g., "No sandbox available" or "Trust level insufficient")

- [x] Task 6: Update remediation package exports (AC: #1)
  - [x] 6.1 Add `SandboxExecutorStep` and `SandboxStepResult` to `investigator/beeper_investigator/remediation/__init__.py` imports and `__all__`

- [x] Task 7: Integrate SandboxExecutorStep into agent pipeline (AC: #1, #2)
  - [x] 7.1 In `investigator/beeper_investigator/agent.py`, add lazy import for `SandboxExecutorStep` in `_build_steps()`
  - [x] 7.2 Insert `SandboxExecutorStep` as step 9 (index 8) between `TestPlannerStep` (index 7) and `PRGeneratorStep` (moves to index 9). Pass `llm_client`, `context`, `status_updater`, `pipeline_metadata`, and also pass `sources=self.sources` for Prometheus/Loki access
  - [x] 7.3 Update `PRGeneratorStep` position from index 8 to index 9 — no code change needed since it's just list order
  - [x] 7.4 Update step count in existing integration test assertions: 9 → 10

- [x] Task 8: Write comprehensive unit tests (AC: #1, #2, #3)
  - [x] 8.1 Create `investigator/tests/test_sandbox_executor.py` with `_make_step()` factory following established pattern. Factory must accept `pipeline_metadata`, `trust_level`, `sources` overrides. Mock K8s API via `step._k8s_core_api = MagicMock()`
  - [x] 8.2 `TestSandboxAvailability`: env var set → returns namespace, env var not set + K8s namespace exists → returns namespace, env var not set + K8s 404 → returns None, K8s exception → returns None with warning log
  - [x] 8.3 `TestTrustGating`: TL1 skips with reason, TL2 skips with reason, TL3 proceeds, TL4 proceeds, TL5 proceeds
  - [x] 8.4 `TestNoTestPlan`: missing `test_plan_generated` → skip, `test_plan_generated=False` → skip, empty verification_steps → skip
  - [x] 8.5 `TestNotPromotable`: `promotable_to_sandbox=False` → skip
  - [x] 8.6 `TestVerificationStepExecution`: metric_check dispatched correctly, api_probe dispatched, health_check dispatched, log_inspection dispatched, manual_verification returns skipped, unknown type falls back to manual
  - [x] 8.7 `TestResultAggregation`: all pass → overall "pass", any fail → overall "fail", mix → overall "partial", all skipped → overall "skipped"
  - [x] 8.8 `TestNoSandboxGracefulDegradation`: no sandbox namespace → StepResult with "No sandbox available — manual verification recommended", `advisory_test_plan_only=True`
  - [x] 8.9 `TestEvidenceAttachment`: result.data has all required keys, sandbox_test_results is list of dicts with correct fields
  - [x] 8.10 `TestExecuteOrchestration`: full happy path end-to-end with mocked sources and K8s, failure path where Prometheus query fails

- [x] Task 9: Write integration tests (AC: #1, #2)
  - [x] 9.1 Create `investigator/tests/test_agent_sandbox_integration.py`: verify `SandboxExecutorStep` is at index 8 (step 9) in `_build_steps()`, total pipeline length is 10, verify `PRGeneratorStep` is at index 9 (step 10), verify pipeline_metadata shared correctly
  - [x] 9.2 Update `investigator/tests/test_agent_pr_integration.py`: PRGeneratorStep is now step 10 (index 9), total steps 10
  - [x] 9.3 Update `investigator/tests/test_agent_runbook_integration.py`: total steps 9 → 10
  - [x] 9.4 Update `investigator/tests/test_agent_testplan_integration.py`: total steps 9 → 10

- [x] Task 10: Update evidence trail tests (AC: #2)
  - [x] 10.1 In `investigator/tests/test_evidence_trail.py`, add tests for new sandbox results section: `TestSandboxResultsSection` — sandbox_executed=True renders table, sandbox_executed=False shows skip reason, no sandbox data gracefully omitted

- [x] Task 11: Run all investigator tests (AC: #1, #2, #3)
  - [x] 11.1 Run `cd investigator && python -m pytest tests/ -v` — all existing + new tests pass
  - [x] 11.2 Run `cd investigator && python -m ruff check .` — no new warnings
  - [x] 11.3 Run `cd investigator && python -m mypy beeper_investigator/ --strict` — no new errors
  - [x] 11.4 Verify zero regressions in existing step tests

## Dev Notes

### Architecture Patterns to Follow

**CRITICAL CONTEXT: This story adds the SandboxExecutorStep to the investigator pipeline BETWEEN TestPlannerStep (step 8) and PRGeneratorStep (now step 10). Unlike TestPlannerStep which always runs, this step is TRUST-GATED at TL3+. The step reads verification_steps from pipeline_metadata (produced by TestPlannerStep), dispatches each step to the appropriate executor based on verification_type, and captures pass/fail results. If no sandbox namespace is available, it gracefully degrades to advisory-only mode (AC#3). Results flow downstream to PRGeneratorStep via pipeline_metadata for inclusion in the PR evidence trail.**

**What already exists (DO NOT recreate):**

| Component | Location | Status |
|-----------|----------|--------|
| `InvestigationStep` protocol + `StepResult` | `investigator/beeper_investigator/steps/__init__.py` | Done (v0.1.0) |
| 6-step investigation pipeline | `investigator/beeper_investigator/steps/` | Done (v0.1.0) |
| `RunbookExecutorStep` (step 7) | `investigator/beeper_investigator/remediation/runbook_executor.py` | Done (Story 4-2) |
| `TestPlannerStep` (step 8) | `investigator/beeper_investigator/remediation/test_planner.py` | Done (Story 4-3) |
| `PRGeneratorStep` (step 9 → becomes 10) | `investigator/beeper_investigator/remediation/pr_generator.py` | Done (Story 4-4) |
| `EvidenceTrailFormatter` | `investigator/beeper_investigator/remediation/evidence_trail.py` | Done (Story 4-4) — needs sandbox section added |
| `remediation/__init__.py` package | `investigator/beeper_investigator/remediation/__init__.py` | Done — add new exports |
| `InvestigatorAgent` lifecycle + `_build_steps()` | `investigator/beeper_investigator/agent.py` | Done — 9 steps currently, will become 10 |
| `LlmClient` with `select_model()`, `complete_sync()` | `investigator/beeper_investigator/llm/client.py` | Done (v0.1.0) |
| `InvestigationContext` with `trust_level`, `confidence_threshold` | `investigator/beeper_investigator/context.py` | Done (Story 4-2) |
| `InvestigationStatusUpdater` using `CustomObjectsApi` | `investigator/beeper_investigator/k8s/status.py` | Done (v0.1.0) |
| `PrometheusClient` (for metric queries) | `investigator/beeper_investigator/sources/prometheus.py` | Done (v0.1.0) |
| `LokiClient` (for log queries) | `investigator/beeper_investigator/sources/loki.py` | Done (v0.1.0) |
| `SourceClients` (prometheus + loki) | `investigator/beeper_investigator/agent.py` | Done — passed to steps as `sources` |
| `RepositoryLookup` + lazy K8s init pattern | `investigator/beeper_investigator/k8s/repository.py` | Done (Story 4-4) — follow lazy init pattern |
| `TestPlanStep` + `AdvisoryTestPlan` dataclasses | `investigator/beeper_investigator/remediation/test_planner.py` | Done (Story 4-3) |

**What this story adds:**

| Component | Description |
|-----------|-------------|
| `remediation/sandbox_executor.py` | `SandboxExecutorStep` — trust-gated sandbox test execution with per-type verification dispatching |
| `SandboxStepResult` dataclass | Per-step result with pass/fail/error/skipped status and timing |
| Evidence trail sandbox section | Sandbox results rendered in PR body via `EvidenceTrailFormatter` |
| Agent pipeline step 9 | `SandboxExecutorStep` wired into `_build_steps()` between TestPlanner and PRGenerator |
| Tests | Unit + integration tests for all new components |

### Pipeline Metadata — Data Flow (CRITICAL)

The `pipeline_metadata` dict is shared by reference across all steps. After prior steps run, it contains:

```python
# Available from step 8 (TestPlannerStep) — the key INPUT for this step:
{
    "test_plan_generated": True,         # SandboxExecutorStep checks this first
    "verification_steps": [              # SandboxExecutorStep iterates these
        {
            "step_number": 1,
            "title": "Check pod restart count",
            "description": "Verify pod restarts decreased",
            "action": "kubectl get pods -n {namespace} -o json | jq '.items[].status.containerStatuses[].restartCount'",
            "expected_outcome": "Pod restart count is 0 after fix applied",
            "metric_or_endpoint": "kube_pod_container_status_restarts_total",
            "verification_type": "metric_check",
            "status": "pending",         # SandboxExecutorStep updates this
        }
    ],
    "metrics_to_watch": ["kube_pod_container_status_restarts_total"],
    "estimated_duration_minutes": 15,
    "promotable_to_sandbox": True,       # SandboxExecutorStep checks this
}

# SandboxExecutorStep will ADD to pipeline_metadata:
{
    "sandbox_executed": True,                      # PRGeneratorStep checks this
    "sandbox_namespace": "beeper-sandbox",
    "sandbox_steps_total": 5,
    "sandbox_steps_passed": 4,
    "sandbox_steps_failed": 0,
    "sandbox_steps_skipped": 1,
    "sandbox_steps_errored": 0,
    "sandbox_test_results": [
        {
            "step_number": 1,
            "title": "Check pod restart count",
            "status": "pass",            # "pass"|"fail"|"error"|"skipped"
            "verification_type": "metric_check",
            "expected_outcome": "Pod restart count is 0",
            "actual_value": "0",
            "error_message": None,
            "duration_seconds": 2.3,
        }
    ],
    "sandbox_overall_status": "pass",    # "pass"|"fail"|"partial"|"skipped"
    "sandbox_duration_seconds": 12.5,
    "sandbox_model_tier": "remediation",
}
```

### Constructor Signature — MUST Extend Standard Pattern

Unlike TestPlannerStep/PRGeneratorStep, SandboxExecutorStep needs access to Prometheus and Loki clients for verification queries. Add `sources: SourceClients` parameter:

```python
from beeper_investigator.agent import SourceClients

class SandboxExecutorStep:
    """Execute advisory test plan in isolated sandbox environment."""

    name: str = "Sandbox Test Execution"

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
        self._k8s_core_api: Any | None = None  # Lazy init to avoid K8s config in tests
```

### Lazy K8s Init Pattern (follow RepositoryLookup / PRGeneratorStep)

```python
def _get_k8s_core_api(self) -> Any:
    """Lazy-initialize K8s CoreV1Api."""
    if self._k8s_core_api is None:
        from kubernetes import client, config  # type: ignore[import-untyped]
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        self._k8s_core_api = client.CoreV1Api()
    return self._k8s_core_api
```

### Sandbox Namespace Detection

```python
def _check_sandbox_available(self) -> str | None:
    """Check if sandbox namespace is available."""
    # 1. Check env var first (fastest)
    ns = os.environ.get("SANDBOX_NAMESPACE")
    if ns:
        logger.info("Sandbox namespace from env: %s", ns)
        return ns

    # 2. Fall back to K8s API probe for "beeper-sandbox"
    try:
        api = self._get_k8s_core_api()
        api.read_namespace("beeper-sandbox")
        logger.info("Sandbox namespace detected via K8s API: beeper-sandbox")
        return "beeper-sandbox"
    except Exception:
        logger.info("No sandbox namespace available")
        return None
```

### Trust-Level Gating (follow PRGeneratorStep pattern exactly)

```python
# In execute():
if self.context.trust_level < 3:
    return StepResult(
        success=True,
        summary=f"Sandbox execution skipped — trust level {self.context.trust_level} below TL3 threshold",
        data={"sandbox_executed": False, "skip_reason": "trust_level_insufficient", "trust_level": self.context.trust_level},
    )
```

### Verification Step Dispatch

```python
_EXECUTORS = {
    "metric_check": "_execute_metric_check",
    "api_probe": "_execute_api_probe",
    "health_check": "_execute_health_check",
    "log_inspection": "_execute_log_inspection",
    "manual_verification": "_execute_manual_verification",
}

def _dispatch_step(self, step: dict, namespace: str) -> SandboxStepResult:
    vtype = step.get("verification_type", "manual_verification")
    executor_name = self._EXECUTORS.get(vtype, "_execute_manual_verification")
    executor = getattr(self, executor_name)
    return executor(step, namespace)
```

### Evidence Trail Enhancement

Add to `EvidenceTrailFormatter.format_pr_body()` after the Advisory Test Plan section:

```python
# Sandbox Test Results
if pipeline_metadata.get("sandbox_executed"):
    overall = pipeline_metadata.get("sandbox_overall_status", "unknown")
    results = pipeline_metadata.get("sandbox_test_results", [])
    sections.append(f"### Sandbox Test Results\n**Overall: {overall.upper()}**\n")
    # Render results table...
elif pipeline_metadata.get("sandbox_executed") is False:
    reason = pipeline_metadata.get("skip_reason", "unknown")
    sections.append(f"### Sandbox Test Results\n*Skipped: {reason}*\n")
```

### Critical Guardrails

- **Trust-gated**: TL3+ required for sandbox execution. TL1-2 skip entirely (advisory-only)
- **Sandbox isolation (NFR13)**: Sandbox namespace must have NetworkPolicy isolation — this story does NOT create the namespace/NetworkPolicy (that's helm/infrastructure), it only executes tests within it
- **No LLM calls needed**: This step dispatches to Prometheus/Loki/HTTP — no LLM interpretation of results. The LLM client is passed for protocol consistency but not used
- **Graceful degradation (AC#3)**: No sandbox → return advisory-only result with "No sandbox available — manual verification recommended"
- **Source client availability**: If Prometheus or Loki is not configured, metric_check and log_inspection steps return "skipped" — not error. HTTP probes (api_probe, health_check) can still execute
- **Timing**: Each step tracks `duration_seconds` via `time.monotonic()` for performance observability
- **Non-fatal**: All `StepResult` returns have `success=True` — sandbox failures are soft (don't crash pipeline)
- **`_get_model_name()` pattern**: Include for consistency even though no LLM calls are made in this step
- **Structured JSON logging** via `logging.getLogger(__name__)`
- **Pipeline position**: Step 9 (index 8) — between TestPlannerStep (7) and PRGeneratorStep (now 10)
- **Zero regressions** — all existing 667 investigator tests must continue passing
- **ruff clean** — no new warnings
- **mypy strict** — must pass strict mode (no new errors)
- **No new dependencies** — kubernetes (K8s), httpx, and source clients already in pyproject.toml

### Test Pattern (follow existing test_pr_generator.py / test_test_planner.py)

```python
from beeper_investigator.agent import SourceClients

def _make_step(pipeline_metadata=None, trust_level=3, sources=None, **overrides):
    """Factory for SandboxExecutorStep with mocked dependencies."""
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
    step = SandboxExecutorStep(**defaults)
    # Mock out K8s API to avoid cluster config in unit tests
    step._k8s_core_api = MagicMock()
    return step, defaults


def _sample_verification_steps():
    """Sample verification steps from TestPlannerStep pipeline_metadata."""
    return [
        {
            "step_number": 1,
            "title": "Check pod restart count",
            "description": "Verify pod restarts decreased after fix",
            "action": "query kube_pod_container_status_restarts_total",
            "expected_outcome": "Restart count is 0",
            "metric_or_endpoint": "kube_pod_container_status_restarts_total",
            "verification_type": "metric_check",
            "status": "pending",
        },
        {
            "step_number": 2,
            "title": "Health endpoint check",
            "description": "Verify service health endpoint returns 200",
            "action": "GET /health",
            "expected_outcome": "HTTP 200 OK",
            "metric_or_endpoint": "http://payments.beeper-sandbox:8080/health",
            "verification_type": "health_check",
            "status": "pending",
        },
    ]


def _sample_pipeline_metadata():
    """Full pipeline_metadata with test plan generated."""
    return {
        "test_plan_generated": True,
        "promotable_to_sandbox": True,
        "verification_steps": _sample_verification_steps(),
        "metrics_to_watch": ["kube_pod_container_status_restarts_total"],
        "estimated_duration_minutes": 15,
    }
```

### Project Structure Notes

- New file: `investigator/beeper_investigator/remediation/sandbox_executor.py`
- Modified: `investigator/beeper_investigator/remediation/__init__.py` (add SandboxExecutorStep + SandboxStepResult exports)
- Modified: `investigator/beeper_investigator/remediation/evidence_trail.py` (add sandbox results section)
- Modified: `investigator/beeper_investigator/agent.py` (insert step 9, PRGeneratorStep moves to 10)
- New test: `investigator/tests/test_sandbox_executor.py`
- New test: `investigator/tests/test_agent_sandbox_integration.py`
- Modified test: `investigator/tests/test_agent_pr_integration.py` (step count 9 → 10)
- Modified test: `investigator/tests/test_agent_runbook_integration.py` (step count 9 → 10)
- Modified test: `investigator/tests/test_agent_testplan_integration.py` (step count 9 → 10)
- Modified test: `investigator/tests/test_evidence_trail.py` (sandbox results section tests)

### Previous Story Intelligence

**From Story 4-4 (Auto-PR Generation with Evidence Trail):**
- Established PRGeneratorStep as step 9 — SandboxExecutorStep inserts before it (step 9), PRGeneratorStep moves to step 10
- Lazy K8s init pattern via `_get_repository_lookup()` — follow with `_get_k8s_core_api()` for sandbox
- Trust gating at TL3 threshold — reuse exact pattern
- EvidenceTrailFormatter reads pipeline_metadata for evidence sections — extend with sandbox results
- Code review narrowed except clauses — use specific exception types (ApiException for K8s)
- Code review removed unused parameters — keep interface clean
- 655 passing tests (post QA checkpoint: 667 passed, 3 skipped)

**From Story 4-3 (Advisory Test Plan Generation):**
- TestPlannerStep produces `verification_steps` with `status: "pending"` — SandboxExecutorStep reads these
- `promotable_to_sandbox=True` always set — SandboxExecutorStep checks this flag
- TestPlanStep dataclass has fields: step_number, title, description, action, expected_outcome, metric_or_endpoint, verification_type
- `_get_model_name()` pattern with "remediation" → "deep_rca" fallback — include for consistency
- Code review eliminated double `_get_model_name()` call — resolve once if needed
- Added warning logging for non-dict entries — add same defensive logging

**From Story 4-2 (Human-Language Runbook Execution):**
- Trust gating: TL1-2 advisory, TL3+ action — SandboxExecutorStep follows same TL3 threshold
- Established `remediation/` package — extend with sandbox_executor.py
- Code review found misleading test names — use precise names describing actual behavior

**From Story 4-1 (Repository CRD & Git Provider Integration):**
- K8s API patterns established — follow for namespace detection
- 4 pre-existing operator test failures (unrelated to Python stories)

### Git Intelligence

Recent commits: `MAESTRO: fix: QA checkpoint regression — resolve 17 mypy errors`, `MAESTRO: 4-4 done`, `MAESTRO: implement story 4-4 (Auto-PR Generation with Evidence Trail)`. Follow commit pattern: `MAESTRO: implement story 4-5 (Sandbox Test Execution)`. Current test counts: operator 527 passed (4 pre-existing), investigator 667 passed + 3 skipped (12 pre-existing async), UI 1,388 passed.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 4, Story 4.5] — User story, acceptance criteria
- [Source: _bmad-output/planning-artifacts/architecture.md#Auto-Remediation Architecture] — FR27: sandbox test execution, NFR13: NetworkPolicy isolation
- [Source: _bmad-output/planning-artifacts/architecture.md#Trust System Architecture] — TL3+ for sandbox execution
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Map] — FR27: `investigator/remediation/sandbox_executor.py`
- [Source: investigator/beeper_investigator/steps/__init__.py] — InvestigationStep protocol, StepResult dataclass
- [Source: investigator/beeper_investigator/remediation/test_planner.py] — TestPlannerStep, TestPlanStep, AdvisoryTestPlan, verification_steps format, promotable_to_sandbox
- [Source: investigator/beeper_investigator/remediation/pr_generator.py] — PRGeneratorStep trust gating pattern, lazy K8s init
- [Source: investigator/beeper_investigator/remediation/evidence_trail.py] — EvidenceTrailFormatter, format_pr_body() method
- [Source: investigator/beeper_investigator/agent.py] — Agent lifecycle, _build_steps(), SourceClients, pipeline_metadata sharing
- [Source: investigator/beeper_investigator/k8s/repository.py] — Lazy K8s init pattern
- [Source: investigator/beeper_investigator/k8s/status.py] — K8s API pattern, CustomObjectsApi
- [Source: investigator/beeper_investigator/context.py] — InvestigationContext with trust_level, confidence_threshold
- [Source: investigator/beeper_investigator/sources/prometheus.py] — PrometheusClient for metric queries
- [Source: investigator/beeper_investigator/sources/loki.py] — LokiClient for log queries
- [Source: investigator/pyproject.toml] — Current dependencies (kubernetes, httpx already present)
- [Source: _bmad-output/implementation-artifacts/4-4-auto-pr-generation-evidence-trail.md] — Previous story patterns and lessons

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- All 11 tasks implemented successfully
- 54 new tests across 3 test files (41 sandbox_executor + 7 agent_sandbox_integration + 6 evidence_trail sandbox)
- Updated 3 existing integration test files (step count 9 → 10, PR step index 8 → 9)
- Total suite: 709 passed, 12 failed (all pre-existing async), 3 skipped
- Ruff clean — zero warnings
- Zero regressions in existing tests
- Lazy K8s CoreV1Api initialization to avoid cluster config in tests
- SandboxExecutorStep inserted as step 9 (index 8) between TestPlannerStep and PRGeneratorStep
- Evidence trail formatter enhanced with sandbox results table section
- Graceful degradation when no sandbox namespace available (AC#3)
- Trust gating at TL3+ following PRGeneratorStep pattern

### File List

- `investigator/beeper_investigator/remediation/sandbox_executor.py` (NEW) — SandboxExecutorStep + SandboxStepResult with per-type verification dispatching
- `investigator/beeper_investigator/remediation/__init__.py` (MODIFIED) — Added SandboxExecutorStep + SandboxStepResult exports
- `investigator/beeper_investigator/remediation/evidence_trail.py` (MODIFIED) — Added sandbox test results section in format_pr_body()
- `investigator/beeper_investigator/agent.py` (MODIFIED) — Added SandboxExecutorStep as step 9 (index 8), lazy import
- `investigator/tests/test_sandbox_executor.py` (NEW) — 41 unit tests
- `investigator/tests/test_agent_sandbox_integration.py` (NEW) — 7 integration tests
- `investigator/tests/test_evidence_trail.py` (MODIFIED) — 6 new sandbox results section tests
- `investigator/tests/test_agent_pr_integration.py` (MODIFIED) — Step count 9 → 10, PR step index 8 → 9
- `investigator/tests/test_agent_testplan_integration.py` (MODIFIED) — Step count 9 → 10
- `investigator/tests/test_agent_runbook_integration.py` (MODIFIED) — Step count 9 → 10
