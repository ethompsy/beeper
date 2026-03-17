"""Tests for AutoKBCreationService."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from beeper_investigator.kb.auto_creation import (
    AutoKBCreationService,
)
from beeper_investigator.kb.schemas import SearchResult


def _make_kb_client() -> MagicMock:
    """Create a mock KBClient."""
    client = MagicMock()
    client.search_knowledge.return_value = []
    client.client = MagicMock()
    return client


def _make_llm_client() -> MagicMock:
    """Create a mock LlmClient."""
    client = MagicMock()
    client.embed_sync.return_value = [0.1] * 1536
    return client


def _sample_investigation_data() -> dict[str, Any]:
    """Sample resolved investigation data."""
    return {
        "investigation_id": "inv-test-001",
        "service": "payments",
        "condition": "High error rate on /checkout endpoint",
        "severity": "high",
        "root_cause_hypothesis": (
            "Database connection pool exhaustion caused "
            "cascading checkout failures"
        ),
        "confidence_level": "high",
        "confidence_percentage": 90,
        "signals_summary": (
            "DB connection pool saturated at 100%; "
            "application 5xx rate spiked to 15%"
        ),
        "supporting_evidence": [
            "DB pool utilization at 100%",
            "5xx errors correlate with pool saturation",
        ],
        "recommendations": [
            {"action": "Increase DB connection pool size to 50", "confidence": "high"},
            {"action": "Add connection pool monitoring alert", "confidence": "medium"},
        ],
        "prior_research_summary": "Similar checkout failures in Q3",
        "relevant_matches": ["inv-prev-042"],
        "customer_impacting": True,
        "related_investigations": ["inv-prev-042", "inv-prev-031"],
        "summary": "Investigation found DB pool exhaustion as root cause",
        "findings": ["DB pool exhausted", "5xx rate spike"],
        "documentation_title": "DB Pool Exhaustion - payments",
        "documentation_summary": (
            "Database connection pool exhaustion on payments service "
            "caused cascading 5xx errors on the /checkout endpoint."
        ),
        "kb_entry_id": "doc-entry-001",
        "key_findings": [
            "DB pool at 100% utilization",
            "5xx rate spiked to 15%",
        ],
    }


class TestCreateOrUpdateFromInvestigation:
    """Test the main create_or_update_from_investigation flow."""

    def test_creates_new_entry_when_no_similar(self) -> None:
        kb = _make_kb_client()
        llm = _make_llm_client()
        service = AutoKBCreationService(kb, llm)

        data = _sample_investigation_data()
        result = service.create_or_update_from_investigation(data)

        assert result["action"] == "created"
        assert result["entry_id"] is not None
        assert result["similar_score"] is None

        # Verify KB entry was persisted
        kb.client.upsert.assert_called()
        call_args = kb.client.upsert.call_args_list
        # At least one call to knowledge collection
        knowledge_calls = [
            c for c in call_args
            if c[0][0] == "knowledge" or c.kwargs.get("collection_name") == "knowledge"
        ]
        assert len(knowledge_calls) >= 1

    def test_entry_has_required_fields(self) -> None:
        kb = _make_kb_client()
        llm = _make_llm_client()
        service = AutoKBCreationService(kb, llm)

        data = _sample_investigation_data()
        service.create_or_update_from_investigation(data)

        # Get the payload from the upsert call
        upsert_calls = kb.client.upsert.call_args_list
        # Find the knowledge collection upsert (not version)
        for call in upsert_calls:
            collection = call[0][0] if call[0] else call.kwargs.get("collection_name")
            if collection == "knowledge":
                points = call[0][1] if len(call[0]) > 1 else call.kwargs.get("points")
                payload = points[0].payload
                assert payload["entry_type"] == "investigation"
                assert payload["validation_status"] == "AI-generated"
                assert payload["service"] == "payments"
                assert payload["source_investigation_id"] == "inv-test-001"
                assert "inv-test-001" in payload["contributing_investigations"]
                assert payload["root_cause"] is not None
                assert payload["title"] is not None
                assert payload["version"] == 1
                return
        pytest.fail("No knowledge collection upsert found")

    def test_resolution_extracted_from_recommendations(self) -> None:
        """Resolution field is populated from recommendations when not explicit."""
        kb = _make_kb_client()
        llm = _make_llm_client()
        service = AutoKBCreationService(kb, llm)

        data = _sample_investigation_data()
        service.create_or_update_from_investigation(data)

        # Find the knowledge collection upsert
        for call in kb.client.upsert.call_args_list:
            collection = call[0][0] if call[0] else call.kwargs.get("collection_name")
            if collection == "knowledge":
                points = call[0][1] if len(call[0]) > 1 else call.kwargs.get("points")
                payload = points[0].payload
                assert payload["resolution"] == "Increase DB connection pool size to 50"
                return
        pytest.fail("No knowledge collection upsert found")

    def test_skips_when_empty_summary(self) -> None:
        kb = _make_kb_client()
        llm = _make_llm_client()
        service = AutoKBCreationService(kb, llm)

        result = service.create_or_update_from_investigation({})

        assert result["action"] == "skipped"
        assert result["reason"] == "empty_summary"
        kb.client.upsert.assert_not_called()


class TestSimilarityCheckAndEnrichment:
    """Test duplicate detection and enrichment."""

    def test_enriches_existing_entry_above_similarity_threshold(self) -> None:
        kb = _make_kb_client()
        llm = _make_llm_client()

        existing_entry = SearchResult(
            id="existing-point-001",
            score=0.90,
            payload={
                "entry_id": "existing-entry-001",
                "entry_type": "investigation",
                "service": "payments",
                "title": "DB Pool Exhaustion",
                "content": "Previous investigation content",
                "root_cause": "DB pool full",
                "resolution": "Restart",
                "key_findings": ["DB pool full"],
                "contributing_investigations": ["inv-old-001"],
                "related_investigations": ["inv-old-001"],
                "version": 2,
                "validation_status": "AI-generated",
            },
        )
        kb.search_knowledge.return_value = [existing_entry]

        service = AutoKBCreationService(kb, llm)
        data = _sample_investigation_data()
        result = service.create_or_update_from_investigation(data)

        assert result["action"] == "enriched"
        assert result["entry_id"] == "existing-entry-001"
        assert result["similar_score"] == 0.90

    def test_enrichment_merges_investigations(self) -> None:
        kb = _make_kb_client()
        llm = _make_llm_client()

        existing_entry = SearchResult(
            id="existing-point-001",
            score=0.88,
            payload={
                "entry_id": "existing-entry-001",
                "entry_type": "investigation",
                "service": "payments",
                "title": "DB Pool Issue",
                "content": "Original content",
                "root_cause": "DB pool full",
                "resolution": "Short fix",
                "key_findings": ["DB pool full"],
                "contributing_investigations": ["inv-old-001"],
                "related_investigations": ["inv-old-001"],
                "version": 1,
            },
        )
        kb.search_knowledge.return_value = [existing_entry]

        service = AutoKBCreationService(kb, llm)
        data = _sample_investigation_data()
        result = service.create_or_update_from_investigation(data)

        assert result["action"] == "enriched"

        # Check the enriched payload
        knowledge_calls = [
            c for c in kb.client.upsert.call_args_list
            if (c[0][0] if c[0] else "") == "knowledge"
        ]
        assert len(knowledge_calls) >= 1
        enriched_points = knowledge_calls[-1][0][1]
        enriched_payload = enriched_points[0].payload

        # Verify merge
        assert "inv-test-001" in enriched_payload["contributing_investigations"]
        assert "inv-old-001" in enriched_payload["contributing_investigations"]
        assert enriched_payload["version"] == 2
        assert "updated_at" in enriched_payload

    def test_enrichment_deduplicates_findings(self) -> None:
        kb = _make_kb_client()
        llm = _make_llm_client()

        existing_entry = SearchResult(
            id="point-001",
            score=0.85,
            payload={
                "entry_id": "entry-001",
                "entry_type": "investigation",
                "service": "payments",
                "key_findings": ["DB pool at 100% utilization", "Unique existing finding"],
                "contributing_investigations": [],
                "related_investigations": [],
                "version": 1,
                "resolution": "",
            },
        )
        kb.search_knowledge.return_value = [existing_entry]

        service = AutoKBCreationService(kb, llm)
        data = _sample_investigation_data()
        result = service.create_or_update_from_investigation(data)

        assert result["action"] == "enriched"

        # Check deduplication
        knowledge_calls = [
            c for c in kb.client.upsert.call_args_list
            if (c[0][0] if c[0] else "") == "knowledge"
        ]
        enriched_payload = knowledge_calls[-1][0][1][0].payload
        findings = enriched_payload["key_findings"]

        # Should have unique findings only
        assert "DB pool at 100% utilization" in findings
        assert "Unique existing finding" in findings
        assert "5xx rate spiked to 15%" in findings
        assert len(findings) == len(set(findings))


    def test_enrichment_updates_resolution_from_recommendations(self) -> None:
        """Enrichment updates resolution when new data has better recommendation."""
        kb = _make_kb_client()
        llm = _make_llm_client()

        existing_entry = SearchResult(
            id="point-001",
            score=0.88,
            payload={
                "entry_id": "entry-001",
                "entry_type": "investigation",
                "service": "payments",
                "key_findings": [],
                "contributing_investigations": [],
                "related_investigations": [],
                "version": 1,
                "resolution": "Short fix",
            },
        )
        kb.search_knowledge.return_value = [existing_entry]

        service = AutoKBCreationService(kb, llm)
        data = _sample_investigation_data()
        service.create_or_update_from_investigation(data)

        knowledge_calls = [
            c for c in kb.client.upsert.call_args_list
            if (c[0][0] if c[0] else "") == "knowledge"
        ]
        enriched_payload = knowledge_calls[-1][0][1][0].payload
        # Resolution should be updated from recommendations since it's longer
        assert enriched_payload["resolution"] == "Increase DB connection pool size to 50"


class TestNoSimilarEntry:
    """Test behavior when no similar KB entry exists."""

    def test_creates_new_when_scores_below_threshold(self) -> None:
        kb = _make_kb_client()
        llm = _make_llm_client()

        low_score_entry = SearchResult(
            id="point-low",
            score=0.50,
            payload={"entry_id": "entry-low"},
        )
        kb.search_knowledge.return_value = [low_score_entry]

        service = AutoKBCreationService(kb, llm)
        data = _sample_investigation_data()
        result = service.create_or_update_from_investigation(data)

        assert result["action"] == "created"
        assert result["similar_score"] == 0.50

    def test_creates_new_when_search_returns_empty(self) -> None:
        kb = _make_kb_client()
        llm = _make_llm_client()
        kb.search_knowledge.return_value = []

        service = AutoKBCreationService(kb, llm)
        data = _sample_investigation_data()
        result = service.create_or_update_from_investigation(data)

        assert result["action"] == "created"
        assert result["similar_score"] is None


class TestEnrichmentThreshold:
    """Test entries between enrichment and similarity thresholds."""

    def test_enriches_at_enrichment_threshold(self) -> None:
        kb = _make_kb_client()
        llm = _make_llm_client()

        entry = SearchResult(
            id="point-mid",
            score=0.75,
            payload={
                "entry_id": "entry-mid",
                "entry_type": "investigation",
                "service": "payments",
                "key_findings": [],
                "contributing_investigations": [],
                "related_investigations": [],
                "version": 1,
                "resolution": "",
            },
        )
        kb.search_knowledge.return_value = [entry]

        service = AutoKBCreationService(kb, llm)
        data = _sample_investigation_data()
        result = service.create_or_update_from_investigation(data)

        assert result["action"] == "enriched"
        assert result["similar_score"] == 0.75

    def test_creates_new_just_below_enrichment_threshold(self) -> None:
        kb = _make_kb_client()
        llm = _make_llm_client()

        entry = SearchResult(
            id="point-low",
            score=0.69,
            payload={"entry_id": "entry-low"},
        )
        kb.search_knowledge.return_value = [entry]

        service = AutoKBCreationService(kb, llm)
        data = _sample_investigation_data()
        result = service.create_or_update_from_investigation(data)

        assert result["action"] == "created"


class TestBuildSummaryText:
    """Test summary text composition."""

    def test_full_data_produces_comprehensive_summary(self) -> None:
        service = AutoKBCreationService(_make_kb_client(), _make_llm_client())
        data = _sample_investigation_data()
        text = service._build_summary_text(data)

        assert "payments" in text
        assert "Database connection pool exhaustion" in text
        assert "DB connection pool saturated" in text
        assert len(text) > 0

    def test_empty_data_returns_empty_string(self) -> None:
        service = AutoKBCreationService(_make_kb_client(), _make_llm_client())
        text = service._build_summary_text({})
        assert text == ""

    def test_partial_data_includes_available_fields(self) -> None:
        service = AutoKBCreationService(_make_kb_client(), _make_llm_client())
        data = {
            "condition": "OOMKilled",
            "service": "worker",
            "root_cause_hypothesis": "Memory leak in batch processor",
        }
        text = service._build_summary_text(data)
        assert "OOMKilled" in text
        assert "worker" in text
        assert "Memory leak" in text

    def test_summary_capped_at_1000_chars(self) -> None:
        service = AutoKBCreationService(_make_kb_client(), _make_llm_client())
        data = {
            "condition": "A" * 500,
            "service": "svc",
            "root_cause_hypothesis": "B" * 500,
            "signals_summary": "C" * 500,
        }
        text = service._build_summary_text(data)
        assert len(text) <= 1000


class TestVersionSnapshot:
    """Test version snapshot creation."""

    def test_version_snapshot_created(self) -> None:
        kb = _make_kb_client()
        llm = _make_llm_client()
        service = AutoKBCreationService(kb, llm)

        payload = {"entry_id": "test-entry", "title": "Test", "version": 3}
        service._save_version_snapshot("test-entry", payload, 3)

        # Check upsert to knowledge_versions
        version_calls = [
            c for c in kb.client.upsert.call_args_list
            if (c[0][0] if c[0] else "") == "knowledge_versions"
        ]
        assert len(version_calls) == 1
        version_point = version_calls[0][0][1][0]
        assert version_point.payload["entry_id"] == "test-entry"
        assert version_point.payload["version"] == 3

    def test_version_snapshot_failure_non_fatal(self) -> None:
        kb = _make_kb_client()
        llm = _make_llm_client()
        kb.client.upsert.side_effect = Exception("Qdrant down")
        service = AutoKBCreationService(kb, llm)

        # Should not raise
        service._save_version_snapshot("test-entry", {}, 1)


class TestGracefulDegradation:
    """Test error handling and graceful degradation."""

    def test_embedding_failure_uses_zero_vector(self) -> None:
        kb = _make_kb_client()
        llm = _make_llm_client()
        llm.embed_sync.side_effect = Exception("Embedding API down")

        service = AutoKBCreationService(kb, llm)
        data = _sample_investigation_data()
        result = service.create_or_update_from_investigation(data)

        # Should still create entry with zero vector
        assert result["action"] == "created"
        assert result["entry_id"] is not None

    def test_search_failure_creates_new_entry(self) -> None:
        kb = _make_kb_client()
        llm = _make_llm_client()
        kb.search_knowledge.side_effect = Exception("Qdrant search failed")

        service = AutoKBCreationService(kb, llm)
        data = _sample_investigation_data()
        result = service.create_or_update_from_investigation(data)

        assert result["action"] == "created"

    def test_write_failure_retries_then_buffers(self) -> None:
        kb = _make_kb_client()
        llm = _make_llm_client()
        kb.client.upsert.side_effect = Exception("Qdrant write failed")

        service = AutoKBCreationService(kb, llm)

        with patch("beeper_investigator.kb.auto_creation.time.sleep"):
            with patch("builtins.open", create=True):
                with patch("os.makedirs"):
                    data = _sample_investigation_data()
                    result = service.create_or_update_from_investigation(data)

        # Should have retried 3 times for the main write
        assert kb.client.upsert.call_count >= 3
        assert result["entry_id"] is not None

    def test_version_snapshot_failure_doesnt_crash(self) -> None:
        kb = _make_kb_client()
        llm = _make_llm_client()

        # First upsert (knowledge) succeeds, second (versions) fails
        call_count = [0]
        original_upsert = kb.client.upsert

        def selective_fail(*args, **kwargs):
            call_count[0] += 1
            if args and args[0] == "knowledge_versions":
                raise Exception("Version write failed")
            return original_upsert(*args, **kwargs)

        kb.client.upsert.side_effect = selective_fail

        service = AutoKBCreationService(kb, llm)
        data = _sample_investigation_data()

        # Should not raise despite version snapshot failure
        result = service.create_or_update_from_investigation(data)
        assert result["action"] == "created"


class TestSkipOnFailedInvestigation:
    """Test that auto KB creation is only for successful investigations."""

    def test_empty_data_skipped(self) -> None:
        """Empty investigation data should be skipped."""
        kb = _make_kb_client()
        llm = _make_llm_client()
        service = AutoKBCreationService(kb, llm)

        result = service.create_or_update_from_investigation({})
        assert result["action"] == "skipped"
