"""Tests for deploy correlation template rendering."""

from unittest.mock import MagicMock, patch

import pytest

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig


@pytest.fixture
def app():
    """Create test application."""
    app = create_app(TestingConfig)
    yield app


def _render_template(app, correlations=None, deploy_summary=""):
    """Render the deploy correlation template."""
    with app.app_context():
        template = app.jinja_env.get_template(
            "investigations/_deploy_correlation.html"
        )
        return template.render(
            deploy_correlations=correlations or [],
            deploy_summary=deploy_summary,
        )


class TestDeployCorrelationTemplate:
    """Test deploy correlation card template rendering."""

    def test_renders_with_deploy_data(self, app):
        correlations = [
            {
                "commit_sha": "abc123def456",
                "confidence": "strong",
                "author": "alice@example.com",
                "message": "Fix payment timeout",
                "deployment_timestamp": "2026-03-17T12:00:00+00:00",
                "time_gap_seconds": 270,
                "anomaly_detected_at": "2026-03-17T12:04:30+00:00",
            }
        ]
        html = _render_template(app, correlations=correlations)
        assert "abc123d" in html
        assert "alice@example.com" in html
        assert "Fix payment timeout" in html
        assert "deploy-correlation-card" in html
        assert "deploy-table" in html

    def test_confidence_strong_badge(self, app):
        correlations = [
            {
                "commit_sha": "abc123def456",
                "confidence": "strong",
                "author": "alice@example.com",
                "message": "Fix bug",
                "deployment_timestamp": "2026-03-17T12:00:00+00:00",
                "time_gap_seconds": 120,
                "anomaly_detected_at": "2026-03-17T12:02:00+00:00",
            }
        ]
        html = _render_template(app, correlations=correlations)
        assert "confidence-strong" in html

    def test_confidence_moderate_badge(self, app):
        correlations = [
            {
                "commit_sha": "def456789012",
                "confidence": "moderate",
                "author": "bob@example.com",
                "message": "Update config",
                "deployment_timestamp": "2026-03-17T11:50:00+00:00",
                "time_gap_seconds": 600,
                "anomaly_detected_at": "2026-03-17T12:00:00+00:00",
            }
        ]
        html = _render_template(app, correlations=correlations)
        assert "confidence-moderate" in html

    def test_confidence_weak_badge(self, app):
        correlations = [
            {
                "commit_sha": "789012345678",
                "confidence": "weak",
                "author": "carol@example.com",
                "message": "Refactor",
                "deployment_timestamp": "2026-03-17T11:15:00+00:00",
                "time_gap_seconds": 2700,
                "anomaly_detected_at": "2026-03-17T12:00:00+00:00",
            }
        ]
        html = _render_template(app, correlations=correlations)
        assert "confidence-weak" in html

    def test_no_deploys_shows_fallback_message(self, app):
        html = _render_template(
            app,
            correlations=[],
            deploy_summary="No recent deployments found — likely not deploy-related",
        )
        assert "deploy-no-results" in html
        assert "No recent deployments found" in html

    def test_no_deploys_no_summary_shows_default_message(self, app):
        html = _render_template(app, correlations=[], deploy_summary="")
        assert "deploy-no-results" in html
        assert "No recent deployments found" in html

    def test_multiple_deploys_all_rendered(self, app):
        correlations = [
            {
                "commit_sha": f"sha{i}00000000",
                "confidence": "strong",
                "author": f"dev{i}@example.com",
                "message": f"Commit {i}",
                "deployment_timestamp": "2026-03-17T12:00:00+00:00",
                "time_gap_seconds": 60 * i,
                "anomaly_detected_at": "2026-03-17T12:05:00+00:00",
            }
            for i in range(1, 4)
        ]
        html = _render_template(app, correlations=correlations)
        # commit_sha[:7] truncation in template
        assert "sha1000" in html
        assert "sha2000" in html
        assert "sha3000" in html

    def test_time_gap_display(self, app):
        correlations = [
            {
                "commit_sha": "abc123def456",
                "confidence": "strong",
                "author": "alice@example.com",
                "message": "Fix bug",
                "deployment_timestamp": "2026-03-17T12:00:00+00:00",
                "time_gap_seconds": 150,
                "anomaly_detected_at": "2026-03-17T12:02:30+00:00",
            }
        ]
        html = _render_template(app, correlations=correlations)
        # 150 seconds = 2 min 30 sec
        assert "2 min" in html
        assert "30 sec" in html
