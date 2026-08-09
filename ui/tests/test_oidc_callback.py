"""Tests for `GET /auth/callback` (Task 8.5 — ADR 0002 §3/§5.2/§7, FR55/FR56).

The core of this task's AC list: full ID-token validation (each failure
class parametrized), FR56 groups→role mapping (incl. UserInfo fallback and
the SCIM-on/off split), tokens-never-persisted, and the cold-permalink
login round trip (FR53/NFR24).

Every test drives a REAL `GET /auth/login` first (same Flask test client,
cookies preserved) to get a genuine `state`/`nonce` pair out of Authlib's
own state machinery, then stubs the IdP's JWKS/token[/userinfo] endpoints
via `responses` and drives `GET /auth/callback` — an actual code-flow
round trip, not a shortcut that hand-seeds session state.
"""

from __future__ import annotations

import time
from urllib.parse import parse_qs, urlsplit

import pytest
import responses
from flask import Flask
from joserfc import jwt as jose_jwt
from joserfc.jwk import OctKey

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig
from tests._stub_oidc_idp import (
    CLIENT_ID,
    DISCOVERY_URL,
    ISSUER,
    ROTATED_KID,
    StubIdP,
)


class _OidcConfig(TestingConfig):
    BEEPER_AUTH_MODE = "oidc"
    BEEPER_OIDC_ISSUER = ISSUER
    BEEPER_OIDC_CLIENT_ID = CLIENT_ID
    BEEPER_OIDC_CLIENT_SECRET = "test-client-secret"
    BEEPER_EXTERNAL_SCHEME = "http"


class _OidcScimConfig(_OidcConfig):
    BEEPER_SCIM_ENABLED = True


class _OidcUserGroupsConfig(_OidcConfig):
    BEEPER_USER_GROUPS = "Employees"


@pytest.fixture(autouse=True)
def _secret_key_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-for-oidc-callback-tests")
    yield


@pytest.fixture
def app(_secret_key_env: None) -> Flask:
    return create_app(_OidcConfig)


@pytest.fixture
def stub_idp() -> StubIdP:
    return StubIdP()


def _mock() -> responses.RequestsMock:
    # `assert_all_requests_are_fired=False`: discovery is cached on the app's
    # OIDC client after `login()`'s fetch, so `callback()`'s own
    # `load_server_metadata()` call never re-hits the network — a second
    # registered discovery response (if any) legitimately goes unused.
    return responses.RequestsMock(assert_all_requests_are_fired=False)


def _do_login(
    client, rsps: responses.RequestsMock, stub_idp: StubIdP, *, next_path: str = "/app"
) -> tuple[str, str]:
    """Drives `GET /auth/login`, returns `(state, nonce)` from Authlib's
    own real state/nonce generation."""
    rsps.add("GET", DISCOVERY_URL, json=stub_idp.discovery_document(), status=200)
    resp = client.get("/auth/login", query_string={"next": next_path})
    assert resp.status_code == 302
    params = parse_qs(urlsplit(resp.headers["Location"]).query)
    state = params["state"][0]
    with client.session_transaction() as sess:
        nonce = sess[f"_state_oidc_{state}"]["data"]["nonce"]
    return state, nonce


def _callback(client, state: str, *, code: str = "test-code"):
    return client.get("/auth/callback", query_string={"code": code, "state": state})


def _assert_no_session(client) -> None:
    with client.session_transaction() as sess:
        assert "identity" not in sess


# ---------------------------------------------------------------------------
# [T] Full valid login
# ---------------------------------------------------------------------------


class TestValidLogin:
    def test_establishes_session_with_expected_identity(
        self, app: Flask, stub_idp: StubIdP
    ) -> None:
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(
                rsps,
                id_token_kwargs={
                    "nonce": nonce,
                    "extra_claims": {
                        "email": "alice@corp.example.com",
                        "name": "Alice Example",
                        "groups": ["Admins"],
                    },
                },
            )
            resp = _callback(client, state)
        assert resp.status_code == 302
        with client.session_transaction() as sess:
            identity = sess["identity"]
        assert identity["sub"] == "user-1"
        assert identity["email"] == "alice@corp.example.com"
        assert identity["email_lc"] == "alice@corp.example.com"
        assert identity["name"] == "Alice Example"
        assert identity["role_snapshot"] == "admin"
        assert identity["external_id"] == "user-1"  # no `oid` claim -> falls back to `sub`

    def test_cold_permalink_round_trips_to_exact_next(
        self, app: Flask, stub_idp: StubIdP
    ) -> None:
        """`[T]` cold permalink logged-out -> login -> identical view
        (FR53/NFR24)."""
        next_path = "/app/investigations/inv-77?tab=timeline#top"
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp, next_path=next_path)
            stub_idp.register(rsps, id_token_kwargs={"nonce": nonce})
            resp = _callback(client, state)
        assert resp.status_code == 302
        assert resp.headers["Location"] == next_path

    def test_session_lifetime_from_config(self, stub_idp: StubIdP) -> None:
        class _ShortLifetimeConfig(_OidcConfig):
            BEEPER_SESSION_LIFETIME_HOURS = 1.0

        app = create_app(_ShortLifetimeConfig)
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(rsps, id_token_kwargs={"nonce": nonce})
            before = time.time()
            _callback(client, state)
        with client.session_transaction() as sess:
            identity = sess["identity"]
        assert abs((identity["exp"] - identity["iat"]) - 3600) < 5
        assert identity["iat"] >= before

    def test_state_is_single_use(self, app: Flask, stub_idp: StubIdP) -> None:
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(rsps, id_token_kwargs={"nonce": nonce})
            first = _callback(client, state)
            assert first.status_code == 302
            second = _callback(client, state)
        assert second.status_code == 400


# ---------------------------------------------------------------------------
# [T] Tokens never persisted (FR55)
# ---------------------------------------------------------------------------


class TestTokensNeverPersisted:
    def test_session_payload_contains_no_token_material(
        self, app: Flask, stub_idp: StubIdP
    ) -> None:
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(
                rsps,
                id_token_kwargs={"nonce": nonce},
                access_token="super-secret-access-token",
            )
            _callback(client, state)
        with client.session_transaction() as sess:
            identity = sess["identity"]
        assert set(identity.keys()) == {
            "sub",
            "email",
            "email_lc",
            "external_id",
            "name",
            "role_snapshot",
            "iat",
            "exp",
        }
        serialized = str(sess)
        assert "super-secret-access-token" not in serialized
        assert "id_token" not in serialized
        assert "access_token" not in serialized
        assert "refresh_token" not in serialized


# ---------------------------------------------------------------------------
# [T] Full ID-token validation — each failure class rejected
# ---------------------------------------------------------------------------


class TestIdTokenValidationFailures:
    def test_bad_signature_rejected(self, app: Flask, stub_idp: StubIdP) -> None:
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            token = stub_idp.make_id_token(nonce=nonce)
            header_b64, payload_b64, sig_b64 = token.split(".")
            tampered_sig = ("A" if sig_b64[0] != "A" else "B") + sig_b64[1:]
            tampered_token = f"{header_b64}.{payload_b64}.{tampered_sig}"
            stub_idp.register(rsps, id_token=tampered_token)
            resp = _callback(client, state)
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["type"] == "https://beeper.dev/errors/invalid-id-token"
        _assert_no_session(client)

    def test_wrong_issuer_rejected(self, app: Flask, stub_idp: StubIdP) -> None:
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(
                rsps, id_token_kwargs={"nonce": nonce, "iss": "https://not-the-idp.example.com"}
            )
            resp = _callback(client, state)
        assert resp.status_code == 401
        _assert_no_session(client)

    def test_wrong_audience_rejected(self, app: Flask, stub_idp: StubIdP) -> None:
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(rsps, id_token_kwargs={"nonce": nonce, "aud": "some-other-client"})
            resp = _callback(client, state)
        assert resp.status_code == 401
        _assert_no_session(client)

    def test_audience_as_list_containing_client_id_accepted(
        self, app: Flask, stub_idp: StubIdP
    ) -> None:
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(
                rsps, id_token_kwargs={"nonce": nonce, "aud": [CLIENT_ID, "some-other-aud"]}
            )
            resp = _callback(client, state)
        assert resp.status_code == 302

    def test_expired_token_rejected(self, app: Flask, stub_idp: StubIdP) -> None:
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(rsps, id_token_kwargs={"nonce": nonce, "exp_offset": -100000})
            resp = _callback(client, state)
        assert resp.status_code == 401
        _assert_no_session(client)

    def test_nonce_mismatch_rejected(self, app: Flask, stub_idp: StubIdP) -> None:
        with _mock() as rsps, app.test_client() as client:
            state, _nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(rsps, id_token_kwargs={"nonce": "attacker-supplied-nonce"})
            resp = _callback(client, state)
        assert resp.status_code == 401
        _assert_no_session(client)

    def test_missing_nonce_claim_rejected(self, app: Flask, stub_idp: StubIdP) -> None:
        with _mock() as rsps, app.test_client() as client:
            state, _nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(rsps, id_token_kwargs={"nonce": None})
            resp = _callback(client, state)
        assert resp.status_code == 401
        _assert_no_session(client)

    def test_missing_sub_claim_rejected(self, app: Flask, stub_idp: StubIdP) -> None:
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(rsps, id_token_kwargs={"nonce": nonce, "omit_sub": True})
            resp = _callback(client, state)
        assert resp.status_code == 401
        _assert_no_session(client)

    def test_symmetric_alg_token_rejected(self, app: Flask, stub_idp: StubIdP) -> None:
        """FR55: signature validation is restricted to asymmetric
        algorithms — an HS256 token, even a validly-computed one, must be
        rejected outright (never reaches key-material verification)."""
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            now = int(time.time())
            claims = {
                "iss": ISSUER,
                "aud": CLIENT_ID,
                "sub": "user-1",
                "exp": now + 300,
                "iat": now,
                "nonce": nonce,
            }
            # Classic alg-confusion attempt: "sign" with the RSA public
            # key's own JWK JSON as the HMAC secret.
            import json

            oct_key = OctKey.import_key(json.dumps(stub_idp.key.as_dict(private=False)).encode())
            forged = jose_jwt.encode({"alg": "HS256"}, claims, oct_key, algorithms=["HS256"])
            stub_idp.register(rsps, id_token=forged)
            resp = _callback(client, state)
        assert resp.status_code == 401
        _assert_no_session(client)

    def test_state_mismatch_rejected_without_prior_login(
        self, app: Flask, stub_idp: StubIdP
    ) -> None:
        with app.test_client() as client:
            resp = _callback(client, "a-state-nobody-issued")
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["type"] == "https://beeper.dev/errors/oidc-state-mismatch"
        _assert_no_session(client)

    def test_missing_state_param_rejected(self, app: Flask, stub_idp: StubIdP) -> None:
        with app.test_client() as client:
            resp = client.get("/auth/callback", query_string={"code": "test-code"})
        assert resp.status_code == 400
        _assert_no_session(client)

    def test_idp_error_param_rejected(self, app: Flask, stub_idp: StubIdP) -> None:
        with _mock() as rsps, app.test_client() as client:
            state, _nonce = _do_login(client, rsps, stub_idp)
            resp = client.get(
                "/auth/callback",
                query_string={
                    "error": "access_denied",
                    "error_description": "user cancelled",
                    "state": state,
                },
            )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["type"] == "https://beeper.dev/errors/oidc-idp-error"
        assert "access_denied" not in resp.get_data(as_text=True)
        _assert_no_session(client)

    def test_missing_id_token_in_token_response_rejected(
        self, app: Flask, stub_idp: StubIdP
    ) -> None:
        with _mock() as rsps, app.test_client() as client:
            state, _nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(
                rsps,
                token_body_override={
                    "access_token": "test-access-token",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            )
            resp = _callback(client, state)
        assert resp.status_code == 401
        _assert_no_session(client)

    def test_unknown_kid_that_never_resolves_rejected_cleanly(
        self, app: Flask, stub_idp: StubIdP
    ) -> None:
        """Both the initial fetch and the one rotation-triggered refetch
        return a JWKS that never contains the token's `kid` — must fail
        cleanly (401), never raise an unhandled exception."""
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            token = stub_idp.make_id_token(nonce=nonce, kid="totally-unknown-kid")
            rsps.add("GET", _jwks_uri(), json=stub_idp.jwks(), status=200)
            rsps.add("GET", _jwks_uri(), json=stub_idp.jwks(), status=200)
            rsps.add(
                "POST",
                _token_endpoint(),
                json={
                    "access_token": "test-access-token",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "id_token": token,
                },
                status=200,
            )
            resp = _callback(client, state)
        assert resp.status_code == 401
        _assert_no_session(client)


def _jwks_uri() -> str:
    from tests._stub_oidc_idp import JWKS_URI

    return JWKS_URI


def _token_endpoint() -> str:
    from tests._stub_oidc_idp import TOKEN_ENDPOINT

    return TOKEN_ENDPOINT


class TestJwksRotationHandling:
    def test_unknown_kid_triggers_forced_refetch_that_then_succeeds(
        self, app: Flask, stub_idp: StubIdP
    ) -> None:
        """`[T]` JWKS fetch with rotation handling (ADR §3): the token is
        signed by a key not yet in the cached JWKS; the RP force-refetches
        once and, finding the rotated key on the second fetch, accepts the
        token."""
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            token = stub_idp.make_id_token(nonce=nonce, key=stub_idp.rotated_key, kid=ROTATED_KID)
            # First JWKS fetch: primary key only (cached, "stale").
            rsps.add("GET", _jwks_uri(), json=stub_idp.jwks(include_rotated=False), status=200)
            # Forced refetch: rotated key now present.
            rsps.add("GET", _jwks_uri(), json=stub_idp.jwks(include_rotated=True), status=200)
            rsps.add(
                "POST",
                _token_endpoint(),
                json={
                    "access_token": "test-access-token",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "id_token": token,
                },
                status=200,
            )
            resp = _callback(client, state)
        assert resp.status_code == 302
        with client.session_transaction() as sess:
            assert sess["identity"]["sub"] == "user-1"


# ---------------------------------------------------------------------------
# [T] FR56 groups -> role mapping (incl. UserInfo fallback, SCIM on/off)
# ---------------------------------------------------------------------------


class TestGroupsToRoleMapping:
    def test_admin_group_membership_grants_admin(self, app: Flask, stub_idp: StubIdP) -> None:
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(
                rsps, id_token_kwargs={"nonce": nonce, "extra_claims": {"groups": ["beeper-admin"]}}
            )
            _callback(client, state)
        with client.session_transaction() as sess:
            assert sess["identity"]["role_snapshot"] == "admin"

    def test_admin_group_match_case_insensitive(self, app: Flask, stub_idp: StubIdP) -> None:
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(
                rsps, id_token_kwargs={"nonce": nonce, "extra_claims": {"groups": ["ADMINS"]}}
            )
            _callback(client, state)
        with client.session_transaction() as sess:
            assert sess["identity"]["role_snapshot"] == "admin"

    def test_empty_user_groups_means_any_authenticated_is_user(
        self, app: Flask, stub_idp: StubIdP
    ) -> None:
        """`BEEPER_USER_GROUPS` empty (the default) = any authenticated
        principal is `user`, per FR56 — even with zero group claims."""
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(
                rsps, id_token_kwargs={"nonce": nonce, "extra_claims": {"groups": []}}
            )
            resp = _callback(client, state)
        assert resp.status_code == 302
        with client.session_transaction() as sess:
            assert sess["identity"]["role_snapshot"] == "user"

    def test_non_admin_user_group_membership_grants_user(self, stub_idp: StubIdP) -> None:
        app = create_app(_OidcUserGroupsConfig)
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(
                rsps, id_token_kwargs={"nonce": nonce, "extra_claims": {"groups": ["Employees"]}}
            )
            resp = _callback(client, state)
        assert resp.status_code == 302
        with client.session_transaction() as sess:
            assert sess["identity"]["role_snapshot"] == "user"

    def test_scim_disabled_refuses_login_when_neither_group_matches(
        self, stub_idp: StubIdP
    ) -> None:
        """`[T]` neither-group refusal (SCIM off): `BEEPER_USER_GROUPS` is
        non-empty and the principal is in neither set -> 403, no session."""
        app = create_app(_OidcUserGroupsConfig)
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(
                rsps, id_token_kwargs={"nonce": nonce, "extra_claims": {"groups": ["Contractors"]}}
            )
            resp = _callback(client, state)
        assert resp.status_code == 403
        body = resp.get_json()
        assert body["type"] == "https://beeper.dev/errors/not-provisioned"
        _assert_no_session(client)

    def test_scim_enabled_never_refuses_on_groups(self, stub_idp: StubIdP) -> None:
        """`[T]` SCIM-on: no callback refusal regardless of group
        membership — provisioning state (Task 8.8/8.3's store) governs at
        request time instead (ADR §3/§5.2). A session IS established even
        though the principal matches neither admin nor (a hypothetical)
        user group."""

        class _ScimUserGroupsConfig(_OidcScimConfig):
            BEEPER_USER_GROUPS = "Employees"

        app = create_app(_ScimUserGroupsConfig)
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(
                rsps, id_token_kwargs={"nonce": nonce, "extra_claims": {"groups": ["Contractors"]}}
            )
            resp = _callback(client, state)
        assert resp.status_code == 302
        with client.session_transaction() as sess:
            # Harmless placeholder snapshot — never authoritative once SCIM
            # is on (resolve_role_for_identity() consults the store).
            assert sess["identity"]["role_snapshot"] == "user"

    def test_userinfo_fallback_when_groups_claim_absent_from_id_token(
        self, app: Flask, stub_idp: StubIdP
    ) -> None:
        """`[T]` one-shot UserInfo fallback (ADR §3 / Entra group-overflow
        case): the ID token has NO `groups` key at all; the RP fetches
        UserInfo and finds it there instead."""
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(
                rsps,
                id_token_kwargs={"nonce": nonce},  # no `groups` claim
                userinfo_body={"sub": "user-1", "groups": ["Admins"]},
            )
            resp = _callback(client, state)
        assert resp.status_code == 302
        with client.session_transaction() as sess:
            assert sess["identity"]["role_snapshot"] == "admin"

    def test_explicit_empty_groups_claim_does_not_trigger_userinfo_fallback(
        self, app: Flask, stub_idp: StubIdP
    ) -> None:
        """An explicit empty `groups: []` in the ID token is the IdP's
        authoritative "zero groups" answer — must NOT trigger a UserInfo
        call (verified by not registering a userinfo mock: an unexpected
        call would raise `ConnectionError` and fail the test)."""
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(
                rsps, id_token_kwargs={"nonce": nonce, "extra_claims": {"groups": []}}
            )
            resp = _callback(client, state)
        assert resp.status_code == 302  # would raise ConnectionError if userinfo were hit

    def test_userinfo_fallback_failure_is_resilient_not_fatal(
        self, app: Flask, stub_idp: StubIdP
    ) -> None:
        """UserInfo fallback erroring must not crash the callback — treated
        as "no groups", falling through to the default-`user` mapping."""
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(rsps, id_token_kwargs={"nonce": nonce})
            from tests._stub_oidc_idp import USERINFO_ENDPOINT

            rsps.add("GET", USERINFO_ENDPOINT, json={"error": "server_error"}, status=500)
            resp = _callback(client, state)
        assert resp.status_code == 302
        with client.session_transaction() as sess:
            assert sess["identity"]["role_snapshot"] == "user"

    def test_groups_claim_as_single_string(self, app: Flask, stub_idp: StubIdP) -> None:
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(
                rsps, id_token_kwargs={"nonce": nonce, "extra_claims": {"groups": "Admins"}}
            )
            _callback(client, state)
        with client.session_transaction() as sess:
            assert sess["identity"]["role_snapshot"] == "admin"

    def test_configurable_groups_claim_name(self, stub_idp: StubIdP) -> None:
        class _CustomClaimConfig(_OidcConfig):
            BEEPER_OIDC_GROUPS_CLAIM = "roles"

        app = create_app(_CustomClaimConfig)
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(
                rsps, id_token_kwargs={"nonce": nonce, "extra_claims": {"roles": ["Admins"]}}
            )
            _callback(client, state)
        with client.session_transaction() as sess:
            assert sess["identity"]["role_snapshot"] == "admin"


# ---------------------------------------------------------------------------
# [T] external_id derivation (ADR §5.2 join key)
# ---------------------------------------------------------------------------


class TestExternalIdDerivation:
    def test_falls_back_to_sub_when_no_oid_claim(self, app: Flask, stub_idp: StubIdP) -> None:
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(rsps, id_token_kwargs={"nonce": nonce, "sub": "okta-user-1"})
            _callback(client, state)
        with client.session_transaction() as sess:
            assert sess["identity"]["external_id"] == "okta-user-1"

    def test_prefers_oid_claim_when_present(self, app: Flask, stub_idp: StubIdP) -> None:
        with _mock() as rsps, app.test_client() as client:
            state, nonce = _do_login(client, rsps, stub_idp)
            stub_idp.register(
                rsps,
                id_token_kwargs={
                    "nonce": nonce,
                    "sub": "entra-pairwise-sub-1",
                    "extra_claims": {"oid": "entra-directory-object-id-1"},
                },
            )
            _callback(client, state)
        with client.session_transaction() as sess:
            assert sess["identity"]["external_id"] == "entra-directory-object-id-1"
