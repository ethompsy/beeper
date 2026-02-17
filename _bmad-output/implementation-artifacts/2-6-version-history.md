# Story 2.6: Version History

Status: done

## Story

As an **SRE**,
I want to view the version history of any KB entry,
So that I can see how documentation evolved and who made changes.

## Acceptance Criteria

### AC1: History Link and Version List
**Given** I am viewing a KB entry
**When** I click "History"
**Then** I see a list of all versions (FR21)
**And** each version shows: version number, date, author, change summary

### AC2: View Previous Version
**Given** version history is displayed
**When** I click on a previous version
**Then** I can view that version's content
**And** I see "Viewing version X of Y" indicator

### AC3: Restore Previous Version
**Given** I am viewing an old version
**When** I want to restore it
**Then** I can click "Restore this version"
**And** a new version is created with the old content

## Tasks / Subtasks

- [x] Task 1: Add version snapshot storage to KBService (AC: #1, #2, #3)
  - [x] 1.1: Add `knowledge_versions` collection to `init-collections.py` with indexes (entry_id, version)
  - [x] 1.2: Add `save_version_snapshot()` method to KBService that stores current entry state before update
  - [x] 1.3: Modify `update_entry()` to call `save_version_snapshot()` before overwriting
  - [x] 1.4: Modify `create_entry()` to store initial version (version 1) snapshot
  - [x] 1.5: Add `list_versions()` method to KBService (returns list of version metadata for an entry_id)
  - [x] 1.6: Add `get_version()` method to KBService (returns full content of a specific version)

- [x] Task 2: Create history route and template (AC: #1)
  - [x] 2.1: Add `GET /knowledge/<entry_id>/history` route to load version history page
  - [x] 2.2: Create `templates/knowledge/history.html` with version list
  - [x] 2.3: Add "History" button to entry detail page (`entry.html`) next to "Edit"

- [x] Task 3: Create version view template (AC: #2)
  - [x] 3.1: Add `GET /knowledge/<entry_id>/version/<version_num>` route to view a specific version
  - [x] 3.2: Create `templates/knowledge/version.html` showing version content with "Viewing version X of Y" banner
  - [x] 3.3: Add navigation links (Previous Version / Next Version / Current Version)

- [x] Task 4: Implement version restore (AC: #3)
  - [x] 4.1: Add `POST /knowledge/<entry_id>/restore/<version_num>` route
  - [x] 4.2: Restore calls `update_entry()` with old version's content (creates new version)
  - [x] 4.3: Create `_restore_result.html` partial for HTMX success/error feedback
  - [x] 4.4: Check embedding service is configured before restore (same pattern as edit)

- [x] Task 5: Add history/version styles (AC: #1, #2)
  - [x] 5.1: Add CSS for version list layout (timeline-style)
  - [x] 5.2: Style version banner ("Viewing version X of Y")
  - [x] 5.3: Style restore button/confirmation

- [x] Task 6: Add tests (AC: all)
  - [x] 6.1: Test `save_version_snapshot()` stores correct data
  - [x] 6.2: Test `list_versions()` returns versions in order
  - [x] 6.3: Test `get_version()` returns correct version content
  - [x] 6.4: Test `update_entry()` saves snapshot before overwriting
  - [x] 6.5: Test history page loads with version list
  - [x] 6.6: Test version view page shows correct content with banner
  - [x] 6.7: Test restore creates new version with old content
  - [x] 6.8: Test restore with embedding service not configured
  - [x] 6.9: Test entry not found errors for history/version/restore

## Dev Notes

### Architecture Compliance

**Source:** [architecture.md - Frontend Approach]

> **MVP: HTMX + Server-Sent Events**
> - No JavaScript complexity
> - Flask-native, simple implementation

All version history UI should use server-rendered Flask templates. No JavaScript required.

### Critical Design Decision: Version Storage Strategy

**Current state:** `update_entry()` OVERWRITES the existing Qdrant point (same point ID) with new payload. Old versions are LOST. The `version` field is incremented but only the latest version persists.

**Recommended approach:** Create a `knowledge_versions` collection in Qdrant for storing version snapshots.

**Why a separate collection (not same collection):**
1. Semantic search (`knowledge` collection) should only return current versions, not old ones
2. Version snapshots don't need embedding vectors (they're not searched semantically)
3. Simpler queries: filter by `entry_id` to get all versions
4. No risk of old versions appearing in search results

**Version snapshot schema:**
```python
# knowledge_versions collection
{
    "entry_id": "kb-abc123",       # Links to knowledge collection
    "version": 3,                  # Version number
    "title": "...",                # Title at this version
    "content": "...",              # Full content at this version
    "author": "edit",              # Who made this version
    "created_at": "2026-02-17T...",  # When original entry was created
    "updated_at": "2026-02-17T...",  # When this version was saved
    "entry_type": "runbook",       # Entry type at this version
    "service": "api",              # Service at this version
    "tags": ["tag1", "tag2"],      # Tags at this version
}
```

**Collection setup (add to `init-collections.py`):**
```python
"knowledge_versions": {
    "description": "Version history for knowledge base entries",
    "payload_indexes": [
        ("entry_id", PayloadSchemaType.KEYWORD),
        ("version", PayloadSchemaType.INTEGER),
    ],
},
```

**Note:** This collection does NOT need vector embeddings. Use a dummy/zero vector or configure the collection without vectors if Qdrant supports it. Check Qdrant docs for collections without vector config. If not supported, use a single-element zero vector `[0.0]` with dimension 1.

### Existing Infrastructure

**From kb_service.py:**

`KBService.update_entry()` (line 681) currently:
1. Fetches existing point by `entry_id`
2. Increments `version` counter
3. Merges new fields with existing payload
4. Generates new embedding
5. **Overwrites** existing point with `client.upsert()`

**Modification needed:** Before step 5 (overwrite), save the CURRENT payload as a version snapshot to `knowledge_versions`.

```python
# In update_entry(), BEFORE the upsert that overwrites:
self._save_version_snapshot(
    entry_id=entry_id,
    payload=existing_payload,  # Save current state before overwriting
    point_id=str(existing_point.id),
)
```

**`KBService.create_entry()` (line 535):** After creating the initial entry, also save version 1 as the first snapshot in `knowledge_versions`. This ensures the initial version is always available in history.

### New KBService Methods

```python
VERSIONS_COLLECTION = "knowledge_versions"

def _save_version_snapshot(self, entry_id: str, payload: dict, point_id: str) -> None:
    """Save current entry state as a version snapshot before overwriting."""
    version_point_id = str(uuid.uuid4())
    version_payload = {
        "entry_id": payload.get("entry_id", entry_id),
        "version": payload.get("version", 1),
        "title": payload.get("title", ""),
        "content": payload.get("content", ""),
        "author": payload.get("author"),
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
        "entry_type": payload.get("entry_type"),
        "service": payload.get("service"),
        "tags": payload.get("tags", []),
    }
    # Use zero vector since versions aren't semantically searched
    self.client.upsert(
        collection_name=VERSIONS_COLLECTION,
        points=[PointStruct(id=version_point_id, vector=[0.0], payload=version_payload)],
    )

def list_versions(self, entry_id: str) -> list[dict]:
    """List all version snapshots for an entry, ordered by version number descending."""
    results, _ = self.client.scroll(
        collection_name=VERSIONS_COLLECTION,
        scroll_filter=Filter(
            must=[FieldCondition(key="entry_id", match=MatchValue(value=entry_id))]
        ),
        limit=100,
        with_payload=True,
        with_vectors=False,
    )
    versions = [
        {
            "version": p.payload.get("version", 1),
            "author": p.payload.get("author"),
            "updated_at": p.payload.get("updated_at"),
            "title": p.payload.get("title"),
        }
        for p in results
    ]
    return sorted(versions, key=lambda v: v["version"], reverse=True)

def get_version(self, entry_id: str, version_num: int) -> Optional[dict]:
    """Get a specific version snapshot's full content."""
    results, _ = self.client.scroll(
        collection_name=VERSIONS_COLLECTION,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="entry_id", match=MatchValue(value=entry_id)),
                FieldCondition(key="version", match=MatchValue(value=version_num)),
            ]
        ),
        limit=1,
        with_payload=True,
        with_vectors=False,
    )
    if not results:
        return None
    return results[0].payload
```

### Route Patterns

**History page:** `GET /knowledge/<entry_id>/history`
- Loads current entry (for header/breadcrumb)
- Calls `list_versions()` for version list
- Also includes the current version in the list (from live entry, not snapshot)

**Version view:** `GET /knowledge/<entry_id>/version/<int:version_num>`
- Calls `get_version()` for specific version content
- Renders content with markdown filter
- Shows "Viewing version X of Y" banner with navigation

**Restore:** `POST /knowledge/<entry_id>/restore/<int:version_num>`
- Gets version content via `get_version()`
- Calls `update_entry()` with old content (which triggers new version + new snapshot)
- Returns HTMX partial with success/redirect

### Route Ordering Note

**Source:** [2-4-runbook-import.md - Dev Agent Record]

> Route ordering: Import route registered BEFORE dynamic `/<entry_id>` route

The history and version routes use nested paths (`/<entry_id>/history`, `/<entry_id>/version/<n>`, `/<entry_id>/restore/<n>`) which Flask matches correctly against the dynamic `/<entry_id>` route. No special ordering required (same as the edit route pattern from Story 2.5).

### Entry Template Modification

Add "History" button next to "Edit" in `entry.html`:

```html
<div class="entry-title-row">
    <h2>{{ entry.title }}</h2>
    <div class="entry-actions">
        <a href="{{ url_for('knowledge.kb_history', entry_id=entry.entry_id) }}" class="btn btn-secondary">History</a>
        <a href="{{ url_for('knowledge.kb_edit', entry_id=entry.entry_id) }}" class="btn btn-secondary">Edit</a>
    </div>
</div>
```

### Change Summary Generation

For AC1 ("each version shows change summary"), a simple approach:
- Compare the title/content length change between versions
- If title changed: "Title updated"
- If content length changed significantly: "Content updated (X chars added/removed)"
- If tags changed: "Tags updated"
- If service changed: "Service changed from X to Y"

This can be computed on the fly when listing versions (compare consecutive version snapshots). No need to store change summaries — they can be derived.

### Security Considerations

**Restore operation:**
- Requires embedding service to be configured (regenerates embeddings for restored content)
- Version check NOT needed for restore (it creates a new version, not a conflict)
- Entry must exist in live `knowledge` collection
- Version must exist in `knowledge_versions` collection

### Project Structure Notes

**New files to create:**
```
ui/beeper_ui/
├── templates/knowledge/
│   ├── history.html               # New: Version history page
│   ├── version.html               # New: Single version view page
│   └── _restore_result.html       # New: Restore result partial
```

**Files to modify:**
```
ui/beeper_ui/
├── services/kb_service.py         # Add _save_version_snapshot, list_versions, get_version
├── routes/knowledge.py            # Add history, version, restore routes
├── templates/knowledge/entry.html # Add "History" button
├── static/css/main.css            # Add history/version styles
scripts/
└── init-collections.py            # Add knowledge_versions collection
ui/tests/
├── test_kb_service.py             # Add version snapshot tests
└── test_kb_routes.py              # Add history/version/restore route tests
```

### Testing Strategy

**Unit Tests (kb_service):**
- Mock Qdrant client for `_save_version_snapshot()`
- Mock Qdrant client for `list_versions()` (return ordered results)
- Mock Qdrant client for `get_version()` (return specific payload)
- Verify `update_entry()` calls `_save_version_snapshot()` before overwrite
- Verify `create_entry()` calls `_save_version_snapshot()` for initial version

**Route Tests (kb_routes):**
- Test history page loads with version list
- Test history page for non-existent entry returns 404
- Test version view shows correct content with banner
- Test version view for non-existent version returns 404
- Test restore creates new version with old content
- Test restore with embedding service not configured
- Test restore for non-existent version returns error

### Previous Story Learnings (2-5)

**Source:** [2-5-kb-entry-editing.md - Code Review Record]

Key patterns to apply:
1. **Optimistic concurrency control:** Story 2.5 added version checking for edits. Restore does NOT need this (it creates a new version).
2. **CSS-only interactions:** Use `:has()` pseudo-class, no JavaScript
3. **HTMX patterns:** Use `hx-post`, `hx-target`, `hx-indicator` for restore action
4. **Embedding service check:** Always check `is_configured()` before write operations
5. **Edit result CSS classes:** Story 2.5 created `edit-result`/`edit-success`/`edit-error` classes. Use a similar pattern for restore results.
6. **Test patterns:** Use `_make_entry()` helper, `@patch` for service mocking

### References

- [Source: architecture.md#Frontend Approach - HTMX]
- [Source: architecture.md#Data Architecture - Qdrant collections]
- [Source: epics.md#Story 2.6: Version History]
- [Source: epics.md#Story 2.7: Version Diff View - upcoming, design for compatibility]
- [Source: kb_service.py#update_entry - Current overwrite behavior]
- [Source: kb_service.py#create_entry - Initial entry creation]
- [Source: init-collections.py - Collection schema definitions]
- [Source: 2-5-kb-entry-editing.md - Edit patterns, concurrency control, CSS classes]
- [Source: 2-4-runbook-import.md - Route ordering, HTMX patterns, validation]
- [Qdrant Scroll API](https://qdrant.tech/documentation/concepts/points/#scroll-points)
- [Qdrant Filter Conditions](https://qdrant.tech/documentation/concepts/filtering/)

---

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

No blocking issues encountered during implementation.

### Completion Notes List

- Added `knowledge_versions` Qdrant collection for version snapshots with minimal 1-dimension vector (no semantic search needed) and entry_id + version indexes
- Added `_save_version_snapshot()`, `list_versions()`, and `get_version()` methods to KBService
- Modified `update_entry()` to save version snapshot BEFORE overwriting the existing point
- Modified `create_entry()` to save initial version 1 snapshot after entry creation
- Added `VERSIONS_COLLECTION = "knowledge_versions"` constant to kb_service.py
- Created 3 new routes: `GET /<entry_id>/history`, `GET /<entry_id>/version/<int:version_num>`, `POST /<entry_id>/restore/<int:version_num>`
- History page merges current live entry with version snapshots, marking current version with badge
- Version view shows "Viewing version X of Y" banner, Previous/Next/Current navigation, and restore button for non-current versions
- Restore uses HTMX `hx-post` pattern with `_restore_result.html` partial, checks embedding service is_configured() before write
- Added "History" button next to "Edit" on entry detail page
- Added CSS for version list, version banner, restore result (follows edit-result/import-result pattern)
- Updated 2 existing tests (`test_create_entry_success`, `test_update_entry_success`) to account for additional upsert calls from version snapshots
- All 234 tests pass (14 new: 6 KB service + 8 route tests)
- No new dependencies introduced

### Code Review Fixes (Claude Opus 4.6)

- **[HIGH] AC1 Change Summary**: Added `_compute_change_summaries()` to routes, extended `list_versions()` to return content_length/tags/service, updated history.html with change_summary display and CSS styling
- **[MEDIUM] Snapshot error handling**: Made `_save_version_snapshot` failure non-fatal in `create_entry()` (wrapped in try/except with warning log) to prevent inconsistent state
- **[MEDIUM] Version navigation**: Changed Previous/Next links in version.html from arithmetic (v-1/v+1) to actual version numbers computed from version list, preventing 404s on non-contiguous versions
- **[MEDIUM] list_versions limit**: Added docstring note about 100 version limit in `list_versions()`
- All 235 tests pass after fixes (1 new test: `test_create_entry_snapshot_failure_non_fatal`)

### Change Log

- 2026-02-17: Implemented version history (Story 2.6) - version storage, history/version/restore routes, templates, CSS, tests
- 2026-02-17: Code review fixes - change summary (AC1), snapshot error handling, version navigation, limit documentation

### File List

New files:
- ui/beeper_ui/templates/knowledge/history.html
- ui/beeper_ui/templates/knowledge/version.html
- ui/beeper_ui/templates/knowledge/_restore_result.html

Modified files:
- ui/beeper_ui/services/kb_service.py
- ui/beeper_ui/routes/knowledge.py
- ui/beeper_ui/templates/knowledge/entry.html
- ui/beeper_ui/static/css/main.css
- scripts/init-collections.py
- ui/tests/test_kb_service.py
- ui/tests/test_kb_routes.py
- _bmad-output/implementation-artifacts/sprint-status.yaml
- _bmad-output/implementation-artifacts/2-6-version-history.md
