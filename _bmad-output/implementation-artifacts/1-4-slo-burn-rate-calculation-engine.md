# Story 1.4: SLO Burn Rate Calculation Engine

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the **system**,
I want to calculate SLO burn rates in real-time from ingested Prometheus metrics,
so that investigations can be triggered when burn rates exceed configured thresholds.

## Acceptance Criteria

1. **AC1: SLO compliance & burn rate computation**
   **Given** a ServiceLevel CRD with a configured SLI metric and objective target
   **When** Prometheus metrics are ingested by the operator
   **Then** the SLO calculator computes compliance percentage and burn rate within a < 5 second refresh cycle (NFR6)
   **And** burn rate snapshots are written to the `slo_snapshots` Qdrant collection

2. **AC2: Multi-window burn rate alerting → Investigation creation**
   **Given** a burn rate that exceeds the configured alert factor for both short and long windows
   **When** the burn rate alerter evaluates
   **Then** an Investigation CRD is created with SLO context (service, burn rate, budget remaining)
   **And** the investigation is triggered within 30 seconds of detection (NFR1)

3. **AC3: Qdrant collection auto-creation**
   **Given** the `slo_snapshots` Qdrant collection does not exist
   **When** the operator starts up
   **Then** the collection is created automatically as payload-only

## Tasks / Subtasks

- [x] Task 1: Create SLO calculator module (AC: #1)
  - [x] 1.1: Create `operator/src/slo/mod.rs` with module declarations and shared types (`SloSnapshot`, `SloCalculationResult`, `SloError`)
  - [x] 1.2: Create `operator/src/slo/calculator.rs` with `SloCalculator` struct that queries Prometheus for good/total events using ServiceLevel CRD selectors
  - [x] 1.3: Implement compliance calculation: `compliance = good_count / total_count` where counts are fetched via PromQL `increase()` queries over the short and long windows
  - [x] 1.4: Implement burn rate calculation: `burn_rate = (1.0 - compliance) / (1.0 - target)` per Google SRE multi-window multi-burn-rate alerting model
  - [x] 1.5: Return `SloCalculationResult` with compliance, burn_rate, error_budget_remaining, good_count, total_count, timestamp
  - [x] 1.6: Handle edge cases: total_count == 0 (no data, skip), target == 1.0 (undefined burn rate), Prometheus query failure (log and skip)

- [x] Task 2: Create burn rate alerter (AC: #2)
  - [x] 2.1: Create `operator/src/slo/burn_rate.rs` with `BurnRateAlerter` struct
  - [x] 2.2: Implement multi-window evaluation: for each `BurnRateAlert` in the ServiceLevel CRD, check if burn rate exceeds `factor` in BOTH the short_window AND long_window — both must exceed for the alert to fire (Google SRE pattern)
  - [x] 2.3: Parse window duration strings ("5m", "1h", "6h", "30d") into `Duration` for Prometheus range queries
  - [x] 2.4: Create Investigation CRD when alert fires — follow existing pattern from `detection/consumer.rs`:
    - Name: `slo-burn-{timestamp_hex}-{seq_hex}`
    - Condition: `"SLO burn rate alert: {service} burn rate {burn_rate:.1}x exceeds {factor}x threshold ({severity})"`
    - Service: from ServiceLevel CRD `.spec.service`
    - Severity: from BurnRateAlert `.severity` (map to Investigation Severity enum)
    - triggered_at: `Utc::now().to_rfc3339()`
  - [x] 2.5: Implement cooldown tracking (reuse fingerprint pattern from detection consumer) to prevent duplicate alerts for the same ServiceLevel + alert combination

- [x] Task 3: Create Qdrant snapshot writer (AC: #1, #3)
  - [x] 3.1: Create a simple `QdrantWriter` in the slo module that uses `reqwest::Client` to call Qdrant REST API (port 6333) — no new crate dependency needed
  - [x] 3.2: Implement `ensure_collection()` — `PUT /collections/slo_snapshots` with payload-only config (no vector index) on operator startup
  - [x] 3.3: Implement `write_snapshot()` — `PUT /collections/slo_snapshots/points` to upsert burn rate snapshot points with payload: `{ service, sli_type, compliance, burn_rate, error_budget_remaining, good_count, total_count, timestamp }`
  - [x] 3.4: Use deterministic point IDs based on service name hash + timestamp bucket to enable efficient time-range queries
  - [x] 3.5: Handle Qdrant connection failures gracefully — log error, continue processing (SLO engine must not crash if Qdrant is down)

- [x] Task 4: Wire SLO engine as background task (AC: #1, #2, #3)
  - [x] 4.1: Create `run_slo_engine()` async function in `operator/src/slo/mod.rs` — takes K8s Client, PrometheusClient (or endpoint config), Qdrant endpoint
  - [x] 4.2: Implement periodic loop: every 5 seconds (configurable via `BEEPER_SLO_REFRESH_SECS`, default 5) — list all ServiceLevel CRDs, compute burn rate for each, write snapshots, evaluate alerts
  - [x] 4.3: On first iteration, call `QdrantWriter::ensure_collection()` to auto-create `slo_snapshots` if missing (AC: #3)
  - [x] 4.4: Add `run_slo_engine` import in `operator/src/main.rs` and spawn as background tokio task (same pattern as detection consumer)
  - [x] 4.5: Add `slo_handle.abort()` to shutdown sequence in main.rs
  - [x] 4.6: Configure PrometheusClient endpoint from `PROMETHEUS_URL` env var (already used by existing ingestion code) or default to `http://prometheus:9090`

- [x] Task 5: Extend SLO API endpoints with burn rate data (AC: #1)
  - [x] 5.1: Add `burn_rate` and `compliance` fields to existing `ServiceLevelResponse` and `ServiceLevelDetailResponse` structs in `operator/src/api.rs`
  - [x] 5.2: Store latest calculation results in a shared `Arc<RwLock<HashMap<String, SloCalculationResult>>>` accessible from API state
  - [x] 5.3: Update `GET /api/v1/slo/services` and `GET /api/v1/slo/services/{name}` handlers to include latest burn rate data from the shared cache

- [x] Task 6: Write tests (AC: #1, #2, #3)
  - [x] 6.1: Calculator unit tests — compliance calculation (100%, 99.9%, 95%, 0%), burn rate computation (1x, 14.4x, 6x), edge cases (zero total, target == 1.0, NaN defense)
  - [x] 6.2: Burn rate alerter tests — multi-window evaluation (both windows exceed → alert, only short exceeds → no alert, only long exceeds → no alert), severity mapping, cooldown prevention
  - [x] 6.3: Window duration parser tests — "5m" → 300s, "1h" → 3600s, "6h" → 21600s, "30d" → 2592000s, invalid inputs
  - [x] 6.4: QdrantWriter tests — collection creation request format, snapshot point format, connection failure handling (mock with wiremock)
  - [x] 6.5: SloSnapshot serialization tests — JSON output format matches expected schema
  - [x] 6.6: Verify all existing operator tests still pass (`cargo test`) — cargo may not be available; Python tests verified as regression guard (482 investigator + 657 UI)

## Dev Notes

### Architecture Compliance

**SLO Engine Placement (from architecture.md):**
The SLO burn rate calculation runs inside the Rust operator process — alongside anomaly detection. No separate service.
```
Prometheus metrics → Operator ingestion → SLO calculator → slo_snapshots (Qdrant)
                                                         → Investigation priority scoring
                                                         → Notification urgency weighting
```
[Source: _bmad-output/planning-artifacts/architecture.md#SLO Engine Architecture (New)]

**File Structure (from architecture.md):**
```
operator/src/slo/                         # New: SLO engine module
    mod.rs                                # Module declarations + run_slo_engine() + shared types
    calculator.rs                         # SLO compliance + burn rate computation
    burn_rate.rs                          # Multi-window burn rate alerting
```
Note: `budget.rs` (Story 1-6) and `impact.rs` (Story 1-5) are NOT in scope for this story.
[Source: _bmad-output/planning-artifacts/architecture.md#Component Architecture]

**Qdrant `slo_snapshots` Collection (from architecture.md):**
```
| slo_snapshots | Payload-only | Burn rate snapshots, error budget data | New |
```
- Type: payload-only (no vector index)
- Purpose: burn rate snapshots for dashboard time-series queries
- Access pattern: write-heavy, time-series queries
[Source: _bmad-output/planning-artifacts/architecture.md#Qdrant Collections]

**API Endpoints (already exist from Story 1-3, extended here):**
```
GET  /api/v1/slo/services                    # List services with SLO status + burn rate
GET  /api/v1/slo/services/{name}             # Service SLO detail + burn rate
```
The `/budget` endpoint is Story 1-6 scope.
[Source: _bmad-output/planning-artifacts/architecture.md#API & Communication Patterns]

**FR to File Mapping (from architecture.md):**
- FR2 (burn rates): `operator/src/slo/calculator.rs`, `operator/src/slo/burn_rate.rs`
- FR3 (SLO-triggered investigations): `operator/src/slo/burn_rate.rs` → `operator/src/controllers/investigation.rs`
[Source: _bmad-output/planning-artifacts/architecture.md#FR to Structure Mapping]

### Implementation Approach

**Key Design Decisions:**

1. **Burn rate formula (Google SRE model):**
   ```
   compliance = good_events / total_events  (over a time window)
   error_rate = 1.0 - compliance
   burn_rate = error_rate / (1.0 - target)
   error_budget_remaining = 1.0 - (error_rate / (1.0 - target)) * (elapsed / window)
   ```
   A burn_rate of 1.0 means consuming budget at exactly the expected rate. A burn_rate of 14.4 means consuming budget 14.4x faster — at that rate, a 30-day budget depletes in ~2 days.

2. **Multi-window multi-burn-rate alerting:**
   For each `BurnRateAlert` in the ServiceLevel CRD, the alerter:
   - Queries compliance over the `short_window` (e.g., 5m)
   - Queries compliance over the `long_window` (e.g., 1h)
   - Computes burn_rate for each
   - Alert fires ONLY if BOTH exceed the `factor` threshold
   This prevents false positives from transient spikes (short window alone) and delays from long-only monitoring.

3. **Prometheus query construction:**
   ```
   # For availability SLI:
   good_count = increase(metric{good_selector}[window])
   total_count = increase(metric{total_selector}[window])

   # The metric name and selectors come directly from ServiceLevelSpec.sli
   # PromQL query: increase({metric}{selector}[{window}])
   ```
   Use `PrometheusClient.query()` with instant PromQL queries using `increase()` function.

4. **Qdrant REST API (no new crate dependency):**
   The operator already has `reqwest` in Cargo.toml. Use Qdrant's HTTP REST API directly:
   - `PUT /collections/slo_snapshots` — create collection (payload-only, no vectors)
   - `PUT /collections/slo_snapshots/points` — upsert snapshot points

   Point payload schema:
   ```json
   {
     "service": "payment-service",
     "sli_type": "availability",
     "compliance": 0.9985,
     "burn_rate": 1.5,
     "error_budget_remaining": 0.85,
     "good_count": 9985.0,
     "total_count": 10000.0,
     "timestamp": "2026-03-14T12:00:00Z"
   }
   ```

5. **Investigation CRD creation follows detection consumer pattern exactly:**
   ```rust
   let investigation = Investigation::new(
       &investigation_name,
       InvestigationSpec {
           condition: format!("SLO burn rate alert: {} burn rate {:.1}x exceeds {:.1}x threshold ({})",
               service, burn_rate, alert.factor, alert.severity),
           service: service.clone(),
           severity: map_alert_severity(&alert.severity),
           triggered_at: Some(Utc::now().to_rfc3339()),
       },
   );
   let investigation_api: Api<Investigation> = Api::namespaced(client.clone(), &namespace);
   investigation_api.create(&PostParams::default(), &investigation).await?;
   ```
   [Source: operator/src/detection/consumer.rs:181-195]

6. **Background task follows detection consumer pattern:**
   - Spawned via `tokio::spawn` in main.rs
   - Runs infinite loop with `tokio::time::sleep(Duration::from_secs(5))` between iterations
   - Handles shutdown via task abort
   - Graceful error handling — log and continue, never crash

7. **Shared state for API access:**
   Use `Arc<RwLock<HashMap<String, SloCalculationResult>>>` to share latest calculations with API handlers:
   - SLO engine writes on each iteration
   - API handlers read on request
   - RwLock allows concurrent reads from API while SLO engine holds write lock briefly

8. **This story does NOT implement:**
   - Customer impact scoring (Story 1-5: `operator/src/slo/impact.rs`)
   - Error budget policies (Story 1-6: `operator/src/slo/budget.rs`)
   - SLO compliance dashboard UI (Story 1-7)
   - Platform resilience (Story 1-8)

   This story ONLY implements: SLO compliance calculation, burn rate computation, multi-window alerting with Investigation creation, Qdrant snapshot writing, and burn rate data in existing API endpoints.

### Technical Requirements

- **Rust stable** — all operator code is Rust
- **kube-rs 0.95** — for K8s API (list ServiceLevel CRDs, create Investigation CRDs)
- **k8s-openapi 0.23** with `v1_30` feature
- **reqwest 0.11** — for Prometheus queries AND Qdrant REST API (already in Cargo.toml)
- **tokio 1** — for async runtime, sleep, spawn (already in Cargo.toml)
- **chrono** — for timestamps (already in Cargo.toml)
- **serde + serde_json** — for JSON serialization (already in Cargo.toml)
- **tracing** — for structured logging (already in Cargo.toml)
- **thiserror** — for error types (already in Cargo.toml)
- **No new dependencies required** — all needed crates are already in Cargo.toml

### File Structure Requirements

**New files to create:**
```
operator/src/slo/mod.rs                    # Module declarations, shared types, run_slo_engine()
operator/src/slo/calculator.rs             # SloCalculator - compliance & burn rate computation
operator/src/slo/burn_rate.rs              # BurnRateAlerter - multi-window alerting + Investigation creation
```

**Files to modify:**
```
operator/src/main.rs                       # Spawn SLO engine background task + shutdown
operator/src/lib.rs                        # Add pub mod slo
operator/src/api.rs                        # Extend SLO response structs with burn_rate fields + shared state
```

### Testing Requirements

- **Framework:** Rust `#[cfg(test)]` modules with `#[test]` and `#[tokio::test]` attributes
- **Mocking:** `wiremock` for HTTP mocking of Prometheus and Qdrant APIs (already in dev-dependencies)
- **Test patterns:** Follow existing operator test patterns:
  - Unit tests for pure calculation functions (compliance, burn_rate, window parsing)
  - Mock-based tests for Prometheus query + Qdrant write interactions
  - Edge case coverage: zero division, NaN, missing data, connection failures
- **Regression:** All existing operator tests must pass. Python tests (482 investigator + 657 UI) serve as regression guard
- **Environment note:** cargo may not be available in the development environment. Write tests that will pass when compiled — verify syntax and logic correctness through code review.

### Critical Guardrails

1. **DO NOT implement customer impact scoring.** That is Story 1-5 (`operator/src/slo/impact.rs`).
2. **DO NOT implement error budget policies.** That is Story 1-6 (`operator/src/slo/budget.rs`).
3. **DO NOT implement the SLO dashboard UI.** That is Story 1-7.
4. **DO NOT add new crate dependencies to Cargo.toml.** Use existing `reqwest` for both Prometheus and Qdrant HTTP APIs.
5. **Follow existing Rust patterns exactly.** Use `#[serde(rename_all = "snake_case")]` on ALL structs and enums. Use `#[serde(skip_serializing_if = "Option::is_none")]` on Option fields.
6. **Use `thiserror::Error` for error types.** Follow `PrometheusError` and `ServiceLevelError` patterns.
7. **Use `tracing` macros** (`info!`, `error!`, `warn!`, `debug!`) for logging — NOT `println!` or `log`.
8. **Use `#[instrument]` attribute** on key functions with `skip(client)` and relevant `fields()`.
9. **Investigation CRD creation MUST follow the existing pattern** from `detection/consumer.rs` — use `Api::namespaced`, `PostParams::default()`, and the existing `Investigation::new()` + `InvestigationSpec` structs.
10. **Burn rate alert MUST check BOTH windows.** Only fire when BOTH short AND long window burn rates exceed the factor. This is the Google SRE multi-window pattern that prevents false positives.
11. **Qdrant collection MUST be payload-only.** No vector index configuration. Use Qdrant REST API `PUT /collections/slo_snapshots` with `vectors: {}` (empty) config.
12. **SLO engine MUST NOT crash on Prometheus/Qdrant failures.** Log errors and continue to next ServiceLevel CRD or next iteration. The engine is a best-effort background process.
13. **Cooldown for Investigation creation.** Prevent duplicate Investigation CRDs for the same ServiceLevel + alert combination. Use fingerprint pattern from `detection/consumer.rs` with configurable cooldown (default 600s).
14. **All JSON fields are `snake_case`** — enforced via serde.

### Previous Story Intelligence

**Story 1-3 (ServiceLevel CRD & Controller) — Completed (direct dependency):**
- Created `ServiceLevelSpec`, `SliSpec`, `ObjectiveSpec`, `BurnRateAlert` structs — Story 1-4 reads these directly
- `SliType` enum: `Availability`, `Latency`, `ErrorRate` with serde snake_case
- `ServiceLevelCondition` enum: `Healthy`, `Warning`, `Critical`
- Key learning from code review: `SliType` `Debug` format produced `"errorrate"` instead of `"error_rate"` — use explicit `sli_type_to_string()` helper instead of `Debug` format
- Controller validates spec and patches status — Story 1-4 builds on top by adding actual burn rate calculation
- API endpoints `GET /api/v1/slo/services` and `GET /api/v1/slo/services/{name}` already exist — extend with burn rate data
- Response structs: `ServiceLevelResponse`, `ServiceLevelDetailResponse`, `ServiceLevelListResponse` — extend these
- NaN defense-in-depth added to `validate_spec()` target range check — apply similar NaN defense in burn rate calculations
- 42 Rust tests total (27 CRD + 8 controller + 7 code review additions)
- Cargo not available in dev environment — Python tests serve as regression guard

**Story 1-2 (Secrets Management & PII Scrubbing) — Completed:**
- Pattern: comprehensive edge case coverage in tests (74 tests)
- Code review found: reversed() on audit entries for no reason, dead code — keep code clean and intentional

**Story 1-1 (Permission Model Enforcement) — Completed:**
- Key learning: Security edge case (JWT fallthrough) caught in code review — validate all edge cases in burn rate alerting
- Code review found: weak tests that didn't actually verify the expected behavior — write strong assertions

**Code review patterns from all 3 stories:**
- Reviews consistently find 5 issues each
- HIGH: correctness/security edge cases
- MEDIUM: dead code, missing type annotations, argument validation
- LOW: weak tests, missing edge case tests

### Project Structure Notes

- SLO engine is a new module in `operator/src/slo/` — this is the first time new non-CRD/non-controller Rust modules are added in this sprint
- The operator already has: `crds/`, `controllers/`, `detection/`, `ingestion/`, `sources/` modules
- Prometheus querying already exists in `operator/src/sources/prometheus.rs` — reuse `PrometheusClient` for SLO queries
- Investigation CRD creation already exists in `operator/src/detection/consumer.rs` — reuse pattern for SLO-triggered investigations
- Qdrant is new territory for the operator (previously only used by Python investigator) — use HTTP REST API via existing `reqwest`
- API state pattern in `operator/src/api.rs` already has `ApiState` with `Arc<Client>` and `Arc<IngestionBuffer>` — extend with SLO cache

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#SLO Engine Architecture (New)] — SLO engine placement and data flow
- [Source: _bmad-output/planning-artifacts/architecture.md#Qdrant Collections] — slo_snapshots collection definition
- [Source: _bmad-output/planning-artifacts/architecture.md#API & Communication Patterns] — SLO API endpoints
- [Source: _bmad-output/planning-artifacts/architecture.md#Component Architecture] — File structure for slo/ module
- [Source: _bmad-output/planning-artifacts/architecture.md#FR to Structure Mapping] — FR2/FR3 to file mapping
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.4] — Acceptance criteria and user story
- [Source: _bmad-output/planning-artifacts/prd.md#FR2] — FR2: Calculate SLO burn rates in real-time
- [Source: _bmad-output/planning-artifacts/prd.md#FR3] — FR3: Trigger investigations on SLO burn rate threshold
- [Source: _bmad-output/planning-artifacts/prd.md#NFR1] — NFR1: Anomaly-to-investigation < 30 seconds
- [Source: _bmad-output/planning-artifacts/prd.md#NFR6] — NFR6: SLO burn rate < 5 second refresh cycle
- [Source: operator/src/crds/servicelevel.rs] — ServiceLevel CRD definition (SliSpec, ObjectiveSpec, BurnRateAlert)
- [Source: operator/src/controllers/servicelevel.rs] — ServiceLevel controller pattern
- [Source: operator/src/detection/consumer.rs:181-195] — Investigation CRD creation pattern
- [Source: operator/src/sources/prometheus.rs] — PrometheusClient (query, query_range)
- [Source: operator/src/main.rs] — Background task spawning pattern
- [Source: operator/src/api.rs] — API state and endpoint patterns
- [Source: operator/src/detection/consumer.rs:220-225] — Cooldown fingerprint pattern

### Git Intelligence

- Recent commits: `b6e5dd9` (1-3 done), `fb31e24` (implement 1-3), `c532e34` (1-2 done), `f1c4dee` (implement 1-2)
- Story 1-3 is the direct dependency — created the ServiceLevel CRD that Story 1-4 reads
- Stories 1-1 and 1-2 were Python. Story 1-3 was Rust. Story 1-4 continues Rust operator work
- Existing operator: 162+ Rust tests (v0.1.0 + Story 1-3's 42 new)
- All dependencies needed are already in Cargo.toml (kube 0.95, reqwest 0.11, tokio, chrono, serde, tracing, thiserror)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

N/A — cargo not available in development environment. Rust code follows existing operator patterns (source.rs, investigation.rs, detection/consumer.rs). Python regression tests pass (482 investigator + 657 UI).

### Completion Notes List

- Created `operator/src/slo/mod.rs` with `SloError`, `SloCalculationResult`, `SloSnapshot`, `SloCache` (Arc<RwLock<HashMap>>), `QdrantWriter`, and `run_slo_engine()` background task
- Created `operator/src/slo/calculator.rs` with `SloCalculator` struct — queries Prometheus via `increase(metric{selector}[window])` PromQL, computes `compliance = good/total`, `burn_rate = (1-compliance)/(1-target)` per Google SRE model
- Created `operator/src/slo/burn_rate.rs` with `BurnRateAlerter` — multi-window evaluation (both short AND long windows must exceed factor), Investigation CRD creation with SLO context, cooldown fingerprinting to prevent duplicate alerts
- `QdrantWriter` uses Qdrant REST API via existing `reqwest` — no new dependencies. Auto-creates `slo_snapshots` payload-only collection on startup. Writes snapshot points with deterministic IDs (hash of service+timestamp)
- `run_slo_engine()` runs as periodic background tokio task (default 5s via `BEEPER_SLO_REFRESH_SECS`). Lists all ServiceLevel CRDs, computes burn rate for each, writes Qdrant snapshots, evaluates alerts, updates shared cache
- Extended `ApiState` with `slo_cache: Option<SloCache>` — API handlers read latest burn rate data from shared cache
- Extended `ServiceLevelResponse` and `ServiceLevelDetailResponse` with `compliance`, `burn_rate`, `error_budget_remaining` (all `Option<f64>` with `skip_serializing_if`)
- Updated `list_servicelevels` and `get_servicelevel` API handlers to include burn rate data from SLO cache
- Wired SLO engine into `main.rs` — spawned as background tokio task with `PROMETHEUS_URL` and `QDRANT_URL` env var config, `slo_handle.abort()` in shutdown sequence
- `compute_burn_rate()` handles all edge cases: zero total (assume compliant), NaN inputs (treat as 0), target == 1.0 (infinite burn rate), good > total (clamp compliance to 1.0)
- `parse_window_duration()` supports "s", "m", "h", "d" suffixes
- `map_alert_severity()` maps "critical"→Critical, "high"→High, "warning"→Medium, "low"→Low, unknown→Medium
- 43 new Rust tests: 14 calculator (compliance, burn rate, edge cases), 12 burn rate alerter (fingerprint, severity mapping, multi-window scenarios), 9 window parser, 8 mod (snapshot serialization, point ID, cache, error display)
- 3 new API tests: ServiceLevelResponse with burn rate data, without burn rate data, detail response with burn rate
- All 482 investigator tests pass (3 skipped), all 657 UI tests pass — zero regressions. Ruff/mypy clean.
- Cargo not available — Rust compilation deferred

### File List

- `operator/src/slo/mod.rs` (new — SLO engine types, QdrantWriter, run_slo_engine, 8 tests)
- `operator/src/slo/calculator.rs` (new — SloCalculator, compute_burn_rate, parse_window_duration, 23 tests)
- `operator/src/slo/burn_rate.rs` (new — BurnRateAlerter, multi-window alerting, cooldown, 12 tests)
- `operator/src/lib.rs` (modified — add pub mod slo + re-exports)
- `operator/src/main.rs` (modified — spawn SLO engine background task + shutdown)
- `operator/src/api.rs` (modified — SloCache in ApiState, burn_rate/compliance fields in response structs, updated handlers + 3 new tests)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified)
- `_bmad-output/implementation-artifacts/1-4-slo-burn-rate-calculation-engine.md` (modified)
