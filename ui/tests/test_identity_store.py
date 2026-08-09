"""Tests for `IdentityStoreService` (Task 8.3 — ADR 0002 §5).

Uses `FakeQdrantClient` (`tests/_fake_qdrant.py`) — an in-memory double
patched in for `beeper_ui.services.identity_store.QdrantClient` — per the
repo's established "mock Qdrant" pattern (see
`tests/test_collaboration_service.py`), but implemented as a real fake
object rather than a per-call `MagicMock`, since the store issues many
distinct filter shapes (id / user_name_lc / external_id / role+active).
"""

from __future__ import annotations

import logging

import pytest

from beeper_ui.services.identity_store import (
    DEFAULT_ADMIN_GROUPS,
    DuplicateUserError,
    GroupRecord,
    IdentityStoreService,
    UserNotFoundError,
    UserRecord,
    get_identity_store,
    get_identity_store_if_initialized,
    reset_identity_store,
    set_identity_store_for_testing,
)
from tests._fake_qdrant import FakeQdrantClient


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_identity_store()
    yield
    reset_identity_store()


@pytest.fixture
def fake_client() -> FakeQdrantClient:
    return FakeQdrantClient()


class _ManualClock:
    """A controllable monotonic clock for deterministic TTL-cache tests."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def store(fake_client: FakeQdrantClient, monkeypatch: pytest.MonkeyPatch) -> IdentityStoreService:
    monkeypatch.setattr(
        "beeper_ui.services.identity_store.QdrantClient", lambda *a, **k: fake_client
    )
    return IdentityStoreService(admin_groups=("Admins", "beeper-admin"))


@pytest.fixture
def clocked_store(
    fake_client: FakeQdrantClient, monkeypatch: pytest.MonkeyPatch
) -> tuple[IdentityStoreService, _ManualClock]:
    monkeypatch.setattr(
        "beeper_ui.services.identity_store.QdrantClient", lambda *a, **k: fake_client
    )
    clock = _ManualClock()
    svc = IdentityStoreService(admin_groups=("Admins", "beeper-admin"), clock=clock)
    return svc, clock


# ---------------------------------------------------------------------------
# Collection lifecycle
# ---------------------------------------------------------------------------


class TestCollectionLifecycle:
    def test_ensure_collections_creates_both(
        self, fake_client: FakeQdrantClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "beeper_ui.services.identity_store.QdrantClient", lambda *a, **k: fake_client
        )
        IdentityStoreService()
        assert "beeper_users" in fake_client.collections
        assert "beeper_groups" in fake_client.collections

    def test_ensure_collections_idempotent_on_existing(
        self, fake_client: FakeQdrantClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "beeper_ui.services.identity_store.QdrantClient", lambda *a, **k: fake_client
        )
        IdentityStoreService()
        # Second construction against the same (already-created) fake
        # client must not raise.
        IdentityStoreService()
        assert "beeper_users" in fake_client.collections


# ---------------------------------------------------------------------------
# UserRecord payload round-trip
# ---------------------------------------------------------------------------


class TestUserRecordPayload:
    def test_roundtrip(self) -> None:
        record = UserRecord(
            id="u1",
            external_id="ext-1",
            user_name="Alice@Corp.com",
            user_name_lc="alice@corp.com",
            display_name="Alice",
            emails=["alice@corp.com"],
            active=True,
            origin="local",
            password_hash="hash",
            role="admin",
            group_ids=["g1"],
            created="2026-01-01T00:00:00+00:00",
            last_modified="2026-01-01T00:00:00+00:00",
            last_login_at=None,
        )
        restored = UserRecord.from_payload(record.to_payload())
        assert restored == record

    def test_from_payload_missing_fields_defaults(self) -> None:
        record = UserRecord.from_payload({})
        assert record.id == ""
        assert record.role == "user"
        assert record.active is True
        assert record.origin == "local"
        assert record.emails == []


class TestGroupRecordPayload:
    def test_roundtrip(self) -> None:
        group = GroupRecord(
            id="g1",
            external_id="ext-g1",
            display_name="Admins",
            display_name_lc="admins",
            member_ids=["u1", "u2"],
        )
        restored = GroupRecord.from_payload(group.to_payload())
        assert restored == group


# ---------------------------------------------------------------------------
# [T] CRUD
# ---------------------------------------------------------------------------


class TestCreateLocalUser:
    def test_create_success(self, store: IdentityStoreService) -> None:
        record = store.create_local_user(
            user_name="alice@corp.com",
            password_hash="hash",
            display_name="Alice",
            role="user",
        )
        assert record.user_name_lc == "alice@corp.com"
        assert record.origin == "local"
        assert record.role == "user"
        assert record.active is True
        fetched = store.get_by_id(record.id, use_cache=False)
        assert fetched is not None
        assert fetched.user_name == "alice@corp.com"

    def test_duplicate_user_name_raises_409_semantics(self, store: IdentityStoreService) -> None:
        store.create_local_user(user_name="alice@corp.com", role="user")
        with pytest.raises(DuplicateUserError):
            store.create_local_user(user_name="alice@corp.com", role="user")

    def test_duplicate_check_is_case_insensitive(self, store: IdentityStoreService) -> None:
        """Canonical key is casefolded — ADR §5.1."""
        store.create_local_user(user_name="Alice@Corp.com", role="user")
        with pytest.raises(DuplicateUserError):
            store.create_local_user(user_name="ALICE@CORP.COM", role="user")

    def test_empty_user_name_raises_value_error(self, store: IdentityStoreService) -> None:
        with pytest.raises(ValueError, match="user_name"):
            store.create_local_user(user_name="   ", role="user")

    def test_invalid_role_raises_value_error(self, store: IdentityStoreService) -> None:
        with pytest.raises(ValueError, match="role"):
            store.create_local_user(user_name="bob@corp.com", role="superadmin")

    def test_display_name_defaults_to_user_name(self, store: IdentityStoreService) -> None:
        record = store.create_local_user(user_name="carol@corp.com", role="user")
        assert record.display_name == "carol@corp.com"


class TestGetByUsername:
    def test_case_insensitive_lookup(self, store: IdentityStoreService) -> None:
        store.create_local_user(user_name="Dave@Corp.com", role="user")
        found = store.get_by_username("DAVE@corp.COM")
        assert found is not None
        assert found.user_name == "Dave@Corp.com"

    def test_unknown_username_returns_none(self, store: IdentityStoreService) -> None:
        assert store.get_by_username("nobody@corp.com") is None


class TestUpdateUser:
    def test_update_role_and_active(self, store: IdentityStoreService) -> None:
        record = store.create_local_user(user_name="erin@corp.com", role="user")
        updated = store.update_user(record.id, role="admin", active=False)
        assert updated.role == "admin"
        assert updated.active is False

    def test_update_missing_user_raises(self, store: IdentityStoreService) -> None:
        with pytest.raises(UserNotFoundError):
            store.update_user("does-not-exist", role="admin")

    def test_update_invalid_role_raises(self, store: IdentityStoreService) -> None:
        record = store.create_local_user(user_name="frank@corp.com", role="user")
        with pytest.raises(ValueError, match="role"):
            store.update_user(record.id, role="superadmin")

    def test_deactivate_and_reactivate(self, store: IdentityStoreService) -> None:
        record = store.create_local_user(user_name="gail@corp.com", role="user")
        deactivated = store.deactivate_user(record.id)
        assert deactivated.active is False
        reactivated = store.reactivate_user(record.id)
        assert reactivated.active is True

    def test_set_role(self, store: IdentityStoreService) -> None:
        record = store.create_local_user(user_name="hank@corp.com", role="user")
        promoted = store.set_role(record.id, "admin")
        assert promoted.role == "admin"

    def test_record_login_stamps_last_login_at(self, store: IdentityStoreService) -> None:
        record = store.create_local_user(user_name="ivy@corp.com", role="user")
        assert record.last_login_at is None
        updated = store.record_login(record.id)
        assert updated is not None
        assert updated.last_login_at is not None

    def test_record_login_missing_user_returns_none(self, store: IdentityStoreService) -> None:
        assert store.record_login("nonexistent") is None


class TestListUsers:
    def test_list_users_returns_all(self, store: IdentityStoreService) -> None:
        store.create_local_user(user_name="a@corp.com", role="user")
        store.create_local_user(user_name="b@corp.com", role="admin")
        users = store.list_users()
        assert {u.user_name_lc for u in users} == {"a@corp.com", "b@corp.com"}


# ---------------------------------------------------------------------------
# [T] 60s TTL cache semantics
# ---------------------------------------------------------------------------


class TestGetByIdCache:
    def test_cache_hit_within_ttl_avoids_refetch(
        self, clocked_store: tuple[IdentityStoreService, _ManualClock]
    ) -> None:
        store, clock = clocked_store
        record = store.create_local_user(user_name="jill@corp.com", role="user")
        store.get_by_id(record.id)  # warms cache

        # Mutate the underlying Qdrant payload directly, bypassing the
        # service (simulates an external write racing the cache) — a
        # cache hit must NOT observe it.
        store._client.collections["beeper_users"][record.id]["role"] = "admin"

        clock.advance(30)  # still within the 60s TTL
        cached = store.get_by_id(record.id)
        assert cached is not None
        assert cached.role == "user"  # stale cached value, as expected

    def test_cache_expires_after_ttl(
        self, clocked_store: tuple[IdentityStoreService, _ManualClock]
    ) -> None:
        store, clock = clocked_store
        record = store.create_local_user(user_name="ken@corp.com", role="user")
        store.get_by_id(record.id)  # warms cache

        store._client.collections["beeper_users"][record.id]["role"] = "admin"

        clock.advance(61)  # past the 60s TTL
        refreshed = store.get_by_id(record.id)
        assert refreshed is not None
        assert refreshed.role == "admin"

    def test_use_cache_false_always_bypasses(
        self, clocked_store: tuple[IdentityStoreService, _ManualClock]
    ) -> None:
        store, _clock = clocked_store
        record = store.create_local_user(user_name="lily@corp.com", role="user")
        store.get_by_id(record.id)  # warms cache

        store._client.collections["beeper_users"][record.id]["role"] = "admin"

        fresh = store.get_by_id(record.id, use_cache=False)
        assert fresh is not None
        assert fresh.role == "admin"

    def test_mutation_invalidates_cache_for_that_id(
        self, clocked_store: tuple[IdentityStoreService, _ManualClock]
    ) -> None:
        store, clock = clocked_store
        record = store.create_local_user(user_name="mona@corp.com", role="user")
        store.get_by_id(record.id)  # warms cache

        store.set_role(record.id, "admin")  # mutation should invalidate

        clock.advance(1)  # well within TTL — proves invalidation, not expiry
        refreshed = store.get_by_id(record.id)
        assert refreshed is not None
        assert refreshed.role == "admin"

    def test_missing_user_returns_none_and_caches_the_miss(
        self, clocked_store: tuple[IdentityStoreService, _ManualClock]
    ) -> None:
        store, _clock = clocked_store
        assert store.get_by_id("ghost") is None
        assert store.get_by_id("ghost") is None  # cached miss, no crash


class TestLookupSeam:
    """The pinned `lookup(email_lc, external_id) -> {role, active} | None`
    seam (ADR §5.2)."""

    def test_matches_user_name_lc_first(self, store: IdentityStoreService) -> None:
        store.create_local_user(user_name="nina@corp.com", role="admin", active=True)
        result = store.lookup("nina@corp.com", external_id=None)
        assert result == {"role": "admin", "active": True}

    def test_falls_back_to_external_id(self, store: IdentityStoreService) -> None:
        store.adopt_or_create_scim_user(
            user_name="oscar@corp.com",
            external_id="scim-ext-42",
            group_display_names=["Admins"],
        )
        # email_lc deliberately doesn't match (simulates an email change
        # upstream at the IdP that hasn't propagated to `user_name_lc` yet)
        # — externalId fallback still resolves it.
        result = store.lookup("stale-email@corp.com", external_id="scim-ext-42")
        assert result == {"role": "admin", "active": True}

    def test_returns_none_when_neither_matches(self, store: IdentityStoreService) -> None:
        assert store.lookup("nobody@corp.com", external_id="nope") is None

    def test_cache_hit_within_ttl(
        self, clocked_store: tuple[IdentityStoreService, _ManualClock]
    ) -> None:
        store, clock = clocked_store
        store.create_local_user(user_name="pete@corp.com", role="user", active=True)
        store.lookup("pete@corp.com", None)  # warm cache

        record = store.get_by_username("pete@corp.com")
        assert record is not None
        store._client.collections["beeper_users"][record.id]["active"] = False

        clock.advance(30)
        cached = store.lookup("pete@corp.com", None)
        assert cached == {"role": "user", "active": True}  # stale, as expected

    def test_cache_expires_after_ttl(
        self, clocked_store: tuple[IdentityStoreService, _ManualClock]
    ) -> None:
        store, clock = clocked_store
        store.create_local_user(user_name="quinn@corp.com", role="user", active=True)
        store.lookup("quinn@corp.com", None)

        record = store.get_by_username("quinn@corp.com")
        assert record is not None
        store._client.collections["beeper_users"][record.id]["active"] = False

        clock.advance(61)
        refreshed = store.lookup("quinn@corp.com", None)
        assert refreshed == {"role": "user", "active": False}


# ---------------------------------------------------------------------------
# [T] Adopt-and-link with authoritative role recompute (ADR §5.2 HIGH-6)
# ---------------------------------------------------------------------------


class TestAdoptAndLinkRoleRecompute:
    def test_named_scenario_local_admin_demoted_by_scim_non_admin_group(
        self, store: IdentityStoreService
    ) -> None:
        """Required AC test (ADR §5.2): local-admin alice@corp.com + SCIM
        push placing alice only in a non-admin group ⇒ resolves to `user`."""
        local_admin = store.create_local_user(
            user_name="alice@corp.com",
            password_hash="$argon2id$fake-hash-stays-intact",
            role="admin",
            active=True,
        )
        assert local_admin.role == "admin"
        assert local_admin.origin == "local"

        adopted = store.adopt_or_create_scim_user(
            user_name="alice@corp.com",
            external_id="scim-ext-alice",
            group_display_names=["Everyone"],  # NOT an admin group
        )

        assert adopted.id == local_admin.id  # same record, adopted not duplicated
        assert adopted.role == "user"  # discarded prior local "admin" role
        assert adopted.origin == "scim"
        assert adopted.external_id == "scim-ext-alice"
        assert adopted.password_hash == "$argon2id$fake-hash-stays-intact"  # hash intact

    def test_adopt_promotes_when_group_is_admin_group(self, store: IdentityStoreService) -> None:
        store.create_local_user(user_name="bob@corp.com", role="user")
        adopted = store.adopt_or_create_scim_user(
            user_name="bob@corp.com",
            external_id="scim-ext-bob",
            group_display_names=["Admins"],
        )
        assert adopted.role == "admin"

    def test_admin_group_match_is_case_insensitive(self, store: IdentityStoreService) -> None:
        record = store.adopt_or_create_scim_user(
            user_name="cara@corp.com",
            external_id="scim-ext-cara",
            group_display_names=["ADMINS"],
            admin_groups=("Admins", "beeper-admin"),
        )
        assert record.role == "admin"

    def test_create_fresh_scim_user_when_no_local_match(
        self, store: IdentityStoreService
    ) -> None:
        record = store.adopt_or_create_scim_user(
            user_name="dana@corp.com",
            external_id="scim-ext-dana",
            display_name="Dana",
            emails=["dana@corp.com"],
            group_display_names=["Everyone"],
        )
        assert record.origin == "scim"
        assert record.role == "user"
        assert record.password_hash is None
        assert store.get_by_username("dana@corp.com") is not None

    def test_default_admin_groups_used_when_not_overridden(self) -> None:
        assert DEFAULT_ADMIN_GROUPS == ("Admins", "beeper-admin")

    def test_flipping_back_to_local_mode_restores_local_login(
        self, store: IdentityStoreService
    ) -> None:
        """§5.2: 'Flipping back to `local` mode restores local login (hash
        intact) and admin-UI write access.' The store doesn't know about
        mode itself — this proves the DATA survives adoption so `local`
        mode's login path (Task 8.6) can still find the hash."""
        store.create_local_user(
            user_name="erin@corp.com", password_hash="original-hash", role="admin"
        )
        store.adopt_or_create_scim_user(
            user_name="erin@corp.com",
            external_id="scim-ext-erin",
            group_display_names=[],
        )
        record = store.get_by_username("erin@corp.com")
        assert record is not None
        assert record.password_hash == "original-hash"


# ---------------------------------------------------------------------------
# [T] Zero-active-admins alarm + last-admin protection primitive (FR60)
# ---------------------------------------------------------------------------


class TestZeroActiveAdminsAlarm:
    def test_no_admins_ever_created_leaves_flag_false_until_a_write_happens(
        self, store: IdentityStoreService
    ) -> None:
        # No mutation has happened yet — the alarm only evaluates on write.
        assert store.has_zero_active_admins() is False

    def test_creating_only_non_admin_users_raises_alarm_after_first_write(
        self, store: IdentityStoreService
    ) -> None:
        store.create_local_user(user_name="frank@corp.com", role="user")
        assert store.has_zero_active_admins() is True

    def test_creating_an_admin_clears_the_alarm(self, store: IdentityStoreService) -> None:
        store.create_local_user(user_name="gail@corp.com", role="user")
        assert store.has_zero_active_admins() is True
        store.create_local_user(user_name="hank@corp.com", role="admin")
        assert store.has_zero_active_admins() is False

    def test_demoting_the_last_admin_raises_alarm(self, store: IdentityStoreService) -> None:
        admin = store.create_local_user(user_name="ivy@corp.com", role="admin")
        assert store.has_zero_active_admins() is False
        store.set_role(admin.id, "user")
        assert store.has_zero_active_admins() is True

    def test_deactivating_the_last_admin_raises_alarm(self, store: IdentityStoreService) -> None:
        admin = store.create_local_user(user_name="jack@corp.com", role="admin")
        store.deactivate_user(admin.id)
        assert store.has_zero_active_admins() is True

    def test_scim_write_leaving_zero_admins_alarms_but_does_not_raise(
        self, store: IdentityStoreService
    ) -> None:
        """§5.3: 'SCIM writes are not refused... they alarm instead.'"""
        admin = store.create_local_user(user_name="kate@corp.com", role="admin")
        # SCIM adoption discards the local admin role via a non-admin group.
        adopted = store.adopt_or_create_scim_user(
            user_name="kate@corp.com",
            external_id="scim-ext-kate",
            group_display_names=["Everyone"],
        )
        assert adopted.id == admin.id
        assert adopted.role == "user"
        assert store.has_zero_active_admins() is True  # alarmed
        # No exception was raised getting here — SCIM writes are never
        # refused by the store itself.

    def test_critical_log_emitted_on_zero_admin_transition(
        self, store: IdentityStoreService, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.CRITICAL):
            store.create_local_user(user_name="leo@corp.com", role="user")
        assert any(
            record.levelno == logging.CRITICAL and "Zero active admins" in record.message
            for record in caplog.records
        )

    def test_multiple_active_admins_keep_flag_false(self, store: IdentityStoreService) -> None:
        store.create_local_user(user_name="mia@corp.com", role="admin")
        second = store.create_local_user(user_name="nate@corp.com", role="admin")
        store.set_role(second.id, "user")  # still one admin left
        assert store.has_zero_active_admins() is False


class TestLastAdminGuardPrimitive:
    """Store-level guard PRIMITIVE for Task 8.7's admin-UI `409 last-admin`
    refusal — NOT enforced by the store's own writes (see
    `TestZeroActiveAdminsAlarm` above: those alarm, never refuse)."""

    def test_would_orphan_admins_true_for_sole_active_admin_demotion(
        self, store: IdentityStoreService
    ) -> None:
        admin = store.create_local_user(user_name="omar@corp.com", role="admin")
        assert store.would_orphan_admins(admin.id, new_role="user") is True

    def test_would_orphan_admins_true_for_sole_active_admin_deactivation(
        self, store: IdentityStoreService
    ) -> None:
        admin = store.create_local_user(user_name="paula@corp.com", role="admin")
        assert store.would_orphan_admins(admin.id, new_active=False) is True

    def test_would_orphan_admins_false_when_another_admin_remains(
        self, store: IdentityStoreService
    ) -> None:
        first = store.create_local_user(user_name="quentin@corp.com", role="admin")
        store.create_local_user(user_name="rosa@corp.com", role="admin")
        assert store.would_orphan_admins(first.id, new_role="user") is False

    def test_would_orphan_admins_false_for_non_admin_user(
        self, store: IdentityStoreService
    ) -> None:
        user = store.create_local_user(user_name="sam@corp.com", role="user")
        assert store.would_orphan_admins(user.id, new_active=False) is False

    def test_would_orphan_admins_false_for_unknown_user(
        self, store: IdentityStoreService
    ) -> None:
        assert store.would_orphan_admins("ghost", new_role="user") is False

    def test_would_orphan_admins_false_when_role_unchanged(
        self, store: IdentityStoreService
    ) -> None:
        admin = store.create_local_user(user_name="tara@corp.com", role="admin")
        assert store.would_orphan_admins(admin.id, new_active=True) is False

    def test_store_writes_never_refuse_even_when_would_orphan(
        self, store: IdentityStoreService
    ) -> None:
        """Confirms the guard is advisory-only at the store layer — 8.7 must
        call `would_orphan_admins()` itself before mutating."""
        admin = store.create_local_user(user_name="uma@corp.com", role="admin")
        # No exception — update_user() doesn't consult the guard itself.
        result = store.set_role(admin.id, "user")
        assert result.role == "user"


# ---------------------------------------------------------------------------
# Groups (ADR §5.1 — arbitrary IdP-pushed groups, passthrough)
# ---------------------------------------------------------------------------


class TestGroups:
    def test_upsert_group_creates(self, store: IdentityStoreService) -> None:
        group = store.upsert_group(
            external_id="grp-1", display_name="Everyone", member_ids=["u1"]
        )
        assert group.display_name_lc == "everyone"
        fetched = store.get_group_by_external_id("grp-1")
        assert fetched is not None
        assert fetched.member_ids == ["u1"]

    def test_upsert_group_updates_existing_by_external_id(
        self, store: IdentityStoreService
    ) -> None:
        first = store.upsert_group(external_id="grp-2", display_name="Team A")
        updated = store.upsert_group(
            external_id="grp-2", display_name="Team A Renamed", member_ids=["u9"]
        )
        assert updated.id == first.id
        assert updated.display_name == "Team A Renamed"
        assert updated.member_ids == ["u9"]

    def test_list_groups(self, store: IdentityStoreService) -> None:
        store.upsert_group(external_id="g1", display_name="A")
        store.upsert_group(external_id="g2", display_name="B")
        groups = store.list_groups()
        assert {g.display_name for g in groups} == {"A", "B"}

    def test_arbitrary_group_count_is_unbounded(self, store: IdentityStoreService) -> None:
        """§5.1: 'Arbitrary IdP-pushed groups are stored (passthrough — push
        two groups or fifty)' — no fixed-rows assumption."""
        for i in range(50):
            store.upsert_group(external_id=f"grp-{i}", display_name=f"Group {i}")
        assert len(store.list_groups(limit=100)) == 50


# ---------------------------------------------------------------------------
# Module singleton (collaboration_service.py pattern)
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_identity_store_lazily_constructs_once(
        self, fake_client: FakeQdrantClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "beeper_ui.services.identity_store.QdrantClient", lambda *a, **k: fake_client
        )
        assert get_identity_store_if_initialized() is None
        first = get_identity_store()
        second = get_identity_store()
        assert first is second

    def test_reset_identity_store_clears_singleton(
        self, fake_client: FakeQdrantClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "beeper_ui.services.identity_store.QdrantClient", lambda *a, **k: fake_client
        )
        get_identity_store()
        reset_identity_store()
        assert get_identity_store_if_initialized() is None

    def test_set_identity_store_for_testing_injects_instance(
        self, store: IdentityStoreService
    ) -> None:
        set_identity_store_for_testing(store)
        assert get_identity_store() is store
        assert get_identity_store_if_initialized() is store
