"""Tests for Task 4.4: Related Knowledge Base panel (FR26 / AD-5).

Each of the five [T] acceptance criteria maps to a clearly-named test class
below. There is NO JavaScript test runner in this repo (AD-8); per the
established convention (test_command_palette.py / test_sse_streaming.py),
client-side behaviour is proven two ways:

  (1) Render assertions — render components/kb.html's kb_panel(...) (directly via
      app.jinja_env or through the /related-kb route) and assert on emitted HTML:
      the "N Related KB Entries" count string, the lg:fixed lg:bottom-0 (wide) +
      static (narrow) utility classes, entry titles + relevance, the per-entry
      expandable <details> markup, and the "0 Related KB Entries" zero-state.
  (2) Static-source assertions — open() static/js/kb-panel.js and assert the
      expand-toggle logic (aria-expanded flip, max-height grow, idempotent bind).

Runtime responsive/expand DOM behaviour is verified MANUALLY in-browser (AD-8).

[T] criterion → test class:
  AC1  TestAC1WideFixedBottomBarExpandsUpward
  AC2  TestAC2NarrowInlineBelowTimeline
  AC3  TestAC3EntryTitlesWithRelevance
  AC4  TestAC4ZeroResultsShowsCount
  AC5  TestAC5EntryDetailExpandsInPanel

NOTE (Q2/AD-5): the KBQueryStep -> investigations Qdrant read-path reliability
is an OPEN question only verifiable against a live operator/Qdrant. These tests
exercise the UI against the existing route + representative mock entries; the
live read path must be verified separately before this is trusted end-to-end.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
import respx
from flask import Flask
from flask.testing import FlaskClient
from httpx import Response

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig
from beeper_ui.services.kb_surfacing_service import KBSurfacingResult

STATIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "beeper_ui",
    "static",
)
KB_PANEL_JS = os.path.join(STATIC_DIR, "js", "kb-panel.js")

MOCK_DETAIL = {
    "id": "inv-detail-001",
    "status": "investigating",
    "service": "payments",
    "severity": "high",
    "condition": "High error rate detected",
    "started_at": "2026-05-20T12:00:00Z",
    "completed_at": None,
    "triggered_at": "2026-05-20T11:55:00Z",
    "message": "Querying knowledge base",
    "signal_count": 12,
}


@pytest.fixture
def app() -> Flask:
    return create_app(TestingConfig)


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    with app.test_client() as c:
        yield c


@pytest.fixture(scope="module")
def kb_panel_source() -> str:
    """The shipped static/js/kb-panel.js source (static-source contract)."""
    with open(KB_PANEL_JS) as f:
        return f.read()


def _render_panel(app: Flask, **kwargs) -> str:
    """Render components/kb.html kb_panel(...) directly with given kwargs."""
    with app.app_context():
        tpl = app.jinja_env.get_template("components/kb.html")
        return tpl.module.kb_panel(**kwargs)


def _entry(
    entry_id: str,
    title: str,
    *,
    validation: str = "AI-generated",
    relevance: float | None = 0.8,
    service: str = "payments",
    preview: str = "Past context and documented resolution.",
    entry_type: str = "investigation",
) -> dict:
    return {
        "entry_id": entry_id,
        "title": title,
        "entry_type": entry_type,
        "service": service,
        "validation_status": validation,
        "relevance_score": relevance,
        "composite_score": (relevance or 0.0),
        "content_preview": preview,
        "created_at": "2026-03-01",
        "link": f"/knowledge/{entry_id}",
    }


def _route_kwargs(surfacing_result: KBSurfacingResult | None):
    """Patch context for the /related-kb route to return surfacing_result."""
    return [
        patch(
            "beeper_ui.routes.investigations.InvestigationService."
            "get_investigation_findings",
            return_value={},
        ),
        patch(
            "beeper_ui.routes.investigations.KBSurfacingService.surface_entries",
            return_value=surfacing_result,
        ),
        patch("beeper_ui.routes.investigations.KBSurfacingService.close"),
        patch(
            "beeper_ui.routes.investigations.KBSurfacingService."
            "mark_novel_investigation",
        ),
    ]


# ---------------------------------------------------------------------------
# AC1 — Viewport >1200px: a FIXED bottom bar reading "N Related KB Entries",
#       rendered via the NEW kb_panel(entries, expanded) macro in the NEW
#       components/kb.html; clicking it expands UPWARD (FR26).
# ---------------------------------------------------------------------------


class TestAC1WideFixedBottomBarExpandsUpward:
    """AC1: wide-screen anchored fixed bottom bar; expands upward via toggle."""

    def test_kb_html_component_exists(self) -> None:
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "beeper_ui",
            "templates",
            "components",
            "kb.html",
        )
        assert os.path.isfile(path), f"Missing: {path}"

    def test_macro_renders_count_bar_string(self, app: Flask) -> None:
        html = _render_panel(
            app, entries=[_entry("kb-1", "A"), _entry("kb-2", "B")]
        )
        assert "2 Related KB Entries" in html

    def test_wide_screen_is_fixed_bottom_bar(self, app: Flask) -> None:
        """>1200px (Tailwind lg): position fixed, anchored to viewport bottom."""
        html = _render_panel(app, entries=[_entry("kb-1", "A")])
        assert "lg:fixed" in html
        assert "lg:bottom-0" in html

    def test_floating_surface_overlay_elevation(self, app: Flask) -> None:
        """Floating panel uses bg-surface-overlay per the UX elevation table."""
        html = _render_panel(app, entries=[_entry("kb-1", "A")])
        assert "bg-surface-overlay" in html

    def test_toggle_controls_body_for_upward_expand(self, app: Flask) -> None:
        """A toggle button (aria-controls the body) drives the expand; the body
        sits ABOVE the bar in source order (order-first) so it grows upward
        while the bar is order-last."""
        html = _render_panel(app, entries=[_entry("kb-1", "A")])
        assert 'data-kb-panel-toggle' in html
        assert 'aria-controls="kb-panel-body"' in html
        # Body appears before the bar (order-first) and bar is order-last.
        assert "order-first" in html
        assert "order-last" in html
        body_pos = html.find("kb-panel-body")
        bar_pos = html.find("kb-panel-bar")
        assert body_pos < bar_pos

    def test_panel_js_wired_on_detail_page(self, client: FlaskClient) -> None:
        with respx.mock:
            respx.get(
                "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
            ).mock(return_value=Response(200, json=MOCK_DETAIL))
            with patch(
                "beeper_ui.routes.investigations.InvestigationService."
                "get_investigation_findings",
                return_value={},
            ):
                resp = client.get("/investigations/inv-detail-001")
                assert resp.status_code == 200
                assert "js/kb-panel.js" in resp.data.decode()

    def test_panel_js_flips_aria_expanded(self, kb_panel_source: str) -> None:
        """The toggle flips aria-expanded — the FR26 expand interaction."""
        assert 'setAttribute("aria-expanded"' in kb_panel_source
        assert 'data-expanded' in kb_panel_source

    def test_panel_js_grows_body_upward_via_max_height(
        self, kb_panel_source: str
    ) -> None:
        """Expanding swaps max-h-0 -> max-h-96 on the (above-bar) body so it
        grows upward; collapsing reverses it."""
        assert "max-h-96" in kb_panel_source
        assert "max-h-0" in kb_panel_source

    def test_panel_js_binds_idempotently_after_htmx_swap(
        self, kb_panel_source: str
    ) -> None:
        """Panel arrives via HTMX (lazy + kb-update SSE); re-bind must not
        double-wire (idempotent via a bound marker)."""
        assert "htmx:afterSwap" in kb_panel_source
        assert "data-kb-bound" in kb_panel_source


# ---------------------------------------------------------------------------
# AC2 — Viewport <=1200px: the panel renders INLINE below the timeline (static,
#       not fixed).
# ---------------------------------------------------------------------------


class TestAC2NarrowInlineBelowTimeline:
    """AC2: narrow-screen inline/static panel (fixed only at lg)."""

    def test_default_is_static_not_fixed(self, app: Flask) -> None:
        """Default (narrow) positioning is static; fixed is gated behind lg:."""
        html = _render_panel(app, entries=[_entry("kb-1", "A")])
        assert " static " in html or "block static" in html
        # The bare `fixed` utility (which would apply at ALL widths) is absent;
        # fixed is only ever lg:fixed.
        assert "lg:fixed" in html
        assert "class=\"kb-panel block static" in html

    def test_route_swaps_panel_into_inline_container(
        self, client: FlaskClient
    ) -> None:
        """The /related-kb partial renders the panel (kb_panel) as the swapped
        content for the inline #related-kb container."""
        with respx.mock:
            respx.get(
                "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
            ).mock(return_value=Response(200, json=MOCK_DETAIL))
            sr = KBSurfacingResult(
                entries=[_entry("kb-1", "Inline Entry")],
                is_novel=False,
                query_text="x",
                investigation_id="inv-detail-001",
            )
            ctxs = _route_kwargs(sr)
            for c in ctxs:
                c.start()
            try:
                resp = client.get(
                    "/investigations/inv-detail-001/related-kb"
                )
            finally:
                for c in ctxs:
                    c.stop()
            assert resp.status_code == 200
            html = resp.data.decode()
            assert 'id="kb-panel"' in html
            # static (narrow default) AND lg:fixed (wide) both present.
            assert "static" in html
            assert "lg:fixed" in html

    def test_detail_container_keeps_lazyload_and_sse_hook(
        self, client: FlaskClient
    ) -> None:
        """The inline #related-kb container preserves hx-get lazy-load and the
        data-sse-swap="kb-update" hook from Task 4.3."""
        with respx.mock:
            respx.get(
                "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
            ).mock(return_value=Response(200, json=MOCK_DETAIL))
            with patch(
                "beeper_ui.routes.investigations.InvestigationService."
                "get_investigation_findings",
                return_value={},
            ):
                resp = client.get("/investigations/inv-detail-001")
                html = resp.data.decode()
                assert 'id="related-kb"' in html
                assert 'hx-trigger="load"' in html
                assert 'data-sse-swap="kb-update"' in html


# ---------------------------------------------------------------------------
# AC3 — The panel shows KBQueryStep results (entry titles WITH relevance
#       context) — AD-5.
# ---------------------------------------------------------------------------


class TestAC3EntryTitlesWithRelevance:
    """AC3: entry titles rendered with relevance + validation context."""

    def test_titles_rendered(self, app: Flask) -> None:
        html = _render_panel(
            app,
            entries=[
                _entry("kb-1", "Payments Runbook"),
                _entry("kb-2", "Payment Error Guide"),
            ],
        )
        assert "Payments Runbook" in html
        assert "Payment Error Guide" in html

    def test_relevance_context_shown(self, app: Flask) -> None:
        """Relevance score is shown as a percentage with explicit context."""
        html = _render_panel(
            app, entries=[_entry("kb-1", "A", relevance=0.88)]
        )
        assert "88% relevant" in html

    def test_validation_status_context_shown(self, app: Flask) -> None:
        html = _render_panel(
            app,
            entries=[
                _entry("kb-1", "Proven", validation="proven"),
                _entry("kb-2", "Human", validation="human-confirmed"),
                _entry("kb-3", "Ai", validation="AI-generated"),
            ],
        )
        assert "proven" in html
        assert "human-confirmed" in html
        assert "AI-generated" in html

    def test_relevance_omitted_when_none(self, app: Flask) -> None:
        """A None relevance_score does not emit a percent-relevance string.

        (The "Relevant" feedback button text/class is unrelated and stays.)
        """
        html = _render_panel(
            app, entries=[_entry("kb-1", "No Score", relevance=None)]
        )
        assert "% relevant" not in html
        assert "kb-relevance" not in html

    def test_ranking_indicator_present(self, app: Flask) -> None:
        html = _render_panel(app, entries=[_entry("kb-1", "A")])
        assert "Ranked by relevance" in html

    def test_route_renders_ranked_entries(self, client: FlaskClient) -> None:
        """End-to-end: the /related-kb route surfaces titles + relevance."""
        with respx.mock:
            respx.get(
                "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
            ).mock(return_value=Response(200, json=MOCK_DETAIL))
            sr = KBSurfacingResult(
                entries=[
                    _entry("kb-1", "Payments Runbook", relevance=0.8),
                    _entry("kb-2", "Payment Error Guide", relevance=0.9),
                ],
                is_novel=False,
                query_text="x",
                investigation_id="inv-detail-001",
            )
            ctxs = _route_kwargs(sr)
            for c in ctxs:
                c.start()
            try:
                resp = client.get(
                    "/investigations/inv-detail-001/related-kb"
                )
            finally:
                for c in ctxs:
                    c.stop()
            assert resp.status_code == 200
            html = resp.data.decode()
            assert "Payments Runbook" in html
            assert "Payment Error Guide" in html
            assert "2 Related KB Entries" in html


# ---------------------------------------------------------------------------
# AC4 — 0 results -> show "0 Related KB Entries" (count visible, panel NOT
#       hidden).
# ---------------------------------------------------------------------------


class TestAC4ZeroResultsShowsCount:
    """AC4: zero-state shows the count bar (never hidden)."""

    def test_zero_count_string(self, app: Flask) -> None:
        html = _render_panel(app, entries=[])
        assert "0 Related KB Entries" in html

    def test_zero_state_still_renders_panel(self, app: Flask) -> None:
        """The panel surface + count bar are present even at N=0."""
        html = _render_panel(app, entries=[])
        assert 'id="kb-panel"' in html
        assert "kb-panel-bar" in html
        # Not hidden / collapsed away — the bar is in the markup.
        assert "0 Related KB Entries" in html

    def test_zero_with_novel_shows_count_and_note(self, app: Flask) -> None:
        """A novel issue (0 entries) still shows the count AND the novel note
        inside the expandable region."""
        html = _render_panel(app, entries=[], is_novel=True)
        assert "0 Related KB Entries" in html
        assert "kb-novel-issue" in html
        assert "novel issue" in html

    def test_route_zero_state(self, client: FlaskClient) -> None:
        with respx.mock:
            respx.get(
                "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
            ).mock(return_value=Response(200, json=MOCK_DETAIL))
            sr = KBSurfacingResult(
                entries=[],
                is_novel=True,
                query_text="x",
                investigation_id="inv-detail-001",
            )
            ctxs = _route_kwargs(sr)
            for c in ctxs:
                c.start()
            try:
                resp = client.get(
                    "/investigations/inv-detail-001/related-kb"
                )
            finally:
                for c in ctxs:
                    c.stop()
            assert resp.status_code == 200
            assert b"0 Related KB Entries" in resp.data

    def test_operator_failure_still_shows_zero_count(
        self, client: FlaskClient
    ) -> None:
        """Even when surfacing fails entirely, the panel shows 0 (not blank)."""
        import httpx

        with respx.mock:
            respx.get(
                "http://mock-operator:8080/api/v1/investigations/inv-detail-001"
            ).mock(side_effect=httpx.ConnectError("Connection refused"))
            resp = client.get("/investigations/inv-detail-001/related-kb")
            assert resp.status_code == 200
            assert b"0 Related KB Entries" in resp.data


# ---------------------------------------------------------------------------
# AC5 — Clicking an entry expands its detail IN-PANEL (past context /
#       resolution / service).
# ---------------------------------------------------------------------------


class TestAC5EntryDetailExpandsInPanel:
    """AC5: per-entry expandable detail (native <details>/<summary>)."""

    def test_entry_uses_native_details_summary(self, app: Flask) -> None:
        """Each entry is an expandable <details> with a clickable <summary> —
        keyboard-accessible in-panel expansion, no JS required."""
        html = _render_panel(app, entries=[_entry("kb-1", "Timeout pattern")])
        assert "<details" in html
        assert "<summary" in html
        assert "kb-entry-summary" in html

    def test_entry_detail_shows_service(self, app: Flask) -> None:
        html = _render_panel(
            app, entries=[_entry("kb-1", "A", service="cartservice")]
        )
        assert "kb-entry-service" in html
        assert "cartservice" in html

    def test_entry_detail_shows_past_context(self, app: Flask) -> None:
        """The expanded detail shows the entry's past context / resolution."""
        html = _render_panel(
            app,
            entries=[
                _entry(
                    "kb-1",
                    "A",
                    preview="Documented resolution: restart the pool.",
                )
            ],
        )
        assert "kb-entry-context" in html
        assert "Documented resolution: restart the pool." in html

    def test_entry_detail_has_open_full_entry_link(self, app: Flask) -> None:
        html = _render_panel(app, entries=[_entry("kb-1", "A")])
        assert 'href="/knowledge/kb-1"' in html
        assert 'target="_blank"' in html

    def test_feedback_affordance_preserved(self, app: Flask) -> None:
        """sendKBFeedback relevant / not-relevant buttons are preserved in the
        per-entry detail (existing JS contract)."""
        html = _render_panel(app, entries=[_entry("kb-fb-1", "A")])
        assert "kb-feedback-relevant" in html
        assert "kb-feedback-not-relevant" in html
        assert "sendKBFeedback('kb-fb-1', true)" in html
        assert "sendKBFeedback('kb-fb-1', false)" in html
        assert 'data-entry-id="kb-fb-1"' in html
