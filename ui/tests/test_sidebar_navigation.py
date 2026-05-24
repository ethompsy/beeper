"""Tests for the sidebar navigation component (Story 3.3 — FR40-42).

Covers the [T] acceptance criteria for `sidebar_group(label, icon, items,
expanded, active_item)` and its wiring into the layout shell. Follows the
render-test patterns in test_layout_shell.py: `create_app(TestingConfig)` for
full-page assertions on `/`, and `render_template_string` importing the macro
for focused, isolated macro behaviour.
"""

from __future__ import annotations

import re

import pytest
from flask import Flask, render_template_string
from flask.testing import FlaskClient

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig


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


# Default macro invocation used by several isolated-macro tests.
_IMPORT = '{% from "components/sidebar.html" import sidebar_group %}'


def _render_group(
    app: Flask,
    *,
    label: str = "Observe",
    icon: str = "<svg id='grp-icon'></svg>",
    items: str = "[{'label': 'Investigations', 'url': '/investigations/'}]",
    expanded: str = "true",
    active_item: str = "''",
) -> str:
    source = (
        f"{_IMPORT}"
        f"{{{{ sidebar_group('{label}', \"{icon}\", {items}, "
        f"expanded={expanded}, active_item={active_item}) }}}}"
    )
    return _render(app, source)


def _sidebar_html(client: FlaskClient) -> str:
    """The rendered #sidebar <nav>...</nav> from the root route."""
    html = client.get("/").data.decode()
    start = html.index('<nav id="sidebar"')
    end = html.index("</nav>", start) + len("</nav>")
    return html[start:end]


# ---------------------------------------------------------------------------
# [T] sidebar_group renders a collapsible group with label, icon, items
# ---------------------------------------------------------------------------


class TestSidebarGroupMacro:
    """sidebar_group(label, icon, items, expanded, active_item) — AC1."""

    def test_renders_label_icon_and_items_with_tailwind(self, app: Flask) -> None:
        html = _render_group(
            app,
            label="Observe",
            icon="<svg id='grp-icon'></svg>",
            items="[{'label': 'Investigations', 'url': '/investigations/'},"
            " {'label': 'Sources', 'url': '/sources/'}]",
        )
        # Group label present.
        assert "Observe" in html
        # Group icon rendered (passed-through SVG).
        assert "grp-icon" in html
        # Both items rendered as links.
        assert 'href="/investigations/"' in html
        assert "Investigations" in html
        assert 'href="/sources/"' in html
        assert "Sources" in html
        # Uses semantic Tailwind tokens (collapsible group container + items).
        assert "sidebar-group" in html
        assert "sidebar-group-items" in html
        assert "text-text-secondary" in html

    def test_expanded_default_shows_items(self, app: Flask) -> None:
        # expanded defaults to true → item list is NOT hidden.
        html = _render_group(app, expanded="true")
        match = re.search(r'<ul class="sidebar-group-items([^"]*)"', html)
        assert match is not None
        assert "hidden" not in match.group(1)

    def test_collapsed_group_hides_items(self, app: Flask) -> None:
        # expanded=false → the group's item <ul> carries `hidden`.
        html = _render_group(app, expanded="false")
        match = re.search(r'<ul class="sidebar-group-items([^"]*)"', html)
        assert match is not None
        assert "hidden" in match.group(1)


# ---------------------------------------------------------------------------
# [T] Groups & membership render in order (FR40)
# ---------------------------------------------------------------------------


class TestGroupsAndMembership:
    """Observe / Learn / Manage groups + their superset items (FR40)."""

    # Spec items per group + the superset routes the product owner retained.
    OBSERVE = {
        "/investigations/": "Investigations",
        "/sources/": "Sources",
        "/health/": "Health",
        "/slo/": "SLO",
        "/services/": "Services",
        "/topology/": "Topology",
    }
    LEARN = {
        "/knowledge/": "Knowledge Base",
        "/metrics/": "Metrics",
        "/analytics/": "Analytics",
        "/reports/executive": "Reports",
        "/handoff/": "Handoff",
    }
    MANAGE = {
        "/spending/": "Spending",
        "/spending/costs": "Cost Insights",
        "/notifications/": "Notifications",
        "/settings/trust/": "Trust",
    }

    def test_group_headers_appear_in_order(self, client: FlaskClient) -> None:
        nav = _sidebar_html(client)
        i_observe = nav.index("Observe")
        i_learn = nav.index("Learn")
        i_manage = nav.index("Manage")
        assert i_observe < i_learn < i_manage, "Groups must be Observe, Learn, Manage"

    def test_observe_first_item_is_investigations(self, client: FlaskClient) -> None:
        # UX spec: Observe first group, Investigations first item.
        nav = _sidebar_html(client)
        i_observe_header = nav.index("Observe")
        first_link = nav.index('href="', i_observe_header)
        assert 'href="/investigations/"' in nav[first_link:first_link + 40]

    def test_observe_group_membership(self, client: FlaskClient) -> None:
        nav = _sidebar_html(client)
        # Slice from Observe header up to the Learn header.
        seg = nav[nav.index("Observe"):nav.index("Learn")]
        for url, label in self.OBSERVE.items():
            assert f'href="{url}"' in seg, f"Observe missing {url}"
            assert label in seg, f"Observe missing label {label}"

    def test_learn_group_membership(self, client: FlaskClient) -> None:
        nav = _sidebar_html(client)
        seg = nav[nav.index("Learn"):nav.index("Manage")]
        for url, label in self.LEARN.items():
            assert f'href="{url}"' in seg, f"Learn missing {url}"
            assert label in seg, f"Learn missing label {label}"

    def test_manage_group_membership(self, client: FlaskClient) -> None:
        nav = _sidebar_html(client)
        seg = nav[nav.index("Manage"):]
        for url, label in self.MANAGE.items():
            assert f'href="{url}"' in seg, f"Manage missing {url}"
            assert label in seg, f"Manage missing label {label}"

    def test_all_fifteen_routes_present(self, client: FlaskClient) -> None:
        # Superset preserved: all 15 live routes remain in the nav.
        nav = _sidebar_html(client)
        for url in {**self.OBSERVE, **self.LEARN, **self.MANAGE}:
            assert f'href="{url}"' in nav, f"Route {url} dropped from sidebar"


# ---------------------------------------------------------------------------
# [T] >= 1200px expanded by default with labels (FR42)
# ---------------------------------------------------------------------------


class TestExpandedAtWideViewport:
    """At >= 1200px the sidebar is expanded with labels (FR42)."""

    def test_sidebar_expanded_width_hook(self, client: FlaskClient) -> None:
        nav = _sidebar_html(client)
        # lg: = 1200px breakpoint → expanded 256px width.
        assert "lg:w-64" in nav

    def test_labels_visible_at_lg(self, client: FlaskClient) -> None:
        nav = _sidebar_html(client)
        # Group headers + item labels reveal at lg: via lg:not-sr-only.
        assert "lg:not-sr-only" in nav
        # Full labels present in the markup.
        assert "Investigations" in nav
        assert "Knowledge Base" in nav
        assert "Spending" in nav


# ---------------------------------------------------------------------------
# [T] < 1200px 64px icon rail with hover tooltip labels
# ---------------------------------------------------------------------------


class TestCollapsedIconRail:
    """At base width (<1200px) the sidebar is a 64px icon rail w/ tooltips."""

    def test_collapsed_rail_width(self, client: FlaskClient) -> None:
        nav = _sidebar_html(client)
        # 64px base rail width (w-16); expands only at lg:.
        assert "w-16" in nav

    def test_items_expose_tooltip_and_icon(self, client: FlaskClient) -> None:
        nav = _sidebar_html(client)
        # Tooltip mechanism: title="<label>" on the nav anchors so the
        # collapsed rail surfaces the label on hover.
        assert 'title="Investigations"' in nav
        assert 'title="Spending"' in nav
        # Labels are sr-only on the rail (revealed at lg:), so icons carry
        # orientation when collapsed.
        assert "sr-only lg:not-sr-only" in nav

    def test_macro_item_label_is_sr_only_on_rail(self, app: Flask) -> None:
        # Isolated-macro proof: each item label span is sr-only by default
        # (icon rail) and reveals at lg:.
        html = _render_group(app)
        assert 'class="sr-only lg:not-sr-only' in html
        assert 'title="Investigations"' in html


# ---------------------------------------------------------------------------
# [T] Hamburger expand uses 200ms transition; <1200px overlays (float) (FR41)
# ---------------------------------------------------------------------------


class TestTransitionAndFloat:
    """200ms transition + float/overlay at base width (FR41)."""

    def test_sidebar_has_200ms_transition(self, client: FlaskClient) -> None:
        nav = _sidebar_html(client)
        assert "transition-all" in nav
        assert "duration-200" in nav
        # Reduced-motion safety preserved from Story 3.2.
        assert "motion-reduce:transition-none" in nav

    def test_sidebar_floats_over_content(self, client: FlaskClient) -> None:
        # `fixed` + a stacking context (z-) means the expanding rail overlays
        # content rather than pushing it at base width (content margin is ml-16).
        nav = _sidebar_html(client)
        match = re.search(r'<nav id="sidebar"[^>]*class="([^"]+)"', nav)
        assert match is not None
        classes = match.group(1)
        assert "fixed" in classes
        assert re.search(r"\bz-\d+\b", classes), "Sidebar needs a z-index to overlay"


# ---------------------------------------------------------------------------
# [T] active_item highlight — aria-current + active style
# ---------------------------------------------------------------------------


class TestActiveItem:
    """active_item marks the current link (aria-current + active style)."""

    def test_active_by_url_gets_aria_current_and_style(self, app: Flask) -> None:
        html = _render_group(
            app,
            items="[{'label': 'Investigations', 'url': '/investigations/'},"
            " {'label': 'Sources', 'url': '/sources/'}]",
            active_item="'/investigations/'",
        )
        # The active anchor carries aria-current="page".
        anchor = re.search(
            r'<a href="/investigations/"[^>]*>', html
        )
        assert anchor is not None
        assert 'aria-current="page"' in anchor.group(0)
        # And an active style: surface-raised bg + primary left border.
        assert "bg-surface-raised" in anchor.group(0)
        assert "border-primary" in anchor.group(0)

    def test_active_by_label_also_matches(self, app: Flask) -> None:
        html = _render_group(
            app,
            items="[{'label': 'Sources', 'url': '/sources/'}]",
            active_item="'Sources'",
        )
        anchor = re.search(r'<a href="/sources/"[^>]*>', html)
        assert anchor is not None
        assert 'aria-current="page"' in anchor.group(0)

    def test_inactive_items_have_no_aria_current(self, app: Flask) -> None:
        html = _render_group(
            app,
            items="[{'label': 'Investigations', 'url': '/investigations/'},"
            " {'label': 'Sources', 'url': '/sources/'}]",
            active_item="'/investigations/'",
        )
        # The non-active anchor must NOT carry aria-current.
        anchor = re.search(r'<a href="/sources/"[^>]*>', html)
        assert anchor is not None
        assert "aria-current" not in anchor.group(0)

    def test_no_active_item_means_no_aria_current(self, app: Flask) -> None:
        html = _render_group(app, active_item="''")
        assert "aria-current" not in html
