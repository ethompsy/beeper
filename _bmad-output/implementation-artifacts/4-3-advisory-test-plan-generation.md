# Story 4.3: Advisory Test Plan Generation

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the **system**,
I want to always produce an advisory test plan describing how to verify a hypothesis,
so that even without a sandbox, SREs know exactly how to validate Beeper's conclusions.

## Acceptance Criteria

1. **Given** an investigation that reaches a root cause hypothesis
   **When** the investigation conclusion is generated
   **Then** an advisory test plan is included with: hypothesis statement, verification steps, expected outcomes, and metrics to watch
   **And** the test plan is generated regardless of trust level or sandbox availability

2. **Given** an advisory test plan
   **When** displayed in the investigation detail view
   **Then** steps are numbered, actionable, and reference specific metrics/endpoints
   **And** the SRE can mark steps as completed or skipped

3. **Given** the advisory test plan
   **When** a sandbox environment is available (Story 4.5)
   **Then** the test plan can be promoted to automated sandbox execution

## Tasks / Subtasks

- [x] Task 1: Create TestPlannerStep class in remediation package (AC: #1)
  - [x] 1.1 Create `investigator/beeper_investigator/remediation/test_planner.py` with `TestPlannerStep` class implementing `InvestigationStep` protocol with `name = "Test Plan Design"`
  - [x] 1.2 Constructor: `__init__(self, llm_client: LlmClient, context: InvestigationContext, status_updater: InvestigationStatusUpdater, pipeline_metadata: dict[str, Any] | None = None)` — note: no `kb_client` needed (test plan is synthesized from pipeline_metadata, not searched from KB)
  - [x] 1.3 Define `TestPlanStep` dataclass: `step_number: int`, `title: str`, `description: str`, `action: str`, `expected_outcome: str`, `metric_or_endpoint: str`, `verification_type: str` (one of: "metric_check", "log_inspection", "api_probe", "health_check", "manual_verification")
  - [x] 1.4 Define `AdvisoryTestPlan` dataclass: `hypothesis_statement: str`, `confidence_level: str`, `confidence_percentage: int`, `verification_steps: list[TestPlanStep]`, `expected_outcomes: list[str]`, `metrics_to_watch: list[str]`, `estimated_duration_minutes: int`, `promotable_to_sandbox: bool`

- [x] Task 2: Extract RCA hypothesis data from pipeline_metadata (AC: #1)
  - [x] 2.1 Implement `_extract_hypothesis_context(self) -> dict | None`: read from `self.pipeline_metadata` the keys: `root_cause_hypothesis`, `confidence_level`, `confidence_percentage`, `supporting_evidence`, `alternative_hypotheses`, `additional_data_needs`
  - [x] 2.2 If `root_cause_hypothesis` is missing or empty, return `StepResult(success=True, summary="No RCA hypothesis available — test plan generation skipped", data={"test_plan_generated": False, "skip_reason": "no_hypothesis"})`
  - [x] 2.3 Also extract signal context if available: `signal_summary`, `service_dependency_chain`, `layers_queried` from pipeline_metadata (enriches test plan quality)

- [x] Task 3: Implement LLM-based test plan generation (AC: #1, #2)
  - [x] 3.1 Define `_TEST_PLAN_SYSTEM_PROMPT`: instruct LLM to act as senior SRE designing verification steps for an RCA hypothesis. Output must be JSON with: `hypothesis_statement`, `verification_steps` (list of numbered, actionable steps each with `step_number`, `title`, `description`, `action`, `expected_outcome`, `metric_or_endpoint`, `verification_type`), `expected_outcomes`, `metrics_to_watch`, `estimated_duration_minutes`
  - [x] 3.2 Define `_TEST_PLAN_USER_TEMPLATE`: include investigation context (condition, service, severity, namespace), RCA hypothesis, confidence level/percentage, supporting evidence, alternative hypotheses, signal context
  - [x] 3.3 Implement `_generate_test_plan(self, hypothesis_context: dict) -> AdvisoryTestPlan`: call `llm_client.complete_sync()` with `remediation` model tier, `temperature=0.0`, `max_tokens=2048`, parse JSON response into `AdvisoryTestPlan`
  - [x] 3.4 Implement `_parse_test_plan_response(self, raw: str) -> AdvisoryTestPlan`: strip markdown fences, parse JSON, validate required fields, construct `AdvisoryTestPlan` with `TestPlanStep` objects. On parse failure, return a minimal fallback plan with a single "manual investigation" step

- [x] Task 4: Implement TestPlannerStep.execute() orchestration (AC: #1, #2, #3)
  - [x] 4.1 Wire `execute()`: extract hypothesis context → generate test plan → return StepResult
  - [x] 4.2 Set `promotable_to_sandbox = True` always (actual sandbox availability check is Story 4-5's responsibility)
  - [x] 4.3 Return `StepResult.data` with: `test_plan_generated: bool`, `hypothesis_statement: str`, `confidence_level: str`, `confidence_percentage: int`, `verification_steps: list[dict]` (each step serialized with all fields including `step_number`, `title`, `action`, `expected_outcome`, `metric_or_endpoint`, `verification_type`, plus `status: "pending"` for SRE tracking per AC#2), `expected_outcomes: list[str]`, `metrics_to_watch: list[str]`, `estimated_duration_minutes: int`, `promotable_to_sandbox: bool`, `steps_total: int`, `test_plan_model_tier: str`, `test_plan_model_used: str`
  - [x] 4.4 Build summary: "Advisory test plan generated: {N} verification steps for hypothesis '{hypothesis}' (confidence: {level})" or fallback summary if skipped

- [x] Task 5: Update remediation package exports (AC: #1)
  - [x] 5.1 Add `TestPlannerStep` to `investigator/beeper_investigator/remediation/__init__.py` imports and `__all__`

- [x] Task 6: Integrate TestPlannerStep into agent pipeline (AC: #1)
  - [x] 6.1 In `investigator/beeper_investigator/agent.py`, add `TestPlannerStep` as step 8 after `RunbookExecutorStep` in `_build_steps()`. Always include — test plans are generated regardless of trust level per AC#1.
  - [x] 6.2 Import `TestPlannerStep` lazily in `_build_steps()` following existing pattern
  - [x] 6.3 Pass `pipeline_metadata`, `llm_client`, `context`, `status_updater` to constructor (no kb_client)

- [x] Task 7: Write comprehensive tests (AC: #1, #2, #3)
  - [x] 7.1 Create `investigator/tests/test_test_planner.py` with test classes:
    - `TestHypothesisExtraction`: no hypothesis in pipeline_metadata returns skip, hypothesis extracted correctly, partial metadata handled gracefully (missing alternative_hypotheses etc.)
    - `TestTestPlanGeneration`: LLM response parsed into AdvisoryTestPlan correctly, verification steps have all required fields, invalid JSON falls back to minimal plan, empty steps list handled, metrics_to_watch populated
    - `TestVerificationStepStructure`: each step has step_number/title/action/expected_outcome/metric_or_endpoint/verification_type, step status defaults to "pending", verification_type is valid enum value
    - `TestExecuteOrchestration`: full happy path (hypothesis found → plan generated → StepResult returned), no hypothesis path (skipped), LLM failure path (fallback plan), promotable_to_sandbox always True
    - `TestSandboxPromotion`: test plan data includes promotable_to_sandbox flag, verification_steps serialized for sandbox consumption (Story 4-5 forward-compat)
  - [x] 7.2 Create `investigator/tests/test_agent_testplan_integration.py`: verify TestPlannerStep is step 8 in `_build_steps()`, verify pipeline_metadata is shared (hypothesis data flows from RCA step), verify step is always included regardless of trust level

- [x] Task 8: Run all investigator tests (AC: #1, #2, #3)
  - [x] 8.1 Run `cd investigator && python -m pytest tests/ -v` — all existing + new tests pass
  - [x] 8.2 Run `cd investigator && python -m ruff check .` — no new warnings
  - [x] 8.3 Verify zero regressions in existing step tests

## Dev Notes

### Architecture Patterns to Follow

**CRITICAL CONTEXT: This story adds the TestPlannerStep to the investigator pipeline. Unlike RunbookExecutorStep (4-2) which searches KB for runbooks, this step synthesizes an advisory test plan from the RCA hypothesis already in pipeline_metadata. The test plan is ALWAYS generated regardless of trust level — this is the key differentiator. The plan provides numbered, actionable steps SREs can follow to verify Beeper's conclusions.**

**What already exists (DO NOT recreate):**

| Component | Location | Status |
|-----------|----------|--------|
| `InvestigationStep` protocol + `StepResult` | `investigator/beeper_investigator/steps/__init__.py` | Done (v0.1.0) |
| 6-step investigation pipeline | `investigator/beeper_investigator/steps/` | Done (v0.1.0) |
| `RunbookExecutorStep` (step 7) | `investigator/beeper_investigator/remediation/runbook_executor.py` | Done (Story 4-2) |
| `remediation/__init__.py` package | `investigator/beeper_investigator/remediation/__init__.py` | Done (Story 4-2) |
| `InvestigatorAgent` lifecycle + `_build_steps()` | `investigator/beeper_investigator/agent.py` | Done — 7 steps currently |
| `LlmClient` with `select_model()`, `complete_sync()` | `investigator/beeper_investigator/llm/client.py` | Done (v0.1.0) |
| `InvestigationContext` with `trust_level`, `confidence_threshold` | `investigator/beeper_investigator/context.py` | Done (Story 4-2) |
| `InvestigationStatusUpdater` | `investigator/beeper_investigator/k8s/status.py` | Done (v0.1.0) |
| `RCAHypothesisStep` (populates pipeline_metadata with hypothesis) | `investigator/beeper_investigator/steps/rca_hypothesis.py` | Done (v0.1.0) |

**What this story adds:**

| Component | Description |
|-----------|-------------|
| `remediation/test_planner.py` | `TestPlannerStep` — synthesize advisory test plan from RCA hypothesis |
| `TestPlanStep` dataclass | Individual verification step with action, outcome, metric |
| `AdvisoryTestPlan` dataclass | Complete test plan with hypothesis, steps, metrics |
| Agent pipeline step 8 | `TestPlannerStep` wired into `_build_steps()` |
| Tests for test planner | Comprehensive unit + integration tests |

### Pipeline Metadata — Data Flow (CRITICAL)

The `pipeline_metadata` dict is shared by reference across all steps. After `RCAHypothesisStep` (step 4) runs, it contains:

```python
# Available in pipeline_metadata after step 4 (RCAHypothesisStep):
{
    "root_cause_hypothesis": "Memory leak in connection pool causing OOM kills",
    "confidence_level": "high",          # "high"|"medium"|"low"
    "confidence_percentage": 85,          # 0-100
    "supporting_evidence": ["Pod restarts correlate with memory growth", ...],
    "alternative_hypotheses": [{"description": "...", "confidence_percentage": 40}, ...],
    "additional_data_needs": ["Heap dump analysis", ...],
    "kb_citation": "kb-entry-123",
    "synthesis_source": "llm",
    "rca_model_tier": "deep_rca",
    "rca_model_used": "claude-opus-4",
}

# Also available from earlier steps:
{
    "customer_impacting": True,           # from CustomerImpactStep
    "signal_summary": "...",              # from SignalCorrelationStep
    "service_dependency_chain": [...],    # from SignalCorrelationStep
    "layers_queried": [...],              # from SignalCorrelationStep
}
```

### Step Protocol Pattern (MUST follow exactly)

```python
class TestPlannerStep:
    """Generate advisory test plan from RCA hypothesis."""

    name: str = "Test Plan Design"

    def __init__(
        self,
        llm_client: LlmClient,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
        pipeline_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.context = context
        self.status_updater = status_updater
        self.pipeline_metadata = pipeline_metadata if pipeline_metadata is not None else {}

    def execute(self) -> StepResult:
        """Generate advisory test plan."""
        ...
```

### LLM Call Pattern (follow RunbookExecutorStep exactly)

```python
model_name = self.llm_client.select_model("remediation")
raw = self.llm_client.complete_sync(
    messages,
    max_tokens=2048,
    temperature=0.0,
    model=model_name,
)
```

### Test Plan Output Schema (for StepResult.data)

```python
# StepResult.data structure:
{
    "test_plan_generated": True,
    "hypothesis_statement": "Memory leak in connection pool...",
    "confidence_level": "high",
    "confidence_percentage": 85,
    "verification_steps": [
        {
            "step_number": 1,
            "title": "Check current memory utilization",
            "description": "Query Prometheus for container memory...",
            "action": "PromQL: container_memory_working_set_bytes{pod=~'service-.*'}",
            "expected_outcome": "Memory usage above 80% of limit",
            "metric_or_endpoint": "container_memory_working_set_bytes",
            "verification_type": "metric_check",
            "status": "pending",  # SRE tracking (AC#2)
        },
        # ... more steps
    ],
    "expected_outcomes": ["Memory usage decreases after fix", ...],
    "metrics_to_watch": ["container_memory_working_set_bytes", "container_restarts_total", ...],
    "estimated_duration_minutes": 15,
    "promotable_to_sandbox": True,  # AC#3 — always True
    "steps_total": 5,
    "test_plan_model_tier": "remediation",
    "test_plan_model_used": "claude-opus-4",
}
```

### Verification Type Enum Values

```python
VALID_VERIFICATION_TYPES = {
    "metric_check",          # Query Prometheus/metrics endpoint
    "log_inspection",        # Check log patterns in Loki/stdout
    "api_probe",             # Hit HTTP endpoint, check response
    "health_check",          # K8s readiness/liveness probe check
    "manual_verification",   # Requires human visual/manual check
}
```

### Critical Guardrails

- **ALWAYS generate test plan** — regardless of trust level. This is advisory output, not a mutation. AC#1 is explicit: "generated regardless of trust level or sandbox availability"
- **No KB dependency** — unlike RunbookExecutorStep, TestPlannerStep does NOT search KB. It synthesizes from pipeline_metadata RCA hypothesis data
- **No actual test execution** — this story generates the PLAN only. Sandbox execution is Story 4-5
- **`promotable_to_sandbox` always True** — the actual sandbox check is Story 4-5's responsibility
- **Each step must have `status: "pending"`** — for SRE tracking in UI (AC#2: "SRE can mark steps as completed or skipped")
- **`temperature=0.0`** for LLM calls — deterministic plan generation
- **No new pip dependencies** — use existing pydantic, litellm
- **Follow `InvestigationStep` protocol** exactly — `name` class attribute + `execute() -> StepResult`
- **Structured JSON logging** for plan generation (matches architecture pattern)
- **PII scrubbing** happens in LlmClient — no need to scrub in step code
- **Zero regressions** — all existing 543 investigator tests must continue passing
- **ruff clean** — no new warnings

### Test Pattern (follow existing test_runbook_executor.py)

```python
class TestHypothesisExtraction:
    def _make_step(self, pipeline_metadata=None, **overrides):
        """Factory for TestPlannerStep with mocked dependencies."""
        llm = MagicMock(spec=LlmClient)
        ctx = InvestigationContext(
            investigation_id="test-inv-001",
            namespace="default",
            condition="high_latency",
            service="payments",
            severity="high",
            trust_level=1,
            confidence_threshold=0.9,
        )
        status = MagicMock(spec=InvestigationStatusUpdater)
        defaults = {
            "llm_client": llm,
            "context": ctx,
            "status_updater": status,
            "pipeline_metadata": pipeline_metadata or {},
        }
        defaults.update(overrides)
        return TestPlannerStep(**defaults), defaults
```

### Project Structure Notes

- New file: `investigator/beeper_investigator/remediation/test_planner.py`
- Modified: `investigator/beeper_investigator/remediation/__init__.py` (add TestPlannerStep export)
- Modified: `investigator/beeper_investigator/agent.py` (add step 8)
- New test: `investigator/tests/test_test_planner.py`
- New test: `investigator/tests/test_agent_testplan_integration.py`

### Previous Story Intelligence

**From Story 4-2 (Human-Language Runbook Execution):**
- Established `remediation/` package structure — extend it, do NOT recreate
- RunbookExecutorStep pattern: class-level `name`, `__init__` with dependencies, `execute()` returning StepResult
- LLM prompt pattern: system prompt + user template, JSON output, markdown fence stripping
- Trust gating: TL1-2 advisory, TL3+ conditional — but TestPlannerStep has NO trust gating (always runs)
- Test patterns: factory functions, MagicMock dependencies, test class organization
- Pipeline integration: lazy import in `_build_steps()`, pass metadata/clients/context/status_updater
- Code review found misleading test names — use precise test names that describe actual behavior
- Code review added `#[instrument]` tracing — add structured logging to key methods

**From Story 4-1 (Repository CRD & Git Provider Integration):**
- 4 pre-existing operator test failures (unrelated to this Python story)
- 12 pre-existing async investigator test failures in `test_llm_client.py` and `test_kb_client.py`
- These are NOT caused by this story — do not attempt to fix

### Git Intelligence

Recent commits: `MAESTRO: 4-2 done`, `MAESTRO: implement story 4-2 (Human-Language Runbook Execution)`. Follow commit pattern: `MAESTRO: implement story 4-3 (Advisory Test Plan Generation)`. Current test counts: operator 527 passed (4 pre-existing), investigator 543 passed (12-13 pre-existing), UI 1,388 passed.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 4, Story 4.3] — User story, acceptance criteria
- [Source: _bmad-output/planning-artifacts/architecture.md#Auto-Remediation Architecture] — Remediation pipeline design, test plan as remediation extension step
- [Source: _bmad-output/planning-artifacts/architecture.md#Trust System Architecture] — Trust levels TL1-TL5 (test plan ignores trust gating — always advisory)
- [Source: _bmad-output/planning-artifacts/architecture.md#LLM Integration] — Remediation model tier (claude-opus-4)
- [Source: investigator/beeper_investigator/steps/__init__.py] — InvestigationStep protocol, StepResult dataclass
- [Source: investigator/beeper_investigator/steps/rca_hypothesis.py] — RCA hypothesis output keys in pipeline_metadata
- [Source: investigator/beeper_investigator/remediation/runbook_executor.py] — Closest pattern reference for remediation step
- [Source: investigator/beeper_investigator/agent.py] — Agent lifecycle, _build_steps(), pipeline_metadata sharing
- [Source: investigator/beeper_investigator/llm/client.py] — LlmClient.select_model(), complete_sync()
- [Source: investigator/beeper_investigator/context.py] — InvestigationContext dataclass
- [Source: _bmad-output/implementation-artifacts/4-2-human-language-runbook-execution.md] — Previous story patterns and lessons

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- All 8 tasks implemented with zero regressions
- Created TestPlannerStep with TestPlanStep and AdvisoryTestPlan dataclasses
- TestPlannerStep synthesizes advisory test plans from RCA hypothesis in pipeline_metadata via LLM
- Always generates regardless of trust level (no trust gating — purely advisory)
- Each verification step includes: step_number, title, description, action, expected_outcome, metric_or_endpoint, verification_type, status="pending" for SRE tracking
- Fallback plan generated when LLM parsing fails (single manual_verification step)
- promotable_to_sandbox always True (forward-compat with Story 4-5)
- Integrated as step 8 in agent pipeline after RunbookExecutorStep
- Updated existing test_agent_runbook_integration.py to reflect 8-step pipeline
- 34 new tests (30 unit + 4 integration), all passing
- Full suite: 577 passed, 12 pre-existing failures (async/ordering), 0 new regressions
- Ruff clean — no lint warnings

### File List

- `investigator/beeper_investigator/remediation/test_planner.py` — New: TestPlannerStep, TestPlanStep, AdvisoryTestPlan
- `investigator/beeper_investigator/remediation/__init__.py` — Modified: added TestPlannerStep export
- `investigator/beeper_investigator/agent.py` — Modified: added TestPlannerStep as step 8
- `investigator/tests/test_test_planner.py` — New: 30 tests across 6 test classes
- `investigator/tests/test_agent_testplan_integration.py` — New: 4 pipeline integration tests
- `investigator/tests/test_agent_runbook_integration.py` — Modified: updated step count assertion from 7 to 8
