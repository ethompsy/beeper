"""Tests for Task 5.4 — BFF JSON API for the React Metrics (MTTR) view.

Acceptance criteria (each [T] maps to a clearly-named test class):

[T1] GET /api/v1/metrics/mttr returns JSON (not HTML); Content-Type is
     application/json; response shape includes trend/by_service/by_severity/
     services/severities/summary fields; period/service/severity filters are
     forwarded to MetricsService (same validation as the Jinja dashboard).

[T2] GET /api/v1/metrics/mttr/drilldown returns JSON with period_label +
     investigations; invalid/missing date range degrades to an empty list
     (400), matching the Jinja route's graceful-degrade behavior instead of
     raising.

[T3] Both endpoints return a JSON error payload (not an HTML error page) on
     an unexpected MetricsService failure.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from flask.testing import FlaskClient

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig


@pytest.fixture()
def app() -> Flask:
    return create_app(TestingConfig)


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    with app.test_client() as c:
        yield c


_TREND = [
    {"period": "2026-01", "avg_mttr": 3600, "count": 5, "start": "2026-01-01", "end": "2026-01-31"},
    {"period": "2026-02", "avg_mttr": 2400, "count": 8, "start": "2026-02-01", "end": "2026-02-28"},
]

_MTTR_DATA = {
    "trend": _TREND,
    "overall_avg_mttr": 3000,
    "total_count": 13,
    "improvement_pct": 33.3,
    "improving": True,
}

_BY_SERVICE = [
    {"service": "api-gateway", "avg_mttr": 2100, "count": 8},
    {"service": "payment-service", "avg_mttr": 4500, "count": 5},
]

_BY_SEVERITY = [
    {"severity": "critical", "avg_mttr": 5400, "count": 3},
    {"severity": "high", "avg_mttr": 3000, "count": 10},
]

_DRILLDOWN_INVESTIGATIONS = [
    {
        "investigation_id": "inv-abc123",
        "service": "api-gateway",
        "severity": "high",
        "mttr_seconds": 3420,
        "resolved_at": "2026-02-15T14:30:00Z",
        "resolution_outcome": "resolved",
    },
]


def _configure_mock_service(mock_svc_cls: MagicMock) -> MagicMock:
    mock_svc = MagicMock()
    mock_svc_cls.return_value = mock_svc
    mock_svc.get_mttr_data.return_value = _MTTR_DATA
    mock_svc.get_mttr_by_service.return_value = _BY_SERVICE
    mock_svc.get_mttr_by_severity.return_value = _BY_SEVERITY
    mock_svc.get_services.return_value = ["api-gateway", "payment-service"]
    mock_svc.get_severities.return_value = ["critical", "high"]
    mock_svc.get_investigations_for_period.return_value = _DRILLDOWN_INVESTIGATIONS
    return mock_svc


# ---------------------------------------------------------------------------
# [T1] GET /api/v1/metrics/mttr
# ---------------------------------------------------------------------------


class TestMttrJsonEndpoint:
    """[T1] /api/v1/metrics/mttr returns JSON with the expected shape."""

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_returns_json_content_type(self, mock_svc_cls: MagicMock, client: FlaskClient) -> None:
        _configure_mock_service(mock_svc_cls)
        resp = client.get("/api/v1/metrics/mttr")
        assert resp.status_code == 200
        assert "application/json" in resp.content_type
        assert "text/html" not in resp.content_type

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_no_html_in_body(self, mock_svc_cls: MagicMock, client: FlaskClient) -> None:
        _configure_mock_service(mock_svc_cls)
        resp = client.get("/api/v1/metrics/mttr")
        raw = resp.data.decode()
        assert "<html" not in raw
        assert "<!DOCTYPE" not in raw

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_response_shape(self, mock_svc_cls: MagicMock, client: FlaskClient) -> None:
        _configure_mock_service(mock_svc_cls)
        resp = client.get("/api/v1/metrics/mttr")
        data = resp.get_json()

        assert data["period"] == "month"
        assert data["service"] is None
        assert data["severity"] is None
        assert data["services"] == ["api-gateway", "payment-service"]
        assert data["severities"] == ["critical", "high"]

        assert data["trend"] == [
            {
                "period": "2026-01",
                "avg_mttr_seconds": 3600,
                "count": 5,
                "start": "2026-01-01",
                "end": "2026-01-31",
            },
            {
                "period": "2026-02",
                "avg_mttr_seconds": 2400,
                "count": 8,
                "start": "2026-02-01",
                "end": "2026-02-28",
            },
        ]
        assert data["overall_avg_mttr_seconds"] == 3000
        assert data["total_count"] == 13
        assert data["improvement_pct"] == 33.3
        assert data["improving"] is True

        assert data["by_service"] == [
            {"service": "api-gateway", "avg_mttr_seconds": 2100, "count": 8},
            {"service": "payment-service", "avg_mttr_seconds": 4500, "count": 5},
        ]
        assert data["by_severity"] == [
            {"severity": "critical", "avg_mttr_seconds": 5400, "count": 3},
            {"severity": "high", "avg_mttr_seconds": 3000, "count": 10},
        ]

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_period_filter_forwarded(self, mock_svc_cls: MagicMock, client: FlaskClient) -> None:
        mock_svc = _configure_mock_service(mock_svc_cls)
        resp = client.get("/api/v1/metrics/mttr?period=week")
        assert resp.status_code == 200
        assert resp.get_json()["period"] == "week"
        mock_svc.get_mttr_data.assert_called_once_with(
            time_period="week", service=None, severity=None
        )

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_service_and_severity_filters_forwarded(
        self, mock_svc_cls: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = _configure_mock_service(mock_svc_cls)
        resp = client.get("/api/v1/metrics/mttr?service=api-gateway&severity=high")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["service"] == "api-gateway"
        assert data["severity"] == "high"
        mock_svc.get_mttr_data.assert_called_once_with(
            time_period="month", service="api-gateway", severity="high"
        )

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_invalid_period_defaults_to_month(
        self, mock_svc_cls: MagicMock, client: FlaskClient
    ) -> None:
        _configure_mock_service(mock_svc_cls)
        resp = client.get("/api/v1/metrics/mttr?period=invalid")
        assert resp.status_code == 200
        assert resp.get_json()["period"] == "month"

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_invalid_severity_ignored(self, mock_svc_cls: MagicMock, client: FlaskClient) -> None:
        mock_svc = _configure_mock_service(mock_svc_cls)
        resp = client.get("/api/v1/metrics/mttr?severity=not-a-real-severity")
        assert resp.status_code == 200
        assert resp.get_json()["severity"] is None
        mock_svc.get_mttr_data.assert_called_once_with(
            time_period="month", service=None, severity=None
        )

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_invalid_service_name_ignored(
        self, mock_svc_cls: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = _configure_mock_service(mock_svc_cls)
        resp = client.get("/api/v1/metrics/mttr?service=../../etc/passwd")
        assert resp.status_code == 200
        assert resp.get_json()["service"] is None
        mock_svc.get_mttr_data.assert_called_once_with(
            time_period="month", service=None, severity=None
        )

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_service_closed_after_request(
        self, mock_svc_cls: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = _configure_mock_service(mock_svc_cls)
        client.get("/api/v1/metrics/mttr")
        mock_svc.close.assert_called_once()


# ---------------------------------------------------------------------------
# [T3] error handling — /api/v1/metrics/mttr
# ---------------------------------------------------------------------------


class TestMttrJsonEndpointErrors:
    """[T3] MetricsService failures degrade to a JSON error, not an HTML page."""

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_service_exception_returns_json_503(
        self, mock_svc_cls: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_svc_cls.return_value = mock_svc
        mock_svc.get_mttr_data.side_effect = RuntimeError("qdrant unavailable")

        resp = client.get("/api/v1/metrics/mttr")
        assert resp.status_code == 503
        assert "application/json" in resp.content_type
        data = resp.get_json()
        assert data["error"] == "metrics_unavailable"
        mock_svc.close.assert_called_once()


# ---------------------------------------------------------------------------
# [T2] GET /api/v1/metrics/mttr/drilldown
# ---------------------------------------------------------------------------


class TestMttrDrilldownJsonEndpoint:
    """[T2] /api/v1/metrics/mttr/drilldown returns JSON period_label + investigations."""

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_returns_json_content_type(self, mock_svc_cls: MagicMock, client: FlaskClient) -> None:
        _configure_mock_service(mock_svc_cls)
        resp = client.get("/api/v1/metrics/mttr/drilldown?start=2026-02-01&end=2026-02-28")
        assert resp.status_code == 200
        assert "application/json" in resp.content_type
        assert "text/html" not in resp.content_type

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_response_shape(self, mock_svc_cls: MagicMock, client: FlaskClient) -> None:
        mock_svc = _configure_mock_service(mock_svc_cls)
        resp = client.get("/api/v1/metrics/mttr/drilldown?start=2026-02-01&end=2026-02-28")
        data = resp.get_json()

        assert data["period_label"] == "2026-02-01 to 2026-02-28"
        assert data["investigations"] == [
            {
                "investigation_id": "inv-abc123",
                "service": "api-gateway",
                "severity": "high",
                "mttr_seconds": 3420,
                "resolved_at": "2026-02-15T14:30:00Z",
                "resolution_outcome": "resolved",
            }
        ]
        mock_svc.get_investigations_for_period.assert_called_once_with(
            start_date="2026-02-01", end_date="2026-02-28", service=None
        )

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_service_filter_forwarded(self, mock_svc_cls: MagicMock, client: FlaskClient) -> None:
        mock_svc = _configure_mock_service(mock_svc_cls)
        resp = client.get(
            "/api/v1/metrics/mttr/drilldown?start=2026-02-01&end=2026-02-28&service=api-gateway"
        )
        assert resp.status_code == 200
        mock_svc.get_investigations_for_period.assert_called_once_with(
            start_date="2026-02-01", end_date="2026-02-28", service="api-gateway"
        )

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_invalid_service_name_ignored(
        self, mock_svc_cls: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = _configure_mock_service(mock_svc_cls)
        client.get(
            "/api/v1/metrics/mttr/drilldown?start=2026-02-01&end=2026-02-28&service=../../etc/passwd"
        )
        mock_svc.get_investigations_for_period.assert_called_once_with(
            start_date="2026-02-01", end_date="2026-02-28", service=None
        )

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_missing_dates_returns_400_empty(
        self, mock_svc_cls: MagicMock, client: FlaskClient
    ) -> None:
        _configure_mock_service(mock_svc_cls)
        resp = client.get("/api/v1/metrics/mttr/drilldown")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["period_label"] is None
        assert data["investigations"] == []

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_malformed_date_returns_400_empty(
        self, mock_svc_cls: MagicMock, client: FlaskClient
    ) -> None:
        _configure_mock_service(mock_svc_cls)
        resp = client.get("/api/v1/metrics/mttr/drilldown?start=2026/02/01&end=2026/02/28")
        assert resp.status_code == 400
        assert resp.get_json()["investigations"] == []

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_start_after_end_returns_400_empty(
        self, mock_svc_cls: MagicMock, client: FlaskClient
    ) -> None:
        _configure_mock_service(mock_svc_cls)
        resp = client.get("/api/v1/metrics/mttr/drilldown?start=2026-02-28&end=2026-02-01")
        assert resp.status_code == 400
        assert resp.get_json()["investigations"] == []

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_empty_period_returns_empty_list_not_blank(
        self, mock_svc_cls: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = _configure_mock_service(mock_svc_cls)
        mock_svc.get_investigations_for_period.return_value = []
        resp = client.get("/api/v1/metrics/mttr/drilldown?start=2026-02-01&end=2026-02-28")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["period_label"] == "2026-02-01 to 2026-02-28"
        assert data["investigations"] == []


class TestMttrDrilldownJsonEndpointErrors:
    """[T3] MetricsService failures degrade to a JSON error, not an HTML page."""

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_service_exception_returns_json_503(
        self, mock_svc_cls: MagicMock, client: FlaskClient
    ) -> None:
        mock_svc = MagicMock()
        mock_svc_cls.return_value = mock_svc
        mock_svc.get_investigations_for_period.side_effect = RuntimeError("qdrant unavailable")

        resp = client.get("/api/v1/metrics/mttr/drilldown?start=2026-02-01&end=2026-02-28")
        assert resp.status_code == 503
        assert "application/json" in resp.content_type
        data = resp.get_json()
        assert data["error"] == "metrics_unavailable"
        assert data["investigations"] == []
