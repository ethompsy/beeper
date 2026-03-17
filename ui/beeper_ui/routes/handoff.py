"""Shift handoff summary routes."""

import logging

from flask import Blueprint, current_app, jsonify, render_template, request

from beeper_ui.services.handoff_service import HandoffService

logger = logging.getLogger(__name__)

handoff_bp = Blueprint("handoff", __name__, url_prefix="/handoff")


def _get_handoff_service() -> HandoffService:
    """Get configured HandoffService instance."""
    return HandoffService(
        operator_url=current_app.config["OPERATOR_URL"],
        timeout=current_app.config["OPERATOR_TIMEOUT"],
    )


@handoff_bp.route("/")
def handoff_summary() -> str:
    """Render shift handoff summary page."""
    svc = _get_handoff_service()
    try:
        summary = svc.generate_summary()
        if request.headers.get("HX-Request"):
            return render_template(
                "handoff/_content.html",
                summary=summary,
                error_message=None,
            )
        return render_template(
            "handoff/handoff.html",
            summary=summary,
            error_message=None,
        )
    except Exception as e:
        logger.exception("Failed to generate handoff summary: %s", e)
        error_data = {
            "summary": None,
            "error_message": "Unable to generate handoff summary",
        }
        if request.headers.get("HX-Request"):
            return render_template("handoff/_content.html", **error_data)
        return render_template("handoff/handoff.html", **error_data)
    finally:
        svc.close()


@handoff_bp.route("/json")
def handoff_json() -> tuple:
    """Return handoff summary as JSON for clipboard copy / integrations."""
    svc = _get_handoff_service()
    try:
        summary = svc.generate_summary()
        return jsonify(summary.to_dict()), 200
    except Exception as e:
        logger.exception("Failed to generate handoff JSON: %s", e)
        return jsonify({"error": "Unable to generate handoff summary"}), 500
    finally:
        svc.close()
