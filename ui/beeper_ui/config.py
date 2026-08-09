"""Configuration for Beeper UI."""

import os
import secrets

VALID_AUTH_MODES: frozenset[str] = frozenset({"none", "local", "oidc"})

_TRUE_STRINGS = frozenset({"1", "true", "yes", "on"})


def _env_bool(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable (`1`/`true`/`yes`/`on`, case-insensitive)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE_STRINGS


def parse_group_names(raw: str) -> tuple[str, ...]:
    """Parse a comma-separated group-name config value into a tuple.

    Used for `BEEPER_ADMIN_GROUPS` / `BEEPER_USER_GROUPS` (ADR 0002 §3/§8) —
    shared by OIDC login (Task 8.5), SCIM group→role derivation (Task 8.8),
    and `beeper_ui.services.identity_store`'s adopt-and-link role recompute
    (Task 8.3). Strips whitespace and drops empty entries so a trailing
    comma or accidental double-comma doesn't produce a spurious empty group
    name that would never match anything anyway.
    """
    return tuple(part.strip() for part in raw.split(",") if part.strip())


class AuthConfigError(RuntimeError):
    """Raised at boot when `BEEPER_AUTH_MODE` / related config is contradictory.

    ADR 0002 §1/§8, FR54: enforcement lives EXCLUSIVELY in
    `beeper_ui.app.create_app()` — never a `Config` subclass `__init__` (see
    `ProductionConfig.__init__`'s docstring below for why that hook is dead
    code under `Flask.config.from_object(<class>)`).
    """


class Config:
    """Base configuration."""

    # Flask settings - use environment variable or generate random key for dev
    SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    DEBUG = False
    TESTING = False

    # Operator API settings
    OPERATOR_URL = os.environ.get("BEEPER_OPERATOR_URL", "http://localhost:8080")
    OPERATOR_TIMEOUT = float(os.environ.get("BEEPER_OPERATOR_TIMEOUT", "5.0"))

    # UI settings
    UI_PORT = int(os.environ.get("BEEPER_UI_PORT", "5050"))
    UI_HOST = os.environ.get("BEEPER_UI_HOST", "0.0.0.0")

    # File upload settings
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2MB max upload size

    # React-owned path-prefix dispatch registry (Task 1.3 / D11; cutover
    # Task 6.3 / D13-D14). Bare requests under one of these prefixes
    # 302-redirect to their `/app/*` React equivalent instead of being
    # served by their Jinja blueprint — see
    # `ui/beeper_ui/routes/react_registry.py` for the redirect mechanism,
    # its exclusions (un-migrated sub-routes that must keep rendering: KB
    # write/history/admin routes, Cost Insights, `/metrics/export`,
    # Jinja-only investigation actions), and its target-path overrides.
    # This is the full "migrated" set (D13) — the ten un-migrated nav
    # destinations in docs/design/route-parity-targets.md §7 (Health, SLO,
    # Services, Topology, Analytics, Reports, Handoff, Cost Insights,
    # Notifications, Trust) are deliberately NOT listed here and keep
    # rendering Jinja. `/api/*` and `/app/*` are always excluded regardless
    # of this list.
    REACT_OWNED_PREFIXES: tuple[str, ...] = (
        "/investigations",
        "/knowledge",
        "/health/ingestion",
        "/sources",
        "/spending",
        "/metrics",
    )

    # Task 6.2a / ADR 0001 §0(a) item 3: whether `beeper_ui.middleware
    # .permissions.resolve_user_role()` honors the `X-Beeper-Role` header.
    # It is a trivially spoofable identity source (any HTTP client can set
    # it), so it stays on for Development/Testing but MUST be off in
    # Production — see `ProductionConfig` below.
    #
    # Read as a *class attribute* by the middleware, not validated in
    # `__init__`: `Flask.config.from_object()` is handed the config *class*
    # itself (see `get_config()` / `create_app()`), never an instance, so a
    # subclass `__init__` is dead code here (see `ProductionConfig` below).
    ALLOW_ROLE_HEADER: bool = True

    # --- ADR 0002 identity/auth config (Task 8.3) -----------------------
    # Single authoritative mode knob (ADR §1): `none` (default) preserves
    # today's behavior exactly; `local`/`oidc` route through the shared
    # identity store + session-cookie resolver
    # (`beeper_ui.middleware.permissions.resolve_request_identity()`).
    BEEPER_AUTH_MODE: str = os.environ.get("BEEPER_AUTH_MODE", "none")

    # Valid ONLY when BEEPER_AUTH_MODE == "oidc" — refused at boot otherwise
    # (ADR §1/§8; see `validate_boot_config()` below). The SCIM blueprint
    # itself (Task 8.8) is registered only when this is true.
    BEEPER_SCIM_ENABLED: bool = _env_bool("BEEPER_SCIM_ENABLED")

    # `oidc` + SCIM only: an authenticated-but-never-provisioned principal
    # normally defaults to role "user" (D2); setting this refuses instead
    # (403 `not-provisioned`) — see ADR §5.2.
    BEEPER_SCIM_STRICT: bool = _env_bool("BEEPER_SCIM_STRICT")

    # One group-name config pair shared by OIDC login (8.5) role mapping,
    # SCIM (8.8) role mapping, and the identity store's adopt-and-link role
    # recompute (ADR §3/§5.2, Task 8.3). Comma-separated, case-insensitive
    # — parse with `parse_group_names()`.
    BEEPER_ADMIN_GROUPS: str = os.environ.get("BEEPER_ADMIN_GROUPS", "Admins,beeper-admin")
    BEEPER_USER_GROUPS: str = os.environ.get("BEEPER_USER_GROUPS", "")

    # Session-cookie hardening (ADR §2). `BEEPER_EXTERNAL_SCHEME` drives
    # `SESSION_COOKIE_SECURE` EXPLICITLY in `create_app()` — never inferred
    # from request introspection, so a TLS-terminating ingress speaking
    # plain http to the pod cannot silently strip the flag (security
    # LOW-10). `BEEPER_SESSION_LIFETIME_HOURS` is the absolute session
    # lifetime (no sliding refresh in v1).
    BEEPER_EXTERNAL_SCHEME: str = os.environ.get("BEEPER_EXTERNAL_SCHEME", "https")
    BEEPER_SESSION_LIFETIME_HOURS: float = float(
        os.environ.get("BEEPER_SESSION_LIFETIME_HOURS", "8")
    )

    # --- ADR 0002 §4/§8 SCIM bearer token(s) (Task 8.8) ------------------
    # Long-lived bearer token(s) for `/scim/v2/*` (env/Secret-supplied —
    # never a source-controlled default, unlike BEEPER_ADMIN_GROUPS above).
    # `BEEPER_SCIM_TOKEN_SECONDARY` is optional and exists solely for
    # dual-token zero-downtime rotation (ADR §4/FR58): during a rotation
    # window both the outgoing and incoming token values are accepted.
    # Neither value is validated at boot (deliberately — see ADR §8's
    # "SCIM enabled without a token" row: the surface REGISTERS and fails
    # closed per-request with 403, it does not refuse to boot; see
    # `beeper_ui.routes.scim_helpers.authenticate_scim_request()`).
    BEEPER_SCIM_TOKEN: str = os.environ.get("BEEPER_SCIM_TOKEN", "")
    BEEPER_SCIM_TOKEN_SECONDARY: str = os.environ.get("BEEPER_SCIM_TOKEN_SECONDARY", "")


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True


class TestingConfig(Config):
    """Testing configuration."""

    TESTING = True
    DEBUG = True
    SECRET_KEY = "test-secret-key-not-for-production"
    # Use mock operator for tests
    OPERATOR_URL = "http://mock-operator:8080"
    # `ui/tests/conftest.py`'s `_RoleClient`/`admin_client`/`user_client`
    # fixtures inject `X-Beeper-Role` and are used across a dozen+ test
    # files — this must stay True or all of them break.
    ALLOW_ROLE_HEADER = True


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False

    # Refuses the spoofable `X-Beeper-Role` header (Task 6.2a / ADR 0001
    # §0(a) item 3). Every `@require_role("admin")` route now resolves to
    # 403 for every caller in production: the header is refused here, and
    # the only other historical path to a role — an unverified-JWT
    # `Authorization: Bearer` peek at the token's `groups` claim — has been
    # deleted unconditionally, in every mode, as a standalone security
    # hotfix (Task 8.2; ADR 0002 §7/§12 CRITICAL-1). That claim was FALSE
    # before Task 8.2 landed: the Bearer peek ran first on every request,
    # ungated by `ALLOW_ROLE_HEADER`, so a crafted token granted "admin" in
    # production regardless of this flag. See
    # `docs/specs/decisions/0002-oidc-scim-and-local-fallback-identity.md`
    # and `ui/beeper_ui/middleware/permissions.py`. Production has NO admin
    # path at all until Task 8.3's unified resolver (ADR 0002 §7) ships
    # verified identity (OIDC/SCIM or local accounts). Operators needing
    # admin-tier changes (trust-level writes, gate-threshold writes,
    # adjustment apply/reject) must use `kubectl`/Helm directly until then.
    ALLOW_ROLE_HEADER = False

    def __init__(self) -> None:
        """Validate production configuration.

        NOTE: dead code today. `Flask.config.from_object()` (see
        `create_app()`) is always passed this *class*, never an instance, so
        `__init__` never runs and this check never fires. Left in place
        as-documented rather than silently removed — do not rely on it for
        enforcement; use class attributes (like `ALLOW_ROLE_HEADER` above)
        for anything that must actually take effect.
        """
        if not os.environ.get("SECRET_KEY"):
            raise ValueError(
                "SECRET_KEY environment variable must be set in production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )


def get_config() -> type[Config]:
    """Get configuration based on the `FLASK_ENV` environment variable.

    Fails SAFE, not open (Task 8.2 hotfix; ADR 0002 §8 / FR54). Two distinct
    cases, deliberately resolved differently:

    - `FLASK_ENV` **absent** (unset): stays `DevelopmentConfig`, preserving
      local-dev ergonomics — `flask run` on a laptop with no env configured
      keeps working exactly as before.
    - `FLASK_ENV` **present but unrecognized** (e.g. a typo like
      `produciton`): previously fell back to the permissive
      `DevelopmentConfig`, which honors the spoofable `X-Beeper-Role`
      header — a silent-open failure mode. Now falls back to
      `ProductionConfig` instead, so a misconfigured deployment fails
      closed rather than accidentally exposing the dev role-header
      affordance. Helm's `ui.flaskEnv` defaults to `production` (D3); only
      `make demo-up`/`demo-deploy` explicitly opt into `development`.
    """
    env = os.environ.get("FLASK_ENV")
    if env is None:
        return DevelopmentConfig
    configs = {
        "development": DevelopmentConfig,
        "testing": TestingConfig,
        "production": ProductionConfig,
    }
    return configs.get(env, ProductionConfig)


def validate_boot_config(config: type[Config]) -> None:
    """Refuse contradictory `BEEPER_AUTH_MODE` config at boot.

    ADR 0002 §1/§8, FR54. Called from `beeper_ui.app.create_app()` —
    deliberately NOT from any `Config` subclass `__init__` (see
    `ProductionConfig.__init__`'s docstring above: that hook never runs
    under `Flask.config.from_object(<class>)`, which is always handed the
    class itself, never an instance).

    Only the two refusals Task 8.3 owns are enforced here:

    1. `BEEPER_SCIM_ENABLED=true` is valid only when `BEEPER_AUTH_MODE=oidc`.
    2. `local`/`oidc` mode requires `SECRET_KEY` supplied via the **process
       environment** — not merely a truthy `config.SECRET_KEY`, which falls
       back to `secrets.token_hex(32)` per process (see `Config.SECRET_KEY`
       above) when the env var is absent. That fallback is fine for `none`
       (no session ever needs to survive a restart) but would silently
       invalidate every session on pod restart, and diverge across
       replicas, in `local`/`oidc` — so it must be refused, not defaulted.

    OIDC-specific refusals (issuer/client-id/client-secret presence, ADR
    §8) belong to Task 8.5, which owns those config keys, and are
    deliberately NOT enforced here.

    Raises:
        AuthConfigError: on any contradiction described above, or an
            unrecognized `BEEPER_AUTH_MODE` value.
    """
    mode = getattr(config, "BEEPER_AUTH_MODE", "none")
    if mode not in VALID_AUTH_MODES:
        raise AuthConfigError(
            f"BEEPER_AUTH_MODE={mode!r} is invalid; must be one of "
            f"{sorted(VALID_AUTH_MODES)}."
        )

    scim_enabled = getattr(config, "BEEPER_SCIM_ENABLED", False)
    if scim_enabled and mode != "oidc":
        raise AuthConfigError(
            "BEEPER_SCIM_ENABLED=true is only valid when BEEPER_AUTH_MODE=oidc "
            f"(got BEEPER_AUTH_MODE={mode!r}). See ADR 0002 §1."
        )

    if mode in {"local", "oidc"} and not os.environ.get("SECRET_KEY"):
        raise AuthConfigError(
            f"SECRET_KEY environment variable must be set when "
            f"BEEPER_AUTH_MODE={mode!r}: sessions must survive process "
            "restarts and stay consistent across replicas (ADR 0002 §2). "
            'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
        )
