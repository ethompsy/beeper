"""Tests for layout shell + base template migration (Story 3.2)."""

from __future__ import annotations

import pathlib
import re

import pytest
from flask import Flask, render_template_string
from flask.testing import FlaskClient

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig

_UI_ROOT = pathlib.Path(__file__).parent.parent
_TEMPLATES = _UI_ROOT / "beeper_ui" / "templates"


@pytest.fixture
def app() -> Flask:
    return create_app(TestingConfig)


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    with app.test_client() as c:
        yield c


def _render(app: Flask, source: str) -> str:
    with app.test_request_context():
        return render_template_string(source)


# ---------------------------------------------------------------------------
# Layout shell DOM structure
# ---------------------------------------------------------------------------


class TestLayoutShellStructure:
    """Structural markup of the layout shell on the root route."""

    def test_sidebar_nav_present(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        assert 'id="sidebar"' in html
        assert 'aria-label="Main navigation"' in html

    def test_main_content_present(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        assert 'id="main-content"' in html
        assert "<main" in html

    def test_hamburger_button_present(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        assert 'id="sidebar-toggle"' in html
        assert 'aria-expanded="false"' in html
        assert 'aria-controls="sidebar"' in html

    def test_skip_link_present_and_first_anchor(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        assert 'href="#main-content"' in html
        # The first <a> element in <body> must be the skip link itself:
        # locate the first anchor's opening tag and assert the skip-link href
        # lives inside that exact tag (not merely somewhere later in the DOM).
        body_start = html.index("<body")
        body_open_end = html.index(">", body_start) + 1
        first_anchor = html.index("<a ", body_open_end)
        first_anchor_tag_end = html.index(">", first_anchor)
        first_anchor_tag = html[first_anchor:first_anchor_tag_end]
        assert 'href="#main-content"' in first_anchor_tag, (
            f"First <a> in <body> must be the skip link; got: {first_anchor_tag!r}"
        )

    def test_below_min_message_in_dom(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        assert 'id="below-min-message"' in html
        assert "768px or wider" in html

    def test_app_shell_wrapper_present(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        assert 'id="app-shell"' in html


# ---------------------------------------------------------------------------
# Block defaults & overrides
# ---------------------------------------------------------------------------


class TestSidebarStateBlock:
    """sidebar_state block defaults to 'auto' and can be overridden."""

    def test_default_is_auto(self, app: Flask) -> None:
        html = _render(app, '{% extends "base.html" %}')
        assert 'data-sidebar-state="auto"' in html

    def test_override_collapsed(self, app: Flask) -> None:
        html = _render(
            app,
            '{% extends "base.html" %}{% block sidebar_state %}collapsed{% endblock %}',
        )
        assert 'data-sidebar-state="collapsed"' in html

    def test_override_expanded(self, app: Flask) -> None:
        html = _render(
            app,
            '{% extends "base.html" %}{% block sidebar_state %}expanded{% endblock %}',
        )
        assert 'data-sidebar-state="expanded"' in html


class TestBreadcrumbBlock:
    """breadcrumb block: no landmark by default, renders overrides."""

    def test_no_breadcrumb_landmark_by_default(self, client: FlaskClient) -> None:
        # A page that supplies no breadcrumb must NOT emit an empty
        # <nav aria-label="Breadcrumb"> ARIA landmark.
        html = client.get("/").data.decode()
        assert 'aria-label="Breadcrumb"' not in html

    def test_override_renders_landmark_and_content(self, app: Flask) -> None:
        source = (
            '{% extends "base.html" %}'
            "{% block breadcrumb %}Investigations &gt; INV-42{% endblock %}"
        )
        html = _render(app, source)
        # When a page supplies a breadcrumb, the landmark AND its content render.
        assert 'aria-label="Breadcrumb"' in html
        assert "Investigations &gt; INV-42" in html

    def test_whitespace_only_breadcrumb_renders_no_landmark(self, app: Flask) -> None:
        # A breadcrumb block containing only whitespace is treated as empty.
        source = '{% extends "base.html" %}{% block breadcrumb %}   {% endblock %}'
        html = _render(app, source)
        assert 'aria-label="Breadcrumb"' not in html


# ---------------------------------------------------------------------------
# Preserved invariants from prior stories
# ---------------------------------------------------------------------------


class TestPreservedInvariants:
    """Story 3-2 must preserve invariants from Story 3-1 and earlier."""

    def test_tailwind_link_before_main_css(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        tw = html.index("css/tailwind.css")
        mn = html.index("css/main.css")
        assert tw < mn

    def test_command_palette_partial_included(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        assert 'id="command-palette-overlay"' in html
        assert 'id="command-search"' in html

    def test_keyboard_help_partial_included(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        assert 'id="keyboard-help-overlay"' in html
        assert "Keyboard Shortcuts" in html

    def test_command_palette_js_script_present(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        assert "js/command-palette.js" in html

    def test_htmx_script_present(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        assert "js/htmx.min.js" in html

    def test_scripts_block_extension_point_exists(self, app: Flask) -> None:
        source = (
            '{% extends "base.html" %}'
            '{% block scripts %}<script id="page-script"></script>{% endblock %}'
        )
        html = _render(app, source)
        assert 'id="page-script"' in html

    def test_title_block_default(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        assert "<title>Beeper - Agentic SRE Platform</title>" in html

    def test_title_block_override(self, app: Flask) -> None:
        html = _render(
            app,
            '{% extends "base.html" %}{% block title %}Custom Page{% endblock %}',
        )
        assert "<title>Custom Page</title>" in html

    def test_content_block_override(self, app: Flask) -> None:
        html = _render(
            app,
            '{% extends "base.html" %}{% block content %}<div id="my-page">Hi</div>{% endblock %}',
        )
        assert 'id="my-page"' in html
        assert ">Hi</div>" in html

    def test_default_content_welcome_card(self, client: FlaskClient) -> None:
        """Default content block (used by `/` route) shows the welcome card."""
        html = client.get("/").data.decode()
        assert "Welcome to Beeper" in html


# ---------------------------------------------------------------------------
# Atomic template migration (AD-3)
# ---------------------------------------------------------------------------


class TestAtomicMigration:
    """All page templates extend base.html only (AD-3)."""

    def test_only_base_html_is_extended(self) -> None:
        """Every {% extends %} directive in templates references base.html."""
        offenders: list[str] = []
        for path in _TEMPLATES.rglob("*.html"):
            text = path.read_text()
            for match in re.finditer(r'{%\s*extends\s+["\']([^"\']+)["\']', text):
                target = match.group(1)
                if target != "base.html":
                    offenders.append(f"{path.relative_to(_UI_ROOT)} -> {target}")
        assert offenders == [], (
            "Templates must extend base.html only (atomic migration per AD-3). "
            f"Offenders: {offenders}"
        )

    def test_page_templates_still_extend_base(self) -> None:
        """The 22 remaining page templates still extend base.html.

        Was 29 (Story 3-2) until Task 6.3 (D13/D14) retired the migrated
        full pages (`investigations/detail.html`, `investigations/list.html`,
        `knowledge/entry.html`, `knowledge/index.html`, `metrics/mttr.html`,
        `sources/list.html`, `spending/spending.html`) — see
        `test_page_template_rendering.py`'s `PAGE_TEMPLATES` for the same list.
        """
        expected = {
            "analytics/dashboard.html",
            "handoff/handoff.html",
            "health/status.html",
            "knowledge/diff.html",
            "knowledge/edit.html",
            "knowledge/history.html",
            "knowledge/import.html",
            "knowledge/learning.html",
            "knowledge/service_knowledge.html",
            "knowledge/trust_settings.html",
            "knowledge/version.html",
            "notifications/config.html",
            "reports/executive.html",
            "reports/noise.html",
            "services/detail.html",
            "services/list.html",
            "slo/dashboard.html",
            "slo/service.html",
            "spending/costs.html",
            "topology/index.html",
            "trust/history.html",
            "trust/settings.html",
        }
        actual: set[str] = set()
        for path in _TEMPLATES.rglob("*.html"):
            text = path.read_text()
            if re.search(r'{%\s*extends\s+["\']base\.html["\']', text):
                actual.add(str(path.relative_to(_TEMPLATES)))
        missing = expected - actual
        assert not missing, f"Page templates missing base.html extends: {missing}"


# ---------------------------------------------------------------------------
# Layout dimensions / responsive classes (Tailwind)
# ---------------------------------------------------------------------------


class TestResponsiveDimensions:
    """Tailwind utility classes encode the AC2 responsive dimensions."""

    def test_sidebar_responsive_width_classes(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        # Find the sidebar nav and check it has w-16 (collapsed) and lg:w-64 (expanded)
        match = re.search(
            r'<nav[^>]*id="sidebar"[^>]*class="([^"]+)"',
            html,
        )
        assert match is not None, "Sidebar nav not found"
        classes = match.group(1)
        assert "w-16" in classes
        assert "lg:w-64" in classes

    def test_top_bar_height_class(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        # Top bar header must have h-12 (48px)
        match = re.search(
            r'<header[^>]*class="([^"]*\bh-12\b[^"]*)"',
            html,
        )
        assert match is not None, "Top bar with h-12 not found"

    def test_content_area_responsive_padding(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        # Content wrapper inside <main> uses p-4 lg:p-6
        assert "p-4" in html
        assert "lg:p-6" in html

    def test_main_responsive_margin_left(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        # <main> shifts right to clear the sidebar: ml-16 lg:ml-64
        match = re.search(
            r'<main[^>]*class="([^"]+)"',
            html,
        )
        assert match is not None
        classes = match.group(1)
        assert "ml-16" in classes
        assert "lg:ml-64" in classes

    def test_transition_classes_with_motion_reduce(self, client: FlaskClient) -> None:
        """All transitioning elements must include motion-reduce:transition-none."""
        html = client.get("/").data.decode()
        # Sidebar and main both transition
        sidebar_match = re.search(
            r'<nav[^>]*id="sidebar"[^>]*class="([^"]+)"',
            html,
        )
        main_match = re.search(r'<main[^>]*class="([^"]+)"', html)
        for name, m in (("sidebar", sidebar_match), ("main", main_match)):
            assert m is not None, f"{name} not found"
            classes = m.group(1)
            assert "duration-200" in classes, f"{name} missing duration-200"
            assert "motion-reduce:transition-none" in classes, (
                f"{name} missing motion-reduce:transition-none"
            )
