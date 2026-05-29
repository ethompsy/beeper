"""Health status routes for Beeper UI."""

from flask import Blueprint, current_app, render_template, request

from beeper_ui.services.health_service import HealthService, HealthServiceError

health_bp = Blueprint("health", __name__, url_prefix="/health")


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


def _pipeline_view(stats: dict | None) -> dict:
    """Derive the pipeline-diagnostic view-model from raw ingestion stats.

    Computes the mutually-exclusive pipeline state and the EWMA warmup
    percentage used by the diagnostic dashboard (Task 5.2, FR32-33):

      • no_data  — metrics_received == 0 AND logs_received == 0 (red chip)
      • warming  — ewma_warmup_samples < ewma_warmup_minimum   (amber chip + bar)
      • active   — samples >= minimum                          (green chip)

    warmup_pct = samples / minimum * 100 (clamped 0-100; 0 when minimum == 0).
    """
    if not stats:
        return {
            "pipeline_state": "no_data",
            "warmup_pct": 0,
            "is_warming": False,
        }

    metrics_received = stats.get("metrics_received", 0) or 0
    logs_received = stats.get("logs_received", 0) or 0
    samples = stats.get("ewma_warmup_samples", 0) or 0
    minimum = stats.get("ewma_warmup_minimum", 0) or 0

    warmup_pct = (samples / minimum * 100) if minimum > 0 else 0
    warmup_pct = max(0, min(100, warmup_pct))

    if metrics_received == 0 and logs_received == 0:
        state = "no_data"
    elif samples < minimum:
        state = "warming"
    else:
        state = "active"

    return {
        "pipeline_state": state,
        "warmup_pct": warmup_pct,
        "is_warming": state == "warming",
    }


@health_bp.route("/ingestion")
def ingestion_stats() -> str:
    """Pipeline diagnostic dashboard (Observe > Ingestion Stats, Task 5.2).

    Grafana-style ingestion + detection diagnostics: metrics/logs received,
    anomaly detection counters, and the EWMA warmup state with a tri-state
    pipeline chip (warming / active / no data).

    Auto-refresh (AC6): the page polls this same route via HTMX
    (``hx-trigger="every 5s"``); HMTX requests get only the stats partial so the
    dashboard re-renders on pipeline state change without a full reload.
    """
    service = get_health_service()
    ingestion_stats_data = None
    error_message = None

    try:
        stats = service.get_ingestion_stats()
        ingestion_stats_data = stats.__dict__
    except HealthServiceError as e:
        error_message = str(e)

    pipeline = _pipeline_view(ingestion_stats_data)

    context = {
        "ingestion_stats": ingestion_stats_data,
        "pipeline": pipeline,
        "error_message": error_message,
    }

    if request.headers.get("HX-Request"):
        return render_template("health/_ingestion_content.html", **context)

    return render_template("health/ingestion.html", **context)


@health_bp.route("/api")
def health_api() -> dict[str, str]:
    """Health check endpoint for the UI itself."""
    return {"status": "healthy"}
