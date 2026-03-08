# Phase 05: Epic 6 — Operations & Insights

This phase implements the Operations & Insights epic, giving administrators visibility into Beeper's operational impact and cost management. Stories deliver: MTTR trends dashboard with drill-down (6-1), LLM spending caps and rate limiting (6-2), and per-service cost visibility with alerts and tuning controls (6-3). By the end, admins can measure Beeper's reliability impact, control LLM costs, and identify noisy services driving excessive investigation spend.

## Tasks

- [x] Create story 6-1 spec (MTTR Trends Dashboard) using the `/bmad-bmm-create-story` skill. This story covers FR35: SRE Leads can view MTTR trends over time. The story should:
  - Be created from `_bmad-output/planning-artifacts/epics.md` Epic 6, Story 6-1
  - Include Dev Notes referencing: investigation resolution (story 4-6) where MTTR is calculated, existing UI patterns from Epic 4, charting approach (server-rendered vs JS library)
  - Consider: time period selection, service breakdown, severity breakdown, drill-down to investigations, data export
  - Update sprint-status.yaml: `epic-6: in-progress`, `6-1-mttr-trends-dashboard: ready-for-dev`
  - Make all decisions autonomously
  - **Done:** Story created at `_bmad-output/implementation-artifacts/6-1-mttr-trends-dashboard.md`. 7 tasks, 5 ACs. Charting: server-rendered inline SVG trend lines + CSS horizontal bars for breakdowns. New MetricsService + metrics Blueprint. HTMX filtering, drill-down, JSON/CSV export. Sprint status updated.

- [x] Implement story 6-1 (MTTR Trends Dashboard) using the `/bmad-bmm-dev-story` skill:
  - Read the story file created in the previous task
  - Before writing new code, review: investigation resolution (4-6) for MTTR data sources, existing UI templates and styling from Epic 4, Flask route patterns
  - Search for any existing metrics/dashboard patterns in the codebase
  - Implement: MTTR aggregation logic, trend visualization, filtering by service/severity/time period, drill-down navigation, export functionality
  - Make all decisions autonomously
  - **Done:** All 7 tasks implemented. MetricsService (MTTR aggregation from Qdrant), metrics Blueprint (4 routes), server-rendered SVG trend chart, HTMX filtering, drill-down, JSON/CSV export. 21 tests pass, ruff clean, mypy clean, 588/588 full suite pass. Story status: review.

- [x] Review and finalize story 6-1:
  - Use the `/bmad-bmm-code-review` skill to review story 6-1 — auto-fix all issues found
  - After review fixes, run all relevant tests, ruff, mypy
  - Fix any remaining test failures or lint/type issues
  - Update sprint-status.yaml: `6-1-mttr-trends-dashboard: done`
  - Update story file status to `done`
  - Commit all changes as `6-1 done`
  - **Done:** Adversarial code review found 7 issues (1 critical, 2 high, 2 medium, 2 low). All fixed: N+1 query problem (added scroll caching), code duplication (extracted shared helpers), missing drilldown date validation, CSS SVG animation fix, 7 new tests for input validation/caching. 28 tests pass, 595/595 full suite, ruff clean, mypy clean.

- [x] Create and implement story 6-2 (LLM Spending Caps). First, use the `/bmad-bmm-create-story` skill to create the spec from Epic 6, Story 6-2 (FR46: set spending caps and rate limits for LLM usage). Then use the `/bmad-bmm-dev-story` skill to implement it:
  - Before writing new code, review: LLM client (`llm/client.py`) for tracking call costs, tiered model selection (3-9) for model cost data, LLM caching (3-10) for cost savings data
  - Implement: spending cap configuration (daily/monthly), rate limiting, threshold warnings (80%), investigation prioritization when cap reached, admin dashboard with spend vs cap visualization
  - Make all decisions autonomously
  - **Done:** Story created at `_bmad-output/implementation-artifacts/6-2-llm-spending-caps.md`. 7 tasks, 5 ACs. CostTracker in LlmClient (token-level cost from LiteLLM usage), SpendingCapEnforcer in agent (daily/monthly caps, sliding-window rate limiting, priority severity bypass for high/critical). SpendingService + spending Blueprint (progress bars, SVG trend chart, cap status badges, HTMX auto-refresh). Env-driven config (BEEPER_LLM_DAILY_CAP_CENTS, etc.) — disabled when unset. 37 new tests (28 investigator + 9 UI), ruff clean, mypy clean, 1007/1007 full suite pass. Story status: review.

- [x] Review and finalize story 6-2:
  - Use the `/bmad-bmm-code-review` skill to review story 6-2 — auto-fix all issues found
  - After review fixes, run all relevant tests, ruff, mypy
  - Fix any remaining test failures or lint/type issues
  - Update sprint-status.yaml: `6-2-llm-spending-caps: done`
  - Update story file status to `done`
  - Commit all changes as `6-2 done`
  - **Done:** Adversarial code review found 7 issues (1 critical, 1 high, 3 medium, 2 low). All fixed: CRITICAL spending caps never enforced (update_spend never called — added cost feedback in agent.run()), HIGH division-by-zero guard for zero caps, MEDIUM CSS progress bar color selectors replaced with server-side classes, MEDIUM env var validation with try/except, MEDIUM documented 3 undocumented step file changes. 3 new tests added. 31 investigator + 9 UI tests pass, 406+604=1010 full suite, ruff clean, mypy clean.

- [x] Create and implement story 6-3 (Cost Visibility & Alerts). First, use the `/bmad-bmm-create-story` skill to create the spec from Epic 6, Story 6-3 (FR47: surface environments with excessive investigation costs). Then use the `/bmad-bmm-dev-story` skill to implement it:
  - Before writing new code, review: spending caps (6-2) for cost tracking infrastructure, MTTR dashboard (6-1) for visualization patterns, existing admin UI
  - Implement: per-service cost breakdown, "High Cost" flagging, threshold-based alerts, actionable recommendations (tune sensitivity, exclude patterns, set service limits), export (CSV/JSON)
  - Make all decisions autonomously
  - **Done:** Story created at `_bmad-output/implementation-artifacts/6-3-cost-visibility-alerts.md`. 7 tasks, 5 ACs. Extended SpendingService with cost breakdown methods (by service/severity/model, high-cost flagging with configurable 2x threshold, trend calculation). 3 new routes on spending_bp (/costs, /costs/breakdown, /costs/export). Server-rendered SVG trend chart, HTMX filtering, category bars, high-cost alert cards with actionable recommendations. JSON/CSV export. 20 new tests, ruff clean, mypy clean, 1030/1030 full suite pass. Story status: review.

- [x] Review and finalize story 6-3:
  - Use the `/bmad-bmm-code-review` skill to review story 6-3 — auto-fix all issues found
  - After review fixes, run all relevant tests, ruff, mypy
  - Fix any remaining test failures or lint/type issues
  - Update sprint-status.yaml: `6-3-cost-visibility-alerts: done`
  - Update story file status to `done`
  - Commit all changes as `6-3 done`
  - **Done:** Adversarial code review found 7 issues (2 high, 3 medium, 2 low). All fixed: HIGH get_high_cost_services ignoring period filter (added period parameter), HIGH task 1.4 falsely marked complete (corrected description), MEDIUM unused re import and SERVICE_NAME_PATTERN removed, MEDIUM trend chart not filtering by period (added date cutoff), MEDIUM CSV export missing model breakdown (added model section). 2 new tests added (invalid period fallback, high cost respects period). 22 cost insights tests pass, 626+406=1032 full suite, ruff clean, mypy clean.

- [ ] Run Epic 6 retrospective and mark epic complete:
  - Use the `/bmad-bmm-retrospective` skill to conduct the Epic 6 retrospective
  - Reference previous retrospectives for format consistency
  - Create retrospective file at `_bmad-output/implementation-artifacts/epic-6-retro-YYYY-MM-DD.md`
  - Include: all 3 stories delivered (6-1 through 6-3), test counts, code review issues fixed, admin/ops patterns established, cost management lessons
  - Update sprint-status.yaml: `epic-6: done`, `epic-6-retrospective: done`
  - Commit as `epic-6 retrospective done`
