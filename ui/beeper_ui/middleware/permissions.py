"""Permission middleware: unified identity resolver + RBAC enforcement.

Implements a two-tier (admin/user) permission model on top of ADR 0002's
unified resolver (§7):

- `resolve_request_identity()` — the single `before_request` hook (Task 8.3;
  supersedes the old `resolve_user_role()`). Mode `none` preserves the
  pre-8.3 header-or-default behavior byte-for-byte; `local`/`oidc` resolve
  identity from the session cookie via the shared identity store (60 s TTL
  cache), enforce the ADR §2 exemption matrix, the 401/403 contract, and the
  Origin/Referer CSRF check.
- `require_role()` — UNCHANGED (Task 6.2a/8.2 behavioral guarantees intact):
  enforces a minimum role requirement on specific routes, RFC7807 403 body,
  `.required_role` introspection marker.
"""

import functools
import logging
from collections.abc import Callable
from typing import Any, NamedTuple
from urllib.parse import urlencode

from flask import Flask, Response, current_app, g, jsonify, redirect, request

from beeper_ui.middleware.session import (
    SessionIdentity,
    build_login_redirect_next,
    clear_session_identity,
    read_session_identity,
    same_origin_request,
)
from beeper_ui.services.identity_store import get_identity_store

logger = logging.getLogger(__name__)

VALID_ROLES = {"admin", "user"}

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# ---------------------------------------------------------------------------
# ADR 0002 §2 exemption matrix — ONE small, table-driven registry collapsing
# the three divergent per-pillar exemption lists. A path matching one of
# these prefixes is served WITHOUT any identity gating in `local`/`oidc`
# mode (in mode `none` nothing is ever gated in the first place — see step 3
# of `resolve_request_identity()` below — so this table is inert there,
# matching the ADR table's "none" column being "open"/"role chain"
# everywhere). Exercised table-driven in
# `tests/test_identity_resolver.py::TestExemptionMatrixTableDriven` and
# `::TestExemptionMatrixEndToEnd`.
#
# Path prefix    | Disposition (local/oidc)     | Why
# /health/api     | open, no gating               | k8s probes must never
#                 |                                | 401 (crash-loop risk)
# /app            | open, no gating                | React shell + hashed
#                 |                                | assets are static/
#                 |                                | data-free in every
#                 |                                | mode; login page
#                 |                                | renders inside shell
# /auth           | open, no gating                | OIDC login/callback/
#                 |                                | logout (Task 8.5) —
#                 |                                | reachable logged-out
# /api/v1/auth    | open, no gating                | local/OIDC auth API
#                 |                                | (8.5/8.6: login/
#                 |                                | logout/me) — reachable
#                 |                                | logged-out
# /socket.io      | open (own 410 underneath)      | 6.2a tombstone
#                 |                                | blueprint returns its
#                 |                                | own RFC7807 410 Gone;
#                 |                                | never identity-gated
# /scim/v2        | open (404 today)               | own bearer auth ships
#                 |                                | in Task 8.8; never
#                 |                                | session/CSRF-gated
#                 |                                | per ADR §2
# everything else | gated (401 API/SSE, 302 page)  | ADR §7 steps 1-2
#
# Ambiguity resolved here (flagged per the task instructions): the ADR's
# table literally lists `/health/api` (exact); this implementation treats
# every entry — including that one — as a PREFIX match (`path == prefix or
# path.startswith(prefix + "/")`) for uniform table semantics. `/health/api`
# has no sub-routes today, so prefix vs. exact behave identically in
# practice; documented here rather than silently deviating per-row.
# ---------------------------------------------------------------------------
EXEMPT_PATH_PREFIXES: tuple[str, ...] = (
    "/health/api",
    "/app",
    "/auth",
    "/api/v1/auth",
    "/socket.io",
    "/scim/v2",
)


def _is_exempt_path(path: str) -> bool:
    """True if `path` falls under one of the §2 exemption-matrix prefixes.

    A path containing a literal `..` segment is NEVER treated as exempt —
    fails closed to the normal gated path instead. This mirrors
    `beeper_ui.routes.react_registry._is_always_excluded()`'s identical
    defensive check (added there per that module's Task 6.3 finding: some
    WSGI servers/raw HTTP clients/intermediate proxies do not normalize
    `..` segments the way a browser does before Flask ever sees
    `request.path`). Applied here for the opposite reason: that function
    excludes `..`-laden paths from a redirect registry (fails open to
    normal Flask dispatch); this one excludes them from the exemption
    table (fails closed to identity gating) — a `..`-laden path must never
    be treated as reaching an unauthenticated surface on the strength of a
    prefix string-match alone.
    """
    if any(segment == ".." for segment in path.split("/")):
        return False
    return any(path == prefix or path.startswith(prefix + "/") for prefix in EXEMPT_PATH_PREFIXES)


def _problem_response(
    *, type_suffix: str, title: str, status: int, detail: str
) -> tuple[Response, int, dict[str, str]]:
    """Build an RFC7807 `application/problem+json` response."""
    body = {
        "type": f"https://beeper.dev/errors/{type_suffix}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.path,
    }
    return jsonify(body), status, {"Content-Type": "application/problem+json"}


class RoleResolution(NamedTuple):
    """Result of `resolve_role_for_identity()` — see its docstring."""

    status: str  # "ok" | "unauthenticated" | "forbidden"
    role: str | None


def resolve_role_for_identity(mode: str, identity: SessionIdentity) -> RoleResolution:
    """Resolve `identity`'s CURRENT role for `mode` (ADR §7 step 1 branches).

    Pure per-mode dispatch, no session mutation — callers decide what to do
    with a non-"ok" result:

    - `"ok"`: `.role` is the resolved role; proceed.
    - `"unauthenticated"`: inactive / missing-from-store / never-provisioned
      (non-strict is folded into "ok" role="user" instead — see below) —
      caller should clear the session and treat the request as
      unauthenticated (401/302).
    - `"forbidden"`: authenticated but refused by `BEEPER_SCIM_STRICT`
      (never-provisioned, strict mode) — caller should return 403 WITHOUT
      clearing the session (the caller is genuinely authenticated, just not
      authorized).

    Deliberately reusable beyond the main request gate: this is what lets
    the SSE keepalive re-check (ADR §2/NFR25, see
    `beeper_ui.routes.investigations._build_sse_reauth_check()`) share the
    exact same authority rule as `resolve_request_identity()` instead of
    re-implementing it.
    """
    if mode == "local":
        store = get_identity_store()
        record = store.get_by_id(identity.sub)
        if record is None or not record.active:
            return RoleResolution(status="unauthenticated", role=None)
        return RoleResolution(status="ok", role=record.role)

    if mode == "oidc":
        scim_enabled = bool(current_app.config.get("BEEPER_SCIM_ENABLED", False))
        if not scim_enabled:
            # No store source in this sub-mode (ADR §5.2) — the login-time
            # claims snapshot is authoritative for the session's bounded
            # lifetime. `read_session_identity()` already enforced `exp`.
            return RoleResolution(status="ok", role=identity.role_snapshot)

        store = get_identity_store()
        result = store.lookup(identity.email_lc or "", identity.external_id)
        if result is None:
            # Authenticated but never provisioned (ADR §5.2 / D2): default
            # to "user" unless BEEPER_SCIM_STRICT opts into a hard refusal.
            # Never admin under any setting here.
            if current_app.config.get("BEEPER_SCIM_STRICT", False):
                return RoleResolution(status="forbidden", role=None)
            return RoleResolution(status="ok", role="user")
        if not result["active"]:
            return RoleResolution(status="unauthenticated", role=None)
        return RoleResolution(status="ok", role=result["role"])

    # mode == "none" never reaches here — handled entirely by step 3 below.
    return RoleResolution(status="unauthenticated", role=None)


def resolve_request_identity() -> Any:
    """The unified resolver (ADR 0002 §7). Registered as the app's sole
    `before_request` hook by `init_permissions()` — supersedes the old
    `resolve_user_role()`.

    ```
    0. Path in the exemption matrix -> no gating; return.
    1. mode != "none" AND valid (unexpired) session:
         resolve_role_for_identity() branch on mode
         "ok"             -> g.user / g.user_role set; CSRF check; return
         "forbidden"      -> 403 RFC7807 (not-provisioned), session kept
         "unauthenticated"-> clear session, fall to step 2
    2. mode != "none" AND no valid session:
         API/SSE path -> 401 application/problem+json (authentication-required)
         page path    -> 302 -> <mode login>?next=<path+query>
    3. mode == "none":
         ALLOW_ROLE_HEADER and X-Beeper-Role in VALID_ROLES -> that role
         default "user"
    ```
    """
    mode = current_app.config.get("BEEPER_AUTH_MODE", "none")

    if mode == "none":
        _resolve_role_header_or_default()
        return None

    path = request.path
    if _is_exempt_path(path):
        return None

    identity = read_session_identity()
    if identity is not None:
        resolution = resolve_role_for_identity(mode, identity)
        if resolution.status == "ok":
            g.user = identity
            g.user_role = resolution.role
            if request.method in _UNSAFE_METHODS and not same_origin_request():
                return _problem_response(
                    type_suffix="csrf-rejected",
                    title="Cross-Origin Request Rejected",
                    status=403,
                    detail=(
                        "This state-changing request's Origin/Referer header "
                        "does not match the request host."
                    ),
                )
            return None
        if resolution.status == "forbidden":
            return _problem_response(
                type_suffix="not-provisioned",
                title="Not Provisioned",
                status=403,
                detail="This account is authenticated but not provisioned for access.",
            )
        # "unauthenticated": inactive / deleted / deprovisioned mid-session.
        clear_session_identity()

    return _unauthenticated_response(path, mode)


def _unauthenticated_response(path: str, mode: str) -> Any:
    """Step 2 of the resolver: 401 for API/SSE, 302-to-login for pages."""
    if path.startswith("/api/"):
        return _problem_response(
            type_suffix="authentication-required",
            title="Authentication Required",
            status=401,
            detail="A valid session is required to access this resource.",
        )
    login_base = "/auth/login" if mode == "oidc" else "/app/login"
    next_value = build_login_redirect_next()
    return redirect(f"{login_base}?{urlencode({'next': next_value})}", code=302)


def _resolve_role_header_or_default() -> None:
    """Mode `none` role resolution — byte-identical to the pre-8.3
    `resolve_user_role()`.

    1. `X-Beeper-Role` header — development/testing affordance ONLY.
       Refused under production config (`Config.ALLOW_ROLE_HEADER = False`
       on `ProductionConfig`) because it is a trivially spoofable identity
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
    8.2; ADR 0002 §7/§12 CRITICAL-1). See `TestBearerTokensNeverGrantRoles`
    in `ui/tests/test_permissions.py` for the permanent regression guard.
    """
    # `ProductionConfig.__init__` cannot gate this: `app.config.from_object()`
    # is handed the *class*, not an instance, so `__init__` never runs.
    # `ALLOW_ROLE_HEADER` is therefore a plain class attribute, read here.
    if current_app.config.get("ALLOW_ROLE_HEADER", True):
        role_header = request.headers.get("X-Beeper-Role", "")
        if role_header in VALID_ROLES:
            g.user_role = role_header
            return

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
    app.before_request(resolve_request_identity)
