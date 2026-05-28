"""Tests for TopologyService."""

from unittest.mock import MagicMock, patch

from beeper_ui.services.topology_service import (
    ServiceDependency,
    ServiceNode,
    TopologyService,
)


def _make_service(qdrant_url="http://localhost:6333"):
    """Create a TopologyService for testing."""
    return TopologyService(qdrant_url=qdrant_url)


def _make_qdrant_record(
    service="payments",
    status="investigating",
    topology=None,
):
    """Create a mock Qdrant record with topology data."""
    record = MagicMock()
    findings = {}
    if topology:
        findings["service_topology"] = topology
    record.payload = {
        "service": service,
        "status": status,
        "findings": findings,
    }
    return record


class TestTopologyService:
    """Test TopologyService methods."""

    @patch("beeper_ui.services.topology_service.QdrantClient")
    def test_get_all_services_topology_empty(self, mock_qdrant_cls):
        """Empty Qdrant returns empty topology gracefully."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        mock_qdrant_cls.return_value = mock_client

        svc = _make_service()
        result = svc.get_all_services_topology()

        assert result["services"] == []
        assert result["dependencies"] == []
        assert result["active_investigations"] == {}

    @patch("beeper_ui.services.topology_service.QdrantClient")
    def test_get_all_services_topology_aggregates(self, mock_qdrant_cls):
        """Aggregates topology data from multiple investigations."""
        mock_client = MagicMock()
        records = [
            _make_qdrant_record(
                service="payments",
                status="investigating",
                topology={
                    "subject_service": "payments",
                    "upstream": ["orders"],
                    "downstream": ["frontend"],
                    "all_services": ["payments", "orders", "frontend"],
                    "dependencies": [
                        {"source_service": "payments", "target_service": "orders"},
                        {"source_service": "frontend", "target_service": "payments"},
                    ],
                    "health": {
                        "payments": {
                            "slo_status": "warning",
                            "has_active_investigation": True,
                            "burn_rate": 3.5,
                        },
                        "orders": {
                            "slo_status": "healthy",
                            "has_active_investigation": False,
                            "burn_rate": 0.5,
                        },
                    },
                    "blast_radius": 1,
                },
            ),
        ]
        mock_client.scroll.return_value = (records, None)
        mock_qdrant_cls.return_value = mock_client

        svc = _make_service()
        result = svc.get_all_services_topology()

        assert len(result["services"]) == 3
        assert len(result["dependencies"]) == 2
        assert result["active_investigations"]["payments"] == 1

        # Check service node properties
        svc_names = {s.name for s in result["services"]}
        assert svc_names == {"payments", "orders", "frontend"}

        payments_node = next(s for s in result["services"] if s.name == "payments")
        assert payments_node.slo_status == "warning"
        assert payments_node.has_active_investigation is True
        assert payments_node.burn_rate == 3.5

    @patch("beeper_ui.services.topology_service.QdrantClient")
    def test_get_all_services_topology_qdrant_error(self, mock_qdrant_cls):
        """Qdrant error returns empty topology gracefully."""
        mock_client = MagicMock()
        mock_client.scroll.side_effect = Exception("Qdrant unavailable")
        mock_qdrant_cls.return_value = mock_client

        svc = _make_service()
        result = svc.get_all_services_topology()

        assert result["services"] == []
        assert result["dependencies"] == []

    @patch("beeper_ui.services.topology_service.QdrantClient")
    def test_get_service_dependencies_success(self, mock_qdrant_cls):
        """Returns upstream/downstream for a specific service."""
        mock_client = MagicMock()
        records = [
            _make_qdrant_record(
                service="payments",
                topology={
                    "subject_service": "payments",
                    "upstream": ["orders", "db"],
                    "downstream": ["frontend"],
                    "health": {"orders": {"slo_status": "healthy"}},
                    "blast_radius": 1,
                },
            ),
        ]
        mock_client.scroll.return_value = (records, None)
        mock_qdrant_cls.return_value = mock_client

        svc = _make_service()
        result = svc.get_service_dependencies("payments")

        assert result["upstream"] == ["orders", "db"]
        assert result["downstream"] == ["frontend"]
        assert result["blast_radius"] == 1

    @patch("beeper_ui.services.topology_service.QdrantClient")
    def test_get_service_dependencies_no_topology(self, mock_qdrant_cls):
        """Returns empty when no topology data available for service."""
        mock_client = MagicMock()
        record = _make_qdrant_record(service="payments", topology=None)
        mock_client.scroll.return_value = ([record], None)
        mock_qdrant_cls.return_value = mock_client

        svc = _make_service()
        result = svc.get_service_dependencies("payments")

        assert result["upstream"] == []
        assert result["downstream"] == []
        assert result["blast_radius"] == 0

    @patch("beeper_ui.services.topology_service.QdrantClient")
    def test_get_service_dependencies_qdrant_error(self, mock_qdrant_cls):
        """Qdrant error returns empty gracefully."""
        mock_client = MagicMock()
        mock_client.scroll.side_effect = Exception("Qdrant down")
        mock_qdrant_cls.return_value = mock_client

        svc = _make_service()
        result = svc.get_service_dependencies("payments")

        assert result["upstream"] == []
        assert result["downstream"] == []
        assert result["blast_radius"] == 0


class TestServiceNodeDataclass:
    """Test ServiceNode dataclass defaults."""

    def test_defaults(self):
        node = ServiceNode(name="test")
        assert node.slo_status == "healthy"
        assert node.has_active_investigation is False
        assert node.burn_rate is None
        assert node.upstream_count == 0
        assert node.downstream_count == 0


class TestServiceDependencyDataclass:
    """Test ServiceDependency dataclass defaults."""

    def test_defaults(self):
        dep = ServiceDependency(source_service="a", target_service="b")
        assert dep.dependency_type == "endpoint"
        assert dep.port is None
