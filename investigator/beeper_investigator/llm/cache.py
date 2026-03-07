"""LLM response cache with TTL-based expiration and LRU-style eviction.

Provides in-memory caching for LLM completion responses within a single
investigation pod lifecycle. Cache keys are generated from message content,
model, max_tokens, and temperature using SHA-256 hashing.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A single cached LLM response."""

    response: str
    created_at: float
    model: str


class LlmResponseCache:
    """In-memory cache for LLM completion responses.

    Uses SHA-256 cache keys, TTL-based expiration, and oldest-entry eviction
    when the maximum entry count is reached.
    """

    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 256) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._entries: dict[str, CacheEntry] = {}
        self._cache_hits: int = 0
        self._cache_misses: int = 0

    @staticmethod
    def _generate_cache_key(
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Generate a deterministic SHA-256 cache key.

        Args:
            messages: LLM message list.
            model: Model identifier.
            max_tokens: Maximum tokens parameter.
            temperature: Temperature parameter.

        Returns:
            Hex digest of the SHA-256 hash.
        """
        key_data = (
            json.dumps(messages, sort_keys=True)
            + f"|{model}|{max_tokens}|{temperature}"
        )
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> str | None:
        """Retrieve a cached response if it exists and has not expired.

        Args:
            messages: LLM message list.
            model: Model identifier.
            max_tokens: Maximum tokens parameter.
            temperature: Temperature parameter.

        Returns:
            Cached response string, or None on miss/expiry.
        """
        key = self._generate_cache_key(messages, model, max_tokens, temperature)
        entry = self._entries.get(key)
        if entry and (time.monotonic() - entry.created_at) < self._ttl_seconds:
            self._cache_hits += 1
            return entry.response
        # Expired or missing
        if entry:
            del self._entries[key]
        self._cache_misses += 1
        return None

    def put(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        response: str,
    ) -> None:
        """Store a response in the cache, evicting the oldest entry if full.

        Args:
            messages: LLM message list.
            model: Model identifier.
            max_tokens: Maximum tokens parameter.
            temperature: Temperature parameter.
            response: The LLM response to cache.
        """
        key = self._generate_cache_key(messages, model, max_tokens, temperature)
        if len(self._entries) >= self._max_entries:
            oldest_key = min(self._entries, key=lambda k: self._entries[k].created_at)
            del self._entries[oldest_key]
        self._entries[key] = CacheEntry(
            response=response,
            created_at=time.monotonic(),
            model=model,
        )

    def clear(self) -> None:
        """Remove all cache entries."""
        self._entries.clear()

    def get_cache_stats(self) -> dict[str, Any]:
        """Return cache performance statistics.

        Returns:
            Dict with hits, misses, hit_rate, entries_count, max_entries, ttl_seconds.
        """
        total = self._cache_hits + self._cache_misses
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "hit_rate": self._cache_hits / total if total > 0 else 0.0,
            "entries_count": len(self._entries),
            "max_entries": self._max_entries,
            "ttl_seconds": self._ttl_seconds,
        }

    def reset_stats(self) -> None:
        """Clear hit/miss counters."""
        self._cache_hits = 0
        self._cache_misses = 0
