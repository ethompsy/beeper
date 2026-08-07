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

    # React-owned path-prefix dispatch registry (Task 1.3 / D11).
    # Explicit list of path prefixes (e.g. "/investigations") that should be
    # served by the React SPA shell instead of their Jinja equivalent, with
    # deterministic precedence over Jinja blueprints. Starts empty — real
    # view migrations populate this per-milestone (see docs/plans/react-ui.md).
    # `/api/*` and `/app/*` are always excluded regardless of this list.
    REACT_OWNED_PREFIXES: tuple[str, ...] = ()

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
    # §0(a) item 3). Consequence: until Task 6.2b (verified identity, blocked
    # on plan Q11) lands, production has NO admin path at all — the K8s-token
    # route also grants "admin" from an unverified JWT payload claim today
    # (§0(a) item 2), so it is not a substitute; every `@require_role
    # ("admin")` route resolves to 403 for every caller in production.
    # This is the intended fail-closed behavior per the user's explicit
    # decision not to ship the spoofable identity source, weighed against a
    # ClusterIP / non-internet-facing deployment. Operators needing
    # admin-tier changes (trust-level writes, gate-threshold writes,
    # adjustment apply/reject) must use `kubectl`/Helm directly until 6.2b.
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
    """Get configuration based on environment."""
    env = os.environ.get("FLASK_ENV", "development")
    configs = {
        "development": DevelopmentConfig,
        "testing": TestingConfig,
        "production": ProductionConfig,
    }
    return configs.get(env, DevelopmentConfig)
