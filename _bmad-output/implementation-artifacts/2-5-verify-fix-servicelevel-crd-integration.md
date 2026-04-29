# Story 2.5: Verify/Fix ServiceLevel CRD Integration

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want the operator to read ServiceLevel CRDs and the investigator to incorporate SLO breach data,
So that investigations include customer impact context when SLOs are breached.

## Background

**Epic 2 dependency chain:** 2.1 (lifecycle) → 2.2 (signal gathering) → 2.3 (KB integration) → 2.4 (LLM RCA) → **2.5 (ServiceLevel CRD)**

Stories 2.1–2.4 fixed the investigation pipeline from lifecycle management through LLM root cause analysis. This final Epic 2 story closes the SLO integration gap: the operator already reads ServiceLevel CRDs and calculates burn rates, but that data never reaches the investigator's LLM context. The result is investigations that miss customer impact signals from SLO breaches.

**PRD context (FR20–FR21):**
- FR20: Operator can read ServiceLevel CRDs to determine SLO targets per service
- FR21: Investigator can incorporate SLO breach data into investigation context

**PRD success criterion:** "payment-failure fault injection produces a specific, evidence-backed investigation 3/3 consecutive runs." SLO breach data enriches this by adding customer impact context (e.g., "checkout availability SLO at 97.2% vs 99.9% target, burn rate 28x").

## Acceptance Criteria

1. **Given** ServiceLevel CRDs are deployed in the cluster defining SLO targets per service
   **When** the operator's servicelevel controller reconciles them
   **Then** SLO targets are read and available for investigation context **(FR20)**

2. **Given** an investigation is running for a service with a defined ServiceLevel CRD
   **When** the investigator gathers context for LLM analysis
   **Then** SLO breach data (if any) is included in the investigation context passed to the LLM **(FR21)**

3. **Given** no ServiceLevel CRD exists for the anomalous service
   **When** the investigator gathers context
   **Then** the investigation proceeds normally without SLO data — absence is handled gracefully, not as an error

## Tasks / Subtasks

- [x] Task 1: Verify operator-side ServiceLevel CRD reading (AC: #1)
  - [x] 1.1 Run existing Rust tests: `cargo test --lib` — **572 passed**, 0 failed, 0 ignored (0.05s)
  - [x] 1.2 Verify SLO engine tests pass: included in `cargo test --lib` — calculator, burn_rate, budget, impact modules all pass ✓
  - [x] 1.3 Verify ServiceLevel controller is registered in `operator/src/controllers/mod.rs` (line 15: `pub use servicelevel::run_servicelevel_controller`) ✓
  - [x] 1.4 Verify SLO engine is spawned in `operator/src/main.rs` (line 262: `run_slo_engine()`, line 232: `run_servicelevel_controller()`) ✓
  - [x] 1.5 Document: operator reads ServiceLevel CRDs ✓, calculates burn_rate/compliance ✓, writes snapshots to Qdrant `slo_snapshots` ✓ — **FR20 satisfied on operator side**

- [x] Task 2: Fix ServiceTopologyStep field extraction (AC: #1, #2)
  - [x] 2.1 Audit `service_topology.py` lines 289-310: confirmed wrong field extraction ✓
  - [x] 2.2 **BUG CONFIRMED:** `status.burnRate`/`status.compliance` DON'T EXIST — actual status has `condition`, `last_evaluated`, `alerts_registered`, `error` ✓
  - [x] 2.3 Fixed field extraction: reads `spec.objective.target`, `spec.service`, `spec.sli.type`, `status.condition` ✓
  - [x] 2.4 Added `_query_slo_snapshot()`: queries Qdrant REST API `POST /collections/slo_snapshots/points/scroll` with service filter ✓
  - [x] 2.5 Updated health classification: critical if `burn_rate > 10`, warning if `burn_rate > 1`, healthy otherwise ✓

- [x] Task 3: Wire SLO data into pipeline_metadata (AC: #2)
  - [x] 3.1 Added `_extract_slo_for_service()` — stores `slo_target`, `slo_compliance`, `slo_burn_rate`, `slo_error_budget_remaining`, `slo_sli_type`, `slo_condition` in `StepResult.data` ✓
  - [x] 3.2 Verified `agent.py:349` merges StepResult.data into pipeline_metadata — SLO data flows to downstream steps ✓
  - [x] 3.3 Verified ServiceTopologyStep (step 5) runs BEFORE RCA (step 7) and recommendations (step 8) ✓

- [x] Task 4: Enhance LLM prompts with SLO context (AC: #2)
  - [x] 4.1 `rca_hypothesis.py`: added `{slo_context}` to user template, `_extract_slo_data()`, `_format_slo_context()` ✓
  - [x] 4.2 `resolution_recommendations.py`: added `{slo_context}` to user template, `_extract_slo_data()`, `_format_slo_context()` ✓
  - [x] 4.3 Both system prompts: added SLO instruction ("If SLO breach data is provided, reference the specific target, current compliance, and burn rate...") ✓
  - [x] 4.4 Clean omission: `_format_slo_context()` returns empty string when no `slo_target` — section omitted entirely ✓

- [x] Task 5: Handle graceful absence of SLO data (AC: #3)
  - [x] 5.1 ServiceTopologyStep: K8s ApiException caught, returns empty SLO fields ✓
  - [x] 5.2 Qdrant query: connection errors, non-200, empty points all return None → empty SLO fields ✓
  - [x] 5.3 LLM prompts: `_format_slo_context()` returns "" when no target → section omitted cleanly ✓
  - [x] 5.4 Tests confirm investigation completes normally without SLO data ✓

- [x] Task 6: Write/update tests (AC: all)
  - [x] 6.1 `test_service_topology.py`: 4 new test classes — TestSLOCRDFieldExtraction, TestQdrantSnapshotQuery, TestSLOPipelinePropagation, TestGracefulAbsence ✓
  - [x] 6.2 `test_rca_hypothesis.py`: TestSLOContextInPrompt — 3 tests (present, absent, system prompt) ✓
  - [x] 6.3 `test_resolution_recommendations.py`: TestSLOContextInResolutionPrompt — 3 tests (present, absent, system prompt) ✓
  - [x] 6.4 Full test suite: **131/131 passed** (43 RCA, 52 recommendations, 36 service topology) ✓

- [~] Task 7: E2E verification (AC: all) — **DEFERRED (pre-existing blocker)**
  - [ ] 7.1–7.4 Deferred: operator OOMKill (documented in Stories 2.2, 2.3, 2.4) blocks E2E
  - [x] 7.5 **Documented:** E2E blocked by pre-existing operator OOMKill. Unit test coverage (131/131) is primary validation. SLO integration is fully tested at unit level ✓

## Dev Notes

### Current State Analysis

**Operator side — FULLY WORKING:**
- ServiceLevel controller (`operator/src/controllers/servicelevel.rs`, 291 lines): watches all ServiceLevel CRDs, validates specs, updates `status.condition` to Healthy/Critical
- SLO engine (`operator/src/slo/mod.rs`, 520 lines): runs as background task, queries Prometheus every 5s, calculates compliance/burn_rate/error_budget, writes `SloSnapshot` to Qdrant `slo_snapshots` collection
- SLO calculator (`operator/src/slo/calculator.rs`, 359 lines): queries Prometheus `increase(metric{selector}[window])`, computes compliance = good/total
- Burn rate alerter (`operator/src/slo/burn_rate.rs`, 384 lines): multi-window alerting (Google SRE pattern), creates Investigation CRDs with `impact_score` when alerts fire
- Error budget policies (`operator/src/slo/budget.rs`, 670 lines): edge-triggered evaluation, supports Notify/Freeze actions
- Impact scorer (`operator/src/slo/impact.rs`, 473 lines): composite formula (0.3*target + 0.4*burn_rate + 0.3*budget)

**Investigator side — BROKEN (3 gaps):**

1. **Wrong field extraction** (`service_topology.py:289-310`): reads `status.burnRate` and `status.compliance` from ServiceLevel CRD status — these fields DON'T EXIST. Actual status: `condition`, `last_evaluated`, `alerts_registered`, `error`
2. **Missing Qdrant query**: burn_rate/compliance are in `slo_snapshots` Qdrant collection, NOT in CRD status. Investigator has no code to query this collection
3. **No pipeline propagation**: even if extraction worked, SLO data is NOT stored in `StepResult.data` and NOT available in `pipeline_metadata` for LLM steps

### Data Flow Gap Diagram

```
ServiceLevel CRD → Operator reads & validates           ✓
                 → SLO Engine calculates burn_rate       ✓
                 → Snapshots → Qdrant slo_snapshots      ✓
                 → Investigator ServiceTopologyStep       ✗ (wrong field names)
                 → Qdrant query for slo_snapshots        ✗ (missing entirely)
                 → pipeline_metadata for LLM steps       ✗ (not stored)
                 → LLM prompt with SLO context           ✗ (not included)
```

### Architecture Context

- **SLO engine refresh interval:** 5 seconds (`operator/src/slo/mod.rs:248`)
- **Qdrant collection:** `slo_snapshots` — payload-only (no vectors), created by operator SLO engine
- **SloSnapshot fields:** `service`, `sli_type`, `compliance`, `burn_rate`, `error_budget_remaining`, `good_count`, `total_count`, `timestamp`
- **ServiceLevel CRD status fields:** `condition` (Healthy/Critical), `last_evaluated`, `alerts_registered`, `error`
- **ServiceLevel CRD spec fields:** `service`, `sli.type`, `sli.metric`, `objective.target`, `objective.window`, `burn_rate_alerts[]`, `error_budget_policies[]`
- **Demo ServiceLevel CRDs:** 4 files in `demo/k8s/`: slo-checkout.yaml, slo-frontend.yaml, slo-cart.yaml, slo-productcatalog.yaml
- **Investigation pipeline ordering:** ServiceTopologyStep is step 5, RCA is step 7, Recommendations is step 8 — SLO data available before LLM steps

### Key Patterns from Story 2.4

Story 2.4 established the pattern for adding new data to LLM prompts:
1. Store data in `StepResult.data` dict (e.g., `raw_signal_detail`, `temporal_summary`)
2. Data flows through `pipeline_metadata` via `agent.py:349`
3. Downstream steps extract with `_extract_signal_data()` or similar helper
4. Add to user prompt template with "No X available" defaults
5. Add system prompt instruction to reference the data

**Follow this exact pattern for SLO data integration.**

### Pre-existing Issues

- **Operator OOMKill:** SLO engine memory leak documented in Stories 2.2, 2.3, 2.4. Operator restarts frequently (141+ restarts observed). E2E verification may be blocked. Unit test coverage is primary validation.
- **Pre-existing test failures:** `test_git_provider.py` has 2 failing tests (unrelated to this story)

### Project Structure Notes

- Operator Rust code: `operator/src/controllers/servicelevel.rs`, `operator/src/crds/servicelevel.rs`, `operator/src/slo/`
- Investigator Python code: `investigator/beeper_investigator/steps/service_topology.py`, `investigator/beeper_investigator/steps/rca_hypothesis.py`, `investigator/beeper_investigator/steps/resolution_recommendations.py`
- Pipeline wiring: `investigator/beeper_investigator/agent.py`
- Demo CRDs: `demo/k8s/slo-*.yaml`
- Helm CRD definition: `helm/beeper/templates/crds/servicelevel-crd.yaml`

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.5 — lines 422-441]
- [Source: _bmad-output/planning-artifacts/epics.md#FR20-FR21 — lines 278-281]
- [Source: _bmad-output/planning-artifacts/prd.md#Workstream 1 Checkpoint 5 — ServiceLevel CRD Integration]
- [Source: _bmad-output/planning-artifacts/architecture.md#SLO Integration — FR20-21]
- [Source: _bmad-output/planning-artifacts/architecture.md#Source Tree — operator/src/slo/, controllers/servicelevel.rs]
- [Source: Story 2.4 — LLM prompt enhancement pattern (raw_signal_detail, temporal_summary)]
- [Source: Story 2.4 — E2E gap: operator OOMKill pre-existing issue]
- [Source: operator/src/slo/mod.rs — SloSnapshot struct, QdrantWriter, slo_snapshots collection]
- [Source: investigator/beeper_investigator/steps/service_topology.py — wrong field extraction at lines 289-310]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- Rust tests: `cargo test --lib` → 572 passed, 0 failed
- Python tests: `poetry run pytest tests/test_rca_hypothesis.py tests/test_resolution_recommendations.py tests/test_service_topology.py` → **134 passed**, 0 failed

### Completion Notes List

- Task 1: Operator-side fully working — 572 Rust tests pass, controller registered, SLO engine spawned
- Tasks 2-5: Fixed 3 investigator-side gaps (wrong field extraction, missing Qdrant query, no pipeline propagation). Added `_query_slo_snapshots()` batch Qdrant query, `_extract_slo_for_service()` for StepResult.data, `_extract_slo_data()`/`_format_slo_context()` in both LLM steps
- Task 6: 134/134 tests pass including 23 new SLO-specific tests
- Task 7: E2E deferred — operator OOMKill pre-existing blocker (documented in Stories 2.2-2.4)
- SLO data cleanly omitted when absent (no "No SLO data available" noise)
- Follows exact Story 2.4 pattern: StepResult.data → pipeline_metadata → extract helper → format for prompt
- **Code review fixes applied:** H1 (order_by timestamp desc), H2 (batch query replaces N+1), M2 (partial SLO data tests), M3 (narrowed exception handling)

### File List

- `investigator/beeper_investigator/steps/service_topology.py` — Fixed CRD field extraction, added `_query_slo_snapshots()` batch query, `_extract_slo_for_service()`
- `investigator/beeper_investigator/steps/rca_hypothesis.py` — Added SLO system prompt instruction, `{slo_context}` template, `_extract_slo_data()`, `_format_slo_context()`
- `investigator/beeper_investigator/steps/resolution_recommendations.py` — Added SLO system prompt instruction, `{slo_context}` template, `_extract_slo_data()`, `_format_slo_context()`
- `investigator/tests/test_service_topology.py` — Fixed existing test, added TestSLOCRDFieldExtraction, TestQdrantSnapshotQuery (batch), TestSLOPipelinePropagation, TestGracefulAbsence
- `investigator/tests/test_rca_hypothesis.py` — Added TestSLOContextInPrompt (4 tests incl. partial data)
- `investigator/tests/test_resolution_recommendations.py` — Added TestSLOContextInResolutionPrompt (4 tests incl. partial data)
