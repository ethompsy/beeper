"""Tests for confidence gate UI integration — investigation gate-status endpoint."""

from unittest.mock import MagicMock, patch

import pytest

from beeper_ui.services.confidence_gate_service import GateDecision


@pytest.fixture
def app():
    """Create Flask app for testing."""
    from beeper_ui.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


class TestGateStatusEndpoint:
    """Tests for GET /investigations/<id>/gate-status."""

    @patch("beeper_ui.routes.investigations.ConfidenceGateService")
    @patch("beeper_ui.routes.investigations.normalize_confidence_score")
    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_gate_status_advisory(
        self, mock_get_svc, mock_normalize, mock_gate_cls, client
    ):
        """Advisory gate status returns correct badge and message."""
        # Mock investigation service
        mock_inv_svc = MagicMock()
        investigation = MagicMock()
        investigation.service = "payment-api"
        investigation.id = "inv-123"
        mock_inv_svc.get_investigation.return_value = investigation
        mock_inv_svc.get_investigation_findings.return_value = {
            "rca_hypothesis": {"confidence_percentage": 80}
        }
        mock_get_svc.return_value = mock_inv_svc

        mock_normalize.return_value = 0.80

        # Mock gate service
        mock_gate = MagicMock()
        mock_gate.evaluate_gate.return_value = GateDecision(
            permitted=False,
            confidence_score=0.80,
            threshold=0.85,
            trust_level=4,
            action_type="advisory",
            reason="below threshold",
            service_name="payment-api",
        )
        mock_gate_cls.return_value = mock_gate

        response = client.get("/investigations/inv-123/gate-status")

        assert response.status_code == 200
        html = response.data.decode()
        assert "Advisory Only" in html
        assert "Manual Approve" in html

    @patch("beeper_ui.routes.investigations.ConfidenceGateService")
    @patch("beeper_ui.routes.investigations.normalize_confidence_score")
    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_gate_status_permitted(
        self, mock_get_svc, mock_normalize, mock_gate_cls, client
    ):
        """Permitted gate status returns correct badge."""
        mock_inv_svc = MagicMock()
        investigation = MagicMock()
        investigation.service = "payment-api"
        investigation.id = "inv-123"
        mock_inv_svc.get_investigation.return_value = investigation
        mock_inv_svc.get_investigation_findings.return_value = {}
        mock_get_svc.return_value = mock_inv_svc

        mock_normalize.return_value = 0.95

        mock_gate = MagicMock()
        mock_gate.evaluate_gate.return_value = GateDecision(
            permitted=True,
            confidence_score=0.95,
            threshold=0.90,
            trust_level=3,
            action_type="autonomous",
            reason="meets threshold",
            service_name="payment-api",
        )
        mock_gate_cls.return_value = mock_gate

        response = client.get("/investigations/inv-123/gate-status")

        assert response.status_code == 200
        html = response.data.decode()
        assert "Auto-action Eligible" in html
        # No manual approve button when permitted
        assert "Manual Approve" not in html

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_gate_status_not_found(self, mock_get_svc, client):
        """Gate status for non-existent investigation returns graceful empty."""
        mock_inv_svc = MagicMock()
        mock_inv_svc.get_investigation.return_value = None
        mock_get_svc.return_value = mock_inv_svc

        response = client.get("/investigations/inv-999/gate-status")

        assert response.status_code == 200
        html = response.data.decode()
        assert "Pending" in html or "gate" in html.lower()

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_gate_status_service_error(self, mock_get_svc, client):
        """Service error shows unavailable status."""
        from beeper_ui.services.investigation_service import InvestigationServiceError

        mock_inv_svc = MagicMock()
        mock_inv_svc.get_investigation.side_effect = InvestigationServiceError(
            "connection refused"
        )
        mock_get_svc.return_value = mock_inv_svc

        response = client.get("/investigations/inv-123/gate-status")

        assert response.status_code == 200
        html = response.data.decode()
        assert "Unavailable" in html

    @patch("beeper_ui.routes.investigations.ConfidenceGateService")
    @patch("beeper_ui.routes.investigations.normalize_confidence_score")
    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_gate_status_manual_approve_button_blocked(
        self, mock_get_svc, mock_normalize, mock_gate_cls, client
    ):
        """Manual approve button shown when gate blocks and TL >= 3."""
        mock_inv_svc = MagicMock()
        investigation = MagicMock()
        investigation.service = "payment-api"
        investigation.id = "inv-123"
        mock_inv_svc.get_investigation.return_value = investigation
        mock_inv_svc.get_investigation_findings.return_value = {}
        mock_get_svc.return_value = mock_inv_svc

        mock_normalize.return_value = 0.70

        mock_gate = MagicMock()
        mock_gate.evaluate_gate.return_value = GateDecision(
            permitted=False,
            confidence_score=0.70,
            threshold=0.90,
            trust_level=3,
            action_type="advisory",
            reason="below threshold",
            service_name="payment-api",
        )
        mock_gate_cls.return_value = mock_gate

        response = client.get("/investigations/inv-123/gate-status")

        assert response.status_code == 200
        html = response.data.decode()
        assert "Manual Approve" in html
        assert "/investigations/inv-123/confirm" in html

    @patch("beeper_ui.routes.investigations.ConfidenceGateService")
    @patch("beeper_ui.routes.investigations.normalize_confidence_score")
    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_gate_status_no_manual_approve_tl1(
        self, mock_get_svc, mock_normalize, mock_gate_cls, client
    ):
        """No manual approve button for TL1 advisory (trust level < 3)."""
        mock_inv_svc = MagicMock()
        investigation = MagicMock()
        investigation.service = "payment-api"
        investigation.id = "inv-123"
        mock_inv_svc.get_investigation.return_value = investigation
        mock_inv_svc.get_investigation_findings.return_value = {}
        mock_get_svc.return_value = mock_inv_svc

        mock_normalize.return_value = 0.95

        mock_gate = MagicMock()
        mock_gate.evaluate_gate.return_value = GateDecision(
            permitted=False,
            confidence_score=0.95,
            threshold=0.0,
            trust_level=1,
            action_type="advisory",
            reason="TL1 advisory-only",
            service_name="payment-api",
        )
        mock_gate_cls.return_value = mock_gate

        response = client.get("/investigations/inv-123/gate-status")

        assert response.status_code == 200
        html = response.data.decode()
        assert "Manual Approve" not in html
