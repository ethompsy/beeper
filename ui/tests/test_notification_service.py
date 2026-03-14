"""Tests for the notification delivery service."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from beeper_ui.services.notification_service import (
    NotificationDeliveryService,
    NotificationServiceError,
)


def _make_entry(**overrides: Any) -> dict[str, Any]:
    """Create a sample outbox entry for testing."""
    base: dict[str, Any] = {
        "investigation_id": "inv-001",
        "event_type": "investigation_started",
        "severity": "high",
        "service": "payment-service",
        "payload": {
            "summary": "CPU spike detected",
            "evidence": ["CPU at 95%"],
            "confidence": 0.87,
        },
        "status": "pending",
    }
    base.update(overrides)
    return base


def _make_slack_channel_config(**overrides: Any) -> dict[str, Any]:
    """Create a sample Slack channel config."""
    base: dict[str, Any] = {
        "channel_type": "slack",
        "config": {"channel": "#sre-alerts", "mention_users": ""},
        "credentials_secret": "slack-bot-token",
    }
    base.update(overrides)
    return base


class TestProcessOutboxEntry:
    """Tests for process_outbox_entry() dispatch."""

    @patch("beeper_ui.services.notification_service.SlackNotifier")
    def test_dispatches_to_slack(self, mock_notifier_class: MagicMock) -> None:
        mock_notifier = MagicMock()
        mock_notifier.send_investigation_message.return_value = {
            "ok": True,
            "channel": "C123",
            "ts": "123.456",
        }
        mock_notifier_class.return_value = mock_notifier

        svc = NotificationDeliveryService("http://operator:8080")
        result = svc.process_outbox_entry(
            _make_entry(),
            _make_slack_channel_config(),
            bot_token="xoxb-test",
        )

        assert result["status"] == "delivered"
        mock_notifier.send_investigation_message.assert_called_once()

    def test_unsupported_channel_type_returns_skipped(self) -> None:
        svc = NotificationDeliveryService("http://operator:8080")
        result = svc.process_outbox_entry(
            _make_entry(),
            {"channel_type": "pagerduty", "config": {}, "credentials_secret": "pd-token"},
        )
        assert result["status"] == "skipped"
        assert not result["retryable"]


class TestDeliverToSlack:
    """Tests for deliver_to_slack() Slack-specific delivery."""

    @patch("beeper_ui.services.notification_service.SlackNotifier")
    def test_successful_initial_message(self, mock_notifier_class: MagicMock) -> None:
        mock_notifier = MagicMock()
        mock_notifier.send_investigation_message.return_value = {
            "ok": True,
            "channel": "C123",
            "ts": "123.456",
        }
        mock_notifier_class.return_value = mock_notifier

        svc = NotificationDeliveryService("http://operator:8080")
        result = svc.deliver_to_slack(
            _make_entry(),
            _make_slack_channel_config(),
            bot_token="xoxb-test",
        )

        assert result["status"] == "delivered"
        assert result["ts"] == "123.456"

    @patch("beeper_ui.services.notification_service.SlackNotifier")
    def test_thread_update_when_thread_ts_present(
        self, mock_notifier_class: MagicMock
    ) -> None:
        mock_notifier = MagicMock()
        mock_notifier.send_thread_update.return_value = {
            "ok": True,
            "channel": "C123",
            "ts": "123.789",
        }
        mock_notifier_class.return_value = mock_notifier

        entry = _make_entry(
            event_type="new_evidence",
            payload={
                "slack_thread_ts": "123.456",
                "evidence": ["New log correlation"],
            },
        )

        svc = NotificationDeliveryService("http://operator:8080")
        result = svc.deliver_to_slack(
            entry,
            _make_slack_channel_config(),
            bot_token="xoxb-test",
        )

        assert result["status"] == "delivered"
        mock_notifier.send_thread_update.assert_called_once()
        call_kwargs = mock_notifier.send_thread_update.call_args
        assert call_kwargs.kwargs["thread_ts"] == "123.456"

    def test_raises_when_no_channel_configured(self) -> None:
        svc = NotificationDeliveryService("http://operator:8080")
        config = _make_slack_channel_config()
        config["config"]["channel"] = ""

        with pytest.raises(NotificationServiceError) as exc_info:
            svc.deliver_to_slack(_make_entry(), config, bot_token="xoxb-test")

        assert not exc_info.value.retryable

    def test_raises_when_no_bot_token(self) -> None:
        svc = NotificationDeliveryService("http://operator:8080")

        with pytest.raises(NotificationServiceError) as exc_info:
            svc.deliver_to_slack(
                _make_entry(),
                _make_slack_channel_config(),
                bot_token=None,
            )

        assert not exc_info.value.retryable
        assert "not available" in str(exc_info.value)

    def test_raises_with_error_detail_when_no_credential(self) -> None:
        config = _make_slack_channel_config()
        config["credentials_secret"] = ""
        svc = NotificationDeliveryService("http://operator:8080")

        with pytest.raises(NotificationServiceError) as exc_info:
            svc.deliver_to_slack(_make_entry(), config, bot_token=None)

        assert "no secret name" in str(exc_info.value)

    @patch("beeper_ui.services.notification_service.SlackNotifier")
    def test_propagates_retryable_error(self, mock_notifier_class: MagicMock) -> None:
        from beeper_ui.notifications.slack import SlackNotifierError

        mock_notifier = MagicMock()
        mock_notifier.send_investigation_message.side_effect = SlackNotifierError(
            "rate_limited", retryable=True
        )
        mock_notifier_class.return_value = mock_notifier

        svc = NotificationDeliveryService("http://operator:8080")

        with pytest.raises(NotificationServiceError) as exc_info:
            svc.deliver_to_slack(
                _make_entry(),
                _make_slack_channel_config(),
                bot_token="xoxb-test",
            )

        assert exc_info.value.retryable

    @patch("beeper_ui.services.notification_service.SlackNotifier")
    def test_propagates_non_retryable_error(self, mock_notifier_class: MagicMock) -> None:
        from beeper_ui.notifications.slack import SlackNotifierError

        mock_notifier = MagicMock()
        mock_notifier.send_investigation_message.side_effect = SlackNotifierError(
            "invalid_auth", retryable=False
        )
        mock_notifier_class.return_value = mock_notifier

        svc = NotificationDeliveryService("http://operator:8080")

        with pytest.raises(NotificationServiceError) as exc_info:
            svc.deliver_to_slack(
                _make_entry(),
                _make_slack_channel_config(),
                bot_token="xoxb-test",
            )

        assert not exc_info.value.retryable

    @patch("beeper_ui.services.notification_service.SlackNotifier")
    def test_parses_mention_users_from_config(self, mock_notifier_class: MagicMock) -> None:
        mock_notifier = MagicMock()
        mock_notifier.send_investigation_message.return_value = {
            "ok": True,
            "channel": "C123",
            "ts": "123.456",
        }
        mock_notifier_class.return_value = mock_notifier

        config = _make_slack_channel_config()
        config["config"]["mention_users"] = "U111,U222"

        svc = NotificationDeliveryService("http://operator:8080")
        svc.deliver_to_slack(_make_entry(), config, bot_token="xoxb-test")

        call_kwargs = mock_notifier.send_investigation_message.call_args
        assert call_kwargs.kwargs["mention_users"] == ["U111", "U222"]

    @patch("beeper_ui.services.notification_service.SlackNotifier")
    def test_mention_users_true_treated_as_no_mentions(
        self, mock_notifier_class: MagicMock
    ) -> None:
        mock_notifier = MagicMock()
        mock_notifier.send_investigation_message.return_value = {
            "ok": True,
            "channel": "C123",
            "ts": "123.456",
        }
        mock_notifier_class.return_value = mock_notifier

        config = _make_slack_channel_config()
        config["config"]["mention_users"] = "true"

        svc = NotificationDeliveryService("http://operator:8080")
        svc.deliver_to_slack(_make_entry(), config, bot_token="xoxb-test")

        call_kwargs = mock_notifier.send_investigation_message.call_args
        assert call_kwargs.kwargs["mention_users"] is None

    @patch("beeper_ui.services.notification_service.SlackNotifier")
    def test_string_payload_is_parsed(self, mock_notifier_class: MagicMock) -> None:
        """Test that a string payload is handled gracefully."""
        mock_notifier = MagicMock()
        mock_notifier.send_investigation_message.return_value = {
            "ok": True,
            "channel": "C123",
            "ts": "123.456",
        }
        mock_notifier_class.return_value = mock_notifier

        entry = _make_entry(payload="plain text payload")

        svc = NotificationDeliveryService("http://operator:8080")
        result = svc.deliver_to_slack(
            entry, _make_slack_channel_config(), bot_token="xoxb-test"
        )

        assert result["status"] == "delivered"


class TestFetchCredential:
    """Tests for _fetch_credential() helper."""

    @patch("beeper_ui.services.notification_service.httpx.Client")
    def test_returns_empty_string_on_missing_secret_name(
        self, mock_client_class: MagicMock
    ) -> None:
        svc = NotificationDeliveryService("http://operator:8080")
        value, error = svc._fetch_credential("", "bot_token")
        assert value == ""
        assert "no secret name" in error

    def test_returns_empty_string_on_http_error(self) -> None:
        svc = NotificationDeliveryService("http://nonexistent-host:9999", timeout=0.1)
        value, error = svc._fetch_credential("my-secret", "bot_token")
        assert value == ""
        assert "operator API error" in error
