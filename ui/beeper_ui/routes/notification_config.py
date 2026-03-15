"""Notification configuration UI routes.

Provides the notification channel listing page and test notification
endpoint for verifying channel configuration from the UI.
"""

import logging
from typing import Any

from flask import Blueprint, current_app, jsonify, render_template, request

from beeper_ui.middleware.permissions import require_role
from beeper_ui.services.notification_channel_service import (
    NotificationChannelService,
    NotificationChannelServiceError,
)

logger = logging.getLogger(__name__)

notification_config_bp = Blueprint(
    "notification_config", __name__, url_prefix="/notifications"
)


def _get_channel_service() -> NotificationChannelService:
    """Get configured NotificationChannelService instance."""
    return NotificationChannelService(
        operator_url=current_app.config["OPERATOR_URL"],
        timeout=current_app.config["OPERATOR_TIMEOUT"],
    )


@notification_config_bp.route("/")
@require_role("user")
def list_channels() -> str:
    """Display all configured notification channels.

    For HTMX requests, returns only the channel list partial.
    For full page requests, returns the complete page.
    """
    service = _get_channel_service()
    error_message = None
    channels: list[dict[str, Any]] = []

    try:
        channels = service.list_channels()
    except NotificationChannelServiceError as e:
        error_message = str(e)
    finally:
        service.close()

    if request.headers.get("HX-Request"):
        return render_template(
            "notifications/_channel_list.html",
            channels=channels,
            error_message=error_message,
        )

    return render_template(
        "notifications/config.html",
        channels=channels,
        error_message=error_message,
    )


@notification_config_bp.route("/test", methods=["POST"])
@require_role("user")
def test_channel() -> tuple[Any, int]:
    """Send a test notification through a channel.

    Request body (JSON):
        {
            "channel_name": "sre-slack",
            "channel_type": "slack"
        }

    Returns:
        HTML partial with test result for HTMX swap, or JSON for API clients.
    """
    data = request.get_json(silent=True)
    if not data:
        result = {"success": False, "error": "Request body is required"}
        if request.headers.get("HX-Request"):
            return render_template("notifications/_test_result.html", result=result), 400
        return jsonify(result), 400

    channel_name = data.get("channel_name", "")
    channel_type = data.get("channel_type", "")

    if not channel_name or not channel_type:
        result = {"success": False, "error": "channel_name and channel_type are required"}
        if request.headers.get("HX-Request"):
            return render_template("notifications/_test_result.html", result=result), 400
        return jsonify(result), 400

    service = _get_channel_service()
    try:
        result = service.send_test_notification(channel_name, channel_type)
        status_code = 200 if result.get("success") else 502
        if request.headers.get("HX-Request"):
            return render_template("notifications/_test_result.html", result=result), status_code
        return jsonify(result), status_code
    except NotificationChannelServiceError as e:
        logger.error("Test notification failed for %s: %s", channel_name, str(e))
        result = {
            "success": False,
            "message": f"Test notification failed for {channel_name}",
            "error": str(e),
        }
        if request.headers.get("HX-Request"):
            return render_template("notifications/_test_result.html", result=result), 502
        return jsonify(result), 502
    finally:
        service.close()
