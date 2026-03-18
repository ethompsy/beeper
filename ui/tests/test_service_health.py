"""Tests for per-service health feeds (Story 7-4)."""

import httpx
import respx
from flask import Flask
from flask.testing import FlaskClient
from httpx import Response

from beeper_ui.services.service_health_service import (
    ServiceHealthService,
    compute_health_status,
)
from tests.conftest import _RoleClient

# --- Mock Data ---

MOCK_SERVICE_LEVELS = {
    "service_levels": [
        {
            "name": "payments-slo",
            "service": "payment-service",
            "sli_type": "availability",
            "target": 0.999,
            "condition": "healthy",
            "compliance": 0.9995,
            "burn_rate": 0.5,
            "error_budget_remaining": 0.85,
            "is_frozen": False,
        },
        {
            "name": "api-slo",
            "service": "api-gateway",
            "sli_type": "latency",
            "target": 0.99,
            "condition": "warning",
            "compliance": 0.985,
            "burn_rate": 3.2,
            "error_budget_remaining": 0.25,
            "is_frozen": True,
        },
        {
            "name": "auth-slo",
            "service": "auth-service",
            "sli_type": "availability",
            "target": 0.9999,
            "condition": "critical",
            "compliance": 0.990,
            "burn_rate": 8.1,
            "error_budget_remaining": 0.05,
            "is_frozen": False,
        },
    ]
}

MOCK_INVESTIGATIONS = [
    {
        "id": "inv-001",
        "status": "investigating",
        "service": "payment-service",
        "severity": "high",
        "condition": "latency_spike",
        "started_at": "2026-03-18T10:00:00Z",
        "completed_at": None,
        "workflow_state": "investigating",
    },
    {
        "id": "inv-002",
        "status": "completed",
        "service": "payment-service",
        "severity": "medium",
        "condition": "error_rate",
        "started_at": "2026-03-15T08:00:00Z",
        "completed_at": "2026-03-15T09:00:00Z",
        "workflow_state": "resolved",
    },
    {
        "id": "inv-003",
        "status": "investigating",
        "service": "api-gateway",
        "severity": "critical",
        "condition": "slo_breach",
        "started_at": "2026-03-18T11:00:00Z",
        "completed_at": None,
        "workflow_state": "investigating",
    },
    {
        "id": "inv-004",
        "status": "completed",
        "service": "auth-service",
        "severity": "low",
        "condition": "anomaly",
        "started_at": "2026-03-01T08:00:00Z",
        "completed_at": "2026-03-01T09:00:00Z",
        "workflow_state": "verified",
    },
]

MOCK_TRUST_LEVELS = [
    {"service_name": "payment-service", "trust_level": 3},
    {"service_name": "api-gateway", "trust_level": 2},
    {"service_name": "auth-service", "trust_level": 1},
]

MOCK_SERVICE_DETAIL = {
    "name": "payments-slo",
    "service": "payment-service",
    "sli": {
        "type": "availability",
        "metric": "http_requests_total",
    },
    "condition": "healthy",
    "compliance": 0.9995,
    "burn_rate": 0.5,
    "error_budget_remaining": 0.85,
    "is_frozen": False,
}

MOCK_BUDGET = {
    "name": "payments-slo",
    "error_budget_remaining": 0.85,
    "is_frozen": False,
}

MOCK_TRUST_DETAIL = {
    "service_name": "payment-service",
    "trust_level": 3,
}


def _mock_all_apis() -> None:
    """Set up respx mocks for all service health APIs."""
    respx.get("http://mock-operator:8080/api/v1/slo/services").mock(
        return_value=Response(200, json=MOCK_SERVICE_LEVELS)
    )
    respx.get("http://mock-operator:8080/api/v1/investigations").mock(
        return_value=Response(200, json=MOCK_INVESTIGATIONS)
    )
    respx.get("http://mock-operator:8080/api/v1/trust/services").mock(
        return_value=Response(200, json=MOCK_TRUST_LEVELS)
    )


def _mock_detail_apis(service_name: str = "payment-service") -> None:
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
        params={"service": service_name},
    ).mock(return_value=Response(200, json=MOCK_INVESTIGATIONS[:2]))
    respx.get(
        f"http://mock-operator:8080/api/v1/trust/services/{service_name}"
    ).mock(return_value=Response(200, json=MOCK_TRUST_DETAIL))


# =============================================================================
# Unit Tests: compute_health_status
# =============================================================================


class TestComputeHealthStatus:
    """Tests for compute_health_status helper."""

    def test_critical_condition(self) -> None:
        assert compute_health_status("critical", 0) == "critical"

    def test_warning_condition(self) -> None:
        assert compute_health_status("warning", 0) == "warning"

    def test_healthy_condition_no_active(self) -> None:
        assert compute_health_status("healthy", 0) == "healthy"

    def test_healthy_with_one_active_becomes_warning(self) -> None:
        assert compute_health_status("healthy", 1) == "warning"

    def test_healthy_with_three_active_becomes_critical(self) -> None:
        assert compute_health_status("healthy", 3) == "critical"

    def test_unknown_condition_no_active(self) -> None:
        assert compute_health_status("unknown", 0) == "healthy"

    def test_unknown_with_active(self) -> None:
        assert compute_health_status("unknown", 2) == "warning"


# =============================================================================
# Unit Tests: ServiceHealthService
# =============================================================================


class TestServiceHealthServiceList:
    """Tests for ServiceHealthService.get_service_list()."""

    @respx.mock
    def test_get_service_list_aggregates_data(self, app: Flask) -> None:
        """Test service list aggregates SLO, investigations, and trust data."""
        with app.app_context():
            _mock_all_apis()
            svc = ServiceHealthService(
                operator_url="http://mock-operator:8080"
            )
            try:
                result = svc.get_service_list()
                assert len(result) == 3
                # Sorted by health: critical first
                assert result[0]["name"] == "auth-service"
                assert result[0]["health_status"] == "critical"
                # payment-service has 1 active investigation → warning
                payment = next(s for s in result if s["name"] == "payment-service")
                assert payment["health_status"] == "warning"
                assert payment["active_investigation_count"] == 1
                assert payment["trust_level"] == 3
                assert payment["compliance"] == 0.9995
            finally:
                svc.close()

    @respx.mock
    def test_get_service_list_with_status_filter(self, app: Flask) -> None:
        """Test filtering by health status."""
        with app.app_context():
            _mock_all_apis()
            svc = ServiceHealthService(
                operator_url="http://mock-operator:8080"
            )
            try:
                result = svc.get_service_list(status_filter="critical")
                assert len(result) == 1
                assert result[0]["name"] == "auth-service"
            finally:
                svc.close()

    @respx.mock
    def test_get_service_list_handles_slo_error(self, app: Flask) -> None:
        """Test graceful handling when SLO service fails."""
        with app.app_context():
            respx.get("http://mock-operator:8080/api/v1/slo/services").mock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            respx.get("http://mock-operator:8080/api/v1/investigations").mock(
                return_value=Response(200, json=[])
            )
            respx.get("http://mock-operator:8080/api/v1/trust/services").mock(
                return_value=Response(200, json=[])
            )
            svc = ServiceHealthService(
                operator_url="http://mock-operator:8080"
            )
            try:
                result = svc.get_service_list()
                assert result == []
            finally:
                svc.close()


class TestServiceHealthServiceDetail:
    """Tests for ServiceHealthService.get_service_detail()."""

    @respx.mock
    def test_get_service_detail_returns_unified_data(self, app: Flask) -> None:
        """Test detail returns SLO, investigations, trust, and budget data."""
        with app.app_context():
            _mock_detail_apis()
            svc = ServiceHealthService(
                operator_url="http://mock-operator:8080"
            )
            try:
                result = svc.get_service_detail("payment-service")
                assert result is not None
                assert result["name"] == "payment-service"
                assert result["compliance"] == 0.9995
                assert result["trust_level"] == 3
                assert result["error_budget_remaining"] == 0.85
                assert len(result["active_investigations"]) == 1
                assert result["active_investigations"][0]["id"] == "inv-001"
                assert result["active_investigation_count"] == 1
            finally:
                svc.close()

    @respx.mock
    def test_get_service_detail_not_found(self, app: Flask) -> None:
        """Test returns None for unknown service."""
        with app.app_context():
            respx.get("http://mock-operator:8080/api/v1/slo/services").mock(
                return_value=Response(200, json={"service_levels": []})
            )
            svc = ServiceHealthService(
                operator_url="http://mock-operator:8080"
            )
            try:
                result = svc.get_service_detail("nonexistent")
                assert result is None
            finally:
                svc.close()

    @respx.mock
    def test_get_service_detail_partitions_investigations(
        self, app: Flask
    ) -> None:
        """Test investigations are partitioned into active and recent resolved."""
        with app.app_context():
            _mock_detail_apis()
            svc = ServiceHealthService(
                operator_url="http://mock-operator:8080"
            )
            try:
                result = svc.get_service_detail("payment-service")
                assert result is not None
                # inv-001 is investigating (active)
                active_ids = [i["id"] for i in result["active_investigations"]]
                assert "inv-001" in active_ids
                # inv-002 completed 3 days ago (within 7 days) → recent resolved
                resolved_ids = [i["id"] for i in result["recent_resolved"]]
                assert "inv-002" in resolved_ids
            finally:
                svc.close()


# =============================================================================
# Integration Tests: Service List Route
# =============================================================================


class TestServiceListRoute:
    """Tests for GET /services/ route."""

    @respx.mock
    def test_service_list_renders(self, client: FlaskClient) -> None:
        """Test service list page renders with service data."""
        _mock_all_apis()
        response = client.get("/services/")
        assert response.status_code == 200
        assert b"Services" in response.data
        assert b"payment-service" in response.data
        assert b"api-gateway" in response.data
        assert b"auth-service" in response.data

    @respx.mock
    def test_service_list_htmx_partial(self, client: FlaskClient) -> None:
        """Test HTMX request returns partial content."""
        _mock_all_apis()
        response = client.get("/services/", headers={"HX-Request": "true"})
        assert response.status_code == 200
        assert b"payment-service" in response.data
        assert b"<!DOCTYPE html>" not in response.data

    @respx.mock
    def test_service_list_shows_health_badges(self, client: FlaskClient) -> None:
        """Test service cards show health status badges."""
        _mock_all_apis()
        response = client.get("/services/")
        assert response.status_code == 200
        assert b"health-healthy" in response.data or b"health-warning" in response.data
        assert b"health-critical" in response.data

    @respx.mock
    def test_service_list_highlights_active_investigations(
        self, client: FlaskClient
    ) -> None:
        """Test services with active investigations are highlighted."""
        _mock_all_apis()
        response = client.get("/services/")
        assert response.status_code == 200
        assert b"service-card-highlighted" in response.data

    @respx.mock
    def test_service_list_status_filter(self, client: FlaskClient) -> None:
        """Test filtering by health status."""
        _mock_all_apis()
        response = client.get("/services/?status=critical")
        assert response.status_code == 200
        assert b"auth-service" in response.data

    @respx.mock
    def test_service_list_htmx_filter_targets_wrapper(
        self, client: FlaskClient
    ) -> None:
        """Test HTMX filter buttons target services-wrapper to avoid nesting."""
        _mock_all_apis()
        response = client.get("/services/")
        assert response.status_code == 200
        assert b'hx-target="#services-wrapper"' in response.data
        # Ensure old target is not present
        assert b'hx-target="#service-list-container"' not in response.data

    @respx.mock
    def test_service_list_empty_state(self, client: FlaskClient) -> None:
        """Test empty state when no services exist."""
        respx.get("http://mock-operator:8080/api/v1/slo/services").mock(
            return_value=Response(200, json={"service_levels": []})
        )
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[])
        )
        respx.get("http://mock-operator:8080/api/v1/trust/services").mock(
            return_value=Response(200, json=[])
        )
        response = client.get("/services/")
        assert response.status_code == 200
        assert b"No services found" in response.data

    @respx.mock
    def test_service_list_api_error(self, client: FlaskClient) -> None:
        """Test graceful degradation when operator unavailable — returns empty list."""
        respx.get("http://mock-operator:8080/api/v1/slo/services").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        respx.get("http://mock-operator:8080/api/v1/trust/services").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        response = client.get("/services/")
        assert response.status_code == 200
        # Service returns empty list gracefully when SLO service fails
        assert b"No services found" in response.data


# =============================================================================
# Integration Tests: Service Detail Route
# =============================================================================


class TestServiceDetailRoute:
    """Tests for GET /services/<name> route."""

    @respx.mock
    def test_service_detail_renders(self, client: FlaskClient) -> None:
        """Test service detail page renders with health data."""
        _mock_detail_apis()
        response = client.get("/services/payment-service")
        assert response.status_code == 200
        assert b"payment-service" in response.data
        assert b"SLO Compliance" in response.data
        assert b"Burn Rate" in response.data
        assert b"Error Budget Remaining" in response.data
        assert b"Active Investigations" in response.data

    @respx.mock
    def test_service_detail_shows_aria_feed(self, client: FlaskClient) -> None:
        """Test detail page has ARIA feed role."""
        _mock_detail_apis()
        response = client.get("/services/payment-service")
        assert response.status_code == 200
        assert b'role="feed"' in response.data
        assert b'aria-label="Service health feed for payment-service"' in response.data

    @respx.mock
    def test_service_detail_not_found(self, client: FlaskClient) -> None:
        """Test 404 for unknown service."""
        respx.get("http://mock-operator:8080/api/v1/slo/services").mock(
            return_value=Response(200, json={"service_levels": []})
        )
        response = client.get("/services/nonexistent")
        assert response.status_code == 404

    def test_service_detail_invalid_name(self, client: FlaskClient) -> None:
        """Test 404 for invalid service name."""
        response = client.get("/services/invalid%20name!")
        assert response.status_code == 404

    def test_service_detail_name_too_long(self, client: FlaskClient) -> None:
        """Test 404 for service name exceeding 100 characters."""
        long_name = "a" * 101
        response = client.get(f"/services/{long_name}")
        assert response.status_code == 404


# =============================================================================
# Integration Tests: Feed Items Partial
# =============================================================================


class TestServiceFeedItemsRoute:
    """Tests for GET /services/<name>/feed-items route."""

    @respx.mock
    def test_feed_items_renders(self, client: FlaskClient) -> None:
        """Test feed items partial renders investigation articles."""
        _mock_detail_apis()
        response = client.get("/services/payment-service/feed-items")
        assert response.status_code == 200
        assert b'role="article"' in response.data
        assert b"inv-001" in response.data
        assert b"Active Investigations" in response.data
        assert b"Recently Resolved" in response.data

    @respx.mock
    def test_feed_items_partitions_correctly(self, client: FlaskClient) -> None:
        """Test feed items correctly partition active vs resolved."""
        _mock_detail_apis()
        response = client.get("/services/payment-service/feed-items")
        assert response.status_code == 200
        # inv-001 is active
        assert b"feed-item-active" in response.data
        # inv-002 is resolved within 7 days
        assert b"feed-item-resolved" in response.data

    def test_feed_items_invalid_name(self, client: FlaskClient) -> None:
        """Test 404 for invalid service name."""
        response = client.get("/services/invalid%20name!/feed-items")
        assert response.status_code == 404


# =============================================================================
# Integration Tests: SSE Stream
# =============================================================================


class TestServiceSSEStream:
    """Tests for GET /services/<name>/stream SSE endpoint."""

    @respx.mock
    def test_sse_stream_content_type(self, client: FlaskClient) -> None:
        """Test SSE stream returns correct content type."""
        from beeper_ui.routes.services import service_health_stream

        _mock_detail_apis()
        app = client.application
        with app.test_request_context("/services/payment-service/stream"):
            response = service_health_stream("payment-service")
            assert "text/event-stream" in response.content_type
            assert response.headers.get("Cache-Control") == "no-cache"
            assert response.headers.get("Connection") == "keep-alive"
            response.close()

    def test_sse_stream_invalid_name(self, client: FlaskClient) -> None:
        """Test 404 for invalid service name."""
        response = client.get("/services/invalid%20name!/stream")
        assert response.status_code == 404


# =============================================================================
# Navigation Tests
# =============================================================================


class TestServiceNavigation:
    """Tests for service health navigation."""

    def test_services_nav_link_present(self, client: FlaskClient) -> None:
        """Test Services link appears in navigation."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"/services/" in response.data
        assert b"Services" in response.data

    def test_services_command_palette_entry(self, client: FlaskClient) -> None:
        """Test Services Health entry in command palette JS."""
        response = client.get("/")
        assert response.status_code == 200
        # The command palette JS should be loaded
        assert b"command-palette" in response.data


# =============================================================================
# Access Control Tests
# =============================================================================


class TestServiceAccessControl:
    """Tests for service health access control."""

    @respx.mock
    def test_services_accessible_by_user(
        self, user_client: _RoleClient
    ) -> None:
        """Test user role can access services page."""
        _mock_all_apis()
        response = user_client.get("/services/")
        assert response.status_code == 200

    @respx.mock
    def test_services_accessible_by_admin(
        self, admin_client: _RoleClient
    ) -> None:
        """Test admin role can access services page."""
        _mock_all_apis()
        response = admin_client.get("/services/")
        assert response.status_code == 200
