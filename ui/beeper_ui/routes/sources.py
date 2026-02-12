"""Source status routes for Beeper UI."""

from flask import Blueprint, current_app, render_template, request

from beeper_ui.services.source_service import SourceService, SourceServiceError

sources_bp = Blueprint("sources", __name__, url_prefix="/sources")


def get_source_service() -> SourceService:
    """Get configured SourceService instance."""
    return SourceService(
        operator_url=current_app.config["OPERATOR_URL"],
        timeout=current_app.config["OPERATOR_TIMEOUT"],
    )


@sources_bp.route("/")
def list_sources() -> str:
    """Display list of all configured sources.

    For HTMX requests (auto-refresh), returns only the list content partial.
    For full page requests, returns the complete page.
    """
    service = get_source_service()
    error_message = None
    sources = []

    try:
        sources = service.get_sources()
    except SourceServiceError as e:
        error_message = str(e)

    # Check if this is an HTMX request (for partial updates)
    if request.headers.get("HX-Request"):
        return render_template(
            "sources/_list_content.html",
            sources=sources,
            error_message=error_message,
        )

    return render_template(
        "sources/list.html",
        sources=sources,
        error_message=error_message,
    )
