"""Tests for CollaborationService — message persistence and active user tracking."""

from unittest.mock import MagicMock, patch

import pytest

from beeper_ui.services.collaboration_service import (
    COLLABORATION_COLLECTION,
    CollaborationMessage,
    CollaborationService,
    get_collaboration_service,
    reset_collaboration_service,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the singleton before each test."""
    reset_collaboration_service()
    yield
    reset_collaboration_service()


def _make_message(
    investigation_id: str = "inv-001",
    user: str = "user",
    content: str = "test message",
    message_type: str = "user_message",
    timestamp: str = "2026-03-16T12:00:00+00:00",
    msg_id: str = "msg-001",
) -> CollaborationMessage:
    return CollaborationMessage(
        id=msg_id,
        investigation_id=investigation_id,
        user=user,
        role=user,
        message_type=message_type,
        content=content,
        timestamp=timestamp,
    )


class TestCollaborationMessage:
    """Tests for CollaborationMessage dataclass."""

    def test_to_payload(self):
        msg = _make_message()
        payload = msg.to_payload()
        assert payload["id"] == "msg-001"
        assert payload["investigation_id"] == "inv-001"
        assert payload["user"] == "user"
        assert payload["message_type"] == "user_message"
        assert payload["content"] == "test message"
        assert payload["timestamp"] == "2026-03-16T12:00:00+00:00"

    def test_from_payload(self):
        payload = {
            "id": "msg-002",
            "investigation_id": "inv-002",
            "user": "admin",
            "role": "admin",
            "message_type": "system_response",
            "content": "Beeper response",
            "timestamp": "2026-03-16T12:01:00+00:00",
        }
        msg = CollaborationMessage.from_payload(payload)
        assert msg.id == "msg-002"
        assert msg.investigation_id == "inv-002"
        assert msg.user == "admin"
        assert msg.message_type == "system_response"

    def test_from_payload_missing_fields(self):
        msg = CollaborationMessage.from_payload({})
        assert msg.id == ""
        assert msg.content == ""

    def test_roundtrip(self):
        original = _make_message()
        payload = original.to_payload()
        restored = CollaborationMessage.from_payload(payload)
        assert restored.id == original.id
        assert restored.content == original.content
        assert restored.timestamp == original.timestamp


class TestCollaborationServiceActiveUsers:
    """Tests for in-memory active user tracking."""

    @patch("beeper_ui.services.collaboration_service.QdrantClient")
    def test_add_and_get_active_users(self, mock_qdrant_cls):
        mock_qdrant_cls.return_value.get_collection.return_value = True
        service = CollaborationService(qdrant_url="http://mock:6333")

        service.add_active_user("inv-001", "sid-1", "alice")
        service.add_active_user("inv-001", "sid-2", "bob")

        users = service.get_active_users("inv-001")
        assert sorted(users) == ["alice", "bob"]

    @patch("beeper_ui.services.collaboration_service.QdrantClient")
    def test_remove_active_user(self, mock_qdrant_cls):
        mock_qdrant_cls.return_value.get_collection.return_value = True
        service = CollaborationService(qdrant_url="http://mock:6333")

        service.add_active_user("inv-001", "sid-1", "alice")
        removed = service.remove_active_user("inv-001", "sid-1")

        assert removed == "alice"
        assert service.get_active_users("inv-001") == []

    @patch("beeper_ui.services.collaboration_service.QdrantClient")
    def test_remove_nonexistent_user(self, mock_qdrant_cls):
        mock_qdrant_cls.return_value.get_collection.return_value = True
        service = CollaborationService(qdrant_url="http://mock:6333")

        removed = service.remove_active_user("inv-001", "unknown-sid")
        assert removed is None

    @patch("beeper_ui.services.collaboration_service.QdrantClient")
    def test_get_active_users_empty_room(self, mock_qdrant_cls):
        mock_qdrant_cls.return_value.get_collection.return_value = True
        service = CollaborationService(qdrant_url="http://mock:6333")

        assert service.get_active_users("nonexistent") == []

    @patch("beeper_ui.services.collaboration_service.QdrantClient")
    def test_duplicate_user_deduplicated(self, mock_qdrant_cls):
        mock_qdrant_cls.return_value.get_collection.return_value = True
        service = CollaborationService(qdrant_url="http://mock:6333")

        service.add_active_user("inv-001", "sid-1", "alice")
        service.add_active_user("inv-001", "sid-2", "alice")

        users = service.get_active_users("inv-001")
        assert users == ["alice"]

    @patch("beeper_ui.services.collaboration_service.QdrantClient")
    def test_room_cleanup_on_last_user_leave(self, mock_qdrant_cls):
        mock_qdrant_cls.return_value.get_collection.return_value = True
        service = CollaborationService(qdrant_url="http://mock:6333")

        service.add_active_user("inv-001", "sid-1", "alice")
        service.remove_active_user("inv-001", "sid-1")

        assert "inv-001" not in service._active_rooms


    @patch("beeper_ui.services.collaboration_service.QdrantClient")
    def test_get_all_room_ids(self, mock_qdrant_cls):
        mock_qdrant_cls.return_value.get_collection.return_value = True
        service = CollaborationService(qdrant_url="http://mock:6333")

        service.add_active_user("inv-001", "sid-1", "alice")
        service.add_active_user("inv-002", "sid-2", "bob")

        room_ids = service.get_all_room_ids()
        assert sorted(room_ids) == ["inv-001", "inv-002"]

    @patch("beeper_ui.services.collaboration_service.QdrantClient")
    def test_get_all_room_ids_empty(self, mock_qdrant_cls):
        mock_qdrant_cls.return_value.get_collection.return_value = True
        service = CollaborationService(qdrant_url="http://mock:6333")

        assert service.get_all_room_ids() == []


class TestCollaborationServiceMessages:
    """Tests for message persistence via Qdrant."""

    @patch("beeper_ui.services.collaboration_service.QdrantClient")
    def test_store_message_success(self, mock_qdrant_cls):
        mock_client = mock_qdrant_cls.return_value
        mock_client.get_collection.return_value = True

        service = CollaborationService(qdrant_url="http://mock:6333")
        msg = _make_message()

        result = service.store_message(msg)

        assert result is True
        mock_client.upsert.assert_called_once()
        call_args = mock_client.upsert.call_args
        assert call_args.kwargs["collection_name"] == COLLABORATION_COLLECTION

    @patch("beeper_ui.services.collaboration_service.QdrantClient")
    def test_store_message_failure(self, mock_qdrant_cls):
        mock_client = mock_qdrant_cls.return_value
        mock_client.get_collection.return_value = True
        mock_client.upsert.side_effect = Exception("Qdrant down")

        service = CollaborationService(qdrant_url="http://mock:6333")
        msg = _make_message()

        result = service.store_message(msg)
        assert result is False

    @patch("beeper_ui.services.collaboration_service.QdrantClient")
    def test_get_message_history(self, mock_qdrant_cls):
        mock_client = mock_qdrant_cls.return_value
        mock_client.get_collection.return_value = True

        point1 = MagicMock()
        point1.payload = _make_message(
            msg_id="m1", timestamp="2026-03-16T12:00:00+00:00", content="first"
        ).to_payload()
        point2 = MagicMock()
        point2.payload = _make_message(
            msg_id="m2", timestamp="2026-03-16T12:01:00+00:00", content="second"
        ).to_payload()

        mock_client.scroll.return_value = ([point2, point1], None)

        service = CollaborationService(qdrant_url="http://mock:6333")
        history = service.get_message_history("inv-001")

        assert len(history) == 2
        assert history[0].content == "first"
        assert history[1].content == "second"

    @patch("beeper_ui.services.collaboration_service.QdrantClient")
    def test_get_message_history_with_since_timestamp(self, mock_qdrant_cls):
        mock_client = mock_qdrant_cls.return_value
        mock_client.get_collection.return_value = True

        point1 = MagicMock()
        point1.payload = _make_message(
            msg_id="m1", timestamp="2026-03-16T12:00:00+00:00", content="old"
        ).to_payload()
        point2 = MagicMock()
        point2.payload = _make_message(
            msg_id="m2", timestamp="2026-03-16T12:05:00+00:00", content="new"
        ).to_payload()

        mock_client.scroll.return_value = ([point1, point2], None)

        service = CollaborationService(qdrant_url="http://mock:6333")
        history = service.get_message_history(
            "inv-001", since_timestamp="2026-03-16T12:01:00+00:00"
        )

        assert len(history) == 1
        assert history[0].content == "new"

    @patch("beeper_ui.services.collaboration_service.QdrantClient")
    def test_get_message_history_failure(self, mock_qdrant_cls):
        mock_client = mock_qdrant_cls.return_value
        mock_client.get_collection.return_value = True
        mock_client.scroll.side_effect = Exception("Connection error")

        service = CollaborationService(qdrant_url="http://mock:6333")
        history = service.get_message_history("inv-001")

        assert history == []

    @patch("beeper_ui.services.collaboration_service.QdrantClient")
    def test_ensure_collection_creates_on_missing(self, mock_qdrant_cls):
        mock_client = mock_qdrant_cls.return_value
        mock_client.get_collection.side_effect = Exception("Not found")

        CollaborationService(qdrant_url="http://mock:6333")

        mock_client.create_collection.assert_called_once()


class TestCollaborationServiceSingleton:
    """Tests for module-level singleton."""

    @patch("beeper_ui.services.collaboration_service.QdrantClient")
    def test_get_singleton(self, mock_qdrant_cls):
        mock_qdrant_cls.return_value.get_collection.return_value = True
        svc1 = get_collaboration_service()
        svc2 = get_collaboration_service()
        assert svc1 is svc2

    @patch("beeper_ui.services.collaboration_service.QdrantClient")
    def test_reset_singleton(self, mock_qdrant_cls):
        mock_qdrant_cls.return_value.get_collection.return_value = True
        svc1 = get_collaboration_service()
        reset_collaboration_service()
        svc2 = get_collaboration_service()
        assert svc1 is not svc2
