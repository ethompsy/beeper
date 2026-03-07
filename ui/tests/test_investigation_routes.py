"""Tests for Investigation routes."""

from unittest.mock import patch

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


MOCK_INVESTIGATION_DETAIL = {
    "id": "inv-detail-001",
    "status": "investigating",
    "service": "payments",
    "severity": "high",
    "condition": "High error rate detected",
    "started_at": "2026-03-06T10:00:00Z",
    "completed_at": None,
    "triggered_at": "2026-03-06T09:55:00Z",
    "message": "Correlating signals across architectural layers",
    "error": None,
    "job_name": "inv-detail-001-job",
}


class TestInvestigationDetailRoute:
    """Tests for investigation detail route."""

    @respx.mock
    def test_detail_full_page(self, client: FlaskClient) -> None:
        """Test investigation detail returns full page HTML."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        with patch(
            "beeper_ui.services.investigation_service.InvestigationService.get_investigation_findings",
            return_value={},
        ):
            response = client.get("/investigations/inv-detail-001")
            assert response.status_code == 200
            assert b"<!DOCTYPE html>" in response.data
            assert b"inv-detail-001" in response.data
            assert b"High error rate detected" in response.data

    @respx.mock
    def test_detail_htmx_partial(self, client: FlaskClient) -> None:
        """Test detail with HX-Request returns partial."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={},
        ):
            response = client.get(
                "/investigations/inv-detail-001",
                headers={"HX-Request": "true"},
            )
            assert response.status_code == 200
            assert b"<!DOCTYPE html>" not in response.data
            assert b"inv-detail-001" in response.data

    @respx.mock
    def test_detail_not_found(self, client: FlaskClient) -> None:
        """Test detail returns 404 for nonexistent investigation."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-nonexistent"
        ).mock(return_value=Response(404, json={"error": "not found"}))

        response = client.get("/investigations/inv-nonexistent")
        assert response.status_code == 404
        assert b"Investigation not found" in response.data

    @respx.mock
    def test_detail_not_found_htmx(self, client: FlaskClient) -> None:
        """Test detail returns 404 partial for HTMX request."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-nonexistent"
        ).mock(return_value=Response(404, json={"error": "not found"}))

        response = client.get(
            "/investigations/inv-nonexistent",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 404
        assert b"<!DOCTYPE html>" not in response.data
        assert b"Investigation not found" in response.data

    @respx.mock
    def test_detail_operator_unavailable(self, client: FlaskClient) -> None:
        """Test detail handles operator connection error."""
        import httpx

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-001"
        ).mock(side_effect=httpx.ConnectError("Connection refused"))

        response = client.get("/investigations/inv-001")
        assert response.status_code == 200
        assert b"Unable to connect" in response.data

    def test_detail_invalid_id_rejected(self, client: FlaskClient) -> None:
        """Test that invalid investigation IDs are rejected."""
        response = client.get("/investigations/../../etc/passwd")
        assert response.status_code == 404

    @respx.mock
    def test_detail_shows_step_progress(self, client: FlaskClient) -> None:
        """Test detail page includes step progress timeline."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={},
        ):
            response = client.get("/investigations/inv-detail-001")
            assert response.status_code == 200
            assert b"Investigation Progress" in response.data
            assert b"step-timeline" in response.data

    @respx.mock
    def test_detail_shows_findings(self, client: FlaskClient) -> None:
        """Test detail page renders findings when available."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        mock_findings = {
            "customer_impacting": True,
            "reasoning": "Users experiencing payment failures",
            "root_cause_hypothesis": "Database pool exhausted",
            "confidence_percentage": 85,
            "confidence_level": "high",
        }

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value=mock_findings,
        ):
            response = client.get("/investigations/inv-detail-001")
            assert response.status_code == 200
            assert b"Customer Impact" in response.data
            assert b"Customer Impacting" in response.data
            assert b"Root Cause Hypothesis" in response.data

    @respx.mock
    def test_detail_shows_evidence_panels(self, client: FlaskClient) -> None:
        """Test detail page renders expandable evidence sections."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        mock_findings = {
            "signals_gathered": 12,
            "supporting_evidence": "Log correlation shows timeout pattern",
        }

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value=mock_findings,
        ):
            response = client.get("/investigations/inv-detail-001")
            assert response.status_code == 200
            assert b"evidence-panel" in response.data
            assert b"Raw Signals" in response.data

    @respx.mock
    def test_detail_stream_content_type(self, client: FlaskClient) -> None:
        """Test detail SSE endpoint returns correct content type."""
        from beeper_ui.routes.investigations import investigation_detail_stream

        app = client.application
        with app.test_request_context("/investigations/inv-001/stream"):
            response = investigation_detail_stream("inv-001")
            assert "text/event-stream" in response.content_type
            assert response.headers.get("Cache-Control") == "no-cache"
            assert response.headers.get("Connection") == "keep-alive"
            response.close()

    def test_detail_stream_invalid_id(self, client: FlaskClient) -> None:
        """Test detail SSE endpoint rejects invalid IDs."""
        response = client.get("/investigations/../../etc/passwd/stream")
        assert response.status_code == 404


class TestStepStates:
    """Tests for step progress state calculation."""

    def test_step_states_all_completed(self) -> None:
        """Test all steps completed when phase is completed."""
        from beeper_ui.routes.investigations import _get_step_states

        states = _get_step_states(None, "completed")
        assert all(s["state"] == "completed" for s in states)
        assert len(states) == 6

    def test_step_states_active_step(self) -> None:
        """Test active step identified from message."""
        from beeper_ui.routes.investigations import _get_step_states

        states = _get_step_states(
            "Correlating signals across architectural layers", "investigating"
        )
        # Customer Impact and KB Query should be completed
        assert states[0]["state"] == "completed"
        assert states[1]["state"] == "completed"
        # Signal Correlation should be active
        assert states[2]["state"] == "active"
        assert states[2]["key"] == "signal_correlation"
        # Remaining should be pending
        assert states[3]["state"] == "pending"
        assert states[4]["state"] == "pending"
        assert states[5]["state"] == "pending"

    def test_step_states_first_step(self) -> None:
        """Test first step as active."""
        from beeper_ui.routes.investigations import _get_step_states

        states = _get_step_states("Assessing customer impact", "investigating")
        assert states[0]["state"] == "active"
        assert states[1]["state"] == "pending"

    def test_step_states_failed(self) -> None:
        """Test error state on failed investigation."""
        from beeper_ui.routes.investigations import _get_step_states

        states = _get_step_states(
            "Generating root cause hypothesis", "failed"
        )
        # Steps before RCA should be completed
        assert states[0]["state"] == "completed"
        assert states[1]["state"] == "completed"
        assert states[2]["state"] == "completed"
        # RCA step should be error
        assert states[3]["state"] == "error"
        assert states[3]["key"] == "rca_hypothesis"
        # After should be pending
        assert states[4]["state"] == "pending"
        assert states[5]["state"] == "pending"

    def test_step_states_no_message(self) -> None:
        """Test step states with no message returns all pending."""
        from beeper_ui.routes.investigations import _get_step_states

        states = _get_step_states(None, "investigating")
        assert all(s["state"] == "pending" for s in states)

    def test_step_states_last_step(self) -> None:
        """Test last step as active."""
        from beeper_ui.routes.investigations import _get_step_states

        states = _get_step_states("Documenting investigation findings", "investigating")
        assert states[0]["state"] == "completed"
        assert states[1]["state"] == "completed"
        assert states[2]["state"] == "completed"
        assert states[3]["state"] == "completed"
        assert states[4]["state"] == "completed"
        assert states[5]["state"] == "active"
        assert states[5]["key"] == "documentation"


class TestDetailSSEEventGeneration:
    """Tests for SSE event generation logic."""

    @respx.mock
    def test_sse_sends_step_update_on_message_change(
        self, client: FlaskClient
    ) -> None:
        """Test SSE sends step-update event when status.message changes."""
        from unittest.mock import patch

        detail_v1 = MOCK_INVESTIGATION_DETAIL.copy()
        detail_v1["message"] = "Assessing customer impact"

        detail_v2 = MOCK_INVESTIGATION_DETAIL.copy()
        detail_v2["message"] = "Querying knowledge base"

        # First call returns v1, second returns v2
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(
            side_effect=[
                Response(200, json=detail_v1),
                Response(200, json=detail_v2),
            ]
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={},
        ), patch(
            "beeper_ui.routes.investigations.time.sleep"
        ):
            from beeper_ui.routes.investigations import _generate_detail_sse_events

            app = client.application
            with app.app_context():
                gen = _generate_detail_sse_events(
                    "http://mock-operator:8080", 5.0, "inv-detail-001"
                )
                # First event: step-update with v1
                event1 = next(gen)
                assert "event: step-update" in event1

                # Second event: step-update with v2 (message changed)
                event2 = next(gen)
                assert "event: step-update" in event2

                gen.close()

    @respx.mock
    def test_sse_sends_complete_on_phase_completed(
        self, client: FlaskClient
    ) -> None:
        """Test SSE sends investigation-complete when phase is completed."""
        from unittest.mock import patch

        detail = MOCK_INVESTIGATION_DETAIL.copy()
        detail["status"] = "completed"

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=detail))

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={},
        ), patch(
            "beeper_ui.routes.investigations.time.sleep"
        ):
            from beeper_ui.routes.investigations import _generate_detail_sse_events

            app = client.application
            with app.app_context():
                gen = _generate_detail_sse_events(
                    "http://mock-operator:8080", 5.0, "inv-detail-001"
                )
                events = list(gen)
                # Should include a step-update and investigation-complete
                assert any("event: step-update" in e for e in events)
                assert any("event: investigation-complete" in e for e in events)
                assert any("data: done" in e for e in events)

    @respx.mock
    def test_sse_sends_not_found_event(self, client: FlaskClient) -> None:
        """Test SSE sends investigation-complete with not-found when 404."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-gone"
        ).mock(return_value=Response(404, json={"error": "not found"}))

        from beeper_ui.routes.investigations import _generate_detail_sse_events

        app = client.application
        with app.app_context():
            gen = _generate_detail_sse_events(
                "http://mock-operator:8080", 5.0, "inv-gone"
            )
            events = list(gen)
            assert len(events) == 1
            assert "event: investigation-complete" in events[0]
            assert "data: not-found" in events[0]

    @respx.mock
    def test_sse_sends_findings_update_on_new_data(
        self, client: FlaskClient
    ) -> None:
        """Test SSE sends findings-update when new findings appear."""
        from unittest.mock import patch

        detail = MOCK_INVESTIGATION_DETAIL.copy()

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=detail))

        findings_v1: dict[str, object] = {}
        findings_v2 = {
            "customer_impacting": True,
            "reasoning": "Users affected",
        }

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            side_effect=[findings_v1, findings_v2],
        ), patch(
            "beeper_ui.routes.investigations.time.sleep"
        ):
            from beeper_ui.routes.investigations import _generate_detail_sse_events

            app = client.application
            with app.app_context():
                gen = _generate_detail_sse_events(
                    "http://mock-operator:8080", 5.0, "inv-detail-001"
                )
                # First iteration: step-update (initial) + no findings
                event1 = next(gen)
                assert "event: step-update" in event1

                # Second iteration: no step change, but findings appeared
                event2 = next(gen)
                assert "event: findings-update" in event2

                gen.close()

    @respx.mock
    def test_detail_page_has_investigation_link(
        self, client: FlaskClient
    ) -> None:
        """Test that investigation list rows contain navigation links."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=MOCK_INVESTIGATIONS)
        )

        response = client.get("/investigations/")
        assert response.status_code == 200
        assert b'href="/investigations/inv-abc123"' in response.data


MOCK_FINDINGS_WITH_RECOMMENDATIONS = {
    "customer_impacting": True,
    "reasoning": "Users experiencing payment failures",
    "root_cause_hypothesis": "Database pool exhausted",
    "confidence_percentage": 85,
    "confidence_level": "high",
    "recommendations": [
        {
            "action": "Scale database connection pool from 10 to 50",
            "confidence": "high",
            "expected_outcome": "Connection errors will stop within 2 minutes",
            "risk_assessment": "low",
            "based_on_prior_incident": "inc-2026-001",
        },
        {
            "action": "Restart the affected database pods",
            "confidence": "medium",
            "expected_outcome": "Clears stale connections and restores service",
            "risk_assessment": "medium",
            "based_on_prior_incident": None,
        },
        {
            "action": "Enable query timeout limits",
            "confidence": "low",
            "expected_outcome": "Prevents long-running queries from exhausting pool",
            "risk_assessment": "low",
            "based_on_prior_incident": None,
        },
    ],
    "recommendation_count": 3,
    "ranking_rationale": "Ranked by confidence level and risk assessment",
    "diagnostic_actions": [
        "Check database connection pool metrics",
        "Review slow query logs for the last hour",
    ],
    "synthesis_source": "llm",
    "resolution_model_tier": "standard",
    "resolution_model_used": "gpt-4",
    "alternative_hypotheses": [
        "Network partition between app and database",
        "Resource exhaustion on database host",
    ],
}


class TestRecommendationsDisplay:
    """Tests for recommendations and confidence display (Story 4-3)."""

    @respx.mock
    def test_recommendations_cards_rendered(self, client: FlaskClient) -> None:
        """Test recommendation cards display action, confidence, risk, outcome."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value=MOCK_FINDINGS_WITH_RECOMMENDATIONS,
        ):
            response = client.get("/investigations/inv-detail-001")
            assert response.status_code == 200
            assert b"recommendation-card" in response.data
            assert b"Scale database connection pool from 10 to 50" in response.data
            assert b"confidence-high" in response.data
            assert b"risk-low" in response.data
            assert b"Connection errors will stop within 2 minutes" in response.data

    @respx.mock
    def test_top_recommendation_highlighted(self, client: FlaskClient) -> None:
        """Test first recommendation has top recommendation class."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value=MOCK_FINDINGS_WITH_RECOMMENDATIONS,
        ):
            response = client.get("/investigations/inv-detail-001")
            assert response.status_code == 200
            assert b"recommendation-top" in response.data
            assert b"Top Recommendation" in response.data

    @respx.mock
    def test_ranking_rationale_displayed(self, client: FlaskClient) -> None:
        """Test ranking rationale text is rendered."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value=MOCK_FINDINGS_WITH_RECOMMENDATIONS,
        ):
            response = client.get("/investigations/inv-detail-001")
            assert response.status_code == 200
            assert b"ranking-rationale" in response.data
            assert b"Ranked by confidence level and risk assessment" in response.data

    @respx.mock
    def test_low_confidence_warning(self, client: FlaskClient) -> None:
        """Test low confidence warning appears when any rec has low confidence."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value=MOCK_FINDINGS_WITH_RECOMMENDATIONS,
        ):
            response = client.get("/investigations/inv-detail-001")
            assert response.status_code == 200
            assert b"low-confidence-warning" in response.data
            assert b"recommendations may need validation" in response.data

    @respx.mock
    def test_diagnostic_actions_rendered(self, client: FlaskClient) -> None:
        """Test diagnostic actions list renders when present."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value=MOCK_FINDINGS_WITH_RECOMMENDATIONS,
        ):
            response = client.get("/investigations/inv-detail-001")
            assert response.status_code == 200
            assert b"diagnostic-actions" in response.data
            assert b"Check database connection pool metrics" in response.data
            assert b"Review slow query logs for the last hour" in response.data

    @respx.mock
    def test_alternative_hypotheses_low_confidence(
        self, client: FlaskClient
    ) -> None:
        """Test alternative hypotheses display when low confidence."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value=MOCK_FINDINGS_WITH_RECOMMENDATIONS,
        ):
            response = client.get("/investigations/inv-detail-001")
            assert response.status_code == 200
            assert b"Alternative Hypotheses" in response.data
            assert b"Network partition between app and database" in response.data

    @respx.mock
    def test_empty_recommendations(self, client: FlaskClient) -> None:
        """Test empty recommendations shows in-progress message."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        findings_no_recs = {
            "customer_impacting": True,
            "reasoning": "Users affected",
        }

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value=findings_no_recs,
        ):
            response = client.get("/investigations/inv-detail-001")
            assert response.status_code == 200
            assert b"No recommendations yet" in response.data
            assert b"investigation still in progress" in response.data

    @respx.mock
    def test_fallback_source_indicator(self, client: FlaskClient) -> None:
        """Test fallback source indicator and low confidence warning."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        fallback_findings = {
            "recommendations": [
                {
                    "action": "Check service logs",
                    "confidence": "medium",
                    "expected_outcome": "Identify error patterns",
                    "risk_assessment": "low",
                    "based_on_prior_incident": None,
                },
            ],
            "ranking_rationale": "Fallback recommendations",
            "diagnostic_actions": [],
            "synthesis_source": "fallback",
        }

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value=fallback_findings,
        ):
            response = client.get("/investigations/inv-detail-001")
            assert response.status_code == 200
            assert b"synthesis-fallback" in response.data
            assert b"Fallback" in response.data
            # Fallback triggers low confidence warning
            assert b"low-confidence-warning" in response.data

    @respx.mock
    def test_prior_incident_link(self, client: FlaskClient) -> None:
        """Test prior incident link renders when based_on_prior_incident set."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value=MOCK_FINDINGS_WITH_RECOMMENDATIONS,
        ):
            response = client.get("/investigations/inv-detail-001")
            assert response.status_code == 200
            assert b"prior-incident-link" in response.data
            assert b"inc-2026-001" in response.data

    @respx.mock
    def test_recommendations_htmx_partial(self, client: FlaskClient) -> None:
        """Test HTMX partial response includes recommendations HTML."""
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=MOCK_INVESTIGATION_DETAIL))

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value=MOCK_FINDINGS_WITH_RECOMMENDATIONS,
        ):
            response = client.get(
                "/investigations/inv-detail-001",
                headers={"HX-Request": "true"},
            )
            assert response.status_code == 200
            assert b"<!DOCTYPE html>" not in response.data
            assert b"recommendation-card" in response.data
            assert b"recommendation-top" in response.data

    @respx.mock
    def test_sse_findings_update_includes_recommendations(
        self, client: FlaskClient
    ) -> None:
        """Test SSE findings-update event includes recommendation cards."""
        detail = MOCK_INVESTIGATION_DETAIL.copy()

        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
        ).mock(return_value=Response(200, json=detail))

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            side_effect=[{}, MOCK_FINDINGS_WITH_RECOMMENDATIONS],
        ), patch(
            "beeper_ui.routes.investigations.time.sleep"
        ):
            from beeper_ui.routes.investigations import _generate_detail_sse_events

            app = client.application
            with app.app_context():
                gen = _generate_detail_sse_events(
                    "http://mock-operator:8080", 5.0, "inv-detail-001"
                )
                # First: step-update (initial)
                event1 = next(gen)
                assert "event: step-update" in event1

                # Second: findings-update with recommendations
                event2 = next(gen)
                assert "event: findings-update" in event2
                assert "recommendation-card" in event2

                gen.close()
