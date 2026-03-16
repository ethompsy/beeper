"""Tests for confidence gate threshold settings UI routes."""

from unittest.mock import MagicMock, patch

from beeper_ui.services.confidence_gate_service import (
    ConfidenceGateConfig,
    ConfidenceGateError,
)

# ---------- Helpers ----------


def _make_gate_config(
    trust_level: int = 3,
    threshold: float = 0.90,
    updated_by: str = "admin@test.com",
    updated_at: str = "2026-03-16T10:00:00+00:00",
    description: str = "Act with Approval",
) -> ConfidenceGateConfig:
    return ConfidenceGateConfig(
        trust_level=trust_level,
        threshold=threshold,
        updated_by=updated_by,
        updated_at=updated_at,
        description=description,
    )


GATE_SERVICE_PATCH = "beeper_ui.routes.trust_settings._get_gate_service"


# ---------- GET /settings/trust/gates ----------


class TestGateThresholdsSection:
    """Tests for GET /settings/trust/gates HTMX partial."""

    def test_returns_thresholds(self, user_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_gate_thresholds.return_value = [
            _make_gate_config(3, 0.90, description="Act with Approval"),
            _make_gate_config(4, 0.85, description="Act and Notify"),
            _make_gate_config(5, 0.80, description="Fully Autonomous"),
        ]

        with patch(GATE_SERVICE_PATCH, return_value=mock_service):
            resp = user_client.get("/settings/trust/gates")

        assert resp.status_code == 200
        html = resp.data.decode()
        assert "TL3" in html
        assert "TL4" in html
        assert "TL5" in html

    def test_shows_all_three_thresholds(self, user_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_gate_thresholds.return_value = [
            _make_gate_config(3, 0.90),
            _make_gate_config(4, 0.85),
            _make_gate_config(5, 0.80),
        ]

        with patch(GATE_SERVICE_PATCH, return_value=mock_service):
            resp = user_client.get("/settings/trust/gates")

        html = resp.data.decode()
        assert "90%" in html
        assert "85%" in html
        assert "80%" in html

    def test_shows_advisory_note(self, user_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_gate_thresholds.return_value = [
            _make_gate_config(3, 0.90),
        ]

        with patch(GATE_SERVICE_PATCH, return_value=mock_service):
            resp = user_client.get("/settings/trust/gates")

        html = resp.data.decode()
        assert "advisory-only" in html

    def test_shows_default_threshold_indicator(self, user_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_gate_thresholds.return_value = [
            _make_gate_config(3, 0.90, updated_by="", updated_at=""),
        ]

        with patch(GATE_SERVICE_PATCH, return_value=mock_service):
            resp = user_client.get("/settings/trust/gates")

        html = resp.data.decode()
        assert "default threshold" in html.lower()

    def test_shows_custom_threshold_metadata(self, user_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_gate_thresholds.return_value = [
            _make_gate_config(3, 0.85, updated_by="admin@test.com"),
        ]

        with patch(GATE_SERVICE_PATCH, return_value=mock_service):
            resp = user_client.get("/settings/trust/gates")

        html = resp.data.decode()
        assert "admin@test.com" in html

    def test_user_role_can_access(self, user_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_gate_thresholds.return_value = []

        with patch(GATE_SERVICE_PATCH, return_value=mock_service):
            resp = user_client.get("/settings/trust/gates")

        assert resp.status_code == 200

    def test_admin_role_can_access(self, admin_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_gate_thresholds.return_value = []

        with patch(GATE_SERVICE_PATCH, return_value=mock_service):
            resp = admin_client.get("/settings/trust/gates")

        assert resp.status_code == 200

    def test_handles_service_error(self, user_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.get_gate_thresholds.side_effect = ConfidenceGateError("fail")

        with patch(GATE_SERVICE_PATCH, return_value=mock_service):
            resp = user_client.get("/settings/trust/gates")

        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Unable to load gate threshold data" in html

    def test_full_settings_page_includes_gate_section(
        self, user_client: MagicMock
    ) -> None:
        trust_patch = "beeper_ui.routes.trust_settings._get_trust_level_service"
        mock_trust = MagicMock()
        mock_trust.get_all_trust_levels.return_value = []

        with patch(trust_patch, return_value=mock_trust):
            resp = user_client.get("/settings/trust/")

        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Confidence Gate Thresholds" in html
        assert "gate-thresholds" in html


# ---------- POST /settings/trust/gates/<trust_level>/update ----------


class TestUpdateGateThreshold:
    """Tests for POST /settings/trust/gates/<trust_level>/update."""

    def test_admin_can_update_valid_threshold(
        self, admin_client: MagicMock
    ) -> None:
        mock_service = MagicMock()
        mock_service.set_gate_threshold.return_value = _make_gate_config(
            3, 0.85
        )

        with patch(GATE_SERVICE_PATCH, return_value=mock_service):
            resp = admin_client.post(
                "/settings/trust/gates/3/update",
                data={"threshold": "0.85"},
            )

        assert resp.status_code == 200
        html = resp.data.decode()
        assert "updated successfully" in html

    def test_user_cannot_update(self, user_client: MagicMock) -> None:
        resp = user_client.post(
            "/settings/trust/gates/3/update",
            data={"threshold": "0.85"},
        )
        assert resp.status_code == 403

    def test_rejects_threshold_above_1(self, admin_client: MagicMock) -> None:
        resp = admin_client.post(
            "/settings/trust/gates/3/update",
            data={"threshold": "1.5"},
        )
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "must be between" in html

    def test_rejects_threshold_below_0(self, admin_client: MagicMock) -> None:
        resp = admin_client.post(
            "/settings/trust/gates/3/update",
            data={"threshold": "-0.1"},
        )
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "must be between" in html

    def test_rejects_non_numeric_threshold(
        self, admin_client: MagicMock
    ) -> None:
        resp = admin_client.post(
            "/settings/trust/gates/3/update",
            data={"threshold": "high"},
        )
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "must be a number" in html

    def test_rejects_empty_threshold(self, admin_client: MagicMock) -> None:
        resp = admin_client.post(
            "/settings/trust/gates/3/update",
            data={"threshold": ""},
        )
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "must be a number" in html

    def test_rejects_tl1(self, admin_client: MagicMock) -> None:
        resp = admin_client.post(
            "/settings/trust/gates/1/update",
            data={"threshold": "0.85"},
        )
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "advisory-only" in html

    def test_rejects_tl2(self, admin_client: MagicMock) -> None:
        resp = admin_client.post(
            "/settings/trust/gates/2/update",
            data={"threshold": "0.85"},
        )
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "advisory-only" in html

    def test_accepts_tl4(self, admin_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.set_gate_threshold.return_value = _make_gate_config(
            4, 0.75, description="Act and Notify"
        )

        with patch(GATE_SERVICE_PATCH, return_value=mock_service):
            resp = admin_client.post(
                "/settings/trust/gates/4/update",
                data={"threshold": "0.75"},
            )

        assert resp.status_code == 200
        html = resp.data.decode()
        assert "updated successfully" in html

    def test_accepts_tl5(self, admin_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.set_gate_threshold.return_value = _make_gate_config(
            5, 0.60, description="Fully Autonomous"
        )

        with patch(GATE_SERVICE_PATCH, return_value=mock_service):
            resp = admin_client.post(
                "/settings/trust/gates/5/update",
                data={"threshold": "0.60"},
            )

        assert resp.status_code == 200
        html = resp.data.decode()
        assert "updated successfully" in html

    def test_handles_service_error(self, admin_client: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.set_gate_threshold.side_effect = ConfidenceGateError(
            "fail"
        )

        with patch(GATE_SERVICE_PATCH, return_value=mock_service):
            resp = admin_client.post(
                "/settings/trust/gates/3/update",
                data={"threshold": "0.85"},
            )

        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Failed to update" in html

    def test_passes_x_beeper_user_header(
        self, admin_client: MagicMock
    ) -> None:
        mock_service = MagicMock()
        mock_service.set_gate_threshold.return_value = _make_gate_config(
            3, 0.85
        )

        with patch(GATE_SERVICE_PATCH, return_value=mock_service):
            admin_client.post(
                "/settings/trust/gates/3/update",
                data={"threshold": "0.85"},
                headers={"X-Beeper-User": "sre@company.com"},
            )

        call_kwargs = mock_service.set_gate_threshold.call_args.kwargs
        assert call_kwargs["updated_by"] == "sre@company.com"

    def test_accepts_boundary_threshold_1(
        self, admin_client: MagicMock
    ) -> None:
        mock_service = MagicMock()
        mock_service.set_gate_threshold.return_value = _make_gate_config(
            3, 1.0
        )

        with patch(GATE_SERVICE_PATCH, return_value=mock_service):
            resp = admin_client.post(
                "/settings/trust/gates/3/update",
                data={"threshold": "1.0"},
            )

        assert resp.status_code == 200
        html = resp.data.decode()
        assert "updated successfully" in html

    def test_accepts_boundary_threshold_0(
        self, admin_client: MagicMock
    ) -> None:
        mock_service = MagicMock()
        mock_service.set_gate_threshold.return_value = _make_gate_config(
            3, 0.0
        )

        with patch(GATE_SERVICE_PATCH, return_value=mock_service):
            resp = admin_client.post(
                "/settings/trust/gates/3/update",
                data={"threshold": "0.0"},
            )

        assert resp.status_code == 200
        html = resp.data.decode()
        assert "updated successfully" in html

    def test_rejects_boolean_true_threshold(
        self, admin_client: MagicMock
    ) -> None:
        resp = admin_client.post(
            "/settings/trust/gates/3/update",
            data={"threshold": "true"},
        )
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "must be a number" in html

    def test_rejects_boolean_false_threshold(
        self, admin_client: MagicMock
    ) -> None:
        resp = admin_client.post(
            "/settings/trust/gates/3/update",
            data={"threshold": "false"},
        )
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "must be a number" in html
