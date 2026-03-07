"""Tests for Investigation service."""

import pytest
import respx
from httpx import Response

from beeper_ui.services.investigation_service import (
    Investigation,
    InvestigationService,
    InvestigationServiceError,
)


class TestInvestigation:
    """Tests for Investigation dataclass."""

    def test_from_dict(self) -> None:
        """Test creating Investigation from dictionary."""
        data = {
            "id": "inv-abc123",
            "status": "investigating",
            "service": "payments",
            "severity": "high",
            "condition": "High error rate detected",
            "started_at": "2026-02-09T12:00:00Z",
            "completed_at": None,
            "triggered_at": "2026-02-09T11:55:00Z",
        }
        inv = Investigation.from_dict(data)
        assert inv.id == "inv-abc123"
        assert inv.status == "investigating"
        assert inv.service == "payments"
        assert inv.severity == "high"
        assert inv.condition == "High error rate detected"
        assert inv.started_at == "2026-02-09T12:00:00Z"
        assert inv.completed_at is None
        assert inv.triggered_at == "2026-02-09T11:55:00Z"

    def test_from_dict_minimal(self) -> None:
        """Test creating Investigation with minimal fields."""
        data = {
            "id": "inv-xyz",
            "status": "investigating",
            "service": "api",
            "severity": "low",
            "condition": "Latency spike",
        }
        inv = Investigation.from_dict(data)
        assert inv.id == "inv-xyz"
        assert inv.started_at is None
        assert inv.completed_at is None
        assert inv.triggered_at is None


class TestInvestigationService:
    """Tests for InvestigationService."""

    @respx.mock
    def test_list_investigations_success(self) -> None:
        """Test successful investigation list fetch."""
        mock_response = [
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
                "condition": "Latency spike",
                "started_at": "2026-02-09T10:00:00Z",
                "completed_at": "2026-02-09T10:15:00Z",
                "triggered_at": "2026-02-09T09:55:00Z",
            },
        ]

        respx.get("http://localhost:8080/api/v1/investigations").mock(
            return_value=Response(200, json=mock_response)
        )

        service = InvestigationService("http://localhost:8080")
        investigations = service.list_investigations()

        assert len(investigations) == 2
        assert investigations[0].id == "inv-abc123"
        assert investigations[0].status == "investigating"
        assert investigations[1].id == "inv-xyz789"
        assert investigations[1].status == "completed"

    @respx.mock
    def test_list_investigations_with_filters(self) -> None:
        """Test investigation list with filter params."""
        respx.get("http://localhost:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[])
        )

        service = InvestigationService("http://localhost:8080")
        service.list_investigations(
            status="investigating",
            service="payments",
            severity="high",
        )

        # Verify query params were sent
        request = respx.calls.last.request
        assert "status=investigating" in str(request.url)
        assert "service=payments" in str(request.url)
        assert "severity=high" in str(request.url)

    @respx.mock
    def test_list_investigations_empty(self) -> None:
        """Test empty investigations response."""
        respx.get("http://localhost:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[])
        )

        service = InvestigationService("http://localhost:8080")
        investigations = service.list_investigations()

        assert investigations == []

    @respx.mock
    def test_list_investigations_timeout(self) -> None:
        """Test timeout handling."""
        import httpx

        respx.get("http://localhost:8080/api/v1/investigations").mock(
            side_effect=httpx.TimeoutException("Request timed out")
        )

        service = InvestigationService("http://localhost:8080", timeout=1.0)

        with pytest.raises(InvestigationServiceError) as exc_info:
            service.list_investigations()

        assert "Timeout" in str(exc_info.value)

    @respx.mock
    def test_list_investigations_connection_error(self) -> None:
        """Test connection error handling."""
        import httpx

        respx.get("http://localhost:8080/api/v1/investigations").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        service = InvestigationService("http://localhost:8080")

        with pytest.raises(InvestigationServiceError) as exc_info:
            service.list_investigations()

        assert "Failed to connect" in str(exc_info.value)

    @respx.mock
    def test_list_investigations_http_error(self) -> None:
        """Test HTTP error handling."""
        respx.get("http://localhost:8080/api/v1/investigations").mock(
            return_value=Response(500, json={"error": "Internal server error"})
        )

        service = InvestigationService("http://localhost:8080")

        with pytest.raises(InvestigationServiceError) as exc_info:
            service.list_investigations()

        assert "500" in str(exc_info.value)

    @respx.mock
    def test_list_investigations_no_filters(self) -> None:
        """Test that no query params are sent when no filters provided."""
        respx.get("http://localhost:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[])
        )

        service = InvestigationService("http://localhost:8080")
        service.list_investigations()

        request = respx.calls.last.request
        assert str(request.url) == "http://localhost:8080/api/v1/investigations"
