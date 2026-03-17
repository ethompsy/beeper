"""Tests for Investigation service."""

from unittest.mock import MagicMock

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


class TestConfirmResolution:
    """Tests for InvestigationService.confirm_resolution()."""

    @respx.mock
    def test_confirm_resolution_success(self) -> None:
        """Test successful confirmation returns True."""
        respx.post(
            "http://localhost:8080/api/v1/investigations/inv-001/confirm"
        ).mock(
            return_value=Response(
                200, json={"status": "ok", "message": "Resolution confirmed"}
            )
        )

        service = InvestigationService("http://localhost:8080")
        result = service.confirm_resolution("inv-001", comment="Looks good")

        assert result is True
        request = respx.calls.last.request
        assert b'"comment"' in request.content

    @respx.mock
    def test_confirm_resolution_not_found(self) -> None:
        """Test confirmation returns False for 404."""
        respx.post(
            "http://localhost:8080/api/v1/investigations/inv-gone/confirm"
        ).mock(return_value=Response(404, json={"error": "not found"}))

        service = InvestigationService("http://localhost:8080")
        result = service.confirm_resolution("inv-gone")

        assert result is False

    @respx.mock
    def test_confirm_resolution_connection_error(self) -> None:
        """Test confirmation raises on connection error."""
        import httpx

        respx.post(
            "http://localhost:8080/api/v1/investigations/inv-001/confirm"
        ).mock(side_effect=httpx.ConnectError("Connection refused"))

        service = InvestigationService("http://localhost:8080")

        with pytest.raises(InvestigationServiceError) as exc_info:
            service.confirm_resolution("inv-001")

        assert "Failed to connect" in str(exc_info.value)

    @respx.mock
    def test_confirm_resolution_timeout(self) -> None:
        """Test confirmation raises on timeout."""
        import httpx

        respx.post(
            "http://localhost:8080/api/v1/investigations/inv-001/confirm"
        ).mock(side_effect=httpx.TimeoutException("Timeout"))

        service = InvestigationService("http://localhost:8080")

        with pytest.raises(InvestigationServiceError) as exc_info:
            service.confirm_resolution("inv-001")

        assert "Timeout" in str(exc_info.value)


class TestRejectResolution:
    """Tests for InvestigationService.reject_resolution()."""

    @respx.mock
    def test_reject_resolution_success(self) -> None:
        """Test successful rejection returns True."""
        respx.post(
            "http://localhost:8080/api/v1/investigations/inv-001/reject"
        ).mock(
            return_value=Response(
                200, json={"status": "ok", "message": "Resolution rejected"}
            )
        )

        service = InvestigationService("http://localhost:8080")
        result = service.reject_resolution(
            "inv-001",
            reason="hypothesis_incorrect",
            reason_details="The root cause is actually a network issue",
            correction="Check network connectivity",
        )

        assert result is True
        request = respx.calls.last.request
        assert b'"reason"' in request.content
        assert b'"reason_details"' in request.content
        assert b'"correction"' in request.content

    @respx.mock
    def test_reject_resolution_not_found(self) -> None:
        """Test rejection returns False for 404."""
        respx.post(
            "http://localhost:8080/api/v1/investigations/inv-gone/reject"
        ).mock(return_value=Response(404, json={"error": "not found"}))

        service = InvestigationService("http://localhost:8080")
        result = service.reject_resolution("inv-gone", reason="other")

        assert result is False

    @respx.mock
    def test_reject_resolution_connection_error(self) -> None:
        """Test rejection raises on connection error."""
        import httpx

        respx.post(
            "http://localhost:8080/api/v1/investigations/inv-001/reject"
        ).mock(side_effect=httpx.ConnectError("Connection refused"))

        service = InvestigationService("http://localhost:8080")

        with pytest.raises(InvestigationServiceError) as exc_info:
            service.reject_resolution("inv-001", reason="other")

        assert "Failed to connect" in str(exc_info.value)


class TestSaveResolutionFeedback:
    """Tests for InvestigationService.save_resolution_feedback()."""

    def test_save_feedback_success(self) -> None:
        """Test feedback saved via Qdrant set_payload."""
        mock_point = MagicMock()
        mock_point.id = "point-123"

        mock_qdrant = MagicMock()
        mock_qdrant.scroll.return_value = ([mock_point], None)

        service = InvestigationService("http://localhost:8080")
        service._qdrant_client = mock_qdrant

        feedback = {
            "resolution_action": "confirmed",
            "resolution_comment": "Looks correct",
        }
        service.save_resolution_feedback("inv-001", feedback)

        mock_qdrant.set_payload.assert_called_once_with(
            collection_name="investigations",
            payload=feedback,
            points=["point-123"],
        )

    def test_save_feedback_no_qdrant_record(self) -> None:
        """Test feedback silently skipped when no Qdrant record found."""
        mock_qdrant = MagicMock()
        mock_qdrant.scroll.return_value = ([], None)

        service = InvestigationService("http://localhost:8080")
        service._qdrant_client = mock_qdrant

        service.save_resolution_feedback("inv-missing", {"action": "confirmed"})

        mock_qdrant.set_payload.assert_not_called()

    def test_save_feedback_qdrant_error_swallowed(self) -> None:
        """Test Qdrant errors are swallowed (logged, not raised)."""
        mock_qdrant = MagicMock()
        mock_qdrant.scroll.side_effect = Exception("Qdrant unavailable")

        service = InvestigationService("http://localhost:8080")
        service._qdrant_client = mock_qdrant

        # Should not raise
        service.save_resolution_feedback("inv-001", {"action": "confirmed"})


class TestResolveInvestigation:
    """Tests for InvestigationService.resolve_investigation()."""

    @respx.mock
    def test_resolve_investigation_success(self) -> None:
        """Test successful resolution returns True."""
        respx.post("http://localhost:8080/api/v1/investigations/inv-001/resolve").mock(
            return_value=Response(200, json={"status": "resolved", "message": "OK"})
        )
        service = InvestigationService("http://localhost:8080")
        result = service.resolve_investigation(
            "inv-001",
            outcome="resolved",
            accuracy_rating="correct",
            resolution_notes="Fixed",
        )
        assert result is True
        req = respx.calls.last.request
        assert b'"outcome"' in req.content
        assert b'"resolved"' in req.content
        assert b'"accuracy_rating"' in req.content

    @respx.mock
    def test_resolve_investigation_not_found(self) -> None:
        """Test 404 returns False."""
        respx.post("http://localhost:8080/api/v1/investigations/inv-missing/resolve").mock(
            return_value=Response(404, json={"title": "Not found"})
        )
        service = InvestigationService("http://localhost:8080")
        result = service.resolve_investigation("inv-missing", outcome="resolved")
        assert result is False

    @respx.mock
    def test_resolve_investigation_connection_error(self) -> None:
        """Test connection error raises InvestigationServiceError."""
        import httpx

        respx.post("http://localhost:8080/api/v1/investigations/inv-001/resolve").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        service = InvestigationService("http://localhost:8080")
        with pytest.raises(InvestigationServiceError, match="Failed to connect"):
            service.resolve_investigation("inv-001", outcome="resolved")

    @respx.mock
    def test_resolve_investigation_escalated(self) -> None:
        """Test escalated outcome sends correct payload."""
        respx.post("http://localhost:8080/api/v1/investigations/inv-001/resolve").mock(
            return_value=Response(200, json={"status": "escalated", "message": "OK"})
        )
        service = InvestigationService("http://localhost:8080")
        result = service.resolve_investigation(
            "inv-001",
            outcome="escalated",
            escalation_target="platform-team",
        )
        assert result is True
        req = respx.calls.last.request
        assert b'"escalated"' in req.content
        assert b'"platform-team"' in req.content


class TestUpdateKBWithResolution:
    """Tests for InvestigationService.update_kb_with_resolution()."""

    def test_update_kb_success(self) -> None:
        """Test KB entry found and updated."""
        mock_point = MagicMock()
        mock_point.id = "kb-point-456"

        mock_qdrant = MagicMock()
        mock_qdrant.scroll.return_value = ([mock_point], None)

        service = InvestigationService("http://localhost:8080")
        service._qdrant_client = mock_qdrant

        resolution_data = {
            "resolution_outcome": "resolved",
            "accuracy_rating": "correct",
            "mttr_seconds": 3420,
        }
        result = service.update_kb_with_resolution("inv-001", resolution_data)
        assert result is True

        mock_qdrant.set_payload.assert_called_once_with(
            collection_name="knowledge",
            payload=resolution_data,
            points=["kb-point-456"],
        )

    def test_update_kb_no_entry(self) -> None:
        """Test returns False when no KB entry for investigation."""
        mock_qdrant = MagicMock()
        mock_qdrant.scroll.return_value = ([], None)

        service = InvestigationService("http://localhost:8080")
        service._qdrant_client = mock_qdrant

        result = service.update_kb_with_resolution("inv-missing", {"outcome": "resolved"})
        assert result is False
        mock_qdrant.set_payload.assert_not_called()

    def test_update_kb_error_swallowed(self) -> None:
        """Test Qdrant errors are swallowed."""
        mock_qdrant = MagicMock()
        mock_qdrant.scroll.side_effect = Exception("Qdrant down")

        service = InvestigationService("http://localhost:8080")
        service._qdrant_client = mock_qdrant

        result = service.update_kb_with_resolution("inv-001", {"outcome": "resolved"})
        assert result is False


class TestCalculateMTTR:
    """Tests for InvestigationService.calculate_mttr()."""

    def test_calculate_mttr_valid(self) -> None:
        """Test MTTR calculated from valid timestamps."""
        result = InvestigationService.calculate_mttr(
            "2026-03-07T10:00:00Z", "2026-03-07T10:57:00Z"
        )
        assert result == 3420  # 57 minutes = 3420 seconds

    def test_calculate_mttr_none_started_at(self) -> None:
        """Test returns None when started_at is None."""
        result = InvestigationService.calculate_mttr(None, "2026-03-07T10:57:00Z")
        assert result is None

    def test_calculate_mttr_with_offset(self) -> None:
        """Test MTTR with timezone-aware timestamps."""
        result = InvestigationService.calculate_mttr(
            "2026-03-07T10:00:00+00:00", "2026-03-07T11:00:00+00:00"
        )
        assert result == 3600  # 1 hour

    def test_calculate_mttr_invalid_format(self) -> None:
        """Test returns None for invalid timestamp format."""
        result = InvestigationService.calculate_mttr(
            "not-a-date", "2026-03-07T10:57:00Z"
        )
        assert result is None


class TestAnnotateInvestigation:
    """Tests for annotate_investigation method."""

    OPERATOR_URL = "http://mock-operator:8080"

    def _make_service(self) -> InvestigationService:
        return InvestigationService(operator_url=self.OPERATOR_URL)

    @respx.mock
    def test_annotate_success(self) -> None:
        """Test successful annotation."""
        respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-001/annotate"
        ).mock(return_value=Response(200, json={"ok": True}))
        svc = self._make_service()
        result = svc.annotate_investigation("inv-001", "DB issue", "admin")
        assert result is True

    @respx.mock
    def test_annotate_not_found(self) -> None:
        """Test annotation on non-existent investigation returns False."""
        respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-999/annotate"
        ).mock(return_value=Response(404))
        svc = self._make_service()
        result = svc.annotate_investigation("inv-999", "text", "user")
        assert result is False

    @respx.mock
    def test_annotate_server_error_returns_false(self) -> None:
        """Test annotation gracefully handles server errors."""
        respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-001/annotate"
        ).mock(return_value=Response(500))
        svc = self._make_service()
        result = svc.annotate_investigation("inv-001", "text", "user")
        assert result is False

    @respx.mock
    def test_annotate_sends_correct_payload(self) -> None:
        """Test annotation sends correct JSON payload."""
        route = respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-001/annotate"
        ).mock(return_value=Response(200, json={"ok": True}))
        svc = self._make_service()
        svc.annotate_investigation("inv-001", "Check pools", "admin")
        assert route.called
        body = route.calls[0].request.content
        import json
        payload = json.loads(body)
        assert payload["text"] == "Check pools"
        assert payload["user"] == "admin"


class TestRedirectInvestigation:
    """Tests for redirect_investigation method."""

    OPERATOR_URL = "http://mock-operator:8080"

    def _make_service(self) -> InvestigationService:
        return InvestigationService(operator_url=self.OPERATOR_URL)

    @respx.mock
    def test_redirect_success(self) -> None:
        """Test successful redirect."""
        respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-001/redirect"
        ).mock(return_value=Response(200, json={"ok": True}))
        svc = self._make_service()
        result = svc.redirect_investigation("inv-001", "Focus on DB", "admin")
        assert result is True

    @respx.mock
    def test_redirect_not_found(self) -> None:
        """Test redirect on non-existent investigation returns False."""
        respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-999/redirect"
        ).mock(return_value=Response(404))
        svc = self._make_service()
        result = svc.redirect_investigation("inv-999", "instruction", "user")
        assert result is False

    @respx.mock
    def test_redirect_server_error_returns_false(self) -> None:
        """Test redirect gracefully handles server errors."""
        respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-001/redirect"
        ).mock(return_value=Response(500))
        svc = self._make_service()
        result = svc.redirect_investigation("inv-001", "instruction", "user")
        assert result is False

    @respx.mock
    def test_redirect_sends_correct_payload(self) -> None:
        """Test redirect sends correct JSON payload."""
        route = respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-001/redirect"
        ).mock(return_value=Response(200, json={"ok": True}))
        svc = self._make_service()
        svc.redirect_investigation("inv-001", "Focus on caching", "admin")
        assert route.called
        body = route.calls[0].request.content
        import json
        payload = json.loads(body)
        assert payload["instruction"] == "Focus on caching"
        assert payload["user"] == "admin"


class TestApproveFix:
    """Tests for approve_fix method."""

    OPERATOR_URL = "http://mock-operator:8080"

    def _make_service(self) -> InvestigationService:
        return InvestigationService(operator_url=self.OPERATOR_URL)

    @respx.mock
    def test_approve_fix_success(self) -> None:
        """Test successful fix approval."""
        respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-001/approve"
        ).mock(return_value=Response(200, json={"ok": True}))
        svc = self._make_service()
        result = svc.approve_fix("inv-001", "admin")
        assert result is True

    @respx.mock
    def test_approve_fix_not_found(self) -> None:
        """Test approval on non-existent investigation returns False."""
        respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-999/approve"
        ).mock(return_value=Response(404))
        svc = self._make_service()
        result = svc.approve_fix("inv-999", "user")
        assert result is False

    @respx.mock
    def test_approve_fix_server_error_returns_false(self) -> None:
        """Test approval gracefully handles server errors."""
        respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-001/approve"
        ).mock(return_value=Response(500))
        svc = self._make_service()
        result = svc.approve_fix("inv-001", "user")
        assert result is False

    @respx.mock
    def test_approve_fix_timeout_returns_false(self) -> None:
        """Test approval gracefully handles timeout."""
        import httpx

        respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-001/approve"
        ).mock(side_effect=httpx.TimeoutException("Timeout"))
        svc = self._make_service()
        result = svc.approve_fix("inv-001", "user")
        assert result is False

    @respx.mock
    def test_approve_fix_connection_error_returns_false(self) -> None:
        """Test approval gracefully handles connection errors."""
        import httpx

        respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-001/approve"
        ).mock(side_effect=httpx.ConnectError("Connection refused"))
        svc = self._make_service()
        result = svc.approve_fix("inv-001", "user")
        assert result is False

    @respx.mock
    def test_approve_fix_sends_correct_payload(self) -> None:
        """Test approval sends correct JSON payload."""
        route = respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-001/approve"
        ).mock(return_value=Response(200, json={"ok": True}))
        svc = self._make_service()
        svc.approve_fix("inv-001", "admin")
        assert route.called
        body = route.calls[0].request.content
        import json
        payload = json.loads(body)
        assert payload["user"] == "admin"


class TestRejectFix:
    """Tests for reject_fix method."""

    OPERATOR_URL = "http://mock-operator:8080"

    def _make_service(self) -> InvestigationService:
        return InvestigationService(operator_url=self.OPERATOR_URL)

    @respx.mock
    def test_reject_fix_success(self) -> None:
        """Test successful fix rejection."""
        respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-001/reject-fix"
        ).mock(return_value=Response(200, json={"ok": True}))
        svc = self._make_service()
        result = svc.reject_fix("inv-001", "admin", reason="Wrong approach")
        assert result is True

    @respx.mock
    def test_reject_fix_not_found(self) -> None:
        """Test rejection on non-existent investigation returns False."""
        respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-999/reject-fix"
        ).mock(return_value=Response(404))
        svc = self._make_service()
        result = svc.reject_fix("inv-999", "user")
        assert result is False

    @respx.mock
    def test_reject_fix_server_error_returns_false(self) -> None:
        """Test rejection gracefully handles server errors."""
        respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-001/reject-fix"
        ).mock(return_value=Response(500))
        svc = self._make_service()
        result = svc.reject_fix("inv-001", "user")
        assert result is False

    @respx.mock
    def test_reject_fix_timeout_returns_false(self) -> None:
        """Test rejection gracefully handles timeout."""
        import httpx

        respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-001/reject-fix"
        ).mock(side_effect=httpx.TimeoutException("Timeout"))
        svc = self._make_service()
        result = svc.reject_fix("inv-001", "user")
        assert result is False

    @respx.mock
    def test_reject_fix_connection_error_returns_false(self) -> None:
        """Test rejection gracefully handles connection errors."""
        import httpx

        respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-001/reject-fix"
        ).mock(side_effect=httpx.ConnectError("Connection refused"))
        svc = self._make_service()
        result = svc.reject_fix("inv-001", "user")
        assert result is False

    @respx.mock
    def test_reject_fix_sends_correct_payload_with_reason(self) -> None:
        """Test rejection sends correct JSON payload with reason."""
        route = respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-001/reject-fix"
        ).mock(return_value=Response(200, json={"ok": True}))
        svc = self._make_service()
        svc.reject_fix("inv-001", "admin", reason="Wrong approach")
        assert route.called
        body = route.calls[0].request.content
        import json
        payload = json.loads(body)
        assert payload["user"] == "admin"
        assert payload["reason"] == "Wrong approach"

    @respx.mock
    def test_reject_fix_sends_payload_without_reason(self) -> None:
        """Test rejection sends payload with null reason when not provided."""
        route = respx.post(
            f"{self.OPERATOR_URL}/api/v1/investigations/inv-001/reject-fix"
        ).mock(return_value=Response(200, json={"ok": True}))
        svc = self._make_service()
        svc.reject_fix("inv-001", "admin")
        assert route.called
        body = route.calls[0].request.content
        import json
        payload = json.loads(body)
        assert payload["user"] == "admin"
        assert payload["reason"] is None
