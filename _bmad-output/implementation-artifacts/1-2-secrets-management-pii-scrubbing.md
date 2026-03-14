# Story 1.2: Secrets Management & PII Scrubbing

Status: done

## Story

As a **platform operator**,
I want integration credentials stored securely and sensitive data scrubbed before LLM calls,
so that Beeper never leaks PII or credentials to external providers.

## Acceptance Criteria

1. **AC1: Credential storage via K8s Secrets**
   **Given** a new integration (Slack, PagerDuty, Git) requires credentials
   **When** the credential is configured
   **Then** it is stored as a K8s Secret with encryption at rest
   **And** never stored in Qdrant or application config

2. **AC2: PII scrubbing before LLM calls**
   **Given** investigation context containing email addresses, IP addresses, tokens, or passwords
   **When** the investigator prepares context for an LLM call
   **Then** the PII scrubber replaces sensitive data with tagged placeholders (e.g., `[SCRUBBED:email]`)
   **And** an audit log of scrubbed content is stored locally (never sent to LLM)
   **And** the scrubber runs before every LLM call regardless of tier

3. **AC3: Configurable scrub rules**
   **Given** a configurable scrub rule set
   **When** a new pattern is added
   **Then** it applies to all subsequent LLM calls without restart

## Tasks / Subtasks

- [x] Task 1: Create PII scrubber module (AC: #2, #3)
  - [x] 1.1: Create `investigator/beeper_investigator/llm/scrubber.py` with `PiiScrubber` class
  - [x] 1.2: Implement default regex patterns for common PII: emails, IPv4/IPv6 addresses, JWT tokens, Bearer tokens, API keys, passwords in env vars, AWS keys, connection strings
  - [x] 1.3: Implement tagged placeholder replacement (e.g., `[SCRUBBED:email]`, `[SCRUBBED:ip_address]`, `[SCRUBBED:token]`)
  - [x] 1.4: Implement audit log — `ScrubAuditEntry` dataclass recording original value, scrubbed type, field location, timestamp; stored locally via structured JSON logging (never sent to LLM)
  - [x] 1.5: Implement `scrub_messages()` method that processes `list[dict[str, str]]` (LLM message format) and returns scrubbed copy + audit entries
  - [x] 1.6: Implement `scrub_text()` method for single-string scrubbing (used for embed_sync text)

- [x] Task 2: Implement configurable scrub rules (AC: #3)
  - [x] 2.1: Implement `ScrubRule` dataclass with `name`, `pattern` (regex), `placeholder_tag`, `enabled` fields
  - [x] 2.2: Support loading custom rules from `BEEPER_SCRUB_RULES_JSON` environment variable (JSON array of rule objects)
  - [x] 2.3: Support `add_rule()` and `remove_rule()` methods for runtime rule modification without restart
  - [x] 2.4: Default rules are always active; custom rules merge with (not replace) defaults

- [x] Task 3: Integrate scrubber into LLM client (AC: #2)
  - [x] 3.1: Modify `LlmClient.__init__()` in `llm/client.py` to instantiate `PiiScrubber` (loading custom rules from env)
  - [x] 3.2: Modify `complete_sync()` to scrub messages before the LiteLLM call (after cache check, before `litellm.completion()`)
  - [x] 3.3: Modify `complete()` (async) to scrub messages before the LiteLLM call (after cache check, before `litellm.acompletion()`)
  - [x] 3.4: Modify `embed_sync()` to scrub text before the LiteLLM embedding call
  - [x] 3.5: Log audit entries via structured JSON logging after each scrub operation

- [x] Task 4: Validate K8s Secrets credential pattern (AC: #1)
  - [x] 4.1: Verify existing credential storage pattern in `llm/client.py` — API keys come from env vars (K8s Secrets → env injection), never stored in Qdrant or config files
  - [x] 4.2: Add documentation comment in `_configure_litellm()` asserting the K8s Secrets pattern for credential injection
  - [x] 4.3: Verify Helm chart `secrets.yaml` template references for credential storage pattern
  - [x] 4.4: Add a test verifying that LlmConfig does NOT persist credentials to any storage backend

- [x] Task 5: Write comprehensive tests (AC: #1, #2, #3)
  - [x] 5.1: Create `investigator/tests/test_scrubber.py` with comprehensive PII scrubbing tests
  - [x] 5.2: Test email scrubbing — various formats (user@domain.com, user+tag@domain.co.uk)
  - [x] 5.3: Test IP address scrubbing — IPv4 (192.168.1.1) and IPv6 (::1, fe80::1)
  - [x] 5.4: Test token scrubbing — JWT tokens, Bearer tokens, API keys (sk-xxx, ghp_xxx, xoxb-xxx)
  - [x] 5.5: Test password scrubbing — password=xxx, PASSWORD: xxx, connection strings with passwords
  - [x] 5.6: Test AWS key scrubbing — AKIA/ASIA prefixed keys
  - [x] 5.7: Test placeholder format correctness — `[SCRUBBED:email]`, `[SCRUBBED:ip_address]` etc.
  - [x] 5.8: Test audit log entries — verify original value captured, type recorded, timestamp present
  - [x] 5.9: Test scrub_messages() — multi-message lists, system + user messages, preserves message structure
  - [x] 5.10: Test scrub_text() — single string input for embedding use case
  - [x] 5.11: Test custom scrub rules — add via env var, runtime add/remove, merge with defaults
  - [x] 5.12: Test LLM client integration — verify complete_sync() calls scrubber before LiteLLM
  - [x] 5.13: Test LLM client integration — verify complete() (async) calls scrubber before LiteLLM
  - [x] 5.14: Test LLM client integration — verify embed_sync() calls scrubber before LiteLLM
  - [x] 5.15: Test no false positives — service names, metric names, normal text not scrubbed
  - [x] 5.16: Test configurable rules apply without restart
  - [x] 5.17: Test credential non-persistence — verify API keys not stored in Qdrant or config
  - [x] 5.18: Run full existing test suite (406 investigator + 657 UI tests) to confirm zero regressions

## Dev Notes

### Architecture Compliance

**PII Scrubbing (NFR11 — from architecture.md):**
Applied before every LLM call in the investigator:
1. Regex patterns for common PII (emails, IPs, tokens, passwords in env vars)
2. Configurable per-service scrub rules via investigation context
3. Replacement with tagged placeholders (`[SCRUBBED:email]`) to preserve context
4. Audit log of scrubbed content (stored locally, never sent to LLM)
[Source: _bmad-output/planning-artifacts/architecture.md#LLM Integration (Extended)]

**Secrets Storage Pattern (NFR10):**
All integration credentials (Slack, PagerDuty, Git tokens, LLM keys) stored as K8s Secrets with encryption at rest. Never stored in Beeper's database (Qdrant).
[Source: _bmad-output/planning-artifacts/architecture.md#Authentication & Security]

**File Location:**
Architecture specifies `investigator/beeper_investigator/llm/scrubber.py` as the new file location.
[Source: _bmad-output/planning-artifacts/architecture.md#Code Structure]

### Implementation Approach

**Key Design Decisions:**

1. **Scrubber integration point: LLM client methods.** The scrubber is called inside `LlmClient.complete_sync()`, `LlmClient.complete()`, and `LlmClient.embed_sync()` as a final checkpoint before any data reaches LiteLLM. This ensures ALL LLM calls are scrubbed regardless of which step calls them, and prevents any code path from accidentally bypassing scrubbing.

2. **Scrubber is NOT middleware.** Unlike the UI permission model (story 1-1), the scrubber is NOT a Flask middleware or a request interceptor. It is a module within the investigator's `llm/` package that processes message content before LLM provider calls.

3. **Default regex patterns** must cover:
   - Email addresses: `\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b`
   - IPv4 addresses: `\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b`
   - IPv6 addresses: common formats including `::1`, `fe80::`, full 8-group
   - JWT tokens: `eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+`
   - Bearer tokens: `Bearer\s+[A-Za-z0-9._~+/=-]+`
   - API keys: patterns for `sk-`, `ghp_`, `gho_`, `xoxb-`, `xoxp-`
   - AWS keys: `(AKIA|ASIA)[A-Z0-9]{16}`
   - Password patterns: `(?:password|passwd|pwd|secret)\s*[:=]\s*\S+`
   - Connection strings with credentials: `://[^:]+:[^@]+@`

4. **Tagged placeholder format:** `[SCRUBBED:{type}]` where type is one of: `email`, `ip_address`, `ipv6_address`, `jwt_token`, `bearer_token`, `api_key`, `aws_key`, `password`, `credential_url`, or a custom rule name.

5. **Audit logging via structured JSON** (follows architecture Process Patterns):
   ```json
   {
     "timestamp": "2026-01-28T14:30:00Z",
     "level": "INFO",
     "component": "investigator",
     "message": "PII scrubbed from LLM context",
     "context": {
       "investigation_id": "inv-abc123",
       "scrub_count": 3,
       "scrub_types": ["email", "ip_address", "token"],
       "method": "complete_sync"
     }
   }
   ```
   The actual scrubbed values are logged at DEBUG level only for forensic analysis.
   [Source: _bmad-output/planning-artifacts/architecture.md#Process Patterns]

6. **Custom rules via environment variable:** `BEEPER_SCRUB_RULES_JSON` expects a JSON array:
   ```json
   [
     {"name": "internal_id", "pattern": "CUST-[0-9]{6}", "placeholder_tag": "customer_id"},
     {"name": "phone", "pattern": "\\b\\d{3}[-.]\\d{3}[-.]\\d{4}\\b", "placeholder_tag": "phone"}
   ]
   ```
   This allows operators to add custom rules without code changes or restarts.

7. **K8s Secrets credential pattern is already implemented.** The existing `LlmConfig.from_env()` reads `BEEPER_LLM_API_KEY` from environment variables. In production, K8s injects these from Secrets (see `helm/beeper/templates/secrets.yaml`). This story validates and documents the pattern but does NOT need to implement new credential storage — it already works correctly.

8. **The scrubber must NOT modify the original messages list.** It should create a deep copy of the messages before scrubbing to avoid side effects on cached data or shared references.

### Technical Requirements

- **Python 3.11+** — use `|` union types, not `Optional[]`
- **No new dependencies** — use only `re` (stdlib) for regex, `json` for custom rules parsing, `logging` for audit, `dataclasses` for models
- **Pydantic NOT required** — use `@dataclass` for `ScrubRule` and `ScrubAuditEntry`
- **Thread safety** — `PiiScrubber` must be safe for concurrent use (use `re.compile()` for compiled patterns, no mutable shared state beyond rules list)

### File Structure Requirements

**New files to create:**
```
investigator/beeper_investigator/llm/scrubber.py  # PiiScrubber class + ScrubRule + ScrubAuditEntry
investigator/tests/test_scrubber.py               # Comprehensive PII scrubbing tests
```

**Files to modify:**
```
investigator/beeper_investigator/llm/__init__.py   # Export PiiScrubber
investigator/beeper_investigator/llm/client.py     # Integrate scrubber into complete/complete_sync/embed_sync
```

**Files to verify (read-only):**
```
helm/beeper/templates/secrets.yaml                 # Verify K8s Secrets pattern
investigator/beeper_investigator/context.py         # Understand context fields (no changes)
```

### Testing Requirements

- **Framework:** pytest (existing)
- **Mocking:** `unittest.mock.patch`, `MagicMock` for LiteLLM calls (existing pattern from `test_llm_client.py`)
- **Test isolation:** Each test should create its own `PiiScrubber` instance; integration tests mock LiteLLM to verify scrubbing occurs
- **Class-based test organization:** Use `class TestPiiScrubber`, `class TestScrubRules`, `class TestLlmClientScrubbing` pattern (existing convention)
- **Regression testing:** Run full `poetry run pytest` and `poetry run ruff check .` and `poetry run mypy .`
- **Target:** All 406 existing investigator tests + 657 UI tests MUST continue passing. New scrubber tests should add ~30-40 tests.

### Critical Guardrails

1. **DO NOT store credentials in Qdrant, config files, or any application database.** Credentials flow exclusively through K8s Secrets → env vars → LiteLLM.
2. **DO NOT send audit log content to LLM providers.** Audit entries with original scrubbed values are logged locally only (DEBUG level).
3. **DO NOT modify the original messages list.** Create a deep copy before scrubbing.
4. **DO NOT scrub LLM responses** — only scrub outgoing messages (input to LLM). Responses come from the LLM and do not contain user PII.
5. **DO NOT add new Python dependencies.** Use only stdlib (`re`, `json`, `logging`, `dataclasses`, `copy`, `datetime`).
6. **DO NOT modify investigation step files** (`steps/*.py`). Scrubbing happens in the LLM client layer, not in individual steps.
7. **DO NOT break the existing LLM caching.** Cache lookup happens with original (unscrubbed) messages for cache-key stability. Scrubbing happens after cache miss, before the actual LLM call.
8. **DO NOT scrub service names, metric names, or Prometheus/Loki query syntax** — these are operational context, not PII.
9. **The scrubber must run for ALL model tiers** (screening, standard, deep_rca) — no exceptions.

### Previous Story Intelligence

**Story 1-1 (Permission Model Enforcement) — Completed:**
- Created middleware package at `ui/beeper_ui/middleware/` — similar pattern for investigator `llm/scrubber.py`
- Used `@dataclass` pattern for config — follow same approach for `ScrubRule` and `ScrubAuditEntry`
- Test pattern: class-based organization (`class TestXxx`), `patch.dict(os.environ, ...)` for env var testing
- RFC 7807 error format established — not applicable to scrubber (no HTTP responses)
- Ruff + mypy must be clean on all new files
- 28 tests added in story 1-1, now 657 UI tests total (626 original + 28 + 3 from review)

**Key learnings from 1-1 code review:**
- HIGH security fix: K8s JWT parsing had fallthrough vulnerability — always validate edge cases in security-critical code
- Test coverage must include bypass/abuse scenarios — add tests for scrubber bypass attempts (e.g., obfuscated PII, split tokens)
- `_RoleClient` wrapper pattern in conftest.py shows how to inject test behavior — similar wrapper approach for scrubber test fixtures

### Project Structure Notes

- Alignment with unified project structure: New `scrubber.py` goes in existing `llm/` package under `beeper_investigator/`, following the architecture's explicit file structure
- The architecture specifies `scrubber.py` in `llm/` (not a separate `utils/` or `security/` package) because PII scrubbing is tightly coupled to LLM context assembly
- Test file `test_scrubber.py` follows existing naming convention in `investigator/tests/`

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#LLM Integration (Extended)] — PII scrubbing design (NFR11)
- [Source: _bmad-output/planning-artifacts/architecture.md#Authentication & Security] — K8s Secrets credential storage (NFR10)
- [Source: _bmad-output/planning-artifacts/architecture.md#Code Structure] — File placement: `llm/scrubber.py`
- [Source: _bmad-output/planning-artifacts/architecture.md#Process Patterns] — Structured JSON logging format
- [Source: _bmad-output/planning-artifacts/architecture.md#Format Patterns] — RFC 7807 (reference only, not used here)
- [Source: _bmad-output/planning-artifacts/architecture.md#NFR Coverage] — NFR10 (K8s Secrets), NFR11 (PII scrubbing)
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.2] — Acceptance criteria and user story
- [Source: _bmad-output/planning-artifacts/prd.md#FR59] — FR59: K8s Secrets with encryption at rest
- [Source: _bmad-output/planning-artifacts/prd.md#FR60] — FR60: Scrub sensitive data before LLM calls

### Git Intelligence

- Recent commits: `f884600` marked 1-1 done, `b117c6b` implemented 1-1 (Permission Model Enforcement)
- Code patterns: `@dataclass` for configs, `patch.dict(os.environ, ...)` for env var testing, class-based test organization
- LLM client (`llm/client.py`) has clear insertion points: `complete_sync()` line 330, `complete()` line 261, `embed_sync()` line 408
- 406 investigator tests, 657 UI tests — all passing as of latest commit
- No existing scrubbing code in investigator — fully greenfield implementation

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

N/A — clean implementation with one test ordering fix (credential_url regex moved before email regex to prevent false match on connection strings).

### Completion Notes List

- Created `PiiScrubber` class in `investigator/beeper_investigator/llm/scrubber.py` with 11 default regex-based scrub rules
- Rule ordering: `credential_url` before `email` to prevent connection string false matches
- `ScrubRule` frozen dataclass with compiled regex, `ScrubAuditEntry` for audit trail, `ScrubResult` with scrubbed_count property
- `scrub_text()` for single strings (embedding use case), `scrub_messages()` for LLM message lists (deep copy — original unmodified)
- `PiiScrubber.from_env()` loads custom rules from `BEEPER_SCRUB_RULES_JSON` env var (JSON array), merges with defaults
- `add_rule()` / `remove_rule()` for runtime modification without restart
- Integrated into `LlmClient`: `complete_sync()`, `complete()` (async), and `embed_sync()` all scrub before LiteLLM calls
- Audit logging: INFO-level structured JSON summary, DEBUG-level individual scrubbed values (never sent to LLM)
- K8s Secrets credential pattern validated and documented in `_configure_litellm()` docstring (NFR10)
- 74 new tests across 14 test classes covering all 3 acceptance criteria
- All 480 investigator tests pass (406 existing + 74 new), zero regressions
- All 657 UI tests pass, zero regressions
- Ruff clean, mypy clean on all new and modified files
- No new dependencies — uses only stdlib (`re`, `json`, `logging`, `dataclasses`, `copy`, `datetime`)

### File List

- `investigator/beeper_investigator/llm/scrubber.py` (new)
- `investigator/beeper_investigator/llm/__init__.py` (modified — added PiiScrubber, ScrubRule, ScrubAuditEntry, ScrubResult exports)
- `investigator/beeper_investigator/llm/client.py` (modified — integrated scrubber into complete/complete_sync/embed_sync, added K8s Secrets docstring)
- `investigator/tests/test_scrubber.py` (new)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified)
- `_bmad-output/implementation-artifacts/1-2-secrets-management-pii-scrubbing.md` (modified)
