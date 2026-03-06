# Story 3.8: Investigation Documentation

Status: done

## Story

As an Investigator,
I want to document my investigation process and findings to the Knowledge Base,
so that the investigation is preserved for future reference and learning.

## Acceptance Criteria

1. **Given** an investigation completes, **When** the investigator documents findings, **Then** a KB entry is created with (FR9): Investigation summary, Detected condition, Correlated signals, Root cause hypothesis, Recommended resolution, Confidence levels throughout.

2. **Given** the KB is available, **When** documentation is written, **Then** the entry is stored in the `knowledge` collection **And** embeddings are generated for semantic search **And** metadata includes: service, timestamp, investigation_id.

3. **Given** the KB is temporarily unavailable, **When** documentation is attempted, **Then** findings are buffered locally (NFR-R2) **And** retry logic persists until KB accepts the write.

4. **Given** the investigation builds on prior research, **When** documenting, **Then** links to referenced prior investigations are included **And** the knowledge graph grows richer.

## Tasks / Subtasks

- [x] Task 1: Create InvestigationDocumentationStep scaffold (AC: 1)
  - [x] 1.1 Create `steps/investigation_documentation.py` with `InvestigationDocumentationStep` implementing `InvestigationStep`
  - [x] 1.2 Accept `llm_client`, `kb_client`, `context`, `status_updater`, `pipeline_metadata` via constructor
  - [x] 1.3 Define `name = "Investigation Documentation"`
  - [x] 1.4 In `execute()`: call status updater, extract pipeline metadata, generate documentation, persist to KB

- [x] Task 2: LLM documentation synthesis (AC: 1, 4)
  - [x] 2.1 Build system prompt instructing structured investigation report generation
  - [x] 2.2 Build user prompt with all pipeline evidence: condition, impact, signals, RCA, resolution recommendations
  - [x] 2.3 Include prior investigation references from KB query metadata (`exact_match_id`, `relevant_matches`)
  - [x] 2.4 Call `complete_sync()` with **no explicit model** (default model; tiered selection is Story 3.9)
  - [x] 2.5 Parse LLM response: `title`, `summary`, `root_cause`, `resolution`, `signals_summary`, `confidence_overview`
  - [x] 2.6 On LLM failure: generate documentation from raw pipeline metadata without LLM summarization

- [x] Task 3: Knowledge collection entry creation with embeddings (AC: 2)
  - [x] 3.1 Generate embedding vector via `llm_client.embed_sync()` using the documentation summary text
  - [x] 3.2 Build knowledge entry payload with all required fields (see Dev Notes for schema)
  - [x] 3.3 Upsert to `knowledge` collection using `kb_client.client.upsert(KNOWLEDGE_COLLECTION, [point])`
  - [x] 3.4 On `embed_sync()` failure: use placeholder zeros `[0.0] * 1536` with warning log
  - [x] 3.5 On KB upsert failure: trigger local buffering (Task 5)

- [x] Task 4: Prior investigation linking (AC: 4)
  - [x] 4.1 Extract `exact_match_id` and `relevant_matches` from pipeline metadata (from KBQueryStep)
  - [x] 4.2 Extract `kb_citation` from RCA step metadata
  - [x] 4.3 Build `related_investigations` list of unique prior investigation IDs
  - [x] 4.4 Include in knowledge entry payload for knowledge graph enrichment

- [x] Task 5: Local buffering and retry mechanism (AC: 3)
  - [x] 5.1 On KB write failure: serialize knowledge entry payload to JSON file at configurable path
  - [x] 5.2 Default buffer path: `/tmp/beeper-buffer/{investigation_id}.json` (from `BEEPER_BUFFER_DIR` env var or default)
  - [x] 5.3 Implement retry with exponential backoff: 3 attempts (1s, 2s, 4s delays)
  - [x] 5.4 On all retries exhausted: write buffer file, log warning, return StepResult with `buffered: True`
  - [x] 5.5 On successful write after retry: clean up buffer file if it exists

- [x] Task 6: Register step in agent pipeline (AC: all)
  - [x] 6.1 Add `InvestigationDocumentationStep` to `_build_steps()` in `agent.py` after `ResolutionRecommendationStep` (lazy import)
  - [x] 6.2 Pass `llm_client`, `kb_client`, `context`, `status_updater`, `pipeline_metadata`
  - [x] 6.3 Status updater reports "Documenting investigation findings"

- [x] Task 7: Tests (AC: all)
  - [x] 7.1 Create `tests/test_investigation_documentation.py` with `_make_step()` helper and `_full_pipeline_metadata()`
  - [x] 7.2 Test KB entry created with all required fields: summary, condition, signals, RCA, resolution, confidence (AC1)
  - [x] 7.3 Test entry stored in `knowledge` collection with correct payload schema (AC2)
  - [x] 7.4 Test embeddings generated via `embed_sync()` and used in point vector (AC2)
  - [x] 7.5 Test metadata includes service, timestamp, investigation_id (AC2)
  - [x] 7.6 Test KB unavailable triggers local buffering to file (AC3)
  - [x] 7.7 Test retry logic: successful retry cleans up buffer (AC3)
  - [x] 7.8 Test retry exhausted: buffer file persisted with correct content (AC3)
  - [x] 7.9 Test prior investigation links included in entry (AC4)
  - [x] 7.10 Test embedding failure falls back to placeholder zeros
  - [x] 7.11 Test LLM failure: documentation generated from raw metadata
  - [x] 7.12 Test LLM malformed JSON: graceful fallback
  - [x] 7.13 Test all prior step data missing: minimal documentation with condition only
  - [x] 7.14 Test partial metadata (RCA only, no recommendations, no signals)
  - [x] 7.15 Test StepResult data includes all expected schema keys (consistent shape)
  - [x] 7.16 Test step name and status update message
  - [x] 7.17 Test LLM prompt includes all pipeline evidence sections

## Dev Notes

### Step Architecture — This Step is Different

Unlike RCAHypothesisStep and ResolutionRecommendationStep which only synthesize data, this step **writes to the KB**. It needs `kb_client` in addition to the standard step dependencies. This follows the same pattern as `KBQueryStep` (Story 3.4) which also receives `kb_client`.

```python
class InvestigationDocumentationStep:
    name: str = "Investigation Documentation"

    def __init__(
        self,
        llm_client: LlmClient,
        kb_client: KBClient,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
        pipeline_metadata: dict[str, Any] | None = None,
    ) -> None:
```

Then in `_build_steps()`, add after `ResolutionRecommendationStep`:
```python
InvestigationDocumentationStep(
    llm_client=self.llm_client,
    kb_client=self.kb_client,
    context=self.context,
    status_updater=self.status_updater,
    pipeline_metadata=self._pipeline_metadata,
),
```

### Key Distinction: `investigations` vs `knowledge` Collections

The agent already persists to `investigations` collection in `_persist_result()` (operational tracking). This step writes to the **`knowledge` collection** for semantic search and future investigation reference. These serve different purposes:

| Collection | Purpose | Written By | Queried By |
|-----------|---------|-----------|-----------|
| `investigations` | Operational tracking, status | `agent._persist_result()` | `kb_client.search_investigations()` |
| `knowledge` | Semantic search, future learning | **This step** | `kb_client.search_knowledge()` (KBQueryStep) |

Import the collection name: `from beeper_investigator.kb.client import KNOWLEDGE_COLLECTION`

### Pipeline Metadata Available from All Prior Steps

**From `CustomerImpactStep` (Story 3.3):**
```python
{
    "customer_impacting": True | False | "unknown",
    "reasoning": str,
}
```

**From `KBQueryStep` (Story 3.4) — KEY FOR AC4 (prior investigation links):**
```python
{
    "recommended_resolution": str | None,
    "confidence_boost": "high" | "medium" | None,
    "exact_match_found": bool,
    "exact_match_id": str | absent,  # Prior investigation ID
    "prior_research_summary": str,
    "relevant_matches": list[str],   # Prior investigation IDs
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

**From `RCAHypothesisStep` (Story 3.6):**
```python
{
    "root_cause_hypothesis": str,
    "confidence_level": "high" | "medium" | "low",
    "confidence_percentage": int | None,
    "supporting_evidence": list[str],
    "alternative_hypotheses": list[dict],
    "additional_data_needs": list[str],
    "kb_citation": str | None,  # Prior incident reference
    "synthesis_source": "llm" | "fallback",
}
```

**From `ResolutionRecommendationStep` (Story 3.7):**
```python
{
    "recommendations": list[dict],  # Each: {action, confidence, expected_outcome, risk_assessment, based_on_prior_incident}
    "recommendation_count": int,
    "ranking_rationale": str,
    "diagnostic_actions": list[str],
    "synthesis_source": "llm" | "fallback",  # Note: same key as RCA step — last writer wins in pipeline_metadata
}
```

**Note on `synthesis_source` key collision:** Both RCA and Resolution steps write `synthesis_source`. In `_pipeline_metadata`, the Resolution step's value overwrites the RCA step's value. The RCA `synthesis_source` can be accessed from the step's own result data within this step if needed, but in practice the documentation step should record the source of the DOCUMENTATION synthesis, not re-use prior step sources.

### LLM Prompt Design

**System Prompt** — instruct investigation report generation:

```python
_DOC_SYSTEM_PROMPT = """\
You are a senior SRE documenting a completed incident investigation. \
Generate a structured, searchable investigation report that will be \
stored in a knowledge base for future reference.

Respond with ONLY a JSON object:
{"title": "concise investigation title",
 "summary": "comprehensive 2-4 sentence investigation summary",
 "root_cause": "confirmed or suspected root cause description",
 "resolution": "actions taken or recommended",
 "signals_summary": "key signals and their correlation",
 "confidence_overview": "overall confidence assessment",
 "key_findings": ["finding 1", "finding 2"]}

Rules:
- title must be specific and searchable (e.g., not "Investigation Report")
- summary should enable future semantic search matches
- Include specific metrics, error patterns, and service names
- If root cause is uncertain, clearly state the uncertainty level
- resolution should include both immediate and long-term actions
- key_findings should capture the most important discoveries"""
```

**User Prompt** — include all evidence:

```python
_DOC_USER_TEMPLATE = """\
Investigation context:
Investigation ID: {investigation_id}
Condition: {condition}
Service: {service}
Severity: {severity}

Customer impact:
{impact_summary}

Signal correlation:
{signal_summary}

Root cause analysis:
Hypothesis: {rca_hypothesis}
Confidence: {rca_confidence} ({rca_percentage}%)
Supporting evidence: {supporting_evidence}

Resolution recommendations:
{resolution_summary}

Prior research:
{prior_research}

Related investigations: {related_ids}"""
```

Use `max_tokens=1024` and `temperature=0.0`. Use the **default model** (not screening model).

### Knowledge Entry Payload Schema

```python
payload = {
    "entry_id": str,              # UUID for this KB entry
    "entry_type": "investigation", # Fixed type identifier
    "investigation_id": str,       # Links to investigations collection
    "service": str,
    "condition": str,
    "severity": str,
    "created_at": str,             # ISO 8601 UTC timestamp
    "title": str,                  # LLM-generated searchable title
    "summary": str,                # LLM-generated comprehensive summary
    "root_cause": str,             # Root cause description
    "resolution": str,             # Resolution description
    "confidence_level": str,       # Overall confidence (high/medium/low)
    "confidence_percentage": int | None,
    "signals_summary": str,        # Correlated signals summary
    "key_findings": list[str],     # Important discoveries
    "recommendations": list[dict], # Resolution recommendations
    "related_investigations": list[str],  # Prior investigation IDs (AC4)
    "customer_impacting": bool | str,     # Impact assessment
}
```

### Embedding Generation

```python
# Generate embedding from the summary text for semantic search
try:
    embedding = self.llm_client.embed_sync(summary_text)
except Exception:
    logger.warning("Embedding generation failed; using placeholder")
    embedding = [0.0] * 1536  # DEFAULT_VECTOR_DIM

point = PointStruct(
    id=str(uuid.uuid4()),
    vector=embedding,
    payload=payload,
)
```

The `embed_sync()` method is available on `LlmClient` (see `llm/client.py:308-335`). It requires `BEEPER_LLM_EMBEDDING_MODEL` env var to be configured. If not configured, it raises `LlmClientError` — catch this and use placeholder zeros.

### Local Buffering Mechanism (NFR-R2)

```python
import json
import os
import time

_DEFAULT_BUFFER_DIR = "/tmp/beeper-buffer"
_MAX_RETRIES = 3
_RETRY_DELAYS = [1.0, 2.0, 4.0]  # Exponential backoff

def _buffer_to_file(
    self, payload: dict, embedding: list[float]
) -> str:
    """Write failed KB entry to local buffer file."""
    buffer_dir = os.environ.get(
        "BEEPER_BUFFER_DIR", _DEFAULT_BUFFER_DIR
    )
    os.makedirs(buffer_dir, exist_ok=True)
    buffer_path = os.path.join(
        buffer_dir,
        f"{self.context.investigation_id}.json",
    )
    buffer_data = {
        "payload": payload,
        "embedding": embedding,
        "collection": KNOWLEDGE_COLLECTION,
        "buffered_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(buffer_path, "w") as f:
        json.dump(buffer_data, f)
    return buffer_path
```

Retry flow:
1. Attempt KB write
2. On failure: wait `_RETRY_DELAYS[attempt]` seconds, retry
3. After 3 failed attempts: buffer to file, log warning
4. On success after retry: delete buffer file if exists
5. Return StepResult with `buffered: True/False` in data

### StepResult Data Schema

**Always return these keys** (consistent shape across all code paths):

```python
data = {
    "documentation_title": str,     # Investigation title
    "documentation_summary": str,   # Full summary text
    "kb_entry_id": str | None,      # UUID of KB entry (None if buffered)
    "persisted": bool,              # True if written to KB
    "buffered": bool,               # True if written to local file
    "buffer_path": str | None,      # Path to buffer file (if buffered)
    "embedding_generated": bool,    # True if real embedding used
    "related_investigations": list[str],  # Prior investigation IDs
    "synthesis_source": "llm" | "fallback",
}
```

### Prior Investigation Linking (AC4)

Collect related investigation IDs from multiple metadata sources:
```python
related: set[str] = set()

# From KB query step
match_id = self.pipeline_metadata.get("exact_match_id")
if match_id:
    related.add(match_id)

relevant = self.pipeline_metadata.get("relevant_matches", [])
for rid in relevant:
    if isinstance(rid, str) and rid:
        related.add(rid)

# From RCA step
kb_citation = self.pipeline_metadata.get("kb_citation")
if isinstance(kb_citation, str) and kb_citation != "null":
    related.add(kb_citation)

# From resolution step
for rec in self.pipeline_metadata.get("recommendations", []):
    prior = rec.get("based_on_prior_incident")
    if isinstance(prior, str) and prior:
        related.add(prior)
```

### Graceful Degradation Paths

| Failure | Step Behavior | `success` | Key Data |
|---------|--------------|-----------|----------|
| No pipeline metadata | Document condition only, minimal entry | `True` | `synthesis_source: "fallback"` |
| LLM synthesis fails | Generate doc from raw metadata | `True` | `synthesis_source: "fallback"` |
| LLM malformed JSON | Fallback to raw metadata | `True` | `synthesis_source: "fallback"` |
| Embedding fails | Use placeholder zeros, warn | `True` | `embedding_generated: False` |
| KB write fails + retry exhausted | Buffer to file | `True` | `persisted: False, buffered: True` |
| KB write fails + no buffer dir | Log error, continue | `True` | `persisted: False, buffered: False` |
| All prior steps failed | Minimal doc with condition/service only | `True` | Minimal payload |

**Key principle (NFR-R1):** Always produce a StepResult. Never fail fatally.

### Critical Anti-Patterns to Avoid

1. **Do NOT make the step async.** Agent is synchronous. Use `complete_sync()`.
2. **Do NOT write to `investigations` collection.** That's handled by `agent._persist_result()`. Write to `knowledge` only.
3. **Do NOT use the screening model.** Documentation generation requires quality. Use default model.
4. **Do NOT hardcode model names.** Story 3.9 handles tiered model selection.
5. **Do NOT import at module level in `agent.py`.** Use lazy import in `_build_steps()`.
6. **Do NOT skip embedding generation.** AC2 explicitly requires embeddings. Fall back to zeros only on failure.
7. **Do NOT block indefinitely on retry.** Cap at 3 attempts with bounded delays.
8. **Do NOT use `time.sleep()` in tests.** Mock the retry delays.
9. **Do NOT return string `"null"` from LLM.** Normalize to Python `None`.
10. **Do NOT duplicate findings from `_persist_result()`.** This step writes to `knowledge`, not `investigations`.
11. **Do NOT forget prior investigation links.** AC4 requires related investigation IDs in the entry.
12. **Do NOT generate vague titles.** Titles must be specific and searchable for future KB queries.

### Previous Story Intelligence

**From Story 3-7 (Resolution Recommendations):**
- Step scaffold pattern proven: constructor with `llm_client`, `context`, `status_updater`, `pipeline_metadata`
- `_parse_response()` with code fence stripping: reuse `_CODE_FENCE_RE` pattern
- Confidence/level normalization helpers: `_normalize_level()` reusable
- Recommendation data schema: `recommendations` list with `based_on_prior_incident` field (source for AC4 linking)
- Fallback pattern: always produce StepResult(success=True) with consistent data schema
- Test pattern: `_make_step()` helper, `_full_pipeline_metadata()`, mock LLM and status

**From Story 3-6 (RCA Hypothesis Generation):**
- String `"null"` handling: check `== "null"` and convert to `None`
- `has_signals` check: verify BOTH `signal_summary` and `hypotheses` for presence
- Confidence band validation: percentage overrides level (>80%=high, 50-80%=medium, <50%=low)
- Ruff lint: keep all lines under 100 chars per `pyproject.toml`
- Schema consistency: ALL code paths must return ALL expected keys

**From Story 3-4 (KB Query):**
- `KBClient` import and usage pattern for upsert operations
- `KNOWLEDGE_COLLECTION` constant for collection name
- `kb_client.client.upsert()` method signature

### Existing Code to Modify

| File | Change |
|------|--------|
| `agent.py` | Add `InvestigationDocumentationStep` to `_build_steps()` (lazy import, after `ResolutionRecommendationStep`); pass `kb_client` + `pipeline_metadata` |

### New Files to Create

| File | Purpose |
|------|---------|
| `beeper_investigator/steps/investigation_documentation.py` | `InvestigationDocumentationStep` implementation |
| `tests/test_investigation_documentation.py` | Unit tests |

### Testing Standards

- Mock `LlmClient.complete_sync()` AND `LlmClient.embed_sync()` — do NOT make real LLM calls
- Mock `KBClient.client.upsert()` — do NOT make real Qdrant calls
- Mock `time.sleep()` to avoid real delays in retry tests
- Mock file I/O for buffer tests (or use `tmp_path` fixture)
- Use `_make_step()` helper with configurable pipeline metadata (established pattern)
- Test all graceful degradation paths (see table above)
- Test consistent data schema across all code paths
- Verify LLM prompt includes all pipeline evidence sections
- Verify embedding generated from summary text
- Verify related_investigations collected from all metadata sources

### Project Structure Notes

```
investigator/beeper_investigator/
├── steps/
│   ├── __init__.py                        # No changes (InvestigationStep protocol, StepResult)
│   ├── impact_assessment.py               # No changes (prior step — metadata source)
│   ├── kb_query.py                        # No changes (prior step — metadata source)
│   ├── signal_correlation.py              # No changes (prior step — metadata source)
│   ├── rca_hypothesis.py                  # No changes (prior step — metadata source)
│   ├── resolution_recommendations.py      # No changes (prior step — metadata source)
│   └── investigation_documentation.py     # NEW: InvestigationDocumentationStep
├── agent.py                               # MODIFY: add InvestigationDocumentationStep to _build_steps()
├── kb/
│   └── client.py                          # No changes (KNOWLEDGE_COLLECTION imported)
└── ...

investigator/tests/
├── test_investigation_documentation.py    # NEW: documentation step tests
└── ... (existing test files unchanged)
```

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic-3, Story 3.8] — FR9, AC1-AC4
- [Source: _bmad-output/planning-artifacts/epics.md#NFR-R2] — Local buffering on KB unavailability
- [Source: _bmad-output/planning-artifacts/epics.md#NFR-R4] — Investigation durability
- [Source: _bmad-output/planning-artifacts/architecture.md] — Qdrant collections, embedding config, knowledge schema
- [Source: _bmad-output/implementation-artifacts/3-7-resolution-recommendations.md] — Step pattern, pipeline metadata, anti-patterns
- [Source: _bmad-output/implementation-artifacts/3-6-rca-hypothesis-generation.md] — Code review fixes, normalization patterns
- [Source: investigator/beeper_investigator/agent.py] — `_build_steps()`, `_run_steps()`, `_persist_result()`, pipeline metadata
- [Source: investigator/beeper_investigator/steps/__init__.py] — `InvestigationStep` protocol, `StepResult`
- [Source: investigator/beeper_investigator/kb/client.py] — `KNOWLEDGE_COLLECTION`, `KBClient`, `search_knowledge()`
- [Source: investigator/beeper_investigator/llm/client.py] — `complete_sync()`, `embed_sync()` API
- [Source: investigator/beeper_investigator/kb/schemas.py] — Qdrant payload schemas
- [Source: scripts/init-collections.py] — Collection definitions, vector dimensions

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

None

### Completion Notes List

- All 7 tasks (17 test subtasks) implemented and passing
- 52/52 unit tests passing for investigation documentation step (4 added during code review)
- 312/318 full regression suite passing (6 pre-existing async test failures in test_llm_client.py — not introduced by this story)
- Ruff lint clean (auto-fixed one I001 import ordering issue)
- Step writes to `knowledge` collection (distinct from `investigations` collection used by `agent._persist_result()`)
- Graceful degradation verified: LLM failure fallback, embedding failure fallback, KB unavailability with retry + local buffering
- Prior investigation linking collects IDs from 4 metadata sources with deduplication
- StepResult data schema consistent across all code paths (9 keys)
- Code review fixes: removed dead retry delay, added "null" string guard on based_on_prior_incident, added buffer write failure test, added agent pipeline registration tests

### Change Log

- Created `InvestigationDocumentationStep` with LLM synthesis, embedding generation, KB persistence, retry/buffering
- Registered step in agent pipeline after `ResolutionRecommendationStep`
- Created comprehensive test suite covering all acceptance criteria and degradation paths
- Code review: fixed `_RETRY_DELAYS` dead code (3→2 elements), added "null" guard on `based_on_prior_incident`, added 4 tests (buffer write failure, "null" prior incident, pipeline registration x2)

### File List

- `investigator/beeper_investigator/steps/investigation_documentation.py` (NEW)
- `investigator/tests/test_investigation_documentation.py` (NEW)
- `investigator/beeper_investigator/agent.py` (MODIFIED — added InvestigationDocumentationStep to _build_steps())
