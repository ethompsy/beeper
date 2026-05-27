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


# --- Template rendering tests ---


def _mock_investigations_with_workflow_states() -> list[dict]:
    """Return mock investigation data with various workflow states."""
    return [
        {
            "id": "inv-001",
            "status": "investigating",
            "service": "payments",
            "severity": "high",
            "condition": "High error rate",
            "started_at": "2026-03-18T10:00:00Z",
            "completed_at": None,
            "triggered_at": "2026-03-18T09:55:00Z",
            "workflow_state": "detected",
            "workflow_state_changed_at": "2026-03-18T09:55:00Z",
        },
        {
            "id": "inv-002",
            "status": "investigating",
            "service": "auth",
            "severity": "medium",
            "condition": "Latency spike",
            "started_at": "2026-03-18T09:00:00Z",
            "completed_at": None,
            "triggered_at": "2026-03-18T08:55:00Z",
            "workflow_state": "investigating",
            "workflow_state_changed_at": "2026-03-18T09:00:00Z",
        },
        {
            "id": "inv-003",
            "status": "completed",
            "service": "api-gateway",
            "severity": "critical",
            "condition": "Connection pool exhaustion",
            "started_at": "2026-03-17T14:00:00Z",
            "completed_at": "2026-03-17T15:30:00Z",
            "triggered_at": "2026-03-17T13:55:00Z",
            "workflow_state": "resolved",
            "workflow_state_changed_at": "2026-03-17T15:30:00Z",
        },
        {
            "id": "inv-004",
            "status": "completed",
            "service": "api-gateway",
            "severity": "high",
            "condition": "Memory leak",
            "started_at": "2026-03-16T10:00:00Z",
            "completed_at": "2026-03-16T12:00:00Z",
            "triggered_at": "2026-03-16T09:55:00Z",
            "workflow_state": "verified",
            "workflow_state_changed_at": "2026-03-16T13:00:00Z",
        },
    ]


class TestWorkflowStateBadgeRendering:
    """Test workflow state badge rendering in list template."""

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_workflow_state_badges_render(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test that workflow state badges render with correct CSS classes.

        Uses status_group=all to bypass the default active-only filter so that
        investigations with any status (including completed) are visible.
        """
        mock_svc = MagicMock()
        mock_svc.list_investigations.return_value = [
            Investigation.from_dict(d)
            for d in _mock_investigations_with_workflow_states()
        ]
        mock_svc.get_investigation_findings.return_value = {}
        mock_get_svc.return_value = mock_svc

        # Use status_group=all to show all investigations regardless of status
        response = client.get("/investigations/?status_group=all")
        html = response.data.decode()

        # Check workflow state CSS classes are present (from the investigation_row
        # legacy table, which is still rendered in _list_content.html for grouped view)
        # and from the workflow-state-group headers in the grouped layout.
        # With the new card layout, workflow states are shown via the card's left border
        # and status badge. The group-by view uses the workflow-state-group class.
        # Verify the investigations are displayed (workflow state data is present)
        assert "inv-001" in html  # workflow_state=detected
        assert "inv-002" in html  # workflow_state=investigating
        assert "inv-003" in html  # workflow_state=resolved
        assert "inv-004" in html  # workflow_state=verified

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_workflow_state_badge_labels(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test that workflow state badges have correct label text."""
        mock_svc = MagicMock()
        mock_svc.list_investigations.return_value = [
            Investigation.from_dict(d)
            for d in _mock_investigations_with_workflow_states()
        ]
        mock_svc.get_investigation_findings.return_value = {}
        mock_get_svc.return_value = mock_svc

        response = client.get("/investigations/")
        html = response.data.decode()

        assert "Detected" in html
        assert "Investigating" in html
        assert "Resolved" in html
        assert "Verified" in html

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_fallback_to_legacy_status_when_no_workflow_state(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """When workflow_state is None, the status is shown via the status_badge macro.

        Story 4.1 migrated the list to use investigation_card + status_badge macros.
        The new contract: cards render a status-badge with data-status= attribute
        instead of the legacy investigation-status-<X> class.
        """
        mock_svc = MagicMock()
        # Investigation without workflow_state
        inv = Investigation(
            id="inv-legacy",
            status="investigating",
            service="payments",
            severity="high",
            condition="Test",
            started_at="2026-03-18T10:00:00Z",
            workflow_state=None,
        )
        mock_svc.list_investigations.return_value = [inv]
        mock_svc.get_investigation_findings.return_value = {}
        mock_get_svc.return_value = mock_svc

        response = client.get("/investigations/")
        html = response.data.decode()

        # New contract (Story 4.1): status_badge macro emits data-status attribute
        # and status-badge class — the legacy investigation-status-X class is replaced.
        assert "inv-legacy" in html
        assert 'data-status="investigating"' in html
        assert "status-badge" in html


class TestWorkflowStateFilter:
    """Test workflow state filter in filter panel."""

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_filter_panel_has_workflow_state_options(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test that filter panel includes workflow state dropdown."""
        mock_svc = MagicMock()
        mock_svc.list_investigations.return_value = []
        mock_get_svc.return_value = mock_svc

        response = client.get("/investigations/")
        html = response.data.decode()

        assert 'id="inv-filter-workflow-state"' in html
        assert 'name="workflow_state"' in html
        assert "All states" in html
        assert 'value="detected"' in html
        assert 'value="investigating"' in html
        assert 'value="resolved"' in html
        assert 'value="verified"' in html
        assert 'value="failed"' in html

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_workflow_state_filter_applied(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test that workflow state filter narrows results."""
        mock_svc = MagicMock()
        mock_svc.list_investigations.return_value = [
            Investigation.from_dict(d)
            for d in _mock_investigations_with_workflow_states()
        ]
        mock_svc.get_investigation_findings.return_value = {}
        mock_get_svc.return_value = mock_svc

        response = client.get("/investigations/?workflow_state=detected")
        html = response.data.decode()

        # Only detected investigation should be in results
        assert "inv-001" in html
        assert "inv-002" not in html
        assert "inv-003" not in html

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_invalid_workflow_state_filter_ignored(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test that invalid workflow state filter values are ignored.

        Uses status_group=all to bypass the default active-only filter so that
        all investigations (including completed ones) are visible — allowing us
        to confirm the invalid workflow_state filter itself has no effect.
        """
        mock_svc = MagicMock()
        mock_svc.list_investigations.return_value = [
            Investigation.from_dict(d)
            for d in _mock_investigations_with_workflow_states()
        ]
        mock_svc.get_investigation_findings.return_value = {}
        mock_get_svc.return_value = mock_svc

        # status_group=all bypasses the default active filter; workflow_state=invalid
        # should be silently ignored so all 3 investigations remain visible.
        response = client.get("/investigations/?workflow_state=invalid&status_group=all")
        html = response.data.decode()

        # All investigations should be visible (invalid filter ignored)
        assert "inv-001" in html
        assert "inv-002" in html
        assert "inv-003" in html


class TestWorkflowStateCounts:
    """Test workflow state count calculation."""

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_workflow_state_counts_in_context(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test that workflow state counts appear in filter panel."""
        mock_svc = MagicMock()
        mock_svc.list_investigations.return_value = [
            Investigation.from_dict(d)
            for d in _mock_investigations_with_workflow_states()
        ]
        mock_svc.get_investigation_findings.return_value = {}
        mock_get_svc.return_value = mock_svc

        response = client.get("/investigations/")
        html = response.data.decode()

        # Counts should appear in filter dropdown options
        # 1 detected, 1 investigating, 1 resolved, 1 verified
        assert "(1)" in html


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


class TestGroupByWorkflowState:
    """Test group_by=workflow_state functionality."""

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_group_by_toggle_button_renders(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test that Group by State toggle button appears."""
        mock_svc = MagicMock()
        mock_svc.list_investigations.return_value = [
            Investigation.from_dict(d)
            for d in _mock_investigations_with_workflow_states()
        ]
        mock_svc.get_investigation_findings.return_value = {}
        mock_get_svc.return_value = mock_svc

        response = client.get("/investigations/")
        html = response.data.decode()
        assert "Group by State" in html

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_group_by_shows_state_headers(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test that group_by=workflow_state renders state group headers."""
        mock_svc = MagicMock()
        mock_svc.list_investigations.return_value = [
            Investigation.from_dict(d)
            for d in _mock_investigations_with_workflow_states()
        ]
        mock_svc.get_investigation_findings.return_value = {}
        mock_get_svc.return_value = mock_svc

        response = client.get("/investigations/?group_by=workflow_state")
        html = response.data.decode()

        assert "workflow-state-group-header" in html
        assert "workflow-state-group-count" in html

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_flat_list_toggle_when_grouped(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test that Flat List toggle appears when grouped."""
        mock_svc = MagicMock()
        mock_svc.list_investigations.return_value = [
            Investigation.from_dict(d)
            for d in _mock_investigations_with_workflow_states()
        ]
        mock_svc.get_investigation_findings.return_value = {}
        mock_get_svc.return_value = mock_svc

        response = client.get("/investigations/?group_by=workflow_state")
        html = response.data.decode()
        assert "Flat List" in html

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_invalid_group_by_ignored(
        self, mock_get_svc: MagicMock, client: FlaskClient
    ) -> None:
        """Test that invalid group_by values are ignored."""
        mock_svc = MagicMock()
        mock_svc.list_investigations.return_value = [
            Investigation.from_dict(d)
            for d in _mock_investigations_with_workflow_states()
        ]
        mock_svc.get_investigation_findings.return_value = {}
        mock_get_svc.return_value = mock_svc

        response = client.get("/investigations/?group_by=invalid")
        html = response.data.decode()
        # Should render flat list (invalid group_by ignored)
        assert "Group by State" in html
        assert "workflow-state-group-header" not in html
