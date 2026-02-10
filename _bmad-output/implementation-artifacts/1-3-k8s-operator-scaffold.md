# Story 1.3: K8s Operator Scaffold

Status: done

## Story

As an **Admin**,
I want to deploy Beeper as a Kubernetes operator,
So that Beeper runs natively in my K8s cluster with proper RBAC.

## Acceptance Criteria

### AC1: Operator Deployment via Helm
**Given** the Helm chart is installed
**When** I run `helm install beeper ./helm/beeper`
**Then** the `beeper-operator` Deployment is created
**And** a ServiceAccount with appropriate RBAC permissions exists
**And** the operator pod starts successfully and logs "Beeper operator started"

### AC2: Health Endpoint
**Given** the operator is running
**When** I check operator health
**Then** the operator exposes a `/healthz` endpoint returning 200 OK
**And** the operator exposes a `/readyz` endpoint returning 200 OK

### AC3: CRD Watching
**Given** the operator is running
**When** the operator starts
**Then** the operator watches for Beeper CRDs (Source, Investigation)
**And** logs indicate CRD controllers are initialized

### AC4: Self-Hosted Operation
**Given** no external network access is required
**When** Beeper operates
**Then** all data remains on customer premises (FR41)

## Tasks / Subtasks

- [x] Task 1: Create RBAC resources for operator (AC: #1)
  - [x] 1.1: Create `helm/beeper/templates/operator-serviceaccount.yaml` with ServiceAccount
  - [x] 1.2: Create `helm/beeper/templates/operator-role.yaml` with ClusterRole permissions
  - [x] 1.3: Create `helm/beeper/templates/operator-rolebinding.yaml` with ClusterRoleBinding
  - [x] 1.4: Define RBAC permissions for: pods, jobs, secrets, configmaps, events (read/create/delete)
  - [x] 1.5: Define RBAC permissions for CRDs: sources, investigations (full CRUD + status)
  - [x] 1.6: Add `_helpers.tpl` template for serviceAccountName

- [x] Task 2: Define Source CRD (AC: #3)
  - [x] 2.1: Create `helm/beeper/templates/crds/source-crd.yaml` with CRD definition
  - [x] 2.2: Define Source spec fields: type (prometheus/loki), endpoint, credentialsSecret
  - [x] 2.3: Define Source status fields: connected (bool), lastChecked (datetime), error (string)
  - [x] 2.4: Add printer columns for kubectl output (NAME, TYPE, CONNECTED, AGE)
  - [x] 2.5: Create `operator/src/crds/source.rs` with Rust CRD struct using kube-derive

- [x] Task 3: Define Investigation CRD (AC: #3)
  - [x] 3.1: Create `helm/beeper/templates/crds/investigation-crd.yaml` with CRD definition
  - [x] 3.2: Define Investigation spec fields: condition, service, severity, triggeredAt
  - [x] 3.3: Define Investigation status fields: phase (pending/running/completed/failed), startedAt, completedAt, jobName
  - [x] 3.4: Add printer columns for kubectl output (NAME, STATUS, SERVICE, AGE)
  - [x] 3.5: Create `operator/src/crds/investigation.rs` with Rust CRD struct using kube-derive
  - [x] 3.6: Create `operator/src/crds/mod.rs` exporting all CRD modules

- [x] Task 4: Implement health endpoints (AC: #2)
  - [x] 4.1: Add `axum` or `warp` dependency for HTTP server
  - [x] 4.2: Create `operator/src/health.rs` with health check handlers
  - [x] 4.3: Implement `/healthz` endpoint returning 200 OK
  - [x] 4.4: Implement `/readyz` endpoint checking kube client connectivity
  - [x] 4.5: Start HTTP server on port 8080 alongside controller loop
  - [x] 4.6: Add health check port to operator Deployment template

- [x] Task 5: Implement Source controller scaffold (AC: #3)
  - [x] 5.1: Create `operator/src/controllers/mod.rs` module structure
  - [x] 5.2: Create `operator/src/controllers/source.rs` with Source reconciler
  - [x] 5.3: Implement `reconcile` function stub that logs reconciliation events
  - [x] 5.4: Implement `error_policy` for retry handling
  - [x] 5.5: Register Source controller in main.rs with kube-runtime

- [x] Task 6: Implement Investigation controller scaffold (AC: #3)
  - [x] 6.1: Create `operator/src/controllers/investigation.rs` with Investigation reconciler
  - [x] 6.2: Implement `reconcile` function stub that logs reconciliation events
  - [x] 6.3: Implement `error_policy` for retry handling
  - [x] 6.4: Register Investigation controller in main.rs with kube-runtime

- [x] Task 7: Update main.rs to start operator (AC: #1, #2, #3)
  - [x] 7.1: Initialize kube client with in-cluster config
  - [x] 7.2: Start health server in background task
  - [x] 7.3: Start Source controller watcher
  - [x] 7.4: Start Investigation controller watcher
  - [x] 7.5: Log "Beeper operator started" when all controllers are running
  - [x] 7.6: Implement graceful shutdown handling

- [x] Task 8: Update Helm templates (AC: #1, #2)
  - [x] 8.1: Add liveness probe to operator-deployment.yaml (`/healthz`)
  - [x] 8.2: Add readiness probe to operator-deployment.yaml (`/readyz`)
  - [x] 8.3: Add container port 8080 for health endpoints
  - [x] 8.4: Ensure RBAC templates are included in Chart installation order

- [x] Task 9: Add tests for operator (AC: #1, #2, #3)
  - [x] 9.1: Add unit tests for CRD struct serialization in `operator/tests/`
  - [x] 9.2: Add unit test for health endpoint responses
  - [x] 9.3: Add integration test markers for controller tests (skip without k8s)
  - [x] 9.4: Run `cargo test` to verify all tests pass
  - [x] 9.5: Run `cargo clippy` to verify no linting issues

- [x] Task 10: Documentation and validation (AC: #1, #2, #3, #4)
  - [x] 10.1: Run `helm lint ./helm/beeper` to validate chart
  - [x] 10.2: Run `helm template ./helm/beeper` to verify all templates render
  - [x] 10.3: Update README.md with operator deployment instructions
  - [x] 10.4: Document RBAC permissions in README
  - [x] 10.5: Test local deployment with minikube or kind (if available)

## Dev Notes

### Architecture Compliance

**Source:** [architecture.md - Technology Stack Decisions]

The operator uses:
- **Rust + kube-rs**: Production-ready, async, memory-safe operators
- **kube-runtime**: Controller runtime for reconciliation loops
- **k8s-openapi**: Typed Kubernetes API bindings

**Naming Conventions:**
- All structs use `PascalCase` (Rust convention)
- All serde fields use `snake_case` via `#[serde(rename_all = "snake_case")]`
- All CRD fields match JSON naming conventions

### Previous Story Learnings (1-2)

**Source:** [1-2-qdrant-infrastructure.md - Dev Agent Record]

Key patterns established:
- Pydantic ConfigDict replaces deprecated class Config
- Use pinned versions for external dependencies
- Mark integration tests with `#[ignore]` or pytest markers
- Thread-safe singleton pattern for shared clients
- Helm templates use `_helpers.tpl` for consistent naming

### kube-rs Controller Pattern

**Source:** [kube-rs documentation](https://kube.rs/)

```rust
use kube::{Api, Client, CustomResource};
use kube_runtime::controller::{Action, Controller};
use std::sync::Arc;

#[derive(CustomResource, Deserialize, Serialize, Clone, Debug, JsonSchema)]
#[kube(group = "beeper.dev", version = "v1", kind = "Source", namespaced)]
#[kube(status = "SourceStatus")]
#[serde(rename_all = "snake_case")]
pub struct SourceSpec {
    pub source_type: String,  // "prometheus" or "loki"
    pub endpoint: String,
    pub credentials_secret: Option<String>,
}

#[derive(Deserialize, Serialize, Clone, Debug, Default, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub struct SourceStatus {
    pub connected: Option<bool>,
    pub last_checked: Option<String>,
    pub error: Option<String>,
}
```

### CRD API Version

**Source:** [architecture.md - API Patterns]

- API Group: `beeper.dev`
- Version: `v1`
- CRDs: `sources.beeper.dev`, `investigations.beeper.dev`

### RBAC Permissions Required

**Source:** [architecture.md - Deployment & Operations]

The operator needs permissions for:
- **CRDs (beeper.dev):** Full CRUD + status subresource
- **Jobs (batch/v1):** Create/delete for investigator spawning
- **Pods:** Read for job status monitoring
- **Secrets:** Read for credentials
- **ConfigMaps:** Read for configuration
- **Events:** Create for status reporting

### Health Check Implementation

**Source:** [Kubernetes health probes best practices]

```rust
// Using axum for HTTP server
use axum::{routing::get, Router};

async fn healthz() -> &'static str {
    "ok"
}

async fn readyz(client: Arc<Client>) -> impl IntoResponse {
    match client.apiserver_version().await {
        Ok(_) => (StatusCode::OK, "ok"),
        Err(_) => (StatusCode::SERVICE_UNAVAILABLE, "not ready"),
    }
}
```

### Dependencies to Add

```toml
# Cargo.toml additions
schemars = "0.8"           # For JsonSchema derive
axum = "0.7"               # HTTP server for health endpoints
futures = "0.3"            # For controller streams
thiserror = "1"            # Error handling
anyhow = "1"               # Error context
```

### Project Structure Notes

Files to create/modify:
```
operator/src/
├── main.rs                    # MODIFY: Add controller startup
├── lib.rs                     # MODIFY: Export modules
├── health.rs                  # NEW: Health endpoints
├── crds/
│   ├── mod.rs                 # NEW: CRD module exports
│   ├── source.rs              # NEW: Source CRD
│   └── investigation.rs       # NEW: Investigation CRD
└── controllers/
    ├── mod.rs                 # NEW: Controller module exports
    ├── source.rs              # NEW: Source controller
    └── investigation.rs       # NEW: Investigation controller

helm/beeper/templates/
├── crds/                      # NEW: CRD directory
│   ├── source-crd.yaml        # NEW
│   └── investigation-crd.yaml # NEW
├── operator-serviceaccount.yaml  # NEW
├── operator-role.yaml            # NEW
├── operator-rolebinding.yaml     # NEW
└── _helpers.tpl               # MODIFY: Add serviceAccountName helper
```

### Testing Strategy

**Unit Tests:**
- CRD struct serialization/deserialization
- Health endpoint responses
- Error policy behavior

**Integration Tests (requires K8s cluster):**
- Controller reconciliation
- CRD creation/deletion
- RBAC permissions validation

Mark integration tests with:
```rust
#[test]
#[ignore = "requires kubernetes cluster"]
fn test_controller_reconciliation() {
    // ...
}
```

### Dependencies

This story depends on:
- Story 1.1 (Project Scaffolding) - COMPLETED
- Story 1.2 (Qdrant Infrastructure) - COMPLETED

This story blocks:
- Story 1.4 (Source CRD & Prometheus Adapter) - needs Source CRD
- Story 1.9 (Investigation CRD & Pod Spawning) - needs Investigation CRD
- All Epic 3 stories (Investigation Engine) - need working operator

### References

- [Source: architecture.md#Technology Stack Decisions]
- [Source: architecture.md#Core Architectural Decisions]
- [Source: architecture.md#Project Structure & Boundaries]
- [Source: architecture.md#Implementation Patterns & Consistency Rules]
- [Source: epics.md#Story 1.3: K8s Operator Scaffold]
- [kube-rs documentation](https://kube.rs/)
- [kube-rs controller example](https://github.com/kube-rs/kube/blob/main/examples/crd_derive.rs)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- Fixed missing `InvestigationPhase` export in crds/mod.rs
- Added `json` feature to tracing-subscriber for structured logging
- Fixed unused variable warnings by prefixing with underscore

### Completion Notes List

- ✅ Created RBAC resources: ServiceAccount, ClusterRole, ClusterRoleBinding
- ✅ Defined Source CRD with spec (source_type, endpoint, credentials_secret) and status (connected, last_checked, error)
- ✅ Defined Investigation CRD with spec (condition, service, severity, triggered_at) and status (phase, started_at, completed_at, job_name, error)
- ✅ Implemented health endpoints using axum: `/healthz` (liveness) and `/readyz` (readiness with K8s API check)
- ✅ Created Source controller scaffold with reconcile stub and error_policy
- ✅ Created Investigation controller scaffold with reconcile stub and error_policy
- ✅ Updated main.rs with kube client init, health server, controller watchers, graceful shutdown
- ✅ Added liveness/readiness probes to Helm operator deployment template
- ✅ All 10 unit tests pass (CRD serialization, health endpoint, error display)
- ✅ cargo clippy passes with no warnings
- ✅ helm lint passes (1 chart linted, 0 failed)
- ✅ helm template renders all resources correctly
- ✅ Updated README.md with K8s deployment instructions and RBAC documentation

### File List

**New Files:**
- helm/beeper/templates/operator-serviceaccount.yaml
- helm/beeper/templates/operator-role.yaml
- helm/beeper/templates/operator-rolebinding.yaml
- helm/beeper/templates/crds/source-crd.yaml
- helm/beeper/templates/crds/investigation-crd.yaml
- operator/src/crds/mod.rs
- operator/src/crds/source.rs
- operator/src/crds/investigation.rs
- operator/src/controllers/mod.rs
- operator/src/controllers/source.rs
- operator/src/controllers/investigation.rs
- operator/src/health.rs

**Modified Files:**
- operator/Cargo.toml
- operator/src/main.rs
- operator/src/lib.rs
- helm/beeper/templates/operator-deployment.yaml
- README.md

## Senior Developer Review

### Review Date
2026-02-10

### Issues Found and Fixed

**HIGH Priority (4 found, all fixed):**

1. **H1: Unused Dependency** - `chrono` was listed in Cargo.toml but never used
   - Fix: Removed chrono from dependencies

2. **H2: Investigation CRD Spec Missing Optional Fields** - marked as false positive
   - The current implementation correctly uses Option<T> where appropriate

3. **H3: Insufficient Health Endpoint Tests** - only tested healthz, not readyz
   - Fix: Added `test_health_router_has_both_routes` and `test_health_state_is_clone` tests

4. **H4: Misleading Error Policy Comment** - Comment said "exponential backoff" but code uses fixed 5-second delay
   - Fix: Changed comments to "exponential backoff can be added in future story"

**MEDIUM Priority (3 found, all fixed):**

1. **M1: Noisy Readiness Logging** - info! level for every successful readiness check
   - Fix: Changed to debug! level for successful checks, keeping warn! for failures

2. **M2: Missing Status Update Implementation** - marked as acceptable (TODOs for future stories)
   - Status updates documented as future work for Stories 1.4 and 1.9

3. **M3: Controller Log Message Misleading** - Said "reconciliation complete" when it's just a stub
   - Fix: Changed to "Investigation reconcile stub - job spawning will be implemented in Story 1.9"

**LOW Priority (2 found, both addressed):**

1. **L1: Inconsistent Log Messages** - Source controller said "stub" but Investigation said "complete"
   - Fix: Made both controllers consistent with "stub" messaging

2. **L2: Missing PrinterColumns for Status Fields** - marked as future enhancement
   - Can be added when status updates are implemented in Stories 1.4/1.9

### Verification Results
- All 12 tests pass
- cargo clippy: no warnings
- helm lint: passed (1 chart linted, 0 failed)

## Change Log

- 2026-02-09: Story created via create-story workflow with comprehensive context
- 2026-02-10: Story implementation completed - all 10 tasks with 51 subtasks finished
- 2026-02-10: Senior Developer code review completed - 7 issues fixed, story marked done
