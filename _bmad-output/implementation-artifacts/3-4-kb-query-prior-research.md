# Story 3.4: KB Query & Prior Research

Status: done

## Story

As an Investigator,
I want to query the Knowledge Base for similar past incidents,
so that I can build on prior research and avoid re-investigating known issues.

## Acceptance Criteria

1. **Given** an investigation is in progress, **When** the investigator queries the KB, **Then** semantically similar past investigations are retrieved (FR5) **And** results include: investigation ID, root cause, resolution, confidence.

2. **Given** similar incidents exist in the KB, **When** the investigator analyzes them, **Then** it builds on prior research rather than starting fresh (FR6) **And** references to prior investigations are included in findings.

3. **Given** an exact match is found (same root cause signature), **When** the investigator identifies the match, **Then** confidence level is elevated **And** prior resolution is recommended with high confidence.

4. **Given** the KB is temporarily unavailable, **When** the investigator attempts to query, **Then** the investigation continues without KB context (NFR-R2) **And** a warning is logged that KB was unavailable.

## Tasks / Subtasks

- [x] Task 1: Add embedding support to LlmClient (AC: 1)
  - [x] 1.1 Add `BEEPER_LLM_EMBEDDING_MODEL` env var to `LlmConfig.from_env()` (optional field)
  - [x] 1.2 Add `embedding_model: str | None` field to `LlmConfig` dataclass
  - [x] 1.3 Add `embed_sync(text: str) -> list[float]` method to `LlmClient` using `litellm.embedding()`
  - [x] 1.4 Add tests for embedding config loading and `embed_sync()` method

- [x] Task 2: Implement KBQueryStep — search and retrieval (AC: 1, 3, 4)
  - [x] 2.1 Create `steps/kb_query.py` with `KBQueryStep` implementing `InvestigationStep`
  - [x] 2.2 Build query text from `context.condition`, `context.service`, `context.severity`
  - [x] 2.3 Generate embedding via `llm_client.embed_sync(query_text)`
  - [x] 2.4 Search `investigations` collection (similar past investigations, filtered by service)
  - [x] 2.5 Search `knowledge` collection (runbooks, prior findings, filtered by service)
  - [x] 2.6 Detect exact matches: similarity score above `EXACT_MATCH_THRESHOLD` (0.92)
  - [x] 2.7 Handle embedding model not configured → graceful skip with warning
  - [x] 2.8 Handle KB connection errors → `StepResult(success=False)` with `kb_available: false`

- [x] Task 3: LLM synthesis of KB findings (AC: 2, 3)
  - [x] 3.1 Build structured LLM prompt: system prompt + user prompt with KB results + investigation context
  - [x] 3.2 Parse LLM JSON response for `prior_research_summary`, `relevant_matches`, `recommended_resolution`
  - [x] 3.3 When no KB results → skip synthesis, return "No prior research found"
  - [x] 3.4 When exact match found → include prior resolution with elevated confidence
  - [x] 3.5 Handle LLM synthesis failure → fall back to raw result summaries

- [x] Task 4: Register step and wire into agent (AC: all)
  - [x] 4.1 Add `KBQueryStep` to `_build_steps()` in `agent.py` (after `CustomerImpactStep`, lazy import)
  - [x] 4.2 Pass `kb_client`, `llm_client`, `context`, `status_updater` to constructor
  - [x] 4.3 Status updater reports "Querying knowledge base for prior research"

- [x] Task 5: Tests (AC: all)
  - [x] 5.1 Create `tests/test_kb_query.py` with unit tests for `KBQueryStep`
  - [x] 5.2 Test similar investigations found → references in findings (AC1)
  - [x] 5.3 Test exact match detection → elevated confidence + prior resolution (AC3)
  - [x] 5.4 Test no KB results → "no prior research found" summary (AC1)
  - [x] 5.5 Test KB unavailable → graceful degradation, `kb_available: false` (AC4)
  - [x] 5.6 Test embedding model not configured → graceful skip with warning
  - [x] 5.7 Test embedding generation failure → continues without KB context
  - [x] 5.8 Test LLM synthesis with multiple results (AC2)
  - [x] 5.9 Test LLM synthesis failure → raw results still returned
  - [x] 5.10 Test metadata filtering by service
  - [x] 5.11 Verify step data flows through pipeline to investigation metadata
  - [x] 5.12 Test embedding config env var loading

## Dev Notes

### Embedding Infrastructure (NEW — required for semantic KB search)

No embedding infrastructure exists yet. The current `_persist_result()` uses placeholder `[0.0] * 1536` vectors. This story adds embedding generation via LiteLLM.

**Add to `LlmConfig`:**
```python
@dataclass
class LlmConfig:
    ...existing fields...
    embedding_model: str | None = None  # NEW

# In from_env():
embedding_model = os.environ.get("BEEPER_LLM_EMBEDDING_MODEL") or None
```

**Add to `LlmClient`:**
```python
def embed_sync(self, text: str) -> list[float]:
    """Generate embedding vector for text using LiteLLM.

    Returns:
        Embedding vector (list of floats).

    Raises:
        LlmClientError: If embedding model not configured or call fails.
    """
    if not self.config.embedding_model:
        raise LlmClientError("Embedding model not configured (set BEEPER_LLM_EMBEDDING_MODEL)")

    try:
        response = litellm.embedding(
            model=self.config.embedding_model,
            input=[text],
        )
        return response.data[0]["embedding"]
    except Exception as e:
        raise _handle_litellm_error(e) from e
```

**Do NOT** validate the embedding model against provider prefixes — it may use a different provider than the completion model (e.g., OpenAI embeddings with Anthropic completions).

**Environment variable naming:** `BEEPER_LLM_EMBEDDING_MODEL` follows the same pattern as `BEEPER_LLM_SCREENING_MODEL`. Example values:
- `text-embedding-3-small` (OpenAI, 1536 dims, cheapest)
- `text-embedding-ada-002` (OpenAI, 1536 dims, legacy)
- `ollama/nomic-embed-text` (local Ollama, 768 dims)
- `ollama/mxbai-embed-large` (local Ollama, 1024 dims)

**Note:** The vector dimension MUST match the Qdrant collection configuration (`DEFAULT_VECTOR_DIM = 1536`). If using a non-1536-dim model, the Qdrant upsert/search will fail. Document this constraint but don't enforce it in code (let Qdrant return the error).

### KBQueryStep Architecture

**Step receives these dependencies via constructor:**
- `kb_client: KBClient` — for searching investigations and knowledge collections
- `llm_client: LlmClient` — for embedding generation AND synthesis
- `context: InvestigationContext` — condition, service, severity
- `status_updater: InvestigationStatusUpdater` — progress messages

**Execution flow:**
```
1. Build query text from context
2. Generate embedding (if embedding model configured)
3. Search investigations collection (past similar investigations)
4. Search knowledge collection (runbooks, prior findings)
5. Merge and deduplicate results
6. Check for exact matches (score > EXACT_MATCH_THRESHOLD)
7. If results found → synthesize with LLM
8. Return StepResult with structured data
```

**Query text construction:**
```python
query_text = f"{context.condition} {context.service} {context.severity}"
```

Keep it simple — condition + service + severity provides enough semantic signal for vector search. Do NOT over-engineer the query.

**Search parameters:**
- `limit=5` for each collection (10 total max results)
- Filter by `service=context.service` to scope results
- Use `search_investigations()` for past investigations
- Use `search_knowledge()` for runbooks and KB entries

**Exact match detection:**
```python
EXACT_MATCH_THRESHOLD = 0.92  # Module-level constant

def _check_exact_match(results: list[SearchResult]) -> SearchResult | None:
    """Return highest-scoring result if above threshold, else None."""
    if results and results[0].score >= EXACT_MATCH_THRESHOLD:
        return results[0]
    return None
```

**Step data returned:**
```python
StepResult(
    success=True,
    summary="Found 3 prior investigations for service 'payments'; exact match detected",
    data={
        "kb_available": True,
        "prior_investigations_count": 3,
        "prior_knowledge_count": 2,
        "exact_match_found": True,
        "exact_match_id": "inv-abc-123",
        "prior_research_summary": "...(LLM synthesis)...",
        "recommended_resolution": "...(from exact match or LLM)...",
        "confidence_boost": "high",  # or "medium" or None
        "kb_results": [...]  # Raw results for downstream steps
    },
)
```

### LLM Synthesis Prompt Design

**System prompt:**
```
You are an SRE investigator reviewing prior research from the Knowledge Base.
Given the current investigation context and relevant KB matches, synthesize
what we know from past incidents.

Respond with ONLY a JSON object:
{
  "prior_research_summary": "brief synthesis of what prior research tells us",
  "relevant_matches": ["inv-id-1: brief description", "inv-id-2: brief description"],
  "recommended_resolution": "resolution suggestion based on prior research or null",
  "confidence_boost": "high"|"medium"|null
}

Rules:
- high confidence: Exact or near-exact match found with known resolution
- medium confidence: Similar incidents found with relevant context
- null: No actionable prior research found
```

**User prompt template:**
```
Current investigation:
Condition: {context.condition}
Service: {context.service}
Severity: {context.severity}

KB search results:
{formatted_results}
```

**LLM call parameters:**
- Use the **default model** (not screening) — synthesis requires more reasoning
- `max_tokens=512` — synthesis may be more verbose than screening
- `temperature=0.0` — deterministic

**Response parsing:** Same JSON parsing pattern as `CustomerImpactStep` — strip code fences, `json.loads()`, graceful fallback on parse failure.

### Graceful Degradation Paths

There are multiple failure modes to handle gracefully:

| Failure | Step Behavior | `success` | Key Data |
|---------|--------------|-----------|----------|
| Embedding model not configured | Skip KB search entirely | `True` | `kb_available: false, reason: "embedding_model_not_configured"` |
| Embedding generation fails | Skip KB search | `True` | `kb_available: false, reason: "embedding_failed"` |
| KB connection fails | Continue without KB | `False` | `kb_available: false, reason: "connection_failed"` |
| KB returns empty results | Report no prior research | `True` | `prior_investigations_count: 0` |
| LLM synthesis fails | Return raw result summaries | `True` | Summary from raw results, no LLM synthesis |

**Key principle:** KB unavailability is NEVER fatal. The investigation always continues. Log a warning and move on.

### Existing Code to Modify

| File | Change |
|------|--------|
| `llm/client.py` | Add `embedding_model` to `LlmConfig`; add `BEEPER_LLM_EMBEDDING_MODEL` env var; add `embed_sync()` method |
| `agent.py` | Add `KBQueryStep` to `_build_steps()` (lazy import, after `CustomerImpactStep`) |

### New Files to Create

| File | Purpose |
|------|---------|
| `beeper_investigator/steps/kb_query.py` | `KBQueryStep` implementation |
| `tests/test_kb_query.py` | Unit tests for KB query step |
| `tests/test_llm_embedding.py` | Unit tests for embedding support |

### Critical Anti-Patterns to Avoid

1. **Do NOT make the step async.** Agent is synchronous (Story 3-2 design decision). Use `embed_sync()` and `complete_sync()`.
2. **Do NOT have the step modify agent state directly.** Return `StepResult`; pipeline aggregates.
3. **Do NOT abort investigation if KB is unavailable.** This is a screening/enrichment step — default to "no prior research" and continue.
4. **Do NOT import `KBQueryStep` at module level in `agent.py`.** Use lazy import in `_build_steps()`.
5. **Do NOT validate embedding dimension in code.** Let Qdrant return the error if dimensions mismatch.
6. **Do NOT create a second `LlmClient` for embeddings.** Use the existing client with `embed_sync()`.
7. **Do NOT over-engineer the query.** `condition + service + severity` is sufficient semantic signal.
8. **Do NOT use the screening model for synthesis.** Synthesis requires more reasoning — use the default model.
9. **Do NOT update the `phase` field on Investigation CR.** Controller owns that lifecycle.
10. **Do NOT implement local write buffering.** That's a Story 3.8 (Documentation) concern. This story only reads from KB.

### Previous Story Intelligence

**From Story 3-3 (Customer Impact Assessment):**
- Step pattern established: `InvestigationStep` protocol with `name: str` + `execute() -> StepResult`
- Dependencies via constructor injection: `llm_client`, `context`, `status_updater`
- JSON parsing: strip markdown code fences, `json.loads()`, graceful fallback to defaults
- Case-insensitive normalization for string values from LLM
- Non-fatal step failures: log warning, continue pipeline
- LLM call pattern: system prompt + user prompt, `complete_sync()`, `temperature=0.0`
- Metadata collision guard in `_persist_result()`: step data keys must not collide with reserved payload keys (`investigation_id`, `service`, `condition`, `severity`, `status`, `summary`, `findings`, `created_at`)
- Model override: `complete_sync(model=...)` for per-call model selection
- Screening model property: `llm_client.screening_model` for lightweight calls

**From Story 3-2 (Investigator Agent Scaffold):**
- Agent lifecycle: `_initialize()` → `_run_steps()` → `_finalize()`. Do NOT modify `_initialize` or `_finalize`.
- `_persist_result()` returns `bool`; `_finalize()` appends WARNING on failure.
- `SourceClients` fields are nullable; `InvestigationContext` is frozen.
- K8s status updater writes only `message` field.
- `PrometheusClient`/`LokiClient` constructors take `base_url` kwarg.
- `test_connection()` on LlmClient is async but called synchronously — known pre-existing issue, don't fix here.

**From Story 3-3 Code Review:**
- `screening_model` property fallback must use `get_litellm_model()` for Azure/Ollama prefix.
- `_RESERVED_KEYS` guard prevents metadata collision in Qdrant payload.
- Case-insensitive string normalization with `.lower()`.
- Silent failures are a recurring pattern — ensure all failures are logged clearly.

### KB Client Method Signatures

The existing `KBClient` (from `kb/client.py`) provides:

```python
def search_knowledge(
    self,
    query_vector: list[float],
    limit: int = 10,
    entry_type: Optional[str] = None,  # "runbook", "investigation", "correction"
    service: Optional[str] = None,
) -> list[SearchResult]:

def search_investigations(
    self,
    query_vector: list[float],
    limit: int = 10,
    status: Optional[str] = None,  # "active", "resolved", "stale"
    service: Optional[str] = None,
) -> list[SearchResult]:
```

`SearchResult` dataclass: `id: str`, `score: float`, `payload: dict`

Both methods use `client.query_points()` with Qdrant `Filter` and `FieldCondition` for metadata filtering. Vector dimension must be 1536 (`DEFAULT_VECTOR_DIM`).

### Project Structure Notes

```
investigator/beeper_investigator/
├── __init__.py
├── main.py               # Entry point — no changes needed
├── agent.py              # MODIFY: add KBQueryStep to _build_steps()
├── context.py            # No changes
├── steps/
│   ├── __init__.py       # No changes (InvestigationStep protocol, StepResult)
│   ├── impact_assessment.py  # No changes (reference for step pattern)
│   └── kb_query.py       # NEW: KBQueryStep
├── llm/
│   ├── __init__.py
│   └── client.py         # MODIFY: embedding_model config, embed_sync()
├── kb/
│   ├── __init__.py
│   ├── client.py         # No changes (search methods already exist)
│   └── schemas.py        # No changes (SearchResult already defined)
├── k8s/
│   ├── __init__.py
│   └── status.py         # No changes
└── sources/
    ├── __init__.py
    ├── prometheus.py      # No changes
    └── loki.py            # No changes

investigator/tests/
├── test_agent.py              # No changes (agent.steps = [] isolates lifecycle tests)
├── test_kb_query.py           # NEW: KB query step tests
├── test_llm_embedding.py      # NEW: Embedding support tests
├── test_llm_screening.py      # No changes
├── test_impact_assessment.py  # No changes
├── test_step_pipeline.py      # No changes
└── ... (other test files unchanged)
```

### Testing Standards

- Mock `LlmClient.embed_sync()` — do NOT make real embedding API calls
- Mock `LlmClient.complete_sync()` — do NOT make real LLM calls
- Mock `KBClient.search_knowledge()` and `search_investigations()` — do NOT connect to real Qdrant
- Use `_make_step()` helper pattern (established in `test_impact_assessment.py`)
- Test all graceful degradation paths (embedding not configured, embedding fails, KB down, empty results, LLM synthesis fails)
- Test exact match detection with score above and below threshold
- Test structured data flows: `StepResult.data` → `InvestigationResult.metadata`
- Verify step data keys don't collide with reserved payload keys

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic-3, Story 3.4] — FR5, FR6, NFR-R2, acceptance criteria
- [Source: _bmad-output/planning-artifacts/architecture.md#Knowledge-Base] — Qdrant collections, vector search, data model
- [Source: _bmad-output/planning-artifacts/architecture.md#LLM-Integration] — LiteLLM, tiered model routing
- [Source: _bmad-output/planning-artifacts/architecture.md#Investigation-State-Machine] — Investigation lifecycle
- [Source: _bmad-output/implementation-artifacts/3-3-customer-impact-assessment.md] — Step pattern, LLM prompts, code review learnings
- [Source: _bmad-output/implementation-artifacts/3-2-investigator-agent-scaffold.md] — Agent lifecycle, design decisions
- [Source: investigator/beeper_investigator/kb/client.py] — `search_knowledge()`, `search_investigations()` signatures
- [Source: investigator/beeper_investigator/kb/schemas.py] — `SearchResult`, `InvestigationEntry`, `KnowledgeEntry`
- [Source: investigator/beeper_investigator/llm/client.py] — `LlmClient`, `LlmConfig`, `complete_sync()`, `embed_sync()` (to add)
- [Source: investigator/beeper_investigator/steps/__init__.py] — `InvestigationStep` protocol, `StepResult`
- [Source: investigator/beeper_investigator/steps/impact_assessment.py] — Reference step implementation
- [Source: investigator/beeper_investigator/agent.py] — `_build_steps()`, `_run_steps()`, `_persist_result()`

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

N/A — all tests passed on first run, no debugging required.

### Completion Notes List

- **Task 1:** Added `embedding_model: str | None = None` to `LlmConfig` dataclass, `BEEPER_LLM_EMBEDDING_MODEL` env var reading in `from_env()`, and `embed_sync()` method on `LlmClient` using `litellm.embedding()`. Raises `LlmClientError` when model not configured or API call fails. Re-raises `LlmClientError` without double-wrapping via `_handle_litellm_error`.
- **Task 2:** Created `KBQueryStep` in `steps/kb_query.py` with full search and retrieval flow. Searches both `investigations` and `knowledge` Qdrant collections filtered by service. Query text built from `condition + service + severity`. Exact match detection at `EXACT_MATCH_THRESHOLD = 0.92`. Five graceful degradation paths: embedding not configured, embedding fails, KB connection fails, empty results, LLM synthesis fails.
- **Task 3:** LLM synthesis uses structured system+user prompt with `complete_sync(max_tokens=512, temperature=0.0)` on the default model (not screening). JSON response parsing strips markdown code fences. Fallback synthesis builds summaries from raw results when LLM fails or returns malformed JSON. Confidence normalization validates `high`/`medium`/`None` only.
- **Task 4:** Added `KBQueryStep` to `_build_steps()` in `agent.py` after `CustomerImpactStep` with lazy import. Passes `kb_client`, `llm_client`, `context`, `status_updater`.
- **Task 5:** 24 tests in `test_kb_query.py` covering all ACs and degradation paths. 7 tests in `test_llm_embedding.py` covering config loading and `embed_sync()`. Total: 31 new tests, all passing. Full suite: 152 passed, 2 pre-existing failures (unrelated), 3 skipped.

### Change Log

| Change | File(s) | Reason |
|--------|---------|--------|
| Add embedding_model config + embed_sync() | `llm/client.py` | Semantic KB search requires embedding generation (Task 1) |
| Create KBQueryStep | `steps/kb_query.py` | Core step implementation — search, exact match, synthesis (Tasks 2-3) |
| Register KBQueryStep in agent | `agent.py` | Wire step into investigation pipeline (Task 4) |
| Add embedding tests | `tests/test_llm_embedding.py` | Test coverage for embedding config and API (Task 1.4) |
| Add KB query tests | `tests/test_kb_query.py` | Test coverage for all ACs and degradation paths (Task 5) |

### Code Review Record

| ID | Severity | Finding | Resolution |
|----|----------|---------|------------|
| MEDIUM-1 | MEDIUM | Fragile string matching `"not configured" in str(exc)` for embedding error classification | Replaced with explicit `config.embedding_model` check before calling `embed_sync()` |
| MEDIUM-2 | MEDIUM | Single try/except wraps both KB collection searches — partial failure discards surviving results | Wrapped each search independently; both must fail for full failure |
| MEDIUM-3 | MEDIUM | Inconsistent StepResult.data schema between empty-results and found-results code paths | Added `prior_research_summary`, `relevant_matches`, `recommended_resolution`, `confidence_boost` defaults to empty-results path |
| LOW-1 | LOW | Raw KB results not exposed in step data (`kb_results` field from dev notes) | Deferred — downstream steps don't yet consume raw results |
| LOW-2 | LOW | `_check_exact_match` only checks investigation_results, not knowledge | Design decision — runbooks aren't "exact matches" for past incidents |
| LOW-3 | LOW | Inconsistent assertion styles across embedding tests | Accepted — functional, cosmetic only |

### File List

| File | Status | Description |
|------|--------|-------------|
| `investigator/beeper_investigator/llm/client.py` | Modified | Added `embedding_model` to `LlmConfig`, `embed_sync()` to `LlmClient` |
| `investigator/beeper_investigator/steps/kb_query.py` | New | `KBQueryStep` — KB search, exact match detection, LLM synthesis |
| `investigator/beeper_investigator/agent.py` | Modified | Added `KBQueryStep` to `_build_steps()` |
| `investigator/tests/test_kb_query.py` | New | 24 tests for KB query step |
| `investigator/tests/test_llm_embedding.py` | New | 7 tests for embedding support |
