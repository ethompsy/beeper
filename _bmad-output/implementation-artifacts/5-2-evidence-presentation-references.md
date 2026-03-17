# Story 5.2: Evidence Presentation with References

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the **system**,
I want to present evidence with references to specific metrics, logs, and prior KB entries,
so that SREs can verify Beeper's reasoning by clicking through to source data.

## Acceptance Criteria

1. **Given** an investigation step produces evidence (metric anomaly, log pattern, KB match) **When** the evidence is displayed in the investigation timeline **Then** each evidence item includes a clickable reference to the source (Prometheus query, Loki log line, KB entry ID) **And** hovering shows a preview; clicking navigates to the full source

2. **Given** evidence references a prior KB entry **When** the KB entry is displayed inline **Then** the entry's validation status (proven/AI-generated/human-confirmed) is visible **And** the relevance score (semantic similarity) is shown

3. **Given** an investigation with multiple evidence items **When** displayed in the timeline **Then** evidence is ordered chronologically with the investigation narrative **And** each item is tagged by type (metric, log, deploy, KB, config change)

## Tasks / Subtasks

- [x] Task 1: Create EvidenceReference data model and EvidenceService (AC: #1, #2, #3)
  - [x] 1.1 Create `ui/beeper_ui/services/evidence_service.py` with `EvidenceService` class following singleton pattern (see `CollaborationService`, `CorrectionService`)
  - [x] 1.2 Define `EvidenceReference` dataclass: `(id, investigation_id, evidence_type, title, content_preview, source_ref, source_type, timestamp, relevance_score, validation_status, raw_data)` where `evidence_type` is one of: `metric`, `log`, `deploy`, `kb`, `config_change`; `source_type` is one of: `prometheus`, `loki`, `kb_entry`, `git_commit`, `config`
  - [x] 1.3 Implement `extract_evidence_references(investigation_id, findings: dict) -> list[EvidenceReference]` — parses existing pipeline metadata fields (`supporting_evidence`, `relevant_matches`, `kb_citation`, `signal_summary`, `layers_queried`, `hypotheses`) into structured `EvidenceReference` objects, ordered chronologically
  - [x] 1.4 Implement `get_kb_reference_detail(entry_id) -> dict` — fetches KB entry via `KBService.get_entry()` and returns `{entry_id, title, entry_type, validation_status, relevance_score, content_preview}`
  - [x] 1.5 Write comprehensive unit tests for `EvidenceService` (extract from various findings shapes, KB reference detail, empty findings, partial findings)

- [x] Task 2: Add evidence reference extraction to investigation detail route (AC: #1, #3)
  - [x] 2.1 In `ui/beeper_ui/routes/investigations.py` `investigation_detail()` route, after fetching findings, call `EvidenceService.extract_evidence_references(investigation_id, findings)` to build the evidence reference list
  - [x] 2.2 Pass `evidence_references` list to the template context alongside existing `findings` dict
  - [x] 2.3 In the SSE stream handler (`investigation_stream()`), add evidence references extraction to the `findings-update` event so references update in real-time as new pipeline steps complete
  - [x] 2.4 Write route-level tests verifying evidence references are passed to template context and SSE stream includes evidence data

- [x] Task 3: Create evidence timeline template partial with clickable references (AC: #1, #2, #3)
  - [x] 3.1 Create `ui/beeper_ui/templates/investigations/_evidence_timeline.html` template partial — displays evidence references as a vertical chronological timeline with type-tagged items
  - [x] 3.2 Each evidence item renders: type icon/badge (metric/log/deploy/kb/config_change), title, content preview, timestamp, and a clickable reference link
  - [x] 3.3 For `kb` type evidence: render inline validation status badge (proven/AI-generated/human-confirmed) and relevance score as a small percentage indicator
  - [x] 3.4 For `metric` type evidence: render Prometheus query as `<code>` block with link text
  - [x] 3.5 For `log` type evidence: render log excerpt with Loki context reference
  - [x] 3.6 Implement hover preview using CSS `title` attribute or a lightweight tooltip showing `content_preview`
  - [x] 3.7 Clicking a KB reference navigates to `/knowledge/{entry_id}` (existing route), clicking metric/log references opens a collapsible detail panel inline

- [x] Task 4: Integrate evidence timeline into investigation detail page (AC: #1, #3)
  - [x] 4.1 Add `_evidence_timeline.html` include to `_detail_content.html` between the "Findings" card and the "Confidence Gate" card, wrapped in its own card with heading "Evidence Timeline"
  - [x] 4.2 Wire SSE event `evidence-timeline-update` to update the evidence timeline div via `sse-swap` pattern (matching existing SSE architecture)
  - [x] 4.3 Add SSE event emission for `evidence-timeline-update` in the stream handler — render `_evidence_timeline.html` partial with updated evidence references
  - [x] 4.4 Add CSS styles for evidence timeline to `ui/beeper_ui/static/css/main.css` following existing patterns: `.evidence-timeline`, `.evidence-timeline-item`, `.evidence-type-badge`, `.evidence-ref-link`, `.validation-status-badge`, `.relevance-score`

- [x] Task 5: Enhance existing evidence and findings partials with reference links (AC: #1, #2)
  - [x] 5.1 Update `_evidence_panel.html` — in the "Correlation & Supporting Evidence" section, parse `supporting_evidence` list items and render each as a clickable reference where possible (KB entries link to `/knowledge/{id}`, metric queries wrapped in `<code>`)
  - [x] 5.2 Update `_findings.html` — in the RCA Hypothesis section, if `kb_citation` exists, render it as a clickable link to `/knowledge/{kb_citation}` with validation status badge
  - [x] 5.3 Update `_related_kb.html` — add `validation_status` badge and `relevance_score` display to each KB entry card (fetch via KBService payload fields)
  - [x] 5.4 Write template rendering tests verifying reference links, validation badges, and relevance scores appear correctly

## Dev Notes

- **Existing evidence data is already rich** — the pipeline accumulates `supporting_evidence`, `relevant_matches`, `kb_citation`, `based_on_prior_incident`, `signal_summary`, `layers_queried`, and `hypotheses` in the findings dict. This story structures and presents that data with proper references rather than generating new data.
- **No new Qdrant collections needed** — all evidence data already exists in the `investigations` collection payload and `knowledge` collection. The `EvidenceService` is a presentation-layer service that extracts and structures existing data.
- **KB validation_status** — KB entries of type `proven_fix` have `validation_status: "proven"` in their payload. Other entries are `AI-generated` by default. The `human-confirmed` status comes from correction workflows (see `CorrectionService`).
- **Relevance score** — Already computed during semantic search in `KBService.search_semantic()` and stored as `relevance_score` on `KBEntry` dataclass. For inline display, retrieve via `KBService.get_entry()` or from `relevant_matches` field which contains `"entry_id: description"` format.
- **SSE streaming pattern** — Follow existing pattern in `investigation_stream()`: poll Qdrant, render template partial, emit as SSE event. The new `evidence-timeline-update` event follows the same pattern as `findings-update` and `evidence-update`.
- **Performance** — Evidence extraction is O(n) over findings fields. KB detail lookups should be batched or cached per-request to avoid N+1 queries.

### Project Structure Notes

- New service: `ui/beeper_ui/services/evidence_service.py` — follows singleton pattern of existing services
- New template: `ui/beeper_ui/templates/investigations/_evidence_timeline.html` — follows `_` prefix partial convention
- Modified templates: `_evidence_panel.html`, `_findings.html`, `_related_kb.html`, `_detail_content.html`
- Modified route: `ui/beeper_ui/routes/investigations.py` — adds evidence reference extraction
- Modified CSS: `ui/beeper_ui/static/css/main.css` — adds evidence timeline styles
- Test files: `ui/tests/test_evidence_service.py`, `ui/tests/test_evidence_timeline.py`

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.2] — Acceptance criteria and story statement
- [Source: _bmad-output/planning-artifacts/architecture.md#Investigation Pipeline] — Pipeline metadata structure and Qdrant collections
- [Source: _bmad-output/planning-artifacts/architecture.md#WebSocket Architecture] — evidence_update event contract
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Evidence Timeline] — Timeline styling: 8-12px gaps, citation styling, confidence visualization
- [Source: ui/beeper_ui/services/investigation_service.py] — get_investigation_findings() returns pipeline metadata dict
- [Source: ui/beeper_ui/services/kb_service.py] — KBEntry dataclass with relevance_score, get_entry() for KB reference detail
- [Source: ui/beeper_ui/templates/investigations/_findings.html] — Current findings display with KB links
- [Source: ui/beeper_ui/templates/investigations/_evidence_panel.html] — Current evidence panel with raw data display
- [Source: ui/beeper_ui/templates/investigations/_related_kb.html] — Current KB entry card display
- [Source: ui/beeper_ui/routes/investigations.py] — SSE streaming pattern for real-time updates
- [Source: ui/beeper_ui/static/css/main.css] — Existing evidence panel and findings CSS classes
- [Source: _bmad-output/implementation-artifacts/5-1-websocket-collaboration-channel.md] — Previous story patterns: Flask-SocketIO, Qdrant service, template partials

## Dev Agent Record

### Agent Model Used

claude-opus-4-6

### Debug Log References

N/A

### Completion Notes List

- Created EvidenceService with EvidenceReference dataclass and 6 extraction methods covering KB matches, signal correlation, supporting evidence, RCA KB citations, recommendation references, and documentation references
- Added evidence-timeline-update SSE event to real-time investigation streaming
- Created _evidence_timeline.html template partial with type badges, validation status, relevance scores, and clickable references
- Enhanced _evidence_panel.html, _findings.html, _related_kb.html with clickable KB references and structured evidence display
- Added ~200 lines of CSS for evidence timeline and enhanced partial styles
- 42 unit tests for EvidenceService, 21 tests for template rendering and route integration
- Fixed 4 SSE test regressions caused by new evidence-timeline-update event (adjusted event counts in range() calls)
- All 1492 UI tests pass, 888 investigator tests pass, operator tests pass

### File List

- `ui/beeper_ui/services/evidence_service.py` (NEW) — EvidenceService with EvidenceReference dataclass
- `ui/beeper_ui/templates/investigations/_evidence_timeline.html` (NEW) — Evidence timeline template partial
- `ui/tests/test_evidence_service.py` (NEW) — 42 unit tests for EvidenceService
- `ui/tests/test_evidence_timeline.py` (NEW) — 21 tests for template rendering and route integration
- `ui/beeper_ui/routes/investigations.py` (MODIFIED) — Added evidence reference extraction to detail route and SSE stream
- `ui/beeper_ui/templates/investigations/_detail_content.html` (MODIFIED) — Added Evidence Timeline card
- `ui/beeper_ui/templates/investigations/_evidence_panel.html` (MODIFIED) — Enhanced with clickable KB references
- `ui/beeper_ui/templates/investigations/_findings.html` (MODIFIED) — Added KB citation link in RCA section
- `ui/beeper_ui/templates/investigations/_related_kb.html` (MODIFIED) — Added validation status badges and relevance scores
- `ui/beeper_ui/static/css/main.css` (MODIFIED) — Added evidence timeline and enhanced partial styles
- `ui/tests/test_investigation_routes.py` (MODIFIED) — Fixed SSE test event counts for new evidence-timeline-update event
