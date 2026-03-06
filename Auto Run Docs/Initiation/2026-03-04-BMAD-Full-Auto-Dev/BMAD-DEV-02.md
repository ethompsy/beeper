# Phase 02: Epic 3 Completion — Investigation Engine

This phase completes the Investigation Engine epic by implementing the remaining three stories: Investigation Documentation (3-8), Tiered LLM Model Selection (3-9), and LLM Response Caching (3-10). After this phase, the investigator agent will persist its findings to the Knowledge Base, intelligently select LLM models based on task complexity, and cache responses to reduce costs. The epic retrospective captures learnings from the full Investigation Engine development.

## Tasks

- [ ] Create story 3-8 spec (Investigation Documentation) using the `/bmad-bmm-create-story` skill. This story covers FR9: documenting investigation process and findings to the Knowledge Base. The story should:
  - Be created from `_bmad-output/planning-artifacts/epics.md` Epic 3, Story 3-8
  - Output to `_bmad-output/implementation-artifacts/` following the established story file format
  - Include Dev Notes referencing existing code: `agent.py` `_finalize()` and `_persist_result()`, `kb/client.py`, `kb/schemas.py`
  - Set status to `ready-for-dev` and update sprint-status.yaml
  - Make all decisions autonomously

- [ ] Implement story 3-8 (Investigation Documentation) using the `/bmad-bmm-dev-story` skill:
  - Read the story file created in the previous task
  - Before writing new code, examine `agent.py` `_persist_result()` — it already stores basic investigation results to Qdrant with placeholder embeddings. This story should enhance that with proper investigation documentation
  - Search `kb/client.py` and `kb/schemas.py` for existing KB write patterns and embedding generation
  - Follow all Dev Notes, acceptance criteria, and anti-patterns from the story file
  - Make all decisions autonomously

- [ ] Review and finalize story 3-8:
  - Use the `/bmad-bmm-code-review` skill to review story 3-8 — auto-fix all issues found
  - After review fixes, run `cd investigator && poetry run pytest && poetry run ruff check . && poetry run mypy .`
  - Fix any remaining test failures or lint/type issues
  - Update sprint-status.yaml: `3-8-investigation-documentation: done`
  - Update story file status to `done`
  - Commit all changes as `3-8 done`

- [ ] Create story 3-9 spec (Tiered LLM Model Selection) using the `/bmad-bmm-create-story` skill. This story covers FR43/FR44: lightweight models for screening tasks and powerful models for deep RCA. The story should:
  - Be created from `_bmad-output/planning-artifacts/epics.md` Epic 3, Story 3-9
  - Include Dev Notes referencing existing code: `llm/client.py` (LiteLLM wrapper, `complete_sync()`, screening model support)
  - Reference how existing steps call the LLM: `impact_assessment.py` uses screening model, `rca_hypothesis.py` and `resolution_recommendations.py` use default model
  - Make all decisions autonomously

- [ ] Implement story 3-9 (Tiered LLM Model Selection) using the `/bmad-bmm-dev-story` skill:
  - Read the story file created in the previous task
  - Before writing new code, examine `llm/client.py` — understand the existing `complete_sync()` API, screening model support, and LiteLLM configuration
  - Search all step files (`impact_assessment.py`, `kb_query.py`, `signal_correlation.py`, `rca_hypothesis.py`, `resolution_recommendations.py`) to understand how each step calls the LLM client
  - Implement tiered model selection without breaking existing step implementations
  - Make all decisions autonomously

- [ ] Review and finalize story 3-9:
  - Use the `/bmad-bmm-code-review` skill to review story 3-9 — auto-fix all issues found
  - After review fixes, run `cd investigator && poetry run pytest && poetry run ruff check . && poetry run mypy .`
  - Fix any remaining test failures or lint/type issues
  - Update sprint-status.yaml: `3-9-tiered-llm-model-selection: done`
  - Update story file status to `done`
  - Commit all changes as `3-9 done`

- [ ] Create story 3-10 spec (LLM Response Caching) using the `/bmad-bmm-create-story` skill. This story covers FR45: cache and memoize LLM results to reduce costs. The story should:
  - Be created from `_bmad-output/planning-artifacts/epics.md` Epic 3, Story 3-10
  - Include Dev Notes referencing existing code: `llm/client.py` (LiteLLM wrapper where caching should be integrated)
  - Consider: cache key generation, TTL, invalidation strategy, cache hit/miss metrics
  - Make all decisions autonomously

- [ ] Implement story 3-10 (LLM Response Caching) using the `/bmad-bmm-dev-story` skill:
  - Read the story file created in the previous task
  - Before writing new code, examine `llm/client.py` — caching should wrap the existing `complete_sync()` method transparently
  - Consider where cache state lives (in-memory dict, Redis, or file-based depending on story requirements)
  - Ensure cache does not break existing tests — all existing LLM mocks should still work
  - Make all decisions autonomously

- [ ] Review and finalize story 3-10:
  - Use the `/bmad-bmm-code-review` skill to review story 3-10 — auto-fix all issues found
  - After review fixes, run `cd investigator && poetry run pytest && poetry run ruff check . && poetry run mypy .`
  - Fix any remaining test failures or lint/type issues
  - Update sprint-status.yaml: `3-10-llm-response-caching: done`
  - Update story file status to `done`
  - Commit all changes as `3-10 done`

- [ ] Run Epic 3 retrospective and mark epic complete:
  - Use the `/bmad-bmm-retrospective` skill to conduct the Epic 3 retrospective
  - Reference `_bmad-output/implementation-artifacts/epic-1-retro-2026-02-12.md` for format: epic summary table, stories delivered table, what went well, what could be improved, action items
  - Create retrospective file at `_bmad-output/implementation-artifacts/epic-3-retro-YYYY-MM-DD.md` (use today's date)
  - Include: all 10 stories delivered (3-1 through 3-10), test counts, code review issues fixed, duration, key patterns and lessons
  - Update sprint-status.yaml: `epic-3: done`, `epic-3-retrospective: done`
  - Commit as `epic-3 retrospective done`
