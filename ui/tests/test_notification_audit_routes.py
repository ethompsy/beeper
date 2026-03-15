"""Tests for notification audit API routes and integration."""

from typing import Any
from unittest.mock import patch

import pytest
import respx
from flask import Flask
from flask.testing import FlaskClient
from httpx import Response

from tests.conftest import _RoleClient


@pytest.fixture
def user_client(app: Flask) -> _RoleClient:
    """Create test client with user role."""
    with app.test_client() as test_client:
        yield _RoleClient(test_client, "user")


@pytest.fixture
def user_get(app: Flask) -> _RoleClient:
    """Create test client with user role for GET requests."""
    with app.test_client() as test_client:
        yield _RoleClient(test_client, "user")


# --- Audit recording integration tests ---


class TestAuditRecordingIntegration:
    """Tests that audit records are created during notification delivery."""

    @patch("beeper_ui.routes.notifications.NotificationAuditService")
    @patch("beeper_ui.routes.notifications.NotificationDeliveryService")
    def test_audit_recorded_on_successful_delivery(
        self, mock_svc_class: Any, mock_audit_class: Any, user_client: _RoleClient
    ) -> None:
        """Audit record is created when delivery succeeds."""
        mock_svc = mock_svc_class.return_value
        mock_svc.process_outbox_entry.return_value = {
            "status": "delivered",
            "channel": "C123",
        }
        mock_audit = mock_audit_class.return_value

        resp = user_client.post(
            "/api/v1/notifications/deliver",
            json={
                "entry": {
                    "investigation_id": "inv-001",
                    "event_type": "investigation_started",
                    "severity": "high",
                    "service": "payment-service",
                    "payload": {},
                },
                "channel_config": {
                    "channel_type": "slack",
                    "name": "ops-alerts",
                    "config": {"channel": "#alerts"},
                },
                "bot_token": "xoxb-test",
            },
        )

        assert resp.status_code == 200
        mock_audit.record_audit.assert_called_once()
        call_args = mock_audit.record_audit.call_args
        assert call_args[0][0]["investigation_id"] == "inv-001"
        assert call_args[0][1]["channel_type"] == "slack"
        assert call_args[0][2]["status"] == "delivered"

    @patch("beeper_ui.routes.notifications.NotificationAuditService")
    @patch("beeper_ui.routes.notifications.NotificationDeliveryService")
    def test_audit_recorded_on_failed_delivery(
        self, mock_svc_class: Any, mock_audit_class: Any, user_client: _RoleClient
    ) -> None:
        """Audit record is created when delivery fails."""
        from beeper_ui.services.notification_service import NotificationServiceError

        mock_svc = mock_svc_class.return_value
        mock_svc.process_outbox_entry.side_effect = NotificationServiceError(
            "Connection refused", retryable=True
        )
        mock_audit = mock_audit_class.return_value

        resp = user_client.post(
            "/api/v1/notifications/deliver",
            json={
                "entry": {"investigation_id": "inv-002", "payload": {}},
                "channel_config": {"channel_type": "slack", "config": {}},
            },
        )

        assert resp.status_code == 502
        mock_audit.record_audit.assert_called_once()
        call_args = mock_audit.record_audit.call_args
        assert call_args[0][2]["status"] == "failed"
        assert "Connection refused" in call_args[0][2]["error"]

    @patch("beeper_ui.routes.notifications.NotificationAuditService")
    @patch("beeper_ui.routes.notifications.NotificationDeliveryService")
    def test_audit_recorded_on_unexpected_error(
        self, mock_svc_class: Any, mock_audit_class: Any, user_client: _RoleClient
    ) -> None:
        """Audit record is created on unexpected delivery errors."""
        mock_svc = mock_svc_class.return_value
        mock_svc.process_outbox_entry.side_effect = RuntimeError("Unexpected")
        mock_audit = mock_audit_class.return_value

        resp = user_client.post(
            "/api/v1/notifications/deliver",
            json={
                "entry": {"investigation_id": "inv-003", "payload": {}},
                "channel_config": {"channel_type": "webhook", "config": {}},
            },
        )

        assert resp.status_code == 500
        mock_audit.record_audit.assert_called_once()
        call_args = mock_audit.record_audit.call_args
        assert call_args[0][2]["status"] == "failed"

    @patch("beeper_ui.routes.notifications.NotificationAuditService")
    @patch("beeper_ui.routes.notifications.NotificationDeliveryService")
    def test_audit_failure_does_not_fail_delivery(
        self, mock_svc_class: Any, mock_audit_class: Any, user_client: _RoleClient
    ) -> None:
        """Audit recording failure does not affect delivery response."""
        mock_svc = mock_svc_class.return_value
        mock_svc.process_outbox_entry.return_value = {"status": "delivered"}
        mock_audit = mock_audit_class.return_value
        mock_audit.record_audit.side_effect = Exception("Qdrant down")

        resp = user_client.post(
            "/api/v1/notifications/deliver",
            json={
                "entry": {"investigation_id": "inv-004", "payload": {}},
                "channel_config": {"channel_type": "slack", "config": {}},
            },
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "delivered"

    @patch("beeper_ui.routes.notifications.NotificationAuditService")
    @patch("beeper_ui.routes.notifications.NotificationDeliveryService")
    def test_audit_close_called_after_recording(
        self, mock_svc_class: Any, mock_audit_class: Any, user_client: _RoleClient
    ) -> None:
        """Audit service is always closed after recording."""
        mock_svc = mock_svc_class.return_value
        mock_svc.process_outbox_entry.return_value = {"status": "delivered"}
        mock_audit = mock_audit_class.return_value

        user_client.post(
            "/api/v1/notifications/deliver",
            json={
                "entry": {"investigation_id": "inv-005", "payload": {}},
                "channel_config": {"channel_type": "email", "config": {}},
            },
        )

        mock_audit.close.assert_called_once()


# --- Audit query endpoint tests ---


class TestGetNotificationAudit:
    """Tests for GET /api/v1/notifications/audit endpoint."""

    @patch("beeper_ui.routes.notifications.NotificationAuditService")
    def test_returns_records_and_statistics(
        self, mock_audit_class: Any, user_get: _RoleClient
    ) -> None:
        """Returns audit records and statistics."""
        mock_audit = mock_audit_class.return_value
        mock_audit.query_audit.return_value = [
            {"investigation_id": "inv-001", "delivery_status": "delivered"},
        ]
        mock_audit.get_audit_statistics.return_value = {
            "total_notifications": 10,
            "false_page_count": 2,
            "false_page_rate": 0.2,
        }

        resp = user_get.get("/api/v1/notifications/audit")

        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["records"]) == 1
        assert data["statistics"]["total_notifications"] == 10
        assert data["statistics"]["false_page_count"] == 2
        assert data["statistics"]["false_page_rate"] == 0.2
        assert data["limit"] == 50
        assert data["offset"] == 0

    @patch("beeper_ui.routes.notifications.NotificationAuditService")
    def test_passes_service_filter(
        self, mock_audit_class: Any, user_get: _RoleClient
    ) -> None:
        """Passes service query parameter to audit service."""
        mock_audit = mock_audit_class.return_value
        mock_audit.query_audit.return_value = []
        mock_audit.get_audit_statistics.return_value = {
            "total_notifications": 0,
            "false_page_count": 0,
            "false_page_rate": 0.0,
        }

        user_get.get("/api/v1/notifications/audit?service=payment-service")

        call_args = mock_audit.query_audit.call_args
        assert call_args.kwargs["service"] == "payment-service"

    @patch("beeper_ui.routes.notifications.NotificationAuditService")
    def test_passes_channel_type_filter(
        self, mock_audit_class: Any, user_get: _RoleClient
    ) -> None:
        """Passes channel_type query parameter."""
        mock_audit = mock_audit_class.return_value
        mock_audit.query_audit.return_value = []
        mock_audit.get_audit_statistics.return_value = {
            "total_notifications": 0,
            "false_page_count": 0,
            "false_page_rate": 0.0,
        }

        user_get.get("/api/v1/notifications/audit?channel_type=slack")

        call_args = mock_audit.query_audit.call_args
        assert call_args.kwargs["channel_type"] == "slack"
        # Verify channel_type is also passed to statistics
        stats_args = mock_audit.get_audit_statistics.call_args
        assert stats_args.kwargs["channel_type"] == "slack"

    @patch("beeper_ui.routes.notifications.NotificationAuditService")
    def test_passes_date_range_filters(
        self, mock_audit_class: Any, user_get: _RoleClient
    ) -> None:
        """Passes date_from and date_to parameters."""
        mock_audit = mock_audit_class.return_value
        mock_audit.query_audit.return_value = []
        mock_audit.get_audit_statistics.return_value = {
            "total_notifications": 0,
            "false_page_count": 0,
            "false_page_rate": 0.0,
        }

        user_get.get(
            "/api/v1/notifications/audit?date_from=2026-03-01&date_to=2026-03-14"
        )

        call_args = mock_audit.query_audit.call_args
        assert call_args.kwargs["date_from"] == "2026-03-01"
        assert call_args.kwargs["date_to"] == "2026-03-14"

    @patch("beeper_ui.routes.notifications.NotificationAuditService")
    def test_passes_is_false_page_filter_true(
        self, mock_audit_class: Any, user_get: _RoleClient
    ) -> None:
        """Passes is_false_page=true as boolean."""
        mock_audit = mock_audit_class.return_value
        mock_audit.query_audit.return_value = []
        mock_audit.get_audit_statistics.return_value = {
            "total_notifications": 0,
            "false_page_count": 0,
            "false_page_rate": 0.0,
        }

        user_get.get("/api/v1/notifications/audit?is_false_page=true")

        call_args = mock_audit.query_audit.call_args
        assert call_args.kwargs["is_false_page"] is True

    @patch("beeper_ui.routes.notifications.NotificationAuditService")
    def test_passes_is_false_page_filter_false(
        self, mock_audit_class: Any, user_get: _RoleClient
    ) -> None:
        """Passes is_false_page=false as boolean."""
        mock_audit = mock_audit_class.return_value
        mock_audit.query_audit.return_value = []
        mock_audit.get_audit_statistics.return_value = {
            "total_notifications": 0,
            "false_page_count": 0,
            "false_page_rate": 0.0,
        }

        user_get.get("/api/v1/notifications/audit?is_false_page=false")

        call_args = mock_audit.query_audit.call_args
        assert call_args.kwargs["is_false_page"] is False

    @patch("beeper_ui.routes.notifications.NotificationAuditService")
    def test_passes_limit_and_offset(
        self, mock_audit_class: Any, user_get: _RoleClient
    ) -> None:
        """Passes limit and offset parameters."""
        mock_audit = mock_audit_class.return_value
        mock_audit.query_audit.return_value = []
        mock_audit.get_audit_statistics.return_value = {
            "total_notifications": 0,
            "false_page_count": 0,
            "false_page_rate": 0.0,
        }

        resp = user_get.get("/api/v1/notifications/audit?limit=25&offset=50")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["limit"] == 25
        assert data["offset"] == 50

    @patch("beeper_ui.routes.notifications.NotificationAuditService")
    def test_limit_capped_at_200(
        self, mock_audit_class: Any, user_get: _RoleClient
    ) -> None:
        """Limit is capped at 200."""
        mock_audit = mock_audit_class.return_value
        mock_audit.query_audit.return_value = []
        mock_audit.get_audit_statistics.return_value = {
            "total_notifications": 0,
            "false_page_count": 0,
            "false_page_rate": 0.0,
        }

        resp = user_get.get("/api/v1/notifications/audit?limit=500")

        data = resp.get_json()
        assert data["limit"] == 200

    @patch("beeper_ui.routes.notifications.NotificationAuditService")
    def test_invalid_limit_defaults_to_50(
        self, mock_audit_class: Any, user_get: _RoleClient
    ) -> None:
        """Invalid limit defaults to 50."""
        mock_audit = mock_audit_class.return_value
        mock_audit.query_audit.return_value = []
        mock_audit.get_audit_statistics.return_value = {
            "total_notifications": 0,
            "false_page_count": 0,
            "false_page_rate": 0.0,
        }

        resp = user_get.get("/api/v1/notifications/audit?limit=abc")

        data = resp.get_json()
        assert data["limit"] == 50

    @patch("beeper_ui.routes.notifications.NotificationAuditService")
    def test_no_filters_returns_all(
        self, mock_audit_class: Any, user_get: _RoleClient
    ) -> None:
        """No filters returns all records (within limit)."""
        mock_audit = mock_audit_class.return_value
        mock_audit.query_audit.return_value = []
        mock_audit.get_audit_statistics.return_value = {
            "total_notifications": 0,
            "false_page_count": 0,
            "false_page_rate": 0.0,
        }

        resp = user_get.get("/api/v1/notifications/audit")

        assert resp.status_code == 200
        call_args = mock_audit.query_audit.call_args
        assert call_args.kwargs["service"] is None
        assert call_args.kwargs["channel_type"] is None

    @patch("beeper_ui.routes.notifications.NotificationAuditService")
    def test_audit_query_error_returns_500(
        self, mock_audit_class: Any, user_get: _RoleClient
    ) -> None:
        """Returns 500 on unexpected error."""
        mock_audit = mock_audit_class.return_value
        mock_audit.query_audit.side_effect = RuntimeError("Unexpected")

        resp = user_get.get("/api/v1/notifications/audit")

        assert resp.status_code == 500
        data = resp.get_json()
        assert data["status"] == "error"

    @patch("beeper_ui.routes.notifications.NotificationAuditService")
    def test_audit_service_closed_after_query(
        self, mock_audit_class: Any, user_get: _RoleClient
    ) -> None:
        """Audit service is always closed after query."""
        mock_audit = mock_audit_class.return_value
        mock_audit.query_audit.return_value = []
        mock_audit.get_audit_statistics.return_value = {
            "total_notifications": 0,
            "false_page_count": 0,
            "false_page_rate": 0.0,
        }

        user_get.get("/api/v1/notifications/audit")

        mock_audit.close.assert_called_once()

    @patch("beeper_ui.routes.notifications.NotificationAuditService")
    def test_statistics_passed_to_response(
        self, mock_audit_class: Any, user_get: _RoleClient
    ) -> None:
        """Statistics from get_audit_statistics are included in response."""
        mock_audit = mock_audit_class.return_value
        mock_audit.query_audit.return_value = []
        mock_audit.get_audit_statistics.return_value = {
            "total_notifications": 42,
            "false_page_count": 7,
            "false_page_rate": 0.1667,
        }

        resp = user_get.get("/api/v1/notifications/audit")

        data = resp.get_json()
        assert data["statistics"]["total_notifications"] == 42
        assert data["statistics"]["false_page_rate"] == 0.1667


# --- False page flagging integration tests ---


class TestFalsePageFlaggingIntegration:
    """Tests that false pages are flagged during investigation resolution."""

    @respx.mock
    @patch("beeper_ui.routes.investigations.NotificationAuditService")
    def test_false_page_flagged_on_not_an_issue(
        self, mock_audit_class: Any, client: FlaskClient
    ) -> None:
        """Flags false pages when outcome is not_an_issue."""
        mock_audit = mock_audit_class.return_value
        respx.get("http://mock-operator:8080/api/v1/investigations/inv-001").mock(
            return_value=Response(200, json={
                "id": "inv-001", "status": "completed", "service": "payments",
                "severity": "low", "condition": "Alert", "started_at": "2026-03-07T10:00:00Z",
            })
        )
        respx.post("http://mock-operator:8080/api/v1/investigations/inv-001/resolve").mock(
            return_value=Response(200, json={"status": "not_an_issue", "message": "OK"})
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.save_resolution_feedback"
        ), patch(
            "beeper_ui.routes.investigations.InvestigationService.update_kb_with_resolution",
            return_value=False,
        ):
            response = client.post(
                "/investigations/inv-001/resolve",
                data={
                    "outcome": "not_an_issue",
                    "not_an_issue_reason": "false_positive",
                },
            )
            assert response.status_code == 200
            mock_audit.flag_false_pages.assert_called_once_with("inv-001", "false_positive")
            mock_audit.close.assert_called_once()

    @respx.mock
    @patch("beeper_ui.routes.investigations.NotificationAuditService")
    def test_false_page_flagged_on_incorrect_accuracy(
        self, mock_audit_class: Any, client: FlaskClient
    ) -> None:
        """Flags false pages when accuracy_rating is incorrect."""
        mock_audit = mock_audit_class.return_value
        respx.get("http://mock-operator:8080/api/v1/investigations/inv-002").mock(
            return_value=Response(200, json={
                "id": "inv-002", "status": "completed", "service": "api-gw",
                "severity": "high", "condition": "Error", "started_at": "2026-03-07T10:00:00Z",
            })
        )
        respx.post("http://mock-operator:8080/api/v1/investigations/inv-002/resolve").mock(
            return_value=Response(200, json={"status": "resolved", "message": "OK"})
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.save_resolution_feedback"
        ), patch(
            "beeper_ui.routes.investigations.InvestigationService.update_kb_with_resolution",
            return_value=False,
        ):
            response = client.post(
                "/investigations/inv-002/resolve",
                data={
                    "outcome": "resolved",
                    "accuracy_rating": "incorrect",
                },
            )
            assert response.status_code == 200
            mock_audit.flag_false_pages.assert_called_once_with("inv-002", "incorrect_accuracy")

    @respx.mock
    @patch("beeper_ui.routes.investigations.NotificationAuditService")
    def test_no_flagging_on_resolved_correct(
        self, mock_audit_class: Any, client: FlaskClient
    ) -> None:
        """Does not flag false pages when outcome is resolved and accuracy is correct."""
        respx.get("http://mock-operator:8080/api/v1/investigations/inv-003").mock(
            return_value=Response(200, json={
                "id": "inv-003", "status": "completed", "service": "api-gw",
                "severity": "medium", "condition": "Latency", "started_at": "2026-03-07T10:00:00Z",
            })
        )
        respx.post("http://mock-operator:8080/api/v1/investigations/inv-003/resolve").mock(
            return_value=Response(200, json={"status": "resolved", "message": "OK"})
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.save_resolution_feedback"
        ), patch(
            "beeper_ui.routes.investigations.InvestigationService.update_kb_with_resolution",
            return_value=True,
        ):
            response = client.post(
                "/investigations/inv-003/resolve",
                data={
                    "outcome": "resolved",
                    "accuracy_rating": "correct",
                },
            )
            assert response.status_code == 200
            mock_audit_class.assert_not_called()

    @respx.mock
    @patch("beeper_ui.routes.investigations.NotificationAuditService")
    def test_flagging_error_does_not_fail_resolution(
        self, mock_audit_class: Any, client: FlaskClient
    ) -> None:
        """False page flagging failure does not affect resolution response."""
        mock_audit = mock_audit_class.return_value
        mock_audit.flag_false_pages.side_effect = Exception("Qdrant down")
        respx.get("http://mock-operator:8080/api/v1/investigations/inv-004").mock(
            return_value=Response(200, json={
                "id": "inv-004", "status": "completed", "service": "payments",
                "severity": "low", "condition": "Alert", "started_at": "2026-03-07T10:00:00Z",
            })
        )
        respx.post("http://mock-operator:8080/api/v1/investigations/inv-004/resolve").mock(
            return_value=Response(200, json={"status": "not_an_issue", "message": "OK"})
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.save_resolution_feedback"
        ), patch(
            "beeper_ui.routes.investigations.InvestigationService.update_kb_with_resolution",
            return_value=False,
        ):
            response = client.post(
                "/investigations/inv-004/resolve",
                data={
                    "outcome": "not_an_issue",
                    "not_an_issue_reason": "transient",
                },
            )
            # Resolution should still succeed despite flagging error
            assert response.status_code == 200

    @respx.mock
    @patch("beeper_ui.routes.investigations.NotificationAuditService")
    def test_not_an_issue_with_expected_behavior_reason(
        self, mock_audit_class: Any, client: FlaskClient
    ) -> None:
        """Flags with expected_behavior reason."""
        mock_audit = mock_audit_class.return_value
        respx.get("http://mock-operator:8080/api/v1/investigations/inv-005").mock(
            return_value=Response(200, json={
                "id": "inv-005", "status": "completed", "service": "auth",
                "severity": "low", "condition": "Noise", "started_at": "2026-03-07T10:00:00Z",
            })
        )
        respx.post("http://mock-operator:8080/api/v1/investigations/inv-005/resolve").mock(
            return_value=Response(200, json={"status": "not_an_issue", "message": "OK"})
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.save_resolution_feedback"
        ), patch(
            "beeper_ui.routes.investigations.InvestigationService.update_kb_with_resolution",
            return_value=False,
        ):
            response = client.post(
                "/investigations/inv-005/resolve",
                data={
                    "outcome": "not_an_issue",
                    "not_an_issue_reason": "expected_behavior",
                },
            )
            assert response.status_code == 200
            mock_audit.flag_false_pages.assert_called_once_with("inv-005", "expected_behavior")

    @respx.mock
    @patch("beeper_ui.routes.investigations.NotificationAuditService")
    def test_no_flagging_on_escalated(
        self, mock_audit_class: Any, client: FlaskClient
    ) -> None:
        """Does not flag false pages on escalated outcome."""
        respx.get("http://mock-operator:8080/api/v1/investigations/inv-006").mock(
            return_value=Response(200, json={
                "id": "inv-006", "status": "completed", "service": "payments",
                "severity": "high", "condition": "Error", "started_at": "2026-03-07T10:00:00Z",
            })
        )
        respx.post("http://mock-operator:8080/api/v1/investigations/inv-006/resolve").mock(
            return_value=Response(200, json={"status": "escalated", "message": "OK"})
        )

        with patch(
            "beeper_ui.routes.investigations.InvestigationService.save_resolution_feedback"
        ), patch(
            "beeper_ui.routes.investigations.InvestigationService.update_kb_with_resolution",
            return_value=False,
        ):
            response = client.post(
                "/investigations/inv-006/resolve",
                data={
                    "outcome": "escalated",
                    "escalation_target": "team-lead",
                },
            )
            assert response.status_code == 200
            mock_audit_class.assert_not_called()
