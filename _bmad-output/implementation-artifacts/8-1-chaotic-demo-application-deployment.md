# Story 8.1: Chaotic Demo Application Deployment

Status: done

## Story

As an **admin**,
I want to deploy a purpose-built chaotic microservices application in K8s alongside Beeper,
so that there is a realistic target environment for demonstrating Beeper's capabilities.

## Acceptance Criteria

1. **Given** the `demo/` directory in the Beeper monorepo
   **When** an admin runs `make demo-deploy`
   **Then** a multi-service application is deployed in a dedicated `beeper-demo` namespace with: API gateway, backend service, database, and worker
   **And** each service has Prometheus metrics, structured logging, and ServiceLevel CRDs pre-configured

2. **Given** the demo application is deployed
   **When** no faults are injected
   **Then** all services are healthy, SLOs are met, and the application serves synthetic traffic
   **And** the demo app does not interfere with Beeper's monitoring of real workloads

3. **Given** the demo application
   **When** an admin runs `make demo-teardown`
   **Then** all demo resources are cleanly removed from the cluster with no orphaned resources

## Tasks / Subtasks

- [x] Task 1: Create demo application directory structure (AC: #1)
  - [x] 1.1 Create `demo/` directory at project root
  - [x] 1.2 Create `demo/app/` with a single multi-purpose Python HTTP server (`server.py`) that serves as all four services (api-gateway, backend, database-proxy, worker) based on `SERVICE_ROLE` env var
  - [x] 1.3 Create `demo/app/requirements.txt` with minimal deps: `flask`, `prometheus-client`
  - [x] 1.4 Create `demo/app/Dockerfile` for building the demo image
  - [x] 1.5 Create `demo/README.md` with usage instructions

- [x] Task 2: Create Kubernetes manifests for demo app (AC: #1, #2)
  - [x] 2.1 Create `demo/k8s/namespace.yaml` — `beeper-demo` namespace with labels for isolation
  - [x] 2.2 Create `demo/k8s/api-gateway.yaml` — Deployment + Service (port 8080), env `SERVICE_ROLE=api-gateway`, Prometheus annotations
  - [x] 2.3 Create `demo/k8s/backend.yaml` — Deployment + Service (port 8081), env `SERVICE_ROLE=backend`, Prometheus annotations
  - [x] 2.4 Create `demo/k8s/database.yaml` — Deployment + Service (port 8082), env `SERVICE_ROLE=database`, Prometheus annotations
  - [x] 2.5 Create `demo/k8s/worker.yaml` — Deployment + Service (port 8083), env `SERVICE_ROLE=worker`, Prometheus annotations
  - [x] 2.6 Each Deployment: resource limits, health/readiness probes, structured JSON logging

- [x] Task 3: Create ServiceLevel CRDs for demo services (AC: #1)
  - [x] 3.1 Create `demo/k8s/slo-api-gateway.yaml` — ServiceLevel CRD: 99.5% availability, 500ms p99 latency
  - [x] 3.2 Create `demo/k8s/slo-backend.yaml` — ServiceLevel CRD: 99.9% availability, 200ms p99 latency
  - [x] 3.3 Create `demo/k8s/slo-database.yaml` — ServiceLevel CRD: 99.95% availability, 50ms p99 latency
  - [x] 3.4 Create `demo/k8s/slo-worker.yaml` — ServiceLevel CRD: 99% availability (lower bar for batch)
  - [x] 3.5 Each ServiceLevel: burn_rate_alerts with warning/critical severity thresholds

- [x] Task 4: Create Makefile with demo targets (AC: #1, #3)
  - [x] 4.1 Create `Makefile` at project root with `demo-deploy` target: apply namespace, all K8s manifests, wait for rollout
  - [x] 4.2 Add `demo-teardown` target: delete namespace (cascading delete of all resources)
  - [x] 4.3 Add `demo-status` target: show pod status, service endpoints, SLO status
  - [x] 4.4 Add `demo-build` target: build demo Docker image
  - [x] 4.5 Add `demo-logs` target: tail logs from all demo pods

- [x] Task 5: Create demo application server (AC: #1, #2)
  - [x] 5.1 Implement `demo/app/server.py` — Flask app with role-based behavior via `SERVICE_ROLE` env var
  - [x] 5.2 API gateway role: routes requests to backend, exposes `/api/v1/orders`, `/api/v1/health`, `/metrics`
  - [x] 5.3 Backend role: business logic endpoints, calls database-proxy, exposes `/process`, `/health`, `/metrics`
  - [x] 5.4 Database role: simulated data store with latency, exposes `/query`, `/health`, `/metrics`
  - [x] 5.5 Worker role: background job processor, exposes `/jobs`, `/health`, `/metrics`
  - [x] 5.6 All roles: Prometheus metrics (request_count, request_duration_seconds histogram, error_count, active_connections gauge)
  - [x] 5.7 All roles: structured JSON logging to stdout
  - [x] 5.8 All roles: configurable fault injection hooks (env vars: `FAULT_TYPE`, `FAULT_ENABLED`) — prepare for story 8-2
  - [x] 5.9 Synthetic traffic: built-in self-traffic via background thread when `SYNTHETIC_TRAFFIC=true`

- [x] Task 6: Write tests (AC: #1, #2, #3)
  - [x] 6.1 Create `demo/tests/test_server.py` — unit tests for each service role
  - [x] 6.2 Test Prometheus metrics endpoint returns valid exposition format
  - [x] 6.3 Test health endpoint returns 200 with structured response
  - [x] 6.4 Test each role's primary endpoints with expected responses
  - [x] 6.5 Test fault injection hooks are present but disabled by default
  - [x] 6.6 Test structured JSON logging output format
  - [x] 6.7 Create `demo/tests/test_k8s_manifests.py` — validate K8s YAML structure (valid YAML, required fields, resource limits present, probe paths match server endpoints)
  - [x] 6.8 Create `demo/tests/test_slo_manifests.py` — validate ServiceLevel CRDs (apiVersion, kind, spec structure matches operator CRD schema)

## Dev Notes

### Architecture Compliance

- **Language:** Python for demo services (consistent with investigator/UI stack, lightweight for demo purposes)
- **Framework:** Flask for HTTP server (already a project dependency, proven pattern)
- **Metrics:** `prometheus-client` library for native Prometheus exposition
- **Logging:** Python `logging` with JSON formatter to stdout
- **K8s Manifests:** Raw YAML in `demo/k8s/` (not Helm — demo app is deliberately simple and self-contained)
- **Namespace isolation:** Dedicated `beeper-demo` namespace prevents interference with real workloads
- **Single image:** One Docker image, role selected via `SERVICE_ROLE` env var (reduces build complexity)
- **Naming:** `snake_case` for all JSON fields, API parameters per project convention
- **API format:** REST, JSON responses, RFC 7807 error details

### ServiceLevel CRD Schema Reference

From `operator/src/crds/servicelevel.rs`:
```yaml
apiVersion: beeper.dev/v1
kind: ServiceLevel
metadata:
  name: <service>-slo
  namespace: beeper-demo
spec:
  service: "<service-name>"
  sli:
    type: Availability | Latency | ErrorRate
    metric: "<prometheus_metric>"
    good_selector: "<promql_selector>"
    total_selector: "<promql_selector>"
  objective:
    target: 0.999  # 0.0-1.0
    window: "30m"  # measurement window
  burn_rate_alerts:
    - severity: warning
      short_window: "5m"
      long_window: "1h"
      factor: 14.4
    - severity: critical
      short_window: "2m"
      long_window: "15m"
      factor: 14.4
```

### Prometheus Metrics Pattern

Each service exposes `/metrics` with:
- `demo_request_total{service, method, endpoint, status}` — counter
- `demo_request_duration_seconds{service, endpoint}` — histogram (buckets: 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5)
- `demo_error_total{service, error_type}` — counter
- `demo_active_connections{service}` — gauge

### K8s Deployment Pattern

Each demo service deployment includes:
```yaml
metadata:
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "<port>"
    prometheus.io/path: "/metrics"
spec:
  containers:
    - livenessProbe:
        httpGet: {path: /health, port: <port>}
      readinessProbe:
        httpGet: {path: /health, port: <port>}
      resources:
        limits: {cpu: 200m, memory: 128Mi}
        requests: {cpu: 50m, memory: 64Mi}
```

### Critical Reuse — DO NOT REINVENT

- **Flask patterns:** Reuse Flask app factory pattern from `ui/beeper_ui/app.py`
- **Prometheus metrics:** Use `prometheus-client` library directly (already used in ecosystem)
- **Structured logging:** Follow JSON logging pattern from `investigator/beeper_investigator/` modules
- **K8s manifest format:** Follow patterns from `helm/beeper/templates/` for Deployment/Service structure
- **ServiceLevel CRD:** Use exact schema from `operator/src/crds/servicelevel.rs` — validated with 30+ test cases
- **Docker:** Follow existing Dockerfile patterns if present, otherwise use `python:3.11-slim` base

### Fault Injection Hooks (Preparation for Story 8-2)

The server should include dormant fault injection points controlled by environment variables:
- `FAULT_ENABLED=false` (default) — all faults disabled
- `FAULT_TYPE=none` (default) — no active fault
- When enabled, middleware intercepts requests to simulate: memory leak, error rate spike, latency increase, resource exhaustion
- Story 8-2 will activate these hooks; this story only creates the injection points

### Testing Standards

- **pytest** for all tests (project standard)
- **No external K8s required** for unit tests — test server logic directly
- **K8s manifest validation:** Parse YAML, check required fields, validate against known schema
- **Test file location:** `demo/tests/` with its own `conftest.py`
- **Test naming:** `test_<feature>_<behavior>` pattern per project convention

### Project Structure Notes

```
demo/
├── app/
│   ├── server.py           # Multi-role Flask server
│   ├── requirements.txt    # Flask, prometheus-client
│   └── Dockerfile          # python:3.11-slim based
├── k8s/
│   ├── namespace.yaml      # beeper-demo namespace
│   ├── api-gateway.yaml    # Deployment + Service
│   ├── backend.yaml        # Deployment + Service
│   ├── database.yaml       # Deployment + Service
│   ├── worker.yaml         # Deployment + Service
│   ├── slo-api-gateway.yaml  # ServiceLevel CRD
│   ├── slo-backend.yaml      # ServiceLevel CRD
│   ├── slo-database.yaml     # ServiceLevel CRD
│   └── slo-worker.yaml       # ServiceLevel CRD
├── tests/
│   ├── conftest.py
│   ├── test_server.py
│   ├── test_k8s_manifests.py
│   └── test_slo_manifests.py
└── README.md
```

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 8, Story 8.1]
- [Source: _bmad-output/planning-artifacts/architecture.md#Demo App decision]
- [Source: operator/src/crds/servicelevel.rs#ServiceLevelSpec]
- [Source: docs/integration-architecture.md#Component Communication]
- [Source: helm/beeper/values.yaml#Service configuration patterns]
- [Source: investigator/demo.py#Existing demo patterns]
- [Source: scripts/demo.sh#Demo startup script]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Completion Notes List

- Implemented multi-role Flask demo server (api-gateway, backend, database, worker) differentiated by SERVICE_ROLE env var
- Each role exposes /health, /metrics (Prometheus), and role-specific business endpoints
- Prometheus metrics: demo_request_total (counter), demo_request_duration_seconds (histogram), demo_error_total (counter), demo_active_connections (gauge)
- Structured JSON logging via custom JsonFormatter
- Fault injection hooks present but dormant (FAULT_ENABLED=false default) — memory-leak, error-rate, latency, resource-exhaustion types
- Synthetic traffic generator via background thread when SYNTHETIC_TRAFFIC=true
- K8s manifests for 4 services in beeper-demo namespace with resource limits, probes, Prometheus annotations
- 4 ServiceLevel CRDs matching operator schema (beeper.dev/v1) with burn_rate_alerts
- Makefile with demo-deploy, demo-teardown, demo-status, demo-build, demo-logs targets
- 133 tests passing: server unit tests (all roles), K8s manifest validation, SLO CRD validation
- Zero regressions: operator 538, investigator 1013, UI 2023 — all passing

### File List

- demo/app/server.py (NEW, 310 lines) — Multi-role Flask demo server
- demo/app/requirements.txt (NEW) — Flask, prometheus-client deps
- demo/app/Dockerfile (NEW) — python:3.11-slim based container
- demo/README.md (NEW) — Usage documentation
- demo/k8s/namespace.yaml (NEW) — beeper-demo namespace
- demo/k8s/api-gateway.yaml (NEW) — Deployment + Service
- demo/k8s/backend.yaml (NEW) — Deployment + Service
- demo/k8s/database.yaml (NEW) — Deployment + Service
- demo/k8s/worker.yaml (NEW) — Deployment + Service
- demo/k8s/slo-api-gateway.yaml (NEW) — ServiceLevel CRD, 99.5% target
- demo/k8s/slo-backend.yaml (NEW) — ServiceLevel CRD, 99.9% target
- demo/k8s/slo-database.yaml (NEW) — ServiceLevel CRD, 99.95% target
- demo/k8s/slo-worker.yaml (NEW) — ServiceLevel CRD, 99% target
- demo/tests/conftest.py (NEW) — Shared test fixtures
- demo/tests/test_server.py (NEW) — Server unit tests (93 tests)
- demo/tests/test_k8s_manifests.py (NEW) — K8s manifest validation (48 tests)
- demo/tests/test_slo_manifests.py (NEW) — SLO CRD validation (40 tests)
- Makefile (NEW) — Demo deployment targets
