# Story 6.5: KB Entry Review, Edit & Correction

Status: review

## Story

As a **user**,
I want to review, edit, and correct Beeper's KB entries as a feedback mechanism,
so that I can fix errors and improve the quality of Beeper's institutional knowledge.

## Acceptance Criteria

1. **Given** a user views a KB entry detail page (`/knowledge/{id}`) **When** the user clicks "Edit" **Then** an inline editor allows modifying the entry's content, tags, and category **And** the edit is saved as a new version in `knowledge_versions` with the editor and timestamp

2. **Given** a user edits a KB entry **When** the edit is saved **Then** the validation_status is updated to "corrected" if content changed, or preserved if only tags changed **And** the `corrections` collection records the diff for learning purposes

3. **Given** a KB entry with version history **When** a user clicks "History" **Then** all versions are displayed with diffs, authors, and timestamps **And** the user can revert to a previous version

## Tasks / Subtasks

- [x] Task 1: Add `entry_type` parameter to `update_entry()` in `KBService` (AC: #1)
  - [x] 1.1 In `ui/beeper_ui/services/kb_service.py`, add `entry_type: Optional[str] = None` parameter to `update_entry()` (line 1255). In the payload construction (line 1328), if `entry_type` is provided, use it; otherwise preserve existing via `existing_payload.get("entry_type", "unknown")`.

- [x] Task 2: Add category (entry_type) dropdown to edit form (AC: #1)
  - [x] 2.1 In `ui/beeper_ui/routes/knowledge.py`, in the `kb_edit()` GET handler (line 881), add `entry_types` to the template context by calling `service_client.get_entry_types()`. Also include "proven_fix" in the list if not already present (the per-service knowledge view groups by it).
  - [x] 2.2 In `ui/beeper_ui/templates/knowledge/edit.html`, add a "Category" select dropdown in the `edit-metadata` section alongside Service and Tags. Options come from `entry_types` template variable. Pre-select the current `entry.entry_type`.
  - [x] 2.3 In `ui/beeper_ui/routes/knowledge.py`, in the `kb_edit()` POST handler (line 912), read `entry_type` from `request.form.get("entry_type")` and pass it to `service_client.update_entry()`.

- [x] Task 3: Record edit diffs in corrections collection (AC: #2)
  - [x] 3.1 In `ui/beeper_ui/routes/knowledge.py`, in the `kb_edit()` POST handler, after a successful `update_entry()` call where content was changed (`new_validation_status == "corrected"`), create a correction record. Call `service_client.create_correction(entry_id=entry_id, user_message=f"Manual edit: {_describe_changes(current_entry, title, content, tags, entry_type)}", author="edit")`. Set the correction status to "applied" immediately since the edit is already saved.
  - [x] 3.2 Add a helper function `_describe_edit_changes(original_entry, new_title, new_content, new_tags, new_entry_type)` in `knowledge.py` that generates a human-readable description of what changed (e.g., "Title changed, Content updated (342 chars added), Tags updated"). Reuse the diff approach from `_compute_change_summaries()`.

- [x] Task 4: Add "Restore" button to version history page (AC: #3)
  - [x] 4.1 In `ui/beeper_ui/templates/knowledge/history.html`, add a "Restore" button for each non-current version in the `version-actions` div. Use HTMX to POST to the existing `kb_restore` route. Include a `#restore-result` div at the bottom of the history page to display restore results.

- [x] Task 5: Write unit tests for `update_entry()` entry_type parameter (AC: #1)
  - [x] 5.1 In `ui/tests/test_kb_service.py`, add `TestUpdateEntryEntryType` class: test that passing `entry_type="runbook"` updates the field in the payload, test that omitting `entry_type` preserves existing value.

- [x] Task 6: Write route tests for category editing and correction recording (AC: #1, #2)
  - [x] 6.1 In `ui/tests/test_routes_knowledge.py`, add `TestEditEntryType` class: test that GET edit includes `entry_types` in context, test that POST edit with `entry_type` passes it to `update_entry()`.
  - [x] 6.2 Add `TestEditCorrectionRecording` class: test that when content changes, a correction is created in the corrections collection, test that when only tags change, no correction is recorded.

- [x] Task 7: Write route tests for history page restore button (AC: #3)
  - [x] 7.1 In `ui/tests/test_routes_knowledge.py`, add `TestHistoryRestoreButton` class: test that history page response contains "Restore" button for non-current versions.

- [x] Task 8: Run full test suite across all components (AC: all)
  - [x] 8.1 Run investigator tests: `cd investigator && poetry run python -m pytest` — 952 passed
  - [x] 8.2 Run investigator linting: `cd investigator && poetry run ruff check .` — All checks passed
  - [x] 8.3 Run investigator type checking: `cd investigator && poetry run mypy .` — 8 pre-existing import stubs, clean
  - [x] 8.4 Run UI tests: `cd ui && poetry run python -m pytest` — 1,698 passed
  - [x] 8.5 Run operator tests: `cd operator && cargo test` — 531 passed
  - [x] 8.6 Verify no regressions from baseline (3,174 tests) — 3,181 total (7 new tests added)

## Dev Notes

### Architecture Patterns (CRITICAL -- must follow)

**FR42 maps to:** `ui/routes/knowledge.py`, `ui/services/correction_service.py` (existing) [Source: architecture.md line 1429]

**What already exists (DO NOT rebuild):**
- Edit route at `/knowledge/<entry_id>/edit` — full GET/POST with HTMX, markdown preview, optimistic concurrency. Editing title, content, service, tags.
- Version history at `/knowledge/<entry_id>/history` — lists versions with change summaries, authors, timestamps
- Version detail at `/knowledge/<entry_id>/version/<num>` — view any version with prev/next navigation
- Diff comparison at `/knowledge/<entry_id>/diff/<from>/<to>` — unified diff with hunks
- Restore at `/knowledge/<entry_id>/restore/<num>` (POST) — creates new version from old content
- Corrections collection infrastructure — `create_correction()`, `update_correction()` in KBService
- validation_status="corrected" auto-set on content changes (story 6-4)
- Version snapshots via `_save_version_snapshot()` before every update

**What this story adds:**
1. Category (entry_type) editing in the edit form
2. Correction recording on manual edits (diff saved in corrections collection)
3. Restore button on history page (button exists on version detail page already)

### Existing Code to Reuse (DO NOT RECREATE)

| Component | Location | What to Reuse |
|-----------|----------|---------------|
| update_entry() | `ui/beeper_ui/services/kb_service.py:1255` | Add entry_type param |
| kb_edit() route | `ui/beeper_ui/routes/knowledge.py:861` | Add entry_type + correction logic |
| get_entry_types() | `ui/beeper_ui/services/kb_service.py:808` | Provides entry type list |
| create_correction() | `ui/beeper_ui/services/kb_service.py:1459` | Create correction record on edit |
| update_correction() | `ui/beeper_ui/services/kb_service.py:1653` | Set status to "applied" |
| _compute_change_summaries() | `ui/beeper_ui/routes/knowledge.py:509` | Pattern for describing changes |
| generate_diff() | `ui/beeper_ui/services/kb_service.py:249` | Generate content diff |
| kb_restore() route | `ui/beeper_ui/routes/knowledge.py:800` | Already exists, wire to history page |
| edit.html template | `ui/beeper_ui/templates/knowledge/edit.html` | Add category dropdown |
| history.html template | `ui/beeper_ui/templates/knowledge/history.html` | Add restore button |
| VALID_ENTRY_TYPES | `ui/beeper_ui/routes/knowledge.py:42` | May need expanding for proven_fix |
| _save_version_snapshot() | `ui/beeper_ui/services/kb_service.py:881` | Already handles snapshots |

### Anti-Patterns to AVOID

- Do NOT recreate the edit form — enhance the existing one
- Do NOT create a new inline editor component — the existing HTMX edit form is the "inline editor"
- Do NOT create a new version history system — everything exists
- Do NOT create a separate corrections service for manual edits — use existing create_correction()
- Do NOT change the corrections collection schema — use existing fields
- Do NOT change the version snapshot format — it already includes all needed fields
- Do NOT modify the investigator component — no changes needed
- Do NOT modify the operator component — no Rust changes needed
- Do NOT add JavaScript — maintain the CSS-only + HTMX pattern

### Previous Story Intelligence (6-4)

**Key learnings from Story 6-4 (KB Entry Validation Weighting):**
- validation_status="corrected" is already set on content changes in edit route (line 955-963)
- `update_entry()` already supports `validation_status` parameter (line 1264)
- `_save_version_snapshot()` already includes validation_status (added in 6-4)
- 3,174 tests pass across all components (952 investigator + 1,691 UI + 531 operator) — baseline for regression
- Pattern: `get_entry()` should be called to get `current_entry` before detecting changes
- The edit route already has concurrency checking via version field
- Route tests mock `get_kb_service()` and assert template context variables

### Testing Standards

- **Framework:** pytest with unittest.mock for Qdrant client, KBService
- **Test locations:**
  - `ui/tests/test_kb_service.py` — update_entry entry_type tests
  - `ui/tests/test_routes_knowledge.py` — edit entry_type, correction recording, history restore
- **Mocking patterns:**
  - `unittest.mock.patch("beeper_ui.routes.knowledge.get_kb_service")` for route tests
  - `unittest.mock.patch.object(kb_service, "client")` for KBService Qdrant mocking

### Project Structure Notes

**Files to CREATE:**
- None (all changes are modifications to existing files)

**Files to MODIFY:**
- `ui/beeper_ui/services/kb_service.py` — Add entry_type param to update_entry()
- `ui/beeper_ui/routes/knowledge.py` — Add entry_type to edit GET context + POST handler, record correction on edit
- `ui/beeper_ui/templates/knowledge/edit.html` — Add category dropdown
- `ui/beeper_ui/templates/knowledge/history.html` — Add restore button per non-current version
- `ui/tests/test_kb_service.py` — entry_type update tests
- `ui/tests/test_routes_knowledge.py` — edit entry_type, correction recording, history restore tests

**Files to NOT touch:**
- `investigator/**` — No investigator changes needed
- `operator/**` — No operator changes needed
- `ui/beeper_ui/services/correction_service.py` — LLM-powered corrections are separate; manual edits use KBService directly
- `ui/beeper_ui/services/kb_surfacing_service.py` — No surfacing changes
- `ui/beeper_ui/templates/knowledge/entry.html` — Entry detail page unchanged
- `ui/beeper_ui/templates/knowledge/version.html` — Already has restore button
- `ui/beeper_ui/templates/knowledge/diff.html` — Diff page unchanged

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 6.5] — Acceptance criteria and story statement (lines 1210-1231)
- [Source: _bmad-output/planning-artifacts/architecture.md#FR42] — KB edit/correct routes (line 1429)
- [Source: ui/beeper_ui/services/kb_service.py:1255-1356] — update_entry() method
- [Source: ui/beeper_ui/services/kb_service.py:808-827] — get_entry_types() method
- [Source: ui/beeper_ui/services/kb_service.py:1459-1513] — create_correction() method
- [Source: ui/beeper_ui/services/kb_service.py:1653-1714] — update_correction() method
- [Source: ui/beeper_ui/services/kb_service.py:249] — generate_diff() function
- [Source: ui/beeper_ui/routes/knowledge.py:861-987] — kb_edit() route handler
- [Source: ui/beeper_ui/routes/knowledge.py:800-858] — kb_restore() route handler
- [Source: ui/beeper_ui/routes/knowledge.py:509-541] — _compute_change_summaries()
- [Source: ui/beeper_ui/routes/knowledge.py:42] — VALID_ENTRY_TYPES constant
- [Source: ui/beeper_ui/templates/knowledge/edit.html] — Current edit form template
- [Source: ui/beeper_ui/templates/knowledge/history.html] — Current history template
- [Source: _bmad-output/implementation-artifacts/6-4-kb-entry-validation-weighting.md] — Previous story with validation_status wiring

## Dev Agent Record

### Agent Model Used

claude-opus-4-6

### Debug Log References

### Completion Notes List

- Added `entry_type: Optional[str] = None` parameter to `update_entry()` in KBService. When provided, updates the entry's category; when omitted, preserves existing entry_type.
- Added Category (entry_type) dropdown to edit form in `edit.html`. Populated via `get_entry_types()` with `proven_fix` always included. Pre-selects current entry type.
- Added `entry_types` to edit route GET handler template context and `new_entry_type` reading in POST handler, passed through to `update_entry()`.
- Added correction recording on content-changing edits: creates a correction record via `create_correction()` with a human-readable change description, immediately set to "applied" status.
- Added `_describe_edit_changes()` helper function to generate change descriptions (title changed, content updated with char diff, tags updated, category changed).
- Added "Restore" button to version history page for each non-current version, with HTMX POST to existing `kb_restore` route and result div.
- 7 new tests: 2 KBService entry_type tests + 2 edit entry_type route tests + 2 correction recording tests + 1 history restore button test.
- All 3,181 tests pass (952 investigator + 1,698 UI + 531 operator) — zero regressions from 3,174 baseline.

### Change Log

- 2026-03-17: Implemented story 6-5 — KB Entry Review, Edit & Correction with category editing, correction recording on edits, and restore button on history page

### File List

- ui/beeper_ui/services/kb_service.py (MODIFIED) — Added entry_type parameter to update_entry()
- ui/beeper_ui/routes/knowledge.py (MODIFIED) — Added entry_types to edit GET context, entry_type in POST handler, correction recording on content edits, _describe_edit_changes() helper
- ui/beeper_ui/templates/knowledge/edit.html (MODIFIED) — Added Category dropdown in edit-metadata section
- ui/beeper_ui/templates/knowledge/history.html (MODIFIED) — Added Restore button for non-current versions with HTMX and restore-result div
- ui/tests/test_kb_service.py (MODIFIED) — Added TestUpdateEntryEntryType (2 tests)
- ui/tests/test_routes_knowledge.py (MODIFIED) — Added TestEditEntryType (2 tests), TestEditCorrectionRecording (2 tests), TestHistoryRestoreButton (1 test)
- _bmad-output/implementation-artifacts/6-5-kb-entry-review-edit-correction.md (MODIFIED) — Story file
- _bmad-output/implementation-artifacts/sprint-status.yaml (MODIFIED) — Story status updates
