"""Metrics routes for MTTR trends dashboard."""

import logging
import re
from typing import Any

from flask import Blueprint, Response, render_template, request

from beeper_ui.services.metrics_service import MetricsService

logger = logging.getLogger(__name__)

metrics_bp = Blueprint("metrics", __name__, url_prefix="/metrics")

VALID_PERIODS = {"week", "month", "quarter"}
VALID_SEVERITIES = {"low", "medium", "high", "critical"}
SERVICE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{1,128}$")
VALID_FORMATS = {"json", "csv"}


def get_metrics_service() -> MetricsService:
    """Create a MetricsService instance."""
    return MetricsService()


def _compute_chart_data(
    trend: list[dict[str, Any]],
    chart_width: int = 800,
    chart_height: int = 300,
) -> dict[str, Any]:
    """Compute SVG chart coordinates from trend data.

    Args:
        trend: List of trend data dicts with avg_mttr.
        chart_width: SVG viewBox width.
        chart_height: SVG viewBox height.

    Returns:
        Dict with chart_width, chart_height, data_points, trend_points, y_grid_lines.
    """
    if not trend:
        return {
            "chart_width": chart_width,
            "chart_height": chart_height,
            "data_points": [],
            "trend_points": "",
            "y_grid_lines": [],
        }

    max_mttr = max(t["avg_mttr"] for t in trend)
    if max_mttr == 0:
        max_mttr = 1  # Avoid division by zero

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
        y = padding_y + (1 - t["avg_mttr"] / max_mttr) * usable_height
        data_points.append({
            "x": round(x, 1),
            "y": round(y, 1),
            "period": t["period"],
            "avg_mttr": t["avg_mttr"],
            "count": t["count"],
            "start": t["start"],
            "end": t["end"],
        })

    trend_points = " ".join(f"{p['x']},{p['y']}" for p in data_points)

    # Y-axis grid lines (4 lines)
    y_grid_lines = []
    for i in range(5):
        y = padding_y + (i / 4) * usable_height
        value = max_mttr - (i / 4) * max_mttr
        y_grid_lines.append({"y": round(y, 1), "value": int(value)})

    return {
        "chart_width": chart_width,
        "chart_height": chart_height,
        "data_points": data_points,
        "trend_points": trend_points,
        "y_grid_lines": y_grid_lines,
    }


@metrics_bp.route("/")
def metrics_dashboard() -> str:
    """Render MTTR trends dashboard page."""
    svc = get_metrics_service()
    try:
        period = request.args.get("period", "month")
        if period not in VALID_PERIODS:
            period = "month"

        service = request.args.get("service", "")
        if service and not SERVICE_NAME_PATTERN.match(service):
            service = ""

        severity = request.args.get("severity", "")
        if severity and severity not in VALID_SEVERITIES:
            severity = ""

        mttr_data = svc.get_mttr_data(
            time_period=period,
            service=service or None,
            severity=severity or None,
        )
        by_service = svc.get_mttr_by_service()
        by_severity = svc.get_mttr_by_severity()
        services = svc.get_services()
        severities = svc.get_severities()

        # Compute max values for bar chart percentages
        max_service_mttr = max((s["avg_mttr"] for s in by_service), default=1) or 1
        max_severity_mttr = max((s["avg_mttr"] for s in by_severity), default=1) or 1

        chart = _compute_chart_data(mttr_data["trend"])

        template_data = {
            "mttr_data": mttr_data,
            "by_service": by_service,
            "by_severity": by_severity,
            "services": services,
            "severities": severities,
            "selected_period": period,
            "selected_service": service,
            "selected_severity": severity,
            "max_service_mttr": max_service_mttr,
            "max_severity_mttr": max_severity_mttr,
            "error_message": None,
            **chart,
        }

        if request.headers.get("HX-Request"):
            return render_template("metrics/_mttr_content.html", **template_data)
        return render_template("metrics/mttr.html", **template_data)
    except Exception as e:
        logger.exception("Failed to load metrics dashboard: %s", e)
        error_data = {"error_message": "Unable to connect to metrics data store"}
        if request.headers.get("HX-Request"):
            return render_template("metrics/_mttr_content.html", **error_data)
        return render_template("metrics/mttr.html", **error_data)
    finally:
        svc.close()


@metrics_bp.route("/mttr")
def mttr_partial() -> str:
    """Return MTTR content partial for HTMX filtering."""
    svc = get_metrics_service()
    try:
        period = request.args.get("period", "month")
        if period not in VALID_PERIODS:
            period = "month"

        service = request.args.get("service", "")
        if service and not SERVICE_NAME_PATTERN.match(service):
            service = ""

        severity = request.args.get("severity", "")
        if severity and severity not in VALID_SEVERITIES:
            severity = ""

        mttr_data = svc.get_mttr_data(
            time_period=period,
            service=service or None,
            severity=severity or None,
        )
        by_service = svc.get_mttr_by_service()
        by_severity = svc.get_mttr_by_severity()
        services = svc.get_services()
        severities = svc.get_severities()

        max_service_mttr = max((s["avg_mttr"] for s in by_service), default=1) or 1
        max_severity_mttr = max((s["avg_mttr"] for s in by_severity), default=1) or 1

        chart = _compute_chart_data(mttr_data["trend"])

        return render_template(
            "metrics/_mttr_content.html",
            mttr_data=mttr_data,
            by_service=by_service,
            by_severity=by_severity,
            services=services,
            severities=severities,
            selected_period=period,
            selected_service=service,
            selected_severity=severity,
            max_service_mttr=max_service_mttr,
            max_severity_mttr=max_severity_mttr,
            error_message=None,
            **chart,
        )
    except Exception as e:
        logger.exception("Failed to load MTTR data: %s", e)
        return render_template(
            "metrics/_mttr_content.html",
            error_message="Unable to connect to metrics data store",
        )
    finally:
        svc.close()


@metrics_bp.route("/mttr/drilldown")
def mttr_drilldown() -> str:
    """Return drill-down investigation list for a time bucket."""
    svc = get_metrics_service()
    try:
        start = request.args.get("start", "")
        end = request.args.get("end", "")
        service = request.args.get("service", "")
        if service and not SERVICE_NAME_PATTERN.match(service):
            service = ""

        if not start or not end:
            return render_template(
                "metrics/_drilldown.html", investigations=[], period_label=""
            )

        investigations = svc.get_investigations_for_period(
            start_date=start, end_date=end, service=service or None
        )
        period_label = f"{start} to {end}"

        return render_template(
            "metrics/_drilldown.html",
            investigations=investigations,
            period_label=period_label,
        )
    except Exception as e:
        logger.exception("Failed to load drill-down data: %s", e)
        return render_template(
            "metrics/_drilldown.html",
            investigations=[],
            period_label="Error loading data",
        )
    finally:
        svc.close()


@metrics_bp.route("/export")
def export_metrics() -> Response:
    """Export MTTR data as JSON or CSV download."""
    svc = get_metrics_service()
    try:
        period = request.args.get("period", "month")
        if period not in VALID_PERIODS:
            period = "month"

        fmt = request.args.get("format", "json")
        if fmt not in VALID_FORMATS:
            fmt = "json"

        data = svc.export_mttr_data(time_period=period, fmt=fmt)

        if fmt == "csv":
            return Response(
                data,
                mimetype="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=mttr-{period}.csv"
                },
            )

        return Response(
            data,
            mimetype="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=mttr-{period}.json"
            },
        )
    except Exception as e:
        logger.exception("Failed to export metrics: %s", e)
        return Response(
            '{"error": "Failed to export metrics"}',
            status=500,
            mimetype="application/json",
        )
    finally:
        svc.close()
