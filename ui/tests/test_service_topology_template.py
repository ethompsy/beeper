"""Tests for service topology investigation detail template."""

import pytest

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig


@pytest.fixture
def app():
    """Create test application."""
    app = create_app(TestingConfig)
    yield app


def _render_template(app, service_topology=None):
    """Render the service topology investigation detail template."""
    with app.app_context():
        template = app.jinja_env.get_template(
            "investigations/_service_topology.html"
        )
        return template.render(service_topology=service_topology)


class TestServiceTopologyTemplate:
    """Test service topology card template rendering."""

    def test_renders_with_topology_data(self, app):
        """Topology card renders with upstream/downstream lists."""
        topology = {
            "subject_service": "payments",
            "upstream": ["orders", "db"],
            "downstream": ["frontend"],
            "health": {
                "orders": {"slo_status": "healthy", "has_active_investigation": False},
                "db": {"slo_status": "warning", "has_active_investigation": False},
                "frontend": {"slo_status": "healthy", "has_active_investigation": False},
            },
            "blast_radius": 1,
        }
        html = _render_template(app, service_topology=topology)

        assert "service-topology-card" in html
        assert "payments" in html
        assert "orders" in html
        assert "db" in html
        assert "frontend" in html

    def test_blast_radius_displayed(self, app):
        """Blast radius count is displayed."""
        topology = {
            "subject_service": "payments",
            "upstream": [],
            "downstream": ["frontend", "mobile"],
            "health": {},
            "blast_radius": 2,
        }
        html = _render_template(app, service_topology=topology)

        assert "Blast radius: 2 services" in html

    def test_blast_radius_singular(self, app):
        """Blast radius of 1 uses singular form."""
        topology = {
            "subject_service": "payments",
            "upstream": [],
            "downstream": ["frontend"],
            "health": {},
            "blast_radius": 1,
        }
        html = _render_template(app, service_topology=topology)

        assert "Blast radius: 1 service" in html
        # Should NOT have "services" (plural)
        assert "1 services" not in html

    def test_health_badges_rendered(self, app):
        """Health badges show correct status classes."""
        topology = {
            "subject_service": "payments",
            "upstream": ["orders"],
            "downstream": ["frontend"],
            "health": {
                "orders": {"slo_status": "critical", "has_active_investigation": False},
                "frontend": {"slo_status": "healthy", "has_active_investigation": True},
            },
            "blast_radius": 1,
        }
        html = _render_template(app, service_topology=topology)

        assert "health-critical" in html
        assert "health-healthy" in html
        assert "topology-investigation-indicator" in html

    def test_no_topology_fallback(self, app):
        """No topology data shows fallback message."""
        html = _render_template(app, service_topology=None)

        assert "topology-no-data" in html
        assert "Topology data not available" in html

    def test_empty_topology_fallback(self, app):
        """Empty topology dict shows fallback message."""
        html = _render_template(app, service_topology={})

        assert "topology-no-data" in html
        assert "Topology data not available" in html

    def test_no_upstream_shows_message(self, app):
        """Empty upstream list shows informational message."""
        topology = {
            "subject_service": "payments",
            "upstream": [],
            "downstream": ["frontend"],
            "health": {},
            "blast_radius": 1,
        }
        html = _render_template(app, service_topology=topology)

        assert "No upstream dependencies found" in html

    def test_no_downstream_shows_message(self, app):
        """Empty downstream list shows informational message."""
        topology = {
            "subject_service": "payments",
            "upstream": ["orders"],
            "downstream": [],
            "health": {},
            "blast_radius": 0,
        }
        html = _render_template(app, service_topology=topology)

        assert "No downstream dependents found" in html

    def test_upstream_and_downstream_counts(self, app):
        """Upstream and downstream counts shown in headers."""
        topology = {
            "subject_service": "payments",
            "upstream": ["orders", "db"],
            "downstream": ["frontend"],
            "health": {},
            "blast_radius": 1,
        }
        html = _render_template(app, service_topology=topology)

        assert "Upstream Dependencies (2)" in html
        assert "Downstream Dependents (1)" in html
