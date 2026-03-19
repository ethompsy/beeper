"""Tests for the scripted repeatable demo scenarios (Story 8-4).

Covers: scenario listing, scenario run, run-all, 10-run reliability (NFR18),
scenario metrics, diagnostics, and edge cases.
"""

import pytest

from server import (
    DEMO_SCENARIOS,
    LIFECYCLE_STAGES,
    SCENARIO_DURATION,
    SCENARIO_RUNS_TOTAL,
    SCENARIO_SUCCESS_TOTAL,
    _get_lifecycle_state,
    _get_scenario_state,
    create_app,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def scenario_app():
    """Create a backend app for scenario testing."""
    application = create_app(role="backend")
    application.config["TESTING"] = True
    return application


@pytest.fixture()
def scenario_client(scenario_app):
    """Create a test client from the scenario app."""
    return scenario_app.test_client()


@pytest.fixture()
def gateway_scenario_app():
    """Create an api-gateway app for scenario testing."""
    application = create_app(role="api-gateway")
    application.config["TESTING"] = True
    return application


@pytest.fixture()
def gateway_scenario_client(gateway_scenario_app):
    """Create a test client from the gateway scenario app."""
    return gateway_scenario_app.test_client()


# ---------------------------------------------------------------------------
# TestScenarioDefinitions — verify built-in scenario catalog
# ---------------------------------------------------------------------------


class TestScenarioDefinitions:
    """Test that DEMO_SCENARIOS dict is correctly defined."""

    def test_four_scenarios_defined(self):
        assert len(DEMO_SCENARIOS) == 4

    def test_scenario_names(self):
        expected = {"memory-leak", "bad-deploy", "cascading-failure", "scale-dependent"}
        assert set(DEMO_SCENARIOS.keys()) == expected

    @pytest.mark.parametrize("scenario_name", list(DEMO_SCENARIOS.keys()))
    def test_scenario_has_required_fields(self, scenario_name):
        scenario = DEMO_SCENARIOS[scenario_name]
        assert "name" in scenario
        assert "description" in scenario
        assert "fault_type" in scenario
        assert "trust_level" in scenario
        assert "timing" in scenario
        assert "duration_estimate_seconds" in scenario
        assert "expected_stages" in scenario

    @pytest.mark.parametrize("scenario_name", list(DEMO_SCENARIOS.keys()))
    def test_scenario_expected_stages_match_lifecycle(self, scenario_name):
        scenario = DEMO_SCENARIOS[scenario_name]
        assert scenario["expected_stages"] == list(LIFECYCLE_STAGES)

    @pytest.mark.parametrize("scenario_name", list(DEMO_SCENARIOS.keys()))
    def test_scenario_duration_estimate_under_5_minutes(self, scenario_name):
        scenario = DEMO_SCENARIOS[scenario_name]
        assert scenario["duration_estimate_seconds"] < 300  # NFR7

    @pytest.mark.parametrize("scenario_name", list(DEMO_SCENARIOS.keys()))
    def test_scenario_timing_sums_match_estimate(self, scenario_name):
        scenario = DEMO_SCENARIOS[scenario_name]
        timing_sum = sum(scenario["timing"].values())
        assert timing_sum == scenario["duration_estimate_seconds"]


# ---------------------------------------------------------------------------
# TestScenariosListEndpoint — GET /scenarios
# ---------------------------------------------------------------------------


class TestScenariosListEndpoint:
    """Test the GET /scenarios endpoint."""

    def test_list_returns_all_scenarios(self, scenario_client):
        resp = scenario_client.get("/scenarios")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 4
        assert len(data["scenarios"]) == 4

    def test_list_scenario_fields(self, scenario_client):
        resp = scenario_client.get("/scenarios")
        data = resp.get_json()
        for scenario in data["scenarios"]:
            assert "name" in scenario
            assert "description" in scenario
            assert "fault_type" in scenario
            assert "trust_level" in scenario
            assert "duration_estimate_seconds" in scenario

    def test_list_scenario_names(self, scenario_client):
        resp = scenario_client.get("/scenarios")
        data = resp.get_json()
        names = {s["name"] for s in data["scenarios"]}
        assert names == {"memory-leak", "bad-deploy", "cascading-failure", "scale-dependent"}

    def test_list_works_for_all_roles(self, client):
        """Verify scenario list works across all service roles (via conftest parameterized client)."""
        resp = client.get("/scenarios")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 4


# ---------------------------------------------------------------------------
# TestScenarioRunEndpoint — POST /scenarios/run
# ---------------------------------------------------------------------------


class TestScenarioRunEndpoint:
    """Test the POST /scenarios/run endpoint."""

    @pytest.mark.parametrize("scenario_name", list(DEMO_SCENARIOS.keys()))
    def test_run_scenario_succeeds(self, scenario_client, scenario_name):
        resp = scenario_client.post(
            "/scenarios/run",
            json={"scenario": scenario_name},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "completed"
        assert data["scenario"] == scenario_name
        assert data["result"]["success"] is True

    @pytest.mark.parametrize("scenario_name", list(DEMO_SCENARIOS.keys()))
    def test_run_scenario_completes_all_stages(self, scenario_client, scenario_name):
        resp = scenario_client.post(
            "/scenarios/run",
            json={"scenario": scenario_name},
        )
        data = resp.get_json()
        stages = data["result"]["stages_completed"]
        assert stages == list(LIFECYCLE_STAGES)

    def test_run_invalid_scenario_returns_400(self, scenario_client):
        resp = scenario_client.post(
            "/scenarios/run",
            json={"scenario": "nonexistent"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "invalid_scenario"
        assert "available_scenarios" in data

    def test_run_empty_scenario_returns_400(self, scenario_client):
        resp = scenario_client.post(
            "/scenarios/run",
            json={},
        )
        assert resp.status_code == 400

    def test_run_scenario_result_has_diagnostics_none_on_success(self, scenario_client):
        resp = scenario_client.post(
            "/scenarios/run",
            json={"scenario": "memory-leak"},
        )
        data = resp.get_json()
        assert data["result"]["diagnostics"] is None

    def test_run_scenario_returns_service_name(self, scenario_client):
        resp = scenario_client.post(
            "/scenarios/run",
            json={"scenario": "memory-leak"},
        )
        data = resp.get_json()
        assert data["service"] == "backend"

    def test_run_scenario_returns_duration(self, scenario_client):
        resp = scenario_client.post(
            "/scenarios/run",
            json={"scenario": "memory-leak"},
        )
        data = resp.get_json()
        assert data["result"]["duration_ms"] >= 0

    def test_run_scenario_returns_timestamps(self, scenario_client):
        resp = scenario_client.post(
            "/scenarios/run",
            json={"scenario": "memory-leak"},
        )
        data = resp.get_json()
        assert data["result"]["started_at"] is not None
        assert data["result"]["ended_at"] is not None

    def test_run_scenario_on_gateway(self, gateway_scenario_client):
        resp = gateway_scenario_client.post(
            "/scenarios/run",
            json={"scenario": "bad-deploy"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["result"]["success"] is True
        assert data["service"] == "api-gateway"


# ---------------------------------------------------------------------------
# TestScenarioStatusEndpoint — GET /scenarios/status
# ---------------------------------------------------------------------------


class TestScenarioStatusEndpoint:
    """Test the GET /scenarios/status endpoint."""

    def test_status_initial_state(self, scenario_client):
        resp = scenario_client.get("/scenarios/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["scenario_active"] is False
        assert data["current_scenario"] is None
        assert data["total_runs"] == 0
        assert data["runs"] == []

    def test_status_after_run(self, scenario_client):
        scenario_client.post(
            "/scenarios/run",
            json={"scenario": "memory-leak"},
        )
        resp = scenario_client.get("/scenarios/status")
        data = resp.get_json()
        assert data["scenario_active"] is False
        assert data["total_runs"] == 1
        assert len(data["runs"]) == 1
        assert data["runs"][0]["scenario"] == "memory-leak"
        assert data["runs"][0]["success"] is True

    def test_status_after_multiple_runs(self, scenario_client):
        scenario_client.post("/scenarios/run", json={"scenario": "memory-leak"})
        scenario_client.post("/scenarios/run", json={"scenario": "bad-deploy"})
        resp = scenario_client.get("/scenarios/status")
        data = resp.get_json()
        assert data["total_runs"] == 2
        assert len(data["runs"]) == 2

    def test_status_returns_service(self, scenario_client):
        resp = scenario_client.get("/scenarios/status")
        data = resp.get_json()
        assert data["service"] == "backend"


# ---------------------------------------------------------------------------
# TestScenarioRunAllEndpoint — POST /scenarios/run-all
# ---------------------------------------------------------------------------


class TestScenarioRunAllEndpoint:
    """Test the POST /scenarios/run-all endpoint."""

    def test_run_all_executes_all_scenarios(self, scenario_client):
        resp = scenario_client.post("/scenarios/run-all")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "completed"
        assert data["scenarios_run"] == 4
        assert data["all_success"] is True

    def test_run_all_returns_individual_results(self, scenario_client):
        resp = scenario_client.post("/scenarios/run-all")
        data = resp.get_json()
        assert len(data["results"]) == 4
        for result in data["results"]:
            assert result["success"] is True
            assert result["stages_completed"] == list(LIFECYCLE_STAGES)

    def test_run_all_returns_total_duration(self, scenario_client):
        resp = scenario_client.post("/scenarios/run-all")
        data = resp.get_json()
        assert data["total_duration_ms"] >= 0

    def test_run_all_covers_all_scenario_names(self, scenario_client):
        resp = scenario_client.post("/scenarios/run-all")
        data = resp.get_json()
        scenario_names = {r["scenario"] for r in data["results"]}
        assert scenario_names == set(DEMO_SCENARIOS.keys())

    def test_run_all_returns_service(self, scenario_client):
        resp = scenario_client.post("/scenarios/run-all")
        data = resp.get_json()
        assert data["service"] == "backend"

    def test_run_all_updates_status(self, scenario_client):
        scenario_client.post("/scenarios/run-all")
        resp = scenario_client.get("/scenarios/status")
        data = resp.get_json()
        assert data["total_runs"] == 4
        assert len(data["runs"]) == 4


# ---------------------------------------------------------------------------
# TestScenarioReliability — 10 consecutive runs (NFR18)
# ---------------------------------------------------------------------------


class TestScenarioReliability:
    """Test 10-run reliability requirement (NFR18)."""

    @pytest.mark.parametrize("scenario_name", list(DEMO_SCENARIOS.keys()))
    def test_10_consecutive_runs_succeed(self, scenario_name):
        """Run each scenario 10 times and verify all succeed (NFR18)."""
        app = create_app(role="backend")
        app.config["TESTING"] = True
        client = app.test_client()

        results = []
        for i in range(10):
            resp = client.post(
                "/scenarios/run",
                json={"scenario": scenario_name},
            )
            assert resp.status_code == 200, f"Run {i+1} returned {resp.status_code}"
            data = resp.get_json()
            assert data["result"]["success"] is True, (
                f"Run {i+1} failed: {data['result'].get('diagnostics')}"
            )
            results.append(data["result"])

        # Verify consistency: all runs produce same stage sequence
        for i, result in enumerate(results):
            assert result["stages_completed"] == list(LIFECYCLE_STAGES), (
                f"Run {i+1} had inconsistent stages: {result['stages_completed']}"
            )

    def test_10_runs_tracked_in_status(self):
        """Verify all 10 runs are recorded in scenario status."""
        app = create_app(role="backend")
        app.config["TESTING"] = True
        client = app.test_client()

        for _ in range(10):
            client.post("/scenarios/run", json={"scenario": "memory-leak"})

        resp = client.get("/scenarios/status")
        data = resp.get_json()
        assert data["total_runs"] == 10
        assert len(data["runs"]) == 10
        assert all(r["success"] for r in data["runs"])

    def test_10_runs_produce_sequential_run_numbers(self):
        """Verify run numbers are sequential across 10 runs."""
        app = create_app(role="backend")
        app.config["TESTING"] = True
        client = app.test_client()

        for _ in range(10):
            client.post("/scenarios/run", json={"scenario": "bad-deploy"})

        resp = client.get("/scenarios/status")
        data = resp.get_json()
        run_numbers = [r["run_number"] for r in data["runs"]]
        assert run_numbers == list(range(1, 11))


# ---------------------------------------------------------------------------
# TestScenarioMetrics — Prometheus metrics
# ---------------------------------------------------------------------------


class TestScenarioMetrics:
    """Test scenario Prometheus metrics."""

    def test_scenario_runs_counter_increments(self, scenario_app, scenario_client):
        initial = SCENARIO_RUNS_TOTAL.labels(
            service="backend", scenario="memory-leak"
        )._value.get()

        scenario_client.post("/scenarios/run", json={"scenario": "memory-leak"})

        after = SCENARIO_RUNS_TOTAL.labels(
            service="backend", scenario="memory-leak"
        )._value.get()
        assert after == initial + 1

    def test_scenario_success_counter_increments(self, scenario_app, scenario_client):
        initial = SCENARIO_SUCCESS_TOTAL.labels(
            service="backend", scenario="memory-leak"
        )._value.get()

        scenario_client.post("/scenarios/run", json={"scenario": "memory-leak"})

        after = SCENARIO_SUCCESS_TOTAL.labels(
            service="backend", scenario="memory-leak"
        )._value.get()
        assert after == initial + 1

    def test_scenario_duration_gauge_set(self, scenario_app, scenario_client):
        scenario_client.post("/scenarios/run", json={"scenario": "memory-leak"})

        duration = SCENARIO_DURATION.labels(
            service="backend", scenario="memory-leak"
        )._value.get()
        assert duration >= 0

    def test_metrics_endpoint_includes_scenario_metrics(self, scenario_client):
        scenario_client.post("/scenarios/run", json={"scenario": "memory-leak"})

        resp = scenario_client.get("/metrics")
        assert resp.status_code == 200
        metrics_text = resp.data.decode()
        assert "demo_scenario_runs_total" in metrics_text
        assert "demo_scenario_success_total" in metrics_text
        assert "demo_scenario_duration_seconds" in metrics_text

    def test_run_all_increments_metrics_for_each_scenario(self, scenario_app, scenario_client):
        scenario_client.post("/scenarios/run-all")

        for scenario_name in DEMO_SCENARIOS:
            runs = SCENARIO_RUNS_TOTAL.labels(
                service="backend", scenario=scenario_name
            )._value.get()
            assert runs >= 1


# ---------------------------------------------------------------------------
# TestScenarioEdgeCases — error handling and edge cases
# ---------------------------------------------------------------------------


class TestScenarioEdgeCases:
    """Test scenario edge cases and error handling."""

    def test_run_after_lifecycle_already_completed(self, scenario_client):
        """Run a scenario after a previous lifecycle has already completed."""
        # First, run a lifecycle directly
        scenario_client.post(
            "/lifecycle/start",
            json={"fault_type": "memory-leak"},
        )
        # Now run a scenario — should succeed by resetting
        resp = scenario_client.post(
            "/scenarios/run",
            json={"scenario": "bad-deploy"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["result"]["success"] is True

    def test_run_scenario_cleans_up_lifecycle(self, scenario_app, scenario_client):
        """Verify scenario run resets lifecycle state after completion."""
        scenario_client.post(
            "/scenarios/run",
            json={"scenario": "memory-leak"},
        )
        # After scenario, lifecycle should show completed (kb_created)
        with scenario_app.app_context():
            state = _get_lifecycle_state(scenario_app)
            assert state["current_stage"] == "kb_created"
            assert state["lifecycle_active"] is False

    def test_run_all_after_previous_run_all(self, scenario_client):
        """Run all scenarios twice — should work cleanly both times."""
        resp1 = scenario_client.post("/scenarios/run-all")
        assert resp1.status_code == 200
        assert resp1.get_json()["all_success"] is True

        resp2 = scenario_client.post("/scenarios/run-all")
        assert resp2.status_code == 200
        assert resp2.get_json()["all_success"] is True

    def test_scenario_state_isolated_per_app(self):
        """Each app instance has its own scenario state."""
        app1 = create_app(role="backend")
        app1.config["TESTING"] = True
        client1 = app1.test_client()

        app2 = create_app(role="api-gateway")
        app2.config["TESTING"] = True
        client2 = app2.test_client()

        client1.post("/scenarios/run", json={"scenario": "memory-leak"})

        resp = client2.get("/scenarios/status")
        data = resp.get_json()
        assert data["total_runs"] == 0

    def test_run_history_capped_at_100(self):
        """Verify run history is capped at 100 entries to prevent memory growth."""
        app = create_app(role="backend")
        app.config["TESTING"] = True
        client = app.test_client()

        for _ in range(105):
            client.post("/scenarios/run", json={"scenario": "memory-leak"})

        resp = client.get("/scenarios/status")
        data = resp.get_json()
        assert data["total_runs"] == 105
        assert len(data["runs"]) == 100
        # Oldest runs should be trimmed — first run number should be 6
        assert data["runs"][0]["run_number"] == 6

    def test_mixed_scenario_and_lifecycle_operations(self, scenario_client):
        """Run a scenario, then a direct lifecycle, then another scenario."""
        resp1 = scenario_client.post(
            "/scenarios/run",
            json={"scenario": "memory-leak"},
        )
        assert resp1.get_json()["result"]["success"] is True

        # Direct lifecycle
        scenario_client.post("/lifecycle/reset")
        scenario_client.post(
            "/lifecycle/start",
            json={"fault_type": "bad-deploy"},
        )

        # Another scenario should work
        resp2 = scenario_client.post(
            "/scenarios/run",
            json={"scenario": "scale-dependent"},
        )
        assert resp2.status_code == 200
        assert resp2.get_json()["result"]["success"] is True
