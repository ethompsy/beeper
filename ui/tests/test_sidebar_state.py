"""Tests for sidebar state management & route-driven collapse (Story 3.4).

Covers the five [T] acceptance criteria for Task 3.4. Following the repo's
established conventions (test_layout_shell.py + test_command_palette.py):

  • Template/CSS-class behaviour is proven by rendering the page and asserting
    on the markup (Tailwind utility classes ARE the contract — Story 3.2/3.3).
  • Client-side behaviour (the sessionStorage state machine in sidebar.js) is
    proven by asserting on the shipped JS source, exactly as test_command_palette
    asserts on command-palette.js. The project runs `poetry run pytest` with no
    Node/browser (AD-7 Node-avoidance, AD-8 manual integration), so runtime DOM
    behaviour is verified manually in the browser during the [H] review; these
    tests pin the source contract that behaviour depends on.

[H] criterion (NFR17 smooth render) is validated by the user in-browser, not here.
"""

from __future__ import annotations

import os
import re

import pytest
from flask import Flask, render_template_string
from flask.testing import FlaskClient

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig

STATIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "beeper_ui",
    "static",
)


@pytest.fixture
def app() -> Flask:
    return create_app(TestingConfig)


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    with app.test_client() as c:
        yield c


def _read_static(relative_path: str) -> str:
    with open(os.path.join(STATIC_DIR, relative_path)) as f:
        return f.read()


def _render_detail(app: Flask) -> str:
    """Render the layout shell with the forced-collapsed sidebar state.

    Task 6.3 (D13/D14) retired `investigations/detail.html` — it was the
    only Jinja page that ever set `{% block sidebar_state %}collapsed
    {% endblock %}`; no other retained page uses the "collapsed" override.
    The forced-collapsed rail is still a generic `layout_shell(sidebar_state=
    ...)` capability of the shell macro itself (Story 3.4), independent of
    any one caller, so this exercises that macro directly rather than a
    now-deleted page — proving the underlying mechanism, not a specific
    (retired) consumer of it.
    """
    with app.test_request_context():
        return render_template_string(
            '{% from "components/layout.html" import layout_shell %}'
            '{% call layout_shell(sidebar_state="collapsed") %}{% endcall %}'
        )


def _app_shell_tag(html: str) -> str:
    """The opening <div id="app-shell" ...> tag (the state root)."""
    start = html.index('<div id="app-shell"')
    return html[start : html.index(">", start) + 1]


def _nav_classes(html: str) -> str:
    match = re.search(r'<nav[^>]*id="sidebar"[^>]*class="([^"]+)"', html)
    assert match is not None, "Sidebar nav not found"
    return match.group(1)


def _main_classes(html: str) -> str:
    match = re.search(r'<main[^>]*id="main-content"[^>]*class="([^"]+)"', html)
    assert match is not None, "main#main-content not found"
    return match.group(1)


# ---------------------------------------------------------------------------
# AC1 — [T] Non-detail templates → `auto` → viewport-responsive (AD-6)
# ---------------------------------------------------------------------------


class TestAutoStateOnNonDetailPages:
    """Non-detail pages resolve to the `auto` (CSS-responsive) sidebar state."""

    def test_state_root_is_app_shell_group(self, client: FlaskClient) -> None:
        # #app-shell is the single state root: it carries the group + the
        # data-sidebar-state the whole machine keys off of.
        tag = _app_shell_tag(client.get("/").data.decode())
        assert "group/shell" in tag
        assert "data-sidebar-state=" in tag

    def test_root_page_is_auto(self, client: FlaskClient) -> None:
        tag = _app_shell_tag(client.get("/").data.decode())
        assert 'data-sidebar-state="auto"' in tag

    def test_health_page_is_auto(self, client: FlaskClient) -> None:
        # A representative non-detail route also inherits the auto default.
        # (Was `/investigations/` — retired by Task 6.3/D13-D14; `/health/`
        # is an un-migrated Jinja page and serves the same "any ordinary
        # page" purpose here.)
        tag = _app_shell_tag(client.get("/health/").data.decode())
        assert 'data-sidebar-state="auto"' in tag

    def test_auto_uses_responsive_width(self, client: FlaskClient) -> None:
        # auto = 64px rail <1200px, 256px ≥1200px (the bare w-16 / lg:w-64 pair).
        classes = _nav_classes(client.get("/").data.decode())
        assert "w-16" in classes
        assert "lg:w-64" in classes

    def test_auto_content_uses_responsive_margin(self, client: FlaskClient) -> None:
        classes = _main_classes(client.get("/").data.decode())
        assert "ml-16" in classes
        assert "lg:ml-64" in classes


# ---------------------------------------------------------------------------
# AC2 — [T] Investigation-detail → `collapsed` regardless of width, hamburger
#        still visible (FR44)
# ---------------------------------------------------------------------------


class TestDetailForcedCollapsed:
    """`layout_shell(sidebar_state='collapsed')` forces the icon rail at any
    width — a page opts into this by setting `{% block sidebar_state %}
    collapsed{% endblock %}` (formerly `investigations/detail.html`, retired
    by Task 6.3; see `_render_detail()` above)."""

    def test_detail_sets_collapsed_state(self, app: Flask) -> None:
        tag = _app_shell_tag(_render_detail(app))
        assert 'data-sidebar-state="collapsed"' in tag

    def test_detail_keeps_hamburger_visible(self, app: Flask) -> None:
        # FR44: the top-bar hamburger remains so the user can still expand.
        html = _render_detail(app)
        assert 'id="sidebar-toggle"' in html
        assert 'aria-controls="sidebar"' in html

    def test_sidebar_has_collapsed_width_override(self, app: Flask) -> None:
        # The collapsed override forces the 64px rail; its `group-data` selector
        # outranks the bare `lg:w-64`, so it wins even at ≥1200px ("regardless
        # of width"). w-16 + lg:w-64 remain for the auto state on other pages.
        classes = _nav_classes(_render_detail(app))
        assert "group-data-[sidebar-state=collapsed]/shell:w-16" in classes

    def test_content_has_collapsed_margin_override(self, app: Flask) -> None:
        classes = _main_classes(_render_detail(app))
        assert "group-data-[sidebar-state=collapsed]/shell:ml-16" in classes

    def test_expanded_override_present_for_forced_expand(
        self, client: FlaskClient
    ) -> None:
        # The third state (forced-expanded) is wired symmetrically so a manual
        # toggle can pin 256px below 1200px too.
        html = client.get("/").data.decode()
        assert "group-data-[sidebar-state=expanded]/shell:w-64" in _nav_classes(html)
        assert "group-data-[sidebar-state=expanded]/shell:ml-64" in _main_classes(html)


# ---------------------------------------------------------------------------
# AC3 — [T] Manual toggle (hamburger or `[`) writes sidebar-manual-override to
#        sessionStorage; cleared on next full navigation
# ---------------------------------------------------------------------------


class TestManualToggleOverride:
    """Hamburger / `[` toggle + the per-page sessionStorage override."""

    def test_sidebar_js_loaded(self, client: FlaskClient) -> None:
        assert "js/sidebar.js" in client.get("/").data.decode()

    def test_sidebar_js_exists(self) -> None:
        assert os.path.isfile(os.path.join(STATIC_DIR, "js", "sidebar.js"))

    def test_override_written_to_sessionstorage(self) -> None:
        js = _read_static("js/sidebar.js")
        assert "sidebar-manual-override" in js
        assert "sessionStorage.setItem" in js

    def test_override_cleared_on_full_navigation(self) -> None:
        # "cleared on next full navigation" = removed on each fresh document load
        # (init runs on DOMContentLoaded / immediately if already loaded).
        js = _read_static("js/sidebar.js")
        assert "sessionStorage.removeItem" in js
        assert "DOMContentLoaded" in js

    def test_hamburger_click_wired(self) -> None:
        js = _read_static("js/sidebar.js")
        assert "sidebar-toggle" in js
        assert "addEventListener" in js
        # Toggling flips the shell's state attribute.
        assert "data-sidebar-state" in js

    def test_bracket_key_toggles_sidebar(self) -> None:
        js = _read_static("js/sidebar.js")
        # `[` keydown handler present and guards typing/overlay contexts.
        assert '"["' in js
        assert "keydown" in js
        assert "command-palette-overlay" in js

    def test_hamburger_has_aria_wiring(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        assert 'id="sidebar-toggle"' in html
        assert 'aria-expanded=' in html
        assert 'aria-controls="sidebar"' in html


# ---------------------------------------------------------------------------
# AC4 — [T] Per-group open/closed state persisted in sessionStorage by group
#        label; defaults all-expanded
# ---------------------------------------------------------------------------


class TestPerGroupPersistence:
    """Group headers toggle, persist by label, and default to expanded."""

    def test_group_header_is_a_toggle_button(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        # Each group header is now a <button> with aria-expanded + aria-controls.
        match = re.search(
            r'<button[^>]*class="sidebar-group-header[^"]*"[^>]*>', html
        )
        assert match is not None, "Group header should be a <button>"
        tag = match.group(0)
        assert "aria-expanded=" in tag
        assert "aria-controls=" in tag

    def test_groups_expose_label_data_attribute(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        assert 'data-group="Observe"' in html
        assert 'data-group="Learn"' in html
        assert 'data-group="Manage"' in html

    def test_items_list_has_id_for_aria_controls(self, client: FlaskClient) -> None:
        html = client.get("/").data.decode()
        # aria-controls target ids exist on the item <ul>s.
        assert 'id="sidebar-group-observe"' in html
        assert 'id="sidebar-group-learn"' in html
        assert 'id="sidebar-group-manage"' in html

    def test_default_groups_expanded(self, client: FlaskClient) -> None:
        # Default all-expanded: rendered item lists are NOT hidden.
        html = client.get("/").data.decode()
        for match in re.finditer(r'<ul[^>]*class="sidebar-group-items([^"]*)"', html):
            assert "hidden" not in match.group(1)

    def test_persistence_keyed_by_group_label(self) -> None:
        js = _read_static("js/sidebar.js")
        # Per-group state stored under a label-keyed sessionStorage key.
        assert "sidebar-group:" in js
        assert "data-group" in js
        assert "sessionStorage.setItem" in js
        assert "sessionStorage.getItem" in js

    def test_default_expanded_when_unset(self) -> None:
        js = _read_static("js/sidebar.js")
        # Only an explicit "closed" persisted value collapses a group; unset /
        # "open" leaves it expanded (default all-expanded).
        assert '"closed"' in js


# ---------------------------------------------------------------------------
# AC5 — [T] Transitions: width 200ms ease-in-out (sidebar), margin-left 200ms
#        ease-in-out (content); respects prefers-reduced-motion
# ---------------------------------------------------------------------------


class TestTransitions:
    """200ms ease-in-out transitions + reduced-motion safety."""

    def test_sidebar_width_transition(self, client: FlaskClient) -> None:
        # transition-all covers `width`; 200ms ease-in-out per the AC.
        classes = _nav_classes(client.get("/").data.decode())
        assert "transition-all" in classes
        assert "duration-200" in classes
        assert "ease-in-out" in classes

    def test_content_margin_transition(self, client: FlaskClient) -> None:
        # transition-all covers `margin-left`; 200ms ease-in-out per the AC.
        classes = _main_classes(client.get("/").data.decode())
        assert "transition-all" in classes
        assert "duration-200" in classes
        assert "ease-in-out" in classes

    def test_sidebar_and_content_respect_reduced_motion(
        self, client: FlaskClient
    ) -> None:
        html = client.get("/").data.decode()
        assert "motion-reduce:transition-none" in _nav_classes(html)
        assert "motion-reduce:transition-none" in _main_classes(html)

    def test_group_chevron_transition_is_reduced_motion_safe(
        self, client: FlaskClient
    ) -> None:
        # The chevron rotate also animates at 200ms and respects reduced motion.
        html = client.get("/").data.decode()
        match = re.search(
            r'class="sidebar-group-chevron([^"]*)"', html
        )
        assert match is not None
        chevron_classes = match.group(1)
        assert "transition-transform" in chevron_classes
        assert "duration-200" in chevron_classes
        assert "motion-reduce:transition-none" in chevron_classes

    def test_js_respects_reduced_motion_via_css_not_js(self) -> None:
        # Smoothness/reduced-motion is a CSS concern (AD-6): sidebar.js must not
        # hand-roll animation timing. It only flips attributes/classes.
        js = _read_static("js/sidebar.js")
        assert "setInterval" not in js
        assert "requestAnimationFrame" not in js
