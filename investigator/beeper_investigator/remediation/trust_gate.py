"""Trust-gated remediation actions.

Post-hoc trust gate evaluation step that scans pipeline_metadata for all
remediation actions taken by prior steps, records comprehensive trust gate
decisions, registers rollback paths for autonomous actions at TL4-5, and
adds trust gate decisions to the evidence trail.

Individual steps (RunbookExecutor, SandboxExecutor, MetricVerifier,
PRGenerator) already implement their own trust gating — this step does
NOT replace those gates. It reviews, validates, and creates the evidence
record.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.steps import StepResult

logger = logging.getLogger(__name__)


@dataclass
class TrustGateDecision:
    """Result of evaluating a single action against trust configuration."""

    allowed: bool
    action_type: str  # "executed" | "advisory" | "requires_approval"
    trust_level: int
    confidence: float | None
    confidence_threshold: float
    reason: str
    advisory_message: str | None
    rollback_registered: bool
    action_name: str = ""
    action_category: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for pipeline_metadata storage."""
        return {
            "allowed": self.allowed,
            "action_type": self.action_type,
            "trust_level": self.trust_level,
            "confidence": self.confidence,
            "confidence_threshold": self.confidence_threshold,
            "reason": self.reason,
            "advisory_message": self.advisory_message,
            "rollback_registered": self.rollback_registered,
            "action_name": self.action_name,
            "action_category": self.action_category,
        }


@dataclass
class TrustGateSummary:
    """Aggregated summary of all trust gate decisions in a pipeline run."""

    total_actions: int
    executed: int
    advisory: int
    requires_approval: int
    rollback_paths: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)


class TrustGateEvaluator:
    """Evaluates actions against the configured trust level and confidence."""

    def __init__(
        self,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
    ) -> None:
        self.context = context
        self.status_updater = status_updater
        self._decisions: list[TrustGateDecision] = []
        self._rollback_paths: list[dict[str, Any]] = []

    def evaluate(
        self,
        action_name: str,
        action_category: str,
        confidence: float | None = None,
    ) -> TrustGateDecision:
        """Evaluate whether an action is permitted under current trust config.

        Args:
            action_name: Human-readable name of the action.
            action_category: One of "read_only", "cluster_mutation",
                "code_change", "notification".
            confidence: Confidence score (0.0-1.0), or None.

        Returns:
            TrustGateDecision with evaluation result.
        """
        effective_confidence = confidence if confidence is not None else 0.0
        tl = self.context.trust_level
        threshold = self.context.confidence_threshold

        _VALID_CATEGORIES = ("read_only", "cluster_mutation", "code_change", "notification")
        if action_category not in _VALID_CATEGORIES:
            logger.warning(
                "Unrecognized action_category '%s' for action '%s'; "
                "treating as gated action",
                action_category,
                action_name,
            )

        # Read-only and notification actions always allowed
        if action_category in ("read_only", "notification"):
            decision = TrustGateDecision(
                allowed=True,
                action_type="executed",
                trust_level=tl,
                confidence=confidence,
                confidence_threshold=threshold,
                reason="Always permitted",
                advisory_message=None,
                rollback_registered=False,
                action_name=action_name,
                action_category=action_category,
            )
            self._decisions.append(decision)
            return decision

        # TL1-2: advisory only for mutations and code changes
        if tl <= 2:
            decision = TrustGateDecision(
                allowed=False,
                action_type="advisory",
                trust_level=tl,
                confidence=confidence,
                confidence_threshold=threshold,
                reason=f"Trust level {tl} — advisory only",
                advisory_message=self._build_advisory_message(
                    action_name, action_category
                ),
                rollback_registered=False,
                action_name=action_name,
                action_category=action_category,
            )
            self._decisions.append(decision)
            return decision

        # TL3-5: confidence gate
        if effective_confidence < threshold:
            decision = TrustGateDecision(
                allowed=False,
                action_type="requires_approval",
                trust_level=tl,
                confidence=confidence,
                confidence_threshold=threshold,
                reason=(
                    f"Confidence {effective_confidence:.2f} below "
                    f"threshold {threshold:.2f} — requires manual approval"
                ),
                advisory_message=None,
                rollback_registered=False,
                action_name=action_name,
                action_category=action_category,
            )
            self._decisions.append(decision)
            return decision

        # TL3-5 with confidence above threshold: allowed
        decision = TrustGateDecision(
            allowed=True,
            action_type="executed",
            trust_level=tl,
            confidence=confidence,
            confidence_threshold=threshold,
            reason=(
                f"Trust level {tl}, confidence "
                f"{effective_confidence:.2f} above threshold"
            ),
            advisory_message=None,
            rollback_registered=False,
            action_name=action_name,
            action_category=action_category,
        )
        self._decisions.append(decision)
        return decision

    def _build_advisory_message(
        self, action_name: str, action_category: str
    ) -> str:
        """Generate human-readable advisory message for low-trust actions."""
        category_detail = {
            "cluster_mutation": "apply cluster changes",
            "code_change": "commit code changes and create PR",
        }
        detail = category_detail.get(action_category, action_category)
        return f"At TL3+, Beeper would: {action_name} ({detail})"

    def register_rollback_path(
        self, action_name: str, rollback_action: str
    ) -> dict[str, Any]:
        """Register a rollback path for an autonomous action.

        Returns:
            Rollback entry dict with action details and timestamp.
        """
        entry: dict[str, Any] = {
            "action_name": action_name,
            "rollback_action": rollback_action,
            "investigation_id": self.context.investigation_id,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        self._rollback_paths.append(entry)
        return entry

    def notify_autonomous_action(
        self, action_name: str, action_details: dict[str, Any]
    ) -> None:
        """Log and notify about an autonomous action at TL5."""
        logger.info(
            "Autonomous action executed: %s (details: %s)",
            action_name,
            action_details,
        )
        self.status_updater.update_message(
            f"Autonomous action: {action_name}"
        )

    def get_summary(self) -> TrustGateSummary:
        """Aggregate all decisions made during the pipeline run."""
        executed = sum(1 for d in self._decisions if d.action_type == "executed")
        advisory = sum(1 for d in self._decisions if d.action_type == "advisory")
        requires_approval = sum(
            1 for d in self._decisions if d.action_type == "requires_approval"
        )
        return TrustGateSummary(
            total_actions=len(self._decisions),
            executed=executed,
            advisory=advisory,
            requires_approval=requires_approval,
            rollback_paths=list(self._rollback_paths),
            decisions=[d.to_dict() for d in self._decisions],
        )


class TrustGateStep:
    """Post-hoc trust gate evaluation and evidence recording."""

    name: str = "Trust Gate Evaluation"

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
        self._evaluator = TrustGateEvaluator(context, status_updater)

    def execute(self) -> StepResult:
        """Scan pipeline_metadata and produce trust gate decision record."""
        self.status_updater.update_message("Evaluating trust gate decisions")
        logger.info(
            "Trust gate evaluation starting — TL%d, threshold %.2f",
            self.context.trust_level,
            self.context.confidence_threshold,
        )

        # Scan pipeline_metadata for remediation actions from prior steps
        self._evaluate_runbook_actions()
        self._evaluate_sandbox_actions()
        self._evaluate_metric_verification_actions()
        self._evaluate_pr_actions()

        # Register rollback paths for autonomous actions at TL4-5
        if self.context.trust_level >= 4:
            self._register_rollback_paths()

        # Notify about autonomous actions at TL5
        if self.context.trust_level >= 5:
            self._notify_autonomous_actions()

        summary = self._evaluator.get_summary()

        approval_required = summary.requires_approval > 0

        logger.info(
            "Trust gate evaluation complete: total=%d executed=%d "
            "advisory=%d requires_approval=%d",
            summary.total_actions,
            summary.executed,
            summary.advisory,
            summary.requires_approval,
        )

        return StepResult(
            success=True,
            summary=(
                f"Trust gate: {summary.total_actions} actions evaluated — "
                f"{summary.executed} executed, {summary.advisory} advisory, "
                f"{summary.requires_approval} require approval"
            ),
            data={
                "trust_gate_evaluated": True,
                "trust_gate_trust_level": self.context.trust_level,
                "trust_gate_confidence_threshold": self.context.confidence_threshold,
                "trust_gate_total_actions": summary.total_actions,
                "trust_gate_executed": summary.executed,
                "trust_gate_advisory": summary.advisory,
                "trust_gate_requires_approval": summary.requires_approval,
                "trust_gate_decisions": summary.decisions,
                "trust_gate_rollback_paths": summary.rollback_paths,
                "trust_gate_approval_required": approval_required,
            },
        )

    def _evaluate_runbook_actions(self) -> None:
        """Evaluate trust gate for runbook execution actions."""
        if not self.pipeline_metadata.get("runbook_found"):
            return

        steps_executed = self.pipeline_metadata.get("steps_executed", 0)
        steps_advisory = self.pipeline_metadata.get("steps_advisory", 0)

        if steps_executed > 0:
            confidence = self.pipeline_metadata.get("confidence_percentage")
            conf_val = float(confidence) / 100.0 if confidence is not None else None
            self._evaluator.evaluate(
                action_name="Runbook execution",
                action_category="cluster_mutation",
                confidence=conf_val,
            )

        if steps_advisory > 0:
            self._evaluator.evaluate(
                action_name="Runbook advisory steps",
                action_category="notification",
            )

    def _evaluate_sandbox_actions(self) -> None:
        """Evaluate trust gate for sandbox execution actions."""
        sandbox_executed = self.pipeline_metadata.get("sandbox_executed")
        if sandbox_executed is None:
            return

        if sandbox_executed:
            confidence = self.pipeline_metadata.get("confidence_percentage")
            conf_val = float(confidence) / 100.0 if confidence is not None else None
            self._evaluator.evaluate(
                action_name="Sandbox test execution",
                action_category="cluster_mutation",
                confidence=conf_val,
            )
        else:
            skip_reason = self.pipeline_metadata.get("skip_reason", "unknown")
            if skip_reason == "trust_level_insufficient":
                self._evaluator.evaluate(
                    action_name="Sandbox test execution (skipped)",
                    action_category="cluster_mutation",
                )

    def _evaluate_metric_verification_actions(self) -> None:
        """Evaluate trust gate for metric verification actions."""
        verification_executed = self.pipeline_metadata.get("verification_executed")
        if verification_executed is None:
            return

        if verification_executed:
            self._evaluator.evaluate(
                action_name="Post-fix metric verification",
                action_category="read_only",
            )
        else:
            skip_reason = self.pipeline_metadata.get(
                "verification_skip_reason", "unknown"
            )
            if skip_reason == "trust_level_insufficient":
                self._evaluator.evaluate(
                    action_name="Post-fix metric verification (skipped)",
                    action_category="read_only",
                )

    def _evaluate_pr_actions(self) -> None:
        """Evaluate trust gate for PR generation actions."""
        pr_generated = self.pipeline_metadata.get("pr_generated")
        if pr_generated is None:
            return

        if pr_generated:
            confidence = self.pipeline_metadata.get("confidence_percentage")
            conf_val = float(confidence) / 100.0 if confidence is not None else None
            self._evaluator.evaluate(
                action_name="Auto-PR generation",
                action_category="code_change",
                confidence=conf_val,
            )

    def _register_rollback_paths(self) -> None:
        """Register rollback paths for autonomous actions at TL4-5."""
        if self.pipeline_metadata.get("pr_generated"):
            pr_url = self.pipeline_metadata.get("pr_url", "unknown")
            self._evaluator.register_rollback_path(
                action_name="Auto-PR",
                rollback_action=f"Close PR and revert: {pr_url}",
            )

        if self.pipeline_metadata.get("sandbox_executed"):
            self._evaluator.register_rollback_path(
                action_name="Sandbox deployment",
                rollback_action="Delete sandbox namespace resources",
            )

    def _notify_autonomous_actions(self) -> None:
        """Notify about autonomous actions at TL5."""
        if self.pipeline_metadata.get("pr_generated"):
            self._evaluator.notify_autonomous_action(
                action_name="Auto-PR created",
                action_details={
                    "pr_url": self.pipeline_metadata.get("pr_url"),
                    "draft": self.pipeline_metadata.get("draft", False),
                },
            )
