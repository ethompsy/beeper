"""Tests for Investor-Ready Executive Reports (Story 7-7)."""

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import respx
from flask.testing import FlaskClient
from httpx import Response

from beeper_ui.services.executive_report_service import (
    ExecutiveReportService,
    _direction,
    _fp_direction,
    _mttr_direction,
    compute_executive_metrics,
    compute_period_comparison,
)
from beeper_ui.services.investigation_service import Investigation

# --- Test Data ---

_NOW = datetime.now(timezone.utc)


def _inv(
    id: str,
    service: str = "test-svc",
    status: str = "completed",
    started_days_ago: float = 3,
    duration_hours: float = 2,
) -> Investigation:
    """Create a test Investigation with configurable timing."""
    started = _NOW - timedelta(days=started_days_ago)
    completed = (
        started + timedelta(hours=duration_hours)
        if status == "completed"
        else None
    )
    return Investigation(
        id=id,
        status=status,
        service=service,
        severity="medium",
        condition="error_rate",
        started_at=started.isoformat(),
        completed_at=completed.isoformat() if completed else None,
        workflow_state="resolved" if status == "completed" else "investigating",
    )


MOCK_INVESTIGATIONS_API = [
    {
        "id": "inv-001",
        "status": "completed",
        "service": "payment-service",
        "severity": "high",
        "condition": "latency_spike",
        "started_at": (_NOW - timedelta(days=3)).isoformat(),
        "completed_at": (_NOW - timedelta(days=3) + timedelta(hours=2)).isoformat(),
        "workflow_state": "resolved",
    },
    {
        "id": "inv-002",
        "status": "completed",
        "service": "api-gateway",
        "severity": "medium",
        "condition": "error_rate",
        "started_at": (_NOW - timedelta(days=10)).isoformat(),
        "completed_at": (_NOW - timedelta(days=10) + timedelta(hours=4)).isoformat(),
        "workflow_state": "resolved",
    },
]

MOCK_SERVICE_LEVELS = {
    "service_levels": [
        {"name": "payments-slo", "service": "payment-service", "compliance": 0.9995},
        {"name": "api-slo", "service": "api-gateway", "compliance": 0.985},
    ]
}

MOCK_TRUST_LEVELS = [
    {
        "service_name": "payment-service",
        "trust_level": 3,
        "previous_level": 2,
        "updated_at": "2026-03-10T14:00:00+00:00",
        "reason": "Promoted after stable period",
    },
    {
        "service_name": "api-gateway",
        "trust_level": 2,
        "previous_level": 1,
        "updated_at": "2026-03-05T10:00:00+00:00",
        "reason": "First promotion",
    },
    {
        "service_name": "auth-service",
        "trust_level": 1,
        "previous_level": None,
        "updated_at": "2026-02-28T09:00:00+00:00",
        "reason": None,
    },
]


def _mock_executive_apis() -> None:
    """Set up respx mocks for executive report APIs."""
    respx.get("http://mock-operator:8080/api/v1/slo/services").mock(
        return_value=Response(200, json=MOCK_SERVICE_LEVELS)
    )
    respx.get("http://mock-operator:8080/api/v1/investigations").mock(
        return_value=Response(200, json=MOCK_INVESTIGATIONS_API)
    )
    respx.get("http://mock-operator:8080/api/v1/trust/services").mock(
        return_value=Response(200, json=MOCK_TRUST_LEVELS)
    )


# =============================================================================
# Unit Tests: compute_executive_metrics
# =============================================================================


class TestComputeExecutiveMetrics:
    """Tests for compute_executive_metrics function."""

    def test_empty_data_returns_zeros(self) -> None:
        result = compute_executive_metrics(
            investigations=[],
            slo_services=[],
            trust_configs=[],
            false_page_rate=0.0,
            period_days=30,
        )
        assert result["total_resolved"] == 0
        assert result["mttr_improvement_pct"] is None
        assert result["avg_slo_compliance"] is None
        assert result["false_page_rate"] == 0.0
        assert result["trust_progression"]["distribution"]["total"] == 0

    def test_correct_resolved_count(self) -> None:
        invs = [
            _inv("inv-1", status="completed", started_days_ago=5),
            _inv("inv-2", status="completed", started_days_ago=10),
            _inv("inv-3", status="investigating", started_days_ago=2),
        ]
        result = compute_executive_metrics(
            investigations=invs,
            slo_services=[],
            trust_configs=[],
            false_page_rate=0.0,
            period_days=30,
        )
        assert result["total_resolved"] == 2

    def test_slo_compliance_averaging(self) -> None:
        slo_services = [
            {"compliance": 0.99},
            {"compliance": 0.95},
        ]
        result = compute_executive_metrics(
            investigations=[],
            slo_services=slo_services,
            trust_configs=[],
            false_page_rate=0.0,
            period_days=30,
        )
        assert result["avg_slo_compliance"] == 0.97

    def test_trust_progression_extraction(self) -> None:
        trust_configs = [
            {
                "trust_level": 3, "previous_level": 2,
                "service_name": "svc-a",
                "updated_at": "2026-03-10", "reason": "ok",
            },
            {
                "trust_level": 1, "previous_level": None,
                "service_name": "svc-b",
                "updated_at": "2026-03-01", "reason": None,
            },
        ]
        result = compute_executive_metrics(
            investigations=[],
            slo_services=[],
            trust_configs=trust_configs,
            false_page_rate=0.0,
            period_days=30,
        )
        assert result["trust_progression"]["changes_count"] == 1
        assert result["trust_progression"]["distribution"]["total"] == 2

    def test_false_page_rate_passthrough(self) -> None:
        result = compute_executive_metrics(
            investigations=[],
            slo_services=[],
            trust_configs=[],
            false_page_rate=0.12,
            period_days=30,
        )
        assert result["false_page_rate"] == 0.12

    def test_period_filter_excludes_old(self) -> None:
        """Investigations outside the period are excluded."""
        invs = [
            _inv("inv-1", status="completed", started_days_ago=5),
            _inv("inv-2", status="completed", started_days_ago=60),
        ]
        result = compute_executive_metrics(
            investigations=invs,
            slo_services=[],
            trust_configs=[],
            false_page_rate=0.0,
            period_days=30,
        )
        assert result["total_resolved"] == 1

    def test_mttr_improvement_with_data(self) -> None:
        """MTTR improvement is computed from investigations in different weeks."""
        invs = [
            _inv("inv-1", status="completed", started_days_ago=3, duration_hours=1),
            _inv("inv-2", status="completed", started_days_ago=10, duration_hours=4),
        ]
        result = compute_executive_metrics(
            investigations=invs,
            slo_services=[],
            trust_configs=[],
            false_page_rate=0.0,
            period_days=30,
        )
        # With 2 investigations in different weeks, MTTR change should be computed
        # (may be None if only 1 week has data, but with 2 different weeks it should have a value)
        assert result["mttr_improvement_pct"] is not None

    def test_all_time_includes_everything(self) -> None:
        """period_days=None includes all investigations."""
        invs = [
            _inv("inv-1", status="completed", started_days_ago=5),
            _inv("inv-2", status="completed", started_days_ago=500),
        ]
        result = compute_executive_metrics(
            investigations=invs,
            slo_services=[],
            trust_configs=[],
            false_page_rate=0.0,
            period_days=None,
        )
        assert result["total_resolved"] == 2


# =============================================================================
# Unit Tests: compute_period_comparison
# =============================================================================


def _metrics(
    resolved: int = 10,
    mttr: float | None = None,
    slo: float | None = 0.99,
    fp: float = 0.10,
) -> dict[str, Any]:
    """Build a metrics dict for comparison tests."""
    return {
        "total_resolved": resolved,
        "mttr_improvement_pct": mttr,
        "avg_slo_compliance": slo,
        "false_page_rate": fp,
    }


class TestComputePeriodComparison:
    """Tests for compute_period_comparison function."""

    def test_improvement_direction(self) -> None:
        current = _metrics(resolved=20, mttr=-30.0, fp=0.05)
        previous = _metrics(resolved=10, slo=0.95, fp=0.10)
        result = compute_period_comparison(current, previous)
        assert result["resolved"]["direction"] == "improved"
        assert result["resolved"]["delta_pct"] == 100.0

    def test_degradation_direction(self) -> None:
        current = _metrics(resolved=5, mttr=20.0, slo=0.90, fp=0.15)
        previous = _metrics(resolved=10, slo=0.95, fp=0.10)
        result = compute_period_comparison(current, previous)
        assert result["resolved"]["direction"] == "declined"

    def test_no_change(self) -> None:
        current = _metrics(resolved=10, fp=0.10)
        previous = _metrics(resolved=10, fp=0.10)
        result = compute_period_comparison(current, previous)
        assert result["resolved"]["delta_pct"] == 0.0
        assert result["resolved"]["direction"] == "stable"

    def test_zero_denominator(self) -> None:
        current = _metrics(resolved=5, slo=None, fp=0.0)
        previous = _metrics(resolved=0, slo=None, fp=0.0)
        result = compute_period_comparison(current, previous)
        assert result["resolved"]["delta_pct"] is None
        assert result["slo_compliance"]["delta_pct"] is None
        assert result["false_page_rate"]["delta_pct"] is None

    def test_false_page_reduction_detected(self) -> None:
        current = _metrics(resolved=10, fp=0.05)
        previous = _metrics(resolved=10, fp=0.10)
        result = compute_period_comparison(current, previous)
        assert result["false_page_rate"]["delta_pct"] == -50.0
        assert result["false_page_rate"]["direction"] == "improved"


# =============================================================================
# Unit Tests: Direction helpers
# =============================================================================


class TestDirectionHelpers:
    """Tests for direction helper functions."""

    def test_direction_positive(self) -> None:
        assert _direction(10.0) == "improved"

    def test_direction_negative(self) -> None:
        assert _direction(-5.0) == "declined"

    def test_direction_zero(self) -> None:
        assert _direction(0.0) == "stable"

    def test_direction_none(self) -> None:
        assert _direction(None) == "stable"

    def test_mttr_direction_negative_is_improved(self) -> None:
        assert _mttr_direction(-20.0) == "improved"

    def test_mttr_direction_positive_is_declined(self) -> None:
        assert _mttr_direction(20.0) == "declined"

    def test_fp_direction_negative_is_improved(self) -> None:
        assert _fp_direction(-10.0) == "improved"

    def test_fp_direction_positive_is_declined(self) -> None:
        assert _fp_direction(10.0) == "declined"


# =============================================================================
# Integration Tests: ExecutiveReportService.get_report_data
# =============================================================================


class TestExecutiveReportServiceGetReportData:
    """Tests for ExecutiveReportService.get_report_data integration."""

    @respx.mock
    def test_returns_complete_structure(self) -> None:
        _mock_executive_apis()
        svc = ExecutiveReportService(operator_url="http://mock-operator:8080")
        try:
            with patch.object(svc, "_get_false_page_rate", return_value=0.05):
                data = svc.get_report_data(period="90d")
            assert "current_metrics" in data
            assert "previous_metrics" in data
            assert "comparison" in data
            assert "period" in data
            assert "period_label" in data
            assert "date_from" in data
            assert "date_to" in data
            assert data["period"] == "90d"
            assert data["period_label"] == "Last 90 Days"
        finally:
            svc.close()

    @respx.mock
    def test_90d_avoids_duplicate_noise_call(self) -> None:
        """For 90d period, prev false page rate reuses current (same noise window)."""
        _mock_executive_apis()
        svc = ExecutiveReportService(operator_url="http://mock-operator:8080")
        try:
            with patch.object(svc, "_get_false_page_rate", return_value=0.08) as mock_fp:
                data = svc.get_report_data(period="90d")
            # Should only call _get_false_page_rate once (current), not twice
            mock_fp.assert_called_once_with("90d")
            # Comparison should show stable for false page (same data)
            assert data["comparison"]["false_page_rate"]["direction"] == "stable"
        finally:
            svc.close()

    @respx.mock
    def test_all_time_has_no_comparison(self) -> None:
        _mock_executive_apis()
        svc = ExecutiveReportService(operator_url="http://mock-operator:8080")
        try:
            with patch.object(svc, "_get_false_page_rate", return_value=0.0):
                data = svc.get_report_data(period="all")
            assert data["comparison"] == {}
            assert data["date_from"] == "Inception"
        finally:
            svc.close()


# =============================================================================
# Route Tests: GET /reports/executive
# =============================================================================


def _mock_report_data() -> dict[str, Any]:
    """Build mock executive report data for route tests."""
    dist = {
        "levels": {1: 1, 2: 1, 3: 1, 4: 0, 5: 0},
        "total": 3,
    }
    return {
        "current_metrics": {
            "total_resolved": 42,
            "mttr_improvement_pct": -25.0,
            "avg_slo_compliance": 0.9925,
            "trust_progression": {
                "distribution": dist,
                "changes_count": 2,
                "changes": [{
                    "service": "svc-a",
                    "from_level": 2,
                    "to_level": 3,
                    "reason": "Promoted",
                }],
            },
            "false_page_rate": 0.05,
        },
        "previous_metrics": {"total_resolved": 30},
        "comparison": {
            "resolved": {
                "current": 42, "previous": 30,
                "delta_pct": 40.0, "direction": "improved",
            },
            "mttr": {
                "current": -25.0, "previous": None,
                "direction": "improved",
            },
            "slo_compliance": {
                "current": 0.9925, "previous": 0.98,
                "delta_pct": 1.28, "direction": "improved",
            },
            "false_page_rate": {
                "current": 0.05, "previous": 0.10,
                "delta_pct": -50.0, "direction": "improved",
            },
        },
        "period": "90d",
        "period_label": "Last 90 Days",
        "date_from": "Dec 19, 2025",
        "date_to": "Mar 18, 2026",
        "selected_period": "90d",
    }


class TestExecutiveReportRoute:
    """Tests for executive report route."""

    def _mock_service(self) -> MagicMock:
        mock_svc = MagicMock()
        mock_svc.get_report_data.return_value = _mock_report_data()
        return mock_svc

    def test_returns_200(self, client: FlaskClient) -> None:
        mock_svc = self._mock_service()
        with patch(
            "beeper_ui.routes.reports._get_executive_report_service",
            return_value=mock_svc,
        ):
            response = client.get("/reports/executive")
        assert response.status_code == 200
        mock_svc.close.assert_called_once()

    def test_htmx_returns_partial(self, client: FlaskClient) -> None:
        mock_svc = self._mock_service()
        with patch(
            "beeper_ui.routes.reports._get_executive_report_service",
            return_value=mock_svc,
        ):
            response = client.get(
                "/reports/executive", headers={"HX-Request": "true"}
            )
        assert response.status_code == 200
        html = response.data.decode()
        assert "<!DOCTYPE html>" not in html
        assert "executive-metric-card" in html

    def test_period_filter(self, client: FlaskClient) -> None:
        mock_svc = self._mock_service()
        with patch(
            "beeper_ui.routes.reports._get_executive_report_service",
            return_value=mock_svc,
        ):
            response = client.get("/reports/executive?period=30d")
        assert response.status_code == 200
        mock_svc.get_report_data.assert_called_once_with(period="30d")

    def test_invalid_period_defaults(self, client: FlaskClient) -> None:
        mock_svc = self._mock_service()
        with patch(
            "beeper_ui.routes.reports._get_executive_report_service",
            return_value=mock_svc,
        ):
            response = client.get("/reports/executive?period=invalid")
        assert response.status_code == 200
        mock_svc.get_report_data.assert_called_once_with(period="90d")

    def test_error_fallback(self, client: FlaskClient) -> None:
        mock_svc = MagicMock()
        mock_svc.get_report_data.side_effect = RuntimeError("service down")
        with patch(
            "beeper_ui.routes.reports._get_executive_report_service",
            return_value=mock_svc,
        ):
            response = client.get("/reports/executive")
        assert response.status_code == 200
        html = response.data.decode()
        assert "Unable to load executive report data" in html
        mock_svc.close.assert_called_once()

    def test_error_htmx_returns_partial(self, client: FlaskClient) -> None:
        mock_svc = MagicMock()
        mock_svc.get_report_data.side_effect = RuntimeError("service down")
        with patch(
            "beeper_ui.routes.reports._get_executive_report_service",
            return_value=mock_svc,
        ):
            response = client.get(
                "/reports/executive", headers={"HX-Request": "true"}
            )
        assert response.status_code == 200
        html = response.data.decode()
        assert "Unable to load executive report data" in html
        assert "<!DOCTYPE html>" not in html


# =============================================================================
# Template Tests
# =============================================================================


class TestExecutiveTemplateContent:
    """Tests for executive report template rendering."""

    def _mock_service(self) -> MagicMock:
        mock_svc = MagicMock()
        mock_svc.get_report_data.return_value = _mock_report_data()
        return mock_svc

    def test_metric_cards_render(self, client: FlaskClient) -> None:
        mock_svc = self._mock_service()
        with patch(
            "beeper_ui.routes.reports._get_executive_report_service",
            return_value=mock_svc,
        ):
            response = client.get("/reports/executive")
        html = response.data.decode()
        assert "executive-metric-card" in html
        assert "42" in html  # Total resolved
        assert "99.25%" in html  # SLO compliance

    def test_comparison_badges_render(self, client: FlaskClient) -> None:
        mock_svc = self._mock_service()
        with patch(
            "beeper_ui.routes.reports._get_executive_report_service",
            return_value=mock_svc,
        ):
            response = client.get("/reports/executive")
        html = response.data.decode()
        assert "badge-improved" in html
        assert "40.0% vs previous period" in html

    def test_period_buttons_have_htmx(self, client: FlaskClient) -> None:
        mock_svc = self._mock_service()
        with patch(
            "beeper_ui.routes.reports._get_executive_report_service",
            return_value=mock_svc,
        ):
            response = client.get("/reports/executive")
        html = response.data.decode()
        assert "hx-get" in html
        assert "executive-period-btn" in html

    def test_export_pdf_button(self, client: FlaskClient) -> None:
        mock_svc = self._mock_service()
        with patch(
            "beeper_ui.routes.reports._get_executive_report_service",
            return_value=mock_svc,
        ):
            response = client.get("/reports/executive")
        html = response.data.decode()
        assert "Export PDF" in html
        assert "executive-export-pdf-btn" in html
        # No inline onclick — CSP compliant (handled via addEventListener in JS)
        assert 'onclick="window.print()"' not in html

    def test_print_only_branding(self, client: FlaskClient) -> None:
        mock_svc = self._mock_service()
        with patch(
            "beeper_ui.routes.reports._get_executive_report_service",
            return_value=mock_svc,
        ):
            response = client.get("/reports/executive")
        html = response.data.decode()
        assert "print-only" in html
        assert "executive-print-header" in html

    def test_aria_landmarks(self, client: FlaskClient) -> None:
        mock_svc = self._mock_service()
        with patch(
            "beeper_ui.routes.reports._get_executive_report_service",
            return_value=mock_svc,
        ):
            response = client.get("/reports/executive")
        html = response.data.decode()
        assert 'aria-label="Key Metrics"' in html
        assert 'aria-label="Report Period"' in html
        assert 'aria-label="Trust Level Distribution"' in html

    def test_trust_distribution_bar(self, client: FlaskClient) -> None:
        mock_svc = self._mock_service()
        with patch(
            "beeper_ui.routes.reports._get_executive_report_service",
            return_value=mock_svc,
        ):
            response = client.get("/reports/executive")
        html = response.data.decode()
        assert "executive-trust-bar" in html
        assert "executive-trust-segment" in html

    def test_trust_changes_listed(self, client: FlaskClient) -> None:
        mock_svc = self._mock_service()
        with patch(
            "beeper_ui.routes.reports._get_executive_report_service",
            return_value=mock_svc,
        ):
            response = client.get("/reports/executive")
        html = response.data.decode()
        assert "executive-change-entry" in html
        assert "svc-a" in html

    @pytest.mark.xfail(
        strict=True,
        reason="Top-nav removed in Story 3.2 layout shell migration. The old "
        "`<a href=\"/reports/executive\">Reports</a>` markup no longer exists. "
        "Story 3.3 introduces sidebar nav with a different macro-based markup. "
        "When that lands this test becomes XPASS — REWRITE the assertion "
        "against the new sidebar HTML and remove this xfail marker.",
    )
    def test_navigation_link_exists(self, client: FlaskClient) -> None:
        mock_svc = self._mock_service()
        with patch(
            "beeper_ui.routes.reports._get_executive_report_service",
            return_value=mock_svc,
        ):
            response = client.get("/reports/executive")
        html = response.data.decode()
        assert '<a href="/reports/executive">Reports</a>' in html

    def test_command_palette_has_executive_command(self) -> None:
        """command-palette.js contains Executive Report entry with correct href and chord."""
        js_path = os.path.join(
            os.path.dirname(__file__),
            "..", "beeper_ui", "static", "js", "command-palette.js",
        )
        content = open(js_path).read()
        assert '"Executive Report"' in content
        assert '"/reports/executive"' in content
        assert 'e: "/reports/executive"' in content

    def test_export_pdf_uses_event_listener(self) -> None:
        """Export PDF button uses addEventListener, not inline onclick (CSP)."""
        js_path = os.path.join(
            os.path.dirname(__file__),
            "..", "beeper_ui", "static", "js", "command-palette.js",
        )
        content = open(js_path).read()
        assert "executive-export-pdf-btn" in content
        assert "window.print()" in content
