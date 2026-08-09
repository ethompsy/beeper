"""Auth API: `GET /api/v1/auth/me` (Task 8.4 — ADR 0002 §3/§6/§7/§8).

Only the shared identity-probe endpoint lands here. `POST /api/v1/auth/login`
(local mode) and the `/auth/login|callback|logout` OIDC flow are Task 8.5/8.6's
scope — this module owns nothing else.

`/api/v1/auth/*` is one of the ADR §2 exemption-matrix prefixes
(`beeper_ui.middleware.permissions.EXEMPT_PATH_PREFIXES`), so
`resolve_request_identity()` (the shared `before_request` hook) returns
early for this path WITHOUT resolving a session — `g.user`/`g.user_role`
are never set here, by design (the whole point of `/me` is to be reachable
logged out). This handler therefore does its own session read + role
resolution, reusing the exact same public building blocks the resolver
itself uses (`read_session_identity()`, `resolve_role_for_identity()`) —
one authority rule, not a second reimplementation of it.

── Response shape ──────────────────────────────────────────────────────
`{authenticated: bool, auth_mode: "none"|"local"|"oidc", user: {user_name,
display_name, role} | null}`. `auth_mode` is always present, including when
unauthenticated — the shell needs it to pick the login redirect target
(ADR §6). No `bootstrap_required` or other posture detail is ever included
(ADR §6 security LOW-11).

`authenticated` reflects "does a valid, non-expired identity exist" — NOT
"is this identity authorized for `/api/v1/*`". The one case where those
diverge is `oidc`+SCIM+`BEEPER_SCIM_STRICT` with an unprovisioned
principal (`resolve_role_for_identity()`'s `"forbidden"` status): the
session is genuinely valid, so `authenticated` is `true`, but `role` is
`null` since no role was granted. This is deliberately more informative
than collapsing that case into "logged out" — it lets a future login/nav
surface "signed in as X, not yet provisioned" instead of a plain login
prompt — while staying inside the ADR's "no posture leakage" rule, which
is scoped to the fully-unauthenticated body, not this authenticated
edge case.
"""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify

from beeper_ui.middleware.permissions import resolve_role_for_identity
from beeper_ui.middleware.session import SessionIdentity, read_session_identity
from beeper_ui.services.identity_store import get_identity_store

auth_api_bp = Blueprint("auth_api", __name__, url_prefix="/api/v1/auth")


def _anonymous(mode: str) -> Response:
    return jsonify({"authenticated": False, "auth_mode": mode, "user": None})


def _display_fields(mode: str, identity: SessionIdentity) -> tuple[str, str]:
    """Best-effort `(user_name, display_name)` for the `/me` body.

    Reads through the store's existing PUBLIC lookup methods only
    (`get_by_id`, `get_by_username`) — never touches `identity_store.py`
    internals. `resolve_role_for_identity()` (called by the route handler
    below) remains the single source of truth for `role`/authority; this
    helper only fills in the two extra display fields the ADR §3 shape
    asks for that `IdentityStoreService.lookup()`'s pinned `{role, active}`
    return shape does not carry.
    """
    if mode == "local":
        record = get_identity_store().get_by_id(identity.sub)
        if record is not None:
            return record.user_name, (record.display_name or record.user_name)
        return identity.sub, identity.sub

    if mode == "oidc":
        if bool(current_app.config.get("BEEPER_SCIM_ENABLED", False)):
            record = get_identity_store().get_by_username(identity.email_lc or "")
            if record is not None:
                return record.user_name, (record.display_name or record.user_name)
        # `oidc` without SCIM (ADR §5.2's snapshot-authoritative case), or
        # SCIM-enabled but not yet provisioned: derive from the login-time
        # claims snapshot rather than the store.
        fallback = identity.email or identity.sub
        return fallback, (identity.name or fallback)

    return identity.sub, identity.sub


@auth_api_bp.route("/me")
def current_user() -> Response:
    """`GET /api/v1/auth/me` — the shared identity probe (all three modes).

    Never 401s (this path is exempt from gating) and never mutates the
    session (a plain read, per the ADR's "READ — no CSRF concern" note) —
    an inactive/deprovisioned session found here is reported as
    unauthenticated but left for the next gated request to actually clear
    (`resolve_request_identity()`'s own "unauthenticated" branch does that).
    """
    mode = current_app.config.get("BEEPER_AUTH_MODE", "none")

    if mode == "none":
        # No session concept in mode `none` at all — always unauthenticated,
        # regardless of any `X-Beeper-Role` dev/test header (ADR §6).
        return _anonymous("none")

    identity = read_session_identity()
    if identity is None:
        return _anonymous(mode)

    resolution = resolve_role_for_identity(mode, identity)
    if resolution.status == "unauthenticated":
        return _anonymous(mode)

    user_name, display_name = _display_fields(mode, identity)
    return jsonify(
        {
            "authenticated": True,
            "auth_mode": mode,
            "user": {
                "user_name": user_name,
                "display_name": display_name,
                # `None` only for the "forbidden" (not-provisioned, strict)
                # status — see the module docstring.
                "role": resolution.role,
            },
        }
    )
