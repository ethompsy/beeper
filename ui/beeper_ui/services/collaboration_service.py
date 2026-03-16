"""Collaboration service for real-time investigation messaging.

Handles message persistence in Qdrant and active user tracking
for WebSocket-based investigation collaboration.
"""

import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

logger = logging.getLogger(__name__)

COLLABORATION_COLLECTION = "collaboration_messages"
VECTOR_SIZE = 1536


@dataclass
class CollaborationMessage:
    """A collaboration message in an investigation room."""

    id: str
    investigation_id: str
    user: str
    role: str
    message_type: str  # user_message, system_response, user_joined, user_left
    content: str
    timestamp: str  # ISO format

    def to_payload(self) -> dict:
        """Convert to Qdrant payload dict."""
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: dict) -> "CollaborationMessage":
        """Create from Qdrant payload dict."""
        return cls(
            id=payload.get("id", ""),
            investigation_id=payload.get("investigation_id", ""),
            user=payload.get("user", ""),
            role=payload.get("role", ""),
            message_type=payload.get("message_type", ""),
            content=payload.get("content", ""),
            timestamp=payload.get("timestamp", ""),
        )


@dataclass
class _ActiveRoom:
    """Tracks active users in an investigation room."""

    users: dict[str, str] = field(default_factory=dict)  # sid -> user


class CollaborationService:
    """Service for managing collaboration messages and active users."""

    def __init__(self, qdrant_url: Optional[str] = None) -> None:
        """Initialize the collaboration service.

        Args:
            qdrant_url: Qdrant server URL. Defaults to QDRANT_URL env var.
        """
        url = qdrant_url or os.environ.get("QDRANT_URL", "http://localhost:6333")
        self._client = QdrantClient(url=url, timeout=5.0)
        self._active_rooms: dict[str, _ActiveRoom] = {}
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Create the collaboration_messages collection if it doesn't exist."""
        try:
            self._client.get_collection(COLLABORATION_COLLECTION)
        except (UnexpectedResponse, Exception):
            try:
                self._client.create_collection(
                    collection_name=COLLABORATION_COLLECTION,
                    vectors_config=VectorParams(
                        size=VECTOR_SIZE,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info("Created collection: %s", COLLABORATION_COLLECTION)
            except Exception:
                logger.warning(
                    "Could not create collection %s — will retry on first write",
                    COLLABORATION_COLLECTION,
                )

    def store_message(self, message: CollaborationMessage) -> bool:
        """Store a collaboration message in Qdrant.

        Args:
            message: The message to store.

        Returns:
            True if stored successfully, False otherwise.
        """
        point = PointStruct(
            id=message.id,
            vector=[0.0] * VECTOR_SIZE,
            payload=message.to_payload(),
        )
        try:
            self._client.upsert(
                collection_name=COLLABORATION_COLLECTION,
                points=[point],
            )
            return True
        except Exception:
            logger.exception("Failed to store collaboration message %s", message.id)
            return False

    def get_message_history(
        self,
        investigation_id: str,
        since_timestamp: Optional[str] = None,
        limit: int = 100,
    ) -> list[CollaborationMessage]:
        """Retrieve message history for an investigation.

        Args:
            investigation_id: The investigation to get messages for.
            since_timestamp: Optional ISO timestamp to filter messages after.
            limit: Maximum number of messages to return.

        Returns:
            List of messages ordered by timestamp.
        """
        must_conditions = [
            FieldCondition(
                key="investigation_id",
                match=MatchValue(value=investigation_id),
            ),
        ]

        try:
            results = self._client.scroll(
                collection_name=COLLABORATION_COLLECTION,
                scroll_filter=Filter(must=must_conditions),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            points = results[0] if results else []
            messages = [CollaborationMessage.from_payload(p.payload) for p in points]

            # Sort by timestamp
            messages.sort(key=lambda m: m.timestamp)

            # Filter by since_timestamp if provided
            if since_timestamp:
                messages = [m for m in messages if m.timestamp > since_timestamp]

            return messages
        except Exception:
            logger.exception(
                "Failed to retrieve message history for investigation %s",
                investigation_id,
            )
            return []

    def add_active_user(
        self, investigation_id: str, sid: str, user: str
    ) -> None:
        """Track a user joining an investigation room.

        Args:
            investigation_id: The investigation room.
            sid: The SocketIO session ID.
            user: The user identifier.
        """
        if investigation_id not in self._active_rooms:
            self._active_rooms[investigation_id] = _ActiveRoom()
        self._active_rooms[investigation_id].users[sid] = user

    def remove_active_user(
        self, investigation_id: str, sid: str
    ) -> Optional[str]:
        """Remove a user from an investigation room.

        Args:
            investigation_id: The investigation room.
            sid: The SocketIO session ID.

        Returns:
            The user identifier that was removed, or None.
        """
        room = self._active_rooms.get(investigation_id)
        if room and sid in room.users:
            user = room.users.pop(sid)
            if not room.users:
                del self._active_rooms[investigation_id]
            return user
        return None

    def get_active_users(self, investigation_id: str) -> list[str]:
        """Get list of active users in an investigation room.

        Args:
            investigation_id: The investigation room.

        Returns:
            List of user identifiers.
        """
        room = self._active_rooms.get(investigation_id)
        if room:
            return list(set(room.users.values()))
        return []


# Module-level singleton
_collaboration_service: Optional[CollaborationService] = None


def get_collaboration_service() -> CollaborationService:
    """Get the global collaboration service instance.

    Returns:
        CollaborationService singleton instance.
    """
    global _collaboration_service
    if _collaboration_service is None:
        _collaboration_service = CollaborationService()
    return _collaboration_service


def reset_collaboration_service() -> None:
    """Reset the global collaboration service singleton (for testing)."""
    global _collaboration_service
    _collaboration_service = None
