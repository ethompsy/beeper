"""Health status routes for Beeper UI."""

from flask import Blueprint, Response, current_app, jsonify, redirect, render_template, request

from beeper_ui.middleware.permissions import require_role
from beeper_ui.routes.react_registry import build_app_redirect_target
from beeper_ui.services.health_service import HealthService, HealthServiceError
from beeper_ui.services.identity_store import get_identity_store_if_initialized

health_bp = Blueprint("health", __name__, url_prefix="/health")

# JSON API blueprint (Task 5.2 — BFF JSON API for the React Ingestion Stats
# view). Kept separate from `health_bp` (which serves the Jinja
# `/health/ingestion` page + its HTMX-partial auto-refresh route, unchanged
# by this task) exactly like `investigations_api_bp` is kept separate from
# `investigations_bp` (`ui/beeper_ui/routes/investigations.py`) — one
# blueprint per response format, both reading through the same service layer.
ingestion_api_bp = Blueprint("ingestion_api", __name__, url_prefix="/api/v1/ingestion")


def get_health_service() -> HealthService:
    """Get configured HealthService instance."""
    return HealthService(
        operator_url=current_app.config["OPERATOR_URL"],
        timeout=current_app.config["OPERATOR_TIMEOUT"],
    )


@health_bp.route("/")
def health_status() -> str:
    """Display operator health status.

    For HTMX requests (auto-refresh), returns only the status content partial.
    For full page requests, returns the complete page.
    """
    service = get_health_service()
    error_message = None
    components: dict[str, dict[str, str | None]] = {}
    overall = "unknown"
    ingestion_stats = None

    try:
        health = service.get_health()
        components = {name: comp.__dict__ for name, comp in health.components.items()}
        overall = health.overall
    except HealthServiceError as e:
        error_message = str(e)

    # Try to get ingestion stats separately (may fail independently)
    try:
        stats = service.get_ingestion_stats()
        ingestion_stats = stats.__dict__
    except HealthServiceError:
        # Ingestion stats are optional, don't fail if unavailable
        pass

    # Check if this is an HTMX request (for partial updates)
    if request.headers.get("HX-Request"):
        return render_template(
            "health/_status_content.html",
            components=components,
            overall=overall,
            ingestion_stats=ingestion_stats,
            error_message=error_message,
        )

    return render_template(
        "health/status.html",
        components=components,
        overall=overall,
        ingestion_stats=ingestion_stats,
        error_message=error_message,
    )


@health_bp.route("/ingestion")
def ingestion_stats() -> Response:
    """Retired (Task 6.3 / D13-D14): the Jinja diagnostic dashboard is removed.

    No retained template links to ``url_for('health.ingestion_stats')``, but
    this route is kept registered (not deleted) for the same defensive-
    fallback reasoning and uniform "retired → redirect" pattern used across
    every migrated route in this task — see
    ``knowledge.py``'s ``kb_index()`` docstring. A real browser request
    never reaches this body: the ``REACT_OWNED_PREFIXES`` ``before_request``
    hook (``react_registry.py``) always redirects the exact bare path
    `/health/ingestion` to `/app/ingestion-stats` first (an explicit target
    override — the React route lives under a differently-named path, not a
    1:1 rewrite of the Jinja one). This route is now free of any reference
    to the removed ``ingestion.html``/``_ingestion_content.html`` templates
    or the ``_pipeline_view()`` helper that fed them (the React view
    re-derives the identical three-state precedence client-side from the
    raw ``/api/v1/ingestion/stats`` fields — see ``ingestion_stats_json()``
    below, unaffected by this change).

    ``/health/`` (the general operator-health overview) and ``/health/api``
    are separate routes on this same blueprint and are untouched — only
    this one path is React-owned.
    """
    return redirect(build_app_redirect_target("/health/ingestion"))


@health_bp.route("/api")
def health_api() -> dict[str, object]:
    """Health check endpoint for the UI itself.

    Task 8.3 / ADR 0002 §5.3, FR60: when the identity store has already
    been constructed (i.e. `BEEPER_AUTH_MODE` is `local`/`oidc` AND at least
    one identity-store operation has run this process), the response gains
    a `zero_active_admins` detail flag mirroring the store's CRITICAL-logged
    alarm state. Deliberately absent in mode `none` and before the store's
    first use in `local`/`oidc` — this route never triggers construction
    itself (`get_identity_store_if_initialized()`, not `get_identity_store
    ()`): a k8s liveness/readiness probe hitting this route must never open
    a Qdrant connection just because it was polled, and this route is
    listed exempt from identity gating precisely so probes never 401
    (ADR §2 exemption matrix).
    """
    body: dict[str, object] = {"status": "healthy"}
    store = get_identity_store_if_initialized()
    if store is not None:
        body["zero_active_admins"] = store.has_zero_active_admins()
    return body


@ingestion_api_bp.route("/stats")
@require_role("user")
def ingestion_stats_json() -> tuple[Response, int] | Response:
    """JSON ingestion/detection pipeline stats for the React UI (Task 5.2, FR32-33).

    Reuses ``HealthService.get_ingestion_stats()`` — the exact same call the
    Jinja ``ingestion_stats()`` view above makes — and returns the
    ``IngestionStats`` dataclass fields verbatim as snake_case JSON, mirroring
    the operator's own ``/api/v1/ingestion/stats`` response shape 1:1.

    Deliberately does NOT include the derived ``pipeline_state``/
    ``warmup_pct``/``is_warming`` fields ``_pipeline_view()`` computes for the
    Jinja template: the React view re-derives the identical three-state
    precedence (no_data / warming / active) client-side from these raw
    fields (mirrors ``_pipeline_view()`` exactly — see
    ``ui/frontend/src/lib/ingestion/pipeline-view.ts``), so the JSON contract
    here stays a thin passthrough of the operator's own stats, not a
    UI-view-model endpoint.
    """
    service = get_health_service()
    try:
        stats = service.get_ingestion_stats()
        return jsonify(
            {
                "buffer_size": stats.buffer_size,
                "buffered_count": stats.buffered_count,
                "dropped_count": stats.dropped_count,
                "is_full": stats.is_full,
                "metrics_received": stats.metrics_received,
                "logs_received": stats.logs_received,
                "anomalies_detected": stats.anomalies_detected,
                "anomalies_suppressed": stats.anomalies_suppressed,
                "active_metric_detectors": stats.active_metric_detectors,
                "ewma_warmup_samples": stats.ewma_warmup_samples,
                "ewma_warmup_minimum": stats.ewma_warmup_minimum,
            }
        )
    except HealthServiceError:
        return jsonify({"error": "operator_unavailable"}), 503
    finally:
        service.close()
