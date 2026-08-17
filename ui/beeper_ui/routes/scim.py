"""SCIM 2.0 provisioning surface (Task 8.8 — ADR 0002 §4, FR57/FR58).

`scim_bp`, mounted at `/scim/v2`. Registered ONLY when `BEEPER_SCIM_ENABLED`
is true (see `beeper_ui.routes.register_blueprints()`) — `validate_boot_config()`
already refuses `BEEPER_SCIM_ENABLED=true` outside `oidc` mode at boot
(`beeper_ui.config`, Task 8.3), so by the time this blueprint is considered
for registration, `BEEPER_AUTH_MODE == "oidc"` is guaranteed. Disabled ⇒ not
registered at all ⇒ `/scim/v2/*` 404s exactly like any other undefined path
(ADR §1: "never a fingerprintable surface").

`/scim/v2/*` is listed in `beeper_ui.middleware.permissions
.EXEMPT_PATH_PREFIXES` — the shared session/CSRF `before_request` hook never
gates it. This blueprint's own `before_request` (`_require_scim_bearer_auth`
below) is the ONLY gate, and it fails closed in every branch (ADR §4/§8):
missing token config ⇒ 403 naming the misconfiguration; missing/wrong/
malformed bearer ⇒ 401; correct primary OR secondary token ⇒ 200.

Route inventory (ADR §4): `ServiceProviderConfig`/`ResourceTypes`/`Schemas`
(static, `scim_discovery.py`); `/Users` GET(list+filter)/POST,
`/Users/{id}` GET/PUT/PATCH/DELETE; `/Groups` GET(list+filter)/POST,
`/Groups/{id}` GET/PUT/PATCH/DELETE with both vendor membership-delta
dialects; everything else registered under this blueprint's prefix falls
through to the catch-all at the bottom, `501`.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, g, jsonify, request

from beeper_ui.config import parse_group_names
from beeper_ui.routes.scim_discovery import (
    RESOURCE_TYPES_BY_NAME,
    SCHEMAS_BY_ID,
    SERVICE_PROVIDER_CONFIG,
)
from beeper_ui.routes.scim_helpers import (
    SCIM_CONTENT_TYPE,
    ScimFilterError,
    ScimPatchError,
    apply_group_patch,
    apply_user_patch,
    audit_log,
    authenticate_scim_request,
    coerce_bool,
    coerce_emails,
    extract_group_display_names,
    extract_member_ids,
    group_to_scim_resource,
    is_admin_group_change,
    parse_eq_filter,
    parse_excluded_attributes,
    parse_pagination,
    parse_patch_operations,
    primary_email,
    recompute_role_for_user,
    scim_error_response,
    scim_list_response,
    user_to_scim_resource,
)
from beeper_ui.services.identity_store import (
    DuplicateUserError,
    GroupNotFoundError,
    GroupRecord,
    IdentityStoreService,
    get_identity_store,
)

scim_bp = Blueprint("scim", __name__, url_prefix="/scim/v2")


@scim_bp.before_request
def _require_scim_bearer_auth() -> Any:
    """The sole auth gate for every `/scim/v2/*` request (see module
    docstring). Stashes the accepted token's fingerprint on `g` for
    `_audit()` below — the raw token value is never stored anywhere past
    `authenticate_scim_request()`'s own local variable."""
    error, fingerprint = authenticate_scim_request()
    if error is not None:
        return error
    g.scim_token_fingerprint = fingerprint
    return None


def _store() -> IdentityStoreService:
    return get_identity_store()


def _admin_groups() -> tuple[str, ...]:
    """Per ADR §5.2/Task 8.3's integration contract: pass the CURRENT
    config value explicitly on every call — never rely on the identity
    store singleton's construction-time default, which is fixed at first
    use and won't reflect a config change without a process restart."""
    return parse_group_names(current_app.config.get("BEEPER_ADMIN_GROUPS", ""))


def _audit(
    *,
    operation: str,
    resource_type: str,
    resource_id: str | None,
    target: str,
    admin_group_change: bool = False,
    detail: str = "",
) -> None:
    audit_log(
        operation=operation,
        resource_type=resource_type,
        resource_id=resource_id,
        target=target,
        token_fingerprint=getattr(g, "scim_token_fingerprint", "unknown"),
        admin_group_change=admin_group_change,
        detail=detail,
    )


def _json_body() -> dict[str, Any] | None:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else None


# ---------------------------------------------------------------------------
# Discovery (static)
# ---------------------------------------------------------------------------


@scim_bp.route("/ServiceProviderConfig", methods=["GET"])
def service_provider_config() -> Any:
    return jsonify(SERVICE_PROVIDER_CONFIG), 200, {"Content-Type": SCIM_CONTENT_TYPE}


@scim_bp.route("/ResourceTypes", methods=["GET"])
def resource_types() -> Any:
    resources = list(RESOURCE_TYPES_BY_NAME.values())
    body = scim_list_response(
        resources, start_index=1, count=len(resources), total_results=len(resources)
    )
    return jsonify(body), 200, {"Content-Type": SCIM_CONTENT_TYPE}


@scim_bp.route("/ResourceTypes/<name>", methods=["GET"])
def resource_type_detail(name: str) -> Any:
    resource_type = RESOURCE_TYPES_BY_NAME.get(name)
    if resource_type is None:
        return scim_error_response(status=404, detail=f"ResourceType {name!r} not found.")
    return jsonify(resource_type), 200, {"Content-Type": SCIM_CONTENT_TYPE}


@scim_bp.route("/Schemas", methods=["GET"])
def schemas() -> Any:
    resources = list(SCHEMAS_BY_ID.values())
    body = scim_list_response(
        resources, start_index=1, count=len(resources), total_results=len(resources)
    )
    return jsonify(body), 200, {"Content-Type": SCIM_CONTENT_TYPE}


@scim_bp.route("/Schemas/<path:schema_id>", methods=["GET"])
def schema_detail(schema_id: str) -> Any:
    schema = SCHEMAS_BY_ID.get(schema_id)
    if schema is None:
        return scim_error_response(status=404, detail=f"Schema {schema_id!r} not found.")
    return jsonify(schema), 200, {"Content-Type": SCIM_CONTENT_TYPE}


# ---------------------------------------------------------------------------
# /Users
# ---------------------------------------------------------------------------


@scim_bp.route("/Users", methods=["GET"])
def list_users() -> Any:
    try:
        parsed_filter = parse_eq_filter(request.args.get("filter"))
    except ScimFilterError as exc:
        return scim_error_response(status=400, detail=str(exc), scim_type="invalidFilter")
    start_index, count = parse_pagination(request.args)
    excluded = parse_excluded_attributes(request.args.get("excludedAttributes"))

    records = _store().list_users(limit=10_000)
    if parsed_filter is not None:
        attr, value = parsed_filter
        value_cf = value.strip().casefold()
        if attr == "username":
            records = [r for r in records if r.user_name_lc == value_cf]
        elif attr == "externalid":
            records = [r for r in records if r.external_id == value]
        elif attr == "displayname":
            records = [r for r in records if r.display_name.casefold() == value_cf]
        else:
            return scim_error_response(
                status=400,
                detail=f"Unsupported filter attribute for /Users: {attr!r}",
                scim_type="invalidFilter",
            )

    total = len(records)
    page = records[start_index - 1 : start_index - 1 + count] if count else []
    resources = [user_to_scim_resource(r, excluded_attributes=excluded) for r in page]
    body = scim_list_response(resources, start_index=start_index, count=count, total_results=total)
    return jsonify(body), 200, {"Content-Type": SCIM_CONTENT_TYPE}


@scim_bp.route("/Users", methods=["POST"])
def create_user() -> Any:
    body = _json_body()
    if body is None:
        return scim_error_response(
            status=400, detail="Request body must be a JSON object.", scim_type="invalidSyntax"
        )

    user_name = body.get("userName") or primary_email(body.get("emails"))
    if not user_name:
        return scim_error_response(
            status=400,
            detail=(
                "userName (or a primary email, per the Entra userName/emails "
                "fallback) is required."
            ),
            scim_type="invalidValue",
        )
    external_id = body.get("externalId") or ""
    if not external_id:
        return scim_error_response(
            status=400, detail="externalId is required.", scim_type="invalidValue"
        )

    store = _store()
    existing = store.get_by_username(user_name)
    if existing is not None and existing.origin == "scim":
        # A genuine duplicate SCIM-origin userName (e.g. a stale retry with
        # a different externalId) — RFC 7644 §3.3's 409 uniqueness. An
        # existing origin="local" record is NOT a duplicate in this sense
        # — it's the ADR §5.2 adopt-and-link scenario, handled below via
        # `adopt_or_create_scim_user()`.
        return scim_error_response(
            status=409, detail=f"userName {user_name!r} already exists.", scim_type="uniqueness"
        )

    admin_groups = _admin_groups()
    group_names = extract_group_display_names(body.get("groups"))
    active = coerce_bool(body.get("active", True))
    display_name = body.get("displayName") or user_name
    emails = coerce_emails(body.get("emails"))
    old_role = existing.role if existing is not None else None
    was_adoption = existing is not None

    record = store.adopt_or_create_scim_user(
        user_name=user_name,
        external_id=external_id,
        display_name=display_name,
        emails=emails,
        group_display_names=group_names,
        active=active,
        admin_groups=admin_groups,
    )
    _audit(
        operation="adopt" if was_adoption else "create",
        resource_type="User",
        resource_id=record.id,
        target=record.user_name,
        admin_group_change=is_admin_group_change(old_role, record.role),
    )
    return (
        jsonify(user_to_scim_resource(record)),
        201,
        {"Content-Type": SCIM_CONTENT_TYPE, "Location": f"/scim/v2/Users/{record.id}"},
    )


@scim_bp.route("/Users/<user_id>", methods=["GET"])
def get_user(user_id: str) -> Any:
    record = _store().get_by_id(user_id, use_cache=False)
    if record is None:
        return scim_error_response(status=404, detail=f"User {user_id!r} not found.")
    excluded = parse_excluded_attributes(request.args.get("excludedAttributes"))
    return jsonify(user_to_scim_resource(record, excluded_attributes=excluded)), 200, {
        "Content-Type": SCIM_CONTENT_TYPE
    }


@scim_bp.route("/Users/<user_id>", methods=["PUT"])
def replace_user(user_id: str) -> Any:
    """Full-resource replace (RFC 7644 §3.5.1). Only the mutable,
    non-role User attributes are honored — `role` is never client-set via
    SCIM (FR56); it is derived exclusively from group membership and is
    left untouched by a Users PUT/PATCH (ADR §5.1: role is "recomputed at
    write time on every GROUP mutation" — this is a USER mutation)."""
    store = _store()
    record = store.get_by_id(user_id, use_cache=False)
    if record is None:
        return scim_error_response(status=404, detail=f"User {user_id!r} not found.")
    body = _json_body()
    if body is None:
        return scim_error_response(
            status=400, detail="Request body must be a JSON object.", scim_type="invalidSyntax"
        )

    user_name = body.get("userName") or primary_email(body.get("emails")) or record.user_name
    display_name = body.get("displayName") or user_name
    emails = coerce_emails(body.get("emails")) if "emails" in body else record.emails
    active = coerce_bool(body.get("active", record.active))

    try:
        updated = store.update_user(
            user_id, user_name=user_name, display_name=display_name, emails=emails, active=active
        )
    except DuplicateUserError as exc:
        return scim_error_response(status=409, detail=str(exc), scim_type="uniqueness")

    _audit(operation="replace", resource_type="User", resource_id=user_id, target=updated.user_name)
    return jsonify(user_to_scim_resource(updated)), 200, {"Content-Type": SCIM_CONTENT_TYPE}


@scim_bp.route("/Users/<user_id>", methods=["PATCH"])
def patch_user(user_id: str) -> Any:
    store = _store()
    record = store.get_by_id(user_id, use_cache=False)
    if record is None:
        return scim_error_response(status=404, detail=f"User {user_id!r} not found.")
    body = _json_body()
    try:
        operations = parse_patch_operations(body)
        changes = apply_user_patch(operations)
    except ScimPatchError as exc:
        return scim_error_response(status=400, detail=str(exc), scim_type="invalidPath")

    try:
        updated = store.update_user(user_id, **changes) if changes else record
    except DuplicateUserError as exc:
        return scim_error_response(status=409, detail=str(exc), scim_type="uniqueness")

    _audit(operation="patch", resource_type="User", resource_id=user_id, target=updated.user_name)
    return jsonify(user_to_scim_resource(updated)), 200, {"Content-Type": SCIM_CONTENT_TYPE}


@scim_bp.route("/Users/<user_id>", methods=["DELETE"])
def delete_user(user_id: str) -> Any:
    store = _store()
    record = store.get_by_id(user_id, use_cache=False)
    if record is None:
        return scim_error_response(status=404, detail=f"User {user_id!r} not found.")
    was_active_admin = record.active and record.role == "admin"
    store.delete_user(user_id)
    _audit(
        operation="delete",
        resource_type="User",
        resource_id=user_id,
        target=record.user_name,
        admin_group_change=was_active_admin,
    )
    return "", 204


# ---------------------------------------------------------------------------
# /Groups
# ---------------------------------------------------------------------------


@scim_bp.route("/Groups", methods=["GET"])
def list_groups() -> Any:
    try:
        parsed_filter = parse_eq_filter(request.args.get("filter"))
    except ScimFilterError as exc:
        return scim_error_response(status=400, detail=str(exc), scim_type="invalidFilter")
    start_index, count = parse_pagination(request.args)
    excluded = parse_excluded_attributes(request.args.get("excludedAttributes"))

    records = _store().list_groups(limit=10_000)
    if parsed_filter is not None:
        attr, value = parsed_filter
        if attr == "displayname":
            records = [g for g in records if g.display_name_lc == value.strip().casefold()]
        elif attr == "externalid":
            records = [g for g in records if g.external_id == value]
        else:
            return scim_error_response(
                status=400,
                detail=f"Unsupported filter attribute for /Groups: {attr!r}",
                scim_type="invalidFilter",
            )

    total = len(records)
    page = records[start_index - 1 : start_index - 1 + count] if count else []
    resources = [group_to_scim_resource(g, excluded_attributes=excluded) for g in page]
    body = scim_list_response(resources, start_index=start_index, count=count, total_results=total)
    return jsonify(body), 200, {"Content-Type": SCIM_CONTENT_TYPE}


def _find_existing_group_for_create(
    store: IdentityStoreService, *, external_id: str | None, display_name: str
) -> GroupRecord | None:
    if external_id:
        existing = store.get_group_by_external_id(external_id)
        if existing is not None:
            return existing
    display_name_cf = display_name.strip().casefold()
    for group in store.list_groups(limit=10_000):
        if group.display_name_lc == display_name_cf:
            return group
    return None


@scim_bp.route("/Groups", methods=["POST"])
def create_group() -> Any:
    body = _json_body()
    if body is None:
        return scim_error_response(
            status=400, detail="Request body must be a JSON object.", scim_type="invalidSyntax"
        )
    display_name = body.get("displayName")
    if not display_name:
        return scim_error_response(
            status=400, detail="displayName is required.", scim_type="invalidValue"
        )

    store = _store()
    external_id = body.get("externalId")
    existing = _find_existing_group_for_create(
        store, external_id=external_id, display_name=display_name
    )
    if existing is not None:
        return scim_error_response(
            status=409, detail=f"Group {display_name!r} already exists.", scim_type="uniqueness"
        )

    member_ids = extract_member_ids(body.get("members"))
    group = store.upsert_group(
        external_id=external_id, display_name=display_name, member_ids=member_ids
    )

    admin_groups = _admin_groups()
    admin_change = False
    for uid in member_ids:
        result = recompute_role_for_user(store, uid, admin_groups)
        if result and is_admin_group_change(result[0], result[1]):
            admin_change = True

    _audit(
        operation="create",
        resource_type="Group",
        resource_id=group.id,
        target=group.display_name,
        admin_group_change=admin_change,
    )
    return (
        jsonify(group_to_scim_resource(group)),
        201,
        {"Content-Type": SCIM_CONTENT_TYPE, "Location": f"/scim/v2/Groups/{group.id}"},
    )


@scim_bp.route("/Groups/<group_id>", methods=["GET"])
def get_group(group_id: str) -> Any:
    group = _store().get_group_by_id(group_id)
    if group is None:
        return scim_error_response(status=404, detail=f"Group {group_id!r} not found.")
    excluded = parse_excluded_attributes(request.args.get("excludedAttributes"))
    return jsonify(group_to_scim_resource(group, excluded_attributes=excluded)), 200, {
        "Content-Type": SCIM_CONTENT_TYPE
    }


def _recompute_affected_members(
    store: IdentityStoreService,
    *,
    old_members: set[str],
    new_members: set[str],
    display_name_changed: bool = False,
) -> bool:
    """Recompute role for every user affected by this group mutation, and
    return whether any of those recomputes crossed the admin boundary.

    When ONLY membership changed, the affected set is the symmetric
    difference (added ∪ removed) — unaffected existing members can't have
    a different role. When `display_name_changed` is True, the affected
    set widens to old_members ∪ new_members: a rename that moves this
    group into or out of `BEEPER_ADMIN_GROUPS` (e.g. "Sales" -> "Admins")
    changes the derived role for EVERY current member even though nobody
    was added or removed — the plan's Task 8.8 AC names this explicitly
    ("group-rename recompute"). Membership-unchanged members would
    otherwise have an empty symmetric difference and be silently skipped.
    """
    affected = (old_members | new_members) if display_name_changed else (old_members ^ new_members)
    admin_groups = _admin_groups()
    admin_change = False
    for uid in affected:
        result = recompute_role_for_user(store, uid, admin_groups)
        if result and is_admin_group_change(result[0], result[1]):
            admin_change = True
    return admin_change


@scim_bp.route("/Groups/<group_id>", methods=["PUT"])
def replace_group(group_id: str) -> Any:
    store = _store()
    group = store.get_group_by_id(group_id)
    if group is None:
        return scim_error_response(status=404, detail=f"Group {group_id!r} not found.")
    body = _json_body()
    if body is None:
        return scim_error_response(
            status=400, detail="Request body must be a JSON object.", scim_type="invalidSyntax"
        )

    display_name = body.get("displayName") or group.display_name
    new_member_ids = extract_member_ids(body.get("members"))
    old_members = set(group.member_ids)
    new_members = set(new_member_ids)

    try:
        updated = store.update_group(
            group_id, display_name=display_name, member_ids=sorted(new_members)
        )
    except GroupNotFoundError:
        return scim_error_response(status=404, detail=f"Group {group_id!r} not found.")

    admin_change = _recompute_affected_members(
        store,
        old_members=old_members,
        new_members=new_members,
        display_name_changed=display_name != group.display_name,
    )
    _audit(
        operation="replace",
        resource_type="Group",
        resource_id=group_id,
        target=updated.display_name,
        admin_group_change=admin_change,
    )
    return jsonify(group_to_scim_resource(updated)), 200, {"Content-Type": SCIM_CONTENT_TYPE}


@scim_bp.route("/Groups/<group_id>", methods=["PATCH"])
def patch_group(group_id: str) -> Any:
    """Membership-delta PATCH — BOTH vendor dialects (ADR §4): Okta's
    `{"op": "add"|"remove", "path": "members", "value": [...]}` and
    Entra's `{"op": "remove", "path": 'members[value eq "<id>"]'}`. See
    `beeper_ui.routes.scim_helpers.apply_group_patch()`."""
    store = _store()
    group = store.get_group_by_id(group_id)
    if group is None:
        return scim_error_response(status=404, detail=f"Group {group_id!r} not found.")
    body = _json_body()
    try:
        operations = parse_patch_operations(body)
        patch = apply_group_patch(operations)
    except ScimPatchError as exc:
        return scim_error_response(status=400, detail=str(exc), scim_type="invalidPath")

    old_members = set(group.member_ids)
    if patch.replace_ids is not None:
        new_members = set(patch.replace_ids)
    else:
        new_members = (old_members | set(patch.add_ids)) - set(patch.remove_ids)
    display_name = patch.display_name or group.display_name

    try:
        updated = store.update_group(
            group_id, display_name=display_name, member_ids=sorted(new_members)
        )
    except GroupNotFoundError:
        return scim_error_response(status=404, detail=f"Group {group_id!r} not found.")

    admin_change = _recompute_affected_members(
        store,
        old_members=old_members,
        new_members=new_members,
        display_name_changed=display_name != group.display_name,
    )
    _audit(
        operation="patch",
        resource_type="Group",
        resource_id=group_id,
        target=updated.display_name,
        admin_group_change=admin_change,
        detail=(
            f"members_added={sorted(new_members - old_members)} "
            f"members_removed={sorted(old_members - new_members)}"
        ),
    )
    return jsonify(group_to_scim_resource(updated)), 200, {"Content-Type": SCIM_CONTENT_TYPE}


@scim_bp.route("/Groups/<group_id>", methods=["DELETE"])
def delete_group(group_id: str) -> Any:
    """Hard-delete a group (RFC 7644 §3.6, ADR §4). Deliberately does NOT
    cascade a role recompute to former members — RFC 7644 does not
    require server-side cascade on group delete, and SCIM clients are
    expected to have already removed members before deleting the group
    (mirrors `IdentityStoreService.delete_group()`'s documented scope
    limit)."""
    store = _store()
    group = store.get_group_by_id(group_id)
    if group is None:
        return scim_error_response(status=404, detail=f"Group {group_id!r} not found.")
    store.delete_group(group_id)
    admin_groups = _admin_groups()
    is_admin_group = group.display_name.strip().casefold() in {g.casefold() for g in admin_groups}
    _audit(
        operation="delete",
        resource_type="Group",
        resource_id=group_id,
        target=group.display_name,
        admin_group_change=is_admin_group and bool(group.member_ids),
    )
    return "", 204


# ---------------------------------------------------------------------------
# Catch-all: any other /scim/v2/* resource (Bulk, Me, ...) — 501, not a
# generic 404, since these are recognized-but-unimplemented SCIM concepts
# (ADR §4: "everything else 501"). Registered last; Werkzeug's routing
# prefers the static rules above over this `<path:...>` catch-all
# regardless of declaration order, so it never shadows a real endpoint.
# ---------------------------------------------------------------------------


@scim_bp.route("/<path:rest>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def not_implemented(rest: str) -> Any:
    return scim_error_response(
        status=501, detail=f"SCIM operation not implemented: {request.method} /scim/v2/{rest}"
    )
