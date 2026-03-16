"""Tests for TestPlannerStep (Story 4.3)."""

import json
from unittest.mock import MagicMock

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.remediation.test_planner import (
    VALID_VERIFICATION_TYPES,
    AdvisoryTestPlan,
    TestPlannerStep,
    TestPlanStep,
)


def _make_context(**overrides) -> InvestigationContext:
    """Create a test InvestigationContext with sensible defaults."""
    defaults = {
        "investigation_id": "test-inv-001",
        "namespace": "default",
        "condition": "high_latency",
        "service": "payments",
        "severity": "high",
        "trust_level": 1,
        "confidence_threshold": 0.9,
    }
    defaults.update(overrides)
    return InvestigationContext(**defaults)


def _make_step(pipeline_metadata=None, **overrides):
    """Factory for TestPlannerStep with mocked dependencies."""
    llm = MagicMock(spec=LlmClient)
    ctx = overrides.pop("context", _make_context())
    status = MagicMock(spec=InvestigationStatusUpdater)

    defaults = {
        "llm_client": llm,
        "context": ctx,
        "status_updater": status,
        "pipeline_metadata": pipeline_metadata or {},
    }
    defaults.update(overrides)
    step = TestPlannerStep(**defaults)
    return step, defaults


def _hypothesis_metadata(**overrides):
    """Create pipeline_metadata with RCA hypothesis data."""
    defaults = {
        "root_cause_hypothesis": "Memory leak in connection pool causing OOM kills",
        "confidence_level": "high",
        "confidence_percentage": 85,
        "supporting_evidence": [
            "Pod restarts correlate with memory growth",
            "Connection count steadily increases without release",
        ],
        "alternative_hypotheses": [
            {"description": "Network timeout causing retries", "confidence_percentage": 40},
        ],
        "additional_data_needs": ["Heap dump analysis"],
        "signal_summary": "Memory usage trending up over 6h window",
        "service_dependency_chain": ["payments", "database", "cache"],
        "layers_queried": ["prometheus", "loki"],
    }
    defaults.update(overrides)
    return defaults


def _llm_plan_response(steps=None, **overrides):
    """Create a mock LLM test plan response."""
    if steps is None:
        steps = [
            {
                "step_number": 1,
                "title": "Check memory utilization",
                "description": "Query Prometheus for container memory metrics",
                "action": "PromQL: container_memory_working_set_bytes{pod=~'payments-.*'}",
                "expected_outcome": "Memory usage above 80% of limit",
                "metric_or_endpoint": "container_memory_working_set_bytes",
                "verification_type": "metric_check",
            },
            {
                "step_number": 2,
                "title": "Inspect connection pool logs",
                "description": "Search Loki for connection pool exhaustion patterns",
                "action": "LogQL: {app='payments'} |= 'connection pool'",
                "expected_outcome": "Connection pool exhaustion errors present",
                "metric_or_endpoint": "{app='payments'} |= 'connection pool'",
                "verification_type": "log_inspection",
            },
            {
                "step_number": 3,
                "title": "Verify pod restart count",
                "description": "Check OOMKilled restart events",
                "action": "kubectl get events --field-selector reason=OOMKilling",
                "expected_outcome": "Recent OOMKilled events for payments pods",
                "metric_or_endpoint": "kube_pod_container_status_restarts_total",
                "verification_type": "metric_check",
            },
        ]
    defaults = {
        "hypothesis_statement": "Memory leak in connection pool causing OOM kills",
        "verification_steps": steps,
        "expected_outcomes": ["Memory usage decreases after fix", "No more OOMKilled events"],
        "metrics_to_watch": [
            "container_memory_working_set_bytes",
            "kube_pod_container_status_restarts_total",
        ],
        "estimated_duration_minutes": 15,
    }
    defaults.update(overrides)
    return json.dumps(defaults)


class TestHypothesisExtraction:
    """Tests for extracting RCA hypothesis from pipeline metadata."""

    def test_no_hypothesis_returns_skip(self):
        """When no hypothesis in metadata, step returns skip result."""
        step, _ = _make_step(pipeline_metadata={})

        result = step.execute()

        assert result.success is True
        assert result.data["test_plan_generated"] is False
        assert result.data["skip_reason"] == "no_hypothesis"

    def test_empty_hypothesis_returns_skip(self):
        """When hypothesis is empty string, step returns skip result."""
        step, _ = _make_step(pipeline_metadata={"root_cause_hypothesis": ""})

        result = step.execute()

        assert result.success is True
        assert result.data["test_plan_generated"] is False
        assert result.data["skip_reason"] == "no_hypothesis"

    def test_hypothesis_extracted_correctly(self):
        """Hypothesis and supporting data extracted from metadata."""
        metadata = _hypothesis_metadata()
        step, _ = _make_step(pipeline_metadata=metadata)

        ctx = step._extract_hypothesis_context()

        assert ctx is not None
        assert ctx["root_cause_hypothesis"] == metadata["root_cause_hypothesis"]
        assert ctx["confidence_level"] == "high"
        assert ctx["confidence_percentage"] == 85
        assert len(ctx["supporting_evidence"]) == 2
        assert len(ctx["alternative_hypotheses"]) == 1
        assert ctx["signal_summary"] == "Memory usage trending up over 6h window"
        assert ctx["service_dependency_chain"] == ["payments", "database", "cache"]

    def test_partial_metadata_handled(self):
        """Missing optional fields in metadata default gracefully."""
        metadata = {"root_cause_hypothesis": "Some hypothesis"}
        step, _ = _make_step(pipeline_metadata=metadata)

        ctx = step._extract_hypothesis_context()

        assert ctx is not None
        assert ctx["root_cause_hypothesis"] == "Some hypothesis"
        assert ctx["confidence_level"] == "unknown"
        assert ctx["confidence_percentage"] == 0
        assert ctx["supporting_evidence"] == []
        assert ctx["alternative_hypotheses"] == []
        assert ctx["signal_summary"] == ""

    def test_none_hypothesis_returns_skip(self):
        """When hypothesis is None, step returns skip."""
        step, _ = _make_step(pipeline_metadata={"root_cause_hypothesis": None})

        result = step.execute()

        assert result.success is True
        assert result.data["test_plan_generated"] is False


class TestTestPlanGeneration:
    """Tests for LLM-based test plan generation."""

    def test_llm_response_parsed_correctly(self):
        """Valid LLM JSON response parsed into AdvisoryTestPlan."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        deps["llm_client"].complete_sync.return_value = _llm_plan_response()
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        assert result.success is True
        assert result.data["test_plan_generated"] is True
        assert result.data["steps_total"] == 3
        assert len(result.data["verification_steps"]) == 3
        expected = "Memory leak in connection pool causing OOM kills"
        assert result.data["hypothesis_statement"] == expected

    def test_response_with_markdown_fences_parsed(self):
        """LLM response wrapped in markdown code fences is handled."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        raw = "```json\n" + _llm_plan_response() + "\n```"
        deps["llm_client"].complete_sync.return_value = raw
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        assert result.success is True
        assert result.data["test_plan_generated"] is True
        assert result.data["steps_total"] == 3

    def test_invalid_json_falls_back_to_minimal_plan(self):
        """Invalid JSON from LLM produces a fallback plan."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        deps["llm_client"].complete_sync.return_value = "this is not json"
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        assert result.success is True
        assert result.data["test_plan_generated"] is True
        assert result.data["steps_total"] == 1
        steps = result.data["verification_steps"]
        assert steps[0]["title"] == "Manual investigation required"
        assert steps[0]["verification_type"] == "manual_verification"

    def test_empty_steps_list_falls_back(self):
        """Empty verification_steps from LLM triggers fallback."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        deps["llm_client"].complete_sync.return_value = json.dumps({
            "hypothesis_statement": "test",
            "verification_steps": [],
            "expected_outcomes": [],
            "metrics_to_watch": [],
            "estimated_duration_minutes": 10,
        })
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        assert result.success is True
        assert result.data["test_plan_generated"] is True
        assert result.data["steps_total"] == 1
        assert result.data["verification_steps"][0]["title"] == "Manual investigation required"

    def test_metrics_to_watch_populated(self):
        """Metrics to watch are captured from LLM response."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        deps["llm_client"].complete_sync.return_value = _llm_plan_response()
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        assert "container_memory_working_set_bytes" in result.data["metrics_to_watch"]
        assert "kube_pod_container_status_restarts_total" in result.data["metrics_to_watch"]

    def test_expected_outcomes_captured(self):
        """Expected outcomes from LLM response are in result data."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        deps["llm_client"].complete_sync.return_value = _llm_plan_response()
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        assert len(result.data["expected_outcomes"]) == 2
        assert "Memory usage decreases after fix" in result.data["expected_outcomes"]

    def test_llm_exception_returns_failure_result(self):
        """LLM call exception returns graceful failure."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        deps["llm_client"].complete_sync.side_effect = RuntimeError("LLM unavailable")
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        assert result.success is True
        assert result.data["test_plan_generated"] is False
        assert result.data["skip_reason"] == "generation_failed"

    def test_estimated_duration_captured(self):
        """Estimated duration from LLM response is in result data."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        deps["llm_client"].complete_sync.return_value = _llm_plan_response()
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        assert result.data["estimated_duration_minutes"] == 15


class TestVerificationStepStructure:
    """Tests for verification step data structure."""

    def test_step_has_all_required_fields(self):
        """Each verification step has all required fields."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        deps["llm_client"].complete_sync.return_value = _llm_plan_response()
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        for vs in result.data["verification_steps"]:
            assert "step_number" in vs
            assert "title" in vs
            assert "description" in vs
            assert "action" in vs
            assert "expected_outcome" in vs
            assert "metric_or_endpoint" in vs
            assert "verification_type" in vs
            assert "status" in vs

    def test_step_status_defaults_to_pending(self):
        """Each step has status='pending' for SRE tracking."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        deps["llm_client"].complete_sync.return_value = _llm_plan_response()
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        for vs in result.data["verification_steps"]:
            assert vs["status"] == "pending"

    def test_verification_type_is_valid(self):
        """Verification type must be one of the valid types."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        deps["llm_client"].complete_sync.return_value = _llm_plan_response()
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        for vs in result.data["verification_steps"]:
            assert vs["verification_type"] in VALID_VERIFICATION_TYPES

    def test_invalid_verification_type_normalized(self):
        """Invalid verification_type from LLM is normalized to manual_verification."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        bad_step = [{
            "step_number": 1,
            "title": "Test",
            "description": "Test step",
            "action": "do something",
            "expected_outcome": "something happens",
            "metric_or_endpoint": "some_metric",
            "verification_type": "invalid_type",
        }]
        deps["llm_client"].complete_sync.return_value = _llm_plan_response(steps=bad_step)
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        assert result.data["verification_steps"][0]["verification_type"] == "manual_verification"

    def test_step_numbers_preserved(self):
        """Step numbers from LLM response are preserved."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        deps["llm_client"].complete_sync.return_value = _llm_plan_response()
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        numbers = [vs["step_number"] for vs in result.data["verification_steps"]]
        assert numbers == [1, 2, 3]


class TestExecuteOrchestration:
    """Tests for full execute() flow."""

    def test_happy_path(self):
        """Full flow: hypothesis → plan → StepResult with all data."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        deps["llm_client"].complete_sync.return_value = _llm_plan_response()
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        assert result.success is True
        assert result.data["test_plan_generated"] is True
        assert result.data["confidence_level"] == "high"
        assert result.data["confidence_percentage"] == 85
        assert result.data["steps_total"] == 3
        assert len(result.data["verification_steps"]) == 3
        assert result.data["test_plan_model_tier"] == "remediation"
        assert result.data["test_plan_model_used"] == "test-model"
        assert "Advisory test plan generated" in result.summary

    def test_no_hypothesis_path(self):
        """Without hypothesis, step skips gracefully."""
        step, _ = _make_step(pipeline_metadata={})

        result = step.execute()

        assert result.success is True
        assert result.data["test_plan_generated"] is False
        assert result.data["skip_reason"] == "no_hypothesis"
        assert "skipped" in result.summary.lower()

    def test_llm_failure_path(self):
        """LLM failure produces graceful result with failure metadata."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        deps["llm_client"].complete_sync.side_effect = RuntimeError("timeout")
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        assert result.success is True
        assert result.data["test_plan_generated"] is False
        assert result.data["skip_reason"] == "generation_failed"

    def test_model_tier_in_result(self):
        """Result includes model tier and model used."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        deps["llm_client"].complete_sync.return_value = _llm_plan_response()
        deps["llm_client"].select_model.return_value = "claude-opus-4"

        result = step.execute()

        assert result.data["test_plan_model_tier"] == "remediation"
        assert result.data["test_plan_model_used"] == "claude-opus-4"

    def test_status_updater_called(self):
        """Status updater is called during execution."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        deps["llm_client"].complete_sync.return_value = _llm_plan_response()
        deps["llm_client"].select_model.return_value = "test-model"

        step.execute()

        assert deps["status_updater"].update_message.call_count >= 1


class TestSandboxPromotion:
    """Tests for sandbox promotion compatibility (AC #3)."""

    def test_promotable_to_sandbox_always_true(self):
        """promotable_to_sandbox is always True."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        deps["llm_client"].complete_sync.return_value = _llm_plan_response()
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        assert result.data["promotable_to_sandbox"] is True

    def test_verification_steps_serialized_for_sandbox(self):
        """Verification steps include all data needed for sandbox execution."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        deps["llm_client"].complete_sync.return_value = _llm_plan_response()
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        for vs in result.data["verification_steps"]:
            # Sandbox executor (Story 4-5) needs these fields
            assert "action" in vs
            assert "verification_type" in vs
            assert "expected_outcome" in vs
            assert "metric_or_endpoint" in vs

    def test_plan_generated_regardless_of_trust_level(self):
        """Test plan is generated at TL1 (advisory) — no trust gating."""
        for tl in [1, 2, 3, 4, 5]:
            ctx = _make_context(trust_level=tl)
            metadata = _hypothesis_metadata()
            step, deps = _make_step(pipeline_metadata=metadata, context=ctx)
            deps["llm_client"].complete_sync.return_value = _llm_plan_response()
            deps["llm_client"].select_model.return_value = "test-model"

            result = step.execute()

            assert result.data["test_plan_generated"] is True, f"Failed at TL{tl}"


class TestDataclasses:
    """Tests for TestPlanStep and AdvisoryTestPlan dataclasses."""

    def test_test_plan_step_creation(self):
        """TestPlanStep can be created with all fields."""
        step = TestPlanStep(
            step_number=1,
            title="Check metrics",
            description="Query Prometheus",
            action="PromQL: up{job='payments'}",
            expected_outcome="Service up",
            metric_or_endpoint="up",
            verification_type="metric_check",
        )
        assert step.step_number == 1
        assert step.verification_type == "metric_check"

    def test_advisory_test_plan_defaults(self):
        """AdvisoryTestPlan has correct defaults."""
        plan = AdvisoryTestPlan(
            hypothesis_statement="test",
            confidence_level="high",
            confidence_percentage=90,
        )
        assert plan.verification_steps == []
        assert plan.expected_outcomes == []
        assert plan.metrics_to_watch == []
        assert plan.estimated_duration_minutes == 15
        assert plan.promotable_to_sandbox is True

    def test_model_fallback_to_deep_rca(self):
        """When remediation tier unavailable, falls back to deep_rca."""
        step, deps = _make_step(pipeline_metadata=_hypothesis_metadata())

        def side_effect(tier):
            if tier == "remediation":
                return None
            return "deep-rca-model"

        deps["llm_client"].select_model.side_effect = side_effect

        model = step._get_model_name()
        assert model == "deep-rca-model"

    def test_non_dict_step_entries_skipped(self):
        """Non-dict entries in verification_steps are skipped with logging."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        mixed_steps = [
            "not a dict",
            {
                "step_number": 1,
                "title": "Valid step",
                "description": "A valid step",
                "action": "check something",
                "expected_outcome": "pass",
                "metric_or_endpoint": "some_metric",
                "verification_type": "metric_check",
            },
            42,
            None,
        ]
        deps["llm_client"].complete_sync.return_value = _llm_plan_response(steps=mixed_steps)
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        assert result.success is True
        assert result.data["test_plan_generated"] is True
        # Only the valid dict entry should survive
        assert result.data["steps_total"] == 1
        assert result.data["verification_steps"][0]["title"] == "Valid step"

    def test_all_model_tiers_none_returns_none(self):
        """When all model tiers return None, _get_model_name returns None."""
        step, deps = _make_step(pipeline_metadata=_hypothesis_metadata())
        deps["llm_client"].select_model.return_value = None

        model = step._get_model_name()
        assert model is None

    def test_model_none_passed_to_llm(self):
        """When _get_model_name returns None, complete_sync is called with model=None."""
        metadata = _hypothesis_metadata()
        step, deps = _make_step(pipeline_metadata=metadata)
        deps["llm_client"].select_model.return_value = None
        deps["llm_client"].complete_sync.return_value = _llm_plan_response()

        result = step.execute()

        # Should still work — LLM client handles None model gracefully
        assert result.success is True
        assert result.data["test_plan_generated"] is True
        assert result.data["test_plan_model_used"] is None
        # Verify complete_sync was called with model=None
        call_kwargs = deps["llm_client"].complete_sync.call_args
        assert call_kwargs[1]["model"] is None
