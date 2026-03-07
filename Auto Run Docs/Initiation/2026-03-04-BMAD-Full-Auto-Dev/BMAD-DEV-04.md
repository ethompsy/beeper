# Phase 04: Epic 5 — Living Knowledge

This phase implements the Living Knowledge epic, enabling Beeper to learn and improve from human feedback. Stories deliver: conversational corrections interface (5-1), automated KB revision processing (5-2), learning from diffs between AI documentation and human corrections (5-3), and graduated authoring trust so validated Beeper entries publish directly (5-4). By the end, the Knowledge Base becomes a living system that improves through human-AI collaboration.

## Tasks

- [x] Create story 5-1 spec (Conversational Corrections Interface) using the `/bmad-bmm-create-story` skill. This story covers FR18: SRE Leads can provide conversational corrections to Beeper. The story should:
  - Be created from `_bmad-output/planning-artifacts/epics.md` Epic 5, Story 5-1
  - Include Dev Notes referencing existing UI code: KB wiki interface (Epic 2 stories), HTMX patterns, Flask routes
  - Consider: chat-style UI for corrections, correction history tracking, acknowledgment flow
  - Update sprint-status.yaml: `epic-5: in-progress`, `5-1-conversational-corrections-interface: ready-for-dev`
  - Make all decisions autonomously
  - *Completed: Story file created at `_bmad-output/implementation-artifacts/5-1-conversational-corrections-interface.md` with comprehensive dev notes covering Qdrant corrections collection, CorrectionService with LLM integration, HTMX chat-style UI, conversation flow, and correction history. Sprint status updated.*

- [ ] Implement story 5-1 (Conversational Corrections Interface) using the `/bmad-bmm-dev-story` skill:
  - Read the story file created in the previous task
  - Before writing new code, explore the `ui/` directory for existing KB entry views, editing patterns (from stories 2-5 KB Entry Editing), and HTMX interaction patterns
  - Search for existing LLM integration patterns in the UI (if any) for processing natural language corrections
  - Implement: correction panel UI, chat-style interface, correction submission endpoint, correction history storage
  - Make all decisions autonomously

- [ ] Review and finalize story 5-1:
  - Use the `/bmad-bmm-code-review` skill to review story 5-1 — auto-fix all issues found
  - After review fixes, run all relevant tests, ruff, mypy
  - Fix any remaining test failures or lint/type issues
  - Update sprint-status.yaml: `5-1-conversational-corrections-interface: done`
  - Update story file status to `done`
  - Commit all changes as `5-1 done`

- [ ] Create and implement story 5-2 (Beeper Revision Processing). First, use the `/bmad-bmm-create-story` skill to create the spec from Epic 5, Story 5-2 (FR19: revise KB entries based on conversational corrections). Then use the `/bmad-bmm-dev-story` skill to implement it:
  - Before writing new code, review: corrections interface (5-1), KB entry editing (story 2-5), version history (story 2-6), version diff (story 2-7), LLM client patterns
  - Implement: LLM-powered revision generation from corrections, diff display, approval workflow, version creation with attribution
  - Make all decisions autonomously

- [ ] Review and finalize story 5-2:
  - Use the `/bmad-bmm-code-review` skill to review story 5-2 — auto-fix all issues found
  - After review fixes, run all relevant tests, ruff, mypy
  - Fix any remaining test failures or lint/type issues
  - Update sprint-status.yaml: `5-2-beeper-revision-processing: done`
  - Update story file status to `done`
  - Commit all changes as `5-2 done`

- [ ] Create and implement story 5-3 (Learning from Diffs). First, use the `/bmad-bmm-create-story` skill to create the spec from Epic 5, Story 5-3 (FR20: learn from diff between AI documentation and human corrections). Then use the `/bmad-bmm-dev-story` skill to implement it:
  - Before writing new code, review: revision processing (5-2) for diff data, KB client for storing learning data, LLM client for pattern analysis
  - Implement: diff analysis, correction pattern categorization, service-scoped learning, prompt adjustment mechanism, improvement metrics
  - Make all decisions autonomously

- [ ] Review and finalize story 5-3:
  - Use the `/bmad-bmm-code-review` skill to review story 5-3 — auto-fix all issues found
  - After review fixes, run all relevant tests, ruff, mypy
  - Fix any remaining test failures or lint/type issues
  - Update sprint-status.yaml: `5-3-learning-from-diffs: done`
  - Update story file status to `done`
  - Commit all changes as `5-3 done`

- [ ] Create and implement story 5-4 (Graduated Authoring Trust). First, use the `/bmad-bmm-create-story` skill to create the spec from Epic 5, Story 5-4 (FR23: publish entries directly as trust is established). Then use the `/bmad-bmm-dev-story` skill to implement it:
  - Before writing new code, review: KB entry creation patterns, learning from diffs (5-3) for accuracy metrics, version history (2-6) for versioning, KB client for trust level storage
  - Implement: per-service trust level tracking, accuracy metric calculation, automatic trust graduation, "Auto-published" transparency flag, trust settings admin view
  - Make all decisions autonomously

- [ ] Review and finalize story 5-4:
  - Use the `/bmad-bmm-code-review` skill to review story 5-4 — auto-fix all issues found
  - After review fixes, run all relevant tests, ruff, mypy
  - Fix any remaining test failures or lint/type issues
  - Update sprint-status.yaml: `5-4-graduated-authoring-trust: done`
  - Update story file status to `done`
  - Commit all changes as `5-4 done`

- [ ] Run Epic 5 retrospective and mark epic complete:
  - Use the `/bmad-bmm-retrospective` skill to conduct the Epic 5 retrospective
  - Reference previous retrospectives for format consistency
  - Create retrospective file at `_bmad-output/implementation-artifacts/epic-5-retro-YYYY-MM-DD.md`
  - Include: all 4 stories delivered (5-1 through 5-4), test counts, code review issues fixed, LLM integration patterns, human-AI collaboration lessons
  - Update sprint-status.yaml: `epic-5: done`, `epic-5-retrospective: done`
  - Commit as `epic-5 retrospective done`
