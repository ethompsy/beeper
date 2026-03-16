"""Tests for k8s/repository.py — RepositoryLookup and credential handling."""

import base64
from unittest.mock import MagicMock, patch

import pytest

from beeper_investigator.k8s.repository import (
    CredentialError,
    RepositoryInfo,
    RepositoryLookup,
)


def _make_lookup():
    """Create a RepositoryLookup with mocked K8s clients."""
    with patch("beeper_investigator.k8s.repository.config"):
        lookup = RepositoryLookup()
    lookup._custom_api = MagicMock()
    lookup._core_api = MagicMock()
    return lookup


def _repo_item(
    name="payments-repo",
    url="https://github.com/org/payments",
    provider="github",
    condition="connected",
    credentials_secret="github-token",
    base_branch="main",
    pr_branch_prefix="beeper/",
):
    """Create a mock Repository CRD item."""
    return {
        "metadata": {"name": name, "namespace": "default"},
        "spec": {
            "url": url,
            "provider": provider,
            "credentials_secret": credentials_secret,
            "branch_policy": {
                "base_branch": base_branch,
                "pr_branch_prefix": pr_branch_prefix,
                "require_pr": True,
            },
            "coding_standards": {
                "language": "python",
                "linter": "ruff",
                "test_command": "pytest",
            },
        },
        "status": {
            "condition": condition,
            "last_checked": "2026-03-16T00:00:00Z",
        },
    }


# ── FindRepository ───────────────────────────────────────


class TestFindRepository:
    def test_repository_found_connected(self):
        lookup = _make_lookup()
        lookup._custom_api.list_namespaced_custom_object.return_value = {
            "items": [_repo_item(name="payments-repo")]
        }

        result = lookup.find_repository("payments", "default")

        assert result is not None
        assert isinstance(result, RepositoryInfo)
        assert result.name == "payments-repo"
        assert result.url == "https://github.com/org/payments"
        assert result.provider == "github"
        assert result.base_branch == "main"
        assert result.pr_branch_prefix == "beeper/"
        assert result.language == "python"
        assert result.linter == "ruff"

    def test_repository_skipped_auth_error(self):
        lookup = _make_lookup()
        lookup._custom_api.list_namespaced_custom_object.return_value = {
            "items": [_repo_item(name="payments-repo", condition="auth_error")]
        }

        result = lookup.find_repository("payments", "default")

        assert result is None

    def test_repository_skipped_not_found(self):
        lookup = _make_lookup()
        lookup._custom_api.list_namespaced_custom_object.return_value = {
            "items": [_repo_item(name="payments-repo", condition="not_found")]
        }

        result = lookup.find_repository("payments", "default")

        assert result is None

    def test_no_repository_found(self):
        lookup = _make_lookup()
        lookup._custom_api.list_namespaced_custom_object.return_value = {
            "items": []
        }

        result = lookup.find_repository("payments", "default")

        assert result is None

    def test_multiple_repos_first_connected_returned(self):
        lookup = _make_lookup()
        lookup._custom_api.list_namespaced_custom_object.return_value = {
            "items": [
                _repo_item(name="payments-old", condition="auth_error"),
                _repo_item(name="payments-new", condition="connected"),
            ]
        }

        result = lookup.find_repository("payments", "default")

        assert result is not None
        assert result.name == "payments-new"

    def test_service_matched_by_url(self):
        lookup = _make_lookup()
        lookup._custom_api.list_namespaced_custom_object.return_value = {
            "items": [_repo_item(name="repo-123", url="https://github.com/org/payments")]
        }

        result = lookup.find_repository("payments", "default")

        assert result is not None
        assert result.name == "repo-123"

    def test_no_match_for_unrelated_service(self):
        lookup = _make_lookup()
        lookup._custom_api.list_namespaced_custom_object.return_value = {
            "items": [_repo_item(name="orders-repo", url="https://github.com/org/orders")]
        }

        result = lookup.find_repository("payments", "default")

        assert result is None

    def test_api_exception_returns_none(self):
        lookup = _make_lookup()
        from kubernetes.client.rest import ApiException

        lookup._custom_api.list_namespaced_custom_object.side_effect = ApiException(
            status=403, reason="Forbidden"
        )

        result = lookup.find_repository("payments", "default")

        assert result is None

    def test_missing_branch_policy_uses_defaults(self):
        lookup = _make_lookup()
        item = _repo_item()
        item["spec"]["branch_policy"] = None
        lookup._custom_api.list_namespaced_custom_object.return_value = {
            "items": [item]
        }

        result = lookup.find_repository("payments", "default")

        assert result is not None
        assert result.base_branch == "main"
        assert result.pr_branch_prefix == "beeper/"

    def test_missing_coding_standards_uses_none(self):
        lookup = _make_lookup()
        item = _repo_item()
        item["spec"]["coding_standards"] = None
        lookup._custom_api.list_namespaced_custom_object.return_value = {
            "items": [item]
        }

        result = lookup.find_repository("payments", "default")

        assert result is not None
        assert result.language is None
        assert result.linter is None


# ── GetCredentials ───────────────────────────────────────


class TestGetCredentials:
    def test_token_decoded_correctly(self):
        lookup = _make_lookup()
        mock_secret = MagicMock()
        mock_secret.data = {"token": base64.b64encode(b"my-secret-token").decode()}
        lookup._core_api.read_namespaced_secret.return_value = mock_secret

        token = lookup.get_credentials("github-token", "default")

        assert token == "my-secret-token"

    def test_missing_secret_raises(self):
        lookup = _make_lookup()
        from kubernetes.client.rest import ApiException

        lookup._core_api.read_namespaced_secret.side_effect = ApiException(
            status=404, reason="Not Found"
        )

        with pytest.raises(CredentialError, match="not found"):
            lookup.get_credentials("missing-secret", "default")

    def test_missing_token_key_raises(self):
        lookup = _make_lookup()
        mock_secret = MagicMock()
        mock_secret.data = {"username": "user"}
        lookup._core_api.read_namespaced_secret.return_value = mock_secret

        with pytest.raises(CredentialError, match="does not contain a 'token' key"):
            lookup.get_credentials("github-token", "default")

    def test_empty_data_raises(self):
        lookup = _make_lookup()
        mock_secret = MagicMock()
        mock_secret.data = None
        lookup._core_api.read_namespaced_secret.return_value = mock_secret

        with pytest.raises(CredentialError, match="does not contain a 'token' key"):
            lookup.get_credentials("github-token", "default")
