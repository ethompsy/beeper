"""Tests for KBQueryStep."""

import json
from unittest.mock import MagicMock

from beeper_investigator.context import InvestigationContext
from beeper_investigator.kb.schemas import SearchResult
from beeper_investigator.llm.client import LlmClientError
from beeper_investigator.steps.kb_query import (
    EXACT_MATCH_THRESHOLD,
    KBQueryStep,
    _check_exact_match,
    _format_results,
)


def _make_step(
    *,
    embedding: list[float] | None = None,
    embedding_error: Exception | None = None,
    investigation_results: list[SearchResult] | None = None,
    knowledge_results: list[SearchResult] | None = None,
    kb_search_error: Exception | None = None,
    llm_response: str = '{"prior_research_summary": "test", "relevant_matches": [], "recommended_resolution": null, "confidence_boost": null}',
    llm_error: Exception | None = None,
    condition: str = "High error rate on /checkout endpoint",
    service: str = "payments",
    severity: str = "high",
) -> tuple[KBQueryStep, MagicMock, MagicMock, MagicMock]:
    """Build a KBQueryStep with mocked dependencies."""
    ctx = InvestigationContext(
        investigation_id="inv-test-001",
        namespace="default",
        condition=condition,
        service=service,
        severity=severity,
    )

    mock_llm = MagicMock()
    if embedding_error:
        mock_llm.embed_sync.side_effect = embedding_error
    else:
        mock_llm.embed_sync.return_value = embedding or [0.1] * 1536

    if llm_error:
        mock_llm.complete_sync.side_effect = llm_error
    else:
        mock_llm.complete_sync.return_value = llm_response

    mock_kb = MagicMock()
    if kb_search_error:
        mock_kb.search_investigations.side_effect = kb_search_error
        mock_kb.search_knowledge.side_effect = kb_search_error
    else:
        mock_kb.search_investigations.return_value = investigation_results or []
        mock_kb.search_knowledge.return_value = knowledge_results or []

    mock_status = MagicMock()

    step = KBQueryStep(
        kb_client=mock_kb,
        llm_client=mock_llm,
        context=ctx,
        status_updater=mock_status,
    )
    return step, mock_llm, mock_kb, mock_status


def _make_result(
    *,
    id: str = "point-1",
    score: float = 0.85,
    investigation_id: str = "inv-prior-001",
    summary: str = "Previous checkout issue",
    root_cause: str = "Memory leak in payment service",
    resolution: str = "Restart pods and increase memory limit",
) -> SearchResult:
    """Build a SearchResult for testing."""
    return SearchResult(
        id=id,
        score=score,
        payload={
            "investigation_id": investigation_id,
            "summary": summary,
            "root_cause": root_cause,
            "resolution": resolution,
            "service": "payments",
        },
    )


class TestKBQueryStep:
    """Tests for the KB query and prior research step."""

    def test_similar_investigations_found(self) -> None:
        """Similar past investigations are retrieved and referenced (AC1)."""
        results = [_make_result(score=0.85)]
        step, *_ = _make_step(
            investigation_results=results,
            llm_response=json.dumps({
                "prior_research_summary": "Previous checkout issue found",
                "relevant_matches": ["inv-prior-001: checkout issue"],
                "recommended_resolution": "Restart pods",
                "confidence_boost": "medium",
            }),
        )

        result = step.execute()

        assert result.success is True
        assert result.data["kb_available"] is True
        assert result.data["prior_investigations_count"] == 1
        assert result.data["prior_research_summary"] == "Previous checkout issue found"

    def test_exact_match_detected(self) -> None:
        """Exact match elevates confidence and recommends resolution (AC3)."""
        exact = _make_result(score=0.95, resolution="Increase memory limit")
        step, *_ = _make_step(
            investigation_results=[exact],
            llm_response=json.dumps({
                "prior_research_summary": "Exact match found",
                "relevant_matches": ["inv-prior-001: exact match"],
                "recommended_resolution": "Increase memory limit",
                "confidence_boost": "high",
            }),
        )

        result = step.execute()

        assert result.success is True
        assert result.data["exact_match_found"] is True
        assert result.data["exact_match_id"] == "inv-prior-001"
        assert result.data["confidence_boost"] == "high"
        assert result.data["recommended_resolution"] == "Increase memory limit"

    def test_no_kb_results(self) -> None:
        """Empty KB returns 'no prior research found' (AC1)."""
        step, *_ = _make_step()

        result = step.execute()

        assert result.success is True
        assert result.data["kb_available"] is True
        assert result.data["prior_investigations_count"] == 0
        assert result.data["prior_knowledge_count"] == 0
        assert result.data["exact_match_found"] is False
        assert "No prior research" in result.summary

    def test_kb_unavailable(self) -> None:
        """KB connection error returns graceful degradation (AC4)."""
        step, *_ = _make_step(
            kb_search_error=ConnectionError("Qdrant unreachable"),
        )

        result = step.execute()

        assert result.success is False
        assert result.data["kb_available"] is False
        assert result.data["reason"] == "connection_failed"
        assert result.error is not None

    def test_embedding_model_not_configured(self) -> None:
        """Missing embedding model skips KB search via config check."""
        step, mock_llm, _, _ = _make_step()
        mock_llm.config.embedding_model = None

        result = step.execute()

        assert result.success is True
        assert result.data["kb_available"] is False
        assert result.data["reason"] == "embedding_model_not_configured"
        mock_llm.embed_sync.assert_not_called()

    def test_embedding_generation_failure(self) -> None:
        """Embedding API failure skips KB search gracefully."""
        step, *_ = _make_step(
            embedding_error=LlmClientError("API error during embedding"),
        )

        result = step.execute()

        assert result.success is True
        assert result.data["kb_available"] is False
        assert result.data["reason"] == "embedding_failed"

    def test_llm_synthesis_with_results(self) -> None:
        """LLM synthesizes KB results into structured findings (AC2)."""
        results = [
            _make_result(id="p1", score=0.88, investigation_id="inv-1", summary="First"),
            _make_result(id="p2", score=0.82, investigation_id="inv-2", summary="Second"),
        ]
        step, *_ = _make_step(
            investigation_results=results,
            llm_response=json.dumps({
                "prior_research_summary": "Two prior incidents found",
                "relevant_matches": ["inv-1: First", "inv-2: Second"],
                "recommended_resolution": None,
                "confidence_boost": "medium",
            }),
        )

        result = step.execute()

        assert result.success is True
        assert result.data["confidence_boost"] == "medium"
        assert len(result.data["relevant_matches"]) == 2

    def test_llm_synthesis_failure_falls_back(self) -> None:
        """LLM synthesis failure falls back to raw results."""
        results = [_make_result(score=0.85)]
        step, *_ = _make_step(
            investigation_results=results,
            llm_error=LlmClientError("LLM down"),
        )

        result = step.execute()

        assert result.success is True
        assert result.data["kb_available"] is True
        assert result.data["prior_research_summary"] != ""
        assert result.data["confidence_boost"] == "medium"

    def test_metadata_filtering_by_service(self) -> None:
        """KB search filters by service name."""
        step, _, mock_kb, _ = _make_step(service="auth-service")

        step.execute()

        call_kwargs = mock_kb.search_investigations.call_args
        assert call_kwargs[1]["service"] == "auth-service"
        call_kwargs = mock_kb.search_knowledge.call_args
        assert call_kwargs[1]["service"] == "auth-service"

    def test_step_data_flows_to_metadata(self) -> None:
        """Step data includes all expected fields for pipeline metadata."""
        results = [_make_result(score=0.95)]
        step, *_ = _make_step(
            investigation_results=results,
            llm_response=json.dumps({
                "prior_research_summary": "test",
                "relevant_matches": [],
                "recommended_resolution": "fix it",
                "confidence_boost": "high",
            }),
        )

        result = step.execute()

        assert "kb_available" in result.data
        assert "prior_investigations_count" in result.data
        assert "prior_knowledge_count" in result.data
        assert "exact_match_found" in result.data
        assert "prior_research_summary" in result.data
        assert "confidence_boost" in result.data

    def test_step_name(self) -> None:
        """Step has descriptive name."""
        step, *_ = _make_step()
        assert step.name == "KB Query & Prior Research"

    def test_status_update_sent(self) -> None:
        """Step sends status update during execution."""
        step, _, _, mock_status = _make_step()

        step.execute()

        mock_status.update_message.assert_called()
        msg = mock_status.update_message.call_args[0][0]
        assert "knowledge base" in msg.lower() or "prior research" in msg.lower()

    def test_both_collections_searched(self) -> None:
        """Step searches both investigations and knowledge collections."""
        step, _, mock_kb, _ = _make_step()

        step.execute()

        mock_kb.search_investigations.assert_called_once()
        mock_kb.search_knowledge.assert_called_once()

    def test_embedding_text_includes_context(self) -> None:
        """Embedding query text includes condition, service, severity."""
        step, mock_llm, _, _ = _make_step(
            condition="OOM kills",
            service="api-gateway",
            severity="critical",
        )

        step.execute()

        query_text = mock_llm.embed_sync.call_args[0][0]
        assert "OOM kills" in query_text
        assert "api-gateway" in query_text
        assert "critical" in query_text

    def test_knowledge_results_included(self) -> None:
        """Knowledge collection results (runbooks) are included."""
        kb_result = SearchResult(
            id="kb-1",
            score=0.80,
            payload={"title": "Payment Service Runbook", "service": "payments"},
        )
        step, *_ = _make_step(
            knowledge_results=[kb_result],
            llm_response=json.dumps({
                "prior_research_summary": "Runbook found",
                "relevant_matches": ["kb-1: runbook"],
                "recommended_resolution": None,
                "confidence_boost": "medium",
            }),
        )

        result = step.execute()

        assert result.success is True
        assert result.data["prior_knowledge_count"] == 1

    def test_partial_kb_failure_uses_surviving_results(self) -> None:
        """One collection failing doesn't discard results from the other."""
        inv_result = _make_result(score=0.85)
        step, _, mock_kb, _ = _make_step(
            investigation_results=[inv_result],
            llm_response=json.dumps({
                "prior_research_summary": "partial results",
                "relevant_matches": ["inv-prior-001: partial"],
                "recommended_resolution": None,
                "confidence_boost": "medium",
            }),
        )
        # Knowledge search fails, investigations succeed
        mock_kb.search_knowledge.side_effect = ConnectionError("knowledge down")

        result = step.execute()

        assert result.success is True
        assert result.data["kb_available"] is True
        assert result.data["prior_investigations_count"] == 1
        assert result.data["prior_knowledge_count"] == 0

    def test_no_results_includes_all_schema_keys(self) -> None:
        """Empty KB results include all expected data keys for downstream consumers."""
        step, *_ = _make_step()

        result = step.execute()

        for key in (
            "kb_available",
            "prior_investigations_count",
            "prior_knowledge_count",
            "exact_match_found",
            "prior_research_summary",
            "relevant_matches",
            "recommended_resolution",
            "confidence_boost",
        ):
            assert key in result.data, f"Missing key: {key}"

    def test_malformed_llm_json_falls_back(self) -> None:
        """Malformed LLM synthesis response falls back to raw results."""
        results = [_make_result(score=0.85)]
        step, *_ = _make_step(
            investigation_results=results,
            llm_response="Not valid JSON at all",
        )

        result = step.execute()

        assert result.success is True
        assert result.data["prior_research_summary"] != ""

    def test_markdown_wrapped_llm_response(self) -> None:
        """LLM response wrapped in markdown fences is parsed correctly."""
        results = [_make_result(score=0.85)]
        step, *_ = _make_step(
            investigation_results=results,
            llm_response='```json\n{"prior_research_summary": "wrapped", "relevant_matches": [], "recommended_resolution": null, "confidence_boost": null}\n```',
        )

        result = step.execute()

        assert result.data["prior_research_summary"] == "wrapped"


class TestExactMatchDetection:
    """Tests for exact match threshold logic."""

    def test_above_threshold(self) -> None:
        """Score above threshold is an exact match."""
        r = _make_result(score=EXACT_MATCH_THRESHOLD)
        assert _check_exact_match([r]) is r

    def test_below_threshold(self) -> None:
        """Score below threshold is not an exact match."""
        r = _make_result(score=EXACT_MATCH_THRESHOLD - 0.01)
        assert _check_exact_match([r]) is None

    def test_empty_results(self) -> None:
        """Empty results return None."""
        assert _check_exact_match([]) is None


class TestFormatResults:
    """Tests for result formatting."""

    def test_empty_results(self) -> None:
        """Empty results format as placeholder."""
        assert _format_results([]) == "(no results)"

    def test_formats_payload_fields(self) -> None:
        """Format includes investigation_id, summary, root_cause, resolution."""
        r = _make_result()
        formatted = _format_results([r])
        assert "inv-prior-001" in formatted
        assert "Previous checkout issue" in formatted
        assert "Memory leak" in formatted
        assert "Restart pods" in formatted
