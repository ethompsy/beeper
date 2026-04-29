"""Tests for RCAHypothesisStep."""

import json
from typing import Any
from unittest.mock import MagicMock

from beeper_investigator.context import InvestigationContext
from beeper_investigator.steps.rca_hypothesis import (
    RCAHypothesisStep,
    _validate_confidence,
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
    """Return pipeline metadata simulating all prior steps succeeded."""
    return {
        # From CustomerImpactStep
        "customer_impacting": True,
        "reasoning": "Payment service directly handles user transactions",
        # From KBQueryStep
        "kb_available": True,
        "prior_investigations_count": 2,
        "prior_knowledge_count": 1,
        "exact_match_found": True,
        "exact_match_id": "inv-prev-042",
        "prior_research_summary": (
            "Similar checkout failures were caused by"
            " DB pool exhaustion in Q3"
        ),
        "relevant_matches": [
            "inv-prev-042: DB pool exhaustion",
            "inv-prev-031: High latency checkout",
        ],
        "recommended_resolution": "Increase DB connection pool size and add circuit breaker",
        "confidence_boost": "high",
        # From SignalCorrelationStep
        "sources_available": {"prometheus": True, "loki": True},
        "layers_queried": ["application", "data", "infrastructure", "platform"],
        "signals_gathered": 12,
        "signal_summary": (
            "DB connection pool saturated at 100%;"
            " application 5xx rate spiked to 15%"
        ),
        "hypotheses": [
            {
                "description": "Database connection pool exhaustion causing application timeouts",
                "causal_chain": "DB connection limit reached -> query timeouts -> 5xx responses",
                "confidence": "high",
                "supporting_signals": ["pg_stat_activity at max", "http_5xx spike"],
                "originating_layer": "data",
            },
            {
                "description": "Memory pressure causing OOM kills on payment pods",
                "causal_chain": "High memory usage -> OOM kill -> pod restart -> request failures",
                "confidence": "low",
                "supporting_signals": ["node_memory_available low"],
                "originating_layer": "infrastructure",
            },
        ],
        "service_dependency_chain": ["payments-db", "payments", "api-gateway"],
        "temporal_summary": (
            "15:03 DB connection count began climbing; "
            "15:05 first 5xx errors on /checkout; "
            "15:07 error rate peaked at 15%"
        ),
        "raw_signal_detail": (
            "[data] prometheus: pg_stat_activity_count → 1 series"
            " | pg_stat_activity_count{service=payments}: latest=100, min=45, max=100, points=30\n"
            "[application] loki: {namespace=\"default\"} |= \"error\" → 2 streams"
            " | 47 log entries, samples: ['2026-04-10T15:05:12Z ERROR payments "
            "connection pool exhausted: max connections reached', "
            "'2026-04-10T15:05:13Z ERROR checkout request failed: upstream timeout']"
        ),
        "correlation_attempted": True,
    }


def _make_step(
    *,
    pipeline_metadata: dict[str, Any] | None = None,
    llm_response: str | None = None,
    llm_error: Exception | None = None,
    condition: str = "High error rate on /checkout endpoint",
    service: str = "payments",
    severity: str = "high",
) -> tuple[RCAHypothesisStep, MagicMock, MagicMock]:
    """Build an RCAHypothesisStep with mocked dependencies."""
    ctx = _make_context(condition=condition, service=service, severity=severity)

    mock_llm = MagicMock()

    default_response = json.dumps({
        "root_cause_hypothesis": (
            "Database connection pool exhaustion caused"
            " cascading checkout failures"
        ),
        "confidence_level": "high",
        "confidence_percentage": 90,
        "supporting_evidence": [
            "pg_stat_activity at max connections",
            "5xx error rate spiked from 0.1% to 15%",
            "Prior incident inv-prev-042 confirms this pattern",
        ],
        "alternative_hypotheses": [],
        "additional_data_needs": [],
        "kb_citation": "inv-prev-042",
    })

    mock_llm.select_model.return_value = "claude-sonnet-4"

    if llm_error:
        mock_llm.complete_sync.side_effect = llm_error
    else:
        mock_llm.complete_sync.return_value = llm_response or default_response

    mock_status = MagicMock()

    step = RCAHypothesisStep(
        llm_client=mock_llm,
        context=ctx,
        status_updater=mock_status,
        pipeline_metadata=(
            pipeline_metadata
            if pipeline_metadata is not None
            else _full_pipeline_metadata()
        ),
    )
    return step, mock_llm, mock_status


# ── Task 7.2: Hypothesis generated with confidence level and percentage (AC1) ──


class TestHypothesisGeneration:
    """Tests for basic hypothesis generation (AC1)."""

    def test_hypothesis_with_confidence_and_percentage(self) -> None:
        """Hypothesis includes root cause, confidence level, and percentage (AC1)."""
        step, *_ = _make_step()

        result = step.execute()

        assert result.success is True
        assert result.data["root_cause_hypothesis"]
        assert result.data["confidence_level"] in ("high", "medium", "low")
        assert isinstance(result.data["confidence_percentage"], int)
        assert 0 <= result.data["confidence_percentage"] <= 100
        assert isinstance(result.data["supporting_evidence"], list)
        assert result.data["synthesis_source"] == "llm"

    def test_supporting_evidence_present(self) -> None:
        """Supporting evidence is included in the result (AC1)."""
        step, *_ = _make_step()

        result = step.execute()

        assert len(result.data["supporting_evidence"]) >= 1


# ── Task 7.3: Strong evidence → high confidence (AC2) ──────────


class TestHighConfidence:
    """Tests for strong evidence scenarios (AC2)."""

    def test_strong_evidence_high_confidence(self) -> None:
        """Strong signal correlation → high confidence with percentage >80% (AC2)."""
        response = json.dumps({
            "root_cause_hypothesis": "DB pool exhaustion",
            "confidence_level": "high",
            "confidence_percentage": 92,
            "supporting_evidence": ["DB metrics confirm saturation"],
            "alternative_hypotheses": [],
            "additional_data_needs": [],
            "kb_citation": "inv-prev-042",
        })
        step, *_ = _make_step(llm_response=response)

        result = step.execute()

        assert result.data["confidence_level"] == "high"
        assert result.data["confidence_percentage"] > 80


# ── Task 7.4: Weak/conflicting → low confidence (AC3) ─────────


class TestLowConfidence:
    """Tests for weak/conflicting signal scenarios (AC3)."""

    def test_weak_signals_low_confidence(self) -> None:
        """Weak signals → low confidence with uncertainty and additional data needs (AC3)."""
        response = json.dumps({
            "root_cause_hypothesis": "Possibly network partition but evidence is inconclusive",
            "confidence_level": "low",
            "confidence_percentage": 25,
            "supporting_evidence": ["Minor latency increase observed"],
            "alternative_hypotheses": [
                {"description": "DNS resolution delay", "confidence_percentage": 20}
            ],
            "additional_data_needs": ["Network tap data", "DNS resolution logs"],
            "kb_citation": None,
        })
        step, *_ = _make_step(llm_response=response)

        result = step.execute()

        assert result.data["confidence_level"] == "low"
        assert result.data["confidence_percentage"] < 50
        assert len(result.data["alternative_hypotheses"]) >= 1
        assert len(result.data["additional_data_needs"]) >= 1


# ── Task 7.5: KB exact match boosts confidence (AC4) ──────────


class TestKBBoost:
    """Tests for KB match confidence boosting (AC4)."""

    def test_kb_exact_match_boosts_confidence(self) -> None:
        """KB exact match boosts confidence and cites prior incident (AC4)."""
        metadata = _full_pipeline_metadata()
        response = json.dumps({
            "root_cause_hypothesis": "DB connection pool exhaustion (confirmed by prior incident)",
            "confidence_level": "high",
            "confidence_percentage": 95,
            "supporting_evidence": ["Signal correlation matches prior pattern"],
            "alternative_hypotheses": [],
            "additional_data_needs": [],
            "kb_citation": "inv-prev-042",
        })
        step, *_ = _make_step(pipeline_metadata=metadata, llm_response=response)

        result = step.execute()

        assert result.data["confidence_level"] == "high"
        assert result.data["kb_citation"] is not None
        # KB exact match evidence should be added
        has_kb_evidence = any(
            "inv-prev-042" in e for e in result.data["supporting_evidence"]
        )
        assert has_kb_evidence

    def test_kb_medium_confidence_boost(self) -> None:
        """KB confidence_boost 'medium' with relevant matches (Task 7.6)."""
        metadata = _full_pipeline_metadata()
        metadata["confidence_boost"] = "medium"
        metadata["exact_match_found"] = False
        metadata.pop("exact_match_id", None)

        response = json.dumps({
            "root_cause_hypothesis": "Likely DB pool issue based on similar incidents",
            "confidence_level": "medium",
            "confidence_percentage": 65,
            "supporting_evidence": ["Similar pattern in KB"],
            "alternative_hypotheses": [
                {"description": "Network issue", "confidence_percentage": 30}
            ],
            "additional_data_needs": [],
            "kb_citation": None,
        })
        step, *_ = _make_step(pipeline_metadata=metadata, llm_response=response)

        result = step.execute()

        assert result.data["confidence_level"] == "medium"
        # No KB exact match boost applied when exact_match_found is False
        assert result.data["synthesis_source"] == "llm"


# ── Task 7.7: All prior step data missing ─────────────────────


class TestMissingData:
    """Tests for missing pipeline metadata."""

    def test_all_prior_data_missing(self) -> None:
        """All prior step data missing → graceful 'insufficient data' (Task 7.7)."""
        step, mock_llm, _ = _make_step(pipeline_metadata={})

        result = step.execute()

        assert result.success is True
        assert result.data["confidence_level"] == "low"
        hyp = result.data["root_cause_hypothesis"].lower()
        assert "insufficient" in hyp or "unable" in hyp
        assert result.data["synthesis_source"] == "fallback"
        assert len(result.data["additional_data_needs"]) >= 1
        # LLM should NOT be called when no data available
        mock_llm.complete_sync.assert_not_called()

    def test_partial_data_impact_only(self) -> None:
        """Impact available, KB and signals unavailable (Task 7.8)."""
        metadata = {
            "customer_impacting": True,
            "reasoning": "Payment service affects users directly",
        }
        response = json.dumps({
            "root_cause_hypothesis": "Customer-impacting issue with unknown root cause",
            "confidence_level": "low",
            "confidence_percentage": 20,
            "supporting_evidence": ["Customer impact confirmed"],
            "alternative_hypotheses": [
                {"description": "Unknown system failure", "confidence_percentage": 15}
            ],
            "additional_data_needs": ["Signal correlation data", "KB research"],
            "kb_citation": None,
        })
        step, *_ = _make_step(pipeline_metadata=metadata, llm_response=response)

        result = step.execute()

        assert result.success is True
        assert result.data["confidence_level"] == "low"
        assert len(result.data["additional_data_needs"]) >= 1

    def test_partial_data_signals_and_impact_no_kb(self) -> None:
        """Impact and signals available, KB unavailable (Task 7.8)."""
        metadata = {
            "customer_impacting": True,
            "reasoning": "Payment failures affect checkout",
            "signal_summary": "5xx rate at 15%, DB connections at max",
            "hypotheses": [
                {
                    "description": "DB exhaustion",
                    "causal_chain": "DB -> app",
                    "confidence": "high",
                    "supporting_signals": ["db_connections_max"],
                    "originating_layer": "data",
                }
            ],
            "layers_queried": ["application", "data"],
            "signals_gathered": 6,
        }
        response = json.dumps({
            "root_cause_hypothesis": "DB connection pool exhaustion",
            "confidence_level": "high",
            "confidence_percentage": 85,
            "supporting_evidence": ["5xx rate spiked", "DB at max connections"],
            "alternative_hypotheses": [],
            "additional_data_needs": [],
            "kb_citation": None,
        })
        step, *_ = _make_step(pipeline_metadata=metadata, llm_response=response)

        result = step.execute()

        assert result.success is True
        assert result.data["confidence_level"] == "high"


# ── Task 7.9: LLM failure fallback ────────────────────────────


class TestLLMFailure:
    """Tests for LLM failure and fallback paths."""

    def test_llm_failure_promotes_signal_hypothesis(self) -> None:
        """LLM failure → fallback promotes signal correlation hypothesis (Task 7.9)."""
        from beeper_investigator.llm.client import LlmClientError

        step, *_ = _make_step(llm_error=LlmClientError("LLM unavailable"))

        result = step.execute()

        assert result.success is True
        assert result.data["synthesis_source"] == "fallback"
        assert result.data["root_cause_hypothesis"]
        # Should promote the best signal correlation hypothesis
        hyp = result.data["root_cause_hypothesis"].lower()
        assert "database" in hyp or "connection" in hyp

    def test_llm_malformed_json_fallback(self) -> None:
        """LLM returns malformed JSON → graceful fallback (Task 7.10)."""
        step, *_ = _make_step(llm_response="This is not JSON at all {{{")

        result = step.execute()

        assert result.success is True
        assert result.data["synthesis_source"] == "fallback"

    def test_llm_empty_hypothesis_fallback(self) -> None:
        """LLM returns empty hypothesis → fallback."""
        response = json.dumps({
            "root_cause_hypothesis": "",
            "confidence_level": "medium",
            "confidence_percentage": 60,
            "supporting_evidence": [],
            "alternative_hypotheses": [],
            "additional_data_needs": [],
            "kb_citation": None,
        })
        step, *_ = _make_step(llm_response=response)

        result = step.execute()

        assert result.success is True
        assert result.data["synthesis_source"] == "fallback"

    def test_llm_markdown_wrapped_json(self) -> None:
        """LLM response wrapped in markdown fences is parsed correctly."""
        inner = json.dumps({
            "root_cause_hypothesis": "DB pool issue",
            "confidence_level": "high",
            "confidence_percentage": 88,
            "supporting_evidence": ["DB metrics"],
            "alternative_hypotheses": [],
            "additional_data_needs": [],
            "kb_citation": None,
        })
        response = f"```json\n{inner}\n```"
        step, *_ = _make_step(llm_response=response)

        result = step.execute()

        assert result.success is True
        assert result.data["synthesis_source"] == "llm"
        assert result.data["root_cause_hypothesis"] == "DB pool issue"


# ── Task 7.11: Confidence band validation ──────────────────────


class TestConfidenceBandValidation:
    """Tests for confidence band alignment validation."""

    def test_percentage_90_level_low_corrected_to_high(self) -> None:
        """Percentage 90 but level 'low' → corrected to 'high' (Task 7.11)."""
        response = json.dumps({
            "root_cause_hypothesis": "Root cause identified with high certainty",
            "confidence_level": "low",
            "confidence_percentage": 90,
            "supporting_evidence": ["Strong evidence"],
            "alternative_hypotheses": [],
            "additional_data_needs": [],
            "kb_citation": None,
        })
        step, *_ = _make_step(llm_response=response)

        result = step.execute()

        assert result.data["confidence_level"] == "high"
        assert result.data["confidence_percentage"] == 90

    def test_percentage_30_level_high_corrected_to_low(self) -> None:
        """Percentage 30 but level 'high' → corrected to 'low'."""
        response = json.dumps({
            "root_cause_hypothesis": "Uncertain hypothesis",
            "confidence_level": "high",
            "confidence_percentage": 30,
            "supporting_evidence": ["Weak evidence"],
            "alternative_hypotheses": [
                {"description": "Alt", "confidence_percentage": 20}
            ],
            "additional_data_needs": ["More data needed"],
            "kb_citation": None,
        })
        step, *_ = _make_step(llm_response=response)

        result = step.execute()

        assert result.data["confidence_level"] == "low"
        assert result.data["confidence_percentage"] == 30

    def test_percentage_65_level_low_corrected_to_medium(self) -> None:
        """Percentage 65 but level 'low' → corrected to 'medium'."""
        response = json.dumps({
            "root_cause_hypothesis": "Moderate confidence hypothesis",
            "confidence_level": "low",
            "confidence_percentage": 65,
            "supporting_evidence": ["Some evidence"],
            "alternative_hypotheses": [
                {"description": "Alt", "confidence_percentage": 40}
            ],
            "additional_data_needs": [],
            "kb_citation": None,
        })
        step, *_ = _make_step(llm_response=response)

        result = step.execute()

        assert result.data["confidence_level"] == "medium"
        assert result.data["confidence_percentage"] == 65

    def test_validate_confidence_function_directly(self) -> None:
        """Direct test of _validate_confidence helper."""
        assert _validate_confidence("low", 90) == ("high", 90)
        assert _validate_confidence("high", 30) == ("low", 30)
        assert _validate_confidence("low", 65) == ("medium", 65)
        assert _validate_confidence("high", None) == ("high", None)
        assert _validate_confidence("medium", 50) == ("medium", 50)
        assert _validate_confidence("medium", 80) == ("medium", 80)
        assert _validate_confidence("medium", 81) == ("high", 81)
        assert _validate_confidence("high", 0) == ("low", 0)
        assert _validate_confidence("low", 100) == ("high", 100)

    def test_percentage_clamped_to_0_100(self) -> None:
        """Confidence percentage is clamped to 0-100 range."""
        response = json.dumps({
            "root_cause_hypothesis": "Hypothesis",
            "confidence_level": "high",
            "confidence_percentage": 150,
            "supporting_evidence": [],
            "alternative_hypotheses": [],
            "additional_data_needs": [],
            "kb_citation": None,
        })
        step, *_ = _make_step(llm_response=response)

        result = step.execute()

        assert result.data["confidence_percentage"] <= 100

    def test_percentage_none_when_not_parseable(self) -> None:
        """Non-parseable percentage defaults to None."""
        response = json.dumps({
            "root_cause_hypothesis": "Hypothesis",
            "confidence_level": "medium",
            "confidence_percentage": "not a number",
            "supporting_evidence": [],
            "alternative_hypotheses": [
                {"description": "Alt", "confidence_percentage": 30}
            ],
            "additional_data_needs": [],
            "kb_citation": None,
        })
        step, *_ = _make_step(llm_response=response)

        result = step.execute()

        assert result.data["confidence_percentage"] is None


# ── Task 7.12: Alternative hypotheses present when confidence < high ──


class TestAlternativeHypotheses:
    """Tests for alternative hypotheses requirements."""

    def test_alternatives_present_when_medium_confidence(self) -> None:
        """Alternative hypotheses are present when confidence < high (Task 7.12)."""
        response = json.dumps({
            "root_cause_hypothesis": "Possible DB issue",
            "confidence_level": "medium",
            "confidence_percentage": 60,
            "supporting_evidence": ["Some evidence"],
            "alternative_hypotheses": [
                {"description": "Network issue", "confidence_percentage": 35}
            ],
            "additional_data_needs": [],
            "kb_citation": None,
        })
        step, *_ = _make_step(llm_response=response)

        result = step.execute()

        assert result.data["confidence_level"] == "medium"
        assert len(result.data["alternative_hypotheses"]) >= 1

    def test_alternatives_enforced_when_llm_omits_them(self) -> None:
        """LLM omits alternatives for medium → filled from signals."""
        response = json.dumps({
            "root_cause_hypothesis": "Possible DB issue",
            "confidence_level": "medium",
            "confidence_percentage": 60,
            "supporting_evidence": ["Some evidence"],
            "alternative_hypotheses": [],
            "additional_data_needs": [],
            "kb_citation": None,
        })
        step, *_ = _make_step(llm_response=response)

        result = step.execute()

        # Alternatives should be populated from signal correlation hypotheses
        assert len(result.data["alternative_hypotheses"]) >= 1

    def test_alternatives_not_required_for_high_confidence(self) -> None:
        """High confidence → alternatives not forcibly added."""
        response = json.dumps({
            "root_cause_hypothesis": "Confirmed DB pool exhaustion",
            "confidence_level": "high",
            "confidence_percentage": 95,
            "supporting_evidence": ["Strong evidence"],
            "alternative_hypotheses": [],
            "additional_data_needs": [],
            "kb_citation": None,
        })
        step, *_ = _make_step(llm_response=response)

        result = step.execute()

        assert result.data["confidence_level"] == "high"
        assert result.data["alternative_hypotheses"] == []


# ── Task 7.13: Additional data needs when confidence is low ────


class TestAdditionalDataNeeds:
    """Tests for additional_data_needs requirements."""

    def test_additional_data_needs_present_when_low(self) -> None:
        """additional_data_needs present when confidence is low (Task 7.13)."""
        response = json.dumps({
            "root_cause_hypothesis": "Unclear root cause",
            "confidence_level": "low",
            "confidence_percentage": 20,
            "supporting_evidence": [],
            "alternative_hypotheses": [
                {"description": "Alt", "confidence_percentage": 15}
            ],
            "additional_data_needs": ["More logs needed", "Network traces"],
            "kb_citation": None,
        })
        step, *_ = _make_step(llm_response=response)

        result = step.execute()

        assert result.data["confidence_level"] == "low"
        assert len(result.data["additional_data_needs"]) >= 1

    def test_additional_data_needs_enforced_when_llm_omits_them(self) -> None:
        """When LLM omits additional_data_needs for low confidence, they're auto-populated."""
        response = json.dumps({
            "root_cause_hypothesis": "Speculative hypothesis",
            "confidence_level": "low",
            "confidence_percentage": 25,
            "supporting_evidence": [],
            "alternative_hypotheses": [
                {"description": "Alt", "confidence_percentage": 20}
            ],
            "additional_data_needs": [],
            "kb_citation": None,
        })
        step, *_ = _make_step(llm_response=response)

        result = step.execute()

        assert result.data["confidence_level"] == "low"
        assert len(result.data["additional_data_needs"]) >= 1


# ── Task 7.14: StepResult schema consistency ───────────────────


class TestSchemaConsistency:
    """Tests for consistent StepResult data schema across all code paths."""

    _EXPECTED_KEYS = (
        "root_cause_hypothesis",
        "confidence_level",
        "confidence_percentage",
        "supporting_evidence",
        "alternative_hypotheses",
        "additional_data_needs",
        "kb_citation",
        "synthesis_source",
    )

    def test_schema_keys_present_llm_success(self) -> None:
        """All expected keys present on LLM success path."""
        step, *_ = _make_step()

        result = step.execute()

        for key in self._EXPECTED_KEYS:
            assert key in result.data, f"Missing key: {key}"

    def test_schema_keys_present_llm_failure(self) -> None:
        """All expected keys present on LLM failure path."""
        from beeper_investigator.llm.client import LlmClientError

        step, *_ = _make_step(llm_error=LlmClientError("fail"))

        result = step.execute()

        for key in self._EXPECTED_KEYS:
            assert key in result.data, f"Missing key: {key}"

    def test_schema_keys_present_no_metadata(self) -> None:
        """All expected keys present when no pipeline metadata."""
        step, *_ = _make_step(pipeline_metadata={})

        result = step.execute()

        for key in self._EXPECTED_KEYS:
            assert key in result.data, f"Missing key: {key}"

    def test_schema_keys_present_malformed_json(self) -> None:
        """All expected keys present on malformed JSON fallback."""
        step, *_ = _make_step(llm_response="not json")

        result = step.execute()

        for key in self._EXPECTED_KEYS:
            assert key in result.data, f"Missing key: {key}"


# ── Task 7.15: Step name and status update ─────────────────────


class TestStepMetadata:
    """Tests for step name and status update message."""

    def test_step_name(self) -> None:
        """Step has correct name."""
        step, *_ = _make_step()
        assert step.name == "RCA Hypothesis Generation"

    def test_status_update_sent(self) -> None:
        """Step sends status update message during execution."""
        step, _, mock_status = _make_step()

        step.execute()

        mock_status.update_message.assert_called()
        msg = mock_status.update_message.call_args[0][0]
        assert "hypothesis" in msg.lower() or "root cause" in msg.lower()


# ── Prompt content verification ────────────────────────────────


class TestPromptContent:
    """Tests verifying LLM prompts include investigation context and evidence."""

    def test_prompt_includes_context(self) -> None:
        """LLM prompt includes investigation condition, service, severity."""
        step, mock_llm, _ = _make_step(
            condition="OOM kills",
            service="api-gateway",
            severity="critical",
        )

        step.execute()

        call_args = mock_llm.complete_sync.call_args
        messages = call_args[0][0]
        user_msg = messages[1]["content"]
        assert "OOM kills" in user_msg
        assert "api-gateway" in user_msg
        assert "critical" in user_msg

    def test_prompt_includes_impact_data(self) -> None:
        """LLM prompt includes customer impact information."""
        step, mock_llm, _ = _make_step()

        step.execute()

        call_args = mock_llm.complete_sync.call_args
        messages = call_args[0][0]
        user_msg = messages[1]["content"]
        assert "customer" in user_msg.lower() or "impact" in user_msg.lower()

    def test_prompt_includes_kb_data(self) -> None:
        """LLM prompt includes KB research data."""
        step, mock_llm, _ = _make_step()

        step.execute()

        call_args = mock_llm.complete_sync.call_args
        messages = call_args[0][0]
        user_msg = messages[1]["content"]
        assert "KB" in user_msg or "prior" in user_msg.lower() or "Q3" in user_msg

    def test_prompt_includes_signal_data(self) -> None:
        """LLM prompt includes signal correlation summary and hypotheses."""
        step, mock_llm, _ = _make_step()

        step.execute()

        call_args = mock_llm.complete_sync.call_args
        messages = call_args[0][0]
        user_msg = messages[1]["content"]
        assert "signal" in user_msg.lower() or "DB connection" in user_msg

    def test_prompt_includes_raw_signal_detail(self) -> None:
        """LLM prompt includes raw metric values and log excerpts (FR18)."""
        step, mock_llm, _ = _make_step()

        step.execute()

        call_args = mock_llm.complete_sync.call_args
        messages = call_args[0][0]
        user_msg = messages[1]["content"]
        # Raw Prometheus values should be present
        assert "latest=100" in user_msg
        assert "pg_stat_activity_count" in user_msg
        # Raw Loki log excerpts should be present
        assert "connection pool exhausted" in user_msg

    def test_prompt_includes_temporal_summary(self) -> None:
        """LLM prompt includes temporal sequence of events."""
        step, mock_llm, _ = _make_step()

        step.execute()

        call_args = mock_llm.complete_sync.call_args
        messages = call_args[0][0]
        user_msg = messages[1]["content"]
        assert "15:03" in user_msg
        assert "error rate peaked" in user_msg

    def test_uses_deep_rca_model(self) -> None:
        """Step uses deep_rca tier via select_model."""
        step, mock_llm, _ = _make_step()

        step.execute()

        mock_llm.select_model.assert_called_once_with("deep_rca")
        call_args = mock_llm.complete_sync.call_args
        assert call_args.kwargs.get("model") == "claude-sonnet-4"


# ── Review Fix: Fallback alternatives includes all hypotheses ──


class TestFallbackAlternativesFixed:
    """Tests verifying _fallback_alternatives includes all hypotheses."""

    def test_single_signal_hypothesis_included(self) -> None:
        """Single signal hypothesis appears as alternative (not skipped)."""
        metadata = {
            "customer_impacting": True,
            "reasoning": "Affects users",
            "signal_summary": "DB at max",
            "hypotheses": [
                {
                    "description": "DB pool exhaustion",
                    "causal_chain": "DB -> app",
                    "confidence": "high",
                    "supporting_signals": ["db_max"],
                    "originating_layer": "data",
                }
            ],
        }
        response = json.dumps({
            "root_cause_hypothesis": "LLM thinks network",
            "confidence_level": "medium",
            "confidence_percentage": 60,
            "supporting_evidence": ["Some evidence"],
            "alternative_hypotheses": [],
            "additional_data_needs": [],
            "kb_citation": None,
        })
        step, *_ = _make_step(
            pipeline_metadata=metadata, llm_response=response,
        )

        result = step.execute()

        alts = result.data["alternative_hypotheses"]
        alt_descs = [a["description"] for a in alts]
        assert "DB pool exhaustion" in alt_descs


# ── Review Fix: has_signals checks hypotheses too ──────────────


class TestHypothesesOnlySignals:
    """Tests for hypotheses present but signal_summary empty."""

    def test_hypotheses_without_signal_summary(self) -> None:
        """Hypotheses present but empty signal_summary still calls LLM."""
        metadata = {
            "customer_impacting": None,
            "signal_summary": "",
            "hypotheses": [
                {
                    "description": "DB issue",
                    "causal_chain": "DB -> app",
                    "confidence": "medium",
                    "supporting_signals": [],
                    "originating_layer": "data",
                }
            ],
        }
        response = json.dumps({
            "root_cause_hypothesis": "DB issue confirmed",
            "confidence_level": "medium",
            "confidence_percentage": 55,
            "supporting_evidence": ["Signal hypothesis"],
            "alternative_hypotheses": [
                {"description": "Alt", "confidence_percentage": 30}
            ],
            "additional_data_needs": [],
            "kb_citation": None,
        })
        step, mock_llm, _ = _make_step(
            pipeline_metadata=metadata, llm_response=response,
        )

        result = step.execute()

        assert result.success is True
        assert result.data["synthesis_source"] == "llm"
        mock_llm.complete_sync.assert_called_once()


# ── Review Fix: kb_citation "null" string handling ─────────────


class TestKbCitationNullString:
    """Test that string 'null' kb_citation is normalized to None."""

    def test_kb_citation_string_null_becomes_none(self) -> None:
        """LLM returning 'null' string for kb_citation → None."""
        metadata = _full_pipeline_metadata()
        metadata["exact_match_found"] = False
        metadata["confidence_boost"] = None
        metadata.pop("exact_match_id", None)

        response = json.dumps({
            "root_cause_hypothesis": "Some hypothesis",
            "confidence_level": "high",
            "confidence_percentage": 85,
            "supporting_evidence": ["Evidence"],
            "alternative_hypotheses": [],
            "additional_data_needs": [],
            "kb_citation": "null",
        })
        step, *_ = _make_step(
            pipeline_metadata=metadata, llm_response=response,
        )

        result = step.execute()

        assert result.data["kb_citation"] is None


# ── Story 2.5: SLO context in LLM prompt ────────────────────


class TestSLOContextInPrompt:
    """Tests that SLO breach data flows into the RCA prompt (Story 2.5)."""

    def test_prompt_includes_slo_context_when_present(self) -> None:
        """SLO data in pipeline_metadata appears in the user prompt."""
        metadata = _full_pipeline_metadata()
        metadata["slo_target"] = 0.999
        metadata["slo_compliance"] = 0.972
        metadata["slo_burn_rate"] = 28.0
        metadata["slo_error_budget_remaining"] = -1.8
        metadata["slo_sli_type"] = "availability"
        metadata["slo_condition"] = "Critical"

        step, mock_llm, _ = _make_step(pipeline_metadata=metadata)

        step.execute()

        call_args = mock_llm.complete_sync.call_args
        user_msg = call_args[0][0][1]["content"]
        assert "0.999" in user_msg
        assert "0.972" in user_msg
        assert "28.0" in user_msg
        assert "availability" in user_msg

    def test_prompt_omits_slo_section_when_absent(self) -> None:
        """No SLO data → SLO section is empty (no noise)."""
        metadata = _full_pipeline_metadata()
        # No slo_* keys at all

        step, mock_llm, _ = _make_step(pipeline_metadata=metadata)

        step.execute()

        call_args = mock_llm.complete_sync.call_args
        user_msg = call_args[0][0][1]["content"]
        # The SLO context section should be blank
        assert "SLI type:" not in user_msg
        assert "Current compliance:" not in user_msg
        assert "Burn rate:" not in user_msg

    def test_system_prompt_mentions_slo(self) -> None:
        """System prompt instructs LLM to reference SLO data."""
        step, mock_llm, _ = _make_step()

        step.execute()

        call_args = mock_llm.complete_sync.call_args
        system_msg = call_args[0][0][0]["content"]
        assert "SLO" in system_msg
        assert "burn rate" in system_msg

    def test_prompt_partial_slo_target_only(self) -> None:
        """SLO target present but compliance/burn_rate None (no Qdrant snapshot)."""
        metadata = _full_pipeline_metadata()
        metadata["slo_target"] = 0.999
        metadata["slo_sli_type"] = "availability"
        # slo_compliance, slo_burn_rate deliberately absent

        step, mock_llm, _ = _make_step(pipeline_metadata=metadata)

        step.execute()

        call_args = mock_llm.complete_sync.call_args
        user_msg = call_args[0][0][1]["content"]
        assert "0.999" in user_msg
        assert "availability" in user_msg
        # These should NOT appear since they're None
        assert "Current compliance:" not in user_msg
        assert "Burn rate:" not in user_msg
