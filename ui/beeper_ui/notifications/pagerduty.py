"""PagerDuty channel integration for Beeper notifications.

Creates, acknowledges, and resolves PagerDuty incidents via Events API v2,
providing bidirectional lifecycle management tied to Beeper investigations.

Implements FR11: Create, acknowledge, and auto-resolve PagerDuty incidents.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PAGERDUTY_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"

# Beeper event types that map to PagerDuty acknowledge action
_ACKNOWLEDGE_EVENT_TYPES = frozenset({
    "investigating",
    "evidence_found",
    "confidence_change",
})

# Beeper event types that map to PagerDuty resolve action
_RESOLVE_EVENT_TYPES = frozenset({
    "resolved",
    "fix_verified",
    "fix_approved",
})

# HTTP status codes that indicate non-retryable errors
_NON_RETRYABLE_STATUS_CODES = frozenset({400, 401, 403})

# PagerDuty summary max length
_MAX_SUMMARY_LENGTH = 1024

# Beeper severity → PagerDuty severity mapping
_SEVERITY_MAP = {
    "critical": "critical",
    "high": "error",
    "medium": "warning",
    "low": "info",
}


class PagerDutyNotifierError(Exception):
    """Error sending PagerDuty notification."""

    def __init__(self, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class PagerDutyNotifier:
    """Manages PagerDuty incident lifecycle for Beeper investigations.

    Creates, acknowledges, and resolves incidents via PagerDuty Events API v2.
    Uses httpx for HTTP calls — no additional dependencies required.
    """

    def __init__(self, routing_key: str) -> None:
        """Initialize the PagerDuty notifier.

        Args:
            routing_key: PagerDuty Events API v2 routing/integration key.
        """
        self._routing_key = routing_key

    def trigger_incident(
        self,
        investigation_id: str,
        payload: dict[str, Any],
        base_url: str = "",
    ) -> dict[str, Any]:
        """Create a new PagerDuty incident for an investigation.

        Args:
            investigation_id: Beeper investigation ID (used as dedup_key).
            payload: Outbox entry payload with investigation details.
            base_url: Base URL for Beeper UI links.

        Returns:
            Dict with 'status', 'dedup_key'.

        Raises:
            PagerDutyNotifierError: If the API call fails.
        """
        event_payload = self._build_payload(investigation_id, payload, base_url)
        event = {
            "routing_key": self._routing_key,
            "event_action": "trigger",
            "dedup_key": investigation_id,
            "payload": event_payload,
            "links": [
                {
                    "href": f"{base_url}/investigations/{investigation_id}",
                    "text": "View Investigation in Beeper",
                }
            ],
        }
        return self._send_event(event)

    def acknowledge_incident(
        self,
        dedup_key: str,
    ) -> dict[str, Any]:
        """Acknowledge a PagerDuty incident.

        Args:
            dedup_key: Dedup key from the original trigger event.

        Returns:
            Dict with 'status', 'dedup_key'.

        Raises:
            PagerDutyNotifierError: If the API call fails.
        """
        event = {
            "routing_key": self._routing_key,
            "event_action": "acknowledge",
            "dedup_key": dedup_key,
        }
        return self._send_event(event)

    def resolve_incident(
        self,
        dedup_key: str,
        payload: dict[str, Any] | None = None,
        base_url: str = "",
    ) -> dict[str, Any]:
        """Resolve a PagerDuty incident.

        Args:
            dedup_key: Dedup key from the original trigger event.
            payload: Optional payload with resolution details.
            base_url: Base URL for Beeper UI links.

        Returns:
            Dict with 'status', 'dedup_key'.

        Raises:
            PagerDutyNotifierError: If the API call fails.
        """
        event: dict[str, Any] = {
            "routing_key": self._routing_key,
            "event_action": "resolve",
            "dedup_key": dedup_key,
        }
        return self._send_event(event)

    def _send_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Send an event to PagerDuty Events API v2.

        Args:
            event: Complete event payload.

        Returns:
            Dict with 'status' and 'dedup_key'.

        Raises:
            PagerDutyNotifierError: If the API call fails.
        """
        try:
            with httpx.Client(timeout=httpx.Timeout(10.0, read=30.0)) as client:
                response = client.post(
                    PAGERDUTY_EVENTS_URL,
                    json=event,
                    headers={"Content-Type": "application/json"},
                )

            if response.status_code in (200, 201, 202):
                data = response.json()
                dedup_key = data.get("dedup_key", event.get("dedup_key", ""))
                logger.info(
                    "PagerDuty event sent: action=%s dedup_key=%s status=%s",
                    event.get("event_action"),
                    dedup_key,
                    data.get("status"),
                )
                return {
                    "status": "success",
                    "dedup_key": dedup_key,
                }

            # Error response
            retryable = response.status_code not in _NON_RETRYABLE_STATUS_CODES
            error_body = ""
            try:
                error_data = response.json()
                error_body = error_data.get("message", str(error_data))
            except Exception:
                error_body = response.text[:200]

            error_msg = (
                f"PagerDuty API error: HTTP {response.status_code} — {error_body}"
            )
            logger.error(
                "PagerDuty API error: action=%s status=%d retryable=%s body=%s",
                event.get("event_action"),
                response.status_code,
                retryable,
                error_body,
            )
            raise PagerDutyNotifierError(error_msg, retryable=retryable)

        except httpx.ConnectError as e:
            logger.error("PagerDuty connection error: %s", e)
            raise PagerDutyNotifierError(
                f"PagerDuty connection error: {e}", retryable=True
            ) from e
        except httpx.TimeoutException as e:
            logger.error("PagerDuty timeout: %s", e)
            raise PagerDutyNotifierError(
                f"PagerDuty timeout: {e}", retryable=True
            ) from e

    def _build_payload(
        self,
        investigation_id: str,
        payload: dict[str, Any],
        base_url: str = "",
    ) -> dict[str, Any]:
        """Build the PagerDuty event payload object.

        Args:
            investigation_id: Beeper investigation ID.
            payload: Outbox entry payload with investigation details.
            base_url: Base URL for Beeper UI links.

        Returns:
            PagerDuty payload dict with summary, severity, source, etc.
        """
        severity = payload.get("severity", "low")
        service = payload.get("service", "unknown-service")
        summary_text = payload.get("summary", "Investigation started")
        evidence = payload.get("evidence", [])
        confidence = payload.get("confidence")

        summary = _truncate_summary(
            f"[Beeper] {service}: {summary_text}", _MAX_SUMMARY_LENGTH
        )

        custom_details: dict[str, Any] = {
            "investigation_id": investigation_id,
            "beeper_url": f"{base_url}/investigations/{investigation_id}",
        }
        if evidence:
            custom_details["evidence_summary"] = (
                "; ".join(str(e) for e in evidence[:5])
            )
        if confidence is not None:
            custom_details["confidence"] = confidence

        return {
            "summary": summary,
            "severity": _map_severity(severity),
            "source": service,
            "component": "beeper-investigator",
            "class": "investigation",
            "custom_details": custom_details,
        }

    @staticmethod
    def map_event_type(event_type: str) -> str:
        """Map a Beeper event_type to a PagerDuty event_action.

        Args:
            event_type: Beeper outbox event type string.

        Returns:
            PagerDuty action: 'trigger', 'acknowledge', or 'resolve'.
        """
        if event_type in _ACKNOWLEDGE_EVENT_TYPES:
            return "acknowledge"
        if event_type in _RESOLVE_EVENT_TYPES:
            return "resolve"
        return "trigger"


def _map_severity(severity: str) -> str:
    """Map Beeper severity to PagerDuty severity.

    Args:
        severity: Beeper severity (critical/high/medium/low).

    Returns:
        PagerDuty severity (critical/error/warning/info).
    """
    return _SEVERITY_MAP.get(severity.lower(), "info")


def _truncate_summary(text: str, max_length: int) -> str:
    """Truncate summary to PagerDuty's max length.

    Args:
        text: Summary text.
        max_length: Maximum allowed length.

    Returns:
        Truncated text with '...' suffix if needed.
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
