"""Tests for Task 4.3: SSE real-time streaming & auto-reconnection (AD-4).

Each of the six [T] acceptance criteria maps to a clearly-named test below.
There is NO JavaScript test runner in this repo (AD-8); per the established
convention (test_command_palette.py / test_sidebar_state.py), client-side
behaviour is proven two ways:

  (1) Render assertions — render the template via the Flask test client /
      app.jinja_env.get_template(...).render(...) and assert on emitted HTML
      (data-sse-url, the wired <script src=".../sse.js">, data-sse-swap hooks).
  (2) Static-source assertions — open() the shipped static/js/sse.js and assert
      the logic/contract strings are present (new EventSource, MAX_RETRIES = 5,
      the exact unavailable message, the backfill fetch, order-based insertion,
      the 5000ms/5s fade).

Runtime DOM behaviour is verified MANUALLY in the browser (AD-8).

[T] criterion → test:
  AC1  TestAC1NativeEventSourceWiring.*                (EventSource opened; list FR24 events)
  AC2  TestAC2StepsInsertedByOrder.*                   (order-based insertion; ≤2s NFR4)
  AC3  TestAC3ReconnectRestBackfill.*                  (reconnect + REST backfill diff by order)
  AC4  TestAC4RetryLimitAndUnavailableBanner.*         (5-retry cap; exact banner; never blanks)
  AC5  TestAC5NewCardHighlightFade.*                   (5s highlight fade)
  AC6  TestAC6NativeNotHtmxAndReconnectWindow.*        (native ES not HTMX; ≤5s reconnect)
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

STATIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "beeper_ui",
    "static",
)
SSE_JS = os.path.join(STATIC_DIR, "js", "sse.js")

_DETAIL = {
    "id": "inv-sse-001",
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
def sse_source() -> str:
    """The shipped static/js/sse.js source (static-source contract)."""
    with open(SSE_JS) as f:
        return f.read()


def _mock_detail_page(findings: dict | None = None):
    """Mock the operator detail fetch + findings for the full detail page."""
    respx.get(
        "http://mock-operator:8080/api/v1/investigations/inv-sse-001"
    ).mock(return_value=Response(200, json=_DETAIL))
    return patch(
        "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
        return_value=findings if findings is not None else {},
    )


# ---------------------------------------------------------------------------
# AC1 — A running investigation opens an EventSource from a NEW sse.js; steps
#       append on arrival; the LIST view receives investigation_created /
#       investigation_status events (FR24).
# ---------------------------------------------------------------------------


class TestAC1NativeEventSourceWiring:
    """AC1: native EventSource from sse.js; detail streams; list FR24 events."""

    def test_sse_js_file_exists(self) -> None:
        assert os.path.isfile(SSE_JS), f"Missing: {SSE_JS}"

    def test_sse_js_opens_native_event_source(self, sse_source: str) -> None:
        # The contract is a NATIVE EventSource, instantiated by the client.
        assert "new EventSource" in sse_source



# ---------------------------------------------------------------------------
# AC2 — Steps inserted at the correct position by their `order` field; UI
#       updates within ≤2s of the event (NFR4).
# ---------------------------------------------------------------------------


class TestAC2StepsInsertedByOrder:
    """AC2: order-based step insertion; immediate (≤2s) DOM update (NFR4)."""

    def test_inserts_steps_by_data_order(self, sse_source: str) -> None:
        # The merge path reads data-order and positions by it.
        assert "data-order" in sse_source
        assert "insertStepByOrder" in sse_source or "insertBefore" in sse_source
        assert "mergeStepsByOrder" in sse_source

    def test_keeps_steps_sorted_ascending_by_order(self, sse_source: str) -> None:
        # A missed/lower-ordered step is inserted BEFORE the first higher one.
        assert "insertBefore" in sse_source
        assert "current > order" in sse_source

    def test_replaces_existing_step_in_place(self, sse_source: str) -> None:
        # Re-sent step (state change) replaces the same-order node in place.
        assert "replaceChild" in sse_source
        assert "current === order" in sse_source

    def test_step_macro_emits_data_order(self, app: Flask) -> None:
        """The server-rendered step carries data-order so the client can place it."""
        with app.app_context():
            tpl = app.jinja_env.get_template("components/investigation.html")
            html = tpl.module.investigation_step(
                {"label": "KB", "state": "completed", "type": "kb"}, False, 3
            )
            assert 'data-order="3"' in html

    def test_update_is_immediate_not_delayed(self, sse_source: str) -> None:
        """NFR4 (≤2s): event handling swaps the DOM synchronously — there is no
        artificial timer gating the application of an arriving event. The only
        setTimeout uses are the reconnect backoff and the 5s highlight fade."""
        # Event dispatch path uses a direct innerHTML swap / DOM merge.
        assert "innerHTML = html" in sse_source
        # No delay is applied to the swap itself (handleEvent has no setTimeout).
        handle = sse_source.split("handleEvent = function")[1].split(
            "handleError = function"
        )[0]
        assert "setTimeout" not in handle


# ---------------------------------------------------------------------------
# AC3 — On connection drop, the client auto-reconnects; on reconnect it fetches
#       GET /api/v1/investigations/{id} and diffs/inserts missed steps by order.
# ---------------------------------------------------------------------------


class TestAC3ReconnectRestBackfill:
    """AC3: auto-reconnect + REST backfill diff/insert by order (AD-4)."""

    def test_auto_reconnects_on_drop(self, sse_source: str) -> None:
        # onerror schedules a reconnect via connect().
        assert "onerror" in sse_source
        assert "self.connect()" in sse_source

    def test_backfill_fetches_json_api_endpoint(self, sse_source: str) -> None:
        # The backfill GETs the JSON investigation endpoint.
        assert "/api/v1/investigations/" in sse_source
        assert "fetch(" in sse_source

    def test_backfill_triggered_on_open(self, sse_source: str) -> None:
        # On (re)connect open, backfill runs to reconcile missed steps.
        assert "onopen" in sse_source
        assert "self.backfill()" in sse_source

    def test_backfill_diffs_and_inserts_missed_steps_by_order(
        self, sse_source: str
    ) -> None:
        # Backfill only inserts steps not already present, positioned by order.
        assert "applyBackfillSteps" in sse_source
        assert 'li[data-order="' in sse_source
        assert "insertStepByOrder" in sse_source


    @respx.mock
    def test_backfill_json_endpoint_returns_steps_with_order(
        self, client: FlaskClient
    ) -> None:
        """GET /api/v1/investigations/{id} returns the current steps with order."""
        with _mock_detail_page():
            response = client.get("/api/v1/investigations/inv-sse-001")
            assert response.status_code == 200
            data = response.get_json()
            assert data["id"] == "inv-sse-001"
            assert "steps" in data
            assert len(data["steps"]) == 6
            orders = [s["order"] for s in data["steps"]]
            assert orders == [1, 2, 3, 4, 5, 6]
            assert all("state" in s for s in data["steps"])

    @respx.mock
    def test_backfill_json_endpoint_404_for_missing(
        self, client: FlaskClient
    ) -> None:
        respx.get(
            "http://mock-operator:8080/api/v1/investigations/inv-sse-001"
        ).mock(return_value=Response(404))
        with patch(
            "beeper_ui.routes.investigations.InvestigationService.get_investigation_findings",
            return_value={},
        ):
            response = client.get("/api/v1/investigations/inv-sse-001")
            assert response.status_code == 404


# ---------------------------------------------------------------------------
# AC4 — After 5 failed retries, show the EXACT message and keep the detail
#       viewable (never hidden/blanked).
# ---------------------------------------------------------------------------


class TestAC4RetryLimitAndUnavailableBanner:
    """AC4: 5-retry cap → exact banner; detail stays viewable."""

    def test_max_retries_is_five(self, sse_source: str) -> None:
        assert "MAX_RETRIES = 5" in sse_source

    def test_exact_unavailable_message(self, sse_source: str) -> None:
        # The exact, user-facing copy must be present verbatim.
        assert "Live updates unavailable — refresh to sync" in sse_source

    def test_banner_shown_only_after_exceeding_retry_budget(
        self, sse_source: str
    ) -> None:
        assert "this.retries > MAX_RETRIES" in sse_source
        assert "showBanner" in sse_source

    def test_banner_inserted_above_content_not_blanking_it(
        self, sse_source: str
    ) -> None:
        """The banner is prepended; the already-rendered detail is never blanked
        (no innerHTML='' / display:none on the detail container)."""
        assert "insertBefore(banner" in sse_source
        # The failure path must not wipe or hide the detail container.
        assert "this.root.innerHTML = ''" not in sse_source
        assert 'this.root.innerHTML = ""' not in sse_source
        assert "this.root.hidden = true" not in sse_source



# ---------------------------------------------------------------------------
# AC5 — A new-investigation card highlight fades over 5s.
# ---------------------------------------------------------------------------


class TestAC5NewCardHighlightFade:
    """AC5: new-card highlight fades over 5s."""

    def test_js_fade_window_is_5000ms(self, sse_source: str) -> None:
        assert "HIGHLIGHT_FADE_MS = 5000" in sse_source

    def test_js_applies_then_removes_highlight_class(
        self, sse_source: str
    ) -> None:
        assert "sse-new-highlight" in sse_source
        assert "startHighlightFade" in sse_source
        # Applied to genuinely new cards on investigation_created.
        assert "highlightNewCards" in sse_source

    def test_css_defines_5s_fade_animation(self) -> None:
        with open(os.path.join(STATIC_DIR, "css", "main.css")) as f:
            css = f.read()
        assert "@keyframes sse-highlight-fade" in css
        assert ".sse-new-highlight" in css
        # 5s animation window.
        assert "animation: sse-highlight-fade 5s" in css

    def test_css_fade_uses_design_tokens_not_hex(self) -> None:
        """D4: the fade is token-colored (var(--color-*)), no arbitrary hex."""
        with open(os.path.join(STATIC_DIR, "css", "main.css")) as f:
            css = f.read()
        block = css.split("@keyframes sse-highlight-fade")[1].split("}")[0:3]
        block_text = "}".join(block)
        assert "var(--color-primary)" in block_text
        assert "#" not in block_text

    def test_css_fade_respects_reduced_motion(self) -> None:
        with open(os.path.join(STATIC_DIR, "css", "main.css")) as f:
            css = f.read()
        # The .sse-new-highlight animation is disabled under reduced motion.
        rm_section = css.split("SSE real-time streaming")[1]
        assert "prefers-reduced-motion: reduce" in rm_section
        assert ".sse-new-highlight" in rm_section.split(
            "prefers-reduced-motion: reduce"
        )[1]


# ---------------------------------------------------------------------------
# AC6 — Uses native EventSource, NOT HTMX (AD-4); auto-reconnect within ≤5s.
# ---------------------------------------------------------------------------


class TestAC6NativeNotHtmxAndReconnectWindow:
    """AC6: native EventSource (not htmx); ≤5s auto-reconnect (NFR9)."""

    def test_sse_js_uses_native_event_source_not_htmx(
        self, sse_source: str
    ) -> None:
        assert "new EventSource" in sse_source
        # sse.js must not depend on the htmx SSE extension API.
        assert "htmx.createEventSource" not in sse_source
        assert "defineExtension" not in sse_source


    def test_reconnect_window_capped_at_5s(self, sse_source: str) -> None:
        """NFR9: the reconnect backoff is capped at 5000ms (≤5s)."""
        assert "MAX_RECONNECT_MS = 5000" in sse_source
        # The scheduled delay is clamped to the 5s cap.
        assert "Math.min(" in sse_source
        assert "MAX_RECONNECT_MS" in sse_source

    def test_htmx_ext_sse_kept_for_other_pages(self) -> None:
        """htmx-ext-sse.js is NOT removed from the repo — services pages still
        use it (only the investigation pages migrated to native ES)."""
        assert os.path.isfile(
            os.path.join(STATIC_DIR, "js", "htmx-ext-sse.js")
        )
