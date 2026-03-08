"""Tests for cost insights routes and service methods."""

import json
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from flask.testing import FlaskClient

from beeper_ui.services.spending_service import SpendingService

# ── SpendingService cost breakdown tests ──────────────────────────


class TestCostByService:
    """Tests for SpendingService.get_cost_by_service()."""

    def _make_point(
        self,
        cost_usd: float = 0.05,
        created_at: str = "2026-03-07T12:00:00Z",
        service: str = "api-gateway",
        severity: str = "high",
        per_model: dict | None = None,
    ) -> MagicMock:
        """Create a mock Qdrant point with cost_stats."""
        point = MagicMock()
        cost_stats: dict = {
            "total_cost_usd": cost_usd,
            "call_count": 3,
            "total_prompt_tokens": 5000,
            "total_completion_tokens": 2000,
        }
        if per_model is not None:
            cost_stats["per_model"] = per_model
        point.payload = {
            "investigation_id": "inv-123",
            "service": service,
            "severity": severity,
            "created_at": created_at,
            "cost_stats": cost_stats,
        }
        return point

    def test_groups_by_service(self) -> None:
        """Test cost grouping by service name."""
        svc = SpendingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = (
            [
                self._make_point(
                    cost_usd=0.10,
                    service="api-gateway",
                    created_at="2026-03-07T10:00:00Z",
                ),
                self._make_point(
                    cost_usd=0.20,
                    service="api-gateway",
                    created_at="2026-03-07T11:00:00Z",
                ),
                self._make_point(
                    cost_usd=0.05,
                    service="payment-service",
                    created_at="2026-03-07T12:00:00Z",
                ),
            ],
            None,
        )

        result = svc.get_cost_by_service(period="month")

        assert len(result) == 2
        # Sorted by total_cost desc
        assert result[0]["service"] == "api-gateway"
        assert result[0]["total_cost_usd"] == 0.30
        assert result[0]["investigation_count"] == 2
        assert result[0]["cost_per_investigation"] == 0.15
        assert result[1]["service"] == "payment-service"
        assert result[1]["total_cost_usd"] == 0.05

    def test_no_data(self) -> None:
        """Test with no investigation data."""
        svc = SpendingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = ([], None)

        result = svc.get_cost_by_service()
        assert result == []

    def test_model_breakdown(self) -> None:
        """Test per-model breakdown in service costs."""
        svc = SpendingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = (
            [
                self._make_point(
                    cost_usd=0.10,
                    service="api-gateway",
                    created_at="2026-03-07T10:00:00Z",
                    per_model={
                        "claude-haiku-3.5": {
                            "cost_usd": 0.02,
                            "calls": 2,
                        },
                        "claude-sonnet-4-20250514": {
                            "cost_usd": 0.08,
                            "calls": 1,
                        },
                    },
                ),
            ],
            None,
        )

        result = svc.get_cost_by_service(period="month")
        assert len(result) == 1
        breakdown = result[0]["model_breakdown"]
        assert "claude-haiku-3.5" in breakdown
        assert breakdown["claude-haiku-3.5"]["cost_usd"] == 0.02


class TestCostBySeverity:
    """Tests for SpendingService.get_cost_by_severity()."""

    def _make_point(
        self,
        cost_usd: float = 0.05,
        created_at: str = "2026-03-07T12:00:00Z",
        severity: str = "high",
    ) -> MagicMock:
        point = MagicMock()
        point.payload = {
            "investigation_id": "inv-123",
            "service": "api-gateway",
            "severity": severity,
            "created_at": created_at,
            "cost_stats": {"total_cost_usd": cost_usd},
        }
        return point

    def test_groups_by_severity(self) -> None:
        """Test cost grouping by severity level."""
        svc = SpendingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = (
            [
                self._make_point(cost_usd=0.30, severity="critical"),
                self._make_point(cost_usd=0.10, severity="high"),
                self._make_point(cost_usd=0.05, severity="low"),
            ],
            None,
        )

        result = svc.get_cost_by_severity(period="month")

        assert len(result) == 3
        assert result[0]["severity"] == "critical"
        assert result[0]["total_cost_usd"] == 0.30


class TestCostByModel:
    """Tests for SpendingService.get_cost_by_model()."""

    def _make_point(
        self,
        created_at: str = "2026-03-07T12:00:00Z",
        per_model: dict | None = None,
    ) -> MagicMock:
        point = MagicMock()
        cost_stats: dict = {"total_cost_usd": 0.10}
        if per_model is not None:
            cost_stats["per_model"] = per_model
        point.payload = {
            "investigation_id": "inv-123",
            "service": "api-gateway",
            "severity": "high",
            "created_at": created_at,
            "cost_stats": cost_stats,
        }
        return point

    def test_aggregates_from_per_model(self) -> None:
        """Test model cost aggregation from per_model nested dicts."""
        svc = SpendingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = (
            [
                self._make_point(
                    per_model={
                        "claude-haiku-3.5": {
                            "cost_usd": 0.02,
                            "calls": 2,
                            "prompt_tokens": 3000,
                            "completion_tokens": 1000,
                        },
                    },
                ),
                self._make_point(
                    per_model={
                        "claude-haiku-3.5": {
                            "cost_usd": 0.03,
                            "calls": 1,
                            "prompt_tokens": 2000,
                            "completion_tokens": 800,
                        },
                        "claude-sonnet-4-20250514": {
                            "cost_usd": 0.10,
                            "calls": 1,
                            "prompt_tokens": 1000,
                            "completion_tokens": 500,
                        },
                    },
                ),
            ],
            None,
        )

        result = svc.get_cost_by_model(period="month")

        assert len(result) == 2
        # Sorted by cost desc
        assert result[0]["model"] == "claude-sonnet-4-20250514"
        assert result[0]["total_cost_usd"] == 0.10
        assert result[1]["model"] == "claude-haiku-3.5"
        assert result[1]["total_cost_usd"] == 0.05
        assert result[1]["call_count"] == 3

    def test_missing_per_model(self) -> None:
        """Test graceful handling when per_model is missing."""
        svc = SpendingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = (
            [self._make_point(per_model=None)],
            None,
        )

        result = svc.get_cost_by_model(period="month")
        assert result == []


class TestHighCostServices:
    """Tests for SpendingService.get_high_cost_services()."""

    def _make_point(
        self,
        cost_usd: float = 0.05,
        service: str = "api-gateway",
        created_at: str = "2026-03-07T12:00:00Z",
    ) -> MagicMock:
        point = MagicMock()
        point.payload = {
            "investigation_id": "inv-123",
            "service": service,
            "severity": "high",
            "created_at": created_at,
            "cost_stats": {"total_cost_usd": cost_usd},
        }
        return point

    def test_flags_above_threshold(self) -> None:
        """Test services above threshold multiplier are flagged."""
        svc = SpendingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = (
            [
                self._make_point(
                    cost_usd=1.00,
                    service="noisy-service",
                    created_at="2026-03-07T10:00:00Z",
                ),
                self._make_point(
                    cost_usd=0.10,
                    service="quiet-a",
                    created_at="2026-03-07T11:00:00Z",
                ),
                self._make_point(
                    cost_usd=0.10,
                    service="quiet-b",
                    created_at="2026-03-07T12:00:00Z",
                ),
            ],
            None,
        )

        result = svc.get_high_cost_services(threshold_multiplier=2.0)

        assert len(result) == 1
        assert result[0]["service"] == "noisy-service"
        assert result[0]["total_cost_usd"] == 1.00
        assert result[0]["multiplier"] > 2.0
        assert "recommendation" in result[0]
        assert "noisy-service" in result[0]["recommendation"]

    def test_all_similar_cost_none_flagged(self) -> None:
        """Test no services flagged when costs are similar."""
        svc = SpendingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = (
            [
                self._make_point(
                    cost_usd=0.10,
                    service="svc-a",
                    created_at="2026-03-07T10:00:00Z",
                ),
                self._make_point(
                    cost_usd=0.12,
                    service="svc-b",
                    created_at="2026-03-07T11:00:00Z",
                ),
                self._make_point(
                    cost_usd=0.11,
                    service="svc-c",
                    created_at="2026-03-07T12:00:00Z",
                ),
            ],
            None,
        )

        result = svc.get_high_cost_services(threshold_multiplier=2.0)
        assert result == []

    def test_single_service_not_flagged(self) -> None:
        """Test single service is not flagged (no meaningful average)."""
        svc = SpendingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = (
            [
                self._make_point(
                    cost_usd=5.0,
                    service="only-service",
                    created_at="2026-03-07T10:00:00Z",
                ),
            ],
            None,
        )

        result = svc.get_high_cost_services(threshold_multiplier=2.0)
        assert result == []

    def test_trend_calculation(self) -> None:
        """Test trend is included in flagged service data."""
        svc = SpendingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = (
            [
                self._make_point(
                    cost_usd=1.00,
                    service="noisy",
                    created_at="2026-03-07T10:00:00Z",
                ),
                self._make_point(
                    cost_usd=0.05,
                    service="quiet",
                    created_at="2026-03-07T11:00:00Z",
                ),
            ],
            None,
        )

        result = svc.get_high_cost_services(threshold_multiplier=1.5)
        assert len(result) == 1
        assert result[0]["trend"] in ("increasing", "stable", "decreasing")


class TestExportCostData:
    """Tests for SpendingService.export_cost_data()."""

    def _make_point(
        self,
        cost_usd: float = 0.10,
        service: str = "api-gateway",
        severity: str = "high",
        created_at: str = "2026-03-07T12:00:00Z",
        per_model: dict | None = None,
    ) -> MagicMock:
        point = MagicMock()
        cost_stats: dict = {"total_cost_usd": cost_usd}
        if per_model:
            cost_stats["per_model"] = per_model
        point.payload = {
            "investigation_id": "inv-123",
            "service": service,
            "severity": severity,
            "created_at": created_at,
            "cost_stats": cost_stats,
        }
        return point

    def test_json_export(self) -> None:
        """Test JSON export contains all sections."""
        svc = SpendingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = (
            [
                self._make_point(service="api-gateway"),
                self._make_point(service="payment-service"),
            ],
            None,
        )

        result = svc.export_cost_data(period="month", fmt="json")
        data = json.loads(result)

        assert data["period"] == "month"
        assert "generated_at" in data
        assert "by_service" in data
        assert "by_severity" in data
        assert "by_model" in data
        assert "high_cost_services" in data

    def test_csv_export(self) -> None:
        """Test CSV export has headers and data rows."""
        svc = SpendingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = (
            [
                self._make_point(service="api-gateway"),
                self._make_point(service="payment-service"),
            ],
            None,
        )

        result = svc.export_cost_data(period="month", fmt="csv")
        assert isinstance(result, bytes)
        lines = result.decode("utf-8").strip().split("\n")

        # Header + 2 data rows
        assert len(lines) == 3
        assert "service" in lines[0]
        assert "total_cost_usd" in lines[0]


class TestPeriodFiltering:
    """Tests for period-based filtering of investigation data."""

    def _make_point(
        self,
        cost_usd: float = 0.05,
        created_at: str = "2026-03-07T12:00:00Z",
        service: str = "api-gateway",
    ) -> MagicMock:
        point = MagicMock()
        point.payload = {
            "investigation_id": "inv-123",
            "service": service,
            "severity": "high",
            "created_at": created_at,
            "cost_stats": {"total_cost_usd": cost_usd},
        }
        return point

    def test_month_filters_old_data(self) -> None:
        """Test month period filters out data older than 30 days."""
        svc = SpendingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = (
            [
                self._make_point(
                    cost_usd=0.10,
                    created_at="2026-03-07T10:00:00Z",
                ),
                self._make_point(
                    cost_usd=0.20,
                    created_at="2025-01-01T10:00:00Z",  # Very old
                ),
            ],
            None,
        )

        result = svc.get_cost_by_service(period="month")
        # Only recent data should be included
        assert len(result) == 1
        assert result[0]["total_cost_usd"] == 0.10


# ── Cost insights route tests ──────────────────────────


class TestCostInsightsRoutes:
    """Tests for cost insights routes."""

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

    def _mock_service(self) -> MagicMock:
        """Create mock SpendingService with cost data."""
        mock_svc = MagicMock()
        mock_svc.get_cost_by_service.return_value = [
            {
                "service": "api-gateway",
                "total_cost_usd": 5.0,
                "investigation_count": 10,
                "cost_per_investigation": 0.50,
                "model_breakdown": {},
            },
        ]
        mock_svc.get_cost_by_severity.return_value = [
            {
                "severity": "high",
                "total_cost_usd": 3.0,
                "investigation_count": 5,
                "cost_per_investigation": 0.60,
            },
        ]
        mock_svc.get_cost_by_model.return_value = [
            {
                "model": "claude-haiku-3.5",
                "total_cost_usd": 2.0,
                "call_count": 20,
                "total_prompt_tokens": 50000,
                "total_completion_tokens": 20000,
            },
        ]
        mock_svc.get_high_cost_services.return_value = []
        mock_svc.get_spending_trend.return_value = []
        return mock_svc

    @patch("beeper_ui.routes.spending.get_spending_service")
    def test_cost_insights_renders(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test full cost insights page renders."""
        mock_get_svc.return_value = self._mock_service()

        response = client.get("/spending/costs")
        assert response.status_code == 200
        assert b"Cost Insights" in response.data

    @patch("beeper_ui.routes.spending.get_spending_service")
    def test_cost_insights_htmx(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test HTMX partial rendering."""
        mock_get_svc.return_value = self._mock_service()

        response = client.get(
            "/spending/costs", headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        assert b"<!DOCTYPE html>" not in response.data

    @patch("beeper_ui.routes.spending.get_spending_service")
    def test_cost_insights_period_filter(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test period filter is passed to service."""
        mock_svc = self._mock_service()
        mock_get_svc.return_value = mock_svc

        response = client.get("/spending/costs?period=week")
        assert response.status_code == 200
        mock_svc.get_cost_by_service.assert_called_with(period="week")

    @patch("beeper_ui.routes.spending.get_spending_service")
    def test_cost_breakdown_partial(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test cost breakdown HTMX partial route."""
        mock_get_svc.return_value = self._mock_service()

        response = client.get("/spending/costs/breakdown")
        assert response.status_code == 200
        assert b"<!DOCTYPE html>" not in response.data

    @patch("beeper_ui.routes.spending.get_spending_service")
    def test_export_json(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test JSON export returns download with Content-Disposition."""
        mock_svc = MagicMock()
        mock_svc.export_cost_data.return_value = '{"period": "month"}'
        mock_get_svc.return_value = mock_svc

        response = client.get(
            "/spending/costs/export?format=json&period=month"
        )
        assert response.status_code == 200
        assert response.content_type == "application/json"
        assert "attachment" in response.headers.get(
            "Content-Disposition", ""
        )

    @patch("beeper_ui.routes.spending.get_spending_service")
    def test_export_csv(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test CSV export returns download with Content-Disposition."""
        mock_svc = MagicMock()
        mock_svc.export_cost_data.return_value = b"service,cost\napi,1.0\n"
        mock_get_svc.return_value = mock_svc

        response = client.get(
            "/spending/costs/export?format=csv&period=month"
        )
        assert response.status_code == 200
        assert "text/csv" in response.content_type
        assert "attachment" in response.headers.get(
            "Content-Disposition", ""
        )

    @patch("beeper_ui.routes.spending.get_spending_service")
    def test_cost_insights_qdrant_error(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test graceful error handling when Qdrant is unavailable."""
        mock_svc = MagicMock()
        mock_svc.get_cost_by_service.side_effect = Exception(
            "Connection refused"
        )
        mock_get_svc.return_value = mock_svc

        response = client.get("/spending/costs")
        assert response.status_code == 200
        assert b"Unable to connect" in response.data
