"""SLO compliance dashboard routes."""

import logging
from typing import Any

from flask import Blueprint, abort, current_app, render_template, request
from werkzeug.exceptions import HTTPException

from beeper_ui.services.slo_service import SloService

logger = logging.getLogger(__name__)

slo_bp = Blueprint("slo", __name__, url_prefix="/slo")


def get_slo_service() -> SloService:
    """Get configured SloService instance."""
    return SloService(
        operator_url=current_app.config["OPERATOR_URL"],
        timeout=current_app.config["OPERATOR_TIMEOUT"],
    )


@slo_bp.route("/")
def slo_dashboard() -> str:
    """Render SLO compliance dashboard."""
    svc = get_slo_service()
    try:
        services = svc.get_services()
        template_data = _build_dashboard_data(services)

        if request.headers.get("HX-Request"):
            return render_template("slo/_content.html", **template_data)
        return render_template("slo/dashboard.html", **template_data)
    except Exception as e:
        logger.exception("Failed to load SLO dashboard: %s", e)
        error_data = {"error_message": "Unable to connect to SLO data"}
        if request.headers.get("HX-Request"):
            return render_template("slo/_content.html", **error_data)
        return render_template("slo/dashboard.html", **error_data)
    finally:
        svc.close()


@slo_bp.route("/services/<name>")
def slo_service_detail(name: str) -> str:
    """Render SLO service detail page."""
    svc = get_slo_service()
    try:
        detail = svc.get_service_detail(name)
        if detail is None:
            abort(404)

        budget = svc.get_service_budget(name)

        return render_template(
            "slo/service.html",
            service=detail,
            budget=budget,
            error_message=None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to load SLO detail for %s: %s", name, e)
        return render_template(
            "slo/service.html",
            service=None,
            budget=None,
            error_message=f"Unable to load SLO data for {name}",
        )
    finally:
        svc.close()


def _build_dashboard_data(services: list[dict[str, Any]]) -> dict[str, Any]:
    """Build template context for SLO dashboard.

    Args:
        services: List of service level dicts from operator API.

    Returns:
        Dict of template variables.
    """
    total = len(services)
    healthy_count = sum(
        1 for s in services if s.get("condition") == "healthy"
    )
    at_risk_count = sum(
        1 for s in services
        if s.get("condition") in ("warning", "critical")
    )
    frozen_count = sum(
        1 for s in services if s.get("is_frozen") is True
    )

    return {
        "services": services,
        "total_services": total,
        "healthy_count": healthy_count,
        "at_risk_count": at_risk_count,
        "frozen_count": frozen_count,
        "error_message": None,
    }
