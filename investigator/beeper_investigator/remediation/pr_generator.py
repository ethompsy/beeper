"""Auto-PR generation step with evidence trail.

Creates pull requests with full investigation evidence when a
code-level fix is identified and the service trust level is TL3+.
Draft PRs are created at TL3; ready-for-merge PRs at TL4-5.
"""

import json
import logging
from typing import Any

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.repository import (
    CredentialError,
    RepositoryInfo,
    RepositoryLookup,
)
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.llm.client import LlmClient, ModelTier
from beeper_investigator.llm.response_parser import parse_json_response
from beeper_investigator.remediation.evidence_trail import EvidenceTrailFormatter
from beeper_investigator.remediation.git_provider import create_git_provider
from beeper_investigator.steps import StepResult

logger = logging.getLogger(__name__)

_FIX_GENERATION_SYSTEM_PROMPT = """\
You are a senior software developer. Your task is to propose \
a minimal, targeted code fix for a production issue based on \
the root cause analysis provided.

RULES:
- Generate the MINIMUM change needed to fix the root cause
- Follow the coding standards specified (language, linter)
- Output ONLY valid JSON with no extra text
- Each file path should be relative to the repository root
- File contents should be the COMPLETE file content after the fix

Output JSON format:
{
  "files": {
    "path/to/file.py": "complete file content after fix...",
    "path/to/another.py": "complete file content..."
  },
  "description": "Short description of what was changed",
  "change_summary": "Why this change fixes the root cause"
}"""

_FIX_GENERATION_USER_TEMPLATE = """## Investigation Context
- Service: {service}
- Condition: {condition}
- Severity: {severity}
- Namespace: {namespace}

## Root Cause Analysis
**Hypothesis:** {hypothesis}
**Confidence:** {confidence_level} ({confidence_percentage}%)

**Supporting Evidence:**
{evidence}

## Coding Standards
- Language: {language}
- Linter: {linter}

## Instructions
Propose a minimal code fix that addresses the root cause hypothesis. \
Generate complete file contents for each changed file."""


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
        self._repository_lookup: RepositoryLookup | None = None
        self._evidence_formatter = EvidenceTrailFormatter()

    def _get_repository_lookup(self) -> RepositoryLookup:
        """Lazy-initialize RepositoryLookup to avoid K8s config in tests."""
        if self._repository_lookup is None:
            self._repository_lookup = RepositoryLookup()
        return self._repository_lookup

    def execute(self) -> StepResult:
        """Generate auto-PR with evidence trail.

        Trust gating: skips at TL1-2, creates draft at TL3,
        creates ready-for-merge at TL4-5.
        """
        # Trust gate: TL3+ required
        if self.context.trust_level < 3:
            logger.info(
                "PR generation skipped — trust level %d below TL3",
                self.context.trust_level,
            )
            return StepResult(
                success=True,
                summary=(
                    f"PR generation skipped — trust level "
                    f"{self.context.trust_level} below TL3 threshold"
                ),
                data={
                    "pr_generated": False,
                    "skip_reason": "trust_level_insufficient",
                    "trust_level": self.context.trust_level,
                },
            )

        # Check for RCA hypothesis
        hypothesis = self.pipeline_metadata.get("root_cause_hypothesis")
        if not hypothesis:
            logger.info("PR generation skipped — no RCA hypothesis available")
            return StepResult(
                success=True,
                summary="PR generation skipped — no RCA hypothesis available",
                data={"pr_generated": False, "skip_reason": "no_hypothesis"},
            )

        # Look up repository
        self.status_updater.update_message("Looking up repository")
        lookup = self._get_repository_lookup()
        repo_info = lookup.find_repository(
            self.context.service, self.context.namespace
        )
        if repo_info is None:
            logger.info(
                "No registered repository found for service '%s'",
                self.context.service,
            )
            return StepResult(
                success=True,
                summary=(
                    f"No registered repository found for "
                    f"service '{self.context.service}'"
                ),
                data={"pr_generated": False, "skip_reason": "no_repository"},
            )

        # Get credentials
        try:
            token = lookup.get_credentials(
                repo_info.credentials_secret, self.context.namespace
            )
        except CredentialError as exc:
            logger.warning("Failed to get repository credentials: %s", exc)
            return StepResult(
                success=True,
                summary=f"PR generation failed — credential error: {exc}",
                data={"pr_generated": False, "skip_reason": "credential_error"},
            )

        # Generate fix via LLM
        self.status_updater.update_message("Generating code fix")
        model_name = self._get_model_name()
        fix_data = self._generate_fix(repo_info, model_name)
        if fix_data is None:
            return StepResult(
                success=True,
                summary="PR generation failed — could not generate fix",
                data={"pr_generated": False, "skip_reason": "fix_generation_failed"},
            )

        files = fix_data.get("files", {})
        fix_description = fix_data.get("description", "Auto-generated fix")

        if not files:
            return StepResult(
                success=True,
                summary="PR generation skipped — LLM produced no file changes",
                data={"pr_generated": False, "skip_reason": "no_files_generated"},
            )

        # Create PR
        self.status_updater.update_message("Creating pull request")
        try:
            pr_result = self._create_pr(
                repo_info, token, files, fix_description
            )
        except Exception as exc:
            logger.warning("Failed to create PR: %s", exc)
            return StepResult(
                success=True,
                summary=f"PR generation failed — git provider error: {exc}",
                data={"pr_generated": False, "skip_reason": "git_provider_error"},
            )

        logger.info("Auto-PR created: %s", pr_result.pr_url)
        return StepResult(
            success=True,
            summary=(
                f"Auto-PR created: {pr_result.pr_url} "
                f"({'draft' if pr_result.draft else 'ready'})"
            ),
            data={
                "pr_generated": True,
                "pr_url": pr_result.pr_url,
                "pr_number": pr_result.pr_number,
                "branch_name": pr_result.branch_name,
                "commit_sha": pr_result.commit_sha,
                "provider": pr_result.provider,
                "draft": pr_result.draft,
                "fix_description": fix_description,
                "files_changed": list(files.keys()),
                "evidence_trail_included": True,
                "trust_level": self.context.trust_level,
                "pr_model_tier": "remediation",
                "pr_model_used": model_name or "unknown",
            },
        )

    # ── Fix generation ─────────────────────────────────────

    def _generate_fix(
        self, repo_info: RepositoryInfo, model_name: str | None
    ) -> dict[str, Any] | None:
        """Use LLM to generate a code fix based on RCA hypothesis."""
        evidence_items = self.pipeline_metadata.get("supporting_evidence", [])
        evidence_text = "\n".join(f"- {e}" for e in evidence_items) if evidence_items else "N/A"

        user_message = _FIX_GENERATION_USER_TEMPLATE.format(
            service=self.context.service,
            condition=self.context.condition,
            severity=self.context.severity,
            namespace=self.context.namespace,
            hypothesis=self.pipeline_metadata.get("root_cause_hypothesis", ""),
            confidence_level=self.pipeline_metadata.get("confidence_level", "unknown"),
            confidence_percentage=self.pipeline_metadata.get("confidence_percentage", "N/A"),
            evidence=evidence_text,
            language=repo_info.language or "unknown",
            linter=repo_info.linter or "none",
        )

        messages = [
            {"role": "system", "content": _FIX_GENERATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        try:
            raw = self.llm_client.complete_sync(
                messages,
                max_tokens=4096,
                temperature=0.0,
                model=model_name,
            )
        except Exception as exc:
            logger.warning("LLM fix generation failed: %s", exc)
            return None

        return self._parse_fix_response(raw)

    def _parse_fix_response(self, raw: str) -> dict[str, Any] | None:
        """Parse LLM fix generation response as JSON."""
        try:
            parsed = parse_json_response(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Failed to parse fix response as JSON: %s", exc)
            return None

        if not isinstance(parsed, dict):
            logger.warning("Fix response is not a dict")
            return None

        if "files" not in parsed or not isinstance(parsed["files"], dict):
            logger.warning("Fix response missing 'files' dict")
            return None

        return parsed

    # ── PR creation ────────────────────────────────────────

    def _create_pr(
        self,
        repo_info: RepositoryInfo,
        token: str,
        files: dict[str, str],
        fix_description: str,
    ) -> Any:
        """Create a branch, commit files, and open a PR."""
        provider = create_git_provider(repo_info.provider, repo_info.url, token)

        branch_name = f"{repo_info.pr_branch_prefix}{self.context.investigation_id}"
        base_branch = repo_info.base_branch

        # Create branch
        provider.create_branch(base_branch, branch_name)

        # Commit files
        commit_message = self._evidence_formatter.format_commit_message(
            self.context, fix_description
        )
        provider.commit_files(branch_name, files, commit_message)

        # Create PR (draft at TL3, ready at TL4-5)
        draft = self.context.trust_level == 3
        pr_title = f"fix({self.context.service}): {fix_description[:60]}"
        pr_body = self._evidence_formatter.format_pr_body(
            self.context, self.pipeline_metadata, fix_description
        )

        return provider.create_pr(pr_title, pr_body, branch_name, base_branch, draft)

    # ── Helpers ─────────────────────────────────────────────

    def _get_model_name(self) -> str | None:
        """Get the model name for remediation tier, with fallback to deep_rca."""
        tier: ModelTier
        for tier in ("remediation", "deep_rca"):
            try:
                model = self.llm_client.select_model(tier)
                if model is not None:
                    return model
            except (KeyError, ValueError, AttributeError):
                logger.debug("Model tier '%s' not available, trying next", tier)
        return None
