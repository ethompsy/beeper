"""Spending service for LLM cost aggregation and dashboard data."""

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
VALID_COST_PERIODS = {"week", "month", "quarter"}


class SpendingService:
    """Service for aggregating LLM spending data from investigations."""

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

    def _scroll_investigations_with_costs(self) -> list[dict[str, Any]]:
        """Scroll all investigations with cost data from Qdrant.

        Results are cached per service instance.

        Returns:
            List of payload dicts for investigations with cost_stats.
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
                if payload.get("cost_stats") and payload.get("created_at"):
                    all_points.append(payload)
            if offset is None:
                break
        self._cached_points = all_points
        return all_points

    def get_spending_summary(self) -> dict[str, Any]:
        """Get current spending summary with cap status.

        Returns:
            Dict with daily/monthly spend, caps, percentages, projections.
        """
        all_points = self._scroll_investigations_with_costs()
        now = datetime.now(UTC)
        today_str = now.strftime("%Y-%m-%d")
        month_str = now.strftime("%Y-%m")

        daily_cost = 0.0
        monthly_cost = 0.0
        daily_count = 0
        monthly_count = 0
        hour_ago = now - timedelta(hours=1)
        recent_count = 0

        for point in all_points:
            created_at = str(point.get("created_at", ""))
            cost_stats = point.get("cost_stats", {})
            cost = float(cost_stats.get("total_cost_usd", 0))

            if created_at[:10] == today_str:
                daily_cost += cost
                daily_count += 1

            if created_at[:7] == month_str:
                monthly_cost += cost
                monthly_count += 1

            try:
                created_dt = datetime.fromisoformat(
                    created_at.replace("Z", "+00:00")
                )
                if created_dt >= hour_ago:
                    recent_count += 1
            except (ValueError, TypeError):
                pass

        # Load caps from env
        daily_cap_cents = os.getenv("BEEPER_LLM_DAILY_CAP_CENTS")
        monthly_cap_cents = os.getenv("BEEPER_LLM_MONTHLY_CAP_CENTS")
        rate_limit = os.getenv("BEEPER_INVESTIGATION_RATE_LIMIT")

        daily_cap_usd = int(daily_cap_cents) / 100 if daily_cap_cents else None
        monthly_cap_usd = (
            int(monthly_cap_cents) / 100 if monthly_cap_cents else None
        )
        rate_limit_val = int(rate_limit) if rate_limit else None

        daily_pct = (
            (daily_cost / daily_cap_usd * 100) if daily_cap_usd else None
        )
        monthly_pct = (
            (monthly_cost / monthly_cap_usd * 100)
            if monthly_cap_usd
            else None
        )

        # Project monthly spend
        day_of_month = now.day
        days_in_month = 30  # approximation
        projected_monthly = (
            (monthly_cost / day_of_month * days_in_month)
            if day_of_month > 0
            else monthly_cost
        )

        return {
            "daily_cost_usd": round(daily_cost, 4),
            "monthly_cost_usd": round(monthly_cost, 4),
            "daily_cap_usd": daily_cap_usd,
            "monthly_cap_usd": monthly_cap_usd,
            "daily_pct": round(daily_pct, 1) if daily_pct is not None else None,
            "monthly_pct": (
                round(monthly_pct, 1) if monthly_pct is not None else None
            ),
            "projected_monthly_usd": round(projected_monthly, 4),
            "daily_investigation_count": daily_count,
            "monthly_investigation_count": monthly_count,
            "rate_per_hour": recent_count,
            "rate_limit": rate_limit_val,
        }

    def get_spending_trend(
        self, period: str = "daily"
    ) -> list[dict[str, Any]]:
        """Get spending trend data for chart rendering.

        Args:
            period: 'daily' or 'weekly' grouping.

        Returns:
            List of dicts with period label, cost, count.
        """
        all_points = self._scroll_investigations_with_costs()

        buckets: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"cost": 0.0, "count": 0}
        )

        for point in all_points:
            created_at = str(point.get("created_at", ""))
            cost_stats = point.get("cost_stats", {})
            cost = float(cost_stats.get("total_cost_usd", 0))

            if period == "weekly":
                try:
                    dt = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )
                    start = dt - timedelta(days=dt.weekday())
                    key = start.strftime("%Y-W%V")
                except (ValueError, TypeError):
                    continue
            else:
                key = created_at[:10]  # YYYY-MM-DD

            if key:
                buckets[key]["cost"] += cost
                buckets[key]["count"] += 1

        return [
            {
                "period": key,
                "cost_usd": round(data["cost"], 4),
                "count": data["count"],
            }
            for key, data in sorted(buckets.items())
        ]

    def get_cap_status(self) -> dict[str, Any]:
        """Get cap enforcement status.

        Returns:
            Dict with enforcement state and warnings.
        """
        summary = self.get_spending_summary()
        warnings: list[str] = []
        enforcement_active = False

        if summary["daily_pct"] is not None and summary["daily_pct"] >= 100:
            enforcement_active = True
            warnings.append(
                f"Daily cap reached: ${summary['daily_cost_usd']:.2f}"
                f" / ${summary['daily_cap_usd']:.2f}"
            )
        elif summary["daily_pct"] is not None and summary["daily_pct"] >= 80:
            warnings.append(
                f"Daily spend at {summary['daily_pct']:.0f}% of cap"
            )

        if (
            summary["monthly_pct"] is not None
            and summary["monthly_pct"] >= 100
        ):
            enforcement_active = True
            warnings.append(
                f"Monthly cap reached: ${summary['monthly_cost_usd']:.2f}"
                f" / ${summary['monthly_cap_usd']:.2f}"
            )
        elif (
            summary["monthly_pct"] is not None
            and summary["monthly_pct"] >= 80
        ):
            warnings.append(
                f"Monthly spend at {summary['monthly_pct']:.0f}% of cap"
            )

        caps_configured = (
            summary["daily_cap_usd"] is not None
            or summary["monthly_cap_usd"] is not None
        )

        return {
            "enforcement_active": enforcement_active,
            "caps_configured": caps_configured,
            "warnings": warnings,
        }

    def _filter_by_period(
        self, points: list[dict[str, Any]], period: str = "month"
    ) -> list[dict[str, Any]]:
        """Filter investigation points by time period.

        Args:
            points: List of investigation payload dicts.
            period: 'week', 'month', or 'quarter'.

        Returns:
            Filtered list of points within the period.
        """
        now = datetime.now(UTC)
        if period == "week":
            cutoff = now - timedelta(days=7)
        elif period == "quarter":
            cutoff = now - timedelta(days=90)
        else:
            cutoff = now - timedelta(days=30)

        filtered = []
        for point in points:
            created_at = str(point.get("created_at", ""))
            try:
                dt = datetime.fromisoformat(
                    created_at.replace("Z", "+00:00")
                )
                if dt >= cutoff:
                    filtered.append(point)
            except (ValueError, TypeError):
                continue
        return filtered

    def get_cost_by_service(
        self, period: str = "month"
    ) -> list[dict[str, Any]]:
        """Get cost breakdown by service.

        Args:
            period: Time period filter ('week', 'month', 'quarter').

        Returns:
            List of dicts sorted by total_cost descending.
        """
        all_points = self._scroll_investigations_with_costs()
        filtered = self._filter_by_period(all_points, period)

        service_data: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "total_cost": 0.0,
                "count": 0,
                "models": defaultdict(
                    lambda: {"cost": 0.0, "calls": 0}
                ),
            }
        )

        for point in filtered:
            service = str(point.get("service", "unknown"))
            cost_stats = point.get("cost_stats", {})
            cost = float(cost_stats.get("total_cost_usd", 0))
            service_data[service]["total_cost"] += cost
            service_data[service]["count"] += 1

            per_model = cost_stats.get("per_model", {})
            if isinstance(per_model, dict):
                for model, mdata in per_model.items():
                    if isinstance(mdata, dict):
                        service_data[service]["models"][model][
                            "cost"
                        ] += float(mdata.get("cost_usd", 0))
                        service_data[service]["models"][model][
                            "calls"
                        ] += int(mdata.get("calls", 0))

        result = []
        for service, data in service_data.items():
            count = data["count"]
            total = data["total_cost"]
            result.append({
                "service": service,
                "total_cost_usd": round(total, 4),
                "investigation_count": count,
                "cost_per_investigation": (
                    round(total / count, 4) if count > 0 else 0
                ),
                "model_breakdown": {
                    m: {
                        "cost_usd": round(md["cost"], 4),
                        "calls": md["calls"],
                    }
                    for m, md in data["models"].items()
                },
            })

        result.sort(
            key=lambda x: float(x["total_cost_usd"]), reverse=True
        )
        return result

    def get_cost_by_severity(
        self, period: str = "month"
    ) -> list[dict[str, Any]]:
        """Get cost breakdown by severity.

        Args:
            period: Time period filter ('week', 'month', 'quarter').

        Returns:
            List of dicts sorted by total_cost descending.
        """
        all_points = self._scroll_investigations_with_costs()
        filtered = self._filter_by_period(all_points, period)

        severity_data: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"total_cost": 0.0, "count": 0}
        )

        for point in filtered:
            severity = str(point.get("severity", "unknown"))
            cost_stats = point.get("cost_stats", {})
            cost = float(cost_stats.get("total_cost_usd", 0))
            severity_data[severity]["total_cost"] += cost
            severity_data[severity]["count"] += 1

        result: list[dict[str, Any]] = []
        for severity, data in severity_data.items():
            count = int(data["count"])
            total = float(data["total_cost"])
            result.append({
                "severity": severity,
                "total_cost_usd": round(total, 4),
                "investigation_count": count,
                "cost_per_investigation": (
                    round(total / count, 4) if count > 0 else 0
                ),
            })

        result.sort(
            key=lambda x: float(x["total_cost_usd"]), reverse=True
        )
        return result

    def get_cost_by_model(
        self, period: str = "month"
    ) -> list[dict[str, Any]]:
        """Get cost breakdown by LLM model.

        Args:
            period: Time period filter ('week', 'month', 'quarter').

        Returns:
            List of dicts sorted by total_cost descending.
        """
        all_points = self._scroll_investigations_with_costs()
        filtered = self._filter_by_period(all_points, period)

        model_data: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "total_cost": 0.0,
                "call_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
            }
        )

        for point in filtered:
            cost_stats = point.get("cost_stats", {})
            per_model = cost_stats.get("per_model", {})
            if not isinstance(per_model, dict):
                continue
            for model, mdata in per_model.items():
                if not isinstance(mdata, dict):
                    continue
                model_data[model]["total_cost"] += float(
                    mdata.get("cost_usd", 0)
                )
                model_data[model]["call_count"] += int(
                    mdata.get("calls", 0)
                )
                model_data[model]["prompt_tokens"] += int(
                    mdata.get("prompt_tokens", 0)
                )
                model_data[model]["completion_tokens"] += int(
                    mdata.get("completion_tokens", 0)
                )

        result = [
            {
                "model": model,
                "total_cost_usd": round(data["total_cost"], 4),
                "call_count": data["call_count"],
                "total_prompt_tokens": data["prompt_tokens"],
                "total_completion_tokens": data["completion_tokens"],
            }
            for model, data in model_data.items()
        ]

        result.sort(
            key=lambda x: float(x["total_cost_usd"]), reverse=True
        )
        return result

    def get_high_cost_services(
        self, threshold_multiplier: float | None = None
    ) -> list[dict[str, Any]]:
        """Identify services with costs exceeding threshold.

        Args:
            threshold_multiplier: Flag services above this multiple of
                average. Defaults to BEEPER_COST_HIGH_THRESHOLD_MULTIPLIER
                env var or 2.0.

        Returns:
            List of flagged service dicts with recommendations.
        """
        if threshold_multiplier is None:
            try:
                threshold_multiplier = float(
                    os.getenv(
                        "BEEPER_COST_HIGH_THRESHOLD_MULTIPLIER", "2.0"
                    )
                )
            except (ValueError, TypeError):
                threshold_multiplier = 2.0

        by_service = self.get_cost_by_service()
        if len(by_service) < 2:
            return []

        avg_cost = sum(
            s["total_cost_usd"] for s in by_service
        ) / len(by_service)
        threshold = avg_cost * threshold_multiplier

        # Get trend data for each service
        all_points = self._scroll_investigations_with_costs()
        now = datetime.now(UTC)
        mid = now - timedelta(days=15)

        flagged = []
        for svc in by_service:
            if svc["total_cost_usd"] <= threshold:
                continue

            multiplier = (
                svc["total_cost_usd"] / avg_cost if avg_cost > 0 else 0
            )

            # Calculate trend
            trend = self._calculate_service_trend(
                svc["service"], all_points, mid, now
            )

            recommendation = (
                f"{svc['service']} generated "
                f"${svc['total_cost_usd']:.2f} in LLM costs "
                f"({multiplier:.1f}x average) \u2014 consider tuning "
                f"anomaly detection thresholds or excluding noisy "
                f"log patterns"
            )

            flagged.append({
                "service": svc["service"],
                "total_cost_usd": svc["total_cost_usd"],
                "average_cost_usd": round(avg_cost, 4),
                "multiplier": round(multiplier, 1),
                "investigation_count": svc["investigation_count"],
                "cost_per_investigation": svc["cost_per_investigation"],
                "trend": trend,
                "recommendation": recommendation,
            })

        return flagged

    def _calculate_service_trend(
        self,
        service: str,
        all_points: list[dict[str, Any]],
        midpoint: datetime,
        now: datetime,
    ) -> str:
        """Calculate cost trend for a service (increasing/stable/decreasing).

        Compares cost in recent half to earlier half of the data window.
        """
        cutoff = midpoint - timedelta(days=15)
        earlier_cost = 0.0
        recent_cost = 0.0

        for point in all_points:
            if str(point.get("service", "")) != service:
                continue
            created_at = str(point.get("created_at", ""))
            cost = float(
                point.get("cost_stats", {}).get("total_cost_usd", 0)
            )
            try:
                dt = datetime.fromisoformat(
                    created_at.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                continue
            if cutoff <= dt < midpoint:
                earlier_cost += cost
            elif midpoint <= dt <= now:
                recent_cost += cost

        if earlier_cost == 0:
            return "stable"
        change_pct = ((recent_cost - earlier_cost) / earlier_cost) * 100
        if change_pct > 10:
            return "increasing"
        elif change_pct < -10:
            return "decreasing"
        return "stable"

    def export_cost_data(
        self, period: str = "month", fmt: str = "json"
    ) -> str | bytes:
        """Export cost breakdown data as JSON or CSV.

        Args:
            period: Time period for data.
            fmt: 'json' or 'csv'.

        Returns:
            JSON string or CSV bytes.
        """
        by_service = self.get_cost_by_service(period=period)
        by_severity = self.get_cost_by_severity(period=period)
        by_model = self.get_cost_by_model(period=period)
        high_cost = self.get_high_cost_services()

        if fmt == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "service",
                "total_cost_usd",
                "investigation_count",
                "cost_per_investigation",
            ])
            for svc in by_service:
                writer.writerow([
                    svc["service"],
                    svc["total_cost_usd"],
                    svc["investigation_count"],
                    svc["cost_per_investigation"],
                ])
            return output.getvalue().encode("utf-8")

        data = {
            "period": period,
            "generated_at": datetime.now(UTC).isoformat(),
            "by_service": by_service,
            "by_severity": by_severity,
            "by_model": by_model,
            "high_cost_services": [
                {
                    "service": h["service"],
                    "total_cost_usd": h["total_cost_usd"],
                    "multiplier": h["multiplier"],
                    "recommendation": h["recommendation"],
                }
                for h in high_cost
            ],
        }
        return json.dumps(data, indent=2)
