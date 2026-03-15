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


def _make_pagerduty_channel_config(**overrides: Any) -> dict[str, Any]:
    """Create a sample PagerDuty channel config."""
    base: dict[str, Any] = {
        "channel_type": "pagerduty",
        "config": {"routing_key": "test-routing-key-123", "base_url": "https://beeper.test"},
        "credentials_secret": "pagerduty-credentials",
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


def _make_email_channel_config(**overrides: Any) -> dict[str, Any]:
    """Create a sample email channel config."""
    base: dict[str, Any] = {
        "channel_type": "email",
        "config": {
            "smtp_host": "smtp.example.com",
            "recipients": "sre@example.com",
            "smtp_port": "587",
            "from_addr": "beeper@example.com",
            "base_url": "https://beeper.test",
        },
        "credentials_secret": "smtp-credentials",
    }
    base.update(overrides)
    return base


def _make_webhook_channel_config(**overrides: Any) -> dict[str, Any]:
    """Create a sample webhook channel config."""
    base: dict[str, Any] = {
        "channel_type": "webhook",
        "config": {
            "url": "https://hooks.example.com/notify",
            "base_url": "https://beeper.test",
        },
        "credentials_secret": "webhook-secret",
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

    @patch("beeper_ui.services.notification_service.PagerDutyNotifier")
    def test_dispatches_to_pagerduty(self, mock_notifier_class: MagicMock) -> None:
        mock_notifier = MagicMock()
        mock_notifier.trigger_incident.return_value = {
            "status": "success",
            "dedup_key": "inv-001",
        }
        mock_notifier.map_event_type.return_value = "trigger"
        mock_notifier_class.return_value = mock_notifier
        mock_notifier_class.map_event_type = MagicMock(return_value="trigger")

        svc = NotificationDeliveryService("http://operator:8080")
        result = svc.process_outbox_entry(
            _make_entry(),
            _make_pagerduty_channel_config(),
        )

        assert result["status"] == "delivered"
        assert result["pagerduty_dedup_key"] == "inv-001"

    @patch("beeper_ui.services.notification_service.EmailNotifier")
    def test_dispatches_to_email(self, mock_notifier_class: MagicMock) -> None:
        mock_notifier = MagicMock()
        mock_notifier.send_investigation_email.return_value = {
            "status": "sent",
            "message_id": "<beeper-abc@smtp.test>",
        }
        mock_notifier_class.return_value = mock_notifier

        svc = NotificationDeliveryService("http://operator:8080")
        result = svc.process_outbox_entry(
            _make_entry(severity="critical"),
            _make_email_channel_config(),
        )

        assert result["status"] == "delivered"
        assert "message_id" in result

    @patch("beeper_ui.services.notification_service.WebhookNotifier")
    def test_dispatches_to_webhook(self, mock_notifier_class: MagicMock) -> None:
        mock_notifier = MagicMock()
        mock_notifier.send_webhook.return_value = {
            "status": "sent",
            "status_code": 200,
        }
        mock_notifier_class.return_value = mock_notifier

        svc = NotificationDeliveryService("http://operator:8080")
        result = svc.process_outbox_entry(
            _make_entry(),
            _make_webhook_channel_config(),
        )

        assert result["status"] == "delivered"
        assert result["status_code"] == 200

    def test_unsupported_channel_type_returns_skipped(self) -> None:
        svc = NotificationDeliveryService("http://operator:8080")
        result = svc.process_outbox_entry(
            _make_entry(),
            {"channel_type": "sms", "config": {}, "credentials_secret": "sms-creds"},
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


class TestDeliverToPagerDuty:
    """Tests for deliver_to_pagerduty() PagerDuty-specific delivery."""

    @patch("beeper_ui.services.notification_service.PagerDutyNotifier")
    def test_successful_trigger(self, mock_notifier_class: MagicMock) -> None:
        mock_notifier = MagicMock()
        mock_notifier.trigger_incident.return_value = {
            "status": "success",
            "dedup_key": "inv-001",
        }
        mock_notifier_class.return_value = mock_notifier
        mock_notifier_class.map_event_type = MagicMock(return_value="trigger")

        svc = NotificationDeliveryService("http://operator:8080")
        result = svc.deliver_to_pagerduty(
            _make_entry(event_type="investigation_started"),
            _make_pagerduty_channel_config(),
        )

        assert result["status"] == "delivered"
        assert result["pagerduty_dedup_key"] == "inv-001"
        mock_notifier_class.assert_called_once_with("test-routing-key-123")
        mock_notifier.trigger_incident.assert_called_once()

    @patch("beeper_ui.services.notification_service.PagerDutyNotifier")
    def test_acknowledge_event(self, mock_notifier_class: MagicMock) -> None:
        mock_notifier = MagicMock()
        mock_notifier.acknowledge_incident.return_value = {
            "status": "success",
            "dedup_key": "inv-001",
        }
        mock_notifier_class.return_value = mock_notifier
        mock_notifier_class.map_event_type = MagicMock(return_value="acknowledge")

        svc = NotificationDeliveryService("http://operator:8080")
        result = svc.deliver_to_pagerduty(
            _make_entry(
                event_type="investigating",
                payload={"pagerduty_dedup_key": "inv-001"},
            ),
            _make_pagerduty_channel_config(),
        )

        assert result["status"] == "delivered"
        mock_notifier.acknowledge_incident.assert_called_once_with(dedup_key="inv-001")

    @patch("beeper_ui.services.notification_service.PagerDutyNotifier")
    def test_resolve_event(self, mock_notifier_class: MagicMock) -> None:
        mock_notifier = MagicMock()
        mock_notifier.resolve_incident.return_value = {
            "status": "success",
            "dedup_key": "inv-001",
        }
        mock_notifier_class.return_value = mock_notifier
        mock_notifier_class.map_event_type = MagicMock(return_value="resolve")

        svc = NotificationDeliveryService("http://operator:8080")
        result = svc.deliver_to_pagerduty(
            _make_entry(
                event_type="resolved",
                payload={"pagerduty_dedup_key": "inv-001"},
            ),
            _make_pagerduty_channel_config(),
        )

        assert result["status"] == "delivered"
        mock_notifier.resolve_incident.assert_called_once_with(dedup_key="inv-001")

    def test_raises_when_no_routing_key(self) -> None:
        svc = NotificationDeliveryService("http://operator:8080")
        config = _make_pagerduty_channel_config()
        config["config"]["routing_key"] = ""

        with pytest.raises(NotificationServiceError) as exc_info:
            svc.deliver_to_pagerduty(_make_entry(), config)

        assert not exc_info.value.retryable
        assert "routing_key" in str(exc_info.value)

    @patch("beeper_ui.services.notification_service.PagerDutyNotifier")
    def test_propagates_retryable_error(self, mock_notifier_class: MagicMock) -> None:
        from beeper_ui.notifications.pagerduty import PagerDutyNotifierError

        mock_notifier = MagicMock()
        mock_notifier.trigger_incident.side_effect = PagerDutyNotifierError(
            "Rate limited", retryable=True
        )
        mock_notifier_class.return_value = mock_notifier
        mock_notifier_class.map_event_type = MagicMock(return_value="trigger")

        svc = NotificationDeliveryService("http://operator:8080")

        with pytest.raises(NotificationServiceError) as exc_info:
            svc.deliver_to_pagerduty(
                _make_entry(),
                _make_pagerduty_channel_config(),
            )

        assert exc_info.value.retryable

    @patch("beeper_ui.services.notification_service.PagerDutyNotifier")
    def test_propagates_non_retryable_error(self, mock_notifier_class: MagicMock) -> None:
        from beeper_ui.notifications.pagerduty import PagerDutyNotifierError

        mock_notifier = MagicMock()
        mock_notifier.trigger_incident.side_effect = PagerDutyNotifierError(
            "Invalid routing key", retryable=False
        )
        mock_notifier_class.return_value = mock_notifier
        mock_notifier_class.map_event_type = MagicMock(return_value="trigger")

        svc = NotificationDeliveryService("http://operator:8080")

        with pytest.raises(NotificationServiceError) as exc_info:
            svc.deliver_to_pagerduty(
                _make_entry(),
                _make_pagerduty_channel_config(),
            )

        assert not exc_info.value.retryable

    @patch("beeper_ui.services.notification_service.PagerDutyNotifier")
    def test_uses_investigation_id_as_dedup_key_when_no_stored_key(
        self, mock_notifier_class: MagicMock
    ) -> None:
        mock_notifier = MagicMock()
        mock_notifier.acknowledge_incident.return_value = {
            "status": "success",
            "dedup_key": "inv-001",
        }
        mock_notifier_class.return_value = mock_notifier
        mock_notifier_class.map_event_type = MagicMock(return_value="acknowledge")

        svc = NotificationDeliveryService("http://operator:8080")
        svc.deliver_to_pagerduty(
            _make_entry(event_type="investigating", payload={}),
            _make_pagerduty_channel_config(),
        )

        # Should fall back to investigation_id when no pagerduty_dedup_key in payload
        mock_notifier.acknowledge_incident.assert_called_once_with(dedup_key="inv-001")

    @patch("beeper_ui.services.notification_service.PagerDutyNotifier")
    def test_string_payload_is_parsed(self, mock_notifier_class: MagicMock) -> None:
        mock_notifier = MagicMock()
        mock_notifier.trigger_incident.return_value = {
            "status": "success",
            "dedup_key": "inv-001",
        }
        mock_notifier_class.return_value = mock_notifier
        mock_notifier_class.map_event_type = MagicMock(return_value="trigger")

        svc = NotificationDeliveryService("http://operator:8080")
        result = svc.deliver_to_pagerduty(
            _make_entry(payload="plain text payload"),
            _make_pagerduty_channel_config(),
        )

        assert result["status"] == "delivered"


class TestDeliverToEmail:
    """Tests for deliver_to_email() email-specific delivery."""

    @patch("beeper_ui.services.notification_service.EmailNotifier")
    def test_successful_immediate_delivery(self, mock_notifier_class: MagicMock) -> None:
        mock_notifier = MagicMock()
        mock_notifier.send_investigation_email.return_value = {
            "status": "sent",
            "message_id": "<beeper-abc@smtp.test>",
        }
        mock_notifier_class.return_value = mock_notifier

        svc = NotificationDeliveryService("http://operator:8080")
        result = svc.deliver_to_email(
            _make_entry(severity="critical"),
            _make_email_channel_config(),
        )

        assert result["status"] == "delivered"
        assert result["message_id"] == "<beeper-abc@smtp.test>"
        mock_notifier.send_investigation_email.assert_called_once()

    @patch("beeper_ui.services.notification_service.EmailNotifier")
    def test_digest_mode_defers_non_critical(self, mock_notifier_class: MagicMock) -> None:
        config = _make_email_channel_config()
        config["config"]["mode"] = "digest"

        svc = NotificationDeliveryService("http://operator:8080")
        result = svc.deliver_to_email(
            _make_entry(severity="medium"),
            config,
        )

        assert result["status"] == "delivered"
        assert result["mode"] == "digest_deferred"
        mock_notifier_class.assert_not_called()

    @patch("beeper_ui.services.notification_service.EmailNotifier")
    def test_digest_mode_sends_critical_immediately(self, mock_notifier_class: MagicMock) -> None:
        mock_notifier = MagicMock()
        mock_notifier.send_investigation_email.return_value = {
            "status": "sent",
            "message_id": "<beeper-xyz@smtp.test>",
        }
        mock_notifier_class.return_value = mock_notifier

        config = _make_email_channel_config()
        config["config"]["mode"] = "digest"

        svc = NotificationDeliveryService("http://operator:8080")
        result = svc.deliver_to_email(
            _make_entry(severity="critical"),
            config,
        )

        assert result["status"] == "delivered"
        assert result["message_id"] == "<beeper-xyz@smtp.test>"
        mock_notifier.send_investigation_email.assert_called_once()

    def test_raises_when_no_smtp_host(self) -> None:
        svc = NotificationDeliveryService("http://operator:8080")
        config = _make_email_channel_config()
        config["config"]["smtp_host"] = ""

        with pytest.raises(NotificationServiceError) as exc_info:
            svc.deliver_to_email(_make_entry(), config)

        assert not exc_info.value.retryable
        assert "smtp_host" in str(exc_info.value)

    def test_raises_when_no_recipients(self) -> None:
        svc = NotificationDeliveryService("http://operator:8080")
        config = _make_email_channel_config()
        config["config"]["recipients"] = ""

        with pytest.raises(NotificationServiceError) as exc_info:
            svc.deliver_to_email(_make_entry(), config)

        assert not exc_info.value.retryable
        assert "recipients" in str(exc_info.value)

    @patch("beeper_ui.services.notification_service.EmailNotifier")
    def test_propagates_retryable_error(self, mock_notifier_class: MagicMock) -> None:
        from beeper_ui.notifications.email import EmailNotifierError

        mock_notifier = MagicMock()
        mock_notifier.send_investigation_email.side_effect = EmailNotifierError(
            "Connection lost", retryable=True
        )
        mock_notifier_class.return_value = mock_notifier

        svc = NotificationDeliveryService("http://operator:8080")

        with pytest.raises(NotificationServiceError) as exc_info:
            svc.deliver_to_email(
                _make_entry(severity="critical"),
                _make_email_channel_config(),
            )

        assert exc_info.value.retryable

    @patch("beeper_ui.services.notification_service.EmailNotifier")
    def test_propagates_non_retryable_error(self, mock_notifier_class: MagicMock) -> None:
        from beeper_ui.notifications.email import EmailNotifierError

        mock_notifier = MagicMock()
        mock_notifier.send_investigation_email.side_effect = EmailNotifierError(
            "Auth failed", retryable=False
        )
        mock_notifier_class.return_value = mock_notifier

        svc = NotificationDeliveryService("http://operator:8080")

        with pytest.raises(NotificationServiceError) as exc_info:
            svc.deliver_to_email(
                _make_entry(severity="critical"),
                _make_email_channel_config(),
            )

        assert not exc_info.value.retryable

    @patch("beeper_ui.services.notification_service.EmailNotifier")
    def test_string_payload_is_parsed(self, mock_notifier_class: MagicMock) -> None:
        mock_notifier = MagicMock()
        mock_notifier.send_investigation_email.return_value = {
            "status": "sent",
            "message_id": "<beeper@test>",
        }
        mock_notifier_class.return_value = mock_notifier

        svc = NotificationDeliveryService("http://operator:8080")
        result = svc.deliver_to_email(
            _make_entry(severity="critical", payload="plain text"),
            _make_email_channel_config(),
        )

        assert result["status"] == "delivered"


class TestDeliverToWebhook:
    """Tests for deliver_to_webhook() webhook-specific delivery."""

    @patch("beeper_ui.services.notification_service.WebhookNotifier")
    def test_successful_webhook(self, mock_notifier_class: MagicMock) -> None:
        mock_notifier = MagicMock()
        mock_notifier.send_webhook.return_value = {
            "status": "sent",
            "status_code": 200,
        }
        mock_notifier_class.return_value = mock_notifier

        svc = NotificationDeliveryService("http://operator:8080")
        result = svc.deliver_to_webhook(
            _make_entry(),
            _make_webhook_channel_config(),
        )

        assert result["status"] == "delivered"
        assert result["status_code"] == 200
        mock_notifier.send_webhook.assert_called_once()

    def test_raises_when_no_url(self) -> None:
        svc = NotificationDeliveryService("http://operator:8080")
        config = _make_webhook_channel_config()
        config["config"]["url"] = ""

        with pytest.raises(NotificationServiceError) as exc_info:
            svc.deliver_to_webhook(_make_entry(), config)

        assert not exc_info.value.retryable
        assert "URL" in str(exc_info.value)

    @patch("beeper_ui.services.notification_service.WebhookNotifier")
    def test_propagates_retryable_error(self, mock_notifier_class: MagicMock) -> None:
        from beeper_ui.notifications.webhook import WebhookNotifierError

        mock_notifier = MagicMock()
        mock_notifier.send_webhook.side_effect = WebhookNotifierError(
            "Server error", retryable=True
        )
        mock_notifier_class.return_value = mock_notifier

        svc = NotificationDeliveryService("http://operator:8080")

        with pytest.raises(NotificationServiceError) as exc_info:
            svc.deliver_to_webhook(
                _make_entry(),
                _make_webhook_channel_config(),
            )

        assert exc_info.value.retryable

    @patch("beeper_ui.services.notification_service.WebhookNotifier")
    def test_propagates_non_retryable_error(self, mock_notifier_class: MagicMock) -> None:
        from beeper_ui.notifications.webhook import WebhookNotifierError

        mock_notifier = MagicMock()
        mock_notifier.send_webhook.side_effect = WebhookNotifierError(
            "Bad request", retryable=False
        )
        mock_notifier_class.return_value = mock_notifier

        svc = NotificationDeliveryService("http://operator:8080")

        with pytest.raises(NotificationServiceError) as exc_info:
            svc.deliver_to_webhook(
                _make_entry(),
                _make_webhook_channel_config(),
            )

        assert not exc_info.value.retryable

    @patch("beeper_ui.services.notification_service.WebhookNotifier")
    def test_custom_headers_parsed_from_json(self, mock_notifier_class: MagicMock) -> None:
        mock_notifier = MagicMock()
        mock_notifier.send_webhook.return_value = {"status": "sent", "status_code": 200}
        mock_notifier_class.return_value = mock_notifier

        config = _make_webhook_channel_config()
        config["config"]["headers"] = '{"Authorization": "Bearer tok123"}'

        svc = NotificationDeliveryService("http://operator:8080")
        svc.deliver_to_webhook(_make_entry(), config)

        call_kwargs = mock_notifier_class.call_args
        assert call_kwargs.kwargs.get("headers", {}).get("Authorization") == "Bearer tok123"

    @patch("beeper_ui.services.notification_service.WebhookNotifier")
    def test_invalid_headers_json_ignored(self, mock_notifier_class: MagicMock) -> None:
        mock_notifier = MagicMock()
        mock_notifier.send_webhook.return_value = {"status": "sent", "status_code": 200}
        mock_notifier_class.return_value = mock_notifier

        config = _make_webhook_channel_config()
        config["config"]["headers"] = "not-valid-json"

        svc = NotificationDeliveryService("http://operator:8080")
        svc.deliver_to_webhook(_make_entry(), config)

        call_kwargs = mock_notifier_class.call_args
        assert call_kwargs.kwargs.get("headers", {}) == {}

    @patch("beeper_ui.services.notification_service.WebhookNotifier")
    def test_string_payload_is_parsed(self, mock_notifier_class: MagicMock) -> None:
        mock_notifier = MagicMock()
        mock_notifier.send_webhook.return_value = {"status": "sent", "status_code": 200}
        mock_notifier_class.return_value = mock_notifier

        svc = NotificationDeliveryService("http://operator:8080")
        result = svc.deliver_to_webhook(
            _make_entry(payload="plain text payload"),
            _make_webhook_channel_config(),
        )

        assert result["status"] == "delivered"
