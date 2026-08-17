"""Tests for `POST /auth/logout` (Task 8.5 — ADR 0002 §2/§3).

Covers: self-enforced CSRF (this route is exempt from the shared
`before_request` gate — ADR §2 — so it must check
`same_origin_request()` itself), local session clearing, and the
RP-initiated-logout decision (`_build_rp_initiated_logout_url()` — see
`oidc_auth.py`'s module docstring and this task's report for the full
`id_token_hint` caveat).
"""

from __future__ import annotations

import time

import pytest
import responses
from flask import Flask

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig
from tests._stub_oidc_idp import CLIENT_ID, DISCOVERY_URL, END_SESSION_ENDPOINT, ISSUER, StubIdP


class _OidcConfig(TestingConfig):
    BEEPER_AUTH_MODE = "oidc"
    BEEPER_OIDC_ISSUER = ISSUER
    BEEPER_OIDC_CLIENT_ID = CLIENT_ID
    BEEPER_OIDC_CLIENT_SECRET = "test-client-secret"
    BEEPER_EXTERNAL_SCHEME = "http"


@pytest.fixture(autouse=True)
def _secret_key_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-for-oidc-logout-tests")
    yield


@pytest.fixture
def app(_secret_key_env: None) -> Flask:
    return create_app(_OidcConfig)


@pytest.fixture
def stub_idp() -> StubIdP:
    return StubIdP()


def _seed_session(client, *, sub: str = "user-1") -> None:
    now = time.time()
    with client.session_transaction() as sess:
        sess["identity"] = {
            "sub": sub,
            "email": f"{sub}@corp.example.com",
            "email_lc": f"{sub}@corp.example.com",
            "external_id": sub,
            "name": "Test User",
            "role_snapshot": "user",
            "iat": now,
            "exp": now + 8 * 3600,
        }


SAME_ORIGIN = "http://localhost"


class TestCsrfEnforcement:
    def test_missing_origin_and_referer_rejected(self, app: Flask) -> None:
        with app.test_client() as client:
            _seed_session(client)
            resp = client.post("/auth/logout")
        assert resp.status_code == 403
        body = resp.get_json()
        assert body["type"] == "https://beeper.dev/errors/csrf-rejected"
        with client.session_transaction() as sess:
            assert "identity" in sess  # session NOT cleared on a rejected request

    def test_cross_origin_request_rejected(self, app: Flask) -> None:
        with app.test_client() as client:
            _seed_session(client)
            resp = client.post(
                "/auth/logout", headers={"Origin": "https://evil.example.com"}
            )
        assert resp.status_code == 403
        with client.session_transaction() as sess:
            assert "identity" in sess

    def test_wrong_scheme_same_host_rejected(self, app: Flask) -> None:
        """`BEEPER_EXTERNAL_SCHEME=http` here; an `https://localhost` Origin
        on an otherwise-matching host must still be rejected (ADR §2: scheme
        AND host both compared)."""
        with app.test_client() as client:
            _seed_session(client)
            resp = client.post("/auth/logout", headers={"Origin": "https://localhost"})
        assert resp.status_code == 403

    def test_same_origin_request_succeeds(self, app: Flask) -> None:
        with app.test_client() as client:
            _seed_session(client)
            resp = client.post("/auth/logout", headers={"Origin": SAME_ORIGIN})
        assert resp.status_code == 200

    def test_same_origin_via_referer_fallback_succeeds(self, app: Flask) -> None:
        with app.test_client() as client:
            _seed_session(client)
            resp = client.post(
                "/auth/logout", headers={"Referer": f"{SAME_ORIGIN}/app/settings"}
            )
        assert resp.status_code == 200


class TestSessionClearing:
    def test_clears_the_session(self, app: Flask) -> None:
        with app.test_client() as client:
            _seed_session(client)
            client.post("/auth/logout", headers={"Origin": SAME_ORIGIN})
            with client.session_transaction() as sess:
                assert "identity" not in sess

    def test_idempotent_with_no_prior_session(self, app: Flask) -> None:
        with app.test_client() as client:
            resp = client.post("/auth/logout", headers={"Origin": SAME_ORIGIN})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["logged_out"] is True

    def test_response_shape(self, app: Flask) -> None:
        with app.test_client() as client:
            _seed_session(client)
            resp = client.post("/auth/logout", headers={"Origin": SAME_ORIGIN})
        assert resp.get_json() == {"logged_out": True, "logout_url": None}


class TestRpInitiatedLogout:
    def test_logout_url_absent_when_not_configured(
        self, app: Flask, stub_idp: StubIdP
    ) -> None:
        """`BEEPER_OIDC_POST_LOGOUT_REDIRECT_URL` unset -> local-clear only,
        no network call at all (an unregistered `responses` mock would
        raise `ConnectionError` if the discovery endpoint were hit)."""
        with responses.RequestsMock(), app.test_client() as client:
            _seed_session(client)
            resp = client.post("/auth/logout", headers={"Origin": SAME_ORIGIN})
        assert resp.get_json()["logout_url"] is None

    def test_logout_url_present_when_configured_and_end_session_endpoint_declared(
        self, stub_idp: StubIdP
    ) -> None:
        class _WithPostLogoutConfig(_OidcConfig):
            BEEPER_OIDC_POST_LOGOUT_REDIRECT_URL = "https://ui.example.com/app/login"

        app = create_app(_WithPostLogoutConfig)
        with responses.RequestsMock() as rsps, app.test_client() as client:
            rsps.add("GET", DISCOVERY_URL, json=stub_idp.discovery_document(), status=200)
            _seed_session(client)
            resp = client.post("/auth/logout", headers={"Origin": SAME_ORIGIN})
        body = resp.get_json()
        assert body["logged_out"] is True
        assert body["logout_url"].startswith(END_SESSION_ENDPOINT)
        assert "post_logout_redirect_uri=" in body["logout_url"]
        # FR55: no id_token retained anywhere in this app -> no id_token_hint
        # can ever be included (see oidc_auth.py's module docstring).
        assert "id_token_hint" not in body["logout_url"]

    def test_logout_url_absent_when_configured_but_idp_lacks_end_session_endpoint(
        self, stub_idp: StubIdP
    ) -> None:
        class _WithPostLogoutConfig(_OidcConfig):
            BEEPER_OIDC_POST_LOGOUT_REDIRECT_URL = "https://ui.example.com/app/login"

        stub_idp.include_end_session_endpoint = False
        app = create_app(_WithPostLogoutConfig)
        with responses.RequestsMock() as rsps, app.test_client() as client:
            rsps.add("GET", DISCOVERY_URL, json=stub_idp.discovery_document(), status=200)
            _seed_session(client)
            resp = client.post("/auth/logout", headers={"Origin": SAME_ORIGIN})
        assert resp.get_json()["logout_url"] is None

    def test_discovery_failure_does_not_fail_the_logout(self) -> None:
        """Local session clear must never depend on IdP reachability — a
        discovery fetch error degrades to `logout_url: null`, not a 5xx."""

        class _WithPostLogoutConfig(_OidcConfig):
            BEEPER_OIDC_POST_LOGOUT_REDIRECT_URL = "https://ui.example.com/app/login"

        app = create_app(_WithPostLogoutConfig)
        with responses.RequestsMock() as rsps, app.test_client() as client:
            rsps.add("GET", DISCOVERY_URL, body=ConnectionError("idp unreachable"))
            _seed_session(client)
            resp = client.post("/auth/logout", headers={"Origin": SAME_ORIGIN})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["logged_out"] is True
        assert body["logout_url"] is None
        with client.session_transaction() as sess:
            assert "identity" not in sess
