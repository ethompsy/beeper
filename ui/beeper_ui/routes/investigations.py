"""Investigation routes for Beeper UI."""

import logging
import os
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

from beeper_ui.middleware.permissions import require_role
from beeper_ui.services.collaboration_service import get_collaboration_service
from beeper_ui.services.confidence_gate_service import (
    ConfidenceGateError,
    ConfidenceGateService,
    format_gate_message,
    normalize_confidence_score,
)
from beeper_ui.services.escalation_urgency_service import (
    EscalationUrgencyError,
    EscalationUrgencyService,
    UrgencyScore,
)
from beeper_ui.services.evidence_service import get_evidence_service
from beeper_ui.services.investigation_service import (
    Investigation,
    InvestigationDetail,
    InvestigationService,
    InvestigationServiceError,
    compute_remediation_status,
)
from beeper_ui.services.kb_service import KBEntry, KBServiceError
from beeper_ui.services.kb_surfacing_service import KBSurfacingService
from beeper_ui.services.notification_audit_service import NotificationAuditService
from beeper_ui.services.slo_service import SloService, SloServiceError

logger = logging.getLogger(__name__)

investigations_bp = Blueprint("investigations", __name__, url_prefix="/investigations")

# Valid filter values (security: prevent arbitrary values)
VALID_STATUSES = {"investigating", "awaiting_confirmation", "completed", "failed"}
VALID_WORKFLOW_STATES = {"detected", "investigating", "resolved", "verified", "failed"}
VALID_SEVERITIES = {"low", "medium", "high", "critical"}
VALID_DATE_RANGES = {"today", "7d", "30d", "90d"}

# Service name validation: alphanumeric, hyphens, underscores, dots (max 128 chars)
SERVICE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{1,128}$")

# Valid resolution outcomes
VALID_OUTCOMES = {"resolved", "not_an_issue", "escalated", "unresolved"}

# Valid Beeper accuracy ratings
VALID_ACCURACY_RATINGS = {"correct", "partially_correct", "incorrect"}

# Valid not-an-issue reasons
VALID_NOT_AN_ISSUE_REASONS = {"false_positive", "expected_behavior", "transient", "other"}

# Human-readable outcome labels
OUTCOME_LABELS = {
    "resolved": "Resolved",
    "not_an_issue": "Not an Issue",
    "escalated": "Escalated",
    "unresolved": "Unresolved",
}

# Human-readable accuracy rating labels
ACCURACY_LABELS = {
    "correct": "Correct",
    "partially_correct": "Partially correct",
    "incorrect": "Incorrect",
}

# Human-readable not-an-issue reason labels
NOT_AN_ISSUE_LABELS = {
    "false_positive": "False positive",
    "expected_behavior": "Expected behavior",
    "transient": "Transient",
    "other": "Other",
}

# Valid rejection reason categories
VALID_REJECTION_REASONS = {
    "hypothesis_incorrect",
    "insufficient_evidence",
    "better_alternative",
    "not_applicable",
    "other",
}

# Human-readable rejection reason labels
REJECTION_REASON_LABELS = {
    "hypothesis_incorrect": "Hypothesis incorrect",
    "insufficient_evidence": "Insufficient evidence",
    "better_alternative": "Better alternative exists",
    "not_applicable": "Not applicable",
    "other": "Other",
}

# Valid one-click investigation feedback types
VALID_FEEDBACK_TYPES = {"accurate", "inaccurate", "not_an_issue"}

# Human-readable feedback type labels
FEEDBACK_TYPE_LABELS = {
    "accurate": "Accurate",
    "inaccurate": "Inaccurate",
    "not_an_issue": "Not an Issue",
}

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


def _get_slo_service() -> SloService:
    """Get configured SloService instance."""
    return SloService(
        operator_url=current_app.config["OPERATOR_URL"],
        timeout=current_app.config.get("OPERATOR_TIMEOUT", 5.0),
    )


def _get_urgency_service() -> EscalationUrgencyService:
    """Get configured EscalationUrgencyService instance."""
    return EscalationUrgencyService(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )


# Valid sort options
VALID_SORTS = {"urgency"}


@investigations_bp.route("/")
def list_investigations() -> str:
    """Display list of all investigations.

    Supports optional query parameters:
    - status: Filter by status (investigating, awaiting_confirmation, completed, failed)
    - service: Filter by service name
    - severity: Filter by severity (low, medium, high, critical)
    - date_range: Filter by time window (today, 7d, 30d, 90d)
    - sort: Sort by urgency score descending (sort=urgency)

    For HTMX requests (filtering/SSE updates), returns only the list content partial.
    For full page requests, returns the complete page.
    """
    status = validate_status(request.args.get("status"))
    service = validate_service(request.args.get("service"))
    severity = validate_severity(request.args.get("severity"))
    date_range = validate_date_range(request.args.get("date_range"))
    sort_by = request.args.get("sort", "")
    if sort_by not in VALID_SORTS:
        sort_by = ""
    workflow_state_filter = request.args.get("workflow_state", "")
    if workflow_state_filter and workflow_state_filter not in VALID_WORKFLOW_STATES:
        workflow_state_filter = ""
    group_by = request.args.get("group_by", "")
    if group_by not in ("", "workflow_state"):
        group_by = ""

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

    # Compute workflow state counts (before filtering by workflow_state)
    workflow_state_counts: dict[str, int] = {}
    for inv in investigations:
        ws = inv.workflow_state or "unknown"
        workflow_state_counts[ws] = workflow_state_counts.get(ws, 0) + 1

    # Apply workflow state filter (after counting)
    if workflow_state_filter:
        investigations = [
            inv
            for inv in investigations
            if inv.workflow_state == workflow_state_filter
        ]

    # Compute urgency scores for all investigations
    urgency_scores: dict[str, UrgencyScore] = {}
    if investigations:
        slo_svc = _get_slo_service()
        urgency_svc = _get_urgency_service()
        try:
            # Fetch SLO budgets per unique service
            services = {inv.service for inv in investigations}
            slo_budgets: dict[str, dict[str, object] | None] = {}
            for svc_name in services:
                try:
                    slo_budgets[svc_name] = slo_svc.get_service_budget(
                        svc_name
                    )
                except SloServiceError:
                    slo_budgets[svc_name] = None

            # Fetch findings per investigation for customer_impacting
            findings_map: dict[str, dict[str, object]] = {}
            for inv in investigations:
                try:
                    findings_map[inv.id] = svc.get_investigation_findings(
                        inv.id
                    )
                except Exception:
                    logger.warning(
                        "Failed to fetch findings for %s, using empty",
                        inv.id,
                    )
                    findings_map[inv.id] = {}

            urgency_scores = urgency_svc.compute_batch_urgency(
                investigations, slo_budgets, findings_map
            )
        except EscalationUrgencyError:
            logger.warning("Failed to compute urgency scores, degrading gracefully")
        finally:
            slo_svc.close()
            urgency_svc.close()

        # Compute remediation status from already-fetched findings
        for inv in investigations:
            if inv.workflow_state in ("investigating", "resolved"):
                inv.remediation_status = compute_remediation_status(
                    findings_map.get(inv.id, {})
                )

    # Sort by urgency if requested
    if sort_by == "urgency" and urgency_scores:
        investigations.sort(
            key=lambda inv: urgency_scores.get(
                inv.id, UrgencyScore.default()
            ).score,
            reverse=True,
        )

    # Calculate if any filter is active
    any_filter_active = bool(status or service or severity or date_range or workflow_state_filter)

    # Group investigations by workflow state if requested
    grouped_investigations: dict[str, list[Investigation]] = {}
    if group_by == "workflow_state":
        for inv in investigations:
            key = inv.workflow_state or "unknown"
            grouped_investigations.setdefault(key, []).append(inv)

    # Check if this is an HTMX request (for partial updates)
    if request.headers.get("HX-Request"):
        return render_template(
            "investigations/_list_content.html",
            investigations=investigations,
            urgency_scores=urgency_scores,
            error_message=error_message,
            workflow_state_counts=workflow_state_counts,
            group_by=group_by,
            grouped_investigations=grouped_investigations,
        )

    return render_template(
        "investigations/list.html",
        investigations=investigations,
        urgency_scores=urgency_scores,
        error_message=error_message,
        selected_status=status,
        selected_service=service,
        selected_severity=severity,
        selected_date_range=date_range,
        selected_sort=sort_by,
        selected_workflow_state=workflow_state_filter,
        workflow_state_counts=workflow_state_counts,
        any_filter_active=any_filter_active,
        group_by=group_by,
        grouped_investigations=grouped_investigations,
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

    # Extract timeline events (includes evidence extraction + KB enrichment internally)
    timeline_events = []
    if findings:
        ev_svc = get_evidence_service()
        timeline_events = ev_svc.get_timeline_events(investigation_id, findings)

    # Extract deploy correlation data from pipeline findings
    deploy_correlations = findings.get("deploy_correlations", []) if findings else []
    deploy_summary = findings.get("deploy_summary", "") if findings else ""

    # Extract service topology data from pipeline findings
    service_topology = findings.get("service_topology", {}) if findings else {}

    # Extract change event correlation data from pipeline findings
    change_events = findings.get("change_events", []) if findings else []
    change_summary = findings.get("change_summary", "") if findings else ""

    # Retrieve human interventions (annotations & redirects) from collaboration history
    human_interventions = []
    try:
        collab_svc = get_collaboration_service()
        all_messages = collab_svc.get_message_history(investigation_id)
        human_interventions = [
            msg.to_payload()
            for msg in all_messages
            if msg.message_type in ("annotation", "redirect")
        ]
    except Exception:
        logger.warning(
            "Failed to fetch human interventions for %s",
            investigation_id,
            exc_info=True,
        )

    if request.headers.get("HX-Request"):
        return render_template(
            "investigations/_detail_content.html",
            investigation=investigation,
            findings=findings,
            step_states=step_states,
            error_message=error_message,
            timeline_events=timeline_events,
            deploy_correlations=deploy_correlations,
            deploy_summary=deploy_summary,
            service_topology=service_topology,
            change_events=change_events,
            change_summary=change_summary,
            human_interventions=human_interventions,
        )

    return render_template(
        "investigations/detail.html",
        investigation=investigation,
        investigation_id=investigation_id,
        findings=findings,
        step_states=step_states,
        error_message=error_message,
        timeline_events=timeline_events,
        deploy_correlations=deploy_correlations,
        deploy_summary=deploy_summary,
        service_topology=service_topology,
        change_events=change_events,
        change_summary=change_summary,
        human_interventions=human_interventions,
    )


@investigations_bp.route("/<investigation_id>/related-kb")
def investigation_related_kb(investigation_id: str) -> str:
    """Fetch related KB entries for an investigation using semantic search.

    Uses KB semantic search to find relevant entries ranked by composite
    score (relevance * validation weight). Falls back to service-based
    listing if semantic search is unavailable.
    Returns a partial HTML template for HTMX lazy-loading.
    """
    if not SERVICE_NAME_PATTERN.match(investigation_id):
        abort(404)

    svc = get_investigation_service()
    surfacing_result = None
    exact_match_entry: KBEntry | None = None
    exact_match_found = False

    try:
        investigation = svc.get_investigation(investigation_id)
        if investigation is None:
            return render_template(
                "investigations/_related_kb.html",
                surfacing_result=None,
                exact_match_entry=None,
                exact_match_found=False,
            )

        findings = svc.get_investigation_findings(investigation_id)
        exact_match_found = bool(findings.get("exact_match_found"))
        exact_match_id = str(findings.get("exact_match_id", "")) or None

        # Use semantic search for KB surfacing
        surfacing_svc = KBSurfacingService()
        try:
            surfacing_result = surfacing_svc.surface_entries(
                investigation_id, findings
            )
            # Fetch exact match entry if available
            if exact_match_id:
                exact_match_entry = surfacing_svc.kb_service.get_entry(
                    exact_match_id
                )
            # Mark novel investigations for future KB creation
            if surfacing_result.is_novel:
                surfacing_svc.mark_novel_investigation(investigation_id)
        except Exception:
            logger.warning(
                "Failed to surface KB entries for investigation %s",
                investigation_id,
                exc_info=True,
            )
        finally:
            surfacing_svc.close()
    except InvestigationServiceError:
        logger.warning(
            "Failed to fetch investigation %s for related KB",
            investigation_id,
        )

    return render_template(
        "investigations/_related_kb.html",
        surfacing_result=surfacing_result,
        exact_match_entry=exact_match_entry,
        exact_match_found=exact_match_found,
    )


@investigations_bp.route("/<investigation_id>/linked-kb")
def investigation_linked_kb(investigation_id: str) -> str:
    """Fetch KB entries created by this investigation.

    Returns entries where source_investigation_id matches, showing
    the bi-directional "Knowledge Created" link.
    """
    if not SERVICE_NAME_PATTERN.match(investigation_id):
        abort(404)

    from beeper_ui.services.kb_service import KBService

    kb_svc = KBService(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )
    linked_kb_entries = kb_svc.get_linked_kb_entries(investigation_id)

    return render_template(
        "investigations/_linked_kb.html",
        linked_kb_entries=linked_kb_entries,
    )


@investigations_bp.route("/<investigation_id>/gate-status")
def investigation_gate_status(investigation_id: str) -> str:
    """Evaluate and return confidence gate status for an investigation.

    Returns HTMX partial showing gate decision for the investigation's
    service and confidence score.
    """
    if not SERVICE_NAME_PATTERN.match(investigation_id):
        abort(404)

    svc = get_investigation_service()
    gate_decision = None
    gate_message = ""
    gate_error = False

    try:
        investigation = svc.get_investigation(investigation_id)
        if investigation is None:
            return render_template(
                "investigations/_confidence_gate.html",
                gate_decision=None,
                gate_message="",
                gate_error=False,
                investigation_id=investigation_id,
            )

        findings = svc.get_investigation_findings(investigation_id)
        confidence_score = normalize_confidence_score(findings)

        gate_svc = ConfidenceGateService(
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", "6333")),
        )
        try:
            gate_decision = gate_svc.evaluate_gate(
                service_name=investigation.service,
                confidence_score=confidence_score,
            )
            gate_message = format_gate_message(gate_decision)
        except ConfidenceGateError as e:
            logger.warning("Failed to evaluate confidence gate: %s", e)
            gate_error = True
        except Exception as e:
            logger.warning("Unexpected error evaluating confidence gate: %s", e)
            gate_error = True
        finally:
            gate_svc.close()
    except InvestigationServiceError:
        gate_error = True

    return render_template(
        "investigations/_confidence_gate.html",
        gate_decision=gate_decision,
        gate_message=gate_message,
        gate_error=gate_error,
        investigation_id=investigation_id,
    )


@investigations_bp.route("/<investigation_id>/urgency")
def investigation_urgency(investigation_id: str) -> str:
    """Compute and return escalation urgency for an investigation.

    Returns HTMX partial showing the impact-weighted urgency score
    with factor breakdown and confidence assessment.
    """
    if not SERVICE_NAME_PATTERN.match(investigation_id):
        abort(404)

    svc = get_investigation_service()
    urgency: UrgencyScore | None = None
    error_message: str | None = None

    try:
        investigation = svc.get_investigation(investigation_id)
        if investigation is None:
            return render_template(
                "investigations/_urgency_card.html",
                urgency=None,
                error_message="Investigation not found.",
            )

        findings = svc.get_investigation_findings(investigation_id)
        customer_impacting = bool(findings.get("customer_impacting", False))

        # Fetch SLO budget for this service
        slo_svc = _get_slo_service()
        burn_rate = None
        budget_remaining = None
        try:
            budget = slo_svc.get_service_budget(investigation.service)
            if budget:
                burn_rate = budget.get("burn_rate")
                budget_remaining = budget.get("budget_remaining")
        except SloServiceError:
            logger.warning(
                "Failed to fetch SLO data for %s", investigation.service
            )
        finally:
            slo_svc.close()

        # Compute urgency score
        urgency_svc = _get_urgency_service()
        try:
            accuracy_data = urgency_svc.get_service_accuracy_rate(
                investigation.service
            )
            urgency = urgency_svc.calculate_urgency(
                investigation_id=investigation_id,
                service_name=investigation.service,
                severity=investigation.severity,
                burn_rate=burn_rate,
                budget_remaining=budget_remaining,
                customer_impacting=customer_impacting,
                accuracy_data=accuracy_data,
            )
        except EscalationUrgencyError as e:
            logger.warning("Failed to compute urgency: %s", e)
            error_message = "Unable to compute urgency score."
        finally:
            urgency_svc.close()
    except InvestigationServiceError:
        error_message = "Unable to connect to the Beeper operator."
    finally:
        svc.close()

    return render_template(
        "investigations/_urgency_card.html",
        urgency=urgency,
        error_message=error_message,
    )


@investigations_bp.route("/<investigation_id>/remediation-progress")
def investigation_remediation_progress(investigation_id: str) -> str:
    """Return remediation progress tracker partial for an investigation.

    Returns HTMX partial showing the remediation pipeline stages.
    """
    if not SERVICE_NAME_PATTERN.match(investigation_id):
        abort(404)

    svc = get_investigation_service()
    try:
        remediation_status = svc.get_remediation_progress(investigation_id)
    except Exception:
        logger.warning("Failed to get remediation progress for %s", investigation_id)
        remediation_status = None
    finally:
        svc.close()

    return render_template(
        "investigations/_remediation_progress.html",
        remediation_status=remediation_status,
        investigation_id=investigation_id,
    )


@investigations_bp.route("/<investigation_id>/confirm", methods=["POST"])
def confirm_resolution(investigation_id: str) -> str | tuple[str, int]:
    """Confirm an investigation's resolution recommendation.

    Accepts HTMX POST with optional comment, calls operator to update
    status, saves feedback to Qdrant for future learning.
    """
    if not SERVICE_NAME_PATTERN.match(investigation_id):
        abort(404)

    comment = (request.form.get("comment") or "").strip() or None

    svc = get_investigation_service()
    try:
        success = svc.confirm_resolution(investigation_id, comment=comment)
        if not success:
            return render_template(
                "investigations/_confirmation_result.html",
                action="error",
                error_message="Investigation not found.",
            ), 404

        # Save feedback to Qdrant for learning
        now = datetime.now(timezone.utc).isoformat()
        svc.save_resolution_feedback(investigation_id, {
            "resolution_action": "confirmed",
            "resolution_comment": comment,
            "resolution_confirmed_at": now,
            "resolution_confirmed_by": "sre",
        })

        return render_template(
            "investigations/_confirmation_result.html",
            action="confirmed",
            comment=comment,
            confirmed_at=now,
        )
    except InvestigationServiceError:
        return render_template(
            "investigations/_confirmation_result.html",
            action="error",
            error_message="Unable to connect to the Beeper operator.",
        ), 503
    finally:
        svc.close()


@investigations_bp.route("/<investigation_id>/verify", methods=["POST"])
@require_role("user")
def verify_investigation(investigation_id: str) -> str | tuple[str, int]:
    """Verify a resolved investigation (Resolved → Verified).

    Calls the operator verify endpoint. Returns HTMX partial on success.
    """
    if not SERVICE_NAME_PATTERN.match(investigation_id):
        abort(404)

    svc = get_investigation_service()
    try:
        success = svc.verify_investigation(investigation_id)
        if not success:
            return render_template(
                "investigations/_confirmation_result.html",
                action="error",
                error_message="Investigation not found or not in resolved state.",
            ), 404

        return render_template(
            "investigations/_confirmation_result.html",
            action="verified",
        )
    except InvestigationServiceError:
        return render_template(
            "investigations/_confirmation_result.html",
            action="error",
            error_message="Unable to connect to the Beeper operator.",
        ), 503
    finally:
        svc.close()


@investigations_bp.route("/<investigation_id>/reject", methods=["POST"])
def reject_resolution(investigation_id: str) -> str | tuple[str, int]:
    """Reject an investigation's resolution recommendation.

    Accepts HTMX POST with rejection reason (required), details (required),
    and optional correction. Calls operator and saves feedback.
    """
    if not SERVICE_NAME_PATTERN.match(investigation_id):
        abort(404)

    rejection_reason = (request.form.get("rejection_reason") or "").strip()
    reason_details = (request.form.get("reason_details") or "").strip()
    correction = (request.form.get("correction") or "").strip() or None

    # Validate rejection reason
    if rejection_reason not in VALID_REJECTION_REASONS:
        return render_template(
            "investigations/_confirmation_result.html",
            action="error",
            error_message="Invalid rejection reason. Please select a valid reason.",
        ), 400

    # Validate reason details required
    if not reason_details:
        return render_template(
            "investigations/_confirmation_result.html",
            action="error",
            error_message="Please provide details about why the recommendation is being rejected.",
        ), 400

    svc = get_investigation_service()
    try:
        success = svc.reject_resolution(
            investigation_id,
            reason=rejection_reason,
            reason_details=reason_details,
            correction=correction,
        )
        if not success:
            return render_template(
                "investigations/_confirmation_result.html",
                action="error",
                error_message="Investigation not found.",
            ), 404

        # Save feedback to Qdrant for learning
        now = datetime.now(timezone.utc).isoformat()
        svc.save_resolution_feedback(investigation_id, {
            "resolution_action": "rejected",
            "rejection_reason": rejection_reason,
            "rejection_reason_details": reason_details,
            "rejection_correction": correction,
            "resolution_rejected_at": now,
        })

        reason_label = REJECTION_REASON_LABELS.get(rejection_reason, rejection_reason)
        return render_template(
            "investigations/_confirmation_result.html",
            action="rejected",
            rejection_reason=reason_label,
            reason_details=reason_details,
            correction=correction,
            rejected_at=now,
        )
    except InvestigationServiceError:
        return render_template(
            "investigations/_confirmation_result.html",
            action="error",
            error_message="Unable to connect to the Beeper operator.",
        ), 503
    finally:
        svc.close()


def format_mttr(seconds: int | None) -> str:
    """Format MTTR seconds as human-readable duration.

    Args:
        seconds: MTTR in seconds, or None.

    Returns:
        Human-readable string like "5m", "2h 15m", "1d 3h", or "N/A".
    """
    if seconds is None:
        return "N/A"
    if seconds < 60:
        return "<1m"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m" if mins else f"{hours}h"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    return f"{days}d {hours}h" if hours else f"{days}d"


@investigations_bp.route("/<investigation_id>/resolve", methods=["POST"])
def resolve_investigation_route(investigation_id: str) -> str | tuple[str, int]:
    """Resolve an investigation with a final outcome.

    Accepts HTMX POST with outcome, accuracy rating, notes, etc.
    Calls operator, saves resolution data, updates KB, calculates MTTR.
    """
    if not SERVICE_NAME_PATTERN.match(investigation_id):
        abort(404)

    outcome = (request.form.get("outcome") or "").strip()
    accuracy_rating = (request.form.get("accuracy_rating") or "").strip() or None
    resolution_notes = (request.form.get("resolution_notes") or "").strip() or None
    escalation_target = (request.form.get("escalation_target") or "").strip() or None
    not_an_issue_reason = (request.form.get("not_an_issue_reason") or "").strip() or None

    # Validate outcome
    if outcome not in VALID_OUTCOMES:
        return render_template(
            "investigations/_resolution_result.html",
            action="error",
            error_message="Invalid resolution outcome.",
        ), 400

    # Conditional validation per outcome
    if outcome == "resolved" and accuracy_rating and accuracy_rating not in VALID_ACCURACY_RATINGS:
        return render_template(
            "investigations/_resolution_result.html",
            action="error",
            error_message="Invalid accuracy rating.",
        ), 400

    if (
        outcome == "not_an_issue"
        and not_an_issue_reason
        and not_an_issue_reason not in VALID_NOT_AN_ISSUE_REASONS
    ):
        return render_template(
            "investigations/_resolution_result.html",
            action="error",
            error_message="Invalid reason for not-an-issue.",
        ), 400

    if outcome == "escalated" and not escalation_target:
        return render_template(
            "investigations/_resolution_result.html",
            action="error",
            error_message="Please provide an escalation target.",
        ), 400

    svc = get_investigation_service()
    try:
        # Get investigation details for MTTR calculation
        investigation = svc.get_investigation(investigation_id)

        success = svc.resolve_investigation(
            investigation_id,
            outcome=outcome,
            accuracy_rating=accuracy_rating,
            resolution_notes=resolution_notes,
            escalation_target=escalation_target,
            not_an_issue_reason=not_an_issue_reason,
        )
        if not success:
            return render_template(
                "investigations/_resolution_result.html",
                action="error",
                error_message="Investigation not found.",
            ), 404

        now = datetime.now(timezone.utc).isoformat()

        # Calculate MTTR for non-escalated outcomes
        mttr_seconds: int | None = None
        if outcome != "escalated" and investigation:
            mttr_seconds = InvestigationService.calculate_mttr(
                investigation.started_at, now
            )

        # Save resolution data to Qdrant investigations collection
        resolution_feedback: dict[str, object] = {
            "resolution_outcome": outcome,
            "accuracy_rating": accuracy_rating,
            "resolution_notes": resolution_notes,
            "escalation_target": escalation_target,
            "not_an_issue_reason": not_an_issue_reason,
            "resolved_at": now,
            "mttr_seconds": mttr_seconds,
        }
        svc.save_resolution_feedback(investigation_id, resolution_feedback)

        # Flag false pages in notification audit trail
        if outcome == "not_an_issue" or accuracy_rating == "incorrect":
            try:
                false_page_reason = not_an_issue_reason or "incorrect_accuracy"
                audit_svc = NotificationAuditService()
                try:
                    audit_svc.flag_false_pages(investigation_id, false_page_reason)
                finally:
                    audit_svc.close()
            except Exception as e:
                logger.warning(
                    "False page flagging failed for %s (non-blocking): %s",
                    investigation_id,
                    e,
                )

        # Update KB entry with resolution for non-escalated
        kb_updated = False
        if outcome != "escalated":
            kb_resolution_data: dict[str, object] = {
                "resolution_outcome": outcome,
                "accuracy_rating": accuracy_rating,
                "resolution_notes": resolution_notes,
                "resolved_at": now,
                "mttr_seconds": mttr_seconds,
            }
            kb_updated = svc.update_kb_with_resolution(
                investigation_id, kb_resolution_data
            )

        outcome_label = OUTCOME_LABELS.get(outcome, outcome)
        accuracy_label = ACCURACY_LABELS.get(accuracy_rating or "", accuracy_rating)
        not_an_issue_label = NOT_AN_ISSUE_LABELS.get(
            not_an_issue_reason or "", not_an_issue_reason
        )
        mttr_display = format_mttr(mttr_seconds)

        return render_template(
            "investigations/_resolution_result.html",
            action=outcome,
            outcome_label=outcome_label,
            accuracy_rating=accuracy_rating,
            accuracy_label=accuracy_label,
            resolution_notes=resolution_notes,
            escalation_target=escalation_target,
            not_an_issue_reason=not_an_issue_reason,
            not_an_issue_label=not_an_issue_label,
            resolved_at=now,
            mttr_seconds=mttr_seconds,
            mttr_display=mttr_display,
            kb_updated=kb_updated,
        )
    except InvestigationServiceError:
        return render_template(
            "investigations/_resolution_result.html",
            action="error",
            error_message="Unable to connect to the Beeper operator.",
        ), 503
    finally:
        svc.close()


@investigations_bp.route("/<investigation_id>/feedback", methods=["POST"])
@require_role("user")
def submit_investigation_feedback(investigation_id: str) -> str | tuple[str, int]:
    """Submit one-click investigation feedback (accurate/inaccurate/not-an-issue).

    Records feedback type, user identity, and timestamp to Qdrant.
    Single click — no modal, no form, no confirmation required.
    Last feedback wins (overwrites previous).
    """
    if not SERVICE_NAME_PATTERN.match(investigation_id):
        abort(404)

    feedback_type = (request.form.get("feedback_type") or "").strip()
    if feedback_type not in VALID_FEEDBACK_TYPES:
        return render_template(
            "investigations/_feedback_result.html",
            error_message="Invalid feedback type.",
            current_feedback="",
            investigation_id=investigation_id,
        ), 400

    user = request.headers.get("X-Beeper-User", "anonymous")
    now = datetime.now(timezone.utc).isoformat()

    svc = get_investigation_service()
    try:
        svc.save_resolution_feedback(investigation_id, {
            "investigation_feedback": feedback_type,
            "investigation_feedback_by": user,
            "investigation_feedback_at": now,
        })
    except InvestigationServiceError:
        return render_template(
            "investigations/_feedback_result.html",
            error_message="Unable to save feedback. Please try again.",
            current_feedback="",
            investigation_id=investigation_id,
        ), 503
    finally:
        svc.close()

    feedback_label = FEEDBACK_TYPE_LABELS.get(feedback_type, feedback_type)
    return render_template(
        "investigations/_feedback_result.html",
        current_feedback=feedback_type,
        feedback_label=feedback_label,
        investigation_id=investigation_id,
        feedback_by=user,
        feedback_at=now,
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
    last_remediation_stage: str | None = None
    kb_update_sent = False
    last_resolution_action: str | None = None
    last_resolution_outcome: str | None = None
    last_investigation_feedback: str | None = None

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

                # Update unified investigation timeline
                try:
                    ev_svc = get_evidence_service()
                    tl_events = ev_svc.get_timeline_events(
                        investigation_id, findings
                    )
                    timeline_html = render_template(
                        "investigations/_unified_timeline.html",
                        timeline_events=tl_events,
                    )
                    timeline_lines = "\n".join(
                        f"data: {line}"
                        for line in timeline_html.split("\n")
                    )
                    yield f"event: evidence-timeline-update\n{timeline_lines}\n\n"
                except (KBServiceError, KeyError, TypeError, ValueError):
                    logger.debug(
                        "SSE: Failed to render evidence timeline for %s",
                        investigation_id,
                    )

                # Update deploy correlation card
                deploy_correlations = findings.get("deploy_correlations", [])
                deploy_summary = findings.get("deploy_summary", "")
                if deploy_correlations or deploy_summary:
                    try:
                        deploy_html = render_template(
                            "investigations/_deploy_correlation.html",
                            deploy_correlations=deploy_correlations,
                            deploy_summary=deploy_summary,
                        )
                        deploy_lines = "\n".join(
                            f"data: {line}"
                            for line in deploy_html.split("\n")
                        )
                        yield f"event: deploy-correlation-update\n{deploy_lines}\n\n"
                    except Exception:
                        logger.debug(
                            "SSE: Failed to render deploy correlation for %s",
                            investigation_id,
                        )

                # Update change events card
                change_events = findings.get("change_events", [])
                change_summary = findings.get("change_summary", "")
                if change_events or change_summary:
                    try:
                        change_html = render_template(
                            "investigations/_change_events.html",
                            change_events=change_events,
                            change_summary=change_summary,
                        )
                        change_lines = "\n".join(
                            f"data: {line}"
                            for line in change_html.split("\n")
                        )
                        yield f"event: change-events-update\n{change_lines}\n\n"
                    except Exception:
                        logger.debug(
                            "SSE: Failed to render change events for %s",
                            investigation_id,
                        )

                # Update service topology card
                service_topology = findings.get("service_topology", {})
                if service_topology and service_topology.get("subject_service"):
                    try:
                        topo_html = render_template(
                            "investigations/_service_topology.html",
                            service_topology=service_topology,
                        )
                        topo_lines = "\n".join(
                            f"data: {line}"
                            for line in topo_html.split("\n")
                        )
                        yield f"event: topology-update\n{topo_lines}\n\n"
                    except Exception:
                        logger.debug(
                            "SSE: Failed to render service topology for %s",
                            investigation_id,
                        )

                # Send kb-update when KB query data first appears
                if (
                    not kb_update_sent
                    and "prior_research_summary" in current_keys
                ):
                    surfacing_svc = KBSurfacingService()
                    try:
                        surfacing_result = surfacing_svc.surface_entries(
                            investigation_id, findings
                        )
                        exact_match_id = (
                            str(findings.get("exact_match_id", "")) or None
                        )
                        exact_match_entry = None
                        if exact_match_id:
                            exact_match_entry = (
                                surfacing_svc.kb_service.get_entry(
                                    exact_match_id
                                )
                            )
                        if surfacing_result.is_novel:
                            surfacing_svc.mark_novel_investigation(
                                investigation_id
                            )
                        kb_html = render_template(
                            "investigations/_related_kb.html",
                            surfacing_result=surfacing_result,
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
                    except Exception:
                        logger.warning(
                            "SSE: Failed to surface KB entries for %s",
                            investigation_id,
                            exc_info=True,
                        )
                    finally:
                        surfacing_svc.close()
                    kb_update_sent = True

                # Update remediation progress card (only when stage changes)
                try:
                    rem_status = compute_remediation_status(findings)
                    current_rem_stage = rem_status["stage"] if rem_status else None
                    if current_rem_stage != last_remediation_stage:
                        rem_html = render_template(
                            "investigations/_remediation_progress.html",
                            remediation_status=rem_status,
                            investigation_id=investigation_id,
                        )
                        rem_lines = "\n".join(
                            f"data: {line}"
                            for line in rem_html.split("\n")
                        )
                        yield f"event: remediation-update\n{rem_lines}\n\n"
                        last_remediation_stage = current_rem_stage
                except Exception:
                    logger.debug(
                        "SSE: Failed to render remediation progress for %s",
                        investigation_id,
                    )

                last_findings_keys = current_keys

            # Check for resolution action changes (confirm/reject)
            # Independent of findings key changes to catch value-only updates
            if findings:
                current_resolution = str(
                    findings.get("resolution_action", "")
                ) or None
                if current_resolution != last_resolution_action:
                    confirm_html = render_template(
                        "investigations/_confirmation_form.html",
                        investigation=detail,
                        findings=findings,
                    )
                    confirm_lines = "\n".join(
                        f"data: {line}"
                        for line in confirm_html.split("\n")
                    )
                    yield f"event: confirmation-update\n{confirm_lines}\n\n"
                    last_resolution_action = current_resolution

            # Check for resolution outcome changes (resolve investigation)
            if findings:
                current_outcome = str(
                    findings.get("resolution_outcome", "")
                ) or None
                if current_outcome != last_resolution_outcome:
                    resolve_html = render_template(
                        "investigations/_resolution_form.html",
                        investigation=detail,
                        findings=findings,
                    )
                    resolve_lines = "\n".join(
                        f"data: {line}"
                        for line in resolve_html.split("\n")
                    )
                    yield f"event: resolution-update\n{resolve_lines}\n\n"
                    last_resolution_outcome = current_outcome

            # Check for investigation feedback changes (one-click feedback)
            if findings:
                current_inv_feedback = str(
                    findings.get("investigation_feedback", "")
                ) or None
                if current_inv_feedback != last_investigation_feedback:
                    feedback_html = render_template(
                        "investigations/_feedback_buttons.html",
                        current_feedback=current_inv_feedback or "",
                        investigation_id=investigation_id,
                    )
                    feedback_lines = "\n".join(
                        f"data: {line}"
                        for line in feedback_html.split("\n")
                    )
                    yield f"event: feedback-update\n{feedback_lines}\n\n"
                    last_investigation_feedback = current_inv_feedback

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
                # Note: urgency_scores not computed in SSE path (too expensive
                # for every poll cycle); template handles missing data gracefully.
                html = render_template(
                    "investigations/_list_content.html",
                    investigations=investigations,
                    urgency_scores={},
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
