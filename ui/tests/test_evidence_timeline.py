"""Tests for evidence timeline template rendering and route integration."""

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from beeper_ui.app import create_app
from beeper_ui.config import TestingConfig
from beeper_ui.services.evidence_service import EvidenceReference


@pytest.fixture
def app():
    """Create test application."""
    app = create_app(TestingConfig)
    yield app


@pytest.fixture
def client(app):
    """Create test client."""
    with app.test_client() as c:
        yield c


def _make_ref(**kwargs):
    """Create an EvidenceReference with defaults."""
    defaults = {
        "id": "ev-test-0",
        "investigation_id": "inv-1",
        "evidence_type": "metric",
        "title": "Test Evidence",
        "content_preview": "Preview text",
        "source_ref": "test-ref",
        "source_type": "prometheus",
        "timestamp": "2026-01-01T00:00:00Z",
        "relevance_score": None,
        "validation_status": None,
        "raw_data": None,
    }
    defaults.update(kwargs)
    return EvidenceReference(**defaults)


# --- Template rendering tests ---


class TestEvidenceTimelineTemplate:
    def test_empty_references_shows_empty_state(self, app):
        with app.app_context():
            html = app.jinja_env.get_template(
                "investigations/_evidence_timeline.html"
            ).render(evidence_references=[])
            assert "No evidence references yet" in html

    def test_metric_ref_renders_badge_and_query(self, app):
        refs = [
            _make_ref(
                evidence_type="metric",
                title="Signal: prometheus",
                source_type="prometheus",
                source_ref="rate(http_errors_total[5m])",
                raw_data="rate(http_errors_total[5m]) > 0.1",
            )
        ]
        with app.app_context():
            html = app.jinja_env.get_template(
                "investigations/_evidence_timeline.html"
            ).render(evidence_references=refs)
            assert "evidence-type-metric" in html
            assert "badge-metric" in html
            assert "metric" in html.lower()
            assert "View Query" in html
            assert "rate(http_errors_total[5m])" in html

    def test_log_ref_renders_badge_and_logs(self, app):
        refs = [
            _make_ref(
                evidence_type="log",
                title="Signal: loki",
                source_type="loki",
                source_ref="loki_query",
                raw_data="Connection refused errors",
            )
        ]
        with app.app_context():
            html = app.jinja_env.get_template(
                "investigations/_evidence_timeline.html"
            ).render(evidence_references=refs)
            assert "evidence-type-log" in html
            assert "badge-log" in html
            assert "View Logs" in html

    def test_kb_ref_renders_link_and_validation(self, app):
        refs = [
            _make_ref(
                evidence_type="kb",
                title="Exact KB Match",
                source_type="kb_entry",
                source_ref="kb-123",
                validation_status="proven",
                relevance_score=0.95,
            )
        ]
        with app.app_context():
            html = app.jinja_env.get_template(
                "investigations/_evidence_timeline.html"
            ).render(evidence_references=refs)
            assert "evidence-type-kb" in html
            assert "View KB Entry" in html
            assert "kb-123" in html
            assert "validation-proven" in html
            assert "proven" in html
            assert "95%" in html

    def test_deploy_ref_renders_commit(self, app):
        refs = [
            _make_ref(
                evidence_type="deploy",
                source_type="git_commit",
                source_ref="abc123def456",
            )
        ]
        with app.app_context():
            html = app.jinja_env.get_template(
                "investigations/_evidence_timeline.html"
            ).render(evidence_references=refs)
            assert "evidence-type-deploy" in html
            assert "abc123def456" in html

    def test_config_ref_renders_detail(self, app):
        refs = [
            _make_ref(
                evidence_type="config_change",
                source_type="config",
                raw_data="ConfigMap updated: DB_POOL_SIZE 10 -> 20",
            )
        ]
        with app.app_context():
            html = app.jinja_env.get_template(
                "investigations/_evidence_timeline.html"
            ).render(evidence_references=refs)
            assert "evidence-type-config_change" in html
            assert "View Config Change" in html
            assert "DB_POOL_SIZE" in html

    def test_multiple_refs_ordered(self, app):
        refs = [
            _make_ref(id="ev-1", evidence_type="metric", title="First"),
            _make_ref(id="ev-2", evidence_type="log", title="Second"),
            _make_ref(id="ev-3", evidence_type="kb", title="Third",
                      source_type="kb_entry", source_ref="kb-x"),
        ]
        with app.app_context():
            html = app.jinja_env.get_template(
                "investigations/_evidence_timeline.html"
            ).render(evidence_references=refs)
            first_pos = html.find("First")
            second_pos = html.find("Second")
            third_pos = html.find("Third")
            assert first_pos < second_pos < third_pos

    def test_validation_status_ai_generated(self, app):
        refs = [
            _make_ref(
                evidence_type="kb",
                source_type="kb_entry",
                source_ref="kb-ai",
                validation_status="AI-generated",
            )
        ]
        with app.app_context():
            html = app.jinja_env.get_template(
                "investigations/_evidence_timeline.html"
            ).render(evidence_references=refs)
            assert "validation-ai-generated" in html
            assert "AI-generated" in html

    def test_validation_status_human_confirmed(self, app):
        refs = [
            _make_ref(
                evidence_type="kb",
                source_type="kb_entry",
                source_ref="kb-hc",
                validation_status="human-confirmed",
            )
        ]
        with app.app_context():
            html = app.jinja_env.get_template(
                "investigations/_evidence_timeline.html"
            ).render(evidence_references=refs)
            assert "validation-human-confirmed" in html

    def test_no_validation_status_no_badge(self, app):
        refs = [
            _make_ref(
                evidence_type="kb",
                source_type="kb_entry",
                source_ref="kb-none",
                validation_status=None,
            )
        ]
        with app.app_context():
            html = app.jinja_env.get_template(
                "investigations/_evidence_timeline.html"
            ).render(evidence_references=refs)
            assert "validation-status-badge" not in html

    def test_content_preview_in_title_attr(self, app):
        refs = [
            _make_ref(content_preview="This is a detailed preview text"),
        ]
        with app.app_context():
            html = app.jinja_env.get_template(
                "investigations/_evidence_timeline.html"
            ).render(evidence_references=refs)
            assert "This is a detailed preview text" in html


# --- Findings template enhancement tests ---


class TestFindingsTemplateEnhancements:
    def test_kb_citation_link_in_rca(self, app):
        findings = {
            "root_cause_hypothesis": "Database pool exhaustion",
            "confidence_percentage": 85,
            "confidence_level": "high",
            "kb_citation": "kb-cite-1",
        }
        with app.app_context():
            html = app.jinja_env.get_template(
                "investigations/_findings.html"
            ).render(findings=findings)
            assert "kb-cite-1" in html
            assert "hypothesis-kb-citation" in html
            assert "KB Citation" in html

    def test_no_kb_citation_no_link(self, app):
        findings = {
            "root_cause_hypothesis": "Some hypothesis",
            "confidence_percentage": 70,
            "confidence_level": "medium",
        }
        with app.app_context():
            html = app.jinja_env.get_template(
                "investigations/_findings.html"
            ).render(findings=findings)
            assert "hypothesis-kb-citation" not in html


# --- Related KB template enhancement tests ---


class TestRelatedKBTemplateEnhancements:
    def test_proven_fix_shows_validation_badge(self, app):
        from beeper_ui.services.kb_surfacing_service import KBSurfacingResult

        surfacing_result = KBSurfacingResult(
            entries=[{
                "entry_id": "kb-pf-1", "title": "Proven Fix Entry",
                "entry_type": "proven_fix", "service": "api",
                "validation_status": "proven", "relevance_score": 0.88,
                "composite_score": 2.64, "content_preview": "This is a proven fix",
                "created_at": "", "link": "/knowledge/kb-pf-1",
            }],
            is_novel=False, query_text="test", investigation_id="inv-1",
        )

        with app.app_context():
            html = app.jinja_env.get_template(
                "investigations/_related_kb.html"
            ).render(
                surfacing_result=surfacing_result,
                exact_match_entry=None,
                exact_match_found=False,
            )
            assert "validation-proven" in html
            assert "proven" in html
            assert "88%" in html

    def test_investigation_shows_ai_generated_badge(self, app):
        from beeper_ui.services.kb_surfacing_service import KBSurfacingResult

        surfacing_result = KBSurfacingResult(
            entries=[{
                "entry_id": "kb-inv-1", "title": "Investigation Entry",
                "entry_type": "investigation", "service": "api",
                "validation_status": "AI-generated", "relevance_score": None,
                "composite_score": 0.0, "content_preview": "Auto-generated",
                "created_at": "", "link": "/knowledge/kb-inv-1",
            }],
            is_novel=False, query_text="test", investigation_id="inv-1",
        )

        with app.app_context():
            html = app.jinja_env.get_template(
                "investigations/_related_kb.html"
            ).render(
                surfacing_result=surfacing_result,
                exact_match_entry=None,
                exact_match_found=False,
            )
            assert "validation-ai-generated" in html
            assert "AI-generated" in html

    def test_correction_shows_human_confirmed_badge(self, app):
        from beeper_ui.services.kb_surfacing_service import KBSurfacingResult

        surfacing_result = KBSurfacingResult(
            entries=[{
                "entry_id": "kb-cor-1", "title": "Correction Entry",
                "entry_type": "correction", "service": "api",
                "validation_status": "human-confirmed", "relevance_score": 0.72,
                "composite_score": 1.44, "content_preview": "Human correction",
                "created_at": "", "link": "/knowledge/kb-cor-1",
            }],
            is_novel=False, query_text="test", investigation_id="inv-1",
        )

        with app.app_context():
            html = app.jinja_env.get_template(
                "investigations/_related_kb.html"
            ).render(
                surfacing_result=surfacing_result,
                exact_match_entry=None,
                exact_match_found=False,
            )
            assert "validation-human-confirmed" in html
            assert "72%" in html


# --- Evidence panel template enhancement tests ---


class TestEvidencePanelEnhancements:
    def test_supporting_evidence_list_renders(self, app):
        findings = {
            "supporting_evidence": [
                "Prometheus rate(errors) spiked",
                "Normal text evidence",
            ],
        }
        with app.app_context():
            html = app.jinja_env.get_template(
                "investigations/_evidence_panel.html"
            ).render(findings=findings)
            assert "evidence-supporting-list" in html
            assert "evidence-query-inline" in html  # Prometheus query inline code

    def test_relevant_matches_list_with_links(self, app):
        findings = {
            "relevant_matches": ["kb-1: Memory issue", "kb-2: CPU issue"],
        }
        with app.app_context():
            html = app.jinja_env.get_template(
                "investigations/_evidence_panel.html"
            ).render(findings=findings)
            assert "evidence-kb-match-list" in html
            assert "kb-1" in html
            assert "kb-2" in html

    def test_documentation_kb_entry_link(self, app):
        findings = {
            "documentation_written": "Investigation documented",
            "kb_entry_id": "kb-doc-99",
        }
        with app.app_context():
            html = app.jinja_env.get_template(
                "investigations/_evidence_panel.html"
            ).render(findings=findings)
            assert "kb-doc-99" in html
            assert "View KB Entry" in html


# --- Route integration tests ---


class TestRouteIntegration:
    @patch("beeper_ui.routes.investigations.get_evidence_service")
    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_detail_route_includes_evidence_references(
        self, mock_get_inv_svc, mock_get_ev_svc, client
    ):
        # Setup mock investigation service
        mock_inv_svc = MagicMock()
        mock_investigation = MagicMock()
        mock_investigation.id = "test-inv-1"
        mock_investigation.status = "investigating"
        mock_investigation.severity = "high"
        mock_investigation.condition = "Test condition"
        mock_investigation.service = "api"
        mock_investigation.started_at = "2026-01-01T00:00:00Z"
        mock_investigation.completed_at = None
        mock_investigation.triggered_at = None
        mock_investigation.message = "Step 1"
        mock_investigation.error = None
        mock_inv_svc.get_investigation.return_value = mock_investigation
        mock_inv_svc.get_investigation_findings.return_value = {
            "layers_queried": ["prometheus"],
            "signal_summary": "Metric spike detected",
        }
        mock_get_inv_svc.return_value = mock_inv_svc

        # Setup mock evidence service
        mock_ev_svc = MagicMock()
        mock_ev_svc.extract_evidence_references.return_value = [
            _make_ref(
                evidence_type="metric",
                title="Signal: prometheus",
                source_type="prometheus",
                source_ref="prometheus",
            )
        ]
        mock_ev_svc.enrich_kb_references.return_value = [
            _make_ref(
                evidence_type="metric",
                title="Signal: prometheus",
                source_type="prometheus",
                source_ref="prometheus",
            )
        ]
        mock_get_ev_svc.return_value = mock_ev_svc

        response = client.get("/investigations/test-inv-1")
        assert response.status_code == 200
        html = response.data.decode()
        assert "Evidence Timeline" in html
        assert "evidence-timeline" in html
        mock_ev_svc.extract_evidence_references.assert_called_once()
        mock_ev_svc.enrich_kb_references.assert_called_once()

    @patch("beeper_ui.routes.investigations.get_investigation_service")
    def test_detail_route_empty_findings_no_evidence(
        self, mock_get_inv_svc, client
    ):
        mock_inv_svc = MagicMock()
        mock_investigation = MagicMock()
        mock_investigation.id = "test-inv-2"
        mock_investigation.status = "investigating"
        mock_investigation.severity = "low"
        mock_investigation.condition = "Test"
        mock_investigation.service = "api"
        mock_investigation.started_at = None
        mock_investigation.completed_at = None
        mock_investigation.triggered_at = None
        mock_investigation.message = None
        mock_investigation.error = None
        mock_inv_svc.get_investigation.return_value = mock_investigation
        mock_inv_svc.get_investigation_findings.return_value = {}
        mock_get_inv_svc.return_value = mock_inv_svc

        response = client.get("/investigations/test-inv-2")
        assert response.status_code == 200
        html = response.data.decode()
        assert "No evidence references yet" in html
