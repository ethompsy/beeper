# Story 4.4: Auto-PR Generation with Evidence Trail

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the **system**,
I want to generate auto-PRs with full evidence trails linking back to the investigation,
so that code reviewers have complete context on why the fix is proposed and what evidence supports it.

## Acceptance Criteria

1. **Given** an investigation that identifies a code-level fix in a registered Repository
   **When** the fix is generated at TL3+ or manually approved
   **Then** a branch is created per the repository's branch_policy, the fix is committed, and a PR is opened
   **And** the PR description includes: investigation link, root cause analysis, log correlation evidence, production conditions at time of incident

2. **Given** an auto-PR is created
   **When** the PR is viewed on the Git provider
   **Then** the audit trail is complete: anomaly → investigation → fix → PR
   **And** the PR is linked back to the investigation in Qdrant (FR30)

3. **Given** an auto-PR for a service at TL3 (act with approval)
   **When** the PR is created
   **Then** the PR is marked as draft/WIP and the SRE is notified for review
   **And** at TL4-5, the PR is opened as ready for merge (per branch policy)

## Tasks / Subtasks

- [x] Task 1: Create GitProvider abstraction and GitHub/GitLab implementations (AC: #1, #2)
  - [x]1.1 Create `investigator/beeper_investigator/remediation/git_provider.py` with abstract `GitProvider` base class defining interface: `create_branch(base_branch, new_branch) -> bool`, `commit_files(branch, files: dict[str, str], message: str) -> str` (returns commit SHA), `create_pr(title, body, head_branch, base_branch, draft: bool) -> PRResult`, `get_default_branch() -> str`
  - [x]1.2 Define `PRResult` dataclass: `pr_url: str`, `pr_number: int`, `branch_name: str`, `commit_sha: str`, `provider: str`, `draft: bool`, `created_at: str`
  - [x]1.3 Implement `GitHubProvider(GitProvider)` using PyGithub: constructor takes `repo_url: str`, `token: str`; parses owner/repo from URL; creates `Github(token).get_repo(owner/repo)` handle; implements all interface methods using PyGithub API (`repo.create_git_ref()`, `repo.create_file()` / `repo.update_file()`, `repo.create_pull()`)
  - [x]1.4 Implement `GitLabProvider(GitProvider)` using python-gitlab: constructor takes `repo_url: str`, `token: str`; parses project path from URL; creates `gitlab.Gitlab(url, private_token=token)` handle; implements all interface methods using python-gitlab API (`project.branches.create()`, `project.files.create()`, `project.mergerequests.create()`)
  - [x]1.5 Implement factory function `create_git_provider(provider_type: str, repo_url: str, token: str) -> GitProvider` that returns `GitHubProvider` or `GitLabProvider` based on `provider_type`

- [x]Task 2: Create Repository CRD lookup utility (AC: #1)
  - [x]2.1 Create `investigator/beeper_investigator/k8s/repository.py` with `RepositoryLookup` class. Constructor: `__init__(self)` — initializes `kubernetes.client.CustomObjectsApi()` and `kubernetes.client.CoreV1Api()` (for Secrets). Load cluster config via `config.load_incluster_config()` with fallback to `config.load_kube_config()` — same pattern as `InvestigationStatusUpdater`
  - [x]2.2 Implement `find_repository(service_name: str, namespace: str) -> RepositoryInfo | None`: list Repository CRDs via `custom_api.list_namespaced_custom_object(group="beeper.dev", version="v1", namespace=namespace, plural="repositories")`, match by service name in metadata or spec.url, return first match with condition="Connected" (skip AuthError/NotFound/Error), return None if no match
  - [x]2.3 Define `RepositoryInfo` dataclass: `name: str`, `url: str`, `provider: str` ("github" | "gitlab"), `credentials_secret: str`, `base_branch: str` (default "main"), `pr_branch_prefix: str` (default "beeper/"), `require_pr: bool` (default True), `language: str | None`, `linter: str | None`, `test_command: str | None`
  - [x]2.4 Implement `get_credentials(secret_name: str, namespace: str) -> str`: read K8s Secret via `core_api.read_namespaced_secret(secret_name, namespace)`, decode base64 `data["token"]` field, return token string. Raise `CredentialError` if Secret not found or `token` key missing.

- [x]Task 3: Create evidence trail formatter (AC: #1, #2)
  - [x]3.1 Create `investigator/beeper_investigator/remediation/evidence_trail.py` with `EvidenceTrailFormatter` class
  - [x]3.2 Implement `format_pr_body(context: InvestigationContext, pipeline_metadata: dict, fix_description: str) -> str`: generates markdown PR body with sections: **Investigation Summary** (investigation_id, service, condition, severity, namespace), **Root Cause Analysis** (hypothesis from pipeline_metadata, confidence level/percentage, supporting evidence), **Log Correlation Evidence** (signal_summary, layers_queried from pipeline_metadata), **Production Conditions** (timestamp, severity, customer_impacting flag), **Advisory Test Plan** (verification steps from test_plan data if available), **Audit Trail** (anomaly → investigation → fix → PR chain with IDs/links)
  - [x]3.3 Implement `format_commit_message(context: InvestigationContext, fix_description: str) -> str`: generates structured commit message with format `fix({service}): {short_description}\n\nInvestigation: {investigation_id}\nRoot Cause: {hypothesis}\nConfidence: {confidence_level} ({confidence_percentage}%)`

- [x]Task 4: Create PRGeneratorStep class (AC: #1, #2, #3)
  - [x]4.1 Create `investigator/beeper_investigator/remediation/pr_generator.py` with `PRGeneratorStep` class implementing `InvestigationStep` protocol with `name = "PR Generation"`
  - [x]4.2 Constructor: `__init__(self, llm_client: LlmClient, context: InvestigationContext, status_updater: InvestigationStatusUpdater, pipeline_metadata: dict[str, Any] | None = None)` — same signature pattern as RunbookExecutorStep and TestPlannerStep. Also instantiate `RepositoryLookup()` and `EvidenceTrailFormatter()` internally
  - [x]4.3 Implement trust-level gating in `execute()`: if `context.trust_level < 3`, return `StepResult(success=True, summary="PR generation skipped — trust level {trust_level} below TL3 threshold", data={"pr_generated": False, "skip_reason": "trust_level_insufficient"})`. This is the key differentiator from TestPlannerStep which always runs
  - [x]4.4 Implement repository lookup: call `repository_lookup.find_repository(context.service, context.namespace)` — if no repository found, return `StepResult(success=True, summary="No registered repository found for service '{service}'", data={"pr_generated": False, "skip_reason": "no_repository"})`
  - [x]4.5 Implement fix generation via LLM: extract `root_cause_hypothesis` and `supporting_evidence` from pipeline_metadata; define `_FIX_GENERATION_SYSTEM_PROMPT` instructing LLM to act as senior developer proposing a minimal, targeted code fix for the root cause; define `_FIX_GENERATION_USER_TEMPLATE` with investigation context, hypothesis, evidence, coding standards from RepositoryInfo; call `llm_client.complete_sync()` with model from `_get_model_name()`, `temperature=0.0`, `max_tokens=4096`; parse response as JSON with fields `files: dict[str, str]` (filepath → content), `description: str`, `change_summary: str`
  - [x]4.6 Implement PR creation flow: get credentials → create git provider → create branch (`{pr_branch_prefix}{investigation_id}`) → commit files → create PR (draft if TL3, ready if TL4-5) → return PRResult
  - [x]4.7 Implement Qdrant investigation-PR linking (FR30): after PR creation, store PR metadata in pipeline_metadata for InvestigationDocumentationStep to persist: `pr_url`, `pr_number`, `branch_name`, `commit_sha`, `provider`, `draft`
  - [x]4.8 Return `StepResult.data` with: `pr_generated: bool`, `pr_url: str`, `pr_number: int`, `branch_name: str`, `commit_sha: str`, `provider: str`, `draft: bool`, `fix_description: str`, `files_changed: list[str]`, `evidence_trail_included: bool`, `trust_level: int`, `pr_model_tier: str`, `pr_model_used: str`

- [x]Task 5: Update remediation package exports (AC: #1)
  - [x]5.1 Add `PRGeneratorStep`, `GitProvider`, `GitHubProvider`, `GitLabProvider`, `PRResult`, `EvidenceTrailFormatter`, `RepositoryInfo` to `investigator/beeper_investigator/remediation/__init__.py` imports and `__all__`

- [x]Task 6: Update k8s package exports
  - [x]6.1 Add `RepositoryLookup`, `RepositoryInfo`, `CredentialError` to `investigator/beeper_investigator/k8s/__init__.py` imports and `__all__`

- [x]Task 7: Integrate PRGeneratorStep into agent pipeline (AC: #1, #2, #3)
  - [x]7.1 In `investigator/beeper_investigator/agent.py`, add `PRGeneratorStep` as step 9 after `TestPlannerStep` in `_build_steps()`. Import lazily in `_build_steps()` following existing pattern
  - [x]7.2 Pass `pipeline_metadata`, `llm_client`, `context`, `status_updater` to constructor (same as TestPlannerStep)
  - [x]7.3 Update existing step count assertions in test files if needed

- [x]Task 8: Add PyGithub and python-gitlab dependencies
  - [x]8.1 Add `PyGithub = "^2.2"` and `python-gitlab = "^4.4"` to `investigator/pyproject.toml` under `[tool.poetry.dependencies]`
  - [x]8.2 Run `cd investigator && poetry lock --no-update` (or equivalent) to update lock file if present

- [x]Task 9: Write comprehensive tests (AC: #1, #2, #3)
  - [x]9.1 Create `investigator/tests/test_git_provider.py` with test classes:
    - `TestGitHubProvider`: mock PyGithub, test create_branch, commit_files, create_pr (draft and ready), URL parsing (github.com/owner/repo)
    - `TestGitLabProvider`: mock python-gitlab, test create_branch, commit_files, create_pr (draft and ready), URL parsing (gitlab.com/group/project)
    - `TestProviderFactory`: correct provider returned for "github"/"gitlab", ValueError for unknown provider
  - [x]9.2 Create `investigator/tests/test_repository_lookup.py` with test classes:
    - `TestFindRepository`: mock K8s API, test repository found (Connected), repository skipped (AuthError), no repository found, multiple repositories (first Connected returned)
    - `TestGetCredentials`: mock K8s Secret read, token decoded correctly, missing Secret raises CredentialError, missing token key raises CredentialError
  - [x]9.3 Create `investigator/tests/test_evidence_trail.py` with test classes:
    - `TestFormatPRBody`: all sections present, investigation context correct, RCA hypothesis included, test plan steps included, missing optional fields handled gracefully
    - `TestFormatCommitMessage`: format correct, service and investigation_id included
  - [x]9.4 Create `investigator/tests/test_pr_generator.py` with test classes:
    - `TestTrustGating`: TL1 skips with reason, TL2 skips with reason, TL3 proceeds, TL4-5 proceeds
    - `TestRepositoryLookup`: no repository found returns skip, repository found proceeds
    - `TestFixGeneration`: LLM response parsed correctly, invalid JSON handled, empty files handled
    - `TestPRCreation`: TL3 creates draft PR, TL4 creates ready PR, TL5 creates ready PR, PR metadata in StepResult.data correct
    - `TestEvidenceTrail`: PR body includes investigation link, RCA included, audit trail complete
    - `TestPipelineMetadata`: PR metadata stored for downstream consumption, fix_description passed through
  - [x]9.5 Create `investigator/tests/test_agent_pr_integration.py`: verify PRGeneratorStep is step 9 in `_build_steps()`, verify pipeline_metadata is shared (hypothesis + test plan flow to PR step), verify step is only included when trust_level >= 3 OR always included (step itself gates internally)

- [x]Task 10: Run all investigator tests (AC: #1, #2, #3)
  - [x]10.1 Run `cd investigator && python -m pytest tests/ -v` — all existing + new tests pass
  - [x]10.2 Run `cd investigator && python -m ruff check .` — no new warnings
  - [x]10.3 Verify zero regressions in existing step tests

## Dev Notes

### Architecture Patterns to Follow

**CRITICAL CONTEXT: This story adds the PRGeneratorStep to the investigator pipeline. Unlike TestPlannerStep (4-3) which always runs regardless of trust level, this step is TRUST-GATED — it only creates PRs at TL3+. At TL3, PRs are created as draft/WIP. At TL4-5, PRs are opened as ready-for-merge. The step also requires a registered Repository CRD with valid credentials. The evidence trail links the full chain: anomaly → investigation → RCA → test plan → fix → PR.**

**What already exists (DO NOT recreate):**

| Component | Location | Status |
|-----------|----------|--------|
| `InvestigationStep` protocol + `StepResult` | `investigator/beeper_investigator/steps/__init__.py` | Done (v0.1.0) |
| 6-step investigation pipeline | `investigator/beeper_investigator/steps/` | Done (v0.1.0) |
| `RunbookExecutorStep` (step 7) | `investigator/beeper_investigator/remediation/runbook_executor.py` | Done (Story 4-2) |
| `TestPlannerStep` (step 8) | `investigator/beeper_investigator/remediation/test_planner.py` | Done (Story 4-3) |
| `remediation/__init__.py` package | `investigator/beeper_investigator/remediation/__init__.py` | Done (Story 4-2) |
| `InvestigatorAgent` lifecycle + `_build_steps()` | `investigator/beeper_investigator/agent.py` | Done — 8 steps currently |
| `LlmClient` with `select_model()`, `complete_sync()` | `investigator/beeper_investigator/llm/client.py` | Done (v0.1.0) |
| `InvestigationContext` with `trust_level`, `confidence_threshold` | `investigator/beeper_investigator/context.py` | Done (Story 4-2) |
| `InvestigationStatusUpdater` using `CustomObjectsApi` | `investigator/beeper_investigator/k8s/status.py` | Done (v0.1.0) |
| `RCAHypothesisStep` (populates pipeline_metadata with hypothesis) | `investigator/beeper_investigator/steps/rca_hypothesis.py` | Done (v0.1.0) |
| Repository CRD (Rust operator side) | `operator/src/crds/repository.rs` | Done (Story 4-1) |
| Repository controller (Rust operator side) | `operator/src/controllers/repository.rs` | Done (Story 4-1) |

**What this story adds:**

| Component | Description |
|-----------|-------------|
| `remediation/git_provider.py` | Abstract `GitProvider` + `GitHubProvider` + `GitLabProvider` implementations |
| `remediation/evidence_trail.py` | `EvidenceTrailFormatter` — formats PR body with full evidence chain |
| `remediation/pr_generator.py` | `PRGeneratorStep` — trust-gated PR creation with evidence trail |
| `k8s/repository.py` | `RepositoryLookup` — find Repository CRDs + read credential Secrets |
| Agent pipeline step 9 | `PRGeneratorStep` wired into `_build_steps()` |
| New dependencies | `PyGithub ^2.2`, `python-gitlab ^4.4` |
| Tests | Unit + integration tests for all new components |

### Pipeline Metadata — Data Flow (CRITICAL)

The `pipeline_metadata` dict is shared by reference across all steps. After prior steps run, it contains:

```python
# Available from step 4 (RCAHypothesisStep):
{
    "root_cause_hypothesis": "Memory leak in connection pool causing OOM kills",
    "confidence_level": "high",          # "high"|"medium"|"low"
    "confidence_percentage": 85,          # 0-100
    "supporting_evidence": ["Pod restarts correlate with memory growth", ...],
    "alternative_hypotheses": [{"description": "...", "confidence_percentage": 40}, ...],
    "additional_data_needs": ["Heap dump analysis", ...],
}

# Available from earlier steps:
{
    "customer_impacting": True,           # from CustomerImpactStep
    "signal_summary": "...",              # from SignalCorrelationStep
    "service_dependency_chain": [...],    # from SignalCorrelationStep
    "layers_queried": [...],              # from SignalCorrelationStep
}

# Available from step 8 (TestPlannerStep):
{
    "test_plan_generated": True,
    "verification_steps": [...],          # list of test plan steps
    "metrics_to_watch": [...],
    "estimated_duration_minutes": 15,
    "promotable_to_sandbox": True,
}

# PRGeneratorStep will ADD to pipeline_metadata:
{
    "pr_generated": True,
    "pr_url": "https://github.com/org/service/pull/42",
    "pr_number": 42,
    "branch_name": "beeper/inv-abc123",
    "commit_sha": "a1b2c3d4",
    "provider": "github",
    "draft": True,  # True at TL3, False at TL4-5
    "fix_description": "...",
    "files_changed": ["src/pool.py"],
}
```

### Repository CRD Structure (from Story 4-1 Rust implementation)

The Repository CRD in K8s has this structure when queried via Python kubernetes client:

```python
# From CustomObjectsApi.list_namespaced_custom_object():
{
    "apiVersion": "beeper.dev/v1",
    "kind": "Repository",
    "metadata": {"name": "payments-repo", "namespace": "default"},
    "spec": {
        "url": "https://github.com/org/payment-service",
        "provider": "github",           # "github" | "gitlab" (snake_case per CRD)
        "credentials_secret": "github-token-payments",
        "branch_policy": {              # Optional
            "base_branch": "main",      # Optional, default "main"
            "pr_branch_prefix": "beeper/",  # Optional, default "beeper/"
            "require_pr": True,         # Optional, default True
        },
        "coding_standards": {           # Optional
            "language": "python",
            "linter": "ruff",
            "test_command": "pytest",
        },
    },
    "status": {
        "condition": "connected",       # "pending"|"connected"|"auth_error"|"not_found"|"error"
        "last_checked": "2026-03-16T...",
        "default_branch_detected": "main",
    },
}
```

### K8s API Pattern (follow InvestigationStatusUpdater exactly)

```python
from kubernetes import client, config  # type: ignore[import-untyped]
from kubernetes.client.rest import ApiException  # type: ignore[import-untyped]

class RepositoryLookup:
    _GROUP = "beeper.dev"
    _VERSION = "v1"
    _PLURAL = "repositories"

    def __init__(self) -> None:
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        self._custom_api = client.CustomObjectsApi()
        self._core_api = client.CoreV1Api()
```

### Step Protocol Pattern (MUST follow exactly)

```python
class PRGeneratorStep:
    """Generate auto-PR with evidence trail for code fixes."""

    name: str = "PR Generation"

    def __init__(
        self,
        llm_client: LlmClient,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
        pipeline_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.context = context
        self.status_updater = status_updater
        self.pipeline_metadata = pipeline_metadata if pipeline_metadata is not None else {}

    def execute(self) -> StepResult:
        """Generate auto-PR with evidence trail."""
        ...
```

### LLM Call Pattern (follow RunbookExecutorStep / TestPlannerStep)

```python
def _get_model_name(self) -> str | None:
    """Get the model name for remediation tier, with fallback to deep_rca."""
    for tier in ("remediation", "deep_rca"):
        try:
            model = self.llm_client.select_model(tier)
            if model is not None:
                return model
        except (KeyError, ValueError, AttributeError):
            logger.debug("Model tier '%s' not available, trying next", tier)
    return None
```

### Trust-Level Gating Logic

```python
# In execute():
if self.context.trust_level < 3:
    return StepResult(
        success=True,
        summary=f"PR generation skipped — trust level {self.context.trust_level} below TL3 threshold",
        data={"pr_generated": False, "skip_reason": "trust_level_insufficient", "trust_level": self.context.trust_level},
    )

# Later, when creating PR:
draft = self.context.trust_level == 3  # TL3 = draft, TL4-5 = ready
```

### Evidence Trail PR Body Format

```markdown
## Beeper Auto-Fix: {service} — {condition}

### Investigation Summary
- **Investigation ID:** {investigation_id}
- **Service:** {service}
- **Condition:** {condition}
- **Severity:** {severity}
- **Namespace:** {namespace}
- **Customer Impacting:** {customer_impacting}

### Root Cause Analysis
**Hypothesis:** {root_cause_hypothesis}
**Confidence:** {confidence_level} ({confidence_percentage}%)

**Supporting Evidence:**
{bulleted list of supporting_evidence items}

### Log Correlation Evidence
{signal_summary}

**Data Sources Queried:** {layers_queried}

### Production Conditions
- **Detected At:** {timestamp}
- **Severity:** {severity}
- **Customer Impacting:** {customer_impacting}

### Advisory Test Plan
{numbered verification steps from test plan, if available}

### Audit Trail
anomaly ({condition}) → investigation ({investigation_id}) → fix (this PR) → verification (pending)

---
*Generated by [Beeper](https://beeper.dev) | Investigation {investigation_id}*
```

### Fix Generation LLM Prompt Pattern

The fix generation prompt should:
- Act as a senior developer proposing a minimal, targeted code fix
- Input: root cause hypothesis, supporting evidence, coding standards (language, linter)
- Output JSON: `{"files": {"path/to/file.py": "file content..."}, "description": "Short description", "change_summary": "What changed and why"}`
- Temperature 0.0 for deterministic output
- Max tokens 4096 (fixes can be longer than test plans)

### Critical Guardrails

- **Trust-gated**: TL3+ required for PR creation. TL1-2 skip entirely (advisory-only in those modes)
- **Draft vs Ready**: TL3 creates draft PR, TL4-5 creates ready-for-merge PR (AC#3)
- **Repository required**: Must find a registered Repository CRD with status "connected". No repository = skip with explanation
- **Credential scoping**: Per-repo tokens from K8s Secrets, NEVER org-wide (NFR9)
- **Evidence trail mandatory**: Every PR body must include full audit chain (AC#2)
- **FR30 compliance**: PR metadata must be stored in pipeline_metadata for Qdrant persistence
- **`temperature=0.0`** for LLM calls — deterministic fix generation
- **No actual code execution** — this story generates fixes and creates PRs, it does NOT execute the fixes. Sandbox execution is Story 4-5
- **Graceful degradation**: If git provider API fails, return `StepResult(success=True)` with error info — don't crash the pipeline
- **Follow existing `_get_model_name()` pattern** with "remediation" → "deep_rca" fallback
- **Structured JSON logging** via `logging.getLogger(__name__)`
- **PII scrubbing** happens in LlmClient — no need to scrub in step code
- **Zero regressions** — all existing 580 investigator tests must continue passing
- **ruff clean** — no new warnings
- **New dependencies**: PyGithub ^2.2, python-gitlab ^4.4 must be added to pyproject.toml

### Test Pattern (follow existing test_test_planner.py / test_runbook_executor.py)

```python
def _make_step(pipeline_metadata=None, trust_level=3, **overrides):
    """Factory for PRGeneratorStep with mocked dependencies."""
    llm = MagicMock(spec=LlmClient)
    ctx = InvestigationContext(
        investigation_id="test-inv-001",
        namespace="default",
        condition="high_error_rate",
        service="payments",
        severity="high",
        trust_level=trust_level,
        confidence_threshold=0.9,
    )
    status = MagicMock(spec=InvestigationStatusUpdater)
    defaults = {
        "llm_client": llm,
        "context": ctx,
        "status_updater": status,
        "pipeline_metadata": pipeline_metadata or {},
    }
    defaults.update(overrides)
    step = PRGeneratorStep(**defaults)
    # Mock out RepositoryLookup to avoid K8s API calls in unit tests
    step._repository_lookup = MagicMock()
    return step, defaults
```

### Project Structure Notes

- New file: `investigator/beeper_investigator/remediation/git_provider.py`
- New file: `investigator/beeper_investigator/remediation/evidence_trail.py`
- New file: `investigator/beeper_investigator/remediation/pr_generator.py`
- New file: `investigator/beeper_investigator/k8s/repository.py`
- Modified: `investigator/beeper_investigator/remediation/__init__.py` (add exports)
- Modified: `investigator/beeper_investigator/k8s/__init__.py` (add exports)
- Modified: `investigator/beeper_investigator/agent.py` (add step 9)
- Modified: `investigator/pyproject.toml` (add PyGithub, python-gitlab)
- New test: `investigator/tests/test_git_provider.py`
- New test: `investigator/tests/test_repository_lookup.py`
- New test: `investigator/tests/test_evidence_trail.py`
- New test: `investigator/tests/test_pr_generator.py`
- New test: `investigator/tests/test_agent_pr_integration.py`

### Previous Story Intelligence

**From Story 4-3 (Advisory Test Plan Generation):**
- Established TestPlannerStep as step 8 — PRGeneratorStep is step 9 after it
- `_get_model_name()` pattern with "remediation" → "deep_rca" fallback — reuse exactly
- Test plan data in pipeline_metadata — PRGeneratorStep should read it for evidence trail
- Code review eliminated double `_get_model_name()` call — resolve model name once, pass to methods
- Code review added warning logging for non-dict entries — add defensive logging
- 580 passing tests, 12 pre-existing async failures

**From Story 4-2 (Human-Language Runbook Execution):**
- Established `remediation/` package — extend it with new files
- Trust gating pattern: TL1-2 advisory, TL3+ action — PRGeneratorStep uses TL3 threshold
- RunbookExecutorStep has `_get_model_name()` — reuse pattern, do NOT duplicate the method in a base class (keep it per-step as established)
- Code review found misleading test names — use precise names describing actual behavior

**From Story 4-1 (Repository CRD & Git Provider Integration):**
- Repository CRD fields: url, provider (github/gitlab), credentials_secret, branch_policy, coding_standards
- RepositoryProvider enum uses snake_case serialization
- BranchPolicy: base_branch, pr_branch_prefix, require_pr
- CodingStandards: language, linter, test_command
- RepositoryCondition: pending, connected, auth_error, not_found, error
- 4 pre-existing operator test failures (unrelated to Python story)
- Operator validates credential Secret existence — Python side reads actual token value

### Git Intelligence

Recent commits: `MAESTRO: 4-3 done`, `MAESTRO: implement story 4-3 (Advisory Test Plan Generation)`. Follow commit pattern: `MAESTRO: implement story 4-4 (Auto-PR Generation with Evidence Trail)`. Current test counts: operator 527 passed (4 pre-existing), investigator 580 passed (12 pre-existing), UI 1,388 passed.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 4, Story 4.4] — User story, acceptance criteria
- [Source: _bmad-output/planning-artifacts/architecture.md#Auto-Remediation Architecture] — Auto-PR flow: Investigator → Clone → Branch → Fix → Commit → PR
- [Source: _bmad-output/planning-artifacts/architecture.md#Trust System Architecture] — TL3 draft, TL4-5 ready-for-merge
- [Source: _bmad-output/planning-artifacts/architecture.md#Technology Stack] — PyGithub / python-gitlab for Git provider integration
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Map] — FR25: `investigator/remediation/pr_generator.py`, FR30: evidence metadata in PR body
- [Source: _bmad-output/planning-artifacts/architecture.md#Security] — NFR9: per-repo scoped tokens, never org-wide
- [Source: operator/src/crds/repository.rs] — Repository CRD spec, BranchPolicy, CodingStandards, RepositoryCondition
- [Source: investigator/beeper_investigator/steps/__init__.py] — InvestigationStep protocol, StepResult dataclass
- [Source: investigator/beeper_investigator/remediation/runbook_executor.py] — _get_model_name() pattern, trust gating pattern
- [Source: investigator/beeper_investigator/remediation/test_planner.py] — TestPlannerStep pattern, pipeline_metadata usage
- [Source: investigator/beeper_investigator/agent.py] — Agent lifecycle, _build_steps(), pipeline_metadata sharing
- [Source: investigator/beeper_investigator/k8s/status.py] — K8s API pattern, CustomObjectsApi, load_incluster_config() fallback
- [Source: investigator/beeper_investigator/context.py] — InvestigationContext with trust_level, confidence_threshold
- [Source: investigator/pyproject.toml] — Current dependencies, Poetry config
- [Source: _bmad-output/implementation-artifacts/4-3-advisory-test-plan-generation.md] — Previous story patterns and lessons

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- All 10 tasks implemented successfully
- 75 new tests across 5 test files (21 git_provider + 14 repository_lookup + 13 evidence_trail + 23 pr_generator + 4 agent_pr_integration)
- Total suite: 655 passed, 12 failed (all pre-existing async), 3 skipped
- Ruff clean — zero warnings
- Zero regressions in existing tests
- Lazy RepositoryLookup initialization to avoid K8s config in tests
- Updated step count assertions in runbook and testplan integration tests (8 → 9)

### File List

- `investigator/beeper_investigator/remediation/git_provider.py` (NEW) — Abstract GitProvider + GitHub/GitLab implementations + PRResult + factory
- `investigator/beeper_investigator/remediation/evidence_trail.py` (NEW) — EvidenceTrailFormatter for PR bodies and commit messages
- `investigator/beeper_investigator/remediation/pr_generator.py` (NEW) — PRGeneratorStep with trust gating, fix generation, PR creation
- `investigator/beeper_investigator/k8s/repository.py` (NEW) — RepositoryLookup + RepositoryInfo + CredentialError
- `investigator/beeper_investigator/remediation/__init__.py` (MODIFIED) — Added new exports
- `investigator/beeper_investigator/k8s/__init__.py` (MODIFIED) — Added new exports
- `investigator/beeper_investigator/agent.py` (MODIFIED) — Added PRGeneratorStep as step 9
- `investigator/pyproject.toml` (MODIFIED) — Added PyGithub ^2.2, python-gitlab ^4.4
- `investigator/tests/test_git_provider.py` (NEW) — 21 tests
- `investigator/tests/test_repository_lookup.py` (NEW) — 14 tests
- `investigator/tests/test_evidence_trail.py` (NEW) — 13 tests
- `investigator/tests/test_pr_generator.py` (NEW) — 23 tests
- `investigator/tests/test_agent_pr_integration.py` (NEW) — 4 tests
- `investigator/tests/test_agent_runbook_integration.py` (MODIFIED) — Step count 8 → 9
- `investigator/tests/test_agent_testplan_integration.py` (MODIFIED) — Step count 8 → 9
