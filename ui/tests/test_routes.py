"""Integration tests for Beeper UI routes."""

import respx
from flask.testing import FlaskClient
from httpx import Response


class TestSourcesRoute:
    """Tests for the (Task 6.3 / D13-D14) retired sources route.

    `/sources/` no longer renders a Jinja page — it 302-redirects to
    `/app/sources` (the React Sources view) before the view function ever
    runs, regardless of operator/data state, HTMX header, or query string.
    The old data/error/empty/HTMX-partial rendering coverage this class used
    to carry is superseded by the React Sources view's own test suite
    (`ui/frontend/src/test/SourcesPage.test.tsx`) and the JSON API it reads
    from (`ui/tests/test_api_v1_sources_spending.py`); redirect-mechanism
    coverage (exclusions, query-string/permalink preservation) lives in
    `ui/tests/test_react_route_registry.py` and
    `ui/tests/test_jinja_retirement.py`. This class keeps a minimal,
    file-local proof that this specific route redirects rather than
    silently dropping all `/sources/` coverage from this file.
    """

    def test_sources_page_redirects_to_react_app(self, client: FlaskClient) -> None:
        response = client.get("/sources/")
        assert response.status_code == 302
        assert response.headers["Location"] == "/app/sources"

    def test_sources_htmx_request_also_redirects(self, client: FlaskClient) -> None:
        # The old HTMX-partial branch (same URL) is gone along with the rest
        # of the Jinja render path — an HX-Request header changes nothing now.
        response = client.get("/sources/", headers={"HX-Request": "true"})
        assert response.status_code == 302
        assert response.headers["Location"] == "/app/sources"


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
