"""Analytics dashboard routes for MTTR, impact, and trust trends."""

import logging
import re
from typing import Any

from flask import (
    Blueprint,
    abort,
    current_app,
    render_template,
    request,
)
from werkzeug.exceptions import HTTPException

from beeper_ui.services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)

analytics_bp = Blueprint("analytics", __name__, url_prefix="/analytics")

_SERVICE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

_VALID_PERIODS = {4, 12, 26}


def _get_analytics_service() -> AnalyticsService:
    """Get configured AnalyticsService instance."""
    return AnalyticsService(
        operator_url=current_app.config["OPERATOR_URL"],
        timeout=current_app.config["OPERATOR_TIMEOUT"],
    )


@analytics_bp.route("/")
def analytics_dashboard() -> str:
    """Render analytics dashboard with MTTR, impact, and trust sections."""
    svc = _get_analytics_service()
    try:
        # Parse period filter
        period_str = request.args.get("period", "12")
        try:
            period_weeks = int(period_str)
        except (ValueError, TypeError):
            period_weeks = 12
        if period_weeks not in _VALID_PERIODS:
            period_weeks = 12

        # Parse service filter
        service_filter = request.args.get("service")
        if service_filter:
            if (
                len(service_filter) > 100
                or not _SERVICE_NAME_RE.match(service_filter)
            ):
                abort(400)

        data = svc.get_dashboard_data(
            period_weeks=period_weeks,
            service_filter=service_filter,
        )

        # Compute max values for bar chart scaling
        max_mttr = max(
            (t["avg_mttr_hours"] for t in data["mttr_trends"]),
            default=1,
        )
        max_inv_count = max(
            (t["investigation_count"] for t in data["impact_trends"]),
            default=1,
        )

        template_data: dict[str, Any] = {
            **data,
            "max_mttr": max_mttr if max_mttr > 0 else 1,
            "max_inv_count": max_inv_count if max_inv_count > 0 else 1,
            "current_period": period_weeks,
            "current_service": service_filter or "",
            "error_message": None,
        }

        if request.headers.get("HX-Request"):
            return render_template(
                "analytics/_dashboard_content.html", **template_data
            )
        return render_template("analytics/dashboard.html", **template_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to load analytics dashboard: %s", e)
        error_data: dict[str, Any] = {
            "mttr_trends": [],
            "mttr_by_service": [],
            "mttr_change_pct": None,
            "impact_trends": [],
            "trust_distribution": {"levels": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}, "total": 0},
            "trust_changes": [],
            "service_names": [],
            "period_weeks": 12,
            "service_filter": None,
            "max_mttr": 1,
            "max_inv_count": 1,
            "current_period": 12,
            "current_service": "",
            "error_message": "Unable to load analytics data",
        }
        if request.headers.get("HX-Request"):
            return render_template(
                "analytics/_dashboard_content.html", **error_data
            )
        return render_template("analytics/dashboard.html", **error_data)
    finally:
        svc.close()
