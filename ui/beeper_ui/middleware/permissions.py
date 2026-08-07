"""Permission middleware for role-based access control.

Implements a two-tier (admin/user) permission model:
- before_request handler resolves user role from K8s token or header
- require_role() decorator enforces role requirements on specific routes
"""

import base64
import functools
import json
import logging
from collections.abc import Callable
from typing import Any

from flask import Flask, current_app, g, jsonify, request

logger = logging.getLogger(__name__)

VALID_ROLES = {"admin", "user"}


def resolve_user_role() -> None:
    """Resolve user role from request context and set on g.user_role.

    Role resolution chain:
    1. K8s ServiceAccount token (Authorization: Bearer <token>) — the only
       path honored in production, though today it verifies group membership
       claimed in the JWT payload WITHOUT verifying the token's signature
       (ADR 0001 §0(a) item 2 — signature verification is Task 6.2b, blocked
       on Q11). Treat this as a UI affordance, not a security boundary, until
       6.2b lands.
    2. X-Beeper-Role header — development/testing affordance ONLY. Refused
       under production config (`Config.ALLOW_ROLE_HEADER = False` on
       `ProductionConfig`) because it is a trivially spoofable identity
       source: any HTTP client can set this header directly. See ADR 0001
       §0(a) item 3.
    3. Default "user".
    """
    # 1. Try K8s ServiceAccount token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]
        role = _extract_role_from_k8s_token(token)
        if role:
            g.user_role = role
            return

    # 2. Try X-Beeper-Role header — development/testing only (Task 6.2a).
    # `ProductionConfig.__init__` cannot gate this: `app.config.from_object()`
    # is handed the *class*, not an instance, so `__init__` never runs.
    # `ALLOW_ROLE_HEADER` is therefore a plain class attribute, read here.
    if current_app.config.get("ALLOW_ROLE_HEADER", True):
        role_header = request.headers.get("X-Beeper-Role", "")
        if role_header in VALID_ROLES:
            g.user_role = role_header
            return

    # 3. Default to "user"
    g.user_role = "user"


def _extract_role_from_k8s_token(token: str) -> str | None:
    """Extract role from K8s ServiceAccount JWT token.

    Checks for 'beeper-admin' in the token's group claims.
    Returns "admin" if found, None otherwise (caller falls through).
    """
    try:
        # JWT has 3 parts: header.payload.signature
        parts = token.split(".")
        if len(parts) != 3:
            return None

        # Decode payload (second part), add padding as needed
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        claims = json.loads(payload_bytes)

        # `claims` is only a groups-bearing object if the JWT payload decoded
        # to a JSON *object*. A crafted token can carry any valid JSON value
        # in that segment (e.g. a bare integer) — json.loads happily returns
        # it, and an unguarded `.get("groups", [])` would raise AttributeError
        # on anything that isn't a dict, crashing this before_request hook
        # and 500ing every route. Treat a non-dict payload as an invalid
        # token instead: fall through to the header/default path.
        if not isinstance(claims, dict):
            return None

        # Valid JWT — check for beeper-admin group
        groups: list[str] = claims.get("groups", [])
        if "beeper-admin" in groups:
            return "admin"

        # Valid JWT but no admin group — return "user" (don't fall through to header)
        return "user"
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        # Token parsing failed — not a valid JWT, fall through
        pass

    return None


def require_role(role: str) -> Callable[..., Any]:
    """Decorator to enforce a minimum role requirement on a route.

    Args:
        role: Required role ("admin" or "user").

    Raises:
        ValueError: If role is not a valid role.

    Usage:
        @app.route("/admin/config")
        @require_role("admin")
        def admin_config():
            ...
    """
    if role not in VALID_ROLES:
        msg = f"Invalid role '{role}'. Must be one of: {VALID_ROLES}"
        raise ValueError(msg)

    def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            user_role = getattr(g, "user_role", "user")

            # "user" role can access "user"-required routes
            # "admin" role can access both "admin" and "user" routes
            if role == "admin" and user_role != "admin":
                logger.warning(
                    "Permission denied",
                    extra={
                        "context": {
                            "user_role": user_role,
                            "required_role": role,
                            "path": request.path,
                            "method": request.method,
                        }
                    },
                )
                return (
                    jsonify(
                        {
                            "type": "https://beeper.dev/errors/permission-denied",
                            "title": "Permission Denied",
                            "status": 403,
                            "detail": "Admin role required to access this resource",
                            "instance": request.path,
                        }
                    ),
                    403,
                    {"Content-Type": "application/problem+json"},
                )

            return f(*args, **kwargs)

        # Introspectable marker: lets tests/tooling assert a route was
        # deliberately gated (and with which role) without needing to
        # provoke the 403 path — e.g. verifying the read-only `/api/v1/*`
        # blueprints' RBAC posture (ADR 0001 §0(a) item 4 / Task 6.2a).
        decorated_function.required_role = role  # type: ignore[attr-defined]

        return decorated_function

    return decorator


def init_permissions(app: Flask) -> None:
    """Register the permission middleware on the Flask app.

    Args:
        app: Flask application instance.
    """
    app.before_request(resolve_user_role)
