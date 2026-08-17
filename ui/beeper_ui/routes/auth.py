"""Auth API: `GET /api/v1/auth/me` + local login/logout (Tasks 8.4 + 8.6 —
ADR 0002 §3/§6/§7/§8).

Three blueprints, all mounted at `/api/v1/auth`:

- `auth_api_bp` — `GET /me` (Task 8.4). Registered unconditionally, in
  every mode — see that route's own docstring below.
- `local_auth_api_bp` — `POST /login` (Task 8.6). Registered by
  `beeper_ui.routes.register_blueprints()` ONLY when
  `BEEPER_AUTH_MODE == "local"` — outside `local` mode the route simply
  does not exist (plain 404), matching how `/scim/v2/*`'s registration is
  gated (ADR §1: "there is no password bypass of the IdP"). This is what
  makes the local-mode uniform-401 login matrix meaningfully distinct from
  "not registered at all" everywhere else.
- `session_auth_api_bp` — `POST /logout` (Task 8.6). Registered whenever
  `BEEPER_AUTH_MODE != "none"` (i.e. `local` OR `oidc`) — see that route's
  own docstring for the `oidc`-mode registration decision and its
  relationship to Task 8.5's separate `/auth/logout`.

The Task 8.5 OIDC flow (`GET /auth/login|callback`, `POST /auth/logout`)
lives entirely under `/auth` (no `/api/v1` prefix, a different blueprint in
`oidc_auth.py`) — no overlap with this file.

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

import time

from flask import Blueprint, Response, current_app, jsonify, request

from beeper_ui.middleware.permissions import resolve_role_for_identity
from beeper_ui.middleware.session import (
    SessionIdentity,
    clear_session_identity,
    establish_session_identity,
    read_session_identity,
    same_origin_request,
)
from beeper_ui.services.identity_store import get_identity_store
from beeper_ui.services.password_hashing import DUMMY_PASSWORD_HASH, verify_password

auth_api_bp = Blueprint("auth_api", __name__, url_prefix="/api/v1/auth")
local_auth_api_bp = Blueprint("local_auth_api", __name__, url_prefix="/api/v1/auth")
session_auth_api_bp = Blueprint("session_auth_api", __name__, url_prefix="/api/v1/auth")

# FR59 "small constant delay" — the wall-clock floor a FAILED login is held
# to before its 401 is returned, so unknown-user / bad-password / deactivated
# cannot be told apart by response latency (only the Argon2id CPU cost is
# already normalized by `password_hashing.DUMMY_PASSWORD_HASH`; this floor
# additionally absorbs the store-lookup and any other incidental latency
# variance between those three cases). Applies to the FAILURE path only —
# ADR §6's own wording ties the delay to "login failures"; a successful
# login is already trivially distinguishable (a real session + 200 body),
# so there is nothing to protect by slowing it down too.
LOGIN_FAILURE_DELAY_SECONDS = 0.3

# Module-level indirection so tests can assert the delay fired (and with
# what remaining duration) without actually blocking — same test-seam
# pattern as `beeper_ui.services.identity_store`'s injectable `clock`.
_sleep = time.sleep
_monotonic = time.monotonic


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


# ---------------------------------------------------------------------------
# Task 8.6 — local login/logout (ADR 0002 §6, FR59)
# ---------------------------------------------------------------------------


def _csrf_rejected_response() -> tuple[Response, int, dict[str, str]]:
    """Same RFC7807 shape/`type` as `resolve_request_identity()`'s own CSRF
    rejection (`beeper_ui.middleware.permissions._problem_response()`), not
    imported directly since that helper is private to that module — see
    this file's module docstring: `/api/v1/auth/*` is exempt from the
    shared `before_request` CSRF check, so `login`/`logout` below MUST
    each call `same_origin_request()` and produce this response
    themselves.
    """
    body = {
        "type": "https://beeper.dev/errors/csrf-rejected",
        "title": "Cross-Origin Request Rejected",
        "status": 403,
        "detail": (
            "This state-changing request's Origin/Referer header does not "
            "match the request host."
        ),
        "instance": request.path,
    }
    return jsonify(body), 403, {"Content-Type": "application/problem+json"}


def _uniform_login_failure_response() -> tuple[Response, int, dict[str, str]]:
    """The ONE 401 body for every login-failure cause (FR59: "login failure
    responses do not distinguish unknown-user, bad-password, and
    deactivated"). Every field is a fixed literal except `instance`, which
    is always `request.path` — itself a fixed value for this route (there
    is only one path that can produce this response) — so two calls to
    this function are byte-identical JSON, the exact property the `[T]`
    acceptance criterion checks.
    """
    body = {
        "type": "https://beeper.dev/errors/invalid-credentials",
        "title": "Invalid Credentials",
        "status": 401,
        "detail": "Invalid username or password.",
        "instance": request.path,
    }
    return jsonify(body), 401, {"Content-Type": "application/problem+json"}


def _apply_constant_delay(started_at: float) -> None:
    """Sleep the remainder of `LOGIN_FAILURE_DELAY_SECONDS` since
    `started_at` (monotonic clock). A no-op if the request already took
    longer than the floor (never speeds anything up, only pads short
    requests up to the floor)."""
    remaining = LOGIN_FAILURE_DELAY_SECONDS - (_monotonic() - started_at)
    if remaining > 0:
        _sleep(remaining)


@local_auth_api_bp.route("/login", methods=["POST"])
def login() -> Response | tuple[Response, int, dict[str, str]]:
    """`POST /api/v1/auth/login` — local username/password login.

    Registered ONLY in `local` mode (see this module's docstring) — a
    request to this path in `none`/`oidc` mode is a plain 404, since the
    blueprint holding it was never registered at all.

    Body: `{"username": str, "password": str}` (JSON). Success (200):
    the same `{authenticated, auth_mode, user}` shape `GET /me` returns,
    plus a freshly ROTATED session cookie (`establish_session_identity()`
    calls `session.clear()` first — the standard login-fixation defense,
    ADR §2). Failure (401): `_uniform_login_failure_response()` — byte
    -identical for an unknown username, a wrong password, and a
    deactivated account, held to a `LOGIN_FAILURE_DELAY_SECONDS` wall
    -clock floor (`_apply_constant_delay()`) on top of the CPU-time
    normalization `password_hashing.DUMMY_PASSWORD_HASH` already provides
    for the Argon2id verify itself — together these are FR59's "small
    constant delay" mechanism. No lockout/attempt-counting table (ADR §6:
    "lockout is a DoS lever against the only admin").

    CSRF: self-enforced via `same_origin_request()` (this path is exempt
    from the shared `before_request` CSRF check — see this module's
    docstring) — checked BEFORE any credential work, so a cross-origin
    login attempt never even reaches the constant-delay/verify machinery.
    """
    if not same_origin_request():
        return _csrf_rejected_response()

    started_at = _monotonic()

    body = request.get_json(silent=True) or {}
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")

    store = get_identity_store()
    record = store.get_by_username(username) if username else None

    # Always verify against SOME real Argon2id hash — the record's own hash
    # if it has one, `DUMMY_PASSWORD_HASH` otherwise (unknown username, or a
    # pure-SCIM-origin record with no local password at all). This is what
    # keeps "unknown user", "user has no local password", and "wrong
    # password for a real hash" CPU-time-indistinguishable; skipping the
    # verify call entirely for any of those cases would itself leak which
    # one occurred via response latency.
    hash_to_check = (
        record.password_hash
        if record is not None and record.password_hash
        else DUMMY_PASSWORD_HASH
    )
    password_ok = verify_password(hash_to_check, password)

    valid = (
        record is not None
        and record.active
        and bool(record.password_hash)
        and password_ok
    )

    if not valid:
        _apply_constant_delay(started_at)
        return _uniform_login_failure_response()

    assert record is not None  # narrows for type-checkers; `valid` implies this
    store.record_login(record.id)
    establish_session_identity(
        sub=record.id,
        email=(record.emails[0] if record.emails else None),
        name=record.display_name or record.user_name,
        role_snapshot=record.role,
        external_id=record.external_id,
        lifetime_hours=float(current_app.config.get("BEEPER_SESSION_LIFETIME_HOURS", 8)),
    )
    return jsonify(
        {
            "authenticated": True,
            "auth_mode": "local",
            "user": {
                "user_name": record.user_name,
                "display_name": record.display_name or record.user_name,
                "role": record.role,
            },
        }
    )


@session_auth_api_bp.route("/logout", methods=["POST"])
def logout() -> Response | tuple[Response, int, dict[str, str]]:
    """`POST /api/v1/auth/logout` — clear the session cookie.

    Registration decision (Task 8.6, flagged per the task instructions):
    this route registers whenever `BEEPER_AUTH_MODE != "none"` — BOTH
    `local` and `oidc` — not `local` only. Rationale:

    1. It is a pure, mode-agnostic action: `clear_session_identity()`
       (`beeper_ui.middleware.session`) drops whatever identity snapshot
       is in the cookie, regardless of whether `establish_session_identity()`
       was originally called by THIS route's sibling `login()` (local
       password) or by Task 8.5's OIDC callback — both write through the
       exact same session module, so there is nothing OIDC-specific this
       handler would need to know to clear an OIDC-established session.
    2. It keeps the React UI's "Sign out" affordance (8.7's `UserMenu`
       primitive) a single, mode-independent `POST /api/v1/auth/logout`
       fetch call — it does not need to branch on `auth_mode` to know
       which URL to call.
    3. No collision with Task 8.5's OWN `POST /auth/logout` (note: no
       `/api/v1` prefix, a different blueprint in `oidc_auth.py`) — that
       route's job is the HEAVIER RP-initiated logout flow (a redirect to
       the IdP's `end_session_endpoint` when configured), appropriate for
       a full-page navigation, not a JSON `fetch`. This route stays a
       plain "clear Beeper's own session cookie" JSON 200, the right
       primitive for both a local-mode logout button AND an oidc-mode
       "sign out of Beeper without necessarily signing out of the IdP
       everywhere" affordance.

    NOT registered in mode `none` — there is no session concept to clear
    there at all (matches `login()`'s "no session, nothing to log out of"
    reasoning, and keeps the `none`/demo surface unchanged).

    CSRF: self-enforced via `same_origin_request()`, same as `login()`
    above (this path is exempt from the shared `before_request` CSRF
    check). Idempotent: calling this with no session present is a 200
    no-op, not an error — matches `clear_session_identity()`'s own
    no-op-if-absent contract.
    """
    if not same_origin_request():
        return _csrf_rejected_response()

    clear_session_identity()
    mode = current_app.config.get("BEEPER_AUTH_MODE", "none")
    return jsonify({"authenticated": False, "auth_mode": mode, "user": None})
