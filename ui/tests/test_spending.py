"""Tests for spending dashboard routes and service."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from flask.testing import FlaskClient

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


# ── Spending routes tests ──────────────────────────


class TestSpendingRoutes:
    """Tests for spending dashboard routes."""

    @pytest.fixture
    def app(self) -> Flask:
        """Create test Flask app."""
        from beeper_ui.app import create_app
        from beeper_ui.config import TestingConfig

        return create_app(TestingConfig)

    @pytest.fixture
    def client(self, app: Flask) -> FlaskClient:
        """Create test client."""
        with app.test_client() as c:
            yield c

    @patch("beeper_ui.routes.spending.get_spending_service")
    def test_spending_dashboard_renders(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test full page renders."""
        mock_svc = MagicMock()
        mock_svc.get_spending_summary.return_value = {
            "daily_cost_usd": 10.50,
            "monthly_cost_usd": 150.00,
            "daily_cap_usd": 50.0,
            "monthly_cap_usd": 500.0,
            "daily_pct": 21.0,
            "monthly_pct": 30.0,
            "projected_monthly_usd": 200.0,
            "daily_investigation_count": 15,
            "monthly_investigation_count": 200,
            "rate_per_hour": 5,
            "rate_limit": 100,
        }
        mock_svc.get_cap_status.return_value = {
            "enforcement_active": False,
            "caps_configured": True,
            "warnings": [],
        }
        mock_svc.get_spending_trend.return_value = []
        mock_get_svc.return_value = mock_svc

        response = client.get("/spending/")
        assert response.status_code == 200
        assert b"Spending" in response.data

    @patch("beeper_ui.routes.spending.get_spending_service")
    def test_spending_dashboard_htmx(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test HTMX partial rendering."""
        mock_svc = MagicMock()
        mock_svc.get_spending_summary.return_value = {
            "daily_cost_usd": 0,
            "monthly_cost_usd": 0,
            "daily_cap_usd": None,
            "monthly_cap_usd": None,
            "daily_pct": None,
            "monthly_pct": None,
            "projected_monthly_usd": 0,
            "daily_investigation_count": 0,
            "monthly_investigation_count": 0,
            "rate_per_hour": 0,
            "rate_limit": None,
        }
        mock_svc.get_cap_status.return_value = {
            "enforcement_active": False,
            "caps_configured": False,
            "warnings": [],
        }
        mock_svc.get_spending_trend.return_value = []
        mock_get_svc.return_value = mock_svc

        response = client.get(
            "/spending/", headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        # Partial should not include full HTML structure
        assert b"<!DOCTYPE html>" not in response.data

    @patch("beeper_ui.routes.spending.get_spending_service")
    def test_spending_status_route(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test spending status HTMX partial route."""
        mock_svc = MagicMock()
        mock_svc.get_spending_summary.return_value = {
            "daily_cost_usd": 5.0,
            "monthly_cost_usd": 100.0,
            "daily_cap_usd": 50.0,
            "monthly_cap_usd": 500.0,
            "daily_pct": 10.0,
            "monthly_pct": 20.0,
            "projected_monthly_usd": 150.0,
            "daily_investigation_count": 5,
            "monthly_investigation_count": 50,
            "rate_per_hour": 2,
            "rate_limit": 100,
        }
        mock_svc.get_cap_status.return_value = {
            "enforcement_active": False,
            "caps_configured": True,
            "warnings": [],
        }
        mock_svc.get_spending_trend.return_value = []
        mock_get_svc.return_value = mock_svc

        response = client.get("/spending/status")
        assert response.status_code == 200

    @patch("beeper_ui.routes.spending.get_spending_service")
    def test_spending_dashboard_qdrant_error(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test graceful error handling when Qdrant is unavailable."""
        mock_svc = MagicMock()
        mock_svc.get_spending_summary.side_effect = Exception(
            "Connection refused"
        )
        mock_get_svc.return_value = mock_svc

        response = client.get("/spending/")
        assert response.status_code == 200
        assert b"Unable to connect" in response.data
