"""Cross-layer signal correlation investigation step.

Queries Prometheus and Loki across architectural layers (infrastructure,
platform, application, data) and uses LLM to correlate signals and
generate root-cause hypotheses (FR4, AC1-AC4).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.steps import StepResult

if TYPE_CHECKING:
    from beeper_investigator.agent import SourceClients

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_MINUTES = 30
_MAX_QUERIES_PER_LAYER = 3
_MAX_SIGNALS_FOR_LLM = 50

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)

_LAYERS = ("infrastructure", "platform", "application", "data")

# ── Default template queries (fallback when LLM fails) ────────

_DEFAULT_QUERIES: dict[str, dict[str, list[str]]] = {
    "infrastructure": {
        "promql": [
            'node_cpu_seconds_total{mode!="idle"}',
            "node_memory_MemAvailable_bytes",
        ],
    },
    "platform": {
        "promql": [
            'kube_pod_container_status_restarts_total{namespace="{namespace}"}',
            'kube_deployment_status_replicas_available{namespace="{namespace}"}',
        ],
    },
    "application": {
        "logql": [
            '{namespace="{namespace}"} |= "error"',
        ],
    },
    "data": {
        "promql": [
            "up",
        ],
    },
}

# ── LLM prompts ───────────────────────────────────────────────

_QUERY_GEN_SYSTEM_PROMPT = """\
You are an SRE signal correlation assistant. Given an investigation context, \
generate PromQL and LogQL queries to gather signals across 4 architectural layers:

1. **infrastructure**: Node-level metrics (CPU, memory, disk, network)
2. **platform**: Kubernetes metrics (pod restarts, deployment replicas, service health)
3. **application**: Service-level metrics and logs (error rates, latency, log patterns)
4. **data**: Database/storage metrics (connections, query times, replication lag)

Respond with ONLY a JSON object:
{"layers": {"infrastructure": {"promql": [...]}, "platform": {"promql": [...]}, \
"application": {"logql": [...], "promql": [...]}, "data": {"promql": [...]}}}

Rules:
- Use promql for Prometheus queries and logql for Loki queries
- Max 3 queries per layer
- Tailor queries to the service and condition described
- Use namespace labels where appropriate
- Omit a layer key if no relevant queries exist for it"""

_QUERY_GEN_USER_TEMPLATE = """\
Investigation context:
Condition: {condition}
Service: {service}
Severity: {severity}
Namespace: {namespace}

Available sources: {available_sources}"""

_ANALYSIS_SYSTEM_PROMPT = """\
You are an SRE root-cause analyst. Given gathered signals from multiple \
architectural layers, perform temporal correlation and causal chain analysis.

Respond with ONLY a JSON object:
{"signal_summary": "brief text summary of all signals", \
"hypotheses": [{"description": "what happened", "causal_chain": "A -> B -> C", \
"confidence": "high"|"medium"|"low", "supporting_signals": ["signal descriptions"], \
"originating_layer": "infrastructure"|"platform"|"application"|"data"}], \
"service_dependency_chain": ["service-a", "service-b"] or null, \
"temporal_summary": "timeline of events"}

Rules:
- Generate 1-3 hypotheses ranked by confidence
- high: Strong signal correlation with clear causal chain
- medium: Partial correlation, plausible chain
- low: Weak correlation, speculative
- Identify the originating layer where the issue likely started
- Document the service dependency chain if signals span services"""

_ANALYSIS_USER_TEMPLATE = """\
Investigation context:
Condition: {condition}
Service: {service}
Severity: {severity}

Gathered signals:
{formatted_signals}

{prior_research}"""


def _parse_response(raw: str) -> dict[str, Any]:
    """Parse LLM response, stripping markdown fences if present."""
    match = _CODE_FENCE_RE.search(raw)
    text = match.group(1) if match else raw
    result: dict[str, Any] = json.loads(text.strip())
    return result


def _resolve_default_queries(namespace: str) -> dict[str, dict[str, list[str]]]:
    """Resolve placeholder variables in default template queries.

    Uses str.replace rather than str.format to avoid conflicts with
    PromQL/LogQL curly braces.
    """
    resolved: dict[str, dict[str, list[str]]] = {}
    for layer, sources in _DEFAULT_QUERIES.items():
        resolved[layer] = {}
        for source_type, queries in sources.items():
            resolved[layer][source_type] = [
                q.replace("{namespace}", namespace) for q in queries
            ]
    return resolved


class SignalCorrelationStep:
    """Correlate signals across architectural layers.

    Two-phase LLM approach:
    1. Generate PromQL/LogQL queries for each architectural layer
    2. Analyze gathered signals for temporal correlation and causal chains
    """

    name: str = "Cross-Layer Signal Correlation"

    def __init__(
        self,
        sources: SourceClients,
        llm_client: LlmClient,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
    ) -> None:
        self.sources = sources
        self.llm_client = llm_client
        self.context = context
        self.status_updater = status_updater

    def execute(self) -> StepResult:
        """Run the cross-layer signal correlation step."""
        self.status_updater.update_message("Correlating signals across architectural layers")
        logger.info(
            "Starting signal correlation for service=%s condition=%s",
            self.context.service,
            self.context.condition,
        )

        has_prometheus = self.sources.prometheus is not None
        has_loki = self.sources.loki is not None
        sources_available = {"prometheus": has_prometheus, "loki": has_loki}

        # No sources → skip entirely
        if not has_prometheus and not has_loki:
            logger.info("No sources configured; skipping signal correlation")
            return StepResult(
                success=True,
                summary="Signal correlation skipped: no sources configured",
                data={
                    "sources_available": sources_available,
                    "layers_queried": [],
                    "signals_gathered": 0,
                    "signal_summary": "",
                    "hypotheses": [],
                    "service_dependency_chain": None,
                    "correlation_attempted": False,
                },
            )

        # Compute time window
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=DEFAULT_LOOKBACK_MINUTES)

        prom_start = start.isoformat()
        prom_end = now.isoformat()
        loki_start = str(int(start.timestamp() * 1_000_000_000))
        loki_end = str(int(now.timestamp() * 1_000_000_000))

        # Phase 1: Generate queries
        layer_queries = self._generate_queries(has_prometheus, has_loki)

        # Phase 2: Execute queries and gather signals
        signals = self._execute_queries(
            layer_queries,
            has_prometheus,
            has_loki,
            prom_start,
            prom_end,
            loki_start,
            loki_end,
        )

        layers_queried = sorted({s["layer"] for s in signals})

        # Phase 3: Analyze signals with LLM
        analysis = self._analyze_signals(signals)

        total = len(signals)
        summary_parts = [
            f"Gathered {total} signals across {len(layers_queried)} layers"
            f" for service '{self.context.service}'"
        ]
        if analysis.get("hypotheses"):
            summary_parts.append(
                f"{len(analysis['hypotheses'])} hypotheses generated"
            )

        return StepResult(
            success=True,
            summary="; ".join(summary_parts),
            data={
                "sources_available": sources_available,
                "layers_queried": layers_queried,
                "signals_gathered": total,
                "signal_summary": analysis.get("signal_summary", ""),
                "hypotheses": analysis.get("hypotheses", []),
                "service_dependency_chain": analysis.get("service_dependency_chain"),
                "correlation_attempted": True,
            },
        )

    # ── Phase 1: Query generation ─────────────────────────────

    def _generate_queries(
        self,
        has_prometheus: bool,
        has_loki: bool,
    ) -> dict[str, dict[str, list[str]]]:
        """Use LLM to generate queries, falling back to defaults."""
        available = []
        if has_prometheus:
            available.append("Prometheus (PromQL)")
        if has_loki:
            available.append("Loki (LogQL)")

        messages = [
            {"role": "system", "content": _QUERY_GEN_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _QUERY_GEN_USER_TEMPLATE.format(
                    condition=self.context.condition,
                    service=self.context.service,
                    severity=self.context.severity,
                    namespace=self.context.namespace,
                    available_sources=", ".join(available),
                ),
            },
        ]

        try:
            raw = self.llm_client.complete_sync(
                messages,
                max_tokens=512,
                temperature=0.0,
            )
            return self._parse_queries(raw, has_prometheus, has_loki)
        except Exception as exc:
            logger.warning("LLM query generation failed: %s; using defaults", exc)
            return self._default_queries(has_prometheus, has_loki)

    def _parse_queries(
        self,
        raw: str,
        has_prometheus: bool,
        has_loki: bool,
    ) -> dict[str, dict[str, list[str]]]:
        """Parse and validate LLM query response."""
        try:
            parsed = _parse_response(raw)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse LLM query response; using defaults")
            return self._default_queries(has_prometheus, has_loki)

        layers_data = parsed.get("layers", {})
        if not isinstance(layers_data, dict):
            return self._default_queries(has_prometheus, has_loki)

        result: dict[str, dict[str, list[str]]] = {}
        for layer in _LAYERS:
            layer_data = layers_data.get(layer, {})
            if not isinstance(layer_data, dict):
                continue

            result[layer] = {}
            for source_type in ("promql", "logql"):
                queries = layer_data.get(source_type, [])
                if not isinstance(queries, list):
                    continue
                # Filter empty strings and cap at max
                valid = [q for q in queries if isinstance(q, str) and q.strip()]
                result[layer][source_type] = valid[:_MAX_QUERIES_PER_LAYER]

            # Remove source types not available
            if not has_prometheus:
                result[layer].pop("promql", None)
            if not has_loki:
                result[layer].pop("logql", None)

            # Remove empty layers
            if not any(result[layer].values()):
                del result[layer]

        return result if result else self._default_queries(has_prometheus, has_loki)

    def _default_queries(
        self,
        has_prometheus: bool,
        has_loki: bool,
    ) -> dict[str, dict[str, list[str]]]:
        """Return default template queries filtered by available sources."""
        resolved = _resolve_default_queries(self.context.namespace)
        result: dict[str, dict[str, list[str]]] = {}

        for layer, sources in resolved.items():
            filtered: dict[str, list[str]] = {}
            if has_prometheus and "promql" in sources:
                filtered["promql"] = sources["promql"]
            if has_loki and "logql" in sources:
                filtered["logql"] = sources["logql"]
            if filtered:
                result[layer] = filtered

        return result

    # ── Phase 2: Query execution ──────────────────────────────

    def _execute_queries(
        self,
        layer_queries: dict[str, dict[str, list[str]]],
        has_prometheus: bool,
        has_loki: bool,
        prom_start: str,
        prom_end: str,
        loki_start: str,
        loki_end: str,
    ) -> list[dict[str, Any]]:
        """Execute queries against sources and gather signals."""
        signals: list[dict[str, Any]] = []

        for layer, sources in layer_queries.items():
            # Execute PromQL queries
            if has_prometheus:
                for query in sources.get("promql", []):
                    signal = self._execute_promql(
                        query, layer, prom_start, prom_end
                    )
                    signals.append(signal)

            # Execute LogQL queries
            if has_loki:
                for query in sources.get("logql", []):
                    signal = self._execute_logql(
                        query, layer, loki_start, loki_end
                    )
                    signals.append(signal)

        return signals[:_MAX_SIGNALS_FOR_LLM]

    def _execute_promql(
        self,
        query: str,
        layer: str,
        start: str,
        end: str,
    ) -> dict[str, Any]:
        """Execute a single PromQL query, returning a signal dict."""
        assert self.sources.prometheus is not None
        try:
            data = self.sources.prometheus.query_range(
                promql=query, start=start, end=end
            )
            return {
                "layer": layer,
                "source": "prometheus",
                "query": query,
                "data": data,
                "error": None,
            }
        except Exception as exc:
            logger.warning("PromQL query failed: %s — %s", query, exc)
            return {
                "layer": layer,
                "source": "prometheus",
                "query": query,
                "data": None,
                "error": str(exc),
            }

    def _execute_logql(
        self,
        query: str,
        layer: str,
        start: str,
        end: str,
    ) -> dict[str, Any]:
        """Execute a single LogQL query, returning a signal dict."""
        assert self.sources.loki is not None
        try:
            data = self.sources.loki.query_range(
                logql=query, start=start, end=end
            )
            return {
                "layer": layer,
                "source": "loki",
                "query": query,
                "data": data,
                "error": None,
            }
        except Exception as exc:
            logger.warning("LogQL query failed: %s — %s", query, exc)
            return {
                "layer": layer,
                "source": "loki",
                "query": query,
                "data": None,
                "error": str(exc),
            }

    # ── Phase 3: Correlation analysis ─────────────────────────

    def _analyze_signals(
        self,
        signals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Use LLM to correlate signals and generate hypotheses."""
        if not signals:
            return self._empty_analysis()

        # Filter to signals with actual data
        successful = [s for s in signals if s["data"] is not None]
        if not successful:
            return {
                "signal_summary": f"{len(signals)} queries executed but all returned errors",
                "hypotheses": [],
                "service_dependency_chain": None,
                "temporal_summary": "",
            }

        formatted = self._format_signals(successful)

        # Include prior research from pipeline metadata if available
        prior_research = ""

        messages = [
            {"role": "system", "content": _ANALYSIS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _ANALYSIS_USER_TEMPLATE.format(
                    condition=self.context.condition,
                    service=self.context.service,
                    severity=self.context.severity,
                    formatted_signals=formatted,
                    prior_research=prior_research,
                ),
            },
        ]

        try:
            raw = self.llm_client.complete_sync(
                messages,
                max_tokens=1024,
                temperature=0.0,
            )
            return self._parse_analysis(raw, successful)
        except Exception as exc:
            logger.warning("LLM correlation analysis failed: %s", exc)
            return self._fallback_analysis(successful)

    def _parse_analysis(
        self,
        raw: str,
        signals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Parse the LLM analysis response."""
        try:
            parsed = _parse_response(raw)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse LLM analysis response")
            return self._fallback_analysis(signals)

        # Normalize hypotheses
        hypotheses = parsed.get("hypotheses", [])
        if not isinstance(hypotheses, list):
            hypotheses = []

        normalized: list[dict[str, Any]] = []
        for h in hypotheses:
            if not isinstance(h, dict):
                continue
            confidence = h.get("confidence")
            if isinstance(confidence, str):
                confidence = confidence.lower()
            if confidence not in ("high", "medium", "low"):
                confidence = None

            originating_layer = h.get("originating_layer", "")
            if originating_layer not in _LAYERS:
                originating_layer = ""

            normalized.append({
                "description": h.get("description", ""),
                "causal_chain": h.get("causal_chain", ""),
                "confidence": confidence,
                "supporting_signals": h.get("supporting_signals", []),
                "originating_layer": originating_layer,
            })

        chain = parsed.get("service_dependency_chain")
        if not isinstance(chain, list):
            chain = None

        return {
            "signal_summary": parsed.get("signal_summary", ""),
            "hypotheses": normalized,
            "service_dependency_chain": chain,
            "temporal_summary": parsed.get("temporal_summary", ""),
        }

    def _fallback_analysis(
        self,
        signals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build analysis from raw signals when LLM fails."""
        layers = sorted({s["layer"] for s in signals})
        summary = (
            f"{len(signals)} signals gathered from {', '.join(layers)} layers"
            " (LLM analysis unavailable)"
        )
        return {
            "signal_summary": summary,
            "hypotheses": [],
            "service_dependency_chain": None,
            "temporal_summary": "",
        }

    def _empty_analysis(self) -> dict[str, Any]:
        """Return empty analysis when no signals exist."""
        return {
            "signal_summary": "",
            "hypotheses": [],
            "service_dependency_chain": None,
            "temporal_summary": "",
        }

    def _format_signals(self, signals: list[dict[str, Any]]) -> str:
        """Format signals as structured text for LLM prompt.

        Summarizes metric values and timestamps rather than dumping raw JSON,
        giving the LLM enough context for temporal correlation.
        """
        lines: list[str] = []
        for s in signals[:_MAX_SIGNALS_FOR_LLM]:
            layer = s["layer"]
            source = s["source"]
            query = s["query"]
            data = s.get("data", {})

            result_items = data.get("result", []) if isinstance(data, dict) else []
            count = len(result_items)

            if source == "prometheus":
                detail = self._summarize_prometheus(result_items)
                lines.append(f"[{layer}] prometheus: {query} → {count} series{detail}")
            elif source == "loki":
                detail = self._summarize_loki(result_items)
                lines.append(f"[{layer}] loki: {query} → {count} streams{detail}")

        return "\n".join(lines) if lines else "(no signals gathered)"

    @staticmethod
    def _summarize_prometheus(results: list[dict[str, Any]]) -> str:
        """Extract key values from Prometheus matrix results."""
        if not results:
            return " (empty)"
        parts: list[str] = []
        for series in results[:3]:
            metric = series.get("metric", {})
            values = series.get("values", [])
            name = metric.get("__name__", "")
            labels = {k: v for k, v in metric.items() if k != "__name__"}
            label_str = f"{{{', '.join(f'{k}={v}' for k, v in labels.items())}}}" if labels else ""
            if values:
                nums = [float(v[1]) for v in values if len(v) >= 2]
                if nums:
                    parts.append(
                        f"{name}{label_str}: latest={nums[-1]:.2g}, "
                        f"min={min(nums):.2g}, max={max(nums):.2g}, "
                        f"points={len(nums)}"
                    )
        if parts:
            return " | " + "; ".join(parts)
        return ""

    @staticmethod
    def _summarize_loki(results: list[dict[str, Any]]) -> str:
        """Extract key info from Loki stream results."""
        if not results:
            return " (empty)"
        total_entries = 0
        sample_lines: list[str] = []
        for stream in results[:3]:
            entries = stream.get("values", [])
            total_entries += len(entries)
            for ts, line in entries[:2]:
                truncated = line[:120] + "..." if len(line) > 120 else line
                sample_lines.append(truncated)
        detail = f" | {total_entries} log entries"
        if sample_lines:
            detail += f", samples: {sample_lines[:3]}"
        return detail
