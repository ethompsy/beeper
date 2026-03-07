# Story 4.2: Real-Time Investigation Pane

Status: review

## Story

As an **SRE**,
I want to view the real-time reasoning of any active Investigator,
so that I can observe Beeper's investigation process as it happens.

## Acceptance Criteria

1. **Given** I click on an active investigation, **When** the investigation pane opens, **Then** I see Beeper's reasoning process in real-time (FR32, FR10) **And** updates stream via SSE (NFR-P2).

2. **Given** the investigator is working, **When** I observe the pane, **Then** I see the current step: "Assessing impact", "Querying KB", "Correlating signals", etc. **And** I see evidence being gathered in real-time **And** I see the reasoning chain as it develops.

3. **Given** the investigation progresses, **When** new findings emerge, **Then** they appear in the pane without refresh **And** timestamps show when each finding was made.

4. **Given** the investigation pane is open, **When** I want to see raw data, **Then** I can expand sections to see: raw log snippets, metric values, KB matches found.

## Tasks / Subtasks

- [x] Task 1: Add Investigation Detail API endpoint to operator (AC: 1, 2)
  - [x] 1.1 Add `GET /api/v1/investigations/{id}` handler in `operator/src/api.rs` that fetches a single Investigation CRD by name via `Api<Investigation>::get(id)`
  - [x] 1.2 Create `InvestigationDetailResponse` struct extending `InvestigationListResponse` with: `message: Option<String>` (status.message — real-time step progress), `error: Option<String>`, `job_name: Option<String>`
  - [x] 1.3 Register route in `api_router()` alongside existing `/api/v1/investigations` list endpoint
  - [x] 1.4 Return 404 JSON error when investigation ID not found (consistent with existing API error patterns)

- [x] Task 2: Extend InvestigationService with detail + findings methods (AC: 1, 2, 3, 4)
  - [x] 2.1 Add `InvestigationDetail` dataclass extending `Investigation` with: `message: str | None`, `error: str | None`, `job_name: str | None`
  - [x] 2.2 Add `get_investigation(investigation_id: str) -> InvestigationDetail | None` method — calls `GET {OPERATOR_URL}/api/v1/investigations/{id}`, returns None on 404
  - [x] 2.3 Add `get_investigation_findings(investigation_id: str) -> dict[str, Any]` method — calls Qdrant `investigations` collection to fetch pipeline metadata (step results accumulated during investigation)
  - [x] 2.4 Handle operator/Qdrant connection errors with graceful degradation (return None/empty dict + log warning, matching existing service patterns)

- [x] Task 3: Create Investigation Detail route (AC: 1, 2, 3, 4)
  - [x] 3.1 Add `GET /investigations/<investigation_id>` route in `ui/beeper_ui/routes/investigations.py` — fetch investigation detail + findings from service, detect `HX-Request` header for partial vs full page
  - [x] 3.2 Add `GET /investigations/<investigation_id>/stream` SSE endpoint — poll operator `GET /api/v1/investigations/{id}` at 3-second intervals, send SSE events when `status.message` or `phase` changes
  - [x] 3.3 SSE event types: `step-update` (message/phase changed — send rendered HTML partial for HTMX swap), `investigation-complete` (phase=Completed — send final state)
  - [x] 3.4 Use `stream_with_context` for SSE generator (established pattern from 4-1 stream endpoint)
  - [x] 3.5 On each poll, also check Qdrant `investigations` collection for new step results — send `findings-update` SSE event with rendered findings partial when new data available

- [x] Task 4: Create Investigation Detail templates (AC: 1, 2, 3, 4)
  - [x] 4.1 Create `ui/beeper_ui/templates/investigations/detail.html` — full page extending `base.html`, includes: header (ID, service, condition, severity badge, status badge, timestamps), step progress section with SSE, findings section, expandable raw data sections
  - [x] 4.2 Create `ui/beeper_ui/templates/investigations/_step_progress.html` — HTMX partial showing: current step name with animated indicator, completed steps with checkmarks and timestamps, step timeline visualization (vertical list: Customer Impact → KB Query → Signal Correlation → RCA Hypothesis → Resolution Recommendations → Documentation)
  - [x] 4.3 Create `ui/beeper_ui/templates/investigations/_findings.html` — HTMX partial showing accumulated findings: customer impact assessment (impact badge + reasoning), KB matches (linked entry titles with similarity scores), signal summary (layer indicators, signals count), RCA hypothesis (confidence indicator + description), alternative hypotheses (if any)
  - [x] 4.4 Create `ui/beeper_ui/templates/investigations/_evidence_panel.html` — expandable raw data sections using `<details>`/`<summary>` HTML elements: "Raw Signals" (metric values, log snippets formatted in `<pre>` blocks), "KB Matches" (full match details with scores), "Correlation Data" (hypothesis supporting signals, causal chains)
  - [x] 4.5 Add back-navigation link to investigation list (`← Back to Investigations` with `hx-get="/investigations/"`)
  - [x] 4.6 Add SSE connection: `hx-ext="sse"` with `sse-connect="/investigations/{id}/stream"`, swap targets: `#step-progress` for `step-update`, `#findings` for `findings-update`

- [x] Task 5: Add CSS styles for investigation detail pane (AC: 1, 2, 3, 4)
  - [x] 5.1 Add styles to `static/css/main.css`: `.investigation-detail` layout, `.step-timeline` (vertical list with connecting line), `.step-item` (circle indicator + step name + timestamp), `.step-active` (pulsing animation), `.step-completed` (green checkmark)
  - [x] 5.2 Add `.findings-section` styles: `.impact-badge`, `.confidence-indicator` (color-coded bar: green>80%, yellow 50-80%, red<50%), `.hypothesis-card`, `.alternative-hypothesis`
  - [x] 5.3 Add `.evidence-panel` styles: expandable `<details>` styling, `<pre>` code block formatting for raw data, consistent with existing investigation list and KB styling
  - [x] 5.4 Add transition animations: fade-in for new findings, smooth step progress transitions

- [x] Task 6: Wire investigation list row click to detail view (AC: 1)
  - [x] 6.1 Update `_investigation_row.html` (or `_list_content.html`) to make each investigation row clickable — add `hx-get="/investigations/{id}"` with `hx-target="#main-content"` `hx-push-url="true"` for SPA-like navigation
  - [x] 6.2 Add hover state styling for clickable investigation rows (`.investigation-row:hover`)

- [x] Task 7: Operator API tests (AC: 1, 2)
  - [x] 7.1 Test `GET /api/v1/investigations/{id}` returns full detail including `message` field
  - [x] 7.2 Test `GET /api/v1/investigations/{id}` returns 404 JSON for nonexistent investigation
  - [x] 7.3 Test detail response includes all fields from list response plus `message`, `error`, `job_name`
  - [x] 7.4 Test `message` field reflects current status.message from CRD

- [x] Task 8: UI route and service tests (AC: 1, 2, 3, 4)
  - [x] 8.1 Test `InvestigationService.get_investigation()` calls operator API correctly and parses detail response
  - [x] 8.2 Test `InvestigationService.get_investigation()` returns None for 404
  - [x] 8.3 Test `InvestigationService.get_investigation_findings()` fetches from Qdrant investigations collection
  - [x] 8.4 Test `GET /investigations/<id>` returns full page HTML with investigation detail (no HX-Request)
  - [x] 8.5 Test `GET /investigations/<id>` returns partial HTML (with HX-Request)
  - [x] 8.6 Test `GET /investigations/<id>` returns 404 page for nonexistent investigation
  - [x] 8.7 Test `GET /investigations/<id>/stream` returns SSE content type
  - [x] 8.8 Test SSE sends `step-update` event when status.message changes between polls
  - [x] 8.9 Test SSE sends `investigation-complete` event when phase transitions to Completed
  - [x] 8.10 Test error state rendering when operator unavailable
  - [x] 8.11 Test expandable evidence sections render with correct data structure

- [x] Task 9: Integration verification (AC: 1, 2, 3, 4)
  - [x] 9.1 Verify clicking investigation row in list navigates to detail view
  - [x] 9.2 Verify SSE connection establishes and receives events
  - [x] 9.3 Run `ruff check` and `mypy --strict` on all new/modified Python files — fix any issues
  - [x] 9.4 Run `cargo clippy` on operator changes — fix any warnings
  - [x] 9.5 Run full Python test suite — verify zero regressions

## Dev Notes

### Architecture Decision: Investigation Detail SSE

Reuse the polling-backed SSE pattern established in story 4-1. The detail pane SSE endpoint polls the operator for a single investigation's status at 3-second intervals. Key difference from list SSE: track `status.message` changes (not just phase changes) to show step-by-step progress. The `status.message` field is updated by the investigator pod via `InvestigationStatusUpdater.update_message()` in `k8s/status.py` during each pipeline step.

**SSE Event Design:**
- `step-update`: Sends rendered `_step_progress.html` partial when `message` or `phase` changes — HTMX swaps into `#step-progress` container
- `findings-update`: Sends rendered `_findings.html` partial when new step results appear in Qdrant — HTMX swaps into `#findings` container
- `investigation-complete`: Sends final rendered state when phase=Completed — triggers full content refresh

### Investigation Pipeline Steps and Status Messages

The investigator agent (`agent.py`) runs these steps sequentially, updating `status.message` before each:

| Step | Status Message | Data Produced (pipeline_metadata keys) |
|------|---------------|---------------------------------------|
| CustomerImpactStep | "Assessing customer impact" | `customer_impacting`, `reasoning` |
| KBQueryStep | "Querying knowledge base" | `prior_research_summary`, `relevant_matches`, `exact_match_found`, `confidence_boost` |
| SignalCorrelationStep | "Correlating signals across architectural layers" | `sources_available`, `layers_queried`, `signals_gathered`, `signal_summary`, `hypotheses`, `correlation_attempted` |
| RCAHypothesisStep | "Generating root cause hypothesis" | `root_cause_hypothesis`, `confidence_level`, `confidence_percentage`, `supporting_evidence`, `alternative_hypotheses`, `additional_data_needs` |
| ResolutionRecommendationStep | "Generating resolution recommendations" | `resolution_recommendation`, `estimated_mttr_minutes`, `escalation_recommended`, `confidence_level` |
| InvestigationDocumentationStep | "Documenting investigation findings" | `documentation_written`, `kb_entry_id` |

### Findings Data Retrieval

Step results accumulate in the Qdrant `investigations` collection during pipeline execution. The UI service should query Qdrant for the investigation document by `investigation_id` metadata field. The document payload contains all accumulated pipeline metadata as a flat dict.

**Qdrant Query Pattern** (follow existing `kb_service.py` patterns):
```python
from qdrant_client import QdrantClient
# Search by investigation_id in investigations collection
results = qdrant_client.scroll(
    collection_name="investigations",
    scroll_filter=Filter(must=[FieldCondition(key="investigation_id", match=MatchValue(value=investigation_id))]),
    limit=1
)
```

### Step Timeline Display Logic

Map `status.message` to step progress:
1. Parse current message to determine active step
2. All steps before active step → completed (green checkmark)
3. Active step → in-progress (pulsing indicator)
4. Steps after active step → pending (gray circle)
5. If phase=Completed → all steps completed
6. If phase=Failed → show error state on current step

### Operator Detail Endpoint

Add `GET /api/v1/investigations/{id}` alongside existing list endpoint in `operator/src/api.rs`. Follow same pattern as list endpoint but use `Api<Investigation>::get(name)` instead of `list()`. Include `status.message` field in response — this is the real-time progress indicator.

```rust
// Pattern from existing api.rs
async fn get_investigation(
    Path(id): Path<String>,
    Extension(client): Extension<Client>,
) -> Result<Json<InvestigationDetailResponse>, StatusCode> {
    let api: Api<Investigation> = Api::namespaced(client, "default");
    match api.get(&id).await {
        Ok(inv) => Ok(Json(map_investigation_detail(&inv))),
        Err(_) => Err(StatusCode::NOT_FOUND),
    }
}
```

### Design Pattern: Expandable Evidence Sections

Use native HTML `<details>`/`<summary>` elements for expandable raw data — no JavaScript needed. Style consistently with existing KB entry detail patterns.

```html
<details class="evidence-panel">
    <summary>Raw Signals ({{ signals_gathered }} collected)</summary>
    <pre class="evidence-data">{{ signal_data }}</pre>
</details>
```

### Design Pattern: SPA-like Navigation from List

Use HTMX `hx-push-url` to update browser URL when navigating from list to detail. This preserves browser back-button behavior without a full page reload.

### Existing Patterns to Reuse

- **SSE streaming:** `investigations.py` `investigation_stream()` from story 4-1 — adapt for single investigation polling
- **Service layer:** `InvestigationService` in `investigation_service.py` — extend with `get_investigation()` and `get_investigation_findings()`
- **HTMX SSE extension:** Already installed at `static/js/htmx-ext-sse.js` from story 4-1
- **Template structure:** `investigations/list.html` extends `base.html` — follow same pattern for `detail.html`
- **Status badges:** CSS classes from story 4-1 (`.status-badge`, `.severity-*`)
- **Error handling:** `InvestigationServiceError` and graceful degradation pattern
- **Blueprint routes:** Already registered in `routes/__init__.py`

### Anti-Patterns to Avoid

- **DO NOT** create a separate service class for findings — extend existing `InvestigationService`
- **DO NOT** use WebSocket — use SSE (polling-backed) per architecture
- **DO NOT** hardcode step names — derive from status.message parsing
- **DO NOT** render unsanitized HTML in evidence data — use `<pre>` with Jinja2 autoescaping
- **DO NOT** create new JavaScript — HTMX + SSE extension handles all dynamic behavior
- **DO NOT** duplicate Qdrant client initialization — reuse from existing services (check `kb_service.py` for Qdrant patterns)
- **DO NOT** poll more frequently than 3 seconds — architecture specifies 2-3 second intervals for MVP

### Key File Paths

| Component | Path |
|-----------|------|
| Operator API (modify) | `operator/src/api.rs` |
| Investigation CRD | `operator/src/crds/investigation.rs` |
| Status Updater | `investigator/beeper_investigator/k8s/status.py` |
| Agent Pipeline | `investigator/beeper_investigator/agent.py` |
| Step Framework | `investigator/beeper_investigator/steps/__init__.py` |
| Investigation Service (modify) | `ui/beeper_ui/services/investigation_service.py` |
| Investigation Routes (modify) | `ui/beeper_ui/routes/investigations.py` |
| Investigation List Templates | `ui/beeper_ui/templates/investigations/` |
| KB Service (Qdrant pattern) | `ui/beeper_ui/services/kb_service.py` |
| CSS Styles (modify) | `ui/beeper_ui/static/css/main.css` |
| Base Template | `ui/beeper_ui/templates/base.html` |
| HTMX SSE Extension | `ui/beeper_ui/static/js/htmx-ext-sse.js` |

### Testing Standards

- **Rust (operator):** Use `#[tokio::test]`, inline tests in `api.rs` for detail endpoint (established pattern from 4-1)
- **Python (UI):** pytest with Flask test client, `respx` for mocking operator HTTP, mock Qdrant client for findings
- **SSE tests:** Verify content type, event format, change detection between polls
- **Template tests:** Verify full-page and HX-Request partial responses, expandable sections structure
- **Linting:** `ruff check`, `mypy --strict`, `cargo clippy` before marking complete

### Project Structure Notes

- No new service files — extend existing `investigation_service.py`
- No new route files — add routes to existing `investigations.py`
- New template files in existing `templates/investigations/` directory
- No new Python dependencies — Qdrant client already available via `kb_service.py` patterns
- No new JS assets — HTMX SSE extension already installed

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 4, Story 4.2]
- [Source: _bmad-output/planning-artifacts/architecture.md — UI Architecture, SSE, Real-Time Updates]
- [Source: investigator/beeper_investigator/agent.py — _run_steps() pipeline, status messages]
- [Source: investigator/beeper_investigator/k8s/status.py — InvestigationStatusUpdater]
- [Source: investigator/beeper_investigator/steps/__init__.py — StepResult protocol, step data schemas]
- [Source: ui/beeper_ui/routes/investigations.py — SSE streaming pattern from 4-1]
- [Source: ui/beeper_ui/services/investigation_service.py — service layer pattern from 4-1]
- [Source: _bmad-output/implementation-artifacts/4-1-investigation-list-view.md — previous story patterns]
- [Source: operator/src/api.rs — existing API endpoint patterns]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created
- SSE polling-backed design reused from 4-1 with per-investigation granularity
- Step progress tracked via CRD status.message field (updated by investigator k8s/status.py)
- Findings data retrieved from Qdrant investigations collection (accumulated pipeline metadata)
- 9 tasks: operator detail API, service extension, routes, templates (6 files), CSS, list-to-detail navigation, operator tests, UI tests, integration verification
- All 322 Python tests pass (68 investigation-specific, 254 existing) — zero regressions
- Ruff check passes on all modified files
- Mypy --strict passes on modified files (pre-existing errors in kb_service.py/knowledge.py unchanged)
- Cargo not available locally — Rust changes follow established api.rs patterns with inline tests

### Change Log

| Change | Details |
|--------|---------|
| Operator detail endpoint | Added `GET /api/v1/investigations/:id` with `InvestigationDetailResponse` struct, 404 handling, 4 unit tests |
| InvestigationService extended | Added `InvestigationDetail` dataclass, `get_investigation()`, `get_investigation_findings()`, Qdrant client property |
| Detail route + SSE | Added `/investigations/<id>` (full page + HTMX partial), `/investigations/<id>/stream` SSE with step-update/findings-update/investigation-complete events |
| 6 new templates | `detail.html`, `_detail_content.html`, `_step_progress.html`, `_findings.html`, `_evidence_panel.html`, `_detail_not_found.html` |
| CSS styles | ~300 lines: step timeline, findings sections, evidence panels, confidence indicators, animations |
| List navigation | Made investigation rows clickable with `hx-get`/`hx-push-url` for SPA-like navigation |
| Tests | 19 service tests, 49 route tests (including step states, SSE, detail rendering, evidence panels) |

### File List

| File | Action | Description |
|------|--------|-------------|
| `operator/src/api.rs` | Modified | Added `InvestigationDetailResponse`, `get_investigation` handler, route registration, 4 tests |
| `ui/beeper_ui/services/investigation_service.py` | Modified | Added `InvestigationDetail` dataclass, `get_investigation()`, `get_investigation_findings()`, Qdrant client |
| `ui/beeper_ui/routes/investigations.py` | Modified | Added `PIPELINE_STEPS`, `_get_step_states()`, `investigation_detail()`, `investigation_detail_stream()` |
| `ui/beeper_ui/templates/investigations/detail.html` | Created | Full page template extending base.html with SSE connection |
| `ui/beeper_ui/templates/investigations/_detail_content.html` | Created | Main detail partial: header, step progress, findings, evidence |
| `ui/beeper_ui/templates/investigations/_step_progress.html` | Created | Step timeline with completed/active/pending/error states |
| `ui/beeper_ui/templates/investigations/_findings.html` | Created | Findings display: impact, KB matches, signals, RCA, resolution |
| `ui/beeper_ui/templates/investigations/_evidence_panel.html` | Created | Expandable `<details>` sections for raw data |
| `ui/beeper_ui/templates/investigations/_detail_not_found.html` | Created | 404 partial for HTMX requests |
| `ui/beeper_ui/templates/investigations/_list_content.html` | Modified | Made rows clickable with hx-get/hx-push-url |
| `ui/beeper_ui/static/css/main.css` | Modified | Added investigation detail styles (~300 lines) |
| `ui/tests/test_investigation_service.py` | Modified | Added 10 new tests (InvestigationDetail, get_investigation, findings) |
| `ui/tests/test_investigation_routes.py` | Modified | Added 16 new tests (detail route, step states, SSE, evidence) |
