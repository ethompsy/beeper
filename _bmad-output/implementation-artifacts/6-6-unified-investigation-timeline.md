# Story 6.6: Unified Investigation Timeline

Status: done

## Story

As a **user**,
I want a unified investigation timeline correlating logs, metrics, deploys, and K8s events,
so that I can see the complete picture of what happened around an incident in one view.

## Acceptance Criteria

1. **Given** an investigation detail page **When** the timeline view loads **Then** events are displayed chronologically: metric anomalies, log patterns, K8s events (pod restarts, OOMs, scaling), deploy events, config changes **And** each event type has a distinct visual indicator (icon + color)

2. **Given** a timeline with multiple event types **When** the user filters by event type (e.g., "deploys only") **Then** only matching events are shown while maintaining the time axis **And** the page responds within 2 seconds (NFR2)

3. **Given** a timeline event **When** the user clicks on it **Then** the full event detail is shown inline (log content, metric graph, deploy diff, K8s event details)

## Tasks / Subtasks

- [x] Task 1: Add `get_timeline_events()` method to `EvidenceService` (AC: #1)
  - [x] 1.1 In `ui/beeper_ui/services/evidence_service.py`, add a `get_timeline_events(investigation_id, findings)` method that calls `extract_evidence_references()` and then sorts the resulting list by `timestamp` field (ISO 8601 chronological order). Return the sorted list.
  - [x] 1.2 Add a `TimelineEvent` dataclass that wraps `EvidenceReference` with an additional `event_category` field (one of: "metric_anomaly", "log_pattern", "k8s_event", "deploy_event", "config_change"). Map from existing `evidence_type` values: metric->metric_anomaly, log->log_pattern, deploy->deploy_event, config_change->config_change, kb->kb_reference.

- [x] Task 2: Create timeline filter bar template partial (AC: #2)
  - [x] 2.1 Create `ui/beeper_ui/templates/investigations/_timeline_filter.html` with a row of toggle buttons (one per event type: Metrics, Logs, Deploys, Config, KB). Each button has class `timeline-filter-btn` and `data-type` attribute matching the evidence_type. All active by default. Use HTMX `hx-get` with query params to re-fetch filtered timeline, or use CSS-only `data-*` attribute toggling for client-side filtering.
  - [x] 2.2 For CSS-only filtering (preferred, avoids round-trip): each filter button toggles a CSS class on the parent `.unified-timeline` container. When a type is deactivated, items matching that type get `display: none`. Use a small inline `<script>` in the template (following existing HTMX pattern) that toggles `.hide-{type}` class on the container.

- [x] Task 3: Create unified timeline template partial (AC: #1, #3)
  - [x] 3.1 Create `ui/beeper_ui/templates/investigations/_unified_timeline.html`. This replaces the existing `_evidence_timeline.html` include in the "Evidence Timeline" card on the detail page. Structure: filter bar include at top, then `<div class="unified-timeline">` containing chronologically sorted events.
  - [x] 3.2 Each timeline event item uses existing `.evidence-timeline-item` CSS structure but adds a timestamp display: `<span class="timeline-event-time">{{ event.timestamp }}</span>` in the header.
  - [x] 3.3 For inline detail expansion (AC #3), wrap the content section in a `<details>` element. The `<summary>` shows the event title + type badge + timestamp. The expanded content shows: full `raw_data` for metrics/logs, `source_ref` for deploys (commit hash), and config diff for config changes. Reuse the existing `evidence-inline-detail` CSS class.

- [x] Task 4: Wire unified timeline into investigation detail route (AC: #1)
  - [x] 4.1 In `ui/beeper_ui/routes/investigations.py`, in the `investigation_detail()` function (line ~430), after extracting `evidence_references`, call `ev_svc.get_timeline_events(investigation_id, findings)` to get sorted timeline events. Pass `timeline_events` to template context.
  - [x] 4.2 In `ui/beeper_ui/templates/investigations/_detail_content.html`, replace the "Evidence Timeline" card content (lines 75-81) to include `_unified_timeline.html` with `timeline_events` instead of `_evidence_timeline.html` with `evidence_references`. Keep the existing SSE swap on `#evidence-timeline` div.
  - [x] 4.3 Update the SSE stream in `_generate_detail_sse_events()` (line ~1163) to render `_unified_timeline.html` with `timeline_events` instead of `_evidence_timeline.html` for the `evidence-timeline-update` event.

- [x] Task 5: Add unified timeline CSS styles (AC: #1, #2)
  - [x] 5.1 In `ui/beeper_ui/static/css/main.css`, add CSS for `.timeline-filter-bar` (flex row, gap 6px, margin-bottom 12px), `.timeline-filter-btn` (pill button, toggleable active state with matching evidence-type color), `.timeline-filter-btn.inactive` (greyed out, opacity 0.5).
  - [x] 5.2 Add `.unified-timeline.hide-metric .evidence-type-metric`, `.unified-timeline.hide-log .evidence-type-log`, etc. rules that set `display: none` for CSS-only filtering.
  - [x] 5.3 Add `.timeline-event-time` styles (font-size 0.75rem, color #9ca3af, monospace font).

- [x] Task 6: Write unit tests for `get_timeline_events()` and `TimelineEvent` (AC: #1)
  - [x] 6.1 In `ui/tests/test_evidence_service.py`, add `TestGetTimelineEvents` class: test that events are sorted chronologically by timestamp, test that empty findings returns empty list, test that `event_category` mapping is correct for each evidence_type.

- [x] Task 7: Write template tests for unified timeline (AC: #1, #2, #3)
  - [x] 7.1 In `ui/tests/test_evidence_timeline.py`, add `TestUnifiedTimelineTemplate` class: test that timeline renders events with timestamps, test that filter buttons render for each event type, test that details elements exist for inline expansion, test that empty state message shows when no events.

- [x] Task 8: Write route tests for timeline integration (AC: #1)
  - [x] 8.1 In `ui/tests/test_investigation_routes.py`, add `TestInvestigationDetailTimeline` class: test that `investigation_detail()` passes `timeline_events` to template context, test that timeline events are chronologically ordered.

- [x] Task 9: Run full test suite across all components (AC: all)
  - [x] 9.1 Run investigator tests: `cd investigator && poetry run python -m pytest` — 952 passed
  - [x] 9.2 Run investigator linting: `cd investigator && poetry run ruff check .` — All checks passed
  - [x] 9.3 Run investigator type checking: `cd investigator && poetry run mypy .` — Pre-existing errors only, no new issues
  - [x] 9.4 Run UI tests: `cd ui && poetry run python -m pytest` — 1,723 passed
  - [x] 9.5 Run operator tests: `cd operator && cargo test` — 531 passed
  - [x] 9.6 Verify no regressions from baseline (3,188 tests) — 3,206 total (18 new tests added)

## Dev Notes

### Architecture Patterns (CRITICAL -- must follow)

**FR43 maps to:** `ui/routes/investigations.py`, `ui/templates/investigations/detail.html` [Source: architecture.md line 1432-1433]

**What already exists (DO NOT rebuild):**
- Evidence timeline template at `_evidence_timeline.html` — vertical list with type badges, color-coded borders, inline details for queries/logs/config
- `EvidenceService.extract_evidence_references()` — pulls all evidence from pipeline metadata (KB matches, signal correlations, supporting evidence, RCA citations, recommendations, documentation)
- `EvidenceReference` dataclass — id, investigation_id, evidence_type, title, content_preview, source_ref, source_type, timestamp, relevance_score, validation_status, raw_data
- Evidence types: metric, log, deploy, kb, config_change (with CSS colors: indigo, amber, green, blue, violet)
- Source types: prometheus, loki, kb_entry, git_commit, config
- SSE real-time updates via `evidence-timeline-update` event in `_generate_detail_sse_events()`
- `enrich_kb_references()` — fetches KB entry details for validation_status enrichment
- CSS styles for `.evidence-timeline`, `.evidence-timeline-item`, `.evidence-type-badge`, all type-specific colors
- Inline detail expansion using `<details>` elements for prometheus queries, loki logs, config changes

**What this story adds:**
1. Chronological sorting of timeline events by timestamp
2. Event type filter bar (CSS-only toggle, no server round-trip)
3. Timestamp display on each event
4. Explicit inline detail expansion for all event types (wrapping in `<details>`)
5. New unified timeline template that replaces evidence timeline

### Existing Code to Reuse (DO NOT RECREATE)

| Component | Location | What to Reuse |
|-----------|----------|---------------|
| EvidenceService | `ui/beeper_ui/services/evidence_service.py` | Add get_timeline_events() method |
| EvidenceReference | `ui/beeper_ui/services/evidence_service.py:24` | Base dataclass — extend with TimelineEvent |
| extract_evidence_references() | `ui/beeper_ui/services/evidence_service.py:47` | Core extraction logic |
| enrich_kb_references() | `ui/beeper_ui/services/evidence_service.py:421` | KB validation enrichment |
| _evidence_timeline.html | `ui/beeper_ui/templates/investigations/_evidence_timeline.html` | Reference for layout patterns |
| _detail_content.html | `ui/beeper_ui/templates/investigations/_detail_content.html:75-81` | Swap point for new template |
| investigation_detail() | `ui/beeper_ui/routes/investigations.py:430` | Add timeline_events to context |
| _generate_detail_sse_events() | `ui/beeper_ui/routes/investigations.py:~1100` | Update SSE to use new template |
| Evidence CSS | `ui/beeper_ui/static/css/main.css:4191-4337` | All existing evidence-timeline styles |

### Anti-Patterns to AVOID

- Do NOT create a new data collection or database table — timeline data comes from existing pipeline metadata
- Do NOT create a separate timeline service — extend EvidenceService
- Do NOT use JavaScript frameworks — maintain CSS-only + HTMX + minimal inline script pattern
- Do NOT add server-side filtering routes — use CSS-only client-side filtering for <2s response
- Do NOT modify the investigator component — no pipeline changes needed
- Do NOT modify the operator component — no Rust changes needed
- Do NOT change EvidenceReference dataclass fields — wrap with TimelineEvent instead
- Do NOT remove the existing `_evidence_timeline.html` — keep it for SSE compatibility, just replace the include in `_detail_content.html`

### Previous Story Intelligence (6-5)

**Key learnings from Story 6-5 (KB Entry Review, Edit & Correction):**
- VALID_ENTRY_TYPES now includes "proven_fix" (added in 6-5 code review)
- `_describe_edit_changes()` helper pattern for generating human-readable descriptions
- Route tests mock `get_kb_service()` and assert template context variables
- hx-confirm attribute pattern for destructive actions (restore button)
- 3,188 tests pass across all components (952 investigator + 1,705 UI + 531 operator) — baseline for regression
- Category dropdown uses `|replace('_', ' ')|title` filter for display names

### Testing Standards

- **Framework:** pytest with unittest.mock
- **Test locations:**
  - `ui/tests/test_evidence_service.py` — get_timeline_events, TimelineEvent tests
  - `ui/tests/test_evidence_timeline.py` — unified timeline template tests
  - `ui/tests/test_investigation_routes.py` — route integration tests
- **Mocking patterns:**
  - `unittest.mock.patch("beeper_ui.routes.investigations.get_evidence_service")` for route tests
  - Direct EvidenceService instantiation for unit tests
  - `app.jinja_env.get_template()` for template rendering tests

### Project Structure Notes

**Files to CREATE:**
- `ui/beeper_ui/templates/investigations/_unified_timeline.html` — New unified timeline template with filter bar and chronological events
- `ui/beeper_ui/templates/investigations/_timeline_filter.html` — Filter bar partial with toggle buttons

**Files to MODIFY:**
- `ui/beeper_ui/services/evidence_service.py` — Add TimelineEvent dataclass, get_timeline_events() method
- `ui/beeper_ui/routes/investigations.py` — Add timeline_events to investigation_detail() context, update SSE rendering
- `ui/beeper_ui/templates/investigations/_detail_content.html` — Replace _evidence_timeline.html include with _unified_timeline.html
- `ui/beeper_ui/static/css/main.css` — Add timeline filter bar, CSS-only filtering, timestamp styles
- `ui/tests/test_evidence_service.py` — Add TestGetTimelineEvents class
- `ui/tests/test_evidence_timeline.py` — Add TestUnifiedTimelineTemplate class
- `ui/tests/test_investigation_routes.py` — Add TestInvestigationDetailTimeline class

**Files to NOT touch:**
- `investigator/**` — No investigator changes needed
- `operator/**` — No operator changes needed
- `ui/beeper_ui/services/investigation_service.py` — No changes to investigation data model
- `ui/beeper_ui/services/kb_service.py` — No KB service changes
- `ui/beeper_ui/templates/investigations/_evidence_timeline.html` — Keep for SSE backward compatibility (may still be used by SSE renderer)

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 6.6] — Acceptance criteria (lines 1233-1253)
- [Source: _bmad-output/planning-artifacts/architecture.md#FR43] — Unified timeline routes (line 1432-1433)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#lines 560-594] — Timeline as narrative flow (signature differentiator)
- [Source: ui/beeper_ui/services/evidence_service.py] — EvidenceService, EvidenceReference, extraction methods
- [Source: ui/beeper_ui/routes/investigations.py:430-474] — investigation_detail() route handler
- [Source: ui/beeper_ui/routes/investigations.py:~1100-1180] — SSE stream evidence-timeline-update logic
- [Source: ui/beeper_ui/templates/investigations/_evidence_timeline.html] — Current evidence timeline template
- [Source: ui/beeper_ui/templates/investigations/_detail_content.html:75-81] — Evidence Timeline card swap point
- [Source: ui/beeper_ui/static/css/main.css:4191-4337] — Existing evidence-timeline CSS styles
- [Source: _bmad-output/implementation-artifacts/6-5-kb-entry-review-edit-correction.md] — Previous story intelligence

## Dev Agent Record

### Agent Model Used

claude-opus-4-6

### Debug Log References

### Completion Notes List

- Added `TimelineEvent` dataclass wrapping `EvidenceReference` with `event_category` field and property delegation. Added `_EVENT_CATEGORY_MAP` for evidence_type to category mapping (metric->metric_anomaly, log->log_pattern, deploy->deploy_event, config_change->config_change, kb->kb_reference).
- Added `get_timeline_events()` method to `EvidenceService` that extracts evidence, enriches KB references, wraps in `TimelineEvent` objects, and sorts chronologically by timestamp.
- Created `_timeline_filter.html` template partial with CSS-only filter toggle buttons (Metrics, Logs, Deploys, Config, KB) using inline onclick handlers that toggle `.hide-{type}` classes on the parent `.unified-timeline` container.
- Created `_unified_timeline.html` template with filter bar, chronological event display using `<details>` elements for inline expansion, timestamp display, and evidence type badges.
- Wired unified timeline into `investigation_detail()` route — calls `get_timeline_events()` and passes `timeline_events` to template context. Updated SSE stream to render unified timeline.
- Updated `_detail_content.html` to include `_unified_timeline.html` instead of `_evidence_timeline.html`. Card header changed from "Evidence Timeline" to "Investigation Timeline".
- Added CSS styles: `.unified-timeline`, `.timeline-filter-bar`, `.timeline-filter-btn` with type-specific active colors, `.inactive` state, CSS-only filtering rules (`.hide-{type} .evidence-type-{type}` → `display: none`), `.timeline-event-time` monospace timestamp, `<details>` summary and detail styling.
- Updated existing route integration tests to work with unified timeline (mock `get_timeline_events()`, check for "Investigation Timeline" and "No timeline events yet").
- 18 new tests: 10 `TestGetTimelineEvents` (service), 6 `TestUnifiedTimelineTemplate` (template), 2 `TestInvestigationDetailTimeline` (route).
- All 3,206 tests pass (952 investigator + 1,723 UI + 531 operator) — zero regressions from 3,188 baseline.

### Change Log

- 2026-03-17: Implemented story 6-6 — Unified Investigation Timeline with chronological event sorting, CSS-only type filtering, inline detail expansion via `<details>`, and TimelineEvent dataclass
- 2026-03-17: Code review (AI) — Found 3 MEDIUM + 2 LOW issues. Auto-fixed: removed double extraction/enrichment in route (dead `evidence_references`), fixed `_make_timeline_event` test helper kwarg leak, added human-readable timestamp formatting, added aria-pressed to filter buttons. Added 4 new tests (timestamp format, aria-pressed, event_category kwarg regression, route assert_not_called). All 3,209 tests pass (952 investigator + 1,726 UI + 531 operator).

### File List

- ui/beeper_ui/services/evidence_service.py (MODIFIED) — Added TimelineEvent dataclass, _EVENT_CATEGORY_MAP, get_timeline_events() method
- ui/beeper_ui/routes/investigations.py (MODIFIED) — Added timeline_events to investigation_detail() context, updated SSE to render unified timeline
- ui/beeper_ui/templates/investigations/_unified_timeline.html (CREATED) — Unified timeline template with filter bar and chronological events
- ui/beeper_ui/templates/investigations/_timeline_filter.html (CREATED) — CSS-only filter toggle buttons
- ui/beeper_ui/templates/investigations/_detail_content.html (MODIFIED) — Replaced _evidence_timeline.html include with _unified_timeline.html
- ui/beeper_ui/static/css/main.css (MODIFIED) — Added unified timeline, filter bar, CSS-only filtering, timestamp, details styling
- ui/tests/test_evidence_service.py (MODIFIED) — Added TestGetTimelineEvents (10 tests)
- ui/tests/test_evidence_timeline.py (MODIFIED) — Added TestUnifiedTimelineTemplate (6 tests), updated existing route tests
- ui/tests/test_investigation_routes.py (MODIFIED) — Added TestInvestigationDetailTimeline (2 tests)
- _bmad-output/implementation-artifacts/6-6-unified-investigation-timeline.md (MODIFIED) — Story file
- _bmad-output/implementation-artifacts/sprint-status.yaml (MODIFIED) — Story status updates
