# Story 5.3: Learning from Diffs

Status: done

## Story

As **Beeper**,
I want to learn from the diff between my documentation and human corrections,
So that I improve my future investigations and documentation.

## Acceptance Criteria

1. **Given** a human correction is applied, **When** the diff is recorded, **Then** Beeper analyzes the pattern of correction (FR20), **And** learns categories like:
   - Missing context I should have included
   - Incorrect correlations I made
   - Wrong conclusions from evidence
   - Unnecessary information I added

2. **Given** multiple corrections follow a pattern, **When** Beeper detects the pattern, **Then** investigation prompts are adjusted to address the gap, **And** future investigations incorporate the learning.

3. **Given** a correction is for a specific service, **When** learning is applied, **Then** service-specific context is weighted in future investigations, **And** the learning is scoped appropriately (not over-generalized).

4. **Given** learning is accumulated, **When** reviewing Beeper's improvement, **Then** SRE Leads can see:
   - Correction categories and frequencies
   - Areas where Beeper has improved
   - Remaining gaps in understanding

## Tasks / Subtasks

- [x] Task 1: Create learning data model and storage (AC: #1, #3)
  - [x] 1.1 Add `LEARNING_PATTERNS_COLLECTION = "learning_patterns"` constant to `kb_service.py`
  - [x] 1.2 Create `LearningPattern` dataclass in `kb_service.py` with fields: pattern_id, entry_id, correction_id, service_name, category (missing_context | incorrect_correlation | wrong_conclusion | unnecessary_info | other), description, original_snippet, corrected_snippet, created_at
  - [x] 1.3 Create `LearningPattern.from_qdrant()` classmethod following Correction pattern
  - [x] 1.4 Add KBService methods: `create_learning_pattern()`, `get_learning_patterns(service_name=None, category=None)`, `get_learning_summary()`
  - [x] 1.5 Write unit tests for all new service methods

- [x] Task 2: Create LearningService for diff analysis (AC: #1, #2)
  - [x] 2.1 Create `ui/beeper_ui/services/learning_service.py` with `LearningService` class following CorrectionService singleton pattern
  - [x] 2.2 Implement `analyze_correction(entry_content, revised_content, entry_title, service_name, correction_messages)` — uses LLM to analyze the diff and categorize the correction pattern(s)
  - [x] 2.3 Add ANALYSIS_SYSTEM_PROMPT_TEMPLATE that instructs LLM to identify correction categories, extract original/corrected snippets, and return structured JSON array of patterns
  - [x] 2.4 Implement `generate_prompt_adjustments(service_name=None)` — aggregates patterns into actionable prompt hints for investigation steps
  - [x] 2.5 Add ADJUSTMENT_SYSTEM_PROMPT_TEMPLATE for generating prompt adjustments from accumulated patterns
  - [x] 2.6 Write unit tests for both methods (mock litellm, test prompt construction, test JSON parsing)

- [x] Task 3: Hook learning into revision apply flow (AC: #1, #3)
  - [x] 3.1 Modify `kb_apply_revision()` route in `knowledge.py` — after successful apply, call `LearningService.analyze_correction()` in a try/except (non-blocking — learning failure should not block apply)
  - [x] 3.2 Store returned patterns via `KBService.create_learning_pattern()` for each identified pattern
  - [x] 3.3 Extract service_name from entry metadata (entry.metadata.get("service", "general"))
  - [x] 3.4 Write route tests verifying learning is triggered on apply and failures don't block apply

- [x] Task 4: Create learning insights UI (AC: #4)
  - [x] 4.1 Add `GET /knowledge/learning` route to `knowledge.py` — renders learning insights page
  - [x] 4.2 Create `templates/knowledge/learning.html` full page with: category breakdown chart (HTML/CSS bars), per-service pattern list, improvement trends
  - [x] 4.3 Add `GET /knowledge/learning/adjustments` route — returns current prompt adjustments as HTMX partial
  - [x] 4.4 Create `templates/knowledge/_learning_adjustments.html` partial showing accumulated prompt hints per service
  - [x] 4.5 Add "Learning Insights" navigation link to KB index/nav
  - [x] 4.6 Write route tests for both endpoints

- [x] Task 5: Implement prompt adjustment mechanism (AC: #2)
  - [x] 5.1 Add `get_prompt_context(service_name)` method to LearningService — retrieves accumulated learning patterns for a service and generates a concise prompt supplement
  - [x] 5.2 Store prompt adjustments in Qdrant (or generate on-demand from patterns) — adjustments are human-readable strings like "For service X: Always include deployment history when documenting outages"
  - [x] 5.3 Expose prompt adjustments via `GET /api/learning/prompt-context/<service_name>` endpoint for investigator integration
  - [x] 5.4 Write tests for prompt context generation and API endpoint

- [x] Task 6: Integration testing and polish
  - [x] 6.1 Test full flow: apply revision → learning patterns created → visible in insights → prompt adjustments generated
  - [x] 6.2 Test service-scoped learning: corrections for service A don't over-generalize to service B
  - [x] 6.3 Test error cases: LLM unavailable for analysis (doesn't block apply), no patterns yet (empty state UI)
  - [x] 6.4 Verify no regressions in existing correction and revision routes
  - [x] 6.5 Run ruff + mypy on all changed files

## Dev Notes

### Architecture & Data Flow

**Learning Flow (triggered on revision apply):**
1. SRE applies revision via `kb_apply_revision()` route (story 5-2)
2. After successful `update_entry()` + `update_correction(status="applied")`, trigger learning
3. Route calls `LearningService.analyze_correction(original_content, revised_content, title, service, messages)`
4. LLM analyzes the diff and returns structured JSON with categorized patterns
5. Each pattern stored in Qdrant `learning_patterns` collection via `KBService.create_learning_pattern()`
6. Learning is **non-blocking** — wrapped in try/except, failure logged but doesn't affect revision apply

**Prompt Adjustment Flow:**
1. LearningService aggregates patterns per service (or globally)
2. `generate_prompt_adjustments()` uses LLM to synthesize patterns into concise prompt hints
3. Prompt context available via API endpoint for investigator integration
4. Investigation steps can query `/api/learning/prompt-context/<service>` for supplemental context

**Learning Categories:**
| Category | Description | Example |
|----------|-------------|---------|
| `missing_context` | Information Beeper should have included | "Didn't mention deployment that happened 30 min before outage" |
| `incorrect_correlation` | Wrong signal correlation | "Blamed load balancer but root cause was health check timeout change" |
| `wrong_conclusion` | Incorrect root cause or resolution | "Concluded DB issue but was actually connection pool exhaustion" |
| `unnecessary_info` | Information that shouldn't have been included | "Included unrelated service metrics that added noise" |
| `other` | Doesn't fit above categories | Formatting, tone, structure corrections |

### Existing Code to Reuse (DO NOT RECREATE)

| Component | Location | What to Reuse |
|-----------|----------|---------------|
| CorrectionService (LLM patterns) | `ui/beeper_ui/services/correction_service.py` | `_complete_sync()`, `_parse_response()`, prompt template pattern, singleton pattern, litellm init |
| generate_diff() | `ui/beeper_ui/services/kb_service.py:174-263` | Diff data for analysis context |
| kb_apply_revision() | `ui/beeper_ui/routes/knowledge.py:1297-1388` | Hook learning trigger here |
| Correction dataclass | `ui/beeper_ui/services/kb_service.py:134-165` | Pattern for LearningPattern dataclass |
| get_correction_service() | `ui/beeper_ui/services/correction_service.py:341-353` | Singleton pattern for LearningService |
| KBEntry metadata | `ui/beeper_ui/services/kb_service.py:71-121` | Entry has `metadata` dict with service info |
| KB index template | `ui/beeper_ui/templates/knowledge/index.html` | Navigation pattern — add Learning link |
| Badge/bar CSS | `ui/beeper_ui/static/css/main.css` | Reuse for category breakdown visualization |
| HTMX partial patterns | `ui/beeper_ui/templates/knowledge/_correction_history.html` | Pattern for insights listing |
| Route test patterns | `ui/tests/test_corrections.py` | Test helpers, mock patterns, Flask test client |

### Anti-Patterns to Avoid

- **DO NOT** make learning synchronous/blocking in the apply route — wrap in try/except
- **DO NOT** create a separate Flask Blueprint — add routes to existing `knowledge_bp`
- **DO NOT** use JavaScript for visualization — use CSS-only bars/charts (project convention)
- **DO NOT** use async in Flask routes — use `_complete_sync()` pattern from CorrectionService
- **DO NOT** skip `finally: svc.close()` for service cleanup
- **DO NOT** over-generalize learnings across services — scope by service_name
- **DO NOT** create a new Qdrant client wrapper — reuse patterns from KBService
- **DO NOT** modify investigator code directly — expose prompt context via API endpoint
- **DO NOT** import from `beeper_investigator` — use litellm directly (UI venv doesn't have investigator package)

### LLM Prompt Design

**Diff Analysis Prompt:**
- System: "You are analyzing a Knowledge Base correction to identify patterns for learning. Compare the original and corrected content. Categorize each change into: missing_context, incorrect_correlation, wrong_conclusion, unnecessary_info, or other. Return ONLY a JSON array of patterns."
- User: Original content + revised content + correction conversation + diff summary
- Response format: `[{"category": "missing_context", "description": "...", "original_snippet": "...", "corrected_snippet": "..."}]`
- Temperature: 0.0 for consistency
- max_tokens: 2048

**Prompt Adjustment Generation:**
- System: "You are synthesizing correction patterns into actionable prompt hints for an AI SRE investigator. Based on accumulated learning patterns, generate concise, specific instructions that would prevent similar mistakes in future investigations."
- User: All patterns for a service (or globally) with categories and descriptions
- Response format: `{"adjustments": ["For service X: Always check deployment logs within 1 hour window", ...]}`
- Temperature: 0.0
- max_tokens: 1024

### Qdrant Collection Schema

**Collection: `learning_patterns`**
```python
# Point payload schema
{
    "pattern_id": str,       # UUID (lrn-XXXXXXXXXXXX)
    "entry_id": str,         # FK to knowledge entry that was corrected
    "correction_id": str,    # FK to correction that triggered learning
    "service_name": str,     # Service scope (or "general")
    "category": str,         # missing_context | incorrect_correlation | wrong_conclusion | unnecessary_info | other
    "description": str,      # Human-readable description of what was learned
    "original_snippet": str, # Relevant original text
    "corrected_snippet": str,# Relevant corrected text
    "created_at": str        # ISO 8601
}
```

No vector embeddings needed — use payload-only points with `models.Distance.COSINE` and dimension 1 (dummy vector `[0.0]`).

### Testing Standards

- **Framework**: pytest with Flask test client
- **Mocking**: `unittest.mock.MagicMock` for Qdrant client, `unittest.mock.patch` for litellm
- **Test file**: `ui/tests/test_learning.py` (new file)
- **Coverage expectations**: All routes tested for success and error paths
- **HTMX testing**: Test both full-page and `HX-Request: true` header responses
- **Error cases**: LLM unavailable (non-blocking), no patterns (empty state), invalid category
- **Pattern**: Follow `ui/tests/test_corrections.py` structure for test helpers and mocks
- **Mock helpers**: Create `_make_learning_pattern_payload()` similar to `_make_correction_payload()`

### Project Structure Notes

- New service: `ui/beeper_ui/services/learning_service.py` (singleton, litellm, follows CorrectionService pattern)
- Extend: `ui/beeper_ui/services/kb_service.py` (add LearningPattern dataclass, LEARNING_PATTERNS_COLLECTION, 3 new methods)
- Extend: `ui/beeper_ui/routes/knowledge.py` (hook into apply route, add 3 new routes)
- New templates: `ui/beeper_ui/templates/knowledge/learning.html`, `_learning_adjustments.html`
- Modify template: `ui/beeper_ui/templates/knowledge/index.html` (add Learning Insights nav link)
- New tests: `ui/tests/test_learning.py`
- CSS additions in existing `ui/beeper_ui/static/css/main.css` (category bars, insights styling)

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 5, Story 5.3]
- [Source: _bmad-output/planning-artifacts/prd.md#FR20]
- [Source: _bmad-output/planning-artifacts/architecture.md#Knowledge Base - Learning substrate]
- [Source: ui/beeper_ui/services/correction_service.py - CorrectionService LLM patterns, singleton]
- [Source: ui/beeper_ui/services/kb_service.py:174-263 - generate_diff()]
- [Source: ui/beeper_ui/services/kb_service.py:134-165 - Correction/CorrectionMessage dataclass patterns]
- [Source: ui/beeper_ui/routes/knowledge.py:1297-1388 - kb_apply_revision() hook point]
- [Source: ui/tests/test_corrections.py - test patterns and mock helpers]
- [Source: _bmad-output/implementation-artifacts/5-2-beeper-revision-processing.md - previous story context]
- [Source: _bmad-output/implementation-artifacts/5-1-conversational-corrections-interface.md - correction data model]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- Pre-existing mypy errors (17 in kb_service.py and knowledge.py) unchanged; zero new errors introduced
- Pre-existing ruff line-length errors (3 in knowledge.py) unchanged; all new code passes clean

### Completion Notes List

- Added LEARNING_PATTERNS_COLLECTION, LEARNING_CATEGORIES, LearningPattern dataclass to kb_service.py
- Added create_learning_pattern(), get_learning_patterns(), get_learning_summary() to KBService
- Created learning_service.py with LearningService class (singleton, litellm, analyze_correction, generate_prompt_adjustments, get_prompt_context)
- Hooked learning into kb_apply_revision() route (non-blocking try/except)
- Created learning.html full page with category bars, service breakdown, pattern list
- Created _learning_adjustments.html partial for HTMX lazy-loaded adjustments
- Added 3 new routes: kb_learning, kb_learning_adjustments, kb_learning_prompt_context
- Added "Learning Insights" button to KB index.html
- Added learning CSS styles to main.css
- Added API endpoint GET /api/learning/prompt-context/<service_name> for investigator integration
- 36 new tests across 7 test classes, all 508 tests pass (zero regressions)

### Change Log

- 2026-03-07: Implemented story 5-3 (Learning from Diffs) — all 6 tasks complete, 36 new tests, 508 total pass

### File List

- ui/beeper_ui/services/learning_service.py (new: LearningService with LLM diff analysis)
- ui/beeper_ui/services/kb_service.py (modified: added LearningPattern dataclass, learning methods)
- ui/beeper_ui/routes/knowledge.py (modified: added learning hook to apply, 3 new routes)
- ui/beeper_ui/templates/knowledge/learning.html (new: learning insights full page)
- ui/beeper_ui/templates/knowledge/_learning_adjustments.html (new: adjustments HTMX partial)
- ui/beeper_ui/templates/knowledge/index.html (modified: added Learning Insights button)
- ui/beeper_ui/static/css/main.css (modified: added learning CSS)
- ui/tests/test_learning.py (new: 36 tests for learning features)
