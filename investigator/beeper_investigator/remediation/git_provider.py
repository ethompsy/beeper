"""Git provider abstraction for auto-PR generation.

Provides a unified interface for creating branches, committing files,
and opening pull requests across GitHub and GitLab providers.
"""

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PRResult:
    """Result of a pull request creation."""

    pr_url: str
    pr_number: int
    branch_name: str
    commit_sha: str
    provider: str
    draft: bool
    created_at: str


class GitProvider(ABC):
    """Abstract base class for git provider integrations."""

    @abstractmethod
    def create_branch(self, base_branch: str, new_branch: str) -> bool:
        """Create a new branch from base.

        Args:
            base_branch: Branch to create from.
            new_branch: Name for the new branch.

        Returns:
            True if branch created successfully.
        """

    @abstractmethod
    def commit_files(
        self, branch: str, files: dict[str, str], message: str
    ) -> str:
        """Commit files to a branch.

        Args:
            branch: Target branch name.
            files: Mapping of file paths to contents.
            message: Commit message.

        Returns:
            Commit SHA.
        """

    @abstractmethod
    def create_pr(
        self,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
        draft: bool,
    ) -> PRResult:
        """Create a pull request.

        Args:
            title: PR title.
            body: PR description body.
            head_branch: Source branch.
            base_branch: Target branch.
            draft: Whether to create as draft PR.

        Returns:
            PRResult with URL, number, and metadata.
        """

    @abstractmethod
    def get_default_branch(self) -> str:
        """Get the repository's default branch name.

        Returns:
            Default branch name (e.g., "main").
        """


def _parse_github_url(url: str) -> tuple[str, str]:
    """Extract owner and repo from a GitHub URL.

    Supports:
        https://github.com/owner/repo
        https://github.com/owner/repo.git

    Returns:
        Tuple of (owner, repo).

    Raises:
        ValueError: If URL cannot be parsed.
    """
    match = re.match(r"https?://github\.com/([^/]+)/([^/.]+?)(?:\.git)?/?$", url)
    if not match:
        raise ValueError(f"Cannot parse GitHub URL: {url}")
    return match.group(1), match.group(2)


def _parse_gitlab_url(url: str) -> tuple[str, str]:
    """Extract the GitLab instance base URL and project path.

    Supports:
        https://gitlab.com/group/project
        https://gitlab.com/group/subgroup/project.git
        https://self-hosted.example.com/group/project

    Returns:
        Tuple of (base_url, project_path).

    Raises:
        ValueError: If URL cannot be parsed.
    """
    match = re.match(r"(https?://[^/]+)/(.+?)(?:\.git)?/?$", url)
    if not match:
        raise ValueError(f"Cannot parse GitLab URL: {url}")
    return match.group(1), match.group(2)


class GitHubProvider(GitProvider):
    """GitHub provider using PyGithub."""

    def __init__(self, repo_url: str, token: str) -> None:
        from github import Github  # type: ignore[import-untyped]

        self._owner, self._repo_name = _parse_github_url(repo_url)
        self._gh = Github(token)
        self._repo = self._gh.get_repo(f"{self._owner}/{self._repo_name}")
        logger.info("GitHubProvider initialized for %s/%s", self._owner, self._repo_name)

    def create_branch(self, base_branch: str, new_branch: str) -> bool:
        base_ref = self._repo.get_branch(base_branch)
        self._repo.create_git_ref(
            ref=f"refs/heads/{new_branch}",
            sha=base_ref.commit.sha,
        )
        logger.info("Created branch %s from %s", new_branch, base_branch)
        return True

    def commit_files(
        self, branch: str, files: dict[str, str], message: str
    ) -> str:
        last_sha = ""
        for filepath, content in files.items():
            try:
                existing = self._repo.get_contents(filepath, ref=branch)
                result = self._repo.update_file(
                    filepath, message, content, existing.sha, branch=branch  # type: ignore[union-attr]
                )
            except Exception:
                result = self._repo.create_file(filepath, message, content, branch=branch)
            last_sha = result["commit"].sha
        logger.info("Committed %d file(s) to %s", len(files), branch)
        return last_sha

    def create_pr(
        self,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
        draft: bool,
    ) -> PRResult:
        pr = self._repo.create_pull(
            title=title,
            body=body,
            head=head_branch,
            base=base_branch,
            draft=draft,
        )
        logger.info("Created PR #%d: %s", pr.number, pr.html_url)
        return PRResult(
            pr_url=pr.html_url,
            pr_number=pr.number,
            branch_name=head_branch,
            commit_sha=pr.head.sha,
            provider="github",
            draft=draft,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def get_default_branch(self) -> str:
        return self._repo.default_branch


class GitLabProvider(GitProvider):
    """GitLab provider using python-gitlab."""

    def __init__(self, repo_url: str, token: str) -> None:
        import gitlab  # type: ignore[import-untyped]

        self._base_url, self._project_path = _parse_gitlab_url(repo_url)
        self._gl = gitlab.Gitlab(self._base_url, private_token=token)
        self._project = self._gl.projects.get(self._project_path)
        logger.info("GitLabProvider initialized for %s", self._project_path)

    def create_branch(self, base_branch: str, new_branch: str) -> bool:
        self._project.branches.create({"branch": new_branch, "ref": base_branch})
        logger.info("Created branch %s from %s", new_branch, base_branch)
        return True

    def commit_files(
        self, branch: str, files: dict[str, str], message: str
    ) -> str:
        actions: list[dict[str, Any]] = []
        for filepath, content in files.items():
            try:
                self._project.files.get(filepath, ref=branch)
                action_type = "update"
            except Exception:
                action_type = "create"
            actions.append({
                "action": action_type,
                "file_path": filepath,
                "content": content,
            })
        commit = self._project.commits.create({
            "branch": branch,
            "commit_message": message,
            "actions": actions,
        })
        logger.info("Committed %d file(s) to %s", len(files), branch)
        return commit.id

    def create_pr(
        self,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
        draft: bool,
    ) -> PRResult:
        mr_data: dict[str, Any] = {
            "source_branch": head_branch,
            "target_branch": base_branch,
            "title": f"Draft: {title}" if draft else title,
            "description": body,
        }
        mr = self._project.mergerequests.create(mr_data)
        mr_url = mr.web_url
        logger.info("Created MR !%d: %s", mr.iid, mr_url)
        return PRResult(
            pr_url=mr_url,
            pr_number=mr.iid,
            branch_name=head_branch,
            commit_sha=mr.sha or "",
            provider="gitlab",
            draft=draft,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def get_default_branch(self) -> str:
        return self._project.default_branch


def create_git_provider(provider_type: str, repo_url: str, token: str) -> GitProvider:
    """Factory function to create a GitProvider instance.

    Args:
        provider_type: "github" or "gitlab".
        repo_url: Repository URL.
        token: Authentication token.

    Returns:
        Configured GitProvider instance.

    Raises:
        ValueError: If provider_type is not recognized.
    """
    if provider_type == "github":
        return GitHubProvider(repo_url, token)
    elif provider_type == "gitlab":
        return GitLabProvider(repo_url, token)
    else:
        raise ValueError(f"Unknown git provider type: {provider_type}")
