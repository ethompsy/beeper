"""Tests for AdaptiveThresholdService."""

from unittest.mock import MagicMock, patch

import pytest

from beeper_ui.services.adaptive_threshold_service import (
    DEFAULT_ALERT_THRESHOLD,
    LOWER_PCT,
    MIN_FEEDBACK_SAMPLE,
    RAISE_PCT,
    AdaptiveThresholdError,
    AdaptiveThresholdService,
    ThresholdAdjustment,
)


class TestThresholdAdjustmentDataclass:
    """Tests for ThresholdAdjustment.from_qdrant."""

    def test_from_qdrant_full_payload(self) -> None:
        payload = {
            "adjustment_id": "adj-001",
            "service_name": "payments",
            "previous_threshold": 3.0,
            "new_threshold": 3.45,
            "adjustment_pct": 15.0,
            "direction": "increased",
            "status": "applied",
            "reason": "Raised threshold 15%: 6/10 marked not-an-issue",
            "feedback_window": 10,
            "not_an_issue_count": 6,
            "accurate_count": 3,
            "inaccurate_count": 1,
            "trust_level": 3,
            "created_at": "2026-03-16T10:00:00+00:00",
            "applied_at": "2026-03-16T10:00:00+00:00",
            "applied_by": "system",
            "rejected_at": None,
            "rejected_by": None,
        }
        adj = ThresholdAdjustment.from_qdrant(payload)
        assert adj.adjustment_id == "adj-001"
        assert adj.service_name == "payments"
        assert adj.previous_threshold == 3.0
        assert adj.new_threshold == 3.45
        assert adj.status == "applied"
        assert adj.trust_level == 3

    def test_from_qdrant_empty_payload(self) -> None:
        adj = ThresholdAdjustment.from_qdrant({})
        assert adj.adjustment_id == ""
        assert adj.service_name == ""
        assert adj.previous_threshold == DEFAULT_ALERT_THRESHOLD
        assert adj.status == "pending"


class TestGetServiceFeedbackSummary:
    """Tests for feedback aggregation from investigations collection."""

    def test_returns_counts_for_each_feedback_type(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()

        # Create mock points with feedback
        points = []
        for fb_type in ["accurate", "accurate", "not_an_issue", "inaccurate"]:
            p = MagicMock()
            p.payload = {"service": "payments", "investigation_feedback": fb_type}
            points.append(p)

        mock_client.scroll.return_value = (points, None)
        svc._client = mock_client

        summary = svc.get_service_feedback_summary("payments")
        assert summary["total"] == 4
        assert summary["accurate"] == 2
        assert summary["not_an_issue"] == 1
        assert summary["inaccurate"] == 1

    def test_skips_investigations_without_feedback(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()

        p1 = MagicMock()
        p1.payload = {"service": "payments", "investigation_feedback": "accurate"}
        p2 = MagicMock()
        p2.payload = {"service": "payments"}  # No feedback
        p3 = MagicMock()
        p3.payload = None  # No payload at all

        mock_client.scroll.return_value = ([p1, p2, p3], None)
        svc._client = mock_client

        summary = svc.get_service_feedback_summary("payments")
        assert summary["total"] == 1
        assert summary["accurate"] == 1

    def test_empty_results(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        svc._client = mock_client

        summary = svc.get_service_feedback_summary("payments")
        assert summary == {"total": 0, "accurate": 0, "inaccurate": 0, "not_an_issue": 0}

    def test_qdrant_failure_raises_error(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()
        mock_client.scroll.side_effect = Exception("Connection refused")
        svc._client = mock_client

        with pytest.raises(AdaptiveThresholdError, match="Connection refused"):
            svc.get_service_feedback_summary("payments")

    def test_pagination_across_multiple_pages(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()

        p1 = MagicMock()
        p1.payload = {"investigation_feedback": "accurate"}
        p2 = MagicMock()
        p2.payload = {"investigation_feedback": "not_an_issue"}

        # First page returns 1 result with offset, second page returns 1 with no offset
        mock_client.scroll.side_effect = [
            ([p1], "offset-2"),
            ([p2], None),
        ]
        svc._client = mock_client

        summary = svc.get_service_feedback_summary("payments")
        assert summary["total"] == 2
        assert mock_client.scroll.call_count == 2


class TestCalculateThresholdAdjustment:
    """Tests for the pure calculation logic."""

    def test_insufficient_feedback_returns_none(self) -> None:
        result = AdaptiveThresholdService.calculate_threshold_adjustment(
            "payments", 3.0, {"total": 9, "accurate": 5, "inaccurate": 2, "not_an_issue": 2}
        )
        assert result is None

    def test_zero_feedback_returns_none(self) -> None:
        result = AdaptiveThresholdService.calculate_threshold_adjustment(
            "payments", 3.0, {"total": 0, "accurate": 0, "inaccurate": 0, "not_an_issue": 0}
        )
        assert result is None

    def test_high_not_an_issue_rate_raises_threshold(self) -> None:
        result = AdaptiveThresholdService.calculate_threshold_adjustment(
            "payments", 3.0, {"total": 10, "accurate": 2, "inaccurate": 2, "not_an_issue": 6}
        )
        assert result is not None
        assert result.direction == "increased"
        assert result.new_threshold == round(3.0 * (1 + RAISE_PCT), 2)
        assert result.adjustment_pct == round(RAISE_PCT * 100, 1)
        assert "6/10" in result.reason
        assert "not-an-issue" in result.reason

    def test_high_accurate_rate_lowers_threshold(self) -> None:
        result = AdaptiveThresholdService.calculate_threshold_adjustment(
            "payments", 3.0, {"total": 10, "accurate": 8, "inaccurate": 1, "not_an_issue": 1}
        )
        assert result is not None
        assert result.direction == "decreased"
        assert result.new_threshold == round(3.0 * (1 - LOWER_PCT), 2)
        assert result.adjustment_pct == round(LOWER_PCT * 100, 1)
        assert "8/10" in result.reason
        assert "accurate" in result.reason

    def test_mixed_feedback_returns_none(self) -> None:
        result = AdaptiveThresholdService.calculate_threshold_adjustment(
            "payments", 3.0, {"total": 10, "accurate": 4, "inaccurate": 3, "not_an_issue": 3}
        )
        assert result is None

    def test_not_an_issue_takes_priority_over_accurate(self) -> None:
        # If both rates are high, not-an-issue check comes first
        result = AdaptiveThresholdService.calculate_threshold_adjustment(
            "payments", 3.0, {"total": 10, "accurate": 7, "inaccurate": 0, "not_an_issue": 5}
        )
        # not_an_issue_rate = 0.5 >= 0.5 → raise threshold wins
        assert result is not None
        assert result.direction == "increased"

    def test_boundary_not_an_issue_rate(self) -> None:
        # Exactly at threshold (50%)
        result = AdaptiveThresholdService.calculate_threshold_adjustment(
            "payments", 3.0, {"total": 10, "accurate": 3, "inaccurate": 2, "not_an_issue": 5}
        )
        assert result is not None
        assert result.direction == "increased"

    def test_boundary_accurate_rate(self) -> None:
        # Exactly at threshold (70%)
        result = AdaptiveThresholdService.calculate_threshold_adjustment(
            "payments", 3.0, {"total": 10, "accurate": 7, "inaccurate": 2, "not_an_issue": 1}
        )
        assert result is not None
        assert result.direction == "decreased"

    def test_exactly_min_sample(self) -> None:
        feedback = {
            "total": MIN_FEEDBACK_SAMPLE,
            "accurate": 0,
            "inaccurate": 0,
            "not_an_issue": MIN_FEEDBACK_SAMPLE,
        }
        result = AdaptiveThresholdService.calculate_threshold_adjustment(
            "payments", 3.0, feedback
        )
        assert result is not None
        assert result.direction == "increased"

    def test_reason_includes_human_readable_evidence(self) -> None:
        result = AdaptiveThresholdService.calculate_threshold_adjustment(
            "api-gateway", 4.0, {"total": 20, "accurate": 3, "inaccurate": 5, "not_an_issue": 12}
        )
        assert result is not None
        assert "12/20" in result.reason
        assert result.service_name == "api-gateway"

    def test_adjustment_preserves_service_name(self) -> None:
        result = AdaptiveThresholdService.calculate_threshold_adjustment(
            "my-service", 3.0, {"total": 10, "accurate": 8, "inaccurate": 1, "not_an_issue": 1}
        )
        assert result is not None
        assert result.service_name == "my-service"


class TestGetCurrentThreshold:
    """Tests for reading per-service threshold from Qdrant."""

    def test_returns_stored_threshold(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()
        point = MagicMock()
        point.payload = {"service_name": "payments", "alert_threshold": 4.5}
        mock_client.scroll.return_value = ([point], None)
        svc._client = mock_client

        result = svc.get_current_threshold("payments")
        assert result == 4.5

    def test_returns_default_when_no_record(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        svc._client = mock_client

        result = svc.get_current_threshold("payments")
        assert result == DEFAULT_ALERT_THRESHOLD

    def test_returns_default_when_field_missing(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()
        point = MagicMock()
        point.payload = {"service_name": "payments"}  # No alert_threshold
        mock_client.scroll.return_value = ([point], None)
        svc._client = mock_client

        result = svc.get_current_threshold("payments")
        assert result == DEFAULT_ALERT_THRESHOLD

    def test_qdrant_failure_raises_error(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()
        mock_client.scroll.side_effect = Exception("timeout")
        svc._client = mock_client

        with pytest.raises(AdaptiveThresholdError, match="timeout"):
            svc.get_current_threshold("payments")


class TestEvaluateService:
    """Tests for the full evaluation orchestration."""

    def _make_feedback_points(self, feedback_list: list[str]) -> list[MagicMock]:
        points = []
        for fb in feedback_list:
            p = MagicMock()
            p.payload = {"investigation_feedback": fb}
            points.append(p)
        return points

    @patch("beeper_ui.services.adaptive_threshold_service.TrustLevelService")
    def test_tl3_auto_applies(self, mock_tl_cls: MagicMock) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()
        svc._client = mock_client

        # Mock feedback: 6/10 not-an-issue
        feedback_points = self._make_feedback_points(
            ["not_an_issue"] * 6 + ["accurate"] * 3 + ["inaccurate"] * 1
        )
        # Mock current threshold
        threshold_point = MagicMock()
        threshold_point.payload = {"service_name": "payments", "alert_threshold": 3.0}
        threshold_point.id = "point-1"

        # Scroll calls: feedback, current threshold, update threshold check, store adjustment
        mock_client.scroll.side_effect = [
            (feedback_points, None),  # feedback
            ([threshold_point], None),  # current threshold
            ([threshold_point], None),  # _update_service_threshold lookup
        ]

        # Mock trust level = 3
        mock_tl_instance = MagicMock()
        mock_tl_instance.get_effective_trust_level.return_value = 3
        mock_tl_cls.return_value = mock_tl_instance

        result = svc.evaluate_service("payments")
        assert result is not None
        assert result.status == "applied"
        assert result.applied_by == "system"
        assert result.trust_level == 3
        assert result.direction == "increased"

        # Verify threshold was updated
        mock_client.upsert.assert_called()

    @patch("beeper_ui.services.adaptive_threshold_service.TrustLevelService")
    def test_tl1_returns_pending(self, mock_tl_cls: MagicMock) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()
        svc._client = mock_client

        feedback_points = self._make_feedback_points(
            ["not_an_issue"] * 6 + ["accurate"] * 3 + ["inaccurate"] * 1
        )
        threshold_point = MagicMock()
        threshold_point.payload = {"service_name": "payments", "alert_threshold": 3.0}
        threshold_point.id = "point-1"

        mock_client.scroll.side_effect = [
            (feedback_points, None),
            ([threshold_point], None),
        ]

        mock_tl_instance = MagicMock()
        mock_tl_instance.get_effective_trust_level.return_value = 1
        mock_tl_cls.return_value = mock_tl_instance

        result = svc.evaluate_service("payments")
        assert result is not None
        assert result.status == "pending"
        assert result.applied_at is None
        assert result.trust_level == 1

    @patch("beeper_ui.services.adaptive_threshold_service.TrustLevelService")
    def test_tl2_returns_pending(self, mock_tl_cls: MagicMock) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()
        svc._client = mock_client

        feedback_points = self._make_feedback_points(
            ["not_an_issue"] * 8 + ["accurate"] * 2
        )
        threshold_point = MagicMock()
        threshold_point.payload = {"service_name": "svc", "alert_threshold": 3.0}
        threshold_point.id = "pt-1"

        mock_client.scroll.side_effect = [
            (feedback_points, None),
            ([threshold_point], None),
        ]

        mock_tl_instance = MagicMock()
        mock_tl_instance.get_effective_trust_level.return_value = 2
        mock_tl_cls.return_value = mock_tl_instance

        result = svc.evaluate_service("svc")
        assert result is not None
        assert result.status == "pending"

    def test_insufficient_feedback_returns_none(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()
        svc._client = mock_client

        feedback_points = self._make_feedback_points(["accurate"] * 5)
        threshold_point = MagicMock()
        threshold_point.payload = {"service_name": "payments", "alert_threshold": 3.0}

        mock_client.scroll.side_effect = [
            (feedback_points, None),
            ([threshold_point], None),
        ]

        result = svc.evaluate_service("payments")
        assert result is None


class TestGetAdjustmentHistory:
    """Tests for adjustment history retrieval."""

    def test_returns_sorted_adjustments(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()

        p1 = MagicMock()
        p1.payload = {
            "adjustment_id": "a1", "service_name": "svc1",
            "created_at": "2026-03-15T10:00:00", "status": "applied",
            "previous_threshold": 3.0, "new_threshold": 3.45,
        }
        p2 = MagicMock()
        p2.payload = {
            "adjustment_id": "a2", "service_name": "svc1",
            "created_at": "2026-03-16T10:00:00", "status": "pending",
            "previous_threshold": 3.45, "new_threshold": 3.97,
        }
        mock_client.scroll.return_value = ([p1, p2], None)
        svc._client = mock_client

        result = svc.get_adjustment_history()
        assert len(result) == 2
        assert result[0].created_at > result[1].created_at

    def test_filter_by_service(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        svc._client = mock_client

        svc.get_adjustment_history(service_name="payments")
        call_args = mock_client.scroll.call_args
        assert call_args.kwargs["scroll_filter"] is not None

    def test_no_filter_returns_all(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        svc._client = mock_client

        svc.get_adjustment_history()
        call_args = mock_client.scroll.call_args
        assert call_args.kwargs["scroll_filter"] is None

    def test_qdrant_failure_raises_error(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()
        mock_client.scroll.side_effect = Exception("timeout")
        svc._client = mock_client

        with pytest.raises(AdaptiveThresholdError):
            svc.get_adjustment_history()


class TestApplyPendingAdjustment:
    """Tests for applying pending adjustments."""

    def test_applies_and_updates_threshold(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()

        adj_point = MagicMock()
        adj_point.id = "point-adj-1"
        adj_point.payload = {
            "adjustment_id": "adj-001",
            "service_name": "payments",
            "status": "pending",
            "previous_threshold": 3.0,
            "new_threshold": 3.45,
        }

        svc_point = MagicMock()
        svc_point.id = "point-svc-1"
        svc_point.payload = {"service_name": "payments", "alert_threshold": 3.0}

        mock_client.scroll.side_effect = [
            ([adj_point], None),  # Find adjustment
            ([svc_point], None),  # _update_service_threshold
        ]
        svc._client = mock_client

        result = svc.apply_pending_adjustment("adj-001", "admin-user")
        assert result.status == "applied"
        assert result.applied_by == "admin-user"
        assert result.applied_at is not None

    def test_not_found_raises_error(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        svc._client = mock_client

        with pytest.raises(AdaptiveThresholdError, match="not found"):
            svc.apply_pending_adjustment("nonexistent", "admin")

    def test_not_pending_raises_error(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()
        point = MagicMock()
        point.id = "p1"
        point.payload = {"adjustment_id": "adj-001", "status": "applied"}
        mock_client.scroll.return_value = ([point], None)
        svc._client = mock_client

        with pytest.raises(AdaptiveThresholdError, match="not pending"):
            svc.apply_pending_adjustment("adj-001", "admin")


class TestRejectPendingAdjustment:
    """Tests for rejecting pending adjustments."""

    def test_rejects_successfully(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()

        adj_point = MagicMock()
        adj_point.id = "point-adj-1"
        adj_point.payload = {
            "adjustment_id": "adj-002",
            "service_name": "api-gateway",
            "status": "pending",
            "previous_threshold": 3.0,
            "new_threshold": 3.45,
        }
        mock_client.scroll.return_value = ([adj_point], None)
        svc._client = mock_client

        result = svc.reject_pending_adjustment("adj-002", "admin-user")
        assert result.status == "rejected"
        assert result.rejected_by == "admin-user"
        assert result.rejected_at is not None

    def test_not_found_raises_error(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        svc._client = mock_client

        with pytest.raises(AdaptiveThresholdError, match="not found"):
            svc.reject_pending_adjustment("nonexistent", "admin")

    def test_not_pending_raises_error(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()
        point = MagicMock()
        point.id = "p1"
        point.payload = {"adjustment_id": "adj-002", "status": "rejected"}
        mock_client.scroll.return_value = ([point], None)
        svc._client = mock_client

        with pytest.raises(AdaptiveThresholdError, match="not pending"):
            svc.reject_pending_adjustment("adj-002", "admin")


class TestServiceLifecycle:
    """Tests for service initialization and cleanup."""

    def test_close_closes_client(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        mock_client = MagicMock()
        svc._client = mock_client

        svc.close()
        mock_client.close.assert_called_once()
        assert svc._client is None

    def test_close_when_no_client(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        svc.close()  # Should not raise

    def test_lazy_initialization(self) -> None:
        svc = AdaptiveThresholdService(host="localhost")
        assert svc._client is None
        # Accessing client property triggers initialization
        with patch("beeper_ui.services.adaptive_threshold_service.QdrantClient"):
            _ = svc.client
            assert svc._client is not None
