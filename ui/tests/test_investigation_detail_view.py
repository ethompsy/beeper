"""Tests for Task 4.2: Investigation detail — summary header & step timeline.

Maps each [T] acceptance criterion to named tests:

  AC1  summary_header(inv) renders service/severity/signal-count/status with NO
       SSE dependency (FR23); breadcrumb reads "Investigations > INV-{id}".
  AC2  Steps render via investigation_step(step, is_first_evidence, order) in
       components/investigation.html, each with a 3px type-colored LEFT border:
         metric=primary, log=status-healthy, kb=status-warning,
         correlation=primary-hover, summary=status-muted.
  AC3  Evidence values render in font-mono; service names render as labels on a
       surface-raised background (FR25).
  AC4  conclusion_block(inv) shows root cause / affected services /
       correlated-signal count, visually distinct from steps.
  AC5  Completed steps render immediately so the page is NEVER blank (NFR7) —
       server-rendered, not dependent on the live stream.

Test pattern follows repo convention (test_investigation_list_view.py):
  - Render assertions via app.jinja_env.get_template().render()
  - Static-source assertions for source-level contracts
  - No JS runner (AD-7 / AD-8)
"""

from __future__ import annotations

import os

import pytest
from flask import Flask

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig
from beeper_ui.services.investigation_service import InvestigationDetail

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "beeper_ui",
    "templates",
)
INVESTIGATION_COMPONENT = os.path.join(
    TEMPLATES_DIR, "components", "investigation.html"
)
STEP_TIMELINE_PARTIAL = os.path.join(
    TEMPLATES_DIR, "investigations", "_step_timeline.html"
)


@pytest.fixture
def app() -> Flask:
    return create_app(TestingConfig)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_DETAIL = {
    "id": "inv-detail-001",
    "status": "investigating",
    "service": "payments",
    "severity": "high",
    "condition": "High error rate detected",
    "started_at": "2026-05-20T12:00:00Z",
    "completed_at": None,
    "triggered_at": "2026-05-20T11:55:00Z",
    "message": "Correlating signals across architectural layers",
    "signal_count": 12,
}

# Mirrors the type contract carried by PIPELINE_STEPS in routes/investigations.py.
_STEP_TYPES = {
    "metric": "border-l-primary",
    "log": "border-l-status-healthy",
    "kb": "border-l-status-warning",
    "correlation": "border-l-primary-hover",
    "summary": "border-l-status-muted",
}


def _detail(**overrides) -> InvestigationDetail:
    data = {**_DETAIL, **overrides}
    return InvestigationDetail.from_dict(data)


def _render_summary_header(app: Flask, inv: InvestigationDetail) -> str:
    with app.app_context():
        tpl = app.jinja_env.get_template("components/investigation.html")
        return tpl.module.summary_header(inv)


def _render_step(
    app: Flask,
    step: dict,
    is_first_evidence: bool = False,
    order: int = 1,
) -> str:
    with app.app_context():
        tpl = app.jinja_env.get_template("components/investigation.html")
        return tpl.module.investigation_step(step, is_first_evidence, order)


def _render_conclusion(
    app: Flask,
    inv: InvestigationDetail,
    findings: dict,
    service_topology: dict | None = None,
) -> str:
    with app.app_context():
        tpl = app.jinja_env.get_template("components/investigation.html")
        return tpl.module.conclusion_block(
            inv, findings, service_topology or {}
        )

# ---------------------------------------------------------------------------
# AC1 — summary_header renders service/severity/signal-count/status (no SSE);
#       breadcrumb reads "Investigations > INV-{id}".
# ---------------------------------------------------------------------------


class TestSummaryHeaderMacro:
    """AC1: summary_header(inv) — service / severity / signal-count / status."""

    def test_header_shows_service(self, app: Flask) -> None:
        html = _render_summary_header(app, _detail())
        assert "payments" in html

    def test_header_shows_severity(self, app: Flask) -> None:
        html = _render_summary_header(app, _detail())
        assert "High" in html

    def test_header_shows_signal_count(self, app: Flask) -> None:
        html = _render_summary_header(app, _detail(signal_count=12))
        assert "12 signals" in html

    def test_header_signal_count_singular(self, app: Flask) -> None:
        html = _render_summary_header(app, _detail(signal_count=1))
        assert "1 signal" in html
        assert "1 signals" not in html

    def test_header_signal_count_defaults_zero(self, app: Flask) -> None:
        html = _render_summary_header(app, _detail(signal_count=None))
        assert "0 signals" in html

    def test_header_shows_status_via_badge(self, app: Flask) -> None:
        html = _render_summary_header(app, _detail(status="investigating"))
        assert "status-badge" in html
        assert 'data-status="investigating"' in html
        assert "In Progress" in html

    def test_header_has_no_sse_dependency(self, app: Flask) -> None:
        """Header is rendered immediately — no sse-connect / sse-swap attrs."""
        html = _render_summary_header(app, _detail())
        assert "sse-connect" not in html
        assert "sse-swap" not in html
        assert 'data-no-sse="true"' in html

    def test_header_macro_file_exists(self) -> None:
        assert os.path.isfile(INVESTIGATION_COMPONENT)
        with open(INVESTIGATION_COMPONENT) as f:
            source = f.read()
        assert "macro summary_header" in source



# ---------------------------------------------------------------------------
# AC2 — investigation_step macro + 3px type-colored left border
# ---------------------------------------------------------------------------


class TestInvestigationStepMacro:
    """AC2: investigation_step(step, is_first_evidence, order) per type color."""

    def test_metric_border_is_primary_indigo(self, app: Flask) -> None:
        html = _render_step(app, {"label": "RCA", "state": "completed", "type": "metric"})
        assert "border-l-primary" in html
        # must not collide with the light-indigo correlation token
        assert "border-l-primary-hover" not in html

    def test_log_border_is_status_healthy_green(self, app: Flask) -> None:
        html = _render_step(app, {"label": "Recs", "state": "completed", "type": "log"})
        assert "border-l-status-healthy" in html

    def test_kb_border_is_status_warning_amber(self, app: Flask) -> None:
        html = _render_step(app, {"label": "KB", "state": "completed", "type": "kb"})
        assert "border-l-status-warning" in html

    def test_correlation_border_is_primary_hover(self, app: Flask) -> None:
        html = _render_step(
            app, {"label": "Signals", "state": "active", "type": "correlation"}
        )
        assert "border-l-primary-hover" in html

    def test_summary_border_is_status_muted_gray(self, app: Flask) -> None:
        html = _render_step(
            app, {"label": "Impact", "state": "completed", "type": "summary"}
        )
        assert "border-l-status-muted" in html

    def test_step_uses_3px_left_border_width(self, app: Flask) -> None:
        html = _render_step(app, {"label": "RCA", "state": "completed", "type": "metric"})
        assert "border-l-[3px]" in html

    @pytest.mark.parametrize("step_type,token", list(_STEP_TYPES.items()))
    def test_each_type_maps_to_its_token(
        self, app: Flask, step_type: str, token: str
    ) -> None:
        html = _render_step(
            app, {"label": "x", "state": "completed", "type": step_type}
        )
        assert token in html

    def test_step_exposes_order_and_type_data_attrs(self, app: Flask) -> None:
        html = _render_step(
            app, {"label": "KB", "state": "completed", "type": "kb"}, order=2
        )
        assert 'data-order="2"' in html
        assert 'data-step-type="kb"' in html

    def test_step_marks_first_evidence(self, app: Flask) -> None:
        html = _render_step(
            app,
            {"label": "Signals", "state": "active", "type": "correlation"},
            is_first_evidence=True,
        )
        assert 'data-first-evidence="true"' in html

    def test_step_not_first_evidence_by_default(self, app: Flask) -> None:
        html = _render_step(
            app, {"label": "Signals", "state": "active", "type": "correlation"}
        )
        assert 'data-first-evidence="true"' not in html

    def test_step_macro_file_exists_and_exports(self) -> None:
        assert os.path.isfile(INVESTIGATION_COMPONENT)
        with open(INVESTIGATION_COMPONENT) as f:
            source = f.read()
        assert "macro investigation_step" in source



# ---------------------------------------------------------------------------
# AC3 — evidence values in font-mono; service names as labels on surface-raised
# ---------------------------------------------------------------------------


class TestEvidenceMonoAndServiceLabels:
    """AC3: font-mono evidence values; surface-raised service labels (FR25)."""

    def test_step_evidence_value_is_mono(self, app: Flask) -> None:
        html = _render_step(
            app,
            {
                "label": "Signal Correlation",
                "state": "completed",
                "type": "correlation",
                "detail": "rate(http_errors[5m])",
            },
        )
        assert "font-mono" in html
        # the evidence detail renders inside a font-mono span
        assert "step-value" in html
        assert "rate(http_errors[5m])" in html

    def test_conclusion_service_label_on_surface_raised(self, app: Flask) -> None:
        """Affected-service chips render as labels on a surface-raised background."""
        html = _render_conclusion(
            app,
            _detail(service="payments"),
            {},
            {"downstream": ["billing"]},
        )
        assert "service-label" in html
        assert "bg-surface-raised" in html
        assert "payments" in html

    def test_summary_header_service_is_label(self, app: Flask) -> None:
        """Service in the header renders as a chip label (not bare text)."""
        html = _render_summary_header(app, _detail(service="payments"))
        assert "service-label" in html
        assert 'data-field="service"' in html

    def test_correlated_signal_count_is_mono(self, app: Flask) -> None:
        """The big signal-count number in the conclusion uses font-mono."""
        html = _render_conclusion(app, _detail(), {"signals_gathered": 7})
        assert "font-mono" in html
        assert "7" in html


# ---------------------------------------------------------------------------
# AC4 — conclusion_block: root cause / affected services / correlated count
# ---------------------------------------------------------------------------


class TestConclusionBlock:
    """AC4: conclusion_block shows root cause / affected services / signal count."""

    def test_shows_root_cause(self, app: Flask) -> None:
        html = _render_conclusion(
            app, _detail(), {"root_cause_hypothesis": "DB pool exhausted"}
        )
        assert 'data-field="root-cause"' in html
        assert "DB pool exhausted" in html

    def test_root_cause_fallback_when_absent(self, app: Flask) -> None:
        html = _render_conclusion(app, _detail(), {})
        assert "Not yet determined" in html

    def test_shows_affected_services_includes_subject(self, app: Flask) -> None:
        html = _render_conclusion(app, _detail(service="payments"), {})
        assert 'data-field="affected-services"' in html
        assert "payments" in html

    def test_affected_services_includes_downstream(self, app: Flask) -> None:
        html = _render_conclusion(
            app,
            _detail(service="payments"),
            {},
            {"downstream": ["billing", "ledger"]},
        )
        assert "billing" in html
        assert "ledger" in html

    def test_affected_services_dedupes_subject(self, app: Flask) -> None:
        """Subject service appearing in downstream is not listed twice."""
        html = _render_conclusion(
            app,
            _detail(service="payments"),
            {},
            {"downstream": ["payments", "billing"]},
        )
        assert html.count("payments") == 1

    def test_shows_correlated_signal_count(self, app: Flask) -> None:
        html = _render_conclusion(app, _detail(), {"signals_gathered": 14})
        assert 'data-field="correlated-signals"' in html
        assert "14" in html

    def test_distinct_from_steps_uses_overlay_surface(self, app: Flask) -> None:
        """Conclusion is visually distinct: overlay surface + primary accent,
        not the surface-raised + left-border treatment used by steps."""
        html = _render_conclusion(app, _detail(), {})
        assert "investigation-conclusion" in html
        assert "bg-surface-overlay" in html
        assert "border-primary/40" in html
        # It must NOT carry the step's 3px left-border treatment
        assert "border-l-[3px]" not in html

    def test_conclusion_macro_file_exists_and_exports(self) -> None:
        with open(INVESTIGATION_COMPONENT) as f:
            source = f.read()
        assert "macro conclusion_block" in source



# ---------------------------------------------------------------------------
# AC5 — completed steps render immediately (NFR7 — page never blank)
# ---------------------------------------------------------------------------


class TestStepsRenderServerSide:
    """AC5: completed steps render server-side; page never blank (NFR7)."""


    def test_step_timeline_partial_uses_macro(self) -> None:
        """_step_timeline.html drives rendering through investigation_step."""
        assert os.path.isfile(STEP_TIMELINE_PARTIAL)
        with open(STEP_TIMELINE_PARTIAL) as f:
            source = f.read()
        assert "investigation_step" in source
        assert "step-timeline" in source


# ---------------------------------------------------------------------------
# D4 token discipline + migration doctrine (no arbitrary color values / no
# legacy classes left on migrated elements).
# ---------------------------------------------------------------------------


class TestTokenDisciplineAndMigration:
    """Design-token discipline (D4) and dark-first migration doctrine (AD-7)."""

    def test_component_has_no_arbitrary_color_values(self) -> None:
        """No bg-[#..]/border-[#..]/text-[#..] arbitrary colors; only tokens.
        border-l-[3px] (a width, not a color) is the sole allowed arbitrary."""
        with open(INVESTIGATION_COMPONENT) as f:
            source = f.read()
        assert "bg-[#" not in source
        assert "text-[#" not in source
        assert "border-[#" not in source
        # raw palette hex literals must not appear inline
        for hex_literal in ("#1a1a2e", "#0f0f1a", "#6366f1", "#22c55e", "#f59e0b"):
            assert hex_literal not in source


    def test_migrated_header_drops_legacy_classes(self) -> None:
        """The migrated summary header carries no legacy main.css header classes
        (investigation-detail-header / detail-meta / severity-indicator /
        service-badge) — doctrine forbids mixing legacy + Tailwind on migrated
        elements."""
        with open(INVESTIGATION_COMPONENT) as f:
            source = f.read()
        for legacy in (
            "investigation-detail-header",
            "detail-meta",
            "severity-indicator",
            "service-badge",
            "detail-timestamps",
        ):
            assert legacy not in source
