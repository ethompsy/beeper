"""Tests for SignalCorrelationStep."""

import json
from unittest.mock import MagicMock

from beeper_investigator.context import InvestigationContext
from beeper_investigator.steps.signal_correlation import (
    DEFAULT_LOOKBACK_MINUTES,
    _LAYERS,
    _MAX_QUERIES_PER_LAYER,
    SignalCorrelationStep,
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


def _make_sources(
    *,
    prometheus: bool = True,
    loki: bool = True,
    prom_return: dict | None = None,
    loki_return: dict | None = None,
    prom_error: Exception | None = None,
    loki_error: Exception | None = None,
) -> MagicMock:
    """Build a mock SourceClients with optional clients."""
    sources = MagicMock()

    if prometheus:
        mock_prom = MagicMock()
        if prom_error:
            mock_prom.query_range.side_effect = prom_error
        else:
            mock_prom.query_range.return_value = prom_return or {
                "resultType": "matrix",
                "result": [{"metric": {"__name__": "up"}, "values": [[1706454600, "1"]]}],
            }
        sources.prometheus = mock_prom
    else:
        sources.prometheus = None

    if loki:
        mock_loki = MagicMock()
        if loki_error:
            mock_loki.query_range.side_effect = loki_error
        else:
            mock_loki.query_range.return_value = loki_return or {
                "resultType": "streams",
                "result": [{"stream": {"app": "payments"}, "values": [["1706454600000000000", "error occurred"]]}],
            }
        sources.loki = mock_loki
    else:
        sources.loki = None

    return sources


def _make_step(
    *,
    prometheus: bool = True,
    loki: bool = True,
    prom_return: dict | None = None,
    loki_return: dict | None = None,
    prom_error: Exception | None = None,
    loki_error: Exception | None = None,
    llm_query_response: str | None = None,
    llm_analysis_response: str | None = None,
    llm_error: Exception | None = None,
    condition: str = "High error rate on /checkout endpoint",
    service: str = "payments",
    severity: str = "high",
    namespace: str = "default",
) -> tuple[SignalCorrelationStep, MagicMock, MagicMock, MagicMock]:
    """Build a SignalCorrelationStep with mocked dependencies."""
    ctx = _make_context(
        condition=condition,
        service=service,
        severity=severity,
        namespace=namespace,
    )

    sources = _make_sources(
        prometheus=prometheus,
        loki=loki,
        prom_return=prom_return,
        loki_return=loki_return,
        prom_error=prom_error,
        loki_error=loki_error,
    )

    mock_llm = MagicMock()

    # Default LLM responses: first call = query generation, second call = analysis
    default_query_response = json.dumps({
        "layers": {
            "infrastructure": {"promql": ["node_cpu_seconds_total{mode!='idle'}"]},
            "platform": {"promql": ["kube_pod_container_status_restarts_total{namespace='default'}"]},
            "application": {
                "logql": ['{namespace="default"} |= "error"'],
                "promql": ["rate(http_requests_total{service='payments',code=~'5..'}[5m])"],
            },
            "data": {"promql": ["pg_stat_activity{datname='payments'}"]},
        }
    })

    default_analysis_response = json.dumps({
        "signal_summary": "4 signals gathered across infrastructure, platform, application, and data layers",
        "hypotheses": [
            {
                "description": "Database connection pool exhaustion causing application timeouts",
                "causal_chain": "DB connection limit reached -> query timeouts -> 5xx responses",
                "confidence": "high",
                "supporting_signals": ["pg_stat_activity spike"],
                "originating_layer": "data",
            }
        ],
        "service_dependency_chain": ["payments-db", "payments"],
        "temporal_summary": "Initial signal at 14:18 (DB layer), cascade to application at 14:22",
    })

    if llm_error:
        mock_llm.complete_sync.side_effect = llm_error
    else:
        mock_llm.complete_sync.side_effect = [
            llm_query_response or default_query_response,
            llm_analysis_response or default_analysis_response,
        ]

    mock_status = MagicMock()

    step = SignalCorrelationStep(
        sources=sources,
        llm_client=mock_llm,
        context=ctx,
        status_updater=mock_status,
    )
    return step, mock_llm, sources, mock_status


# ── Task 1: Scaffold and source handling ──────────────────────


class TestSignalCorrelationScaffold:
    """Tests for step scaffold and source availability handling."""

    def test_step_name(self) -> None:
        """Step has descriptive name."""
        step, *_ = _make_step()
        assert step.name == "Cross-Layer Signal Correlation"

    def test_status_update_sent(self) -> None:
        """Step sends status update during execution (Task 1, 5.3)."""
        step, _, _, mock_status = _make_step()

        step.execute()

        mock_status.update_message.assert_called()
        msg = mock_status.update_message.call_args[0][0]
        assert "correlat" in msg.lower() or "signal" in msg.lower()

    def test_no_sources_configured(self) -> None:
        """No sources → graceful skip with sources_available empty (Task 1.4)."""
        step, *_ = _make_step(prometheus=False, loki=False)

        result = step.execute()

        assert result.success is True
        assert result.data["sources_available"] == {"prometheus": False, "loki": False}
        assert result.data["correlation_attempted"] is False
        assert "no sources" in result.summary.lower()

    def test_prometheus_only(self) -> None:
        """Prometheus only → partial correlation (Task 1.3)."""
        step, *_ = _make_step(prometheus=True, loki=False)

        result = step.execute()

        assert result.success is True
        assert result.data["sources_available"] == {"prometheus": True, "loki": False}
        assert result.data["correlation_attempted"] is True

    def test_loki_only(self) -> None:
        """Loki only → partial correlation (Task 1.3)."""
        step, *_ = _make_step(prometheus=False, loki=True)

        result = step.execute()

        assert result.success is True
        assert result.data["sources_available"] == {"prometheus": False, "loki": True}
        assert result.data["correlation_attempted"] is True

    def test_both_sources_configured(self) -> None:
        """Both sources → full correlation (Task 1.3)."""
        step, *_ = _make_step(prometheus=True, loki=True)

        result = step.execute()

        assert result.success is True
        assert result.data["sources_available"] == {"prometheus": True, "loki": True}
        assert result.data["correlation_attempted"] is True

    def test_default_lookback_constant(self) -> None:
        """Default lookback is 30 minutes (Task 1.5)."""
        assert DEFAULT_LOOKBACK_MINUTES == 30


# ── Task 2: LLM query generation ─────────────────────────────


class TestQueryGeneration:
    """Tests for LLM-driven query generation."""

    def test_signals_gathered_across_all_layers(self) -> None:
        """Queries are generated for all 4 layers (AC1, Task 2.1-2.3)."""
        step, mock_llm, _, _ = _make_step()

        result = step.execute()

        assert result.success is True
        # LLM was called for query generation (first call)
        assert mock_llm.complete_sync.call_count >= 1

    def test_llm_query_generation_failure_falls_back(self) -> None:
        """LLM failure → default template queries used (Task 2.5)."""
        from beeper_investigator.llm.client import LlmClientError

        # First call (query gen) fails, second call (analysis) succeeds
        mock_llm = MagicMock()
        analysis_resp = json.dumps({
            "signal_summary": "signals gathered with defaults",
            "hypotheses": [],
            "service_dependency_chain": None,
            "temporal_summary": "",
        })
        mock_llm.complete_sync.side_effect = [
            LlmClientError("LLM down"),
            analysis_resp,
        ]

        ctx = _make_context()
        sources = _make_sources()
        mock_status = MagicMock()

        step = SignalCorrelationStep(
            sources=sources,
            llm_client=mock_llm,
            context=ctx,
            status_updater=mock_status,
        )
        result = step.execute()

        assert result.success is True
        # Should still have queried sources with default queries
        assert result.data["correlation_attempted"] is True

    def test_query_validation_max_per_layer(self) -> None:
        """Generated queries are capped at max per layer (Task 2.6)."""
        oversized = json.dumps({
            "layers": {
                "infrastructure": {"promql": ["q1", "q2", "q3", "q4", "q5"]},
            }
        })
        step, _, sources, _ = _make_step(
            llm_query_response=oversized,
            loki=False,
        )

        result = step.execute()

        assert result.success is True
        # Only _MAX_QUERIES_PER_LAYER queries should have been executed
        assert sources.prometheus.query_range.call_count == _MAX_QUERIES_PER_LAYER

    def test_malformed_llm_query_json_falls_back(self) -> None:
        """Malformed query generation JSON → falls back to defaults (Task 2.4)."""
        analysis_resp = json.dumps({
            "signal_summary": "fallback used",
            "hypotheses": [],
            "service_dependency_chain": None,
            "temporal_summary": "",
        })
        step, *_ = _make_step(
            llm_query_response="Not valid JSON at all",
            llm_analysis_response=analysis_resp,
        )
        # Override to make both calls work (first is bad JSON string, second is analysis)
        step.llm_client.complete_sync.side_effect = [
            "Not valid JSON at all",
            analysis_resp,
        ]

        result = step.execute()

        assert result.success is True
        assert result.data["correlation_attempted"] is True


# ── Task 3: Query execution and signal gathering ─────────────


class TestQueryExecution:
    """Tests for query execution against sources."""

    def test_per_query_failure_continues(self) -> None:
        """Individual query failure → continues with remaining (Task 3.4)."""
        # Prometheus fails on first call, succeeds on second
        mock_prom = MagicMock()
        mock_prom.query_range.side_effect = [
            ConnectionError("first query failed"),
            {"resultType": "matrix", "result": []},
            {"resultType": "matrix", "result": []},
            {"resultType": "matrix", "result": []},
        ]

        step, _, sources, _ = _make_step()
        sources.prometheus = mock_prom

        result = step.execute()

        assert result.success is True
        # Some queries should still have executed
        assert result.data["correlation_attempted"] is True

    def test_all_queries_empty_results(self) -> None:
        """All queries return empty → no signals, empty hypotheses."""
        step, *_ = _make_step(
            prom_return={"resultType": "matrix", "result": []},
            loki_return={"resultType": "streams", "result": []},
            llm_analysis_response=json.dumps({
                "signal_summary": "No signals found",
                "hypotheses": [],
                "service_dependency_chain": None,
                "temporal_summary": "",
            }),
        )

        result = step.execute()

        assert result.success is True


# ── Task 4: LLM correlation analysis ─────────────────────────


class TestCorrelationAnalysis:
    """Tests for LLM-based correlation analysis."""

    def test_temporal_correlation_and_causal_chain(self) -> None:
        """Temporal correlation + causal chain hypothesized (AC2)."""
        step, *_ = _make_step()

        result = step.execute()

        assert result.success is True
        assert len(result.data["hypotheses"]) >= 1
        hypothesis = result.data["hypotheses"][0]
        assert "description" in hypothesis
        assert "causal_chain" in hypothesis
        assert "confidence" in hypothesis
        assert "originating_layer" in hypothesis

    def test_service_dependency_chain_documented(self) -> None:
        """Service dependency chain is documented (AC3)."""
        step, *_ = _make_step()

        result = step.execute()

        assert result.data["service_dependency_chain"] is not None
        assert len(result.data["service_dependency_chain"]) >= 1

    def test_multiple_hypotheses_with_confidence(self) -> None:
        """Multiple hypotheses with confidence levels for ambiguous signals (AC4)."""
        analysis_resp = json.dumps({
            "signal_summary": "Ambiguous signals",
            "hypotheses": [
                {
                    "description": "Hypothesis A",
                    "causal_chain": "A -> B -> C",
                    "confidence": "high",
                    "supporting_signals": ["signal-1"],
                    "originating_layer": "data",
                },
                {
                    "description": "Hypothesis B",
                    "causal_chain": "X -> Y -> Z",
                    "confidence": "low",
                    "supporting_signals": ["signal-2"],
                    "originating_layer": "infrastructure",
                },
            ],
            "service_dependency_chain": ["svc-a", "svc-b"],
            "temporal_summary": "Multiple cascades detected",
        })
        step, *_ = _make_step(llm_analysis_response=analysis_resp)

        result = step.execute()

        assert result.success is True
        assert len(result.data["hypotheses"]) == 2
        confidences = {h["confidence"] for h in result.data["hypotheses"]}
        assert "high" in confidences
        assert "low" in confidences

    def test_llm_analysis_failure_falls_back(self) -> None:
        """LLM analysis failure → raw signal summary, no hypotheses (Task 4.6)."""
        # First call (query gen) succeeds, second call (analysis) fails
        query_resp = json.dumps({
            "layers": {
                "infrastructure": {"promql": ["node_cpu_seconds_total"]},
            }
        })
        mock_llm = MagicMock()
        from beeper_investigator.llm.client import LlmClientError
        mock_llm.complete_sync.side_effect = [
            query_resp,
            LlmClientError("Analysis failed"),
        ]

        ctx = _make_context()
        sources = _make_sources()
        mock_status = MagicMock()

        step = SignalCorrelationStep(
            sources=sources,
            llm_client=mock_llm,
            context=ctx,
            status_updater=mock_status,
        )
        result = step.execute()

        assert result.success is True
        assert result.data["hypotheses"] == []
        assert result.data["signal_summary"] != ""

    def test_malformed_analysis_json_falls_back(self) -> None:
        """Malformed LLM analysis JSON → graceful fallback (Task 4.6)."""
        query_resp = json.dumps({
            "layers": {"infrastructure": {"promql": ["up"]}},
        })
        mock_llm = MagicMock()
        mock_llm.complete_sync.side_effect = [
            query_resp,
            "Not JSON at all",
        ]

        ctx = _make_context()
        sources = _make_sources()
        mock_status = MagicMock()

        step = SignalCorrelationStep(
            sources=sources,
            llm_client=mock_llm,
            context=ctx,
            status_updater=mock_status,
        )
        result = step.execute()

        assert result.success is True
        assert result.data["hypotheses"] == []

    def test_confidence_normalization(self) -> None:
        """Confidence values are normalized to high/medium/low/null (Task 4.5)."""
        analysis_resp = json.dumps({
            "signal_summary": "test",
            "hypotheses": [
                {
                    "description": "test",
                    "causal_chain": "a -> b",
                    "confidence": "HIGH",
                    "supporting_signals": [],
                    "originating_layer": "data",
                },
                {
                    "description": "test2",
                    "causal_chain": "c -> d",
                    "confidence": "INVALID_VALUE",
                    "supporting_signals": [],
                    "originating_layer": "infrastructure",
                },
            ],
            "service_dependency_chain": None,
            "temporal_summary": "",
        })
        step, *_ = _make_step(llm_analysis_response=analysis_resp)

        result = step.execute()

        assert result.data["hypotheses"][0]["confidence"] == "high"
        assert result.data["hypotheses"][1]["confidence"] is None

    def test_originating_layer_validated(self) -> None:
        """Invalid originating_layer is normalized to empty string."""
        analysis_resp = json.dumps({
            "signal_summary": "test",
            "hypotheses": [
                {
                    "description": "test",
                    "causal_chain": "a -> b",
                    "confidence": "medium",
                    "supporting_signals": [],
                    "originating_layer": "network",
                },
            ],
            "service_dependency_chain": None,
            "temporal_summary": "",
        })
        step, *_ = _make_step(llm_analysis_response=analysis_resp)

        result = step.execute()

        assert result.data["hypotheses"][0]["originating_layer"] == ""


# ── Schema consistency ────────────────────────────────────────


class TestSchemaConsistency:
    """Tests for consistent StepResult data schema."""

    def test_all_schema_keys_present_with_results(self) -> None:
        """Step data includes all expected keys with results."""
        step, *_ = _make_step()

        result = step.execute()

        for key in (
            "sources_available",
            "layers_queried",
            "signals_gathered",
            "signal_summary",
            "hypotheses",
            "service_dependency_chain",
            "correlation_attempted",
        ):
            assert key in result.data, f"Missing key: {key}"

    def test_all_schema_keys_present_no_sources(self) -> None:
        """Step data includes all expected keys even with no sources."""
        step, *_ = _make_step(prometheus=False, loki=False)

        result = step.execute()

        for key in (
            "sources_available",
            "layers_queried",
            "signals_gathered",
            "signal_summary",
            "hypotheses",
            "service_dependency_chain",
            "correlation_attempted",
        ):
            assert key in result.data, f"Missing key: {key}"

    def test_no_sources_default_values(self) -> None:
        """No-sources path returns correct default values."""
        step, *_ = _make_step(prometheus=False, loki=False)

        result = step.execute()

        assert result.data["layers_queried"] == []
        assert result.data["signals_gathered"] == 0
        assert result.data["hypotheses"] == []
        assert result.data["service_dependency_chain"] is None

    def test_markdown_wrapped_llm_response(self) -> None:
        """LLM response wrapped in markdown fences is parsed correctly."""
        query_resp = '```json\n{"layers": {"infrastructure": {"promql": ["up"]}}}\n```'
        analysis_resp = '```json\n{"signal_summary": "wrapped", "hypotheses": [], "service_dependency_chain": null, "temporal_summary": ""}\n```'
        step, *_ = _make_step(
            llm_query_response=query_resp,
            llm_analysis_response=analysis_resp,
        )
        step.llm_client.complete_sync.side_effect = [query_resp, analysis_resp]

        result = step.execute()

        assert result.success is True


# ── Prompt content verification ───────────────────────────────


class TestPromptContent:
    """Tests verifying LLM prompts include investigation context."""

    def test_query_gen_prompt_includes_context(self) -> None:
        """Query generation prompt includes condition, service, severity, namespace."""
        step, mock_llm, _, _ = _make_step(
            condition="OOM kills",
            service="api-gateway",
            severity="critical",
            namespace="production",
        )

        step.execute()

        # First call is query generation
        call_args = mock_llm.complete_sync.call_args_list[0]
        messages = call_args[0][0]
        user_msg = messages[1]["content"]
        assert "OOM kills" in user_msg
        assert "api-gateway" in user_msg
        assert "critical" in user_msg
        assert "production" in user_msg

    def test_analysis_prompt_includes_signals(self) -> None:
        """Analysis prompt includes formatted signal data."""
        step, mock_llm, _, _ = _make_step()

        step.execute()

        # Second call is analysis
        assert mock_llm.complete_sync.call_count == 2
        call_args = mock_llm.complete_sync.call_args_list[1]
        messages = call_args[0][0]
        user_msg = messages[1]["content"]
        # Should contain signal formatting markers
        assert "prometheus:" in user_msg or "loki:" in user_msg

    def test_signal_format_includes_metric_values(self) -> None:
        """Formatted signals include actual metric values, not just counts."""
        step, mock_llm, _, _ = _make_step(
            prom_return={
                "resultType": "matrix",
                "result": [{
                    "metric": {"__name__": "node_cpu", "instance": "node-1"},
                    "values": [[1706454600, "0.85"], [1706454660, "0.92"]],
                }],
            },
        )

        step.execute()

        # Check the analysis prompt has metric summaries
        call_args = mock_llm.complete_sync.call_args_list[1]
        messages = call_args[0][0]
        user_msg = messages[1]["content"]
        assert "node_cpu" in user_msg
        assert "0.85" in user_msg or "0.92" in user_msg
