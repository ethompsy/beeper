"""Tests for TrustGateEvaluator, TrustGateStep — trust-gated remediation actions."""

from unittest.mock import MagicMock

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.remediation.trust_gate import (
    TrustGateDecision,
    TrustGateEvaluator,
    TrustGateStep,
)
from beeper_investigator.steps import InvestigationStep

# ── Factories ────────────────────────────────────────────


def _make_evaluator(trust_level=3, confidence_threshold=0.9):
    """Factory for TrustGateEvaluator with mocked dependencies."""
    ctx = InvestigationContext(
        investigation_id="test-inv-001",
        namespace="default",
        condition="high_error_rate",
        service="payments",
        severity="high",
        trust_level=trust_level,
        confidence_threshold=confidence_threshold,
    )
    status = MagicMock(spec=InvestigationStatusUpdater)
    evaluator = TrustGateEvaluator(ctx, status)
    return evaluator, ctx, status


def _make_step(pipeline_metadata=None, trust_level=3, **overrides):
    """Factory for TrustGateStep with mocked dependencies."""
    llm = MagicMock(spec=LlmClient)
    ctx = InvestigationContext(
        investigation_id="test-inv-001",
        namespace="default",
        condition="high_error_rate",
        service="payments",
        severity="high",
        trust_level=trust_level,
        confidence_threshold=0.9,
    )
    status = MagicMock(spec=InvestigationStatusUpdater)
    defaults = {
        "llm_client": llm,
        "context": ctx,
        "status_updater": status,
        "pipeline_metadata": pipeline_metadata or {},
    }
    defaults.update(overrides)
    step = TrustGateStep(**defaults)
    return step, defaults


# ── TrustGateDecision ────────────────────────────────────


class TestTrustGateDecision:
    def test_dataclass_creation(self):
        d = TrustGateDecision(
            allowed=True,
            action_type="executed",
            trust_level=3,
            confidence=0.95,
            confidence_threshold=0.9,
            reason="Test reason",
            advisory_message=None,
            rollback_registered=False,
        )
        assert d.allowed is True
        assert d.action_type == "executed"
        assert d.trust_level == 3
        assert d.confidence == 0.95

    def test_to_dict_serialization(self):
        d = TrustGateDecision(
            allowed=False,
            action_type="advisory",
            trust_level=1,
            confidence=None,
            confidence_threshold=0.9,
            reason="TL1 advisory",
            advisory_message="At TL3+, Beeper would: restart pod",
            rollback_registered=False,
            action_name="restart pod",
            action_category="cluster_mutation",
        )
        result = d.to_dict()
        assert isinstance(result, dict)
        assert result["allowed"] is False
        assert result["action_type"] == "advisory"
        assert result["confidence"] is None
        assert result["advisory_message"] == "At TL3+, Beeper would: restart pod"

    def test_to_dict_includes_action_name_and_category(self):
        d = TrustGateDecision(
            allowed=True,
            action_type="executed",
            trust_level=3,
            confidence=0.95,
            confidence_threshold=0.9,
            reason="OK",
            advisory_message=None,
            rollback_registered=False,
            action_name="Restart pod",
            action_category="cluster_mutation",
        )
        result = d.to_dict()
        assert result["action_name"] == "Restart pod"
        assert result["action_category"] == "cluster_mutation"


# ── Evaluate: read_only ──────────────────────────────────


class TestEvaluateReadOnly:
    def test_read_only_allowed_at_tl1(self):
        evaluator, _, _ = _make_evaluator(trust_level=1)
        decision = evaluator.evaluate("Check logs", "read_only")
        assert decision.allowed is True
        assert decision.action_type == "executed"
        assert decision.reason == "Always permitted"

    def test_evaluate_populates_action_name_and_category(self):
        evaluator, _, _ = _make_evaluator(trust_level=1)
        decision = evaluator.evaluate("Check logs", "read_only")
        assert decision.action_name == "Check logs"
        assert decision.action_category == "read_only"

    def test_read_only_allowed_at_tl3(self):
        evaluator, _, _ = _make_evaluator(trust_level=3)
        decision = evaluator.evaluate("Query metrics", "read_only")
        assert decision.allowed is True

    def test_read_only_allowed_at_tl5(self):
        evaluator, _, _ = _make_evaluator(trust_level=5)
        decision = evaluator.evaluate("Inspect pods", "read_only")
        assert decision.allowed is True


# ── Evaluate: notification ───────────────────────────────


class TestEvaluateNotification:
    def test_notification_allowed_at_tl1(self):
        evaluator, _, _ = _make_evaluator(trust_level=1)
        decision = evaluator.evaluate("Send Slack alert", "notification")
        assert decision.allowed is True
        assert decision.action_type == "executed"

    def test_notification_allowed_at_tl5(self):
        evaluator, _, _ = _make_evaluator(trust_level=5)
        decision = evaluator.evaluate("Send email", "notification")
        assert decision.allowed is True


# ── Evaluate: cluster_mutation TL1 ───────────────────────


class TestEvaluateClusterMutationTL1:
    def test_tl1_advisory_only(self):
        evaluator, _, _ = _make_evaluator(trust_level=1)
        decision = evaluator.evaluate("Restart pod", "cluster_mutation")
        assert decision.allowed is False
        assert decision.action_type == "advisory"
        assert "Trust level 1" in decision.reason
        assert decision.advisory_message is not None
        assert "TL3+" in decision.advisory_message


# ── Evaluate: cluster_mutation TL2 ───────────────────────


class TestEvaluateClusterMutationTL2:
    def test_tl2_advisory_only(self):
        evaluator, _, _ = _make_evaluator(trust_level=2)
        decision = evaluator.evaluate("Scale deployment", "cluster_mutation")
        assert decision.allowed is False
        assert decision.action_type == "advisory"
        assert "Trust level 2" in decision.reason


# ── Evaluate: cluster_mutation TL3 below threshold ───────


class TestEvaluateClusterMutationTL3BelowThreshold:
    def test_tl3_below_threshold_requires_approval(self):
        evaluator, _, _ = _make_evaluator(trust_level=3, confidence_threshold=0.85)
        decision = evaluator.evaluate(
            "Restart pod", "cluster_mutation", confidence=0.82
        )
        assert decision.allowed is False
        assert decision.action_type == "requires_approval"
        assert "0.82" in decision.reason
        assert "0.85" in decision.reason
        assert "manual approval" in decision.reason


# ── Evaluate: cluster_mutation TL3 above threshold ───────


class TestEvaluateClusterMutationTL3AboveThreshold:
    def test_tl3_above_threshold_allowed(self):
        evaluator, _, _ = _make_evaluator(trust_level=3, confidence_threshold=0.85)
        decision = evaluator.evaluate(
            "Restart pod", "cluster_mutation", confidence=0.90
        )
        assert decision.allowed is True
        assert decision.action_type == "executed"
        assert "above threshold" in decision.reason


# ── Evaluate: cluster_mutation TL4 ───────────────────────


class TestEvaluateClusterMutationTL4:
    def test_tl4_above_threshold_allowed(self):
        evaluator, _, _ = _make_evaluator(trust_level=4, confidence_threshold=0.9)
        decision = evaluator.evaluate(
            "Restart pod", "cluster_mutation", confidence=0.95
        )
        assert decision.allowed is True
        assert decision.action_type == "executed"

    def test_tl4_below_threshold_requires_approval(self):
        evaluator, _, _ = _make_evaluator(trust_level=4, confidence_threshold=0.9)
        decision = evaluator.evaluate(
            "Restart pod", "cluster_mutation", confidence=0.80
        )
        assert decision.allowed is False
        assert decision.action_type == "requires_approval"


# ── Evaluate: cluster_mutation TL5 ───────────────────────


class TestEvaluateClusterMutationTL5:
    def test_tl5_above_threshold_allowed(self):
        evaluator, _, _ = _make_evaluator(trust_level=5, confidence_threshold=0.9)
        decision = evaluator.evaluate(
            "Restart pod", "cluster_mutation", confidence=0.95
        )
        assert decision.allowed is True
        assert decision.action_type == "executed"


# ── Evaluate: code_change TL1-TL2 ───────────────────────


class TestEvaluateCodeChangeTL1TL2:
    def test_tl1_code_change_advisory(self):
        evaluator, _, _ = _make_evaluator(trust_level=1)
        decision = evaluator.evaluate("Create PR", "code_change")
        assert decision.allowed is False
        assert decision.action_type == "advisory"
        assert decision.advisory_message is not None
        assert "code changes" in decision.advisory_message

    def test_tl2_code_change_advisory(self):
        evaluator, _, _ = _make_evaluator(trust_level=2)
        decision = evaluator.evaluate("Create PR", "code_change")
        assert decision.allowed is False
        assert decision.action_type == "advisory"


# ── Evaluate: code_change TL3 ───────────────────────────


class TestEvaluateCodeChangeTL3:
    def test_tl3_code_change_above_threshold(self):
        evaluator, _, _ = _make_evaluator(trust_level=3, confidence_threshold=0.85)
        decision = evaluator.evaluate(
            "Create PR", "code_change", confidence=0.90
        )
        assert decision.allowed is True
        assert decision.action_type == "executed"

    def test_tl3_code_change_below_threshold(self):
        evaluator, _, _ = _make_evaluator(trust_level=3, confidence_threshold=0.85)
        decision = evaluator.evaluate(
            "Create PR", "code_change", confidence=0.80
        )
        assert decision.allowed is False
        assert decision.action_type == "requires_approval"


# ── Unrecognized action_category ─────────────────────────


class TestUnrecognizedActionCategory:
    def test_unrecognized_category_logs_warning(self, caplog):
        evaluator, _, _ = _make_evaluator(trust_level=1)
        decision = evaluator.evaluate("Unknown action", "unknown_category")
        assert decision.allowed is False
        assert decision.action_type == "advisory"
        assert "Unrecognized action_category" in caplog.text
        assert "unknown_category" in caplog.text


# ── Advisory message ─────────────────────────────────────


class TestAdvisoryMessage:
    def test_cluster_mutation_advisory_message(self):
        evaluator, _, _ = _make_evaluator(trust_level=1)
        decision = evaluator.evaluate("Restart pod", "cluster_mutation")
        assert "At TL3+, Beeper would: Restart pod" in decision.advisory_message
        assert "apply cluster changes" in decision.advisory_message

    def test_code_change_advisory_message(self):
        evaluator, _, _ = _make_evaluator(trust_level=1)
        decision = evaluator.evaluate("Create PR", "code_change")
        assert "At TL3+, Beeper would: Create PR" in decision.advisory_message
        assert "commit code changes" in decision.advisory_message


# ── Rollback registration ────────────────────────────────


class TestRollbackRegistration:
    def test_register_rollback_path_returns_entry(self):
        evaluator, _, _ = _make_evaluator()
        entry = evaluator.register_rollback_path(
            action_name="Auto-PR",
            rollback_action="Close PR and revert",
        )
        assert entry["action_name"] == "Auto-PR"
        assert entry["rollback_action"] == "Close PR and revert"
        assert entry["investigation_id"] == "test-inv-001"
        assert "registered_at" in entry

    def test_rollback_paths_in_summary(self):
        evaluator, _, _ = _make_evaluator()
        evaluator.register_rollback_path("Auto-PR", "Close PR")
        evaluator.register_rollback_path("Sandbox", "Delete namespace")
        summary = evaluator.get_summary()
        assert len(summary.rollback_paths) == 2


# ── Autonomous notification ──────────────────────────────


class TestAutonomousNotification:
    def test_notify_autonomous_action_logs_and_updates(self):
        evaluator, _, status = _make_evaluator()
        evaluator.notify_autonomous_action(
            action_name="Auto-PR created",
            action_details={"pr_url": "https://github.com/..."},
        )
        status.update_message.assert_called_once()
        call_arg = status.update_message.call_args[0][0]
        assert "Auto-PR created" in call_arg


# ── TrustGateSummary ─────────────────────────────────────


class TestTrustGateSummary:
    def test_summary_aggregation(self):
        evaluator, _, _ = _make_evaluator(trust_level=3, confidence_threshold=0.9)
        # Generate mixed decisions
        evaluator.evaluate("Check logs", "read_only")
        evaluator.evaluate("Send alert", "notification")
        evaluator.evaluate("Restart pod", "cluster_mutation", confidence=0.95)
        evaluator.evaluate("Create PR", "code_change", confidence=0.80)

        summary = evaluator.get_summary()
        assert summary.total_actions == 4
        assert summary.executed == 3  # read_only + notification + cluster_mutation above threshold
        assert summary.advisory == 0
        assert summary.requires_approval == 1  # code_change below threshold
        assert len(summary.decisions) == 4

    def test_summary_with_tl1_advisory(self):
        evaluator, _, _ = _make_evaluator(trust_level=1)
        evaluator.evaluate("Restart pod", "cluster_mutation")
        evaluator.evaluate("Check logs", "read_only")

        summary = evaluator.get_summary()
        assert summary.total_actions == 2
        assert summary.executed == 1
        assert summary.advisory == 1


# ── Confidence None handling ─────────────────────────────


class TestConfidenceNone:
    def test_confidence_none_treated_as_zero(self):
        evaluator, _, _ = _make_evaluator(trust_level=3, confidence_threshold=0.9)
        decision = evaluator.evaluate(
            "Restart pod", "cluster_mutation", confidence=None
        )
        assert decision.allowed is False
        assert decision.action_type == "requires_approval"
        assert "0.00" in decision.reason

    def test_confidence_none_at_tl1_still_advisory(self):
        evaluator, _, _ = _make_evaluator(trust_level=1)
        decision = evaluator.evaluate(
            "Restart pod", "cluster_mutation", confidence=None
        )
        assert decision.allowed is False
        assert decision.action_type == "advisory"


# ── TrustGateStep execution ─────────────────────────────


class TestTrustGateStepExecution:
    def test_step_protocol_compliance(self):
        step, _ = _make_step()
        assert isinstance(step, InvestigationStep)
        assert step.name == "Trust Gate Evaluation"

    def test_empty_pipeline_metadata(self):
        step, _ = _make_step(pipeline_metadata={})
        result = step.execute()
        assert result.success is True
        assert result.data["trust_gate_evaluated"] is True
        assert result.data["trust_gate_total_actions"] == 0

    def test_step_returns_trust_level_in_data(self):
        step, _ = _make_step(trust_level=4)
        result = step.execute()
        assert result.data["trust_gate_trust_level"] == 4
        assert result.data["trust_gate_confidence_threshold"] == 0.9


# ── TrustGateStep with runbook data ─────────────────────


class TestTrustGateStepWithRunbookData:
    def test_runbook_execution_evaluated(self):
        metadata = {
            "runbook_found": True,
            "steps_executed": 3,
            "steps_advisory": 1,
            "confidence_percentage": 85,
        }
        step, _ = _make_step(pipeline_metadata=metadata, trust_level=3)
        result = step.execute()
        assert result.data["trust_gate_total_actions"] >= 2
        assert result.success is True

    def test_runbook_not_found_no_evaluation(self):
        metadata = {"runbook_found": False}
        step, _ = _make_step(pipeline_metadata=metadata)
        result = step.execute()
        # No runbook actions evaluated
        assert result.data["trust_gate_total_actions"] == 0


# ── TrustGateStep with sandbox data ─────────────────────


class TestTrustGateStepWithSandboxData:
    def test_sandbox_executed_evaluated(self):
        metadata = {
            "sandbox_executed": True,
            "sandbox_overall_status": "pass",
            "confidence_percentage": 92,
        }
        step, _ = _make_step(pipeline_metadata=metadata, trust_level=3)
        result = step.execute()
        assert result.data["trust_gate_total_actions"] >= 1

    def test_sandbox_skipped_trust_insufficient(self):
        metadata = {
            "sandbox_executed": False,
            "skip_reason": "trust_level_insufficient",
        }
        step, _ = _make_step(pipeline_metadata=metadata, trust_level=1)
        result = step.execute()
        assert result.data["trust_gate_total_actions"] >= 1


# ── TrustGateStep with PR data ──────────────────────────


class TestTrustGateStepWithPRData:
    def test_pr_generated_evaluated(self):
        metadata = {
            "pr_generated": True,
            "pr_url": "https://github.com/org/repo/pull/42",
            "draft": True,
            "trust_level": 3,
            "confidence_percentage": 90,
        }
        step, _ = _make_step(pipeline_metadata=metadata, trust_level=3)
        result = step.execute()
        assert result.data["trust_gate_total_actions"] >= 1

    def test_pr_not_generated_no_evaluation(self):
        metadata = {"pr_generated": None}
        step, _ = _make_step(pipeline_metadata=metadata)
        result = step.execute()
        # No PR actions evaluated
        assert "pr" not in str(result.data.get("trust_gate_decisions", [])).lower() or \
            result.data["trust_gate_total_actions"] == 0


# ── TrustGateStep with metric verification data ─────────


class TestTrustGateStepWithMetricVerificationData:
    def test_verification_executed_evaluated(self):
        metadata = {
            "verification_executed": True,
            "verification_status": "confirmed",
        }
        step, _ = _make_step(pipeline_metadata=metadata, trust_level=3)
        result = step.execute()
        assert result.data["trust_gate_total_actions"] >= 1

    def test_verification_skipped_trust_insufficient(self):
        metadata = {
            "verification_executed": False,
            "verification_skip_reason": "trust_level_insufficient",
        }
        step, _ = _make_step(pipeline_metadata=metadata, trust_level=1)
        result = step.execute()
        # Read-only action still evaluated
        assert result.data["trust_gate_total_actions"] >= 1

    def test_rollback_paths_at_tl4(self):
        metadata = {
            "pr_generated": True,
            "pr_url": "https://github.com/org/repo/pull/42",
            "sandbox_executed": True,
            "confidence_percentage": 95,
        }
        step, _ = _make_step(pipeline_metadata=metadata, trust_level=4)
        result = step.execute()
        assert len(result.data["trust_gate_rollback_paths"]) == 2

    def test_no_rollback_paths_at_tl3(self):
        metadata = {
            "pr_generated": True,
            "pr_url": "https://github.com/org/repo/pull/42",
            "confidence_percentage": 95,
        }
        step, _ = _make_step(pipeline_metadata=metadata, trust_level=3)
        result = step.execute()
        assert len(result.data["trust_gate_rollback_paths"]) == 0

    def test_autonomous_notification_at_tl5(self):
        metadata = {
            "pr_generated": True,
            "pr_url": "https://github.com/org/repo/pull/42",
            "draft": False,
            "confidence_percentage": 95,
        }
        step, defs = _make_step(pipeline_metadata=metadata, trust_level=5)
        step.execute()
        # status_updater should have been called for autonomous action
        defs["status_updater"].update_message.assert_any_call(
            "Autonomous action: Auto-PR created"
        )

    def test_approval_required_flag(self):
        metadata = {
            "pr_generated": True,
            "pr_url": "https://github.com/org/repo/pull/42",
            "confidence_percentage": 50,
        }
        step, _ = _make_step(pipeline_metadata=metadata, trust_level=3)
        result = step.execute()
        # PR at TL3 with confidence 0.50 < 0.9 → requires approval
        assert result.data["trust_gate_approval_required"] is True
