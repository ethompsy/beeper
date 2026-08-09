"""Configuration for Beeper UI."""

import os
import secrets


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
