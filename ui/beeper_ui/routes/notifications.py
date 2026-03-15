"""Notification delivery API routes.

Provides the delivery endpoint called by the operator's outbox worker
to deliver notifications through configured channels (Slack, PagerDuty,
email, webhooks), a digest flush endpoint for email digest compilation,
and an audit query endpoint for notification history and false page tracking.
"""

import logging
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from beeper_ui.middleware.permissions import require_role
from beeper_ui.services.notification_audit_service import NotificationAuditService
from beeper_ui.services.notification_service import (
    NotificationDeliveryService,
    NotificationServiceError,
)

logger = logging.getLogger(__name__)

notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/v1/notifications")


def _record_audit(
    entry: dict[str, Any],
    channel_config: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Record audit trail for a notification delivery. Never raises."""
    try:
        audit_svc = NotificationAuditService()
        try:
            audit_svc.record_audit(entry, channel_config, result)
        finally:
            audit_svc.close()
    except Exception as e:
        logger.warning("Audit recording failed (non-blocking): %s", e)


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
        _record_audit(entry, channel_config, result)
        status_code = 200 if result.get("status") == "delivered" else 202
        return jsonify(result), status_code
    except NotificationServiceError as e:
        logger.error("Notification delivery failed: %s (retryable=%s)", str(e), e.retryable)
        failed_result = {
            "status": "failed",
            "error": str(e),
            "retryable": e.retryable,
        }
        _record_audit(entry, channel_config, failed_result)
        return jsonify(failed_result), 502 if e.retryable else 422
    except Exception as e:
        logger.exception("Unexpected error in notification delivery: %s", str(e))
        failed_result = {
            "status": "failed",
            "error": "Internal server error",
            "retryable": True,
        }
        _record_audit(entry, channel_config, failed_result)
        return jsonify(failed_result), 500
    finally:
        svc.close()


@notifications_bp.route("/digest/flush", methods=["POST"])
@require_role("user")
def flush_email_digest() -> tuple[Any, int]:
    """Trigger email digest compilation and sending.

    Accepts a list of investigations and email channel config, compiles
    a digest email, and sends it to configured recipients.

    Request body:
        {
            "investigations": [ { investigation summaries } ],
            "channel_config": { email channel configuration },
            "period_label": "Daily"  (optional, defaults to "Daily")
        }

    Returns:
        JSON with digest delivery status.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "error": "Request body is required"}), 400

    investigations = data.get("investigations", [])
    if not investigations:
        return jsonify({"status": "error", "error": "investigations list is required"}), 400

    channel_config = data.get("channel_config")
    if not channel_config:
        return jsonify({"status": "error", "error": "channel_config is required"}), 400

    config = channel_config.get("config", {})
    smtp_host = config.get("smtp_host", "")
    if not smtp_host:
        return jsonify({"status": "error", "error": "smtp_host is required"}), 400

    recipients_str = config.get("recipients", "")
    if not recipients_str:
        return jsonify({"status": "error", "error": "recipients is required"}), 400

    recipients = [r.strip() for r in recipients_str.split(",") if r.strip()]
    period_label = data.get("period_label", "Daily")

    try:
        smtp_port = int(config.get("smtp_port", 587))
    except (ValueError, TypeError):
        smtp_port = 587
    use_tls = str(config.get("use_tls", True)).lower() != "false"
    from_addr = config.get("from_addr", "")
    base_url = config.get("base_url", "")

    # Fetch SMTP credentials
    svc = NotificationDeliveryService(
        operator_url=current_app.config["OPERATOR_URL"],
        timeout=current_app.config["OPERATOR_TIMEOUT"],
    )
    username = ""
    password = ""
    credentials_secret = channel_config.get("credentials_secret", "")
    try:
        if credentials_secret:
            username, _ = svc.fetch_credential(credentials_secret, "username")
            password, _ = svc.fetch_credential(credentials_secret, "password")

        from beeper_ui.notifications.email import EmailNotifier, EmailNotifierError

        notifier = EmailNotifier(
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            username=username,
            password=password,
            use_tls=use_tls,
            from_addr=from_addr,
        )
        result = notifier.send_digest(
            recipients=recipients,
            investigations=investigations,
            period_label=period_label,
            base_url=base_url,
        )
        return jsonify({
            "status": "delivered",
            "message_id": result.get("message_id", ""),
            "investigation_count": result.get("investigation_count", 0),
        }), 200
    except EmailNotifierError as e:
        logger.error("Digest email delivery failed: %s", str(e))
        return jsonify({
            "status": "failed",
            "error": str(e),
            "retryable": e.retryable,
        }), 502 if e.retryable else 422
    except Exception as e:
        logger.exception("Unexpected error in digest flush: %s", str(e))
        return jsonify({
            "status": "failed",
            "error": "Internal server error",
            "retryable": True,
        }), 500
    finally:
        svc.close()


@notifications_bp.route("/audit", methods=["GET"])
@require_role("user")
def get_notification_audit() -> tuple[Any, int]:
    """Query notification audit records with optional filters.

    Query parameters:
        service: Filter by service name.
        channel_type: Filter by channel type (slack, pagerduty, email, webhook).
        date_from: ISO 8601 start date (inclusive).
        date_to: ISO 8601 end date (inclusive).
        is_false_page: Filter by false page status (true/false).
        limit: Maximum records to return (default 50, max 200).
        offset: Number of records to skip (default 0).

    Returns:
        JSON with 'records' list and 'statistics' dict.
    """
    service = request.args.get("service")
    channel_type = request.args.get("channel_type")
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    is_false_page_str = request.args.get("is_false_page")

    is_false_page: bool | None = None
    if is_false_page_str is not None:
        is_false_page = is_false_page_str.lower() == "true"

    try:
        limit = min(int(request.args.get("limit", 50)), 200)
    except (ValueError, TypeError):
        limit = 50
    try:
        offset = max(int(request.args.get("offset", 0)), 0)
    except (ValueError, TypeError):
        offset = 0

    audit_svc = NotificationAuditService()
    try:
        records = audit_svc.query_audit(
            service=service,
            channel_type=channel_type,
            date_from=date_from,
            date_to=date_to,
            is_false_page=is_false_page,
            limit=limit,
            offset=offset,
        )
        statistics = audit_svc.get_audit_statistics(
            service=service,
            date_from=date_from,
            date_to=date_to,
        )
        return jsonify({
            "records": records,
            "statistics": statistics,
            "limit": limit,
            "offset": offset,
        }), 200
    except Exception as e:
        logger.exception("Failed to query notification audit: %s", str(e))
        return jsonify({
            "status": "error",
            "error": "Failed to query audit records",
        }), 500
    finally:
        audit_svc.close()
