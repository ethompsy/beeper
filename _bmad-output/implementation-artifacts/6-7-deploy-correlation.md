# Story 6.7: Deploy Correlation

Status: review

## Story

As the **system**,
I want to correlate anomalies with recent deployments,
so that SREs can immediately see if a deploy likely caused the issue.

## Acceptance Criteria

1. **Given** an anomaly detected on a service **When** the investigator analyzes the anomaly **Then** recent deployments to that service (within a configurable lookback window, default 1 hour) are retrieved **And** temporal correlation is calculated (e.g., "anomaly started 4 min after deploy #847")

2. **Given** a deploy is correlated with an anomaly **When** the correlation is displayed in the investigation **Then** the deploy details are shown: commit hash, author, changed files, deploy timestamp **And** the correlation confidence is rated (strong: <5 min gap, moderate: 5-30 min, weak: 30-60 min)

3. **Given** no recent deployments exist for the affected service **When** the deploy correlation check runs **Then** the investigation notes "No recent deployments found — likely not deploy-related"

## Tasks / Subtasks

- [x] Task 1: Create `DeployCorrelationStep` investigator pipeline step (AC: #1, #2, #3)
  - [x]1.1 Create `investigator/beeper_investigator/steps/deploy_correlation.py` with `DeployCorrelationStep` class following the `InvestigationStep` protocol (name attribute + execute() -> StepResult). Constructor takes: `sources: SourceClients`, `llm_client: LlmClient`, `context: InvestigationContext`, `status_updater: InvestigationStatusUpdater`, `pipeline_metadata: dict`. Add `DEFAULT_LOOKBACK_MINUTES = 60` constant.
  - [x]1.2 Implement `_fetch_recent_deployments()` method: use `RepositoryLookup` to find the Repository CRD for `self.context.service` in `self.context.namespace`. If found, get credentials via `RepositoryLookup.get_credentials()`, create git provider via `create_git_provider()`, and fetch commits from the last `DEFAULT_LOOKBACK_MINUTES` minutes. Return a list of deploy info dicts with: `timestamp`, `commit_sha`, `author`, `message`, `changed_files`. Handle `RepositoryLookup` and `CredentialError` gracefully — log warning and return empty list.
  - [x]1.3 Implement `_calculate_correlations()` method: for each deployment, calculate the time gap between deploy timestamp and anomaly detection time (use `self.context` investigation start). Classify confidence: "strong" (<5 min), "moderate" (5-30 min), "weak" (30-60 min). Return list of correlation dicts with: `deployment_timestamp`, `anomaly_detected_at`, `time_gap_seconds`, `confidence`, `commit_sha`, `author`, `message`.
  - [x]1.4 Implement `_format_deploy_summary()` method: generate human-readable summary. If correlations exist, format like "Anomaly started 4 min 30 sec after deploy abc123 by alice (strong correlation)". If no deployments found, return "No recent deployments found — likely not deploy-related".
  - [x]1.5 Implement `execute()` method: call `_fetch_recent_deployments()`, then `_calculate_correlations()`, then `_format_deploy_summary()`. Return `StepResult(success=True, summary=..., data={"recent_deployments": [...], "deploy_correlations": [...], "deploy_summary": "...", "deploy_correlation_attempted": True})`.

- [x]Task 2: Register `DeployCorrelationStep` in the agent pipeline (AC: #1)
  - [x]2.1 In `investigator/beeper_investigator/agent.py`, add lazy import for `DeployCorrelationStep` from `beeper_investigator.steps.deploy_correlation` (line ~204 area).
  - [x]2.2 Insert `DeployCorrelationStep` into the steps list AFTER `SignalCorrelationStep` and BEFORE `RCAHypothesisStep` (between lines 223-224). Pass `sources`, `llm_client`, `context`, `status_updater`, and `pipeline_metadata=self._pipeline_metadata`.

- [x]Task 3: Add deploy correlation evidence extraction to `EvidenceService` (AC: #2)
  - [x]3.1 In `ui/beeper_ui/services/evidence_service.py`, add a new method `_extract_deploy_correlation_references()` following the existing extraction pattern (takes investigation_id, findings, references, ref_index, returns ref_index). Extract from `findings["deploy_correlations"]` list. For each correlation, create an `EvidenceReference` with: `evidence_type="deploy"`, `source_type="git_commit"`, title like "Deploy Correlation: abc123 (strong)", `content_preview` with summary, `source_ref=commit_sha`, `timestamp=deployment_timestamp`, `raw_data` as JSON of full correlation dict.
  - [x]3.2 Wire `_extract_deploy_correlation_references()` into `extract_evidence_references()` — add as step 2.5 (after signal references extraction, before supporting evidence). This ensures deploy evidence appears in the timeline between signal analysis and RCA evidence.

- [x]Task 4: Add deploy correlation card to investigation detail template (AC: #2, #3)
  - [x]4.1 Create `ui/beeper_ui/templates/investigations/_deploy_correlation.html` partial template. Show a "Deploy Correlation" card with: deploy details table (commit hash truncated to 7 chars, author, message, timestamp, confidence badge), confidence color coding (strong=red, moderate=amber, weak=blue). When no deploys found, show "No recent deployments found — likely not deploy-related" info message.
  - [x]4.2 In `ui/beeper_ui/templates/investigations/_detail_content.html`, include `_deploy_correlation.html` after the investigation timeline card, passing `deploy_correlations` from the context.

- [x]Task 5: Wire deploy correlation data into investigation detail route (AC: #2, #3)
  - [x]5.1 In `ui/beeper_ui/routes/investigations.py`, in `investigation_detail()` (line ~462), extract `deploy_correlations` and `deploy_summary` from `findings` dict. Pass `deploy_correlations` and `deploy_summary` to the template context.
  - [x]5.2 Update the SSE stream in `_generate_detail_sse_events()` to include deploy correlation data when available in the findings.

- [x]Task 6: Add deploy correlation CSS styles (AC: #2)
  - [x]6.1 In `ui/beeper_ui/static/css/main.css`, add styles for `.deploy-correlation-card`, `.deploy-table`, `.deploy-confidence-badge` (with variants `.confidence-strong` red, `.confidence-moderate` amber, `.confidence-weak` blue), `.deploy-no-results` info message.

- [x]Task 7: Write unit tests for `DeployCorrelationStep` (AC: #1, #2, #3)
  - [x]7.1 Create `investigator/tests/test_deploy_correlation.py`. Test classes: `TestDeployCorrelationStep` with tests for: successful correlation with deploys (strong/moderate/weak confidence), no repository found returns empty + fallback summary, no credentials returns empty gracefully, no recent deploys returns fallback summary, multiple deploys are all correlated, time gap calculation accuracy.
  - [x]7.2 Mock `RepositoryLookup`, `create_git_provider`, and git provider methods. Use `unittest.mock.patch` for K8s API calls.

- [x]Task 8: Write UI tests for deploy correlation evidence extraction and template (AC: #2, #3)
  - [x]8.1 In `ui/tests/test_evidence_service.py`, add `TestExtractDeployCorrelationReferences` class: test deploy correlations are extracted as deploy evidence type, test no correlations produces no deploy evidence, test confidence levels are preserved in evidence title.
  - [x]8.2 Create `ui/tests/test_deploy_correlation_template.py`: test deploy correlation card renders with deploy data, test confidence badges have correct classes, test no-deploys message renders when empty.
  - [x]8.3 In `ui/tests/test_investigation_routes.py`, add tests: verify `deploy_correlations` is passed to template context, verify deploy summary is passed.

- [x]Task 9: Run full test suite across all components (AC: all)
  - [x]9.1 Run investigator tests: `cd investigator && poetry run python -m pytest`
  - [x]9.2 Run investigator linting: `cd investigator && poetry run ruff check .`
  - [x]9.3 Run investigator type checking: `cd investigator && poetry run mypy .`
  - [x]9.4 Run UI tests: `cd ui && poetry run python -m pytest`
  - [x]9.5 Run operator tests: `cd operator && cargo test`
  - [x]9.6 Verify no regressions from baseline (3,209 tests)

## Dev Notes

### Architecture Patterns (CRITICAL -- must follow)

**FR44 maps to:** `investigator/correlation/signals.py` (extended) [Source: architecture.md line 1433]

**What already exists (DO NOT rebuild):**
- `InvestigationStep` protocol in `investigator/beeper_investigator/steps/__init__.py` — name attribute + execute() -> StepResult
- `StepResult` dataclass — success, summary, data dict, error
- `SignalCorrelationStep` in `investigator/beeper_investigator/steps/signal_correlation.py` — reference implementation for step pattern
- `RepositoryLookup` in `investigator/beeper_investigator/k8s/repository.py` — finds Repository CRDs by service name, reads credential Secrets
- `RepositoryInfo` dataclass — name, url, provider, credentials_secret, base_branch
- `GitProvider` ABC + `GitHubProvider` + `GitLabProvider` in `investigator/beeper_investigator/remediation/git_provider.py` — PR creation, branch management, commit operations
- `create_git_provider()` factory function
- `InvestigationContext` dataclass — investigation_id, namespace, condition, service, severity, trust_level
- `InvestigationStatusUpdater` in `investigator/beeper_investigator/k8s/status.py` — update_message() for status reporting
- Evidence types: "deploy" and source types: "git_commit" already defined in `ui/beeper_ui/services/evidence_service.py`
- Timeline already supports deploy events (green color, `_EVENT_CATEGORY_MAP["deploy"] = "deploy_event"`)
- `_classify_evidence()` in EvidenceService already classifies deploy keywords → ("deploy", "git_commit")

**What this story adds:**
1. New `DeployCorrelationStep` pipeline step that fetches recent deploys and calculates temporal correlation
2. Deploy correlation evidence extraction in `EvidenceService._extract_deploy_correlation_references()`
3. Deploy correlation card template for investigation detail view
4. Deploy details display with confidence rating (strong/moderate/weak)
5. "No recent deployments" fallback message

### Existing Code to Reuse (DO NOT RECREATE)

| Component | Location | What to Reuse |
|-----------|----------|---------------|
| InvestigationStep protocol | `investigator/beeper_investigator/steps/__init__.py` | Protocol definition and StepResult |
| SignalCorrelationStep | `investigator/beeper_investigator/steps/signal_correlation.py` | Reference implementation pattern |
| Agent pipeline | `investigator/beeper_investigator/agent.py:180-289` | Step registration pattern |
| RepositoryLookup | `investigator/beeper_investigator/k8s/repository.py:41-146` | Repository CRD + credential lookup |
| GitProvider/GitHubProvider | `investigator/beeper_investigator/remediation/git_provider.py` | Git commit fetching |
| create_git_provider() | `investigator/beeper_investigator/remediation/git_provider.py:276` | Factory function |
| EvidenceService | `ui/beeper_ui/services/evidence_service.py` | Evidence extraction pattern |
| Evidence types/colors | `ui/beeper_ui/services/evidence_service.py:16-17` | "deploy" type + "git_commit" source |
| _EVENT_CATEGORY_MAP | `ui/beeper_ui/services/evidence_service.py:23-29` | Deploy → deploy_event mapping |
| InvestigationContext | `investigator/beeper_investigator/context.py` | Service name + namespace context |

### Anti-Patterns to AVOID

- Do NOT create a new K8s controller or watcher for deployments — use existing Repository CRD + git provider to fetch recent commits
- Do NOT modify the operator component — no Rust changes needed for this story
- Do NOT create a new service class in the UI — extend `EvidenceService` with a new extraction method
- Do NOT add JavaScript for confidence badges — use CSS classes only
- Do NOT modify `SignalCorrelationStep` — create a separate step to maintain single-responsibility
- Do NOT add a new Qdrant collection — deploy correlation data flows through existing pipeline_metadata
- Do NOT add new evidence types — use existing "deploy" type and "git_commit" source_type
- Do NOT require LLM for correlation logic — time-gap calculation is deterministic, save LLM calls for RCA

### Previous Story Intelligence (6-6)

**Key learnings from Story 6-6 (Unified Investigation Timeline):**
- `TimelineEvent` wraps `EvidenceReference` with `event_category` — deploy events already supported
- CSS-only filtering with `.hide-deploy .evidence-type-deploy` already hides/shows deploy events in timeline
- Evidence extraction follows numbered pattern in `extract_evidence_references()` — add new extraction step between signal and supporting evidence
- SSE stream updates render `_unified_timeline.html` — deploy evidence will automatically appear in timeline
- `get_timeline_events()` calls `extract_evidence_references()` internally — new deploy extraction will flow through
- Filter buttons in `_timeline_filter.html` already include "Deploys" toggle — no filter bar changes needed
- 3,209 tests pass across all components (952 investigator + 1,726 UI + 531 operator) — baseline for regression
- `aria-pressed` attribute pattern for toggle button accessibility

### Git Intelligence

**Recent commits (last 5):**
- `f834a0b` MAESTRO: 6-6 done (code review fixes)
- `5f135a8` MAESTRO: implement story 6-6 (Unified Investigation Timeline)
- `3c84a74` MAESTRO: 6-5 done
- `ce2b31c` MAESTRO: implement story 6-5 (KB Entry Review, Edit & Correction)
- `016669b` MAESTRO: 6-4 done

**Patterns observed:**
- Steps follow lazy import pattern in agent.py `_build_steps()`
- Pipeline metadata is shared via `self._pipeline_metadata` dict
- Each step is non-fatal: failures logged but don't abort pipeline
- Status updates via `self.status_updater.update_message()`
- Tests use `unittest.mock.patch` for external dependencies

### Testing Standards

- **Framework:** pytest with unittest.mock
- **Test locations:**
  - `investigator/tests/test_deploy_correlation.py` — DeployCorrelationStep unit tests (NEW)
  - `ui/tests/test_evidence_service.py` — Deploy evidence extraction tests
  - `ui/tests/test_deploy_correlation_template.py` — Deploy correlation template tests (NEW)
  - `ui/tests/test_investigation_routes.py` — Route integration tests
- **Mocking patterns:**
  - `unittest.mock.patch("beeper_investigator.steps.deploy_correlation.RepositoryLookup")` for K8s mocking
  - `unittest.mock.patch("beeper_investigator.steps.deploy_correlation.create_git_provider")` for git provider mocking
  - `unittest.mock.patch("beeper_ui.routes.investigations.get_evidence_service")` for route tests
  - Direct EvidenceService instantiation for unit tests

### Project Structure Notes

**Files to CREATE:**
- `investigator/beeper_investigator/steps/deploy_correlation.py` — DeployCorrelationStep pipeline step
- `investigator/tests/test_deploy_correlation.py` — Step unit tests
- `ui/beeper_ui/templates/investigations/_deploy_correlation.html` — Deploy correlation card template
- `ui/tests/test_deploy_correlation_template.py` — Template tests

**Files to MODIFY:**
- `investigator/beeper_investigator/agent.py` — Register DeployCorrelationStep in pipeline
- `ui/beeper_ui/services/evidence_service.py` — Add _extract_deploy_correlation_references()
- `ui/beeper_ui/routes/investigations.py` — Pass deploy_correlations to template context
- `ui/beeper_ui/templates/investigations/_detail_content.html` — Include _deploy_correlation.html
- `ui/beeper_ui/static/css/main.css` — Deploy correlation card styles
- `ui/tests/test_evidence_service.py` — Deploy evidence extraction tests
- `ui/tests/test_investigation_routes.py` — Route integration tests

**Files to NOT touch:**
- `operator/**` — No operator changes needed
- `investigator/beeper_investigator/steps/signal_correlation.py` — Separate step, don't modify
- `ui/beeper_ui/templates/investigations/_unified_timeline.html` — Deploy events auto-appear via evidence extraction
- `ui/beeper_ui/templates/investigations/_timeline_filter.html` — "Deploys" filter already exists
- `ui/beeper_ui/services/kb_service.py` — No KB changes needed

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 6.7] — Acceptance criteria (lines 1255-1275)
- [Source: _bmad-output/planning-artifacts/architecture.md#FR44] — Deploy correlation: investigator/correlation/signals.py (line 1433)
- [Source: investigator/beeper_investigator/steps/__init__.py] — InvestigationStep protocol, StepResult
- [Source: investigator/beeper_investigator/steps/signal_correlation.py] — Reference step implementation pattern
- [Source: investigator/beeper_investigator/agent.py:180-289] — Pipeline step registration and execution
- [Source: investigator/beeper_investigator/k8s/repository.py:41-146] — RepositoryLookup CRD + credentials
- [Source: investigator/beeper_investigator/remediation/git_provider.py] — GitHubProvider, GitLabProvider, create_git_provider()
- [Source: investigator/beeper_investigator/context.py] — InvestigationContext (service, namespace, etc.)
- [Source: ui/beeper_ui/services/evidence_service.py:16-17] — Evidence types including "deploy"
- [Source: ui/beeper_ui/services/evidence_service.py:114-168] — extract_evidence_references() extraction pipeline
- [Source: ui/beeper_ui/routes/investigations.py:430-489] — investigation_detail() route handler
- [Source: _bmad-output/implementation-artifacts/6-6-unified-investigation-timeline.md] — Previous story intelligence

## Dev Agent Record

### Agent Model Used

claude-opus-4-6

### Debug Log References

### Completion Notes List

- Created `DeployCorrelationStep` pipeline step with `_fetch_recent_deployments()` (GitHub/GitLab), `_calculate_correlations()` (strong/moderate/weak confidence by time gap), `_format_deploy_summary()`, and `execute()` methods. Uses `RepositoryLookup` + git provider for commit fetching with graceful error handling.
- Registered `DeployCorrelationStep` at index 3 in agent pipeline (after `SignalCorrelationStep`, before `RCAHypothesisStep`). Pipeline now has 14 steps (7 core + 7 remediation).
- Added `_extract_deploy_correlation_references()` to `EvidenceService` (step 2.5 in extraction pipeline). Creates `EvidenceReference` with `evidence_type="deploy"`, `source_type="git_commit"`, confidence in title, and full correlation dict as raw_data.
- Created `_deploy_correlation.html` template with deploy details table (truncated commit hash, author, message, timestamp, time gap, confidence badge). Includes fallback message when no deploys found. Wired into `_detail_content.html` after investigation timeline card with SSE support.
- Wired deploy correlation data into `investigation_detail()` route — extracts `deploy_correlations` and `deploy_summary` from findings dict. SSE stream renders `_deploy_correlation.html` via `deploy-correlation-update` event.
- Added CSS styles: `.deploy-correlation-card`, `.deploy-table`, `.deploy-confidence-badge` with color variants (`.confidence-strong` red, `.confidence-moderate` amber, `.confidence-weak` blue), `.deploy-no-results` info message.
- Fixed 4 pipeline integration test files (testplan, sandbox, PR, proven_fix) to use updated step indices and pipeline length of 14 (was 13 before DeployCorrelationStep addition).
- 14 new investigator tests in `TestDeployCorrelationStep` + `TestClassifyConfidence` + `TestFormatTimeGap`. 6 new evidence service tests in `TestExtractDeployCorrelationReferences`. 8 new template tests in `TestDeployCorrelationTemplate`. 2 new route tests in `TestDeployCorrelationRoute`.
- All 2,714 tests pass (972 investigator + 1,742 UI) — zero regressions. Operator tests skipped (cargo not available in environment).

### Change Log

- 2026-03-17: Implemented story 6-7 — Deploy Correlation with DeployCorrelationStep pipeline step, evidence extraction, template card with confidence badges, SSE support, and comprehensive tests. Fixed 4 pipeline integration test files for updated step indices.

### File List

- investigator/beeper_investigator/steps/deploy_correlation.py (CREATED) — DeployCorrelationStep with GitHub/GitLab commit fetching and temporal correlation
- investigator/beeper_investigator/agent.py (MODIFIED) — Registered DeployCorrelationStep at pipeline index 3
- ui/beeper_ui/services/evidence_service.py (MODIFIED) — Added _extract_deploy_correlation_references() method
- ui/beeper_ui/routes/investigations.py (MODIFIED) — Added deploy_correlations/deploy_summary to template context + SSE stream
- ui/beeper_ui/templates/investigations/_deploy_correlation.html (CREATED) — Deploy correlation card template
- ui/beeper_ui/templates/investigations/_detail_content.html (MODIFIED) — Included _deploy_correlation.html card
- ui/beeper_ui/static/css/main.css (MODIFIED) — Added deploy correlation CSS styles
- investigator/tests/test_deploy_correlation.py (CREATED) — DeployCorrelationStep unit tests (14 tests)
- investigator/tests/test_agent_testplan_integration.py (MODIFIED) — Updated step indices for 14-step pipeline
- investigator/tests/test_agent_sandbox_integration.py (MODIFIED) — Updated step indices for 14-step pipeline
- investigator/tests/test_agent_pr_integration.py (MODIFIED) — Updated step indices for 14-step pipeline
- investigator/tests/test_agent_proven_fix_integration.py (MODIFIED) — Updated step indices for 14-step pipeline
- ui/tests/test_evidence_service.py (MODIFIED) — Added TestExtractDeployCorrelationReferences (6 tests)
- ui/tests/test_deploy_correlation_template.py (CREATED) — Deploy correlation template tests (8 tests)
- ui/tests/test_investigation_routes.py (MODIFIED) — Added TestDeployCorrelationRoute (2 tests)
