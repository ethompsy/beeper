"""Metrics routes for MTTR trends dashboard."""

import logging
import re

from flask import Blueprint, Response, jsonify, redirect, request

from beeper_ui.middleware.permissions import require_role
from beeper_ui.routes.react_registry import build_app_redirect_target
from beeper_ui.services.metrics_service import MetricsService

logger = logging.getLogger(__name__)

metrics_bp = Blueprint("metrics", __name__, url_prefix="/metrics")

# JSON API blueprint (Task 5.4 / AD-4-style REST backfill for the React
# Metrics view). Kept separate from the HTML `metrics_bp` — same pattern as
# `investigations_api_bp` in `ui/beeper_ui/routes/investigations.py` — so it
# can live under the `/api/v1` prefix the React BFF client fetches from. The
# Jinja `/metrics/*` routes above are untouched; this blueprint reuses
# `MetricsService` rather than reimplementing MTTR aggregation.
metrics_api_bp = Blueprint("metrics_api", __name__, url_prefix="/api/v1/metrics")

VALID_PERIODS = {"week", "month", "quarter"}
VALID_SEVERITIES = {"low", "medium", "high", "critical"}
SERVICE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{1,128}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VALID_FORMATS = {"json", "csv"}


def get_metrics_service() -> MetricsService:
    """Create a MetricsService instance."""
    return MetricsService()


def _validate_filters() -> tuple[str, str, str]:
    """Validate and sanitize common filter parameters from the request.

    Returns:
        Tuple of (period, service, severity) with safe defaults.
    """
    period = request.args.get("period", "month")
    if period not in VALID_PERIODS:
        period = "month"

    service = request.args.get("service", "")
    if service and not SERVICE_NAME_PATTERN.match(service):
        service = ""

    severity = request.args.get("severity", "")
    if severity and severity not in VALID_SEVERITIES:
        severity = ""

    return period, service, severity


@metrics_bp.route("/")
def metrics_dashboard() -> Response:
    """Retired (Task 6.3 / D13-D14): the Jinja MTTR dashboard is removed.

    No retained template links to ``url_for('metrics.metrics_dashboard')``,
    but this route is kept registered (not deleted) for the same
    defensive-fallback reasoning and uniform "retired → redirect" pattern
    used across every migrated route in this task — see
    ``knowledge.py``'s ``kb_index()`` docstring. A real browser request
    never reaches this body: the ``before_request`` hook always redirects
    `/metrics` (bare) to `/app/metrics` first. This route (and
    ``mttr_partial``/``mttr_drilldown`` below) is now free of any reference
    to the removed ``mttr.html``/``_mttr_content.html``/``_drilldown.html``
    templates or the ``_load_mttr_template_data()``/``_compute_chart_data()``
    helpers that fed them — the React ``TrendChart`` primitive computes its
    own layout client-side (`ui/frontend/src/lib/...`), so no Python
    replacement for the removed SVG-coordinate helper is needed.
    `/metrics/export` (CSV/JSON, no template) is untouched by this change.
    """
    return redirect(build_app_redirect_target("/metrics/"))


@metrics_bp.route("/mttr")
def mttr_partial() -> Response:
    """Retired (Task 6.3 / D13-D14): the HTMX filter partial is removed.

    Same page as ``metrics_dashboard()`` above in Jinja (an alternate URL
    for the identical content); the ``before_request`` hook redirects bare
    `/metrics/mttr` to `/app/metrics` via an explicit target override
    (`react_registry.py`'s `_REDIRECT_TARGET_OVERRIDES`).
    """
    return redirect(build_app_redirect_target("/metrics/mttr"))


@metrics_bp.route("/mttr/drilldown")
def mttr_drilldown() -> Response:
    """Retired (Task 6.3 / D13-D14): the HTMX drilldown partial is removed.

    The React Metrics view reproduces this as an in-page expandable section
    backed by ``GET /api/v1/metrics/mttr/drilldown`` (JSON, below) rather
    than a separate route — drilldown state is deliberately not a URL
    permalink (route-parity-targets.md §5), so the ``start``/``end``/
    ``service`` query params are intentionally dropped on redirect, same as
    every other view here: the ``before_request`` hook redirects bare
    `/metrics/mttr/drilldown` to `/app/metrics` via an explicit target
    override.
    """
    return redirect(build_app_redirect_target("/metrics/mttr/drilldown"))


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
                headers={"Content-Disposition": f"attachment; filename=mttr-{period}.csv"},
            )

        return Response(
            data,
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename=mttr-{period}.json"},
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


# ---------------------------------------------------------------------------
# JSON API (Task 5.4) — BFF endpoints for the React Metrics (MTTR Trends)
# view. Mirrors the Jinja dashboard's filters exactly (period/service/
# severity, validated by `_validate_filters`) but returns raw aggregation
# data instead of rendered HTML/SVG-geometry — the React chart primitive
# (`TrendChart`) computes its own layout client-side from `trend`, so the
# Jinja-only `_compute_chart_data` (x/y pixel coordinates) is intentionally
# NOT reproduced here. `/metrics/export` (CSV/JSON download) is NOT
# duplicated here either — the React view links directly to the existing
# Jinja `export_metrics` endpoint (parity doc §5: "an equivalent export
# affordance exists", not a reimplementation).
# ---------------------------------------------------------------------------


@metrics_api_bp.route("/mttr")
@require_role("user")
def mttr_json() -> tuple[Response, int] | Response:
    """JSON MTTR trend + service/severity breakdown for the React view.

    Accepts the same ``period``/``service``/``severity`` query filters as
    the Jinja dashboard (validated by the shared ``_validate_filters``
    helper) and delegates to ``MetricsService`` — no MTTR aggregation logic
    is reimplemented here.

    Response shape::

        {
          "period": "month", "service": null, "severity": null,
          "services": [...], "severities": [...],
          "trend": [{"period", "avg_mttr_seconds", "count", "start", "end"}],
          "overall_avg_mttr_seconds": int, "total_count": int,
          "improvement_pct": float | null, "improving": bool | null,
          "by_service": [{"service", "avg_mttr_seconds", "count"}],
          "by_severity": [{"severity", "avg_mttr_seconds", "count"}]
        }
    """
    svc = get_metrics_service()
    try:
        period, service, severity = _validate_filters()

        mttr_data = svc.get_mttr_data(
            time_period=period,
            service=service or None,
            severity=severity or None,
        )
        by_service = svc.get_mttr_by_service()
        by_severity = svc.get_mttr_by_severity()

        return jsonify(
            {
                "period": period,
                "service": service or None,
                "severity": severity or None,
                "services": svc.get_services(),
                "severities": svc.get_severities(),
                "trend": [
                    {
                        "period": t["period"],
                        "avg_mttr_seconds": t["avg_mttr"],
                        "count": t["count"],
                        "start": t["start"],
                        "end": t["end"],
                    }
                    for t in mttr_data["trend"]
                ],
                "overall_avg_mttr_seconds": mttr_data["overall_avg_mttr"],
                "total_count": mttr_data["total_count"],
                "improvement_pct": mttr_data["improvement_pct"],
                "improving": mttr_data["improving"],
                "by_service": [
                    {
                        "service": s["service"],
                        "avg_mttr_seconds": s["avg_mttr"],
                        "count": s["count"],
                    }
                    for s in by_service
                ],
                "by_severity": [
                    {
                        "severity": s["severity"],
                        "avg_mttr_seconds": s["avg_mttr"],
                        "count": s["count"],
                    }
                    for s in by_severity
                ],
            }
        )
    except Exception as e:
        logger.exception("Failed to load MTTR JSON data: %s", e)
        return jsonify({"error": "metrics_unavailable"}), 503
    finally:
        svc.close()


@metrics_api_bp.route("/mttr/drilldown")
@require_role("user")
def mttr_drilldown_json() -> tuple[Response, int] | Response:
    """JSON drill-down investigation list for a time bucket (React view).

    Accepts ``start``/``end`` (``YYYY-MM-DD``, required) and an optional
    ``service`` filter — same validation as the Jinja ``mttr_drilldown``
    route. An invalid/missing date range returns an empty list with a 400,
    matching the Jinja route's "no data" degrade-gracefully behavior rather
    than raising.
    """
    svc = get_metrics_service()
    try:
        start = request.args.get("start", "")
        end = request.args.get("end", "")
        service = request.args.get("service", "")
        if service and not SERVICE_NAME_PATTERN.match(service):
            service = ""

        if (
            not start
            or not end
            or not DATE_PATTERN.match(start)
            or not DATE_PATTERN.match(end)
            or start > end
        ):
            return jsonify({"period_label": None, "investigations": []}), 400

        investigations = svc.get_investigations_for_period(
            start_date=start, end_date=end, service=service or None
        )

        return jsonify(
            {
                "period_label": f"{start} to {end}",
                "investigations": [
                    {
                        "investigation_id": inv.get("investigation_id"),
                        "service": inv.get("service"),
                        "severity": inv.get("severity"),
                        "mttr_seconds": inv.get("mttr_seconds"),
                        "resolved_at": inv.get("resolved_at"),
                        "resolution_outcome": inv.get("resolution_outcome"),
                    }
                    for inv in investigations
                ],
            }
        )
    except Exception as e:
        logger.exception("Failed to load MTTR drilldown JSON data: %s", e)
        return jsonify(
            {"error": "metrics_unavailable", "period_label": None, "investigations": []}
        ), 503
    finally:
        svc.close()
