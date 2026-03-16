"""Tests for trust level configuration API routes."""

import json
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


SERVICE_PATCH = "beeper_ui.routes.trust_config._get_trust_level_service"


# ---------- GET /api/v1/trust/services ----------


class TestListTrustLevels:
    """Tests for GET /api/v1/trust/services."""

    def test_returns_all_trust_levels(self, admin_client: MagicMock) -> None:
        configs = [
            _make_config("svc-a", 2),
            _make_config("svc-b", 4),
        ]
        mock_service = MagicMock()
        mock_service.get_all_trust_levels.return_value = configs

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = admin_client.get("/api/v1/trust/services")

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data) == 2
        assert data[0]["service_name"] == "svc-a"
        assert data[0]["trust_level"] == 2
        assert data[1]["service_name"] == "svc-b"
        assert data[1]["trust_level"] == 4

    def test_returns_empty_list(self, admin_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_all_trust_levels.return_value = []

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = admin_client.get("/api/v1/trust/services")

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data == []

    def test_user_role_can_read(self, user_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_all_trust_levels.return_value = []

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = user_client.get("/api/v1/trust/services")

        assert resp.status_code == 200

    def test_returns_500_on_service_error(self, admin_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_all_trust_levels.side_effect = TrustLevelServiceError("fail")

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = admin_client.get("/api/v1/trust/services")

        assert resp.status_code == 500
        data = json.loads(resp.data)
        assert data["title"] == "Service Error"

    def test_includes_trust_level_name(self, admin_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_all_trust_levels.return_value = [_make_config("svc-a", 3)]

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = admin_client.get("/api/v1/trust/services")

        data = json.loads(resp.data)
        assert data[0]["trust_level_name"] == "Act with Approval"

    def test_closes_service(self, admin_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_all_trust_levels.return_value = []

        with patch(SERVICE_PATCH, return_value=mock_service):
            admin_client.get("/api/v1/trust/services")

        mock_service.close.assert_called_once()


# ---------- GET /api/v1/trust/services/<name> ----------


class TestGetTrustLevel:
    """Tests for GET /api/v1/trust/services/<name>."""

    def test_returns_configured_level(self, user_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_service_trust_level.return_value = _make_config("payment-api", 3)

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = user_client.get("/api/v1/trust/services/payment-api")

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["service_name"] == "payment-api"
        assert data["trust_level"] == 3
        assert data["is_default"] is False

    def test_returns_default_for_unconfigured(self, user_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_service_trust_level.return_value = None

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = user_client.get("/api/v1/trust/services/new-service")

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["service_name"] == "new-service"
        assert data["trust_level"] == 1
        assert data["trust_level_name"] == "Advisory Only"
        assert data["is_default"] is True

    def test_returns_500_on_service_error(self, user_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_service_trust_level.side_effect = TrustLevelServiceError("fail")

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = user_client.get("/api/v1/trust/services/payment-api")

        assert resp.status_code == 500


# ---------- PUT /api/v1/trust/services/<name> ----------


class TestUpdateTrustLevel:
    """Tests for PUT /api/v1/trust/services/<name>."""

    def test_admin_can_update(self, admin_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.set_trust_level.return_value = _make_config("payment-api", 4, previous_level=3)

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = admin_client.put(
                "/api/v1/trust/services/payment-api",
                data=json.dumps({"level": 4, "reason": "Earned it"}),
                content_type="application/json",
            )

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["trust_level"] == 4

    def test_user_cannot_update(self, user_client: MagicMock) -> None:
        resp = user_client.put(
            "/api/v1/trust/services/payment-api",
            data=json.dumps({"level": 4}),
            content_type="application/json",
        )
        assert resp.status_code == 403
        data = json.loads(resp.data)
        assert data["status"] == 403

    def test_rejects_missing_level(self, admin_client: MagicMock) -> None:
        resp = admin_client.put(
            "/api/v1/trust/services/payment-api",
            data=json.dumps({"reason": "no level"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "level" in data["detail"]

    def test_rejects_invalid_level_zero(self, admin_client: MagicMock) -> None:
        resp = admin_client.put(
            "/api/v1/trust/services/payment-api",
            data=json.dumps({"level": 0}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_rejects_invalid_level_six(self, admin_client: MagicMock) -> None:
        resp = admin_client.put(
            "/api/v1/trust/services/payment-api",
            data=json.dumps({"level": 6}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_rejects_non_integer_level(self, admin_client: MagicMock) -> None:
        resp = admin_client.put(
            "/api/v1/trust/services/payment-api",
            data=json.dumps({"level": "high"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_rejects_float_level(self, admin_client: MagicMock) -> None:
        resp = admin_client.put(
            "/api/v1/trust/services/payment-api",
            data=json.dumps({"level": 3.5}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_rejects_negative_level(self, admin_client: MagicMock) -> None:
        resp = admin_client.put(
            "/api/v1/trust/services/payment-api",
            data=json.dumps({"level": -1}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_rejects_missing_json_body(self, admin_client: MagicMock) -> None:
        resp = admin_client.put(
            "/api/v1/trust/services/payment-api",
            data="not json",
            content_type="text/plain",
        )
        assert resp.status_code == 400

    def test_returns_500_on_service_error(self, admin_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.set_trust_level.side_effect = TrustLevelServiceError("fail")

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = admin_client.put(
                "/api/v1/trust/services/payment-api",
                data=json.dumps({"level": 3}),
                content_type="application/json",
            )

        assert resp.status_code == 500

    def test_accepts_level_1(self, admin_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.set_trust_level.return_value = _make_config("svc", 1)

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = admin_client.put(
                "/api/v1/trust/services/svc",
                data=json.dumps({"level": 1}),
                content_type="application/json",
            )
        assert resp.status_code == 200

    def test_accepts_level_5(self, admin_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.set_trust_level.return_value = _make_config("svc", 5)

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = admin_client.put(
                "/api/v1/trust/services/svc",
                data=json.dumps({"level": 5}),
                content_type="application/json",
            )
        assert resp.status_code == 200

    def test_reason_is_optional(self, admin_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.set_trust_level.return_value = _make_config("svc", 3, reason=None)

        with patch(SERVICE_PATCH, return_value=mock_service):
            resp = admin_client.put(
                "/api/v1/trust/services/svc",
                data=json.dumps({"level": 3}),
                content_type="application/json",
            )
        assert resp.status_code == 200

    def test_rejects_boolean_true_level(self, admin_client: MagicMock) -> None:
        resp = admin_client.put(
            "/api/v1/trust/services/payment-api",
            data=json.dumps({"level": True}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_rejects_boolean_false_level(self, admin_client: MagicMock) -> None:
        resp = admin_client.put(
            "/api/v1/trust/services/payment-api",
            data=json.dumps({"level": False}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_rejects_invalid_service_name_special_chars(self, admin_client: MagicMock) -> None:
        resp = admin_client.put(
            "/api/v1/trust/services/invalid%20name!",
            data=json.dumps({"level": 3}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_rejects_empty_service_name(self, admin_client: MagicMock) -> None:
        resp = admin_client.put(
            "/api/v1/trust/services/",
            data=json.dumps({"level": 3}),
            content_type="application/json",
        )
        # Empty name hits 404 (no route match) or 405 — not a valid path
        assert resp.status_code in (404, 405)


# ---------- GET /api/v1/trust/definitions ----------


class TestGetTrustDefinitions:
    """Tests for GET /api/v1/trust/definitions."""

    def test_returns_all_definitions(self, user_client: MagicMock) -> None:
        resp = user_client.get("/api/v1/trust/definitions")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data) == 5
        assert data[0]["level"] == 1
        assert data[0]["name"] == "Advisory Only"
        assert data[4]["level"] == 5
        assert data[4]["name"] == "Fully Autonomous"

    def test_definitions_are_sorted(self, user_client: MagicMock) -> None:
        resp = user_client.get("/api/v1/trust/definitions")
        data = json.loads(resp.data)
        levels = [d["level"] for d in data]
        assert levels == [1, 2, 3, 4, 5]
