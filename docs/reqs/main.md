---
stepsCompleted:
  - step-01-init
  - step-02-discovery
  - step-03-success
  - step-04-journeys
  - step-05-domain
  - step-06-innovation-skipped
  - step-07-project-type
  - step-08-scoping
  - step-09-functional
  - step-10-nonfunctional
  - step-11-polish
classification:
  projectType: saas_b2b
  domain: Agentic AI for SRE
  complexity: medium-high
  projectContext: brownfield
inputDocuments:
  - product-brief-beeper-2026-03-09.md
  - product-brief-beeper-2026-01-27.md
  - brainstorming-session-2026-03-08.md
  - project-overview.md
  - integration-architecture.md
  - source-tree-analysis.md
  - development-guide.md
  - deployment-guide.md
  - api-contracts.md
  - index.md
workflowType: 'prd'
documentCounts:
  briefs: 2
  research: 0
  brainstorming: 1
  projectDocs: 7
---

# Product Requirements Document — Beeper Pipeline Fix & UI Overhaul

**Author:** eric
**Date:** 2026-04-04

## Executive Summary

Beeper is an agentic AI SRE platform that autonomously detects anomalies in Kubernetes clusters, investigates root causes by querying Prometheus metrics and Loki logs, and produces evidence-backed findings via LLM analysis. The end-to-end pipeline — from OTEL telemetry ingestion through anomaly detection, investigation execution, and UI display — is currently broken. Investigations either don't fire or produce vague "insufficient data" results.

This PRD scopes two parallel workstreams to restore Beeper to demo-ready state: (1) a sequential pipeline diagnostic fix from OTEL Collector ingestion through to LLM-backed root cause output, and (2) a UI overhaul converting the fixed-width top-nav layout to a responsive sidebar-navigated interface. Definition of done: `payment-failure` fault injection produces a specific, evidence-backed investigation 3/3 consecutive runs in a clean, responsive UI.

## Success Criteria

### User Success

- **Investor/Evaluator (Diana persona):** Watches a repeatable, scripted demo: inject `payment-failure` → Beeper detects within 5 minutes → investigation completes with specific root cause referencing "payment service" and "error rate" → evidence includes real Prometheus metrics and Loki log excerpts
- **SRE (Sam persona):** Opens the Beeper UI on laptop/tablet, navigates cleanly through grouped sidebar nav (Observe / Learn / Manage) — no clutter, investigation view owns the screen during live demos
- **Demo script is rehearsable:** The full fault → detect → investigate → display cycle is repeatable and completes within a predictable window every time

### Business Success

- **3-month demo-ready target back on track:** End-to-end demo is reliable, scripted, and repeatable for investor conversations
- **Credibility restored:** Every investigation produces specific, evidence-backed findings — zero "insufficient data" results when faults are active
- **First impressions:** UI feels professional — clean sidebar navigation, investigation view is the hero, responsive across laptop/tablet/conference screen sizes

### Technical Success

Pipeline diagnostic checkpoints (each must pass independently) and UI targets are consolidated in the measurable outcomes table below. ServiceLevel CRDs already exist in demo config — verify they're wired into the operator's SLO controller; fix as part of pipeline work if broken.

### Measurable Outcomes

| Outcome | Target |
|---------|--------|
| Ingestion receiving data | `GET /api/v1/ingestion/stats` shows `metrics_received > 0` AND `logs_received > 0` within 5 min of deploy |
| Detection fires on fault | Investigation CRD created within 5 min of `make demo-fault FAULT=payment-failure` |
| Investigator gathers real signals | Investigator Job logs confirm successful Prometheus PromQL + Loki LogQL queries (non-empty results) |
| LLM receives real signal data | Investigation findings reference specific metric values, service names, and log patterns |
| End-to-end in UI | Investigation visible in dashboard with real root cause hypothesis and actionable recommendations |
| Zero vague investigations | 0% "insufficient data" when faults active |
| Repeatable demo script | Payment-failure scenario completes reliably 3/3 consecutive runs |
| UI responsive | Usable at 768px–1920px+, no breakage at 768px tablet |
| Navigation grouped | Observe / Learn / Manage sidebar categories with collapsible hamburger |

**Timing reference (two clocks):** "within 5 min of deploy" (ingestion) and "within 5 min of `make demo-fault`" (detection) are measured from *different* t=0 events. The demo sequence is: deploy → wait 2–3 min for EWMA warmup (NFR6) → inject fault → detect within 5 min (NFR1) → full investigation within 10 min p95 (NFR3).

**"Evidence-backed" pass condition (resolves "zero vague investigations"):** an investigation passes only if its findings contain ≥1 real Prometheus metric value **AND** ≥1 real Loki log excerpt **AND** name the fault-affected service (`paymentservice` for payment-failure). It fails if it contains the literal "insufficient data" or omits any of the three. This is the operational test behind the 0% "insufficient data" and "3/3 consecutive runs" gates.

**3/3 run protocol:** each run is `make demo-fault FAULT=payment-failure` → observe evidence-backed completion → `make demo-recover`, spaced beyond the FR8 cooldown so suppression does not mask a run; no cluster restart between runs (NFR8).

## Product Scope

### MVP Strategy & Philosophy

**MVP Approach:** Problem-Solving MVP — restore the existing design to working state
**Resource:** Solo developer (Eric)
**Definition of Done:** `payment-failure` fault scenario completes 3/3 reliably with evidence-backed root cause in a responsive, sidebar-navigated UI

**Scope boundary (diagnostic-first):** Workstream 1 items are framed "verify/fix" — the binding deliverable is the measurable outcome (payment-failure 3/3, evidence-backed), not a predetermined code change. If a single fix is assessed as larger than a config/calibration change or requires a net-new subsystem, it is escalated as an Open Question before proceeding rather than silently absorbed.

### MVP Feature Set (Phase 1) — This PRD

**Core User Journeys Supported:** All 5 (Diana investor, Eric demo operator, Sam daily SRE, Jordan new user, Eric troubleshooting)

**Workstream 1: Pipeline Fix (prerequisite, sequential):**
1. **OTEL Demo Verification** — Confirm OTEL Astronomy Shop runs correctly, Collector exports configured properly
2. **Beeper Ingestion Fix** — Verify/fix Prometheus remote write and Loki push handlers accept OTEL Collector output
3. **Detection Calibration** — Verify/fix EWMA thresholds and log patterns fire on demo traffic anomalies
4. **Investigator Signal Gathering Fix** — Verify/fix investigator Jobs can reach Prometheus/Loki inside the cluster and pull real signals
5. **LLM Prompt/Context Fix** — Verify/fix investigation steps pass real signal data to LLM, producing specific root causes
6. **ServiceLevel CRD Integration** — Verify/fix SLO controller wiring with existing demo ServiceLevel CRDs

**Workstream 2: UI Overhaul (parallel after checkpoint 1 passes):**
7. **UI Responsive Layout** — Convert fixed-width layout to responsive CSS (768px–1920px+)
8. **UI Navigation Overhaul** — Replace top nav with collapsible left sidebar hamburger menu grouped into Observe / Learn / Manage

**New capabilities added by this PRD:**
- Detection stats in ingestion stats endpoint (`anomalies_detected`, `anomalies_suppressed`, `active_metric_detectors`, `ewma_warmup_samples`)
- Inline Related KB entries panel on investigation detail view

### Post-MVP Features (Phase 2)

- Trust levels and auto-remediation
- Collaborative investigations
- Notification engine (Slack, PagerDuty)
- True mobile responsive (320px+)
- Demo script automation with fault → recovery verification

### Expansion (Phase 3 — v0.2.0)

- Full v0.2.0 feature set per `prd-v0.2.0.md`
- Full investor demo script with detect → investigate → fix → prove lifecycle
- **SRE-centric React UI overhaul** — convert the UI to React for a focused, first-seconds incident-triage experience and a Claude Design pass (see [SRE-Centric React UI Overhaul](#sre-centric-react-ui-overhaul-next-ui-workstream) below)

### Risk Mitigation Strategy

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| OTEL format incompatibility requires code change (not just config) | Medium | High | Test ingestion endpoint with real OTEL Collector output first; worst case is adding a format adapter |
| EWMA thresholds don't calibrate cleanly on demo traffic | Medium | Medium | Capture real demo traffic baseline first; lower thresholds or increase sensitivity for demo |
| "Insufficient data" is an LLM prompt issue, not signal gathering | Low | Medium | Check investigator logs for actual signal payloads before touching prompts |
| UI CSS overhaul breaks existing Jinja templates | Low | Medium | Work in feature branch; test on each template |
| Scope creep into v0.2.0 features during fix work | Medium | Medium | PRD is the guard — anything not in the 8 MVP items is post-MVP |

## User Journeys

### Journey 1: Diana Watches the Demo (Investor/Evaluator — Success Path)

**Diana** is VP of Engineering at a Series B startup. She's been pitched six "AI for ops" tools this quarter. All of them showed dashboards. None of them showed the AI actually doing anything.

**Opening Scene:** Diana joins a video call. Eric shares his screen showing the Beeper UI — clean sidebar on the left, investigation list front and center. "Let me show you what happens when a payment service fails." He runs `make demo-fault FAULT=payment-failure`. The screen is calm. The OTEL demo app is humming along with live traffic from the load generator.

**Rising Action:** Within a couple of minutes, the investigation list updates — a new investigation appears. Diana sees it move from "Pending" to "Running." The sidebar stays out of the way. Eric clicks into the investigation. The detail view fills the screen — step-by-step progress: customer impact assessment, KB query, signal correlation, root cause hypothesis. Each step populates with real data: "HTTP 5xx error rate spiked to 34% on paymentservice," "Correlated with checkout service upstream errors," specific Prometheus metric values and Loki log excerpts inline.

**Climax:** The investigation completes. Root cause: "Payment service returning HTTP 500 errors due to injected failure condition. Error rate correlated across checkout and frontend services. Customer impact: checkout flow unavailable." Recommendations are specific and actionable. Diana leans forward — this isn't a dashboard summarizing alerts. The AI actually investigated, correlated signals across services, and explained what happened with evidence.

**Resolution:** Eric recovers the fault with `make demo-recover`. Diana asks to see it again with a different fault. It works again. Same flow, different root cause, same quality of evidence. Diana schedules a follow-up with her CTO. "This is the first demo where the AI actually showed its work."

**Capabilities revealed:** Reliable end-to-end pipeline, real-time UI updates, evidence-backed investigations, repeatable demo flow, clean distraction-free UI during presentation.

### Journey 2: Eric Runs the Demo (Demo Operator — Setup & Execution)

**Eric** is about to demo Beeper to an investor in 30 minutes. He needs confidence it will work.

**Opening Scene:** Eric opens his terminal. The kind cluster is running. He runs `make demo-deploy` — the OTEL Astronomy Shop spins up with its 16+ microservices, the Collector is configured to forward to Beeper's ingestion endpoint, and ServiceLevel CRDs are applied.

**Rising Action:** Eric runs `make demo-ui` — which sets up port-forwards for the Beeper UI, operator API, and the OTEL demo frontend. He opens the Beeper UI at `localhost:8080`. He checks pipeline health in the UI itself: Observe → Ingestion Stats shows metrics and logs arriving. He opens Observe → Sources — Prometheus and Loki both show connected. He waits 2-3 minutes for EWMA warmup, then injects a fault: `make demo-fault FAULT=payment-failure`. He watches the investigation list — within minutes, a new investigation appears and begins progressing through steps.

**Climax:** The investigation completes with a specific, evidence-backed root cause. Eric runs it two more times with different faults — `cart-failure`, `high-cpu`. Each time: detection fires, investigation runs, specific root cause with real evidence. 3/3 reliable.

**Resolution:** Eric joins the investor call with confidence. The demo script is a known quantity — not a prayer.

**Capabilities revealed:** Reliable demo setup, pipeline health verification via UI, fault injection works predictably, multiple fault scenarios produce distinct investigations, repeatable 3/3, port-forward setup via Makefile.

### Journey 3: Sam Uses the New UI (On-Call SRE — Daily Usage)

**Sam** is mid-level SRE, on-call this week. Beeper has been running against the team's staging environment.

**Opening Scene:** Sam opens Beeper on a laptop. The left sidebar is collapsed — just a hamburger icon. The investigation list is the main view. Three investigations from overnight. Sam scans the list — severity, service name, status — all visible without scrolling horizontally.

**Rising Action:** Sam clicks into a high-severity investigation on `checkout-service`. The detail view expands — the sidebar auto-collapses to give maximum screen real estate to the evidence. Sam reads the root cause hypothesis, scrolls through correlated signals (Prometheus metrics showing latency spike, Loki logs showing connection timeouts). Below the evidence section, a **"Related Knowledge"** panel shows KB entries the investigator already found during its `KBQueryStep` — a past investigation with a matching connection timeout pattern. Sam didn't have to leave the page.

**Climax:** The related KB entry confirms this is a known issue with a documented resolution. Sam confirms the resolution and closes the investigation without ever opening the sidebar.

**Resolution:** For a different investigation where the KB match isn't enough, Sam opens the sidebar (clicks hamburger), navigates to Learn → Knowledge Base for a broader search. The grouped navigation gets Sam there in two clicks. Back to Investigations via Observe → Investigations. The workflow is: inline KB for triage speed, sidebar KB for deeper research. The responsive layout worked on the 13" laptop without horizontal scrolling.

**Capabilities revealed:** Collapsible sidebar maximizes investigation view, grouped navigation (Observe/Learn/Manage) supports natural SRE workflow, inline Related KB panel on investigation detail, responsive layout on laptop, investigation detail shows real evidence, KB search accessible from sidebar.

### Journey 4: Jordan Orients in the UI (Junior SRE — First Time)

**Jordan** joined the SRE team two months ago. First time opening Beeper.

**Opening Scene:** Jordan opens the URL. The investigation list loads — it's the default view. On Jordan's wide monitor (1440px), the left sidebar is **expanded by default** showing the three groups: Observe, Learn, Manage.

**Rising Action:** Jordan sees the structure immediately: **Observe** (Investigations, Sources, Ingestion Stats), **Learn** (Knowledge Base, Metrics), **Manage** (Spending). No guessing. Jordan clicks "Knowledge Base" and browses existing entries to understand what Beeper knows about their services.

**Climax:** An investigation fires while Jordan is browsing. Jordan navigates back to Investigations. They click into the live investigation and watch it progress step by step — customer impact, signal correlation, root cause. It's like reading over a senior engineer's shoulder. The evidence is specific enough that Jordan learns something about the service. The Related Knowledge panel shows a similar past incident — instant context.

**Resolution:** Jordan bookmarks the KB and starts their on-call shift feeling like they have a senior engineer's notes available. The sidebar grouping meant they found everything without asking a teammate "where do I find X?"

**Capabilities revealed:** Sidebar defaults expanded on wide screens (1200px+), discoverable grouped navigation, KB as learning tool, live investigation as teaching tool, inline Related KB for context, intuitive information architecture for new users.

### Journey 5: Eric Troubleshoots a Silent Pipeline (Demo Operator — Failure Recovery)

**Eric** injected `payment-failure` three minutes ago. No investigation has appeared. The investor call is in 20 minutes.

**Opening Scene:** Eric stares at the investigation list. Nothing new. Heart rate rising. He needs to diagnose — fast.

**Rising Action:** Eric opens the sidebar, clicks Observe → Ingestion Stats. The page shows: `metrics_received: 12,847`, `logs_received: 3,201` — data is flowing. Good, not an ingestion problem. He scans further: `anomalies_detected: 0`, `anomalies_suppressed: 0`, `active_metric_detectors: 23`. Zero anomalies detected means the EWMA detectors aren't seeing anything unusual yet. Either the fault hasn't produced enough divergent samples (warmup), or the demo traffic is too noisy for the current thresholds.

**Climax:** Eric checks `ewma_warmup_samples` — most detectors show 8-9 samples against the 10-sample minimum. The fault was injected too recently. He waits 60 more seconds. The stats page updates: `anomalies_detected: 2`. Seconds later, an investigation appears in the list. The pipeline isn't broken — it was warming up.

**Resolution:** Eric now knows: after deploying the demo, wait 2-3 minutes for EWMA warmup before injecting faults. He adds this to his demo prep checklist. If `anomalies_detected` stays at 0 after 5 minutes with an active fault, THAT's a real problem to debug.

**Capabilities revealed:** Detection pipeline visibility via ingestion stats (anomalies detected/suppressed, EWMA warmup status), diagnostic path for "data flowing but no investigations" scenario, exposed via existing `/api/v1/ingestion/stats` endpoint (lightweight addition).

### Journey Requirements Summary

| Journey | Key Capabilities Required |
|---------|--------------------------|
| Diana (Investor Demo) | Reliable pipeline, real-time UI updates, evidence-backed investigations, clean presentation-ready UI |
| Eric (Demo Operator) | Pipeline health verification via UI, predictable fault injection, repeatable demo script, port-forward setup via Makefile |
| Sam (Daily SRE) | Collapsible sidebar, grouped nav, inline Related KB panel on investigation detail, responsive layout |
| Jordan (New User) | Sidebar defaults expanded on wide screens (1200px+), discoverable grouped navigation, KB browsing, live investigation progress |
| Eric (Troubleshooting) | Detection stats in ingestion stats view (anomalies detected/suppressed, EWMA warmup), diagnostic workflow for silent pipeline |

## Technical Context

### Deployment Model

**Single-tenant K8s operator** — one Beeper instance per cluster. No multi-tenancy, no cross-cluster isolation required. Each deployment is self-contained with its own Qdrant StatefulSet, operator, investigator job pool, and UI. Horizontal scaling not in scope for this PRD.

### Permission Model

No authentication or authorization layer in this PRD scope. The UI and operator REST API are unauthenticated — access is controlled at the network/infrastructure level (port-forwarding for demo, cluster-internal for production). Auth deferred to post-MVP.

### Integration Requirements

| Integration | Direction | Protocol | Status |
|-------------|-----------|----------|--------|
| OTEL Collector → Beeper | Inbound | Prometheus remote write (snappy+protobuf) | **Fix required** |
| OTEL Collector → Beeper | Inbound | Loki push API (JSON) | **Fix required** |
| Beeper → Prometheus | Outbound (investigator) | HTTP PromQL query API | **Fix required** |
| Beeper → Loki | Outbound (investigator) | HTTP LogQL query API | **Fix required** |
| Beeper → LLM provider | Outbound (investigator) | LiteLLM → Anthropic/OpenAI/etc. | Verify working |
| Beeper → Kubernetes API | Bidirectional (operator) | kube-rs controller | Verify working |
| Beeper → Qdrant | Bidirectional (investigator + UI) | Qdrant HTTP/gRPC client | Verify working |

**Integration priorities for this PRD:**
1. OTEL Collector → Beeper ingestion (inbound): verify format compatibility — the OTEL Collector's `prometheusremotewrite` exporter must produce exactly the snappy+protobuf format Beeper's ingestion handler expects
2. Beeper → Prometheus/Loki (outbound from investigator Jobs): verify cross-namespace DNS resolution and correct endpoint configuration in Source CRDs
3. All others: verify connectivity, fix if broken

**Real-time (SSE):** Two SSE endpoints — investigation **list** updates and investigation **detail** streaming — emitted by the operator (`:8080`) and consumed by the UI (`:5000`, which may proxy). Reconnection backfill uses `GET /api/v1/investigations/{id}` returning steps in order (idempotent re-fetch); see FR24/FR27 and NFR9.

### Compliance

None required. No HIPAA, PCI-DSS, SOC2, or GDPR obligations for this open-source demo deployment.

## Functional Requirements

### Telemetry Ingestion

- FR1: Operator can receive Prometheus remote write metrics from OTEL Collector in snappy+protobuf format
- FR2: Operator can receive Loki push logs from OTEL Collector in JSON format
- FR3: Operator can buffer incoming telemetry and expose ingestion statistics via API
- FR4: Operator can report per-source ingestion health (bytes received, parse errors, last received timestamp)

### Anomaly Detection

- FR5: Operator can run EWMA-based anomaly detection on buffered metric streams. Detection calibration requirements:
  - FR5a: Detect on per-second **rates** for cumulative counters (`*_total`/`*_count`/`*_sum`), not raw cumulative values; treat a counter drop-to-lower as a reset, not an anomaly
  - FR5b: Skip histogram bucket series (`*_bucket`) and host/runtime/infra telemetry (e.g. `system_*`, `process_*`, `otelcol_*`, `jvm_memory_limit/init`) via a configurable metric-name denylist; skip anomalies on the `unknown` service
  - FR5c: Normalize service identity (strip any `namespace/` prefix) so one service maps to one detection fingerprint
  - FR5d: Default deviation threshold tuned to produce zero false-positive investigations on a quiescent OTEL demo cluster (4σ baseline; optional minimum-absolute-deviation floor for near-zero-variance streams)
- FR6: Operator can run pattern-based anomaly detection on buffered log streams
- FR7: Operator can create Investigation CRDs when anomaly thresholds are crossed
- FR8: Operator can suppress duplicate investigations for the same service within a configurable cooldown window. The window is anchored on investigation state derived from the API (survives operator restart) and is longer after a Failed investigation than a Completed one (defaults: 30 min after Completed, 60 min after Failed), so a persistently-failing signal does not re-fire every few minutes
- FR9: Operator can expose detection status metrics via ingestion stats API: `anomalies_detected`, `anomalies_suppressed`, `active_metric_detectors`, and `ewma_warmup_samples` (the minimum sample count across active metric detectors; detectors are operationally warm once this reaches the configured warmup minimum, default 10)

### Investigation Lifecycle

- FR10: Operator can transition investigations through defined lifecycle states (Pending → Running → Completed/Failed)
- FR11: Operator can spawn investigator Jobs for new investigations, enforcing a configurable cap on concurrent investigator Jobs (`maxConcurrentInvestigations`; default low for single-node/local-LLM, e.g. 2). Investigations beyond the cap are deferred via a work queue and fire when a slot frees — never dropped
- FR12: Operator can track and surface investigator Job failures in the investigation status
- FR13: Operator can clean up completed investigator Jobs after investigation completion, and reconcile orphaned `Running` investigations whose Job no longer exists by transitioning them to `Failed` within one reconciliation interval

### Investigation Execution

- FR14: Investigator can query Prometheus for relevant metrics using PromQL within the cluster
- FR15: Investigator can query Loki for relevant logs using LogQL within the cluster
- FR16: Investigator can verify data availability before committing to LLM analysis
- FR17: Investigator can search the Knowledge Base for similar past incidents
- FR18: Investigator can generate root cause hypotheses using LLM with real signal data
- FR19: Investigator can generate specific, actionable resolution recommendations

### SLO Integration

- FR20: Operator can read ServiceLevel CRDs to determine SLO targets per service
- FR21: Investigator can incorporate SLO breach data into investigation context

### Investigation Display

- FR22: Users can view a list of investigations filterable by status groups (active: Pending/Running, resolved: Completed, failed: Failed). The list defaults to the **active** group on load; when a group is empty it shows an explanatory waiting state (never blank); returning from detail restores the previous scroll position
- FR23: Users can view investigation detail with step-by-step execution progress. A Failed investigation renders the steps completed before failure followed by a visually distinct failure notice (no conclusion block)
- FR24: Users can view real-time investigation updates via SSE without page refresh (separate list and detail streams; see Integration Requirements → Real-time)
- FR25: Users can view evidence inline (Prometheus metric values, Loki log excerpts) within investigation steps
- FR26: Users can view related Knowledge Base entries inline on investigation detail page, read from the KBQueryStep results already stored in the investigation record (no new semantic query at display time); when results are absent or unparseable, show "0 Related KB Entries" without error
- FR27: UI can automatically reconnect SSE streams after network interruption (EventSource 4-state lifecycle: Connected/Disconnected/Reconnected/Failed). During reconnect it shows a subtle "Reconnecting…" indicator below the last step and backfills missed steps via REST (`GET /api/v1/investigations/{id}`, ordered/idempotent); after repeated failures it shows a "Live updates unavailable — refresh to sync" fallback. Detail remains viewable in all states

### Knowledge Base

- FR28: Users can browse Knowledge Base entries
- FR29: Users can search Knowledge Base by keyword or service name
- FR30: Investigator can store investigation outcomes as new Knowledge Base entries
- FR31: Users can view Knowledge Base entry details including past incident context

### System Health & Diagnostics

- FR32: Users can view ingestion statistics showing metrics_received and logs_received counts, auto-refreshing without manual reload so EWMA warmup progress (FR33) is observable in real time
- FR33: Users can view detection statistics (anomalies_detected, anomalies_suppressed, active_metric_detectors, ewma_warmup_samples)
- FR34: Users can view data source connection status (Prometheus, Loki connected/disconnected)
- FR35: Users can view LLM provider configuration and spending metrics (existing capability surfaced under Manage → Spending — verify-only, not new work in this PRD)

### Demo Environment

- FR36: Demo operator can deploy the full demo environment via single Makefile target
- FR37: Demo operator can inject named fault scenarios via Makefile target. `payment-failure` is the only scenario gated by NFR8 (3/3 reliability); `cart-failure` and `high-cpu` (shown illustratively in Journeys 1–2) are supported best-effort and are not held to the 3/3 evidence bar
- FR38: Demo operator can recover from fault scenarios via Makefile target
- FR39: Demo operator can set up port-forwards for all demo services via Makefile target

### Navigation & Layout

- FR40: Users can navigate via a left sidebar organized into Observe, Learn, and Manage groups
- FR41: Users can collapse/expand the sidebar via a hamburger icon. Collapsed, the sidebar is a 64px icon rail (one icon per group, tooltip label on hover) — never a bare hamburger. Below 1200px, manually expanding overlays the content (does not push/shrink it)
- FR42: Sidebar defaults to expanded on screens ≥1200px and collapsed to the icon rail below 1200px
- FR43: UI layout is responsive between 768px and 1920px+ without horizontal scrolling. Below 768px (true mobile, out of scope) the UI shows a minimum-width notice rather than a broken layout
- FR44: Investigation detail view maximizes screen real estate by auto-collapsing the sidebar while it is the active route, regardless of viewport. Navigating back to the list restores the viewport-appropriate default (expanded ≥1200px, icon rail below); the user can always manually override via the hamburger

## Non-Functional Requirements

### Performance

- **NFR1 — Detection latency:** Investigation CRD created within 5 minutes of fault injection (prerequisite: EWMA warmup complete, at least 10 samples collected)
- **NFR2 — Pipeline completion (excluding LLM):** Investigation pipeline steps excluding LLM calls complete within 2 minutes of CRD creation
- **NFR3 — Full investigation completion:** Full investigation including LLM steps completes within 10 minutes at p95 under normal API response times
- **NFR4 — UI responsiveness:** Beeper UI page loads within 3 seconds; investigation list updates within 2 seconds of SSE event received
- **NFR5 — Ingestion throughput:** Ingestion endpoint handles ≥100 metric series/minute (16 OTEL demo microservices × standard scrape intervals) without dropping samples
- **NFR6 — EWMA warmup:** Detection engine reaches operational warmup (10 samples per metric stream) within 2–3 minutes of OTEL demo deploy
- **NFR7 — Investigation detail progressive rendering:** Investigation detail page renders known steps immediately and updates incrementally as steps complete — no blank page while investigation is Running

### Reliability

- **NFR8 — Demo repeatability:** See Success Criteria — payment-failure fault scenario completes end-to-end 3/3 consecutive runs without cluster restart
- **NFR9 — SSE stability:** SSE connection maintains for duration of a typical investigation (10 min); auto-reconnects within 5 seconds of network interruption (verified by integration test simulating disconnect)
- **NFR10 — Investigator Job resilience:** Job failures surface in investigation status within 30 seconds; failed investigations do not leave orphaned Jobs running
- **NFR11 — Ingestion continuity:** Operator continues accepting telemetry during investigation processing — ingestion and detection are not blocked by active investigator Jobs
- **NFR12 — Operator restart recovery:** Operator resumes processing existing Investigation CRDs after pod restart without re-triggering duplicate investigations or spawning duplicate Jobs. Restart must not cause a burst of false-positive investigations: the duplicate-suppression anchor (FR8) is persisted/API-derived so it survives restart. Warm-starting EWMA baselines or a startup grace period that suppresses firing until baselines restabilize is the intended mechanism for the detection path (see Open Questions Q1)

### Integration

- **NFR13 — OTEL Collector compatibility:** Beeper ingestion endpoint accepts the exact output format produced by the OTEL Collector `prometheusremotewrite` exporter (snappy+protobuf) and Loki `loki` exporter (JSON push) without transformation at the Collector side
- **NFR14 — Cluster DNS constraint:** Investigator Jobs must resolve cluster-internal endpoints (Prometheus, Loki) using standard kind cluster DNS defaults without additional cluster admin configuration
- **NFR15 — LiteLLM provider compatibility:** Investigator works with at least one configured LLM provider (Anthropic Claude) without requiring provider-specific code changes
- **NFR16 — Kubernetes API compatibility:** Operator runs against kind cluster Kubernetes version (verify against kube-rs client library version)

### UI Quality

- **NFR17 — Sidebar transition smoothness:** Sidebar collapse/expand CSS transitions render without layout reflow or jank at 60fps; no disruption to user's reading context in the main content area
- **NFR18 — Accessibility:** New components and pages meet WCAG 2.1 AA contrast (4.5:1 normal text, 3:1 large text); all interactive elements are keyboard-focusable with a visible `focus-visible` ring; all transitions and animations respect `prefers-reduced-motion` (instant state change when requested), including the NFR17 sidebar animation

## SRE-Centric React UI Overhaul (Next UI Workstream)

**Status:** Proposed — forward-looking scope, sequenced **after** the Phase 1 `payment-failure` DoD; filed under Expansion (Phase 3 — v0.2.0), not part of the committed MVP. Supersedes the server-rendered Jinja UI **incrementally**; the two coexist during migration.

**Problem:** The current UI (Flask/Jinja + HTMX) is feature-complete but information-dense and confusing under pressure. In the first seconds of an incident an on-call SRE must answer a fixed set of questions — *which service, which component, what is wrong, how bad, since when* — and today's layout makes them hunt. The UI should lead with those answers, in tightened standardized language, with non-essential chrome removed.

**Approach (incremental, incident-triage first):**
1. Rebuild the incident-triage hero surface (investigation list + detail) in React first, against the existing operator REST + SSE API (`:8080`), served via the Flask BFF (R2) so no operator CORS/auth change is required for parity. The BFF serves the React shell on **migrated React deep paths** — a low-priority catch-all that leaves `/api/*`, the SSE endpoints, and not-yet-migrated Jinja routes untouched — which is what makes every migrated view deep-linkable (FR53).
2. Extract a reusable React component library from that surface, built on the existing dark-first Tailwind tokens (FR51); this library is the input to the Claude Design workflow (`/design-sync`), enabling on-brand design iteration that maps 1:1 to shippable components. (This is the React component layer whose absence currently blocks a Claude Design pass — the UI is server-rendered Jinja today.)
3. Migrate the inventory routes view-by-view; React and Jinja coexist without functional regression until the inventory is fully migrated, after which the Jinja templates and Flask render path are retired.

**Routes to migrate (inventory):** the routes surfaced in the Observe/Learn/Manage navigation — Investigations (list + detail), Sources, Ingestion/Detection Stats, Knowledge Base (browse/search + entry detail), Metrics, Spending. Confirm against the live route table before planning; v0.2.0-only views (e.g. topology, trust, SLO) are out of this workstream unless added to the nav.

**"First-seconds" information model** — the triage glance, answerable without interaction. Each fact names its data source so the list row and detail header are designable:

| Priority | Fact | Source (data origin) | Example |
|----------|------|----------------------|---------|
| 1 | Affected service / app (+ namespace) | Investigation CRD `service` (normalized, FR5c) | `otel-demo/paymentservice` |
| 2 | Affected component | Anomalous signal subsystem (metric family / endpoint / container) from the triggering anomaly — a dedicated field may need investigator output (see R5) | payment gateway call path |
| 3 | Problem state (plain language) | Triggering anomaly signal via the FR47 mapping | "HTTP 5xx error rate elevated — 34%" |
| 4 | Severity | Investigation severity | High |
| 4b | Customer impact / blast radius | **Gated on RFC 0001 Phase 3** (cross-service correlation) — not in the first increment; see FR48 | checkout unavailable; upstream: frontend, checkout |
| 5 | Elapsed time (since creation) | Investigation `created_at` | started 2m ago |
| 6 | Investigation status | Investigation CRD status + step progress | Running — step 4/7 |

### Functional Requirements (React UI)

**First increment (incident-triage surface):**

- FR45: Incident-triage views surface the first-seconds facts (service, component, problem state, severity, elapsed time, status) at a glance — visible without clicks or expansion
- FR46: The investigation list orders active, high-severity incidents first; each row communicates service, component, problem state, severity, and age without horizontal scrolling
- FR47: Problem state is rendered in standardized plain language. The first increment uses a per-metric **heuristic mapping** in the frontend (`{metric pattern → template}`, e.g. `http_*_5xx*` → "HTTP {code} error rate elevated ({value}%)") covering at least the demo fault scenarios; when no pattern matches it falls back to the raw anomaly description from the investigation record. A canonical symptom taxonomy is deferred (R4)
- FR49: The UI is a React frontend consuming the existing operator REST + SSE API via the Flask BFF (R2). **Parity bar** — the React list + detail must implement every capability of the Jinja views they replace: SSE 4-state lifecycle + REST backfill (FR24/FR27), inline evidence (FR25), Related KB including the "0 entries" state (FR26), status-group filter + empty/waiting state + scroll restore (FR22), Failed-investigation rendering (FR23), and sidebar state rules (FR41–FR44). No capability regresses
- FR50: The incident-triage surface (list + detail) ships first; remaining inventory routes migrate view-by-view; React and Jinja coexist without functional regression until the inventory is fully migrated, after which the Jinja templates and Flask render path are retired
- FR51: A reusable React component library is extracted, **built on the existing dark-first Tailwind design tokens** (color palette, spacing, motion, typography per the UX design specification — no hardcoded color/spacing/motion values), and structured for export to Claude Design via `/design-sync` (compiled, renderable components) so design iteration maps directly to shippable code
- FR52: A language/simplification pass produces two reviewable artifacts before each view's React implementation: (1) a **terminology glossary** mapping current labels → standardized SRE labels (statuses, step names, evidence summaries); (2) a **visual-density audit** naming the specific elements to remove or de-emphasize per view. Not a subjective "tidy-up"
- FR53: **Every migrated view is a shareable permalink.** The URL encodes all *content/navigation* state needed to reproduce the view, as path + query params (or hash) — **not** in `sessionStorage`/`localStorage`. Per surface:
  - **Investigation list:** the selected status-group filter (and any future list filters), mapped to a backing list query (see R6)
  - **Investigation detail:** the investigation id (path) and the anchored step (`#step-<id>`), so a shared link lands on the step under discussion
  - **KB browse/search:** the search query (keyword / service, FR29). *(The inline Related KB panel on detail (FR26) is driven by stored KBQueryStep results, not a user query — nothing to encode beyond the investigation id.)*

  Opening a URL cold (hard refresh, or a different person) reconstructs the identical view: the BFF serves the React shell for migrated React paths, and each view hydrates its data from the URL params via the operator API. **Every encoded state must have a backing reload path** (an API query or an addressable resource); state with no backing API is not permalink-eligible. *Ephemeral chrome* — sidebar collapsed/expanded and pixel scroll offset — stays local and is NOT in the permalink; a detail permalink still auto-collapses the sidebar per FR44 (which fires on the detail route regardless of how the user arrived). This supersedes FR22's storage-scoped filter/selection for migrated views; not-yet-migrated Jinja routes remain governed by FR22 and are inherently URL-addressable, so they sit outside the FR53/NFR24 bar. (Holds under the current no-auth model — everyone with access sees the same view; if auth is added (R3), permalinks must stay access-consistent.)

**Later increments (out of scope for the first React increment):**

- FR48: Incident detail shows blast radius — the upstream/downstream services correlated to the incident. **Gated on RFC 0001 Phase 3** (cross-service correlation), which is not yet delivered (the operator produces no `correlatedServices`/`downstream[]` fields today). Until it ships, the detail view shows single-service triage facts with an "impact: not yet correlated" placeholder

### Non-Functional Requirements (React UI)

- **NFR19 — Triage glance:** the "first-seconds" facts (FR45) are visible above the fold on incident detail and within each list row, without interaction, at 768px–1920px+
- **NFR20 — Functional parity gate:** each React view reaches parity with the Jinja view it replaces — measured against the FR49 parity bar (and the equivalent capability set for non-incident routes) — before that Jinja route is retired
- **NFR21 — Responsiveness:** React incident views are interactive within 3 s of load; SSE-driven updates render within 2 s of event receipt (carries NFR4)
- **NFR22 — Accessibility parity:** React components meet the same bar as NFR18 (WCAG 2.1 AA contrast, keyboard `focus-visible` rings, `prefers-reduced-motion`)
- **NFR23 — Design-sync compatibility:** the component library builds to a compiled component bundle — the artifact `/design-sync` ingests (a `dist/` bundle, plus Storybook stories if the chosen kit provides them). The exact expected format is confirmed by a trial `/design-sync` run before FR51 is finalized (see R1)
- **NFR24 — Permalink integrity:** a URL copied from any migrated view, opened cold by another user, renders the same view and data — no view state is reachable only through in-app navigation (under the R3 no-auth model). Verified by a test that loads representative deep links directly (filtered list; a **Completed** investigation detail — avoids SSE-update flakiness; KB query) with no prior navigation

### Definition of Done — first increment

- React incident list + detail reach the FR49 parity bar (all listed states), verified by porting the existing UI test scenarios (UI test suite under `ui/tests/`)
- **Triage-glance test:** two reviewers who did not build the feature and have not seen the UI, shown a running investigation's detail cold and asked "what is wrong and how bad is it?", each correctly name the service, problem state, and severity within 5 seconds, across ≥3 distinct recorded incidents; any miss triggers a language/layout iteration. ("Component" joins the unassisted bar once R5 defines its source.)
- The extracted component library builds to a bundle that a trial `/design-sync` run ingests without error, enabling a Claude Design pass
- **Permalink check:** URLs for a filtered list, a Completed investigation detail (anchored to a step), and a KB search, opened cold with no prior navigation, render the same view — proven by a test that loads them directly (NFR24)

### Definition of Done — workstream (Jinja retirement)

- Every route in the migration inventory has a React view at functional parity (NFR20) and accessibility parity (NFR22); the Jinja templates and Flask render path are deleted; no route is served by Jinja

### Success Metrics (observational, post-rollout)

- Reduced time-to-triage and fewer "where do I find X?" moments — measured by a post-rollout SRE survey against the current Jinja baseline (not a build-time gate)

### Open Questions (React UI)

| # | Question | Impact | Status |
|---|----------|--------|--------|
| R1 | Component library — build bespoke vs. adopt an existing React/Tailwind kit (must be skinnable to the dark-first tokens, FR51)? | Effort + design-sync fidelity | Open |
| R2 | Hosting — **resolved: Flask BFF** (reuses the existing SSE proxy; no operator CORS/auth change — this is the FR49 / Approach contract). A later move to a static bundle calling `:8080` directly would re-open operator CORS + the auth surface (R3) and the FR49 "no operator change" claim, and requires PRD escalation. | CORS, auth surface, deploy shape, SSE latency hop | **Resolved — Flask BFF** |
| R3 | Does retiring Jinja change the permission model? PRD currently scopes no auth (network-level only). | Security surface of a static SPA | Open |
| R4 | Problem-state plain language (FR47) — canonical symptom taxonomy vs. the first-increment per-metric heuristic? | Consistency/scale of triage language | Open — heuristic-first for the increment |
| R5 | "Affected component" (model row 2) — is there a CRD/investigator field for it, or is it derived from the anomalous signal? | Whether the list row needs new investigator output | Open |
| R6 | Does the operator list endpoint (`GET /api/v1/investigations`) accept a status filter for filtered-list permalinks (FR53), or does the client filter the full list? | Backing API for list permalinks | Open — verify API contract |

## Open Questions

These items are resolved by clarifications above where context allowed; the following remain genuinely open. All are **non-blocking** for the committed payment-failure DoD — they are detection-quality and lifecycle hardening for broader/production use.

| # | Question | Impact | Status |
|---|----------|--------|--------|
| Q1 | Should EWMA detector baselines persist across operator restarts (vs. a startup grace period)? (NFR12, FR5) | Avoids a re-warmup false-positive burst on every restart | Open — non-blocking; FR8's persisted suppression anchor covers the creation path in the interim |
| Q2 | Should the global concurrent-investigation work-queue (FR11) default **on** for single-node/local-LLM deployments? | Prevents RAM starvation under wide outages; currently the per-service guard is the primary bound | Open — config-gated, default off; recommended on for local/single-node |
| Q3 | Orphaned `Running` investigations whose Job was garbage-collected (FR13) — reconcile to `Failed` on a timer? | Stuck `Running` rows after Job GC | Open — reconciliation requirement stated in FR13; residual timing gap tracked for follow-up |
