"""Tests for WebSocket investigation collaboration event handlers.

Uses a module-scoped app so Flask-SocketIO's init_app() runs only once,
avoiding server recreation issues between tests. Each test gets a fresh
test client and mocked Qdrant backend.
"""

from unittest.mock import MagicMock, patch

import pytest

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig
from beeper_ui.services.collaboration_service import (
    CollaborationMessage,
    CollaborationService,
    reset_collaboration_service,
)
from beeper_ui.websocket import socketio


@pytest.fixture(scope="module")
def ws_app():
    """Module-scoped app — init_socketio runs only once."""
    application = create_app(TestingConfig)
    return application


@pytest.fixture(autouse=True)
def _reset_collab():
    """Reset collaboration service singleton for each test."""
    reset_collaboration_service()
    yield
    reset_collaboration_service()


@pytest.fixture
def ws_client(ws_app):
    """Create a Flask-SocketIO test client with mocked Qdrant backend.

    Patches QdrantClient so CollaborationService works without a real Qdrant.
    """
    mock_qdrant = MagicMock()
    mock_qdrant.get_collection.return_value = True
    mock_qdrant.scroll.return_value = ([], None)

    with patch(
        "beeper_ui.services.collaboration_service.QdrantClient",
        return_value=mock_qdrant,
    ):
        client = socketio.test_client(ws_app)
        yield client, mock_qdrant
        if client.is_connected():
            client.disconnect()


class TestJoinInvestigation:
    """Tests for join_investigation event handler."""

    def test_join_sends_empty_history(self, ws_client):
        client, _ = ws_client
        client.emit("join_investigation", {"investigation_id": "inv-001"})
        received = client.get_received()
        event_names = [r["name"] for r in received]
        assert "message_history" in event_names
        history = next(r for r in received if r["name"] == "message_history")
        assert history["args"][0] == []

    def test_join_broadcasts_user_joined(self, ws_client):
        client, _ = ws_client
        client.emit("join_investigation", {"investigation_id": "inv-001"})
        received = client.get_received()
        assert "user_joined" in [r["name"] for r in received]

    def test_join_user_joined_has_active_users(self, ws_client):
        client, _ = ws_client
        client.emit("join_investigation", {"investigation_id": "inv-001"})
        received = client.get_received()
        joined = next(r for r in received if r["name"] == "user_joined")
        assert isinstance(joined["args"][0]["active_users"], list)
        assert len(joined["args"][0]["active_users"]) > 0

    def test_join_stores_message_in_qdrant(self, ws_client):
        client, mock_qdrant = ws_client
        client.emit("join_investigation", {"investigation_id": "inv-001"})
        # Should upsert the join message
        mock_qdrant.upsert.assert_called()

    def test_join_missing_investigation_id(self, ws_client):
        client, _ = ws_client
        client.emit("join_investigation", {})
        received = client.get_received()
        errors = [r for r in received if r["name"] == "error"]
        assert len(errors) == 1
        assert "investigation_id" in errors[0]["args"][0]["message"]

    def test_join_with_last_seen_sends_history(self, ws_client):
        client, mock_qdrant = ws_client
        # Set up scroll to return a message
        point = MagicMock()
        point.payload = {
            "id": "m1",
            "investigation_id": "inv-001",
            "user": "admin",
            "role": "admin",
            "message_type": "user_message",
            "content": "old message",
            "timestamp": "2026-03-16T12:05:00+00:00",
        }
        mock_qdrant.scroll.return_value = ([point], None)

        client.emit("join_investigation", {
            "investigation_id": "inv-001",
            "last_seen_timestamp": "2026-03-16T12:00:00+00:00",
        })

        received = client.get_received()
        history = next(r for r in received if r["name"] == "message_history")
        assert len(history["args"][0]) == 1
        assert history["args"][0][0]["content"] == "old message"


class TestLeaveInvestigation:
    """Tests for leave_investigation event handler."""

    def test_leave_broadcasts_user_left(self, ws_client):
        client, _ = ws_client
        # First join, then leave
        client.emit("join_investigation", {"investigation_id": "inv-001"})
        client.get_received()  # Clear

        client.emit("leave_investigation", {"investigation_id": "inv-001"})
        received = client.get_received()
        assert "user_left" in [r["name"] for r in received]

    def test_leave_stores_message(self, ws_client):
        client, mock_qdrant = ws_client
        client.emit("join_investigation", {"investigation_id": "inv-001"})
        mock_qdrant.upsert.reset_mock()

        client.emit("leave_investigation", {"investigation_id": "inv-001"})
        mock_qdrant.upsert.assert_called()

    def test_leave_missing_id_no_crash(self, ws_client):
        client, _ = ws_client
        client.emit("leave_investigation", {})
        # Should not crash


class TestSendMessage:
    """Tests for send_message event handler."""

    def _join_room(self, client):
        """Helper: join investigation room and clear received events."""
        client.emit("join_investigation", {"investigation_id": "inv-001"})
        client.get_received()  # Clear join events

    def test_stores_and_broadcasts(self, ws_client):
        client, mock_qdrant = ws_client
        self._join_room(client)

        client.emit("send_message", {
            "investigation_id": "inv-001",
            "content": "Hello team!",
        })

        # Check broadcast
        received = client.get_received()
        msgs = [r for r in received if r["name"] == "new_message"]
        assert len(msgs) == 1
        assert msgs[0]["args"][0]["content"] == "Hello team!"
        assert msgs[0]["args"][0]["message_type"] == "user_message"

        # Check Qdrant upsert
        mock_qdrant.upsert.assert_called()

    def test_missing_content_returns_error(self, ws_client):
        client, _ = ws_client
        client.emit("send_message", {"investigation_id": "inv-001", "content": ""})
        received = client.get_received()
        assert any(r["name"] == "error" for r in received)

    def test_missing_investigation_id_returns_error(self, ws_client):
        client, _ = ws_client
        client.emit("send_message", {"content": "Hello"})
        received = client.get_received()
        assert any(r["name"] == "error" for r in received)

    def test_strips_whitespace(self, ws_client):
        client, _ = ws_client
        self._join_room(client)

        client.emit("send_message", {
            "investigation_id": "inv-001",
            "content": "  Hello!  ",
        })
        received = client.get_received()
        msgs = [r for r in received if r["name"] == "new_message"]
        assert msgs[0]["args"][0]["content"] == "Hello!"

    def test_message_has_uuid_id(self, ws_client):
        client, _ = ws_client
        self._join_room(client)

        client.emit("send_message", {"investigation_id": "inv-001", "content": "Test"})
        received = client.get_received()
        msgs = [r for r in received if r["name"] == "new_message"]
        assert len(msgs[0]["args"][0]["id"]) == 36

    def test_message_has_timestamp(self, ws_client):
        client, _ = ws_client
        self._join_room(client)

        client.emit("send_message", {"investigation_id": "inv-001", "content": "Test"})
        received = client.get_received()
        msgs = [r for r in received if r["name"] == "new_message"]
        assert "T" in msgs[0]["args"][0]["timestamp"]  # ISO format


class TestDisconnect:
    """Tests for disconnect handler."""

    def test_disconnect_no_crash(self, ws_client):
        client, _ = ws_client
        client.disconnect()


class TestSocketIOInit:
    """Tests for SocketIO initialization."""

    def test_socketio_initialized(self, ws_app):
        assert socketio.server is not None

    def test_client_connects(self, ws_client):
        client, _ = ws_client
        assert client.is_connected()

    def test_client_disconnects(self, ws_client):
        client, _ = ws_client
        client.disconnect()
        assert not client.is_connected()


class TestTemplateIntegration:
    """Tests for template rendering with collaboration panel."""

    def test_collab_panel_renders(self, ws_app):
        with ws_app.test_request_context():
            tmpl = ws_app.jinja_env.get_template(
                "investigations/_collaboration_panel.html"
            )
            html = tmpl.render(investigation=MagicMock(id="inv-test"))
            assert 'id="collab-panel"' in html
            assert 'data-investigation-id="inv-test"' in html
            assert 'id="collab-messages"' in html
            assert 'id="collab-input"' in html

    def test_detail_includes_socketio_scripts(self, ws_app):
        with ws_app.test_request_context():
            tmpl = ws_app.jinja_env.get_template("investigations/detail.html")
            html = tmpl.render(
                investigation=MagicMock(id="inv-test"),
                error_message=None,
                investigation_id="inv-test",
            )
            assert "socket.io" in html
            assert "investigation-collab.js" in html
