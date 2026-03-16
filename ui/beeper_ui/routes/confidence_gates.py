"""Confidence gate API routes.

Provides REST API endpoints for evaluating confidence gates and
managing gate threshold configuration. Admin-only for threshold
writes, user-accessible for reads and evaluation.
"""

import logging
import os
import re
from typing import Any

from flask import Blueprint, jsonify, request

from beeper_ui.middleware.permissions import require_role
from beeper_ui.services.confidence_gate_service import (
    GATED_TRUST_LEVELS,
    MAX_GATED_LEVEL,
    MIN_GATED_LEVEL,
    ConfidenceGateConfig,
    ConfidenceGateError,
    ConfidenceGateService,
    GateDecision,
    format_gate_message,
)

logger = logging.getLogger(__name__)

confidence_gates_bp = Blueprint(
    "confidence_gates", __name__, url_prefix="/api/v1/trust/gates"
)

_SERVICE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _get_gate_service() -> ConfidenceGateService:
    """Get configured ConfidenceGateService instance."""
    return ConfidenceGateService(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )


def _gate_decision_to_dict(decision: GateDecision) -> dict[str, Any]:
    """Convert GateDecision to API response dict."""
    return {
        "permitted": decision.permitted,
        "confidence_score": decision.confidence_score,
        "threshold": decision.threshold,
        "trust_level": decision.trust_level,
        "action_type": decision.action_type,
        "reason": decision.reason,
        "service_name": decision.service_name,
        "message": format_gate_message(decision),
    }


def _gate_config_to_dict(config: ConfidenceGateConfig) -> dict[str, Any]:
    """Convert ConfidenceGateConfig to API response dict."""
    return {
        "trust_level": config.trust_level,
        "threshold": config.threshold,
        "updated_by": config.updated_by,
        "updated_at": config.updated_at,
        "description": config.description,
    }


@confidence_gates_bp.route("/evaluate", methods=["POST"])
@require_role("user")
def evaluate_gate() -> tuple[Any, int]:
    """Evaluate confidence gate for a service and confidence score."""
    data = request.get_json(silent=True)
    if data is None:
        return (
            jsonify(
                {
                    "type": "https://beeper.dev/errors/invalid-request",
                    "title": "Bad Request",
                    "status": 400,
                    "detail": "Request body must be valid JSON",
                }
            ),
            400,
        )

    service_name = data.get("service_name")
    if not service_name or not isinstance(service_name, str):
        return (
            jsonify(
                {
                    "type": "https://beeper.dev/errors/validation-error",
                    "title": "Validation Error",
                    "status": 400,
                    "detail": "'service_name' field is required and must be a string",
                }
            ),
            400,
        )

    if not _SERVICE_NAME_RE.match(service_name) or len(service_name) > 100:
        return (
            jsonify(
                {
                    "type": "https://beeper.dev/errors/validation-error",
                    "title": "Validation Error",
                    "status": 400,
                    "detail": (
                        "Service name must be 1-100 alphanumeric,"
                        " hyphen, or underscore characters"
                    ),
                }
            ),
            400,
        )

    confidence_score = data.get("confidence_score")
    if confidence_score is None:
        return (
            jsonify(
                {
                    "type": "https://beeper.dev/errors/validation-error",
                    "title": "Validation Error",
                    "status": 400,
                    "detail": "'confidence_score' field is required",
                }
            ),
            400,
        )

    if (
        isinstance(confidence_score, bool)
        or not isinstance(confidence_score, (int, float))
        or confidence_score < 0.0
        or confidence_score > 1.0
    ):
        return (
            jsonify(
                {
                    "type": "https://beeper.dev/errors/validation-error",
                    "title": "Validation Error",
                    "status": 400,
                    "detail": "confidence_score must be a number between 0.0 and 1.0",
                }
            ),
            400,
        )

    action_context = data.get("action_context")

    service = _get_gate_service()
    try:
        decision = service.evaluate_gate(
            service_name=service_name,
            confidence_score=float(confidence_score),
            action_context=action_context,
        )
        return jsonify(_gate_decision_to_dict(decision)), 200
    except ConfidenceGateError as e:
        logger.warning("Failed to evaluate gate: %s", e)
        return (
            jsonify(
                {
                    "type": "https://beeper.dev/errors/service-error",
                    "title": "Service Error",
                    "status": 500,
                    "detail": "Unable to evaluate confidence gate",
                }
            ),
            500,
        )
    finally:
        service.close()


@confidence_gates_bp.route("", methods=["GET"])
@require_role("user")
def list_gate_thresholds() -> tuple[Any, int]:
    """List all gate threshold configurations."""
    service = _get_gate_service()
    try:
        thresholds = service.get_gate_thresholds()
        return (
            jsonify([_gate_config_to_dict(cfg) for cfg in thresholds]),
            200,
        )
    except ConfidenceGateError as e:
        logger.warning("Failed to list gate thresholds: %s", e)
        return (
            jsonify(
                {
                    "type": "https://beeper.dev/errors/service-error",
                    "title": "Service Error",
                    "status": 500,
                    "detail": "Unable to retrieve gate thresholds",
                }
            ),
            500,
        )
    finally:
        service.close()


@confidence_gates_bp.route("/<int:trust_level>", methods=["GET"])
@require_role("user")
def get_gate_threshold(trust_level: int) -> tuple[Any, int]:
    """Get gate threshold for a specific trust level."""
    if trust_level not in GATED_TRUST_LEVELS:
        return (
            jsonify(
                {
                    "type": "https://beeper.dev/errors/validation-error",
                    "title": "Validation Error",
                    "status": 400,
                    "detail": (
                        f"Trust levels 1-2 are advisory-only and have no"
                        f" confidence gate. Valid levels: "
                        f"{MIN_GATED_LEVEL}-{MAX_GATED_LEVEL}"
                    ),
                }
            ),
            400,
        )

    service = _get_gate_service()
    try:
        config = service.get_gate_threshold(trust_level)
        return jsonify(_gate_config_to_dict(config)), 200
    except ConfidenceGateError as e:
        logger.warning(
            "Failed to get gate threshold for TL%d: %s", trust_level, e
        )
        return (
            jsonify(
                {
                    "type": "https://beeper.dev/errors/service-error",
                    "title": "Service Error",
                    "status": 500,
                    "detail": f"Unable to retrieve gate threshold for TL{trust_level}",
                }
            ),
            500,
        )
    finally:
        service.close()


@confidence_gates_bp.route("/<int:trust_level>", methods=["PUT"])
@require_role("admin")
def update_gate_threshold(trust_level: int) -> tuple[Any, int]:
    """Update gate threshold for a trust level. Admin-only."""
    if trust_level not in GATED_TRUST_LEVELS:
        return (
            jsonify(
                {
                    "type": "https://beeper.dev/errors/validation-error",
                    "title": "Validation Error",
                    "status": 400,
                    "detail": (
                        "Trust levels 1-2 are advisory-only and have no"
                        " confidence gate. Only trust levels"
                        f" {MIN_GATED_LEVEL}-{MAX_GATED_LEVEL} can be configured"
                    ),
                }
            ),
            400,
        )

    data = request.get_json(silent=True)
    if data is None:
        return (
            jsonify(
                {
                    "type": "https://beeper.dev/errors/invalid-request",
                    "title": "Bad Request",
                    "status": 400,
                    "detail": "Request body must be valid JSON",
                }
            ),
            400,
        )

    threshold = data.get("threshold")
    if threshold is None:
        return (
            jsonify(
                {
                    "type": "https://beeper.dev/errors/validation-error",
                    "title": "Validation Error",
                    "status": 400,
                    "detail": "'threshold' field is required",
                }
            ),
            400,
        )

    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or threshold < 0.0
        or threshold > 1.0
    ):
        return (
            jsonify(
                {
                    "type": "https://beeper.dev/errors/validation-error",
                    "title": "Validation Error",
                    "status": 400,
                    "detail": "Threshold must be a number between 0.0 and 1.0",
                }
            ),
            400,
        )

    updated_by = request.headers.get("X-Beeper-User", "admin")

    service = _get_gate_service()
    try:
        config = service.set_gate_threshold(
            trust_level=trust_level,
            threshold=float(threshold),
            updated_by=updated_by,
        )
        return jsonify(_gate_config_to_dict(config)), 200
    except ConfidenceGateError as e:
        logger.warning(
            "Failed to update gate threshold for TL%d: %s", trust_level, e
        )
        return (
            jsonify(
                {
                    "type": "https://beeper.dev/errors/service-error",
                    "title": "Service Error",
                    "status": 500,
                    "detail": f"Failed to update gate threshold for TL{trust_level}",
                }
            ),
            500,
        )
    finally:
        service.close()
