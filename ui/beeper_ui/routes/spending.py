"""Spending routes for LLM cost dashboard."""

import logging
from typing import Any

from flask import Blueprint, render_template, request

from beeper_ui.services.spending_service import SpendingService

logger = logging.getLogger(__name__)

spending_bp = Blueprint("spending", __name__, url_prefix="/spending")


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
