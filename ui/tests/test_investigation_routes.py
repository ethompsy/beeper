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
    def test_investigations_error_hides_internals(self, client: FlaskClient) -> None:
        """Test error messages don't expose internal operator details."""
        import httpx

        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        response = client.get("/investigations/")
        assert response.status_code == 200
        # Should NOT expose internal operator URL
        assert b"mock-operator" not in response.data

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
    def test_investigations_filter_service(self, client: FlaskClient) -> None:
        """Test service filter is passed through to operator."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[MOCK_INVESTIGATIONS[0]])
        )

        response = client.get("/investigations/?service=payments")
        assert response.status_code == 200

        request = respx.calls.last.request
        assert "service=payments" in str(request.url)

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
    def test_investigations_filter_invalid_service(self, client: FlaskClient) -> None:
        """Test service filter validation rejects malformed service names."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[])
        )

        # Service with injection-style characters should be rejected
        response = client.get("/investigations/?service=../../etc/passwd")
        assert response.status_code == 200

        request = respx.calls.last.request
        assert "service=" not in str(request.url)

    @respx.mock
    def test_investigations_filter_date_range(self, client: FlaskClient) -> None:
        """Test date range filter works."""
        # Create an investigation with a very old timestamp
        old_investigation = {
            "id": "inv-old",
            "status": "completed",
            "service": "api",
            "severity": "low",
            "condition": "Old issue",
            "started_at": "2020-01-01T00:00:00Z",
            "completed_at": "2020-01-01T01:00:00Z",
            "triggered_at": "2020-01-01T00:00:00Z",
        }

        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[MOCK_INVESTIGATIONS[0], old_investigation])
        )

        # Filter to today only - old investigation should be excluded
        response = client.get("/investigations/?date_range=today")
        assert response.status_code == 200
        assert b"inv-old" not in response.data

    @respx.mock
    def test_investigations_filter_invalid_date_range(
        self, client: FlaskClient
    ) -> None:
        """Test invalid date range is ignored."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=MOCK_INVESTIGATIONS)
        )

        response = client.get("/investigations/?date_range=invalid")
        assert response.status_code == 200
        # All investigations should still appear (invalid range ignored)
        assert b"inv-abc123" in response.data
        assert b"inv-xyz789" in response.data

    @respx.mock
    def test_investigations_stream_content_type(self, client: FlaskClient) -> None:
        """Test SSE stream endpoint returns correct content type."""
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


class TestInvestigationFingerprint:
    """Tests for investigation fingerprint and SSE helpers."""

    def test_fingerprint_empty(self) -> None:
        """Test fingerprint of empty list."""
        from beeper_ui.routes.investigations import _investigation_fingerprint

        result = _investigation_fingerprint([])
        assert result == ""

    def test_fingerprint_single(self) -> None:
        """Test fingerprint of single investigation."""
        from beeper_ui.routes.investigations import _investigation_fingerprint
        from beeper_ui.services.investigation_service import Investigation

        inv = Investigation(
            id="inv-1",
            status="investigating",
            service="api",
            severity="high",
            condition="test",
        )
        result = _investigation_fingerprint([inv])
        assert result == "inv-1:investigating"

    def test_fingerprint_multiple(self) -> None:
        """Test fingerprint of multiple investigations."""
        from beeper_ui.routes.investigations import _investigation_fingerprint
        from beeper_ui.services.investigation_service import Investigation

        invs = [
            Investigation(
                id="inv-1", status="investigating", service="api",
                severity="high", condition="test1",
            ),
            Investigation(
                id="inv-2", status="completed", service="web",
                severity="low", condition="test2",
            ),
        ]
        result = _investigation_fingerprint(invs)
        assert result == "inv-1:investigating|inv-2:completed"

    def test_fingerprint_detects_status_change(self) -> None:
        """Test that fingerprint changes when status changes."""
        from beeper_ui.routes.investigations import _investigation_fingerprint
        from beeper_ui.services.investigation_service import Investigation

        inv_v1 = Investigation(
            id="inv-1", status="investigating", service="api",
            severity="high", condition="test",
        )
        inv_v2 = Investigation(
            id="inv-1", status="completed", service="api",
            severity="high", condition="test",
        )
        assert _investigation_fingerprint([inv_v1]) != _investigation_fingerprint([inv_v2])


class TestFilterValidation:
    """Tests for filter validation functions."""

    def test_validate_status_valid(self) -> None:
        """Test valid status values pass validation."""
        from beeper_ui.routes.investigations import validate_status

        assert validate_status("investigating") == "investigating"
        assert validate_status("completed") == "completed"
        assert validate_status("failed") == "failed"
        assert validate_status("awaiting_confirmation") == "awaiting_confirmation"

    def test_validate_status_invalid(self) -> None:
        """Test invalid status values are rejected."""
        from beeper_ui.routes.investigations import validate_status

        assert validate_status("hacked") is None
        assert validate_status("") is None
        assert validate_status(None) is None

    def test_validate_severity_valid(self) -> None:
        """Test valid severity values pass validation."""
        from beeper_ui.routes.investigations import validate_severity

        assert validate_severity("low") == "low"
        assert validate_severity("critical") == "critical"

    def test_validate_severity_invalid(self) -> None:
        """Test invalid severity values are rejected."""
        from beeper_ui.routes.investigations import validate_severity

        assert validate_severity("extreme") is None
        assert validate_severity(None) is None

    def test_validate_service_valid(self) -> None:
        """Test valid service names pass validation."""
        from beeper_ui.routes.investigations import validate_service

        assert validate_service("payments") == "payments"
        assert validate_service("api-gateway") == "api-gateway"
        assert validate_service("my_service.v2") == "my_service.v2"

    def test_validate_service_invalid(self) -> None:
        """Test invalid service names are rejected."""
        from beeper_ui.routes.investigations import validate_service

        assert validate_service("../../etc/passwd") is None
        assert validate_service("service with spaces") is None
        assert validate_service("a" * 200) is None
        assert validate_service("") is None
        assert validate_service(None) is None

    def test_validate_date_range_valid(self) -> None:
        """Test valid date ranges pass validation."""
        from beeper_ui.routes.investigations import validate_date_range

        assert validate_date_range("today") == "today"
        assert validate_date_range("7d") == "7d"
        assert validate_date_range("30d") == "30d"
        assert validate_date_range("90d") == "90d"

    def test_validate_date_range_invalid(self) -> None:
        """Test invalid date ranges are rejected."""
        from beeper_ui.routes.investigations import validate_date_range

        assert validate_date_range("1y") is None
        assert validate_date_range("invalid") is None
        assert validate_date_range("") is None
        assert validate_date_range(None) is None


class TestDateRangeFiltering:
    """Tests for date range filtering logic."""

    def test_parse_date_range_today(self) -> None:
        """Test parsing 'today' date range."""
        from beeper_ui.routes.investigations import parse_date_range

        result = parse_date_range("today")
        assert result is not None
        assert result.hour == 0
        assert result.minute == 0

    def test_parse_date_range_none(self) -> None:
        """Test None input returns None."""
        from beeper_ui.routes.investigations import parse_date_range

        assert parse_date_range(None) is None
        assert parse_date_range("") is None

    def test_filter_by_date_range(self) -> None:
        """Test filtering investigations by date cutoff."""
        from datetime import datetime, timezone

        from beeper_ui.routes.investigations import filter_by_date_range
        from beeper_ui.services.investigation_service import Investigation

        recent = Investigation(
            id="inv-new", status="investigating", service="api",
            severity="high", condition="test",
            started_at="2026-03-06T12:00:00Z",
        )
        old = Investigation(
            id="inv-old", status="completed", service="api",
            severity="low", condition="old test",
            started_at="2020-01-01T00:00:00Z",
        )
        cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = filter_by_date_range([recent, old], cutoff)

        assert len(result) == 1
        assert result[0].id == "inv-new"

    def test_filter_by_date_range_uses_triggered_at_fallback(self) -> None:
        """Test date filtering falls back to triggered_at when no started_at."""
        from datetime import datetime, timezone

        from beeper_ui.routes.investigations import filter_by_date_range
        from beeper_ui.services.investigation_service import Investigation

        inv = Investigation(
            id="inv-1", status="investigating", service="api",
            severity="high", condition="test",
            started_at=None,
            triggered_at="2026-03-06T12:00:00Z",
        )
        cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = filter_by_date_range([inv], cutoff)
        assert len(result) == 1

    def test_filter_by_date_range_excludes_no_timestamp(self) -> None:
        """Test investigations without any timestamp are excluded."""
        from datetime import datetime, timezone

        from beeper_ui.routes.investigations import filter_by_date_range
        from beeper_ui.services.investigation_service import Investigation

        inv = Investigation(
            id="inv-1", status="investigating", service="api",
            severity="high", condition="test",
        )
        cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = filter_by_date_range([inv], cutoff)
        assert len(result) == 0
