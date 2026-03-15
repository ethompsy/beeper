"""Webhook channel integration for Beeper notifications.

Sends investigation notification payloads to external systems via HTTP POST.
Supports custom headers, HMAC-SHA256 payload signing, and RFC 7807 error
format on failures.

Implements FR13: Webhook triggers to external systems (CD pipelines, Jira, status pages).
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# HTTP status codes that indicate non-retryable errors
_NON_RETRYABLE_STATUS_CODES = frozenset({400, 401, 403, 404, 405, 422})


class WebhookNotifierError(Exception):
    """Error sending webhook notification."""

    def __init__(self, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class WebhookNotifier:
    """Sends webhook notifications for Beeper investigations.

    POSTs investigation payloads as JSON to configured target URLs.
    Supports HMAC-SHA256 payload signing for webhook authenticity verification.
    Uses httpx (existing dependency) — no additional dependencies required.
    """

    def __init__(
        self,
        target_url: str,
        headers: dict[str, str] | None = None,
        secret: str = "",
    ) -> None:
        """Initialize the webhook notifier.

        Args:
            target_url: The webhook target URL to POST to.
            headers: Optional custom headers to include in requests.
            secret: Optional secret for HMAC-SHA256 payload signing.
        """
        self._target_url = target_url
        self._custom_headers = headers or {}
        self._secret = secret

    def send_webhook(
        self,
        investigation_id: str,
        event_type: str,
        payload: dict[str, Any],
        base_url: str = "",
    ) -> dict[str, Any]:
        """Send a webhook notification with investigation payload.

        Args:
            investigation_id: Beeper investigation ID.
            event_type: Beeper event type (e.g., investigation_started, resolved).
            payload: Outbox entry payload with investigation details.
            base_url: Base URL for Beeper UI links.

        Returns:
            Dict with 'status' and 'status_code'.

        Raises:
            WebhookNotifierError: If the HTTP call fails.
        """
        webhook_payload = _build_webhook_payload(
            investigation_id, event_type, payload, base_url
        )
        body = json.dumps(webhook_payload, default=str)

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": "Beeper-Webhook/1.0",
        }
        headers.update(self._custom_headers)

        if self._secret:
            signature = _sign_payload(body, self._secret)
            headers["X-Beeper-Signature"] = f"sha256={signature}"

        try:
            with httpx.Client(timeout=httpx.Timeout(10.0, read=30.0)) as client:
                response = client.post(
                    self._target_url,
                    content=body,
                    headers=headers,
                )

            if 200 <= response.status_code < 300:
                logger.info(
                    "Webhook sent: url=%s investigation=%s status=%d",
                    self._target_url,
                    investigation_id,
                    response.status_code,
                )
                return {
                    "status": "sent",
                    "status_code": response.status_code,
                }

            # Rate limited — retryable
            if response.status_code == 429:
                error_msg = f"Webhook rate limited: HTTP 429 from {self._target_url}"
                logger.warning(error_msg)
                raise WebhookNotifierError(error_msg, retryable=True)

            # Non-retryable client errors
            retryable = response.status_code not in _NON_RETRYABLE_STATUS_CODES
            error_body = response.text[:200] if response.text else ""
            error_msg = (
                f"Webhook delivery failed: HTTP {response.status_code} "
                f"from {self._target_url} — {error_body}"
            )
            logger.error(
                "Webhook error: url=%s status=%d retryable=%s body=%s",
                self._target_url,
                response.status_code,
                retryable,
                error_body,
            )
            raise WebhookNotifierError(error_msg, retryable=retryable)

        except httpx.ConnectError as e:
            logger.error("Webhook connection error: %s → %s", self._target_url, e)
            raise WebhookNotifierError(
                f"Webhook connection error: {e}", retryable=True
            ) from e
        except httpx.TimeoutException as e:
            logger.error("Webhook timeout: %s → %s", self._target_url, e)
            raise WebhookNotifierError(
                f"Webhook timeout: {e}", retryable=True
            ) from e
        except httpx.HTTPError as e:
            logger.error("Webhook HTTP error: %s → %s", self._target_url, e)
            raise WebhookNotifierError(
                f"Webhook error: {e}", retryable=True
            ) from e


def _build_webhook_payload(
    investigation_id: str,
    event_type: str,
    payload: dict[str, Any],
    base_url: str = "",
) -> dict[str, Any]:
    """Build the standardized webhook JSON payload.

    Args:
        investigation_id: Beeper investigation ID.
        event_type: Beeper event type.
        payload: Outbox entry payload with investigation details.
        base_url: Base URL for Beeper UI links.

    Returns:
        Standardized webhook payload dict.
    """
    severity = payload.get("severity", "unknown")
    service = payload.get("service", "unknown")
    summary = payload.get("summary", "")
    evidence = payload.get("evidence", [])
    confidence = payload.get("confidence")

    webhook_body: dict[str, Any] = {
        "event": "beeper.notification",
        "version": "1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "investigation_id": investigation_id,
        "event_type": event_type,
        "severity": severity,
        "service": service,
        "summary": summary,
    }

    if evidence:
        webhook_body["evidence"] = evidence
    if confidence is not None:
        webhook_body["confidence"] = confidence
    if base_url:
        webhook_body["url"] = f"{base_url}/investigations/{investigation_id}"

    return webhook_body


def _sign_payload(body: str, secret: str) -> str:
    """Compute HMAC-SHA256 signature for webhook payload.

    Args:
        body: The JSON request body string.
        secret: The webhook secret key.

    Returns:
        Hex digest of the HMAC-SHA256 signature.
    """
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
