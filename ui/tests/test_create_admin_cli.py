"""Tests for `flask create-admin` (Task 8.6 — ADR 0002 §6, FR61 recovery
path).

AC [T]: "create-admin CLI works non-interactively."

Deliberately builds the Flask app INLINE per test (`_make_app()`) rather
than via a pytest fixture named `app`: a fixture chain of
`app -> seeded_store` requested alongside a directly-requested
`seeded_store` parameter was observed to let the autouse `_reset_store`
fixture's setup run AFTER `seeded_store`'s setup in this pytest version —
silently swapping the module singleton out from under the test right
before the test body executes. Every other file in this suite
(`test_local_auth_routes.py`, `test_bootstrap.py`, `test_auth_me.py`)
sidesteps this by calling a plain `_make_app()` helper function inside the
test body instead of depending on an `app` fixture; this file follows the
same convention for the same reason.
"""

from __future__ import annotations

import pytest
from flask import Flask

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig
from beeper_ui.services.identity_store import (
    IdentityStoreService,
    reset_identity_store,
    set_identity_store_for_testing,
)
from beeper_ui.services.password_hashing import hash_password, verify_password
from tests._fake_qdrant import FakeQdrantClient


@pytest.fixture(autouse=True)
def _secret_key_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-real-secret-for-cli-tests")
    yield


@pytest.fixture(autouse=True)
def _clear_bootstrap_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("BEEPER_BOOTSTRAP_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("BEEPER_BOOTSTRAP_ADMIN_PASSWORD", raising=False)


@pytest.fixture(autouse=True)
def _reset_store():
    reset_identity_store()
    yield
    reset_identity_store()


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


def _make_app() -> Flask:
    # Mode "none" — `flask create-admin` is registered unconditionally
    # regardless of `BEEPER_AUTH_MODE` (see `beeper_ui.cli`'s docstring).
    return create_app(TestingConfig)


class TestCreateAdminCliNonInteractive:
    def test_password_flag_creates_active_admin(
        self, seeded_store: IdentityStoreService
    ) -> None:
        runner = _make_app().test_cli_runner()
        result = runner.invoke(
            args=["create-admin", "alice", "--password", "a-strong-password-1"]
        )
        assert result.exit_code == 0, result.output
        record = seeded_store.get_by_username("alice")
        assert record is not None
        assert record.role == "admin"
        assert record.active is True
        assert record.password_hash is not None
        assert verify_password(record.password_hash, "a-strong-password-1") is True

    def test_password_stdin_creates_active_admin(
        self, seeded_store: IdentityStoreService
    ) -> None:
        runner = _make_app().test_cli_runner()
        result = runner.invoke(
            args=["create-admin", "bob", "--password-stdin"],
            input="a-different-strong-password\n",
        )
        assert result.exit_code == 0, result.output
        record = seeded_store.get_by_username("bob")
        assert record is not None
        assert verify_password(record.password_hash or "", "a-different-strong-password") is True

    def test_password_below_minimum_rejected(
        self, seeded_store: IdentityStoreService
    ) -> None:
        runner = _make_app().test_cli_runner()
        result = runner.invoke(args=["create-admin", "carl", "--password", "short"])
        assert result.exit_code != 0
        assert seeded_store.get_by_username("carl") is None

    def test_display_name_flag(self, seeded_store: IdentityStoreService) -> None:
        runner = _make_app().test_cli_runner()
        result = runner.invoke(
            args=[
                "create-admin",
                "dana",
                "--password",
                "a-strong-password-2",
                "--display-name",
                "Dana Delta",
            ]
        )
        assert result.exit_code == 0, result.output
        record = seeded_store.get_by_username("dana")
        assert record is not None
        assert record.display_name == "Dana Delta"

    def test_existing_deactivated_user_is_promoted_and_reactivated(
        self, seeded_store: IdentityStoreService
    ) -> None:
        record = seeded_store.create_local_user(
            user_name="erin", password_hash=hash_password("existing-password-1"), role="user"
        )
        seeded_store.deactivate_user(record.id)

        runner = _make_app().test_cli_runner()
        result = runner.invoke(
            args=["create-admin", "erin", "--password", "ignored-for-existing-user"]
        )
        assert result.exit_code == 0, result.output

        updated = seeded_store.get_by_id(record.id, use_cache=False)
        assert updated is not None
        assert updated.role == "admin"
        assert updated.active is True
        # Password untouched by the promote-existing path (still the
        # original hash, not re-hashed from the CLI's --password value).
        assert verify_password(updated.password_hash or "", "existing-password-1") is True

    def test_resolves_zero_admin_alarm(self, seeded_store: IdentityStoreService) -> None:
        seeded_store.create_local_user(user_name="only-user", role="user")
        assert seeded_store.has_zero_active_admins() is True

        runner = _make_app().test_cli_runner()
        runner.invoke(
            args=["create-admin", "recovery-admin", "--password", "recovery-password-1"]
        )

        assert seeded_store.has_zero_active_admins() is False
