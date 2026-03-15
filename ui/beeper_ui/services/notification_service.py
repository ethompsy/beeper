"""Notification delivery service.

Orchestrates notification delivery to configured channels. Supports Slack
and PagerDuty delivery; email and webhook channels are placeholders for
Story 2-5.
"""

import json
import logging
from typing import Any

import httpx

from beeper_ui.notifications.pagerduty import PagerDutyNotifier, PagerDutyNotifierError
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

        if channel_type == "pagerduty":
            return self.deliver_to_pagerduty(entry, channel_config)

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

        fetch_error = ""
        if bot_token is None:
            credentials_secret = channel_config.get("credentials_secret", "")
            bot_token, fetch_error = self._fetch_credential(credentials_secret, "bot_token")

        if not bot_token:
            error_detail = f" ({fetch_error})" if fetch_error else ""
            raise NotificationServiceError(
                f"Slack bot token not available{error_detail}", retryable=False
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

    def deliver_to_pagerduty(
        self,
        entry: dict[str, Any],
        channel_config: dict[str, Any],
    ) -> dict[str, Any]:
        """Deliver a notification to PagerDuty via Events API v2.

        Determines the appropriate PagerDuty action (trigger/acknowledge/resolve)
        from the event_type and manages dedup_key lifecycle through the outbox payload.

        Args:
            entry: Outbox entry dict.
            channel_config: PagerDuty channel configuration with 'config' containing
                           'routing_key'.

        Returns:
            Delivery result dict with status, dedup_key, pagerduty_dedup_key.

        Raises:
            NotificationServiceError: If PagerDuty delivery fails.
        """
        config = channel_config.get("config", {})
        routing_key = config.get("routing_key", "")
        if not routing_key:
            raise NotificationServiceError(
                "PagerDuty routing_key not configured", retryable=False
            )

        investigation_id = entry.get("investigation_id", "")
        event_type = entry.get("event_type", "investigation_started")
        payload = entry.get("payload", {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                payload = {"summary": payload}

        base_url = config.get("base_url", "")

        # Merge entry-level fields into payload for PagerDuty payload building
        merged_payload = {
            "severity": entry.get("severity", "low"),
            "service": entry.get("service", "unknown"),
            **payload,
        }

        notifier = PagerDutyNotifier(routing_key)
        action = PagerDutyNotifier.map_event_type(event_type)

        try:
            # Determine dedup_key: use stored one for ack/resolve, investigation_id for trigger
            stored_dedup_key = payload.get("pagerduty_dedup_key", "")

            if action == "acknowledge":
                dedup_key = stored_dedup_key or investigation_id
                if not stored_dedup_key:
                    logger.warning(
                        "No stored pagerduty_dedup_key for %s action on investigation %s, "
                        "falling back to investigation_id",
                        action,
                        investigation_id,
                    )
                result = notifier.acknowledge_incident(dedup_key=dedup_key)
            elif action == "resolve":
                dedup_key = stored_dedup_key or investigation_id
                if not stored_dedup_key:
                    logger.warning(
                        "No stored pagerduty_dedup_key for %s action on investigation %s, "
                        "falling back to investigation_id",
                        action,
                        investigation_id,
                    )
                result = notifier.resolve_incident(dedup_key=dedup_key)
            else:
                # trigger
                result = notifier.trigger_incident(
                    investigation_id=investigation_id,
                    payload=merged_payload,
                    base_url=base_url,
                )

            return {
                "status": "delivered",
                "dedup_key": result.get("dedup_key", investigation_id),
                "pagerduty_dedup_key": result.get("dedup_key", investigation_id),
            }
        except PagerDutyNotifierError as e:
            logger.error(
                "PagerDuty delivery failed for investigation %s: %s",
                investigation_id,
                str(e),
            )
            raise NotificationServiceError(
                f"PagerDuty delivery failed: {e}", retryable=e.retryable
            ) from e

    def _fetch_credential(self, secret_name: str, key: str) -> tuple[str, str]:
        """Fetch a credential value from the operator API.

        Args:
            secret_name: K8s Secret name.
            key: Key within the Secret data.

        Returns:
            Tuple of (credential_value, error_reason). Error reason is empty on success.
        """
        if not secret_name:
            return "", "no secret name configured"
        try:
            response = self.client.get(
                f"{self.operator_url}/api/v1/secrets/{secret_name}/keys/{key}"
            )
            if response.status_code == 200:
                data: dict[str, Any] = response.json()
                result: str = data.get("value", "")
                return result, ""
            reason = f"HTTP {response.status_code} from operator API"
            logger.warning(
                "Failed to fetch credential %s/%s: %s",
                secret_name,
                key,
                reason,
            )
            return "", reason
        except httpx.HTTPError as e:
            reason = f"operator API error: {e}"
            logger.warning(
                "Error fetching credential %s/%s: %s",
                secret_name,
                key,
                reason,
            )
            return "", reason
