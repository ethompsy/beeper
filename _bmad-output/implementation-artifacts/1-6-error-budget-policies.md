# Story 1.6: Error Budget Policies

Status: review

## Story

As an **admin**,
I want to define error budget policies that trigger notifications or deployment freezes,
so that teams are proactively alerted before SLO budgets are exhausted.

## Acceptance Criteria

1. **AC1: Threshold-based policy evaluation**
   **Given** a ServiceLevel CRD with error budget policy configuration
   **When** error budget consumption crosses a configured threshold (e.g., 50%, 75%, 90%)
   **Then** a notification event is generated with budget status and recommended action
   **And** the event includes the burn rate trend and projected budget exhaustion time

2. **AC2: Deployment freeze recommendation**
   **Given** an error budget policy with a "freeze" action at 95% consumption
   **When** budget consumption reaches 95%
   **Then** the system records a deployment freeze recommendation visible in the SLO dashboard
   **And** a critical notification is queued (when notification engine is available in Epic 2)

3. **AC3: Error budget status API endpoint**
   **Given** a ServiceLevel with error budget data
   **When** a user queries the error budget status
   **Then** the API returns current budget remaining, consumption, burn rate, projected exhaustion, freeze status, and triggered policy events

4. **AC4: Policy events are edge-triggered (not level-triggered)**
   **Given** a threshold that has already been crossed
   **When** the SLO engine evaluates the same ServiceLevel on the next cycle
   **Then** no duplicate event is generated
   **And** events are only generated on state transitions (crossing thresholds)

## Tasks / Subtasks

- [x] Task 1: Extend ServiceLevel CRD with error budget policy configuration (AC: #1, #2)
  - [x] 1.1: Add `ErrorBudgetPolicy` struct to `operator/src/crds/servicelevel.rs` with fields: `threshold: f64` (consumption fraction 0.0–1.0), `action: BudgetPolicyAction` (notify/freeze)
  - [x] 1.2: Add `BudgetPolicyAction` enum with `Notify` and `Freeze` variants, `#[serde(rename_all = "snake_case")]`
  - [x] 1.3: Add `error_budget_policies: Option<Vec<ErrorBudgetPolicy>>` to `ServiceLevelSpec` with `#[serde(skip_serializing_if = "Option::is_none")]`
  - [x] 1.4: Extend `validate_spec()` to validate error budget policies: thresholds must be in (0.0, 1.0], must be unique per ServiceLevel, reject NaN/negative
  - [x] 1.5: Update Helm CRD template `helm/beeper/templates/crds/servicelevel-crd.yaml` with `error_budget_policies` array in OpenAPI v3 schema
  - [x] 1.6: Add serialization tests for ErrorBudgetPolicy and BudgetPolicyAction, deserialization round-trip test with policies embedded in ServiceLevelSpec
  - [x] 1.7: Add validation tests for error budget policies: valid thresholds, out-of-range thresholds, NaN threshold, empty threshold list (allowed)

- [x] Task 2: Create `operator/src/slo/budget.rs` — Error budget policy evaluator (AC: #1, #2, #4)
  - [x] 2.1: Define `BudgetPolicyEvent` struct: `service: String`, `servicelevel_name: String`, `threshold: f64`, `current_consumption: f64`, `action: String` ("notify" or "freeze"), `burn_rate: f64`, `projected_exhaustion_secs: Option<f64>`, `triggered_at: String`
  - [x] 2.2: Define `BudgetPolicyState = Arc<RwLock<HashMap<String, ServiceBudgetStatus>>>` type where `ServiceBudgetStatus` holds: `is_frozen: bool`, `triggered_events: Vec<BudgetPolicyEvent>`, `triggered_thresholds: HashSet<u64>` (threshold * 10000 as u64 for fingerprinting)
  - [x] 2.3: Create `ErrorBudgetEvaluator` struct holding `BudgetPolicyState`
  - [x] 2.4: Implement `evaluate()` method: for each policy in the ServiceLevel's `error_budget_policies`, compute `consumption = 1.0 - error_budget_remaining`, check if `consumption >= threshold` AND threshold not already in `triggered_thresholds`, if so → generate event, add threshold to triggered set. If `consumption < threshold` AND threshold WAS in triggered set → remove it (recovery/hysteresis)
  - [x] 2.5: Implement projected exhaustion time calculation: `projected_secs = (error_budget_remaining * window_secs) / burn_rate` — reuse `parse_window_duration()` from `calculator.rs`. Return None if burn_rate <= 0 or error_budget_remaining <= 0
  - [x] 2.6: When a "freeze" action policy triggers → set `is_frozen = true` on the ServiceBudgetStatus. When budget recovers below the freeze threshold → set `is_frozen = false`
  - [x] 2.7: Log triggered events via `tracing::info!` with structured fields (service, threshold, consumption, action, projected_exhaustion)
  - [x] 2.8: Create `new_budget_policy_state() -> BudgetPolicyState` constructor

- [x] Task 3: Integrate budget evaluator into SLO engine loop (AC: #1, #2, #4)
  - [x] 3.1: Add `pub mod budget` to `operator/src/slo/mod.rs`
  - [x] 3.2: Import `ErrorBudgetEvaluator` and `BudgetPolicyState` in mod.rs
  - [x] 3.3: Accept `budget_policy_state: BudgetPolicyState` parameter in `run_slo_engine()`
  - [x] 3.4: Create `ErrorBudgetEvaluator` instance at start of engine loop
  - [x] 3.5: After burn rate calculation and alerter evaluation, call `evaluator.evaluate()` with the ServiceLevelSpec, SloCalculationResult, and spec.objective.window
  - [x] 3.6: Only call evaluator when `spec.error_budget_policies` is Some and non-empty

- [x] Task 4: Add error budget API endpoint and extend ServiceLevel responses (AC: #3)
  - [x] 4.1: Add `BudgetPolicyState` to `ApiState` struct in `operator/src/api.rs`
  - [x] 4.2: Create `ErrorBudgetResponse` struct: `service: String`, `target: f64`, `error_budget_total: f64` (1.0 - target), `error_budget_remaining: f64`, `error_budget_consumed: f64`, `burn_rate: f64`, `projected_exhaustion_secs: Option<f64>`, `is_frozen: bool`, `triggered_policies: Vec<BudgetPolicyEventResponse>`
  - [x] 4.3: Create `BudgetPolicyEventResponse` struct: `threshold: f64`, `action: String`, `triggered_at: String`, `consumption_at_trigger: f64`
  - [x] 4.4: Implement `GET /api/v1/slo/services/{name}/budget` endpoint handler — reads from SloCache for live data + BudgetPolicyState for policy state. Returns RFC 7807 404 if ServiceLevel not found
  - [x] 4.5: Add `is_frozen: Option<bool>` to `ServiceLevelResponse` and `ServiceLevelDetailResponse` with `#[serde(skip_serializing_if = "Option::is_none")]` — populated from BudgetPolicyState
  - [x] 4.6: Wire new endpoint and budget_policy_state into API router

- [x] Task 5: Wire budget policy state through main.rs (AC: #1, #2, #3)
  - [x] 5.1: Import `new_budget_policy_state` in `operator/src/main.rs`
  - [x] 5.2: Create `BudgetPolicyState` instance alongside `SloCache`
  - [x] 5.3: Clone and pass to `run_slo_engine()` and API server
  - [x] 5.4: Update `start_health_api_server()` signature to accept `BudgetPolicyState`

- [x] Task 6: Write comprehensive tests (AC: #1, #2, #3, #4)
  - [x] 6.1: ErrorBudgetPolicy serialization tests — action enum values ("notify", "freeze"), threshold serialization, full policy embedded in ServiceLevelSpec
  - [x] 6.2: Validation tests — valid thresholds (0.5, 0.75, 0.9, 0.95), invalid thresholds (0.0, -0.1, 1.5, NaN), duplicate thresholds
  - [x] 6.3: Budget evaluator unit tests — threshold crossing generates event, threshold not yet crossed generates nothing, recovery (consumption drops below threshold) clears triggered state
  - [x] 6.4: Edge-triggered behavior test — same threshold crossed twice in a row produces only one event (AC: #4)
  - [x] 6.5: Freeze action test — freeze policy at 0.95 triggers → is_frozen=true, budget recovers below 0.95 → is_frozen=false
  - [x] 6.6: Projected exhaustion test — with known burn_rate and window, verify projected seconds matches expected formula. Edge cases: burn_rate=0 → None, budget_remaining=0 → None
  - [x] 6.7: API ErrorBudgetResponse serialization test — verify all fields, skip_serializing_if behavior
  - [x] 6.8: ServiceLevel response with is_frozen field — present when Some, absent when None
  - [x] 6.9: Regression guard — all existing Python tests (482 investigator + 657 UI) must pass

## Dev Notes

### Architecture Compliance

**File Placement (from architecture.md):**
```
operator/src/slo/budget.rs    # Error budget tracking + policy enforcement
```
[Source: _bmad-output/planning-artifacts/architecture.md#Component Architecture]

**FR to File Mapping (from architecture.md):**
- FR5 (error budget policies): `operator/src/slo/budget.rs`
[Source: _bmad-output/planning-artifacts/architecture.md#FR to Structure Mapping]

**API Endpoint (from architecture.md):**
```
GET  /api/v1/slo/services/{name}/budget      # Error budget status
```
[Source: _bmad-output/planning-artifacts/architecture.md#API Endpoints]

**SLO Engine Data Flow (from architecture.md):**
```
Prometheus metrics → Operator ingestion → SLO calculator → slo_snapshots (Qdrant)
                                                         → Investigation priority scoring  (Story 1-5)
                                                         → Error budget policy evaluation  ← THIS STORY
                                                         → Notification urgency weighting  (Wave 2)
```
[Source: _bmad-output/planning-artifacts/architecture.md#SLO Engine Architecture (New)]

### Implementation Approach

**Key Design Decisions:**

1. **Error budget policies are part of ServiceLevel CRD (no separate CRD):**
   The architecture maps FR5 to `budget.rs` and the ServiceLevel CRD. No `ErrorBudgetPolicy` CRD is defined. Policies are configured inline:
   ```yaml
   apiVersion: beeper.dev/v1
   kind: ServiceLevel
   metadata:
     name: payments-slo
   spec:
     service: payment-service
     sli: { type: availability, metric: http_requests_total, ... }
     objective: { target: 0.999, window: 30d }
     burn_rate_alerts: [...]
     error_budget_policies:
       - threshold: 0.50
         action: notify
       - threshold: 0.75
         action: notify
       - threshold: 0.90
         action: notify
       - threshold: 0.95
         action: freeze
   ```

2. **Error budget consumption calculation:**
   Already available from `SloCalculationResult.error_budget_remaining`:
   ```
   consumption = 1.0 - error_budget_remaining
   ```
   Example: `error_budget_remaining = 0.5` → consumption = 0.5 (50% consumed)

3. **Edge-triggered events (not level-triggered):**
   Use a `HashSet<u64>` of triggered threshold fingerprints per ServiceLevel.
   Threshold fingerprint: `(threshold * 10000.0) as u64` (e.g., 0.50 → 5000, 0.95 → 9500).
   Event is generated ONLY when:
   - consumption >= threshold AND threshold NOT in triggered set
   On recovery (consumption < threshold AND threshold IN triggered set) → remove from set.
   This prevents duplicate events on every 5-second evaluation cycle.

4. **Projected exhaustion time:**
   ```
   projected_exhaustion_secs = (error_budget_remaining * window_secs) / burn_rate
   ```
   Reuse `parse_window_duration()` from `calculator.rs` (already public).
   - If `burn_rate <= 0.0` → None (not burning, infinite time)
   - If `error_budget_remaining <= 0.0` → None (already exhausted)
   Example: 50% remaining, 30d window, 5x burn → (0.5 × 2592000) / 5 = 259200 secs ≈ 3 days

5. **BudgetPolicyState shared state:**
   ```rust
   pub type BudgetPolicyState = Arc<RwLock<HashMap<String, ServiceBudgetStatus>>>;

   pub struct ServiceBudgetStatus {
       pub is_frozen: bool,
       pub triggered_events: Vec<BudgetPolicyEvent>,
       pub triggered_thresholds: HashSet<u64>,
   }
   ```
   Keyed by ServiceLevel CRD name (same as SloCache).
   Read by API, written by SLO engine.

6. **Freeze semantics:**
   A "freeze" action is a **recommendation** — the system records `is_frozen = true` on the `ServiceBudgetStatus`. The SLO dashboard (Story 1-7) will display this. The actual enforcement (blocking deployments) is out of scope.
   Freeze is reversible: if budget recovers below the freeze threshold, `is_frozen = false`.

7. **Notification queuing (deferred to Epic 2):**
   AC1 says "notification event is generated" — for now this means:
   - A `BudgetPolicyEvent` is stored in `BudgetPolicyState` (visible via API)
   - A `tracing::info!` log entry is emitted with all event details
   When the notification engine (Epic 2) is available, these events will be converted to outbox entries.

8. **API endpoint `GET /api/v1/slo/services/{name}/budget`:**
   Returns comprehensive budget status by combining SloCache data with BudgetPolicyState.
   404 if ServiceLevel not found (RFC 7807 error response, matching existing patterns).

9. **ServiceLevel response extension:**
   Add `is_frozen: Option<bool>` to both list and detail responses.
   None when no policy state exists (no policies configured), Some(false)/Some(true) when policies are active.

### Technical Requirements

- **Rust stable** — all operator code is Rust
- **kube-rs 0.95** — for K8s API (ServiceLevel CRD extension)
- **tokio 1** — async RwLock for BudgetPolicyState
- **serde + serde_json** — ServiceLevelSpec extension, BudgetPolicyEvent serialization
- **schemars** — JsonSchema derive for new types
- **tracing** — structured logging for policy events
- **chrono** — timestamps for triggered events
- **No new dependencies required** — all crates already in Cargo.toml

### Library & Framework Requirements

- Use `parse_window_duration()` from `calculator.rs` for window string parsing — do NOT duplicate
- Use `serde(rename_all = "snake_case")` on all new enums (BudgetPolicyAction)
- Use `#[serde(skip_serializing_if = "Option::is_none")]` on all Option fields
- Use RFC 7807 error responses for API errors (existing `ApiError` pattern)
- Use `tracing::info!` with structured fields for policy events — NOT `println!`

### File Structure Requirements

**New files to create:**
```
operator/src/slo/budget.rs                # ErrorBudgetEvaluator, BudgetPolicyEvent, ServiceBudgetStatus, BudgetPolicyState
```

**Files to modify:**
```
operator/src/crds/servicelevel.rs        # Add ErrorBudgetPolicy, BudgetPolicyAction, extend ServiceLevelSpec, extend validate_spec()
operator/src/slo/mod.rs                  # Add pub mod budget, accept BudgetPolicyState in run_slo_engine(), call evaluator
operator/src/api.rs                      # Add ErrorBudgetResponse, budget endpoint, is_frozen on ServiceLevel responses, BudgetPolicyState in ApiState
operator/src/main.rs                     # Create BudgetPolicyState, pass to SLO engine and API server
helm/beeper/templates/crds/servicelevel-crd.yaml  # Add error_budget_policies to OpenAPI v3 schema
```

### Testing Requirements

- **Framework:** Rust `#[cfg(test)]` modules with `#[test]` and `#[tokio::test]`
- **Test patterns:** Follow existing operator test patterns:
  - Pure function tests for validation (ErrorBudgetPolicy thresholds)
  - Serialization/deserialization round-trip tests
  - Async tests for evaluator with mock SLO data
  - Edge-triggered behavior verification (no duplicate events)
  - API response struct serialization tests
- **Regression:** All existing operator tests must pass. Python tests (482 investigator + 657 UI) serve as regression guard
- **Environment note:** Cargo may not be available — write correct Rust tests verified through code review

### Critical Guardrails

1. **DO NOT implement actual notification delivery.** That is Epic 2. Policy events are stored in BudgetPolicyState and logged via tracing — the notification outbox integration comes later.
2. **DO NOT implement deployment freeze enforcement.** The "freeze" action is a recommendation recorded in state and exposed via API. Actual deployment blocking is out of scope.
3. **DO NOT implement the SLO dashboard UI.** That is Story 1-7. But DO expose freeze status and policy events via API so Story 1-7 can display them.
4. **DO NOT add new crate dependencies to Cargo.toml.** Everything needed is already there.
5. **Follow existing Rust patterns exactly.** `#[serde(rename_all = "snake_case")]`, `#[serde(skip_serializing_if = "Option::is_none")]` on Option fields.
6. **Use `tracing` macros** (`info!`, `debug!`, `warn!`) — NOT `println!` or `log`.
7. **ServiceLevelSpec change MUST be backward-compatible.** `error_budget_policies` is `Option<Vec<>>` with `skip_serializing_if` — existing CRDs without policies will deserialize as None.
8. **Reuse `parse_window_duration()` from `calculator.rs`** for projected exhaustion calculation. Do NOT duplicate window parsing.
9. **Edge-triggered events are critical (AC4).** Each threshold fires exactly once per crossing. Test this explicitly.
10. **Freeze threshold recovery must work.** When budget recovers below the freeze threshold, `is_frozen` must reset to false.
11. **API budget endpoint must handle missing ServiceLevel gracefully.** Return RFC 7807 404, not a 500.
12. **`run_slo_engine()` signature change must be propagated to main.rs** — pass the new BudgetPolicyState parameter.
13. **Validation must reject NaN thresholds** — apply same NaN defense-in-depth pattern from ServiceLevel target validation.

### Previous Story Intelligence

**Story 1-5 (Customer Impact Scoring) — completed:**
- Added `impact_score: Option<f64>` to InvestigationSpec — same pattern to follow for `is_frozen: Option<bool>` on ServiceLevel responses
- Code review caught AC1 test data mismatch — use exact expected values in tests, not ranges
- Code review replaced weak range assertions with epsilon comparisons — apply same rigor

**Story 1-4 (SLO Burn Rate Calculation Engine) — direct dependency:**
- Created `SloCache = Arc<RwLock<HashMap<String, SloCalculationResult>>>` — BudgetPolicyState follows same pattern
- `SloCalculationResult.error_budget_remaining` is the input for budget consumption
- `run_slo_engine()` spawned as background task — budget evaluation hooks into same loop
- `parse_window_duration()` in `calculator.rs` is public and reusable
- Code review fixed: SLO cache not wired to API — ensure BudgetPolicyState is properly wired on first pass
- Code review added: cooldown HashMap cleanup at 1000 entries — apply similar cleanup to triggered_thresholds if needed

**Story 1-3 (ServiceLevel CRD) — indirect dependency:**
- Created `ServiceLevelSpec` with `burn_rate_alerts: Option<Vec<>>` — `error_budget_policies` follows identical pattern
- `validate_spec()` validates burn_rate_alerts — extend with error_budget_policies validation
- NaN defense on target validation — apply same to policy thresholds

**Code review patterns across stories 1-1 through 1-5:**
- Reviews consistently find 5 issues: 1 HIGH, 2-3 MEDIUM, 1-2 LOW
- HIGH issues: correctness/security edge cases, data not wired properly
- MEDIUM: dead code, missing type annotations, argument validation
- LOW: weak tests, missing edge case tests

### Project Structure Notes

- `budget.rs` is the 5th and final file in `operator/src/slo/` (after `mod.rs`, `calculator.rs`, `burn_rate.rs`, `impact.rs`)
- API response struct fields use `Option<T>` with `skip_serializing_if` — same pattern as `compliance`, `burn_rate`, `error_budget_remaining`, `impact_score`
- ServiceLevel CRD Helm template at `helm/beeper/templates/crds/servicelevel-crd.yaml`
- `start_health_api_server()` already takes multiple parameters (client, buffer, detection_stats, slo_cache, port) — adding BudgetPolicyState is consistent
- `api_router_full()` already takes `slo_cache` — extend with `budget_policy_state`

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#SLO Engine Architecture (New)] — Error budget tracking placement
- [Source: _bmad-output/planning-artifacts/architecture.md#Component Architecture] — budget.rs file location
- [Source: _bmad-output/planning-artifacts/architecture.md#FR to Structure Mapping] — FR5 mapping
- [Source: _bmad-output/planning-artifacts/architecture.md#API Endpoints] — budget endpoint
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.6] — Acceptance criteria and user story
- [Source: _bmad-output/planning-artifacts/prd.md#FR5] — Define error budget policies
- [Source: operator/src/slo/mod.rs] — SloCache type, SloCalculationResult, run_slo_engine
- [Source: operator/src/slo/calculator.rs] — parse_window_duration(), compute_burn_rate()
- [Source: operator/src/slo/burn_rate.rs] — BurnRateAlerter pattern, cooldown tracking
- [Source: operator/src/crds/servicelevel.rs] — ServiceLevelSpec, validate_spec(), BurnRateAlert pattern
- [Source: operator/src/api.rs] — ApiState, ServiceLevelResponse, API router pattern
- [Source: operator/src/main.rs] — Background task spawning, shared state wiring
- [Source: helm/beeper/templates/crds/servicelevel-crd.yaml] — OpenAPI v3 schema

### Git Intelligence

- Recent commits: `a8bc9b6` (1-5 done), `7ec0d58` (implement 1-5), `efe3c7a` (1-4 done), `503e187` (implement 1-4)
- All story implementations follow: create new file(s) → extend existing types → wire into main.rs → write tests
- Rust operator codebase has grown: slo/ module with 4 files, ~120+ tests from Stories 1-3 through 1-5

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- Implemented `ErrorBudgetPolicy` struct and `BudgetPolicyAction` enum in ServiceLevel CRD with full validation (threshold range, NaN, duplicates)
- Created `operator/src/slo/budget.rs` with `ErrorBudgetEvaluator`, `BudgetPolicyEvent`, `ServiceBudgetStatus`, edge-triggered evaluation with hysteresis
- Integrated budget evaluation into SLO engine loop (runs after burn rate alerts, before cache update)
- Added `GET /api/v1/slo/services/{name}/budget` endpoint with `ErrorBudgetResponse` and `BudgetPolicyEventResponse`
- Extended `ServiceLevelResponse` and `ServiceLevelDetailResponse` with `is_frozen: Option<bool>` from BudgetPolicyState
- Wired `BudgetPolicyState` through main.rs to both SLO engine and API server
- 10 new CRD tests + 15 budget evaluator tests + 5 new API tests = 30 new Rust tests
- All 482 investigator tests pass (3 skipped), all 657 UI tests pass. Ruff/mypy clean. Cargo not available — Rust compilation deferred.

### File List

**New files:**
- `operator/src/slo/budget.rs` — ErrorBudgetEvaluator, BudgetPolicyEvent, ServiceBudgetStatus, BudgetPolicyState, projected exhaustion, edge-triggered evaluation

**Modified files:**
- `operator/src/crds/servicelevel.rs` — ErrorBudgetPolicy, BudgetPolicyAction, error_budget_policies in ServiceLevelSpec, validate_spec() extensions, 10 new tests
- `operator/src/crds/mod.rs` — Added BudgetPolicyAction, ErrorBudgetPolicy to public exports
- `operator/src/controllers/servicelevel.rs` — Added error_budget_policies: None to test sample_spec()
- `operator/src/slo/mod.rs` — Added pub mod budget, budget_policy_state param to run_slo_engine(), ErrorBudgetEvaluator integration
- `operator/src/api.rs` — ErrorBudgetResponse, BudgetPolicyEventResponse, get_servicelevel_budget handler, is_frozen on responses, BudgetPolicyState in ApiState, 5 new tests
- `operator/src/main.rs` — new_budget_policy_state(), wired to SLO engine and API server
- `helm/beeper/templates/crds/servicelevel-crd.yaml` — error_budget_policies in OpenAPI v3 schema
