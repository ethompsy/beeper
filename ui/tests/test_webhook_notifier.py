"""Tests for the webhook notifier module."""

import hashlib
import hmac
from unittest.mock import MagicMock, patch

import httpx
import pytest

from beeper_ui.notifications.webhook import (
    WebhookNotifier,
    WebhookNotifierError,
    _build_webhook_payload,
    _sign_payload,
)


class TestWebhookNotifierError:
    """Tests for WebhookNotifierError exception class."""

    def test_retryable_default_true(self) -> None:
        err = WebhookNotifierError("connection failed")
        assert err.retryable is True
        assert str(err) == "connection failed"

    def test_non_retryable(self) -> None:
        err = WebhookNotifierError("bad request", retryable=False)
        assert err.retryable is False

    def test_retryable_explicit(self) -> None:
        err = WebhookNotifierError("timeout", retryable=True)
        assert err.retryable is True


class TestWebhookNotifierInit:
    """Tests for WebhookNotifier constructor."""

    def test_minimal_init(self) -> None:
        notifier = WebhookNotifier(target_url="https://hooks.example.com/notify")
        assert notifier._target_url == "https://hooks.example.com/notify"
        assert notifier._custom_headers == {}
        assert notifier._secret == ""

    def test_full_init(self) -> None:
        notifier = WebhookNotifier(
            target_url="https://hooks.example.com/notify",
            headers={"Authorization": "Bearer token123"},
            secret="webhook-secret",
        )
        assert notifier._target_url == "https://hooks.example.com/notify"
        assert notifier._custom_headers == {"Authorization": "Bearer token123"}
        assert notifier._secret == "webhook-secret"


class TestSendWebhook:
    """Tests for send_webhook() method."""

    @patch("beeper_ui.notifications.webhook.httpx.Client")
    def test_successful_post(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

        notifier = WebhookNotifier(target_url="https://hooks.example.com/notify")
        result = notifier.send_webhook(
            investigation_id="inv-001",
            event_type="investigation_started",
            payload={"severity": "high", "service": "api-gw", "summary": "CPU spike"},
            base_url="https://beeper.test",
        )

        assert result["status"] == "sent"
        assert result["status_code"] == 200
        mock_client.post.assert_called_once()

    @patch("beeper_ui.notifications.webhook.httpx.Client")
    def test_successful_post_201(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

        notifier = WebhookNotifier(target_url="https://hooks.example.com/notify")
        result = notifier.send_webhook(
            investigation_id="inv-001",
            event_type="resolved",
            payload={"severity": "low"},
        )

        assert result["status"] == "sent"
        assert result["status_code"] == 201

    @patch("beeper_ui.notifications.webhook.httpx.Client")
    def test_custom_headers_included(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

        notifier = WebhookNotifier(
            target_url="https://hooks.example.com/notify",
            headers={"Authorization": "Bearer token123"},
        )
        notifier.send_webhook(
            investigation_id="inv-001",
            event_type="investigation_started",
            payload={"severity": "high"},
        )

        call_kwargs = mock_client.post.call_args
        headers = call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {}))
        assert headers.get("Authorization") == "Bearer token123"
        assert headers.get("Content-Type") == "application/json"

    @patch("beeper_ui.notifications.webhook.httpx.Client")
    def test_hmac_signature_included_when_secret_set(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

        notifier = WebhookNotifier(
            target_url="https://hooks.example.com/notify",
            secret="my-webhook-secret",
        )
        notifier.send_webhook(
            investigation_id="inv-001",
            event_type="investigation_started",
            payload={"severity": "high"},
        )

        call_kwargs = mock_client.post.call_args
        headers = call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {}))
        assert "X-Beeper-Signature" in headers
        assert headers["X-Beeper-Signature"].startswith("sha256=")

    @patch("beeper_ui.notifications.webhook.httpx.Client")
    def test_hmac_signature_not_included_when_no_secret(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

        notifier = WebhookNotifier(target_url="https://hooks.example.com/notify")
        notifier.send_webhook(
            investigation_id="inv-001",
            event_type="investigation_started",
            payload={"severity": "high"},
        )

        call_kwargs = mock_client.post.call_args
        headers = call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {}))
        assert "X-Beeper-Signature" not in headers

    @patch("beeper_ui.notifications.webhook.httpx.Client")
    def test_http_400_is_non_retryable(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

        notifier = WebhookNotifier(target_url="https://hooks.example.com/notify")

        with pytest.raises(WebhookNotifierError) as exc_info:
            notifier.send_webhook(
                investigation_id="inv-001",
                event_type="investigation_started",
                payload={"severity": "high"},
            )

        assert not exc_info.value.retryable

    @patch("beeper_ui.notifications.webhook.httpx.Client")
    def test_http_401_is_non_retryable(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

        notifier = WebhookNotifier(target_url="https://hooks.example.com/notify")

        with pytest.raises(WebhookNotifierError) as exc_info:
            notifier.send_webhook(
                investigation_id="inv-001",
                event_type="investigation_started",
                payload={"severity": "high"},
            )

        assert not exc_info.value.retryable

    @patch("beeper_ui.notifications.webhook.httpx.Client")
    def test_http_403_is_non_retryable(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

        notifier = WebhookNotifier(target_url="https://hooks.example.com/notify")

        with pytest.raises(WebhookNotifierError) as exc_info:
            notifier.send_webhook(
                investigation_id="inv-001",
                event_type="investigation_started",
                payload={"severity": "high"},
            )

        assert not exc_info.value.retryable

    @patch("beeper_ui.notifications.webhook.httpx.Client")
    def test_http_404_is_non_retryable(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

        notifier = WebhookNotifier(target_url="https://hooks.example.com/notify")

        with pytest.raises(WebhookNotifierError) as exc_info:
            notifier.send_webhook(
                investigation_id="inv-001",
                event_type="investigation_started",
                payload={"severity": "high"},
            )

        assert not exc_info.value.retryable

    @patch("beeper_ui.notifications.webhook.httpx.Client")
    def test_http_429_is_retryable(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate Limited"
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

        notifier = WebhookNotifier(target_url="https://hooks.example.com/notify")

        with pytest.raises(WebhookNotifierError) as exc_info:
            notifier.send_webhook(
                investigation_id="inv-001",
                event_type="investigation_started",
                payload={"severity": "high"},
            )

        assert exc_info.value.retryable

    @patch("beeper_ui.notifications.webhook.httpx.Client")
    def test_http_500_is_retryable(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

        notifier = WebhookNotifier(target_url="https://hooks.example.com/notify")

        with pytest.raises(WebhookNotifierError) as exc_info:
            notifier.send_webhook(
                investigation_id="inv-001",
                event_type="investigation_started",
                payload={"severity": "high"},
            )

        assert exc_info.value.retryable

    @patch("beeper_ui.notifications.webhook.httpx.Client")
    def test_connection_error_is_retryable(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

        notifier = WebhookNotifier(target_url="https://hooks.example.com/notify")

        with pytest.raises(WebhookNotifierError) as exc_info:
            notifier.send_webhook(
                investigation_id="inv-001",
                event_type="investigation_started",
                payload={"severity": "high"},
            )

        assert exc_info.value.retryable

    @patch("beeper_ui.notifications.webhook.httpx.Client")
    def test_timeout_is_retryable(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.TimeoutException("Read timeout")
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

        notifier = WebhookNotifier(target_url="https://hooks.example.com/notify")

        with pytest.raises(WebhookNotifierError) as exc_info:
            notifier.send_webhook(
                investigation_id="inv-001",
                event_type="investigation_started",
                payload={"severity": "high"},
            )

        assert exc_info.value.retryable


class TestBuildWebhookPayload:
    """Tests for _build_webhook_payload() helper."""

    def test_basic_payload_structure(self) -> None:
        payload = _build_webhook_payload(
            investigation_id="inv-001",
            event_type="investigation_started",
            payload={"severity": "high", "service": "api-gw", "summary": "CPU spike"},
            base_url="https://beeper.test",
        )

        assert payload["event"] == "beeper.notification"
        assert payload["version"] == "1"
        assert "timestamp" in payload
        assert payload["investigation_id"] == "inv-001"
        assert payload["event_type"] == "investigation_started"
        assert payload["severity"] == "high"
        assert payload["service"] == "api-gw"
        assert payload["summary"] == "CPU spike"
        assert payload["url"] == "https://beeper.test/investigations/inv-001"

    def test_evidence_included_when_present(self) -> None:
        payload = _build_webhook_payload(
            "inv-001",
            "investigation_started",
            {"evidence": ["Error log found"]},
        )
        assert payload["evidence"] == ["Error log found"]

    def test_evidence_excluded_when_empty(self) -> None:
        payload = _build_webhook_payload(
            "inv-001",
            "investigation_started",
            {"severity": "low"},
        )
        assert "evidence" not in payload

    def test_confidence_included_when_present(self) -> None:
        payload = _build_webhook_payload(
            "inv-001",
            "investigation_started",
            {"confidence": 0.85},
        )
        assert payload["confidence"] == 0.85

    def test_confidence_excluded_when_none(self) -> None:
        payload = _build_webhook_payload(
            "inv-001",
            "investigation_started",
            {"severity": "low"},
        )
        assert "confidence" not in payload

    def test_url_excluded_when_no_base_url(self) -> None:
        payload = _build_webhook_payload(
            "inv-001",
            "investigation_started",
            {"severity": "low"},
        )
        assert "url" not in payload

    def test_defaults_for_missing_fields(self) -> None:
        payload = _build_webhook_payload("inv-001", "resolved", {})
        assert payload["severity"] == "unknown"
        assert payload["service"] == "unknown"
        assert payload["summary"] == ""


class TestSignPayload:
    """Tests for _sign_payload() helper."""

    def test_produces_valid_hmac_sha256(self) -> None:
        body = '{"test": "data"}'
        secret = "my-secret"
        result = _sign_payload(body, secret)

        expected = hmac.new(
            secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        assert result == expected

    def test_different_secrets_produce_different_signatures(self) -> None:
        body = '{"test": "data"}'
        sig1 = _sign_payload(body, "secret1")
        sig2 = _sign_payload(body, "secret2")
        assert sig1 != sig2

    def test_different_bodies_produce_different_signatures(self) -> None:
        secret = "my-secret"
        sig1 = _sign_payload('{"a": 1}', secret)
        sig2 = _sign_payload('{"b": 2}', secret)
        assert sig1 != sig2
