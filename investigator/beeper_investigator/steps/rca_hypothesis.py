"""RCA hypothesis generation investigation step.

Synthesizes findings from all prior investigation steps — customer impact,
KB prior research, and signal correlation — into a definitive root cause
hypothesis with confidence level (FR7, FR44).
"""

import json
import logging
from typing import Any

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.llm.response_parser import parse_json_response
from beeper_investigator.steps import StepResult

logger = logging.getLogger(__name__)

_RCA_SYSTEM_PROMPT = """\
You are a senior SRE performing deep root-cause analysis. Synthesize ALL \
available evidence — customer impact, prior incidents from the knowledge base, \
and correlated signals — into a definitive root cause hypothesis.

Respond with ONLY a JSON object:
{"root_cause_hypothesis": "clear description of the root cause", \
"confidence_level": "high"|"medium"|"low", \
"confidence_percentage": 85, \
"supporting_evidence": ["evidence item 1", "evidence item 2"], \
"alternative_hypotheses": [{"description": "alt hypothesis", "confidence_percentage": 30}], \
"additional_data_needs": ["what else would help if uncertain"], \
"kb_citation": "prior incident ID if applicable or null"}

Rules:
- high confidence (>80%): Strong correlation + clear causal chain
- high confidence may also be confirmed by KB
- medium confidence (50-80%): Partial correlation, plausible but not confirmed
- low confidence (<50%): Weak/conflicting signals, speculative hypothesis
- ALWAYS provide alternative_hypotheses when confidence < high
- ALWAYS provide additional_data_needs when confidence is low
- If a known KB match exists, cite it and boost confidence appropriately
- confidence_percentage must be an integer 0-100
- Reference specific metric values and log excerpts from the raw signal data \
in your hypothesis and supporting_evidence (e.g., "error rate spiked to 34%", \
"latency p99 reached 2.3s", "log shows 'connection refused to db-primary'")
- If SLO breach data is provided, reference the specific target, current \
compliance, and burn rate in your hypothesis (e.g., "availability SLO at \
97.2% vs 99.9% target, burn rate 28x indicates severe customer impact")"""

_RCA_USER_TEMPLATE = """\
Investigation context:
Condition: {condition}
Service: {service}
Severity: {severity}

Customer impact: {impact_summary}

Prior KB research:
{kb_summary}

Signal correlation findings:
{signal_summary}

Raw signal data (metric values and log excerpts):
{raw_signal_detail}

Temporal sequence of events:
{temporal_summary}

Signal correlation hypotheses:
{correlation_hypotheses}

SLO breach context:
{slo_context}"""


def _parse_response(raw: str) -> dict[str, Any]:
    """Parse LLM response, stripping thinking tokens and markdown fences."""
    return parse_json_response(raw)


def _validate_confidence(
    level: str, percentage: int | None
) -> tuple[str, int | None]:
    """Validate and correct confidence level/percentage alignment.

    If percentage is provided, the level is overridden to match the band:
    - >80%: high
    - 50-80%: medium
    - <50%: low
    """
    if percentage is not None:
        if percentage > 80:
            level = "high"
        elif percentage >= 50:
            level = "medium"
        else:
            level = "low"
    return level, percentage


class RCAHypothesisStep:
    """Generate a root cause hypothesis from all prior investigation evidence.

    Synthesizes customer impact, KB prior research, and signal correlation
    findings into a single hypothesis with confidence level.
    """

    name: str = "RCA Hypothesis Generation"

    def __init__(
        self,
        llm_client: LlmClient,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
        pipeline_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.context = context
        self.status_updater = status_updater
        self.pipeline_metadata = pipeline_metadata if pipeline_metadata is not None else {}

    def execute(self) -> StepResult:
        """Run the RCA hypothesis generation step."""
        self.status_updater.update_message("Generating root cause hypothesis")
        logger.info(
            "Generating RCA hypothesis for service=%s condition=%s",
            self.context.service,
            self.context.condition,
        )

        # Extract prior step data from pipeline metadata
        impact_data = self._extract_impact_data()
        kb_data = self._extract_kb_data()
        signal_data = self._extract_signal_data()
        slo_data = self._extract_slo_data()

        # Check if we have any useful data at all
        has_impact = impact_data.get("customer_impacting") is not None
        has_kb = bool(kb_data.get("prior_research_summary"))
        has_signals = (
            bool(signal_data.get("signal_summary"))
            or bool(signal_data.get("hypotheses"))
        )

        if not has_impact and not has_kb and not has_signals:
            logger.info("No pipeline metadata available; returning insufficient data")
            return self._insufficient_data_result()

        # Build and call LLM
        impact_summary = self._format_impact(impact_data)
        kb_summary = self._format_kb(kb_data)
        signal_summary = signal_data.get("signal_summary", "No signal data available")
        raw_signal_detail = signal_data.get(
            "raw_signal_detail", "No raw signal data available"
        ) or "No raw signal data available"
        temporal_summary = signal_data.get(
            "temporal_summary", "No temporal data available"
        ) or "No temporal data available"
        correlation_hypotheses = self._format_hypotheses(
            signal_data.get("hypotheses", [])
        )
        slo_context = self._format_slo_context(slo_data)

        messages = [
            {"role": "system", "content": _RCA_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _RCA_USER_TEMPLATE.format(
                    condition=self.context.condition,
                    service=self.context.service,
                    severity=self.context.severity,
                    impact_summary=impact_summary,
                    kb_summary=kb_summary,
                    signal_summary=signal_summary,
                    raw_signal_detail=raw_signal_detail,
                    temporal_summary=temporal_summary,
                    correlation_hypotheses=correlation_hypotheses,
                    slo_context=slo_context,
                ),
            },
        ]

        model_name = self.llm_client.select_model("deep_rca")
        logger.info("Escalating to deep RCA model for hypothesis generation")

        try:
            # This is the one genuinely reasoning-heavy step: keep the model's
            # <think> reasoning ON even when the rest of the pipeline disables it
            # (qwen3 /no_think), since the root-cause hypothesis is the highest-
            # value output. It is correspondingly the slowest call on a local
            # reasoning model, so give it generous per-call timeout headroom.
            raw = self.llm_client.complete_sync(
                messages,
                max_tokens=4096,
                temperature=0.0,
                model=model_name,
                keep_thinking=True,
                timeout=1200,
            )
        except Exception as exc:
            logger.warning("LLM RCA synthesis failed: %s", exc)
            return self._fallback_result(signal_data, kb_data, model_name)

        return self._parse_result(raw, signal_data, kb_data, model_name)

    # ── Pipeline metadata extraction ─────────────────────────

    def _extract_impact_data(self) -> dict[str, Any]:
        """Extract customer impact data from pipeline metadata."""
        return {
            "customer_impacting": self.pipeline_metadata.get("customer_impacting"),
            "reasoning": self.pipeline_metadata.get("reasoning", ""),
        }

    def _extract_kb_data(self) -> dict[str, Any]:
        """Extract KB query data from pipeline metadata."""
        return {
            "prior_research_summary": self.pipeline_metadata.get(
                "prior_research_summary", ""
            ),
            "relevant_matches": self.pipeline_metadata.get("relevant_matches", []),
            "recommended_resolution": self.pipeline_metadata.get(
                "recommended_resolution"
            ),
            "confidence_boost": self.pipeline_metadata.get("confidence_boost"),
            "exact_match_found": self.pipeline_metadata.get(
                "exact_match_found", False
            ),
            "exact_match_id": self.pipeline_metadata.get("exact_match_id"),
        }

    def _extract_signal_data(self) -> dict[str, Any]:
        """Extract signal correlation data from pipeline metadata."""
        return {
            "hypotheses": self.pipeline_metadata.get("hypotheses", []),
            "signal_summary": self.pipeline_metadata.get("signal_summary", ""),
            "service_dependency_chain": self.pipeline_metadata.get(
                "service_dependency_chain"
            ),
            "layers_queried": self.pipeline_metadata.get("layers_queried", []),
            "signals_gathered": self.pipeline_metadata.get("signals_gathered", 0),
            "temporal_summary": self.pipeline_metadata.get("temporal_summary", ""),
            "raw_signal_detail": self.pipeline_metadata.get("raw_signal_detail", ""),
        }

    def _extract_slo_data(self) -> dict[str, Any]:
        """Extract SLO breach data from pipeline metadata."""
        return {
            "slo_target": self.pipeline_metadata.get("slo_target"),
            "slo_compliance": self.pipeline_metadata.get("slo_compliance"),
            "slo_burn_rate": self.pipeline_metadata.get("slo_burn_rate"),
            "slo_error_budget_remaining": self.pipeline_metadata.get(
                "slo_error_budget_remaining"
            ),
            "slo_sli_type": self.pipeline_metadata.get("slo_sli_type", ""),
            "slo_condition": self.pipeline_metadata.get("slo_condition", ""),
        }

    # ── Prompt formatting ────────────────────────────────────

    def _format_impact(self, impact_data: dict[str, Any]) -> str:
        """Format customer impact data for the LLM prompt."""
        impact = impact_data.get("customer_impacting")
        reasoning = impact_data.get("reasoning", "")
        if impact is None:
            return "Customer impact assessment not available"
        return f"Customer impacting: {impact}. {reasoning}".strip()

    def _format_kb(self, kb_data: dict[str, Any]) -> str:
        """Format KB data for the LLM prompt."""
        summary = kb_data.get("prior_research_summary", "")
        if not summary:
            return "No prior KB research available"

        parts = [summary]
        if kb_data.get("exact_match_found"):
            match_id = kb_data.get("exact_match_id", "unknown")
            parts.append(f"Exact match found: {match_id}")
        if kb_data.get("recommended_resolution"):
            parts.append(
                f"Recommended resolution: {kb_data['recommended_resolution']}"
            )
        if kb_data.get("confidence_boost"):
            parts.append(f"KB confidence boost: {kb_data['confidence_boost']}")

        return "\n".join(parts)

    def _format_slo_context(self, slo_data: dict[str, Any]) -> str:
        """Format SLO breach data for the LLM prompt.

        Returns an empty string when no SLO data is available so the
        prompt section is omitted cleanly.
        """
        target = slo_data.get("slo_target")
        if target is None:
            return ""

        parts: list[str] = []
        sli_type = slo_data.get("slo_sli_type", "unknown")
        parts.append(f"SLI type: {sli_type}, target: {target}")

        compliance = slo_data.get("slo_compliance")
        if compliance is not None:
            parts.append(f"Current compliance: {compliance}")

        burn_rate = slo_data.get("slo_burn_rate")
        if burn_rate is not None:
            parts.append(f"Burn rate: {burn_rate}x")

        budget = slo_data.get("slo_error_budget_remaining")
        if budget is not None:
            parts.append(f"Error budget remaining: {budget}")

        condition = slo_data.get("slo_condition", "")
        if condition:
            parts.append(f"Condition: {condition}")

        return "\n".join(parts)

    def _format_hypotheses(self, hypotheses: list[dict[str, Any]]) -> str:
        """Format signal correlation hypotheses for the LLM prompt."""
        if not hypotheses:
            return "No signal correlation hypotheses available"

        lines: list[str] = []
        for i, h in enumerate(hypotheses, 1):
            desc = h.get("description", "")
            chain = h.get("causal_chain", "")
            conf = h.get("confidence", "unknown")
            signals = h.get("supporting_signals", [])
            layer = h.get("originating_layer", "unknown")
            lines.append(
                f"{i}. {desc} (confidence: {conf}, layer: {layer})\n"
                f"   Causal chain: {chain}\n"
                f"   Supporting signals: {', '.join(signals) if signals else 'none'}"
            )
        return "\n".join(lines)

    # ── Response parsing ─────────────────────────────────────

    def _parse_result(
        self,
        raw: str,
        signal_data: dict[str, Any],
        kb_data: dict[str, Any],
        model_name: str | None = None,
    ) -> StepResult:
        """Parse LLM response into a StepResult."""
        try:
            parsed = _parse_response(raw)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse LLM RCA response")
            return self._fallback_result(signal_data, kb_data, model_name)

        # Extract and normalize fields
        hypothesis = parsed.get("root_cause_hypothesis", "")
        if not isinstance(hypothesis, str) or not hypothesis:
            logger.warning("LLM returned empty or invalid hypothesis")
            return self._fallback_result(signal_data, kb_data, model_name)

        level = parsed.get("confidence_level", "low")
        if isinstance(level, str):
            level = level.lower()
        if level not in ("high", "medium", "low"):
            level = "low"

        percentage = parsed.get("confidence_percentage")
        percentage = self._normalize_percentage(percentage)

        level, percentage = _validate_confidence(level, percentage)

        supporting = parsed.get("supporting_evidence", [])
        if not isinstance(supporting, list):
            supporting = []

        alternatives = self._normalize_alternatives(
            parsed.get("alternative_hypotheses", [])
        )
        additional_needs = parsed.get("additional_data_needs", [])
        if not isinstance(additional_needs, list):
            additional_needs = []

        kb_citation = parsed.get("kb_citation")
        if not isinstance(kb_citation, str) or kb_citation == "null":
            kb_citation = None

        # Apply KB boost if applicable
        if (
            kb_data.get("confidence_boost") == "high"
            and kb_data.get("exact_match_found")
        ):
            match_id = kb_data.get("exact_match_id", "unknown")
            evidence_note = f"KB exact match ({match_id}) confirms this pattern"
            if evidence_note not in supporting:
                supporting.append(evidence_note)
            if kb_citation is None:
                kb_citation = match_id

        # Enforce alternatives when confidence < high
        if level != "high" and not alternatives:
            alternatives = self._fallback_alternatives(signal_data)

        # Enforce additional_data_needs when confidence is low
        if level == "low" and not additional_needs:
            additional_needs = [
                "Additional monitoring data or logs may clarify"
                " the root cause"
            ]

        if len(hypothesis) > 100:
            summary = (
                f"RCA hypothesis: {hypothesis[:100]}..."
                f" (confidence: {level})"
            )
        else:
            summary = (
                f"RCA hypothesis: {hypothesis}"
                f" (confidence: {level})"
            )

        return StepResult(
            success=True,
            summary=summary,
            data={
                "root_cause_hypothesis": hypothesis,
                "confidence_level": level,
                "confidence_percentage": percentage,
                "supporting_evidence": supporting,
                "alternative_hypotheses": alternatives,
                "additional_data_needs": additional_needs,
                "kb_citation": kb_citation,
                "synthesis_source": "llm",
                "rca_model_tier": "deep_rca",
                "rca_model_used": model_name,
            },
        )

    def _normalize_percentage(self, value: Any) -> int | None:
        """Normalize confidence percentage to int 0-100 or None."""
        if value is None:
            return None
        try:
            pct = int(value)
            return max(0, min(100, pct))
        except (TypeError, ValueError):
            return None

    def _normalize_alternatives(
        self, raw: Any
    ) -> list[dict[str, Any]]:
        """Normalize alternative hypotheses list."""
        if not isinstance(raw, list):
            return []
        result: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            desc = item.get("description", "")
            if not desc:
                continue
            pct = self._normalize_percentage(item.get("confidence_percentage"))
            result.append({"description": desc, "confidence_percentage": pct})
        return result

    # ── Fallback and degradation paths ───────────────────────

    def _fallback_result(
        self,
        signal_data: dict[str, Any],
        kb_data: dict[str, Any],
        model_name: str | None = None,
    ) -> StepResult:
        """Build result from signal correlation hypotheses when LLM fails."""
        hypotheses = signal_data.get("hypotheses", [])

        # Promote best signal correlation hypothesis
        if hypotheses:
            best = hypotheses[0]
            hypothesis = best.get("description", "Unable to determine root cause")
            supporting = best.get("supporting_signals", [])
            level = best.get("confidence", "low")
            if isinstance(level, str):
                level = level.lower()
            if level not in ("high", "medium", "low"):
                level = "low"

            # Build alternatives from remaining hypotheses
            alternatives = []
            for h in hypotheses[1:]:
                desc = h.get("description", "")
                if desc:
                    alternatives.append({
                        "description": desc,
                        "confidence_percentage": None,
                    })

            additional_needs = []
            if level == "low":
                additional_needs = [
                    "LLM synthesis failed; additional analysis needed"
                ]
        else:
            hypothesis = "Unable to determine root cause — insufficient data"
            supporting = []
            level = "low"
            alternatives = []
            additional_needs = [
                "No signal correlation data available for analysis"
            ]

        # Check for KB citation
        kb_citation = None
        if kb_data.get("exact_match_found"):
            kb_citation = kb_data.get("exact_match_id")

        # Enforce alternatives when confidence < high
        if level != "high" and not alternatives:
            alternatives = [
                {
                    "description": "Insufficient data for alternatives",
                    "confidence_percentage": None,
                }
            ]

        fallback_summary = (
            f"RCA hypothesis (fallback): {hypothesis[:80]}"
            f" (confidence: {level})"
        )
        return StepResult(
            success=True,
            summary=fallback_summary,
            data={
                "root_cause_hypothesis": hypothesis,
                "confidence_level": level,
                "confidence_percentage": None,
                "supporting_evidence": supporting,
                "alternative_hypotheses": alternatives,
                "additional_data_needs": additional_needs,
                "kb_citation": kb_citation,
                "synthesis_source": "fallback",
                "rca_model_tier": "deep_rca" if model_name else "none",
                "rca_model_used": model_name,
            },
        )

    def _insufficient_data_result(self) -> StepResult:
        """Return result when no pipeline metadata is available."""
        no_data_msg = (
            "Unable to determine root cause"
            " — no prior step data available"
        )
        return StepResult(
            success=True,
            summary=f"RCA hypothesis: {no_data_msg} (confidence: low)",
            data={
                "root_cause_hypothesis": no_data_msg,
                "confidence_level": "low",
                "confidence_percentage": None,
                "supporting_evidence": [],
                "alternative_hypotheses": [
                    {
                        "description": "Insufficient data for alternatives",
                        "confidence_percentage": None,
                    }
                ],
                "additional_data_needs": [
                    "Customer impact assessment data",
                    "Knowledge base prior research",
                    "Signal correlation data",
                ],
                "kb_citation": None,
                "synthesis_source": "fallback",
                "rca_model_tier": "none",
                "rca_model_used": None,
            },
        )

    def _fallback_alternatives(
        self, signal_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Build alternative hypotheses from signal correlation.

        Used when the LLM produced a main hypothesis but omitted
        alternatives.  All signal hypotheses are included because
        the main hypothesis came from the LLM, not from this list.
        """
        hypotheses = signal_data.get("hypotheses", [])
        alternatives: list[dict[str, Any]] = []
        for h in hypotheses:
            desc = h.get("description", "")
            if desc:
                alternatives.append(
                    {"description": desc, "confidence_percentage": None}
                )
        if not alternatives:
            alternatives = [
                {
                    "description": "Insufficient data for alternatives",
                    "confidence_percentage": None,
                }
            ]
        return alternatives
