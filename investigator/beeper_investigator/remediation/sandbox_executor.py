"""Sandbox test execution step.

Executes advisory test plan steps in an isolated sandbox environment,
dispatching each verification step by type (metric_check, api_probe,
health_check, log_inspection, manual_verification). Trust-gated at TL3+.
If no sandbox namespace is available, gracefully degrades to advisory-only.
"""

import logging
import os
import time as time_module
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.steps import StepResult

logger = logging.getLogger(__name__)


@dataclass
class SandboxStepResult:
    """Result from executing a single verification step in the sandbox."""

    step_number: int
    title: str
    status: str  # "pass" | "fail" | "error" | "skipped"
    verification_type: str
    expected_outcome: str
    actual_value: str
    error_message: str | None
    duration_seconds: float


class SandboxExecutorStep:
    """Execute advisory test plan in isolated sandbox environment."""

    name: str = "Sandbox Test Execution"

    def __init__(
        self,
        llm_client: LlmClient,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
        pipeline_metadata: dict[str, Any] | None = None,
        sources: Any | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.context = context
        self.status_updater = status_updater
        self.pipeline_metadata = pipeline_metadata if pipeline_metadata is not None else {}
        self.sources = sources
        self._k8s_core_api: Any | None = None  # Lazy init

    # ── Sandbox availability ──────────────────────────────

    def _get_k8s_core_api(self) -> Any:
        """Lazy-initialize K8s CoreV1Api to avoid config loading in tests."""
        if self._k8s_core_api is None:
            from kubernetes import client, config

            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config()
            self._k8s_core_api = client.CoreV1Api()
        return self._k8s_core_api

    def _check_sandbox_available(self) -> str | None:
        """Check if a sandbox namespace is available.

        Returns namespace name if available, None otherwise.
        Checks SANDBOX_NAMESPACE env var first, then K8s API.
        """
        ns = os.environ.get("SANDBOX_NAMESPACE")
        if ns:
            logger.info("Sandbox namespace from env: %s", ns)
            return ns

        try:
            api = self._get_k8s_core_api()
            api.read_namespace("beeper-sandbox")
            logger.info("Sandbox namespace detected via K8s API: beeper-sandbox")
            return "beeper-sandbox"
        except Exception as exc:
            # Distinguish K8s 404 (namespace doesn't exist) from real errors
            status = getattr(exc, "status", None)
            if status == 404:
                logger.info("Sandbox namespace 'beeper-sandbox' does not exist")
            else:
                logger.warning("Error checking sandbox namespace: %s", exc)
            return None

    # ── Main execution ────────────────────────────────────

    def execute(self) -> StepResult:
        """Execute sandbox test plan.

        Trust gating: skips at TL1-2. Requires test plan and sandbox
        namespace. Dispatches each verification step by type.
        """
        # Trust gate: TL3+ required
        if self.context.trust_level < 3:
            logger.info(
                "Sandbox execution skipped — trust level %d below TL3",
                self.context.trust_level,
            )
            return StepResult(
                success=True,
                summary=(
                    f"Sandbox execution skipped — trust level "
                    f"{self.context.trust_level} below TL3 threshold"
                ),
                data={
                    "sandbox_executed": False,
                    "skip_reason": "trust_level_insufficient",
                    "trust_level": self.context.trust_level,
                },
            )

        # Check for test plan
        if not self.pipeline_metadata.get("test_plan_generated"):
            logger.info("Sandbox execution skipped — no test plan available")
            return StepResult(
                success=True,
                summary="No test plan available — sandbox execution skipped",
                data={
                    "sandbox_executed": False,
                    "skip_reason": "no_test_plan",
                },
            )

        # Check promotable_to_sandbox
        if not self.pipeline_metadata.get("promotable_to_sandbox", True):
            logger.info("Sandbox execution skipped — test plan not promotable")
            return StepResult(
                success=True,
                summary="Test plan not promotable to sandbox",
                data={
                    "sandbox_executed": False,
                    "skip_reason": "not_promotable",
                },
            )

        # Check verification steps exist
        verification_steps = self.pipeline_metadata.get("verification_steps", [])
        if not verification_steps:
            logger.info("Sandbox execution skipped — no verification steps")
            return StepResult(
                success=True,
                summary="No verification steps available — sandbox execution skipped",
                data={
                    "sandbox_executed": False,
                    "skip_reason": "no_verification_steps",
                },
            )

        # Check sandbox availability (AC#3)
        self.status_updater.update_message("Checking sandbox availability")
        sandbox_ns = self._check_sandbox_available()
        if sandbox_ns is None:
            logger.info("No sandbox available — manual verification recommended")
            return StepResult(
                success=True,
                summary="No sandbox available — manual verification recommended",
                data={
                    "sandbox_executed": False,
                    "skip_reason": "no_sandbox_configured",
                    "advisory_test_plan_only": True,
                },
            )

        # Execute verification steps
        self.status_updater.update_message(
            f"Executing sandbox tests in {sandbox_ns}"
        )
        logger.info(
            "Starting sandbox execution: namespace=%s steps=%d",
            sandbox_ns,
            len(verification_steps),
        )

        overall_start = time_module.monotonic()
        step_results = self._execute_verification_steps(
            verification_steps, sandbox_ns
        )
        overall_duration = time_module.monotonic() - overall_start

        # Aggregate results
        overall_status = self._aggregate_results(step_results)
        passed = sum(1 for r in step_results if r.status == "pass")
        failed = sum(1 for r in step_results if r.status == "fail")
        skipped = sum(1 for r in step_results if r.status == "skipped")
        errored = sum(1 for r in step_results if r.status == "error")

        summary = (
            f"Sandbox tests {overall_status}: "
            f"{passed} passed, {failed} failed, "
            f"{skipped} skipped, {errored} errors "
            f"in {sandbox_ns}"
        )
        logger.info(
            "Sandbox execution complete: overall=%s passed=%d failed=%d "
            "skipped=%d errored=%d duration=%.1fs",
            overall_status, passed, failed, skipped, errored, overall_duration,
        )

        return StepResult(
            success=True,
            summary=summary,
            data={
                "sandbox_executed": True,
                "sandbox_namespace": sandbox_ns,
                "sandbox_steps_total": len(step_results),
                "sandbox_steps_passed": passed,
                "sandbox_steps_failed": failed,
                "sandbox_steps_skipped": skipped,
                "sandbox_steps_errored": errored,
                "sandbox_test_results": [
                    {
                        "step_number": r.step_number,
                        "title": r.title,
                        "status": r.status,
                        "verification_type": r.verification_type,
                        "expected_outcome": r.expected_outcome,
                        "actual_value": r.actual_value,
                        "error_message": r.error_message,
                        "duration_seconds": r.duration_seconds,
                    }
                    for r in step_results
                ],
                "sandbox_overall_status": overall_status,
                "sandbox_duration_seconds": round(overall_duration, 3),
                "sandbox_model_tier": "remediation",
            },
        )

    # ── Verification step execution ───────────────────────

    def _execute_verification_steps(
        self,
        steps: list[dict[str, Any]],
        namespace: str,
    ) -> list[SandboxStepResult]:
        """Iterate verification steps and dispatch each by type."""
        results: list[SandboxStepResult] = []
        for step in steps:
            if not isinstance(step, dict):
                logger.warning(
                    "Skipping non-dict verification step: %s",
                    type(step).__name__,
                )
                continue
            result = self._dispatch_step(step, namespace)
            results.append(result)
        return results

    def _dispatch_step(
        self, step: dict[str, Any], namespace: str
    ) -> SandboxStepResult:
        """Dispatch a verification step to the appropriate executor."""
        vtype = str(step.get("verification_type", "manual_verification"))
        executors = {
            "metric_check": self._execute_metric_check,
            "api_probe": self._execute_api_probe,
            "health_check": self._execute_health_check,
            "log_inspection": self._execute_log_inspection,
            "manual_verification": self._execute_manual_verification,
        }
        executor = executors.get(vtype, self._execute_manual_verification)
        try:
            return executor(step, namespace)
        except Exception as exc:
            logger.warning(
                "Verification step %s failed unexpectedly: %s",
                step.get("step_number", "?"),
                exc,
            )
            return SandboxStepResult(
                step_number=step.get("step_number", 0),
                title=str(step.get("title", "Unknown")),
                status="error",
                verification_type=vtype,
                expected_outcome=str(step.get("expected_outcome", "")),
                actual_value="",
                error_message=str(exc),
                duration_seconds=0.0,
            )

    def _execute_metric_check(
        self, step: dict[str, Any], namespace: str
    ) -> SandboxStepResult:
        """Execute a Prometheus metric check."""
        start = time_module.monotonic()
        step_number = step.get("step_number", 0)
        title = str(step.get("title", "Metric Check"))
        expected = str(step.get("expected_outcome", ""))
        metric = str(step.get("metric_or_endpoint", ""))

        if not self.sources or not self.sources.prometheus:
            return SandboxStepResult(
                step_number=step_number,
                title=title,
                status="skipped",
                verification_type="metric_check",
                expected_outcome=expected,
                actual_value="",
                error_message="Prometheus source not configured",
                duration_seconds=time_module.monotonic() - start,
            )

        try:
            result = self.sources.prometheus.query(metric)
            result_data = result.get("data", {}).get("result", [])
            actual = str(result_data) if result_data else "no data"
            # Simple presence check — actual comparison is advisory
            status = "pass" if result_data else "fail"
        except Exception as exc:
            return SandboxStepResult(
                step_number=step_number,
                title=title,
                status="error",
                verification_type="metric_check",
                expected_outcome=expected,
                actual_value="",
                error_message=str(exc),
                duration_seconds=time_module.monotonic() - start,
            )

        return SandboxStepResult(
            step_number=step_number,
            title=title,
            status=status,
            verification_type="metric_check",
            expected_outcome=expected,
            actual_value=actual,
            error_message=None,
            duration_seconds=time_module.monotonic() - start,
        )

    def _execute_api_probe(
        self, step: dict[str, Any], namespace: str
    ) -> SandboxStepResult:
        """Execute an HTTP API probe."""
        start = time_module.monotonic()
        step_number = step.get("step_number", 0)
        title = str(step.get("title", "API Probe"))
        expected = str(step.get("expected_outcome", ""))
        endpoint = str(step.get("metric_or_endpoint", ""))

        parsed = urlparse(endpoint)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return SandboxStepResult(
                step_number=step_number,
                title=title,
                status="error",
                verification_type="api_probe",
                expected_outcome=expected,
                actual_value="",
                error_message=f"Invalid endpoint URL: {endpoint}",
                duration_seconds=time_module.monotonic() - start,
            )

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(endpoint)
            actual = f"HTTP {response.status_code}"
            status = "pass" if response.is_success else "fail"
        except Exception as exc:
            return SandboxStepResult(
                step_number=step_number,
                title=title,
                status="error",
                verification_type="api_probe",
                expected_outcome=expected,
                actual_value="",
                error_message=str(exc),
                duration_seconds=time_module.monotonic() - start,
            )

        return SandboxStepResult(
            step_number=step_number,
            title=title,
            status=status,
            verification_type="api_probe",
            expected_outcome=expected,
            actual_value=actual,
            error_message=None,
            duration_seconds=time_module.monotonic() - start,
        )

    def _execute_health_check(
        self, step: dict[str, Any], namespace: str
    ) -> SandboxStepResult:
        """Execute a health endpoint check."""
        start = time_module.monotonic()
        step_number = step.get("step_number", 0)
        title = str(step.get("title", "Health Check"))
        expected = str(step.get("expected_outcome", ""))
        endpoint = str(step.get("metric_or_endpoint", ""))

        parsed = urlparse(endpoint)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return SandboxStepResult(
                step_number=step_number,
                title=title,
                status="error",
                verification_type="health_check",
                expected_outcome=expected,
                actual_value="",
                error_message=f"Invalid endpoint URL: {endpoint}",
                duration_seconds=time_module.monotonic() - start,
            )

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(endpoint)
            actual = f"HTTP {response.status_code}"
            status = "pass" if response.status_code == 200 else "fail"
        except Exception as exc:
            return SandboxStepResult(
                step_number=step_number,
                title=title,
                status="error",
                verification_type="health_check",
                expected_outcome=expected,
                actual_value="",
                error_message=str(exc),
                duration_seconds=time_module.monotonic() - start,
            )

        return SandboxStepResult(
            step_number=step_number,
            title=title,
            status=status,
            verification_type="health_check",
            expected_outcome=expected,
            actual_value=actual,
            error_message=None,
            duration_seconds=time_module.monotonic() - start,
        )

    def _execute_log_inspection(
        self, step: dict[str, Any], namespace: str
    ) -> SandboxStepResult:
        """Execute a Loki log inspection."""
        start = time_module.monotonic()
        step_number = step.get("step_number", 0)
        title = str(step.get("title", "Log Inspection"))
        expected = str(step.get("expected_outcome", ""))
        action = str(step.get("action", ""))

        if not self.sources or not self.sources.loki:
            return SandboxStepResult(
                step_number=step_number,
                title=title,
                status="skipped",
                verification_type="log_inspection",
                expected_outcome=expected,
                actual_value="",
                error_message="Loki source not configured",
                duration_seconds=time_module.monotonic() - start,
            )

        try:
            # Scope query to sandbox namespace; escape backticks in action
            safe_action = action.replace("`", "\\`")
            logql = f'{{namespace="{namespace}"}} |= `{safe_action}`'
            result = self.sources.loki.query(logql, limit=10)
            result_data = result.get("data", {}).get("result", [])
            actual = str(result_data) if result_data else "no matching logs"
            status = "pass" if result_data else "fail"
        except Exception as exc:
            return SandboxStepResult(
                step_number=step_number,
                title=title,
                status="error",
                verification_type="log_inspection",
                expected_outcome=expected,
                actual_value="",
                error_message=str(exc),
                duration_seconds=time_module.monotonic() - start,
            )

        return SandboxStepResult(
            step_number=step_number,
            title=title,
            status=status,
            verification_type="log_inspection",
            expected_outcome=expected,
            actual_value=actual,
            error_message=None,
            duration_seconds=time_module.monotonic() - start,
        )

    def _execute_manual_verification(
        self, step: dict[str, Any], namespace: str
    ) -> SandboxStepResult:
        """Return skipped for manual verification steps."""
        return SandboxStepResult(
            step_number=step.get("step_number", 0),
            title=str(step.get("title", "Manual Verification")),
            status="skipped",
            verification_type="manual_verification",
            expected_outcome=str(step.get("expected_outcome", "")),
            actual_value="",
            error_message=(
                "Manual verification required — "
                "automated sandbox execution not possible for this step"
            ),
            duration_seconds=0.0,
        )

    # ── Result aggregation ────────────────────────────────

    @staticmethod
    def _aggregate_results(results: list[SandboxStepResult]) -> str:
        """Compute overall sandbox status from individual step results.

        Returns: "pass", "fail", "partial", or "skipped".
        """
        if not results:
            return "skipped"

        non_skipped = [r for r in results if r.status != "skipped"]
        if not non_skipped:
            return "skipped"

        has_pass = any(r.status == "pass" for r in non_skipped)
        has_fail = any(r.status in ("fail", "error") for r in non_skipped)

        if has_fail and has_pass:
            return "partial"
        if has_fail:
            return "fail"
        return "pass"

