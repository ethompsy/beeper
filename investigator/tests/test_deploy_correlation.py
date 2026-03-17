"""Tests for DeployCorrelationStep."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.repository import CredentialError, RepositoryInfo
from beeper_investigator.steps.deploy_correlation import (
    _NO_DEPLOY_SUMMARY,
    DEFAULT_LOOKBACK_MINUTES,
    DeployCorrelationStep,
    _classify_confidence,
    _format_time_gap,
)


def _make_context(
    *,
    service: str = "payments",
    namespace: str = "default",
) -> InvestigationContext:
    return InvestigationContext(
        investigation_id="inv-test-001",
        namespace=namespace,
        condition="High error rate on /checkout",
        service=service,
        severity="high",
    )


def _make_step(
    *,
    service: str = "payments",
    namespace: str = "default",
) -> DeployCorrelationStep:
    context = _make_context(service=service, namespace=namespace)
    return DeployCorrelationStep(
        llm_client=MagicMock(),
        context=context,
        status_updater=MagicMock(),
        pipeline_metadata={},
    )


class TestClassifyConfidence:
    """Test confidence classification based on time gap."""

    def test_strong_under_5_minutes(self):
        assert _classify_confidence(0) == "strong"
        assert _classify_confidence(60) == "strong"
        assert _classify_confidence(299) == "strong"

    def test_moderate_5_to_30_minutes(self):
        assert _classify_confidence(300) == "moderate"
        assert _classify_confidence(900) == "moderate"
        assert _classify_confidence(1799) == "moderate"

    def test_weak_30_to_60_minutes(self):
        assert _classify_confidence(1800) == "weak"
        assert _classify_confidence(3000) == "weak"
        assert _classify_confidence(3600) == "weak"


class TestFormatTimeGap:
    """Test human-readable time gap formatting."""

    def test_seconds_only(self):
        assert _format_time_gap(45) == "45 sec"

    def test_exact_minutes(self):
        assert _format_time_gap(120) == "2 min"
        assert _format_time_gap(60) == "1 min"

    def test_minutes_and_seconds(self):
        assert _format_time_gap(270) == "4 min 30 sec"
        assert _format_time_gap(90) == "1 min 30 sec"


class TestDeployCorrelationStep:
    """Test the DeployCorrelationStep pipeline step."""

    @patch("beeper_investigator.steps.deploy_correlation.RepositoryLookup")
    def test_no_repository_found(self, mock_lookup_cls):
        """When no repository is found, return fallback summary."""
        mock_lookup = MagicMock()
        mock_lookup.find_repository.return_value = None
        mock_lookup_cls.return_value = mock_lookup

        step = _make_step()
        result = step.execute()

        assert result.success is True
        assert result.data["deploy_correlation_attempted"] is True
        assert result.data["recent_deployments"] == []
        assert result.data["deploy_correlations"] == []
        assert result.data["deploy_summary"] == _NO_DEPLOY_SUMMARY

    @patch("beeper_investigator.steps.deploy_correlation.RepositoryLookup")
    def test_credential_error_returns_empty(self, mock_lookup_cls):
        """When credentials fail, return empty gracefully."""
        mock_lookup = MagicMock()
        mock_lookup.find_repository.return_value = RepositoryInfo(
            name="payments",
            url="https://github.com/org/payments",
            provider="github",
            credentials_secret="git-token",
        )
        mock_lookup.get_credentials.side_effect = CredentialError("Secret not found")
        mock_lookup_cls.return_value = mock_lookup

        step = _make_step()
        result = step.execute()

        assert result.success is True
        assert result.data["recent_deployments"] == []
        assert result.data["deploy_summary"] == _NO_DEPLOY_SUMMARY

    @patch("beeper_investigator.steps.deploy_correlation.RepositoryLookup")
    def test_no_recent_deploys_returns_fallback(self, mock_lookup_cls):
        """When repo exists but no recent commits, return fallback."""
        mock_lookup = MagicMock()
        mock_lookup.find_repository.return_value = RepositoryInfo(
            name="payments",
            url="https://github.com/org/payments",
            provider="github",
            credentials_secret="git-token",
        )
        mock_lookup.get_credentials.return_value = "fake-token"
        mock_lookup_cls.return_value = mock_lookup

        with patch(
            "beeper_investigator.steps.deploy_correlation.DeployCorrelationStep._fetch_github_commits"
        ) as mock_fetch:
            mock_fetch.return_value = []
            step = _make_step()
            result = step.execute()

        assert result.success is True
        assert result.data["deploy_summary"] == _NO_DEPLOY_SUMMARY

    @patch("beeper_investigator.steps.deploy_correlation.RepositoryLookup")
    def test_successful_strong_correlation(self, mock_lookup_cls):
        """Deploy within 5 minutes gets strong confidence."""
        mock_lookup = MagicMock()
        mock_lookup.find_repository.return_value = RepositoryInfo(
            name="payments",
            url="https://github.com/org/payments",
            provider="github",
            credentials_secret="git-token",
        )
        mock_lookup.get_credentials.return_value = "fake-token"
        mock_lookup_cls.return_value = mock_lookup

        now = datetime.now(timezone.utc)
        deploy_time = now - timedelta(minutes=2)

        with patch(
            "beeper_investigator.steps.deploy_correlation.DeployCorrelationStep._fetch_github_commits"
        ) as mock_fetch:
            mock_fetch.return_value = [
                {
                    "timestamp": deploy_time.isoformat(),
                    "commit_sha": "abc123def456",
                    "author": "alice@example.com",
                    "message": "Fix payment timeout",
                    "changed_files": ["src/payment.py"],
                }
            ]
            step = _make_step()
            result = step.execute()

        assert result.success is True
        assert len(result.data["deploy_correlations"]) == 1
        corr = result.data["deploy_correlations"][0]
        assert corr["confidence"] == "strong"
        assert corr["commit_sha"] == "abc123def456"
        assert corr["author"] == "alice@example.com"
        assert "abc123d" in result.data["deploy_summary"]
        assert "strong" in result.data["deploy_summary"]

    @patch("beeper_investigator.steps.deploy_correlation.RepositoryLookup")
    def test_moderate_correlation(self, mock_lookup_cls):
        """Deploy 10 minutes ago gets moderate confidence."""
        mock_lookup = MagicMock()
        mock_lookup.find_repository.return_value = RepositoryInfo(
            name="payments",
            url="https://github.com/org/payments",
            provider="github",
            credentials_secret="git-token",
        )
        mock_lookup.get_credentials.return_value = "fake-token"
        mock_lookup_cls.return_value = mock_lookup

        now = datetime.now(timezone.utc)
        deploy_time = now - timedelta(minutes=10)

        with patch(
            "beeper_investigator.steps.deploy_correlation.DeployCorrelationStep._fetch_github_commits"
        ) as mock_fetch:
            mock_fetch.return_value = [
                {
                    "timestamp": deploy_time.isoformat(),
                    "commit_sha": "def456789012",
                    "author": "bob@example.com",
                    "message": "Update config",
                    "changed_files": [],
                }
            ]
            step = _make_step()
            result = step.execute()

        corr = result.data["deploy_correlations"][0]
        assert corr["confidence"] == "moderate"

    @patch("beeper_investigator.steps.deploy_correlation.RepositoryLookup")
    def test_weak_correlation(self, mock_lookup_cls):
        """Deploy 45 minutes ago gets weak confidence."""
        mock_lookup = MagicMock()
        mock_lookup.find_repository.return_value = RepositoryInfo(
            name="payments",
            url="https://github.com/org/payments",
            provider="github",
            credentials_secret="git-token",
        )
        mock_lookup.get_credentials.return_value = "fake-token"
        mock_lookup_cls.return_value = mock_lookup

        now = datetime.now(timezone.utc)
        deploy_time = now - timedelta(minutes=45)

        with patch(
            "beeper_investigator.steps.deploy_correlation.DeployCorrelationStep._fetch_github_commits"
        ) as mock_fetch:
            mock_fetch.return_value = [
                {
                    "timestamp": deploy_time.isoformat(),
                    "commit_sha": "789012345678",
                    "author": "carol@example.com",
                    "message": "Refactor module",
                    "changed_files": [],
                }
            ]
            step = _make_step()
            result = step.execute()

        corr = result.data["deploy_correlations"][0]
        assert corr["confidence"] == "weak"

    @patch("beeper_investigator.steps.deploy_correlation.RepositoryLookup")
    def test_multiple_deploys_sorted_by_time_gap(self, mock_lookup_cls):
        """Multiple deployments are all correlated and sorted by time gap."""
        mock_lookup = MagicMock()
        mock_lookup.find_repository.return_value = RepositoryInfo(
            name="payments",
            url="https://github.com/org/payments",
            provider="github",
            credentials_secret="git-token",
        )
        mock_lookup.get_credentials.return_value = "fake-token"
        mock_lookup_cls.return_value = mock_lookup

        now = datetime.now(timezone.utc)

        with patch(
            "beeper_investigator.steps.deploy_correlation.DeployCorrelationStep._fetch_github_commits"
        ) as mock_fetch:
            mock_fetch.return_value = [
                {
                    "timestamp": (now - timedelta(minutes=30)).isoformat(),
                    "commit_sha": "aaa111222333",
                    "author": "alice@example.com",
                    "message": "Old deploy",
                    "changed_files": [],
                },
                {
                    "timestamp": (now - timedelta(minutes=3)).isoformat(),
                    "commit_sha": "bbb444555666",
                    "author": "bob@example.com",
                    "message": "Recent deploy",
                    "changed_files": [],
                },
            ]
            step = _make_step()
            result = step.execute()

        assert len(result.data["deploy_correlations"]) == 2
        # Closest deploy should be first
        assert result.data["deploy_correlations"][0]["commit_sha"] == "bbb444555666"
        assert result.data["deploy_correlations"][1]["commit_sha"] == "aaa111222333"

    @patch("beeper_investigator.steps.deploy_correlation.RepositoryLookup")
    def test_repository_lookup_init_failure(self, mock_lookup_cls):
        """RepositoryLookup init failure is handled gracefully."""
        mock_lookup_cls.side_effect = Exception("K8s not available")

        step = _make_step()
        result = step.execute()

        assert result.success is True
        assert result.data["recent_deployments"] == []
        assert result.data["deploy_summary"] == _NO_DEPLOY_SUMMARY

    @patch("beeper_investigator.steps.deploy_correlation.RepositoryLookup")
    def test_unsupported_provider(self, mock_lookup_cls):
        """Unsupported git provider returns empty."""
        mock_lookup = MagicMock()
        mock_lookup.find_repository.return_value = RepositoryInfo(
            name="payments",
            url="https://bitbucket.org/org/payments",
            provider="bitbucket",
            credentials_secret="git-token",
        )
        mock_lookup.get_credentials.return_value = "fake-token"
        mock_lookup_cls.return_value = mock_lookup

        step = _make_step()
        result = step.execute()

        assert result.success is True
        assert result.data["recent_deployments"] == []

    def test_step_name(self):
        """Step has correct name attribute."""
        step = _make_step()
        assert step.name == "Deploy Correlation"

    def test_default_lookback(self):
        """Default lookback window is 60 minutes."""
        assert DEFAULT_LOOKBACK_MINUTES == 60

    def test_calculate_correlations_empty_deployments(self):
        """Empty deployment list returns empty correlations."""
        step = _make_step()
        result = step._calculate_correlations([])
        assert result == []

    def test_format_deploy_summary_no_correlations(self):
        """No correlations returns the fallback message."""
        step = _make_step()
        result = step._format_deploy_summary([])
        assert result == _NO_DEPLOY_SUMMARY

    def test_format_deploy_summary_with_correlations(self):
        """Correlations produce human-readable summary."""
        step = _make_step()
        correlations = [
            {
                "commit_sha": "abc123def456",
                "author": "alice@example.com",
                "time_gap_seconds": 270,
                "confidence": "strong",
                "message": "Fix bug",
            }
        ]
        result = step._format_deploy_summary(correlations)
        assert "abc123d" in result
        assert "alice@example.com" in result
        assert "4 min 30 sec" in result
        assert "strong" in result
