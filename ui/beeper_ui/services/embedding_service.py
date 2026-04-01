"""Embedding service for semantic search.

This module provides embedding generation for KB semantic search
using LiteLLM for provider flexibility.
"""

import hashlib
import logging
import os
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

# Default embedding model (OpenAI text-embedding-3-small = 1536 dimensions)
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIMENSIONS = 1536


class EmbeddingServiceError(Exception):
    """Exception raised by embedding service operations."""

    pass


class EmbeddingService:
    """Service for generating text embeddings using LiteLLM.

    Supports multiple embedding providers through LiteLLM's unified interface.
    Includes in-memory LRU caching for repeated queries.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        cache_size: int = 128,
    ) -> None:
        """Initialize the embedding service.

        Args:
            model: Embedding model to use (defaults to EMBEDDING_MODEL env var
                or text-embedding-3-small).
            api_key: API key for the embedding provider (defaults to OPENAI_API_KEY env)
            cache_size: Maximum number of cached embeddings
        """
        self.model: str = model or os.getenv("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._cache_size = cache_size

        # Create cached embedding function
        self._get_embedding_cached = lru_cache(maxsize=cache_size)(self._get_embedding_uncached)

        logger.info(f"Embedding service initialized with model: {self.model}")

    def _get_embedding_uncached(self, text_hash: str, text: str) -> tuple[float, ...]:
        """Get embedding without caching (used internally by cache).

        Args:
            text_hash: Hash of text for cache key
            text: The text to embed

        Returns:
            Embedding vector as tuple (hashable for cache).
        """
        try:
            import litellm

            # Set API key if provided
            if self._api_key:
                os.environ["OPENAI_API_KEY"] = self._api_key

            response = litellm.embedding(
                model=self.model,
                input=[text],
            )

            embedding = response.data[0]["embedding"]
            logger.debug(f"Generated embedding for text (hash={text_hash[:8]})")

            return tuple(embedding)

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise EmbeddingServiceError(f"Failed to generate embedding: {e}") from e

    def get_embedding(self, text: str) -> list[float]:
        """Generate embedding for the given text.

        Uses LRU cache to avoid redundant API calls for identical queries.

        Args:
            text: The text to generate an embedding for

        Returns:
            List of floats representing the embedding vector.

        Raises:
            EmbeddingServiceError: If embedding generation fails.
        """
        if not text or not text.strip():
            raise EmbeddingServiceError("Cannot generate embedding for empty text")

        # Normalize text for caching
        normalized_text = text.strip()

        # Create hash for cache key (LRU cache needs hashable args)
        text_hash = hashlib.sha256(normalized_text.encode()).hexdigest()

        # Get cached or generate new embedding
        embedding_tuple = self._get_embedding_cached(text_hash, normalized_text)

        return list(embedding_tuple)

    def get_embedding_dimensions(self) -> int:
        """Get the number of dimensions for the configured embedding model.

        Returns:
            Number of dimensions in the embedding vector.
        """
        # Known model dimensions
        model_dimensions: dict[str, int] = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }

        return model_dimensions.get(self.model, DEFAULT_EMBEDDING_DIMENSIONS)

    def clear_cache(self) -> None:
        """Clear the embedding cache."""
        self._get_embedding_cached.cache_clear()
        logger.info("Embedding cache cleared")

    def get_cache_info(self) -> dict[str, int | None]:
        """Get cache statistics.

        Returns:
            Dict with hits, misses, maxsize, currsize.
        """
        info = self._get_embedding_cached.cache_info()
        return {
            "hits": info.hits,
            "misses": info.misses,
            "maxsize": info.maxsize,
            "currsize": info.currsize,
        }

    def is_configured(self) -> bool:
        """Check if the embedding service has required configuration.

        Returns:
            True if API key is configured, False otherwise.
        """
        return bool(self._api_key or os.getenv("OPENAI_API_KEY"))


# Module-level singleton for convenience
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get the global embedding service instance.

    Returns:
        EmbeddingService singleton instance.
    """
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


def reset_embedding_service() -> None:
    """Reset the global embedding service singleton.

    Primarily used for testing to ensure a fresh instance.
    """
    global _embedding_service
    _embedding_service = None
