# Story 6.9: Change Event Ingestion & Correlation

Status: done

## Story

As the **system**,
I want to ingest and correlate change events (config changes, scaling, DNS, certs),
so that Beeper can identify non-deploy changes that may have caused anomalies.

## Acceptance Criteria

1. **Given** K8s watch events for ConfigMaps, Secrets, HPA scaling, Ingress/DNS, and cert-manager resources **When** a change event occurs **Then** the event is stored with: resource type, namespace, name, change diff, timestamp **And** the event is available for timeline correlation

2. **Given** an anomaly under investigation **When** the investigator checks for correlated changes **Then** all change events within the lookback window for the affected service and its dependencies are surfaced **And** temporal correlation is calculated (same as deploy correlation)

3. **Given** change events are accumulating **When** storage grows beyond the retention window (configurable, default 30 days) **Then** older events are pruned automatically

## Tasks / Subtasks

- [x] Task 1: Create `ChangeEventCorrelationStep` investigator pipeline step (AC: #1, #2)
  - [x]1.1 Create `investigator/beeper_investigator/steps/change_event_correlation.py` with `ChangeEventCorrelationStep` class following the `InvestigationStep` protocol (name attribute + execute() -> StepResult). Constructor takes: `llm_client: LlmClient`, `context: InvestigationContext`, `status_updater: InvestigationStatusUpdater`, `pipeline_metadata: dict`. Add constants: `DEFAULT_LOOKBACK_MINUTES = 60`, `_STRONG_THRESHOLD = 5 * 60`, `_MODERATE_THRESHOLD = 30 * 60`, `WATCHED_RESOURCE_TYPES = ("ConfigMap", "Secret", "HorizontalPodAutoscaler", "Ingress", "Certificate")`.
  - [x]1.2 Implement `_fetch_change_events()` method: use K8s `CoreV1Api().list_namespaced_event()` with `field_selector="involvedObject.namespace={namespace}"` to list events in the investigation namespace. Filter for events where `involved_object.kind` is in `WATCHED_RESOURCE_TYPES` and `event_time` or `last_timestamp` falls within the lookback window. For each matching event, extract: `resource_type` (involvedObject.kind), `namespace`, `resource_name` (involvedObject.name), `change_description` (event.message), `timestamp` (event.last_timestamp or event.event_time as ISO string), `reason` (event.reason), `action` (event.action or ""). Handle `ApiException` gracefully — log warning and return empty list.
  - [x]1.3 Implement `_fetch_resource_modifications()` method: for ConfigMaps and Secrets, use `CoreV1Api().list_namespaced_config_map()` / `list_namespaced_secret()` filtered by service-related labels (label_selector `app={service}` or `app.kubernetes.io/name={service}`). Check `metadata.managed_fields` for recent modifications within the lookback window. For HPA, use `AutoscalingV1Api().list_namespaced_horizontal_pod_autoscaler()`. For Ingress, use `NetworkingV1Api().list_namespaced_ingress()`. For cert-manager Certificates, use `CustomObjectsApi().list_namespaced_custom_object(group="cert-manager.io", version="v1", plural="certificates")`. Deduplicate events from `_fetch_change_events()` by resource_name + timestamp proximity (<60s).
  - [x]1.4 Implement `_correlate_changes()` method: for each change event, calculate `time_gap_seconds` between the event timestamp and `self.context` anomaly detection time (from `pipeline_metadata.get("anomaly_detected_at")` or fallback to current time). Apply same confidence classification as DeployCorrelationStep: `<5min = "strong"`, `5-30min = "moderate"`, `>30min = "weak"`. Sort by time_gap_seconds ascending (closest first). Return list of correlation dicts with: `resource_type`, `namespace`, `resource_name`, `change_description`, `timestamp`, `time_gap_seconds`, `confidence`, `reason`.
  - [x]1.5 Implement `_format_change_summary()` method: generate human-readable summary. Pattern: "N change events found within lookback window (X strong, Y moderate, Z weak correlation)". If no events: "No recent change events found — likely not config-change-related". Include strongest correlation detail: "ConfigMap payments-config changed 3 min before anomaly (strong correlation)".
  - [x]1.6 Implement `execute()` method: call `self.status_updater.update_message("Checking for correlated change events...")`, then `_fetch_change_events()`, then `_fetch_resource_modifications()`, merge+deduplicate results, then `_correlate_changes()`, then `_format_change_summary()`. Return `StepResult(success=True, summary=..., data={"change_events": [...], "change_summary": "...", "change_event_correlation_attempted": True})`. On any unhandled exception: return `StepResult(success=False, summary="Change event correlation failed", error=str(e), data={"change_event_correlation_attempted": True})`.

- [x]Task 2: Register `ChangeEventCorrelationStep` in the agent pipeline (AC: #1)
  - [x]2.1 In `investigator/beeper_investigator/agent.py`, add lazy import for `ChangeEventCorrelationStep` from `beeper_investigator.steps.change_event_correlation` (after the ServiceTopologyStep import).
  - [x]2.2 Insert `ChangeEventCorrelationStep` into the steps list AFTER `ServiceTopologyStep` and BEFORE `RCAHypothesisStep` (at index 5, pushing RCA to index 6). Pass `llm_client`, `context`, `status_updater`, and `pipeline_metadata=self._pipeline_metadata`. This makes the pipeline 16 steps total (9 core + 7 remediation).

- [x]Task 3: Add change event evidence extraction to EvidenceService (AC: #1, #2)
  - [x]3.1 In `ui/beeper_ui/services/evidence_service.py`, add `_extract_change_event_references()` method following the exact pattern of `_extract_deploy_correlation_references()`. Extract from `findings.get("change_events", [])`. For each event dict, create `EvidenceReference` with: `evidence_type="config_change"`, `source_type="config"`, `title="Config Change: {resource_type}/{resource_name} ({confidence})"`, `content_preview=change_description`, `source_ref=resource_name`, `timestamp=event timestamp`, `raw_data=json.dumps(event)`.
  - [x]3.2 Call `_extract_change_event_references()` in `extract_evidence_references()` after deploy correlation extraction (between "Step 2.5" and "Step 3"). This makes change events appear in the unified timeline automatically (config_change type and config source_type already exist in `EVIDENCE_TYPES` and `SOURCE_TYPES`).

- [x]Task 4: Create change events investigation detail card template (AC: #2)
  - [x]4.1 Create `ui/beeper_ui/templates/investigations/_change_events.html`. Structure follows `_deploy_correlation.html` pattern exactly:
    - If `change_events` list is non-empty: render a table with columns: Resource Type, Resource Name, Change Description, Timestamp, Time Gap, Confidence. Each row shows resource_type, resource_name, truncated change_description, formatted timestamp (replace T with space, truncate to 19 chars), formatted time gap (X min Y sec, omit "0 sec"), confidence badge with class `change-confidence-badge confidence-{confidence}`.
    - Elif `change_summary` exists: render in `change-no-results` div.
    - Else: render "No recent change events found" in `change-no-results` div.

- [x]Task 5: Wire change events into investigation detail route (AC: #2)
  - [x]5.1 In `ui/beeper_ui/routes/investigations.py`, in `investigation_detail()`, extract `change_events = findings.get("change_events", [])` and `change_summary = findings.get("change_summary", "")`. Pass both to the template context.
  - [x]5.2 In `_generate_detail_sse_events()`, add a change events SSE block following the deploy correlation pattern: extract `change_events` and `change_summary` from findings, if present render `investigations/_change_events.html` and yield as `event: change-events-update`.

- [x]Task 6: Add change events card to investigation detail page (AC: #2)
  - [x]6.1 In `ui/beeper_ui/templates/investigations/_detail_content.html`, add a new card block AFTER the Service Dependencies card (after line 97) and BEFORE the Human Interventions section (before line 99):
    ```html
    {# Change Event Correlation #}
    <div class="card">
        <h3>Change Event Correlation</h3>
        <div id="change-events" sse-swap="change-events-update" hx-swap="innerHTML">
            {% include "investigations/_change_events.html" %}
        </div>
    </div>
    ```

- [x]Task 7: Add change events CSS styles (AC: #2)
  - [x]7.1 In `ui/beeper_ui/static/css/main.css`, add styles for change events card. Follow the deploy correlation CSS pattern exactly: `.change-events-card`, `.change-table` (same structure as `.deploy-table`), `.change-confidence-badge` with `.confidence-strong` (red #f87171), `.confidence-moderate` (amber #fbbf24), `.confidence-weak` (blue #60a5fa) — reuse existing confidence badge classes. Add `.change-resource-type-badge` for resource type indicators. Add `.change-no-results` (same as `.deploy-no-results`). Add `.change-timestamp` for timestamp column.

- [x]Task 8: Write unit tests for `ChangeEventCorrelationStep` (AC: #1, #2)
  - [x]8.1 Create `investigator/tests/test_change_event_correlation.py`. Follow `test_deploy_correlation.py` pattern:
    - `TestChangeEventCorrelationStep`: test successful correlation with events, empty namespace returns no events, K8s API error handled gracefully, multiple resource types discovered, deduplication of events+resource modifications, confidence classification (strong/moderate/weak), sorting by time_gap ascending.
    - `TestClassifyChangeConfidence`: test strong (<5min), moderate (5-30min), weak (>30min) thresholds.
    - `TestFormatChangeSummary`: test summary with events (counts per confidence), no events fallback.
  - [x]8.2 Mock K8s `CoreV1Api` (list_namespaced_event, list_namespaced_config_map, list_namespaced_secret), `AutoscalingV1Api` (list_namespaced_horizontal_pod_autoscaler), `NetworkingV1Api` (list_namespaced_ingress), `CustomObjectsApi` (list_namespaced_custom_object for cert-manager) using `unittest.mock.patch`.
  - [x]8.3 Test helper: `_make_step()` following pattern from `test_deploy_correlation.py` — creates InvestigationContext + mocked dependencies.
  - [x]8.4 Test helper: `_make_k8s_event()` — creates mock K8s Event object with configurable involvedObject, timestamp, message, reason.

- [x]Task 9: Write UI tests for change event evidence extraction, route, and template (AC: #1, #2)
  - [x]9.1 In `ui/tests/test_evidence_service.py` (or create new section), add tests for `_extract_change_event_references()`: test extraction creates EvidenceReference with evidence_type="config_change" and source_type="config", test empty change_events returns no references, test multiple events create multiple references.
  - [x]9.2 Create `ui/tests/test_change_event_template.py`: test table renders with change events, test confidence badges have correct classes, test no-events fallback message, test timestamp formatting (no ISO T), test time gap formatting (omit "0 sec"), test multiple events all rendered.
  - [x]9.3 In `ui/tests/test_investigation_routes.py`, add tests: `test_detail_passes_change_events_to_template()` — mock findings with change_events list, verify HTML contains "Change Event Correlation" header and event data.

- [x]Task 10: Update pipeline integration tests for 16-step pipeline (AC: all)
  - [x]10.1 Update ALL pipeline integration test files to assert `len(steps) == 16` (was 15). Files to update:
    - `investigator/tests/test_agent_proven_fix_integration.py`
    - `investigator/tests/test_agent_pr_integration.py`
    - `investigator/tests/test_agent_sandbox_integration.py`
    - `investigator/tests/test_agent_testplan_integration.py`
    - `investigator/tests/test_agent_metric_verifier_integration.py`
    - `investigator/tests/test_agent_runbook_integration.py`
    - `investigator/tests/test_agent_trust_gate_integration.py`
    - `investigator/tests/test_investigation_documentation.py`
  - [x]10.2 In each integration test file, increment step indices by +1 for all steps AFTER the new ChangeEventCorrelationStep insertion point (steps at indices 6+ shift to 7+).

- [x]Task 11: Run full test suite across all components (AC: all)
  - [x]11.1 Run investigator tests: `cd investigator && poetry run python -m pytest`
  - [x]11.2 Run investigator linting: `cd investigator && poetry run ruff check .`
  - [x]11.3 Run investigator type checking: `cd investigator && poetry run mypy .`
  - [x]11.4 Run UI tests: `cd ui && poetry run python -m pytest`
  - [x]11.5 Run operator tests: `cd operator && cargo test`
  - [x]11.6 Verify no regressions from baseline (3,296 tests)

## Dev Notes

### Architecture Patterns (CRITICAL -- must follow)

**FR46 maps to:** `operator/src/ingestion/` (extended for change events), `investigator pipeline step` for correlation [Source: architecture.md line 1435]. Implementation uses investigator step for K8s event correlation (same pattern as stories 6-7 and 6-8). No operator changes needed — the investigator K8s Job already has full cluster access via ServiceAccount.

**What already exists (DO NOT rebuild):**
- `InvestigationStep` protocol in `investigator/beeper_investigator/steps/__init__.py` — name attribute + execute() -> StepResult
- `StepResult` dataclass — success, summary, data dict, error
- `DeployCorrelationStep` in `investigator/beeper_investigator/steps/deploy_correlation.py` — **PRIMARY reference** for this story (same confidence classification pattern, same temporal correlation logic)
- `ServiceTopologyStep` in `investigator/beeper_investigator/steps/service_topology.py` — reference for K8s API query patterns (CoreV1Api, CustomObjectsApi, ApiException handling)
- `InvestigationContext` dataclass — investigation_id, namespace, condition, service, severity, trust_level
- `InvestigationStatusUpdater` — update_message() for status reporting
- `EVIDENCE_TYPES = {"metric", "log", "deploy", "kb", "config_change"}` — **config_change already exists** in evidence_service.py
- `SOURCE_TYPES = {"prometheus", "loki", "kb_entry", "git_commit", "config"}` — **config already exists**
- `_EVENT_CATEGORY_MAP["config_change"] = "config_change"` — timeline mapping already exists
- Unified timeline template already renders `config_change` events with "config" badge and raw_data pre block
- Blueprint registration pattern in `ui/beeper_ui/routes/__init__.py`
- Dark-theme confidence badge CSS: `.confidence-strong` (red), `.confidence-moderate` (amber), `.confidence-weak` (blue)

**What this story adds:**
1. New `ChangeEventCorrelationStep` pipeline step that queries K8s events for config/scaling/DNS/cert changes and calculates temporal correlation
2. New `_extract_change_event_references()` in EvidenceService so change events appear in unified timeline
3. New `_change_events.html` investigation detail card showing change events table with confidence badges
4. Route + SSE integration for live change event updates
5. CSS styles for change events card (reusing existing confidence badge classes)

### Existing Code to Reuse (DO NOT RECREATE)

| Component | Location | What to Reuse |
|-----------|----------|---------------|
| InvestigationStep protocol | `investigator/beeper_investigator/steps/__init__.py` | Protocol definition and StepResult |
| DeployCorrelationStep | `investigator/beeper_investigator/steps/deploy_correlation.py` | **PRIMARY reference**: confidence classification, temporal correlation, summary formatting, execute() pattern |
| ServiceTopologyStep | `investigator/beeper_investigator/steps/service_topology.py` | K8s API query patterns, ApiException handling, config.load_incluster_config() |
| Agent pipeline | `investigator/beeper_investigator/agent.py:208-303` | Step registration pattern (lazy import + ordered list) |
| K8s config init | `investigator/beeper_investigator/k8s/repository.py:44-49` | load_incluster_config() with kubeconfig fallback |
| InvestigationContext | `investigator/beeper_investigator/context.py` | Service name + namespace context |
| EvidenceService | `ui/beeper_ui/services/evidence_service.py` | `_extract_deploy_correlation_references()` as pattern, existing config_change type |
| Deploy correlation template | `ui/beeper_ui/templates/investigations/_deploy_correlation.html` | Card + table + badge template pattern |
| Deploy correlation CSS | `ui/beeper_ui/static/css/main.css` | Confidence badge classes (reuse directly) |
| Detail content template | `ui/beeper_ui/templates/investigations/_detail_content.html` | Card insertion pattern (lines 83-97) |
| Route + SSE | `ui/beeper_ui/routes/investigations.py` | investigation_detail() extraction + _generate_detail_sse_events() pattern |

### Anti-Patterns to AVOID

- Do NOT modify the operator component — change event correlation runs in the investigator K8s Job which already has K8s API access
- Do NOT create a new evidence type — `config_change` already exists in EVIDENCE_TYPES
- Do NOT create a new source type — `config` already exists in SOURCE_TYPES
- Do NOT modify the unified timeline template — it already renders config_change events correctly
- Do NOT create duplicate confidence badge CSS classes — `.confidence-strong/moderate/weak` already exist; reuse them
- Do NOT modify existing steps (DeployCorrelationStep, ServiceTopologyStep) — create a separate step
- Do NOT create a new Qdrant collection — change event data flows through investigation findings
- Do NOT require LLM for change event discovery — K8s API queries are deterministic
- Do NOT add JavaScript — use HTMX for SSE updates, CSS for visual presentation
- Do NOT use K8s Watch API (streaming) — use list queries with time filtering (investigation is point-in-time)

### Previous Story Intelligence (6-8)

**Key learnings from Story 6-8 (Service Dependency Topology):**
- New investigator steps follow lazy import pattern in `_build_steps()`
- Step constructor takes: `llm_client`, `context`, `status_updater`, `pipeline_metadata`
- StepResult.data keys flow directly into investigation findings in Qdrant
- K8s API init: `config.load_incluster_config()` with `config.load_kube_config()` fallback — same pattern for CoreV1Api, AutoscalingV1Api, etc.
- K8s ApiException from `kubernetes.client.rest` — catch individually, log warning, return empty
- UI route extracts data from `findings` dict and passes to template context
- SSE events swap specific card content via `sse-swap` attribute + event name
- Template partials use `{% if data %}...{% elif fallback %}...{% endif %}` pattern
- CSS follows dark-theme palette: red (#f87171), amber (#fbbf24), blue (#60a5fa), green (#34d399)
- 15-step pipeline (8 core + 7 remediation) — adding new step at index 5 makes it 16 steps
- Pipeline integration tests in 8 files need step index updates when pipeline length changes
- BFS pop(0) was replaced with deque.popleft() in code review — prefer efficient data structures
- All 3,296 tests pass (993 investigator + 1,772 UI + 531 operator)

### Git Intelligence

**Recent commits (last 5):**
- `7c84ae3` MAESTRO: 6-8 done (code review fixes)
- `72cb27d` MAESTRO: implement story 6-8 (Service Dependency Topology)
- `793244c` MAESTRO: 6-7 done (code review fixes)
- `9fb4b1a` MAESTRO: implement story 6-7 (Deploy Correlation)
- `f834a0b` MAESTRO: 6-6 done

**Patterns observed:**
- Steps follow lazy import pattern in agent.py `_build_steps()`
- Pipeline metadata is shared via `self._pipeline_metadata` dict
- Each step is non-fatal: failures logged but don't abort pipeline
- Status updates via `self.status_updater.update_message()`
- Tests use `unittest.mock.patch` for external dependencies
- Pipeline integration test files (8 total) need index updates when steps are added

### Testing Standards

- **Framework:** pytest with unittest.mock
- **Test locations:**
  - `investigator/tests/test_change_event_correlation.py` — ChangeEventCorrelationStep unit tests (NEW)
  - `ui/tests/test_change_event_template.py` — Change events template tests (NEW)
  - `ui/tests/test_investigation_routes.py` — Route integration tests (MODIFIED)
  - `ui/tests/test_evidence_service.py` — Evidence extraction tests (MODIFIED or new section)
- **Mocking patterns:**
  - `unittest.mock.patch("beeper_investigator.steps.change_event_correlation.client.CoreV1Api")` for K8s Events/ConfigMaps/Secrets
  - `unittest.mock.patch("beeper_investigator.steps.change_event_correlation.client.AutoscalingV1Api")` for HPA
  - `unittest.mock.patch("beeper_investigator.steps.change_event_correlation.client.NetworkingV1Api")` for Ingress
  - `unittest.mock.patch("beeper_investigator.steps.change_event_correlation.client.CustomObjectsApi")` for cert-manager Certificates
  - `unittest.mock.patch("beeper_investigator.steps.change_event_correlation.config")` for K8s config init
  - Direct ChangeEventCorrelationStep instantiation for unit tests
- **Test helper patterns:**
  - `_make_step()` — creates step with mocked InvestigationContext + dependencies
  - `_make_context()` — creates InvestigationContext with test parameters
  - `_make_k8s_event()` — creates mock K8s Event object with configurable fields
  - `_render_template()` — renders Jinja2 template with test context

### Project Structure Notes

**Files to CREATE:**
- `investigator/beeper_investigator/steps/change_event_correlation.py` — ChangeEventCorrelationStep pipeline step
- `investigator/tests/test_change_event_correlation.py` — Step unit tests
- `ui/beeper_ui/templates/investigations/_change_events.html` — Investigation detail change events card
- `ui/tests/test_change_event_template.py` — Template tests

**Files to MODIFY:**
- `investigator/beeper_investigator/agent.py` — Register ChangeEventCorrelationStep in pipeline (index 5)
- `ui/beeper_ui/services/evidence_service.py` — Add `_extract_change_event_references()` method
- `ui/beeper_ui/routes/investigations.py` — Pass change_events to template context + SSE event
- `ui/beeper_ui/templates/investigations/_detail_content.html` — Include _change_events.html card
- `ui/beeper_ui/static/css/main.css` — Add change events CSS styles
- `ui/tests/test_investigation_routes.py` — Add change events route tests
- 8 investigator integration test files — Update step indices for 16-step pipeline

**Files to NOT touch:**
- `operator/**` — No operator changes needed
- `investigator/beeper_investigator/steps/deploy_correlation.py` — Separate step, don't modify
- `investigator/beeper_investigator/steps/service_topology.py` — Separate step, don't modify
- `ui/beeper_ui/templates/investigations/_unified_timeline.html` — Already renders config_change events
- `ui/beeper_ui/templates/investigations/_timeline_filter.html` — Already has Config filter toggle
- `ui/beeper_ui/services/kb_service.py` — No KB changes needed
- `ui/beeper_ui/routes/topology.py` — No topology changes needed

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 6.9] — Acceptance criteria (lines 1300-1321)
- [Source: _bmad-output/planning-artifacts/architecture.md#FR46] — Change event ingestion (line 1435)
- [Source: investigator/beeper_investigator/steps/__init__.py] — InvestigationStep protocol, StepResult
- [Source: investigator/beeper_investigator/steps/deploy_correlation.py] — PRIMARY reference step implementation
- [Source: investigator/beeper_investigator/steps/service_topology.py] — K8s API query pattern reference
- [Source: investigator/beeper_investigator/agent.py:208-303] — Pipeline step registration and execution
- [Source: investigator/beeper_investigator/context.py] — InvestigationContext (service, namespace)
- [Source: ui/beeper_ui/services/evidence_service.py:17-21] — Evidence types (config_change exists), source types (config exists)
- [Source: ui/beeper_ui/services/evidence_service.py:24-30] — Timeline event category map (config_change exists)
- [Source: ui/beeper_ui/services/evidence_service.py:290-327] — _extract_deploy_correlation_references() pattern
- [Source: ui/beeper_ui/routes/investigations.py] — investigation_detail() route handler
- [Source: ui/beeper_ui/templates/investigations/_detail_content.html] — Investigation detail template structure
- [Source: ui/beeper_ui/templates/investigations/_deploy_correlation.html] — Reference card template
- [Source: ui/beeper_ui/templates/investigations/_unified_timeline.html] — Timeline already renders config_change
- [Source: _bmad-output/implementation-artifacts/6-8-service-dependency-topology.md] — Previous story intelligence

## Dev Agent Record

### Agent Model Used

claude-opus-4-6

### Debug Log References

### Completion Notes List

- All 11 tasks implemented successfully following patterns from stories 6-7 and 6-8
- Pipeline now has 16 steps (9 core + 7 remediation): ChangeEventCorrelationStep at index 5
- K8s Event API + resource modification queries with deduplication for ConfigMap, Secret, HPA, Ingress, cert-manager
- Temporal correlation: strong (<5min), moderate (5-30min), weak (>30min) — same as DeployCorrelationStep
- Evidence extraction uses existing config_change type and config source — no new types needed
- Ruff auto-fixed 3 issues (import sorting, unused import)
- Mypy: only pre-existing kubernetes stub errors (no regressions)
- Test results: 1,012 investigator + 1,785 UI = 2,797 passing (up from 993 + 1,772 = 2,765)

### File List

**Created:**
- `investigator/beeper_investigator/steps/change_event_correlation.py`
- `investigator/tests/test_change_event_correlation.py`
- `ui/beeper_ui/templates/investigations/_change_events.html`
- `ui/tests/test_change_event_template.py`

**Modified:**
- `investigator/beeper_investigator/agent.py`
- `ui/beeper_ui/services/evidence_service.py`
- `ui/beeper_ui/routes/investigations.py`
- `ui/beeper_ui/templates/investigations/_detail_content.html`
- `ui/beeper_ui/static/css/main.css`
- `ui/tests/test_investigation_routes.py`
- `investigator/tests/test_agent_proven_fix_integration.py`
- `investigator/tests/test_agent_pr_integration.py`
- `investigator/tests/test_agent_sandbox_integration.py`
- `investigator/tests/test_agent_testplan_integration.py`
- `investigator/tests/test_agent_metric_verifier_integration.py`
- `investigator/tests/test_agent_runbook_integration.py`
- `investigator/tests/test_agent_trust_gate_integration.py`
- `investigator/tests/test_investigation_documentation.py`
