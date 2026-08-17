"""Tests for `beeper_ui.services.bootstrap.ensure_bootstrap_admin` (Task
8.6 — ADR 0002 §6, FR61).

AC [T] linkage (docs/plans/react-ui.md Task 8.6):
  - bootstrap idempotent, never overwrites a rotated password (restart
    -with-same-secret test) -> TestIdempotency
  - no-seed-no-admin => startup ERROR + health flag, not crash
    -> TestZeroAdminAlarm
  - mode `none` boots with zero config -> TestModeNoneUntouched
"""

from __future__ import annotations

import logging

import pytest
from flask import Flask

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig
from beeper_ui.services.bootstrap import PASSWORD_ENV, USERNAME_ENV, ensure_bootstrap_admin
from beeper_ui.services.identity_store import (
    IdentityStoreService,
    get_identity_store_if_initialized,
    reset_identity_store,
    set_identity_store_for_testing,
)
from beeper_ui.services.password_hashing import verify_password
from tests._fake_qdrant import FakeQdrantClient


@pytest.fixture(autouse=True)
def _secret_key_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-real-secret-for-bootstrap-tests")
    yield


@pytest.fixture(autouse=True)
def _reset_store():
    reset_identity_store()
    yield
    reset_identity_store()


@pytest.fixture(autouse=True)
def _clear_bootstrap_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(USERNAME_ENV, raising=False)
    monkeypatch.delenv(PASSWORD_ENV, raising=False)


class _LocalConfig(TestingConfig):
    BEEPER_AUTH_MODE = "local"


@pytest.fixture
def fake_client() -> FakeQdrantClient:
    return FakeQdrantClient()


@pytest.fixture
def seeded_store(
    fake_client: FakeQdrantClient, monkeypatch: pytest.MonkeyPatch
) -> IdentityStoreService:
    monkeypatch.setattr(
        "beeper_ui.services.identity_store.QdrantClient", lambda *a, **k: fake_client
    )
    store = IdentityStoreService(admin_groups=("Admins", "beeper-admin"))
    set_identity_store_for_testing(store)
    return store


def _make_app(config_class: type = _LocalConfig) -> Flask:
    return create_app(config_class)


# ---------------------------------------------------------------------------
# [T] idempotency — seed creates once, never overwrites a rotated password
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_seeds_admin_from_env(
        self, seeded_store: IdentityStoreService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(USERNAME_ENV, "root")
        monkeypatch.setenv(PASSWORD_ENV, "bootstrap-password-1")
        app = _make_app()
        ensure_bootstrap_admin(app)

        record = seeded_store.get_by_username("root")
        assert record is not None
        assert record.role == "admin"
        assert record.active is True
        assert record.password_hash is not None
        assert verify_password(record.password_hash, "bootstrap-password-1") is True

    def test_restart_with_changed_env_password_does_not_overwrite(
        self,
        seeded_store: IdentityStoreService,
        fake_client: FakeQdrantClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """FR61: 'a rotated password is never reverted by a restart.'"""
        monkeypatch.setenv(USERNAME_ENV, "root")
        monkeypatch.setenv(PASSWORD_ENV, "original-bootstrap-password")
        app = _make_app()
        ensure_bootstrap_admin(app)  # "first boot" — creates the user

        record = seeded_store.get_by_username("root")
        assert record is not None
        # Simulate an admin rotating the password by hand, out of band —
        # write straight into the fake Qdrant payload (below the store's
        # own API, which has no "set an arbitrary password_hash" method by
        # design — only `create_local_user`/admin-reset would do this for
        # real, out of this test's scope).
        fake_client.collections["beeper_users"][record.id]["password_hash"] = (
            "rotated-hash-value"
        )
        seeded_store.invalidate_cache()

        # "Restart" — the env var STILL has the ORIGINAL password. Must NOT
        # revert the rotated hash.
        ensure_bootstrap_admin(app)

        after_restart = seeded_store.get_by_username("root")
        assert after_restart is not None
        assert after_restart.password_hash == "rotated-hash-value"

    def test_seed_does_not_run_twice_even_with_same_password(
        self, seeded_store: IdentityStoreService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(USERNAME_ENV, "root")
        monkeypatch.setenv(PASSWORD_ENV, "same-password-both-times")
        app = _make_app()
        ensure_bootstrap_admin(app)
        first = seeded_store.get_by_username("root")
        assert first is not None

        ensure_bootstrap_admin(app)
        second = seeded_store.get_by_username("root")
        assert second is not None
        # Same record (never recreated), same hash (re-hashing the same
        # password twice would still produce a DIFFERENT digest since
        # Argon2id salts randomly — proving no second create/update ran).
        assert second.id == first.id
        assert second.password_hash == first.password_hash

    def test_only_username_set_refuses_and_creates_nothing(
        self, seeded_store: IdentityStoreService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(USERNAME_ENV, "root")
        app = _make_app()
        ensure_bootstrap_admin(app)
        assert seeded_store.get_by_username("root") is None

    def test_only_password_set_refuses_and_creates_nothing(
        self, seeded_store: IdentityStoreService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(PASSWORD_ENV, "orphan-password-123")
        app = _make_app()
        ensure_bootstrap_admin(app)
        assert seeded_store.list_users() == []

    def test_password_below_minimum_length_refused(
        self, seeded_store: IdentityStoreService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(USERNAME_ENV, "root")
        monkeypatch.setenv(PASSWORD_ENV, "short")
        app = _make_app()
        ensure_bootstrap_admin(app)
        assert seeded_store.get_by_username("root") is None

    def test_neither_env_set_creates_nothing_but_does_not_raise(
        self, seeded_store: IdentityStoreService
    ) -> None:
        app = _make_app()
        ensure_bootstrap_admin(app)  # must not raise
        assert seeded_store.list_users() == []


# ---------------------------------------------------------------------------
# [T] zero-admin alarm — no-seed-no-admin => ERROR + health flag, not a crash
# ---------------------------------------------------------------------------


class TestZeroAdminAlarm:
    def test_no_seed_configured_and_zero_admins_sets_health_flag(
        self, seeded_store: IdentityStoreService
    ) -> None:
        app = _make_app()
        ensure_bootstrap_admin(app)  # no env configured at all
        assert seeded_store.has_zero_active_admins() is True

    def test_no_seed_configured_and_zero_admins_logs_error_not_crash(
        self, seeded_store: IdentityStoreService, caplog: pytest.LogCaptureFixture
    ) -> None:
        app = _make_app()
        with caplog.at_level(logging.ERROR):
            ensure_bootstrap_admin(app)  # must not raise
        assert any(
            record.levelno >= logging.ERROR and "ZERO active admins" in record.message
            for record in caplog.records
        )

    def test_seed_creates_an_active_admin_so_alarm_stays_clear(
        self, seeded_store: IdentityStoreService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(USERNAME_ENV, "root")
        monkeypatch.setenv(PASSWORD_ENV, "a-fine-bootstrap-password")
        app = _make_app()
        ensure_bootstrap_admin(app)
        assert seeded_store.has_zero_active_admins() is False

    def test_health_api_surfaces_the_flag(
        self, seeded_store: IdentityStoreService
    ) -> None:
        app = _make_app()
        ensure_bootstrap_admin(app)
        with app.test_client() as client:
            body = client.get("/health/api").get_json()
            assert body["zero_active_admins"] is True

    def test_qdrant_unavailable_at_boot_does_not_crash_create_app(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No `seeded_store` fixture here — a REAL (unreachable)
        `QdrantClient` is constructed. `create_app()` must still succeed
        (FR61: "not a crash")."""
        monkeypatch.setenv(USERNAME_ENV, "root")
        monkeypatch.setenv(PASSWORD_ENV, "a-fine-bootstrap-password")
        app = _make_app()  # calls ensure_bootstrap_admin() internally
        assert app is not None
        assert get_identity_store_if_initialized() is not None


# ---------------------------------------------------------------------------
# [T] mode `none` requires zero bootstrap configuration
# ---------------------------------------------------------------------------


class TestModeNoneUntouched:
    def test_mode_none_never_constructs_the_identity_store_even_with_env_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(USERNAME_ENV, "root")
        monkeypatch.setenv(PASSWORD_ENV, "irrelevant-in-mode-none")
        create_app(TestingConfig)  # mode "none" — bootstrap must never run
        assert get_identity_store_if_initialized() is None

    def test_mode_none_boots_with_zero_bootstrap_env_set(self) -> None:
        app = create_app(TestingConfig)
        assert app is not None
        assert get_identity_store_if_initialized() is None
