"""Beeper UI routes package."""

from flask import Flask


def register_blueprints(app: Flask) -> None:
    """Register all blueprints with the Flask application.

    Args:
        app: Flask application instance.
    """
    from beeper_ui.routes.health import health_bp
    from beeper_ui.routes.sources import sources_bp

    app.register_blueprint(sources_bp)
    app.register_blueprint(health_bp)
