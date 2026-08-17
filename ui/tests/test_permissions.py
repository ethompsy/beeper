"""Tests for permission middleware (Story 1.1: Permission Model Enforcement)."""

import base64
import json

import pytest
from flask import Flask, g
from flask.testing import FlaskClient

from beeper_ui.app import create_app
from beeper_ui.config import (
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
    get_config,
)
from beeper_ui.middleware.permissions import require_role


@pytest.fixture
def permission_app() -> Flask:
    """Create app with test routes for permission testing."""
    app = create_app(TestingConfig)

    @app.route("/test/admin-only")
    @require_role("admin")
    def admin_only() -> dict[str, str]:
        return {"message": "admin access granted"}

    @app.route("/test/user-route")
    @require_role("user")
    def user_route() -> dict[str, str]:
        return {"message": "user access granted"}

    @app.route("/test/unprotected")
    def unprotected() -> dict[str, str]:
        return {"message": "anyone can access"}

    return app


@pytest.fixture
def production_permission_app() -> Flask:
    """Create app with ProductionConfig and test routes for permission testing.

    Task 6.2a / ADR 0001 §0(a) item 3: `X-Beeper-Role` must be refused under
    production config. `ProductionConfig.__init__`'s SECRET_KEY validation is
    dead code under `Flask.config.from_object(<class>)` (no instantiation
    happens), so this exercises the real, class-attribute-driven gate
    (`Config.ALLOW_ROLE_HEADER`) rather than relying on that constructor.
    """
    app = create_app(ProductionConfig)

    @app.route("/test/admin-only")
    @require_role("admin")
    def admin_only() -> dict[str, str]:
        return {"message": "admin access granted"}

    return app


def _make_bearer_token(groups: list[str]) -> str:
    """Craft a JWT-shaped 3-segment token with the given `groups` claim.

    NOTE: this used to be `_make_k8s_token`, a legitimate-looking name from
    when `_extract_role_from_k8s_token` actually read this payload. That
    function is deleted (Task 8.2 / ADR 0002 §7 CRITICAL-1) — nothing in the
    app reads an `Authorization: Bearer` header's payload anymore, in any
    mode. This helper now exists ONLY to prove that: every test using it
    lives in `TestBearerTokensNeverGrantRoles` below and asserts the crafted
    token is ignored.
    """
    header_b64 = base64.urlsafe_b64encode(
        json.dumps({"alg": "RS256"}).encode()
    ).rstrip(b"=").decode()
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps({"groups": groups}).encode()
    ).rstrip(b"=").decode()
    sig_b64 = base64.urlsafe_b64encode(b"fake-signature").rstrip(b"=").decode()
    return f"{header_b64}.{payload_b64}.{sig_b64}"


class TestRequireRoleAdminRejectsUser:
    """AC1: @require_role('admin') rejects role 'user' with 403 + RFC 7807."""

    def test_user_role_gets_403_on_admin_route(self, permission_app: Flask) -> None:
        with permission_app.test_client() as client:
            resp = client.get("/test/admin-only", headers={"X-Beeper-Role": "user"})
            assert resp.status_code == 403

    def test_no_role_header_defaults_to_user_gets_403(self, permission_app: Flask) -> None:
        with permission_app.test_client() as client:
            resp = client.get("/test/admin-only")
            assert resp.status_code == 403

    def test_403_response_is_rfc7807_format(self, permission_app: Flask) -> None:
        with permission_app.test_client() as client:
            resp = client.get("/test/admin-only", headers={"X-Beeper-Role": "user"})
            data = resp.get_json()
            assert data["type"] == "https://beeper.dev/errors/permission-denied"
            assert data["title"] == "Permission Denied"
            assert data["status"] == 403
            assert data["detail"] == "Admin role required to access this resource"
            assert data["instance"] == "/test/admin-only"

    def test_403_content_type_is_problem_json(self, permission_app: Flask) -> None:
        with permission_app.test_client() as client:
            resp = client.get("/test/admin-only", headers={"X-Beeper-Role": "user"})
            assert resp.content_type == "application/problem+json"


class TestRequireRoleAdminAllowsAdmin:
    """AC1: @require_role('admin') allows role 'admin'."""

    def test_admin_role_gets_200_on_admin_route(self, permission_app: Flask) -> None:
        with permission_app.test_client() as client:
            resp = client.get("/test/admin-only", headers={"X-Beeper-Role": "admin"})
            assert resp.status_code == 200
            assert resp.get_json()["message"] == "admin access granted"


class TestRequireRoleUserAllowsBothRoles:
    """AC1: @require_role('user') allows both 'admin' and 'user' roles."""

    def test_user_role_accesses_user_route(self, permission_app: Flask) -> None:
        with permission_app.test_client() as client:
            resp = client.get("/test/user-route", headers={"X-Beeper-Role": "user"})
            assert resp.status_code == 200
            assert resp.get_json()["message"] == "user access granted"

    def test_admin_role_accesses_user_route(self, permission_app: Flask) -> None:
        with permission_app.test_client() as client:
            resp = client.get("/test/user-route", headers={"X-Beeper-Role": "admin"})
            assert resp.status_code == 200
            assert resp.get_json()["message"] == "user access granted"

    def test_no_role_defaults_to_user_accesses_user_route(self, permission_app: Flask) -> None:
        with permission_app.test_client() as client:
            resp = client.get("/test/user-route")
            assert resp.status_code == 200


class TestDefaultRoleIsUser:
    """AC2: Default role is 'user' when no header/token present."""

    def test_default_role_is_user(self, permission_app: Flask) -> None:
        with permission_app.test_client() as client:
            resp = client.get("/test/unprotected")
            assert resp.status_code == 200

    def test_g_user_role_defaults_to_user(self, permission_app: Flask) -> None:
        captured_role = {}

        @permission_app.route("/test/capture-default-role")
        def capture_default_role() -> dict[str, str]:
            captured_role["role"] = g.user_role
            return {"role": g.user_role}

        with permission_app.test_client() as client:
            resp = client.get("/test/capture-default-role")
            assert resp.status_code == 200
            assert resp.get_json()["role"] == "user"
            assert captured_role["role"] == "user"


class TestXBeeperRoleHeader:
    """AC2: X-Beeper-Role header sets role in development mode."""

    def test_header_sets_admin_role(self, permission_app: Flask) -> None:
        with permission_app.test_client() as client:
            resp = client.get("/test/admin-only", headers={"X-Beeper-Role": "admin"})
            assert resp.status_code == 200

    def test_header_sets_user_role(self, permission_app: Flask) -> None:
        with permission_app.test_client() as client:
            resp = client.get("/test/user-route", headers={"X-Beeper-Role": "user"})
            assert resp.status_code == 200

    def test_invalid_header_value_defaults_to_user(self, permission_app: Flask) -> None:
        with permission_app.test_client() as client:
            resp = client.get("/test/admin-only", headers={"X-Beeper-Role": "superadmin"})
            assert resp.status_code == 403


class TestXBeeperRoleHeaderRefusedInProduction:
    """Task 6.2a / ADR 0001 §0(a) item 3: `X-Beeper-Role` is a trivially
    spoofable identity source (§0(a) — any HTTP client can set it directly)
    and must be refused under production config, while staying honored in
    development/testing (see `TestXBeeperRoleHeader` above, unchanged).

    Consequence, documented per the plan's requirement: with the header
    refused and no verified identity source yet (Task 6.2b, blocked on plan
    Q11), production has NO path to the "admin" role at all — every
    `@require_role("admin")` route resolves to 403 for every caller there
    until 6.2b ships. This is the intended fail-closed behavior.
    """

    def test_header_does_not_grant_admin_in_production(
        self, production_permission_app: Flask
    ) -> None:
        with production_permission_app.test_client() as client:
            resp = client.get("/test/admin-only", headers={"X-Beeper-Role": "admin"})
            # Header is ignored under ProductionConfig — falls through to the
            # default "user" role, which the admin-gated route rejects.
            assert resp.status_code == 403

    def test_header_user_value_also_ignored_in_production(
        self, production_permission_app: Flask
    ) -> None:
        with production_permission_app.test_client() as client:
            resp = client.get("/test/admin-only", headers={"X-Beeper-Role": "user"})
            assert resp.status_code == 403

    def test_response_is_still_well_formed_rfc7807_in_production(
        self, production_permission_app: Flask
    ) -> None:
        """Refusing the header must not degrade into an opaque failure —
        the caller still gets the same well-formed 403 body as any other
        permission denial, not a mystery error."""
        with production_permission_app.test_client() as client:
            resp = client.get("/test/admin-only", headers={"X-Beeper-Role": "admin"})
            assert resp.content_type == "application/problem+json"
            data = resp.get_json()
            assert data["status"] == 403
            assert data["detail"] == "Admin role required to access this resource"

    def test_allow_role_header_class_attribute_is_false_on_production_config(self) -> None:
        assert ProductionConfig.ALLOW_ROLE_HEADER is False

    def test_allow_role_header_class_attribute_is_true_on_testing_config(self) -> None:
        assert TestingConfig.ALLOW_ROLE_HEADER is True

    def test_header_still_honored_under_development_config(self) -> None:
        """Explicit development-config coverage alongside the existing
        testing-config coverage in `TestXBeeperRoleHeader` — both
        non-production configs keep the header as a live affordance."""
        dev_app = create_app(DevelopmentConfig)

        @dev_app.route("/test/dev-admin-only")
        @require_role("admin")
        def dev_admin_only() -> dict[str, str]:
            return {"message": "admin access granted"}

        with dev_app.test_client() as client:
            resp = client.get("/test/dev-admin-only", headers={"X-Beeper-Role": "admin"})
            assert resp.status_code == 200


class TestGUserRoleAvailable:
    """AC2: g.user_role is available in request context."""

    def test_g_user_role_set_for_admin(self, permission_app: Flask) -> None:
        captured_role = {}

        @permission_app.route("/test/capture-role")
        def capture_role() -> dict[str, str]:
            captured_role["role"] = g.user_role
            return {"role": g.user_role}

        with permission_app.test_client() as client:
            resp = client.get("/test/capture-role", headers={"X-Beeper-Role": "admin"})
            assert resp.status_code == 200
            assert resp.get_json()["role"] == "admin"
            assert captured_role["role"] == "admin"

    def test_g_user_role_set_for_user(self, permission_app: Flask) -> None:
        captured_role = {}

        @permission_app.route("/test/capture-role-user")
        def capture_role_user() -> dict[str, str]:
            captured_role["role"] = g.user_role
            return {"role": g.user_role}

        with permission_app.test_client() as client:
            resp = client.get("/test/capture-role-user", headers={"X-Beeper-Role": "user"})
            assert resp.status_code == 200
            assert resp.get_json()["role"] == "user"
            assert captured_role["role"] == "user"

    def test_g_user_role_set_for_default(self, permission_app: Flask) -> None:
        captured_role = {}

        @permission_app.route("/test/capture-role-default")
        def capture_role_default() -> dict[str, str]:
            captured_role["role"] = g.user_role
            return {"role": g.user_role}

        with permission_app.test_client() as client:
            resp = client.get("/test/capture-role-default")
            assert resp.status_code == 200
            assert resp.get_json()["role"] == "user"
            assert captured_role["role"] == "user"


class TestRFC7807ErrorFormat:
    """AC1: RFC 7807 error response format validation."""

    def test_rfc7807_has_all_required_fields(self, permission_app: Flask) -> None:
        with permission_app.test_client() as client:
            resp = client.get("/test/admin-only")
            data = resp.get_json()
            required_fields = {"type", "title", "status", "detail", "instance"}
            assert required_fields.issubset(set(data.keys()))

    def test_rfc7807_type_is_uri(self, permission_app: Flask) -> None:
        with permission_app.test_client() as client:
            resp = client.get("/test/admin-only")
            data = resp.get_json()
            assert data["type"].startswith("https://")

    def test_rfc7807_status_matches_http_status(self, permission_app: Flask) -> None:
        with permission_app.test_client() as client:
            resp = client.get("/test/admin-only")
            data = resp.get_json()
            assert data["status"] == resp.status_code == 403

    def test_rfc7807_instance_matches_request_path(self, permission_app: Flask) -> None:
        with permission_app.test_client() as client:
            resp = client.get("/test/admin-only")
            data = resp.get_json()
            assert data["instance"] == "/test/admin-only"


class TestBearerTokensNeverGrantRoles:
    """Task 8.2 / ADR 0002 §7 CRITICAL-1 — permanent regression guard.

    `_extract_role_from_k8s_token` and its call site are DELETED
    unconditionally, in every mode (not gated behind `ALLOW_ROLE_HEADER`,
    not gated behind any auth mode). Before this fix, the unverified
    `groups` claim of a Bearer JWT's payload was read FIRST, ungated, on
    every request — so a crafted 3-segment base64 token carrying exactly
    `{"groups": ["beeper-admin"]}` granted "admin" in **production**, today,
    defeating Task 6.2a's fail-closed guarantee entirely (the header refusal
    below it never even ran).

    This class is the named replacement for the deleted
    `TestK8sTokenRoleResolution` (recorded per ADR 0002 §7's "deleted with
    named replacements" requirement) — old name -> new name(s):

    - test_k8s_token_with_beeper_admin_group
        -> test_admin_bypass_payload_is_ignored_in_testing,
           test_admin_bypass_payload_is_ignored_in_production
    - test_k8s_token_without_admin_group_defaults_to_user
        -> test_non_admin_groups_payload_is_ignored
    - test_k8s_token_takes_precedence_over_header
        -> test_bearer_token_never_overrides_x_beeper_role_header
    - test_invalid_jwt_format_falls_through
        -> test_not_a_jwt_is_ignored
    - test_k8s_non_admin_token_blocks_header_bypass
        -> test_bearer_token_cannot_grant_admin_even_with_admin_header_absent
    - test_malformed_jwt_payload_falls_through
        -> test_malformed_base64_payload_is_ignored
    - test_crafted_jwt_with_non_object_payload_does_not_crash
        -> test_non_object_payload_does_not_crash_in_testing,
           test_non_object_payload_does_not_crash_in_production
    - test_crafted_jwt_does_not_crash_other_routes_either
        -> test_non_object_payload_does_not_crash_other_routes

    Every payload proven inert here is proven inert in BOTH a non-production
    config (`TestingConfig`, `ALLOW_ROLE_HEADER=True`, via `permission_app`)
    and `ProductionConfig` (via `production_permission_app`) — the whole
    point of this hotfix is that the Bearer path never mattered which mode
    was active.
    """

    def test_admin_bypass_payload_is_ignored_in_testing(self, permission_app: Flask) -> None:
        """The EXACT old bypass payload: {"groups": ["beeper-admin"]}."""
        token = _make_bearer_token(["beeper-admin"])
        with permission_app.test_client() as client:
            resp = client.get(
                "/test/admin-only",
                headers={"Authorization": f"Bearer {token}"},
            )
            # No X-Beeper-Role header either -> falls to default "user".
            assert resp.status_code == 403

    def test_admin_bypass_payload_is_ignored_in_production(
        self, production_permission_app: Flask
    ) -> None:
        """CRITICAL-1: this exact payload granted admin in production before
        Task 8.2 landed. It must never do so again, in any mode."""
        token = _make_bearer_token(["beeper-admin"])
        with production_permission_app.test_client() as client:
            resp = client.get(
                "/test/admin-only",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403

    def test_non_admin_groups_payload_is_ignored(self, permission_app: Flask) -> None:
        token = _make_bearer_token(["beeper-user"])
        with permission_app.test_client() as client:
            resp = client.get(
                "/test/admin-only",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403

    def test_empty_groups_payload_is_ignored(self, permission_app: Flask) -> None:
        token = _make_bearer_token([])
        with permission_app.test_client() as client:
            resp = client.get(
                "/test/admin-only",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403

    def test_bearer_token_never_overrides_x_beeper_role_header(
        self, permission_app: Flask
    ) -> None:
        """A Bearer token can no longer take precedence over anything — it
        is simply never read. The header (dev/testing only) is the sole
        decider here, so an admin-claiming token alongside a `user` header
        must still land on "user" (the header wins because the token is
        inert, not because the token "loses" to it)."""
        token = _make_bearer_token(["beeper-admin"])
        with permission_app.test_client() as client:
            resp = client.get(
                "/test/admin-only",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Beeper-Role": "user",
                },
            )
            assert resp.status_code == 403

    def test_bearer_token_cannot_grant_admin_even_with_admin_header_absent(
        self, permission_app: Flask
    ) -> None:
        """Security: a non-admin-groups token combined with an `admin`
        header must resolve via the header (dev/testing affordance), not be
        blocked by stale token-precedence logic — proving the token plays
        no role in the decision at all, positive or negative."""
        token = _make_bearer_token(["beeper-user"])
        with permission_app.test_client() as client:
            resp = client.get(
                "/test/admin-only",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Beeper-Role": "admin",
                },
            )
            # Header grants admin (Task 6.2a affordance); the token, whatever
            # it claims, is never consulted.
            assert resp.status_code == 200

    def test_not_a_jwt_is_ignored(self, permission_app: Flask) -> None:
        with permission_app.test_client() as client:
            resp = client.get(
                "/test/admin-only",
                headers={"Authorization": "Bearer not-a-jwt"},
            )
            assert resp.status_code == 403

    def test_malformed_base64_payload_is_ignored(self, permission_app: Flask) -> None:
        token = "eyJhbGciOiJSUzI1NiJ9.!!!invalid!!!.fake"
        with permission_app.test_client() as client:
            resp = client.get(
                "/test/admin-only",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403

    def test_non_object_payload_does_not_crash_in_testing(
        self, permission_app: Flask
    ) -> None:
        """Regression input retained (originally Task 6.2a): `x.MTIz.y` —
        "MTIz" is `base64.urlsafe_b64encode(b"123")`, so a JSON parse of the
        payload segment used to return the integer 123, and the old
        `claims.get("groups", [])` raised an uncaught AttributeError (an int
        has no `.get`), 500ing every route. The Bearer path is deleted
        entirely now (Task 8.2) — there is nothing left to parse or crash —
        so this proves the token is inert, not merely crash-proofed.
        """
        with permission_app.test_client() as client:
            resp = client.get(
                "/test/admin-only",
                headers={"Authorization": "Bearer x.MTIz.y"},
            )
            assert resp.status_code != 500
            assert resp.status_code == 403

    def test_non_object_payload_does_not_crash_in_production(
        self, production_permission_app: Flask
    ) -> None:
        with production_permission_app.test_client() as client:
            resp = client.get(
                "/test/admin-only",
                headers={"Authorization": "Bearer x.MTIz.y"},
            )
            assert resp.status_code != 500
            assert resp.status_code == 403

    def test_non_object_payload_does_not_crash_other_routes(
        self, permission_app: Flask
    ) -> None:
        """The old bug was in `before_request`, which runs for every route —
        confirm an unrelated, unprotected route survives the same header
        too, not just the admin-gated one above."""
        with permission_app.test_client() as client:
            resp = client.get(
                "/test/unprotected",
                headers={"Authorization": "Bearer x.MTIz.y"},
            )
            assert resp.status_code == 200

    def test_g_user_role_is_default_user_with_admin_bypass_token_present(
        self, permission_app: Flask
    ) -> None:
        """Direct assertion on `g.user_role` (not just the 403 it causes):
        proves the resolved role itself is "user", never "admin", with the
        bypass payload present and no header to fall back on."""
        captured_role: dict[str, str] = {}

        @permission_app.route("/test/capture-role-with-bearer-token")
        def capture_role_with_bearer_token() -> dict[str, str]:
            captured_role["role"] = g.user_role
            return {"role": g.user_role}

        token = _make_bearer_token(["beeper-admin"])
        with permission_app.test_client() as client:
            resp = client.get(
                "/test/capture-role-with-bearer-token",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            assert captured_role["role"] == "user"

    def test_bearer_token_ignored_in_development_config_too(self) -> None:
        """The deletion is unconditional across ALL modes, not just
        Testing/Production — explicit `DevelopmentConfig` coverage alongside
        the two above (mirrors `TestXBeeperRoleHeaderRefusedInProduction
        .test_header_still_honored_under_development_config`)."""
        dev_app = create_app(DevelopmentConfig)

        @dev_app.route("/test/dev-admin-only-bearer")
        @require_role("admin")
        def dev_admin_only_bearer() -> dict[str, str]:
            return {"message": "admin access granted"}

        token = _make_bearer_token(["beeper-admin"])
        with dev_app.test_client() as client:
            resp = client.get(
                "/test/dev-admin-only-bearer",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403


class TestRequireRoleValidation:
    """require_role() validates the role argument at decoration time."""

    def test_invalid_role_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid role"):
            @require_role("superadmin")
            def bad_route() -> dict[str, str]:
                return {"message": "should not reach"}

    def test_capitalized_role_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid role"):
            @require_role("Admin")
            def bad_route() -> dict[str, str]:
                return {"message": "should not reach"}


class TestExistingRoutesAccessible:
    """AC3: All existing routes remain accessible without role header."""

    def test_root_accessible(self, client: FlaskClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200

    def test_health_accessible(self, client: FlaskClient) -> None:
        resp = client.get("/health/")
        assert resp.status_code == 200


class TestPermissionLogging:
    """Verify structured logging on permission denial."""

    def test_denial_logs_warning(
        self, permission_app: Flask, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        with caplog.at_level(logging.WARNING):
            with permission_app.test_client() as client:
                client.get("/test/admin-only", headers={"X-Beeper-Role": "user"})
        assert "Permission denied" in caplog.text


class TestGetConfigFailSafeFallback:
    """Task 8.2 / ADR 0002 §8, FR54: `get_config()`'s environment-variable
    resolution must fail SAFE, not open — distinguishing an *absent*
    `FLASK_ENV` (local-dev ergonomics, stays `DevelopmentConfig`) from a
    *present but unrecognized* value (a misconfiguration, now fails closed
    to `ProductionConfig` instead of silently granting the permissive
    dev config)."""

    def test_absent_flask_env_defaults_to_development(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FLASK_ENV", raising=False)
        assert get_config() is DevelopmentConfig

    def test_flask_env_development_maps_to_development_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FLASK_ENV", "development")
        assert get_config() is DevelopmentConfig

    def test_flask_env_testing_maps_to_testing_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FLASK_ENV", "testing")
        assert get_config() is TestingConfig

    def test_flask_env_production_maps_to_production_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FLASK_ENV", "production")
        assert get_config() is ProductionConfig

    def test_unrecognized_flask_env_fails_closed_to_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The core hotfix assertion: a typo like `produciton` (or any other
        unrecognized string) must NOT silently resolve to the permissive
        `DevelopmentConfig` — it must fail closed to `ProductionConfig`."""
        monkeypatch.setenv("FLASK_ENV", "produciton")
        assert get_config() is ProductionConfig

    def test_empty_string_flask_env_fails_closed_to_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty string is *present* (distinct from unset), so it must
        take the unrecognized-value path, not the absent-value path."""
        monkeypatch.setenv("FLASK_ENV", "")
        assert get_config() is ProductionConfig

    def test_unrecognized_flask_env_does_not_grant_role_header_in_practice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end proof that the fallback actually closes the hole: an
        app built from the unrecognized-env config must refuse
        `X-Beeper-Role` exactly like an explicit `ProductionConfig` app."""
        monkeypatch.setenv("FLASK_ENV", "bogus")
        config_class = get_config()
        app = create_app(config_class)

        @app.route("/test/unrecognized-env-admin-only")
        @require_role("admin")
        def unrecognized_env_admin_only() -> dict[str, str]:
            return {"message": "admin access granted"}

        with app.test_client() as client:
            resp = client.get(
                "/test/unrecognized-env-admin-only",
                headers={"X-Beeper-Role": "admin"},
            )
            assert resp.status_code == 403
