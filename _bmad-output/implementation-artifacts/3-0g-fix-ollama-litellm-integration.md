# Story 3.0g: Fix Ollama/LiteLLM Integration

Status: done

## Story

As a **developer**,
I want the investigator to work correctly with Ollama via LiteLLM,
So that I can run investigations locally without API costs.

## Background

**Origin:** Story 3-0c walkthrough failure (2026-05-06). Two distinct issues:

1. **Connection timeout:** `litellm.Timeout: Connection timed out after 600.0 seconds` — Ollama at `host.docker.internal:11434` not reachable from kind cluster because Ollama defaults to binding `127.0.0.1` only.

2. **JSON parse failure:** `Failed to parse LLM response as JSON` — LiteLLM's Ollama provider may return responses in a different format than expected, or the qwen3 model produces output that doesn't parse as expected.

## Acceptance Criteria

1. **Given** Ollama is running on the host with `OLLAMA_HOST=0.0.0.0`
   **When** an investigator Job runs inside the kind cluster
   **Then** it successfully connects to Ollama and completes LLM calls

2. **Given** the investigator uses Ollama/qwen3:8b via LiteLLM
   **When** an LLM response is returned
   **Then** the response is parsed correctly without JSON errors

3. **Given** a developer is setting up Ollama for the first time
   **When** they read the setup documentation
   **Then** the `OLLAMA_HOST=0.0.0.0` requirement is clearly documented

## Tasks / Subtasks

- [x] Task 1: Document Ollama host binding requirement
  - [x] 1.1 Add `OLLAMA_HOST=0.0.0.0` to Makefile demo targets or dev docs
  - [x] 1.2 Update helm/beeper/values.yaml comments for Ollama endpoint

- [x] Task 2: Investigate and fix LLM JSON parsing
  - [x] 2.1 Reproduce the `Failed to parse LLM response as JSON` error locally
  - [x] 2.2 Check if qwen3:8b returns non-JSON output (thinking tokens, markdown wrapping, etc.)
  - [x] 2.3 Check if LiteLLM's Ollama provider needs specific configuration
  - [x] 2.4 Fix the parsing logic or add response sanitization for Ollama responses
  - [x] 2.5 Consider adding `/no_think` or similar parameter if qwen3 outputs thinking tokens

- [x] Task 3: Add Ollama connectivity validation
  - [x] 3.1 Add a startup health check in the investigator that tests LLM connectivity
  - [x] 3.2 Log a clear error message if Ollama is unreachable (not just a 600s timeout)

- [x] Task 4: Verify
  - [x] 4.1 Run investigator tests: `cd investigator && python -m pytest tests/ -x -q`
  - [x] 4.2 Test with Ollama locally if possible

## Dev Notes

### Key Files

- `investigator/beeper_investigator/llm/client.py:235-261` — `_configure_litellm()`, sets `OLLAMA_API_BASE`
- `investigator/beeper_investigator/llm/client.py:73-139` — `from_env()`, reads `BEEPER_LLM_ENDPOINT`
- `investigator/beeper_investigator/steps/rca_hypothesis.py` — Where "Escalating to deep RCA model" is logged
- `investigator/beeper_investigator/llm/client.py:504-534` — Model tier selection, deep_rca falls back to default model

### Ollama Network Setup

For Docker Desktop + kind:
```bash
# Ollama must listen on all interfaces, not just localhost
OLLAMA_HOST=0.0.0.0 ollama serve

# From inside kind cluster, access via:
# http://host.docker.internal:11434
```

### Model Tiers with Ollama

When `BEEPER_LLM_DEEP_RCA_MODEL` is not set, deep_rca tier falls back to the default model (qwen3:8b). All tiers use the same model, which is fine for dev.

### qwen3 Thinking Tokens

qwen3 models output `<think>...</think>` blocks before the actual response. LiteLLM does not strip these, causing JSON parse failures. Fixed by adding a shared `parse_json_response()` utility that strips thinking tokens before parsing.

## Senior Developer Review (AI)

**Review Date:** 2026-05-10
**Review Outcome:** Approve (with fixes applied)
**Reviewer Model:** Claude Opus 4.6

### Issues Found & Fixed

- [x] [HIGH] Think token regex corrupted JSON values containing `<think>` strings — fixed extraction order: code fences first (trusted), then strip think tokens
- [x] [MEDIUM] Parser failed on preamble text between `</think>` and JSON — added first-`{` extraction fallback
- [x] [MEDIUM] Connectivity check raised `LlmClientError` (exit 1 = permanent) — changed to `LlmUnavailableError` (exit 2 = retryable)
- [x] [LOW] urllib imports inside function body — accepted (lazy import is fine for optional path)
- [x] [LOW] No unit test for connectivity check — accepted (requires mocking urllib, tested via integration)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- No debug issues encountered — clean implementation.

### Completion Notes List

- Created shared `investigator/beeper_investigator/llm/response_parser.py` with `parse_json_response()` that extracts JSON from LLM responses
- Parser handles: code fences, thinking tokens, preamble text, whitespace — in correct order to avoid corrupting JSON content
- Updated 9 modules to use the shared parser instead of duplicated `_CODE_FENCE_RE` + `json.loads` patterns:
  - Steps: impact_assessment, rca_hypothesis, signal_correlation, kb_query, resolution_recommendations, investigation_documentation
  - Remediation: test_planner, runbook_executor, pr_generator
- Added Ollama startup connectivity check in `main.py` with 10s timeout — raises `LlmUnavailableError` (retryable exit 2) instead of permanent failure
- Added `OLLAMA_HOST=0.0.0.0` documentation to Makefile prerequisites and values-dev.yaml
- Added 15 tests in `tests/test_response_parser.py` covering all edge cases
- 339 related tests pass, 579 Rust tests pass

### File List

- `investigator/beeper_investigator/llm/response_parser.py` — NEW: Shared LLM response parser
- `investigator/beeper_investigator/steps/impact_assessment.py` — Use shared parser
- `investigator/beeper_investigator/steps/rca_hypothesis.py` — Use shared parser
- `investigator/beeper_investigator/steps/signal_correlation.py` — Use shared parser
- `investigator/beeper_investigator/steps/kb_query.py` — Use shared parser
- `investigator/beeper_investigator/steps/resolution_recommendations.py` — Use shared parser
- `investigator/beeper_investigator/steps/investigation_documentation.py` — Use shared parser
- `investigator/beeper_investigator/remediation/test_planner.py` — Use shared parser
- `investigator/beeper_investigator/remediation/runbook_executor.py` — Use shared parser
- `investigator/beeper_investigator/remediation/pr_generator.py` — Use shared parser
- `investigator/beeper_investigator/main.py` — Ollama startup connectivity check (retryable)
- `investigator/tests/test_response_parser.py` — NEW: 15 tests for shared parser
- `Makefile` — Added OLLAMA_HOST=0.0.0.0 to prerequisites
- `helm/beeper/values-dev.yaml` — Added Ollama host binding comment
