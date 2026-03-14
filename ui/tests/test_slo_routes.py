"""Integration tests for SLO dashboard routes."""

import httpx
import respx
from flask.testing import FlaskClient
from httpx import Response

MOCK_SERVICE_LEVELS = {
    "service_levels": [
        {
            "name": "payments-slo",
            "service": "payment-service",
            "sli_type": "availability",
            "target": 0.999,
            "window": "30d",
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
            "window": "7d",
            "condition": "warning",
            "compliance": 0.985,
            "burn_rate": 3.2,
            "error_budget_remaining": 0.25,
            "is_frozen": True,
        },
    ]
}

MOCK_SERVICE_DETAIL = {
    "name": "payments-slo",
    "service": "payment-service",
    "sli": {
        "type": "availability",
        "metric": "http_requests_total",
        "good_selector": '{code=~"2.."}',
        "total_selector": "{}",
    },
    "objective": {"target": 0.999, "window": "30d"},
    "burn_rate_alerts": [
        {
            "severity": "critical",
            "short_window": "5m",
            "long_window": "1h",
            "factor": 14.4,
        }
    ],
    "condition": "healthy",
    "compliance": 0.9995,
    "burn_rate": 0.5,
    "error_budget_remaining": 0.85,
    "is_frozen": False,
}

MOCK_BUDGET = {
    "name": "payments-slo",
    "service": "payment-service",
    "target": 0.999,
    "error_budget_total": 0.001,
    "error_budget_remaining": 0.85,
    "error_budget_consumed": 0.15,
    "burn_rate": 0.5,
    "projected_exhaustion_secs": 259200.0,
    "is_frozen": False,
    "triggered_policies": [
        {
            "threshold": 0.5,
            "action": "notify",
            "triggered_at": "2026-03-14T12:00:00Z",
            "consumption_at_trigger": 0.52,
        }
    ],
}


class TestSloDashboard:
    """Tests for /slo/ dashboard route."""

    @respx.mock
    def test_slo_dashboard_renders(self, client: FlaskClient) -> None:
        """Test dashboard renders with service data."""
        respx.get("http://mock-operator:8080/api/v1/slo/services").mock(
            return_value=Response(200, json=MOCK_SERVICE_LEVELS)
        )
        response = client.get("/slo/")
        assert response.status_code == 200
        assert b"SLO Compliance Dashboard" in response.data
        assert b"payments-slo" in response.data
        assert b"api-slo" in response.data

    @respx.mock
    def test_slo_dashboard_htmx_partial(self, client: FlaskClient) -> None:
        """Test HTMX request returns partial content."""
        respx.get("http://mock-operator:8080/api/v1/slo/services").mock(
            return_value=Response(200, json=MOCK_SERVICE_LEVELS)
        )
        response = client.get("/slo/", headers={"HX-Request": "true"})
        assert response.status_code == 200
        assert b"payments-slo" in response.data
        # Partial should not contain full page wrapper
        assert b"<!DOCTYPE html>" not in response.data

    @respx.mock
    def test_slo_dashboard_empty_services(self, client: FlaskClient) -> None:
        """Test empty state when no services configured."""
        respx.get("http://mock-operator:8080/api/v1/slo/services").mock(
            return_value=Response(200, json={"service_levels": []})
        )
        response = client.get("/slo/")
        assert response.status_code == 200
        assert b"No ServiceLevel CRDs configured" in response.data

    @respx.mock
    def test_slo_dashboard_api_error(self, client: FlaskClient) -> None:
        """Test error state when operator unavailable."""
        respx.get("http://mock-operator:8080/api/v1/slo/services").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        response = client.get("/slo/")
        assert response.status_code == 200
        assert b"Unable to connect to SLO data" in response.data

    @respx.mock
    def test_slo_dashboard_shows_service_data(
        self, client: FlaskClient
    ) -> None:
        """Test dashboard renders compliance, burn rate, budget data."""
        respx.get("http://mock-operator:8080/api/v1/slo/services").mock(
            return_value=Response(200, json=MOCK_SERVICE_LEVELS)
        )
        response = client.get("/slo/")
        assert response.status_code == 200
        # Compliance formatted
        assert b"99.95%" in response.data
        # Burn rate formatted
        assert b"0.5x" in response.data
        # Budget remaining formatted
        assert b"85.0%" in response.data
        # Status badges
        assert b"Healthy" in response.data
        assert b"Warning" in response.data
        # Frozen badge
        assert b"Frozen" in response.data


class TestSloServiceDetail:
    """Tests for /slo/services/<name> detail route."""

    @respx.mock
    def test_slo_service_detail_renders(self, client: FlaskClient) -> None:
        """Test service detail page renders."""
        respx.get(
            "http://mock-operator:8080/api/v1/slo/services/payments-slo"
        ).mock(return_value=Response(200, json=MOCK_SERVICE_DETAIL))
        respx.get(
            "http://mock-operator:8080/api/v1/slo/services/payments-slo/budget"
        ).mock(return_value=Response(200, json=MOCK_BUDGET))

        response = client.get("/slo/services/payments-slo")
        assert response.status_code == 200
        assert b"payments-slo" in response.data
        assert b"payment-service" in response.data
        assert b"99.95%" in response.data

    @respx.mock
    def test_slo_service_detail_not_found(
        self, client: FlaskClient
    ) -> None:
        """Test 404 for unknown service."""
        respx.get(
            "http://mock-operator:8080/api/v1/slo/services/nonexistent"
        ).mock(
            return_value=Response(
                404, json={"error": "not found"}
            )
        )

        response = client.get("/slo/services/nonexistent")
        assert response.status_code == 404

    @respx.mock
    def test_slo_service_detail_with_budget(
        self, client: FlaskClient
    ) -> None:
        """Test detail page shows budget data and triggered policies."""
        respx.get(
            "http://mock-operator:8080/api/v1/slo/services/payments-slo"
        ).mock(return_value=Response(200, json=MOCK_SERVICE_DETAIL))
        respx.get(
            "http://mock-operator:8080/api/v1/slo/services/payments-slo/budget"
        ).mock(return_value=Response(200, json=MOCK_BUDGET))

        response = client.get("/slo/services/payments-slo")
        assert response.status_code == 200
        # Budget data
        assert b"Error Budget" in response.data
        assert b"15.0%" in response.data  # consumed
        assert b"85.0%" in response.data  # remaining
        # Projected exhaustion
        assert b"3d 0h" in response.data
        # Triggered policies
        assert b"Triggered Policies" in response.data
        assert b"Notify" in response.data

    @respx.mock
    def test_slo_service_detail_with_config(
        self, client: FlaskClient
    ) -> None:
        """Test detail page shows SLO configuration."""
        respx.get(
            "http://mock-operator:8080/api/v1/slo/services/payments-slo"
        ).mock(return_value=Response(200, json=MOCK_SERVICE_DETAIL))
        respx.get(
            "http://mock-operator:8080/api/v1/slo/services/payments-slo/budget"
        ).mock(return_value=Response(200, json=MOCK_BUDGET))

        response = client.get("/slo/services/payments-slo")
        assert response.status_code == 200
        assert b"SLO Configuration" in response.data
        assert b"99.90%" in response.data  # target formatted
        assert b"30d" in response.data
        assert b"http_requests_total" in response.data
        # Burn rate alerts
        assert b"Burn Rate Alerts" in response.data
        assert b"14.4x" in response.data


class TestSloAccessControl:
    """Tests for SLO dashboard access control."""

    @respx.mock
    def test_slo_dashboard_accessible_by_user(
        self, user_client: object
    ) -> None:
        """Test user role can access SLO dashboard."""
        respx.get("http://mock-operator:8080/api/v1/slo/services").mock(
            return_value=Response(200, json={"service_levels": []})
        )
        response = user_client.get("/slo/")  # type: ignore[union-attr]
        assert response.status_code == 200

    @respx.mock
    def test_slo_dashboard_accessible_by_admin(
        self, admin_client: object
    ) -> None:
        """Test admin role can access SLO dashboard."""
        respx.get("http://mock-operator:8080/api/v1/slo/services").mock(
            return_value=Response(200, json={"service_levels": []})
        )
        response = admin_client.get("/slo/")  # type: ignore[union-attr]
        assert response.status_code == 200


class TestSloNavigation:
    """Tests for SLO navigation link."""

    def test_slo_navigation_link_present(self, client: FlaskClient) -> None:
        """Test SLO link appears in base navigation."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"/slo/" in response.data
        assert b"SLO" in response.data
