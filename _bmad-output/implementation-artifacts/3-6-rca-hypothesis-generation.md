# Story 3.6: RCA Hypothesis Generation

Status: done

## Story

As an Investigator,
I want to generate a root cause hypothesis with an explicit confidence level,
so that SREs understand the certainty of my findings.

## Acceptance Criteria

1. **Given** signal correlation is complete, **When** the investigator synthesizes findings, **Then** a root cause hypothesis is generated (FR7) **And** the hypothesis includes: Root cause description, Confidence level (high/medium/low with percentage), Supporting evidence (correlated signals), Alternative hypotheses if confidence < high.

2. **Given** strong signal correlation exists, **When** generating hypothesis, **Then** powerful LLM model is used for deep RCA (FR44) **And** confidence reflects strength of evidence.

3. **Given** weak or conflicting signals, **When** generating hypothesis, **Then** confidence is appropriately low **And** the hypothesis explicitly states uncertainty **And** additional data needs are identified.

4. **Given** a known issue pattern from KB, **When** generating hypothesis, **Then** the KB match boosts confidence **And** the prior incident is cited as supporting evidence.

## Tasks / Subtasks

- [x] Task 1: Create RCAHypothesisStep scaffold (AC: 1, 2)
  - [x] 1.1 Create `steps/rca_hypothesis.py` with `RCAHypothesisStep` implementing `InvestigationStep`
  - [x] 1.2 Accept `llm_client`, `context`, `status_updater` via constructor (same pattern as `CustomerImpactStep`)
  - [x] 1.3 Define `name = "RCA Hypothesis Generation"`
  - [x] 1.4 In `execute()`: extract prior step data from `context` pipeline metadata (see Dev Notes)

- [x] Task 2: Pipeline metadata extraction (AC: 1, 4)
  - [x] 2.1 Extract impact assessment data: `customer_impacting`, `reasoning`
  - [x] 2.2 Extract KB query data: `prior_research_summary`, `relevant_matches`, `recommended_resolution`, `confidence_boost`, `exact_match_found`
  - [x] 2.3 Extract signal correlation data: `hypotheses`, `signal_summary`, `service_dependency_chain`, `layers_queried`, `signals_gathered`
  - [x] 2.4 Handle missing metadata gracefully — any prior step may have failed or been skipped

- [x] Task 3: LLM RCA synthesis (AC: 1, 2, 3, 4)
  - [x] 3.1 Build system prompt for deep root-cause analysis synthesis
  - [x] 3.2 Build user prompt with all extracted evidence: impact, KB findings, correlated signals, prior hypotheses
  - [x] 3.3 Call `complete_sync()` with **no explicit model** (use default, which is the investigation-tier model; FR44 tiered model selection is Story 3.9)
  - [x] 3.4 Parse LLM response: `root_cause_hypothesis`, `confidence_level`, `confidence_percentage`, `supporting_evidence`, `alternative_hypotheses`, `additional_data_needs`
  - [x] 3.5 On LLM failure → fallback: promote best signal correlation hypothesis or return "insufficient data"

- [x] Task 4: Confidence quantification (AC: 1, 3, 4)
  - [x] 4.1 Normalize `confidence_level`: "high"/"medium"/"low" (case-insensitive, default to "low")
  - [x] 4.2 Normalize `confidence_percentage`: clamp to 0-100 integer range, default to `None` if not parseable
  - [x] 4.3 Validate band alignment: high >80%, medium 50-80%, low <50% — override level if percentage contradicts
  - [x] 4.4 KB match boost: if `confidence_boost` from KB step is "high" and `exact_match_found`, note in supporting evidence

- [x] Task 5: Alternative hypotheses and uncertainty (AC: 3)
  - [x] 5.1 When `confidence_level` < "high": require `alternative_hypotheses` list (at least one)
  - [x] 5.2 When `confidence_level` == "low": require `additional_data_needs` list (what else to investigate)
  - [x] 5.3 On LLM returning empty alternatives when confidence < high: populate from signal correlation hypotheses as fallback

- [x] Task 6: Register step in agent pipeline (AC: all)
  - [x] 6.1 Add `RCAHypothesisStep` to `_build_steps()` in `agent.py` after `SignalCorrelationStep` (lazy import)
  - [x] 6.2 Pass `llm_client`, `context`, `status_updater`
  - [x] 6.3 Status updater reports "Generating root cause hypothesis"

- [x] Task 7: Tests (AC: all)
  - [x] 7.1 Create `tests/test_rca_hypothesis.py` with `_make_step()` helper
  - [x] 7.2 Test hypothesis generated with confidence level and percentage (AC1)
  - [x] 7.3 Test strong evidence → high confidence with percentage >80% (AC2)
  - [x] 7.4 Test weak/conflicting signals → low confidence with uncertainty statement and additional data needs (AC3)
  - [x] 7.5 Test KB exact match boosts confidence and cites prior incident (AC4)
  - [x] 7.6 Test KB confidence_boost "medium" with relevant matches
  - [x] 7.7 Test all prior step data missing → graceful handling with "insufficient data" summary
  - [x] 7.8 Test partial prior step data (e.g., impact available, KB unavailable, signals available)
  - [x] 7.9 Test LLM failure → fallback promotes signal correlation hypothesis
  - [x] 7.10 Test LLM malformed JSON → graceful fallback
  - [x] 7.11 Test confidence band validation (percentage 90 but level "low" → corrected to "high")
  - [x] 7.12 Test alternative hypotheses present when confidence < high
  - [x] 7.13 Test additional_data_needs present when confidence is low
  - [x] 7.14 Test StepResult data includes all expected schema keys (consistent shape)
  - [x] 7.15 Test step name and status update message

## Dev Notes

### Step Architecture — Accessing Pipeline Metadata

This step **does not need source clients or KB client**. It synthesizes data already gathered by prior steps. The agent pipeline (`_run_steps()` in `agent.py`) merges each step's `StepResult.data` into `InvestigationResult.metadata`. However, steps don't have direct access to prior step results — the metadata is only merged after all steps run.

**Solution**: The `InvestigationContext` needs to carry pipeline metadata forward. Looking at the current agent code, `_run_steps()` collects metadata sequentially. To pass data between steps, add a `pipeline_metadata: dict` field to `InvestigationContext`, and update `_run_steps()` to feed accumulated metadata into context before each step:

```python
# In agent.py _run_steps() — MODIFY the step loop:
for step in self.steps:
    self.context.pipeline_metadata = dict(metadata)  # snapshot of prior steps
    result = step.execute()
    metadata.update(result.data)
```

Since `InvestigationContext` is a frozen dataclass, use `object.__setattr__` or change to a non-frozen dataclass. **Preferred**: add a mutable `pipeline_metadata: dict[str, Any]` field with `field(default_factory=dict)` and remove `frozen=True` from the dataclass, or keep frozen and use a separate mechanism.

**Check `context.py` before implementing** — if `InvestigationContext` is frozen, the simplest approach is to make `pipeline_metadata` a separate mutable dict that the agent passes to each step, rather than modifying the frozen context. In that case, add it to the step constructor:

```python
class RCAHypothesisStep:
    def __init__(
        self,
        llm_client: LlmClient,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
        pipeline_metadata: dict[str, Any] | None = None,
    ) -> None:
```

Then in `_build_steps()`, store `self._pipeline_metadata = {}` on the agent, pass it to RCAHypothesisStep, and update it in `_run_steps()`:

```python
# In _run_steps():
for step in self.steps:
    result = step.execute()
    metadata.update(result.data)
    self._pipeline_metadata.update(result.data)
```

This avoids modifying the frozen context or the `InvestigationStep` protocol.

### Pipeline Metadata Available from Prior Steps

**From `CustomerImpactStep` (Story 3.3):**
```python
{
    "customer_impacting": True | False | "unknown",
    "reasoning": "brief explanation",
}
```

**From `KBQueryStep` (Story 3.4):**
```python
{
    "kb_available": bool,
    "prior_investigations_count": int,
    "prior_knowledge_count": int,
    "exact_match_found": bool,
    "exact_match_id": str | absent,       # only when exact_match_found
    "prior_research_summary": str,
    "relevant_matches": list[str],
    "recommended_resolution": str | None,
    "confidence_boost": "high" | "medium" | None,
}
```

**From `SignalCorrelationStep` (Story 3.5):**
```python
{
    "sources_available": {"prometheus": bool, "loki": bool},
    "layers_queried": list[str],
    "signals_gathered": int,
    "signal_summary": str,
    "hypotheses": [
        {
            "description": str,
            "causal_chain": str,
            "confidence": "high" | "medium" | "low" | None,
            "supporting_signals": list[str],
            "originating_layer": str,
        }
    ],
    "service_dependency_chain": list[str] | None,
    "correlation_attempted": bool,
}
```

### LLM Prompt Design

**System Prompt** — instruct deep RCA synthesis:

```python
_RCA_SYSTEM_PROMPT = """\
You are a senior SRE performing deep root-cause analysis. Synthesize ALL \
available evidence — customer impact, prior incidents from the knowledge base, \
and correlated signals — into a definitive root cause hypothesis.

Respond with ONLY a JSON object:
{"root_cause_hypothesis": "clear description of the root cause", \
"confidence_level": "high"|"medium"|"low", \
"confidence_percentage": 85, \
"supporting_evidence": ["evidence item 1", "evidence item 2"], \
"alternative_hypotheses": [{"description": "alt hypothesis", "confidence_percentage": 30}], \
"additional_data_needs": ["what else would help if uncertain"], \
"kb_citation": "prior incident ID if applicable or null"}

Rules:
- high confidence (>80%): Strong signal correlation + clear causal chain + optionally confirmed by KB
- medium confidence (50-80%): Partial correlation, plausible but not confirmed
- low confidence (<50%): Weak/conflicting signals, speculative hypothesis
- ALWAYS provide alternative_hypotheses when confidence < high
- ALWAYS provide additional_data_needs when confidence is low
- If a known KB match exists, cite it and boost confidence appropriately
- confidence_percentage must be an integer 0-100"""
```

**User Prompt** — include all evidence:

```python
_RCA_USER_TEMPLATE = """\
Investigation context:
Condition: {condition}
Service: {service}
Severity: {severity}

Customer impact: {impact_summary}

Prior KB research:
{kb_summary}

Signal correlation findings:
{signal_summary}

Signal correlation hypotheses:
{correlation_hypotheses}"""
```

Use `max_tokens=1024` and `temperature=0.0`. Use the **default model** (not screening model — this is deep analysis). Note: FR44 mentions "powerful models for deep RCA" but tiered model selection is Story 3.9. For now, use the default model which is already the investigation-tier model.

### StepResult Data Schema

**Always return these keys** (consistent shape across all code paths):

```python
data = {
    "root_cause_hypothesis": str,           # Main hypothesis description
    "confidence_level": "high" | "medium" | "low",
    "confidence_percentage": int | None,    # 0-100 or None if unparseable
    "supporting_evidence": list[str],       # Evidence items backing the hypothesis
    "alternative_hypotheses": list[dict],   # Each: {description: str, confidence_percentage: int|None}
    "additional_data_needs": list[str],     # Empty list when confident
    "kb_citation": str | None,             # Prior incident ID if applicable
    "synthesis_source": "llm" | "fallback", # How the hypothesis was generated
}
```

### Confidence Band Validation

After parsing the LLM response, validate that `confidence_level` and `confidence_percentage` agree:

```python
def _validate_confidence(level: str, percentage: int | None) -> tuple[str, int | None]:
    if percentage is not None:
        if percentage > 80:
            level = "high"
        elif percentage >= 50:
            level = "medium"
        else:
            level = "low"
    return level, percentage
```

This prevents the LLM from saying "high confidence" with a 30% number.

### Graceful Degradation Paths

| Failure | Step Behavior | `success` | Key Data |
|---------|--------------|-----------|----------|
| No pipeline metadata at all | Generate "insufficient data" hypothesis | `True` | `confidence_level: "low"`, `synthesis_source: "fallback"` |
| Impact only (no KB, no signals) | Minimal hypothesis based on condition + impact | `True` | Low confidence, `additional_data_needs` populated |
| KB exact match found | Promote KB resolution as hypothesis, boost confidence | `True` | `confidence_level: "high"`, `kb_citation` set |
| Signal hypotheses but no KB | Synthesize from signal hypotheses only | `True` | Confidence based on signal evidence strength |
| LLM synthesis fails | Promote best signal correlation hypothesis | `True` | `synthesis_source: "fallback"` |
| LLM returns malformed JSON | Fallback to signal correlation hypothesis | `True` | `synthesis_source: "fallback"` |
| All prior steps failed | "Unable to determine root cause" with low confidence | `True` | `additional_data_needs` lists what was missing |

**Key principle (from NFR-R1):** Always produce a StepResult. Never fail fatally.

### Critical Anti-Patterns to Avoid

1. **Do NOT make the step async.** Agent is synchronous. Use `complete_sync()`.
2. **Do NOT modify agent state directly.** Return `StepResult`; pipeline aggregates.
3. **Do NOT use the screening model.** This is deep RCA analysis — use the default model.
4. **Do NOT re-query sources or KB.** Synthesize from pipeline metadata only — avoid duplicate work.
5. **Do NOT import at module level in `agent.py`.** Use lazy import in `_build_steps()`.
6. **Do NOT hardcode model names.** Story 3.9 handles tiered model selection later.
7. **Do NOT ignore the KB confidence boost.** When `confidence_boost` is "high" and `exact_match_found`, the hypothesis should reflect this.
8. **Do NOT trust LLM confidence values blindly.** Validate percentage against level band and correct mismatches.
9. **Do NOT dump raw pipeline metadata into the LLM prompt.** Format it as readable evidence summaries.
10. **Do NOT skip alternative hypotheses.** AC3 explicitly requires them when confidence < high.

### Previous Story Intelligence

**From Story 3-5 (Cross-Layer Signal Correlation):**
- Two-phase LLM proven again (query gen → analysis); this step is single-phase (synthesis only)
- `_parse_response()` with code fence stripping: reuse the same pattern
- Confidence normalization: case-insensitive, validate against known values
- `TYPE_CHECKING` guard for import cycles (may be needed if importing `SourceClients` — but this step doesn't need it)
- Signal formatting: summarize for LLM, don't dump raw data
- Code review fixes: doubled braces in prompts (use single `{` in regular strings), validate `originating_layer` against known values, include actual metric values not just counts

**From Story 3-4 (KB Query & Prior Research):**
- Independent error handling: wrap each operation separately
- Consistent data schema: always return all expected keys in all code paths
- `_fallback_synthesis()` pattern: when LLM fails, build result from raw data
- Config check before API call: check `embedding_model` configured before using

**From Story 3-3 (Customer Impact Assessment):**
- Screening model for lightweight tasks; default model for deep analysis
- Case-insensitive normalization for LLM string values
- Status updater called before main logic

**From Story 3-2 (Investigator Agent Scaffold):**
- Steps don't currently receive pipeline metadata — this is the first step that needs it
- Modify `_run_steps()` to pass accumulated metadata forward

### Existing Code to Modify

| File | Change |
|------|--------|
| `agent.py` | Add `RCAHypothesisStep` to `_build_steps()` (lazy import, after `SignalCorrelationStep`); modify `_run_steps()` to pass accumulated metadata to steps via constructor or shared dict |

### New Files to Create

| File | Purpose |
|------|---------|
| `beeper_investigator/steps/rca_hypothesis.py` | `RCAHypothesisStep` implementation |
| `tests/test_rca_hypothesis.py` | Unit tests for RCA hypothesis step |

### Testing Standards

- Mock `LlmClient.complete_sync()` — do NOT make real LLM calls
- Use `_make_step()` helper with configurable pipeline metadata (established pattern)
- Test all graceful degradation paths (see table above)
- Test consistent data schema across all code paths
- Test confidence band validation independently
- Verify LLM prompt includes investigation context and prior evidence
- Verify alternative hypotheses and additional_data_needs present when confidence < high/low

### Project Structure Notes

```
investigator/beeper_investigator/
├── steps/
│   ├── __init__.py              # No changes (InvestigationStep protocol, StepResult)
│   ├── impact_assessment.py     # No changes (prior step — metadata source)
│   ├── kb_query.py              # No changes (prior step — metadata source)
│   ├── signal_correlation.py    # No changes (prior step — metadata source)
│   └── rca_hypothesis.py        # NEW: RCAHypothesisStep
├── agent.py                     # MODIFY: add RCAHypothesisStep to _build_steps(), pass pipeline metadata
├── context.py                   # MAYBE MODIFY: see pipeline metadata approach
└── ...

investigator/tests/
├── test_rca_hypothesis.py       # NEW: RCA hypothesis step tests
└── ... (existing test files unchanged)
```

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic-3, Story 3.6] — FR7, FR44, AC1-AC4
- [Source: _bmad-output/planning-artifacts/epics.md#FR-Coverage-Map] — FR7 (RCA hypothesis with confidence), FR44 (powerful models for deep RCA)
- [Source: _bmad-output/implementation-artifacts/3-5-cross-layer-signal-correlation.md] — Signal hypotheses schema, graceful degradation, code review fixes
- [Source: _bmad-output/implementation-artifacts/3-4-kb-query-prior-research.md] — KB data schema, fallback synthesis, confidence boost
- [Source: _bmad-output/implementation-artifacts/3-3-customer-impact-assessment.md] — Impact data schema, screening model pattern
- [Source: investigator/beeper_investigator/agent.py] — `_build_steps()`, `_run_steps()` metadata aggregation, `InvestigationResult`
- [Source: investigator/beeper_investigator/steps/__init__.py] — `InvestigationStep` protocol, `StepResult`
- [Source: investigator/beeper_investigator/context.py] — `InvestigationContext` fields (frozen dataclass)
- [Source: investigator/beeper_investigator/llm/client.py] — `complete_sync()` with optional `model` parameter, `screening_model` property

## Senior Developer Review (AI)

**Review Date:** 2026-03-02
**Review Outcome:** Approve (after fixes applied)
**Reviewer:** Claude Opus 4.6

### Action Items

- [x] **[HIGH]** Fix `_fallback_alternatives` bug: incorrectly skipped first signal hypothesis in LLM success path (rca_hypothesis.py:466)
- [x] **[MEDIUM]** Fix 17 ruff E501 lint violations across rca_hypothesis.py and test_rca_hypothesis.py
- [x] **[MEDIUM]** Fix `has_signals` check to also consider `hypotheses` list presence (rca_hypothesis.py:128)
- [x] **[MEDIUM]** Handle LLM returning string `"null"` for `kb_citation` (rca_hypothesis.py:299)
- [x] **[LOW]** Add documentation comment for shared mutable `_pipeline_metadata` dict (agent.py:69)
- **[LOW]** `_CODE_FENCE_RE` and `_parse_response` duplicated with signal_correlation.py — defer to future cleanup
- **[LOW]** Pre-existing I001 import sort in agent.py module-level imports — not introduced by this story

### Review Notes

- All 4 ACs verified as fully implemented
- All 33 subtasks verified against actual code — legitimately complete
- Git File List matches story File List exactly (0 discrepancies)
- Graceful degradation paths comprehensively tested
- 3 new regression tests added for the fixed bugs
- Final state: 38 tests passing, ruff clean, 0 regressions

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- All 38 RCA hypothesis tests pass (0 failures) — 35 original + 3 review-fix tests
- Full regression suite: 211 passed, 8 failed (pre-existing), 3 skipped — no regressions introduced
- Pre-existing failures: 6 in test_llm_client.py (missing pytest-asyncio), 2 in test_kb_client.py (qdrant-client API changes)
- Ruff lint: 0 violations on all changed files

### Completion Notes List

- Created `RCAHypothesisStep` in `steps/rca_hypothesis.py` implementing full RCA synthesis pipeline
- Step extracts pipeline metadata from prior steps (CustomerImpact, KBQuery, SignalCorrelation) via shared `_pipeline_metadata` dict
- LLM synthesis uses system+user prompts with formatted evidence; parses JSON response with code fence stripping
- Confidence band validation corrects mismatches between level and percentage (e.g., 90% + "low" → "high")
- KB exact match boost adds supporting evidence and sets kb_citation
- Alternative hypotheses enforced when confidence < high; additional_data_needs enforced when low
- Graceful degradation: LLM failure promotes best signal hypothesis; malformed JSON falls back; no data returns "insufficient data"
- All code paths return consistent StepResult data schema with 8 keys
- Agent pipeline modified: `_pipeline_metadata` dict shared with RCAHypothesisStep; updated in `_run_steps()` after each step
- Registered in `_build_steps()` after `SignalCorrelationStep` with lazy import

### Change Log

- 2026-03-02: Implemented RCA Hypothesis Generation step (Story 3.6) — all 7 tasks complete, 35 tests passing
- 2026-03-02: Code review fixes — 4 HIGH/MEDIUM issues fixed, 3 new tests added, all ruff violations resolved

### File List

- investigator/beeper_investigator/steps/rca_hypothesis.py (NEW)
- investigator/beeper_investigator/agent.py (MODIFIED — added RCAHypothesisStep to _build_steps(), pipeline_metadata passing in _run_steps())
- investigator/tests/test_rca_hypothesis.py (NEW)
