---
stepsCompleted:
  - step-01-init
  - step-02-context
  - step-03-starter
  - step-04-decisions
  - step-05-patterns
  - step-06-structure
  - step-07-validation
  - step-08-complete
inputDocuments:
  - prd.md
  - ux-design-specification.md
  - project-overview.md
  - integration-architecture.md
  - source-tree-analysis.md
  - api-contracts.md
  - development-guide.md
  - deployment-guide.md
workflowType: 'architecture'
project_name: 'beeper'
user_name: 'eric'
date: '2026-04-09'
lastStep: 8
status: 'complete'
completedAt: '2026-04-09'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements (44 FRs across 9 categories):**

| Category | FRs | Architectural Domain | Key Architectural Implication |
|---|---|---|---|
| Telemetry Ingestion | FR1-4 | Operator (Rust, Axum :9090) | OTEL Collector compatibility — two distinct concerns: **format compatibility** (snappy compression on/off) and **schema compatibility** (protobuf message definitions must match between OTEL Collector's `prometheusremotewrite` exporter and operator's prost 0.13 decoder). |
| Anomaly Detection | FR5-9 | Operator (Rust, in-memory) | EWMA detector must expose warmup and detection stats via the existing :8080 management API endpoint (FR9). New fields flow from EWMA module → stats struct → :8080 Axum handler. **Cross-workstream dependency:** Rust API change must land before UI diagnostic dashboard can render these fields. |
| Investigation Lifecycle | FR10-13 | Operator ↔ K8s API | Existing CRD state machine (Pending → Running → Completed/Failed). Verify Job creation, failure tracking, and cleanup work correctly. |
| Investigation Execution | FR14-19 | Investigator (Python, K8s Job) | Cross-namespace DNS resolution for Prometheus/Loki queries. LLM prompt must pass real signal data. Fix-in-place, not redesign. |
| SLO Integration | FR20-21 | Operator (Rust, ServiceLevel CRD) | ServiceLevel CRDs already exist in demo config. Verify operator's SLO controller reads them; fix wiring if broken. |
| Investigation Display | FR22-27 | UI (Flask/HTMX/SSE) | SSE streaming, progressive rendering, inline evidence, Related KB panel (new). SSE lifecycle implies operator must support **idempotent re-fetch** of investigation steps for reconnection backfill. |
| Knowledge Base | FR28-31 | UI ↔ Qdrant | Existing CRUD against `knowledge` collection. Related KB panel (FR26) consumes KBQueryStep data already in `investigations` collection — may require new query patterns (see Query Contract Stability below). |
| System Health | FR32-35 | Operator API → UI | Detection stats extension (FR33) is the only new API contract. All other stats already exist. |
| Demo Environment | FR36-39 | Makefile + Helm + OTEL | Infrastructure automation. No application code — Makefile targets, Helm values, OTEL Collector config. |
| Navigation & Layout | FR40-44 | UI (Tailwind + Jinja2) | Atomic layout shell migration — all routes adopt sidebar simultaneously. Route-driven sidebar collapse (FR44) is **server-rendered state** via Jinja2 blocks (`{% block sidebar_state %}collapsed{% endblock %}`), not client-side — distinct from SPA sidebar patterns. |

**Non-Functional Requirements (17 NFRs across 4 categories):**

| NFR | Architectural Decision Driver |
|---|---|
| NFR1 (Detection ≤5min) | EWMA warmup timing, buffer flush intervals, threshold sensitivity |
| NFR5 (≥100 series/min) | Ingestion buffer sizing, backpressure responses already implemented |
| NFR7 (Progressive rendering) | Server-sent events architecture, Jinja2 partial templates per step |
| NFR9 (SSE auto-reconnect ≤5s) | Client-side EventSource lifecycle (4 states: Connected/Disconnected/Reconnected/Failed), REST fallback via `GET /api/v1/investigations/{id}` for missed steps — operator must return steps in order for idempotent re-fetch |
| NFR13 (OTEL format compat) | Ingestion handler must accept OTEL Collector's exact output — both snappy compression format AND protobuf schema version must match |
| NFR17 (60fps sidebar transition) | CSS-only transition (`transition: width 200ms ease-in-out`), no JS layout recalculation |

### Scale & Complexity

- **Primary domain:** Full-stack distributed system (Rust + Python + Flask/HTMX + K8s)
- **Complexity level:** Medium-high
  - Brownfield: 1,032 existing tests, 4 sub-projects, ~3,900 lines existing CSS
  - Real-time: SSE streaming with reconnection and REST fallback
  - Distributed: Operator → K8s Job → Qdrant → UI data flow
  - Format compatibility: OTEL Collector → snappy+protobuf → Rust decoder chain
- **Estimated architectural components:** 6 (Operator, Investigator, UI, Qdrant, OTEL Demo, Helm/Infra)
- **New components:** 0 — all changes are fixes or extensions to existing components
- **Solo developer:** Architecture must prioritize simplicity and sequential buildability

### Architectural Risk Hotspots

The three highest-risk integration points where the pipeline is most likely to break:

| # | Risk Hotspot | Components | Why It's Dangerous |
|---|---|---|---|
| 1 | **Protobuf schema compatibility** | OTEL Collector `prometheusremotewrite` exporter → Operator prost 0.13 decoder | The OTEL Collector may emit a protobuf schema version that doesn't match what the operator compiled against. This is not a format issue (snappy on/off) — it's a **schema version issue** (protobuf message definitions). If the Collector emits fields the operator doesn't know about, prost silently ignores them. If the operator expects fields the Collector doesn't send, deserialization may silently produce zero values. Diagnosis: compare the `.proto` definitions compiled into each side. |
| 2 | **Cross-namespace DNS resolution** | Investigator Job (beeper namespace) → Prometheus/Loki (otel-demo namespace) | Investigator Jobs must resolve `prometheus.otel-demo.svc.cluster.local` and `loki.otel-demo.svc.cluster.local` using standard kind cluster DNS. If Source CRDs contain short names (`prometheus:9090` instead of FQDNs), resolution fails silently — the investigator gets connection timeouts, not DNS errors. Diagnosis: check Source CRD endpoint values against actual service FQDNs. |
| 3 | **Atomic template migration** | UI (all Jinja2 templates) | Every template must inherit from the new layout shell base template in a single PR. Any template that misses the migration renders without navigation — the user sees content floating in a void. This is the highest-risk UI change because it touches every route simultaneously with no incremental path. Diagnosis: `grep -r "extends" templates/` to verify all templates inherit from the new base. |

### Technical Constraints & Dependencies

**Hard constraints (non-negotiable):**

| Constraint | Source | Impact |
|---|---|---|
| Rust operator (kube-rs 0.95, Axum 0.7) | Existing codebase | No language or framework changes. Extend existing handlers. |
| **Dual HTTP server architecture** | Existing operator | :8080 (Axum management API) and :9090 (ingestion server) are separate servers in the same process. Detection stats (FR9) flow from EWMA module through :8080 management API, NOT through :9090 ingestion API. |
| Python investigator (Poetry, LiteLLM) | Existing codebase | No new dependencies unless strictly required for fix. |
| Flask/Jinja2/HTMX UI | Existing codebase + PRD | No frontend framework (React, Vue). HTMX for interactivity. |
| Tailwind CSS (standalone binary) | UX spec Phase 0 | No Node.js dependency. Tailwind CLI generates CSS. |
| SSE only (no WebSocket) | PRD + UX spec | EventSource API. Server-sent events from operator/UI. |
| No authentication | PRD scope | Simplifies every endpoint. Network-level access control only. |
| OTEL Astronomy Shop demo | PRD FR36-39 | Demo workload is the OTel demo, not custom app. |
| kind cluster | PRD deployment model | Local K8s for development and demo. |
| Single-tenant, single-replica | PRD scope | No multi-tenancy, no HA, no horizontal scaling. |

**Soft constraints (existing patterns to preserve):**

| Pattern | Source | Preserve Because |
|---|---|---|
| snake_case JSON everywhere | API contracts, development guide | Serde `rename_all`, Pydantic native. Changing breaks all consumers. |
| RFC 7807 error format | API contracts | Established contract between UI and operator. |
| ISO 8601 UTC timestamps | Development guide | All components expect this format. |
| Structured JSON logging | Development guide | Operator and investigator both emit structured logs. |
| K8s Job-based investigation | Integration architecture | Decouples operator from investigator. No direct HTTP between them. |
| 6 Qdrant collections | Project overview | Schema exists, data exists. No collection changes in scope. |
| OpenAPI 3.1 spec | API contracts | Source of truth for UI ↔ operator contract. |

**Dependencies between workstreams:**

```
Pipeline Fix (sequential):
  Checkpoint 1: OTEL → Ingestion → data flows ──────────┐
  Checkpoint 2: Detection → EWMA fires                  │
  Checkpoint 3: Investigator → real signals              │
  Checkpoint 4: LLM → specific root cause                │
  Checkpoint 5: ServiceLevel CRD wiring                  │
                                                         │
  ┌─ Cross-workstream dependency ────────────────────┐   │
  │ FR9: Detection stats API extension (Rust :8080)  │   │
  │ Must land BEFORE UI diagnostic dashboard renders │   │
  └──────────────────────────────────────────────────┘   │
                                                         │
UI Overhaul (parallel after checkpoint 1):               │
  Phase 0: Tailwind installation ◄───────────────────────┘
  Phase 1: Layout shell (atomic — all routes, highest-risk UI change)
  Phase 2: New components (KB panel, diagnostic tiles ← depends on FR9)
  Phase 3: Incremental migration (as-touched)
```

### Cross-Cutting Concerns

| Concern | Components Affected | Architectural Mechanism |
|---|---|---|
| **Investigation state machine** | Operator, K8s API, Investigator, Qdrant, UI | CRD status field is source of truth. Operator manages transitions. UI reads via API + SSE. |
| **SSE lifecycle** | Operator (emitter), UI (consumer) | Two SSE endpoints: investigation list updates, investigation detail streaming. Client-side `EventSource` with 4-state lifecycle (Connected/Disconnected/Reconnected/Failed). Reconnect requires **idempotent step re-fetch** — operator must support `GET /api/v1/investigations/{id}` returning ordered steps for backfill. |
| **OTEL ingestion compatibility** | OTEL Collector, Operator ingestion (:9090) | Two distinct concerns: (1) **Format compatibility** — snappy compression toggle, content-type headers. (2) **Schema compatibility** — protobuf message definitions between OTEL Collector's exporter and operator's prost 0.13 compiled schemas. Schema mismatch is silent — fields are ignored or zero-valued. |
| **Qdrant stability** | Investigator (writer), UI (reader) | **Schema stability:** 6 collections with established schemas, no schema changes in scope. **Query contract stability:** Related KB panel (FR26) may require new Qdrant query patterns against existing `investigations` collection to extract KBQueryStep results — not a schema change, but a query contract change. Both Python components use same Qdrant client patterns. |
| **Tailwind/CSS coexistence** | UI (all templates) | New Tailwind CSS coexists with ~3,900 lines existing custom CSS. Coexistence rule: never mix Tailwind + custom CSS on same element. |
| **Atomic layout shell migration** | UI (all routes) | **Highest-risk UI change.** All routes must adopt sidebar layout in one PR. Any template that fails to inherit from the new base renders without navigation. Anti-pattern: two navigation systems coexisting. Verification: `grep -r "extends" templates/` confirms all templates use new base. |
| **Detection stats data flow** | Operator (EWMA module → stats struct → :8080 API), UI (:8080 API → diagnostic dashboard) | New fields added to existing `/api/v1/ingestion/stats` response on :8080 management API. Data originates in EWMA detector, crosses internal module boundary to stats struct, serialized via Axum handler. **Cross-workstream dependency** — Rust API change must ship before UI can render diagnostic tiles. |
| **Server-rendered sidebar state** | UI (Jinja2 templates) | Sidebar state (auto/collapsed/expanded) is **server-determined per route** via Jinja2 block inheritance (`{% block sidebar_state %}`), not client-side JavaScript. Investigation detail template sets `collapsed`; all other templates default to `auto` (viewport-responsive). This is a server-rendered state decision, architecturally different from SPA sidebar patterns. |
| **Demo infrastructure** | Makefile, Helm values, OTEL Collector config, kind cluster | End-to-end demo reliability is a cross-cutting quality attribute. Every component must work together for the 3/3 repeatability target. |

## Starter Template Evaluation

### Primary Technology Domain

**Full-stack distributed system** — brownfield, established codebase. No starter template selection needed.

### Brownfield Status: Existing Technical Foundation

This project has a complete, functioning codebase with 4 sub-projects, 1,032 tests, and an established deployment pipeline. All technology selections were made during v0.1.0 and are locked for this PRD scope. This section documents the existing foundation as the architectural baseline.

### Existing Foundation (Replaces Starter Selection)

**No initialization command** — the project exists. `git clone` + dependency install is the "starter."

### Architectural Decisions Already Made by Existing Codebase

**Language & Runtime:**

| Component | Language | Runtime | Package Manager |
|---|---|---|---|
| Operator | Rust (stable, edition 2021) | tokio 1.x (full features) | Cargo |
| Investigator | Python ^3.11 | CPython | Poetry 1.7+ |
| UI | Python ^3.11 | CPython (Flask dev server / Gunicorn prod) | Poetry 1.7+ |
| Helm | YAML | Helm 3.x CLI | N/A |

**HTTP & API Framework:**

| Component | Framework | Ports | Protocols |
|---|---|---|---|
| Operator management | Axum 0.7 | :8080 | REST (JSON), SSE |
| Operator ingestion | Custom Axum server | :9090 | Prometheus remote write (snappy+protobuf), Loki push (JSON) |
| UI | Flask ^3.0 | :5000 | HTML (Jinja2), SSE, REST proxy to operator |
| Investigator | httpx ^0.27 (client only) | None (ephemeral Job) | Outbound HTTP to Prometheus, Loki, Qdrant, LLM |

**Styling Solution:**

| Current | Migration Target | Strategy |
|---|---|---|
| ~3,900 lines custom CSS | Tailwind CSS (standalone binary, no Node.js) | Coexistence: new components in Tailwind, existing CSS untouched until template is individually migrated. Never mix on same element. |

**Frontend Interactivity:**

| Technology | Role | What It Replaces |
|---|---|---|
| HTMX | Server-driven partial page updates | No SPA framework (no React/Vue/Angular) |
| SSE (EventSource) | Real-time streaming | No WebSocket |
| Vanilla JavaScript | SSE lifecycle management, sidebar toggle, clipboard | No JS framework |
| Jinja2 macros | Reusable components | No component library |

**Build Tooling:**

| Tool | Component | Purpose |
|---|---|---|
| `cargo build/test/fmt/clippy` | Operator | Compile, test, lint |
| `poetry install/run` | Investigator, UI | Dependency management, execution |
| `ruff` | Investigator, UI | Python linting |
| `mypy` (strict) | Investigator, UI | Type checking |
| `docker build` | All | Container images |
| `helm lint/install` | Deployment | K8s chart validation and deployment |
| `tailwindcss --watch/--minify` | UI (**new**) | CSS generation from Tailwind utilities. **Build pipeline addition:** Tailwind CLI must integrate with existing Makefile (new targets: `tailwind-watch`, `tailwind-build`) and UI Dockerfile (production minification as build stage). This is a build architecture change, not just a CSS addition. |
| `make` | All | Orchestration (build, deploy, demo, fault, recover) |

**Testing Framework:**

| Component | Framework | Count | Mocking |
|---|---|---|---|
| Operator | `cargo test` | 162 | wiremock 0.5 |
| Investigator | `pytest` ^8.0 | 375 | Standard mocking |
| UI | `pytest` ^8.0 | 495 | respx ^0.21 |

**Test suite health caveat:** The 1,032 tests are documented from v0.1.0, but their current pass/fail status against the broken pipeline state is **unknown**. Failing tests are diagnostic information — they indicate which components are broken and how. **Recommendation:** Run the full test suite across all 3 components as a pre-implementation baseline before beginning pipeline fixes. Test failures may reveal root causes faster than manual debugging.

**Integration test gap:** All 1,032 tests are **unit-level**. The pipeline breakage is an integration problem at component boundaries:
- OTEL Collector → Operator ingestion (protobuf schema compatibility)
- Operator detection → Investigation CRD creation (EWMA threshold calibration)
- Investigator → Prometheus/Loki (cross-namespace DNS resolution)
- Investigator → Qdrant (investigation result persistence)

No existing tests cover these boundaries. Architecture should account for this gap when defining the testing strategy for pipeline fixes — manual verification via `curl`, `kubectl logs`, and Makefile targets will be the primary integration testing mechanism for this PRD scope.

**Code Organization (existing structure):**

```
beeper/
├── operator/src/          # Rust: controllers/, ingestion/, slo/, detection/
├── investigator/src/      # Python: steps/, llm/, signals/, kb/
├── ui/                    # Python: templates/, static/, routes/
├── helm/beeper/           # Helm chart: templates/, values.yaml, CRDs
├── demo/                  # OTEL demo config, ServiceLevel CRDs
├── scripts/               # Setup, seeding, testing utilities
├── docs/                  # Architecture, API contracts, guides
└── Makefile               # Orchestration entry point
```

**Data Layer:**

| Storage | Technology | Schema | Collections/Tables |
|---|---|---|---|
| Vector DB | Qdrant v1.15.0 (local) / v1.12.0 (Helm) | 1536d vectors (OpenAI-compatible) | 6 collections (investigations, knowledge, knowledge_versions, corrections, learning_patterns, service_trust_levels) |
| K8s CRDs | beeper.dev/v1 | YAML manifests | Source, Investigation, ServiceLevel |
| Secrets | K8s Secrets | Key-value | LLM credentials, source credentials |

**Qdrant version discrepancy risk:** Local development uses Qdrant **v1.15.0** (via docker-compose) while the Helm chart deploys **v1.12.0**. If investigator or UI code uses Qdrant client features or API behaviors introduced between v1.12.0 and v1.15.0, those calls will work locally but fail in the Helm deployment. **Recommendation:** Either pin both to the same version (prefer upgrading Helm to v1.15.0) or verify that all Qdrant operations use only v1.12.0-compatible APIs.

**Development Experience:**

| Feature | Implementation |
|---|---|
| Hot reload (Rust) | `cargo watch` (optional, local only) |
| Hot reload (Python) | Flask debug mode (`FLASK_ENV=development`) |
| Local infra | `docker-compose up -d` (Qdrant only) |
| K8s local | kind cluster |
| CI/CD | GitHub Actions (lint + test + build per component, Helm lint) |
| Container registry | ghcr.io |
| API spec | OpenAPI 3.1 |

**Development inner loop asymmetry:** The operator and Python components have fundamentally different iteration speeds:

| Component | Change → Test Cycle | Mechanism |
|---|---|---|
| **Operator (Rust)** | **Slow** — Docker rebuild + `kind load docker-image` + pod restart | Compiled binary must be containerized and loaded into kind. Each iteration: `docker build` (~1-3 min) + `kind load` (~30s) + pod restart. No live reload in cluster. |
| **Investigator (Python)** | **Medium** — Docker rebuild + `kind load` for Job template changes; `poetry run` for logic-only changes testable outside cluster | Jobs are ephemeral, so each investigation spawns a fresh pod from the image. |
| **UI (Python)** | **Fast** — `poetry run flask run` with debug mode for local dev; Docker rebuild only for cluster testing | Flask dev server hot-reloads on file changes. Most UI work can be tested locally against the operator API via port-forward. |

This asymmetry affects pipeline fix iteration speed: operator ingestion/detection fixes (Workstream 1, Checkpoints 1-2) will have the slowest feedback loop. Plan accordingly — get unit tests passing first, then validate in-cluster.

### What This Foundation Means for Architecture Decisions

The existing codebase has already resolved these categories of architectural decisions:

| Category | Status | Architecture Implication |
|---|---|---|
| **Language selection** | Locked | No migration. Rust for performance-critical operator, Python for LLM/AI flexibility. |
| **Framework selection** | Locked | Axum, Flask, HTMX. No framework changes. |
| **Database selection** | Locked | Qdrant. No additional databases. |
| **API design** | Locked | REST + SSE + OpenAPI. snake_case + RFC 7807. |
| **Testing strategy** | Locked (unit) | cargo test + pytest. Existing 1,032 tests as regression safety net. **Gap:** no integration tests at component boundaries. |
| **Deployment model** | Locked | Helm chart on K8s. Single-tenant, single-replica. |
| **CSS framework** | **New addition** | Tailwind CSS standalone binary — new technology + new build pipeline step. |

**Note:** Because this is brownfield, the first implementation task is NOT project initialization — it's running the existing test suite to establish a baseline, then pipeline diagnostic verification (Workstream 1, Checkpoint 1).

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**

| # | Decision | Category | Blocks |
|---|---|---|---|
| AD-1 | OTEL protobuf schema alignment approach | Data / Ingestion | Pipeline Checkpoint 1 |
| AD-2 | Detection stats API extension design | API | Pipeline Checkpoint 2 + UI diagnostic dashboard |
| AD-3 | Layout shell template inheritance strategy | Frontend | All UI overhaul work |
| AD-4 | SSE reconnection and REST backfill contract | API / Frontend | Investigation detail reliability (NFR9) |

**Important Decisions (Shape Architecture):**

| # | Decision | Category | Affects |
|---|---|---|---|
| AD-5 | Related KB panel Qdrant query pattern | Data | Investigation detail view (FR26) |
| AD-6 | Sidebar state management approach | Frontend | Navigation behavior (FR40-44) |
| AD-7 | Tailwind build pipeline integration | Infrastructure | UI development workflow |
| AD-8 | Integration testing strategy for pipeline fixes | Testing | All pipeline checkpoints |

**Deferred Decisions (Post-MVP):**

| Decision | Rationale for Deferral |
|---|---|
| Authentication & authorization | Explicitly out of scope per PRD |
| Horizontal scaling / HA | Single-tenant, single-replica per PRD |
| WebSocket / real-time collaboration | SSE only per PRD + UX spec |
| Mobile responsive (<768px) | Deferred per PRD |
| Qdrant collection schema changes | No schema changes in scope |
| CI/CD pipeline changes | Existing GitHub Actions sufficient |

**Do Not Decide (Tempting but Out of Scope):**

These decisions may seem natural to make during implementation but are explicitly deferred. Dev agents must NOT introduce these:

| Tempting Decision | Why Not Now |
|---|---|
| Qdrant query optimization (indexes, caching) | Current query patterns are sufficient for single-tenant demo scale. Optimize only if latency measured as a problem. |
| Log aggregation / structured log pipeline | Existing `kubectl logs` + structured JSON logging is sufficient for debugging. No centralized log aggregation in scope. |
| Operator metrics/tracing export (Prometheus self-metrics) | Beeper monitors other services — monitoring Beeper itself is a meta-concern for post-MVP. |
| Custom demo application (replace OTEL Astronomy Shop) | PRD explicitly uses OTEL Astronomy Shop. No custom demo workload. |
| Notification integration (Slack, PagerDuty) | PRD defers to post-MVP Phase 2. |
| WebSocket upgrade for SSE endpoints | SSE is sufficient for unidirectional server→client streaming. No bidirectional need in current scope. |
| Tailwind component library / design system package | Jinja2 macros are the component system. No separate package. |
| Investigation workflow actions (approve, reject, remediate) | Beeper is read-only for this PRD. No user actions on investigations. |

### Data Architecture

**AD-1: OTEL Protobuf Schema Alignment**

- **Decision:** Verify-first, adapt-if-needed approach
- **Rationale:** The operator compiles Prometheus remote write protobuf definitions via prost 0.13. The OTEL Collector's `prometheusremotewrite` exporter may use a different proto version. Rather than preemptively changing the operator's proto definitions, the approach is:
  1. Deploy OTEL demo and capture raw bytes from Collector output
  2. Attempt deserialization with current operator proto definitions
  3. If deserialization fails or produces zero values → update operator's `.proto` files to match Collector's version
  4. If deserialization succeeds → no change needed
- **Affects:** Operator ingestion module (`operator/src/ingestion/`)
- **Constraint:** The OTEL Collector configuration must NOT be modified to accommodate Beeper. Beeper adapts to the Collector's output format (NFR13).

**AD-5: Related KB Panel Qdrant Query Pattern**

- **Decision:** Query `investigations` collection for KBQueryStep results by investigation ID, not a separate KB search
- **Rationale:** The investigator's KBQueryStep stores its results (matched KB entry IDs and relevance scores) in the investigation record in Qdrant's `investigations` collection. The Related KB panel reads this existing data — it does NOT perform a new semantic search against the `knowledge` collection. This is a read of existing data, not a new query pattern.
- **Status:** **Assumption — not yet verified.** Must be verified during investigation execution fix (Pipeline Checkpoint 3) by inspecting an actual investigation record in Qdrant to confirm KBQueryStep results contain individual KB entry IDs. If they contain only a text summary without entry references, a separate Qdrant query against the `knowledge` collection by service name will be needed as fallback.
- **Query contract:** `GET investigation by ID → extract steps where step_type == "KBQueryStep" → render matched KB entries`
- **Affects:** UI investigation detail template, Qdrant read path

### Authentication & Security

**No decisions required.** PRD explicitly scopes out authentication and authorization. All endpoints are unauthenticated. Access control is at the network/infrastructure level (port-forwarding for demo, cluster-internal for production). Security considerations are limited to:
- K8s Secrets for credentials (existing pattern, no changes)
- Pod security context (`runAsNonRoot: true`, `runAsUser: 1000`) — already configured
- No PII in investigation data (observability signals only)

### API & Communication Patterns

**AD-2: Detection Stats API Extension**

- **Decision:** Extend existing `/api/v1/ingestion/stats` response with new fields (additive only)
- **Backward compatibility constraint:** Existing fields (`metrics_received`, `logs_received`, `buffer_utilization`) must NOT change name, type, or structure. New fields are strictly additive. Dev agents must NOT refactor the existing response shape for consistency or aesthetics — the existing UI consumes these fields as-is.
- **New fields added to response:**

```json
{
  "metrics_received": 12847,
  "logs_received": 3201,
  "buffer_utilization": 0.34,
  "anomalies_detected": 2,
  "anomalies_suppressed": 0,
  "active_metric_detectors": 23,
  "ewma_warmup_samples": 10,
  "ewma_warmup_minimum": 10
}
```

- **Rationale:** Extending the existing endpoint (not creating a new one) keeps the API surface minimal. The 4 new fields (`anomalies_detected`, `anomalies_suppressed`, `active_metric_detectors`, `ewma_warmup_samples`) plus `ewma_warmup_minimum` (detector's configured minimum) are sufficient for the UI diagnostic dashboard to compute warmup percentage: `ewma_warmup_samples / ewma_warmup_minimum * 100`.
- **Implementation:** Rust stats struct extension in operator. EWMA detector module exposes counters; stats aggregation collects them on the :8080 management API handler.
- **Affects:** Operator stats module, UI Ingestion Stats template
- **Cross-workstream dependency:** This API change must ship before the UI diagnostic dashboard can render EWMA warmup and detection stats.

**AD-4: SSE Reconnection and REST Backfill Contract**

- **Decision:** Client-side EventSource reconnection with REST backfill via existing investigation detail API. Explicitly **no `Last-Event-ID` support** on the server.
- **`Last-Event-ID` decision:** The SSE spec natively supports `Last-Event-ID` — the client sends it on reconnect, and the server resumes from that point. We are choosing **not** to implement this. Rationale:
  - REST backfill is simpler — no server-side state tracking of event sequences
  - Investigation payloads are small (<50 steps per investigation) — fetching the full state is negligible overhead
  - Solo developer — simpler server wins over marginal efficiency
  - If `Last-Event-ID` support is ever needed, it can be added later without breaking existing clients
- **Contract:**
  1. Client opens `EventSource` to SSE endpoint for investigation detail streaming
  2. On disconnect (`onerror`): browser auto-retries with exponential backoff (native EventSource behavior)
  3. On reconnect (`onopen` after disconnect): client fetches `GET /api/v1/investigations/{id}` to get full current state
  4. Client diffs received steps against already-rendered steps, inserts missed steps at correct positions based on step `order` field
  5. After 5 consecutive retry failures: show static "Live updates unavailable — refresh to sync" message
- **Ordering guarantee:** Investigation steps have an `order` field (integer sequence number). REST response returns steps ordered by this field. Client inserts backfilled steps at the correct DOM position, maintaining narrative coherence.
- **Affects:** Client-side `static/js/sse.js` module, investigation detail template

### Frontend Architecture

**AD-3: Layout Shell Template Inheritance Strategy**

- **Decision:** Modify existing `base.html` to include sidebar + top bar layout shell. All 29 page templates that extend `base.html` inherit the new layout automatically.
- **Template inventory (verified):**
  - **102 total HTML templates** in `ui/beeper_ui/templates/`
  - **1 base template:** `base.html` — the single file to rewrite with layout shell
  - **29 page templates** that `{% extends "base.html" %}` — inherit layout automatically
  - **72 partial templates** (prefixed with `_`) — included by page templates, no `extends`, no changes needed for layout
- **Migration scope:**
  - **1 file rewrite:** `base.html` → add sidebar component, top bar with breadcrumb slot, content area wrapper
  - **1-2 template updates:** `investigations/detail.html` adds `{% block sidebar_state %}collapsed{% endblock %}`; other pages default to `auto`
  - **29 incremental updates:** Add `{% block breadcrumb %}Section Name{% endblock %}` to each page template (can be done incrementally, not atomically)
- **Coexistence:** The layout shell is built in Tailwind. Page content inside `{% block content %}` continues to use existing custom CSS until individually migrated.
- **Verification:** `grep -r "extends" ui/beeper_ui/templates/ --include="*.html"` — every result must reference `base.html` (or a future base that itself extends `base.html`).
- **Affects:** `ui/beeper_ui/templates/base.html` (primary), all page templates (incremental)

**AD-6: Sidebar State Management Approach**

- **Decision:** Hybrid — server-rendered default + client-side override
- **How it works:**
  1. **Server-rendered default:** Each template sets its sidebar state via Jinja2 block (`auto` or `collapsed`). This determines what HTML/CSS classes are in the initial response.
  2. **Viewport-responsive (CSS):** `auto` state uses Tailwind responsive classes (`w-16 lg:w-64`) — sidebar collapses/expands based on viewport width via CSS media queries alone, no JavaScript.
  3. **Client-side override:** `[` key toggle and hamburger click set a JavaScript override stored in `sessionStorage`. Override resets on route navigation (next full page load clears it).
  4. **Group expand/collapse:** Sidebar group state (Observe/Learn/Manage open or closed) stored in `sessionStorage` by group label. Defaults: all expanded.
- **Rationale:** Server-rendered state means no JavaScript is needed for the correct initial layout. CSS handles responsive behavior. JavaScript only needed for user-initiated overrides (hamburger, `[` key). This is the simplest approach that satisfies all UX spec requirements (FR40-44).
- **Affects:** Layout shell template, sidebar component macro, minimal JavaScript

**AD-7: Tailwind Build Pipeline Integration**

- **Decision:** Tailwind CLI standalone binary integrated into Makefile + UI Dockerfile
- **Development workflow:**
  - New Makefile target: `make tailwind-watch` — runs `tailwindcss --watch -i ui/beeper_ui/static/css/input.css -o ui/beeper_ui/static/css/tailwind.css`
  - Developer runs `make tailwind-watch` in a separate terminal alongside `poetry run flask run`
- **Production build:**
  - New Makefile target: `make tailwind-build` — runs `tailwindcss --minify -i ui/beeper_ui/static/css/input.css -o ui/beeper_ui/static/css/tailwind.css`
  - UI Dockerfile adds a build stage: download Tailwind CLI binary, run minification, copy output CSS to final image
  - `make tailwind-build` also called as prerequisite in existing `docker build` flow
- **Tailwind config:** `tailwind.config.js` at `ui/` root with `content: ['./beeper_ui/templates/**/*.html', './beeper_ui/static/js/**/*.js']` for tree-shaking
- **Affects:** Makefile, UI Dockerfile, new `ui/tailwind.config.js`, new `ui/beeper_ui/static/css/input.css`

**AD-7 addendum (2026-05-20, Story 3.2 implementation discovery): Tailwind v4 + main.css cascade contract**

Story 3.1 implemented AD-7 using Tailwind v4 (not v3). The recommended v4 setup places utilities inside an `@layer utilities` via `@import "tailwindcss/utilities.css" layer(utilities);` in `input.css`.

CSS `@layer` rules have **lower cascade priority than ALL unlayered rules, regardless of selector specificity**. The existing `main.css` (6,982 lines) is unlayered and contains bare-element selectors like `main { padding: 20px 0 }`, `header { padding: 20px 0 }`, and `nav { display: flex }`, plus a global `* { box-sizing: border-box }`. With Tailwind utilities layered, these unlayered legacy rules beat utility classes like `.p-6` even though `.p-6` has higher specificity (0,1,0 vs 0,0,1).

This surfaced during Story 3.2's layout-shell migration: the shell's `<main>`, `<header>`, and `<nav>` rendered with legacy padding/display instead of the Tailwind utilities. **Fix (in `input.css`): drop the `layer(utilities)` annotation** so utilities cascade by normal specificity rules. Theme remains layered (`@layer theme;`) so it loses cleanly to author overrides.

**Resulting cascade contract:**

| Conflict type | Winner | Notes |
|---|---|---|
| Tailwind utility class (e.g. `.p-6`) vs bare element selector (e.g. `main { … }`) in `main.css` | **Tailwind utility** wins on class-vs-element specificity (0,1,0 > 0,0,1) | Intended behavior for the layout shell and any newly-migrated template |
| Tailwind utility class vs class-based legacy selector (e.g. `.card { … }`) | **Same specificity (0,1,0)** — source order decides; `tailwind.css` loads first so `main.css` wins | Unmigrated pages using `.card`, `.entry-card`, etc. keep their legacy styling unchanged |
| Tailwind utility class vs higher-specificity legacy selector (e.g. `.entry-card .header h2 { … }`) | **Legacy wins** (0,2,1 > 0,1,0) | Acceptable — per-template migration is per the Tailwind/CSS coexistence rule |
| Property NOT touched by a Tailwind class (e.g. an element gets `px-4` but no `py-*`) | **Legacy wins** for the untouched axis | Mitigation: explicitly set the property via Tailwind |

**Implication for future template-migration stories:** when migrating a template to Tailwind, set the FULL set of relevant properties via utilities so legacy bare-element rules cannot leak through on uncovered axes. The Story 3.2 layout shell (`components/layout.html`) demonstrates the pattern with three defensive overrides against known `main.css` selectors:

| Shell element | Override | Cancels legacy rule |
|---|---|---|
| `<header>` | `py-0` | `header { padding: 20px 0 }` (would collapse the `h-12` box under `box-sizing: border-box`) |
| `<nav>` | `block` | `nav { display: flex }` (would lay sidebar links horizontally) |
| `<main>` | `pt-12 pb-0` | `main { padding: 20px 0 }` (and clears the 48px fixed header) |

**Future cleanup option:** once enough pages migrate, `main.css`'s bare-element selectors (`body`, `header`, `nav`, `main`) can be removed or rewritten as classes, eliminating the need for these defensive overrides.

### Infrastructure & Deployment

**Qdrant version alignment:** Upgrade Helm chart Qdrant to v1.15.0 to match local development. This is a values.yaml change, not an architectural decision, but noted here to prevent the version discrepancy from causing integration issues.

**Demo environment:** OTEL Collector configuration is managed via `demo/otel-demo-values.yaml` Helm values overlay. No custom Collector image — configuration only. The Collector's `prometheusremotewrite` exporter targets `beeper-operator.default.svc.cluster.local:9090/api/v1/write` and the `loki` exporter targets `beeper-operator.default.svc.cluster.local:9090/loki/api/v1/push`.

### Testing Strategy

**AD-8: Integration Testing Strategy for Pipeline Fixes**

- **Decision:** Manual verification via Makefile targets + `kubectl` + `curl`, documented as runbook steps
- **Rationale:** The pipeline breakage is at integration boundaries that unit tests don't cover. Writing automated integration tests for K8s Job → Prometheus cross-namespace queries would require a running cluster, which is the demo environment itself. The manual verification steps ARE the integration tests — they just run through the Makefile.
- **Verification protocol per checkpoint:**

| Checkpoint | Verification Command | Expected Result |
|---|---|---|
| 1: Ingestion | `curl localhost:8080/api/v1/ingestion/stats` | `metrics_received > 0`, `logs_received > 0` |
| 2: Detection | `kubectl get investigations.beeper.dev` | Investigation CRD created after fault injection |
| 3: Signals | `kubectl logs -l app=investigator` | Prometheus/Loki queries return non-empty results |
| 4: LLM output | `curl localhost:8080/api/v1/investigations/{id}` | Findings reference specific service names + metric values |
| 5: SLO | `kubectl get servicelevel.beeper.dev` | ServiceLevel CRDs exist and operator logs show SLO processing |

- **Pre-implementation baseline:** Run `cargo test`, `poetry run pytest` (investigator), `poetry run pytest` (UI) to establish which tests are currently passing/failing. Document results as diagnostic input.
- **Affects:** Makefile targets (may need new `make test-pipeline` convenience target), developer workflow

### Decision Impact Analysis

**Implementation Sequence:**

```
1. AD-8  Test baseline (run existing tests, document results)
2. AD-1  OTEL protobuf verification (Checkpoint 1 — data must flow first)
3. AD-2  Detection stats API extension (unblocks UI diagnostic dashboard)
4. AD-7  Tailwind build pipeline (unblocks all UI overhaul work)
5. AD-3  Layout shell template migration (atomic — unblocks all UI components)
6. AD-6  Sidebar state management (depends on layout shell)
7. AD-4  SSE reconnection contract (investigation detail reliability)
8. AD-5  Related KB panel query (investigation detail feature)
```

**Cross-Component Dependencies:**

| Decision | Depends On | Blocks |
|---|---|---|
| AD-1 (Protobuf) | AD-8 (test baseline informs what's broken) | AD-2 (data must flow before detection stats make sense) |
| AD-2 (Stats API) | AD-1 (data flowing) | UI diagnostic dashboard (Phase 2) |
| AD-3 (Layout shell) | AD-7 (Tailwind pipeline) | AD-6 (sidebar), all UI components |
| AD-4 (SSE reconnect) | AD-3 (layout shell) | Investigation detail reliability |
| AD-5 (KB panel) | AD-3 (layout shell) | Investigation detail feature completeness |
| AD-6 (Sidebar) | AD-3 (layout shell) | Navigation behavior |
| AD-7 (Tailwind) | AD-8 (test baseline informs what's broken) | AD-3 (layout shell needs Tailwind) |
| AD-8 (Test baseline) | Nothing | Informs AD-1, AD-7, and all subsequent work |

## Implementation Patterns & Consistency Rules

### Pattern Categories Defined

**Critical Conflict Points Identified:** 8 areas where AI agents could make different choices that would break consistency or cause integration failures.

These patterns are primarily extracted from the existing codebase (v0.1.0). New patterns are introduced only for the Tailwind migration and sidebar layout — areas where no precedent exists.

### Naming Patterns

**Rust Naming (Operator):**

| Element | Convention | Example | Enforced By |
|---|---|---|---|
| Modules | snake_case | `ingestion`, `detection`, `slo` | `cargo fmt` |
| Structs | PascalCase | `IngestionStats`, `InvestigationStatus` | `cargo fmt` |
| Functions | snake_case | `get_ingestion_stats`, `create_investigation` | `cargo fmt` |
| Constants | SCREAMING_SNAKE_CASE | `DEFAULT_EWMA_SPAN`, `INGESTION_PORT` | `cargo clippy` |
| Serde fields | `#[serde(rename_all = "snake_case")]` | `metrics_received`, `buffer_utilization` | Serde derives |
| HTTP routes | `/api/v1/{resource}` | `/api/v1/ingestion/stats`, `/api/v1/investigations` | Convention |

**Python Naming (Investigator + UI):**

| Element | Convention | Example | Enforced By |
|---|---|---|---|
| Modules/files | snake_case | `investigation_steps.py`, `kb_query.py` | `ruff` |
| Classes | PascalCase | `InvestigationStep`, `KBQueryResult` | `ruff` |
| Functions/methods | snake_case | `run_investigation`, `query_prometheus` | `ruff` |
| Constants | SCREAMING_SNAKE_CASE | `DEFAULT_LLM_MODEL`, `QDRANT_COLLECTION` | Convention |
| Pydantic fields | snake_case | `service_name`, `root_cause` | Pydantic default |
| Flask routes | `/route-name` (kebab-case) | `/investigations`, `/knowledge/entry/<id>` | Convention |
| Jinja2 template variables | snake_case | `{{ inv.service_name }}`, `{{ stats.metrics_received }}` | Convention |

**HTML/CSS Naming:**

| Element | Convention | Example |
|---|---|---|
| HTML IDs | kebab-case | `#investigation-list`, `#sidebar-nav`, `#sse-reconnecting` |
| Tailwind custom classes | Tailwind semantic tokens only — no arbitrary values | `bg-surface-base text-primary`, NEVER `bg-[#0f0f1a]` |
| Existing CSS classes | Preserve existing names, do not rename | Whatever exists in current stylesheets |
| Jinja2 block names | snake_case | `{% block sidebar_state %}`, `{% block breadcrumb %}`, `{% block content %}` |
| Jinja2 macro names | snake_case | `{% macro investigation_card(inv) %}`, `{% macro status_badge(status) %}` |
| JavaScript functions | camelCase | `initSSE()`, `toggleSidebar()`, `copyToClipboard()` |
| sessionStorage keys | kebab-case | `sidebar-group-observe`, `sidebar-manual-override` |

### Structure Patterns

**Project Organization (existing, do not change):**

```
operator/
├── src/
│   ├── main.rs                  # Entry point, Axum routers
│   ├── controllers/             # K8s reconciliation loops
│   │   ├── investigation.rs
│   │   ├── source.rs
│   │   └── servicelevel.rs
│   ├── ingestion/               # :9090 ingestion handlers
│   ├── detection/               # EWMA anomaly detection
│   ├── slo/                     # ServiceLevel CRD processing
│   └── api/                     # :8080 REST handlers
├── tests/                       # Unit tests (wiremock)
└── Cargo.toml

investigator/
├── src/
│   ├── main.py                  # Entry point
│   ├── steps/                   # InvestigationStep implementations
│   ├── llm/                     # LiteLLM integration
│   ├── signals/                 # Prometheus/Loki query clients
│   └── kb/                      # Qdrant KB operations
├── tests/                       # Unit tests (pytest)
└── pyproject.toml

ui/
├── beeper_ui/
│   ├── app.py                   # Flask app factory
│   ├── routes/                  # Flask route blueprints
│   ├── templates/               # Jinja2 templates (102 files)
│   │   ├── base.html            # Base template (layout shell lives here)
│   │   ├── components/          # NEW — shared Jinja2 macro components
│   │   ├── investigations/      # Investigation list + detail
│   │   ├── knowledge/           # KB pages
│   │   ├── sources/             # Source list
│   │   └── ...                  # Other route templates
│   └── static/
│       ├── css/
│       │   ├── input.css        # Tailwind input (NEW)
│       │   └── tailwind.css     # Tailwind output (NEW, gitignored)
│       └── js/
│           └── sse.js           # SSE lifecycle manager (NEW)
├── tests/                       # Unit tests (pytest + respx)
└── pyproject.toml
```

**Canonical Component Macro Files (from UX Specification):**

The `ui/beeper_ui/templates/components/` directory is **NEW** — it does not exist in the current codebase and must be created as part of the layout shell migration (AD-3). Flat structure, 8 files, 12 macros:

| File | Macros Defined | UX Spec Reference |
|---|---|---|
| `components/layout.html` | Layout shell (sidebar + top bar + content area) | Component #1 |
| `components/sidebar.html` | `sidebar_group(label, icon, items, expanded, active_item)` | Component #2 |
| `components/cards.html` | `investigation_card(inv)` | Component #3 |
| `components/investigation.html` | `summary_header(inv)`, `investigation_step(step, is_first_evidence, order)`, `conclusion_block(inv)` | Components #4, #5, #6 |
| `components/status.html` | `status_badge(status)` | Component #7 |
| `components/diagnostic.html` | `metric_tile(label, value, status, trend)`, `ewma_progress(percentage, status)` | Components #8, #9 |
| `components/kb.html` | `kb_panel(entries, expanded)` | Component #10 |
| `components/empty.html` | `empty_state(title, description, icon)` | Component #11 |

Dev agents must use these exact filenames and macro signatures. The layout shell in `components/layout.html` is imported by `base.html`, not extended — `base.html` remains the single inheritance root.

**Where new files go:**

| New File Type | Location | Rationale |
|---|---|---|
| New Rust module | `operator/src/{domain}/` | Follow existing domain grouping |
| New Python step | `investigator/src/steps/` | Follow InvestigationStep protocol |
| New Flask route | `ui/beeper_ui/routes/` | One blueprint per route group |
| New Jinja2 page template | `ui/beeper_ui/templates/{route-group}/` | Group by route |
| New Jinja2 partial | `ui/beeper_ui/templates/{route-group}/_name.html` | Underscore prefix = partial |
| New Jinja2 component macro | `ui/beeper_ui/templates/components/{name}.html` | Shared components (NEW directory) |
| New JavaScript module | `ui/beeper_ui/static/js/` | Flat structure, one file per concern |
| New test (Rust) | `operator/tests/` | Or `#[cfg(test)] mod tests` in source |
| New test (Python) | `{component}/tests/` | Mirror source structure |

### Format Patterns

**API Response Formats:**

All API responses from the operator (:8080) follow these rules:

| Pattern | Rule | Example |
|---|---|---|
| **Success (single)** | Direct JSON object, no wrapper | `{"id": "inv-001", "service_name": "payment"}` |
| **Success (list)** | Direct JSON array, no wrapper | `[{"id": "inv-001"}, {"id": "inv-002"}]` |
| **Error** | RFC 7807 Problem Details | `{"type": "about:blank", "title": "Not Found", "status": 404, "detail": "Investigation inv-999 not found"}` |
| **Field names** | snake_case always | `service_name`, NOT `serviceName` |
| **Timestamps** | ISO 8601 UTC with Z suffix | `"2026-04-09T14:30:00Z"` |
| **IDs** | String, prefixed by resource type | `"inv-001"`, `"src-prometheus"` |
| **Booleans** | `true`/`false` | Never `1`/`0`, never `"true"` |
| **Nulls** | Omit field if null, or explicit `null` | Never empty string as null substitute |
| **HTTP status codes** | 200 (ok), 201 (created), 404 (not found), 500 (internal) | No 204 for successful responses — always return a body |

**SSE Event Format:**

SSE events from operator to UI follow this pattern:

```
event: investigation_step
data: {"investigation_id": "inv-001", "step": {...}, "order": 5}

event: investigation_status
data: {"investigation_id": "inv-001", "status": "Completed"}
```

| Field | Rule |
|---|---|
| Event names | snake_case, resource-scoped: `investigation_step`, `investigation_status`, `investigation_created` |
| Data payload | JSON object, same field naming as REST API |
| Step ordering | Integer `order` field, monotonically increasing per investigation |

**SSE is NOT HTMX:** SSE connections use the native browser `EventSource` API from JavaScript (`static/js/sse.js`). They are completely separate from the HTMX request/response cycle. Dev agents must NEVER use `hx-get`, `hx-trigger`, or any HTMX attribute to initiate or manage SSE connections. HTMX handles HTML fragment swaps; `EventSource` handles real-time event streaming. These are two independent systems that coexist on the same page.

### Communication Patterns

**Operator ↔ UI Communication:**

| Channel | Pattern | When to Use |
|---|---|---|
| REST (GET) | Request/response, JSON | Page loads, data fetching, REST backfill after SSE reconnect |
| SSE | Server-push, event stream | Real-time investigation step streaming, list update notifications |
| HTMX | HTML fragment responses | Partial page updates triggered by user interaction |

**HTMX Response Rules:**

| Trigger | Response Type | Content-Type |
|---|---|---|
| `hx-get` / `hx-post` | HTML fragment (not full page) | `text/html` |
| Regular Flask route | Full page (extends `base.html`) | `text/html` |
| API endpoint (`/api/v1/...`) | JSON | `application/json` |
| SSE endpoint | `text/event-stream` | Managed by `EventSource`, not HTMX |

Dev agents must NEVER return JSON from an `hx-get` target, HTML from an `/api/v1/` endpoint, or use HTMX attributes on SSE connections.

**Logging Patterns:**

| Component | Library | Format | Level Rule |
|---|---|---|---|
| Operator | `tracing` | Structured JSON (`tracing-subscriber`) | `info` for lifecycle events, `debug` for data flow, `warn` for recoverable errors, `error` for unrecoverable |
| Investigator | Python `logging` | Structured JSON | Same level semantics |
| UI | Python `logging` | Structured JSON | Same level semantics |

Log messages must include: `component`, `action`, and relevant IDs (`investigation_id`, `source_name`).

### Process Patterns

**Error Handling:**

| Component | Pattern | Example |
|---|---|---|
| **Operator (Rust)** | `thiserror` for typed errors, `anyhow` for context chaining | `#[error("Failed to decode protobuf: {0}")] DecodeError(#[from] prost::DecodeError)` |
| **Investigator (Python)** | Typed exceptions, caught at step boundary | `class SignalQueryError(InvestigationError)` |
| **UI (Flask)** | Flask error handlers return RFC 7807 for API, error template for HTML | `@app.errorhandler(404)` returns different content based on `Accept` header |
| **UI (HTMX)** | Errors swap into target element, never full-page error | `hx-swap="innerHTML"` with error HTML fragment |

**Loading & Empty State Rules:**

| Context | Pattern | Dev Agent Rule |
|---|---|---|
| Page load | Skeleton screens (gray pulsing blocks matching layout shape) | Never use a spinner. Always match the layout shape. |
| HTMX partial update | No loading indicator — swap is instant | Never add a spinner to an HTMX swap target |
| SSE streaming | Steps append progressively, no loading for individual steps | Never show "Loading step..." — steps appear when they arrive |
| Empty list | Explanatory text, not just blank space | Always include a message explaining why and what will happen |
| KB panel loading | "Checking knowledge base..." with pulse | Distinct from "0 entries" result — different emotional message |

**Tailwind / CSS Coexistence Rules:**

| Rule | Rationale |
|---|---|
| **Never mix Tailwind + custom CSS on the same HTML element** | Specificity conflicts are impossible to debug. One or the other. |
| **New components: Tailwind only** | Layout shell, sidebar, new macros — all Tailwind. |
| **Existing templates: custom CSS until migrated** | Content inside `{% block content %}` keeps existing CSS. |
| **Migration is per-template, not per-class** | When a template is migrated, ALL its styling converts to Tailwind. No half-Tailwind templates. |
| **`tailwind.css` is generated, never hand-edited** | It's a build output. Edit `input.css` for `@apply` directives or custom Tailwind config. |
| **Always use semantic design tokens, never arbitrary values** | Write `bg-surface-base`, NEVER `bg-[#0f0f1a]`. Token names carry semantic meaning. Arbitrary values bypass the design system. |

**Tailwind Design Tokens (must be configured in `tailwind.config.js`):**

These tokens are defined in the UX Specification and must be registered as Tailwind theme extensions. Dev agents must use these token names in all Tailwind classes — never raw hex values.

```javascript
// ui/tailwind.config.js — theme.extend.colors
colors: {
  'surface-base': '#0f0f1a',
  'surface-raised': '#1a1a2e',
  'surface-overlay': '#252540',
  'primary': '#6366f1',
  'primary-hover': '#818cf8',
  'status-healthy': '#22c55e',
  'status-warning': '#f59e0b',
  'status-critical': '#ef4444',
  'status-muted': '#6b7280',
  'text-primary': '#f8fafc',
  'text-secondary': '#94a3b8',
  'text-muted': '#64748b',
}
```

**Usage examples:**
- `bg-surface-base` (page background) — NOT `bg-[#0f0f1a]`
- `text-primary` (headings) — NOT `text-[#f8fafc]`
- `border-status-healthy` (active investigation) — NOT `border-[#22c55e]`
- `ring-primary` (focus ring) — NOT `ring-[#6366f1]`

**Breakpoint tokens (also in `tailwind.config.js`):**

```javascript
screens: {
  'sm': '768px',
  'lg': '1200px',
  'xl': '1920px',
}
```

### Testing Patterns

**Unit tests vs. Integration tests — critical distinction:**

| Test Type | Mandatory? | Enforced By | What It Covers |
|---|---|---|---|
| **Unit tests** | **YES — mandatory for all new code** | CI (GitHub Actions) | Individual functions, struct serialization, route handlers, template rendering |
| **Integration tests** | Manual, per AD-8 protocol | Developer runs `curl`/`kubectl` | End-to-end pipeline: OTEL → operator → investigator → UI |

Dev agents must NEVER skip unit tests because "AD-8 says manual verification." AD-8 covers pipeline integration verification. Unit tests cover individual code changes. These are different things.

**Minimum test expectations per component type:**

| Component | New Code | Minimum Test |
|---|---|---|
| **Operator (Rust)** | New struct fields | Test serialization: `serde_json::to_value(&stats)` → verify field names and types |
| **Operator (Rust)** | New/modified API handler | Test response: `wiremock` mock → handler → assert status code + response shape |
| **Operator (Rust)** | New detection logic | Test behavior: input metric → expected detection output |
| **Investigator (Python)** | New/modified step | Test step execution: mock external calls → assert step result structure |
| **Investigator (Python)** | New query logic | Test query construction: assert PromQL/LogQL string is correct |
| **UI (Python)** | New Flask route | Test response: `test_client.get()` → assert status 200 + correct content type |
| **UI (Python)** | New Jinja2 macro | Test rendering: `render_template_string("{% from 'components/x.html' import macro %}{{ macro(data) }}")` with sample data → assert no error + expected HTML structure |
| **UI (Python)** | Modified template | Test rendering: existing test still passes + new elements present |

**Anti-pattern:** Writing `assert True` or trivial tests that don't verify actual behavior. Every test must assert something meaningful about the code it covers.

### Enforcement Guidelines

**All AI Agents MUST:**

1. Run `cargo fmt` and `cargo clippy` before considering any Rust change complete
2. Run `ruff check` and `mypy` before considering any Python change complete
3. Follow the existing test co-location pattern — tests in `tests/` directory, not co-located
4. Use snake_case for ALL JSON fields, API responses, and database payloads — no exceptions
5. Return RFC 7807 errors from all `/api/v1/` endpoints — no custom error shapes
6. Use Jinja2 block inheritance — never duplicate layout HTML across templates
7. Prefix partial templates with `_` — full pages never start with underscore
8. Keep SSE event names in snake_case, resource-scoped format
9. Never introduce new dependencies without explicit justification in the story
10. Never modify the "Do Not Decide" items from the architectural decisions
11. Use Tailwind semantic tokens (`bg-surface-base`) — never arbitrary values (`bg-[#hex]`)
12. Use canonical component filenames from the UX spec — never invent new macro filenames
13. Write meaningful unit tests for all new code paths — `assert True` is not a test
14. Never use HTMX attributes for SSE connections — `EventSource` is JavaScript, not HTMX

**Pattern Verification Checklist (for code review):**

- [ ] All new Rust structs have `#[serde(rename_all = "snake_case")]`
- [ ] All new API endpoints return RFC 7807 on error
- [ ] All new templates extend `base.html`
- [ ] All new partials are prefixed with `_`
- [ ] All new component macros use canonical filenames from UX spec
- [ ] All new Tailwind usage uses semantic tokens, no arbitrary values
- [ ] All new Tailwind components — no mixing with custom CSS on same element
- [ ] All new JavaScript uses camelCase function names
- [ ] All sessionStorage keys use kebab-case
- [ ] SSE managed by `EventSource` in `sse.js`, not by HTMX attributes
- [ ] No new dependencies added without story justification
- [ ] Unit tests exist for all new code paths with meaningful assertions
- [ ] Tests follow minimum expectations per component type

## Project Structure & Boundaries

### Complete Project Directory Structure

Existing files are unmarked. **NEW** = created by this PRD. **(MODIFY — FR#/AD#)** = changed by this PRD with the driving requirement noted. Dev agents must not create files outside this structure without explicit story justification.

```
beeper/
├── .github/
│   └── workflows/               # CI/CD — existing, no changes
│       ├── operator.yml
│       ├── investigator.yml
│       ├── ui.yml
│       └── helm.yml
├── operator/
│   ├── Cargo.toml
│   ├── build.rs                 # Protobuf compilation (prost-build)
│   ├── proto/
│   │   └── prometheus.proto     # (MODIFY — AD-1, FR1: may need schema update)
│   ├── src/
│   │   ├── main.rs              # Entry point: :8080 + :9090 servers (MODIFY — FR9: register stats fields)
│   │   ├── api.rs               # :8080 REST handlers — monolithic (MODIFY — FR9, AD-2: detection stats fields)
│   │   ├── health.rs            # Health/readiness probes
│   │   ├── investigator_job.rs  # K8s Job spawning for investigations
│   │   ├── lib.rs               # Library exports
│   │   ├── llm.rs               # LLM health check client
│   │   ├── controllers/
│   │   │   ├── mod.rs
│   │   │   ├── investigation.rs # Investigation CRD reconciler (MODIFY — FR10-13: verify lifecycle)
│   │   │   ├── source.rs        # Source CRD reconciler
│   │   │   ├── servicelevel.rs  # ServiceLevel CRD reconciler (MODIFY — FR20-21: verify wiring)
│   │   │   ├── notification_channel.rs  # Out of scope — do not modify
│   │   │   └── repository.rs    # Out of scope — do not modify
│   │   ├── crds/
│   │   │   ├── mod.rs
│   │   │   ├── investigation.rs # Investigation CRD type definition
│   │   │   ├── source.rs        # Source CRD type definition
│   │   │   ├── servicelevel.rs  # ServiceLevel CRD type definition
│   │   │   ├── notification_channel.rs  # Out of scope
│   │   │   └── repository.rs    # Out of scope
│   │   ├── ingestion/
│   │   │   ├── mod.rs           # :9090 server setup (MODIFY — FR1: verify protobuf decoding)
│   │   │   ├── prometheus.rs    # Prometheus remote write handler (MODIFY — FR1: snappy+protobuf fix)
│   │   │   ├── loki.rs          # Loki push handler (MODIFY — FR2: verify JSON acceptance)
│   │   │   ├── otlp.rs          # OTLP handler (MODIFY — FR1: verify encoding)
│   │   │   └── buffer.rs        # Ingestion buffer (MODIFY — FR3: verify stats exposure)
│   │   ├── detection/
│   │   │   ├── mod.rs           # Detection engine orchestration
│   │   │   ├── ewma.rs          # EWMA anomaly detector (MODIFY — FR5, FR9: expose warmup stats)
│   │   │   ├── metrics.rs       # Metric detection pipeline (MODIFY — FR7: verify threshold)
│   │   │   ├── logs.rs          # Log pattern detector (MODIFY — FR6: verify pattern matching)
│   │   │   ├── consumer.rs      # Buffer consumer
│   │   │   └── types.rs         # Detection types
│   │   ├── slo/
│   │   │   ├── mod.rs           # SLO processing (MODIFY — FR20-21: verify CRD reads)
│   │   │   ├── budget.rs        # Error budget calculation
│   │   │   ├── burn_rate.rs     # Burn rate calculation
│   │   │   ├── calculator.rs    # SLO calculation
│   │   │   └── impact.rs        # Impact assessment
│   │   ├── sources/
│   │   │   ├── mod.rs
│   │   │   ├── prometheus.rs    # Prometheus health check (FR4: per-source health)
│   │   │   └── loki.rs          # Loki health check (FR4: per-source health)
│   │   └── notifications/       # Out of scope — do not modify
│   │       ├── mod.rs
│   │       ├── outbox.rs
│   │       └── router.rs
│   └── tests/                   # (MODIFY — FR9, AD-2: add stats serialization tests)
├── investigator/
│   ├── pyproject.toml
│   ├── beeper_investigator/     # Python package
│   │   ├── main.py              # Entry point (MODIFY — FR14-19: verify signal passing)
│   │   ├── agent.py             # Investigation agent orchestrator
│   │   ├── steps/
│   │   │   ├── metric_query.py  # Prometheus PromQL (MODIFY — FR14: verify query execution)
│   │   │   ├── signal_correlation.py  # Signal correlation (MODIFY — FR16: verify correlation)
│   │   │   ├── kb_query.py      # Qdrant KB search (FR17: verify KB results stored)
│   │   │   ├── rca_hypothesis.py # Root cause hypothesis (MODIFY — FR18: verify LLM receives signals)
│   │   │   ├── resolution_recommendations.py # (MODIFY — FR19: verify specific recommendations)
│   │   │   ├── impact_assessment.py
│   │   │   ├── investigation_documentation.py
│   │   │   ├── deploy_correlation.py
│   │   │   ├── service_topology.py
│   │   │   └── change_event_correlation.py
│   │   ├── llm/
│   │   │   ├── client.py        # LiteLLM wrapper
│   │   │   └── prompts.py       # Prompt templates (MODIFY — FR18-19: specific output)
│   │   ├── sources/
│   │   │   ├── prometheus.py    # PromQL query client (MODIFY — FR14: verify FQDN resolution)
│   │   │   └── loki.py          # LogQL query client (MODIFY — FR15: verify FQDN resolution)
│   │   ├── kb/
│   │   │   ├── client.py        # Qdrant operations (FR17, FR30)
│   │   │   └── schemas.py       # KB data schemas
│   │   ├── k8s/
│   │   │   ├── __init__.py
│   │   │   ├── status.py        # InvestigationStatusUpdater — patches CRD directly
│   │   │   └── repository.py    # K8s API client helpers
│   │   └── remediation/         # Out of scope — do not modify
│   └── tests/
│       ├── test_main.py
│       ├── test_agent.py
│       ├── test_sources.py      # (MODIFY — FR14-15: verify query tests)
│       └── ...
├── ui/
│   ├── pyproject.toml
│   ├── tailwind.config.js       # **NEW** (AD-7: Tailwind theme + content paths)
│   ├── beeper_ui/
│   │   ├── app.py               # Flask app factory
│   │   ├── routes/
│   │   │   ├── investigations.py # (MODIFY — FR22-27: SSE proxy, KB panel data)
│   │   │   ├── knowledge.py     # (MODIFY — FR28-31: verify CRUD)
│   │   │   ├── sources.py
│   │   │   ├── metrics.py
│   │   │   ├── spending.py
│   │   │   └── health.py        # (MODIFY — FR32-35: diagnostic dashboard data)
│   │   ├── templates/
│   │   │   ├── base.html        # (MODIFY — AD-3: rewrite with layout shell)
│   │   │   ├── components/      # **NEW** directory (AD-3)
│   │   │   │   ├── layout.html  # **NEW** (AD-3: layout shell macro)
│   │   │   │   ├── sidebar.html # **NEW** (AD-3, FR40-43: sidebar group macro)
│   │   │   │   ├── cards.html   # **NEW** (FR22: investigation card macro)
│   │   │   │   ├── investigation.html # **NEW** (FR23-25: summary, step, conclusion macros)
│   │   │   │   ├── status.html  # **NEW** (FR22: status badge macro)
│   │   │   │   ├── diagnostic.html # **NEW** (FR33: metric tile, EWMA progress macros)
│   │   │   │   ├── kb.html      # **NEW** (FR26: related KB panel macro)
│   │   │   │   └── empty.html   # **NEW** (FR22: empty state macro)
│   │   │   ├── investigations/
│   │   │   │   ├── list.html    # (MODIFY — FR22: use investigation_card macro)
│   │   │   │   ├── detail.html  # (MODIFY — FR23-27, AD-6: sidebar_state, KB panel, SSE)
│   │   │   │   └── _*.html      # Partials (existing, may need MODIFY for HTMX targets)
│   │   │   ├── knowledge/       # (MODIFY — FR28-31: verify CRUD templates)
│   │   │   ├── health/
│   │   │   │   ├── status.html  # (MODIFY — FR32-35: add diagnostic tiles)
│   │   │   │   └── _status_content.html # (MODIFY — FR33: detection stats display)
│   │   │   ├── sources/         # (MODIFY — FR4: per-source health display)
│   │   │   ├── slo/             # (MODIFY — FR21: SLO dashboard)
│   │   │   └── ...              # Other existing route templates
│   │   └── static/
│   │       ├── css/
│   │       │   ├── style.css    # Existing custom CSS (~3,900 lines) — do not modify
│   │       │   ├── input.css    # **NEW** (AD-7: Tailwind input directives)
│   │       │   └── tailwind.css # **NEW** (AD-7: generated output, gitignored)
│   │       └── js/
│   │           └── sse.js       # **NEW** (AD-4, FR23: SSE lifecycle manager)
│   └── tests/
│       ├── routes/
│       ├── templates/           # (MODIFY: add component macro rendering tests)
│       └── conftest.py
├── helm/
│   └── beeper/
│       ├── Chart.yaml
│       ├── values.yaml          # (MODIFY — Qdrant version bump to v1.15.0)
│       ├── templates/
│       │   ├── operator-deployment.yaml # (MODIFY — FR36: verify image + env)
│       │   ├── investigator-job-template.yaml
│       │   ├── ui-deployment.yaml
│       │   ├── qdrant-statefulset.yaml
│       │   └── ...
│       └── crds/
├── demo/
│   ├── README.md                # (MODIFY — FR36: updated demo instructions)
│   ├── otel-demo-values.yaml    # (MODIFY — FR37: OTEL Collector → operator routing)
│   └── servicelevel-crds/       # ServiceLevel CRD manifests (MODIFY — FR20: verify)
├── scripts/                     # Setup and utility scripts
├── docs/                        # Project documentation (reference only — do not modify)
├── Makefile                     # (MODIFY — AD-7: tailwind targets, AD-8: test-pipeline target, FR36-39: demo targets)
├── kind-config.yaml             # (MODIFY — FR36: verify port mappings)
├── docker-compose.yml           # Local Qdrant
└── .gitignore                   # (MODIFY — add tailwind.css output)
```

### New File Creation Mapping

Every new file is assigned to the AD/FR that creates it. Story-planning agents use this to know which story owns file creation.

| New File | Created By | Story Scope |
|---|---|---|
| `ui/tailwind.config.js` | AD-7 | Tailwind build pipeline setup |
| `ui/beeper_ui/static/css/input.css` | AD-7 | Tailwind build pipeline setup |
| `ui/beeper_ui/static/css/tailwind.css` | AD-7 | Generated output (gitignored) |
| `ui/beeper_ui/templates/components/` (directory) | AD-3 | Layout shell migration |
| `ui/beeper_ui/templates/components/layout.html` | AD-3 | Layout shell migration |
| `ui/beeper_ui/templates/components/sidebar.html` | AD-3, FR40-43 | Layout shell migration |
| `ui/beeper_ui/templates/components/cards.html` | FR22 | Investigation list redesign |
| `ui/beeper_ui/templates/components/investigation.html` | FR23-25 | Investigation detail redesign |
| `ui/beeper_ui/templates/components/status.html` | FR22 | Investigation list redesign |
| `ui/beeper_ui/templates/components/diagnostic.html` | FR33 | Diagnostic dashboard |
| `ui/beeper_ui/templates/components/kb.html` | FR26 | Related KB panel |
| `ui/beeper_ui/templates/components/empty.html` | FR22 | Investigation list redesign |
| `ui/beeper_ui/static/js/sse.js` | AD-4, FR23 | SSE lifecycle manager |

### Architectural Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│                        K8s Cluster                            │
│                                                               │
│  OTEL Collector ─── :9090 ──→ ┌──────────────────────┐       │
│  (prometheusremotewrite,       │  beeper-operator     │       │
│   loki push)                   │                      │       │
│                                │  :9090 Ingestion API │       │
│                                │  (protobuf, JSON)    │       │
│                                │                      │       │
│                                │  :8080 Management API│       │
│                                │  (REST JSON, SSE)    │       │
│                                └──────┬───────────────┘       │
│                                       │                       │
│                                       │ spawns K8s Job        │
│                                       ▼                       │
│                                ┌──────────────────────┐       │
│  Prometheus ◄──── PromQL ──── │  investigator Job    │       │
│  Loki ◄────────── LogQL ──── │  (Python, ephemeral) │       │
│  Qdrant ◄──────── HTTP ───── │                      │       │
│  LLM API ◄─────── LiteLLM ── │                      │       │
│  K8s API ◄──── PATCH CRD ─── │  (status updater)    │       │
│                                └──────────────────────┘       │
│                                                               │
│  ┌──────────────────────┐                                     │
│  │  beeper-ui            │                                     │
│  │  :5000 Flask          │──── REST ──→ operator :8080        │
│  │  (HTML, SSE proxy)    │──── SSE ──→ operator :8080        │
│  │                        │──── HTTP ──→ Qdrant (KB direct)   │
│  └──────────────────────┘                                     │
│                                                               │
│  User Browser ◄──── :5000 (port-forward) ──── beeper-ui      │
└─────────────────────────────────────────────────────────────┘
```

**Investigator → CRD Write Mechanism (clarified):**

The investigator has **direct K8s API access** via `InvestigationStatusUpdater` (`beeper_investigator/k8s/status.py`). It PATCHes the Investigation CRD's status subresource directly — it does NOT write status to Qdrant for the operator to read. The write paths are:

| Write Target | Mechanism | What's Written |
|---|---|---|
| Investigation CRD status | K8s API PATCH (via `kubernetes` Python client) | Progress messages, final status (Completed/Failed) |
| Qdrant `investigations` collection | HTTP POST (via Qdrant client) | Investigation results, step data, findings, KB matches |

The operator watches the CRD status field changes and emits SSE events to the UI. The UI reads detailed step data from the operator API, which proxies to Qdrant.

**Boundary Rules:**

| Boundary | Rule | Violation Example |
|---|---|---|
| Operator → Investigator | **No direct communication.** Operator spawns Job, watches CRD status. | Operator calling investigator HTTP endpoint |
| Investigator → Operator | **No direct communication.** Investigator patches CRD status + writes to Qdrant. | Investigator calling operator :8080 API |
| UI → Operator | **REST + SSE only via :8080.** No direct Rust function calls. | UI importing operator Rust code |
| UI → Qdrant | **Direct HTTP for KB reads only.** Investigation data comes from operator API. | UI writing to Qdrant |
| Browser → UI | **HTTP + SSE via :5000 only.** All operator data proxied through Flask. | Browser JavaScript calling operator :8080 directly |
| Browser → Operator | **Not allowed in application code.** Port-forward to :8080 is for demo `curl` debugging only — UI code must never reference :8080. | `fetch('http://localhost:8080/api/v1/...')` in JavaScript |

### Requirements to Structure Mapping (Exhaustive FR → File)

**Every FR mapped to its primary implementation file:**

| FR | Description | Primary File(s) | Test File(s) |
|---|---|---|---|
| FR1 | Accept Prometheus remote write | `operator/src/ingestion/prometheus.rs`, `otlp.rs` | `operator/tests/` |
| FR2 | Accept Loki log push | `operator/src/ingestion/loki.rs` | `operator/tests/` |
| FR3 | Buffer telemetry + expose ingestion stats | `operator/src/ingestion/buffer.rs`, `operator/src/api.rs` | `operator/tests/` |
| FR4 | Per-source ingestion health | `operator/src/api.rs` (`/api/v1/health/components`), `operator/src/sources/prometheus.rs`, `sources/loki.rs` | `operator/tests/` |
| FR5 | EWMA anomaly detection on metrics | `operator/src/detection/ewma.rs` | `operator/tests/` |
| FR6 | Log pattern anomaly detection | `operator/src/detection/logs.rs` | `operator/tests/` |
| FR7 | Configurable detection thresholds | `operator/src/detection/metrics.rs`, `types.rs` | `operator/tests/` |
| FR8 | Auto-create Investigation CRD | `operator/src/controllers/investigation.rs` | `operator/tests/` |
| FR9 | Expose detection stats via API | `operator/src/detection/ewma.rs` → `operator/src/api.rs` | `operator/tests/` |
| FR10 | Investigation lifecycle (Pending→Running→…) | `operator/src/controllers/investigation.rs`, `crds/investigation.rs` | `operator/tests/` |
| FR11 | Spawn investigator K8s Job | `operator/src/investigator_job.rs` | `operator/tests/` |
| FR12 | Track investigation failure count | `operator/src/controllers/investigation.rs` | `operator/tests/` |
| FR13 | Clean up completed Jobs | `operator/src/controllers/investigation.rs` | `operator/tests/` |
| FR14 | Query Prometheus for metrics | `investigator/beeper_investigator/sources/prometheus.py`, `steps/metric_query.py` | `investigator/tests/test_sources.py` |
| FR15 | Query Loki for logs | `investigator/beeper_investigator/sources/loki.py` | `investigator/tests/test_sources.py` |
| FR16 | Correlate signals | `investigator/beeper_investigator/steps/signal_correlation.py` | `investigator/tests/test_signal_correlation.py` |
| FR17 | Query KB for related knowledge | `investigator/beeper_investigator/steps/kb_query.py` | `investigator/tests/test_kb_query.py` |
| FR18 | Generate root cause hypothesis via LLM | `investigator/beeper_investigator/steps/rca_hypothesis.py`, `llm/prompts.py` | `investigator/tests/test_rca_hypothesis.py` |
| FR19 | Generate resolution recommendations | `investigator/beeper_investigator/steps/resolution_recommendations.py` | `investigator/tests/test_resolution_recommendations.py` |
| FR20 | Read ServiceLevel CRDs | `operator/src/controllers/servicelevel.rs`, `crds/servicelevel.rs` | `operator/tests/` |
| FR21 | Display SLO dashboard | `ui/beeper_ui/routes/` (slo), `templates/slo/` | `ui/tests/` |
| FR22 | Investigation list with cards | `ui/beeper_ui/routes/investigations.py`, `templates/investigations/list.html`, `templates/components/cards.html` | `ui/tests/` |
| FR23 | Progressive SSE rendering | `ui/beeper_ui/routes/investigations.py`, `templates/investigations/detail.html`, `static/js/sse.js` | `ui/tests/` |
| FR24 | Inline evidence display | `templates/components/investigation.html` (`investigation_step` macro) | `ui/tests/templates/` |
| FR25 | Investigation conclusion block | `templates/components/investigation.html` (`conclusion_block` macro) | `ui/tests/templates/` |
| FR26 | Related KB panel | `templates/components/kb.html`, `ui/beeper_ui/routes/investigations.py` | `ui/tests/` |
| FR27 | Investigation summary header | `templates/components/investigation.html` (`summary_header` macro) | `ui/tests/templates/` |
| FR28 | KB entry list with search | `ui/beeper_ui/routes/knowledge.py`, `templates/knowledge/index.html` | `ui/tests/` |
| FR29 | KB entry detail + history | `templates/knowledge/entry.html`, `history.html` | `ui/tests/` |
| FR30 | KB entry edit | `templates/knowledge/edit.html` | `ui/tests/` |
| FR31 | KB entry import | `templates/knowledge/import.html` | `ui/tests/` |
| FR32 | System health overview | `ui/beeper_ui/routes/health.py`, `templates/health/status.html` | `ui/tests/` |
| FR33 | Detection stats diagnostic dashboard | `templates/health/_status_content.html`, `templates/components/diagnostic.html` | `ui/tests/` |
| FR34 | Source connectivity status | `templates/sources/list.html` | `ui/tests/` |
| FR35 | LLM spending display | `templates/spending/spending.html` | `ui/tests/` |
| FR36 | Demo deploy via Makefile | `Makefile`, `demo/otel-demo-values.yaml` | Manual (AD-8) |
| FR37 | Demo fault injection | `Makefile` (`demo-fault` target) | Manual (AD-8) |
| FR38 | Demo recovery | `Makefile` (`demo-recover` target) | Manual (AD-8) |
| FR39 | Demo 3/3 repeatability | `Makefile`, `demo/README.md` | Manual (AD-8) |
| FR40 | Sidebar navigation | `templates/base.html`, `templates/components/sidebar.html` | `ui/tests/templates/` |
| FR41 | Sidebar groups (Observe/Learn/Manage) | `templates/components/sidebar.html` | `ui/tests/templates/` |
| FR42 | Sidebar collapse/expand | `templates/components/sidebar.html`, `static/js/sse.js` (sidebar toggle) | `ui/tests/` |
| FR43 | Sidebar active state | `templates/components/sidebar.html` | `ui/tests/templates/` |
| FR44 | Route-driven sidebar collapse | `templates/investigations/detail.html` (`{% block sidebar_state %}`) | `ui/tests/templates/` |

### Integration Points

**Internal Communication:**

| From | To | Protocol | Data Format | Direction |
|---|---|---|---|---|
| OTEL Collector | Operator :9090 | HTTP POST | Snappy+protobuf (metrics), JSON (logs) | Inbound |
| Operator | K8s API | kube-rs client | CRD YAML | Bidirectional |
| Operator | Investigator | K8s Job spawn | Job manifest YAML | Outbound (fire-and-forget) |
| Investigator | K8s API | kubernetes Python client | PATCH CRD status subresource | Outbound |
| Investigator | Prometheus | HTTP GET | PromQL → JSON response | Outbound |
| Investigator | Loki | HTTP GET | LogQL → JSON response | Outbound |
| Investigator | Qdrant | HTTP POST/GET | JSON | Bidirectional |
| Investigator | LLM | HTTP POST (LiteLLM) | JSON (prompt → completion) | Outbound |
| UI | Operator :8080 | HTTP GET + SSE | JSON (REST), text/event-stream (SSE) | Outbound |
| UI | Qdrant | HTTP GET | JSON (KB reads) | Outbound |
| Browser | UI :5000 | HTTP + SSE | HTML (pages), HTML fragments (HTMX), text/event-stream (SSE) | Bidirectional |

**External Integrations:**

| Service | Component | Protocol | Configuration |
|---|---|---|---|
| LLM Provider (Anthropic) | Investigator | HTTPS via LiteLLM | K8s Secret → env var `ANTHROPIC_API_KEY` |
| OTEL Astronomy Shop | Demo workload | N/A (just runs) | `demo/otel-demo-values.yaml` |
| Container Registry (ghcr.io) | CI/CD | Docker push | GitHub Actions secrets |

**Data Flow (end-to-end investigation):**

```
OTEL Collector
  │ POST /api/v1/write (protobuf)
  │ POST /loki/api/v1/push (JSON)
  ▼
Operator Ingestion (:9090)
  │ buffers → detection engine
  ▼
EWMA Detector
  │ threshold crossed → create Investigation CRD
  ▼
K8s API (CRD created)
  │ operator watches → spawns Job
  ▼
Investigator Job
  │ queries Prometheus, Loki, Qdrant KB
  │ sends signals to LLM
  │ PATCHes Investigation CRD status (via K8s API)
  │ writes results to Qdrant investigations collection
  ▼
Operator (watches CRD status change)
  │ emits SSE event to connected UI clients
  ▼
UI (receives SSE)
  │ fetches investigation detail from operator API
  │ operator API reads from Qdrant + CRD
  │ renders investigation steps progressively
  ▼
Browser (user sees investigation)
```

### Development Workflow Integration

**Development Commands (Makefile):**

| Target | Purpose | Changed? |
|---|---|---|
| `make build` | Build all Docker images | Existing |
| `make test` | Run all unit tests (cargo + pytest) | Existing |
| `make deploy` | Deploy to kind cluster | Existing |
| `make demo-deploy` | Deploy OTEL demo | Existing (MODIFY config) |
| `make demo-fault FAULT=X` | Inject named fault | Existing |
| `make demo-recover` | Recover from fault | Existing |
| `make demo-ui` | Port-forward UI + operator + demo | Existing |
| `make tailwind-watch` | **NEW** (AD-7) — Tailwind CLI watch mode for development |
| `make tailwind-build` | **NEW** (AD-7) — Tailwind CSS production minified build |
| `make test-pipeline` | **NEW** (AD-8) — Run all 5 checkpoint verifications sequentially. Requires running kind cluster with OTEL demo deployed. Outputs pass/fail per checkpoint: (1) ingestion stats > 0, (2) investigation CRD exists, (3) investigator logs show query results, (4) investigation findings reference specific services, (5) ServiceLevel CRDs processed. Fails on first checkpoint failure with diagnostic output. |

**Build Process:**

| Component | Build Command | Output |
|---|---|---|
| Operator | `docker build -f operator/Dockerfile .` | `ghcr.io/ethompsy/beeper-operator:latest` |
| Investigator | `docker build -f investigator/Dockerfile .` | `ghcr.io/ethompsy/beeper-investigator:latest` |
| UI | `docker build -f ui/Dockerfile .` (includes Tailwind build stage) | `ghcr.io/ethompsy/beeper-ui:latest` |
| Helm | `helm package helm/beeper` | `beeper-0.1.0.tgz` |

---

## Architecture Validation Results

### Coherence Validation

**Decision Compatibility — PASS (7 checks):**

| Decision Pair | Compatibility | Notes |
|---|---|---|
| AD-1 (OTEL protobuf) ↔ AD-8 (integration test) | Compatible | Integration test checkpoint 1 validates ingestion that AD-1 fixes |
| AD-2 (detection stats) ↔ AD-4 (SSE reconnection) | Compatible | Stats API is REST-only, SSE carries investigation events — no overlap |
| AD-3 (layout shell) ↔ AD-7 (Tailwind) | Compatible | Layout shell uses Jinja2 blocks; Tailwind provides utility classes. AD-7 build must complete before AD-3 templates reference Tailwind classes |
| AD-4 (SSE reconnection) ↔ AD-5 (KB panel query) | Compatible | SSE carries investigation events; KB panel uses REST query. Independent data paths |
| AD-5 (KB panel query) ↔ AD-6 (sidebar state) | Compatible | KB panel is page content; sidebar is navigation. No interaction |
| AD-6 (sidebar state) ↔ AD-3 (layout shell) | Compatible | Sidebar state is a Jinja2 block within the layout shell. AD-3 enables AD-6 |
| AD-7 (Tailwind) ↔ AD-1 (OTEL protobuf) | Independent | Different components (UI vs Operator), zero coupling |

**Merge Conflict Hotspot — FLAGGED:**

`operator/src/api.rs` is a monolithic file touched by 5+ FRs (FR2, FR4, FR9, FR33, FR34). Stories modifying this file must be sequenced within a single epic or explicitly coordinated to avoid merge conflicts. The sprint plan must not parallelize stories that both modify `api.rs`.

**Pattern Consistency — PASS:**

All 14 enforcement rules are internally consistent. No rule contradicts another. Rule 14 (never use HTMX for SSE) reinforces Rule 8 (SSE event naming) — both address the same subsystem with complementary constraints.

**Structure Alignment — PASS:**

Every NEW file in the project structure maps to at least one FR and one AD. Every MODIFY annotation references specific FRs driving the change. No orphan files.

### NFR Constraint Additions

Two new measurable constraints identified during validation and added to the architecture:

| NFR | Constraint | Source |
|---|---|---|
| NFR-P2 (UI responsiveness) | SSE `retry` field must be set to ≤ 3000ms in operator's SSE endpoint response headers | AD-4 SSE reconnection contract |
| NFR-P3 (UI transitions) | Sidebar collapse/expand transition must use exactly `width 200ms ease-in-out` | AD-6 + UX spec Section 7.3 |

### Requirements Coverage

**Functional Requirements: 44/44 (100%)**

| FR Range | Category | Coverage | Key Architectural Mapping |
|---|---|---|---|
| FR1-4 | Telemetry Ingestion | 4/4 | AD-1 → `operator/src/ingestion/` |
| FR5-9 | Anomaly Detection | 5/5 | AD-2 → `operator/src/detection/`, `operator/src/api.rs` |
| FR10-13 | Investigation Lifecycle | 4/4 | Existing CRD machinery, verify-only |
| FR14-19 | Investigation Execution | 6/6 | `investigator/beeper_investigator/` fix-in-place |
| FR20-21 | SLO Integration | 2/2 | `operator/src/slo/`, `operator/src/controllers/servicelevel.rs` |
| FR22-27 | Investigation Display | 6/6 | AD-4, AD-5 → `ui/beeper_ui/templates/investigations/` |
| FR28-31 | Knowledge Base | 4/4 | Existing KB CRUD, Related KB panel (AD-5) |
| FR32-35 | System Health | 4/4 | AD-2 → `operator/src/api.rs`, `ui/beeper_ui/templates/diagnostics/` |
| FR36-39 | Demo Environment | 4/4 | AD-8 → `Makefile`, `demo/`, `helm/` |
| FR40-44 | Navigation & Layout | 5/5 | AD-3, AD-6, AD-7 → `ui/beeper_ui/templates/components/`, `base.html` |

**Non-Functional Requirements: 17/17 (100%) + 2 new constraints**

All 17 NFRs from PRD mapped to architectural decisions or existing infrastructure. Two additional measurable constraints added during validation (see NFR Constraint Additions above).

### User Journey Validation

**5/5 User Journeys — PASS**

**UJ1: First-Time Exploration**
1. User opens Beeper UI → FR40 (responsive layout), AD-3 (layout shell), AD-7 (Tailwind)
2. Sidebar shows navigation → FR41-43 (sidebar sections), AD-6 (sidebar state)
3. Clicks "Diagnostics" → FR32-34 (system health), AD-2 (detection stats)
4. Sees detection stats with EWMA warmup → FR9 (warmup stats), AD-2 (stats API)
5. Returns to dashboard → FR40 (layout shell), existing dashboard route

**UJ2: Live Investigation Monitoring**
1. Anomaly triggers investigation → FR5-8 (detection), FR10-11 (lifecycle)
2. SSE notification arrives → FR22 (SSE streaming), AD-4 (reconnection contract)
3. User clicks investigation → FR23-25 (progressive rendering, inline evidence)
4. Steps render progressively → FR23 (step rendering), AD-4 (REST backfill on reconnect)
5. Related KB entries shown → FR26 (KB panel), AD-5 (query pattern)

**UJ3: Knowledge Base Research**
1. User navigates to KB → FR41 (sidebar), AD-6 (sidebar state)
2. Views KB entries → FR28-29 (KB listing, detail)
3. Edits an entry → FR30 (KB editing), existing Qdrant CRUD
4. Views entry versions → FR31 (KB versioning), `knowledge_versions` collection

**UJ4: Demo Deployment & Fault Injection**
1. Runs `make deploy` → FR36 (one-command deploy)
2. Runs `make demo-deploy` → FR37 (OTEL demo), AD-1 (OTEL compatibility)
3. Runs `make demo-fault FAULT=high-cpu` → FR38 (fault injection)
4. Watches investigation trigger → UJ2 flow above
5. Runs `make demo-recover` → FR39 (recovery)

**UJ5: Pipeline Verification**
1. Runs `make test-pipeline` → FR36-39 (demo), AD-8 (integration test)
2. Checkpoint 1: ingestion stats > 0 → FR1-2 (telemetry), AD-1
3. Checkpoint 2: Investigation CRD exists → FR10-11 (lifecycle)
4. Checkpoint 3: Investigator logs show queries → FR14-16 (execution)
5. Checkpoint 4: Findings reference services → FR17-19 (RCA)
6. Checkpoint 5: ServiceLevel CRDs processed → FR20-21 (SLO)

### Implementation Readiness

**Decisions — PASS:**
All 8 architectural decisions (AD-1 through AD-8) have: rationale, alternatives considered, implementation guidance, and dependency mapping. No decision references undefined concepts.

**Structure — PASS:**
Complete file tree with NEW/MODIFY annotations. Every new file maps to a driving FR and AD. Directory creation paths verified against actual codebase structure.

**Patterns — PASS:**
14 enforcement rules cover naming, structure, format, communication, and process. Canonical component macro list verified (8 files, 12 macros). Test expectations defined per component type.

### Gap Analysis

**Critical Gaps: 0**

**Important Gaps (acknowledged, not blocking): 2**

1. **Qdrant version discrepancy**: Local dev uses v1.15.0 (Docker Compose), Helm deploys v1.12.0. Unlikely to cause issues for the collections we use, but should be aligned when convenient.
2. **`api.rs` monolithic structure**: Not blocking, but the merge conflict risk means sprint planning must sequence stories touching this file carefully.

**Nice-to-Have (deferred): 3**

1. Integration test for SSE reconnection (would require browser automation — out of scope for AD-8's checkpoint approach)
2. Tailwind dark mode variant tokens (current palette is dark-only; if light mode ever needed, tokens would need HSL variants)
3. Load testing for SSE connection limits (NFR-P1 says "support 10 concurrent users" — current SSE implementation likely handles this, but no load test exists)

### Completeness Checklist

- [x] All FRs mapped to files and architectural decisions
- [x] All NFRs mapped to decisions or existing infrastructure
- [x] All user journeys validated against FR/AD mapping
- [x] All architectural decisions have rationale and alternatives
- [x] Implementation patterns cover naming, structure, format, communication, process
- [x] Enforcement rules are internally consistent
- [x] Project structure has NEW/MODIFY annotations with driving FRs
- [x] Dependency graph between decisions is documented
- [x] Merge conflict hotspots identified
- [x] "Do Not Decide" list established (technology changes, new CRDs, auth, multi-tenancy, horizontal scaling)
- [x] Deferred decisions documented with trigger conditions

### Readiness Assessment

**Verdict: READY FOR IMPLEMENTATION**

**Confidence: High for static architecture; two runtime verification points remain:**
1. OTEL protobuf schema compatibility (AD-1) — can only be fully verified when operator receives real OTEL Collector traffic
2. SSE reconnection with `Last-Event-ID` backfill (AD-4) — browser behavior with `retry` field must be verified in running system

These are implementation verification items, not architectural gaps. The architecture provides clear guidance for both; runtime testing will confirm the specific behavior.

### Implementation Handoff

**Recommended Implementation Sequence:**

| Phase | Architectural Decisions | Rationale |
|---|---|---|
| **Phase 0 (can start immediately)** | AD-7 (Tailwind build pipeline) | Zero dependencies on other ADs. Sets up CSS tooling needed by all UI work. |
| **Phase 1** | AD-1 (OTEL protobuf), AD-8 (integration testing) | Fix ingestion pipeline first — everything downstream depends on data flowing in. AD-8 validates AD-1. |
| **Phase 2** | AD-2 (detection stats), AD-4 (SSE reconnection) | Extend operator APIs. AD-2 provides stats for diagnostic UI. AD-4 provides reconnection contract for investigation UI. |
| **Phase 3** | AD-3 (layout shell), AD-6 (sidebar state) | UI structure. Layout shell migration enables all new UI pages. Sidebar state depends on layout shell. |
| **Phase 4** | AD-5 (KB panel query) | Last UI feature, depends on investigation display (AD-4) and layout (AD-3) being in place. |

**Parallelization Note:** AD-7 (Tailwind) can start immediately in parallel with Phase 1. Workstream 1 (Rust/operator: AD-1, AD-2, AD-8) and Workstream 2 (UI: AD-3, AD-6, AD-7) can proceed in parallel once AD-7 is complete, with AD-4 as the cross-workstream bridge point.
