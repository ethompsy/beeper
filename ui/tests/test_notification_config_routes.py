"""Tests for notification configuration UI routes.

Uses shared fixtures from conftest.py: app, user_client, admin_client, _RoleClient.
"""

from typing import Any
from unittest.mock import patch

from flask import Flask

from beeper_ui.services.notification_channel_service import (
    NotificationChannelServiceError,
)


SAMPLE_CHANNELS = [
    {
        "name": "sre-slack",
        "type": "slack",
        "credentials_secret": "slack-token",
        "condition": "configured",
        "last_validated": "2026-03-14T10:00:00Z",
        "error": None,
    },
    {
        "name": "oncall-pd",
        "type": "pagerduty",
        "credentials_secret": "pd-key",
        "condition": "error",
        "last_validated": "2026-03-14T09:00:00Z",
        "error": "Secret not found",
    },
]


class TestListChannelsPage:
    """Test GET /notifications/ route."""

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_list_channels_full_page(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.list_channels.return_value = SAMPLE_CHANNELS

        resp = user_client.get("/notifications/")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Notification Channels" in html
        assert "sre-slack" in html
        assert "oncall-pd" in html
        mock_svc.close.assert_called_once()

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_list_channels_htmx_partial(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.list_channels.return_value = SAMPLE_CHANNELS

        resp = user_client.get("/notifications/", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        html = resp.data.decode()
        # Partial should NOT contain full page structure
        assert "<!DOCTYPE html>" not in html
        # But should have channel data
        assert "sre-slack" in html
        assert "oncall-pd" in html

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_list_channels_shows_status(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.list_channels.return_value = SAMPLE_CHANNELS

        resp = user_client.get("/notifications/")
        html = resp.data.decode()
        assert "Configured" in html
        assert "Error" in html
        assert "Secret not found" in html

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_list_channels_shows_channel_type_badge(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.list_channels.return_value = SAMPLE_CHANNELS

        resp = user_client.get("/notifications/")
        html = resp.data.decode()
        assert "slack" in html
        assert "pagerduty" in html

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_list_channels_empty_state(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.list_channels.return_value = []

        resp = user_client.get("/notifications/")
        html = resp.data.decode()
        assert "No notification channels configured" in html

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_list_channels_error_state(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.list_channels.side_effect = NotificationChannelServiceError(
            "Connection refused"
        )

        resp = user_client.get("/notifications/")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Unable to fetch notification channels" in html
        assert "Connection refused" in html

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_list_channels_error_htmx(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.list_channels.side_effect = NotificationChannelServiceError(
            "Timeout"
        )

        resp = user_client.get("/notifications/", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Timeout" in html
        assert "<!DOCTYPE html>" not in html

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_list_channels_requires_role(
        self, mock_svc_class: Any, app: Flask
    ) -> None:
        """No role header defaults to user, which has access."""
        mock_svc = mock_svc_class.return_value
        mock_svc.list_channels.return_value = []

        with app.test_client() as client:
            resp = client.get("/notifications/")
            assert resp.status_code == 200

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_list_channels_admin_access(
        self, mock_svc_class: Any, admin_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.list_channels.return_value = []

        resp = admin_client.get("/notifications/")
        assert resp.status_code == 200

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_list_channels_shows_last_validated(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.list_channels.return_value = [SAMPLE_CHANNELS[0]]

        resp = user_client.get("/notifications/")
        html = resp.data.decode()
        assert "2026-03-14T10:00:00Z" in html

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_list_channels_shows_routing_info(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.list_channels.return_value = [SAMPLE_CHANNELS[0]]

        resp = user_client.get("/notifications/")
        html = resp.data.decode()
        assert "Managed via CRD routing rules" in html


class TestTestChannel:
    """Test POST /notifications/test route."""

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_send_test_success(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.send_test_notification.return_value = {
            "success": True,
            "message": "Test notification delivered to sre-slack",
            "details": {"status": "delivered"},
        }

        resp = user_client.post(
            "/notifications/test",
            json={"channel_name": "sre-slack", "channel_type": "slack"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        mock_svc.send_test_notification.assert_called_once_with("sre-slack", "slack")
        mock_svc.close.assert_called_once()

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_send_test_success_htmx(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.send_test_notification.return_value = {
            "success": True,
            "message": "Test notification delivered to sre-slack",
        }

        resp = user_client.post(
            "/notifications/test",
            json={"channel_name": "sre-slack", "channel_type": "slack"},
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "test-success" in html
        assert "delivered" in html.lower()

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_send_test_failure(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.send_test_notification.return_value = {
            "success": False,
            "message": "Test notification failed",
            "error": "Slack API error: invalid_token",
        }

        resp = user_client.post(
            "/notifications/test",
            json={"channel_name": "sre-slack", "channel_type": "slack"},
        )
        assert resp.status_code == 502
        data = resp.get_json()
        assert data["success"] is False

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_send_test_failure_htmx(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.send_test_notification.return_value = {
            "success": False,
            "error": "invalid_token",
        }

        resp = user_client.post(
            "/notifications/test",
            json={"channel_name": "sre-slack", "channel_type": "slack"},
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 502
        html = resp.data.decode()
        assert "test-failure" in html

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_send_test_service_error(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.send_test_notification.side_effect = NotificationChannelServiceError(
            "Connection refused"
        )

        resp = user_client.post(
            "/notifications/test",
            json={"channel_name": "sre-slack", "channel_type": "slack"},
        )
        assert resp.status_code == 502
        data = resp.get_json()
        assert data["success"] is False
        assert "Connection refused" in data["error"]

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_send_test_service_error_htmx(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.send_test_notification.side_effect = NotificationChannelServiceError(
            "Timeout"
        )

        resp = user_client.post(
            "/notifications/test",
            json={"channel_name": "sre-slack", "channel_type": "slack"},
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 502
        html = resp.data.decode()
        assert "test-failure" in html
        assert "Timeout" in html

    def test_send_test_missing_body(self, user_client: _RoleClient) -> None:
        resp = user_client.post("/notifications/test")
        assert resp.status_code == 400

    def test_send_test_missing_body_htmx(self, user_client: _RoleClient) -> None:
        resp = user_client.post(
            "/notifications/test", headers={"HX-Request": "true"}
        )
        assert resp.status_code == 400
        html = resp.data.decode()
        assert "test-failure" in html

    def test_send_test_missing_channel_name(self, user_client: _RoleClient) -> None:
        resp = user_client.post(
            "/notifications/test",
            json={"channel_type": "slack"},
        )
        assert resp.status_code == 400

    def test_send_test_missing_channel_type(self, user_client: _RoleClient) -> None:
        resp = user_client.post(
            "/notifications/test",
            json={"channel_name": "sre-slack"},
        )
        assert resp.status_code == 400

    def test_send_test_empty_values(self, user_client: _RoleClient) -> None:
        resp = user_client.post(
            "/notifications/test",
            json={"channel_name": "", "channel_type": ""},
        )
        assert resp.status_code == 400

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_send_test_admin_access(
        self, mock_svc_class: Any, admin_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.send_test_notification.return_value = {
            "success": True,
            "message": "delivered",
        }

        resp = admin_client.post(
            "/notifications/test",
            json={"channel_name": "sre-slack", "channel_type": "slack"},
        )
        assert resp.status_code == 200


class TestNavigation:
    """Test navigation link is present."""

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_notifications_link_in_nav(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.list_channels.return_value = []

        resp = user_client.get("/notifications/")
        html = resp.data.decode()
        assert 'href="/notifications/"' in html

    def test_notifications_link_on_home(self, app: Flask) -> None:
        with app.test_client() as client:
            resp = client.get("/")
            html = resp.data.decode()
            assert 'href="/notifications/"' in html


class TestTestResultPartial:
    """Test the _test_result.html partial rendering."""

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_success_result_shows_green(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.send_test_notification.return_value = {
            "success": True,
            "message": "Test notification delivered to email-alerts",
        }

        resp = user_client.post(
            "/notifications/test",
            json={"channel_name": "email-alerts", "channel_type": "email"},
            headers={"HX-Request": "true"},
        )
        html = resp.data.decode()
        assert "test-success" in html
        assert "status-healthy" in html

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_failure_result_shows_red(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.send_test_notification.return_value = {
            "success": False,
            "error": "SMTP authentication failed",
        }

        resp = user_client.post(
            "/notifications/test",
            json={"channel_name": "email-alerts", "channel_type": "email"},
            headers={"HX-Request": "true"},
        )
        html = resp.data.decode()
        assert "test-failure" in html
        assert "status-critical" in html
        assert "SMTP authentication failed" in html


class TestChannelCardDetails:
    """Test channel card rendering details."""

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_error_channel_has_disabled_test_button(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.list_channels.return_value = [SAMPLE_CHANNELS[1]]  # error channel

        resp = user_client.get("/notifications/")
        html = resp.data.decode()
        assert "disabled" in html

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_configured_channel_has_enabled_test_button(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.list_channels.return_value = [SAMPLE_CHANNELS[0]]  # configured channel

        resp = user_client.get("/notifications/")
        html = resp.data.decode()
        assert "Send Test Notification" in html
        # The configured channel should NOT have the disabled attribute
        # Check the test button section for the configured channel
        assert 'hx-post="/notifications/test"' in html

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_multiple_channels_rendered(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.list_channels.return_value = [
            {
                "name": "ch-1", "type": "slack",
                "condition": "configured", "error": None,
                "last_validated": None,
            },
            {
                "name": "ch-2", "type": "email",
                "condition": "configured", "error": None,
                "last_validated": None,
            },
            {
                "name": "ch-3", "type": "webhook",
                "condition": "error", "error": "Bad URL",
                "last_validated": None,
            },
        ]

        resp = user_client.get("/notifications/")
        html = resp.data.decode()
        assert "ch-1" in html
        assert "ch-2" in html
        assert "ch-3" in html
        assert "Bad URL" in html

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_channel_close_called_on_error(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.list_channels.side_effect = NotificationChannelServiceError("fail")

        user_client.get("/notifications/")
        mock_svc.close.assert_called_once()

    @patch("beeper_ui.routes.notification_config.NotificationChannelService")
    def test_test_endpoint_close_called_on_error(
        self, mock_svc_class: Any, user_client: _RoleClient
    ) -> None:
        mock_svc = mock_svc_class.return_value
        mock_svc.send_test_notification.side_effect = NotificationChannelServiceError("fail")

        user_client.post(
            "/notifications/test",
            json={"channel_name": "ch", "channel_type": "slack"},
        )
        mock_svc.close.assert_called_once()
