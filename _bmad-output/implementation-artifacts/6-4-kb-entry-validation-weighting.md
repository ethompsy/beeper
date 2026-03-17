# Story 6.4: KB Entry Validation Weighting

Status: review

## Story

As the **system**,
I want KB entries weighted by validation status (human-confirmed, AI-generated, corrected),
so that proven knowledge ranks higher than unverified AI conclusions.

## Acceptance Criteria

1. **Given** KB entries with different validation statuses **When** the investigator performs a semantic search for relevant knowledge **Then** results are ranked with weighting: proven (1.0x) > human-confirmed (0.9x) > corrected (0.8x) > AI-generated (0.6x) **And** the weighting is applied as a multiplier on the semantic similarity score

2. **Given** an SRE confirms an AI-generated KB entry as accurate **When** the confirmation is recorded **Then** the entry's validation_status changes from "AI-generated" to "human-confirmed" **And** the change is versioned with the confirming user and timestamp

3. **Given** an SRE corrects a KB entry **When** the correction is saved **Then** the validation_status changes to "corrected" with the original and corrected content preserved **And** future investigations referencing this entry see the corrected version

## Tasks / Subtasks

- [x] Task 1: Update `VALIDATION_WEIGHTS` and `_derive_validation_status()` in `KBSurfacingService` (AC: #1)
  - [x]1.1 In `ui/beeper_ui/services/kb_surfacing_service.py`, update `VALIDATION_WEIGHTS` dict (line 25) to: `{"proven": 1.0, "human-confirmed": 0.9, "corrected": 0.8, "AI-generated": 0.6}`. Update `DEFAULT_VALIDATION_WEIGHT` (line 30) to `0.6` (treat unknown statuses same as AI-generated).
  - [x]1.2 In `ui/beeper_ui/services/kb_surfacing_service.py`, rewrite `_derive_validation_status()` (line 222) to read `entry.validation_status` directly. If `entry.validation_status` is not None, return it. Otherwise, fall back to the existing entry_type-based derivation: `proven_fix` -> `"proven"`, `correction` -> `"human-confirmed"`, else `"AI-generated"`.
  - [x]1.3 Update `_compute_validation_weight()` (line 238) docstring to reflect the new weight values. No structural change needed — the lookup pattern is already correct.

- [x] Task 2: Apply validation weighting in investigator `KBQueryStep` (AC: #1)
  - [x]2.1 In `investigator/beeper_investigator/steps/kb_query.py`, add `VALIDATION_WEIGHTS: dict[str, float] = {"proven": 1.0, "human-confirmed": 0.9, "corrected": 0.8, "AI-generated": 0.6}` constant and `DEFAULT_VALIDATION_WEIGHT = 0.6` near existing `EXACT_MATCH_THRESHOLD` constant (line 21).
  - [x]2.2 Add a `_apply_validation_weighting(results: list[SearchResult]) -> list[SearchResult]` static method to `KBQueryStep`. For each result, read `result.payload.get("validation_status", "AI-generated")`, look up the weight from `VALIDATION_WEIGHTS` (default `DEFAULT_VALIDATION_WEIGHT`), compute `weighted_score = result.score * weight`, and create a new `SearchResult` with `score=weighted_score`. Return the list sorted descending by weighted score. IMPORTANT: Do NOT modify the `EXACT_MATCH_THRESHOLD` logic — it should still operate on raw scores before weighting is applied.
  - [x]2.3 In `KBQueryStep.execute()`, apply `_apply_validation_weighting()` to `knowledge_results` after the `search_knowledge()` call (around line 140) but BEFORE the exact match threshold check. Do NOT apply weighting to `investigation_results` (they don't have `validation_status`).
  - [x]2.4 In `_format_results()` (line 66), add `validation_status` to the formatted output: `- [{inv_id}] (score={r.score:.2f}, status={validation_status}) {summary} | root_cause: ... | resolution: ...` so the LLM synthesizer can see the trust level.

- [x] Task 3: Add `confirm_entry()` method to `KBService` (AC: #2)
  - [x]3.1 In `ui/beeper_ui/services/kb_service.py`, add `confirm_entry(self, entry_id: str, user: str) -> int` method. Steps: (1) Fetch existing entry via scroll on `KNOWLEDGE_COLLECTION` with `entry_id` filter. (2) Verify current `validation_status` is `"AI-generated"` (raise `KBServiceError` if not — can only confirm AI-generated entries). (3) Save version snapshot via `self._save_version_snapshot()`. (4) Update payload with `validation_status="human-confirmed"`, increment `version`, set `updated_at` to now (ISO format), set `author` to the confirming user. (5) Upsert to Qdrant preserving existing vector. (6) Return new version number.
  - [x]3.2 Also add `validation_status` to the `_save_version_snapshot()` method (line 881): add `"validation_status": payload.get("validation_status")` to `version_payload` dict so version history tracks status transitions.

- [x] Task 4: Wire correction flow to set validation_status="corrected" (AC: #3)
  - [x]4.1 In `ui/beeper_ui/services/kb_service.py`, modify `update_entry()` (line 1254): Add `validation_status: Optional[str] = None` parameter. When building the updated payload (around line 1334), if `validation_status` is provided, use it; otherwise preserve `existing_payload.get("validation_status")`.
  - [x]4.2 In `ui/beeper_ui/routes/knowledge.py`, in the edit route handler (line 861), when a content change is detected (title or content differs from original), pass `validation_status="corrected"` to `kb_service.update_entry()`. When only tags change, do NOT change validation_status. Use the existing diff detection logic — compare `new_title != existing.title or new_content != existing.content`.

- [x] Task 5: Add confirm entry route (AC: #2)
  - [x]5.1 In `ui/beeper_ui/routes/knowledge.py`, add `POST /knowledge/<entry_id>/confirm` route. Accept `user` from form data (or default to `"anonymous"`). Call `kb_service.confirm_entry(entry_id, user)`. On success, flash "Entry confirmed as human-verified" and redirect to entry detail page. On `KBServiceError`, flash error and redirect. Use the existing `get_kb_service()` factory and `sanitize_query()` for entry_id.
  - [x]5.2 In `ui/beeper_ui/templates/knowledge/entry.html`, add a "Confirm as Accurate" button that is only visible when `entry.validation_status == "AI-generated"`. The button should POST to `/knowledge/{entry_id}/confirm`. Style consistently with existing action buttons on the page.

- [x] Task 6: Write unit tests for `KBSurfacingService` changes (AC: #1)
  - [x]6.1 In `ui/tests/test_kb_surfacing_service.py`, update `_make_kb_entry()` helper (line 18) to accept `validation_status: Optional[str] = None` parameter and pass it to `KBEntry`.
  - [x]6.2 Update `TestComputeValidationWeight` (line 73): change expected values to match new weights (proven=1.0, human-confirmed=0.9, corrected=0.8, AI-generated=0.6). Add test for `"corrected"` returning 0.8. Update `None`/unknown to return `DEFAULT_VALIDATION_WEIGHT` (0.6).
  - [x]6.3 Update `TestDeriveValidationStatus` (line 92): add test that when `entry.validation_status` is set (e.g., `"human-confirmed"`), it returns the field value directly regardless of `entry_type`. Add test that when `entry.validation_status` is `None`, falls back to entry_type derivation.
  - [x]6.4 Update `TestSurfaceEntries.test_surface_entries_ranked` (line 166): adjust expected composite scores to use new weights. Verify ordering: proven entry (0.6 * 1.0 = 0.6) vs human-confirmed (0.7 * 0.9 = 0.63) vs AI-generated (0.9 * 0.6 = 0.54). The ranking should be: human-confirmed > proven > AI-generated with these test scores.

- [x] Task 7: Write unit tests for `KBQueryStep` validation weighting (AC: #1)
  - [x]7.1 In `investigator/tests/test_kb_query.py`, update `_make_result()` helper to accept optional `validation_status` parameter, included in the payload dict.
  - [x]7.2 Add `TestValidationWeighting` class with tests: (a) `test_weighting_reranks_results` — proven entry with score 0.5 ranks above AI-generated entry with score 0.7 after weighting (0.5*1.0=0.5 > 0.7*0.6=0.42). (b) `test_missing_validation_status_defaults_to_ai_generated` — entry without validation_status in payload gets 0.6x weight. (c) `test_corrected_weight` — corrected entry gets 0.8x weight. (d) `test_format_results_includes_validation_status` — formatted output includes status string.

- [x] Task 8: Write unit tests for `KBService.confirm_entry()` and updated `update_entry()` (AC: #2, #3)
  - [x]8.1 In `ui/tests/test_kb_service.py`, add `TestConfirmEntry` class: test successful confirmation (AI-generated -> human-confirmed), test rejection when current status is not AI-generated, test version snapshot is saved before update, test author and timestamp are recorded.
  - [x]8.2 Add `TestUpdateEntryValidationStatus` tests: test that passing `validation_status="corrected"` updates the field, test that omitting `validation_status` preserves existing value.

- [x] Task 9: Write route tests for confirm endpoint (AC: #2)
  - [x]9.1 In `ui/tests/test_routes_knowledge.py`, add `TestConfirmEntryRoute` class: test POST to `/knowledge/{entry_id}/confirm` returns redirect on success, test confirm with non-AI-generated entry shows error flash, test entry_id is sanitized.

- [x] Task 10: Run full test suite across all components (AC: all)
  - [x]10.1 Run investigator tests: `cd investigator && poetry run python -m pytest`
  - [x]10.2 Run investigator linting: `cd investigator && poetry run ruff check .`
  - [x]10.3 Run investigator type checking: `cd investigator && poetry run mypy .`
  - [x]10.4 Run UI tests: `cd ui && poetry run python -m pytest`
  - [x]10.5 Run operator tests: `cd operator && cargo test`
  - [x]10.6 Verify no regressions from baseline (3,143 tests)

## Dev Notes

### Architecture Patterns (CRITICAL -- must follow)

**FR41 maps to:** `investigator/kb/schemas.py` (validation_status field), `ui/services/kb_surfacing_service.py` (weighting logic) [Source: architecture.md line 1428]

**Weighting reconciliation:** The epic specifies relative multipliers (1.0x, 0.9x, 0.8x, 0.6x) which normalize the top weight to 1.0. The existing implementation used absolute multipliers (3.0, 2.0, 1.0). Story 6-4 adopts the epic's normalized multiplier scheme as it is more intuitive and clearly documented.

**Dual weighting locations:** Validation weighting must be applied in TWO places:
1. `KBSurfacingService.surface_entries()` — UI-side surfacing during live investigations (already has composite scoring structure)
2. `KBQueryStep.execute()` — Investigator-side KB query during autonomous investigation (currently NO weighting)

**Confirmation vs. Correction distinction:**
- "Confirm" (AC2): Changes status to `human-confirmed`. SRE says "this AI-generated entry is accurate." Content stays the same.
- "Correct" (AC3): Changes status to `corrected`. SRE modifies the content. Existing edit route handles content changes — just needs to set `validation_status="corrected"` on content edits.

**Version snapshot pattern:** Always call `_save_version_snapshot()` BEFORE overwriting the Qdrant point. This is the established pattern in `update_entry()` (line 1341) and `create_entry()` (line 1176).

### Existing Code to Reuse (DO NOT RECREATE)

| Component | Location | What to Reuse |
|-----------|----------|---------------|
| VALIDATION_WEIGHTS dict | `ui/beeper_ui/services/kb_surfacing_service.py:25` | Update values, don't restructure |
| _derive_validation_status() | `ui/beeper_ui/services/kb_surfacing_service.py:222` | Add field-first logic, keep fallback |
| _compute_validation_weight() | `ui/beeper_ui/services/kb_surfacing_service.py:238` | Keep lookup pattern, update docstring |
| surface_entries() composite scoring | `ui/beeper_ui/services/kb_surfacing_service.py:165-189` | Don't change scoring structure |
| _save_version_snapshot() | `ui/beeper_ui/services/kb_service.py:881` | Extend with validation_status field |
| update_entry() | `ui/beeper_ui/services/kb_service.py:1254` | Add validation_status param |
| edit route handler | `ui/beeper_ui/routes/knowledge.py:861` | Add validation_status pass-through |
| KBEntry dataclass | `ui/beeper_ui/services/kb_service.py:83` | Already has validation_status field |
| KnowledgeEntry schema | `investigator/beeper_investigator/kb/schemas.py:48` | Already has validation_status field |
| SearchResult schema | `investigator/beeper_investigator/kb/schemas.py:81` | payload dict already contains validation_status |
| VALID_VALIDATION_STATUSES | `ui/beeper_ui/routes/knowledge.py:44` | Already includes all 4 statuses |
| EXACT_MATCH_THRESHOLD | `investigator/beeper_investigator/steps/kb_query.py:21` | Keep using raw scores for this |
| get_kb_service() | `ui/beeper_ui/routes/knowledge.py:101` | Factory for confirm route |
| sanitize_query() | `ui/beeper_ui/routes/knowledge.py:60` | Sanitize entry_id in confirm route |
| _make_kb_entry() test helper | `ui/tests/test_kb_surfacing_service.py:18` | Extend with validation_status param |
| _make_result() test helper | `investigator/tests/test_kb_query.py` | Extend with validation_status in payload |

### Anti-Patterns to AVOID

- Do NOT change the semantic similarity search itself — only apply weighting AFTER retrieval
- Do NOT apply validation weighting to investigation results (they don't have validation_status)
- Do NOT modify `EXACT_MATCH_THRESHOLD` or its usage — keep it based on raw cosine similarity
- Do NOT create a new Qdrant collection for validation state — use existing `validation_status` field in `knowledge` collection
- Do NOT create a new service class — extend existing `KBService` and `KBSurfacingService`
- Do NOT create a separate confirmation model/schema — reuse the existing Qdrant payload pattern
- Do NOT allow confirming entries that are already `human-confirmed`, `proven`, or `corrected`
- Do NOT break the existing `record_relevance_feedback()` method — it's about surfacing feedback, not validation status
- Do NOT change the operator component — no Rust changes needed
- Do NOT duplicate the VALIDATION_WEIGHTS between investigator and UI — they are independent but use the same values

### Previous Story Intelligence (6-3)

**Key learnings from Story 6-3 (Per-Service Knowledge Views):**
- `VALID_VALIDATION_STATUSES` constant was extracted during 6-3 code review (line 44 in routes/knowledge.py) — reuse it for validation
- `get_service_validation_counts()` uses `with_payload=["validation_status"]` for efficient counting — good pattern reference
- Code review found hardcoded validation statuses as an issue — use constants consistently
- Test pattern: mock `KBService` methods in route tests, mock Qdrant client in service tests
- 3,143 tests pass across all components (941 investigator + 1,671 UI + 531 operator) — baseline for regression

**Patterns from 6-3 implementation:**
- Route pattern: `@knowledge_bp.route("/...")` with `get_kb_service()` factory
- Version snapshots: `_save_version_snapshot()` called BEFORE Qdrant upsert
- Flash messages: `flash("message", "success")` or `flash("message", "error")` with redirect
- Service method pattern: Qdrant scroll → filter → parse payload → return typed results

### Testing Standards

- **Framework:** pytest with unittest.mock for Qdrant client, KBService, EmbeddingService
- **Test locations:**
  - `ui/tests/test_kb_surfacing_service.py` — update existing weight tests + new derive tests
  - `ui/tests/test_kb_service.py` — new confirm_entry + update_entry validation_status tests
  - `ui/tests/test_routes_knowledge.py` — new confirm route tests
  - `investigator/tests/test_kb_query.py` — new validation weighting tests
- **Mocking patterns:**
  - `unittest.mock.patch("beeper_ui.services.kb_surfacing_service.KBService")` for surfacing service tests
  - `unittest.mock.patch.object(kb_service, "client")` for KBService Qdrant mocking
  - `unittest.mock.patch("beeper_investigator.steps.kb_query.KBClient")` for investigator KB tests
- **Coverage:** All weight values, all status transitions, fallback behavior, confirm happy/error paths, edit with content change setting corrected, format output includes status

### Project Structure Notes

**Files to CREATE:**
- None (all changes are modifications to existing files)

**Files to MODIFY:**
- `ui/beeper_ui/services/kb_surfacing_service.py` — Update VALIDATION_WEIGHTS, _derive_validation_status(), _compute_validation_weight() docstring
- `ui/beeper_ui/services/kb_service.py` — Add confirm_entry() method, add validation_status to _save_version_snapshot(), add validation_status param to update_entry()
- `ui/beeper_ui/routes/knowledge.py` — Add POST confirm route, pass validation_status="corrected" on content edits
- `ui/beeper_ui/templates/knowledge/entry.html` — Add "Confirm as Accurate" button for AI-generated entries
- `investigator/beeper_investigator/steps/kb_query.py` — Add VALIDATION_WEIGHTS, _apply_validation_weighting(), update _format_results()
- `ui/tests/test_kb_surfacing_service.py` — Update weight tests, add derive tests, update ranking test
- `ui/tests/test_kb_service.py` — Add confirm_entry tests, update_entry validation_status tests
- `ui/tests/test_routes_knowledge.py` — Add confirm route tests
- `investigator/tests/test_kb_query.py` — Add validation weighting tests

**Files to NOT touch:**
- `investigator/beeper_investigator/kb/schemas.py` — validation_status field already exists
- `investigator/beeper_investigator/kb/client.py` — search methods already return full payload
- `investigator/beeper_investigator/kb/auto_creation.py` — already sets validation_status="AI-generated"
- `operator/**` — No operator changes needed
- `ui/beeper_ui/services/correction_service.py` — Corrections service is separate (story 6-5 territory)
- `ui/beeper_ui/templates/knowledge/service_knowledge.html` — Service views unchanged
- `ui/beeper_ui/templates/knowledge/index.html` — KB index unchanged
- `ui/beeper_ui/templates/knowledge/_entry_card.html` — Entry cards unchanged
- `ui/beeper_ui/templates/knowledge/_filter_panel.html` — Filter panel unchanged

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 6.4] — Acceptance criteria and story statement (lines 1187-1208)
- [Source: _bmad-output/planning-artifacts/architecture.md#FR41] — `investigator/kb/schemas.py` (validation_status field) (line 1428)
- [Source: ui/beeper_ui/services/kb_surfacing_service.py:25-30] — Current VALIDATION_WEIGHTS dict
- [Source: ui/beeper_ui/services/kb_surfacing_service.py:222-236] — Current _derive_validation_status() method
- [Source: ui/beeper_ui/services/kb_surfacing_service.py:238-250] — Current _compute_validation_weight() method
- [Source: ui/beeper_ui/services/kb_surfacing_service.py:165-189] — Composite scoring in surface_entries()
- [Source: ui/beeper_ui/services/kb_service.py:881-905] — _save_version_snapshot() pattern
- [Source: ui/beeper_ui/services/kb_service.py:1254-1346] — update_entry() method
- [Source: ui/beeper_ui/services/kb_service.py:99] — KBEntry.validation_status field
- [Source: ui/beeper_ui/routes/knowledge.py:44] — VALID_VALIDATION_STATUSES constant
- [Source: ui/beeper_ui/routes/knowledge.py:861] — Edit route handler
- [Source: investigator/beeper_investigator/steps/kb_query.py:21] — EXACT_MATCH_THRESHOLD constant
- [Source: investigator/beeper_investigator/steps/kb_query.py:66-82] — _format_results() method
- [Source: investigator/beeper_investigator/steps/kb_query.py:106-218] — KBQueryStep.execute() method
- [Source: investigator/beeper_investigator/kb/schemas.py:62-65] — validation_status field on KnowledgeEntry
- [Source: investigator/beeper_investigator/kb/schemas.py:81-87] — SearchResult model with payload dict
- [Source: _bmad-output/implementation-artifacts/6-3-per-service-knowledge-views.md] — Previous story with version snapshot patterns
- [Source: ui/tests/test_kb_surfacing_service.py:18-41] — _make_kb_entry() test helper
- [Source: ui/tests/test_kb_surfacing_service.py:73-109] — Existing validation weight and derive tests

## Dev Agent Record

### Agent Model Used

claude-opus-4-6

### Debug Log References

### Completion Notes List

- Updated `VALIDATION_WEIGHTS` in `KBSurfacingService` to normalized multipliers: proven=1.0, human-confirmed=0.9, corrected=0.8, AI-generated=0.6. Updated `DEFAULT_VALIDATION_WEIGHT` to 0.6.
- Rewrote `_derive_validation_status()` to read `entry.validation_status` field directly, falling back to entry_type derivation only when field is None.
- Added `VALIDATION_WEIGHTS` and `_apply_validation_weighting()` function to investigator `KBQueryStep`. Applied to knowledge results after search but before LLM synthesis.
- Updated `_format_results()` to include validation_status in LLM prompt context.
- Added `confirm_entry()` method to `KBService` — changes AI-generated entries to human-confirmed with version snapshot and user/timestamp tracking.
- Added `validation_status` parameter to `update_entry()` in `KBService`.
- Added `validation_status` field to `_save_version_snapshot()` for version history tracking of status changes.
- Wired edit route to automatically set `validation_status="corrected"` when content changes are detected.
- Added `POST /knowledge/<entry_id>/confirm` route for SRE confirmation flow.
- Added "Confirm as Accurate" button to entry.html (visible only for AI-generated entries).
- Added validation_status badge to entry detail page metadata.
- 27 new tests: 11 investigator (validation weighting + format), 16 UI (6 surfacing + 6 KBService + 5 route)
- All 3,170 tests pass (952 investigator + 1,687 UI + 531 operator)

### Change Log

- 2026-03-17: Implemented story 6-4 — KB entry validation weighting with normalized multipliers, field-first status derivation, investigator-side weighting, SRE confirmation flow, and correction status wiring

### File List

- ui/beeper_ui/services/kb_surfacing_service.py (MODIFIED) — Updated VALIDATION_WEIGHTS to normalized multipliers, added "corrected" status, rewrote _derive_validation_status() to read field first
- ui/beeper_ui/services/kb_service.py (MODIFIED) — Added confirm_entry() method, added validation_status param to update_entry(), added validation_status to _save_version_snapshot()
- ui/beeper_ui/routes/knowledge.py (MODIFIED) — Added POST confirm route, added flask imports (flash, redirect, url_for), wired edit route to set validation_status="corrected" on content changes
- ui/beeper_ui/templates/knowledge/entry.html (MODIFIED) — Added "Confirm as Accurate" button for AI-generated entries, added validation_status badge to metadata
- investigator/beeper_investigator/steps/kb_query.py (MODIFIED) — Added VALIDATION_WEIGHTS, _apply_validation_weighting(), updated _format_results() with status
- ui/tests/test_kb_surfacing_service.py (MODIFIED) — Updated weight/derive tests for new values, added corrected/field-based derive tests, updated ranking test
- ui/tests/test_kb_service.py (MODIFIED) — Added TestConfirmEntry (4 tests), TestUpdateEntryValidationStatus (2 tests)
- ui/tests/test_routes_knowledge.py (MODIFIED) — Added TestConfirmEntryRoute (5 tests)
- investigator/tests/test_kb_query.py (MODIFIED) — Added TestValidationWeighting (7 tests), TestKBQueryStepValidationWeighting (2 tests), format status tests (2 tests)
- _bmad-output/implementation-artifacts/6-4-kb-entry-validation-weighting.md (MODIFIED) — Story file
- _bmad-output/implementation-artifacts/sprint-status.yaml (MODIFIED) — Story status updates
