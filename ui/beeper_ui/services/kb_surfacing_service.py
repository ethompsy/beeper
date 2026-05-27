"""KB Surfacing service for live investigation knowledge surfacing.

Composes KBService and EmbeddingService to semantically search for relevant
KB entries during live investigations, rank them by composite score
(relevance * validation weight), and record relevance feedback.
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from beeper_ui.services.embedding_service import EmbeddingService, EmbeddingServiceError
from beeper_ui.services.kb_service import KBEntry, KBService, KBServiceError

logger = logging.getLogger(__name__)

INVESTIGATIONS_COLLECTION = "investigations"

# Validation status weights for composite ranking
# Normalized multipliers: proven (1.0) > human-confirmed (0.9) > corrected (0.8)
# > AI-generated (0.6)
VALIDATION_WEIGHTS: dict[str, float] = {
    "proven": 1.0,
    "human-confirmed": 0.9,
    "corrected": 0.8,
    "AI-generated": 0.6,
}
DEFAULT_VALIDATION_WEIGHT = 0.6

# Maximum query length for semantic search
MAX_QUERY_LENGTH = 500


@dataclass
class KBSurfacingResult:
    """Result of KB entry surfacing for an investigation."""

    entries: list[dict] = field(default_factory=list)
    is_novel: bool = False
    query_text: str = ""
    investigation_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "entries": self.entries,
            "is_novel": self.is_novel,
            "query_text": self.query_text,
            "investigation_id": self.investigation_id,
        }


class KBSurfacingService:
    """Service for surfacing relevant KB entries during live investigations.

    Composes KBService for semantic search and records relevance feedback
    in the investigation's Qdrant payload.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        embedding_api_key: Optional[str] = None,
    ) -> None:
        """Initialize the KB surfacing service.

        Args:
            host: Qdrant server host (defaults to QDRANT_HOST env or localhost)
            port: Qdrant HTTP port (defaults to QDRANT_PORT env or 6333)
            embedding_api_key: API key for embedding service (defaults to OPENAI_API_KEY env)
        """
        self._host = host or os.getenv("QDRANT_HOST", "localhost")
        self._port = port or int(os.getenv("QDRANT_PORT", "6333"))
        self._embedding_api_key = embedding_api_key
        self._kb_service: Optional[KBService] = None
        self._embedding_service: Optional[EmbeddingService] = None
        self._qdrant_client: Optional[QdrantClient] = None

    @property
    def kb_service(self) -> KBService:
        """Get or create KBService (lazy initialization)."""
        if self._kb_service is None:
            self._kb_service = KBService(host=self._host, port=self._port)
        return self._kb_service

    @property
    def embedding_service(self) -> EmbeddingService:
        """Get or create EmbeddingService (lazy initialization)."""
        if self._embedding_service is None:
            self._embedding_service = EmbeddingService(
                api_key=self._embedding_api_key
            )
        return self._embedding_service

    @property
    def qdrant_client(self) -> QdrantClient:
        """Get or create the Qdrant client (lazy initialization)."""
        if self._qdrant_client is None:
            self._qdrant_client = QdrantClient(
                host=self._host, port=self._port
            )
        return self._qdrant_client

    def surface_entries(
        self, investigation_id: str, findings: dict[str, Any]
    ) -> KBSurfacingResult:
        """Surface semantically relevant KB entries for an investigation.

        Composes a query from investigation findings, performs semantic search,
        and ranks results by composite score (relevance * validation weight).

        Args:
            investigation_id: The investigation ID.
            findings: Investigation findings dict from Qdrant.

        Returns:
            KBSurfacingResult with ranked entries and novel issue flag.
        """
        query_text = self._compose_query(findings)
        result = KBSurfacingResult(
            investigation_id=investigation_id,
            query_text=query_text,
        )

        if not query_text:
            result.is_novel = True
            return result

        entries: list[KBEntry] = []
        try:
            entries, _ = self.kb_service.search_semantic(
                query=query_text,
                limit=10,
                score_threshold=0.4,
                embedding_service=self.embedding_service,
            )
        except (KBServiceError, EmbeddingServiceError):
            logger.warning(
                "Semantic search failed for investigation %s, "
                "falling back to service-based listing",
                investigation_id,
                exc_info=True,
            )
            # Fallback to service-based listing
            try:
                service_name = findings.get("service", "")
                if service_name:
                    entries = self.kb_service.list_entries_by_service(
                        service_name, limit=10
                    )
            except KBServiceError:
                logger.warning(
                    "Service-based KB listing also failed for %s",
                    investigation_id,
                    exc_info=True,
                )

        if not entries:
            result.is_novel = True
            return result

        # Build ranked entry dicts
        ranked = []
        for entry in entries:
            validation_status = self._derive_validation_status(entry)
            validation_weight = self._compute_validation_weight(validation_status)
            relevance = entry.relevance_score if entry.relevance_score is not None else 0.0
            composite_score = relevance * validation_weight

            ranked.append({
                "id": entry.id,
                "entry_id": entry.entry_id,
                "title": entry.title,
                "content_preview": (entry.content or "")[:150],
                "entry_type": entry.entry_type,
                "service": entry.service,
                "validation_status": validation_status,
                "relevance_score": relevance,
                "composite_score": composite_score,
                "created_at": entry.created_at.strftime("%Y-%m-%d") if entry.created_at else "",
                "link": f"/knowledge/{entry.entry_id}",
            })

        # Sort by composite score descending
        ranked.sort(key=lambda e: e["composite_score"], reverse=True)
        result.entries = ranked
        return result

    def _compose_query(self, findings: dict[str, Any]) -> str:
        """Build a semantic search query from investigation findings.

        Extracts key symptoms and context from the findings dict to compose
        a natural language query for KB semantic search.

        Args:
            findings: Investigation findings dict.

        Returns:
            Query string, capped at MAX_QUERY_LENGTH characters.
        """
        if not findings:
            return ""

        parts = []
        for key in (
            "root_cause_hypothesis",
            "prior_research_summary",
            "signal_summary",
            "condition",
            "severity",
        ):
            value = findings.get(key, "")
            if value and isinstance(value, str):
                parts.append(value)

        query = " ".join(parts).strip()
        return query[:MAX_QUERY_LENGTH]

    @staticmethod
    def _derive_validation_status(entry: KBEntry) -> str:
        """Derive validation status from a KB entry.

        Uses the entry's validation_status field directly if set.
        Falls back to entry_type-based derivation for legacy entries
        without an explicit validation_status.

        Args:
            entry: The KB entry.

        Returns:
            One of: 'proven', 'human-confirmed', 'corrected', 'AI-generated'.
        """
        if entry.validation_status:
            return entry.validation_status
        if entry.entry_type == "proven_fix":
            return "proven"
        if entry.entry_type == "correction":
            return "human-confirmed"
        return "AI-generated"

    @staticmethod
    def _compute_validation_weight(validation_status: Optional[str]) -> float:
        """Compute weight multiplier for a validation status.

        Args:
            validation_status: The validation status string.

        Returns:
            Weight multiplier (proven=1.0, human-confirmed=0.9, corrected=0.8, AI-generated=0.6).
        """
        if validation_status is None:
            return DEFAULT_VALIDATION_WEIGHT
        return VALIDATION_WEIGHTS.get(validation_status, DEFAULT_VALIDATION_WEIGHT)

    def record_relevance_feedback(
        self,
        investigation_id: str,
        entry_id: str,
        is_relevant: bool,
        user: str,
    ) -> bool:
        """Record KB relevance feedback for an investigation.

        Stores feedback in the investigation's Qdrant payload under
        the 'kb_relevance_feedback' key.

        Args:
            investigation_id: The investigation ID.
            entry_id: The KB entry ID being rated.
            is_relevant: Whether the entry was relevant.
            user: The user providing feedback.

        Returns:
            True on success, False on failure.
        """
        try:
            # Fetch the investigation point from Qdrant
            results, _ = self.qdrant_client.scroll(
                collection_name=INVESTIGATIONS_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="investigation_id",
                            match=MatchValue(value=investigation_id),
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if not results:
                logger.warning(
                    "No Qdrant record for investigation %s, "
                    "cannot store KB relevance feedback",
                    investigation_id,
                )
                return False

            point_id = results[0].id
            existing_payload = dict(results[0].payload or {})
            feedback = existing_payload.get("kb_relevance_feedback", {})

            feedback[entry_id] = {
                "is_relevant": is_relevant,
                "user": user,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            self.qdrant_client.set_payload(
                collection_name=INVESTIGATIONS_COLLECTION,
                payload={"kb_relevance_feedback": feedback},
                points=[point_id],
            )
            return True
        except Exception:
            logger.warning(
                "Failed to record KB relevance feedback for %s",
                investigation_id,
                exc_info=True,
            )
            return False

    def mark_novel_investigation(self, investigation_id: str) -> bool:
        """Mark an investigation as a novel issue candidate.

        Sets 'novel_issue_candidate: true' in the investigation's
        Qdrant payload for future KB entry creation.

        Args:
            investigation_id: The investigation ID.

        Returns:
            True on success, False on failure.
        """
        try:
            results, _ = self.qdrant_client.scroll(
                collection_name=INVESTIGATIONS_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="investigation_id",
                            match=MatchValue(value=investigation_id),
                        )
                    ]
                ),
                limit=1,
                with_payload=False,
                with_vectors=False,
            )
            if not results:
                logger.warning(
                    "No Qdrant record for investigation %s, "
                    "cannot mark as novel",
                    investigation_id,
                )
                return False

            point_id = results[0].id
            self.qdrant_client.set_payload(
                collection_name=INVESTIGATIONS_COLLECTION,
                payload={"novel_issue_candidate": True},
                points=[point_id],
            )
            return True
        except Exception:
            logger.warning(
                "Failed to mark investigation %s as novel",
                investigation_id,
                exc_info=True,
            )
            return False

    def close(self) -> None:
        """Close internal service connections."""
        try:
            if self._kb_service is not None:
                self._kb_service.close()
        except Exception:
            logger.warning("Failed to close KBService", exc_info=True)
        finally:
            self._kb_service = None
            if self._qdrant_client is not None:
                try:
                    self._qdrant_client.close()
                except Exception:
                    logger.warning("Failed to close Qdrant client", exc_info=True)
                self._qdrant_client = None
            self._embedding_service = None
