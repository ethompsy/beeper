"""Tests for ResolutionRecommendationStep."""

import json
from typing import Any
from unittest.mock import MagicMock

from beeper_investigator.context import InvestigationContext
from beeper_investigator.steps.resolution_recommendations import (
    ResolutionRecommendationStep,
    _normalize_level,
    _parse_response,
    _sort_recommendations,
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
        "recommended_resolution": (
            "Increase DB connection pool size and add circuit breaker"
        ),
        "confidence_boost": "high",
        # From SignalCorrelationStep
        "sources_available": {"prometheus": True, "loki": True},
        "layers_queried": [
            "application", "data", "infrastructure", "platform",
        ],
        "signals_gathered": 12,
        "signal_summary": (
            "DB connection pool saturated at 100%;"
            " application 5xx rate spiked to 15%"
        ),
        "hypotheses": [
            {
                "description": (
                    "Database connection pool exhaustion"
                    " causing application timeouts"
                ),
                "causal_chain": (
                    "DB connection limit reached"
                    " -> query timeouts -> 5xx responses"
                ),
                "confidence": "high",
                "supporting_signals": [
                    "pg_stat_activity at max",
                    "http_5xx spike",
                ],
                "originating_layer": "data",
            },
        ],
        "service_dependency_chain": [
            "payments-db", "payments", "api-gateway",
        ],
        "temporal_summary": (
            "15:03 DB connection count began climbing; "
            "15:05 first 5xx errors on /checkout; "
            "15:07 error rate peaked at 15%"
        ),
        "raw_signal_detail": (
            "[data] prometheus: pg_stat_activity_count → 1 series"
            " | pg_stat_activity_count{service=payments}: latest=100, min=45, max=100, points=30\n"
            "[application] loki: {namespace=\"default\"} |= \"error\" → 2 streams"
            " | 47 log entries, samples: ['connection pool exhausted: max connections reached']"
        ),
        "correlation_attempted": True,
        # From RCAHypothesisStep
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
        "alternative_hypotheses": [],
        "additional_data_needs": [],
        "kb_citation": "inv-prev-042",
        "synthesis_source": "llm",
    }


def _default_llm_response() -> str:
    """Return a valid LLM response for resolution recommendations."""
    return json.dumps({
        "recommendations": [
            {
                "action": (
                    "Increase DB connection pool size from 20 to 50"
                ),
                "confidence": "high",
                "expected_outcome": (
                    "Resolve connection pool exhaustion"
                ),
                "risk_assessment": "low",
                "based_on_prior_incident": "inv-prev-042",
            },
            {
                "action": (
                    "Add circuit breaker to payment service"
                    " DB connections"
                ),
                "confidence": "medium",
                "expected_outcome": (
                    "Prevent cascading failures during"
                    " pool exhaustion"
                ),
                "risk_assessment": "low",
                "based_on_prior_incident": None,
            },
            {
                "action": "Scale payment service replicas to 5",
                "confidence": "low",
                "expected_outcome": (
                    "Distribute load across more instances"
                ),
                "risk_assessment": "medium",
                "based_on_prior_incident": None,
            },
        ],
        "ranking_rationale": (
            "Pool increase is proven fix from prior incident;"
            " circuit breaker is preventative"
        ),
        "diagnostic_actions": [
            "Check current pg_stat_activity connections",
            "Review connection pool metrics in Grafana",
        ],
    })


def _make_step(
    *,
    pipeline_metadata: dict[str, Any] | None = None,
    llm_response: str | None = None,
    llm_error: Exception | None = None,
    condition: str = "High error rate on /checkout endpoint",
    service: str = "payments",
    severity: str = "high",
) -> tuple[ResolutionRecommendationStep, MagicMock, MagicMock]:
    """Build a ResolutionRecommendationStep with mocked dependencies."""
    ctx = _make_context(
        condition=condition, service=service, severity=severity,
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

    mock_status = MagicMock()

    step = ResolutionRecommendationStep(
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


# ── 7.2: Recommendations with action, confidence, outcome, risk (AC1) ──


class TestRecommendationGeneration:
    """Tests for basic recommendation generation (AC1)."""

    def test_recommendations_have_required_fields(self) -> None:
        """Each recommendation includes action, confidence,
        expected_outcome, risk_assessment (AC1)."""
        step, *_ = _make_step()

        result = step.execute()

        assert result.success is True
        assert len(result.data["recommendations"]) >= 1
        for rec in result.data["recommendations"]:
            assert "action" in rec
            assert rec["confidence"] in ("high", "medium", "low")
            assert "expected_outcome" in rec
            assert rec["risk_assessment"] in ("high", "medium", "low")
            assert "based_on_prior_incident" in rec

    def test_synthesis_source_is_llm(self) -> None:
        """Successful LLM call sets synthesis_source to 'llm'."""
        step, *_ = _make_step()

        result = step.execute()

        assert result.data["synthesis_source"] == "llm"


# ── 7.3: Prior KB resolution promoted with elevated confidence (AC2) ──


class TestKBResolutionPromotion:
    """Tests for KB prior resolution promotion (AC2)."""

    def test_kb_exact_match_promotes_resolution(self) -> None:
        """KB exact match → resolution promoted with high confidence
        (AC2)."""
        metadata = _full_pipeline_metadata()
        # LLM response does NOT include the KB resolution
        response = json.dumps({
            "recommendations": [
                {
                    "action": "Scale service replicas",
                    "confidence": "medium",
                    "expected_outcome": "Distribute load",
                    "risk_assessment": "low",
                    "based_on_prior_incident": None,
                },
            ],
            "ranking_rationale": "Based on RCA",
            "diagnostic_actions": [],
        })
        step, *_ = _make_step(
            pipeline_metadata=metadata, llm_response=response,
        )

        result = step.execute()

        recs = result.data["recommendations"]
        # KB resolution should be present
        kb_recs = [
            r for r in recs
            if r.get("based_on_prior_incident") == "inv-prev-042"
        ]
        assert len(kb_recs) >= 1
        assert kb_recs[0]["confidence"] == "high"

    def test_kb_match_already_present_gets_boosted(self) -> None:
        """KB match already in LLM results → confidence elevated."""
        metadata = _full_pipeline_metadata()
        response = json.dumps({
            "recommendations": [
                {
                    "action": "Increase DB pool",
                    "confidence": "medium",
                    "expected_outcome": "Fix pool exhaustion",
                    "risk_assessment": "low",
                    "based_on_prior_incident": "inv-prev-042",
                },
            ],
            "ranking_rationale": "Based on KB",
            "diagnostic_actions": [],
        })
        step, *_ = _make_step(
            pipeline_metadata=metadata, llm_response=response,
        )

        result = step.execute()

        recs = result.data["recommendations"]
        kb_recs = [
            r for r in recs
            if r.get("based_on_prior_incident") == "inv-prev-042"
        ]
        assert len(kb_recs) >= 1
        assert kb_recs[0]["confidence"] == "high"

    def test_no_kb_match_no_promotion(self) -> None:
        """No KB exact match → no KB rec force-promoted."""
        metadata = _full_pipeline_metadata()
        metadata["exact_match_found"] = False
        metadata.pop("exact_match_id", None)
        step, *_ = _make_step(pipeline_metadata=metadata)

        result = step.execute()

        recs = result.data["recommendations"]
        # No rec should have been force-promoted by _promote_kb_resolution
        kb_promoted = [
            r for r in recs
            if (
                r.get("action")
                == metadata.get("recommended_resolution")
                and r.get("confidence") == "high"
                and r.get("based_on_prior_incident") is not None
            )
        ]
        assert len(kb_promoted) == 0


# ── 7.4: Uncertain RCA → safe diagnostic actions first (AC3) ──


class TestUncertainRCA:
    """Tests for uncertain RCA → diagnostic actions (AC3)."""

    def test_low_confidence_prepends_diagnostic(self) -> None:
        """Low RCA confidence → gather-more-info recommendation
        prepended (AC3)."""
        metadata = _full_pipeline_metadata()
        metadata["confidence_level"] = "low"
        metadata["confidence_percentage"] = 25
        step, *_ = _make_step(pipeline_metadata=metadata)

        result = step.execute()

        recs = result.data["recommendations"]
        assert len(recs) >= 1
        # Should have a gather/diagnostic action
        has_gather = any(
            "gather" in r.get("action", "").lower()
            or "diagnostic" in r.get("action", "").lower()
            for r in recs
        )
        assert has_gather

    def test_medium_confidence_no_gather_prepend(self) -> None:
        """Medium RCA confidence → no gather-info rec prepended."""
        metadata = _full_pipeline_metadata()
        metadata["confidence_level"] = "medium"
        metadata["confidence_percentage"] = 55
        step, *_ = _make_step(pipeline_metadata=metadata)

        result = step.execute()

        assert result.success is True
        recs = result.data["recommendations"]
        # Medium confidence should NOT get the explicit
        # "Gather additional diagnostic" recommendation
        has_gather = any(
            "gather additional diagnostic" in r.get(
                "action", ""
            ).lower()
            for r in recs
        )
        assert not has_gather

    def test_high_confidence_no_diagnostic_prepend(self) -> None:
        """High RCA confidence → no diagnostic prepend (AC3)."""
        metadata = _full_pipeline_metadata()
        metadata["confidence_level"] = "high"
        step, *_ = _make_step(pipeline_metadata=metadata)

        result = step.execute()

        recs = result.data["recommendations"]
        # No gather-diagnostic action forcibly prepended
        first_action = recs[0].get("action", "").lower() if recs else ""
        # First rec should NOT be a gather-info step for high confidence
        assert "gather additional diagnostic" not in first_action


# ── 7.5: Recommendations ranked by confidence and risk (AC4) ──


class TestRecommendationRanking:
    """Tests for recommendation ranking (AC4)."""

    def test_sorted_by_confidence_desc_risk_asc(self) -> None:
        """Recommendations sorted by confidence desc then risk asc
        (AC4)."""
        response = json.dumps({
            "recommendations": [
                {
                    "action": "Low conf high risk",
                    "confidence": "low",
                    "expected_outcome": "Unknown",
                    "risk_assessment": "high",
                    "based_on_prior_incident": None,
                },
                {
                    "action": "High conf low risk",
                    "confidence": "high",
                    "expected_outcome": "Fix issue",
                    "risk_assessment": "low",
                    "based_on_prior_incident": None,
                },
                {
                    "action": "Medium conf medium risk",
                    "confidence": "medium",
                    "expected_outcome": "Partial fix",
                    "risk_assessment": "medium",
                    "based_on_prior_incident": None,
                },
            ],
            "ranking_rationale": "Confidence then risk",
            "diagnostic_actions": [],
        })
        metadata = _full_pipeline_metadata()
        metadata["confidence_level"] = "high"
        step, *_ = _make_step(
            pipeline_metadata=metadata, llm_response=response,
        )

        result = step.execute()

        recs = result.data["recommendations"]
        # High confidence should come first
        conf_order = [r["confidence"] for r in recs]
        assert conf_order.index("high") < conf_order.index("low")

    def test_sort_recommendations_function(self) -> None:
        """Direct test of _sort_recommendations helper."""
        recs = [
            {
                "action": "a",
                "confidence": "low",
                "risk_assessment": "high",
            },
            {
                "action": "b",
                "confidence": "high",
                "risk_assessment": "low",
            },
            {
                "action": "c",
                "confidence": "high",
                "risk_assessment": "medium",
            },
            {
                "action": "d",
                "confidence": "medium",
                "risk_assessment": "low",
            },
        ]
        sorted_recs = _sort_recommendations(recs)
        actions = [r["action"] for r in sorted_recs]
        # high-low, high-medium, medium-low, low-high
        assert actions == ["b", "c", "d", "a"]


# ── 7.6: High RCA confidence → direct resolution actions ──


class TestHighConfidenceResolution:
    """Tests for high confidence direct resolution."""

    def test_high_confidence_direct_actions(self) -> None:
        """High RCA confidence → direct resolution actions without
        diagnostic prepend."""
        metadata = _full_pipeline_metadata()
        metadata["confidence_level"] = "high"
        metadata["confidence_percentage"] = 92
        step, *_ = _make_step(pipeline_metadata=metadata)

        result = step.execute()

        assert result.success is True
        recs = result.data["recommendations"]
        assert len(recs) >= 1
        # First recommendation should be actionable, not diagnostic
        first_action = recs[0].get("action", "").lower()
        assert "gather additional diagnostic" not in first_action


# ── 7.7: All prior step data missing → graceful fallback ──


class TestNoDataFallback:
    """Tests for no pipeline metadata fallback."""

    def test_empty_metadata_returns_generic_safe(self) -> None:
        """All prior data missing → generic safe diagnostic (7.7)."""
        step, mock_llm, _ = _make_step(pipeline_metadata={})

        result = step.execute()

        assert result.success is True
        assert result.data["synthesis_source"] == "fallback"
        assert result.data["recommendation_count"] == 1
        assert len(result.data["diagnostic_actions"]) >= 1
        # LLM should NOT be called when no data
        mock_llm.complete_sync.assert_not_called()

    def test_empty_metadata_recommendation_is_safe(self) -> None:
        """No-data recommendation has low risk and confidence."""
        step, *_ = _make_step(pipeline_metadata={})

        result = step.execute()

        rec = result.data["recommendations"][0]
        assert rec["confidence"] == "low"
        assert rec["risk_assessment"] == "low"


# ── 7.8: Partial metadata (RCA only, no KB, no signals) ──


class TestPartialMetadata:
    """Tests for partial pipeline metadata."""

    def test_rca_only_no_kb_no_signals(self) -> None:
        """RCA data only → recommendations based on RCA alone (7.8)."""
        metadata = {
            "root_cause_hypothesis": (
                "Memory leak in payment service"
            ),
            "confidence_level": "medium",
            "confidence_percentage": 60,
            "supporting_evidence": [
                "Heap usage growing linearly",
            ],
        }
        step, mock_llm, _ = _make_step(pipeline_metadata=metadata)

        result = step.execute()

        assert result.success is True
        # LLM should be called with available data
        mock_llm.complete_sync.assert_called_once()

    def test_impact_only(self) -> None:
        """Impact data only → LLM called with partial context."""
        metadata = {
            "customer_impacting": True,
            "reasoning": "Checkout failures affect revenue",
        }
        step, mock_llm, _ = _make_step(pipeline_metadata=metadata)

        result = step.execute()

        assert result.success is True
        mock_llm.complete_sync.assert_called_once()

    def test_kb_only(self) -> None:
        """KB data only → LLM called, KB resolution available."""
        metadata = {
            "recommended_resolution": "Restart payment pods",
            "exact_match_found": True,
            "exact_match_id": "inv-prev-099",
            "prior_research_summary": "Pod restart resolved issue",
        }
        step, mock_llm, _ = _make_step(pipeline_metadata=metadata)

        result = step.execute()

        assert result.success is True
        mock_llm.complete_sync.assert_called_once()


# ── 7.9: LLM failure → fallback from KB recommended_resolution ──


class TestLLMFailureFallback:
    """Tests for LLM failure fallback paths."""

    def test_llm_failure_with_kb_resolution(self) -> None:
        """LLM fails → fallback uses KB recommended_resolution
        (7.9)."""
        metadata = _full_pipeline_metadata()
        step, *_ = _make_step(
            pipeline_metadata=metadata,
            llm_error=RuntimeError("LLM unavailable"),
        )

        result = step.execute()

        assert result.success is True
        assert result.data["synthesis_source"] == "fallback"
        recs = result.data["recommendations"]
        assert len(recs) >= 1
        # KB resolution should be present
        kb_rec = recs[0]
        assert "pool" in kb_rec["action"].lower() or (
            "circuit" in kb_rec["action"].lower()
        )

    def test_llm_failure_no_kb_uses_rca(self) -> None:
        """LLM fails, no KB → fallback uses RCA hypothesis (7.9)."""
        metadata = {
            "root_cause_hypothesis": "Memory leak in API gateway",
            "confidence_level": "medium",
        }
        step, *_ = _make_step(
            pipeline_metadata=metadata,
            llm_error=RuntimeError("LLM down"),
        )

        result = step.execute()

        assert result.success is True
        assert result.data["synthesis_source"] == "fallback"
        recs = result.data["recommendations"]
        assert any(
            "memory" in r["action"].lower() for r in recs
        )

    def test_llm_failure_no_kb_no_rca(self) -> None:
        """LLM fails, no KB, no RCA → generic safe fallback."""
        metadata = {
            "customer_impacting": True,
            "reasoning": "Service is down",
        }
        step, *_ = _make_step(
            pipeline_metadata=metadata,
            llm_error=RuntimeError("LLM unreachable"),
        )

        result = step.execute()

        assert result.success is True
        assert result.data["synthesis_source"] == "fallback"
        assert len(result.data["recommendations"]) >= 1
        assert len(result.data["diagnostic_actions"]) >= 1

    def test_llm_failure_with_signals_uses_signal_detail(self) -> None:
        """LLM fails, no KB, no RCA, but signals available → signal-specific fallback."""
        metadata = {
            "customer_impacting": True,
            "reasoning": "Service is down",
            "raw_signal_detail": (
                "[data] prometheus: pg_connections → 1 series"
                " | pg_connections: latest=100, max=100"
            ),
        }
        step, *_ = _make_step(
            pipeline_metadata=metadata,
            llm_error=RuntimeError("LLM unreachable"),
        )

        result = step.execute()

        assert result.success is True
        assert result.data["synthesis_source"] == "fallback"
        recs = result.data["recommendations"]
        assert len(recs) >= 1
        # Fallback should reference actual signal data, not generic "dashboards"
        action = recs[0]["action"]
        assert "pg_connections" in action or "latest=100" in action


# ── 7.10: LLM malformed JSON → graceful fallback ──


class TestMalformedJSON:
    """Tests for malformed LLM response handling."""

    def test_malformed_json_fallback(self) -> None:
        """LLM returns malformed JSON → graceful fallback (7.10)."""
        step, *_ = _make_step(
            llm_response="This is not JSON at all {{{",
        )

        result = step.execute()

        assert result.success is True
        assert result.data["synthesis_source"] == "fallback"

    def test_empty_recommendations_array(self) -> None:
        """LLM returns empty recommendations → fallback."""
        response = json.dumps({
            "recommendations": [],
            "ranking_rationale": "",
            "diagnostic_actions": [],
        })
        step, *_ = _make_step(llm_response=response)

        result = step.execute()

        assert result.success is True
        assert result.data["synthesis_source"] == "fallback"

    def test_all_recs_fail_validation_triggers_fallback(
        self,
    ) -> None:
        """All recs fail normalization → fallback triggered."""
        response = json.dumps({
            "recommendations": [
                {"action": "", "confidence": "high"},
                {"action": "", "confidence": "medium"},
            ],
            "ranking_rationale": "",
            "diagnostic_actions": [],
        })
        step, *_ = _make_step(llm_response=response)

        result = step.execute()

        assert result.success is True
        assert result.data["synthesis_source"] == "fallback"
        assert result.data["recommendation_count"] >= 1

    def test_recommendations_not_a_list(self) -> None:
        """LLM returns recommendations as string → fallback."""
        response = json.dumps({
            "recommendations": "just a string",
            "ranking_rationale": "",
            "diagnostic_actions": [],
        })
        step, *_ = _make_step(llm_response=response)

        result = step.execute()

        assert result.success is True
        assert result.data["synthesis_source"] == "fallback"

    def test_markdown_wrapped_json_parsed(self) -> None:
        """LLM response wrapped in markdown fences is parsed."""
        inner = json.dumps({
            "recommendations": [
                {
                    "action": "Restart pods",
                    "confidence": "high",
                    "expected_outcome": "Fix issue",
                    "risk_assessment": "low",
                    "based_on_prior_incident": None,
                },
            ],
            "ranking_rationale": "Known fix",
            "diagnostic_actions": [],
        })
        response = f"```json\n{inner}\n```"
        metadata = _full_pipeline_metadata()
        metadata["confidence_level"] = "high"
        step, *_ = _make_step(
            pipeline_metadata=metadata, llm_response=response,
        )

        result = step.execute()

        assert result.success is True
        assert result.data["synthesis_source"] == "llm"


# ── 7.11: Recommendations capped at 5 ──


class TestRecommendationCap:
    """Tests for recommendation cap at 5."""

    def test_capped_at_five(self) -> None:
        """More than 5 recommendations → capped at 5 (7.11)."""
        recs = [
            {
                "action": f"Action {i}",
                "confidence": "medium",
                "expected_outcome": f"Outcome {i}",
                "risk_assessment": "low",
                "based_on_prior_incident": None,
            }
            for i in range(8)
        ]
        response = json.dumps({
            "recommendations": recs,
            "ranking_rationale": "Many options",
            "diagnostic_actions": [],
        })
        metadata = _full_pipeline_metadata()
        metadata["confidence_level"] = "high"
        step, *_ = _make_step(
            pipeline_metadata=metadata, llm_response=response,
        )

        result = step.execute()

        assert result.data["recommendation_count"] <= 5
        assert len(result.data["recommendations"]) <= 5


# ── 7.12: Ranking rationale present ──


class TestRankingRationale:
    """Tests for ranking rationale."""

    def test_rationale_present(self) -> None:
        """Ranking rationale is a non-empty string (7.12)."""
        step, *_ = _make_step()

        result = step.execute()

        assert isinstance(result.data["ranking_rationale"], str)
        assert len(result.data["ranking_rationale"]) > 0

    def test_rationale_generated_when_llm_omits(self) -> None:
        """Missing ranking_rationale → auto-generated."""
        response = json.dumps({
            "recommendations": [
                {
                    "action": "Fix it",
                    "confidence": "high",
                    "expected_outcome": "Fixed",
                    "risk_assessment": "low",
                    "based_on_prior_incident": None,
                },
            ],
            "ranking_rationale": "",
            "diagnostic_actions": [],
        })
        metadata = _full_pipeline_metadata()
        metadata["confidence_level"] = "high"
        step, *_ = _make_step(
            pipeline_metadata=metadata, llm_response=response,
        )

        result = step.execute()

        assert len(result.data["ranking_rationale"]) > 0


# ── 7.13: StepResult data includes all expected schema keys ──


class TestSchemaConsistency:
    """Tests for consistent StepResult data schema."""

    _EXPECTED_KEYS = (
        "recommendations",
        "recommendation_count",
        "ranking_rationale",
        "diagnostic_actions",
        "synthesis_source",
    )

    def test_schema_keys_present_llm_success(self) -> None:
        """All expected keys on LLM success path."""
        step, *_ = _make_step()

        result = step.execute()

        for key in self._EXPECTED_KEYS:
            assert key in result.data, f"Missing key: {key}"

    def test_schema_keys_present_llm_failure(self) -> None:
        """All expected keys on LLM failure path."""
        step, *_ = _make_step(
            llm_error=RuntimeError("fail"),
        )

        result = step.execute()

        for key in self._EXPECTED_KEYS:
            assert key in result.data, f"Missing key: {key}"

    def test_schema_keys_present_no_metadata(self) -> None:
        """All expected keys when no pipeline metadata."""
        step, *_ = _make_step(pipeline_metadata={})

        result = step.execute()

        for key in self._EXPECTED_KEYS:
            assert key in result.data, f"Missing key: {key}"

    def test_schema_keys_present_malformed_json(self) -> None:
        """All expected keys on malformed JSON fallback."""
        step, *_ = _make_step(llm_response="not json")

        result = step.execute()

        for key in self._EXPECTED_KEYS:
            assert key in result.data, f"Missing key: {key}"

    def test_recommendation_dict_schema(self) -> None:
        """Each recommendation dict has all expected fields."""
        step, *_ = _make_step()

        result = step.execute()

        rec_keys = (
            "action",
            "confidence",
            "expected_outcome",
            "risk_assessment",
            "based_on_prior_incident",
        )
        for rec in result.data["recommendations"]:
            for key in rec_keys:
                assert key in rec, f"Missing rec key: {key}"


# ── 7.14: Step name and status update message ──


class TestStepMetadata:
    """Tests for step name and status update."""

    def test_step_name(self) -> None:
        """Step has correct name (7.14)."""
        step, *_ = _make_step()
        assert step.name == "Resolution Recommendations"

    def test_status_update_sent(self) -> None:
        """Step sends status update during execution (7.14)."""
        step, _, mock_status = _make_step()

        step.execute()

        mock_status.update_message.assert_called()
        msg = mock_status.update_message.call_args[0][0]
        assert "resolution" in msg.lower() or "recommend" in msg.lower()


# ── 7.15: LLM prompt includes RCA, KB, and impact context ──


class TestPromptContent:
    """Tests verifying LLM prompt includes all evidence."""

    def test_prompt_includes_context(self) -> None:
        """LLM prompt includes condition, service, severity."""
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

    def test_prompt_includes_rca_hypothesis(self) -> None:
        """LLM prompt includes RCA hypothesis."""
        step, mock_llm, _ = _make_step()

        step.execute()

        call_args = mock_llm.complete_sync.call_args
        messages = call_args[0][0]
        user_msg = messages[1]["content"]
        assert "connection pool exhaustion" in user_msg.lower()

    def test_prompt_includes_kb_data(self) -> None:
        """LLM prompt includes KB research data."""
        step, mock_llm, _ = _make_step()

        step.execute()

        call_args = mock_llm.complete_sync.call_args
        messages = call_args[0][0]
        user_msg = messages[1]["content"]
        assert (
            "inv-prev-042" in user_msg
            or "Exact match" in user_msg
            or "DB pool exhaustion" in user_msg
        )

    def test_prompt_includes_impact_data(self) -> None:
        """LLM prompt includes customer impact."""
        step, mock_llm, _ = _make_step()

        step.execute()

        call_args = mock_llm.complete_sync.call_args
        messages = call_args[0][0]
        user_msg = messages[1]["content"]
        assert "True" in user_msg or "impacting" in user_msg.lower()

    def test_prompt_includes_signal_data(self) -> None:
        """LLM prompt includes signal correlation."""
        step, mock_llm, _ = _make_step()

        step.execute()

        call_args = mock_llm.complete_sync.call_args
        messages = call_args[0][0]
        user_msg = messages[1]["content"]
        assert "saturated" in user_msg or "5xx" in user_msg

    def test_prompt_includes_dependency_chain(self) -> None:
        """LLM prompt includes service dependency chain."""
        step, mock_llm, _ = _make_step()

        step.execute()

        call_args = mock_llm.complete_sync.call_args
        messages = call_args[0][0]
        user_msg = messages[1]["content"]
        assert "payments-db" in user_msg or "api-gateway" in user_msg

    def test_prompt_includes_raw_signal_detail(self) -> None:
        """LLM prompt includes raw metric values and log excerpts (FR19)."""
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

    def test_uses_standard_model(self) -> None:
        """Step uses standard tier via select_model."""
        step, mock_llm, _ = _make_step()

        step.execute()

        mock_llm.select_model.assert_called_once_with("standard")
        call_args = mock_llm.complete_sync.call_args
        assert call_args.kwargs.get("model") == "claude-sonnet-4"


# ── Helper function tests ──


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_parse_response_plain_json(self) -> None:
        """Parse plain JSON string."""
        raw = '{"key": "value"}'
        assert _parse_response(raw) == {"key": "value"}

    def test_parse_response_code_fence(self) -> None:
        """Parse JSON wrapped in code fences."""
        raw = '```json\n{"key": "value"}\n```'
        assert _parse_response(raw) == {"key": "value"}

    def test_normalize_level_valid(self) -> None:
        """Valid levels normalized correctly."""
        assert _normalize_level("High") == "high"
        assert _normalize_level("MEDIUM") == "medium"
        assert _normalize_level("low") == "low"

    def test_normalize_level_invalid(self) -> None:
        """Invalid values return default."""
        assert _normalize_level("invalid") == "medium"
        assert _normalize_level(42) == "medium"
        assert _normalize_level(None) == "medium"
        assert _normalize_level("invalid", "low") == "low"

    def test_normalize_level_based_on_prior_null_string(
        self,
    ) -> None:
        """Normalize 'null' string for based_on_prior_incident."""
        # This tests the normalization in _normalize_recommendations
        step, *_ = _make_step()
        raw_recs = [
            {
                "action": "Do something",
                "confidence": "high",
                "expected_outcome": "Fixed",
                "risk_assessment": "low",
                "based_on_prior_incident": "null",
            },
        ]
        result = step._normalize_recommendations(raw_recs)
        assert result[0]["based_on_prior_incident"] is None

    def test_normalize_recommendations_skips_invalid(self) -> None:
        """Non-dict and empty-action items are skipped."""
        step, *_ = _make_step()
        raw_recs: list[Any] = [
            "not a dict",
            {"action": ""},
            {"action": "Valid action", "confidence": "high"},
        ]
        result = step._normalize_recommendations(raw_recs)
        assert len(result) == 1
        assert result[0]["action"] == "Valid action"
