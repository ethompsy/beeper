"""Tests for remediation progress tracking (Story 7-3)."""

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from flask.testing import FlaskClient

from beeper_ui.services.investigation_service import (
    Investigation,
    InvestigationDetail,
    InvestigationService,
    compute_remediation_status,
)


# --- compute_remediation_status tests ---


class TestComputeRemediationStatus:
    """Test compute_remediation_status() with various pipeline_metadata combinations."""

    def test_returns_none_for_empty_findings(self) -> None:
        assert compute_remediation_status({}) is None

    def test_returns_none_for_no_remediation_keys(self) -> None:
        findings = {"recommendations": "some text", "root_cause": "memory leak"}
        assert compute_remediation_status(findings) is None

    def test_pr_generated_draft_returns_proposed(self) -> None:
        findings = {"pr_generated": True, "draft": True, "pr_url": "https://github.com/org/repo/pull/42"}
        result = compute_remediation_status(findings)
        assert result is not None
        assert result["stage"] == "proposed"
        assert result["label"] == "PR Open"
        assert result["pr_url"] == "https://github.com/org/repo/pull/42"

    def test_pr_generated_not_draft_returns_approved(self) -> None:
        findings = {"pr_generated": True, "draft": False, "pr_url": "https://github.com/org/repo/pull/42"}
        result = compute_remediation_status(findings)
        assert result is not None
        assert result["stage"] == "approved"
        assert result["label"] == "PR Approved"

    def test_sandbox_executed_returns_testing(self) -> None:
        findings = {
            "pr_generated": True,
            "draft": False,
            "sandbox_executed": True,
            "sandbox_overall_status": "pass",
        }
        result = compute_remediation_status(findings)
        assert result is not None
        assert result["stage"] == "testing"
        assert result["label"] == "Sandbox Testing"

    def test_trust_gate_evaluated_returns_applied(self) -> None:
        findings = {
            "pr_generated": True,
            "sandbox_executed": True,
            "trust_gate_evaluated": True,
            "trust_gate_decisions": [],
        }
        result = compute_remediation_status(findings)
        assert result is not None
        assert result["stage"] == "applied"
        assert result["label"] == "Fix Applied"

    def test_verification_pending_returns_verifying(self) -> None:
        findings = {
            "pr_generated": True,
            "sandbox_executed": True,
            "trust_gate_evaluated": True,
            "verification_executed": True,
            "verification_status": "pending",
        }
        result = compute_remediation_status(findings)
        assert result is not None
        assert result["stage"] == "verifying"
        assert result["label"] == "Verifying"

    def test_verification_confirmed_returns_verified(self) -> None:
        findings = {
            "pr_generated": True,
            "sandbox_executed": True,
            "trust_gate_evaluated": True,
            "verification_executed": True,
            "verification_status": "confirmed",
            "fix_verified": True,
        }
        result = compute_remediation_status(findings)
        assert result is not None
        assert result["stage"] == "verified"
        assert result["label"] == "Verified"

    def test_verification_degraded_returns_rolled_back(self) -> None:
        findings = {
            "pr_generated": True,
            "sandbox_executed": True,
            "trust_gate_evaluated": True,
            "verification_executed": True,
            "verification_status": "degraded",
            "trust_gate_rollback_paths": [{"reason": "CPU usage increased 40%"}],
            "verification_results": [
                {"metric": "cpu_usage", "pre_value": "20%", "post_value": "60%", "delta": "+40%", "status": "degraded"},
            ],
        }
        result = compute_remediation_status(findings)
        assert result is not None
        assert result["stage"] == "rolled_back"
        assert result["label"] == "Rolled Back"
        assert result["rollback_reason"] == "CPU usage increased 40%"
        assert result["verification_results"] is not None
        assert len(result["verification_results"]) == 1

    def test_rollback_with_no_paths_gets_default_reason(self) -> None:
        findings = {
            "verification_executed": True,
            "verification_status": "degraded",
        }
        result = compute_remediation_status(findings)
        assert result is not None
        assert result["stage"] == "rolled_back"
        assert result["rollback_reason"] == "Metric degradation detected"

    def test_sandbox_failure_returns_failed(self) -> None:
        findings = {
            "pr_generated": True,
            "draft": False,
            "sandbox_executed": True,
            "sandbox_overall_status": "fail",
        }
        result = compute_remediation_status(findings)
        assert result is not None
        assert result["stage"] == "failed"
        assert result["label"] == "Failed"

    def test_sandbox_pass_returns_testing(self) -> None:
        findings = {
            "pr_generated": True,
            "draft": False,
            "sandbox_executed": True,
            "sandbox_overall_status": "pass",
        }
        result = compute_remediation_status(findings)
        assert result is not None
        assert result["stage"] == "testing"

    def test_runbook_found_only_returns_proposed(self) -> None:
        findings = {"runbook_found": True, "runbook_steps_executed": 3}
        result = compute_remediation_status(findings)
        assert result is not None
        assert result["stage"] == "proposed"

    def test_stages_completed_list_populated(self) -> None:
        findings = {"pr_generated": True, "draft": False, "sandbox_executed": True}
        result = compute_remediation_status(findings)
        assert result is not None
        stages = result["stages_completed"]
        assert len(stages) == 6
        # proposed and approved should be completed
        assert stages[0]["name"] == "proposed"
        assert stages[0]["status"] == "completed"
        assert stages[1]["name"] == "approved"
        assert stages[1]["status"] == "completed"
        assert stages[2]["name"] == "testing"
        assert stages[2]["status"] == "completed"

    def test_full_pipeline_returns_verified(self) -> None:
        findings = {
            "runbook_found": True,
            "runbook_steps_executed": 3,
            "pr_generated": True,
            "draft": False,
            "pr_url": "https://github.com/pr/1",
            "sandbox_executed": True,
            "sandbox_overall_status": "pass",
            "trust_gate_evaluated": True,
            "verification_executed": True,
            "verification_status": "confirmed",
            "fix_verified": True,
            "kb_entry_created": True,
            "proven_fix_entry_id": "kb-123",
        }
        result = compute_remediation_status(findings)
        assert result is not None
        assert result["stage"] == "verified"
        assert result["pr_url"] == "https://github.com/pr/1"
        assert result["proven_fix_entry_id"] == "kb-123"

    def test_proven_fix_entry_id_passed_through(self) -> None:
        findings = {"kb_entry_created": True, "proven_fix_entry_id": "kb-abc"}
        result = compute_remediation_status(findings)
        assert result is not None
        assert result["proven_fix_entry_id"] == "kb-abc"


# --- get_remediation_progress tests ---


class TestGetRemediationProgress:
    """Test InvestigationService.get_remediation_progress() method."""

    def test_returns_none_when_no_findings(self) -> None:
        svc = InvestigationService(operator_url="http://localhost:8080")
        with patch.object(svc, "get_investigation_findings", return_value={}):
            result = svc.get_remediation_progress("test-inv-1")
        assert result is None

    def test_returns_dict_with_all_fields(self) -> None:
        svc = InvestigationService(operator_url="http://localhost:8080")
        findings = {"pr_generated": True, "draft": True, "pr_url": "https://pr/1"}
        with patch.object(svc, "get_investigation_findings", return_value=findings):
            result = svc.get_remediation_progress("test-inv-1")
        assert result is not None
        assert "stage" in result
        assert "label" in result
        assert "stages_completed" in result
        assert "pr_url" in result
        assert "rollback_reason" in result
        assert "verification_results" in result


# --- Investigation dataclass remediation_status field tests ---


class TestRemediationStatusField:
    """Test that Investigation dataclass has remediation_status field."""

    def test_investigation_has_remediation_status_field(self) -> None:
        inv = Investigation(
            id="test-1", status="investigating", service="payments",
            severity="high", condition="High error rate",
            remediation_status={"stage": "testing", "label": "Sandbox Testing"},
        )
        assert inv.remediation_status is not None
        assert inv.remediation_status["stage"] == "testing"

    def test_remediation_status_defaults_to_none(self) -> None:
        inv = Investigation(
            id="test-1", status="investigating", service="payments",
            severity="high", condition="High error rate",
        )
        assert inv.remediation_status is None

    def test_detail_has_remediation_status_field(self) -> None:
        detail = InvestigationDetail(
            id="test-1", status="investigating", service="payments",
            severity="high", condition="High error rate",
            remediation_status={"stage": "verified"},
        )
        assert detail.remediation_status is not None


# --- Template rendering tests ---


def _read_static(filename: str) -> str:
    """Read a static file from the beeper_ui package."""
    import importlib.resources as resources
    from pathlib import Path

    static_dir = Path(__file__).parent.parent / "beeper_ui" / "templates" / "investigations"
    return (static_dir / filename).read_text()


@pytest.fixture
def remediation_progress_html() -> str:
    return _read_static("_remediation_progress.html")


class TestRemediationProgressTemplate:
    """Test _remediation_progress.html template rendering."""

    def test_template_exists(self, remediation_progress_html: str) -> None:
        assert "remediation-timeline" in remediation_progress_html

    def test_template_has_all_stages(self, remediation_progress_html: str) -> None:
        assert "Proposed" in remediation_progress_html
        assert "Approved" in remediation_progress_html
        assert "Testing" in remediation_progress_html
        assert "Applied" in remediation_progress_html
        assert "Verifying" in remediation_progress_html
        assert "Verified" in remediation_progress_html

    def test_template_has_empty_state(self, remediation_progress_html: str) -> None:
        assert "No remediation actions" in remediation_progress_html

    def test_template_has_rollback_section(self, remediation_progress_html: str) -> None:
        assert "rollback-details" in remediation_progress_html
        assert "metric-comparison-table" in remediation_progress_html

    def test_template_has_pr_link(self, remediation_progress_html: str) -> None:
        assert "View PR" in remediation_progress_html

    def test_template_has_kb_link(self, remediation_progress_html: str) -> None:
        assert "View KB Entry" in remediation_progress_html


# --- Route tests ---


class TestRemediationProgressRoute:
    """Test the /investigations/<id>/remediation-progress HTMX partial route."""

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_route_returns_200(self, mock_get_svc: MagicMock, client: FlaskClient) -> None:
        mock_svc = MagicMock(spec=InvestigationService)
        mock_svc.get_remediation_progress.return_value = {
            "stage": "testing",
            "label": "Sandbox Testing",
            "stages_completed": [
                {"name": "proposed", "status": "completed"},
                {"name": "approved", "status": "completed"},
                {"name": "testing", "status": "completed"},
                {"name": "applied", "status": "pending"},
                {"name": "verifying", "status": "pending"},
                {"name": "verified", "status": "pending"},
            ],
            "pr_url": "https://github.com/pr/1",
            "rollback_reason": None,
            "verification_results": None,
            "proven_fix_entry_id": None,
        }
        mock_get_svc.return_value = mock_svc
        resp = client.get("/investigations/test-inv-1/remediation-progress")
        assert resp.status_code == 200
        assert b"remediation-timeline" in resp.data

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_route_shows_empty_state(self, mock_get_svc: MagicMock, client: FlaskClient) -> None:
        mock_svc = MagicMock(spec=InvestigationService)
        mock_svc.get_remediation_progress.return_value = None
        mock_get_svc.return_value = mock_svc
        resp = client.get("/investigations/test-inv-1/remediation-progress")
        assert resp.status_code == 200
        assert b"No remediation actions" in resp.data

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_route_shows_rollback_details(self, mock_get_svc: MagicMock, client: FlaskClient) -> None:
        mock_svc = MagicMock(spec=InvestigationService)
        mock_svc.get_remediation_progress.return_value = {
            "stage": "rolled_back",
            "label": "Rolled Back",
            "stages_completed": [
                {"name": "proposed", "status": "completed"},
                {"name": "approved", "status": "completed"},
                {"name": "testing", "status": "completed"},
                {"name": "applied", "status": "completed"},
                {"name": "verifying", "status": "completed"},
                {"name": "verified", "status": "pending"},
            ],
            "pr_url": None,
            "rollback_reason": "CPU usage increased 40%",
            "verification_results": [
                {"metric": "cpu_usage", "pre_value": "20%", "post_value": "60%", "delta": "+40%", "status": "degraded"},
            ],
            "proven_fix_entry_id": None,
        }
        mock_get_svc.return_value = mock_svc
        resp = client.get("/investigations/test-inv-1/remediation-progress")
        assert resp.status_code == 200
        assert b"rollback-details" in resp.data
        assert b"CPU usage increased 40%" in resp.data
        assert b"metric-comparison-table" in resp.data

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_route_shows_pr_link(self, mock_get_svc: MagicMock, client: FlaskClient) -> None:
        mock_svc = MagicMock(spec=InvestigationService)
        mock_svc.get_remediation_progress.return_value = {
            "stage": "proposed",
            "label": "PR Open",
            "stages_completed": [{"name": "proposed", "status": "completed"}] + [
                {"name": s, "status": "pending"} for s in ("approved", "testing", "applied", "verifying", "verified")
            ],
            "pr_url": "https://github.com/org/repo/pull/99",
            "rollback_reason": None,
            "verification_results": None,
            "proven_fix_entry_id": None,
        }
        mock_get_svc.return_value = mock_svc
        resp = client.get("/investigations/test-inv-1/remediation-progress")
        assert resp.status_code == 200
        assert b"View PR" in resp.data
        assert b"https://github.com/org/repo/pull/99" in resp.data

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_route_shows_kb_link(self, mock_get_svc: MagicMock, client: FlaskClient) -> None:
        mock_svc = MagicMock(spec=InvestigationService)
        mock_svc.get_remediation_progress.return_value = {
            "stage": "verified",
            "label": "Verified",
            "stages_completed": [
                {"name": s, "status": "completed"} for s in ("proposed", "approved", "testing", "applied", "verifying", "verified")
            ],
            "pr_url": None,
            "rollback_reason": None,
            "verification_results": None,
            "proven_fix_entry_id": "kb-fix-123",
        }
        mock_get_svc.return_value = mock_svc
        resp = client.get("/investigations/test-inv-1/remediation-progress")
        assert resp.status_code == 200
        assert b"View KB Entry" in resp.data
        assert b"/knowledge/kb-fix-123" in resp.data


# --- List view tests ---


class TestRemediationBadgeInList:
    """Test remediation badge in investigation list view."""

    def test_list_content_template_has_remediation_column(self) -> None:
        html = _read_static("_list_content.html")
        assert "Remediation" in html
        assert "remediation-badge" in html

    def test_list_content_template_has_em_dash_fallback(self) -> None:
        html = _read_static("_list_content.html")
        assert "mdash" in html  # &mdash; for no remediation


# --- Detail page integration tests ---


class TestRemediationInDetailPage:
    """Test remediation progress card in investigation detail page."""

    def test_detail_template_has_remediation_section(self) -> None:
        html = _read_static("_detail_content.html")
        assert "Remediation Progress" in html
        assert "remediation-progress" in html
        assert "remediation-update" in html


# --- SSE tests ---


class TestRemediationSSEEvent:
    """Test SSE remediation-update event generation."""

    def test_sse_generator_references_remediation_update(self) -> None:
        """Verify the SSE generator code contains remediation-update event."""
        from pathlib import Path

        route_file = Path(__file__).parent.parent / "beeper_ui" / "routes" / "investigations.py"
        code = route_file.read_text()
        assert "remediation-update" in code
        assert "compute_remediation_status" in code
        assert "_remediation_progress.html" in code

    def test_compute_remediation_status_stage_change_detection(self) -> None:
        """Verify that SSE filtering works: same stage should not trigger re-emit."""
        # Simulate two findings snapshots with same remediation stage but different non-remediation keys
        findings_v1 = {"pr_generated": True, "draft": True, "root_cause": "memory leak"}
        findings_v2 = {"pr_generated": True, "draft": True, "root_cause": "updated cause", "recommendations": "fix it"}
        status_v1 = compute_remediation_status(findings_v1)
        status_v2 = compute_remediation_status(findings_v2)
        assert status_v1 is not None
        assert status_v2 is not None
        # Both should be "proposed" — SSE should NOT re-emit
        assert status_v1["stage"] == status_v2["stage"] == "proposed"

        # Now a real stage change
        findings_v3 = {**findings_v2, "sandbox_executed": True, "sandbox_overall_status": "pass"}
        status_v3 = compute_remediation_status(findings_v3)
        assert status_v3 is not None
        assert status_v3["stage"] == "testing"
        # Different stage — SSE SHOULD emit
        assert status_v3["stage"] != status_v2["stage"]
