"""Investigator agent lifecycle framework.

Orchestrates: initialize → run_steps → finalize.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from qdrant_client.models import PointStruct

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.kb.auto_creation import AutoKBCreationService
from beeper_investigator.kb.client import INVESTIGATIONS_COLLECTION, KBClient
from beeper_investigator.llm.client import LlmClient, LlmClientError
from beeper_investigator.llm.spending_cap import SpendingCapConfig, SpendingCapEnforcer
from beeper_investigator.sources.loki import LokiClient
from beeper_investigator.sources.prometheus import PrometheusClient
from beeper_investigator.steps import InvestigationStep, StepResult

logger = logging.getLogger(__name__)


@dataclass
class SourceClients:
    """Optional source query clients.

    Either client may be ``None`` if the corresponding source is not configured.
    """

    prometheus: Optional[PrometheusClient] = None
    loki: Optional[LokiClient] = None


@dataclass
class InvestigationResult:
    """Outcome of an investigation run."""

    success: bool
    summary: str
    findings: list[str] = field(default_factory=list)
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class LlmUnavailableError(RuntimeError):
    """Raised when the LLM provider is unavailable (retryable failure)."""

    pass


class InvestigatorAgent:
    """Lifecycle framework for a single investigation.

    Follows the pattern: ``_initialize`` → ``_run_steps`` → ``_finalize``.
    Future stories (3.3-3.8) add investigation steps without modifying
    this framework.
    """

    def __init__(
        self,
        context: InvestigationContext,
        kb_client: KBClient,
        llm_client: LlmClient,
        sources: SourceClients,
        status_updater: InvestigationStatusUpdater,
    ) -> None:
        self.context = context
        self.kb_client = kb_client
        self.llm_client = llm_client
        self.sources = sources
        self.status_updater = status_updater
        self.steps: list[InvestigationStep] | None = None
        # Shared by reference with RCAHypothesisStep; updated after each
        # step in _run_steps() so later steps see prior step results.
        self._pipeline_metadata: dict[str, Any] = {}
        # Spending cap enforcement (optional — disabled when env vars not set)
        cap_config = SpendingCapConfig.from_env()
        self.spending_enforcer: SpendingCapEnforcer | None = (
            SpendingCapEnforcer(cap_config) if cap_config.enabled else None
        )

    def run(self) -> InvestigationResult:
        """Execute the full investigation lifecycle.

        Returns:
            InvestigationResult with success/failure and summary.
        """
        try:
            self._initialize()
            if self.steps is None:
                self.steps = self._build_steps()
            result = self._run_steps()
            result.metadata["model_usage"] = self.llm_client.get_model_usage()
            result.metadata["cache_stats"] = self.llm_client.get_cache_stats()
            result.metadata["cost_stats"] = self.llm_client.get_cost_stats()
            # Update spending enforcer with actual investigation cost
            if self.spending_enforcer:
                cost_cents = result.metadata["cost_stats"].get("total_cost_cents", 0)
                self.spending_enforcer.update_spend(cost_cents)
            self._finalize(result)
            return result
        except LlmUnavailableError:
            # Let LLM unavailability propagate to main() for retryable exit code
            raise
        except Exception as exc:
            error_msg = f"Investigation failed: {exc}"
            logger.exception(error_msg)
            self.status_updater.set_failed(str(exc))
            return InvestigationResult(
                success=False,
                summary="Investigation failed with an unexpected error",
                error=error_msg,
            )

    # ── lifecycle phases ────────────────────────────────

    def _initialize(self) -> None:
        """Validate connections and set initial status."""
        self.status_updater.update_message("Initializing investigation")
        logger.info(
            "Initializing investigation %s for service=%s condition=%s",
            self.context.investigation_id,
            self.context.service,
            self.context.condition,
        )

        # Validate KB connectivity
        if not self.kb_client.health_check():
            raise RuntimeError("KB health check failed")

        # Validate LLM connectivity
        try:
            if not self.llm_client.test_connection():
                self.status_updater.set_llm_unavailable("LLM connection test returned False")
                raise LlmUnavailableError("LLM connection test failed")
        except LlmClientError as exc:
            self.status_updater.set_llm_unavailable(str(exc))
            raise LlmUnavailableError(str(exc)) from exc

        # Log source availability (not required)
        if self.sources.prometheus:
            logger.info("Prometheus source available at %s", self.sources.prometheus.base_url)
        else:
            logger.info("Prometheus source not configured")

        if self.sources.loki:
            logger.info("Loki source available at %s", self.sources.loki.base_url)
        else:
            logger.info("Loki source not configured")

        # Check spending caps and rate limits
        if self.spending_enforcer:
            # Rate limit check
            if not self.spending_enforcer.check_rate_limit():
                msg = "Investigation rate limit exceeded"
                logger.warning(msg)
                self.status_updater.set_failed(msg)
                raise RuntimeError(msg)

            # Budget check
            check = self.spending_enforcer.check_budget(self.context.severity)
            if check.warning:
                logger.warning(
                    "Spending cap warning: %s (%.1f%%)",
                    check.reason,
                    check.spend_pct,
                )
            if not check.allowed:
                msg = f"Spending cap enforcement: {check.reason}"
                logger.warning("Investigation capped: %s", check.reason)
                self.status_updater.set_failed(msg)
                raise RuntimeError(msg)

            self.spending_enforcer.record_investigation()

    def _build_steps(self) -> list[InvestigationStep]:
        """Build the ordered list of investigation steps.

        Uses lazy imports to keep the agent framework decoupled from
        specific step implementations.
        """
        from beeper_investigator.remediation.metric_verifier import MetricVerifierStep
        from beeper_investigator.remediation.pr_generator import PRGeneratorStep
        from beeper_investigator.remediation.proven_fix_accumulator import (
            ProvenFixAccumulatorStep,
        )
        from beeper_investigator.remediation.runbook_executor import RunbookExecutorStep
        from beeper_investigator.remediation.sandbox_executor import SandboxExecutorStep
        from beeper_investigator.remediation.test_planner import TestPlannerStep
        from beeper_investigator.remediation.trust_gate import TrustGateStep
        from beeper_investigator.steps.change_event_correlation import (
            ChangeEventCorrelationStep,
        )
        from beeper_investigator.steps.deploy_correlation import DeployCorrelationStep
        from beeper_investigator.steps.impact_assessment import CustomerImpactStep
        from beeper_investigator.steps.investigation_documentation import (
            InvestigationDocumentationStep,
        )
        from beeper_investigator.steps.kb_query import KBQueryStep
        from beeper_investigator.steps.rca_hypothesis import RCAHypothesisStep
        from beeper_investigator.steps.resolution_recommendations import (
            ResolutionRecommendationStep,
        )
        from beeper_investigator.steps.service_topology import ServiceTopologyStep
        from beeper_investigator.steps.signal_correlation import SignalCorrelationStep

        steps: list[InvestigationStep] = [
            CustomerImpactStep(
                llm_client=self.llm_client,
                context=self.context,
                status_updater=self.status_updater,
            ),
            KBQueryStep(
                kb_client=self.kb_client,
                llm_client=self.llm_client,
                context=self.context,
                status_updater=self.status_updater,
            ),
            SignalCorrelationStep(
                sources=self.sources,
                llm_client=self.llm_client,
                context=self.context,
                status_updater=self.status_updater,
            ),
            DeployCorrelationStep(
                llm_client=self.llm_client,
                context=self.context,
                status_updater=self.status_updater,
                pipeline_metadata=self._pipeline_metadata,
            ),
            ServiceTopologyStep(
                llm_client=self.llm_client,
                context=self.context,
                status_updater=self.status_updater,
                pipeline_metadata=self._pipeline_metadata,
            ),
            ChangeEventCorrelationStep(
                llm_client=self.llm_client,
                context=self.context,
                status_updater=self.status_updater,
                pipeline_metadata=self._pipeline_metadata,
            ),
            RCAHypothesisStep(
                llm_client=self.llm_client,
                context=self.context,
                status_updater=self.status_updater,
                pipeline_metadata=self._pipeline_metadata,
            ),
            ResolutionRecommendationStep(
                llm_client=self.llm_client,
                context=self.context,
                status_updater=self.status_updater,
                pipeline_metadata=self._pipeline_metadata,
            ),
            InvestigationDocumentationStep(
                llm_client=self.llm_client,
                kb_client=self.kb_client,
                context=self.context,
                status_updater=self.status_updater,
                pipeline_metadata=self._pipeline_metadata,
            ),
            RunbookExecutorStep(
                llm_client=self.llm_client,
                kb_client=self.kb_client,
                context=self.context,
                status_updater=self.status_updater,
                pipeline_metadata=self._pipeline_metadata,
            ),
            TestPlannerStep(
                llm_client=self.llm_client,
                context=self.context,
                status_updater=self.status_updater,
                pipeline_metadata=self._pipeline_metadata,
            ),
            SandboxExecutorStep(
                llm_client=self.llm_client,
                context=self.context,
                status_updater=self.status_updater,
                pipeline_metadata=self._pipeline_metadata,
                sources=self.sources,
            ),
            MetricVerifierStep(
                llm_client=self.llm_client,
                context=self.context,
                status_updater=self.status_updater,
                pipeline_metadata=self._pipeline_metadata,
                sources=self.sources,
            ),
            PRGeneratorStep(
                llm_client=self.llm_client,
                context=self.context,
                status_updater=self.status_updater,
                pipeline_metadata=self._pipeline_metadata,
            ),
            TrustGateStep(
                llm_client=self.llm_client,
                context=self.context,
                status_updater=self.status_updater,
                pipeline_metadata=self._pipeline_metadata,
            ),
            ProvenFixAccumulatorStep(
                llm_client=self.llm_client,
                kb_client=self.kb_client,
                context=self.context,
                status_updater=self.status_updater,
                pipeline_metadata=self._pipeline_metadata,
            ),
        ]
        return steps

    def _run_steps(self) -> InvestigationResult:
        """Run registered investigation steps sequentially.

        Each step is non-fatal: failures are logged but do not abort
        the pipeline. Step data is merged into the result metadata.
        """
        self.status_updater.update_message("Running investigation steps")

        if not self.steps:
            logger.info("No investigation steps configured")
            return InvestigationResult(
                success=True,
                summary="No investigation steps configured",
            )

        all_findings: list[str] = []
        metadata: dict[str, Any] = {}

        for step in self.steps:
            self.status_updater.update_message(f"Running: {step.name}")
            logger.info("Executing step: %s", step.name)
            try:
                result = step.execute()
            except Exception as exc:
                logger.exception("Step %s raised an exception", step.name)
                result = StepResult(
                    success=False,
                    summary=f"Step {step.name} failed unexpectedly",
                    error=str(exc),
                )

            if result.summary:
                all_findings.append(result.summary)
            metadata.update(result.data)
            self._pipeline_metadata.update(result.data)

            if not result.success:
                logger.warning("Step %s failed: %s", step.name, result.error)

        return InvestigationResult(
            success=True,
            summary="; ".join(all_findings) if all_findings else "Investigation complete",
            findings=all_findings,
            metadata=metadata,
        )

    def _finalize(self, result: InvestigationResult) -> None:
        """Persist results and update final status."""
        logger.info(
            "Finalizing investigation %s: success=%s",
            self.context.investigation_id,
            result.success,
        )

        # Persist investigation result to Qdrant
        persisted = self._persist_result(result)

        # Auto-create KB entry from resolved investigation (FR38)
        if result.success:
            try:
                auto_kb_result = self._auto_create_kb_entry(result)
                result.metadata["auto_kb_creation"] = auto_kb_result
            except Exception:
                logger.exception(
                    "Auto KB entry creation failed (non-fatal)"
                )
                result.metadata["auto_kb_creation"] = {
                    "action": "skipped",
                    "reason": "exception",
                }

        # Update Investigation CR status
        if result.success:
            summary = result.summary
            if not persisted:
                summary = f"{summary} (WARNING: results not persisted to KB)"
            self.status_updater.set_completed(summary)
        else:
            self.status_updater.set_failed(result.error or result.summary)

    def _persist_result(self, result: InvestigationResult) -> bool:
        """Store investigation outcome in the Qdrant investigations collection.

        Returns:
            True if persistence succeeded, False otherwise.
        """
        _RESERVED_KEYS = {
            "investigation_id", "service", "condition", "severity",
            "status", "summary", "findings", "created_at",
        }
        safe_metadata = {}
        for key, value in result.metadata.items():
            if key in _RESERVED_KEYS:
                logger.warning(
                    "Step metadata key '%s' collides with reserved payload field; skipping",
                    key,
                )
            else:
                safe_metadata[key] = value

        payload = {
            "investigation_id": self.context.investigation_id,
            "service": self.context.service,
            "condition": self.context.condition,
            "severity": self.context.severity,
            "status": "resolved" if result.success else "failed",
            "summary": result.summary,
            "findings": result.findings,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **safe_metadata,
        }
        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=[0.0] * 1536,  # placeholder; embedding added in future stories
            payload=payload,
        )
        try:
            self.kb_client.client.upsert(INVESTIGATIONS_COLLECTION, [point])
            logger.info("Persisted investigation result to Qdrant")
            return True
        except Exception:
            logger.exception("Failed to persist investigation result to Qdrant")
            return False

    def _auto_create_kb_entry(
        self, result: "InvestigationResult"
    ) -> dict[str, Any]:
        """Auto-create KB entry from resolved investigation (FR38).

        Non-fatal: returns result dict even on failure.
        """
        service = AutoKBCreationService(self.kb_client, self.llm_client)

        pm = self._pipeline_metadata if self._pipeline_metadata else {}

        investigation_data: dict[str, Any] = {
            # Context
            "investigation_id": self.context.investigation_id,
            "service": self.context.service,
            "condition": self.context.condition,
            "severity": self.context.severity,
            # Pipeline metadata
            "root_cause_hypothesis": pm.get("root_cause_hypothesis", ""),
            "confidence_level": pm.get("confidence_level", ""),
            "confidence_percentage": pm.get("confidence_percentage"),
            "signals_summary": pm.get("signal_summary", ""),
            "supporting_evidence": pm.get("supporting_evidence", []),
            "recommendations": pm.get("recommendations", []),
            "prior_research_summary": pm.get("prior_research_summary", ""),
            "relevant_matches": pm.get("relevant_matches", []),
            "customer_impacting": pm.get("customer_impacting"),
            "related_investigations": pm.get("related_investigations", []),
            # Result
            "summary": result.summary,
            "findings": result.findings,
            # Documentation step output
            "documentation_title": pm.get("documentation_title", ""),
            "documentation_summary": pm.get("documentation_summary", ""),
            "kb_entry_id": pm.get("kb_entry_id"),
            "key_findings": pm.get("key_findings", []),
        }

        return service.create_or_update_from_investigation(investigation_data)
