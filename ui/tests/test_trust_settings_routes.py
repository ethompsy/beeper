"""Tests for trust settings UI page routes."""

from unittest.mock import MagicMock, patch

from beeper_ui.services.trust_level_service import (
    TrustLevelConfig,
    TrustLevelServiceError,
)

# ---------- Helpers ----------


def _make_config(
    service_name: str = "payment-api",
    trust_level: int = 3,
    updated_by: str = "admin@test.com",
    updated_at: str = "2026-03-15T10:00:00+00:00",
    reason: str | None = "Proven reliable",
    previous_level: int | None = 2,
) -> TrustLevelConfig:
    return TrustLevelConfig(
        service_name=service_name,
        trust_level=trust_level,
        updated_by=updated_by,
        updated_at=updated_at,
        reason=reason,
        previous_level=previous_level,
    )


SERVICE_PATCH = "beeper_ui.routes.trust_settings._get_trust_level_service"


# ---------- GET /settings/trust/ ----------


class TestTrustSettingsPage:
    """Tests for GET /settings/trust/ UI page."""

    def test_renders_page_with_trusts(self, user_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_all_trust_levels.return_value = [
            _make_config("svc-a", 2),
            _make_config("svc-b", 4),
        ]

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = user_client.get("/settings/trust/")

        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Trust Level Configuration" in html
        assert "svc-a" in html
        assert "svc-b" in html

    def test_renders_empty_state(self, user_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_all_trust_levels.return_value = []

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = user_client.get("/settings/trust/")

        assert resp.status_code == 200
        html = resp.data.decode()
        assert "No services have been configured" in html

    def test_renders_error_state(self, user_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_all_trust_levels.side_effect = TrustLevelServiceError("fail")

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = user_client.get("/settings/trust/")

        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Unable to load trust level data" in html

    def test_htmx_returns_partial(self, user_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_all_trust_levels.return_value = [_make_config("svc-a", 2)]

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = user_client.get(
                "/settings/trust/",
                headers={"HX-Request": "true"},
            )

        assert resp.status_code == 200
        html = resp.data.decode()
        # Partial should not include full page chrome
        assert "<!DOCTYPE html>" not in html
        assert "svc-a" in html

    def test_user_role_can_access(self, user_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_all_trust_levels.return_value = []

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = user_client.get("/settings/trust/")

        assert resp.status_code == 200

    def test_admin_role_can_access(self, admin_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_all_trust_levels.return_value = []

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = admin_client.get("/settings/trust/")

        assert resp.status_code == 200

    def test_trust_level_reference_table_shown(self, user_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_all_trust_levels.return_value = []

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = user_client.get("/settings/trust/")

        html = resp.data.decode()
        assert "Trust Level Reference" in html
        assert "Advisory Only" in html
        assert "Fully Autonomous" in html


# ---------- POST /settings/trust/<service_name>/update ----------


class TestUpdateTrustLevel:
    """Tests for POST /settings/trust/<service_name>/update."""

    def test_admin_can_update(self, admin_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.set_trust_level.return_value = _make_config("payment-api", 4, previous_level=3)

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = admin_client.post(
                "/settings/trust/payment-api/update",
                data={"trust_level": "4", "reason": "Earned it"},
            )

        assert resp.status_code == 200
        html = resp.data.decode()
        assert "updated successfully" in html

    def test_user_cannot_update(self, user_client: MagicMock) -> None:
        resp = user_client.post(
            "/settings/trust/payment-api/update",
            data={"trust_level": "4"},
        )
        assert resp.status_code == 403

    def test_rejects_invalid_service_name(self, admin_client: MagicMock) -> None:
        resp = admin_client.post(
            "/settings/trust/invalid name!/update",
            data={"trust_level": "3"},
        )
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Invalid service name" in html

    def test_rejects_non_numeric_level(self, admin_client: MagicMock) -> None:
        resp = admin_client.post(
            "/settings/trust/payment-api/update",
            data={"trust_level": "high"},
        )
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "must be a number" in html

    def test_rejects_level_out_of_range(self, admin_client: MagicMock) -> None:
        resp = admin_client.post(
            "/settings/trust/payment-api/update",
            data={"trust_level": "6"},
        )
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "must be between" in html

    def test_handles_service_error(self, admin_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.set_trust_level.side_effect = TrustLevelServiceError("fail")

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = admin_client.post(
                "/settings/trust/payment-api/update",
                data={"trust_level": "3"},
            )

        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Failed to update" in html

    def test_empty_reason_treated_as_none(self, admin_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.set_trust_level.return_value = _make_config("svc", 3, reason=None)

        with patch(SERVICE_PATCH, return_value=mock_service):
            admin_client.post(
                "/settings/trust/svc/update",
                data={"trust_level": "3", "reason": ""},
            )

        # Verify reason=None was passed
        call_args = mock_service.set_trust_level.call_args
        assert call_args.kwargs.get("reason") is None or call_args[1].get("reason") is None

    def test_rejects_long_service_name(self, admin_client: MagicMock) -> None:
        long_name = "a" * 101
        resp = admin_client.post(
            f"/settings/trust/{long_name}/update",
            data={"trust_level": "3"},
        )
        html = resp.data.decode()
        assert "Invalid service name" in html
