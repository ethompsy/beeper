"""Tests for the KB Surfacing service."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from beeper_ui.services.embedding_service import EmbeddingServiceError
from beeper_ui.services.kb_service import KBEntry, KBServiceError
from beeper_ui.services.kb_surfacing_service import (
    DEFAULT_VALIDATION_WEIGHT,
    MAX_QUERY_LENGTH,
    KBSurfacingResult,
    KBSurfacingService,
)


def _make_kb_entry(
    entry_id: str = "kb-001",
    title: str = "Test Entry",
    entry_type: str = "investigation",
    service: str = "payments",
    relevance_score: float = 0.8,
    content: str = "Some investigation content",
    validation_status: str | None = None,
) -> KBEntry:
    """Create a KBEntry for testing."""
    return KBEntry(
        id="point-" + entry_id,
        entry_id=entry_id,
        entry_type=entry_type,
        title=title,
        content=content,
        service=service,
        created_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        author="beeper",
        version=1,
        tags=[],
        auto_published=True,
        validation_status=validation_status,
        relevance_score=relevance_score,
    )


class TestKBSurfacingResult:
    """Tests for KBSurfacingResult dataclass."""

    def test_default_creation(self) -> None:
        result = KBSurfacingResult()
        assert result.entries == []
        assert result.is_novel is False
        assert result.query_text == ""
        assert result.investigation_id == ""

    def test_to_dict(self) -> None:
        result = KBSurfacingResult(
            entries=[{"entry_id": "kb-001", "title": "Test"}],
            is_novel=False,
            query_text="test query",
            investigation_id="inv-123",
        )
        d = result.to_dict()
        assert d["entries"] == [{"entry_id": "kb-001", "title": "Test"}]
        assert d["is_novel"] is False
        assert d["query_text"] == "test query"
        assert d["investigation_id"] == "inv-123"

    def test_novel_flag(self) -> None:
        result = KBSurfacingResult(is_novel=True)
        assert result.is_novel is True
        assert result.to_dict()["is_novel"] is True


class TestComputeValidationWeight:
    """Tests for _compute_validation_weight static method."""

    def test_proven(self) -> None:
        assert KBSurfacingService._compute_validation_weight("proven") == 1.0

    def test_human_confirmed(self) -> None:
        assert KBSurfacingService._compute_validation_weight("human-confirmed") == 0.9

    def test_corrected(self) -> None:
        assert KBSurfacingService._compute_validation_weight("corrected") == 0.8

    def test_ai_generated(self) -> None:
        assert KBSurfacingService._compute_validation_weight("AI-generated") == 0.6

    def test_none(self) -> None:
        assert KBSurfacingService._compute_validation_weight(None) == DEFAULT_VALIDATION_WEIGHT

    def test_unknown_string(self) -> None:
        assert KBSurfacingService._compute_validation_weight("unknown") == DEFAULT_VALIDATION_WEIGHT


class TestDeriveValidationStatus:
    """Tests for _derive_validation_status static method."""

    def test_proven_fix_fallback(self) -> None:
        entry = _make_kb_entry(entry_type="proven_fix")
        assert KBSurfacingService._derive_validation_status(entry) == "proven"

    def test_correction_fallback(self) -> None:
        entry = _make_kb_entry(entry_type="correction")
        assert KBSurfacingService._derive_validation_status(entry) == "human-confirmed"

    def test_investigation_fallback(self) -> None:
        entry = _make_kb_entry(entry_type="investigation")
        assert KBSurfacingService._derive_validation_status(entry) == "AI-generated"

    def test_unknown_type_fallback(self) -> None:
        entry = _make_kb_entry(entry_type="other")
        assert KBSurfacingService._derive_validation_status(entry) == "AI-generated"

    def test_uses_field_when_set(self) -> None:
        entry = _make_kb_entry(entry_type="investigation", validation_status="human-confirmed")
        assert KBSurfacingService._derive_validation_status(entry) == "human-confirmed"

    def test_corrected_field(self) -> None:
        entry = _make_kb_entry(entry_type="investigation", validation_status="corrected")
        assert KBSurfacingService._derive_validation_status(entry) == "corrected"

    def test_proven_field_overrides_type(self) -> None:
        entry = _make_kb_entry(entry_type="investigation", validation_status="proven")
        assert KBSurfacingService._derive_validation_status(entry) == "proven"

    def test_none_field_falls_back_to_type(self) -> None:
        entry = _make_kb_entry(entry_type="proven_fix", validation_status=None)
        assert KBSurfacingService._derive_validation_status(entry) == "proven"


class TestComposeQuery:
    """Tests for _compose_query method."""

    def test_full_findings(self) -> None:
        svc = KBSurfacingService()
        findings = {
            "root_cause_hypothesis": "Database connection pool exhausted",
            "prior_research_summary": "Similar issue found last month",
            "signal_summary": "High latency in API gateway",
            "condition": "critical",
            "severity": "high",
        }
        query = svc._compose_query(findings)
        assert "Database connection pool exhausted" in query
        assert "Similar issue found last month" in query
        assert "High latency in API gateway" in query
        assert "critical" in query
        assert "high" in query

    def test_empty_findings(self) -> None:
        svc = KBSurfacingService()
        assert svc._compose_query({}) == ""

    def test_none_findings(self) -> None:
        svc = KBSurfacingService()
        assert svc._compose_query(None) == ""

    def test_partial_findings(self) -> None:
        svc = KBSurfacingService()
        findings = {"root_cause_hypothesis": "Memory leak in worker process"}
        query = svc._compose_query(findings)
        assert "Memory leak in worker process" in query

    def test_query_capped_at_max_length(self) -> None:
        svc = KBSurfacingService()
        findings = {"root_cause_hypothesis": "x" * 600}
        query = svc._compose_query(findings)
        assert len(query) == MAX_QUERY_LENGTH

    def test_non_string_values_ignored(self) -> None:
        svc = KBSurfacingService()
        findings = {
            "root_cause_hypothesis": "valid text",
            "signal_summary": 12345,  # non-string
            "layers_queried": ["layer1"],  # non-string
        }
        query = svc._compose_query(findings)
        assert "valid text" in query
        assert "12345" not in query


class TestSurfaceEntries:
    """Tests for surface_entries method."""

    def test_surface_entries_ranked(self) -> None:
        svc = KBSurfacingService()

        # Create entries with explicit validation statuses
        proven_entry = _make_kb_entry(
            entry_id="kb-proven", entry_type="proven_fix",
            validation_status="proven", relevance_score=0.8,
        )
        human_entry = _make_kb_entry(
            entry_id="kb-human", entry_type="investigation",
            validation_status="human-confirmed", relevance_score=0.8,
        )
        corrected_entry = _make_kb_entry(
            entry_id="kb-corrected", entry_type="investigation",
            validation_status="corrected", relevance_score=0.8,
        )
        ai_entry = _make_kb_entry(
            entry_id="kb-ai", entry_type="investigation",
            validation_status="AI-generated", relevance_score=0.8,
        )

        mock_kb = MagicMock()
        mock_kb.search_semantic.return_value = (
            [ai_entry, corrected_entry, human_entry, proven_entry],
            True,
        )
        svc._kb_service = mock_kb
        svc._embedding_service = MagicMock()

        findings = {"root_cause_hypothesis": "Some issue", "service": "payments"}
        result = svc.surface_entries("inv-123", findings)

        assert result.investigation_id == "inv-123"
        assert result.is_novel is False
        assert len(result.entries) == 4

        # proven (0.8*1.0=0.8) > human-confirmed (0.8*0.9=0.72) > corrected (0.8*0.8=0.64) > AI (0.8*0.6=0.48)
        assert result.entries[0]["entry_id"] == "kb-proven"
        assert result.entries[0]["composite_score"] == pytest.approx(0.8)
        assert result.entries[1]["entry_id"] == "kb-human"
        assert result.entries[1]["composite_score"] == pytest.approx(0.72)
        assert result.entries[2]["entry_id"] == "kb-corrected"
        assert result.entries[2]["composite_score"] == pytest.approx(0.64)
        assert result.entries[3]["entry_id"] == "kb-ai"
        assert result.entries[3]["composite_score"] == pytest.approx(0.48)

    def test_surface_entries_empty_returns_novel(self) -> None:
        svc = KBSurfacingService()
        svc._kb_service = MagicMock()
        svc._kb_service.search_semantic.return_value = ([], False)

        findings = {"root_cause_hypothesis": "Never seen before"}
        result = svc.surface_entries("inv-456", findings)

        assert result.is_novel is True
        assert result.entries == []
        assert result.investigation_id == "inv-456"
        assert "Never seen before" in result.query_text

    def test_surface_entries_empty_findings_returns_novel(self) -> None:
        svc = KBSurfacingService()
        result = svc.surface_entries("inv-789", {})

        assert result.is_novel is True
        assert result.entries == []
        assert result.query_text == ""

    def test_surface_entries_entry_dict_structure(self) -> None:
        svc = KBSurfacingService()
        svc._kb_service = MagicMock()
        entry = _make_kb_entry(entry_id="kb-test", entry_type="investigation", relevance_score=0.85)
        svc._kb_service.search_semantic.return_value = ([entry], True)

        result = svc.surface_entries("inv-100", {"root_cause_hypothesis": "test"})

        assert len(result.entries) == 1
        e = result.entries[0]
        assert e["entry_id"] == "kb-test"
        assert e["title"] == "Test Entry"
        assert e["entry_type"] == "investigation"
        assert e["service"] == "payments"
        assert e["validation_status"] == "AI-generated"
        assert e["relevance_score"] == pytest.approx(0.85)
        # AI-generated weight = 0.6, so composite = 0.85 * 0.6 = 0.51
        assert e["composite_score"] == pytest.approx(0.51)
        assert e["link"] == "/knowledge/kb-test"
        assert e["created_at"] == "2026-03-01"
        assert len(e["content_preview"]) <= 150


class TestGracefulDegradation:
    """Tests for graceful degradation when services fail."""

    def test_semantic_search_fails_falls_back_to_service_listing(self) -> None:
        svc = KBSurfacingService()
        svc._kb_service = MagicMock()
        svc._kb_service.search_semantic.side_effect = KBServiceError("search failed")
        fallback_entry = _make_kb_entry(entry_id="kb-fallback", relevance_score=None)
        svc._kb_service.list_entries_by_service.return_value = [fallback_entry]

        findings = {"root_cause_hypothesis": "test", "service": "payments"}
        result = svc.surface_entries("inv-fallback", findings)

        assert result.is_novel is False
        assert len(result.entries) == 1
        assert result.entries[0]["entry_id"] == "kb-fallback"
        svc._kb_service.list_entries_by_service.assert_called_once_with("payments", limit=10)

    def test_both_searches_fail_returns_novel(self) -> None:
        svc = KBSurfacingService()
        svc._kb_service = MagicMock()
        svc._kb_service.search_semantic.side_effect = KBServiceError("search failed")
        svc._kb_service.list_entries_by_service.side_effect = KBServiceError("listing failed")

        findings = {"root_cause_hypothesis": "test", "service": "payments"}
        result = svc.surface_entries("inv-fail", findings)

        assert result.is_novel is True
        assert result.entries == []

    def test_embedding_error_falls_back(self) -> None:
        svc = KBSurfacingService()
        svc._kb_service = MagicMock()
        svc._kb_service.search_semantic.side_effect = EmbeddingServiceError("no API key")
        fallback_entry = _make_kb_entry(entry_id="kb-emb-fallback", relevance_score=None)
        svc._kb_service.list_entries_by_service.return_value = [fallback_entry]

        findings = {"root_cause_hypothesis": "test", "service": "api-gateway"}
        result = svc.surface_entries("inv-emb", findings)

        assert len(result.entries) == 1
        svc._kb_service.list_entries_by_service.assert_called_once_with("api-gateway", limit=10)

    def test_fallback_no_service_name(self) -> None:
        svc = KBSurfacingService()
        svc._kb_service = MagicMock()
        svc._kb_service.search_semantic.side_effect = KBServiceError("failed")

        # No service key in findings
        findings = {"root_cause_hypothesis": "test"}
        result = svc.surface_entries("inv-no-svc", findings)

        assert result.is_novel is True
        svc._kb_service.list_entries_by_service.assert_not_called()


class TestRecordRelevanceFeedback:
    """Tests for record_relevance_feedback method."""

    def test_successful_feedback(self) -> None:
        svc = KBSurfacingService()
        mock_point = MagicMock()
        mock_point.id = "point-123"
        mock_point.payload = {}

        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = ([mock_point], None)

        result = svc.record_relevance_feedback("inv-100", "kb-001", True, "sam")
        assert result is True

        svc._qdrant_client.set_payload.assert_called_once()
        call_kwargs = svc._qdrant_client.set_payload.call_args
        payload = call_kwargs.kwargs.get("payload") or call_kwargs[1].get("payload")
        assert "kb_relevance_feedback" in payload
        assert payload["kb_relevance_feedback"]["kb-001"]["is_relevant"] is True
        assert payload["kb_relevance_feedback"]["kb-001"]["user"] == "sam"

    def test_feedback_no_investigation_found(self) -> None:
        svc = KBSurfacingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = ([], None)

        result = svc.record_relevance_feedback("inv-missing", "kb-001", True, "sam")
        assert result is False

    def test_feedback_qdrant_failure(self) -> None:
        svc = KBSurfacingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.side_effect = Exception("connection failed")

        result = svc.record_relevance_feedback("inv-fail", "kb-001", False, "sam")
        assert result is False

    def test_multiple_feedbacks_additive(self) -> None:
        svc = KBSurfacingService()
        mock_point = MagicMock()
        mock_point.id = "point-123"
        mock_point.payload = {
            "kb_relevance_feedback": {
                "kb-existing": {
                    "is_relevant": True,
                    "user": "alex",
                    "timestamp": "2026-03-01T00:00:00Z",
                }
            }
        }

        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = ([mock_point], None)

        result = svc.record_relevance_feedback("inv-100", "kb-new", False, "sam")
        assert result is True

        call_kwargs = svc._qdrant_client.set_payload.call_args
        payload = call_kwargs.kwargs.get("payload") or call_kwargs[1].get("payload")
        feedback = payload["kb_relevance_feedback"]
        # Both old and new feedback should be present
        assert "kb-existing" in feedback
        assert "kb-new" in feedback
        assert feedback["kb-existing"]["is_relevant"] is True
        assert feedback["kb-new"]["is_relevant"] is False


class TestMarkNovelInvestigation:
    """Tests for mark_novel_investigation method."""

    def test_successful_marking(self) -> None:
        svc = KBSurfacingService()
        mock_point = MagicMock()
        mock_point.id = "point-456"

        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = ([mock_point], None)

        result = svc.mark_novel_investigation("inv-novel")
        assert result is True

        svc._qdrant_client.set_payload.assert_called_once()
        call_kwargs = svc._qdrant_client.set_payload.call_args
        payload = call_kwargs.kwargs.get("payload") or call_kwargs[1].get("payload")
        assert payload["novel_issue_candidate"] is True

    def test_marking_no_investigation_found(self) -> None:
        svc = KBSurfacingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.return_value = ([], None)

        result = svc.mark_novel_investigation("inv-missing")
        assert result is False

    def test_marking_qdrant_failure(self) -> None:
        svc = KBSurfacingService()
        svc._qdrant_client = MagicMock()
        svc._qdrant_client.scroll.side_effect = Exception("connection failed")

        result = svc.mark_novel_investigation("inv-fail")
        assert result is False


class TestClose:
    """Tests for close method."""

    def test_close_cleans_up(self) -> None:
        svc = KBSurfacingService()
        svc._kb_service = MagicMock()
        svc._qdrant_client = MagicMock()
        svc._embedding_service = MagicMock()

        svc.close()

        assert svc._kb_service is None
        assert svc._qdrant_client is None
        assert svc._embedding_service is None

    def test_close_handles_kb_failure(self) -> None:
        svc = KBSurfacingService()
        mock_kb = MagicMock()
        mock_kb.close.side_effect = Exception("close failed")
        svc._kb_service = mock_kb
        mock_qdrant = MagicMock()
        svc._qdrant_client = mock_qdrant

        # Should not raise even if kb_service.close() fails
        svc.close()
        # Qdrant client should still be cleaned up despite kb_service failure
        mock_qdrant.close.assert_called_once()
        assert svc._qdrant_client is None
