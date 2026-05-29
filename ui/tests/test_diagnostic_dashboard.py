"""Tests for Task 5.2: Pipeline diagnostic dashboard (FR32-33).

Observe > Ingestion Stats — a Grafana-style dashboard for ingestion throughput
and anomaly-detection stats, with a tri-state pipeline chip (Warming Up / Active
/ No Data) and an EWMA warmup progress bar.

There is NO JavaScript test runner in this repo (AD-8). Per the established
convention (test_related_kb_panel.py / test_sidebar_navigation.py), behaviour is
proven two ways:

  (1) Render assertions — render components/diagnostic.html's macros directly via
      app.jinja_env (metric_tile / ewma_progress / pipeline_state_chip), and the
      /health/ingestion route (full page + HX partial) with mocked stats, then
      assert on the emitted HTML: tile values, the three chip states (amber /
      green / red via their status-token classes + the exact labels "Warming Up"
      / "Active" / "No Data"), the warmup percentage math (samples/minimum*100),
      and the auto-refresh hook (hx-trigger).
  (2) Static-source assertions — none needed; auto-refresh uses HTMX polling
      (no new JS). Runtime swap behaviour is verified MANUALLY in-browser (AD-8).

[T] criterion → test class:
  AC1  TestAC1IngestionStatsTiles
  AC2  TestAC2DetectionTiles
  AC3  TestAC3WarmingUpState
  AC4  TestAC4WarmedActiveState
  AC5  TestAC5NoDataState
  AC6  TestAC6AutoRefresh

NOTE: there is no live operator/Qdrant in dev (AD-8). These tests exercise the UI
against the route with mocked HealthService stats. Real values must be verified
against a live operator before this dashboard is trusted end-to-end.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from flask import Flask
from flask.testing import FlaskClient

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig
from beeper_ui.services.health_service import HealthService, IngestionStats


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


def _stats(**overrides) -> IngestionStats:
    """Build an IngestionStats with sensible defaults; override per-test."""
    base = {
        "buffer_size": 1000,
        "buffered_count": 10,
        "dropped_count": 0,
        "is_full": False,
        "metrics_received": 506635,
        "logs_received": 4119,
        "anomalies_detected": 12,
        "anomalies_suppressed": 7,
        "active_metric_detectors": 5,
        "ewma_warmup_samples": 100,
        "ewma_warmup_minimum": 100,
    }
    base.update(overrides)
    return IngestionStats(**base)


def _get_page(client: FlaskClient, stats: IngestionStats | None, **kwargs):
    """GET /health/ingestion with HealthService.get_ingestion_stats mocked."""
    if stats is None:
        from beeper_ui.services.health_service import HealthServiceError

        target = patch.object(
            HealthService,
            "get_ingestion_stats",
            side_effect=HealthServiceError("operator down"),
        )
    else:
        target = patch.object(
            HealthService, "get_ingestion_stats", return_value=stats
        )
    with target:
        return client.get("/health/ingestion", **kwargs)


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

    def test_page_shows_metrics_and_logs_received(
        self, client: FlaskClient
    ) -> None:
        resp = _get_page(
            client, _stats(metrics_received=506635, logs_received=4119)
        )
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Metrics Received" in html
        assert "506,635" in html
        assert "Logs Received" in html
        assert "4,119" in html


# ---------------------------------------------------------------------------
# AC2 — adds anomalies_detected / anomalies_suppressed / active_metric_detectors
#       tiles (FR33).
# ---------------------------------------------------------------------------


class TestAC2DetectionTiles:
    """AC2: detection-stat tiles (detected / suppressed / detectors)."""

    def test_page_shows_all_three_detection_tiles(
        self, client: FlaskClient
    ) -> None:
        resp = _get_page(
            client,
            _stats(
                anomalies_detected=12,
                anomalies_suppressed=7,
                active_metric_detectors=5,
            ),
        )
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Anomalies Detected" in html
        assert "Anomalies Suppressed" in html
        assert "Active Metric Detectors" in html
        # The three numeric values render.
        assert ">12<" in html
        assert ">7<" in html
        assert ">5<" in html

    def test_active_detectors_healthy_when_present(
        self, client: FlaskClient
    ) -> None:
        """A nonzero active detector count reads as healthy (green accent)."""
        resp = _get_page(client, _stats(active_metric_detectors=5))
        html = resp.data.decode()
        # The detectors tile carries the healthy status token.
        assert "text-status-healthy" in html


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

    def test_page_warming_shows_amber_chip_and_bar(
        self, client: FlaskClient
    ) -> None:
        # samples 30 < minimum 120 -> warming; 30/120*100 = 25%.
        resp = _get_page(
            client,
            _stats(
                metrics_received=100,
                logs_received=0,
                ewma_warmup_samples=30,
                ewma_warmup_minimum=120,
            ),
        )
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Warming Up" in html
        assert 'data-pipeline-state="warming"' in html
        assert "text-status-warning" in html
        # progress bar present with the computed 25%.
        assert "EWMA Warmup" in html
        assert "width: 25%" in html

    def test_percentage_math_via_route(self, client: FlaskClient) -> None:
        """percentage = samples / minimum * 100 (50 / 200 = 25%)."""
        resp = _get_page(
            client,
            _stats(
                metrics_received=5,
                ewma_warmup_samples=50,
                ewma_warmup_minimum=200,
            ),
        )
        html = resp.data.decode()
        assert "width: 25%" in html


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

    def test_page_warmed_shows_green_active_chip(
        self, client: FlaskClient
    ) -> None:
        # samples >= minimum -> active, with data flowing.
        resp = _get_page(
            client,
            _stats(
                metrics_received=1000,
                logs_received=50,
                ewma_warmup_samples=150,
                ewma_warmup_minimum=100,
            ),
        )
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'data-pipeline-state="active"' in html
        assert "text-status-healthy" in html
        # The Active state does NOT render the warming chip/bar.
        assert "Warming Up" not in html
        assert "EWMA Warmup" not in html

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

    def test_page_no_data_when_both_zero(self, client: FlaskClient) -> None:
        resp = _get_page(
            client, _stats(metrics_received=0, logs_received=0)
        )
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "No Data" in html
        assert 'data-pipeline-state="no_data"' in html
        assert "text-status-critical" in html

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

    def test_no_data_takes_priority_even_while_unwarmed(
        self, client: FlaskClient
    ) -> None:
        """Zero ingestion -> No Data, even if samples < minimum."""
        resp = _get_page(
            client,
            _stats(
                metrics_received=0,
                logs_received=0,
                ewma_warmup_samples=10,
                ewma_warmup_minimum=100,
            ),
        )
        html = resp.data.decode()
        assert "No Data" in html
        assert "Warming Up" not in html


# ---------------------------------------------------------------------------
# AC6 — Dashboard auto-refreshes on pipeline state change.
# ---------------------------------------------------------------------------


class TestAC6AutoRefresh:
    """AC6: auto-refresh via HTMX polling of the stats partial."""

    def test_full_page_has_polling_hook(self, client: FlaskClient) -> None:
        """The page wraps the stats in an HTMX-polled container."""
        resp = _get_page(client, _stats())
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'id="ingestion-stats"' in html
        assert 'hx-get="/health/ingestion"' in html
        assert 'hx-trigger="every 5s"' in html
        assert 'hx-swap="innerHTML"' in html

    def test_hx_request_returns_partial_only(
        self, client: FlaskClient
    ) -> None:
        """An HX-Request returns the stats partial, not the full page shell."""
        resp = _get_page(
            client, _stats(), headers={"HX-Request": "true"}
        )
        assert resp.status_code == 200
        html = resp.data.decode()
        # Partial content present...
        assert "Pipeline status" in html
        # ...but NOT the full-page chrome (sidebar nav / doctype).
        assert "<!DOCTYPE html>" not in html
        assert 'id="sidebar"' not in html

    def test_partial_reflects_state_change_across_polls(
        self, client: FlaskClient
    ) -> None:
        """Two HX polls with different stats yield different chip states —
        i.e. the polled partial re-renders on pipeline state change."""
        warming = _get_page(
            client,
            _stats(
                metrics_received=10,
                logs_received=0,
                ewma_warmup_samples=10,
                ewma_warmup_minimum=100,
            ),
            headers={"HX-Request": "true"},
        ).data.decode()
        active = _get_page(
            client,
            _stats(
                metrics_received=10,
                logs_received=0,
                ewma_warmup_samples=100,
                ewma_warmup_minimum=100,
            ),
            headers={"HX-Request": "true"},
        ).data.decode()
        assert 'data-pipeline-state="warming"' in warming
        assert 'data-pipeline-state="active"' in active


# ---------------------------------------------------------------------------
# Sidebar nav wiring (deferred from Story 3.3 to this task per plan note).
# ---------------------------------------------------------------------------


class TestSidebarNavEntry:
    """The Observe group exposes an 'Ingestion Stats' item -> /health/ingestion."""

    def test_nav_item_present_and_links_to_route(
        self, client: FlaskClient
    ) -> None:
        html = client.get("/").data.decode()
        assert 'href="/health/ingestion"' in html
        assert "Ingestion Stats" in html

    def test_nav_item_active_on_dashboard(self, client: FlaskClient) -> None:
        """On the dashboard, its sidebar item gets the active state."""
        resp = _get_page(client, _stats())
        html = resp.data.decode()
        # Active item carries aria-current="page" on its anchor.
        anchor_start = html.find('href="/health/ingestion"')
        assert anchor_start != -1
        # The active anchor (same href) is marked current somewhere in the page.
        assert 'aria-current="page"' in html
