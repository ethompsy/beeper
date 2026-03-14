"""Tests for the Slack notifier module."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from beeper_ui.notifications.slack import (
    SlackNotifier,
    SlackNotifierError,
    _build_mentions,
    _is_retryable_error,
    _severity_emoji,
)

# --- Helper fixtures ---


def _make_payload(**overrides: Any) -> dict[str, Any]:
    """Create a sample payload for testing."""
    base: dict[str, Any] = {
        "severity": "high",
        "service": "payment-service",
        "event_type": "investigation_started",
        "summary": "CPU usage spiked to 95% on payment-service",
        "evidence": [
            "CPU usage: 95% (threshold: 80%)",
            "Memory usage: 72%",
            "Error rate: 2.1%",
        ],
        "confidence": 0.87,
    }
    base.update(overrides)
    return base


# --- SlackNotifier block construction tests ---


class TestBuildBlocks:
    """Tests for _build_blocks() block construction."""

    def test_builds_header_with_severity_and_service(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        payload = _make_payload()
        blocks = notifier._build_blocks("inv-001", payload)

        header = blocks[0]
        assert header["type"] == "header"
        assert "HIGH" in header["text"]["text"]
        assert "payment-service" in header["text"]["text"]

    def test_builds_summary_section(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        payload = _make_payload(summary="Test summary")
        blocks = notifier._build_blocks("inv-001", payload)

        summary_block = blocks[1]
        assert summary_block["type"] == "section"
        assert "inv-001" in summary_block["text"]["text"]
        assert "Test summary" in summary_block["text"]["text"]

    def test_builds_evidence_section(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        payload = _make_payload(evidence=["Error rate spike", "Latency increase"])
        blocks = notifier._build_blocks("inv-001", payload)

        evidence_block = blocks[2]
        assert evidence_block["type"] == "section"
        assert "Evidence Highlights" in evidence_block["text"]["text"]
        assert "Error rate spike" in evidence_block["text"]["text"]

    def test_caps_evidence_at_five_items(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        evidence_items = [f"Item {i}" for i in range(10)]
        payload = _make_payload(evidence=evidence_items)
        blocks = notifier._build_blocks("inv-001", payload)

        evidence_block = blocks[2]
        text = evidence_block["text"]["text"]
        assert "Item 0" in text
        assert "Item 4" in text
        assert "...and 5 more" in text

    def test_builds_confidence_section(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        payload = _make_payload(confidence=0.87)
        blocks = notifier._build_blocks("inv-001", payload)

        # Find confidence block
        conf_blocks = [
            b for b in blocks if b["type"] == "section" and "Confidence" in b["text"]["text"]
        ]
        assert len(conf_blocks) == 1
        assert "87%" in conf_blocks[0]["text"]["text"]

    def test_builds_action_buttons_with_view(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        payload = _make_payload()
        blocks = notifier._build_blocks("inv-001", payload, base_url="https://beeper.dev")

        actions = blocks[-1]
        assert actions["type"] == "actions"
        assert len(actions["elements"]) == 1
        assert actions["elements"][0]["text"]["text"] == "View Investigation"
        assert "https://beeper.dev/investigations/inv-001" in actions["elements"][0]["url"]

    def test_builds_approve_fix_button_for_fix_proposed(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        payload = _make_payload(event_type="fix_proposed")
        blocks = notifier._build_blocks("inv-001", payload, base_url="https://beeper.dev")

        actions = blocks[-1]
        assert actions["type"] == "actions"
        assert len(actions["elements"]) == 2
        assert actions["elements"][1]["text"]["text"] == "Approve Fix"
        assert actions["elements"][1]["style"] == "primary"

    def test_builds_mentions_section(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        payload = _make_payload()
        blocks = notifier._build_blocks(
            "inv-001", payload, mention_users=["U12345", "U67890"]
        )

        mention_blocks = [
            b for b in blocks if b["type"] == "section" and "cc:" in b["text"]["text"]
        ]
        assert len(mention_blocks) == 1
        assert "<@U12345>" in mention_blocks[0]["text"]["text"]
        assert "<@U67890>" in mention_blocks[0]["text"]["text"]

    def test_no_evidence_section_when_empty(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        payload = _make_payload(evidence=[])
        blocks = notifier._build_blocks("inv-001", payload)

        evidence_blocks = [
            b
            for b in blocks
            if b["type"] == "section" and "Evidence" in b.get("text", {}).get("text", "")
        ]
        assert len(evidence_blocks) == 0

    def test_no_confidence_section_when_none(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        payload = _make_payload(confidence=None)
        blocks = notifier._build_blocks("inv-001", payload)

        conf_blocks = [
            b
            for b in blocks
            if b["type"] == "section" and "Confidence" in b.get("text", {}).get("text", "")
        ]
        assert len(conf_blocks) == 0


class TestFormatUpdateBlocks:
    """Tests for _format_update_blocks() thread update formatting."""

    def test_new_evidence_update(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        payload: dict[str, Any] = {"evidence": ["New log correlation found"]}
        blocks = notifier._format_update_blocks("inv-001", "new_evidence", payload)

        assert len(blocks) >= 1
        assert "New Evidence Found" in blocks[0]["text"]["text"]
        assert "New log correlation found" in blocks[0]["text"]["text"]

    def test_confidence_change_update(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        payload: dict[str, Any] = {"old_confidence": 0.5, "new_confidence": 0.85}
        blocks = notifier._format_update_blocks("inv-001", "confidence_change", payload)

        assert "Confidence Updated" in blocks[0]["text"]["text"]
        assert "50%" in blocks[0]["text"]["text"]
        assert "85%" in blocks[0]["text"]["text"]

    def test_fix_proposed_update(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        payload: dict[str, Any] = {"fix_description": "Restart pod payment-service-abc123"}
        blocks = notifier._format_update_blocks(
            "inv-001", "fix_proposed", payload, base_url="https://beeper.dev"
        )

        assert "Fix Proposed" in blocks[0]["text"]["text"]
        assert "Restart pod" in blocks[0]["text"]["text"]
        # Should have action button
        assert any(b["type"] == "actions" for b in blocks)

    def test_unknown_update_type(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        payload: dict[str, Any] = {"summary": "Custom update message"}
        blocks = notifier._format_update_blocks("inv-001", "custom_event", payload)

        assert "Custom update message" in blocks[0]["text"]["text"]

    def test_update_with_mentions(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        payload: dict[str, Any] = {"evidence": ["Evidence"]}
        blocks = notifier._format_update_blocks(
            "inv-001", "new_evidence", payload, mention_users=["U12345"]
        )

        mention_blocks = [
            b for b in blocks if b["type"] == "section" and "cc:" in b["text"]["text"]
        ]
        assert len(mention_blocks) == 1
        assert "<@U12345>" in mention_blocks[0]["text"]["text"]


# --- Send investigation message tests ---


class TestSendInvestigationMessage:
    """Tests for send_investigation_message() with mocked Slack API."""

    @patch("beeper_ui.notifications.slack.WebClient")
    def test_successful_send(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {
            "ok": True,
            "channel": "C12345",
            "ts": "1234567890.123456",
        }
        mock_client_class.return_value = mock_client

        notifier = SlackNotifier("xoxb-fake-token")
        notifier._client = mock_client

        result = notifier.send_investigation_message(
            channel="#sre-alerts",
            investigation_id="inv-001",
            payload=_make_payload(),
        )

        assert result["ok"] is True
        assert result["ts"] == "1234567890.123456"
        mock_client.chat_postMessage.assert_called_once()

    @patch("beeper_ui.notifications.slack.WebClient")
    def test_send_includes_fallback_text(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ok": True, "channel": "C1", "ts": "1"}
        mock_client_class.return_value = mock_client

        notifier = SlackNotifier("xoxb-fake-token")
        notifier._client = mock_client

        notifier.send_investigation_message(
            channel="#sre-alerts",
            investigation_id="inv-001",
            payload=_make_payload(),
        )

        call_kwargs = mock_client.chat_postMessage.call_args
        assert "text" in call_kwargs.kwargs
        assert "inv-001" in call_kwargs.kwargs["text"]

    @patch("beeper_ui.notifications.slack.WebClient")
    def test_send_raises_on_api_error(self, mock_client_class: MagicMock) -> None:
        from slack_sdk.errors import SlackApiError

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.get.return_value = "channel_not_found"
        mock_client.chat_postMessage.side_effect = SlackApiError(
            message="channel_not_found", response=mock_response
        )
        mock_client_class.return_value = mock_client

        notifier = SlackNotifier("xoxb-fake-token")
        notifier._client = mock_client

        with pytest.raises(SlackNotifierError) as exc_info:
            notifier.send_investigation_message(
                channel="#nonexistent",
                investigation_id="inv-001",
                payload=_make_payload(),
            )

        assert not exc_info.value.retryable  # channel_not_found is not retryable


class TestSendThreadUpdate:
    """Tests for send_thread_update() with mocked Slack API."""

    @patch("beeper_ui.notifications.slack.WebClient")
    def test_successful_thread_update(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {
            "ok": True,
            "channel": "C12345",
            "ts": "1234567890.789",
        }
        mock_client_class.return_value = mock_client

        notifier = SlackNotifier("xoxb-fake-token")
        notifier._client = mock_client

        result = notifier.send_thread_update(
            channel="#sre-alerts",
            thread_ts="1234567890.123",
            investigation_id="inv-001",
            update_type="new_evidence",
            payload={"evidence": ["New finding"]},
        )

        assert result["ok"] is True
        call_kwargs = mock_client.chat_postMessage.call_args
        assert call_kwargs.kwargs["thread_ts"] == "1234567890.123"


# --- Utility function tests ---


class TestBuildMentions:
    """Tests for _build_mentions() helper."""

    def test_single_user(self) -> None:
        assert _build_mentions(["U12345"]) == "<@U12345>"

    def test_multiple_users(self) -> None:
        result = _build_mentions(["U12345", "U67890"])
        assert "<@U12345>" in result
        assert "<@U67890>" in result

    def test_empty_list(self) -> None:
        assert _build_mentions([]) == ""

    def test_filters_empty_strings(self) -> None:
        result = _build_mentions(["U12345", "", "U67890"])
        assert result == "<@U12345> <@U67890>"


class TestSeverityEmoji:
    """Tests for _severity_emoji() helper."""

    def test_critical(self) -> None:
        assert _severity_emoji("CRITICAL") == "\U0001f534"

    def test_high(self) -> None:
        assert _severity_emoji("HIGH") == "\U0001f7e0"

    def test_medium(self) -> None:
        assert _severity_emoji("MEDIUM") == "\U0001f7e1"

    def test_low(self) -> None:
        assert _severity_emoji("LOW") == "\U0001f7e2"

    def test_unknown(self) -> None:
        assert _severity_emoji("UNKNOWN") == "\u26aa"

    def test_case_insensitive(self) -> None:
        assert _severity_emoji("critical") == "\U0001f534"


class TestIsRetryableError:
    """Tests for _is_retryable_error() helper."""

    def test_retryable_errors(self) -> None:
        assert _is_retryable_error("rate_limited") is True
        assert _is_retryable_error("service_unavailable") is True
        assert _is_retryable_error("timeout") is True

    def test_non_retryable_errors(self) -> None:
        assert _is_retryable_error("channel_not_found") is False
        assert _is_retryable_error("not_authed") is False
        assert _is_retryable_error("invalid_auth") is False
        assert _is_retryable_error("token_revoked") is False
        assert _is_retryable_error("no_permission") is False
        assert _is_retryable_error("missing_scope") is False
        assert _is_retryable_error("is_archived") is False
        assert _is_retryable_error("account_inactive") is False


class TestFallbackText:
    """Tests for fallback text building."""

    def test_investigation_fallback(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        payload = _make_payload()
        text = notifier._build_fallback_text("inv-001", payload)
        assert "[HIGH]" in text
        assert "payment-service" in text
        assert "inv-001" in text

    def test_update_fallback_new_evidence(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        text = notifier._build_update_fallback("inv-001", "new_evidence", {})
        assert "evidence" in text.lower()
        assert "inv-001" in text

    def test_update_fallback_confidence_change(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        text = notifier._build_update_fallback(
            "inv-001", "confidence_change", {"new_confidence": 0.9}
        )
        assert "confidence" in text.lower()

    def test_update_fallback_fix_proposed(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        text = notifier._build_update_fallback("inv-001", "fix_proposed", {})
        assert "fix" in text.lower()

    def test_update_fallback_unknown_type(self) -> None:
        notifier = SlackNotifier("xoxb-fake-token")
        text = notifier._build_update_fallback("inv-001", "custom", {})
        assert "inv-001" in text
