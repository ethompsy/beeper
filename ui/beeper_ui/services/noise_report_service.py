"""Noise Report Dashboard service.

Aggregates investigation feedback and false page data across all services
to produce signal-to-noise ratios, false page rates, per-service breakdowns,
and false page rate trends over time.

Read-only service — no writes to any Qdrant collection.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    Range,
)

logger = logging.getLogger(__name__)

INVESTIGATIONS_COLLECTION = "investigations"
AUDIT_COLLECTION = "notification_audit"

VALID_PERIODS = {"7d", "30d", "90d"}

PERIOD_CONFIG: dict[str, dict[str, Any]] = {
    "7d": {"days": 7, "buckets": 7, "label_format": "%b %d"},
    "30d": {"days": 30, "buckets": 6, "label_format": "%b %d"},
    "90d": {"days": 90, "buckets": 6, "label_format": "%b %d"},
}

VALID_FEEDBACK_TYPES = {"accurate", "inaccurate", "not_an_issue"}


class NoiseReportServiceError(Exception):
    """Exception raised by noise report service operations."""


@dataclass
class ServiceNoiseStats:
    """Per-service noise metrics."""

    service_name: str
    total_investigations: int
    accurate_count: int
    inaccurate_count: int
    not_an_issue_count: int
    signal_to_noise_ratio: float
    false_page_count: int
    total_notifications: int
    false_page_rate: float
    is_worst_performer: bool = False


@dataclass
class NoiseReportData:
    """Complete noise report data container."""

    overall_signal_to_noise: float
    overall_false_page_rate: float
    total_investigations_with_feedback: int
    total_notifications: int
    total_false_pages: int
    per_service: list[ServiceNoiseStats] = field(default_factory=list)
    trend_data: list[dict[str, Any]] = field(default_factory=list)
    selected_service: str | None = None
    selected_period: str = "30d"


class NoiseReportService:
    """Aggregates investigation feedback and false page data for noise reporting.

    Reads from existing ``investigations`` and ``notification_audit``
    Qdrant collections. No write operations.
    """

    def __init__(self, host: str | None = None, port: int = 6333) -> None:
        self._host = host
        self._port = port
        self._client: QdrantClient | None = None

    @property
    def client(self) -> QdrantClient:
        """Lazy-initialize Qdrant client."""
        if self._client is None:
            self._client = QdrantClient(host=self._host, port=self._port)
        return self._client

    def close(self) -> None:
        """Close the Qdrant client connection."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def get_all_service_feedback(
        self, service_filter: str | None = None
    ) -> dict[str, dict[str, int]]:
        """Aggregate investigation feedback grouped by service.

        Args:
            service_filter: Optional single service to filter by.

        Returns:
            Dict mapping service_name -> {total, accurate, inaccurate, not_an_issue}.

        Raises:
            NoiseReportServiceError: On Qdrant communication failure.
        """
        try:
            per_service: dict[str, dict[str, int]] = {}
            scroll_filter = None
            if service_filter:
                scroll_filter = Filter(
                    must=[
                        FieldCondition(
                            key="service",
                            match=MatchValue(value=service_filter),
                        )
                    ]
                )

            offset = None
            while True:
                results, offset = self.client.scroll(
                    collection_name=INVESTIGATIONS_COLLECTION,
                    scroll_filter=scroll_filter,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                for point in results:
                    payload = point.payload or {}
                    svc_name = payload.get("service")
                    feedback = payload.get("investigation_feedback")
                    if not svc_name or not feedback:
                        continue
                    if feedback not in VALID_FEEDBACK_TYPES:
                        continue
                    if svc_name not in per_service:
                        per_service[svc_name] = {
                            "total": 0,
                            "accurate": 0,
                            "inaccurate": 0,
                            "not_an_issue": 0,
                        }
                    per_service[svc_name][feedback] += 1
                    per_service[svc_name]["total"] += 1
                if offset is None:
                    break
            return per_service
        except Exception as e:
            msg = f"Failed to get service feedback: {e}"
            logger.warning(msg)
            raise NoiseReportServiceError(msg) from e

    def get_false_page_stats(
        self,
        service: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Get false page statistics per service from notification_audit collection.

        Args:
            service: Optional service filter.
            date_from: ISO 8601 start date.
            date_to: ISO 8601 end date.

        Returns:
            Dict mapping service_name -> {total_notifications, false_page_count, false_page_rate}.

        Raises:
            NoiseReportServiceError: On Qdrant communication failure.
        """
        try:
            per_service: dict[str, dict[str, Any]] = {}
            conditions: list[FieldCondition] = []

            if service:
                conditions.append(
                    FieldCondition(
                        key="service",
                        match=MatchValue(value=service),
                    )
                )
            if date_from is not None or date_to is not None:
                range_params: dict[str, Any] = {}
                if date_from is not None:
                    range_params["gte"] = _iso_to_epoch(date_from)
                if date_to is not None:
                    range_params["lte"] = _iso_to_epoch(date_to)
                if range_params:
                    conditions.append(
                        FieldCondition(
                            key="timestamp_epoch",
                            range=Range(**range_params),
                        )
                    )

            scroll_filter = Filter(must=conditions) if conditions else None

            offset = None
            while True:
                results, offset = self.client.scroll(
                    collection_name=AUDIT_COLLECTION,
                    scroll_filter=scroll_filter,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                for point in results:
                    payload = point.payload or {}
                    svc_name = payload.get("service")
                    if not svc_name:
                        continue
                    if svc_name not in per_service:
                        per_service[svc_name] = {
                            "total_notifications": 0,
                            "false_page_count": 0,
                            "false_page_rate": 0.0,
                        }
                    per_service[svc_name]["total_notifications"] += 1
                    if payload.get("is_false_page") is True:
                        per_service[svc_name]["false_page_count"] += 1
                if offset is None:
                    break

            # Compute rates
            for stats in per_service.values():
                total = stats["total_notifications"]
                if total > 0:
                    stats["false_page_rate"] = round(
                        stats["false_page_count"] / total, 4
                    )

            return per_service
        except Exception as e:
            msg = f"Failed to get false page stats: {e}"
            logger.warning(msg)
            raise NoiseReportServiceError(msg) from e

    def get_false_page_trend(
        self,
        service: str | None = None,
        period: str = "30d",
    ) -> list[dict[str, Any]]:
        """Get false page rate trend data over time buckets.

        Args:
            service: Optional service filter.
            period: Time period ("7d", "30d", "90d").

        Returns:
            List of {period_label, false_page_rate, total, false_page_count} dicts.

        Raises:
            NoiseReportServiceError: On Qdrant communication failure.
        """
        config = PERIOD_CONFIG.get(period, PERIOD_CONFIG["30d"])
        days = config["days"]
        buckets = config["buckets"]
        label_format = config["label_format"]

        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days)
        bucket_size = timedelta(days=days / buckets)

        trend: list[dict[str, Any]] = []
        try:
            for i in range(buckets):
                bucket_start = start + (bucket_size * i)
                bucket_end = start + (bucket_size * (i + 1))

                conditions: list[FieldCondition] = [
                    FieldCondition(
                        key="timestamp_epoch",
                        range=Range(
                            gte=bucket_start.timestamp(),
                            lte=bucket_end.timestamp(),
                        ),
                    )
                ]
                if service:
                    conditions.append(
                        FieldCondition(
                            key="service",
                            match=MatchValue(value=service),
                        )
                    )

                scroll_filter = Filter(must=conditions)
                total = 0
                false_pages = 0

                scroll_offset = None
                while True:
                    results, scroll_offset = self.client.scroll(
                        collection_name=AUDIT_COLLECTION,
                        scroll_filter=scroll_filter,
                        limit=100,
                        offset=scroll_offset,
                        with_payload=True,
                        with_vectors=False,
                    )
                    for point in results:
                        total += 1
                        payload = point.payload or {}
                        if payload.get("is_false_page") is True:
                            false_pages += 1
                    if scroll_offset is None:
                        break

                rate = round(false_pages / total, 4) if total > 0 else 0.0
                trend.append(
                    {
                        "period_label": bucket_start.strftime(label_format),
                        "false_page_rate": rate,
                        "total": total,
                        "false_page_count": false_pages,
                    }
                )

            return trend
        except Exception as e:
            msg = f"Failed to get false page trend: {e}"
            logger.warning(msg)
            raise NoiseReportServiceError(msg) from e

    def build_noise_report(
        self,
        service: str | None = None,
        period: str = "30d",
    ) -> NoiseReportData:
        """Build complete noise report by aggregating feedback and audit data.

        Args:
            service: Optional service filter.
            period: Time period for trend data.

        Returns:
            NoiseReportData with all metrics computed.

        Raises:
            NoiseReportServiceError: On data access failure.
        """
        now = datetime.now(timezone.utc)
        config = PERIOD_CONFIG.get(period, PERIOD_CONFIG["30d"])
        date_from = (now - timedelta(days=config["days"])).isoformat()
        date_to = now.isoformat()

        # Get investigation feedback per service
        feedback_by_service = self.get_all_service_feedback(
            service_filter=service
        )

        # Get false page stats per service
        fp_by_service = self.get_false_page_stats(
            service=service, date_from=date_from, date_to=date_to
        )

        # Get trend data
        trend_data = self.get_false_page_trend(
            service=service, period=period
        )

        # Merge into per-service stats
        all_services = set(feedback_by_service.keys()) | set(
            fp_by_service.keys()
        )
        per_service_stats: list[ServiceNoiseStats] = []

        total_accurate = 0
        total_feedback = 0
        total_notif = 0
        total_fp = 0

        for svc_name in sorted(all_services):
            fb = feedback_by_service.get(
                svc_name,
                {"total": 0, "accurate": 0, "inaccurate": 0, "not_an_issue": 0},
            )
            fp = fp_by_service.get(
                svc_name,
                {"total_notifications": 0, "false_page_count": 0, "false_page_rate": 0.0},
            )

            sn_ratio = _compute_signal_to_noise(fb["accurate"], fb["total"])

            stats = ServiceNoiseStats(
                service_name=svc_name,
                total_investigations=fb["total"],
                accurate_count=fb["accurate"],
                inaccurate_count=fb["inaccurate"],
                not_an_issue_count=fb["not_an_issue"],
                signal_to_noise_ratio=sn_ratio,
                false_page_count=fp["false_page_count"],
                total_notifications=fp["total_notifications"],
                false_page_rate=fp["false_page_rate"],
            )
            per_service_stats.append(stats)

            total_accurate += fb["accurate"]
            total_feedback += fb["total"]
            total_notif += fp["total_notifications"]
            total_fp += fp["false_page_count"]

        # Mark worst performers
        _mark_worst_performers(per_service_stats)

        overall_sn = _compute_signal_to_noise(total_accurate, total_feedback)
        overall_fp_rate = round(total_fp / total_notif, 4) if total_notif > 0 else 0.0

        return NoiseReportData(
            overall_signal_to_noise=overall_sn,
            overall_false_page_rate=overall_fp_rate,
            total_investigations_with_feedback=total_feedback,
            total_notifications=total_notif,
            total_false_pages=total_fp,
            per_service=per_service_stats,
            trend_data=trend_data,
            selected_service=service,
            selected_period=period,
        )


def _compute_signal_to_noise(accurate: int, total: int) -> float:
    """Compute signal-to-noise ratio.

    Returns:
        Float between 0.0 and 1.0 (accurate / total), or 0.0 if no data.
    """
    if total == 0:
        return 0.0
    return round(accurate / total, 4)


def _mark_worst_performers(stats: list[ServiceNoiseStats]) -> None:
    """Mark services with highest false page rate as worst performers.

    Strategy: services with false_page_rate > 2x the average are marked,
    provided they have at least 1 notification.
    """
    rates = [
        s.false_page_rate
        for s in stats
        if s.total_notifications > 0
    ]
    if not rates:
        return

    avg_rate = sum(rates) / len(rates)
    threshold = avg_rate * 2.0

    for s in stats:
        if s.total_notifications > 0 and s.false_page_rate > threshold:
            s.is_worst_performer = True


def _iso_to_epoch(iso_str: str) -> float:
    """Convert ISO 8601 timestamp string to epoch float."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.timestamp()
    except (ValueError, AttributeError):
        logger.warning("Failed to parse ISO timestamp: %s", iso_str)
        return 0.0
