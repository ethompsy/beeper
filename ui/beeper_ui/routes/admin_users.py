"""Admin users API (Task 8.7 — ADR 0002 §6/§5.2/§5.3, FR60).

`admin_users_api_bp`, mounted at `/api/v1/admin/users`. Every route carries
`@require_role("admin")` (structurally provable via `.required_role ==
"admin"`, mirroring `test_json_api_rbac.py`'s pattern — see
`ui/tests/test_admin_users_api.py::TestRbacStructural`).

── Registration (mirrors `session_auth_api_bp`'s decision, Task 8.6) ───────
Registered in `beeper_ui.routes.register_blueprints()` whenever
`BEEPER_AUTH_MODE != "none"` — i.e. BOTH `local` AND `oidc`, never `none`.
Not `local`-only: ADR §5.2's "adopt-and-link" rule explicitly describes the
admin UI rendering a SCIM-linked record "read-only... while in `oidc`
mode" (409 `scim-owned-user` on writes) — that behavior is only meaningful
if the view exists and lists users while `oidc` mode is active, so the
admin UI must be reachable in `oidc` mode too (to review/manage any
locally-created or origin="local" leftover records, and to observe
SCIM-owned rows even though it cannot edit them). Never registered in mode
`none`: there is no identity store to manage there at all — the module
docstring in `beeper_ui.services.identity_store` is explicit that
`get_identity_store()` must never be constructed in mode `none`, and
registering this blueprint unconditionally would let an
`ALLOW_ROLE_HEADER`-admin dev/test caller reach a route that touches
Qdrant lazily, defeating that invariant. A request to this prefix in mode
`none` is therefore a plain 404 (blueprint never registered), exactly like
`/scim/v2/*` when SCIM is disabled.

── CSRF (flagged per the task instructions) ────────────────────────────────
`/api/v1/admin/*` is **NOT** one of `beeper_ui.middleware.permissions
.EXEMPT_PATH_PREFIXES` — the shared `before_request` hook
(`resolve_request_identity()`) already runs its Origin/Referer
same-origin check on every unsafe-method request to this blueprint BEFORE
Flask ever dispatches to a view function here. These routes therefore do
**NOT** self-enforce CSRF the way `routes/auth.py`'s exempt-path
login/logout routes must — there is nothing to add here; re-implementing
the check would be redundant, not defense-in-depth (there is exactly one
CSRF mechanism per ADR §2, "one place").

── Session auth (also free) ────────────────────────────────────────────────
The same shared `before_request` hook resolves the caller's session and
sets `g.user_role` (401 `authentication-required` for no/expired session)
before `require_role("admin")` ever runs — this module only needs to
express the ADMIN-specific 403 on top of that, via the decorator.

── The `oidc`-mode local-user-creation decision (flagged per the task
instructions) ──────────────────────────────────────────────────────────────
`POST /` (create local user) returns `409 local-user-creation-unavailable`
in `oidc` mode. Reasoning (ADR §5/§6 read together, not left implicit):

1. Local password login (`POST /api/v1/auth/login`) is registered **only**
   in `local` mode (FR62/ADR §1: "there is no password bypass of the IdP").
   A user created here while the server runs in `oidc` mode could never
   authenticate with that password — the endpoint would be minting
   permanently-inert credentials, which is confusing at best and a stale
   -secret liability at worst (ADR §6: "no password self-service" — the
   admin UI should not grow a way to create secrets nobody can audit the
   use of).
2. `oidc` mode's user-provisioning writer is SCIM (ADR §5: "one store, two
   writers" — SCIM in `oidc`, the admin UI in `local`). A `local`-origin
   record created here would sit inert until either (a) mode flips back to
   `local`, or (b) a SCIM push later adopts it by matching `user_name_lc`
   — at which point ADR §5.2's adopt-and-link rule **discards the role
   this endpoint would have assigned**, so the create's most consequential
   parameter (role) has no durable effect under the very mode it was
   created in.
3. `409` (not `422`) because the request is well-formed and could succeed
   under a different, real server state (switch to `local` mode) — the
   conflict is with current server configuration, not with the payload
   itself. Matches this file's other 409s (`last-admin`, `scim-owned-user`)
   in being a state conflict, not a validation failure.

`local` mode is otherwise the normal, fully-supported path for this route.

── Response shape ──────────────────────────────────────────────────────────
A user resource: `{id, user_name, display_name, role, origin, active,
last_login_at}` — `last_login_at` is included because the store DOES track
it (`UserRecord.last_login_at`, stamped by `IdentityStoreService
.record_login()` on local login); the task's "omit rather than invent"
guidance therefore does not apply here. Never includes `password_hash`.
`GET /` returns a bare JSON array, matching this codebase's other list
JSON endpoints (`sources_list_json`, `investigations_list_json`) — sorted
by `user_name_lc` for a stable, predictable table order (`list_users()`
itself returns Qdrant scroll order, which is not guaranteed stable).

── One additive `identity_store` change (flagged prominently) ─────────────
`IdentityStoreService.update_user()` gains one new keyword-only parameter,
`password_hash: str | None = None` (default = no-op, exactly the same
additive-kwarg pattern Task 8.8 already used on this same method for
`user_name`/`emails`/`group_ids`) — needed because `POST
/<user_id>/reset-password` must persist a freshly-hashed password onto an
EXISTING record, and no pre-8.7 write primitive could do that (
`create_local_user()` only sets a hash at creation time). See that
parameter's docstring in `identity_store.py` and
`ui/tests/test_admin_users_api.py::TestPasswordResetHashPersistence`.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request

from beeper_ui.middleware.permissions import require_role
from beeper_ui.services.identity_store import VALID_ROLES as STORE_VALID_ROLES
from beeper_ui.services.identity_store import (
    DuplicateUserError,
    UserRecord,
    get_identity_store,
)
from beeper_ui.services.password_hashing import MIN_PASSWORD_LENGTH, hash_password

admin_users_api_bp = Blueprint(
    "admin_users_api", __name__, url_prefix="/api/v1/admin/users"
)

_ERROR_BASE = "https://beeper.dev/errors"

# Shared return-type alias — every route below either returns a plain 200/201
# `jsonify(...)` Response or one of this module's RFC7807 `_problem()` tuples.
_JsonResponse = Response | tuple[Response, int] | tuple[Response, int, dict[str, str]]


def _problem(
    *, type_suffix: str, title: str, status: int, detail: str
) -> tuple[Response, int, dict[str, str]]:
    """RFC7807 `application/problem+json` body — the exact shape used
    throughout `routes/auth.py` and `middleware/permissions.py` (house
    style; this module deliberately does not invent a second convention)."""
    body = {
        "type": f"{_ERROR_BASE}/{type_suffix}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.path,
    }
    return jsonify(body), status, {"Content-Type": "application/problem+json"}


def _user_to_dict(record: UserRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "user_name": record.user_name,
        "display_name": record.display_name,
        "role": record.role,
        "origin": record.origin,
        "active": record.active,
        "last_login_at": record.last_login_at,
    }


def _is_oidc_mode() -> bool:
    return current_app.config.get("BEEPER_AUTH_MODE") == "oidc"


def _scim_owned_conflict(record: UserRecord) -> tuple[Response, int, dict[str, str]] | None:
    """The shared `409 scim-owned-user` guard for every write route below
    (`PATCH`, reset-password). ADR §5.2: a SCIM-adopted record is read-only
    from the admin UI's perspective **while in `oidc` mode** — SCIM is the
    live authoritative writer there, so a manual override would be
    silently clobbered on the next provisioning sync (or worse, would look
    like a durable change while SCIM's authoritative role recompute
    disagrees). Returns `None` (no conflict) for `local`-origin records in
    any mode, and for `scim`-origin records while the server itself is
    running in `local` mode (no active SCIM writer to contend with there —
    see this module's docstring on why `oidc`-mode-only is deliberate, not
    an oversight).
    """
    if _is_oidc_mode() and record.origin == "scim":
        return _problem(
            type_suffix="scim-owned-user",
            title="SCIM-Owned Record",
            status=409,
            detail=(
                "This user is provisioned and managed by SCIM while SSO is "
                "enabled. Changes must be made in the identity provider; "
                "unassign the account there or disable SCIM to edit it here."
            ),
        )
    return None


def _validate_password(password: str) -> str | None:
    """Returns an error detail string if `password` fails the 8.6 minimum
    -length rule, else `None`. No composition/rotation policy — ADR §6 /
    `password_hashing.py`'s own NIST-800-63-aligned stance, unchanged
    here."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    return None


# ---------------------------------------------------------------------------
# GET / — list users
# ---------------------------------------------------------------------------


@admin_users_api_bp.route("/", methods=["GET"])
@require_role("admin")
def list_users() -> Response:
    store = get_identity_store()
    records = sorted(store.list_users(), key=lambda r: r.user_name_lc)
    return jsonify([_user_to_dict(r) for r in records])


# ---------------------------------------------------------------------------
# POST / — create local user
# ---------------------------------------------------------------------------


@admin_users_api_bp.route("/", methods=["POST"])
@require_role("admin")
def create_user() -> _JsonResponse:
    if _is_oidc_mode():
        return _problem(
            type_suffix="local-user-creation-unavailable",
            title="Local User Creation Unavailable",
            status=409,
            detail=(
                "Local accounts cannot be created while SSO (oidc mode) is "
                "enabled — provision users via SCIM/your identity provider, "
                "or switch to local mode to manage local accounts."
            ),
        )

    body = request.get_json(silent=True) or {}
    username = str(body.get("user_name") or body.get("username") or "").strip()
    display_name = str(body.get("display_name") or "").strip()
    password = str(body.get("password") or "")
    role = str(body.get("role") or "user")

    problems: list[str] = []
    if not username:
        problems.append("user_name is required.")
    if role not in STORE_VALID_ROLES:
        problems.append(f"role must be one of {sorted(STORE_VALID_ROLES)}.")
    password_problem = _validate_password(password)
    if password_problem:
        problems.append(password_problem)

    if problems:
        return _problem(
            type_suffix="validation-failed",
            title="Validation Failed",
            status=422,
            detail=" ".join(problems),
        )

    store = get_identity_store()
    try:
        record = store.create_local_user(
            user_name=username,
            password_hash=hash_password(password),
            display_name=display_name or username,
            role=role,
            active=True,
        )
    except DuplicateUserError:
        return _problem(
            type_suffix="username-already-exists",
            title="Username Already Exists",
            status=409,
            detail=f"A user named {username!r} already exists.",
        )

    return jsonify(_user_to_dict(record)), 201


# ---------------------------------------------------------------------------
# PATCH /<user_id> — role change + activate/deactivate
# ---------------------------------------------------------------------------


@admin_users_api_bp.route("/<user_id>", methods=["PATCH"])
@require_role("admin")
def patch_user(user_id: str) -> _JsonResponse:
    store = get_identity_store()
    record = store.get_by_id(user_id, use_cache=False)
    if record is None:
        return _problem(
            type_suffix="user-not-found",
            title="User Not Found",
            status=404,
            detail=f"No user with id {user_id!r} exists.",
        )

    conflict = _scim_owned_conflict(record)
    if conflict is not None:
        return conflict

    body = request.get_json(silent=True) or {}
    has_role = "role" in body
    has_active = "active" in body
    if not has_role and not has_active:
        return _problem(
            type_suffix="validation-failed",
            title="Validation Failed",
            status=422,
            detail="At least one of role/active must be supplied.",
        )

    new_role = body.get("role") if has_role else None
    new_active = body.get("active") if has_active else None

    if has_role and new_role not in STORE_VALID_ROLES:
        return _problem(
            type_suffix="validation-failed",
            title="Validation Failed",
            status=422,
            detail=f"role must be one of {sorted(STORE_VALID_ROLES)}.",
        )
    if has_active and not isinstance(new_active, bool):
        return _problem(
            type_suffix="validation-failed",
            title="Validation Failed",
            status=422,
            detail="active must be a boolean.",
        )

    # ADR §5.3 / FR60: last-admin protection is a STORE-LEVEL primitive
    # (`would_orphan_admins`) the admin UI must call BEFORE mutating —
    # `update_user()` itself never refuses (SCIM writes must alarm, not
    # 409, per ADR §5.3), so this refusal is this route's responsibility.
    if store.would_orphan_admins(user_id, new_role=new_role, new_active=new_active):
        return _problem(
            type_suffix="last-admin",
            title="Last Admin Protected",
            status=409,
            detail=(
                "This is the last active admin. Promote another user to "
                "admin before demoting or deactivating this account."
            ),
        )

    updated = store.update_user(
        user_id,
        role=new_role if has_role else None,
        active=new_active if has_active else None,
    )
    return jsonify(_user_to_dict(updated))


# ---------------------------------------------------------------------------
# POST /<user_id>/reset-password — admin password reset (local users)
# ---------------------------------------------------------------------------


@admin_users_api_bp.route("/<user_id>/reset-password", methods=["POST"])
@require_role("admin")
def reset_password(user_id: str) -> _JsonResponse:
    store = get_identity_store()
    record = store.get_by_id(user_id, use_cache=False)
    if record is None:
        return _problem(
            type_suffix="user-not-found",
            title="User Not Found",
            status=404,
            detail=f"No user with id {user_id!r} exists.",
        )

    conflict = _scim_owned_conflict(record)
    if conflict is not None:
        return conflict

    body = request.get_json(silent=True) or {}
    password = str(body.get("password") or "")
    password_problem = _validate_password(password)
    if password_problem:
        return _problem(
            type_suffix="validation-failed",
            title="Validation Failed",
            status=422,
            detail=password_problem,
        )

    updated = store.update_user(user_id, password_hash=hash_password(password))
    return jsonify(_user_to_dict(updated))
