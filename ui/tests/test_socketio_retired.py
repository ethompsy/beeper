"""Tests for the retired `/socket.io/*` mount (Task 6.2a / ADR 0001 §0(b)).

Flask-SocketIO is no longer initialized. Without a defined response, any
`/socket.io/*` request would fall through to Flask's default, unstyled HTML
404 — this asserts the explicit `410 Gone` + `application/problem+json`
contract from ADR 0001 §6 instead.
"""

import pytest
from flask import Flask
from flask.testing import FlaskClient

EXPECTED_TYPE = "https://beeper.dev/errors/feature-retired"
EXPECTED_TITLE = "Collaboration Feature Retired"
EXPECTED_DETAIL = (
    "Real-time investigation collaboration (chat/annotations/approvals/"
    "redirections) was retired during the React migration. See "
    "docs/specs/decisions/0001-rbac-and-realtime-collaboration-in-react-ui.md."
)


class TestSocketIORootGone:
    """`/socket.io/` (Engine.IO polling handshake root)."""

    def test_get_returns_410(self, client: FlaskClient) -> None:
        resp = client.get("/socket.io/")
        assert resp.status_code == 410

    def test_content_type_is_problem_json(self, client: FlaskClient) -> None:
        resp = client.get("/socket.io/")
        assert resp.content_type == "application/problem+json"

    def test_body_matches_adr_0001_section_6_verbatim(self, client: FlaskClient) -> None:
        resp = client.get("/socket.io/")
        data = resp.get_json()
        assert data == {
            "type": EXPECTED_TYPE,
            "title": EXPECTED_TITLE,
            "status": 410,
            "detail": EXPECTED_DETAIL,
            "instance": "/socket.io/",
        }

    def test_not_a_500_and_not_a_bare_404(self, client: FlaskClient) -> None:
        resp = client.get("/socket.io/")
        assert resp.status_code not in (404, 500)

    def test_post_also_returns_410(self, client: FlaskClient) -> None:
        """Engine.IO's polling transport uses both GET and POST."""
        resp = client.post("/socket.io/")
        assert resp.status_code == 410
        assert resp.content_type == "application/problem+json"


class TestSocketIOSubpathGone:
    """Any `/socket.io/<path>` sub-path (polling query string, stale asset
    requests, WebSocket upgrade attempts routed through Werkzeug)."""

    @pytest.mark.parametrize(
        "path",
        [
            "/socket.io/socket.io.js",
            "/socket.io/1/",
            "/socket.io/?EIO=4&transport=polling",
        ],
    )
    def test_subpath_returns_410(self, client: FlaskClient, path: str) -> None:
        resp = client.get(path)
        assert resp.status_code == 410
        assert resp.content_type == "application/problem+json"

    def test_instance_reflects_actual_request_path(self, client: FlaskClient) -> None:
        resp = client.get("/socket.io/socket.io.js")
        data = resp.get_json()
        assert data["instance"] == "/socket.io/socket.io.js"

    def test_subpath_body_uses_same_type_title_detail(self, client: FlaskClient) -> None:
        resp = client.get("/socket.io/1/")
        data = resp.get_json()
        assert data["type"] == EXPECTED_TYPE
        assert data["title"] == EXPECTED_TITLE
        assert data["status"] == 410
        assert data["detail"] == EXPECTED_DETAIL

    def test_put_delete_patch_all_return_410(self, client: FlaskClient) -> None:
        for method in ("put", "delete", "patch"):
            resp = getattr(client, method)("/socket.io/some/path")
            assert resp.status_code == 410, f"{method.upper()} did not return 410"


def test_socketio_not_initialized_on_app(app: Flask) -> None:
    """`init_socketio` is no longer called from `create_app` — SocketIO's
    own event-loop machinery shouldn't be attached to the app at all."""
    assert "socketio" not in app.extensions
