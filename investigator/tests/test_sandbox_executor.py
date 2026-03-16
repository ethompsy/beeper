"""Unit tests for SandboxExecutorStep (Story 4.5)."""

import os
from unittest.mock import MagicMock, patch

from beeper_investigator.agent import SourceClients
from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.remediation.sandbox_executor import (
    SandboxExecutorStep,
    SandboxStepResult,
)

# ── Helpers ─────────────────────────────────────────────


def _make_context(**overrides) -> InvestigationContext:
    defaults = {
        "investigation_id": "test-inv-001",
        "namespace": "default",
        "condition": "high_error_rate",
        "service": "payments",
        "severity": "high",
        "trust_level": 3,
        "confidence_threshold": 0.9,
    }
    defaults.update(overrides)
    return InvestigationContext(**defaults)


def _make_step(pipeline_metadata=None, trust_level=3, sources=None, **overrides):
    """Factory for SandboxExecutorStep with mocked dependencies."""
    llm = MagicMock(spec=LlmClient)
    ctx = _make_context(trust_level=trust_level)
    status = MagicMock(spec=InvestigationStatusUpdater)
    if sources is None:
        sources = SourceClients(prometheus=MagicMock(), loki=MagicMock())
    defaults = {
        "llm_client": llm,
        "context": ctx,
        "status_updater": status,
        "pipeline_metadata": pipeline_metadata or {},
        "sources": sources,
    }
    defaults.update(overrides)
    step = SandboxExecutorStep(**defaults)
    # Mock K8s API to avoid cluster config in tests
    step._k8s_core_api = MagicMock()
    return step, defaults


def _sample_verification_steps():
    return [
        {
            "step_number": 1,
            "title": "Check pod restart count",
            "description": "Verify pod restarts decreased",
            "action": "query kube_pod_container_status_restarts_total",
            "expected_outcome": "Restart count is 0",
            "metric_or_endpoint": "kube_pod_container_status_restarts_total",
            "verification_type": "metric_check",
            "status": "pending",
        },
        {
            "step_number": 2,
            "title": "Health endpoint check",
            "description": "Verify service health endpoint returns 200",
            "action": "GET /health",
            "expected_outcome": "HTTP 200 OK",
            "metric_or_endpoint": "http://payments.beeper-sandbox:8080/health",
            "verification_type": "health_check",
            "status": "pending",
        },
    ]


def _sample_pipeline_metadata():
    return {
        "test_plan_generated": True,
        "promotable_to_sandbox": True,
        "verification_steps": _sample_verification_steps(),
        "metrics_to_watch": ["kube_pod_container_status_restarts_total"],
        "estimated_duration_minutes": 15,
    }


# ── Tests ───────────────────────────────────────────────


class TestSandboxAvailability:
    def test_env_var_set_returns_namespace(self):
        step, _ = _make_step()
        with patch.dict(os.environ, {"SANDBOX_NAMESPACE": "test-sandbox"}):
            ns = step._check_sandbox_available()
        assert ns == "test-sandbox"

    def test_env_var_not_set_k8s_namespace_exists(self):
        step, _ = _make_step()
        with patch.dict(os.environ, {}, clear=True):
            # Remove SANDBOX_NAMESPACE if present
            os.environ.pop("SANDBOX_NAMESPACE", None)
            step._k8s_core_api.read_namespace.return_value = MagicMock()
            ns = step._check_sandbox_available()
        assert ns == "beeper-sandbox"

    def test_env_var_not_set_k8s_404_returns_none(self):
        step, _ = _make_step()
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SANDBOX_NAMESPACE", None)
            step._k8s_core_api.read_namespace.side_effect = Exception("404 Not Found")
            ns = step._check_sandbox_available()
        assert ns is None

    def test_k8s_exception_returns_none_with_warning(self):
        step, _ = _make_step()
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SANDBOX_NAMESPACE", None)
            step._k8s_core_api.read_namespace.side_effect = RuntimeError("connection refused")
            ns = step._check_sandbox_available()
        assert ns is None


class TestTrustGating:
    def test_tl1_skips(self):
        step, _ = _make_step(trust_level=1, pipeline_metadata=_sample_pipeline_metadata())
        result = step.execute()
        assert result.success is True
        assert result.data["sandbox_executed"] is False
        assert result.data["skip_reason"] == "trust_level_insufficient"
        assert result.data["trust_level"] == 1

    def test_tl2_skips(self):
        step, _ = _make_step(trust_level=2, pipeline_metadata=_sample_pipeline_metadata())
        result = step.execute()
        assert result.data["sandbox_executed"] is False
        assert result.data["skip_reason"] == "trust_level_insufficient"

    def test_tl3_proceeds(self):
        step, _ = _make_step(trust_level=3, pipeline_metadata=_sample_pipeline_metadata())
        with patch.dict(os.environ, {"SANDBOX_NAMESPACE": "test-sandbox"}):
            step.sources.prometheus.query.return_value = {"data": {"result": [{"value": [1, "0"]}]}}
            result = step.execute()
        assert result.data["sandbox_executed"] is True

    def test_tl4_proceeds(self):
        step, _ = _make_step(trust_level=4, pipeline_metadata=_sample_pipeline_metadata())
        with patch.dict(os.environ, {"SANDBOX_NAMESPACE": "test-sandbox"}):
            step.sources.prometheus.query.return_value = {"data": {"result": [{"value": [1, "0"]}]}}
            result = step.execute()
        assert result.data["sandbox_executed"] is True

    def test_tl5_proceeds(self):
        step, _ = _make_step(trust_level=5, pipeline_metadata=_sample_pipeline_metadata())
        with patch.dict(os.environ, {"SANDBOX_NAMESPACE": "test-sandbox"}):
            step.sources.prometheus.query.return_value = {"data": {"result": [{"value": [1, "0"]}]}}
            result = step.execute()
        assert result.data["sandbox_executed"] is True


class TestNoTestPlan:
    def test_missing_test_plan_generated_skips(self):
        step, _ = _make_step(pipeline_metadata={})
        result = step.execute()
        assert result.data["sandbox_executed"] is False
        assert result.data["skip_reason"] == "no_test_plan"

    def test_test_plan_generated_false_skips(self):
        step, _ = _make_step(pipeline_metadata={"test_plan_generated": False})
        result = step.execute()
        assert result.data["sandbox_executed"] is False
        assert result.data["skip_reason"] == "no_test_plan"

    def test_empty_verification_steps_skips(self):
        meta = {
            "test_plan_generated": True,
            "promotable_to_sandbox": True,
            "verification_steps": [],
        }
        step, _ = _make_step(pipeline_metadata=meta)
        result = step.execute()
        assert result.data["sandbox_executed"] is False
        assert result.data["skip_reason"] == "no_verification_steps"


class TestNotPromotable:
    def test_promotable_false_skips(self):
        meta = {
            "test_plan_generated": True,
            "promotable_to_sandbox": False,
            "verification_steps": _sample_verification_steps(),
        }
        step, _ = _make_step(pipeline_metadata=meta)
        result = step.execute()
        assert result.data["sandbox_executed"] is False
        assert result.data["skip_reason"] == "not_promotable"


class TestVerificationStepExecution:
    def test_metric_check_dispatched(self):
        step, _ = _make_step()
        step.sources.prometheus.query.return_value = {"data": {"result": [{"value": [1, "0"]}]}}
        vstep = {
            "step_number": 1,
            "title": "Test metric",
            "verification_type": "metric_check",
            "expected_outcome": "value is 0",
            "metric_or_endpoint": "test_metric",
            "action": "query test_metric",
        }
        result = step._dispatch_step(vstep, "beeper-sandbox")
        assert result.status == "pass"
        assert result.verification_type == "metric_check"

    def test_metric_check_no_prometheus_skipped(self):
        step, _ = _make_step(sources=SourceClients())
        vstep = {
            "step_number": 1,
            "title": "Test metric",
            "verification_type": "metric_check",
            "expected_outcome": "value is 0",
            "metric_or_endpoint": "test_metric",
        }
        result = step._dispatch_step(vstep, "beeper-sandbox")
        assert result.status == "skipped"
        assert "not configured" in str(result.error_message)

    def test_api_probe_dispatched(self):
        step, _ = _make_step()
        vstep = {
            "step_number": 1,
            "title": "Test API",
            "verification_type": "api_probe",
            "expected_outcome": "HTTP 200",
            "metric_or_endpoint": "http://localhost:9999/test",
        }
        with patch("beeper_investigator.remediation.sandbox_executor.httpx.Client") as mock_client:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.is_success = True
            mock_get = MagicMock(get=MagicMock(return_value=mock_resp))
            mock_client.return_value.__enter__ = MagicMock(return_value=mock_get)
            mock_client.return_value.__exit__ = MagicMock(return_value=False)
            result = step._dispatch_step(vstep, "beeper-sandbox")
        assert result.verification_type == "api_probe"

    def test_health_check_dispatched(self):
        step, _ = _make_step()
        vstep = {
            "step_number": 1,
            "title": "Health check",
            "verification_type": "health_check",
            "expected_outcome": "HTTP 200",
            "metric_or_endpoint": "http://localhost:9999/health",
        }
        with patch("beeper_investigator.remediation.sandbox_executor.httpx.Client") as mock_client:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_get = MagicMock(get=MagicMock(return_value=mock_resp))
            mock_client.return_value.__enter__ = MagicMock(return_value=mock_get)
            mock_client.return_value.__exit__ = MagicMock(return_value=False)
            result = step._dispatch_step(vstep, "beeper-sandbox")
        assert result.verification_type == "health_check"

    def test_log_inspection_dispatched(self):
        step, _ = _make_step()
        step.sources.loki.query.return_value = {"data": {"result": [{"stream": {}, "values": []}]}}
        vstep = {
            "step_number": 1,
            "title": "Log check",
            "verification_type": "log_inspection",
            "expected_outcome": "No errors",
            "metric_or_endpoint": "error_pattern",
            "action": "search for errors",
        }
        result = step._dispatch_step(vstep, "beeper-sandbox")
        assert result.verification_type == "log_inspection"
        assert result.status == "pass"

    def test_log_inspection_no_loki_skipped(self):
        step, _ = _make_step(sources=SourceClients())
        vstep = {
            "step_number": 1,
            "title": "Log check",
            "verification_type": "log_inspection",
            "expected_outcome": "No errors",
            "action": "search logs",
        }
        result = step._dispatch_step(vstep, "beeper-sandbox")
        assert result.status == "skipped"
        assert "not configured" in str(result.error_message)

    def test_manual_verification_returns_skipped(self):
        step, _ = _make_step()
        vstep = {
            "step_number": 1,
            "title": "Manual check",
            "verification_type": "manual_verification",
            "expected_outcome": "Manually verify",
        }
        result = step._dispatch_step(vstep, "beeper-sandbox")
        assert result.status == "skipped"
        assert "Manual verification required" in str(result.error_message)

    def test_unknown_type_falls_back_to_manual(self):
        step, _ = _make_step()
        vstep = {
            "step_number": 1,
            "title": "Unknown type",
            "verification_type": "unknown_type",
            "expected_outcome": "Something",
        }
        result = step._dispatch_step(vstep, "beeper-sandbox")
        assert result.status == "skipped"

    def test_non_dict_verification_step_skipped(self):
        step, _ = _make_step()
        results = step._execute_verification_steps(
            ["not a dict", 42], "beeper-sandbox"
        )
        assert len(results) == 0

    def test_api_probe_invalid_url_returns_error(self):
        step, _ = _make_step()
        vstep = {
            "step_number": 1,
            "title": "Bad URL",
            "verification_type": "api_probe",
            "expected_outcome": "HTTP 200",
            "metric_or_endpoint": "not-a-url",
        }
        result = step._dispatch_step(vstep, "beeper-sandbox")
        assert result.status == "error"
        assert "Invalid endpoint URL" in str(result.error_message)

    def test_health_check_invalid_url_returns_error(self):
        step, _ = _make_step()
        vstep = {
            "step_number": 1,
            "title": "Bad URL",
            "verification_type": "health_check",
            "expected_outcome": "HTTP 200",
            "metric_or_endpoint": "ftp://invalid",
        }
        result = step._dispatch_step(vstep, "beeper-sandbox")
        assert result.status == "error"
        assert "Invalid endpoint URL" in str(result.error_message)

    def test_log_inspection_escapes_backticks_in_action(self):
        step, _ = _make_step()
        step.sources.loki.query.return_value = {
            "data": {"result": [{"stream": {}, "values": []}]}
        }
        vstep = {
            "step_number": 1,
            "title": "Log check with backticks",
            "verification_type": "log_inspection",
            "expected_outcome": "No errors",
            "action": "search `error` pattern",
        }
        result = step._dispatch_step(vstep, "beeper-sandbox")
        # Should not error from backticks — they get escaped
        assert result.verification_type == "log_inspection"
        # Verify loki was called with escaped action
        call_args = step.sources.loki.query.call_args[0][0]
        assert "\\`" in call_args


class TestResultAggregation:
    def test_all_pass(self):
        results = [
            SandboxStepResult(1, "A", "pass", "metric_check", "", "", None, 1.0),
            SandboxStepResult(2, "B", "pass", "api_probe", "", "", None, 1.0),
        ]
        assert SandboxExecutorStep._aggregate_results(results) == "pass"

    def test_any_fail(self):
        results = [
            SandboxStepResult(1, "A", "fail", "metric_check", "", "", None, 1.0),
            SandboxStepResult(2, "B", "fail", "api_probe", "", "", None, 1.0),
        ]
        assert SandboxExecutorStep._aggregate_results(results) == "fail"

    def test_mix_partial(self):
        results = [
            SandboxStepResult(1, "A", "pass", "metric_check", "", "", None, 1.0),
            SandboxStepResult(2, "B", "fail", "api_probe", "", "", None, 1.0),
        ]
        assert SandboxExecutorStep._aggregate_results(results) == "partial"

    def test_all_skipped(self):
        results = [
            SandboxStepResult(1, "A", "skipped", "manual_verification", "", "", None, 0.0),
            SandboxStepResult(2, "B", "skipped", "manual_verification", "", "", None, 0.0),
        ]
        assert SandboxExecutorStep._aggregate_results(results) == "skipped"

    def test_empty_results(self):
        assert SandboxExecutorStep._aggregate_results([]) == "skipped"

    def test_error_counts_as_fail(self):
        results = [
            SandboxStepResult(1, "A", "pass", "metric_check", "", "", None, 1.0),
            SandboxStepResult(2, "B", "error", "api_probe", "", "", "timeout", 1.0),
        ]
        assert SandboxExecutorStep._aggregate_results(results) == "partial"

    def test_pass_plus_skipped_is_pass(self):
        results = [
            SandboxStepResult(1, "A", "pass", "metric_check", "", "", None, 1.0),
            SandboxStepResult(2, "B", "skipped", "manual_verification", "", "", None, 0.0),
        ]
        assert SandboxExecutorStep._aggregate_results(results) == "pass"


class TestNoSandboxGracefulDegradation:
    def test_no_sandbox_returns_advisory_only(self):
        step, _ = _make_step(pipeline_metadata=_sample_pipeline_metadata())
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SANDBOX_NAMESPACE", None)
            step._k8s_core_api.read_namespace.side_effect = Exception("Not Found")
            result = step.execute()

        assert result.success is True
        assert result.data["sandbox_executed"] is False
        assert result.data["skip_reason"] == "no_sandbox_configured"
        assert result.data["advisory_test_plan_only"] is True
        assert "No sandbox available" in result.summary

    def test_no_sandbox_summary_message(self):
        step, _ = _make_step(pipeline_metadata=_sample_pipeline_metadata())
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SANDBOX_NAMESPACE", None)
            step._k8s_core_api.read_namespace.side_effect = Exception("Not Found")
            result = step.execute()

        assert result.summary == "No sandbox available — manual verification recommended"


class TestEvidenceAttachment:
    def test_result_data_has_all_required_keys(self):
        step, _ = _make_step(pipeline_metadata=_sample_pipeline_metadata())
        with patch.dict(os.environ, {"SANDBOX_NAMESPACE": "test-sandbox"}):
            step.sources.prometheus.query.return_value = {"data": {"result": [{"value": [1, "0"]}]}}
            result = step.execute()

        required_keys = [
            "sandbox_executed",
            "sandbox_namespace",
            "sandbox_steps_total",
            "sandbox_steps_passed",
            "sandbox_steps_failed",
            "sandbox_steps_skipped",
            "sandbox_steps_errored",
            "sandbox_test_results",
            "sandbox_overall_status",
            "sandbox_duration_seconds",
            "sandbox_model_tier",
        ]
        for key in required_keys:
            assert key in result.data, f"Missing key: {key}"

    def test_sandbox_test_results_is_list_of_dicts(self):
        step, _ = _make_step(pipeline_metadata=_sample_pipeline_metadata())
        with patch.dict(os.environ, {"SANDBOX_NAMESPACE": "test-sandbox"}):
            step.sources.prometheus.query.return_value = {"data": {"result": [{"value": [1, "0"]}]}}
            result = step.execute()

        results_list = result.data["sandbox_test_results"]
        assert isinstance(results_list, list)
        assert len(results_list) > 0
        for r in results_list:
            assert isinstance(r, dict)
            assert "step_number" in r
            assert "title" in r
            assert "status" in r
            assert "verification_type" in r
            assert "duration_seconds" in r

    def test_sandbox_model_tier_is_remediation(self):
        step, _ = _make_step(pipeline_metadata=_sample_pipeline_metadata())
        with patch.dict(os.environ, {"SANDBOX_NAMESPACE": "test-sandbox"}):
            step.sources.prometheus.query.return_value = {"data": {"result": [{"value": [1, "0"]}]}}
            result = step.execute()

        assert result.data["sandbox_model_tier"] == "remediation"


class TestExecuteOrchestration:
    def test_happy_path_end_to_end(self):
        meta = _sample_pipeline_metadata()
        step, _ = _make_step(pipeline_metadata=meta)
        with patch.dict(os.environ, {"SANDBOX_NAMESPACE": "test-sandbox"}):
            step.sources.prometheus.query.return_value = {
                "data": {"result": [{"value": [1, "0"]}]}
            }
            result = step.execute()

        assert result.success is True
        assert result.data["sandbox_executed"] is True
        assert result.data["sandbox_namespace"] == "test-sandbox"
        assert result.data["sandbox_steps_total"] == 2

    def test_prometheus_query_failure_returns_error(self):
        meta = {
            "test_plan_generated": True,
            "promotable_to_sandbox": True,
            "verification_steps": [
                {
                    "step_number": 1,
                    "title": "Failing metric",
                    "verification_type": "metric_check",
                    "expected_outcome": "value is 0",
                    "metric_or_endpoint": "test_metric",
                    "status": "pending",
                },
            ],
        }
        step, _ = _make_step(pipeline_metadata=meta)
        with patch.dict(os.environ, {"SANDBOX_NAMESPACE": "test-sandbox"}):
            step.sources.prometheus.query.side_effect = Exception("connection refused")
            result = step.execute()

        assert result.data["sandbox_executed"] is True
        assert result.data["sandbox_steps_errored"] == 1
        assert result.data["sandbox_overall_status"] == "fail"

    def test_metric_check_no_data_fails(self):
        meta = {
            "test_plan_generated": True,
            "promotable_to_sandbox": True,
            "verification_steps": [
                {
                    "step_number": 1,
                    "title": "Empty metric",
                    "verification_type": "metric_check",
                    "expected_outcome": "value is 0",
                    "metric_or_endpoint": "test_metric",
                    "status": "pending",
                },
            ],
        }
        step, _ = _make_step(pipeline_metadata=meta)
        with patch.dict(os.environ, {"SANDBOX_NAMESPACE": "test-sandbox"}):
            step.sources.prometheus.query.return_value = {"data": {"result": []}}
            result = step.execute()

        assert result.data["sandbox_executed"] is True
        assert result.data["sandbox_steps_failed"] == 1


class TestSandboxStepResultDataclass:
    def test_construction(self):
        r = SandboxStepResult(
            step_number=1,
            title="Test",
            status="pass",
            verification_type="metric_check",
            expected_outcome="x",
            actual_value="y",
            error_message=None,
            duration_seconds=1.5,
        )
        assert r.step_number == 1
        assert r.status == "pass"
        assert r.duration_seconds == 1.5

    def test_error_message_present(self):
        r = SandboxStepResult(
            step_number=2,
            title="Fail",
            status="error",
            verification_type="api_probe",
            expected_outcome="200",
            actual_value="",
            error_message="timeout",
            duration_seconds=10.0,
        )
        assert r.error_message == "timeout"


class TestStepName:
    def test_step_name_is_sandbox_test_execution(self):
        step, _ = _make_step()
        assert step.name == "Sandbox Test Execution"


class TestProtocolCompliance:
    def test_implements_investigation_step(self):
        from beeper_investigator.steps import InvestigationStep

        step, _ = _make_step()
        assert isinstance(step, InvestigationStep)
        assert hasattr(step, "name")
        assert hasattr(step, "execute")
        assert callable(step.execute)
