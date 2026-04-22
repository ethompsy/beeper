# Story 2.0c: Investigator Test Baseline

Status: done

> Preparation task from Epic 1 retrospective — must complete before Epic 2 stories.
> Priority: MEDIUM | Source: [epic-1-retro-2026-04-18.md](epic-1-retro-2026-04-18.md#epic-2-preparation-tasks)

## Story

As a **developer**,
I want to establish a documented test baseline for the investigator Python codebase,
So that Epic 2 stories can measure test growth and detect regressions against a known state.

## Background

Epic 1 established a test-first approach (Story 1.1) with operator Rust tests growing from 550→572. The investigator Python codebase has a parallel test suite that was briefly checked during Story 2.1 (1011 pass, 2 fail, 3 skip) but never formally baselined. This task creates the official baseline for Epic 2's investigator-heavy stories (2.2-2.4).

## Acceptance Criteria

1. **Given** the investigator codebase at `investigator/`
   **When** `poetry run pytest` is executed
   **Then** the total pass/fail/skip/error counts are documented
   **And** any failures are classified as pre-existing vs new

2. **Given** the test results are documented
   **When** test failures exist
   **Then** each failure is investigated: root cause, whether it blocks Epic 2, and whether it needs fixing
   **And** the investigation is recorded in Dev Agent Record

3. **Given** the baseline is established
   **When** future Epic 2 stories add investigator tests
   **Then** they can reference this baseline count to measure test growth

## Tasks / Subtasks

- [x] Task 1: Run investigator test suite (AC: #1)
  - [x] 1.1 `poetry install --quiet` — dependencies current (Python 3.14, poetry venv)
  - [x] 1.2 `poetry run pytest --tb=short` — **1011 passed, 2 failed, 3 skipped, 196477 warnings in 25.25s**
  - [x] 1.3 Collected: 1016 tests, 43 files. Passed: 1011. Failed: 2. Skipped: 3. Errors: 0. Warnings: 196477 (mostly pytest-asyncio deprecation for Python 3.16).
  - [x] 1.4 `poetry run pytest --co -q` — 1016 tests collected in 17.30s. 1 collection warning: TestPlanStep has __init__.

- [x] Task 2: Classify test failures (AC: #2)
  - [x] 2.1 Failure 1: `TestGitHubProvider::test_commit_files_creates_new` — mock raises `Exception("not found")` but code catches `UnknownObjectException` (imported from github library). Failure 2: `TestGitLabProvider::test_commit_files` — same pattern with `GitlabGetError`.
  - [x] 2.2 Classification: Both are **pre-existing test mock bugs** — mocks use generic Exception but code catches library-specific exceptions since PyGithub/python-gitlab ARE installed.
  - [x] 2.3 **Does NOT block Epic 2**: Stories 2.2-2.4 don't use git providers. Git remediation is a separate feature area.
  - [x] 2.4 Analysis documented in Dev Agent Record below.

- [x] Task 3: Run linting baseline (AC: #1)
  - [x] 3.1 `poetry run ruff check .` — **All checks passed!** Zero lint issues.
  - [x] 3.2 `poetry run mypy beeper_investigator/` — **5 errors in 1 file** (`git_provider.py`): 2 incompatible assignment errors, 1 union-attr error, 2 misc errors. All in the same file as the test failures. 41 source files checked, 40 clean.

- [x] Task 4: Document baseline (AC: #3)
  - [x] 4.1 Baseline recorded below: 1016 collected, 1011 passed, 2 failed (pre-existing), 3 skipped.
  - [x] 4.2 Categories: ~970 unit tests, 43 integration tests (7 agent integration files + 3 KBClient integration), 12 async tests (across 4 files).
  - [x] 4.3 Epic 2 key files listed in Dev Notes above.

## Dev Notes

### Test Environment

- **Framework:** pytest 8.0+ with pytest-asyncio 0.24+
- **Package manager:** Poetry (Python ^3.11)
- **Config:** `pyproject.toml` — `asyncio_mode = "auto"`
- **CI:** `.github/workflows/ci.yml` — runs `poetry run ruff check .` + `poetry run pytest`

### Test Suite Structure (43 files, ~1016 tests)

Key test files for Epic 2:
- `test_agent.py` (12 tests) — agent lifecycle, critical for Stories 2.2-2.4
- `test_context.py` (21 tests) — investigation context, critical for 2.2
- `test_llm_client.py` (~130 tests) — LLM integration, critical for 2.4
- `test_kb_client.py` (~150 tests) — KB queries, critical for 2.3
- `test_kb_query.py` (~130 tests) — KB search, critical for 2.3
- `test_k8s_status.py` (3 tests) — K8s status updates, critical for 2.1-2.4

### Known Issues (from Story 2.1 session)

- **2 failures in test_git_provider.py** — pre-existing, unrelated to investigation lifecycle
- **1 collection warning** — `TestPlanStep` class at `beeper_investigator/remediation/test_planner.py:84` has `__init__` constructor (not a real test class, `Test` prefix triggers pytest collection)
- **3 skipped tests** — `TestKBClientIntegration` class (test_health_check_integration, test_collection_exists, test_search_returns_results) skipped when `QDRANT_HOST` env var is unset

### Previous Intelligence

- **Story 2.1:** Ran `poetry run pytest` — 1011 passed, 2 failed, 3 skipped (point-in-time)
- **Story 1.1 pattern:** Operator baseline was 550 tests → grew to 572 by Epic 1 end
- **Epic 1 retro:** Test-first with diagnostic baseline should be repeated for every epic

### References

- [Source: investigator/pyproject.toml] — pytest config, dependencies
- [Source: investigator/tests/] — 43 test files
- [Source: .github/workflows/ci.yml] — CI test execution
- [Source: epic-1-retro-2026-04-18.md#Key Insights] — "Test-first with diagnostic baseline"

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- `poetry run pytest --tb=short` → 2 failed, 1011 passed, 3 skipped, 196477 warnings in 25.25s
- `poetry run pytest --co -q` → 1016 tests collected in 17.30s
- `poetry run ruff check .` → All checks passed!
- `poetry run mypy beeper_investigator/` → Found 5 errors in 1 file (checked 41 source files)

### Investigator Test Baseline (Official)

| Metric | Value |
|--------|-------|
| Tests collected | 1016 |
| Passed | 1011 |
| Failed | 2 (pre-existing) |
| Skipped | 3 |
| Errors | 0 |
| Warnings | 196477 (asyncio deprecation) |
| Duration | 25.25s |
| Test files | 43 |
| Ruff lint | 0 issues |
| Mypy errors | 5 (all in git_provider.py) |

### Failure Analysis

**Failure 1:** `TestGitHubProvider::test_commit_files_creates_new`
- Root cause: Mock uses `Exception("not found")` but code catches `github.UnknownObjectException` (library IS installed, so specific exception type is used)
- Classification: Pre-existing test mock bug
- Epic 2 impact: NONE — git providers not used in Stories 2.2-2.4

**Failure 2:** `TestGitLabProvider::test_commit_files`
- Root cause: Same pattern — mock uses `Exception("not found")` but code catches `gitlab.exceptions.GitlabGetError`
- Classification: Pre-existing test mock bug
- Epic 2 impact: NONE

### Pre-existing Issues Backlog

These issues are non-blocking for Epic 2 but should be tracked for eventual cleanup:
- **2 test failures** (`test_git_provider.py`): Fix mocks to raise `github.UnknownObjectException` / `gitlab.exceptions.GitlabGetError` instead of generic `Exception`. Target: git provider feature work.
- **5 mypy errors** (`beeper_investigator/git_provider.py`): 2 incompatible assignment, 1 union-attr, 2 misc. Target: git provider feature work.
- **1 collection warning** (`TestPlanStep`): Rename class to `PlanStep` or add `collect_ignore` in conftest. Target: any investigator cleanup PR.
- **196,477 pytest-asyncio warnings**: Deprecation for `asyncio.set_event_loop_policy` (Python 3.16). Upgrade `pytest-asyncio` or adjust `asyncio_mode` config. Target: dependency update cycle.

### Completion Notes List

- AC #1 PASS: Full test suite executed, all counts documented. 1016 collected, 1011 passed, 2 failed, 3 skipped.
- AC #2 PASS: Both failures investigated — pre-existing mock bugs in git_provider.py, do NOT block Epic 2.
- AC #3 PASS: Baseline established. Epic 2 stories should reference: 1016 tests (1011 passing) as starting point.
- Linting clean (ruff), 5 mypy errors (all in git_provider.py, same pre-existing file).
- Python 3.14 runtime detected — pytest-asyncio deprecation warnings for asyncio.set_event_loop_policy (slated for removal in 3.16). Non-blocking.

### Code Review Fixes Applied

- [M1] Corrected test category counts: integration 38→43 (includes 3 KBClient), async 9→12 (across 4 files)
- [M2] Identified skipped tests: `TestKBClientIntegration` (3 tests) skipped when `QDRANT_HOST` unset
- [M3] Added Pre-existing Issues Backlog section documenting 2 test failures, 5 mypy errors, 1 collection warning, and deprecation warnings with remediation targets
- [L1-L3] Documented as observations in Pre-existing Issues Backlog

### Change Log

- 2026-04-21: Established investigator test baseline — 1016 tests, 1011 passing. No code changes (diagnostic-only task).
- 2026-04-21: Code review fixes — corrected test category counts, identified skipped tests, added remediation backlog.

### File List

No files modified — diagnostic/baseline task.
