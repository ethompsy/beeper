"""Source status routes for Beeper UI."""

from typing import Any

from flask import Blueprint, Response, current_app, jsonify, redirect

from beeper_ui.middleware.permissions import require_role
from beeper_ui.routes.react_registry import build_app_redirect_target
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
def list_sources() -> Response:
    """Retired (Task 6.3 / D13-D14): the Jinja sources list page is removed.

    No retained template links to ``url_for('sources.list_sources')``, but
    this route is kept registered (not deleted) for the same defensive-
    fallback reasoning and uniform "retired → redirect" pattern used across
    every migrated route in this task — see
    ``knowledge.py``'s ``kb_index()`` docstring. A real browser request
    never reaches this body: the ``before_request`` hook always redirects
    `/sources` (bare) to `/app/sources` first. This route is now free of
    any reference to the removed ``list.html``/``_list_content.html``
    templates.
    """
    return redirect(build_app_redirect_target("/sources/"))


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
