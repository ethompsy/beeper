# Story 3.3: Customer Impact Assessment

Status: done

## Story

As an Investigator,
I want to assess whether a detected condition has customer impact,
so that I can prioritize appropriately and focus on real issues.

## Acceptance Criteria

1. **Given** a suspicious condition is detected, **When** the investigator starts, **Then** it first assesses customer impact (FR3) **And** uses lightweight LLM model for initial screening (FR43).

2. **Given** the condition affects customer-facing services, **When** impact assessment completes, **Then** the investigation is flagged as `customer_impacting: true` **And** investigation proceeds with higher priority.

3. **Given** the condition is internal/infrastructure only, **When** impact assessment completes, **Then** the investigation is flagged as `customer_impacting: false` **And** investigation still proceeds but with appropriate priority.

4. **Given** impact cannot be determined, **When** assessment is uncertain, **Then** `customer_impacting: unknown` is set **And** investigation proceeds with default priority.

## Tasks / Subtasks

- [x] Task 1: Create investigation step protocol and pipeline (AC: all)
  - [x] 1.1 Create `steps/__init__.py` with `InvestigationStep` protocol, `StepResult` dataclass
  - [x] 1.2 Replace placeholder `_run_steps()` in `agent.py` with step pipeline that iterates registered steps
  - [x] 1.3 Add `metadata: dict[str, Any]` field to `InvestigationResult` for structured step output
  - [x] 1.4 Update `_persist_result()` to include metadata (especially `customer_impacting`) in Qdrant payload
  - [x] 1.5 Update existing `test_agent.py` tests for new step pipeline behavior

- [x] Task 2: Add model override support to LlmClient (AC: 1)
  - [x] 2.1 Add optional `model` parameter to `LlmClient.complete_sync()` that overrides default model
  - [x] 2.2 Add `BEEPER_LLM_SCREENING_MODEL` env var support to `LlmConfig` (read in `from_env()`)
  - [x] 2.3 Expose `screening_model` property on `LlmClient` (returns screening model or falls back to default)
  - [x] 2.4 Add tests for model override and screening model env var

- [x] Task 3: Implement CustomerImpactStep (AC: 1, 2, 3, 4)
  - [x] 3.1 Create `steps/impact_assessment.py` with `CustomerImpactStep` implementing `InvestigationStep`
  - [x] 3.2 Build structured LLM prompt: system prompt + user prompt with condition/service/severity context
  - [x] 3.3 Parse LLM JSON response to extract `customer_impacting` (true/false/unknown) and `reasoning`
  - [x] 3.4 Handle LLM parse failures gracefully (default to `unknown`)
  - [x] 3.5 Return `StepResult` with `customer_impacting` in data dict

- [x] Task 4: Register step and wire into agent (AC: all)
  - [x] 4.1 Register `CustomerImpactStep` in `agent.py` step list (or `main.py` injection)
  - [x] 4.2 Pass `screening_model` to `CustomerImpactStep` for lightweight model usage
  - [x] 4.3 Ensure status updater reports "Assessing customer impact" during step

- [x] Task 5: Tests (AC: all)
  - [x] 5.1 Create `tests/test_impact_assessment.py` with unit tests for CustomerImpactStep
  - [x] 5.2 Test customer-facing service → `customer_impacting: true`
  - [x] 5.3 Test internal/infra service → `customer_impacting: false`
  - [x] 5.4 Test uncertain/ambiguous → `customer_impacting: unknown`
  - [x] 5.5 Test LLM response parse failure → graceful fallback to `unknown`
  - [x] 5.6 Test LLM call failure → step returns error, investigation continues
  - [x] 5.7 Verify `customer_impacting` appears in Qdrant persist payload

## Dev Notes

### Step System Architecture (NEW — establishes pattern for Stories 3.4-3.8)

This is the **first investigation step** — the step system doesn't exist yet. Design it for extensibility.

**Step protocol:**
```python
# steps/__init__.py
from dataclasses import dataclass, field
from typing import Any, Protocol

@dataclass
class StepResult:
    success: bool
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

class InvestigationStep(Protocol):
    """Protocol for investigation steps. Stories 3.3-3.8 each implement one."""
    name: str

    def execute(self) -> StepResult:
        """Run the step. Returns structured result."""
        ...
```

**Step receives dependencies via constructor** (dependency injection), NOT by accessing the agent. Each step is constructed with only what it needs:
- `CustomerImpactStep(llm_client, context, status_updater, screening_model)`

**Pipeline in `_run_steps()`:**
```python
def _run_steps(self) -> InvestigationResult:
    steps = self._build_steps()  # List[InvestigationStep]
    all_findings: list[str] = []
    metadata: dict[str, Any] = {}

    for step in steps:
        self.status_updater.update_message(f"Running: {step.name}")
        result = step.execute()
        if result.summary:
            all_findings.append(result.summary)
        metadata.update(result.data)
        if not result.success:
            # Step failure is non-fatal for the pipeline; log and continue
            logger.warning("Step %s failed: %s", step.name, result.error)

    return InvestigationResult(
        success=True,
        summary="; ".join(all_findings) if all_findings else "Investigation complete",
        findings=all_findings,
        metadata=metadata,
    )
```

**Key design decisions:**
- Steps are **non-fatal** — a failed step logs a warning but doesn't abort the pipeline. The investigation continues with remaining steps.
- Each step writes its structured data to `StepResult.data`. The pipeline merges all step data into `InvestigationResult.metadata`.
- `_build_steps()` is a method that returns the ordered step list. Future stories add their step here.

### LLM Model Override for Screening (FR43)

Architecture specifies tiered model routing: `screening → claude-3-haiku`. The current `LlmClient.complete_sync()` always uses `self.config.get_litellm_model()`.

**Implementation approach — add optional `model` kwarg to `complete_sync()`:**
```python
def complete_sync(self, messages, max_tokens=4096, temperature=0.0, *, model: str | None = None, **kwargs) -> str:
    effective_model = model or self.config.get_litellm_model()
    response = litellm.completion(model=effective_model, messages=messages, ...)
```

**Add `BEEPER_LLM_SCREENING_MODEL` env var:**
- Read in `LlmConfig.from_env()` as optional field
- Do NOT validate against provider prefixes (screening model may differ from main model)
- Expose via `LlmClient.screening_model` property (returns screening model or default)
- Story 3.9 (Tiered Model Selection) will expand this to a full routing system — keep it simple now

**Do NOT** create a second `LlmClient` instance for screening. One client, model override per call.

### LLM Prompt Design

**System prompt:**
```
You are an SRE impact assessment assistant. Given information about a detected
condition, determine whether it impacts customers.

Respond with ONLY a JSON object:
{"customer_impacting": true|false|"unknown", "reasoning": "brief explanation"}

Rules:
- true: Condition affects customer-facing services, user experience, or data
- false: Condition is purely internal/infrastructure with no customer visibility
- "unknown": Insufficient information to determine impact
```

**User prompt template:**
```
Condition: {context.condition}
Service: {context.service}
Severity: {context.severity}
```

**Response parsing:**
- Parse JSON from LLM response using `json.loads()`
- Strip markdown code fences if present (LLMs often wrap JSON in ```json blocks)
- Validate `customer_impacting` is one of: `true`, `false`, `"unknown"`
- On any parse failure → default to `"unknown"` with warning log

**LLM call parameters:**
- `max_tokens=256` (response is small JSON)
- `temperature=0.0` (deterministic assessment)
- `model=self.screening_model` (use lightweight model)

### InvestigationResult Changes

Add `metadata` field to carry structured data from steps:

```python
@dataclass
class InvestigationResult:
    success: bool
    summary: str
    findings: list[str] = field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)  # NEW
```

Update `_persist_result()` to spread metadata into the Qdrant payload:
```python
payload = {
    "investigation_id": self.context.investigation_id,
    ...existing fields...,
    **result.metadata,  # Includes customer_impacting, reasoning, etc.
}
```

### Existing Code to Modify

| File | Change |
|------|--------|
| `agent.py` | Replace `_run_steps()` placeholder with step pipeline; add `metadata` to `InvestigationResult`; add `_build_steps()` method; update `_persist_result()` payload |
| `llm/client.py` | Add `model` kwarg to `complete_sync()` and `complete()`; add `screening_model` to `LlmConfig`; add `screening_model` property to `LlmClient` |
| `test_agent.py` | Update tests for new step pipeline (placeholder test changes to "no steps" test; lifecycle test still passes; persist test checks metadata in payload) |

### New Files to Create

| File | Purpose |
|------|---------|
| `beeper_investigator/steps/__init__.py` | `InvestigationStep` protocol, `StepResult` dataclass |
| `beeper_investigator/steps/impact_assessment.py` | `CustomerImpactStep` implementation |
| `tests/test_impact_assessment.py` | Unit tests for impact assessment step |

### Critical Anti-Patterns to Avoid

1. **Do NOT make the step async.** The agent is synchronous (Story 3-2 design decision). Use `complete_sync()`.
2. **Do NOT have steps modify the agent's state directly.** Steps return `StepResult`; the pipeline aggregates.
3. **Do NOT create a separate LlmClient for screening.** Use model override on existing client.
4. **Do NOT abort the investigation if impact assessment fails.** It's a screening step — default to `unknown` and continue.
5. **Do NOT import `CustomerImpactStep` at module level in `agent.py`.** Import in `_build_steps()` to keep the agent framework decoupled from specific steps (lazy import pattern).
6. **Do NOT update the `phase` field on Investigation CR.** Controller owns that lifecycle (Story 3-2 design decision).
7. **Do NOT over-engineer the prompt.** Keep it minimal — condition/service/severity is sufficient context for a screening assessment.

### Previous Story Intelligence

**From Story 3-2 (Investigator Agent Scaffold):**
- Agent lifecycle: `_initialize()` → `_run_steps()` → `_finalize()`. Do NOT modify `_initialize` or `_finalize`.
- `_persist_result()` returns `bool`; `_finalize()` appends WARNING on failure.
- `SourceClients` fields are nullable; `InvestigationContext` is frozen.
- K8s status updater writes only `message` field.
- `test_connection()` on LlmClient is async but called synchronously — known pre-existing issue, don't fix here.
- `PrometheusClient`/`LokiClient` constructors take `base_url` kwarg.

**From Story 3-1 (Anomaly Detection Engine):**
- `InvestigationContext.condition` contains the detected condition description (from EWMA detector output).
- `InvestigationContext.service` is the service name extracted from labels.
- `InvestigationContext.severity` is the mapped severity (low/medium/high/critical).

**From Story 3-2 Code Review:**
- Silent failures are a recurring pattern — ensure step failures are logged clearly.
- Return booleans/structured results from methods that can fail (don't just swallow errors).
- Auth-related code should be tested (test both valid and invalid cases).

### Project Structure Notes

```
investigator/beeper_investigator/
├── __init__.py
├── main.py               # Entry point — no changes needed
├── agent.py              # MODIFY: step pipeline, metadata, _build_steps()
├── context.py            # No changes
├── steps/                # NEW package
│   ├── __init__.py       # InvestigationStep protocol, StepResult
│   └── impact_assessment.py  # CustomerImpactStep
├── llm/
│   ├── __init__.py
│   └── client.py         # MODIFY: model override, screening_model
├── kb/
│   ├── __init__.py
│   ├── client.py         # No changes
│   └── schemas.py
├── k8s/
│   ├── __init__.py
│   └── status.py         # No changes
└── sources/
    ├── __init__.py
    ├── prometheus.py      # No changes
    └── loki.py            # No changes

investigator/tests/
├── test_agent.py              # MODIFY: update for step pipeline
├── test_impact_assessment.py  # NEW
├── test_llm_client.py         # MODIFY: add model override tests
└── ... (other test files unchanged)
```

### Testing Standards

- Mock `LlmClient.complete_sync()` in step tests — do NOT make real LLM calls
- Use the same `_make_agent()` helper pattern from `test_agent.py` for agent-level tests
- Test both success and failure paths for every method
- Test the JSON parsing edge cases: valid JSON, malformed JSON, missing fields, markdown-wrapped JSON
- Verify structured data flows from `StepResult.data` → `InvestigationResult.metadata` → Qdrant payload

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic-3, Story 3.3] — FR3, FR43, acceptance criteria
- [Source: _bmad-output/planning-artifacts/architecture.md#LLM-Integration] — Tiered model routing: screening → claude-3-haiku
- [Source: _bmad-output/planning-artifacts/architecture.md#Investigation-State-Machine] — pending → started → investigating → completed/failed
- [Source: _bmad-output/implementation-artifacts/3-2-investigator-agent-scaffold.md] — Agent lifecycle, design decisions, code review learnings
- [Source: investigator/beeper_investigator/agent.py] — Current `_run_steps()` placeholder, `InvestigationResult` dataclass
- [Source: investigator/beeper_investigator/llm/client.py] — `LlmClient.complete_sync()`, `LlmConfig.from_env()`

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- **Task 1:** Created `steps/__init__.py` with `InvestigationStep` protocol (`@runtime_checkable`) and `StepResult` dataclass. Replaced `_run_steps()` placeholder with step pipeline: iterates registered steps, merges `StepResult.data` into `InvestigationResult.metadata`, catches step exceptions gracefully. Added `metadata: dict[str, Any]` to `InvestigationResult`. Updated `_persist_result()` to spread `result.metadata` into Qdrant payload. Steps use `None` sentinel on `self.steps` (auto-populated via `_build_steps()` on first `run()`, overridable to `[]` for testing). Updated `test_agent.py` to set `agent.steps = []` for lifecycle isolation. Added 9 step pipeline tests in `test_step_pipeline.py`.
- **Task 2:** Added `screening_model: str | None` to `LlmConfig`. `from_env()` reads `BEEPER_LLM_SCREENING_MODEL` env var (optional). Added keyword-only `model` parameter to `complete_sync()` — overrides default when provided. Added `LlmClient.screening_model` property (falls back to default model). 6 new tests in `test_llm_screening.py`.
- **Task 3:** Created `steps/impact_assessment.py` with `CustomerImpactStep`. System prompt instructs LLM to return JSON `{customer_impacting, reasoning}`. User prompt includes condition/service/severity. Parses JSON response, strips markdown code fences. Normalizes `customer_impacting` to `true`/`false`/`"unknown"`. Graceful degradation: parse failures → `unknown`, LLM errors → `unknown` with `success=False`. Uses `max_tokens=256`, `temperature=0.0`, `model=screening_model`. 12 tests in `test_impact_assessment.py`.
- **Task 4:** `_build_steps()` in `agent.py` uses lazy import of `CustomerImpactStep`. Constructs step with dependency injection (`llm_client`, `context`, `status_updater`). Step sends "Assessing customer impact" via status updater.
- **Task 5:** All test files created with comprehensive coverage. 12 impact assessment tests, 9 step pipeline tests, 6 screening model tests = 27 new tests. Full suite: 101 Python tests pass (excluding 2 pre-existing `test_kb_client.py` failures), 162 Rust tests pass.

### Code Review Record

**Reviewer:** Claude Opus 4.6 (adversarial)
**Date:** 2026-02-24
**Findings:** 6 issues (1 HIGH, 2 MEDIUM, 3 LOW) — all fixed

| # | Severity | Finding | Resolution |
|---|----------|---------|------------|
| HIGH-1 | HIGH | `screening_model` property fallback bypasses `get_litellm_model()` — Azure/Ollama provider prefix not applied | Changed fallback to use `get_litellm_model()`. Added test for Azure prefix. |
| MED-1 | MEDIUM | `**result.metadata` spread in Qdrant payload can silently overwrite reserved fields | Added `_RESERVED_KEYS` guard with warning log; colliding keys are skipped. Added test. |
| MED-2 | MEDIUM | Impact normalization doesn't handle LLM case variations (`"True"`, `"FALSE"`) | Added `.lower()` normalization before comparison. Added 2 tests. |
| LOW-1 | LOW | "Running investigation steps" status message only sent when no steps exist | Moved `update_message` before the `if not self.steps` check. |
| LOW-2 | LOW | Async `complete()` lacks `model` override kwarg (parity with `complete_sync()`) | Added `*, model: str \| None = None` parameter to `complete()`. |
| LOW-3 | LOW | No test for `_build_steps()` ImportError path | Added test verifying `run()` catches and reports the error. |

**Post-fix test results:** 121 passed, 2 failed (pre-existing `test_kb_client.py`), 3 skipped

### Change Log

- 2026-02-24: Story 3.3 implementation complete — customer impact assessment step with step pipeline framework
- 2026-02-24: Code review — 6 findings fixed (1 HIGH, 2 MEDIUM, 3 LOW); 5 new tests added

### File List

**New files:**
- investigator/beeper_investigator/steps/__init__.py
- investigator/beeper_investigator/steps/impact_assessment.py
- investigator/tests/test_impact_assessment.py
- investigator/tests/test_step_pipeline.py
- investigator/tests/test_llm_screening.py

**Modified files:**
- investigator/beeper_investigator/agent.py
- investigator/beeper_investigator/llm/client.py
- investigator/tests/test_agent.py
- _bmad-output/implementation-artifacts/sprint-status.yaml
- _bmad-output/implementation-artifacts/3-3-customer-impact-assessment.md
