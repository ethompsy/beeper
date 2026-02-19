# Story 2.7: Version Diff View

Status: done

## Story

As an **SRE**,
I want to compare versions of a KB entry,
So that I can see exactly what changed between versions.

## Acceptance Criteria

### AC1: Side-by-Side or Unified Diff View
**Given** I am viewing version history
**When** I select two versions to compare
**Then** I see a side-by-side or unified diff view (FR22)
**And** additions are highlighted in green
**And** deletions are highlighted in red

### AC2: Diff Navigation and Context Toggle
**Given** I am viewing a diff
**When** the changes are extensive
**Then** I can toggle between "changes only" and "full context"
**And** I can navigate between change hunks

### AC3: Correction Verification
**Given** Beeper made corrections based on human feedback
**When** I view the diff
**Then** I can see exactly what Beeper learned
**And** the diff helps me verify the correction was applied correctly

## Tasks / Subtasks

- [x] Task 1: Add diff generation to KBService (AC: #1, #3)
  - [x] 1.1: Add `generate_diff()` method to KBService using Python `difflib` (standard library, NO new dependencies)
  - [x] 1.2: Method accepts two version payloads and returns structured diff data (added/removed/unchanged lines)
  - [x] 1.3: Unified diff output format (AC allows "side-by-side or unified")
  - [x] 1.4: Handle edge cases: identical versions, empty content, missing versions

- [x] Task 2: Create diff route (AC: #1, #2, #3)
  - [x] 2.1: Add `GET /knowledge/<entry_id>/diff/<int:from_version>/<int:to_version>` route
  - [x] 2.2: Fetch both versions using existing `get_version()` method
  - [x] 2.3: Call `generate_diff()` and pass structured diff data to template
  - [x] 2.4: Return 404 if entry or either version not found
  - [x] 2.5: Pass version metadata (author, date, title) for diff header display

- [x] Task 3: Create diff template (AC: #1, #2)
  - [x] 3.1: Create `templates/knowledge/diff.html` with breadcrumb navigation
  - [x] 3.2: Render unified diff view as default with line-by-line additions (green) and deletions (red)
  - [x] 3.3: Add CSS-only toggle between "changes only" and "full context" using `:has()` pseudo-class pattern (NO JavaScript)
  - [x] 3.4: Add change hunk navigation (anchor links to each change section)
  - [x] 3.5: Show diff header: "Comparing version X → version Y" with version metadata

- [x] Task 4: Add diff entry points to existing templates (AC: #1)
  - [x] 4.1: Add "Compare" link on history page — each non-current version gets "Compare with current" link
  - [x] 4.2: Add "Compare with previous" link on version view page (next to Previous/Next navigation)

- [x] Task 5: Add diff CSS styles (AC: #1, #2)
  - [x] 5.1: Style diff container with monospace font for content comparison
  - [x] 5.2: Style additions (green background `#dcfce7`, left border `#22c55e`)
  - [x] 5.3: Style deletions (red background `#fee2e2`, left border `#ef4444`)
  - [x] 5.4: Style unchanged context lines (subtle gray)
  - [x] 5.5: Style change hunk separators and navigation
  - [x] 5.6: Style "changes only" / "full context" toggle (reuse CSS-only radio pattern from edit.html)

- [x] Task 6: Add tests (AC: all)
  - [x] 6.1: Test `generate_diff()` with content additions
  - [x] 6.2: Test `generate_diff()` with content deletions
  - [x] 6.3: Test `generate_diff()` with mixed changes
  - [x] 6.4: Test `generate_diff()` with identical content
  - [x] 6.5: Test diff route loads with correct diff data
  - [x] 6.6: Test diff route with non-existent entry returns 404
  - [x] 6.7: Test diff route with non-existent version returns 404
  - [x] 6.8: Test diff page shows additions highlighted
  - [x] 6.9: Test diff page shows "Comparing version X → Y" header
  - [x] 6.10: Test history page has "Compare" links

## Dev Notes

### Architecture Compliance

**Source:** [architecture.md - Frontend Approach]

> **MVP: HTMX + Server-Sent Events**
> - No JavaScript complexity
> - Flask-native, simple implementation

All diff UI MUST use server-rendered Flask templates with CSS-only interactivity. The "changes only" / "full context" toggle MUST use the `:has()` pseudo-class pattern (same as edit/preview toggle in Story 2.5). NO JavaScript.

### Critical Design Decision: Diff Algorithm

**Use Python `difflib` (standard library) — DO NOT add any new dependencies.**

`difflib` provides:
- `unified_diff()` for line-by-line unified diff output
- `SequenceMatcher` for computing similarity ratios
- `HtmlDiff` for side-by-side HTML diff (NOT recommended — generates its own HTML/CSS that conflicts with our styling)

**Recommended approach:** Use `difflib.unified_diff()` to generate line-by-line changes, then process the output into structured diff data for the template to render.

```python
import difflib

def generate_diff(old_content: str, new_content: str) -> list[dict]:
    """Generate structured diff data from two content strings.

    Returns list of diff sections (hunks), each containing:
    - lines: list of {type: 'add'|'remove'|'context', content: str}
    - start_old: starting line number in old version
    - start_new: starting line number in new version
    """
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(old_lines, new_lines, lineterm='')
    # Parse unified diff output into structured hunks
    # Lines starting with '+' = additions (green)
    # Lines starting with '-' = deletions (red)
    # Lines starting with ' ' = context (unchanged)
    # Lines starting with '@@' = hunk headers
```

### Diff Data Structure

```python
# Route passes this to template:
{
    "entry": KBEntry,          # Current live entry (for breadcrumb)
    "from_version": dict,      # Full version payload (older)
    "to_version": dict,        # Full version payload (newer)
    "hunks": [                 # Parsed diff hunks
        {
            "header": "@@ -10,5 +10,7 @@",
            "lines": [
                {"type": "context", "content": "unchanged line", "old_num": 10, "new_num": 10},
                {"type": "remove", "content": "deleted line", "old_num": 11, "new_num": None},
                {"type": "add", "content": "added line", "old_num": None, "new_num": 11},
            ]
        }
    ],
    "has_changes": bool,       # False if versions are identical
    "summary": str,            # e.g. "3 additions, 2 deletions"
}
```

### "Changes Only" vs "Full Context" Toggle

Use the **CSS-only radio button pattern** from Story 2.5 (edit/preview toggle):

```html
<!-- Hidden radio inputs -->
<input type="radio" id="mode-changes" name="diff_mode" class="diff-mode-radio" checked>
<input type="radio" id="mode-full" name="diff_mode" class="diff-mode-radio">

<!-- Tab labels -->
<label for="mode-changes" class="diff-tab">Changes Only</label>
<label for="mode-full" class="diff-tab">Full Context</label>

<!-- CSS-only visibility toggle -->
<div class="diff-section-changes"><!-- Shows only hunks with changes --></div>
<div class="diff-section-full"><!-- Shows ALL lines including unchanged --></div>
```

```css
/* CSS-only toggle using :has() */
.diff-mode-radio { position: absolute; opacity: 0; pointer-events: none; }
.diff-container:has(#mode-changes:checked) .diff-section-full { display: none; }
.diff-container:has(#mode-full:checked) .diff-section-changes { display: none; }
.diff-section-full { display: none; } /* Default: changes only */
```

### Route Pattern

```python
@knowledge_bp.route("/<entry_id>/diff/<int:from_version>/<int:to_version>")
def kb_diff(entry_id: str, from_version: int, to_version: int) -> tuple[str, int] | str:
```

This follows the same nested path pattern as `/history`, `/version/<n>`, `/restore/<n>`. No special route ordering needed (same as Story 2.6).

### Entry Points in Existing Templates

**history.html** — Add "Compare with current" link to each non-current version:
```html
{% if not v.is_current %}
<a href="{{ url_for('knowledge.kb_diff', entry_id=entry.entry_id, from_version=v.version, to_version=entry.version) }}"
   class="btn btn-secondary btn-sm">Compare</a>
{% endif %}
```

**version.html** — Add "Compare with previous" link in version navigation:
```html
{% if prev_version is not none %}
<a href="{{ url_for('knowledge.kb_diff', entry_id=entry.entry_id, from_version=prev_version, to_version=version_data.version) }}"
   class="btn btn-secondary btn-sm">Compare with Previous</a>
{% endif %}
```

### Existing Infrastructure to Reuse

**From kb_service.py:**
- `get_version(entry_id, version_num)` — returns full version payload including `content` field
- `list_versions(entry_id)` — returns version metadata (already used for navigation)
- `get_entry(entry_id)` — returns current live entry (for breadcrumb/header)

**From Story 2.6 code review fixes:**
- Version navigation uses actual version numbers (not arithmetic) — follow same pattern
- `_compute_change_summaries()` in routes for summary text

**CSS color patterns already in codebase:**
- Green success: `#dcfce7` bg, `#166534` text, `#22c55e` border (from `.version-badge-current`, `.import-success`)
- Red error: `#fee2e2` bg, `#991b1b` text, `#ef4444` border (from `.error-card`, `.edit-error`)

### Security Considerations

- Diff operates on stored content only (no user input in diff computation)
- Version numbers are integers validated by Flask's `<int:>` converter
- Content is already sanitized when rendered via the `|markdown` filter
- Diff lines shown as plain text (NOT rendered as HTML) to avoid XSS in diff display

### Performance Considerations

- `difflib.unified_diff()` is O(n*m) where n,m are line counts — acceptable for KB entries
- Both versions loaded with single Qdrant scroll each (already optimized)
- No embedding service needed (read-only operation)

### Project Structure Notes

**New files to create:**
```
ui/beeper_ui/
├── templates/knowledge/
│   └── diff.html                # New: Diff view page
```

**Files to modify:**
```
ui/beeper_ui/
├── services/kb_service.py       # Add generate_diff() method
├── routes/knowledge.py          # Add kb_diff route
├── templates/knowledge/
│   ├── history.html             # Add "Compare" link per version
│   └── version.html             # Add "Compare with previous" link
├── static/css/main.css          # Add diff styling
ui/tests/
├── test_kb_service.py           # Add generate_diff() tests
└── test_kb_routes.py            # Add diff route tests
```

### Testing Strategy

**Unit Tests (kb_service):**
- Mock-free tests for `generate_diff()` (pure function, no Qdrant dependency)
- Test with various content scenarios: additions, deletions, mixed, identical, empty

**Route Tests (kb_routes):**
- Mock `get_version()` and `get_entry()` as in Story 2.6
- Verify 404s for missing entries/versions
- Verify diff data passed to template contains expected structure
- Verify "Compare" links appear in history page

### Previous Story Learnings (2-6)

**Source:** [2-6-version-history.md - Code Review Record]

Key patterns to apply:
1. **CSS-only interactions:** Use `:has()` pseudo-class for toggle (no JavaScript)
2. **HTMX patterns:** Not needed for diff (read-only page), but follow existing nav patterns
3. **Test patterns:** Use `_make_entry()` helper, `@patch` for service mocking
4. **Version navigation:** Always use actual version numbers from list, never arithmetic
5. **Route patterns:** Nested paths under `/<entry_id>/` work fine with Flask routing
6. **Non-fatal errors:** Handle gracefully (e.g., if one version is missing, show error not crash)

### References

- [Source: architecture.md#Frontend Approach - HTMX, no JavaScript]
- [Source: architecture.md#Data Architecture - Qdrant collections]
- [Source: epics.md#Story 2.7: Version Diff View - AC and FR22]
- [Source: 2-6-version-history.md - Version storage, routes, templates, CSS patterns]
- [Source: 2-5-kb-entry-editing.md - CSS-only toggle pattern with :has()]
- [Python difflib documentation](https://docs.python.org/3/library/difflib.html)

---

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

None — all tests passed on first run.

### Completion Notes List

- Implemented `generate_diff()` as a module-level function in `kb_service.py` using `difflib.unified_diff()`. Parses unified diff output into structured hunks with line types (add/remove/context) and line numbers. Returns dict with `hunks`, `has_changes`, and `summary` fields.
- Added `kb_diff` route at `/<entry_id>/diff/<int:from_version>/<int:to_version>` with 404 handling for missing entry/versions.
- Created `diff.html` template with CSS-only `:has()` toggle for changes-only/full-context modes, hunk navigation via anchor links, and breadcrumb navigation.
- Added "Compare" link to `history.html` for non-current versions (links to diff vs current).
- Added "Compare with Previous" link to `version.html` in version navigation section.
- Added comprehensive diff CSS styles: monospace font for diff lines, green (#dcfce7) for additions, red (#fee2e2) for deletions, context lines in gray, hunk headers in indigo, toggle tabs matching existing pattern.
- 19 new tests added (11 unit + 8 route): all 254 tests pass, zero regressions.
- No new dependencies added — uses only Python standard library `difflib` and `re`.
- Diff content is rendered as plain text (not HTML/markdown) to prevent XSS.

### File List

**New:**
- `ui/beeper_ui/templates/knowledge/diff.html`

**Modified:**
- `ui/beeper_ui/services/kb_service.py` — Added `generate_diff()` function, imports for `difflib` and `re`
- `ui/beeper_ui/routes/knowledge.py` — Added `kb_diff` route, import for `generate_diff`
- `ui/beeper_ui/templates/knowledge/history.html` — Added "Compare" link for non-current versions
- `ui/beeper_ui/templates/knowledge/version.html` — Added "Compare with Previous" link
- `ui/beeper_ui/static/css/main.css` — Added diff view CSS styles
- `ui/tests/test_kb_service.py` — Added `TestGenerateDiff` class (11 tests)
- `ui/tests/test_kb_routes.py` — Added `TestKBDiffRoute` class (8 tests)

## Code Review Record

### Review Model Used

Claude Opus 4.6

### Findings (5 issues found, all fixed)

| # | Severity | Finding | Fix |
|---|----------|---------|-----|
| 1 | CRITICAL | "Compare with current" links always 404 — current live version isn't in `knowledge_versions` | Added `_entry_as_version()` fallback in `kb_diff` route to use live entry content when `get_version()` returns None for a version matching the live entry |
| 2 | HIGH | "Changes Only" / "Full Context" toggle was non-functional — both sections rendered identical content | Replaced duplicated DOM sections with single section; CSS `:has(#mode-changes:checked) .diff-line-context { display: none }` hides context lines in Changes Only mode |
| 3 | MEDIUM | `generate_diff()` incorrectly skipped content lines starting with `---`/`+++` (e.g., markdown horizontal rules) | Changed to skip only the first 2 lines (file headers) via index check instead of prefix matching |
| 4 | MEDIUM | Hunk navigation links targeted hidden anchors in Full Context mode | Resolved by Finding 2 fix (single section eliminates duplicate anchor IDs) |
| 5 | LOW | Task 1.3 marked [x] claimed "both unified and side-by-side" but only unified was implemented | Reworded task 1.3 to match AC ("side-by-side or unified") and actual implementation |

### Tests Added During Review

- `test_content_with_markdown_horizontal_rule` — verifies `---` content is preserved in diff (Finding 3)
- `test_diff_falls_back_to_live_entry_for_current_version` — verifies diff works when current version not in snapshots (Finding 1)
