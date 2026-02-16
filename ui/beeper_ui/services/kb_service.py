"""Knowledge Base service for Beeper UI.

This module provides high-level operations for interacting with the
Knowledge Base stored in Qdrant.
"""

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    DatetimeRange,
    Direction,
    FieldCondition,
    Filter,
    MatchValue,
    OrderBy,
    PointStruct,
    Range,
)

from beeper_ui.services.embedding_service import EmbeddingService, EmbeddingServiceError

logger = logging.getLogger(__name__)

# Collection name (must match init-collections.py)
KNOWLEDGE_COLLECTION = "knowledge"

# Maximum entries to scan for filter metadata (services, types)
# Note: If KB grows beyond this, filter dropdowns may be incomplete
MAX_FILTER_METADATA_ENTRIES = 1000


def parse_date_range(date_range: str) -> tuple[Optional[datetime], Optional[datetime]]:
    """Parse a date range string into start and end datetimes.

    Args:
        date_range: Date range string (e.g., 'today', '7d', '30d', '90d')

    Returns:
        Tuple of (date_from, date_to) in UTC. Returns (None, None) for empty/invalid input.
    """
    if not date_range:
        return None, None

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    if date_range == "today":
        return today_start, today_end
    elif date_range == "7d":
        return today_start - timedelta(days=7), today_end
    elif date_range == "30d":
        return today_start - timedelta(days=30), today_end
    elif date_range == "90d":
        return today_start - timedelta(days=90), today_end
    else:
        logger.warning(f"Unknown date range: {date_range}")
        return None, None


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
        # Filter metadata caches
        self._services_cache: Optional[list[str]] = None
        self._entry_types_cache: Optional[list[str]] = None

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
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> list[KBEntry]:
        """List recent KB entries with optional filtering.

        Args:
            limit: Maximum number of entries to return
            entry_type: Optional filter by entry type (runbook, investigation, correction)
            service: Optional filter by service name
            date_from: Optional start of date range (inclusive)
            date_to: Optional end of date range (inclusive)

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

            # Add date range filter
            date_filter = self._build_date_filter(date_from, date_to)
            if date_filter:
                conditions.append(date_filter)

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

        Results are cached to avoid repeated Qdrant queries.
        Use clear_filter_cache() to force refresh.

        Returns:
            List of unique service names (sorted).

        Raises:
            KBServiceError: If the query fails.
        """
        # Return cached result if available
        if self._services_cache is not None:
            return self._services_cache

        try:
            # Get all entries and extract unique services
            # Note: In a production system, this should use Qdrant's
            # aggregation capabilities or a separate index
            results, _ = self.client.scroll(
                collection_name=KNOWLEDGE_COLLECTION,
                limit=MAX_FILTER_METADATA_ENTRIES,
                with_payload=["service"],
                with_vectors=False,
            )

            services = set()
            for point in results:
                if point.payload and point.payload.get("service"):
                    services.add(point.payload["service"])

            self._services_cache = sorted(services)
            return self._services_cache

        except UnexpectedResponse as e:
            logger.error(f"Qdrant query failed: {e}")
            raise KBServiceError(f"Failed to get services: {e}") from e
        except Exception as e:
            logger.error(f"KB service error: {e}")
            raise KBServiceError(f"Failed to get services: {e}") from e

    def get_entry_types(self) -> list[str]:
        """Get list of entry types in the KB.

        Returns known entry types. Results are cached.
        Use clear_filter_cache() to force refresh.

        Returns:
            List of entry types (sorted).
        """
        # Return cached result if available
        if self._entry_types_cache is not None:
            return self._entry_types_cache

        # Known entry types (always included)
        known_types = {"investigation", "runbook", "correction"}

        # For MVP, return known types. In future, could query Qdrant
        # for additional dynamic types.
        self._entry_types_cache = sorted(known_types)
        return self._entry_types_cache

    def clear_filter_cache(self) -> None:
        """Clear cached filter metadata.

        Call this method when KB data changes and filter options
        need to be refreshed.
        """
        self._services_cache = None
        self._entry_types_cache = None
        logger.debug("Filter metadata cache cleared")

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

    def _build_date_filter(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> Optional[FieldCondition]:
        """Build a date range filter for created_at field.

        Args:
            date_from: Start of date range (inclusive)
            date_to: End of date range (inclusive)

        Returns:
            FieldCondition for date range, or None if no dates provided.
        """
        if not date_from and not date_to:
            return None

        # Build the range filter
        range_params: dict[str, datetime] = {}
        if date_from:
            range_params["gte"] = date_from
        if date_to:
            range_params["lte"] = date_to

        return FieldCondition(
            key="created_at",
            range=DatetimeRange(**range_params),
        )

    def search_semantic(
        self,
        query: str,
        limit: int = 10,
        entry_type: Optional[str] = None,
        service: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
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
            date_from: Optional start of date range (inclusive)
            date_to: Optional end of date range (inclusive)
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

            # Add date range filter
            date_filter = self._build_date_filter(date_from, date_to)
            if date_filter:
                conditions.append(date_filter)

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

    def create_entry(
        self,
        title: str,
        content: str,
        entry_type: str,
        service: Optional[str] = None,
        tags: Optional[list[str]] = None,
        author: Optional[str] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ) -> str:
        """Create a new KB entry.

        Args:
            title: Entry title
            content: Entry content (markdown)
            entry_type: Type of entry (runbook, investigation, correction)
            service: Optional service name
            tags: Optional list of tags
            author: Optional author name
            embedding_service: EmbeddingService instance for generating embeddings

        Returns:
            The entry_id of the created entry.

        Raises:
            KBServiceError: If the creation fails.
        """
        try:
            # Generate entry_id
            entry_id = f"kb-{uuid.uuid4().hex[:12]}"
            point_id = str(uuid.uuid4())

            # Get or create embedding service
            if embedding_service is None:
                embedding_service = EmbeddingService()

            # Generate embedding from title + content
            text_for_embedding = f"{title}\n\n{content}"
            try:
                embedding_vector = embedding_service.get_embedding(text_for_embedding)
            except EmbeddingServiceError as e:
                logger.error(f"Failed to generate embedding: {e}")
                raise KBServiceError(f"Failed to create KB entry: {e}") from e

            # Create timestamp
            now = datetime.now(timezone.utc)

            # Build payload
            payload = {
                "entry_id": entry_id,
                "entry_type": entry_type,
                "title": title,
                "content": content,
                "service": service,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "author": author or "import",
                "version": 1,
                "tags": tags or [],
            }

            # Create point
            point = PointStruct(
                id=point_id,
                vector=embedding_vector,
                payload=payload,
            )

            # Upsert to Qdrant
            self.client.upsert(
                collection_name=KNOWLEDGE_COLLECTION,
                points=[point],
            )

            # Clear services cache since a new service might have been added
            self.clear_filter_cache()

            logger.info(f"Created KB entry: {entry_id} (type={entry_type}, service={service})")
            return entry_id

        except KBServiceError:
            raise
        except UnexpectedResponse as e:
            logger.error(f"Qdrant upsert failed: {e}")
            raise KBServiceError(f"Failed to create KB entry: {e}") from e
        except Exception as e:
            logger.error(f"KB service error: {e}")
            raise KBServiceError(f"Failed to create KB entry: {e}") from e

    def check_duplicate(
        self,
        title: str,
        service: Optional[str],
        entry_type: str,
    ) -> Optional[KBEntry]:
        """Check if a similar entry already exists.

        Checks for case-insensitive title match within the same service and type.

        Args:
            title: Entry title to check
            service: Service name (can be None)
            entry_type: Entry type (runbook, investigation, correction)

        Returns:
            Existing KBEntry if duplicate found, None otherwise.

        Raises:
            KBServiceError: If the query fails.
        """
        try:
            # Build filter conditions
            conditions = [
                FieldCondition(key="entry_type", match=MatchValue(value=entry_type)),
            ]
            if service:
                conditions.append(
                    FieldCondition(key="service", match=MatchValue(value=service))
                )

            # Query for entries with matching type and service
            results, _ = self.client.scroll(
                collection_name=KNOWLEDGE_COLLECTION,
                scroll_filter=Filter(must=conditions),
                limit=100,
                with_payload=True,
                with_vectors=False,
            )

            # Check for case-insensitive title match
            title_lower = title.lower()
            for point in results:
                if point.payload:
                    existing_title = point.payload.get("title", "")
                    if existing_title.lower() == title_lower:
                        return KBEntry.from_qdrant(point.id, point.payload)

            return None

        except UnexpectedResponse as e:
            logger.error(f"Qdrant query failed: {e}")
            raise KBServiceError(f"Failed to check duplicate: {e}") from e
        except Exception as e:
            logger.error(f"KB service error: {e}")
            raise KBServiceError(f"Failed to check duplicate: {e}") from e

    def update_entry(
        self,
        entry_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        service: Optional[str] = None,
        tags: Optional[list[str]] = None,
        author: Optional[str] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ) -> int:
        """Update an existing KB entry, incrementing its version.

        Args:
            entry_id: The entry_id of the entry to update
            title: New title (optional, keeps existing if not provided)
            content: New content (optional, keeps existing if not provided)
            service: New service (optional, keeps existing if not provided)
            tags: New tags (optional, keeps existing if not provided)
            author: Author of this update
            embedding_service: EmbeddingService instance for generating embeddings

        Returns:
            The new version number.

        Raises:
            KBServiceError: If the entry is not found or update fails.
        """
        try:
            # Get existing entry
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
                raise KBServiceError(f"Entry not found: {entry_id}")

            existing_point = results[0]
            existing_payload = existing_point.payload or {}

            # Calculate new version
            current_version = existing_payload.get("version", 1)
            new_version = current_version + 1

            # Merge fields
            new_title = title if title is not None else existing_payload.get("title", "")
            new_content = content if content is not None else existing_payload.get("content", "")
            new_service = service if service is not None else existing_payload.get("service")
            new_tags = tags if tags is not None else existing_payload.get("tags", [])

            # Get or create embedding service
            if embedding_service is None:
                embedding_service = EmbeddingService()

            # Generate new embedding
            text_for_embedding = f"{new_title}\n\n{new_content}"
            try:
                embedding_vector = embedding_service.get_embedding(text_for_embedding)
            except EmbeddingServiceError as e:
                logger.error(f"Failed to generate embedding: {e}")
                raise KBServiceError(f"Failed to update KB entry: {e}") from e

            # Create updated payload
            now = datetime.now(timezone.utc)
            payload = {
                "entry_id": entry_id,
                "entry_type": existing_payload.get("entry_type", "unknown"),
                "title": new_title,
                "content": new_content,
                "service": new_service,
                "created_at": existing_payload.get("created_at", now.isoformat()),
                "updated_at": now.isoformat(),
                "author": author or existing_payload.get("author"),
                "version": new_version,
                "tags": new_tags,
            }

            # Create new point with same ID to replace
            point = PointStruct(
                id=str(existing_point.id),
                vector=embedding_vector,
                payload=payload,
            )

            # Upsert to Qdrant
            self.client.upsert(
                collection_name=KNOWLEDGE_COLLECTION,
                points=[point],
            )

            # Clear services cache in case service changed
            self.clear_filter_cache()

            logger.info(f"Updated KB entry: {entry_id} (version={new_version})")
            return new_version

        except KBServiceError:
            raise
        except UnexpectedResponse as e:
            logger.error(f"Qdrant upsert failed: {e}")
            raise KBServiceError(f"Failed to update KB entry: {e}") from e
        except Exception as e:
            logger.error(f"KB service error: {e}")
            raise KBServiceError(f"Failed to update KB entry: {e}") from e
