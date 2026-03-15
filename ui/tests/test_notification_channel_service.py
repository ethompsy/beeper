"""Tests for NotificationChannelService."""

from unittest.mock import MagicMock

import httpx
import pytest

from beeper_ui.services.notification_channel_service import (
    NotificationChannelService,
    NotificationChannelServiceError,
)


class TestNotificationChannelServiceInit:
    """Test service initialization."""

    def test_init_strips_trailing_slash(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080/")
        assert svc.operator_url == "http://localhost:8080"

    def test_init_default_timeout(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080")
        assert svc.timeout == 5.0

    def test_init_custom_timeout(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080", timeout=10.0)
        assert svc.timeout == 10.0

    def test_client_property_creates_client(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080")
        client = svc.client
        assert isinstance(client, httpx.Client)
        svc.close()

    def test_client_property_reuses_client(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080")
        c1 = svc.client
        c2 = svc.client
        assert c1 is c2
        svc.close()

    def test_close_clears_client(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080")
        _ = svc.client
        svc.close()
        assert svc._client is None

    def test_close_noop_when_no_client(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080")
        svc.close()  # Should not raise


class TestListChannels:
    """Test list_channels method."""

    def test_list_channels_success(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080")
        channels = [
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
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = channels
        svc._client = MagicMock()
        svc._client.is_closed = False
        svc._client.get.return_value = mock_response

        result = svc.list_channels()
        assert len(result) == 2
        assert result[0]["name"] == "sre-slack"
        assert result[1]["condition"] == "error"
        svc._client.get.assert_called_once_with(
            "http://localhost:8080/api/v1/notifications/channels"
        )

    def test_list_channels_empty(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        svc._client = MagicMock()
        svc._client.is_closed = False
        svc._client.get.return_value = mock_response

        result = svc.list_channels()
        assert result == []

    def test_list_channels_non_list_response(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"channels": []}  # wrong format
        svc._client = MagicMock()
        svc._client.is_closed = False
        svc._client.get.return_value = mock_response

        result = svc.list_channels()
        assert result == []

    def test_list_channels_500_error(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080")
        mock_response = MagicMock()
        mock_response.status_code = 500
        svc._client = MagicMock()
        svc._client.is_closed = False
        svc._client.get.return_value = mock_response

        with pytest.raises(NotificationChannelServiceError) as exc_info:
            svc.list_channels()
        assert "HTTP 500" in str(exc_info.value)
        assert exc_info.value.retryable is True

    def test_list_channels_404_error(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080")
        mock_response = MagicMock()
        mock_response.status_code = 404
        svc._client = MagicMock()
        svc._client.is_closed = False
        svc._client.get.return_value = mock_response

        with pytest.raises(NotificationChannelServiceError) as exc_info:
            svc.list_channels()
        assert "HTTP 404" in str(exc_info.value)
        assert exc_info.value.retryable is False

    def test_list_channels_connection_error(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080")
        svc._client = MagicMock()
        svc._client.is_closed = False
        svc._client.get.side_effect = httpx.ConnectError("Connection refused")

        with pytest.raises(NotificationChannelServiceError) as exc_info:
            svc.list_channels()
        assert "Failed to connect" in str(exc_info.value)
        assert exc_info.value.retryable is True

    def test_list_channels_timeout_error(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080")
        svc._client = MagicMock()
        svc._client.is_closed = False
        svc._client.get.side_effect = httpx.ReadTimeout("Read timed out")

        with pytest.raises(NotificationChannelServiceError) as exc_info:
            svc.list_channels()
        assert exc_info.value.retryable is True


class TestSendTestNotification:
    """Test send_test_notification method."""

    def test_send_test_success(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"status": "delivered"}
        svc._client = MagicMock()
        svc._client.is_closed = False
        svc._client.post.return_value = mock_response

        result = svc.send_test_notification("sre-slack", "slack")
        assert result["success"] is True
        assert "sre-slack" in result["message"]

        # Verify the POST was called with correct structure
        call_args = svc._client.post.call_args
        assert "/api/v1/notifications/test" in call_args[0][0]
        body = call_args[1]["json"]
        assert body["entry"]["event_type"] == "test"
        assert body["entry"]["severity"] == "low"
        assert body["channel_config"]["channel_name"] == "sre-slack"
        assert body["channel_config"]["channel_type"] == "slack"

    def test_send_test_202_accepted(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080")
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"status": "queued"}
        svc._client = MagicMock()
        svc._client.is_closed = False
        svc._client.post.return_value = mock_response

        result = svc.send_test_notification("oncall-pd", "pagerduty")
        assert result["success"] is True

    def test_send_test_failure_response(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080")
        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"error": "Slack API error: invalid_token"}
        svc._client = MagicMock()
        svc._client.is_closed = False
        svc._client.post.return_value = mock_response

        result = svc.send_test_notification("sre-slack", "slack")
        assert result["success"] is False
        assert "invalid_token" in result["error"]

    def test_send_test_failure_non_json_response(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.headers = {"content-type": "text/html"}
        svc._client = MagicMock()
        svc._client.is_closed = False
        svc._client.post.return_value = mock_response

        result = svc.send_test_notification("sre-slack", "slack")
        assert result["success"] is False
        assert "HTTP 500" in result["error"]

    def test_send_test_connection_error(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080")
        svc._client = MagicMock()
        svc._client.is_closed = False
        svc._client.post.side_effect = httpx.ConnectError("Connection refused")

        with pytest.raises(NotificationChannelServiceError) as exc_info:
            svc.send_test_notification("sre-slack", "slack")
        assert "Failed to send test" in str(exc_info.value)
        assert exc_info.value.retryable is True

    def test_send_test_generates_unique_ids(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"status": "delivered"}
        svc._client = MagicMock()
        svc._client.is_closed = False
        svc._client.post.return_value = mock_response

        svc.send_test_notification("ch1", "slack")
        svc.send_test_notification("ch2", "slack")

        call1_body = svc._client.post.call_args_list[0][1]["json"]
        call2_body = svc._client.post.call_args_list[1][1]["json"]
        assert call1_body["entry"]["investigation_id"] != call2_body["entry"]["investigation_id"]

    def test_send_test_payload_structure(self) -> None:
        svc = NotificationChannelService(operator_url="http://localhost:8080")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"status": "delivered"}
        svc._client = MagicMock()
        svc._client.is_closed = False
        svc._client.post.return_value = mock_response

        svc.send_test_notification("webhook-alerts", "webhook")

        body = svc._client.post.call_args[1]["json"]
        entry = body["entry"]
        assert entry["investigation_id"].startswith("test-")
        assert entry["event_type"] == "test"
        assert entry["severity"] == "low"
        assert entry["service"] == "test-service"
        assert "title" in entry["payload"]
        assert "summary" in entry["payload"]
        assert "confidence" in entry["payload"]
        assert "evidence" in entry["payload"]


class TestNotificationChannelServiceError:
    """Test error class."""

    def test_default_retryable(self) -> None:
        err = NotificationChannelServiceError("test error")
        assert str(err) == "test error"
        assert err.retryable is True

    def test_non_retryable(self) -> None:
        err = NotificationChannelServiceError("bad config", retryable=False)
        assert err.retryable is False
