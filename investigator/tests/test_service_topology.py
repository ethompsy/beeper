"""Tests for ServiceTopologyStep."""

from unittest.mock import MagicMock, patch

from kubernetes.client.rest import ApiException

from beeper_investigator.context import InvestigationContext
from beeper_investigator.steps.service_topology import (
    _NO_TOPOLOGY_SUMMARY,
    MAX_DEPENDENCY_DEPTH,
    ServiceTopologyStep,
)


def _make_context(
    *,
    service: str = "payments",
    namespace: str = "default",
) -> InvestigationContext:
    return InvestigationContext(
        investigation_id="inv-test-001",
        namespace=namespace,
        condition="High error rate on /checkout",
        service=service,
        severity="high",
    )


def _make_step(
    *,
    service: str = "payments",
    namespace: str = "default",
) -> ServiceTopologyStep:
    context = _make_context(service=service, namespace=namespace)
    return ServiceTopologyStep(
        llm_client=MagicMock(),
        context=context,
        status_updater=MagicMock(),
        pipeline_metadata={},
    )


def _make_k8s_service(name, namespace="default", selectors=None, ports=None, labels=None):
    """Create a mock K8s service object."""
    svc = MagicMock()
    svc.metadata.name = name
    svc.metadata.namespace = namespace
    svc.metadata.labels = labels or {"app": name}
    svc.spec.selector = selectors or {"app": name}
    svc.spec.cluster_ip = f"10.0.0.{hash(name) % 255}"
    if ports is None:
        port = MagicMock()
        port.port = 8080
        port.target_port = 8080
        port.protocol = "TCP"
        svc.spec.ports = [port]
    else:
        svc.spec.ports = ports
    return svc


def _make_endpoint(name, pod_names=None):
    """Create a mock K8s endpoint object."""
    ep = MagicMock()
    ep.metadata.name = name
    if pod_names:
        addresses = []
        for pname in pod_names:
            addr = MagicMock()
            addr.target_ref = MagicMock()
            addr.target_ref.kind = "Pod"
            addr.target_ref.name = pname
            addresses.append(addr)
        subset = MagicMock()
        subset.addresses = addresses
        port = MagicMock()
        port.port = 8080
        subset.ports = [port]
        ep.subsets = [subset]
    else:
        ep.subsets = []
    return ep


class TestServiceTopologyStep:
    """Test the ServiceTopologyStep pipeline step."""

    def test_step_name(self):
        """Step has correct name attribute."""
        step = _make_step()
        assert step.name == "Service Topology"

    def test_max_dependency_depth_is_2(self):
        """MAX_DEPENDENCY_DEPTH constant is 2."""
        assert MAX_DEPENDENCY_DEPTH == 2

    @patch("beeper_investigator.steps.service_topology.config")
    @patch("beeper_investigator.steps.service_topology.client")
    def test_k8s_init_failure_returns_empty(self, mock_client, mock_config):
        """When K8s init fails, return empty topology gracefully."""
        mock_config.load_incluster_config.side_effect = Exception("No cluster")
        mock_config.load_kube_config.side_effect = Exception("No kubeconfig")

        step = _make_step()
        result = step.execute()

        assert result.success is True
        assert result.data["topology_discovery_attempted"] is True
        assert result.data["service_topology"] == {}
        assert result.summary == _NO_TOPOLOGY_SUMMARY

    @patch("beeper_investigator.steps.service_topology.config")
    @patch("beeper_investigator.steps.service_topology.client")
    def test_empty_namespace_returns_empty(self, mock_client, mock_config):
        """When no services found in namespace, return empty topology."""
        mock_config.load_incluster_config.return_value = None
        mock_core = MagicMock()
        svc_list = MagicMock()
        svc_list.items = []
        mock_core.list_namespaced_service.return_value = svc_list
        mock_client.CoreV1Api.return_value = mock_core
        mock_client.CustomObjectsApi.return_value = MagicMock()

        step = _make_step()
        result = step.execute()

        assert result.success is True
        assert result.data["service_topology"] == {}
        assert result.summary == _NO_TOPOLOGY_SUMMARY

    @patch("beeper_investigator.steps.service_topology.config")
    @patch("beeper_investigator.steps.service_topology.client")
    def test_successful_topology_discovery(self, mock_client, mock_config):
        """Successful discovery with services and dependencies."""
        mock_config.load_incluster_config.return_value = None

        # Mock services
        mock_core = MagicMock()
        svc_list = MagicMock()
        svc_list.items = [
            _make_k8s_service("payments"),
            _make_k8s_service("orders"),
            _make_k8s_service("users"),
        ]
        mock_core.list_namespaced_service.return_value = svc_list

        # Mock endpoints — payments pod references orders
        ep_list = MagicMock()
        ep_list.items = [
            _make_endpoint("payments", pod_names=["payments-pod-1"]),
            _make_endpoint("orders"),
            _make_endpoint("users"),
        ]
        mock_core.list_namespaced_endpoints.return_value = ep_list

        # Mock pod env vars — payments depends on orders
        pod = MagicMock()
        container = MagicMock()
        env1 = MagicMock()
        env1.value = "http://orders:8080"
        container.env = [env1]
        pod.spec.containers = [container]
        mock_core.read_namespaced_pod.return_value = pod

        mock_client.CoreV1Api.return_value = mock_core

        # Mock CRDs — no ServiceLevels or Investigations
        mock_custom = MagicMock()
        mock_custom.list_namespaced_custom_object.return_value = {"items": []}
        mock_client.CustomObjectsApi.return_value = mock_custom

        step = _make_step(service="payments")
        result = step.execute()

        assert result.success is True
        topo = result.data["service_topology"]
        assert topo["subject_service"] == "payments"
        assert "orders" in topo["upstream"]
        assert len(topo["all_services"]) == 3
        assert topo["blast_radius"] >= 0
        assert topo["discovery_timestamp"]
        assert result.data["topology_discovery_attempted"] is True

    @patch("beeper_investigator.steps.service_topology.config")
    @patch("beeper_investigator.steps.service_topology.client")
    def test_k8s_api_error_handled_gracefully(self, mock_client, mock_config):
        """K8s API error during service listing handled gracefully."""
        mock_config.load_incluster_config.return_value = None

        mock_core = MagicMock()
        mock_core.list_namespaced_service.side_effect = ApiException(status=403, reason="Forbidden")
        mock_client.CoreV1Api.return_value = mock_core
        mock_client.CustomObjectsApi.return_value = MagicMock()

        step = _make_step()
        result = step.execute()

        assert result.success is True
        assert result.data["service_topology"] == {}

    @patch("beeper_investigator.steps.service_topology.config")
    @patch("beeper_investigator.steps.service_topology.client")
    def test_health_status_from_servicelevels(self, mock_client, mock_config):
        """Health status extracted from ServiceLevel CRDs."""
        mock_config.load_incluster_config.return_value = None

        mock_core = MagicMock()
        svc_list = MagicMock()
        svc_list.items = [_make_k8s_service("payments")]
        mock_core.list_namespaced_service.return_value = svc_list

        ep_list = MagicMock()
        ep_list.items = []
        mock_core.list_namespaced_endpoints.return_value = ep_list
        mock_client.CoreV1Api.return_value = mock_core

        # ServiceLevel with high burn rate = critical
        mock_custom = MagicMock()
        mock_custom.list_namespaced_custom_object.side_effect = [
            {"items": [{
                "spec": {"service": "payments"},
                "status": {"burnRate": 15.0, "compliance": 0.92},
            }]},
            {"items": []},  # No active investigations
        ]
        mock_client.CustomObjectsApi.return_value = mock_custom

        step = _make_step(service="payments")
        result = step.execute()

        assert result.success is True
        topo = result.data["service_topology"]
        assert topo["health"]["payments"]["slo_status"] == "critical"
        assert topo["health"]["payments"]["burn_rate"] == 15.0

    @patch("beeper_investigator.steps.service_topology.config")
    @patch("beeper_investigator.steps.service_topology.client")
    def test_active_investigation_detection(self, mock_client, mock_config):
        """Active investigations are detected in health data."""
        mock_config.load_incluster_config.return_value = None

        mock_core = MagicMock()
        svc_list = MagicMock()
        svc_list.items = [_make_k8s_service("payments")]
        mock_core.list_namespaced_service.return_value = svc_list

        ep_list = MagicMock()
        ep_list.items = []
        mock_core.list_namespaced_endpoints.return_value = ep_list
        mock_client.CoreV1Api.return_value = mock_core

        mock_custom = MagicMock()
        mock_custom.list_namespaced_custom_object.side_effect = [
            {"items": []},  # No ServiceLevels
            {"items": [{
                "spec": {"service": "payments"},
                "status": {"phase": "investigating"},
            }]},
        ]
        mock_client.CustomObjectsApi.return_value = mock_custom

        step = _make_step(service="payments")
        result = step.execute()

        assert result.success is True
        topo = result.data["service_topology"]
        assert topo["health"]["payments"]["has_active_investigation"] is True


class TestBFS:
    """Test the BFS traversal used for topology classification."""

    def test_single_level(self):
        adjacency = {"A": ["B", "C"]}
        result = ServiceTopologyStep._bfs("A", adjacency, 2)
        assert set(result) == {"B", "C"}

    def test_multi_level_within_depth(self):
        adjacency = {"A": ["B"], "B": ["C"]}
        result = ServiceTopologyStep._bfs("A", adjacency, 2)
        assert set(result) == {"B", "C"}

    def test_depth_limit(self):
        adjacency = {"A": ["B"], "B": ["C"], "C": ["D"]}
        result = ServiceTopologyStep._bfs("A", adjacency, 2)
        assert set(result) == {"B", "C"}
        assert "D" not in result

    def test_no_neighbors(self):
        adjacency = {}
        result = ServiceTopologyStep._bfs("A", adjacency, 2)
        assert result == []

    def test_cycle_handling(self):
        adjacency = {"A": ["B"], "B": ["A"]}
        result = ServiceTopologyStep._bfs("A", adjacency, 2)
        assert result == ["B"]


class TestClassifyTopology:
    """Test topology classification into upstream/downstream."""

    def test_upstream_and_downstream(self):
        """Test correct upstream/downstream classification."""
        step = _make_step(service="B")
        services = [{"name": n} for n in ["A", "B", "C"]]
        deps = [
            {"source_service": "B", "target_service": "A"},  # B depends on A
            {"source_service": "C", "target_service": "B"},  # C depends on B
        ]
        result = step._classify_topology(services, deps)
        assert "A" in result["upstream"]
        assert "C" in result["downstream"]
        assert result["blast_radius"] == 1

    def test_no_dependencies(self):
        """No dependencies means empty upstream/downstream."""
        step = _make_step(service="A")
        services = [{"name": "A"}]
        result = step._classify_topology(services, [])
        assert result["upstream"] == []
        assert result["downstream"] == []
        assert result["blast_radius"] == 0


class TestFormatTopologySummary:
    """Test human-readable topology summary formatting."""

    def test_summary_with_dependencies(self):
        step = _make_step()
        topology = {
            "subject_service": "payments",
            "upstream": ["orders"],
            "downstream": ["frontend", "mobile"],
            "blast_radius": 2,
            "health": {},
        }
        result = step._format_topology_summary(topology)
        assert "payments" in result
        assert "1 upstream" in result
        assert "2 downstream" in result
        assert "Blast radius: 2" in result

    def test_summary_with_unhealthy(self):
        step = _make_step()
        topology = {
            "subject_service": "payments",
            "upstream": [],
            "downstream": [],
            "blast_radius": 0,
            "health": {
                "orders": {"slo_status": "critical", "has_active_investigation": False},
            },
        }
        result = step._format_topology_summary(topology)
        assert "orders" in result
        assert "Unhealthy" in result

    def test_summary_no_blast_radius(self):
        step = _make_step()
        topology = {
            "subject_service": "payments",
            "upstream": ["orders"],
            "downstream": [],
            "blast_radius": 0,
            "health": {},
        }
        result = step._format_topology_summary(topology)
        assert "Blast radius" not in result
