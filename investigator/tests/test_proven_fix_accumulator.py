"""Tests for ProvenFixAccumulatorStep.

Covers:
- Skip logic when fix_proven is not True
- KB entry creation with correct payload fields
- Embedding generation and fallback
- Persistence retry and file buffering
- Pipeline metadata output keys
"""

import json
from unittest.mock import MagicMock, patch

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.kb.client import KBClient
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.remediation.proven_fix_accumulator import (
    ProvenFixAccumulatorStep,
)


def _make_step(pipeline_metadata=None, trust_level=3, confidence_threshold=0.9):
    """Factory for ProvenFixAccumulatorStep with mocked dependencies."""
    llm = MagicMock(spec=LlmClient)
    llm.embed_sync.return_value = [0.1] * 1536
    kb = MagicMock(spec=KBClient)
    ctx = InvestigationContext(
        investigation_id="test-inv-001",
        namespace="default",
        condition="high_error_rate",
        service="payments",
        severity="high",
        trust_level=trust_level,
        confidence_threshold=confidence_threshold,
    )
    status = MagicMock(spec=InvestigationStatusUpdater)
    step = ProvenFixAccumulatorStep(
        llm_client=llm,
        kb_client=kb,
        context=ctx,
        status_updater=status,
        pipeline_metadata=pipeline_metadata or {},
    )
    return step, llm, kb, ctx, status


def _proven_fix_metadata():
    """Pipeline metadata that triggers proven fix accumulation."""
    return {
        "fix_proven": True,
        "fix_verified": True,
        "verification_executed": True,
        "verification_status": "confirmed",
        "verification_window_minutes": 15,
        "verification_results": [
            {
                "metric": "http_error_rate",
                "pre_fix_value": 0.15,
                "post_fix_value": 0.02,
                "status": "confirmed",
                "delta_pct": -86.7,
                "error_message": None,
            },
        ],
        "root_cause_hypothesis": "Connection pool exhaustion",
        "confidence_level": "high",
        "confidence_percentage": 85,
        "recommendations": [
            {"action": "Increase connection pool size", "confidence": "high"},
        ],
        "documentation_title": "Connection Pool Exhaustion - payments",
        "documentation_summary": "Investigation found connection pool exhaustion",
        "pr_url": "https://github.com/org/repo/pull/42",
        "pr_generated": True,
    }


class TestFixNotProven:
    """fix_proven missing or False → skip, return kb_entry_created=False."""

    def test_fix_proven_missing(self):
        step, _, _, _, _ = _make_step(pipeline_metadata={})
        result = step.execute()
        assert result.success is True
        assert result.data["kb_entry_created"] is False
        assert result.data["proven_fix_skip_reason"] == "fix_not_proven"

    def test_fix_proven_false(self):
        step, _, _, _, _ = _make_step(
            pipeline_metadata={"fix_proven": False}
        )
        result = step.execute()
        assert result.success is True
        assert result.data["kb_entry_created"] is False
        assert result.data["proven_fix_skip_reason"] == "fix_not_proven"

    def test_fix_proven_none(self):
        step, _, _, _, _ = _make_step(
            pipeline_metadata={"fix_proven": None}
        )
        result = step.execute()
        assert result.success is True
        assert result.data["kb_entry_created"] is False


class TestFixProvenCreatesEntry:
    """fix_proven=True → KB entry created with correct payload fields."""

    def test_kb_entry_created(self):
        metadata = _proven_fix_metadata()
        step, _, kb, _, _ = _make_step(pipeline_metadata=metadata)
        result = step.execute()
        assert result.success is True
        assert result.data["kb_entry_created"] is True
        assert result.data["proven_fix_entry_id"] is not None
        assert result.data["proven_fix_skip_reason"] is None
        kb.client.upsert.assert_called_once()


class TestPayloadContainsValidationStatus:
    """payload has validation_status: 'proven' and entry_type: 'proven_fix'."""

    def test_validation_status_and_entry_type(self):
        metadata = _proven_fix_metadata()
        step, _, kb, _, _ = _make_step(pipeline_metadata=metadata)
        step.execute()

        call_args = kb.client.upsert.call_args
        points = call_args[0][1]
        payload = points[0].payload
        assert payload["validation_status"] == "proven"
        assert payload["entry_type"] == "proven_fix"


class TestPayloadContainsVerificationEvidence:
    """verification_results and verification_status included in payload."""

    def test_verification_evidence(self):
        metadata = _proven_fix_metadata()
        step, _, kb, _, _ = _make_step(pipeline_metadata=metadata)
        step.execute()

        payload = kb.client.upsert.call_args[0][1][0].payload
        evidence = payload["verification_evidence"]
        assert evidence["status"] == "confirmed"
        assert evidence["window_minutes"] == 15
        assert len(evidence["results"]) == 1
        assert evidence["results"][0]["metric"] == "http_error_rate"


class TestPayloadContainsInvestigationLink:
    """source_investigation_id matches context.investigation_id."""

    def test_investigation_link(self):
        metadata = _proven_fix_metadata()
        step, _, kb, ctx, _ = _make_step(pipeline_metadata=metadata)
        step.execute()

        payload = kb.client.upsert.call_args[0][1][0].payload
        assert payload["source_investigation_id"] == ctx.investigation_id
        assert payload["investigation_id"] == ctx.investigation_id


class TestPayloadContainsRootCause:
    """root_cause_hypothesis from pipeline_metadata included."""

    def test_root_cause(self):
        metadata = _proven_fix_metadata()
        step, _, kb, _, _ = _make_step(pipeline_metadata=metadata)
        step.execute()

        payload = kb.client.upsert.call_args[0][1][0].payload
        assert payload["root_cause"] == "Connection pool exhaustion"


class TestPayloadContainsPRUrl:
    """pr_url from pipeline_metadata included when available."""

    def test_pr_url_present(self):
        metadata = _proven_fix_metadata()
        step, _, kb, _, _ = _make_step(pipeline_metadata=metadata)
        step.execute()

        payload = kb.client.upsert.call_args[0][1][0].payload
        assert payload["pr_url"] == "https://github.com/org/repo/pull/42"


class TestPayloadWithoutPRUrl:
    """pr_url absent when not in pipeline_metadata (None)."""

    def test_pr_url_missing(self):
        metadata = _proven_fix_metadata()
        del metadata["pr_url"]
        step, _, kb, _, _ = _make_step(pipeline_metadata=metadata)
        step.execute()

        payload = kb.client.upsert.call_args[0][1][0].payload
        assert payload["pr_url"] is None


class TestFixSummaryGeneration:
    """_build_fix_summary produces searchable text."""

    def test_summary_contains_service_and_condition(self):
        metadata = _proven_fix_metadata()
        step, _, _, _, _ = _make_step(pipeline_metadata=metadata)
        summary = step._build_fix_summary()
        assert "payments" in summary
        assert "high_error_rate" in summary

    def test_summary_contains_root_cause(self):
        metadata = _proven_fix_metadata()
        step, _, _, _, _ = _make_step(pipeline_metadata=metadata)
        summary = step._build_fix_summary()
        assert "Connection pool exhaustion" in summary

    def test_summary_contains_resolution(self):
        metadata = _proven_fix_metadata()
        step, _, _, _, _ = _make_step(pipeline_metadata=metadata)
        summary = step._build_fix_summary()
        assert "Increase connection pool size" in summary

    def test_summary_contains_metric_improvement(self):
        metadata = _proven_fix_metadata()
        step, _, _, _, _ = _make_step(pipeline_metadata=metadata)
        summary = step._build_fix_summary()
        assert "http_error_rate" in summary
        assert "86.7%" in summary


class TestEmbeddingGeneration:
    """embedding generated from fix summary."""

    def test_embedding_called_with_summary(self):
        metadata = _proven_fix_metadata()
        step, llm, _, _, _ = _make_step(pipeline_metadata=metadata)
        step.execute()
        llm.embed_sync.assert_called_once()
        call_text = llm.embed_sync.call_args[0][0]
        assert "payments" in call_text


class TestEmbeddingFailureFallback:
    """embedding failure produces zero vector, step still succeeds."""

    def test_embedding_failure(self):
        metadata = _proven_fix_metadata()
        step, llm, kb, _, _ = _make_step(pipeline_metadata=metadata)
        llm.embed_sync.side_effect = RuntimeError("Embedding API down")
        result = step.execute()
        assert result.success is True
        # Should still attempt to persist with zero vector
        kb.client.upsert.assert_called_once()
        point = kb.client.upsert.call_args[0][1][0]
        assert point.vector == [0.0] * 1536


class TestKBPersistenceFailure:
    """Qdrant upsert fails → step still returns success=True."""

    def test_persistence_failure_returns_success(self):
        metadata = _proven_fix_metadata()
        step, _, kb, _, _ = _make_step(pipeline_metadata=metadata)
        kb.client.upsert.side_effect = RuntimeError("Qdrant down")
        with patch.object(step, "_buffer_to_file", return_value=None):
            result = step.execute()
        assert result.success is True
        assert result.data["kb_entry_created"] is False
        assert result.data["proven_fix_skip_reason"] == "persistence_failed"


class TestKBPersistenceRetry:
    """Verify retry logic (3 attempts)."""

    def test_retries_three_times(self):
        metadata = _proven_fix_metadata()
        step, _, kb, _, _ = _make_step(pipeline_metadata=metadata)
        kb.client.upsert.side_effect = RuntimeError("Qdrant down")
        with patch.object(step, "_buffer_to_file", return_value=None):
            with patch("beeper_investigator.remediation.proven_fix_accumulator.time.sleep"):
                step.execute()
        assert kb.client.upsert.call_count == 3


class TestStepName:
    """step.name == 'Proven Fix Accumulation'."""

    def test_name(self):
        step, _, _, _, _ = _make_step()
        assert step.name == "Proven Fix Accumulation"


class TestStepSuccessAlways:
    """step always returns success=True regardless of outcome."""

    def test_success_on_skip(self):
        step, _, _, _, _ = _make_step(pipeline_metadata={})
        assert step.execute().success is True

    def test_success_on_accumulation(self):
        step, _, _, _, _ = _make_step(pipeline_metadata=_proven_fix_metadata())
        assert step.execute().success is True

    def test_success_on_failure(self):
        metadata = _proven_fix_metadata()
        step, _, kb, _, _ = _make_step(pipeline_metadata=metadata)
        kb.client.upsert.side_effect = RuntimeError("fail")
        with patch.object(step, "_buffer_to_file", return_value=None):
            with patch("beeper_investigator.remediation.proven_fix_accumulator.time.sleep"):
                assert step.execute().success is True


class TestPipelineMetadataOutput:
    """step adds kb_entry_created, proven_fix_entry_id, proven_fix_skip_reason."""

    def test_output_keys_on_success(self):
        step, _, _, _, _ = _make_step(pipeline_metadata=_proven_fix_metadata())
        result = step.execute()
        assert "kb_entry_created" in result.data
        assert "proven_fix_entry_id" in result.data
        assert "proven_fix_skip_reason" in result.data
        assert "proven_fix_buffered" in result.data
        assert "proven_fix_buffer_path" in result.data

    def test_output_keys_on_skip(self):
        step, _, _, _, _ = _make_step(pipeline_metadata={})
        result = step.execute()
        assert result.data["kb_entry_created"] is False
        assert result.data["proven_fix_skip_reason"] == "fix_not_proven"


class TestVerificationStatusIncluded:
    """verification evidence dict in payload matches metric verifier output."""

    def test_verification_evidence_structure(self):
        metadata = _proven_fix_metadata()
        step, _, kb, _, _ = _make_step(pipeline_metadata=metadata)
        step.execute()
        payload = kb.client.upsert.call_args[0][1][0].payload
        evidence = payload["verification_evidence"]
        assert isinstance(evidence, dict)
        assert "status" in evidence
        assert "window_minutes" in evidence
        assert "results" in evidence


class TestBufferToFileOnPersistenceFailure:
    """failed persistence buffers entry to file."""

    def test_buffer_on_qdrant_failure(self, tmp_path):
        metadata = _proven_fix_metadata()
        step, _, kb, _, _ = _make_step(pipeline_metadata=metadata)
        kb.client.upsert.side_effect = RuntimeError("Qdrant down")
        with patch.dict(
            "os.environ", {"BEEPER_BUFFER_DIR": str(tmp_path)}
        ):
            with patch("beeper_investigator.remediation.proven_fix_accumulator.time.sleep"):
                result = step.execute()
        assert result.data["proven_fix_buffered"] is True
        assert result.data["proven_fix_buffer_path"] is not None
        # Verify file was written
        buffer_path = result.data["proven_fix_buffer_path"]
        with open(buffer_path) as f:
            buffer_data = json.load(f)
        assert buffer_data["payload"]["entry_type"] == "proven_fix"
        assert buffer_data["collection"] == "knowledge"


class TestPayloadTitle:
    """title format is 'Proven Fix: {documentation_title}'."""

    def test_title_from_documentation(self):
        metadata = _proven_fix_metadata()
        step, _, kb, _, _ = _make_step(pipeline_metadata=metadata)
        step.execute()
        payload = kb.client.upsert.call_args[0][1][0].payload
        assert payload["title"] == "Proven Fix: Connection Pool Exhaustion - payments"

    def test_title_fallback(self):
        metadata = _proven_fix_metadata()
        del metadata["documentation_title"]
        step, _, kb, _, _ = _make_step(pipeline_metadata=metadata)
        step.execute()
        payload = kb.client.upsert.call_args[0][1][0].payload
        assert payload["title"] == "Proven Fix: high_error_rate - payments"
