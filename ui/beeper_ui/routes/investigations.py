"""Investigation routes for Beeper UI."""

import logging
import re
import time
from collections.abc import Generator
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    render_template,
    request,
    stream_with_context,
)

from beeper_ui.services.investigation_service import (
    Investigation,
    InvestigationDetail,
    InvestigationService,
    InvestigationServiceError,
)
from beeper_ui.services.kb_service import KBEntry, KBService, KBServiceError

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


# Pipeline step definitions for timeline display
PIPELINE_STEPS = [
    {
        "key": "customer_impact",
        "label": "Customer Impact Assessment",
        "message": "Assessing customer impact",
    },
    {
        "key": "kb_query",
        "label": "Knowledge Base Query",
        "message": "Querying knowledge base",
    },
    {
        "key": "signal_correlation",
        "label": "Signal Correlation",
        "message": "Correlating signals across architectural layers",
    },
    {
        "key": "rca_hypothesis",
        "label": "Root Cause Hypothesis",
        "message": "Generating root cause hypothesis",
    },
    {
        "key": "resolution_recommendation",
        "label": "Resolution Recommendations",
        "message": "Generating resolution recommendations",
    },
    {
        "key": "documentation",
        "label": "Documentation",
        "message": "Documenting investigation findings",
    },
]


def _get_step_states(
    message: str | None, phase: str | None
) -> list[dict[str, str]]:
    """Map current status message/phase to step timeline states.

    Returns list of step dicts with 'key', 'label', and 'state' fields.
    State is one of: 'completed', 'active', 'pending', 'error'.
    """
    steps = []
    active_found = False

    if phase == "completed":
        return [
            {**step, "state": "completed"} for step in PIPELINE_STEPS
        ]

    if phase == "failed":
        # Show all steps up to the failing one as completed, current as error
        for step in PIPELINE_STEPS:
            if not active_found and message and step["message"] in message:
                steps.append({**step, "state": "error"})
                active_found = True
            elif active_found:
                steps.append({**step, "state": "pending"})
            else:
                steps.append({**step, "state": "completed"})
        if not active_found:
            # No matching step — show all as pending
            return [{**step, "state": "pending"} for step in PIPELINE_STEPS]
        return steps

    # Running / Pending — find active step from message
    for step in PIPELINE_STEPS:
        if not active_found:
            if message and step["message"] in message:
                steps.append({**step, "state": "active"})
                active_found = True
            else:
                # Steps before active are completed (if active is later)
                steps.append({**step, "state": "pending"})
        else:
            steps.append({**step, "state": "pending"})

    if active_found:
        # Mark all steps before the active step as completed
        active_idx = next(
            i for i, s in enumerate(steps) if s["state"] == "active"
        )
        for i in range(active_idx):
            steps[i]["state"] = "completed"

    return steps


@investigations_bp.route("/<investigation_id>")
def investigation_detail(investigation_id: str) -> str | tuple[str, int]:
    """Display investigation detail pane with real-time updates.

    For HTMX requests, returns partial HTML.
    For full page requests, returns the complete page.
    """
    if not SERVICE_NAME_PATTERN.match(investigation_id):
        abort(404)

    svc = get_investigation_service()
    error_message: str | None = None
    investigation: InvestigationDetail | None = None
    findings: dict[str, object] = {}
    step_states: list[dict[str, str]] = []

    try:
        investigation = svc.get_investigation(investigation_id)
        if investigation is None:
            if request.headers.get("HX-Request"):
                return render_template(
                    "investigations/_detail_not_found.html",
                    investigation_id=investigation_id,
                ), 404
            return render_template(
                "investigations/detail.html",
                investigation=None,
                investigation_id=investigation_id,
                error_message="Investigation not found.",
                findings={},
                step_states=[],
            ), 404

        findings = svc.get_investigation_findings(investigation_id)
        step_states = _get_step_states(investigation.message, investigation.status)
    except InvestigationServiceError:
        error_message = "Unable to connect to the Beeper operator."

    if request.headers.get("HX-Request"):
        return render_template(
            "investigations/_detail_content.html",
            investigation=investigation,
            findings=findings,
            step_states=step_states,
            error_message=error_message,
        )

    return render_template(
        "investigations/detail.html",
        investigation=investigation,
        investigation_id=investigation_id,
        findings=findings,
        step_states=step_states,
        error_message=error_message,
    )


@investigations_bp.route("/<investigation_id>/related-kb")
def investigation_related_kb(investigation_id: str) -> str:
    """Fetch related KB entries for an investigation.

    Uses the investigation's service name to find KB entries
    and highlights exact matches from the investigation findings.
    Returns a partial HTML template for HTMX lazy-loading.
    """
    if not SERVICE_NAME_PATTERN.match(investigation_id):
        abort(404)

    svc = get_investigation_service()
    related_entries: list[KBEntry] = []
    exact_match_entry: KBEntry | None = None
    exact_match_found = False
    exact_match_id: str | None = None

    try:
        investigation = svc.get_investigation(investigation_id)
        if investigation is None:
            return render_template(
                "investigations/_related_kb.html",
                related_entries=[],
                exact_match_entry=None,
                exact_match_found=False,
            )

        findings = svc.get_investigation_findings(investigation_id)
        exact_match_found = bool(findings.get("exact_match_found"))
        exact_match_id = str(findings.get("exact_match_id", "")) or None

        # Fetch related KB entries by service
        kb_svc = KBService()
        try:
            related_entries = kb_svc.list_entries_by_service(
                investigation.service, limit=10
            )
            # Fetch exact match entry if available
            if exact_match_id:
                exact_match_entry = kb_svc.get_entry(exact_match_id)
        except KBServiceError:
            logger.warning(
                "Failed to fetch KB entries for investigation %s",
                investigation_id,
            )
    except InvestigationServiceError:
        logger.warning(
            "Failed to fetch investigation %s for related KB",
            investigation_id,
        )

    return render_template(
        "investigations/_related_kb.html",
        related_entries=related_entries,
        exact_match_entry=exact_match_entry,
        exact_match_found=exact_match_found,
    )


def _generate_detail_sse_events(
    operator_url: str,
    operator_timeout: float,
    investigation_id: str,
) -> Generator[str, None, None]:
    """Generate SSE events for a single investigation's progress.

    Polls operator for status changes and Qdrant for new findings.
    Sends rendered HTML partials for HTMX swap.
    """
    svc = InvestigationService(
        operator_url=operator_url,
        timeout=operator_timeout,
    )
    last_message: str | None = None
    last_phase: str | None = None
    last_findings_keys: set[str] = set()
    kb_update_sent = False

    while True:
        try:
            detail = svc.get_investigation(investigation_id)
            if detail is None:
                yield "event: investigation-complete\ndata: not-found\n\n"
                svc.close()
                return

            current_message = detail.message
            current_phase = detail.status

            # Check for step/phase changes
            if current_message != last_message or current_phase != last_phase:
                step_states = _get_step_states(current_message, current_phase)
                html = render_template(
                    "investigations/_step_progress.html",
                    step_states=step_states,
                    investigation=detail,
                )
                data_lines = "\n".join(
                    f"data: {line}" for line in html.split("\n")
                )
                yield f"event: step-update\n{data_lines}\n\n"
                last_message = current_message
                last_phase = current_phase

            # Check for new findings in Qdrant
            findings = svc.get_investigation_findings(investigation_id)
            current_keys = set(findings.keys())
            if findings and current_keys != last_findings_keys:
                html = render_template(
                    "investigations/_findings.html",
                    findings=findings,
                )
                data_lines = "\n".join(
                    f"data: {line}" for line in html.split("\n")
                )
                yield f"event: findings-update\n{data_lines}\n\n"

                # Also update evidence panels
                evidence_html = render_template(
                    "investigations/_evidence_panel.html",
                    findings=findings,
                )
                evidence_lines = "\n".join(
                    f"data: {line}" for line in evidence_html.split("\n")
                )
                yield f"event: evidence-update\n{evidence_lines}\n\n"

                # Send kb-update when KB query data first appears
                if (
                    not kb_update_sent
                    and "prior_research_summary" in current_keys
                ):
                    kb_svc = KBService()
                    try:
                        related_entries = kb_svc.list_entries_by_service(
                            detail.service, limit=10
                        )
                        exact_match_id = (
                            str(findings.get("exact_match_id", "")) or None
                        )
                        exact_match_entry = None
                        if exact_match_id:
                            exact_match_entry = kb_svc.get_entry(
                                exact_match_id
                            )
                        kb_html = render_template(
                            "investigations/_related_kb.html",
                            related_entries=related_entries,
                            exact_match_entry=exact_match_entry,
                            exact_match_found=bool(
                                findings.get("exact_match_found")
                            ),
                        )
                        kb_lines = "\n".join(
                            f"data: {line}"
                            for line in kb_html.split("\n")
                        )
                        yield f"event: kb-update\n{kb_lines}\n\n"
                    except KBServiceError:
                        logger.warning(
                            "SSE: Failed to fetch KB entries for %s",
                            investigation_id,
                        )
                    kb_update_sent = True

                last_findings_keys = current_keys

            # Send completion event
            if current_phase == "completed":
                yield "event: investigation-complete\ndata: done\n\n"
                svc.close()
                return

        except InvestigationServiceError:
            logger.warning(
                "SSE: Failed to poll operator for investigation %s",
                investigation_id,
            )
        except GeneratorExit:
            svc.close()
            return

        time.sleep(SSE_POLL_INTERVAL)


@investigations_bp.route("/<investigation_id>/stream")
def investigation_detail_stream(investigation_id: str) -> Response:
    """SSE endpoint for real-time investigation detail updates.

    Polls the operator API every 3 seconds for a single investigation,
    sends events when status.message or phase changes.
    """
    if not SERVICE_NAME_PATTERN.match(investigation_id):
        abort(404)

    operator_url: str = current_app.config["OPERATOR_URL"]
    operator_timeout: float = current_app.config["OPERATOR_TIMEOUT"]
    return Response(
        stream_with_context(
            _generate_detail_sse_events(
                operator_url, operator_timeout, investigation_id
            )
        ),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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
