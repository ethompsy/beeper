# Story 3.2: Investigator Agent Scaffold

Status: done

## Story

As **Beeper**,
I want a Python investigator agent that can be spawned for each suspicious condition,
So that investigations run in isolation with dedicated resources.

## Acceptance Criteria

### AC1: Full Investigation Context Initialization
**Given** the operator creates an Investigation CR
**When** the investigator Job starts
**Then** the Python agent initializes with:
- Investigation ID and condition details (condition, service, severity)
- Qdrant connection for KB access
- LLM client (LiteLLM) configuration
- Source clients for querying Prometheus/Loki

### AC2: Progress Tracking via Investigation CR
**Given** the investigator agent starts
**When** it begins processing
**Then** it logs structured JSON with `investigation_id` context
**And** progress updates are written to Investigation CR status via `message` field

### AC3: Graceful Lifecycle Management
**Given** the investigation completes or fails
**When** the agent exits
**Then** exit code reflects success/failure (0 = success, 1 = failure)
**And** final status is persisted to Investigation CR before termination

## Tasks / Subtasks

- [x] Task 1: Create InvestigationContext and read full environment config (AC: #1)
  - [x]1.1: Create `investigator/beeper_investigator/context.py` — `InvestigationContext` dataclass bundling all investigation env vars: `investigation_id`, `namespace`, `condition`, `service`, `severity`
  - [x]1.2: Factory method `InvestigationContext.from_env()` — reads from `INVESTIGATION_ID`, `INVESTIGATION_NAMESPACE`, `INVESTIGATION_CONDITION`, `INVESTIGATION_SERVICE`, `INVESTIGATION_SEVERITY`
  - [x]1.3: Validate required fields (investigation_id, namespace are required; condition/service/severity have defaults)

- [x] Task 2: Add Investigation CR status update capability (AC: #2, #3)
  - [x]2.1: Add `message: Option<String>` field to `InvestigationStatus` in `operator/src/crds/investigation.rs` — for progress messages from the investigator pod (the controller does NOT touch this field)
  - [x]2.2: Update Investigation CRD YAML schema in `helm/beeper/templates/crds/investigation-crd.yaml` — add `message` to status properties
  - [x]2.3: Create `investigator/beeper_investigator/k8s/__init__.py` and `investigator/beeper_investigator/k8s/status.py`
  - [x]2.4: Implement `InvestigationStatusUpdater` class — uses `kubernetes` Python client to PATCH Investigation CR status subresource
  - [x]2.5: Methods: `update_message(msg)`, `set_completed(summary)`, `set_failed(error)` — all PATCH the Investigation CR's `.status` using the K8s custom resource API
  - [x]2.6: Use in-cluster config (`kubernetes.config.load_incluster_config()`) for ServiceAccount auth
  - [x]2.7: Add `kubernetes` package to `pyproject.toml` dependencies
  - [x]2.8: Update investigator RBAC in `helm/beeper/templates/investigator-rbac.yaml` — add `get`, `patch` permissions on `investigations.beeper.dev` and `investigations.beeper.dev/status`

- [x] Task 3: Create source query clients (AC: #1)
  - [x]3.1: Create `investigator/beeper_investigator/sources/__init__.py`
  - [x]3.2: Create `investigator/beeper_investigator/sources/prometheus.py` — `PrometheusClient` class with `query(promql)` and `query_range(promql, start, end, step)` methods using `httpx`
  - [x]3.3: Create `investigator/beeper_investigator/sources/loki.py` — `LokiClient` class with `query(logql)` and `query_range(logql, start, end)` methods using `httpx`
  - [x]3.4: Both clients read from env vars: `PROMETHEUS_URL`, `LOKI_URL` — optional (sources may not be configured)
  - [x]3.5: Support optional basic auth via `PROMETHEUS_AUTH` and `LOKI_AUTH` env vars (base64-encoded `user:pass`)
  - [x]3.6: Add env var injection to operator's `investigator_job.rs` — inject `PROMETHEUS_URL` and `LOKI_URL` from `InvestigatorConfig` fields
  - [x]3.7: Add `prometheus_url` and `loki_url` fields to `InvestigatorConfig` struct with env var loading from `BEEPER_PROMETHEUS_URL` and `BEEPER_LOKI_URL` (defaults to empty string = not configured)

- [x] Task 4: Create InvestigatorAgent lifecycle framework (AC: #1, #2, #3)
  - [x]4.1: Create `investigator/beeper_investigator/agent.py` — `InvestigatorAgent` class
  - [x]4.2: Constructor takes: `context: InvestigationContext`, `kb_client: KBClient`, `llm_client: LlmClient`, `sources: SourceClients`, `status_updater: InvestigationStatusUpdater`
  - [x]4.3: `SourceClients` dataclass: bundles optional `PrometheusClient` and `LokiClient` (both nullable — sources may not be configured)
  - [x]4.4: `run()` method orchestrates lifecycle: `_initialize()` → `_run_steps()` → `_finalize(result)`
  - [x]4.5: `_initialize()`: validate connections (KB health check, LLM test, source connectivity), update status message to "Initializing investigation"
  - [x]4.6: `_run_steps()`: placeholder that returns `InvestigationResult(success=True, summary="No investigation steps configured")` — future stories (3.3-3.8) will add actual steps
  - [x]4.7: `_finalize(result)`: persist investigation summary to Qdrant `investigations` collection, update Investigation CR status message with result summary, set completed or failed
  - [x]4.8: `InvestigationResult` dataclass: `success: bool`, `summary: str`, `findings: list[str]`, `error: str | None`
  - [x]4.9: Wrap entire `run()` in try/except — on any exception, log error, update Investigation CR status with error, return failure exit code

- [x] Task 5: Wire agent into main.py (AC: #1, #2, #3)
  - [x]5.1: Replace the TODO block in `main.py` with full agent instantiation and execution
  - [x]5.2: Build InvestigationContext from env, create all clients, create InvestigatorAgent
  - [x]5.3: Call `agent.run()` — returns InvestigationResult
  - [x]5.4: Exit with code 0 on success, 1 on failure
  - [x]5.5: Ensure cleanup in `finally` block (close KB client, close source clients)

- [x] Task 6: Tests (AC: all)
  - [x]6.1: Unit test `InvestigationContext.from_env()` — all env vars read correctly
  - [x]6.2: Unit test `InvestigationContext.from_env()` — missing required var raises SystemExit
  - [x]6.3: Unit test `InvestigationStatusUpdater.update_message()` — mocked K8s API, verify PATCH payload
  - [x]6.4: Unit test `InvestigationStatusUpdater.set_completed()` — verify correct status fields
  - [x]6.5: Unit test `InvestigationStatusUpdater.set_failed()` — verify error field populated
  - [x]6.6: Unit test `PrometheusClient.query()` — mocked HTTP, verify PromQL passed correctly
  - [x]6.7: Unit test `LokiClient.query()` — mocked HTTP, verify LogQL passed correctly
  - [x]6.8: Unit test source clients handle connection failure gracefully
  - [x]6.9: Unit test `InvestigatorAgent.run()` lifecycle — mock all dependencies, verify initialization → steps → finalize sequence
  - [x]6.10: Unit test `InvestigatorAgent.run()` failure path — verify error is captured and status updated
  - [x]6.11: Integration test: main.py with mocked env vars — verify successful exit code 0
  - [x]6.12: Integration test: main.py with missing INVESTIGATION_ID — verify exit code 1
  - [x]6.13: Rust test: `InvestigatorConfig` with source URL env vars
  - [x]6.14: Rust test: Job env vars include PROMETHEUS_URL and LOKI_URL

## Dev Notes

### Architecture Compliance

**Source:** [architecture.md - Investigation Engine Architecture]

> Prometheus/Loki → Operator (detect) → K8s Job (investigate) → Qdrant (store) → UI (display)

This story implements the **K8s Job (investigate)** scaffold. The investigator agent runs as a K8s Job spawned by the operator (Story 1-9). It receives investigation context via environment variables, queries sources (Prometheus/Loki) and KB (Qdrant), uses LLM (LiteLLM) for reasoning, and writes results back.

**Source:** [architecture.md - Technology Stack]

> Investigator Agents: Python — Rapid development, excellent LLM libraries
> Language: Python 3.11+ for investigators and UI

All investigator code MUST be Python. The agent framework lives in the `investigator/` directory.

### Critical Design Decisions

**1. Synchronous agent (not async):**
The existing `main.py` and all clients (`LlmClient`, `KBClient`) use synchronous code. Keep the agent synchronous for the scaffold. Future stories can introduce async if concurrent source queries prove necessary.

**2. K8s status updates vs controller reconciliation:**
The Investigation controller (Rust operator) manages the `phase` field (Pending → Running → Completed/Failed) based on Job status. The investigator agent writes ONLY to the `message` field for progress tracking. This avoids race conditions between the controller and the investigator.

**Do NOT** have the investigator update the `phase` field — the controller owns that lifecycle.

**3. Source clients are optional:**
Not all deployments have both Prometheus and Loki configured. Source clients are nullable — if `PROMETHEUS_URL` is empty or unset, `PrometheusClient` is `None`. The agent handles this gracefully.

**4. Agent step system for extensibility:**
The `_run_steps()` method is a placeholder. Stories 3.3-3.8 will each add investigation steps:
- 3.3: Customer impact assessment step
- 3.4: KB query step
- 3.5: Signal correlation step
- 3.6: RCA hypothesis generation step
- 3.7: Resolution recommendations step
- 3.8: Investigation documentation step

Design the agent so steps can be added without modifying the lifecycle framework.

### Existing Code to Build On (Do NOT Redefine)

**From Story 1-9 (`investigator/beeper_investigator/main.py`):**
- `JsonFormatter` — JSON log formatter with investigation_id context
- `configure_logging(investigation_id)` — sets up structured logging
- `get_required_env(name)` — reads required env var, exits with code 1 if missing
- `main()` — entry point, initializes LLM and KB clients

**From Story 1-8 (`investigator/beeper_investigator/llm/client.py`):**
```python
class LlmClient:
    @classmethod
    def from_env(cls) -> "LlmClient"   # Reads BEEPER_LLM_* env vars
    def complete(self, prompt: str, system: str = None) -> str
    async def acomplete(self, prompt: str, system: str = None) -> str
    def test_connection(self) -> bool
    provider: str   # anthropic, openai, azure, ollama
    model: str      # e.g., claude-sonnet-4
```

**From Story 1-2 (`investigator/beeper_investigator/kb/client.py`):**
```python
class KBClient:
    def __init__(self, host=None, port=None)  # Reads QDRANT_HOST, QDRANT_PORT from env
    def health_check(self) -> bool
    def search(self, collection, query_vector, filters=None, limit=10) -> list[SearchResult]
    def upsert(self, collection, points) -> None
    def close(self) -> None
    host: str
    port: int
```

**From Story 1-9 (`operator/src/crds/investigation.rs`):**
```rust
pub struct InvestigationStatus {
    pub phase: Option<InvestigationPhase>,      // Pending, Running, Completed, Failed
    pub started_at: Option<String>,
    pub completed_at: Option<String>,
    pub job_name: Option<String>,
    pub error: Option<String>,
    // ADD: pub message: Option<String>,  ← NEW for this story
}
```

**From Story 1-9 (`operator/src/investigator_job.rs`):**
```rust
pub struct InvestigatorConfig {
    pub image: String,                     // "beeper/investigator:latest"
    pub qdrant_host: String,               // "qdrant"
    pub qdrant_port: String,               // "6333"
    pub llm_provider: String,              // "anthropic"
    pub llm_model: String,                 // "claude-sonnet-4"
    pub llm_api_key_secret: String,        // "llm-credentials"
    pub llm_api_key_secret_key: String,    // "api-key"
    pub service_account_name: String,      // "beeper-investigator"
    // ADD: pub prometheus_url: String,     ← NEW for this story
    // ADD: pub loki_url: String,           ← NEW for this story
    // ... other fields
}
```

### Environment Variables Injected by Operator (Full List After This Story)

| Variable | Source | Required | Default |
|----------|--------|----------|---------|
| `INVESTIGATION_ID` | Investigation CR name | Yes | — |
| `INVESTIGATION_NAMESPACE` | Investigation CR namespace | Yes | — |
| `INVESTIGATION_CONDITION` | InvestigationSpec.condition | Yes | — |
| `INVESTIGATION_SERVICE` | InvestigationSpec.service | Yes | — |
| `INVESTIGATION_SEVERITY` | InvestigationSpec.severity | Yes | — |
| `BEEPER_LLM_PROVIDER` | InvestigatorConfig | Yes | — |
| `BEEPER_LLM_MODEL` | InvestigatorConfig | Yes | — |
| `BEEPER_LLM_API_KEY` | K8s Secret | Yes* | — |
| `QDRANT_HOST` | InvestigatorConfig | No | "qdrant" |
| `QDRANT_PORT` | InvestigatorConfig | No | "6333" |
| `PROMETHEUS_URL` | InvestigatorConfig | No | "" (not configured) |
| `LOKI_URL` | InvestigatorConfig | No | "" (not configured) |

*Required for cloud LLM providers (Anthropic, OpenAI, Azure). Not needed for Ollama.

### Prometheus/Loki Query API Reference

**Prometheus Instant Query:**
```
GET /api/v1/query?query={promql}&time={timestamp}
Response: { "status": "success", "data": { "resultType": "vector", "result": [...] } }
```

**Prometheus Range Query:**
```
GET /api/v1/query_range?query={promql}&start={start}&end={end}&step={step}
Response: { "status": "success", "data": { "resultType": "matrix", "result": [...] } }
```

**Loki Query:**
```
GET /loki/api/v1/query?query={logql}&limit={limit}&time={timestamp}
Response: { "status": "success", "data": { "resultType": "streams", "result": [...] } }
```

**Loki Range Query:**
```
GET /loki/api/v1/query_range?query={logql}&start={start_ns}&end={end_ns}&limit={limit}
Response: { "status": "success", "data": { "resultType": "streams", "result": [...] } }
```

### K8s Custom Resource Status Update Pattern

```python
from kubernetes import client, config

# In-cluster config (uses ServiceAccount token)
config.load_incluster_config()

# Create custom objects API
api = client.CustomObjectsApi()

# PATCH Investigation CR status subresource
api.patch_namespaced_custom_object_status(
    group="beeper.dev",
    version="v1",
    namespace=namespace,
    plural="investigations",
    name=investigation_id,
    body={"status": {"message": "Correlating signals..."}},
)
```

### Investigation Result Persistence

When the investigation completes, persist results to Qdrant `investigations` collection:

```python
from beeper_investigator.kb.schemas import InvestigationEntry
from qdrant_client.models import PointStruct
import uuid

point = PointStruct(
    id=str(uuid.uuid4()),
    vector=[0.0] * 384,  # Placeholder vector (embedding happens in future stories)
    payload={
        "investigation_id": context.investigation_id,
        "service": context.service,
        "condition": context.condition,
        "severity": context.severity,
        "status": "resolved" if result.success else "failed",
        "summary": result.summary,
        "findings": result.findings,
        "created_at": datetime.utcnow().isoformat() + "Z",
    },
)
kb_client.upsert("investigations", [point])
```

### RBAC Changes

The investigator ServiceAccount (`beeper-investigator`) currently has:
- `secrets`: get, list
- `configmaps`: get, list

**Add for this story:**
- `investigations.beeper.dev`: get, patch
- `investigations.beeper.dev/status`: get, patch, update

### Testing Strategy

**Python Tests:** Run with `cd investigator && poetry run pytest`
- Mock K8s API with `unittest.mock.patch` (do NOT require a real cluster)
- Mock HTTP with `respx` or `httpx.MockTransport` for source client tests
- Mock LlmClient and KBClient for agent lifecycle tests

**Rust Tests:** Run with `cd operator && cargo test`
- Test new InvestigatorConfig fields and env var loading
- Test Job builder includes PROMETHEUS_URL and LOKI_URL env vars
- All existing 157 tests must continue passing

**Test Commands:**
```bash
cd investigator && poetry run pytest              # All Python tests
cd investigator && poetry run pytest tests/ -v    # Verbose
cd operator && cargo test                         # All Rust tests
cd operator && cargo clippy -- -D warnings        # Clippy clean
```

### Previous Story Learnings

**From Story 3-1 (Anomaly Detection Engine) — Code Review:**
- Guard against NaN/Infinity inputs at system boundaries
- Use finite values for deviation magnitudes (not f64::INFINITY) to prevent JSON serialization issues
- Record cooldown/backoff BEFORE making external API calls to prevent flood on persistent failures
- Sorted insert for time-windowed data (partition_point) to handle out-of-order timestamps
- Include `app` label in service extraction chains (common Kubernetes label)
- Check-before-update pattern when measuring deviation against historical statistics

**From Story 1-9 (Investigation CRD Pod Spawning):**
- `INVESTIGATION_NAMESPACE` must be explicitly passed (not assumed from operator namespace)
- ServiceAccount must be set on PodSpec for RBAC to work
- Qdrant env vars are `QDRANT_HOST`/`QDRANT_PORT` (NOT `BEEPER_QDRANT_URL`)

**From Story 1-8 (LLM Provider Configuration):**
- LiteLLM is the LLM client abstraction (do NOT use raw anthropic/openai SDKs)
- `LlmClient.from_env()` reads `BEEPER_LLM_PROVIDER`, `BEEPER_LLM_MODEL`, `BEEPER_LLM_API_KEY`
- Multi-provider support: anthropic, openai, azure, ollama

### Project Structure Notes

**New files to create:**
```
investigator/beeper_investigator/
├── context.py                  # InvestigationContext dataclass
├── agent.py                    # InvestigatorAgent lifecycle framework
├── k8s/
│   ├── __init__.py
│   └── status.py               # InvestigationStatusUpdater
├── sources/
│   ├── __init__.py
│   ├── prometheus.py           # PrometheusClient
│   └── loki.py                 # LokiClient
```

**Files to modify:**
```
investigator/
├── beeper_investigator/
│   └── main.py                 # Wire agent into entry point
├── pyproject.toml              # Add kubernetes dependency
├── tests/
│   ├── test_context.py         # NEW: Context tests
│   ├── test_agent.py           # NEW: Agent lifecycle tests
│   ├── test_k8s_status.py      # NEW: Status updater tests
│   ├── test_sources.py         # NEW: Source client tests
│   └── test_main.py            # UPDATE: Integration tests

operator/src/
├── crds/investigation.rs       # Add message field to InvestigationStatus
├── investigator_job.rs         # Add source URL env vars

helm/beeper/templates/
├── crds/investigation-crd.yaml # Add message to status schema
├── investigator-rbac.yaml      # Add Investigation CR permissions
```

### References

- [Source: architecture.md#Investigation Engine Architecture - Data pipeline and investigator role]
- [Source: architecture.md#Technology Stack - Python for investigators, LiteLLM for LLM]
- [Source: architecture.md#API Patterns - RFC 7807, endpoint naming, K8s Job pattern]
- [Source: architecture.md#Component Boundaries - Operator spawns Job, investigator reads CRDs]
- [Source: architecture.md#Security - RBAC, ServiceAccount, K8s Secrets for API keys]
- [Source: epics.md#Story 3.2 - Acceptance criteria, investigator initialization]
- [Source: epics.md#Epic 3 - Full investigation engine context, downstream stories 3.3-3.8]
- [Source: 3-1-anomaly-detection-engine.md - Previous story learnings, review findings]
- [Source: 1-9-investigation-crd-pod-spawning.md - Investigation CRD, Job builder, RBAC patterns]
- [Source: 1-8-llm-provider-configuration.md - LlmClient API, LiteLLM integration patterns]

---

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

None — clean implementation, no debugging required.

### Completion Notes List

- **Task 1:** Created `context.py` with frozen `InvestigationContext` dataclass and `from_env()` factory. Required fields (investigation_id, namespace) exit on missing; optional fields (condition, service, severity) have sensible defaults.
- **Task 2:** Added `message: Option<String>` to Rust `InvestigationStatus`, updated CRD YAML, created Python `InvestigationStatusUpdater` that PATCHes Investigation CR status subresource. Only writes `message` field — `phase` lifecycle owned by controller. Added `kubernetes ^29.0` dependency. Updated RBAC with `investigations.beeper.dev` get/patch permissions.
- **Task 3:** Created `PrometheusClient` and `LokiClient` with query/query_range methods using httpx MockTransport for testing. Optional basic auth via base64-encoded env vars. Added `prometheus_url`/`loki_url` to Rust `InvestigatorConfig` (defaults empty) and injected as Job env vars.
- **Task 4:** Created `InvestigatorAgent` with initialize → run_steps → finalize lifecycle. Placeholder `_run_steps()` returns success. `_finalize()` persists results to Qdrant and updates Investigation CR status. Full try/except wrapping in `run()`.
- **Task 5:** Replaced TODO block in `main.py` with full agent wiring. Builds `InvestigationContext`, creates all clients (KB, LLM, optional sources, K8s status updater), instantiates and runs agent. Cleanup in finally block closes all clients.
- **Task 6:** 37 Python tests (6 context, 5 K8s status, 8 sources, 8 agent, 10 main) + 3 new Rust tests (config defaults, source URL env vars, empty defaults). Total: 160 Rust tests, 37 new Python tests.

### Change Log

- 2026-02-19: Story 3-2 implemented — investigator agent scaffold with context, K8s status updater, source clients, agent lifecycle, main.py wiring, and comprehensive tests
- 2026-02-20: Code review fixes — (1) _persist_result returns success flag, status warns on persistence failure; (2) InvestigatorConfig.from_env() reads BEEPER_PROMETHEUS_URL/BEEPER_LOKI_URL, operator main.rs now uses it; (3) Simplified redundant base64 re-encode in source auth; (4) Status updater returns bool; (5) Added auth tests for source clients, persist failure test for agent; (6) +6 Python tests, +2 Rust tests

### Senior Developer Review (AI)

**Reviewer:** eric on 2026-02-20
**Outcome:** Changes Requested → Fixed

**Findings (7 total: 1 HIGH, 4 MEDIUM, 2 LOW):**

1. **HIGH — Silent data loss on Qdrant persist failure** (`agent.py:165-169`): `_persist_result` failure was silently swallowed; agent reported success even when results weren't stored. **FIXED:** `_persist_result` now returns bool; `_finalize` appends WARNING to status message on failure.

2. **MEDIUM — InvestigatorConfig env var loading missing** (Task 3.7): Fields added but `BEEPER_PROMETHEUS_URL`/`BEEPER_LOKI_URL` never read from env. Operator always used `Default::default()`. **FIXED:** Added `InvestigatorConfig::from_env()`; `main.rs` now uses `run_investigation_controller_with_config`.

3. **MEDIUM — No tests for source client basic auth** (Task 3.5): Auth code existed but was completely untested. **FIXED:** Added 4 auth tests (valid + invalid for both Prometheus and Loki).

4. **MEDIUM — Redundant base64 decode+re-encode in auth** (`prometheus.py`, `loki.py`): Decoded base64, split user:pass, re-encoded identically. **FIXED:** Simplified to decode-validate-use-original.

5. **MEDIUM — Status updater errors silently swallowed** (`k8s/status.py`): K8s API errors logged but not signaled to callers. **FIXED:** `update_message` now returns bool for optional caller inspection.

6. **LOW — Source client tests bypass `__init__`** (`test_sources.py`): Used `__new__` pattern. Noted but not changed (existing tests still valid).

7. **LOW — No test for persist failure path**: **FIXED:** Added `test_persist_failure_warns_in_status`.

### File List

**New files:**
- investigator/beeper_investigator/context.py
- investigator/beeper_investigator/agent.py
- investigator/beeper_investigator/k8s/__init__.py
- investigator/beeper_investigator/k8s/status.py
- investigator/beeper_investigator/sources/__init__.py
- investigator/beeper_investigator/sources/prometheus.py
- investigator/beeper_investigator/sources/loki.py
- investigator/tests/test_context.py
- investigator/tests/test_agent.py
- investigator/tests/test_k8s_status.py
- investigator/tests/test_sources.py

**Modified files:**
- investigator/beeper_investigator/main.py
- investigator/pyproject.toml
- investigator/tests/test_main.py
- operator/src/crds/investigation.rs
- operator/src/investigator_job.rs
- operator/src/lib.rs
- operator/src/main.rs
- helm/beeper/templates/crds/investigation-crd.yaml
- helm/beeper/templates/investigator-rbac.yaml
- _bmad-output/implementation-artifacts/sprint-status.yaml
