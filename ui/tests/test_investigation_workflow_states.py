"""Tests for investigation workflow states (Story 7-2)."""

from unittest.mock import MagicMock, patch

from flask.testing import FlaskClient

from beeper_ui.services.investigation_service import Investigation, InvestigationDetail

# --- Investigation dataclass tests ---


class TestInvestigationWorkflowStateFields:
    """Test that Investigation and InvestigationDetail include workflow_state fields."""

    def test_investigation_has_workflow_state_field(self) -> None:
        inv = Investigation(
            id="test-1",
            status="investigating",
            service="payments",
            severity="high",
            condition="High error rate",
            workflow_state="detected",
            workflow_state_changed_at="2026-03-18T10:00:00Z",
        )
        assert inv.workflow_state == "detected"
        assert inv.workflow_state_changed_at == "2026-03-18T10:00:00Z"

    def test_investigation_workflow_state_defaults_to_none(self) -> None:
        inv = Investigation(
            id="test-1",
            status="investigating",
            service="payments",
            severity="high",
            condition="High error rate",
        )
        assert inv.workflow_state is None
        assert inv.workflow_state_changed_at is None

    def test_investigation_from_dict_with_workflow_state(self) -> None:
        data = {
            "id": "test-1",
            "status": "investigating",
            "service": "payments",
            "severity": "high",
            "condition": "High error rate",
            "workflow_state": "investigating",
            "workflow_state_changed_at": "2026-03-18T10:00:00Z",
        }
        inv = Investigation.from_dict(data)
        assert inv.workflow_state == "investigating"
        assert inv.workflow_state_changed_at == "2026-03-18T10:00:00Z"

    def test_investigation_from_dict_without_workflow_state(self) -> None:
        data = {
            "id": "test-1",
            "status": "investigating",
            "service": "payments",
            "severity": "high",
            "condition": "High error rate",
        }
        inv = Investigation.from_dict(data)
        assert inv.workflow_state is None
        assert inv.workflow_state_changed_at is None

    def test_investigation_detail_from_dict_with_workflow_state(self) -> None:
        data = {
            "id": "test-1",
            "status": "completed",
            "service": "payments",
            "severity": "high",
            "condition": "High error rate",
            "message": "Resolved",
            "error": None,
            "job_name": "inv-test-1",
            "workflow_state": "resolved",
            "workflow_state_changed_at": "2026-03-18T11:00:00Z",
        }
        detail = InvestigationDetail.from_dict(data)
        assert detail.workflow_state == "resolved"
        assert detail.workflow_state_changed_at == "2026-03-18T11:00:00Z"



class TestWorkflowStateCSSExists:
    """Test that workflow state CSS classes exist in stylesheet."""

    def test_workflow_state_css_classes_exist(self) -> None:
        """Verify workflow state CSS classes exist in main.css."""
        import pathlib

        css_path = (
            pathlib.Path(__file__).parent.parent / "beeper_ui" / "static" / "css" / "main.css"
        )
        css_content = css_path.read_text()

        assert ".workflow-state-detected" in css_content
        assert ".workflow-state-investigating" in css_content
        assert ".workflow-state-resolved" in css_content
        assert ".workflow-state-verified" in css_content
        assert ".workflow-state-failed" in css_content

    def test_workflow_state_css_colors(self) -> None:
        """Verify workflow state badges use correct colors."""
        import pathlib

        css_path = (
            pathlib.Path(__file__).parent.parent / "beeper_ui" / "static" / "css" / "main.css"
        )
        css_content = css_path.read_text()

        # detected = yellow (#fbbf24)
        assert "#fbbf24" in css_content
        # investigating = blue (#60a5fa)
        assert "#60a5fa" in css_content
        # resolved = green (#34d399)
        assert "#34d399" in css_content
        # verified = purple (#a78bfa)
        assert "#a78bfa" in css_content


class TestValidWorkflowStatesConstant:
    """Test VALID_WORKFLOW_STATES constant."""

    def test_valid_workflow_states_defined(self) -> None:
        from beeper_ui.routes.investigations import VALID_WORKFLOW_STATES

        assert VALID_WORKFLOW_STATES == {
            "detected",
            "investigating",
            "resolved",
            "verified",
            "failed",
        }


class TestVerifyRoute:
    """Test POST /investigations/<id>/verify route."""

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_verify_route_exists(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test that verify route is registered and callable."""
        mock_svc = MagicMock()
        mock_svc.verify_investigation.return_value = True
        mock_get_svc.return_value = mock_svc

        response = client.post("/investigations/inv-test-001/verify")
        # Should not 404 (route exists)
        assert response.status_code != 404

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_verify_route_calls_service(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test that verify route calls InvestigationService.verify_investigation."""
        mock_svc = MagicMock()
        mock_svc.verify_investigation.return_value = True
        mock_get_svc.return_value = mock_svc

        client.post("/investigations/inv-test-001/verify")
        mock_svc.verify_investigation.assert_called_once_with("inv-test-001")

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_verify_route_not_found(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test verify returns 404 when investigation not found or wrong state."""
        mock_svc = MagicMock()
        mock_svc.verify_investigation.return_value = False
        mock_get_svc.return_value = mock_svc

        response = client.post("/investigations/inv-missing/verify")
        assert response.status_code == 404


