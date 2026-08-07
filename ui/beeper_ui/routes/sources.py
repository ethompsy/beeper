"""Source status routes for Beeper UI."""

from typing import Any

from flask import Blueprint, Response, current_app, jsonify, render_template, request

from beeper_ui.middleware.permissions import require_role
from beeper_ui.services.source_service import Source, SourceService, SourceServiceError

sources_bp = Blueprint("sources", __name__, url_prefix="/sources")

# JSON API blueprint (Task 5.3 / FR34). Kept separate from the HTML
# `sources_bp` so it can live under the /api/v1 prefix the React Sources
# view (`ui/frontend/src/routes/SourcesPage.tsx`) fetches from — mirrors the
# `investigations_bp`/`investigations_api_bp` split
# (`ui/beeper_ui/routes/investigations.py`).
sources_api_bp = Blueprint("sources_api", __name__, url_prefix="/api/v1/sources")


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


def _source_to_dict(source: Source) -> dict[str, Any]:
    """Serialize a ``Source`` (including its nested error, if any) for JSON."""
    return {
        "name": source.name,
        "type": source.type,
        "endpoint": source.endpoint,
        "status": source.status,
        "last_check": source.last_check,
        "error": (
            {
                "type": source.error.type,
                "message": source.error.message,
                "details": source.error.details,
            }
            if source.error
            else None
        ),
    }


@sources_api_bp.route("/")
@require_role("user")
def sources_list_json() -> tuple[Response, int] | Response:
    """JSON list of configured sources for the React UI (Task 5.3 / FR34).

    Reuses ``SourceService.get_sources()`` exactly as the Jinja view does —
    including its dedup-by-name behavior (NFR12) — no service logic is
    reimplemented here. Mirrors ``investigations_list_json``'s contract
    (`ui/beeper_ui/routes/investigations.py`): a bare JSON array on success,
    ``{"error": ...}`` with HTTP 503 when the operator is unreachable.
    """
    service = get_source_service()
    try:
        sources = service.get_sources()
    except SourceServiceError as e:
        return jsonify({"error": "operator_unavailable", "message": str(e)}), 503

    return jsonify([_source_to_dict(s) for s in sources])
