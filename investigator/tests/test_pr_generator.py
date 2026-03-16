"""Tests for pr_generator.py — PRGeneratorStep trust gating, fix generation, PR creation."""

import json
from unittest.mock import MagicMock, patch

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.repository import CredentialError, RepositoryInfo
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.remediation.git_provider import PRResult
from beeper_investigator.remediation.pr_generator import PRGeneratorStep

_PROVIDER_PATH = (
    "beeper_investigator.remediation.pr_generator.create_git_provider"
)


def _make_context(trust_level=3, **overrides):
    defaults = {
        "investigation_id": "inv-abc123",
        "namespace": "default",
        "condition": "high_error_rate",
        "service": "payments",
        "severity": "high",
        "trust_level": trust_level,
        "confidence_threshold": 0.9,
    }
    defaults.update(overrides)
    return InvestigationContext(**defaults)


def _hypothesis_metadata():
    return {
        "root_cause_hypothesis": "Memory leak in connection pool",
        "confidence_level": "high",
        "confidence_percentage": 85,
        "supporting_evidence": ["Pod restarts correlate with memory growth"],
        "customer_impacting": True,
        "test_plan_generated": True,
        "verification_steps": [{"step_number": 1, "title": "Check mem", "action": "check"}],
    }


def _repo_info():
    return RepositoryInfo(
        name="payments-repo",
        url="https://github.com/org/payments",
        provider="github",
        credentials_secret="github-token",
        base_branch="main",
        pr_branch_prefix="beeper/",
        language="python",
        linter="ruff",
    )


def _llm_fix_response():
    return json.dumps({
        "files": {"src/pool.py": "# fixed content"},
        "description": "Increase pool max connections",
        "change_summary": "Raised max from 10 to 50",
    })


def _make_step(trust_level=3, pipeline_metadata=None, **overrides):
    """Factory for PRGeneratorStep with mocked dependencies."""
    llm = MagicMock(spec=LlmClient)
    ctx = _make_context(trust_level=trust_level)
    status = MagicMock(spec=InvestigationStatusUpdater)
    defaults = {
        "llm_client": llm,
        "context": ctx,
        "status_updater": status,
        "pipeline_metadata": pipeline_metadata or {},
    }
    defaults.update(overrides)

    step = PRGeneratorStep(**defaults)
    step._repository_lookup = MagicMock()
    return step, defaults


# ── Trust Gating ─────────────────────────────────────────


class TestTrustGating:
    def test_tl1_skips_with_reason(self):
        step, _ = _make_step(trust_level=1, pipeline_metadata=_hypothesis_metadata())

        result = step.execute()

        assert result.success is True
        assert result.data["pr_generated"] is False
        assert result.data["skip_reason"] == "trust_level_insufficient"
        assert "trust level 1" in result.summary

    def test_tl2_skips_with_reason(self):
        step, _ = _make_step(trust_level=2, pipeline_metadata=_hypothesis_metadata())

        result = step.execute()

        assert result.success is True
        assert result.data["pr_generated"] is False
        assert result.data["skip_reason"] == "trust_level_insufficient"

    def test_tl3_proceeds(self):
        step, deps = _make_step(trust_level=3, pipeline_metadata=_hypothesis_metadata())
        step._repository_lookup.find_repository.return_value = _repo_info()
        step._repository_lookup.get_credentials.return_value = "token"
        deps["llm_client"].complete_sync.return_value = _llm_fix_response()
        deps["llm_client"].select_model.return_value = "test-model"

        with patch(_PROVIDER_PATH) as mock_factory:
            mock_provider = MagicMock()
            mock_provider.commit_files.return_value = "sha123"
            mock_provider.create_pr.return_value = PRResult(
                pr_url="https://github.com/org/payments/pull/1",
                pr_number=1,
                branch_name="beeper/inv-abc123",
                commit_sha="sha123",
                provider="github",
                draft=True,
                created_at="2026-03-16T00:00:00Z",
            )
            mock_factory.return_value = mock_provider

            result = step.execute()

        assert result.data["pr_generated"] is True
        assert result.data["draft"] is True

    def test_tl4_creates_ready_pr(self):
        step, deps = _make_step(trust_level=4, pipeline_metadata=_hypothesis_metadata())
        step._repository_lookup.find_repository.return_value = _repo_info()
        step._repository_lookup.get_credentials.return_value = "token"
        deps["llm_client"].complete_sync.return_value = _llm_fix_response()
        deps["llm_client"].select_model.return_value = "test-model"

        with patch(_PROVIDER_PATH) as mock_factory:
            mock_provider = MagicMock()
            mock_provider.commit_files.return_value = "sha123"
            mock_provider.create_pr.return_value = PRResult(
                pr_url="https://github.com/org/payments/pull/2",
                pr_number=2,
                branch_name="beeper/inv-abc123",
                commit_sha="sha123",
                provider="github",
                draft=False,
                created_at="2026-03-16T00:00:00Z",
            )
            mock_factory.return_value = mock_provider

            result = step.execute()

        assert result.data["pr_generated"] is True
        assert result.data["draft"] is False

    def test_tl5_creates_ready_pr(self):
        step, deps = _make_step(trust_level=5, pipeline_metadata=_hypothesis_metadata())
        step._repository_lookup.find_repository.return_value = _repo_info()
        step._repository_lookup.get_credentials.return_value = "token"
        deps["llm_client"].complete_sync.return_value = _llm_fix_response()
        deps["llm_client"].select_model.return_value = "test-model"

        with patch(_PROVIDER_PATH) as mock_factory:
            mock_provider = MagicMock()
            mock_provider.commit_files.return_value = "sha123"
            mock_provider.create_pr.return_value = PRResult(
                pr_url="https://github.com/org/payments/pull/3",
                pr_number=3,
                branch_name="beeper/inv-abc123",
                commit_sha="sha123",
                provider="github",
                draft=False,
                created_at="2026-03-16T00:00:00Z",
            )
            mock_factory.return_value = mock_provider

            result = step.execute()

        assert result.data["pr_generated"] is True
        assert result.data["draft"] is False


# ── Repository Lookup ────────────────────────────────────


class TestRepositoryLookup:
    def test_no_repository_found_returns_skip(self):
        step, _ = _make_step(trust_level=3, pipeline_metadata=_hypothesis_metadata())
        step._repository_lookup.find_repository.return_value = None

        result = step.execute()

        assert result.success is True
        assert result.data["pr_generated"] is False
        assert result.data["skip_reason"] == "no_repository"

    def test_credential_error_returns_skip(self):
        step, _ = _make_step(trust_level=3, pipeline_metadata=_hypothesis_metadata())
        step._repository_lookup.find_repository.return_value = _repo_info()
        step._repository_lookup.get_credentials.side_effect = CredentialError("Secret missing")

        result = step.execute()

        assert result.success is True
        assert result.data["pr_generated"] is False
        assert result.data["skip_reason"] == "credential_error"


# ── No Hypothesis ────────────────────────────────────────


class TestNoHypothesis:
    def test_no_hypothesis_returns_skip(self):
        step, _ = _make_step(trust_level=3, pipeline_metadata={})

        result = step.execute()

        assert result.success is True
        assert result.data["pr_generated"] is False
        assert result.data["skip_reason"] == "no_hypothesis"


# ── Fix Generation ───────────────────────────────────────


class TestFixGeneration:
    def test_llm_response_parsed_correctly(self):
        step, deps = _make_step(trust_level=3, pipeline_metadata=_hypothesis_metadata())
        step._repository_lookup.find_repository.return_value = _repo_info()
        step._repository_lookup.get_credentials.return_value = "token"
        deps["llm_client"].complete_sync.return_value = _llm_fix_response()
        deps["llm_client"].select_model.return_value = "test-model"

        with patch(_PROVIDER_PATH) as mock_factory:
            mock_provider = MagicMock()
            mock_provider.commit_files.return_value = "sha123"
            mock_provider.create_pr.return_value = PRResult(
                pr_url="https://github.com/org/payments/pull/1",
                pr_number=1,
                branch_name="beeper/inv-abc123",
                commit_sha="sha123",
                provider="github",
                draft=True,
                created_at="2026-03-16T00:00:00Z",
            )
            mock_factory.return_value = mock_provider

            result = step.execute()

        assert result.data["files_changed"] == ["src/pool.py"]
        assert result.data["fix_description"] == "Increase pool max connections"

    def test_invalid_json_returns_failure(self):
        step, deps = _make_step(trust_level=3, pipeline_metadata=_hypothesis_metadata())
        step._repository_lookup.find_repository.return_value = _repo_info()
        step._repository_lookup.get_credentials.return_value = "token"
        deps["llm_client"].complete_sync.return_value = "not valid json"
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        assert result.success is True
        assert result.data["pr_generated"] is False
        assert result.data["skip_reason"] == "fix_generation_failed"

    def test_empty_files_returns_skip(self):
        step, deps = _make_step(trust_level=3, pipeline_metadata=_hypothesis_metadata())
        step._repository_lookup.find_repository.return_value = _repo_info()
        step._repository_lookup.get_credentials.return_value = "token"
        deps["llm_client"].complete_sync.return_value = json.dumps({
            "files": {},
            "description": "No changes needed",
            "change_summary": "",
        })
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        assert result.success is True
        assert result.data["pr_generated"] is False
        assert result.data["skip_reason"] == "no_files_generated"

    def test_llm_exception_returns_failure(self):
        step, deps = _make_step(trust_level=3, pipeline_metadata=_hypothesis_metadata())
        step._repository_lookup.find_repository.return_value = _repo_info()
        step._repository_lookup.get_credentials.return_value = "token"
        deps["llm_client"].complete_sync.side_effect = RuntimeError("LLM down")
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        assert result.success is True
        assert result.data["pr_generated"] is False
        assert result.data["skip_reason"] == "fix_generation_failed"

    def test_markdown_fenced_json_parsed(self):
        step, deps = _make_step(trust_level=3, pipeline_metadata=_hypothesis_metadata())
        step._repository_lookup.find_repository.return_value = _repo_info()
        step._repository_lookup.get_credentials.return_value = "token"
        fenced = "```json\n" + _llm_fix_response() + "\n```"
        deps["llm_client"].complete_sync.return_value = fenced
        deps["llm_client"].select_model.return_value = "test-model"

        with patch(_PROVIDER_PATH) as mock_factory:
            mock_provider = MagicMock()
            mock_provider.commit_files.return_value = "sha123"
            mock_provider.create_pr.return_value = PRResult(
                pr_url="https://github.com/org/payments/pull/1",
                pr_number=1,
                branch_name="beeper/inv-abc123",
                commit_sha="sha123",
                provider="github",
                draft=True,
                created_at="2026-03-16T00:00:00Z",
            )
            mock_factory.return_value = mock_provider

            result = step.execute()

        assert result.data["pr_generated"] is True


# ── PR Creation ──────────────────────────────────────────


class TestPRCreation:
    def test_tl3_creates_draft_pr(self):
        step, deps = _make_step(trust_level=3, pipeline_metadata=_hypothesis_metadata())
        step._repository_lookup.find_repository.return_value = _repo_info()
        step._repository_lookup.get_credentials.return_value = "token"
        deps["llm_client"].complete_sync.return_value = _llm_fix_response()
        deps["llm_client"].select_model.return_value = "test-model"

        with patch(_PROVIDER_PATH) as mock_factory:
            mock_provider = MagicMock()
            mock_provider.commit_files.return_value = "sha123"
            mock_provider.create_pr.return_value = PRResult(
                pr_url="https://github.com/org/payments/pull/1",
                pr_number=1,
                branch_name="beeper/inv-abc123",
                commit_sha="sha123",
                provider="github",
                draft=True,
                created_at="2026-03-16T00:00:00Z",
            )
            mock_factory.return_value = mock_provider

            step.execute()

        # Verify create_pr called with draft=True
        mock_provider.create_pr.assert_called_once()
        call_args = mock_provider.create_pr.call_args[0]
        assert call_args[4] is True  # 5th positional arg is draft

    def test_pr_metadata_in_result(self):
        step, deps = _make_step(trust_level=3, pipeline_metadata=_hypothesis_metadata())
        step._repository_lookup.find_repository.return_value = _repo_info()
        step._repository_lookup.get_credentials.return_value = "token"
        deps["llm_client"].complete_sync.return_value = _llm_fix_response()
        deps["llm_client"].select_model.return_value = "test-model"

        with patch(_PROVIDER_PATH) as mock_factory:
            mock_provider = MagicMock()
            mock_provider.commit_files.return_value = "sha123"
            mock_provider.create_pr.return_value = PRResult(
                pr_url="https://github.com/org/payments/pull/42",
                pr_number=42,
                branch_name="beeper/inv-abc123",
                commit_sha="sha123",
                provider="github",
                draft=True,
                created_at="2026-03-16T00:00:00Z",
            )
            mock_factory.return_value = mock_provider

            result = step.execute()

        assert result.data["pr_url"] == "https://github.com/org/payments/pull/42"
        assert result.data["pr_number"] == 42
        assert result.data["branch_name"] == "beeper/inv-abc123"
        assert result.data["commit_sha"] == "sha123"
        assert result.data["provider"] == "github"
        assert result.data["evidence_trail_included"] is True
        assert result.data["trust_level"] == 3

    def test_git_provider_error_returns_gracefully(self):
        step, deps = _make_step(trust_level=3, pipeline_metadata=_hypothesis_metadata())
        step._repository_lookup.find_repository.return_value = _repo_info()
        step._repository_lookup.get_credentials.return_value = "token"
        deps["llm_client"].complete_sync.return_value = _llm_fix_response()
        deps["llm_client"].select_model.return_value = "test-model"

        with patch(_PROVIDER_PATH) as mock_factory:
            mock_factory.side_effect = RuntimeError("API error")

            result = step.execute()

        assert result.success is True
        assert result.data["pr_generated"] is False
        assert result.data["skip_reason"] == "git_provider_error"


# ── Evidence Trail ───────────────────────────────────────


class TestEvidenceTrail:
    def test_pr_body_includes_investigation_link(self):
        step, deps = _make_step(trust_level=3, pipeline_metadata=_hypothesis_metadata())
        step._repository_lookup.find_repository.return_value = _repo_info()
        step._repository_lookup.get_credentials.return_value = "token"
        deps["llm_client"].complete_sync.return_value = _llm_fix_response()
        deps["llm_client"].select_model.return_value = "test-model"

        with patch(_PROVIDER_PATH) as mock_factory:
            mock_provider = MagicMock()
            mock_provider.commit_files.return_value = "sha123"
            mock_provider.create_pr.return_value = PRResult(
                pr_url="https://github.com/org/payments/pull/1",
                pr_number=1,
                branch_name="beeper/inv-abc123",
                commit_sha="sha123",
                provider="github",
                draft=True,
                created_at="2026-03-16T00:00:00Z",
            )
            mock_factory.return_value = mock_provider

            step.execute()

        # Verify PR body contains investigation evidence
        call_args = mock_provider.create_pr.call_args[0]
        pr_body = call_args[1]  # second positional arg is body
        assert "inv-abc123" in pr_body
        assert "Memory leak in connection pool" in pr_body
        assert "Audit Trail" in pr_body


# ── Pipeline Metadata ────────────────────────────────────


class TestPipelineMetadata:
    def test_pr_metadata_stored_for_downstream(self):
        step, deps = _make_step(trust_level=3, pipeline_metadata=_hypothesis_metadata())
        step._repository_lookup.find_repository.return_value = _repo_info()
        step._repository_lookup.get_credentials.return_value = "token"
        deps["llm_client"].complete_sync.return_value = _llm_fix_response()
        deps["llm_client"].select_model.return_value = "test-model"

        with patch(_PROVIDER_PATH) as mock_factory:
            mock_provider = MagicMock()
            mock_provider.commit_files.return_value = "sha123"
            mock_provider.create_pr.return_value = PRResult(
                pr_url="https://github.com/org/payments/pull/1",
                pr_number=1,
                branch_name="beeper/inv-abc123",
                commit_sha="sha123",
                provider="github",
                draft=True,
                created_at="2026-03-16T00:00:00Z",
            )
            mock_factory.return_value = mock_provider

            result = step.execute()

        # These fields are available for downstream steps (e.g., Documentation, Qdrant persistence)
        assert "pr_url" in result.data
        assert "pr_number" in result.data
        assert "branch_name" in result.data
        assert "commit_sha" in result.data
        assert "provider" in result.data

    def test_model_tier_in_result(self):
        step, deps = _make_step(trust_level=3, pipeline_metadata=_hypothesis_metadata())
        step._repository_lookup.find_repository.return_value = _repo_info()
        step._repository_lookup.get_credentials.return_value = "token"
        deps["llm_client"].complete_sync.return_value = _llm_fix_response()
        deps["llm_client"].select_model.return_value = "test-model"

        with patch(_PROVIDER_PATH) as mock_factory:
            mock_provider = MagicMock()
            mock_provider.commit_files.return_value = "sha123"
            mock_provider.create_pr.return_value = PRResult(
                pr_url="https://github.com/org/payments/pull/1",
                pr_number=1,
                branch_name="beeper/inv-abc123",
                commit_sha="sha123",
                provider="github",
                draft=True,
                created_at="2026-03-16T00:00:00Z",
            )
            mock_factory.return_value = mock_provider

            result = step.execute()

        assert result.data["pr_model_tier"] == "remediation"
        assert result.data["pr_model_used"] == "test-model"
