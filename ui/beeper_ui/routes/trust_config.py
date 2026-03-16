"""Trust level configuration API routes.

Provides REST API endpoints for managing per-service autonomy trust
levels (TL1-5). Admin-only for writes, user-accessible for reads.
"""

import logging
import os
import re
from typing import Any

from flask import Blueprint, jsonify, request

from beeper_ui.middleware.permissions import require_role
from beeper_ui.services.trust_level_service import (
    DEFAULT_TRUST_LEVEL,
    MAX_TRUST_LEVEL,
    MIN_TRUST_LEVEL,
    TRUST_LEVEL_DEFINITIONS,
    TrustLevelConfig,
    TrustLevelService,
    TrustLevelServiceError,
)

logger = logging.getLogger(__name__)

trust_config_bp = Blueprint(
    "trust_config", __name__, url_prefix="/api/v1/trust"
)

_SERVICE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _get_trust_level_service() -> TrustLevelService:
    """Get configured TrustLevelService instance."""
    return TrustLevelService(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )


def _trust_config_to_dict(config: TrustLevelConfig) -> dict[str, Any]:
    """Convert TrustLevelConfig to API response dict."""
    defn = TRUST_LEVEL_DEFINITIONS.get(config.trust_level, {})
    return {
        "service_name": config.service_name,
        "trust_level": config.trust_level,
        "trust_level_name": defn.get("name", "Unknown"),
        "trust_level_description": defn.get("description", ""),
        "updated_by": config.updated_by,
        "updated_at": config.updated_at,
        "reason": config.reason,
        "previous_level": config.previous_level,
    }


@trust_config_bp.route("/services", methods=["GET"])
@require_role("user")
def list_trust_levels() -> tuple[Any, int]:
    """List all configured service trust levels."""
    service = _get_trust_level_service()
    try:
        levels = service.get_all_trust_levels()
        return jsonify([_trust_config_to_dict(cfg) for cfg in levels]), 200
    except TrustLevelServiceError as e:
        logger.warning("Failed to list trust levels: %s", e)
        return (
            jsonify(
                {
                    "type": "https://beeper.dev/errors/service-error",
                    "title": "Service Error",
                    "status": 500,
                    "detail": "Unable to retrieve trust levels",
                }
            ),
            500,
        )
    finally:
        service.close()


@trust_config_bp.route("/services/<name>", methods=["GET"])
@require_role("user")
def get_trust_level(name: str) -> tuple[Any, int]:
    """Get trust level for a specific service."""
    service = _get_trust_level_service()
    try:
        config = service.get_service_trust_level(name)
        if config is None:
            # Return default TL1 for unconfigured services
            defn = TRUST_LEVEL_DEFINITIONS[DEFAULT_TRUST_LEVEL]
            return (
                jsonify(
                    {
                        "service_name": name,
                        "trust_level": DEFAULT_TRUST_LEVEL,
                        "trust_level_name": defn["name"],
                        "trust_level_description": defn["description"],
                        "updated_by": "",
                        "updated_at": "",
                        "reason": None,
                        "previous_level": None,
                        "is_default": True,
                    }
                ),
                200,
            )
        result = _trust_config_to_dict(config)
        result["is_default"] = False
        return jsonify(result), 200
    except TrustLevelServiceError as e:
        logger.warning("Failed to get trust level for %s: %s", name, e)
        return (
            jsonify(
                {
                    "type": "https://beeper.dev/errors/service-error",
                    "title": "Service Error",
                    "status": 500,
                    "detail": f"Unable to retrieve trust level for {name}",
                }
            ),
            500,
        )
    finally:
        service.close()


@trust_config_bp.route("/services/<name>", methods=["PUT"])
@require_role("admin")
def update_trust_level(name: str) -> tuple[Any, int]:
    """Update trust level for a service. Admin-only."""
    if not name or len(name) > 100 or not _SERVICE_NAME_RE.match(name):
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

    level = data.get("level")
    if level is None:
        return (
            jsonify(
                {
                    "type": "https://beeper.dev/errors/validation-error",
                    "title": "Validation Error",
                    "status": 400,
                    "detail": "'level' field is required",
                }
            ),
            400,
        )

    if (
        isinstance(level, bool)
        or not isinstance(level, int)
        or level < MIN_TRUST_LEVEL
        or level > MAX_TRUST_LEVEL
    ):
        return (
            jsonify(
                {
                    "type": "https://beeper.dev/errors/validation-error",
                    "title": "Validation Error",
                    "status": 400,
                    "detail": (
                        f"Trust level must be an integer between "
                        f"{MIN_TRUST_LEVEL} and {MAX_TRUST_LEVEL}"
                    ),
                }
            ),
            400,
        )

    reason = data.get("reason")
    # Use the admin identity from request context
    updated_by = request.headers.get("X-Beeper-User", "admin")

    service = _get_trust_level_service()
    try:
        config = service.set_trust_level(
            service_name=name,
            level=level,
            updated_by=updated_by,
            reason=reason,
        )
        result = _trust_config_to_dict(config)
        return jsonify(result), 200
    except TrustLevelServiceError as e:
        logger.warning("Failed to update trust level for %s: %s", name, e)
        return (
            jsonify(
                {
                    "type": "https://beeper.dev/errors/service-error",
                    "title": "Service Error",
                    "status": 500,
                    "detail": f"Failed to update trust level for {name}",
                }
            ),
            500,
        )
    finally:
        service.close()


@trust_config_bp.route("/definitions", methods=["GET"])
@require_role("user")
def get_trust_definitions() -> tuple[Any, int]:
    """Return trust level definitions."""
    definitions = [
        {
            "level": level,
            "name": defn["name"],
            "description": defn["description"],
        }
        for level, defn in sorted(TRUST_LEVEL_DEFINITIONS.items())
    ]
    return jsonify(definitions), 200
