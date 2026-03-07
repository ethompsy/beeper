# Phase 03: Epic 4 — Investigation Experience

This phase builds the user-facing Investigation Experience, giving SREs the ability to view, interact with, and resolve investigations through the web UI. Stories deliver: investigation list with real-time SSE updates (4-1), live investigation reasoning pane (4-2), recommendations and confidence display (4-3), KB entry navigation (4-4), resolution confirmation workflow (4-5), and investigation closure with MTTR tracking (4-6). By the end, the full investigation lifecycle is visible and controllable through the Flask/HTMX interface.

## Tasks

- [x] Create story 4-1 spec (Investigation List View) using the `/bmad-bmm-create-story` skill. This story covers FR31: SREs can view a list of active investigations. The story should:
  - Be created from `_bmad-output/planning-artifacts/epics.md` Epic 4, Story 4-1
  - Include Dev Notes referencing existing UI code: the `ui/` module structure, Flask routes, HTMX patterns, SSE implementation
  - Reference existing operator API endpoints for fetching investigation status from K8s CRDs
  - Update sprint-status.yaml: `epic-4: in-progress`, `4-1-investigation-list-view: ready-for-dev`
  - Make all decisions autonomously
  <!-- Completed 2026-03-06: Story file created at _bmad-output/implementation-artifacts/4-1-investigation-list-view.md with 9 tasks, comprehensive dev notes covering SSE polling-backed design, operator API endpoint, service layer, HTMX templates, and filter panel. Sprint status updated. -->

- [x] Implement story 4-1 (Investigation List View) using the `/bmad-bmm-dev-story` skill:
  - Read the story file created in the previous task
  - Before writing new code, explore the `ui/` directory to understand existing Flask app structure, templates, static assets, and HTMX patterns
  - Search for existing SSE implementations in the codebase (operator or UI) to reuse patterns
  - Implement: Flask route, Jinja2 template with HTMX, SSE endpoint for real-time updates, filtering controls
  - Make all decisions autonomously
  <!-- Completed 2026-03-06: Full implementation of story 4-1 across 8 tasks. Operator: GET /api/v1/investigations endpoint with filtering/sorting (Rust). UI: InvestigationService (httpx), investigation routes with HTMX, filter panel, SSE polling-backed streaming, severity/status CSS. Tests: 20 new tests (9 service + 11 route), 135 total pass. Ruff + mypy --strict clean. Sprint status → review. -->

- [x] Review and finalize story 4-1:
  - Use the `/bmad-bmm-code-review` skill to review story 4-1 — auto-fix all issues found
  - After review fixes, run all relevant tests (Python tests for UI routes, ruff, mypy)
  - Fix any remaining test failures or lint/type issues
  - Update sprint-status.yaml: `4-1-investigation-list-view: done`
  - Update story file status to `done`
  - Commit all changes as `4-1 done`
  <!-- Completed 2026-03-06: Adversarial code review found 7 issues (2 HIGH, 3 MEDIUM, 2 LOW). Fixed: (1) SSE sends HTML partials instead of JSON for HTMX swap compatibility, (2) date range filter added to route/template (AC4 complete), (3) service filter sanitized with regex validation, (4) error messages no longer expose internal operator URLs, (5) stream_with_context for SSE generator robustness. Tests: 42 investigation tests (up from 20), 296 total pass, zero regressions. Ruff + mypy clean on all investigation files. Sprint status + story → done. -->

- [x] Create story 4-2 spec (Real-Time Investigation Pane) using the `/bmad-bmm-create-story` skill. This story covers FR32/FR10: SREs can observe Beeper's reasoning process in real-time. The story should:
  - Be created from `_bmad-output/planning-artifacts/epics.md` Epic 4, Story 4-2
  - Include Dev Notes referencing: investigation step pipeline (agent.py `_run_steps()`), status updater pattern, SSE streaming for step-by-step updates
  - Reference the investigation list view (4-1) for navigation patterns
  - Make all decisions autonomously
  <!-- Completed 2026-03-06: Story file created at _bmad-output/implementation-artifacts/4-2-real-time-investigation-pane.md with 9 tasks, comprehensive dev notes covering SSE polling-backed detail streaming, operator detail API endpoint, step timeline display logic, Qdrant findings retrieval, expandable evidence panels, and list-to-detail HTMX navigation. Sprint status updated. -->

- [x] Implement story 4-2 (Real-Time Investigation Pane) using the `/bmad-bmm-dev-story` skill:
  - Read the story file created in the previous task
  - Before writing new code, review: the investigation list view (story 4-1 code) for navigation and SSE patterns, `agent.py` step pipeline for understanding what data to stream, `k8s/status.py` for status update flow
  - Implement: SSE endpoint streaming step progress, expandable evidence sections, real-time findings display
  - Make all decisions autonomously
  <!-- Completed 2026-03-06: Full implementation of story 4-2 across 9 tasks. Operator: GET /api/v1/investigations/:id detail endpoint with InvestigationDetailResponse, 404 handling, 4 Rust tests. UI: InvestigationDetail dataclass, get_investigation() + get_investigation_findings() (Qdrant), detail route with HTMX partial support, SSE streaming (step-update/findings-update/investigation-complete events), 6 new templates (detail, step progress timeline, findings, evidence panels, not-found), ~300 lines CSS (step timeline, confidence indicators, animations). List rows clickable with hx-get/hx-push-url. Tests: 68 investigation tests (19 service + 49 route), 322 total pass, zero regressions. Ruff + mypy clean. Sprint status → review. -->

- [x] Review and finalize story 4-2:
  - Use the `/bmad-bmm-code-review` skill to review story 4-2 — auto-fix all issues found
  - After review fixes, run all relevant tests, ruff, mypy
  - Fix any remaining test failures or lint/type issues
  - Update sprint-status.yaml: `4-2-real-time-investigation-pane: done`
  - Update story file status to `done`
  - Commit all changes as `4-2 done`
  <!-- Completed 2026-03-06: Adversarial code review found 7 issues (2 HIGH, 4 MEDIUM, 1 LOW). Fixed: (1) HTMX list-to-detail navigation broken — replaced hx-target="body" with standard anchor links to ensure SSE connects on page load, (2) SSE generator resource leak — added svc.close() on 404 path, (3) Evidence panels SSE update — added evidence-update SSE event target, (4) CSS injection risk — added |int filter to confidence_percentage, (5) Qdrant client leak — close() now closes both httpx and Qdrant clients, (6) Added 7 new tests: SSE event generation (step-update on message change, complete on phase, not-found, findings-update), Qdrant close, link navigation. Tests: 76 investigation tests (up from 68), 330 total pass, zero regressions. Ruff + mypy clean on investigation files. Sprint status + story → done. -->

- [x] Create story 4-3 spec (Recommendations & Confidence Display) using the `/bmad-bmm-create-story` skill. This story covers FR33: SREs can view recommended resolutions with confidence levels. The story should:
  - Be created from `_bmad-output/planning-artifacts/epics.md` Epic 4, Story 4-3
  - Include Dev Notes referencing: `resolution_recommendations.py` StepResult data schema (recommendations list, ranking_rationale, diagnostic_actions), confidence level bands (high >80%, medium 50-80%, low <50%)
  - Make all decisions autonomously
  <!-- Completed 2026-03-06: Story file created at _bmad-output/implementation-artifacts/4-3-recommendations-confidence-display.md with 6 tasks, comprehensive dev notes covering ResolutionRecommendationStep data schema (recommendations list with action/confidence/risk_assessment/expected_outcome/based_on_prior_incident, ranking_rationale, diagnostic_actions), confidence bands (high >80% green, medium 50-80% yellow, low <50% red), template-only enhancement approach (no new endpoints/services/SSE), existing pattern reuse from 4-2. Sprint status updated. -->

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
