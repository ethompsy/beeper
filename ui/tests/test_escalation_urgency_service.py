"""Tests for EscalationUrgencyService."""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from beeper_ui.services.escalation_urgency_service import (
    SEVERITY_SCORES,
    EscalationUrgencyError,
    EscalationUrgencyService,
    UrgencyScore,
)


@dataclass
class MockInvestigation:
    """Minimal Investigation-like object for testing."""

    id: str
    service: str
    severity: str
    status: str = "completed"
    condition: str = "test"
    started_at: str | None = None
    completed_at: str | None = None
    triggered_at: str | None = None


class TestUrgencyScoreDefault:
    """Tests for UrgencyScore.default()."""

    def test_default_score_is_zero(self):
        score = UrgencyScore.default()
        assert score.score == 0.0

    def test_default_confidence_is_unknown(self):
        score = UrgencyScore.default()
        assert score.confidence == "unknown"

    def test_default_not_low_confidence(self):
        score = UrgencyScore.default()
        assert score.low_confidence is False

    def test_default_no_slo_data(self):
        score = UrgencyScore.default()
        assert score.has_slo_data is False


class TestCalculateUrgency:
    """Tests for EscalationUrgencyService.calculate_urgency()."""

    def setup_method(self):
        self.service = EscalationUrgencyService(host="localhost")

    def _no_feedback(self):
        return {
            "accurate_rate": None,
            "total_feedback": 0,
            "accurate_count": 0,
            "inaccurate_count": 0,
            "not_an_issue_count": 0,
        }

    def _high_accuracy(self):
        return {
            "accurate_rate": 0.9,
            "total_feedback": 20,
            "accurate_count": 18,
            "inaccurate_count": 1,
            "not_an_issue_count": 1,
        }

    def _low_accuracy(self):
        return {
            "accurate_rate": 0.3,
            "total_feedback": 20,
            "accurate_count": 6,
            "inaccurate_count": 4,
            "not_an_issue_count": 10,
        }

    def _moderate_accuracy(self):
        return {
            "accurate_rate": 0.6,
            "total_feedback": 20,
            "accurate_count": 12,
            "inaccurate_count": 4,
            "not_an_issue_count": 4,
        }

    # --- AC #1: SLO-weighted urgency ---

    def test_high_burn_rate_low_budget_produces_high_urgency(self):
        """High burn rate + low budget remaining = high urgency score."""
        score = self.service.calculate_urgency(
            investigation_id="inv-1",
            service_name="api-gateway",
            severity="critical",
            burn_rate=4.0,
            budget_remaining=0.1,
            customer_impacting=False,
            accuracy_data=self._no_feedback(),
        )
        assert score.score > 70
        assert score.has_slo_data is True

    def test_low_burn_rate_high_budget_produces_low_urgency(self):
        """Low burn rate + high budget remaining = low urgency score."""
        score = self.service.calculate_urgency(
            investigation_id="inv-2",
            service_name="api-gateway",
            severity="low",
            burn_rate=0.5,
            budget_remaining=0.8,
            customer_impacting=False,
            accuracy_data=self._no_feedback(),
        )
        assert score.score < 30
        assert score.has_slo_data is True

    def test_fast_burning_10pct_higher_than_slow_burning_80pct(self):
        """AC #1: fast-burning SLO with 10% budget > slow-burning with 80%."""
        fast_score = self.service.calculate_urgency(
            investigation_id="inv-fast",
            service_name="api-gateway",
            severity="high",
            burn_rate=4.0,
            budget_remaining=0.1,
            customer_impacting=False,
            accuracy_data=self._no_feedback(),
        )
        slow_score = self.service.calculate_urgency(
            investigation_id="inv-slow",
            service_name="api-gateway",
            severity="high",
            burn_rate=0.5,
            budget_remaining=0.8,
            customer_impacting=False,
            accuracy_data=self._no_feedback(),
        )
        assert fast_score.score > slow_score.score

    def test_severity_only_fallback_when_no_slo(self):
        """When no SLO data, urgency falls back to severity score only."""
        score = self.service.calculate_urgency(
            investigation_id="inv-3",
            service_name="api-gateway",
            severity="critical",
            burn_rate=None,
            budget_remaining=None,
            customer_impacting=False,
            accuracy_data=self._no_feedback(),
        )
        assert score.score == SEVERITY_SCORES["critical"]
        assert score.has_slo_data is False

    def test_severity_scores_mapping(self):
        """Each severity produces the expected base score when no SLO."""
        for sev, expected in SEVERITY_SCORES.items():
            score = self.service.calculate_urgency(
                investigation_id="inv-sev",
                service_name="svc",
                severity=sev,
                burn_rate=None,
                budget_remaining=None,
                customer_impacting=False,
                accuracy_data=self._no_feedback(),
            )
            assert score.score == expected, f"Severity {sev} mismatch"

    def test_customer_impact_boost_increases_urgency(self):
        """Customer impacting investigations get a boost."""
        no_impact = self.service.calculate_urgency(
            investigation_id="inv-no",
            service_name="svc",
            severity="high",
            burn_rate=2.0,
            budget_remaining=0.5,
            customer_impacting=False,
            accuracy_data=self._no_feedback(),
        )
        with_impact = self.service.calculate_urgency(
            investigation_id="inv-yes",
            service_name="svc",
            severity="high",
            burn_rate=2.0,
            budget_remaining=0.5,
            customer_impacting=True,
            accuracy_data=self._no_feedback(),
        )
        assert with_impact.score > no_impact.score
        assert with_impact.factors["customer_impact_boost"] is True
        assert no_impact.factors["customer_impact_boost"] is False

    def test_urgency_caps_at_100(self):
        """Urgency score never exceeds 100 even with boost."""
        score = self.service.calculate_urgency(
            investigation_id="inv-max",
            service_name="svc",
            severity="critical",
            burn_rate=10.0,
            budget_remaining=0.0,
            customer_impacting=True,
            accuracy_data=self._no_feedback(),
        )
        assert score.score <= 100.0

    # --- AC #2: Confidence dampening ---

    def test_high_accuracy_preserves_urgency(self):
        """AC #2: >80% accurate → confidence="high", urgency preserved."""
        score = self.service.calculate_urgency(
            investigation_id="inv-hi",
            service_name="svc",
            severity="high",
            burn_rate=3.0,
            budget_remaining=0.3,
            customer_impacting=False,
            accuracy_data=self._high_accuracy(),
        )
        assert score.confidence == "high"
        assert score.low_confidence is False
        assert score.factors["confidence_dampening"] is False

    def test_low_accuracy_dampens_urgency(self):
        """AC #2: <50% accurate → low confidence, urgency dampened."""
        undampened = self.service.calculate_urgency(
            investigation_id="inv-undamp",
            service_name="svc",
            severity="high",
            burn_rate=3.0,
            budget_remaining=0.3,
            customer_impacting=False,
            accuracy_data=self._no_feedback(),
        )
        dampened = self.service.calculate_urgency(
            investigation_id="inv-damp",
            service_name="svc",
            severity="high",
            burn_rate=3.0,
            budget_remaining=0.3,
            customer_impacting=False,
            accuracy_data=self._low_accuracy(),
        )
        assert dampened.confidence == "low"
        assert dampened.low_confidence is True
        assert dampened.factors["confidence_dampening"] is True
        assert dampened.score < undampened.score

    def test_moderate_accuracy_no_dampening(self):
        """50-80% accurate → moderate confidence, no dampening."""
        score = self.service.calculate_urgency(
            investigation_id="inv-mod",
            service_name="svc",
            severity="high",
            burn_rate=3.0,
            budget_remaining=0.3,
            customer_impacting=False,
            accuracy_data=self._moderate_accuracy(),
        )
        assert score.confidence == "moderate"
        assert score.low_confidence is False
        assert score.factors["confidence_dampening"] is False

    def test_insufficient_feedback_unknown_confidence(self):
        """<10 feedback entries → confidence="unknown", no dampening."""
        score = self.service.calculate_urgency(
            investigation_id="inv-unk",
            service_name="svc",
            severity="high",
            burn_rate=3.0,
            budget_remaining=0.3,
            customer_impacting=False,
            accuracy_data=self._no_feedback(),
        )
        assert score.confidence == "unknown"
        assert score.low_confidence is False

    # --- Factors dict for tooltip ---

    def test_factors_dict_complete_with_slo(self):
        """Factors dict contains all components when SLO data present."""
        score = self.service.calculate_urgency(
            investigation_id="inv-f",
            service_name="svc",
            severity="high",
            burn_rate=2.0,
            budget_remaining=0.5,
            customer_impacting=True,
            accuracy_data=self._low_accuracy(),
        )
        assert "burn_rate_component" in score.factors
        assert "budget_component" in score.factors
        assert "severity_component" in score.factors
        assert "customer_impact_boost" in score.factors
        assert "confidence_dampening" in score.factors
        assert score.factors["burn_rate_component"] > 0
        assert score.factors["budget_component"] > 0
        assert score.factors["severity_component"] > 0

    def test_factors_dict_severity_only_without_slo(self):
        """Factors dict shows severity-only values when no SLO data."""
        score = self.service.calculate_urgency(
            investigation_id="inv-ns",
            service_name="svc",
            severity="medium",
            burn_rate=None,
            budget_remaining=None,
            customer_impacting=False,
            accuracy_data=self._no_feedback(),
        )
        assert score.factors["burn_rate_component"] == 0.0
        assert score.factors["budget_component"] == 0.0
        assert score.factors["severity_component"] == SEVERITY_SCORES["medium"]

    # --- Boolean bypass ---

    def test_boolean_burn_rate_falls_back_to_severity(self):
        """Boolean burn_rate value falls back to severity-only scoring."""
        score = self.service.calculate_urgency(
            investigation_id="inv-bool",
            service_name="svc",
            severity="high",
            burn_rate=True,
            budget_remaining=0.5,
            customer_impacting=False,
            accuracy_data=self._no_feedback(),
        )
        assert score.has_slo_data is False

    def test_boolean_budget_remaining_falls_back_to_severity(self):
        """Boolean budget_remaining value falls back to severity-only."""
        score = self.service.calculate_urgency(
            investigation_id="inv-bool2",
            service_name="svc",
            severity="high",
            burn_rate=2.0,
            budget_remaining=True,
            customer_impacting=False,
            accuracy_data=self._no_feedback(),
        )
        assert score.has_slo_data is False

    def test_boolean_accurate_rate_treated_as_unknown(self):
        """Boolean accurate_rate is treated as unknown confidence."""
        score = self.service.calculate_urgency(
            investigation_id="inv-bool3",
            service_name="svc",
            severity="high",
            burn_rate=2.0,
            budget_remaining=0.5,
            customer_impacting=False,
            accuracy_data={"accurate_rate": True},
        )
        assert score.confidence == "unknown"


class TestGetServiceAccuracyRate:
    """Tests for EscalationUrgencyService.get_service_accuracy_rate()."""

    def setup_method(self):
        self.service = EscalationUrgencyService(host="localhost")
        self.mock_client = MagicMock()
        self.service._client = self.mock_client

    def _mock_point(self, feedback_value):
        point = MagicMock()
        point.payload = {"investigation_feedback": feedback_value, "service": "api"}
        return point

    def test_aggregates_feedback_correctly(self):
        self.mock_client.scroll.return_value = (
            [
                self._mock_point("accurate"),
                self._mock_point("accurate"),
                self._mock_point("inaccurate"),
                self._mock_point("not_an_issue"),
            ]
            * 3,  # 12 total entries
            None,
        )
        result = self.service.get_service_accuracy_rate("api")
        assert result["total_feedback"] == 12
        assert result["accurate_count"] == 6
        assert result["inaccurate_count"] == 3
        assert result["not_an_issue_count"] == 3
        assert result["accurate_rate"] == 6 / 12

    def test_returns_none_rate_below_min_feedback(self):
        self.mock_client.scroll.return_value = (
            [self._mock_point("accurate")] * 5,
            None,
        )
        result = self.service.get_service_accuracy_rate("api")
        assert result["total_feedback"] == 5
        assert result["accurate_rate"] is None

    def test_skips_entries_without_feedback(self):
        no_feedback_point = MagicMock()
        no_feedback_point.payload = {"service": "api"}
        self.mock_client.scroll.return_value = (
            [no_feedback_point, self._mock_point("accurate")],
            None,
        )
        result = self.service.get_service_accuracy_rate("api")
        assert result["total_feedback"] == 1
        assert result["accurate_rate"] is None  # Below MIN_FEEDBACK

    def test_qdrant_failure_raises_error(self):
        self.mock_client.scroll.side_effect = Exception("connection refused")
        with pytest.raises(EscalationUrgencyError):
            self.service.get_service_accuracy_rate("api")


class TestComputeBatchUrgency:
    """Tests for EscalationUrgencyService.compute_batch_urgency()."""

    def setup_method(self):
        self.service = EscalationUrgencyService(host="localhost")

    @patch.object(EscalationUrgencyService, "get_service_accuracy_rate")
    def test_batch_returns_score_per_investigation(self, mock_accuracy):
        mock_accuracy.return_value = {
            "accurate_rate": None,
            "total_feedback": 0,
            "accurate_count": 0,
            "inaccurate_count": 0,
            "not_an_issue_count": 0,
        }
        investigations = [
            MockInvestigation(id="inv-1", service="api", severity="high"),
            MockInvestigation(id="inv-2", service="api", severity="low"),
        ]
        slo_budgets = {"api": {"burn_rate": 2.0, "budget_remaining": 0.5}}
        findings = {"inv-1": {}, "inv-2": {}}

        result = self.service.compute_batch_urgency(
            investigations, slo_budgets, findings
        )
        assert "inv-1" in result
        assert "inv-2" in result
        assert result["inv-1"].score > result["inv-2"].score  # high > low severity

    @patch.object(EscalationUrgencyService, "get_service_accuracy_rate")
    def test_batch_caches_accuracy_per_service(self, mock_accuracy):
        mock_accuracy.return_value = {
            "accurate_rate": None,
            "total_feedback": 0,
            "accurate_count": 0,
            "inaccurate_count": 0,
            "not_an_issue_count": 0,
        }
        investigations = [
            MockInvestigation(id="inv-1", service="api", severity="high"),
            MockInvestigation(id="inv-2", service="api", severity="medium"),
            MockInvestigation(id="inv-3", service="db", severity="low"),
        ]
        slo_budgets = {"api": None, "db": None}
        findings = {"inv-1": {}, "inv-2": {}, "inv-3": {}}

        self.service.compute_batch_urgency(
            investigations, slo_budgets, findings
        )
        # 2 unique services → 2 calls, not 3
        assert mock_accuracy.call_count == 2

    @patch.object(EscalationUrgencyService, "get_service_accuracy_rate")
    def test_batch_handles_no_slo_gracefully(self, mock_accuracy):
        mock_accuracy.return_value = {
            "accurate_rate": None,
            "total_feedback": 0,
            "accurate_count": 0,
            "inaccurate_count": 0,
            "not_an_issue_count": 0,
        }
        investigations = [
            MockInvestigation(id="inv-1", service="api", severity="high"),
        ]
        slo_budgets = {"api": None}
        findings = {"inv-1": {}}

        result = self.service.compute_batch_urgency(
            investigations, slo_budgets, findings
        )
        assert result["inv-1"].has_slo_data is False
        assert result["inv-1"].score == SEVERITY_SCORES["high"]

    @patch.object(EscalationUrgencyService, "get_service_accuracy_rate")
    def test_batch_extracts_customer_impacting(self, mock_accuracy):
        mock_accuracy.return_value = {
            "accurate_rate": None,
            "total_feedback": 0,
            "accurate_count": 0,
            "inaccurate_count": 0,
            "not_an_issue_count": 0,
        }
        investigations = [
            MockInvestigation(id="inv-1", service="api", severity="high"),
        ]
        slo_budgets = {"api": None}
        findings = {"inv-1": {"customer_impacting": True}}

        result = self.service.compute_batch_urgency(
            investigations, slo_budgets, findings
        )
        assert result["inv-1"].factors["customer_impact_boost"] is True

    @patch.object(EscalationUrgencyService, "get_service_accuracy_rate")
    def test_batch_handles_accuracy_error_gracefully(self, mock_accuracy):
        mock_accuracy.side_effect = EscalationUrgencyError("qdrant down")
        investigations = [
            MockInvestigation(id="inv-1", service="api", severity="high"),
        ]
        slo_budgets = {"api": None}
        findings = {"inv-1": {}}

        result = self.service.compute_batch_urgency(
            investigations, slo_budgets, findings
        )
        # Should still produce a score with unknown confidence
        assert "inv-1" in result
        assert result["inv-1"].confidence == "unknown"
