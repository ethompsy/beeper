# Story 6.8: Service Dependency Topology

Status: review

## Story

As the **system**,
I want to discover and display service dependency topology,
so that SREs can understand blast radius and identify cascading failure paths.

## Acceptance Criteria

1. **Given** K8s service definitions and network traffic patterns **When** the topology discovery process runs **Then** service-to-service dependencies are identified and stored **And** the topology is refreshable on demand or via periodic background process

2. **Given** a user navigates to the topology view (`/topology`) **When** the page loads **Then** services are displayed as a graph with dependency edges **And** services with active investigations or SLO breaches are highlighted

3. **Given** an investigation on a specific service **When** the investigation detail shows dependencies **Then** upstream and downstream services are listed with their current health status **And** potential blast radius is indicated

## Tasks / Subtasks

- [x] Task 1: Create `ServiceTopologyStep` investigator pipeline step (AC: #1, #3)
  - [x] 1.1 Create `investigator/beeper_investigator/steps/service_topology.py` with `ServiceTopologyStep` class following the `InvestigationStep` protocol (name attribute + execute() -> StepResult). Constructor takes: `llm_client: LlmClient`, `context: InvestigationContext`, `status_updater: InvestigationStatusUpdater`, `pipeline_metadata: dict`. Add `MAX_DEPENDENCY_DEPTH = 2` constant for limiting traversal depth.
  - [x] 1.2 Implement `_discover_services()` method: use K8s `CoreV1Api().list_namespaced_service()` to list all services in `self.context.namespace`. Parse each service's spec (selectors, ports, labels). Return list of service info dicts with: `name`, `namespace`, `labels`, `selectors`, `ports`, `cluster_ip`. Handle ApiException gracefully — log warning and return empty list.
  - [x] 1.3 Implement `_discover_dependencies()` method: use K8s `CoreV1Api().list_namespaced_endpoints()` to examine endpoint subsets and addresses. For each endpoint, identify the target service and any `targetRef` pods. Cross-reference pod labels with service selectors to identify service-to-service connections. Also check for services referenced in pod environment variables (e.g., `SERVICE_URL` patterns) and ConfigMaps. Return a list of dependency dicts with: `source_service`, `target_service`, `dependency_type` (endpoint, env_var, configmap), `port`.
  - [x] 1.4 Implement `_get_service_health()` method: query K8s `CustomObjectsApi().list_namespaced_custom_object()` for ServiceLevel CRDs (group="beeper.dev", version="v1", plural="servicelevels"). For each ServiceLevel, extract compliance status and burn rate from CRD status. Also check for active Investigation CRDs (plural="investigations", status="investigating"). Return a dict mapping service name to health info: `slo_status` (healthy/warning/critical), `has_active_investigation` (bool), `burn_rate` (float|None).
  - [x] 1.5 Implement `_classify_topology()` method: given the investigation's target service (`self.context.service`) and the full dependency graph, classify services as: `upstream` (services that the target depends on), `downstream` (services that depend on the target), `unrelated`. Calculate `blast_radius` as count of downstream services (direct + transitive up to MAX_DEPENDENCY_DEPTH). Return topology classification dict.
  - [x] 1.6 Implement `execute()` method: call `_discover_services()`, then `_discover_dependencies()`, then `_get_service_health()`, then `_classify_topology()`. Return `StepResult(success=True, summary=..., data={"service_topology": {"subject_service": ..., "upstream": [...], "downstream": [...], "all_services": [...], "dependencies": [...], "health": {...}, "blast_radius": N, "discovery_timestamp": ...}, "topology_discovery_attempted": True})`.

- [x] Task 2: Register `ServiceTopologyStep` in the agent pipeline (AC: #1)
  - [x] 2.1 In `investigator/beeper_investigator/agent.py`, add lazy import for `ServiceTopologyStep` from `beeper_investigator.steps.service_topology` (after the DeployCorrelationStep import).
  - [x] 2.2 Insert `ServiceTopologyStep` into the steps list AFTER `DeployCorrelationStep` and BEFORE `RCAHypothesisStep` (between current pipeline index 3 and 4). Pass `llm_client`, `context`, `status_updater`, and `pipeline_metadata=self._pipeline_metadata`.

- [x] Task 3: Create `TopologyService` in the UI (AC: #2)
  - [x] 3.1 Create `ui/beeper_ui/services/topology_service.py` with `TopologyService` class and `TopologyServiceError` exception. Constructor takes `qdrant_url: str`. Add a `get_topology_service()` factory function following the pattern from `get_evidence_service()`.
  - [x] 3.2 Implement `get_all_services_topology()` method: query Qdrant `investigations` collection to aggregate known services from recent investigations. For each unique service, collect: latest topology data from investigation findings, SLO status from `slo_snapshots` collection, active investigation count. Return a dict with `services` list and `dependencies` list.
  - [x] 3.3 Implement `get_service_dependencies(service_name)` method: query Qdrant for the most recent investigation involving the given service. Extract topology data from findings. Return upstream/downstream services with health status.

- [x] Task 4: Create topology route and templates (AC: #2)
  - [x] 4.1 Create `ui/beeper_ui/routes/topology.py` with `topology_bp = Blueprint("topology", __name__, url_prefix="/topology")`. Add `index()` route at `/` that calls `TopologyService.get_all_services_topology()` and renders `topology/index.html`. Pass `services`, `dependencies`, and `active_investigations` to template context.
  - [x] 4.2 Register `topology_bp` in `ui/beeper_ui/routes/__init__.py` following the existing blueprint registration pattern.
  - [x] 4.3 Create `ui/beeper_ui/templates/topology/index.html` extending `base.html`. Display a page title "Service Dependency Topology" with a grid of service cards. Each card shows: service name, health status badge (healthy=green, warning=amber, critical=red), active investigation indicator, dependency count (upstream/downstream). Cards link to service detail. Include a "Refresh Topology" button that triggers an HTMX GET to reload the topology data.
  - [x] 4.4 Create `ui/beeper_ui/templates/topology/_service_card.html` partial for individual service card rendering. Show: service name as heading, health badge using `.topology-health-badge` with status variant classes, upstream count badge, downstream count badge, active investigation badge (if any), click to expand showing dependency list.
  - [x] 4.5 Create `ui/beeper_ui/templates/topology/_dependency_graph.html` partial showing a table/list representation of all dependencies. Columns: Source Service, Target Service, Dependency Type, Port. Highlight rows where either service has active investigations.

- [x] Task 5: Add service topology card to investigation detail (AC: #3)
  - [x] 5.1 Create `ui/beeper_ui/templates/investigations/_service_topology.html` partial template. Show a "Service Dependencies" card with: investigated service highlighted as the subject, upstream services list with health badges, downstream services list with health badges, blast radius count ("N downstream services potentially affected"). When no topology data exists, show "Topology data not available" info message.
  - [x] 5.2 In `ui/beeper_ui/templates/investigations/_detail_content.html`, include `_service_topology.html` AFTER the Deploy Correlation card, passing `service_topology` from the context.

- [x] Task 6: Wire topology data into investigation detail route (AC: #3)
  - [x] 6.1 In `ui/beeper_ui/routes/investigations.py`, in `investigation_detail()`, extract `service_topology` from `findings` dict. Pass `service_topology` to the template context.
  - [x] 6.2 Update the SSE stream in `_generate_detail_sse_events()` to include topology data when available — emit `topology-update` event that swaps `_service_topology.html`.

- [x] Task 7: Add topology CSS styles (AC: #2, #3)
  - [x] 7.1 In `ui/beeper_ui/static/css/main.css`, add styles for the standalone topology page: `.topology-grid` (CSS grid, responsive, 3 columns), `.topology-service-card` (card styling with hover effect), `.topology-health-badge` with status variants (`.health-healthy` green, `.health-warning` amber, `.health-critical` red), `.topology-investigation-indicator` (pulsing dot), `.topology-dependency-count` badge styles.
  - [x] 7.2 Add styles for the investigation detail topology card: `.service-topology-card`, `.topology-subject-service` (highlighted), `.topology-service-list` (upstream/downstream list), `.topology-blast-radius` (count display with warning styling), `.topology-no-data` info message. Follow the same dark-theme color palette as deploy correlation badges.

- [x] Task 8: Write unit tests for `ServiceTopologyStep` (AC: #1, #3)
  - [x] 8.1 Create `investigator/tests/test_service_topology.py`. Test classes: `TestServiceTopologyStep` with tests for: successful topology discovery with services and dependencies, empty namespace returns empty topology, K8s API error handled gracefully, blast radius calculation (direct + transitive), health status integration with ServiceLevel CRDs, active investigation detection, MAX_DEPENDENCY_DEPTH limits traversal.
  - [x] 8.2 Mock K8s `CoreV1Api`, `CustomObjectsApi` using `unittest.mock.patch`. Test topology classification (upstream/downstream/unrelated) with various dependency graph shapes.

- [x] Task 9: Write UI tests for topology service, routes, and templates (AC: #2, #3)
  - [x] 9.1 Create `ui/tests/test_topology_service.py`: test `get_all_services_topology()` returns aggregated topology, test `get_service_dependencies()` returns correct upstream/downstream, test empty Qdrant returns empty topology gracefully.
  - [x] 9.2 Create `ui/tests/test_topology_routes.py`: test `/topology` renders index page, test service cards render with correct health badges, test HTMX refresh triggers topology reload.
  - [x] 9.3 Create `ui/tests/test_service_topology_template.py`: test investigation detail topology card renders upstream/downstream lists, test blast radius count display, test no-topology fallback message, test health badge classes.
  - [x] 9.4 In `ui/tests/test_investigation_routes.py`, add tests: verify `service_topology` is passed to template context from findings.

- [x] Task 10: Run full test suite across all components (AC: all)
  - [x] 10.1 Run investigator tests: `cd investigator && poetry run python -m pytest`
  - [x] 10.2 Run investigator linting: `cd investigator && poetry run ruff check .`
  - [x] 10.3 Run investigator type checking: `cd investigator && poetry run mypy .`
  - [x] 10.4 Run UI tests: `cd ui && poetry run python -m pytest`
  - [x] 10.5 Run operator tests: `cd operator && cargo test`
  - [x] 10.6 Verify no regressions from baseline (2,716 tests)

## Dev Notes

### Architecture Patterns (CRITICAL -- must follow)

**FR45 maps to:** `ui/routes/analytics.py`, `operator/src/api.rs` (topology endpoint) [Source: architecture.md line 1435]. Implementation uses `ui/routes/topology.py` (dedicated route) + investigator step for discovery. No operator changes needed — topology discovery runs in the investigator K8s Job which already has full cluster access.

**What already exists (DO NOT rebuild):**
- `InvestigationStep` protocol in `investigator/beeper_investigator/steps/__init__.py` — name attribute + execute() -> StepResult
- `StepResult` dataclass — success, summary, data dict, error
- `DeployCorrelationStep` in `investigator/beeper_investigator/steps/deploy_correlation.py` — reference implementation for K8s-querying step pattern
- `RepositoryLookup` in `investigator/beeper_investigator/k8s/repository.py` — K8s API init pattern (load_incluster_config with kubeconfig fallback)
- `InvestigationContext` dataclass — investigation_id, namespace, condition, service, severity, trust_level
- `InvestigationStatusUpdater` in `investigator/beeper_investigator/k8s/status.py` — update_message() for status reporting
- ServiceLevel CRD schema in `operator/src/crds/servicelevel.rs` — service, SLI type, SLO targets
- SLO service in `ui/beeper_ui/services/slo_service.py` — already queries SLO data from Qdrant
- Evidence types: "deploy", "metric", "log", "kb", "config_change" in `ui/beeper_ui/services/evidence_service.py`
- Blueprint registration pattern in `ui/beeper_ui/routes/__init__.py`
- Investigation detail template structure in `ui/beeper_ui/templates/investigations/_detail_content.html`
- Dark-theme CSS color palette in `ui/beeper_ui/static/css/main.css`

**What this story adds:**
1. New `ServiceTopologyStep` pipeline step that discovers K8s service dependencies and health
2. New `TopologyService` UI service for aggregating topology data from Qdrant
3. New `/topology` route and templates for standalone topology view
4. New `_service_topology.html` investigation detail partial showing upstream/downstream with blast radius
5. CSS styles for topology visualization (service cards, health badges, dependency graph)

### Existing Code to Reuse (DO NOT RECREATE)

| Component | Location | What to Reuse |
|-----------|----------|---------------|
| InvestigationStep protocol | `investigator/beeper_investigator/steps/__init__.py` | Protocol definition and StepResult |
| DeployCorrelationStep | `investigator/beeper_investigator/steps/deploy_correlation.py` | Reference step implementation + K8s query pattern |
| Agent pipeline | `investigator/beeper_investigator/agent.py:180-297` | Step registration pattern (lazy import + ordered list) |
| K8s config init | `investigator/beeper_investigator/k8s/repository.py:44-49` | load_incluster_config() with kubeconfig fallback |
| InvestigationContext | `investigator/beeper_investigator/context.py` | Service name + namespace context |
| Blueprint registration | `ui/beeper_ui/routes/__init__.py` | Import + register pattern |
| EvidenceService | `ui/beeper_ui/services/evidence_service.py` | Factory function pattern (get_*_service) |
| SLO Service | `ui/beeper_ui/services/slo_service.py` | Qdrant query pattern for service health |
| Deploy correlation template | `ui/beeper_ui/templates/investigations/_deploy_correlation.html` | Card + table + badge template pattern |
| Deploy correlation CSS | `ui/beeper_ui/static/css/main.css:5216-5287` | Dark-theme badge/card color patterns |

### Anti-Patterns to AVOID

- Do NOT modify the operator component — topology discovery runs in the investigator K8s Job which already has K8s API access
- Do NOT add a new evidence type for topology — topology is context/enrichment, not investigation evidence
- Do NOT require external graph visualization libraries (D3.js, vis.js) — use CSS grid layout with cards and table for dependency display
- Do NOT add JavaScript for interactivity — use HTMX for refresh, CSS for visual presentation
- Do NOT modify existing steps — create a separate `ServiceTopologyStep` to maintain single-responsibility
- Do NOT create a new Qdrant collection — topology data flows through investigation findings in existing `investigations` collection
- Do NOT require LLM for topology discovery — K8s API queries are deterministic
- Do NOT modify the unified timeline — topology is not a timeline event, it's structural context

### Previous Story Intelligence (6-7)

**Key learnings from Story 6-7 (Deploy Correlation):**
- New investigator steps follow lazy import pattern in `_build_steps()`
- Step constructor takes: `llm_client`, `context`, `status_updater`, `pipeline_metadata`
- StepResult.data keys flow directly into investigation findings in Qdrant
- UI route extracts data from `findings` dict and passes to template context
- SSE events swap specific card content via `sse-swap` attribute + event name
- Template partials use `{% if data %}...{% elif fallback %}...{% endif %}` pattern
- CSS follows dark-theme palette: red (#f87171), amber (#fbbf24), blue (#60a5fa), green (#34d399)
- 14-step pipeline (7 core + 7 remediation) — adding new step at index 4 makes it 15 steps
- Pipeline integration tests in 8 files need step index updates when pipeline length changes
- All 2,716 tests pass (972 investigator + 1,744 UI + 531 operator baseline)

### Git Intelligence

**Recent commits (last 5):**
- `793244c` MAESTRO: 6-7 done (code review fixes)
- `9fb4b1a` MAESTRO: implement story 6-7 (Deploy Correlation)
- `f834a0b` MAESTRO: 6-6 done
- `5f135a8` MAESTRO: implement story 6-6 (Unified Investigation Timeline)
- `3c84a74` MAESTRO: 6-5 done

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
  - `investigator/tests/test_service_topology.py` — ServiceTopologyStep unit tests (NEW)
  - `ui/tests/test_topology_service.py` — TopologyService unit tests (NEW)
  - `ui/tests/test_topology_routes.py` — Topology route tests (NEW)
  - `ui/tests/test_service_topology_template.py` — Investigation detail topology template tests (NEW)
  - `ui/tests/test_investigation_routes.py` — Route integration tests (MODIFIED)
- **Mocking patterns:**
  - `unittest.mock.patch("beeper_investigator.steps.service_topology.client.CoreV1Api")` for K8s Services/Endpoints
  - `unittest.mock.patch("beeper_investigator.steps.service_topology.client.CustomObjectsApi")` for ServiceLevel/Investigation CRDs
  - `unittest.mock.patch("beeper_ui.services.topology_service.QdrantClient")` for topology service
  - Direct TopologyService instantiation for unit tests

### Project Structure Notes

**Files to CREATE:**
- `investigator/beeper_investigator/steps/service_topology.py` — ServiceTopologyStep pipeline step
- `investigator/tests/test_service_topology.py` — Step unit tests
- `ui/beeper_ui/services/topology_service.py` — TopologyService for standalone topology view
- `ui/beeper_ui/routes/topology.py` — `/topology` route and blueprint
- `ui/beeper_ui/templates/topology/index.html` — Standalone topology page
- `ui/beeper_ui/templates/topology/_service_card.html` — Service card partial
- `ui/beeper_ui/templates/topology/_dependency_graph.html` — Dependency table partial
- `ui/beeper_ui/templates/investigations/_service_topology.html` — Investigation detail topology card
- `ui/tests/test_topology_service.py` — TopologyService tests
- `ui/tests/test_topology_routes.py` — Topology route tests
- `ui/tests/test_service_topology_template.py` — Template tests

**Files to MODIFY:**
- `investigator/beeper_investigator/agent.py` — Register ServiceTopologyStep in pipeline (index 4)
- `ui/beeper_ui/routes/__init__.py` — Register topology_bp blueprint
- `ui/beeper_ui/routes/investigations.py` — Pass service_topology to template context
- `ui/beeper_ui/templates/investigations/_detail_content.html` — Include _service_topology.html card
- `ui/beeper_ui/static/css/main.css` — Add topology CSS styles
- `ui/tests/test_investigation_routes.py` — Add topology route integration tests
- 8 investigator integration test files — Update step indices for 15-step pipeline

**Files to NOT touch:**
- `operator/**` — No operator changes needed
- `investigator/beeper_investigator/steps/deploy_correlation.py` — Separate step, don't modify
- `ui/beeper_ui/services/evidence_service.py` — Topology is context, not evidence
- `ui/beeper_ui/templates/investigations/_unified_timeline.html` — Topology is not a timeline event
- `ui/beeper_ui/templates/investigations/_timeline_filter.html` — No filter changes needed
- `ui/beeper_ui/services/kb_service.py` — No KB changes needed

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 6.8] — Acceptance criteria (lines 1277-1298)
- [Source: _bmad-output/planning-artifacts/architecture.md#FR45] — Service topology: ui/routes/analytics.py, operator/src/api.rs (line 1435)
- [Source: investigator/beeper_investigator/steps/__init__.py] — InvestigationStep protocol, StepResult
- [Source: investigator/beeper_investigator/steps/deploy_correlation.py] — Reference step implementation pattern
- [Source: investigator/beeper_investigator/agent.py:180-297] — Pipeline step registration and execution
- [Source: investigator/beeper_investigator/k8s/repository.py:41-50] — K8s config init pattern
- [Source: investigator/beeper_investigator/context.py] — InvestigationContext (service, namespace)
- [Source: ui/beeper_ui/routes/__init__.py] — Blueprint registration pattern
- [Source: ui/beeper_ui/services/evidence_service.py:17-21] — Evidence types and source types
- [Source: ui/beeper_ui/routes/investigations.py] — investigation_detail() route handler
- [Source: ui/beeper_ui/templates/investigations/_detail_content.html] — Investigation detail template structure
- [Source: _bmad-output/implementation-artifacts/6-7-deploy-correlation.md] — Previous story intelligence

## Dev Agent Record

### Agent Model Used

claude-opus-4-6

### Debug Log References

### Completion Notes List

- Created `ServiceTopologyStep` pipeline step that discovers K8s service dependencies, health status from ServiceLevel CRDs, and classifies upstream/downstream topology with blast radius calculation
- Registered `ServiceTopologyStep` in pipeline at index 4 (after DeployCorrelation, before RCAHypothesis) — 15-step pipeline (8 core + 7 remediation)
- Created `TopologyService` UI service aggregating topology data from Qdrant investigation findings
- Created `/topology` standalone page with responsive CSS grid layout, service cards with health badges, dependency table, and HTMX refresh
- Created `_service_topology.html` investigation detail card showing upstream/downstream with health badges and blast radius
- Wired topology data into investigation detail route and SSE stream (topology-update event)
- Added comprehensive dark-theme CSS styles for topology visualization (standalone page + investigation detail)
- Updated 8 pipeline integration test files for 15-step pipeline (step index +1 offset)
- 45 new tests total: 18 investigator (ServiceTopologyStep), 7 topology service, 8 topology routes, 10 topology template, 2 investigation route
- All 3,292 tests pass (990 investigator + 1,771 UI + 531 operator). Zero regressions from baseline.

### File List

**Created:**
- `investigator/beeper_investigator/steps/service_topology.py`
- `investigator/tests/test_service_topology.py`
- `ui/beeper_ui/services/topology_service.py`
- `ui/beeper_ui/routes/topology.py`
- `ui/beeper_ui/templates/topology/index.html`
- `ui/beeper_ui/templates/topology/_topology_content.html`
- `ui/beeper_ui/templates/topology/_service_card.html`
- `ui/beeper_ui/templates/topology/_dependency_graph.html`
- `ui/beeper_ui/templates/investigations/_service_topology.html`
- `ui/tests/test_topology_service.py`
- `ui/tests/test_topology_routes.py`
- `ui/tests/test_service_topology_template.py`

**Modified:**
- `investigator/beeper_investigator/agent.py` — Register ServiceTopologyStep in pipeline (index 4)
- `ui/beeper_ui/routes/__init__.py` — Register topology_bp blueprint
- `ui/beeper_ui/routes/investigations.py` — Pass service_topology to template, add SSE event
- `ui/beeper_ui/templates/investigations/_detail_content.html` — Include _service_topology.html card
- `ui/beeper_ui/static/css/main.css` — Add topology CSS styles
- `ui/tests/test_investigation_routes.py` — Add topology integration tests
- `investigator/tests/test_agent_proven_fix_integration.py` — Update step indices (14→15)
- `investigator/tests/test_agent_pr_integration.py` — Update step indices
- `investigator/tests/test_agent_sandbox_integration.py` — Update step indices
- `investigator/tests/test_agent_testplan_integration.py` — Update step indices
- `investigator/tests/test_agent_metric_verifier_integration.py` — Update step indices
- `investigator/tests/test_agent_runbook_integration.py` — Update step indices
- `investigator/tests/test_agent_trust_gate_integration.py` — Update step indices
- `investigator/tests/test_investigation_documentation.py` — Update step indices
