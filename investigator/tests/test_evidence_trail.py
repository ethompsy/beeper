"""Tests for evidence_trail.py — PR body and commit message formatting."""

from beeper_investigator.context import InvestigationContext
from beeper_investigator.remediation.evidence_trail import EvidenceTrailFormatter


def _make_context(**overrides):
    defaults = {
        "investigation_id": "inv-abc123",
        "namespace": "default",
        "condition": "high_error_rate",
        "service": "payments",
        "severity": "high",
        "trust_level": 3,
        "confidence_threshold": 0.9,
    }
    defaults.update(overrides)
    return InvestigationContext(**defaults)


def _full_metadata():
    return {
        "root_cause_hypothesis": "Memory leak in connection pool",
        "confidence_level": "high",
        "confidence_percentage": 85,
        "supporting_evidence": [
            "Pod restarts correlate with memory growth",
            "Connection count exceeds pool max",
        ],
        "customer_impacting": True,
        "signal_summary": "Error rate spiked 5x in the last 30 minutes",
        "layers_queried": ["prometheus", "loki"],
        "test_plan_generated": True,
        "verification_steps": [
            {
                "step_number": 1,
                "title": "Check memory utilization",
                "action": "PromQL: container_memory_working_set_bytes",
            },
            {
                "step_number": 2,
                "title": "Verify connection pool size",
                "action": "Check connection pool metrics",
            },
        ],
    }


# ── FormatPRBody ─────────────────────────────────────────


class TestFormatPRBody:
    def test_all_sections_present(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        body = fmt.format_pr_body(ctx, _full_metadata(), "Fix connection pool leak")

        assert "## Beeper Auto-Fix: payments — high_error_rate" in body
        assert "### Investigation Summary" in body
        assert "### Root Cause Analysis" in body
        assert "### Log Correlation Evidence" in body
        assert "### Production Conditions" in body
        assert "### Advisory Test Plan" in body
        assert "### Audit Trail" in body

    def test_investigation_context_correct(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        body = fmt.format_pr_body(ctx, _full_metadata(), "Fix")

        assert "inv-abc123" in body
        assert "payments" in body
        assert "high_error_rate" in body
        assert "high" in body
        assert "default" in body

    def test_rca_hypothesis_included(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        body = fmt.format_pr_body(ctx, _full_metadata(), "Fix")

        assert "Memory leak in connection pool" in body
        assert "high (85%)" in body
        assert "Pod restarts correlate with memory growth" in body

    def test_test_plan_steps_included(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        body = fmt.format_pr_body(ctx, _full_metadata(), "Fix")

        assert "Check memory utilization" in body
        assert "Verify connection pool size" in body

    def test_audit_trail_chain(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        body = fmt.format_pr_body(ctx, _full_metadata(), "Fix")

        assert "anomaly (high_error_rate)" in body
        assert "investigation (inv-abc123)" in body
        assert "fix (this PR)" in body
        assert "verification (pending)" in body

    def test_missing_optional_fields_handled(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        minimal_metadata = {"customer_impacting": False}
        body = fmt.format_pr_body(ctx, minimal_metadata, "Fix")

        # Should not crash; core sections should still be present
        assert "### Investigation Summary" in body
        assert "### Production Conditions" in body
        # No RCA or test plan sections if data is missing
        assert "### Root Cause Analysis" not in body
        assert "### Advisory Test Plan" not in body

    def test_no_test_plan_when_not_generated(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        metadata = _full_metadata()
        metadata["test_plan_generated"] = False
        body = fmt.format_pr_body(ctx, metadata, "Fix")

        assert "### Advisory Test Plan" not in body

    def test_fix_description_in_body(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        body = fmt.format_pr_body(ctx, _full_metadata(), "Increase pool max connections")

        assert "Increase pool max connections" in body

    def test_non_dict_verification_steps_skipped(self, caplog):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        metadata = _full_metadata()
        metadata["verification_steps"] = [
            "not a dict",
            {"step_number": 1, "title": "Valid", "action": "do it"},
        ]
        body = fmt.format_pr_body(ctx, metadata, "Fix")

        assert "Valid" in body
        assert "Skipping non-dict verification step" in caplog.text


# ── FormatCommitMessage ──────────────────────────────────


class TestFormatCommitMessage:
    def test_format_correct(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        msg = fmt.format_commit_message(ctx, "Fix connection pool leak")

        assert msg.startswith("fix(payments):")
        assert "Fix connection pool leak" in msg
        assert "Investigation: inv-abc123" in msg

    def test_service_and_id_included(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context(service="orders", investigation_id="inv-xyz")
        msg = fmt.format_commit_message(ctx, "Fix timeout")

        assert "fix(orders):" in msg
        assert "Investigation: inv-xyz" in msg

    def test_long_description_truncated(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        long_desc = "A" * 200
        msg = fmt.format_commit_message(ctx, long_desc)

        first_line = msg.split("\n")[0]
        # fix(payments): + 72 chars max
        assert len(first_line) <= 100

    def test_condition_and_severity_included(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context(condition="oom_kill", severity="critical")
        msg = fmt.format_commit_message(ctx, "Fix OOM")

        assert "Condition: oom_kill" in msg
        assert "Severity: critical" in msg


# ── Sandbox Results Section ─────────────────────────────


class TestSandboxResultsSection:
    def test_sandbox_executed_renders_table(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        metadata = _full_metadata()
        metadata["sandbox_executed"] = True
        metadata["sandbox_overall_status"] = "pass"
        metadata["sandbox_namespace"] = "beeper-sandbox"
        metadata["sandbox_test_results"] = [
            {
                "step_number": 1,
                "title": "Check memory",
                "status": "pass",
                "expected_outcome": "Memory < 512MB",
                "actual_value": "256MB",
                "duration_seconds": 2.5,
            },
        ]
        body = fmt.format_pr_body(ctx, metadata, "Fix")

        assert "### Sandbox Test Results" in body
        assert "PASS" in body
        assert "beeper-sandbox" in body
        assert "Check memory" in body

    def test_sandbox_not_executed_shows_skip_reason(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        metadata = _full_metadata()
        metadata["sandbox_executed"] = False
        metadata["skip_reason"] = "no_sandbox_configured"
        body = fmt.format_pr_body(ctx, metadata, "Fix")

        assert "### Sandbox Test Results" in body
        assert "Skipped: no_sandbox_configured" in body

    def test_no_sandbox_data_gracefully_omitted(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        metadata = _full_metadata()
        # No sandbox_executed key at all
        body = fmt.format_pr_body(ctx, metadata, "Fix")

        assert "### Sandbox Test Results" not in body

    def test_sandbox_results_in_audit_trail(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        metadata = _full_metadata()
        metadata["sandbox_executed"] = True
        metadata["sandbox_overall_status"] = "pass"
        metadata["sandbox_namespace"] = "beeper-sandbox"
        metadata["sandbox_test_results"] = []
        body = fmt.format_pr_body(ctx, metadata, "Fix")

        # Without verification_executed, audit trail uses sandbox status
        assert "verification (pass)" in body

    def test_audit_trail_pending_when_no_sandbox(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        metadata = _full_metadata()
        body = fmt.format_pr_body(ctx, metadata, "Fix")

        assert "verification (pending)" in body

    def test_non_dict_sandbox_results_skipped(self, caplog):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        metadata = _full_metadata()
        metadata["sandbox_executed"] = True
        metadata["sandbox_overall_status"] = "pass"
        metadata["sandbox_namespace"] = "beeper-sandbox"
        metadata["sandbox_test_results"] = [
            "not a dict",
            {
                "step_number": 1,
                "title": "Valid",
                "status": "pass",
                "expected_outcome": "ok",
                "actual_value": "ok",
                "duration_seconds": 1.0,
            },
        ]
        body = fmt.format_pr_body(ctx, metadata, "Fix")

        assert "Valid" in body
        assert "Skipping non-dict sandbox result" in caplog.text


# ── Verification Results Section ──────────────────────────


class TestVerificationResultsSection:
    def test_verification_executed_renders_table(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        metadata = _full_metadata()
        metadata["verification_executed"] = True
        metadata["verification_status"] = "confirmed"
        metadata["verification_window_minutes"] = 15
        metadata["verification_results"] = [
            {
                "metric": "kube_pod_container_status_restarts_total",
                "pre_fix_value": 10.0,
                "post_fix_value": 0.0,
                "status": "confirmed",
                "delta_pct": -100.0,
                "error_message": None,
            },
        ]
        body = fmt.format_pr_body(ctx, metadata, "Fix")

        assert "### Post-Fix Verification" in body
        assert "CONFIRMED" in body
        assert "15min" in body
        assert "kube_pod_container_status_restarts_total" in body

    def test_verification_degraded_shows_rollback_warning(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        metadata = _full_metadata()
        metadata["verification_executed"] = True
        metadata["verification_status"] = "degraded"
        metadata["verification_window_minutes"] = 15
        metadata["verification_results"] = [
            {
                "metric": "error_rate",
                "pre_fix_value": 5.0,
                "post_fix_value": 15.0,
                "status": "degraded",
                "delta_pct": 200.0,
                "error_message": None,
            },
        ]
        body = fmt.format_pr_body(ctx, metadata, "Fix")

        assert "### Post-Fix Verification" in body
        assert "DEGRADED" in body
        assert "ROLLBACK RECOMMENDED" in body

    def test_verification_confirmed_in_audit_trail(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        metadata = _full_metadata()
        metadata["verification_executed"] = True
        metadata["verification_status"] = "confirmed"
        metadata["verification_window_minutes"] = 15
        metadata["verification_results"] = []
        body = fmt.format_pr_body(ctx, metadata, "Fix")

        assert "verification (confirmed)" in body

    def test_verification_not_executed_shows_skip_reason(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        metadata = _full_metadata()
        metadata["verification_executed"] = False
        metadata["verification_skip_reason"] = "no_prometheus"
        body = fmt.format_pr_body(ctx, metadata, "Fix")

        assert "### Post-Fix Verification" in body
        assert "Skipped: no_prometheus" in body

    def test_no_verification_data_gracefully_omitted(self):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        metadata = _full_metadata()
        # No verification_executed key at all
        body = fmt.format_pr_body(ctx, metadata, "Fix")

        assert "### Post-Fix Verification" not in body

    def test_verification_skip_reason_not_confused_with_sandbox_skip_reason(self):
        """Verify namespaced skip_reason keys prevent cross-step contamination."""
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        metadata = _full_metadata()
        metadata["sandbox_executed"] = False
        metadata["skip_reason"] = "no_sandbox_configured"
        metadata["verification_executed"] = False
        metadata["verification_skip_reason"] = "no_prometheus"
        body = fmt.format_pr_body(ctx, metadata, "Fix")

        assert "Skipped: no_sandbox_configured" in body
        assert "Skipped: no_prometheus" in body

    def test_non_dict_verification_results_skipped(self, caplog):
        fmt = EvidenceTrailFormatter()
        ctx = _make_context()
        metadata = _full_metadata()
        metadata["verification_executed"] = True
        metadata["verification_status"] = "confirmed"
        metadata["verification_window_minutes"] = 15
        metadata["verification_results"] = [
            "not a dict",
            {
                "metric": "valid_metric",
                "pre_fix_value": 10.0,
                "post_fix_value": 1.0,
                "status": "confirmed",
                "delta_pct": -90.0,
                "error_message": None,
            },
        ]
        body = fmt.format_pr_body(ctx, metadata, "Fix")

        assert "valid_metric" in body
        assert "Skipping non-dict verification result" in caplog.text
