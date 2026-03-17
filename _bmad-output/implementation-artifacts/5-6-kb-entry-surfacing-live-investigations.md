# Story 5.6: KB Entry Surfacing During Live Investigations

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the **system**,
I want to surface relevant past KB entries during live investigations,
so that Beeper and the SRE can leverage institutional knowledge in real-time.

## Acceptance Criteria

1. **Given** an active investigation with identified symptoms **When** the investigator reaches the analysis phase **Then** semantically similar KB entries are retrieved and displayed as "Related Knowledge" in the investigation view **And** entries are ranked by relevance score and validation status (proven > human-confirmed > AI-generated)

2. **Given** a surfaced KB entry during a live investigation **When** the SRE clicks on the entry **Then** the full KB entry is displayed with its evidence trail and prior investigation links **And** the SRE can flag the entry as "relevant" or "not relevant" to improve future surfacing

3. **Given** no relevant KB entries exist **When** the KB search returns empty **Then** the investigation notes "No prior knowledge found — this may be a novel issue" **And** the investigation outcome is marked as a candidate for new KB entry creation

## Tasks / Subtasks

- [x]Task 1: Create `KBSurfacingService` in `ui/beeper_ui/services/kb_surfacing_service.py` (AC: #1, #2, #3)
  - [x]1.1 Create `KBSurfacingResult` dataclass with fields: `entries: list[dict]` (each with id, entry_id, title, content_preview, entry_type, service, validation_status, relevance_score, composite_score, created_at, link), `is_novel: bool`, `query_text: str`, `investigation_id: str`. Add `to_dict()` method for serialization.
  - [x]1.2 Create `KBSurfacingService` class with `__init__(self, qdrant_url: str, qdrant_api_key: str | None = None, embedding_api_key: str | None = None)` — lazily creates `KBService` and `EmbeddingService` instances internally. Follow existing service composition pattern from `HandoffService` at `services/handoff_service.py:25-45`.
  - [x]1.3 Add `surface_entries(self, investigation_id: str, findings: dict) -> KBSurfacingResult` method that: (a) composes a semantic query from findings by extracting symptoms, root cause hypothesis, service name, signal summary, and investigation condition, (b) calls `KBService.search_semantic(query, limit=10, score_threshold=0.4)` to get semantically similar entries, (c) computes composite_score for each entry = `relevance_score * validation_weight` where proven=3.0, human-confirmed=2.0, AI-generated=1.0, (d) sorts by composite_score descending, (e) sets `is_novel = True` when no entries returned, (f) builds link as `/knowledge/{entry_id}` for each entry.
  - [x]1.4 Add `_compose_query(self, findings: dict) -> str` private method that builds a search query string from findings. Extract and concatenate: `findings.get("root_cause_hypothesis", "")`, `findings.get("prior_research_summary", "")`, `findings.get("signal_summary", "")`, condition/severity from top-level investigation data. Cap at 500 characters. If findings is empty/None, return empty string.
  - [x]1.5 Add `_compute_validation_weight(self, validation_status: str | None) -> float` private static method. Returns: `"proven"` → 3.0, `"human-confirmed"` → 2.0, `"AI-generated"` → 1.0, `None`/unknown → 1.0.
  - [x]1.6 Add `record_relevance_feedback(self, investigation_id: str, entry_id: str, is_relevant: bool, user: str) -> bool` method. Fetches the investigation's findings from Qdrant `investigations` collection, adds/updates a `kb_relevance_feedback` dict in the payload: `{entry_id: {"is_relevant": bool, "user": str, "timestamp": iso_now}}`. Upserts back to Qdrant. Returns True on success. On failure, log warning with exc_info=True and return False.
  - [x]1.7 Add `mark_novel_investigation(self, investigation_id: str) -> bool` method. Fetches investigation from Qdrant, sets `novel_issue_candidate: true` in payload. Returns True on success. On failure, log warning and return False.
  - [x]1.8 Add `close(self)` method that closes internal KBService instance.
  - [x]1.9 Wrap all external calls in try/except — if KBService fails, return empty KBSurfacingResult with `is_novel=True` (safe fallback). If EmbeddingService fails, fall back to `KBService.list_entries_by_service()` (service-based listing without semantic search). Log warnings with `exc_info=True` on failures.

- [x]Task 2: Update `investigation_related_kb` route to use semantic search (AC: #1, #3)
  - [x]2.1 In `ui/beeper_ui/routes/investigations.py`, update the `investigation_related_kb(investigation_id)` route function. Replace the current `kb_service.list_entries_by_service(investigation.service, limit=10)` call with `KBSurfacingService.surface_entries(investigation_id, findings)`. Import `KBSurfacingService`.
  - [x]2.2 Add `_get_kb_surfacing_service() -> KBSurfacingService` helper function using `current_app.config["QDRANT_URL"]` and `current_app.config.get("QDRANT_API_KEY")` and `current_app.config.get("EMBEDDING_API_KEY")`. Follow the `_get_kb_service()` pattern already in investigations.py.
  - [x]2.3 Pass `surfacing_result` to `_related_kb.html` template instead of separate `related_entries` and `exact_match_entry`. Template receives: `surfacing_result` (KBSurfacingResult), `exact_match_entry` (still fetched separately if `exact_match_id` present), `exact_match_found` (from findings). Always close service in `finally` block.
  - [x]2.4 When `surfacing_result.is_novel` is True, call `surfacing_service.mark_novel_investigation(investigation_id)` to flag the investigation (AC #3).

- [x]Task 3: Update SSE `kb-update` event to use semantic search (AC: #1)
  - [x]3.1 In `_generate_detail_sse_events()` in `investigations.py`, replace the KB entry listing logic (currently uses `kb_service.list_entries_by_service()`) with `KBSurfacingService.surface_entries(investigation_id, findings)`. Pass the surfacing_result to the template render.
  - [x]3.2 Ensure the SSE event still renders `_related_kb.html` partial — just with the enhanced semantic results and ranking.

- [x]Task 4: Add WebSocket handler for KB relevance feedback (AC: #2)
  - [x]4.1 In `ui/beeper_ui/websocket/investigation.py`, add `@socketio.on("kb_relevance_feedback")` handler. Expects `data = {"investigation_id": str, "entry_id": str, "is_relevant": bool}`. Validates investigation_id and entry_id are present. Creates `KBSurfacingService` instance, calls `record_relevance_feedback()`. Broadcasts `kb_feedback_recorded` event to investigation room with `{"entry_id": entry_id, "is_relevant": is_relevant, "user": user}`. Always close service in finally block. Follow validate → action → broadcast pattern from `handle_annotate` at `investigation.py:95-130`.
  - [x]4.2 Store a `CollaborationMessage` with `message_type="kb_feedback"` and `content` describing the feedback (e.g., "Marked KB entry 'title' as relevant"). Persist via `CollaborationService.store_message()`. This provides audit trail in collaboration history.

- [x]Task 5: Update `_related_kb.html` template for semantic ranking, feedback, and empty state (AC: #1, #2, #3)
  - [x]5.1 Refactor `_related_kb.html` to accept `surfacing_result` instead of `related_entries`. Loop over `surfacing_result.entries` displaying each entry card with: title (clickable link to `/knowledge/{entry_id}`), entry_type badge, validation_status badge with weight indicator (proven=gold star, human-confirmed=blue check, AI-generated=gray bot), composite_score display, relevance_score percentage, service badge, content_preview (first 150 chars), created_at date.
  - [x]5.2 Add relevance feedback buttons to each KB entry card: "Relevant" (thumbs-up icon, green accent on click) and "Not Relevant" (thumbs-down icon, gray accent on click). Buttons emit WebSocket `kb_relevance_feedback` event. Once clicked, button shows selected state and disables the other button. Use `data-entry-id` attribute for JS targeting.
  - [x]5.3 Add empty state (AC #3): When `surfacing_result.is_novel` is True (or `surfacing_result.entries` is empty), display a styled "No prior knowledge found" banner: amber-bordered card with text "No prior knowledge found — this may be a novel issue" and a note "This investigation will be flagged as a candidate for new KB entry creation." Use `.kb-novel-issue` CSS class.
  - [x]5.4 Preserve the existing `exact_match_found` banner: If `exact_match_found and exact_match_entry`, show the "Building on prior research" banner at top, above the semantically surfaced entries.
  - [x]5.5 Add sort indicator: Small text above entry list showing "Ranked by relevance and validation status" with a tooltip explaining the ranking formula.

- [x]Task 6: Add JavaScript for KB relevance feedback and real-time updates (AC: #2)
  - [x]6.1 In `ui/beeper_ui/static/js/collaboration.js` (the existing collaboration panel JS), add WebSocket event listener for `kb_feedback_recorded`. When received, update the feedback button state for the matching `data-entry-id` entry card — show selected state on the voted button, disable the other.
  - [x]6.2 Add `sendKBFeedback(entryId, isRelevant)` function that emits `kb_relevance_feedback` WebSocket event with `{investigation_id: currentInvestigationId, entry_id: entryId, is_relevant: isRelevant}`. Use optimistic UI — immediately update button state before server confirmation.
  - [x]6.3 Attach click handlers to `.kb-feedback-btn` elements using event delegation on the related-kb container (handles HTMX-swapped content). Each button has `data-entry-id` and `data-feedback` (relevant/not-relevant) attributes.

- [x]Task 7: Add CSS styles for KB surfacing enhancements (AC: #1, #2, #3)
  - [x]7.1 In `ui/beeper_ui/static/css/main.css`, add `.kb-surfacing-entry` card styles — extends existing `.kb-entry-card` pattern. Add `.kb-composite-score` badge (inline, smaller than validation badge), `.kb-validation-weight` indicator (star/check/bot icons as text, gold/blue/gray colors).
  - [x]7.2 Add `.kb-feedback-btn` styles — small icon buttons, `.kb-feedback-btn.selected-relevant` (green background), `.kb-feedback-btn.selected-not-relevant` (gray background), `.kb-feedback-btn:disabled` (reduced opacity). Follow existing `.collab-*` button sizing patterns.
  - [x]7.3 Add `.kb-novel-issue` banner styles — amber left-border accent (matching SBAR Assessment amber from story 5-5), centered text, investigation-detail-friendly spacing. Follow `.handoff-all-clear` pattern but with amber instead of green.
  - [x]7.4 Add `.kb-sort-indicator` text style — small muted text, positioned above entry list, consistent with existing `.evidence-timeline` label styling.

- [x]Task 8: Write unit tests for KBSurfacingService in `ui/tests/test_kb_surfacing_service.py` (AC: #1, #2, #3)
  - [x]8.1 `TestKBSurfacingResult` — test dataclass creation, `to_dict()` serialization, `is_novel` flag behavior.
  - [x]8.2 `TestSurfaceEntries` — mock KBService.search_semantic() and EmbeddingService. Test with: multiple KB entries with mixed validation statuses → verify composite_score calculation and descending sort order. Test proven (weight 3.0) outranks AI-generated (weight 1.0) even with slightly lower relevance_score.
  - [x]8.3 `TestSurfaceEntriesEmptyResults` — mock search_semantic returning empty → verify `is_novel=True`, empty entries list, query_text set.
  - [x]8.4 `TestComposeQuery` — test query composition from various findings dicts: full findings → concatenated symptoms, empty findings → empty string, None findings → empty string, findings with only root_cause → includes that text. Verify 500-char cap.
  - [x]8.5 `TestComputeValidationWeight` — test all status values: "proven" → 3.0, "human-confirmed" → 2.0, "AI-generated" → 1.0, None → 1.0, unknown string → 1.0.
  - [x]8.6 `TestRecordRelevanceFeedback` — mock Qdrant client. Test: successful feedback recording → returns True, feedback stored in payload. Test: Qdrant failure → returns False, no crash. Test: multiple feedbacks for same investigation → additive (doesn't overwrite previous feedback for different entries).
  - [x]8.7 `TestMarkNovelInvestigation` — mock Qdrant client. Test: successful marking → returns True, `novel_issue_candidate: true` in payload. Test: Qdrant failure → returns False.
  - [x]8.8 `TestGracefulDegradation` — test: KBService.search_semantic raises → fallback to list_entries_by_service. EmbeddingService unavailable → fallback to service-based listing. Both fail → empty result, no crash.

- [x]Task 9: Write route, WebSocket, and template integration tests (AC: #1, #2, #3)
  - [x]9.1 `TestRelatedKBSemanticSearch` in `ui/tests/test_investigation_routes.py` — mock KBSurfacingService. Test GET `/investigations/{id}/related-kb` uses semantic search, returns HTML with ranked entries, validation badges, composite scores.
  - [x]9.2 `TestRelatedKBEmptyState` — test empty search results render "No prior knowledge found" banner with `.kb-novel-issue` class (AC #3). Verify `mark_novel_investigation()` called.
  - [x]9.3 `TestRelatedKBFeedbackButtons` — test template renders relevance feedback buttons with correct `data-entry-id` and `data-feedback` attributes for each entry.
  - [x]9.4 `TestKBRelevanceFeedbackWebSocket` in `ui/tests/test_websocket_handlers.py` — test `kb_relevance_feedback` event: valid feedback → `record_relevance_feedback()` called, `kb_feedback_recorded` broadcast to room, `CollaborationMessage` stored. Test missing investigation_id → error response. Test missing entry_id → error response.
  - [x]9.5 `TestRelatedKBRanking` — test that entries with `proven` validation appear before `AI-generated` entries even when relevance_scores are similar. Verify composite_score ordering in rendered HTML.
  - [x]9.6 `TestExactMatchPreservation` — test that exact_match_entry banner still renders above semantic results when `exact_match_found` is True.

- [x]Task 10: Run full test suite across all components (AC: all)
  - [x]10.1 Run UI tests: `cd ui && poetry run python -m pytest` — all pass (existing + new)
  - [x]10.2 Run investigator tests: `cd investigator && poetry run python -m pytest` — 888 passed, 3 skipped
  - [x]10.3 Run operator tests: `cd operator && cargo test` — 531 passed
  - [x]10.4 No regressions found

## Dev Notes

### Architecture Patterns (CRITICAL — must follow)

**KB surfacing is a COMPOSITION service (from architecture.md):**
- The architecture specifies: `FR37 (surface past KB): investigator/steps/kb_query.py (extended: real-time KB push via SocketIO)`
- In the UI layer, this translates to: `KBSurfacingService` composing `KBService` + `EmbeddingService` for semantic search
- The service is a read-only aggregation — it queries existing KB entries, it does NOT create or modify them
- Relevance feedback writes to the investigation's Qdrant payload (not the KB entry itself)

**Semantic Search (CRITICAL — replaces service-based listing):**
The current `investigation_related_kb` route uses `kb_service.list_entries_by_service()` which is NOT semantic — it just filters by service name. Story 5-6 MUST upgrade this to `kb_service.search_semantic()` using investigation findings as the query. The `search_semantic()` method already exists and handles:
- Vector embedding via `EmbeddingService` (text-embedding-3-small, 1536 dims)
- Qdrant `query_points()` with cosine similarity
- Score threshold filtering (default 0.5, use 0.4 for broader surfacing)
- Returns `(entries, has_exact_matches)` tuple

**Composite Ranking Formula (AC #1 — CRITICAL):**
```
composite_score = relevance_score * validation_weight

Validation weights:
  proven          → 3.0  (gold star indicator)
  human-confirmed → 2.0  (blue check indicator)
  AI-generated    → 1.0  (gray bot indicator)
  unknown/None    → 1.0  (no indicator)
```
This ensures a proven entry with 0.6 relevance (composite: 1.8) outranks an AI-generated entry with 0.7 relevance (composite: 0.7). Sort descending by composite_score.

**Two-Channel Pattern (SocketIO + SSE):**
- SSE channel: Used for investigation progress updates. The `kb-update` SSE event already fires when KB query step completes. This should be upgraded to use semantic search results.
- WebSocket channel: Used for collaboration (messages, annotations, approvals). KB relevance feedback is a collaboration action, so it goes through WebSocket.
- Both channels can push KB data — SSE for initial/periodic updates, WebSocket for feedback events.

**Relevance Feedback Storage Pattern:**
```python
# Stored in investigation's Qdrant payload under kb_relevance_feedback key
investigations_collection.payload:
  kb_relevance_feedback:
    "kb-entry-abc123":
      is_relevant: true
      user: "sam"
      timestamp: "2026-03-16T14:30:00Z"
    "kb-entry-def456":
      is_relevant: false
      user: "sam"
      timestamp: "2026-03-16T14:31:00Z"
```
This stores feedback per-investigation (not globally) — avoids polluting KB entries with investigation-specific relevance. Future stories (Epic 6) can aggregate this feedback across investigations for KB improvement.

**Novel Issue Detection (AC #3):**
When `search_semantic()` returns empty results:
1. Display "No prior knowledge found — this may be a novel issue" banner
2. Set `novel_issue_candidate: true` in investigation Qdrant payload
3. This flag will be consumed by Story 6-1 (Automatic KB Entry Creation) to prioritize creating KB entries from novel investigations

**Data Sources (reuse existing services — DO NOT recreate):**
```
KBSurfacingService
  ├── KBService.search_semantic(query)     → semantically similar entries
  ├── KBService.get_entry(entry_id)        → exact match detail
  ├── EmbeddingService.get_embedding()     → used internally by KBService
  ├── InvestigationService (via Qdrant)    → investigation findings for query composition
  └── Relevance feedback storage           → investigation Qdrant payload
```

**WebSocket Handler Pattern (follow `handle_annotate`):**
```python
@socketio.on("kb_relevance_feedback")
def handle_kb_relevance_feedback(data):
    investigation_id = data.get("investigation_id")
    entry_id = data.get("entry_id")
    is_relevant = data.get("is_relevant")
    if not investigation_id or not entry_id or is_relevant is None:
        emit("error", {"message": "Missing required fields"})
        return
    # ... record feedback, store collaboration message, broadcast
```

**NFR2 Compliance — < 2 seconds:**
- `search_semantic()` already optimized with Qdrant vector search (sub-second for 10K entries per NFR20)
- EmbeddingService uses LRU cache (128 entries) — repeated queries for same investigation are instant
- Template rendering is minimal — no additional API calls in Jinja2
- Fallback to `list_entries_by_service()` if embedding fails — still fast

### Existing Code to Reuse (DO NOT RECREATE)

| Component | Location | What to Reuse |
|-----------|----------|---------------|
| KBService | `ui/beeper_ui/services/kb_service.py:17` | `search_semantic()`, `get_entry()`, `list_entries_by_service()`, KBEntry dataclass |
| EmbeddingService | `ui/beeper_ui/services/embedding_service.py:12` | `get_embedding()`, `is_configured()` |
| EvidenceService | `ui/beeper_ui/services/evidence_service.py:10` | `_derive_validation_status()` pattern for validation weights |
| InvestigationService | `ui/beeper_ui/services/investigation_service.py:73` | `get_investigation()`, `get_investigation_findings()`, Investigation dataclass |
| CollaborationService | `ui/beeper_ui/services/collaboration_service.py:12` | `store_message()`, CollaborationMessage dataclass |
| WebSocket handlers | `ui/beeper_ui/websocket/investigation.py:25` | Pattern: validate → action → broadcast with room join |
| Related KB template | `ui/beeper_ui/templates/investigations/_related_kb.html` | Existing layout — modify in place, do not recreate |
| Evidence timeline | `ui/beeper_ui/templates/investigations/_evidence_timeline.html` | KB-type evidence reference rendering |
| Detail content | `ui/beeper_ui/templates/investigations/_detail_content.html` | Related Knowledge section HTMX lazy-load pattern |
| KB entry card CSS | `ui/beeper_ui/static/css/main.css` | `.kb-entry-card`, validation-status badges, evidence-type badges |
| Collaboration JS | `ui/beeper_ui/static/js/collaboration.js` | WebSocket connection, event emission/reception patterns |
| Route patterns | `ui/beeper_ui/routes/investigations.py:200` | `_get_kb_service()`, `investigation_related_kb()` |

### Anti-Patterns to AVOID

- Do NOT create a new Qdrant collection — feedback is stored in existing `investigations` collection payload
- Do NOT modify `KBService.search_semantic()` — compose around it, don't change it
- Do NOT add a separate search endpoint — use the existing `investigation_related_kb` route
- Do NOT implement global KB ranking changes — relevance feedback is per-investigation only
- Do NOT import or use any new dependencies — everything needed (KBService, EmbeddingService, Qdrant, Flask-SocketIO) already installed
- Do NOT create modal dialogs for KB entry detail — clicking links navigates to `/knowledge/{entry_id}` (existing page)
- Do NOT modify the investigator component — this story is UI-only, composing existing services
- Do NOT add keyboard shortcuts for relevance feedback — mouse clicks on thumbs-up/down are sufficient for this interaction
- Do NOT change the `_evidence_timeline.html` KB reference rendering — that shows inline evidence, while `_related_kb.html` shows the dedicated Related Knowledge section. They are complementary, not duplicates.

### Previous Story Intelligence (5-5)

**Key learnings from Story 5-5 (Shift Handoff Summaries):**
- Service composition pattern: HandoffService composes InvestigationService + SloService — follow same pattern for KBSurfacingService composing KBService + EmbeddingService
- Graceful degradation: One service failure shouldn't crash the whole feature — if semantic search fails, fall back to service-based listing
- `close()` method wrapped in try/finally to prevent resource leaks
- CSS namespace: `.handoff-*` for handoff, use `.kb-surfacing-*` for new KB surfacing styles
- Test patterns: service unit tests + route/template integration tests in separate files

**Key learnings from Story 5-4 (Fix Approval & Rejection):**
- WebSocket handler pattern: validate → forward → store → broadcast — apply to kb_relevance_feedback
- Optimistic UI: button state updates immediately before server confirmation — apply to feedback buttons
- `appendLabeledMessage()` helper — collaboration panel messages should use consistent formatting
- CSS follows `.collab-*` namespace for collaboration features

**Key learnings from Story 5-2 (Evidence Presentation with References):**
- EvidenceService pattern: extract → enrich → render — KBSurfacingService follows extract → rank → render
- validation_status badges already styled: `.validation-proven`, `.validation-human-confirmed`, `.validation-ai-generated`
- KB-type evidence references already link to `/knowledge/{entry_id}` — reuse this link pattern

**Key learnings from Story 5-1 (WebSocket):**
- Blueprint-less WebSocket handlers — all handlers in `websocket/investigation.py`
- Room-based broadcasting: `emit(..., to=room_id)` for investigation-scoped events
- CollaborationMessage persistence for audit trail

### Testing Standards

- **Framework:** pytest with Flask test client + Flask-SocketIO test client
- **Test location:** `ui/tests/test_kb_surfacing_service.py` (service unit tests), additional tests in `ui/tests/test_investigation_routes.py` and `ui/tests/test_websocket_handlers.py`
- **Mocking:** Use `unittest.mock.patch` for KBService, EmbeddingService, and Qdrant client
- **Coverage expectations:** All service methods, route happy path, error states, empty state (novel issue), WebSocket feedback handler, template rendering with ranked entries
- **Pattern reference:** Follow `ui/tests/test_evidence_service.py` for service mocking patterns and `ui/tests/test_investigation_routes.py` for route test patterns, `ui/tests/test_websocket_handlers.py` for WebSocket handler test patterns
- **Assert on HTML content:** Check for validation status badges, composite score display, feedback buttons, novel issue banner, ranking order

### Project Structure Notes

**Files to CREATE:**
- `ui/beeper_ui/services/kb_surfacing_service.py` — KBSurfacingService + KBSurfacingResult dataclass
- `ui/tests/test_kb_surfacing_service.py` — KBSurfacingService unit tests

**Files to MODIFY:**
- `ui/beeper_ui/routes/investigations.py` — update `investigation_related_kb()` route and SSE handler to use semantic search
- `ui/beeper_ui/websocket/investigation.py` — add `kb_relevance_feedback` handler
- `ui/beeper_ui/templates/investigations/_related_kb.html` — enhanced ranking display, feedback buttons, empty state
- `ui/beeper_ui/static/js/collaboration.js` — add KB feedback WebSocket handlers and click handlers
- `ui/beeper_ui/static/css/main.css` — add KB surfacing CSS styles
- `ui/tests/test_investigation_routes.py` — add semantic search route tests, empty state tests, ranking tests
- `ui/tests/test_websocket_handlers.py` — add kb_relevance_feedback handler tests

**Files to NOT touch:**
- `ui/beeper_ui/services/kb_service.py` — use as-is, no changes
- `ui/beeper_ui/services/evidence_service.py` — use as-is, no changes
- `ui/beeper_ui/services/embedding_service.py` — use as-is, no changes
- `ui/beeper_ui/services/investigation_service.py` — use as-is, no changes
- `ui/beeper_ui/services/collaboration_service.py` — use as-is, no changes
- `ui/beeper_ui/templates/investigations/_evidence_timeline.html` — complementary display, not duplicate
- `ui/beeper_ui/templates/investigations/_detail_content.html` — HTMX lazy-load pattern already correct
- Any investigator or operator files — this story is UI-only

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.6] — Acceptance criteria and story statement
- [Source: _bmad-output/planning-artifacts/architecture.md#FR37] — `investigator/steps/kb_query.py` (extended: real-time KB push via SocketIO)
- [Source: _bmad-output/planning-artifacts/architecture.md#Knowledge Base] — KB access patterns, Qdrant collections
- [Source: _bmad-output/planning-artifacts/architecture.md#WebSocket Events] — SocketIO event definitions
- [Source: _bmad-output/planning-artifacts/architecture.md#Data Architecture] — Qdrant collections: `knowledge` (Vector 1536d), `investigations` (Vector 1536d)
- [Source: _bmad-output/planning-artifacts/prd.md#FR37] — System can surface relevant past KB entries during live investigations
- [Source: _bmad-output/planning-artifacts/prd.md#NFR2] — UI response time < 2 seconds for all interactions
- [Source: _bmad-output/planning-artifacts/prd.md#NFR20] — KB semantic search on 10,000+ entries < 2 seconds
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Evidence Timeline] — Citation links, KB references, confidence breakdown with KB precedent
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Investigation Detail] — Related Knowledge section, split-pane KB view
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Design Principles] — "Evidence over assertion" — show KB refs, test results
- [Source: ui/beeper_ui/services/kb_service.py] — KBService.search_semantic(), get_entry(), list_entries_by_service(), KBEntry dataclass
- [Source: ui/beeper_ui/services/embedding_service.py] — EmbeddingService.get_embedding(), is_configured()
- [Source: ui/beeper_ui/services/evidence_service.py] — EvidenceReference, _derive_validation_status(), enrich_kb_references()
- [Source: ui/beeper_ui/services/collaboration_service.py] — CollaborationMessage, store_message()
- [Source: ui/beeper_ui/routes/investigations.py] — investigation_related_kb() route, _generate_detail_sse_events()
- [Source: ui/beeper_ui/websocket/investigation.py] — WebSocket handler patterns, room broadcasting
- [Source: ui/beeper_ui/templates/investigations/_related_kb.html] — Current template to enhance
- [Source: _bmad-output/implementation-artifacts/5-5-shift-handoff-summaries.md] — Previous story: service composition, graceful degradation, CSS namespace
- [Source: _bmad-output/implementation-artifacts/5-4-fix-approval-rejection.md] — Previous story: WebSocket handler patterns, optimistic UI
- [Source: _bmad-output/implementation-artifacts/5-2-evidence-presentation-references.md] — Previous story: evidence extraction, KB reference enrichment, validation badges

## Dev Agent Record

### Agent Model Used

claude-opus-4-6

### Debug Log References

### Completion Notes List

### Change Log

### File List
