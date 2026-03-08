"""Metrics service for MTTR data aggregation and reporting."""

import csv
import io
import json
import logging
import os
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from qdrant_client import QdrantClient

logger = logging.getLogger(__name__)

INVESTIGATIONS_COLLECTION = "investigations"


class MetricsService:
    """Service for aggregating MTTR metrics from resolved investigations."""

    def __init__(self) -> None:
        self._qdrant_client: QdrantClient | None = None
        self._cached_points: list[dict[str, Any]] | None = None

    @property
    def qdrant_client(self) -> QdrantClient:
        """Get or create the Qdrant client (lazy initialization)."""
        if self._qdrant_client is None:
            host = os.getenv("QDRANT_HOST", "localhost")
            port = int(os.getenv("QDRANT_PORT", "6333"))
            self._qdrant_client = QdrantClient(host=host, port=port)
        return self._qdrant_client

    def close(self) -> None:
        """Close the Qdrant client."""
        if self._qdrant_client is not None:
            self._qdrant_client.close()
            self._qdrant_client = None

    def _scroll_resolved_investigations(self) -> list[dict[str, Any]]:
        """Scroll all investigations with MTTR data from Qdrant.

        Results are cached per service instance to avoid redundant Qdrant
        scrolls when multiple aggregation methods are called in one request.

        Returns:
            List of payload dicts for investigations with mttr_seconds set.
        """
        if self._cached_points is not None:
            return self._cached_points

        all_points: list[dict[str, Any]] = []
        offset = None
        while True:
            results, offset = self.qdrant_client.scroll(
                collection_name=INVESTIGATIONS_COLLECTION,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in results:
                payload: dict[str, Any] = dict(point.payload or {})
                if payload.get("mttr_seconds") is not None and payload.get(
                    "resolved_at"
                ):
                    all_points.append(payload)
            if offset is None:
                break
        self._cached_points = all_points
        return all_points

    @staticmethod
    def _bucket_key(resolved_at: str, period: str) -> str:
        """Generate a time bucket key for grouping.

        Args:
            resolved_at: ISO 8601 timestamp.
            period: One of 'week', 'month', 'quarter'.

        Returns:
            Bucket key string like '2026-W10', '2026-03', '2026-Q1'.
        """
        dt = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
        if period == "week":
            start = dt - timedelta(days=dt.weekday())
            return start.strftime("%Y-W%V")
        elif period == "quarter":
            q = (dt.month - 1) // 3 + 1
            return f"{dt.year}-Q{q}"
        return dt.strftime("%Y-%m")

    @staticmethod
    def _bucket_date_range(bucket_key: str, period: str) -> tuple[str, str]:
        """Get start and end ISO dates for a bucket key.

        Args:
            bucket_key: The bucket key string.
            period: One of 'week', 'month', 'quarter'.

        Returns:
            Tuple of (start_date, end_date) as ISO date strings.
        """
        if period == "week":
            year = int(bucket_key[:4])
            week = int(bucket_key.split("W")[1])
            jan4 = datetime(year, 1, 4)
            start_of_week1 = jan4 - timedelta(days=jan4.weekday())
            start = start_of_week1 + timedelta(weeks=week - 1)
            end = start + timedelta(days=6)
            return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        elif period == "quarter":
            year = int(bucket_key[:4])
            q = int(bucket_key[-1])
            start_month = (q - 1) * 3 + 1
            end_month = q * 3
            start = datetime(year, start_month, 1)
            if end_month == 12:
                end = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                end = datetime(year, end_month + 1, 1) - timedelta(days=1)
            return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        else:
            year = int(bucket_key[:4])
            month = int(bucket_key[5:7])
            start = datetime(year, month, 1)
            if month == 12:
                end = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                end = datetime(year, month + 1, 1) - timedelta(days=1)
            return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    def get_mttr_data(
        self,
        time_period: str = "month",
        service: str | None = None,
        severity: str | None = None,
    ) -> dict[str, Any]:
        """Get aggregated MTTR trend data.

        Args:
            time_period: Grouping period - 'week', 'month', or 'quarter'.
            service: Optional service name filter.
            severity: Optional severity level filter.

        Returns:
            Dict with trend data, improvement percentage, and summary stats.
        """
        all_points = self._scroll_resolved_investigations()

        if service:
            all_points = [p for p in all_points if p.get("service") == service]
        if severity:
            all_points = [
                p for p in all_points if p.get("severity") == severity
            ]

        if not all_points:
            return {
                "trend": [],
                "overall_avg_mttr": 0,
                "total_count": 0,
                "improvement_pct": None,
                "improving": None,
            }

        buckets: dict[str, list[int]] = defaultdict(list)
        for point in all_points:
            key = self._bucket_key(point["resolved_at"], time_period)
            buckets[key].append(int(point["mttr_seconds"]))

        trend_data: list[dict[str, Any]] = [
            {
                "period": key,
                "avg_mttr": sum(vals) // len(vals),
                "count": len(vals),
                "start": self._bucket_date_range(key, time_period)[0],
                "end": self._bucket_date_range(key, time_period)[1],
            }
            for key, vals in sorted(buckets.items())
        ]

        all_mttr = [int(p["mttr_seconds"]) for p in all_points]
        overall_avg = sum(all_mttr) // len(all_mttr)

        improvement_pct: float | None = None
        improving: bool | None = None
        if len(trend_data) >= 2:
            current = int(trend_data[-1]["avg_mttr"])
            previous = int(trend_data[-2]["avg_mttr"])
            if previous > 0:
                improvement_pct = round(
                    ((previous - current) / previous) * 100, 1
                )
                improving = improvement_pct > 0

        return {
            "trend": trend_data,
            "overall_avg_mttr": overall_avg,
            "total_count": len(all_points),
            "improvement_pct": improvement_pct,
            "improving": improving,
        }

    def get_mttr_by_service(self) -> list[dict[str, Any]]:
        """Get MTTR breakdown by service.

        Returns:
            List of dicts with service, avg_mttr, count.
        """
        all_points = self._scroll_resolved_investigations()

        service_buckets: dict[str, list[int]] = defaultdict(list)
        for point in all_points:
            svc = str(point.get("service", "unknown"))
            service_buckets[svc].append(int(point["mttr_seconds"]))

        return sorted(
            [
                {
                    "service": svc,
                    "avg_mttr": sum(vals) // len(vals),
                    "count": len(vals),
                }
                for svc, vals in service_buckets.items()
            ],
            key=lambda x: int(x["avg_mttr"]),
            reverse=True,
        )

    def get_mttr_by_severity(self) -> list[dict[str, Any]]:
        """Get MTTR breakdown by severity level.

        Returns:
            List of dicts with severity, avg_mttr, count.
        """
        all_points = self._scroll_resolved_investigations()

        severity_buckets: dict[str, list[int]] = defaultdict(list)
        for point in all_points:
            sev = str(point.get("severity", "unknown"))
            severity_buckets[sev].append(int(point["mttr_seconds"]))

        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return sorted(
            [
                {
                    "severity": sev,
                    "avg_mttr": sum(vals) // len(vals),
                    "count": len(vals),
                }
                for sev, vals in severity_buckets.items()
            ],
            key=lambda x: severity_order.get(str(x["severity"]), 99),
        )

    def get_investigations_for_period(
        self,
        start_date: str,
        end_date: str,
        service: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get resolved investigations for a specific time period.

        Args:
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            service: Optional service name filter.

        Returns:
            List of investigation dicts for drill-down display.
        """
        all_points = self._scroll_resolved_investigations()

        filtered: list[dict[str, Any]] = []
        for point in all_points:
            resolved_at = str(point.get("resolved_at", ""))
            resolved_date = resolved_at[:10]
            if start_date <= resolved_date <= end_date:
                if service and point.get("service") != service:
                    continue
                filtered.append(point)

        return sorted(
            filtered,
            key=lambda x: str(x.get("resolved_at", "")),
            reverse=True,
        )

    def get_services(self) -> list[str]:
        """Get list of distinct service names from resolved investigations.

        Returns:
            Sorted list of service names.
        """
        all_points = self._scroll_resolved_investigations()
        services = {str(p.get("service", "unknown")) for p in all_points}
        return sorted(services)

    def get_severities(self) -> list[str]:
        """Get list of distinct severity levels from resolved investigations.

        Returns:
            Sorted list of severity levels.
        """
        all_points = self._scroll_resolved_investigations()
        severities = {str(p.get("severity", "unknown")) for p in all_points}
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return sorted(severities, key=lambda x: severity_order.get(x, 99))

    def export_mttr_data(
        self, time_period: str = "month", fmt: str = "json"
    ) -> str | bytes:
        """Export MTTR data in JSON or CSV format.

        Args:
            time_period: Grouping period.
            fmt: Export format - 'json' or 'csv'.

        Returns:
            JSON string or CSV bytes.
        """
        mttr_data = self.get_mttr_data(time_period=time_period)
        by_service = self.get_mttr_by_service()
        by_severity = self.get_mttr_by_severity()

        if fmt == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["period", "avg_mttr_seconds", "count"])
            for row in mttr_data["trend"]:
                writer.writerow(
                    [row["period"], row["avg_mttr"], row["count"]]
                )
            return output.getvalue().encode("utf-8")

        export_data = {
            "period": time_period,
            "generated_at": datetime.now(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "trend": [
                {
                    "period": t["period"],
                    "avg_mttr_seconds": t["avg_mttr"],
                    "count": t["count"],
                }
                for t in mttr_data["trend"]
            ],
            "by_service": [
                {
                    "service": s["service"],
                    "avg_mttr_seconds": s["avg_mttr"],
                    "count": s["count"],
                }
                for s in by_service
            ],
            "by_severity": [
                {
                    "severity": s["severity"],
                    "avg_mttr_seconds": s["avg_mttr"],
                    "count": s["count"],
                }
                for s in by_severity
            ],
        }
        return json.dumps(export_data, indent=2)
