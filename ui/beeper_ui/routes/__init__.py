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
