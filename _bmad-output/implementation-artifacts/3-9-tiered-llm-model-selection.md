# Story 3.9: Tiered LLM Model Selection

Status: done

## Story

As Beeper,
I want to use lightweight models for screening and powerful models for deep RCA,
so that I balance cost and capability appropriately.

## Acceptance Criteria

1. **Given** LLM configuration includes tiered models, **When** the investigator needs LLM assistance, **Then** model selection is based on task type: screening/triage uses the screening model (FR43), investigation/correlation uses the default model (FR44), and deep RCA/complex reasoning uses the deep RCA model (FR44).

2. **Given** initial screening is performed, **When** using the lightweight model, **Then** response latency is fast **And** cost per screening is minimal.

3. **Given** deep RCA is required, **When** escalating to the powerful model, **Then** the escalation is logged with rationale **And** the more capable model is used for reasoning.

4. **Given** model routing decisions are made, **When** the investigation completes, **Then** model usage is tracked for cost reporting.

## Tasks / Subtasks

- [x] Task 1: Extend LlmConfig with deep RCA model (AC: 1)
  - [x] 1.1 Add `deep_rca_model: str | None = None` field to `LlmConfig` dataclass
  - [x] 1.2 Load from `BEEPER_LLM_DEEP_RCA_MODEL` env var in `from_env()` (same `or None` pattern as screening_model)
  - [x] 1.3 Add `deep_rca_model` property to `LlmClient` that returns configured model or falls back to `get_litellm_model()` (same pattern as `screening_model` property)

- [x] Task 2: Create model tier selection helper (AC: 1, 3)
  - [x] 2.1 Add `ModelTier` string literal type: `"screening" | "standard" | "deep_rca"`
  - [x] 2.2 Add `select_model(tier: ModelTier) -> str` method on `LlmClient` that returns the appropriate model name for the tier
  - [x] 2.3 `select_model("screening")` returns `self.screening_model`
  - [x] 2.4 `select_model("standard")` returns `self.config.get_litellm_model()`
  - [x] 2.5 `select_model("deep_rca")` returns `self.deep_rca_model`
  - [x] 2.6 Log model selection with tier and rationale at INFO level

- [x] Task 3: Add model usage tracking to LlmClient (AC: 4)
  - [x] 3.1 Add `_model_usage: dict[str, int]` counter dict to `LlmClient.__init__()` tracking call count per model name
  - [x] 3.2 Increment counter in `complete_sync()` after successful completion (use `effective_model` as key)
  - [x] 3.3 Add `get_model_usage() -> dict[str, int]` method returning a copy of the usage dict
  - [x] 3.4 Add `reset_model_usage() -> None` method

- [x] Task 4: Update RCAHypothesisStep to use deep RCA model (AC: 1, 3)
  - [x] 4.1 Pass `model=self.llm_client.select_model("deep_rca")` to `complete_sync()` call
  - [x] 4.2 Log escalation message: "Escalating to deep RCA model for hypothesis generation"
  - [x] 4.3 Include `model_tier: "deep_rca"` in StepResult data
  - [x] 4.4 Include `model_used: <model_name>` in StepResult data

- [x] Task 5: Update ResolutionRecommendationStep to use standard model explicitly (AC: 1)
  - [x] 5.1 Pass `model=self.llm_client.select_model("standard")` to `complete_sync()` call
  - [x] 5.2 Include `model_tier: "standard"` in StepResult data
  - [x] 5.3 Include `model_used: <model_name>` in StepResult data

- [x] Task 6: Update InvestigationDocumentationStep to use standard model explicitly (AC: 1)
  - [x] 6.1 Pass `model=self.llm_client.select_model("standard")` to `complete_sync()` call
  - [x] 6.2 Include `model_tier: "standard"` in StepResult data
  - [x] 6.3 Include `model_used: <model_name>` in StepResult data

- [x] Task 7: Update CustomerImpactStep to use select_model (AC: 1, 2)
  - [x] 7.1 Replace `model=self.llm_client.screening_model` with `model=self.llm_client.select_model("screening")` in `complete_sync()` call
  - [x] 7.2 Include `model_tier: "screening"` in StepResult data
  - [x] 7.3 Include `model_used: <model_name>` in StepResult data

- [x] Task 8: Propagate model usage to InvestigationResult (AC: 4)
  - [x] 8.1 After `_run_steps()` completes, call `self.llm_client.get_model_usage()` and include in `InvestigationResult.metadata` under key `model_usage`
  - [x] 8.2 Model usage dict flows through to `_persist_result()` payload automatically via safe_metadata
  - [x] 8.3 Verify `model_usage` is NOT in the `_RESERVED_KEYS` set (it is not — "model_usage" is safe)

- [x] Task 9: Tests (AC: all)
  - [x] 9.1 Test `LlmConfig.deep_rca_model` field defaults to None
  - [x] 9.2 Test `LlmConfig.from_env()` loads `BEEPER_LLM_DEEP_RCA_MODEL`
  - [x] 9.3 Test `LlmClient.deep_rca_model` property returns configured model
  - [x] 9.4 Test `LlmClient.deep_rca_model` property falls back to default model when not configured
  - [x] 9.5 Test `select_model("screening")` returns screening model
  - [x] 9.6 Test `select_model("standard")` returns default model
  - [x] 9.7 Test `select_model("deep_rca")` returns deep RCA model
  - [x] 9.8 Test `select_model()` logs model selection at INFO level
  - [x] 9.9 Test `get_model_usage()` tracks call counts per model
  - [x] 9.10 Test `reset_model_usage()` clears counters
  - [x] 9.11 Test RCAHypothesisStep passes deep_rca model to complete_sync
  - [x] 9.12 Test RCAHypothesisStep includes model_tier and model_used in data
  - [x] 9.13 Test ResolutionRecommendationStep includes model_tier in data
  - [x] 9.14 Test InvestigationDocumentationStep includes model_tier in data
  - [x] 9.15 Test CustomerImpactStep uses select_model("screening") instead of direct property
  - [x] 9.16 Test model_usage propagated to InvestigationResult.metadata
  - [x] 9.17 Test all tiers fall back to default model when tier-specific model not configured

## Dev Notes

### Current Model Architecture

The `LlmClient` already supports 2-tier model selection. Story 3.9 extends this to 3 tiers:

| Tier | Config Env Var | LlmClient Property | Current Usage | Target Model |
|------|---------------|--------------------|----|-------|
| **Screening** | `BEEPER_LLM_SCREENING_MODEL` | `screening_model` | `CustomerImpactStep` only | claude-3-haiku |
| **Standard** (default) | `BEEPER_LLM_MODEL` | `model` / `get_litellm_model()` | RCA, Resolution, Documentation | claude-sonnet-4 |
| **Deep RCA** | `BEEPER_LLM_DEEP_RCA_MODEL` (NEW) | `deep_rca_model` (NEW) | None yet → `RCAHypothesisStep` | claude-opus-4 |

### Existing Model Selection Patterns

**Screening model (already implemented in Story 3.3):**

```python
# LlmConfig (llm/client.py:26)
screening_model: str | None = None

# LlmClient property (llm/client.py:337-344)
@property
def screening_model(self) -> str:
    """Falls back to get_litellm_model() for provider prefix correctness."""
    return self.config.screening_model or self.config.get_litellm_model()

# Usage in CustomerImpactStep (impact_assessment.py:94)
raw = self.llm_client.complete_sync(
    messages, max_tokens=256, temperature=0.0,
    model=self.llm_client.screening_model,
)
```

**Default model (used by 3 steps):**

```python
# No explicit model parameter → uses default
raw = self.llm_client.complete_sync(
    messages, max_tokens=1024, temperature=0.0,
)
# effective_model = model or self.config.get_litellm_model()
```

### Model Override Mechanism in `complete_sync()`

```python
def complete_sync(
    self,
    messages: list[dict[str, str]],
    max_tokens: int = 4096,
    temperature: float = 0.0,
    *,
    model: str | None = None,   # keyword-only override
    **kwargs: Any,
) -> str:
    effective_model = model or self.config.get_litellm_model()
    response = litellm.completion(
        model=effective_model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        **kwargs,
    )
```

The `model` parameter is keyword-only (after `*`). All steps can pass any model name here. The architecture already supports N tiers — Story 3.9 adds the 3rd tier and formalizes selection.

### Environment Variable Loading Pattern

Follow the exact pattern from `from_env()` (llm/client.py:72):

```python
screening_model = os.environ.get("BEEPER_LLM_SCREENING_MODEL") or None
# Add:
deep_rca_model = os.environ.get("BEEPER_LLM_DEEP_RCA_MODEL") or None
```

### `select_model()` Design

This is a thin convenience method — NOT a complex router. It maps tier names to the correct model string and logs the selection:

```python
from typing import Literal

ModelTier = Literal["screening", "standard", "deep_rca"]

def select_model(self, tier: ModelTier) -> str:
    """Select model for the given task tier.

    Args:
        tier: Task tier determining model capability level.

    Returns:
        Model string formatted for LiteLLM.
    """
    if tier == "screening":
        model = self.screening_model
    elif tier == "deep_rca":
        model = self.deep_rca_model
    else:
        model = self.config.get_litellm_model()
    logger.info(
        "Model tier '%s' selected: %s", tier, model
    )
    return model
```

### Model Usage Tracking

Simple counter dict — NOT a database or complex system (Story 6.2 handles cost caps):

```python
def __init__(self, config: LlmConfig) -> None:
    self.config = config
    self._configure_litellm()
    self._model_usage: dict[str, int] = {}

# In complete_sync(), after successful completion:
self._model_usage[effective_model] = (
    self._model_usage.get(effective_model, 0) + 1
)

def get_model_usage(self) -> dict[str, int]:
    return dict(self._model_usage)

def reset_model_usage(self) -> None:
    self._model_usage.clear()
```

### Step Modifications — Minimal Changes

Each step needs exactly 2 changes:
1. Add `model=self.llm_client.select_model("<tier>")` to the `complete_sync()` call
2. Add `model_tier` and `model_used` to the StepResult data dict

**Example for RCAHypothesisStep (rca_hypothesis.py):**

```python
# In execute() or _parse_result():
model_name = self.llm_client.select_model("deep_rca")

# In the complete_sync() call:
raw = self.llm_client.complete_sync(
    messages,
    max_tokens=1024,
    temperature=0.0,
    model=model_name,
)

# In StepResult data (add to existing keys):
"model_tier": "deep_rca",
"model_used": model_name,
```

**For fallback paths (when LLM is NOT called):** set `model_tier: "none"` and `model_used: None`.

### Agent Integration — Model Usage Propagation

After `_run_steps()`, the agent should capture model usage stats:

```python
# In agent.py, after result = self._run_steps():
model_usage = self.llm_client.get_model_usage()
result.metadata["model_usage"] = model_usage
```

The `model_usage` key is NOT in `_RESERVED_KEYS` (which only contains: `investigation_id`, `service`, `condition`, `severity`, `status`, `summary`, `findings`, `created_at`), so it flows through to the Qdrant payload automatically.

### Critical Anti-Patterns to Avoid

1. **Do NOT add a complex model router or strategy pattern.** This is a simple 3-tier mapping, not a dynamic routing engine.
2. **Do NOT modify the `complete_sync()` signature.** The `model` kwarg already supports tier selection.
3. **Do NOT hardcode model names (e.g., "claude-3-haiku") in step code.** Always use `select_model()` or properties.
4. **Do NOT make model tier selection async.** Agent is synchronous.
5. **Do NOT add model usage tracking to `embed_sync()`.** Embedding calls are separate from completion tiers.
6. **Do NOT add token counting or cost estimation.** That's Story 6.2 (LLM spending caps).
7. **Do NOT modify tests that verify existing behavior unless the behavior changes.** Only add new keys to StepResult data — existing keys remain unchanged.
8. **Do NOT break existing fallback paths.** Steps that fail LLM calls still return `StepResult(success=True)` — add `model_tier: "none"` for fallback.
9. **Do NOT forget to update fallback result data schemas.** Every code path must include `model_tier` and `model_used`.
10. **Do NOT add import-time imports in agent.py.** Keep the lazy import pattern in `_build_steps()`.

### Existing Test Patterns for Model Selection

Reference: `tests/test_llm_screening.py` and `tests/test_impact_assessment.py`

```python
# test_llm_screening.py — LlmConfig screening model tests
class TestLlmConfigScreeningModel:
    def test_screening_model_default_none(self) -> None: ...
    def test_screening_model_from_env(self) -> None: ...

class TestLlmClientScreeningModel:
    def test_screening_model_configured(self) -> None: ...
    def test_screening_model_fallback(self) -> None: ...

class TestCompleteSyncModelOverride:
    def test_model_override_used(self) -> None: ...
    def test_no_override_uses_default(self) -> None: ...

# test_impact_assessment.py — Step-level screening model test
def test_uses_screening_model(self) -> None:
    """Verifies screening model is passed to complete_sync."""
    step, mock_llm, _ = _make_step()
    step.execute()
    call_kwargs = mock_llm.complete_sync.call_args
    assert call_kwargs.kwargs.get("model") == "claude-3-haiku-20240307"
```

Add similar test patterns for `deep_rca_model` and `select_model()`. For step tests, verify:

```python
call_kwargs = mock_llm.complete_sync.call_args
assert call_kwargs.kwargs.get("model") == expected_model
assert result.data["model_tier"] == expected_tier
assert result.data["model_used"] == expected_model
```

### Existing Code to Modify

| File | Change |
|------|--------|
| `llm/client.py` | Add `deep_rca_model` to `LlmConfig`, add `deep_rca_model` property and `select_model()` method and `_model_usage` tracking to `LlmClient` |
| `steps/rca_hypothesis.py` | Add `model=select_model("deep_rca")` to `complete_sync()`, add `model_tier`/`model_used` to StepResult data |
| `steps/resolution_recommendations.py` | Add `model=select_model("standard")` to `complete_sync()`, add `model_tier`/`model_used` to StepResult data |
| `steps/investigation_documentation.py` | Add `model=select_model("standard")` to `complete_sync()`, add `model_tier`/`model_used` to StepResult data |
| `steps/impact_assessment.py` | Replace `model=self.llm_client.screening_model` with `model=select_model("screening")`, add `model_tier`/`model_used` to StepResult data |
| `agent.py` | Add `model_usage` propagation after `_run_steps()` |

### New Files to Create

| File | Purpose |
|------|---------|
| `tests/test_tiered_model_selection.py` | Tests for `deep_rca_model`, `select_model()`, model usage tracking, tier propagation in steps |

### Project Structure Notes

```
investigator/beeper_investigator/
├── llm/
│   ├── client.py                 # MODIFY: deep_rca_model, select_model(), _model_usage
│   └── cost.py                   # NOT modified (future Story 6.2)
├── steps/
│   ├── impact_assessment.py      # MODIFY: select_model("screening"), model_tier/model_used
│   ├── rca_hypothesis.py         # MODIFY: select_model("deep_rca"), model_tier/model_used
│   ├── resolution_recommendations.py  # MODIFY: select_model("standard"), model_tier/model_used
│   └── investigation_documentation.py # MODIFY: select_model("standard"), model_tier/model_used
├── agent.py                      # MODIFY: model_usage propagation

investigator/tests/
├── test_llm_screening.py         # NOT modified (existing screening tests still valid)
├── test_impact_assessment.py     # MODIFY: update to use select_model
├── test_tiered_model_selection.py # NEW: comprehensive tier selection tests
└── ... (existing test files — update model_tier/model_used in data assertions)
```

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic-3, Story 3.9] — FR43, FR44, AC1-AC4
- [Source: _bmad-output/planning-artifacts/architecture.md] — LLM integration, tiered models (Haiku/Sonnet/Opus)
- [Source: investigator/beeper_investigator/llm/client.py] — LlmConfig, LlmClient, screening_model, complete_sync model kwarg
- [Source: investigator/beeper_investigator/steps/impact_assessment.py] — screening model usage pattern
- [Source: investigator/tests/test_llm_screening.py] — screening model test patterns
- [Source: investigator/tests/test_impact_assessment.py] — step-level model test pattern
- [Source: _bmad-output/implementation-artifacts/3-8-investigation-documentation.md] — Anti-pattern: "Do NOT hardcode model names (Story 3.9 handles tiered selection)"

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- All 9 tasks implemented with 25 tests (test_tiered_model_selection.py)
- 315 tests pass (excluding 6 pre-existing async failures in test_llm_client.py)
- Updated existing test mocks in 4 test files to support select_model()
- Updated schema key sets in test_investigation_documentation.py
- Fallback paths with LLM attempted: preserve actual tier/model; no-data paths: "none"/None
- model_usage propagated through InvestigationResult.metadata to Qdrant payload
- Code review fixes applied: async tracking, namespaced model keys, fallback consistency, tier validation

### Change Log

- Tasks 1-3: Extended LlmConfig/LlmClient with deep_rca_model, ModelTier, select_model(), _model_usage tracking
- Tasks 4-7: Updated all 4 step files to use select_model() and include model_tier/model_used in StepResult data
- Task 8: Added model_usage propagation in agent.py after _run_steps()
- Task 9: Created test_tiered_model_selection.py with 25 comprehensive tests
- Review Fix: Added model usage tracking to async complete() method
- Review Fix: Namespaced model_tier/model_used keys per step (impact_, rca_, resolution_, doc_) to prevent pipeline clobbering
- Review Fix: Fallback paths now preserve actual tier/model when LLM was attempted (only "none" when LLM not called)
- Review Fix: select_model() raises ValueError for unrecognized tier (was silent fallthrough)

### File List

- investigator/beeper_investigator/llm/client.py (MODIFIED)
- investigator/beeper_investigator/steps/rca_hypothesis.py (MODIFIED)
- investigator/beeper_investigator/steps/resolution_recommendations.py (MODIFIED)
- investigator/beeper_investigator/steps/investigation_documentation.py (MODIFIED)
- investigator/beeper_investigator/steps/impact_assessment.py (MODIFIED)
- investigator/beeper_investigator/agent.py (MODIFIED)
- investigator/tests/test_tiered_model_selection.py (NEW)
- investigator/tests/test_impact_assessment.py (MODIFIED - mock update)
- investigator/tests/test_rca_hypothesis.py (MODIFIED - mock update, test rename)
- investigator/tests/test_resolution_recommendations.py (MODIFIED - mock update, test rename)
- investigator/tests/test_investigation_documentation.py (MODIFIED - mock update, schema keys)
