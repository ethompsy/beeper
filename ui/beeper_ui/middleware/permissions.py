"""Permission middleware for role-based access control.

Implements a two-tier (admin/user) permission model:
- before_request handler resolves user role from the X-Beeper-Role header
  (development/testing affordance only) or defaults to "user"
- require_role() decorator enforces role requirements on specific routes
"""

import functools
import logging
from collections.abc import Callable
from typing import Any

from flask import Flask, current_app, g, jsonify, request

logger = logging.getLogger(__name__)

VALID_ROLES = {"admin", "user"}


def resolve_user_role() -> None:
    """Resolve user role from request context and set on g.user_role.

    Role resolution chain:
    1. X-Beeper-Role header — development/testing affordance ONLY. Refused
       under production config (`Config.ALLOW_ROLE_HEADER = False` on
       `ProductionConfig`) because it is a trivially spoofable identity
       source: any HTTP client can set this header directly. See ADR 0001
       §0(a) item 3.
    2. Default "user".

    An `Authorization: Bearer <token>` header is NEVER consulted here, in
    any mode. A prior version of this resolver peeked at the *unverified*
    `groups` claim of a Bearer JWT's payload, unconditionally, before the
    `ALLOW_ROLE_HEADER` gate above — so a crafted 3-segment base64 token
    carrying `{"groups": ["beeper-admin"]}` granted "admin" to any caller in
    production too, defeating the fail-closed guarantee below entirely. That
    path (`_extract_role_from_k8s_token`) and its call site were deleted
    unconditionally, in every mode, as a standalone security hotfix (Task
    8.2; ADR 0002 §7/§12 CRITICAL-1 — see
    `docs/specs/decisions/0002-oidc-scim-and-local-fallback-identity.md`).
    See `TestBearerTokensNeverGrantRoles` in `ui/tests/test_permissions.py`
    for the permanent regression guard proving the exact old bypass payload,
    and other crafted tokens, are inert in every mode. Verified,
    request-bound identity is Task 8.3's unified resolver (ADR 0002 §7);
    until it ships, a stray `Authorization: Bearer` header is simply
    ignored.
    """
    # 1. X-Beeper-Role header — development/testing only (Task 6.2a).
    # `ProductionConfig.__init__` cannot gate this: `app.config.from_object()`
    # is handed the *class*, not an instance, so `__init__` never runs.
    # `ALLOW_ROLE_HEADER` is therefore a plain class attribute, read here.
    if current_app.config.get("ALLOW_ROLE_HEADER", True):
        role_header = request.headers.get("X-Beeper-Role", "")
        if role_header in VALID_ROLES:
            g.user_role = role_header
            return

    # 2. Default to "user"
    g.user_role = "user"


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
