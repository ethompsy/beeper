"""KB query and prior research investigation step.

Queries the Knowledge Base for similar past incidents and synthesizes
findings using LLM to build on prior research (FR5, FR6).
"""

import json
import logging
import re
from typing import Any

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.kb.client import KBClient
from beeper_investigator.kb.schemas import SearchResult
from beeper_investigator.llm.client import LlmClient, LlmClientError
from beeper_investigator.steps import StepResult

logger = logging.getLogger(__name__)

EXACT_MATCH_THRESHOLD = 0.92

_SYNTHESIS_SYSTEM_PROMPT = """\
You are an SRE investigator reviewing prior research from the Knowledge Base. \
Given the current investigation context and relevant KB matches, synthesize \
what we know from past incidents.

Respond with ONLY a JSON object:
{"prior_research_summary": "brief synthesis of what prior research tells us", \
"relevant_matches": ["inv-id-1: brief description"], \
"recommended_resolution": "resolution suggestion based on prior research or null", \
"confidence_boost": "high"|"medium"|null}

Rules:
- high confidence: Exact or near-exact match found with known resolution
- medium confidence: Similar incidents found with relevant context
- null: No actionable prior research found"""

_SYNTHESIS_USER_TEMPLATE = """\
Current investigation:
Condition: {condition}
Service: {service}
Severity: {severity}

KB search results:
{formatted_results}"""

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def _parse_response(raw: str) -> dict[str, Any]:
    """Parse LLM response, stripping markdown fences if present."""
    match = _CODE_FENCE_RE.search(raw)
    text = match.group(1) if match else raw
    result: dict[str, Any] = json.loads(text.strip())
    return result


def _check_exact_match(results: list[SearchResult]) -> SearchResult | None:
    """Return highest-scoring result if above threshold, else None."""
    if results and results[0].score >= EXACT_MATCH_THRESHOLD:
        return results[0]
    return None


def _format_results(results: list[SearchResult]) -> str:
    """Format search results for LLM prompt."""
    if not results:
        return "(no results)"
    lines: list[str] = []
    for r in results:
        payload = r.payload
        inv_id = payload.get("investigation_id", r.id)
        summary = payload.get("summary", payload.get("title", ""))
        root_cause = payload.get("root_cause", "")
        resolution = payload.get("resolution", "")
        lines.append(
            f"- [{inv_id}] (score={r.score:.2f}) {summary}"
            + (f" | root_cause: {root_cause}" if root_cause else "")
            + (f" | resolution: {resolution}" if resolution else "")
        )
    return "\n".join(lines)


class KBQueryStep:
    """Query the Knowledge Base for similar past incidents.

    Searches both the investigations and knowledge collections, detects
    exact matches, and synthesizes findings using LLM.
    """

    name: str = "KB Query & Prior Research"

    def __init__(
        self,
        kb_client: KBClient,
        llm_client: LlmClient,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
    ) -> None:
        self.kb_client = kb_client
        self.llm_client = llm_client
        self.context = context
        self.status_updater = status_updater

    def execute(self) -> StepResult:
        """Run the KB query and prior research step."""
        self.status_updater.update_message("Querying knowledge base for prior research")
        logger.info(
            "Querying KB for service=%s condition=%s",
            self.context.service,
            self.context.condition,
        )

        # Check embedding model availability before attempting
        if not self.llm_client.config.embedding_model:
            logger.warning("Embedding model not configured; skipping KB query")
            return StepResult(
                success=True,
                summary="KB query skipped: embedding model not configured",
                data={"kb_available": False, "reason": "embedding_model_not_configured"},
            )

        # Generate embedding
        query_text = (
            f"{self.context.condition} {self.context.service} {self.context.severity}"
        )
        try:
            embedding = self.llm_client.embed_sync(query_text)
        except LlmClientError as exc:
            logger.warning("Embedding generation failed: %s", exc)
            return StepResult(
                success=True,
                summary="KB query skipped: embedding unavailable",
                data={"kb_available": False, "reason": "embedding_failed"},
            )

        # Search both collections independently so partial results survive
        investigation_results: list[SearchResult] = []
        knowledge_results: list[SearchResult] = []
        search_errors: list[str] = []

        try:
            investigation_results = self.kb_client.search_investigations(
                query_vector=embedding,
                limit=5,
                service=self.context.service,
            )
        except Exception as exc:
            logger.warning("Investigation search failed: %s", exc)
            search_errors.append(f"investigations: {exc}")

        try:
            knowledge_results = self.kb_client.search_knowledge(
                query_vector=embedding,
                limit=5,
                service=self.context.service,
            )
        except Exception as exc:
            logger.warning("Knowledge search failed: %s", exc)
            search_errors.append(f"knowledge: {exc}")

        # Both collections failed — report full failure
        if len(search_errors) == 2:
            return StepResult(
                success=False,
                summary="KB query failed: connection error",
                data={"kb_available": False, "reason": "connection_failed"},
                error="; ".join(search_errors),
            )

        all_results = investigation_results + knowledge_results
        if not all_results:
            logger.info("No prior research found in KB")
            return StepResult(
                success=True,
                summary="No prior research found",
                data={
                    "kb_available": True,
                    "prior_investigations_count": 0,
                    "prior_knowledge_count": 0,
                    "exact_match_found": False,
                    "prior_research_summary": "",
                    "relevant_matches": [],
                    "recommended_resolution": None,
                    "confidence_boost": None,
                },
            )

        # Check for exact match
        exact_match = _check_exact_match(investigation_results)

        # Synthesize with LLM
        data: dict[str, Any] = {
            "kb_available": True,
            "prior_investigations_count": len(investigation_results),
            "prior_knowledge_count": len(knowledge_results),
            "exact_match_found": exact_match is not None,
        }

        if exact_match:
            data["exact_match_id"] = exact_match.payload.get(
                "investigation_id", exact_match.id
            )

        synthesis = self._synthesize(all_results, exact_match)
        data.update(synthesis)

        total = len(investigation_results) + len(knowledge_results)
        summary_parts = [f"Found {total} prior KB entries for service '{self.context.service}'"]
        if exact_match:
            summary_parts.append("exact match detected")

        return StepResult(
            success=True,
            summary="; ".join(summary_parts),
            data=data,
        )

    def _synthesize(
        self,
        results: list[SearchResult],
        exact_match: SearchResult | None,
    ) -> dict[str, Any]:
        """Use LLM to synthesize KB findings."""
        formatted = _format_results(results)
        messages = [
            {"role": "system", "content": _SYNTHESIS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _SYNTHESIS_USER_TEMPLATE.format(
                    condition=self.context.condition,
                    service=self.context.service,
                    severity=self.context.severity,
                    formatted_results=formatted,
                ),
            },
        ]

        try:
            raw = self.llm_client.complete_sync(
                messages,
                max_tokens=512,
                temperature=0.0,
            )
        except Exception as exc:
            logger.warning("LLM synthesis failed: %s", exc)
            return self._fallback_synthesis(results, exact_match)

        return self._parse_synthesis(raw, results, exact_match)

    def _parse_synthesis(
        self,
        raw: str,
        results: list[SearchResult],
        exact_match: SearchResult | None,
    ) -> dict[str, Any]:
        """Parse the LLM synthesis response."""
        try:
            parsed = _parse_response(raw)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse LLM synthesis response: %s", raw)
            return self._fallback_synthesis(results, exact_match)

        confidence = parsed.get("confidence_boost")
        if isinstance(confidence, str):
            confidence = confidence.lower()
        if confidence not in ("high", "medium", None):
            confidence = None

        return {
            "prior_research_summary": parsed.get("prior_research_summary", ""),
            "relevant_matches": parsed.get("relevant_matches", []),
            "recommended_resolution": parsed.get("recommended_resolution"),
            "confidence_boost": confidence,
        }

    def _fallback_synthesis(
        self,
        results: list[SearchResult],
        exact_match: SearchResult | None,
    ) -> dict[str, Any]:
        """Build synthesis from raw results when LLM fails."""
        summaries = []
        for r in results[:3]:
            inv_id = r.payload.get("investigation_id", r.id)
            summary = r.payload.get("summary", r.payload.get("title", ""))
            if summary:
                summaries.append(f"{inv_id}: {summary}")

        resolution = None
        confidence = None
        if exact_match:
            resolution = exact_match.payload.get("resolution")
            confidence = "high"
        elif results:
            confidence = "medium"

        return {
            "prior_research_summary": "; ".join(summaries) if summaries else "",
            "relevant_matches": summaries,
            "recommended_resolution": resolution,
            "confidence_boost": confidence,
        }
