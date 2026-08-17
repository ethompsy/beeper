"""Beeper UI routes package."""

from flask import Flask


def register_blueprints(app: Flask) -> None:
    """Register all blueprints with the Flask application.

    Args:
        app: Flask application instance.
    """
    from beeper_ui.routes.analytics import analytics_bp
    from beeper_ui.routes.confidence_gates import confidence_gates_bp
    from beeper_ui.routes.handoff import handoff_bp

    # `ingestion_api_bp` (Task 5.2: JSON BFF API for the React Ingestion Stats
    # view) added to the existing `health_bp` import — `ruff --fix`'s
    # import-sort rule merges same-module imports onto one line; see
    # ui/beeper_ui/routes/health.py for both blueprints.
    from beeper_ui.routes.health import health_bp, ingestion_api_bp
    from beeper_ui.routes.investigations import (
        investigations_api_bp,
        investigations_bp,
    )
    from beeper_ui.routes.knowledge import knowledge_api_bp, knowledge_bp
    from beeper_ui.routes.metrics import metrics_bp
    from beeper_ui.routes.notification_config import notification_config_bp
    from beeper_ui.routes.notifications import notifications_bp
    from beeper_ui.routes.react_registry import init_react_dispatch
    from beeper_ui.routes.react_shell import react_shell_bp
    from beeper_ui.routes.reports import reports_bp
    from beeper_ui.routes.services import services_bp
    from beeper_ui.routes.slo import slo_bp
    from beeper_ui.routes.socketio_gone import socketio_gone_bp
    from beeper_ui.routes.sources import sources_api_bp, sources_bp
    from beeper_ui.routes.spending import spending_api_bp, spending_bp
    from beeper_ui.routes.topology import topology_bp
    from beeper_ui.routes.trust_config import trust_config_bp
    from beeper_ui.routes.trust_settings import trust_settings_bp

    app.register_blueprint(sources_bp)
    app.register_blueprint(sources_api_bp)
    app.register_blueprint(investigations_bp)
    app.register_blueprint(investigations_api_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(knowledge_api_bp)
    app.register_blueprint(metrics_bp)
    app.register_blueprint(spending_bp)
    app.register_blueprint(spending_api_bp)
    app.register_blueprint(slo_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(notification_config_bp)
    app.register_blueprint(trust_config_bp)
    app.register_blueprint(trust_settings_bp)
    app.register_blueprint(confidence_gates_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(handoff_bp)
    app.register_blueprint(topology_bp)
    app.register_blueprint(services_bp)
    app.register_blueprint(analytics_bp)
    # Task 6.2a / ADR 0001 §0(b): defined 410 Gone response for the retired
    # SocketIO mount — replaces `init_socketio(app)` (removed from `app.py`).
    app.register_blueprint(socketio_gone_bp)
    # Task 5.2: JSON BFF API for the React Ingestion Stats view.
    app.register_blueprint(ingestion_api_bp)
    # Task 1.1: React SPA shell (served at /app/*)
    app.register_blueprint(react_shell_bp)

    # Task 1.3: explicit React-owned path-prefix dispatch registry.
    # Installs a before_request hook so a registered prefix deterministically
    # wins over any Jinja blueprint for the same path, regardless of the
    # blueprint registration order above. See react_registry.py for details.
    init_react_dispatch(app)

    # Task 5.4: JSON API blueprint for the React Metrics (MTTR Trends) view.
    # Added additively — see docs/plans/react-ui.md Task 5.0b's "shared files
    # edited additively only" contract for this file.
    from beeper_ui.routes.metrics import metrics_api_bp

    app.register_blueprint(metrics_api_bp)

    # Task 8.4: shared `GET /api/v1/auth/me` identity probe (ADR 0002 §3/§6).
    # Added additively, same pattern as `metrics_api_bp` above — Task 8.8
    # (SCIM, running in parallel) owns `routes/__init__.py` edits of its own
    # kind but this file's contract stays "append only" for both tasks.
    from beeper_ui.routes.auth import auth_api_bp

    app.register_blueprint(auth_api_bp)

    # Task 8.8 (ADR 0002 §1/§4): the SCIM 2.0 provisioning blueprint is
    # registered ONLY when BEEPER_SCIM_ENABLED is true — disabled ⇒ not
    # registered at all ⇒ /scim/v2/* 404s like any other undefined path
    # (never a fingerprintable surface). `validate_boot_config()` already
    # refuses BEEPER_SCIM_ENABLED=true outside `oidc` mode at boot (Task
    # 8.3), so this flag alone is sufficient here — by the time
    # register_blueprints() runs, `oidc` mode is guaranteed whenever this
    # is true. Bearer-token presence is NOT checked here (see ADR §8):
    # "enabled but unconfigured" is a per-request 403 inside the
    # blueprint's own `before_request` (beeper_ui.routes.scim
    # ._require_scim_bearer_auth`), not a registration-time refusal.
    if app.config.get("BEEPER_SCIM_ENABLED", False):
        from beeper_ui.routes.scim import scim_bp

        app.register_blueprint(scim_bp)

    # Task 8.5: browser-facing OIDC login (`GET /auth/login|callback`,
    # `POST /auth/logout`) — ADR 0002 §1/§3. Registered ONLY in `oidc` mode,
    # mirroring the SCIM blueprint's (Task 8.8) "disabled ⇒ plain 404, no
    # fingerprintable surface" pattern and the local-auth (Task 8.6)
    # "registered only in local mode" pattern. The Authlib OAuth client is
    # constructed here too (`init_oidc_client()`) but touches the network
    # only lazily, on first `/auth/login` hit — `none`/`local` mode boots
    # never construct it at all.
    if app.config.get("BEEPER_AUTH_MODE") == "oidc":
        from beeper_ui.routes.oidc_auth import auth_bp, init_oidc_client

        init_oidc_client(app)
        app.register_blueprint(auth_bp)

    # Task 8.6: local login/logout (ADR 0002 §6, FR59). Both conditionally
    # registered on `BEEPER_AUTH_MODE` — a request to an unregistered route
    # 404s outright, rather than 403ing at request time — mirroring how the
    # (future, Task 8.8) SCIM blueprint's registration is mode-gated. See
    # `beeper_ui/routes/auth.py`'s module docstring for the full
    # local-only-vs-both-session-modes registration rationale for each of
    # the two blueprints below.
    from beeper_ui.routes.auth import local_auth_api_bp, session_auth_api_bp

    auth_mode = app.config.get("BEEPER_AUTH_MODE", "none")
    if auth_mode == "local":
        app.register_blueprint(local_auth_api_bp)
    if auth_mode in {"local", "oidc"}:
        app.register_blueprint(session_auth_api_bp)

    # Task 8.7 (ADR 0002 §6/§5.2, FR60): the admin users management API.
    # Registered whenever BEEPER_AUTH_MODE != "none" — BOTH `local` and
    # `oidc` (not `local`-only) — see `routes/admin_users.py`'s module
    # docstring for the full registration rationale (the SCIM-owned
    # read-only behavior it implements is only meaningful if the view is
    # reachable in `oidc` mode too). Never registered in mode `none`: no
    # identity store exists there, and this blueprint's routes touch
    # `get_identity_store()`, which must never be constructed in that mode.
    if auth_mode in {"local", "oidc"}:
        from beeper_ui.routes.admin_users import admin_users_api_bp

        app.register_blueprint(admin_users_api_bp)
