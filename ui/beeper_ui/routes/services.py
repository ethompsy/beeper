"""Per-service health feed routes."""

import logging
import re
import time
from typing import Any

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    render_template,
    request,
    stream_with_context,
)
from werkzeug.exceptions import HTTPException

from beeper_ui.services.service_health_service import ServiceHealthService

logger = logging.getLogger(__name__)

services_bp = Blueprint("services", __name__, url_prefix="/services")

_SERVICE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

SSE_POLL_INTERVAL = 3


def _get_service_health_service() -> ServiceHealthService:
    """Get configured ServiceHealthService instance."""
    return ServiceHealthService(
        operator_url=current_app.config["OPERATOR_URL"],
        timeout=current_app.config["OPERATOR_TIMEOUT"],
    )


@services_bp.route("/")
def service_list() -> str:
    """Render service list with health summary badges."""
    svc = _get_service_health_service()
    try:
        status_filter = request.args.get("status")
        services = svc.get_service_list(status_filter=status_filter)

        # Compute summary counts
        all_services = svc.get_service_list() if status_filter else services
        total = len(all_services)
        healthy_count = sum(
            1 for s in all_services if s["health_status"] == "healthy"
        )
        warning_count = sum(
            1 for s in all_services if s["health_status"] == "warning"
        )
        critical_count = sum(
            1 for s in all_services if s["health_status"] == "critical"
        )

        template_data: dict[str, Any] = {
            "services": services,
            "total_services": total,
            "healthy_count": healthy_count,
            "warning_count": warning_count,
            "critical_count": critical_count,
            "current_filter": status_filter or "all",
            "error_message": None,
        }

        if request.headers.get("HX-Request"):
            return render_template("services/_list_content.html", **template_data)
        return render_template("services/list.html", **template_data)
    except Exception as e:
        logger.exception("Failed to load service list: %s", e)
        error_data: dict[str, Any] = {
            "services": [],
            "total_services": 0,
            "healthy_count": 0,
            "warning_count": 0,
            "critical_count": 0,
            "current_filter": "all",
            "error_message": "Unable to load service health data",
        }
        if request.headers.get("HX-Request"):
            return render_template("services/_list_content.html", **error_data)
        return render_template("services/list.html", **error_data)
    finally:
        svc.close()


@services_bp.route("/<name>")
def service_detail(name: str) -> str:
    """Render per-service health detail page."""
    if not _SERVICE_NAME_RE.match(name):
        abort(404)

    svc = _get_service_health_service()
    try:
        detail = svc.get_service_detail(name)
        if detail is None:
            abort(404)

        if request.headers.get("HX-Request"):
            return render_template("services/_detail_content.html", service=detail)
        return render_template("services/detail.html", service=detail)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to load service detail for %s: %s", name, e)
        return render_template(
            "services/detail.html",
            service=None,
            error_message=f"Unable to load health data for {name}",
        )
    finally:
        svc.close()


@services_bp.route("/<name>/feed-items")
def service_feed_items(name: str) -> str:
    """Render feed items partial for a service (HTMX lazy-load)."""
    if not _SERVICE_NAME_RE.match(name):
        abort(404)

    svc = _get_service_health_service()
    try:
        detail = svc.get_service_detail(name)
        if detail is None:
            abort(404)

        return render_template(
            "services/_health_feed_items.html",
            active_investigations=detail["active_investigations"],
            recent_resolved=detail["recent_resolved"],
            service_name=name,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to load feed items for %s: %s", name, e)
        return render_template(
            "services/_health_feed_items.html",
            active_investigations=[],
            recent_resolved=[],
            service_name=name,
        )
    finally:
        svc.close()


@services_bp.route("/<name>/stream")
def service_health_stream(name: str) -> Response:
    """SSE stream for real-time service health updates."""
    if not _SERVICE_NAME_RE.match(name):
        abort(404)

    def generate() -> Any:
        prev_active_count: int | None = None
        while True:
            try:
                svc = _get_service_health_service()
                try:
                    detail = svc.get_service_detail(name)
                    if detail is None:
                        time.sleep(SSE_POLL_INTERVAL)
                        continue

                    current_count = detail["active_investigation_count"]
                    if prev_active_count is not None and current_count != prev_active_count:
                        html = render_template(
                            "services/_health_feed_items.html",
                            active_investigations=detail["active_investigations"],
                            recent_resolved=detail["recent_resolved"],
                            service_name=name,
                        )
                        yield f"event: investigation-update\ndata: {html}\n\n"

                    prev_active_count = current_count
                finally:
                    svc.close()
            except GeneratorExit:
                return
            except Exception as e:
                logger.warning("SSE error for service %s: %s", name, e)

            time.sleep(SSE_POLL_INTERVAL)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
