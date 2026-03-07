"""Investigation documentation step.

Generates comprehensive investigation documentation and persists it
to the knowledge base for future reference and semantic search
(FR9, AC1-AC4).
"""

import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from qdrant_client.models import PointStruct

from beeper_investigator.context import InvestigationContext
from beeper_investigator.k8s.status import InvestigationStatusUpdater
from beeper_investigator.kb.client import (
    KNOWLEDGE_COLLECTION,
    KBClient,
)
from beeper_investigator.llm.client import LlmClient
from beeper_investigator.steps import StepResult

logger = logging.getLogger(__name__)

_CODE_FENCE_RE = re.compile(
    r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL
)

_DEFAULT_BUFFER_DIR = "/tmp/beeper-buffer"
_MAX_RETRIES = 3
_RETRY_DELAYS = [1.0, 2.0]
_DEFAULT_VECTOR_DIM = 1536

_DOC_SYSTEM_PROMPT = """\
You are a senior SRE documenting a completed incident investigation. \
Generate a structured, searchable investigation report that will be \
stored in a knowledge base for future reference.

Respond with ONLY a JSON object:
{"title": "concise investigation title",
 "summary": "comprehensive 2-4 sentence investigation summary",
 "root_cause": "confirmed or suspected root cause description",
 "resolution": "actions taken or recommended",
 "signals_summary": "key signals and their correlation",
 "confidence_overview": "overall confidence assessment",
 "key_findings": ["finding 1", "finding 2"]}

Rules:
- title must be specific and searchable (not "Investigation Report")
- summary should enable future semantic search matches
- Include specific metrics, error patterns, and service names
- If root cause is uncertain, clearly state the uncertainty level
- resolution should include both immediate and long-term actions
- key_findings should capture the most important discoveries"""

_DOC_USER_TEMPLATE = """\
Investigation context:
Investigation ID: {investigation_id}
Condition: {condition}
Service: {service}
Severity: {severity}

Customer impact:
{impact_summary}

Signal correlation:
{signal_summary}

Root cause analysis:
Hypothesis: {rca_hypothesis}
Confidence: {rca_confidence} ({rca_percentage}%)
Supporting evidence: {supporting_evidence}

Resolution recommendations:
{resolution_summary}

Prior research:
{prior_research}

Related investigations: {related_ids}"""


def _parse_response(raw: str) -> dict[str, Any]:
    """Parse LLM response, stripping markdown fences."""
    match = _CODE_FENCE_RE.search(raw)
    text = match.group(1) if match else raw
    result: dict[str, Any] = json.loads(text.strip())
    return result


class InvestigationDocumentationStep:
    """Document investigation findings to the knowledge base.

    Generates a comprehensive investigation report using LLM and
    persists it with embeddings for future semantic search (FR9).
    """

    name: str = "Investigation Documentation"

    def __init__(
        self,
        llm_client: LlmClient,
        kb_client: KBClient,
        context: InvestigationContext,
        status_updater: InvestigationStatusUpdater,
        pipeline_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.kb_client = kb_client
        self.context = context
        self.status_updater = status_updater
        self.pipeline_metadata = pipeline_metadata or {}

    def execute(self) -> StepResult:
        """Run the investigation documentation step."""
        self.status_updater.update_message(
            "Documenting investigation findings"
        )
        logger.info(
            "Documenting investigation for "
            "service=%s condition=%s",
            self.context.service,
            self.context.condition,
        )

        rca_data = self._extract_rca_data()
        kb_data = self._extract_kb_data()
        impact_data = self._extract_impact_data()
        signal_data = self._extract_signal_data()
        resolution_data = self._extract_resolution_data()
        related = self._collect_related_investigations(
            kb_data, rca_data, resolution_data
        )

        doc = self._generate_documentation(
            rca_data, kb_data, impact_data,
            signal_data, resolution_data, related,
        )

        embedding, embedding_ok = self._generate_embedding(
            doc["summary"]
        )

        entry_id = str(uuid.uuid4())
        payload = self._build_payload(
            entry_id, doc, rca_data, resolution_data,
            impact_data, related,
        )

        persisted, buffered, buffer_path = (
            self._persist_entry(entry_id, payload, embedding)
        )

        summary = (
            f"Documented investigation: {doc['title']}"
        )
        if not persisted and buffered:
            summary += " (buffered locally)"
        elif not persisted:
            summary += " (persistence failed)"

        return StepResult(
            success=True,
            summary=summary,
            data={
                "documentation_title": doc["title"],
                "documentation_summary": doc["summary"],
                "kb_entry_id": entry_id if persisted else None,
                "persisted": persisted,
                "buffered": buffered,
                "buffer_path": buffer_path,
                "embedding_generated": embedding_ok,
                "related_investigations": list(related),
                "synthesis_source": doc["synthesis_source"],
                "doc_model_tier": doc.get("doc_model_tier", "none"),
                "doc_model_used": doc.get("doc_model_used"),
            },
        )

    # ── Pipeline metadata extraction ────────────────────────

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
            "kb_citation": self.pipeline_metadata.get(
                "kb_citation"
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
            "exact_match_id": self.pipeline_metadata.get(
                "exact_match_id"
            ),
            "prior_research_summary": self.pipeline_metadata.get(
                "prior_research_summary", ""
            ),
            "relevant_matches": self.pipeline_metadata.get(
                "relevant_matches", []
            ),
        }

    def _extract_impact_data(self) -> dict[str, Any]:
        return {
            "customer_impacting": self.pipeline_metadata.get(
                "customer_impacting"
            ),
            "reasoning": self.pipeline_metadata.get(
                "reasoning", ""
            ),
        }

    def _extract_signal_data(self) -> dict[str, Any]:
        return {
            "signal_summary": self.pipeline_metadata.get(
                "signal_summary", ""
            ),
            "hypotheses": self.pipeline_metadata.get(
                "hypotheses", []
            ),
            "service_dependency_chain": self.pipeline_metadata.get(
                "service_dependency_chain"
            ),
        }

    def _extract_resolution_data(self) -> dict[str, Any]:
        return {
            "recommendations": self.pipeline_metadata.get(
                "recommendations", []
            ),
            "recommendation_count": self.pipeline_metadata.get(
                "recommendation_count", 0
            ),
            "ranking_rationale": self.pipeline_metadata.get(
                "ranking_rationale", ""
            ),
            "diagnostic_actions": self.pipeline_metadata.get(
                "diagnostic_actions", []
            ),
        }

    # ── Prior investigation linking ─────────────────────────

    def _collect_related_investigations(
        self,
        kb_data: dict[str, Any],
        rca_data: dict[str, Any],
        resolution_data: dict[str, Any],
    ) -> list[str]:
        """Collect unique prior investigation IDs."""
        related: set[str] = set()

        match_id = kb_data.get("exact_match_id")
        if isinstance(match_id, str) and match_id:
            related.add(match_id)

        for rid in kb_data.get("relevant_matches", []):
            if isinstance(rid, str) and rid:
                related.add(rid)

        kb_citation = rca_data.get("kb_citation")
        if (
            isinstance(kb_citation, str)
            and kb_citation
            and kb_citation != "null"
        ):
            related.add(kb_citation)

        for rec in resolution_data.get("recommendations", []):
            prior = rec.get("based_on_prior_incident")
            if (
                isinstance(prior, str)
                and prior
                and prior != "null"
            ):
                related.add(prior)

        return sorted(related)

    # ── LLM documentation generation ───────────────────────

    def _generate_documentation(
        self,
        rca_data: dict[str, Any],
        kb_data: dict[str, Any],
        impact_data: dict[str, Any],
        signal_data: dict[str, Any],
        resolution_data: dict[str, Any],
        related: list[str],
    ) -> dict[str, Any]:
        """Generate documentation via LLM or fallback."""
        messages = self._build_messages(
            rca_data, kb_data, impact_data,
            signal_data, resolution_data, related,
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
            logger.warning(
                "LLM documentation synthesis failed: %s", exc
            )
            return self._fallback_documentation(
                rca_data, signal_data, resolution_data,
                model_name,
            )

        try:
            parsed = _parse_response(raw)
        except (json.JSONDecodeError, ValueError):
            logger.warning(
                "Failed to parse LLM documentation response"
            )
            return self._fallback_documentation(
                rca_data, signal_data, resolution_data,
                model_name,
            )

        title = parsed.get("title", "")
        if not isinstance(title, str) or not title:
            title = (
                f"{self.context.condition}"
                f" - {self.context.service}"
            )

        summary = parsed.get("summary", "")
        if not isinstance(summary, str) or not summary:
            summary = self._build_fallback_summary(
                rca_data, signal_data
            )

        root_cause = parsed.get("root_cause", "")
        if not isinstance(root_cause, str):
            root_cause = ""

        resolution = parsed.get("resolution", "")
        if not isinstance(resolution, str):
            resolution = ""

        signals_summary = parsed.get("signals_summary", "")
        if not isinstance(signals_summary, str):
            signals_summary = ""

        confidence_overview = parsed.get(
            "confidence_overview", ""
        )
        if not isinstance(confidence_overview, str):
            confidence_overview = ""

        key_findings = parsed.get("key_findings", [])
        if not isinstance(key_findings, list):
            key_findings = []
        key_findings = [
            str(f) for f in key_findings
            if isinstance(f, str) and f
        ]

        return {
            "title": title,
            "summary": summary,
            "root_cause": root_cause,
            "resolution": resolution,
            "signals_summary": signals_summary,
            "confidence_overview": confidence_overview,
            "key_findings": key_findings,
            "synthesis_source": "llm",
            "doc_model_tier": "standard",
            "doc_model_used": model_name,
        }

    def _fallback_documentation(
        self,
        rca_data: dict[str, Any],
        signal_data: dict[str, Any],
        resolution_data: dict[str, Any],
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Generate documentation from raw metadata."""
        title = (
            f"{self.context.condition}"
            f" - {self.context.service}"
        )
        summary = self._build_fallback_summary(
            rca_data, signal_data
        )
        root_cause = rca_data.get(
            "root_cause_hypothesis", ""
        )

        recs = resolution_data.get("recommendations", [])
        if recs:
            actions = [
                r.get("action", "")
                for r in recs if r.get("action")
            ]
            resolution = "; ".join(actions[:3])
        else:
            resolution = ""

        signals_summary = signal_data.get(
            "signal_summary", ""
        )

        confidence = rca_data.get(
            "confidence_level", "unknown"
        )
        pct = rca_data.get("confidence_percentage")
        if pct is not None:
            confidence_overview = (
                f"RCA confidence: {confidence} ({pct}%)"
            )
        else:
            confidence_overview = (
                f"RCA confidence: {confidence}"
            )

        return {
            "title": title,
            "summary": summary,
            "root_cause": root_cause,
            "resolution": resolution,
            "signals_summary": signals_summary,
            "confidence_overview": confidence_overview,
            "key_findings": [],
            "synthesis_source": "fallback",
            "doc_model_tier": "standard" if model_name else "none",
            "doc_model_used": model_name,
        }

    def _build_fallback_summary(
        self,
        rca_data: dict[str, Any],
        signal_data: dict[str, Any],
    ) -> str:
        """Build summary from raw metadata."""
        parts: list[str] = []
        parts.append(
            f"Investigation of {self.context.condition}"
            f" for service {self.context.service}"
            f" (severity: {self.context.severity})."
        )
        hypothesis = rca_data.get(
            "root_cause_hypothesis", ""
        )
        if hypothesis:
            parts.append(f"Root cause: {hypothesis}.")
        sig = signal_data.get("signal_summary", "")
        if sig:
            parts.append(f"Signals: {sig}.")
        return " ".join(parts)

    # ── Prompt building ─────────────────────────────────────

    def _build_messages(
        self,
        rca_data: dict[str, Any],
        kb_data: dict[str, Any],
        impact_data: dict[str, Any],
        signal_data: dict[str, Any],
        resolution_data: dict[str, Any],
        related: list[str],
    ) -> list[dict[str, str]]:
        impact_val = impact_data.get("customer_impacting")
        reasoning = impact_data.get("reasoning", "")
        if impact_val is None:
            impact_summary = "Unknown"
        else:
            impact_summary = (
                f"{impact_val}. {reasoning}".strip()
            )

        hypothesis = (
            rca_data.get("root_cause_hypothesis")
            or "No RCA hypothesis available"
        )
        confidence = rca_data.get(
            "confidence_level", "unknown"
        )
        percentage = rca_data.get("confidence_percentage")
        pct_str = (
            str(percentage) if percentage is not None
            else "N/A"
        )

        evidence = rca_data.get("supporting_evidence", [])
        evidence_str = (
            "\n".join(f"- {e}" for e in evidence)
            if evidence
            else "No supporting evidence"
        )

        recs = resolution_data.get("recommendations", [])
        if recs:
            rec_lines: list[str] = []
            for r in recs[:5]:
                action = r.get("action", "")
                conf = r.get("confidence", "")
                rec_lines.append(f"- {action} ({conf})")
            resolution_summary = "\n".join(rec_lines)
        else:
            resolution_summary = "No recommendations"

        prior = kb_data.get(
            "prior_research_summary", ""
        )
        if not prior:
            prior = "No prior research available"

        related_str = (
            ", ".join(related) if related else "None"
        )

        sig_summary = (
            signal_data.get("signal_summary")
            or "No signal data available"
        )

        user_content = _DOC_USER_TEMPLATE.format(
            investigation_id=(
                self.context.investigation_id
            ),
            condition=self.context.condition,
            service=self.context.service,
            severity=self.context.severity,
            impact_summary=impact_summary,
            rca_hypothesis=hypothesis,
            rca_confidence=confidence,
            rca_percentage=pct_str,
            supporting_evidence=evidence_str,
            resolution_summary=resolution_summary,
            prior_research=prior,
            signal_summary=sig_summary,
            related_ids=related_str,
        )

        return [
            {"role": "system", "content": _DOC_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    # ── Embedding generation ────────────────────────────────

    def _generate_embedding(
        self, summary_text: str
    ) -> tuple[list[float], bool]:
        """Generate embedding vector from summary text.

        Returns:
            Tuple of (embedding_vector, success_flag).
        """
        if not summary_text:
            return [0.0] * _DEFAULT_VECTOR_DIM, False

        try:
            embedding = self.llm_client.embed_sync(
                summary_text
            )
            return embedding, True
        except Exception as exc:
            logger.warning(
                "Embedding generation failed: %s", exc
            )
            return [0.0] * _DEFAULT_VECTOR_DIM, False

    # ── Knowledge entry payload ─────────────────────────────

    def _build_payload(
        self,
        entry_id: str,
        doc: dict[str, Any],
        rca_data: dict[str, Any],
        resolution_data: dict[str, Any],
        impact_data: dict[str, Any],
        related: list[str],
    ) -> dict[str, Any]:
        return {
            "entry_id": entry_id,
            "entry_type": "investigation",
            "investigation_id": (
                self.context.investigation_id
            ),
            "service": self.context.service,
            "condition": self.context.condition,
            "severity": self.context.severity,
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "title": doc["title"],
            "summary": doc["summary"],
            "root_cause": doc.get("root_cause", ""),
            "resolution": doc.get("resolution", ""),
            "confidence_level": rca_data.get(
                "confidence_level", "unknown"
            ),
            "confidence_percentage": rca_data.get(
                "confidence_percentage"
            ),
            "signals_summary": doc.get(
                "signals_summary", ""
            ),
            "key_findings": doc.get("key_findings", []),
            "recommendations": resolution_data.get(
                "recommendations", []
            ),
            "related_investigations": related,
            "customer_impacting": impact_data.get(
                "customer_impacting"
            ),
        }

    # ── Persistence with retry ──────────────────────────────

    def _persist_entry(
        self,
        entry_id: str,
        payload: dict[str, Any],
        embedding: list[float],
    ) -> tuple[bool, bool, str | None]:
        """Persist KB entry with retry and buffering.

        Returns:
            Tuple of (persisted, buffered, buffer_path).
        """
        point = PointStruct(
            id=entry_id,
            vector=embedding,
            payload=payload,
        )

        for attempt in range(_MAX_RETRIES):
            try:
                self.kb_client.client.upsert(
                    KNOWLEDGE_COLLECTION, [point]
                )
                logger.info(
                    "Persisted investigation documentation"
                    " to knowledge collection"
                )
                self._cleanup_buffer()
                return True, False, None
            except Exception as exc:
                logger.warning(
                    "KB write attempt %d/%d failed: %s",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                )
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_RETRY_DELAYS[attempt])

        buffer_path = self._buffer_to_file(
            payload, embedding
        )
        return False, buffer_path is not None, buffer_path

    def _buffer_to_file(
        self,
        payload: dict[str, Any],
        embedding: list[float],
    ) -> str | None:
        """Write failed KB entry to local buffer file."""
        buffer_dir = os.environ.get(
            "BEEPER_BUFFER_DIR", _DEFAULT_BUFFER_DIR
        )
        try:
            os.makedirs(buffer_dir, exist_ok=True)
            buffer_path = os.path.join(
                buffer_dir,
                f"{self.context.investigation_id}.json",
            )
            buffer_data = {
                "payload": payload,
                "embedding": embedding,
                "collection": KNOWLEDGE_COLLECTION,
                "buffered_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            }
            with open(buffer_path, "w") as f:
                json.dump(buffer_data, f)
            logger.warning(
                "Buffered investigation documentation"
                " to %s",
                buffer_path,
            )
            return buffer_path
        except Exception as exc:
            logger.error(
                "Failed to buffer investigation"
                " documentation: %s",
                exc,
            )
            return None

    def _cleanup_buffer(self) -> None:
        """Remove buffer file if it exists."""
        buffer_dir = os.environ.get(
            "BEEPER_BUFFER_DIR", _DEFAULT_BUFFER_DIR
        )
        buffer_path = os.path.join(
            buffer_dir,
            f"{self.context.investigation_id}.json",
        )
        try:
            if os.path.exists(buffer_path):
                os.remove(buffer_path)
                logger.info(
                    "Cleaned up buffer file %s",
                    buffer_path,
                )
        except Exception as exc:
            logger.warning(
                "Failed to clean up buffer file: %s",
                exc,
            )
