"""Tests for ConfidenceGateService — confidence gate evaluation engine."""

from unittest.mock import MagicMock

import pytest

from beeper_ui.services.confidence_gate_service import (
    GATE_THRESHOLDS_KEY,
    TEXT_CONFIDENCE_MAP,
    ConfidenceGateError,
    ConfidenceGateService,
    GateDecision,
    format_gate_message,
    normalize_confidence_score,
)

# ---------- Fixtures & Helpers ----------


def _make_gate_payload(
    tl3: float = 0.90,
    tl4: float = 0.85,
    tl5: float = 0.80,
    updated_by: str = "admin@test.com",
    updated_at: str = "2026-03-16T10:00:00+00:00",
) -> dict:
    """Create a mock Qdrant payload for gate thresholds."""
    return {
        "service_name": GATE_THRESHOLDS_KEY,
        "gate_threshold_tl3": tl3,
        "gate_threshold_tl4": tl4,
        "gate_threshold_tl5": tl5,
        "gate_updated_by": updated_by,
        "gate_updated_at": updated_at,
    }


def _make_point(
    point_id: str = "gate-uuid-1",
    payload: dict | None = None,
) -> MagicMock:
    """Create a mock Qdrant point."""
    point = MagicMock()
    point.id = point_id
    point.payload = payload if payload is not None else _make_gate_payload()
    return point


def _make_service(mock_client: MagicMock | None = None) -> ConfidenceGateService:
    """Create a ConfidenceGateService with mocked Qdrant client."""
    service = ConfidenceGateService(host="localhost", port=6333)
    if mock_client is not None:
        service._client = mock_client
    return service


# ---------- Test evaluate_gate ----------


class TestEvaluateGate:
    """Tests for evaluate_gate method."""

    def test_tl1_always_advisory(self):
        """TL1 always returns advisory regardless of confidence score."""
        mock_client = MagicMock()
        service = _make_service(mock_client)
        trust_svc = MagicMock()
        trust_svc.get_effective_trust_level.return_value = 1
        service._trust_service = trust_svc

        decision = service.evaluate_gate("payment-api", 0.99)

        assert decision.permitted is False
        assert decision.action_type == "advisory"
        assert decision.trust_level == 1
        assert decision.confidence_score == 0.99

    def test_tl2_always_advisory(self):
        """TL2 always returns advisory regardless of confidence score."""
        mock_client = MagicMock()
        service = _make_service(mock_client)
        trust_svc = MagicMock()
        trust_svc.get_effective_trust_level.return_value = 2
        service._trust_service = trust_svc

        decision = service.evaluate_gate("payment-api", 1.0)

        assert decision.permitted is False
        assert decision.action_type == "advisory"
        assert decision.trust_level == 2

    def test_tl3_score_above_threshold_permitted(self):
        """TL3 with score >= 0.90 should be permitted."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)  # No custom thresholds
        service = _make_service(mock_client)
        trust_svc = MagicMock()
        trust_svc.get_effective_trust_level.return_value = 3
        service._trust_service = trust_svc

        decision = service.evaluate_gate("payment-api", 0.95)

        assert decision.permitted is True
        assert decision.action_type == "autonomous"
        assert decision.threshold == 0.90

    def test_tl3_score_below_threshold_advisory(self):
        """TL3 with score < 0.90 should be advisory."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        service = _make_service(mock_client)
        trust_svc = MagicMock()
        trust_svc.get_effective_trust_level.return_value = 3
        service._trust_service = trust_svc

        decision = service.evaluate_gate("payment-api", 0.85)

        assert decision.permitted is False
        assert decision.action_type == "advisory"
        assert decision.threshold == 0.90

    def test_tl3_score_exactly_at_threshold_permitted(self):
        """TL3 with score == 0.90 should be permitted (>=)."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        service = _make_service(mock_client)
        trust_svc = MagicMock()
        trust_svc.get_effective_trust_level.return_value = 3
        service._trust_service = trust_svc

        decision = service.evaluate_gate("payment-api", 0.90)

        assert decision.permitted is True

    def test_tl4_score_above_threshold_permitted(self):
        """TL4 with score >= 0.85 should be permitted."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        service = _make_service(mock_client)
        trust_svc = MagicMock()
        trust_svc.get_effective_trust_level.return_value = 4
        service._trust_service = trust_svc

        decision = service.evaluate_gate("payment-api", 0.85)

        assert decision.permitted is True
        assert decision.threshold == 0.85

    def test_tl4_score_below_threshold_advisory(self):
        """TL4 with score < 0.85 should be advisory."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        service = _make_service(mock_client)
        trust_svc = MagicMock()
        trust_svc.get_effective_trust_level.return_value = 4
        service._trust_service = trust_svc

        decision = service.evaluate_gate("payment-api", 0.80)

        assert decision.permitted is False
        assert decision.action_type == "advisory"

    def test_tl5_score_above_threshold_permitted(self):
        """TL5 with score >= 0.80 should be permitted."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        service = _make_service(mock_client)
        trust_svc = MagicMock()
        trust_svc.get_effective_trust_level.return_value = 5
        service._trust_service = trust_svc

        decision = service.evaluate_gate("payment-api", 0.80)

        assert decision.permitted is True
        assert decision.threshold == 0.80

    def test_tl5_score_below_threshold_advisory(self):
        """TL5 with score < 0.80 should be advisory."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        service = _make_service(mock_client)
        trust_svc = MagicMock()
        trust_svc.get_effective_trust_level.return_value = 5
        service._trust_service = trust_svc

        decision = service.evaluate_gate("payment-api", 0.75)

        assert decision.permitted is False

    def test_same_score_different_trust_levels_ac2(self):
        """AC#2: Same confidence (0.80) yields different decisions at TL3 vs TL4."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)

        # TL3 (threshold 0.90) — score 0.80 should be advisory
        service = _make_service(mock_client)
        trust_svc = MagicMock()
        trust_svc.get_effective_trust_level.return_value = 3
        service._trust_service = trust_svc
        decision_tl3 = service.evaluate_gate("svc-a", 0.80)
        assert decision_tl3.permitted is False
        assert decision_tl3.action_type == "advisory"

        # TL4 (threshold 0.85) — score 0.80 should still be advisory
        trust_svc.get_effective_trust_level.return_value = 4
        decision_tl4 = service.evaluate_gate("svc-a", 0.80)
        assert decision_tl4.permitted is False

        # TL5 (threshold 0.80) — score 0.80 should be permitted
        trust_svc.get_effective_trust_level.return_value = 5
        decision_tl5 = service.evaluate_gate("svc-a", 0.80)
        assert decision_tl5.permitted is True
        assert decision_tl5.action_type == "autonomous"

    def test_custom_thresholds_override_defaults(self):
        """Custom thresholds from Qdrant override defaults."""
        mock_client = MagicMock()
        point = _make_point(payload=_make_gate_payload(tl3=0.70))
        mock_client.scroll.return_value = ([point], None)
        service = _make_service(mock_client)
        trust_svc = MagicMock()
        trust_svc.get_effective_trust_level.return_value = 3
        service._trust_service = trust_svc

        decision = service.evaluate_gate("payment-api", 0.75)

        assert decision.permitted is True
        assert decision.threshold == 0.70

    def test_unconfigured_service_defaults_to_tl1_advisory(self):
        """Unconfigured service defaults to TL1 → always advisory."""
        mock_client = MagicMock()
        service = _make_service(mock_client)
        trust_svc = MagicMock()
        # get_effective_trust_level returns 1 for unconfigured service
        trust_svc.get_effective_trust_level.return_value = 1
        service._trust_service = trust_svc

        decision = service.evaluate_gate("unknown-service", 0.99)

        assert decision.permitted is False
        assert decision.trust_level == 1

    def test_service_name_preserved_in_decision(self):
        """Service name is correctly stored in GateDecision."""
        mock_client = MagicMock()
        service = _make_service(mock_client)
        trust_svc = MagicMock()
        trust_svc.get_effective_trust_level.return_value = 1
        service._trust_service = trust_svc

        decision = service.evaluate_gate("my-service", 0.5)

        assert decision.service_name == "my-service"


# ---------- Test get/set/list gate thresholds ----------


class TestGateThresholds:
    """Tests for threshold CRUD methods."""

    def test_get_gate_thresholds_defaults(self):
        """Returns default thresholds when no custom config exists."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        service = _make_service(mock_client)

        thresholds = service.get_gate_thresholds()

        assert len(thresholds) == 3
        assert thresholds[0].trust_level == 3
        assert thresholds[0].threshold == 0.90
        assert thresholds[1].trust_level == 4
        assert thresholds[1].threshold == 0.85
        assert thresholds[2].trust_level == 5
        assert thresholds[2].threshold == 0.80

    def test_get_gate_thresholds_custom(self):
        """Returns custom thresholds from Qdrant."""
        mock_client = MagicMock()
        point = _make_point(payload=_make_gate_payload(tl3=0.75, tl4=0.70, tl5=0.60))
        mock_client.scroll.return_value = ([point], None)
        service = _make_service(mock_client)

        thresholds = service.get_gate_thresholds()

        assert thresholds[0].threshold == 0.75
        assert thresholds[1].threshold == 0.70
        assert thresholds[2].threshold == 0.60

    def test_get_gate_threshold_single(self):
        """Get threshold for a specific trust level."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        service = _make_service(mock_client)

        config = service.get_gate_threshold(4)

        assert config.trust_level == 4
        assert config.threshold == 0.85

    def test_get_gate_threshold_invalid_level_raises(self):
        """Getting threshold for TL1 or TL2 raises ValueError."""
        mock_client = MagicMock()
        service = _make_service(mock_client)

        with pytest.raises(ValueError, match="Confidence gates only apply"):
            service.get_gate_threshold(1)

        with pytest.raises(ValueError, match="Confidence gates only apply"):
            service.get_gate_threshold(2)

    def test_set_gate_threshold_success(self):
        """Setting a valid threshold persists to Qdrant."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        service = _make_service(mock_client)

        config = service.set_gate_threshold(3, 0.85, "admin@test.com")

        assert config.trust_level == 3
        assert config.threshold == 0.85
        assert config.updated_by == "admin@test.com"
        mock_client.upsert.assert_called_once()

    def test_set_gate_threshold_updates_existing(self):
        """Updating existing threshold preserves other thresholds."""
        mock_client = MagicMock()
        existing_point = _make_point(payload=_make_gate_payload())
        mock_client.scroll.return_value = ([existing_point], None)
        service = _make_service(mock_client)

        config = service.set_gate_threshold(4, 0.75, "admin@test.com")

        assert config.threshold == 0.75
        # Verify upsert preserves existing point ID
        call_args = mock_client.upsert.call_args
        points = call_args.kwargs.get("points") or call_args[1].get("points")
        assert points[0].id == "gate-uuid-1"
        # Verify payload has updated TL4 but TL3 and TL5 preserved
        payload = points[0].payload
        assert payload["gate_threshold_tl4"] == 0.75
        assert payload["gate_threshold_tl3"] == 0.90
        assert payload["gate_threshold_tl5"] == 0.80

    def test_set_gate_threshold_invalid_level_raises(self):
        """Setting threshold for TL1-2 raises ValueError."""
        mock_client = MagicMock()
        service = _make_service(mock_client)

        with pytest.raises(ValueError, match="Confidence gates only apply"):
            service.set_gate_threshold(1, 0.90, "admin")

        with pytest.raises(ValueError, match="Confidence gates only apply"):
            service.set_gate_threshold(2, 0.90, "admin")

    def test_set_gate_threshold_below_zero_raises(self):
        """Threshold < 0.0 raises ValueError."""
        mock_client = MagicMock()
        service = _make_service(mock_client)

        with pytest.raises(ValueError, match="Threshold must be"):
            service.set_gate_threshold(3, -0.1, "admin")

    def test_set_gate_threshold_above_one_raises(self):
        """Threshold > 1.0 raises ValueError."""
        mock_client = MagicMock()
        service = _make_service(mock_client)

        with pytest.raises(ValueError, match="Threshold must be"):
            service.set_gate_threshold(3, 1.1, "admin")

    def test_set_gate_threshold_boolean_rejected(self):
        """Boolean values rejected as threshold."""
        mock_client = MagicMock()
        service = _make_service(mock_client)

        with pytest.raises(ValueError, match="Threshold must be"):
            service.set_gate_threshold(3, True, "admin")

    def test_set_gate_threshold_qdrant_error(self):
        """Qdrant failure raises ConfidenceGateError."""
        mock_client = MagicMock()
        mock_client.scroll.side_effect = Exception("connection refused")
        service = _make_service(mock_client)

        with pytest.raises(ConfidenceGateError, match="Failed to set"):
            service.set_gate_threshold(3, 0.85, "admin")


# ---------- Test normalize_confidence_score ----------


class TestNormalizeConfidenceScore:
    """Tests for the confidence score normalization utility."""

    def test_rca_percentage(self):
        """RCA confidence_percentage (0-100) normalized to 0.0-1.0."""
        findings = {
            "rca_hypothesis": {"confidence_percentage": 85, "confidence_level": "high"}
        }
        score = normalize_confidence_score(findings)
        assert score == 0.85

    def test_rca_text_level_only(self):
        """RCA with text level only maps to numeric."""
        findings = {"rca_hypothesis": {"confidence_level": "medium"}}
        score = normalize_confidence_score(findings)
        assert score == TEXT_CONFIDENCE_MAP["medium"]

    def test_rca_percentage_clamped(self):
        """RCA percentage > 100 clamped to 1.0."""
        findings = {"rca_hypothesis": {"confidence_percentage": 150}}
        score = normalize_confidence_score(findings)
        assert score == 1.0

    def test_rca_percentage_negative_clamped(self):
        """RCA percentage < 0 clamped to 0.0."""
        findings = {"rca_hypothesis": {"confidence_percentage": -10}}
        score = normalize_confidence_score(findings)
        assert score == 0.0

    def test_signal_correlation_highest(self):
        """Signal correlation uses highest confidence hypothesis."""
        findings = {
            "hypotheses": [
                {"confidence": "low"},
                {"confidence": "high"},
                {"confidence": "medium"},
            ]
        }
        score = normalize_confidence_score(findings)
        assert score == TEXT_CONFIDENCE_MAP["high"]

    def test_kb_match_confidence(self):
        """KB confidence_boost maps to numeric."""
        findings = {"confidence_boost": "high"}
        score = normalize_confidence_score(findings)
        assert score == TEXT_CONFIDENCE_MAP["high"]

    def test_missing_data_returns_zero(self):
        """Empty findings returns 0.0."""
        assert normalize_confidence_score({}) == 0.0
        assert normalize_confidence_score({"unrelated": "data"}) == 0.0

    def test_single_source_used_directly(self):
        """When only one source available, it's used directly (no weighting)."""
        findings = {"rca_hypothesis": {"confidence_percentage": 90}}
        score = normalize_confidence_score(findings)
        assert score == 0.90

    def test_composite_weighted_average(self):
        """Multiple sources produce weighted composite score."""
        findings = {
            "rca_hypothesis": {"confidence_percentage": 80},  # 0.80
            "hypotheses": [{"confidence": "high"}],  # 0.85
            "confidence_boost": "medium",  # 0.65
        }
        score = normalize_confidence_score(findings)

        # Expected: (0.80*0.5 + 0.85*0.3 + 0.65*0.2) / (0.5+0.3+0.2)
        expected = (0.80 * 0.5 + 0.85 * 0.3 + 0.65 * 0.2) / 1.0
        assert abs(score - expected) < 0.001

    def test_rca_boolean_percentage_ignored(self):
        """Boolean values for confidence_percentage are ignored."""
        findings = {"rca_hypothesis": {"confidence_percentage": True}}
        score = normalize_confidence_score(findings)
        assert score == 0.0

    def test_null_rca_data(self):
        """None rca_hypothesis handled gracefully."""
        findings = {"rca_hypothesis": None}
        score = normalize_confidence_score(findings)
        assert score == 0.0

    def test_empty_hypotheses_list(self):
        """Empty hypotheses list produces no signal correlation score."""
        findings = {"hypotheses": []}
        score = normalize_confidence_score(findings)
        assert score == 0.0


# ---------- Test format_gate_message ----------


class TestFormatGateMessage:
    """Tests for the gate message formatting utility."""

    def test_advisory_tl1_message(self):
        """TL1 produces advisory-only message."""
        decision = GateDecision(
            permitted=False,
            confidence_score=0.95,
            threshold=0.0,
            trust_level=1,
            action_type="advisory",
            reason="Advisory only",
            service_name="svc",
        )
        msg = format_gate_message(decision)
        assert "advisory-only" in msg
        assert "Trust level 1" in msg

    def test_advisory_tl2_message(self):
        """TL2 produces advisory-only message."""
        decision = GateDecision(
            permitted=False,
            confidence_score=0.95,
            threshold=0.0,
            trust_level=2,
            action_type="advisory",
            reason="Advisory only",
            service_name="svc",
        )
        msg = format_gate_message(decision)
        assert "advisory-only" in msg

    def test_permitted_message(self):
        """Permitted decision produces 'meets threshold' message."""
        decision = GateDecision(
            permitted=True,
            confidence_score=0.95,
            threshold=0.90,
            trust_level=3,
            action_type="autonomous",
            reason="ok",
            service_name="svc",
        )
        msg = format_gate_message(decision)
        assert "95%" in msg
        assert "meets threshold" in msg
        assert "90%" in msg

    def test_blocked_message(self):
        """Blocked decision produces 'below threshold' message with advisory."""
        decision = GateDecision(
            permitted=False,
            confidence_score=0.80,
            threshold=0.85,
            trust_level=4,
            action_type="advisory",
            reason="below",
            service_name="svc",
        )
        msg = format_gate_message(decision)
        assert "80%" in msg
        assert "below threshold" in msg
        assert "85%" in msg
        assert "advisory only" in msg


# ---------- Test error handling ----------


class TestErrorHandling:
    """Tests for error conditions and safe defaults."""

    def test_qdrant_unreachable_uses_defaults(self):
        """When Qdrant is unreachable, default thresholds are used."""
        mock_client = MagicMock()
        mock_client.scroll.side_effect = Exception("connection refused")
        service = _make_service(mock_client)
        trust_svc = MagicMock()
        trust_svc.get_effective_trust_level.return_value = 3
        service._trust_service = trust_svc

        # evaluate_gate should still work with defaults
        decision = service.evaluate_gate("payment-api", 0.95)
        assert decision.permitted is True
        assert decision.threshold == 0.90

    def test_trust_service_error_defaults_to_tl1(self):
        """TrustLevelService error defaults to TL1 (advisory)."""
        from beeper_ui.services.trust_level_service import TrustLevelServiceError

        mock_client = MagicMock()
        service = _make_service(mock_client)
        trust_svc = MagicMock()
        trust_svc.get_effective_trust_level.side_effect = TrustLevelServiceError("fail")
        service._trust_service = trust_svc

        decision = service.evaluate_gate("payment-api", 0.99)
        assert decision.permitted is False
        assert decision.trust_level == 1

    def test_close_cleans_up(self):
        """Close shuts down both Qdrant client and trust service."""
        mock_client = MagicMock()
        service = _make_service(mock_client)
        trust_svc = MagicMock()
        service._trust_service = trust_svc

        service.close()

        mock_client.close.assert_called_once()
        trust_svc.close.assert_called_once()
        assert service._client is None
        assert service._trust_service is None
