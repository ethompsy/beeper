# Phase 06: Epic 2 Retrospective + Final Release Validation

This phase closes out the project by running the deferred Epic 2 (Knowledge Base) retrospective, performing a comprehensive sprint status summary, and validating the full release across all epics. By the end, all 6 epics are complete with retrospectives, the sprint status reflects the full journey, and a final validation confirms the entire Beeper platform is functioning correctly.

## Tasks

- [x] Run Epic 2 (Knowledge Base) retrospective:
  - Use the `/bmad-bmm-retrospective` skill to conduct the Epic 2 retrospective
  - This was deferred (marked `optional` in sprint-status.yaml) — now is the right time since all epics are complete and we have full project context
  - Reference previous retrospectives for format: `epic-1-retro-2026-02-12.md`, Epic 3 retro, Epic 4 retro
  - Create retrospective file at `_bmad-output/implementation-artifacts/epic-2-retro-YYYY-MM-DD.md`
  - Include: all 7 stories delivered (2-1 through 2-7), test counts, patterns established (KB wiki, semantic search, structured search, runbook import, editing, versioning, diff view)
  - Update sprint-status.yaml: `epic-2-retrospective: done`
  - Commit as `epic-2 retrospective done`
  - ✅ Completed 2026-03-08: Retrospective saved to `epic-2-retro-2026-03-08.md`. Reviewed all 7 story files, extracted 46 code review issues (38 fixed), documented patterns established, updated sprint-status.yaml.

- [ ] Generate final sprint status summary and cross-epic analysis:
  - Read sprint-status.yaml and all retrospective files to compile a comprehensive summary
  - Create `_bmad-output/implementation-artifacts/final-sprint-summary-YYYY-MM-DD.md` with YAML front matter:
    ```yaml
    ---
    type: report
    title: Beeper Final Sprint Summary
    created: YYYY-MM-DD
    tags:
      - sprint-summary
      - release
      - beeper
    related:
      - '[[epic-1-retro]]'
      - '[[epic-2-retro]]'
      - '[[epic-3-retro]]'
      - '[[epic-4-retro]]'
      - '[[epic-5-retro]]'
      - '[[epic-6-retro]]'
    ---
    ```
  - Include sections:
    - Project overview (39 stories across 6 epics)
    - Epic-by-epic summary with key metrics (stories, tests, review issues)
    - Total test count across all modules (Rust operator + Python investigator + UI)
    - Functional requirements coverage (FR1-FR47 mapped to stories)
    - Non-functional requirements validation status
    - Architecture compliance check
    - Key patterns and conventions established
    - Risks and known limitations
  - Commit as `final sprint summary`

- [ ] Run full release validation across all components:
  - **Investigator module:** `cd investigator && poetry run pytest -v && poetry run ruff check . && poetry run mypy .`
  - **Operator module:** `cd operator && cargo test` (if Rust tests exist)
  - **UI module:** Run any existing UI tests
  - **Integration check:** Verify `docker-compose.yaml` references are consistent with implemented services
  - **Sprint status verification:** Confirm all stories show `done` in sprint-status.yaml, all epics show `done`, all retrospectives show `done`
  - **OpenAPI spec check:** Verify `openapi/` specs match implemented endpoints
  - If any validation fails, fix the issue and commit the fix
  - Final commit: `release: all epics complete — full platform validated`
