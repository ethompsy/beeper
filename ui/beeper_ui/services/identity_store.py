"""Shared identity store — one store, two writers (Task 8.3 / ADR 0002 §5).

Owns two Qdrant payload-only collections (zero-vector points, scroll+filter,
`_ensure_collection`, module singleton + `reset_*` — the
`beeper_ui.services.collaboration_service` pattern, per the no-new-datastore
constraint):

- `beeper_users` — merged SCIM + local schema (ADR §5.1): canonical
  `user_name_lc` (casefolded) key, `external_id` machine join key, `role`
  (the authorization value), `active`, `origin` ("local" | "scim"),
  `password_hash` (nullable — pure-SCIM users have none).
- `beeper_groups` — arbitrary IdP-pushed groups, passthrough (no
  two-fixed-rows concept — that fallback-pillar design is superseded).

Both collections are created lazily, on first use, exactly like
`collaboration_service` — this module is NEVER imported/constructed by any
code path in mode `none` (see `beeper_ui.middleware.permissions
.resolve_role_for_identity()`, which only calls `get_identity_store()` when
`BEEPER_AUTH_MODE != "none"`), so demo Qdrant stays clean (ADR §5).

Read/write contract for downstream tasks (8.5 OIDC, 8.6 local auth, 8.7
admin UI, 8.8 SCIM) — see the module-level docstrings on `lookup()`,
`adopt_or_create_scim_user()`, and `would_orphan_admins()` for the pinned
interfaces each of those tasks integrates against.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

logger = logging.getLogger(__name__)

USERS_COLLECTION = "beeper_users"
GROUPS_COLLECTION = "beeper_groups"

# ADR §2/§5.1: "one TTL program-wide" for store-backed role resolution.
ROLE_CACHE_TTL_SECONDS = 60.0

VALID_ROLES = frozenset({"admin", "user"})

# ADR §3 default: "Admins" per the directive's naming, "beeper-admin" for
# continuity with the group name the deleted token path historically looked
# for. Only used when a caller doesn't supply `admin_groups` explicitly —
# callers with Flask app-context access should prefer passing
# `parse_group_names(current_app.config["BEEPER_ADMIN_GROUPS"])`
# per-call (see `adopt_or_create_scim_user()`), since the module singleton's
# construction-time default is fixed at first use and won't reflect a
# config change without a process restart.
DEFAULT_ADMIN_GROUPS: tuple[str, ...] = ("Admins", "beeper-admin")


class IdentityStoreError(Exception):
    """Base error for identity store operations."""


class DuplicateUserError(IdentityStoreError):
    """Raised when a `user_name_lc` uniqueness check fails (409 semantics).

    Uniqueness is enforced service-layer, check-then-insert, under a
    process lock (`self._write_lock`) — safe at `replicaCount: 1` (ADR
    §5.1's named invariant; revisit before any multi-replica change).
    """


class UserNotFoundError(IdentityStoreError):
    """Raised when a mutation targets a user id that doesn't exist."""


class LastAdminError(IdentityStoreError):
    """Raised by `update_user(..., guard_last_admin=True)` when the write
    would leave zero active admins.

    ADDITIVE (Task 8.7 — security-review fix). Before this, the admin-users
    route's last-admin refusal was TWO separate calls —
    `would_orphan_admins()` (its own, UNLOCKED read) followed by a later,
    separately-locked `update_user()` — which left a TOCTOU race: two
    concurrent demotions of two different admins could each observe "not
    the last admin" before either write landed, together orphaning the
    store. This exception is raised from INSIDE `update_user()`'s own
    `self._write_lock` critical section, so the check and the write are
    now atomic relative to every other call through this same lock (the
    only way any mutation reaches the store). `would_orphan_admins()`
    itself is UNCHANGED and remains available as a cheap, non-mutating,
    best-effort pre-check (e.g. for a UI that wants to disable a control
    before the user even submits) — it is simply no longer the sole
    enforcement mechanism for admin-UI callers, which now pass
    `guard_last_admin=True` for the authoritative check.
    """


class GroupNotFoundError(IdentityStoreError):
    """Raised when a mutation targets a group id that doesn't exist.

    ADDITIVE (Task 8.8 — SCIM surface), mirrors `UserNotFoundError`. See
    `update_group()`'s docstring for why this — and that method — exist
    alongside the pre-existing `upsert_group()`.
    """


@dataclass
class UserRecord:
    """`beeper_users` schema (ADR §5.1). Point id = uuid4 (== `id` below)."""

    id: str
    external_id: str | None
    user_name: str
    user_name_lc: str
    display_name: str
    emails: list[str] = field(default_factory=list)
    active: bool = True
    origin: str = "local"  # "local" | "scim"
    password_hash: str | None = None
    role: str = "user"  # "admin" | "user" — THE authorization value
    group_ids: list[str] = field(default_factory=list)
    created: str = ""
    last_modified: str = ""
    last_login_at: str | None = None

    def to_payload(self) -> dict[str, Any]:
        """Convert to a Qdrant payload dict."""
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> UserRecord:
        """Create from a Qdrant point payload dict."""
        return cls(
            id=payload.get("id", ""),
            external_id=payload.get("external_id"),
            user_name=payload.get("user_name", ""),
            user_name_lc=payload.get("user_name_lc", ""),
            display_name=payload.get("display_name", ""),
            emails=list(payload.get("emails") or []),
            active=bool(payload.get("active", True)),
            origin=payload.get("origin", "local"),
            password_hash=payload.get("password_hash"),
            role=payload.get("role", "user"),
            group_ids=list(payload.get("group_ids") or []),
            created=payload.get("created", ""),
            last_modified=payload.get("last_modified", ""),
            last_login_at=payload.get("last_login_at"),
        )


@dataclass
class GroupRecord:
    """`beeper_groups` schema (ADR §5.1). Arbitrary IdP-pushed groups,
    stored as passthrough — the fallback pillar's two-fixed-rows design is
    deleted; "Admins/Users" is realized via `BEEPER_ADMIN_GROUPS`, not
    physical rows."""

    id: str
    external_id: str | None
    display_name: str
    display_name_lc: str
    member_ids: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> GroupRecord:
        return cls(
            id=payload.get("id", ""),
            external_id=payload.get("external_id"),
            display_name=payload.get("display_name", ""),
            display_name_lc=payload.get("display_name_lc", ""),
            member_ids=list(payload.get("member_ids") or []),
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _recompute_role(group_display_names: Iterable[str], admin_groups: Iterable[str]) -> str:
    """Derive `admin`/`user` from SCIM/OIDC group membership (ADR §3/§5.2).

    Case-insensitive membership test against `admin_groups` (already
    case-insensitive per `BEEPER_ADMIN_GROUPS`'s documented semantics).
    """
    admin_cf = {g.casefold() for g in admin_groups if g}
    for name in group_display_names:
        if name and name.casefold() in admin_cf:
            return "admin"
    return "user"


class IdentityStoreService:
    """CRUD + role resolution over the shared identity store (ADR §5)."""

    def __init__(
        self,
        qdrant_url: str | None = None,
        *,
        admin_groups: Iterable[str] | None = None,
        clock: Callable[[], float] = time.monotonic,
        cache_ttl_seconds: float = ROLE_CACHE_TTL_SECONDS,
    ) -> None:
        url = qdrant_url or os.environ.get("QDRANT_URL", "http://localhost:6333")
        self._client = QdrantClient(url=url, timeout=5.0)
        self._admin_groups: tuple[str, ...] = (
            tuple(admin_groups) if admin_groups is not None else DEFAULT_ADMIN_GROUPS
        )
        self._clock = clock
        self._cache_ttl = cache_ttl_seconds
        self._write_lock = threading.Lock()
        self._id_cache: dict[str, tuple[float, UserRecord | None]] = {}
        self._lookup_cache: dict[tuple[str, str | None], tuple[float, dict[str, Any] | None]] = {}
        self._zero_active_admins = False
        self._ensure_collections()

    # ------------------------------------------------------------------
    # Collection lifecycle
    # ------------------------------------------------------------------

    def _ensure_collections(self) -> None:
        for name in (USERS_COLLECTION, GROUPS_COLLECTION):
            try:
                self._client.get_collection(name)
            except Exception:
                try:
                    self._client.create_collection(
                        collection_name=name,
                        vectors_config=VectorParams(size=1, distance=Distance.COSINE),
                    )
                    logger.info("Created collection: %s", name)
                except Exception:
                    logger.warning(
                        "Could not create collection %s — will retry on first write", name
                    )

    # ------------------------------------------------------------------
    # In-process 60s TTL cache (ADR §2/§5.1 — "one TTL program-wide")
    # ------------------------------------------------------------------

    def _cache_get(self, cache: dict[Any, tuple[float, Any]], key: Any) -> tuple[bool, Any]:
        entry = cache.get(key)
        if entry is None:
            return False, None
        ts, value = entry
        if self._clock() - ts > self._cache_ttl:
            del cache[key]
            return False, None
        return True, value

    def _cache_put(self, cache: dict[Any, tuple[float, Any]], key: Any, value: Any) -> None:
        cache[key] = (self._clock(), value)

    def invalidate_cache(self, user_id: str | None = None) -> None:
        """Clear cached role data. `user_id=None` clears everything (used by
        tests and by `_after_mutation` — a small dataset makes whole-cache
        invalidation on write simpler and safer than partial invalidation of
        the `lookup()` cache, which is keyed by `(email_lc, external_id)`,
        not by `user_id`)."""
        if user_id is None:
            self._id_cache.clear()
            self._lookup_cache.clear()
        else:
            self._id_cache.pop(user_id, None)
            self._lookup_cache.clear()

    # ------------------------------------------------------------------
    # Raw Qdrant fetch helpers (cache-bypassing)
    # ------------------------------------------------------------------

    def _fetch_one(self, *, key: str, value: str) -> UserRecord | None:
        try:
            results, _ = self._client.scroll(
                collection_name=USERS_COLLECTION,
                scroll_filter=Filter(must=[FieldCondition(key=key, match=MatchValue(value=value))]),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
        except Exception:
            logger.exception("Failed to fetch user by %s=%r", key, value)
            return None
        if not results:
            return None
        return UserRecord.from_payload(results[0].payload or {})

    def _fetch_by_id_raw(self, user_id: str) -> UserRecord | None:
        return self._fetch_one(key="id", value=user_id)

    def _fetch_by_username_lc_raw(self, user_name_lc: str) -> UserRecord | None:
        return self._fetch_one(key="user_name_lc", value=user_name_lc)

    def _fetch_by_external_id_raw(self, external_id: str) -> UserRecord | None:
        return self._fetch_one(key="external_id", value=external_id)

    def _upsert(self, record: UserRecord) -> None:
        self._client.upsert(
            collection_name=USERS_COLLECTION,
            points=[PointStruct(id=record.id, vector=[0.0], payload=record.to_payload())],
        )

    # ------------------------------------------------------------------
    # Public reads
    # ------------------------------------------------------------------

    def get_by_id(self, user_id: str, *, use_cache: bool = True) -> UserRecord | None:
        """Local-mode per-request lookup (ADR §5.2, 60 s TTL cache)."""
        if use_cache:
            hit, cached = self._cache_get(self._id_cache, user_id)
            if hit:
                return cached
        record = self._fetch_by_id_raw(user_id)
        self._cache_put(self._id_cache, user_id, record)
        return record

    def get_by_username(self, user_name: str) -> UserRecord | None:
        """Case-insensitive lookup by `userName` (local login / SCIM `userName eq`)."""
        return self._fetch_by_username_lc_raw(user_name.strip().casefold())

    def get_by_external_id(self, external_id: str) -> UserRecord | None:
        """Lookup by SCIM `externalId` (Task 8.8: `externalId eq` filter,
        `GET /Users/{id}` after adoption, PUT/PATCH/DELETE resource
        lookup).

        ADDITIVE — Task 8.8 (SCIM surface). Task 8.3 exposed only
        `lookup()` (a `{role, active}`-shaped seam for the resolver) and
        the private `_fetch_by_external_id_raw`; the SCIM route layer
        needs a full `UserRecord` keyed by `externalId` without going
        through the resolver's cached, narrower `lookup()` shape (e.g. a
        SCIM `GET /Users/{id}` must return every SCIM attribute, and a
        `PUT`/`PATCH`/`DELETE` must resolve the full record to mutate).
        Trivial pass-through to the existing private raw-fetch helper —
        no new query shape, no cache semantics change.
        """
        return self._fetch_by_external_id_raw(external_id)

    def lookup(
        self, email_lc: str, external_id: str | None = None, *, use_cache: bool = True
    ) -> dict[str, Any] | None:
        """The pinned seam interface (ADR §5.2): `lookup(email_lc, external_id)
        -> {role, active} | None`. Matches `user_name_lc` first, `external_id`
        fallback. 60 s TTL cache — the `oidc`+SCIM per-request role source.

        Returns a plain dict (not `UserRecord`) deliberately: this is the
        exact shape ADR §5.2 pins for this seam, consumed by
        `beeper_ui.middleware.permissions.resolve_role_for_identity()` and,
        in Task 8.8, the SCIM-authoritative resolution path.
        """
        cache_key = (email_lc, external_id)
        if use_cache:
            hit, cached = self._cache_get(self._lookup_cache, cache_key)
            if hit:
                return cached
        record = self._fetch_by_username_lc_raw(email_lc) if email_lc else None
        if record is None and external_id:
            record = self._fetch_by_external_id_raw(external_id)
        result: dict[str, Any] | None = (
            {"role": record.role, "active": record.active} if record is not None else None
        )
        self._cache_put(self._lookup_cache, cache_key, result)
        return result

    def list_users(self, limit: int = 1000) -> list[UserRecord]:
        try:
            results, _ = self._client.scroll(
                collection_name=USERS_COLLECTION,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
        except Exception:
            logger.exception("Failed to list users")
            return []
        return [UserRecord.from_payload(p.payload or {}) for p in (results or [])]

    # ------------------------------------------------------------------
    # Writes — local account CRUD (Task 8.6/8.7 callers)
    # ------------------------------------------------------------------

    def create_local_user(
        self,
        *,
        user_name: str,
        password_hash: str | None = None,
        display_name: str = "",
        emails: Iterable[str] | None = None,
        role: str = "user",
        active: bool = True,
    ) -> UserRecord:
        """Create a `local`-origin user. Raises `DuplicateUserError` (409
        semantics) if `user_name_lc` already exists — uniqueness check under
        `self._write_lock` (ADR §5.1)."""
        if role not in VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(VALID_ROLES)}, got {role!r}")
        user_name_lc = user_name.strip().casefold()
        if not user_name_lc:
            raise ValueError("user_name must not be empty")
        with self._write_lock:
            if self._fetch_by_username_lc_raw(user_name_lc) is not None:
                raise DuplicateUserError(f"user_name {user_name!r} already exists")
            now = _now_iso()
            record = UserRecord(
                id=str(uuid4()),
                external_id=None,
                user_name=user_name,
                user_name_lc=user_name_lc,
                display_name=display_name or user_name,
                emails=list(emails or []),
                active=active,
                origin="local",
                password_hash=password_hash,
                role=role,
                group_ids=[],
                created=now,
                last_modified=now,
                last_login_at=None,
            )
            self._upsert(record)
        self._after_mutation(record.id)
        return record

    def update_user(
        self,
        user_id: str,
        *,
        role: str | None = None,
        active: bool | None = None,
        display_name: str | None = None,
        user_name: str | None = None,
        emails: Iterable[str] | None = None,
        group_ids: Iterable[str] | None = None,
        password_hash: str | None = None,
        guard_last_admin: bool = False,
    ) -> UserRecord:
        """Partial update (role/active/display_name/user_name/emails/
        group_ids/password_hash). Raises `UserNotFoundError` if `user_id`
        doesn't exist. By default this method never refuses on last-admin
        grounds (see `_after_mutation`'s alarm-only behavior below) — SCIM
        writes (Task 8.8) must stay alarm-only per ADR §5.3 ("a hard 409 to
        the IdP would page someone with a permanent provisioning error").

        `guard_last_admin=True` (Task 8.7's admin UI; security-review fix)
        makes this call raise `LastAdminError` INSTEAD of writing, still
        inside this method's own `self._write_lock` critical section, if
        the resulting role/active combination would leave zero active
        admins. This replaces the admin-UI route's earlier two-call
        pattern (a separate, unlocked `would_orphan_admins()` check
        followed by a separately-locked write) — that pattern had a TOCTOU
        race: two concurrent demotions of two different admins could each
        observe "not the last admin" before either write landed, together
        orphaning the store. Passing `guard_last_admin=True` closes that
        race by making the check and the write atomic relative to every
        other mutation, which all funnel through this same lock.
        `would_orphan_admins()` remains available, unchanged, as a
        non-mutating, best-effort pre-check (e.g. to proactively disable a
        UI control) — it is simply no longer the sole enforcement point.

        ADDITIVE (Task 8.8 — SCIM surface): `user_name`, `emails`, and
        `group_ids` are new keyword-only parameters, all defaulting to
        `None` (no-op) — every pre-existing call site (Task 8.3's own
        tests, Task 8.6/8.7's local-account and admin-UI callers) is
        unaffected. Needed because a SCIM `PUT /Users/{id}` is a
        full-resource replace that can rename `userName` and/or replace
        `emails`, and `group_ids` is the store's documented "read-model"
        of current group membership (ADR §5.1) that SCIM group-membership
        PATCH/PUT keeps in sync so the admin UI (Task 8.7) can render it
        later — without this, SCIM would have needed a second write path
        duplicating this method's lock/cache/alarm bookkeeping.
        `user_name` renames go through the same uniqueness check as
        `create_local_user()` (case-insensitive, excludes self), raising
        `DuplicateUserError` on collision.

        ADDITIVE (Task 8.7 — admin UI): `password_hash`, same "new
        keyword-only parameter, defaults to `None` = no-op" shape as the
        Task 8.8 additions above. Needed because `POST
        /api/v1/admin/users/<id>/reset-password`
        (`beeper_ui.routes.admin_users`) must persist a freshly-Argon2id
        -hashed password onto an EXISTING record — no pre-8.7 write
        primitive could do that (`create_local_user()` only accepts a hash
        at creation time). Passing a hash here does not change `origin`,
        `role`, or `active` — a reset is orthogonal to those fields, and
        the caller (the admin-users route) applies its own
        `409 scim-owned-user` guard before calling this for a SCIM-linked
        record while in `oidc` mode.
        """
        if role is not None and role not in VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(VALID_ROLES)}, got {role!r}")
        with self._write_lock:
            record = self._fetch_by_id_raw(user_id)
            if record is None:
                raise UserNotFoundError(user_id)
            if guard_last_admin:
                # Same predicate as `would_orphan_admins()`, but evaluated
                # HERE — inside the lock this method already holds for its
                # own write — so no other mutation can interleave between
                # this check and the `_upsert()` below. `count_active_admins`
                # is a read (no lock of its own), but every WRITE that could
                # change its answer is itself serialized on `self._write_lock`,
                # which this call already holds — that's what makes the
                # check-then-write atomic.
                currently_counted = record.role == "admin" and record.active
                resulting_role = role if role is not None else record.role
                resulting_active = active if active is not None else record.active
                still_counted = resulting_role == "admin" and resulting_active
                if (
                    currently_counted
                    and not still_counted
                    and self.count_active_admins(exclude_user_id=user_id) == 0
                ):
                    raise LastAdminError(user_id)
            if user_name is not None:
                new_lc = user_name.strip().casefold()
                if not new_lc:
                    raise ValueError("user_name must not be empty")
                if new_lc != record.user_name_lc:
                    existing = self._fetch_by_username_lc_raw(new_lc)
                    if existing is not None and existing.id != user_id:
                        raise DuplicateUserError(f"user_name {user_name!r} already exists")
                record.user_name = user_name
                record.user_name_lc = new_lc
            if role is not None:
                record.role = role
            if active is not None:
                record.active = active
            if display_name is not None:
                record.display_name = display_name
            if emails is not None:
                record.emails = list(emails)
            if group_ids is not None:
                record.group_ids = list(group_ids)
            if password_hash is not None:
                record.password_hash = password_hash
            record.last_modified = _now_iso()
            self._upsert(record)
        self._after_mutation(user_id)
        return record

    def deactivate_user(self, user_id: str) -> UserRecord:
        return self.update_user(user_id, active=False)

    def reactivate_user(self, user_id: str) -> UserRecord:
        return self.update_user(user_id, active=True)

    def set_role(self, user_id: str, role: str) -> UserRecord:
        return self.update_user(user_id, role=role)

    def record_login(self, user_id: str) -> UserRecord | None:
        """Stamp `last_login_at` (local login, Task 8.6). Not a role/active
        mutation, so it deliberately does NOT invalidate the role cache or
        run the zero-admin check — `last_login_at` doesn't affect either."""
        with self._write_lock:
            record = self._fetch_by_id_raw(user_id)
            if record is None:
                return None
            record.last_login_at = _now_iso()
            record.last_modified = _now_iso()
            self._upsert(record)
        return record

    def delete_user(self, user_id: str) -> bool:
        """Hard-delete a user record. Returns True if a record was deleted,
        False if `user_id` didn't exist (idempotent — no exception).

        ADDITIVE (Task 8.8 — SCIM surface). No pre-8.8 caller performs a
        hard delete: `local`-mode accounts use `deactivate_user()` (ADR
        §6: "no hard delete in v1" for the local-fallback pillar — history
        stays recoverable, prevents username-reuse identity confusion).
        SCIM is different: FR57/ADR §4 explicitly require `DELETE
        /Users/{id}` to be a real, hard delete (the IdP's own deprovisioning
        contract), so this is a genuinely new write primitive, not a
        relaxation of the local-mode policy above — the SCIM route layer is
        the only caller."""
        with self._write_lock:
            record = self._fetch_by_id_raw(user_id)
            if record is None:
                return False
            self._client.delete(collection_name=USERS_COLLECTION, points_selector=[user_id])
        self.invalidate_cache(user_id)
        self._check_zero_admin_alarm()
        return True

    # ------------------------------------------------------------------
    # Writes — SCIM adopt-and-link (Task 8.8 callers; ADR §5.2 HIGH-6)
    # ------------------------------------------------------------------

    def adopt_or_create_scim_user(
        self,
        *,
        user_name: str,
        external_id: str,
        display_name: str = "",
        emails: Iterable[str] | None = None,
        group_display_names: Iterable[str] = (),
        active: bool = True,
        admin_groups: Iterable[str] | None = None,
    ) -> UserRecord:
        """SCIM create/adopt path (ADR §5.2 "adopt-and-link with authoritative
        role recompute", security HIGH-6).

        If an existing record's `user_name_lc` matches, it is ADOPTED:
        `external_id` set, `origin` flips to `"scim"`, `password_hash` is
        retained inert/untouched (so flipping back to `local` mode still
        works, hash intact) — and `role` is recomputed from
        `group_display_names`, discarding any prior local role
        unconditionally. If no match exists, a fresh `scim`-origin record is
        created with the same recompute.

        `admin_groups` defaults to the instance's construction-time value
        (`DEFAULT_ADMIN_GROUPS` unless overridden) — pass it explicitly
        (e.g. `parse_group_names(current_app.config["BEEPER_ADMIN_GROUPS"])`)
        rather than relying on that default whenever `current_app` is
        available, since the singleton's default is fixed at first
        construction.

        Full SCIM `/Users` POST/PUT/PATCH semantics (both vendor
        membership-delta dialects, `externalId eq` filtering, SCIM error
        schema, etc.) belong to Task 8.8 — this is the identity-store-level
        primitive that endpoint calls into.
        """
        user_name_lc = user_name.strip().casefold()
        if not user_name_lc:
            raise ValueError("user_name must not be empty")
        groups = tuple(admin_groups) if admin_groups is not None else self._admin_groups
        role = _recompute_role(group_display_names, groups)
        with self._write_lock:
            existing = self._fetch_by_username_lc_raw(user_name_lc)
            now = _now_iso()
            if existing is not None:
                existing.external_id = external_id
                existing.origin = "scim"
                existing.role = role
                if display_name:
                    existing.display_name = display_name
                if emails is not None:
                    existing.emails = list(emails)
                existing.active = active
                existing.last_modified = now
                self._upsert(existing)
                record = existing
            else:
                record = UserRecord(
                    id=str(uuid4()),
                    external_id=external_id,
                    user_name=user_name,
                    user_name_lc=user_name_lc,
                    display_name=display_name or user_name,
                    emails=list(emails or []),
                    active=active,
                    origin="scim",
                    password_hash=None,
                    role=role,
                    group_ids=[],
                    created=now,
                    last_modified=now,
                    last_login_at=None,
                )
                self._upsert(record)
        self._after_mutation(record.id)
        return record

    # ------------------------------------------------------------------
    # Last-admin protection + zero-active-admins alarm (ADR §5.3, FR60)
    # ------------------------------------------------------------------

    def count_active_admins(self, exclude_user_id: str | None = None) -> int:
        """Count distinct active-admin users, excluding `exclude_user_id`."""
        try:
            results, _ = self._client.scroll(
                collection_name=USERS_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(key="role", match=MatchValue(value="admin")),
                        FieldCondition(key="active", match=MatchValue(value=True)),
                    ]
                ),
                limit=10_000,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as e:
            logger.exception("Failed to count active admins")
            raise IdentityStoreError("Failed to count active admins") from e
        ids = {p.payload.get("id") for p in (results or []) if p.payload}
        if exclude_user_id:
            ids.discard(exclude_user_id)
        return len(ids)

    def would_orphan_admins(
        self, user_id: str, *, new_role: str | None = None, new_active: bool | None = None
    ) -> bool:
        """Store-level last-admin guard PRIMITIVE (ADR §5.3).

        NOT enforced by this module's own writes — `update_user()` /
        `adopt_or_create_scim_user()` never refuse on this basis by
        default; per ADR §5.3, "SCIM writes are not refused... they alarm
        instead" (a hard 409 to the IdP would page someone with a
        permanent provisioning error).

        THIS METHOD IS NOT ATOMIC WITH ANY SUBSEQUENT WRITE (security
        -review finding, Task 8.7): it takes an unlocked snapshot read, so
        a caller that calls this and THEN separately calls `update_user()`
        has a TOCTOU race window between the two calls. Task 8.7's
        admin-UI mutation route does NOT use this method for its `409
        last-admin` enforcement for that reason — it calls
        `update_user(..., guard_last_admin=True)` instead, which performs
        the equivalent check atomically inside its own write-lock. This
        method remains public and useful as a cheap, non-mutating,
        best-effort PRE-check only (e.g. a caller that wants to disable a
        UI control before the user even submits, tolerating a rare
        stale-by-milliseconds answer) — never as the sole enforcement for
        a caller that needs a hard guarantee.

        Returns True iff `user_id` is CURRENTLY a counted active admin and
        the proposed `new_role`/`new_active` change would remove them from
        the count while zero OTHER active admins remain.
        """
        record = self.get_by_id(user_id, use_cache=False)
        if record is None:
            return False
        currently_counted = record.role == "admin" and record.active
        if not currently_counted:
            return False
        resulting_role = new_role if new_role is not None else record.role
        resulting_active = new_active if new_active is not None else record.active
        still_counted = resulting_role == "admin" and resulting_active
        if still_counted:
            return False
        return self.count_active_admins(exclude_user_id=user_id) == 0

    def has_zero_active_admins(self) -> bool:
        """Current alarm state, for `/health/api`'s detail flag (FR60)."""
        return self._zero_active_admins

    def refresh_zero_admin_alarm(self) -> bool:
        """PUBLIC, read-triggered variant of the zero-active-admins alarm
        check (ADR §5.3 / FR60 / FR61).

        Task 8.6 addition (flagged per the task's "minimal additive method
        allowed if genuinely needed" allowance — this is the one identity
        -store change this task makes; every other 8.6 interaction goes
        through the pre-existing public API). Every WRITE path
        (`create_local_user`, `update_user`, `adopt_or_create_scim_user`)
        already re-runs `_check_zero_admin_alarm()` via `_after_mutation()`
        — but Task 8.6's `local`-mode boot-time bootstrap
        (`beeper_ui.services.bootstrap.ensure_bootstrap_admin()`) has a
        legitimate no-write path (the seeded username already exists, or no
        seed is configured at all) that must STILL raise the same
        CRITICAL-log + `/health/api` flag when the store nonetheless has
        zero active admins (FR61: "no seed + no active admin ⇒ prominent
        startup ERROR"). This is that path's read-only trigger. Returns the
        resulting `has_zero_active_admins()` value for convenience.
        """
        self._check_zero_admin_alarm()
        return self._zero_active_admins

    def _check_zero_admin_alarm(self) -> None:
        try:
            count = self.count_active_admins()
        except IdentityStoreError:
            logger.warning("Skipping zero-active-admins check — store unavailable")
            return
        self._zero_active_admins = count == 0
        if self._zero_active_admins:
            logger.critical(
                "Zero active admins remain in the Beeper identity store — no "
                "caller can complete an admin-gated action. See ADR 0002 "
                "§5.3 / FR60. Recovery: `flask --app beeper_ui create-admin "
                "<username>` (local mode) or provision an admin-group member "
                "via the IdP/SCIM."
            )

    def _after_mutation(self, user_id: str) -> None:
        self.invalidate_cache(user_id)
        self._check_zero_admin_alarm()

    # ------------------------------------------------------------------
    # Groups (ADR §5.1 — arbitrary IdP-pushed groups, passthrough)
    # ------------------------------------------------------------------

    def upsert_group(
        self,
        *,
        external_id: str | None,
        display_name: str,
        member_ids: Iterable[str] = (),
    ) -> GroupRecord:
        display_name_lc = display_name.strip().casefold()
        with self._write_lock:
            existing = self._fetch_group_by_external_id_raw(external_id) if external_id else None
            if existing is None:
                existing = self._fetch_group_by_display_name_lc_raw(display_name_lc)
            if existing is not None:
                existing.display_name = display_name
                existing.display_name_lc = display_name_lc
                existing.member_ids = list(member_ids)
                if external_id:
                    existing.external_id = external_id
                group = existing
            else:
                group = GroupRecord(
                    id=str(uuid4()),
                    external_id=external_id,
                    display_name=display_name,
                    display_name_lc=display_name_lc,
                    member_ids=list(member_ids),
                )
            self._client.upsert(
                collection_name=GROUPS_COLLECTION,
                points=[PointStruct(id=group.id, vector=[0.0], payload=group.to_payload())],
            )
        return group

    def update_group(
        self,
        group_id: str,
        *,
        display_name: str | None = None,
        member_ids: Iterable[str] | None = None,
    ) -> GroupRecord:
        """Update a group resolved BY ITS SCIM RESOURCE ID (`id`), in place
        — never forks a second row. Raises `GroupNotFoundError` if
        `group_id` doesn't exist.

        ADDITIVE (Task 8.8 — SCIM surface). `upsert_group()` (Task 8.3)
        keys its find-or-create lookup on `external_id` first,
        `display_name_lc` second — the right primitive for an idempotent
        SCIM *push* keyed by the IdP's own identifiers, but wrong for `PUT
        /Groups/{id}` and the membership-PATCH routes: a SCIM client that
        already resolved the group by its `id` and is renaming
        `displayName` in the same request would make `upsert_group()` look
        up the *new* name, fail to find this row, and silently create a
        SECOND group instead of updating the one being edited — worse for
        a group with no `externalId` at all, which falls through to the
        display-name-only match entirely. This method resolves strictly
        by `id`, matching `update_user()`'s existing shape and its
        "resolve first, then mutate that exact row" contract.
        """
        with self._write_lock:
            record = self._fetch_group_one(key="id", value=group_id)
            if record is None:
                raise GroupNotFoundError(group_id)
            if display_name is not None:
                record.display_name = display_name
                record.display_name_lc = display_name.strip().casefold()
            if member_ids is not None:
                record.member_ids = list(member_ids)
            self._client.upsert(
                collection_name=GROUPS_COLLECTION,
                points=[PointStruct(id=record.id, vector=[0.0], payload=record.to_payload())],
            )
        return record

    def get_group_by_external_id(self, external_id: str) -> GroupRecord | None:
        return self._fetch_group_by_external_id_raw(external_id)

    def get_group_by_id(self, group_id: str) -> GroupRecord | None:
        """ADDITIVE (Task 8.8 — SCIM surface): `GET /Groups/{id}` and every
        `PUT`/`PATCH`/`DELETE /Groups/{id}` resolves the target group by
        its SCIM resource `id` (our point id), not by `externalId` or
        `displayName` — the only two lookups Task 8.3 exposed. Trivial
        pass-through, same shape as `get_by_id()` on the user side."""
        return self._fetch_group_one(key="id", value=group_id)

    def delete_group(self, group_id: str) -> bool:
        """Hard-delete a group record. Returns True if deleted, False if
        `group_id` didn't exist (idempotent).

        ADDITIVE (Task 8.8 — SCIM surface). Mirrors `delete_user()`: FR57/
        ADR §4 specify `/Groups/{id} GET/PUT/PATCH/DELETE`, and unlike
        users, groups have no pre-existing soft-deactivation concept at
        all (`beeper_groups` is pure IdP-pushed passthrough, ADR §5.1) — a
        SCIM group delete is simply a hard delete of the passthrough row.
        Deleting a group does NOT retroactively touch any member's `role`
        — SCIM clients that delete a group are expected to have already
        removed its members (RFC 7644 does not require server-side
        cascade), so no role recompute is triggered here; the route layer
        documents this as a deliberate, RFC-conforming scope limit."""
        with self._write_lock:
            record = self._fetch_group_one(key="id", value=group_id)
            if record is None:
                return False
            self._client.delete(collection_name=GROUPS_COLLECTION, points_selector=[group_id])
        return True

    def list_groups(self, limit: int = 1000) -> list[GroupRecord]:
        try:
            results, _ = self._client.scroll(
                collection_name=GROUPS_COLLECTION,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
        except Exception:
            logger.exception("Failed to list groups")
            return []
        return [GroupRecord.from_payload(p.payload or {}) for p in (results or [])]

    def _fetch_group_one(self, *, key: str, value: str) -> GroupRecord | None:
        try:
            results, _ = self._client.scroll(
                collection_name=GROUPS_COLLECTION,
                scroll_filter=Filter(must=[FieldCondition(key=key, match=MatchValue(value=value))]),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
        except Exception:
            logger.exception("Failed to fetch group by %s=%r", key, value)
            return None
        if not results:
            return None
        return GroupRecord.from_payload(results[0].payload or {})

    def _fetch_group_by_external_id_raw(self, external_id: str) -> GroupRecord | None:
        return self._fetch_group_one(key="external_id", value=external_id)

    def _fetch_group_by_display_name_lc_raw(self, display_name_lc: str) -> GroupRecord | None:
        return self._fetch_group_one(key="display_name_lc", value=display_name_lc)


# ---------------------------------------------------------------------------
# Module-level singleton (collaboration_service.py pattern)
# ---------------------------------------------------------------------------

_identity_store: IdentityStoreService | None = None


def get_identity_store(
    qdrant_url: str | None = None, *, admin_groups: Iterable[str] | None = None
) -> IdentityStoreService:
    """Get (lazily constructing on first call) the global identity store.

    Deliberately lazy, mirroring `collaboration_service.get_collaboration_service()`:
    constructing this touches Qdrant (`_ensure_collections()`), and per ADR
    §5, "Collections are created only on first `local`/`oidc` boot, so demo
    Qdrant stays clean." No code path in mode `none` calls this.
    """
    global _identity_store
    if _identity_store is None:
        _identity_store = IdentityStoreService(qdrant_url, admin_groups=admin_groups)
    return _identity_store


def get_identity_store_if_initialized() -> IdentityStoreService | None:
    """Read the singleton WITHOUT constructing it — for callers (e.g.
    `/health/api`) that must never trigger a Qdrant connection just because
    they were polled."""
    return _identity_store


def reset_identity_store() -> None:
    """Reset the global identity store singleton (for testing)."""
    global _identity_store
    _identity_store = None


def set_identity_store_for_testing(service: IdentityStoreService | None) -> None:
    """Test seam: inject a pre-built (typically fake-Qdrant-backed)
    `IdentityStoreService` as the module singleton, bypassing
    `get_identity_store()`'s lazy-construction path.

    Needed because resolver-level integration tests
    (`beeper_ui.middleware.permissions.resolve_request_identity()`, driven
    via a Flask test client) call the bare `get_identity_store()` with no
    arguments — this lets a test pre-seed the singleton with a fake client
    before issuing a request.
    """
    global _identity_store
    _identity_store = service
