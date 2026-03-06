# Phase 03: Epic 4 — Investigation Experience

This phase builds the user-facing Investigation Experience, giving SREs the ability to view, interact with, and resolve investigations through the web UI. Stories deliver: investigation list with real-time SSE updates (4-1), live investigation reasoning pane (4-2), recommendations and confidence display (4-3), KB entry navigation (4-4), resolution confirmation workflow (4-5), and investigation closure with MTTR tracking (4-6). By the end, the full investigation lifecycle is visible and controllable through the Flask/HTMX interface.

## Tasks

- [ ] Create story 4-1 spec (Investigation List View) using the `/bmad-bmm-create-story` skill. This story covers FR31: SREs can view a list of active investigations. The story should:
  - Be created from `_bmad-output/planning-artifacts/epics.md` Epic 4, Story 4-1
  - Include Dev Notes referencing existing UI code: the `ui/` module structure, Flask routes, HTMX patterns, SSE implementation
  - Reference existing operator API endpoints for fetching investigation status from K8s CRDs
  - Update sprint-status.yaml: `epic-4: in-progress`, `4-1-investigation-list-view: ready-for-dev`
  - Make all decisions autonomously

- [ ] Implement story 4-1 (Investigation List View) using the `/bmad-bmm-dev-story` skill:
  - Read the story file created in the previous task
  - Before writing new code, explore the `ui/` directory to understand existing Flask app structure, templates, static assets, and HTMX patterns
  - Search for existing SSE implementations in the codebase (operator or UI) to reuse patterns
  - Implement: Flask route, Jinja2 template with HTMX, SSE endpoint for real-time updates, filtering controls
  - Make all decisions autonomously

- [ ] Review and finalize story 4-1:
  - Use the `/bmad-bmm-code-review` skill to review story 4-1 — auto-fix all issues found
  - After review fixes, run all relevant tests (Python tests for UI routes, ruff, mypy)
  - Fix any remaining test failures or lint/type issues
  - Update sprint-status.yaml: `4-1-investigation-list-view: done`
  - Update story file status to `done`
  - Commit all changes as `4-1 done`

- [ ] Create story 4-2 spec (Real-Time Investigation Pane) using the `/bmad-bmm-create-story` skill. This story covers FR32/FR10: SREs can observe Beeper's reasoning process in real-time. The story should:
  - Be created from `_bmad-output/planning-artifacts/epics.md` Epic 4, Story 4-2
  - Include Dev Notes referencing: investigation step pipeline (agent.py `_run_steps()`), status updater pattern, SSE streaming for step-by-step updates
  - Reference the investigation list view (4-1) for navigation patterns
  - Make all decisions autonomously

- [ ] Implement story 4-2 (Real-Time Investigation Pane) using the `/bmad-bmm-dev-story` skill:
  - Read the story file created in the previous task
  - Before writing new code, review: the investigation list view (story 4-1 code) for navigation and SSE patterns, `agent.py` step pipeline for understanding what data to stream, `k8s/status.py` for status update flow
  - Implement: SSE endpoint streaming step progress, expandable evidence sections, real-time findings display
  - Make all decisions autonomously

- [ ] Review and finalize story 4-2:
  - Use the `/bmad-bmm-code-review` skill to review story 4-2 — auto-fix all issues found
  - After review fixes, run all relevant tests, ruff, mypy
  - Fix any remaining test failures or lint/type issues
  - Update sprint-status.yaml: `4-2-real-time-investigation-pane: done`
  - Update story file status to `done`
  - Commit all changes as `4-2 done`

- [ ] Create story 4-3 spec (Recommendations & Confidence Display) using the `/bmad-bmm-create-story` skill. This story covers FR33: SREs can view recommended resolutions with confidence levels. The story should:
  - Be created from `_bmad-output/planning-artifacts/epics.md` Epic 4, Story 4-3
  - Include Dev Notes referencing: `resolution_recommendations.py` StepResult data schema (recommendations list, ranking_rationale, diagnostic_actions), confidence level bands (high >80%, medium 50-80%, low <50%)
  - Make all decisions autonomously

- [ ] Implement story 4-3 (Recommendations & Confidence Display) using the `/bmad-bmm-dev-story` skill:
  - Read the story file created in the previous task
  - Before writing new code, review: resolution recommendations step output schema, existing investigation pane (4-2) for display patterns, UI templates for consistent styling
  - Implement: ranked recommendation cards with visual confidence indicators, risk badges, supporting evidence, warning display for low confidence
  - Make all decisions autonomously

- [ ] Review and finalize story 4-3:
  - Use the `/bmad-bmm-code-review` skill to review story 4-3 — auto-fix all issues found
  - After review fixes, run all relevant tests, ruff, mypy
  - Fix any remaining test failures or lint/type issues
  - Update sprint-status.yaml: `4-3-recommendations-confidence-display: done`
  - Update story file status to `done`
  - Commit all changes as `4-3 done`

- [ ] Create and implement story 4-4 (KB Entry Navigation). First, use the `/bmad-bmm-create-story` skill to create the spec from Epic 4, Story 4-4 (FR34: navigate from investigation to related KB entries). Then use the `/bmad-bmm-dev-story` skill to implement it:
  - Before writing new code, review: KB wiki interface (Epic 2 code in `ui/`), investigation pane (4-2) for linking patterns, `kb/client.py` for fetching related entries
  - Implement: related incidents section, side panel/modal for KB entry viewing, similarity scores, navigation breadcrumbs
  - Make all decisions autonomously

- [ ] Review and finalize story 4-4:
  - Use the `/bmad-bmm-code-review` skill to review story 4-4 — auto-fix all issues found
  - After review fixes, run all relevant tests, ruff, mypy
  - Fix any remaining test failures or lint/type issues
  - Update sprint-status.yaml: `4-4-kb-entry-navigation: done`
  - Update story file status to `done`
  - Commit all changes as `4-4 done`

- [ ] Create and implement story 4-5 (Resolution Confirmation). First, use the `/bmad-bmm-create-story` skill to create the spec from Epic 4, Story 4-5 (FR11: confirm or reject resolution recommendations). Then use the `/bmad-bmm-dev-story` skill to implement it:
  - Before writing new code, review: recommendations display (4-3), investigation pane (4-2), existing HTMX form patterns in `ui/`
  - Implement: confirm/reject buttons, comment/reason capture, investigation status update, feedback recording for future learning
  - Make all decisions autonomously

- [ ] Review and finalize story 4-5:
  - Use the `/bmad-bmm-code-review` skill to review story 4-5 — auto-fix all issues found
  - After review fixes, run all relevant tests, ruff, mypy
  - Fix any remaining test failures or lint/type issues
  - Update sprint-status.yaml: `4-5-resolution-confirmation: done`
  - Update story file status to `done`
  - Commit all changes as `4-5 done`

- [ ] Create and implement story 4-6 (Investigation Resolution). First, use the `/bmad-bmm-create-story` skill to create the spec from Epic 4, Story 4-6 (FR12: mark investigation as resolved with outcome confirmation). Then use the `/bmad-bmm-dev-story` skill to implement it:
  - Before writing new code, review: resolution confirmation (4-5), investigation list (4-1), KB documentation (3-8) for writing resolution to KB, existing MTTR patterns
  - Implement: resolution form (Resolved/Not an issue/Escalated/Unresolved), accuracy rating, KB update with resolution, MTTR calculation
  - Make all decisions autonomously

- [ ] Review and finalize story 4-6:
  - Use the `/bmad-bmm-code-review` skill to review story 4-6 — auto-fix all issues found
  - After review fixes, run all relevant tests, ruff, mypy
  - Fix any remaining test failures or lint/type issues
  - Update sprint-status.yaml: `4-6-investigation-resolution: done`
  - Update story file status to `done`
  - Commit all changes as `4-6 done`

- [ ] Run Epic 4 retrospective and mark epic complete:
  - Use the `/bmad-bmm-retrospective` skill to conduct the Epic 4 retrospective
  - Reference previous retrospectives for format: `_bmad-output/implementation-artifacts/epic-1-retro-2026-02-12.md` and the Epic 3 retro
  - Create retrospective file at `_bmad-output/implementation-artifacts/epic-4-retro-YYYY-MM-DD.md`
  - Include: all 6 stories delivered (4-1 through 4-6), test counts, code review issues fixed, UI/UX patterns established, lessons learned
  - Update sprint-status.yaml: `epic-4: done`, `epic-4-retrospective: done`
  - Commit as `epic-4 retrospective done`
