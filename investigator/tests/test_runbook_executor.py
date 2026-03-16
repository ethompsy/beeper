"""Tests for RunbookExecutorStep (Story 4.2)."""

import json
import logging
from unittest.mock import MagicMock, patch

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.kb.client import KBClient
from beeper_investigator.kb.schemas import SearchResult
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.remediation.runbook_executor import (
    RUNBOOK_MATCH_THRESHOLD,
    RunbookExecutorStep,
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


def _make_step(**overrides):
    """Factory for RunbookExecutorStep with mocked dependencies."""
    llm = MagicMock(spec=LlmClient)
    kb = MagicMock(spec=KBClient)
    ctx = overrides.pop("context", _make_context())
    status = MagicMock(spec=InvestigationStatusUpdater)
    metadata = overrides.pop("pipeline_metadata", {})

    defaults = {
        "llm_client": llm,
        "kb_client": kb,
        "context": ctx,
        "status_updater": status,
        "pipeline_metadata": metadata,
    }
    defaults.update(overrides)
    step = RunbookExecutorStep(**defaults)
    return step, defaults


def _runbook_payload(
    title="Restart Service Runbook",
    content="1. Check pod status\n2. Restart deployment",
):
    """Create a runbook KB payload."""
    return {
        "title": title,
        "content": content,
        "entry_id": "rb-001",
        "entry_type": "runbook",
        "service": "payments",
    }


def _llm_response(steps):
    """Create a mock LLM response with interpreted steps."""
    return json.dumps({"steps": steps})


class TestRunbookSearch:
    """Tests for KB runbook search and selection."""

    def test_no_runbook_found_returns_skip(self):
        """When no runbooks match, return skip result."""
        step, deps = _make_step()
        deps["llm_client"].embed_sync.return_value = [0.0] * 1536
        deps["kb_client"].search_knowledge.return_value = []

        result = step.execute()

        assert result.success is True
        assert result.data["runbook_found"] is False
        assert result.data["runbook_execution_skipped"] is True

    def test_runbook_below_threshold_skipped(self):
        """Runbook with score below threshold is skipped."""
        step, deps = _make_step()
        deps["llm_client"].embed_sync.return_value = [0.0] * 1536
        deps["kb_client"].search_knowledge.return_value = [
            SearchResult(id="r1", score=RUNBOOK_MATCH_THRESHOLD - 0.01, payload=_runbook_payload()),
        ]

        result = step.execute()

        assert result.success is True
        assert result.data["runbook_found"] is False

    def test_best_runbook_selected(self):
        """Highest-scoring runbook above threshold is selected."""
        step, deps = _make_step()
        deps["llm_client"].embed_sync.return_value = [0.0] * 1536
        low = SearchResult(id="r1", score=0.76, payload=_runbook_payload("Low Match"))
        high = SearchResult(id="r2", score=0.92, payload=_runbook_payload("High Match"))
        deps["kb_client"].search_knowledge.return_value = [low, high]

        # Mock interpretation
        steps_json = _llm_response([{
            "step_number": 1,
            "original_text": "Check pod status",
            "action_type": "diagnostic_check",
            "interpreted_action": "kubectl get pods",
            "confidence": 0.95,
            "k8s_resource": "pod",
            "k8s_operation": "get",
        }])
        deps["llm_client"].complete_sync.return_value = steps_json
        deps["llm_client"].select_model.return_value = "test-model"

        result = step.execute()

        assert result.data["runbook_found"] is True
        assert result.data["runbook_title"] == "High Match"

    def test_embedding_failure_returns_no_runbook(self):
        """When embedding fails, return no runbook found."""
        step, deps = _make_step()
        deps["llm_client"].embed_sync.side_effect = RuntimeError("embed failed")

        result = step.execute()

        assert result.success is True
        assert result.data["runbook_found"] is False

    def test_kb_search_failure_returns_no_runbook(self):
        """When KB search fails, return no runbook found."""
        step, deps = _make_step()
        deps["llm_client"].embed_sync.return_value = [0.0] * 1536
        deps["kb_client"].search_knowledge.side_effect = RuntimeError("KB down")

        result = step.execute()

        assert result.success is True
        assert result.data["runbook_found"] is False


class TestRunbookInterpretation:
    """Tests for LLM runbook interpretation."""

    def test_valid_response_parsed(self):
        """Valid LLM JSON response is parsed correctly."""
        step, deps = _make_step()
        deps["llm_client"].embed_sync.return_value = [0.0] * 1536
        deps["kb_client"].search_knowledge.return_value = [
            SearchResult(id="r1", score=0.9, payload=_runbook_payload()),
        ]
        deps["llm_client"].select_model.return_value = "test-model"

        steps_json = _llm_response([
            {
                "step_number": 1,
                "original_text": "Check pods",
                "action_type": "diagnostic_check",
                "interpreted_action": "kubectl get pods -n payments",
                "confidence": 0.95,
                "k8s_resource": "pod",
                "k8s_operation": "get",
            },
            {
                "step_number": 2,
                "original_text": "Restart deployment",
                "action_type": "cluster_action",
                "interpreted_action": "kubectl rollout restart deployment/payments",
                "confidence": 0.88,
                "k8s_resource": "deployment",
                "k8s_operation": "restart",
            },
        ])
        deps["llm_client"].complete_sync.return_value = steps_json

        result = step.execute()

        assert result.data["runbook_found"] is True
        assert result.data["steps_total"] == 2

    def test_markdown_fenced_response_parsed(self):
        """Response wrapped in markdown code fences is handled."""
        step, deps = _make_step()
        deps["llm_client"].embed_sync.return_value = [0.0] * 1536
        deps["kb_client"].search_knowledge.return_value = [
            SearchResult(id="r1", score=0.9, payload=_runbook_payload()),
        ]
        deps["llm_client"].select_model.return_value = "test-model"

        inner = json.dumps({"steps": [{
            "step_number": 1,
            "original_text": "Check logs",
            "action_type": "diagnostic_check",
            "interpreted_action": "View application logs",
            "confidence": 0.9,
            "k8s_resource": None,
            "k8s_operation": None,
        }]})
        deps["llm_client"].complete_sync.return_value = f"```json\n{inner}\n```"

        result = step.execute()

        assert result.data["steps_total"] == 1

    def test_invalid_json_graceful_fallback(self):
        """Invalid JSON from LLM is handled gracefully."""
        step, deps = _make_step()
        deps["llm_client"].embed_sync.return_value = [0.0] * 1536
        deps["kb_client"].search_knowledge.return_value = [
            SearchResult(id="r1", score=0.9, payload=_runbook_payload()),
        ]
        deps["llm_client"].select_model.return_value = "test-model"
        deps["llm_client"].complete_sync.return_value = "not valid json at all"

        result = step.execute()

        assert result.success is True
        assert "no steps could be interpreted" in result.summary

    def test_action_type_normalization(self):
        """Unknown action_type defaults to manual_step."""
        step, _ = _make_step()
        validated = step._validate_interpreted_steps([{
            "step_number": 1,
            "original_text": "Do something",
            "action_type": "unknown_type",
            "interpreted_action": "Do it",
            "confidence": 0.8,
        }])

        assert len(validated) == 1
        assert validated[0]["action_type"] == "manual_step"

    def test_confidence_clamping(self):
        """Confidence values are clamped to 0.0-1.0."""
        step, _ = _make_step()
        validated = step._validate_interpreted_steps([
            {
                "step_number": 1,
                "original_text": "Step A",
                "action_type": "diagnostic_check",
                "interpreted_action": "Do A",
                "confidence": 1.5,
            },
            {
                "step_number": 2,
                "original_text": "Step B",
                "action_type": "diagnostic_check",
                "interpreted_action": "Do B",
                "confidence": -0.3,
            },
        ])

        assert validated[0]["confidence"] == 1.0
        assert validated[1]["confidence"] == 0.0

    def test_missing_original_text_skipped(self):
        """Steps missing original_text are filtered out."""
        step, _ = _make_step()
        validated = step._validate_interpreted_steps([
            {"step_number": 1, "action_type": "diagnostic_check", "confidence": 0.9},
            {
                "step_number": 2, "original_text": "Valid",
                "action_type": "diagnostic_check", "confidence": 0.9,
            },
        ])

        assert len(validated) == 1
        assert validated[0]["original_text"] == "Valid"

    def test_all_fields_present_in_validated_step(self):
        """Validated steps have all required fields."""
        step, _ = _make_step()
        validated = step._validate_interpreted_steps([{
            "step_number": 1,
            "original_text": "Check it",
            "action_type": "diagnostic_check",
            "interpreted_action": "Do check",
            "confidence": 0.85,
            "k8s_resource": "pod",
            "k8s_operation": "get",
        }])

        s = validated[0]
        assert "step_number" in s
        assert "original_text" in s
        assert "action_type" in s
        assert "interpreted_action" in s
        assert "confidence" in s
        assert "k8s_resource" in s
        assert "k8s_operation" in s

    def test_llm_exception_handled(self):
        """LLM exception during interpretation returns graceful result."""
        step, deps = _make_step()
        deps["llm_client"].embed_sync.return_value = [0.0] * 1536
        deps["kb_client"].search_knowledge.return_value = [
            SearchResult(id="r1", score=0.9, payload=_runbook_payload()),
        ]
        deps["llm_client"].select_model.return_value = "test-model"
        deps["llm_client"].complete_sync.side_effect = RuntimeError("LLM down")

        result = step.execute()

        assert result.success is True
        assert "interpretation failed" in result.summary


class TestTrustGating:
    """Tests for trust-level gated execution."""

    def _setup_runbook_step(self, trust_level, confidence_threshold=0.9):
        """Helper to set up a step with runbook found and interpreted."""
        ctx = _make_context(trust_level=trust_level, confidence_threshold=confidence_threshold)
        step, deps = _make_step(context=ctx)
        deps["llm_client"].embed_sync.return_value = [0.0] * 1536
        deps["kb_client"].search_knowledge.return_value = [
            SearchResult(id="r1", score=0.9, payload=_runbook_payload()),
        ]
        deps["llm_client"].select_model.return_value = "test-model"
        return step, deps

    def test_tl1_advisory_only(self):
        """TL1 produces advisory actions for cluster_actions."""
        step, deps = self._setup_runbook_step(trust_level=1)

        steps_json = _llm_response([
            {
                "step_number": 1,
                "original_text": "Restart pod",
                "action_type": "cluster_action",
                "interpreted_action": "kubectl rollout restart",
                "confidence": 0.95,
                "k8s_resource": "deployment",
                "k8s_operation": "restart",
            },
        ])
        deps["llm_client"].complete_sync.return_value = steps_json

        result = step.execute()

        assert result.data["steps_advisory"] == 1
        assert result.data["steps_blocked"] == 0
        log = result.data["execution_log"][0]
        assert log["status"] == "advisory"

    def test_tl2_advisory_only(self):
        """TL2 also produces advisory for cluster_actions."""
        step, deps = self._setup_runbook_step(trust_level=2)

        steps_json = _llm_response([{
            "step_number": 1,
            "original_text": "Scale up",
            "action_type": "cluster_action",
            "interpreted_action": "kubectl scale --replicas=3",
            "confidence": 0.95,
            "k8s_resource": "deployment",
            "k8s_operation": "scale",
        }])
        deps["llm_client"].complete_sync.return_value = steps_json

        result = step.execute()

        assert result.data["steps_advisory"] == 1
        log = result.data["execution_log"][0]
        assert log["status"] == "advisory"

    def test_tl3_high_confidence_approved(self):
        """TL3 with confidence above threshold approves execution."""
        step, deps = self._setup_runbook_step(trust_level=3, confidence_threshold=0.9)

        steps_json = _llm_response([{
            "step_number": 1,
            "original_text": "Restart pod",
            "action_type": "cluster_action",
            "interpreted_action": "kubectl rollout restart",
            "confidence": 0.95,
            "k8s_resource": "deployment",
            "k8s_operation": "restart",
        }])
        deps["llm_client"].complete_sync.return_value = steps_json

        result = step.execute()

        log = result.data["execution_log"][0]
        assert log["status"] == "approved"
        assert result.data["steps_blocked"] == 0

    def test_tl3_low_confidence_blocked(self):
        """TL3 with confidence below threshold blocks execution."""
        step, deps = self._setup_runbook_step(trust_level=3, confidence_threshold=0.9)

        steps_json = _llm_response([{
            "step_number": 1,
            "original_text": "Dangerous action",
            "action_type": "cluster_action",
            "interpreted_action": "kubectl delete pod",
            "confidence": 0.7,
            "k8s_resource": "pod",
            "k8s_operation": "delete",
        }])
        deps["llm_client"].complete_sync.return_value = steps_json

        result = step.execute()

        assert result.data["steps_blocked"] == 1
        log = result.data["execution_log"][0]
        assert log["status"] == "blocked"

    def test_diagnostic_check_always_executes(self):
        """diagnostic_check runs regardless of trust level."""
        for tl in [1, 2, 3, 4, 5]:
            step, deps = self._setup_runbook_step(trust_level=tl)
            steps_json = _llm_response([{
                "step_number": 1,
                "original_text": "Check logs",
                "action_type": "diagnostic_check",
                "interpreted_action": "kubectl logs",
                "confidence": 0.5,
                "k8s_resource": None,
                "k8s_operation": None,
            }])
            deps["llm_client"].complete_sync.return_value = steps_json

            result = step.execute()
            log = result.data["execution_log"][0]
            assert log["status"] == "executed", f"Failed at TL{tl}"

    def test_manual_step_never_auto_executes(self):
        """manual_step is always marked as requiring human action."""
        for tl in [1, 3, 5]:
            step, deps = self._setup_runbook_step(trust_level=tl)
            steps_json = _llm_response([{
                "step_number": 1,
                "original_text": "Contact team lead",
                "action_type": "manual_step",
                "interpreted_action": "Contact the team lead for approval",
                "confidence": 0.99,
                "k8s_resource": None,
                "k8s_operation": None,
            }])
            deps["llm_client"].complete_sync.return_value = steps_json

            result = step.execute()
            log = result.data["execution_log"][0]
            assert log["status"] == "manual", f"Failed at TL{tl}"


class TestStepFailure:
    """Tests for step failure and halt behavior."""

    def test_failure_halts_execution(self):
        """Step failure halts pipeline and captures error context."""
        ctx = _make_context(trust_level=3, confidence_threshold=0.5)
        step, _ = _make_step(context=ctx)

        interpreted = [
            {
                "step_number": 1,
                "original_text": "Check logs",
                "action_type": "diagnostic_check",
                "interpreted_action": "kubectl logs",
                "confidence": 0.95,
                "k8s_resource": None,
                "k8s_operation": None,
            },
            {
                "step_number": 2,
                "original_text": "Restart pod",
                "action_type": "cluster_action",
                "interpreted_action": "kubectl rollout restart",
                "confidence": 0.95,
                "k8s_resource": "deployment",
                "k8s_operation": "restart",
            },
            {
                "step_number": 3,
                "original_text": "Scale up",
                "action_type": "cluster_action",
                "interpreted_action": "scale",
                "confidence": 0.9,
                "k8s_resource": "deployment",
                "k8s_operation": "scale",
            },
        ]

        # Patch logger.info to raise on the second call (step 2's log)
        original_info = logging.getLogger("beeper_investigator.remediation.runbook_executor").info
        call_count = 0

        def _exploding_info(msg, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            # call 1 = step 1 diagnostic log; call 2 = step 2 approved log → explode
            if call_count >= 2:
                raise RuntimeError("simulated step failure")
            return original_info(msg, *args, **kwargs)

        with patch.object(
            logging.getLogger("beeper_investigator.remediation.runbook_executor"),
            "info",
            side_effect=_exploding_info,
        ):
            result = step._execute_steps(interpreted)

        assert result.halted is True
        assert result.failed_step is not None
        assert result.failed_step["step_number"] == 2
        assert "simulated step failure" in result.failed_step["error"]
        assert len(result.remaining_steps) == 1
        assert result.remaining_steps[0]["step_number"] == 3

    def test_remaining_steps_captured_on_halt(self):
        """On halt, remaining unexecuted steps are captured."""
        ctx = _make_context(trust_level=1)
        step, _ = _make_step(context=ctx)

        interpreted = [
            {
                "step_number": 1,
                "original_text": "Check logs",
                "action_type": "diagnostic_check",
                "interpreted_action": "kubectl logs",
                "confidence": 0.95,
                "k8s_resource": None,
                "k8s_operation": None,
            },
            {
                "step_number": 2,
                "original_text": "Restart pod",
                "action_type": "cluster_action",
                "interpreted_action": "kubectl rollout restart",
                "confidence": 0.95,
                "k8s_resource": "deployment",
                "k8s_operation": "restart",
            },
            {
                "step_number": 3,
                "original_text": "Scale up",
                "action_type": "cluster_action",
                "interpreted_action": "scale",
                "confidence": 0.9,
                "k8s_resource": "deployment",
                "k8s_operation": "scale",
            },
        ]

        # Explode on step 2 to verify remaining_steps captures step 3
        original_info = logging.getLogger("beeper_investigator.remediation.runbook_executor").info
        call_count = 0

        def _exploding_info(msg, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            # call 1 = step 1 diagnostic log; call 2 = step 2 advisory log → explode
            if call_count >= 2:
                raise RuntimeError("boom")
            return original_info(msg, *args, **kwargs)

        with patch.object(
            logging.getLogger("beeper_investigator.remediation.runbook_executor"),
            "info",
            side_effect=_exploding_info,
        ):
            result = step._execute_steps(interpreted)

        assert result.halted is True
        assert result.failed_step is not None
        assert result.failed_step["step_number"] == 2
        assert len(result.remaining_steps) == 1
        assert result.remaining_steps[0]["step_number"] == 3
        # Step 1 should have completed before halt
        assert len(result.executed_steps) == 1
        assert result.executed_steps[0]["step_number"] == 1

    def test_partial_execution_reported(self):
        """Partial execution correctly reports executed count."""
        ctx = _make_context(trust_level=1)
        step, deps = _make_step(context=ctx)
        deps["llm_client"].embed_sync.return_value = [0.0] * 1536
        deps["kb_client"].search_knowledge.return_value = [
            SearchResult(id="r1", score=0.9, payload=_runbook_payload()),
        ]
        deps["llm_client"].select_model.return_value = "test-model"

        steps_json = _llm_response([
            {
                "step_number": 1,
                "original_text": "Check logs",
                "action_type": "diagnostic_check",
                "interpreted_action": "View logs",
                "confidence": 0.9,
                "k8s_resource": None,
                "k8s_operation": None,
            },
            {
                "step_number": 2,
                "original_text": "Restart",
                "action_type": "cluster_action",
                "interpreted_action": "Restart service",
                "confidence": 0.95,
                "k8s_resource": "deployment",
                "k8s_operation": "restart",
            },
        ])
        deps["llm_client"].complete_sync.return_value = steps_json

        result = step.execute()

        assert result.data["steps_total"] == 2
        assert result.data["steps_executed"] == 2
        assert result.data["steps_advisory"] == 1  # cluster_action at TL1


class TestExecuteOrchestration:
    """Tests for full execute() orchestration."""

    def test_happy_path(self):
        """Full happy path: runbook found → interpreted → executed."""
        ctx = _make_context(trust_level=3, confidence_threshold=0.8)
        step, deps = _make_step(context=ctx)
        deps["llm_client"].embed_sync.return_value = [0.0] * 1536
        deps["kb_client"].search_knowledge.return_value = [
            SearchResult(id="r1", score=0.9, payload=_runbook_payload("My Runbook")),
        ]
        deps["llm_client"].select_model.return_value = "test-model"

        steps_json = _llm_response([
            {
                "step_number": 1,
                "original_text": "Check pod health",
                "action_type": "diagnostic_check",
                "interpreted_action": "kubectl get pods",
                "confidence": 0.95,
                "k8s_resource": "pod",
                "k8s_operation": "get",
            },
            {
                "step_number": 2,
                "original_text": "Restart the deployment",
                "action_type": "cluster_action",
                "interpreted_action": "kubectl rollout restart",
                "confidence": 0.9,
                "k8s_resource": "deployment",
                "k8s_operation": "restart",
            },
        ])
        deps["llm_client"].complete_sync.return_value = steps_json

        result = step.execute()

        assert result.success is True
        assert result.data["runbook_found"] is True
        assert result.data["runbook_title"] == "My Runbook"
        assert result.data["steps_total"] == 2
        assert result.data["steps_executed"] == 2
        assert result.data["execution_halted"] is False
        assert "Executed runbook" in result.summary

    def test_no_runbook_path(self):
        """No runbook in KB returns clean skip."""
        step, deps = _make_step()
        deps["llm_client"].embed_sync.return_value = [0.0] * 1536
        deps["kb_client"].search_knowledge.return_value = []

        result = step.execute()

        assert result.success is True
        assert result.data["runbook_found"] is False
        assert "No matching runbook" in result.summary

    def test_interpretation_failure_path(self):
        """LLM failure returns graceful result."""
        step, deps = _make_step()
        deps["llm_client"].embed_sync.return_value = [0.0] * 1536
        deps["kb_client"].search_knowledge.return_value = [
            SearchResult(id="r1", score=0.9, payload=_runbook_payload()),
        ]
        deps["llm_client"].select_model.return_value = "test-model"
        deps["llm_client"].complete_sync.side_effect = Exception("LLM error")

        result = step.execute()

        assert result.success is True
        assert result.data["runbook_found"] is True
        assert result.data.get("interpretation_failed") is True

    def test_step_result_data_fields(self):
        """StepResult.data contains all expected fields on success."""
        ctx = _make_context(trust_level=1)
        step, deps = _make_step(context=ctx)
        deps["llm_client"].embed_sync.return_value = [0.0] * 1536
        deps["kb_client"].search_knowledge.return_value = [
            SearchResult(id="r1", score=0.9, payload=_runbook_payload("Test RB")),
        ]
        deps["llm_client"].select_model.return_value = "test-model"

        steps_json = _llm_response([{
            "step_number": 1,
            "original_text": "Check it",
            "action_type": "diagnostic_check",
            "interpreted_action": "Do check",
            "confidence": 0.9,
            "k8s_resource": None,
            "k8s_operation": None,
        }])
        deps["llm_client"].complete_sync.return_value = steps_json

        result = step.execute()

        expected_keys = {
            "runbook_found", "runbook_title", "runbook_id",
            "steps_total", "steps_executed", "steps_advisory",
            "steps_blocked", "execution_halted", "failed_step_context",
            "remaining_steps", "advisory_actions", "execution_log",
            "runbook_model_tier", "runbook_model_used",
        }
        assert expected_keys.issubset(set(result.data.keys()))

    def test_mixed_action_types(self):
        """Mixed action types are handled correctly at TL1."""
        ctx = _make_context(trust_level=1)
        step, deps = _make_step(context=ctx)
        deps["llm_client"].embed_sync.return_value = [0.0] * 1536
        deps["kb_client"].search_knowledge.return_value = [
            SearchResult(id="r1", score=0.9, payload=_runbook_payload()),
        ]
        deps["llm_client"].select_model.return_value = "test-model"

        steps_json = _llm_response([
            {
                "step_number": 1,
                "original_text": "Check logs",
                "action_type": "diagnostic_check",
                "interpreted_action": "View logs",
                "confidence": 0.95,
                "k8s_resource": None,
                "k8s_operation": None,
            },
            {
                "step_number": 2,
                "original_text": "Restart pod",
                "action_type": "cluster_action",
                "interpreted_action": "Restart deployment",
                "confidence": 0.9,
                "k8s_resource": "deployment",
                "k8s_operation": "restart",
            },
            {
                "step_number": 3,
                "original_text": "Call team lead",
                "action_type": "manual_step",
                "interpreted_action": "Contact team lead",
                "confidence": 0.99,
                "k8s_resource": None,
                "k8s_operation": None,
            },
        ])
        deps["llm_client"].complete_sync.return_value = steps_json

        result = step.execute()

        assert result.data["steps_total"] == 3
        assert result.data["steps_executed"] == 3
        logs = result.data["execution_log"]
        assert logs[0]["status"] == "executed"   # diagnostic_check
        assert logs[1]["status"] == "advisory"   # cluster_action at TL1
        assert logs[2]["status"] == "manual"     # manual_step
