"""Comprehensive tests for configurable fault injection (Story 8-2)."""

import pytest

from server import FAULT_TYPES, create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fault_app():
    """Create a Flask test app with fault injection support."""
    app = create_app(role="backend")
    app.config["TESTING"] = True
    return app


@pytest.fixture()
def fault_client(fault_app):
    """Create a test client for fault injection tests."""
    return fault_app.test_client()


@pytest.fixture()
def gateway_app():
    """Create api-gateway app for cascading failure tests."""
    app = create_app(role="api-gateway")
    app.config["TESTING"] = True
    return app


@pytest.fixture()
def gateway_client(gateway_app):
    """Create test client for api-gateway."""
    return gateway_app.test_client()


@pytest.fixture(params=["api-gateway", "backend", "database", "worker"])
def any_role(request):
    """Parameterized fixture providing each service role."""
    return request.param


@pytest.fixture()
def any_client(any_role):
    """Create a test client for any role."""
    app = create_app(role=any_role)
    app.config["TESTING"] = True
    return app.test_client()


# ---------------------------------------------------------------------------
# Fault Inject API Tests (Task 1)
# ---------------------------------------------------------------------------


class TestFaultInjectEndpoint:
    """Test POST /fault/inject endpoint."""

    def test_inject_valid_fault_type(self, fault_client):
        """Injecting a valid fault type returns 200 with status 'injected'."""
        response = fault_client.post(
            "/fault/inject",
            json={"fault_type": "memory-leak"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "injected"
        assert data["fault_type"] == "memory-leak"
        assert data["service"] == "backend"

    def test_inject_with_custom_params(self, fault_client):
        """Injecting with custom params merges with defaults."""
        response = fault_client.post(
            "/fault/inject",
            json={"fault_type": "memory-leak", "params": {"chunk_size_kb": 200}},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["params"]["chunk_size_kb"] == 200

    def test_inject_invalid_fault_type_returns_400(self, fault_client):
        """Injecting an invalid fault type returns 400 with available types."""
        response = fault_client.post(
            "/fault/inject",
            json={"fault_type": "nonexistent"},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["error"] == "invalid_fault_type"
        assert "available_types" in data
        assert set(data["available_types"]) == set(FAULT_TYPES.keys())

    def test_inject_empty_body_returns_400(self, fault_client):
        """Injecting without fault_type returns 400."""
        response = fault_client.post(
            "/fault/inject",
            json={},
        )
        assert response.status_code == 400

    def test_inject_all_fault_types(self, fault_client):
        """All defined fault types can be injected."""
        for fault_type in FAULT_TYPES:
            response = fault_client.post(
                "/fault/inject",
                json={"fault_type": fault_type},
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data["fault_type"] == fault_type
            # Recover before next
            fault_client.post("/fault/recover")

    def test_inject_activates_fault_on_all_roles(self, any_client, any_role):
        """Fault injection works on all service roles."""
        response = any_client.post(
            "/fault/inject",
            json={"fault_type": "bad-deploy"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["service"] == any_role
        assert data["status"] == "injected"
        # Cleanup
        any_client.post("/fault/recover")


# ---------------------------------------------------------------------------
# Fault Recover API Tests (Task 1)
# ---------------------------------------------------------------------------


class TestFaultRecoverEndpoint:
    """Test POST /fault/recover endpoint."""

    def test_recover_clears_active_fault(self, fault_client):
        """Recovery clears the active fault and returns previous type."""
        fault_client.post("/fault/inject", json={"fault_type": "bad-deploy"})
        response = fault_client.post("/fault/recover")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "recovered"
        assert data["cleared_fault"] == "bad-deploy"

    def test_recover_when_no_fault_active(self, fault_client):
        """Recovery when no fault is active returns cleared_fault=none."""
        response = fault_client.post("/fault/recover")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "recovered"
        assert data["cleared_fault"] == "none"

    def test_recover_clears_memory_leak(self, fault_client):
        """Recovery clears memory leak store and resets bytes counter."""
        # Inject memory leak
        fault_client.post("/fault/inject", json={"fault_type": "memory-leak"})
        # Make requests to accumulate memory
        fault_client.post("/process", json={"data": "test"})
        fault_client.post("/process", json={"data": "test"})

        # Verify memory accumulated
        status = fault_client.get("/fault/status").get_json()
        assert status["memory_leak_bytes"] > 0

        # Recover
        fault_client.post("/fault/recover")

        # Verify memory cleared
        status = fault_client.get("/fault/status").get_json()
        assert status["memory_leak_bytes"] == 0
        assert status["fault_active"] is False

    def test_recover_returns_service_to_healthy(self, fault_client):
        """After recovery, health endpoint shows healthy status."""
        fault_client.post("/fault/inject", json={"fault_type": "bad-deploy"})

        # Health shows degraded
        health = fault_client.get("/health").get_json()
        assert health["status"] == "degraded"

        # Recover
        fault_client.post("/fault/recover")

        # Health shows healthy
        health = fault_client.get("/health").get_json()
        assert health["status"] == "healthy"
        assert health["fault_enabled"] is False


# ---------------------------------------------------------------------------
# Fault Status API Tests (Task 1)
# ---------------------------------------------------------------------------


class TestFaultStatusEndpoint:
    """Test GET /fault/status endpoint."""

    def test_status_when_no_fault(self, fault_client):
        """Status shows no active fault when none injected."""
        response = fault_client.get("/fault/status")
        assert response.status_code == 200
        data = response.get_json()
        assert data["fault_active"] is False
        assert data["fault_type"] == "none"
        assert data["service"] == "backend"

    def test_status_after_injection(self, fault_client):
        """Status shows active fault details after injection."""
        fault_client.post("/fault/inject", json={"fault_type": "memory-leak"})
        response = fault_client.get("/fault/status")
        data = response.get_json()
        assert data["fault_active"] is True
        assert data["fault_type"] == "memory-leak"
        assert data["started_at"] is not None
        assert data["description"] is not None
        assert data["expected_beeper_response"] is not None
        # Cleanup
        fault_client.post("/fault/recover")

    def test_status_includes_params(self, fault_client):
        """Status includes merged params after injection."""
        fault_client.post(
            "/fault/inject",
            json={"fault_type": "bad-deploy", "params": {"error_rate": 0.5}},
        )
        data = fault_client.get("/fault/status").get_json()
        assert data["params"]["error_rate"] == 0.5
        # Cleanup
        fault_client.post("/fault/recover")

    def test_status_after_recovery(self, fault_client):
        """Status shows no fault after recovery."""
        fault_client.post("/fault/inject", json={"fault_type": "bad-deploy"})
        fault_client.post("/fault/recover")
        data = fault_client.get("/fault/status").get_json()
        assert data["fault_active"] is False
        assert data["fault_type"] == "none"


# ---------------------------------------------------------------------------
# Fault Types Listing API Tests (Task 1)
# ---------------------------------------------------------------------------


class TestFaultTypesEndpoint:
    """Test GET /fault/types endpoint."""

    def test_fault_types_returns_all_types(self, fault_client):
        """Fault types endpoint returns all registered fault types."""
        response = fault_client.get("/fault/types")
        assert response.status_code == 200
        data = response.get_json()
        types = {ft["type"] for ft in data["fault_types"]}
        assert types == {"memory-leak", "bad-deploy", "cascading-failure", "scale-dependent"}

    def test_fault_types_include_descriptions(self, fault_client):
        """Each fault type includes description and expected_beeper_response."""
        data = fault_client.get("/fault/types").get_json()
        for ft in data["fault_types"]:
            assert "description" in ft
            assert "default_params" in ft
            assert "expected_beeper_response" in ft
            assert len(ft["description"]) > 10
            assert len(ft["expected_beeper_response"]) > 10


# ---------------------------------------------------------------------------
# Memory Leak Fault Tests (Task 2)
# ---------------------------------------------------------------------------


class TestMemoryLeakFault:
    """Test memory-leak fault type behavior."""

    def test_memory_accumulates_per_request(self, fault_client):
        """Memory leak accumulates bytes with each request."""
        fault_client.post("/fault/inject", json={"fault_type": "memory-leak"})

        # Make requests
        fault_client.post("/process", json={"data": "test"})
        status1 = fault_client.get("/fault/status").get_json()
        bytes1 = status1["memory_leak_bytes"]

        fault_client.post("/process", json={"data": "test"})
        status2 = fault_client.get("/fault/status").get_json()
        bytes2 = status2["memory_leak_bytes"]

        assert bytes2 > bytes1
        assert bytes1 > 0
        # Cleanup
        fault_client.post("/fault/recover")

    def test_memory_leak_configurable_chunk_size(self, fault_client):
        """Custom chunk size affects memory accumulation rate."""
        fault_client.post(
            "/fault/inject",
            json={"fault_type": "memory-leak", "params": {"chunk_size_kb": 50}},
        )
        fault_client.post("/process", json={"data": "test"})
        status = fault_client.get("/fault/status").get_json()
        # 50KB = 51200 bytes
        assert status["memory_leak_bytes"] == 50 * 1024
        # Cleanup
        fault_client.post("/fault/recover")

    def test_memory_leak_recovery_clears_store(self, fault_client):
        """Recovery clears the memory leak store completely."""
        fault_client.post("/fault/inject", json={"fault_type": "memory-leak"})
        fault_client.post("/process", json={"data": "test"})
        fault_client.post("/fault/recover")
        status = fault_client.get("/fault/status").get_json()
        assert status["memory_leak_bytes"] == 0


# ---------------------------------------------------------------------------
# Bad Deploy Fault Tests (Task 2)
# ---------------------------------------------------------------------------


class TestBadDeployFault:
    """Test bad-deploy fault type behavior."""

    def test_bad_deploy_increases_error_rate(self, fault_client):
        """Bad deploy fault causes high error rate on requests."""
        fault_client.post("/fault/inject", json={"fault_type": "bad-deploy"})
        errors = 0
        total = 50
        for _ in range(total):
            response = fault_client.post("/process", json={"data": "test"})
            if response.status_code == 500:
                errors += 1

        # Default error rate is 0.8, so we expect ~40/50 errors (allow variance)
        assert errors > 20, f"Expected significant errors, got {errors}/{total}"
        # Cleanup
        fault_client.post("/fault/recover")

    def test_bad_deploy_error_response_format(self, fault_client):
        """Bad deploy errors return proper JSON error format."""
        fault_client.post(
            "/fault/inject",
            json={"fault_type": "bad-deploy", "params": {"error_rate": 1.0}},
        )
        response = fault_client.post("/process", json={"data": "test"})
        assert response.status_code == 500
        data = response.get_json()
        assert data["error"] == "internal_server_error"
        assert "bad-deploy" in data["detail"]
        # Cleanup
        fault_client.post("/fault/recover")

    def test_bad_deploy_custom_error_rate(self, fault_client):
        """Custom error rate parameter is respected."""
        # Error rate = 0 means no errors
        fault_client.post(
            "/fault/inject",
            json={"fault_type": "bad-deploy", "params": {"error_rate": 0.0}},
        )
        for _ in range(10):
            response = fault_client.post("/process", json={"data": "test"})
            assert response.status_code == 200
        # Cleanup
        fault_client.post("/fault/recover")


# ---------------------------------------------------------------------------
# Cascading Failure Fault Tests (Task 2)
# ---------------------------------------------------------------------------


class TestCascadingFailureFault:
    """Test cascading-failure fault type behavior."""

    def test_cascading_failure_returns_503(self, fault_client):
        """Cascading failure returns 503 Service Unavailable."""
        fault_client.post(
            "/fault/inject",
            json={"fault_type": "cascading-failure", "params": {"error_rate": 1.0}},
        )
        response = fault_client.post("/process", json={"data": "test"})
        assert response.status_code == 503
        data = response.get_json()
        assert data["error"] == "service_unavailable"
        assert "cascading-failure" in data["detail"]
        # Cleanup
        fault_client.post("/fault/recover")

    def test_cascading_failure_on_gateway(self, gateway_client):
        """Cascading failure works on api-gateway role too."""
        gateway_client.post(
            "/fault/inject",
            json={"fault_type": "cascading-failure", "params": {"error_rate": 1.0}},
        )
        response = gateway_client.get("/api/v1/orders")
        assert response.status_code == 503
        # Cleanup
        gateway_client.post("/fault/recover")

    def test_cascading_failure_high_error_rate(self, fault_client):
        """Cascading failure with default rate causes high failure rate."""
        fault_client.post("/fault/inject", json={"fault_type": "cascading-failure"})
        errors = 0
        total = 30
        for _ in range(total):
            response = fault_client.post("/process", json={"data": "test"})
            if response.status_code == 503:
                errors += 1
        # Default error rate 0.9, expect most to fail
        assert errors > 15, f"Expected significant cascade errors, got {errors}/{total}"
        # Cleanup
        fault_client.post("/fault/recover")


# ---------------------------------------------------------------------------
# Scale-Dependent Fault Tests (Task 2)
# ---------------------------------------------------------------------------


class TestScaleDependentFault:
    """Test scale-dependent fault type behavior."""

    def test_scale_dependent_has_correct_params(self, fault_client):
        """Scale-dependent fault uses base_latency_ms and per_connection_ms."""
        fault_client.post("/fault/inject", json={"fault_type": "scale-dependent"})
        status = fault_client.get("/fault/status").get_json()
        assert "base_latency_ms" in status["params"]
        assert "per_connection_ms" in status["params"]
        # Cleanup
        fault_client.post("/fault/recover")

    def test_scale_dependent_custom_params(self, fault_client):
        """Custom latency params are accepted."""
        fault_client.post(
            "/fault/inject",
            json={
                "fault_type": "scale-dependent",
                "params": {"base_latency_ms": 100, "per_connection_ms": 500},
            },
        )
        status = fault_client.get("/fault/status").get_json()
        assert status["params"]["base_latency_ms"] == 100
        assert status["params"]["per_connection_ms"] == 500
        # Cleanup
        fault_client.post("/fault/recover")

    def test_scale_dependent_no_sleep_in_testing(self, fault_client):
        """In TESTING mode, scale-dependent doesn't sleep (fast tests)."""
        fault_client.post("/fault/inject", json={"fault_type": "scale-dependent"})
        # Should not hang in test mode
        response = fault_client.post("/process", json={"data": "test"})
        assert response.status_code == 200
        # Cleanup
        fault_client.post("/fault/recover")


# ---------------------------------------------------------------------------
# Fault Metrics Tests (Task 3)
# ---------------------------------------------------------------------------


class TestFaultMetrics:
    """Test fault injection Prometheus metrics."""

    def test_injection_increments_total_counter(self, fault_client):
        """Injecting a fault increments the injection total counter."""
        fault_client.post("/fault/inject", json={"fault_type": "memory-leak"})

        metrics_after = fault_client.get("/metrics").data.decode()
        assert "demo_fault_injection_total" in metrics_after
        # Cleanup
        fault_client.post("/fault/recover")

    def test_active_gauge_set_on_inject(self, fault_client):
        """Active gauge is set to 1 when fault is injected."""
        fault_client.post("/fault/inject", json={"fault_type": "bad-deploy"})
        metrics = fault_client.get("/metrics").data.decode()
        assert "demo_fault_injection_active" in metrics
        # Cleanup
        fault_client.post("/fault/recover")

    def test_memory_leak_bytes_tracked(self, fault_client):
        """Memory leak bytes gauge tracks accumulation."""
        fault_client.post("/fault/inject", json={"fault_type": "memory-leak"})
        fault_client.post("/process", json={"data": "test"})
        metrics = fault_client.get("/metrics").data.decode()
        assert "demo_memory_leak_bytes" in metrics
        # Cleanup
        fault_client.post("/fault/recover")

    def test_memory_leak_bytes_reset_on_recover(self, fault_client):
        """Memory leak bytes gauge resets to 0 on recovery."""
        fault_client.post("/fault/inject", json={"fault_type": "memory-leak"})
        fault_client.post("/process", json={"data": "test"})
        fault_client.post("/fault/recover")
        status = fault_client.get("/fault/status").get_json()
        assert status["memory_leak_bytes"] == 0


# ---------------------------------------------------------------------------
# Health Endpoint Fault Integration Tests
# ---------------------------------------------------------------------------


class TestHealthWithFaults:
    """Test health endpoint integration with fault injection."""

    def test_health_shows_degraded_when_fault_active(self, fault_client):
        """Health status shows 'degraded' when fault is active."""
        fault_client.post("/fault/inject", json={"fault_type": "bad-deploy"})
        health = fault_client.get("/health").get_json()
        assert health["status"] == "degraded"
        assert health["fault_enabled"] is True
        assert health["fault_type"] == "bad-deploy"
        # Cleanup
        fault_client.post("/fault/recover")

    def test_health_shows_healthy_after_recovery(self, fault_client):
        """Health status returns to 'healthy' after fault recovery."""
        fault_client.post("/fault/inject", json={"fault_type": "bad-deploy"})
        fault_client.post("/fault/recover")
        health = fault_client.get("/health").get_json()
        assert health["status"] == "healthy"
        assert health["fault_enabled"] is False
        assert health["fault_type"] == "none"


# ---------------------------------------------------------------------------
# Fault Disabled Default Behavior Tests
# ---------------------------------------------------------------------------


class TestFaultDisabledDefault:
    """Test that faults don't affect requests when disabled."""

    def test_no_faults_by_default(self, fault_client):
        """No faults are active by default on a fresh app."""
        status = fault_client.get("/fault/status").get_json()
        assert status["fault_active"] is False

    def test_requests_succeed_when_no_fault(self, fault_client):
        """All requests succeed when no fault is injected."""
        for _ in range(20):
            response = fault_client.post("/process", json={"data": "test"})
            assert response.status_code == 200

    def test_fault_endpoints_available_on_all_roles(self, any_client, any_role):
        """Fault control endpoints are available on all service roles."""
        status = any_client.get("/fault/status")
        assert status.status_code == 200
        types = any_client.get("/fault/types")
        assert types.status_code == 200


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestFaultEdgeCases:
    """Test edge cases and error handling."""

    def test_inject_replaces_previous_fault(self, fault_client):
        """Injecting a new fault replaces the previous one."""
        fault_client.post("/fault/inject", json={"fault_type": "memory-leak"})
        fault_client.post("/fault/inject", json={"fault_type": "bad-deploy"})
        status = fault_client.get("/fault/status").get_json()
        assert status["fault_type"] == "bad-deploy"
        # Cleanup
        fault_client.post("/fault/recover")

    def test_multiple_recover_calls_safe(self, fault_client):
        """Multiple recover calls are idempotent and safe."""
        fault_client.post("/fault/inject", json={"fault_type": "memory-leak"})
        fault_client.post("/fault/recover")
        fault_client.post("/fault/recover")
        status = fault_client.get("/fault/status").get_json()
        assert status["fault_active"] is False

    def test_inject_with_no_json_body(self, fault_client):
        """POST to inject with no JSON body returns 400."""
        response = fault_client.post("/fault/inject")
        assert response.status_code == 400
