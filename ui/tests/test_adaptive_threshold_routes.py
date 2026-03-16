"""Tests for adaptive threshold tuning routes in trust_settings.py."""

from unittest.mock import MagicMock, patch

from beeper_ui.services.adaptive_threshold_service import (
    AdaptiveThresholdError,
    ThresholdAdjustment,
)

ADAPTIVE_SVC_PATCH = "beeper_ui.routes.trust_settings._get_adaptive_service"

# Valid UUID for test adjustment IDs (must pass _UUID_RE validation)
TEST_UUID = "550e8400-e29b-41d4-a716-446655440000"
TEST_UUID_2 = "550e8400-e29b-41d4-a716-446655440999"


def _make_adjustment(
    adjustment_id: str = "adj-001",
    service_name: str = "payments",
    previous_threshold: float = 3.0,
    new_threshold: float = 3.45,
    adjustment_pct: float = 15.0,
    direction: str = "increased",
    status: str = "applied",
    reason: str = "Raised threshold 15%: 6/10 marked not-an-issue",
    trust_level: int = 3,
    created_at: str = "2026-03-16T10:00:00+00:00",
    applied_at: str | None = "2026-03-16T10:00:00+00:00",
    applied_by: str | None = "system",
) -> ThresholdAdjustment:
    return ThresholdAdjustment(
        adjustment_id=adjustment_id,
        service_name=service_name,
        previous_threshold=previous_threshold,
        new_threshold=new_threshold,
        adjustment_pct=adjustment_pct,
        direction=direction,
        status=status,
        reason=reason,
        feedback_window=10,
        not_an_issue_count=6,
        accurate_count=3,
        inaccurate_count=1,
        trust_level=trust_level,
        created_at=created_at,
        applied_at=applied_at,
        applied_by=applied_by,
    )


class TestThresholdHistoryPage:
    """Tests for GET /settings/trust/history."""

    def test_user_can_view_history_page(self, user_client: MagicMock) -> None:
        response = user_client.get("/settings/trust/history")
        assert response.status_code == 200
        assert b"Threshold Adjustment History" in response.data

    def test_admin_can_view_history_page(self, admin_client: MagicMock) -> None:
        response = admin_client.get("/settings/trust/history")
        assert response.status_code == 200
        assert b"Threshold Adjustment History" in response.data


class TestThresholdHistoryContent:
    """Tests for GET /settings/trust/history/content (HTMX partial)."""

    def test_returns_adjustments_table(self, user_client: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_adjustment_history.return_value = [
            _make_adjustment(),
            _make_adjustment(
                adjustment_id="adj-002",
                status="pending",
                direction="decreased",
                applied_at=None,
                applied_by=None,
            ),
        ]

        with patch(ADAPTIVE_SVC_PATCH, return_value=mock_svc):
            response = user_client.get("/settings/trust/history/content")

        assert response.status_code == 200
        assert b"payments" in response.data
        assert b"Applied" in response.data
        assert b"Pending" in response.data

    def test_empty_history(self, user_client: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_adjustment_history.return_value = []

        with patch(ADAPTIVE_SVC_PATCH, return_value=mock_svc):
            response = user_client.get("/settings/trust/history/content")

        assert response.status_code == 200
        assert b"No threshold adjustments" in response.data

    def test_qdrant_error_shows_error_message(self, user_client: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_adjustment_history.side_effect = AdaptiveThresholdError("timeout")

        with patch(ADAPTIVE_SVC_PATCH, return_value=mock_svc):
            response = user_client.get("/settings/trust/history/content")

        assert response.status_code == 200
        assert b"Unable to load adjustment history" in response.data

    def test_pending_adjustments_show_action_buttons(self, user_client: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.get_adjustment_history.return_value = [
            _make_adjustment(status="pending", applied_at=None, applied_by=None),
        ]

        with patch(ADAPTIVE_SVC_PATCH, return_value=mock_svc):
            response = user_client.get("/settings/trust/history/content")

        assert response.status_code == 200
        assert b"Apply" in response.data
        assert b"Reject" in response.data


class TestApplyAdjustment:
    """Tests for POST /settings/trust/adjustments/<id>/apply."""

    def test_admin_can_apply(self, admin_client: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.apply_pending_adjustment.return_value = _make_adjustment(
            status="applied", applied_by="admin"
        )

        with patch(ADAPTIVE_SVC_PATCH, return_value=mock_svc):
            response = admin_client.post(f"/settings/trust/adjustments/{TEST_UUID}/apply")

        assert response.status_code == 200
        assert b"Applied" in response.data

    def test_user_cannot_apply(self, user_client: MagicMock) -> None:
        response = user_client.post(f"/settings/trust/adjustments/{TEST_UUID}/apply")
        assert response.status_code == 403

    def test_not_found_returns_error(self, admin_client: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.apply_pending_adjustment.side_effect = AdaptiveThresholdError("not found")

        with patch(ADAPTIVE_SVC_PATCH, return_value=mock_svc):
            response = admin_client.post(f"/settings/trust/adjustments/{TEST_UUID_2}/apply")

        assert response.status_code == 400
        assert b"not found" in response.data

    def test_service_is_closed(self, admin_client: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.apply_pending_adjustment.return_value = _make_adjustment()

        with patch(ADAPTIVE_SVC_PATCH, return_value=mock_svc):
            admin_client.post(f"/settings/trust/adjustments/{TEST_UUID}/apply")

        mock_svc.close.assert_called_once()


class TestRejectAdjustment:
    """Tests for POST /settings/trust/adjustments/<id>/reject."""

    def test_admin_can_reject(self, admin_client: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.reject_pending_adjustment.return_value = _make_adjustment(
            status="rejected"
        )

        with patch(ADAPTIVE_SVC_PATCH, return_value=mock_svc):
            response = admin_client.post(f"/settings/trust/adjustments/{TEST_UUID}/reject")

        assert response.status_code == 200
        assert b"Rejected" in response.data

    def test_user_cannot_reject(self, user_client: MagicMock) -> None:
        response = user_client.post(f"/settings/trust/adjustments/{TEST_UUID}/reject")
        assert response.status_code == 403

    def test_not_found_returns_error(self, admin_client: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.reject_pending_adjustment.side_effect = AdaptiveThresholdError("not found")

        with patch(ADAPTIVE_SVC_PATCH, return_value=mock_svc):
            response = admin_client.post(f"/settings/trust/adjustments/{TEST_UUID_2}/reject")

        assert response.status_code == 400
        assert b"not found" in response.data


class TestEvaluateServiceThreshold:
    """Tests for POST /settings/trust/adaptive/evaluate/<service_name>."""

    def test_admin_can_evaluate(self, admin_client: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.evaluate_service.return_value = _make_adjustment()

        with patch(ADAPTIVE_SVC_PATCH, return_value=mock_svc):
            response = admin_client.post("/settings/trust/adaptive/evaluate/payments")

        assert response.status_code == 200
        assert b"payments" in response.data

    def test_user_cannot_evaluate(self, user_client: MagicMock) -> None:
        response = user_client.post("/settings/trust/adaptive/evaluate/payments")
        assert response.status_code == 403

    def test_no_adjustment_needed(self, admin_client: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.evaluate_service.return_value = None

        with patch(ADAPTIVE_SVC_PATCH, return_value=mock_svc):
            response = admin_client.post("/settings/trust/adaptive/evaluate/payments")

        assert response.status_code == 200
        assert b"No adjustment needed" in response.data

    def test_invalid_service_name(self, admin_client: MagicMock) -> None:
        response = admin_client.post("/settings/trust/adaptive/evaluate/invalid name!")
        assert response.status_code == 400
        assert b"Invalid service name" in response.data

    def test_qdrant_error_returns_503(self, admin_client: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.evaluate_service.side_effect = AdaptiveThresholdError("timeout")

        with patch(ADAPTIVE_SVC_PATCH, return_value=mock_svc):
            response = admin_client.post("/settings/trust/adaptive/evaluate/payments")

        assert response.status_code == 503
        assert b"Evaluation failed" in response.data

    def test_auto_applied_shows_badge(self, admin_client: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.evaluate_service.return_value = _make_adjustment(
            status="applied", trust_level=4
        )

        with patch(ADAPTIVE_SVC_PATCH, return_value=mock_svc):
            response = admin_client.post("/settings/trust/adaptive/evaluate/payments")

        assert response.status_code == 200
        assert b"Auto-applied" in response.data

    def test_pending_shows_badge(self, admin_client: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.evaluate_service.return_value = _make_adjustment(
            status="pending", trust_level=1, applied_at=None, applied_by=None
        )

        with patch(ADAPTIVE_SVC_PATCH, return_value=mock_svc):
            response = admin_client.post("/settings/trust/adaptive/evaluate/payments")

        assert response.status_code == 200
        assert b"Pending admin approval" in response.data

    def test_service_is_closed(self, admin_client: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.evaluate_service.return_value = None

        with patch(ADAPTIVE_SVC_PATCH, return_value=mock_svc):
            admin_client.post("/settings/trust/adaptive/evaluate/payments")

        mock_svc.close.assert_called_once()


class TestAdaptiveTuningSection:
    """Tests for GET /settings/trust/adaptive/tuning (HTMX partial)."""

    def test_user_can_view_tuning_section(self, user_client: MagicMock) -> None:
        mock_tl_svc = MagicMock()
        svc1 = MagicMock()
        svc1.service_name = "payments"
        svc2 = MagicMock()
        svc2.service_name = "api-gateway"
        mock_tl_svc.get_all_trust_levels.return_value = [svc1, svc2]

        patch_path = "beeper_ui.routes.trust_settings._get_trust_level_service"
        with patch(patch_path, return_value=mock_tl_svc):
            response = user_client.get("/settings/trust/adaptive/tuning")

        assert response.status_code == 200
        assert b"payments" in response.data
        assert b"api-gateway" in response.data
        assert b"Evaluate" in response.data

    def test_empty_services_shows_message(self, user_client: MagicMock) -> None:
        mock_tl_svc = MagicMock()
        mock_tl_svc.get_all_trust_levels.return_value = []

        patch_path = "beeper_ui.routes.trust_settings._get_trust_level_service"
        with patch(patch_path, return_value=mock_tl_svc):
            response = user_client.get("/settings/trust/adaptive/tuning")

        assert response.status_code == 200
        assert b"No services configured" in response.data

    def test_service_is_closed(self, user_client: MagicMock) -> None:
        mock_tl_svc = MagicMock()
        mock_tl_svc.get_all_trust_levels.return_value = []

        patch_path = "beeper_ui.routes.trust_settings._get_trust_level_service"
        with patch(patch_path, return_value=mock_tl_svc):
            user_client.get("/settings/trust/adaptive/tuning")

        mock_tl_svc.close.assert_called_once()


class TestApplyRejectUuidValidation:
    """Tests for UUID validation on adjustment ID parameters."""

    def test_apply_rejects_non_uuid_id(self, admin_client: MagicMock) -> None:
        response = admin_client.post("/settings/trust/adjustments/not-a-uuid/apply")
        assert response.status_code == 400
        assert b"Invalid adjustment ID" in response.data

    def test_reject_rejects_non_uuid_id(self, admin_client: MagicMock) -> None:
        response = admin_client.post("/settings/trust/adjustments/hello-world/reject")
        assert response.status_code == 400
        assert b"Invalid adjustment ID" in response.data

    def test_apply_accepts_valid_uuid(self, admin_client: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.apply_pending_adjustment.return_value = _make_adjustment()

        with patch(ADAPTIVE_SVC_PATCH, return_value=mock_svc):
            response = admin_client.post(
                f"/settings/trust/adjustments/{TEST_UUID}/apply"
            )

        assert response.status_code == 200

    def test_reject_accepts_valid_uuid(self, admin_client: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.reject_pending_adjustment.return_value = _make_adjustment(status="rejected")

        with patch(ADAPTIVE_SVC_PATCH, return_value=mock_svc):
            response = admin_client.post(
                f"/settings/trust/adjustments/{TEST_UUID}/reject"
            )

        assert response.status_code == 200


class TestSettingsPageHasHistoryLink:
    """Test that the settings page includes the history link."""

    def test_settings_page_has_history_link(self, user_client: MagicMock) -> None:
        # Mock the trust level service that settings page uses
        mock_svc = MagicMock()
        mock_svc.get_all_trust_levels.return_value = []

        patch_path = (
            "beeper_ui.routes.trust_settings._get_trust_level_service"
        )
        with patch(patch_path, return_value=mock_svc):
            response = user_client.get("/settings/trust/")

        assert response.status_code == 200
        assert b"Adjustment History" in response.data
        assert b"Adaptive Alert Threshold" in response.data
