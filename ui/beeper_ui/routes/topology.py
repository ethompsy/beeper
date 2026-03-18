"""Topology routes for Beeper UI."""

import logging

from flask import Blueprint, render_template, request

from beeper_ui.services.topology_service import (
    TopologyServiceError,
    get_topology_service,
)

logger = logging.getLogger(__name__)

topology_bp = Blueprint("topology", __name__, url_prefix="/topology")


@topology_bp.route("/")
def index() -> str | tuple[str, int]:
    """Render the service dependency topology page."""
    try:
        svc = get_topology_service()
        topology_data = svc.get_all_services_topology()
    except TopologyServiceError as exc:
        logger.warning("Failed to load topology: %s", exc)
        topology_data = {"services": [], "dependencies": [], "active_investigations": {}}

    services = topology_data.get("services", [])
    dependencies = topology_data.get("dependencies", [])
    active_investigations = topology_data.get("active_investigations", {})

    if request.headers.get("HX-Request"):
        return render_template(
            "topology/_topology_content.html",
            services=services,
            dependencies=dependencies,
            active_investigations=active_investigations,
        )

    return render_template(
        "topology/index.html",
        services=services,
        dependencies=dependencies,
        active_investigations=active_investigations,
    )
