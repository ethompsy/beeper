"""Route and template integration tests for shift handoff summaries."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from flask import Flask
from flask.testing import FlaskClient

from beeper_ui.services.handoff_service import HandoffSummary


# -----------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------

@pytest.fixture
def mock_summary() -> HandoffSummary:
    """A normal (non-all-clear) handoff summary for testing."""
    return HandoffSummary(
        active_investigations=[
            {
                "id": "inv-1",
                "service": "auth-svc",
                "severity": "high",
                "status": "investigating",
                "condition": "degraded",
                "started_at": "2026-03-16T08:00:00+00:00",
                "link": "/investigations/inv-1",
            },
        ],
        resolved_incidents=[
            {
                "id": "inv-2",
                "service": "order-svc",
                "severity": "medium",
                "condition": "ok",
                "started_at": "2026-03-16T06:00:00+00:00",
                "completed_at": "2026-03-16T07:30:00+00:00",
                "link": "/investigations/inv-2",
            },
        ],
        slo_status=[
            {
                "name": "auth-slo",
                "condition": "warning",
                "compliance": 0.98,
                "burn_rate": 3.0,
                "link": "/slo/services/auth-slo",
            },
        ],
        items_to_watch=[
            {
                "type": "slo",
                "description": "auth-slo SLO is warning",
                "severity": "warning",
                "link": "/slo/services/auth-slo",
            },
        ],
        generated_at="2026-03-16T12:00:00+00:00",
        is_all_clear=False,
    )


@pytest.fixture
def mock_all_clear_summary() -> HandoffSummary:
    """An all-clear handoff summary."""
    return HandoffSummary(
        active_investigations=[],
        resolved_incidents=[],
        slo_status=[
            {
                "name": "api-slo",
                "condition": "healthy",
                "compliance": 0.999,
                "burn_rate": 0.3,
                "link": "/slo/services/api-slo",
            },
        ],
        items_to_watch=[],
        generated_at="2026-03-16T12:00:00+00:00",
        is_all_clear=True,
    )


# -----------------------------------------------------------------
# Handoff route — normal summary
# -----------------------------------------------------------------

class TestHandoffRoute:
    """Tests for GET /handoff/."""

    def test_handoff_returns_200(
        self, client: FlaskClient, mock_summary: HandoffSummary
    ) -> None:
        with patch(
            "beeper_ui.routes.handoff.HandoffService"
        ) as MockSvc:
            MockSvc.return_value.generate_summary.return_value = mock_summary
            resp = client.get("/handoff/")
        assert resp.status_code == 200

    def test_handoff_renders_sbar_sections(
        self, client: FlaskClient, mock_summary: HandoffSummary
    ) -> None:
        with patch(
            "beeper_ui.routes.handoff.HandoffService"
        ) as MockSvc:
            MockSvc.return_value.generate_summary.return_value = mock_summary
            resp = client.get("/handoff/")
        html = resp.data.decode()
        assert "Situation" in html
        assert "Background" in html
        assert "Assessment" in html
        assert "Recommendation" in html

    def test_handoff_contains_investigation_link(
        self, client: FlaskClient, mock_summary: HandoffSummary
    ) -> None:
        with patch(
            "beeper_ui.routes.handoff.HandoffService"
        ) as MockSvc:
            MockSvc.return_value.generate_summary.return_value = mock_summary
            resp = client.get("/handoff/")
        html = resp.data.decode()
        assert '/investigations/inv-1' in html
        assert '/investigations/inv-2' in html

    def test_handoff_contains_slo_link(
        self, client: FlaskClient, mock_summary: HandoffSummary
    ) -> None:
        with patch(
            "beeper_ui.routes.handoff.HandoffService"
        ) as MockSvc:
            MockSvc.return_value.generate_summary.return_value = mock_summary
            resp = client.get("/handoff/")
        html = resp.data.decode()
        assert '/slo/services/auth-slo' in html

    def test_htmx_returns_partial(
        self, client: FlaskClient, mock_summary: HandoffSummary
    ) -> None:
        with patch(
            "beeper_ui.routes.handoff.HandoffService"
        ) as MockSvc:
            MockSvc.return_value.generate_summary.return_value = mock_summary
            resp = client.get(
                "/handoff/", headers={"HX-Request": "true"}
            )
        html = resp.data.decode()
        # Partial should NOT include base template's <nav> but should have SBAR
        assert "Situation" in html
        # Partial should not extend base (no full <html> tag)
        assert "<!DOCTYPE" not in html


# -----------------------------------------------------------------
# JSON endpoint
# -----------------------------------------------------------------

class TestHandoffJsonRoute:
    """Tests for GET /handoff/json."""

    def test_json_returns_200(
        self, client: FlaskClient, mock_summary: HandoffSummary
    ) -> None:
        with patch(
            "beeper_ui.routes.handoff.HandoffService"
        ) as MockSvc:
            MockSvc.return_value.generate_summary.return_value = mock_summary
            resp = client.get("/handoff/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "active_investigations" in data
        assert "resolved_incidents" in data
        assert "slo_status" in data
        assert "items_to_watch" in data
        assert "generated_at" in data
        assert "is_all_clear" in data

    def test_json_error_returns_500(self, client: FlaskClient) -> None:
        with patch(
            "beeper_ui.routes.handoff.HandoffService"
        ) as MockSvc:
            MockSvc.return_value.generate_summary.side_effect = Exception(
                "boom"
            )
            resp = client.get("/handoff/json")
        assert resp.status_code == 500
        data = resp.get_json()
        assert "error" in data


# -----------------------------------------------------------------
# All-clear state
# -----------------------------------------------------------------

class TestHandoffAllClear:
    """Tests for all-clear handoff rendering."""

    def test_all_clear_renders_card(
        self,
        client: FlaskClient,
        mock_all_clear_summary: HandoffSummary,
    ) -> None:
        with patch(
            "beeper_ui.routes.handoff.HandoffService"
        ) as MockSvc:
            MockSvc.return_value.generate_summary.return_value = (
                mock_all_clear_summary
            )
            resp = client.get("/handoff/")
        html = resp.data.decode()
        assert "All Clear" in html
        # SLO overview still shown
        assert "api-slo" in html

    def test_all_clear_no_sbar_sections(
        self,
        client: FlaskClient,
        mock_all_clear_summary: HandoffSummary,
    ) -> None:
        with patch(
            "beeper_ui.routes.handoff.HandoffService"
        ) as MockSvc:
            MockSvc.return_value.generate_summary.return_value = (
                mock_all_clear_summary
            )
            resp = client.get("/handoff/")
        html = resp.data.decode()
        # SBAR section headers should NOT appear in all-clear mode
        assert "sbar-s" not in html


# -----------------------------------------------------------------
# Error state
# -----------------------------------------------------------------

class TestHandoffError:
    """Tests for error-state rendering."""

    def test_service_failure_renders_error(
        self, client: FlaskClient
    ) -> None:
        with patch(
            "beeper_ui.routes.handoff.HandoffService"
        ) as MockSvc:
            MockSvc.return_value.generate_summary.side_effect = Exception(
                "operator down"
            )
            resp = client.get("/handoff/")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Unable to generate handoff summary" in html


# -----------------------------------------------------------------
# Navigation link
# -----------------------------------------------------------------

class TestHandoffNavigation:
    """Tests for handoff link in base navigation."""

    def test_nav_contains_handoff_link(self, client: FlaskClient) -> None:
        with patch(
            "beeper_ui.routes.handoff.HandoffService"
        ) as MockSvc:
            MockSvc.return_value.generate_summary.return_value = (
                HandoffSummary(is_all_clear=True, generated_at="now")
            )
            resp = client.get("/handoff/")
        html = resp.data.decode()
        assert 'href="/handoff/"' in html


# -----------------------------------------------------------------
# Clickable links
# -----------------------------------------------------------------

class TestHandoffClickableLinks:
    """Tests for clickable investigation and SLO links."""

    def test_investigation_id_is_anchor(
        self, client: FlaskClient, mock_summary: HandoffSummary
    ) -> None:
        with patch(
            "beeper_ui.routes.handoff.HandoffService"
        ) as MockSvc:
            MockSvc.return_value.generate_summary.return_value = mock_summary
            resp = client.get("/handoff/")
        html = resp.data.decode()
        assert '<a href="/investigations/inv-1">' in html

    def test_slo_service_is_anchor(
        self, client: FlaskClient, mock_summary: HandoffSummary
    ) -> None:
        with patch(
            "beeper_ui.routes.handoff.HandoffService"
        ) as MockSvc:
            MockSvc.return_value.generate_summary.return_value = mock_summary
            resp = client.get("/handoff/")
        html = resp.data.decode()
        assert '<a href="/slo/services/auth-slo">' in html


# -----------------------------------------------------------------
# Copy button
# -----------------------------------------------------------------

class TestHandoffCopyButton:
    """Tests for clipboard copy button presence."""

    def test_copy_button_present(
        self, client: FlaskClient, mock_summary: HandoffSummary
    ) -> None:
        with patch(
            "beeper_ui.routes.handoff.HandoffService"
        ) as MockSvc:
            MockSvc.return_value.generate_summary.return_value = mock_summary
            resp = client.get("/handoff/")
        html = resp.data.decode()
        assert "Copy to Clipboard" in html
        assert "copyHandoff()" in html
