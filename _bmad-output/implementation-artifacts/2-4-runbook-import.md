# Story 2.4: Runbook Import

Status: done

## Story

As an **SRE Lead**,
I want to import existing runbooks into the Knowledge Base,
So that Beeper has seed context for investigations.

## Acceptance Criteria

### AC1: Import Interface
**Given** I am on the Knowledge Base page
**When** I click "Import Runbook"
**Then** I see an import interface with:
- File upload option (markdown, text, or JSON)
- Paste content option (manual entry)
- Metadata fields: service, tags, entry type (pre-filled as "runbook")

### AC2: Markdown File Upload
**Given** I upload a markdown runbook file
**When** the import processes
**Then** the runbook is parsed and stored in Qdrant
**And** embeddings are generated for semantic search (FR13)
**And** the entry appears in the KB wiki with correct formatting

### AC3: Metadata Specification
**Given** I am importing a runbook
**When** I specify metadata (service, tags)
**Then** the metadata is saved with the entry
**And** the service dropdown is populated from existing KB services
**And** tags can be entered as comma-separated values

### AC4: Import Summary
**Given** I import runbooks (single or batch)
**When** import completes
**Then** I see a summary: "X entries imported, Y warnings"
**And** any parsing issues are reported with details
**And** I can navigate to imported entries

### AC5: Paste Content Import
**Given** I choose to paste content
**When** I paste markdown text and provide title + metadata
**Then** the content is imported as a new runbook entry
**And** the same embedding generation and storage occurs

### AC6: Duplicate Detection
**Given** a runbook with the same title and service already exists
**When** I attempt to import
**Then** I see a warning: "Similar entry exists"
**And** I can choose to: create new, skip, or update existing (creating new version)

## Tasks / Subtasks

- [x] Task 1: Extend KBService with write operations (AC: #2, #5)
  - [x] 1.1: Add `create_entry()` method to KBService for writing to Qdrant
  - [x] 1.2: Add `check_duplicate()` method using title+service similarity (AC: #6)
  - [x] 1.3: Add `update_entry()` method for version incrementing
  - [x] 1.4: Handle embedding generation on write using EmbeddingService

- [x] Task 2: Create import service (AC: #2, #4)
  - [x] 2.1: Create `ui/beeper_ui/services/import_service.py`
  - [x] 2.2: Add `parse_markdown_file()` function to extract content and metadata
  - [x] 2.3: Add `validate_import_data()` function for schema validation
  - [x] 2.4: Add `ImportResult` dataclass for tracking success/warnings

- [x] Task 3: Create import routes (AC: #1, #2, #3, #5)
  - [x] 3.1: Add `POST /knowledge/import` route for file upload
  - [x] 3.2: Add `POST /knowledge/import/paste` route for pasted content
  - [x] 3.3: Configure Flask for file uploads (MAX_CONTENT_LENGTH)
  - [x] 3.4: Add file type validation (markdown, text, json extensions)

- [x] Task 4: Create import UI (AC: #1, #3)
  - [x] 4.1: Create `templates/knowledge/import.html` import page
  - [x] 4.2: Add import button to KB index page
  - [x] 4.3: Create service dropdown populated from `get_available_services()`
  - [x] 4.4: Create tags input field (comma-separated)
  - [x] 4.5: Add HTMX form submission with progress indication

- [x] Task 5: Create import results UI (AC: #4)
  - [x] 5.1: Create `templates/knowledge/_import_result.html` partial
  - [x] 5.2: Display success count, warning count, and details
  - [x] 5.3: Add links to navigate to imported entries

- [x] Task 6: Handle duplicate detection UI (AC: #6)
  - [x] 6.1: Create `templates/knowledge/_import_duplicate.html` partial
  - [x] 6.2: Show existing entry preview when duplicate detected
  - [x] 6.3: Add action buttons: "Create New", "Skip", "Update Existing"

- [x] Task 7: Add tests (AC: all)
  - [x] 7.1: Test KBService write operations (create, update, duplicate check)
  - [x] 7.2: Test import service (markdown parsing, validation)
  - [x] 7.3: Test import routes (file upload, paste, validation errors)
  - [x] 7.4: Test duplicate detection flow
  - [x] 7.5: Test import result rendering

## Dev Notes

### Architecture Compliance

**Source:** [architecture.md - API Patterns]

> **API versioning:** `/api/v1/` base path for API routes
> **Query params:** `snake_case`

Import routes use knowledge blueprint prefix (`/knowledge/import`) following existing patterns.

**Source:** [architecture.md - Frontend Approach]

> **MVP: HTMX + Server-Sent Events**
> - No JavaScript complexity
> - Flask-native, simple implementation

Use HTMX for form submission and result updates:
- `hx-post` for import submission
- `hx-target` to update results area
- `hx-indicator` for loading state

### Existing Infrastructure

**From Story 2-2 and 2-3:**

EmbeddingService is already available:
```python
from beeper_ui.services.embedding_service import EmbeddingService, get_embedding_service

# Get singleton instance
embedding_service = get_embedding_service()

# Generate embedding
vector = embedding_service.get_embedding(content)
```

KBService already handles reading - extend with write operations.

**Qdrant Collections (from scripts/init-collections.py):**

The `knowledge` collection schema:
```python
"payload_indexes": [
    ("entry_id", PayloadSchemaType.KEYWORD),
    ("entry_type", PayloadSchemaType.KEYWORD),
    ("service", PayloadSchemaType.KEYWORD),
    ("created_at", PayloadSchemaType.DATETIME),
]
```

Writing to Qdrant:
```python
from qdrant_client.models import PointStruct
import uuid

point = PointStruct(
    id=str(uuid.uuid4()),
    vector=embedding_vector,  # 1536 dimensions
    payload={
        "entry_id": entry_id,
        "entry_type": "runbook",
        "title": title,
        "content": content,
        "service": service,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "author": "import",
        "version": 1,
        "tags": tags_list,
    }
)

client.upsert(
    collection_name=KNOWLEDGE_COLLECTION,
    points=[point],
)
```

### Flask File Upload Configuration

**config.py additions:**
```python
# Maximum upload size: 2MB
MAX_CONTENT_LENGTH = 2 * 1024 * 1024

# Allowed extensions
ALLOWED_EXTENSIONS = {'md', 'txt', 'json', 'markdown'}
```

**Route pattern for file upload:**
```python
from flask import request
from werkzeug.utils import secure_filename

@knowledge_bp.route("/import", methods=["GET", "POST"])
def kb_import():
    if request.method == "POST":
        file = request.files.get("file")
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            content = file.read().decode("utf-8")
            # Process content...
```

### Markdown Parsing

Use existing `markdown_utils.py` for XSS-safe rendering on display. For import parsing:

```python
def parse_markdown_file(content: str, filename: str) -> dict:
    """Parse markdown file, extracting front matter if present."""
    lines = content.split("\n")

    # Check for YAML front matter
    if lines[0].strip() == "---":
        end_idx = lines[1:].index("---") + 1
        front_matter = yaml.safe_load("\n".join(lines[1:end_idx]))
        content_body = "\n".join(lines[end_idx + 1:])
    else:
        front_matter = {}
        content_body = content

    # Extract title from first H1 if not in front matter
    if "title" not in front_matter:
        for line in lines:
            if line.startswith("# "):
                front_matter["title"] = line[2:].strip()
                break

    return {
        "title": front_matter.get("title", filename),
        "service": front_matter.get("service"),
        "tags": front_matter.get("tags", []),
        "content": content_body.strip(),
    }
```

### Duplicate Detection Strategy

Use semantic similarity + metadata matching:

```python
def check_duplicate(self, title: str, service: str) -> Optional[KBEntry]:
    """Check if a similar runbook already exists."""
    # First try exact title + service match
    results, _ = self.client.scroll(
        collection_name=KNOWLEDGE_COLLECTION,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="entry_type", match=MatchValue(value="runbook")),
                FieldCondition(key="service", match=MatchValue(value=service)),
            ]
        ),
        limit=100,
        with_payload=True,
    )

    # Check for title similarity (case-insensitive)
    for point in results:
        if point.payload.get("title", "").lower() == title.lower():
            return KBEntry.from_qdrant(point.id, point.payload)

    return None
```

### ImportResult Dataclass

```python
from dataclasses import dataclass, field

@dataclass
class ImportResult:
    """Result of a runbook import operation."""
    success: bool
    entry_id: Optional[str] = None
    title: str = ""
    warnings: list[str] = field(default_factory=list)
    error: Optional[str] = None
    duplicate_of: Optional[str] = None  # Entry ID if duplicate detected
```

### HTMX Import Form Pattern

```html
<form hx-post="{{ url_for('knowledge.kb_import') }}"
      hx-target="#import-result"
      hx-indicator="#import-loading"
      enctype="multipart/form-data">

    <!-- File upload or paste tabs -->
    <div class="import-tabs">
        <input type="radio" name="import_mode" value="file" id="mode-file" checked>
        <label for="mode-file">Upload File</label>

        <input type="radio" name="import_mode" value="paste" id="mode-paste">
        <label for="mode-paste">Paste Content</label>
    </div>

    <!-- File upload section -->
    <div id="file-section">
        <input type="file" name="file" accept=".md,.txt,.json,.markdown">
    </div>

    <!-- Paste section (hidden by default) -->
    <div id="paste-section" style="display: none;">
        <input type="text" name="title" placeholder="Runbook Title">
        <textarea name="content" placeholder="Paste markdown content..."></textarea>
    </div>

    <!-- Metadata (always visible) -->
    <select name="service">
        <option value="">Select service...</option>
        {% for svc in services %}
        <option value="{{ svc }}">{{ svc }}</option>
        {% endfor %}
    </select>

    <input type="text" name="tags" placeholder="Tags (comma-separated)">

    <button type="submit">Import Runbook</button>
    <div id="import-loading" class="htmx-indicator">Importing...</div>
</form>

<div id="import-result"></div>
```

### Security Considerations

**File Upload Validation:**
- Check file extension against whitelist
- Limit file size (MAX_CONTENT_LENGTH = 2MB)
- Use `secure_filename()` for any filename handling
- Decode as UTF-8, reject binary content
- Do NOT save files to disk - process in memory only

**Content Validation:**
- Sanitize markdown content on display (already done via markdown_utils)
- Validate service name against existing services OR allow new ones (decision: allow new)
- Validate tags as alphanumeric + hyphens + underscores
- Strip leading/trailing whitespace from all fields

**Input Validation:**
```python
def validate_import_data(
    title: str,
    content: str,
    service: Optional[str],
    tags: list[str],
) -> list[str]:
    """Validate import data, return list of warnings/errors."""
    errors = []

    if not title or len(title.strip()) < 3:
        errors.append("Title must be at least 3 characters")
    if len(title) > 200:
        errors.append("Title must be under 200 characters")

    if not content or len(content.strip()) < 10:
        errors.append("Content must be at least 10 characters")
    if len(content) > 100000:
        errors.append("Content exceeds maximum size (100KB)")

    # Validate tags (alphanumeric + hyphen + underscore)
    tag_pattern = re.compile(r'^[a-zA-Z0-9_-]+$')
    for tag in tags:
        if not tag_pattern.match(tag):
            errors.append(f"Invalid tag format: {tag}")

    return errors
```

### Project Structure Notes

**New files to create:**
```
ui/beeper_ui/
├── services/
│   └── import_service.py           # New: Import parsing and validation
├── templates/knowledge/
│   ├── import.html                  # New: Import page
│   ├── _import_result.html          # New: Import result partial
│   └── _import_duplicate.html       # New: Duplicate warning partial
```

**Files to modify:**
```
ui/beeper_ui/
├── services/kb_service.py           # Add create_entry, check_duplicate, update_entry
├── routes/knowledge.py              # Add import routes
├── templates/knowledge/index.html   # Add "Import" button
├── config.py                        # Add MAX_CONTENT_LENGTH
├── static/css/main.css              # Add import form styles
ui/tests/
├── test_kb_service.py               # Add write operation tests
├── test_kb_routes.py                # Add import route tests
└── test_import_service.py           # New: Import service tests
```

### Testing Strategy

**Unit Tests:**
- Mock Qdrant client for write operations
- Mock EmbeddingService for vector generation
- Test markdown parsing with various formats
- Test validation edge cases (empty, too long, invalid chars)
- Test duplicate detection logic

**Integration Tests:**
- Test import route with file upload (multipart form)
- Test import route with pasted content
- Test validation error responses
- Test duplicate detection UI flow
- Test HTMX partial rendering

### Previous Story Learnings (2-3)

**Source:** [2-3-structured-search-filtering.md - Code Review Record]

Key patterns to apply:
1. **Input validation:** Add validation functions with constants (like `VALID_ENTRY_TYPES`)
2. **Filter caching:** Use `clear_filter_cache()` after writes to refresh service list
3. **CSS-only interactions:** Prefer CSS over JavaScript where possible
4. **HTMX patterns:** Use `hx-include` for form fields, `hx-target` for result areas
5. **Test coverage:** Add tests for validation, error cases, and happy paths

### References

- [Source: architecture.md#API Patterns - File uploads]
- [Source: architecture.md#Frontend Approach - HTMX]
- [Source: epics.md#Story 2.4: Runbook Import]
- [Source: 2-3-structured-search-filtering.md - Patterns and learnings]
- [Flask File Uploads](https://flask.palletsprojects.com/en/3.0.x/patterns/fileuploads/)
- [HTMX Forms](https://htmx.org/docs/#forms)
- [Qdrant Upsert API](https://qdrant.tech/documentation/concepts/points/#upload-points)

---

## Dev Agent Record

**Status:** Implementation complete, code review passed
**Completion Date:** 2026-02-15
**Tests:** 212 passed (47 new tests added)

### Implementation Summary

All 7 tasks completed using TDD red-green-refactor cycle:

1. **Task 1 - KBService Write Operations:** Extended `kb_service.py` with `create_entry()`, `check_duplicate()`, and `update_entry()` methods. Includes embedding generation and filter cache invalidation.

2. **Task 2 - Import Service:** Created `import_service.py` with `parse_markdown_file()` (handles YAML front matter), `validate_import_data()`, `parse_tags()`, and `ImportResult` dataclass.

3. **Task 3 - Import Routes:** Added `kb_import()` route to `knowledge.py` handling both file upload and paste modes. Added `MAX_CONTENT_LENGTH` config and file extension validation.

4. **Task 4 - Import UI:** Created `import.html` with CSS-only tab switching, service dropdown, and tags input. Added "Import Runbook" button to KB index page.

5. **Task 5 - Import Results UI:** Created `_import_result.html` partial showing success/error states with navigation links.

6. **Task 6 - Duplicate Detection UI:** Created `_import_duplicate.html` partial with preview of existing entry and action buttons (Create New, Update Existing, Skip).

7. **Task 7 - Tests:** Added 47 new tests covering all functionality.

### Files Created
- `ui/beeper_ui/services/import_service.py`
- `ui/beeper_ui/templates/knowledge/import.html`
- `ui/beeper_ui/templates/knowledge/_import_result.html`
- `ui/beeper_ui/templates/knowledge/_import_duplicate.html`
- `ui/tests/test_import_service.py`

### Files Modified
- `ui/beeper_ui/services/kb_service.py` - Added write operations
- `ui/beeper_ui/routes/knowledge.py` - Added import route (before dynamic route)
- `ui/beeper_ui/config.py` - Added MAX_CONTENT_LENGTH
- `ui/beeper_ui/templates/knowledge/index.html` - Added import button
- `ui/beeper_ui/templates/knowledge/_search_results.html` - Added active filters include
- `ui/beeper_ui/static/css/main.css` - Added import form styles
- `ui/tests/test_kb_service.py` - Added 11 write operation tests
- `ui/tests/test_kb_routes.py` - Added 10 import route tests

### Key Implementation Notes
- Route ordering: Import route registered BEFORE dynamic `/<entry_id>` route to prevent path conflicts
- CSS-only tab switching using `:has()` pseudo-class (no JavaScript)
- HTMX form submission with `hx-post`, `hx-target`, `hx-indicator`
- Filter cache cleared on write operations to refresh service dropdown
- Duplicate detection uses case-insensitive title + service matching

---

## Code Review Record

**Review Date:** 2026-02-15
**Issues Found:** 2 High, 4 Medium, 3 Low
**Issues Fixed:** 6 (all High and Medium)

### Fixes Applied

1. **[HIGH] Missing is_configured() check for update path** - Added embedding service configuration check in update duplicate action path (`knowledge.py:304-314`)

2. **[HIGH] YAML front matter parsing edge case** - Added handling for missing closing `---` and broader exception catching (`import_service.py:100-103`)

3. **[MEDIUM] Undocumented file change** - Added `_search_results.html` to Files Modified list

4. **[MEDIUM] JavaScript onclick in template** - Converted to CSS-only tabs using `:has()` pseudo-class (`import.html:27-35`, `main.css:953-997`)

5. **[MEDIUM] Redundant duplicate check** - Added `duplicate_entry_id` hidden field to template and used it directly instead of re-querying (`_import_duplicate.html:35`, `knowledge.py:297-299`)

6. **[MEDIUM] Missing test coverage** - Added `test_import_update_not_configured` test (`test_kb_routes.py`)

### Low Issues (Not Fixed - Acceptable)
- Service name format validation: Allowing any string is acceptable for MVP
- Skip action messaging: Semantically a user choice, acceptable behavior
- Help text updated for clarity
