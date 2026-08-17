"""Tests for Beeper UI Flask application."""

import respx
from flask.testing import FlaskClient
from httpx import Response

from beeper_ui import __version__


def test_version() -> None:
    """Test version is set."""
    assert __version__ == "0.1.0"


def test_health_api_endpoint(client: FlaskClient) -> None:
    """Test health API endpoint returns healthy status."""
    response = client.get("/health/api")
    assert response.status_code == 200
    assert response.json == {"status": "healthy"}


def test_index_page(client: FlaskClient) -> None:
    """Test index page renders."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Beeper" in response.data


# NOTE (Task 6.3 / D13-D14): `test_sources_page_renders_with_sources` and
# `test_sources_page_renders_error_when_operator_unavailable` were removed
# here — `/sources/` no longer renders a Jinja page (see
# `test_routes.py::TestSourcesRoute` for the redirect coverage that replaces
# them; the data/error rendering they used to prove now lives in the React
# Sources view's own suite, `ui/frontend/src/test/SourcesPage.test.tsx`).


@respx.mock
def test_health_page_renders_with_health_data(client: FlaskClient) -> None:
    """Test health page renders with health data from operator."""
    health_response = {
        "components": {
            "operator": {"status": "healthy", "message": "Running"},
            "kubernetes": {"status": "healthy", "message": "Connected"},
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
    assert b"Operator Health" in response.data
    assert b"healthy" in response.data


@respx.mock
def test_health_page_renders_error_when_operator_unavailable(client: FlaskClient) -> None:
    """Test health page gracefully handles operator unavailability."""
    import httpx

    respx.get("http://mock-operator:8080/api/v1/health/components").mock(
        side_effect=httpx.ConnectError("Connection refused")
    )
    respx.get("http://mock-operator:8080/api/v1/ingestion/stats").mock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    response = client.get("/health/")
    assert response.status_code == 200
    assert b"Operator Health" in response.data
    assert b"Unable to fetch health status" in response.data
