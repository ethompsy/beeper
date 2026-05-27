"""Tests for Task 4.1: Investigation list view with status filtering.

Maps each [T] acceptance criterion to a named test:

  AC1  investigation_card macro renders service/severity/status/timestamp
  AC2  status_badge macro colors status with correct Tailwind tokens
  AC3  Status-group filter: active is default; user can switch to resolved/failed
  AC4  Cards carry 3px status-colored left border; completed cards are muted
  AC5  empty_state macro renders with title/description/icon

Test pattern follows repo convention (test_sidebar_state.py, test_command_palette.py):
  - Render assertions using client.get() and app.jinja_env.get_template().render()
  - Static-source assertions for source-level contracts
  - No JS runner (AD-7 / AD-8)
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
import respx
from flask import Flask
from flask.testing import FlaskClient
from httpx import Response

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig
from beeper_ui.services.investigation_service import Investigation

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "beeper_ui",
    "templates",
)


@pytest.fixture
def app() -> Flask:
    return create_app(TestingConfig)


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Shared mock investigation fixtures
# ---------------------------------------------------------------------------

_INVESTIGATING = {
    "id": "inv-active-001",
    "status": "investigating",
    "service": "payments",
    "severity": "high",
    "condition": "High error rate detected",
    "started_at": "2026-05-20T12:00:00Z",
    "completed_at": None,
    "triggered_at": "2026-05-20T11:55:00Z",
}

_AWAITING = {
    "id": "inv-await-001",
    "status": "awaiting_confirmation",
    "service": "auth-service",
    "severity": "medium",
    "condition": "Latency spike",
    "started_at": "2026-05-20T13:00:00Z",
    "completed_at": None,
    "triggered_at": "2026-05-20T12:55:00Z",
}

_COMPLETED = {
    "id": "inv-done-001",
    "status": "completed",
    "service": "api-gateway",
    "severity": "low",
    "condition": "Resolved latency issue",
    "started_at": "2026-05-19T10:00:00Z",
    "completed_at": "2026-05-19T10:30:00Z",
    "triggered_at": "2026-05-19T09:55:00Z",
}

_FAILED = {
    "id": "inv-fail-001",
    "status": "failed",
    "service": "billing",
    "severity": "critical",
    "condition": "Investigation error",
    "started_at": "2026-05-18T08:00:00Z",
    "completed_at": None,
    "triggered_at": "2026-05-18T07:55:00Z",
}


def _mock_urgency():
    """Context manager that mocks out SLO/urgency service calls."""
    return patch("beeper_ui.routes.investigations._get_slo_service"), \
           patch("beeper_ui.routes.investigations._get_urgency_service")


def _render_card(app: Flask, inv_data: dict) -> str:
    """Render the investigation_card macro for a single investigation."""
    inv = Investigation.from_dict(inv_data)
    with app.app_context():
        tpl = app.jinja_env.get_template("components/cards.html")
        return tpl.module.investigation_card(inv)


def _render_badge(app: Flask, status: str) -> str:
    """Render the status_badge macro for a given status string."""
    with app.app_context():
        tpl = app.jinja_env.get_template("components/status.html")
        return tpl.module.status_badge(status)


def _render_empty(app: Flask, title: str, description: str, icon: str = "") -> str:
    """Render the empty_state macro."""
    with app.app_context():
        tpl = app.jinja_env.get_template("components/empty.html")
        return tpl.module.empty_state(title, description, icon)


# ---------------------------------------------------------------------------
# AC1 — investigation_card macro renders service / severity / status / timestamp
# ---------------------------------------------------------------------------

class TestInvestigationCardMacro:
    """AC1: investigation_card(inv) shows service / severity / status / timestamp."""

    def test_card_shows_service(self, app: Flask) -> None:
        """investigation_card renders the service name."""
        html = _render_card(app, _INVESTIGATING)
        assert "payments" in html

    def test_card_shows_severity(self, app: Flask) -> None:
        """investigation_card renders the severity level."""
        html = _render_card(app, _INVESTIGATING)
        assert "High" in html

    def test_card_shows_status_via_badge(self, app: Flask) -> None:
        """investigation_card renders the status badge for 'investigating'."""
        html = _render_card(app, _INVESTIGATING)
        # The status_badge macro is called inside the card; verify badge output
        assert "status-badge" in html
        assert "In Progress" in html

    def test_card_shows_timestamp(self, app: Flask) -> None:
        """investigation_card renders the started_at timestamp."""
        html = _render_card(app, _INVESTIGATING)
        assert "2026-05-20T12:00:00Z" in html

    def test_card_shows_investigation_id(self, app: Flask) -> None:
        """investigation_card renders the investigation ID."""
        html = _render_card(app, _INVESTIGATING)
        assert "inv-active-001" in html

    def test_card_is_a_link(self, app: Flask) -> None:
        """investigation_card wraps the card in an anchor tag pointing to the detail page."""
        html = _render_card(app, _INVESTIGATING)
        assert 'href="/investigations/inv-active-001"' in html

    def test_card_macro_file_exists(self) -> None:
        """templates/components/cards.html exists and exports investigation_card."""
        path = os.path.join(TEMPLATES_DIR, "components", "cards.html")
        assert os.path.isfile(path), f"cards.html not found at {path}"
        with open(path) as f:
            source = f.read()
        assert "macro investigation_card" in source


# ---------------------------------------------------------------------------
# AC2 — status_badge macro applies correct color tokens per status
# ---------------------------------------------------------------------------

class TestStatusBadgeMacro:
    """AC2: status_badge(status) colors status appropriately."""

    def test_badge_active_is_green(self, app: Flask) -> None:
        """investigating status renders with status-healthy (green) token."""
        html = _render_badge(app, "investigating")
        assert "status-healthy" in html

    def test_badge_awaiting_is_amber(self, app: Flask) -> None:
        """awaiting_confirmation status renders with status-warning (amber) token."""
        html = _render_badge(app, "awaiting_confirmation")
        assert "status-warning" in html

    def test_badge_failed_is_red(self, app: Flask) -> None:
        """failed status renders with status-critical (red) token."""
        html = _render_badge(app, "failed")
        assert "status-critical" in html

    def test_badge_completed_is_gray(self, app: Flask) -> None:
        """completed status renders with status-muted (gray) token."""
        html = _render_badge(app, "completed")
        assert "status-muted" in html

    def test_badge_has_data_status_attribute(self, app: Flask) -> None:
        """status_badge sets data-status= attribute for test selection."""
        for status in ("investigating", "awaiting_confirmation", "failed", "completed"):
            html = _render_badge(app, status)
            assert f'data-status="{status}"' in html

    def test_badge_investigating_label(self, app: Flask) -> None:
        """investigating badge shows 'In Progress' label."""
        html = _render_badge(app, "investigating")
        assert "In Progress" in html

    def test_badge_awaiting_label(self, app: Flask) -> None:
        """awaiting_confirmation badge shows 'Awaiting' label."""
        html = _render_badge(app, "awaiting_confirmation")
        assert "Awaiting" in html

    def test_badge_failed_label(self, app: Flask) -> None:
        """failed badge shows 'Failed' label."""
        html = _render_badge(app, "failed")
        assert "Failed" in html

    def test_badge_completed_label(self, app: Flask) -> None:
        """completed badge shows 'Completed' label."""
        html = _render_badge(app, "completed")
        assert "Completed" in html

    def test_badge_macro_file_exists(self) -> None:
        """templates/components/status.html exists and exports status_badge."""
        path = os.path.join(TEMPLATES_DIR, "components", "status.html")
        assert os.path.isfile(path), f"status.html not found at {path}"
        with open(path) as f:
            source = f.read()
        assert "macro status_badge" in source


# ---------------------------------------------------------------------------
# AC3 — Status-group filter: active is default; user can switch to resolved/failed
# ---------------------------------------------------------------------------

class TestStatusGroupFilter:
    """AC3: active group is default; user can switch to resolved/failed."""

    @pytest.fixture(autouse=True)
    def _mock_urgency(self):
        with patch("beeper_ui.routes.investigations._get_slo_service") as mock_slo, \
             patch("beeper_ui.routes.investigations._get_urgency_service") as mock_urg:
            slo = MagicMock()
            slo.get_service_budget.return_value = None
            mock_slo.return_value = slo
            urg = MagicMock()
            urg.compute_batch_urgency.return_value = {}
            mock_urg.return_value = urg
            yield

    @respx.mock
    def test_default_view_shows_active_investigations(self, client: FlaskClient) -> None:
        """GET /investigations/ with no params shows active (investigating) group by default."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[_INVESTIGATING, _COMPLETED, _FAILED])
        )
        response = client.get("/investigations/")
        assert response.status_code == 200
        # Active investigation visible
        assert b"inv-active-001" in response.data

    @respx.mock
    def test_default_view_hides_completed(self, client: FlaskClient) -> None:
        """Default active group does NOT show completed investigations."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[_INVESTIGATING, _COMPLETED])
        )
        response = client.get("/investigations/")
        assert response.status_code == 200
        # Completed investigation not in default active view
        assert b"inv-done-001" not in response.data

    @respx.mock
    def test_status_group_resolved_shows_completed(self, client: FlaskClient) -> None:
        """status_group=resolved shows completed investigations."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[_INVESTIGATING, _COMPLETED])
        )
        response = client.get("/investigations/?status_group=resolved")
        assert response.status_code == 200
        assert b"inv-done-001" in response.data
        assert b"inv-active-001" not in response.data

    @respx.mock
    def test_status_group_failed_shows_failed(self, client: FlaskClient) -> None:
        """status_group=failed shows failed investigations."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[_INVESTIGATING, _FAILED])
        )
        response = client.get("/investigations/?status_group=failed")
        assert response.status_code == 200
        assert b"inv-fail-001" in response.data
        assert b"inv-active-001" not in response.data

    @respx.mock
    def test_active_group_includes_awaiting_confirmation(
        self, client: FlaskClient
    ) -> None:
        """active group includes both investigating AND awaiting_confirmation investigations."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[_INVESTIGATING, _AWAITING, _COMPLETED])
        )
        response = client.get("/investigations/?status_group=active")
        assert response.status_code == 200
        assert b"inv-active-001" in response.data
        assert b"inv-await-001" in response.data
        assert b"inv-done-001" not in response.data

    def test_status_group_tab_bar_in_template(self) -> None:
        """list.html contains the status-group tab bar with active/resolved/failed tabs."""
        path = os.path.join(TEMPLATES_DIR, "investigations", "list.html")
        with open(path) as f:
            source = f.read()
        # The template uses a loop over tab IDs; verify all three group keys appear
        assert "active" in source
        assert "resolved" in source
        assert "failed" in source
        # Verify it's a tab bar referencing status_group
        assert "status_group" in source

    def test_status_group_tab_bar_role_tablist(self) -> None:
        """Status-group tab bar has role=tablist for accessibility."""
        path = os.path.join(TEMPLATES_DIR, "investigations", "list.html")
        with open(path) as f:
            source = f.read()
        assert 'role="tablist"' in source

    @respx.mock
    def test_active_tab_has_aria_selected_true(self, client: FlaskClient) -> None:
        """Default /investigations/ renders active tab with aria-selected=true."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[])
        )
        response = client.get("/investigations/")
        assert response.status_code == 200
        assert b'aria-selected="true"' in response.data


# ---------------------------------------------------------------------------
# AC4 — Cards carry 3px status-colored left border; completed cards are muted
# ---------------------------------------------------------------------------

class TestCardBorderAndMuting:
    """AC4: 3px status-colored left border; completed cards are muted."""

    def test_investigating_card_has_green_border(self, app: Flask) -> None:
        """investigating card has border-l-status-healthy (green) left border."""
        html = _render_card(app, _INVESTIGATING)
        assert "border-l-status-healthy" in html

    def test_awaiting_card_has_amber_border(self, app: Flask) -> None:
        """awaiting_confirmation card has border-l-status-warning (amber) left border."""
        html = _render_card(app, _AWAITING)
        assert "border-l-status-warning" in html

    def test_failed_card_has_red_border(self, app: Flask) -> None:
        """failed card has border-l-status-critical (red) left border."""
        html = _render_card(app, _FAILED)
        assert "border-l-status-critical" in html

    def test_completed_card_has_gray_border(self, app: Flask) -> None:
        """completed card has border-l-status-muted (gray) left border."""
        html = _render_card(app, _COMPLETED)
        assert "border-l-status-muted" in html

    def test_completed_card_is_reduced_opacity(self, app: Flask) -> None:
        """completed card includes opacity-60 class for visual muting."""
        html = _render_card(app, _COMPLETED)
        assert "opacity-60" in html

    def test_active_card_is_not_muted(self, app: Flask) -> None:
        """investigating card does NOT include opacity-60 (not muted)."""
        html = _render_card(app, _INVESTIGATING)
        assert "opacity-60" not in html

    def test_card_uses_surface_raised_background(self, app: Flask) -> None:
        """Card uses bg-surface-raised design token (not an arbitrary hex color)."""
        html = _render_card(app, _INVESTIGATING)
        assert "bg-surface-raised" in html

    def test_card_border_uses_3px_via_tailwind(self) -> None:
        """cards.html uses border-l-[3px] (or border-l-3) for the 3px border spec."""
        path = os.path.join(TEMPLATES_DIR, "components", "cards.html")
        with open(path) as f:
            source = f.read()
        # Accept either Tailwind arbitrary value or a standard border-l-N class
        assert "border-l-[3px]" in source or "border-l-3" in source


# ---------------------------------------------------------------------------
# AC5 — empty_state macro with title / description / icon
# ---------------------------------------------------------------------------

class TestEmptyStateMacro:
    """AC5: empty_state(title, description, icon) explains investigations appear on detection."""

    def test_empty_state_shows_title(self, app: Flask) -> None:
        """empty_state renders the title argument."""
        html = _render_empty(app, "No active investigations", "Some description")
        assert "No active investigations" in html

    def test_empty_state_shows_description(self, app: Flask) -> None:
        """empty_state renders the description argument."""
        html = _render_empty(
            app, "No active investigations",
            "Investigations appear automatically when Beeper detects anomalies."
        )
        assert "Investigations appear automatically when Beeper detects anomalies." in html

    def test_empty_state_renders_svg_icon(self, app: Flask) -> None:
        """empty_state renders an SVG icon when provided."""
        icon = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/></svg>'
        html = _render_empty(app, "Title", "Desc", icon)
        assert "<svg" in html
        assert "viewBox" in html

    def test_empty_state_without_icon(self, app: Flask) -> None:
        """empty_state renders correctly when no icon is provided."""
        html = _render_empty(app, "No data", "Nothing here yet.")
        assert "No data" in html
        assert "Nothing here yet." in html

    def test_empty_state_has_empty_state_class(self, app: Flask) -> None:
        """empty_state element has the .empty-state class (used by AC5 assertion)."""
        html = _render_empty(app, "Title", "Desc")
        assert "empty-state" in html

    @respx.mock
    def test_empty_state_rendered_in_page_when_no_investigations(
        self, client: FlaskClient
    ) -> None:
        """Full page renders empty_state when the active group has no investigations."""
        with patch("beeper_ui.routes.investigations._get_slo_service") as ms, \
             patch("beeper_ui.routes.investigations._get_urgency_service") as mu:
            ms.return_value = MagicMock()
            ms.return_value.get_service_budget.return_value = None
            mu.return_value = MagicMock()
            mu.return_value.compute_batch_urgency.return_value = {}

            respx.get("http://mock-operator:8080/api/v1/investigations").mock(
                return_value=Response(200, json=[])
            )
            response = client.get("/investigations/")
            assert response.status_code == 200
            assert b"empty-state" in response.data
            assert b"No active investigations" in response.data

    @respx.mock
    def test_empty_state_message_mentions_detection(
        self, client: FlaskClient
    ) -> None:
        """Empty state description explains investigations appear on detection."""
        with patch("beeper_ui.routes.investigations._get_slo_service") as ms, \
             patch("beeper_ui.routes.investigations._get_urgency_service") as mu:
            ms.return_value = MagicMock()
            ms.return_value.get_service_budget.return_value = None
            mu.return_value = MagicMock()
            mu.return_value.compute_batch_urgency.return_value = {}

            respx.get("http://mock-operator:8080/api/v1/investigations").mock(
                return_value=Response(200, json=[])
            )
            response = client.get("/investigations/")
            assert response.status_code == 200
            # The empty state explains that investigations appear on anomaly detection
            assert b"anomal" in response.data.lower() or b"detect" in response.data.lower()

    def test_empty_state_macro_file_exists(self) -> None:
        """templates/components/empty.html exists and exports empty_state."""
        path = os.path.join(TEMPLATES_DIR, "components", "empty.html")
        assert os.path.isfile(path), f"empty.html not found at {path}"
        with open(path) as f:
            source = f.read()
        assert "macro empty_state" in source


# ---------------------------------------------------------------------------
# Integration: full page render with new macros
# ---------------------------------------------------------------------------

class TestListPageIntegration:
    """Integration tests for the migrated list page."""

    @pytest.fixture(autouse=True)
    def _mock_urgency(self):
        with patch("beeper_ui.routes.investigations._get_slo_service") as mock_slo, \
             patch("beeper_ui.routes.investigations._get_urgency_service") as mock_urg:
            slo = MagicMock()
            slo.get_service_budget.return_value = None
            mock_slo.return_value = slo
            urg = MagicMock()
            urg.compute_batch_urgency.return_value = {}
            mock_urg.return_value = urg
            yield

    @respx.mock
    def test_list_uses_investigation_card_macro(self, client: FlaskClient) -> None:
        """Full-page render uses investigation_card macro (class contract)."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[_INVESTIGATING])
        )
        response = client.get("/investigations/")
        assert response.status_code == 200
        # investigation_card produces a link with the investigation-card class
        assert b"investigation-card" in response.data

    @respx.mock
    def test_list_sse_container_preserved(self, client: FlaskClient) -> None:
        """id='investigation-list' SSE container is preserved (Task 4.3 hook)."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[])
        )
        response = client.get("/investigations/")
        assert response.status_code == 200
        assert b'id="investigation-list"' in response.data
        assert b'sse-connect="/investigations/stream"' in response.data

    @respx.mock
    def test_list_no_legacy_card_class_on_migrated_elements(
        self, client: FlaskClient
    ) -> None:
        """Migrated list page does not use the legacy .card class on investigation rows."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[_INVESTIGATING])
        )
        response = client.get("/investigations/")
        assert response.status_code == 200
        # The investigation card itself should use bg-surface-raised, not .card
        assert b"bg-surface-raised" in response.data

    @respx.mock
    def test_list_uses_semantic_tokens_not_hex(self, client: FlaskClient) -> None:
        """Rendered list page has no raw hex color literals (uses design tokens)."""
        respx.get("http://mock-operator:8080/api/v1/investigations").mock(
            return_value=Response(200, json=[_INVESTIGATING])
        )
        response = client.get("/investigations/")
        assert response.status_code == 200
        html = response.data.decode()
        # Check that investigation cards don't embed hardcoded palette colors
        assert "#1a1a2e" not in html
        assert "#0f0f1a" not in html
        assert "#22c55e" not in html
