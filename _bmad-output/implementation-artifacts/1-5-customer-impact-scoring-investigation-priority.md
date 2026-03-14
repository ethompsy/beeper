# Story 1.5: Customer Impact Scoring & Investigation Priority

Status: review

## Story

As an **SRE**,
I want anomalies scored by customer impact using SLO data rather than static severity labels,
so that I can focus on issues that actually affect users first.

## Acceptance Criteria

1. **AC1: Customer impact scoring from SLO data**
   **Given** an anomaly detected on a service with an active ServiceLevel CRD
   **When** the detection consumer scores the anomaly
   **Then** customer impact is calculated based on SLO breach severity and error budget remaining
   **And** an anomaly affecting a 99.9% SLO with 50% budget remaining scores higher than one affecting a 99% SLO with 90% budget remaining

2. **AC2: Investigation list sorted by impact severity**
   **Given** multiple investigations are active simultaneously
   **When** an SRE views the investigation list
   **Then** investigations are sorted by SLO impact severity (highest impact first)
   **And** the impact score is visible on each investigation card

3. **AC3: Impact score on SLO-triggered investigations**
   **Given** the SLO burn rate alerter creates an Investigation CRD
   **When** the investigation is created
   **Then** the impact score is calculated from the ServiceLevel's target, burn rate, and error budget remaining
   **And** the score is stored in the Investigation CRD spec

4. **AC4: Graceful degradation when no SLO data**
   **Given** an anomaly detected on a service with NO active ServiceLevel CRD
   **When** the detection consumer attempts scoring
   **Then** impact_score is None (not populated)
   **And** severity-based sorting still functions as a fallback

## Tasks / Subtasks

- [x] Task 1: Create `operator/src/slo/impact.rs` — Customer impact scorer (AC: #1, #3)
  - [x] 1.1: Create `CustomerImpactScorer` struct holding a reference to `SloCache`
  - [x] 1.2: Implement `score_service(service: &str) -> Option<f64>` — looks up service in SloCache, computes impact score (0.0 to 1.0) based on: SLO target stringency, burn rate severity, error budget depletion
  - [x] 1.3: Implement scoring formula: `impact = w_target * target_factor + w_burn * burn_factor + w_budget * budget_factor` where `target_factor = (target - 0.9) / 0.1` (normalized: 99.9% → 0.9, 99% → 0.0), `burn_factor = min(1.0, burn_rate / 10.0)` (capped at 10x), `budget_factor = 1.0 - error_budget_remaining` (less budget = higher impact). Default weights: w_target=0.3, w_burn=0.4, w_budget=0.3
  - [x] 1.4: Clamp final score to [0.0, 1.0]
  - [x] 1.5: Handle multi-SLO services — if multiple ServiceLevel CRDs reference the same service, use the HIGHEST impact score
  - [x] 1.6: Return None when service has no ServiceLevel CRDs in cache (AC: #4)

- [x] Task 2: Extend InvestigationSpec with impact_score field (AC: #1, #2)
  - [x] 2.1: Add `impact_score: Option<f64>` field to `InvestigationSpec` in `operator/src/crds/investigation.rs` with `#[serde(skip_serializing_if = "Option::is_none")]`
  - [x] 2.2: Update the Helm CRD template `helm/templates/crds/investigation-crd.yaml` to include `impact_score` in OpenAPI v3 schema (type: number, format: double, nullable: true)
  - [x] 2.3: Update existing `InvestigationSpec` test to verify impact_score serialization (None → absent, Some(0.85) → present)

- [x] Task 3: Integrate impact scoring into detection consumer (AC: #1, #4)
  - [x] 3.1: Add `SloCache` parameter to `DetectionConsumer::run()` (optional, like in API)
  - [x] 3.2: Create `CustomerImpactScorer` from SloCache at start of `run()`
  - [x] 3.3: Before creating Investigation CRD, call `scorer.score_service(&event.service)` to get impact_score
  - [x] 3.4: Set `impact_score` field on `InvestigationSpec` (Some(score) if SLO data exists, None otherwise)
  - [x] 3.5: Update main.rs to pass `slo_cache.clone()` to detection consumer

- [x] Task 4: Integrate impact scoring into burn rate alerter (AC: #3)
  - [x] 4.1: Pass `SloCache` to `BurnRateAlerter` (it already has burn rate data available, but the scorer provides the normalized composite score)
  - [x] 4.2: When creating SLO-triggered Investigation CRDs, compute and set `impact_score` from the same scorer
  - [x] 4.3: For burn rate alerts, the scorer already has data from the same service — use it

- [x] Task 5: Extend API with impact score and priority sorting (AC: #2)
  - [x] 5.1: Add `impact_score: Option<f64>` to `InvestigationResponse` and `InvestigationDetailResponse` with `#[serde(skip_serializing_if = "Option::is_none")]`
  - [x] 5.2: Read `impact_score` from `InvestigationSpec` in `list_investigations` handler
  - [x] 5.3: Update investigation sorting: primary sort by status priority (existing), secondary sort by `impact_score` descending (highest impact first), tertiary sort by `started_at` descending (existing fallback)
  - [x] 5.4: When `impact_score` is None, sort those below scored investigations within the same status group

- [x] Task 6: Write comprehensive tests (AC: #1, #2, #3, #4)
  - [x] 6.1: Impact scorer unit tests — scoring formula with known SLO data (99.9% target / 50% budget / 5x burn → high score; 99% target / 90% budget / 1x burn → low score), edge cases (no cache data → None, empty cache → None, NaN defense)
  - [x] 6.2: Multi-SLO service test — two ServiceLevels for same service, highest score wins
  - [x] 6.3: InvestigationSpec serialization — impact_score None (field absent), Some(0.85) (field present)
  - [x] 6.4: API response tests — InvestigationResponse with impact_score, sorting by impact within status groups
  - [x] 6.5: Integration scenario — detection event → SLO lookup → impact-scored Investigation CRD
  - [x] 6.6: Verify all existing operator tests still pass (Python tests: 482 investigator + 657 UI as regression guard)

## Dev Notes

### Architecture Compliance

**File Placement (from architecture.md):**
```
operator/src/slo/impact.rs    # Customer impact scoring for anomaly prioritization
```
[Source: _bmad-output/planning-artifacts/architecture.md#Component Architecture]

**FR to File Mapping (from architecture.md):**
- FR4 (SLO-based scoring): `operator/src/slo/impact.rs`, `operator/src/detection/consumer.rs`
- FR7 (investigation priority): `operator/src/slo/impact.rs` → `operator/src/detection/consumer.rs`
- FR21 (impact-weighted urgency): `operator/src/slo/impact.rs` → `operator/src/notifications/router.rs` (Wave 2 — not in scope, but design `score_service()` so notifications can reuse it)
[Source: _bmad-output/planning-artifacts/architecture.md#FR to Structure Mapping]

**SLO Engine Data Flow (from architecture.md):**
```
Prometheus metrics → Operator ingestion → SLO calculator → slo_snapshots (Qdrant)
                                                         → Investigation priority scoring  ← THIS STORY
                                                         → Notification urgency weighting  (Wave 2)
```
[Source: _bmad-output/planning-artifacts/architecture.md#SLO Engine Architecture (New)]

**Customer Impact Scoring Design (from architecture.md):**
> Customer Impact Scoring: Anomalies correlated with SLO breach severity. An anomaly affecting a 99.9% SLO with 50% budget remaining scores higher than one affecting a 99% SLO with 90% budget remaining.
[Source: _bmad-output/planning-artifacts/architecture.md#SLO Engine Architecture (New)]

### Implementation Approach

**Key Design Decisions:**

1. **Impact scoring formula (composite of 3 factors):**
   ```
   target_factor = clamp((target - 0.9) / 0.1, 0.0, 1.0)
     → 99.9% (0.999) → 0.99, 99% (0.99) → 0.9, 95% (0.95) → 0.5, 90% (0.9) → 0.0

   burn_factor = clamp(burn_rate / 10.0, 0.0, 1.0)
     → 1x burn → 0.1, 5x → 0.5, 10x+ → 1.0

   budget_factor = clamp(1.0 - error_budget_remaining, 0.0, 1.0)
     → 90% remaining → 0.1 (low impact), 50% remaining → 0.5, 10% remaining → 0.9

   impact_score = 0.3 * target_factor + 0.4 * burn_factor + 0.3 * budget_factor
   ```
   This ensures: 99.9% SLO / 50% budget / 5x burn ≈ 0.3×0.99 + 0.4×0.5 + 0.3×0.5 = 0.647
   vs. 99% SLO / 90% budget / 1x burn ≈ 0.3×0.9 + 0.4×0.1 + 0.3×0.1 = 0.340
   Satisfying AC1: higher target + lower budget + higher burn → higher score.

2. **SloCache access pattern:**
   `CustomerImpactScorer` takes `SloCache` (which is `Arc<RwLock<HashMap<String, SloCalculationResult>>>`).
   Call `cache.read().await` for non-blocking read access. The SLO engine writes every 5s, so data is always fresh.
   ```rust
   pub struct CustomerImpactScorer {
       cache: SloCache,
   }

   impl CustomerImpactScorer {
       pub fn new(cache: SloCache) -> Self { Self { cache } }

       pub async fn score_service(&self, service: &str) -> Option<f64> {
           let guard = self.cache.read().await;
           // Find all SloCalculationResults where result.service == service
           // Return highest impact score, or None if no matches
       }
   }
   ```

3. **Multi-SLO handling:**
   Multiple ServiceLevel CRDs can reference the same service (e.g., availability SLO + latency SLO).
   The SloCache is keyed by ServiceLevel CRD name, not by service name.
   `score_service()` must iterate all cache entries, filter by `result.service == service`, compute impact for each, and return the maximum.

4. **InvestigationSpec extension:**
   Add one optional field. No CRD version bump needed — additive optional field is backward-compatible.
   ```rust
   pub struct InvestigationSpec {
       pub condition: String,
       pub service: String,
       #[serde(default)]
       pub severity: Severity,
       #[serde(skip_serializing_if = "Option::is_none")]
       pub triggered_at: Option<String>,
       #[serde(skip_serializing_if = "Option::is_none")]
       pub impact_score: Option<f64>,  // NEW: 0.0-1.0, None if no SLO data
   }
   ```

5. **Detection consumer integration:**
   `DetectionConsumer::run()` currently takes `buffer, client, namespace`.
   Add `slo_cache: Option<SloCache>` parameter. When Some, create `CustomerImpactScorer` and call `score_service()` before each Investigation CRD creation. When None, set `impact_score: None`.

6. **Burn rate alerter integration:**
   `BurnRateAlerter::evaluate()` already has access to burn rate data. Pass `SloCache` to it (or create scorer there) so SLO-triggered investigations also get impact scores. The scorer's `score_service()` is the canonical scoring function — both detection and burn rate paths use it.

7. **API sorting change:**
   Current sort: `status_priority → started_at desc`
   New sort: `status_priority → impact_score desc (None last) → started_at desc`
   ```rust
   investigations.sort_by(|a, b| {
       let order_cmp = status_sort_order(&a.status).cmp(&status_sort_order(&b.status));
       if order_cmp != std::cmp::Ordering::Equal {
           return order_cmp;
       }
       // Impact score descending (higher = more important), None sorts last
       let impact_cmp = b.impact_score.partial_cmp(&a.impact_score)
           .unwrap_or(if a.impact_score.is_none() && b.impact_score.is_none() {
               std::cmp::Ordering::Equal
           } else if a.impact_score.is_none() {
               std::cmp::Ordering::Greater  // a (None) sorts after b (Some)
           } else {
               std::cmp::Ordering::Less     // a (Some) sorts before b (None)
           });
       if impact_cmp != std::cmp::Ordering::Equal {
           return impact_cmp;
       }
       b.started_at.as_deref().unwrap_or("").cmp(a.started_at.as_deref().unwrap_or(""))
   });
   ```

8. **This story does NOT implement:**
   - Error budget policies (Story 1-6: `operator/src/slo/budget.rs`)
   - SLO compliance dashboard UI (Story 1-7)
   - Notification urgency weighting (FR21 — Wave 2, will reuse `score_service()`)
   - Trust-level gating (Wave 2)

### Technical Requirements

- **Rust stable** — all operator code is Rust
- **kube-rs 0.95** — for K8s API (Investigation CRD creation)
- **tokio 1** — async RwLock for SloCache read access
- **serde + serde_json** — InvestigationSpec extension
- **schemars** — JsonSchema derive for new field
- **tracing** — structured logging
- **No new dependencies required** — all crates already in Cargo.toml

### File Structure Requirements

**New files to create:**
```
operator/src/slo/impact.rs                # CustomerImpactScorer + scoring formula + tests
```

**Files to modify:**
```
operator/src/slo/mod.rs                   # Add pub mod impact
operator/src/crds/investigation.rs        # Add impact_score field to InvestigationSpec
operator/src/detection/consumer.rs        # Pass SloCache, compute impact before Investigation creation
operator/src/slo/burn_rate.rs             # Pass SloCache, compute impact for SLO-triggered investigations
operator/src/api.rs                       # Add impact_score to responses, update sort order
operator/src/main.rs                      # Pass slo_cache to detection consumer
helm/templates/crds/investigation-crd.yaml  # Add impact_score to OpenAPI schema
```

### Testing Requirements

- **Framework:** Rust `#[cfg(test)]` modules with `#[test]` and `#[tokio::test]`
- **Test patterns:** Follow existing operator test patterns:
  - Pure function tests for scoring formula (target_factor, burn_factor, budget_factor, composite)
  - Async tests for SloCache-based scoring (create cache with known data, verify scores)
  - Serialization tests for extended InvestigationSpec
  - Sort order tests for API response
  - Edge cases: NaN inputs, empty cache, missing service, target == 1.0
- **Regression:** All existing operator tests must pass. Python tests (482 investigator + 657 UI) serve as regression guard
- **Environment note:** Cargo may not be available — write correct Rust tests verified through code review

### Critical Guardrails

1. **DO NOT implement error budget policies.** That is Story 1-6 (`operator/src/slo/budget.rs`).
2. **DO NOT implement the SLO dashboard UI.** That is Story 1-7.
3. **DO NOT implement notification urgency weighting.** That is FR21/Wave 2. But DO design `score_service()` as a reusable function that notifications can call later.
4. **DO NOT add new crate dependencies to Cargo.toml.** Everything needed is already there.
5. **Follow existing Rust patterns exactly.** `#[serde(rename_all = "snake_case")]`, `#[serde(skip_serializing_if = "Option::is_none")]` on Option fields.
6. **Use `tracing` macros** (`info!`, `debug!`, `warn!`) — NOT `println!` or `log`.
7. **InvestigationSpec change MUST be backward-compatible.** `impact_score` is `Option<f64>` with `skip_serializing_if = "Option::is_none"` — existing CRDs without this field will deserialize as None.
8. **CustomerImpactScorer must be async** because `SloCache.read()` returns a future (tokio RwLock).
9. **Multi-SLO services:** Always take the HIGHEST impact score across all ServiceLevel CRDs for a given service.
10. **Scoring must satisfy AC1 ordering:** 99.9% SLO / 50% budget MUST score higher than 99% SLO / 90% budget. Verify this in tests with concrete numbers.
11. **API sort must not break existing behavior.** Status sort order is unchanged. Impact sort is secondary, within each status group. Investigations without impact scores sort below those with scores.
12. **Detection consumer's `run()` signature change must be propagated to main.rs** — pass the shared `SloCache` clone.
13. **Burn rate alerter must not duplicate scoring logic.** Use the same `CustomerImpactScorer::score_service()` function.

### Previous Story Intelligence

**Story 1-4 (SLO Burn Rate Calculation Engine) — Direct dependency:**
- Created `SloCache = Arc<RwLock<HashMap<String, SloCalculationResult>>>` — Story 1-5 reads this
- `SloCalculationResult` fields: `service`, `sli_type`, `compliance`, `burn_rate`, `error_budget_remaining`, `good_count`, `total_count`, `timestamp`
- Cache is keyed by ServiceLevel CRD name (NOT service name) — must iterate to find by service
- Code review fixed: SLO cache not wired to API (was hardcoded None) — now passed via `api_router_full()`
- Code review added: cooldown HashMap cleanup at 1000 entries
- `run_slo_engine()` spawned as background task in main.rs

**Story 1-3 (ServiceLevel CRD & Controller) — Indirect dependency:**
- Created `ServiceLevelSpec` with `service`, `sli`, `objective`, `burn_rate_alerts`
- `ObjectiveSpec` has `target` (f64, 0.0-1.0) and `window` (String)
- Code review caught: `SliType` Debug format bug — use `sli_type_to_string()` helper
- NaN defense-in-depth on target validation — apply similar NaN defense in scoring

**Story 1-1 (Permission Model) code review insight:**
- Security edge case (JWT fallthrough) caught — validate all edge cases in impact scoring
- Weak tests caught — write strong assertions with concrete expected values

**Code review patterns across stories 1-1 through 1-4:**
- Reviews consistently find 5 issues: 1 HIGH, 2-3 MEDIUM, 1-2 LOW
- HIGH issues: correctness/security edge cases
- MEDIUM: dead code, missing type annotations, argument validation
- LOW: weak tests, missing edge case tests

### Project Structure Notes

- `impact.rs` is the 4th file in `operator/src/slo/` (after `mod.rs`, `calculator.rs`, `burn_rate.rs`)
- `budget.rs` (Story 1-6) is the only remaining slo/ file — do NOT create it
- Detection consumer currently takes `(buffer, client, namespace)` — adding `slo_cache` parameter follows the pattern of optional dependencies in API router functions
- API response struct fields use `Option<f64>` with `skip_serializing_if` — same pattern as `compliance`, `burn_rate`, `error_budget_remaining` fields added in Story 1-4
- Investigation CRD Helm template at `helm/templates/crds/investigation-crd.yaml` — update OpenAPI schema

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#SLO Engine Architecture (New)] — Customer impact scoring placement and data flow
- [Source: _bmad-output/planning-artifacts/architecture.md#Component Architecture] — impact.rs file location
- [Source: _bmad-output/planning-artifacts/architecture.md#FR to Structure Mapping] — FR4, FR7, FR21 mapping
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.5] — Acceptance criteria and user story
- [Source: _bmad-output/planning-artifacts/prd.md#FR4] — Score anomalies by customer impact using SLO data
- [Source: _bmad-output/planning-artifacts/prd.md#FR7] — Prioritize investigations by SLO impact severity
- [Source: operator/src/slo/mod.rs] — SloCache type definition, SloCalculationResult fields
- [Source: operator/src/crds/investigation.rs] — InvestigationSpec, Severity enum
- [Source: operator/src/detection/consumer.rs] — Detection loop, Investigation creation pattern
- [Source: operator/src/slo/burn_rate.rs] — Burn rate alerter Investigation creation
- [Source: operator/src/api.rs] — InvestigationResponse, sort logic, ApiState
- [Source: operator/src/main.rs] — Background task spawning, SloCache wiring

### Git Intelligence

- Recent commits: `efe3c7a` (1-4 done), `503e187` (implement 1-4), `b6e5dd9` (1-3 done), `fb31e24` (implement 1-3)
- Story 1-4 is the direct dependency — created SloCache and burn rate calculation that Story 1-5 consumes
- All story implementations followed: create new file(s) → extend existing types → wire into main.rs → write tests
- Rust operator codebase has grown: slo/ module with 3 files, ~46 tests from Stories 1-3 and 1-4

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

N/A

### Completion Notes List

- Created `CustomerImpactScorer` in `operator/src/slo/impact.rs` with composite scoring formula: `impact = 0.3 * target_factor + 0.4 * burn_factor + 0.3 * budget_factor`. Target factor normalizes SLO target (0.9→0.0, 1.0→1.0), burn factor caps at 10x, budget factor = 1 - remaining. All factors clamped to [0.0, 1.0] with NaN defense.
- `score_service()` is async (reads tokio RwLock), iterates all SloCache entries matching service name, returns highest score (multi-SLO support). Returns None when no SLO data exists (AC4 graceful degradation).
- Extended `InvestigationSpec` with `impact_score: Option<f64>` using `skip_serializing_if`. Backward-compatible — no CRD version bump needed.
- Updated Helm CRD template with `impact_score` in OpenAPI v3 schema (type: number, format: double).
- Integrated scoring into both detection consumer (`slo_cache` parameter on `run()`) and burn rate alerter (`with_slo_cache()` constructor). Both use the same `CustomerImpactScorer::score_service()` — no duplicated logic.
- Updated `main.rs` to clone `slo_cache` before SLO engine spawn to avoid moved value issue, passing clone to detection consumer.
- Extended API responses (`InvestigationResponse`, `InvestigationDetailResponse`) with `impact_score`. Updated sort to 3-level: status priority → impact_score desc (None last) → started_at desc.
- AC1 verified with concrete test: 99.9% SLO / 50% budget / 5x burn = 0.647 > 99% SLO / 90% budget / 1x burn = 0.340.
- 28 new Rust tests in impact.rs, 3 new tests in investigation.rs, 4 new tests in api.rs. All 482 investigator + 657 UI Python tests pass (zero regressions).

### File List

- `operator/src/slo/impact.rs` (NEW) — CustomerImpactScorer, scoring formula, 28 tests
- `operator/src/slo/mod.rs` (MODIFIED) — Added `pub mod impact`, updated BurnRateAlerter to use `with_slo_cache()`
- `operator/src/crds/investigation.rs` (MODIFIED) — Added `impact_score: Option<f64>` to InvestigationSpec, 3 new tests
- `operator/src/detection/consumer.rs` (MODIFIED) — Added `slo_cache` parameter, impact scoring integration
- `operator/src/slo/burn_rate.rs` (MODIFIED) — Added `impact_scorer` field, `with_slo_cache()` constructor
- `operator/src/api.rs` (MODIFIED) — Added impact_score to responses, updated sort order, 4 new tests
- `operator/src/main.rs` (MODIFIED) — Cloned slo_cache for detection consumer
- `operator/src/investigator_job.rs` (MODIFIED) — Updated test InvestigationSpec constructions with `impact_score: None`
- `helm/beeper/templates/crds/investigation-crd.yaml` (MODIFIED) — Added impact_score to OpenAPI v3 schema
