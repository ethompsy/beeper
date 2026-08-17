"""Tests for MTTR Trends Dashboard (Story 6-1)."""

import json
from unittest.mock import MagicMock, patch

from flask.testing import FlaskClient

from beeper_ui.services.metrics_service import MetricsService


def _make_qdrant_point(
    investigation_id: str = "inv-abc123",
    service: str = "api-gateway",
    severity: str = "high",
    resolution_outcome: str = "resolved",
    resolved_at: str = "2026-02-15T14:30:00Z",
    mttr_seconds: int | None = 3420,
) -> MagicMock:
    """Create a mock Qdrant point with investigation payload."""
    point = MagicMock()
    point.payload = {
        "investigation_id": investigation_id,
        "service": service,
        "severity": severity,
        "resolution_outcome": resolution_outcome,
        "resolved_at": resolved_at,
        "mttr_seconds": mttr_seconds,
    }
    return point


MOCK_POINTS = [
    _make_qdrant_point(
        investigation_id="inv-001",
        service="api-gateway",
        severity="high",
        resolved_at="2026-01-10T10:00:00Z",
        mttr_seconds=3600,
    ),
    _make_qdrant_point(
        investigation_id="inv-002",
        service="payment-service",
        severity="critical",
        resolved_at="2026-01-20T10:00:00Z",
        mttr_seconds=7200,
    ),
    _make_qdrant_point(
        investigation_id="inv-003",
        service="api-gateway",
        severity="medium",
        resolved_at="2026-02-05T10:00:00Z",
        mttr_seconds=1800,
    ),
    _make_qdrant_point(
        investigation_id="inv-004",
        service="payment-service",
        severity="high",
        resolved_at="2026-02-15T10:00:00Z",
        mttr_seconds=5400,
    ),
    _make_qdrant_point(
        investigation_id="inv-005",
        service="api-gateway",
        severity="low",
        resolved_at="2026-03-01T10:00:00Z",
        mttr_seconds=900,
    ),
]

# Point with no mttr_seconds (escalated)
MOCK_POINT_NO_MTTR = _make_qdrant_point(
    investigation_id="inv-escalated",
    mttr_seconds=None,
    resolved_at="2026-02-10T10:00:00Z",
)


def _mock_scroll_with_points(points: list):
    """Create a side_effect function for qdrant scroll that returns given points."""
    def scroll_side_effect(**kwargs):
        return (points, None)
    return scroll_side_effect


class TestMetricsServiceGetMTTRData:
    """Tests for MetricsService.get_mttr_data()."""

    @patch("beeper_ui.services.metrics_service.QdrantClient")
    def test_get_mttr_data_returns_aggregated_data(self, mock_qdrant_cls: MagicMock) -> None:
        """Test MTTR data aggregation with mock data."""
        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client
        mock_client.scroll.side_effect = _mock_scroll_with_points(MOCK_POINTS)

        svc = MetricsService()
        svc._qdrant_client = mock_client
        result = svc.get_mttr_data(time_period="month")

        assert result["total_count"] == 5
        assert result["overall_avg_mttr"] > 0
        assert len(result["trend"]) > 0
        # Should have entries for Jan, Feb, Mar
        periods = [t["period"] for t in result["trend"]]
        assert "2026-01" in periods
        assert "2026-02" in periods

        svc.close()

    @patch("beeper_ui.services.metrics_service.QdrantClient")
    def test_get_mttr_data_empty(self, mock_qdrant_cls: MagicMock) -> None:
        """Test MTTR data with no resolved investigations returns empty."""
        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client
        mock_client.scroll.side_effect = _mock_scroll_with_points([])

        svc = MetricsService()
        svc._qdrant_client = mock_client
        result = svc.get_mttr_data()

        assert result["total_count"] == 0
        assert result["trend"] == []
        assert result["improvement_pct"] is None

        svc.close()

    @patch("beeper_ui.services.metrics_service.QdrantClient")
    def test_get_mttr_data_filters_null_mttr(self, mock_qdrant_cls: MagicMock) -> None:
        """Test that investigations without mttr_seconds are filtered out."""
        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client
        # Mix points with and without mttr
        points_with_null = [MOCK_POINTS[0], MOCK_POINT_NO_MTTR]
        mock_client.scroll.side_effect = _mock_scroll_with_points(points_with_null)

        svc = MetricsService()
        svc._qdrant_client = mock_client
        result = svc.get_mttr_data()

        assert result["total_count"] == 1

        svc.close()

    @patch("beeper_ui.services.metrics_service.QdrantClient")
    def test_get_mttr_data_filter_by_service(self, mock_qdrant_cls: MagicMock) -> None:
        """Test filtering by service name."""
        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client
        mock_client.scroll.side_effect = _mock_scroll_with_points(MOCK_POINTS)

        svc = MetricsService()
        svc._qdrant_client = mock_client
        result = svc.get_mttr_data(service="api-gateway")

        # Only api-gateway points (inv-001, inv-003, inv-005)
        assert result["total_count"] == 3

        svc.close()

    @patch("beeper_ui.services.metrics_service.QdrantClient")
    def test_get_mttr_data_filter_by_severity(self, mock_qdrant_cls: MagicMock) -> None:
        """Test filtering by severity."""
        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client
        mock_client.scroll.side_effect = _mock_scroll_with_points(MOCK_POINTS)

        svc = MetricsService()
        svc._qdrant_client = mock_client
        result = svc.get_mttr_data(severity="high")

        # Only high severity points (inv-001, inv-004)
        assert result["total_count"] == 2

        svc.close()

    @patch("beeper_ui.services.metrics_service.QdrantClient")
    def test_get_mttr_data_weekly_period(self, mock_qdrant_cls: MagicMock) -> None:
        """Test weekly time period grouping."""
        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client
        mock_client.scroll.side_effect = _mock_scroll_with_points(MOCK_POINTS)

        svc = MetricsService()
        svc._qdrant_client = mock_client
        result = svc.get_mttr_data(time_period="week")

        assert result["total_count"] == 5
        # Weekly should have more granular periods
        for t in result["trend"]:
            assert "W" in t["period"]

        svc.close()

    @patch("beeper_ui.services.metrics_service.QdrantClient")
    def test_improvement_percentage_positive(self, mock_qdrant_cls: MagicMock) -> None:
        """Test improvement percentage when MTTR is decreasing."""
        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client
        # Create points that show improvement: high MTTR in Jan, low in Feb
        improving_points = [
            _make_qdrant_point(
                investigation_id="inv-old",
                resolved_at="2026-01-15T10:00:00Z",
                mttr_seconds=6000,
            ),
            _make_qdrant_point(
                investigation_id="inv-new",
                resolved_at="2026-02-15T10:00:00Z",
                mttr_seconds=3000,
            ),
        ]
        mock_client.scroll.side_effect = _mock_scroll_with_points(improving_points)

        svc = MetricsService()
        svc._qdrant_client = mock_client
        result = svc.get_mttr_data(time_period="month")

        assert result["improvement_pct"] == 50.0
        assert result["improving"] is True

        svc.close()

    @patch("beeper_ui.services.metrics_service.QdrantClient")
    def test_improvement_percentage_negative(self, mock_qdrant_cls: MagicMock) -> None:
        """Test improvement percentage when MTTR is increasing."""
        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client
        worsening_points = [
            _make_qdrant_point(
                investigation_id="inv-old",
                resolved_at="2026-01-15T10:00:00Z",
                mttr_seconds=3000,
            ),
            _make_qdrant_point(
                investigation_id="inv-new",
                resolved_at="2026-02-15T10:00:00Z",
                mttr_seconds=6000,
            ),
        ]
        mock_client.scroll.side_effect = _mock_scroll_with_points(worsening_points)

        svc = MetricsService()
        svc._qdrant_client = mock_client
        result = svc.get_mttr_data(time_period="month")

        assert result["improvement_pct"] == -100.0
        assert result["improving"] is False

        svc.close()


class TestMetricsServiceByService:
    """Tests for MetricsService.get_mttr_by_service()."""

    @patch("beeper_ui.services.metrics_service.QdrantClient")
    def test_groups_by_service(self, mock_qdrant_cls: MagicMock) -> None:
        """Test MTTR grouping by service."""
        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client
        mock_client.scroll.side_effect = _mock_scroll_with_points(MOCK_POINTS)

        svc = MetricsService()
        svc._qdrant_client = mock_client
        result = svc.get_mttr_by_service()

        services = {r["service"] for r in result}
        assert "api-gateway" in services
        assert "payment-service" in services
        # Each service should have count and avg_mttr
        for item in result:
            assert "avg_mttr" in item
            assert "count" in item
            assert item["count"] > 0

        svc.close()


class TestMetricsServiceBySeverity:
    """Tests for MetricsService.get_mttr_by_severity()."""

    @patch("beeper_ui.services.metrics_service.QdrantClient")
    def test_groups_by_severity(self, mock_qdrant_cls: MagicMock) -> None:
        """Test MTTR grouping by severity."""
        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client
        mock_client.scroll.side_effect = _mock_scroll_with_points(MOCK_POINTS)

        svc = MetricsService()
        svc._qdrant_client = mock_client
        result = svc.get_mttr_by_severity()

        severities = {r["severity"] for r in result}
        assert "high" in severities
        assert "critical" in severities
        for item in result:
            assert "avg_mttr" in item
            assert "count" in item

        svc.close()


class TestMetricsServiceInvestigationsForPeriod:
    """Tests for MetricsService.get_investigations_for_period()."""

    @patch("beeper_ui.services.metrics_service.QdrantClient")
    def test_returns_filtered_list(self, mock_qdrant_cls: MagicMock) -> None:
        """Test getting investigations for a specific period."""
        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client
        mock_client.scroll.side_effect = _mock_scroll_with_points(MOCK_POINTS)

        svc = MetricsService()
        svc._qdrant_client = mock_client
        result = svc.get_investigations_for_period("2026-02-01", "2026-02-28")

        # Should include inv-003 and inv-004 (Feb dates)
        ids = [r["investigation_id"] for r in result]
        assert "inv-003" in ids
        assert "inv-004" in ids
        assert "inv-001" not in ids  # January

        svc.close()


class TestMetricsServiceExport:
    """Tests for MetricsService.export_mttr_data()."""

    @patch("beeper_ui.services.metrics_service.QdrantClient")
    def test_export_json(self, mock_qdrant_cls: MagicMock) -> None:
        """Test JSON export returns valid JSON."""
        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client
        mock_client.scroll.side_effect = _mock_scroll_with_points(MOCK_POINTS)

        svc = MetricsService()
        svc._qdrant_client = mock_client
        result = svc.export_mttr_data(fmt="json")

        assert isinstance(result, str)
        data = json.loads(result)
        assert "trend" in data
        assert "by_service" in data
        assert "by_severity" in data
        assert "period" in data
        assert "generated_at" in data

        svc.close()

    @patch("beeper_ui.services.metrics_service.QdrantClient")
    def test_export_csv(self, mock_qdrant_cls: MagicMock) -> None:
        """Test CSV export returns valid CSV."""
        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client
        mock_client.scroll.side_effect = _mock_scroll_with_points(MOCK_POINTS)

        svc = MetricsService()
        svc._qdrant_client = mock_client
        result = svc.export_mttr_data(fmt="csv")

        assert isinstance(result, bytes)
        text = result.decode("utf-8")
        lines = [line.strip() for line in text.strip().split("\n")]
        assert lines[0] == "period,avg_mttr_seconds,count"
        assert len(lines) > 1  # At least header + 1 data row

        svc.close()


class TestMetricsRoutes:
    """Tests for metrics routes.

    Task 6.3 (D13/D14) retired the Jinja MTTR dashboard: `GET /metrics/`,
    `GET /metrics/mttr`, and `GET /metrics/mttr/drilldown` are all gutted to
    redirect to `/app/metrics` (react_registry.py) rather than rendering
    `mttr.html`/`_mttr_content.html`/`_drilldown.html` (deleted). The
    `_load_mttr_template_data()`/`_compute_chart_data()` helpers that fed
    those templates are deleted too — the React `TrendChart` primitive
    computes its own layout client-side.

    Tests that rendered those routes' HTML, or asserted on the route-level
    `period`/`service`/`severity` sanitization + service-call arguments (that
    logic is gone from the Jinja routes; it now lives only in
    `_validate_filters()`, used exclusively by the JSON API), have been
    removed. Equivalent sanitization coverage survives at the JSON API layer
    in `test_api_v1_metrics.py` (`TestMttrJsonEndpoint::
    test_invalid_period_defaults_to_month`, `test_invalid_severity_ignored`,
    `test_invalid_service_name_ignored`; `TestMttrDrilldownJsonEndpoint::
    test_missing_dates_returns_400_empty`,
    `test_malformed_date_returns_400_empty`,
    `test_start_after_end_returns_400_empty`), so no coverage was lost.

    `GET /metrics/export` (CSV/JSON download, no template) is untouched by
    Task 6.3 and its tests below (`test_export_json`, `test_export_csv`,
    `test_export_invalid_format_defaults_to_json`) are unaffected.
    """

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_export_json(self, mock_svc_cls: MagicMock, client: FlaskClient) -> None:
        """Test GET /metrics/export?format=json returns JSON download."""
        mock_svc = MagicMock()
        mock_svc_cls.return_value = mock_svc
        mock_svc.export_mttr_data.return_value = '{"trend": []}'

        response = client.get("/metrics/export?format=json")
        assert response.status_code == 200
        assert response.content_type == "application/json"
        assert b"trend" in response.data

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_export_csv(self, mock_svc_cls: MagicMock, client: FlaskClient) -> None:
        """Test GET /metrics/export?format=csv returns CSV download."""
        mock_svc = MagicMock()
        mock_svc_cls.return_value = mock_svc
        mock_svc.export_mttr_data.return_value = b"period,avg_mttr_seconds,count\n2026-01,3600,5\n"

        response = client.get("/metrics/export?format=csv")
        assert response.status_code == 200
        assert "text/csv" in response.content_type

    @patch("beeper_ui.routes.metrics.MetricsService")
    def test_export_invalid_format_defaults_to_json(
        self, mock_svc_cls: MagicMock, client: FlaskClient
    ) -> None:
        """Test invalid export format falls back to json."""
        mock_svc = MagicMock()
        mock_svc_cls.return_value = mock_svc
        mock_svc.export_mttr_data.return_value = '{"trend": []}'

        response = client.get("/metrics/export?format=xml")
        assert response.status_code == 200
        mock_svc.export_mttr_data.assert_called_once_with(
            time_period="month", fmt="json"
        )


class TestMetricsServiceCaching:
    """Tests for MetricsService scroll caching."""

    @patch("beeper_ui.services.metrics_service.QdrantClient")
    def test_scroll_called_once_for_multiple_methods(
        self, mock_qdrant_cls: MagicMock
    ) -> None:
        """Test that _scroll_resolved_investigations caches results."""
        mock_client = MagicMock()
        mock_qdrant_cls.return_value = mock_client
        mock_client.scroll.side_effect = _mock_scroll_with_points(MOCK_POINTS)

        svc = MetricsService()
        svc._qdrant_client = mock_client

        svc.get_mttr_data()
        svc.get_mttr_by_service()
        svc.get_mttr_by_severity()
        svc.get_services()
        svc.get_severities()

        # scroll should only be called once due to caching
        assert mock_client.scroll.call_count == 1

        svc.close()
