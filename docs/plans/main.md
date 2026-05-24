# Implementation Plan: Beeper — Pipeline Fix & UI Overhaul

## Overview

Brownfield delivery across two workstreams: (1) restore the sequential pipeline from OTEL ingestion → anomaly detection → investigation → LLM root cause; (2) overhaul the UI from fixed-width top-nav to a responsive sidebar-navigated interface. Definition of done: a `payment-failure` fault injection produces an evidence-backed investigation 3/3 consecutive runs in a clean, responsive UI. Traces to [docs/reqs/main.md](docs/reqs/main.md); specs in [docs/specs/](docs/specs/).

> **Provenance:** Transcribed from BMAD artifacts (`_bmad-output/planning-artifacts/epics.md` + `_bmad-output/implementation-artifacts/sprint-status.yaml`, generated 2026-04-10) to preserve completion state. Status values reflect that sprint snapshot, verified against git history through Story 3.2. Full per-story detail and Given/When/Then criteria for completed work live in `_bmad-output/implementation-artifacts/<story-slug>.md`.

**Status legend:** `done` · `in progress` · `pending` · `blocked`. Synthex's `next-priority` executes the lowest-numbered actionable `pending` tasks within the current milestone and never crosses a phase boundary in one session.

**Current resume point:** Phase 3, Milestone 3.1 — **Task 3.4 (Sidebar State Management & Route-Driven Collapse)** is the next actionable task. Phases 1–2 complete; Tasks 3.1–3.3 done; Milestone 3.0 complete except the blocked `3-0c` (see Open Questions). Completing 3.4 finishes Milestone 3.1 and Phase 3.

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
| 3.4 | Implement sidebar state management & route-driven collapse | M | 3.3 | pending |

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

**Task 3.4 — pending.**
- `[T]` Non-detail templates set `{% block sidebar_state %}auto{% endblock %}` → viewport-responsive (expanded ≥1200, collapsed <1200) (AD-6).
- `[T]` Investigation-detail template sets `collapsed` → collapsed regardless of width, hamburger still visible (FR44).
- `[T]` Manual toggle (hamburger or `[` key) writes `sidebar-manual-override` to sessionStorage; cleared on next full navigation.
- `[T]` Per-group open/closed state persisted in sessionStorage by group label; defaults all-expanded.
- `[T]` Transitions: `width 200ms ease-in-out` (sidebar), `margin-left 200ms ease-in-out` (content); respects `prefers-reduced-motion`.
- `[H]` Collapse/expand renders smoothly without visible reflow or jank (NFR17).

**Parallelizable:** None within Milestone 3.1 — 3.1→3.2→3.3→3.4 is a strict chain. Task 3.3 has an `[H]` criterion; start its user review early so it overlaps with 3.4 prep. _(max 8 concurrent per config, not reached here)_
**Milestone Value:** Every page renders in a consistent, responsive, navigable shell — foundation for Epics 4–5 views.
**Observational Outcomes:** `[O]` Sidebar transitions sustain 60fps in-browser (NFR17).

---

## Phase 4: Investigation Display & Real-Time Streaming

List/filter investigations, watch them unfold step-by-step via SSE with inline evidence, see related KB entries; SSE auto-reconnects. (Epic 4 — FR22–27; AD-4, AD-5; NFR4, NFR7, NFR9) Depends on Phase 3 (shell) + Phase 2 (real data).

### Milestone 4.1: Investigation Views & Streaming

| # | Task | Complexity | Dependencies | Status |
|---|------|-----------|--------------|--------|
| 4.1 | Investigation list view with status filtering | M | 3.2 | pending |
| 4.2 | Investigation detail: summary header & step timeline | L | 4.1 | pending |
| 4.3 | SSE real-time streaming & auto-reconnection | L | 4.2 | pending |
| 4.4 | Related Knowledge Base panel on investigation detail | M | 4.2, 2.3 | pending |

**Task 4.1 — pending.**
- `[T]` List renders investigations via `investigation_card(inv)` (`cards.html`) showing service/severity/status/timestamp.
- `[T]` `status_badge(status)` (`status.html`) colors status (green=active, amber=warning, red=failed, gray=completed).
- `[T]` Status-group filter: active (Pending/Running) default; switch to resolved/failed (FR22).
- `[T]` Cards carry 3px status-colored left border; completed cards reduced-opacity/muted.
- `[T]` Empty state via `empty_state(title, description, icon)` (`empty.html`) explaining investigations appear on detection.

**Task 4.2 — pending.**
- `[T]` `summary_header(inv)` renders immediately (service/severity/signal-count/status), no SSE dependency (FR23); breadcrumb "Investigations > INV-{id}".
- `[T]` Steps via `investigation_step(step, is_first_evidence, order)` (`investigation.html`) with 3px type-colored left border (metric=indigo, log=green, KB=amber, correlation=light indigo, summary=gray).
- `[T]` Evidence in `ui-monospace`; service names as labels on `surface-raised` (FR25).
- `[T]` `conclusion_block(inv)` shows root cause / affected services / correlated count, visually distinct.
- `[T]` Completed steps render immediately; page never blank (NFR7).

**Task 4.3 — pending.**
- `[T]` Running investigation opens `EventSource` from `static/js/sse.js`; steps append on arrival; list view receives `investigation_created`/`investigation_status` (FR24).
- `[T]` Steps inserted at correct position by `order` field; UI updates ≤2s of event (NFR4).
- `[T]` On drop, reconnect fetches `GET /api/v1/investigations/{id}` and diffs/inserts missed steps by `order` (AD-4 REST backfill).
- `[T]` After 5 failed retries, show "Live updates unavailable — refresh to sync"; detail stays viewable.
- `[T]` New-investigation card highlight fades over 5s.
- `[T]` Uses native `EventSource`, NOT HTMX (AD-4); auto-reconnect ≤5s (NFR9).

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
