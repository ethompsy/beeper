"""Tests for Investigation service."""

from unittest.mock import MagicMock, patch

import pytest
import respx
from httpx import Response

from beeper_ui.services.investigation_service import (
    Investigation,
    InvestigationDetail,
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


class TestInvestigationDetail:
    """Tests for InvestigationDetail dataclass."""

    def test_from_dict(self) -> None:
        """Test creating InvestigationDetail from dictionary."""
        data = {
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
        detail = InvestigationDetail.from_dict(data)
        assert detail.id == "inv-detail-001"
        assert detail.message == "Correlating signals across architectural layers"
        assert detail.error is None
        assert detail.job_name == "inv-detail-001-job"
        # Base fields
        assert detail.status == "investigating"
        assert detail.service == "payments"

    def test_from_dict_minimal(self) -> None:
        """Test InvestigationDetail with no optional detail fields."""
        data = {
            "id": "inv-min",
            "status": "investigating",
            "service": "api",
            "severity": "low",
            "condition": "Test",
        }
        detail = InvestigationDetail.from_dict(data)
        assert detail.message is None
        assert detail.error is None
        assert detail.job_name is None

    def test_inherits_from_investigation(self) -> None:
        """Test InvestigationDetail is an Investigation subclass."""
        detail = InvestigationDetail(
            id="inv-1", status="investigating", service="api",
            severity="high", condition="test",
        )
        assert isinstance(detail, Investigation)


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

    @respx.mock
    def test_get_investigation_success(self) -> None:
        """Test fetching a single investigation detail."""
        mock_detail = {
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

        respx.get("http://localhost:8080/api/v1/investigations/inv-detail-001").mock(
            return_value=Response(200, json=mock_detail)
        )

        service = InvestigationService("http://localhost:8080")
        result = service.get_investigation("inv-detail-001")

        assert result is not None
        assert isinstance(result, InvestigationDetail)
        assert result.id == "inv-detail-001"
        assert result.message == "Correlating signals across architectural layers"
        assert result.job_name == "inv-detail-001-job"

    @respx.mock
    def test_get_investigation_not_found(self) -> None:
        """Test get_investigation returns None for 404."""
        respx.get("http://localhost:8080/api/v1/investigations/inv-nonexistent").mock(
            return_value=Response(404, json={"error": "Not found"})
        )

        service = InvestigationService("http://localhost:8080")
        result = service.get_investigation("inv-nonexistent")

        assert result is None

    @respx.mock
    def test_get_investigation_connection_error(self) -> None:
        """Test get_investigation raises on connection error."""
        import httpx

        respx.get("http://localhost:8080/api/v1/investigations/inv-001").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        service = InvestigationService("http://localhost:8080")

        with pytest.raises(InvestigationServiceError) as exc_info:
            service.get_investigation("inv-001")

        assert "Failed to connect" in str(exc_info.value)

    @respx.mock
    def test_get_investigation_timeout(self) -> None:
        """Test get_investigation raises on timeout."""
        import httpx

        respx.get("http://localhost:8080/api/v1/investigations/inv-001").mock(
            side_effect=httpx.TimeoutException("Timeout")
        )

        service = InvestigationService("http://localhost:8080")

        with pytest.raises(InvestigationServiceError) as exc_info:
            service.get_investigation("inv-001")

        assert "Timeout" in str(exc_info.value)

    def test_get_investigation_findings_success(self) -> None:
        """Test fetching investigation findings from Qdrant."""
        mock_point = MagicMock()
        mock_point.payload = {
            "investigation_id": "inv-001",
            "customer_impacting": True,
            "reasoning": "High error rate affecting users",
            "root_cause_hypothesis": "Database connection pool exhausted",
            "confidence_percentage": 85,
        }

        mock_qdrant = MagicMock()
        mock_qdrant.scroll.return_value = ([mock_point], None)

        service = InvestigationService("http://localhost:8080")
        service._qdrant_client = mock_qdrant

        result = service.get_investigation_findings("inv-001")

        assert result["customer_impacting"] is True
        assert result["root_cause_hypothesis"] == "Database connection pool exhausted"
        assert result["confidence_percentage"] == 85

    def test_get_investigation_findings_not_found(self) -> None:
        """Test findings returns empty dict when not found."""
        mock_qdrant = MagicMock()
        mock_qdrant.scroll.return_value = ([], None)

        service = InvestigationService("http://localhost:8080")
        service._qdrant_client = mock_qdrant

        result = service.get_investigation_findings("inv-nonexistent")

        assert result == {}

    def test_get_investigation_findings_qdrant_error(self) -> None:
        """Test findings returns empty dict on Qdrant error."""
        mock_qdrant = MagicMock()
        mock_qdrant.scroll.side_effect = Exception("Qdrant unavailable")

        service = InvestigationService("http://localhost:8080")
        service._qdrant_client = mock_qdrant

        result = service.get_investigation_findings("inv-001")

        assert result == {}

    def test_close_closes_qdrant_client(self) -> None:
        """Test close() closes both httpx and Qdrant clients."""
        mock_qdrant = MagicMock()

        service = InvestigationService("http://localhost:8080")
        service._qdrant_client = mock_qdrant
        # Initialize httpx client
        _ = service.client

        service.close()

        mock_qdrant.close.assert_called_once()
        assert service._qdrant_client is None
        assert service._client is None

    def test_close_without_qdrant(self) -> None:
        """Test close() works when Qdrant client was never initialized."""
        service = InvestigationService("http://localhost:8080")
        # Initialize httpx client
        _ = service.client

        # Should not raise
        service.close()
        assert service._client is None
        assert service._qdrant_client is None
