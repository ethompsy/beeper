"""Tests for the PagerDuty notifier module."""

from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from beeper_ui.notifications.pagerduty import (
    PAGERDUTY_EVENTS_URL,
    PagerDutyNotifier,
    PagerDutyNotifierError,
    _map_severity,
    _truncate_summary,
)


def _make_payload(**overrides: Any) -> dict[str, Any]:
    """Create a sample investigation payload for testing."""
    base: dict[str, Any] = {
        "severity": "critical",
        "service": "payment-service",
        "summary": "CPU spike detected on payment-service",
        "evidence": ["CPU at 95%", "Memory at 88%"],
        "confidence": 0.87,
    }
    base.update(overrides)
    return base


def _mock_success_response(dedup_key: str = "inv-001") -> httpx.Response:
    """Create a mock successful PagerDuty response."""
    response = httpx.Response(
        status_code=202,
        json={"status": "success", "message": "Event processed", "dedup_key": dedup_key},
        request=httpx.Request("POST", PAGERDUTY_EVENTS_URL),
    )
    return response


def _mock_error_response(status_code: int, message: str = "error") -> httpx.Response:
    """Create a mock error PagerDuty response."""
    response = httpx.Response(
        status_code=status_code,
        json={"status": "error", "message": message},
        request=httpx.Request("POST", PAGERDUTY_EVENTS_URL),
    )
    return response


class TestSeverityMapping:
    """Tests for _map_severity()."""

    def test_critical_maps_to_critical(self) -> None:
        assert _map_severity("critical") == "critical"

    def test_high_maps_to_error(self) -> None:
        assert _map_severity("high") == "error"

    def test_medium_maps_to_warning(self) -> None:
        assert _map_severity("medium") == "warning"

    def test_low_maps_to_info(self) -> None:
        assert _map_severity("low") == "info"

    def test_unknown_defaults_to_info(self) -> None:
        assert _map_severity("unknown") == "info"

    def test_case_insensitive(self) -> None:
        assert _map_severity("CRITICAL") == "critical"
        assert _map_severity("High") == "error"


class TestTruncateSummary:
    """Tests for _truncate_summary()."""

    def test_short_text_unchanged(self) -> None:
        assert _truncate_summary("hello", 1024) == "hello"

    def test_exact_length_unchanged(self) -> None:
        text = "a" * 1024
        assert _truncate_summary(text, 1024) == text

    def test_long_text_truncated_with_ellipsis(self) -> None:
        text = "a" * 1030
        result = _truncate_summary(text, 1024)
        assert len(result) == 1024
        assert result.endswith("...")

    def test_empty_text(self) -> None:
        assert _truncate_summary("", 1024) == ""


class TestMapEventType:
    """Tests for PagerDutyNotifier.map_event_type()."""

    def test_investigation_started_maps_to_trigger(self) -> None:
        assert PagerDutyNotifier.map_event_type("investigation_started") == "trigger"

    def test_investigating_maps_to_acknowledge(self) -> None:
        assert PagerDutyNotifier.map_event_type("investigating") == "acknowledge"

    def test_evidence_found_maps_to_acknowledge(self) -> None:
        assert PagerDutyNotifier.map_event_type("evidence_found") == "acknowledge"

    def test_confidence_change_maps_to_acknowledge(self) -> None:
        assert PagerDutyNotifier.map_event_type("confidence_change") == "acknowledge"

    def test_resolved_maps_to_resolve(self) -> None:
        assert PagerDutyNotifier.map_event_type("resolved") == "resolve"

    def test_fix_verified_maps_to_resolve(self) -> None:
        assert PagerDutyNotifier.map_event_type("fix_verified") == "resolve"

    def test_fix_approved_maps_to_resolve(self) -> None:
        assert PagerDutyNotifier.map_event_type("fix_approved") == "resolve"

    def test_unknown_event_type_defaults_to_trigger(self) -> None:
        assert PagerDutyNotifier.map_event_type("some_random_event") == "trigger"


class TestTriggerIncident:
    """Tests for trigger_incident()."""

    @patch("beeper_ui.notifications.pagerduty.httpx.Client")
    def test_successful_trigger(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_success_response("inv-001")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = PagerDutyNotifier("test-routing-key")
        result = notifier.trigger_incident(
            investigation_id="inv-001",
            payload=_make_payload(),
            base_url="https://beeper.example.com",
        )

        assert result["status"] == "success"
        assert result["dedup_key"] == "inv-001"

        # Verify the POST call
        call_args = mock_client.post.call_args
        assert call_args.args[0] == PAGERDUTY_EVENTS_URL
        event_body = call_args.kwargs["json"]
        assert event_body["routing_key"] == "test-routing-key"
        assert event_body["event_action"] == "trigger"
        assert event_body["dedup_key"] == "inv-001"
        assert event_body["payload"]["severity"] == "critical"
        assert event_body["payload"]["source"] == "payment-service"
        assert "links" in event_body
        assert event_body["links"][0]["href"] == "https://beeper.example.com/investigations/inv-001"

    @patch("beeper_ui.notifications.pagerduty.httpx.Client")
    def test_trigger_payload_has_custom_details(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_success_response()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = PagerDutyNotifier("test-key")
        notifier.trigger_incident("inv-001", _make_payload())

        event_body = mock_client.post.call_args.kwargs["json"]
        custom = event_body["payload"]["custom_details"]
        assert custom["investigation_id"] == "inv-001"
        assert custom["confidence"] == 0.87
        assert "CPU at 95%" in custom["evidence_summary"]

    @patch("beeper_ui.notifications.pagerduty.httpx.Client")
    def test_trigger_summary_truncated_at_1024(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_success_response()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        long_summary = "x" * 2000
        notifier = PagerDutyNotifier("test-key")
        notifier.trigger_incident("inv-001", _make_payload(summary=long_summary))

        event_body = mock_client.post.call_args.kwargs["json"]
        summary = event_body["payload"]["summary"]
        assert len(summary) <= 1024
        assert summary.endswith("...")

    @patch("beeper_ui.notifications.pagerduty.httpx.Client")
    def test_trigger_without_evidence(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_success_response()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = PagerDutyNotifier("test-key")
        notifier.trigger_incident("inv-001", _make_payload(evidence=[], confidence=None))

        event_body = mock_client.post.call_args.kwargs["json"]
        custom = event_body["payload"]["custom_details"]
        assert "evidence_summary" not in custom
        assert "confidence" not in custom

    @patch("beeper_ui.notifications.pagerduty.httpx.Client")
    def test_trigger_severity_mapping_in_payload(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_success_response()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = PagerDutyNotifier("test-key")
        notifier.trigger_incident("inv-001", _make_payload(severity="high"))

        event_body = mock_client.post.call_args.kwargs["json"]
        assert event_body["payload"]["severity"] == "error"


class TestAcknowledgeIncident:
    """Tests for acknowledge_incident()."""

    @patch("beeper_ui.notifications.pagerduty.httpx.Client")
    def test_successful_acknowledge(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_success_response("inv-001")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = PagerDutyNotifier("test-key")
        result = notifier.acknowledge_incident(dedup_key="inv-001")

        assert result["status"] == "success"
        assert result["dedup_key"] == "inv-001"

        event_body = mock_client.post.call_args.kwargs["json"]
        assert event_body["event_action"] == "acknowledge"
        assert event_body["dedup_key"] == "inv-001"
        assert "payload" not in event_body

    @patch("beeper_ui.notifications.pagerduty.httpx.Client")
    def test_acknowledge_uses_routing_key(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_success_response()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = PagerDutyNotifier("my-routing-key")
        notifier.acknowledge_incident("inv-001")

        event_body = mock_client.post.call_args.kwargs["json"]
        assert event_body["routing_key"] == "my-routing-key"


class TestResolveIncident:
    """Tests for resolve_incident()."""

    @patch("beeper_ui.notifications.pagerduty.httpx.Client")
    def test_successful_resolve(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_success_response("inv-001")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = PagerDutyNotifier("test-key")
        result = notifier.resolve_incident(dedup_key="inv-001")

        assert result["status"] == "success"
        assert result["dedup_key"] == "inv-001"

        event_body = mock_client.post.call_args.kwargs["json"]
        assert event_body["event_action"] == "resolve"
        assert event_body["dedup_key"] == "inv-001"

    @patch("beeper_ui.notifications.pagerduty.httpx.Client")
    def test_resolve_uses_routing_key(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_success_response()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = PagerDutyNotifier("my-routing-key")
        notifier.resolve_incident("inv-001")

        event_body = mock_client.post.call_args.kwargs["json"]
        assert event_body["routing_key"] == "my-routing-key"


class TestErrorHandling:
    """Tests for error handling and retryability classification."""

    @patch("beeper_ui.notifications.pagerduty.httpx.Client")
    def test_http_400_is_non_retryable(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_error_response(400, "Invalid routing key")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = PagerDutyNotifier("bad-key")
        with pytest.raises(PagerDutyNotifierError) as exc_info:
            notifier.trigger_incident("inv-001", _make_payload())
        assert not exc_info.value.retryable

    @patch("beeper_ui.notifications.pagerduty.httpx.Client")
    def test_http_401_is_non_retryable(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_error_response(401, "Unauthorized")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = PagerDutyNotifier("bad-key")
        with pytest.raises(PagerDutyNotifierError) as exc_info:
            notifier.trigger_incident("inv-001", _make_payload())
        assert not exc_info.value.retryable

    @patch("beeper_ui.notifications.pagerduty.httpx.Client")
    def test_http_403_is_non_retryable(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_error_response(403, "Forbidden")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = PagerDutyNotifier("bad-key")
        with pytest.raises(PagerDutyNotifierError) as exc_info:
            notifier.trigger_incident("inv-001", _make_payload())
        assert not exc_info.value.retryable

    @patch("beeper_ui.notifications.pagerduty.httpx.Client")
    def test_http_429_is_retryable(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_error_response(429, "Rate limited")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = PagerDutyNotifier("test-key")
        with pytest.raises(PagerDutyNotifierError) as exc_info:
            notifier.trigger_incident("inv-001", _make_payload())
        assert exc_info.value.retryable

    @patch("beeper_ui.notifications.pagerduty.httpx.Client")
    def test_http_500_is_retryable(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_error_response(500, "Internal server error")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = PagerDutyNotifier("test-key")
        with pytest.raises(PagerDutyNotifierError) as exc_info:
            notifier.trigger_incident("inv-001", _make_payload())
        assert exc_info.value.retryable

    @patch("beeper_ui.notifications.pagerduty.httpx.Client")
    def test_connection_error_is_retryable(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = PagerDutyNotifier("test-key")
        with pytest.raises(PagerDutyNotifierError) as exc_info:
            notifier.trigger_incident("inv-001", _make_payload())
        assert exc_info.value.retryable
        assert "connection error" in str(exc_info.value).lower()

    @patch("beeper_ui.notifications.pagerduty.httpx.Client")
    def test_timeout_error_is_retryable(self, mock_client_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.ReadTimeout("Read timed out")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = PagerDutyNotifier("test-key")
        with pytest.raises(PagerDutyNotifierError) as exc_info:
            notifier.trigger_incident("inv-001", _make_payload())
        assert exc_info.value.retryable
        assert "timeout" in str(exc_info.value).lower()


class TestMalformedResponse:
    """Tests for handling malformed API responses."""

    @patch("beeper_ui.notifications.pagerduty.httpx.Client")
    def test_malformed_json_on_success_still_returns(self, mock_client_class: MagicMock) -> None:
        """Malformed 202 JSON still returns result using dedup_key from event."""
        mock_client = MagicMock()
        # Create a response that raises on .json()
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = PagerDutyNotifier("test-key")
        result = notifier.trigger_incident("inv-001", _make_payload())

        assert result["status"] == "success"
        assert result["dedup_key"] == "inv-001"


class TestEventLifecycle:
    """Tests for the full trigger → acknowledge → resolve lifecycle."""

    @patch("beeper_ui.notifications.pagerduty.httpx.Client")
    def test_full_lifecycle(self, mock_client_class: MagicMock) -> None:
        """Test trigger → acknowledge → resolve with dedup_key tracking."""
        mock_client = MagicMock()
        mock_client.post.return_value = _mock_success_response("inv-lifecycle")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        notifier = PagerDutyNotifier("test-key")

        # Step 1: Trigger
        trigger_result = notifier.trigger_incident("inv-lifecycle", _make_payload())
        assert trigger_result["status"] == "success"
        dedup_key = trigger_result["dedup_key"]
        assert dedup_key == "inv-lifecycle"

        # Verify trigger event
        trigger_body = mock_client.post.call_args.kwargs["json"]
        assert trigger_body["event_action"] == "trigger"

        # Step 2: Acknowledge
        ack_result = notifier.acknowledge_incident(dedup_key)
        assert ack_result["status"] == "success"
        ack_body = mock_client.post.call_args.kwargs["json"]
        assert ack_body["event_action"] == "acknowledge"
        assert ack_body["dedup_key"] == dedup_key

        # Step 3: Resolve
        resolve_result = notifier.resolve_incident(dedup_key)
        assert resolve_result["status"] == "success"
        resolve_body = mock_client.post.call_args.kwargs["json"]
        assert resolve_body["event_action"] == "resolve"
        assert resolve_body["dedup_key"] == dedup_key


class TestBuildPayload:
    """Tests for _build_payload() internal method."""

    def test_payload_structure(self) -> None:
        notifier = PagerDutyNotifier("test-key")
        result = notifier._build_payload(
            "inv-001",
            _make_payload(),
            "https://beeper.example.com",
        )

        assert result["severity"] == "critical"
        assert result["source"] == "payment-service"
        assert result["component"] == "beeper-investigator"
        assert result["class"] == "investigation"
        assert "[Beeper] payment-service:" in result["summary"]
        assert result["custom_details"]["investigation_id"] == "inv-001"

    def test_payload_without_optional_fields(self) -> None:
        notifier = PagerDutyNotifier("test-key")
        result = notifier._build_payload(
            "inv-001",
            {"severity": "low", "service": "web"},
            "",
        )

        assert result["severity"] == "info"
        assert result["source"] == "web"
        assert "evidence_summary" not in result["custom_details"]
        assert "confidence" not in result["custom_details"]

    def test_payload_evidence_capped_at_5(self) -> None:
        notifier = PagerDutyNotifier("test-key")
        evidence = [f"Evidence item {i}" for i in range(10)]
        result = notifier._build_payload(
            "inv-001",
            _make_payload(evidence=evidence),
            "",
        )

        # Evidence summary should only include first 5 items
        summary = result["custom_details"]["evidence_summary"]
        assert "Evidence item 0" in summary
        assert "Evidence item 4" in summary
        # Items beyond 5 should not be in the joined string
        assert "Evidence item 5" not in summary
