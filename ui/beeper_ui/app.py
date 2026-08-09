"""Beeper UI Flask application factory."""

from datetime import timedelta

from flask import Flask, render_template

from beeper_ui.config import get_config, validate_boot_config
from beeper_ui.middleware.permissions import init_permissions
from beeper_ui.utils import setup_markdown_filter


def create_app(config_class: type | None = None) -> Flask:
    """Create and configure the Flask application.

    Args:
        config_class: Optional configuration class to use. If not provided,
                     the configuration is determined from the FLASK_ENV environment variable.

    Returns:
        Configured Flask application instance.

    Raises:
        beeper_ui.config.AuthConfigError: on contradictory `BEEPER_AUTH_MODE`
            config (ADR 0002 §1/§8, FR54) — e.g. `BEEPER_SCIM_ENABLED=true`
            outside `oidc` mode, or `local`/`oidc` mode without an
            env-supplied `SECRET_KEY`. Enforcement lives here, not in any
            `Config` subclass `__init__` — see `validate_boot_config()`.
    """
    if config_class is None:
        config_class = get_config()
    validate_boot_config(config_class)

    app = Flask(__name__)

    # Load configuration
    app.config.from_object(config_class)

    # Session-cookie hardening (ADR 0002 §2) — `local`/`oidc` ONLY.
    #
    # Self-review finding (fixed here): `beeper_ui.routes.knowledge` calls
    # Flask's `flash()` on a pre-existing, un-migrated Jinja route
    # (`confirm_entry`), which is reachable in mode `none` too and is
    # itself backed by Flask's session cookie. Setting
    # `SESSION_COOKIE_SECURE = True` unconditionally (the default this
    # block used to compute whenever `BEEPER_EXTERNAL_SCHEME` was unset)
    # would have changed that PRE-EXISTING flash-cookie's behavior in mode
    # `none` too: a browser refuses to send a `Secure` cookie back over
    # plain HTTP, which is exactly how the demo/`kubectl port-forward`
    # access pattern (ADR §1's "demo/dev" row) works today. That would
    # have broken flash-message round-tripping in the default, zero-config
    # demo path — a direct violation of the "mode `none` preserves today's
    # behavior exactly" / NFR26 program gate. Scoping this whole block to
    # `local`/`oidc` keeps mode `none` byte-identical to pre-8.3 Flask
    # session-cookie defaults, matching every other piece of 8.3's new
    # session-cookie/CSRF machinery, none of which activates in mode
    # `none` either.
    #
    # `HttpOnly` is Flask's default already; set explicitly for clarity.
    # `SameSite=Lax` too, in `local`/`oidc`. `Secure` is driven EXPLICITLY
    # by `BEEPER_EXTERNAL_SCHEME` — never inferred from request
    # introspection (security LOW-10): a TLS-terminating ingress speaking
    # plain http to the pod must not be able to silently strip the flag.
    # Absolute session lifetime per `BEEPER_SESSION_LIFETIME_HOURS`
    # (default 8h; no sliding refresh in v1) — enforced again,
    # independently, inside the session payload's own `exp` field (see
    # `beeper_ui.middleware.session.read_session_identity()`), since
    # `PERMANENT_SESSION_LIFETIME` only bounds the cookie's `Max-Age`, not
    # whether an unexpired-looking cookie's payload has actually expired
    # server-side.
    if app.config.get("BEEPER_AUTH_MODE", "none") != "none":
        app.config["SESSION_COOKIE_HTTPONLY"] = True
        app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
        external_scheme = app.config.get("BEEPER_EXTERNAL_SCHEME", "https")
        app.config["SESSION_COOKIE_SECURE"] = external_scheme != "http"
        app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
            hours=float(app.config.get("BEEPER_SESSION_LIFETIME_HOURS", 8))
        )

    # Register permission middleware (before_request identity resolver)
    init_permissions(app)

    # Task 8.6: `flask create-admin` CLI (ADR 0002 §6 / FR61 recovery path).
    # Registered unconditionally — see beeper_ui/cli.py's module docstring
    # for why gating CLI *registration* on `BEEPER_AUTH_MODE` would be
    # counterproductive for a command whose whole purpose is recovering a
    # misconfigured deployment.
    from beeper_ui.cli import register_cli

    register_cli(app)

    # Task 8.6: local-mode admin bootstrap (ADR 0002 §6, FR61) — idempotent
    # seed from BEEPER_BOOTSTRAP_ADMIN_USERNAME/_PASSWORD, or (if neither is
    # set) just the zero-active-admins alarm check. Never raises (see
    # `beeper_ui.services.bootstrap`'s module docstring) and is a pure no-op
    # outside `local` mode — mode `none` (the demo) never touches the
    # identity store at all, preserving NFR26's "zero identity
    # configuration" guarantee.
    if app.config.get("BEEPER_AUTH_MODE", "none") == "local":
        from beeper_ui.services.bootstrap import ensure_bootstrap_admin

        ensure_bootstrap_admin(app)

    # Register markdown template filter
    setup_markdown_filter(app)

    # Register investigation template helpers
    from beeper_ui.routes.investigations import (
        ACCURACY_LABELS,
        NOT_AN_ISSUE_LABELS,
        OUTCOME_LABELS,
        format_mttr,
    )

    app.jinja_env.filters["format_mttr"] = format_mttr
    app.jinja_env.globals["OUTCOME_LABELS"] = OUTCOME_LABELS
    app.jinja_env.globals["ACCURACY_LABELS"] = ACCURACY_LABELS
    app.jinja_env.globals["NOT_AN_ISSUE_LABELS"] = NOT_AN_ISSUE_LABELS

    # Register SLO template helpers
    from beeper_ui.services.slo_service import (
        condition_css_class,
        format_budget_remaining,
        format_burn_rate,
        format_compliance,
        format_percentage,
        format_projected_exhaustion,
    )

    app.jinja_env.globals["format_compliance"] = format_compliance
    app.jinja_env.globals["format_burn_rate"] = format_burn_rate
    app.jinja_env.globals["format_budget_remaining"] = format_budget_remaining
    app.jinja_env.globals["format_percentage"] = format_percentage
    app.jinja_env.globals["format_projected_exhaustion"] = format_projected_exhaustion
    app.jinja_env.globals["condition_css_class"] = condition_css_class

    # Register blueprints
    from beeper_ui.routes import register_blueprints

    register_blueprints(app)

    # Register root route
    @app.route("/")
    def index() -> str:
        """Render the main page."""
        return render_template("base.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host=app.config["UI_HOST"], port=app.config["UI_PORT"])
