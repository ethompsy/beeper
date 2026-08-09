"""Tests for the unified resolver (Task 8.3 — ADR 0002 §7):
`resolve_request_identity()`, the §2 exemption matrix, and the Origin/
Referer CSRF check.

Mode `none`'s byte-identical behavior is already exhaustively proven by the
pre-existing, UNMODIFIED `tests/test_permissions.py` (31+ tests) — this file
adds only a couple of confidence spot-checks for mode `none` and focuses on
the NEW `local`/`oidc` behavior.
"""

from __future__ import annotations

import time
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import Flask, g

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig
from beeper_ui.middleware.permissions import (
    EXEMPT_PATH_PREFIXES,
    _is_exempt_path,
    require_role,
)
from beeper_ui.services.identity_store import (
    IdentityStoreService,
    reset_identity_store,
    set_identity_store_for_testing,
)
from tests._fake_qdrant import FakeQdrantClient


@pytest.fixture(autouse=True)
def _secret_key_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-real-secret-for-session-tests")
    yield


@pytest.fixture(autouse=True)
def _reset_store():
    reset_identity_store()
    yield
    reset_identity_store()


class _LocalConfig(TestingConfig):
    BEEPER_AUTH_MODE = "local"
    # Flask's test client always issues plain-http requests; matching
    # BEEPER_EXTERNAL_SCHEME here lets the CSRF same-origin scheme check
    # (beeper_ui.middleware.session.same_origin_request()) pass for
    # same-origin `Origin: http://localhost` test requests below — the
    # default "https" would otherwise reject every one of them.
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


def _register_test_routes(app: Flask) -> Flask:
    @app.route("/api/v1/test-resource")
    @require_role("user")
    def api_resource() -> dict:
        return {"role": g.user_role}

    @app.route("/api/v1/test-admin-resource")
    @require_role("admin")
    def api_admin_resource() -> dict:
        return {"role": g.user_role}

    @app.route("/api/v1/test-mutate", methods=["POST"])
    @require_role("user")
    def api_mutate() -> dict:
        return {"ok": True}

    @app.route("/some-page")
    @require_role("user")
    def some_page() -> str:
        return "page-ok"

    return app


def _make_app(config_class: type) -> Flask:
    return _register_test_routes(create_app(config_class))


def _seed_session(
    client,
    *,
    sub: str,
    email: str | None = None,
    external_id: str | None = None,
    role_snapshot: str = "user",
    exp_offset: float = 8 * 3600,
    iat_offset: float = 0,
) -> None:
    now = time.time()
    with client.session_transaction() as sess:
        sess["identity"] = {
            "sub": sub,
            "email": email,
            "email_lc": email.strip().casefold() if email else None,
            "external_id": external_id,
            "name": None,
            "role_snapshot": role_snapshot,
            "iat": now - iat_offset,
            "exp": now + exp_offset,
        }


def _extract_next(location: str) -> str | None:
    parsed = urlsplit(location)
    qs = parse_qs(parsed.query)
    values = qs.get("next")
    return values[0] if values else None


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


# ---------------------------------------------------------------------------
# [T] Exemption matrix — table-driven
# ---------------------------------------------------------------------------


class TestExemptionMatrixTableDriven:
    """Every row of `EXEMPT_PATH_PREFIXES` exercised, plus boundary cases
    proving prefix matching doesn't over-match (`/apple` is not `/app`)."""

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("/health/api", True),
            ("/health/api/", True),
            ("/app", True),
            ("/app/", True),
            ("/app/assets/index-abc123.js", True),
            ("/auth", True),
            ("/auth/login", True),
            ("/auth/callback", True),
            ("/api/v1/auth", True),
            ("/api/v1/auth/login", True),
            ("/api/v1/auth/me", True),
            ("/socket.io", True),
            ("/socket.io/", True),
            ("/socket.io/socket.io.js", True),
            ("/scim/v2", True),
            ("/scim/v2/Users", True),
            # Non-exempt / boundary cases — must NOT match.
            ("/apple", False),
            ("/application", False),
            ("/authentication", False),
            ("/api/v1/authenticate", False),
            ("/scim2/v2/Users", False),
            ("/health/", False),
            ("/health", False),
            ("/investigations", False),
            ("/api/v1/investigations", False),
            ("/api/v1/investigations/inv-1/events", False),
            ("/", False),
            # Path-confusion hardening (mirrors react_registry.py's
            # `_is_always_excluded()`): a literal `..` segment must never
            # be treated as exempt, even though the raw string starts with
            # an exempt prefix — fails closed to normal gating instead.
            ("/api/v1/auth/../../investigations/secret", False),
            ("/app/../admin/users", False),
            ("/health/api/../../investigations", False),
        ],
    )
    def test_is_exempt_path(self, path: str, expected: bool) -> None:
        assert _is_exempt_path(path) is expected

    def test_every_prefix_has_at_least_one_covering_row_above(self) -> None:
        """Guards the table itself: if a new prefix is added to
        `EXEMPT_PATH_PREFIXES` without a corresponding parametrized row
        above, this fails loudly instead of silently under-testing it."""
        covered_prefixes = {
            "/health/api",
            "/app",
            "/auth",
            "/api/v1/auth",
            "/socket.io",
            "/scim/v2",
        }
        assert set(EXEMPT_PATH_PREFIXES) == covered_prefixes


class TestExemptionMatrixEndToEnd:
    """HTTP-level proof that exempt paths skip identity gating entirely in
    `local`/`oidc` mode (no synthetic 401/302 from the resolver)."""

    @pytest.mark.parametrize("config_class", [_LocalConfig, _OidcNoScimConfig])
    def test_health_api_open_with_no_session(self, config_class: type) -> None:
        app = _make_app(config_class)
        with app.test_client() as client:
            resp = client.get("/health/api")
            assert resp.status_code == 200

    @pytest.mark.parametrize("config_class", [_LocalConfig, _OidcNoScimConfig])
    def test_socket_io_falls_through_to_its_own_410(self, config_class: type) -> None:
        app = _make_app(config_class)
        with app.test_client() as client:
            resp = client.get("/socket.io/")
            assert resp.status_code == 410
            assert resp.content_type == "application/problem+json"

    @pytest.mark.parametrize("config_class", [_LocalConfig, _OidcNoScimConfig])
    def test_scim_v2_falls_through_to_plain_404_today(self, config_class: type) -> None:
        app = _make_app(config_class)
        with app.test_client() as client:
            resp = client.get("/scim/v2/Users")
            # No blueprint registered yet (Task 8.8) — Flask's normal 404,
            # NOT our resolver's synthetic authentication-required 401.
            assert resp.status_code == 404

    @pytest.mark.parametrize("config_class", [_LocalConfig, _OidcNoScimConfig])
    def test_auth_prefix_open_with_no_session(self, config_class: type) -> None:
        app = _make_app(config_class)
        with app.test_client() as client:
            resp = client.get("/auth/login")
            # No blueprint registered yet (Task 8.5) — plain 404, not 401/302.
            assert resp.status_code == 404

    @pytest.mark.parametrize("config_class", [_LocalConfig, _OidcNoScimConfig])
    def test_api_v1_auth_prefix_open_with_no_session(self, config_class: type) -> None:
        """Task 8.4 landed `GET /api/v1/auth/me` (see `test_auth_me.py` for
        its full behavioral coverage) — this exemption-matrix test now
        proves the *reachable-logged-out* half of the contract: a 200 with
        an unauthenticated body, not a synthetic 401/302 from the resolver
        (superseding this test's prior "no blueprint registered yet, plain
        404" assertion, documented here per the Task 8.2 precedent of never
        swapping a pinned assertion silently)."""
        app = _make_app(config_class)
        with app.test_client() as client:
            resp = client.get("/api/v1/auth/me")
            assert resp.status_code == 200
            assert resp.get_json()["authenticated"] is False

    def test_non_exempt_api_path_is_gated_with_no_session(self) -> None:
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.get("/api/v1/test-resource")
            assert resp.status_code == 401

    def test_non_exempt_page_path_is_gated_with_no_session(self) -> None:
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.get("/some-page")
            assert resp.status_code == 302


# ---------------------------------------------------------------------------
# [T] Mode `none` spot-checks (full coverage lives in test_permissions.py)
# ---------------------------------------------------------------------------


class TestModeNoneSpotCheck:
    def test_none_mode_default_role_is_user(self) -> None:
        app = _make_app(TestingConfig)
        with app.test_client() as client:
            resp = client.get("/api/v1/test-resource")
            assert resp.status_code == 200
            assert resp.get_json()["role"] == "user"

    def test_none_mode_role_header_still_honored(self) -> None:
        app = _make_app(TestingConfig)
        with app.test_client() as client:
            resp = client.get(
                "/api/v1/test-admin-resource", headers={"X-Beeper-Role": "admin"}
            )
            assert resp.status_code == 200

    def test_none_mode_unaffected_by_cross_origin_post(self) -> None:
        """CSRF check must never fire in mode `none` — no session-cookie
        auth is ever active there."""
        app = _make_app(TestingConfig)
        with app.test_client() as client:
            resp = client.post(
                "/api/v1/test-mutate", headers={"Origin": "http://evil.example.com"}
            )
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# [T] Resolver mode matrix — local
# ---------------------------------------------------------------------------


class TestLocalModeResolution:
    def test_unauthenticated_api_gets_401_problem_json(self) -> None:
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.get("/api/v1/test-resource")
            assert resp.status_code == 401
            assert resp.content_type == "application/problem+json"
            body = resp.get_json()
            assert body["type"] == "https://beeper.dev/errors/authentication-required"
            assert body["status"] == 401

    def test_unauthenticated_page_gets_302_to_app_login_with_next(self) -> None:
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.get("/some-page?foo=bar")
            assert resp.status_code == 302
            location = resp.headers["Location"]
            assert location.startswith("/app/login?")
            assert _extract_next(location) == "/some-page?foo=bar"

    def test_authenticated_active_admin_resolves_admin_role(
        self, seeded_store: IdentityStoreService
    ) -> None:
        record = seeded_store.create_local_user(user_name="alice@corp.com", role="admin")
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            _seed_session(client, sub=record.id)
            resp = client.get("/api/v1/test-admin-resource")
            assert resp.status_code == 200
            assert resp.get_json()["role"] == "admin"

    def test_authenticated_user_role_is_denied_admin_route(
        self, seeded_store: IdentityStoreService
    ) -> None:
        record = seeded_store.create_local_user(user_name="bob@corp.com", role="user")
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            _seed_session(client, sub=record.id)
            resp = client.get("/api/v1/test-admin-resource")
            assert resp.status_code == 403  # require_role's RFC7807 403, unchanged

    def test_deleted_or_unknown_user_id_is_unauthenticated(
        self, seeded_store: IdentityStoreService
    ) -> None:
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            _seed_session(client, sub="ghost-user-id")
            resp = client.get("/api/v1/test-resource")
            assert resp.status_code == 401

    def test_expired_session_is_unauthenticated(
        self, seeded_store: IdentityStoreService
    ) -> None:
        record = seeded_store.create_local_user(user_name="carl@corp.com", role="user")
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            _seed_session(client, sub=record.id, exp_offset=-1)  # already expired
            resp = client.get("/api/v1/test-resource")
            assert resp.status_code == 401

    def test_deactivated_user_within_cache_ttl_still_succeeds_stale(
        self, seeded_store: IdentityStoreService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """[T] simulate: cache TTL semantics observed through the resolver,
        not just the store directly."""
        clock_state = {"t": 1000.0}
        monkeypatch.setattr(seeded_store, "_clock", lambda: clock_state["t"])
        record = seeded_store.create_local_user(user_name="dana@corp.com", role="user")
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            _seed_session(client, sub=record.id)
            resp = client.get("/api/v1/test-resource")
            assert resp.status_code == 200  # warms the resolver-level cache

            seeded_store._client.collections["beeper_users"][record.id]["active"] = False
            clock_state["t"] += 30  # within 60s TTL

            resp2 = client.get("/api/v1/test-resource")
            assert resp2.status_code == 200  # still stale-active

    def test_deactivated_user_after_cache_ttl_is_unauthenticated(
        self, seeded_store: IdentityStoreService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """[T] deactivation takes effect within the 60s cache TTL window."""
        clock_state = {"t": 1000.0}
        monkeypatch.setattr(seeded_store, "_clock", lambda: clock_state["t"])
        record = seeded_store.create_local_user(user_name="erin@corp.com", role="user")
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            _seed_session(client, sub=record.id)
            resp = client.get("/api/v1/test-resource")
            assert resp.status_code == 200

            seeded_store._client.collections["beeper_users"][record.id]["active"] = False
            clock_state["t"] += 61  # past the 60s TTL

            resp2 = client.get("/api/v1/test-resource")
            assert resp2.status_code == 401


# ---------------------------------------------------------------------------
# [T] Resolver mode matrix — oidc (with and without SCIM)
# ---------------------------------------------------------------------------


class TestOidcWithoutScimResolution:
    def test_role_snapshot_is_authoritative(self) -> None:
        app = _make_app(_OidcNoScimConfig)
        with app.test_client() as client:
            _seed_session(client, sub="oidc-sub-1", role_snapshot="admin")
            resp = client.get("/api/v1/test-admin-resource")
            assert resp.status_code == 200
            assert resp.get_json()["role"] == "admin"

    def test_never_touches_the_store(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(*_a: object, **_k: object) -> None:
            raise AssertionError("store must not be consulted when SCIM is disabled")

        monkeypatch.setattr("beeper_ui.middleware.permissions.get_identity_store", _boom)
        app = _make_app(_OidcNoScimConfig)
        with app.test_client() as client:
            _seed_session(client, sub="oidc-sub-2", role_snapshot="user")
            resp = client.get("/api/v1/test-resource")
            assert resp.status_code == 200

    def test_unauthenticated_redirects_to_auth_login(self) -> None:
        app = _make_app(_OidcNoScimConfig)
        with app.test_client() as client:
            resp = client.get("/some-page")
            assert resp.status_code == 302
            assert resp.headers["Location"].startswith("/auth/login?")


class TestOidcWithScimResolution:
    def test_found_active_resolves_store_role(
        self, seeded_store: IdentityStoreService
    ) -> None:
        seeded_store.adopt_or_create_scim_user(
            user_name="frank@corp.com",
            external_id="ext-frank",
            group_display_names=["Admins"],
        )
        app = _make_app(_OidcScimConfig)
        with app.test_client() as client:
            _seed_session(
                client,
                sub="frank@corp.com",
                email="frank@corp.com",
                external_id="ext-frank",
                role_snapshot="user",  # snapshot deliberately wrong — store must win
            )
            resp = client.get("/api/v1/test-admin-resource")
            assert resp.status_code == 200
            assert resp.get_json()["role"] == "admin"

    def test_found_inactive_is_unauthenticated(
        self, seeded_store: IdentityStoreService
    ) -> None:
        record = seeded_store.adopt_or_create_scim_user(
            user_name="gail@corp.com",
            external_id="ext-gail",
            group_display_names=["Everyone"],
        )
        seeded_store.deactivate_user(record.id)
        app = _make_app(_OidcScimConfig)
        with app.test_client() as client:
            _seed_session(client, sub="gail@corp.com", email="gail@corp.com")
            resp = client.get("/api/v1/test-resource")
            assert resp.status_code == 401

    def test_not_provisioned_non_strict_defaults_to_user(
        self, seeded_store: IdentityStoreService
    ) -> None:
        app = _make_app(_OidcScimConfig)
        with app.test_client() as client:
            _seed_session(client, sub="never-provisioned", email="nobody@corp.com")
            resp = client.get("/api/v1/test-resource")
            assert resp.status_code == 200
            assert resp.get_json()["role"] == "user"

    def test_not_provisioned_non_strict_never_grants_admin(
        self, seeded_store: IdentityStoreService
    ) -> None:
        app = _make_app(_OidcScimConfig)
        with app.test_client() as client:
            _seed_session(
                client,
                sub="never-provisioned-2",
                email="nobody2@corp.com",
                role_snapshot="admin",  # snapshot claims admin — must be ignored
            )
            resp = client.get("/api/v1/test-admin-resource")
            assert resp.status_code == 403  # never admin when unprovisioned

    def test_not_provisioned_strict_is_403_not_provisioned(
        self, seeded_store: IdentityStoreService
    ) -> None:
        app = _make_app(_OidcScimStrictConfig)
        with app.test_client() as client:
            _seed_session(client, sub="never-provisioned-3", email="strict@corp.com")
            resp = client.get("/api/v1/test-resource")
            assert resp.status_code == 403
            body = resp.get_json()
            assert body["type"] == "https://beeper.dev/errors/not-provisioned"

    def test_not_provisioned_strict_session_is_not_cleared(
        self, seeded_store: IdentityStoreService
    ) -> None:
        """403 (forbidden) is distinct from 401 (unauthenticated) — the
        session must survive so a SUBSEQUENT SCIM push can self-heal within
        60s without forcing a re-login."""
        app = _make_app(_OidcScimStrictConfig)
        with app.test_client() as client:
            _seed_session(client, sub="never-provisioned-4", email="heals@corp.com")
            first = client.get("/api/v1/test-resource")
            assert first.status_code == 403

            seeded_store.adopt_or_create_scim_user(
                user_name="heals@corp.com",
                external_id="ext-heals",
                group_display_names=[],
            )
            second = client.get("/api/v1/test-resource")
            assert second.status_code == 200  # no re-login needed
            assert second.get_json()["role"] == "user"

    def test_lookup_matches_by_external_id_fallback(
        self, seeded_store: IdentityStoreService
    ) -> None:
        seeded_store.adopt_or_create_scim_user(
            user_name="harry@corp.com",
            external_id="ext-harry",
            group_display_names=["Admins"],
        )
        app = _make_app(_OidcScimConfig)
        with app.test_client() as client:
            # Session email deliberately stale/mismatched; external_id still resolves.
            _seed_session(
                client, sub="harry-sub", email="stale@corp.com", external_id="ext-harry"
            )
            resp = client.get("/api/v1/test-admin-resource")
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# [T] CSRF — Origin/Referer host-equality check
# ---------------------------------------------------------------------------


class TestCsrfCheck:
    def test_cross_origin_post_with_valid_session_rejected(
        self, seeded_store: IdentityStoreService
    ) -> None:
        record = seeded_store.create_local_user(user_name="ivy@corp.com", role="user")
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            _seed_session(client, sub=record.id)
            resp = client.post(
                "/api/v1/test-mutate", headers={"Origin": "http://evil.example.com"}
            )
            assert resp.status_code == 403
            body = resp.get_json()
            assert body["type"] == "https://beeper.dev/errors/csrf-rejected"

    def test_same_origin_post_with_valid_session_allowed(
        self, seeded_store: IdentityStoreService
    ) -> None:
        record = seeded_store.create_local_user(user_name="jack@corp.com", role="user")
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            _seed_session(client, sub=record.id)
            resp = client.post(
                "/api/v1/test-mutate", headers={"Origin": "http://localhost"}
            )
            assert resp.status_code == 200

    def test_same_host_but_wrong_scheme_origin_rejected(
        self, seeded_store: IdentityStoreService
    ) -> None:
        """Security-review MEDIUM fix: an origin is `(scheme, host, port)`
        (RFC 6454 §7) — same HOST but a scheme that doesn't match the
        configured `BEEPER_EXTERNAL_SCHEME` must be rejected. `_LocalConfig`
        here is `http`, so an `https://localhost` Origin (same host, wrong
        scheme relative to the deployment's configured scheme) is a
        mismatch, guarding against a same-host Origin accepted on the
        strength of host-equality alone during an SSL-strip/downgrade or a
        misconfigured dual HTTP/HTTPS listener."""
        record = seeded_store.create_local_user(user_name="nadia@corp.com", role="user")
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            _seed_session(client, sub=record.id)
            resp = client.post(
                "/api/v1/test-mutate", headers={"Origin": "https://localhost"}
            )
            assert resp.status_code == 403

    def test_origin_host_comparison_is_case_insensitive(
        self, seeded_store: IdentityStoreService
    ) -> None:
        record = seeded_store.create_local_user(user_name="omar@corp.com", role="user")
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            _seed_session(client, sub=record.id)
            resp = client.post(
                "/api/v1/test-mutate", headers={"Origin": "http://LOCALHOST"}
            )
            assert resp.status_code == 200

    def test_referer_fallback_when_origin_absent(
        self, seeded_store: IdentityStoreService
    ) -> None:
        record = seeded_store.create_local_user(user_name="kelly@corp.com", role="user")
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            _seed_session(client, sub=record.id)
            resp = client.post(
                "/api/v1/test-mutate",
                headers={"Referer": "http://localhost/some-page"},
            )
            assert resp.status_code == 200

    def test_missing_both_origin_and_referer_rejected(
        self, seeded_store: IdentityStoreService
    ) -> None:
        record = seeded_store.create_local_user(user_name="liam@corp.com", role="user")
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            _seed_session(client, sub=record.id)
            resp = client.post("/api/v1/test-mutate")
            assert resp.status_code == 403

    def test_safe_method_get_never_csrf_checked(
        self, seeded_store: IdentityStoreService
    ) -> None:
        record = seeded_store.create_local_user(user_name="mona@corp.com", role="user")
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            _seed_session(client, sub=record.id)
            resp = client.get(
                "/api/v1/test-resource", headers={"Origin": "http://evil.example.com"}
            )
            assert resp.status_code == 200

    def test_unauthenticated_cross_origin_post_gets_401_not_403(self) -> None:
        """No session at all -> the 401 unauthenticated path wins; CSRF is
        only checked once a session has authenticated the request."""
        app = _make_app(_LocalConfig)
        with app.test_client() as client:
            resp = client.post(
                "/api/v1/test-mutate", headers={"Origin": "http://evil.example.com"}
            )
            assert resp.status_code == 401


# ---------------------------------------------------------------------------
# g.user / g.user_role integration surface
# ---------------------------------------------------------------------------


class TestGUserIntegrationSurface:
    def test_g_user_is_session_identity_in_local_mode(
        self, seeded_store: IdentityStoreService
    ) -> None:
        record = seeded_store.create_local_user(user_name="nora@corp.com", role="admin")
        app = create_app(_LocalConfig)

        captured = {}

        @app.route("/api/v1/capture-guser")
        @require_role("user")
        def capture() -> dict:
            captured["sub"] = g.user.sub
            captured["role"] = g.user_role
            return {"ok": True}

        with app.test_client() as client:
            _seed_session(client, sub=record.id)
            resp = client.get("/api/v1/capture-guser")
            assert resp.status_code == 200
            assert captured["sub"] == record.id
            assert captured["role"] == "admin"
