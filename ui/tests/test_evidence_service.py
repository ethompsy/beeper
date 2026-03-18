"""Tests for EvidenceService — evidence extraction and KB reference enrichment."""

from unittest.mock import MagicMock, patch

import pytest

from beeper_ui.services.evidence_service import (
    EvidenceReference,
    EvidenceService,
    TimelineEvent,
    get_evidence_service,
    reset_evidence_service,
)


@pytest.fixture
def service():
    """Create a fresh EvidenceService instance."""
    return EvidenceService()


# --- extract_evidence_references: empty / missing findings ---


class TestExtractEmpty:
    def test_empty_findings_returns_empty(self, service):
        result = service.extract_evidence_references("inv-1", {})
        assert result == []

    def test_none_findings_returns_empty(self, service):
        result = service.extract_evidence_references("inv-1", None)
        assert result == []


# --- extract_evidence_references: KB match references ---


class TestKBMatches:
    def test_exact_match_extracted(self, service):
        findings = {
            "exact_match_found": True,
            "exact_match_id": "kb-123",
            "prior_research_summary": "Found matching incident from last week",
        }
        refs = service.extract_evidence_references("inv-1", findings)
        kb_refs = [r for r in refs if r.title == "Exact KB Match"]
        assert len(kb_refs) == 1
        assert kb_refs[0].source_ref == "kb-123"
        assert kb_refs[0].source_type == "kb_entry"
        assert kb_refs[0].evidence_type == "kb"
        assert kb_refs[0].relevance_score == 1.0

    def test_exact_match_not_extracted_when_false(self, service):
        findings = {"exact_match_found": False, "exact_match_id": "kb-123"}
        refs = service.extract_evidence_references("inv-1", findings)
        assert len([r for r in refs if r.title == "Exact KB Match"]) == 0

    def test_relevant_matches_extracted(self, service):
        findings = {
            "relevant_matches": [
                "kb-abc: Memory leak in payment service",
                "kb-def: CPU spike in auth service",
            ],
        }
        refs = service.extract_evidence_references("inv-1", findings)
        kb_refs = [r for r in refs if r.evidence_type == "kb"]
        assert len(kb_refs) == 2
        assert kb_refs[0].source_ref == "kb-abc"
        assert "Memory leak" in kb_refs[0].content_preview
        assert kb_refs[1].source_ref == "kb-def"

    def test_relevant_matches_without_colon_ignored(self, service):
        findings = {"relevant_matches": ["no-colon-here"]}
        refs = service.extract_evidence_references("inv-1", findings)
        assert len([r for r in refs if r.evidence_type == "kb"]) == 0

    def test_relevant_matches_non_list_ignored(self, service):
        findings = {"relevant_matches": "not a list"}
        refs = service.extract_evidence_references("inv-1", findings)
        assert len(refs) == 0


# --- extract_evidence_references: signal correlation ---


class TestSignalCorrelation:
    def test_layers_extracted_as_separate_refs(self, service):
        findings = {
            "layers_queried": ["prometheus", "loki"],
            "signal_summary": "Correlated metric spike with log errors",
        }
        refs = service.extract_evidence_references("inv-1", findings)
        assert len(refs) == 2
        assert refs[0].evidence_type == "metric"
        assert refs[0].source_type == "prometheus"
        assert refs[1].evidence_type == "log"
        assert refs[1].source_type == "loki"

    def test_no_signal_summary_no_refs(self, service):
        findings = {"layers_queried": ["prometheus"]}
        refs = service.extract_evidence_references("inv-1", findings)
        assert len(refs) == 0

    def test_hypotheses_extracted(self, service):
        findings = {
            "hypotheses": [
                "Database connection pool exhaustion",
                "Memory leak in worker process",
            ],
        }
        refs = service.extract_evidence_references("inv-1", findings)
        hyp_refs = [r for r in refs if r.title == "Signal Hypothesis"]
        assert len(hyp_refs) == 2
        assert "Database connection" in hyp_refs[0].content_preview

    def test_empty_hypotheses_ignored(self, service):
        findings = {"hypotheses": ["", "  "]}
        refs = service.extract_evidence_references("inv-1", findings)
        assert len(refs) == 0


# --- extract_evidence_references: supporting evidence ---


class TestSupportingEvidence:
    def test_supporting_evidence_classified(self, service):
        findings = {
            "supporting_evidence": [
                "Prometheus metric rate(http_errors_total) spiked",
                "Loki log shows connection timeout errors",
                "Recent deploy v2.3.1 changed DB config",
            ],
        }
        refs = service.extract_evidence_references("inv-1", findings)
        assert len(refs) == 3
        assert refs[0].evidence_type == "metric"
        assert refs[1].evidence_type == "log"
        assert refs[2].evidence_type == "deploy"

    def test_empty_supporting_items_ignored(self, service):
        findings = {"supporting_evidence": ["", None, "  "]}
        refs = service.extract_evidence_references("inv-1", findings)
        assert len(refs) == 0

    def test_non_list_supporting_evidence_ignored(self, service):
        findings = {"supporting_evidence": "just a string"}
        refs = service.extract_evidence_references("inv-1", findings)
        assert len(refs) == 0


# --- extract_evidence_references: RCA KB citation ---


class TestRCAKBCitation:
    def test_kb_citation_extracted(self, service):
        findings = {
            "kb_citation": "kb-rca-001",
            "root_cause_hypothesis": "Connection pool exhausted",
        }
        refs = service.extract_evidence_references("inv-1", findings)
        kb_refs = [r for r in refs if r.title == "RCA KB Citation"]
        assert len(kb_refs) == 1
        assert kb_refs[0].source_ref == "kb-rca-001"

    def test_kb_citation_not_duplicated_with_exact_match(self, service):
        findings = {
            "exact_match_found": True,
            "exact_match_id": "kb-rca-001",
            "kb_citation": "kb-rca-001",
        }
        refs = service.extract_evidence_references("inv-1", findings)
        kb_entry_refs = [
            r for r in refs if r.source_ref == "kb-rca-001"
        ]
        # Should only appear once (as exact match, not duplicated as RCA citation)
        assert len(kb_entry_refs) == 1

    def test_empty_kb_citation_ignored(self, service):
        findings = {"kb_citation": ""}
        refs = service.extract_evidence_references("inv-1", findings)
        assert len(refs) == 0


# --- extract_evidence_references: recommendation references ---


class TestRecommendationReferences:
    def test_prior_incident_extracted(self, service):
        findings = {
            "recommendations": [
                {
                    "action": "Restart worker pods",
                    "confidence": "high",
                    "based_on_prior_incident": "kb-prior-99",
                },
            ],
        }
        refs = service.extract_evidence_references("inv-1", findings)
        prior_refs = [r for r in refs if "Prior Incident" in r.title]
        assert len(prior_refs) == 1
        assert prior_refs[0].source_ref == "kb-prior-99"

    def test_no_prior_incident_no_ref(self, service):
        findings = {
            "recommendations": [
                {
                    "action": "Restart pods",
                    "confidence": "high",
                    "based_on_prior_incident": None,
                },
            ],
        }
        refs = service.extract_evidence_references("inv-1", findings)
        assert len([r for r in refs if "Prior Incident" in r.title]) == 0

    def test_duplicate_prior_incident_not_added(self, service):
        findings = {
            "recommendations": [
                {"action": "A", "based_on_prior_incident": "kb-dup"},
                {"action": "B", "based_on_prior_incident": "kb-dup"},
            ],
        }
        refs = service.extract_evidence_references("inv-1", findings)
        dup_refs = [r for r in refs if r.source_ref == "kb-dup"]
        assert len(dup_refs) == 1


# --- extract_evidence_references: documentation reference ---


class TestDocumentationReference:
    def test_kb_entry_id_extracted(self, service):
        findings = {
            "kb_entry_id": "kb-doc-42",
            "documentation_title": "Payment service timeout investigation",
        }
        refs = service.extract_evidence_references("inv-1", findings)
        doc_refs = [r for r in refs if r.title == "Investigation Documentation"]
        assert len(doc_refs) == 1
        assert doc_refs[0].source_ref == "kb-doc-42"

    def test_no_kb_entry_id_no_ref(self, service):
        findings = {"documentation_title": "Some title"}
        refs = service.extract_evidence_references("inv-1", findings)
        assert len([r for r in refs if r.title == "Investigation Documentation"]) == 0


# --- Full pipeline findings extraction ---


class TestFullPipelineExtraction:
    def test_comprehensive_findings_all_types(self, service):
        findings = {
            "exact_match_found": True,
            "exact_match_id": "kb-exact-1",
            "prior_research_summary": "Found prior incident",
            "relevant_matches": ["kb-rel-1: Similar issue"],
            "layers_queried": ["prometheus", "loki"],
            "signal_summary": "Metric and log correlation found",
            "hypotheses": ["Connection pool issue"],
            "supporting_evidence": ["Prometheus rate spike detected"],
            "kb_citation": "kb-rca-1",
            "root_cause_hypothesis": "DB pool exhaustion",
            "recommendations": [
                {"action": "Restart", "based_on_prior_incident": "kb-prior-1"}
            ],
            "kb_entry_id": "kb-doc-1",
            "documentation_title": "Investigation doc",
        }
        refs = service.extract_evidence_references("inv-1", findings)
        # Should have references from all extraction methods
        types = {r.evidence_type for r in refs}
        assert "kb" in types
        assert "metric" in types
        assert "log" in types
        # All refs should have valid IDs
        assert all(r.id.startswith("ev-inv-1-") for r in refs)
        # All should have the investigation_id
        assert all(r.investigation_id == "inv-1" for r in refs)

    def test_ids_are_unique(self, service):
        findings = {
            "layers_queried": ["prometheus", "loki"],
            "signal_summary": "Correlations",
            "supporting_evidence": ["Metric spike", "Log errors"],
        }
        refs = service.extract_evidence_references("inv-1", findings)
        ids = [r.id for r in refs]
        assert len(ids) == len(set(ids))


# --- classify_evidence ---


class TestClassifyEvidence:
    def test_metric_keywords(self, service):
        assert service._classify_evidence("Prometheus metric spike")[0] == "metric"
        assert service._classify_evidence("rate(http_errors)")[0] == "metric"

    def test_log_keywords(self, service):
        assert service._classify_evidence("Loki log shows errors")[0] == "log"
        assert service._classify_evidence("stderr output detected")[0] == "log"

    def test_deploy_keywords(self, service):
        assert service._classify_evidence("Recent deploy changed config")[0] == "deploy"
        assert service._classify_evidence("git commit abc123")[0] == "deploy"

    def test_config_keywords(self, service):
        assert service._classify_evidence("ConfigMap updated")[0] == "config_change"

    def test_kb_keywords(self, service):
        assert service._classify_evidence("KB entry matches prior incident")[0] == "kb"

    def test_fallback_to_metric(self, service):
        assert service._classify_evidence("Unknown evidence text")[0] == "metric"


# --- get_kb_reference_detail ---


class TestGetKBReferenceDetail:
    @patch("beeper_ui.services.evidence_service.KBService")
    def test_returns_detail_for_valid_entry(self, mock_kb_cls, service):
        mock_entry = MagicMock()
        mock_entry.entry_id = "kb-123"
        mock_entry.title = "Test Entry"
        mock_entry.entry_type = "proven_fix"
        mock_entry.relevance_score = 0.85
        mock_entry.content = "This is a proven fix for the issue"

        mock_kb = MagicMock()
        mock_kb.get_entry.return_value = mock_entry
        mock_kb_cls.return_value = mock_kb

        result = service.get_kb_reference_detail("kb-123")
        assert result["entry_id"] == "kb-123"
        assert result["title"] == "Test Entry"
        assert result["validation_status"] == "proven"
        assert result["relevance_score"] == 0.85

    @patch("beeper_ui.services.evidence_service.KBService")
    def test_returns_empty_for_not_found(self, mock_kb_cls, service):
        mock_kb = MagicMock()
        mock_kb.get_entry.return_value = None
        mock_kb_cls.return_value = mock_kb

        result = service.get_kb_reference_detail("kb-missing")
        assert result == {}

    @patch("beeper_ui.services.evidence_service.KBService")
    def test_returns_empty_on_error(self, mock_kb_cls, service):
        from beeper_ui.services.kb_service import KBServiceError

        mock_kb = MagicMock()
        mock_kb.get_entry.side_effect = KBServiceError("Connection failed")
        mock_kb_cls.return_value = mock_kb

        result = service.get_kb_reference_detail("kb-err")
        assert result == {}


# --- derive_validation_status ---


class TestDeriveValidationStatus:
    def test_proven_fix_returns_proven(self, service):
        entry = MagicMock()
        entry.entry_type = "proven_fix"
        assert service._derive_validation_status(entry) == "proven"

    def test_correction_returns_human_confirmed(self, service):
        entry = MagicMock()
        entry.entry_type = "correction"
        assert service._derive_validation_status(entry) == "human-confirmed"

    def test_investigation_returns_ai_generated(self, service):
        entry = MagicMock()
        entry.entry_type = "investigation"
        assert service._derive_validation_status(entry) == "AI-generated"

    def test_runbook_returns_ai_generated(self, service):
        entry = MagicMock()
        entry.entry_type = "runbook"
        assert service._derive_validation_status(entry) == "AI-generated"


# --- enrich_kb_references ---


class TestEnrichKBReferences:
    @patch("beeper_ui.services.evidence_service.KBService")
    def test_enriches_kb_references(self, mock_kb_cls, service):
        mock_entry = MagicMock()
        mock_entry.entry_type = "proven_fix"
        mock_entry.relevance_score = 0.92
        mock_entry.content = "Fix description"

        mock_kb = MagicMock()
        mock_kb.get_entry.return_value = mock_entry
        mock_kb_cls.return_value = mock_kb

        refs = [
            EvidenceReference(
                id="ev-1",
                investigation_id="inv-1",
                evidence_type="kb",
                title="KB Match",
                content_preview="",
                source_ref="kb-123",
                source_type="kb_entry",
                timestamp="2026-01-01T00:00:00Z",
            ),
            EvidenceReference(
                id="ev-2",
                investigation_id="inv-1",
                evidence_type="metric",
                title="Metric Signal",
                content_preview="Spike",
                source_ref="prometheus",
                source_type="prometheus",
                timestamp="2026-01-01T00:00:00Z",
            ),
        ]

        result = service.enrich_kb_references(refs)
        assert result[0].validation_status == "proven"
        assert result[0].relevance_score == 0.92
        # Non-KB ref unchanged
        assert result[1].validation_status is None

    def test_no_kb_refs_returns_unchanged(self, service):
        refs = [
            EvidenceReference(
                id="ev-1",
                investigation_id="inv-1",
                evidence_type="metric",
                title="Metric",
                content_preview="Spike",
                source_ref="prom",
                source_type="prometheus",
                timestamp="2026-01-01T00:00:00Z",
            ),
        ]
        result = service.enrich_kb_references(refs)
        assert len(result) == 1


# --- EvidenceReference dataclass ---


class TestEvidenceReferenceDataclass:
    def test_to_dict(self):
        ref = EvidenceReference(
            id="ev-1",
            investigation_id="inv-1",
            evidence_type="metric",
            title="Test",
            content_preview="Preview",
            source_ref="prom-query",
            source_type="prometheus",
            timestamp="2026-01-01T00:00:00Z",
            relevance_score=0.5,
            validation_status="proven",
            raw_data="raw",
        )
        d = ref.to_dict()
        assert d["id"] == "ev-1"
        assert d["evidence_type"] == "metric"
        assert d["relevance_score"] == 0.5


# --- Singleton pattern ---


class TestGetTimelineEvents:
    def test_empty_findings_returns_empty(self, service):
        result = service.get_timeline_events("inv-1", {})
        assert result == []

    def test_none_findings_returns_empty(self, service):
        result = service.get_timeline_events("inv-1", None)
        assert result == []

    @patch.object(EvidenceService, "enrich_kb_references", side_effect=lambda refs: refs)
    def test_events_sorted_chronologically(self, _mock_enrich, service):
        findings = {
            "layers_queried": ["Prometheus"],
            "signal_summary": "CPU spike detected",
            "supporting_evidence": ["Log shows OOM kill at 14:32"],
        }
        events = service.get_timeline_events("inv-1", findings)
        assert len(events) > 1
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(timestamps)

    @patch.object(EvidenceService, "enrich_kb_references", side_effect=lambda refs: refs)
    def test_event_category_mapping_metric(self, _mock_enrich, service):
        findings = {
            "layers_queried": ["Prometheus"],
            "signal_summary": "Spike",
        }
        events = service.get_timeline_events("inv-1", findings)
        metric_events = [e for e in events if e.evidence_type == "metric"]
        assert len(metric_events) > 0
        for ev in metric_events:
            assert ev.event_category == "metric_anomaly"

    @patch.object(EvidenceService, "enrich_kb_references", side_effect=lambda refs: refs)
    def test_event_category_mapping_log(self, _mock_enrich, service):
        findings = {
            "layers_queried": ["Loki"],
            "signal_summary": "Error logs found",
        }
        events = service.get_timeline_events("inv-1", findings)
        log_events = [e for e in events if e.evidence_type == "log"]
        assert len(log_events) > 0
        for ev in log_events:
            assert ev.event_category == "log_pattern"

    @patch.object(EvidenceService, "enrich_kb_references", side_effect=lambda refs: refs)
    def test_event_category_mapping_deploy(self, _mock_enrich, service):
        findings = {
            "supporting_evidence": ["Deploy rollout caused failure"],
        }
        events = service.get_timeline_events("inv-1", findings)
        deploy_events = [e for e in events if e.evidence_type == "deploy"]
        assert len(deploy_events) > 0
        for ev in deploy_events:
            assert ev.event_category == "deploy_event"

    @patch.object(EvidenceService, "enrich_kb_references", side_effect=lambda refs: refs)
    def test_event_category_mapping_kb(self, _mock_enrich, service):
        findings = {
            "exact_match_found": True,
            "exact_match_id": "kb-123",
            "prior_research_summary": "Known issue",
        }
        events = service.get_timeline_events("inv-1", findings)
        kb_events = [e for e in events if e.evidence_type == "kb"]
        assert len(kb_events) > 0
        for ev in kb_events:
            assert ev.event_category == "kb_reference"

    @patch.object(EvidenceService, "enrich_kb_references", side_effect=lambda refs: refs)
    def test_event_category_mapping_config_change(self, _mock_enrich, service):
        findings = {
            "supporting_evidence": ["ConfigMap update triggered restart"],
        }
        events = service.get_timeline_events("inv-1", findings)
        config_events = [e for e in events if e.evidence_type == "config_change"]
        assert len(config_events) > 0
        for ev in config_events:
            assert ev.event_category == "config_change"

    @patch.object(EvidenceService, "enrich_kb_references", side_effect=lambda refs: refs)
    def test_timeline_event_properties_delegate_to_reference(self, _mock_enrich, service):
        findings = {
            "layers_queried": ["Prometheus"],
            "signal_summary": "CPU spike",
        }
        events = service.get_timeline_events("inv-1", findings)
        assert len(events) > 0
        ev = events[0]
        assert ev.id == ev.reference.id
        assert ev.investigation_id == ev.reference.investigation_id
        assert ev.title == ev.reference.title
        assert ev.content_preview == ev.reference.content_preview
        assert ev.source_ref == ev.reference.source_ref
        assert ev.source_type == ev.reference.source_type
        assert ev.timestamp == ev.reference.timestamp

    @patch.object(EvidenceService, "enrich_kb_references", side_effect=lambda refs: refs)
    def test_timeline_event_to_dict_includes_category(self, _mock_enrich, service):
        findings = {
            "layers_queried": ["Prometheus"],
            "signal_summary": "Spike",
        }
        events = service.get_timeline_events("inv-1", findings)
        assert len(events) > 0
        d = events[0].to_dict()
        assert "event_category" in d
        assert d["event_category"] == "metric_anomaly"


class TestSingleton:
    def test_get_returns_same_instance(self):
        reset_evidence_service()
        s1 = get_evidence_service()
        s2 = get_evidence_service()
        assert s1 is s2
        reset_evidence_service()

    def test_reset_clears_instance(self):
        reset_evidence_service()
        s1 = get_evidence_service()
        reset_evidence_service()
        s2 = get_evidence_service()
        assert s1 is not s2
        reset_evidence_service()


# --- extract_evidence_references: deploy correlation references ---


class TestExtractDeployCorrelationReferences:
    """Test deploy correlation evidence extraction."""

    def test_deploy_correlations_extracted(self, service):
        findings = {
            "deploy_correlations": [
                {
                    "commit_sha": "abc123def456",
                    "confidence": "strong",
                    "author": "alice@example.com",
                    "message": "Fix payment timeout",
                    "deployment_timestamp": "2026-03-17T12:00:00+00:00",
                    "time_gap_seconds": 270,
                }
            ],
        }
        refs = service.extract_evidence_references("inv-1", findings)
        deploy_refs = [r for r in refs if r.evidence_type == "deploy"]
        assert len(deploy_refs) == 1
        assert deploy_refs[0].source_type == "git_commit"
        assert deploy_refs[0].source_ref == "abc123def456"
        assert "abc123d" in deploy_refs[0].title
        assert "strong" in deploy_refs[0].title

    def test_no_correlations_produces_no_deploy_evidence(self, service):
        findings = {"deploy_correlations": []}
        refs = service.extract_evidence_references("inv-1", findings)
        deploy_refs = [r for r in refs if r.evidence_type == "deploy"]
        assert len(deploy_refs) == 0

    def test_missing_correlations_key_produces_no_deploy_evidence(self, service):
        findings = {"signal_summary": "some data"}
        refs = service.extract_evidence_references("inv-1", findings)
        deploy_refs = [r for r in refs if r.evidence_type == "deploy"]
        assert len(deploy_refs) == 0

    def test_confidence_levels_preserved_in_title(self, service):
        findings = {
            "deploy_correlations": [
                {
                    "commit_sha": "aaa111222333",
                    "confidence": "moderate",
                    "author": "bob@example.com",
                    "message": "Update config",
                    "deployment_timestamp": "2026-03-17T11:50:00+00:00",
                    "time_gap_seconds": 600,
                },
                {
                    "commit_sha": "bbb444555666",
                    "confidence": "weak",
                    "author": "carol@example.com",
                    "message": "Refactor",
                    "deployment_timestamp": "2026-03-17T11:30:00+00:00",
                    "time_gap_seconds": 2400,
                },
            ],
        }
        refs = service.extract_evidence_references("inv-1", findings)
        deploy_refs = [r for r in refs if r.evidence_type == "deploy"]
        assert len(deploy_refs) == 2
        assert "moderate" in deploy_refs[0].title
        assert "weak" in deploy_refs[1].title

    def test_deploy_correlation_timestamp_used(self, service):
        findings = {
            "deploy_correlations": [
                {
                    "commit_sha": "abc123def456",
                    "confidence": "strong",
                    "author": "alice@example.com",
                    "message": "Fix bug",
                    "deployment_timestamp": "2026-03-17T12:00:00+00:00",
                    "time_gap_seconds": 120,
                }
            ],
        }
        refs = service.extract_evidence_references("inv-1", findings)
        deploy_refs = [r for r in refs if r.evidence_type == "deploy"]
        assert deploy_refs[0].timestamp == "2026-03-17T12:00:00+00:00"

    def test_multiple_correlations_all_extracted(self, service):
        findings = {
            "deploy_correlations": [
                {
                    "commit_sha": f"sha{i}00000000",
                    "confidence": "strong",
                    "author": f"dev{i}@example.com",
                    "message": f"Commit {i}",
                    "deployment_timestamp": "2026-03-17T12:00:00+00:00",
                    "time_gap_seconds": 60 * i,
                }
                for i in range(1, 4)
            ],
        }
        refs = service.extract_evidence_references("inv-1", findings)
        deploy_refs = [r for r in refs if r.evidence_type == "deploy"]
        assert len(deploy_refs) == 3


class TestExtractChangeEventReferences:
    """Test change event correlation evidence extraction."""

    def test_change_events_extracted(self, service):
        findings = {
            "change_events": [
                {
                    "resource_type": "ConfigMap",
                    "resource_name": "payments-config",
                    "confidence": "strong",
                    "change_description": "Updated TIMEOUT_MS from 5000 to 1000",
                    "timestamp": "2026-03-17T12:00:00+00:00",
                    "time_gap_seconds": 180,
                    "namespace": "default",
                    "reason": "Modified",
                }
            ],
        }
        refs = service.extract_evidence_references("inv-1", findings)
        change_refs = [r for r in refs if r.evidence_type == "config_change"]
        assert len(change_refs) == 1
        assert change_refs[0].source_type == "config"
        assert change_refs[0].source_ref == "payments-config"
        assert "ConfigMap" in change_refs[0].title
        assert "strong" in change_refs[0].title

    def test_no_change_events_produces_no_evidence(self, service):
        findings = {"change_events": []}
        refs = service.extract_evidence_references("inv-1", findings)
        change_refs = [r for r in refs if r.evidence_type == "config_change"]
        assert len(change_refs) == 0

    def test_multiple_change_events_all_extracted(self, service):
        findings = {
            "change_events": [
                {
                    "resource_type": f"Type{i}",
                    "resource_name": f"resource-{i}",
                    "confidence": "moderate",
                    "change_description": f"Change {i}",
                    "timestamp": "2026-03-17T12:00:00+00:00",
                    "time_gap_seconds": 60 * i,
                    "namespace": "default",
                    "reason": "",
                }
                for i in range(1, 4)
            ],
        }
        refs = service.extract_evidence_references("inv-1", findings)
        change_refs = [r for r in refs if r.evidence_type == "config_change"]
        assert len(change_refs) == 3
