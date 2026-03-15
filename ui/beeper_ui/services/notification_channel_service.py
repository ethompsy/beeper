"""Notification channel configuration service.

Fetches notification channel configuration from the operator API
and supports sending test notifications through configured channels.
"""

import json
import logging
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class NotificationChannelServiceError(Exception):
    """Error in notification channel service."""

    def __init__(self, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class NotificationChannelService:
    """Fetches notification channel data from the operator and sends test notifications."""

    def __init__(self, operator_url: str, timeout: float = 5.0) -> None:
        self.operator_url = operator_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            self._client.close()
            self._client = None

    def list_channels(self) -> list[dict[str, Any]]:
        """Fetch all configured NotificationChannel CRDs from the operator.

        Returns:
            List of channel dicts with name, type, condition, last_validated, error.

        Raises:
            NotificationChannelServiceError: If the operator API call fails.
        """
        try:
            response = self.client.get(
                f"{self.operator_url}/api/v1/notifications/channels"
            )
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    return data
                return []
            raise NotificationChannelServiceError(
                f"Operator returned HTTP {response.status_code}",
                retryable=response.status_code >= 500,
            )
        except httpx.HTTPError as e:
            raise NotificationChannelServiceError(
                f"Failed to connect to operator: {e}", retryable=True
            ) from e

    def send_test_notification(
        self, channel_name: str, channel_type: str
    ) -> dict[str, Any]:
        """Send a test notification through a specific channel.

        Constructs sample investigation data and delivers it through the
        UI's delivery endpoint via the operator outbox flow.

        Args:
            channel_name: Name of the notification channel to test.
            channel_type: Type of channel (slack, pagerduty, email, webhook).

        Returns:
            Dict with success status and message/error details.

        Raises:
            NotificationChannelServiceError: If the test delivery fails.
        """
        test_id = f"test-{uuid.uuid4().hex[:8]}"
        entry = {
            "investigation_id": test_id,
            "event_type": "test",
            "severity": "low",
            "service": "test-service",
            "payload": {
                "title": "Test Notification from Beeper",
                "summary": "This is a test notification to verify channel configuration.",
                "confidence": 0.95,
                "evidence": [
                    {"finding": "Channel connectivity test", "source": "beeper-ui"}
                ],
            },
        }
        channel_config = {
            "channel_type": channel_type,
            "channel_name": channel_name,
        }

        try:
            response = self.client.post(
                f"{self.operator_url}/api/v1/notifications/test",
                json={"entry": entry, "channel_config": channel_config},
            )
            if response.status_code in (200, 202):
                try:
                    details = response.json()
                except (json.JSONDecodeError, ValueError):
                    details = {"raw": response.text}
                return {
                    "success": True,
                    "message": f"Test notification delivered to {channel_name}",
                    "details": details,
                }
            content_type = response.headers.get("content-type", "")
            error_msg = f"HTTP {response.status_code}"
            if content_type.startswith("application/json"):
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", error_msg)
                except (json.JSONDecodeError, ValueError):
                    pass
            return {
                "success": False,
                "message": f"Test notification failed for {channel_name}",
                "error": error_msg,
            }
        except httpx.HTTPError as e:
            raise NotificationChannelServiceError(
                f"Failed to send test notification: {e}", retryable=True
            ) from e
