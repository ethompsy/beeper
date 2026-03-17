# Story 6.2: Bi-Directional KB-Investigation Links

Status: done

## Story

As the **system**,
I want KB entries linked bi-directionally to investigations and related entries,
so that navigating between knowledge and incidents is seamless in both directions.

## Acceptance Criteria

1. **Given** a KB entry created from investigation #42 **When** a user views the KB entry detail **Then** the entry shows a "Source Investigation" link that navigates to investigation #42 **And** "Contributing Investigations" lists all investigations that enriched this entry

2. **Given** a resolved investigation where a KB entry was created **When** a user views the investigation detail **Then** a "Knowledge Created" link navigates to the resulting KB entry **And** "Related Knowledge" shows entries that were referenced during the investigation

3. **Given** a KB entry is updated or corrected **When** the update is saved **Then** all bi-directional links are preserved and the link metadata includes the relationship type (source, related, supersedes)

## Tasks / Subtasks

- [x] Task 1: Extend `KnowledgeEntry` schema with link relationship metadata (AC: #3)
  - [x] 1.1 In `investigator/beeper_investigator/kb/schemas.py`, add `linked_investigations: list[dict] = Field(default_factory=list, description="Investigation links with relationship type")` to `KnowledgeEntry`. Each dict has: `investigation_id: str`, `relationship: str` (one of "source", "related", "supersedes"), `linked_at: str` (ISO 8601).
  - [x] 1.2 Keep existing `source_investigation_id` and `contributing_investigations` fields as-is for backward compatibility — the new `linked_investigations` is a richer, structured version used by the UI.

- [x] Task 2: Add `get_kb_entries_for_investigation()` method to `KBClient` (AC: #2)
  - [x] 2.1 In `investigator/beeper_investigator/kb/client.py`, add `get_kb_entries_for_investigation(self, investigation_id: str) -> list[SearchResult]` method. Scrolls `knowledge` collection filtering by `source_investigation_id == investigation_id` OR `contributing_investigations` array containing `investigation_id`. Returns all matching KB entries as `SearchResult` objects with full payload.
  - [x] 2.2 Add `get_entries_by_investigation_id(self, investigation_id: str) -> list[SearchResult]` method. Searches `knowledge` collection using `FieldCondition(key="source_investigation_id", match=MatchValue(value=investigation_id))`. This is the primary lookup for "Knowledge Created" links.

- [x] Task 3: Add bi-directional link service methods to `KBService` in UI (AC: #1, #2, #3)
  - [x] 3.1 In `ui/beeper_ui/services/kb_service.py`, add `get_source_investigation(self, entry_id: str) -> dict | None` method. Given a KB entry_id, retrieves the entry and returns `{"investigation_id": source_investigation_id, "relationship": "source"}` if `source_investigation_id` is set.
  - [x] 3.2 Add `get_contributing_investigations(self, entry_id: str) -> list[dict]` method. Returns list of `{"investigation_id": id, "relationship": "contributing"}` from the entry's `contributing_investigations` field.
  - [x] 3.3 Add `get_linked_kb_entries(self, investigation_id: str) -> list[KBEntry]` method. Scrolls `knowledge` collection for entries where `source_investigation_id == investigation_id` OR `investigation_id` is in `contributing_investigations`. Returns as `KBEntry` list.
  - [x] 3.4 Ensure `_update_entry_payload()` and correction application methods preserve `linked_investigations`, `source_investigation_id`, and `contributing_investigations` fields on update/edit (AC: #3).

- [x] Task 4: Populate `linked_investigations` during auto KB creation (AC: #3)
  - [x] 4.1 In `investigator/beeper_investigator/kb/auto_creation.py`, update `_create_new_entry()` to include `linked_investigations` in payload. Add `{"investigation_id": investigation_id, "relationship": "source", "linked_at": now}` for the source investigation.
  - [x] 4.2 Update `_enrich_existing_entry()` to append to `linked_investigations`. Add `{"investigation_id": investigation_id, "relationship": "related", "linked_at": now}` for contributing investigations. Deduplicate by `investigation_id`.

- [x] Task 5: Add "Source Investigation" and "Contributing Investigations" to KB entry detail page (AC: #1)
  - [x] 5.1 In `ui/beeper_ui/routes/knowledge.py`, update `kb_entry()` route to fetch source investigation and contributing investigations using new `KBService` methods. Pass `source_investigation` and `contributing_investigations` to template context.
  - [x] 5.2 In `ui/beeper_ui/templates/knowledge/entry.html`, add "Investigation Links" section after entry metadata. Show "Source Investigation" link navigating to `/investigations/<id>`. Show "Contributing Investigations" as a list of links. Use existing `service-badge` and `status-badge` CSS patterns.

- [x] Task 6: Add "Knowledge Created" link to investigation detail page (AC: #2)
  - [x] 6.1 In `ui/beeper_ui/routes/investigations.py`, add a new HTMX endpoint `/<investigation_id>/linked-kb` that calls `KBService.get_linked_kb_entries(investigation_id)` and renders `investigations/_linked_kb.html` partial.
  - [x] 6.2 Create `ui/beeper_ui/templates/investigations/_linked_kb.html` partial template. Display "Knowledge Created" section with links to KB entries created from this investigation, showing entry title, type badge, and validation status badge. Use existing `kb-entry-card` CSS patterns from `_related_kb.html`.
  - [x] 6.3 In `ui/beeper_ui/templates/investigations/_detail_content.html`, add a "Knowledge Created" section (using HTMX `hx-get` to load `/<investigation_id>/linked-kb`) right before the "Related Knowledge Base Entries" section. This distinguishes entries *created by* this investigation from entries *related to* it.

- [x] Task 7: Ensure link preservation on edit/correction (AC: #3)
  - [x] 7.1 In `ui/beeper_ui/services/kb_service.py`, verify `update_entry()` and related update methods include `linked_investigations`, `source_investigation_id`, and `contributing_investigations` in preserved payload fields. If any update logic replaces the full payload, ensure these link fields are always carried over.
  - [x] 7.2 In `ui/beeper_ui/services/correction_service.py`, verify correction application preserves bi-directional link fields. When a correction modifies a KB entry, link metadata must be preserved.

- [x] Task 8: Write unit tests for `KBClient` new methods (AC: #2)
  - [x] 8.1 In `investigator/tests/test_kb_client.py` (or create if needed), add `TestGetKBEntriesForInvestigation` — mock Qdrant scroll. Verify: returns entries with matching `source_investigation_id`. Verify: returns entries with investigation_id in `contributing_investigations`. Verify: returns empty list when no matches.
  - [x] 8.2 Add `TestGetEntriesByInvestigationId` — verify filter by `source_investigation_id` field condition.

- [x] Task 9: Write unit tests for `KBService` bi-directional link methods (AC: #1, #2, #3)
  - [x] 9.1 In `ui/tests/test_kb_service.py`, add `TestGetSourceInvestigation` — mock KB entry with `source_investigation_id` set. Verify: returns correct investigation link dict. Verify: returns None when no source_investigation_id.
  - [x] 9.2 Add `TestGetContributingInvestigations` — mock KB entry with `contributing_investigations` list. Verify: returns correctly formatted list.
  - [x] 9.3 Add `TestGetLinkedKBEntries` — mock Qdrant scroll. Verify: returns KBEntry list for matching investigation_id.
  - [x] 9.4 Add `TestLinkPreservationOnUpdate` — update a KB entry with new content. Verify: `linked_investigations`, `source_investigation_id`, `contributing_investigations` are preserved.

- [x] Task 10: Write UI route tests (AC: #1, #2)
  - [x] 10.1 In `ui/tests/test_routes_knowledge.py`, add `TestKBEntryDetailLinks` — verify entry detail page passes source_investigation and contributing_investigations to template context.
  - [x] 10.2 In `ui/tests/test_routes_investigations.py`, add `TestLinkedKBEndpoint` — mock `KBService.get_linked_kb_entries()`. Verify: endpoint returns rendered HTML with KB entry links. Verify: empty state when no linked entries.

- [x] Task 11: Write tests for auto_creation.py link population (AC: #3)
  - [x] 11.1 In `investigator/tests/test_auto_kb_creation.py`, add `TestLinkedInvestigationsOnCreate` — verify `_create_new_entry()` includes `linked_investigations` with source relationship. Verify structure: `{"investigation_id": ..., "relationship": "source", "linked_at": ...}`.
  - [x] 11.2 Add `TestLinkedInvestigationsOnEnrich` — verify `_enrich_existing_entry()` appends to `linked_investigations` with "related" relationship. Verify deduplication by investigation_id.

- [x] Task 12: Run full test suite across all components (AC: all)
  - [x] 12.1 Run investigator tests: `cd investigator && poetry run python -m pytest`
  - [x] 12.2 Run investigator linting: `cd investigator && poetry run ruff check .`
  - [x] 12.3 Run investigator type checking: `cd investigator && poetry run mypy .`
  - [x] 12.4 Run UI tests: `cd ui && poetry run python -m pytest`
  - [x] 12.5 Run operator tests: `cd operator && cargo test`
  - [x] 12.6 No regressions found

## Dev Notes

### Architecture Patterns (CRITICAL — must follow)

**FR39 maps to:** `investigator/kb/schemas.py`, `investigator/kb/client.py` (per architecture.md line 1426)
**UI extensions:** `ui/routes/knowledge.py` (extended with bi-directional links), `ui/services/kb_service.py` (extended with bi-directional links), `ui/templates/knowledge/entry.html` (extended with bi-directional links)

**Bi-directional link model:**
- KB entry → Investigation(s): via `source_investigation_id` (primary creator), `contributing_investigations` (all enrichments), and `linked_investigations` (structured with relationship type)
- Investigation → KB entry(ies): via Qdrant scroll filtering `source_investigation_id` or `contributing_investigations` array in `knowledge` collection

**Link relationship types (AC #3):**
- `source` — Investigation that triggered KB entry creation
- `related` — Investigation that enriched/contributed evidence to the entry
- `supersedes` — Future: when a corrected entry replaces an older one

**Data already in place from Story 6-1:**
- `KnowledgeEntry.source_investigation_id` — Links to the originating investigation
- `KnowledgeEntry.contributing_investigations` — List of all investigations that enriched the entry
- `AutoKBCreationService._create_new_entry()` — Sets `source_investigation_id` and `contributing_investigations`
- `AutoKBCreationService._enrich_existing_entry()` — Appends to `contributing_investigations`

**Story 6-2 adds:**
- Structured `linked_investigations` field with relationship type metadata
- UI rendering of links on both KB entry detail and investigation detail pages
- New `KBClient` method to look up KB entries by investigation_id (reverse direction)
- Link preservation during edits and corrections

### Existing Code to Reuse (DO NOT RECREATE)

| Component | Location | What to Reuse |
|-----------|----------|---------------|
| KBClient | `investigator/beeper_investigator/kb/client.py:34` | `client.scroll()` for filtered lookups |
| KBClient.search_knowledge() | `investigator/beeper_investigator/kb/client.py:111` | Existing vector search pattern |
| KBService.get_entry() | `ui/beeper_ui/services/kb_service.py` | Retrieves entry with full payload |
| KBService.list_related_entries() | `ui/beeper_ui/services/kb_service.py` | Service-based related entries (extend) |
| KBEntry dataclass | `ui/beeper_ui/services/kb_service.py` | UI entry representation |
| InvestigationService | `ui/beeper_ui/services/investigation_service.py` | Investigation fetching patterns |
| _related_kb.html template | `ui/beeper_ui/templates/investigations/_related_kb.html` | KB entry card CSS patterns |
| entry.html template | `ui/beeper_ui/templates/knowledge/entry.html` | KB detail page layout |
| _detail_content.html | `ui/beeper_ui/templates/investigations/_detail_content.html` | Investigation detail layout, HTMX pattern |
| AutoKBCreationService | `investigator/beeper_investigator/kb/auto_creation.py` | auto KB creation with link fields |

### Anti-Patterns to AVOID

- Do NOT create a separate Qdrant collection for links — links are payload fields on existing `knowledge` collection entries
- Do NOT break backward compatibility — `source_investigation_id` and `contributing_investigations` must remain for code that reads them directly
- Do NOT modify the investigator pipeline flow — this story only adds UI rendering and a structured link field
- Do NOT modify the operator component — bi-directional links are in KB entries (investigator) and UI layer
- Do NOT duplicate the "Related Knowledge Base Entries" section — "Knowledge Created" is entries CREATED BY this investigation, "Related Knowledge" is entries FOUND RELEVANT TO this investigation (from KB surfacing service)
- Do NOT use vector search for link lookups — use Qdrant scroll with field filters (exact match on investigation_id)

### Previous Story Intelligence (6-1)

**Key learnings from Story 6-1 (Automatic KB Entry Creation):**
- `AutoKBCreationService._create_new_entry()` already sets `source_investigation_id` and `contributing_investigations` in payload
- `AutoKBCreationService._enrich_existing_entry()` appends to `contributing_investigations` and `related_investigations`
- Payload structure is already rich with investigation links — story 6-2 adds UI rendering and the structured `linked_investigations` field
- Version snapshots in `knowledge_versions` collection already capture full payload including link fields
- Code review found and fixed: empty resolution field extraction, dead enrichment code, broad type hint
- 3,072 tests pass across all components (916 investigator + 1,625 UI + 531 operator)

**Key patterns:**
- Qdrant scroll pattern: `client.scroll(collection_name, scroll_filter=Filter(must=[FieldCondition(...)]), limit=N, with_payload=True)`
- HTMX lazy loading pattern: `<div hx-get="/<endpoint>" hx-trigger="load" hx-swap="innerHTML">`
- KB entry card HTML pattern from `_related_kb.html`: `.kb-entry-card` div with `.kb-entry-card-header`, type badge, validation badge

### Testing Standards

- **Framework:** pytest with unittest.mock for KBClient, Qdrant, KBService
- **Test locations:**
  - `investigator/tests/test_auto_kb_creation.py` — extend with link population tests
  - `investigator/tests/test_kb_client.py` — new or extend for client methods (check if exists)
  - `ui/tests/test_kb_service.py` — extend for bi-directional link service methods
  - `ui/tests/test_routes_knowledge.py` — extend for entry detail links
  - `ui/tests/test_routes_investigations.py` — extend for linked-kb endpoint
- **Mocking:** `unittest.mock.patch` for Qdrant client, KBService methods
- **Coverage:** All new service methods, link preservation, empty states, template rendering

### Project Structure Notes

**Files to CREATE:**
- `ui/beeper_ui/templates/investigations/_linked_kb.html` — New partial template for "Knowledge Created" links on investigation detail

**Files to MODIFY:**
- `investigator/beeper_investigator/kb/schemas.py` — Add `linked_investigations` field to KnowledgeEntry
- `investigator/beeper_investigator/kb/client.py` — Add `get_kb_entries_for_investigation()`, `get_entries_by_investigation_id()` methods
- `investigator/beeper_investigator/kb/auto_creation.py` — Populate `linked_investigations` in _create_new_entry() and _enrich_existing_entry()
- `ui/beeper_ui/services/kb_service.py` — Add bi-directional link service methods
- `ui/beeper_ui/routes/knowledge.py` — Pass link data to entry detail template
- `ui/beeper_ui/routes/investigations.py` — Add `/<investigation_id>/linked-kb` endpoint
- `ui/beeper_ui/templates/knowledge/entry.html` — Add investigation links section
- `ui/beeper_ui/templates/investigations/_detail_content.html` — Add "Knowledge Created" section
- `investigator/tests/test_auto_kb_creation.py` — Add link population tests
- `ui/tests/test_kb_service.py` — Add bi-directional link tests
- `ui/tests/test_routes_knowledge.py` — Add entry detail link tests
- `ui/tests/test_routes_investigations.py` — Add linked-kb endpoint tests

**Files to NOT touch:**
- `investigator/beeper_investigator/agent.py` — No pipeline changes needed
- `investigator/beeper_investigator/steps/*.py` — No step changes needed
- Any operator files — investigator + UI only
- `ui/beeper_ui/services/kb_surfacing_service.py` — Handles "Related Knowledge" (semantic), not "Knowledge Created" (link-based)

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 6.2] — Acceptance criteria and story statement
- [Source: _bmad-output/planning-artifacts/architecture.md#FR39] — `investigator/kb/schemas.py`, `investigator/kb/client.py`
- [Source: _bmad-output/planning-artifacts/architecture.md#Data Architecture] — Qdrant collections, knowledge collection with bi-directional links
- [Source: _bmad-output/planning-artifacts/prd.md#FR39] — System can link KB entries bi-directionally to investigations and related entries
- [Source: _bmad-output/planning-artifacts/prd.md#NFR2] — UI response time < 2 seconds
- [Source: investigator/beeper_investigator/kb/auto_creation.py] — AutoKBCreationService with source_investigation_id, contributing_investigations
- [Source: investigator/beeper_investigator/kb/schemas.py] — KnowledgeEntry with existing link fields
- [Source: investigator/beeper_investigator/kb/client.py] — KBClient scroll and search patterns
- [Source: ui/beeper_ui/services/kb_service.py] — KBService.get_entry(), list_related_entries()
- [Source: ui/beeper_ui/routes/knowledge.py] — kb_entry() route
- [Source: ui/beeper_ui/routes/investigations.py] — investigation_related_kb() endpoint
- [Source: ui/beeper_ui/templates/knowledge/entry.html] — KB entry detail page
- [Source: ui/beeper_ui/templates/investigations/_detail_content.html] — Investigation detail with HTMX sections
- [Source: ui/beeper_ui/templates/investigations/_related_kb.html] — Related KB card patterns
- [Source: _bmad-output/implementation-artifacts/6-1-automatic-kb-entry-creation.md] — Previous story with link field implementation

## Dev Agent Record

### Agent Model Used

claude-opus-4-6

### Debug Log References

### Completion Notes List

- Added `linked_investigations` field to `KnowledgeEntry` schema with structured relationship type metadata (source, related, supersedes)
- Added `get_kb_entries_for_investigation()` and `get_entries_by_investigation_id()` to `KBClient` for reverse lookups from investigation to KB entries
- Added `get_source_investigation()`, `get_contributing_investigations()`, `get_linked_kb_entries()`, `get_entry_payload()` to `KBService`
- Fixed `KBService.update_entry()` to preserve `source_investigation_id`, `contributing_investigations`, `linked_investigations`, and `validation_status` on edit
- Updated `AutoKBCreationService._create_new_entry()` to populate `linked_investigations` with source relationship
- Updated `AutoKBCreationService._enrich_existing_entry()` to append to `linked_investigations` with related relationship (deduplicating by investigation_id)
- Added "Investigation Links" section to KB entry detail page with Source Investigation and Contributing Investigations links
- Added "Knowledge Created" HTMX section to investigation detail page showing KB entries created from this investigation
- Created `_linked_kb.html` partial template for the Knowledge Created section
- 25 new investigator tests (16 KBClient + 9 auto_creation), 24 new UI tests (15 kb_service + 5 routes_knowledge + 4 routes_investigations)
- All 3,121 tests pass across all components (941 investigator + 1,649 UI + 531 operator)

### Change Log

- 2026-03-17: Implemented story 6-2 — bi-directional KB-investigation links with structured relationship metadata, UI rendering on both KB entry and investigation detail pages, link preservation on edit
- 2026-03-17: Code review found 3 MEDIUM + 2 LOW issues. Auto-fixed: triple Qdrant query perf issue (M1), missing validation_status badge in _linked_kb.html (M2), hardcoded URL paths in entry.html (M3). Added validation_status field to KBEntry dataclass. Added 1 new test. All 3,122 tests pass (941 investigator + 1,650 UI + 531 operator).

### File List

- investigator/beeper_investigator/kb/schemas.py (MODIFIED) — Added `linked_investigations` field to KnowledgeEntry
- investigator/beeper_investigator/kb/client.py (MODIFIED) — Added `get_kb_entries_for_investigation()`, `get_entries_by_investigation_id()` methods
- investigator/beeper_investigator/kb/auto_creation.py (MODIFIED) — Populated `linked_investigations` in `_create_new_entry()` and `_enrich_existing_entry()`
- ui/beeper_ui/services/kb_service.py (MODIFIED) — Added bi-directional link methods + link preservation in `update_entry()`
- ui/beeper_ui/routes/knowledge.py (MODIFIED) — Pass investigation link data to entry detail template
- ui/beeper_ui/routes/investigations.py (MODIFIED) — Added `/<investigation_id>/linked-kb` endpoint
- ui/beeper_ui/templates/knowledge/entry.html (MODIFIED) — Added Investigation Links section
- ui/beeper_ui/templates/investigations/_detail_content.html (MODIFIED) — Added Knowledge Created section
- ui/beeper_ui/templates/investigations/_linked_kb.html (CREATED) — Partial template for Knowledge Created links
- investigator/tests/test_kb_client.py (CREATED) — 16 tests for new KBClient methods
- investigator/tests/test_auto_kb_creation.py (MODIFIED) — 9 new tests for linked_investigations population
- ui/tests/test_kb_service.py (MODIFIED) — 15 new tests for bi-directional link service methods
- ui/tests/test_routes_knowledge.py (CREATED) — 5 tests for entry detail links
- ui/tests/test_routes_investigations.py (CREATED) — 4 tests for linked-kb endpoint
- _bmad-output/implementation-artifacts/6-2-bi-directional-kb-investigation-links.md (MODIFIED) — Story file
- _bmad-output/implementation-artifacts/sprint-status.yaml (MODIFIED) — Story status updates
