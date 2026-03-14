"""Tests for permission middleware (Story 1.1: Permission Model Enforcement)."""

import base64
import json

import pytest
from flask import Flask, g
from flask.testing import FlaskClient

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig
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


def _make_k8s_token(groups: list[str]) -> str:
    """Create a fake JWT token with the given groups claim."""
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


class TestK8sTokenRoleResolution:
    """AC2: K8s ServiceAccount token resolves role."""

    def test_k8s_token_with_beeper_admin_group(self, permission_app: Flask) -> None:
        token = _make_k8s_token(["beeper-admin"])
        with permission_app.test_client() as client:
            resp = client.get(
                "/test/admin-only",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200

    def test_k8s_token_without_admin_group_defaults_to_user(self, permission_app: Flask) -> None:
        token = _make_k8s_token(["beeper-user"])
        with permission_app.test_client() as client:
            resp = client.get(
                "/test/admin-only",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403

    def test_k8s_token_takes_precedence_over_header(self, permission_app: Flask) -> None:
        token = _make_k8s_token(["beeper-admin"])
        with permission_app.test_client() as client:
            resp = client.get(
                "/test/admin-only",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Beeper-Role": "user",
                },
            )
            # Token should take precedence — admin role from token
            assert resp.status_code == 200

    def test_invalid_jwt_format_falls_through(self, permission_app: Flask) -> None:
        with permission_app.test_client() as client:
            resp = client.get(
                "/test/admin-only",
                headers={"Authorization": "Bearer not-a-jwt"},
            )
            # Invalid token → no role from token → falls to header → default "user"
            assert resp.status_code == 403

    def test_k8s_non_admin_token_blocks_header_bypass(self, permission_app: Flask) -> None:
        """Security: valid non-admin K8s token must NOT fall through to X-Beeper-Role header."""
        token = _make_k8s_token(["beeper-user"])
        with permission_app.test_client() as client:
            resp = client.get(
                "/test/admin-only",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Beeper-Role": "admin",
                },
            )
            # Token is authoritative — non-admin token means "user", header ignored
            assert resp.status_code == 403

    def test_malformed_jwt_payload_falls_through(self, permission_app: Flask) -> None:
        # Create a JWT with invalid base64 payload
        token = "eyJhbGciOiJSUzI1NiJ9.!!!invalid!!!.fake"
        with permission_app.test_client() as client:
            resp = client.get(
                "/test/admin-only",
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
