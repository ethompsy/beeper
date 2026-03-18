"""Tests for reliability score per service (Story 7-5)."""

from datetime import datetime, timedelta, timezone

import respx
from flask.testing import FlaskClient
from httpx import Response

from beeper_ui.services.investigation_service import Investigation
from beeper_ui.services.service_health_service import (
    ServiceHealthService,
    compute_reliability_score,
)

# --- Test Data ---

_NOW = datetime.now(timezone.utc)


def _inv(
    id: str,
    service: str = "test-svc",
    status: str = "completed",
    started_hours_ago: float = 24,
    duration_hours: float = 2,
) -> Investigation:
    """Create a test Investigation with configurable timing."""
    started = _NOW - timedelta(hours=started_hours_ago)
    completed = started + timedelta(hours=duration_hours) if status == "completed" else None
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


# =============================================================================
# Unit Tests: compute_reliability_score
# =============================================================================


class TestComputeReliabilityScore:
    """Tests for compute_reliability_score helper."""

    def test_perfect_score(self) -> None:
        """Full compliance, no incidents → score near 100."""
        result = compute_reliability_score(
            compliance=1.0,
            investigations=[],
        )
        assert result["score"] == 85  # 40 + 30 + 15 (neutral MTTR)
        assert result["trend"] == "stable"
        assert result["slo_component"] == 40.0
        assert result["frequency_component"] == 30.0
        assert result["mttr_component"] == 15.0
        assert result["below_threshold"] is False
        assert result["score_class"] == "good"

    def test_zero_compliance_no_incidents(self) -> None:
        """Zero compliance, no incidents → low score."""
        result = compute_reliability_score(
            compliance=0.0,
            investigations=[],
        )
        assert result["score"] == 45  # 0 + 30 + 15
        assert result["slo_component"] == 0.0

    def test_none_compliance(self) -> None:
        """None compliance treated as 0."""
        result = compute_reliability_score(
            compliance=None,
            investigations=[],
        )
        assert result["slo_component"] == 0.0

    def test_incident_frequency_max_penalty(self) -> None:
        """10+ incidents in lookback → 0 frequency component."""
        invs = [_inv(f"inv-{i}", started_hours_ago=i * 24) for i in range(12)]
        result = compute_reliability_score(
            compliance=1.0,
            investigations=invs,
        )
        assert result["frequency_component"] == 0.0

    def test_incident_frequency_partial(self) -> None:
        """5 incidents → half frequency component."""
        invs = [_inv(f"inv-{i}", started_hours_ago=i * 24) for i in range(5)]
        result = compute_reliability_score(
            compliance=1.0,
            investigations=invs,
        )
        assert result["frequency_component"] == 15.0

    def test_mttr_fast_resolution(self) -> None:
        """Quick resolution (0h) → full MTTR score."""
        invs = [_inv("inv-1", started_hours_ago=24, duration_hours=0.01)]
        result = compute_reliability_score(
            compliance=1.0,
            investigations=invs,
        )
        # Very close to 30
        assert result["mttr_component"] >= 29.0

    def test_mttr_slow_resolution(self) -> None:
        """24h+ resolution → 0 MTTR score."""
        invs = [_inv("inv-1", started_hours_ago=48, duration_hours=25)]
        result = compute_reliability_score(
            compliance=1.0,
            investigations=invs,
        )
        assert result["mttr_component"] == 0.0

    def test_mttr_neutral_when_no_resolved(self) -> None:
        """No resolved investigations → neutral 15 MTTR."""
        invs = [_inv("inv-1", status="investigating", started_hours_ago=24)]
        result = compute_reliability_score(
            compliance=1.0,
            investigations=invs,
        )
        assert result["mttr_component"] == 15.0

    def test_score_clamped_0_100(self) -> None:
        """Score is always 0-100."""
        result = compute_reliability_score(
            compliance=1.0,
            investigations=[],
        )
        assert 0 <= result["score"] <= 100

    def test_below_threshold_flag(self) -> None:
        """Score below threshold is flagged."""
        # 10+ incidents + 0 compliance → low score
        invs = [_inv(f"inv-{i}", started_hours_ago=i * 24, duration_hours=20) for i in range(10)]
        result = compute_reliability_score(
            compliance=0.0,
            investigations=invs,
            threshold=70,
        )
        assert result["below_threshold"] is True
        assert result["score_class"] in ("warning", "critical")

    def test_above_threshold_not_flagged(self) -> None:
        """Score above threshold is not flagged."""
        result = compute_reliability_score(
            compliance=1.0,
            investigations=[],
            threshold=70,
        )
        assert result["below_threshold"] is False

    def test_custom_threshold(self) -> None:
        """Custom threshold works."""
        result = compute_reliability_score(
            compliance=1.0,
            investigations=[],
            threshold=90,
        )
        # Score is 85, below custom threshold of 90
        assert result["below_threshold"] is True

    def test_old_investigations_excluded(self) -> None:
        """Investigations outside lookback window are excluded."""
        old_inv = _inv("inv-old", started_hours_ago=31 * 24)  # 31 days ago
        result = compute_reliability_score(
            compliance=1.0,
            investigations=[old_inv],
            lookback_days=30,
        )
        # Old investigation not counted
        assert result["frequency_component"] == 30.0

    def test_score_class_critical(self) -> None:
        """Score <= 40 yields score_class 'critical'."""
        # 0 compliance + many incidents + slow MTTR → very low score
        invs = [_inv(f"inv-{i}", started_hours_ago=i * 24, duration_hours=25) for i in range(10)]
        result = compute_reliability_score(
            compliance=0.0,
            investigations=invs,
        )
        assert result["score"] <= 40
        assert result["score_class"] == "critical"

    def test_score_class_warning(self) -> None:
        """Score 41-69 yields score_class 'warning'."""
        result = compute_reliability_score(
            compliance=0.5,
            investigations=[],
            threshold=70,
        )
        # 20 + 30 + 15 = 65
        assert result["score"] == 65
        assert result["score_class"] == "warning"

    def test_score_class_good(self) -> None:
        """Score >= threshold yields score_class 'good'."""
        result = compute_reliability_score(
            compliance=1.0,
            investigations=[],
            threshold=70,
        )
        assert result["score"] >= 70
        assert result["score_class"] == "good"


# =============================================================================
# Unit Tests: Trend Calculation
# =============================================================================


class TestReliabilityTrend:
    """Tests for reliability score trend calculation."""

    def test_stable_with_no_investigations(self) -> None:
        """No investigations → stable trend."""
        result = compute_reliability_score(compliance=1.0, investigations=[])
        assert result["trend"] == "stable"

    def test_improving_trend(self) -> None:
        """More incidents last week than this week → improving."""
        # Need investigations in BOTH windows for trend to compute.
        # Many incidents 8-14 days ago, 1 in last 7 days → current better.
        invs = [
            _inv("inv-recent", started_hours_ago=2 * 24, duration_hours=1),
        ] + [
            _inv(f"inv-old-{i}", started_hours_ago=(8 + i) * 24, duration_hours=2)
            for i in range(6)
        ]
        result = compute_reliability_score(
            compliance=1.0,
            investigations=invs,
        )
        assert result["trend"] == "improving"

    def test_declining_trend(self) -> None:
        """More incidents this week than last → declining."""
        # Many incidents in last 7 days, 1 in previous window.
        invs = [
            _inv(f"inv-new-{i}", started_hours_ago=(1 + i) * 24, duration_hours=2)
            for i in range(6)
        ] + [
            _inv("inv-old", started_hours_ago=10 * 24, duration_hours=1),
        ]
        result = compute_reliability_score(
            compliance=1.0,
            investigations=invs,
        )
        assert result["trend"] == "declining"

    def test_stable_when_similar(self) -> None:
        """Similar incident counts in both windows → stable."""
        invs = [
            _inv("inv-1", started_hours_ago=2 * 24, duration_hours=2),
            _inv("inv-2", started_hours_ago=10 * 24, duration_hours=2),
        ]
        result = compute_reliability_score(
            compliance=1.0,
            investigations=invs,
        )
        assert result["trend"] == "stable"


# =============================================================================
# Integration Tests: ServiceHealthService with reliability score
# =============================================================================

MOCK_SERVICE_LEVELS = {
    "service_levels": [
        {
            "name": "payments-slo",
            "service": "payment-service",
            "condition": "healthy",
            "compliance": 0.9995,
            "burn_rate": 0.5,
            "error_budget_remaining": 0.85,
            "is_frozen": False,
        },
        {
            "name": "api-slo",
            "service": "api-gateway",
            "condition": "warning",
            "compliance": 0.5,
            "burn_rate": 3.2,
            "error_budget_remaining": 0.25,
            "is_frozen": False,
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
        "started_at": (_NOW - timedelta(hours=48)).isoformat(),
        "completed_at": (_NOW - timedelta(hours=46)).isoformat(),
        "workflow_state": "resolved",
    },
]

MOCK_TRUST_LEVELS = [
    {"service_name": "payment-service", "trust_level": 3},
    {"service_name": "api-gateway", "trust_level": 2},
]


def _mock_list_apis() -> None:
    """Set up respx mocks for service list APIs."""
    respx.get("http://mock-operator:8080/api/v1/slo/services").mock(
        return_value=Response(200, json=MOCK_SERVICE_LEVELS)
    )
    respx.get("http://mock-operator:8080/api/v1/investigations").mock(
        return_value=Response(200, json=MOCK_INVESTIGATIONS)
    )
    respx.get("http://mock-operator:8080/api/v1/trust/services").mock(
        return_value=Response(200, json=MOCK_TRUST_LEVELS)
    )


MOCK_SERVICE_DETAIL = {
    "name": "payments-slo",
    "service": "payment-service",
    "condition": "healthy",
    "compliance": 0.9995,
    "burn_rate": 0.5,
    "error_budget_remaining": 0.85,
    "is_frozen": False,
}

MOCK_BUDGET = {
    "name": "payments-slo",
    "error_budget_remaining": 0.85,
}

MOCK_TRUST_DETAIL = {
    "service_name": "payment-service",
    "trust_level": 3,
}


def _mock_detail_apis() -> None:
    """Set up respx mocks for service detail APIs."""
    respx.get("http://mock-operator:8080/api/v1/slo/services").mock(
        return_value=Response(200, json=MOCK_SERVICE_LEVELS)
    )
    respx.get("http://mock-operator:8080/api/v1/slo/services/payments-slo").mock(
        return_value=Response(200, json=MOCK_SERVICE_DETAIL)
    )
    respx.get("http://mock-operator:8080/api/v1/slo/services/payments-slo/budget").mock(
        return_value=Response(200, json=MOCK_BUDGET)
    )
    respx.get(
        "http://mock-operator:8080/api/v1/investigations",
        params={"service": "payment-service"},
    ).mock(return_value=Response(200, json=MOCK_INVESTIGATIONS))
    respx.get(
        "http://mock-operator:8080/api/v1/trust/services/payment-service"
    ).mock(return_value=Response(200, json=MOCK_TRUST_DETAIL))


class TestServiceListReliabilityScore:
    """Tests that service list includes reliability scores."""

    @respx.mock
    def test_service_list_includes_reliability_score(self) -> None:
        """get_service_list() includes reliability_score in each service."""
        _mock_list_apis()
        svc = ServiceHealthService(operator_url="http://mock-operator:8080")
        try:
            services = svc.get_service_list()
            for s in services:
                assert "reliability_score" in s
                rs = s["reliability_score"]
                assert "score" in rs
                assert "trend" in rs
                assert 0 <= rs["score"] <= 100
        finally:
            svc.close()

    @respx.mock
    def test_sort_by_reliability(self) -> None:
        """sort_by='reliability' sorts services by score ascending."""
        _mock_list_apis()
        svc = ServiceHealthService(operator_url="http://mock-operator:8080")
        try:
            services = svc.get_service_list(sort_by="reliability")
            scores = [s["reliability_score"]["score"] for s in services]
            assert scores == sorted(scores)
        finally:
            svc.close()

    @respx.mock
    def test_default_sort_is_health_status(self) -> None:
        """Default sort is by health status (critical first)."""
        _mock_list_apis()
        svc = ServiceHealthService(operator_url="http://mock-operator:8080")
        try:
            services = svc.get_service_list()
            statuses = [s["health_status"] for s in services]
            status_order = {"critical": 0, "warning": 1, "healthy": 2}
            assert statuses == sorted(statuses, key=lambda s: status_order.get(s, 3))
        finally:
            svc.close()


class TestServiceDetailReliabilityScore:
    """Tests that service detail includes reliability score."""

    @respx.mock
    def test_service_detail_includes_reliability_score(self) -> None:
        """get_service_detail() includes reliability_score."""
        _mock_detail_apis()
        svc = ServiceHealthService(operator_url="http://mock-operator:8080")
        try:
            detail = svc.get_service_detail("payment-service")
            assert detail is not None
            assert "reliability_score" in detail
            rs = detail["reliability_score"]
            assert "score" in rs
            assert "trend" in rs
            assert "slo_component" in rs
            assert "frequency_component" in rs
            assert "mttr_component" in rs
            assert "below_threshold" in rs
        finally:
            svc.close()


# =============================================================================
# Route Tests
# =============================================================================


class TestServiceListSortRoute:
    """Tests for sort query parameter on service list route."""

    @respx.mock
    def test_sort_by_reliability_route(self, client: FlaskClient) -> None:
        """GET /services/?sort=reliability returns sorted list."""
        _mock_list_apis()
        response = client.get("/services/?sort=reliability")
        assert response.status_code == 200
        html = response.data.decode()
        assert "By Reliability" in html
        assert "Reliability" in html

    @respx.mock
    def test_sort_by_status_route(self, client: FlaskClient) -> None:
        """GET /services/?sort=status returns status-sorted list."""
        _mock_list_apis()
        response = client.get("/services/?sort=status")
        assert response.status_code == 200
        html = response.data.decode()
        assert "By Status" in html

    @respx.mock
    def test_sort_button_active_state_default(self, client: FlaskClient) -> None:
        """Default view shows 'By Status' sort button as active."""
        _mock_list_apis()
        response = client.get("/services/")
        html = response.data.decode()
        # By Status button should have active class in default view
        assert 'sort=status' in html
        assert 'sort=reliability' in html
        # The status button should be active (current_sort defaults to "status")
        # Check that "By Status" button line includes "active"
        import re
        status_btn = re.search(r'<button[^>]*sort=status[^>]*>By Status</button>', html)
        assert status_btn is not None
        assert "active" in status_btn.group(0)

    @respx.mock
    def test_sort_button_active_state_reliability(self, client: FlaskClient) -> None:
        """Reliability sort view shows 'By Reliability' sort button as active."""
        _mock_list_apis()
        response = client.get("/services/?sort=reliability")
        html = response.data.decode()
        import re
        reliability_btn = re.search(r'<button[^>]*sort=reliability[^>]*>By Reliability</button>', html)
        assert reliability_btn is not None
        assert "active" in reliability_btn.group(0)


class TestServiceDetailReliabilityRoute:
    """Tests for reliability score display in service detail."""

    @respx.mock
    def test_detail_shows_reliability_score(self, client: FlaskClient) -> None:
        """Service detail page displays reliability score with ARIA meter."""
        _mock_detail_apis()
        response = client.get("/services/payment-service")
        assert response.status_code == 200
        html = response.data.decode()
        assert 'role="meter"' in html
        assert "aria-valuemin" in html
        assert "aria-valuemax" in html
        assert "aria-valuenow" in html
        assert "Reliability Score" in html

    @respx.mock
    def test_detail_shows_trend_indicator(self, client: FlaskClient) -> None:
        """Service detail page displays trend indicator."""
        _mock_detail_apis()
        response = client.get("/services/payment-service")
        assert response.status_code == 200
        html = response.data.decode()
        assert "reliability-trend" in html

    @respx.mock
    def test_detail_shows_breakdown(self, client: FlaskClient) -> None:
        """Service detail page displays contributing factors breakdown."""
        _mock_detail_apis()
        response = client.get("/services/payment-service")
        assert response.status_code == 200
        html = response.data.decode()
        assert "SLO Compliance (40%)" in html
        assert "Incident Frequency (30%)" in html
        assert "MTTR (30%)" in html


class TestServiceListReliabilityDisplay:
    """Tests for reliability score display in service list."""

    @respx.mock
    def test_list_shows_reliability_metric(self, client: FlaskClient) -> None:
        """Service list cards show reliability score."""
        _mock_list_apis()
        response = client.get("/services/")
        assert response.status_code == 200
        html = response.data.decode()
        assert "Reliability" in html
        assert "reliability-score-inline" in html

    @respx.mock
    def test_list_shows_warning_for_low_score(self, client: FlaskClient) -> None:
        """Service list shows warning/critical indicator for below-threshold scores."""
        _mock_list_apis()
        response = client.get("/services/")
        assert response.status_code == 200
        html = response.data.decode()
        # api-gateway has compliance=0.5, no incidents → score 65, below threshold 70
        # Should show warning or critical class
        assert "reliability-warning" in html or "reliability-critical" in html

    @respx.mock
    def test_htmx_sort_request(self, client: FlaskClient) -> None:
        """HTMX sort request returns partial content."""
        _mock_list_apis()
        response = client.get(
            "/services/?sort=reliability",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        html = response.data.decode()
        assert "service-health-grid" in html or "empty-state" in html

    @respx.mock
    def test_filter_buttons_preserve_sort(self, client: FlaskClient) -> None:
        """Filter buttons include current sort parameter in HTMX URLs."""
        _mock_list_apis()
        response = client.get("/services/?sort=reliability")
        assert response.status_code == 200
        html = response.data.decode()
        # Filter buttons should preserve sort=reliability
        assert "sort=reliability" in html

    @respx.mock
    def test_sort_buttons_preserve_filter(self, client: FlaskClient) -> None:
        """Sort buttons include current filter parameter in HTMX URLs."""
        _mock_list_apis()
        response = client.get("/services/?status=warning&sort=status")
        assert response.status_code == 200
        html = response.data.decode()
        # Sort buttons should preserve status=warning filter
        assert "status=warning" in html

    @respx.mock
    def test_score_class_in_service_list(self, client: FlaskClient) -> None:
        """Service list renders score_class for color differentiation."""
        _mock_list_apis()
        response = client.get("/services/")
        assert response.status_code == 200
        html = response.data.decode()
        assert "reliability-score-inline" in html
