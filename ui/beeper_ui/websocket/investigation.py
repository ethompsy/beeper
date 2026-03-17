"""WebSocket event handlers for investigation collaboration.

Handles join/leave rooms, message sending/receiving, and reconnection
with message history replay.
"""

import logging
import uuid
from datetime import datetime, timezone

from flask import g, request
from flask_socketio import emit, join_room, leave_room

from beeper_ui.services import collaboration_service as collab_svc
from beeper_ui.services.collaboration_service import CollaborationMessage
from beeper_ui.websocket import socketio

logger = logging.getLogger(__name__)


def _room_name(investigation_id: str) -> str:
    """Build the SocketIO room name for an investigation."""
    return f"investigation:{investigation_id}"


def _now_iso() -> str:
    """Return current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def _get_user() -> str:
    """Get user identifier from Flask g context."""
    return getattr(g, "user_role", "user")


@socketio.on("join_investigation")
def handle_join(data: dict) -> None:
    """Handle a user joining an investigation collaboration room.

    Args:
        data: Dict with 'investigation_id' and optional 'last_seen_timestamp'.
    """
    investigation_id = data.get("investigation_id", "")
    if not investigation_id:
        emit("error", {"message": "investigation_id is required"})
        return

    last_seen = data.get("last_seen_timestamp")
    room = _room_name(investigation_id)
    user = _get_user()
    sid = request.sid  # type: ignore[attr-defined]

    join_room(room)

    # Track active user
    service = collab_svc.get_collaboration_service()
    service.add_active_user(investigation_id, sid, user)

    # Send message history to the joining client
    history = service.get_message_history(
        investigation_id, since_timestamp=last_seen
    )
    emit("message_history", [msg.to_payload() for msg in history])

    # Store and broadcast join event
    join_msg = CollaborationMessage(
        id=str(uuid.uuid4()),
        investigation_id=investigation_id,
        user=user,
        role=user,
        message_type="user_joined",
        content=f"{user} joined the investigation",
        timestamp=_now_iso(),
    )
    service.store_message(join_msg)

    active_users = service.get_active_users(investigation_id)
    emit(
        "user_joined",
        {"user": user, "active_users": active_users},
        room=room,
    )


@socketio.on("leave_investigation")
def handle_leave(data: dict) -> None:
    """Handle a user leaving an investigation collaboration room.

    Args:
        data: Dict with 'investigation_id'.
    """
    investigation_id = data.get("investigation_id", "")
    if not investigation_id:
        return

    room = _room_name(investigation_id)
    sid = request.sid  # type: ignore[attr-defined]

    service = collab_svc.get_collaboration_service()
    user = service.remove_active_user(investigation_id, sid)
    if user is None:
        user = _get_user()

    # Store and broadcast leave event BEFORE leaving the room
    leave_msg = CollaborationMessage(
        id=str(uuid.uuid4()),
        investigation_id=investigation_id,
        user=user,
        role=user,
        message_type="user_left",
        content=f"{user} left the investigation",
        timestamp=_now_iso(),
    )
    service.store_message(leave_msg)

    active_users = service.get_active_users(investigation_id)
    emit(
        "user_left",
        {"user": user, "active_users": active_users},
        room=room,
    )

    leave_room(room)


@socketio.on("send_message")
def handle_send_message(data: dict) -> None:
    """Handle a user sending a collaboration message.

    Args:
        data: Dict with 'investigation_id' and 'content'.
    """
    investigation_id = data.get("investigation_id", "")
    content = data.get("content", "").strip()

    if not investigation_id or not content:
        emit("error", {"message": "investigation_id and content are required"})
        return

    user = _get_user()
    room = _room_name(investigation_id)

    message = CollaborationMessage(
        id=str(uuid.uuid4()),
        investigation_id=investigation_id,
        user=user,
        role=user,
        message_type="user_message",
        content=content,
        timestamp=_now_iso(),
    )

    service = collab_svc.get_collaboration_service()
    service.store_message(message)

    # Broadcast to all users in the room
    emit("new_message", message.to_payload(), room=room)


@socketio.on("disconnect")
def handle_disconnect() -> None:
    """Handle client disconnection — clean up active user tracking."""
    sid = request.sid  # type: ignore[attr-defined]
    service = collab_svc.get_collaboration_service()

    # Remove user from all rooms they were in
    for inv_id in service.get_all_room_ids():
        user = service.remove_active_user(inv_id, sid)
        if user:
            room = _room_name(inv_id)
            active_users = service.get_active_users(inv_id)
            emit(
                "user_left",
                {"user": user, "active_users": active_users},
                room=room,
            )
