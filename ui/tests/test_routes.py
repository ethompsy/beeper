"""Integration tests for Beeper UI routes."""

import respx
from flask.testing import FlaskClient
from httpx import Response


class TestSourcesRoute:
    """Tests for sources route."""

    @respx.mock
    def test_sources_page_with_data(self, client: FlaskClient) -> None:
        """Test sources page renders with source data."""
        mock_response = {
            "sources": [
                {
                    "name": "prometheus-main",
                    "type": "prometheus",
                    "endpoint": "http://prometheus:9090",
                    "status": "connected",
                    "last_check": "2026-02-10T12:00:00Z",
                    "error": None,
                },
            ]
        }

        respx.get("http://mock-operator:8080/api/v1/sources").mock(
            return_value=Response(200, json=mock_response)
        )

        response = client.get("/sources/")
        assert response.status_code == 200
        assert b"prometheus-main" in response.data
        assert b"connected" in response.data

    @respx.mock
    def test_sources_page_with_error(self, client: FlaskClient) -> None:
        """Test sources page shows error for source with error."""
        mock_response = {
            "sources": [
                {
                    "name": "loki-prod",
                    "type": "loki",
                    "endpoint": "http://loki:3100",
                    "status": "error",
                    "last_check": "2026-02-10T12:00:00Z",
                    "error": {
                        "type": "connection_error",
                        "message": "Connection refused: check endpoint URL",
                        "details": "dial tcp: connection refused",
                    },
                }
            ]
        }

        respx.get("http://mock-operator:8080/api/v1/sources").mock(
            return_value=Response(200, json=mock_response)
        )

        response = client.get("/sources/")
        assert response.status_code == 200
        assert b"loki-prod" in response.data
        assert b"error" in response.data
        assert b"Connection refused" in response.data

    @respx.mock
    def test_sources_page_operator_unavailable(self, client: FlaskClient) -> None:
        """Test sources page shows error when operator is unavailable."""
        import httpx

        respx.get("http://mock-operator:8080/api/v1/sources").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        response = client.get("/sources/")
        assert response.status_code == 200
        assert b"Unable to fetch sources" in response.data

    @respx.mock
    def test_sources_page_empty(self, client: FlaskClient) -> None:
        """Test sources page with no configured sources."""
        respx.get("http://mock-operator:8080/api/v1/sources").mock(
            return_value=Response(200, json={"sources": []})
        )

        response = client.get("/sources/")
        assert response.status_code == 200
        assert b"No data sources configured" in response.data

    @respx.mock
    def test_sources_htmx_partial(self, client: FlaskClient) -> None:
        """Test HTMX request returns partial content."""
        mock_response = {
            "sources": [
                {
                    "name": "prometheus-main",
                    "type": "prometheus",
                    "endpoint": "http://prometheus:9090",
                    "status": "connected",
                    "last_check": None,
                    "error": None,
                }
            ]
        }

        respx.get("http://mock-operator:8080/api/v1/sources").mock(
            return_value=Response(200, json=mock_response)
        )

        response = client.get("/sources/", headers={"HX-Request": "true"})
        assert response.status_code == 200
        # Partial should not include full HTML structure
        assert b"<!DOCTYPE html>" not in response.data
        assert b"prometheus-main" in response.data


class TestHealthRoute:
    """Tests for health route."""

    @respx.mock
    def test_health_page_all_healthy(self, client: FlaskClient) -> None:
        """Test health page with all healthy components."""
        health_response = {
            "components": {
                "operator": {"status": "healthy", "message": "Running"},
                "kubernetes": {"status": "healthy", "message": "Connected"},
                "ingestion": {"status": "healthy", "message": "Buffer: 50/10000"},
            },
            "overall": "healthy",
        }

        stats_response = {
            "buffer_size": 10000,
            "buffered_count": 50,
            "dropped_count": 0,
            "is_full": False,
        }

        respx.get("http://mock-operator:8080/api/v1/health/components").mock(
            return_value=Response(200, json=health_response)
        )
        respx.get("http://mock-operator:8080/api/v1/ingestion/stats").mock(
            return_value=Response(200, json=stats_response)
        )

        response = client.get("/health/")
        assert response.status_code == 200
        assert b"Operator" in response.data or b"operator" in response.data
        assert b"healthy" in response.data

    @respx.mock
    def test_health_page_unhealthy_component(self, client: FlaskClient) -> None:
        """Test health page with unhealthy component."""
        health_response = {
            "components": {
                "operator": {"status": "healthy", "message": "Running"},
                "kubernetes": {"status": "unhealthy", "message": "Cannot connect"},
            },
            "overall": "unhealthy",
        }

        respx.get("http://mock-operator:8080/api/v1/health/components").mock(
            return_value=Response(200, json=health_response)
        )
        stats_json = {
            "buffer_size": 0, "buffered_count": 0, "dropped_count": 0, "is_full": False
        }
        respx.get("http://mock-operator:8080/api/v1/ingestion/stats").mock(
            return_value=Response(200, json=stats_json)
        )

        response = client.get("/health/")
        assert response.status_code == 200
        assert b"unhealthy" in response.data

    @respx.mock
    def test_health_page_operator_unavailable(self, client: FlaskClient) -> None:
        """Test health page when operator is unavailable."""
        import httpx

        respx.get("http://mock-operator:8080/api/v1/health/components").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        # Also mock ingestion stats since it may be called
        respx.get("http://mock-operator:8080/api/v1/ingestion/stats").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        response = client.get("/health/")
        assert response.status_code == 200
        assert b"Unable to fetch health status" in response.data

    @respx.mock
    def test_health_api_endpoint(self, client: FlaskClient) -> None:
        """Test UI's own health API endpoint."""
        response = client.get("/health/api")
        assert response.status_code == 200
        assert response.json == {"status": "healthy"}

    @respx.mock
    def test_health_htmx_partial(self, client: FlaskClient) -> None:
        """Test HTMX request returns partial content."""
        health_response = {
            "components": {
                "operator": {"status": "healthy", "message": "Running"},
            },
            "overall": "healthy",
        }

        respx.get("http://mock-operator:8080/api/v1/health/components").mock(
            return_value=Response(200, json=health_response)
        )
        stats_json = {
            "buffer_size": 0, "buffered_count": 0, "dropped_count": 0, "is_full": False
        }
        respx.get("http://mock-operator:8080/api/v1/ingestion/stats").mock(
            return_value=Response(200, json=stats_json)
        )

        response = client.get("/health/", headers={"HX-Request": "true"})
        assert response.status_code == 200
        # Partial should not include full HTML structure
        assert b"<!DOCTYPE html>" not in response.data
