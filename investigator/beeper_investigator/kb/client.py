"""Qdrant client wrapper for Beeper knowledge base operations.

This module provides a high-level interface for interacting with the
Beeper knowledge base stored in Qdrant.
"""

import logging
import os
import threading
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Condition, FieldCondition, Filter, MatchValue

from beeper_investigator.kb.schemas import (
    CollectionInfo,
    SearchResult,
)

logger = logging.getLogger(__name__)

# Collection names (must match init-collections.py)
INVESTIGATIONS_COLLECTION = "investigations"
KNOWLEDGE_COLLECTION = "knowledge"
VERSIONS_COLLECTION = "knowledge_versions"

# Default configuration
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 6333
DEFAULT_GRPC_PORT = 6334
DEFAULT_VECTOR_DIM = 1536


class KBClient:
    """High-level client for Beeper knowledge base operations.

    This client wraps the Qdrant client and provides domain-specific
    methods for working with investigations and knowledge entries.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        grpc_port: Optional[int] = None,
        prefer_grpc: bool = False,
    ) -> None:
        """Initialize the KB client.

        Args:
            host: Qdrant server host (defaults to QDRANT_HOST env or localhost)
            port: Qdrant HTTP port (defaults to QDRANT_PORT env or 6333)
            grpc_port: Qdrant gRPC port (defaults to QDRANT_GRPC_PORT env or 6334)
            prefer_grpc: Whether to prefer gRPC over HTTP
        """
        self.host = host or os.getenv("QDRANT_HOST", DEFAULT_HOST)
        self.port = port or int(os.getenv("QDRANT_PORT", str(DEFAULT_PORT)))
        self.grpc_port = grpc_port or int(
            os.getenv("QDRANT_GRPC_PORT", str(DEFAULT_GRPC_PORT))
        )
        self.prefer_grpc = prefer_grpc

        self._client: Optional[QdrantClient] = None

    @property
    def client(self) -> QdrantClient:
        """Get or create the Qdrant client (lazy initialization)."""
        if self._client is None:
            logger.info(f"Connecting to Qdrant at {self.host}:{self.port}")
            self._client = QdrantClient(
                host=self.host,
                port=self.port,
                grpc_port=self.grpc_port if self.prefer_grpc else 0,
                prefer_grpc=self.prefer_grpc,
            )
        return self._client

    def health_check(self) -> bool:
        """Check if Qdrant is healthy and reachable.

        Returns:
            True if Qdrant is healthy, False otherwise.
        """
        try:
            self.client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            return False

    def get_collection_info(self, collection_name: str) -> Optional[CollectionInfo]:
        """Get information about a collection.

        Args:
            collection_name: Name of the collection

        Returns:
            CollectionInfo if collection exists, None otherwise.
        """
        try:
            info = self.client.get_collection(collection_name)
            return CollectionInfo(
                name=collection_name,
                vectors_count=info.indexed_vectors_count or 0,
                points_count=info.points_count or 0,
            )
        except Exception as e:
            logger.error(f"Failed to get collection info for '{collection_name}': {e}")
            return None

    def search_knowledge(
        self,
        query_vector: list[float],
        limit: int = 10,
        entry_type: Optional[str] = None,
        service: Optional[str] = None,
    ) -> list[SearchResult]:
        """Search the knowledge base using vector similarity.

        Args:
            query_vector: Query embedding vector
            limit: Maximum number of results to return
            entry_type: Optional filter by entry type (runbook, investigation, correction)
            service: Optional filter by service name

        Returns:
            List of search results sorted by similarity score.
        """
        # Build filter conditions
        conditions: list[Condition] = []
        if entry_type:
            conditions.append(
                FieldCondition(key="entry_type", match=MatchValue(value=entry_type))
            )
        if service:
            conditions.append(
                FieldCondition(key="service", match=MatchValue(value=service))
            )

        query_filter = Filter(must=conditions) if conditions else None

        results = self.client.query_points(
            collection_name=KNOWLEDGE_COLLECTION,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
        )

        return [
            SearchResult(
                id=str(r.id),
                score=r.score,
                payload=r.payload or {},
            )
            for r in results.points
        ]

    def search_investigations(
        self,
        query_vector: list[float],
        limit: int = 10,
        status: Optional[str] = None,
        service: Optional[str] = None,
    ) -> list[SearchResult]:
        """Search investigations using vector similarity.

        Args:
            query_vector: Query embedding vector
            limit: Maximum number of results to return
            status: Optional filter by investigation status
            service: Optional filter by service name

        Returns:
            List of search results sorted by similarity score.
        """
        conditions: list[Condition] = []
        if status:
            conditions.append(
                FieldCondition(key="status", match=MatchValue(value=status))
            )
        if service:
            conditions.append(
                FieldCondition(key="service", match=MatchValue(value=service))
            )

        query_filter = Filter(must=conditions) if conditions else None

        results = self.client.query_points(
            collection_name=INVESTIGATIONS_COLLECTION,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
        )

        return [
            SearchResult(
                id=str(r.id),
                score=r.score,
                payload=r.payload or {},
            )
            for r in results.points
        ]

    def close(self) -> None:
        """Close the Qdrant client connection."""
        if self._client is not None:
            self._client.close()
            self._client = None


# Thread-safe singleton instance
_kb_client: Optional[KBClient] = None
_kb_client_lock = threading.Lock()


def get_kb_client() -> KBClient:
    """Get the global KB client instance (thread-safe singleton pattern).

    Returns:
        The global KBClient instance.
    """
    global _kb_client
    if _kb_client is None:
        with _kb_client_lock:
            # Double-check locking pattern
            if _kb_client is None:
                _kb_client = KBClient()
    return _kb_client
