"""Tests for LLM response caching (Story 3-10).

Covers: LlmResponseCache, LlmClient cache integration, cache stats propagation,
and LlmConfig cache configuration.
"""

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from beeper_investigator.llm.cache import CacheEntry, LlmResponseCache
from beeper_investigator.llm.client import LlmClient, LlmConfig

# ── Task 6: Tests for LlmResponseCache ──────────────────────────


class TestLlmResponseCacheKeyGeneration:
    """Tests for cache key generation (Task 6.1-6.3)."""

    def test_deterministic_hash_for_same_inputs(self) -> None:
        """6.1: Same inputs produce the same cache key."""
        messages = [{"role": "user", "content": "Hello"}]
        key1 = LlmResponseCache._generate_cache_key(messages, "model-a", 4096, 0.0)
        key2 = LlmResponseCache._generate_cache_key(messages, "model-a", 4096, 0.0)
        assert key1 == key2

    def test_different_hash_for_different_messages(self) -> None:
        """6.2: Different messages produce different cache keys."""
        key1 = LlmResponseCache._generate_cache_key(
            [{"role": "user", "content": "Hello"}], "model-a", 4096, 0.0
        )
        key2 = LlmResponseCache._generate_cache_key(
            [{"role": "user", "content": "Goodbye"}], "model-a", 4096, 0.0
        )
        assert key1 != key2

    def test_different_hash_for_different_model(self) -> None:
        """6.3: Different model produces different cache key."""
        messages = [{"role": "user", "content": "Hello"}]
        key1 = LlmResponseCache._generate_cache_key(messages, "model-a", 4096, 0.0)
        key2 = LlmResponseCache._generate_cache_key(messages, "model-b", 4096, 0.0)
        assert key1 != key2

    def test_different_hash_for_different_max_tokens(self) -> None:
        """6.3: Different max_tokens produces different cache key."""
        messages = [{"role": "user", "content": "Hello"}]
        key1 = LlmResponseCache._generate_cache_key(messages, "model-a", 4096, 0.0)
        key2 = LlmResponseCache._generate_cache_key(messages, "model-a", 2048, 0.0)
        assert key1 != key2

    def test_different_hash_for_different_temperature(self) -> None:
        """6.3: Different temperature produces different cache key."""
        messages = [{"role": "user", "content": "Hello"}]
        key1 = LlmResponseCache._generate_cache_key(messages, "model-a", 4096, 0.0)
        key2 = LlmResponseCache._generate_cache_key(messages, "model-a", 4096, 0.5)
        assert key1 != key2


class TestLlmResponseCacheOperations:
    """Tests for cache get/put/clear operations (Task 6.4-6.8)."""

    def test_get_returns_none_on_miss(self) -> None:
        """6.4: get() returns None on cache miss."""
        cache = LlmResponseCache()
        result = cache.get([{"role": "user", "content": "Hello"}], "model", 4096, 0.0)
        assert result is None

    def test_put_then_get_returns_cached_response(self) -> None:
        """6.5: put() then get() returns cached response."""
        cache = LlmResponseCache()
        messages = [{"role": "user", "content": "Hello"}]
        cache.put(messages, "model", 4096, 0.0, "cached answer")
        result = cache.get(messages, "model", 4096, 0.0)
        assert result == "cached answer"

    def test_get_returns_none_after_ttl_expires(self) -> None:
        """6.6: get() returns None after TTL expires."""
        cache = LlmResponseCache(ttl_seconds=1)
        messages = [{"role": "user", "content": "Hello"}]
        cache.put(messages, "model", 4096, 0.0, "cached answer")

        # Manually expire entry by setting created_at in the past
        key = LlmResponseCache._generate_cache_key(messages, "model", 4096, 0.0)
        cache._entries[key] = CacheEntry(
            response="cached answer",
            created_at=time.monotonic() - 2,  # 2 seconds ago, TTL is 1
            model="model",
        )

        result = cache.get(messages, "model", 4096, 0.0)
        assert result is None
        # Expired entry should be cleaned up
        assert key not in cache._entries

    def test_put_evicts_oldest_when_max_entries_exceeded(self) -> None:
        """6.7: put() evicts oldest entry when max_entries exceeded."""
        cache = LlmResponseCache(max_entries=2)
        msg1 = [{"role": "user", "content": "first"}]
        msg2 = [{"role": "user", "content": "second"}]
        msg3 = [{"role": "user", "content": "third"}]

        cache.put(msg1, "model", 4096, 0.0, "resp1")
        cache.put(msg2, "model", 4096, 0.0, "resp2")
        # This should evict msg1 (oldest)
        cache.put(msg3, "model", 4096, 0.0, "resp3")

        assert cache.get(msg1, "model", 4096, 0.0) is None  # evicted
        assert cache.get(msg2, "model", 4096, 0.0) == "resp2"
        assert cache.get(msg3, "model", 4096, 0.0) == "resp3"

    def test_clear_removes_all_entries(self) -> None:
        """6.8: clear() removes all entries."""
        cache = LlmResponseCache()
        messages = [{"role": "user", "content": "Hello"}]
        cache.put(messages, "model", 4096, 0.0, "cached")
        assert cache.get(messages, "model", 4096, 0.0) == "cached"

        cache.clear()
        assert cache.get(messages, "model", 4096, 0.0) is None


class TestLlmResponseCacheMetrics:
    """Tests for cache metrics tracking (Task 6.9-6.11, Task 4)."""

    def test_cache_hit_miss_counters(self) -> None:
        """6.9: Cache hit/miss counters are incremented correctly."""
        cache = LlmResponseCache()
        messages = [{"role": "user", "content": "Hello"}]

        # Miss
        cache.get(messages, "model", 4096, 0.0)
        assert cache._cache_misses == 1
        assert cache._cache_hits == 0

        # Store and hit
        cache.put(messages, "model", 4096, 0.0, "cached")
        cache.get(messages, "model", 4096, 0.0)
        assert cache._cache_hits == 1
        assert cache._cache_misses == 1

    def test_get_cache_stats_hit_rate(self) -> None:
        """6.10: get_cache_stats() returns correct hit_rate calculation."""
        cache = LlmResponseCache(ttl_seconds=3600, max_entries=256)
        messages = [{"role": "user", "content": "Hello"}]

        # 1 miss then 1 hit → 50% hit rate
        cache.get(messages, "model", 4096, 0.0)  # miss
        cache.put(messages, "model", 4096, 0.0, "cached")
        cache.get(messages, "model", 4096, 0.0)  # hit

        stats = cache.get_cache_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5
        assert stats["entries_count"] == 1
        assert stats["max_entries"] == 256
        assert stats["ttl_seconds"] == 3600

    def test_get_cache_stats_no_requests(self) -> None:
        """get_cache_stats() returns 0.0 hit_rate when no requests made."""
        cache = LlmResponseCache()
        stats = cache.get_cache_stats()
        assert stats["hit_rate"] == 0.0
        assert stats["hits"] == 0
        assert stats["misses"] == 0

    def test_reset_stats_clears_counters(self) -> None:
        """6.11: reset_stats() clears counters."""
        cache = LlmResponseCache()
        messages = [{"role": "user", "content": "Hello"}]
        cache.get(messages, "model", 4096, 0.0)  # miss
        cache.put(messages, "model", 4096, 0.0, "cached")
        cache.get(messages, "model", 4096, 0.0)  # hit

        cache.reset_stats()
        assert cache._cache_hits == 0
        assert cache._cache_misses == 0
        stats = cache.get_cache_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0


# ── Task 7: Tests for LlmClient cache integration ───────────────


class TestLlmClientCacheIntegration:
    """Tests for LlmClient cache integration (Task 7)."""

    def _make_client(self, cache_enabled: bool = True) -> LlmClient:
        config = LlmConfig(
            provider="anthropic",
            model="claude-sonnet-4",
            api_key="key",
            cache_enabled=cache_enabled,
        )
        return LlmClient(config)

    def _mock_response(self, content: str) -> MagicMock:
        mock = MagicMock()
        mock.choices = [MagicMock()]
        mock.choices[0].message.content = content
        return mock

    def test_complete_sync_returns_cached_on_hit(self) -> None:
        """7.1: complete_sync() returns cached response (litellm NOT called)."""
        client = self._make_client()
        messages = [{"role": "user", "content": "Hello"}]

        with patch("litellm.completion") as mock_completion:
            mock_completion.return_value = self._mock_response("first response")
            # First call — miss, calls litellm
            result1 = client.complete_sync(messages)
            assert result1 == "first response"
            assert mock_completion.call_count == 1

            # Second call — hit, does NOT call litellm
            result2 = client.complete_sync(messages)
            assert result2 == "first response"
            assert mock_completion.call_count == 1  # still 1

    def test_complete_sync_cache_miss_stores_result(self) -> None:
        """7.2: complete_sync() calls litellm on miss and stores result."""
        client = self._make_client()
        messages = [{"role": "user", "content": "Hello"}]

        with patch("litellm.completion") as mock_completion:
            mock_completion.return_value = self._mock_response("new response")
            result = client.complete_sync(messages)
            assert result == "new response"
            mock_completion.assert_called_once()

        # Verify it was cached
        cached = client._cache.get(messages, "claude-sonnet-4", 4096, 0.0)
        assert cached == "new response"

    def test_complete_sync_different_models_no_cross_pollution(self) -> None:
        """7.3: Different models produce different cache keys."""
        client = self._make_client()
        messages = [{"role": "user", "content": "Hello"}]

        with patch("litellm.completion") as mock_completion:
            mock_completion.return_value = self._mock_response("default model response")
            client.complete_sync(messages)

            mock_completion.return_value = self._mock_response("screening model response")
            client.complete_sync(messages, model="claude-haiku")
            assert mock_completion.call_count == 2  # Both were misses

    @pytest.mark.asyncio
    async def test_complete_async_returns_cached_on_hit(self) -> None:
        """7.4: complete() async returns cached response on hit."""
        client = self._make_client()
        messages = [{"role": "user", "content": "Hello"}]

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = self._mock_response("async response")
            result1 = await client.complete(messages)
            assert result1 == "async response"
            assert mock_completion.call_count == 1

            # Second call — cache hit
            result2 = await client.complete(messages)
            assert result2 == "async response"
            assert mock_completion.call_count == 1  # still 1

    def test_clear_cache_invalidates_all(self) -> None:
        """7.5: clear_cache() invalidates all cached responses."""
        client = self._make_client()
        messages = [{"role": "user", "content": "Hello"}]

        with patch("litellm.completion") as mock_completion:
            mock_completion.return_value = self._mock_response("response")
            client.complete_sync(messages)

            # Clear and verify miss
            client.clear_cache()
            mock_completion.return_value = self._mock_response("new response")
            result = client.complete_sync(messages)
            assert result == "new response"
            assert mock_completion.call_count == 2

    def test_cache_disabled_always_calls_litellm(self) -> None:
        """7.6: cache_enabled=False always calls litellm."""
        client = self._make_client(cache_enabled=False)
        messages = [{"role": "user", "content": "Hello"}]

        with patch("litellm.completion") as mock_completion:
            mock_completion.return_value = self._mock_response("response")
            client.complete_sync(messages)
            client.complete_sync(messages)
            assert mock_completion.call_count == 2  # No caching

    def test_existing_llm_mocks_still_work(self) -> None:
        """7.7: Existing LLM mocks still work (backward compatibility)."""
        client = MagicMock(spec=LlmClient)
        client.complete_sync.return_value = "mocked"
        result = client.complete_sync([{"role": "user", "content": "test"}])
        assert result == "mocked"

    def test_model_usage_tracks_cached_calls(self) -> None:
        """7.8: _model_usage tracks cached calls with (cached) suffix."""
        client = self._make_client()
        messages = [{"role": "user", "content": "Hello"}]

        with patch("litellm.completion") as mock_completion:
            mock_completion.return_value = self._mock_response("response")
            client.complete_sync(messages)  # miss
            client.complete_sync(messages)  # hit

        usage = client.get_model_usage()
        assert usage["claude-sonnet-4"] == 1
        assert usage["claude-sonnet-4(cached)"] == 1

    def test_non_deterministic_temperature_skips_cache(self) -> None:
        """Cache is skipped when temperature > 0 (anti-pattern #8)."""
        client = self._make_client()
        messages = [{"role": "user", "content": "Hello"}]

        with patch("litellm.completion") as mock_completion:
            mock_completion.return_value = self._mock_response("response")
            client.complete_sync(messages, temperature=0.7)
            client.complete_sync(messages, temperature=0.7)
            assert mock_completion.call_count == 2  # No caching

    def test_empty_response_not_cached(self) -> None:
        """Empty responses are not cached (anti-pattern #5)."""
        client = self._make_client()
        messages = [{"role": "user", "content": "Hello"}]

        with patch("litellm.completion") as mock_completion:
            mock_completion.return_value = self._mock_response("")
            client.complete_sync(messages)
            # Empty response should not be cached
            cached = client._cache.get(messages, "claude-sonnet-4", 4096, 0.0)
            assert cached is None

    def test_none_response_not_cached(self) -> None:
        """None responses are not cached."""
        client = self._make_client()
        messages = [{"role": "user", "content": "Hello"}]

        mock = MagicMock()
        mock.choices = [MagicMock()]
        mock.choices[0].message.content = None

        with patch("litellm.completion") as mock_completion:
            mock_completion.return_value = mock
            result = client.complete_sync(messages)
            assert result == ""
            # None response should not be cached
            cached = client._cache.get(messages, "claude-sonnet-4", 4096, 0.0)
            assert cached is None


# ── Task 8: Tests for cache stats propagation ────────────────────


class TestCacheStatsPropagation:
    """Tests for cache stats propagation to InvestigationResult (Task 8)."""

    def test_cache_stats_in_investigation_result(self) -> None:
        """8.1: cache_stats propagated to InvestigationResult.metadata."""
        from beeper_investigator.agent import InvestigatorAgent

        agent = MagicMock(spec=InvestigatorAgent)
        agent.context = MagicMock()
        agent.context.investigation_id = "test-id"
        agent.context.service = "test-service"
        agent.context.condition = "test-cond"
        agent.context.severity = "warning"

        # Test that LlmClient.get_cache_stats returns expected structure
        config = LlmConfig(
            provider="anthropic", model="claude-sonnet-4", api_key="key"
        )
        client = LlmClient(config)
        stats = client.get_cache_stats()
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats
        assert "entries_count" in stats

    def test_cache_stats_contains_expected_keys(self) -> None:
        """8.2: cache_stats contains expected keys."""
        config = LlmConfig(
            provider="anthropic", model="claude-sonnet-4", api_key="key"
        )
        client = LlmClient(config)
        stats = client.get_cache_stats()
        expected_keys = {
            "hits", "misses", "hit_rate", "entries_count", "max_entries", "ttl_seconds",
        }
        assert set(stats.keys()) == expected_keys


# ── Task 9: LlmConfig cache configuration tests ─────────────────


class TestLlmConfigCacheFields:
    """Tests for LlmConfig cache configuration (Task 9)."""

    def test_cache_fields_correct_defaults(self) -> None:
        """9.1: LlmConfig cache fields have correct defaults."""
        config = LlmConfig(provider="anthropic", model="claude-sonnet-4", api_key="key")
        assert config.cache_ttl_seconds == 3600
        assert config.cache_max_entries == 256
        assert config.cache_enabled is True

    def test_from_env_loads_cache_env_vars(self) -> None:
        """9.2: from_env() loads cache env vars."""
        with patch.dict(
            os.environ,
            {
                "BEEPER_LLM_PROVIDER": "anthropic",
                "BEEPER_LLM_MODEL": "claude-sonnet-4",
                "BEEPER_LLM_API_KEY": "key",
                "BEEPER_LLM_CACHE_ENABLED": "false",
                "BEEPER_LLM_CACHE_TTL_SECONDS": "7200",
                "BEEPER_LLM_CACHE_MAX_ENTRIES": "512",
            },
            clear=True,
        ):
            config = LlmConfig.from_env()
            assert config.cache_enabled is False
            assert config.cache_ttl_seconds == 7200
            assert config.cache_max_entries == 512

    def test_from_env_uses_defaults_for_missing_cache_vars(self) -> None:
        """9.3: from_env() handles missing cache env vars (uses defaults)."""
        with patch.dict(
            os.environ,
            {
                "BEEPER_LLM_PROVIDER": "anthropic",
                "BEEPER_LLM_MODEL": "claude-sonnet-4",
                "BEEPER_LLM_API_KEY": "key",
            },
            clear=True,
        ):
            config = LlmConfig.from_env()
            assert config.cache_enabled is True
            assert config.cache_ttl_seconds == 3600
            assert config.cache_max_entries == 256
