"""WebSocket module for real-time investigation collaboration.

Implements Flask-SocketIO for bidirectional communication during
active investigations. Uses the two-channel pattern:
- SocketIO: collaboration messages, annotations, redirections, approvals
- SSE (existing): step progress, findings, evidence streaming
"""

from flask import Flask
from flask_socketio import SocketIO

socketio = SocketIO()


def init_socketio(app: Flask) -> SocketIO:
    """Initialize Flask-SocketIO on the Flask application.

    Args:
        app: Flask application instance.

    Returns:
        Configured SocketIO instance.
    """
    # Import event handlers BEFORE init_app so decorators store in
    # self.handlers (survives server recreation on subsequent init_app calls)
    from beeper_ui.websocket import investigation  # noqa: F401

    socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")

    return socketio
