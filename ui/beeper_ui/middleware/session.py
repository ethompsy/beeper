"""Session-cookie identity snapshot — the "session core" of Task 8.3.

ADR 0002 §2/§7. The Flask session cookie (signed, `HttpOnly`,
`SameSite=Lax` — see `beeper_ui.app.create_app()` for the cookie
attributes) carries an identity *snapshot*, never tokens, and — except in
the one bounded exception ADR §5.2 documents (`oidc` without SCIM) — never
the authoritative role. See
`beeper_ui.middleware.permissions.resolve_role_for_identity()` for the
per-mode authority rule that consumes the snapshot this module produces.

This module is intentionally store-free and Flask-request-context-only —
no Qdrant — so it is testable with a bare Flask app/request context and
reusable, unmodified, by the OIDC (8.5) and local-auth (8.6) login
endpoints that will call `establish_session_identity()` and by
`POST /auth/logout` / `POST /api/v1/auth/logout`, which must call
`same_origin_request()` themselves (those routes are exempt from the
shared `before_request` CSRF check — see
`beeper_ui.middleware.permissions.EXEMPT_PATH_PREFIXES`).
`same_origin_request()` reads one config key, `BEEPER_EXTERNAL_SCHEME`
(same key `create_app()` uses for the session cookie's `Secure` flag) — see
its docstring.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from flask import current_app, request, session

_SESSION_KEY = "identity"


@dataclass(frozen=True)
class SessionIdentity:
    """The identity snapshot carried in the session cookie (ADR §2).

    Fields mirror the ADR's `{sub_or_user_id, email, name, role_snapshot,
    iat, exp}` plus `external_id` (SCIM join key) and a pre-casefolded
    `email_lc` (avoids re-casefolding on every request in the `oidc`+SCIM
    lookup path).
    """

    sub: str
    email: str | None
    email_lc: str | None
    external_id: str | None
    name: str | None
    role_snapshot: str
    iat: float
    exp: float


def establish_session_identity(
    *,
    sub: str,
    email: str | None = None,
    name: str | None = None,
    role_snapshot: str = "user",
    external_id: str | None = None,
    lifetime_hours: float = 8.0,
) -> SessionIdentity:
    """Rotate the session and write a fresh identity snapshot (login).

    `session.clear()` discards any pre-login session content before writing
    the new identity — session rotation on login (ADR §2), the standard
    fixation defense: a cookie value an attacker fixed pre-auth carries no
    post-login authority because the payload underneath it is replaced
    wholesale, not merely amended.
    """
    now = time.time()
    session.clear()
    identity = SessionIdentity(
        sub=sub,
        email=email,
        email_lc=email.strip().casefold() if email else None,
        external_id=external_id,
        name=name,
        role_snapshot=role_snapshot,
        iat=now,
        exp=now + (lifetime_hours * 3600),
    )
    session[_SESSION_KEY] = _identity_to_dict(identity)
    session.permanent = True
    return identity


def read_session_identity() -> SessionIdentity | None:
    """Return the current session's identity snapshot, or None.

    None for a missing OR expired snapshot — expiry checking is this
    function's entire reason to exist beyond a plain dict read: Flask's
    signed cookie already makes a *tampered* cookie transparently empty (a
    bad signature means `session` just has no `identity` key), but nothing
    else enforces the absolute lifetime the ADR requires, since the
    `Set-Cookie` `Max-Age` only bounds when the *browser* discards the
    cookie, not whether a still-fresh-looking cookie's payload has expired
    server-side.
    """
    raw = session.get(_SESSION_KEY)
    if not raw:
        return None
    try:
        identity = SessionIdentity(
            sub=raw["sub"],
            email=raw.get("email"),
            email_lc=raw.get("email_lc"),
            external_id=raw.get("external_id"),
            name=raw.get("name"),
            role_snapshot=raw.get("role_snapshot", "user"),
            # Coerced to float HERE, inside the guarded block (security
            # review LOW finding): a malformed `iat`/`exp` (a future
            # application bug writing a bad payload, never reachable via
            # cookie tampering since the cookie is itsdangerous-signed)
            # must be treated as an invalid session, not raise an uncaught
            # `TypeError` out of the `time.time() > identity.exp` check
            # below.
            iat=float(raw.get("iat", 0.0)),
            exp=float(raw.get("exp", 0.0)),
        )
    except (KeyError, TypeError, ValueError):
        session.pop(_SESSION_KEY, None)
        return None
    if time.time() > identity.exp:
        session.pop(_SESSION_KEY, None)
        return None
    return identity


def clear_session_identity() -> None:
    """Drop the identity snapshot (logout, or deactivation-triggered clear)."""
    session.pop(_SESSION_KEY, None)


def _identity_to_dict(identity: SessionIdentity) -> dict[str, Any]:
    return {
        "sub": identity.sub,
        "email": identity.email,
        "email_lc": identity.email_lc,
        "external_id": identity.external_id,
        "name": identity.name,
        "role_snapshot": identity.role_snapshot,
        "iat": identity.iat,
        "exp": identity.exp,
    }


def build_login_redirect_next(path: str | None = None) -> str:
    """Build the same-origin `next=` value for a login redirect (ADR §2/§7).

    Defaults to `request.full_path` (path + query string), which is by
    construction always a same-origin relative path with no scheme/host
    component — safe to embed without further validation on the *issuing*
    side. The login endpoints that consume `next` (Task 8.5/8.6) are
    responsible for percent-decoding and re-validating it before honoring a
    redirect (reject a decoded `//`, `\\`, or any scheme) per ADR §2 — this
    function only builds a safe value, it is not that validator.
    """
    target = path if path is not None else request.full_path
    # `request.full_path` appends a trailing "?" even with no query string;
    # strip it so a bare path doesn't carry a dangling "?".
    return target[:-1] if target.endswith("?") else target


def same_origin_request() -> bool:
    """CSRF check (ADR §2): Origin (falling back to Referer) must match the
    request's own scheme+host.

    The sole CSRF mechanism for state-changing (unsafe-method) requests
    once a session cookie has authenticated the caller — Origin/Referer
    same-origin equality, with `SameSite=Lax` as the browser backstop.
    Covers React `fetch`, HTMX, and Jinja-remainder `<form>` POSTs with
    zero markup changes (ADR §2).

    Missing BOTH headers is treated as a mismatch (reject): every
    legitimate same-origin `fetch`/HTMX/`<form>` POST this scheme needs to
    cover sends at least one of them, so an absent pair is either a very
    unusual client or a forged request — reject rather than guess.

    Compares BOTH host and scheme (security review MEDIUM finding, fixed):
    an origin is `(scheme, host, port)` per RFC 6454 §7 — comparing netloc
    alone would treat `http://<host>` and `https://<host>` as the same
    origin, which matters here because a same-host HTTP origin can appear
    on a real request during an SSL-strip/downgrade or a misconfigured
    dual HTTP/HTTPS listener. The expected scheme is read from
    `BEEPER_EXTERNAL_SCHEME` — the same explicit, non-inferred config key
    `create_app()` uses for the session cookie's `Secure` flag (ADR §2
    security LOW-10) — rather than `request.is_secure`, which would be
    WRONG in this codebase's own documented deployment shape: a
    TLS-terminating ingress speaking plain http to the pod makes
    `request.is_secure` false for a genuinely HTTPS-originated request,
    which would reject every legitimate same-origin POST in that topology.
    Host comparison is case-insensitive (browsers lowercase the Host/Origin
    authority; this is defense-in-depth, not attacker-reachable, since the
    attacker never controls `request.host`).
    """
    source = request.headers.get("Origin") or request.headers.get("Referer")
    if not source:
        return False
    try:
        parsed = urlsplit(source)
    except ValueError:
        return False
    expected_scheme = current_app.config.get("BEEPER_EXTERNAL_SCHEME", "https")
    return (
        parsed.scheme.lower() == expected_scheme.lower()
        and parsed.netloc.lower() == request.host.lower()
    )
