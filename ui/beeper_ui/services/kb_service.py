"""Knowledge Base service for Beeper UI.

This module provides high-level operations for interacting with the
Knowledge Base stored in Qdrant.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Direction, FieldCondition, Filter, MatchValue, OrderBy

from beeper_ui.services.embedding_service import EmbeddingService, EmbeddingServiceError

logger = logging.getLogger(__name__)

# Collection name (must match init-collections.py)
KNOWLEDGE_COLLECTION = "knowledge"


@dataclass
class KBEntry:
    """Represents a Knowledge Base entry."""

    id: str
    entry_id: str
    entry_type: str
    title: str
    content: str
    service: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    author: Optional[str]
    version: int
    tags: list[str]
    relevance_score: Optional[float] = None  # Set during semantic search

    @classmethod
    def from_qdrant(cls, point_id: str | int | UUID, payload: dict[str, Any]) -> "KBEntry":
        """Create KBEntry from Qdrant point payload."""
        created_at = None
        if payload.get("created_at"):
            try:
                created_at = datetime.fromisoformat(
                    payload["created_at"].replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        updated_at = None
        if payload.get("updated_at"):
            try:
                updated_at = datetime.fromisoformat(
                    payload["updated_at"].replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        return cls(
            id=str(point_id),
            entry_id=payload.get("entry_id", str(point_id)),
            entry_type=payload.get("entry_type", "unknown"),
            title=payload.get("title", "Untitled"),
            content=payload.get("content", ""),
            service=payload.get("service"),
            created_at=created_at,
            updated_at=updated_at,
            author=payload.get("author"),
            version=payload.get("version", 1),
            tags=payload.get("tags", []),
        )


class KBServiceError(Exception):
    """Exception raised by KB service operations."""

    pass


class KBService:
    """Service for Knowledge Base operations."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        """Initialize the KB service.

        Args:
            host: Qdrant server host (defaults to QDRANT_HOST env or localhost)
            port: Qdrant HTTP port (defaults to QDRANT_PORT env or 6333)
        """
        self.host = host or os.getenv("QDRANT_HOST", "localhost")
        self.port = port or int(os.getenv("QDRANT_PORT", "6333"))
        self._client: Optional[QdrantClient] = None

    @property
    def client(self) -> QdrantClient:
        """Get or create the Qdrant client (lazy initialization)."""
        if self._client is None:
            logger.info(f"Connecting to Qdrant at {self.host}:{self.port}")
            self._client = QdrantClient(host=self.host, port=self.port)
        return self._client

    def list_recent_entries(
        self,
        limit: int = 20,
        entry_type: Optional[str] = None,
        service: Optional[str] = None,
    ) -> list[KBEntry]:
        """List recent KB entries with optional filtering.

        Args:
            limit: Maximum number of entries to return
            entry_type: Optional filter by entry type (runbook, investigation, correction)
            service: Optional filter by service name

        Returns:
            List of KB entries sorted by created_at descending.

        Raises:
            KBServiceError: If the query fails.
        """
        try:
            # Build filter conditions
            conditions = []
            if entry_type:
                conditions.append(
                    FieldCondition(key="entry_type", match=MatchValue(value=entry_type))
                )
            if service:
                conditions.append(
                    FieldCondition(key="service", match=MatchValue(value=service))
                )

            query_filter = Filter(must=conditions) if conditions else None  # type: ignore[arg-type]

            # Use scroll to get entries (no vector needed)
            results, _ = self.client.scroll(
                collection_name=KNOWLEDGE_COLLECTION,
                scroll_filter=query_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
                order_by=OrderBy(key="created_at", direction=Direction.DESC),
            )

            return [KBEntry.from_qdrant(point.id, point.payload or {}) for point in results]

        except UnexpectedResponse as e:
            logger.error(f"Qdrant query failed: {e}")
            raise KBServiceError(f"Failed to list KB entries: {e}") from e
        except Exception as e:
            logger.error(f"KB service error: {e}")
            raise KBServiceError(f"Failed to list KB entries: {e}") from e

    def get_entry(self, entry_id: str) -> Optional[KBEntry]:
        """Get a single KB entry by its entry_id.

        Args:
            entry_id: The unique identifier of the entry

        Returns:
            KBEntry if found, None otherwise.

        Raises:
            KBServiceError: If the query fails.
        """
        try:
            results, _ = self.client.scroll(
                collection_name=KNOWLEDGE_COLLECTION,
                scroll_filter=Filter(
                    must=[FieldCondition(key="entry_id", match=MatchValue(value=entry_id))]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )

            if not results:
                return None

            return KBEntry.from_qdrant(results[0].id, results[0].payload or {})

        except UnexpectedResponse as e:
            logger.error(f"Qdrant query failed: {e}")
            raise KBServiceError(f"Failed to get KB entry: {e}") from e
        except Exception as e:
            logger.error(f"KB service error: {e}")
            raise KBServiceError(f"Failed to get KB entry: {e}") from e

    def list_entries_by_service(
        self,
        service_name: str,
        limit: int = 20,
    ) -> list[KBEntry]:
        """List KB entries filtered by service name.

        Args:
            service_name: The service to filter by
            limit: Maximum number of entries to return

        Returns:
            List of KB entries for the specified service.

        Raises:
            KBServiceError: If the query fails.
        """
        return self.list_recent_entries(limit=limit, service=service_name)

    def list_related_entries(
        self,
        entry_id: str,
        service: Optional[str] = None,
        limit: int = 5,
    ) -> list[KBEntry]:
        """List entries related to a given entry.

        For now, this returns other entries with the same service.
        Future: Could use vector similarity for semantic relatedness.

        Args:
            entry_id: The entry to find related entries for
            service: The service to filter by (if known)
            limit: Maximum number of related entries to return

        Returns:
            List of related KB entries (excluding the original entry).

        Raises:
            KBServiceError: If the query fails.
        """
        try:
            # If service not provided, try to get it from the entry
            if not service:
                entry = self.get_entry(entry_id)
                if entry:
                    service = entry.service

            if not service:
                return []

            # Get entries with same service, excluding the original
            entries = self.list_entries_by_service(service, limit=limit + 1)

            # Filter out the original entry
            return [e for e in entries if e.entry_id != entry_id][:limit]

        except KBServiceError:
            raise
        except Exception as e:
            logger.error(f"KB service error: {e}")
            raise KBServiceError(f"Failed to list related entries: {e}") from e

    def get_available_services(self) -> list[str]:
        """Get list of unique service names in the KB.

        Returns:
            List of unique service names.

        Raises:
            KBServiceError: If the query fails.
        """
        try:
            # Get all entries and extract unique services
            # Note: In a production system, this should use Qdrant's
            # aggregation capabilities or a separate index
            results, _ = self.client.scroll(
                collection_name=KNOWLEDGE_COLLECTION,
                limit=1000,  # Reasonable limit for MVP
                with_payload=["service"],
                with_vectors=False,
            )

            services = set()
            for point in results:
                if point.payload and point.payload.get("service"):
                    services.add(point.payload["service"])

            return sorted(services)

        except UnexpectedResponse as e:
            logger.error(f"Qdrant query failed: {e}")
            raise KBServiceError(f"Failed to get services: {e}") from e
        except Exception as e:
            logger.error(f"KB service error: {e}")
            raise KBServiceError(f"Failed to get services: {e}") from e

    def get_entry_types(self) -> list[str]:
        """Get list of unique entry types in the KB.

        Returns:
            List of unique entry types.
        """
        # Return the known entry types (static for now)
        return ["investigation", "runbook", "correction"]

    def health_check(self) -> bool:
        """Check if Qdrant is healthy and the knowledge collection exists.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            self.client.get_collection(KNOWLEDGE_COLLECTION)
            return True
        except Exception as e:
            logger.error(f"KB health check failed: {e}")
            return False

    def search_semantic(
        self,
        query: str,
        limit: int = 10,
        entry_type: Optional[str] = None,
        service: Optional[str] = None,
        score_threshold: float = 0.5,
        embedding_service: Optional[EmbeddingService] = None,
    ) -> tuple[list["KBEntry"], bool]:
        """Search KB using semantic similarity.

        Uses vector embeddings to find semantically similar entries.

        Args:
            query: Natural language search query
            limit: Maximum number of results to return
            entry_type: Optional filter by entry type
            service: Optional filter by service name
            score_threshold: Minimum cosine similarity score (0.0-1.0)
            embedding_service: Optional EmbeddingService instance (creates one if not provided)

        Returns:
            Tuple of (results, has_exact_matches).
            has_exact_matches is False when best score < 0.7.

        Raises:
            KBServiceError: If the search fails.
        """
        if not query or not query.strip():
            return [], True

        try:
            # Get or create embedding service
            if embedding_service is None:
                embedding_service = EmbeddingService()

            # Generate embedding for the query
            try:
                query_vector = embedding_service.get_embedding(query)
            except EmbeddingServiceError as e:
                logger.error(f"Failed to generate query embedding: {e}")
                raise KBServiceError(f"Search failed: {e}") from e

            # Build filter conditions
            conditions = []
            if entry_type:
                conditions.append(
                    FieldCondition(key="entry_type", match=MatchValue(value=entry_type))
                )
            if service:
                conditions.append(
                    FieldCondition(key="service", match=MatchValue(value=service))
                )

            query_filter = Filter(must=conditions) if conditions else None  # type: ignore[arg-type]

            # Perform vector search
            results = self.client.query_points(
                collection_name=KNOWLEDGE_COLLECTION,
                query=query_vector,
                query_filter=query_filter,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )

            # Convert results to KBEntry objects with relevance scores
            entries: list[KBEntry] = []
            max_score = 0.0

            for point in results.points:
                entry = KBEntry.from_qdrant(point.id, point.payload or {})
                entry.relevance_score = point.score
                entries.append(entry)
                max_score = max(max_score, point.score)

            # Determine if we have "exact" matches (score >= 0.7)
            has_exact_matches = max_score >= 0.7 if entries else True

            logger.debug(
                f"Semantic search for '{query[:50]}...' returned {len(entries)} results "
                f"(max_score={max_score:.2f}, has_exact={has_exact_matches})"
            )

            return entries, has_exact_matches

        except UnexpectedResponse as e:
            logger.error(f"Qdrant vector search failed: {e}")
            raise KBServiceError(f"Search failed: {e}") from e
        except KBServiceError:
            raise
        except Exception as e:
            logger.error(f"KB semantic search error: {e}")
            raise KBServiceError(f"Search failed: {e}") from e
