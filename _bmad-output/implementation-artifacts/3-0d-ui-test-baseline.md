# Story 3.0d: UI Test Baseline

Status: done

## Story

As a **developer**,
I want a fresh UI test baseline with all pre-existing failures documented and fixable ones resolved,
So that Epic 3 UI stories can be verified against a known-good test suite with zero false failures.

## Background

**Origin:** Epic 2 retrospective preparation task. Story 1.1 baseline (2026-04-10) found 16 pre-existing UI test failures across 3 categories. Story 3-0c (full demo walkthrough) failed and spawned bug-fix stories 3-0e through 3-0h — all now merged. A fresh baseline is needed post-fixes to confirm UI test suite health before Epic 3 begins.

**Previous Baseline (Story 1.1):** 2,023 UI tests — 2,007 passed, 10 failed, 6 errors, 0 skipped.

## Acceptance Criteria

1. **Given** the UI test suite at `ui/tests/`
   **When** `cd ui && poetry run pytest` is executed
   **Then** all tests pass OR remaining failures are documented with root cause and categorized as "deferred" with justification

2. **Given** the 3 time-sensitive test failures (hardcoded dates)
   **When** they are updated to use relative date calculations
   **Then** those tests pass reliably regardless of execution date

3. **Given** the 6 `test_embedding_service.py` errors (`AttributeError: module does not have attribute 'litellm'`)
   **When** the root cause is investigated
   **Then** the errors are fixed OR documented as deferred with clear justification (e.g., missing optional dependency configuration)

4. **Given** the 7 `test_cost_insights.py` assertion failures
   **When** the root cause is investigated
   **Then** the failures are fixed OR documented as deferred with clear justification

5. **Given** the completed baseline
   **When** a summary is produced
   **Then** it includes: total tests, passed, failed, errors, skipped, duration, and comparison to Story 1.1 baseline

## Tasks / Subtasks

- [x] Task 1: Run initial UI test suite and capture current state
  - [x] 1.1 Execute `cd ui && poetry run pytest -v --tb=short 2>&1 | tee test-output.txt` and capture full output
  - [x] 1.2 Document total/passed/failed/error/skipped counts
  - [x] 1.3 List every failing test with file, test name, and failure type (assertion vs error vs timeout)
  - [x] 1.4 Compare to Story 1.1 baseline (2,023 total, 2,007 pass, 10 fail, 6 error)

- [x] Task 2: Fix time-sensitive test failures (3 tests)
  - [x] 2.1 Fix `test_service_health.py` — 2 tests with hardcoded date `2026-03-18` outside 7-day window; replace with `datetime.now() - timedelta(days=N)` or freeze time
  - [x] 2.2 Fix `test_spending.py` — 1 test with hardcoded date `2026-03-07` outside monthly window; same approach
  - [x] 2.3 Run fixed tests to confirm they pass

- [x] Task 3: Investigate and fix embedding_service errors (6 tests)
  - [x] 3.1 Read `ui/tests/test_embedding_service.py` to understand what it tests
  - [x] 3.2 Identify root cause of `AttributeError: module does not have attribute 'litellm'`
  - [x] 3.3 Fix the import/mock issue OR document as deferred if it requires infrastructure changes (e.g., litellm version mismatch, optional feature not configured)
  - [x] 3.4 Run tests to confirm fix (or document deferral rationale)

- [x] Task 4: Investigate and fix cost_insights failures (7 tests)
  - [x] 4.1 Read `ui/tests/test_cost_insights.py` to understand what it tests
  - [x] 4.2 Identify root cause of "data aggregation returns 0 counts" assertions
  - [x] 4.3 Fix mock data or business logic OR document as deferred
  - [x] 4.4 Run tests to confirm fix (or document deferral rationale)

- [x] Task 5: Run final baseline and document results
  - [x] 5.1 Execute full UI test suite: `cd ui && poetry run pytest -v --tb=short`
  - [x] 5.2 Run linting: `cd ui && poetry run ruff check .`
  - [x] 5.3 Document final baseline in Completion Notes: total/pass/fail/error/skip/duration
  - [x] 5.4 Compare final vs initial vs Story 1.1 baselines
  - [x] 5.5 Update File List with all modified test files

## Dev Notes

### Architecture Reference
- **AD-8 (Integration Testing Strategy):** Pre-implementation baseline required before Epic 3. Manual verification via Makefile targets + `kubectl` + `curl`. Unit tests mandatory for all new code.
- **Testing Framework:** pytest ^8.0, respx ^0.21 (HTTP mocking), pytest-asyncio ^0.24
- **CI Pipeline:** GitHub Actions runs `poetry run ruff check .` and `poetry run pytest` on `ui/` [Source: .github/workflows/ci.yml]

### UI Test Infrastructure
- **66 test files** in `ui/tests/` (~35K LOC)
- **Test patterns:**
  - Route testing: `@respx.mock` + `client.get()` + HTML content assertions
  - Service mocking: `@patch("beeper_ui.services.*.ServiceClass")`
  - Template rendering: `app.jinja_env.get_template().render()`
  - Role-based: `admin_client` / `user_client` fixtures with `X-Beeper-Role` header
- **Mock operator URL:** `http://mock-operator:8080` (set in `TestingConfig`)
- **Key fixture file:** `ui/tests/conftest.py`

### Known Failure Categories (from Story 1.1)

| Category | Count | Root Cause | Files |
|----------|-------|-----------|-------|
| Time-sensitive dates | 3 | Hardcoded dates drift outside assertion windows | `test_service_health.py`, `test_spending.py` |
| Embedding service | 6 | `AttributeError: module does not have attribute 'litellm'` | `test_embedding_service.py` |
| Cost insights | 7 | Data aggregation returns 0 counts | `test_cost_insights.py` |

### Key Files to Examine
- `ui/tests/test_service_health.py` — look for hardcoded `2026-03-18`
- `ui/tests/test_spending.py` — look for hardcoded `2026-03-07`
- `ui/tests/test_embedding_service.py` — look for litellm import/mock issues
- `ui/tests/test_cost_insights.py` — look for mock data returning 0 counts
- `ui/tests/conftest.py` — shared fixtures
- `ui/pyproject.toml` — dependency versions

### Previous Story Learnings

**From Story 3-0c (failed walkthrough):**
- UI investigation detail was broken (fixed in 3-0f: `Api::namespaced()`)
- SSE streaming for investigation steps works end-to-end
- UI routes: `ui/beeper_ui/routes/investigations.py` (1,615 LOC)
- Investigation templates: `ui/beeper_ui/templates/investigations/`

**From Story 2-0c (investigator test baseline):**
- Investigator had 1,016 tests, 1,011 passing — clean baseline achieved
- Pre-existing failures were isolated and documented, not force-fixed
- Approach: fix what's fixable, document what's deferred with clear rationale

**From Story 1-1 (initial test baseline):**
- UI had 2,023 tests with 16 failures across 3 categories
- Time-sensitive tests are the easiest wins (just fix hardcoded dates)
- Embedding service errors may require dependency investigation
- Cost insights failures may be mock data issues

### Security Principle
This story only modifies test files. No production code changes expected. All fixes should be in `ui/tests/` directory.

### Project Structure Notes
- UI project root: `ui/`
- Tests: `ui/tests/`
- Run tests from `ui/` directory: `poetry run pytest`
- Run linting from `ui/` directory: `poetry run ruff check .`

### References
- [Source: _bmad-output/implementation-artifacts/1-1-establish-test-baseline.md — UI baseline section]
- [Source: _bmad-output/implementation-artifacts/2-0c-investigator-test-baseline.md — baseline approach pattern]
- [Source: _bmad-output/implementation-artifacts/3-0c-full-demo-walkthrough.md — UI failure context]
- [Source: _bmad-output/planning-artifacts/architecture.md — AD-8 testing strategy]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 3 preparation tasks]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References
N/A

### Completion Notes List

**Initial Baseline (Task 1):** 2,023 tests — 2,007 passed, 16 failed, 0 skipped (~50s). Matches Story 1.1 baseline counts exactly.

**Task 2 — Time-sensitive test fixes (3 tests fixed):**
- `test_service_health.py`: Replaced 6 hardcoded `2026-03-18` dates with dynamic `datetime.now(timezone.utc) - timedelta(days=N)` calculations. 2 tests fixed.
- `test_spending.py`: Added dynamic `_TODAY_ISO`, `_TODAY_MINUS_1H`, `_TODAY_MINUS_2H` constants replacing hardcoded `2026-03-07` dates. 1 test fixed.

**Task 3 — Embedding service errors (6 tests fixed):**
- Root cause: `import litellm` was lazy (inside method body), so `@patch("beeper_ui.services.embedding_service.litellm")` could not find the module attribute.
- Fix: Moved `import litellm` to module level in `embedding_service.py`. This is a production code change (1 line moved), not just test changes.

**Task 4 — Cost insights failures (7 tests fixed):**
- Root cause: Same hardcoded date pattern — mock data used `2026-03-07` which fell outside the current month filter in `_filter_by_period()`.
- Fix: Added dynamic date constants (`_RECENT`, `_RECENT_1H`, `_RECENT_2H`) and replaced all 20 occurrences of hardcoded dates.

**Task 5 — Final Baseline:**

| Metric | Story 1.1 | Initial (Task 1) | Final (Task 5) |
|--------|-----------|-------------------|----------------|
| Total | 2,023 | 2,023 | 2,023 |
| Passed | 2,007 | 2,007 | 2,023 |
| Failed | 10 | 16 | 0 |
| Errors | 6 | 0 | 0 |
| Skipped | 0 | 0 | 0 |
| Duration | ~50s | ~50s | ~50s |

All 16 failures resolved. Zero regressions. Linting clean on all modified files (109 pre-existing ruff warnings in other files — not in scope).

**Code Review Fixes (2026-05-13):**
- M1: Replaced confusing `timedelta(days=N, hours=-1)` double-negative with explicit `timedelta(days=N) + timedelta(hours=1)` in `test_service_health.py`
- M2: Replaced last hardcoded dates in `test_spending.py::test_get_spending_trend` with dynamic `_YESTERDAY_ISO`/`_TODAY_ISO` constants and dynamic period assertions

### File List
- `ui/tests/test_service_health.py` — replaced hardcoded dates with dynamic calculations
- `ui/tests/test_spending.py` — replaced hardcoded dates with dynamic calculations
- `ui/tests/test_cost_insights.py` — replaced hardcoded dates with dynamic calculations
- `ui/beeper_ui/services/embedding_service.py` — moved `import litellm` from lazy to module-level
