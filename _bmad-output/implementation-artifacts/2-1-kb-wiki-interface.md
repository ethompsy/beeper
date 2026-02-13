# Story 2.1: KB Wiki Interface

Status: done

## Story

As an **SRE**,
I want to access a wiki-style interface for the Knowledge Base,
So that I can browse and read documentation in a human-friendly format.

## Acceptance Criteria

### AC1: KB Index Page
**Given** the UI is deployed
**When** I navigate to `/knowledge`
**Then** I see the KB wiki index page (FR36)
**And** I see a list of recent KB entries
**And** entries are organized by type (investigations, runbooks)

### AC2: Entry Detail View
**Given** KB entries exist
**When** I click on an entry
**Then** I see the entry in human-readable wiki format (FR16)
**And** the entry displays: title, content, metadata (service, date, author)
**And** markdown content is rendered properly

### AC3: Service Linking
**Given** an entry is linked to a service
**When** I view the entry
**Then** I see the service name as a clickable filter
**And** related entries for that service are suggested

## Tasks / Subtasks

- [x] Task 1: Create KB routes in Flask (AC: #1)
  - [x] 1.1: Create `ui/beeper_ui/routes/knowledge.py` with `/knowledge` blueprint
  - [x] 1.2: Implement `GET /knowledge` route to list recent KB entries
  - [x] 1.3: Implement `GET /knowledge/<entry_id>` route for entry detail
  - [x] 1.4: Register blueprint in `app.py`

- [x] Task 2: Implement KB service layer (AC: #1, #2, #3)
  - [x] 2.1: Create `ui/beeper_ui/services/kb_service.py` for KB operations
  - [x] 2.2: Implement `list_recent_entries(limit=20)` using Qdrant client
  - [x] 2.3: Implement `get_entry(entry_id)` to fetch single entry
  - [x] 2.4: Implement `list_entries_by_service(service_name)` for service filtering
  - [x] 2.5: Implement `list_related_entries(entry_id, service)` for suggestions

- [x] Task 3: Create KB templates with HTMX (AC: #1, #2)
  - [x] 3.1: Create `templates/knowledge/index.html` - KB wiki index page
  - [x] 3.2: Create `templates/knowledge/entry.html` - Entry detail view
  - [x] 3.3: Create `templates/knowledge/_entry_list.html` - Partial for entry list
  - [x] 3.4: Create `templates/knowledge/_entry_card.html` - Partial for single entry card
  - [x] 3.5: Style with CSS matching existing UI patterns from status page

- [x] Task 4: Implement markdown rendering (AC: #2)
  - [x] 4.1: Add `markdown` package to pyproject.toml dependencies
  - [x] 4.2: Create Jinja2 filter for markdown rendering with code highlighting
  - [x] 4.3: Sanitize markdown output to prevent XSS
  - [x] 4.4: Support code blocks, tables, and standard markdown features

- [x] Task 5: Implement service filter functionality (AC: #3)
  - [x] 5.1: Add service filter dropdown to index page
  - [x] 5.2: Implement HTMX-powered filter without page reload
  - [x] 5.3: Add clickable service badges on entry detail page
  - [x] 5.4: Show "Related entries for this service" section on detail page

- [x] Task 6: Add navigation and layout (AC: #1, #2)
  - [x] 6.1: Add "Knowledge Base" link to main navigation in base.html
  - [x] 6.2: Add breadcrumb navigation: KB > Entry Title
  - [x] 6.3: Add entry type badges (investigation, runbook, correction)
  - [x] 6.4: Add created_at timestamp display in human-readable format

- [x] Task 7: Add tests (AC: #1, #2, #3)
  - [x] 7.1: Test `/knowledge` route returns 200 with entry list
  - [x] 7.2: Test `/knowledge/<entry_id>` returns entry detail
  - [x] 7.3: Test service filter returns filtered entries
  - [x] 7.4: Test markdown rendering with various input
  - [x] 7.5: Test XSS prevention in markdown output

## Dev Notes

### Architecture Compliance

**Source:** [architecture.md - Frontend Approach]

> **MVP: HTMX + Server-Sent Events**
> - No JavaScript complexity
> - Flask-native, simple implementation

The KB wiki should use HTMX for dynamic updates (filters, related entries) without writing JavaScript.

**Source:** [architecture.md - FR to Structure Mapping]

> **Knowledge Base (FR13-23):**
> - FR16-17 (view/edit): `ui/templates/knowledge/`
> - FR36: `ui/routes/knowledge.py`

**Source:** [architecture.md - Qdrant Naming]

> - **Collections:** `snake_case` (`investigations`, `knowledge`)
> - **Fields:** `snake_case` (`investigation_id`, `created_at`, `confidence_level`)
> - **Payload fields:** Match JSON field naming exactly

### Existing Infrastructure

**Qdrant Collections (from scripts/init-collections.py):**

The `knowledge` collection already exists with schema:
```python
"knowledge": {
    "payload_indexes": [
        ("entry_id", PayloadSchemaType.KEYWORD),
        ("entry_type", PayloadSchemaType.KEYWORD),  # runbook, investigation, correction
        ("service", PayloadSchemaType.KEYWORD),
        ("created_at", PayloadSchemaType.DATETIME),
    ],
},
```

**KBClient (from investigator/beeper_investigator/kb/client.py):**

The existing `KBClient` class provides:
- `search_knowledge(query_vector, limit, entry_type, service)` - Vector similarity search
- `search_investigations(query_vector, limit, status, service)` - Investigation search
- `get_collection_info(collection_name)` - Collection metadata

For the wiki interface, we need **non-vector queries** (list all, filter by type/service). The current client is vector-search focused. The UI will need to add direct Qdrant scroll/filter operations.

**UI Patterns (from ui/beeper_ui/templates/health/_status_content.html):**

The status page already establishes patterns for:
- Status badges with color indicators
- Card-based layouts
- HTMX partial loading (`hx-get`, `hx-trigger`)
- Responsive grid layouts

**CSS Classes (from ui/beeper_ui/static/css/main.css):**

Existing styles include:
- `.status-badge.ok`, `.status-badge.error`, `.status-badge.warning`
- `.card`, `.card-header`, `.card-body`
- Grid layout utilities

### Qdrant Query Patterns for Wiki

**List all entries (paginated):**
```python
from qdrant_client.models import ScrollRequest

client.scroll(
    collection_name="knowledge",
    limit=20,
    with_payload=True,
    with_vectors=False,
)
```

**Filter by entry_type:**
```python
from qdrant_client.models import Filter, FieldCondition, MatchValue

client.scroll(
    collection_name="knowledge",
    scroll_filter=Filter(
        must=[FieldCondition(key="entry_type", match=MatchValue(value="runbook"))]
    ),
    limit=20,
)
```

**Filter by service:**
```python
client.scroll(
    collection_name="knowledge",
    scroll_filter=Filter(
        must=[FieldCondition(key="service", match=MatchValue(value="payments"))]
    ),
    limit=20,
)
```

**Get single entry by entry_id:**
```python
from qdrant_client.models import Filter, FieldCondition, MatchValue

results = client.scroll(
    collection_name="knowledge",
    scroll_filter=Filter(
        must=[FieldCondition(key="entry_id", match=MatchValue(value="entry-123"))]
    ),
    limit=1,
)
```

### Previous Story Learnings (1-9)

**Source:** [1-9-investigation-crd-pod-spawning.md - Code Review Record]

Key patterns to follow:
1. **Environment variables:** Read from env with sensible defaults
2. **Structured logging:** Use JSON logging with context fields
3. **Test coverage:** Write tests for all routes and edge cases
4. **Error handling:** Return appropriate HTTP status codes

**CSS additions from 1-7:**
The status page CSS establishes the visual language - KB wiki should match.

### KB Entry Payload Structure

Based on architecture and schemas, KB entries should have payload:
```json
{
  "entry_id": "kb-abc123",
  "entry_type": "investigation",  // or "runbook", "correction"
  "title": "Database Connection Timeout Investigation",
  "content": "## Summary\n\nMarkdown content here...",
  "service": "payments",
  "created_at": "2026-02-13T10:30:00Z",
  "updated_at": "2026-02-13T10:30:00Z",
  "author": "beeper",  // or "human"
  "version": 1,
  "tags": ["database", "timeout", "postgresql"]
}
```

### Template Structure

```
templates/knowledge/
├── index.html          # Full page: KB wiki index
├── entry.html          # Full page: Entry detail view
├── _entry_list.html    # HTMX partial: List of entries (for filtering)
├── _entry_card.html    # Component: Single entry card
└── _related.html       # HTMX partial: Related entries section
```

### Security Considerations

**Markdown XSS Prevention:**
- Use `bleach` library to sanitize HTML output from markdown
- Whitelist only safe HTML tags and attributes
- Never render raw HTML from user/LLM generated content

```python
import bleach
import markdown

ALLOWED_TAGS = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'em',
                'ul', 'ol', 'li', 'pre', 'code', 'blockquote', 'a', 'table',
                'thead', 'tbody', 'tr', 'th', 'td']
ALLOWED_ATTRIBUTES = {'a': ['href', 'title'], 'code': ['class']}

def render_markdown(content: str) -> str:
    html = markdown.markdown(content, extensions=['tables', 'fenced_code'])
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)
```

### Dependencies to Add

Add to `ui/pyproject.toml`:
```toml
[tool.poetry.dependencies]
markdown = "^3.5"
bleach = "^6.1"
```

### Project Structure Notes

**New files to create:**
```
ui/beeper_ui/
├── routes/
│   └── knowledge.py           # New: KB wiki routes
├── services/
│   └── kb_service.py          # New: KB business logic
├── templates/knowledge/
│   ├── index.html             # New: KB index page
│   ├── entry.html             # New: Entry detail page
│   ├── _entry_list.html       # New: Entry list partial
│   ├── _entry_card.html       # New: Entry card component
│   └── _related.html          # New: Related entries partial
```

**Files to modify:**
```
ui/beeper_ui/
├── app.py                     # Register knowledge blueprint
├── templates/base.html        # Add KB to navigation
├── static/css/main.css        # Add KB-specific styles
pyproject.toml                 # Add markdown, bleach dependencies
```

### Testing Strategy

**Route Tests:**
- Mock Qdrant client to return test data
- Test 200 response with correct template
- Test 404 for missing entry_id
- Test filter parameters work correctly

**Service Tests:**
- Mock Qdrant client calls
- Test pagination logic
- Test filter combinations

**Template Tests:**
- Test markdown rendering in isolation
- Test XSS prevention with malicious input

**Integration Tests (optional, requires Qdrant):**
- Full flow: create entry via script, view in wiki

### References

- [Source: architecture.md#Frontend Approach - HTMX + SSE]
- [Source: architecture.md#FR to Structure Mapping - FR16, FR36]
- [Source: architecture.md#Qdrant Naming - snake_case fields]
- [Source: epics.md#Story 2.1: KB Wiki Interface]
- [Source: 1-9-investigation-crd-pod-spawning.md - Previous patterns]
- [Source: scripts/init-collections.py - Knowledge collection schema]
- [Source: investigator/beeper_investigator/kb/client.py - Existing KB client]
- [Qdrant Python Client Docs](https://qdrant.tech/documentation/quick-start/)
- [HTMX Documentation](https://htmx.org/docs/)
- [Python Markdown Library](https://python-markdown.github.io/)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

N/A - All tests passed on first run

### Completion Notes List

1. Created `ui/beeper_ui/services/kb_service.py` - KBService class with methods for listing entries, getting single entries, filtering by service, and finding related entries
2. Created `ui/beeper_ui/utils/markdown_utils.py` - Safe markdown rendering with XSS protection using bleach
3. Created `ui/beeper_ui/routes/knowledge.py` - Flask blueprint with routes for KB index, entry detail, and related entries
4. Created 5 Jinja2 templates: index.html, entry.html, _entry_list.html, _entry_card.html, _related.html
5. Added comprehensive CSS styles for KB wiki interface matching existing UI patterns
6. Added "Knowledge Base" link to main navigation
7. Added markdown and bleach dependencies to pyproject.toml
8. Registered markdown Jinja2 filter in app.py
9. Created 44 new tests (16 for KB service, 12 for KB routes, 16 for markdown rendering)
10. All 75 UI tests pass (44 new + 31 existing)
11. All linting checks pass

### File List

**New Files Created:**
- `ui/beeper_ui/services/kb_service.py` - KB service layer (~200 lines)
- `ui/beeper_ui/utils/__init__.py` - Utils package init
- `ui/beeper_ui/utils/markdown_utils.py` - Markdown rendering utilities (~70 lines)
- `ui/beeper_ui/routes/knowledge.py` - KB routes blueprint (~100 lines)
- `ui/beeper_ui/templates/knowledge/index.html` - KB index page template
- `ui/beeper_ui/templates/knowledge/entry.html` - Entry detail page template
- `ui/beeper_ui/templates/knowledge/_entry_list.html` - Entry list partial
- `ui/beeper_ui/templates/knowledge/_entry_card.html` - Entry card component
- `ui/beeper_ui/templates/knowledge/_related.html` - Related entries partial
- `ui/tests/test_kb_service.py` - KB service tests (16 tests)
- `ui/tests/test_kb_routes.py` - KB routes tests (12 tests)
- `ui/tests/test_markdown.py` - Markdown rendering tests (16 tests)

**Files Modified:**
- `ui/pyproject.toml` - Added markdown and bleach dependencies
- `ui/beeper_ui/app.py` - Added markdown filter registration
- `ui/beeper_ui/routes/__init__.py` - Registered knowledge blueprint
- `ui/beeper_ui/services/__init__.py` - Exported KBService
- `ui/beeper_ui/templates/base.html` - Added Knowledge Base navigation link
- `ui/beeper_ui/static/css/main.css` - Added KB-specific styles (~200 lines)

## Code Review Record

### Review Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Issues Found

1. **Issue #2: Missing Type Stubs** (Low) - Added `types-bleach` and `types-Markdown` to dev dependencies
2. **Issue #3: Type Annotations** (Low) - Fixed generic types in `knowledge.py` routes
3. **Issue #4: OrderBy Direction** (Medium) - Changed from string "desc" to `Direction.DESC` enum
4. **Issue #5: Raw Markdown Preview** (Medium) - Added `strip_markdown` filter for card previews
5. **Issue #6: img src Security** (Medium) - Removed `img` tag from allowed tags to prevent data URL attacks

### Files Modified During Review

- `ui/pyproject.toml` - Added type stub dependencies
- `ui/beeper_ui/services/kb_service.py` - Fixed Direction enum, type annotations
- `ui/beeper_ui/routes/knowledge.py` - Fixed type annotations
- `ui/beeper_ui/utils/markdown_utils.py` - Added `strip_markdown`, removed img tag, added protocol filtering
- `ui/beeper_ui/utils/__init__.py` - Exported `strip_markdown`
- `ui/beeper_ui/templates/knowledge/_entry_card.html` - Use `strip_markdown` filter
- `ui/tests/test_markdown.py` - Added 15 new tests for `strip_markdown` and security

### Test Results After Review

- 87 UI tests pass (15 new tests added)
- All ruff checks pass
- mypy clean for KB module (1 pre-existing error in health.py)

## Change Log

- 2026-02-13: Story created by create-story workflow - ready for development
- 2026-02-13: Implemented all 7 tasks - KB wiki interface complete
  - Created KBService with Qdrant scroll/filter operations
  - Created markdown rendering with XSS protection
  - Created Flask routes and HTMX-powered templates
  - Added comprehensive CSS styling
  - Added 44 new tests, all passing
  - All 75 UI tests pass, all linting checks pass
- 2026-02-13: Code review completed - 5 issues found and fixed
  - Added type stubs for bleach and markdown
  - Fixed type annotations across routes and service
  - Fixed OrderBy to use Direction enum
  - Added strip_markdown filter for safe previews
  - Removed img tag for security (data URL attacks)
  - Added 15 new tests (87 total UI tests pass)
