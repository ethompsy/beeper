"""Handoff service for generating shift handoff summaries."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from beeper_ui.services.investigation_service import (
    Investigation,
    InvestigationService,
    InvestigationServiceError,
)
from beeper_ui.services.slo_service import SloService, SloServiceError

logger = logging.getLogger(__name__)

# Investigations resolved within this window appear in handoff
RESOLVED_WINDOW_HOURS = 8


@dataclass
class HandoffSummary:
    """Shift handoff summary with SBAR-structured data."""

    active_investigations: list[dict[str, Any]] = field(default_factory=list)
    resolved_incidents: list[dict[str, Any]] = field(default_factory=list)
    slo_status: list[dict[str, Any]] = field(default_factory=list)
    items_to_watch: list[dict[str, Any]] = field(default_factory=list)
    generated_at: str = ""
    is_all_clear: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize summary to dict for JSON endpoint."""
        return {
            "active_investigations": self.active_investigations,
            "resolved_incidents": self.resolved_incidents,
            "slo_status": self.slo_status,
            "items_to_watch": self.items_to_watch,
            "generated_at": self.generated_at,
            "is_all_clear": self.is_all_clear,
        }


class HandoffService:
    """Aggregation service for shift handoff summaries.

    Composes InvestigationService and SloService to produce a unified
    handoff view.  Each external call is wrapped so a single service
    failure does not prevent the rest of the summary from being built.
    """

    def __init__(self, operator_url: str, timeout: float = 5.0) -> None:
        self.operator_url = operator_url
        self.timeout = timeout
        self._inv_svc: InvestigationService | None = None
        self._slo_svc: SloService | None = None

    @property
    def _investigation_service(self) -> InvestigationService:
        if self._inv_svc is None:
            self._inv_svc = InvestigationService(
                self.operator_url, self.timeout
            )
        return self._inv_svc

    @property
    def _slo_service(self) -> SloService:
        if self._slo_svc is None:
            self._slo_svc = SloService(self.operator_url, self.timeout)
        return self._slo_svc

    def close(self) -> None:
        """Close underlying service clients."""
        try:
            if self._inv_svc is not None:
                self._inv_svc.close()
                self._inv_svc = None
        finally:
            if self._slo_svc is not None:
                self._slo_svc.close()
                self._slo_svc = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_summary(self) -> HandoffSummary:
        """Build a complete shift handoff summary.

        Failures in one data source do not prevent the others from
        populating — the summary degrades gracefully.
        """
        now = datetime.now(timezone.utc)

        # Fetch investigations (graceful degradation)
        investigations: list[Investigation] = []
        try:
            investigations = self._investigation_service.list_investigations()
        except InvestigationServiceError:
            logger.warning(
                "Failed to fetch investigations for handoff",
                exc_info=True,
            )

        active = self._build_active_investigations(investigations)
        resolved = self._build_resolved_incidents(investigations, now)

        # Fetch SLO data (graceful degradation)
        slo_services: list[dict[str, Any]] = []
        try:
            slo_services = self._slo_service.get_services()
        except SloServiceError:
            logger.warning(
                "Failed to fetch SLO data for handoff", exc_info=True
            )

        slo_status = self._build_slo_status(slo_services)
        items_to_watch = self._build_items_to_watch(slo_services, active)

        is_all_clear = len(active) == 0 and len(resolved) == 0

        return HandoffSummary(
            active_investigations=active,
            resolved_incidents=resolved,
            slo_status=slo_status,
            items_to_watch=items_to_watch,
            generated_at=now.isoformat(),
            is_all_clear=is_all_clear,
        )

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_active_investigations(
        investigations: list[Investigation],
    ) -> list[dict[str, Any]]:
        """Extract active investigations (investigating / awaiting_confirmation)."""
        active_statuses = {"investigating", "awaiting_confirmation"}
        return [
            {
                "id": inv.id,
                "service": inv.service,
                "severity": inv.severity,
                "status": inv.status,
                "condition": inv.condition,
                "started_at": inv.started_at,
                "link": f"/investigations/{inv.id}",
            }
            for inv in investigations
            if inv.status in active_statuses
        ]

    @staticmethod
    def _build_resolved_incidents(
        investigations: list[Investigation],
        now: datetime,
    ) -> list[dict[str, Any]]:
        """Filter to completed investigations within the past 8 hours."""
        cutoff = now.timestamp() - RESOLVED_WINDOW_HOURS * 3600
        resolved: list[dict[str, Any]] = []
        for inv in investigations:
            if inv.status != "completed" or not inv.completed_at:
                continue
            try:
                completed_ts = datetime.fromisoformat(
                    inv.completed_at
                ).timestamp()
            except (ValueError, TypeError):
                continue
            if completed_ts < cutoff:
                continue
            resolved.append(
                {
                    "id": inv.id,
                    "service": inv.service,
                    "severity": inv.severity,
                    "condition": inv.condition,
                    "started_at": inv.started_at,
                    "completed_at": inv.completed_at,
                    "link": f"/investigations/{inv.id}",
                }
            )

        # Most recent first
        resolved.sort(key=lambda r: r["completed_at"], reverse=True)
        return resolved

    @staticmethod
    def _build_slo_status(
        services: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Map SLO services to handoff summary format."""
        return [
            {
                "name": svc.get("name", "unknown"),
                "condition": svc.get("condition", "unknown"),
                "compliance": svc.get("compliance"),
                "burn_rate": svc.get("burn_rate"),
                "link": f"/slo/services/{svc.get('name', 'unknown')}",
            }
            for svc in services
        ]

    @staticmethod
    def _build_items_to_watch(
        services: list[dict[str, Any]],
        active_investigations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Identify items requiring incoming-shift attention."""
        items: list[dict[str, Any]] = []

        # SLO services in warning / critical state
        for svc in services:
            condition = svc.get("condition", "")
            burn_rate = svc.get("burn_rate")
            name = svc.get("name", "unknown")

            if condition in ("warning", "critical"):
                items.append(
                    {
                        "type": "slo",
                        "description": f"{name} SLO is {condition}",
                        "severity": condition,
                        "link": f"/slo/services/{name}",
                    }
                )
            elif burn_rate is not None and burn_rate > 1.0:
                items.append(
                    {
                        "type": "slo",
                        "description": (
                            f"{name} burn rate elevated ({burn_rate:.1f}x)"
                        ),
                        "severity": "warning",
                        "link": f"/slo/services/{name}",
                    }
                )

        # Active investigations that are awaiting action
        for inv in active_investigations:
            if inv["status"] == "awaiting_confirmation":
                items.append(
                    {
                        "type": "investigation",
                        "description": (
                            f"{inv['service']} investigation awaiting confirmation"
                        ),
                        "severity": inv["severity"],
                        "link": inv["link"],
                    }
                )

        return items
