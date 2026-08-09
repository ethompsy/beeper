"""OIDC login (Task 8.5 — ADR 0002 §1/§3/§5.2/§7, FR55/FR56).

`auth_bp` (`/auth`) is the browser-facing OIDC Relying Party: `GET
/auth/login` starts the authorization-code flow, `GET /auth/callback`
completes it with full ID-token validation, `POST /auth/logout` clears the
session. This module owns nothing else — `/api/v1/auth/*` (the `/me` probe
and, in Task 8.6, local-mode login) is `beeper_ui.routes.auth`'s scope; SCIM
(`/scim/v2/*`) is Task 8.8's.

Registered ONLY when `BEEPER_AUTH_MODE == "oidc"` (`init_oidc_client()` /
`routes/__init__.py`) — mirrors the SCIM blueprint's "disabled ⇒ plain 404,
no fingerprintable surface" pattern (ADR §1) and means `none`/`local` mode
boots never construct an OAuth client or touch the network for this
blueprint at all.

── Library choice and a deliberate, documented deviation ──────────────────
ADR §3 names Authlib as "the maintained de-facto standard Flask RP:
discovery, state/nonce, code exchange, JWKS fetch/rotation-cache, full
ID-token validation" and this module uses `authlib.integrations.flask_client
.OAuth`/`FlaskOAuth2App` for exactly that: `create_authorization_url()` +
`save_authorize_data()` for state/nonce generation and storage (mirroring
`FlaskOAuth2App.authorize_redirect()`, with one addition — see `login()`),
`fetch_access_token()` for the code exchange, and `fetch_jwk_set()` for
JWKS fetch WITH Authlib's built-in rotation handling (`InvalidKeyIdError` ⇒
force refetch once — the exact mechanism `OpenIDMixin.parse_id_token()`
itself uses internally).

The one deliberate deviation: this module does NOT call Authlib's own
`parse_id_token()`/`authorize_access_token()` for the final ID-token
decode. Those pass `algorithms=metadata.get("id_token_signing_alg_values_
supported")` to `joserfc.jwt.decode()` — i.e. the ALLOWED SIGNING
ALGORITHMS are whatever the IdP's OWN discovery document declares, or (if
that field is absent) joserfc's `default_registry`, whose "recommended"
algorithm set INCLUDES `HS256` (verified empirically against joserfc
1.x — `HMACAlgorithm(256, recommended=True)`). FR55 requires "signature via
issuer JWKS restricted to asymmetric algorithms" as an INVARIANT the RP
enforces itself, independent of what the IdP declares — trusting IdP
metadata for this would reopen exactly the alg-confusion class of bug the
requirement exists to close (a misconfigured or malicious discovery
document declaring `HS256` should not be able to make this RP accept
HMAC-signed tokens). `_validate_id_token()` below therefore calls
`joserfc.jwt.decode()` directly with a hardcoded `ASYMMETRIC_ALGORITHMS`
allowlist that never varies with server metadata. This is calling the
same, actively-maintained JOSE engine Authlib itself depends on and
delegates to (`joserfc` — `authlib.jose` is upstream-deprecated in favor of
it as of Authlib 1.6) directly for one security-critical parameter Authlib's
own wrapper doesn't let a caller override — not "hand-rolled JOSE".
Everything else (state, nonce, PKCE-readiness, JWKS transport/rotation,
token exchange, UserInfo) is unmodified Authlib.

── Groups → role (FR56) ────────────────────────────────────────────────────
`_map_groups_to_role()` mirrors `identity_store._recompute_role()`'s
admin-group membership test but additionally implements the
`BEEPER_USER_GROUPS` refusal `identity_store` deliberately doesn't need
(SCIM never refuses; only the SCIM-disabled login path does — ADR §3):
`None` return means "refuse" and is only actually honored by the caller
when SCIM is disabled (§5.2's "no callback refusal when SCIM on").

── Session content — tokens discarded (FR55) ───────────────────────────────
`token` (access/refresh/id_token) is a local variable only, read once for
signature validation and the UserInfo fallback, and goes out of scope at
the end of `callback()`. `establish_session_identity()` (Task 8.3) is the
only thing written into the session, and its shape structurally excludes
token material — see `test_oidc_callback.py::TestTokensNeverPersisted`.

── external_id (ADR §5.2's `external_id` SCIM join key) ───────────────────
Set to `claims.get("oid") or claims["sub"]`. Okta and Keycloak's `sub` claim
IS their stable, IdP-internal user id — the same value operators
conventionally map into the SCIM `externalId` attribute. Entra ID is a
documented exception: by default its OIDC `sub` is a PAIRWISE,
per-application identifier, NOT the stable directory object id — that's
`oid` instead. Preferring `oid` when present (harmless no-op for
Okta/Keycloak, which don't emit it) makes the external_id join correct for
all three named IdPs without new required config. Documented for Task 8.9's
deployment guide: Entra tenants must map the SCIM `externalId` attribute to
`id`/`objectId` (matching `oid`), not `sub`.

── `next` (open-redirect hardening, ADR §2) ────────────────────────────────
Scoped to same-origin paths starting `/app` per this task's brief — the
ONLY documented source of a `GET /auth/login?next=` request is Task 8.4's
frontend seam (`src/api/http.ts`), which always sends a percent-encoded
`/app/...` path (`useCurrentUser`'s 401 handler). The unified resolver's
OWN server-side login redirect for the ten un-migrated Jinja remainder
pages (`middleware.permissions._unauthenticated_response()`, Task 8.3) can
in principle build a `next` outside `/app` (e.g. `/services`) — such a
value is rejected by `_validate_safe_next()` here and falls back to `/app`,
so a cold permalink into one of those ten pages while logged out lands on
the shell's default view after login rather than back on the exact Jinja
page. This is a known, narrow scope limitation (not a security gap — the
fallback is a safe, authenticated landing page): flagged for whoever
carries the Jinja-remainder-pages login round trip further; the trend
(D13/D14) is toward retiring those pages, and every `/app/*` permalink —
the primary, React-served surface — round-trips exactly.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import unquote, urlsplit

from authlib.integrations.base_client import OAuthError  # type: ignore[import-untyped]
from authlib.integrations.flask_client import OAuth  # type: ignore[import-untyped]
from flask import (
    Blueprint,
    Flask,
    Response,
    current_app,
    jsonify,
    redirect,
    request,
    session,
    url_for,
)
from joserfc import jwt as jose_jwt
from joserfc.errors import InvalidKeyIdError, JoseError
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry

from beeper_ui.config import parse_group_names
from beeper_ui.middleware.session import (
    clear_session_identity,
    establish_session_identity,
    same_origin_request,
)

logger = logging.getLogger(__name__)

auth_bp = Blueprint("oidc_auth", __name__, url_prefix="/auth")

_EXT_KEY = "beeper_oidc_client"

# FR55 / ADR §3: "signature via issuer JWKS restricted to asymmetric
# algorithms" — a fixed allowlist independent of IdP-declared metadata. See
# the module docstring's "deliberate deviation" section for why this is
# never derived from `id_token_signing_alg_values_supported`.
ASYMMETRIC_ALGORITHMS: tuple[str, ...] = (
    "RS256",
    "RS384",
    "RS512",
    "PS256",
    "PS384",
    "PS512",
    "ES256",
    "ES384",
    "ES512",
    "EdDSA",
)

# ID-token / claims validation leeway (clock skew), matching Authlib's own
# `parse_id_token()` default.
_CLAIMS_LEEWAY_SECONDS = 120

_DEFAULT_NEXT = "/app"
_SAFE_NEXT_PREFIX = "/app"


class _CallbackRejected(Exception):
    """Carries the RFC7807 shape for a clean callback failure response.

    Never carries IdP- or attacker-supplied text into `detail` — that text
    goes to the server log only (`callback()`'s handler), so a caller can't
    use error-message content to distinguish failure reasons (bad
    signature vs. wrong `aud` vs. expired, etc.) — "rejected with a clean
    error" per this task's AC.
    """

    def __init__(self, type_suffix: str, title: str, status: int, detail: str) -> None:
        self.type_suffix = type_suffix
        self.title = title
        self.status = status
        self.detail = detail
        super().__init__(detail)


# ---------------------------------------------------------------------------
# OAuth client lifecycle
# ---------------------------------------------------------------------------


def init_oidc_client(app: Flask) -> None:
    """Construct and register the Authlib OIDC client on `app`.

    A FRESH `OAuth()` instance per Flask app (never a module-level
    singleton): Authlib's `BaseOAuth` caches registered clients by name on
    the `OAuth` instance itself (`self._clients[name]`), constructed once
    at `register()` time from whatever `app.config` held at that moment. A
    shared singleton across multiple `create_app()` calls (this test suite
    creates one Flask app per test) would leak the FIRST app's client
    config/cached discovery metadata into every later app. Storing the
    constructed client on `app.extensions` instead keeps each app's OIDC
    client — and its lazily-cached discovery/JWKS metadata — fully
    app-scoped.

    Only called when `BEEPER_AUTH_MODE == "oidc"` (`routes/__init__.py`) —
    no discovery-document fetch happens here; `server_metadata_url`
    registration is lazy, fetched on first actual use
    (`FlaskOAuth2App.load_server_metadata()`), which for this app happens
    inside `login()`/`callback()`, never at boot.
    """
    issuer = app.config.get("BEEPER_OIDC_ISSUER", "").rstrip("/")
    scopes = app.config.get("BEEPER_OIDC_SCOPES", "openid profile email groups")
    oauth = OAuth()
    oauth.init_app(app)
    client = oauth.register(
        name="oidc",
        client_id=app.config.get("BEEPER_OIDC_CLIENT_ID", ""),
        client_secret=app.config.get("BEEPER_OIDC_CLIENT_SECRET", ""),
        server_metadata_url=f"{issuer}/.well-known/openid-configuration",
        client_kwargs={"scope": scopes},
    )
    app.extensions = getattr(app, "extensions", {})
    app.extensions[_EXT_KEY] = client


def _get_oidc_client() -> Any:
    client = current_app.extensions.get(_EXT_KEY)
    if client is None:  # pragma: no cover — defensive; routes/__init__.py always calls init first
        raise RuntimeError(
            "OIDC client not initialized on this app — was init_oidc_client() called? "
            "(routes/__init__.py registers auth_bp only when BEEPER_AUTH_MODE == 'oidc'.)"
        )
    return client


# ---------------------------------------------------------------------------
# Safe-`next` validation (ADR §2) — see module docstring's "`next`" section
# ---------------------------------------------------------------------------


def _validate_safe_next(raw: str | None) -> str:
    """Same-origin path under `/app`, query+hash preserved; else `/app`.

    Percent-decoded BEFORE validation (this task's AC wording): Flask's own
    query-string parsing already decodes `request.args.get()` once, so this
    `unquote()` is a defense-in-depth no-op on the common path and closes
    any gap where a not-yet-decoded value reaches this function some other
    way (e.g. a future caller passing a raw query string). Decoding first
    and then demanding an EXACT `/app`-rooted prefix on the result (not a
    substring/startswith-without-boundary check) is what makes single- vs.
    double-encoding tricks irrelevant: `%2F%2Fevil.com` decodes once to
    `/evil.com`... texts that don't land on a real `/app`-rooted path after
    exactly one decode are rejected regardless of how many encoding layers
    they had.
    """
    if not raw:
        return _DEFAULT_NEXT
    decoded = unquote(raw)
    if "\\" in decoded:
        # Reject decoded backslashes (some browsers normalize `\` to `/`,
        # turning `/\evil.com` into a protocol-relative `//evil.com`).
        return _DEFAULT_NEXT
    parsed = urlsplit(decoded)
    if parsed.scheme or parsed.netloc:
        # Covers absolute URLs (`https://evil`) AND protocol-relative
        # (`//evil` parses with empty scheme but a netloc).
        return _DEFAULT_NEXT
    if not (
        decoded == _SAFE_NEXT_PREFIX
        or decoded.startswith(_SAFE_NEXT_PREFIX + "/")
        or decoded.startswith(_SAFE_NEXT_PREFIX + "?")
        or decoded.startswith(_SAFE_NEXT_PREFIX + "#")
    ):
        # Boundary-checked prefix match — `/appevil.com` must NOT pass just
        # because it starts with the four characters "/app".
        return _DEFAULT_NEXT
    return decoded


# ---------------------------------------------------------------------------
# Groups → role (FR56)
# ---------------------------------------------------------------------------


def _map_groups_to_role(
    groups: list[str], *, admin_groups: tuple[str, ...], user_groups: tuple[str, ...]
) -> str | None:
    """`admin` | `user` | `None` (refuse — only honored when SCIM is off).

    Case-insensitive throughout (ADR §3/§8). Admin-group membership always
    wins. Empty `user_groups` (the default) means "any authenticated
    principal is `user`" per FR56; a non-empty `user_groups` narrows that —
    membership in neither set returns `None`.
    """
    group_cf = {g.casefold() for g in groups if g}
    admin_cf = {g.casefold() for g in admin_groups if g}
    if group_cf & admin_cf:
        return "admin"
    if not user_groups:
        return "user"
    user_cf = {g.casefold() for g in user_groups if g}
    if group_cf & user_cf:
        return "user"
    return None


_MISSING = object()


def _extract_groups(
    claims: dict[str, Any], client: Any, token: dict[str, Any], *, groups_claim: str
) -> list[str]:
    """Read the groups claim off the ID token; one-shot UserInfo fallback
    when ABSENT (key not present at all — not merely falsy/empty, which is
    the IdP's authoritative "zero groups" answer and must NOT trigger a
    fallback call). Covers Entra's dropped-`groups`-claim-over-200-groups
    case (ADR §3)."""
    raw = claims.get(groups_claim, _MISSING)
    if raw is _MISSING:
        raw = None
        try:
            metadata = client.load_server_metadata()
            if metadata.get("userinfo_endpoint"):
                userinfo = client.userinfo(token=token)
                raw = userinfo.get(groups_claim)
        except Exception:
            logger.warning("OIDC UserInfo groups fallback failed", exc_info=True)
            raw = None
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, (list, tuple)):
        return [str(g) for g in raw if g]
    return []


# ---------------------------------------------------------------------------
# ID-token validation (FR55) — see module docstring's library-choice section
# ---------------------------------------------------------------------------


def _validate_id_token(
    client: Any, token: dict[str, Any], *, nonce: str | None
) -> dict[str, Any]:
    """Full ID-token validation: signature (asymmetric-only, issuer JWKS
    with rotation handling), exact `iss`, `aud` (contains client id), `exp`
    (with leeway), `nonce`, and presence of `sub`. Raises
    `_CallbackRejected` (never a raw `JoseError`) — callers get one clean,
    generic-to-the-client error regardless of which check failed; the
    specific `JoseError` is logged by the caller.
    """
    if "id_token" not in token:
        raise _CallbackRejected(
            "invalid-id-token",
            "Invalid ID Token",
            401,
            "Token response did not include an id_token.",
        )
    metadata = client.load_server_metadata()
    issuer = metadata.get("issuer")
    if not issuer:
        raise _CallbackRejected(
            "oidc-discovery-failed",
            "Login Failed",
            400,
            "IdP discovery document is missing 'issuer'.",
        )

    try:
        key_set = KeySet.import_key_set(client.fetch_jwk_set())
        try:
            decoded = jose_jwt.decode(
                token["id_token"], key=key_set, algorithms=ASYMMETRIC_ALGORITHMS
            )
        except InvalidKeyIdError:
            # JWKS rotation handling (ADR §3): the token's `kid` isn't in
            # our cached key set — force one refetch and retry once before
            # giving up. Mirrors `authlib...OpenIDMixin.parse_id_token()`'s
            # own retry, since this module bypasses that method (see the
            # module docstring) but reuses `fetch_jwk_set()` unmodified.
            key_set = KeySet.import_key_set(client.fetch_jwk_set(force=True))
            decoded = jose_jwt.decode(
                token["id_token"], key=key_set, algorithms=ASYMMETRIC_ALGORITHMS
            )

        registry = JWTClaimsRegistry(
            leeway=_CLAIMS_LEEWAY_SECONDS,
            iss={"essential": True, "value": issuer},
            aud={"essential": True, "value": client.client_id},
            sub={"essential": True},
            exp={"essential": True},
            # `nonce or ""`: a missing stored nonce (should be structurally
            # impossible — `login()` always generates one — but defensive)
            # compares against a value no real nonce claim (always
            # non-empty, `generate_token(20)`) can ever equal, so this still
            # rejects rather than accidentally widening what's accepted.
            nonce={"essential": True, "value": nonce or ""},
        )
        registry.validate(decoded.claims)
    except JoseError as exc:
        logger.warning("OIDC ID token rejected: %s: %s", type(exc).__name__, exc)
        raise _CallbackRejected(
            "invalid-id-token",
            "Invalid ID Token",
            401,
            "The identity provider's ID token failed validation.",
        ) from exc

    return decoded.claims


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _build_redirect_uri() -> str:
    """The callback URL registered with the IdP.

    `BEEPER_OIDC_REDIRECT_URL` when configured; else derived from the
    request host with the scheme driven EXPLICITLY by
    `BEEPER_EXTERNAL_SCHEME` — never `request.is_secure`/`url_for(_external
    =True)`'s scheme inference (same doctrine as `middleware.session
    .same_origin_request()`: a TLS-terminating ingress speaking plain http
    to the pod must not silently downgrade this). Covers `kubectl
    port-forward`, where the externally-visible host isn't known at boot.
    """
    configured = current_app.config.get("BEEPER_OIDC_REDIRECT_URL", "")
    if configured:
        return configured
    scheme = current_app.config.get("BEEPER_EXTERNAL_SCHEME", "https")
    path = url_for("oidc_auth.callback")
    return f"{scheme}://{request.host}{path}"


@auth_bp.route("/login")
def login() -> Response:
    """`GET /auth/login?next=` — starts the authorization-code flow.

    Reimplements `FlaskOAuth2App.authorize_redirect()`'s four lines with one
    addition: the validated `next` value is stored in the SAME per-`state`
    session envelope as Authlib's own `nonce`/`redirect_uri` (via
    `save_authorize_data()`), rather than passed as an authorization-URL
    query parameter — which would leak an internal app path to the IdP and
    risk rejection by strict IdPs that reject unrecognized params. This way
    `next` is retrieved atomically with `nonce` in `callback()`, correctly
    scoped to THIS login attempt (not a stale value from an abandoned
    concurrent one).
    """
    client = _get_oidc_client()
    redirect_uri = _build_redirect_uri()
    next_path = _validate_safe_next(request.args.get("next"))
    rv = client.create_authorization_url(redirect_uri)
    client.save_authorize_data(redirect_uri=redirect_uri, next=next_path, **rv)
    return redirect(rv["url"])


@auth_bp.route("/callback")
def callback() -> Response | tuple[Response, int, dict[str, str]]:
    """`GET /auth/callback` — full validation per FR55, then session
    establishment per ADR §5.2/§7. Tokens are read for validation only and
    discarded at the end of this function (never written to the session —
    see the module docstring)."""
    client = _get_oidc_client()

    idp_error = request.args.get("error")
    if idp_error:
        # Server-side log only — never reflect IdP-supplied text back to
        # the caller (module docstring: "clean error").
        logger.info(
            "OIDC callback received an IdP error: %s (%s)",
            idp_error,
            request.args.get("error_description", ""),
        )
        return _problem_response(
            type_suffix="oidc-idp-error",
            title="Login Failed",
            status=400,
            detail="The identity provider did not complete sign-in.",
        )

    state = request.args.get("state")
    state_data = client.framework.get_state_data(session, state) if state else None
    client.framework.clear_state_data(session, state or "")
    if state_data is None:
        return _problem_response(
            type_suffix="oidc-state-mismatch",
            title="Invalid State",
            status=400,
            detail="The OIDC state parameter is missing or does not match an in-progress login.",
        )

    try:
        token = client.fetch_access_token(
            code=request.args.get("code"),
            state=state,
            redirect_uri=state_data.get("redirect_uri"),
        )
        claims = _validate_id_token(client, token, nonce=state_data.get("nonce"))
    except _CallbackRejected as exc:
        return _problem_response(
            type_suffix=exc.type_suffix, title=exc.title, status=exc.status, detail=exc.detail
        )
    except OAuthError as exc:
        logger.warning("OIDC token exchange failed: %s", exc)
        return _problem_response(
            type_suffix="oidc-token-exchange-failed",
            title="Login Failed",
            status=400,
            detail="Unable to exchange the authorization code.",
        )

    groups_claim = current_app.config.get("BEEPER_OIDC_GROUPS_CLAIM", "groups")
    groups = _extract_groups(claims, client, token, groups_claim=groups_claim)
    del token  # FR55: tokens are validated then discarded — never referenced again.

    admin_groups = parse_group_names(current_app.config.get("BEEPER_ADMIN_GROUPS", ""))
    user_groups = parse_group_names(current_app.config.get("BEEPER_USER_GROUPS", ""))
    mapped_role = _map_groups_to_role(groups, admin_groups=admin_groups, user_groups=user_groups)

    scim_enabled = bool(current_app.config.get("BEEPER_SCIM_ENABLED", False))
    if not scim_enabled and mapped_role is None:
        # ADR §3: SCIM-disabled callback refusal — neither admin- nor
        # user-group membership, and BEEPER_USER_GROUPS is non-empty. No
        # session is established.
        return _problem_response(
            type_suffix="not-provisioned",
            title="Not Provisioned",
            status=403,
            detail="This account is not a member of a group authorized for access.",
        )
    # SCIM enabled: ADR §3 — "the callback performs no group-based
    # refusal — provisioning state decides" (§5.2). `mapped_role` still
    # seeds the session snapshot (harmless placeholder metadata; ignored
    # for authority — `resolve_role_for_identity()` uses the store).
    role_snapshot = mapped_role or "user"

    email = claims.get("email")
    establish_session_identity(
        sub=claims["sub"],
        email=email,
        name=claims.get("name"),
        role_snapshot=role_snapshot,
        external_id=claims.get("oid") or claims["sub"],
        lifetime_hours=float(current_app.config.get("BEEPER_SESSION_LIFETIME_HOURS", 8.0)),
    )

    next_path = state_data.get("next") or _DEFAULT_NEXT
    return redirect(next_path)


@auth_bp.route("/logout", methods=["POST"])
def logout() -> Response | tuple[Response, int, dict[str, str]]:
    """`POST /auth/logout` — self-enforced CSRF (exempt from the shared
    `before_request` gate, per ADR §2), then clears the local session.

    RP-initiated logout decision (ADR §3's "when configured"): the local
    session is ALWAYS cleared first and unconditionally — that must never
    depend on IdP reachability. A best-effort `logout_url` is additionally
    included in the response ONLY when `BEEPER_OIDC_POST_LOGOUT_REDIRECT_URL`
    is configured; building it can never fail the request (wrapped, falls
    back to `None` on any error, including a down/unreachable IdP). See the
    module docstring section on this and the task report for the full
    id_token_hint caveat: this app never retains an `id_token` (FR55), so
    the URL is built WITHOUT `id_token_hint` — some IdPs will interpose a
    confirmation prompt without it rather than silently redirecting.
    """
    if not same_origin_request():
        return _problem_response(
            type_suffix="csrf-rejected",
            title="Cross-Origin Request Rejected",
            status=403,
            detail=(
                "This state-changing request's Origin/Referer header does "
                "not match the request host."
            ),
        )

    clear_session_identity()

    logout_url = _build_rp_initiated_logout_url()
    return jsonify({"logged_out": True, "logout_url": logout_url})


def _build_rp_initiated_logout_url() -> str | None:
    post_logout_url = current_app.config.get("BEEPER_OIDC_POST_LOGOUT_REDIRECT_URL", "")
    if not post_logout_url:
        return None
    try:
        client = _get_oidc_client()
        metadata = client.load_server_metadata()
        if not metadata.get("end_session_endpoint"):
            return None
        result = client.create_logout_url(post_logout_redirect_uri=post_logout_url)
        return result.get("url")
    except Exception:
        logger.warning("RP-initiated logout URL construction failed", exc_info=True)
        return None


def _problem_response(
    *, type_suffix: str, title: str, status: int, detail: str
) -> tuple[Response, int, dict[str, str]]:
    """RFC7807 `application/problem+json` — same shape as
    `middleware.permissions._problem_response()` (not imported/reused
    directly: that helper is module-private to `permissions.py`)."""
    body = {
        "type": f"https://beeper.dev/errors/{type_suffix}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.path,
    }
    return jsonify(body), status, {"Content-Type": "application/problem+json"}
