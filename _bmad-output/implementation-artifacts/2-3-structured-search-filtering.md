# Story 2.3: Structured Search & Filtering

Status: complete

## Story

As an **SRE**,
I want to search the KB using structured filters,
So that I can narrow down results by service, error type, or date range.

## Acceptance Criteria

### AC1: Filter Panel
**Given** I am on the KB search page
**When** I apply filters:
- Service: `payments`
- Date range: Last 30 days
- Entry type: `investigation`
**Then** only matching entries are returned (FR15)
**And** filters can be combined with semantic search

### AC2: Filter Options Display
**Given** filter options exist
**When** I view the filter panel
**Then** I see available filters: service, entry type, date range ~~, severity~~
**And** filter values are populated from existing KB metadata

> **AC2 Deviation:** Severity filter not implemented - `severity` field not in Qdrant schema (per init-collections.py). Would require schema migration to add.

### AC3: Active Filters Display
**Given** I apply a filter
**When** results are displayed
**Then** active filters are shown as removable chips
**And** I can clear all filters with one click

## Tasks / Subtasks

- [x] Task 1: Extend KB service with filter metadata retrieval (AC: #2)
  - [x] 1.1: Add `get_available_services()` method to KBService (return unique services from Qdrant)
  - [N/A] 1.2: Add `get_available_severity_levels()` method to KBService (severity not in Qdrant schema)
  - [x] 1.3: Ensure `get_entry_types()` returns all entry types from KB entries
  - [x] 1.4: Add caching for filter metadata (avoid repeated Qdrant queries)

- [x] Task 2: Create filter panel UI component (AC: #2)
  - [x] 2.1: Create `templates/knowledge/_filter_panel.html` partial
  - [x] 2.2: Add service dropdown with options from KB metadata
  - [x] 2.3: Add entry type dropdown (investigation, runbook, correction)
  - [N/A] 2.4: Add severity dropdown (if applicable to entry types) - severity not in Qdrant schema
  - [x] 2.5: Add date range picker (predefined options: Today, Last 7 days, Last 30 days, Last 90 days)
  - [x] 2.6: Style filter panel with CSS styles

- [x] Task 3: Implement date range filtering (AC: #1)
  - [x] 3.1: Add `date_from` and `date_to` parameters to `search_semantic()` method
  - [x] 3.2: Add `list_recent_entries()` support for date range filtering
  - [x] 3.3: Implement Qdrant datetime range filter using `created_at` field
  - [x] 3.4: Date range validation via `parse_date_range()` function

- [x] Task 4: Implement combined filter + semantic search (AC: #1)
  - [x] 4.1: Update `/knowledge/search` route to accept all filter parameters
  - [x] 4.2: Build Qdrant Filter with all conditions (entry_type, service, date_range)
  - [x] 4.3: Ensure filters work both with and without semantic query
  - [x] 4.4: Add filter-only search mode (no semantic query, just structured filters)

- [x] Task 5: Create active filter chips UI (AC: #3)
  - [x] 5.1: Create `templates/knowledge/_active_filters.html` partial
  - [x] 5.2: Display each active filter as a removable chip
  - [x] 5.3: Add HTMX behavior to remove individual filter chips
  - [x] 5.4: Add "Clear all filters" button
  - [x] 5.5: Update search results when filters change via HTMX

- [x] Task 6: Add HTMX filter interactions (AC: #1, #3)
  - [x] 6.1: Wire filter panel changes to trigger search via HTMX
  - [x] 6.2: Include all filter values in search requests (`hx-include`)
  - [x] 6.3: Update URL with filter state for shareable/bookmarkable URLs (`hx-push-url`)
  - [x] 6.4: Preserve filter state across page navigation

- [x] Task 7: Add tests (AC: #1, #2, #3)
  - [x] 7.1: Test filter metadata retrieval (services, types, caching)
  - [x] 7.2: Test date range filtering (parse_date_range, _build_date_filter)
  - [x] 7.3: Test combined semantic + filter search (with date_from/date_to)
  - [x] 7.4: Test filter-only search (no semantic query)
  - [N/A] 7.5: Test filter chip removal behavior - HTMX frontend behavior (manual testing)
  - [N/A] 7.6: Test "clear all filters" functionality - HTMX frontend behavior (manual testing)

## Dev Notes

### Architecture Compliance

**Source:** [architecture.md - API Patterns]

> **Query params:** `snake_case` (`?service_name=payments`)

Filter params should use snake_case:
- `?entry_type=investigation`
- `?service=payments`
- `?severity=critical`
- `?date_from=2026-01-01`
- `?date_to=2026-02-01`

**Source:** [architecture.md - Frontend Approach]

> **MVP: HTMX + Server-Sent Events**
> - No JavaScript complexity
> - Flask-native, simple implementation

Use HTMX for filter interactions:
- `hx-get` to trigger search on filter change
- `hx-include` to include all filter inputs
- `hx-push-url` to update URL with filter state

**Source:** [architecture.md - Qdrant Naming]

> **Payload fields:** Match JSON field naming exactly
> - `entry_type` (keyword)
> - `service` (keyword)
> - `created_at` (datetime)

### Existing Infrastructure

**From Story 2-2:**

The search route already accepts `entry_type` and `service` parameters:
```python
@bp.route("/search")
def kb_search() -> Response:
    query = sanitize_query(request.args.get("q", ""))
    entry_type = request.args.get("entry_type")
    service = request.args.get("service")
```

The `search_semantic()` method already handles these filters:
```python
def search_semantic(
    self,
    query: str,
    limit: int = 10,
    entry_type: Optional[str] = None,
    service: Optional[str] = None,
    embedding_service: Optional[EmbeddingService] = None,
) -> tuple[list[KBEntry], bool]:
```

**Qdrant Collections (from scripts/init-collections.py):**

The `knowledge` collection has indexed fields:
```python
"payload_indexes": [
    ("entry_id", PayloadSchemaType.KEYWORD),
    ("entry_type", PayloadSchemaType.KEYWORD),
    ("service", PayloadSchemaType.KEYWORD),
    ("created_at", PayloadSchemaType.DATETIME),
]
```

Note: `severity` is NOT currently indexed. If severity filtering is required, the collection schema needs updating.

### Date Range Filtering with Qdrant

```python
from qdrant_client.models import DatetimeRange, FieldCondition, Filter, Range

# Date range filter
date_filter = FieldCondition(
    key="created_at",
    range=DatetimeRange(
        gte=datetime(2026, 1, 1, tzinfo=timezone.utc),
        lte=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
)

# Combine with other filters
query_filter = Filter(
    must=[
        date_filter,
        FieldCondition(key="entry_type", match=MatchValue(value="investigation")),
    ]
)
```

### Filter-Only Search (No Semantic Query)

When no search query is provided but filters are active:
- Use `scroll()` or `query_points()` without vector
- Filter by metadata only
- Sort by `created_at` descending (most recent first)

```python
# Scroll with filter (no vector search)
results = client.scroll(
    collection_name=KNOWLEDGE_COLLECTION,
    scroll_filter=query_filter,
    limit=limit,
    order_by="created_at",
)
```

### Predefined Date Ranges

| Option | date_from | date_to |
|--------|-----------|---------|
| Today | today 00:00 UTC | today 23:59 UTC |
| Last 7 days | today - 7 days | today |
| Last 30 days | today - 30 days | today |
| Last 90 days | today - 90 days | today |
| Custom | user-selected | user-selected |

### HTMX Filter Panel Pattern

```html
<form id="filter-form"
      hx-get="{{ url_for('knowledge.kb_search') }}"
      hx-trigger="change"
      hx-target="#search-results"
      hx-push-url="true">

    <!-- Service filter -->
    <select name="service">
        <option value="">All services</option>
        {% for svc in services %}
        <option value="{{ svc }}" {% if svc == selected_service %}selected{% endif %}>
            {{ svc }}
        </option>
        {% endfor %}
    </select>

    <!-- Entry type filter -->
    <select name="entry_type">
        <option value="">All types</option>
        {% for type in entry_types %}
        <option value="{{ type }}" {% if type == selected_type %}selected{% endif %}>
            {{ type }}
        </option>
        {% endfor %}
    </select>

    <!-- Date range -->
    <select name="date_range">
        <option value="">All time</option>
        <option value="today">Today</option>
        <option value="7d">Last 7 days</option>
        <option value="30d">Last 30 days</option>
        <option value="90d">Last 90 days</option>
    </select>
</form>
```

### Active Filter Chips Pattern

```html
<div class="active-filters">
    {% if selected_service %}
    <span class="filter-chip">
        Service: {{ selected_service }}
        <button hx-get="{{ url_for('knowledge.kb_search') }}"
                hx-include="#filter-form"
                hx-vals='{"service": ""}'
                hx-target="#search-results"
                hx-push-url="true"
                class="chip-remove">×</button>
    </span>
    {% endif %}

    {% if any_filter_active %}
    <button hx-get="{{ url_for('knowledge.kb_search') }}"
            hx-target="#search-results"
            hx-push-url="true"
            class="clear-all">Clear all</button>
    {% endif %}
</div>
```

### Previous Story Learnings (2-2)

**Source:** [2-2-semantic-search.md - Code Review Record]

Key patterns to apply:
1. **Route ordering:** Static routes (`/search`) must come BEFORE dynamic routes (`/<entry_id>`)
2. **Query sanitization:** Always sanitize user input before use
3. **Singleton patterns:** Include reset function for testing
4. **Type annotations:** Use parameterized generics (`list[str]`)
5. **HTMX patterns:** Use `hx-trigger="change"` for select elements

### Security Considerations

**Filter Value Validation:**
- Validate entry_type against known types (investigation, runbook, correction)
- Validate date_from/date_to are valid ISO 8601 dates
- Sanitize service names (alphanumeric + hyphens only)
- Limit date range to reasonable bounds (e.g., max 1 year)

### Project Structure Notes

**New files to create:**
```
ui/beeper_ui/
├── templates/knowledge/
│   ├── _filter_panel.html      # New: Filter panel partial
│   └── _active_filters.html    # New: Active filter chips partial
```

**Files to modify:**
```
ui/beeper_ui/
├── services/kb_service.py      # Add filter metadata methods, date filtering
├── routes/knowledge.py         # Add date_range param, filter-only mode
├── templates/knowledge/
│   ├── index.html              # Add filter panel
│   └── _search_results.html    # Include active filters
├── static/css/main.css         # Add filter panel and chip styles
ui/tests/
├── test_kb_service.py          # Add filter tests
└── test_kb_routes.py           # Add filter route tests
```

### Testing Strategy

**Unit Tests:**
- Mock Qdrant client for filter metadata retrieval
- Test date range parsing and validation
- Test filter combination logic

**Integration Tests:**
- Test filter panel renders with correct options
- Test filter chips appear/disappear correctly
- Test URL updates with filter state
- Test combined semantic + filter search

### References

- [Source: architecture.md#API Patterns - Query params]
- [Source: architecture.md#Frontend Approach - HTMX]
- [Source: architecture.md#Qdrant Naming - Payload fields]
- [Source: epics.md#Story 2.3: Structured Search & Filtering]
- [Source: 2-2-semantic-search.md - Patterns and learnings]
- [Qdrant Filtering Docs](https://qdrant.tech/documentation/concepts/filtering/)
- [Qdrant Range Filtering](https://qdrant.tech/documentation/concepts/filtering/#range)
- [HTMX Form Handling](https://htmx.org/docs/#forms)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- All 67 KB tests pass (test_kb_service.py: 27 tests, test_kb_routes.py: 40 tests)
- mypy type check: Success, no issues found in 2 source files

### Completion Notes List

- Task 1.2 and 2.4 marked N/A: `severity` field not in Qdrant schema per init-collections.py
- Task 7.5 and 7.6 marked N/A: HTMX frontend behavior requires manual browser testing
- Filter metadata caching implemented to avoid repeated Qdrant queries
- Filter-only search mode implemented: when no query but filters active, uses `list_recent_entries()` with scroll
- Date range uses predefined options (today, 7d, 30d, 90d) parsed via `parse_date_range()` function
- Custom date range not implemented (would require date picker UI complexity)
- URL state preservation via `hx-push-url="true"` for shareable filter URLs

### File List

**New Files:**
- `ui/beeper_ui/templates/knowledge/_filter_panel.html` - Filter panel partial with dropdowns
- `ui/beeper_ui/templates/knowledge/_active_filters.html` - Active filter chips partial

**Modified Files:**
- `ui/beeper_ui/services/kb_service.py` - Added filter caching, date filtering, `parse_date_range()`, `MAX_FILTER_METADATA_ENTRIES` constant
- `ui/beeper_ui/routes/knowledge.py` - Added date_range param, filter-only mode, `validate_entry_type()`, `VALID_ENTRY_TYPES` constant
- `ui/beeper_ui/templates/knowledge/index.html` - Added filter panel include
- `ui/beeper_ui/templates/knowledge/_search_results.html` - Added active filters include
- `ui/beeper_ui/static/css/main.css` - Added filter panel and chip styles, CSS-only accordion
- `ui/tests/test_kb_service.py` - Added 14 new tests (filter metadata, date parsing, date filtering)
- `ui/tests/test_kb_routes.py` - Added 16 new tests (date range search, filter-only mode, entry type validation, clear filters)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` - Updated 2-3 status to done

### Code Review Record

**Reviewer:** Claude Opus 4.5 (Adversarial Code Review)
**Date:** 2026-02-13
**Issues Found:** 3 HIGH, 4 MEDIUM, 2 LOW
**Issues Fixed:** 7 (all HIGH + MEDIUM)

**Fixes Applied:**

1. **HIGH: AC2 Severity Filter** - Documented deviation in AC2 (severity not in Qdrant schema)
2. **HIGH: Missing Input Validation** - Added `validate_entry_type()` function with `VALID_ENTRY_TYPES` constant
3. **HIGH: Task 6.4 Filter State** - Verified working via `hx-push-url` + `selected_*` template variables
4. **MEDIUM: Inline JavaScript** - Replaced onclick with CSS-only accordion using hidden checkbox
5. **MEDIUM: Missing Test for Clear Filters** - Added `test_kb_search_clear_all_filters` and `test_kb_search_invalid_entry_type_ignored`
6. **MEDIUM: Story File List** - Added `sprint-status.yaml` to file list
7. **LOW: Magic Number** - Extracted `MAX_FILTER_METADATA_ENTRIES = 1000` constant
8. **LOW: Redundant Calculation** - Removed template `any_filter_active` calculation, added to kb_index route

**Test Results After Fixes:**
- 76 KB tests pass (up from 67)
- mypy: Success, no issues
