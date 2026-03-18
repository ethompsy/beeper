"""Report Dashboard routes.

Provides noise report dashboard and investor-ready executive reports.
"""

import logging
import os
import re
from typing import Any

from flask import Blueprint, current_app, render_template, request
from werkzeug.exceptions import HTTPException

from beeper_ui.middleware.permissions import require_role
from beeper_ui.services.executive_report_service import (
    VALID_EXECUTIVE_PERIODS,
    ExecutiveReportService,
)
from beeper_ui.services.noise_report_service import (
    VALID_PERIODS,
    NoiseReportService,
    NoiseReportServiceError,
)

logger = logging.getLogger(__name__)

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")

_SERVICE_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]{1,128}$")


def _get_noise_report_service() -> NoiseReportService:
    """Get configured NoiseReportService instance."""
    return NoiseReportService(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )


def _build_template_data(
    report: Any,
    service_filter: str | None,
    period: str,
) -> dict[str, Any]:
    """Build template context from report data.

    Args:
        report: NoiseReportData instance.
        service_filter: Currently selected service filter.
        period: Currently selected time period.

    Returns:
        Dict of template variables.
    """
    return {
        "report": report,
        "selected_service": service_filter,
        "selected_period": period,
        "available_services": [s.service_name for s in report.per_service],
        "error_message": None,
    }


@reports_bp.route("/noise")
@require_role("user")
def noise_report() -> str:
    """Render noise report dashboard.

    Query params:
        service: Optional service name filter.
        period: Time period (7d, 30d, 90d). Defaults to 30d.

    Returns:
        Rendered template (full page or HTMX partial).
    """
    service_filter = request.args.get("service") or None
    period = request.args.get("period", "30d")

    # Validate inputs
    if period not in VALID_PERIODS:
        period = "30d"
    if service_filter and not _SERVICE_NAME_RE.match(service_filter):
        service_filter = None

    svc = _get_noise_report_service()
    try:
        report = svc.build_noise_report(service=service_filter, period=period)
        template_data = _build_template_data(report, service_filter, period)

        if request.headers.get("HX-Request"):
            return render_template(
                "reports/_noise_content.html", **template_data
            )
        return render_template("reports/noise.html", **template_data)
    except NoiseReportServiceError as e:
        logger.warning("Noise report service error: %s", e)
        return _render_error_response(service_filter, period)
    except Exception as e:
        logger.exception("Failed to load noise report: %s", e)
        return _render_error_response(service_filter, period)
    finally:
        svc.close()


def _render_error_response(
    service_filter: str | None,
    period: str,
) -> str:
    """Render error page (full or HTMX partial)."""
    error_data = {
        "error_message": "Unable to load noise report data",
        "report": None,
        "selected_service": service_filter,
        "selected_period": period,
        "available_services": [],
    }
    if request.headers.get("HX-Request"):
        return render_template("reports/_noise_content.html", **error_data)
    return render_template("reports/noise.html", **error_data)


# =============================================================================
# Executive Report
# =============================================================================


def _get_executive_report_service() -> ExecutiveReportService:
    """Get configured ExecutiveReportService instance."""
    return ExecutiveReportService(
        operator_url=current_app.config["OPERATOR_URL"],
        timeout=current_app.config.get("OPERATOR_TIMEOUT", 5.0),
    )


@reports_bp.route("/executive")
@require_role("user")
def executive_report() -> str:
    """Render investor-ready executive report.

    Query params:
        period: Time period (30d, 90d, all). Defaults to 90d.

    Returns:
        Rendered template (full page or HTMX partial).
    """
    period = request.args.get("period", "90d")

    # Validate period
    if period not in VALID_EXECUTIVE_PERIODS:
        period = "90d"

    svc = _get_executive_report_service()
    try:
        data = svc.get_report_data(period=period)

        template_data: dict[str, Any] = {
            **data,
            "selected_period": period,
            "error_message": None,
        }

        if request.headers.get("HX-Request"):
            return render_template(
                "reports/_executive_content.html", **template_data
            )
        return render_template("reports/executive.html", **template_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to load executive report: %s", e)
        return _render_executive_error(period)
    finally:
        svc.close()


def _render_executive_error(period: str) -> str:
    """Render executive report error page."""
    error_data: dict[str, Any] = {
        "current_metrics": {
            "total_resolved": 0,
            "mttr_improvement_pct": None,
            "avg_slo_compliance": None,
            "trust_progression": {
                "distribution": {"levels": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}, "total": 0},
                "changes_count": 0,
                "changes": [],
            },
            "false_page_rate": 0,
        },
        "previous_metrics": {},
        "comparison": {},
        "period": period,
        "period_label": period,
        "date_from": "",
        "date_to": "",
        "selected_period": period,
        "error_message": "Unable to load executive report data",
    }
    if request.headers.get("HX-Request"):
        return render_template("reports/_executive_content.html", **error_data)
    return render_template("reports/executive.html", **error_data)
