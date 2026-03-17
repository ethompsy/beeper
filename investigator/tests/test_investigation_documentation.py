"""Tests for InvestigationDocumentationStep."""

import json
import os
import pathlib
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from beeper_investigator.context import InvestigationContext
from beeper_investigator.steps.investigation_documentation import (
    InvestigationDocumentationStep,
    _parse_response,
)


def _make_context(
    *,
    condition: str = "High error rate on /checkout endpoint",
    service: str = "payments",
    severity: str = "high",
    namespace: str = "default",
) -> InvestigationContext:
    return InvestigationContext(
        investigation_id="inv-test-001",
        namespace=namespace,
        condition=condition,
        service=service,
        severity=severity,
    )


def _full_pipeline_metadata() -> dict[str, Any]:
    """Pipeline metadata simulating all prior steps."""
    return {
        # CustomerImpactStep
        "customer_impacting": True,
        "reasoning": (
            "Payment service directly handles"
            " user transactions"
        ),
        # KBQueryStep
        "exact_match_found": True,
        "exact_match_id": "inv-prev-042",
        "prior_research_summary": (
            "Similar checkout failures were caused by"
            " DB pool exhaustion in Q3"
        ),
        "relevant_matches": [
            "inv-prev-042",
            "inv-prev-031",
        ],
        "recommended_resolution": (
            "Increase DB connection pool size"
        ),
        "confidence_boost": "high",
        # SignalCorrelationStep
        "signal_summary": (
            "DB connection pool saturated at 100%;"
            " application 5xx rate spiked to 15%"
        ),
        "hypotheses": [
            {
                "description": (
                    "Database connection pool exhaustion"
                ),
                "confidence": "high",
            },
        ],
        "service_dependency_chain": [
            "payments-db", "payments", "api-gateway",
        ],
        # RCAHypothesisStep
        "root_cause_hypothesis": (
            "Database connection pool exhaustion caused"
            " cascading checkout failures"
        ),
        "confidence_level": "high",
        "confidence_percentage": 90,
        "supporting_evidence": [
            "pg_stat_activity at max connections",
            "5xx error rate spiked from 0.1% to 15%",
        ],
        "kb_citation": "inv-prev-042",
        # ResolutionRecommendationStep
        "recommendations": [
            {
                "action": "Increase DB pool size to 50",
                "confidence": "high",
                "expected_outcome": (
                    "Resolve pool exhaustion"
                ),
                "risk_assessment": "low",
                "based_on_prior_incident": "inv-prev-042",
            },
        ],
        "recommendation_count": 1,
        "ranking_rationale": "Proven fix from prior",
        "diagnostic_actions": [],
    }


def _default_llm_response() -> str:
    """Valid LLM response for documentation."""
    return json.dumps({
        "title": (
            "DB Pool Exhaustion Causing Checkout Failures"
            " in Payments Service"
        ),
        "summary": (
            "Investigation of high error rate on"
            " /checkout endpoint for the payments"
            " service. Root cause identified as database"
            " connection pool exhaustion at 100%"
            " saturation causing cascading 5xx errors."
        ),
        "root_cause": (
            "Database connection pool exhaustion"
            " caused cascading checkout failures"
        ),
        "resolution": (
            "Increase DB connection pool size from"
            " 20 to 50; add circuit breaker"
        ),
        "signals_summary": (
            "DB pool at 100%; 5xx rate 0.1% to 15%"
        ),
        "confidence_overview": (
            "High confidence (90%) based on strong"
            " signal correlation and prior incident"
        ),
        "key_findings": [
            "DB pool saturated at max connections",
            "Error rate spike correlated with pool",
        ],
    })


def _make_step(
    *,
    pipeline_metadata: dict[str, Any] | None = None,
    llm_response: str | None = None,
    llm_error: Exception | None = None,
    embed_response: list[float] | None = None,
    embed_error: Exception | None = None,
    kb_error: Exception | None = None,
    condition: str = (
        "High error rate on /checkout endpoint"
    ),
    service: str = "payments",
    severity: str = "high",
) -> tuple[
    InvestigationDocumentationStep,
    MagicMock,
    MagicMock,
    MagicMock,
]:
    """Build step with mocked dependencies.

    Returns:
        Tuple of (step, mock_llm, mock_kb, mock_status).
    """
    ctx = _make_context(
        condition=condition,
        service=service,
        severity=severity,
    )

    mock_llm = MagicMock()
    mock_llm.select_model.return_value = "claude-sonnet-4"
    if llm_error:
        mock_llm.complete_sync.side_effect = llm_error
    else:
        mock_llm.complete_sync.return_value = (
            llm_response
            if llm_response is not None
            else _default_llm_response()
        )

    if embed_error:
        mock_llm.embed_sync.side_effect = embed_error
    else:
        mock_llm.embed_sync.return_value = (
            embed_response
            if embed_response is not None
            else [0.1] * 1536
        )

    mock_kb = MagicMock()
    if kb_error:
        mock_kb.client.upsert.side_effect = kb_error

    mock_status = MagicMock()

    step = InvestigationDocumentationStep(
        llm_client=mock_llm,
        kb_client=mock_kb,
        context=ctx,
        status_updater=mock_status,
        pipeline_metadata=(
            pipeline_metadata
            if pipeline_metadata is not None
            else _full_pipeline_metadata()
        ),
    )
    return step, mock_llm, mock_kb, mock_status


# ── 7.2: KB entry with all required fields (AC1) ────────


class TestKBEntryCreation:
    """Test KB entry contains all required fields (AC1)."""

    def test_entry_has_all_fields(self) -> None:
        """KB entry includes summary, condition, signals,
        RCA, resolution, confidence."""
        step, *_ = _make_step()
        result = step.execute()

        assert result.success is True
        data = result.data
        assert data["documentation_title"]
        assert data["documentation_summary"]
        assert data["synthesis_source"] == "llm"

    def test_payload_has_investigation_data(self) -> None:
        """Persisted payload includes all required fields."""
        step, _, mock_kb, _ = _make_step()
        result = step.execute()

        assert result.data["persisted"] is True
        call_args = mock_kb.client.upsert.call_args
        points = call_args[0][1]
        payload = points[0].payload

        assert payload["entry_type"] == "investigation"
        assert payload["investigation_id"] == "inv-test-001"
        assert payload["service"] == "payments"
        assert payload["condition"]
        assert payload["severity"] == "high"
        assert payload["title"]
        assert payload["summary"]
        assert payload["root_cause"]
        assert payload["resolution"]
        assert payload["confidence_level"] == "high"
        assert payload["confidence_percentage"] == 90
        assert payload["signals_summary"]
        assert payload["created_at"]


# ── 7.3: Entry stored in knowledge collection (AC2) ─────


class TestKnowledgeCollection:
    """Test entry stored in knowledge collection (AC2)."""

    def test_upsert_to_knowledge_collection(self) -> None:
        """Entry is stored in 'knowledge' collection."""
        step, _, mock_kb, _ = _make_step()
        step.execute()

        call_args = mock_kb.client.upsert.call_args
        collection = call_args[0][0]
        assert collection == "knowledge"

    def test_payload_schema_complete(self) -> None:
        """Payload has all expected schema keys."""
        step, _, mock_kb, _ = _make_step()
        step.execute()

        call_args = mock_kb.client.upsert.call_args
        payload = call_args[0][1][0].payload

        expected_keys = {
            "entry_id", "entry_type",
            "investigation_id", "service",
            "condition", "severity", "created_at",
            "title", "summary", "root_cause",
            "resolution", "confidence_level",
            "confidence_percentage", "signals_summary",
            "key_findings", "recommendations",
            "related_investigations",
            "customer_impacting",
            "validation_status",
            "source_investigation_id",
        }
        assert set(payload.keys()) == expected_keys

    def test_validation_status_is_ai_generated(self) -> None:
        """Payload includes validation_status='AI-generated'."""
        step, _, mock_kb, _ = _make_step()
        step.execute()

        call_args = mock_kb.client.upsert.call_args
        payload = call_args[0][1][0].payload
        assert payload["validation_status"] == "AI-generated"

    def test_source_investigation_id_present(self) -> None:
        """Payload includes source_investigation_id matching context."""
        step, _, mock_kb, _ = _make_step()
        step.execute()

        call_args = mock_kb.client.upsert.call_args
        payload = call_args[0][1][0].payload
        assert payload["source_investigation_id"] == "inv-test-001"


# ── 7.4: Embeddings generated via embed_sync (AC2) ──────


class TestEmbeddingGeneration:
    """Test embeddings are generated (AC2)."""

    def test_embed_sync_called(self) -> None:
        """embed_sync is called with summary text."""
        step, mock_llm, _, _ = _make_step()
        step.execute()

        mock_llm.embed_sync.assert_called_once()
        call_text = mock_llm.embed_sync.call_args[0][0]
        assert len(call_text) > 0

    def test_embedding_used_in_point(self) -> None:
        """Generated embedding is used in the point."""
        embed = [0.5] * 1536
        step, _, mock_kb, _ = _make_step(
            embed_response=embed
        )
        result = step.execute()

        assert result.data["embedding_generated"] is True
        call_args = mock_kb.client.upsert.call_args
        point = call_args[0][1][0]
        assert point.vector == embed


# ── 7.5: Metadata includes service, timestamp, id (AC2) ─


class TestMetadataFields:
    """Test metadata includes required fields (AC2)."""

    def test_service_in_payload(self) -> None:
        step, _, mock_kb, _ = _make_step()
        step.execute()
        payload = (
            mock_kb.client.upsert.call_args[0][1][0]
            .payload
        )
        assert payload["service"] == "payments"

    def test_timestamp_in_payload(self) -> None:
        step, _, mock_kb, _ = _make_step()
        step.execute()
        payload = (
            mock_kb.client.upsert.call_args[0][1][0]
            .payload
        )
        assert "created_at" in payload
        assert "T" in payload["created_at"]

    def test_investigation_id_in_payload(self) -> None:
        step, _, mock_kb, _ = _make_step()
        step.execute()
        payload = (
            mock_kb.client.upsert.call_args[0][1][0]
            .payload
        )
        assert payload["investigation_id"] == (
            "inv-test-001"
        )


# ── 7.6: KB unavailable triggers local buffering (AC3) ──


class TestKBUnavailableBuffering:
    """Test local buffering when KB is unavailable (AC3)."""

    @patch(
        "beeper_investigator.steps"
        ".investigation_documentation.time.sleep"
    )
    def test_kb_failure_triggers_buffer(
        self, mock_sleep: Any, tmp_path: pathlib.Path
    ) -> None:
        """When KB is down, findings are buffered."""
        step, _, _, _ = _make_step(
            kb_error=ConnectionError("Qdrant down")
        )
        buf_dir = str(tmp_path / "buffer")
        with patch.dict(
            os.environ, {"BEEPER_BUFFER_DIR": buf_dir}
        ):
            result = step.execute()

        assert result.data["persisted"] is False
        assert result.data["buffered"] is True
        assert result.data["buffer_path"] is not None
        assert os.path.exists(result.data["buffer_path"])

    @patch(
        "beeper_investigator.steps"
        ".investigation_documentation.time.sleep"
    )
    def test_buffer_file_contains_payload(
        self, mock_sleep: Any, tmp_path: pathlib.Path
    ) -> None:
        """Buffer file contains valid JSON with payload."""
        step, _, _, _ = _make_step(
            kb_error=ConnectionError("Qdrant down")
        )
        buf_dir = str(tmp_path / "buffer")
        with patch.dict(
            os.environ, {"BEEPER_BUFFER_DIR": buf_dir}
        ):
            result = step.execute()

        with open(result.data["buffer_path"]) as f:
            data = json.load(f)

        assert "payload" in data
        assert "embedding" in data
        assert data["collection"] == "knowledge"
        assert "buffered_at" in data
        assert (
            data["payload"]["investigation_id"]
            == "inv-test-001"
        )


# ── 7.7: Retry logic: successful retry cleans up (AC3) ──


class TestRetrySuccess:
    """Test successful retry cleans up buffer (AC3)."""

    @patch(
        "beeper_investigator.steps"
        ".investigation_documentation.time.sleep"
    )
    def test_retry_succeeds_on_second_attempt(
        self, mock_sleep: Any
    ) -> None:
        """KB write succeeds on retry after failure."""
        step, _, mock_kb, _ = _make_step()
        mock_kb.client.upsert.side_effect = [
            ConnectionError("temp failure"),
            None,
        ]
        result = step.execute()

        assert result.data["persisted"] is True
        assert result.data["buffered"] is False
        assert mock_kb.client.upsert.call_count == 2
        mock_sleep.assert_called_once_with(1.0)

    @patch(
        "beeper_investigator.steps"
        ".investigation_documentation.time.sleep"
    )
    def test_retry_cleans_up_existing_buffer(
        self, mock_sleep: Any, tmp_path: pathlib.Path
    ) -> None:
        """Successful retry removes existing buffer file."""
        buf_dir = str(tmp_path / "buffer")
        os.makedirs(buf_dir)
        buf_file = os.path.join(
            buf_dir, "inv-test-001.json"
        )
        with open(buf_file, "w") as f:
            f.write("{}")

        step, _, _, _ = _make_step()
        with patch.dict(
            os.environ, {"BEEPER_BUFFER_DIR": buf_dir}
        ):
            result = step.execute()

        assert result.data["persisted"] is True
        assert not os.path.exists(buf_file)


# ── 7.8: Retry exhausted: buffer file persisted (AC3) ───


class TestRetryExhausted:
    """Test buffer on retry exhaustion (AC3)."""

    @patch(
        "beeper_investigator.steps"
        ".investigation_documentation.time.sleep"
    )
    def test_all_retries_fail_buffers(
        self, mock_sleep: Any, tmp_path: pathlib.Path
    ) -> None:
        """3 retry failures result in buffer file."""
        step, _, mock_kb, _ = _make_step(
            kb_error=ConnectionError("down")
        )
        buf_dir = str(tmp_path / "buffer")
        with patch.dict(
            os.environ, {"BEEPER_BUFFER_DIR": buf_dir}
        ):
            result = step.execute()

        assert result.data["persisted"] is False
        assert result.data["buffered"] is True
        assert mock_kb.client.upsert.call_count == 3
        assert mock_sleep.call_count == 2

    @patch(
        "beeper_investigator.steps"
        ".investigation_documentation.time.sleep"
    )
    def test_retry_delays_exponential(
        self, mock_sleep: Any
    ) -> None:
        """Retry delays follow 1s, 2s pattern."""
        step, _, _, _ = _make_step(
            kb_error=ConnectionError("down")
        )
        with patch.dict(
            os.environ,
            {"BEEPER_BUFFER_DIR": "/tmp/test-buf"},
        ):
            with patch(
                "builtins.open",
                MagicMock(),
            ):
                with patch("os.makedirs"):
                    step.execute()

        calls = mock_sleep.call_args_list
        assert calls[0][0][0] == 1.0
        assert calls[1][0][0] == 2.0


class TestBufferWriteFailure:
    """Test graceful degradation when buffer write fails."""

    @patch(
        "beeper_investigator.steps"
        ".investigation_documentation.time.sleep"
    )
    def test_buffer_write_failure_returns_not_buffered(
        self, mock_sleep: Any
    ) -> None:
        """When KB and buffer both fail, buffered=False."""
        step, _, _, _ = _make_step(
            kb_error=ConnectionError("down")
        )
        with patch.dict(
            os.environ,
            {"BEEPER_BUFFER_DIR": "/no/such/path"},
        ):
            with patch(
                "os.makedirs",
                side_effect=PermissionError("denied"),
            ):
                result = step.execute()

        assert result.success is True
        assert result.data["persisted"] is False
        assert result.data["buffered"] is False
        assert result.data["buffer_path"] is None


# ── 7.9: Prior investigation links included (AC4) ───────


class TestPriorInvestigationLinks:
    """Test prior investigation links (AC4)."""

    def test_related_investigations_from_kb(self) -> None:
        """Related IDs collected from KB metadata."""
        step, _, mock_kb, _ = _make_step()
        step.execute()

        payload = (
            mock_kb.client.upsert.call_args[0][1][0]
            .payload
        )
        related = payload["related_investigations"]
        assert "inv-prev-042" in related
        assert "inv-prev-031" in related

    def test_related_from_rca_citation(self) -> None:
        """kb_citation from RCA step included."""
        meta = _full_pipeline_metadata()
        meta["kb_citation"] = "inv-rca-099"
        step, _, mock_kb, _ = _make_step(
            pipeline_metadata=meta
        )
        step.execute()

        payload = (
            mock_kb.client.upsert.call_args[0][1][0]
            .payload
        )
        assert "inv-rca-099" in (
            payload["related_investigations"]
        )

    def test_related_from_resolution_prior(self) -> None:
        """based_on_prior_incident from resolution."""
        meta = _full_pipeline_metadata()
        meta["recommendations"] = [
            {
                "action": "Fix it",
                "confidence": "high",
                "expected_outcome": "Fixed",
                "risk_assessment": "low",
                "based_on_prior_incident": "inv-res-077",
            },
        ]
        step, _, mock_kb, _ = _make_step(
            pipeline_metadata=meta
        )
        step.execute()

        payload = (
            mock_kb.client.upsert.call_args[0][1][0]
            .payload
        )
        assert "inv-res-077" in (
            payload["related_investigations"]
        )

    def test_related_deduplicates(self) -> None:
        """Same ID from multiple sources appears once."""
        step, *_ = _make_step()
        result = step.execute()
        related = result.data["related_investigations"]
        assert len(related) == len(set(related))

    def test_null_string_citation_excluded(self) -> None:
        """String 'null' kb_citation is excluded."""
        meta = _full_pipeline_metadata()
        meta["kb_citation"] = "null"
        meta["exact_match_id"] = None
        meta["relevant_matches"] = []
        meta["recommendations"] = []
        step, *_ = _make_step(pipeline_metadata=meta)
        result = step.execute()
        assert "null" not in (
            result.data["related_investigations"]
        )

    def test_null_string_prior_incident_excluded(
        self,
    ) -> None:
        """String 'null' based_on_prior_incident excluded."""
        meta = _full_pipeline_metadata()
        meta["exact_match_id"] = None
        meta["relevant_matches"] = []
        meta["kb_citation"] = None
        meta["recommendations"] = [
            {
                "action": "Fix it",
                "confidence": "high",
                "expected_outcome": "Fixed",
                "risk_assessment": "low",
                "based_on_prior_incident": "null",
            },
        ]
        step, *_ = _make_step(pipeline_metadata=meta)
        result = step.execute()
        assert "null" not in (
            result.data["related_investigations"]
        )


# ── 7.10: Embedding failure falls back to zeros ─────────


class TestEmbeddingFallback:
    """Test embedding failure uses placeholder zeros."""

    def test_embed_failure_uses_zeros(self) -> None:
        """When embed_sync fails, placeholder zeros used."""
        step, _, mock_kb, _ = _make_step(
            embed_error=RuntimeError("no model")
        )
        result = step.execute()

        assert result.data["embedding_generated"] is False
        assert result.data["persisted"] is True
        point = mock_kb.client.upsert.call_args[0][1][0]
        assert point.vector == [0.0] * 1536

    def test_empty_summary_uses_fallback_for_embed(
        self,
    ) -> None:
        """Empty LLM summary triggers fallback summary
        which is still embedded."""
        resp = json.dumps({
            "title": "Test",
            "summary": "",
            "root_cause": "",
            "resolution": "",
            "signals_summary": "",
            "confidence_overview": "",
            "key_findings": [],
        })
        step, mock_llm, _, _ = _make_step(
            llm_response=resp, pipeline_metadata={}
        )
        result = step.execute()
        # Fallback summary is always non-empty (includes
        # condition), so embed_sync IS called.
        assert result.data["embedding_generated"] is True
        mock_llm.embed_sync.assert_called_once()


# ── 7.11: LLM failure: documentation from metadata ──────


class TestLLMFailureFallback:
    """Test fallback when LLM fails."""

    def test_llm_exception_uses_fallback(self) -> None:
        """LLM error triggers fallback documentation."""
        step, *_ = _make_step(
            llm_error=RuntimeError("LLM down")
        )
        result = step.execute()

        assert result.success is True
        assert result.data["synthesis_source"] == "fallback"
        assert result.data["documentation_title"]
        assert result.data["documentation_summary"]

    def test_fallback_includes_condition(self) -> None:
        """Fallback title includes condition and service."""
        step, *_ = _make_step(
            llm_error=RuntimeError("fail")
        )
        result = step.execute()

        title = result.data["documentation_title"]
        assert "payments" in title
        assert "checkout" in title.lower()


# ── 7.12: LLM malformed JSON: graceful fallback ─────────


class TestMalformedJSONFallback:
    """Test fallback on malformed LLM response."""

    def test_invalid_json_triggers_fallback(self) -> None:
        """Non-JSON LLM response uses fallback."""
        step, *_ = _make_step(
            llm_response="not valid json {{"
        )
        result = step.execute()

        assert result.success is True
        assert result.data["synthesis_source"] == "fallback"

    def test_empty_json_title_uses_context(self) -> None:
        """Empty title in JSON uses condition/service."""
        resp = json.dumps({
            "title": "",
            "summary": "Some summary",
            "root_cause": "",
            "resolution": "",
            "signals_summary": "",
            "confidence_overview": "",
            "key_findings": [],
        })
        step, *_ = _make_step(llm_response=resp)
        result = step.execute()
        title = result.data["documentation_title"]
        assert "payments" in title


# ── 7.13: All prior step data missing ───────────────────


class TestNoMetadata:
    """Test minimal doc when all prior data missing."""

    def test_empty_metadata_creates_doc(self) -> None:
        """Empty pipeline metadata still produces doc."""
        step, *_ = _make_step(pipeline_metadata={})
        result = step.execute()

        assert result.success is True
        assert result.data["documentation_title"]
        assert result.data["documentation_summary"]

    def test_empty_metadata_has_condition(self) -> None:
        """Fallback summary includes condition."""
        step, *_ = _make_step(pipeline_metadata={})
        result = step.execute()

        summary = result.data["documentation_summary"]
        assert "checkout" in summary.lower()


# ── 7.14: Partial metadata (RCA only) ───────────────────


class TestPartialMetadata:
    """Test with partial pipeline metadata."""

    def test_rca_only_metadata(self) -> None:
        """Only RCA data in pipeline metadata."""
        meta = {
            "root_cause_hypothesis": "Memory leak",
            "confidence_level": "medium",
            "confidence_percentage": 60,
            "supporting_evidence": ["OOM kills"],
        }
        step, *_ = _make_step(pipeline_metadata=meta)
        result = step.execute()

        assert result.success is True
        assert result.data["documentation_title"]

    def test_no_recommendations_ok(self) -> None:
        """Missing resolution data is handled."""
        meta = {
            "root_cause_hypothesis": "Disk full",
            "confidence_level": "low",
        }
        step, _, mock_kb, _ = _make_step(
            pipeline_metadata=meta
        )
        step.execute()

        payload = (
            mock_kb.client.upsert.call_args[0][1][0]
            .payload
        )
        assert payload["recommendations"] == []
        assert payload["related_investigations"] == []


# ── 7.15: StepResult data schema consistent ─────────────


class TestStepResultSchema:
    """Test consistent data schema across all paths."""

    _EXPECTED_KEYS = {
        "documentation_title",
        "documentation_summary",
        "kb_entry_id",
        "persisted",
        "buffered",
        "buffer_path",
        "embedding_generated",
        "related_investigations",
        "synthesis_source",
        "doc_model_tier",
        "doc_model_used",
    }

    def test_schema_on_success(self) -> None:
        step, *_ = _make_step()
        result = step.execute()
        assert set(result.data.keys()) == self._EXPECTED_KEYS

    def test_schema_on_llm_failure(self) -> None:
        step, *_ = _make_step(
            llm_error=RuntimeError("fail")
        )
        result = step.execute()
        assert set(result.data.keys()) == self._EXPECTED_KEYS

    def test_schema_on_empty_metadata(self) -> None:
        step, *_ = _make_step(pipeline_metadata={})
        result = step.execute()
        assert set(result.data.keys()) == self._EXPECTED_KEYS

    @patch(
        "beeper_investigator.steps"
        ".investigation_documentation.time.sleep"
    )
    def test_schema_on_kb_failure(
        self, mock_sleep: Any, tmp_path: pathlib.Path
    ) -> None:
        step, _, _, _ = _make_step(
            kb_error=ConnectionError("down")
        )
        buf_dir = str(tmp_path / "buffer")
        with patch.dict(
            os.environ, {"BEEPER_BUFFER_DIR": buf_dir}
        ):
            result = step.execute()
        assert set(result.data.keys()) == self._EXPECTED_KEYS

    def test_schema_on_malformed_json(self) -> None:
        step, *_ = _make_step(
            llm_response="bad json"
        )
        result = step.execute()
        assert set(result.data.keys()) == self._EXPECTED_KEYS


# ── 7.16: Step name and status update message ───────────


class TestStepIdentity:
    """Test step name and status update."""

    def test_step_name(self) -> None:
        step, *_ = _make_step()
        assert step.name == "Investigation Documentation"

    def test_status_update_called(self) -> None:
        step, _, _, mock_status = _make_step()
        step.execute()
        mock_status.update_message.assert_called_with(
            "Documenting investigation findings"
        )


# ── 7.17: LLM prompt includes all evidence ──────────────


class TestLLMPromptContent:
    """Test LLM prompt includes all pipeline evidence."""

    def test_prompt_includes_condition(self) -> None:
        step, mock_llm, _, _ = _make_step()
        step.execute()

        call_args = mock_llm.complete_sync.call_args
        messages = call_args[0][0]
        user_msg = messages[1]["content"]
        assert "checkout" in user_msg.lower()

    def test_prompt_includes_rca(self) -> None:
        step, mock_llm, _, _ = _make_step()
        step.execute()

        user_msg = (
            mock_llm.complete_sync.call_args[0][0][1]
            ["content"]
        )
        assert "connection pool exhaustion" in (
            user_msg.lower()
        )

    def test_prompt_includes_impact(self) -> None:
        step, mock_llm, _, _ = _make_step()
        step.execute()

        user_msg = (
            mock_llm.complete_sync.call_args[0][0][1]
            ["content"]
        )
        assert "True" in user_msg

    def test_prompt_includes_signal_summary(self) -> None:
        step, mock_llm, _, _ = _make_step()
        step.execute()

        user_msg = (
            mock_llm.complete_sync.call_args[0][0][1]
            ["content"]
        )
        assert "5xx" in user_msg

    def test_prompt_includes_recommendations(self) -> None:
        step, mock_llm, _, _ = _make_step()
        step.execute()

        user_msg = (
            mock_llm.complete_sync.call_args[0][0][1]
            ["content"]
        )
        assert "pool size" in user_msg.lower()

    def test_prompt_includes_related_ids(self) -> None:
        step, mock_llm, _, _ = _make_step()
        step.execute()

        user_msg = (
            mock_llm.complete_sync.call_args[0][0][1]
            ["content"]
        )
        assert "inv-prev-042" in user_msg

    def test_prompt_includes_investigation_id(self) -> None:
        step, mock_llm, _, _ = _make_step()
        step.execute()

        user_msg = (
            mock_llm.complete_sync.call_args[0][0][1]
            ["content"]
        )
        assert "inv-test-001" in user_msg

    def test_system_prompt_present(self) -> None:
        step, mock_llm, _, _ = _make_step()
        step.execute()

        messages = (
            mock_llm.complete_sync.call_args[0][0]
        )
        assert messages[0]["role"] == "system"
        assert "SRE" in messages[0]["content"]


# ── Helper function tests ────────────────────────────────


class TestParseResponse:
    """Test _parse_response helper."""

    def test_plain_json(self) -> None:
        raw = '{"title": "test"}'
        assert _parse_response(raw)["title"] == "test"

    def test_code_fenced_json(self) -> None:
        raw = '```json\n{"title": "fenced"}\n```'
        assert _parse_response(raw)["title"] == "fenced"

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            _parse_response("not json")


# ── Agent pipeline registration (Task 6) ─────────────


class TestAgentPipelineRegistration:
    """Test step is registered in agent pipeline."""

    def test_documentation_step_in_build_steps(
        self,
    ) -> None:
        """InvestigationDocumentationStep is in pipeline."""
        from beeper_investigator.agent import (
            InvestigatorAgent,
            SourceClients,
        )

        ctx = _make_context()
        mock_kb = MagicMock()
        mock_llm = MagicMock()
        mock_status = MagicMock()
        sources = SourceClients()

        agent = InvestigatorAgent(
            context=ctx,
            kb_client=mock_kb,
            llm_client=mock_llm,
            sources=sources,
            status_updater=mock_status,
        )
        steps = agent._build_steps()

        step_names = [s.name for s in steps]
        assert "Investigation Documentation" in step_names

    def test_documentation_step_position(self) -> None:
        """Documentation step is step 6 (before remediation steps)."""
        from beeper_investigator.agent import (
            InvestigatorAgent,
            SourceClients,
        )

        ctx = _make_context()
        agent = InvestigatorAgent(
            context=ctx,
            kb_client=MagicMock(),
            llm_client=MagicMock(),
            sources=SourceClients(),
            status_updater=MagicMock(),
        )
        steps = agent._build_steps()

        assert steps[5].name == "Investigation Documentation"
