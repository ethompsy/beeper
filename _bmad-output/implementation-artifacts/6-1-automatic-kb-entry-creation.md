# Story 6.1: Automatic KB Entry Creation from Resolved Investigations

Status: review

## Story

As the **system**,
I want to create KB entries automatically from resolved investigations,
so that every investigation outcome contributes to Beeper's institutional knowledge without manual effort.

## Acceptance Criteria

1. **Given** an investigation transitions to "resolved" or "verified" status **When** the KB auto-creation process triggers **Then** a KB entry is created with: root cause summary, symptoms, evidence references, resolution steps, and affected service **And** the entry is tagged with `validation_status: "AI-generated"` and linked to the source investigation

2. **Given** a resolved investigation that closely matches an existing KB entry **When** the auto-creation process evaluates similarity **Then** the existing entry is updated/enriched rather than creating a duplicate **And** the update is versioned in the `knowledge_versions` collection

3. **Given** the KB has 10,000+ entries **When** semantic search is performed **Then** results return within 2 seconds (NFR20)

## Tasks / Subtasks

- [x] Task 1: Create `AutoKBCreationService` in `investigator/beeper_investigator/kb/auto_creation.py` (AC: #1, #2, #3)
  - [x]1.1 Create module with imports from existing KB infrastructure: `KBClient`, `KNOWLEDGE_COLLECTION`, `LlmClient`, `PointStruct`, `FieldCondition`, `Filter`, `MatchValue`. Import `KnowledgeEntry` schema.
  - [x]1.2 Create `AutoKBCreationService` class with `__init__(self, kb_client: KBClient, llm_client: LlmClient)`. Stores both clients. Define constants: `SIMILARITY_THRESHOLD = 0.85` (above this = duplicate), `ENRICHMENT_THRESHOLD = 0.70` (above this = candidate for enrichment), `DEFAULT_VECTOR_DIM = 1536`.
  - [x]1.3 Add `create_or_update_from_investigation(self, investigation_data: dict) -> dict` method. This is the main entry point. Flow: (a) Build summary text from investigation_data, (b) Generate embedding via `llm_client.embed_sync(summary_text)`, (c) Search for similar existing KB entries via `kb_client.search_knowledge(embedding, limit=5)`, (d) If best match score >= SIMILARITY_THRESHOLD: call `_enrich_existing_entry()`, (e) Elif best match score >= ENRICHMENT_THRESHOLD: still call `_enrich_existing_entry()` but add new evidence only (don't overwrite), (f) Else: call `_create_new_entry()`. Return dict with `action` ("created"/"enriched"/"skipped"), `entry_id`, `similar_score`.
  - [x]1.4 Add `_build_summary_text(self, data: dict) -> str` private method. Compose from: `data["root_cause"]`, `data["condition"]`, `data["service"]`, `data["signals_summary"]`, `data["resolution"]`. Cap at 1000 chars. Return empty string if data is empty/None.
  - [x]1.5 Add `_create_new_entry(self, data: dict, embedding: list[float]) -> str` private method. Build payload with: `entry_id` (uuid4), `entry_type: "investigation"`, `validation_status: "AI-generated"`, `service`, `condition`, `severity`, `created_at` (ISO 8601 UTC), `title`, `summary` (=`data["documentation_summary"]`), `content` (markdown with root_cause, symptoms, resolution steps), `root_cause`, `resolution`, `signals_summary`, `key_findings`, `recommendations`, `source_investigation_id`, `related_investigations`, `version: 1`. Upsert `PointStruct` to `knowledge` collection. Return entry_id.
  - [x]1.6 Add `_enrich_existing_entry(self, existing_point_id: str, existing_payload: dict, new_data: dict, new_embedding: list[float]) -> str` private method. (a) Read existing payload, (b) Merge new evidence: append new `key_findings`, add new `related_investigations` (deduplicate), update `resolution` if new data has more detail, add `source_investigation_id` to a `contributing_investigations` list, (c) Update `updated_at` to now, increment `version`, (d) Create version snapshot in `knowledge_versions` collection (payload-only, no vector), (e) Upsert updated point with new embedding to `knowledge` collection. Return existing entry_id.
  - [x]1.7 Add `_save_version_snapshot(self, entry_id: str, payload: dict, version: int) -> None` private method. Creates a point in `knowledge_versions` collection with: `version_id` (uuid4), `entry_id`, `version`, `payload` snapshot, `created_at`. Use zero vector `[0.0] * DEFAULT_VECTOR_DIM` since versions are payload-only. Non-fatal: catch exceptions and log warning.
  - [x]1.8 Wrap all external calls in try/except. If Qdrant search fails: skip similarity check and create new entry (safe fallback). If embedding fails: use zero vector but still persist. If Qdrant write fails: use retry pattern (3 attempts, [1.0, 2.0]s delays) then buffer to `/tmp/beeper-buffer/auto-kb-{investigation_id}.json`. Follow `InvestigationDocumentationStep._persist_entry()` pattern exactly.

- [x] Task 2: Modify `InvestigationDocumentationStep` to add `validation_status` (AC: #1)
  - [x]2.1 In `investigator/beeper_investigator/steps/investigation_documentation.py`, update `_build_payload()` method to include `"validation_status": "AI-generated"` in the returned payload dict. Add it after the `"customer_impacting"` field.
  - [x]2.2 Add `"source_investigation_id": self.context.investigation_id` to the payload if not already present (it has `investigation_id` but not explicitly named `source_investigation_id`; add for consistency with AC1).

- [x] Task 3: Integrate `AutoKBCreationService` into the investigation agent pipeline (AC: #1, #2)
  - [x]3.1 In `investigator/beeper_investigator/agent.py`, import `AutoKBCreationService` from `beeper_investigator.kb.auto_creation`.
  - [x]3.2 In `_finalize()` method, AFTER `_persist_result(result)` succeeds and BEFORE `set_completed()`, add auto KB creation call: instantiate `AutoKBCreationService(self.kb_client, self.llm_client)`, build `investigation_data` dict from `result` (success, summary, findings, metadata) and `self.context` (investigation_id, service, condition, severity) and `self.pipeline_metadata` (root_cause_hypothesis, signals_summary, recommendations, etc.), call `service.create_or_update_from_investigation(investigation_data)`. Only call when `result.success` is True.
  - [x]3.3 Wrap the auto KB creation in try/except — if it fails, log warning but do NOT fail the investigation. The investigation itself succeeded; KB entry creation is non-fatal. Add the auto-kb result to `result.metadata["auto_kb_creation"]` for debugging.

- [x] Task 4: Update `KnowledgeEntry` schema to include `validation_status` (AC: #1)
  - [x]4.1 In `investigator/beeper_investigator/kb/schemas.py`, add `validation_status: Optional[str] = Field(None, description="Validation status: AI-generated, human-confirmed, proven, corrected")` to `KnowledgeEntry` model. Add after `version` field.
  - [x]4.2 Add `source_investigation_id: Optional[str] = Field(None, description="Source investigation that created this entry")` to `KnowledgeEntry` model.
  - [x]4.3 Add `contributing_investigations: list[str] = Field(default_factory=list, description="All investigations that contributed to this entry")` to `KnowledgeEntry` model.

- [x] Task 5: Write unit tests for `AutoKBCreationService` in `investigator/tests/test_auto_kb_creation.py` (AC: #1, #2, #3)
  - [x]5.1 `TestCreateOrUpdateFromInvestigation` — mock KBClient and LlmClient. Test with resolved investigation data: verify KB entry created with all required fields (root_cause, symptoms, evidence, resolution, service, validation_status="AI-generated", source_investigation_id). Verify embedding generated from summary text.
  - [x]5.2 `TestSimilarityCheckAndEnrichment` — mock `kb_client.search_knowledge()` to return a similar existing entry with score=0.90 (above SIMILARITY_THRESHOLD). Verify: existing entry is enriched (not new entry created), version snapshot saved to knowledge_versions, `contributing_investigations` updated with new investigation ID.
  - [x]5.3 `TestNoSimilarEntry` — mock search returning empty results or low scores (< 0.70). Verify: new KB entry created, validation_status="AI-generated", source_investigation_id set.
  - [x]5.4 `TestEnrichmentThreshold` — mock search returning score between 0.70-0.85. Verify: existing entry enriched with new evidence appended, not overwritten.
  - [x]5.5 `TestBuildSummaryText` — test summary text composition from various data dicts. Test: full data → comprehensive summary. Empty data → empty string. Partial data → includes available fields. Verify 1000-char cap.
  - [x]5.6 `TestVersionSnapshot` — mock Qdrant. Verify: version snapshot created with correct payload, version number incremented, entry_id matches.
  - [x]5.7 `TestGracefulDegradation` — test: embedding failure → zero vector used but entry still created. Qdrant search failure → skip similarity, create new entry. Qdrant write failure → retry 3 times then buffer. Version snapshot failure → log warning but entry creation succeeds.
  - [x]5.8 `TestSkipOnFailedInvestigation` — verify that auto KB creation is NOT triggered when investigation result.success is False (only resolved/verified investigations create KB entries).

- [x] Task 6: Write integration tests for agent pipeline hook in `investigator/tests/test_agent.py` (AC: #1, #2)
  - [x]6.1 `TestAutoKBCreationInFinalize` — mock the agent with a successful investigation result. Verify `AutoKBCreationService.create_or_update_from_investigation()` is called during `_finalize()`. Verify investigation_data dict contains all expected fields from result, context, and pipeline_metadata.
  - [x]6.2 `TestAutoKBCreationFailureNonFatal` — mock `AutoKBCreationService` to raise exception. Verify investigation still completes successfully (set_completed called, not set_failed). Verify warning logged.
  - [x]6.3 `TestAutoKBCreationSkippedOnFailure` — mock agent with failed investigation (result.success=False). Verify `AutoKBCreationService` is NOT called.

- [x] Task 7: Update existing `InvestigationDocumentationStep` tests (AC: #1)
  - [x]7.1 In `investigator/tests/test_investigation_documentation.py`, update existing tests to verify `validation_status: "AI-generated"` is present in the KB entry payload.
  - [x]7.2 Verify `source_investigation_id` is present in the payload and matches context.investigation_id.

- [x] Task 8: Run full test suite across all components (AC: all)
  - [x]8.1 Run investigator tests: `cd investigator && poetry run python -m pytest` — all pass (existing + new)
  - [x]8.2 Run investigator linting: `cd investigator && poetry run ruff check .` — no issues
  - [x]8.3 Run investigator type checking: `cd investigator && poetry run mypy .` — no issues
  - [x]8.4 Run UI tests: `cd ui && poetry run python -m pytest` — all pass (no regressions)
  - [x]8.5 Run operator tests: `cd operator && cargo test` — all pass (no regressions)
  - [x]8.6 No regressions found

## Dev Notes

### Architecture Patterns (CRITICAL — must follow)

**Auto KB creation is a POST-PIPELINE service in the investigator layer:**
- Architecture maps FR38 to: `investigator/steps/investigation_documentation.py`
- Story 6-1 enhances this by adding duplicate prevention and validation_status
- The service runs in `agent._finalize()` after `_persist_result()` succeeds
- Non-fatal: if auto KB creation fails, investigation still succeeds

**Duplicate Prevention via Semantic Similarity (AC #2 — CRITICAL):**
```
Given: resolved investigation with root_cause="OOMKilled pod in payment-service"
Step 1: Generate embedding from investigation summary
Step 2: Search knowledge collection for similar entries
Step 3: If score >= 0.85 (SIMILARITY_THRESHOLD):
           → Enrich existing entry (don't create duplicate)
           → Version the update in knowledge_versions
        Elif score >= 0.70 (ENRICHMENT_THRESHOLD):
           → Enrich existing entry with new evidence only
           → Version the update
        Else:
           → Create new KB entry
```

**Validation Status Tagging (AC #1 — CRITICAL):**
All auto-created KB entries MUST include `validation_status: "AI-generated"`. This field is consumed by:
- Story 5-6: `KBSurfacingService._compute_validation_weight()` maps validation_status to ranking weights
- Story 6-4 (future): KB entry validation weighting system
- Story 6-5 (future): KB entry review/edit interface showing validation badges

**Versioning Pattern (AC #2):**
```python
# When enriching an existing entry:
# 1. Save snapshot of CURRENT state to knowledge_versions
knowledge_versions.upsert(PointStruct(
    id=str(uuid4()),
    vector=[0.0] * 1536,  # payload-only, no semantic search
    payload={
        "version_id": str(uuid4()),
        "entry_id": original_entry_id,
        "version": current_version,
        "payload": current_payload_snapshot,
        "created_at": now.isoformat(),
    }
))
# 2. Update the entry in knowledge collection with incremented version
```

**Investigation Data Flow into KB Entry:**
```python
investigation_data = {
    # From InvestigationContext
    "investigation_id": context.investigation_id,
    "service": context.service,
    "condition": context.condition,
    "severity": context.severity,
    # From pipeline_metadata (populated by all 13 steps)
    "root_cause_hypothesis": pipeline_metadata.get("root_cause_hypothesis", ""),
    "confidence_level": pipeline_metadata.get("confidence_level", ""),
    "confidence_percentage": pipeline_metadata.get("confidence_percentage"),
    "signals_summary": pipeline_metadata.get("signal_summary", ""),
    "supporting_evidence": pipeline_metadata.get("supporting_evidence", []),
    "recommendations": pipeline_metadata.get("recommendations", []),
    "prior_research_summary": pipeline_metadata.get("prior_research_summary", ""),
    "relevant_matches": pipeline_metadata.get("relevant_matches", []),
    "customer_impacting": pipeline_metadata.get("customer_impacting"),
    # From InvestigationResult
    "summary": result.summary,
    "findings": result.findings,
    # From InvestigationDocumentationStep output (step 6)
    "documentation_title": pipeline_metadata.get("documentation_title", ""),
    "documentation_summary": pipeline_metadata.get("documentation_summary", ""),
    "kb_entry_id": pipeline_metadata.get("kb_entry_id"),  # step 6 entry if persisted
}
```

**Retry and Buffer Pattern (follow InvestigationDocumentationStep exactly):**
- 3 attempts with delays [1.0, 2.0] seconds
- On exhaustion: buffer to `/tmp/beeper-buffer/auto-kb-{investigation_id}.json`
- Buffer format: `{"payload": {...}, "embedding": [...], "collection": "knowledge", "buffered_at": "..."}`
- Buffer cleanup on successful write

### Existing Code to Reuse (DO NOT RECREATE)

| Component | Location | What to Reuse |
|-----------|----------|---------------|
| KBClient | `investigator/beeper_investigator/kb/client.py:33` | `search_knowledge()`, `client.upsert()`, `health_check()` |
| KBClient constants | `investigator/beeper_investigator/kb/client.py:24` | `KNOWLEDGE_COLLECTION`, `INVESTIGATIONS_COLLECTION` |
| KnowledgeEntry schema | `investigator/beeper_investigator/kb/schemas.py:48` | Pydantic model for KB entries |
| LlmClient | `investigator/beeper_investigator/llm/client.py` | `embed_sync()` for generating embeddings |
| InvestigationDocStep | `investigator/beeper_investigator/steps/investigation_documentation.py:96` | Payload build pattern, retry/buffer pattern, LLM doc generation pattern |
| ProvenFixAccumulator | `investigator/beeper_investigator/remediation/proven_fix_accumulator.py` | Post-resolution KB creation pattern |
| Agent finalize | `investigator/beeper_investigator/agent.py:337` | `_finalize()` hook point |
| StepResult | `investigator/beeper_investigator/steps/__init__.py` | Step return type |

### Anti-Patterns to AVOID

- Do NOT create KB entries in the UI layer — auto-creation happens in the investigator pipeline where investigation data is available
- Do NOT modify `KBService` in the UI — that handles user-facing CRUD; auto-creation uses `KBClient` directly
- Do NOT search the `investigations` collection for similarity — search the `knowledge` collection (that's where prior KB entries live)
- Do NOT create a separate Qdrant collection — use existing `knowledge` and `knowledge_versions`
- Do NOT make auto KB creation fatal — it must NEVER block investigation completion
- Do NOT duplicate InvestigationDocumentationStep's LLM synthesis — reuse its output from pipeline_metadata
- Do NOT skip the embedding generation — entries without proper embeddings break semantic search (NFR20)
- Do NOT modify the operator component — auto KB creation is purely investigator-side
- Do NOT modify any UI code — this story is investigator-only

### Previous Story Intelligence (5-6)

**Key learnings from Story 5-6 (KB Entry Surfacing):**
- `KBSurfacingService._compute_validation_weight()` maps validation_status to weights: proven=3.0, human-confirmed=2.0, AI-generated=1.0
- Story 6-1 entries tagged `validation_status: "AI-generated"` will be automatically surfaced with 1.0 weight in future investigations
- The `novel_issue_candidate: true` flag set by story 5-6 indicates investigations that found no prior knowledge — these are HIGH PRIORITY for KB entry creation
- Composite ranking: `relevance_score * validation_weight` — new entries start at weight 1.0, can be upgraded to 2.0 (human-confirmed) or 3.0 (proven) via story 6-4/6-5

**Key learnings from Story 3.8 (InvestigationDocumentationStep):**
- Retry pattern: 3 attempts, [1.0, 2.0]s delays, then buffer to /tmp/beeper-buffer/
- Payload structure: entry_id, entry_type, investigation_id, service, condition, severity, created_at, title, summary, root_cause, resolution, etc.
- Embedding: `llm_client.embed_sync(summary_text)` — returns list[float] 1536d
- Fallback: zero vector `[0.0] * 1536` if embedding fails
- Always returns success=True (non-fatal step)

**Key learnings from Story 4.8 (ProvenFixAccumulator):**
- Post-resolution KB creation pattern — only creates entry when fix is verified
- Includes `validation_status: "proven"` for verified fixes
- `source_investigation_id` field links back to originating investigation
- Similar retry/buffer pattern

### Testing Standards

- **Framework:** pytest with unittest.mock for KBClient, LlmClient, Qdrant
- **Test location:** `investigator/tests/test_auto_kb_creation.py` (new), updates to `investigator/tests/test_investigation_documentation.py` and `investigator/tests/test_agent.py`
- **Mocking:** `unittest.mock.patch` for KBClient.client, LlmClient.embed_sync, KBClient.search_knowledge
- **Coverage:** All service methods, similarity check paths (create/enrich/skip), error handling, retry/buffer, version snapshots, graceful degradation
- **Pattern reference:** Follow `investigator/tests/test_investigation_documentation.py` for step testing patterns, `investigator/tests/test_proven_fix_accumulator.py` for post-resolution patterns

### Project Structure Notes

**Files to CREATE:**
- `investigator/beeper_investigator/kb/auto_creation.py` — AutoKBCreationService
- `investigator/tests/test_auto_kb_creation.py` — AutoKBCreationService unit tests

**Files to MODIFY:**
- `investigator/beeper_investigator/steps/investigation_documentation.py` — add validation_status and source_investigation_id to payload
- `investigator/beeper_investigator/kb/schemas.py` — add validation_status, source_investigation_id, contributing_investigations fields to KnowledgeEntry
- `investigator/beeper_investigator/agent.py` — add auto KB creation call in _finalize()
- `investigator/tests/test_investigation_documentation.py` — verify validation_status in payload
- `investigator/tests/test_agent.py` — verify auto KB creation integration

**Files to NOT touch:**
- `ui/beeper_ui/services/kb_service.py` — user-facing KB CRUD, not auto-creation
- `ui/beeper_ui/services/kb_surfacing_service.py` — reads KB entries, doesn't create
- `ui/beeper_ui/services/embedding_service.py` — UI-side embeddings
- Any operator files — investigator-only change
- Any UI route, template, or static files — investigator-only change

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 6.1] — Acceptance criteria and story statement
- [Source: _bmad-output/planning-artifacts/architecture.md#FR38] — `investigator/steps/investigation_documentation.py`
- [Source: _bmad-output/planning-artifacts/architecture.md#Knowledge Base] — KB access patterns, Qdrant collections
- [Source: _bmad-output/planning-artifacts/architecture.md#Data Architecture] — Qdrant collections: `knowledge` (Vector 1536d), `knowledge_versions` (payload-only)
- [Source: _bmad-output/planning-artifacts/prd.md#FR38] — System can create KB entries automatically from resolved investigations
- [Source: _bmad-output/planning-artifacts/prd.md#NFR2] — UI response time < 2 seconds for all interactions
- [Source: _bmad-output/planning-artifacts/prd.md#NFR20] — KB semantic search on 10,000+ entries < 2 seconds
- [Source: investigator/beeper_investigator/steps/investigation_documentation.py] — KB entry creation pattern, retry/buffer, LLM synthesis
- [Source: investigator/beeper_investigator/remediation/proven_fix_accumulator.py] — Post-resolution KB entry creation pattern
- [Source: investigator/beeper_investigator/kb/client.py] — KBClient, search_knowledge(), KNOWLEDGE_COLLECTION
- [Source: investigator/beeper_investigator/kb/schemas.py] — KnowledgeEntry, KnowledgeEntryType
- [Source: investigator/beeper_investigator/agent.py] — _finalize(), _persist_result() hook points
- [Source: _bmad-output/implementation-artifacts/5-6-kb-entry-surfacing-live-investigations.md] — Previous story: validation_weight mapping, novel issue detection

## Dev Agent Record

### Agent Model Used

claude-opus-4-6

### Debug Log References

### Completion Notes List

- Created AutoKBCreationService with semantic similarity-based duplicate detection
- Two thresholds: SIMILARITY_THRESHOLD (0.85) and ENRICHMENT_THRESHOLD (0.70)
- Added validation_status: "AI-generated" and source_investigation_id to InvestigationDocumentationStep payload
- Extended KnowledgeEntry schema with validation_status, source_investigation_id, contributing_investigations
- Integrated auto KB creation into agent._finalize() — non-fatal, runs only on successful investigations
- Version snapshots saved to knowledge_versions collection before enrichment
- Full retry/buffer pattern following InvestigationDocumentationStep
- 21 new tests for AutoKBCreationService, 3 new agent integration tests, 2 updated doc step tests
- All 3,070 tests pass across all components (914 investigator, 1625 UI, 531 operator)

### Change Log

- 2026-03-17: Implemented story 6-1 — automatic KB entry creation from resolved investigations

### File List

- investigator/beeper_investigator/kb/auto_creation.py (CREATED) — AutoKBCreationService
- investigator/beeper_investigator/kb/schemas.py (MODIFIED) — Added validation_status, source_investigation_id, contributing_investigations to KnowledgeEntry
- investigator/beeper_investigator/kb/client.py (MODIFIED) — Added VERSIONS_COLLECTION constant
- investigator/beeper_investigator/steps/investigation_documentation.py (MODIFIED) — Added validation_status and source_investigation_id to payload
- investigator/beeper_investigator/agent.py (MODIFIED) — Added auto KB creation hook in _finalize(), _auto_create_kb_entry method
- investigator/tests/test_auto_kb_creation.py (CREATED) — 21 tests for AutoKBCreationService
- investigator/tests/test_agent.py (MODIFIED) — 3 new integration tests, 1 updated test
- investigator/tests/test_investigation_documentation.py (MODIFIED) — 2 new tests for validation_status, updated schema test
- _bmad-output/implementation-artifacts/6-1-automatic-kb-entry-creation.md (MODIFIED) — Story file
- _bmad-output/implementation-artifacts/sprint-status.yaml (MODIFIED) — Epic 6 in-progress, story 6-1 status updates
