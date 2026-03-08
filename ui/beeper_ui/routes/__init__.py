"""Beeper UI routes package."""

from flask import Flask


def register_blueprints(app: Flask) -> None:
    """Register all blueprints with the Flask application.

    Args:
        app: Flask application instance.
    """
    from beeper_ui.routes.health import health_bp
    from beeper_ui.routes.investigations import investigations_bp
    from beeper_ui.routes.knowledge import knowledge_bp
    from beeper_ui.routes.metrics import metrics_bp
    from beeper_ui.routes.sources import sources_bp
    from beeper_ui.routes.spending import spending_bp

    app.register_blueprint(sources_bp)
    app.register_blueprint(investigations_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(metrics_bp)
    app.register_blueprint(spending_bp)
