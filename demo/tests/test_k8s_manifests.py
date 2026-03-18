"""Validate Kubernetes manifest YAML structure."""

import os

import pytest
import yaml

K8S_DIR = os.path.join(os.path.dirname(__file__), "..", "k8s")

DEPLOYMENT_FILES = ["api-gateway.yaml", "backend.yaml", "database.yaml", "worker.yaml"]
SLO_FILES = ["slo-api-gateway.yaml", "slo-backend.yaml", "slo-database.yaml", "slo-worker.yaml"]


def load_yaml_docs(filename):
    """Load all YAML documents from a file."""
    filepath = os.path.join(K8S_DIR, filename)
    with open(filepath) as f:
        return list(yaml.safe_load_all(f))


# ---------------------------------------------------------------------------
# Namespace Tests
# ---------------------------------------------------------------------------


class TestNamespaceManifest:
    """Test namespace.yaml structure."""

    def test_namespace_valid_yaml(self):
        """namespace.yaml is valid YAML."""
        docs = load_yaml_docs("namespace.yaml")
        assert len(docs) == 1

    def test_namespace_kind(self):
        """namespace.yaml has kind: Namespace."""
        docs = load_yaml_docs("namespace.yaml")
        assert docs[0]["kind"] == "Namespace"

    def test_namespace_name(self):
        """namespace.yaml has name: beeper-demo."""
        docs = load_yaml_docs("namespace.yaml")
        assert docs[0]["metadata"]["name"] == "beeper-demo"

    def test_namespace_labels(self):
        """namespace.yaml has required labels."""
        docs = load_yaml_docs("namespace.yaml")
        labels = docs[0]["metadata"]["labels"]
        assert "app.kubernetes.io/part-of" in labels
        assert labels["app.kubernetes.io/part-of"] == "beeper-demo"


# ---------------------------------------------------------------------------
# Deployment + Service Tests
# ---------------------------------------------------------------------------


class TestDeploymentManifests:
    """Test deployment manifest structure."""

    @pytest.mark.parametrize("filename", DEPLOYMENT_FILES)
    def test_valid_yaml(self, filename):
        """Deployment files are valid YAML with multiple docs."""
        docs = load_yaml_docs(filename)
        assert len(docs) == 2  # Deployment + Service

    @pytest.mark.parametrize("filename", DEPLOYMENT_FILES)
    def test_deployment_kind(self, filename):
        """First doc is a Deployment."""
        docs = load_yaml_docs(filename)
        assert docs[0]["kind"] == "Deployment"
        assert docs[0]["apiVersion"] == "apps/v1"

    @pytest.mark.parametrize("filename", DEPLOYMENT_FILES)
    def test_service_kind(self, filename):
        """Second doc is a Service."""
        docs = load_yaml_docs(filename)
        assert docs[1]["kind"] == "Service"
        assert docs[1]["apiVersion"] == "v1"

    @pytest.mark.parametrize("filename", DEPLOYMENT_FILES)
    def test_deployment_namespace(self, filename):
        """Deployment is in beeper-demo namespace."""
        docs = load_yaml_docs(filename)
        assert docs[0]["metadata"]["namespace"] == "beeper-demo"

    @pytest.mark.parametrize("filename", DEPLOYMENT_FILES)
    def test_service_namespace(self, filename):
        """Service is in beeper-demo namespace."""
        docs = load_yaml_docs(filename)
        assert docs[1]["metadata"]["namespace"] == "beeper-demo"

    @pytest.mark.parametrize("filename", DEPLOYMENT_FILES)
    def test_resource_limits_present(self, filename):
        """Deployment containers have resource limits."""
        docs = load_yaml_docs(filename)
        container = docs[0]["spec"]["template"]["spec"]["containers"][0]
        assert "resources" in container
        assert "limits" in container["resources"]
        assert "requests" in container["resources"]
        assert "cpu" in container["resources"]["limits"]
        assert "memory" in container["resources"]["limits"]

    @pytest.mark.parametrize("filename", DEPLOYMENT_FILES)
    def test_probes_present(self, filename):
        """Deployment containers have liveness and readiness probes."""
        docs = load_yaml_docs(filename)
        container = docs[0]["spec"]["template"]["spec"]["containers"][0]
        assert "livenessProbe" in container
        assert "readinessProbe" in container
        assert container["livenessProbe"]["httpGet"]["path"] == "/health"
        assert container["readinessProbe"]["httpGet"]["path"] == "/health"

    @pytest.mark.parametrize("filename", DEPLOYMENT_FILES)
    def test_prometheus_annotations(self, filename):
        """Pod template has Prometheus scrape annotations."""
        docs = load_yaml_docs(filename)
        annotations = docs[0]["spec"]["template"]["metadata"]["annotations"]
        assert annotations["prometheus.io/scrape"] == "true"
        assert "prometheus.io/port" in annotations
        assert annotations["prometheus.io/path"] == "/metrics"

    @pytest.mark.parametrize("filename", DEPLOYMENT_FILES)
    def test_service_role_env(self, filename):
        """Container has SERVICE_ROLE environment variable."""
        docs = load_yaml_docs(filename)
        container = docs[0]["spec"]["template"]["spec"]["containers"][0]
        env_vars = {e["name"]: e["value"] for e in container["env"]}
        assert "SERVICE_ROLE" in env_vars

    @pytest.mark.parametrize("filename", DEPLOYMENT_FILES)
    def test_fault_disabled_by_default(self, filename):
        """Container has FAULT_ENABLED=false by default."""
        docs = load_yaml_docs(filename)
        container = docs[0]["spec"]["template"]["spec"]["containers"][0]
        env_vars = {e["name"]: e["value"] for e in container["env"]}
        assert env_vars.get("FAULT_ENABLED") == "false"

    @pytest.mark.parametrize("filename", DEPLOYMENT_FILES)
    def test_probe_port_matches_service_port(self, filename):
        """Probe port matches the container port."""
        docs = load_yaml_docs(filename)
        container = docs[0]["spec"]["template"]["spec"]["containers"][0]
        container_port = container["ports"][0]["containerPort"]
        assert container["livenessProbe"]["httpGet"]["port"] == container_port
        assert container["readinessProbe"]["httpGet"]["port"] == container_port
