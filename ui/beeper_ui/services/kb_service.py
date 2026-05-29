"""Knowledge Base service for Beeper UI.

This module provides high-level operations for interacting with the
Knowledge Base stored in Qdrant.
"""

import difflib
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
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
)

from beeper_ui.services.embedding_service import EmbeddingService, EmbeddingServiceError

logger = logging.getLogger(__name__)

# Collection names (must match init-collections.py)
KNOWLEDGE_COLLECTION = "knowledge"
VERSIONS_COLLECTION = "knowledge_versions"
CORRECTIONS_COLLECTION = "corrections"
LEARNING_PATTERNS_COLLECTION = "learning_patterns"
SERVICE_TRUST_COLLECTION = "service_trust_levels"

# Valid learning pattern categories
LEARNING_CATEGORIES = {
    "missing_context",
    "incorrect_correlation",
    "wrong_conclusion",
    "unnecessary_info",
    "other",
}

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
    auto_published: bool = False
    validation_status: Optional[str] = None  # AI-generated, human-confirmed, proven, corrected
    relevance_score: Optional[float] = None  # Set during semantic search
    # Structured incident detail (FR31). Populated from the payload when the
    # authoring agent / resolution flow records them; otherwise None/empty and
    # the freeform `content` markdown remains the source of truth.
    root_cause: Optional[str] = None
    resolution: Optional[str] = None
    affected_services: list[str] = field(default_factory=list)

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

        # Affected services may arrive as a list or a single string.
        raw_affected = payload.get("affected_services")
        if isinstance(raw_affected, str):
            affected_services = [raw_affected] if raw_affected else []
        elif isinstance(raw_affected, list):
            affected_services = [str(s) for s in raw_affected if s]
        else:
            affected_services = []

        # Resolution prefers explicit notes; falls back to the recorded outcome
        # written by the investigation resolution flow.
        resolution = payload.get("resolution") or payload.get("resolution_notes")
        if not resolution and payload.get("resolution_outcome"):
            resolution = str(payload["resolution_outcome"])

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
            auto_published=payload.get("auto_published", False),
            validation_status=payload.get("validation_status"),
            root_cause=payload.get("root_cause"),
            resolution=resolution or None,
            affected_services=affected_services,
        )


@dataclass
class CorrectionMessage:
    """A single message in a correction conversation."""

    role: str  # "user" or "assistant"
    content: str
    timestamp: str  # ISO 8601


@dataclass
class Correction:
    """Represents a correction conversation for a KB entry."""

    correction_id: str
    entry_id: str
    messages: list[CorrectionMessage]
    status: str  # "pending", "applied", "rejected"
    summary: Optional[str]
    created_at: str  # ISO 8601
    updated_at: str  # ISO 8601

    @classmethod
    def from_qdrant(cls, payload: dict[str, Any]) -> "Correction":
        """Create Correction from Qdrant point payload."""
        messages = [
            CorrectionMessage(
                role=m.get("role", "user"),
                content=m.get("content", ""),
                timestamp=m.get("timestamp", ""),
            )
            for m in payload.get("messages", [])
        ]
        return cls(
            correction_id=payload.get("correction_id", ""),
            entry_id=payload.get("entry_id", ""),
            messages=messages,
            status=payload.get("status", "pending"),
            summary=payload.get("summary"),
            created_at=payload.get("created_at", ""),
            updated_at=payload.get("updated_at", ""),
        )


@dataclass
class LearningPattern:
    """Represents a learned pattern from a correction diff."""

    pattern_id: str
    entry_id: str
    correction_id: str
    service_name: str
    category: str  # missing_context, incorrect_correlation, etc.
    description: str
    original_snippet: str
    corrected_snippet: str
    created_at: str  # ISO 8601

    @classmethod
    def from_qdrant(cls, payload: dict[str, Any]) -> "LearningPattern":
        """Create LearningPattern from Qdrant point payload."""
        return cls(
            pattern_id=payload.get("pattern_id", ""),
            entry_id=payload.get("entry_id", ""),
            correction_id=payload.get("correction_id", ""),
            service_name=payload.get("service_name", "general"),
            category=payload.get("category", "other"),
            description=payload.get("description", ""),
            original_snippet=payload.get("original_snippet", ""),
            corrected_snippet=payload.get("corrected_snippet", ""),
            created_at=payload.get("created_at", ""),
        )


@dataclass
class ServiceTrustLevel:
    """Represents a per-service trust level for Beeper's authoring."""

    service_name: str
    trust_level: str  # "draft" | "trusted"
    accuracy_pct: float
    total_entries: int
    reviewed_entries: int
    correct_entries: int
    last_updated: str  # ISO 8601
    manually_adjusted: bool
    manual_reason: str

    @classmethod
    def from_qdrant(cls, payload: dict[str, Any]) -> "ServiceTrustLevel":
        """Create ServiceTrustLevel from Qdrant point payload."""
        return cls(
            service_name=payload.get("service_name", ""),
            trust_level=payload.get("trust_level", "draft"),
            accuracy_pct=payload.get("accuracy_pct", 0.0),
            total_entries=payload.get("total_entries", 0),
            reviewed_entries=payload.get("reviewed_entries", 0),
            correct_entries=payload.get("correct_entries", 0),
            last_updated=payload.get("last_updated", ""),
            manually_adjusted=payload.get("manually_adjusted", False),
            manual_reason=payload.get("manual_reason", ""),
        )


class KBServiceError(Exception):
    """Exception raised by KB service operations."""

    pass


def generate_diff(old_content: str, new_content: str) -> dict:
    """Generate structured diff data from two content strings.

    Uses Python's difflib.unified_diff to produce line-by-line changes,
    parsed into structured hunks for template rendering.

    Args:
        old_content: Content of the older version
        new_content: Content of the newer version

    Returns:
        Dict with keys: hunks (list of hunk dicts), has_changes (bool), summary (str).
        Each hunk has: header (str), lines (list of line dicts).
        Each line has: type ('add'|'remove'|'context'), content (str),
                       old_num (int|None), new_num (int|None).
    """
    old_lines = old_content.splitlines(keepends=False)
    new_lines = new_content.splitlines(keepends=False)

    diff_output = list(
        difflib.unified_diff(old_lines, new_lines, lineterm="", n=3)
    )

    # No changes
    if not diff_output:
        return {"hunks": [], "has_changes": False, "summary": "No changes"}

    hunks: list[dict] = []
    current_hunk: dict | None = None
    old_num = 0
    new_num = 0
    additions = 0
    deletions = 0

    for i, line in enumerate(diff_output):
        # Skip the first two lines (file headers: --- and +++)
        if i < 2 and (line.startswith("---") or line.startswith("+++")):
            continue

        # Hunk header: @@ -old_start,old_count +new_start,new_count @@
        if line.startswith("@@"):
            match = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if match:
                old_num = int(match.group(1))
                new_num = int(match.group(2))
            current_hunk = {"header": line, "lines": []}
            hunks.append(current_hunk)
            continue

        if current_hunk is None:
            continue

        if line.startswith("+"):
            current_hunk["lines"].append({
                "type": "add",
                "content": line[1:],
                "old_num": None,
                "new_num": new_num,
            })
            new_num += 1
            additions += 1
        elif line.startswith("-"):
            current_hunk["lines"].append({
                "type": "remove",
                "content": line[1:],
                "old_num": old_num,
                "new_num": None,
            })
            old_num += 1
            deletions += 1
        else:
            # Context line (starts with space or is empty)
            content = line[1:] if line.startswith(" ") else line
            current_hunk["lines"].append({
                "type": "context",
                "content": content,
                "old_num": old_num,
                "new_num": new_num,
            })
            old_num += 1
            new_num += 1

    parts = []
    if additions:
        parts.append(f"{additions} addition{'s' if additions != 1 else ''}")
    if deletions:
        parts.append(f"{deletions} deletion{'s' if deletions != 1 else ''}")
    summary = ", ".join(parts) if parts else "No changes"

    return {"hunks": hunks, "has_changes": True, "summary": summary}


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

    def close(self) -> None:
        """Close the Qdrant client connection."""
        if self._client is not None:
            self._client.close()
            self._client = None

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

    def get_service_knowledge_grouped(
        self,
        service_name: str,
        validation_status: Optional[str] = None,
        limit: int = 100,
    ) -> dict[str, list[KBEntry]]:
        """Get KB entries for a service grouped by category.

        Groups entries into: root_causes (investigation), runbooks (runbook),
        proven_fixes (proven_fix), and patterns (correction + other).

        Args:
            service_name: The service to get knowledge for.
            validation_status: Optional filter by validation status.
            limit: Maximum total entries to return.

        Returns:
            Dict with category keys mapping to lists of KBEntry.

        Raises:
            KBServiceError: If the query fails.
        """
        try:
            conditions: list[FieldCondition] = [
                FieldCondition(key="service", match=MatchValue(value=service_name))
            ]
            if validation_status:
                conditions.append(
                    FieldCondition(
                        key="validation_status",
                        match=MatchValue(value=validation_status),
                    )
                )

            query_filter = Filter(must=conditions)  # type: ignore[arg-type]

            results, _ = self.client.scroll(
                collection_name=KNOWLEDGE_COLLECTION,
                scroll_filter=query_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
                order_by=OrderBy(key="created_at", direction=Direction.DESC),
            )

            entries = [KBEntry.from_qdrant(point.id, point.payload or {}) for point in results]

            groups: dict[str, list[KBEntry]] = {
                "root_causes": [],
                "runbooks": [],
                "proven_fixes": [],
                "patterns": [],
            }

            for entry in entries:
                if entry.entry_type == "investigation":
                    groups["root_causes"].append(entry)
                elif entry.entry_type == "runbook":
                    groups["runbooks"].append(entry)
                elif entry.entry_type == "proven_fix":
                    groups["proven_fixes"].append(entry)
                else:
                    groups["patterns"].append(entry)

            return groups

        except UnexpectedResponse as e:
            logger.error(f"Qdrant query failed: {e}")
            raise KBServiceError(f"Failed to get service knowledge: {e}") from e
        except Exception as e:
            logger.error(f"KB service error: {e}")
            raise KBServiceError(f"Failed to get service knowledge: {e}") from e

    def get_service_validation_counts(
        self,
        service_name: str,
    ) -> dict[str, int]:
        """Get counts of KB entries per validation status for a service.

        Args:
            service_name: The service to count entries for.

        Returns:
            Dict with validation status keys and counts, plus "total" key.

        Raises:
            KBServiceError: If the query fails.
        """
        try:
            results, _ = self.client.scroll(
                collection_name=KNOWLEDGE_COLLECTION,
                scroll_filter=Filter(
                    must=[FieldCondition(key="service", match=MatchValue(value=service_name))]
                ),
                limit=MAX_FILTER_METADATA_ENTRIES,
                with_payload=["validation_status"],
                with_vectors=False,
            )

            counts: dict[str, int] = {}
            total = 0
            for point in results:
                status = (point.payload or {}).get("validation_status", "unknown")
                if not status:
                    status = "unknown"
                counts[status] = counts.get(status, 0) + 1
                total += 1

            counts["total"] = total
            return counts

        except UnexpectedResponse as e:
            logger.error(f"Qdrant query failed: {e}")
            raise KBServiceError(f"Failed to get validation counts: {e}") from e
        except Exception as e:
            logger.error(f"KB service error: {e}")
            raise KBServiceError(f"Failed to get validation counts: {e}") from e

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

    def get_entry_payload(self, entry_id: str) -> Optional[dict[str, Any]]:
        """Get raw payload for a KB entry by entry_id.

        Args:
            entry_id: The unique identifier of the entry.

        Returns:
            Raw payload dict if found, None otherwise.
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
            return dict(results[0].payload or {})
        except Exception as e:
            logger.warning(f"Failed to get entry payload for {entry_id}: {e}")
            return None

    def get_source_investigation(
        self, entry_id: str, payload: Optional[dict[str, Any]] = None
    ) -> Optional[dict[str, str]]:
        """Get the source investigation link for a KB entry.

        Args:
            entry_id: The KB entry ID.
            payload: Optional pre-fetched payload to avoid extra Qdrant query.

        Returns:
            Dict with investigation_id and relationship, or None.
        """
        if payload is None:
            payload = self.get_entry_payload(entry_id)
        if not payload:
            return None
        source_id = payload.get("source_investigation_id")
        if not source_id:
            return None
        return {"investigation_id": source_id, "relationship": "source"}

    def get_contributing_investigations(
        self, entry_id: str, payload: Optional[dict[str, Any]] = None
    ) -> list[dict[str, str]]:
        """Get contributing investigation links for a KB entry.

        Args:
            entry_id: The KB entry ID.
            payload: Optional pre-fetched payload to avoid extra Qdrant query.

        Returns:
            List of dicts with investigation_id and relationship.
        """
        if payload is None:
            payload = self.get_entry_payload(entry_id)
        if not payload:
            return []
        contribs = payload.get("contributing_investigations", [])
        source_id = payload.get("source_investigation_id", "")
        return [
            {"investigation_id": inv_id, "relationship": "contributing"}
            for inv_id in contribs
            if inv_id and inv_id != source_id
        ]

    def get_linked_kb_entries(self, investigation_id: str) -> list[KBEntry]:
        """Get KB entries linked to an investigation.

        Finds entries where the investigation is the source or contributor.

        Args:
            investigation_id: The investigation ID to look up.

        Returns:
            List of KBEntry objects linked to this investigation.
        """
        try:
            results, _ = self.client.scroll(
                collection_name=KNOWLEDGE_COLLECTION,
                scroll_filter=Filter(
                    should=[
                        FieldCondition(
                            key="source_investigation_id",
                            match=MatchValue(value=investigation_id),
                        ),
                        FieldCondition(
                            key="contributing_investigations",
                            match=MatchValue(value=investigation_id),
                        ),
                    ]
                ),
                limit=50,
                with_payload=True,
                with_vectors=False,
            )
            return [
                KBEntry.from_qdrant(r.id, r.payload or {})
                for r in results
            ]
        except Exception as e:
            logger.warning(
                "Failed to get linked KB entries for investigation %s: %s",
                investigation_id,
                e,
            )
            return []

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

    def _save_version_snapshot(self, entry_id: str, payload: dict, point_id: str) -> None:
        """Save current entry state as a version snapshot before overwriting.

        Args:
            entry_id: The entry_id of the entry
            payload: The current payload to snapshot
            point_id: The point ID (unused, kept for traceability)
        """
        version_point_id = str(uuid.uuid4())
        version_payload = {
            "entry_id": payload.get("entry_id", entry_id),
            "version": payload.get("version", 1),
            "title": payload.get("title", ""),
            "content": payload.get("content", ""),
            "author": payload.get("author"),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
            "entry_type": payload.get("entry_type"),
            "service": payload.get("service"),
            "tags": payload.get("tags", []),
            "validation_status": payload.get("validation_status"),
        }
        self.client.upsert(
            collection_name=VERSIONS_COLLECTION,
            points=[PointStruct(id=version_point_id, vector=[0.0], payload=version_payload)],
        )

    def list_versions(self, entry_id: str) -> list[dict]:
        """List all version snapshots for an entry, ordered by version descending.

        Args:
            entry_id: The entry_id to list versions for

        Returns:
            List of version metadata dicts with version, author, updated_at, title,
            content_length, tags, and service (used for change summary computation).

        Note:
            Limited to 100 versions per entry. Entries with more than 100 versions
            will show only the most recent 100 (by Qdrant scroll order).

        Raises:
            KBServiceError: If the query fails.
        """
        try:
            results, _ = self.client.scroll(
                collection_name=VERSIONS_COLLECTION,
                scroll_filter=Filter(
                    must=[FieldCondition(key="entry_id", match=MatchValue(value=entry_id))]
                ),
                limit=100,
                with_payload=True,
                with_vectors=False,
            )
            versions = [
                {
                    "version": p.payload.get("version", 1),
                    "author": p.payload.get("author"),
                    "updated_at": p.payload.get("updated_at"),
                    "title": p.payload.get("title"),
                    "content_length": len(p.payload.get("content", "")),
                    "tags": p.payload.get("tags", []),
                    "service": p.payload.get("service"),
                }
                for p in results
            ]
            return sorted(versions, key=lambda v: v["version"], reverse=True)
        except UnexpectedResponse as e:
            logger.error(f"Qdrant query failed: {e}")
            raise KBServiceError(f"Failed to list versions: {e}") from e
        except Exception as e:
            logger.error(f"KB service error: {e}")
            raise KBServiceError(f"Failed to list versions: {e}") from e

    def get_version(self, entry_id: str, version_num: int) -> Optional[dict]:
        """Get a specific version snapshot's full content.

        Args:
            entry_id: The entry_id of the entry
            version_num: The version number to retrieve

        Returns:
            Full payload dict of the version, or None if not found.

        Raises:
            KBServiceError: If the query fails.
        """
        try:
            results, _ = self.client.scroll(
                collection_name=VERSIONS_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(key="entry_id", match=MatchValue(value=entry_id)),
                        FieldCondition(key="version", match=MatchValue(value=version_num)),
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if not results:
                return None
            return results[0].payload
        except UnexpectedResponse as e:
            logger.error(f"Qdrant query failed: {e}")
            raise KBServiceError(f"Failed to get version: {e}") from e
        except Exception as e:
            logger.error(f"KB service error: {e}")
            raise KBServiceError(f"Failed to get version: {e}") from e

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

            # Check if service has earned auto-publish trust
            auto_published = False
            if service and author in ("beeper", "investigation"):
                auto_published = self.should_auto_publish(service)

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
                "auto_published": auto_published,
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

            # Save initial version snapshot (non-fatal: entry already created)
            try:
                self._save_version_snapshot(
                    entry_id=entry_id, payload=payload, point_id=point_id
                )
            except Exception:
                logger.warning(f"Failed to save initial version snapshot for {entry_id}")

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
        validation_status: Optional[str] = None,
        entry_type: Optional[str] = None,
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
            validation_status: New validation status (optional, preserves existing if not provided)
            entry_type: New entry type/category (optional, preserves existing if not provided)

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

            # Create updated payload — preserve bi-directional link fields
            now = datetime.now(timezone.utc)
            payload = {
                "entry_id": entry_id,
                "entry_type": (
                    entry_type
                    if entry_type is not None
                    else existing_payload.get("entry_type", "unknown")
                ),
                "title": new_title,
                "content": new_content,
                "service": new_service,
                "created_at": existing_payload.get("created_at", now.isoformat()),
                "updated_at": now.isoformat(),
                "author": author or existing_payload.get("author"),
                "version": new_version,
                "tags": new_tags,
                "validation_status": (
                    validation_status
                    if validation_status is not None
                    else existing_payload.get("validation_status")
                ),
                "source_investigation_id": existing_payload.get("source_investigation_id"),
                "contributing_investigations": existing_payload.get(
                    "contributing_investigations", []
                ),
                "linked_investigations": existing_payload.get("linked_investigations", []),
            }

            # Save version snapshot BEFORE overwriting
            self._save_version_snapshot(
                entry_id=entry_id,
                payload=existing_payload,
                point_id=str(existing_point.id),
            )

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

    def confirm_entry(self, entry_id: str, user: str) -> int:
        """Confirm an AI-generated KB entry as accurate (human-confirmed).

        Changes validation_status from 'AI-generated' to 'human-confirmed',
        saves a version snapshot, and records the confirming user and timestamp.

        Args:
            entry_id: The entry_id of the entry to confirm.
            user: The user confirming the entry.

        Returns:
            The new version number.

        Raises:
            KBServiceError: If the entry is not found, not AI-generated, or update fails.
        """
        try:
            results, _ = self.client.scroll(
                collection_name=KNOWLEDGE_COLLECTION,
                scroll_filter=Filter(
                    must=[FieldCondition(key="entry_id", match=MatchValue(value=entry_id))]
                ),
                limit=1,
                with_payload=True,
                with_vectors=True,
            )

            if not results:
                raise KBServiceError(f"KB entry not found: {entry_id}")

            existing_point = results[0]
            existing_payload = dict(existing_point.payload or {})
            current_status = existing_payload.get("validation_status")

            if current_status != "AI-generated":
                raise KBServiceError(
                    f"Can only confirm AI-generated entries, current status: {current_status}"
                )

            # Save version snapshot BEFORE overwriting
            self._save_version_snapshot(
                entry_id=entry_id,
                payload=existing_payload,
                point_id=str(existing_point.id),
            )

            # Update payload
            new_version = existing_payload.get("version", 1) + 1
            now = datetime.now(timezone.utc).isoformat()
            existing_payload["validation_status"] = "human-confirmed"
            existing_payload["version"] = new_version
            existing_payload["updated_at"] = now
            existing_payload["author"] = user

            # Get existing vector
            vector = existing_point.vector
            if isinstance(vector, dict):
                vector = list(vector.values())[0] if vector else [0.0]
            if vector is None:
                vector = [0.0]

            point = PointStruct(
                id=str(existing_point.id),
                vector=vector,
                payload=existing_payload,
            )

            self.client.upsert(
                collection_name=KNOWLEDGE_COLLECTION,
                points=[point],
            )

            logger.info(f"Confirmed KB entry: {entry_id} (version={new_version}, user={user})")
            return new_version

        except KBServiceError:
            raise
        except Exception as e:
            logger.error(f"Failed to confirm KB entry: {e}")
            raise KBServiceError(f"Failed to confirm KB entry: {e}") from e

    def create_correction(
        self,
        entry_id: str,
        user_message: str,
        assistant_response: str,
        summary: Optional[str] = None,
    ) -> Correction:
        """Create a new correction conversation for a KB entry.

        Args:
            entry_id: The KB entry being corrected
            user_message: The user's correction text
            assistant_response: Beeper's acknowledgment
            summary: Optional summary of understood changes

        Returns:
            The created Correction.

        Raises:
            KBServiceError: If creation fails.
        """
        try:
            now = datetime.now(timezone.utc).isoformat()
            correction_id = f"corr-{uuid.uuid4().hex[:12]}"
            point_id = str(uuid.uuid4())

            messages = [
                {"role": "user", "content": user_message, "timestamp": now},
                {"role": "assistant", "content": assistant_response, "timestamp": now},
            ]

            payload = {
                "correction_id": correction_id,
                "entry_id": entry_id,
                "messages": messages,
                "status": "pending",
                "summary": summary,
                "created_at": now,
                "updated_at": now,
            }

            self.client.upsert(
                collection_name=CORRECTIONS_COLLECTION,
                points=[PointStruct(id=point_id, vector=[0.0], payload=payload)],
            )

            logger.info(f"Created correction {correction_id} for entry {entry_id}")
            return Correction.from_qdrant(payload)

        except UnexpectedResponse as e:
            logger.error(f"Qdrant upsert failed: {e}")
            raise KBServiceError(f"Failed to create correction: {e}") from e
        except Exception as e:
            logger.error(f"KB service error: {e}")
            raise KBServiceError(f"Failed to create correction: {e}") from e

    def get_corrections_for_entry(self, entry_id: str) -> list[Correction]:
        """Get all corrections for a KB entry, ordered by created_at descending.

        Args:
            entry_id: The KB entry to get corrections for

        Returns:
            List of Correction objects.

        Raises:
            KBServiceError: If the query fails.
        """
        try:
            results, _ = self.client.scroll(
                collection_name=CORRECTIONS_COLLECTION,
                scroll_filter=Filter(
                    must=[FieldCondition(key="entry_id", match=MatchValue(value=entry_id))]
                ),
                limit=100,
                with_payload=True,
                with_vectors=False,
            )

            corrections = [
                Correction.from_qdrant(point.payload or {}) for point in results
            ]
            # Sort by created_at descending
            corrections.sort(key=lambda c: c.created_at, reverse=True)
            return corrections

        except UnexpectedResponse as e:
            logger.error(f"Qdrant query failed: {e}")
            raise KBServiceError(f"Failed to get corrections: {e}") from e
        except Exception as e:
            logger.error(f"KB service error: {e}")
            raise KBServiceError(f"Failed to get corrections: {e}") from e

    def get_correction(self, correction_id: str) -> Optional[Correction]:
        """Get a single correction by its correction_id.

        Args:
            correction_id: The unique identifier of the correction

        Returns:
            Correction if found, None otherwise.

        Raises:
            KBServiceError: If the query fails.
        """
        try:
            results, _ = self.client.scroll(
                collection_name=CORRECTIONS_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="correction_id", match=MatchValue(value=correction_id)
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )

            if not results:
                return None

            return Correction.from_qdrant(results[0].payload or {})

        except UnexpectedResponse as e:
            logger.error(f"Qdrant query failed: {e}")
            raise KBServiceError(f"Failed to get correction: {e}") from e
        except Exception as e:
            logger.error(f"KB service error: {e}")
            raise KBServiceError(f"Failed to get correction: {e}") from e

    def add_correction_message(
        self,
        correction_id: str,
        role: str,
        content: str,
    ) -> Correction:
        """Add a message to an existing correction conversation.

        Args:
            correction_id: The correction to add the message to
            role: Message role ('user' or 'assistant')
            content: Message content

        Returns:
            Updated Correction.

        Raises:
            KBServiceError: If the correction is not found or update fails.
        """
        try:
            results, _ = self.client.scroll(
                collection_name=CORRECTIONS_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="correction_id", match=MatchValue(value=correction_id)
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )

            if not results:
                raise KBServiceError(f"Correction not found: {correction_id}")

            point = results[0]
            payload = dict(point.payload or {})
            now = datetime.now(timezone.utc).isoformat()

            messages = list(payload.get("messages", []))
            messages.append({"role": role, "content": content, "timestamp": now})
            payload["messages"] = messages
            payload["updated_at"] = now

            self.client.upsert(
                collection_name=CORRECTIONS_COLLECTION,
                points=[PointStruct(id=str(point.id), vector=[0.0], payload=payload)],
            )

            return Correction.from_qdrant(payload)

        except KBServiceError:
            raise
        except UnexpectedResponse as e:
            logger.error(f"Qdrant upsert failed: {e}")
            raise KBServiceError(f"Failed to add correction message: {e}") from e
        except Exception as e:
            logger.error(f"KB service error: {e}")
            raise KBServiceError(f"Failed to add correction message: {e}") from e

    def update_correction(
        self,
        correction_id: str,
        status: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> Correction:
        """Update a correction's status or summary.

        Args:
            correction_id: The correction to update
            status: New status (pending/applied/rejected)
            summary: Updated summary

        Returns:
            Updated Correction.

        Raises:
            KBServiceError: If the correction is not found or update fails.
        """
        try:
            results, _ = self.client.scroll(
                collection_name=CORRECTIONS_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="correction_id", match=MatchValue(value=correction_id)
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )

            if not results:
                raise KBServiceError(f"Correction not found: {correction_id}")

            point = results[0]
            payload = dict(point.payload or {})
            now = datetime.now(timezone.utc).isoformat()

            if status is not None:
                payload["status"] = status
            if summary is not None:
                payload["summary"] = summary
            payload["updated_at"] = now

            self.client.upsert(
                collection_name=CORRECTIONS_COLLECTION,
                points=[PointStruct(id=str(point.id), vector=[0.0], payload=payload)],
            )

            return Correction.from_qdrant(payload)

        except KBServiceError:
            raise
        except UnexpectedResponse as e:
            logger.error(f"Qdrant upsert failed: {e}")
            raise KBServiceError(f"Failed to update correction: {e}") from e
        except Exception as e:
            logger.error(f"KB service error: {e}")
            raise KBServiceError(f"Failed to update correction: {e}") from e

    def create_learning_pattern(
        self,
        entry_id: str,
        correction_id: str,
        service_name: str,
        category: str,
        description: str,
        original_snippet: str = "",
        corrected_snippet: str = "",
    ) -> LearningPattern:
        """Store a learned pattern from a correction diff.

        Args:
            entry_id: The KB entry that was corrected
            correction_id: The correction that triggered learning
            service_name: Service scope for the pattern
            category: Pattern category (missing_context, etc.)
            description: Human-readable description of what was learned
            original_snippet: Relevant original text
            corrected_snippet: Relevant corrected text

        Returns:
            The created LearningPattern.

        Raises:
            KBServiceError: If creation fails.
        """
        if category not in LEARNING_CATEGORIES:
            category = "other"

        try:
            now = datetime.now(timezone.utc).isoformat()
            pattern_id = f"lrn-{uuid.uuid4().hex[:12]}"
            point_id = str(uuid.uuid4())

            payload = {
                "pattern_id": pattern_id,
                "entry_id": entry_id,
                "correction_id": correction_id,
                "service_name": service_name,
                "category": category,
                "description": description,
                "original_snippet": original_snippet,
                "corrected_snippet": corrected_snippet,
                "created_at": now,
            }

            self.client.upsert(
                collection_name=LEARNING_PATTERNS_COLLECTION,
                points=[PointStruct(id=point_id, vector=[0.0], payload=payload)],
            )

            logger.info(
                f"Created learning pattern {pattern_id} "
                f"({category}) for entry {entry_id}"
            )
            return LearningPattern.from_qdrant(payload)

        except UnexpectedResponse as e:
            logger.error(f"Qdrant upsert failed: {e}")
            raise KBServiceError(f"Failed to create learning pattern: {e}") from e
        except Exception as e:
            logger.error(f"KB service error: {e}")
            raise KBServiceError(f"Failed to create learning pattern: {e}") from e

    def get_learning_patterns(
        self,
        service_name: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 200,
    ) -> list[LearningPattern]:
        """Get learning patterns, optionally filtered by service and/or category.

        Args:
            service_name: Filter by service name (None = all services)
            category: Filter by category (None = all categories)
            limit: Maximum number of patterns to return

        Returns:
            List of LearningPattern objects sorted by created_at descending.

        Raises:
            KBServiceError: If the query fails.
        """
        try:
            conditions = []
            if service_name:
                conditions.append(
                    FieldCondition(
                        key="service_name", match=MatchValue(value=service_name)
                    )
                )
            if category and category in LEARNING_CATEGORIES:
                conditions.append(
                    FieldCondition(
                        key="category", match=MatchValue(value=category)
                    )
                )

            scroll_filter: Filter | None = None
            if conditions:
                scroll_filter = Filter(must=conditions)  # type: ignore[arg-type]

            results, _ = self.client.scroll(
                collection_name=LEARNING_PATTERNS_COLLECTION,
                scroll_filter=scroll_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )

            patterns = [
                LearningPattern.from_qdrant(point.payload or {}) for point in results
            ]
            patterns.sort(key=lambda p: p.created_at, reverse=True)
            return patterns

        except UnexpectedResponse as e:
            logger.error(f"Qdrant query failed: {e}")
            raise KBServiceError(f"Failed to get learning patterns: {e}") from e
        except Exception as e:
            logger.error(f"KB service error: {e}")
            raise KBServiceError(f"Failed to get learning patterns: {e}") from e

    def get_learning_summary(self) -> dict[str, Any]:
        """Get aggregated learning summary with category counts and per-service breakdown.

        Returns:
            Dict with 'total', 'by_category', 'by_service', and 'patterns' keys.

        Raises:
            KBServiceError: If the query fails.
        """
        patterns = self.get_learning_patterns()

        by_category: dict[str, int] = {}
        by_service: dict[str, int] = {}
        for p in patterns:
            by_category[p.category] = by_category.get(p.category, 0) + 1
            by_service[p.service_name] = by_service.get(p.service_name, 0) + 1

        return {
            "total": len(patterns),
            "by_category": by_category,
            "by_service": by_service,
            "patterns": patterns,
        }

    # ── Service Trust Level Methods ──

    def get_service_trust(
        self, service_name: str
    ) -> Optional[ServiceTrustLevel]:
        """Get trust level for a specific service.

        Args:
            service_name: Service to get trust for

        Returns:
            ServiceTrustLevel or None if not found.

        Raises:
            KBServiceError: If the query fails.
        """
        try:
            results, _ = self.client.scroll(
                collection_name=SERVICE_TRUST_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="service_name",
                            match=MatchValue(value=service_name),
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if results:
                return ServiceTrustLevel.from_qdrant(
                    results[0].payload or {}
                )
            return None
        except UnexpectedResponse as e:
            raise KBServiceError(
                f"Failed to get service trust: {e}"
            ) from e
        except Exception as e:
            raise KBServiceError(
                f"Failed to get service trust: {e}"
            ) from e

    def upsert_service_trust(
        self,
        service_name: str,
        trust_level: str,
        accuracy_pct: float,
        total_entries: int,
        reviewed_entries: int,
        correct_entries: int,
        manually_adjusted: bool = False,
        manual_reason: str = "",
    ) -> ServiceTrustLevel:
        """Create or update a service trust level record.

        Args:
            service_name: Service name
            trust_level: "draft" or "trusted"
            accuracy_pct: Accuracy percentage (0-100)
            total_entries: Total entries for this service
            reviewed_entries: Number of reviewed entries
            correct_entries: Number of correct entries
            manually_adjusted: Whether this was a manual override
            manual_reason: Reason for manual override

        Returns:
            The upserted ServiceTrustLevel.

        Raises:
            KBServiceError: If the upsert fails.
        """
        if trust_level not in ("draft", "trusted"):
            trust_level = "draft"

        try:
            now = datetime.now(timezone.utc).isoformat()

            # Single query to find existing point (reuse ID to avoid duplicates)
            point_id = str(uuid.uuid4())
            try:
                results, _ = self.client.scroll(
                    collection_name=SERVICE_TRUST_COLLECTION,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(
                                key="service_name",
                                match=MatchValue(value=service_name),
                            )
                        ]
                    ),
                    limit=1,
                    with_payload=False,
                    with_vectors=False,
                )
                if results:
                    point_id = str(results[0].id)
            except Exception as e:
                logger.warning(
                    "Could not find existing trust point for %s: %s",
                    service_name, e,
                )

            payload = {
                "service_name": service_name,
                "trust_level": trust_level,
                "accuracy_pct": accuracy_pct,
                "total_entries": total_entries,
                "reviewed_entries": reviewed_entries,
                "correct_entries": correct_entries,
                "last_updated": now,
                "manually_adjusted": manually_adjusted,
                "manual_reason": manual_reason,
            }

            self.client.upsert(
                collection_name=SERVICE_TRUST_COLLECTION,
                points=[
                    PointStruct(
                        id=point_id, vector=[0.0], payload=payload
                    )
                ],
            )

            return ServiceTrustLevel.from_qdrant(payload)

        except KBServiceError:
            raise
        except Exception as e:
            raise KBServiceError(
                f"Failed to upsert service trust: {e}"
            ) from e

    def get_all_service_trusts(self) -> list[ServiceTrustLevel]:
        """Get all service trust level records.

        Returns:
            List of ServiceTrustLevel objects.

        Raises:
            KBServiceError: If the query fails.
        """
        try:
            results, _ = self.client.scroll(
                collection_name=SERVICE_TRUST_COLLECTION,
                limit=200,
                with_payload=True,
                with_vectors=False,
            )
            return [
                ServiceTrustLevel.from_qdrant(p.payload or {})
                for p in results
            ]
        except Exception as e:
            raise KBServiceError(
                f"Failed to get service trusts: {e}"
            ) from e

    def set_manual_trust_override(
        self,
        service_name: str,
        trust_level: str,
        reason: str,
    ) -> ServiceTrustLevel:
        """Manually set a service's trust level (admin override).

        Args:
            service_name: Service name
            trust_level: "draft" or "trusted"
            reason: Reason for override

        Returns:
            The updated ServiceTrustLevel.

        Raises:
            KBServiceError: If the update fails.
        """
        existing = self.get_service_trust(service_name)
        return self.upsert_service_trust(
            service_name=service_name,
            trust_level=trust_level,
            accuracy_pct=existing.accuracy_pct if existing else 0.0,
            total_entries=existing.total_entries if existing else 0,
            reviewed_entries=(
                existing.reviewed_entries if existing else 0
            ),
            correct_entries=existing.correct_entries if existing else 0,
            manually_adjusted=True,
            manual_reason=reason,
        )

    def calculate_service_accuracy(
        self, service_name: str
    ) -> dict[str, Any]:
        """Calculate accuracy metrics for a service.

        Counts total entries authored by Beeper for this service,
        and entries that had corrections (learning patterns exist).

        Args:
            service_name: Service to calculate accuracy for

        Returns:
            Dict with total_entries, reviewed_entries,
            correct_entries, accuracy_pct.

        Raises:
            KBServiceError: If the query fails.
        """
        try:
            # Count total entries for this service by Beeper
            entry_results, _ = self.client.scroll(
                collection_name=KNOWLEDGE_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="service",
                            match=MatchValue(value=service_name),
                        ),
                    ]
                ),
                limit=500,
                with_payload=["entry_id"],
                with_vectors=False,
            )
            total_entries = len(entry_results)

            if total_entries == 0:
                return {
                    "total_entries": 0,
                    "reviewed_entries": 0,
                    "correct_entries": 0,
                    "accuracy_pct": 0.0,
                }

            # Get unique entry_ids that have learning patterns
            patterns = self.get_learning_patterns(
                service_name=service_name
            )
            corrected_entry_ids = {p.entry_id for p in patterns}
            reviewed_entries = len(corrected_entry_ids)
            correct_entries = total_entries - reviewed_entries

            accuracy_pct = (
                (correct_entries / total_entries * 100)
                if total_entries > 0
                else 0.0
            )

            return {
                "total_entries": total_entries,
                "reviewed_entries": reviewed_entries,
                "correct_entries": correct_entries,
                "accuracy_pct": round(accuracy_pct, 1),
            }
        except KBServiceError:
            raise
        except Exception as e:
            raise KBServiceError(
                f"Failed to calculate accuracy: {e}"
            ) from e

    def evaluate_trust_graduation(
        self, service_name: str
    ) -> Optional[ServiceTrustLevel]:
        """Evaluate and update trust level based on accuracy.

        Graduation: >=10 entries, >=90% accuracy → "trusted"
        Downgrade: <80% accuracy → "draft"

        Args:
            service_name: Service to evaluate

        Returns:
            Updated ServiceTrustLevel, or None if no entries.

        Raises:
            KBServiceError: If evaluation fails.
        """
        metrics = self.calculate_service_accuracy(service_name)

        if metrics["total_entries"] == 0:
            return None

        existing = self.get_service_trust(service_name)

        # Don't override manual adjustments automatically
        if existing and existing.manually_adjusted:
            return existing

        current_level = existing.trust_level if existing else "draft"
        new_level = current_level

        # Graduation: enough entries with high accuracy
        if (
            current_level == "draft"
            and metrics["total_entries"] >= 10
            and metrics["accuracy_pct"] >= 90.0
        ):
            new_level = "trusted"

        # Downgrade: accuracy dropped
        if (
            current_level == "trusted"
            and metrics["accuracy_pct"] < 80.0
        ):
            new_level = "draft"

        return self.upsert_service_trust(
            service_name=service_name,
            trust_level=new_level,
            accuracy_pct=metrics["accuracy_pct"],
            total_entries=metrics["total_entries"],
            reviewed_entries=metrics["reviewed_entries"],
            correct_entries=metrics["correct_entries"],
        )

    def should_auto_publish(self, service_name: str) -> bool:
        """Check if a service has earned trusted status.

        Args:
            service_name: Service to check

        Returns:
            True if service trust level is "trusted".
        """
        try:
            trust = self.get_service_trust(service_name)
            return trust is not None and trust.trust_level == "trusted"
        except KBServiceError:
            return False
