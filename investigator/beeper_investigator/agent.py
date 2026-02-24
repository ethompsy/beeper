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
from beeper_investigator.kb.client import KBClient, INVESTIGATIONS_COLLECTION
from beeper_investigator.llm.client import LlmClient
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
            self._finalize(result)
            return result
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
        if not self.llm_client.test_connection():
            raise RuntimeError("LLM connection test failed")

        # Log source availability (not required)
        if self.sources.prometheus:
            logger.info("Prometheus source available at %s", self.sources.prometheus.base_url)
        else:
            logger.info("Prometheus source not configured")

        if self.sources.loki:
            logger.info("Loki source available at %s", self.sources.loki.base_url)
        else:
            logger.info("Loki source not configured")

    def _build_steps(self) -> list[InvestigationStep]:
        """Build the ordered list of investigation steps.

        Uses lazy imports to keep the agent framework decoupled from
        specific step implementations.
        """
        from beeper_investigator.steps.impact_assessment import CustomerImpactStep

        steps: list[InvestigationStep] = [
            CustomerImpactStep(
                llm_client=self.llm_client,
                context=self.context,
                status_updater=self.status_updater,
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
