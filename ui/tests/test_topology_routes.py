"""Tests for topology routes."""

from unittest.mock import MagicMock, patch

import pytest
from flask.testing import FlaskClient

from beeper_ui.services.topology_service import ServiceDependency, ServiceNode


class TestTopologyRoutes:
    """Tests for /topology routes."""

    @patch("beeper_ui.routes.topology.get_topology_service")
    def test_index_renders_page(self, mock_get_svc, client: FlaskClient):
        """GET /topology/ renders the topology page."""
        mock_svc = MagicMock()
        mock_svc.get_all_services_topology.return_value = {
            "services": [],
            "dependencies": [],
            "active_investigations": {},
        }
        mock_get_svc.return_value = mock_svc

        response = client.get("/topology/")
        assert response.status_code == 200
        html = response.data.decode()
        assert "Service Dependency Topology" in html

    @patch("beeper_ui.routes.topology.get_topology_service")
    def test_index_with_services(self, mock_get_svc, client: FlaskClient):
        """Service cards render with health badges."""
        mock_svc = MagicMock()
        mock_svc.get_all_services_topology.return_value = {
            "services": [
                ServiceNode(name="payments", slo_status="warning", upstream_count=1, downstream_count=2),
                ServiceNode(name="orders", slo_status="healthy"),
            ],
            "dependencies": [],
            "active_investigations": {},
        }
        mock_get_svc.return_value = mock_svc

        response = client.get("/topology/")
        assert response.status_code == 200
        html = response.data.decode()
        assert "payments" in html
        assert "orders" in html
        assert "health-warning" in html
        assert "health-healthy" in html
        assert "1 upstream" in html
        assert "2 downstream" in html

    @patch("beeper_ui.routes.topology.get_topology_service")
    def test_index_with_dependencies(self, mock_get_svc, client: FlaskClient):
        """Dependency graph table renders."""
        mock_svc = MagicMock()
        mock_svc.get_all_services_topology.return_value = {
            "services": [
                ServiceNode(name="payments"),
                ServiceNode(name="orders"),
            ],
            "dependencies": [
                {"source_service": "payments", "target_service": "orders", "dependency_type": "env_var", "port": 8080},
            ],
            "active_investigations": {},
        }
        mock_get_svc.return_value = mock_svc

        response = client.get("/topology/")
        assert response.status_code == 200
        html = response.data.decode()
        assert "topology-dep-table" in html
        assert "env_var" in html

    @patch("beeper_ui.routes.topology.get_topology_service")
    def test_index_htmx_returns_partial(self, mock_get_svc, client: FlaskClient):
        """HTMX request returns only the topology content partial."""
        mock_svc = MagicMock()
        mock_svc.get_all_services_topology.return_value = {
            "services": [],
            "dependencies": [],
            "active_investigations": {},
        }
        mock_get_svc.return_value = mock_svc

        response = client.get("/topology/", headers={"HX-Request": "true"})
        assert response.status_code == 200
        html = response.data.decode()
        # Partial should not include base.html elements like <!DOCTYPE
        assert "<!DOCTYPE" not in html

    @patch("beeper_ui.routes.topology.get_topology_service")
    def test_index_empty_shows_no_data(self, mock_get_svc, client: FlaskClient):
        """Empty topology shows informational message."""
        mock_svc = MagicMock()
        mock_svc.get_all_services_topology.return_value = {
            "services": [],
            "dependencies": [],
            "active_investigations": {},
        }
        mock_get_svc.return_value = mock_svc

        response = client.get("/topology/")
        assert response.status_code == 200
        html = response.data.decode()
        assert "topology-no-data" in html
        assert "No topology data available" in html

    @patch("beeper_ui.routes.topology.get_topology_service")
    def test_index_with_active_investigation(self, mock_get_svc, client: FlaskClient):
        """Active investigation indicator renders."""
        mock_svc = MagicMock()
        mock_svc.get_all_services_topology.return_value = {
            "services": [
                ServiceNode(name="payments", has_active_investigation=True),
            ],
            "dependencies": [],
            "active_investigations": {"payments": 1},
        }
        mock_get_svc.return_value = mock_svc

        response = client.get("/topology/")
        assert response.status_code == 200
        html = response.data.decode()
        assert "topology-investigation-indicator" in html
        assert "investigating" in html

    @patch("beeper_ui.routes.topology.get_topology_service")
    def test_index_service_error_handled(self, mock_get_svc, client: FlaskClient):
        """TopologyServiceError is handled gracefully."""
        from beeper_ui.services.topology_service import TopologyServiceError
        mock_get_svc.return_value.get_all_services_topology.side_effect = TopologyServiceError("Qdrant down")

        response = client.get("/topology/")
        assert response.status_code == 200
        html = response.data.decode()
        assert "topology-no-data" in html

    @patch("beeper_ui.routes.topology.get_topology_service")
    def test_burn_rate_displayed(self, mock_get_svc, client: FlaskClient):
        """Burn rate is displayed when available."""
        mock_svc = MagicMock()
        mock_svc.get_all_services_topology.return_value = {
            "services": [
                ServiceNode(name="payments", burn_rate=5.2),
            ],
            "dependencies": [],
            "active_investigations": {},
        }
        mock_get_svc.return_value = mock_svc

        response = client.get("/topology/")
        assert response.status_code == 200
        html = response.data.decode()
        assert "5.2x" in html

    @pytest.mark.xfail(
        strict=True,
        reason="Top-nav removed in Story 3.2 layout shell migration. The old "
        "top-bar `Topology` link no longer exists in base.html. Story 3.3 "
        "introduces sidebar nav with different macro markup. When that lands "
        "this test becomes XPASS — REWRITE the assertion against the new "
        "sidebar HTML and remove this xfail marker.",
    )
    @patch("beeper_ui.routes.topology.get_topology_service")
    def test_topology_nav_link_visible(self, mock_get_svc, client: FlaskClient):
        """Topology link is present in main navigation."""
        mock_svc = MagicMock()
        mock_svc.get_all_services_topology.return_value = {
            "services": [],
            "dependencies": [],
            "active_investigations": {},
        }
        mock_get_svc.return_value = mock_svc

        response = client.get("/topology/")
        assert response.status_code == 200
        html = response.data.decode()
        assert 'href="/topology/"' in html
        assert ">Topology<" in html
