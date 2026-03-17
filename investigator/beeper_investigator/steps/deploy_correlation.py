"""Deploy correlation investigation step.

Correlates anomalies with recent deployments by querying git providers
for recent commits and calculating temporal correlation (FR44).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.repository import CredentialError, RepositoryLookup
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.steps import StepResult

if TYPE_CHECKING:
    from beeper_investigator.llm.client import LlmClient

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_MINUTES = 60

# Confidence thresholds in seconds
_STRONG_THRESHOLD = 5 * 60  # <5 min
_MODERATE_THRESHOLD = 30 * 60  # 5-30 min
# Anything 30-60 min is weak; >60 min is outside lookback window

_NO_DEPLOY_SUMMARY = "No recent deployments found \u2014 likely not deploy-related"


def _classify_confidence(time_gap_seconds: int) -> str:
    """Classify deploy correlation confidence based on time gap."""
    if time_gap_seconds < _STRONG_THRESHOLD:
        return "strong"
    if time_gap_seconds < _MODERATE_THRESHOLD:
        return "moderate"
    return "weak"


def _format_time_gap(seconds: int) -> str:
    """Format a time gap in seconds to a human-readable string."""
    if seconds < 60:
        return f"{seconds} sec"
    minutes = seconds // 60
    remaining = seconds % 60
    if remaining == 0:
        return f"{minutes} min"
    return f"{minutes} min {remaining} sec"


class DeployCorrelationStep:
    """Correlate anomalies with recent deployments.

    Queries Repository CRDs to find the git provider for the affected
    service, fetches recent commits within a configurable lookback window,
    and calculates temporal correlation with the anomaly detection time.
    """

    name: str = "Deploy Correlation"

    def __init__(
        self,
        llm_client: LlmClient,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
        pipeline_metadata: dict[str, Any],
    ) -> None:
        self.llm_client = llm_client
        self.context = context
        self.status_updater = status_updater
        self.pipeline_metadata = pipeline_metadata

    def execute(self) -> StepResult:
        """Run the deploy correlation step."""
        self.status_updater.update_message(
            "Checking for recent deployments correlated with anomaly"
        )
        logger.info(
            "Starting deploy correlation for service=%s namespace=%s",
            self.context.service,
            self.context.namespace,
        )

        deployments = self._fetch_recent_deployments()
        correlations = self._calculate_correlations(deployments)
        summary = self._format_deploy_summary(correlations)

        deploy_count = len(deployments)
        correlation_count = len(correlations)

        logger.info(
            "Deploy correlation complete: %d deployments found, %d correlations",
            deploy_count,
            correlation_count,
        )

        return StepResult(
            success=True,
            summary=summary,
            data={
                "recent_deployments": deployments,
                "deploy_correlations": correlations,
                "deploy_summary": summary,
                "deploy_correlation_attempted": True,
            },
        )

    def _fetch_recent_deployments(self) -> list[dict[str, Any]]:
        """Fetch recent deployments from the git provider.

        Uses RepositoryLookup to find the Repository CRD and credentials,
        then queries the git provider for recent commits.

        Returns:
            List of deployment dicts with timestamp, commit_sha, author,
            message, and changed_files.
        """
        try:
            repo_lookup = RepositoryLookup()
        except Exception as exc:
            logger.warning("Failed to initialize RepositoryLookup: %s", exc)
            return []

        repo_info = repo_lookup.find_repository(
            self.context.service, self.context.namespace
        )
        if repo_info is None:
            logger.info(
                "No repository found for service %s in namespace %s",
                self.context.service,
                self.context.namespace,
            )
            return []

        try:
            token = repo_lookup.get_credentials(
                repo_info.credentials_secret, self.context.namespace
            )
        except CredentialError as exc:
            logger.warning("Failed to get git credentials: %s", exc)
            return []

        now = datetime.now(timezone.utc)
        since = now - timedelta(minutes=DEFAULT_LOOKBACK_MINUTES)

        if repo_info.provider == "github":
            return self._fetch_github_commits(repo_info.url, token, since)
        elif repo_info.provider == "gitlab":
            return self._fetch_gitlab_commits(repo_info.url, token, since)
        else:
            logger.warning("Unsupported git provider: %s", repo_info.provider)
            return []

    def _fetch_github_commits(
        self, repo_url: str, token: str, since: datetime
    ) -> list[dict[str, Any]]:
        """Fetch recent commits from GitHub."""
        try:
            from github import Github

            from beeper_investigator.remediation.git_provider import _parse_github_url

            owner, repo_name = _parse_github_url(repo_url)
            gh = Github(token)
            repo = gh.get_repo(f"{owner}/{repo_name}")
            commits = repo.get_commits(since=since)

            results: list[dict[str, Any]] = []
            for commit in commits:
                committed_at = commit.commit.committer.date
                if committed_at.tzinfo is None:
                    committed_at = committed_at.replace(tzinfo=timezone.utc)
                results.append({
                    "timestamp": committed_at.isoformat(),
                    "commit_sha": commit.sha,
                    "author": (
                        commit.commit.author.email
                        if commit.commit.author
                        else "unknown"
                    ),
                    "message": (commit.commit.message or "").split("\n")[0],
                    "changed_files": [f.filename for f in commit.files]
                    if commit.files
                    else [],
                })
            return results
        except Exception as exc:
            logger.warning("Failed to fetch GitHub commits: %s", exc)
            return []

    def _fetch_gitlab_commits(
        self, repo_url: str, token: str, since: datetime
    ) -> list[dict[str, Any]]:
        """Fetch recent commits from GitLab."""
        try:
            import gitlab

            from beeper_investigator.remediation.git_provider import _parse_gitlab_url

            base_url, project_path = _parse_gitlab_url(repo_url)
            gl = gitlab.Gitlab(base_url, private_token=token)
            project = gl.projects.get(project_path)
            commits = project.commits.list(since=since.isoformat())

            results: list[dict[str, Any]] = []
            for commit in commits:
                results.append({
                    "timestamp": commit.committed_date,
                    "commit_sha": commit.id,
                    "author": commit.author_email or "unknown",
                    "message": (commit.title or "").split("\n")[0],
                    "changed_files": [],
                })
            return results
        except Exception as exc:
            logger.warning("Failed to fetch GitLab commits: %s", exc)
            return []

    def _calculate_correlations(
        self, deployments: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Calculate temporal correlation between deployments and anomaly.

        For each deployment, calculates the time gap between the deploy
        timestamp and the anomaly detection time, and classifies the
        correlation confidence.

        Returns:
            List of correlation dicts sorted by time gap (closest first).
        """
        if not deployments:
            return []

        # Use current time as anomaly detection time approximation
        anomaly_time = datetime.now(timezone.utc)

        correlations: list[dict[str, Any]] = []
        for deploy in deployments:
            deploy_ts = deploy["timestamp"]
            try:
                if isinstance(deploy_ts, str):
                    deploy_dt = datetime.fromisoformat(deploy_ts.replace("Z", "+00:00"))
                else:
                    deploy_dt = deploy_ts
                if deploy_dt.tzinfo is None:
                    deploy_dt = deploy_dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError) as exc:
                logger.warning("Cannot parse deploy timestamp %r: %s", deploy_ts, exc)
                continue

            time_gap = int((anomaly_time - deploy_dt).total_seconds())
            if time_gap < 0:
                time_gap = 0  # Deploy is in the future (clock skew)

            confidence = _classify_confidence(time_gap)

            correlations.append({
                "deployment_timestamp": deploy_dt.isoformat(),
                "anomaly_detected_at": anomaly_time.isoformat(),
                "time_gap_seconds": time_gap,
                "confidence": confidence,
                "commit_sha": deploy["commit_sha"],
                "author": deploy["author"],
                "message": deploy["message"],
            })

        # Sort by time gap (closest deploy first)
        correlations.sort(key=lambda c: c["time_gap_seconds"])
        return correlations

    def _format_deploy_summary(
        self, correlations: list[dict[str, Any]]
    ) -> str:
        """Generate a human-readable deploy correlation summary."""
        if not correlations:
            return _NO_DEPLOY_SUMMARY

        parts: list[str] = []
        for corr in correlations:
            sha_short = corr["commit_sha"][:7]
            gap_str = _format_time_gap(corr["time_gap_seconds"])
            author = corr["author"]
            confidence = corr["confidence"]
            parts.append(
                f"Anomaly started {gap_str} after deploy {sha_short}"
                f" by {author} ({confidence} correlation)"
            )

        return "; ".join(parts)
