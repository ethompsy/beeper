# Story 5.2: Beeper Revision Processing

Status: done

## Story

As **Beeper**,
I want to revise Knowledge Base entries based on conversational corrections,
so that the KB reflects accurate, human-validated information.

## Acceptance Criteria

1. **Given** an SRE submits a conversational correction, **When** Beeper processes it, **Then** Beeper understands the intent and generates a revision (FR19), **And** the revision is shown to the SRE for approval before applying.

2. **Given** Beeper generates a revision, **When** the SRE reviews it, **Then** the SRE sees:
   - Original content
   - Proposed revision
   - Diff highlighting changes
   - "Apply" or "Revise further" options

3. **Given** the SRE approves the revision, **When** applying the change, **Then** the KB entry is updated, **And** a new version is created with attribution, **And** the correction is logged for learning.

4. **Given** the revision needs adjustment, **When** the SRE provides additional feedback, **Then** Beeper refines the revision, **And** the cycle continues until approved.

## Tasks / Subtasks

- [x] Task 1: Add revision generation to CorrectionService (AC: #1)
  - [x]1.1 Add `generate_revision(entry_content, entry_title, correction_messages)` method to `CorrectionService` — LLM prompt takes original content + full correction conversation and returns revised content as plain text
  - [x]1.2 Add `refine_revision(entry_content, entry_title, correction_messages, previous_revision, feedback)` method — takes prior revision + user feedback and returns improved revision
  - [x]1.3 Add REVISION_SYSTEM_PROMPT_TEMPLATE and REFINE_SYSTEM_PROMPT_TEMPLATE constants
  - [x]1.4 Write unit tests for both methods (mock litellm, test prompt construction, test response handling)

- [x] Task 2: Create revision generation route (AC: #1, #2)
  - [x]2.1 Add `POST /knowledge/<entry_id>/corrections/<correction_id>/revision` route to `knowledge.py` — calls `generate_revision()`, then `generate_diff()` to produce diff data
  - [x]2.2 Validate: entry exists, correction exists and belongs to entry, correction status is "pending"
  - [x]2.3 Return `_revision_panel.html` partial with: original content, proposed revision, diff data, correction_id
  - [x]2.4 Write route tests with mocked LLM and Qdrant

- [x] Task 3: Build revision panel UI (AC: #2)
  - [x]3.1 Create `templates/knowledge/_revision_panel.html` partial — shows diff (reuse diff rendering pattern from `diff.html`), "Apply" button, "Revise Further" textarea + submit
  - [x]3.2 Add "Generate Revision" button to `_correction_response.html` — appears after correction acknowledgment, uses `hx-post` to revision route
  - [x]3.3 Add `hx-indicator` for "Generating revision..." loading state
  - [x]3.4 Add CSS for revision panel (use existing diff styles from `main.css`)

- [x] Task 4: Implement approval workflow (AC: #3)
  - [x]4.1 Add `POST /knowledge/<entry_id>/corrections/<correction_id>/apply` route — calls `KBService.update_entry()` with revised content and author="correction", then `update_correction(status="applied")`
  - [x]4.2 Ensure `update_entry()` creates version snapshot (already automatic via `_save_version_snapshot`)
  - [x]4.3 Return `_revision_result.html` partial with success message, link to updated entry, and link to version diff
  - [x]4.4 Create `templates/knowledge/_revision_result.html` partial
  - [x]4.5 Write route tests for apply flow (success, entry not found, correction not found, already applied)

- [x] Task 5: Implement "Revise Further" flow (AC: #4)
  - [x]5.1 Add `POST /knowledge/<entry_id>/corrections/<correction_id>/revision/refine` route — calls `refine_revision()` with user feedback, regenerates diff
  - [x]5.2 Store feedback as additional correction message via `add_correction_message()`
  - [x]5.3 Return updated `_revision_panel.html` with new diff
  - [x]5.4 Write route tests for refinement cycle

- [x] Task 6: Integration testing and polish
  - [x]6.1 Test full flow: correction → generate revision → view diff → apply → verify entry updated + version created
  - [x]6.2 Test refinement flow: generate revision → revise further → refine → apply
  - [x]6.3 Test error cases: LLM unavailable, entry not found, correction not found, correction already applied, empty feedback
  - [x]6.4 Verify no regressions in existing correction routes and KB routes
  - [x]6.5 Run ruff + mypy on all changed files

## Dev Notes

### Architecture & Data Flow

**Revision Flow:**
1. User has a pending correction (from story 5-1) → clicks "Generate Revision"
2. `hx-post` to `/knowledge/<entry_id>/corrections/<correction_id>/revision`
3. Route loads entry content + correction messages → calls `CorrectionService.generate_revision()`
4. LLM returns revised entry content as plain text
5. Route calls `KBService.generate_diff(original_content, revised_content)` to produce diff data
6. Returns `_revision_panel.html` with diff display + approval controls
7. User clicks "Apply" → `hx-post` to `.../apply` → `KBService.update_entry()` + `update_correction(status="applied")`
8. Or user provides feedback → `hx-post` to `.../revision/refine` → `CorrectionService.refine_revision()` → new diff

**Key Integration Points:**
- `CorrectionService.generate_revision()` — NEW method, follows same litellm pattern as `process_correction()`
- `KBService.generate_diff()` — EXISTING at `kb_service.py:174-263`, returns `{"hunks": [...], "has_changes": bool, "summary": str}`
- `KBService.update_entry()` — EXISTING at `kb_service.py:942-1057`, auto-creates version snapshot, increments version
- `KBService.update_correction()` — EXISTING at `kb_service.py:1253-1314`, updates status to "applied"
- `KBService.get_correction()` — EXISTING at `kb_service.py:1152-1189`, returns Correction or None
- `KBService.add_correction_message()` — EXISTING at `kb_service.py:1191-1251`, appends message to correction

### Existing Code to Reuse (DO NOT RECREATE)

| Component | Location | What to Reuse |
|-----------|----------|---------------|
| CorrectionService (LLM patterns) | `ui/beeper_ui/services/correction_service.py` | `_complete_sync()`, `_parse_response()`, prompt template pattern, singleton pattern |
| generate_diff() | `ui/beeper_ui/services/kb_service.py:174-263` | Line-by-line diff with hunks structure |
| update_entry() | `ui/beeper_ui/services/kb_service.py:942-1057` | Updates entry, creates version snapshot, generates embedding |
| update_correction() | `ui/beeper_ui/services/kb_service.py:1253-1314` | Changes correction status to "applied" |
| get_correction() | `ui/beeper_ui/services/kb_service.py:1152-1189` | Loads correction by correction_id |
| add_correction_message() | `ui/beeper_ui/services/kb_service.py:1191-1251` | Appends feedback to correction conversation |
| Correction/CorrectionMessage | `ui/beeper_ui/services/kb_service.py:125-165` | Dataclasses for correction data |
| Diff rendering pattern | `ui/beeper_ui/templates/knowledge/diff.html` | CSS-only mode toggle, hunk rendering, line styling |
| Diff CSS styles | `ui/beeper_ui/static/css/main.css` | `.diff-*` classes for add/remove/context lines |
| Correction response template | `ui/beeper_ui/templates/knowledge/_correction_response.html` | Add "Generate Revision" button here |
| HTMX form patterns | `ui/beeper_ui/templates/knowledge/edit.html:34-38` | `hx-post`, `hx-target`, `hx-indicator` |
| Input sanitization | `ui/beeper_ui/routes/knowledge.py:48-70` | `sanitize_query()` for user input |
| EmbeddingService singleton | `ui/beeper_ui/services/embedding_service.py` | Required by `update_entry()` for new embedding |

### Anti-Patterns to Avoid

- **DO NOT** create a new diff implementation — reuse `KBService.generate_diff()` exactly
- **DO NOT** create a separate Flask Blueprint — add routes to existing `knowledge_bp`
- **DO NOT** use JavaScript for the diff display — reuse CSS-only patterns from `diff.html`
- **DO NOT** use async in Flask routes — use `CorrectionService._complete_sync()`
- **DO NOT** skip `finally: svc.close()` for service cleanup
- **DO NOT** use redirects after form submission — return HTMX partials (project convention)
- **DO NOT** hardcode URLs — use `url_for()` in templates
- **DO NOT** manually create version snapshots — `update_entry()` does this automatically
- **DO NOT** skip embedding regeneration — `update_entry()` requires `embedding_service` param

### HTMX Patterns to Follow

```html
<!-- Generate Revision button (add to _correction_response.html) -->
<button hx-post="{{ url_for('knowledge.kb_generate_revision', entry_id=entry_id, correction_id=correction.correction_id) }}"
        hx-target="#revision-panel"
        hx-swap="innerHTML"
        hx-indicator="#revision-loading"
        class="btn btn-primary">Generate Revision</button>
<span id="revision-loading" class="htmx-indicator">Generating revision...</span>

<!-- Apply Revision button (in _revision_panel.html) -->
<button hx-post="{{ url_for('knowledge.kb_apply_revision', entry_id=entry_id, correction_id=correction_id) }}"
        hx-target="#revision-panel"
        hx-swap="innerHTML"
        hx-confirm="Apply this revision to the KB entry?"
        class="btn btn-success">Apply Revision</button>

<!-- Revise Further form (in _revision_panel.html) -->
<form hx-post="{{ url_for('knowledge.kb_refine_revision', entry_id=entry_id, correction_id=correction_id) }}"
      hx-target="#revision-panel"
      hx-swap="innerHTML"
      hx-indicator="#refine-loading">
  <textarea name="feedback" placeholder="Describe what needs to change..." required></textarea>
  <button type="submit">Refine</button>
  <span id="refine-loading" class="htmx-indicator">Refining revision...</span>
</form>
```

### LLM Prompt Design

**Revision Generation Prompt:**
- System: "You are revising a Knowledge Base entry based on corrections. Apply the corrections to produce updated content. Return ONLY the revised content as plain text (not JSON). Preserve the original structure, formatting, and any sections not affected by corrections."
- User: Original entry content + correction conversation history
- Temperature: 0.0 for consistency
- max_tokens: 4096 (entries can be long)

**Revision Refinement Prompt:**
- System: Same as above but includes: "A previous revision was generated but needs adjustment based on additional feedback."
- User: Original content + corrections + previous revision + feedback
- Temperature: 0.0

### Testing Standards

- **Framework**: pytest with Flask test client
- **Mocking**: `unittest.mock.MagicMock` for Qdrant client, `unittest.mock.patch` for litellm
- **Test file**: `ui/tests/test_corrections.py` (extend existing file with new test classes)
- **Coverage expectations**: All routes tested for success and error paths
- **HTMX testing**: Test both full-page and `HX-Request: true` header responses
- **Error cases**: LLM unavailable (503), entry not found (404), correction not found (404), correction already applied (400), empty feedback (400)
- **Pattern**: Follow existing `TestCorrectionRoutes` class structure in `test_corrections.py`
- **Mock helpers**: Reuse existing `_make_correction_payload()` and `_make_entry()` from test_corrections.py

### Project Structure Notes

- All new routes in existing `ui/beeper_ui/routes/knowledge.py` (extend knowledge_bp)
- Extend `ui/beeper_ui/services/correction_service.py` with revision methods
- New templates: `ui/beeper_ui/templates/knowledge/_revision_panel.html`, `_revision_result.html`
- Modify template: `ui/beeper_ui/templates/knowledge/_correction_response.html` (add Generate Revision button)
- Extend tests: `ui/tests/test_corrections.py` (add revision test classes)
- CSS additions in existing `ui/beeper_ui/static/css/main.css` (minimal — mostly reuse diff styles)

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 5, Story 5.2]
- [Source: _bmad-output/planning-artifacts/prd.md#FR19]
- [Source: _bmad-output/planning-artifacts/architecture.md#Knowledge Base]
- [Source: ui/beeper_ui/services/correction_service.py - CorrectionService LLM patterns]
- [Source: ui/beeper_ui/services/kb_service.py:174-263 - generate_diff()]
- [Source: ui/beeper_ui/services/kb_service.py:942-1057 - update_entry()]
- [Source: ui/beeper_ui/services/kb_service.py:1152-1314 - correction methods]
- [Source: ui/beeper_ui/routes/knowledge.py - KB routes and correction routes]
- [Source: ui/beeper_ui/templates/knowledge/diff.html - diff rendering patterns]
- [Source: ui/tests/test_corrections.py - correction test patterns]
- [Source: _bmad-output/implementation-artifacts/5-1-conversational-corrections-interface.md - previous story context]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- Pre-existing mypy errors (2 in knowledge.py) unchanged; zero new errors introduced
- Pre-existing ruff line-length errors (3 in knowledge.py) unchanged; all new code passes clean

### Completion Notes List

- Added REVISION_SYSTEM_PROMPT_TEMPLATE and REFINE_SYSTEM_PROMPT_TEMPLATE to correction_service.py
- Added generate_revision() and refine_revision() methods to CorrectionService
- Added 3 new Flask routes: kb_generate_revision (POST), kb_apply_revision (POST), kb_refine_revision (POST)
- Created _revision_panel.html partial with diff display (reuses existing diff CSS) and approval/refine controls
- Created _revision_result.html partial with success message and navigation links
- Added "Generate Revision" button to _correction_response.html
- Added #revision-panel div to entry.html
- Added revision panel CSS styles to main.css
- 18 new tests: 4 service tests (generate_revision, refine_revision, error cases), 14 route tests (success, 404, 400, 503 for all 3 routes)
- All 470 tests pass (zero regressions)

### Change Log

- 2026-03-07: Implemented story 5-2 (Beeper Revision Processing) — all 6 tasks complete, 18 new tests
- 2026-03-07: Code review fixes — 5 issues found (1 HIGH, 3 MEDIUM, 1 LOW), 4 fixed: added entry_id mismatch validation to apply route, added status check to refine route, fixed stale messages in refine route, replaced sanitize_query with proper feedback truncation. Added 2 new tests (apply_revision_wrong_entry, refine_revision_already_applied). Total: 472 tests pass.

### File List

- ui/beeper_ui/services/correction_service.py (modified: added revision prompts, generate_revision, refine_revision methods)
- ui/beeper_ui/routes/knowledge.py (modified: added 3 revision routes)
- ui/beeper_ui/templates/knowledge/_revision_panel.html (new: diff display + approval/refine controls)
- ui/beeper_ui/templates/knowledge/_revision_result.html (new: success message after applying revision)
- ui/beeper_ui/templates/knowledge/_correction_response.html (modified: added Generate Revision button)
- ui/beeper_ui/templates/knowledge/entry.html (modified: added #revision-panel div)
- ui/beeper_ui/static/css/main.css (modified: added revision panel CSS)
- ui/tests/test_corrections.py (modified: added 18 revision tests)
