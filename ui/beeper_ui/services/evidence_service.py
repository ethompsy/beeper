"""Evidence service for structuring investigation evidence with references.

Extracts evidence references from pipeline metadata and structures them
for presentation in the investigation timeline with clickable source links.
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from beeper_ui.services.kb_service import KBEntry, KBService, KBServiceError

logger = logging.getLogger(__name__)

# Valid evidence types (what kind of evidence)
EVIDENCE_TYPES = {"metric", "log", "deploy", "kb", "config_change"}

# Valid source types (where the evidence came from)
SOURCE_TYPES = {"prometheus", "loki", "kb_entry", "git_commit", "config"}


_EVENT_CATEGORY_MAP: dict[str, str] = {
    "metric": "metric_anomaly",
    "log": "log_pattern",
    "deploy": "deploy_event",
    "config_change": "config_change",
    "kb": "kb_reference",
}


@dataclass
class EvidenceReference:
    """A structured evidence reference from an investigation."""

    id: str
    investigation_id: str
    evidence_type: str  # metric, log, deploy, kb, config_change
    title: str
    content_preview: str
    source_ref: str  # Prometheus query, log line, KB entry ID, etc.
    source_type: str  # prometheus, loki, kb_entry, git_commit, config
    timestamp: str  # ISO format
    relevance_score: Optional[float] = None
    validation_status: Optional[str] = None  # proven, AI-generated, human-confirmed
    raw_data: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for template rendering."""
        return asdict(self)


@dataclass
class TimelineEvent:
    """A timeline event wrapping an EvidenceReference with category classification."""

    reference: EvidenceReference
    event_category: str  # metric_anomaly, log_pattern, deploy_event, config_change, kb_reference

    @property
    def id(self) -> str:
        return self.reference.id

    @property
    def investigation_id(self) -> str:
        return self.reference.investigation_id

    @property
    def evidence_type(self) -> str:
        return self.reference.evidence_type

    @property
    def title(self) -> str:
        return self.reference.title

    @property
    def content_preview(self) -> str:
        return self.reference.content_preview

    @property
    def source_ref(self) -> str:
        return self.reference.source_ref

    @property
    def source_type(self) -> str:
        return self.reference.source_type

    @property
    def timestamp(self) -> str:
        return self.reference.timestamp

    @property
    def relevance_score(self) -> Optional[float]:
        return self.reference.relevance_score

    @property
    def validation_status(self) -> Optional[str]:
        return self.reference.validation_status

    @property
    def raw_data(self) -> Optional[str]:
        return self.reference.raw_data

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for template rendering."""
        d = self.reference.to_dict()
        d["event_category"] = self.event_category
        return d


class EvidenceService:
    """Service for extracting and structuring investigation evidence references."""

    def extract_evidence_references(
        self,
        investigation_id: str,
        findings: dict[str, Any],
    ) -> list[EvidenceReference]:
        """Extract structured evidence references from pipeline metadata.

        Parses existing pipeline findings fields into structured EvidenceReference
        objects, ordered chronologically by extraction order (which mirrors
        pipeline step execution order).

        Args:
            investigation_id: The investigation ID.
            findings: Pipeline metadata dict from Qdrant investigations collection.

        Returns:
            List of EvidenceReference objects ordered chronologically.
        """
        if not findings:
            return []

        references: list[EvidenceReference] = []
        ref_index = 0

        # 1. Extract KB match references (from kb_query step)
        ref_index = self._extract_kb_references(
            investigation_id, findings, references, ref_index
        )

        # 2. Extract signal correlation evidence (from signal_correlation step)
        ref_index = self._extract_signal_references(
            investigation_id, findings, references, ref_index
        )

        # 2.5 Extract deploy correlation evidence (from deploy_correlation step)
        ref_index = self._extract_deploy_correlation_references(
            investigation_id, findings, references, ref_index
        )

        # 3. Extract supporting evidence items (from rca_hypothesis step)
        ref_index = self._extract_supporting_evidence(
            investigation_id, findings, references, ref_index
        )

        # 4. Extract KB citation from RCA (from rca_hypothesis step)
        ref_index = self._extract_rca_kb_citation(
            investigation_id, findings, references, ref_index
        )

        # 5. Extract prior incident references from recommendations
        ref_index = self._extract_recommendation_references(
            investigation_id, findings, references, ref_index
        )

        # 6. Extract investigation documentation KB entry
        self._extract_documentation_reference(
            investigation_id, findings, references, ref_index
        )

        return references

    def _extract_kb_references(
        self,
        investigation_id: str,
        findings: dict[str, Any],
        references: list[EvidenceReference],
        ref_index: int,
    ) -> int:
        """Extract KB match references from kb_query step findings."""
        # Exact match
        if findings.get("exact_match_found") and findings.get("exact_match_id"):
            entry_id = str(findings["exact_match_id"])
            references.append(
                EvidenceReference(
                    id=f"ev-{investigation_id}-{ref_index}",
                    investigation_id=investigation_id,
                    evidence_type="kb",
                    title="Exact KB Match",
                    content_preview=findings.get(
                        "prior_research_summary", "Exact match found in knowledge base"
                    )[:200],
                    source_ref=entry_id,
                    source_type="kb_entry",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    relevance_score=1.0,
                    validation_status=None,  # Will be enriched by get_kb_reference_detail
                )
            )
            ref_index += 1

        # Related matches
        relevant_matches = findings.get("relevant_matches", [])
        if isinstance(relevant_matches, list):
            for match in relevant_matches:
                if isinstance(match, str) and ":" in match:
                    match_id = match.split(":")[0].strip()
                    match_desc = match.split(":", 1)[1].strip() if ":" in match else match
                    references.append(
                        EvidenceReference(
                            id=f"ev-{investigation_id}-{ref_index}",
                            investigation_id=investigation_id,
                            evidence_type="kb",
                            title=f"Related KB: {match_id}",
                            content_preview=match_desc[:200],
                            source_ref=match_id,
                            source_type="kb_entry",
                            timestamp=datetime.now(timezone.utc).isoformat(),
                        )
                    )
                    ref_index += 1

        return ref_index

    def _extract_signal_references(
        self,
        investigation_id: str,
        findings: dict[str, Any],
        references: list[EvidenceReference],
        ref_index: int,
    ) -> int:
        """Extract signal correlation evidence from signal_correlation step."""
        layers = findings.get("layers_queried", [])
        signal_summary = findings.get("signal_summary", "")

        if signal_summary and isinstance(layers, list):
            for layer in layers:
                layer_str = str(layer).lower()
                if layer_str == "prometheus":
                    evidence_type = "metric"
                    source_type = "prometheus"
                elif layer_str == "loki":
                    evidence_type = "log"
                    source_type = "loki"
                else:
                    logger.debug("Unknown signal layer %r, defaulting to metric/prometheus", layer_str)
                    evidence_type = "metric"
                    source_type = "prometheus"

                references.append(
                    EvidenceReference(
                        id=f"ev-{investigation_id}-{ref_index}",
                        investigation_id=investigation_id,
                        evidence_type=evidence_type,
                        title=f"Signal: {layer}",
                        content_preview=signal_summary[:200],
                        source_ref=layer_str,
                        source_type=source_type,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        raw_data=signal_summary,
                    )
                )
                ref_index += 1

        # Hypotheses from signal analysis
        hypotheses = findings.get("hypotheses", [])
        if isinstance(hypotheses, list):
            for hyp in hypotheses:
                if isinstance(hyp, str) and hyp.strip():
                    references.append(
                        EvidenceReference(
                            id=f"ev-{investigation_id}-{ref_index}",
                            investigation_id=investigation_id,
                            evidence_type="metric",
                            title="Signal Hypothesis",
                            content_preview=hyp[:200],
                            source_ref="signal_correlation",
                            source_type="prometheus",
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            raw_data=hyp,
                        )
                    )
                    ref_index += 1

        return ref_index

    def _extract_deploy_correlation_references(
        self,
        investigation_id: str,
        findings: dict[str, Any],
        references: list[EvidenceReference],
        ref_index: int,
    ) -> int:
        """Extract deploy correlation evidence from deploy_correlation step."""
        correlations = findings.get("deploy_correlations", [])
        if not isinstance(correlations, list):
            return ref_index

        for corr in correlations:
            if not isinstance(corr, dict):
                continue
            commit_sha = corr.get("commit_sha", "unknown")
            confidence = corr.get("confidence", "unknown")
            sha_short = commit_sha[:7]
            author = corr.get("author", "unknown")
            message = corr.get("message", "")
            timestamp = corr.get("deployment_timestamp", datetime.now(timezone.utc).isoformat())

            references.append(
                EvidenceReference(
                    id=f"ev-{investigation_id}-{ref_index}",
                    investigation_id=investigation_id,
                    evidence_type="deploy",
                    title=f"Deploy Correlation: {sha_short} ({confidence})",
                    content_preview=f"{message} by {author}" if message else f"Commit {sha_short} by {author}",
                    source_ref=commit_sha,
                    source_type="git_commit",
                    timestamp=timestamp,
                    raw_data=json.dumps(corr),
                )
            )
            ref_index += 1

        return ref_index

    def _extract_supporting_evidence(
        self,
        investigation_id: str,
        findings: dict[str, Any],
        references: list[EvidenceReference],
        ref_index: int,
    ) -> int:
        """Extract supporting evidence items from RCA hypothesis step."""
        supporting = findings.get("supporting_evidence", [])
        if isinstance(supporting, list):
            for item in supporting:
                if isinstance(item, str) and item.strip():
                    # Classify the evidence type based on content
                    evidence_type, source_type = self._classify_evidence(item)
                    references.append(
                        EvidenceReference(
                            id=f"ev-{investigation_id}-{ref_index}",
                            investigation_id=investigation_id,
                            evidence_type=evidence_type,
                            title="Supporting Evidence",
                            content_preview=item[:200],
                            source_ref=item[:100],
                            source_type=source_type,
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            raw_data=item,
                        )
                    )
                    ref_index += 1

        return ref_index

    def _extract_rca_kb_citation(
        self,
        investigation_id: str,
        findings: dict[str, Any],
        references: list[EvidenceReference],
        ref_index: int,
    ) -> int:
        """Extract KB citation from RCA hypothesis step."""
        kb_citation = findings.get("kb_citation")
        if kb_citation and isinstance(kb_citation, str):
            # Avoid duplicating if already added as exact match
            existing_kb_refs = [
                r for r in references
                if r.source_type == "kb_entry" and r.source_ref == kb_citation
            ]
            if not existing_kb_refs:
                references.append(
                    EvidenceReference(
                        id=f"ev-{investigation_id}-{ref_index}",
                        investigation_id=investigation_id,
                        evidence_type="kb",
                        title="RCA KB Citation",
                        content_preview=findings.get(
                            "root_cause_hypothesis", "KB entry cited in root cause analysis"
                        )[:200],
                        source_ref=kb_citation,
                        source_type="kb_entry",
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                )
                ref_index += 1

        return ref_index

    def _extract_recommendation_references(
        self,
        investigation_id: str,
        findings: dict[str, Any],
        references: list[EvidenceReference],
        ref_index: int,
    ) -> int:
        """Extract prior incident references from recommendations."""
        recommendations = findings.get("recommendations", [])
        if isinstance(recommendations, list):
            for rec in recommendations:
                if isinstance(rec, dict):
                    prior = rec.get("based_on_prior_incident")
                    if prior and isinstance(prior, str):
                        existing = [
                            r for r in references
                            if r.source_type == "kb_entry" and r.source_ref == prior
                        ]
                        if not existing:
                            references.append(
                                EvidenceReference(
                                    id=f"ev-{investigation_id}-{ref_index}",
                                    investigation_id=investigation_id,
                                    evidence_type="kb",
                                    title=f"Prior Incident: {prior}",
                                    content_preview=rec.get(
                                        "action", "Based on prior incident"
                                    )[:200],
                                    source_ref=prior,
                                    source_type="kb_entry",
                                    timestamp=datetime.now(timezone.utc).isoformat(),
                                )
                            )
                            ref_index += 1

        return ref_index

    def _extract_documentation_reference(
        self,
        investigation_id: str,
        findings: dict[str, Any],
        references: list[EvidenceReference],
        ref_index: int,
    ) -> int:
        """Extract investigation documentation KB entry reference."""
        kb_entry_id = findings.get("kb_entry_id")
        if kb_entry_id and isinstance(kb_entry_id, str):
            references.append(
                EvidenceReference(
                    id=f"ev-{investigation_id}-{ref_index}",
                    investigation_id=investigation_id,
                    evidence_type="kb",
                    title="Investigation Documentation",
                    content_preview=findings.get(
                        "documentation_summary",
                        findings.get("documentation_title", "Investigation documented in KB"),
                    )[:200],
                    source_ref=kb_entry_id,
                    source_type="kb_entry",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )
            ref_index += 1

        return ref_index

    @staticmethod
    def _classify_evidence(text: str) -> tuple[str, str]:
        """Classify evidence text by type and source.

        Args:
            text: Evidence text content.

        Returns:
            Tuple of (evidence_type, source_type).
        """
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["metric", "prometheus", "promql", "rate(", "sum("]):
            return "metric", "prometheus"
        if any(kw in text_lower for kw in ["log", "loki", "logql", "stderr", "stdout"]):
            return "log", "loki"
        if any(kw in text_lower for kw in ["deploy", "commit", "release", "rollout", "git"]):
            return "deploy", "git_commit"
        if any(kw in text_lower for kw in ["config", "configmap", "env", "setting"]):
            return "config_change", "config"
        if any(kw in text_lower for kw in ["kb", "knowledge", "prior", "incident"]):
            return "kb", "kb_entry"
        return "metric", "prometheus"

    def get_kb_reference_detail(self, entry_id: str) -> dict[str, Any]:
        """Fetch KB entry detail for inline evidence display.

        Args:
            entry_id: The KB entry ID to fetch.

        Returns:
            Dict with entry_id, title, entry_type, validation_status,
            relevance_score, content_preview. Empty dict if not found.
        """
        try:
            kb_svc = KBService()
        except Exception:
            logger.warning("Failed to connect to KB service for %s", entry_id)
            return {}

        try:
            entry = kb_svc.get_entry(entry_id)
            if entry is None:
                return {}
            return {
                "entry_id": entry.entry_id,
                "title": entry.title,
                "entry_type": entry.entry_type,
                "validation_status": self._derive_validation_status(entry),
                "relevance_score": entry.relevance_score,
                "content_preview": (entry.content or "")[:200],
            }
        except KBServiceError:
            logger.warning("Failed to fetch KB reference detail for %s", entry_id)
            return {}
        finally:
            kb_svc.close()

    @staticmethod
    def _derive_validation_status(entry: KBEntry) -> str:
        """Derive validation status from KB entry type and metadata.

        Args:
            entry: The KB entry.

        Returns:
            One of: 'proven', 'human-confirmed', 'AI-generated'.
        """
        if entry.entry_type == "proven_fix":
            return "proven"
        if entry.entry_type == "correction":
            return "human-confirmed"
        return "AI-generated"

    def get_timeline_events(
        self,
        investigation_id: str,
        findings: dict[str, Any],
    ) -> list[TimelineEvent]:
        """Extract and sort evidence as timeline events in chronological order.

        Calls extract_evidence_references(), wraps each in a TimelineEvent with
        an event_category, enriches KB references, and sorts by timestamp.

        Args:
            investigation_id: The investigation ID.
            findings: Pipeline metadata dict from Qdrant investigations collection.

        Returns:
            List of TimelineEvent objects sorted chronologically by timestamp.
        """
        references = self.extract_evidence_references(investigation_id, findings)
        references = self.enrich_kb_references(references)

        events: list[TimelineEvent] = []
        for ref in references:
            category = _EVENT_CATEGORY_MAP.get(ref.evidence_type, "metric_anomaly")
            events.append(TimelineEvent(reference=ref, event_category=category))

        events.sort(key=lambda e: e.timestamp)
        return events

    def enrich_kb_references(
        self, references: list[EvidenceReference]
    ) -> list[EvidenceReference]:
        """Enrich KB-type evidence references with validation status and detail.

        Fetches KB entry details for references with source_type='kb_entry'
        and populates validation_status and relevance_score fields.

        Args:
            references: List of evidence references to enrich.

        Returns:
            The same list with KB references enriched in-place.
        """
        kb_refs = [r for r in references if r.source_type == "kb_entry"]
        if not kb_refs:
            return references

        try:
            kb_svc = KBService()
        except Exception:
            logger.debug("Could not connect to KB service for enrichment")
            return references

        try:
            entry_cache: dict[str, KBEntry | None] = {}
            for ref in kb_refs:
                if ref.source_ref not in entry_cache:
                    try:
                        entry_cache[ref.source_ref] = kb_svc.get_entry(ref.source_ref)
                    except KBServiceError:
                        logger.debug(
                            "Could not enrich KB reference %s", ref.source_ref
                        )
                        entry_cache[ref.source_ref] = None
                entry = entry_cache.get(ref.source_ref)
                if entry:
                    ref.validation_status = self._derive_validation_status(entry)
                    if entry.relevance_score is not None:
                        ref.relevance_score = entry.relevance_score
                    if not ref.content_preview or ref.content_preview == ref.source_ref:
                        ref.content_preview = (entry.content or "")[:200]
        finally:
            kb_svc.close()

        return references


# Module-level singleton
_evidence_service: Optional[EvidenceService] = None


def get_evidence_service() -> EvidenceService:
    """Get the global evidence service instance."""
    global _evidence_service
    if _evidence_service is None:
        _evidence_service = EvidenceService()
    return _evidence_service


def reset_evidence_service() -> None:
    """Reset the global evidence service singleton (for testing)."""
    global _evidence_service
    _evidence_service = None
