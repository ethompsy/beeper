"""Helpers for the SCIM 2.0 provisioning surface (Task 8.8 — ADR 0002 §4).

Kept separate from `scim.py` (the Flask blueprint + route handlers) so the
route module stays focused on HTTP wiring: this module owns bearer
authentication, SCIM resource (de)serialization, `eq`-filter parsing, the
two vendor PATCH-op dialects, pagination, the SCIM error-response envelope
(the recorded RFC7807 deviation, scoped to `/scim/v2/*` — ADR §4), and the
audit-log line format (FR58: op, resource, actor token fingerprint —
*never* the token — with admin-group membership changes flagged
distinctly).

Zero new runtime dependencies (ADR §4: "the `eq` filter is a ~10-line
parse"). `jsonschema`-based response validation is a *test-only* dev
dependency (`ui/tests/_scim_json_schemas.py`), not imported here.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from flask import Response, current_app, jsonify, request

from beeper_ui.services.identity_store import IdentityStoreService

logger = logging.getLogger("beeper_ui.scim.audit")

# FR58 requires every provisioning mutation to be audit-logged in the DEPLOYED
# process, not just under test. The records are INFO-level, but Flask/Werkzeug
# leave the root logger unconfigured (effective WARNING via logging.lastResort),
# so without a dedicated handler the audit trail is silently dropped in-cluster
# — found in the Task 8.9 live validation (unit tests passed via caplog, which
# bypasses handler config). A dedicated handler makes emission
# independent of ambient logging configuration.
if not logger.handlers:
    _audit_handler = logging.StreamHandler()
    _audit_handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    )
    logger.addHandler(_audit_handler)
    logger.setLevel(logging.INFO)
    # propagate stays True: pytest's caplog captures via root propagation, and
    # in-cluster the unconfigured root drops INFO silently, so the dedicated
    # handler above is the only in-cluster emitter (no double lines).

# RFC 7644 §3.1: SCIM's own content type. Used on every /scim/v2/* response
# (a recorded deviation from the rest of the app's `application/problem+json`
# convention — SCIM error bodies use the SCIM error schema, not RFC7807; see
# `scim_error_response()` below and ADR 0002 §4).
SCIM_CONTENT_TYPE = "application/scim+json"

SCIM_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
SCIM_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"

DEFAULT_PAGE_COUNT = 100
MAX_PAGE_COUNT = 200


class ScimFilterError(ValueError):
    """An unsupported or malformed SCIM `filter` query parameter."""


class ScimPatchError(ValueError):
    """A malformed SCIM PATCH request body."""


# ---------------------------------------------------------------------------
# Bearer auth (ADR §4/§8, FR58)
# ---------------------------------------------------------------------------


def _fingerprint(token: str) -> str:
    """`sha256(token)[:8]` — the ONLY form of a SCIM token that may ever be
    logged (FR58: "audit-logged with a token fingerprint, never the
    token"). Same construction the ADR names explicitly (§4)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:8]


def authenticate_scim_request() -> tuple[Any, str | None]:
    """Bearer-auth gate for every `/scim/v2/*` request.

    Returns `(error_response, token_fingerprint)`:
      - On success: `(None, fingerprint)` — `fingerprint` is the accepted
        token's `sha256[:8]`, threaded through to the audit log.
      - On failure: `(scim_error_response(...), None)` — the caller
        returns `error_response` directly from its `before_request` hook.

    Three fail-closed cases, deliberately distinguished (ADR §4/§8):

    1. **Enabled but unconfigured** — neither `BEEPER_SCIM_TOKEN` nor
       `BEEPER_SCIM_TOKEN_SECONDARY` is set. `403`, naming the
       misconfiguration. ADR §8 picks this over a boot refusal
       ("SCIM enabled without a token ... surface registers fail-closed
       403, per §4") and over a plain 401: a 401 implies "authenticate and
       retry," which is never true here — no bearer value an IdP could
       ever present would succeed until an operator configures a token, so
       naming the *operator-facing* misconfiguration at 403 is more
       honest than repeatedly telling the IdP's credential is wrong.
    2. **Missing/malformed `Authorization` header, or a token that matches
       neither configured value** — `401`, generic "invalid bearer token"
       (never reveals which of the two configured values, if any, is
       set — that would leak rotation state to an unauthenticated
       caller).
    3. **Token matches the primary OR secondary value** — success. Both
       are accepted simultaneously (not "primary preferred, secondary as
       fallback") — that symmetry IS the zero-downtime dual-token rotation
       contract: during a rotation window, old-token IdP requests and
       new-token IdP requests both succeed, in any order, for as long as
       both config values are set.

    Comparison is constant-time (`hmac.compare_digest`) against each
    configured value independently — never a "compare against a
    concatenation" or "compare against whichever is longer" shortcut that
    could leak which slot matched via timing.
    """
    primary = (current_app.config.get("BEEPER_SCIM_TOKEN") or "").strip()
    secondary = (current_app.config.get("BEEPER_SCIM_TOKEN_SECONDARY") or "").strip()
    if not primary and not secondary:
        return (
            scim_error_response(
                status=403,
                detail=(
                    "SCIM is enabled but no bearer token is configured "
                    "(BEEPER_SCIM_TOKEN / BEEPER_SCIM_TOKEN_SECONDARY). "
                    "Every request is refused until an operator sets a "
                    "token via the SCIM Secret."
                ),
            ),
            None,
        )

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return scim_error_response(status=401, detail="Missing or malformed bearer token."), None
    presented = auth_header[len("Bearer ") :].strip()
    if not presented:
        return scim_error_response(status=401, detail="Missing or malformed bearer token."), None

    presented_bytes = presented.encode("utf-8")
    matched = (primary and hmac.compare_digest(presented_bytes, primary.encode("utf-8"))) or (
        secondary and hmac.compare_digest(presented_bytes, secondary.encode("utf-8"))
    )
    if not matched:
        return scim_error_response(status=401, detail="Invalid bearer token."), None

    return None, _fingerprint(presented)


# ---------------------------------------------------------------------------
# SCIM error / list envelopes (ADR §4 — the recorded RFC7807 deviation)
# ---------------------------------------------------------------------------


def scim_error_response(
    *, status: int, detail: str, scim_type: str | None = None
) -> tuple[Response, int, dict[str, str]]:
    """RFC 7644 §3.12 SCIM error response body.

    `scimType` (when given) is one of RFC 7644's enumerated values
    (`invalidFilter`, `uniqueness`, `invalidPath`, `invalidValue`,
    `invalidSyntax`, ...) — see individual call sites.
    """
    body: dict[str, Any] = {"schemas": [SCIM_ERROR_SCHEMA], "status": str(status), "detail": detail}
    if scim_type:
        body["scimType"] = scim_type
    return jsonify(body), status, {"Content-Type": SCIM_CONTENT_TYPE}


def scim_list_response(
    resources: list[dict[str, Any]], *, start_index: int, count: int, total_results: int
) -> dict[str, Any]:
    """RFC 7644 §3.4.2 ListResponse envelope, 1-based `startIndex`."""
    return {
        "schemas": [SCIM_LIST_SCHEMA],
        "totalResults": total_results,
        "startIndex": start_index,
        "itemsPerPage": len(resources),
        "Resources": resources,
    }


def parse_pagination(args: Any) -> tuple[int, int]:
    """`startIndex` (1-based, RFC 7644 §3.4.2) / `count` query params, with
    tolerant coercion (non-numeric or absent falls back to the default
    rather than 400ing — pagination params are optional per the RFC)."""
    try:
        start_index = int(args.get("startIndex", 1))
    except (TypeError, ValueError):
        start_index = 1
    if start_index < 1:
        start_index = 1
    try:
        count = int(args.get("count", DEFAULT_PAGE_COUNT))
    except (TypeError, ValueError):
        count = DEFAULT_PAGE_COUNT
    if count < 0:
        count = 0
    count = min(count, MAX_PAGE_COUNT)
    return start_index, count


def parse_excluded_attributes(raw: str | None) -> frozenset[str]:
    """`excludedAttributes` query param (RFC 7644 §3.9), comma-separated.
    ADR §4 names honoring `excludedAttributes=members` on `/Groups` GET
    explicitly; implemented generically here since RFC 7644 doesn't scope
    the parameter to any one resource type or attribute."""
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def _apply_excluded_attributes(
    resource: dict[str, Any], excluded: frozenset[str]
) -> dict[str, Any]:
    if not excluded:
        return resource
    excluded_lc = {e.lower() for e in excluded}
    return {k: v for k, v in resource.items() if k.lower() not in excluded_lc}


# ---------------------------------------------------------------------------
# Resource (de)serialization
# ---------------------------------------------------------------------------


def user_to_scim_resource(
    record: Any, *, excluded_attributes: frozenset[str] = frozenset()
) -> dict[str, Any]:
    """`UserRecord` -> RFC 7643 §4.1 User resource."""
    resource: dict[str, Any] = {
        "schemas": [USER_SCHEMA],
        "id": record.id,
        "externalId": record.external_id,
        "userName": record.user_name,
        "displayName": record.display_name,
        "name": {"formatted": record.display_name},
        "emails": [{"value": e, "primary": i == 0} for i, e in enumerate(record.emails)],
        "active": record.active,
        # Read-only per RFC 7643 §4.1.2 — membership is written via the
        # Group resource (ADR §5.1's "group_ids (read-model)"), never here.
        "groups": [{"value": gid} for gid in record.group_ids],
        "meta": {
            "resourceType": "User",
            "created": record.created,
            "lastModified": record.last_modified,
            "location": f"/scim/v2/Users/{record.id}",
        },
    }
    return _apply_excluded_attributes(resource, excluded_attributes)


def group_to_scim_resource(
    record: Any, *, excluded_attributes: frozenset[str] = frozenset()
) -> dict[str, Any]:
    """`GroupRecord` -> RFC 7643 §4.2 Group resource."""
    resource: dict[str, Any] = {
        "schemas": [GROUP_SCHEMA],
        "id": record.id,
        "externalId": record.external_id,
        "displayName": record.display_name,
        "members": [{"value": m} for m in record.member_ids],
        "meta": {
            "resourceType": "Group",
            "location": f"/scim/v2/Groups/{record.id}",
        },
    }
    return _apply_excluded_attributes(resource, excluded_attributes)


# ---------------------------------------------------------------------------
# Vendor-quirk-tolerant value coercion (ADR §4)
# ---------------------------------------------------------------------------


def coerce_bool(value: Any) -> bool:
    """String-boolean tolerance (ADR §4 named quirk): some SCIM clients
    send `"true"`/`"false"` as JSON strings instead of a native boolean
    for `active`."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def coerce_emails(value: Any) -> list[str]:
    """Accepts RFC-shaped `[{"value": "...", ...}, ...]`, a bare list of
    strings, or a single string — tolerant of minor vendor variance."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, dict) and "value" in item:
                out.append(str(item["value"]))
            elif isinstance(item, str):
                out.append(item)
        return out
    return []


def primary_email(emails_raw: Any) -> str | None:
    emails = coerce_emails(emails_raw)
    return emails[0] if emails else None


def extract_group_display_names(groups_raw: Any) -> list[str]:
    """Best-effort: a User POST body's optional `groups` attribute is
    read-only per RFC 7643 §4.1.2 in real deployments — Okta/Entra/
    Keycloak all manage membership exclusively via Group resource writes
    (POST/PATCH `/Groups`), never via this field. Extracting `display`
    (never `value`, which is the group's SCIM `id`, not comparable to
    `BEEPER_ADMIN_GROUPS`) is a defensive fallback only; the authoritative
    path is `recompute_role_for_user()` below, driven by Group writes."""
    if not isinstance(groups_raw, list):
        return []
    return [
        str(item["display"])
        for item in groups_raw
        if isinstance(item, dict) and item.get("display")
    ]


def extract_member_ids(value: Any) -> list[str]:
    """Accepts RFC-shaped `[{"value": "<user-id>", ...}, ...]`, a bare list
    of id strings, or a single `{"value": "..."}` object."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, dict) and "value" in item:
                out.append(str(item["value"]))
            elif isinstance(item, str):
                out.append(item)
        return out
    if isinstance(value, dict) and "value" in value:
        return [str(value["value"])]
    return []


# ---------------------------------------------------------------------------
# `eq` filter parsing (RFC 7644 §3.4.2.2) — ADR §4: "userName eq"/
# "externalId eq" on Users, "displayName eq" on Groups. Attribute NAME
# matching is case-insensitive per RFC 7643 §2.1; only `eq` is supported —
# any other operator (or a filter this can't parse) is a 400 `invalidFilter`,
# not a silent ignore.
# ---------------------------------------------------------------------------

_FILTER_RE = re.compile(r'^\s*([a-zA-Z0-9_.]+)\s+eq\s+"((?:[^"\\]|\\.)*)"\s*$', re.IGNORECASE)


def parse_eq_filter(filter_param: str | None) -> tuple[str, str] | None:
    """Returns `(attribute_name_lowercased, value)`, or `None` if no filter
    was given. Raises `ScimFilterError` for anything it can't parse as a
    single `attr eq "value"` clause."""
    if not filter_param:
        return None
    match = _FILTER_RE.match(filter_param)
    if not match:
        raise ScimFilterError(f"Unsupported or malformed filter: {filter_param!r}")
    attr, value = match.groups()
    value = value.replace('\\"', '"').replace("\\\\", "\\")
    return attr.lower(), value


# ---------------------------------------------------------------------------
# PATCH operation parsing (RFC 7644 §3.5.2) — op-case tolerance, path-less
# ops (ADR §4 named quirks).
# ---------------------------------------------------------------------------


def parse_patch_operations(body: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Normalize a PATCH request body's `Operations` array. Each returned
    dict is `{"op": "add"|"remove"|"replace", "path": str|None, "value":
    Any}` — `op` is lowercased here (case-insensitive PATCH ops is an ADR
    §4 named quirk: Okta and Entra do not agree on `Op`/`op` casing)."""
    if not body:
        raise ScimPatchError("Missing PATCH request body.")
    ops = body.get("Operations") or body.get("operations")
    if not isinstance(ops, list) or not ops:
        raise ScimPatchError("PATCH body must include a non-empty 'Operations' array.")
    normalized: list[dict[str, Any]] = []
    for raw_op in ops:
        if not isinstance(raw_op, dict):
            raise ScimPatchError("Each PATCH operation must be an object.")
        op = str(raw_op.get("op", "")).strip().lower()
        if op not in {"add", "remove", "replace"}:
            raise ScimPatchError(f"Unsupported PATCH op: {raw_op.get('op')!r}")
        normalized.append({"op": op, "path": raw_op.get("path"), "value": raw_op.get("value")})
    return normalized


# User PATCH: only the mutable, non-role attributes are recognized — role
# is NEVER settable via SCIM Users PATCH/PUT (FR56: "role assignment
# derives solely from the [admin-]group set", never a client-supplied
# value). Unknown attribute names are silently ignored (ADR §4 named
# quirk: "unknown attributes ignored").
_USER_PATCH_ATTR_ALIASES = {
    "active": "active",
    "displayname": "display_name",
    "username": "user_name",
    "emails": "emails",
}


def apply_user_patch(operations: list[dict[str, Any]]) -> dict[str, Any]:
    """Reduce normalized PATCH operations into an
    `IdentityStoreService.update_user()`-shaped kwargs dict.

    Tolerates (ADR §4 named quirks): string booleans for `active`,
    path-less `replace` ops whose `value` is an `{attr: value}` object,
    a sub-attribute/filter suffix on `path` (e.g. `name.formatted` — only
    the top-level attribute name drives a supported change), and unknown
    attributes (ignored, not an error).
    """
    changes: dict[str, Any] = {}
    for operation in operations:
        path = operation["path"]
        value = operation["value"]
        if path is None:
            if isinstance(value, dict):
                for raw_key, raw_val in value.items():
                    _apply_user_attr(changes, raw_key, raw_val)
            continue
        top_level = re.split(r"[.\[]", path, maxsplit=1)[0]
        _apply_user_attr(changes, top_level, value)
    return changes


def _apply_user_attr(changes: dict[str, Any], raw_key: str, value: Any) -> None:
    key = _USER_PATCH_ATTR_ALIASES.get(raw_key.strip().lower())
    if key is None:
        return
    if key == "active":
        changes["active"] = coerce_bool(value)
    elif key == "emails":
        changes["emails"] = coerce_emails(value)
    else:
        changes[key] = value


@dataclass
class GroupPatchResult:
    """Result of `apply_group_patch()` — see its docstring."""

    add_ids: list[str] = field(default_factory=list)
    remove_ids: list[str] = field(default_factory=list)
    replace_ids: list[str] | None = None
    display_name: str | None = None


# Entra's filtered-path membership-delta dialect:
# {"op": "remove", "path": 'members[value eq "<user-id>"]'}
_MEMBER_FILTER_RE = re.compile(r'members\[\s*value\s+eq\s+"([^"]+)"\s*\]', re.IGNORECASE)


def apply_group_patch(operations: list[dict[str, Any]]) -> GroupPatchResult:
    """Parse BOTH vendor membership-delta dialects (ADR §4):

    - **Okta-style**: `{"op": "add"|"remove", "path": "members", "value":
      [{"value": "<user-id>"}, ...]}` — a plain `path` with an array
      `value`.
    - **Entra-style**: `{"op": "remove", "path": 'members[value eq
      "<user-id>"]'}` — the target id is encoded IN the path via a filter
      expression, typically with no `value` at all.

    Also tolerates: `op: "replace"` with `path: "members"` (full
    membership replace — some Okta connectors sync this way), a `remove`
    on plain `path: "members"` with NO value (RFC 7644 §3.5.2.2: "If
    ``path`` contains no filter, the attribute and all values are
    removed" — realized here as `replace_ids = []`), and a path-less
    `replace` whose `value` is `{"members": [...], "displayName": "..."}`.
    """
    add_ids: list[str] = []
    remove_ids: list[str] = []
    replace_ids: list[str] | None = None
    display_name: str | None = None

    for operation in operations:
        op = operation["op"]
        path = operation["path"]
        value = operation["value"]

        if path is None:
            if isinstance(value, dict):
                if "members" in value:
                    replace_ids = extract_member_ids(value["members"])
                if "displayName" in value:
                    display_name = str(value["displayName"])
            continue

        path_stripped = path.strip()
        member_match = _MEMBER_FILTER_RE.search(path_stripped)
        if member_match:
            target_id = member_match.group(1)
            if op == "remove":
                remove_ids.append(target_id)
            elif op == "add":
                add_ids.append(target_id)
            continue

        top_level = re.split(r"[.\[]", path_stripped, maxsplit=1)[0].strip().lower()
        if top_level == "members":
            ids = extract_member_ids(value)
            if op == "add":
                add_ids.extend(ids)
            elif op == "remove":
                if ids:
                    remove_ids.extend(ids)
                else:
                    replace_ids = []  # RFC 7644 §3.5.2.2: no filter -> remove all
            elif op == "replace":
                replace_ids = ids
        elif top_level == "displayname" and isinstance(value, str):
            display_name = value

    return GroupPatchResult(
        add_ids=add_ids, remove_ids=remove_ids, replace_ids=replace_ids, display_name=display_name
    )


# ---------------------------------------------------------------------------
# Role recompute on group-membership mutation (ADR §5.1: "recomputed at
# write time on every group mutation")
# ---------------------------------------------------------------------------


def is_admin_group_change(old_role: str | None, new_role: str) -> bool:
    """True iff a role transition CROSSES the admin boundary (user<->admin)
    — used to decide the audit log's `admin_group_change` flag (FR58: "the
    highest-stakes mutation"). A `user`->`user` (no-op) or a transition
    that never touches `admin` at either end is NOT flagged."""
    old = old_role or "user"
    return old != new_role and (old == "admin" or new_role == "admin")


def recompute_role_for_user(
    store: IdentityStoreService, user_id: str, admin_groups: tuple[str, ...]
) -> tuple[str, str] | None:
    """Recompute `user_id`'s role from ALL of their CURRENT group
    memberships (every group in the store whose `member_ids` contains
    them) — not just the one group that just changed, since a user can
    belong to several groups simultaneously. Persists the result (and the
    refreshed `group_ids` read-model, ADR §5.1) via
    `store.update_user()`, which also runs the zero-active-admins alarm
    check (`_after_mutation`) — so a group-membership PATCH that removes
    the last admin's only admin-group membership alarms exactly the same
    way a direct role write would.

    Returns `(old_role, new_role)`, or `None` if `user_id` doesn't
    resolve to a stored user (e.g. an IdP pushed a Group membership
    referencing a user id Beeper has never seen — tolerated, not an
    error: SCIM does not require the server to reject unknown member
    references, and Okta/Entra routinely push Users and Groups out of
    strict dependency order).
    """
    record = store.get_by_id(user_id, use_cache=False)
    if record is None:
        return None
    all_groups = store.list_groups()
    member_group_names = [g.display_name for g in all_groups if user_id in g.member_ids]
    member_group_ids = [g.id for g in all_groups if user_id in g.member_ids]
    admin_cf = {g.casefold() for g in admin_groups if g}
    new_role = "admin" if any(n.casefold() in admin_cf for n in member_group_names if n) else "user"
    old_role = record.role
    if new_role != old_role or set(member_group_ids) != set(record.group_ids):
        store.update_user(user_id, role=new_role, group_ids=member_group_ids)
    return old_role, new_role


# ---------------------------------------------------------------------------
# Audit log (FR58: op, resource, actor fingerprint — never the token —
# admin-group changes flagged distinctly)
# ---------------------------------------------------------------------------


def audit_log(
    *,
    operation: str,
    resource_type: str,
    resource_id: str | None,
    target: str,
    token_fingerprint: str,
    admin_group_change: bool = False,
    detail: str = "",
) -> None:
    """Log one SCIM provisioning mutation at INFO (ADR §4: "every
    provisioning mutation is audit-logged at INFO"). Grep-stable prefix
    `"SCIM audit:"`; the token fingerprint is the ONLY token-derived value
    ever logged — the raw bearer token is never passed to this function in
    the first place (call sites thread through `g.scim_token_fingerprint`,
    never the header value)."""
    logger.info(
        "SCIM audit: op=%s resource_type=%s resource_id=%s target=%s "
        "token_fp=%s admin_group_change=%s%s",
        operation,
        resource_type,
        resource_id or "-",
        target,
        token_fingerprint,
        admin_group_change,
        f" detail={detail}" if detail else "",
    )
