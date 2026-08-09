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


def _recompute_role(
    group_display_names: Iterable[str], admin_groups: Iterable[str]
) -> str:
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
        self._lookup_cache: dict[
            tuple[str, str | None], tuple[float, dict[str, Any] | None]
        ] = {}
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
    ) -> UserRecord:
        """Partial update (role/active/display_name). Raises
        `UserNotFoundError` if `user_id` doesn't exist. Callers that must
        refuse a last-admin-orphaning write (Task 8.7's admin UI, per ADR
        §5.3's `409 last-admin`) should check `would_orphan_admins()`
        BEFORE calling this — this method itself never refuses (see
        `_after_mutation`'s alarm-only behavior below)."""
        if role is not None and role not in VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(VALID_ROLES)}, got {role!r}")
        with self._write_lock:
            record = self._fetch_by_id_raw(user_id)
            if record is None:
                raise UserNotFoundError(user_id)
            if role is not None:
                record.role = role
            if active is not None:
                record.active = active
            if display_name is not None:
                record.display_name = display_name
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
        """Store-level last-admin guard PRIMITIVE (ADR §5.3) for Task 8.7's
        admin UI to use for its `409 last-admin` refusal.

        NOT enforced by this module's own writes — `update_user()` /
        `adopt_or_create_scim_user()` never refuse on this basis; per ADR
        §5.3, "SCIM writes are not refused... they alarm instead" (a hard
        409 to the IdP would page someone with a permanent provisioning
        error). 8.7's admin-UI mutation routes are expected to call this
        BEFORE calling `update_user()`/`deactivate_user()` and return `409
        last-admin` themselves when it returns True.

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
            existing = (
                self._fetch_group_by_external_id_raw(external_id) if external_id else None
            )
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

    def get_group_by_external_id(self, external_id: str) -> GroupRecord | None:
        return self._fetch_group_by_external_id_raw(external_id)

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
