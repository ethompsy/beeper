"""Tests for notification delivery API routes."""

from typing import Any
from unittest.mock import patch

import pytest
from flask import Flask
from flask.testing import FlaskClient


class _RoleClient:
    """Wrapper that injects X-Beeper-Role header on every request."""

    def __init__(self, client: FlaskClient, role: str) -> None:
        self._client = client
        self._role = role

    def post(self, *args: Any, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["X-Beeper-Role"] = self._role
        return self._client.post(*args, headers=headers, **kwargs)


@pytest.fixture
def user_post(app: Flask) -> _RoleClient:
    """Create test client with user role for POST requests."""
    with app.test_client() as test_client:
        yield _RoleClient(test_client, "user")


class TestDeliverNotification:
    """Tests for POST /api/v1/notifications/deliver endpoint."""

    def test_missing_body_returns_400(self, user_post: _RoleClient) -> None:
        resp = user_post.post(
            "/api/v1/notifications/deliver",
            content_type="application/json",
            data="",
        )
        assert resp.status_code == 400

    def test_missing_entry_returns_400(self, user_post: _RoleClient) -> None:
        resp = user_post.post(
            "/api/v1/notifications/deliver",
            json={"channel_config": {"channel_type": "slack"}},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "entry is required"

    def test_missing_channel_config_returns_400(self, user_post: _RoleClient) -> None:
        resp = user_post.post(
            "/api/v1/notifications/deliver",
            json={"entry": {"investigation_id": "inv-001"}},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "channel_config is required"

    def test_missing_investigation_id_returns_400(self, user_post: _RoleClient) -> None:
        resp = user_post.post(
            "/api/v1/notifications/deliver",
            json={
                "entry": {"event_type": "test"},
                "channel_config": {"channel_type": "slack"},
            },
        )
        assert resp.status_code == 400

    @patch(
        "beeper_ui.routes.notifications.NotificationDeliveryService"
    )
    def test_successful_delivery_returns_200(
        self, mock_svc_class: Any, user_post: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.process_outbox_entry.return_value = {
            "status": "delivered",
            "channel": "C123",
            "ts": "123.456",
        }

        resp = user_post.post(
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
                    "config": {"channel": "#sre-alerts"},
                    "credentials_secret": "slack-bot-token",
                },
                "bot_token": "xoxb-test",
            },
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "delivered"

    @patch(
        "beeper_ui.routes.notifications.NotificationDeliveryService"
    )
    def test_skipped_delivery_returns_202(
        self, mock_svc_class: Any, user_post: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.process_outbox_entry.return_value = {
            "status": "skipped",
            "error": "Channel type not implemented",
            "retryable": False,
        }

        resp = user_post.post(
            "/api/v1/notifications/deliver",
            json={
                "entry": {
                    "investigation_id": "inv-001",
                    "event_type": "test",
                    "payload": {},
                },
                "channel_config": {
                    "channel_type": "pagerduty",
                    "config": {},
                    "credentials_secret": "",
                },
            },
        )

        assert resp.status_code == 202

    @patch(
        "beeper_ui.routes.notifications.NotificationDeliveryService"
    )
    def test_retryable_failure_returns_502(
        self, mock_svc_class: Any, user_post: _RoleClient
    ) -> None:
        from beeper_ui.services.notification_service import NotificationServiceError

        mock_svc = mock_svc_class.return_value
        mock_svc.process_outbox_entry.side_effect = NotificationServiceError(
            "rate_limited", retryable=True
        )

        resp = user_post.post(
            "/api/v1/notifications/deliver",
            json={
                "entry": {"investigation_id": "inv-001", "payload": {}},
                "channel_config": {"channel_type": "slack", "config": {"channel": "#test"}},
            },
        )

        assert resp.status_code == 502
        data = resp.get_json()
        assert data["retryable"] is True

    @patch(
        "beeper_ui.routes.notifications.NotificationDeliveryService"
    )
    def test_non_retryable_failure_returns_422(
        self, mock_svc_class: Any, user_post: _RoleClient
    ) -> None:
        from beeper_ui.services.notification_service import NotificationServiceError

        mock_svc = mock_svc_class.return_value
        mock_svc.process_outbox_entry.side_effect = NotificationServiceError(
            "invalid_auth", retryable=False
        )

        resp = user_post.post(
            "/api/v1/notifications/deliver",
            json={
                "entry": {"investigation_id": "inv-001", "payload": {}},
                "channel_config": {"channel_type": "slack", "config": {"channel": "#test"}},
            },
        )

        assert resp.status_code == 422
        data = resp.get_json()
        assert data["retryable"] is False

    def test_no_role_header_defaults_to_user_and_allows(self, app: Flask) -> None:
        """Verify permission middleware defaults to user role (allows access)."""
        with app.test_client() as tc:
            resp = tc.post(
                "/api/v1/notifications/deliver",
                json={
                    "entry": {"investigation_id": "inv-001", "payload": {}},
                    "channel_config": {"channel_type": "slack", "config": {}},
                },
            )
            # Should not be 403 — default role is "user" which satisfies @require_role("user")
            assert resp.status_code != 403
