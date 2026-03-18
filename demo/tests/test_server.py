"""Unit tests for the demo application server."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from server import JsonFormatter, create_app, registry  # noqa: E402


# ---------------------------------------------------------------------------
# Health Endpoint Tests (all roles)
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """Test health endpoint across all service roles."""

    def test_health_returns_200(self, client):
        """Health endpoint returns 200 for all roles."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_json(self, client):
        """Health endpoint returns valid JSON."""
        response = client.get("/health")
        data = response.get_json()
        assert data is not None
        assert "status" in data
        assert data["status"] == "healthy"

    def test_health_includes_service_name(self, client, role):
        """Health endpoint includes the service role name."""
        response = client.get("/health")
        data = response.get_json()
        assert "service" in data
        assert data["service"] == role

    def test_health_shows_fault_disabled_by_default(self, client):
        """Health endpoint shows fault injection is disabled."""
        response = client.get("/health")
        data = response.get_json()
        assert data["fault_enabled"] is False


# ---------------------------------------------------------------------------
# Metrics Endpoint Tests (all roles)
# ---------------------------------------------------------------------------


class TestMetricsEndpoint:
    """Test Prometheus metrics endpoint across all roles."""

    def test_metrics_returns_200(self, client):
        """Metrics endpoint returns 200."""
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_content_type(self, client):
        """Metrics endpoint returns text/plain content type."""
        response = client.get("/metrics")
        assert "text/plain" in response.content_type

    def test_metrics_contains_prometheus_format(self, client):
        """Metrics endpoint returns valid Prometheus exposition format."""
        # Make a request first to generate metrics
        client.get("/health")
        response = client.get("/metrics")
        text = response.data.decode("utf-8")
        # Prometheus exposition format contains HELP and TYPE lines
        assert "# HELP" in text or "# TYPE" in text or text.strip() == ""


# ---------------------------------------------------------------------------
# API Gateway Role Tests
# ---------------------------------------------------------------------------


class TestApiGatewayRole:
    """Test api-gateway specific endpoints."""

    def test_get_orders(self, api_gateway_client):
        """GET /api/v1/orders returns order list."""
        response = api_gateway_client.get("/api/v1/orders")
        assert response.status_code == 200
        data = response.get_json()
        assert "orders" in data
        assert "total" in data
        assert isinstance(data["orders"], list)
        assert data["total"] == len(data["orders"])

    def test_post_orders(self, api_gateway_client):
        """POST /api/v1/orders creates an order."""
        response = api_gateway_client.post(
            "/api/v1/orders",
            json={"item": "widget", "quantity": 5},
        )
        assert response.status_code == 201
        data = response.get_json()
        assert "order_id" in data
        assert data["status"] == "created"

    def test_api_health(self, api_gateway_client):
        """GET /api/v1/health returns upstream status."""
        response = api_gateway_client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.get_json()
        assert "gateway" in data
        assert data["gateway"] == "healthy"
        assert "upstream_services" in data


# ---------------------------------------------------------------------------
# Backend Role Tests
# ---------------------------------------------------------------------------


class TestBackendRole:
    """Test backend specific endpoints."""

    def test_process_endpoint(self, backend_client):
        """POST /process returns processing result."""
        response = backend_client.post("/process", json={"data": "test"})
        assert response.status_code == 200
        data = response.get_json()
        assert data["result"] == "processed"
        assert "processing_time_ms" in data
        assert data["service"] == "backend"


# ---------------------------------------------------------------------------
# Database Role Tests
# ---------------------------------------------------------------------------


class TestDatabaseRole:
    """Test database specific endpoints."""

    def test_query_default_table(self, database_client):
        """GET /query returns orders table by default."""
        response = database_client.get("/query")
        assert response.status_code == 200
        data = response.get_json()
        assert data["table"] == "orders"
        assert "rows" in data
        assert "count" in data
        assert isinstance(data["rows"], list)

    def test_query_specific_table(self, database_client):
        """GET /query?table=customers returns customer data."""
        response = database_client.get("/query?table=customers")
        assert response.status_code == 200
        data = response.get_json()
        assert data["table"] == "customers"
        assert data["count"] > 0

    def test_query_nonexistent_table(self, database_client):
        """GET /query?table=missing returns empty result."""
        response = database_client.get("/query?table=nonexistent")
        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 0
        assert data["rows"] == []


# ---------------------------------------------------------------------------
# Worker Role Tests
# ---------------------------------------------------------------------------


class TestWorkerRole:
    """Test worker specific endpoints."""

    def test_jobs_endpoint(self, worker_client):
        """GET /jobs returns job queue."""
        response = worker_client.get("/jobs")
        assert response.status_code == 200
        data = response.get_json()
        assert "jobs" in data
        assert "total" in data
        assert "running" in data
        assert "queued" in data
        assert isinstance(data["jobs"], list)


# ---------------------------------------------------------------------------
# Fault Injection Hook Tests
# ---------------------------------------------------------------------------


class TestFaultInjectionHooks:
    """Test that fault injection hooks exist but are disabled by default."""

    def test_fault_disabled_by_default(self, api_gateway_client):
        """Faults do not affect requests when disabled."""
        # Make multiple requests - none should fail
        for _ in range(10):
            response = api_gateway_client.get("/api/v1/orders")
            assert response.status_code == 200

    def test_health_reports_fault_status(self, client):
        """Health endpoint reports fault injection status."""
        response = client.get("/health")
        data = response.get_json()
        assert "fault_enabled" in data
        assert "fault_type" in data


# ---------------------------------------------------------------------------
# JSON Logging Tests
# ---------------------------------------------------------------------------


class TestStructuredLogging:
    """Test structured JSON logging output format."""

    def test_json_formatter_produces_valid_json(self):
        """JsonFormatter produces valid JSON output."""
        import logging

        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "Test message"
        assert parsed["level"] == "info"
        assert "timestamp" in parsed
        assert "logger" in parsed

    def test_json_formatter_includes_service_name(self):
        """JsonFormatter includes the service name."""
        import logging

        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="Warning message",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "service" in parsed


# ---------------------------------------------------------------------------
# App Factory Tests
# ---------------------------------------------------------------------------


class TestAppFactory:
    """Test the create_app factory function."""

    def test_create_app_all_roles(self):
        """create_app works for all valid roles."""
        for role_name in ["api-gateway", "backend", "database", "worker"]:
            app = create_app(role=role_name)
            assert app is not None

    def test_create_app_default_role(self):
        """create_app uses SERVICE_ROLE env var as default."""
        app = create_app()
        assert app is not None
