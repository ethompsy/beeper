"""Trust level settings UI routes.

Provides HTML pages for viewing and configuring per-service autonomy
trust levels (TL1-5) and confidence gate thresholds.
Separate from the API routes in trust_config.py and confidence_gates.py.
"""

import logging
import os
import re

from flask import Blueprint, render_template, request

from beeper_ui.middleware.permissions import require_role
from beeper_ui.services.confidence_gate_service import (
    GATED_TRUST_LEVELS,
    ConfidenceGateError,
    ConfidenceGateService,
)
from beeper_ui.services.trust_level_service import (
    MAX_TRUST_LEVEL,
    MIN_TRUST_LEVEL,
    TRUST_LEVEL_DEFINITIONS,
    TrustLevelService,
    TrustLevelServiceError,
)

logger = logging.getLogger(__name__)

trust_settings_bp = Blueprint(
    "trust_settings", __name__, url_prefix="/settings/trust"
)

_SERVICE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _get_trust_level_service() -> TrustLevelService:
    """Get configured TrustLevelService instance."""
    return TrustLevelService(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )


def _get_gate_service() -> ConfidenceGateService:
    """Get configured ConfidenceGateService instance."""
    return ConfidenceGateService(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )


@trust_settings_bp.route("/")
@require_role("user")
def trust_settings_page() -> str:
    """Display trust level configuration page."""
    service = _get_trust_level_service()
    error_message = None
    trusts = []

    try:
        trusts = service.get_all_trust_levels()
    except TrustLevelServiceError as e:
        logger.warning("Trust settings query failed: %s", e)
        error_message = "Unable to load trust level data"
    finally:
        service.close()

    if request.headers.get("HX-Request"):
        return render_template(
            "trust/_service_list.html",
            trusts=trusts,
            trust_definitions=TRUST_LEVEL_DEFINITIONS,
            error_message=error_message,
        )

    return render_template(
        "trust/settings.html",
        trusts=trusts,
        trust_definitions=TRUST_LEVEL_DEFINITIONS,
        error_message=error_message,
    )


@trust_settings_bp.route("/<service_name>/update", methods=["POST"])
@require_role("admin")
def update_trust_level(service_name: str) -> str:
    """Handle form submission to update a service's trust level."""
    # Validate service_name
    if not service_name or len(service_name) > 100 or not _SERVICE_NAME_RE.match(
        service_name
    ):
        return render_template(
            "trust/_update_result.html",
            error_message="Invalid service name",
            service_name=service_name,
        )

    level_str = request.form.get("trust_level", "")
    reason = request.form.get("reason", "").strip() or None

    try:
        level = int(level_str)
    except (ValueError, TypeError):
        return render_template(
            "trust/_update_result.html",
            error_message="Trust level must be a number",
            service_name=service_name,
        )

    if level < MIN_TRUST_LEVEL or level > MAX_TRUST_LEVEL:
        return render_template(
            "trust/_update_result.html",
            error_message=f"Trust level must be between {MIN_TRUST_LEVEL} and {MAX_TRUST_LEVEL}",
            service_name=service_name,
        )

    updated_by = request.headers.get("X-Beeper-User", "admin")

    service = _get_trust_level_service()
    try:
        config = service.set_trust_level(
            service_name=service_name,
            level=level,
            updated_by=updated_by,
            reason=reason,
        )
    except TrustLevelServiceError as e:
        logger.warning("Trust level update failed for %s: %s", service_name, e)
        return render_template(
            "trust/_update_result.html",
            error_message="Failed to update trust level",
            service_name=service_name,
        )
    finally:
        service.close()

    return render_template(
        "trust/_update_result.html",
        config=config,
        trust_definitions=TRUST_LEVEL_DEFINITIONS,
        error_message=None,
        service_name=service_name,
    )


@trust_settings_bp.route("/gates")
@require_role("user")
def gate_thresholds_section() -> str:
    """Display confidence gate thresholds section."""
    service = _get_gate_service()
    gate_error = None
    thresholds = []

    try:
        thresholds = service.get_gate_thresholds()
    except ConfidenceGateError as e:
        logger.warning("Gate thresholds query failed: %s", e)
        gate_error = "Unable to load gate threshold data"
    finally:
        service.close()

    return render_template(
        "trust/_gate_thresholds.html",
        thresholds=thresholds,
        gate_error=gate_error,
    )


@trust_settings_bp.route("/gates/<int:trust_level>/update", methods=["POST"])
@require_role("admin")
def update_gate_threshold(trust_level: int) -> str:
    """Handle form submission to update a gate threshold."""
    if trust_level not in GATED_TRUST_LEVELS:
        return render_template(
            "trust/_gate_update_result.html",
            error_message=(
                "Trust levels 1-2 are advisory-only and have no"
                " confidence gate. Only levels 3-5 can be configured."
            ),
            trust_level=trust_level,
        )

    threshold_str = request.form.get("threshold", "")

    try:
        threshold = float(threshold_str)
    except (ValueError, TypeError):
        return render_template(
            "trust/_gate_update_result.html",
            error_message="Threshold must be a number",
            trust_level=trust_level,
        )

    if isinstance(threshold_str, bool) or threshold < 0.0 or threshold > 1.0:
        return render_template(
            "trust/_gate_update_result.html",
            error_message="Threshold must be between 0.0 and 1.0",
            trust_level=trust_level,
        )

    updated_by = request.headers.get("X-Beeper-User", "admin")

    service = _get_gate_service()
    try:
        config = service.set_gate_threshold(
            trust_level=trust_level,
            threshold=threshold,
            updated_by=updated_by,
        )
    except ConfidenceGateError as e:
        logger.warning(
            "Gate threshold update failed for TL%d: %s", trust_level, e
        )
        return render_template(
            "trust/_gate_update_result.html",
            error_message="Failed to update gate threshold",
            trust_level=trust_level,
        )
    finally:
        service.close()

    return render_template(
        "trust/_gate_update_result.html",
        config=config,
        error_message=None,
        trust_level=trust_level,
    )
