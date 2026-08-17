"""Stub OIDC IdP test double (Task 8.5).

Mocks the discovery/JWKS/token/UserInfo HTTP boundary with `responses`
(ADR 0002 §9: "responses not respx for Authlib stubs" — Authlib's OAuth
client is `requests`-based, unlike this suite's `httpx`-based clients,
which are `respx`-mocked elsewhere).

Not a test file itself (no `test_` prefix — not collected by pytest);
imported by `test_oidc_config_boot_refusals.py`, `test_oidc_login.py`,
`test_oidc_callback.py`, `test_oidc_logout.py`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from joserfc import jwt as jose_jwt
from joserfc.jwk import RSAKey

ISSUER = "https://idp.example.com"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"
AUTHORIZATION_ENDPOINT = f"{ISSUER}/authorize"
TOKEN_ENDPOINT = f"{ISSUER}/token"
JWKS_URI = f"{ISSUER}/jwks"
USERINFO_ENDPOINT = f"{ISSUER}/userinfo"
END_SESSION_ENDPOINT = f"{ISSUER}/end-session"

CLIENT_ID = "beeper-ui-test-client"
CLIENT_SECRET = "test-client-secret"  # noqa: S105 - test fixture, not a real secret

PRIMARY_KID = "kid-primary"
ROTATED_KID = "kid-rotated"


def _generate_rsa_key(kid: str) -> RSAKey:
    return RSAKey.generate_key(2048, parameters={"kid": kid}, private=True)


@dataclass
class StubIdP:
    """A minimal, deterministic OIDC IdP. One RSA keypair (`kid-primary`) is
    the "current" signing key; `rotated_key` (`kid-rotated`) simulates a key
    rotation the RP hasn't cached yet, for the JWKS-rotation-handling test.
    """

    key: RSAKey = field(default_factory=lambda: _generate_rsa_key(PRIMARY_KID))
    rotated_key: RSAKey = field(default_factory=lambda: _generate_rsa_key(ROTATED_KID))
    include_end_session_endpoint: bool = True
    declared_signing_algs: list[str] = field(default_factory=lambda: ["RS256"])

    def discovery_document(self, **overrides: Any) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "issuer": ISSUER,
            "authorization_endpoint": AUTHORIZATION_ENDPOINT,
            "token_endpoint": TOKEN_ENDPOINT,
            "jwks_uri": JWKS_URI,
            "userinfo_endpoint": USERINFO_ENDPOINT,
            "id_token_signing_alg_values_supported": self.declared_signing_algs,
            "scopes_supported": ["openid", "profile", "email", "groups"],
        }
        if self.include_end_session_endpoint:
            doc["end_session_endpoint"] = END_SESSION_ENDPOINT
        doc.update(overrides)
        return doc

    def jwks(self, *, include_rotated: bool = False) -> dict[str, Any]:
        keys = [self.key]
        if include_rotated:
            keys.append(self.rotated_key)
        return {"keys": [k.as_dict(private=False) for k in keys]}

    def make_id_token(
        self,
        *,
        sub: str = "user-1",
        aud: str | list[str] = CLIENT_ID,
        iss: str = ISSUER,
        nonce: str | None = "test-nonce",
        exp_offset: float = 300,
        iat_offset: float = 0,
        extra_claims: dict[str, Any] | None = None,
        omit_sub: bool = False,
        key: RSAKey | None = None,
        alg: str = "RS256",
        kid: str | None = None,
    ) -> str:
        """Build a signed ID token. Defaults produce a token that validates
        cleanly against `self.key` / the default discovery+JWKS. Every
        parameter is a hook for a specific failure-class test (wrong
        `iss`/`aud`, expired, nonce mismatch, missing `sub`, alternate
        signing key/kid for rotation and bad-signature tests)."""
        signing_key = key if key is not None else self.key
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": iss,
            "aud": aud,
            "exp": now + exp_offset,
            "iat": now + iat_offset,
        }
        if not omit_sub:
            claims["sub"] = sub
        if nonce is not None:
            claims["nonce"] = nonce
        if extra_claims:
            claims.update(extra_claims)
        header = {"alg": alg, "kid": kid if kid is not None else signing_key.kid}
        return jose_jwt.encode(header, claims, signing_key, algorithms=[alg])

    def register(
        self,
        rsps: Any,
        *,
        id_token: str | None = None,
        id_token_kwargs: dict[str, Any] | None = None,
        access_token: str = "test-access-token",  # noqa: S107 - test fixture value
        token_status: int = 200,
        token_body_override: dict[str, Any] | None = None,
        userinfo_body: dict[str, Any] | None = None,
        jwks_body: dict[str, Any] | None = None,
        discovery_body: dict[str, Any] | None = None,
    ) -> str:
        """Register `responses` mocks for discovery/JWKS/token[/userinfo] on
        the given `responses.RequestsMock` instance. Returns the id_token
        string that will be returned from the token endpoint (built fresh
        via `make_id_token(**id_token_kwargs)` unless `id_token` is given
        explicitly)."""
        rsps.add(
            "GET",
            DISCOVERY_URL,
            json=discovery_body if discovery_body is not None else self.discovery_document(),
            status=200,
        )
        rsps.add(
            "GET",
            JWKS_URI,
            json=jwks_body if jwks_body is not None else self.jwks(),
            status=200,
        )
        token = id_token if id_token is not None else self.make_id_token(**(id_token_kwargs or {}))
        body = token_body_override if token_body_override is not None else {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "id_token": token,
        }
        rsps.add("POST", TOKEN_ENDPOINT, json=body, status=token_status)
        if userinfo_body is not None:
            rsps.add("GET", USERINFO_ENDPOINT, json=userinfo_body, status=200)
        return token
