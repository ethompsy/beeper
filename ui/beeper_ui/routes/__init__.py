"""Beeper UI routes package."""

from flask import Flask


def register_blueprints(app: Flask) -> None:
    """Register all blueprints with the Flask application.

    Args:
        app: Flask application instance.
    """
    from beeper_ui.routes.analytics import analytics_bp
    from beeper_ui.routes.confidence_gates import confidence_gates_bp
    from beeper_ui.routes.react_shell import react_shell_bp
    from beeper_ui.routes.handoff import handoff_bp
    from beeper_ui.routes.health import health_bp
    from beeper_ui.routes.investigations import (
        investigations_api_bp,
        investigations_bp,
    )
    from beeper_ui.routes.knowledge import knowledge_bp
    from beeper_ui.routes.metrics import metrics_bp
    from beeper_ui.routes.notification_config import notification_config_bp
    from beeper_ui.routes.notifications import notifications_bp
    from beeper_ui.routes.reports import reports_bp
    from beeper_ui.routes.services import services_bp
    from beeper_ui.routes.slo import slo_bp
    from beeper_ui.routes.sources import sources_bp
    from beeper_ui.routes.spending import spending_bp
    from beeper_ui.routes.topology import topology_bp
    from beeper_ui.routes.trust_config import trust_config_bp
    from beeper_ui.routes.trust_settings import trust_settings_bp

    app.register_blueprint(sources_bp)
    app.register_blueprint(investigations_bp)
    app.register_blueprint(investigations_api_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(metrics_bp)
    app.register_blueprint(spending_bp)
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
    # Task 1.1: React SPA shell (served at /app/*; full dispatch registry is Task 1.3)
    app.register_blueprint(react_shell_bp)
