# Implementation Plan: Beeper — Pipeline Fix & UI Overhaul

## Overview

Brownfield delivery across two workstreams: (1) restore the sequential pipeline from OTEL ingestion → anomaly detection → investigation → LLM root cause; (2) overhaul the UI from fixed-width top-nav to a responsive sidebar-navigated interface. Definition of done: a `payment-failure` fault injection produces an evidence-backed investigation 3/3 consecutive runs in a clean, responsive UI. Traces to [docs/reqs/main.md](docs/reqs/main.md); specs in [docs/specs/](docs/specs/).

> **Provenance:** Transcribed from BMAD artifacts (`_bmad-output/planning-artifacts/epics.md` + `_bmad-output/implementation-artifacts/sprint-status.yaml`, generated 2026-04-10) to preserve completion state. Status values reflect that sprint snapshot, verified against git history through Story 3.2. Full per-story detail and Given/When/Then criteria for completed work live in `_bmad-output/implementation-artifacts/<story-slug>.md`.

**Status legend:** `done` · `in progress` · `pending` · `blocked`. Synthex's `next-priority` executes the lowest-numbered actionable `pending` tasks within the current milestone and never crosses a phase boundary in one session.

**Current resume point:** Phase 4, Milestone 4.1 — **Tasks 4.1 (PR #4, `0e46e4e`) and 4.2 (PR #5, `eafe9ae`) done & merged to `main`**. **Task 4.3 (SSE streaming) in progress** on branch `feature/4.3-sse-streaming` (build-for-review). **Task 4.4 (Related KB panel) deferred** until 4.3 merges — both edit `investigations/detail.html`, so they are sequenced (not run concurrently) to avoid conflicts — and until Q2/AD-5 is verified against a live backend. Phases 1–2 complete; **Phase 3 complete** (Tasks 3.1–3.4 done; Milestone 3.0 complete except the blocked `3-0c`, carried forward to Task 6.3 per Q1).

## Decisions

| # | Decision | Context | Rationale |
|---|----------|---------|-----------|
| AD-1 | OTEL protobuf: verify-first, adapt-if-needed | Collector exports snappy+protobuf to `:9090` | Beeper adapts to Collector output; Collector config must NOT be modified |
| AD-2 | Detection stats API: additive only | Existing `/api/v1/ingestion/stats` on `:8080` | New fields added; existing fields unchanged in name/type/structure |
| AD-3 | Layout shell via `base.html` inheritance | 29 page templates | Modify `base.html` once; all routes adopt the shell simultaneously (atomic migration) |
| AD-4 | SSE reconnection + REST backfill | No `Last-Event-ID` support | Client reconnects via `EventSource` + `GET /api/v1/investigations/{id}`; steps ordered by `order` field |
| AD-5 | Related KB panel reads `investigations` collection | KBQueryStep results by investigation ID | Assumption to verify during pipeline fix (see Q2) |
| AD-6 | Sidebar state: hybrid server default + client override | Responsive + manual toggle | CSS handles responsive behavior; JS only for user toggle (sessionStorage) |
| AD-7 | Tailwind via standalone binary | New components Tailwind-only | `make tailwind-watch`/`tailwind-build`; UI Dockerfile build stage; coexists with existing CSS |
| AD-8 | Integration testing = manual verification | Slow Rust inner loop; brownfield | Makefile + `kubectl` + `curl`; pre-implementation test baseline required |
| D1 | Dual HTTP server architecture | `:8080` Axum mgmt API + `:9090` ingestion | Separate servers, same process |
| D2 | Qdrant upgraded v1.12.0 → v1.15.0 | Helm chart vs local dev mismatch | Align versions to avoid KB read/write discrepancies |
| D3 | Cross-workstream gate | FR9 detection stats API (Rust) blocks UI diagnostics | Task 1.4 must ship before Task 5.2 can render real data |
| D4 | Tailwind/CSS coexistence | Never mix on same element | New components Tailwind-only; existing CSS preserved until per-template migration; semantic tokens (`bg-surface-base`) required, never arbitrary `bg-[#0f0f1a]` |

## Open Questions

| # | Question | Impact | Status |
|---|----------|--------|--------|
| Q1 | `3-0c-full-demo-walkthrough` failed in the 2026-04-10 snapshot | Full E2E demo not yet proven; superseded/retested by Epic 6 (Task 6.3) | Open — blocked task carried forward |
| Q2 | AD-5: does the `investigations` Qdrant collection reliably hold KBQueryStep results keyed by investigation ID? | Tasks 4.4 and 5.1 depend on this read pattern | Open — verify during Epic 2 KB work / before Task 4.4 |
| Q3 | Are all `[T]` UI criteria automatable, given AD-8's manual-verification stance? | Some UI criteria are `[H]` (visual/UX judgment) rather than `[T]` | Resolved per-criterion below; revisit if a test harness for templates lands |

---

## Phase 1: Restore Data Pipeline — Telemetry Ingestion & Anomaly Detection

Telemetry flows OTEL Collector → Beeper, EWMA detectors calibrate and fire, Investigation CRDs are created automatically, and detection stats are exposed via API. (Epic 1 — FR1–9; AD-1, AD-2, AD-8; NFR1, NFR5, NFR6, NFR11, NFR13)

### Milestone 1.1: Ingestion & Detection

| # | Task | Complexity | Dependencies | Status |
|---|------|-----------|--------------|--------|
| 1.1 | Establish test baseline (document pass/fail across operator/investigator/UI) | S | None | done |
| 1.2 | Fix OTEL Collector → operator ingestion (protobuf metrics + JSON logs) | L | 1.1 | done |
| 1.3 | Fix anomaly detection & investigation triggering (EWMA + pattern + dedup) | L | 1.2 | done |
| 1.4 | Extend ingestion stats API with detection metrics | M | 1.3 | done |

**Task 1.1 — done.** `[T]` Full suite results documented per component with failures categorized by boundary. Detail: `_bmad-output/implementation-artifacts/1-1-establish-test-baseline.md`.

**Task 1.2 — done.** `[T]` Operator decodes snappy+protobuf remote-write at `:9090/api/v1/write` and buffers samples (proto defs adapted to Collector output per AD-1); `[T]` Loki JSON push at `:9090/loki/api/v1/push` parsed and buffered; `[T]` `GET /api/v1/ingestion/stats` shows `metrics_received > 0` and `logs_received > 0` with per-source health (bytes, parse errors, last-received).

**Task 1.3 — done.** `[T]` EWMA detectors warm up (≥10 samples/stream) and evaluate thresholds; `[T]` `payment-failure` fault → EWMA fires (FR5) + Investigation CRD created (FR7); `[T]` log pattern detector flags anomalies (FR6); `[T]` duplicate investigations suppressed within cooldown and counted (FR8).

**Task 1.4 — done.** `[T]` Stats response adds `anomalies_detected`, `anomalies_suppressed`, `active_metric_detectors`, `ewma_warmup_samples`, `ewma_warmup_minimum` (AD-2); `[T]` existing fields unchanged; `[T]` serialization tests confirm snake_case field names/types.

**Milestone Value:** Pipeline ingests real telemetry and autonomously creates investigations; detection state is observable via API (unblocks UI diagnostics, Task 5.2).
**Observational Outcomes:** `[O]` Investigation CRD within 5 min of fault post-warmup (NFR1); `[O]` EWMA warmup within 2–3 min of OTEL deploy (NFR6); `[O]` ingestion ≥100 series/min without drops (NFR5); `[O]` ingestion continues during investigation processing (NFR11).

---

## Phase 2: Investigation Execution — Signal Gathering & LLM Root Cause

Investigations gather real Prometheus metrics and Loki logs, query the KB, incorporate SLO context, and produce specific, evidence-backed root cause hypotheses with actionable recommendations. (Epic 2 — FR10–21, FR30; AD-5; NFR2, NFR3, NFR10, NFR14, NFR15) Depends on Phase 1.

### Milestone 2.0: Stabilization

| # | Task | Complexity | Dependencies | Status |
|---|------|-----------|--------------|--------|
| 2-0a | Verify cluster stability | S | Phase 1 | done |
| 2-0b | Close Story 1.4 E2E gap | S | 1.4 | done |
| 2-0c | Investigator test baseline | S | 2-0a | done |
| 2-0d | Verify Qdrant health | S | 2-0a | done |
| 2-0e | Verify LLM config | S | 2-0a | done |

**Tasks 2-0a–2-0e — done.** Stabilization/verification tasks (no formal AC). Detail in `_bmad-output/implementation-artifacts/2-0*.md`.

### Milestone 2.1: Investigation Execution

| # | Task | Complexity | Dependencies | Status |
|---|------|-----------|--------------|--------|
| 2.1 | Verify/fix investigation lifecycle & Job management | L | 2-0a..2-0e | done |
| 2.2 | Fix investigator signal gathering (Prometheus & Loki) | L | 2.1 | done |
| 2.3 | Fix Knowledge Base integration in investigations | M | 2.2, 2-0d | done |
| 2.4 | Fix LLM root cause analysis & recommendations | L | 2.2, 2.3 | done |
| 2.5 | Verify/fix ServiceLevel CRD integration | M | 2.1 | done |

**Task 2.1 — done.** `[T]` Pending→Running transition spawns investigator Job (FR10/11); `[T]` Job failure → Failed within 30s, no orphaned Jobs (FR12/NFR10); `[T]` success → Completed + Job cleanup (FR13); `[T]` operator restart resumes CRDs without duplicates (NFR12).

**Task 2.2 — done.** `[T]` PromQL resolves Prometheus via cluster DNS, returns non-empty metrics (FR14/NFR14); `[T]` LogQL returns relevant logs (FR15); `[T]` data-availability check before LLM; empty results reported, not silent failure (FR16).

**Task 2.3 — done.** `[T]` KB search of `investigations` collection returns results/empty without error, stored in step data (FR17, AD-5); `[T]` completed investigation writes a new KB entry with context/service/resolution (FR30); `[T]` all KB ops work on Qdrant v1.15.0.

**Task 2.4 — done.** `[T]` LLM prompt includes actual signal data (metric values, log excerpts), response references observed evidence (FR18); `[T]` recommendations are specific/actionable, not generic (FR19); `[O]` full investigation ≤10 min p95 (NFR3/NFR15); `[O]` non-LLM steps ≤2 min from CRD creation (NFR2).

**Task 2.5 — done.** `[T]` operator reads ServiceLevel CRDs into investigation context (FR20); `[T]` SLO breach data passed to LLM when present (FR21); `[T]` missing ServiceLevel handled gracefully (no error).

**Milestone Value:** Investigations produce real, evidence-backed root cause + recommendations end-to-end.
**Observational Outcomes:** `[O]` Job failures surface ≤30s with no orphans (NFR10).

---

## Phase 3: UI Layout Shell & Sidebar Navigation

Collapsible left sidebar (Observe/Learn/Manage), responsive 768px–1920px+, investigation-detail auto-collapse. (Epic 3 — FR40–44; AD-3, AD-6, AD-7; NFR17) UI workstream — runs parallel to Phases 1–2.

### Milestone 3.0: UI/Pipeline Stabilization

| # | Task | Complexity | Dependencies | Status |
|---|------|-----------|--------------|--------|
| 3-0a | Fix SLO engine memory leak | M | Phase 2 | done |
| 3-0b | Full pipeline E2E verification | M | Phase 2 | done |
| 3-0c | Full demo walkthrough | M | 3-0b | blocked |
| 3-0d | UI test baseline | S | None | done |
| 3-0e | Fix investigation startup flood | M | 3-0b | done |
| 3-0f | Fix UI investigation detail "not found" | S | 3-0d | done |
| 3-0g | Fix Ollama/LiteLLM integration | M | 2.4 | done |
| 3-0h | Fix investigator RBAC permissions | S | 2.1 | done |

**Tasks 3-0a, 3-0b, 3-0d–3-0h — done.** Stabilization/verification tasks. Detail in `_bmad-output/implementation-artifacts/3-0*.md`.

**Task 3-0c — BLOCKED.** Full demo walkthrough failed in the 2026-04-10 snapshot (see Q1). `[H]` A clean end-to-end demo walkthrough completes without manual intervention. Superseded by Task 6.3 (3/3 repeatability) — revisit there rather than in isolation; do not let it block Milestone 3.1 UI work.

### Milestone 3.1: Layout Shell & Sidebar

| # | Task | Complexity | Dependencies | Status |
|---|------|-----------|--------------|--------|
| 3.1 | Install Tailwind CSS build pipeline | M | None | done |
| 3.2 | Implement layout shell & `base.html` migration | L | 3.1 | done |
| 3.3 | Build sidebar navigation component | M | 3.2 | done |
| 3.4 | Implement sidebar state management & route-driven collapse | M | 3.3 | done |

**Task 3.1 — done.** `[T]` `make tailwind-watch`/`tailwind-build` produce `static/css/tailwind.css`; `[T]` config carries v0.2.0 tokens + breakpoints (sm=768, lg=1200, xl=1920) + content tree-shake paths; `[T]` generated CSS gitignored; `[T]` Dockerfile minifies as a build stage (AD-7).

**Task 3.2 — done.** `[T]` `base.html` imports layout macro (sidebar + 48px top bar + content with 24px padding) using `{% block content %}`; `[T]` responsive 256px/64px sidebar, no horizontal scroll 768–1920px+ (FR43); `[T]` all 29 templates inherit `base.html` (AD-3, verified by grep); `[T]` `layout.html` macro exposes hamburger slot, logo, `{% block breadcrumb %}`.

**Task 3.3 — done (2026-05-23).** Implemented `templates/components/sidebar.html` (`sidebar_group` macro), wired into `layout.html` as Observe/Learn/Manage groups; `base.html` gained an `{% block active_item %}` for active-state plumbing. **Superset decision (product owner):** all 15 live routes retained, sorted into the 3 spec groups (Observe: Investigations/Sources/Health/SLO/Services/Topology · Learn: Knowledge Base/Metrics/Analytics/Reports/Handoff · Manage: Spending/Cost Insights/Notifications/Trust). "Ingestion Stats" deferred to Story 5.2.
- `[T]` `sidebar_group(...)` renders collapsible group w/ label/icon/items + Tailwind → `test_sidebar_navigation.py::TestSidebarGroupMacro::test_renders_label_icon_and_items_with_tailwind`
- `[T]` Groups & membership in order (FR40) → `TestGroupsAndMembership::{test_group_headers_appear_in_order, test_observe_group_membership, test_learn_group_membership, test_manage_group_membership, test_all_fifteen_routes_present}`
- `[T]` ≥1200px expanded with labels (FR42) → `TestExpandedAtWideViewport::{test_sidebar_expanded_width_hook, test_labels_visible_at_lg}`
- `[T]` <1200px 64px icon rail + hover tooltips → `TestCollapsedIconRail::{test_collapsed_rail_width, test_items_expose_tooltip_and_icon}`
- `[T]` 200ms transition + float overlay (FR41) → `TestTransitionAndFloat::{test_sidebar_has_200ms_transition, test_sidebar_floats_over_content}`
- `[T]` active_item highlight (`aria-current="page"` + active style) → `TestActiveItem::test_active_by_url_gets_aria_current_and_style`
- `[H]` Visual hierarchy/grouping reads clearly — **approved by user 2026-05-23** after rendered review (expanded + collapsed screenshots). Accepted dots-only collapsed rail; per-item icons noted as future polish.
- **Bug fixed during `[H]` review:** group icons were rendering as escaped raw SVG text (Jinja autoescape); fixed with `|safe` on the trusted hardcoded SVGs.
- **Test note:** two brittle exact-tag nav assertions (`test_analytics_dashboard.py`, `test_executive_report.py`) loosened to `href=`/label substring checks to accommodate the new anchor markup. Full UI suite: 2111 passed.

**Task 3.4 — done (2026-05-26).** Implemented the three-state sidebar machine driven by a single `data-sidebar-state` attribute on `#app-shell` (the `group/shell` root, added in `components/layout.html`). State is pure-CSS via Tailwind `group-data-[sidebar-state=…]/shell:` utilities on `#sidebar` (width), `#main-content` (margin), and the `sidebar_group` label/chevron spans (visibility) — the `group-data` overrides outrank the bare `lg:` utilities on specificity, so a forced state wins at every breakpoint (AD-6: CSS owns responsive, JS owns only the toggle). New `static/js/sidebar.js` handles the hamburger/`[`-key toggle + per-group persistence; group headers became accessible toggle `<button>`s. `investigations/detail.html` sets `collapsed` (FR44). Tests follow the repo convention (render + static JS/CSS-source assertions, per `test_command_palette.py`): `tests/test_sidebar_state.py` (28 tests). Full UI suite: **2139 passed**.
- `[T]` Non-detail templates → `auto` viewport-responsive (AD-6) → `test_sidebar_state.py::TestAutoStateOnNonDetailPages::{test_root_page_is_auto, test_investigation_list_is_auto, test_auto_uses_responsive_width, test_auto_content_uses_responsive_margin, test_state_root_is_app_shell_group}` (browser-verified: 256px @1300px, 64px rail @1000px)
- `[T]` Investigation-detail → `collapsed` regardless of width, hamburger visible (FR44) → `TestDetailForcedCollapsed::{test_detail_sets_collapsed_state, test_detail_keeps_hamburger_visible, test_sidebar_has_collapsed_width_override, test_content_has_collapsed_margin_override, test_expanded_override_present_for_forced_expand}` (browser-verified: 64px @1300px + hamburger visible)
- `[T]` Manual toggle (hamburger or `[`) writes `sidebar-manual-override`; cleared on next full navigation → `TestManualToggleOverride::{test_sidebar_js_loaded, test_sidebar_js_exists, test_override_written_to_sessionstorage, test_override_cleared_on_full_navigation, test_hamburger_click_wired, test_bracket_key_toggles_sidebar, test_hamburger_has_aria_wiring}` (browser-verified: both toggles flip state + write override; override null after nav; `[` ignored in inputs)
- `[T]` Per-group open/closed persisted by group label; defaults all-expanded → `TestPerGroupPersistence::{test_group_header_is_a_toggle_button, test_groups_expose_label_data_attribute, test_items_list_has_id_for_aria_controls, test_default_groups_expanded, test_persistence_keyed_by_group_label, test_default_expanded_when_unset}` (browser-verified: Observe collapse persists across navigation; Learn default-expanded)
- `[T]` Transitions `width`/`margin-left` 200ms ease-in-out; respects `prefers-reduced-motion` → `TestTransitions::{test_sidebar_width_transition, test_content_margin_transition, test_sidebar_and_content_respect_reduced_motion, test_group_chevron_transition_is_reduced_motion_safe, test_js_respects_reduced_motion_via_css_not_js}` (browser-verified: `transition: all 0.2s cubic-bezier(0.4,0,0.2,1)`)
- `[H]` Collapse/expand renders smoothly without visible reflow or jank (NFR17) — **approved by user 2026-05-26** after rendered review (expanded-wide, collapsed-rail-on-detail, narrow-auto-rail screenshots). Sidebar `width` + content `margin-left` animate in lockstep over 200ms; `position: fixed` overlay avoids content reflow.
- **Drive-by fix:** the top-bar hamburger (`#sidebar-toggle`, from Story 3.2) showed the grey UA-default button background because Tailwind preflight is disabled (`input.css`); gave it `bg-transparent border-0`, matching the new group-header buttons. **Broader follow-up:** other native `<button>`s across the app likely share this UA-default-chrome issue (preflight off) — out of scope here.
- **Test note:** two brittle Story 3.3 regexes in `test_sidebar_navigation.py` (`test_expanded_default_shows_items`, `test_collapsed_group_hides_items`) assumed `class` was the first attribute on the items `<ul>`; loosened `<ul class=` → `<ul[^>]*class=` to accommodate the new `id=` (aria-controls target). Intent preserved.

**Parallelizable:** None within Milestone 3.1 — 3.1→3.2→3.3→3.4 is a strict chain. Task 3.3 has an `[H]` criterion; start its user review early so it overlaps with 3.4 prep. _(max 8 concurrent per config, not reached here)_
**Milestone Value:** Every page renders in a consistent, responsive, navigable shell — foundation for Epics 4–5 views.
**Observational Outcomes:** `[O]` Sidebar transitions sustain 60fps in-browser (NFR17).

---

## Phase 4: Investigation Display & Real-Time Streaming

List/filter investigations, watch them unfold step-by-step via SSE with inline evidence, see related KB entries; SSE auto-reconnects. (Epic 4 — FR22–27; AD-4, AD-5; NFR4, NFR7, NFR9) Depends on Phase 3 (shell) + Phase 2 (real data).

### Milestone 4.1: Investigation Views & Streaming

| # | Task | Complexity | Dependencies | Status |
|---|------|-----------|--------------|--------|
| 4.1 | Investigation list view with status filtering | M | 3.2 | done |
| 4.2 | Investigation detail: summary header & step timeline | L | 4.1 | done |
| 4.3 | SSE real-time streaming & auto-reconnection | L | 4.2 | in progress |
| 4.4 | Related Knowledge Base panel on investigation detail | M | 4.2, 2.3 | pending |

**Task 4.1 — done.** _(merged via PR #4, squash commit `0e46e4e`; 2184 UI tests green at merge; all CI checks passed)_
- `[T]` List renders investigations via `investigation_card(inv)` (`cards.html`) showing service/severity/status/timestamp.
- `[T]` `status_badge(status)` (`status.html`) colors status (green=active, amber=warning, red=failed, gray=completed).
- `[T]` Status-group filter: active (Pending/Running) default; switch to resolved/failed (FR22).
- `[T]` Cards carry 3px status-colored left border; completed cards reduced-opacity/muted.
- `[T]` Empty state via `empty_state(title, description, icon)` (`empty.html`) explaining investigations appear on detection.

**Implemented on branch `feature/4.1-investigation-list-view` (2026-05-26) — awaiting review/merge (not auto-merged, per request; commit `35b8996`).** New macros `components/cards.html` (`investigation_card`), `components/status.html` (`status_badge`), `components/empty.html` (`empty_state`); `investigations/list.html` + `_list_content.html` migrated onto them; status-group tab filter (`status_group` param, default = active) added to `routes/investigations.py`. New components are Tailwind dark-token only (D4-compliant — verified no arbitrary `bg-[#…]` values). SSE hook (`#investigation-list`, `sse-connect=/investigations/stream`) preserved for Task 4.3. Full UI suite: **2184 passed**.
- `[T]` AC1 card service/severity/status/timestamp → `test_investigation_list_view.py::TestInvestigationCardMacro::{test_card_shows_service,test_card_shows_severity,test_card_shows_status_via_badge,test_card_shows_timestamp}`
- `[T]` AC2 status_badge colors (green/amber/red/gray) → `::TestStatusBadgeMacro::{test_badge_active_is_green,test_badge_awaiting_is_amber,test_badge_failed_is_red,test_badge_completed_is_gray}`
- `[T]` AC3 status-group filter, active default (FR22) → `::TestStatusGroupFilter::{test_default_view_shows_active_investigations,test_default_view_hides_completed,test_status_group_resolved_shows_completed,test_status_group_failed_shows_failed,test_active_tab_has_aria_selected_true}`
- `[T]` AC4 3px status border + completed muted → `::TestCardBorderAndMuting::{test_investigating_card_has_green_border,test_failed_card_has_red_border,test_completed_card_is_reduced_opacity,test_active_card_is_not_muted,test_card_border_uses_3px_via_tailwind}`
- `[T]` AC5 empty_state title/description/detection-message → `::TestEmptyStateMacro::{test_empty_state_shows_title,test_empty_state_shows_description,test_empty_state_rendered_in_page_when_no_investigations,test_empty_state_message_mentions_detection}`
- Existing tests updated for the new card markup + default-active filter (intent preserved; `status_group=all` bypasses the default where a test needs all rows): `test_investigation_routes.py`, `test_escalation_urgency_routes.py`, `test_investigation_workflow_states.py`.
- **Review note:** urgency score is no longer shown on the card (was in the legacy table); still computed for `sort=urgency`. Confirm this is acceptable for the card layout, or fold urgency into the card before merge.

**Task 4.2 — done.** _(implemented on branch `feature/4.2-investigation-detail`, commit `517a296`; build-for-review, same flow as 4.1)_
- `[T]` `summary_header(inv)` renders immediately (service/severity/signal-count/status), no SSE dependency (FR23); breadcrumb "Investigations > INV-{id}".
- `[T]` Steps via `investigation_step(step, is_first_evidence, order)` (`investigation.html`) with 3px type-colored left border (metric=indigo, log=green, KB=amber, correlation=light indigo, summary=gray).
- `[T]` Evidence in `ui-monospace`; service names as labels on `surface-raised` (FR25).
- `[T]` `conclusion_block(inv)` shows root cause / affected services / correlated count, visually distinct.
- `[T]` Completed steps render immediately; page never blank (NFR7).

**Implemented (2026-05-26) — full UI suite 2231 passed (+47); D4-compliant (no arbitrary color values); ruff clean.** New `components/investigation.html` (`summary_header`, `investigation_step`, `conclusion_block`, reuses `status_badge`) + `_step_timeline.html`; `detail.html`/`_detail_content.html` migrated onto them (legacy classes dropped on migrated elements); route adds `type` to `PIPELINE_STEPS` + derives `signal_count`; SSE `step-update` repointed to the new (fully-Tailwind) `_step_timeline.html`; legacy `_step_progress.html` removed. SSE hook preserved for 4.3.
- `[T]` AC1 summary header (no-SSE) + breadcrumb → `test_investigation_detail_view.py::TestSummaryHeaderMacro::*` (10 tests incl. `test_header_has_no_sse_dependency`, `test_breadcrumb_reads_investigations_inv_id`, `test_page_renders_summary_header_immediately`)
- `[T]` AC2 step macro + 3px type-colored border → `::TestInvestigationStepMacro::*` (incl. `test_metric_border_is_primary_indigo`, `test_log_border_is_status_healthy_green`, `test_kb_border_is_status_warning_amber`, `test_correlation_border_is_primary_hover`, `test_summary_border_is_status_muted_gray`, `test_step_uses_3px_left_border_width`)
- `[T]` AC3 mono evidence + surface service labels (FR25) → `::TestEvidenceMonoAndServiceLabels::*`
- `[T]` AC4 conclusion_block (root cause/affected/correlated) → `::TestConclusionBlock::*`
- `[T]` AC5 server-rendered, never blank (NFR7) → `::TestStepsRenderServerSide::*` (incl. `test_completed_steps_present_without_streaming`, `test_sse_hook_preserved_for_task_4_3`)
- D4/doctrine guards → `::TestTokenDisciplineAndMigration::*` (no arbitrary color values; migrated header drops legacy classes)
- **Review notes:** (a) `affected_services` is derived (`inv.service` + `service_topology.downstream`, deduped) since findings lacks the field; (b) remaining legacy detail partials (`_findings`, `_unified_timeline`, `_evidence_panel`, `_recommendations`, urgency/remediation/gate/feedback/resolution/KB) intentionally NOT migrated — scoped to header+timeline+conclusion; (c) pre-existing duplicate `id="main-content"` (layout `<main>` + detail div) left as-is (it's the 4.3 SSE/htmx hook).

**Task 4.3 — in progress.** _(branch `feature/4.3-sse-streaming`; build-for-review, not auto-merged)_
- `[T]` Running investigation opens `EventSource` from `static/js/sse.js`; steps append on arrival; list view receives `investigation_created`/`investigation_status` (FR24).
- `[T]` Steps inserted at correct position by `order` field; UI updates ≤2s of event (NFR4).
- `[T]` On drop, reconnect fetches `GET /api/v1/investigations/{id}` and diffs/inserts missed steps by `order` (AD-4 REST backfill).
- `[T]` After 5 failed retries, show "Live updates unavailable — refresh to sync"; detail stays viewable.
- `[T]` New-investigation card highlight fades over 5s.
- `[T]` Uses native `EventSource`, NOT HTMX (AD-4); auto-reconnect ≤5s (NFR9).

**Implemented on branch `feature/4.3-sse-streaming` (2026-05-26) — awaiting review/merge (not auto-merged, per request; commit `65ba7e5`).** New `static/js/sse.js` (356 lines): native `EventSource` per AD-4 — replaces the htmx-ext-sse extension on the investigation detail + list pages; builds an event→element map from `data-sse-swap` attrs (1:1 with the old `sse-swap`) so all 12 detail panels keep updating; capped exponential backoff (`MAX_RECONNECT_MS=5000`, ≤5s NFR9), `MAX_RETRIES=5` then the exact banner; on every (re)connect REST-backfills from the NEW `GET /api/v1/investigations/{id}` JSON endpoint (`investigations_api_bp`) and inserts missed steps by `order`. List stream now emits `investigation_created`/`investigation_status` (FR24). 5s token-colored `@keyframes sse-highlight-fade` in `main.css` (no hex; reduced-motion guard). `htmx-ext-sse.js` retained (still used by `services/detail.html`). D4-clean; ruff clean. Full UI suite: **2265 passed** (+34). Runtime DOM behavior (live append, mid-stream reconnect→backfill, 5-retry banner, 5s fade) to be confirmed in-browser against a live operator (AD-8).
- `[T]` AC1 native ES from sse.js + steps append + list FR24 events → `test_sse_streaming.py::TestAC1NativeEventSourceWiring::{test_sse_js_opens_native_event_source,test_detail_page_wires_sse_js_and_stream_url,test_list_registers_fr24_events,test_list_stream_emits_fr24_event_names}`
- `[T]` AC2 steps inserted by `order`, ≤2s → `::TestAC2StepsInsertedByOrder::{test_inserts_steps_by_data_order,test_keeps_steps_sorted_ascending_by_order,test_update_is_immediate_not_delayed}`
- `[T]` AC3 reconnect + REST backfill diff by order (AD-4) → `::TestAC3ReconnectRestBackfill::{test_auto_reconnects_on_drop,test_backfill_fetches_json_api_endpoint,test_backfill_diffs_and_inserts_missed_steps_by_order,test_backfill_json_endpoint_returns_steps_with_order}`
- `[T]` AC4 5-retry cap + exact banner, detail stays viewable → `::TestAC4RetryLimitAndUnavailableBanner::{test_max_retries_is_five,test_exact_unavailable_message,test_banner_inserted_above_content_not_blanking_it}`
- `[T]` AC5 new-card highlight fades 5s → `::TestAC5NewCardHighlightFade::{test_js_fade_window_is_5000ms,test_css_defines_5s_fade_animation}`
- `[T]` AC6 native EventSource not HTMX + reconnect ≤5s → `::TestAC6NativeNotHtmxAndReconnectWindow::{test_sse_js_uses_native_event_source_not_htmx,test_detail_page_drops_htmx_sse_extension,test_reconnect_window_capped_at_5s,test_htmx_ext_sse_kept_for_other_pages}`
- Updated existing tests to the `data-sse-url`/`data-sse-swap` contract (intent preserved): `test_investigation_detail_view.py::test_sse_hook_preserved_for_task_4_3`, `test_investigation_list_view.py::test_list_sse_container_preserved`.
- **Review note:** all 12 detail SSE panels migrated to native-ES dispatch; lazy `hx-get` panels keep their initial HTMX load and also receive SSE updates. The new backfill endpoint derives steps from the same operator status source (`_get_step_states`/`PIPELINE_STEPS`) as the server-rendered timeline, so REST and SSE stay consistent.

**Task 4.4 — pending.** *(verify Q2 / AD-5 before relying on the read path)*
- `[T]` Viewport >1200px: fixed bottom bar "N Related KB Entries" via `kb_panel(entries, expanded)` (`kb.html`); click expands upward (FR26).
- `[T]` Viewport ≤1200px: panel renders inline below the timeline.
- `[T]` Panel reads KBQueryStep results from the `investigations` Qdrant collection (AD-5); shows titles with relevance context.
- `[T]` 0 results → "0 Related KB Entries" shown, not hidden.
- `[T]` Clicking an entry expands detail in-panel (past context/resolution/service).

**Parallelizable:** 4.1→4.2 sequential; once 4.2 lands, 4.3 and 4.4 may run concurrently (both build on detail). _(max 8 concurrent per config)_
**Milestone Value:** SREs and demo viewers watch investigations unfold live with inline evidence and KB context.
**Observational Outcomes:** `[O]` UI loads ≤3s, list updates ≤2s of SSE (NFR4); `[O]` SSE holds 10 min, reconnects ≤5s (NFR9); `[O]` progressive render of partial step sets (NFR7).

---

## Phase 5: Supporting Views — KB Browsing, Diagnostics & Health

Browse/search KB, view pipeline diagnostics (ingestion + detection stats, EWMA warmup), source connection status, and LLM spending. (Epic 5 — FR28–29, FR31–35; NFR12) Depends on Phase 3 (shell); Task 5.2 also depends on Task 1.4.

### Milestone 5.1: Supporting Views

| # | Task | Complexity | Dependencies | Status |
|---|------|-----------|--------------|--------|
| 5.1 | Knowledge Base browsing, search & detail views | M | 3.2, 2.3 | pending |
| 5.2 | Pipeline diagnostic dashboard (ingestion + detection stats) | M | 3.2, 1.4 | pending |
| 5.3 | Source connection status & LLM spending views | M | 3.2 | pending |

**Task 5.1 — pending.**
- `[T]` Learn > Knowledge Base lists entries with service/title/date (FR28).
- `[T]` Search by keyword or service filters to matches (FR29).
- `[T]` Entry detail shows past root cause, resolution, affected services, source investigation ref (FR31).
- `[T]` Empty KB → explanatory empty state, not blank.

**Task 5.2 — pending.** *(gated on Task 1.4 detection stats API)*
- `[T]` Observe > Ingestion Stats shows `metrics_received`/`logs_received` via `metric_tile(label, value, status, trend)` (`diagnostic.html`) (FR32).
- `[T]` Adds `anomalies_detected`, `anomalies_suppressed`, `active_metric_detectors` tiles (FR33).
- `[T]` Warming up (`samples < minimum`): `ewma_progress(percentage, status)` bar + amber "Warming Up" chip; percentage = `samples / minimum * 100`.
- `[T]` Warmed (`samples >= minimum`): green "Active" chip, visually distinct.
- `[T]` `metrics_received == 0 && logs_received == 0`: red "No Data" chip, distinct from both other states.
- `[T]` Dashboard auto-refreshes on pipeline state change.

**Task 5.3 — pending.**
- `[T]` Observe > Sources shows Prometheus/Loki connection status with indicators (FR34).
- `[T]` Connected → green "Connected" + last-seen; disconnected → red "Disconnected".
- `[T]` Manage > Spending shows LLM provider config + spending metrics (FR35).
- `[T]` Operator restart resumes CRDs without duplicates, verified via source/investigation state consistency (NFR12).

**Parallelizable:** 5.1, 5.2, 5.3 are independent once Phase 3 lands and Task 1.4 is done — run all three concurrently. _(max 8 concurrent per config)_
**Milestone Value:** Eric can diagnose "broken vs. warming up" from the UI in seconds; KB is browsable.
**Observational Outcomes:** `[O]` Operator restart recovery without duplicate investigations/Jobs (NFR12).

---

## Phase 6: Demo Automation & End-to-End Reliability

Full demo lifecycle — deploy, verify, inject fault, watch, recover, repeat — reliably 3/3 for investor presentations. (Epic 6 — FR36–39; NFR8) Depends on Phases 1–5.

### Milestone 6.1: Demo Lifecycle & Validation

| # | Task | Complexity | Dependencies | Status |
|---|------|-----------|--------------|--------|
| 6.1 | Fix demo deployment & port-forward automation | M | Phase 1 | pending |
| 6.2 | Fix fault injection & recovery automation | M | 6.1 | pending |
| 6.3 | End-to-end demo validation — 3/3 repeatability | L | 6.1, 6.2, Phases 1–5 | pending |

**Task 6.1 — pending.**
- `[T]` `make demo-deploy` deploys OTEL Astronomy Shop (16+ services), configures Collector → Beeper ingestion, applies ServiceLevel CRDs (FR36).
- `[T]` `make demo-ui` establishes port-forwards (Beeper UI :8080, operator API, OTEL frontend); UI opens in browser (FR39).
- `[T]` Helm-deployed Qdrant runs v1.15.0 (D2).
- `[T]` `kind-config.yaml` port mappings correct for all demo services.

**Task 6.2 — pending.**
- `[T]` `make demo-fault FAULT=payment-failure` injects fault; anomalous behavior begins (FR37).
- `[T]` `make demo-recover` removes fault; demo returns to normal (FR38).
- `[T]` Multiple fault names (`payment-failure`, `cart-failure`, `high-cpu`) each produce distinct anomalies/investigations.

**Task 6.3 — pending.** *(resolves Q1 / the blocked 3-0c)*
- `[H]` Run the full demo sequence (deploy → verify stats → await EWMA warmup → `demo-fault payment-failure` → investigation appears & completes → verify root cause references "payment service"/"error rate" → verify real Prometheus + Loki evidence → `demo-recover`) **3 consecutive times without cluster restart**, all succeeding (NFR8).
- `[T]` Zero "insufficient data" results while faults are active.
- `[T]` `demo/README.md` documents the full script with timing (2–3 min warmup; 5–10 min investigation).

**Parallelizable:** 6.1→6.2 sequential; 6.3 is the final gate after all prior phases. Task 6.3 has an `[H]` criterion (manual demo run) — schedule the user review session explicitly. _(max 8 concurrent per config)_
**Milestone Value:** Eric joins investor calls confident the demo works repeatably — the project definition of done.
**Observational Outcomes:** `[O]` `payment-failure` completes E2E 3/3 consecutive runs without cluster restart (NFR8).
