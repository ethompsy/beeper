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
        """Health status extracted from ServiceLevel CRDs + Qdrant snapshot."""
        mock_config.load_incluster_config.return_value = None

        mock_core = MagicMock()
        svc_list = MagicMock()
        svc_list.items = [_make_k8s_service("payments")]
        mock_core.list_namespaced_service.return_value = svc_list

        ep_list = MagicMock()
        ep_list.items = []
        mock_core.list_namespaced_endpoints.return_value = ep_list
        mock_client.CoreV1Api.return_value = mock_core

        # ServiceLevel CRD with correct spec/status fields
        mock_custom = MagicMock()
        mock_custom.list_namespaced_custom_object.side_effect = [
            {"items": [{
                "spec": {
                    "service": "payments",
                    "sli": {"type": "availability"},
                    "objective": {"target": 0.999, "window": "30m"},
                },
                "status": {"condition": "Critical", "alerts_registered": 2},
            }]},
            {"items": []},  # No active investigations
        ]
        mock_client.CustomObjectsApi.return_value = mock_custom

        step = _make_step(service="payments")

        # Mock Qdrant snapshots with high burn rate
        snapshots = {"payments": {"compliance": 0.92, "burn_rate": 15.0, "error_budget_remaining": 0.0}}
        with patch.object(step, "_query_slo_snapshots", return_value=snapshots):
            result = step.execute()

        assert result.success is True
        topo = result.data["service_topology"]
        assert topo["health"]["payments"]["slo_status"] == "critical"
        assert topo["health"]["payments"]["burn_rate"] == 15.0
        assert topo["health"]["payments"]["slo_target"] == 0.999
        assert topo["health"]["payments"]["slo_compliance"] == 0.92
        # SLO data should also appear in result.data for pipeline propagation
        assert result.data.get("slo_target") == 0.999
        assert result.data.get("slo_burn_rate") == 15.0

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


class TestGetPodServiceReferences:
    """Test hostname-based service reference matching in env vars."""

    def test_matches_url_hostname(self):
        """Service name in URL is matched (e.g., http://orders:8080)."""
        step = _make_step()
        step._core_api = MagicMock()
        pod = MagicMock()
        container = MagicMock()
        env = MagicMock()
        env.value = "http://orders:8080/api"
        container.env = [env]
        pod.spec.containers = [container]
        step._core_api.read_namespaced_pod.return_value = pod

        refs = step._get_pod_service_references("payments-pod", {"orders", "db"})
        assert ("orders", "env_var") in refs

    def test_rejects_substring_false_positive(self):
        """Service name 'db' should NOT match env var 'DEBUG=true'."""
        step = _make_step()
        step._core_api = MagicMock()
        pod = MagicMock()
        container = MagicMock()
        env = MagicMock()
        env.value = "DEBUG=true"
        container.env = [env]
        pod.spec.containers = [container]
        step._core_api.read_namespaced_pod.return_value = pod

        refs = step._get_pod_service_references("payments-pod", {"db"})
        assert refs == []

    def test_matches_dns_hostname(self):
        """Service name as K8s DNS hostname (orders.default.svc)."""
        step = _make_step()
        step._core_api = MagicMock()
        pod = MagicMock()
        container = MagicMock()
        env = MagicMock()
        env.value = "orders.default.svc.cluster.local:8080"
        container.env = [env]
        pod.spec.containers = [container]
        step._core_api.read_namespaced_pod.return_value = pod

        refs = step._get_pod_service_references("payments-pod", {"orders"})
        assert ("orders", "env_var") in refs


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


# ── SLO Data Integration Tests (Story 2.5) ──────────────────


class TestSLOCRDFieldExtraction:
    """Test that _get_service_health reads correct CRD fields (not old burnRate/compliance)."""

    def test_reads_spec_target_and_sli_type(self):
        """spec.objective.target and spec.sli.type are extracted."""
        step = _make_step()
        step._custom_api = MagicMock()
        step._custom_api.list_namespaced_custom_object.side_effect = [
            {"items": [{
                "spec": {
                    "service": "checkout",
                    "sli": {"type": "availability"},
                    "objective": {"target": 0.999},
                },
                "status": {"condition": "Healthy"},
            }]},
            {"items": []},
        ]
        with patch.object(step, "_query_slo_snapshots", return_value={}):
            health = step._get_service_health()

        assert health["checkout"]["slo_target"] == 0.999
        assert health["checkout"]["slo_sli_type"] == "availability"
        assert health["checkout"]["slo_condition"] == "Healthy"
        assert health["checkout"]["burn_rate"] is None  # No snapshot

    def test_skips_empty_service(self):
        """CRD items with empty service name are skipped."""
        step = _make_step()
        step._custom_api = MagicMock()
        step._custom_api.list_namespaced_custom_object.side_effect = [
            {"items": [{
                "spec": {"service": "", "sli": {"type": "availability"}, "objective": {"target": 0.99}},
                "status": {},
            }]},
            {"items": []},
        ]
        with patch.object(step, "_query_slo_snapshots", return_value={}):
            health = step._get_service_health()

        assert len(health) == 0


class TestQdrantSnapshotQuery:
    """Test _query_slo_snapshots batch query and Qdrant enrichment."""

    @patch("beeper_investigator.steps.service_topology.httpx.post")
    def test_successful_query(self, mock_post):
        """Successful Qdrant batch query returns dict keyed by service."""
        step = _make_step()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "result": {
                "points": [{
                    "id": 1,
                    "payload": {
                        "service": "checkout",
                        "compliance": 0.972,
                        "burn_rate": 28.0,
                        "error_budget_remaining": 0.0,
                    },
                }],
            }
        }
        mock_post.return_value = mock_resp

        result = step._query_slo_snapshots({"checkout"})
        assert "checkout" in result
        assert result["checkout"]["compliance"] == 0.972
        assert result["checkout"]["burn_rate"] == 28.0

    @patch("beeper_investigator.steps.service_topology.httpx.post")
    def test_no_points_returns_empty(self, mock_post):
        """Empty points list returns empty dict."""
        step = _make_step()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {"points": []}}
        mock_post.return_value = mock_resp

        assert step._query_slo_snapshots({"missing"}) == {}

    @patch("beeper_investigator.steps.service_topology.httpx.post")
    def test_connection_error_returns_empty(self, mock_post):
        """Connection failure returns empty dict gracefully."""
        step = _make_step()
        mock_post.side_effect = OSError("Connection refused")
        assert step._query_slo_snapshots({"checkout"}) == {}

    @patch("beeper_investigator.steps.service_topology.httpx.post")
    def test_non_200_returns_empty(self, mock_post):
        """Non-200 HTTP status returns empty dict."""
        step = _make_step()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_post.return_value = mock_resp
        assert step._query_slo_snapshots({"checkout"}) == {}

    @patch("beeper_investigator.steps.service_topology.httpx.post")
    def test_keeps_latest_per_service(self, mock_post):
        """When multiple points exist for a service, keeps only the first (latest)."""
        step = _make_step()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "result": {
                "points": [
                    {"id": 2, "payload": {"service": "checkout", "burn_rate": 28.0, "compliance": 0.97}},
                    {"id": 1, "payload": {"service": "checkout", "burn_rate": 5.0, "compliance": 0.99}},
                ],
            }
        }
        mock_post.return_value = mock_resp

        result = step._query_slo_snapshots({"checkout"})
        assert result["checkout"]["burn_rate"] == 28.0  # First point kept

    def test_enriches_health_with_snapshot(self):
        """Qdrant snapshot data flows into health dict."""
        step = _make_step()
        step._custom_api = MagicMock()
        step._custom_api.list_namespaced_custom_object.side_effect = [
            {"items": [{
                "spec": {
                    "service": "checkout",
                    "sli": {"type": "availability"},
                    "objective": {"target": 0.999},
                },
                "status": {"condition": "Critical"},
            }]},
            {"items": []},
        ]

        snapshots = {"checkout": {"compliance": 0.972, "burn_rate": 28.0, "error_budget_remaining": 0.0}}
        with patch.object(step, "_query_slo_snapshots", return_value=snapshots):
            health = step._get_service_health()

        assert health["checkout"]["burn_rate"] == 28.0
        assert health["checkout"]["slo_compliance"] == 0.972
        assert health["checkout"]["slo_error_budget_remaining"] == 0.0
        assert health["checkout"]["slo_status"] == "critical"

    def test_health_classification_warning(self):
        """Burn rate 1-10 yields warning status."""
        step = _make_step()
        step._custom_api = MagicMock()
        step._custom_api.list_namespaced_custom_object.side_effect = [
            {"items": [{
                "spec": {"service": "checkout", "sli": {"type": "availability"}, "objective": {"target": 0.999}},
                "status": {"condition": "Healthy"},
            }]},
            {"items": []},
        ]
        snapshots = {"checkout": {"compliance": 0.998, "burn_rate": 3.5, "error_budget_remaining": 0.5}}
        with patch.object(step, "_query_slo_snapshots", return_value=snapshots):
            health = step._get_service_health()

        assert health["checkout"]["slo_status"] == "warning"

    def test_health_classification_healthy(self):
        """Burn rate < 1 yields healthy status."""
        step = _make_step()
        step._custom_api = MagicMock()
        step._custom_api.list_namespaced_custom_object.side_effect = [
            {"items": [{
                "spec": {"service": "checkout", "sli": {"type": "availability"}, "objective": {"target": 0.999}},
                "status": {"condition": "Healthy"},
            }]},
            {"items": []},
        ]
        snapshots = {"checkout": {"compliance": 0.9995, "burn_rate": 0.5, "error_budget_remaining": 0.8}}
        with patch.object(step, "_query_slo_snapshots", return_value=snapshots):
            health = step._get_service_health()

        assert health["checkout"]["slo_status"] == "healthy"


class TestSLOPipelinePropagation:
    """Test that SLO data reaches StepResult.data for pipeline_metadata."""

    def test_slo_fields_in_result_data(self):
        """SLO fields appear in StepResult.data when CRD + snapshot exist."""
        step = _make_step(service="payments")
        step._core_api = MagicMock()
        step._custom_api = MagicMock()

        svc = _make_k8s_service("payments")
        step._core_api.list_namespaced_service.return_value = MagicMock(items=[svc])
        step._core_api.list_namespaced_endpoints.return_value = MagicMock(items=[])

        step._custom_api.list_namespaced_custom_object.side_effect = [
            {"items": [{
                "spec": {
                    "service": "payments",
                    "sli": {"type": "availability"},
                    "objective": {"target": 0.999},
                },
                "status": {"condition": "Critical"},
            }]},
            {"items": []},
        ]

        snapshots = {"payments": {"compliance": 0.92, "burn_rate": 15.0, "error_budget_remaining": 0.0}}
        with patch.object(step, "_query_slo_snapshots", return_value=snapshots):
            result = step.execute()

        assert result.data["slo_target"] == 0.999
        assert result.data["slo_compliance"] == 0.92
        assert result.data["slo_burn_rate"] == 15.0
        assert result.data["slo_error_budget_remaining"] == 0.0
        assert result.data["slo_sli_type"] == "availability"
        assert result.data["slo_condition"] == "Critical"

    def test_no_slo_when_no_crd(self):
        """SLO fields absent from result when no ServiceLevel CRD exists."""
        step = _make_step(service="unknown")
        step._core_api = MagicMock()
        step._custom_api = MagicMock()

        svc = _make_k8s_service("unknown")
        step._core_api.list_namespaced_service.return_value = MagicMock(items=[svc])
        step._core_api.list_namespaced_endpoints.return_value = MagicMock(items=[])

        step._custom_api.list_namespaced_custom_object.side_effect = [
            {"items": []},
            {"items": []},
        ]

        result = step.execute()

        assert result.success
        assert "slo_target" not in result.data
        assert "slo_burn_rate" not in result.data

    def test_extract_slo_for_service_returns_empty_when_no_target(self):
        """_extract_slo_for_service returns {} when slo_target is None."""
        step = _make_step()
        health = {"payments": {"slo_target": None, "burn_rate": None}}
        assert step._extract_slo_for_service(health, "payments") == {}

    def test_extract_slo_for_service_returns_empty_for_unknown(self):
        """_extract_slo_for_service returns {} for unknown service."""
        step = _make_step()
        assert step._extract_slo_for_service({}, "unknown") == {}


class TestGracefulAbsence:
    """Test that missing SLO data is handled without errors (AC #3)."""

    def test_servicelevel_api_exception_graceful(self):
        """ApiException on ServiceLevel query produces empty health dict."""
        step = _make_step()
        step._custom_api = MagicMock()
        step._custom_api.list_namespaced_custom_object.side_effect = ApiException(
            status=403, reason="Forbidden"
        )
        health = step._get_service_health()
        assert health == {}

    @patch("beeper_investigator.steps.service_topology.config")
    @patch("beeper_investigator.steps.service_topology.client")
    def test_k8s_init_failure_no_slo_data(self, mock_client, mock_config):
        """K8s init failure produces no SLO data in result."""
        mock_config.load_incluster_config.side_effect = Exception("No cluster")
        mock_config.load_kube_config.side_effect = Exception("No kubeconfig")

        step = _make_step()
        result = step.execute()

        assert result.success
        assert "slo_target" not in result.data
        assert "slo_burn_rate" not in result.data
