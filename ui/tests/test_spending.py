"""Tests for the spending service.

Task 6.3 (D13/D14) retired the Jinja `/spending/` and `/spending/status`
routes (`spending/spending.html`, `spending/_spending_content.html` deleted);
both bare URLs now 302-redirect to `/app/spending` (react_registry.py). The
`TestSpendingRoutes` class that used to live in this file exercised those
now-deleted templates (full page, HTMX partial, the HTMX auto-refresh status
partial, and the Qdrant-unavailable error card) and has been removed in
full — see `test_sources_spending_views.py`'s module docstring for the
equivalent note on the sibling `/sources/` retirement. The Qdrant-unavailable
JSON error path survives at the JSON API layer
(`test_api_v1_sources_spending.py::TestSpendingJsonEndpoint::
test_spending_data_unavailable_returns_503`).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from beeper_ui.services.spending_service import SpendingService

# Dynamic dates for time-sensitive tests
_now = datetime.now(timezone.utc)
_TODAY_ISO = _now.strftime("%Y-%m-%dT%H:%M:%SZ")
_TODAY_MINUS_1H = (_now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
_TODAY_MINUS_2H = (_now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
_YESTERDAY_ISO = (_now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
_TODAY_DATE = _now.strftime("%Y-%m-%d")
_YESTERDAY_DATE = (_now - timedelta(days=1)).strftime("%Y-%m-%d")

# ── SpendingService tests ──────────────────────────


class TestSpendingService:
    """Tests for SpendingService."""

    def _make_point(
        self,
        cost_usd: float = 0.05,
        created_at: str = _TODAY_ISO,
        service: str = "api-gateway",
    ) -> MagicMock:
        """Create a mock Qdrant point with cost_stats."""
        point = MagicMock()
        point.payload = {
            "investigation_id": "inv-123",
            "service": service,
            "severity": "high",
            "created_at": created_at,
            "cost_stats": {
                "total_cost_usd": cost_usd,
                "call_count": 3,
                "total_prompt_tokens": 5000,
                "total_completion_tokens": 2000,
            },
        }
        return point

    def test_get_spending_summary(self) -> None:
        """Test spending summary aggregation."""
        svc = SpendingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = (
            [
                self._make_point(cost_usd=0.05, created_at=_TODAY_MINUS_2H),
                self._make_point(cost_usd=0.10, created_at=_TODAY_MINUS_1H),
            ],
            None,
        )

        with patch.dict(
            "os.environ",
            {
                "BEEPER_LLM_DAILY_CAP_CENTS": "5000",
                "BEEPER_LLM_MONTHLY_CAP_CENTS": "50000",
            },
        ):
            summary = svc.get_spending_summary()

        assert summary["monthly_cost_usd"] > 0
        assert summary["daily_cap_usd"] == 50.0
        assert summary["monthly_cap_usd"] == 500.0

    def test_get_spending_summary_no_data(self) -> None:
        """Test spending summary with no investigation data."""
        svc = SpendingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = ([], None)

        with patch.dict("os.environ", {}, clear=False):
            summary = svc.get_spending_summary()

        assert summary["daily_cost_usd"] == 0.0
        assert summary["monthly_cost_usd"] == 0.0

    def test_get_spending_trend(self) -> None:
        """Test spending trend data aggregation."""
        svc = SpendingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = (
            [
                self._make_point(cost_usd=0.05, created_at=_YESTERDAY_ISO),
                self._make_point(cost_usd=0.10, created_at=_TODAY_ISO),
            ],
            None,
        )

        trend = svc.get_spending_trend(period="daily")
        assert len(trend) == 2
        assert trend[0]["period"] == _YESTERDAY_DATE
        assert trend[1]["period"] == _TODAY_DATE
        assert trend[0]["cost_usd"] > 0

    def test_get_cap_status_no_caps(self) -> None:
        """Test cap status with no caps configured."""
        svc = SpendingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = ([], None)

        with patch.dict("os.environ", {}, clear=False):
            for key in [
                "BEEPER_LLM_DAILY_CAP_CENTS",
                "BEEPER_LLM_MONTHLY_CAP_CENTS",
            ]:
                import os

                os.environ.pop(key, None)
            status = svc.get_cap_status()

        assert status["caps_configured"] is False
        assert status["enforcement_active"] is False

    def test_scroll_caching(self) -> None:
        """Test that scroll results are cached per service instance."""
        svc = SpendingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = (
            [self._make_point()],
            None,
        )

        # Call twice
        with patch.dict("os.environ", {}, clear=False):
            svc.get_spending_summary()
            svc.get_spending_summary()

        # Qdrant scroll should only be called once
        assert svc._qdrant_client.scroll.call_count == 1
