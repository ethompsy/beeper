# Story 5.1: Conversational Corrections Interface

Status: ready-for-dev

## Story

As an **SRE Lead**,
I want to provide conversational corrections to Beeper through a chat-style interface on KB entries,
so that I can correct entries naturally without manual editing, and Beeper can learn from my feedback.

## Acceptance Criteria

1. **Given** I am viewing a KB entry, **When** I click "Suggest Correction" or open the correction panel, **Then** I see a chat-style interface for providing feedback (FR18). I can type natural language corrections like:
   - "The root cause wasn't the load balancer - it was a deployment that changed the health check timeout"
   - "Add that this only happens during peak traffic hours"
   - "Remove the section about database - that was a red herring"

2. **Given** I submit a conversational correction, **When** the correction is processed, **Then** I see "Processing correction..." status, **And** Beeper acknowledges the correction with a summary of understood changes.

3. **Given** Beeper misunderstands my correction, **When** I see the proposed changes, **Then** I can clarify or rephrase my correction, **And** the conversation continues until the correction is right.

4. **Given** corrections are submitted, **When** I view my correction history, **Then** I see past corrections I've made, **And** I can see which were applied and their impact.

## Tasks / Subtasks

- [ ] Task 1: Create corrections data model and storage (AC: #1, #4)
  - [ ] 1.1 Add `corrections` collection to Qdrant with schema: correction_id, entry_id, messages (list), status (pending/applied/rejected), created_at, updated_at
  - [ ] 1.2 Create `Correction` dataclass in `kb_service.py` with from_qdrant classmethod
  - [ ] 1.3 Add KBService methods: `create_correction()`, `get_corrections_for_entry()`, `update_correction()`, `add_correction_message()`
  - [ ] 1.4 Write unit tests for all new service methods

- [ ] Task 2: Create correction submission endpoint (AC: #1, #2)
  - [ ] 2.1 Add `POST /knowledge/<entry_id>/corrections` route to `knowledge.py` for submitting corrections
  - [ ] 2.2 Validate input (sanitize correction text, check entry exists)
  - [ ] 2.3 Create `CorrectionService` in `ui/beeper_ui/services/correction_service.py` that wraps LLM interaction
  - [ ] 2.4 Implement LLM prompt that takes entry content + user correction text and returns structured acknowledgment (summary of understood changes)
  - [ ] 2.5 Return HTMX partial `_correction_response.html` with acknowledgment
  - [ ] 2.6 Write route tests with mocked LLM and Qdrant

- [ ] Task 3: Build correction panel UI (AC: #1, #2)
  - [ ] 3.1 Create `templates/knowledge/_correction_panel.html` partial with chat-style layout
  - [ ] 3.2 Add "Suggest Correction" button to `entry.html` (after content section, line ~63)
  - [ ] 3.3 Use HTMX `hx-get` with `hx-trigger="click"` to lazy-load correction panel
  - [ ] 3.4 Implement chat message display (user messages right-aligned, Beeper responses left-aligned)
  - [ ] 3.5 Add correction input textarea with `hx-post` submission
  - [ ] 3.6 Add `hx-indicator` for "Processing correction..." loading state
  - [ ] 3.7 Add CSS styles for chat interface in `main.css`

- [ ] Task 4: Implement conversation flow (AC: #3)
  - [ ] 4.1 Add `POST /knowledge/<entry_id>/corrections/<correction_id>/reply` route for follow-up messages
  - [ ] 4.2 LLM prompt includes full conversation history for context continuity
  - [ ] 4.3 Each reply appends to the correction's messages list
  - [ ] 4.4 Response partial swaps into chat container, preserving history
  - [ ] 4.5 Write tests for multi-turn conversation flow

- [ ] Task 5: Build correction history view (AC: #4)
  - [ ] 5.1 Add `GET /knowledge/<entry_id>/corrections` route to list corrections for an entry
  - [ ] 5.2 Create `templates/knowledge/_correction_history.html` partial
  - [ ] 5.3 Display corrections with: date, first message preview, status badge (pending/applied/rejected)
  - [ ] 5.4 Add "Corrections" tab or link on entry detail page
  - [ ] 5.5 Write route tests for history listing

- [ ] Task 6: Integration testing and polish
  - [ ] 6.1 Test full flow: open panel → submit correction → see acknowledgment → reply → view history
  - [ ] 6.2 Test error cases: LLM unavailable, entry not found, empty correction text
  - [ ] 6.3 Verify no regressions in existing KB routes
  - [ ] 6.4 Run ruff + mypy on all changed files

## Dev Notes

### Architecture & Data Flow

**Correction Flow:**
1. User views KB entry → clicks "Suggest Correction"
2. HTMX lazy-loads correction panel (`hx-get`, `hx-trigger="click"`)
3. User types natural language correction → submits via `hx-post`
4. Route calls `CorrectionService.process_correction()` → calls LLM via `LlmClient.complete_sync()`
5. LLM returns structured acknowledgment of understood changes
6. Response rendered as `_correction_response.html` partial, swapped into chat container
7. User can reply for clarification → `hx-post` to reply endpoint
8. Correction stored in Qdrant `corrections` collection

**New CorrectionService** (`ui/beeper_ui/services/correction_service.py`):
- Wraps `LlmClient` from `beeper_investigator.llm.client`
- Uses `LlmConfig.from_env()` for configuration (env vars: `BEEPER_LLM_PROVIDER`, `BEEPER_LLM_MODEL`, `BEEPER_LLM_API_KEY`)
- `complete_sync()` for synchronous LLM calls (no async needed in Flask routes)
- Prompt engineering: system prompt with entry content, user message as correction
- Returns structured dict: `{"summary": str, "understood_changes": list[str]}`

### Existing Code to Reuse (DO NOT RECREATE)

| Component | Location | What to Reuse |
|-----------|----------|---------------|
| KB entry detail view | `ui/beeper_ui/routes/knowledge.py:976-1016` (`kb_entry()`) | Add correction panel trigger here |
| Entry template | `ui/beeper_ui/templates/knowledge/entry.html:61-63` | Add correction button after content |
| KBService | `ui/beeper_ui/services/kb_service.py` | Extend with correction methods, reuse Qdrant patterns |
| KBEntry dataclass | `ui/beeper_ui/services/kb_service.py:71-121` | Pattern for Correction dataclass |
| LlmClient | `investigator/beeper_investigator/llm/client.py:169-454` | `complete_sync()` for LLM calls |
| LlmConfig | `investigator/beeper_investigator/llm/client.py:25-146` | `from_env()` for config |
| Embedding service | `ui/beeper_ui/services/embedding_service.py` | Pattern for singleton service |
| HTMX form patterns | `ui/beeper_ui/templates/knowledge/edit.html:34-38` | `hx-post`, `hx-target`, `hx-indicator` |
| Result partials | `ui/beeper_ui/templates/knowledge/_edit_result.html` | Pattern for response feedback |
| Confirmation flow | `ui/beeper_ui/templates/investigations/_confirmation_form.html` | Most conversational UI pattern in codebase |
| Badge system | `ui/beeper_ui/static/css/main.css` | Status badges for correction states |
| Input sanitization | `ui/beeper_ui/routes/knowledge.py:48-70` (`sanitize_query()`) | Reuse for correction text |
| Blueprint registration | `ui/beeper_ui/routes/__init__.py:6-20` | No new blueprint needed; add routes to knowledge_bp |

### Anti-Patterns to Avoid

- **DO NOT** create a separate Flask Blueprint for corrections — add routes to existing `knowledge_bp`
- **DO NOT** use JavaScript for the chat interface — use HTMX + CSS only (project convention)
- **DO NOT** use async in Flask routes — use `LlmClient.complete_sync()` not `complete()`
- **DO NOT** import Django, React, or any frontend framework — Flask + HTMX + Jinja2 only
- **DO NOT** create a new Qdrant client wrapper — reuse patterns from `KBService`
- **DO NOT** skip `finally: svc.close()` for service cleanup
- **DO NOT** use redirects after form submission — return HTMX partials (project convention)
- **DO NOT** hardcode URLs — use `url_for()` in templates

### HTMX Patterns to Follow

```html
<!-- Correction panel lazy load -->
<button hx-get="{{ url_for('knowledge.kb_corrections_panel', entry_id=entry.entry_id) }}"
        hx-target="#correction-panel"
        hx-swap="innerHTML"
        class="btn btn-secondary">Suggest Correction</button>

<!-- Correction submission -->
<form hx-post="{{ url_for('knowledge.kb_submit_correction', entry_id=entry.entry_id) }}"
      hx-target="#correction-chat"
      hx-swap="beforeend"
      hx-indicator="#correction-loading">
  <textarea name="correction_text" placeholder="Describe what should be changed..." required></textarea>
  <button type="submit">Send</button>
  <span id="correction-loading" class="htmx-indicator">Processing correction...</span>
</form>
```

### Qdrant Collection Schema

**Collection: `corrections`**
```python
# Point payload schema
{
    "correction_id": str,       # UUID
    "entry_id": str,            # FK to knowledge entry
    "messages": [               # Conversation history
        {
            "role": "user" | "assistant",
            "content": str,
            "timestamp": str    # ISO 8601
        }
    ],
    "status": "pending" | "applied" | "rejected",
    "summary": str | None,      # LLM-generated summary of changes
    "created_at": str,          # ISO 8601
    "updated_at": str           # ISO 8601
}
```

No vector embeddings needed for corrections collection — use payload-only points with `models.Distance.COSINE` and dimension 1 (dummy vector) since we only need payload storage and filtering.

### Testing Standards

- **Framework**: pytest with Flask test client
- **Mocking**: `unittest.mock.MagicMock` for Qdrant client, `unittest.mock.patch` for LLM calls
- **Test file**: `ui/tests/test_corrections.py`
- **Coverage expectations**: All routes tested for both success and error paths
- **HTMX testing**: Test both full-page and `HX-Request: true` header responses
- **Error cases**: LLM unavailable (graceful degradation), entry not found (404), empty input (400), Qdrant errors (500)
- **Pattern**: Follow `ui/tests/test_knowledge_routes.py` structure

### CSS Chat Interface

Follow existing badge/card patterns from `main.css`. Chat messages:
- User messages: right-aligned, accent background
- Beeper messages: left-aligned, neutral background
- Status indicators: use existing `.htmx-indicator` pattern
- Correction status badges: reuse `.entry-type-badge` pattern with new `badge-pending`, `badge-applied`, `badge-rejected` variants

### Project Structure Notes

- All new routes go in existing `ui/beeper_ui/routes/knowledge.py` (extend, don't create new blueprint)
- New service file: `ui/beeper_ui/services/correction_service.py` (follows singleton pattern from `embedding_service.py`)
- New templates: `ui/beeper_ui/templates/knowledge/_correction_panel.html`, `_correction_response.html`, `_correction_history.html`
- New tests: `ui/tests/test_corrections.py`
- CSS additions in existing `ui/beeper_ui/static/css/main.css`

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 5, Story 5.1]
- [Source: _bmad-output/planning-artifacts/prd.md#FR18]
- [Source: _bmad-output/planning-artifacts/architecture.md#Knowledge Base, LLM Integration]
- [Source: ui/beeper_ui/routes/knowledge.py - KB routes]
- [Source: ui/beeper_ui/services/kb_service.py - KB service layer]
- [Source: investigator/beeper_investigator/llm/client.py - LLM client]
- [Source: ui/beeper_ui/templates/investigations/_confirmation_form.html - Conversational UI pattern]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

### File List
