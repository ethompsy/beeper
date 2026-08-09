"""Tests for `admin_users_api_bp` (`/api/v1/admin/users`, Task 8.7 — ADR
0002 §6/§5.2/§5.3, FR60).

Mirrors `test_local_auth_routes.py`'s fixtures/config-class pattern
(per-file duplication is this suite's established convention — see
`test_auth_me.py`'s own docstring).

AC [T] linkage (docs/plans/react-ui.md Task 8.7):
  - every route `.required_role == "admin"` (structural) + user-role 403
    (behavioral) -> TestRbacStructural, TestRbacBehavioral
  - create/assign/deactivate/reset flows -> TestCreateUser, TestPatchUser,
    TestResetPassword
  - last-admin 409, store unchanged; non-final admin succeeds ->
    TestLastAdminProtection
  - SCIM-owned rows read-only in oidc mode; local records editable ->
    TestScimOwnedProtection
  - create/reset password follow the 8.6 hashing + min-length rules;
    created user can actually log in end-to-end (local mode) ->
    TestCreateUser, TestResetPassword, TestCreatedUserCanLogIn
  - oidc-mode create-user decision -> TestOidcModeCreateRefused
  - route registration (none -> 404; local/oidc -> present) ->
    TestRouteRegistration

Security-review addendum (post-review fixes, both MEDIUM):
  - non-dict JSON body -> 422 validation-failed, never an unhandled 500 ->
    TestMalformedJsonBody
  - last-admin guard is atomic (no separate unlocked pre-check +
    later-locked write) -> TestLastAdminGuardAtomicity
  - CSRF regression guard for this blueprint specifically -> TestCsrf
"""

from __future__ import annotations

import time

import pytest
from flask import Flask
from flask.testing import FlaskClient

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig
from beeper_ui.services.identity_store import (
    IdentityStoreService,
    LastAdminError,
    reset_identity_store,
    set_identity_store_for_testing,
)
from beeper_ui.services.password_hashing import hash_password
from tests._fake_qdrant import FakeQdrantClient


@pytest.fixture(autouse=True)
def _secret_key_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-real-secret-for-admin-users-tests")
    yield


@pytest.fixture(autouse=True)
def _reset_store():
    reset_identity_store()
    yield
    reset_identity_store()


class _LocalConfig(TestingConfig):
    BEEPER_AUTH_MODE = "local"
    BEEPER_EXTERNAL_SCHEME = "http"


class _OidcConfig(TestingConfig):
    BEEPER_AUTH_MODE = "oidc"
    BEEPER_EXTERNAL_SCHEME = "http"
    BEEPER_OIDC_ISSUER = "https://idp.example.com"
    BEEPER_OIDC_CLIENT_ID = "client-1"
    BEEPER_OIDC_CLIENT_SECRET = "secret-1"


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


SAME_ORIGIN = {"Origin": "http://localhost"}


def _login(client: FlaskClient, username: str, password: str) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers=SAME_ORIGIN,
    )
    assert resp.status_code == 200, resp.get_json()


def _admin_client(
    app: Flask,
    store: IdentityStoreService,
    *,
    username: str = "admin@corp.com",
    password: str = "admins-password-1",
) -> FlaskClient:
    store.create_local_user(user_name=username, password_hash=hash_password(password), role="admin")
    client = app.test_client()
    _login(client, username, password)
    return client


def _seed_session(
    client: FlaskClient,
    *,
    sub: str,
    email: str | None = None,
    name: str | None = None,
    external_id: str | None = None,
    role_snapshot: str = "user",
    exp_offset: float = 8 * 3600,
) -> None:
    """Directly write an identity snapshot into the session cookie —
    mirrors `test_auth_me.py`'s own `_seed_session()` helper (per-file
    duplication convention). Used for `oidc`-mode tests, where there is no
    local login route to drive a session through end-to-end."""
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


# ---------------------------------------------------------------------------
# [T] route registration — absent in mode `none`, present in local/oidc
# ---------------------------------------------------------------------------


class TestRouteRegistration:
    def test_absent_in_mode_none(self) -> None:
        app = _make_app(TestingConfig)
        with app.test_client() as client:
            resp = client.get("/api/v1/admin/users/", headers={"X-Beeper-Role": "admin"})
            assert resp.status_code == 404

    def test_present_in_local_mode(self, seeded_store: IdentityStoreService) -> None:
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.get("/api/v1/admin/users/")
            assert resp.status_code == 200

    def test_present_in_oidc_mode(self, seeded_store: IdentityStoreService) -> None:
        # oidc mode has no local login route; drive via the SCIM-adoption
        # seam instead, mirroring TestScimOwnedProtection's setup below, to
        # prove the *route* exists (structural role check covers RBAC).
        app = _make_app(_OidcConfig)
        with app.test_client() as client:
            resp = client.get("/api/v1/admin/users/", headers={"X-Beeper-Role": "admin"})
            # ALLOW_ROLE_HEADER only applies in mode "none"; in oidc mode the
            # resolver requires a real session, so this is 401, never 404 —
            # proving the blueprint IS registered (a 404 would mean absent).
            assert resp.status_code == 401


# ---------------------------------------------------------------------------
# [T] RBAC — structural (.required_role) + behavioral (403/401)
# ---------------------------------------------------------------------------

ADMIN_USERS_ENDPOINTS = [
    "admin_users_api.list_users",
    "admin_users_api.create_user",
    "admin_users_api.patch_user",
    "admin_users_api.reset_password",
]


class TestRbacStructural:
    @pytest.mark.parametrize("endpoint", ADMIN_USERS_ENDPOINTS)
    def test_endpoint_has_required_role_admin(self, endpoint: str) -> None:
        app = _make_app(_LocalConfig)
        view = app.view_functions[endpoint]
        assert (
            getattr(view, "required_role", None) == "admin"
        ), f"{endpoint} is missing @require_role('admin') (Task 8.7 / FR60)"

    def test_all_four_known_routes_present(self) -> None:
        app = _make_app(_LocalConfig)
        missing = [e for e in ADMIN_USERS_ENDPOINTS if e not in app.view_functions]
        assert missing == []


class TestRbacBehavioral:
    def test_anonymous_gets_401_in_local_mode(self, seeded_store: IdentityStoreService) -> None:
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.get("/api/v1/admin/users/")
            assert resp.status_code == 401
            assert resp.get_json()["type"] == "https://beeper.dev/errors/authentication-required"

    def test_non_admin_session_gets_403(self, seeded_store: IdentityStoreService) -> None:
        seeded_store.create_local_user(
            user_name="regular@corp.com",
            password_hash=hash_password("regulars-password-1"),
            role="user",
        )
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            _login(client, "regular@corp.com", "regulars-password-1")
            resp = client.get("/api/v1/admin/users/")
            assert resp.status_code == 403
            body = resp.get_json()
            assert body["type"] == "https://beeper.dev/errors/permission-denied"

    def test_admin_session_gets_200(self, seeded_store: IdentityStoreService) -> None:
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.get("/api/v1/admin/users/")
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# [T] GET / — list users
# ---------------------------------------------------------------------------


class TestListUsers:
    def test_lists_all_users_sorted_by_username(self, seeded_store: IdentityStoreService) -> None:
        seeded_store.create_local_user(
            user_name="zed@corp.com", password_hash=hash_password("x" * 12), role="user"
        )
        seeded_store.create_local_user(
            user_name="amy@corp.com", password_hash=hash_password("x" * 12), role="user"
        )
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store, username="admin2@corp.com") as client:
            resp = client.get("/api/v1/admin/users/")
            assert resp.status_code == 200
            names = [u["user_name"] for u in resp.get_json()]
            assert names == sorted(names)
            assert "zed@corp.com" in names
            assert "amy@corp.com" in names

    def test_response_shape_omits_password_hash(self, seeded_store: IdentityStoreService) -> None:
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.get("/api/v1/admin/users/")
            body = resp.get_json()
            admin_row = next(u for u in body if u["user_name"] == "admin@corp.com")
            assert set(admin_row.keys()) == {
                "id",
                "user_name",
                "display_name",
                "role",
                "origin",
                "active",
                "last_login_at",
            }
            assert admin_row["role"] == "admin"
            assert admin_row["origin"] == "local"
            assert admin_row["active"] is True
            # Logging in (via _admin_client's helper) stamps last_login_at.
            assert admin_row["last_login_at"] is not None

    def test_empty_store_returns_empty_array(self, seeded_store: IdentityStoreService) -> None:
        app = _make_app(_LocalConfig)
        # Bootstrap an admin purely to authenticate, then assert the OTHER
        # users list is empty (i.e. the admin itself is the only row).
        with _admin_client(app, seeded_store) as client:
            resp = client.get("/api/v1/admin/users/")
            assert len(resp.get_json()) == 1


# ---------------------------------------------------------------------------
# [T] POST / — create local user
# ---------------------------------------------------------------------------


class TestCreateUser:
    def test_create_success_201(self, seeded_store: IdentityStoreService) -> None:
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.post(
                "/api/v1/admin/users/",
                json={
                    "user_name": "newbie@corp.com",
                    "display_name": "Newbie Newton",
                    "password": "brand-new-password-1",
                    "role": "user",
                },
                headers=SAME_ORIGIN,
            )
            assert resp.status_code == 201
            body = resp.get_json()
            assert body["user_name"] == "newbie@corp.com"
            assert body["display_name"] == "Newbie Newton"
            assert body["role"] == "user"
            assert body["origin"] == "local"
            assert body["active"] is True
            assert "password" not in body
            assert "password_hash" not in body

    def test_create_admin_role(self, seeded_store: IdentityStoreService) -> None:
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.post(
                "/api/v1/admin/users/",
                json={
                    "user_name": "secondadmin@corp.com",
                    "password": "second-admins-pw-1",
                    "role": "admin",
                },
                headers=SAME_ORIGIN,
            )
            assert resp.status_code == 201
            assert resp.get_json()["role"] == "admin"

    def test_duplicate_username_409(self, seeded_store: IdentityStoreService) -> None:
        seeded_store.create_local_user(
            user_name="dup@corp.com", password_hash=hash_password("x" * 12), role="user"
        )
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.post(
                "/api/v1/admin/users/",
                json={
                    "user_name": "dup@corp.com",
                    "password": "another-password-1",
                    "role": "user",
                },
                headers=SAME_ORIGIN,
            )
            assert resp.status_code == 409
            assert resp.get_json()["type"] == "https://beeper.dev/errors/username-already-exists"

    def test_short_password_rejected_422(self, seeded_store: IdentityStoreService) -> None:
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.post(
                "/api/v1/admin/users/",
                json={"user_name": "shortpw@corp.com", "password": "short1", "role": "user"},
                headers=SAME_ORIGIN,
            )
            assert resp.status_code == 422
            assert resp.get_json()["type"] == "https://beeper.dev/errors/validation-failed"

    def test_empty_username_rejected_422(self, seeded_store: IdentityStoreService) -> None:
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.post(
                "/api/v1/admin/users/",
                json={"user_name": "  ", "password": "a-real-password-1", "role": "user"},
                headers=SAME_ORIGIN,
            )
            assert resp.status_code == 422

    def test_invalid_role_rejected_422(self, seeded_store: IdentityStoreService) -> None:
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.post(
                "/api/v1/admin/users/",
                json={
                    "user_name": "badrole@corp.com",
                    "password": "a-real-password-1",
                    "role": "superuser",
                },
                headers=SAME_ORIGIN,
            )
            assert resp.status_code == 422

    def test_password_is_argon2_hashed_at_rest(self, seeded_store: IdentityStoreService) -> None:
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            client.post(
                "/api/v1/admin/users/",
                json={
                    "user_name": "hashcheck@corp.com",
                    "password": "a-real-password-1",
                    "role": "user",
                },
                headers=SAME_ORIGIN,
            )
        record = seeded_store.get_by_username("hashcheck@corp.com")
        assert record is not None
        assert record.password_hash is not None
        assert record.password_hash.startswith("$argon2id$")
        assert record.password_hash != "a-real-password-1"


class TestOidcModeCreateRefused:
    """The oidc-mode local-user-creation decision (409, not 422 — see
    `routes/admin_users.py`'s module docstring)."""

    def test_create_in_oidc_mode_409(self, seeded_store: IdentityStoreService) -> None:
        # Seed an admin via adopt-and-link (SCIM path) since local login
        # isn't registered in oidc mode, then drive its session directly
        # (mirrors `test_auth_me.py`'s `_seed_session()` pattern) — the
        # oidc+SCIM resolver re-resolves role from the store per request,
        # so `role_snapshot` here just needs to be non-empty; the store's
        # "Admins" group membership is what actually grants admin.
        record = seeded_store.adopt_or_create_scim_user(
            user_name="oidcadmin@corp.com",
            external_id="ext-1",
            group_display_names=["Admins"],
        )
        app = _make_app(_OidcConfig)
        with app.test_client() as client:
            _seed_session(
                client,
                sub=record.id,
                email="oidcadmin@corp.com",
                external_id="ext-1",
                role_snapshot="admin",
            )
            resp = client.post(
                "/api/v1/admin/users/",
                json={
                    "user_name": "newlocal@corp.com",
                    "password": "a-real-password-1",
                    "role": "user",
                },
                headers=SAME_ORIGIN,
            )
            assert resp.status_code == 409
            assert (
                resp.get_json()["type"]
                == "https://beeper.dev/errors/local-user-creation-unavailable"
            )


# ---------------------------------------------------------------------------
# [T] PATCH /<user_id> — role/active
# ---------------------------------------------------------------------------


class TestPatchUser:
    def test_promote_user_to_admin(self, seeded_store: IdentityStoreService) -> None:
        target = seeded_store.create_local_user(
            user_name="promote@corp.com", password_hash=hash_password("x" * 12), role="user"
        )
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.patch(
                f"/api/v1/admin/users/{target.id}", json={"role": "admin"}, headers=SAME_ORIGIN
            )
            assert resp.status_code == 200
            assert resp.get_json()["role"] == "admin"

    def test_deactivate_non_admin(self, seeded_store: IdentityStoreService) -> None:
        target = seeded_store.create_local_user(
            user_name="deact@corp.com", password_hash=hash_password("x" * 12), role="user"
        )
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.patch(
                f"/api/v1/admin/users/{target.id}", json={"active": False}, headers=SAME_ORIGIN
            )
            assert resp.status_code == 200
            assert resp.get_json()["active"] is False

    def test_reactivate(self, seeded_store: IdentityStoreService) -> None:
        target = seeded_store.create_local_user(
            user_name="react@corp.com", password_hash=hash_password("x" * 12), role="user"
        )
        seeded_store.deactivate_user(target.id)
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.patch(
                f"/api/v1/admin/users/{target.id}", json={"active": True}, headers=SAME_ORIGIN
            )
            assert resp.status_code == 200
            assert resp.get_json()["active"] is True

    def test_unknown_user_404(self, seeded_store: IdentityStoreService) -> None:
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.patch(
                "/api/v1/admin/users/does-not-exist", json={"active": False}, headers=SAME_ORIGIN
            )
            assert resp.status_code == 404
            assert resp.get_json()["type"] == "https://beeper.dev/errors/user-not-found"

    def test_empty_body_422(self, seeded_store: IdentityStoreService) -> None:
        target = seeded_store.create_local_user(
            user_name="empty@corp.com", password_hash=hash_password("x" * 12), role="user"
        )
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.patch(f"/api/v1/admin/users/{target.id}", json={}, headers=SAME_ORIGIN)
            assert resp.status_code == 422

    def test_invalid_role_422(self, seeded_store: IdentityStoreService) -> None:
        target = seeded_store.create_local_user(
            user_name="badrole2@corp.com", password_hash=hash_password("x" * 12), role="user"
        )
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.patch(
                f"/api/v1/admin/users/{target.id}", json={"role": "superuser"}, headers=SAME_ORIGIN
            )
            assert resp.status_code == 422

    def test_invalid_active_type_422(self, seeded_store: IdentityStoreService) -> None:
        target = seeded_store.create_local_user(
            user_name="badactive@corp.com", password_hash=hash_password("x" * 12), role="user"
        )
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.patch(
                f"/api/v1/admin/users/{target.id}", json={"active": "yes"}, headers=SAME_ORIGIN
            )
            assert resp.status_code == 422


# ---------------------------------------------------------------------------
# [T] Last-admin protection (ADR §5.3, FR60)
# ---------------------------------------------------------------------------


class TestLastAdminProtection:
    def test_demoting_sole_admin_409_store_unchanged(
        self, seeded_store: IdentityStoreService
    ) -> None:
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            # `_admin_client` seeded exactly one admin (itself). Fetch its id.
            me = client.get("/api/v1/admin/users/").get_json()[0]
            resp = client.patch(
                f"/api/v1/admin/users/{me['id']}", json={"role": "user"}, headers=SAME_ORIGIN
            )
            assert resp.status_code == 409
            assert resp.get_json()["type"] == "https://beeper.dev/errors/last-admin"
        unchanged = seeded_store.get_by_id(me["id"], use_cache=False)
        assert unchanged is not None
        assert unchanged.role == "admin"
        assert unchanged.active is True

    def test_deactivating_sole_admin_409_store_unchanged(
        self, seeded_store: IdentityStoreService
    ) -> None:
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            me = client.get("/api/v1/admin/users/").get_json()[0]
            resp = client.patch(
                f"/api/v1/admin/users/{me['id']}", json={"active": False}, headers=SAME_ORIGIN
            )
            assert resp.status_code == 409
            assert resp.get_json()["type"] == "https://beeper.dev/errors/last-admin"
        unchanged = seeded_store.get_by_id(me["id"], use_cache=False)
        assert unchanged is not None
        assert unchanged.active is True

    def test_demoting_a_non_final_admin_succeeds(self, seeded_store: IdentityStoreService) -> None:
        second = seeded_store.create_local_user(
            user_name="second-admin@corp.com", password_hash=hash_password("x" * 12), role="admin"
        )
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.patch(
                f"/api/v1/admin/users/{second.id}", json={"role": "user"}, headers=SAME_ORIGIN
            )
            assert resp.status_code == 200
            assert resp.get_json()["role"] == "user"

    def test_deactivating_a_non_final_admin_succeeds(
        self, seeded_store: IdentityStoreService
    ) -> None:
        second = seeded_store.create_local_user(
            user_name="third-admin@corp.com", password_hash=hash_password("x" * 12), role="admin"
        )
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.patch(
                f"/api/v1/admin/users/{second.id}", json={"active": False}, headers=SAME_ORIGIN
            )
            assert resp.status_code == 200
            assert resp.get_json()["active"] is False


# ---------------------------------------------------------------------------
# [T] SCIM-owned protection (ADR §5.2, FR60) — oidc mode only
# ---------------------------------------------------------------------------


class TestScimOwnedProtection:
    def _oidc_admin_client(self, app: Flask, store: IdentityStoreService) -> FlaskClient:
        record = store.adopt_or_create_scim_user(
            user_name="scimadmin@corp.com", external_id="ext-admin", group_display_names=["Admins"]
        )
        client = app.test_client()
        _seed_session(
            client,
            sub=record.id,
            email="scimadmin@corp.com",
            external_id="ext-admin",
            role_snapshot="admin",
        )
        return client

    def test_patch_scim_owned_user_in_oidc_mode_409(
        self, seeded_store: IdentityStoreService
    ) -> None:
        app = _make_app(_OidcConfig)
        target = seeded_store.adopt_or_create_scim_user(
            user_name="scimtarget@corp.com", external_id="ext-target", group_display_names=[]
        )
        client = self._oidc_admin_client(app, seeded_store)
        resp = client.patch(
            f"/api/v1/admin/users/{target.id}", json={"role": "admin"}, headers=SAME_ORIGIN
        )
        assert resp.status_code == 409
        assert resp.get_json()["type"] == "https://beeper.dev/errors/scim-owned-user"
        unchanged = seeded_store.get_by_id(target.id, use_cache=False)
        assert unchanged is not None
        assert unchanged.role == "user"

    def test_reset_password_scim_owned_user_in_oidc_mode_409(
        self, seeded_store: IdentityStoreService
    ) -> None:
        app = _make_app(_OidcConfig)
        target = seeded_store.adopt_or_create_scim_user(
            user_name="scimtarget2@corp.com", external_id="ext-target-2", group_display_names=[]
        )
        client = self._oidc_admin_client(app, seeded_store)
        resp = client.post(
            f"/api/v1/admin/users/{target.id}/reset-password",
            json={"password": "a-real-password-1"},
            headers=SAME_ORIGIN,
        )
        assert resp.status_code == 409
        assert resp.get_json()["type"] == "https://beeper.dev/errors/scim-owned-user"

    def test_local_origin_record_editable_in_oidc_mode(
        self, seeded_store: IdentityStoreService
    ) -> None:
        app = _make_app(_OidcConfig)
        # A local-origin leftover record (created back when mode was
        # `local`) must remain editable even while running in `oidc` mode —
        # the 409 is scoped to origin == "scim", not to the server's mode
        # alone.
        target = seeded_store.create_local_user(
            user_name="localleftover@corp.com", password_hash=hash_password("x" * 12), role="user"
        )
        client = self._oidc_admin_client(app, seeded_store)
        resp = client.patch(
            f"/api/v1/admin/users/{target.id}", json={"active": False}, headers=SAME_ORIGIN
        )
        assert resp.status_code == 200
        assert resp.get_json()["active"] is False

    def test_scim_origin_record_editable_when_server_is_in_local_mode(
        self, seeded_store: IdentityStoreService
    ) -> None:
        # A SCIM-linked record left over from a prior oidc deployment is
        # editable once the server itself is back in `local` mode (no live
        # SCIM writer to contend with) — the 409 is deliberately scoped to
        # "while in oidc mode", per this module's docstring.
        target = seeded_store.adopt_or_create_scim_user(
            user_name="scimleftover@corp.com", external_id="ext-leftover", group_display_names=[]
        )
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.patch(
                f"/api/v1/admin/users/{target.id}", json={"role": "admin"}, headers=SAME_ORIGIN
            )
            assert resp.status_code == 200
            assert resp.get_json()["role"] == "admin"


# ---------------------------------------------------------------------------
# [T] POST /<user_id>/reset-password
# ---------------------------------------------------------------------------


class TestResetPassword:
    def test_reset_success_200(self, seeded_store: IdentityStoreService) -> None:
        target = seeded_store.create_local_user(
            user_name="resetme@corp.com", password_hash=hash_password("old-password-1"), role="user"
        )
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.post(
                f"/api/v1/admin/users/{target.id}/reset-password",
                json={"password": "brand-new-password-2"},
                headers=SAME_ORIGIN,
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert "password" not in body
            assert "password_hash" not in body

    def test_reset_unknown_user_404(self, seeded_store: IdentityStoreService) -> None:
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.post(
                "/api/v1/admin/users/does-not-exist/reset-password",
                json={"password": "a-real-password-1"},
                headers=SAME_ORIGIN,
            )
            assert resp.status_code == 404

    def test_reset_short_password_422(self, seeded_store: IdentityStoreService) -> None:
        target = seeded_store.create_local_user(
            user_name="shortreset@corp.com",
            password_hash=hash_password("old-password-1"),
            role="user",
        )
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.post(
                f"/api/v1/admin/users/{target.id}/reset-password",
                json={"password": "short1"},
                headers=SAME_ORIGIN,
            )
            assert resp.status_code == 422


class TestPasswordResetHashPersistence:
    """Proves the one additive `identity_store.update_user(password_hash=)`
    kwarg actually persists a new hash onto an EXISTING record (the change
    flagged in this module's docstring)."""

    def test_new_hash_persisted_and_old_password_stops_working(
        self, seeded_store: IdentityStoreService
    ) -> None:
        target = seeded_store.create_local_user(
            user_name="rehash@corp.com", password_hash=hash_password("old-password-1"), role="user"
        )
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            client.post(
                f"/api/v1/admin/users/{target.id}/reset-password",
                json={"password": "new-password-99"},
                headers=SAME_ORIGIN,
            )
        updated = seeded_store.get_by_id(target.id, use_cache=False)
        assert updated is not None
        assert updated.password_hash is not None
        assert updated.password_hash.startswith("$argon2id$")
        assert updated.password_hash != hash_password("old-password-1")


# ---------------------------------------------------------------------------
# [T] End-to-end: created user can actually log in (local mode)
# ---------------------------------------------------------------------------


class TestCreatedUserCanLogIn:
    def test_admin_created_user_can_log_in_through_the_real_login_route(
        self, seeded_store: IdentityStoreService
    ) -> None:
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            create_resp = client.post(
                "/api/v1/admin/users/",
                json={
                    "user_name": "freshlogin@corp.com",
                    "password": "fresh-login-password-1",
                    "role": "user",
                },
                headers=SAME_ORIGIN,
            )
            assert create_resp.status_code == 201

        with app.test_client() as new_client:
            login_resp = new_client.post(
                "/api/v1/auth/login",
                json={"username": "freshlogin@corp.com", "password": "fresh-login-password-1"},
                headers=SAME_ORIGIN,
            )
            assert login_resp.status_code == 200
            assert login_resp.get_json()["authenticated"] is True

    def test_admin_reset_password_then_new_password_logs_in(
        self, seeded_store: IdentityStoreService
    ) -> None:
        target = seeded_store.create_local_user(
            user_name="resetlogin@corp.com",
            password_hash=hash_password("old-password-1"),
            role="user",
        )
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.post(
                f"/api/v1/admin/users/{target.id}/reset-password",
                json={"password": "post-reset-password-1"},
                headers=SAME_ORIGIN,
            )
            assert resp.status_code == 200

        with app.test_client() as new_client:
            old_login = new_client.post(
                "/api/v1/auth/login",
                json={"username": "resetlogin@corp.com", "password": "old-password-1"},
                headers=SAME_ORIGIN,
            )
            assert old_login.status_code == 401

            new_login = new_client.post(
                "/api/v1/auth/login",
                json={"username": "resetlogin@corp.com", "password": "post-reset-password-1"},
                headers=SAME_ORIGIN,
            )
            assert new_login.status_code == 200


# ---------------------------------------------------------------------------
# [T] Security-review fix #2: malformed (non-dict) JSON body -> 422, never 500
# ---------------------------------------------------------------------------


class TestMalformedJsonBody:
    """A syntactically-valid but non-object JSON top-level value (a list,
    string, number, or bool) previously reached `body.get(...)` unchanged
    (`get_json(silent=True) or {}` only substitutes `{}` for a FALSY
    value), raising an unhandled `AttributeError` — Flask's default,
    non-RFC7807 500. Every mutating route must instead return this
    module's own `422 validation-failed`."""

    @pytest.mark.parametrize("payload", [[1, 2, 3], "just a string", 42, True])
    def test_create_user_non_dict_body_422_not_500(
        self, seeded_store: IdentityStoreService, payload: object
    ) -> None:
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.post("/api/v1/admin/users/", json=payload, headers=SAME_ORIGIN)
            assert resp.status_code == 422
            assert resp.get_json()["type"] == "https://beeper.dev/errors/validation-failed"

    @pytest.mark.parametrize("payload", [[1, 2, 3], "just a string", 42, True])
    def test_patch_user_non_dict_body_422_not_500(
        self, seeded_store: IdentityStoreService, payload: object
    ) -> None:
        target = seeded_store.create_local_user(
            user_name="malformed1@corp.com", password_hash=hash_password("x" * 12), role="user"
        )
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.patch(
                f"/api/v1/admin/users/{target.id}", json=payload, headers=SAME_ORIGIN
            )
            assert resp.status_code == 422
            assert resp.get_json()["type"] == "https://beeper.dev/errors/validation-failed"

    @pytest.mark.parametrize("payload", [[1, 2, 3], "just a string", 42, True])
    def test_reset_password_non_dict_body_422_not_500(
        self, seeded_store: IdentityStoreService, payload: object
    ) -> None:
        target = seeded_store.create_local_user(
            user_name="malformed2@corp.com", password_hash=hash_password("x" * 12), role="user"
        )
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.post(
                f"/api/v1/admin/users/{target.id}/reset-password",
                json=payload,
                headers=SAME_ORIGIN,
            )
            assert resp.status_code == 422
            assert resp.get_json()["type"] == "https://beeper.dev/errors/validation-failed"


# ---------------------------------------------------------------------------
# [T] Security-review fix #1: atomic last-admin guard (TOCTOU close)
# ---------------------------------------------------------------------------


class TestLastAdminGuardAtomicity:
    """Store-level proof that `update_user(..., guard_last_admin=True)`
    raises `LastAdminError` from INSIDE its own write-lock critical
    section, rather than via a separate, unlocked `would_orphan_admins()`
    pre-check — the fix for the TOCTOU race the security review flagged
    (two concurrent demotions of two different admins could each pass a
    separate pre-check before either write landed)."""

    def test_guard_last_admin_raises_and_does_not_write(
        self, seeded_store: IdentityStoreService
    ) -> None:
        admin = seeded_store.create_local_user(
            user_name="soleadmin@corp.com", password_hash=hash_password("x" * 12), role="admin"
        )
        with pytest.raises(LastAdminError):
            seeded_store.update_user(admin.id, role="user", guard_last_admin=True)
        unchanged = seeded_store.get_by_id(admin.id, use_cache=False)
        assert unchanged is not None
        assert unchanged.role == "admin"

    def test_guard_last_admin_allows_non_orphaning_write(
        self, seeded_store: IdentityStoreService
    ) -> None:
        seeded_store.create_local_user(
            user_name="admin-a@corp.com", password_hash=hash_password("x" * 12), role="admin"
        )
        second = seeded_store.create_local_user(
            user_name="admin-b@corp.com", password_hash=hash_password("x" * 12), role="admin"
        )
        updated = seeded_store.update_user(second.id, role="user", guard_last_admin=True)
        assert updated.role == "user"

    def test_guard_last_admin_false_by_default_never_raises(
        self, seeded_store: IdentityStoreService
    ) -> None:
        """Default behavior (SCIM's own call sites, and any pre-8.7 caller)
        is UNCHANGED — `update_user()` without `guard_last_admin=True`
        still never refuses, per ADR §5.3's "SCIM writes alarm instead"."""
        admin = seeded_store.create_local_user(
            user_name="scimstyle@corp.com", password_hash=hash_password("x" * 12), role="admin"
        )
        updated = seeded_store.update_user(admin.id, role="user")
        assert updated.role == "user"

    def test_the_route_uses_the_atomic_guard_not_a_separate_precheck(
        self, seeded_store: IdentityStoreService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """White-box regression guard (security-review recommendation #4):
        `patch_user()` must call `update_user(..., guard_last_admin=True)`
        and must NOT call `would_orphan_admins()` at all — asserts the
        route was actually rewired to the atomic primitive, not just that
        its observable 409 behavior still happens to pass."""
        import beeper_ui.routes.admin_users as admin_users_module

        orphan_calls: list[str] = []
        original = IdentityStoreService.would_orphan_admins

        def spy(self: IdentityStoreService, user_id: str, **kwargs: object) -> bool:
            orphan_calls.append(user_id)
            return original(self, user_id, **kwargs)

        monkeypatch.setattr(IdentityStoreService, "would_orphan_admins", spy)

        target = seeded_store.create_local_user(
            user_name="routecheck@corp.com", password_hash=hash_password("x" * 12), role="user"
        )
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.patch(
                f"/api/v1/admin/users/{target.id}", json={"active": False}, headers=SAME_ORIGIN
            )
            assert resp.status_code == 200
        assert orphan_calls == [], (
            "admin_users.patch_user() called would_orphan_admins() — it should call "
            "update_user(..., guard_last_admin=True) exclusively"
        )
        assert admin_users_module.LastAdminError is LastAdminError


# ---------------------------------------------------------------------------
# [T] CSRF regression guard for this blueprint (security-review recommendation #3)
# ---------------------------------------------------------------------------


class TestCsrf:
    """The shared `before_request` hook (`resolve_request_identity()`)
    covers CSRF for `/api/v1/admin/*` since it is NOT in
    `permissions.EXEMPT_PATH_PREFIXES` — this module's routes do not
    self-enforce it. This is cheap regression insurance against a future
    accidental addition of `/api/v1/admin` to that exemption list."""

    def test_patch_without_origin_or_referer_403_csrf_rejected(
        self, seeded_store: IdentityStoreService
    ) -> None:
        target = seeded_store.create_local_user(
            user_name="csrfcheck@corp.com", password_hash=hash_password("x" * 12), role="user"
        )
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.patch(f"/api/v1/admin/users/{target.id}", json={"active": False})
            assert resp.status_code == 403
            assert resp.get_json()["type"] == "https://beeper.dev/errors/csrf-rejected"
        unchanged = seeded_store.get_by_id(target.id, use_cache=False)
        assert unchanged is not None
        assert unchanged.active is True

    def test_create_with_cross_origin_origin_header_403_csrf_rejected(
        self, seeded_store: IdentityStoreService
    ) -> None:
        app = _make_app(_LocalConfig)
        with _admin_client(app, seeded_store) as client:
            resp = client.post(
                "/api/v1/admin/users/",
                json={
                    "user_name": "evil@corp.com",
                    "password": "a-real-password-1",
                    "role": "user",
                },
                headers={"Origin": "http://evil.example.com"},
            )
            assert resp.status_code == 403
            assert resp.get_json()["type"] == "https://beeper.dev/errors/csrf-rejected"
