# Story 4.2: Human-Language Runbook Execution

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the **system**,
I want to execute human-language runbooks without DSL translation,
so that SRE teams can point Beeper at existing plain-language runbooks for zero-friction adoption — no YAML rewrite or playbook migration required.

## Acceptance Criteria

1. **Given** a KB runbook entry with plain-language steps (e.g., "Check if the service pod is in CrashLoopBackOff", "Scale deployment to 3 replicas")
   **When** the investigator pipeline encounters a matching runbook during investigation
   **Then** the LLM interprets each step, maps it to an executable action type (diagnostic_check, cluster_action, manual_step), and logs each interpretation with the original step text, interpreted action, and confidence score

2. **Given** a runbook step interpreted as a cluster action (e.g., "Scale deployment to 3 replicas", "Restart pod")
   **When** the service trust level is TL1 or TL2
   **Then** the action is logged as advisory only ("would execute at higher trust level"), the SRE sees what Beeper would do, and no cluster mutation occurs
   **And** when the trust level is TL3+, the action executes if confidence >= the configured threshold

3. **Given** a runbook step that fails during execution (action errors, timeout, or unexpected result)
   **When** the failure is detected
   **Then** execution halts immediately, the SRE is notified with: failure context (which step, what error, what was attempted), and the remaining unexecuted steps listed for manual completion

## Tasks / Subtasks

- [x] Task 1: Extend InvestigationContext with trust_level field (AC: #2)
  - [x]1.1 Add `trust_level: int` field to `InvestigationContext` dataclass in `investigator/beeper_investigator/context.py` with default value `1` (advisory). Read from env var `INVESTIGATION_TRUST_LEVEL` in `from_env()`.
  - [x]1.2 Add `confidence_threshold: float` field to `InvestigationContext` with default `0.9`. Read from env var `INVESTIGATION_CONFIDENCE_THRESHOLD` in `from_env()`.
  - [x]1.3 Add unit tests in `investigator/tests/test_context.py`: trust_level defaults to 1, reads from env, confidence_threshold defaults to 0.9, reads from env, invalid values handled gracefully

- [x] Task 2: Create remediation package structure (AC: #1, #2, #3)
  - [x]2.1 Create `investigator/beeper_investigator/remediation/__init__.py` with `RunbookExecutorStep` import
  - [x]2.2 Create `investigator/beeper_investigator/remediation/runbook_executor.py` with the `RunbookExecutorStep` class

- [x] Task 3: Implement RunbookExecutorStep — KB runbook retrieval (AC: #1)
  - [x]3.1 Define `RunbookExecutorStep` class implementing `InvestigationStep` protocol with `name = "Runbook Execution"`
  - [x]3.2 Constructor: `__init__(self, llm_client: LlmClient, kb_client: KBClient, context: InvestigationContext, status_updater: InvestigationStatusUpdater, pipeline_metadata: dict[str, Any] | None = None)`
  - [x]3.3 Implement `_search_runbooks(self) -> list[SearchResult]`: use `kb_client.search_knowledge(query_vector=embedding, entry_type="runbook", service=context.service, limit=3)` where embedding is generated from `f"{context.condition} {context.service}"` using `llm_client.embed_sync()`
  - [x]3.4 Implement `_select_best_runbook(self, results: list[SearchResult]) -> dict | None`: return the highest-scoring result above `RUNBOOK_MATCH_THRESHOLD = 0.75`, or None if no match
  - [x]3.5 If no runbook found, return `StepResult(success=True, summary="No matching runbook found", data={"runbook_found": False, "runbook_execution_skipped": True})`

- [x] Task 4: Implement RunbookExecutorStep — LLM interpretation (AC: #1)
  - [x]4.1 Implement `_interpret_runbook(self, runbook_content: str) -> list[dict]`: send runbook content to LLM with `remediation` model tier, parse response as JSON list of `{"step_number": int, "original_text": str, "action_type": "diagnostic_check"|"cluster_action"|"manual_step", "interpreted_action": str, "confidence": float, "k8s_resource": str|None, "k8s_operation": str|None}`
  - [x]4.2 Define `_RUNBOOK_INTERPRET_SYSTEM_PROMPT` — instruct LLM to interpret each runbook step into structured actions with explicit action_type classification
  - [x]4.3 Define `_RUNBOOK_INTERPRET_USER_TEMPLATE` — include investigation context (condition, service, severity), runbook title, runbook content
  - [x]4.4 Implement `_validate_interpreted_steps(self, steps: list[dict]) -> list[dict]`: validate each step has required fields, normalize action_type, clamp confidence to 0.0-1.0
  - [x]4.5 Log each interpreted step with structured JSON: `{"step_number": N, "original_text": "...", "action_type": "...", "interpreted_action": "...", "confidence": 0.XX}`

- [x] Task 5: Implement RunbookExecutorStep — trust-gated execution (AC: #2, #3)
  - [x]5.1 Implement `_execute_steps(self, interpreted_steps: list[dict]) -> RunbookExecutionResult`: iterate through steps, gate execution by trust level and confidence
  - [x]5.2 Define `RunbookExecutionResult` dataclass: `executed_steps: list[dict]`, `failed_step: dict | None`, `remaining_steps: list[dict]`, `halted: bool`, `advisory_only: bool`
  - [x]5.3 For `diagnostic_check` action type: always execute (log what would be checked, record in execution log). These are safe read-only operations.
  - [x]5.4 For `cluster_action` action type: if `context.trust_level <= 2` → log as advisory ("Advisory: would execute '{action}' at TL3+"), add to `advisory_actions` list. If `context.trust_level >= 3` AND step confidence >= `context.confidence_threshold` → mark as "approved for execution" (actual K8s execution deferred to Story 4-5 sandbox). If confidence < threshold → log as "blocked: confidence {X} below threshold {Y}"
  - [x]5.5 For `manual_step` action type: always log as requiring human action, never auto-execute
  - [x]5.6 On any step failure: halt immediately, capture `failed_step` with error context, populate `remaining_steps` with all unexecuted steps, set `halted=True`

- [x] Task 6: Implement RunbookExecutorStep.execute() orchestration (AC: #1, #2, #3)
  - [x]6.1 Wire up `execute()` method: search runbooks → select best → interpret → execute steps → return StepResult
  - [x]6.2 Return `StepResult.data` with: `runbook_found: bool`, `runbook_title: str`, `runbook_id: str`, `steps_total: int`, `steps_executed: int`, `steps_advisory: int`, `steps_blocked: int`, `execution_halted: bool`, `failed_step_context: dict | None`, `remaining_steps: list[dict]`, `advisory_actions: list[str]`, `execution_log: list[dict]`, `runbook_model_tier: str`, `runbook_model_used: str`
  - [x]6.3 Build summary string: "Executed runbook '{title}': {executed}/{total} steps ({advisory} advisory, {blocked} blocked)" or "Runbook execution halted at step {N}: {error}" if halted

- [x] Task 7: Integrate RunbookExecutorStep into agent pipeline (AC: #1, #2, #3)
  - [x]7.1 In `investigator/beeper_investigator/agent.py`, add `RunbookExecutorStep` as step 7 after `InvestigationDocumentationStep` in `_build_steps()`. Only add if `self.context.trust_level >= 1` (always, since even TL1 produces advisory output).
  - [x]7.2 Import `RunbookExecutorStep` lazily in `_build_steps()` following existing pattern
  - [x]7.3 Pass `pipeline_metadata`, `kb_client`, `llm_client`, `context`, `status_updater` to constructor

- [x] Task 8: Write comprehensive tests (AC: #1, #2, #3)
  - [x]8.1 Create `investigator/tests/test_runbook_executor.py` with test classes:
    - `TestRunbookSearch`: no runbook found returns skip result, runbook below threshold skipped, best runbook selected from multiple results
    - `TestRunbookInterpretation`: LLM response parsed correctly, invalid JSON falls back gracefully, action_type normalization, confidence clamping, all step fields present
    - `TestTrustGating`: TL1 produces advisory only (zero cluster actions executed), TL2 produces advisory only, TL3+ with high confidence executes, TL3+ with low confidence blocks, diagnostic_check always executes regardless of trust level, manual_step never auto-executes
    - `TestStepFailure`: failure halts execution, remaining steps captured, failed step context includes error, partial execution reported correctly
    - `TestExecuteOrchestration`: full happy path (runbook found → interpreted → executed), no runbook path, LLM interpretation failure path
  - [x]8.2 Create `investigator/tests/test_agent_runbook_integration.py`: verify RunbookExecutorStep is included in `_build_steps()` as step 7, verify pipeline_metadata is shared, verify trust_level context flows through

- [x] Task 9: Run all investigator tests (AC: #1, #2, #3)
  - [x]9.1 Run `cd investigator && python -m pytest tests/ -v` — all existing + new tests pass
  - [x]9.2 Run `cd investigator && python -m ruff check .` — no new warnings
  - [x]9.3 Verify zero regressions in existing step tests

## Dev Notes

### Architecture Patterns to Follow

**CRITICAL CONTEXT: This story adds the first remediation step to the investigator pipeline. It creates the `remediation/` package and the `RunbookExecutorStep` that retrieves human-language runbooks from the KB, interprets them via LLM, and executes steps gated by trust level. This is the foundation for all subsequent remediation stories (4-3 through 4-8).**

**What already exists (DO NOT recreate):**

| Component | Location | Status |
|-----------|----------|--------|
| `InvestigationStep` protocol + `StepResult` | `investigator/beeper_investigator/steps/__init__.py` | Done (v0.1.0) |
| 6-step investigation pipeline | `investigator/beeper_investigator/steps/` | Done (v0.1.0) |
| `InvestigatorAgent` lifecycle | `investigator/beeper_investigator/agent.py` | Done (v0.1.0) |
| `KBClient` with `search_knowledge(entry_type="runbook")` | `investigator/beeper_investigator/kb/client.py` | Done (v0.1.0) |
| `KnowledgeEntryType.RUNBOOK` enum | `investigator/beeper_investigator/kb/schemas.py` | Done (v0.1.0) |
| `LlmClient` with `select_model()`, `complete_sync()`, `embed_sync()` | `investigator/beeper_investigator/llm/client.py` | Done (v0.1.0) |
| `InvestigationContext` dataclass | `investigator/beeper_investigator/context.py` | Done (v0.1.0) |
| `InvestigationStatusUpdater` | `investigator/beeper_investigator/k8s/status.py` | Done (v0.1.0) |
| `ResolutionRecommendationStep` pattern | `investigator/beeper_investigator/steps/resolution_recommendations.py` | Done — closest pattern reference |

**What this story adds:**

| Component | Description |
|-----------|-------------|
| `trust_level` + `confidence_threshold` in `InvestigationContext` | Env-based config for trust gating |
| `remediation/__init__.py` | New package for all remediation steps |
| `remediation/runbook_executor.py` | `RunbookExecutorStep` — KB search, LLM interpret, trust-gated execution |
| Agent pipeline step 7 | `RunbookExecutorStep` wired into `_build_steps()` |
| Tests for runbook execution | Comprehensive unit + integration tests |

### Step Protocol Pattern (MUST follow exactly)

```python
class RunbookExecutorStep:
    """Execute human-language runbooks from KB without DSL translation."""

    name: str = "Runbook Execution"

    def __init__(
        self,
        llm_client: LlmClient,
        kb_client: KBClient,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
        pipeline_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.kb_client = kb_client
        self.context = context
        self.status_updater = status_updater
        self.pipeline_metadata = pipeline_metadata if pipeline_metadata is not None else {}

    def execute(self) -> StepResult:
        """Run the runbook execution step."""
        ...
```

### LLM Call Pattern (follow ResolutionRecommendationStep exactly)

```python
model_name = self.llm_client.select_model("remediation")
raw = self.llm_client.complete_sync(
    messages,
    max_tokens=2048,
    temperature=0.0,
    model=model_name,
)
```

Note: The `remediation` model tier may not be configured yet. If `select_model("remediation")` returns None or falls back, use `"deep_rca"` as fallback since both target the highest-capability model. Check `LlmClient.select_model()` behavior — if tier not found, it returns the default model. This is acceptable.

### KB Runbook Search Pattern

```python
# Generate embedding for search
query_text = f"{self.context.condition} {self.context.service}"
embedding = self.llm_client.embed_sync(query_text)

# Search for runbooks
results = self.kb_client.search_knowledge(
    query_vector=embedding,
    entry_type="runbook",
    service=self.context.service,
    limit=3,
)
```

### Trust Level Gating Logic

```python
# Trust levels (from architecture.md):
# TL1: Advisory — investigate + document + recommend
# TL2: Notify + Recommend — all of TL1 + proactive notification
# TL3: Auto-fix + Review — auto-apply fixes above confidence gate
# TL4: Autonomous + Audit — expanded fix scope
# TL5: Fully Autonomous — full autonomy within scope

# Runbook execution gating:
if action_type == "diagnostic_check":
    # Always safe — read-only operations
    execute_and_log()
elif action_type == "cluster_action":
    if context.trust_level <= 2:
        log_advisory(f"Advisory: would execute '{action}' at TL3+")
    elif step_confidence >= context.confidence_threshold:
        log_approved(f"Approved for execution: '{action}'")
        # NOTE: Actual K8s execution deferred to Story 4-5 (sandbox)
        # For now, log as "approved" but don't mutate cluster
    else:
        log_blocked(f"Blocked: confidence {confidence} < threshold {threshold}")
elif action_type == "manual_step":
    log_manual(f"Requires human action: '{action}'")
```

**IMPORTANT: Story 4-2 does NOT implement actual K8s cluster mutations.** It interprets runbooks, classifies actions, and gates by trust level. The actual execution of cluster actions happens in Story 4-5 (Sandbox Test Execution). For TL3+ approved actions, log them as "approved for execution" but do not call kubectl or K8s API.

### Test Pattern (follow existing test_resolution_recommendations.py)

```python
class TestRunbookSearch:
    def _make_step(self, **overrides):
        """Factory for RunbookExecutorStep with mocked dependencies."""
        llm = MagicMock(spec=LlmClient)
        kb = MagicMock(spec=KBClient)
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
            "llm_client": llm, "kb_client": kb,
            "context": ctx, "status_updater": status,
            "pipeline_metadata": {},
        }
        defaults.update(overrides)
        return RunbookExecutorStep(**defaults), defaults
```

### Critical Guardrails

- **No actual K8s cluster mutations** — this story classifies and gates actions, actual execution is Story 4-5
- **No new pip dependencies** — use existing qdrant-client, litellm, pydantic
- **Follow `InvestigationStep` protocol** exactly — `name` class attribute + `execute() -> StepResult`
- **`temperature=0.0`** for all LLM calls — deterministic interpretation
- **Structured JSON logging** for all step interpretations (matches architecture pattern)
- **PII scrubbing** happens in LlmClient automatically — no need to scrub in step code
- **Model tier fallback** — if `remediation` tier not configured, `select_model()` returns default model (acceptable)
- **Trust level defaults to 1** (advisory) — safest default, operator must explicitly set higher
- **Confidence threshold defaults to 0.9** (90%) — conservative default per architecture
- **Zero regressions** — all existing 505 investigator tests must continue passing
- **ruff clean** — no new warnings

### Project Structure Notes

- New package: `investigator/beeper_investigator/remediation/` (per architecture)
- New file: `investigator/beeper_investigator/remediation/__init__.py`
- New file: `investigator/beeper_investigator/remediation/runbook_executor.py`
- Modified: `investigator/beeper_investigator/context.py` (add trust_level, confidence_threshold)
- Modified: `investigator/beeper_investigator/agent.py` (add step 7)
- New test: `investigator/tests/test_runbook_executor.py`
- New test: `investigator/tests/test_agent_runbook_integration.py`

### Previous Story Intelligence

**From Story 4-1 (Repository CRD & Git Provider Integration):**
- Rust toolchain installed (resolved CRITICAL blocker) — not relevant for this Python story
- 4 pre-existing operator test failures (3 float precision + 1 substring match) — not in scope
- 12 pre-existing async investigator test failures in `test_llm_client.py` and `test_kb_client.py` — these are pre-existing and NOT caused by this story
- `validate_spec` pattern — analogous to `_validate_interpreted_steps` for runbook steps
- Code review found missing `#[instrument]` tracing — add structured logging to all key methods

**From Epic 3 Stories (Trust & Anti-Noise):**
- Trust level configuration persisted in `service_trust_levels` Qdrant collection (Story 3-1)
- Confidence gate engine validates trust_level × confidence_score gating (Story 3-2)
- Trust level is per-service, set by operator when spawning investigator Job via env vars

### Git Intelligence

Recent commits: `MAESTRO: 4-1 done`, `MAESTRO: implement story 4-1 (Repository CRD & Git Provider Integration)`. Follow commit pattern: `MAESTRO: implement story 4-2 (Human-Language Runbook Execution)`. Current test counts: operator 527 passed (4 pre-existing), investigator 505 passed (12 pre-existing async), UI 1,388 passed.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 4, Story 4.2] — User story, acceptance criteria
- [Source: _bmad-output/planning-artifacts/architecture.md#Auto-Remediation Architecture] — Remediation pipeline design, agent framework evolution
- [Source: _bmad-output/planning-artifacts/architecture.md#Trust System Architecture] — Trust levels TL1-TL5, confidence gating
- [Source: _bmad-output/planning-artifacts/architecture.md#LLM Integration] — Remediation model tier (claude-opus-4)
- [Source: _bmad-output/planning-artifacts/prd.md#Innovation] — Human-language runbook execution as key differentiator
- [Source: investigator/beeper_investigator/steps/__init__.py] — InvestigationStep protocol, StepResult dataclass
- [Source: investigator/beeper_investigator/steps/resolution_recommendations.py] — Closest pattern reference for LLM synthesis step
- [Source: investigator/beeper_investigator/agent.py] — Agent lifecycle, _build_steps(), pipeline_metadata sharing
- [Source: investigator/beeper_investigator/kb/client.py] — KBClient.search_knowledge(entry_type="runbook")
- [Source: investigator/beeper_investigator/kb/schemas.py] — KnowledgeEntryType.RUNBOOK enum
- [Source: investigator/beeper_investigator/llm/client.py] — LlmClient.select_model(), complete_sync(), embed_sync()
- [Source: investigator/beeper_investigator/context.py] — InvestigationContext dataclass
- [Source: _bmad-output/implementation-artifacts/4-1-repository-crd-git-provider-integration.md] — Previous story patterns and lessons

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- All 9 tasks implemented with zero regressions
- Extended InvestigationContext with trust_level (default 1) and confidence_threshold (default 0.9) fields
- Created remediation/ package with RunbookExecutorStep
- RunbookExecutorStep searches KB for runbooks, interprets via LLM, executes with trust-gated logic
- Trust gating: TL1-2 advisory only, TL3+ approved/blocked by confidence threshold, diagnostics always safe, manual never auto-executed
- Step failures halt execution immediately with remaining steps captured
- Integrated as step 7 in agent pipeline
- 31 new tests (27 unit + 4 integration), all passing
- Full suite: 543 passed, 13 pre-existing failures (async/ordering), 0 new regressions
- Ruff clean — no lint warnings

### File List

- `investigator/beeper_investigator/context.py` — Modified: added trust_level, confidence_threshold fields
- `investigator/beeper_investigator/remediation/__init__.py` — New: package init
- `investigator/beeper_investigator/remediation/runbook_executor.py` — New: RunbookExecutorStep implementation
- `investigator/beeper_investigator/agent.py` — Modified: added RunbookExecutorStep as step 7
- `investigator/tests/test_context.py` — Modified: 8 new tests for trust/confidence fields
- `investigator/tests/test_runbook_executor.py` — New: 27 tests across 5 test classes
- `investigator/tests/test_agent_runbook_integration.py` — New: 4 pipeline integration tests
