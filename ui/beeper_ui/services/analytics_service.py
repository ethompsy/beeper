"""Analytics service for MTTR, impact, and trust trend dashboards.

Aggregates data from Investigation, SLO, and Trust Level services
to compute trends over configurable time periods.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from beeper_ui.services.investigation_service import (
    Investigation,
    InvestigationService,
    InvestigationServiceError,
)
from beeper_ui.services.slo_service import SloService, SloServiceError

logger = logging.getLogger(__name__)


def _parse_dt(ts: str | None) -> datetime | None:
    """Parse ISO 8601 timestamp string to datetime."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def compute_mttr_trends(
    investigations: list[Investigation],
    num_weeks: int = 12,
) -> list[dict[str, Any]]:
    """Aggregate MTTR by ISO week for resolved investigations.

    Args:
        investigations: List of Investigation objects.
        num_weeks: Number of weeks to look back.

    Returns:
        Sorted list of weekly MTTR dicts with week, avg_mttr_hours, count.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(weeks=num_weeks)

    weeks: dict[str, list[float]] = {}
    for inv in investigations:
        if inv.status != "completed" or not inv.started_at or not inv.completed_at:
            continue
        started = _parse_dt(inv.started_at)
        completed = _parse_dt(inv.completed_at)
        if not started or not completed or started < cutoff or completed <= started:
            continue
        iso_year, iso_week, _ = started.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        hours = (completed - started).total_seconds() / 3600
        weeks.setdefault(week_key, []).append(hours)

    return sorted(
        [
            {
                "week": k,
                "avg_mttr_hours": round(sum(v) / len(v), 1),
                "count": len(v),
            }
            for k, v in weeks.items()
        ],
        key=lambda x: x["week"],
    )


def compute_mttr_trends_by_service(
    investigations: list[Investigation],
    num_weeks: int = 12,
) -> list[dict[str, Any]]:
    """Aggregate MTTR by service, each with weekly breakdown.

    Args:
        investigations: List of Investigation objects.
        num_weeks: Number of weeks to look back.

    Returns:
        List of dicts with service name and weekly MTTR data.
    """
    by_service: dict[str, list[Investigation]] = {}
    for inv in investigations:
        by_service.setdefault(inv.service, []).append(inv)

    result = []
    for service, invs in sorted(by_service.items()):
        weeks = compute_mttr_trends(invs, num_weeks)
        if weeks:
            result.append({"service": service, "weeks": weeks})
    return result


def compute_mttr_change_pct(
    trends: list[dict[str, Any]],
) -> float | None:
    """Compute percentage change in MTTR between oldest and newest week.

    Returns:
        Percentage change (negative = improvement), or None if insufficient data.
    """
    if len(trends) < 2:
        return None
    oldest = trends[0]["avg_mttr_hours"]
    newest = trends[-1]["avg_mttr_hours"]
    if oldest == 0:
        return None
    return round((newest - oldest) / oldest * 100, 1)


def compute_impact_trends(
    slo_services: list[dict[str, Any]],
    investigations: list[Investigation],
    num_weeks: int = 12,
) -> list[dict[str, Any]]:
    """Aggregate customer impact trends by week.

    Combines average SLO compliance (current snapshot, repeated per week for
    baseline) with weekly investigation counts.

    Args:
        slo_services: List of SLO service dicts with compliance field.
        investigations: List of Investigation objects.
        num_weeks: Number of weeks to look back.

    Returns:
        Sorted list of weekly impact dicts.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(weeks=num_weeks)

    # Current average SLO compliance across all services
    compliance_values = [
        s["compliance"]
        for s in slo_services
        if s.get("compliance") is not None
    ]
    avg_compliance = (
        round(sum(compliance_values) / len(compliance_values), 4)
        if compliance_values
        else None
    )

    # Count investigations per week
    week_counts: dict[str, int] = {}
    for inv in investigations:
        started = _parse_dt(inv.started_at)
        if started and started >= cutoff:
            iso_year, iso_week, _ = started.isocalendar()
            week_key = f"{iso_year}-W{iso_week:02d}"
            week_counts[week_key] = week_counts.get(week_key, 0) + 1

    # Build trend data for each week with investigations
    return sorted(
        [
            {
                "week": k,
                "investigation_count": v,
                "avg_compliance": avg_compliance,
            }
            for k, v in week_counts.items()
        ],
        key=lambda x: x["week"],
    )


def compute_trust_distribution(
    trust_configs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Count services at each trust level (TL1-TL5).

    Args:
        trust_configs: List of trust config dicts with trust_level field.

    Returns:
        Dict with levels (1-5 counts) and total.
    """
    levels: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for cfg in trust_configs:
        tl = cfg.get("trust_level", 1)
        if tl in levels:
            levels[tl] += 1
    return {"levels": levels, "total": sum(levels.values())}


def compute_trust_changes(
    trust_configs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract recent trust level changes (where previous_level is set).

    Args:
        trust_configs: List of trust config dicts.

    Returns:
        List of trust change dicts sorted by updated_at descending.
    """
    changes = []
    for cfg in trust_configs:
        prev = cfg.get("previous_level")
        if prev is not None:
            changes.append(
                {
                    "service": cfg.get("service_name", ""),
                    "from_level": prev,
                    "to_level": cfg.get("trust_level", 1),
                    "updated_at": cfg.get("updated_at", ""),
                    "reason": cfg.get("reason"),
                }
            )

    changes.sort(key=lambda x: x["updated_at"], reverse=True)
    return changes


class AnalyticsService:
    """Aggregates analytics dashboard data from multiple services."""

    def __init__(
        self,
        operator_url: str,
        timeout: float = 5.0,
    ) -> None:
        self.operator_url = operator_url.rstrip("/")
        self.timeout = timeout
        self._slo_service: SloService | None = None
        self._investigation_service: InvestigationService | None = None
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
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.warning("Failed to fetch trust levels: %s", e)
        return []

    def get_dashboard_data(
        self,
        period_weeks: int = 12,
        service_filter: str | None = None,
    ) -> dict[str, Any]:
        """Fetch and compute all analytics dashboard data.

        Args:
            period_weeks: Number of weeks to look back for trends.
            service_filter: Optional service name to filter MTTR/impact data.

        Returns:
            Dict with mttr_trends, mttr_change_pct, impact_trends,
            trust_distribution, trust_changes, and metadata.
        """
        # Fetch investigations
        try:
            if service_filter:
                investigations = self.investigation_service.list_investigations(
                    service=service_filter
                )
            else:
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

        # Compute trends
        mttr_trends = compute_mttr_trends(investigations, period_weeks)
        mttr_by_service = compute_mttr_trends_by_service(
            investigations, period_weeks
        )
        mttr_change = compute_mttr_change_pct(mttr_trends)
        impact_trends = compute_impact_trends(
            slo_services, investigations, period_weeks
        )
        trust_dist = compute_trust_distribution(trust_configs)
        trust_changes = compute_trust_changes(trust_configs)

        # Collect unique service names for filter dropdown
        service_names = sorted(
            {inv.service for inv in investigations} | {
                s.get("service", s.get("name", ""))
                for s in slo_services
            }
        )

        return {
            "mttr_trends": mttr_trends,
            "mttr_by_service": mttr_by_service,
            "mttr_change_pct": mttr_change,
            "impact_trends": impact_trends,
            "trust_distribution": trust_dist,
            "trust_changes": trust_changes,
            "service_names": service_names,
            "period_weeks": period_weeks,
            "service_filter": service_filter,
        }
