# Beeper Source Tree Analysis

**Project:** Beeper — Open-Source Agentic AI SRE Platform
**Version:** 0.1.0
**Repository type:** Monorepo (Rust operator + Python investigator + Python/Flask UI + Helm chart)

---

## Table of Contents

1. [Repository Overview](#repository-overview)
2. [Annotated Directory Tree](#annotated-directory-tree)
3. [Critical Folders Explained](#critical-folders-explained)
   - [operator/](#operator-rust-kubernetes-operator)
   - [investigator/](#investigator-python-ai-agent)
   - [ui/](#ui-pythonflask-dashboard)
   - [helm/](#helm-kubernetes-deployment)
   - [.github/](#github-cicd-pipelines)
   - [scripts/](#scripts-developer-tooling)
4. [Entry Points](#entry-points)
5. [Key Patterns and Protocols](#key-patterns-and-protocols)
   - [InvestigationStep Protocol](#investigationstep-protocol)
   - [SSE Streaming](#sse-streaming)
   - [Investigation Lifecycle State Machine](#investigation-lifecycle-state-machine)
   - [Detection Pipeline](#detection-pipeline)
   - [LLM Tiered Model Selection](#llm-tiered-model-selection)
   - [Ingestion Buffer and Backpressure](#ingestion-buffer-and-backpressure)
6. [Cross-Component Data Flow](#cross-component-data-flow)
7. [Test Coverage Map](#test-coverage-map)

---

## Repository Overview

Beeper is structured as a monorepo with four independently-buildable sub-projects plus shared Helm and script tooling. Each sub-project has its own language, build system, and Dockerfile.

| Sub-project | Language | Build | Purpose |
|---|---|---|---|
| `operator/` | Rust | Cargo | Kubernetes controller + ingestion endpoints + anomaly detection |
| `investigator/` | Python 3.11 | Poetry | AI agent that runs as a K8s Job to investigate anomalies |
| `ui/` | Python 3.11 / Flask | Poetry | Web dashboard for SREs |
| `helm/` | YAML | Helm 3 | Kubernetes deployment manifests |

---

## Annotated Directory Tree

```
beeper/
│
├── .github/
│   └── workflows/
│       ├── ci.yml           # CI matrix: Rust (fmt+clippy+test), Python investigator
│       │                    # (ruff+pytest), Python UI (ruff+pytest), Helm lint
│       └── release.yml      # Builds and pushes Docker images to ghcr.io on tag
│
├── helm/
│   └── beeper/
│       ├── Chart.yaml       # chart name=beeper, version=0.1.0, appVersion=0.1.0
│       ├── README.md
│       ├── values.yaml      # Default values (image tags, replicas, resource limits)
│       ├── values-dev.yaml  # Development overrides (lower resource requests, debug flags)
│       ├── examples/
│       │   └── llm-secret.yaml          # Example Secret for LLM API key
│       └── templates/
│           ├── _helpers.tpl             # Helm label/name helpers
│           ├── crds/
│           │   ├── investigation-crd.yaml  # Investigation CustomResourceDefinition
│           │   └── source-crd.yaml         # Source CustomResourceDefinition
│           ├── investigator-rbac.yaml      # ServiceAccount + Role + RoleBinding for
│           │                               # investigator pods (read pods/secrets, patch
│           │                               # Investigation status)
│           ├── operator-deployment.yaml    # Operator Deployment (1 replica, leader election)
│           ├── operator-role.yaml          # ClusterRole: watch/create/patch Investigations,
│           │                               # Jobs, Sources
│           ├── operator-rolebinding.yaml   # ClusterRoleBinding for operator ServiceAccount
│           ├── operator-serviceaccount.yaml
│           ├── qdrant-service.yaml         # ClusterIP Service for Qdrant (port 6333)
│           ├── qdrant-statefulset.yaml     # Qdrant StatefulSet with persistent volume
│           └── ui-deployment.yaml          # UI Deployment + Service
│
├── investigator/
│   ├── .env.example         # Required env vars for local development
│   ├── Dockerfile           # Multi-stage build: poetry install → slim runtime image
│   ├── README.md
│   ├── pyproject.toml       # Poetry config: python ^3.11, dependencies include
│   │                        # litellm, qdrant-client, kubernetes, pydantic
│   ├── poetry.lock
│   ├── beeper_investigator/ # Main package
│   │   ├── __init__.py
│   │   ├── main.py          # ENTRY POINT: K8s Job entrypoint; reads env, wires
│   │   │                    # clients, runs InvestigatorAgent
│   │   ├── agent.py         # InvestigatorAgent: _initialize → _build_steps →
│   │   │                    # _run_steps → _finalize lifecycle framework
│   │   ├── context.py       # InvestigationContext: structured env-var parsing
│   │   │                    # (service, condition, severity, investigation_id)
│   │   ├── k8s/
│   │   │   ├── __init__.py
│   │   │   └── status.py    # InvestigationStatusUpdater: patches Investigation CR
│   │   │                    # .status.message in-flight via kubernetes-client
│   │   ├── kb/
│   │   │   ├── __init__.py
│   │   │   ├── client.py    # KBClient: Qdrant wrapper managing two collections
│   │   │   │                # (kb_entries + investigations)
│   │   │   └── schemas.py   # Pydantic models: KBEntry, Investigation (Qdrant payloads)
│   │   ├── llm/
│   │   │   ├── __init__.py
│   │   │   ├── cache.py     # SHA-256 keyed in-memory LRU response cache with TTL
│   │   │   ├── client.py    # LlmClient: LiteLLM wrapper with tiered model selection
│   │   │   │                # (screening / standard / deep_rca), sync + async complete,
│   │   │   │                # embed_sync, cost tracking, response caching
│   │   │   ├── cost.py      # CostTracker: per-model token cost accumulator
│   │   │   └── spending_cap.py  # SpendingCapEnforcer: budget + rate-limit guards
│   │   │                        # checked before each investigation starts
│   │   ├── sources/
│   │   │   ├── __init__.py
│   │   │   ├── loki.py      # LokiClient: HTTP wrapper for LogQL queries
│   │   │   └── prometheus.py  # PrometheusClient: HTTP wrapper for PromQL queries
│   │   └── steps/
│   │       ├── __init__.py  # PROTOCOL DEFINITION: InvestigationStep protocol +
│   │       │                # StepResult dataclass (see Key Patterns section)
│   │       ├── impact_assessment.py          # Step 1: CustomerImpactStep
│   │       ├── kb_query.py                   # Step 2: KBQueryStep
│   │       ├── signal_correlation.py         # Step 3: SignalCorrelationStep
│   │       ├── rca_hypothesis.py             # Step 4: RCAHypothesisStep
│   │       ├── resolution_recommendations.py # Step 5: ResolutionRecommendationStep
│   │       └── investigation_documentation.py  # Step 6: InvestigationDocumentationStep
│   └── tests/
│       ├── __init__.py
│       ├── test_agent.py
│       ├── test_context.py
│       ├── test_impact_assessment.py
│       ├── test_investigation_documentation.py
│       ├── test_k8s_status.py
│       ├── test_kb_client.py
│       ├── test_kb_query.py
│       ├── test_llm_cache.py
│       ├── test_llm_client.py
│       ├── test_llm_embedding.py
│       ├── test_llm_screening.py
│       ├── test_main.py
│       ├── test_rca_hypothesis.py
│       ├── test_resolution_recommendations.py
│       ├── test_signal_correlation.py
│       ├── test_sources.py
│       ├── test_spending_caps.py
│       └── test_step_pipeline.py
│
├── openapi/
│   └── beeper-api.yaml      # OpenAPI 3.1 specification for the operator REST API
│                            # (used to generate typed clients via scripts/)
│
├── operator/
│   ├── Cargo.toml           # Dependencies: kube-rs 0.95, axum 0.7, tokio 1 (full),
│   │                        # serde, tracing, reqwest, prost, snap (snappy codec)
│   ├── Dockerfile           # Multi-stage: cargo build --release → distroless runtime
│   └── src/
│       ├── main.rs          # ENTRY POINT: tokio::main; wires all subsystems,
│       │                    # spawns background tasks, handles SIGTERM/SIGINT
│       ├── lib.rs           # Library crate root; re-exports all public types
│       ├── api.rs           # axum REST API for UI: GET /investigations,
│       │                    # GET /investigations/{id}, GET /sources, GET /spending,
│       │                    # POST /investigations/{id}/confirm, etc.
│       ├── health.rs        # GET /healthz (liveness) + GET /readyz (readiness)
│       ├── investigator_job.rs  # build_investigator_job(): constructs K8s Job spec
│       │                        # with env vars from InvestigatorConfig; phase
│       │                        # transition helpers (set_phase_pending/running/
│       │                        # completed/failed) patch Investigation .status
│       ├── llm.rs           # LlmManager: reads LLM provider config from K8s Secrets
│       ├── controllers/
│       │   ├── mod.rs
│       │   ├── investigation.rs  # kube-runtime Controller for Investigation CRD;
│       │   │                     # reconcile() manages Pending→Running→Completed/Failed
│       │   │                     # state machine; watches Jobs for completion
│       │   └── source.rs         # kube-runtime Controller for Source CRD;
│       │                         # reconciles connectivity + status reporting
│       ├── crds/
│       │   ├── mod.rs
│       │   ├── investigation.rs  # Investigation struct (CustomResource derive);
│       │   │                     # InvestigationSpec, InvestigationStatus,
│       │   │                     # InvestigationPhase enum, Severity enum
│       │   └── source.rs         # Source struct; SourceSpec, SourceStatus
│       ├── detection/
│       │   ├── mod.rs            # DetectionConfig (from env), DetectionStats
│       │   ├── consumer.rs       # DetectionConsumer: reads IngestionBuffer in a loop,
│       │   │                     # routes to metric/log detectors, creates Investigation
│       │   │                     # CRDs on anomaly; CooldownTracker prevents alert storms
│       │   ├── ewma.rs           # EwmaDetector: exponentially weighted moving average
│       │   │                     # with adaptive baseline; fires AnomalySignal when
│       │   │                     # value deviates > threshold stddevs; NaN-safe
│       │   ├── logs.rs           # LogDetector: pattern-based log anomaly detection
│       │   ├── metrics.rs        # MetricDetector: per-metric EWMA detector pool
│       │   └── types.rs          # AnomalySignal, AnomalyEvent type definitions
│       ├── ingestion/
│       │   ├── mod.rs
│       │   ├── buffer.rs         # IngestionBuffer: bounded tokio mpsc channel
│       │   │                     # (default 10,000 capacity) with backpressure;
│       │   │                     # tracks buffered_count and dropped_count atomically
│       │   ├── loki.rs           # POST /loki/api/v1/push endpoint (Loki push protocol)
│       │   └── prometheus.rs     # POST /api/v1/write endpoint (Prometheus remote write
│       │                         # with snappy + protobuf decoding)
│       └── sources/
│           ├── mod.rs
│           ├── loki.rs           # LokiClient: operator-side query client for Loki
│           └── prometheus.rs     # PrometheusClient: operator-side query client for Prometheus
│
├── scripts/
│   ├── demo.sh              # End-to-end demo orchestration
│   ├── generate-clients.sh  # Runs openapi-generator against openapi/beeper-api.yaml
│   ├── init-collections.py  # Creates Qdrant collections (kb_entries, investigations)
│   │                        # with correct vector dimensions
│   ├── local-testing.sh     # Runs full local test suite across all sub-projects
│   ├── seed-kb.sh           # Orchestrates KB seeding: init-collections + seed_kb
│   ├── seed_kb.py           # Inserts sample KB entries (runbooks, incident records)
│   │                        # into Qdrant for development and demo purposes
│   └── setup-dev.sh         # Developer bootstrap: installs toolchains, Poetry envs,
│                            # starts Docker Compose (Qdrant), creates .env files
│
├── ui/
│   ├── .env.example
│   ├── Dockerfile           # Multi-stage: poetry install → slim runtime image
│   ├── README.md
│   ├── pyproject.toml       # Poetry config: python ^3.11, Flask ^3.0, htmx-flask,
│   │                        # qdrant-client, mistune (markdown), bleach (XSS sanitize)
│   ├── poetry.lock
│   ├── beeper_ui/
│   │   ├── __init__.py
│   │   ├── app.py           # ENTRY POINT: Flask app factory create_app(); registers
│   │   │                    # blueprints, Jinja2 filters, markdown filter
│   │   ├── config.py        # Config classes (Development/Production); reads OPERATOR_URL,
│   │   │                    # QDRANT_HOST, SECRET_KEY, etc. from env
│   │   ├── routes/
│   │   │   ├── __init__.py  # register_blueprints(): mounts all route blueprints
│   │   │   ├── health.py    # GET /health — UI health check
│   │   │   ├── investigations.py  # Blueprint /investigations: list, detail, SSE stream,
│   │   │   │                      # confirm/reject resolution, resolve investigation;
│   │   │   │                      # HTMX-aware (returns partials for HX-Request headers)
│   │   │   ├── knowledge.py       # Blueprint /knowledge: KB wiki CRUD interface
│   │   │   ├── metrics.py         # Blueprint /metrics: MTTR trends dashboard
│   │   │   ├── sources.py         # Blueprint /sources: Source status views
│   │   │   └── spending.py        # Blueprint /spending: LLM cost visibility dashboard
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── correction_service.py   # Conversational correction processing
│   │   │   ├── embedding_service.py    # Embedding generation for KB search
│   │   │   ├── health_service.py       # Operator + Qdrant connectivity checks
│   │   │   ├── import_service.py       # Runbook import (markdown → KB entry)
│   │   │   ├── investigation_service.py  # HTTP client for operator REST API;
│   │   │   │                             # list_investigations, get_investigation,
│   │   │   │                             # confirm_resolution, save_resolution_feedback,
│   │   │   │                             # calculate_mttr
│   │   │   ├── kb_service.py           # Qdrant CRUD for KB entries: list, get, create,
│   │   │   │                           # update, delete, search (vector similarity),
│   │   │   │                           # list_entries_by_service
│   │   │   ├── learning_service.py     # Diff-based learning: extracts deltas from SRE
│   │   │   │                           # corrections to improve future investigations
│   │   │   ├── metrics_service.py      # MTTR aggregation queries against Qdrant
│   │   │   ├── source_service.py       # Fetches Source status from operator API
│   │   │   └── spending_service.py     # Fetches LLM cost data from operator API
│   │   └── utils/
│   │       ├── __init__.py
│   │       └── markdown_utils.py  # Markdown rendering (mistune) with bleach XSS
│   │                              # sanitization; registered as Jinja2 filter
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_app.py
│       ├── test_corrections.py
│       ├── test_cost_insights.py
│       ├── test_embedding_service.py
│       ├── test_import_service.py
│       ├── test_investigation_routes.py
│       ├── test_investigation_service.py
│       ├── test_kb_routes.py
│       ├── test_kb_service.py
│       ├── test_learning.py
│       ├── test_markdown.py
│       ├── test_metrics.py
│       ├── test_routes.py
│       ├── test_services.py
│       ├── test_spending.py
│       └── test_trust.py
│
├── CONTRIBUTING.md
├── LICENSE                  # Apache 2.0
├── README.md
├── VISION.md
├── docker-compose.yaml      # Local development: Qdrant only (operator/investigator
│                            # run natively or in-cluster)
└── .gitignore
```

---

## Critical Folders Explained

### `operator/` — Rust Kubernetes Operator

The operator is the control plane of Beeper. It is a single binary that runs multiple concurrent subsystems, all wired in `main.rs` and spawned as independent Tokio tasks:

**Subsystems started by `main.rs`:**

| Tokio task | Port | Purpose |
|---|---|---|
| Health/API server | `BEEPER_HEALTH_PORT` (default 8080) | `/healthz`, `/readyz`, and the full UI REST API |
| Ingestion server | `BEEPER_INGESTION_PORT` (default 9090) | Prometheus remote write + Loki push endpoints |
| Source controller | — | kube-runtime controller for `Source` CRDs |
| Investigation controller | — | kube-runtime controller for `Investigation` CRDs |
| Detection consumer | — | Reads ingestion buffer, runs anomaly detection, creates Investigation CRDs |

**`operator/src/crds/`** — The CRD type definitions are central to everything. `investigation.rs` defines `InvestigationPhase` (`Pending`, `Running`, `Completed`, `Failed`) and `Severity` (`Low`, `Medium`, `High`, `Critical`). These Rust types are derived into the YAML CRDs in `helm/beeper/templates/crds/`.

**`operator/src/detection/`** — The anomaly detection engine. The `EwmaDetector` in `ewma.rs` implements a stateful exponentially weighted moving average (alpha=0.2, threshold=3.0 stddevs by default, min 10 samples warmup). The `DetectionConsumer` in `consumer.rs` reads `IngestionData` from the shared `IngestionBuffer`, routes it to `MetricDetector` (a pool of per-metric `EwmaDetector` instances) or `LogDetector`, and creates `Investigation` CRDs via the Kubernetes API when an anomaly fires. A `CooldownTracker` prevents repeated Investigation creation for the same anomaly signature.

**`operator/src/ingestion/`** — Data ingress layer. `prometheus.rs` accepts Prometheus remote write (snappy-compressed protobuf); `loki.rs` accepts the Loki push API. Both decode their formats and call `IngestionBuffer::try_send()`. The buffer is a bounded `tokio::sync::mpsc` channel with atomic drop counters for backpressure visibility.

**`operator/src/investigator_job.rs`** — The job builder. `build_investigator_job()` constructs a complete `k8s_openapi::api::batch::v1::Job` spec, populating all environment variables the investigator process expects (`INVESTIGATION_ID`, `INVESTIGATION_NAMESPACE`, `BEEPER_LLM_PROVIDER`, `BEEPER_LLM_MODEL`, `BEEPER_LLM_API_KEY` from a Secret reference, `QDRANT_HOST`, `QDRANT_PORT`, `PROMETHEUS_URL`, `LOKI_URL`). The `InvestigatorConfig` struct drives all tunables (image, resource limits, TTL, backoff).

---

### `investigator/` — Python AI Agent

Each investigation runs as an ephemeral Kubernetes Job. The investigator is a single-execution Python process; it does not serve HTTP traffic.

**`beeper_investigator/main.py`** — Wires all clients from environment variables, constructs `InvestigatorAgent`, calls `agent.run()`, and exits with code 0 (success) or 1 (failure). Uses a `JsonFormatter` for structured logging that includes `investigation_id` in every line.

**`beeper_investigator/agent.py`** — The `InvestigatorAgent` class owns the investigation lifecycle: `_initialize()` validates KB and LLM connectivity and enforces spending caps; `_build_steps()` lazily constructs the ordered pipeline; `_run_steps()` executes steps sequentially (non-fatal — a failing step is logged but does not abort the pipeline); `_finalize()` persists the result to Qdrant and patches the Investigation CR status. The `_pipeline_metadata` dict is passed by reference to later steps so they can read prior step outputs.

**`beeper_investigator/steps/`** — The investigation pipeline. Each step module contains a class that satisfies the `InvestigationStep` protocol (see Key Patterns). The canonical order is:

1. `CustomerImpactStep` — LLM-driven customer impact assessment
2. `KBQueryStep` — Vector similarity search of prior KB entries
3. `SignalCorrelationStep` — Cross-layer correlation of Prometheus + Loki signals
4. `RCAHypothesisStep` — Root cause hypothesis using `deep_rca` model tier
5. `ResolutionRecommendationStep` — Actionable remediation steps
6. `InvestigationDocumentationStep` — Writes findings back to Qdrant KB

**`beeper_investigator/llm/`** — The LLM subsystem. `LlmClient` wraps LiteLLM and supports Anthropic, OpenAI, Azure, and Ollama. Three model tiers are selectable via `select_model(tier)`: `screening` (fast/cheap), `standard` (default), `deep_rca` (most capable). All deterministic calls (temperature=0.0) are checked against a SHA-256-keyed in-memory LRU cache before hitting the API. `CostTracker` accumulates per-model token costs; `SpendingCapEnforcer` gates investigation start against a configured budget and rate limit.

**`beeper_investigator/kb/`** — Qdrant integration. `KBClient` manages two collections: `kb_entries` (runbooks, incident records, SRE knowledge) and `investigations` (completed investigation results for future lookup). `schemas.py` contains Pydantic models matching the Qdrant payload schemas.

**`beeper_investigator/sources/`** — Thin HTTP client wrappers for querying Prometheus (PromQL) and Loki (LogQL) during signal correlation. Both are optional; the investigator runs without them if the URLs are not configured.

---

### `ui/` — Python/Flask Dashboard

The UI is a server-rendered Flask application with HTMX for partial page updates and SSE for real-time streaming. It never has direct database access to the Kubernetes API — all investigation data comes through the operator REST API. KB data is fetched directly from Qdrant.

**`beeper_ui/app.py`** — The Flask application factory `create_app()`. Registers blueprints from `routes/`, sets up the Jinja2 markdown filter, and registers template globals (`OUTCOME_LABELS`, `ACCURACY_LABELS`).

**`beeper_ui/routes/investigations.py`** — The largest and most complex route module. Contains:
- `list_investigations()` — HTMX-aware list view with status/service/severity/date filtering
- `investigation_detail()` — Detail pane with pipeline step timeline
- `investigation_detail_stream()` — SSE endpoint for real-time investigation progress (see Key Patterns)
- `investigation_stream()` — SSE endpoint for real-time investigation list updates
- `confirm_resolution()` / `reject_resolution()` — SRE feedback collection
- `resolve_investigation_route()` — Final resolution with MTTR calculation and KB update
- `_get_step_states()` — Maps current status message to pipeline step timeline states

**`beeper_ui/services/`** — Service layer decouples routes from data access:
- `InvestigationService` — HTTP client for the operator REST API
- `KBService` — Qdrant CRUD and vector search for KB entries
- `LearningService` — Extracts diffs from SRE corrections
- `MetricsService` — MTTR aggregation
- `SpendingService` — LLM cost summaries

**`beeper_ui/utils/markdown_utils.py`** — Renders Markdown to HTML via `mistune` and sanitizes with `bleach` to prevent XSS. Registered as the `markdown` Jinja2 filter used throughout templates.

---

### `helm/` — Kubernetes Deployment

The Helm chart (`helm/beeper/`) deploys the complete Beeper stack into a Kubernetes cluster.

**`templates/crds/`** — The `Investigation` and `Source` CRDs. These must be installed before the operator starts. The operator will fail to start if CRDs are absent.

**`templates/investigator-rbac.yaml`** — Creates the `beeper-investigator` ServiceAccount and gives it exactly the permissions investigator pods need: read `Pods` and `Secrets`, and patch `Investigation` status. This is set on every Job pod via `InvestigatorConfig.service_account_name`.

**`values.yaml` vs `values-dev.yaml`** — `values-dev.yaml` overrides image pull policy to `Always`, reduces resource requests, and may enable additional debug logging. Use `helm install beeper ./helm/beeper -f helm/beeper/values-dev.yaml` for local cluster testing.

---

### `.github/` — CI/CD Pipelines

**`ci.yml`** — Runs on every push and pull request to `main`. Three parallel jobs:
- `rust`: `cargo fmt --check`, `cargo clippy -- -D warnings`, `cargo test`
- `python-investigator`: `ruff check`, `pytest` (working directory `investigator/`)
- `python-ui`: `ruff check`, `pytest` (working directory `ui/`)
- `helm`: `helm lint ./helm/beeper`

**`release.yml`** — Triggered on version tags. Builds Docker images for `operator`, `investigator`, and `ui` and pushes to `ghcr.io`.

---

### `scripts/` — Developer Tooling

| Script | Purpose |
|---|---|
| `setup-dev.sh` | One-shot developer bootstrap: installs Rust, Poetry, starts Qdrant via Docker Compose |
| `local-testing.sh` | Runs all test suites (Rust + both Python) in sequence |
| `init-collections.py` | Creates required Qdrant collections with correct vector dimensions before first use |
| `seed-kb.sh` | Calls `init-collections.py` then `seed_kb.py` to populate demo KB data |
| `seed_kb.py` | Inserts realistic sample runbook and incident entries into Qdrant |
| `generate-clients.sh` | Generates typed API clients from `openapi/beeper-api.yaml` |
| `demo.sh` | End-to-end demonstration orchestration |

---

## Entry Points

### Operator (Rust)

**File:** `/Users/ethompsy/Projects/beeper/operator/src/main.rs`
**Function:** `async fn main() -> anyhow::Result<()>`
**How started:** `cargo run` (development) or the container entrypoint (production)

The operator reads three environment variables at startup:
- `BEEPER_HEALTH_PORT` (default 8080) — health + API server port
- `BEEPER_INGESTION_PORT` (default 9090) — Prometheus/Loki ingestion port
- `BEEPER_INGESTION_BUFFER_SIZE` (default 10,000) — ingestion buffer capacity

All five subsystems are spawned as `tokio::spawn` tasks. The process then waits for `SIGTERM` or `SIGINT` and aborts all tasks cleanly.

### Investigator (Python)

**File:** `/Users/ethompsy/Projects/beeper/investigator/beeper_investigator/main.py`
**Function:** `def main() -> None`
**Invoked as:** `poetry run python -m beeper_investigator.main` (or via the container entrypoint)
**How started:** Created as a Kubernetes Job by the operator's `build_investigator_job()` function

The investigator is single-execution: it runs one investigation and exits. Required environment variables:
- `INVESTIGATION_ID` — Investigation CR name
- `INVESTIGATION_NAMESPACE` — Kubernetes namespace
- `BEEPER_LLM_PROVIDER` — LLM provider (`anthropic`, `openai`, `azure`, `ollama`)
- `BEEPER_LLM_MODEL` — Model name
- `BEEPER_LLM_API_KEY` — API key (from a K8s Secret)
- `QDRANT_HOST`, `QDRANT_PORT` — Qdrant connection
- `PROMETHEUS_URL`, `LOKI_URL` — Optional source URLs

Exit codes: 0 = success, 1 = failure.

### UI (Python/Flask)

**File:** `/Users/ethompsy/Projects/beeper/ui/beeper_ui/app.py`
**Function:** `create_app(config_class=None) -> Flask`
**How started:** `poetry run flask run` (development) or `gunicorn beeper_ui.app:app` (production)

The module-level `app = create_app()` at the bottom of `app.py` provides compatibility for `flask run` and WSGI servers.

---

## Key Patterns and Protocols

### InvestigationStep Protocol

**Location:** `/Users/ethompsy/Projects/beeper/investigator/beeper_investigator/steps/__init__.py`

```python
@runtime_checkable
class InvestigationStep(Protocol):
    """Protocol for investigation steps."""

    name: str

    def execute(self) -> StepResult:
        """Run the step and return structured result."""
        ...
```

Every investigation step is a class with a `name: str` attribute and an `execute() -> StepResult` method. `StepResult` carries `success: bool`, `summary: str`, `data: dict[str, Any]`, and optional `error: str`. Steps are registered in `InvestigatorAgent._build_steps()` and executed sequentially in `_run_steps()`. Failures are non-fatal: the pipeline continues and the error is logged. Step output data is accumulated into `_pipeline_metadata` (passed by reference), making it available to all subsequent steps.

To add a new investigation step: create a module in `investigator/beeper_investigator/steps/`, implement the `InvestigationStep` protocol, and add an instance to the list in `_build_steps()`. No changes to the agent framework are required.

---

### SSE Streaming

**Location:** `/Users/ethompsy/Projects/beeper/ui/beeper_ui/routes/investigations.py`

The UI uses two SSE endpoints, both backed by generator functions wrapped with Flask's `stream_with_context`:

**Investigation list stream** — `GET /investigations/stream`
Generator: `_generate_sse_events(operator_url, operator_timeout)`
Polls the operator API every 3 seconds. Computes a fingerprint (`id:status` pairs joined by `|`) to detect changes. On change, renders the `investigations/_list_content.html` partial and sends it as an SSE event. Event types: `investigation-update` (status change) or `investigation-new` (new investigation appeared).

**Investigation detail stream** — `GET /investigations/<id>/stream`
Generator: `_generate_detail_sse_events(operator_url, operator_timeout, investigation_id)`
Polls both the operator API (for status message changes) and Qdrant (for new findings keys). Sends multiple event types as the investigation progresses:

| SSE Event | Payload | HTMX Target |
|---|---|---|
| `step-update` | Rendered `_step_progress.html` partial | Step timeline |
| `findings-update` | Rendered `_findings.html` partial | Findings panel |
| `evidence-update` | Rendered `_evidence_panel.html` partial | Evidence panel |
| `kb-update` | Rendered `_related_kb.html` partial | Related KB panel |
| `confirmation-update` | Rendered `_confirmation_form.html` partial | Confirm/reject form |
| `resolution-update` | Rendered `_resolution_form.html` partial | Resolution form |
| `investigation-complete` | `"done"` literal | Stops SSE polling |

SSE response headers:
```
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no   # prevents nginx from buffering the stream
```

The poll interval is 3 seconds (`SSE_POLL_INTERVAL = 3`).

---

### Investigation Lifecycle State Machine

The `InvestigationPhase` enum drives a state machine spanning the operator and investigator:

```
[None / new CR created]
         │
         ▼ (operator sets status)
      Pending
         │
         ▼ (operator creates Job, sets started_at)
      Running  ◄─── Investigator patches .status.message as steps execute
         │
    ┌────┴────┐
    ▼         ▼
Completed   Failed
```

Phase transitions are applied via `patch_status()` in `investigator_job.rs`. The kube-runtime controller in `controllers/investigation.rs` reconciles based on the current phase: if `None` → set `Pending` and requeue; if `Pending` → create Job, set `Running`; watch the Job for completion or failure and update accordingly.

The investigator updates `.status.message` in-flight via `InvestigationStatusUpdater` in `k8s/status.py`, giving the UI real-time progress visibility without waiting for job completion.

---

### Detection Pipeline

```
Prometheus remote write / Loki push
            │
            ▼
      IngestionBuffer (bounded mpsc, 10,000 capacity)
            │
            ▼
     DetectionConsumer (background task)
            │
    ┌───────┴────────┐
    ▼                ▼
MetricDetector   LogDetector
(per-metric       (pattern
 EwmaDetector     matching)
 pool)
    │                │
    └───────┬────────┘
            │ AnomalyEvent
            ▼
    CooldownTracker (suppress duplicates)
            │
            ▼
    kubernetes API: create Investigation CR
```

The `EwmaDetector` in `detection/ewma.rs` uses alpha=0.2 (configurable), a threshold of 3.0 standard deviations, and requires 10 samples before firing. It checks for anomaly against the old mean before incorporating the new value, preventing a spike from inflating the variance it is measured against. Infinite and NaN inputs are silently discarded to prevent detector poisoning.

---

### LLM Tiered Model Selection

**Location:** `/Users/ethompsy/Projects/beeper/investigator/beeper_investigator/llm/client.py`

The `LlmClient.select_model(tier: ModelTier)` method maps task complexity to model capability:

| Tier | Env var | Default fallback | Use case |
|---|---|---|---|
| `screening` | `BEEPER_LLM_SCREENING_MODEL` | Standard model | Quick triage, yes/no classification |
| `standard` | `BEEPER_LLM_MODEL` (required) | — | Most investigation steps |
| `deep_rca` | `BEEPER_LLM_DEEP_RCA_MODEL` | Standard model | Root cause hypothesis generation |

All three tiers fall back to the standard model if the specific tier env var is not set. Provider prefixes (`azure/`, `ollama/`) are applied by `get_litellm_model()` before any LiteLLM call.

The SHA-256 keyed response cache (`llm/cache.py`) deduplicates identical prompts at temperature=0.0. Cache entries are keyed on `(messages, model, max_tokens, temperature)` and expire after `BEEPER_LLM_CACHE_TTL_SECONDS` (default 3600 seconds).

---

### Ingestion Buffer and Backpressure

**Location:** `/Users/ethompsy/Projects/beeper/operator/src/ingestion/buffer.rs`

The `IngestionBuffer` wraps a bounded `tokio::sync::mpsc::channel`. The Prometheus and Loki ingestion handlers call `try_send()` (non-blocking). When the buffer is full:
- `try_send()` returns `Err(data)` — the data point is dropped
- `dropped_count` is atomically incremented
- A `tracing::warn!` log is emitted with the cumulative drop count

The buffer statistics (`buffered_count`, `dropped_count`, `capacity`, `is_full`) are exposed through the operator's REST API and visible in the UI spending/metrics dashboards. The capacity defaults to 10,000 items and is configurable via `BEEPER_INGESTION_BUFFER_SIZE`.

---

## Cross-Component Data Flow

```
External telemetry (Prometheus / Loki)
    │
    │ remote_write / push API (port 9090)
    ▼
Operator: IngestionBuffer
    │
    │ Detection consumer reads buffer
    ▼
Operator: EwmaDetector / LogDetector
    │
    │ kubectl create Investigation CR
    ▼
Kubernetes API
    │
    │ kube-runtime controller watches Investigation
    ▼
Operator: Investigation controller
    │
    │ kubectl create Job (inv-<name>)
    ▼
Kubernetes: Investigator Job Pod
    │
    ├─► Qdrant: KBQueryStep reads kb_entries collection
    ├─► Prometheus HTTP API: SignalCorrelationStep queries PromQL
    ├─► Loki HTTP API: SignalCorrelationStep queries LogQL
    ├─► LLM API (via LiteLLM): multiple steps
    ├─► Kubernetes API: status.message patches (InvestigationStatusUpdater)
    └─► Qdrant: InvestigationDocumentationStep writes to kb_entries + investigations
    │
    │ Job exits 0 or 1
    ▼
Operator: Investigation controller sets phase Completed / Failed
    │
    │ REST API (port 8080)
    ▼
UI: InvestigationService polls operator
    │
    ├─► SSE stream pushes rendered HTML partials to browser (HTMX swap)
    ├─► SRE confirms/rejects/resolves via HTMX POST
    └─► Resolution feedback saved to Qdrant investigations collection
```

---

## Test Coverage Map

| Test file | What it covers |
|---|---|
| `investigator/tests/test_agent.py` | `InvestigatorAgent` lifecycle, step orchestration, error handling |
| `investigator/tests/test_context.py` | `InvestigationContext.from_env()` parsing |
| `investigator/tests/test_impact_assessment.py` | `CustomerImpactStep.execute()` |
| `investigator/tests/test_investigation_documentation.py` | `InvestigationDocumentationStep` KB write |
| `investigator/tests/test_k8s_status.py` | `InvestigationStatusUpdater` CR patching |
| `investigator/tests/test_kb_client.py` | `KBClient` Qdrant operations |
| `investigator/tests/test_kb_query.py` | `KBQueryStep` vector search + exact match |
| `investigator/tests/test_llm_cache.py` | SHA-256 cache hit/miss, TTL, eviction |
| `investigator/tests/test_llm_client.py` | `LlmClient` provider config, completion, error mapping |
| `investigator/tests/test_llm_embedding.py` | `embed_sync()` with embedding model |
| `investigator/tests/test_llm_screening.py` | Tiered model selection |
| `investigator/tests/test_main.py` | End-to-end `main()` with mocked clients |
| `investigator/tests/test_rca_hypothesis.py` | `RCAHypothesisStep` hypothesis generation |
| `investigator/tests/test_resolution_recommendations.py` | `ResolutionRecommendationStep` |
| `investigator/tests/test_signal_correlation.py` | `SignalCorrelationStep` with Prometheus/Loki |
| `investigator/tests/test_sources.py` | `PrometheusClient` + `LokiClient` HTTP queries |
| `investigator/tests/test_spending_caps.py` | `SpendingCapEnforcer` budget + rate limit |
| `investigator/tests/test_step_pipeline.py` | Full six-step pipeline integration |
| `ui/tests/test_app.py` | Flask app factory, blueprint registration |
| `ui/tests/test_corrections.py` | `CorrectionService` conversational corrections |
| `ui/tests/test_cost_insights.py` | Cost visibility data aggregation |
| `ui/tests/test_embedding_service.py` | `EmbeddingService` vector generation |
| `ui/tests/test_import_service.py` | Runbook markdown import |
| `ui/tests/test_investigation_routes.py` | Investigation list, detail, SSE routes |
| `ui/tests/test_investigation_service.py` | `InvestigationService` HTTP client |
| `ui/tests/test_kb_routes.py` | Knowledge base CRUD routes |
| `ui/tests/test_kb_service.py` | `KBService` Qdrant operations |
| `ui/tests/test_learning.py` | `LearningService` diff extraction |
| `ui/tests/test_markdown.py` | Markdown rendering + XSS sanitization |
| `ui/tests/test_metrics.py` | MTTR metrics aggregation |
| `ui/tests/test_routes.py` | Route registration and health endpoints |
| `ui/tests/test_services.py` | Service layer integration |
| `ui/tests/test_spending.py` | Spending dashboard data |
| `ui/tests/test_trust.py` | Trust/feedback loop correctness |

Operator unit tests are co-located as `#[cfg(test)]` modules within each Rust source file. Notable in-file test suites: `ewma.rs` (10 test cases covering spikes, drops, warmup, adaptation, NaN/Inf guards), `buffer.rs` (overflow, batch send, log entries), and `investigator_job.rs` (job spec construction, env var injection, resource limits, missing name/namespace errors).
