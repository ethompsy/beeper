"""Investigation routes for Beeper UI."""

import logging
import re
import time
from collections.abc import Generator
from datetime import datetime, timedelta, timezone

from flask import Blueprint, Response, current_app, render_template, request, stream_with_context

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
VALID_DATE_RANGES = {"today", "7d", "30d", "90d"}

# Service name validation: alphanumeric, hyphens, underscores, dots (max 128 chars)
SERVICE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{1,128}$")

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


def validate_service(service: str | None) -> str | None:
    """Validate service name filter."""
    if not service:
        return None
    return service if SERVICE_NAME_PATTERN.match(service) else None


def validate_date_range(date_range: str | None) -> str | None:
    """Validate date range filter against known values."""
    if not date_range:
        return None
    return date_range if date_range in VALID_DATE_RANGES else None


def parse_date_range(date_range: str | None) -> datetime | None:
    """Parse date range string into a cutoff datetime.

    Args:
        date_range: Date range string (e.g., 'today', '7d', '30d', '90d')

    Returns:
        Cutoff datetime (investigations started after this are included),
        or None for no date filtering.
    """
    if not date_range:
        return None

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if date_range == "today":
        return today_start
    elif date_range == "7d":
        return today_start - timedelta(days=7)
    elif date_range == "30d":
        return today_start - timedelta(days=30)
    elif date_range == "90d":
        return today_start - timedelta(days=90)
    return None


def filter_by_date_range(
    investigations: list[Investigation], cutoff: datetime
) -> list[Investigation]:
    """Filter investigations by date range cutoff.

    Compares started_at (or triggered_at as fallback) against the cutoff.
    """
    filtered = []
    for inv in investigations:
        timestamp = inv.started_at or inv.triggered_at
        if not timestamp:
            continue
        try:
            inv_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if inv_dt >= cutoff:
                filtered.append(inv)
        except (ValueError, AttributeError):
            # Include investigation if timestamp is unparseable
            filtered.append(inv)
    return filtered


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
    - date_range: Filter by time window (today, 7d, 30d, 90d)

    For HTMX requests (filtering/SSE updates), returns only the list content partial.
    For full page requests, returns the complete page.
    """
    status = validate_status(request.args.get("status"))
    service = validate_service(request.args.get("service"))
    severity = validate_severity(request.args.get("severity"))
    date_range = validate_date_range(request.args.get("date_range"))

    svc = get_investigation_service()
    error_message: str | None = None
    investigations: list[Investigation] = []

    try:
        investigations = svc.list_investigations(
            status=status,
            service=service,
            severity=severity,
        )
        # Apply client-side date range filtering
        cutoff = parse_date_range(date_range)
        if cutoff:
            investigations = filter_by_date_range(investigations, cutoff)
    except InvestigationServiceError:
        error_message = "Unable to connect to the Beeper operator."

    # Calculate if any filter is active
    any_filter_active = bool(status or service or severity or date_range)

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
        selected_date_range=date_range,
        any_filter_active=any_filter_active,
    )


def _investigation_fingerprint(investigations: list[Investigation]) -> str:
    """Create a fingerprint of the investigation list for change detection."""
    return "|".join(f"{inv.id}:{inv.status}" for inv in investigations)


def _generate_sse_events(
    operator_url: str, operator_timeout: float
) -> Generator[str, None, None]:
    """Generate SSE events by polling the operator API.

    Renders HTML partials for HTMX SSE swap integration.
    """
    svc = InvestigationService(
        operator_url=operator_url,
        timeout=operator_timeout,
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

                # Render HTML partial for HTMX swap
                html = render_template(
                    "investigations/_list_content.html",
                    investigations=investigations,
                    error_message=None,
                )
                # Format for SSE: prefix each line with "data: "
                data_lines = "\n".join(
                    f"data: {line}" for line in html.split("\n")
                )
                yield f"event: {event_type}\n{data_lines}\n\n"
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
    when the investigation list changes. Sends rendered HTML partials
    for direct HTMX swap.
    """
    # Capture config before entering generator
    operator_url: str = current_app.config["OPERATOR_URL"]
    operator_timeout: float = current_app.config["OPERATOR_TIMEOUT"]
    return Response(
        stream_with_context(
            _generate_sse_events(operator_url, operator_timeout)
        ),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
