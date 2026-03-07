"""Investigation routes for Beeper UI."""

import json
import logging
import time
from collections.abc import Generator

from flask import Blueprint, Response, current_app, render_template, request

from beeper_ui.services.investigation_service import (
    Investigation,
    InvestigationService,
    InvestigationServiceError,
)

logger = logging.getLogger(__name__)

investigations_bp = Blueprint("investigations", __name__, url_prefix="/investigations")

# Valid filter values (security: prevent arbitrary values)
VALID_STATUSES = {"investigating", "awaiting_confirmation", "completed", "failed"}
VALID_SEVERITIES = {"low", "medium", "high", "critical"}

# SSE polling interval in seconds
SSE_POLL_INTERVAL = 3


def validate_status(status: str | None) -> str | None:
    """Validate status filter against known values."""
    if not status:
        return None
    return status if status in VALID_STATUSES else None


def validate_severity(severity: str | None) -> str | None:
    """Validate severity filter against known values."""
    if not severity:
        return None
    return severity if severity in VALID_SEVERITIES else None


def get_investigation_service() -> InvestigationService:
    """Get configured InvestigationService instance."""
    return InvestigationService(
        operator_url=current_app.config["OPERATOR_URL"],
        timeout=current_app.config["OPERATOR_TIMEOUT"],
    )


@investigations_bp.route("/")
def list_investigations() -> str:
    """Display list of all investigations.

    Supports optional query parameters:
    - status: Filter by status (investigating, awaiting_confirmation, completed, failed)
    - service: Filter by service name
    - severity: Filter by severity (low, medium, high, critical)

    For HTMX requests (filtering/SSE updates), returns only the list content partial.
    For full page requests, returns the complete page.
    """
    status = validate_status(request.args.get("status"))
    service = request.args.get("service")
    severity = validate_severity(request.args.get("severity"))

    svc = get_investigation_service()
    error_message: str | None = None
    investigations: list[Investigation] = []

    try:
        investigations = svc.list_investigations(
            status=status,
            service=service,
            severity=severity,
        )
    except InvestigationServiceError as e:
        error_message = str(e)

    # Calculate if any filter is active
    any_filter_active = bool(status or service or severity)

    # Check if this is an HTMX request (for partial updates)
    if request.headers.get("HX-Request"):
        return render_template(
            "investigations/_list_content.html",
            investigations=investigations,
            error_message=error_message,
        )

    return render_template(
        "investigations/list.html",
        investigations=investigations,
        error_message=error_message,
        selected_status=status,
        selected_service=service,
        selected_severity=severity,
        any_filter_active=any_filter_active,
    )


def _investigation_fingerprint(investigations: list[Investigation]) -> str:
    """Create a fingerprint of the investigation list for change detection."""
    return "|".join(f"{inv.id}:{inv.status}" for inv in investigations)


def _generate_sse_events() -> Generator[str, None, None]:
    """Generate SSE events by polling the operator API."""
    svc = InvestigationService(
        operator_url=current_app.config["OPERATOR_URL"],
        timeout=current_app.config["OPERATOR_TIMEOUT"],
    )
    last_fingerprint = ""

    while True:
        try:
            investigations = svc.list_investigations()
            current_fingerprint = _investigation_fingerprint(investigations)

            if current_fingerprint != last_fingerprint:
                # Determine event type
                if not last_fingerprint:
                    event_type = "investigation-update"
                elif len(current_fingerprint.split("|")) > len(
                    last_fingerprint.split("|")
                ):
                    event_type = "investigation-new"
                else:
                    event_type = "investigation-update"

                data = json.dumps(
                    [
                        {
                            "id": inv.id,
                            "status": inv.status,
                            "service": inv.service,
                            "severity": inv.severity,
                            "condition": inv.condition,
                            "started_at": inv.started_at,
                            "completed_at": inv.completed_at,
                            "triggered_at": inv.triggered_at,
                        }
                        for inv in investigations
                    ]
                )
                yield f"event: {event_type}\ndata: {data}\n\n"
                last_fingerprint = current_fingerprint

        except InvestigationServiceError:
            logger.warning("SSE: Failed to poll operator for investigations")
        except GeneratorExit:
            svc.close()
            return

        time.sleep(SSE_POLL_INTERVAL)


@investigations_bp.route("/stream")
def investigation_stream() -> Response:
    """SSE endpoint for real-time investigation updates.

    Polls the operator API every 3 seconds and only pushes events
    when the investigation list changes.
    """
    return Response(
        _generate_sse_events(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
