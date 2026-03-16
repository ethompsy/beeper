"""Tests for MetricVerifierStep — post-fix metric verification."""

from unittest.mock import MagicMock, patch

from beeper_investigator.agent import SourceClients
from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.remediation.metric_verifier import (
    MetricVerifierStep,
    VerificationResult,
)
from beeper_investigator.steps import InvestigationStep

# ── Factories ────────────────────────────────────────────


_SENTINEL = object()


def _make_step(pipeline_metadata=None, trust_level=3, sources=_SENTINEL, **overrides):
    """Factory for MetricVerifierStep with mocked dependencies."""
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
    if sources is _SENTINEL:
        sources = SourceClients(prometheus=MagicMock(), loki=MagicMock())
    defaults = {
        "llm_client": llm,
        "context": ctx,
        "status_updater": status,
        "pipeline_metadata": pipeline_metadata or {},
        "sources": sources,
    }
    defaults.update(overrides)
    step = MetricVerifierStep(**defaults)
    return step, defaults


def _prometheus_response(value):
    """Mock Prometheus query response with a single result."""
    return {
        "data": {
            "result": [
                {"value": [1234567890, str(value)]}
            ]
        }
    }


def _prometheus_empty():
    """Mock Prometheus query response with no results."""
    return {"data": {"result": []}}


def _sample_pipeline_metadata():
    """Full pipeline_metadata with sandbox results and metrics."""
    return {
        "test_plan_generated": True,
        "metrics_to_watch": [
            "kube_pod_container_status_restarts_total",
            "http_request_errors_total",
        ],
        "sandbox_executed": True,
        "sandbox_overall_status": "pass",
    }


# ── Trust Gating ─────────────────────────────────────────


class TestTrustGating:
    """Verify trust-level gating at TL3 threshold."""

    def test_tl1_skips(self):
        step, _ = _make_step(trust_level=1, pipeline_metadata=_sample_pipeline_metadata())
        result = step.execute()
        assert result.success is True
        assert result.data["verification_executed"] is False
        assert result.data["verification_skip_reason"] == "trust_level_insufficient"
        assert result.data["trust_level"] == 1

    def test_tl2_skips(self):
        step, _ = _make_step(trust_level=2, pipeline_metadata=_sample_pipeline_metadata())
        result = step.execute()
        assert result.success is True
        assert result.data["verification_executed"] is False
        assert result.data["verification_skip_reason"] == "trust_level_insufficient"

    def test_tl3_proceeds(self):
        step, _ = _make_step(trust_level=3, pipeline_metadata=_sample_pipeline_metadata())
        step.sources.prometheus.query.return_value = _prometheus_response(5.0)
        result = step.execute()
        assert result.data["verification_executed"] is True

    def test_tl4_proceeds(self):
        step, _ = _make_step(trust_level=4, pipeline_metadata=_sample_pipeline_metadata())
        step.sources.prometheus.query.return_value = _prometheus_response(5.0)
        result = step.execute()
        assert result.data["verification_executed"] is True

    def test_tl5_proceeds(self):
        step, _ = _make_step(trust_level=5, pipeline_metadata=_sample_pipeline_metadata())
        step.sources.prometheus.query.return_value = _prometheus_response(5.0)
        result = step.execute()
        assert result.data["verification_executed"] is True


# ── Prerequisite Checks ──────────────────────────────────


class TestPrerequisiteChecks:
    """Verify prerequisite validation before execution."""

    def test_no_fix_applied_skips(self):
        step, _ = _make_step(pipeline_metadata={"metrics_to_watch": ["m1"]})
        result = step.execute()
        assert result.success is True
        assert result.data["verification_executed"] is False
        assert result.data["verification_skip_reason"] == "no_fix_applied"

    def test_no_prometheus_skips(self):
        sources = SourceClients(prometheus=None, loki=MagicMock())
        step, _ = _make_step(
            pipeline_metadata=_sample_pipeline_metadata(),
            sources=sources,
        )
        result = step.execute()
        assert result.success is True
        assert result.data["verification_executed"] is False
        assert result.data["verification_skip_reason"] == "no_prometheus"

    def test_no_metrics_to_watch_skips(self):
        step, _ = _make_step(
            pipeline_metadata={"sandbox_executed": True, "metrics_to_watch": []},
        )
        result = step.execute()
        assert result.success is True
        assert result.data["verification_executed"] is False
        assert result.data["verification_skip_reason"] == "no_metrics_to_watch"

    def test_no_metrics_key_skips(self):
        step, _ = _make_step(
            pipeline_metadata={"sandbox_executed": True},
        )
        result = step.execute()
        assert result.success is True
        assert result.data["verification_skip_reason"] == "no_metrics_to_watch"

    def test_sandbox_executed_true_proceeds(self):
        step, _ = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["m1"],
        })
        step.sources.prometheus.query.return_value = _prometheus_response(5.0)
        result = step.execute()
        assert result.data["verification_executed"] is True

    def test_pr_generated_true_proceeds(self):
        step, _ = _make_step(pipeline_metadata={
            "pr_generated": True,
            "metrics_to_watch": ["m1"],
        })
        step.sources.prometheus.query.return_value = _prometheus_response(5.0)
        result = step.execute()
        assert result.data["verification_executed"] is True

    def test_no_sources_skips(self):
        step, _ = _make_step(
            pipeline_metadata=_sample_pipeline_metadata(),
            sources=None,
        )
        result = step.execute()
        assert result.data["verification_skip_reason"] == "no_prometheus"


# ── Metric Comparison ────────────────────────────────────


class TestMetricComparison:
    """Verify metric comparison logic."""

    def test_metric_improved_confirmed(self):
        """Error metric decreasing > 10% = confirmed."""
        step, _ = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["error_rate"],
        })
        # Pre-fix: 10.0, Post-fix: 2.0 → -80% → confirmed
        step.sources.prometheus.query.side_effect = [
            _prometheus_response(10.0),  # pre-fix query
            _prometheus_response(2.0),   # post-fix query
        ]
        result = step.execute()
        assert result.data["verification_status"] == "confirmed"
        assert result.data["metrics_confirmed"] == 1

    def test_metric_unchanged_inconclusive(self):
        """Change < 10% = inconclusive."""
        step, _ = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["error_rate"],
        })
        # Pre-fix: 10.0, Post-fix: 9.5 → -5% → inconclusive
        step.sources.prometheus.query.side_effect = [
            _prometheus_response(10.0),
            _prometheus_response(9.5),
        ]
        result = step.execute()
        assert result.data["verification_status"] == "inconclusive"
        assert result.data["metrics_inconclusive"] == 1

    def test_metric_degraded(self):
        """Error metric increasing > 10% = degraded."""
        step, _ = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["error_rate"],
        })
        # Pre-fix: 5.0, Post-fix: 10.0 → +100% → degraded
        step.sources.prometheus.query.side_effect = [
            _prometheus_response(5.0),
            _prometheus_response(10.0),
        ]
        result = step.execute()
        assert result.data["verification_status"] == "degraded"
        assert result.data["metrics_degraded"] == 1

    def test_prometheus_error_inconclusive(self):
        """Prometheus query failure → inconclusive."""
        step, _ = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["error_rate"],
        })
        step.sources.prometheus.query.side_effect = Exception("connection refused")
        result = step.execute()
        assert result.data["verification_status"] == "inconclusive"
        assert result.data["metrics_inconclusive"] == 1

    def test_no_data_returned_inconclusive(self):
        """No Prometheus data → inconclusive."""
        step, _ = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["error_rate"],
        })
        step.sources.prometheus.query.return_value = _prometheus_empty()
        result = step.execute()
        assert result.data["verification_status"] == "inconclusive"

    def test_pre_fix_zero_post_fix_zero_inconclusive(self):
        """Both zero → 0% change → inconclusive."""
        step, _ = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["error_rate"],
        })
        step.sources.prometheus.query.side_effect = [
            _prometheus_response(0.0),
            _prometheus_response(0.0),
        ]
        result = step.execute()
        assert result.data["verification_status"] == "inconclusive"

    def test_pre_fix_zero_post_fix_nonzero_degraded(self):
        """Pre-fix=0, post-fix>0 → 100% increase → degraded."""
        step, _ = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["error_rate"],
        })
        step.sources.prometheus.query.side_effect = [
            _prometheus_response(0.0),
            _prometheus_response(5.0),
        ]
        result = step.execute()
        assert result.data["verification_status"] == "degraded"

    def test_only_pre_fix_data_inconclusive(self):
        """Only pre-fix data available → inconclusive."""
        step, _ = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["error_rate"],
        })
        step.sources.prometheus.query.side_effect = [
            _prometheus_response(10.0),  # pre-fix
            _prometheus_empty(),          # post-fix
        ]
        result = step.execute()
        assert result.data["verification_status"] == "inconclusive"


# ── Overall Status ───────────────────────────────────────


class TestOverallStatus:
    """Verify overall status determination from individual results."""

    def test_all_confirmed(self):
        results = [
            VerificationResult("m1", 10.0, 1.0, "confirmed", -90.0, None),
            VerificationResult("m2", 20.0, 5.0, "confirmed", -75.0, None),
        ]
        assert MetricVerifierStep._determine_overall_status(results) == "confirmed"

    def test_any_degraded(self):
        results = [
            VerificationResult("m1", 10.0, 1.0, "confirmed", -90.0, None),
            VerificationResult("m2", 5.0, 15.0, "degraded", 200.0, None),
        ]
        assert MetricVerifierStep._determine_overall_status(results) == "degraded"

    def test_mix_confirmed_inconclusive(self):
        results = [
            VerificationResult("m1", 10.0, 1.0, "confirmed", -90.0, None),
            VerificationResult("m2", 10.0, 9.5, "inconclusive", -5.0, None),
        ]
        assert MetricVerifierStep._determine_overall_status(results) == "inconclusive"

    def test_all_inconclusive(self):
        results = [
            VerificationResult("m1", 10.0, 9.5, "inconclusive", -5.0, None),
            VerificationResult("m2", None, None, "inconclusive", None, "error"),
        ]
        assert MetricVerifierStep._determine_overall_status(results) == "inconclusive"

    def test_empty_results(self):
        assert MetricVerifierStep._determine_overall_status([]) == "inconclusive"


# ── Degradation Handling ─────────────────────────────────


class TestDegradationHandling:
    """Verify behavior when metrics show degradation."""

    def test_degraded_triggers_status_update(self):
        step, defaults = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["error_rate"],
        })
        step.sources.prometheus.query.side_effect = [
            _prometheus_response(5.0),
            _prometheus_response(15.0),
        ]
        step.execute()
        # Check status_updater was called with degradation message
        status = defaults["status_updater"]
        calls = [str(c) for c in status.update_message.call_args_list]
        assert any("DEGRADATION DETECTED" in c for c in calls)

    def test_degraded_sets_rollback_recommended(self):
        step, _ = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["error_rate"],
        })
        step.sources.prometheus.query.side_effect = [
            _prometheus_response(5.0),
            _prometheus_response(15.0),
        ]
        result = step.execute()
        assert result.data["rollback_recommended"] is True

    def test_degraded_includes_comparison(self):
        step, _ = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["error_rate"],
        })
        step.sources.prometheus.query.side_effect = [
            _prometheus_response(5.0),
            _prometheus_response(15.0),
        ]
        result = step.execute()
        vr = result.data["verification_results"]
        assert len(vr) == 1
        assert vr[0]["pre_fix_value"] is not None
        assert vr[0]["post_fix_value"] is not None
        assert vr[0]["delta_pct"] is not None


# ── Confirmed Handling ───────────────────────────────────


class TestConfirmedHandling:
    """Verify behavior when metrics confirm resolution."""

    def test_confirmed_sets_fix_verified(self):
        step, _ = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["error_rate"],
        })
        step.sources.prometheus.query.side_effect = [
            _prometheus_response(10.0),
            _prometheus_response(1.0),
        ]
        result = step.execute()
        assert result.data["fix_verified"] is True

    def test_confirmed_sets_fix_proven(self):
        step, _ = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["error_rate"],
        })
        step.sources.prometheus.query.side_effect = [
            _prometheus_response(10.0),
            _prometheus_response(1.0),
        ]
        result = step.execute()
        assert result.data["fix_proven"] is True

    def test_confirmed_sets_verification_status(self):
        step, _ = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["error_rate"],
        })
        step.sources.prometheus.query.side_effect = [
            _prometheus_response(10.0),
            _prometheus_response(1.0),
        ]
        result = step.execute()
        assert result.data["verification_status"] == "confirmed"

    def test_confirmed_calls_status_updater(self):
        step, defaults = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["error_rate"],
        })
        step.sources.prometheus.query.side_effect = [
            _prometheus_response(10.0),
            _prometheus_response(1.0),
        ]
        step.execute()
        status = defaults["status_updater"]
        calls = [str(c) for c in status.update_message.call_args_list]
        assert any("Fix verified" in c for c in calls)

    def test_inconclusive_does_not_set_fix_proven(self):
        step, _ = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["error_rate"],
        })
        step.sources.prometheus.query.side_effect = [
            _prometheus_response(10.0),
            _prometheus_response(9.5),
        ]
        result = step.execute()
        assert result.data["fix_verified"] is False
        assert result.data["fix_proven"] is False
        assert result.data["rollback_recommended"] is False


# ── Verification Window ──────────────────────────────────


class TestVerificationWindow:
    """Verify configurable verification window."""

    def test_default_window_15_minutes(self):
        step, _ = _make_step(pipeline_metadata=_sample_pipeline_metadata())
        assert step._verification_window_minutes == 15

    @patch.dict("os.environ", {"VERIFICATION_WINDOW_MINUTES": "30"})
    def test_custom_window_from_env(self):
        step, _ = _make_step(pipeline_metadata=_sample_pipeline_metadata())
        assert step._verification_window_minutes == 30

    @patch.dict("os.environ", {"VERIFICATION_WINDOW_MINUTES": "invalid"})
    def test_invalid_window_defaults_to_15(self):
        step, _ = _make_step(pipeline_metadata=_sample_pipeline_metadata())
        assert step._verification_window_minutes == 15

    @patch.dict("os.environ", {"VERIFICATION_WINDOW_MINUTES": "0"})
    def test_zero_window_clamped_to_1(self):
        step, _ = _make_step(pipeline_metadata=_sample_pipeline_metadata())
        assert step._verification_window_minutes == 1

    def test_window_used_in_result_data(self):
        step, _ = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["m1"],
        })
        step.sources.prometheus.query.return_value = _prometheus_response(5.0)
        result = step.execute()
        assert result.data["verification_window_minutes"] == 15


# ── Evidence Attachment ──────────────────────────────────


class TestEvidenceAttachment:
    """Verify result data structure for downstream consumption."""

    def test_result_has_all_required_keys(self):
        step, _ = _make_step(pipeline_metadata=_sample_pipeline_metadata())
        step.sources.prometheus.query.return_value = _prometheus_response(5.0)
        result = step.execute()
        required_keys = {
            "verification_executed",
            "verification_status",
            "verification_window_minutes",
            "metrics_compared",
            "metrics_confirmed",
            "metrics_degraded",
            "metrics_inconclusive",
            "verification_results",
            "fix_verified",
            "fix_proven",
            "rollback_recommended",
            "verification_model_tier",
        }
        assert required_keys.issubset(set(result.data.keys()))

    def test_verification_results_is_list_of_dicts(self):
        step, _ = _make_step(pipeline_metadata=_sample_pipeline_metadata())
        step.sources.prometheus.query.return_value = _prometheus_response(5.0)
        result = step.execute()
        vr = result.data["verification_results"]
        assert isinstance(vr, list)
        assert len(vr) == 2
        for item in vr:
            assert isinstance(item, dict)
            assert "metric" in item
            assert "status" in item

    def test_verification_model_tier(self):
        step, _ = _make_step(pipeline_metadata=_sample_pipeline_metadata())
        step.sources.prometheus.query.return_value = _prometheus_response(5.0)
        result = step.execute()
        assert result.data["verification_model_tier"] == "remediation"

    def test_multiple_metrics_counted(self):
        step, _ = _make_step(pipeline_metadata=_sample_pipeline_metadata())
        step.sources.prometheus.query.return_value = _prometheus_response(5.0)
        result = step.execute()
        assert result.data["metrics_compared"] == 2


# ── Step Metadata ────────────────────────────────────────


class TestStepName:
    def test_step_name(self):
        step, _ = _make_step()
        assert step.name == "Post-Fix Metric Verification"


class TestProtocolCompliance:
    def test_implements_investigation_step(self):
        step, _ = _make_step()
        assert isinstance(step, InvestigationStep)


class TestNonFatalResults:
    """Verify all results return success=True (non-fatal)."""

    def test_skip_result_is_non_fatal(self):
        step, _ = _make_step(trust_level=1)
        result = step.execute()
        assert result.success is True

    def test_degraded_result_is_non_fatal(self):
        step, _ = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["error_rate"],
        })
        step.sources.prometheus.query.side_effect = [
            _prometheus_response(5.0),
            _prometheus_response(15.0),
        ]
        result = step.execute()
        assert result.success is True

    def test_confirmed_result_is_non_fatal(self):
        step, _ = _make_step(pipeline_metadata={
            "sandbox_executed": True,
            "metrics_to_watch": ["error_rate"],
        })
        step.sources.prometheus.query.side_effect = [
            _prometheus_response(10.0),
            _prometheus_response(1.0),
        ]
        result = step.execute()
        assert result.success is True
