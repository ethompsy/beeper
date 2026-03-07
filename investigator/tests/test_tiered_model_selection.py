"""Tests for tiered LLM model selection (Story 3.9).

Covers: deep_rca_model config/property, select_model(), model usage tracking,
tier propagation in steps, and model_usage in InvestigationResult.
"""

import json
import logging
import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from beeper_investigator.context import InvestigationContext
from beeper_investigator.llm.client import LlmClient, LlmConfig

# ── Helpers ─────────────────────────────────────────────────


def _make_config(**overrides: Any) -> LlmConfig:
    defaults: dict[str, Any] = {
        "provider": "anthropic",
        "model": "claude-sonnet-4",
        "api_key": "test-key",
    }
    defaults.update(overrides)
    return LlmConfig(**defaults)


def _make_client(**overrides: Any) -> LlmClient:
    return LlmClient(_make_config(**overrides))


def _make_context() -> InvestigationContext:
    return InvestigationContext(
        investigation_id="inv-test-001",
        namespace="default",
        condition="High error rate",
        service="payments",
        severity="high",
    )


def _mock_completion_response(content: str = "response") -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    return resp


# ── 9.1: LlmConfig.deep_rca_model defaults to None ──────


class TestLlmConfigDeepRcaModel:
    def test_deep_rca_model_defaults_none(self) -> None:
        config = LlmConfig(
            provider="anthropic", model="claude-sonnet-4", api_key="key",
        )
        assert config.deep_rca_model is None

    # ── 9.2: from_env() loads BEEPER_LLM_DEEP_RCA_MODEL ──

    def test_deep_rca_model_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "BEEPER_LLM_PROVIDER": "anthropic",
                "BEEPER_LLM_MODEL": "claude-sonnet-4",
                "BEEPER_LLM_API_KEY": "key",
                "BEEPER_LLM_DEEP_RCA_MODEL": "claude-opus-4",
            },
            clear=True,
        ):
            config = LlmConfig.from_env()
            assert config.deep_rca_model == "claude-opus-4"

    def test_deep_rca_model_empty_env_is_none(self) -> None:
        with patch.dict(
            os.environ,
            {
                "BEEPER_LLM_PROVIDER": "anthropic",
                "BEEPER_LLM_MODEL": "claude-sonnet-4",
                "BEEPER_LLM_API_KEY": "key",
                "BEEPER_LLM_DEEP_RCA_MODEL": "",
            },
            clear=True,
        ):
            config = LlmConfig.from_env()
            assert config.deep_rca_model is None


# ── 9.3 / 9.4: LlmClient.deep_rca_model property ───────


class TestLlmClientDeepRcaModel:
    def test_returns_configured_model(self) -> None:
        client = _make_client(deep_rca_model="claude-opus-4")
        assert client.deep_rca_model == "claude-opus-4"

    def test_falls_back_to_default(self) -> None:
        client = _make_client()
        assert client.deep_rca_model == "claude-sonnet-4"

    def test_fallback_uses_litellm_format(self) -> None:
        client = _make_client(
            provider="azure",
            model="my-deployment",
            endpoint="https://my.azure.endpoint",
        )
        assert client.deep_rca_model == "azure/my-deployment"


# ── 9.5 / 9.6 / 9.7: select_model() ────────────────────


class TestSelectModel:
    def test_screening_returns_screening_model(self) -> None:
        client = _make_client(screening_model="claude-3-haiku-20240307")
        assert client.select_model("screening") == "claude-3-haiku-20240307"

    def test_standard_returns_default_model(self) -> None:
        client = _make_client()
        assert client.select_model("standard") == "claude-sonnet-4"

    def test_deep_rca_returns_deep_rca_model(self) -> None:
        client = _make_client(deep_rca_model="claude-opus-4")
        assert client.select_model("deep_rca") == "claude-opus-4"

    # ── 9.8: select_model logs at INFO level ──

    def test_logs_model_selection(self, caplog: pytest.LogCaptureFixture) -> None:
        client = _make_client(deep_rca_model="claude-opus-4")
        with caplog.at_level(logging.INFO):
            client.select_model("deep_rca")
        assert any(
            "deep_rca" in record.message and "claude-opus-4" in record.message
            for record in caplog.records
        )

    # ── 9.17: all tiers fall back when not configured ──

    def test_screening_fallback(self) -> None:
        client = _make_client()
        assert client.select_model("screening") == "claude-sonnet-4"

    def test_deep_rca_fallback(self) -> None:
        client = _make_client()
        assert client.select_model("deep_rca") == "claude-sonnet-4"

    def test_standard_is_always_default(self) -> None:
        client = _make_client(
            screening_model="haiku", deep_rca_model="opus",
        )
        assert client.select_model("standard") == "claude-sonnet-4"

    def test_invalid_tier_raises(self) -> None:
        client = _make_client()
        with pytest.raises(ValueError, match="Unknown model tier"):
            client.select_model("invalid")  # type: ignore[arg-type]


# ── 9.9 / 9.10: Model usage tracking ────────────────────


class TestModelUsageTracking:
    def test_tracks_call_counts(self) -> None:
        client = _make_client()
        resp = _mock_completion_response()
        with patch("litellm.completion", return_value=resp):
            client.complete_sync(
                [{"role": "user", "content": "a"}],
                model="claude-opus-4",
            )
            client.complete_sync(
                [{"role": "user", "content": "b"}],
                model="claude-opus-4",
            )
            client.complete_sync(
                [{"role": "user", "content": "c"}],
                model="claude-sonnet-4",
            )

        usage = client.get_model_usage()
        assert usage == {"claude-opus-4": 2, "claude-sonnet-4": 1}

    def test_get_model_usage_returns_copy(self) -> None:
        client = _make_client()
        resp = _mock_completion_response()
        with patch("litellm.completion", return_value=resp):
            client.complete_sync(
                [{"role": "user", "content": "x"}],
                model="test-model",
            )
        usage = client.get_model_usage()
        usage["test-model"] = 999
        assert client.get_model_usage()["test-model"] == 1

    def test_reset_clears_counters(self) -> None:
        client = _make_client()
        resp = _mock_completion_response()
        with patch("litellm.completion", return_value=resp):
            client.complete_sync(
                [{"role": "user", "content": "x"}],
                model="test-model",
            )
        client.reset_model_usage()
        assert client.get_model_usage() == {}

    def test_empty_initially(self) -> None:
        client = _make_client()
        assert client.get_model_usage() == {}

    def test_failed_call_not_counted(self) -> None:
        client = _make_client()
        with patch("litellm.completion", side_effect=Exception("fail")):
            with pytest.raises(Exception):
                client.complete_sync(
                    [{"role": "user", "content": "x"}],
                    model="test-model",
                )
        assert client.get_model_usage() == {}


# ── 9.11 / 9.12: RCAHypothesisStep tier propagation ─────


class TestRCAHypothesisModelTier:
    def test_passes_deep_rca_model(self) -> None:
        from beeper_investigator.steps.rca_hypothesis import RCAHypothesisStep

        mock_llm = MagicMock()
        mock_llm.select_model.return_value = "claude-opus-4"
        mock_llm.complete_sync.return_value = json.dumps({
            "root_cause_hypothesis": "DB pool exhaustion",
            "confidence_level": "high",
            "confidence_percentage": 90,
            "supporting_evidence": ["evidence"],
            "alternative_hypotheses": [],
            "additional_data_needs": [],
            "kb_citation": None,
        })

        step = RCAHypothesisStep(
            llm_client=mock_llm,
            context=_make_context(),
            status_updater=MagicMock(),
            pipeline_metadata={"customer_impacting": True},
        )
        result = step.execute()

        mock_llm.select_model.assert_called_once_with("deep_rca")
        call_args = mock_llm.complete_sync.call_args
        assert call_args.kwargs.get("model") == "claude-opus-4"
        assert result.data["rca_model_tier"] == "deep_rca"
        assert result.data["rca_model_used"] == "claude-opus-4"

    def test_fallback_preserves_tier(self) -> None:
        from beeper_investigator.steps.rca_hypothesis import RCAHypothesisStep

        mock_llm = MagicMock()
        mock_llm.select_model.return_value = "claude-opus-4"
        mock_llm.complete_sync.side_effect = Exception("fail")

        step = RCAHypothesisStep(
            llm_client=mock_llm,
            context=_make_context(),
            status_updater=MagicMock(),
            pipeline_metadata={"customer_impacting": True},
        )
        result = step.execute()

        assert result.data["rca_model_tier"] == "deep_rca"
        assert result.data["rca_model_used"] == "claude-opus-4"


# ── 9.13: ResolutionRecommendationStep tier propagation ──


class TestResolutionRecommendationModelTier:
    def test_includes_standard_tier(self) -> None:
        from beeper_investigator.steps.resolution_recommendations import (
            ResolutionRecommendationStep,
        )

        mock_llm = MagicMock()
        mock_llm.select_model.return_value = "claude-sonnet-4"
        mock_llm.complete_sync.return_value = json.dumps({
            "recommendations": [
                {
                    "action": "Restart pods",
                    "confidence": "high",
                    "expected_outcome": "Service restored",
                    "risk_assessment": "low",
                    "based_on_prior_incident": None,
                }
            ],
            "ranking_rationale": "test",
            "diagnostic_actions": [],
        })

        step = ResolutionRecommendationStep(
            llm_client=mock_llm,
            context=_make_context(),
            status_updater=MagicMock(),
            pipeline_metadata={
                "root_cause_hypothesis": "DB pool exhaustion",
                "confidence_level": "high",
            },
        )
        result = step.execute()

        mock_llm.select_model.assert_called_once_with("standard")
        assert result.data["resolution_model_tier"] == "standard"
        assert result.data["resolution_model_used"] == "claude-sonnet-4"


# ── 9.14: InvestigationDocumentationStep tier propagation ──


class TestInvestigationDocumentationModelTier:
    def test_includes_standard_tier(self) -> None:
        from beeper_investigator.steps.investigation_documentation import (
            InvestigationDocumentationStep,
        )

        mock_llm = MagicMock()
        mock_llm.select_model.return_value = "claude-sonnet-4"
        mock_llm.complete_sync.return_value = json.dumps({
            "title": "Test Investigation",
            "summary": "Test summary",
            "root_cause": "Test cause",
            "resolution": "Test resolution",
            "signals_summary": "Test signals",
            "confidence_overview": "High",
            "key_findings": ["finding"],
        })
        mock_llm.embed_sync.return_value = [0.1] * 1536

        mock_kb = MagicMock()

        step = InvestigationDocumentationStep(
            llm_client=mock_llm,
            kb_client=mock_kb,
            context=_make_context(),
            status_updater=MagicMock(),
            pipeline_metadata={
                "root_cause_hypothesis": "test",
                "confidence_level": "high",
            },
        )
        result = step.execute()

        mock_llm.select_model.assert_called_once_with("standard")
        assert result.data["doc_model_tier"] == "standard"
        assert result.data["doc_model_used"] == "claude-sonnet-4"


# ── 9.15: CustomerImpactStep uses select_model ──────────


class TestCustomerImpactSelectModel:
    def test_uses_select_model_screening(self) -> None:
        from beeper_investigator.steps.impact_assessment import CustomerImpactStep

        mock_llm = MagicMock()
        mock_llm.select_model.return_value = "claude-3-haiku-20240307"
        mock_llm.complete_sync.return_value = json.dumps(
            {"customer_impacting": True, "reasoning": "test"}
        )

        step = CustomerImpactStep(
            llm_client=mock_llm,
            context=_make_context(),
            status_updater=MagicMock(),
        )
        result = step.execute()

        mock_llm.select_model.assert_called_once_with("screening")
        call_args = mock_llm.complete_sync.call_args
        assert call_args.kwargs.get("model") == "claude-3-haiku-20240307"
        assert result.data["impact_model_tier"] == "screening"
        assert result.data["impact_model_used"] == "claude-3-haiku-20240307"


# ── 9.16: model_usage propagated to InvestigationResult ──


class TestModelUsagePropagation:
    def test_model_usage_in_result_metadata(self) -> None:
        from beeper_investigator.agent import (
            InvestigatorAgent,
            SourceClients,
        )

        mock_kb = MagicMock()
        mock_kb.health_check.return_value = True

        mock_llm = MagicMock()
        mock_llm.test_connection.return_value = True
        mock_llm.get_model_usage.return_value = {
            "claude-sonnet-4": 3,
            "claude-opus-4": 1,
        }

        mock_step = MagicMock()
        mock_step.name = "test-step"
        from beeper_investigator.steps import StepResult

        mock_step.execute.return_value = StepResult(
            success=True,
            summary="ok",
            data={"test": True},
        )

        agent = InvestigatorAgent(
            context=_make_context(),
            kb_client=mock_kb,
            llm_client=mock_llm,
            sources=SourceClients(),
            status_updater=MagicMock(),
        )
        agent.steps = [mock_step]

        result = agent.run()

        assert result.metadata["model_usage"] == {
            "claude-sonnet-4": 3,
            "claude-opus-4": 1,
        }
