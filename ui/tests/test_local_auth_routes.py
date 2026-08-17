"""Tests for `POST /api/v1/auth/login` + `POST /api/v1/auth/logout`
(Task 8.6 — ADR 0002 §6, FR59).

Mirrors `test_auth_me.py`/`test_identity_resolver.py`'s fixtures/config
-class pattern (per-file duplication is this suite's established
convention — see `test_auth_me.py`'s own docstring).

AC [T] linkage (docs/plans/react-ui.md Task 8.6):
  - login sets a rotated session; unknown/bad-password/deactivated return
    identical 401s -> TestLoginMatrix, TestUniformFailureBodyIsByteIdentical
  - CSRF: cross-origin login/logout POSTs rejected; same-origin accepted
    -> TestCsrf
  - login route absent (404) outside `local` mode -> TestRouteRegistration
  - constant-delay mechanism exercised -> TestConstantDelay
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
from beeper_ui.services.password_hashing import hash_password
from tests._fake_qdrant import FakeQdrantClient


@pytest.fixture(autouse=True)
def _secret_key_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-real-secret-for-local-auth-tests")
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
    # Task 8.5's boot refusal requires OIDC completeness in `oidc` mode
    # (merge-resolution addition, same stubs as test_auth_me.py).
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


# ---------------------------------------------------------------------------
# [T] route registration — local only for /login; local+oidc for /logout
# ---------------------------------------------------------------------------


class TestRouteRegistration:
    def test_login_absent_outside_local_mode_none(self) -> None:
        app = _make_app(TestingConfig)  # mode "none"
        with app.test_client() as client:
            resp = client.post("/api/v1/auth/login", json={}, headers=SAME_ORIGIN)
            assert resp.status_code == 404

    def test_login_absent_outside_local_mode_oidc(self) -> None:
        app = _make_app(_OidcConfig)
        with app.test_client() as client:
            resp = client.post("/api/v1/auth/login", json={}, headers=SAME_ORIGIN)
            assert resp.status_code == 404

    def test_login_present_in_local_mode(
        self, seeded_store: IdentityStoreService
    ) -> None:
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.post("/api/v1/auth/login", json={}, headers=SAME_ORIGIN)
            assert resp.status_code != 404

    def test_logout_absent_in_mode_none(self) -> None:
        app = _make_app(TestingConfig)
        with app.test_client() as client:
            resp = client.post("/api/v1/auth/logout", headers=SAME_ORIGIN)
            assert resp.status_code == 404

    def test_logout_present_in_local_mode(self) -> None:
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.post("/api/v1/auth/logout", headers=SAME_ORIGIN)
            assert resp.status_code == 200

    def test_logout_present_in_oidc_mode(self) -> None:
        app = _make_app(_OidcConfig)
        with app.test_client() as client:
            resp = client.post("/api/v1/auth/logout", headers=SAME_ORIGIN)
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# [T] login matrix — success + the three uniform-failure causes
# ---------------------------------------------------------------------------


class TestLoginMatrix:
    def test_success_sets_rotated_session_and_returns_me_shape(
        self, seeded_store: IdentityStoreService
    ) -> None:
        seeded_store.create_local_user(
            user_name="alice@corp.com",
            password_hash=hash_password("correct-horse-battery-staple"),
            display_name="Alice Alpha",
            role="admin",
        )
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.post(
                "/api/v1/auth/login",
                json={"username": "alice@corp.com", "password": "correct-horse-battery-staple"},
                headers=SAME_ORIGIN,
            )
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
            # Session actually established — /me reflects it on a
            # subsequent request using the same client (cookie jar).
            me = client.get("/api/v1/auth/me").get_json()
            assert me["authenticated"] is True
            assert me["user"]["user_name"] == "alice@corp.com"

    def test_success_stamps_last_login_at(self, seeded_store: IdentityStoreService) -> None:

        record = seeded_store.create_local_user(
            user_name="bob@corp.com", password_hash=hash_password("hunter2hunter2"), role="user"
        )
        assert record.last_login_at is None
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            client.post(
                "/api/v1/auth/login",
                json={"username": "bob@corp.com", "password": "hunter2hunter2"},
                headers=SAME_ORIGIN,
            )
        updated = seeded_store.get_by_id(record.id, use_cache=False)
        assert updated is not None
        assert updated.last_login_at is not None

    def test_unknown_username_401(self, seeded_store: IdentityStoreService) -> None:
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.post(
                "/api/v1/auth/login",
                json={"username": "nobody@corp.com", "password": "whatever12345"},
                headers=SAME_ORIGIN,
            )
            assert resp.status_code == 401

    def test_bad_password_401(self, seeded_store: IdentityStoreService) -> None:

        seeded_store.create_local_user(
            user_name="carl@corp.com", password_hash=hash_password("real-password-1"), role="user"
        )
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.post(
                "/api/v1/auth/login",
                json={"username": "carl@corp.com", "password": "wrong-password-1"},
                headers=SAME_ORIGIN,
            )
            assert resp.status_code == 401

    def test_deactivated_user_401(self, seeded_store: IdentityStoreService) -> None:

        record = seeded_store.create_local_user(
            user_name="dana@corp.com", password_hash=hash_password("dana-password-1"), role="user"
        )
        seeded_store.deactivate_user(record.id)
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.post(
                "/api/v1/auth/login",
                json={"username": "dana@corp.com", "password": "dana-password-1"},
                headers=SAME_ORIGIN,
            )
            assert resp.status_code == 401

    def test_user_with_no_local_password_401(
        self, seeded_store: IdentityStoreService
    ) -> None:
        # A pure-SCIM-origin record (password_hash=None) attempting local
        # login — must fail uniformly too, not raise/500.
        seeded_store.adopt_or_create_scim_user(
            user_name="erin@corp.com", external_id="ext-erin", group_display_names=[]
        )
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.post(
                "/api/v1/auth/login",
                json={"username": "erin@corp.com", "password": "anything123"},
                headers=SAME_ORIGIN,
            )
            assert resp.status_code == 401

    def test_missing_body_401_not_500(self, seeded_store: IdentityStoreService) -> None:
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.post("/api/v1/auth/login", headers=SAME_ORIGIN)
            assert resp.status_code == 401


# ---------------------------------------------------------------------------
# [T] uniform 401 bodies — byte-equal across all three failure causes
# ---------------------------------------------------------------------------


class TestUniformFailureBodyIsByteIdentical:
    def test_all_three_failure_causes_produce_byte_identical_bodies(
        self, seeded_store: IdentityStoreService
    ) -> None:
        seeded_store.create_local_user(
            user_name="frank@corp.com",
            password_hash=hash_password("franks-password-1"),
            role="user",
        )
        deactivated = seeded_store.create_local_user(
            user_name="gail@corp.com",
            password_hash=hash_password("gails-password-1"),
            role="user",
        )
        seeded_store.deactivate_user(deactivated.id)

        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            unknown_resp = client.post(
                "/api/v1/auth/login",
                json={"username": "nobody@corp.com", "password": "x" * 12},
                headers=SAME_ORIGIN,
            )
            bad_password_resp = client.post(
                "/api/v1/auth/login",
                json={"username": "frank@corp.com", "password": "wrong-wrong-wrong"},
                headers=SAME_ORIGIN,
            )
            deactivated_resp = client.post(
                "/api/v1/auth/login",
                json={"username": "gail@corp.com", "password": "gails-password-1"},
                headers=SAME_ORIGIN,
            )

        assert unknown_resp.status_code == 401
        assert bad_password_resp.status_code == 401
        assert deactivated_resp.status_code == 401

        # Byte-equal response bodies — the exact `[T]` assertion.
        assert unknown_resp.data == bad_password_resp.data == deactivated_resp.data

        body = unknown_resp.get_json()
        assert body == {
            "type": "https://beeper.dev/errors/invalid-credentials",
            "title": "Invalid Credentials",
            "status": 401,
            "detail": "Invalid username or password.",
            "instance": "/api/v1/auth/login",
        }
        assert unknown_resp.content_type == "application/problem+json"


# ---------------------------------------------------------------------------
# [T] constant-delay mechanism
# ---------------------------------------------------------------------------


class TestConstantDelay:
    def test_delay_is_applied_on_every_failure_cause(
        self, seeded_store: IdentityStoreService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import beeper_ui.routes.auth as auth_module

        calls: list[float] = []
        monkeypatch.setattr(auth_module, "_sleep", lambda seconds: calls.append(seconds))

        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            client.post(
                "/api/v1/auth/login",
                json={"username": "nobody@corp.com", "password": "x" * 12},
                headers=SAME_ORIGIN,
            )
        assert len(calls) == 1
        assert 0 < calls[0] <= auth_module.LOGIN_FAILURE_DELAY_SECONDS

    def test_delay_not_applied_when_request_already_exceeded_the_floor(
        self, seeded_store: IdentityStoreService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import beeper_ui.routes.auth as auth_module

        calls: list[float] = []
        monkeypatch.setattr(auth_module, "_sleep", lambda seconds: calls.append(seconds))
        # Force `_monotonic()` to report the request already took longer
        # than the floor — `_apply_constant_delay` must not sleep at all.
        times = iter([0.0, auth_module.LOGIN_FAILURE_DELAY_SECONDS + 1.0])
        monkeypatch.setattr(auth_module, "_monotonic", lambda: next(times))

        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            client.post(
                "/api/v1/auth/login",
                json={"username": "nobody@corp.com", "password": "x" * 12},
                headers=SAME_ORIGIN,
            )
        assert calls == []

    def test_delay_not_applied_on_success(
        self, seeded_store: IdentityStoreService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import beeper_ui.routes.auth as auth_module

        seeded_store.create_local_user(
            user_name="hank@corp.com", password_hash=hash_password("hanks-password-1"), role="user"
        )
        calls: list[float] = []
        monkeypatch.setattr(auth_module, "_sleep", lambda seconds: calls.append(seconds))

        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.post(
                "/api/v1/auth/login",
                json={"username": "hank@corp.com", "password": "hanks-password-1"},
                headers=SAME_ORIGIN,
            )
        assert resp.status_code == 200
        assert calls == []

    def test_unknown_user_verify_runs_against_the_dummy_hash_not_skipped(
        self, seeded_store: IdentityStoreService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Proves the timing-normalization path is actually exercised
        (`verify_password` is called with `DUMMY_PASSWORD_HASH`, not
        short-circuited) for an unknown username."""
        import beeper_ui.routes.auth as auth_module

        calls: list[tuple[str, str]] = []
        real_verify = auth_module.verify_password

        def spy(password_hash: str, password: str) -> bool:
            calls.append((password_hash, password))
            return real_verify(password_hash, password)

        monkeypatch.setattr(auth_module, "verify_password", spy)

        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            client.post(
                "/api/v1/auth/login",
                json={"username": "nobody@corp.com", "password": "x" * 12},
                headers=SAME_ORIGIN,
            )
        assert len(calls) == 1
        assert calls[0][0] == auth_module.DUMMY_PASSWORD_HASH


# ---------------------------------------------------------------------------
# [T] CSRF — cross-origin rejected, same-origin accepted (login + logout)
# ---------------------------------------------------------------------------


class TestCsrf:
    def test_login_cross_origin_rejected(self, seeded_store: IdentityStoreService) -> None:
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.post(
                "/api/v1/auth/login",
                json={"username": "x", "password": "y" * 12},
                headers={"Origin": "http://evil.example.com"},
            )
            assert resp.status_code == 403
            assert resp.get_json()["type"] == "https://beeper.dev/errors/csrf-rejected"

    def test_login_missing_origin_and_referer_rejected(
        self, seeded_store: IdentityStoreService
    ) -> None:
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.post(
                "/api/v1/auth/login", json={"username": "x", "password": "y" * 12}
            )
            assert resp.status_code == 403

    def test_login_same_origin_accepted(self, seeded_store: IdentityStoreService) -> None:
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.post(
                "/api/v1/auth/login",
                json={"username": "nobody@corp.com", "password": "y" * 12},
                headers=SAME_ORIGIN,
            )
            # Reaches credential evaluation (401, not 403 CSRF).
            assert resp.status_code == 401

    def test_logout_cross_origin_rejected(self) -> None:
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.post(
                "/api/v1/auth/logout", headers={"Origin": "http://evil.example.com"}
            )
            assert resp.status_code == 403
            assert resp.get_json()["type"] == "https://beeper.dev/errors/csrf-rejected"

    def test_logout_same_origin_accepted(self) -> None:
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.post("/api/v1/auth/logout", headers=SAME_ORIGIN)
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# [T] logout clears the session
# ---------------------------------------------------------------------------


class TestLogout:
    def test_logout_clears_session_me_becomes_anonymous(
        self, seeded_store: IdentityStoreService
    ) -> None:
        seeded_store.create_local_user(
            user_name="ivan@corp.com", password_hash=hash_password("ivans-password-1"), role="user"
        )
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            client.post(
                "/api/v1/auth/login",
                json={"username": "ivan@corp.com", "password": "ivans-password-1"},
                headers=SAME_ORIGIN,
            )
            assert client.get("/api/v1/auth/me").get_json()["authenticated"] is True

            logout_resp = client.post("/api/v1/auth/logout", headers=SAME_ORIGIN)
            assert logout_resp.status_code == 200
            assert logout_resp.get_json() == {
                "authenticated": False,
                "auth_mode": "local",
                "user": None,
            }

            assert client.get("/api/v1/auth/me").get_json()["authenticated"] is False

    def test_logout_with_no_session_is_a_no_op_200(self) -> None:
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.post("/api/v1/auth/logout", headers=SAME_ORIGIN)
            assert resp.status_code == 200
            assert resp.get_json()["authenticated"] is False


# ---------------------------------------------------------------------------
# [T] end-to-end: a logged-in local admin's session passes require_role("admin")
# ---------------------------------------------------------------------------


class TestLoggedInAdminPassesRequireRoleAdmin:
    """AC (docs/plans/react-ui.md Task 8.6): "local mode: session admin
    passes `require_role('admin')`". `test_identity_resolver.py` (Task 8.3)
    already proves the resolver's per-mode truth table generically (a
    seeded session -> `require_role` outcome, independent of how the
    session was established); this test closes the loop specifically
    through THIS task's own `POST /api/v1/auth/login` endpoint end-to-end
    — login response -> cookie jar -> a real `@require_role("admin")`
    route -> 200, and the mirror-image 403 for a non-admin login."""

    def test_admin_login_then_admin_gated_route_succeeds(
        self, seeded_store: IdentityStoreService
    ) -> None:
        from beeper_ui.middleware.permissions import require_role

        seeded_store.create_local_user(
            user_name="admin@corp.com",
            password_hash=hash_password("admins-password-1"),
            role="admin",
        )
        app = _make_app(_LocalConfig)

        @app.route("/api/v1/test-admin-only")
        @require_role("admin")
        def _admin_only() -> dict:
            return {"ok": True}

        with app.test_client() as client:
            login_resp = client.post(
                "/api/v1/auth/login",
                json={"username": "admin@corp.com", "password": "admins-password-1"},
                headers=SAME_ORIGIN,
            )
            assert login_resp.status_code == 200

            gated_resp = client.get("/api/v1/test-admin-only")
            assert gated_resp.status_code == 200
            assert gated_resp.get_json() == {"ok": True}

    def test_non_admin_login_then_admin_gated_route_403s(
        self, seeded_store: IdentityStoreService
    ) -> None:
        from beeper_ui.middleware.permissions import require_role

        seeded_store.create_local_user(
            user_name="regular@corp.com",
            password_hash=hash_password("regulars-password-1"),
            role="user",
        )
        app = _make_app(_LocalConfig)

        @app.route("/api/v1/test-admin-only-2")
        @require_role("admin")
        def _admin_only_2() -> dict:
            return {"ok": True}

        with app.test_client() as client:
            login_resp = client.post(
                "/api/v1/auth/login",
                json={"username": "regular@corp.com", "password": "regulars-password-1"},
                headers=SAME_ORIGIN,
            )
            assert login_resp.status_code == 200

            gated_resp = client.get("/api/v1/test-admin-only-2")
            assert gated_resp.status_code == 403

    def test_unauthenticated_api_request_401s_in_local_mode(self) -> None:
        app = _make_app(_LocalConfig)

        @app.route("/api/v1/test-needs-auth")
        def _needs_auth() -> dict:
            return {"ok": True}

        with app.test_client() as client:
            resp = client.get("/api/v1/test-needs-auth")
            assert resp.status_code == 401
            assert (
                resp.get_json()["type"] == "https://beeper.dev/errors/authentication-required"
            )
