"""Beeper UI Flask application factory."""

from flask import Flask, render_template

from beeper_ui.config import get_config
from beeper_ui.middleware.permissions import init_permissions
from beeper_ui.utils import setup_markdown_filter


def create_app(config_class: type | None = None) -> Flask:
    """Create and configure the Flask application.

    Args:
        config_class: Optional configuration class to use. If not provided,
                     the configuration is determined from the FLASK_ENV environment variable.

    Returns:
        Configured Flask application instance.
    """
    app = Flask(__name__)

    # Load configuration
    if config_class is None:
        config_class = get_config()
    app.config.from_object(config_class)

    # Register permission middleware (before_request role resolver)
    init_permissions(app)

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

    # Initialize WebSocket support (Flask-SocketIO)
    from beeper_ui.websocket import init_socketio

    init_socketio(app)

    # Register root route
    @app.route("/")
    def index() -> str:
        """Render the main page."""
        return render_template("base.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host=app.config["UI_HOST"], port=app.config["UI_PORT"])
