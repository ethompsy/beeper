"""Notification delivery API routes.

Provides the delivery endpoint called by the operator's outbox worker
to deliver notifications through configured channels (Slack, etc.).
"""

import logging
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from beeper_ui.middleware.permissions import require_role
from beeper_ui.services.notification_service import (
    NotificationDeliveryService,
    NotificationServiceError,
)

logger = logging.getLogger(__name__)

notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/v1/notifications")


@notifications_bp.route("/deliver", methods=["POST"])
@require_role("user")
def deliver_notification() -> tuple[Any, int]:
    """Deliver a notification through the appropriate channel.

    Accepts an outbox entry and channel configuration, delivers via
    the appropriate channel notifier, and returns delivery status.

    Request body:
        {
            "entry": { outbox entry fields },
            "channel_config": { channel configuration },
            "bot_token": "optional-pre-resolved-token"
        }

    Returns:
        JSON with delivery status and details.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "error": "Request body is required"}), 400

    entry = data.get("entry")
    channel_config = data.get("channel_config")

    if not entry:
        return jsonify({"status": "error", "error": "entry is required"}), 400
    if not channel_config:
        return jsonify({"status": "error", "error": "channel_config is required"}), 400

    if not entry.get("investigation_id"):
        return jsonify({"status": "error", "error": "entry.investigation_id is required"}), 400

    bot_token: str | None = data.get("bot_token")

    svc = NotificationDeliveryService(
        operator_url=current_app.config["OPERATOR_URL"],
        timeout=current_app.config["OPERATOR_TIMEOUT"],
    )
    try:
        result = svc.process_outbox_entry(entry, channel_config, bot_token=bot_token)
        status_code = 200 if result.get("status") == "delivered" else 202
        return jsonify(result), status_code
    except NotificationServiceError as e:
        logger.error("Notification delivery failed: %s (retryable=%s)", str(e), e.retryable)
        return (
            jsonify(
                {
                    "status": "failed",
                    "error": str(e),
                    "retryable": e.retryable,
                }
            ),
            502 if e.retryable else 422,
        )
    except Exception as e:
        logger.exception("Unexpected error in notification delivery: %s", str(e))
        return (
            jsonify(
                {
                    "status": "failed",
                    "error": "Internal server error",
                    "retryable": True,
                }
            ),
            500,
        )
    finally:
        svc.close()
