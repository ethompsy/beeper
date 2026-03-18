"""Executive Report service for investor-ready reports.

Aggregates data from Investigation, SLO, Noise Report, and Trust Level
services to produce executive summary metrics with period-over-period
comparison.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from beeper_ui.services.analytics_service import (
    _parse_dt,
    compute_mttr_change_pct,
    compute_mttr_trends,
    compute_trust_changes,
    compute_trust_distribution,
)
from beeper_ui.services.investigation_service import (
    Investigation,
    InvestigationService,
    InvestigationServiceError,
)
from beeper_ui.services.noise_report_service import (
    NoiseReportService,
    NoiseReportServiceError,
)
from beeper_ui.services.slo_service import SloService, SloServiceError

logger = logging.getLogger(__name__)

VALID_EXECUTIVE_PERIODS = {"30d", "90d", "all"}

_PERIOD_DAYS: dict[str, int | None] = {
    "30d": 30,
    "90d": 90,
    "all": None,
}

_PERIOD_LABELS: dict[str, str] = {
    "30d": "Last 30 Days",
    "90d": "Last 90 Days",
    "all": "All Time",
}


def compute_executive_metrics(
    investigations: list[Investigation],
    slo_services: list[dict[str, Any]],
    trust_configs: list[dict[str, Any]],
    false_page_rate: float,
    period_days: int | None = None,
) -> dict[str, Any]:
    """Compute executive summary metrics for a given period.

    Args:
        investigations: List of Investigation objects.
        slo_services: List of SLO service dicts with compliance field.
        trust_configs: List of trust config dicts with trust_level field.
        false_page_rate: Overall false page rate for the period.
        period_days: Number of days to look back, or None for all time.

    Returns:
        Dict with total_resolved, mttr_improvement_pct, avg_slo_compliance,
        trust_progression, false_page_rate.
    """
    now = datetime.now(timezone.utc)

    # Filter investigations to period
    if period_days is not None:
        cutoff = now - timedelta(days=period_days)
        period_invs = [
            inv
            for inv in investigations
            if inv.started_at and (_parse_dt(inv.started_at) or now) >= cutoff
        ]
    else:
        period_invs = list(investigations)

    # Total resolved investigations
    total_resolved = sum(
        1 for inv in period_invs if inv.status == "completed"
    )

    # MTTR improvement
    num_weeks = (period_days // 7) if period_days else 52
    mttr_trends = compute_mttr_trends(period_invs, num_weeks=max(num_weeks, 2))
    mttr_improvement_pct = compute_mttr_change_pct(mttr_trends)

    # Average SLO compliance
    compliance_values = [
        s["compliance"]
        for s in slo_services
        if s.get("compliance") is not None
    ]
    avg_slo_compliance = (
        round(sum(compliance_values) / len(compliance_values), 4)
        if compliance_values
        else None
    )

    # Trust progression
    trust_dist = compute_trust_distribution(trust_configs)
    trust_changes = compute_trust_changes(trust_configs)

    return {
        "total_resolved": total_resolved,
        "mttr_improvement_pct": mttr_improvement_pct,
        "avg_slo_compliance": avg_slo_compliance,
        "trust_progression": {
            "distribution": trust_dist,
            "changes_count": len(trust_changes),
            "changes": trust_changes[:5],
        },
        "false_page_rate": false_page_rate,
    }


def compute_period_comparison(
    current: dict[str, Any],
    previous: dict[str, Any],
) -> dict[str, Any]:
    """Compute comparison between current and previous period metrics.

    Args:
        current: Current period metrics dict.
        previous: Previous period metrics dict.

    Returns:
        Dict with delta and direction for each comparable metric.
    """
    comparisons: dict[str, Any] = {}

    # Resolved investigation count change
    curr_resolved = current.get("total_resolved", 0)
    prev_resolved = previous.get("total_resolved", 0)
    if prev_resolved > 0:
        resolved_delta = round(
            (curr_resolved - prev_resolved) / prev_resolved * 100, 1
        )
    else:
        resolved_delta = None
    comparisons["resolved"] = {
        "current": curr_resolved,
        "previous": prev_resolved,
        "delta_pct": resolved_delta,
        "direction": _direction(resolved_delta),
    }

    # MTTR improvement
    curr_mttr = current.get("mttr_improvement_pct")
    prev_mttr = previous.get("mttr_improvement_pct")
    comparisons["mttr"] = {
        "current": curr_mttr,
        "previous": prev_mttr,
        "direction": _mttr_direction(curr_mttr),
    }

    # SLO compliance
    curr_slo = current.get("avg_slo_compliance")
    prev_slo = previous.get("avg_slo_compliance")
    if curr_slo is not None and prev_slo is not None and prev_slo > 0:
        slo_delta = round((curr_slo - prev_slo) / prev_slo * 100, 2)
    else:
        slo_delta = None
    comparisons["slo_compliance"] = {
        "current": curr_slo,
        "previous": prev_slo,
        "delta_pct": slo_delta,
        "direction": _direction(slo_delta),
    }

    # False page rate reduction
    curr_fp = current.get("false_page_rate", 0)
    prev_fp = previous.get("false_page_rate", 0)
    if prev_fp > 0:
        fp_delta = round((curr_fp - prev_fp) / prev_fp * 100, 1)
    else:
        fp_delta = None
    comparisons["false_page_rate"] = {
        "current": curr_fp,
        "previous": prev_fp,
        "delta_pct": fp_delta,
        "direction": _fp_direction(fp_delta),
    }

    return comparisons


def _direction(delta: float | None) -> str:
    """Return 'improved', 'declined', or 'stable' based on delta."""
    if delta is None:
        return "stable"
    if delta > 0:
        return "improved"
    if delta < 0:
        return "declined"
    return "stable"


def _mttr_direction(change_pct: float | None) -> str:
    """MTTR direction: negative = improved (faster resolution)."""
    if change_pct is None:
        return "stable"
    if change_pct < 0:
        return "improved"
    if change_pct > 0:
        return "declined"
    return "stable"


def _fp_direction(delta: float | None) -> str:
    """False page direction: negative = improved (fewer false pages)."""
    if delta is None:
        return "stable"
    if delta < 0:
        return "improved"
    if delta > 0:
        return "declined"
    return "stable"


class ExecutiveReportService:
    """Aggregates executive report data from multiple services."""

    def __init__(
        self,
        operator_url: str,
        timeout: float = 5.0,
    ) -> None:
        self.operator_url = operator_url.rstrip("/")
        self.timeout = timeout
        self._slo_service: SloService | None = None
        self._investigation_service: InvestigationService | None = None
        self._noise_report_service: NoiseReportService | None = None
        self._http_client: httpx.Client | None = None

    @property
    def slo_service(self) -> SloService:
        if self._slo_service is None:
            self._slo_service = SloService(
                operator_url=self.operator_url, timeout=self.timeout
            )
        return self._slo_service

    @property
    def investigation_service(self) -> InvestigationService:
        if self._investigation_service is None:
            self._investigation_service = InvestigationService(
                operator_url=self.operator_url, timeout=self.timeout
            )
        return self._investigation_service

    @property
    def noise_report_service(self) -> NoiseReportService:
        if self._noise_report_service is None:
            self._noise_report_service = NoiseReportService(
                host=os.getenv("QDRANT_HOST", "localhost"),
                port=int(os.getenv("QDRANT_PORT", "6333")),
            )
        return self._noise_report_service

    @property
    def http_client(self) -> httpx.Client:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.Client(timeout=self.timeout)
        return self._http_client

    def close(self) -> None:
        """Close all internal service clients."""
        if self._slo_service is not None:
            self._slo_service.close()
            self._slo_service = None
        if self._investigation_service is not None:
            self._investigation_service.close()
            self._investigation_service = None
        if self._noise_report_service is not None:
            self._noise_report_service.close()
            self._noise_report_service = None
        if self._http_client is not None and not self._http_client.is_closed:
            self._http_client.close()
            self._http_client = None

    def _get_trust_levels(self) -> list[dict[str, Any]]:
        """Fetch trust levels for all services from the trust API."""
        try:
            response = self.http_client.get(
                f"{self.operator_url}/api/v1/trust/services"
            )
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    return data
        except httpx.RequestError as e:
            logger.warning("Failed to fetch trust levels: %s", e)
        return []

    def _get_false_page_rate(self, period: str) -> float:
        """Get overall false page rate for the period.

        Args:
            period: Period string (30d, 90d, or all).

        Returns:
            False page rate as a float (0.0 if unavailable).
        """
        noise_period = "90d" if period == "all" else period
        if noise_period not in {"7d", "30d", "90d"}:
            noise_period = "90d"
        try:
            report = self.noise_report_service.build_noise_report(
                period=noise_period
            )
            return report.overall_false_page_rate
        except NoiseReportServiceError:
            return 0.0

    def get_report_data(
        self,
        period: str = "90d",
    ) -> dict[str, Any]:
        """Fetch and compute all executive report data.

        Args:
            period: Time period ("30d", "90d", "all").

        Returns:
            Dict with current_metrics, previous_metrics, comparison,
            period info, and date range.
        """
        period_days = _PERIOD_DAYS.get(period)

        # Fetch investigations
        try:
            investigations = self.investigation_service.list_investigations()
        except InvestigationServiceError:
            investigations = []

        # Fetch SLO services
        try:
            slo_services = self.slo_service.get_services()
        except SloServiceError:
            slo_services = []

        # Fetch trust levels
        trust_configs = self._get_trust_levels()

        # Get false page rate for current period
        current_fp_rate = self._get_false_page_rate(period)

        # Compute current period metrics
        current_metrics = compute_executive_metrics(
            investigations=investigations,
            slo_services=slo_services,
            trust_configs=trust_configs,
            false_page_rate=current_fp_rate,
            period_days=period_days,
        )

        # Compute previous period metrics for comparison
        previous_metrics: dict[str, Any] = {}
        comparison: dict[str, Any] = {}
        if period_days is not None:
            # For "all" period, skip comparison
            prev_period = f"{period_days * 2}d" if period_days <= 90 else "90d"
            prev_noise_period = "90d" if prev_period not in {"7d", "30d", "90d"} else prev_period
            prev_fp_rate = self._get_false_page_rate(prev_noise_period)

            previous_metrics = compute_executive_metrics(
                investigations=investigations,
                slo_services=slo_services,
                trust_configs=trust_configs,
                false_page_rate=prev_fp_rate,
                period_days=period_days * 2,
            )
            comparison = compute_period_comparison(current_metrics, previous_metrics)

        # Date range
        now = datetime.now(timezone.utc)
        if period_days:
            date_from = (now - timedelta(days=period_days)).strftime("%b %d, %Y")
        else:
            date_from = "Inception"
        date_to = now.strftime("%b %d, %Y")

        return {
            "current_metrics": current_metrics,
            "previous_metrics": previous_metrics,
            "comparison": comparison,
            "period": period,
            "period_label": _PERIOD_LABELS.get(period, period),
            "date_from": date_from,
            "date_to": date_to,
        }
