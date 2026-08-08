"""Tests for Task 5.2: Pipeline diagnostic dashboard (FR32-33).

Observe > Ingestion Stats — a Grafana-style dashboard for ingestion throughput
and anomaly-detection stats, with a tri-state pipeline chip (Warming Up / Active
/ No Data) and an EWMA warmup progress bar.

Task 6.3 (D13/D14) retired the Jinja `/health/ingestion` route (full page +
HTMX partial) in favor of the React view at `/app/ingestion-stats`; the bare
URL now 302-redirects there (`react_registry.py`). Every test in this file
that exercised `/health/ingestion` directly — tile/chip/progress-bar
rendering across the tri-state pipeline logic, the auto-refresh hx-trigger
wiring, and the sidebar's "active on this page" state — tested that now-
deleted render path and has been removed; the equivalent tri-state precedence
logic (formerly `_pipeline_view()`) now lives client-side in React
(`ui/frontend/src/lib/ingestion/pipeline-view.ts`), out of scope for this
Python test file.

What remains here still exercises real, live behaviour:

  (1) Render assertions — render components/diagnostic.html's macros directly
      via app.jinja_env (metric_tile / ewma_progress / pipeline_state_chip).
      That template file was NOT deleted (only the full-page/partial
      templates that composed it were), so these macro-level unit tests are
      still valid, still exercise real Jinja rendering, and still guard the
      status-token classes + exact labels ("Warming Up" / "Active" /
      "No Data") and the warmup percentage math (samples/minimum*100).
  (2) The sidebar nav item — GET `/` (still a live, un-migrated Jinja page)
      links to Ingestion Stats. Task 6.3 rewired this link straight to
      `/app/ingestion-stats` (the React route) rather than the bare,
      redirecting `/health/ingestion` URL, so the assertion here was updated
      to match.

[T] criterion → test class:
  AC1  TestAC1IngestionStatsTiles (macro-level tests only; route-level
       assertions retired, see module docstring above)
  AC3  TestAC3WarmingUpState (macro-level tests only)
  AC4  TestAC4WarmedActiveState (macro-level tests only)
  AC5  TestAC5NoDataState (macro-level tests only)

AC2 (TestAC2DetectionTiles) and AC6 (TestAC6AutoRefresh) were entirely
route-level (no macro-only coverage existed for either) and have been
removed in full.
"""

from __future__ import annotations

import pytest
from flask import Flask
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


# --- macro render helpers ---------------------------------------------------


def _render_macro(app: Flask, name: str, **kwargs) -> str:
    """Render a components/diagnostic.html macro directly with given kwargs."""
    with app.app_context():
        tpl = app.jinja_env.get_template("components/diagnostic.html")
        return getattr(tpl.module, name)(**kwargs)


# ---------------------------------------------------------------------------
# AC1 — Observe > Ingestion Stats shows metrics_received / logs_received via a
#       NEW metric_tile(label, value, status, trend) macro in a NEW
#       components/diagnostic.html (FR32).
# ---------------------------------------------------------------------------


class TestAC1IngestionStatsTiles:
    """AC1: metrics_received / logs_received tiles via metric_tile macro."""

    def test_diagnostic_component_exists(self) -> None:
        import os

        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "beeper_ui",
            "templates",
            "components",
            "diagnostic.html",
        )
        assert os.path.isfile(path), f"Missing: {path}"

    def test_metric_tile_macro_renders_label_value(self, app: Flask) -> None:
        html = _render_macro(
            app, "metric_tile", label="Metrics Received", value="506,635"
        )
        assert "Metrics Received" in html
        assert "506,635" in html
        assert "metric-tile" in html

    def test_metric_tile_accepts_status_and_trend(self, app: Flask) -> None:
        html = _render_macro(
            app,
            "metric_tile",
            label="Logs Received",
            value="4,119",
            status="healthy",
            trend="+12% vs last hour",
        )
        assert 'data-status="healthy"' in html
        assert "text-status-healthy" in html
        assert "+12% vs last hour" in html


# ---------------------------------------------------------------------------
# AC3 — Warming up (samples < minimum): an ewma_progress(percentage, status) bar
#       + an amber "Warming Up" chip; percentage = samples / minimum * 100.
# ---------------------------------------------------------------------------


class TestAC3WarmingUpState:
    """AC3: warming state — amber chip + progress bar with correct percent."""

    def test_chip_macro_warming_is_amber(self, app: Flask) -> None:
        html = _render_macro(app, "pipeline_state_chip", state="warming")
        assert "Warming Up" in html
        assert "text-status-warning" in html  # amber
        assert 'data-pipeline-state="warming"' in html

    def test_ewma_progress_macro_renders_percentage(self, app: Flask) -> None:
        # 25 / 100 * 100 = 25%
        html = _render_macro(
            app, "ewma_progress", percentage=25, status="warning"
        )
        assert "25%" in html
        assert "width: 25%" in html
        assert 'aria-valuenow="25"' in html
        assert "bg-status-warning" in html

    def test_ewma_progress_clamps_above_100(self, app: Flask) -> None:
        html = _render_macro(
            app, "ewma_progress", percentage=140, status="healthy"
        )
        assert "width: 100%" in html
        assert 'aria-valuenow="100"' in html


# ---------------------------------------------------------------------------
# AC4 — Warmed (samples >= minimum): a green "Active" chip, visually distinct.
# ---------------------------------------------------------------------------


class TestAC4WarmedActiveState:
    """AC4: warmed state — green Active chip, distinct from warming."""

    def test_chip_macro_active_is_green(self, app: Flask) -> None:
        html = _render_macro(app, "pipeline_state_chip", state="active")
        assert "Active" in html
        assert "text-status-healthy" in html  # green
        assert 'data-pipeline-state="active"' in html

    def test_active_distinct_from_warming(self, app: Flask) -> None:
        """Active (green) and Warming (amber) chips use distinct tokens/labels."""
        active = _render_macro(app, "pipeline_state_chip", state="active")
        warming = _render_macro(app, "pipeline_state_chip", state="warming")
        assert "text-status-healthy" in active
        assert "text-status-warning" in warming
        assert active != warming


# ---------------------------------------------------------------------------
# AC5 — metrics_received == 0 && logs_received == 0: a red "No Data" chip,
#       distinct from both other states.
# ---------------------------------------------------------------------------


class TestAC5NoDataState:
    """AC5: no-data state — red No Data chip, distinct from warming/active."""

    def test_chip_macro_no_data_is_red(self, app: Flask) -> None:
        html = _render_macro(app, "pipeline_state_chip", state="no_data")
        assert "No Data" in html
        assert "text-status-critical" in html  # red
        assert 'data-pipeline-state="no_data"' in html

    def test_no_data_distinct_from_other_two(self, app: Flask) -> None:
        """The three chips use three distinct status tokens + labels."""
        no_data = _render_macro(app, "pipeline_state_chip", state="no_data")
        warming = _render_macro(app, "pipeline_state_chip", state="warming")
        active = _render_macro(app, "pipeline_state_chip", state="active")
        assert "text-status-critical" in no_data
        assert "text-status-warning" in warming
        assert "text-status-healthy" in active
        # All three distinct.
        assert len({no_data, warming, active}) == 3


# ---------------------------------------------------------------------------
# Sidebar nav wiring (deferred from Story 3.3 to this task per plan note).
# ---------------------------------------------------------------------------


class TestSidebarNavEntry:
    """The Observe group exposes an 'Ingestion Stats' item.

    Task 6.3 (D13/D14) rewired this link to point directly at the React
    route (`/app/ingestion-stats`) rather than the bare, redirecting
    `/health/ingestion` URL — see `components/layout.html`'s "Task 6.3"
    comment. The dashboard's own "active nav item" state (formerly asserted
    here by visiting `/health/ingestion` and checking for
    `aria-current="page"`) no longer applies: that page is now rendered by
    React at `/app/ingestion-stats`, and React-side active-nav-item state is
    out of scope for this Python test file.
    """

    def test_nav_item_present_and_links_to_route(
        self, client: FlaskClient
    ) -> None:
        html = client.get("/").data.decode()
        assert 'href="/app/ingestion-stats"' in html
        assert "Ingestion Stats" in html
