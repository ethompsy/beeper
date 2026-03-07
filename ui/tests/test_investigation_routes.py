"""Tests for Investigation routes."""

import respx
from flask.testing import FlaskClient
from httpx import Response

MOCK_INVESTIGATIONS = [
    {
        "id": "inv-abc123",
        "status": "investigating",
        "service": "payments",
        "severity": "high",
        "condition": "High error rate detected",
        "started_at": "2026-02-09T12:00:00Z",
        "completed_at": None,
        "triggered_at": "2026-02-09T11:55:00Z",
    },
    {
        "id": "inv-xyz789",
        "status": "completed",
        "service": "api-gateway",
        "severity": "medium",
        "condition": "Latency spike resolved",
        "started_at": "2026-02-09T10:00:00Z",
        "completed_at": "2026-02-09T10:15:00Z",
        "triggered_at": "2026-02-09T09:55:00Z",
    },
]


class TestInvestigationsRoute:
    """Tests for investigations route."""

    @respx.mock
    def test_investigations_page_with_data(self, client: FlaskClient) -> None:
        """Test investigations page renders with investigation data."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=MOCK_INVESTIGATIONS)
        )

        response = client.get("/investigations/")
        assert response.status_code == 200
        assert b"inv-abc123" in response.data
        assert b"payments" in response.data
        assert b"In Progress" in response.data

    @respx.mock
    def test_investigations_page_full_html(self, client: FlaskClient) -> None:
        """Test full page includes HTML structure (no HX-Request header)."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=MOCK_INVESTIGATIONS)
        )

        response = client.get("/investigations/")
        assert response.status_code == 200
        assert b"<!DOCTYPE html>" in response.data
        assert b"Investigations" in response.data

    @respx.mock
    def test_investigations_htmx_partial(self, client: FlaskClient) -> None:
        """Test HTMX request returns partial content."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=MOCK_INVESTIGATIONS)
        )

        response = client.get("/investigations/", headers={"HX-Request": "true"})
        assert response.status_code == 200
        # Partial should not include full HTML structure
        assert b"<!DOCTYPE html>" not in response.data
        assert b"inv-abc123" in response.data

    @respx.mock
    def test_investigations_empty(self, client: FlaskClient) -> None:
        """Test empty state rendering when no investigations."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[])
        )

        response = client.get("/investigations/")
        assert response.status_code == 200
        assert b"No active investigations" in response.data

    @respx.mock
    def test_investigations_operator_unavailable(self, client: FlaskClient) -> None:
        """Test error state rendering when operator unavailable."""
        import httpx

        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        response = client.get("/investigations/")
        assert response.status_code == 200
        assert b"Unable to fetch investigations" in response.data

    @respx.mock
    def test_investigations_filter_status(self, client: FlaskClient) -> None:
        """Test filter params are passed through to service layer."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[MOCK_INVESTIGATIONS[0]])
        )

        response = client.get("/investigations/?status=investigating")
        assert response.status_code == 200

        # Verify the request was made with query params
        request = respx.calls.last.request
        assert "status=investigating" in str(request.url)

    @respx.mock
    def test_investigations_filter_severity(self, client: FlaskClient) -> None:
        """Test severity filter."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[])
        )

        response = client.get("/investigations/?severity=high")
        assert response.status_code == 200

        request = respx.calls.last.request
        assert "severity=high" in str(request.url)

    @respx.mock
    def test_investigations_filter_invalid_status(self, client: FlaskClient) -> None:
        """Test filter validation rejects invalid status values."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[])
        )

        response = client.get("/investigations/?status=invalid_status")
        assert response.status_code == 200

        # Invalid status should not be passed as query param
        request = respx.calls.last.request
        assert "status=invalid_status" not in str(request.url)

    @respx.mock
    def test_investigations_filter_invalid_severity(self, client: FlaskClient) -> None:
        """Test filter validation rejects invalid severity values."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[])
        )

        response = client.get("/investigations/?severity=extreme")
        assert response.status_code == 200

        request = respx.calls.last.request
        assert "severity=extreme" not in str(request.url)

    @respx.mock
    def test_investigations_stream_content_type(self, client: FlaskClient) -> None:
        """Test SSE stream endpoint returns correct content type.

        Note: We test the route exists and returns the right content type.
        The Flask test client buffers streaming responses, so we verify
        the response is created correctly without consuming the stream.
        """

        from beeper_ui.routes.investigations import investigation_stream

        # Test the route is registered and the handler returns Response
        app = client.application
        with app.test_request_context("/investigations/stream"):
            response = investigation_stream()
            assert "text/event-stream" in response.content_type
            assert response.headers.get("Cache-Control") == "no-cache"
            assert response.headers.get("Connection") == "keep-alive"
            # Close the response to stop the generator
            response.close()

    @respx.mock
    def test_investigations_nav_link(self, client: FlaskClient) -> None:
        """Test that Investigations link appears in navigation."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[])
        )

        response = client.get("/investigations/")
        assert b'href="/investigations/"' in response.data
