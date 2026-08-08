"""Tests for escalation urgency routes in investigations.py."""

from unittest.mock import MagicMock, patch

from beeper_ui.services.escalation_urgency_service import (
    EscalationUrgencyError,
    UrgencyScore,
)
from beeper_ui.services.investigation_service import InvestigationDetail

INV_SVC_PATCH = "beeper_ui.routes.investigations.get_investigation_service"
SLO_SVC_PATCH = "beeper_ui.routes.investigations._get_slo_service"
URG_SVC_PATCH = "beeper_ui.routes.investigations._get_urgency_service"


def _make_investigation_detail(
    inv_id: str = "inv-001",
    service: str = "api-gateway",
    severity: str = "high",
    status: str = "investigating",
    condition: str = "HighErrorRate",
) -> InvestigationDetail:
    return InvestigationDetail(
        id=inv_id,
        status=status,
        service=service,
        severity=severity,
        condition=condition,
        started_at="2026-03-16T10:00:00Z",
        completed_at="2026-03-16T10:05:00Z",
        triggered_at="2026-03-16T09:59:00Z",
        message=None,
        error=None,
        job_name=None,
    )


def _make_urgency_score(
    score: float = 72.5,
    confidence: str = "high",
    low_confidence: bool = False,
    has_slo_data: bool = True,
) -> UrgencyScore:
    return UrgencyScore(
        score=score,
        confidence=confidence,
        low_confidence=low_confidence,
        factors={
            "burn_rate_component": 32.0,
            "budget_component": 22.8,
            "severity_component": 18.8,
            "customer_impact_boost": False,
            "confidence_dampening": False,
        },
        service_name="api-gateway",
        investigation_id="inv-001",
        has_slo_data=has_slo_data,
    )




class TestInvestigationUrgencyDetail:
    """Tests for GET /investigations/<id>/urgency."""

    @patch(URG_SVC_PATCH)
    @patch(SLO_SVC_PATCH)
    @patch(INV_SVC_PATCH)
    def test_returns_urgency_card(
        self, mock_inv_svc, mock_slo_svc, mock_urg_svc, client
    ):
        inv_svc = MagicMock()
        inv_svc.get_investigation.return_value = _make_investigation_detail()
        inv_svc.get_investigation_findings.return_value = {
            "customer_impacting": True,
        }
        mock_inv_svc.return_value = inv_svc

        slo_svc = MagicMock()
        slo_svc.get_service_budget.return_value = {
            "burn_rate": 3.0,
            "budget_remaining": 0.2,
        }
        mock_slo_svc.return_value = slo_svc

        urg_svc = MagicMock()
        urg_svc.get_service_accuracy_rate.return_value = {
            "accurate_rate": 0.85,
            "total_feedback": 20,
            "accurate_count": 17,
            "inaccurate_count": 2,
            "not_an_issue_count": 1,
        }
        urg_svc.calculate_urgency.return_value = _make_urgency_score()
        mock_urg_svc.return_value = urg_svc

        response = client.get("/investigations/inv-001/urgency")
        assert response.status_code == 200
        assert b"Escalation Urgency" in response.data

    @patch(URG_SVC_PATCH)
    @patch(SLO_SVC_PATCH)
    @patch(INV_SVC_PATCH)
    def test_urgency_card_shows_factors(
        self, mock_inv_svc, mock_slo_svc, mock_urg_svc, client
    ):
        inv_svc = MagicMock()
        inv_svc.get_investigation.return_value = _make_investigation_detail()
        inv_svc.get_investigation_findings.return_value = {}
        mock_inv_svc.return_value = inv_svc

        slo_svc = MagicMock()
        slo_svc.get_service_budget.return_value = {
            "burn_rate": 2.0,
            "budget_remaining": 0.4,
        }
        mock_slo_svc.return_value = slo_svc

        urg_svc = MagicMock()
        urg_svc.get_service_accuracy_rate.return_value = {
            "accurate_rate": None,
            "total_feedback": 0,
            "accurate_count": 0,
            "inaccurate_count": 0,
            "not_an_issue_count": 0,
        }
        urg_svc.calculate_urgency.return_value = _make_urgency_score()
        mock_urg_svc.return_value = urg_svc

        response = client.get("/investigations/inv-001/urgency")
        assert response.status_code == 200
        assert b"Burn Rate" in response.data
        assert b"Budget Remaining" in response.data
        assert b"Severity" in response.data

    @patch(URG_SVC_PATCH)
    @patch(SLO_SVC_PATCH)
    @patch(INV_SVC_PATCH)
    def test_urgency_card_no_slo_shows_fallback(
        self, mock_inv_svc, mock_slo_svc, mock_urg_svc, client
    ):
        inv_svc = MagicMock()
        inv_svc.get_investigation.return_value = _make_investigation_detail()
        inv_svc.get_investigation_findings.return_value = {}
        mock_inv_svc.return_value = inv_svc

        slo_svc = MagicMock()
        slo_svc.get_service_budget.return_value = None
        mock_slo_svc.return_value = slo_svc

        urg_svc = MagicMock()
        urg_svc.get_service_accuracy_rate.return_value = {
            "accurate_rate": None,
            "total_feedback": 0,
            "accurate_count": 0,
            "inaccurate_count": 0,
            "not_an_issue_count": 0,
        }
        urg_svc.calculate_urgency.return_value = _make_urgency_score(
            has_slo_data=False,
        )
        mock_urg_svc.return_value = urg_svc

        response = client.get("/investigations/inv-001/urgency")
        assert response.status_code == 200
        assert b"severity-only" in response.data

    @patch(URG_SVC_PATCH)
    @patch(SLO_SVC_PATCH)
    @patch(INV_SVC_PATCH)
    def test_urgency_card_low_confidence_shows_warning(
        self, mock_inv_svc, mock_slo_svc, mock_urg_svc, client
    ):
        inv_svc = MagicMock()
        inv_svc.get_investigation.return_value = _make_investigation_detail()
        inv_svc.get_investigation_findings.return_value = {}
        mock_inv_svc.return_value = inv_svc

        slo_svc = MagicMock()
        slo_svc.get_service_budget.return_value = {
            "burn_rate": 2.0,
            "budget_remaining": 0.4,
        }
        mock_slo_svc.return_value = slo_svc

        urg_svc = MagicMock()
        urg_svc.get_service_accuracy_rate.return_value = {
            "accurate_rate": 0.3,
            "total_feedback": 20,
            "accurate_count": 6,
            "inaccurate_count": 4,
            "not_an_issue_count": 10,
        }
        urg_svc.calculate_urgency.return_value = _make_urgency_score(
            confidence="low",
            low_confidence=True,
        )
        mock_urg_svc.return_value = urg_svc

        response = client.get("/investigations/inv-001/urgency")
        assert response.status_code == 200
        assert b"dampened" in response.data or b"low confidence" in response.data.lower()

    @patch(URG_SVC_PATCH)
    @patch(SLO_SVC_PATCH)
    @patch(INV_SVC_PATCH)
    def test_urgency_qdrant_failure_returns_error(
        self, mock_inv_svc, mock_slo_svc, mock_urg_svc, client
    ):
        inv_svc = MagicMock()
        inv_svc.get_investigation.return_value = _make_investigation_detail()
        inv_svc.get_investigation_findings.return_value = {}
        mock_inv_svc.return_value = inv_svc

        slo_svc = MagicMock()
        slo_svc.get_service_budget.return_value = None
        mock_slo_svc.return_value = slo_svc

        urg_svc = MagicMock()
        urg_svc.get_service_accuracy_rate.side_effect = EscalationUrgencyError(
            "qdrant down"
        )
        mock_urg_svc.return_value = urg_svc

        response = client.get("/investigations/inv-001/urgency")
        assert response.status_code == 200
        assert b"Unable to compute" in response.data or b"error" in response.data.lower()

    @patch(INV_SVC_PATCH)
    def test_urgency_investigation_not_found(self, mock_inv_svc, client):
        inv_svc = MagicMock()
        inv_svc.get_investigation.return_value = None
        mock_inv_svc.return_value = inv_svc

        response = client.get("/investigations/inv-missing/urgency")
        assert response.status_code == 200
        assert b"not found" in response.data.lower()

    @patch(URG_SVC_PATCH)
    @patch(SLO_SVC_PATCH)
    @patch(INV_SVC_PATCH)
    def test_urgency_route_closes_investigation_service(
        self, mock_inv_svc, mock_slo_svc, mock_urg_svc, client
    ):
        """Verify InvestigationService is closed after urgency route completes."""
        inv_svc = MagicMock()
        inv_svc.get_investigation.return_value = _make_investigation_detail()
        inv_svc.get_investigation_findings.return_value = {}
        mock_inv_svc.return_value = inv_svc

        slo_svc = MagicMock()
        slo_svc.get_service_budget.return_value = None
        mock_slo_svc.return_value = slo_svc

        urg_svc = MagicMock()
        urg_svc.get_service_accuracy_rate.return_value = {
            "accurate_rate": None,
            "total_feedback": 0,
            "accurate_count": 0,
            "inaccurate_count": 0,
            "not_an_issue_count": 0,
        }
        urg_svc.calculate_urgency.return_value = _make_urgency_score()
        mock_urg_svc.return_value = urg_svc

        client.get("/investigations/inv-001/urgency")
        inv_svc.close.assert_called_once()


