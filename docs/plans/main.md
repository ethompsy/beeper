# Implementation Plan: Beeper — Pipeline Fix & UI Overhaul

## Overview

Brownfield delivery across two workstreams: (1) restore the sequential pipeline from OTEL ingestion → anomaly detection → investigation → LLM root cause; (2) overhaul the UI from fixed-width top-nav to a responsive sidebar-navigated interface. Definition of done: a `payment-failure` fault injection produces an evidence-backed investigation 3/3 consecutive runs in a clean, responsive UI. Traces to [docs/reqs/main.md](docs/reqs/main.md); specs in [docs/specs/](docs/specs/).

> **Provenance:** Transcribed from BMAD artifacts (`_bmad-output/planning-artifacts/epics.md` + `_bmad-output/implementation-artifacts/sprint-status.yaml`, generated 2026-04-10) to preserve completion state. Status values reflect that sprint snapshot, verified against git history through Story 3.2. Full per-story detail and Given/When/Then criteria for completed work live in `_bmad-output/implementation-artifacts/<story-slug>.md`.

**Status legend:** `done` · `in progress` · `pending` · `blocked`. Synthex's `next-priority` executes the lowest-numbered actionable `pending` tasks within the current milestone and never crosses a phase boundary in one session.

**Current resume point:** **All implementation tasks merged to `main` — only the Task 6.3 `[H]` 3/3 acceptance run remains.** Phases 1–5 done; Phase 6 Tasks 6.1 (PR #11), 6.2 (PR #12), and 6.3-`[T]` + every live-run blocker (PR #13, `ad2da02` — Finding H, Q4 parser+truncation, Q5 trigger filtering, Q6 RBAC, Q7 attribution dedup, 4σ) all merged. (Status-table rows reconciled 2026-06-01 — earlier passes left them "in progress" though the work had merged.) **The single remaining item is Task 6.3's `[H]` criterion: run the documented `demo/README.md` 3/3 script and witness 3 consecutive evidence-backed payment-failure investigations (NFR8; resolves Q1/`3-0c`).** It is NOT autonomously actionable — it needs (a) the **Anthropic LLM switch** (local qwen3:8b throughput is the only remaining limiter — every code blocker is fixed; see Q4) and (b) a witnessed acceptance session. No other task is actionable until then. NOTE: Phase 6 = live Docker/kind cluster + LLM, AD-8 manual verification.

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
| Q4 | Local `ollama/qwen3:8b` returns unparseable LLM output (6/6 investigators: "Failed to parse LLM response; using defaults") + is slow (~1–2.5 min/step) | RCA falls back to defaults → 6.3 `[H]` can't produce evidence-backed payment RCA; blocks 3/3 | **PARSING FIXED (2026-05-31); speed/truncation still open.** Root cause of the parse failures: `response_parser.parse_json_response` searched for a ```json code fence on the *raw* string BEFORE stripping `<think>`, so a draft fence the qwen3 reasoning block wrote was grabbed instead of the real post-`</think>` answer. Rewrote it as a priority-ordered multi-strategy parser (answer-after-last-`</think>` → raw-fence → think-stripped balanced-brace, string-aware) — `investigator/.../llm/response_parser.py`; 20 unit tests incl. the exact bug repro (`tests/test_response_parser.py::TestParseJsonResponse::test_draft_json_inside_think_is_ignored`), ruff clean, backward-compatible. NOT yet live-validated (needs an investigator image rebuild + a completed investigation; Ollama currently saturated). **Still open:** qwen3 thinking also burns the token budget (slow, can truncate before the JSON) — complementary fix is to disable thinking (`/no_think` / ollama `think:false`) or use a faster/cloud model; tracked with Q5 for the actual run. On `feature/6.3-e2e-demo-validation`. |
| Q5 | Detection over-sensitivity: fires on system/`unknown`-service metrics (e.g. `system_cpu_time_seconds_total`), creating a baseline investigation backlog even on a fresh cluster | Buries an injected fault; backlog + concurrency=2 makes 3/3 impractically slow; noisy demo | **FIX LANDED (2026-06-01); pending live validation.** Root cause: the operator fired an investigation for ANY metric crossing 3σ with no service/metric filtering. Added (operator `src/detection/`): (1) skip anomalies with `service==unknown` (not actionable; `BEEPER_DETECTION_SKIP_UNKNOWN_SERVICE`, default on); (2) configurable metric-name denylist filtering host/runtime telemetry (`system_*`,`v8js_*`,`process_*`,`runtime_*`; `BEEPER_DETECTION_METRIC_DENYLIST`) so only service-health signals trigger. `cargo test` 46 pass (incl. new denylist/env tests), fmt+clippy clean. On `feature/6.3-e2e-demo-validation`. Per user direction, did NOT cap token budgets (limiting reasoning is the wrong lever — tune triggers instead). |
| Q6 | Investigator SA `beeper-investigator` cannot `list investigations.beeper.dev` (403 in topology step; confirmed via `kubectl auth can-i`) | Topology step degraded; recurring 403s | **RESOLVED 2026-05-31** — added `list` to the investigations verbs in `helm/beeper/templates/investigator-rbac.yaml` (was `get,patch` → `get,list,patch`); applied live, `kubectl auth can-i` → yes; guarded by `test_demo_automation.py::TestInvestigatorRbac`. On `feature/6.3-e2e-demo-validation`. |
| Q7 | Service attribution is inconsistent: the same service appears as both `otel-demo/payment` and `payment` (different metrics carry different service-identifying labels → `extract_service` returns different values) | Splits the per-service cooldown fingerprint, so a service can open ~2× the investigations; also clutters the list | **FIX LANDED (2026-06-01).** Added `detection::normalize_service` (strips any `namespace/` prefix → last path segment) applied in both `metrics.rs` + `logs.rs` `extract_service`, so `otel-demo/payment` and `payment` collapse to one identity/fingerprint. Same increment also raised the default deviation threshold 3σ→4σ (`metric/log_threshold`) to quiet per-service baseline self-triggers. `cargo test` 47 pass, fmt+clippy clean. On `feature/6.3-e2e-demo-validation`; pending operator rebuild + live re-observe. |
| Q8 | **Operator spawns UNBOUNDED concurrent investigator Jobs** — one per anomaly Investigation CRD, no global cap. `maxConcurrentInvestigations` (values-dev `llm.*`) is NOT wired to Job spawning (`grep maxConcurrent operator/src` → nothing). At warmup ~22–27 services trip at once → ~25+ investigator pods spawn simultaneously. | **Actual root cause of "demo non-completion on local LLM"** — not qwen speed. ~25 Python investigator pods starved host RAM (free → ~78 MB, ~18 GB compressed) → throttled qwen ~37→~15 tok/s AND overloaded Ollama → big calls exceed the client window → `litellm.APIConnectionError` → retry-amplified spiral → **0/48 completed**. | Open — found 2026-06-02 via live profiling. **Fix: bound concurrent investigator Jobs in the operator** (work-queue/semaphore honouring `maxConcurrentInvestigations`; ~1–2 for local LLM). Corrected qwen profile: isolated + memory-freed → ~37 tok/s, small calls ~4 s, pod→Ollama 10 ms, RCA completes in ~70 s (no timeout). A *single* investigation still ≈12–15 min (~7+ sequential LLM steps) → for a snappy demo prefer Anthropic; for local qwen, Q8 makes it *complete* (slow) instead of spiralling. **Partly addressed by RFC 0001 Phase 1 (PR #17, per-service guard); but see Q9–Q11 for why the baseline still isn't calm.** |
| Q9 | Phase 1 bounds duplicates *per service* but not *global* concurrent investigations. A wide outage (or the Q10/Q11 warmup burst) → ~#services concurrent investigator pods → single-node + local-LLM RAM starvation (live: ~92 MB free, 0/23 complete). | Refines Q-E (which dropped the "blunt cap"). For single-node/local-LLM a global limit IS needed — but as a **work-queue that defers, not drops**. | Open — found 2026-06-03. Safety-net (do Q10/Q11 first); config-gated global work-queue, default off, recommend on for local/single-node. RFC 0001 §10. |
| Q10 | `ewma.rs::update()` emits `deviation=1e6` (instant anomaly) when a near-zero-variance metric changes at all post-warmup. Flat gauges/steady rates are common → first wobble of ~every service fires a false anomaly → the ~23 warmup investigations. | **Primary cause of the "investigation flood"** — false positives, not real incidents. | Open — found 2026-06-03. **Highest-impact, smallest fix:** require a minimum absolute deviation (and/or N corroborating breaches) before firing on a (near-)zero-variance stream. RFC 0001 §10. |
| Q11 | EWMA detector state is in-memory (rebuilt in `DetectionConsumer::run()`), so every operator restart wipes baselines → full re-warmup → a Q10 false-positive burst. Restarts are routine (rolling updates, crashes). | Each operator restart re-triggers the flood. | Open — found 2026-06-03. Fix: persist/warm-start EWMA state, or a startup grace period suppressing firing until variance stabilizes. Pairs with Q10. RFC 0001 §10. |
| Q12 | **The EWMA detector runs on RAW cumulative metrics** — Prometheus counters (`*_total`) and histogram buckets (`*_bucket`) are monotonic/cumulative and reset to 0 on pod restart. EWMA-ing raw cumulative values makes normal load ramps look like spikes and counter resets look like drops. | **The actual dominant driver of the warmup "flood,"** correcting the Q10 hypothesis. Live (post-Q10): 23→**21** baseline investigations, ~all on `*_bucket`/`*_total` with genuine >4σ deviations (e.g. `shipping http_server_duration drop to 0` = a restart counter reset). Q10 (zero-variance floor) only removed ~2 — it was NOT the main cause. | Open — found 2026-06-04 (corrects Q10). Fix: detect on **rates/deltas** for counters/histograms (per-interval increase) and handle counter resets (drop-to-lower = reset, not anomaly), instead of EWMA on raw cumulative values. Likely the highest-leverage detection-quality fix; pairs with Q10/Q11. |

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
| 4.3 | SSE real-time streaming & auto-reconnection | L | 4.2 | done |
| 4.4 | Related Knowledge Base panel on investigation detail | M | 4.2, 2.3 | done |

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

**Task 4.4 — in progress.** _(branch `feature/4.4-related-kb-panel`; build-for-review, not auto-merged)_ *(verify Q2 / AD-5 against a live backend before relying on the read path)*
- `[T]` Viewport >1200px: fixed bottom bar "N Related KB Entries" via `kb_panel(entries, expanded)` (`kb.html`); click expands upward (FR26).
- `[T]` Viewport ≤1200px: panel renders inline below the timeline.
- `[T]` Panel reads KBQueryStep results from the `investigations` Qdrant collection (AD-5); shows titles with relevance context.
- `[T]` 0 results → "0 Related KB Entries" shown, not hidden.
- `[T]` Clicking an entry expands detail in-panel (past context/resolution/service).

**Implemented on branch `feature/4.4-related-kb-panel` (2026-05-26) — awaiting review/merge (not auto-merged, per request; commit `1dd3b14`).** New `components/kb.html` (`kb_panel(entries, expanded, is_novel, exact_match_entry, exact_match_found)`) — fully Tailwind, `bg-surface-overlay` floating panel (UX elevation table), **no new custom CSS** (`main.css` untouched), no arbitrary values. Wide (`lg:` ≥1200px): `lg:fixed lg:bottom-0` anchored bottom bar **"N Related KB Entries"** that expands UPWARD (expandable body `order-first` above the count bar `order-last`). Narrow (<1200px): `static`, inline below the timeline. Per-entry detail via native `<details>/<summary>` (service / past-context / type / date / "Open full entry" + preserved `sendKBFeedback` relevant/not-relevant buttons). New dependency-free `static/js/kb-panel.js` toggles the panel (`aria-expanded`, `max-h-0`↔`max-h-96`, re-binds on `htmx:afterSwap`); reduced-motion respected. `_related_kb.html` now renders `kb_panel(...)`; `_detail_content.html` dropped the legacy `.card`/`<h3>` wrapper but PRESERVED the `hx-get` lazy-load + `data-sse-swap="kb-update"` (Task 4.3 hook). ruff clean. Full UI suite: **2293 passed** (+28).
- `[T]` AC1 wide fixed bottom bar "N Related KB Entries", expands upward (FR26) → `test_related_kb_panel.py::TestAC1WideFixedBottomBarExpandsUpward`
- `[T]` AC2 narrow inline/static below timeline → `::TestAC2NarrowInlineBelowTimeline`
- `[T]` AC3 entry titles with relevance context (AD-5) → `::TestAC3EntryTitlesWithRelevance`
- `[T]` AC4 0 results → "0 Related KB Entries" shown, not hidden → `::TestAC4ZeroResultsShowsCount`
- `[T]` AC5 clicking an entry expands detail in-panel → `::TestAC5EntryDetailExpandsInPanel`
- Updated existing tests to the new markup (intent preserved): `test_investigation_routes.py` (exact-match banner, validation ranking, lazy-load), `test_evidence_timeline.py::TestRelatedKBTemplateEnhancements` (chip status-text vs legacy `.validation-*` classes).
- **Q2/AD-5 (OPEN — must verify before trusting end-to-end):** the KBQueryStep → `investigations` Qdrant read path is verifiable only against a live operator/Qdrant (down in dev); UI built on the existing `/related-kb` route + representative mock data. Runtime responsive/expand DOM behavior verified in-browser per AD-8.

**Parallelizable:** 4.1→4.2 sequential; once 4.2 lands, 4.3 and 4.4 may run concurrently (both build on detail). _(max 8 concurrent per config)_
**Milestone Value:** SREs and demo viewers watch investigations unfold live with inline evidence and KB context.
**Observational Outcomes:** `[O]` UI loads ≤3s, list updates ≤2s of SSE (NFR4); `[O]` SSE holds 10 min, reconnects ≤5s (NFR9); `[O]` progressive render of partial step sets (NFR7).

---

## Phase 5: Supporting Views — KB Browsing, Diagnostics & Health

Browse/search KB, view pipeline diagnostics (ingestion + detection stats, EWMA warmup), source connection status, and LLM spending. (Epic 5 — FR28–29, FR31–35; NFR12) Depends on Phase 3 (shell); Task 5.2 also depends on Task 1.4.

### Milestone 5.1: Supporting Views

| # | Task | Complexity | Dependencies | Status |
|---|------|-----------|--------------|--------|
| 5.1 | Knowledge Base browsing, search & detail views | M | 3.2, 2.3 | done |
| 5.2 | Pipeline diagnostic dashboard (ingestion + detection stats) | M | 3.2, 1.4 | done |
| 5.3 | Source connection status & LLM spending views | M | 3.2 | done |

**Task 5.1 — in progress.** _(branch `feature/5.1-kb-views`; build-for-review, not auto-merged)_
- `[T]` Learn > Knowledge Base lists entries with service/title/date (FR28).
- `[T]` Search by keyword or service filters to matches (FR29).
- `[T]` Entry detail shows past root cause, resolution, affected services, source investigation ref (FR31).
- `[T]` Empty KB → explanatory empty state, not blank.

**Implemented on branch `feature/5.1-kb-views` (commit `af59bf6`) — build-for-review.** Migrated KB index/search/entry templates to dark tokens (no arbitrary values; legacy classes removed on migrated elements). Added structured FR31 fields (`root_cause`/`resolution`/`affected_services`) to `KBEntry` + `kb_service.from_qdrant` parsing (additive, optional; falls back to markdown content + `resolution_outcome`). Shared `kb_type_badge` in `components/kb.html`; `empty_state` for AC4. Full UI suite **2303 passed**; ruff clean.
- `[T]` AC1 list service/title/date (FR28) → `test_kb_views.py::TestAC1ListShowsServiceTitleDate::test_kb_index_lists_service_title_and_date`
- `[T]` AC2 keyword/service search (FR29) → `::TestAC2SearchFiltersToMatches::{test_keyword_search_returns_matching_entries,test_service_filter_returns_filtered_entries}`
- `[T]` AC3 entry detail FR31 fields → `::TestAC3EntryDetailShowsFR31Fields::{test_entry_detail_renders_root_cause_resolution_affected_and_source,test_kbentry_parses_fr31_fields_from_payload}`
- `[T]` AC4 explanatory empty state → `::TestAC4EmptyState::test_empty_kb_renders_explanatory_empty_state`
- **Review note:** service-layer change (`KBEntry` fields + Qdrant parsing); `knowledge/_related.html` left legacy (out of scope). Structured fields populate only when the authoring/resolution pipeline writes them; older entries fall back to markdown.

**Task 5.2 — in progress.** _(branch `feature/5.2-diagnostic-dashboard`; build-for-review, not auto-merged)_ *(gated on Task 1.4 detection stats API — done)*
- `[T]` Observe > Ingestion Stats shows `metrics_received`/`logs_received` via `metric_tile(label, value, status, trend)` (`diagnostic.html`) (FR32).
- `[T]` Adds `anomalies_detected`, `anomalies_suppressed`, `active_metric_detectors` tiles (FR33).
- `[T]` Warming up (`samples < minimum`): `ewma_progress(percentage, status)` bar + amber "Warming Up" chip; percentage = `samples / minimum * 100`.
- `[T]` Warmed (`samples >= minimum`): green "Active" chip, visually distinct.
- `[T]` `metrics_received == 0 && logs_received == 0`: red "No Data" chip, distinct from both other states.
- `[T]` Dashboard auto-refreshes on pipeline state change.

**Implemented on branch `feature/5.2-diagnostic-dashboard` (commit `c6d2c53`) — build-for-review.** New `components/diagnostic.html` (`metric_tile`, `ewma_progress`, `pipeline_state_chip`, Tailwind-only); new `/health/ingestion` route + `ingestion.html`/`_ingestion_content.html`; extended `IngestionStats` with the 7 Task-1.4 fields (snake_case, confirmed vs operator `IngestionStatsResponse`). State precedence red `no_data` → amber `warming` (+progress, pct=samples/min*100 clamped 0–100) → green `active`, all via status tokens. Auto-refresh = HTMX `hx-trigger="every 5s"` (no general pipeline SSE channel; matches `health/status.html`). Added Observe > Ingestion Stats sidebar nav (deferred from Story 3.3). Full UI suite **2316 passed**; ruff clean.
- `[T]` AC1 metrics/logs tiles via `metric_tile` (FR32) → `test_diagnostic_dashboard.py::TestAC1IngestionStatsTiles`
- `[T]` AC2 detection tiles (FR33) → `::TestAC2DetectionTiles`
- `[T]` AC3 warming amber chip + `ewma_progress` bar + pct math → `::TestAC3WarmingUpState`
- `[T]` AC4 warmed green "Active" chip (distinct) → `::TestAC4WarmedActiveState`
- `[T]` AC5 no-data red chip (distinct, precedence) → `::TestAC5NoDataState`
- `[T]` AC6 auto-refresh → `::TestAC6AutoRefresh` (+ `::TestSidebarNavEntry`)
- **Review note:** real numbers + HTMX swap-on-state-change need live-operator verification (AD-8); legacy `health/status.html` buffer card left unmigrated (out of scope).

**Task 5.3 — in progress.** _(branch `feature/5.3-sources-spending`; build-for-review, not auto-merged)_
- `[T]` Observe > Sources shows Prometheus/Loki connection status with indicators (FR34).
- `[T]` Connected → green "Connected" + last-seen; disconnected → red "Disconnected".
- `[T]` Manage > Spending shows LLM provider config + spending metrics (FR35).
- `[T]` Operator restart resumes CRDs without duplicates, verified via source/investigation state consistency (NFR12).

**Implemented on branch `feature/5.3-sources-spending` (commit `deaff9b`) — build-for-review.** Migrated sources + spending templates to dark tokens; new `source_status_badge` in `components/status.html` (connected→green "Connected" + last-seen; error/disconnected/failed→red "Disconnected"; else gray "Unknown"; preserves raw `data-status`). Added `SpendingService.get_provider_config()` (reads `BEEPER_LLM_*` env, masks API key to last 4) + "LLM Provider Configuration" block. AC4/NFR12: added dedup-by-name in `SourceService.get_sources()` + UI-layer consistency tests (operator idempotency itself covered by Rust `test_deterministic_job_name_prevents_duplicates`). Full UI suite **2300 passed**; ruff clean.
- `[T]` AC1 Prom/Loki indicators (FR34) → `test_sources_spending_views.py::TestAC1SourceConnectionStatusIndicators::test_ac1_sources_show_prometheus_loki_status_indicators`
- `[T]` AC2 connected-green+last-seen / disconnected-red → `::TestAC2ConnectedDisconnectedIndicators::{test_ac2_connected_green_with_last_seen_disconnected_red,test_ac2_disconnected_source_renders_red_label}`
- `[T]` AC3 provider config + metrics (FR35) → `::TestAC3SpendingProviderConfigAndMetrics::{test_ac3_spending_dashboard_shows_provider_config_and_metrics,test_ac3_provider_config_masks_api_key_and_reads_env}`
- `[T]` AC4 restart consistency (NFR12) → `::TestAC4RestartStateConsistency::{test_ac4_sources_view_is_consistent_and_dedup_free_after_restart,test_ac4_duplicate_resume_payload_is_deduplicated_by_name}`
- **Review notes:** service-layer changes (`SourceService` dedup, `SpendingService` provider config); `costs.html`/`_cost_breakdown.html` left legacy (out of scope); NFR12 full end-to-end proof needs a live operator restart (UI-layer consistency proven here).

**Parallelizable:** 5.1, 5.2, 5.3 are independent once Phase 3 lands and Task 1.4 is done — run all three concurrently. _(max 8 concurrent per config)_
**Milestone Value:** Eric can diagnose "broken vs. warming up" from the UI in seconds; KB is browsable.
**Observational Outcomes:** `[O]` Operator restart recovery without duplicate investigations/Jobs (NFR12).

---

## Phase 6: Demo Automation & End-to-End Reliability

Full demo lifecycle — deploy, verify, inject fault, watch, recover, repeat — reliably 3/3 for investor presentations. (Epic 6 — FR36–39; NFR8) Depends on Phases 1–5.

### Milestone 6.1: Demo Lifecycle & Validation

| # | Task | Complexity | Dependencies | Status |
|---|------|-----------|--------------|--------|
| 6.1 | Fix demo deployment & port-forward automation | M | Phase 1 | done |
| 6.2 | Fix fault injection & recovery automation | M | 6.1 | done |
| 6.3 | End-to-end demo validation — 3/3 repeatability | L | 6.1, 6.2, Phases 1–5 | in progress |

**Task 6.1 — in progress.** _(branch `feature/6.1-demo-deploy-automation`; build-for-review, not auto-merged. Driven LIVE against the `beeper-demo` kind cluster.)_
- `[T]` `make demo-deploy` deploys OTEL Astronomy Shop (16+ services), configures Collector → Beeper ingestion, applies ServiceLevel CRDs (FR36).
- `[T]` `make demo-ui` establishes port-forwards (Beeper UI :8080, operator API, OTEL frontend); UI opens in browser (FR39).
- `[T]` Helm-deployed Qdrant runs v1.15.0 (D2).
- `[T]` `kind-config.yaml` port mappings correct for all demo services.

**Implemented (2026-05-29).** Fixed four real defects in the demo automation — all rooted in Make running each recipe line in a separate shell, which is exactly the class of flakiness behind the failing `3-0c` / Q1:
- **Finding A — `demo-deploy` leaked its Qdrant port-forward.** `… &` on one recipe line + `kill %1` on another (separate shells) never matched → `:6333` stayed bound → the next `demo-deploy`/`demo-up` failed. Fixed: forward + init + seed + teardown now run in ONE shell with a captured `PF_PID` and an `EXIT` trap. **Verified live** (EXIT trap tears the forward down; Qdrant `/readyz` 200, collections reachable through it).
- **Finding B — `demo-ui`'s `wait` was a no-op.** Forwards backgrounded on separate lines + `wait` in its own childless shell → returned instantly, orphaning the forwards. Fixed: all forwards + `trap 'kill 0' INT TERM EXIT` + `wait` in one shell. **Verified live** (recipe blocks while serving; Ctrl+C group-teardown is verify-by-construction — no TTY in CI/sandbox to signal a process group, manual-confirm per AD-8).
- **Finding C — `demo-ui` never forwarded the operator API.** Added `beeper-operator` `:8081 → svc :8080`. **Verified live**: `http://localhost:8081/healthz` 200 and `/api/v1/ingestion/stats` serves real data (200k+ metrics) — this is the "operator backend unavailable" symptom seen in the UI all along.
- **Finding D — kind/NodePort mismatch.** `values-dev.yaml` set `ui.service.type: NodePort` but pinned no port, so K8s auto-assigned (live: 30351) while `kind-config.yaml` mapped host 5050→node 30050 → `localhost:5050` never reached the UI. Fixed: chart template now renders `nodePort`, `values-dev.yaml` pins `ui.service.nodePort: 30050`, kind-config documented/ordered. **Verified**: `helm template` renders `nodePort: 30050`; live UI + operator + OTel + Jaeger all 200 via the fixed `demo-ui`.
- **D2 confirmed live:** `qdrant/qdrant:v1.15.0` (API reports 1.15.0).
- **Deploy state confirmed live:** 24 OTel services Running, Source `connected=true`, 4 ServiceLevels healthy, operator ingesting.

Test linkage (`demo/tests/test_demo_automation.py`, 13 static tests — pure pyyaml/file-parse, no cluster; AD-8 keeps the *runtime* checks manual). **Now wired into CI** via a new `demo-config` job in `.github/workflows/ci.yml` (also rescues the pre-existing `test_slo_manifests.py`, which ran in no CI job before):
- `[T]` deploy (FR36) → `TestQdrantPortForwardNoLeak::*` (recipe single-shell/trap, init+seed present) + existing `test_slo_manifests.py` (CRD manifests) — plus live confirmation above.
- `[T]` demo-ui forwards (FR39) → `TestDemoUiPortForwards::{test_demo_ui_forwards_beeper_ui,test_demo_ui_forwards_operator_api,test_demo_ui_forwards_otel_frontend_and_jaeger,test_demo_ui_waits_and_traps_in_one_shell}`
- `[T]` Qdrant v1.15.0 (D2) → `TestQdrantVersion::test_values_dev_pins_qdrant_v1_15_0`
- `[T]` kind port mappings correct → `TestKindNodePortConsistency::{test_kind_maps_5050_to_30050,test_ui_service_nodeport_is_pinned_to_30050,test_kind_and_values_nodeport_agree,test_ui_template_supports_nodeport,test_kind_config_valid_two_node_cluster}`
- **Review/verify-on-fresh-cluster notes:** (a) kind `extraPortMappings` apply only at `kind create cluster`, so the 5050→30050 direct-access path is fully proven only after `make demo-down && make demo-up`; (b) OTel frontend-proxy/Jaeger direct kind access needs NodePort exposure in `otel-demo-values.yaml` (left as a documented TODO, not a blind edit — they work today via `demo-ui` port-forward); (c) the AC text "Beeper UI :8080" is a typo — convention is Beeper UI :5050, OTel Shop :8080 (kept); (d) **out of scope:** a pile of stale `inv-anomaly-*` pods stuck Terminating/Unknown (15d old, finalizer issue) — noise, not demo-automation; flag for cleanup.

**Task 6.2 — in progress.** _(branch `feature/6.2-fault-injection`; build-for-review, not auto-merged. Driven LIVE against the `beeper-demo` kind cluster.)_
- `[T]` `make demo-fault FAULT=payment-failure` injects fault; anomalous behavior begins (FR37).
- `[T]` `make demo-recover` removes fault; demo returns to normal (FR38).
- `[T]` Multiple fault names (`payment-failure`, `cart-failure`, `high-cpu`) each produce distinct anomalies/investigations.

**Implemented (2026-05-29).** Found two real fault-injection bugs by cross-checking the `demo-fault` flag/variant mappings against the live flagd config:
- **Finding F (critical) — `payment-failure` set an invalid variant `100%%`.** The recipe used `ON_VARIANT='100%%'` on the assumption that Make collapses `%%`→`%`. It does **not** — `%` is literal in Make *recipes* (only special in pattern rules/functions), so flagd received `defaultVariant=100%%`, which is not a valid `paymentFailure` variant (`100%/90%/…/off`). **The primary demo fault — the one `3-0c`/Q1's 3/3 run depends on — was silently broken.** Fixed → `'100%'`. **Verified live**: injecting now sets `defaultVariant='100%'` (was `'100%%'`).
- **Finding E — `slow-images` set an invalid variant `on`.** `imageSlowLoad`'s variants are `10sec/5sec/off` (no `on`). Fixed → `10sec`. **Verified live**: sets `defaultVariant='10sec'`.
- **`demo-recover` verified live**: resets every flag to `state=DISABLED, defaultVariant=off` (FR38) — confirmed all-clean after each test; cluster left clean.
- The three criterion faults (`payment-failure`, `cart-failure`, `high-cpu`) map to valid, non-off variants; `demo-fault-list` advertises exactly the faults the `case` handles.

Test linkage (`demo/tests/test_demo_automation.py`, +9 tests; pure-parse, no cluster — runtime "investigation appears" stays AD-8 manual). The parser intentionally does NOT collapse `%%`, so Finding F is caught not hidden:
- `[T]` inject (FR37) → `TestFaultInjectionMapping::{test_criterion_faults_are_handled,test_every_fault_uses_a_valid_nonoff_variant,test_payment_failure_uses_100_percent,test_fault_list_matches_case_handler,test_demo_fault_requires_FAULT_arg,test_demo_fault_rejects_unknown_fault}` — plus live confirmation above.
- `[T]` recover (FR38) → `TestFaultRecovery::{test_recover_disables_all_flags,test_recover_iterates_every_flag,test_recover_restarts_flagd}` — plus live confirmation.
- `[T]` distinct faults → `test_every_fault_uses_a_valid_nonoff_variant` (each maps to a distinct valid flag/variant). The runtime *"each produces a distinct investigation"* outcome needs ~10-min EWMA warmup per fault → verified during the **6.3 manual demo run** (AD-8), not automatable here.
- **Notes:** (a) minor — two `make demo-fault` calls within ~1s hit flagd's rollout-restart rate limit (`please wait before attempting to trigger another`); the configmap still updates, only the restart is skipped — normal single-fault usage is unaffected, flagged as a possible future `--wait`/retry hardening; (b) the new `demo/tests` run in the `demo-config` CI job added in 6.1.

**Task 6.3 — in progress.** _(branch `feature/6.3-e2e-demo-validation`; resolves Q1 / the blocked 3-0c)_
- `[H]` Run the full demo sequence (deploy → verify stats → await EWMA warmup → `demo-fault payment-failure` → investigation appears & completes → verify root cause references "payment service"/"error rate" → verify real Prometheus + Loki evidence → `demo-recover`) **3 consecutive times without cluster restart**, all succeeding (NFR8).
- `[T]` Zero "insufficient data" results while faults are active.
- `[T]` `demo/README.md` documents the full script with timing (2–3 min warmup; 5–10 min investigation).

**Progress (2026-05-29).** The `[T]` documentation criterion is DONE and the `[H]` run is staged:
- `[T]` **`demo/README.md` now documents the full timed 3/3 script** — "Full Demo Script — 3/3 Validation (NFR8)": one-time setup + a 7-step per-cycle runbook (verify ingestion via operator API → await EWMA warmup ~2–3 min → `demo-fault payment-failure` → watch investigation ~5–10 min → verify evidence-backed root cause names the payment service with real Prom/Loki data and **zero "insufficient data"** → `demo-recover` → confirm clean), repeated 3× with no restart. Also **fixed a doc bug**: the Available Faults table listed non-existent flag names (`paymentServiceFailure`/`cartServiceFailure`/`adServiceHighCpu`) — corrected to the real `paymentFailure`/`cartFailure`/`adHighCpu` (+ variants), and added the operator-API :8081 access. → `demo/tests/test_demo_automation.py::TestDemoReadmeScript::*` (5 tests, incl. flag-names-match-Makefile guard). The "zero insufficient-data" `[T]` is documented as a pass-criterion and verified during the live run.
- `[H]` **BLOCKED on environment quality — the demo *automation* is verified end-to-end, but a credible 3/3 *outcome* is not achievable on the current local setup.** Drove a full fresh rebuild live (2026-05-31): `make demo-down` → recreate cluster (picks up 6.1 kind-config) → reuse `*:dev` images → `demo-beeper` (validated **Finding H**: proceeds on Ollama with no API key) → `demo-deploy` (validated **6.1 Qdrant port-forward fix**: init-collections + seed_kb succeeded). Fresh cluster came up calm-ish (33→47 investigations vs the old 38k). BUT after ~12 min, **0 of 47 investigations completed**, and diagnosis of the investigator pods found three environmental/config blockers (NOT demo-automation defects):
  1. **LLM quality:** local `ollama/qwen3:8b` produces unparseable output — `Failed to parse LLM query/analysis response; using defaults` on **6/6** sampled investigator pods → RCA degrades to defaults, so conclusions won't reliably reference "payment service / error rate" (fails the `[H]` quality bar).
  2. **LLM speed + concurrency:** ~52s–2.5 min per LLM step × multiple steps/investigation, `maxConcurrentInvestigations: 2`, behind a ~47-deep baseline backlog → an injected fault wouldn't complete in a demo-reasonable window.
  3. **Investigator RBAC 403 (confirmed via `kubectl auth can-i`):** `beeper-investigator` SA cannot `list investigations.beeper.dev` (topology step) — a real permission gap (cf. Task 3-0h).
  - Plus **detection over-sensitivity**: fires on system/`unknown`-service metrics (e.g. `system_cpu_time_seconds_total`), generating the baseline-investigation backlog that buries an injected fault.
  - **Conclusion:** Tasks 6.1/6.2 and 6.3's `[T]` (script/docs) are DONE and live-validated; the 6.3 `[H]` 3/3 run needs (a) a higher-quality/faster LLM (e.g. Anthropic) for parseable RCA, (b) detection-noise tuning for a clean baseline, and (c) the investigator RBAC fix. These are operator/config issues beyond the demo-automation scope — see new follow-ups Q4–Q6. The `[H]` acceptance run stays pending until they're addressed.

**Live-validation pass 2 (2026-06-01) — rebuilt operator+investigator with the Q4/Q5/Q6 fixes, cleared the 3.1k-investigation backlog, redeployed on a clean slate:**
- **Q5 filters PROVEN live:** after 5 min on the clean slate, **0** `service=unknown` and **0** infra-metric (`system_*`/`v8js_*`) investigations (these were the bulk of the old 38k). ✅
- **Q4 parser PROVEN live:** the larger-budget steps (512/1024) now parse with no failures (fence-in-think bug fixed). The single residual parse failure was `impact_assessment` at `max_tokens=256` returning an EMPTY response → **truncation**, not a parse bug → fixed by raising budgets (commit `1a29d15`); needs an investigator image rebuild to go live.
- **Residual (not blocking the fixes, but blocks a *pristine* 3/3):** every *real* service still self-trips 3σ once on the demo's bursty traffic (~36 one-time investigations, vs thousands before) + the Q7 attribution duplication; and completion is slow (`maxConcurrentInvestigations: 2` + local qwen3 ≈ 1–3 min/LLM-step) so a 36-deep queue drains slowly and an injected fault waits behind it.
- **Realistic path to the actual investor 3/3:** use a faster/higher-quality LLM (Anthropic) — qwen3:8b on a single kind node is the throughput/latency bottleneck — and optionally a further detection-tuning increment (raise 3σ→4σ and/or fix Q7) for a calmer baseline. The demo *automation* + all discovered code blockers (Finding H, Q4 parse + truncation, Q5 filtering, Q6 RBAC) are fixed/validated; the remaining gap is environmental (LLM throughput) + a baseline-calm polish, not the Beeper code paths the demo exercises.

**Live-validation pass 3 (2026-06-01) — 4σ + Q7 normalization increment, operator rebuilt, clean-slate redeploy, 5.5-min baseline:** baseline went **38k → 36 (Q5 filters) → 22 (4σ+Q7)** — a ~99.94% reduction. Measured live: **0** slash-form services (Q7 dedup ✅), **0** `service=unknown`, **0** infra-metric (Q5 holds ✅), 22 distinct services with no duplicates. Baseline is now genuinely calm. The only remaining limiter for a *fast* 3/3 is LLM throughput (`maxConcurrentInvestigations: 2` + local qwen3:8b ≈ 1–3 min/step) — infrastructure, not Beeper code. **Recommendation for the actual investor 3/3: switch to Anthropic** (fast, parseable RCA); with every code blocker above fixed, it should pass cleanly. (The investigator token-budget fix `1a29d15` is committed/unit-tested but not yet in the running investigator image — operator-only was rebuilt this pass.)

**Parallelizable:** 6.1→6.2 sequential; 6.3 is the final gate after all prior phases. Task 6.3 has an `[H]` criterion (manual demo run) — schedule the user review session explicitly. _(max 8 concurrent per config)_
**Milestone Value:** Eric joins investor calls confident the demo works repeatably — the project definition of done.
**Observational Outcomes:** `[O]` `payment-failure` completes E2E 3/3 consecutive runs without cluster restart (NFR8).
