# Story 4.7: Trust-Gated Remediation Actions

Status: review

## Story

As the **system**,
I want remediation actions gated to the configured trust level and confidence tier,
so that Beeper never exceeds the autonomy boundary an admin has set.

## Acceptance Criteria

1. **Given** a remediation action (runbook step, auto-PR, sandbox deploy) for a service at TL1
   **When** the action is evaluated
   **Then** only advisory output is produced — no code changes, no cluster mutations
   **And** the advisory includes what Beeper would do at higher trust levels

2. **Given** a remediation action for a service at TL3 with confidence 0.82 and gate threshold 0.85
   **When** the confidence gate evaluates
   **Then** the action is blocked and presented as "requires manual approval" with confidence explanation
   **And** the SRE can one-click approve to override

3. **Given** a remediation action for a service at TL5 with confidence above threshold
   **When** the action executes autonomously
   **Then** a notification is sent to the admin with action details
   **And** a rollback path is registered for the action (FR62)

## Tasks / Subtasks

- [ ] Task 1: Create TrustGateEvaluator utility class (AC: #1, #2, #3)
  - [ ] 1.1 Create `investigator/beeper_investigator/remediation/trust_gate.py` with `TrustGateEvaluator` class
  - [ ] 1.2 Constructor: `__init__(self, context: InvestigationContext, status_updater: InvestigationStatusUpdater)` — reads trust_level and confidence_threshold from context
  - [ ] 1.3 Create `TrustGateDecision` dataclass: `allowed: bool`, `action_type: str` ("executed"|"advisory"|"blocked"|"requires_approval"), `trust_level: int`, `confidence: float | None`, `confidence_threshold: float`, `reason: str`, `advisory_message: str | None` (what Beeper would do at higher TL), `rollback_registered: bool`
  - [ ] 1.4 Implement `evaluate(action_name: str, action_category: str, confidence: float | None = None) -> TrustGateDecision`:
    - `action_category` is one of: "read_only", "cluster_mutation", "code_change", "notification"
    - "read_only" → always allowed at all trust levels (diagnostic checks)
    - "notification" → always allowed (non-mutating)
    - TL1-2: "cluster_mutation" and "code_change" → advisory only, populate advisory_message
    - TL3: if confidence provided and < confidence_threshold → blocked/requires_approval
    - TL3: if confidence >= threshold → allowed (draft PR mode)
    - TL4-5: if confidence >= threshold → allowed (full autonomy)
    - TL4-5: if confidence < threshold → blocked/requires_approval (safety fallback)
  - [ ] 1.5 Implement `_build_advisory_message(action_name: str, action_category: str) -> str`: generates human-readable "At TL3+, Beeper would: {action_name}" with category-specific detail
  - [ ] 1.6 Implement `register_rollback_path(action_name: str, rollback_action: str) -> dict[str, Any]`: creates a rollback registration entry with action details, timestamp, investigation_id. Returns the rollback entry dict
  - [ ] 1.7 Implement `notify_autonomous_action(action_name: str, action_details: dict[str, Any]) -> None`: logs autonomous action notification at INFO level and calls `status_updater.update_message()` with action details. At TL5, this is the primary notification mechanism

- [ ] Task 2: Create TrustGateSummary for pipeline metadata aggregation (AC: #1, #2, #3)
  - [ ] 2.1 Create `TrustGateSummary` dataclass: `total_actions: int`, `executed: int`, `advisory: int`, `blocked: int`, `requires_approval: int`, `rollback_paths: list[dict[str, Any]]`, `decisions: list[dict[str, Any]]` (serialized TrustGateDecision list)
  - [ ] 2.2 Implement `TrustGateEvaluator.get_summary() -> TrustGateSummary`: aggregates all decisions made during the pipeline run
  - [ ] 2.3 Store decisions internally in `self._decisions: list[TrustGateDecision]` and rollback paths in `self._rollback_paths: list[dict[str, Any]]`

- [ ] Task 3: Create TrustGateStep pipeline step (AC: #1, #2, #3)
  - [ ] 3.1 Create `TrustGateStep` class in `trust_gate.py` implementing `InvestigationStep` protocol with `name = "Trust Gate Evaluation"`
  - [ ] 3.2 Constructor: `__init__(self, llm_client: LlmClient, context: InvestigationContext, status_updater: InvestigationStatusUpdater, pipeline_metadata: dict[str, Any] | None = None)` — same pattern as other steps
  - [ ] 3.3 Implement `execute() -> StepResult`:
    - Create TrustGateEvaluator from context
    - Scan pipeline_metadata for all remediation actions taken by prior steps (runbook execution, sandbox execution, metric verification, PR generation)
    - Re-evaluate each action against trust gates
    - Collect all trust gate decisions
    - For actions that were already correctly gated: validate and log
    - For actions requiring approval: add to `requires_approval` list
    - Register rollback paths for all autonomous actions at TL4-5
    - Return StepResult with comprehensive trust gate summary in data
  - [ ] 3.4 The step reviews and validates the trust gating that was already applied by individual steps. It does NOT block already-executed steps retroactively — it captures the comprehensive decision record for the evidence trail

- [ ] Task 4: Update EvidenceTrailFormatter for trust gate decisions (AC: #1, #2, #3)
  - [ ] 4.1 In `evidence_trail.py`, add a "Trust Gate Decisions" section in `format_pr_body()` after the Post-Fix Verification section
  - [ ] 4.2 Render trust level, confidence threshold, and a table of trust gate decisions: Action, Category, Decision, Confidence, Reason
  - [ ] 4.3 If any actions require approval, render "MANUAL APPROVAL REQUIRED" banner
  - [ ] 4.4 If rollback paths registered, render "Rollback Paths" subsection listing each registered rollback

- [ ] Task 5: Integrate TrustGateStep into agent pipeline (AC: #1, #2, #3)
  - [ ] 5.1 In `agent.py`, add lazy import for `TrustGateStep` in `_build_steps()`
  - [ ] 5.2 Insert `TrustGateStep` as step 12 (index 11) AFTER PRGeneratorStep (step 11). This is a post-hoc review step that summarizes all trust gate decisions made by the pipeline
  - [ ] 5.3 PRGeneratorStep stays at index 10, total pipeline becomes 12 steps

- [ ] Task 6: Update remediation package exports (AC: #1)
  - [ ] 6.1 Add `TrustGateEvaluator`, `TrustGateDecision`, `TrustGateSummary`, `TrustGateStep` to `remediation/__init__.py` imports and `__all__`

- [ ] Task 7: Write comprehensive unit tests (AC: #1, #2, #3)
  - [ ] 7.1 Create `investigator/tests/test_trust_gate.py` with `_make_evaluator()` and `_make_step()` factory functions following established patterns
  - [ ] 7.2 `TestTrustGateDecision`: dataclass creation, serialization to dict
  - [ ] 7.3 `TestEvaluateReadOnly`: read_only always allowed at TL1-5
  - [ ] 7.4 `TestEvaluateNotification`: notification always allowed at TL1-5
  - [ ] 7.5 `TestEvaluateClusterMutationTL1`: TL1 → advisory only, advisory_message populated
  - [ ] 7.6 `TestEvaluateClusterMutationTL2`: TL2 → advisory only
  - [ ] 7.7 `TestEvaluateClusterMutationTL3BelowThreshold`: TL3, confidence < threshold → blocked/requires_approval
  - [ ] 7.8 `TestEvaluateClusterMutationTL3AboveThreshold`: TL3, confidence >= threshold → allowed
  - [ ] 7.9 `TestEvaluateClusterMutationTL4`: TL4, confidence >= threshold → allowed (autonomous)
  - [ ] 7.10 `TestEvaluateClusterMutationTL5`: TL5, confidence >= threshold → allowed (full autonomy)
  - [ ] 7.11 `TestEvaluateCodeChangeTL1TL2`: code_change advisory at TL1-2
  - [ ] 7.12 `TestEvaluateCodeChangeTL3`: code_change with confidence gating at TL3
  - [ ] 7.13 `TestAdvisoryMessage`: advisory_message content format and category-specific detail
  - [ ] 7.14 `TestRollbackRegistration`: register_rollback_path returns proper entry with action details
  - [ ] 7.15 `TestAutonomousNotification`: notify_autonomous_action logs and calls status_updater
  - [ ] 7.16 `TestTrustGateSummary`: summary aggregation from multiple decisions
  - [ ] 7.17 `TestConfidenceNone`: when confidence is None, treat as 0.0 for gating purposes
  - [ ] 7.18 `TestTrustGateStepExecution`: TrustGateStep execute() returns correct StepResult
  - [ ] 7.19 `TestTrustGateStepWithRunbookData`: step scans runbook execution results
  - [ ] 7.20 `TestTrustGateStepWithSandboxData`: step scans sandbox execution results
  - [ ] 7.21 `TestTrustGateStepWithPRData`: step scans PR generation results
  - [ ] 7.22 `TestTrustGateStepWithMetricVerificationData`: step scans metric verification results

- [ ] Task 8: Write integration tests (AC: #1)
  - [ ] 8.1 Create `investigator/tests/test_agent_trust_gate_integration.py`: verify `TrustGateStep` is at index 11 (step 12) in `_build_steps()`, total pipeline length is 12
  - [ ] 8.2 Update `investigator/tests/test_agent_pr_integration.py`: total steps 11 → 12
  - [ ] 8.3 Update `investigator/tests/test_agent_metric_verifier_integration.py`: total steps 11 → 12
  - [ ] 8.4 Update `investigator/tests/test_agent_sandbox_integration.py`: total steps 11 → 12
  - [ ] 8.5 Update `investigator/tests/test_agent_runbook_integration.py`: total steps 11 → 12
  - [ ] 8.6 Update `investigator/tests/test_agent_testplan_integration.py`: total steps 11 → 12

- [ ] Task 9: Update evidence trail tests (AC: #1, #2, #3)
  - [ ] 9.1 In `investigator/tests/test_evidence_trail.py`, add tests for trust gate section: `TestTrustGateDecisionsSection` — decisions rendered in table, requires_approval banner, rollback paths listed, no trust gate data shows no section

- [ ] Task 10: Run all investigator tests (AC: #1, #2, #3)
  - [ ] 10.1 Run `cd investigator && python -m pytest tests/ -v` — all existing + new tests pass
  - [ ] 10.2 Run `cd investigator && python -m ruff check .` — no new warnings
  - [ ] 10.3 Run `cd investigator && python -m mypy beeper_investigator/ --strict` — no new errors
  - [ ] 10.4 Verify zero regressions in existing step tests

## Dev Notes

### Architecture Patterns to Follow

**CRITICAL CONTEXT: This story creates a TrustGateEvaluator utility and a TrustGateStep pipeline step that centralizes trust-level decision recording and evidence for the remediation pipeline. The existing steps (RunbookExecutorStep, SandboxExecutorStep, MetricVerifierStep, PRGeneratorStep) ALREADY implement their own trust gating correctly — this story does NOT replace those gates. Instead, TrustGateStep is a POST-HOC review step at the END of the pipeline that: (1) scans pipeline_metadata for all remediation actions taken, (2) records a comprehensive trust gate decision log, (3) registers rollback paths for autonomous actions at TL4-5, (4) adds trust gate decisions to the evidence trail, and (5) captures approval requirements for confidence-blocked actions.**

**FR29 (trust-gated remediation)** maps to `investigator/remediation/__init__.py` (gate check before steps) per architecture.md — implement as `trust_gate.py` in the remediation package.

**What already exists (DO NOT recreate):**

| Component | Location | Status |
|-----------|----------|--------|
| `InvestigationStep` protocol + `StepResult` | `investigator/beeper_investigator/steps/__init__.py` | Done (v0.1.0) |
| `InvestigationContext` with `trust_level` and `confidence_threshold` | `investigator/beeper_investigator/context.py` | Done (Story 4-2) |
| RunbookExecutorStep trust gating (TL1-2 advisory, TL3+ confidence gate) | `investigator/beeper_investigator/remediation/runbook_executor.py` | Done (Story 4-2) |
| TestPlannerStep (always generates — advisory only, no trust gate) | `investigator/beeper_investigator/remediation/test_planner.py` | Done (Story 4-3) |
| PRGeneratorStep trust gating (TL1-2 skip, TL3 draft, TL4-5 ready) | `investigator/beeper_investigator/remediation/pr_generator.py` | Done (Story 4-4) |
| SandboxExecutorStep trust gating (TL1-2 skip, TL3+ execute) | `investigator/beeper_investigator/remediation/sandbox_executor.py` | Done (Story 4-5) |
| MetricVerifierStep trust gating (TL1-2 skip, TL3+ verify) | `investigator/beeper_investigator/remediation/metric_verifier.py` | Done (Story 4-6) |
| `EvidenceTrailFormatter` with advisory test plan, sandbox results, verification sections | `investigator/beeper_investigator/remediation/evidence_trail.py` | Done — extend with trust gate section |
| `InvestigatorAgent._build_steps()` — 11 steps currently | `investigator/beeper_investigator/agent.py` | Done — will become 12 |
| `InvestigationStatusUpdater` | `investigator/beeper_investigator/k8s/status.py` | Done (v0.1.0) |

**What this story adds:**

| Component | Description |
|-----------|-------------|
| `remediation/trust_gate.py` | `TrustGateEvaluator` utility + `TrustGateDecision` + `TrustGateSummary` + `TrustGateStep` |
| Evidence trail trust gate section | Trust gate decisions table, approval banners, rollback paths in PR body |
| Agent pipeline step 12 | `TrustGateStep` wired into `_build_steps()` after PRGeneratorStep |
| Tests | Unit + integration tests for all new components |

### Pipeline Metadata — Data Flow (CRITICAL)

The `pipeline_metadata` dict is shared by reference across all steps. After prior steps run, it contains the following keys that TrustGateStep must scan:

```python
# From RunbookExecutorStep (step 7):
{
    "runbook_found": True,
    "steps_executed": 3,
    "steps_advisory": 1,          # Advisory actions count
    "steps_blocked": 0,           # Blocked by confidence gate
    "advisory_actions": ["Advisory: would execute 'restart pod' at TL3+"],
    "execution_log": [...],       # Each step with status
}

# From SandboxExecutorStep (step 9):
{
    "sandbox_executed": True,     # or False with skip_reason
    "skip_reason": "trust_level_insufficient",  # If skipped
    "sandbox_overall_status": "pass",
}

# From MetricVerifierStep (step 10):
{
    "verification_executed": True,
    "verification_status": "confirmed",
    "fix_verified": True,
    "rollback_recommended": False,
    "verification_skip_reason": "trust_level_insufficient",  # If skipped
}

# From PRGeneratorStep (step 11):
{
    "pr_generated": True,
    "pr_url": "https://github.com/...",
    "draft": True,                # Draft at TL3, ready at TL4-5
    "trust_level": 3,
}
```

TrustGateStep will ADD to pipeline_metadata:
```python
{
    "trust_gate_evaluated": True,
    "trust_gate_trust_level": 3,
    "trust_gate_confidence_threshold": 0.9,
    "trust_gate_total_actions": 5,
    "trust_gate_executed": 3,
    "trust_gate_advisory": 1,
    "trust_gate_blocked": 0,
    "trust_gate_requires_approval": 1,
    "trust_gate_decisions": [...],          # Serialized decisions
    "trust_gate_rollback_paths": [...],     # Registered rollback entries
    "trust_gate_approval_required": True,   # True if any action requires manual approval
}
```

### Constructor Signature — MUST Follow Existing Step Pattern

```python
class TrustGateStep:
    """Post-hoc trust gate evaluation and evidence recording."""

    name: str = "Trust Gate Evaluation"

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
        self._evaluator = TrustGateEvaluator(context, status_updater)
```

### Trust Gate Decision Logic (CRITICAL)

```python
def evaluate(
    self,
    action_name: str,
    action_category: str,
    confidence: float | None = None,
) -> TrustGateDecision:
    """Evaluate whether an action is permitted under current trust configuration.

    action_category: "read_only" | "cluster_mutation" | "code_change" | "notification"
    """
    effective_confidence = confidence if confidence is not None else 0.0
    tl = self.context.trust_level
    threshold = self.context.confidence_threshold

    # Read-only and notification actions always allowed
    if action_category in ("read_only", "notification"):
        return TrustGateDecision(
            allowed=True, action_type="executed",
            trust_level=tl, confidence=confidence,
            confidence_threshold=threshold,
            reason="Always permitted",
            advisory_message=None, rollback_registered=False,
        )

    # TL1-2: advisory only for mutations and code changes
    if tl <= 2:
        return TrustGateDecision(
            allowed=False, action_type="advisory",
            trust_level=tl, confidence=confidence,
            confidence_threshold=threshold,
            reason=f"Trust level {tl} — advisory only",
            advisory_message=self._build_advisory_message(action_name, action_category),
            rollback_registered=False,
        )

    # TL3-5: confidence gate
    if effective_confidence < threshold:
        return TrustGateDecision(
            allowed=False, action_type="requires_approval",
            trust_level=tl, confidence=confidence,
            confidence_threshold=threshold,
            reason=(
                f"Confidence {effective_confidence:.2f} below "
                f"threshold {threshold:.2f} — requires manual approval"
            ),
            advisory_message=None, rollback_registered=False,
        )

    # TL3-5 with confidence above threshold: allowed
    return TrustGateDecision(
        allowed=True, action_type="executed",
        trust_level=tl, confidence=confidence,
        confidence_threshold=threshold,
        reason=f"Trust level {tl}, confidence {effective_confidence:.2f} above threshold",
        advisory_message=None, rollback_registered=False,
    )
```

### Evidence Trail Enhancement

Add to `EvidenceTrailFormatter.format_pr_body()` after the Post-Fix Verification section:

```python
# Trust Gate Decisions
if pipeline_metadata.get("trust_gate_evaluated"):
    tl = pipeline_metadata.get("trust_gate_trust_level", "?")
    threshold = pipeline_metadata.get("trust_gate_confidence_threshold", "?")
    decisions = pipeline_metadata.get("trust_gate_decisions", [])
    rollback_paths = pipeline_metadata.get("trust_gate_rollback_paths", [])
    approval_required = pipeline_metadata.get("trust_gate_approval_required", False)

    trust_lines = [
        "### Trust Gate Decisions\n"
        f"**Trust Level:** TL{tl} | **Confidence Threshold:** {threshold}\n"
    ]

    if approval_required:
        trust_lines.append(
            "**MANUAL APPROVAL REQUIRED** — some actions blocked by confidence gate.\n"
        )

    if decisions:
        trust_lines.append("| Action | Category | Decision | Confidence | Reason |")
        trust_lines.append("|--------|----------|----------|------------|--------|")
        for d in decisions:
            if isinstance(d, dict):
                conf = d.get("confidence")
                conf_str = f"{conf:.2f}" if conf is not None else "N/A"
                trust_lines.append(
                    f"| {d.get('action_name', '?')[:30]} "
                    f"| {d.get('action_category', '?')} "
                    f"| {d.get('action_type', '?')} "
                    f"| {conf_str} "
                    f"| {d.get('reason', '')[:40]} |"
                )

    if rollback_paths:
        trust_lines.append("\n**Registered Rollback Paths:**\n")
        for rp in rollback_paths:
            if isinstance(rp, dict):
                trust_lines.append(
                    f"- {rp.get('action_name', '?')}: {rp.get('rollback_action', '?')}"
                )

    sections.append("\n".join(trust_lines) + "\n")
```

### Critical Guardrails

- **Post-hoc step**: TrustGateStep runs AFTER all other remediation steps. It does NOT gate them — individual steps gate themselves. TrustGateStep records, validates, and creates the evidence trail
- **No LLM calls needed**: This step reads pipeline_metadata and evaluates trust decisions — no LLM interpretation
- **Non-fatal**: All `StepResult` returns have `success=True` — trust gate review never crashes pipeline
- **Confidence None handling**: When confidence is not provided (None), treat as 0.0 for gating purposes (conservative default)
- **Rollback registration is advisory**: `register_rollback_path()` records rollback metadata in pipeline_metadata. Actual rollback execution is handled by the operator (FR62)
- **Pipeline position**: Step 12 (index 11) — after PRGeneratorStep (step 11). This is the LAST step in the pipeline
- **Zero regressions** — all existing 773 investigator tests must continue passing
- **ruff clean** — no new warnings
- **mypy strict** — must pass strict mode (no new errors)
- **No new dependencies** — uses only existing InvestigationContext, InvestigationStatusUpdater, StepResult

### Test Pattern (follow existing test_metric_verifier.py)

```python
def _make_evaluator(trust_level=3, confidence_threshold=0.9):
    """Factory for TrustGateEvaluator with mocked dependencies."""
    ctx = InvestigationContext(
        investigation_id="test-inv-001",
        namespace="default",
        condition="high_error_rate",
        service="payments",
        severity="high",
        trust_level=trust_level,
        confidence_threshold=confidence_threshold,
    )
    status = MagicMock(spec=InvestigationStatusUpdater)
    evaluator = TrustGateEvaluator(ctx, status)
    return evaluator, ctx, status


def _make_step(pipeline_metadata=None, trust_level=3, **overrides):
    """Factory for TrustGateStep with mocked dependencies."""
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
    defaults = {
        "llm_client": llm,
        "context": ctx,
        "status_updater": status,
        "pipeline_metadata": pipeline_metadata or {},
    }
    defaults.update(overrides)
    step = TrustGateStep(**defaults)
    return step, defaults
```

### Project Structure Notes

- New file: `investigator/beeper_investigator/remediation/trust_gate.py`
- Modified: `investigator/beeper_investigator/remediation/__init__.py` (add TrustGateEvaluator, TrustGateDecision, TrustGateSummary, TrustGateStep exports)
- Modified: `investigator/beeper_investigator/remediation/evidence_trail.py` (add trust gate decisions section)
- Modified: `investigator/beeper_investigator/agent.py` (insert step 12, total steps 11 → 12)
- New test: `investigator/tests/test_trust_gate.py`
- New test: `investigator/tests/test_agent_trust_gate_integration.py`
- Modified test: `investigator/tests/test_agent_pr_integration.py` (total steps 11 → 12)
- Modified test: `investigator/tests/test_agent_metric_verifier_integration.py` (total steps 11 → 12)
- Modified test: `investigator/tests/test_agent_sandbox_integration.py` (total steps 11 → 12)
- Modified test: `investigator/tests/test_agent_runbook_integration.py` (total steps 11 → 12)
- Modified test: `investigator/tests/test_agent_testplan_integration.py` (total steps 11 → 12)
- Modified test: `investigator/tests/test_evidence_trail.py` (trust gate decisions section tests)

### Previous Story Intelligence

**From Story 4-6 (Post-Fix Metric Verification):**
- MetricVerifierStep uses `verification_skip_reason` (namespaced) to avoid collision with SandboxExecutorStep's `skip_reason` — use `trust_gate_` prefix for all TrustGateStep metadata keys
- Pipeline has 11 steps. TrustGateStep will be step 12 (index 11)
- Code review renamed stale test name `test_total_pipeline_length_is_10` → `test_total_pipeline_length_is_11` — update to 12
- 773 passing investigator tests (12 pre-existing async failures unchanged)

**From Story 4-2 (Human-Language Runbook Execution):**
- RunbookExecutorStep has the most comprehensive trust gating example with advisory_actions, blocked_actions, executed_steps lists
- Confidence gate: `confidence >= self.context.confidence_threshold` — reuse exact pattern
- Advisory message pattern: `"Advisory: would execute '{action_desc}' at TL3+"`

**From Story 4-4 (Auto-PR Generation with Evidence Trail):**
- PRGeneratorStep uses `draft = self.context.trust_level == 3` for TL3 draft PRs
- EvidenceTrailFormatter sections are ordered: Investigation Summary → RCA → Log Correlation → Production Conditions → Advisory Test Plan → Sandbox Results → Post-Fix Verification → Audit Trail → Footer
- Trust Gate Decisions section should go between Post-Fix Verification and Audit Trail

### Git Intelligence

Recent commits: `MAESTRO: 4-6 done`, `MAESTRO: implement story 4-6 (Post-Fix Metric Verification)`. Follow commit pattern: `MAESTRO: implement story 4-7 (Trust-Gated Remediation Actions)`. Current test counts: operator 527 passed (4 pre-existing), investigator 773 passed (12 pre-existing async), UI 1,388 passed.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 4, Story 4.7] — User story, acceptance criteria
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Map] — FR29: `investigator/remediation/__init__.py`
- [Source: _bmad-output/planning-artifacts/architecture.md#Auto-Remediation Architecture] — Trust-gated remediation, rollback within 60s
- [Source: _bmad-output/planning-artifacts/prd.md#FR62] — System can rollback any autonomous action
- [Source: _bmad-output/planning-artifacts/prd.md#NFR9] — Scoped per-repo tokens
- [Source: _bmad-output/planning-artifacts/prd.md#NFR13] — Sandbox isolation
- [Source: _bmad-output/planning-artifacts/prd.md#NFR16] — Autonomous action rollback within 60 seconds
- [Source: investigator/beeper_investigator/context.py] — InvestigationContext with trust_level, confidence_threshold
- [Source: investigator/beeper_investigator/remediation/runbook_executor.py] — Trust gating + confidence gate reference implementation
- [Source: investigator/beeper_investigator/remediation/pr_generator.py] — PRGeneratorStep trust gating, draft vs ready
- [Source: investigator/beeper_investigator/remediation/sandbox_executor.py] — SandboxExecutorStep trust gating
- [Source: investigator/beeper_investigator/remediation/metric_verifier.py] — MetricVerifierStep trust gating, verification_skip_reason namespacing
- [Source: investigator/beeper_investigator/remediation/evidence_trail.py] — EvidenceTrailFormatter section ordering
- [Source: investigator/beeper_investigator/agent.py] — Agent lifecycle, _build_steps(), pipeline_metadata sharing
- [Source: _bmad-output/implementation-artifacts/4-6-post-fix-metric-verification.md] — Previous story patterns and lessons

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Implemented TrustGateEvaluator utility class with evaluate(), register_rollback_path(), notify_autonomous_action(), get_summary()
- Created TrustGateDecision and TrustGateSummary dataclasses
- Created TrustGateStep pipeline step (step 12, index 11) — post-hoc trust gate review
- Extended EvidenceTrailFormatter with Trust Gate Decisions section (between Post-Fix Verification and Audit Trail)
- Inserted TrustGateStep into agent pipeline as last step after PRGeneratorStep
- 42 new unit tests (test_trust_gate.py) + 7 integration tests (test_agent_trust_gate_integration.py) + 6 evidence trail tests
- Updated 5 existing integration test files (pipeline length 11 → 12)
- All suites: investigator 828 passed (12 pre-existing async failures), ruff clean, mypy clean (8 pre-existing stubs errors only)

### File List

- investigator/beeper_investigator/remediation/trust_gate.py (NEW)
- investigator/beeper_investigator/remediation/__init__.py (MODIFIED)
- investigator/beeper_investigator/remediation/evidence_trail.py (MODIFIED)
- investigator/beeper_investigator/agent.py (MODIFIED)
- investigator/tests/test_trust_gate.py (NEW)
- investigator/tests/test_agent_trust_gate_integration.py (NEW)
- investigator/tests/test_evidence_trail.py (MODIFIED)
- investigator/tests/test_agent_pr_integration.py (MODIFIED)
- investigator/tests/test_agent_metric_verifier_integration.py (MODIFIED)
- investigator/tests/test_agent_sandbox_integration.py (MODIFIED)
- investigator/tests/test_agent_runbook_integration.py (MODIFIED)
- investigator/tests/test_agent_testplan_integration.py (MODIFIED)
