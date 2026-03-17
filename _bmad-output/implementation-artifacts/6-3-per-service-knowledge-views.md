# Story 6.3: Per-Service Knowledge Views

Status: review

## Story

As a **user**,
I want per-service knowledge views through service catalog integration,
so that I can see all institutional knowledge related to a specific service in one place.

## Acceptance Criteria

1. **Given** a user navigates to a service detail page (`/services/{name}/knowledge`) **When** the page loads **Then** all KB entries tagged with that service are displayed, sorted by relevance and recency **And** entries are grouped by category (root causes, runbooks, proven fixes, patterns)

2. **Given** the service knowledge view **When** filtered by validation status **Then** the user can view only "proven" entries, or only "AI-generated" entries needing review **And** entry counts per validation status are shown as filter badges

3. **Given** a service with no KB entries **When** the knowledge view loads **Then** a helpful empty state is shown: "No knowledge entries yet — entries are created automatically as investigations resolve"

## Tasks / Subtasks

- [x] Task 1: Add `get_service_knowledge_grouped()` method to `KBService` (AC: #1, #2)
  - [x]1.1 In `ui/beeper_ui/services/kb_service.py`, add `get_service_knowledge_grouped(self, service_name: str, validation_status: str | None = None, limit: int = 100) -> dict[str, list[KBEntry]]` method. Scrolls `knowledge` collection filtering by `service == service_name` (and optionally `validation_status`). Groups results into dict with keys: `"root_causes"` (entry_type=="investigation"), `"runbooks"` (entry_type=="runbook"), `"proven_fixes"` (entry_type=="proven_fix"), `"patterns"` (entry_type=="correction" or any other). Sort each group by `created_at` descending. Use Qdrant scroll with Filter(must=[...]) and OrderBy(key="created_at", direction=Direction.DESC).
  - [x]1.2 Add `get_service_validation_counts(self, service_name: str) -> dict[str, int]` method. Scrolls `knowledge` collection filtering by `service == service_name`, with_payload=["validation_status"]. Counts entries per validation_status value (AI-generated, human-confirmed, proven, corrected). Returns dict like `{"AI-generated": 5, "proven": 3, "human-confirmed": 2, "corrected": 1}`. Include a "total" key with total count.

- [x] Task 2: Add `/services/<service_name>/knowledge` route to knowledge blueprint (AC: #1, #2, #3)
  - [x]2.1 In `ui/beeper_ui/routes/knowledge.py`, add `service_knowledge(service_name)` route at `@knowledge_bp.route("/services/<service_name>/knowledge")`. URL-decode service_name. Call `get_kb_service()`. Fetch grouped entries via `kb_service.get_service_knowledge_grouped(service_name, validation_status=request.args.get("validation_status"))`. Fetch validation counts via `kb_service.get_service_validation_counts(service_name)`. Render `knowledge/service_knowledge.html` template with context: `service_name`, `groups` (the grouped dict), `validation_counts`, `active_filter` (current validation_status filter or None), `available_services` (from `get_available_services()`). Handle KBServiceError with flash message and redirect to KB index.
  - [x]2.2 The route must sanitize `service_name` input — use the existing `sanitize_query()` pattern to prevent injection. Verify the service exists in `get_available_services()` list; if not, return 404 page.

- [x] Task 3: Create `service_knowledge.html` template (AC: #1, #2, #3)
  - [x]3.1 Create `ui/beeper_ui/templates/knowledge/service_knowledge.html` extending `base.html`. Page title: "Knowledge — {service_name}". Breadcrumb: Knowledge > {service_name}. Include link back to `/knowledge` (main KB index).
  - [x]3.2 Add validation status filter badges section at top. Each badge shows: status label + count (e.g., "Proven (3)", "AI-generated (5)"). Clicking a badge filters to that status — link to `?validation_status=proven`. Active badge highlighted with different CSS class. Include "All ({total})" badge to clear filter. Use existing `status-badge` CSS patterns from `entry.html`.
  - [x]3.3 Add grouped sections for each category: "Root Causes", "Runbooks", "Proven Fixes", "Patterns". Each section header shows count. Each group renders entries using the existing `_entry_card.html` partial (or inline card pattern matching `_entry_card.html` style). Only show sections that have entries. Sections collapsible with details/summary HTML pattern.
  - [x]3.4 Add empty state (AC #3): When no entries exist (all groups empty), show centered message: "No knowledge entries yet — entries are created automatically as investigations resolve." with a subtle icon and link back to the main KB page.
  - [x]3.5 Add service summary sidebar or header: Show service name prominently, total entry count, validation status breakdown as a mini-chart or stat row, link to service investigations at `/investigations?service={service_name}`.

- [x] Task 4: Add service knowledge navigation links (AC: #1)
  - [x]4.1 In `ui/beeper_ui/templates/knowledge/_entry_card.html`, verify the service badge already links to the service knowledge view. If the service badge currently links to `?service={service}` (KB index filter), update it to link to `/knowledge/services/{service}/knowledge` instead for direct service knowledge view.
  - [x]4.2 In `ui/beeper_ui/templates/knowledge/entry.html`, add a link from the service badge to the per-service knowledge view at `/knowledge/services/{service}/knowledge`.
  - [x]4.3 In `ui/beeper_ui/templates/knowledge/index.html` or `_filter_panel.html`, add "View Service Knowledge" link next to each service in the filter dropdown or as a service list section.

- [x] Task 5: Write unit tests for `KBService` new methods (AC: #1, #2)
  - [x]5.1 In `ui/tests/test_kb_service.py`, add `TestGetServiceKnowledgeGrouped` class. Test: returns correctly grouped entries by entry_type. Test: filters by service_name correctly. Test: filters by validation_status when provided. Test: returns empty dict values when no entries in a group. Test: sorts entries by created_at descending within groups.
  - [x]5.2 Add `TestGetServiceValidationCounts` class. Test: counts entries per validation_status correctly. Test: returns total count. Test: returns all zeros for service with no entries. Test: handles entries with no validation_status (counts under "unknown" key).

- [x] Task 6: Write route tests for service knowledge view (AC: #1, #2, #3)
  - [x]6.1 In `ui/tests/test_routes_knowledge.py`, add `TestServiceKnowledgeRoute` class. Test: GET `/knowledge/services/payment-service/knowledge` returns 200 with grouped entries. Test: validation_status query param filters correctly. Test: renders validation count badges. Test: empty state shown when no entries. Test: returns 404 for unknown service. Test: service_name is sanitized.
  - [x]6.2 Add `TestServiceKnowledgeNavigation` — Test that entry card and entry detail pages include links to service knowledge views.

- [x] Task 7: Run full test suite across all components (AC: all)
  - [x]7.1 Run investigator tests: `cd investigator && poetry run python -m pytest`
  - [x]7.2 Run investigator linting: `cd investigator && poetry run ruff check .`
  - [x]7.3 Run investigator type checking: `cd investigator && poetry run mypy .`
  - [x]7.4 Run UI tests: `cd ui && poetry run python -m pytest`
  - [x]7.5 Run operator tests: `cd operator && cargo test`
  - [x]7.6 No regressions found

## Dev Notes

### Architecture Patterns (CRITICAL — must follow)

**FR40 maps to:** `ui/routes/knowledge.py` (service filter), `ui/services/kb_service.py` [Source: architecture.md#FR-to-Structure mapping, line 1426]

**Route structure:** The architecture specifies `knowledge.py` is extended with "service views" — add the route to the existing knowledge blueprint, NOT a new services blueprint. The URL pattern `/services/{name}/knowledge` from the acceptance criteria should be mounted under the knowledge blueprint prefix `/knowledge`, making the actual route `/knowledge/services/<service_name>/knowledge`.

**Category grouping maps to entry_type field:**
- `entry_type == "investigation"` → "Root Causes" group (these are auto-created from resolved investigations with root cause analysis)
- `entry_type == "runbook"` → "Runbooks" group (imported or manually created runbooks)
- `entry_type == "proven_fix"` → "Proven Fixes" group (from ProvenFixAccumulator, story 4-8)
- `entry_type == "correction"` → "Patterns" group (corrections represent learned patterns)
- Any other entry_type → "Patterns" group (catch-all)

**Validation status values** (from KnowledgeEntry schema):
- `"AI-generated"` — Auto-created by system, not yet reviewed
- `"human-confirmed"` — Reviewed and confirmed by SRE
- `"proven"` — Verified through repeated successful application
- `"corrected"` — Edited/corrected by user

**Filter badge pattern:** Use `<a href="?validation_status=proven" class="status-badge {% if active_filter == 'proven' %}active{% endif %}">Proven ({{ validation_counts.proven }})</a>` pattern. Follow existing badge CSS from `entry.html` validation status badges.

### Existing Code to Reuse (DO NOT RECREATE)

| Component | Location | What to Reuse |
|-----------|----------|---------------|
| KBService.list_recent_entries() | `ui/beeper_ui/services/kb_service.py:376` | Filter pattern with service + Qdrant scroll + OrderBy |
| KBService.list_entries_by_service() | `ui/beeper_ui/services/kb_service.py:472` | Already scrolls by service — extend for grouping |
| KBService.get_available_services() | `ui/beeper_ui/services/kb_service.py:648` | Service list for validation (404 check) |
| KBEntry.from_qdrant() | `ui/beeper_ui/services/kb_service.py:102` | Entry parsing from Qdrant point |
| KBEntry dataclass | `ui/beeper_ui/services/kb_service.py:84` | Has service, entry_type, validation_status fields |
| get_kb_service() | `ui/beeper_ui/routes/knowledge.py:101` | Factory for KBService instances |
| sanitize_query() | `ui/beeper_ui/routes/knowledge.py:60` | Input sanitization pattern |
| _entry_card.html | `ui/beeper_ui/templates/knowledge/_entry_card.html` | Card rendering for entries in groups |
| _filter_panel.html | `ui/beeper_ui/templates/knowledge/_filter_panel.html` | Service filter dropdown pattern |
| entry.html | `ui/beeper_ui/templates/knowledge/entry.html` | Validation status badge CSS pattern (lines 64-89) |
| base.html | `ui/beeper_ui/templates/base.html` | Base template with navigation, breadcrumbs |
| KNOWLEDGE_COLLECTION | `ui/beeper_ui/services/kb_service.py:33` | Collection name constant |
| Filter, FieldCondition, MatchValue, OrderBy, Direction | `ui/beeper_ui/services/kb_service.py` (imports) | Qdrant query building |

### Anti-Patterns to AVOID

- Do NOT create a new Flask blueprint for services — add route to existing `knowledge_bp` blueprint
- Do NOT create a new Qdrant collection — query existing `knowledge` collection with service filter
- Do NOT modify the investigator component — this is a UI-only story
- Do NOT modify the operator component — UI-only
- Do NOT duplicate KB entry rendering logic — reuse `_entry_card.html` partial
- Do NOT use vector search for the service view — use Qdrant scroll with field filters (exact match on service name)
- Do NOT break existing KB index page or filter functionality
- Do NOT hardcode service names — dynamically discover from `get_available_services()`
- Do NOT create a ServiceCatalog model/collection — services are inferred from KB entry `service` field

### Previous Story Intelligence (6-2)

**Key learnings from Story 6-2 (Bi-Directional KB-Investigation Links):**
- HTMX lazy loading pattern works well: `<div hx-get="..." hx-trigger="load">`
- KB entry card CSS pattern from `_entry_card.html` is the standard display unit
- Validation status badge already rendered in `_linked_kb.html` — reuse pattern
- `KBService.get_linked_kb_entries()` uses `should` filter (OR logic) — good reference for combined filters
- Code review found performance issue with triple Qdrant query — use single query with payload reuse where possible
- 3,122 tests pass across all components (941 investigator + 1,650 UI + 531 operator)

**Key patterns from 6-2 implementation:**
- Route pattern: `@knowledge_bp.route("/...")` with `get_kb_service()` factory
- Template context: pass data from service methods, render with Jinja2
- Test pattern: mock `KBService` methods in route tests, mock Qdrant in service tests
- URL generation: use `url_for('knowledge.endpoint_name', ...)` in templates

### Testing Standards

- **Framework:** pytest with unittest.mock for KBService, Qdrant
- **Test locations:**
  - `ui/tests/test_kb_service.py` — extend with service knowledge grouped + validation counts tests
  - `ui/tests/test_routes_knowledge.py` — extend with service knowledge route tests
- **Mocking:** `unittest.mock.patch` for Qdrant client, KBService methods
- **Coverage:** All new service methods, validation counts, grouped entries, empty states, filter parameters, template rendering, 404 for unknown service
- **Pattern reference:** Follow `ui/tests/test_kb_service.py` for KBService tests, `ui/tests/test_routes_knowledge.py` for route tests

### Project Structure Notes

**Files to CREATE:**
- `ui/beeper_ui/templates/knowledge/service_knowledge.html` — Per-service knowledge view template

**Files to MODIFY:**
- `ui/beeper_ui/services/kb_service.py` — Add `get_service_knowledge_grouped()`, `get_service_validation_counts()` methods
- `ui/beeper_ui/routes/knowledge.py` — Add `service_knowledge()` route
- `ui/beeper_ui/templates/knowledge/_entry_card.html` — Update service badge link to per-service view (if needed)
- `ui/beeper_ui/templates/knowledge/entry.html` — Add service knowledge view link
- `ui/tests/test_kb_service.py` — Add grouped + validation count tests
- `ui/tests/test_routes_knowledge.py` — Add service knowledge route tests

**Files to NOT touch:**
- `investigator/**` — No investigator changes needed (UI-only story)
- `operator/**` — No operator changes needed
- `ui/beeper_ui/services/kb_surfacing_service.py` — Handles live investigation surfacing, not service views
- `ui/beeper_ui/services/correction_service.py` — Corrections are a separate feature
- `ui/beeper_ui/routes/investigations.py` — Investigation routes stay unchanged
- `ui/beeper_ui/templates/knowledge/index.html` — Main KB index stays unchanged (just navigation links)

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 6.3] — Acceptance criteria and story statement
- [Source: _bmad-output/planning-artifacts/architecture.md#FR40] — `ui/routes/knowledge.py` (service filter), `ui/services/kb_service.py`
- [Source: _bmad-output/planning-artifacts/architecture.md#Knowledge Templates] — knowledge/ template directory structure
- [Source: _bmad-output/planning-artifacts/prd.md#FR40] — System can provide per-service knowledge views through service catalog integration
- [Source: _bmad-output/planning-artifacts/prd.md#NFR20] — KB capacity: 10,000+ entries with < 2 second semantic search
- [Source: ui/beeper_ui/services/kb_service.py:376] — list_recent_entries() scroll + filter pattern
- [Source: ui/beeper_ui/services/kb_service.py:472] — list_entries_by_service() existing method
- [Source: ui/beeper_ui/services/kb_service.py:648] — get_available_services() service discovery
- [Source: ui/beeper_ui/services/kb_service.py:84] — KBEntry dataclass with service, entry_type, validation_status
- [Source: ui/beeper_ui/routes/knowledge.py:36] — knowledge_bp blueprint
- [Source: ui/beeper_ui/templates/knowledge/_entry_card.html] — Entry card rendering pattern
- [Source: ui/beeper_ui/templates/knowledge/entry.html:64-89] — Validation status badge rendering
- [Source: _bmad-output/implementation-artifacts/6-2-bi-directional-kb-investigation-links.md] — Previous story with HTMX patterns and badge CSS

## Dev Agent Record

### Agent Model Used

claude-opus-4-6

### Debug Log References

### Completion Notes List

- Added `get_service_knowledge_grouped()` method to `KBService` — groups KB entries by category (root_causes, runbooks, proven_fixes, patterns) based on entry_type, with optional validation_status filter
- Added `get_service_validation_counts()` method to `KBService` — counts entries per validation_status for a service (AI-generated, human-confirmed, proven, corrected, unknown, total)
- Added `/knowledge/services/<service_name>/knowledge` route to knowledge blueprint — displays per-service knowledge view with grouped entries, validation status filter badges, and empty state
- Created `service_knowledge.html` template with validation status filter badges, grouped collapsible sections, and empty state message
- Updated `_entry_card.html` and `entry.html` service badges to link to per-service knowledge view instead of KB index filter
- Route validates service name against available services (404 for unknown), sanitizes input, and handles KBServiceError gracefully
- 6 new KBService tests (grouped entries + validation counts), 7 new route tests (service knowledge view)
- All 3,141 tests pass across all components (941 investigator + 1,669 UI + 531 operator)

### Change Log

- 2026-03-17: Implemented story 6-3 — per-service knowledge views with grouped entries by category, validation status filter badges, empty state, and navigation from service badges

### File List

- ui/beeper_ui/services/kb_service.py (MODIFIED) — Added `get_service_knowledge_grouped()`, `get_service_validation_counts()` methods
- ui/beeper_ui/routes/knowledge.py (MODIFIED) — Added `service_knowledge()` route at `/services/<service_name>/knowledge`
- ui/beeper_ui/templates/knowledge/service_knowledge.html (CREATED) — Per-service knowledge view template with grouped sections, validation badges, empty state
- ui/beeper_ui/templates/knowledge/_entry_card.html (MODIFIED) — Service badge links to per-service knowledge view
- ui/beeper_ui/templates/knowledge/entry.html (MODIFIED) — Service badge links to per-service knowledge view
- ui/tests/test_kb_service.py (MODIFIED) — Added TestGetServiceKnowledgeGrouped (6 tests) + TestGetServiceValidationCounts (6 tests)
- ui/tests/test_routes_knowledge.py (MODIFIED) — Added TestServiceKnowledgeRoute (7 tests)
- _bmad-output/implementation-artifacts/6-3-per-service-knowledge-views.md (MODIFIED) — Story file
- _bmad-output/implementation-artifacts/sprint-status.yaml (MODIFIED) — Story status updates
