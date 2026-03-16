"""Post-fix metric verification step.

Compares pre-fix and post-fix Prometheus metrics for affected SLOs
to determine if a fix actually resolved the issue. Produces one of
three verification outcomes: confirmed, inconclusive, or degraded.
Trust-gated at TL3+. On degradation, flags rollback_recommended.
On confirmation, marks the fix as proven for KB accumulation.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.steps import StepResult

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result from comparing a single metric pre-fix vs post-fix."""

    metric: str
    pre_fix_value: float | None
    post_fix_value: float | None
    status: str  # "confirmed" | "inconclusive" | "degraded"
    delta_pct: float | None
    error_message: str | None


class MetricVerifierStep:
    """Verify fix effectiveness by comparing pre/post-fix metrics."""

    name: str = "Post-Fix Metric Verification"

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
        # Configurable verification window (default 15 minutes per AC#1)
        window_raw = os.environ.get("VERIFICATION_WINDOW_MINUTES", "15")
        try:
            self._verification_window_minutes = max(1, int(window_raw))
        except (ValueError, TypeError):
            self._verification_window_minutes = 15

    # ── Main execution ────────────────────────────────────

    def execute(self) -> StepResult:
        """Execute post-fix metric verification.

        Trust gating: skips at TL1-2. Requires a fix to have been
        applied (sandbox or PR) and Prometheus for metric queries.
        """
        # Trust gate: TL3+ required
        if self.context.trust_level < 3:
            logger.info(
                "Post-fix verification skipped — trust level %d below TL3",
                self.context.trust_level,
            )
            return StepResult(
                success=True,
                summary=(
                    f"Post-fix verification skipped — trust level "
                    f"{self.context.trust_level} below TL3 threshold"
                ),
                data={
                    "verification_executed": False,
                    "skip_reason": "trust_level_insufficient",
                    "trust_level": self.context.trust_level,
                },
            )

        # Check if a fix was applied
        fix_applied = (
            self.pipeline_metadata.get("sandbox_executed")
            or self.pipeline_metadata.get("pr_generated")
        )
        if not fix_applied:
            logger.info("Post-fix verification skipped — no fix applied")
            return StepResult(
                success=True,
                summary="No fix applied — metric verification skipped",
                data={
                    "verification_executed": False,
                    "skip_reason": "no_fix_applied",
                },
            )

        # Check Prometheus availability
        if not self.sources or not self.sources.prometheus:
            logger.info("Post-fix verification skipped — Prometheus not configured")
            return StepResult(
                success=True,
                summary="Prometheus not configured — metric verification skipped",
                data={
                    "verification_executed": False,
                    "skip_reason": "no_prometheus",
                },
            )

        # Check metrics_to_watch
        metrics = self.pipeline_metadata.get("metrics_to_watch", [])
        if not metrics:
            logger.info("Post-fix verification skipped — no metrics to watch")
            return StepResult(
                success=True,
                summary="No metrics to watch — metric verification skipped",
                data={
                    "verification_executed": False,
                    "skip_reason": "no_metrics_to_watch",
                },
            )

        # Execute metric comparison
        self.status_updater.update_message(
            "Verifying post-fix metrics"
        )
        logger.info(
            "Starting post-fix metric verification: metrics=%d window=%dmin",
            len(metrics),
            self._verification_window_minutes,
        )

        results = self._compare_metrics(metrics)
        overall_status = self._determine_overall_status(results)

        confirmed = sum(1 for r in results if r.status == "confirmed")
        degraded = sum(1 for r in results if r.status == "degraded")
        inconclusive = sum(1 for r in results if r.status == "inconclusive")

        # Handle outcome
        fix_verified = False
        fix_proven = False
        rollback_recommended = False

        if overall_status == "degraded":
            self._handle_degradation(results)
            rollback_recommended = True
        elif overall_status == "confirmed":
            self._handle_confirmed()
            fix_verified = True
            fix_proven = True

        summary = (
            f"Post-fix verification {overall_status}: "
            f"{confirmed} confirmed, {degraded} degraded, "
            f"{inconclusive} inconclusive"
        )
        logger.info(
            "Post-fix verification complete: overall=%s confirmed=%d "
            "degraded=%d inconclusive=%d",
            overall_status, confirmed, degraded, inconclusive,
        )

        return StepResult(
            success=True,
            summary=summary,
            data={
                "verification_executed": True,
                "verification_status": overall_status,
                "verification_window_minutes": self._verification_window_minutes,
                "metrics_compared": len(results),
                "metrics_confirmed": confirmed,
                "metrics_degraded": degraded,
                "metrics_inconclusive": inconclusive,
                "verification_results": [
                    {
                        "metric": r.metric,
                        "pre_fix_value": r.pre_fix_value,
                        "post_fix_value": r.post_fix_value,
                        "status": r.status,
                        "delta_pct": r.delta_pct,
                        "error_message": r.error_message,
                    }
                    for r in results
                ],
                "fix_verified": fix_verified,
                "fix_proven": fix_proven,
                "rollback_recommended": rollback_recommended,
                "verification_model_tier": "remediation",
            },
        )

    # ── Metric comparison ─────────────────────────────────

    def _query_metric_range(
        self, metric: str, offset_minutes: int, duration_minutes: int
    ) -> float | None:
        """Query Prometheus for average metric value over a time range.

        Uses PromQL avg_over_time with offset for time-shifted queries.
        Returns average value as float, or None if no data/error.
        """
        if offset_minutes > 0:
            query = (
                f"avg_over_time({metric}[{duration_minutes}m] "
                f"offset {offset_minutes}m)"
            )
        else:
            query = f"avg_over_time({metric}[{duration_minutes}m])"

        try:
            assert self.sources is not None  # guarded in execute()
            result = self.sources.prometheus.query(query)
            data = result.get("data", {}).get("result", [])
            if data and len(data) > 0:
                value = data[0].get("value", [None, None])
                if isinstance(value, list) and len(value) > 1 and value[1] is not None:
                    return float(value[1])
        except Exception as exc:
            logger.warning("Prometheus query failed for %s: %s", metric, exc)
        return None

    def _compare_metrics(
        self, metrics: list[str],
    ) -> list[VerificationResult]:
        """Compare pre-fix and post-fix metric values for all metrics."""
        results: list[VerificationResult] = []
        window = self._verification_window_minutes

        for metric in metrics:
            # Pre-fix: average value during window before fix applied
            pre_val = self._query_metric_range(
                metric, offset_minutes=window + 5, duration_minutes=5,
            )
            # Post-fix: average value in last 5 minutes
            post_val = self._query_metric_range(
                metric, offset_minutes=0, duration_minutes=5,
            )

            if pre_val is None and post_val is None:
                results.append(VerificationResult(
                    metric=metric,
                    pre_fix_value=None,
                    post_fix_value=None,
                    status="inconclusive",
                    delta_pct=None,
                    error_message="Incomplete metric data",
                ))
                continue

            if pre_val is None or post_val is None:
                results.append(VerificationResult(
                    metric=metric,
                    pre_fix_value=pre_val,
                    post_fix_value=post_val,
                    status="inconclusive",
                    delta_pct=None,
                    error_message=None,
                ))
                continue

            # Calculate percentage change
            if pre_val == 0:
                delta_pct = 0.0 if post_val == 0 else 100.0
            else:
                delta_pct = ((post_val - pre_val) / abs(pre_val)) * 100

            # Classify: error/restart metrics decreasing = good (confirmed),
            # increasing = bad (degraded). Threshold: 10%.
            if abs(delta_pct) < 10:
                status = "inconclusive"
            elif delta_pct < -10:
                status = "confirmed"
            else:
                status = "degraded"

            results.append(VerificationResult(
                metric=metric,
                pre_fix_value=round(pre_val, 4),
                post_fix_value=round(post_val, 4),
                status=status,
                delta_pct=round(delta_pct, 2),
                error_message=None,
            ))

        return results

    @staticmethod
    def _determine_overall_status(results: list[VerificationResult]) -> str:
        """Compute overall verification status from individual metric results.

        Returns: "confirmed", "degraded", or "inconclusive".
        """
        if not results:
            return "inconclusive"

        has_degraded = any(r.status == "degraded" for r in results)
        if has_degraded:
            return "degraded"

        has_confirmed = any(r.status == "confirmed" for r in results)
        all_confirmed = all(r.status == "confirmed" for r in results)
        if all_confirmed:
            return "confirmed"
        if has_confirmed:
            return "inconclusive"

        return "inconclusive"

    # ── Outcome handlers ──────────────────────────────────

    def _handle_degradation(
        self, results: list[VerificationResult],
    ) -> None:
        """Notify SRE and flag rollback on metric degradation (NFR16, FR62)."""
        degraded = [r for r in results if r.status == "degraded"]
        comparison = "; ".join(
            f"{r.metric}: {r.pre_fix_value} → {r.post_fix_value} "
            f"({r.delta_pct:+.1f}%)" if r.delta_pct is not None
            else f"{r.metric}: degraded"
            for r in degraded
        )
        self.status_updater.update_message(
            f"DEGRADATION DETECTED — rollback recommended. {comparison}"
        )
        logger.warning(
            "Post-fix metric degradation detected: %s", comparison,
        )

    def _handle_confirmed(self) -> None:
        """Update status when fix is confirmed by metrics (AC#3)."""
        self.status_updater.update_message(
            "Fix verified — metrics confirm resolution"
        )
        logger.info("Post-fix metrics confirm resolution — fix proven")
