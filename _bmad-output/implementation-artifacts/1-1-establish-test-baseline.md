# Story 1.1: Establish Test Baseline

Status: done

## Story

As a **developer**,
I want to run the full existing test suite and document which tests pass/fail,
So that I have diagnostic information to guide pipeline fixes.

## Acceptance Criteria

1. **Given** the existing codebase with ~1,032 tests across 3 components
   **When** `cargo test` is run for the operator, `poetry run pytest` for investigator, and `poetry run pytest` for UI
   **Then** test results are documented with pass/fail counts per component
   **And** failing tests are categorized by component boundary they reveal (ingestion, detection, lifecycle, etc.)

## Tasks / Subtasks

- [x] Task 1: Run operator tests (AC: #1)
  - [x] 1.1 `cd operator && cargo test 2>&1 | tee /tmp/operator-test-results.txt`
  - [x] 1.2 Record pass/fail/skip counts and compare actual total to expected (~162)
  - [x] 1.3 Categorize failures by module: ingestion/, detection/, slo/, controllers/, api/
  - [x] 1.4 Distinguish compile errors from test assertion failures
- [x] Task 2: Run investigator tests (AC: #1)
  - [x] 2.1 `cd investigator && poetry install && poetry run pytest -v 2>&1 | tee /tmp/investigator-test-results.txt`
  - [x] 2.2 Record pass/fail/skip/error counts and compare actual total to expected (~375)
  - [x] 2.3 Categorize failures by module: steps/, llm/, signals/, kb/
  - [x] 2.4 Distinguish errors (import failures, missing fixtures, timeouts) from assertion failures
- [x] Task 3: Run UI tests (AC: #1)
  - [x] 3.1 `cd ui && poetry install && poetry run pytest -v 2>&1 | tee /tmp/ui-test-results.txt`
  - [x] 3.2 Record pass/fail/skip/error counts and compare actual total to expected (~495)
  - [x] 3.3 Categorize failures by module: routes/, templates/, services
  - [x] 3.4 Distinguish errors (import failures, missing fixtures, timeouts) from assertion failures
- [x] Task 4: Run linters (informational, not blocking) (AC: #1)
  - [x] 4.1 `cd operator && cargo fmt --check && cargo clippy -- -D warnings`
  - [x] 4.2 `cd investigator && poetry run ruff check .`
  - [x] 4.3 `cd ui && poetry run ruff check .`
- [x] Task 5: Document baseline results (AC: #1)
  - [x] 5.1 Create summary table: component | expected | actual | pass | fail | error | skip
  - [x] 5.2 List all failing tests grouped by component boundary, distinguishing errors (environment/dependency issues) from assertion failures (logic bugs)
  - [x] 5.3 Note which failures are relevant to pipeline fix (ingestion, detection, lifecycle, signals) vs. unrelated (notifications, trust, remediation — out of scope modules)
  - [x] 5.4 Update this story's Completion Notes with the baseline

## Dev Notes

### Purpose
This is a diagnostic story per AD-8 (Integration Testing Strategy). The goal is NOT to fix tests — it's to run them and document what passes and fails. Failures are diagnostic information that reveals which components are broken and how.

### What NOT to Do
- Do NOT fix any failing tests in this story
- Do NOT modify any source code
- Do NOT create new tests
- Do NOT update dependencies unless required to run tests
- Do NOT touch modules marked "Out of scope" (notifications/, remediation/, repository/)

### Component Test Commands

| Component | Directory | Command | Framework | Expected Count |
|-----------|-----------|---------|-----------|----------------|
| Operator | `operator/` | `cargo test` | cargo test + wiremock 0.5 | ~162 tests |
| Investigator | `investigator/` | `poetry run pytest` | pytest ^8.0 | ~375 tests |
| UI | `ui/` | `poetry run pytest` | pytest ^8.0 + respx ^0.21 | ~495 tests |

### Test File Locations

- **Operator:** Tests in `operator/tests/` and inline `#[cfg(test)]` modules within `src/`
- **Investigator:** Tests in `investigator/tests/` (47 test files)
- **UI:** Tests in `ui/tests/` (62 test files), fixtures in `ui/tests/conftest.py`
- **Demo:** `demo/tests/test_slo_manifests.py` (ServiceLevel CRD validation)

### Failure Categorization Guide

Group failing tests by the pipeline boundary they reveal:

| Category | Relevant to Pipeline Fix? | Module Patterns |
|----------|---------------------------|-----------------|
| Ingestion | YES — FR1-FR4 | `ingestion/`, `otlp`, `prometheus.rs`, `loki.rs` |
| Detection | YES — FR5-FR9 | `detection/`, `ewma`, `anomaly` |
| Lifecycle | YES — FR10-FR13 | `controllers/investigation`, `investigator_job` |
| Signals | YES — FR14-FR16 | `sources/`, `signals/`, `test_sources` |
| KB | YES — FR17, FR28-FR31 | `kb/`, `knowledge` |
| LLM | YES — FR18-FR19 | `llm/`, `rca_hypothesis`, `resolution` |
| SLO | YES — FR20-FR21 | `slo/`, `servicelevel`, `burn_rate` |
| UI Routes | Partially — FR22-FR35 | `test_routes`, `test_app`, `test_services` |
| Notifications | NO — out of scope | `notification`, `slack`, `pagerduty`, `email`, `webhook` |
| Trust/Remediation | NO — out of scope | `trust`, `confidence_gate`, `remediation`, `sandbox` |
| Collaboration | NO — out of scope | `corrections`, `learning`, `feedback` |

### Development Iteration

This story runs entirely locally — no cluster needed. Fast feedback loop:
- Operator: `cargo test` (~1-2 min compile + test)
- Investigator/UI: `poetry run pytest` (seconds)

### CI/CD Reference

The same tests run in GitHub Actions (`.github/workflows/ci.yml`):
- Rust: `cargo fmt --check` → `cargo clippy -- -D warnings` → `cargo test`
- Investigator: `poetry run ruff check .` → `poetry run pytest`
- UI: `poetry run ruff check .` → `poetry run pytest`

### Project Structure Notes

- Alignment: Tests follow standard patterns — `operator/tests/`, `investigator/tests/`, `ui/tests/`
- Operator Rust tests use `#[cfg(test)]` inline modules AND `tests/` directory
- Python projects use Poetry for dependency management
- No special test configuration beyond `pyproject.toml` `[tool.pytest.ini_options]`

### References

- [Source: _bmad-output/planning-artifacts/architecture.md — AD-8: Integration Testing Strategy]
- [Source: _bmad-output/planning-artifacts/architecture.md — Testing Patterns section]
- [Source: _bmad-output/planning-artifacts/architecture.md — Pre-implementation baseline]
- [Source: _bmad-output/planning-artifacts/epics.md — Story 1.1]
- [Source: .github/workflows/ci.yml — CI test pipeline]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- Raw operator results: `/tmp/operator-test-results.txt`
- Raw investigator results: `/tmp/investigator-test-results.txt`
- Raw UI results: `/tmp/ui-test-results.txt`

### Completion Notes List

#### Test Baseline Summary (2026-04-11)

##### Summary Table

| Component | Expected | Actual | Pass | Fail | Error | Skip |
|-----------|----------|--------|------|------|-------|------|
| Operator | ~162 | 550 | 550 | 0 | 0 | 0 |
| Investigator | ~375 | 1016 | 1011 | 2 | 0 | 3 |
| UI | ~495 | 2023 | 2007 | 10 | 6 | 0 |
| **TOTAL** | **~1,032** | **3,589** | **3,568** | **12** | **6** | **3** |

**Count validation note:** Actual test counts (3,589) are ~3.5x the architecture doc estimates (~1,032). This indicates significant test growth since the architecture was written. All additional tests are passing — the codebase is healthier than expected.

##### Linter Results (Informational)

| Component | Tool | Result |
|-----------|------|--------|
| Operator | `cargo fmt --check` | FAIL — formatting diffs in `api.rs`, `main.rs`, `slo/mod.rs`, `controllers/servicelevel.rs`, `crds/notification_channel.rs`, `crds/repository.rs` |
| Operator | `cargo clippy -- -D warnings` | FAIL — 1 warning in `slo/mod.rs` (`clippy::manual_map`) |
| Investigator | `ruff check .` | PASS |
| UI | `ruff check .` | PASS |

**CI blocker note:** The operator `cargo fmt` and `cargo clippy` failures are pre-existing (not introduced by this sprint). However, CI pipeline (`.github/workflows/ci.yml`) runs `cargo fmt --check → cargo clippy -- -D warnings → cargo test` in sequence — fmt/clippy failures will block CI before tests run. These must be addressed before or during Story 1.2.

##### Failing Tests by Component Boundary

**Investigator — 2 failures (all assertion failures, no errors)**

| Test | Category | Relevant? |
|------|----------|-----------|
| `test_git_provider.py::TestGitHubProvider::test_commit_files_creates_new` | Repository | NO — out of scope |
| `test_git_provider.py::TestGitLabProvider::test_commit_files` | Repository | NO — out of scope |

**UI — 10 assertion failures + 6 errors**

| Test | Type | Category | Relevant? | Root Cause |
|------|------|----------|-----------|------------|
| `test_cost_insights.py::TestCostByService::test_groups_by_service` | Assertion | UI Routes | Partially — FR22-FR35 | Returns 0 counts; data aggregation logic |
| `test_cost_insights.py::TestCostByService::test_model_breakdown` | Assertion | UI Routes | Partially — FR22-FR35 | Returns 0 counts; data aggregation logic |
| `test_cost_insights.py::TestCostBySeverity::test_groups_by_severity` | Assertion | UI Routes | Partially — FR22-FR35 | Returns 0 counts; data aggregation logic |
| `test_cost_insights.py::TestCostByModel::test_aggregates_from_per_model` | Assertion | UI Routes | Partially — FR22-FR35 | Returns 0 counts; data aggregation logic |
| `test_cost_insights.py::TestHighCostServices::test_flags_above_threshold` | Assertion | UI Routes | Partially — FR22-FR35 | Returns empty list; data aggregation logic |
| `test_cost_insights.py::TestHighCostServices::test_trend_calculation` | Assertion | UI Routes | Partially — FR22-FR35 | Returns empty list; data aggregation logic |
| `test_cost_insights.py::TestPeriodFiltering::test_month_filters_old_data` | Assertion | UI Routes | Partially — FR22-FR35 | Returns 0 counts; data aggregation logic |
| `test_embedding_service.py::TestEmbeddingService::test_get_embedding_success` | **Error** | KB | YES — FR17, FR28-FR31 | `AttributeError: module does not have attribute 'litellm'` |
| `test_embedding_service.py::TestEmbeddingService::test_get_embedding_caches_identical_queries` | **Error** | KB | YES — FR17, FR28-FR31 | `AttributeError: module does not have attribute 'litellm'` |
| `test_embedding_service.py::TestEmbeddingService::test_get_embedding_different_queries_not_cached` | **Error** | KB | YES — FR17, FR28-FR31 | `AttributeError: module does not have attribute 'litellm'` |
| `test_embedding_service.py::TestEmbeddingService::test_get_embedding_api_error` | **Error** | KB | YES — FR17, FR28-FR31 | `AttributeError: module does not have attribute 'litellm'` |
| `test_embedding_service.py::TestEmbeddingService::test_clear_cache` | **Error** | KB | YES — FR17, FR28-FR31 | `AttributeError: module does not have attribute 'litellm'` |
| `test_embedding_service.py::TestEmbeddingService::test_get_cache_info` | **Error** | KB | YES — FR17, FR28-FR31 | `AttributeError: module does not have attribute 'litellm'` |
| `test_service_health.py::TestServiceHealthServiceDetail::test_get_service_detail_partitions_investigations` | Assertion | UI Routes | Partially — FR22-FR35 | **Time-sensitive:** hardcoded date now outside 7-day window |
| `test_service_health.py::TestServiceFeedItemsRoute::test_feed_items_partitions_correctly` | Assertion | UI Routes | Partially — FR22-FR35 | **Time-sensitive:** hardcoded date now outside 7-day window |
| `test_spending.py::TestSpendingService::test_get_spending_summary` | Assertion | UI Routes | Partially — FR22-FR35 | **Time-sensitive:** hardcoded date now outside monthly window |

**Skipped Tests — 3 (Investigator)**

| Test | Reason |
|------|--------|
| `test_kb_client.py::TestKBClientIntegration::test_health_check_integration` | Requires running Qdrant instance |
| `test_kb_client.py::TestKBClientIntegration::test_collection_exists` | Requires running Qdrant instance |
| `test_kb_client.py::TestKBClientIntegration::test_search_returns_results` | Requires running Qdrant instance |

##### Pipeline-Relevant Failure Summary

| Category | Failures | Component |
|----------|----------|-----------|
| KB (FR17, FR28-FR31) | 6 errors | UI — embedding service (AttributeError: missing `litellm` attribute) |
| UI Routes (FR22-FR35) | 7 assertion | UI — cost insights (data aggregation returns 0) |
| UI Routes — time-sensitive | 3 assertion | UI — service health + spending (hardcoded dates outside filter window) |
| **Pipeline-relevant total** | **16** | |
| Out of scope (Repository) | 2 assertion | Investigator — git provider |
| **Grand total failures** | **18** | |

##### Key Diagnostic Findings

1. **Operator is clean.** 550/550 tests pass. No failures in any pipeline-relevant module (ingestion, detection, SLO, controllers). Linter issues (fmt + clippy) are pre-existing and will block CI — must be fixed before/during Story 1.2.
2. **Investigator is nearly clean.** 1011/1016 pass (99.5%). The 2 failures are in `test_git_provider.py` (repository module — out of scope). 3 skipped tests require a running Qdrant instance (expected for integration tests).
3. **UI has 16 failures across 3 test files**, broken down by failure type:
   - `test_embedding_service.py` (6 **errors**) — `AttributeError`: module missing `litellm` attribute. Module structure/import issue, not logic bug. Pipeline-relevant (KB).
   - `test_cost_insights.py` (7 **assertion failures**) — data aggregation returns 0 counts. Logic bug in cost insights service. Partially relevant (Story 5.3).
   - `test_service_health.py` (2 **assertion failures**) — **time-sensitive**: hardcoded dates (`2026-03-18`) now outside "last 7 days" filter. Test design issue, not application bug.
   - `test_spending.py` (1 **assertion failure**) — **time-sensitive**: hardcoded date (`2026-03-07`) now outside monthly window. Test design issue, not application bug.
4. **3 time-sensitive tests** identified — these will pass/fail depending on run date. Not real application bugs; test fixtures need relative dates.
5. **Test counts are 3.5x higher than architecture estimates** — significant test growth since architecture doc was authored.

### Change Log

- 2026-04-12: Code review fixes applied — corrected failure classifications (6 UI errors reclassified from assertion to AttributeError), identified 3 time-sensitive tests, added CI blocker note for operator linters, fixed git_provider categorization from Trust/Remediation to Repository, added root cause details for all failures.

### File List

No files created or modified (diagnostic-only story). Story file updated with baseline results.

## Senior Developer Review (AI)

**Review Date:** 2026-04-12
**Review Outcome:** Approve (with fixes applied)

### Action Items

- [x] [HIGH] Reclassify 6 embedding_service failures as errors (AttributeError), not assertion failures — summary table corrected
- [x] [MEDIUM] Identify 3 time-sensitive tests (service_health x2, spending x1) as flaky/date-dependent, not application bugs
- [x] [MEDIUM] Add CI blocker note for operator cargo fmt/clippy failures that will block pipeline
- [x] [LOW] Fix git_provider categorization: Repository, not Trust/Remediation
- [x] [LOW] Add root cause details for cost_insights failures (data aggregation returns 0)
