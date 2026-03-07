# Story 3.10: LLM Response Caching

Status: review

## Story

As Beeper,
I want to cache and memoize LLM results to avoid redundant calls,
so that I reduce costs and improve response times for recurring patterns.

## Acceptance Criteria

1. **Given** an LLM query is made, **When** a similar query was recently made (same messages, model, temperature, max_tokens), **Then** the cached response is returned (FR45) **And** cache hit is logged for metrics.

2. **Given** an investigation encounters a recurring issue, **When** querying for analysis, **Then** prior LLM reasoning is retrieved from cache **And** only delta analysis requires new LLM calls.

3. **Given** cache entries exist, **When** the entry's TTL has expired, **Then** cache is invalidated appropriately **And** stale reasoning is not returned.

4. **Given** caching is operational, **When** reviewing costs, **Then** cache hit rate is reported **And** estimated cost savings are visible via `get_cache_stats()`.

## Tasks / Subtasks

- [x] Task 1: Create LlmResponseCache class in `llm/cache.py` (AC: 1, 2)
  - [x] 1.1 Create `investigator/beeper_investigator/llm/cache.py` with `LlmResponseCache` class
  - [x] 1.2 Add `_generate_cache_key(messages, model, max_tokens, temperature) -> str` static method using `hashlib.sha256` on `json.dumps(messages, sort_keys=True)` + model + str(max_tokens) + str(temperature)
  - [x] 1.3 Add `_entries: dict[str, CacheEntry]` instance variable storing `CacheEntry(response: str, created_at: float, model: str)`
  - [x] 1.4 Add `get(messages, model, max_tokens, temperature) -> str | None` method — returns cached response if key exists and TTL not expired, else None
  - [x] 1.5 Add `put(messages, model, max_tokens, temperature, response) -> None` method — stores response with current timestamp; evicts oldest entry if `_max_entries` exceeded
  - [x] 1.6 Add `clear() -> None` method to invalidate all cache entries
  - [x] 1.7 Add `CacheEntry` dataclass: `response: str`, `created_at: float`, `model: str`

- [x] Task 2: Add cache configuration to LlmConfig (AC: 3)
  - [x] 2.1 Add `cache_ttl_seconds: int = 3600` field to `LlmConfig` dataclass
  - [x] 2.2 Add `cache_max_entries: int = 256` field to `LlmConfig` dataclass
  - [x] 2.3 Add `cache_enabled: bool = True` field to `LlmConfig` dataclass
  - [x] 2.4 Load from env vars in `from_env()`: `BEEPER_LLM_CACHE_TTL_SECONDS`, `BEEPER_LLM_CACHE_MAX_ENTRIES`, `BEEPER_LLM_CACHE_ENABLED`

- [x] Task 3: Integrate cache into LlmClient (AC: 1, 2, 3)
  - [x] 3.1 Add `_cache: LlmResponseCache` instance variable in `LlmClient.__init__()`, initialized with config TTL and max_entries
  - [x] 3.2 In `complete_sync()`: before calling `litellm.completion()`, check `self._cache.get()` — if hit, log at INFO and return cached response; still increment `_model_usage` with a `(cached)` suffix
  - [x] 3.3 In `complete_sync()`: after successful `litellm.completion()`, call `self._cache.put()` to store result
  - [x] 3.4 In `complete()` (async): same cache check/store pattern as `complete_sync()`
  - [x] 3.5 Add `clear_cache() -> None` proxy method on `LlmClient`
  - [x] 3.6 Skip caching when `self.config.cache_enabled is False`

- [x] Task 4: Add cache metrics tracking (AC: 4)
  - [x] 4.1 Add `_cache_hits: int` and `_cache_misses: int` counters to `LlmResponseCache`
  - [x] 4.2 Increment `_cache_hits` in `get()` on hit, `_cache_misses` on miss
  - [x] 4.3 Add `get_cache_stats() -> dict[str, Any]` method returning: `hits`, `misses`, `hit_rate` (float 0-1), `entries_count`, `max_entries`, `ttl_seconds`
  - [x] 4.4 Add `reset_stats() -> None` method

- [x] Task 5: Propagate cache stats to InvestigationResult (AC: 4)
  - [x] 5.1 In `agent.py`, after `_run_steps()` completes, call `self.llm_client.get_cache_stats()` and include in `InvestigationResult.metadata` under key `cache_stats`
  - [x] 5.2 Verify `cache_stats` is NOT in `_RESERVED_KEYS` set (it is not)

- [x] Task 6: Tests for LlmResponseCache (AC: all)
  - [x] 6.1 Test `_generate_cache_key()` produces deterministic hash for same inputs
  - [x] 6.2 Test `_generate_cache_key()` produces different hash for different messages
  - [x] 6.3 Test `_generate_cache_key()` produces different hash for different model/max_tokens/temperature
  - [x] 6.4 Test `get()` returns None on cache miss
  - [x] 6.5 Test `put()` then `get()` returns cached response (cache hit)
  - [x] 6.6 Test `get()` returns None after TTL expires (use time mocking)
  - [x] 6.7 Test `put()` evicts oldest entry when `_max_entries` exceeded
  - [x] 6.8 Test `clear()` removes all entries
  - [x] 6.9 Test cache hit/miss counters are incremented correctly
  - [x] 6.10 Test `get_cache_stats()` returns correct hit_rate calculation
  - [x] 6.11 Test `reset_stats()` clears counters

- [x] Task 7: Tests for LlmClient cache integration (AC: 1, 2, 3)
  - [x] 7.1 Test `complete_sync()` returns cached response on cache hit (litellm.completion NOT called)
  - [x] 7.2 Test `complete_sync()` calls litellm.completion on cache miss and stores result
  - [x] 7.3 Test `complete_sync()` with different models produces different cache keys (no cross-model pollution)
  - [x] 7.4 Test `complete()` async returns cached response on hit
  - [x] 7.5 Test `clear_cache()` invalidates all cached responses
  - [x] 7.6 Test cache disabled via `cache_enabled=False` — always calls litellm
  - [x] 7.7 Test existing LLM mocks still work (backward compatibility)
  - [x] 7.8 Test `_model_usage` tracks cached calls with `(cached)` suffix

- [x] Task 8: Tests for cache stats propagation (AC: 4)
  - [x] 8.1 Test `cache_stats` propagated to `InvestigationResult.metadata`
  - [x] 8.2 Test `cache_stats` contains expected keys (hits, misses, hit_rate, entries_count)

- [x] Task 9: LlmConfig cache configuration tests (AC: 3)
  - [x] 9.1 Test `LlmConfig` cache fields have correct defaults (TTL=3600, max=256, enabled=True)
  - [x] 9.2 Test `from_env()` loads cache env vars
  - [x] 9.3 Test `from_env()` handles missing cache env vars (uses defaults)

## Dev Notes

### Architecture Decision: File Location

The architecture document (`architecture.md:630`) specifies `llm/cost.py` for FR45-47 (cost tracking, memoization). However, since Story 6.2 (LLM spending caps) will also use `cost.py` for its own concerns, and caching is a distinct responsibility, create a dedicated `llm/cache.py` module. This keeps separation of concerns clean and avoids a premature mega-module.

### Cache Design: In-Memory Dict

Use a simple in-memory `dict[str, CacheEntry]` — same pattern as `_model_usage` in LlmClient. Rationale:
- Investigator pods are short-lived K8s Jobs (one per investigation)
- No persistence needed between pod restarts
- No external dependency (Redis/file)
- Cache is most valuable WITHIN a single investigation for recurring sub-queries
- Cross-investigation caching would require shared state, which is a different story scope

### Cache Key Generation

Use `hashlib.sha256` on deterministic serialization:

```python
import hashlib
import json

@staticmethod
def _generate_cache_key(
    messages: list[dict[str, str]],
    model: str,
    max_tokens: int,
    temperature: float,
) -> str:
    key_data = json.dumps(messages, sort_keys=True) + f"|{model}|{max_tokens}|{temperature}"
    return hashlib.sha256(key_data.encode()).hexdigest()
```

**Why include model/max_tokens/temperature:**
- Different models produce different outputs for same prompt
- Different max_tokens could truncate differently
- Different temperature changes randomness (though Beeper uses 0.0 everywhere)

### Cache Integration — Transparent Wrapping

Cache logic goes INSIDE `complete_sync()` and `complete()` — **no step code changes required**. Steps already call these methods and receive strings. The cache is invisible to consumers:

```python
def complete_sync(self, messages, max_tokens=4096, temperature=0.0, *, model=None, **kwargs):
    effective_model = model or self.config.get_litellm_model()

    # Cache check
    if self.config.cache_enabled:
        cached = self._cache.get(messages, effective_model, max_tokens, temperature)
        if cached is not None:
            logger.info("Cache hit for model %s", effective_model)
            self._model_usage[f"{effective_model}(cached)"] = (
                self._model_usage.get(f"{effective_model}(cached)", 0) + 1
            )
            return cached

    # LLM call (existing code)
    response = litellm.completion(...)
    content = response.choices[0].message.content
    self._model_usage[effective_model] = self._model_usage.get(effective_model, 0) + 1

    # Cache store
    if self.config.cache_enabled and content:
        self._cache.put(messages, effective_model, max_tokens, temperature, content)

    return content or ""
```

### TTL Expiration

```python
from dataclasses import dataclass
import time

@dataclass
class CacheEntry:
    response: str
    created_at: float
    model: str

# In get():
entry = self._entries.get(key)
if entry and (time.monotonic() - entry.created_at) < self._ttl_seconds:
    self._cache_hits += 1
    return entry.response
# expired or missing
if entry:
    del self._entries[key]  # clean up expired
self._cache_misses += 1
return None
```

Use `time.monotonic()` (not `time.time()`) for TTL — immune to system clock changes.

### LRU-Style Eviction

When `_max_entries` is reached, evict the oldest entry by `created_at`:

```python
def put(self, messages, model, max_tokens, temperature, response):
    key = self._generate_cache_key(messages, model, max_tokens, temperature)
    if len(self._entries) >= self._max_entries:
        oldest_key = min(self._entries, key=lambda k: self._entries[k].created_at)
        del self._entries[oldest_key]
    self._entries[key] = CacheEntry(
        response=response,
        created_at=time.monotonic(),
        model=model,
    )
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `BEEPER_LLM_CACHE_ENABLED` | `true` | Enable/disable caching |
| `BEEPER_LLM_CACHE_TTL_SECONDS` | `3600` | Cache entry time-to-live |
| `BEEPER_LLM_CACHE_MAX_ENTRIES` | `256` | Maximum cache entries before eviction |

Follow the existing `from_env()` pattern in `LlmConfig`:

```python
cache_enabled = os.environ.get("BEEPER_LLM_CACHE_ENABLED", "true").lower() != "false"
cache_ttl_seconds = int(os.environ.get("BEEPER_LLM_CACHE_TTL_SECONDS", "3600"))
cache_max_entries = int(os.environ.get("BEEPER_LLM_CACHE_MAX_ENTRIES", "256"))
```

### Cache Stats

```python
def get_cache_stats(self) -> dict[str, Any]:
    total = self._cache_hits + self._cache_misses
    return {
        "hits": self._cache_hits,
        "misses": self._cache_misses,
        "hit_rate": self._cache_hits / total if total > 0 else 0.0,
        "entries_count": len(self._entries),
        "max_entries": self._max_entries,
        "ttl_seconds": self._ttl_seconds,
    }
```

### Backward Compatibility

- **No step code changes** — caching is transparent inside LlmClient
- **Existing mocks still work** — `MagicMock()` for `LlmClient` won't have cache behavior; tests that mock `complete_sync()` directly are unaffected
- **`_model_usage` tracking preserved** — cached calls tracked with `(cached)` suffix so cost reporting can distinguish

### Critical Anti-Patterns to Avoid

1. **Do NOT add caching to `embed_sync()`** — embedding calls are separate from completion caching and use a different API
2. **Do NOT use `functools.lru_cache`** — it can't handle mutable dict arguments (messages list) and doesn't support TTL
3. **Do NOT add Redis or external dependencies** — investigator pods are ephemeral K8s Jobs; in-memory is sufficient
4. **Do NOT modify step files** — caching is transparent inside LlmClient
5. **Do NOT cache empty responses** — only cache non-empty content strings
6. **Do NOT use `time.time()` for TTL** — use `time.monotonic()` for clock-change immunity
7. **Do NOT add token counting or cost estimation** — that's Story 6.2 (LLM spending caps)
8. **Do NOT cache when temperature > 0** — non-deterministic responses should not be cached (Beeper uses 0.0 everywhere, but guard against future changes)
9. **Do NOT break the `**kwargs` passthrough** — `kwargs` should NOT be part of cache key (they contain LiteLLM-internal options)
10. **Do NOT persist cache to disk** — pod lifecycle handles cleanup naturally

### Existing Code to Modify

| File | Change |
|------|--------|
| `llm/client.py` | Add cache config fields to `LlmConfig`, integrate `LlmResponseCache` into `LlmClient` |
| `agent.py` | Add `cache_stats` propagation to `InvestigationResult.metadata` |

### New Files to Create

| File | Purpose |
|------|---------|
| `llm/cache.py` | `LlmResponseCache` class with cache key generation, TTL, eviction, metrics |
| `tests/test_llm_cache.py` | Comprehensive tests for cache behavior, LlmClient integration, stats propagation |

### Project Structure Notes

```
investigator/beeper_investigator/
├── llm/
│   ├── __init__.py
│   ├── client.py            # MODIFY: cache config in LlmConfig, cache integration in LlmClient
│   ├── cache.py             # NEW: LlmResponseCache, CacheEntry
│   └── prompts.py           # NOT modified
├── agent.py                 # MODIFY: cache_stats propagation after _run_steps()

investigator/tests/
├── test_llm_cache.py        # NEW: comprehensive cache tests
├── test_llm_client.py       # NOT modified (existing mocks still work)
├── test_llm_screening.py    # NOT modified
└── ...
```

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic-3, Story 3.10] — FR45, AC1-AC4
- [Source: _bmad-output/planning-artifacts/prd.md#FR45] — Cache and memoize results to avoid redundant LLM calls
- [Source: _bmad-output/planning-artifacts/prd.md#Risk-Mitigation] — Memoization as cost mitigation strategy
- [Source: _bmad-output/planning-artifacts/architecture.md#line-630] — `cost.py # FR45-47: Cost tracking, memoization`
- [Source: investigator/beeper_investigator/llm/client.py] — LlmConfig, LlmClient, complete_sync(), complete()
- [Source: _bmad-output/implementation-artifacts/3-9-tiered-llm-model-selection.md] — Model usage tracking pattern, _model_usage dict
- [Source: investigator/beeper_investigator/agent.py] — model_usage propagation pattern to InvestigationResult.metadata

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

None required — all tests passed on first run.

### Completion Notes List

- Created `llm/cache.py` with `LlmResponseCache` class: SHA-256 cache key generation, TTL-based expiration via `time.monotonic()`, LRU-style eviction, hit/miss metrics tracking
- Added `cache_ttl_seconds`, `cache_max_entries`, `cache_enabled` fields to `LlmConfig` with env var loading (`BEEPER_LLM_CACHE_*`)
- Integrated cache transparently into `LlmClient.complete_sync()` and `complete()` — no step code changes required
- Cache skips non-deterministic responses (temperature > 0) and empty/None responses per anti-patterns #5 and #8
- Cached calls tracked in `_model_usage` with `(cached)` suffix for cost reporting distinction
- Added `cache_stats` propagation to `InvestigationResult.metadata` in `agent.py`
- 30 new tests covering all 9 tasks: cache key generation, get/put/clear/eviction/TTL, LlmClient integration (sync+async), cache stats propagation, LlmConfig defaults and env var loading
- Fixed pre-existing mypy type issue in `test_tiered_model_selection.py` caused by new `int`/`bool` config fields
- Full regression suite: 373 passed, 3 skipped, 0 failures
- Ruff: all checks passed
- Mypy: only pre-existing issues in `test_investigation_documentation.py` (8 errors, all from story 3-8)

### Change Log

- 2026-03-06: Implemented LLM Response Caching (Story 3-10) — all 9 tasks, 31 subtasks complete with 30 new tests

### File List

- `investigator/beeper_investigator/llm/cache.py` (NEW) — LlmResponseCache, CacheEntry
- `investigator/beeper_investigator/llm/client.py` (MODIFIED) — cache config in LlmConfig, cache integration in LlmClient
- `investigator/beeper_investigator/agent.py` (MODIFIED) — cache_stats propagation to InvestigationResult.metadata
- `investigator/tests/test_llm_cache.py` (NEW) — 30 comprehensive cache tests
- `investigator/tests/test_tiered_model_selection.py` (MODIFIED) — fixed mypy type annotation for `_make_config` helper
