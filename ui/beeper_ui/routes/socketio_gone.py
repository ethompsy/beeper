"""Defined response for the retired `/socket.io/*` mount.

Task 6.2a / ADR 0001 §0(b): real-time investigation collaboration (chat,
annotations, redirects, fix approve/reject) was dropped during the React
migration — the code surface only, per the ADR's explicit condition. The
persisted `collaboration_messages` Qdrant collection is left in place and
is still read by the Jinja investigation-detail view's "human interventions"
history (see `beeper_ui.routes.investigations.investigation_detail` and
`beeper_ui.services.collaboration_service`).

Flask-SocketIO is no longer initialized (`init_socketio` removed from
`beeper_ui.app.create_app`), so without this blueprint any `/socket.io/*`
request — Engine.IO polling or WebSocket upgrade attempts from a stale
client — would fall through to Flask's default, unstyled HTML 404,
inconsistent with the app's RFC 7807 (`application/problem+json`)
convention used elsewhere (see `beeper_ui.middleware.permissions`). This
blueprint registers an explicit route instead, returning the exact `410
Gone` body specified in ADR 0001 §6.
"""

from flask import Blueprint, Response, jsonify, request

socketio_gone_bp = Blueprint("socketio_gone", __name__, url_prefix="/socket.io")

# Engine.IO's polling transport issues GET and POST; the WebSocket upgrade
# handshake starts as a GET. Accept every method here so any client attempt
# — old or new — gets the defined 410 response rather than a 405.
_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]

_DETAIL = (
    "Real-time investigation collaboration (chat/annotations/approvals/"
    "redirections) was retired during the React migration. See "
    "docs/specs/decisions/0001-rbac-and-realtime-collaboration-in-react-ui.md."
)


def _gone_response() -> tuple[Response, int, dict[str, str]]:
    """Build the RFC 7807 `410 Gone` response specified in ADR 0001 §6."""
    body = {
        "type": "https://beeper.dev/errors/feature-retired",
        "title": "Collaboration Feature Retired",
        "status": 410,
        "detail": _DETAIL,
        "instance": request.path,
    }
    return jsonify(body), 410, {"Content-Type": "application/problem+json"}


@socketio_gone_bp.route("/", methods=_METHODS)
def socketio_root_gone() -> tuple[Response, int, dict[str, str]]:
    """Return 410 Gone for the removed SocketIO mount root (`/socket.io/`)."""
    return _gone_response()


@socketio_gone_bp.route("/<path:_subpath>", methods=_METHODS)
def socketio_subpath_gone(_subpath: str) -> tuple[Response, int, dict[str, str]]:
    """Return 410 Gone for any retired `/socket.io/*` sub-path.

    Covers Engine.IO polling (`/socket.io/?EIO=4&transport=polling`, which
    matches the root route above) and any other sub-path a stale client
    might probe (`/socket.io/socket.io.js`, etc.).
    """
    return _gone_response()
