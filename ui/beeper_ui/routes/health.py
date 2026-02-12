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
    components: dict = {}
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


@health_bp.route("/api")
def health_api() -> dict[str, str]:
    """Health check endpoint for the UI itself."""
    return {"status": "healthy"}
