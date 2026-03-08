"""Resolution recommendation generation investigation step.

Synthesizes all prior investigation findings — RCA hypothesis, KB prior
resolutions, impact assessment, and signal correlation — into actionable
resolution recommendations for SREs (FR8, AC1-AC4).
"""

import json
import logging
import re
from typing import Any

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.steps import StepResult

logger = logging.getLogger(__name__)

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)

_RESOLUTION_SYSTEM_PROMPT = """\
You are a senior SRE generating actionable resolution recommendations \
based on a completed root-cause analysis. Provide practical, specific \
actions that an on-call engineer can execute.

Respond with ONLY a JSON object:
{"recommendations": [
  {"action": "specific action description",
   "confidence": "high"|"medium"|"low",
   "expected_outcome": "what will happen if action is taken",
   "risk_assessment": "high"|"medium"|"low",
   "based_on_prior_incident": "incident ID or null"}
],
"ranking_rationale": "why recommendations are ordered this way",
"diagnostic_actions": ["safe diagnostic step 1", "step 2"]}

Rules:
- Provide 1-5 recommendations, ordered by confidence (highest first)
- high confidence: proven fix, confirmed by prior incident or strong evidence
- medium confidence: likely effective based on RCA but not confirmed
- low confidence: speculative, may help but needs validation
- risk_assessment: high = could cause outage, medium = minor impact, \
low = safe
- ALWAYS include diagnostic_actions when root cause confidence < high
- If prior KB resolution exists, include it as the first recommendation
- Each action must be specific and actionable, not generic advice
- based_on_prior_incident must reference actual incident ID or be null"""

_RESOLUTION_USER_TEMPLATE = """\
Investigation context:
Condition: {condition}
Service: {service}
Severity: {severity}
Customer impacting: {impact_summary}

Root cause analysis:
Hypothesis: {rca_hypothesis}
Confidence: {rca_confidence} ({rca_percentage}%)
Supporting evidence: {supporting_evidence}

Prior KB research:
{kb_summary}

Signal correlation:
{signal_summary}

Service dependency chain: {dependency_chain}"""

_VALID_LEVELS = ("high", "medium", "low")

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}
_CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


def _parse_response(raw: str) -> dict[str, Any]:
    """Parse LLM response, stripping markdown fences if present."""
    match = _CODE_FENCE_RE.search(raw)
    text = match.group(1) if match else raw
    result: dict[str, Any] = json.loads(text.strip())
    return result


def _normalize_level(value: Any, default: str = "medium") -> str:
    """Normalize a confidence/risk level to high/medium/low."""
    if not isinstance(value, str):
        return default
    lower = value.lower().strip()
    if lower in _VALID_LEVELS:
        return lower
    return default


def _sort_recommendations(
    recs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sort by confidence descending then risk ascending."""
    return sorted(
        recs,
        key=lambda r: (
            _CONFIDENCE_ORDER.get(r.get("confidence", "medium"), 1),
            _RISK_ORDER.get(r.get("risk_assessment", "medium"), 1),
        ),
    )


class ResolutionRecommendationStep:
    """Generate resolution recommendations from investigation findings.

    Synthesizes RCA hypothesis, KB prior resolutions, customer impact,
    and signal correlation into ranked, actionable recommendations.
    """

    name: str = "Resolution Recommendations"

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
        """Run the resolution recommendation step."""
        self.status_updater.update_message(
            "Generating resolution recommendations"
        )
        logger.info(
            "Generating resolution recommendations for "
            "service=%s condition=%s",
            self.context.service,
            self.context.condition,
        )

        rca_data = self._extract_rca_data()
        kb_data = self._extract_kb_data()
        impact_data = self._extract_impact_data()
        signal_data = self._extract_signal_data()

        has_rca = bool(rca_data.get("root_cause_hypothesis"))
        has_kb = bool(
            kb_data.get("prior_research_summary")
            or kb_data.get("recommended_resolution")
        )
        has_signals = bool(
            signal_data.get("signal_summary")
            or signal_data.get("hypotheses")
        )
        has_impact = impact_data.get("customer_impacting") is not None

        if not has_rca and not has_kb and not has_signals and not has_impact:
            logger.info(
                "No pipeline metadata available; returning generic"
                " safe diagnostic"
            )
            return self._no_data_result()

        # Build LLM prompt
        messages = self._build_messages(
            rca_data, kb_data, impact_data, signal_data
        )

        model_name = self.llm_client.select_model("standard")

        try:
            raw = self.llm_client.complete_sync(
                messages,
                max_tokens=1024,
                temperature=0.0,
                model=model_name,
            )
        except Exception as exc:
            logger.warning("LLM recommendation synthesis failed: %s", exc)
            return self._fallback_result(rca_data, kb_data, model_name)

        return self._parse_result(raw, rca_data, kb_data, model_name)

    # ── Pipeline metadata extraction ─────────────────────────

    def _extract_rca_data(self) -> dict[str, Any]:
        return {
            "root_cause_hypothesis": self.pipeline_metadata.get(
                "root_cause_hypothesis", ""
            ),
            "confidence_level": self.pipeline_metadata.get(
                "confidence_level", ""
            ),
            "confidence_percentage": self.pipeline_metadata.get(
                "confidence_percentage"
            ),
            "supporting_evidence": self.pipeline_metadata.get(
                "supporting_evidence", []
            ),
            "alternative_hypotheses": self.pipeline_metadata.get(
                "alternative_hypotheses", []
            ),
            "kb_citation": self.pipeline_metadata.get("kb_citation"),
            "synthesis_source": self.pipeline_metadata.get(
                "synthesis_source", ""
            ),
        }

    def _extract_kb_data(self) -> dict[str, Any]:
        return {
            "recommended_resolution": self.pipeline_metadata.get(
                "recommended_resolution"
            ),
            "confidence_boost": self.pipeline_metadata.get(
                "confidence_boost"
            ),
            "exact_match_found": self.pipeline_metadata.get(
                "exact_match_found", False
            ),
            "exact_match_id": self.pipeline_metadata.get("exact_match_id"),
            "prior_research_summary": self.pipeline_metadata.get(
                "prior_research_summary", ""
            ),
        }

    def _extract_impact_data(self) -> dict[str, Any]:
        return {
            "customer_impacting": self.pipeline_metadata.get(
                "customer_impacting"
            ),
            "reasoning": self.pipeline_metadata.get("reasoning", ""),
        }

    def _extract_signal_data(self) -> dict[str, Any]:
        return {
            "signal_summary": self.pipeline_metadata.get(
                "signal_summary", ""
            ),
            "hypotheses": self.pipeline_metadata.get("hypotheses", []),
            "service_dependency_chain": self.pipeline_metadata.get(
                "service_dependency_chain"
            ),
        }

    # ── Prompt building ──────────────────────────────────────

    def _build_messages(
        self,
        rca_data: dict[str, Any],
        kb_data: dict[str, Any],
        impact_data: dict[str, Any],
        signal_data: dict[str, Any],
    ) -> list[dict[str, str]]:
        impact_val = impact_data.get("customer_impacting")
        reasoning = impact_data.get("reasoning", "")
        if impact_val is None:
            impact_summary = "Unknown"
        else:
            impact_summary = f"{impact_val}. {reasoning}".strip()

        hypothesis = (
            rca_data.get("root_cause_hypothesis")
            or "No RCA hypothesis available"
        )
        confidence = rca_data.get("confidence_level", "unknown")
        percentage = rca_data.get("confidence_percentage")
        pct_str = str(percentage) if percentage is not None else "N/A"

        evidence = rca_data.get("supporting_evidence", [])
        evidence_str = (
            "\n".join(f"- {e}" for e in evidence)
            if evidence
            else "No supporting evidence"
        )

        kb_summary = self._format_kb_summary(kb_data)
        sig_summary = (
            signal_data.get("signal_summary")
            or "No signal data available"
        )
        dep_chain = signal_data.get("service_dependency_chain")
        dep_str = (
            " → ".join(dep_chain)
            if dep_chain
            else "Not available"
        )

        user_content = _RESOLUTION_USER_TEMPLATE.format(
            condition=self.context.condition,
            service=self.context.service,
            severity=self.context.severity,
            impact_summary=impact_summary,
            rca_hypothesis=hypothesis,
            rca_confidence=confidence,
            rca_percentage=pct_str,
            supporting_evidence=evidence_str,
            kb_summary=kb_summary,
            signal_summary=sig_summary,
            dependency_chain=dep_str,
        )

        return [
            {"role": "system", "content": _RESOLUTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    def _format_kb_summary(self, kb_data: dict[str, Any]) -> str:
        summary = kb_data.get("prior_research_summary", "")
        if not summary and not kb_data.get("recommended_resolution"):
            return "No prior KB research available"

        parts: list[str] = []
        if summary:
            parts.append(summary)
        if kb_data.get("exact_match_found"):
            match_id = kb_data.get("exact_match_id", "unknown")
            parts.append(f"Exact match found: {match_id}")
        if kb_data.get("recommended_resolution"):
            parts.append(
                "Recommended resolution: "
                f"{kb_data['recommended_resolution']}"
            )
        if kb_data.get("confidence_boost"):
            parts.append(
                f"KB confidence boost: {kb_data['confidence_boost']}"
            )
        return "\n".join(parts) if parts else "No prior KB research available"

    # ── Response parsing ─────────────────────────────────────

    def _parse_result(
        self,
        raw: str,
        rca_data: dict[str, Any],
        kb_data: dict[str, Any],
        model_name: str | None = None,
    ) -> StepResult:
        try:
            parsed = _parse_response(raw)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse LLM recommendation response")
            return self._fallback_result(rca_data, kb_data, model_name)

        raw_recs = parsed.get("recommendations", [])
        if not isinstance(raw_recs, list) or not raw_recs:
            logger.warning("LLM returned empty recommendations")
            return self._fallback_result(rca_data, kb_data, model_name)

        recommendations = self._normalize_recommendations(raw_recs)
        if not recommendations:
            logger.warning(
                "All LLM recommendations failed validation"
            )
            return self._fallback_result(rca_data, kb_data, model_name)

        ranking_rationale = parsed.get("ranking_rationale", "")
        if not isinstance(ranking_rationale, str):
            ranking_rationale = ""

        raw_diag = parsed.get("diagnostic_actions", [])
        diagnostic_actions: list[str] = (
            [str(d) for d in raw_diag]
            if isinstance(raw_diag, list)
            else []
        )

        # Promote KB resolution if exact match found
        recommendations = self._promote_kb_resolution(
            recommendations, kb_data
        )

        # Add diagnostic actions when RCA confidence < high
        rca_confidence = _normalize_level(
            rca_data.get("confidence_level", ""), "low"
        )
        if rca_confidence != "high":
            recommendations = self._prepend_diagnostics(
                recommendations, rca_confidence
            )

        # Sort and cap
        recommendations = _sort_recommendations(recommendations)
        recommendations = recommendations[:5]

        if not ranking_rationale:
            ranking_rationale = self._generate_rationale(recommendations)

        count = len(recommendations)
        summary = (
            f"Generated {count} resolution recommendation"
            f"{'s' if count != 1 else ''}"
        )

        return StepResult(
            success=True,
            summary=summary,
            data={
                "recommendations": recommendations,
                "recommendation_count": count,
                "ranking_rationale": ranking_rationale,
                "diagnostic_actions": diagnostic_actions,
                "synthesis_source": "llm",
                "resolution_model_tier": "standard",
                "resolution_model_used": model_name,
            },
        )

    def _normalize_recommendations(
        self, raw_recs: list[Any]
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for item in raw_recs:
            if not isinstance(item, dict):
                continue
            action = item.get("action", "")
            if not isinstance(action, str) or not action:
                continue

            prior = item.get("based_on_prior_incident")
            if (
                not isinstance(prior, str)
                or prior == "null"
                or prior == ""
            ):
                prior = None

            result.append({
                "action": action,
                "confidence": _normalize_level(
                    item.get("confidence"), "medium"
                ),
                "expected_outcome": str(
                    item.get("expected_outcome", "")
                ),
                "risk_assessment": _normalize_level(
                    item.get("risk_assessment"), "medium"
                ),
                "based_on_prior_incident": prior,
            })
        return result

    def _promote_kb_resolution(
        self,
        recommendations: list[dict[str, Any]],
        kb_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Promote KB resolution when exact match found."""
        if not kb_data.get("exact_match_found"):
            return recommendations
        resolution = kb_data.get("recommended_resolution")
        if not resolution:
            return recommendations

        match_id = kb_data.get("exact_match_id")
        # Check if already present
        for rec in recommendations:
            if rec.get("based_on_prior_incident") == match_id:
                rec["confidence"] = "high"
                return recommendations

        kb_rec: dict[str, Any] = {
            "action": resolution,
            "confidence": "high",
            "expected_outcome": "Resolution proven effective"
            " in prior incident",
            "risk_assessment": "low",
            "based_on_prior_incident": match_id,
        }
        return [kb_rec] + recommendations

    def _prepend_diagnostics(
        self,
        recommendations: list[dict[str, Any]],
        rca_confidence: str,
    ) -> list[dict[str, Any]]:
        """Add diagnostic steps when RCA confidence is not high."""
        if rca_confidence == "low":
            gather_rec: dict[str, Any] = {
                "action": (
                    "Gather additional diagnostic data: review"
                    " recent logs, check dependent service health,"
                    " and verify monitoring coverage"
                ),
                "confidence": "high",
                "expected_outcome": (
                    "Better understanding of root cause"
                    " before taking corrective action"
                ),
                "risk_assessment": "low",
                "based_on_prior_incident": None,
            }
            has_gather = any(
                "gather" in r.get("action", "").lower()
                for r in recommendations
            )
            if not has_gather:
                recommendations = [gather_rec] + recommendations

        return recommendations

    def _generate_rationale(
        self, recommendations: list[dict[str, Any]]
    ) -> str:
        if not recommendations:
            return "No recommendations available"
        top = recommendations[0]
        return (
            f"Top recommendation has {top.get('confidence', 'unknown')}"
            f" confidence with"
            f" {top.get('risk_assessment', 'unknown')} risk"
        )

    # ── Fallback and degradation paths ───────────────────────

    def _fallback_result(
        self,
        rca_data: dict[str, Any],
        kb_data: dict[str, Any],
        model_name: str | None = None,
    ) -> StepResult:
        """Build result when LLM fails or returns bad data."""
        recommendations: list[dict[str, Any]] = []
        diagnostic_actions: list[str] = []

        # Try KB recommended resolution first
        kb_resolution = kb_data.get("recommended_resolution")
        if kb_resolution:
            match_id = kb_data.get("exact_match_id")
            recommendations.append({
                "action": kb_resolution,
                "confidence": (
                    "high"
                    if kb_data.get("exact_match_found")
                    else "medium"
                ),
                "expected_outcome": (
                    "Resolution based on prior KB research"
                ),
                "risk_assessment": "low",
                "based_on_prior_incident": match_id,
            })

        # Try RCA hypothesis
        hypothesis = rca_data.get("root_cause_hypothesis", "")
        if hypothesis and not recommendations:
            rca_confidence = _normalize_level(
                rca_data.get("confidence_level"), "low"
            )
            recommendations.append({
                "action": (
                    f"Investigate and address: {hypothesis}"
                ),
                "confidence": rca_confidence,
                "expected_outcome": (
                    "Address identified root cause"
                ),
                "risk_assessment": "medium",
                "based_on_prior_incident": None,
            })

        # Always have at least one recommendation
        if not recommendations:
            recommendations.append({
                "action": (
                    "Review service health dashboards and"
                    " recent deployment changes for the"
                    f" affected service ({self.context.service})"
                ),
                "confidence": "low",
                "expected_outcome": (
                    "Identify potential contributing factors"
                ),
                "risk_assessment": "low",
                "based_on_prior_incident": None,
            })
            diagnostic_actions = [
                "Check service logs for error patterns",
                "Verify recent deployments or config changes",
                "Check dependent service health",
            ]

        recommendations = recommendations[:5]
        count = len(recommendations)
        summary = (
            f"Generated {count} resolution recommendation"
            f"{'s' if count != 1 else ''} (fallback)"
        )

        return StepResult(
            success=True,
            summary=summary,
            data={
                "recommendations": recommendations,
                "recommendation_count": count,
                "ranking_rationale": (
                    "Fallback recommendations based on"
                    " available evidence"
                ),
                "diagnostic_actions": diagnostic_actions,
                "synthesis_source": "fallback",
                "resolution_model_tier": "standard" if model_name else "none",
                "resolution_model_used": model_name,
            },
        )

    def _no_data_result(self) -> StepResult:
        """Return result when no pipeline metadata is available."""
        diagnostic_actions = [
            "Check service logs for error patterns",
            "Verify recent deployments or config changes",
            "Check dependent service health",
        ]
        rec: dict[str, Any] = {
            "action": (
                "Review service health dashboards and"
                " recent deployment changes for the"
                f" affected service ({self.context.service})"
            ),
            "confidence": "low",
            "expected_outcome": (
                "Identify potential contributing factors"
            ),
            "risk_assessment": "low",
            "based_on_prior_incident": None,
        }
        return StepResult(
            success=True,
            summary=(
                "Generated 1 resolution recommendation"
                " (insufficient data)"
            ),
            data={
                "recommendations": [rec],
                "recommendation_count": 1,
                "ranking_rationale": (
                    "Insufficient data for ranked recommendations;"
                    " providing safe diagnostic action"
                ),
                "diagnostic_actions": diagnostic_actions,
                "synthesis_source": "fallback",
                "resolution_model_tier": "none",
                "resolution_model_used": None,
            },
        )
