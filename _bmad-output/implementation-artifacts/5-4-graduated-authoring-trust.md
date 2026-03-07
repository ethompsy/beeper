# Story 5.4: Graduated Authoring Trust

Status: done

## Story

As **Beeper**,
I want to publish entries directly as trust is established,
so that validated accurate documentation flows faster while maintaining quality.

## Acceptance Criteria

1. **Given** Beeper creates a new KB entry, **When** trust level is "new" (default), **Then** the entry is marked "Draft - Awaiting Review" **And** SRE must approve before it becomes active.

2. **Given** Beeper's entries for a service have high accuracy, **When** trust metrics meet threshold (>90% accuracy over 10+ entries), **Then** trust level graduates to "trusted" for that service **And** future entries are published directly (still versioned).

3. **Given** trust level is "trusted", **When** Beeper publishes directly, **Then** the entry is immediately visible **And** it's flagged as "Auto-published" for transparency **And** SREs can still review and correct.

4. **Given** a directly published entry is corrected, **When** the correction is significant, **Then** trust level may be re-evaluated **And** trust can be downgraded if accuracy drops.

5. **Given** trust levels exist, **When** an SRE Lead views trust settings, **Then** they see:
   - Per-service trust levels
   - Accuracy metrics backing the trust level
   - Option to manually adjust trust

## Tasks / Subtasks

- [x] Task 1: Extend data model for trust (AC: #1, #3)
  - [x] 1.1 Add `auto_published` (bool, default False) field to KBEntry — extend `from_qdrant()` classmethod at `kb_service.py:105-132`
  - [x] 1.2 Create `ServiceTrustLevel` dataclass in `kb_service.py` with fields: service_name, trust_level ("draft"|"trusted"), accuracy_pct, total_entries, reviewed_entries, correct_entries, last_updated, manually_adjusted (bool), manual_reason (str)
  - [x] 1.3 Create `ServiceTrustLevel.from_qdrant()` classmethod following LearningPattern pattern
  - [x] 1.4 Add `SERVICE_TRUST_COLLECTION = "service_trust_levels"` constant
  - [x] 1.5 Add collection to `scripts/init-collections.py` with payload indexes: service_name, trust_level
  - [x] 1.6 Write unit tests for dataclass construction and defaults

- [x] Task 2: Trust level CRUD in KBService (AC: #2, #4, #5)
  - [x] 2.1 Add `get_service_trust(service_name)` → returns ServiceTrustLevel or None
  - [x] 2.2 Add `upsert_service_trust(service_name, trust_level, accuracy_pct, ...)` → creates or updates trust record
  - [x] 2.3 Add `get_all_service_trusts()` → returns list of all ServiceTrustLevel records
  - [x] 2.4 Add `set_manual_trust_override(service_name, trust_level, reason)` → manually set trust level
  - [x] 2.5 Write unit tests for all 4 methods (mock Qdrant)

- [x] Task 3: Accuracy calculation and trust graduation logic (AC: #2, #4)
  - [x] 3.1 Add `calculate_service_accuracy(service_name)` method to KBService — counts total entries for service (from knowledge collection), entries that had corrections applied (entries with learning patterns from `learning_patterns` collection), returns accuracy metrics dict
  - [x] 3.2 Add `evaluate_trust_graduation(service_name)` method — calls `calculate_service_accuracy()`, applies graduation threshold (>=10 reviewed, >=90% accuracy → "trusted"), applies downgrade threshold (<80% accuracy → "draft"), upserts result
  - [x] 3.3 Hook `evaluate_trust_graduation()` into `kb_apply_revision()` route — after learning patterns are created, re-evaluate trust for that service (non-blocking, same try/except pattern as learning hook)
  - [x] 3.4 Write unit tests for accuracy calculation and trust graduation/downgrade logic

- [x] Task 4: Auto-publish integration (AC: #1, #3)
  - [x] 4.1 Add `should_auto_publish(service_name)` convenience method to KBService — checks if service trust level is "trusted"
  - [x] 4.2 Modify `create_entry()` in KBService — when author is "beeper" or "investigation", query trust level, set `auto_published=True` if trusted, add `auto_published` to entry payload
  - [x] 4.3 Ensure entries with `auto_published=False` are still visible in listing (no filtering) — the "Draft" status is purely informational for this story
  - [x] 4.4 Write tests for auto-publish flag setting on entry creation

- [x] Task 5: Trust settings UI (AC: #5)
  - [x] 5.1 Add `GET /knowledge/trust-settings` route — renders trust settings page with all service trust levels and accuracy metrics
  - [x] 5.2 Create `templates/knowledge/trust_settings.html` — full page with per-service trust cards showing: trust level badge, accuracy percentage bar, entry counts, last updated, manual override form
  - [x] 5.3 Add `POST /knowledge/trust-settings/<service_name>/override` route — accepts trust_level and reason form data, calls `set_manual_trust_override()`
  - [x] 5.4 Create `templates/knowledge/_trust_override_result.html` — HTMX partial returned after override
  - [x] 5.5 Add "Trust Settings" navigation link to KB index.html (next to "Learning Insights")
  - [x] 5.6 Add auto-published badge to entry.html — show "Auto-published" indicator when entry.auto_published is True
  - [x] 5.7 Add CSS for trust settings page (trust cards, accuracy bars, trust badges)
  - [x] 5.8 Write route tests for trust settings page and override

- [x] Task 6: Integration testing and polish
  - [x] 6.1 Test full flow: entries created → corrections applied → trust graduates → next entry auto-published
  - [x] 6.2 Test trust downgrade: trusted service → corrections drop accuracy → trust reverts to draft
  - [x] 6.3 Test manual override: SRE manually sets trust level
  - [x] 6.4 Test error cases: Qdrant unavailable, no entries for service, trust evaluation fails non-blocking
  - [x] 6.5 Verify no regressions in existing KB, correction, revision, and learning routes
  - [x] 6.6 Run ruff + mypy on all changed files

## Dev Notes

### Architecture & Data Flow

**Trust System Flow:**
1. Beeper creates KB entry via `create_entry()` (from investigation documentation step or runbook import)
2. `create_entry()` checks service trust: `get_service_trust(entry.service)` → if "trusted", set `auto_published=True` in entry payload
3. SRE reviews entries → applies corrections via story 5-1/5-2 workflow
4. When revision is applied (story 5-2), learning patterns are created (story 5-3)
5. After learning patterns created, `evaluate_trust_graduation()` is called (non-blocking)
6. Trust graduation checks: >=10 entries reviewed, >=90% accuracy → upgrade to "trusted"
7. Trust downgrade checks: <80% accuracy on recent entries → downgrade to "draft"

**Accuracy Metric Calculation:**
```
total_entries = count entries in 'knowledge' collection for service (author="beeper" or "investigation")
entries_with_corrections = count unique entry_ids in 'learning_patterns' collection for service
correct_entries = total_entries - entries_with_corrections
accuracy_pct = correct_entries / total_entries * 100 (if total > 0)
```

**Trust Level State Machine:**
```
         >=10 reviewed, >=90% accuracy
"draft" ──────────────────────────────→ "trusted"
  ↑                                        │
  │      <80% accuracy or manual           │
  └────────────────────────────────────────┘
```

### Existing Code to Reuse (DO NOT RECREATE)

| Component | Location | What to Reuse |
|-----------|----------|---------------|
| KBEntry dataclass | `ui/beeper_ui/services/kb_service.py:83-132` | Extend with `auto_published` field |
| KBEntry.from_qdrant() | `ui/beeper_ui/services/kb_service.py:105-132` | Add `auto_published` extraction |
| LearningPattern | `ui/beeper_ui/services/kb_service.py:179-205` | Query for accuracy calculation |
| get_learning_patterns() | `ui/beeper_ui/services/kb_service.py:1421-1478` | Filter by service for accuracy |
| create_learning_pattern() | `ui/beeper_ui/services/kb_service.py:1356-1419` | Hook trust re-eval after |
| Learning hook in apply | `ui/beeper_ui/routes/knowledge.py:1391-1421` | Add trust re-eval after learning |
| create_entry() | `ui/beeper_ui/services/kb_service.py` | Modify to set auto_published |
| KB index template | `ui/beeper_ui/templates/knowledge/index.html` | Add Trust Settings nav link |
| entry.html | `ui/beeper_ui/templates/knowledge/entry.html` | Add Auto-published badge |
| learning.html patterns | `ui/beeper_ui/templates/knowledge/learning.html` | Reuse card, bar, grid patterns |
| Learning CSS styles | `ui/beeper_ui/static/css/main.css` | Reuse category-bar, badge patterns |
| init-collections.py | `scripts/init-collections.py` | Add service_trust_levels collection |
| HTMX form patterns | `ui/beeper_ui/templates/knowledge/edit.html` | hx-post, hx-target, hx-indicator |
| Route test patterns | `ui/tests/test_learning.py` | Mock helpers, Flask test client patterns |

### Anti-Patterns to Avoid

- **DO NOT** create a separate TrustService — keep trust methods in KBService (it's all Qdrant data, same client)
- **DO NOT** create a new Flask Blueprint — add routes to existing `knowledge_bp`
- **DO NOT** use JavaScript for the UI — CSS-only bars/badges (project convention)
- **DO NOT** use async in Flask routes — use synchronous Qdrant calls
- **DO NOT** make trust evaluation blocking in the apply route — wrap in try/except like learning hook
- **DO NOT** filter out draft entries from KB listing — "draft" is informational only for this story
- **DO NOT** modify investigator code — this story only affects the UI layer
- **DO NOT** create separate accuracy models — calculate on-demand from existing collections
- **DO NOT** skip `auto_published` field backward compatibility — default to False for existing entries

### Qdrant Collection Schema

**Collection: `service_trust_levels`**
```python
# Point payload schema
{
    "service_name": str,        # e.g., "api-gateway", "auth-service"
    "trust_level": str,         # "draft" | "trusted"
    "accuracy_pct": float,      # 0.0-100.0
    "total_entries": int,       # Total entries by Beeper for this service
    "reviewed_entries": int,    # Entries that were reviewed (had corrections or confirmations)
    "correct_entries": int,     # Entries without corrections
    "last_updated": str,        # ISO 8601
    "manually_adjusted": bool,  # True if admin override
    "manual_reason": str,       # Reason for manual override
}
```

No vector embeddings needed — use payload-only points with `models.Distance.COSINE` and dimension 1 (dummy vector `[0.0]`).

### Testing Standards

- **Framework**: pytest with Flask test client
- **Mocking**: `unittest.mock.MagicMock` for Qdrant client, `unittest.mock.patch` for service calls
- **Test file**: `ui/tests/test_trust.py` (new file)
- **Coverage expectations**: All routes tested for success and error paths
- **HTMX testing**: Test both full-page and `HX-Request: true` header responses
- **Error cases**: Qdrant unavailable, no entries for service, trust evaluation fails non-blocking
- **Pattern**: Follow `ui/tests/test_learning.py` structure for test helpers and mocks

### Project Structure Notes

- Extend: `ui/beeper_ui/services/kb_service.py` (add ServiceTrustLevel dataclass, trust methods, extend KBEntry)
- Extend: `ui/beeper_ui/routes/knowledge.py` (add trust routes, hook trust eval into apply)
- New templates: `ui/beeper_ui/templates/knowledge/trust_settings.html`, `_trust_override_result.html`
- Modify templates: `ui/beeper_ui/templates/knowledge/entry.html` (auto-published badge), `index.html` (Trust Settings link)
- New tests: `ui/tests/test_trust.py`
- CSS additions in existing `ui/beeper_ui/static/css/main.css`
- Extend: `scripts/init-collections.py` (add service_trust_levels collection)

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 5, Story 5.4]
- [Source: _bmad-output/planning-artifacts/prd.md#FR23]
- [Source: _bmad-output/planning-artifacts/architecture.md#Knowledge Base]
- [Source: ui/beeper_ui/services/kb_service.py:83-132 - KBEntry dataclass]
- [Source: ui/beeper_ui/services/kb_service.py:179-205 - LearningPattern dataclass]
- [Source: ui/beeper_ui/services/kb_service.py:1356-1502 - Learning pattern methods]
- [Source: ui/beeper_ui/routes/knowledge.py:1391-1421 - Learning hook in apply route]
- [Source: ui/beeper_ui/templates/knowledge/learning.html - Learning insights UI patterns]
- [Source: ui/tests/test_learning.py - Test patterns and mock helpers]
- [Source: scripts/init-collections.py - Collection initialization patterns]
- [Source: _bmad-output/implementation-artifacts/5-3-learning-from-diffs.md - Previous story context]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- ServiceTrustLevel dataclass with from_qdrant(), auto_published field on KBEntry
- 7 KBService methods: get/upsert/get_all trust, manual override, accuracy calc, graduation eval, auto-publish check
- Trust graduation: >=10 entries + >=90% accuracy → "trusted"; <80% → downgrade to "draft"
- Manual overrides preserved (not auto-changed by graduation)
- Non-blocking trust re-evaluation hooked into kb_apply_revision route
- create_entry() auto-sets auto_published=True for beeper/investigation authors on trusted services
- Trust settings UI with per-service cards, accuracy bars, manual override forms (HTMX)
- Auto-published badge on entry detail page
- 48 new tests in test_trust.py covering all service methods, routes, and integration flows
- 557 total tests pass, ruff clean, mypy 17 errors (all pre-existing)

### Change Log

- Added ServiceTrustLevel dataclass and SERVICE_TRUST_COLLECTION constant
- Extended KBEntry with auto_published field (backward compatible, defaults False)
- Added 7 trust methods to KBService
- Modified create_entry() to check trust and set auto_published
- Added trust re-evaluation hook to kb_apply_revision route
- Added GET /knowledge/trust-settings and POST .../override routes
- Created trust_settings.html and _trust_override_result.html templates
- Added Trust Settings link to KB index.html
- Added auto-published badge to entry.html
- Added trust CSS styles to main.css
- Added service_trust_levels collection to init-collections.py

### File List

- `ui/beeper_ui/services/kb_service.py` (modified)
- `ui/beeper_ui/routes/knowledge.py` (modified)
- `ui/beeper_ui/templates/knowledge/trust_settings.html` (new)
- `ui/beeper_ui/templates/knowledge/_trust_override_result.html` (new)
- `ui/beeper_ui/templates/knowledge/entry.html` (modified)
- `ui/beeper_ui/templates/knowledge/index.html` (modified)
- `ui/beeper_ui/static/css/main.css` (modified)
- `ui/tests/test_trust.py` (new)
- `scripts/init-collections.py` (modified)
