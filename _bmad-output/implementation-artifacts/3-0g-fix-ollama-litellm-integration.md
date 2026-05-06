# Story 3.0g: Fix Ollama/LiteLLM Integration

Status: ready-for-dev

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

- [ ] Task 1: Document Ollama host binding requirement
  - [ ] 1.1 Add `OLLAMA_HOST=0.0.0.0` to Makefile demo targets or dev docs
  - [ ] 1.2 Update helm/beeper/values.yaml comments for Ollama endpoint

- [ ] Task 2: Investigate and fix LLM JSON parsing
  - [ ] 2.1 Reproduce the `Failed to parse LLM response as JSON` error locally
  - [ ] 2.2 Check if qwen3:8b returns non-JSON output (thinking tokens, markdown wrapping, etc.)
  - [ ] 2.3 Check if LiteLLM's Ollama provider needs specific configuration
  - [ ] 2.4 Fix the parsing logic or add response sanitization for Ollama responses
  - [ ] 2.5 Consider adding `/no_think` or similar parameter if qwen3 outputs thinking tokens

- [ ] Task 3: Add Ollama connectivity validation
  - [ ] 3.1 Add a startup health check in the investigator that tests LLM connectivity
  - [ ] 3.2 Log a clear error message if Ollama is unreachable (not just a 600s timeout)

- [ ] Task 4: Verify
  - [ ] 4.1 Run investigator tests: `cd investigator && python -m pytest tests/ -x -q`
  - [ ] 4.2 Test with Ollama locally if possible

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

qwen3 models may output `<think>...</think>` blocks before the actual response. LiteLLM may not strip these, causing JSON parse failures. May need to pass `extra_body={"enable_thinking": false}` or strip thinking tokens from responses.

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
