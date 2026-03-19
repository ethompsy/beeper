# Story 8.3: Full Lifecycle Demonstration

Status: review

## Story

As the **system**,
I want to demonstrate the full lifecycle: healthy → fault → detect → investigate → fix → prove → recover,
so that investors can see Beeper's complete value proposition in a single continuous flow.

## Acceptance Criteria

1. **Given** the demo application is healthy and Beeper is monitoring it
   **When** a fault is injected
   **Then** Beeper detects the anomaly, starts an investigation, identifies root cause, proposes a fix, verifies resolution, and creates a KB entry
   **And** the full lifecycle completes in under 5 minutes (NFR7)

2. **Given** the full lifecycle is running
   **When** viewed in the Beeper UI
   **Then** each stage is visible in real-time: detection alert → investigation timeline streaming → fix proposal → verification metrics → KB entry creation
   **And** the narrative is coherent and explainable to a non-technical audience

3. **Given** the demo application's trust level
   **When** set to TL4 or TL5 for the demo
   **Then** Beeper acts autonomously through the full lifecycle without human intervention
   **And** each autonomous action is logged and visible in the UI for the audience

## Tasks / Subtasks

- [x] Task 1: Add lifecycle orchestrator to demo server (AC: #1, #2, #3)
  - [x] 1.1 Add lifecycle stage enum/constants: `healthy`, `fault_injected`, `detecting`, `investigating`, `fix_proposed`, `fix_applied`, `verifying`, `recovered`, `kb_created`
  - [x] 1.2 Add lifecycle state management to app config — `_get_lifecycle_state(app)` pattern consistent with `_get_fault_state(app)`
  - [x] 1.3 Add `POST /lifecycle/start` endpoint — kicks off a full lifecycle demo: injects fault (using existing `/fault/inject`), then auto-advances through simulated stages with configurable timing
  - [x] 1.4 Add `GET /lifecycle/status` endpoint — returns current lifecycle state: stage, stage_history (list of {stage, timestamp, description, duration_ms}), total_elapsed_ms, narrative for current stage
  - [x] 1.5 Add `POST /lifecycle/reset` endpoint — clears lifecycle state, recovers any active faults (calls existing `/fault/recover` logic), returns to `healthy`
  - [x] 1.6 Add `GET /lifecycle/timeline` endpoint — returns the complete timeline of all stages with timestamps, descriptions, and investor-friendly narration text
  - [x] 1.7 Lifecycle auto-advance: use `threading.Timer` (or synchronous simulation in TESTING mode) to advance stages with configurable delays: detect (5-10s), investigate (10-20s), fix_proposed (5s), fix_applied (5s), verifying (10s), recovered (5s), kb_created (5s) — total well under 5 minutes

- [x] Task 2: Add investor-friendly narration for each stage (AC: #2)
  - [x] 2.1 Each stage has a `narrative` text field — plain English description of what Beeper is doing and why, suitable for non-technical audience
  - [x] 2.2 `healthy` → "The application is running normally. All services are healthy and meeting their SLO targets."
  - [x] 2.3 `fault_injected` → "A {fault_type} has been introduced. In a real production environment, this could happen due to a bad deployment, resource exhaustion, or infrastructure failure."
  - [x] 2.4 `detecting` → "Beeper's monitoring has detected an anomaly. The SLO burn rate has spiked, triggering an automatic investigation."
  - [x] 2.5 `investigating` → "Beeper is now autonomously investigating the root cause. It's analyzing metrics, logs, and service dependencies to identify what went wrong."
  - [x] 2.6 `fix_proposed` → "Beeper has identified the root cause and is proposing a fix. At trust level {trust_level}, it can apply this fix automatically."
  - [x] 2.7 `fix_applied` → "The fix has been applied. Beeper is now verifying that the issue is truly resolved by monitoring the affected metrics."
  - [x] 2.8 `verifying` → "Verification in progress. Beeper is confirming that SLO metrics have returned to normal and no new issues have emerged."
  - [x] 2.9 `recovered` → "The service has fully recovered. All SLOs are back within target. The incident took {elapsed} to resolve — fully autonomously."
  - [x] 2.10 `kb_created` → "Beeper has created a knowledge base entry documenting this incident. Next time a similar issue occurs, resolution will be even faster."

- [x] Task 3: Add lifecycle Prometheus metrics (AC: #1)
  - [x] 3.1 Add `demo_lifecycle_stage{service, stage}` gauge — 1 for current stage, 0 for others
  - [x] 3.2 Add `demo_lifecycle_duration_seconds{service}` gauge — total elapsed time for current lifecycle run
  - [x] 3.3 Add `demo_lifecycle_runs_total{service}` counter — total lifecycle demonstrations completed

- [x] Task 4: Add Makefile targets for lifecycle control (AC: #1, #2)
  - [x] 4.1 Add `demo-lifecycle` target — `make demo-lifecycle FAULT=memory-leak SERVICE=backend` → POST /lifecycle/start with fault_type and trust_level params
  - [x] 4.2 Add `demo-lifecycle-status` target — GET /lifecycle/status, display current stage and timeline
  - [x] 4.3 Add `demo-lifecycle-reset` target — POST /lifecycle/reset to all services
  - [x] 4.4 Add `demo-lifecycle-timeline` target — GET /lifecycle/timeline, display full narrated timeline
  - [x] 4.5 Update `.PHONY` declaration with new targets

- [x] Task 5: Write comprehensive tests (AC: #1, #2, #3)
  - [x] 5.1 Create `demo/tests/test_lifecycle.py` — dedicated test file for lifecycle orchestrator
  - [x] 5.2 Test `POST /lifecycle/start` with each fault type starts lifecycle and advances through stages
  - [x] 5.3 Test `GET /lifecycle/status` returns correct state at each stage
  - [x] 5.4 Test `POST /lifecycle/reset` clears lifecycle and recovers faults
  - [x] 5.5 Test `GET /lifecycle/timeline` returns complete narrated history
  - [x] 5.6 Test lifecycle auto-advance completes all stages (in TESTING mode with zero/minimal delays)
  - [x] 5.7 Test lifecycle narrative text is present and includes fault-type-specific details
  - [x] 5.8 Test lifecycle metrics: stage gauge, duration gauge, runs counter
  - [x] 5.9 Test lifecycle start while already running returns appropriate error
  - [x] 5.10 Test lifecycle with each fault type produces correct stage sequence
  - [x] 5.11 Test lifecycle total duration tracking
  - [x] 5.12 Test lifecycle with custom timing parameters
  - [x] 5.13 Test lifecycle trust_level parameter in narration
  - [x] 5.14 Verify existing test_server.py and test_fault_injection.py tests still pass with lifecycle code present

## Dev Notes

### Architecture Compliance

- **Language:** Python (consistent with demo app and investigator/UI stack)
- **Framework:** Flask (extending existing `demo/app/server.py`)
- **Metrics:** `prometheus-client` library — add new gauges/counters to existing registry
- **Logging:** Structured JSON logging via existing `JsonFormatter` — lifecycle events logged as info/warning
- **API format:** REST, JSON requests/responses, `snake_case` field names
- **State Management:** In-memory mutable dict on app context — lifecycle state is ephemeral (cleared on pod restart)
- **Threading:** Use `threading.Timer` for stage auto-advance in production mode; synchronous simulation in TESTING mode
- **Time Budget:** All auto-advance delays must sum to well under 5 minutes (NFR7) — defaults total ~60-75s

### Critical Reuse — DO NOT REINVENT

- **Existing `_get_fault_state(app)` pattern** in `demo/app/server.py` — REPLICATE this pattern for `_get_lifecycle_state(app)`
- **Existing `_create_fault_state()` pattern** — REPLICATE for `_create_lifecycle_state()`
- **Existing fault control API** (`/fault/inject`, `/fault/recover`) — CALL these internally from lifecycle orchestrator, do not duplicate fault logic
- **Existing Prometheus registry** — add new metrics to same `registry` instance
- **Existing test fixtures** in `demo/tests/conftest.py` — reuse `client`, `app`, role-specific fixtures
- **Existing `FAULT_TYPES` dict** — reference for fault_type validation and narrative templates
- **Flask app factory** `create_app()` — add lifecycle routes via `_register_lifecycle_routes(app, active_role, logger)`, keep same pattern as `_register_fault_control_routes`

### Lifecycle Stage Flow

```
healthy → fault_injected → detecting → investigating → fix_proposed → fix_applied → verifying → recovered → kb_created
```

Each stage transition:
1. Updates lifecycle state dict
2. Appends to stage_history with timestamp and duration
3. Sets Prometheus gauge for current stage
4. Schedules next stage transition (via Timer or synchronous in TESTING mode)

### Lifecycle Start API Design

```
POST /lifecycle/start
Body: {
  "fault_type": "memory-leak",       # Required — must be valid FAULT_TYPES key
  "trust_level": 5,                   # Optional — default 5 (fully autonomous)
  "timing": {                         # Optional — override default stage durations
    "detect_seconds": 8,
    "investigate_seconds": 15,
    "fix_propose_seconds": 5,
    "fix_apply_seconds": 5,
    "verify_seconds": 10,
    "recover_seconds": 5,
    "kb_create_seconds": 5
  }
}
Response: {
  "status": "started",
  "fault_type": "memory-leak",
  "trust_level": 5,
  "service": "<role>",
  "current_stage": "fault_injected",
  "estimated_duration_seconds": 53
}

GET /lifecycle/status
Response: {
  "service": "<role>",
  "lifecycle_active": true,
  "current_stage": "investigating",
  "fault_type": "memory-leak",
  "trust_level": 5,
  "started_at": "2026-03-18T12:00:00Z",
  "total_elapsed_ms": 23000,
  "stage_history": [
    {"stage": "healthy", "timestamp": "...", "duration_ms": 0, "narrative": "..."},
    {"stage": "fault_injected", "timestamp": "...", "duration_ms": 100, "narrative": "..."},
    {"stage": "detecting", "timestamp": "...", "duration_ms": 8000, "narrative": "..."},
    {"stage": "investigating", "timestamp": "...", "duration_ms": null, "narrative": "..."}
  ]
}

POST /lifecycle/reset
Response: {
  "status": "reset",
  "service": "<role>",
  "previous_stage": "investigating",
  "faults_cleared": true
}

GET /lifecycle/timeline
Response: {
  "service": "<role>",
  "lifecycle_complete": true,
  "total_duration_ms": 53000,
  "fault_type": "memory-leak",
  "trust_level": 5,
  "stages": [
    {"stage": "healthy", "timestamp": "...", "duration_ms": 0, "narrative": "The application is running normally..."},
    ...
  ]
}
```

### TESTING Mode Behavior

In TESTING mode (`app.config["TESTING"] = True`):
- All stage transitions happen synchronously (no threading.Timer)
- Call `_advance_lifecycle_stage(app)` directly in a loop to complete lifecycle
- Zero-delay between stages for fast test execution
- Alternative: provide a `_run_lifecycle_sync(app)` helper for tests

### Mapping to NFRs

- **NFR7** (Demo full lifecycle < 5 minutes): Default timing sums to ~53-75 seconds, well under budget
- **NFR18** (10 consecutive runs without failure): Deterministic stage progression, no external dependencies in test mode

### Previous Story (8-2) Learnings

- Runtime fault state refactored to app-level mutable dict — replicate exact same pattern for lifecycle state
- `_get_fault_state(app)` with fallback to default state — use identical `_get_fault_state`-style accessor
- Fault inject/recover API works well — lifecycle start should call fault_inject internally to avoid code duplication
- `FAULT_TYPES` dict provides descriptions and expected_beeper_response — use these in lifecycle narration
- 180 existing demo tests must remain green after changes
- Prometheus registry is shared — new metrics added to same instance
- `elif` chain pattern in fault_middleware corrected — lifecycle stage handling should also use elif

### Testing Standards

- **pytest** for all tests (project standard)
- **Test file:** `demo/tests/test_lifecycle.py` — new dedicated file
- **Test naming:** `test_<lifecycle_behavior>` pattern
- **Test class organization:** `TestLifecycleStartEndpoint`, `TestLifecycleStatusEndpoint`, `TestLifecycleResetEndpoint`, `TestLifecycleTimeline`, `TestLifecycleAutoAdvance`, `TestLifecycleNarration`, `TestLifecycleMetrics`, `TestLifecycleEdgeCases`
- **Fixtures:** Reuse existing conftest.py fixtures, add lifecycle-specific fixtures as needed
- **No external K8s required** — test lifecycle logic directly via Flask test client
- **Parametrize:** Use `@pytest.mark.parametrize` for testing all fault types through lifecycle

### Project Structure Notes

```
demo/
├── app/
│   └── server.py           # MODIFY: add lifecycle orchestrator API, lifecycle metrics
├── tests/
│   ├── conftest.py          # VERIFY: no changes needed (reuse existing fixtures)
│   ├── test_server.py       # VERIFY: no regressions
│   ├── test_fault_injection.py  # VERIFY: no regressions
│   ├── test_lifecycle.py    # NEW: comprehensive lifecycle orchestrator tests
│   ├── test_k8s_manifests.py    # VERIFY: no regressions
│   └── test_slo_manifests.py    # VERIFY: no regressions
Makefile                     # MODIFY: add demo-lifecycle, demo-lifecycle-status, demo-lifecycle-reset, demo-lifecycle-timeline targets
```

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 8, Story 8.3]
- [Source: _bmad-output/planning-artifacts/architecture.md#Demo Application Architecture]
- [Source: _bmad-output/planning-artifacts/prd.md#FR56, NFR7, NFR18]
- [Source: demo/app/server.py#_get_fault_state, _create_fault_state, _register_fault_control_routes]
- [Source: demo/app/server.py#FAULT_TYPES]
- [Source: demo/tests/conftest.py#fixtures]
- [Source: demo/tests/test_fault_injection.py#test patterns]
- [Source: Makefile#demo targets]
- [Source: _bmad-output/implementation-artifacts/8-2-configurable-fault-injection.md#Dev Notes]
- [Source: _bmad-output/implementation-artifacts/8-1-chaotic-demo-application-deployment.md#Dev Notes]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Completion Notes List

- Added lifecycle orchestrator with 9-stage flow: healthy → fault_injected → detecting → investigating → fix_proposed → fix_applied → verifying → recovered → kb_created
- Lifecycle state management follows exact same pattern as fault state (`_create_lifecycle_state()`, `_get_lifecycle_state(app)`)
- 4 lifecycle API endpoints: POST /lifecycle/start, GET /lifecycle/status, POST /lifecycle/reset, GET /lifecycle/timeline
- Lifecycle start internally injects faults using existing fault state (no code duplication)
- Auto-advance via `threading.Timer` in production mode, synchronous `_run_lifecycle_sync()` in TESTING mode
- Default timing sums to 53 seconds — well under NFR7's 5-minute budget
- 9 investor-friendly narration templates with fault_type, trust_level, and elapsed time interpolation
- Fault recovery happens automatically at the "recovered" stage, clearing fault state and metrics
- 3 new Prometheus metrics: demo_lifecycle_stage gauge, demo_lifecycle_duration_seconds gauge, demo_lifecycle_runs_total counter
- 4 Makefile targets: demo-lifecycle, demo-lifecycle-status, demo-lifecycle-reset, demo-lifecycle-timeline
- 60 new lifecycle tests across 8 test classes covering all endpoints, narration, metrics, and edge cases
- All 240 demo tests passing (180 existing + 60 new), zero regressions
- No regressions: operator 538, investigator 371, UI 2023 passed
- Ruff linting passes clean on all modified files

### File List

- demo/app/server.py (MODIFIED, ~830 lines) — Added lifecycle orchestrator: stages, state management, narration, auto-advance, 4 API endpoints, 3 Prometheus metrics
- demo/tests/test_lifecycle.py (NEW, ~440 lines) — Comprehensive lifecycle tests (60 tests) across 8 test classes
- Makefile (MODIFIED) — Added demo-lifecycle, demo-lifecycle-status, demo-lifecycle-reset, demo-lifecycle-timeline targets
- _bmad-output/implementation-artifacts/8-3-full-lifecycle-demonstration.md (MODIFIED) — Story spec with task completion
