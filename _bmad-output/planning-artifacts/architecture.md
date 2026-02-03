---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
inputDocuments:
  - prd.md
  - product-brief-beeper-2026-01-27.md
workflowType: 'architecture'
lastStep: 8
status: 'complete'
completedAt: '2026-02-03'
project_name: 'beeper'
user_name: 'eric'
date: '2026-01-28'
classification:
  projectType: Agentic Platform
  domain: DevOps/SRE
  complexity: high
  projectContext: greenfield
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
- 47 FRs across 6 capability areas defining an agentic SRE platform
- Core loop: Detect anomaly → Spawn investigator → Correlate signals → Document to KB → Human review
- Knowledge Base is both output (investigations) and input (prior knowledge, runbooks)
- Multi-actor system: Beeper (agent), Investigator (spawned), SRE, SRE Lead, Admin

**Non-Functional Requirements:**
- **Performance:** Seconds-level detection latency, real-time UI streaming, sub-second KB search
- **Security:** Self-hosted, read-only access, existing secrets infrastructure, network-only auth for MVP
- **Reliability:** Component independence, KB unavailability buffering, graceful degradation
- **Integration:** Prometheus/Loki MVP, streaming ingestion, K8s-native deployment

**Scale & Complexity:**

| Dimension | Assessment |
|-----------|------------|
| Primary domain | Backend/Platform (K8s operator, data pipelines, LLM orchestration) |
| Complexity level | High - Agentic system with LLM integration |
| Deployment model | K8s operator spawning investigator pods |
| Data flow | Streaming ingestion → Agent processing → KB persistence → UI streaming |
| Estimated components | 6-8 major components (Operator, Investigator, KB, UI, Adapters, LLM Client) |

### Technical Constraints & Dependencies

**Hard Constraints:**
- K8s-only deployment for MVP (daemon model deferred)
- Prometheus/Loki as sole data sources for MVP
- Single LLM provider (Claude API default, configurable)
- Vector-only KB (graph deferred to v1.1)
- No autonomous actions (read-only, observe-and-document)

**Dependencies:**
- Customer's existing K8s cluster
- Customer's Prometheus/Loki stack
- LLM API access (Claude or configured alternative)
- Vector database for KB (technology TBD)

**Team Constraint:**
- 1-2 humans + Claude as development partner
- Aggressive MVP scope required

### Cross-Cutting Concerns Identified

| Concern | Impact |
|---------|--------|
| **Streaming Architecture** | Three distinct patterns: ingestion, internal events, UI updates |
| **LLM Abstraction** | Provider flexibility, tiered model selection, cost tracking |
| **State Management** | Investigation lifecycle, KB versioning, agent coordination |
| **Error Handling** | KB unavailability buffering, LLM failure fallbacks, data source errors |
| **Observability** | Beeper's own health, investigation metrics, cost reporting |
| **Configuration** | CRDs for K8s-native config, source credentials, LLM settings |
| **Testing Infrastructure** | Ground truth data for validating agentic reasoning accuracy |

### Critical Path Analysis

**Knowledge Base is the Hardest Component:**
The KB serves four distinct access patterns simultaneously:
1. Write destination (investigations documenting findings)
2. Read source (investigators querying for prior art)
3. Human interface (wiki for SREs)
4. Learning substrate (corrections feeding back)

Each pattern has different consistency requirements. KB architecture is **critical path**.

**Key Architecture Decisions Needed:**

| Decision | Options | MVP Recommendation |
|----------|---------|-------------------|
| KB consistency model | Eventually consistent / Read-your-writes / Strong | Read-your-writes (investigator sees own writes) |
| UI update mechanism | WebSocket streaming / SSE / Polling | Polling (2-3 sec) acceptable for MVP |
| Streaming infrastructure | Unified / Separate per concern | Decide per concern - may not need unified |
| Investigation lifecycle | What happens on crash? | Define recovery/cleanup strategy |

**Acceptable MVP Trade-offs:**

| Trade-off | Rationale |
|-----------|-----------|
| UI polling instead of true streaming | Validates UX without WebSocket complexity |
| Good-enough semantic search | Perfect relevance not needed to prove value |
| Single operator instance | No horizontal scaling until validated |
| Basic LLM cost tracking | Optimize after shipping |

### Component Risk Assessment

| Component | Risk | Rationale |
|-----------|------|-----------|
| K8s Operator | Medium | Well-understood pattern, good tooling (kubebuilder) |
| LLM Integration | Medium | API abstraction standard, cost is operational risk |
| **Knowledge Base** | **High** | Novel usage pattern, multiple consistency models |
| Prometheus/Loki Adapters | Low | Standard integration, documented APIs |
| Investigation UI | Medium | Real-time adds complexity, but polling de-risks |

## Starter Template Evaluation

### Primary Technology Domain

Backend/Platform with K8s Operator + Agentic Services + Web UI

### Technology Stack Decisions

| Component | Technology | Rationale |
|-----------|------------|-----------|
| K8s Controller | **Rust + kube-rs** | Production-ready, async, memory-safe operators |
| Investigator Agents | **Python** | Rapid development, excellent LLM libraries |
| Vector Database | **Qdrant** | Rust-based, SaaS-scalable, excellent metadata filtering |
| Web UI (MVP) | **Flask + HTMX + SSE** | Simple, live updates, no JS complexity |
| Web UI (v2) | **Django + Dash** | Full-featured, data visualization |
| Infrastructure | **AWS + Terraform + GitHub Actions** | Familiar stack, open-source CI/CD |

### Vector Database Decision

**Why Qdrant over pgvector:**

| Factor | Qdrant | pgvector |
|--------|--------|----------|
| Scale | Horizontal scaling built-in | Breaks down at scale |
| Performance | Purpose-built for vectors | Query planner doesn't understand vectors |
| Filtering | Excellent metadata filtering | Basic SQL WHERE |
| SaaS Ready | Distributed deployment | Requires sharding hacks |
| Language | Rust 🦀 | PostgreSQL extension |

**Migration Path:**
- MVP: Qdrant single node (self-hosted)
- Scale: Qdrant distributed cluster
- Extreme: Evaluate Milvus if billions of vectors

### Frontend Approach

**MVP: HTMX + Server-Sent Events**
- No JavaScript complexity
- SSE for investigation pane streaming
- Flask-native, simple implementation

**v2: Dash or Svelte**
- Dash for data-heavy visualization (Flask-based, pure Python)
- Svelte for more sophisticated frontend

### Initialization Approach

Unlike typical web apps, Beeper uses a polyglot architecture:

```bash
# Rust Controller
cargo new beeper-operator
# Add kube-rs, tokio, serde dependencies

# Python Investigator
poetry new beeper-investigator
# Add anthropic, httpx, pydantic dependencies

# Flask UI
poetry new beeper-ui
# Add flask, htmx dependencies

# Qdrant
# Docker or Helm chart deployment
```

### Architectural Decisions Established by Stack

**Language & Runtime:**
- Rust (stable) for K8s operator - memory safety for long-running controller
- Python 3.11+ for investigators and UI - rapid iteration, LLM ecosystem

**Vector Storage:**
- Qdrant for semantic search and KB storage
- Metadata filtering for structured queries (service, date, severity)
- ACID transactions for KB consistency

**Real-Time Updates:**
- Server-Sent Events (SSE) for investigation pane
- HTMX for dynamic UI without JavaScript complexity
- Polling acceptable fallback (2-3 sec intervals)

**Build & Deployment:**
- Cargo for Rust, Poetry for Python
- Docker multi-stage builds
- Helm charts for K8s deployment
- GitHub Actions for CI/CD

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
- Inter-service communication pattern
- Investigation state storage
- LLM client architecture

**Important Decisions (Shape Architecture):**
- API design patterns
- Deployment topology

**Deferred Decisions (Post-MVP):**
- Authentication/Authorization (MVP is internal network only per NFR-S4)
- Horizontal scaling strategy
- Multi-tenancy for SaaS

### Data Architecture

| Decision | Choice | Version/Details |
|----------|--------|-----------------|
| Vector Database | Qdrant | Latest stable |
| Investigation State | Qdrant (single store) | `investigations` + `knowledge` collections |
| KB Documents | Qdrant | Semantic search + metadata filtering |

**Rationale:** Minimize dependencies for 2-person team. Revisit if Qdrant proves limiting for operational state.

**Collections:**
- `investigations` - operational state (status, progress, in-flight findings)
- `knowledge` - permanent KB (completed investigations, runbooks, corrections)

### Authentication & Security

| Decision | Choice | Rationale |
|----------|--------|-----------|
| MVP Auth | Internal network only | Per NFR-S4, defer authn/authz complexity |
| Secrets | K8s Secrets | Per NFR-S2, use existing infrastructure |
| API Security | Network policies | Restrict inter-service communication |

**Deferred to v1.1:** Role-based access control (admin vs user)

### API & Communication Patterns

| Decision | MVP | Scale Target |
|----------|-----|--------------|
| Inter-service | REST/HTTP + K8s Jobs | NATS JetStream |
| API Specification | OpenAPI 3.1 | Generated clients for Rust + Python |
| Error Format | RFC 7807 Problem Details | Standard `type`, `title`, `status`, `detail` |
| UI Updates | SSE (Server-Sent Events) | NATS subscription (at scale) |

**Communication Flow (MVP):**
```
Operator (Rust) --[K8s Job spawn]--> Investigator (Python)
Investigator --[REST/HTTP]--> Qdrant (KB writes)
Investigator --[REST/HTTP]--> API (status updates)
UI (Flask) --[SSE]--> API (progress streaming)
```

**Communication Flow (Scale):**
```
Operator --[NATS publish]--> investigate.new
Investigator --[NATS subscribe]--> investigate.new
Investigator --[NATS publish]--> investigate.progress.{id}
UI --[NATS subscribe]--> investigate.progress.*
```

### LLM Integration

| Decision | Choice | Rationale |
|----------|--------|-----------|
| LLM Client | LiteLLM | Provider flexibility, streaming, no custom abstraction |
| Default Provider | Anthropic Claude | Per PRD specification |
| Tiered Models | Haiku → Sonnet → Opus | Cost optimization per PRD |

**Model Routing:**
- `screening`: claude-3-haiku (fast, cheap initial assessment)
- `investigation`: claude-sonnet-4 (balanced RCA)
- `deep_rca`: claude-opus-4 (complex multi-layer correlation)

### Infrastructure & Deployment

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Repository | Monorepo | Single repo for 2-person team |
| Deployments | Separate per component | Scale independently |
| Packaging | Helm chart | Single install, multiple components |
| CI/CD | GitHub Actions | Open source friendly |
| Registry | Docker Hub | Public for open source |
| IaC | Terraform | Team familiarity |

**Repository Structure:**
```
beeper/
├── operator/           # Rust K8s operator
├── investigator/       # Python investigator agent
├── ui/                 # Flask + HTMX web UI
├── api/                # Python API service (optional, may merge with UI)
├── helm/               # Helm chart for full deployment
├── openapi/            # Shared API specifications
└── .github/workflows/  # CI/CD pipelines
```

**K8s Resources:**
- `Deployment: beeper-operator` - Rust controller (1 replica)
- `Deployment: beeper-ui` - Flask UI (1+ replicas)
- `Job: beeper-investigator-{id}` - Spawned per investigation
- `StatefulSet: qdrant` - Vector database (or external)

### Decision Impact Analysis

**Implementation Sequence:**
1. Qdrant setup + collection schemas
2. OpenAPI spec definition
3. Rust operator scaffold (kube-rs)
4. Python investigator scaffold
5. Flask UI scaffold
6. Integration wiring

**Cross-Component Dependencies:**
- OpenAPI spec must be defined before Rust/Python client generation
- Qdrant schema must be defined before investigator can write
- Operator CRDs must be defined before investigator spawning works

## Implementation Patterns & Consistency Rules

### Pattern Categories Defined

**Critical Conflict Points Identified:** 6 areas where AI agents could make different choices across Rust/Python polyglot codebase.

### Naming Patterns

**JSON Field Naming:**
- **Convention:** `snake_case` everywhere
- **Rust:** Use `#[serde(rename_all = "snake_case")]` on all structs
- **Python:** Native (Pydantic models use snake_case by default)

```rust
// Rust
#[derive(Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
struct Investigation {
    investigation_id: String,
    started_at: DateTime<Utc>,
    root_cause_hypothesis: Option<String>,
}
```

```python
# Python
class Investigation(BaseModel):
    investigation_id: str
    started_at: datetime
    root_cause_hypothesis: str | None
```

**API Endpoint Naming:**
- **Base path:** `/api/v1/`
- **Resources:** Plural nouns (`/investigations`, `/sources`)
- **Actions:** Verb suffixes where needed (`/investigations/{id}/resolve`)
- **Query params:** `snake_case` (`?service_name=payments`)

| Resource | Endpoints |
|----------|-----------|
| Investigations | `GET /api/v1/investigations`, `GET /api/v1/investigations/{id}` |
| Knowledge | `GET /api/v1/knowledge`, `POST /api/v1/knowledge`, `PATCH /api/v1/knowledge/{id}` |
| Sources | `GET /api/v1/sources`, `POST /api/v1/sources`, `DELETE /api/v1/sources/{id}` |

**Qdrant Naming:**
- **Collections:** `snake_case` (`investigations`, `knowledge`)
- **Fields:** `snake_case` (`investigation_id`, `created_at`, `confidence_level`)
- **Payload fields:** Match JSON field naming exactly

**Code Naming by Language:**

| Language | Functions/Methods | Variables | Files | Classes/Structs |
|----------|-------------------|-----------|-------|-----------------|
| Rust | `snake_case` | `snake_case` | `snake_case.rs` | `PascalCase` |
| Python | `snake_case` | `snake_case` | `snake_case.py` | `PascalCase` |

### Structure Patterns

**Monorepo Organization:**
```
beeper/
├── operator/                 # Rust K8s operator
│   ├── src/
│   │   ├── main.rs
│   │   ├── controller.rs
│   │   └── crd.rs
│   ├── tests/               # Rust tests (separate directory)
│   └── Cargo.toml
├── investigator/            # Python investigator agent
│   ├── beeper_investigator/
│   │   ├── __init__.py
│   │   ├── agent.py
│   │   ├── llm.py
│   │   └── kb.py
│   ├── tests/               # Python tests (separate directory)
│   └── pyproject.toml
├── ui/                      # Flask web UI
│   ├── beeper_ui/
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── routes/
│   │   └── templates/
│   ├── tests/
│   └── pyproject.toml
├── openapi/                 # Shared API specifications
│   └── beeper-api.yaml
├── helm/                    # Helm chart
│   └── beeper/
└── .github/workflows/       # CI/CD
```

**Test Organization:**
- Tests in separate `tests/` directory per component
- Test files mirror source structure
- Integration tests in `tests/integration/`

### Format Patterns

**API Response Format:**

Success responses return data directly:
```json
{
  "investigation_id": "inv-abc123",
  "status": "investigating",
  "started_at": "2026-01-28T14:30:00Z"
}
```

List responses include metadata:
```json
{
  "items": [...],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

**Error Response Format (RFC 7807):**
```json
{
  "type": "https://beeper.dev/errors/investigation-not-found",
  "title": "Investigation Not Found",
  "status": 404,
  "detail": "Investigation inv-abc123 does not exist",
  "instance": "/api/v1/investigations/inv-abc123"
}
```

**Date/Time Format:**
- **Always:** ISO 8601 with UTC timezone
- **Format:** `YYYY-MM-DDTHH:MM:SSZ`
- **Example:** `2026-01-28T14:30:00Z`
- **Rust:** `chrono::DateTime<Utc>`
- **Python:** `datetime.datetime` with `timezone.utc`

### Communication Patterns

**Event Naming (for NATS at scale):**
- **Pattern:** `beeper.{component}.{action}`
- **Examples:**
  - `beeper.investigation.started`
  - `beeper.investigation.progress`
  - `beeper.investigation.completed`
  - `beeper.kb.entry_created`

**Event Payload Structure:**
```json
{
  "event_id": "evt-xyz789",
  "event_type": "beeper.investigation.progress",
  "timestamp": "2026-01-28T14:30:00Z",
  "data": {
    "investigation_id": "inv-abc123",
    "step": "correlating_signals",
    "progress_pct": 45
  }
}
```

**Investigation State Machine:**
```
pending → started → investigating → [correlating|querying_kb|reasoning] → completed
                                                                      ↘ failed
```

### Process Patterns

**Logging Format (Structured JSON):**
```json
{
  "timestamp": "2026-01-28T14:30:00Z",
  "level": "INFO",
  "component": "investigator",
  "investigation_id": "inv-abc123",
  "message": "Starting signal correlation",
  "context": {
    "service": "payments",
    "signal_count": 47
  }
}
```

**Required Log Fields:**
- `timestamp` (ISO 8601 UTC)
- `level` (DEBUG, INFO, WARN, ERROR)
- `component` (operator, investigator, ui)
- `message` (human-readable)

**Optional Context Fields:**
- `investigation_id` (when applicable)
- `service` (target service being investigated)
- `error` (error details when level=ERROR)

**Error Handling:**
- Use RFC 7807 for all API errors
- Log errors with full context before returning
- Never expose internal details in user-facing errors
- Include `request_id` for correlation

**HTTP Status Code Usage:**

| Code | Usage |
|------|-------|
| 200 | Successful GET, PATCH |
| 201 | Successful POST (created) |
| 204 | Successful DELETE |
| 400 | Invalid request (validation failed) |
| 404 | Resource not found |
| 409 | Conflict (duplicate, invalid state) |
| 500 | Internal server error |

### Enforcement Guidelines

**All AI Agents MUST:**
1. Use `snake_case` for all JSON fields, API params, and Qdrant fields
2. Include required log fields in all log statements
3. Return RFC 7807 error responses for all error cases
4. Use ISO 8601 UTC for all timestamps
5. Follow the file/directory structure defined above

**Pattern Verification:**
- OpenAPI spec validates API patterns
- Pydantic/serde enforce JSON field naming
- CI linting enforces code naming conventions
- Log aggregation validates log format

### Anti-Patterns to Avoid

| Anti-Pattern | Correct Pattern |
|--------------|-----------------|
| `camelCase` JSON fields | `snake_case` |
| `/api/investigation` (singular) | `/api/v1/investigations` (plural) |
| Plain text logs | Structured JSON logs |
| Local timestamps | UTC timestamps |
| Custom error format | RFC 7807 |
| `userId` in Python | `user_id` |

## Project Structure & Boundaries

### Complete Project Directory Structure

```
beeper/
├── README.md
├── LICENSE                          # Open source license
├── CONTRIBUTING.md
├── .gitignore
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                   # Build + test all components
│   │   ├── release.yml              # Build + push containers
│   │   └── helm-lint.yml            # Validate Helm chart
│   └── CODEOWNERS
│
├── openapi/                         # Shared API specifications
│   ├── beeper-api.yaml              # Main OpenAPI spec
│   └── schemas/
│       ├── investigation.yaml
│       ├── knowledge.yaml
│       └── source.yaml
│
├── operator/                        # Rust K8s operator
│   ├── Cargo.toml
│   ├── Cargo.lock
│   ├── Dockerfile
│   ├── src/
│   │   ├── main.rs                  # Entry point
│   │   ├── lib.rs                   # Library exports
│   │   ├── controller.rs            # Main reconciliation loop
│   │   ├── crd.rs                   # CRD definitions (Investigation, Source)
│   │   ├── investigator_job.rs      # Job spawning logic
│   │   ├── sources/
│   │   │   ├── mod.rs
│   │   │   ├── prometheus.rs        # FR24: Prometheus adapter
│   │   │   └── loki.rs              # FR25: Loki adapter
│   │   ├── detection/
│   │   │   ├── mod.rs
│   │   │   └── anomaly.rs           # FR1: Anomaly detection
│   │   └── config.rs                # Configuration handling
│   └── tests/
│       ├── controller_test.rs
│       └── integration/
│           └── crd_test.rs
│
├── investigator/                    # Python investigator agent
│   ├── pyproject.toml
│   ├── poetry.lock
│   ├── Dockerfile
│   ├── beeper_investigator/
│   │   ├── __init__.py
│   │   ├── main.py                  # Entry point (run as K8s Job)
│   │   ├── agent.py                 # FR2-12: Core investigation logic
│   │   ├── llm/
│   │   │   ├── __init__.py
│   │   │   ├── client.py            # FR42-44: LiteLLM wrapper
│   │   │   ├── prompts.py           # Investigation prompts
│   │   │   └── cost.py              # FR45-47: Cost tracking, memoization
│   │   ├── kb/
│   │   │   ├── __init__.py
│   │   │   ├── client.py            # Qdrant client wrapper
│   │   │   ├── search.py            # FR5,14,15: Semantic + filtered search
│   │   │   ├── write.py             # FR9,19: Write investigation findings
│   │   │   └── schemas.py           # Pydantic models for KB documents
│   │   ├── correlation/
│   │   │   ├── __init__.py
│   │   │   └── signals.py           # FR4: Cross-layer signal correlation
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── investigation.py     # Investigation state model
│   │   │   └── finding.py           # Finding/hypothesis models
│   │   └── config.py                # Configuration (env vars)
│   └── tests/
│       ├── __init__.py
│       ├── test_agent.py
│       ├── test_llm.py
│       ├── test_kb.py
│       └── integration/
│           └── test_investigation_flow.py
│
├── ui/                              # Flask web UI
│   ├── pyproject.toml
│   ├── poetry.lock
│   ├── Dockerfile
│   ├── beeper_ui/
│   │   ├── __init__.py
│   │   ├── app.py                   # Flask app factory
│   │   ├── config.py                # Configuration
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── investigations.py    # FR31-34: Investigation views
│   │   │   ├── knowledge.py         # FR16,17,21,22,36: KB wiki interface
│   │   │   ├── sources.py           # FR28,29: Source status views
│   │   │   ├── metrics.py           # FR35: MTTR trends
│   │   │   └── sse.py               # SSE endpoints for live updates
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── investigation_service.py
│   │   │   ├── kb_service.py        # FR18: Conversational corrections
│   │   │   └── qdrant_client.py
│   │   ├── templates/
│   │   │   ├── base.html
│   │   │   ├── investigations/
│   │   │   │   ├── list.html        # FR31: Investigation list
│   │   │   │   └── detail.html      # FR32,33: Investigation pane
│   │   │   ├── knowledge/
│   │   │   │   ├── index.html       # FR36: KB wiki index
│   │   │   │   ├── entry.html       # FR16: KB entry view
│   │   │   │   ├── edit.html        # FR17: KB edit
│   │   │   │   └── diff.html        # FR22: Version diff
│   │   │   └── sources/
│   │   │       └── status.html      # FR28,29: Source status
│   │   └── static/
│   │       ├── css/
│   │       │   └── main.css
│   │       └── js/
│   │           └── htmx.min.js      # HTMX for dynamic updates
│   └── tests/
│       ├── __init__.py
│       ├── test_routes.py
│       └── test_services.py
│
├── helm/                            # Helm chart for deployment
│   └── beeper/
│       ├── Chart.yaml
│       ├── values.yaml              # Default configuration
│       ├── values-dev.yaml          # Development overrides
│       ├── templates/
│       │   ├── _helpers.tpl
│       │   ├── operator-deployment.yaml
│       │   ├── operator-rbac.yaml   # ServiceAccount, Role, RoleBinding
│       │   ├── ui-deployment.yaml
│       │   ├── ui-service.yaml
│       │   ├── qdrant-statefulset.yaml  # Optional: bundled Qdrant
│       │   ├── configmap.yaml       # Shared configuration
│       │   ├── secrets.yaml         # Secret references
│       │   └── crds/
│       │       ├── investigation-crd.yaml
│       │       └── source-crd.yaml
│       └── README.md
│
├── scripts/                         # Development scripts
│   ├── setup-dev.sh                 # Local dev environment setup
│   ├── generate-clients.sh          # Generate clients from OpenAPI
│   └── seed-kb.sh                   # Seed KB with sample data
│
├── docs/                            # Documentation
│   ├── architecture.md              # Link to this document
│   ├── development.md               # Local dev guide
│   ├── deployment.md                # Production deployment guide
│   └── api.md                       # API documentation
│
└── docker-compose.yaml              # Local development stack
```

### Architectural Boundaries

**API Boundaries:**

| Boundary | Protocol | Location |
|----------|----------|----------|
| External → UI | HTTP/HTTPS | `ui/routes/*` |
| UI → Qdrant | HTTP (Qdrant API) | `ui/services/qdrant_client.py` |
| Operator → K8s API | K8s client | `operator/src/controller.rs` |
| Investigator → Qdrant | HTTP | `investigator/kb/client.py` |
| Investigator → LLM | HTTP (LiteLLM) | `investigator/llm/client.py` |
| Operator → Prometheus | HTTP (PromQL) | `operator/src/sources/prometheus.rs` |
| Operator → Loki | HTTP (LogQL) | `operator/src/sources/loki.rs` |

**Component Boundaries:**

```
┌─────────────────────────────────────────────────────────────┐
│                        K8s Cluster                          │
│  ┌─────────────────┐                                        │
│  │  beeper-operator│──────┐                                 │
│  │     (Rust)      │      │ spawns Job                      │
│  └────────┬────────┘      ▼                                 │
│           │         ┌─────────────────┐                     │
│   watches │         │  investigator   │                     │
│   CRDs    │         │   Job (Python)  │                     │
│           │         └────────┬────────┘                     │
│           │                  │ writes findings              │
│           ▼                  ▼                              │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │ Investigation   │  │     Qdrant      │                   │
│  │ CRD (status)    │  │  (StatefulSet)  │                   │
│  └─────────────────┘  └────────┬────────┘                   │
│                                │ queries                    │
│                                ▼                            │
│                       ┌─────────────────┐                   │
│                       │   beeper-ui     │                   │
│                       │    (Flask)      │                   │
│                       └─────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

**Data Boundaries:**

| Data Type | Storage | Access Pattern |
|-----------|---------|----------------|
| Investigation state | Qdrant `investigations` | Read-your-writes |
| KB entries | Qdrant `knowledge` | Eventually consistent |
| CRD status | K8s etcd | Operator reconciliation |
| Secrets | K8s Secrets | Mounted to pods |
| Config | ConfigMap + env vars | Injected at deploy |

### FR to Structure Mapping

**Investigation Management (FR1-12):**
- FR1 (anomaly detection): `operator/src/detection/anomaly.rs`
- FR2 (spawn investigator): `operator/src/investigator_job.rs`
- FR3-8 (investigation logic): `investigator/agent.py`, `investigator/correlation/`
- FR9 (document to KB): `investigator/kb/write.py`
- FR10-12 (SRE interaction): `ui/routes/investigations.py`, `ui/templates/investigations/`

**Knowledge Base (FR13-23):**
- FR13 (import runbooks): `ui/routes/knowledge.py` (upload endpoint)
- FR14-15 (search): `investigator/kb/search.py`, `ui/services/kb_service.py`
- FR16-17 (view/edit): `ui/templates/knowledge/`
- FR18-20 (corrections): `ui/services/kb_service.py`
- FR21-22 (version history): `ui/routes/knowledge.py`, `ui/templates/knowledge/diff.html`
- FR23 (graduated authoring): `investigator/kb/write.py` (trust level)

**Observability Integration (FR24-30):**
- FR24-25 (Prometheus/Loki): `operator/src/sources/`
- FR26-27 (credentials, streaming): `operator/src/config.rs`
- FR28-29 (source status): `ui/routes/sources.py`
- FR30 (no latency): Operator design (async, non-blocking)

**User Interface (FR31-36):**
- FR31-34: `ui/routes/investigations.py`, `ui/templates/investigations/`
- FR35: `ui/routes/metrics.py`
- FR36: `ui/routes/knowledge.py`

**Deployment & Operations (FR37-41):**
- FR37-39 (K8s operator): `operator/`, `helm/`
- FR40 (health status): `operator/` + `ui/routes/sources.py`
- FR41 (self-hosted): `helm/` (all-in-cluster deployment)

**LLM Management (FR42-47):**
- All: `investigator/llm/`

### Integration Points

**Internal Communication (MVP):**
- Operator → Investigator: K8s Job creation (no direct communication)
- Investigator → UI: Shared Qdrant state (investigations collection)
- UI → Investigator findings: Qdrant queries

**External Integrations:**
- Prometheus: `operator/src/sources/prometheus.rs` via PromQL HTTP API
- Loki: `operator/src/sources/loki.rs` via LogQL HTTP API
- Claude/LLM: `investigator/llm/client.py` via LiteLLM
- Qdrant: All Python components via `qdrant-client`

**Data Flow:**
```
Prometheus/Loki → Operator (detect) → K8s Job (investigate) → Qdrant (store) → UI (display)
                                           ↓
                                      Claude API (reason)
```

### Development Workflow

**Local Development:**
```bash
# Start local stack
docker-compose up -d  # Qdrant + (optional) Prometheus/Loki

# Operator (Rust)
cd operator && cargo run

# Investigator (Python) - run manually for testing
cd investigator && poetry run python -m beeper_investigator.main

# UI (Flask)
cd ui && poetry run flask run --reload
```

**Build Process:**
```bash
# All containers
docker build -t beeper-operator:dev ./operator
docker build -t beeper-investigator:dev ./investigator
docker build -t beeper-ui:dev ./ui

# Helm install (local K8s)
helm install beeper ./helm/beeper -f helm/beeper/values-dev.yaml
```

## Architecture Validation

### Coherence Validation

All architectural decisions are compatible and reinforce each other:

| Decision Pair | Compatibility |
|---------------|---------------|
| Rust Operator + Python Investigator | ✅ K8s Job isolation, no tight coupling |
| Qdrant + LiteLLM | ✅ Both accessed via HTTP, standard patterns |
| Flask/HTMX + SSE | ✅ Native Flask support, no JavaScript complexity |
| REST MVP + NATS Scale | ✅ Clear migration path, no rewrite needed |
| Monorepo + Helm | ✅ Single source of truth, unified deployment |

**No Incompatibilities Found.**

### Requirements Coverage

**Functional Requirements: 47/47 covered**

| FR Group | Coverage | Location |
|----------|----------|----------|
| FR1-12 (Investigation) | ✅ 100% | `operator/`, `investigator/` |
| FR13-23 (Knowledge Base) | ✅ 100% | `investigator/kb/`, `ui/routes/knowledge.py` |
| FR24-30 (Observability) | ✅ 100% | `operator/src/sources/` |
| FR31-36 (User Interface) | ✅ 100% | `ui/` |
| FR37-41 (Deployment) | ✅ 100% | `helm/`, `operator/` |
| FR42-47 (LLM) | ✅ 100% | `investigator/llm/` |

**Non-Functional Requirements: 17/17 covered**

| NFR Category | Coverage | How Addressed |
|--------------|----------|---------------|
| Performance (P1-P4) | ✅ | Async Rust operator, SSE streaming, Qdrant sub-second search |
| Security (S1-S5) | ✅ | Network-only auth MVP, K8s secrets, read-only access |
| Reliability (R1-R4) | ✅ | Component independence, graceful degradation |
| Integration (I1-I4) | ✅ | K8s-native, Prometheus/Loki adapters |

### Implementation Readiness

| Criterion | Status |
|-----------|--------|
| Technology stack fully specified | ✅ |
| Project structure defined | ✅ |
| API patterns documented | ✅ |
| Data models identified | ✅ |
| Integration points mapped | ✅ |
| Build/deploy process outlined | ✅ |

**Confidence Level: High** - Ready for epic/story breakdown and implementation.

### Gap Analysis

**Critical Gaps:** 0
**Moderate Gaps:** 0
**Informational Notes:**

1. **CRD Schema Details** - Exact CRD fields will be defined during epic breakdown
2. **Qdrant Index Configuration** - Vector dimensions and index type to be determined with LLM selection
3. **Error Recovery Patterns** - Detailed retry/backoff strategies to be defined per component

These are expected to be resolved during implementation, not architecture blockers.

### Architecture Completeness Checklist

- [x] Technology stack decisions documented
- [x] Data architecture defined
- [x] API patterns established
- [x] Security model specified
- [x] Communication patterns defined
- [x] Project structure mapped
- [x] FR coverage complete
- [x] NFR coverage complete
- [x] No blocking gaps identified

## Implementation Handoff

### Epic Prioritization Recommendation

**Epic 1: Foundation**
- Qdrant setup + collection schemas
- OpenAPI spec definition
- CI/CD pipeline skeleton

**Epic 2: Operator Core**
- Rust operator scaffold (kube-rs)
- CRD definitions
- Prometheus/Loki adapters

**Epic 3: Investigator Core**
- Python investigator scaffold
- LLM integration (LiteLLM)
- KB read/write operations

**Epic 4: UI Foundation**
- Flask app scaffold
- Investigation list/detail views
- KB wiki interface

**Epic 5: Integration**
- End-to-end investigation flow
- SSE streaming
- Source status views

### Critical Path

```
OpenAPI Spec → Qdrant Schema → Operator CRDs → Investigator → UI
```

The OpenAPI spec and Qdrant schema are foundational - define these first to enable parallel work on operator and investigator.

### Architecture as Single Source of Truth

This document serves as the definitive reference for:
- Technology choices (no re-debates)
- Naming conventions (enforced via linting)
- API patterns (validated via OpenAPI)
- Project structure (followed by all agents)

Any deviation should be documented as an ADR (Architecture Decision Record) with explicit rationale.

