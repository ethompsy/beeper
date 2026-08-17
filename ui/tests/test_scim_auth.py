"""Bearer-auth matrix for `/scim/v2/*` (Task 8.8 — ADR 0002 §4/§8, FR58).

Covers: valid token 200; missing/wrong token 401 (SCIM error schema);
constant-time comparison actually used; dual-token zero-downtime rotation
(old+new both work mid-rotation); enabled-but-unconfigured fails closed
(403, naming the misconfiguration); disabled ⇒ blueprint unregistered
(404, indistinguishable from any other undefined path).
"""

from __future__ import annotations

import hmac

import pytest

from beeper_ui.routes import scim_helpers
from beeper_ui.services.identity_store import reset_identity_store
from tests._scim_helpers import (
    SCIM_TOKEN,
    SCIM_TOKEN_SECONDARY,
    ScimDisabledConfig,
    ScimDualTokenConfig,
    ScimTestConfig,
    ScimTokenlessConfig,
    auth_headers,
    build_scim_app,
)


@pytest.fixture(autouse=True)
def _secret_key_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-real-secret-for-scim-auth-tests")
    yield


@pytest.fixture(autouse=True)
def _reset_store():
    reset_identity_store()
    yield
    reset_identity_store()


class TestValidToken:
    def test_correct_bearer_token_succeeds(self) -> None:
        app, _store, _fake = build_scim_app(ScimTestConfig)
        client = app.test_client()
        resp = client.get("/scim/v2/Users", headers=auth_headers(SCIM_TOKEN))
        assert resp.status_code == 200


class TestMissingOrWrongToken:
    def test_no_authorization_header_401(self) -> None:
        app, _store, _fake = build_scim_app(ScimTestConfig)
        client = app.test_client()
        resp = client.get("/scim/v2/Users")
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:Error"]
        assert body["status"] == "401"

    def test_malformed_authorization_header_401(self) -> None:
        app, _store, _fake = build_scim_app(ScimTestConfig)
        client = app.test_client()
        resp = client.get("/scim/v2/Users", headers={"Authorization": "Basic abc123"})
        assert resp.status_code == 401

    def test_empty_bearer_value_401(self) -> None:
        app, _store, _fake = build_scim_app(ScimTestConfig)
        client = app.test_client()
        resp = client.get("/scim/v2/Users", headers={"Authorization": "Bearer "})
        assert resp.status_code == 401

    def test_wrong_token_401(self) -> None:
        app, _store, _fake = build_scim_app(ScimTestConfig)
        client = app.test_client()
        resp = client.get("/scim/v2/Users", headers=auth_headers("totally-wrong-token"))
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:Error"]

    def test_response_content_type_is_scim(self) -> None:
        app, _store, _fake = build_scim_app(ScimTestConfig)
        client = app.test_client()
        resp = client.get("/scim/v2/Users")
        assert resp.content_type.startswith("application/scim+json")


class TestConstantTimeComparison:
    def test_compare_digest_is_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Proves the token-match path routes through
        `hmac.compare_digest` rather than a plain `==` — a spy wraps the
        real function (still returns a correct result) so this stays a
        behavioral proof, not just a mock-call assertion."""
        calls: list[tuple[bytes, bytes]] = []
        real_compare_digest = hmac.compare_digest

        def _spy(a: bytes, b: bytes) -> bool:
            calls.append((a, b))
            return real_compare_digest(a, b)

        monkeypatch.setattr(scim_helpers.hmac, "compare_digest", _spy)

        app, _store, _fake = build_scim_app(ScimTestConfig)
        client = app.test_client()
        resp = client.get("/scim/v2/Users", headers=auth_headers(SCIM_TOKEN))
        assert resp.status_code == 200
        assert len(calls) >= 1, "expected hmac.compare_digest to be used for token comparison"


class TestDualTokenRotation:
    def test_primary_token_works_during_rotation(self) -> None:
        app, _store, _fake = build_scim_app(ScimDualTokenConfig)
        client = app.test_client()
        resp = client.get("/scim/v2/Users", headers=auth_headers(SCIM_TOKEN))
        assert resp.status_code == 200

    def test_secondary_token_works_during_rotation(self) -> None:
        app, _store, _fake = build_scim_app(ScimDualTokenConfig)
        client = app.test_client()
        resp = client.get("/scim/v2/Users", headers=auth_headers(SCIM_TOKEN_SECONDARY))
        assert resp.status_code == 200

    def test_a_third_unrelated_token_still_401s(self) -> None:
        app, _store, _fake = build_scim_app(ScimDualTokenConfig)
        client = app.test_client()
        resp = client.get("/scim/v2/Users", headers=auth_headers("neither-of-the-two"))
        assert resp.status_code == 401


class TestEnabledButUnconfigured:
    def test_every_request_403s_when_no_token_configured(self) -> None:
        app, _store, _fake = build_scim_app(ScimTokenlessConfig)
        client = app.test_client()
        # Even with NO Authorization header at all — this is a
        # configuration failure, not a missing-credential 401.
        resp = client.get("/scim/v2/Users")
        assert resp.status_code == 403
        body = resp.get_json()
        assert body["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:Error"]
        assert "no bearer token is configured" in body["detail"]

    def test_403_even_with_a_bearer_header_present(self) -> None:
        """Presenting SOME bearer value doesn't help — there is no correct
        answer until an operator configures a token (ADR §8: never a
        401-retry-with-different-credentials story)."""
        app, _store, _fake = build_scim_app(ScimTokenlessConfig)
        client = app.test_client()
        resp = client.get("/scim/v2/Users", headers=auth_headers("anything-at-all"))
        assert resp.status_code == 403

    def test_write_routes_also_403(self) -> None:
        app, _store, _fake = build_scim_app(ScimTokenlessConfig)
        client = app.test_client()
        resp = client.post("/scim/v2/Users", json={"userName": "x", "externalId": "e1"})
        assert resp.status_code == 403


class TestDisabledBlueprintUnregistered:
    def test_scim_disabled_returns_plain_404(self) -> None:
        app, _store, _fake = build_scim_app(ScimDisabledConfig)
        client = app.test_client()
        resp = client.get("/scim/v2/Users", headers=auth_headers(SCIM_TOKEN))
        assert resp.status_code == 404
        # Plain Flask 404 — NOT the SCIM error schema, since the blueprint
        # was never registered at all (ADR §1: "never a fingerprintable
        # surface" — indistinguishable from any other undefined path).
        assert resp.content_type != "application/scim+json"

    def test_scim_disabled_service_provider_config_also_404s(self) -> None:
        app, _store, _fake = build_scim_app(ScimDisabledConfig)
        client = app.test_client()
        resp = client.get("/scim/v2/ServiceProviderConfig", headers=auth_headers(SCIM_TOKEN))
        assert resp.status_code == 404
