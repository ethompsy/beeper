"""Spending service for LLM cost aggregation and dashboard data."""

import logging
import os
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from qdrant_client import QdrantClient

logger = logging.getLogger(__name__)

INVESTIGATIONS_COLLECTION = "investigations"


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
