# Story 3.7: Resolution Recommendations

Status: done

## Story

As an Investigator,
I want to recommend resolution actions based on investigation findings,
so that SREs have actionable next steps.

## Acceptance Criteria

1. **Given** a root cause hypothesis is generated, **When** the investigator generates recommendations, **Then** resolution actions are suggested (FR8) **And** each recommendation includes: Action description, Confidence level, Expected outcome, Risk assessment.

2. **Given** a similar past incident was resolved, **When** generating recommendations, **Then** the prior resolution is recommended **And** confidence is elevated based on past success.

3. **Given** the root cause is uncertain (confidence < high), **When** generating recommendations, **Then** safe diagnostic actions are recommended first **And** "gather more information" steps are included.

4. **Given** multiple resolution paths exist, **When** generating recommendations, **Then** options are ranked by confidence and risk **And** trade-offs are explained.

## Tasks / Subtasks

- [x] Task 1: Create ResolutionRecommendationStep scaffold (AC: 1)
  - [x] 1.1 Create `steps/resolution_recommendations.py` with `ResolutionRecommendationStep` implementing `InvestigationStep`
  - [x] 1.2 Accept `llm_client`, `context`, `status_updater`, `pipeline_metadata` via constructor (same pattern as `RCAHypothesisStep`)
  - [x] 1.3 Define `name = "Resolution Recommendations"`
  - [x] 1.4 In `execute()`: call status updater, extract pipeline metadata, call LLM, parse response

- [x] Task 2: Pipeline metadata extraction (AC: 1, 2)
  - [x] 2.1 Extract RCA data: `root_cause_hypothesis`, `confidence_level`, `confidence_percentage`, `supporting_evidence`, `alternative_hypotheses`, `kb_citation`, `synthesis_source`
  - [x] 2.2 Extract KB data: `recommended_resolution`, `confidence_boost`, `exact_match_found`, `exact_match_id`, `prior_research_summary`
  - [x] 2.3 Extract impact data: `customer_impacting`, `reasoning`
  - [x] 2.4 Extract signal data: `signal_summary`, `hypotheses`, `service_dependency_chain`
  - [x] 2.5 Handle missing metadata gracefully — any prior step may have failed or been skipped

- [x] Task 3: LLM recommendation synthesis (AC: 1, 2, 3, 4)
  - [x] 3.1 Build system prompt for resolution recommendation generation
  - [x] 3.2 Build user prompt with all evidence: RCA hypothesis, KB prior resolutions, impact assessment, signal data
  - [x] 3.3 Call `complete_sync()` with **no explicit model** (use default; tiered selection is Story 3.9)
  - [x] 3.4 Parse LLM response: list of recommendations each with `action`, `confidence`, `expected_outcome`, `risk_assessment`, `based_on_prior_incident`
  - [x] 3.5 On LLM failure → fallback: derive recommendations from KB `recommended_resolution` or RCA evidence

- [x] Task 4: Recommendation ranking and risk assessment (AC: 1, 4)
  - [x] 4.1 Normalize `confidence` to "high"/"medium"/"low" (case-insensitive, default "medium")
  - [x] 4.2 Normalize `risk_assessment` to "high"/"medium"/"low" (case-insensitive, default "medium")
  - [x] 4.3 Sort recommendations by confidence descending, then risk ascending (safest high-confidence first)
  - [x] 4.4 Limit to top 5 recommendations maximum (prevent overwhelming SREs)
  - [x] 4.5 Generate `ranking_rationale` explaining why top recommendation is preferred

- [x] Task 5: Confidence-aware recommendation strategy (AC: 2, 3)
  - [x] 5.1 When RCA `confidence_level` == "high": recommend direct resolution actions
  - [x] 5.2 When RCA `confidence_level` < "high": prepend safe diagnostic actions before resolution actions
  - [x] 5.3 When RCA `confidence_level` == "low": add "gather more information" steps as first recommendations
  - [x] 5.4 When KB `exact_match_found` and `recommended_resolution` exists: promote KB resolution and elevate its confidence
  - [x] 5.5 On LLM returning empty recommendations: generate at least one safe diagnostic action as fallback

- [x] Task 6: Register step in agent pipeline (AC: all)
  - [x] 6.1 Add `ResolutionRecommendationStep` to `_build_steps()` in `agent.py` after `RCAHypothesisStep` (lazy import)
  - [x] 6.2 Pass `llm_client`, `context`, `status_updater`, `pipeline_metadata`
  - [x] 6.3 Status updater reports "Generating resolution recommendations"

- [x] Task 7: Tests (AC: all)
  - [x] 7.1 Create `tests/test_resolution_recommendations.py` with `_make_step()` helper and `_full_pipeline_metadata()`
  - [x] 7.2 Test recommendations generated with action, confidence, expected_outcome, risk_assessment (AC1)
  - [x] 7.3 Test prior KB resolution promoted with elevated confidence (AC2)
  - [x] 7.4 Test uncertain RCA → safe diagnostic actions first with "gather more info" (AC3)
  - [x] 7.5 Test multiple recommendations ranked by confidence and risk (AC4)
  - [x] 7.6 Test high RCA confidence → direct resolution actions
  - [x] 7.7 Test all prior step data missing → graceful fallback with generic safe action
  - [x] 7.8 Test partial metadata (RCA only, no KB, no signals)
  - [x] 7.9 Test LLM failure → fallback derives from KB recommended_resolution
  - [x] 7.10 Test LLM malformed JSON → graceful fallback
  - [x] 7.11 Test recommendations capped at 5 maximum
  - [x] 7.12 Test ranking rationale present in result
  - [x] 7.13 Test StepResult data includes all expected schema keys (consistent shape)
  - [x] 7.14 Test step name and status update message
  - [x] 7.15 Test LLM prompt includes RCA hypothesis, KB data, and impact context

## Dev Notes

### Step Architecture — Accessing Pipeline Metadata

This step follows the same pattern as `RCAHypothesisStep` (Story 3.6). It **does not need source clients or KB client**. It synthesizes recommendations from data already gathered by prior steps. The agent's `_pipeline_metadata` dict accumulates results from all prior steps and is passed to the constructor by reference.

```python
class ResolutionRecommendationStep:
    def __init__(
        self,
        llm_client: LlmClient,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
        pipeline_metadata: dict[str, Any] | None = None,
    ) -> None:
```

Then in `_build_steps()`, add after `RCAHypothesisStep` with `pipeline_metadata=self._pipeline_metadata`.

### Pipeline Metadata Available from Prior Steps

**From `RCAHypothesisStep` (Story 3.6) — PRIMARY INPUT:**
```python
{
    "root_cause_hypothesis": str,
    "confidence_level": "high" | "medium" | "low",
    "confidence_percentage": int | None,
    "supporting_evidence": list[str],
    "alternative_hypotheses": list[dict],
    "additional_data_needs": list[str],
    "kb_citation": str | None,
    "synthesis_source": "llm" | "fallback",
}
```

**From `KBQueryStep` (Story 3.4) — KEY FOR AC2:**
```python
{
    "recommended_resolution": str | None,  # ← Primary source for prior resolution
    "confidence_boost": "high" | "medium" | None,
    "exact_match_found": bool,
    "exact_match_id": str | absent,
    "prior_research_summary": str,
    "relevant_matches": list[str],
}
```

**From `CustomerImpactStep` (Story 3.3):**
```python
{
    "customer_impacting": True | False | "unknown",
    "reasoning": str,
}
```

**From `SignalCorrelationStep` (Story 3.5):**
```python
{
    "signal_summary": str,
    "hypotheses": list[dict],
    "service_dependency_chain": list[str] | None,
    "layers_queried": list[str],
    "signals_gathered": int,
}
```

### LLM Prompt Design

**System Prompt** — instruct resolution recommendation generation:

```python
_RESOLUTION_SYSTEM_PROMPT = """\
You are a senior SRE generating actionable resolution recommendations \
based on a completed root-cause analysis. Provide practical, specific \
actions that an on-call engineer can execute.

Respond with ONLY a JSON object:
{"recommendations": [
  {"action": "specific action description",
   "confidence": "high"|"medium"|"low",
   "expected_outcome": "what will happen if action is taken",
   "risk_assessment": "high"|"medium"|"low",
   "based_on_prior_incident": "incident ID or null"}
],
"ranking_rationale": "why recommendations are ordered this way",
"diagnostic_actions": ["safe diagnostic step 1", "step 2"]}

Rules:
- Provide 1-5 recommendations, ordered by confidence (highest first)
- high confidence: proven fix, confirmed by prior incident or strong evidence
- medium confidence: likely effective based on RCA but not confirmed
- low confidence: speculative, may help but needs validation
- risk_assessment: high = could cause outage, medium = minor impact, low = safe
- ALWAYS include diagnostic_actions when root cause confidence < high
- If prior KB resolution exists, include it as the first recommendation
- Each action must be specific and actionable, not generic advice
- based_on_prior_incident must reference actual incident ID or be null"""
```

**User Prompt** — include all evidence:

```python
_RESOLUTION_USER_TEMPLATE = """\
Investigation context:
Condition: {condition}
Service: {service}
Severity: {severity}
Customer impacting: {impact_summary}

Root cause analysis:
Hypothesis: {rca_hypothesis}
Confidence: {rca_confidence} ({rca_percentage}%)
Supporting evidence: {supporting_evidence}

Prior KB research:
{kb_summary}

Signal correlation:
{signal_summary}

Service dependency chain: {dependency_chain}"""
```

Use `max_tokens=1024` and `temperature=0.0`. Use the **default model** (not screening model — this is actionable recommendation generation). Tiered model selection is Story 3.9.

### StepResult Data Schema

**Always return these keys** (consistent shape across all code paths):

```python
data = {
    "recommendations": list[dict],  # Each: {action, confidence, expected_outcome, risk_assessment, based_on_prior_incident}
    "recommendation_count": int,
    "ranking_rationale": str,
    "diagnostic_actions": list[str],  # Safe diagnostic steps (populated when RCA confidence < high)
    "synthesis_source": "llm" | "fallback",
}
```

Each recommendation dict:
```python
{
    "action": str,                           # Specific actionable step
    "confidence": "high" | "medium" | "low", # Confidence in this action
    "expected_outcome": str,                 # What happens if applied
    "risk_assessment": "high" | "medium" | "low",
    "based_on_prior_incident": str | None,   # Prior incident ID or None
}
```

### Confidence-Aware Recommendation Strategy

| RCA Confidence | KB Match | Strategy |
|---------------|----------|----------|
| high + KB exact match | Yes | Promote KB resolution first (highest confidence), add corroborating actions |
| high + no KB match | No | Direct resolution actions based on RCA hypothesis |
| medium | Any | Mix of resolution actions + safe diagnostic steps |
| low | Any | Diagnostic actions first, then speculative resolutions with caveats |
| N/A (fallback) | Yes | Promote KB resolution only |
| N/A (fallback) | No | Generic safe diagnostic actions |

### Graceful Degradation Paths

| Failure | Step Behavior | `success` | Key Data |
|---------|--------------|-----------|----------|
| No pipeline metadata at all | Generate generic safe diagnostic action | `True` | `synthesis_source: "fallback"`, 1 generic recommendation |
| RCA only (no KB, no signals) | Recommendations based on RCA hypothesis alone | `True` | Confidence mirrors RCA confidence |
| KB exact match found | Promote KB resolution as top recommendation | `True` | `based_on_prior_incident` set, confidence elevated |
| Low RCA confidence | Diagnostic actions first, then speculative resolutions | `True` | `diagnostic_actions` populated |
| LLM synthesis fails | Derive from KB `recommended_resolution` or generic fallback | `True` | `synthesis_source: "fallback"` |
| LLM returns malformed JSON | Fallback to KB resolution or generic | `True` | `synthesis_source: "fallback"` |
| All prior steps failed | "Unable to recommend — insufficient data" with safe diagnostic | `True` | `diagnostic_actions` with generic steps |

**Key principle (from NFR-R1):** Always produce a StepResult. Never fail fatally.

### Critical Anti-Patterns to Avoid

1. **Do NOT make the step async.** Agent is synchronous. Use `complete_sync()`.
2. **Do NOT re-query sources or KB.** Synthesize from pipeline metadata only.
3. **Do NOT use the screening model.** This generates actionable recommendations — use default model.
4. **Do NOT hardcode model names.** Story 3.9 handles tiered model selection.
5. **Do NOT import at module level in `agent.py`.** Use lazy import in `_build_steps()`.
6. **Do NOT produce generic recommendations** like "monitor logs" — be specific to the detected issue.
7. **Do NOT recommend high-risk actions when RCA confidence is low** — prioritize safe diagnostics.
8. **Do NOT trust LLM confidence values blindly.** Normalize and validate.
9. **Do NOT dump raw pipeline metadata into the LLM prompt.** Format as readable summaries.
10. **Do NOT produce more than 5 recommendations** — prioritize quality over quantity.
11. **Do NOT forget KB prior resolutions.** When `recommended_resolution` exists, it MUST appear in results.
12. **Do NOT return string `"null"` from LLM** — normalize to Python `None`.

### Previous Story Intelligence

**From Story 3-6 (RCA Hypothesis Generation):**
- Step scaffold pattern proven: constructor with `llm_client`, `context`, `status_updater`, `pipeline_metadata`
- `_parse_response()` with code fence stripping: reuse `_CODE_FENCE_RE` pattern
- Confidence normalization: case-insensitive, validate against known values
- `_fallback_alternatives()` fix: include ALL items from prior data (don't skip index 0)
- `has_signals` check: verify BOTH `signal_summary` and `hypotheses` for presence
- String `"null"` handling: check `kb_citation == "null"` and convert to `None`
- Ruff lint: keep all lines under 100 chars per `pyproject.toml`
- Schema consistency: ALL code paths must return ALL expected keys
- Status updater: call before main logic in `execute()`
- Prompt formatting: section-based, readable summaries (not raw dicts)

**From Story 3-5 (Signal Correlation):**
- Two-phase LLM proven (query gen → analysis); this step is single-phase (synthesis)
- Code fence stripping regex: `re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)`
- Confidence normalization: case-insensitive, validate against known values

**From Story 3-4 (KB Query):**
- `recommended_resolution` field is the primary source for AC2 (prior resolution)
- `exact_match_found` + `confidence_boost` indicate strength of KB match
- Independent error handling: wrap each operation separately

### Existing Code to Modify

| File | Change |
|------|--------|
| `agent.py` | Add `ResolutionRecommendationStep` to `_build_steps()` (lazy import, after `RCAHypothesisStep`); pass `pipeline_metadata` |

### New Files to Create

| File | Purpose |
|------|---------|
| `beeper_investigator/steps/resolution_recommendations.py` | `ResolutionRecommendationStep` implementation |
| `tests/test_resolution_recommendations.py` | Unit tests |

### Testing Standards

- Mock `LlmClient.complete_sync()` — do NOT make real LLM calls
- Use `_make_step()` helper with configurable pipeline metadata (established pattern)
- Test all graceful degradation paths (see table above)
- Test consistent data schema across all code paths
- Test recommendation ranking (confidence desc, risk asc)
- Verify LLM prompt includes RCA hypothesis, KB data, and context
- Verify diagnostic_actions populated when RCA confidence < high
- Verify KB resolution promoted when exact_match_found
- Verify recommendations capped at 5

### Project Structure Notes

```
investigator/beeper_investigator/
├── steps/
│   ├── __init__.py                      # No changes (InvestigationStep protocol, StepResult)
│   ├── impact_assessment.py             # No changes (prior step — metadata source)
│   ├── kb_query.py                      # No changes (prior step — metadata source)
│   ├── signal_correlation.py            # No changes (prior step — metadata source)
│   ├── rca_hypothesis.py               # No changes (prior step — metadata source)
│   └── resolution_recommendations.py    # NEW: ResolutionRecommendationStep
├── agent.py                             # MODIFY: add ResolutionRecommendationStep to _build_steps()
└── ...

investigator/tests/
├── test_resolution_recommendations.py   # NEW: resolution recommendation tests
└── ... (existing test files unchanged)
```

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic-3, Story 3.7] — FR8, AC1-AC4
- [Source: _bmad-output/planning-artifacts/epics.md#FR-Coverage-Map] — FR8 (resolution recommendations)
- [Source: _bmad-output/implementation-artifacts/3-6-rca-hypothesis-generation.md] — Step scaffold pattern, pipeline metadata, code review fixes
- [Source: _bmad-output/implementation-artifacts/3-5-cross-layer-signal-correlation.md] — Signal data schema
- [Source: _bmad-output/implementation-artifacts/3-4-kb-query-prior-research.md] — KB data schema, recommended_resolution
- [Source: _bmad-output/implementation-artifacts/3-3-customer-impact-assessment.md] — Impact data schema
- [Source: investigator/beeper_investigator/agent.py] — `_build_steps()`, `_run_steps()`, pipeline metadata
- [Source: investigator/beeper_investigator/steps/__init__.py] — `InvestigationStep` protocol, `StepResult`
- [Source: investigator/beeper_investigator/steps/rca_hypothesis.py] — Reference implementation for step pattern
- [Source: investigator/beeper_investigator/llm/client.py] — `complete_sync()` API

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- All 7 tasks implemented successfully with 46 passing tests
- Follows established step pattern from RCAHypothesisStep (Story 3-6)
- All code paths return consistent StepResult data schema
- Graceful degradation: no-data fallback, LLM failure fallback, malformed JSON fallback
- KB resolution promoted when exact_match_found
- Diagnostic actions prepended when RCA confidence < high
- Recommendations sorted by confidence desc, risk asc, capped at 5
- 265 total tests pass, ruff clean, mypy clean

### Change Log

- Created `beeper_investigator/steps/resolution_recommendations.py`
- Modified `beeper_investigator/agent.py` (added ResolutionRecommendationStep to _build_steps)
- Created `tests/test_resolution_recommendations.py` (46 tests)

### File List

- `beeper_investigator/steps/resolution_recommendations.py` (NEW)
- `beeper_investigator/agent.py` (MODIFIED)
- `tests/test_resolution_recommendations.py` (NEW)
