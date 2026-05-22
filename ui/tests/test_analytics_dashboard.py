"""Tests for MTTR, Impact & Trust Trend Dashboards (Story 7-6)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import respx
from flask.testing import FlaskClient
from httpx import Response

from beeper_ui.services.analytics_service import (
    AnalyticsService,
    compute_impact_trends,
    compute_mttr_change_pct,
    compute_mttr_trends,
    compute_mttr_trends_by_service,
    compute_trust_changes,
    compute_trust_distribution,
)
from beeper_ui.services.investigation_service import Investigation

# --- Test Data ---

_NOW = datetime.now(timezone.utc)


def _inv(
    id: str,
    service: str = "test-svc",
    status: str = "completed",
    started_hours_ago: float = 24,
    duration_hours: float = 2,
    started_days_ago: float | None = None,
) -> Investigation:
    """Create a test Investigation with configurable timing."""
    if started_days_ago is not None:
        started = _NOW - timedelta(days=started_days_ago)
    else:
        started = _NOW - timedelta(hours=started_hours_ago)
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


MOCK_SERVICE_LEVELS = {
    "service_levels": [
        {
            "name": "payments-slo",
            "service": "payment-service",
            "condition": "healthy",
            "compliance": 0.9995,
            "burn_rate": 0.5,
        },
        {
            "name": "api-slo",
            "service": "api-gateway",
            "condition": "warning",
            "compliance": 0.985,
            "burn_rate": 3.2,
        },
    ]
}

MOCK_INVESTIGATIONS = [
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
    {
        "id": "inv-003",
        "status": "investigating",
        "service": "payment-service",
        "severity": "critical",
        "condition": "slo_breach",
        "started_at": (_NOW - timedelta(days=1)).isoformat(),
        "completed_at": None,
        "workflow_state": "investigating",
    },
]

MOCK_TRUST_LEVELS = [
    {
        "service_name": "payment-service",
        "trust_level": 3,
        "updated_at": "2026-03-10T14:00:00+00:00",
        "previous_level": 2,
        "reason": "Promoted after stable period",
    },
    {
        "service_name": "api-gateway",
        "trust_level": 2,
        "updated_at": "2026-03-05T10:00:00+00:00",
        "previous_level": 1,
        "reason": "First promotion",
    },
    {
        "service_name": "auth-service",
        "trust_level": 1,
        "updated_at": "2026-02-28T09:00:00+00:00",
        "previous_level": None,
        "reason": None,
    },
]


def _mock_analytics_apis() -> None:
    """Set up respx mocks for analytics dashboard APIs."""
    respx.get("http://mock-operator:8080/api/v1/slo/services").mock(
        return_value=Response(200, json=MOCK_SERVICE_LEVELS)
    )
    respx.get("http://mock-operator:8080/api/v1/investigations").mock(
        return_value=Response(200, json=MOCK_INVESTIGATIONS)
    )
    respx.get("http://mock-operator:8080/api/v1/trust/services").mock(
        return_value=Response(200, json=MOCK_TRUST_LEVELS)
    )


def _mock_service_filtered_apis(service: str) -> None:
    """Set up respx mocks for service-filtered analytics."""
    respx.get("http://mock-operator:8080/api/v1/slo/services").mock(
        return_value=Response(200, json=MOCK_SERVICE_LEVELS)
    )
    matching = [inv for inv in MOCK_INVESTIGATIONS if inv["service"] == service]
    respx.get(
        "http://mock-operator:8080/api/v1/investigations",
        params={"service": service},
    ).mock(return_value=Response(200, json=matching))
    respx.get("http://mock-operator:8080/api/v1/trust/services").mock(
        return_value=Response(200, json=MOCK_TRUST_LEVELS)
    )


# =============================================================================
# Unit Tests: compute_mttr_trends
# =============================================================================


class TestComputeMttrTrends:
    """Tests for compute_mttr_trends helper."""

    def test_empty_investigations(self) -> None:
        result = compute_mttr_trends([], num_weeks=12)
        assert result == []

    def test_only_active_investigations(self) -> None:
        """Non-completed investigations are excluded."""
        invs = [_inv("inv-1", status="investigating")]
        result = compute_mttr_trends(invs, num_weeks=12)
        assert result == []

    def test_single_week(self) -> None:
        """One resolved investigation produces one week entry."""
        invs = [_inv("inv-1", started_hours_ago=48, duration_hours=3)]
        result = compute_mttr_trends(invs, num_weeks=12)
        assert len(result) == 1
        assert result[0]["avg_mttr_hours"] == 3.0
        assert result[0]["count"] == 1

    def test_multiple_weeks(self) -> None:
        """Investigations in different weeks produce separate entries."""
        invs = [
            _inv("inv-1", started_days_ago=3, duration_hours=2),
            _inv("inv-2", started_days_ago=10, duration_hours=4),
        ]
        result = compute_mttr_trends(invs, num_weeks=12)
        # Should have 1 or 2 entries depending on whether they're in same week
        assert len(result) >= 1
        for entry in result:
            assert "week" in entry
            assert "avg_mttr_hours" in entry
            assert "count" in entry

    def test_excludes_investigations_before_cutoff(self) -> None:
        """Investigations older than num_weeks are excluded."""
        invs = [_inv("inv-1", started_days_ago=100, duration_hours=2)]
        result = compute_mttr_trends(invs, num_weeks=4)
        assert result == []

    def test_only_counts_completed_with_timestamps(self) -> None:
        """Requires both started_at and completed_at."""
        inv = Investigation(
            id="inv-no-complete",
            status="completed",
            service="test",
            severity="medium",
            condition="error",
            started_at=_NOW.isoformat(),
            completed_at=None,
        )
        result = compute_mttr_trends([inv], num_weeks=12)
        assert result == []


# =============================================================================
# Unit Tests: compute_mttr_trends_by_service
# =============================================================================


class TestComputeMttrTrendsByService:
    """Tests for compute_mttr_trends_by_service helper."""

    def test_empty(self) -> None:
        result = compute_mttr_trends_by_service([], num_weeks=12)
        assert result == []

    def test_groups_by_service(self) -> None:
        invs = [
            _inv("inv-1", service="svc-a", started_days_ago=3, duration_hours=2),
            _inv("inv-2", service="svc-b", started_days_ago=3, duration_hours=4),
        ]
        result = compute_mttr_trends_by_service(invs, num_weeks=12)
        services = [r["service"] for r in result]
        assert "svc-a" in services
        assert "svc-b" in services


# =============================================================================
# Unit Tests: compute_mttr_change_pct
# =============================================================================


class TestComputeMttrChangePct:
    """Tests for compute_mttr_change_pct helper."""

    def test_improvement(self) -> None:
        """MTTR decreased → negative percentage."""
        trends = [
            {"week": "2026-W08", "avg_mttr_hours": 10.0, "count": 5},
            {"week": "2026-W09", "avg_mttr_hours": 5.0, "count": 3},
        ]
        result = compute_mttr_change_pct(trends)
        assert result == -50.0

    def test_degradation(self) -> None:
        """MTTR increased → positive percentage."""
        trends = [
            {"week": "2026-W08", "avg_mttr_hours": 5.0, "count": 3},
            {"week": "2026-W09", "avg_mttr_hours": 10.0, "count": 5},
        ]
        result = compute_mttr_change_pct(trends)
        assert result == 100.0

    def test_no_data(self) -> None:
        """Insufficient data returns None."""
        assert compute_mttr_change_pct([]) is None
        assert compute_mttr_change_pct([{"week": "W1", "avg_mttr_hours": 5.0}]) is None

    def test_zero_oldest(self) -> None:
        """Zero oldest MTTR returns None (avoid division by zero)."""
        trends = [
            {"week": "2026-W08", "avg_mttr_hours": 0.0, "count": 1},
            {"week": "2026-W09", "avg_mttr_hours": 5.0, "count": 1},
        ]
        assert compute_mttr_change_pct(trends) is None


# =============================================================================
# Unit Tests: compute_impact_trends
# =============================================================================


class TestComputeImpactTrends:
    """Tests for compute_impact_trends helper."""

    def test_empty(self) -> None:
        result = compute_impact_trends([], [], num_weeks=12)
        assert result == []

    def test_aggregates_investigation_counts(self) -> None:
        invs = [
            _inv("inv-1", started_days_ago=3),
            _inv("inv-2", started_days_ago=3),
            _inv("inv-3", started_days_ago=10),
        ]
        slo_services = [{"compliance": 0.99}]
        result = compute_impact_trends(slo_services, invs, num_weeks=12)
        total_count = sum(t["investigation_count"] for t in result)
        assert total_count == 3

    def test_includes_compliance(self) -> None:
        invs = [_inv("inv-1", started_days_ago=3)]
        slo_services = [{"compliance": 0.99}, {"compliance": 0.98}]
        result = compute_impact_trends(slo_services, invs, num_weeks=12)
        assert len(result) >= 1
        assert result[0]["avg_compliance"] == 0.985


# =============================================================================
# Unit Tests: compute_trust_distribution
# =============================================================================


class TestComputeTrustDistribution:
    """Tests for compute_trust_distribution helper."""

    def test_empty(self) -> None:
        result = compute_trust_distribution([])
        assert result["total"] == 0
        assert result["levels"] == {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    def test_all_at_tl1(self) -> None:
        configs = [
            {"trust_level": 1},
            {"trust_level": 1},
            {"trust_level": 1},
        ]
        result = compute_trust_distribution(configs)
        assert result["levels"][1] == 3
        assert result["total"] == 3

    def test_mixed_distribution(self) -> None:
        configs = [
            {"trust_level": 1},
            {"trust_level": 2},
            {"trust_level": 3},
            {"trust_level": 3},
            {"trust_level": 5},
        ]
        result = compute_trust_distribution(configs)
        assert result["levels"] == {1: 1, 2: 1, 3: 2, 4: 0, 5: 1}
        assert result["total"] == 5


# =============================================================================
# Unit Tests: compute_trust_changes
# =============================================================================


class TestComputeTrustChanges:
    """Tests for compute_trust_changes helper."""

    def test_empty(self) -> None:
        result = compute_trust_changes([])
        assert result == []

    def test_filters_to_configs_with_previous_level(self) -> None:
        configs = [
            {
                "service_name": "svc-a",
                "trust_level": 3,
                "previous_level": 2,
                "updated_at": "2026-03-10T14:00:00+00:00",
                "reason": "Promoted",
            },
            {
                "service_name": "svc-b",
                "trust_level": 1,
                "previous_level": None,
                "updated_at": "2026-02-28T09:00:00+00:00",
                "reason": None,
            },
        ]
        result = compute_trust_changes(configs)
        assert len(result) == 1
        assert result[0]["service"] == "svc-a"
        assert result[0]["from_level"] == 2
        assert result[0]["to_level"] == 3

    def test_sorts_by_updated_at_desc(self) -> None:
        configs = [
            {
                "service_name": "svc-a",
                "trust_level": 2,
                "previous_level": 1,
                "updated_at": "2026-03-01T10:00:00+00:00",
                "reason": None,
            },
            {
                "service_name": "svc-b",
                "trust_level": 3,
                "previous_level": 2,
                "updated_at": "2026-03-10T14:00:00+00:00",
                "reason": None,
            },
        ]
        result = compute_trust_changes(configs)
        assert len(result) == 2
        assert result[0]["service"] == "svc-b"  # Most recent first
        assert result[1]["service"] == "svc-a"


# =============================================================================
# Integration Tests: AnalyticsService.get_dashboard_data
# =============================================================================


class TestAnalyticsServiceGetDashboardData:
    """Tests for AnalyticsService.get_dashboard_data integration."""

    @respx.mock
    def test_returns_all_sections(self) -> None:
        _mock_analytics_apis()
        svc = AnalyticsService(operator_url="http://mock-operator:8080")
        try:
            data = svc.get_dashboard_data(period_weeks=12)
            assert "mttr_trends" in data
            assert "mttr_change_pct" in data
            assert "impact_trends" in data
            assert "trust_distribution" in data
            assert "trust_changes" in data
            assert "service_names" in data
            assert "period_weeks" in data
            assert data["period_weeks"] == 12
        finally:
            svc.close()

    @respx.mock
    def test_service_filter(self) -> None:
        _mock_service_filtered_apis("payment-service")
        svc = AnalyticsService(operator_url="http://mock-operator:8080")
        try:
            data = svc.get_dashboard_data(
                period_weeks=12, service_filter="payment-service"
            )
            assert data["service_filter"] == "payment-service"
        finally:
            svc.close()


# =============================================================================
# Route Tests: GET /analytics/
# =============================================================================


class TestAnalyticsRoute:
    """Tests for analytics dashboard route."""

    @respx.mock
    def test_returns_200(self, client: FlaskClient) -> None:
        _mock_analytics_apis()
        response = client.get("/analytics/")
        assert response.status_code == 200

    @respx.mock
    def test_contains_all_three_sections(self, client: FlaskClient) -> None:
        _mock_analytics_apis()
        response = client.get("/analytics/")
        html = response.data.decode()
        assert "MTTR Trends" in html
        assert "Customer Impact Trends" in html
        assert "Trust Level Progression" in html

    @respx.mock
    def test_htmx_returns_partial(self, client: FlaskClient) -> None:
        _mock_analytics_apis()
        response = client.get(
            "/analytics/", headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        html = response.data.decode()
        # Partial should NOT contain full page structure
        assert "<!DOCTYPE html>" not in html
        # But should contain dashboard content
        assert "MTTR Trends" in html

    @respx.mock
    def test_service_filter(self, client: FlaskClient) -> None:
        _mock_service_filtered_apis("payment-service")
        response = client.get("/analytics/?service=payment-service")
        assert response.status_code == 200

    @respx.mock
    def test_period_filter_4w(self, client: FlaskClient) -> None:
        _mock_analytics_apis()
        response = client.get("/analytics/?period=4")
        assert response.status_code == 200
        html = response.data.decode()
        assert "4 weeks" in html

    @respx.mock
    def test_invalid_period_defaults_to_12(self, client: FlaskClient) -> None:
        _mock_analytics_apis()
        response = client.get("/analytics/?period=99")
        assert response.status_code == 200
        html = response.data.decode()
        assert "12 weeks" in html  # Default period button active

    @respx.mock
    def test_invalid_service_name_returns_400(self, client: FlaskClient) -> None:
        response = client.get("/analytics/?service=../../../etc/passwd")
        assert response.status_code == 400


# =============================================================================
# Template Tests
# =============================================================================


class TestAnalyticsTemplateContent:
    """Tests for analytics template rendering."""

    @respx.mock
    def test_mttr_bar_chart_rendered(self, client: FlaskClient) -> None:
        _mock_analytics_apis()
        response = client.get("/analytics/")
        html = response.data.decode()
        assert "analytics-bar-chart" in html
        assert "analytics-bar-mttr" in html

    @respx.mock
    def test_trust_distribution_rendered(self, client: FlaskClient) -> None:
        _mock_analytics_apis()
        response = client.get("/analytics/")
        html = response.data.decode()
        assert "trust-distribution-bar" in html
        assert "trust-dist-segment" in html

    @respx.mock
    def test_trust_change_timeline_rendered(self, client: FlaskClient) -> None:
        _mock_analytics_apis()
        response = client.get("/analytics/")
        html = response.data.decode()
        assert "trust-change-timeline" in html
        assert "trust-change-entry" in html
        # Should show at least one trust change
        assert "payment-service" in html

    @respx.mock
    def test_mttr_change_badge_rendered(self, client: FlaskClient) -> None:
        _mock_analytics_apis()
        response = client.get("/analytics/")
        html = response.data.decode()
        # Mock data has 2 completed investigations in different weeks — badge must render
        assert "mttr-change-badge" in html

    @respx.mock
    def test_aria_region_landmarks(self, client: FlaskClient) -> None:
        _mock_analytics_apis()
        response = client.get("/analytics/")
        html = response.data.decode()
        assert 'aria-label="MTTR Trends"' in html
        assert 'aria-label="Customer Impact Trends"' in html
        assert 'aria-label="Trust Level Progression"' in html

    @respx.mock
    def test_period_buttons_preserve_service_filter(self, client: FlaskClient) -> None:
        _mock_service_filtered_apis("payment-service")
        response = client.get("/analytics/?service=payment-service&period=12")
        html = response.data.decode()
        # Period buttons should include service param
        assert "service=payment-service" in html


# =============================================================================
# Command Palette Tests
# =============================================================================


class TestAnalyticsCommandPalette:
    """Tests for analytics command in command palette."""

    @respx.mock
    def test_command_palette_has_analytics(self, client: FlaskClient) -> None:
        _mock_analytics_apis()
        response = client.get("/analytics/")
        html = response.data.decode()
        # Command palette script should contain analytics entry
        assert "/analytics/" in html

    @pytest.mark.xfail(
        strict=True,
        reason="Top-nav removed in Story 3.2 layout shell migration. The old "
        "`<a href=\"/analytics/\">Analytics</a>` markup no longer exists. "
        "Story 3.3 introduces sidebar nav with a different macro-based markup "
        "(likely `<a href=\"/analytics/\" class=\"sidebar-link\" "
        "aria-current=\"page\">Analytics</a>`). When that lands this test "
        "becomes XPASS — REWRITE the assertion against the new sidebar HTML "
        "and remove this xfail marker.",
    )
    @respx.mock
    def test_navigation_link_exists(self, client: FlaskClient) -> None:
        _mock_analytics_apis()
        response = client.get("/analytics/")
        html = response.data.decode()
        assert '<a href="/analytics/">Analytics</a>' in html


# =============================================================================
# Error Fallback Tests
# =============================================================================


class TestAnalyticsErrorFallback:
    """Tests for analytics dashboard error handling."""

    def test_error_renders_error_message(self, client: FlaskClient) -> None:
        """When service raises, the dashboard renders with error message."""
        mock_svc = MagicMock()
        mock_svc.get_dashboard_data.side_effect = RuntimeError("service down")
        with patch(
            "beeper_ui.routes.analytics._get_analytics_service",
            return_value=mock_svc,
        ):
            response = client.get("/analytics/")
        assert response.status_code == 200
        html = response.data.decode()
        assert "Unable to load analytics data" in html
        mock_svc.close.assert_called_once()

    def test_error_htmx_returns_partial(self, client: FlaskClient) -> None:
        """HTMX error fallback returns partial template, not full page."""
        mock_svc = MagicMock()
        mock_svc.get_dashboard_data.side_effect = RuntimeError("service down")
        with patch(
            "beeper_ui.routes.analytics._get_analytics_service",
            return_value=mock_svc,
        ):
            response = client.get(
                "/analytics/", headers={"HX-Request": "true"}
            )
        assert response.status_code == 200
        html = response.data.decode()
        assert "Unable to load analytics data" in html
        assert "<!DOCTYPE html>" not in html
