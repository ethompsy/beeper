"""Tests for `GET /api/v1/auth/me` (Task 8.4 — ADR 0002 §3/§6/§7).

Mirrors `test_identity_resolver.py`'s fixtures/config-class pattern
(`_LocalConfig`/`_OidcNoScimConfig`/`_OidcScimConfig`/`_OidcScimStrictConfig`,
`_seed_session`, `seeded_store`) rather than importing them — this file's
config classes are its own contract, matching the established per-file
duplication convention in this test suite (`test_session_identity.py`,
`test_sse_reauth.py`).

Covers modes none/local/oidc x authenticated/anonymous, per Task 8.4's AC:
"`[T]` `/api/v1/auth/me` shape per ADR §3, tested in all three modes
(Python)."
"""

from __future__ import annotations

import time

import pytest
from flask import Flask

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig
from beeper_ui.services.identity_store import (
    IdentityStoreService,
    reset_identity_store,
    set_identity_store_for_testing,
)
from tests._fake_qdrant import FakeQdrantClient


@pytest.fixture(autouse=True)
def _secret_key_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-real-secret-for-auth-me-tests")
    yield


@pytest.fixture(autouse=True)
def _reset_store():
    reset_identity_store()
    yield
    reset_identity_store()


class _LocalConfig(TestingConfig):
    BEEPER_AUTH_MODE = "local"
    BEEPER_EXTERNAL_SCHEME = "http"


class _OidcNoScimConfig(TestingConfig):
    BEEPER_AUTH_MODE = "oidc"
    BEEPER_SCIM_ENABLED = False


class _OidcScimConfig(TestingConfig):
    BEEPER_AUTH_MODE = "oidc"
    BEEPER_SCIM_ENABLED = True


class _OidcScimStrictConfig(TestingConfig):
    BEEPER_AUTH_MODE = "oidc"
    BEEPER_SCIM_ENABLED = True
    BEEPER_SCIM_STRICT = True


def _seed_session(
    client,
    *,
    sub: str,
    email: str | None = None,
    name: str | None = None,
    external_id: str | None = None,
    role_snapshot: str = "user",
    exp_offset: float = 8 * 3600,
) -> None:
    now = time.time()
    with client.session_transaction() as sess:
        sess["identity"] = {
            "sub": sub,
            "email": email,
            "email_lc": email.strip().casefold() if email else None,
            "external_id": external_id,
            "name": name,
            "role_snapshot": role_snapshot,
            "iat": now,
            "exp": now + exp_offset,
        }


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


def _make_app(config_class: type) -> Flask:
    return create_app(config_class)


# ---------------------------------------------------------------------------
# [T] mode `none` — always the fixed anonymous shape, header-independent
# ---------------------------------------------------------------------------


class TestModeNone:
    def test_anonymous_shape(self) -> None:
        app = _make_app(TestingConfig)
        with app.test_client() as client:
            resp = client.get("/api/v1/auth/me")
            assert resp.status_code == 200
            assert resp.get_json() == {
                "authenticated": False,
                "auth_mode": "none",
                "user": None,
            }

    def test_role_header_does_not_change_the_response(self) -> None:
        """Mode `none` has no session/identity concept at all — the dev-only
        `X-Beeper-Role` header (which DOES grant an effective role on gated
        routes) must have zero effect on `/me`'s identity probe."""
        app = _make_app(TestingConfig)
        with app.test_client() as client:
            resp = client.get("/api/v1/auth/me", headers={"X-Beeper-Role": "admin"})
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["authenticated"] is False
            assert body["user"] is None

    def test_no_bootstrap_required_or_other_posture_leak(self) -> None:
        app = _make_app(TestingConfig)
        with app.test_client() as client:
            body = client.get("/api/v1/auth/me").get_json()
            assert set(body.keys()) == {"authenticated", "auth_mode", "user"}


# ---------------------------------------------------------------------------
# [T] mode `local`
# ---------------------------------------------------------------------------


class TestModeLocal:
    def test_no_session_is_anonymous(self) -> None:
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.get("/api/v1/auth/me")
            assert resp.status_code == 200
            assert resp.get_json() == {
                "authenticated": False,
                "auth_mode": "local",
                "user": None,
            }

    def test_authenticated_active_user(self, seeded_store: IdentityStoreService) -> None:
        record = seeded_store.create_local_user(
            user_name="alice@corp.com", display_name="Alice Alpha", role="admin"
        )
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            _seed_session(client, sub=record.id)
            resp = client.get("/api/v1/auth/me")
            assert resp.status_code == 200
            assert resp.get_json() == {
                "authenticated": True,
                "auth_mode": "local",
                "user": {
                    "user_name": "alice@corp.com",
                    "display_name": "Alice Alpha",
                    "role": "admin",
                },
            }

    def test_deactivated_user_is_anonymous_not_401(
        self, seeded_store: IdentityStoreService
    ) -> None:
        """`/me` never 401s (it is exempt from gating) — an
        inactive/deprovisioned session resolves to the plain anonymous body,
        the same 200 shape as no session at all."""
        record = seeded_store.create_local_user(user_name="bob@corp.com", role="user")
        seeded_store.deactivate_user(record.id)
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            _seed_session(client, sub=record.id)
            resp = client.get("/api/v1/auth/me")
            assert resp.status_code == 200
            assert resp.get_json()["authenticated"] is False

    def test_expired_session_is_anonymous(self, seeded_store: IdentityStoreService) -> None:
        record = seeded_store.create_local_user(user_name="carl@corp.com", role="user")
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            _seed_session(client, sub=record.id, exp_offset=-1)
            resp = client.get("/api/v1/auth/me")
            assert resp.status_code == 200
            assert resp.get_json()["authenticated"] is False

    def test_display_name_falls_back_to_user_name_when_blank(
        self, seeded_store: IdentityStoreService
    ) -> None:
        record = seeded_store.create_local_user(user_name="dana@corp.com", role="user")
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            _seed_session(client, sub=record.id)
            body = client.get("/api/v1/auth/me").get_json()
            assert body["user"]["display_name"] == "dana@corp.com"


# ---------------------------------------------------------------------------
# [T] mode `oidc`, SCIM disabled — claims-snapshot authoritative
# ---------------------------------------------------------------------------


class TestModeOidcNoScim:
    def test_no_session_is_anonymous(self) -> None:
        app = _make_app(_OidcNoScimConfig)
        with app.test_client() as client:
            resp = client.get("/api/v1/auth/me")
            assert resp.status_code == 200
            assert resp.get_json() == {
                "authenticated": False,
                "auth_mode": "oidc",
                "user": None,
            }

    def test_authenticated_uses_snapshot_role_and_claims(self) -> None:
        app = _make_app(_OidcNoScimConfig)
        with app.test_client() as client:
            _seed_session(
                client,
                sub="oidc-sub-1",
                email="erin@corp.com",
                name="Erin Echo",
                role_snapshot="admin",
            )
            resp = client.get("/api/v1/auth/me")
            assert resp.status_code == 200
            assert resp.get_json() == {
                "authenticated": True,
                "auth_mode": "oidc",
                "user": {
                    "user_name": "erin@corp.com",
                    "display_name": "Erin Echo",
                    "role": "admin",
                },
            }

    def test_display_name_falls_back_to_email_when_name_absent(self) -> None:
        app = _make_app(_OidcNoScimConfig)
        with app.test_client() as client:
            _seed_session(client, sub="oidc-sub-2", email="frank@corp.com")
            body = client.get("/api/v1/auth/me").get_json()
            assert body["user"]["user_name"] == "frank@corp.com"
            assert body["user"]["display_name"] == "frank@corp.com"

    def test_user_name_falls_back_to_sub_when_no_email_claim(self) -> None:
        app = _make_app(_OidcNoScimConfig)
        with app.test_client() as client:
            _seed_session(client, sub="oidc-sub-3")
            body = client.get("/api/v1/auth/me").get_json()
            assert body["user"]["user_name"] == "oidc-sub-3"


# ---------------------------------------------------------------------------
# [T] mode `oidc`, SCIM enabled — store-primary
# ---------------------------------------------------------------------------


class TestModeOidcScim:
    def test_found_active_uses_store_role_over_stale_snapshot(
        self, seeded_store: IdentityStoreService
    ) -> None:
        seeded_store.adopt_or_create_scim_user(
            user_name="grace@corp.com",
            external_id="ext-grace",
            display_name="Grace Gamma",
            group_display_names=["Admins"],
        )
        app = _make_app(_OidcScimConfig)
        with app.test_client() as client:
            _seed_session(
                client,
                sub="grace@corp.com",
                email="grace@corp.com",
                external_id="ext-grace",
                role_snapshot="user",  # deliberately stale — store must win
            )
            resp = client.get("/api/v1/auth/me")
            assert resp.status_code == 200
            assert resp.get_json() == {
                "authenticated": True,
                "auth_mode": "oidc",
                "user": {
                    "user_name": "grace@corp.com",
                    "display_name": "Grace Gamma",
                    "role": "admin",
                },
            }

    def test_found_inactive_is_anonymous_not_401(
        self, seeded_store: IdentityStoreService
    ) -> None:
        record = seeded_store.adopt_or_create_scim_user(
            user_name="hank@corp.com", external_id="ext-hank", group_display_names=[]
        )
        seeded_store.deactivate_user(record.id)
        app = _make_app(_OidcScimConfig)
        with app.test_client() as client:
            _seed_session(client, sub="hank@corp.com", email="hank@corp.com")
            resp = client.get("/api/v1/auth/me")
            assert resp.status_code == 200
            assert resp.get_json()["authenticated"] is False

    def test_not_provisioned_non_strict_defaults_to_user(
        self, seeded_store: IdentityStoreService
    ) -> None:
        app = _make_app(_OidcScimConfig)
        with app.test_client() as client:
            _seed_session(
                client,
                sub="never-provisioned",
                email="nobody@corp.com",
                name="Nobody Special",
            )
            resp = client.get("/api/v1/auth/me")
            assert resp.status_code == 200
            assert resp.get_json() == {
                "authenticated": True,
                "auth_mode": "oidc",
                "user": {
                    "user_name": "nobody@corp.com",
                    "display_name": "Nobody Special",
                    "role": "user",
                },
            }

    def test_not_provisioned_strict_is_authenticated_with_null_role(
        self, seeded_store: IdentityStoreService
    ) -> None:
        """The one place `authenticated` and "can call `/api/v1/*`" diverge
        (see `routes/auth.py`'s module docstring): the session is real and
        unexpired, so `authenticated` is `true`, but `role` is `null` since
        `BEEPER_SCIM_STRICT` refuses to grant one for an unprovisioned
        principal — never admin, never even the non-strict default `user`."""
        app = _make_app(_OidcScimStrictConfig)
        with app.test_client() as client:
            _seed_session(client, sub="never-provisioned-2", email="strict@corp.com")
            resp = client.get("/api/v1/auth/me")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["authenticated"] is True
            assert body["user"]["role"] is None
            assert body["user"]["user_name"] == "strict@corp.com"

    def test_lookup_matches_by_external_id_fallback(
        self, seeded_store: IdentityStoreService
    ) -> None:
        seeded_store.adopt_or_create_scim_user(
            user_name="ivan@corp.com",
            external_id="ext-ivan",
            group_display_names=["Admins"],
        )
        app = _make_app(_OidcScimConfig)
        with app.test_client() as client:
            # Session email deliberately stale/mismatched; external_id still
            # resolves the role via `resolve_role_for_identity()`. Display
            # fields fall back to the snapshot here (a documented
            # simplification — see `_display_fields()` — since
            # `get_by_username()` alone has no external_id fallback).
            _seed_session(
                client, sub="ivan-sub", email="stale@corp.com", external_id="ext-ivan"
            )
            resp = client.get("/api/v1/auth/me")
            assert resp.status_code == 200
            assert resp.get_json()["user"]["role"] == "admin"
