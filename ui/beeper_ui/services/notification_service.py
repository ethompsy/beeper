"""Notification delivery service.

Orchestrates notification delivery to configured channels. Currently supports
Slack delivery; PagerDuty, email, and webhook channels are placeholders for
Stories 2-4 and 2-5.
"""

import logging
from typing import Any

import httpx

from beeper_ui.notifications.slack import SlackNotifier, SlackNotifierError

logger = logging.getLogger(__name__)


class NotificationServiceError(Exception):
    """Error in notification delivery service."""

    def __init__(self, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class NotificationDeliveryService:
    """Dispatches outbox entries to the appropriate channel delivery method."""

    def __init__(self, operator_url: str, timeout: float = 5.0) -> None:
        """Initialize the notification delivery service.

        Args:
            operator_url: Base URL of the operator API (for channel config + credentials).
            timeout: HTTP request timeout in seconds.
        """
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

    def process_outbox_entry(
        self,
        entry: dict[str, Any],
        channel_config: dict[str, Any],
        bot_token: str | None = None,
    ) -> dict[str, Any]:
        """Process an outbox entry and deliver to the appropriate channel.

        Args:
            entry: Outbox entry dict with investigation_id, event_type, severity,
                   service, payload, status.
            channel_config: Channel configuration dict with channel_type, config,
                           credentials_secret.
            bot_token: Pre-resolved bot token (for Slack). If None, credentials
                      are fetched from the operator API.

        Returns:
            Dict with 'status' ('delivered' or 'failed'), 'error' (if failed),
            'retryable' (bool), and channel-specific data.

        Raises:
            NotificationServiceError: If delivery fails.
        """
        channel_type = channel_config.get("channel_type", "")

        if channel_type == "slack":
            return self.deliver_to_slack(entry, channel_config, bot_token)

        # TODO: Story 2-4 — PagerDuty delivery
        # TODO: Story 2-5 — Email and webhook delivery
        logger.warning(
            "Unsupported channel type '%s' — delivery skipped (future stories)",
            channel_type,
        )
        return {
            "status": "skipped",
            "error": f"Channel type '{channel_type}' not yet implemented",
            "retryable": False,
        }

    def deliver_to_slack(
        self,
        entry: dict[str, Any],
        channel_config: dict[str, Any],
        bot_token: str | None = None,
    ) -> dict[str, Any]:
        """Deliver a notification to Slack.

        Args:
            entry: Outbox entry dict.
            channel_config: Slack channel configuration with 'config' containing
                           'channel' key and optionally 'mention_users'.
            bot_token: Slack bot token. If None, fetched from operator.

        Returns:
            Delivery result dict.

        Raises:
            NotificationServiceError: If Slack delivery fails.
        """
        config = channel_config.get("config", {})
        slack_channel = config.get("channel", "")
        if not slack_channel:
            raise NotificationServiceError(
                "Slack channel not configured", retryable=False
            )

        if bot_token is None:
            credentials_secret = channel_config.get("credentials_secret", "")
            bot_token = self._fetch_credential(credentials_secret, "bot_token")

        if not bot_token:
            raise NotificationServiceError(
                "Slack bot token not available", retryable=False
            )

        # Parse mention users from config
        mention_users_str = config.get("mention_users", "")
        mention_users: list[str] | None = None
        if mention_users_str and mention_users_str != "true":
            mention_users = [u.strip() for u in mention_users_str.split(",") if u.strip()]

        base_url = config.get("base_url", "")
        investigation_id = entry.get("investigation_id", "")
        payload = entry.get("payload", {})
        if isinstance(payload, str):
            import json

            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                payload = {"summary": payload}

        notifier = SlackNotifier(bot_token)

        try:
            # Check for thread continuation
            thread_ts = payload.get("slack_thread_ts")
            event_type = entry.get("event_type", "investigation_started")

            if thread_ts and event_type != "investigation_started":
                # Thread update
                result = notifier.send_thread_update(
                    channel=slack_channel,
                    thread_ts=thread_ts,
                    investigation_id=investigation_id,
                    update_type=event_type,
                    payload=payload,
                    mention_users=mention_users,
                    base_url=base_url,
                )
            else:
                # Initial message
                # Merge entry-level fields into payload for block building
                merged_payload = {
                    "severity": entry.get("severity", "low"),
                    "service": entry.get("service", "unknown"),
                    "event_type": event_type,
                    **payload,
                }
                result = notifier.send_investigation_message(
                    channel=slack_channel,
                    investigation_id=investigation_id,
                    payload=merged_payload,
                    mention_users=mention_users,
                    base_url=base_url,
                )

            return {
                "status": "delivered",
                "channel": result.get("channel", slack_channel),
                "ts": result.get("ts", ""),
                "thread_ts": thread_ts or result.get("ts", ""),
            }
        except SlackNotifierError as e:
            logger.error(
                "Slack delivery failed for investigation %s: %s",
                investigation_id,
                str(e),
            )
            raise NotificationServiceError(
                f"Slack delivery failed: {e}", retryable=e.retryable
            ) from e

    def _fetch_credential(self, secret_name: str, key: str) -> str:
        """Fetch a credential value from the operator API.

        Args:
            secret_name: K8s Secret name.
            key: Key within the Secret data.

        Returns:
            Credential value as string, or empty string on failure.
        """
        if not secret_name:
            return ""
        try:
            response = self.client.get(
                f"{self.operator_url}/api/v1/secrets/{secret_name}/keys/{key}"
            )
            if response.status_code == 200:
                data: dict[str, Any] = response.json()
                result: str = data.get("value", "")
                return result
            logger.warning(
                "Failed to fetch credential %s/%s: HTTP %d",
                secret_name,
                key,
                response.status_code,
            )
            return ""
        except httpx.HTTPError as e:
            logger.warning(
                "Error fetching credential %s/%s: %s",
                secret_name,
                key,
                str(e),
            )
            return ""
