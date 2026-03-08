"""Spending routes for LLM cost dashboard."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import Blueprint, Response, render_template, request

from beeper_ui.services.spending_service import SpendingService

logger = logging.getLogger(__name__)

spending_bp = Blueprint("spending", __name__, url_prefix="/spending")

VALID_COST_PERIODS = {"week", "month", "quarter"}
VALID_FORMATS = {"json", "csv"}


def get_spending_service() -> SpendingService:
    """Create a SpendingService instance."""
    return SpendingService()


def _compute_spend_chart_data(
    trend: list[dict[str, Any]],
    chart_width: int = 800,
    chart_height: int = 300,
) -> dict[str, Any]:
    """Compute SVG chart coordinates from spending trend data.

    Args:
        trend: List of trend data dicts with cost_usd.
        chart_width: SVG viewBox width.
        chart_height: SVG viewBox height.

    Returns:
        Dict with chart coordinates for SVG rendering.
    """
    if not trend:
        return {
            "chart_width": chart_width,
            "chart_height": chart_height,
            "data_points": [],
            "trend_points": "",
            "y_grid_lines": [],
        }

    max_cost = max(t["cost_usd"] for t in trend)
    if max_cost == 0:
        max_cost = 1.0

    padding_x = 60
    padding_y = 30
    usable_width = chart_width - 2 * padding_x
    usable_height = chart_height - 2 * padding_y

    data_points = []
    for i, t in enumerate(trend):
        if len(trend) > 1:
            x = padding_x + (i / (len(trend) - 1)) * usable_width
        else:
            x = chart_width / 2
        y = padding_y + (1 - t["cost_usd"] / max_cost) * usable_height
        data_points.append({
            "x": round(x, 1),
            "y": round(y, 1),
            "period": t["period"],
            "cost_usd": t["cost_usd"],
            "count": t["count"],
        })

    trend_points = " ".join(f"{p['x']},{p['y']}" for p in data_points)

    y_grid_lines = []
    for i in range(5):
        y = padding_y + (i / 4) * usable_height
        value = max_cost - (i / 4) * max_cost
        y_grid_lines.append({"y": round(y, 1), "value": round(value, 2)})

    return {
        "chart_width": chart_width,
        "chart_height": chart_height,
        "data_points": data_points,
        "trend_points": trend_points,
        "y_grid_lines": y_grid_lines,
    }


def _load_spending_template_data(svc: SpendingService) -> dict[str, Any]:
    """Load all spending dashboard data.

    Args:
        svc: SpendingService instance.

    Returns:
        Dict of template variables.
    """
    summary = svc.get_spending_summary()
    cap_status = svc.get_cap_status()
    trend = svc.get_spending_trend(period="daily")
    chart = _compute_spend_chart_data(trend)

    return {
        "summary": summary,
        "cap_status": cap_status,
        "error_message": None,
        **chart,
    }


@spending_bp.route("/")
def spending_dashboard() -> str:
    """Render spending dashboard page."""
    svc = get_spending_service()
    try:
        template_data = _load_spending_template_data(svc)

        if request.headers.get("HX-Request"):
            return render_template(
                "spending/_spending_content.html", **template_data
            )
        return render_template("spending/spending.html", **template_data)
    except Exception as e:
        logger.exception("Failed to load spending dashboard: %s", e)
        error_data = {
            "error_message": "Unable to connect to spending data store"
        }
        if request.headers.get("HX-Request"):
            return render_template(
                "spending/_spending_content.html", **error_data
            )
        return render_template("spending/spending.html", **error_data)
    finally:
        svc.close()


@spending_bp.route("/status")
def spending_status() -> str:
    """Return spending status partial for HTMX updates."""
    svc = get_spending_service()
    try:
        template_data = _load_spending_template_data(svc)
        return render_template(
            "spending/_spending_content.html", **template_data
        )
    except Exception as e:
        logger.exception("Failed to load spending status: %s", e)
        return render_template(
            "spending/_spending_content.html",
            error_message="Unable to connect to spending data store",
        )
    finally:
        svc.close()


def _validate_cost_filters() -> str:
    """Validate and sanitize cost filter parameters.

    Returns:
        Validated period string.
    """
    period = request.args.get("period", "month")
    if period not in VALID_COST_PERIODS:
        period = "month"
    return period


def _load_cost_template_data(svc: SpendingService) -> dict[str, Any]:
    """Load all cost insights data.

    Args:
        svc: SpendingService instance.

    Returns:
        Dict of template variables for cost breakdown rendering.
    """
    period = _validate_cost_filters()

    by_service = svc.get_cost_by_service(period=period)
    by_severity = svc.get_cost_by_severity(period=period)
    by_model = svc.get_cost_by_model(period=period)
    high_cost = svc.get_high_cost_services(period=period)

    max_service_cost = max(
        (s["total_cost_usd"] for s in by_service), default=1.0
    )
    if max_service_cost == 0:
        max_service_cost = 1.0

    max_severity_cost = max(
        (s["total_cost_usd"] for s in by_severity), default=1.0
    )
    if max_severity_cost == 0:
        max_severity_cost = 1.0

    max_model_cost = max(
        (m["total_cost_usd"] for m in by_model), default=1.0
    )
    if max_model_cost == 0:
        max_model_cost = 1.0

    high_cost_service_names = {h["service"] for h in high_cost}

    # Compute cost trend chart filtered to selected period
    trend = svc.get_spending_trend(period="daily")
    now = datetime.now(UTC)
    if period == "week":
        cutoff_str = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    elif period == "quarter":
        cutoff_str = (now - timedelta(days=90)).strftime("%Y-%m-%d")
    else:
        cutoff_str = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    filtered_trend = [t for t in trend if t["period"] >= cutoff_str]
    chart = _compute_spend_chart_data(filtered_trend)

    return {
        "by_service": by_service,
        "by_severity": by_severity,
        "by_model": by_model,
        "high_cost_services": high_cost,
        "high_cost_service_names": high_cost_service_names,
        "max_service_cost": max_service_cost,
        "max_severity_cost": max_severity_cost,
        "max_model_cost": max_model_cost,
        "selected_period": period,
        "error_message": None,
        **chart,
    }


@spending_bp.route("/costs")
def cost_insights() -> str:
    """Render cost insights dashboard page."""
    svc = get_spending_service()
    try:
        template_data = _load_cost_template_data(svc)

        if request.headers.get("HX-Request"):
            return render_template(
                "spending/_cost_breakdown.html", **template_data
            )
        return render_template("spending/costs.html", **template_data)
    except Exception as e:
        logger.exception("Failed to load cost insights: %s", e)
        error_data = {
            "error_message": "Unable to connect to cost data store"
        }
        if request.headers.get("HX-Request"):
            return render_template(
                "spending/_cost_breakdown.html", **error_data
            )
        return render_template("spending/costs.html", **error_data)
    finally:
        svc.close()


@spending_bp.route("/costs/breakdown")
def cost_breakdown_partial() -> str:
    """Return cost breakdown partial for HTMX filtering."""
    svc = get_spending_service()
    try:
        template_data = _load_cost_template_data(svc)
        return render_template(
            "spending/_cost_breakdown.html", **template_data
        )
    except Exception as e:
        logger.exception("Failed to load cost breakdown: %s", e)
        return render_template(
            "spending/_cost_breakdown.html",
            error_message="Unable to connect to cost data store",
        )
    finally:
        svc.close()


@spending_bp.route("/costs/export")
def export_costs() -> Response:
    """Export cost data as JSON or CSV download."""
    svc = get_spending_service()
    try:
        period = _validate_cost_filters()

        fmt = request.args.get("format", "json")
        if fmt not in VALID_FORMATS:
            fmt = "json"

        data = svc.export_cost_data(period=period, fmt=fmt)

        if fmt == "csv":
            return Response(
                data,
                mimetype="text/csv",
                headers={
                    "Content-Disposition": (
                        f"attachment; filename=costs-{period}.csv"
                    )
                },
            )

        return Response(
            data,
            mimetype="application/json",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=costs-{period}.json"
                )
            },
        )
    except Exception as e:
        logger.exception("Failed to export cost data: %s", e)
        return Response(
            '{"error": "Failed to export cost data"}',
            status=500,
            mimetype="application/json",
        )
    finally:
        svc.close()
