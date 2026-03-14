"""Slack channel integration for Beeper notifications.

Sends rich Block Kit messages to Slack channels with investigation context,
threaded reply updates, @mentions, and action buttons. Uses the Slack SDK
WebClient for reliable delivery with built-in rate limiting.

Implements FR10: Rich Slack messages with threads, @mentions, and action buttons.
"""

import logging
from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


class SlackNotifierError(Exception):
    """Error sending Slack notification."""

    def __init__(self, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class SlackNotifier:
    """Sends rich Slack notifications for Beeper investigations.

    Uses Slack Block Kit for structured messages with investigation summary,
    evidence highlights, confidence scores, and action buttons.
    """

    def __init__(self, bot_token: str) -> None:
        """Initialize the Slack notifier.

        Args:
            bot_token: Slack Bot User OAuth Token (xoxb-...).
        """
        self._client = WebClient(token=bot_token)

    def send_investigation_message(
        self,
        channel: str,
        investigation_id: str,
        payload: dict[str, Any],
        mention_users: list[str] | None = None,
        base_url: str = "",
    ) -> dict[str, Any]:
        """Send a rich investigation notification to a Slack channel.

        Args:
            channel: Slack channel ID or name (e.g., "#sre-alerts").
            investigation_id: Beeper investigation ID.
            payload: Outbox entry payload with investigation details.
            mention_users: Optional list of Slack user IDs to @mention.
            base_url: Base URL for Beeper UI links.

        Returns:
            Dict with 'ok', 'channel', 'ts' (message timestamp for threading).

        Raises:
            SlackNotifierError: If the Slack API call fails.
        """
        blocks = self._build_blocks(investigation_id, payload, mention_users, base_url)
        fallback_text = self._build_fallback_text(investigation_id, payload)

        try:
            response = self._client.chat_postMessage(
                channel=channel,
                blocks=blocks,
                text=fallback_text,
            )
            logger.info(
                "Sent Slack investigation message: investigation=%s channel=%s ts=%s",
                investigation_id,
                channel,
                response.get("ts"),
            )
            return {
                "ok": response.get("ok", False),
                "channel": response.get("channel", channel),
                "ts": response.get("ts", ""),
            }
        except SlackApiError as e:
            error_msg = str(e.response.get("error", "unknown_error") if e.response else e)
            retryable = _is_retryable_error(error_msg)
            logger.error(
                "Slack API error sending investigation message: %s (retryable=%s)",
                error_msg,
                retryable,
            )
            raise SlackNotifierError(
                f"Failed to send Slack message: {error_msg}", retryable=retryable
            ) from e

    def send_thread_update(
        self,
        channel: str,
        thread_ts: str,
        investigation_id: str,
        update_type: str,
        payload: dict[str, Any],
        mention_users: list[str] | None = None,
        base_url: str = "",
    ) -> dict[str, Any]:
        """Post a threaded reply update to an existing investigation message.

        Args:
            channel: Slack channel ID or name.
            thread_ts: Message timestamp of the original message (for threading).
            investigation_id: Beeper investigation ID.
            update_type: Type of update: 'new_evidence', 'confidence_change', 'fix_proposed'.
            payload: Update payload with details.
            mention_users: Optional list of Slack user IDs to @mention.
            base_url: Base URL for Beeper UI links.

        Returns:
            Dict with 'ok', 'channel', 'ts'.

        Raises:
            SlackNotifierError: If the Slack API call fails.
        """
        blocks = self._format_update_blocks(
            investigation_id, update_type, payload, mention_users, base_url
        )
        fallback_text = self._build_update_fallback(investigation_id, update_type, payload)

        try:
            response = self._client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                blocks=blocks,
                text=fallback_text,
            )
            logger.info(
                "Sent Slack thread update: investigation=%s type=%s thread=%s",
                investigation_id,
                update_type,
                thread_ts,
            )
            return {
                "ok": response.get("ok", False),
                "channel": response.get("channel", channel),
                "ts": response.get("ts", ""),
            }
        except SlackApiError as e:
            error_msg = str(e.response.get("error", "unknown_error") if e.response else e)
            retryable = _is_retryable_error(error_msg)
            logger.error(
                "Slack API error sending thread update: %s (retryable=%s)",
                error_msg,
                retryable,
            )
            raise SlackNotifierError(
                f"Failed to send Slack thread update: {error_msg}", retryable=retryable
            ) from e

    def _build_blocks(
        self,
        investigation_id: str,
        payload: dict[str, Any],
        mention_users: list[str] | None = None,
        base_url: str = "",
    ) -> list[dict[str, Any]]:
        """Build Slack Block Kit blocks for an investigation notification.

        Constructs: header (severity + service), summary section,
        evidence section, confidence section, action buttons.
        """
        severity = payload.get("severity", "unknown").upper()
        service = payload.get("service", "unknown-service")
        summary = payload.get("summary", "Investigation started")
        evidence = payload.get("evidence", [])
        confidence = payload.get("confidence", None)
        event_type = payload.get("event_type", "investigation_started")

        severity_emoji = _severity_emoji(severity)

        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{severity_emoji} [{severity}] {service}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Investigation:* `{investigation_id}`\n"
                        f"*Event:* {event_type}\n\n{summary}"
                    ),
                },
            },
        ]

        # Evidence highlights
        if evidence:
            evidence_lines = evidence[:5]  # Cap at 5 items
            evidence_text = "\n".join(f"• {item}" for item in evidence_lines)
            if len(evidence) > 5:
                evidence_text += f"\n_...and {len(evidence) - 5} more_"
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Evidence Highlights:*\n{evidence_text}",
                    },
                }
            )

        # Confidence score
        if confidence is not None:
            confidence_pct = (
                f"{confidence * 100:.0f}%" if isinstance(confidence, float) else str(confidence)
            )
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Confidence:* {confidence_pct}",
                    },
                }
            )

        # @mentions
        if mention_users:
            mentions_text = _build_mentions(mention_users)
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"cc: {mentions_text}"},
                }
            )

        # Action buttons
        actions: list[dict[str, Any]] = [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "View Investigation", "emoji": True},
                "url": f"{base_url}/investigations/{investigation_id}",
                "action_id": "view_investigation",
            }
        ]
        if event_type == "fix_proposed":
            actions.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve Fix", "emoji": True},
                    "url": f"{base_url}/investigations/{investigation_id}#approve",
                    "style": "primary",
                    "action_id": "approve_fix",
                }
            )
        blocks.append({"type": "actions", "elements": actions})

        return blocks

    def _format_update_blocks(
        self,
        investigation_id: str,
        update_type: str,
        payload: dict[str, Any],
        mention_users: list[str] | None = None,
        base_url: str = "",
    ) -> list[dict[str, Any]]:
        """Build Block Kit blocks for a threaded update.

        Different layouts for: new_evidence, confidence_change, fix_proposed.
        """
        blocks: list[dict[str, Any]] = []

        if update_type == "new_evidence":
            evidence = payload.get("evidence", [])
            evidence_text = "\n".join(f"• {item}" for item in evidence[:5])
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*New Evidence Found:*\n{evidence_text}",
                    },
                }
            )
        elif update_type == "confidence_change":
            old_conf = payload.get("old_confidence", "?")
            new_conf = payload.get("new_confidence", "?")
            old_pct = f"{old_conf * 100:.0f}%" if isinstance(old_conf, float) else str(old_conf)
            new_pct = f"{new_conf * 100:.0f}%" if isinstance(new_conf, float) else str(new_conf)
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Confidence Updated:* {old_pct} → {new_pct}",
                    },
                }
            )
        elif update_type == "fix_proposed":
            fix_desc = payload.get("fix_description", "Fix proposed")
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Fix Proposed:*\n{fix_desc}",
                    },
                }
            )
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Review Fix",
                                "emoji": True,
                            },
                            "url": f"{base_url}/investigations/{investigation_id}#approve",
                            "style": "primary",
                            "action_id": "approve_fix",
                        }
                    ],
                }
            )
        else:
            summary = payload.get("summary", f"Update: {update_type}")
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": summary},
                }
            )

        # @mentions on updates
        if mention_users:
            mentions_text = _build_mentions(mention_users)
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"cc: {mentions_text}"},
                }
            )

        return blocks

    def _build_fallback_text(
        self, investigation_id: str, payload: dict[str, Any]
    ) -> str:
        """Build plain-text fallback for push notifications."""
        severity = payload.get("severity", "unknown").upper()
        service = payload.get("service", "unknown-service")
        summary = payload.get("summary", "Investigation started")
        return f"[{severity}] {service} - {investigation_id}: {summary}"

    def _build_update_fallback(
        self, investigation_id: str, update_type: str, payload: dict[str, Any]
    ) -> str:
        """Build plain-text fallback for thread update notifications."""
        if update_type == "new_evidence":
            return f"New evidence found for {investigation_id}"
        elif update_type == "confidence_change":
            new_conf = payload.get("new_confidence", "?")
            return f"Confidence updated for {investigation_id}: {new_conf}"
        elif update_type == "fix_proposed":
            return f"Fix proposed for {investigation_id}"
        return f"Update ({update_type}) for {investigation_id}"


def _build_mentions(user_ids: list[str]) -> str:
    """Format Slack user IDs as @mention strings.

    Args:
        user_ids: List of Slack user IDs (e.g., ["U12345", "U67890"]).

    Returns:
        Formatted mention string (e.g., "<@U12345> <@U67890>").
    """
    return " ".join(f"<@{uid}>" for uid in user_ids if uid)


def _severity_emoji(severity: str) -> str:
    """Map severity level to an emoji for Slack header."""
    mapping = {
        "CRITICAL": "\U0001f534",  # red circle
        "HIGH": "\U0001f7e0",  # orange circle
        "MEDIUM": "\U0001f7e1",  # yellow circle
        "LOW": "\U0001f7e2",  # green circle
    }
    return mapping.get(severity.upper(), "\u26aa")  # white circle default


def _is_retryable_error(error: str) -> bool:
    """Determine if a Slack API error is retryable."""
    non_retryable = {
        "channel_not_found",
        "not_authed",
        "invalid_auth",
        "account_inactive",
        "token_revoked",
        "no_permission",
        "missing_scope",
        "is_archived",
    }
    return error not in non_retryable
