# Story 2.5: KB Entry Editing

Status: done

## Story

As an **SRE Lead**,
I want to directly edit Knowledge Base entries,
So that I can correct errors and add context.

## Acceptance Criteria

### AC1: Edit Button Access
**Given** I am viewing a KB entry
**When** I click "Edit"
**Then** I see a markdown editor with the entry content (FR17)
**And** I can modify title, content, and metadata

### AC2: Save Changes
**Given** I am editing an entry
**When** I save changes
**Then** the entry is updated in Qdrant
**And** embeddings are regenerated for the new content
**And** a new version is created (for history tracking)

### AC3: Preview Mode
**Given** I am editing
**When** I click "Preview"
**Then** I see the rendered markdown
**And** I can toggle between edit and preview modes

### AC4: Concurrent Viewing
**Given** another user is viewing the entry
**When** I save changes
**Then** they see the updated content on refresh
**And** no data is lost

## Tasks / Subtasks

- [x] Task 1: Create edit route and template (AC: #1)
  - [x] 1.1: Add `GET /knowledge/<entry_id>/edit` route to load edit form
  - [x] 1.2: Create `templates/knowledge/edit.html` with edit form
  - [x] 1.3: Add "Edit" button to entry detail page (`entry.html`)
  - [x] 1.4: Include title, content textarea, service dropdown, tags input

- [x] Task 2: Implement save functionality (AC: #2)
  - [x] 2.1: Add `POST /knowledge/<entry_id>/edit` route for saving
  - [x] 2.2: Validate form input (title, content required; validate tags format)
  - [x] 2.3: Call `KBService.update_entry()` with embedding regeneration
  - [x] 2.4: Display success message and redirect to entry view
  - [x] 2.5: Handle validation errors with inline error display

- [x] Task 3: Create edit/preview toggle (AC: #3)
  - [x] 3.1: Add preview section to edit template
  - [x] 3.2: Use CSS-only tab switching for edit/preview modes (like import.html)
  - [x] 3.3: Add HTMX for live preview rendering (`hx-post` to preview endpoint)
  - [x] 3.4: Create `POST /knowledge/preview` endpoint for markdown rendering

- [x] Task 4: Add edit form styles (AC: #1, #3)
  - [x] 4.1: Add CSS for edit form layout (full-width textarea, metadata row)
  - [x] 4.2: Style edit/preview tabs consistent with import tabs
  - [x] 4.3: Style preview pane to match entry content display

- [x] Task 5: Add tests (AC: all)
  - [x] 5.1: Test edit page loads with populated form data
  - [x] 5.2: Test save updates entry and increments version
  - [x] 5.3: Test validation errors display correctly
  - [x] 5.4: Test preview endpoint renders markdown
  - [x] 5.5: Test embedding service not configured error
  - [x] 5.6: Test entry not found error

## Dev Notes

### Architecture Compliance

**Source:** [architecture.md - Frontend Approach]

> **MVP: HTMX + Server-Sent Events**
> - No JavaScript complexity
> - Flask-native, simple implementation

Use HTMX for form submission and preview updates:
- `hx-post` for save and preview
- `hx-target` to update result/preview areas
- CSS-only tab switching (no JavaScript) using `:has()` pseudo-class

### Existing Infrastructure

**From Story 2-4 (runbook-import):**

`KBService.update_entry()` already exists and handles:
- Version incrementing
- Embedding regeneration
- Filter cache invalidation

```python
from beeper_ui.services.kb_service import KBService, KBServiceError

# Update entry with new content
kb_service = get_kb_service()
new_version = kb_service.update_entry(
    entry_id=entry_id,
    title=title,
    content=content,
    tags=tags,
    author="edit",
    embedding_service=embedding_service,
)
```

**Validation pattern from import_service.py:**

```python
from beeper_ui.services.import_service import validate_import_data, parse_tags

# Validate input
errors = validate_import_data(title, content, service, tags)
if errors:
    # Return form with errors
```

**CSS-only tabs pattern from import.html:**

```html
{# Radio inputs for tab state #}
<input type="radio" name="edit_mode" value="edit" id="mode-edit" class="edit-mode-radio" checked>
<input type="radio" name="edit_mode" value="preview" id="mode-preview" class="edit-mode-radio">

<div class="edit-tabs">
    <label for="mode-edit" class="edit-tab">Edit</label>
    <label for="mode-preview" class="edit-tab">Preview</label>
</div>

{# Sections shown/hidden via CSS :has() #}
<div class="edit-section edit-section-edit">
    <textarea name="content">{{ entry.content }}</textarea>
</div>
<div class="edit-section edit-section-preview">
    {{ preview_content|markdown }}
</div>
```

**CSS for tab switching (from main.css):**

```css
.edit-form:has(#mode-edit:checked) .edit-section-edit { display: block; }
.edit-form:has(#mode-edit:checked) .edit-section-preview { display: none; }
.edit-form:has(#mode-preview:checked) .edit-section-edit { display: none; }
.edit-form:has(#mode-preview:checked) .edit-section-preview { display: block; }
```

### Markdown Rendering

**Existing infrastructure:**

Use the `markdown` Jinja filter already available:
```html
{{ content|markdown }}
```

For preview endpoint, return rendered HTML:
```python
from beeper_ui.utils.markdown_utils import render_markdown

@knowledge_bp.route("/preview", methods=["POST"])
def kb_preview() -> str:
    content = request.form.get("content", "")
    return render_markdown(content)
```

### Edit Form Structure

```html
<form hx-post="{{ url_for('knowledge.kb_edit', entry_id=entry.entry_id) }}"
      hx-target="#edit-result"
      hx-swap="innerHTML"
      class="edit-form card">

    <div class="form-group">
        <label for="title">Title</label>
        <input type="text" name="title" id="title" value="{{ entry.title }}" required>
    </div>

    {# Edit/Preview tabs #}
    <input type="radio" name="edit_mode" value="edit" id="mode-edit" class="edit-mode-radio" checked>
    <input type="radio" name="edit_mode" value="preview" id="mode-preview" class="edit-mode-radio">
    <div class="edit-tabs">
        <label for="mode-edit" class="edit-tab">Edit</label>
        <label for="mode-preview" class="edit-tab">Preview</label>
    </div>

    <div class="edit-section edit-section-edit">
        <label for="content">Content (Markdown)</label>
        <textarea name="content" id="content" rows="20" required
                  hx-post="{{ url_for('knowledge.kb_preview') }}"
                  hx-trigger="change delay:500ms"
                  hx-target="#preview-content">{{ entry.content }}</textarea>
    </div>

    <div class="edit-section edit-section-preview">
        <div id="preview-content" class="entry-content">
            {{ entry.content|markdown }}
        </div>
    </div>

    <div class="edit-metadata">
        <div class="form-group">
            <label for="service">Service</label>
            <select name="service" id="service">
                <option value="">Select service...</option>
                {% for svc in services %}
                <option value="{{ svc }}" {% if entry.service == svc %}selected{% endif %}>{{ svc }}</option>
                {% endfor %}
            </select>
        </div>

        <div class="form-group">
            <label for="tags">Tags</label>
            <input type="text" name="tags" id="tags" value="{{ entry.tags|join(', ') }}"
                   placeholder="tag1, tag2, tag3">
            <p class="help-text">Comma-separated tags</p>
        </div>
    </div>

    <div class="edit-actions">
        <button type="submit" class="btn btn-primary">Save Changes</button>
        <a href="{{ url_for('knowledge.kb_entry', entry_id=entry.entry_id) }}" class="btn btn-secondary">Cancel</a>
        <span id="edit-loading" class="htmx-indicator">Saving...</span>
    </div>
</form>

<div id="edit-result"></div>
```

### Security Considerations

**Validation requirements:**
- Title: 3-200 characters, required
- Content: 10-100,000 characters, required
- Service: Optional, validated against existing services OR allow new
- Tags: Alphanumeric + hyphen + underscore only

**Embedding service check:**
```python
embedding_service = get_embedding_service()
if not embedding_service.is_configured():
    return render_template(
        "knowledge/_edit_result.html",
        error="Embedding service not configured. Set OPENAI_API_KEY to enable editing.",
    )
```

### Project Structure Notes

**New files to create:**
```
ui/beeper_ui/
├── templates/knowledge/
│   ├── edit.html                    # New: Edit page
│   └── _edit_result.html            # New: Edit result partial
```

**Files to modify:**
```
ui/beeper_ui/
├── routes/knowledge.py              # Add edit routes (GET/POST), preview route
├── templates/knowledge/entry.html   # Add "Edit" button
├── static/css/main.css              # Add edit form styles
ui/tests/
└── test_kb_routes.py                # Add edit tests
```

### Route Ordering Note

**Source:** [2-4-runbook-import.md - Dev Agent Record]

> Route ordering: Import route registered BEFORE dynamic `/<entry_id>` route

The edit route uses a nested path `/<entry_id>/edit`, which Flask will match correctly against the dynamic route. No special ordering required.

### Testing Strategy

**Unit Tests:**
- Mock KBService for update operations
- Mock EmbeddingService for embedding generation
- Test validation with various invalid inputs
- Test preview rendering

**Integration Tests:**
- Test edit page loads with entry data populated
- Test save flow (form submission → update → redirect)
- Test validation error display
- Test entry not found handling
- Test embedding service not configured

### Previous Story Learnings (2-4)

**Source:** [2-4-runbook-import.md - Code Review Record]

Key patterns to apply:
1. **is_configured() check:** Always check embedding service before write operations
2. **CSS-only tabs:** Use `:has()` pseudo-class, no JavaScript
3. **Validation:** Use existing `validate_import_data()` and `parse_tags()`
4. **HTMX patterns:** Use `hx-post`, `hx-target`, `hx-indicator`
5. **Service dropdown:** Populate from `get_available_services()`

### References

- [Source: architecture.md#Frontend Approach - HTMX]
- [Source: epics.md#Story 2.5: KB Entry Editing]
- [Source: 2-4-runbook-import.md - CSS-only tabs, validation patterns]
- [Source: kb_service.py#update_entry - Existing update method]
- [HTMX Forms](https://htmx.org/docs/#forms)

---

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

No blocking issues encountered during implementation.

### Completion Notes List

- Implemented GET/POST `/knowledge/<entry_id>/edit` route with full CRUD support
- Reused existing `validate_import_data()` and `parse_tags()` from import_service for input validation
- Reused existing `KBService.update_entry()` for saving with automatic version increment and embedding regeneration
- Created CSS-only edit/preview tab switching using `:has()` pseudo-class (consistent with import.html pattern)
- Added HTMX-powered live preview via `POST /knowledge/preview` endpoint using existing `render_markdown()`
- Added "Edit" button to entry detail page header
- Created `_edit_result.html` partial for HTMX inline success/error feedback
- All 8 test cases pass covering: form load, save flow, validation errors, preview rendering, embedding not configured, entry not found, service error on save, concurrent edit detection
- No new dependencies introduced

### Change Log

- 2026-02-16: Implemented KB entry editing (Story 2.5) - edit routes, templates, CSS, tests
- 2026-02-17: Code review fixes - added optimistic concurrency control (AC4), fixed HTMX preview trigger, renamed edit CSS classes, added 2 tests

### File List

New files:
- ui/beeper_ui/templates/knowledge/edit.html
- ui/beeper_ui/templates/knowledge/_edit_result.html

Modified files:
- ui/beeper_ui/routes/knowledge.py
- ui/beeper_ui/templates/knowledge/entry.html
- ui/beeper_ui/static/css/main.css
- ui/tests/test_kb_routes.py
- _bmad-output/implementation-artifacts/sprint-status.yaml
- _bmad-output/implementation-artifacts/2-5-kb-entry-editing.md

Unrelated changes in git (not part of this story):
- ui/beeper_ui/app.py (host/port config for app.run)
- ui/beeper_ui/config.py (default port 5000→5050)
- ui/.env.example (port change + FLASK_APP)
- local-testing.sh (deleted, moved to scripts/)
- scripts/demo.sh (new)
- scripts/local-testing.sh (new)
