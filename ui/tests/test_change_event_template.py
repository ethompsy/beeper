"""Tests for change event correlation template rendering."""

import pytest

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig


@pytest.fixture
def app():
    """Create test application."""
    app = create_app(TestingConfig)
    yield app


def _render_template(app, change_events=None, change_summary=""):
    """Render the change events template."""
    with app.app_context():
        template = app.jinja_env.get_template(
            "investigations/_change_events.html"
        )
        return template.render(
            change_events=change_events or [],
            change_summary=change_summary,
        )


class TestChangeEventTemplate:
    """Test change event correlation card template rendering."""

    def test_renders_with_change_events(self, app):
        events = [
            {
                "resource_type": "ConfigMap",
                "resource_name": "payments-config",
                "change_description": "Updated TIMEOUT_MS from 5000 to 1000",
                "timestamp": "2026-03-17T12:00:00+00:00",
                "time_gap_seconds": 180,
                "confidence": "strong",
                "namespace": "default",
                "reason": "Modified",
            }
        ]
        html = _render_template(app, change_events=events)
        assert "change-events-card" in html
        assert "change-table" in html
        assert "ConfigMap" in html
        assert "payments-config" in html
        assert "Updated TIMEOUT_MS" in html

    def test_confidence_strong_badge(self, app):
        events = [
            {
                "resource_type": "ConfigMap",
                "resource_name": "cfg",
                "change_description": "",
                "timestamp": "2026-03-17T12:00:00+00:00",
                "time_gap_seconds": 120,
                "confidence": "strong",
                "namespace": "default",
                "reason": "",
            }
        ]
        html = _render_template(app, change_events=events)
        assert "confidence-strong" in html

    def test_confidence_moderate_badge(self, app):
        events = [
            {
                "resource_type": "Secret",
                "resource_name": "secret1",
                "change_description": "",
                "timestamp": "2026-03-17T11:50:00+00:00",
                "time_gap_seconds": 600,
                "confidence": "moderate",
                "namespace": "default",
                "reason": "",
            }
        ]
        html = _render_template(app, change_events=events)
        assert "confidence-moderate" in html

    def test_confidence_weak_badge(self, app):
        events = [
            {
                "resource_type": "Ingress",
                "resource_name": "web-ingress",
                "change_description": "",
                "timestamp": "2026-03-17T11:15:00+00:00",
                "time_gap_seconds": 2700,
                "confidence": "weak",
                "namespace": "default",
                "reason": "",
            }
        ]
        html = _render_template(app, change_events=events)
        assert "confidence-weak" in html

    def test_no_events_shows_fallback_message(self, app):
        html = _render_template(
            app,
            change_events=[],
            change_summary="No recent change events found — likely not config-change-related",
        )
        assert "change-no-results" in html
        assert "No recent change events found" in html

    def test_no_events_no_summary_shows_default_message(self, app):
        html = _render_template(app, change_events=[], change_summary="")
        assert "change-no-results" in html
        assert "No recent change events found" in html

    def test_multiple_events_all_rendered(self, app):
        events = [
            {
                "resource_type": f"Type{i}",
                "resource_name": f"resource-{i}",
                "change_description": f"Change {i}",
                "timestamp": "2026-03-17T12:00:00+00:00",
                "time_gap_seconds": 60 * i,
                "confidence": "strong",
                "namespace": "default",
                "reason": "",
            }
            for i in range(1, 4)
        ]
        html = _render_template(app, change_events=events)
        assert "resource-1" in html
        assert "resource-2" in html
        assert "resource-3" in html

    def test_time_gap_display(self, app):
        events = [
            {
                "resource_type": "ConfigMap",
                "resource_name": "cfg",
                "change_description": "",
                "timestamp": "2026-03-17T12:00:00+00:00",
                "time_gap_seconds": 150,
                "confidence": "strong",
                "namespace": "default",
                "reason": "",
            }
        ]
        html = _render_template(app, change_events=events)
        assert "2 min" in html
        assert "30 sec" in html

    def test_exact_minute_no_zero_sec(self, app):
        """Exact minute values should show '2 min' not '2 min 0 sec'."""
        events = [
            {
                "resource_type": "ConfigMap",
                "resource_name": "cfg",
                "change_description": "",
                "timestamp": "2026-03-17T12:00:00+00:00",
                "time_gap_seconds": 120,
                "confidence": "strong",
                "namespace": "default",
                "reason": "",
            }
        ]
        html = _render_template(app, change_events=events)
        assert "2 min" in html
        assert "0 sec" not in html

    def test_timestamp_human_readable(self, app):
        """Timestamp should be formatted without 'T' separator."""
        events = [
            {
                "resource_type": "ConfigMap",
                "resource_name": "cfg",
                "change_description": "",
                "timestamp": "2026-03-17T12:00:00+00:00",
                "time_gap_seconds": 60,
                "confidence": "strong",
                "namespace": "default",
                "reason": "",
            }
        ]
        html = _render_template(app, change_events=events)
        assert "2026-03-17T12:00:00" not in html
        assert "2026-03-17 12:00:00" in html

    def test_resource_type_badge(self, app):
        events = [
            {
                "resource_type": "HorizontalPodAutoscaler",
                "resource_name": "hpa-1",
                "change_description": "Scaled",
                "timestamp": "2026-03-17T12:00:00+00:00",
                "time_gap_seconds": 60,
                "confidence": "strong",
                "namespace": "default",
                "reason": "",
            }
        ]
        html = _render_template(app, change_events=events)
        assert "change-resource-type-badge" in html
        assert "HorizontalPodAutoscaler" in html
