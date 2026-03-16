"""Tests for confidence gate API routes."""

from unittest.mock import MagicMock, patch

import pytest

from beeper_ui.services.confidence_gate_service import (
    ConfidenceGateConfig,
    GateDecision,
)


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


@pytest.fixture
def app():
    """Create Flask app for testing."""
    from beeper_ui.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app


# ---------- POST /api/v1/trust/gates/evaluate ----------


class TestEvaluateGate:
    """Tests for POST /api/v1/trust/gates/evaluate."""

    @patch("beeper_ui.routes.confidence_gates._get_gate_service")
    def test_evaluate_valid_request(self, mock_get_svc, client):
        """Valid evaluate request returns 200 with GateDecision JSON."""
        mock_svc = MagicMock()
        mock_svc.evaluate_gate.return_value = GateDecision(
            permitted=True,
            confidence_score=0.95,
            threshold=0.90,
            trust_level=3,
            action_type="autonomous",
            reason="Confidence 95% meets threshold 90%",
            service_name="payment-api",
        )
        mock_get_svc.return_value = mock_svc

        response = client.post(
            "/api/v1/trust/gates/evaluate",
            json={"service_name": "payment-api", "confidence_score": 0.95},
            headers={"X-Beeper-Role": "user"},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["permitted"] is True
        assert data["confidence_score"] == 0.95
        assert data["service_name"] == "payment-api"
        assert "message" in data

    @patch("beeper_ui.routes.confidence_gates._get_gate_service")
    def test_evaluate_missing_service_name(self, mock_get_svc, client):
        """Missing service_name returns 400."""
        response = client.post(
            "/api/v1/trust/gates/evaluate",
            json={"confidence_score": 0.95},
            headers={"X-Beeper-Role": "user"},
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "service_name" in data["detail"]

    @patch("beeper_ui.routes.confidence_gates._get_gate_service")
    def test_evaluate_missing_confidence_score(self, mock_get_svc, client):
        """Missing confidence_score returns 400."""
        response = client.post(
            "/api/v1/trust/gates/evaluate",
            json={"service_name": "payment-api"},
            headers={"X-Beeper-Role": "user"},
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "confidence_score" in data["detail"]

    @patch("beeper_ui.routes.confidence_gates._get_gate_service")
    def test_evaluate_negative_confidence_score(self, mock_get_svc, client):
        """Negative confidence_score returns 400."""
        response = client.post(
            "/api/v1/trust/gates/evaluate",
            json={"service_name": "payment-api", "confidence_score": -0.1},
            headers={"X-Beeper-Role": "user"},
        )

        assert response.status_code == 400

    @patch("beeper_ui.routes.confidence_gates._get_gate_service")
    def test_evaluate_confidence_score_above_one(self, mock_get_svc, client):
        """confidence_score > 1.0 returns 400."""
        response = client.post(
            "/api/v1/trust/gates/evaluate",
            json={"service_name": "payment-api", "confidence_score": 1.5},
            headers={"X-Beeper-Role": "user"},
        )

        assert response.status_code == 400

    @patch("beeper_ui.routes.confidence_gates._get_gate_service")
    def test_evaluate_invalid_json(self, mock_get_svc, client):
        """Invalid JSON body returns 400."""
        response = client.post(
            "/api/v1/trust/gates/evaluate",
            data="not json",
            content_type="application/json",
            headers={"X-Beeper-Role": "user"},
        )

        assert response.status_code == 400


# ---------- GET /api/v1/trust/gates ----------


class TestListGateThresholds:
    """Tests for GET /api/v1/trust/gates."""

    @patch("beeper_ui.routes.confidence_gates._get_gate_service")
    def test_list_thresholds(self, mock_get_svc, client):
        """Lists all gate thresholds."""
        mock_svc = MagicMock()
        mock_svc.get_gate_thresholds.return_value = [
            ConfidenceGateConfig(3, 0.90, "", "", "Act with Approval"),
            ConfidenceGateConfig(4, 0.85, "", "", "Act and Notify"),
            ConfidenceGateConfig(5, 0.80, "", "", "Fully Autonomous"),
        ]
        mock_get_svc.return_value = mock_svc

        response = client.get(
            "/api/v1/trust/gates",
            headers={"X-Beeper-Role": "user"},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 3
        assert data[0]["trust_level"] == 3
        assert data[0]["threshold"] == 0.90


# ---------- GET /api/v1/trust/gates/<trust_level> ----------


class TestGetGateThreshold:
    """Tests for GET /api/v1/trust/gates/<trust_level>."""

    @patch("beeper_ui.routes.confidence_gates._get_gate_service")
    def test_get_threshold_valid(self, mock_get_svc, client):
        """Get threshold for valid trust level."""
        mock_svc = MagicMock()
        mock_svc.get_gate_threshold.return_value = ConfidenceGateConfig(
            3, 0.90, "admin", "2026-03-16T10:00:00Z", "Act with Approval"
        )
        mock_get_svc.return_value = mock_svc

        response = client.get(
            "/api/v1/trust/gates/3",
            headers={"X-Beeper-Role": "user"},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["trust_level"] == 3
        assert data["threshold"] == 0.90

    @patch("beeper_ui.routes.confidence_gates._get_gate_service")
    def test_get_threshold_tl1_invalid(self, mock_get_svc, client):
        """TL1 returns 400 — advisory-only."""
        response = client.get(
            "/api/v1/trust/gates/1",
            headers={"X-Beeper-Role": "user"},
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "advisory-only" in data["detail"]


# ---------- PUT /api/v1/trust/gates/<trust_level> ----------


class TestUpdateGateThreshold:
    """Tests for PUT /api/v1/trust/gates/<trust_level>."""

    @patch("beeper_ui.routes.confidence_gates._get_gate_service")
    def test_update_valid_threshold(self, mock_get_svc, client):
        """Admin can update threshold for TL3."""
        mock_svc = MagicMock()
        mock_svc.set_gate_threshold.return_value = ConfidenceGateConfig(
            3, 0.85, "admin", "2026-03-16T10:00:00Z", "Act with Approval"
        )
        mock_get_svc.return_value = mock_svc

        response = client.put(
            "/api/v1/trust/gates/3",
            json={"threshold": 0.85},
            headers={"X-Beeper-Role": "admin"},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["threshold"] == 0.85

    @patch("beeper_ui.routes.confidence_gates._get_gate_service")
    def test_update_tl1_rejected(self, mock_get_svc, client):
        """PUT for TL1 returns 400."""
        response = client.put(
            "/api/v1/trust/gates/1",
            json={"threshold": 0.90},
            headers={"X-Beeper-Role": "admin"},
        )

        assert response.status_code == 400

    @patch("beeper_ui.routes.confidence_gates._get_gate_service")
    def test_update_user_role_forbidden(self, mock_get_svc, client):
        """User role returns 403 for PUT."""
        response = client.put(
            "/api/v1/trust/gates/3",
            json={"threshold": 0.85},
            headers={"X-Beeper-Role": "user"},
        )

        assert response.status_code == 403

    @patch("beeper_ui.routes.confidence_gates._get_gate_service")
    def test_update_threshold_above_one(self, mock_get_svc, client):
        """Threshold > 1.0 returns 400."""
        response = client.put(
            "/api/v1/trust/gates/3",
            json={"threshold": 1.5},
            headers={"X-Beeper-Role": "admin"},
        )

        assert response.status_code == 400

    @patch("beeper_ui.routes.confidence_gates._get_gate_service")
    def test_update_threshold_negative(self, mock_get_svc, client):
        """Threshold < 0.0 returns 400."""
        response = client.put(
            "/api/v1/trust/gates/3",
            json={"threshold": -0.5},
            headers={"X-Beeper-Role": "admin"},
        )

        assert response.status_code == 400

    @patch("beeper_ui.routes.confidence_gates._get_gate_service")
    def test_update_missing_threshold(self, mock_get_svc, client):
        """Missing threshold field returns 400."""
        response = client.put(
            "/api/v1/trust/gates/3",
            json={},
            headers={"X-Beeper-Role": "admin"},
        )

        assert response.status_code == 400
