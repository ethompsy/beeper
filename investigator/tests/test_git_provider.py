"""Tests for git_provider module — GitHubProvider, GitLabProvider, factory."""

from unittest.mock import MagicMock, patch

import pytest

from beeper_investigator.remediation.git_provider import (
    GitHubProvider,
    GitLabProvider,
    PRResult,
    _parse_github_url,
    _parse_gitlab_url,
    create_git_provider,
)

# ── URL parsing ──────────────────────────────────────────


class TestParseGitHubURL:
    def test_standard_url(self):
        owner, repo = _parse_github_url("https://github.com/org/service")
        assert owner == "org"
        assert repo == "service"

    def test_url_with_git_suffix(self):
        owner, repo = _parse_github_url("https://github.com/org/service.git")
        assert owner == "org"
        assert repo == "service"

    def test_url_with_trailing_slash(self):
        owner, repo = _parse_github_url("https://github.com/org/service/")
        assert owner == "org"
        assert repo == "service"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Cannot parse GitHub URL"):
            _parse_github_url("https://gitlab.com/group/project")

    def test_no_repo_raises(self):
        with pytest.raises(ValueError, match="Cannot parse GitHub URL"):
            _parse_github_url("https://github.com/org")


class TestParseGitLabURL:
    def test_standard_url(self):
        base, path = _parse_gitlab_url("https://gitlab.com/group/project")
        assert base == "https://gitlab.com"
        assert path == "group/project"

    def test_subgroup_url(self):
        base, path = _parse_gitlab_url("https://gitlab.com/group/sub/project")
        assert base == "https://gitlab.com"
        assert path == "group/sub/project"

    def test_self_hosted(self):
        base, path = _parse_gitlab_url("https://git.example.com/team/repo")
        assert base == "https://git.example.com"
        assert path == "team/repo"

    def test_url_with_git_suffix(self):
        base, path = _parse_gitlab_url("https://gitlab.com/group/project.git")
        assert base == "https://gitlab.com"
        assert path == "group/project"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Cannot parse GitLab URL"):
            _parse_gitlab_url("not-a-url")


# ── GitHubProvider ───────────────────────────────────────


class TestGitHubProvider:
    def _make_provider(self):
        """Create a GitHubProvider with mocked internals (bypass __init__)."""
        mock_gh = MagicMock()
        mock_repo = MagicMock()
        mock_gh.get_repo.return_value = mock_repo
        provider = GitHubProvider.__new__(GitHubProvider)
        provider._owner = "org"
        provider._repo_name = "service"
        provider._gh = mock_gh
        provider._repo = mock_repo
        return provider, mock_repo

    def test_create_branch(self):
        provider, mock_repo = self._make_provider()
        mock_branch = MagicMock()
        mock_branch.commit.sha = "abc123"
        mock_repo.get_branch.return_value = mock_branch

        result = provider.create_branch("main", "beeper/fix-1")

        assert result is True
        mock_repo.create_git_ref.assert_called_once_with(
            ref="refs/heads/beeper/fix-1", sha="abc123"
        )

    def test_commit_files_creates_new(self):
        provider, mock_repo = self._make_provider()
        mock_repo.get_contents.side_effect = Exception("not found")
        mock_repo.create_file.return_value = {"commit": MagicMock(sha="def456")}

        sha = provider.commit_files("beeper/fix-1", {"src/app.py": "content"}, "fix")

        assert sha == "def456"
        mock_repo.create_file.assert_called_once()

    def test_commit_files_updates_existing(self):
        provider, mock_repo = self._make_provider()
        existing = MagicMock()
        existing.sha = "old-sha"
        mock_repo.get_contents.return_value = existing
        mock_repo.update_file.return_value = {"commit": MagicMock(sha="ghi789")}

        sha = provider.commit_files("beeper/fix-1", {"src/app.py": "content"}, "fix")

        assert sha == "ghi789"
        mock_repo.update_file.assert_called_once()

    def test_create_pr_draft(self):
        provider, mock_repo = self._make_provider()
        mock_pr = MagicMock()
        mock_pr.html_url = "https://github.com/org/service/pull/42"
        mock_pr.number = 42
        mock_pr.head.sha = "abc123"
        mock_repo.create_pull.return_value = mock_pr

        result = provider.create_pr("fix", "body", "beeper/fix", "main", draft=True)

        assert isinstance(result, PRResult)
        assert result.pr_url == "https://github.com/org/service/pull/42"
        assert result.pr_number == 42
        assert result.draft is True
        assert result.provider == "github"
        mock_repo.create_pull.assert_called_once_with(
            title="fix", body="body", head="beeper/fix", base="main", draft=True
        )

    def test_create_pr_ready(self):
        provider, mock_repo = self._make_provider()
        mock_pr = MagicMock()
        mock_pr.html_url = "https://github.com/org/service/pull/43"
        mock_pr.number = 43
        mock_pr.head.sha = "abc123"
        mock_repo.create_pull.return_value = mock_pr

        result = provider.create_pr("fix", "body", "beeper/fix", "main", draft=False)

        assert result.draft is False

    def test_get_default_branch(self):
        provider, mock_repo = self._make_provider()
        mock_repo.default_branch = "main"

        assert provider.get_default_branch() == "main"


# ── GitLabProvider ───────────────────────────────────────


class TestGitLabProvider:
    def _make_provider(self):
        provider = GitLabProvider.__new__(GitLabProvider)
        provider._base_url = "https://gitlab.com"
        provider._project_path = "group/project"
        mock_gl = MagicMock()
        mock_project = MagicMock()
        provider._gl = mock_gl
        provider._project = mock_project
        return provider, mock_project

    def test_create_branch(self):
        provider, mock_project = self._make_provider()

        result = provider.create_branch("main", "beeper/fix-1")

        assert result is True
        mock_project.branches.create.assert_called_once_with(
            {"branch": "beeper/fix-1", "ref": "main"}
        )

    def test_commit_files(self):
        provider, mock_project = self._make_provider()
        mock_project.files.get.side_effect = Exception("not found")
        mock_commit = MagicMock()
        mock_commit.id = "abc123"
        mock_project.commits.create.return_value = mock_commit

        sha = provider.commit_files("beeper/fix-1", {"src/app.py": "content"}, "fix")

        assert sha == "abc123"
        mock_project.commits.create.assert_called_once()

    def test_commit_files_update_existing(self):
        provider, mock_project = self._make_provider()
        mock_project.files.get.return_value = MagicMock()
        mock_commit = MagicMock()
        mock_commit.id = "def456"
        mock_project.commits.create.return_value = mock_commit

        sha = provider.commit_files("beeper/fix-1", {"src/app.py": "content"}, "fix")

        assert sha == "def456"
        # Verify action type is "update" for existing files
        call_args = mock_project.commits.create.call_args[0][0]
        assert call_args["actions"][0]["action"] == "update"

    def test_create_pr_draft(self):
        provider, mock_project = self._make_provider()
        mock_mr = MagicMock()
        mock_mr.web_url = "https://gitlab.com/group/project/-/merge_requests/10"
        mock_mr.iid = 10
        mock_mr.sha = "abc123"
        mock_project.mergerequests.create.return_value = mock_mr

        result = provider.create_pr("fix", "body", "beeper/fix", "main", draft=True)

        assert isinstance(result, PRResult)
        assert result.pr_number == 10
        assert result.draft is True
        assert result.provider == "gitlab"
        # Draft MRs get "Draft: " prefix in title
        call_args = mock_project.mergerequests.create.call_args[0][0]
        assert call_args["title"].startswith("Draft: ")

    def test_create_pr_ready(self):
        provider, mock_project = self._make_provider()
        mock_mr = MagicMock()
        mock_mr.web_url = "https://gitlab.com/group/project/-/merge_requests/11"
        mock_mr.iid = 11
        mock_mr.sha = "abc123"
        mock_project.mergerequests.create.return_value = mock_mr

        result = provider.create_pr("fix", "body", "beeper/fix", "main", draft=False)

        assert result.draft is False
        call_args = mock_project.mergerequests.create.call_args[0][0]
        assert not call_args["title"].startswith("Draft: ")

    def test_get_default_branch(self):
        provider, mock_project = self._make_provider()
        mock_project.default_branch = "develop"

        assert provider.get_default_branch() == "develop"


# ── Factory ──────────────────────────────────────────────


class TestProviderFactory:
    @patch("beeper_investigator.remediation.git_provider.GitHubProvider")
    def test_github_provider(self, mock_cls):
        mock_cls.return_value = MagicMock()
        result = create_git_provider("github", "https://github.com/org/repo", "token")
        mock_cls.assert_called_once_with("https://github.com/org/repo", "token")
        assert result is not None

    @patch("beeper_investigator.remediation.git_provider.GitLabProvider")
    def test_gitlab_provider(self, mock_cls):
        mock_cls.return_value = MagicMock()
        result = create_git_provider("gitlab", "https://gitlab.com/group/repo", "token")
        mock_cls.assert_called_once_with("https://gitlab.com/group/repo", "token")
        assert result is not None

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown git provider type"):
            create_git_provider("bitbucket", "https://bitbucket.org/org/repo", "token")
