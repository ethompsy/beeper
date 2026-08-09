"""Tests for `GET /auth/login` (Task 8.5 — ADR 0002 §2/§3).

Covers: authorization-URL construction (client_id/response_type/scope/
redirect_uri/state/nonce present), safe-`next` validation (parametrized —
"[T] open-redirect attempts ... rejected"), and that `state`/`nonce`/`next`
are stored server-side (session), never leaked into the IdP-facing URL.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
import responses
from flask import Flask

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig
from tests._stub_oidc_idp import AUTHORIZATION_ENDPOINT, CLIENT_ID, StubIdP


class _OidcConfig(TestingConfig):
    BEEPER_AUTH_MODE = "oidc"
    BEEPER_OIDC_ISSUER = "https://idp.example.com"
    BEEPER_OIDC_CLIENT_ID = CLIENT_ID
    BEEPER_OIDC_CLIENT_SECRET = "test-client-secret"
    BEEPER_EXTERNAL_SCHEME = "http"


@pytest.fixture(autouse=True)
def _secret_key_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-for-oidc-login-tests")
    yield


@pytest.fixture
def app(_secret_key_env: None) -> Flask:
    return create_app(_OidcConfig)


@pytest.fixture
def stub_idp() -> StubIdP:
    return StubIdP()


def _register_discovery_only(rsps: responses.RequestsMock, stub_idp: StubIdP) -> None:
    from tests._stub_oidc_idp import DISCOVERY_URL

    rsps.add("GET", DISCOVERY_URL, json=stub_idp.discovery_document(), status=200)


class TestAuthorizationUrl:
    def test_redirects_to_authorization_endpoint(self, app: Flask, stub_idp: StubIdP) -> None:
        with responses.RequestsMock() as rsps:
            _register_discovery_only(rsps, stub_idp)
            with app.test_client() as client:
                resp = client.get("/auth/login")
        assert resp.status_code == 302
        assert resp.headers["Location"].startswith(AUTHORIZATION_ENDPOINT)

    def test_authorization_url_has_required_params(self, app: Flask, stub_idp: StubIdP) -> None:
        with responses.RequestsMock() as rsps:
            _register_discovery_only(rsps, stub_idp)
            with app.test_client() as client:
                resp = client.get("/auth/login")
        params = parse_qs(urlsplit(resp.headers["Location"]).query)
        assert params["client_id"] == [CLIENT_ID]
        assert params["response_type"] == ["code"]
        assert "state" in params
        assert "nonce" in params
        assert "openid" in params["scope"][0]

    def test_redirect_uri_derived_from_request_host_when_unconfigured(
        self, app: Flask, stub_idp: StubIdP
    ) -> None:
        with responses.RequestsMock() as rsps:
            _register_discovery_only(rsps, stub_idp)
            with app.test_client() as client:
                resp = client.get("/auth/login", base_url="http://ui.example.test")
        params = parse_qs(urlsplit(resp.headers["Location"]).query)
        assert params["redirect_uri"] == ["http://ui.example.test/auth/callback"]

    def test_explicit_redirect_url_config_wins(
        self, _secret_key_env: None, stub_idp: StubIdP
    ) -> None:
        class _ExplicitRedirectConfig(_OidcConfig):
            BEEPER_OIDC_REDIRECT_URL = "https://public.example.com/auth/callback"

        app = create_app(_ExplicitRedirectConfig)
        with responses.RequestsMock() as rsps:
            _register_discovery_only(rsps, stub_idp)
            with app.test_client() as client:
                resp = client.get("/auth/login")
        params = parse_qs(urlsplit(resp.headers["Location"]).query)
        assert params["redirect_uri"] == ["https://public.example.com/auth/callback"]

    def test_state_and_nonce_stored_server_side_not_leaked_as_next_param(
        self, app: Flask, stub_idp: StubIdP
    ) -> None:
        """`next` must never appear in the IdP-facing authorization URL
        (module docstring: leaking an internal path to a third party) —
        it's stored in the session, correlated with `state`."""
        with responses.RequestsMock() as rsps:
            _register_discovery_only(rsps, stub_idp)
            with app.test_client() as client:
                resp = client.get("/auth/login?next=/app/investigations/inv-1")
                params = parse_qs(urlsplit(resp.headers["Location"]).query)
                assert "next" not in params
                with client.session_transaction() as sess:
                    state_keys = [k for k in sess if k.startswith("_state_oidc_")]
                    assert len(state_keys) == 1
                    assert sess[state_keys[0]]["data"]["next"] == "/app/investigations/inv-1"
                    assert sess[state_keys[0]]["data"]["nonce"] == params["nonce"][0]


class TestSafeNextValidation:
    """`[T]` open-redirect attempts rejected; `/app/...` (+query/hash)
    accepted. Table-driven over the session-stored `next` value."""

    @pytest.mark.parametrize(
        "raw_next",
        [
            "https://evil.example.com",
            "http://evil.example.com/app",
            "//evil.example.com",
            "//evil.example.com/app",
            "/\\evil.example.com",
            "\\\\evil.example.com",
            "https:evil.example.com",
            "/appevil.example.com",  # prefix-match bypass attempt
            "/other/path",
            "",
            "javascript:alert(1)",
        ],
    )
    def test_unsafe_next_falls_back_to_default(
        self, app: Flask, stub_idp: StubIdP, raw_next: str
    ) -> None:
        with responses.RequestsMock() as rsps:
            _register_discovery_only(rsps, stub_idp)
            with app.test_client() as client:
                client.get("/auth/login", query_string={"next": raw_next})
                with client.session_transaction() as sess:
                    state_keys = [k for k in sess if k.startswith("_state_oidc_")]
                    assert sess[state_keys[0]]["data"]["next"] == "/app"

    @pytest.mark.parametrize(
        "raw_next,expected",
        [
            ("/app", "/app"),
            ("/app/", "/app/"),
            ("/app/investigations/inv-1", "/app/investigations/inv-1"),
            ("/app/investigations?tab=timeline", "/app/investigations?tab=timeline"),
            ("/app/investigations#section", "/app/investigations#section"),
        ],
    )
    def test_safe_next_preserved_exactly(
        self, app: Flask, stub_idp: StubIdP, raw_next: str, expected: str
    ) -> None:
        with responses.RequestsMock() as rsps:
            _register_discovery_only(rsps, stub_idp)
            with app.test_client() as client:
                client.get("/auth/login", query_string={"next": raw_next})
                with client.session_transaction() as sess:
                    state_keys = [k for k in sess if k.startswith("_state_oidc_")]
                    assert sess[state_keys[0]]["data"]["next"] == expected

    def test_no_next_param_defaults_to_app(self, app: Flask, stub_idp: StubIdP) -> None:
        with responses.RequestsMock() as rsps:
            _register_discovery_only(rsps, stub_idp)
            with app.test_client() as client:
                client.get("/auth/login")
                with client.session_transaction() as sess:
                    state_keys = [k for k in sess if k.startswith("_state_oidc_")]
                    assert sess[state_keys[0]]["data"]["next"] == "/app"

    def test_encoded_variant_open_redirect_rejected(
        self, app: Flask, stub_idp: StubIdP
    ) -> None:
        """A `next` value that arrives ALREADY percent-encoded in the raw
        query string (e.g. built by a caller other than this app's own
        `urlencode()` — the AC's "encoded variants" case): after Flask's
        own single decode of the query string, `%2F%2Fevil.example.com`
        becomes `//evil.example.com`, which `_validate_safe_next()` then
        rejects as protocol-relative."""
        with responses.RequestsMock() as rsps:
            _register_discovery_only(rsps, stub_idp)
            with app.test_client() as client:
                client.get("/auth/login?next=%2F%2Fevil.example.com")
                with client.session_transaction() as sess:
                    state_keys = [k for k in sess if k.startswith("_state_oidc_")]
                    assert sess[state_keys[0]]["data"]["next"] == "/app"

    def test_doubly_encoded_app_path_still_accepted(
        self, app: Flask, stub_idp: StubIdP
    ) -> None:
        """A `next=/app%2Finvestigations` value — `/app` already literal,
        the rest percent-encoded — decodes once to a safe `/app/...` path
        and is accepted."""
        with responses.RequestsMock() as rsps:
            _register_discovery_only(rsps, stub_idp)
            with app.test_client() as client:
                client.get("/auth/login?next=/app%2Finvestigations")
                with client.session_transaction() as sess:
                    state_keys = [k for k in sess if k.startswith("_state_oidc_")]
                    assert sess[state_keys[0]]["data"]["next"] == "/app/investigations"
