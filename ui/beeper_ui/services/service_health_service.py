"""Service health aggregation service.

Combines data from SLO, Investigation, and Trust Level services
to provide a unified per-service health view.
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

DEFAULT_RELIABILITY_THRESHOLD = 70
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_MAX_INCIDENTS = 10
DEFAULT_MAX_MTTR_HOURS = 24


def compute_reliability_score(
    compliance: float | None,
    investigations: list["Investigation"],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    threshold: int = DEFAULT_RELIABILITY_THRESHOLD,
    max_incidents: int = DEFAULT_MAX_INCIDENTS,
    max_mttr_hours: float = DEFAULT_MAX_MTTR_HOURS,
) -> dict[str, Any]:
    """Compute a 0-100 reliability score as a weighted composite.

    Components:
        - SLO compliance (40%): compliance * 100 * 0.4
        - Incident frequency trend (30%): fewer incidents = higher score
        - MTTR trend (30%): faster resolution = higher score

    Args:
        compliance: SLO compliance value (0.0-1.0), or None.
        investigations: List of Investigation objects for this service.
        lookback_days: Number of days to look back for frequency/MTTR.
        threshold: Score below which service is flagged.
        max_incidents: Number of incidents that yields 0 frequency score.
        max_mttr_hours: MTTR in hours that yields 0 MTTR score.

    Returns:
        Dict with score, trend, component breakdown, and threshold flag.
    """
    now = datetime.now(timezone.utc)
    lookback_start = now - timedelta(days=lookback_days)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    # SLO component (max 40 points)
    slo_component = (compliance if compliance is not None else 0.0) * 100 * 0.4

    # Parse investigation timestamps into lookback window
    def _parse_dt(ts: str | None) -> datetime | None:
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    lookback_investigations = []
    for inv in investigations:
        started = _parse_dt(inv.started_at)
        if started and started >= lookback_start:
            lookback_investigations.append(inv)

    # Incident frequency component (max 30 points)
    incident_count = len(lookback_investigations)
    frequency_component = max(0.0, 30.0 - (incident_count * 30.0 / max_incidents))

    # MTTR component (max 30 points)
    resolution_hours: list[float] = []
    for inv in lookback_investigations:
        if inv.status == "completed" and inv.completed_at and inv.started_at:
            started = _parse_dt(inv.started_at)
            completed = _parse_dt(inv.completed_at)
            if started and completed and completed > started:
                hours = (completed - started).total_seconds() / 3600
                resolution_hours.append(hours)

    if resolution_hours:
        avg_mttr = sum(resolution_hours) / len(resolution_hours)
        mttr_component = max(0.0, 30.0 - (avg_mttr * 30.0 / max_mttr_hours))
    else:
        mttr_component = 15.0  # neutral when no data

    score = round(slo_component + frequency_component + mttr_component)
    score = max(0, min(100, score))

    # Trend: compare current 7-day window vs previous 7-day window
    def _window_score(start: datetime, end: datetime) -> float | None:
        window_invs = []
        window_resolutions: list[float] = []
        for inv in investigations:
            s = _parse_dt(inv.started_at)
            if s and start <= s < end:
                window_invs.append(inv)
                if inv.status == "completed" and inv.completed_at:
                    c = _parse_dt(inv.completed_at)
                    if c and s and c > s:
                        window_resolutions.append(
                            (c - s).total_seconds() / 3600
                        )
        if not window_invs:
            return None
        w_freq = max(0.0, 30.0 - (len(window_invs) * 30.0 / max_incidents))
        if window_resolutions:
            w_mttr = max(
                0.0,
                30.0
                - (
                    sum(window_resolutions)
                    / len(window_resolutions)
                    * 30.0
                    / max_mttr_hours
                ),
            )
        else:
            w_mttr = 15.0
        return slo_component + w_freq + w_mttr

    current_window = _window_score(week_ago, now)
    previous_window = _window_score(two_weeks_ago, week_ago)

    if current_window is not None and previous_window is not None:
        diff = current_window - previous_window
        if diff > 5:
            trend = "improving"
        elif diff < -5:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "stable"

    below = score < threshold
    if score <= 40:
        score_class = "critical"
    elif below:
        score_class = "warning"
    else:
        score_class = "good"

    return {
        "score": score,
        "trend": trend,
        "slo_component": round(slo_component, 1),
        "frequency_component": round(frequency_component, 1),
        "mttr_component": round(mttr_component, 1),
        "below_threshold": below,
        "score_class": score_class,
    }


def compute_health_status(condition: str, active_count: int) -> str:
    """Compute overall health status from SLO condition and active investigation count.

    Args:
        condition: SLO condition (healthy/warning/critical/unknown).
        active_count: Number of active investigations.

    Returns:
        One of "critical", "warning", "healthy".
    """
    if condition == "critical" or active_count >= 3:
        return "critical"
    if condition == "warning" or active_count >= 1:
        return "warning"
    return "healthy"


class ServiceHealthService:
    """Aggregates per-service health data from SLO, Investigation, and Trust services."""

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

    def _get_trust_levels(self) -> dict[str, dict[str, Any]]:
        """Fetch trust levels for all services from the trust API.

        Returns:
            Dict mapping service_name to trust level info.
        """
        try:
            response = self.http_client.get(
                f"{self.operator_url}/api/v1/trust/services"
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    item["service_name"]: item
                    for item in data
                    if "service_name" in item
                }
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.warning("Failed to fetch trust levels: %s", e)
        return {}

    def _get_trust_level_for_service(self, name: str) -> int:
        """Fetch trust level for a specific service.

        Args:
            name: Service name.

        Returns:
            Trust level (1-5), defaults to 1.
        """
        try:
            response = self.http_client.get(
                f"{self.operator_url}/api/v1/trust/services/{name}"
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("trust_level", 1)
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.warning("Failed to fetch trust level for %s: %s", name, e)
        return 1

    def get_service_list(
        self,
        status_filter: str | None = None,
        sort_by: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all services with aggregated health data.

        Args:
            status_filter: Optional filter by health status (healthy/warning/critical).
            sort_by: Sort order — "reliability" for ascending reliability score,
                     default sorts by health status (critical first).

        Returns:
            List of service health dicts.
        """
        # Fetch SLO services
        try:
            slo_services = self.slo_service.get_services()
        except SloServiceError:
            slo_services = []

        # Fetch all investigations and group by service
        try:
            all_investigations = self.investigation_service.list_investigations()
        except InvestigationServiceError:
            all_investigations = []

        inv_by_service: dict[str, list[Investigation]] = {}
        for inv in all_investigations:
            inv_by_service.setdefault(inv.service, []).append(inv)

        # Fetch trust levels
        trust_levels = self._get_trust_levels()

        # Build aggregated service list
        services: list[dict[str, Any]] = []
        for svc in slo_services:
            name = svc.get("service", svc.get("name", ""))
            condition = svc.get("condition", "unknown")
            service_investigations = inv_by_service.get(name, [])
            active_investigations = [
                inv
                for inv in service_investigations
                if inv.status != "completed"
            ]
            active_count = len(active_investigations)

            trust_info = trust_levels.get(name, {})
            trust_level = trust_info.get("trust_level", 1)

            health_status = compute_health_status(condition, active_count)

            reliability = compute_reliability_score(
                compliance=svc.get("compliance"),
                investigations=service_investigations,
            )

            services.append(
                {
                    "name": name,
                    "slo_name": svc.get("name", ""),
                    "condition": condition,
                    "health_status": health_status,
                    "compliance": svc.get("compliance"),
                    "burn_rate": svc.get("burn_rate"),
                    "error_budget_remaining": svc.get("error_budget_remaining"),
                    "active_investigation_count": active_count,
                    "has_active_investigations": active_count > 0,
                    "trust_level": trust_level,
                    "is_frozen": svc.get("is_frozen", False),
                    "reliability_score": reliability,
                }
            )

        # Apply status filter
        if status_filter and status_filter in ("healthy", "warning", "critical"):
            services = [
                s for s in services if s["health_status"] == status_filter
            ]

        # Sort
        if sort_by == "reliability":
            services.sort(
                key=lambda s: s.get("reliability_score", {}).get("score", 0)
            )
        else:
            status_order = {"critical": 0, "warning": 1, "healthy": 2}
            services.sort(
                key=lambda s: status_order.get(s["health_status"], 3)
            )

        return services

    def get_service_detail(self, name: str) -> dict[str, Any] | None:
        """Get detailed health data for a specific service.

        Args:
            name: Service name.

        Returns:
            Unified service health dict, or None if service not found.
        """
        # Fetch SLO data — try by service name first
        slo_detail = None
        try:
            all_services = self.slo_service.get_services()
            for svc in all_services:
                if svc.get("service") == name or svc.get("name") == name:
                    slo_name = svc.get("name", name)
                    slo_detail = self.slo_service.get_service_detail(slo_name)
                    break
        except SloServiceError:
            pass

        if slo_detail is None:
            return None

        # Fetch error budget
        slo_name = slo_detail.get("name", name)
        budget = self.slo_service.get_service_budget(slo_name)

        # Fetch investigations for this service
        try:
            investigations = self.investigation_service.list_investigations(
                service=name
            )
        except InvestigationServiceError:
            investigations = []

        # Partition into active and recent resolved
        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)

        active: list[dict[str, Any]] = []
        recent_resolved: list[dict[str, Any]] = []

        for inv in investigations:
            inv_dict = {
                "id": inv.id,
                "status": inv.status,
                "service": inv.service,
                "severity": inv.severity,
                "condition": inv.condition,
                "started_at": inv.started_at,
                "completed_at": inv.completed_at,
                "workflow_state": inv.workflow_state,
            }
            if inv.status != "completed":
                active.append(inv_dict)
            elif inv.completed_at:
                try:
                    completed_dt = datetime.fromisoformat(
                        inv.completed_at.replace("Z", "+00:00")
                    )
                    if completed_dt >= seven_days_ago:
                        recent_resolved.append(inv_dict)
                except (ValueError, TypeError):
                    pass

        # Trust level
        trust_level = self._get_trust_level_for_service(name)

        condition = slo_detail.get("condition", "unknown")
        health_status = compute_health_status(condition, len(active))

        reliability = compute_reliability_score(
            compliance=slo_detail.get("compliance"),
            investigations=investigations,
        )

        return {
            "name": name,
            "slo_name": slo_name,
            "condition": condition,
            "health_status": health_status,
            "compliance": slo_detail.get("compliance"),
            "burn_rate": slo_detail.get("burn_rate"),
            "error_budget_remaining": budget.get("error_budget_remaining")
            if budget
            else None,
            "is_frozen": slo_detail.get("is_frozen", False),
            "trust_level": trust_level,
            "active_investigations": active,
            "recent_resolved": recent_resolved,
            "active_investigation_count": len(active),
            "slo_detail": slo_detail,
            "budget": budget,
            "reliability_score": reliability,
        }
