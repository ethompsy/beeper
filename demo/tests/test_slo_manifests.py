"""Validate ServiceLevel CRD manifest structure for OTel demo services."""

import os

import pytest
import yaml

K8S_DIR = os.path.join(os.path.dirname(__file__), "..", "k8s")

SLO_FILES = [
    ("slo-checkout.yaml", "checkoutservice", 0.999),
    ("slo-cart.yaml", "cartservice", 0.999),
    ("slo-payment.yaml", "paymentservice", 0.9995),
    ("slo-frontend.yaml", "frontend", 0.995),
    ("slo-productcatalog.yaml", "productcatalogservice", 0.999),
]

VALID_SLI_TYPES = ["availability", "latency", "error_rate"]


def load_slo(filename):
    """Load a ServiceLevel CRD from file."""
    filepath = os.path.join(K8S_DIR, filename)
    with open(filepath) as f:
        return yaml.safe_load(f)


class TestServiceLevelCRDs:
    """Validate ServiceLevel CRD manifests match operator schema."""

    @pytest.mark.parametrize("filename,service,target", SLO_FILES)
    def test_valid_yaml(self, filename, service, target):
        """SLO file is valid YAML."""
        doc = load_slo(filename)
        assert doc is not None

    @pytest.mark.parametrize("filename,service,target", SLO_FILES)
    def test_api_version(self, filename, service, target):
        """SLO has correct apiVersion."""
        doc = load_slo(filename)
        assert doc["apiVersion"] == "beeper.dev/v1"

    @pytest.mark.parametrize("filename,service,target", SLO_FILES)
    def test_kind(self, filename, service, target):
        """SLO has kind: ServiceLevel."""
        doc = load_slo(filename)
        assert doc["kind"] == "ServiceLevel"

    @pytest.mark.parametrize("filename,service,target", SLO_FILES)
    def test_namespace(self, filename, service, target):
        """SLO is in otel-demo namespace."""
        doc = load_slo(filename)
        assert doc["metadata"]["namespace"] == "otel-demo"

    @pytest.mark.parametrize("filename,service,target", SLO_FILES)
    def test_service_name(self, filename, service, target):
        """SLO references correct service."""
        doc = load_slo(filename)
        assert doc["spec"]["service"] == service

    @pytest.mark.parametrize("filename,service,target", SLO_FILES)
    def test_sli_structure(self, filename, service, target):
        """SLO has valid SLI structure."""
        doc = load_slo(filename)
        sli = doc["spec"]["sli"]
        assert "type" in sli
        assert sli["type"] in VALID_SLI_TYPES
        assert "metric" in sli
        assert "good_selector" in sli
        assert "total_selector" in sli

    @pytest.mark.parametrize("filename,service,target", SLO_FILES)
    def test_objective_target(self, filename, service, target):
        """SLO has correct target value."""
        doc = load_slo(filename)
        objective = doc["spec"]["objective"]
        assert objective["target"] == target
        assert 0.0 < objective["target"] <= 1.0

    @pytest.mark.parametrize("filename,service,target", SLO_FILES)
    def test_objective_window(self, filename, service, target):
        """SLO has a measurement window."""
        doc = load_slo(filename)
        assert "window" in doc["spec"]["objective"]
        assert doc["spec"]["objective"]["window"] == "30m"

    @pytest.mark.parametrize("filename,service,target", SLO_FILES)
    def test_burn_rate_alerts(self, filename, service, target):
        """SLO has burn rate alert configuration."""
        doc = load_slo(filename)
        alerts = doc["spec"]["burn_rate_alerts"]
        assert isinstance(alerts, list)
        assert len(alerts) >= 2

        severities = [a["severity"] for a in alerts]
        assert "warning" in severities
        assert "critical" in severities

        for alert in alerts:
            assert "short_window" in alert
            assert "long_window" in alert
            assert "factor" in alert
            assert alert["factor"] > 0

    @pytest.mark.parametrize("filename,service,target", SLO_FILES)
    def test_part_of_label(self, filename, service, target):
        """SLO has otel-demo part-of label."""
        doc = load_slo(filename)
        labels = doc["metadata"]["labels"]
        assert labels["app.kubernetes.io/part-of"] == "otel-demo"
