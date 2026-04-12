---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - prd.md
  - architecture.md
  - ux-design-specification.md
---

# Beeper - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for Beeper Pipeline Fix & UI Overhaul, decomposing the requirements from the PRD, UX Design, and Architecture into implementable stories.

**Context:** Brownfield project. Two parallel workstreams: (1) Sequential pipeline diagnostic fix from OTEL ingestion through LLM root cause output. (2) UI overhaul converting fixed-width top-nav to responsive sidebar-navigated interface. Definition of done: `payment-failure` fault injection produces evidence-backed investigation 3/3 consecutive runs in a clean, responsive UI.

## Requirements Inventory

### Functional Requirements

**Telemetry Ingestion:**
- FR1: Operator can receive Prometheus remote write metrics from OTEL Collector in snappy+protobuf format
- FR2: Operator can receive Loki push logs from OTEL Collector in JSON format
- FR3: Operator can buffer incoming telemetry and expose ingestion statistics via API
- FR4: Operator can report per-source ingestion health (bytes received, parse errors, last received timestamp)

**Anomaly Detection:**
- FR5: Operator can run EWMA-based anomaly detection on buffered metric streams
- FR6: Operator can run pattern-based anomaly detection on buffered log streams
- FR7: Operator can create Investigation CRDs when anomaly thresholds are crossed
- FR8: Operator can suppress duplicate investigations for the same service within a cooldown window
- FR9: Operator can expose detection status metrics (anomalies_detected, anomalies_suppressed, active_metric_detectors, ewma_warmup_samples) via ingestion stats API

**Investigation Lifecycle:**
- FR10: Operator can transition investigations through defined lifecycle states (Pending → Running → Completed/Failed)
- FR11: Operator can spawn investigator Jobs for new investigations
- FR12: Operator can track and surface investigator Job failures in the investigation status
- FR13: Operator can clean up completed investigator Jobs after investigation completion

**Investigation Execution:**
- FR14: Investigator can query Prometheus for relevant metrics using PromQL within the cluster
- FR15: Investigator can query Loki for relevant logs using LogQL within the cluster
- FR16: Investigator can verify data availability before committing to LLM analysis
- FR17: Investigator can search the Knowledge Base for similar past incidents
- FR18: Investigator can generate root cause hypotheses using LLM with real signal data
- FR19: Investigator can generate specific, actionable resolution recommendations

**SLO Integration:**
- FR20: Operator can read ServiceLevel CRDs to determine SLO targets per service
- FR21: Investigator can incorporate SLO breach data into investigation context

**Investigation Display:**
- FR22: Users can view a list of investigations filterable by status groups (active: Pending/Running, resolved: Completed, failed: Failed)
- FR23: Users can view investigation detail with step-by-step execution progress
- FR24: Users can view real-time investigation updates via SSE without page refresh
- FR25: Users can view evidence inline (Prometheus metric values, Loki log excerpts) within investigation steps
- FR26: Users can view related Knowledge Base entries inline on investigation detail page
- FR27: UI can automatically reconnect SSE streams after network interruption

**Knowledge Base:**
- FR28: Users can browse Knowledge Base entries
- FR29: Users can search Knowledge Base by keyword or service name
- FR30: Investigator can store investigation outcomes as new Knowledge Base entries
- FR31: Users can view Knowledge Base entry details including past incident context

**System Health & Diagnostics:**
- FR32: Users can view ingestion statistics showing metrics_received and logs_received counts
- FR33: Users can view detection statistics (anomalies_detected, anomalies_suppressed, active_metric_detectors, ewma_warmup_samples)
- FR34: Users can view data source connection status (Prometheus, Loki connected/disconnected)
- FR35: Users can view LLM provider configuration and spending metrics

**Demo Environment:**
- FR36: Demo operator can deploy the full demo environment via single Makefile target
- FR37: Demo operator can inject named fault scenarios via Makefile target
- FR38: Demo operator can recover from fault scenarios via Makefile target
- FR39: Demo operator can set up port-forwards for all demo services via Makefile target

**Navigation & Layout:**
- FR40: Users can navigate via a left sidebar organized into Observe, Learn, and Manage groups
- FR41: Users can collapse/expand the sidebar via a hamburger icon
- FR42: Sidebar defaults to expanded on screens 1200px wide or wider
- FR43: UI layout is responsive between 768px and 1920px+ without horizontal scrolling
- FR44: Investigation detail view maximizes screen real estate by auto-collapsing sidebar during active view

### NonFunctional Requirements

**Performance:**
- NFR1: Detection latency — Investigation CRD created within 5 minutes of fault injection (prerequisite: EWMA warmup complete, at least 10 samples collected)
- NFR2: Pipeline completion (excluding LLM) — Investigation pipeline steps excluding LLM calls complete within 2 minutes of CRD creation
- NFR3: Full investigation completion — Full investigation including LLM steps completes within 10 minutes at p95
- NFR4: UI responsiveness — Beeper UI page loads within 3 seconds; investigation list updates within 2 seconds of SSE event received
- NFR5: Ingestion throughput — Ingestion endpoint handles ≥100 metric series/minute without dropping samples
- NFR6: EWMA warmup — Detection engine reaches operational warmup (10 samples per metric stream) within 2–3 minutes of OTEL demo deploy
- NFR7: Investigation detail progressive rendering — renders known steps immediately and updates incrementally as steps complete

**Reliability:**
- NFR8: Demo repeatability — payment-failure fault scenario completes end-to-end 3/3 consecutive runs without cluster restart
- NFR9: SSE stability — SSE connection maintains for 10 min; auto-reconnects within 5 seconds of network interruption
- NFR10: Investigator Job resilience — Job failures surface in investigation status within 30 seconds; failed investigations do not leave orphaned Jobs
- NFR11: Ingestion continuity — Operator continues accepting telemetry during investigation processing
- NFR12: Operator restart recovery — Operator resumes processing existing Investigation CRDs after pod restart without duplicate investigations or Jobs

**Integration:**
- NFR13: OTEL Collector compatibility — Beeper ingestion accepts exact output format from OTEL Collector (snappy+protobuf, JSON push) without Collector-side transformation
- NFR14: Cluster DNS constraint — Investigator Jobs must resolve cluster-internal endpoints using standard kind cluster DNS defaults
- NFR15: LiteLLM provider compatibility — Investigator works with at least one configured LLM provider (Anthropic Claude)
- NFR16: Kubernetes API compatibility — Operator runs against kind cluster Kubernetes version

**UI Quality:**
- NFR17: Sidebar transition smoothness — Sidebar collapse/expand CSS transitions render at 60fps without layout reflow or jank

### Additional Requirements

**From Architecture:**
- AD-1: OTEL protobuf schema alignment — verify-first, adapt-if-needed approach. Beeper adapts to Collector output; Collector config must NOT be modified
- AD-2: Detection stats API extension — extend existing `/api/v1/ingestion/stats` on :8080 with additive fields only. Existing fields must NOT change
- AD-3: Layout shell template inheritance — modify `base.html` to include sidebar; all 29 page templates inherit automatically. Atomic deployment — all routes adopt simultaneously
- AD-4: SSE reconnection and REST backfill — no `Last-Event-ID` support. Client reconnects via EventSource + REST fallback via `GET /api/v1/investigations/{id}`. Steps have `order` field for correct positioning
- AD-5: Related KB panel — query `investigations` collection for KBQueryStep results by investigation ID. Assumption to verify during pipeline fix
- AD-6: Sidebar state management — hybrid server-rendered default (`{% block sidebar_state %}`) + client-side override (sessionStorage). CSS handles responsive; JS for user toggle only
- AD-7: Tailwind build pipeline integration — standalone binary, `make tailwind-watch` for dev, `make tailwind-build` for production, UI Dockerfile build stage
- AD-8: Integration testing strategy — manual verification via Makefile targets + `kubectl` + `curl`. Pre-implementation test baseline required
- Dual HTTP server architecture: :8080 (Axum management API) and :9090 (ingestion server) are separate servers in same process
- Qdrant version alignment: upgrade Helm chart Qdrant from v1.12.0 to v1.15.0 to match local development
- Cross-workstream dependency: FR9 detection stats API (Rust :8080) must ship before UI diagnostic dashboard can render
- No starter template — brownfield. First task is test baseline, not project initialization
- Development inner loop: Operator (Rust) has slow iteration (Docker rebuild + kind load); UI (Flask) has fast iteration (hot reload). Plan accordingly

**From UX Design:**
- Responsive layout: 768px minimum, sidebar collapse at 1200px breakpoint, ultrawide at 1920px+
- Dark-first color palette (carry forward from v0.2.0): `#0f0f1a` surface base, `#6366f1` indigo primary. No light mode
- Route-driven sidebar collapse: investigation detail auto-collapses sidebar regardless of viewport width
- Sidebar behavior per breakpoint: <1200px overlays content (float), >=1200px pushes content (resize)
- Component macro architecture: 8 new files in `templates/components/`, 12 macros with canonical filenames
- SSE lifecycle management: EventSource-based (`static/js/sse.js`), completely separate from HTMX
- Scroll position preservation on list-to-detail-to-list navigation (sessionStorage)
- Empty states always explanatory, never blank
- EWMA warmup displayed as progress bar with percentage; amber to green transition on completion
- Related KB panel: anchored bottom bar on wide screens (>1200px), inline on narrow. Always shows count (even 0)
- Summary header renders immediately on investigation detail (no SSE dependency)
- New investigation highlight animation (5s fade); first evidence emphasis (2s settle)
- Evidence rendered in monospace (`ui-monospace` font family)
- Step type color coding via 3px left borders (metric=indigo, log=green, KB=amber, correlation=light indigo, summary=gray)
- Tailwind/CSS coexistence rule: never mix on same element. New components Tailwind only; existing CSS preserved until per-template migration
- Tailwind semantic tokens required: `bg-surface-base`, never `bg-[#0f0f1a]`
- Jinja2 macro component files with canonical names (sidebar.html, cards.html, investigation.html, status.html, diagnostic.html, kb.html, empty.html, layout.html)

### FR Coverage Map

| FR | Epic | Description |
|----|------|-------------|
| FR1 | Epic 1 | Prometheus remote write ingestion (snappy+protobuf) |
| FR2 | Epic 1 | Loki push log ingestion (JSON) |
| FR3 | Epic 1 | Telemetry buffering and ingestion stats API |
| FR4 | Epic 1 | Per-source ingestion health reporting |
| FR5 | Epic 1 | EWMA-based metric anomaly detection |
| FR6 | Epic 1 | Pattern-based log anomaly detection |
| FR7 | Epic 1 | Investigation CRD creation on anomaly threshold |
| FR8 | Epic 1 | Duplicate investigation suppression (cooldown) |
| FR9 | Epic 1 | Detection stats exposure via ingestion stats API |
| FR10 | Epic 2 | Investigation lifecycle state transitions |
| FR11 | Epic 2 | Investigator Job spawning |
| FR12 | Epic 2 | Job failure tracking in investigation status |
| FR13 | Epic 2 | Completed Job cleanup |
| FR14 | Epic 2 | Prometheus PromQL query from investigator |
| FR15 | Epic 2 | Loki LogQL query from investigator |
| FR16 | Epic 2 | Data availability verification before LLM |
| FR17 | Epic 2 | Knowledge Base search for similar incidents |
| FR18 | Epic 2 | LLM root cause hypothesis with real signal data |
| FR19 | Epic 2 | Specific, actionable resolution recommendations |
| FR20 | Epic 2 | ServiceLevel CRD reading for SLO targets |
| FR21 | Epic 2 | SLO breach data in investigation context |
| FR22 | Epic 4 | Investigation list with status group filtering |
| FR23 | Epic 4 | Investigation detail with step-by-step progress |
| FR24 | Epic 4 | Real-time SSE investigation updates |
| FR25 | Epic 4 | Inline evidence (metrics, logs) in steps |
| FR26 | Epic 4 | Inline Related KB entries on detail page |
| FR27 | Epic 4 | SSE auto-reconnect on network interruption |
| FR28 | Epic 5 | Knowledge Base browsing |
| FR29 | Epic 5 | Knowledge Base search by keyword/service |
| FR30 | Epic 2 | Store investigation outcomes as KB entries |
| FR31 | Epic 5 | KB entry detail with past incident context |
| FR32 | Epic 5 | Ingestion stats display (metrics/logs counts) |
| FR33 | Epic 5 | Detection stats display (anomalies, EWMA warmup) |
| FR34 | Epic 5 | Source connection status display |
| FR35 | Epic 5 | LLM provider config and spending display |
| FR36 | Epic 6 | Deploy full demo via Makefile target |
| FR37 | Epic 6 | Inject named fault scenarios via Makefile |
| FR38 | Epic 6 | Recover from faults via Makefile |
| FR39 | Epic 6 | Port-forward setup via Makefile |
| FR40 | Epic 3 | Left sidebar with Observe/Learn/Manage groups |
| FR41 | Epic 3 | Sidebar collapse/expand via hamburger icon |
| FR42 | Epic 3 | Sidebar expanded by default at 1200px+ |
| FR43 | Epic 3 | Responsive layout 768px–1920px+ |
| FR44 | Epic 3 | Auto-collapse sidebar on investigation detail |

## Epic List

### Epic 1: Restore Data Pipeline — Telemetry Ingestion & Anomaly Detection
After deploying the demo, telemetry data flows from OTEL Collector into Beeper, EWMA detectors calibrate and fire on anomalies, and Investigation CRDs are created automatically. Detection stats are exposed via API for downstream UI consumption.
**FRs covered:** FR1-9
**ADs:** AD-1 (protobuf alignment), AD-2 (detection stats API), AD-8 (test baseline)
**NFRs:** NFR1, NFR5, NFR6, NFR11, NFR13

### Epic 2: Investigation Execution — Signal Gathering & LLM Root Cause
Investigations autonomously gather real Prometheus metrics and Loki logs, query the Knowledge Base for similar incidents, incorporate SLO context, and produce specific, evidence-backed root cause hypotheses with actionable recommendations.
**FRs covered:** FR10-21, FR30
**ADs:** AD-5 (verify KB query pattern)
**NFRs:** NFR2, NFR3, NFR10, NFR14, NFR15

### Epic 3: UI Layout Shell & Sidebar Navigation
Users navigate Beeper through a collapsible left sidebar organized into Observe/Learn/Manage groups, with responsive layout from 768px to 1920px+. Investigation detail auto-collapses sidebar for maximum evidence real estate.
**FRs covered:** FR40-44
**ADs:** AD-3 (layout shell), AD-6 (sidebar state), AD-7 (Tailwind pipeline)
**NFRs:** NFR17

### Epic 4: Investigation Display & Real-Time Streaming
Users view and filter investigation lists, watch investigations unfold step-by-step in real-time via SSE with inline evidence (metric values, log excerpts), and see related Knowledge Base entries on the investigation detail page. SSE auto-reconnects on network interruption.
**FRs covered:** FR22-27
**ADs:** AD-4 (SSE reconnection), AD-5 (Related KB panel query)
**NFRs:** NFR4, NFR7, NFR9

### Epic 5: Supporting Views — KB Browsing, Diagnostics & Health
Users can browse and search the Knowledge Base, view pipeline diagnostics (ingestion stats with EWMA warmup, detection counts), monitor source connections, and view LLM spending. Eric can diagnose "silent pipeline" issues from the UI.
**FRs covered:** FR28-29, FR31-35
**NFRs:** NFR12

### Epic 6: Demo Automation & End-to-End Reliability
Eric can run the full demo lifecycle — deploy, verify pipeline health, inject named faults, watch investigation complete with evidence, recover, repeat — reliably 3/3 consecutive times for investor presentations.
**FRs covered:** FR36-39
**NFRs:** NFR8

---

## Epic 1: Restore Data Pipeline — Telemetry Ingestion & Anomaly Detection

After deploying the demo, telemetry data flows from OTEL Collector into Beeper, EWMA detectors calibrate and fire on anomalies, and Investigation CRDs are created automatically. Detection stats are exposed via API for downstream UI consumption.

### Story 1.1: Establish Test Baseline

As a **developer**,
I want to run the full existing test suite and document which tests pass/fail,
So that I have diagnostic information to guide pipeline fixes.

**Acceptance Criteria:**

**Given** the existing codebase with 1,032 tests across 3 components
**When** `cargo test` is run for the operator, `poetry run pytest` for investigator, and `poetry run pytest` for UI
**Then** test results are documented with pass/fail counts per component
**And** failing tests are categorized by component boundary they reveal (ingestion, detection, lifecycle, etc.)

### Story 1.2: Fix OTEL Collector to Operator Ingestion

As a **demo operator (Eric)**,
I want telemetry data from the OTEL Astronomy Shop to flow into Beeper's ingestion endpoint,
So that the pipeline has real metric and log data to detect anomalies from.

**Acceptance Criteria:**

**Given** the OTEL demo is deployed with its Collector configured to export to Beeper
**When** the Collector sends Prometheus remote write (snappy+protobuf) to `:9090/api/v1/write`
**Then** the operator decodes the protobuf payload without errors and buffers the metric samples
**And** if protobuf schema mismatch is detected, operator proto definitions are updated to match Collector output (AD-1)

**Given** the OTEL Collector sends Loki push (JSON) to `:9090/loki/api/v1/push`
**When** log entries arrive at the ingestion endpoint
**Then** the operator parses JSON log payloads and buffers them without errors

**Given** data is flowing from both metric and log sources
**When** `GET /api/v1/ingestion/stats` is called on `:8080`
**Then** response shows `metrics_received > 0` AND `logs_received > 0` within 5 minutes of deploy
**And** per-source health reports (FR4) show bytes received, parse errors, and last received timestamp

### Story 1.3: Fix Anomaly Detection & Investigation Triggering

As a **demo operator (Eric)**,
I want EWMA detectors to fire on demo traffic anomalies and create Investigation CRDs automatically,
So that the pipeline progresses from data ingestion to autonomous investigation.

**Acceptance Criteria:**

**Given** metric data is flowing into the operator from Story 1.2
**When** EWMA detectors accumulate at least 10 samples per metric stream (NFR6: within 2-3 minutes)
**Then** detectors reach operational warmup and begin evaluating anomaly thresholds

**Given** `make demo-fault FAULT=payment-failure` is executed after EWMA warmup
**When** the payment service error rate diverges from the EWMA baseline
**Then** EWMA-based anomaly detection fires (FR5) and an Investigation CRD is created (FR7) within 5 minutes (NFR1)

**Given** log streams contain anomalous patterns from the fault injection
**When** the log pattern detector evaluates buffered logs
**Then** pattern-based anomaly detection identifies relevant log anomalies (FR6)

**Given** an investigation was already created for the same service within the cooldown window
**When** another anomaly is detected for that service
**Then** a duplicate investigation is NOT created (FR8)
**And** the suppressed detection is counted

### Story 1.4: Extend Ingestion Stats API with Detection Metrics

As a **demo operator (Eric)**,
I want to see detection pipeline status (anomalies detected, EWMA warmup progress) via the stats API,
So that I can diagnose whether the pipeline is warming up or broken before a demo.

**Acceptance Criteria:**

**Given** the existing `/api/v1/ingestion/stats` endpoint on `:8080`
**When** detection stats fields are added to the response
**Then** the response includes `anomalies_detected`, `anomalies_suppressed`, `active_metric_detectors`, `ewma_warmup_samples`, and `ewma_warmup_minimum` (AD-2)
**And** existing fields (`metrics_received`, `logs_received`, `buffer_utilization`) are unchanged in name, type, and structure

**Given** the EWMA detectors are actively processing metric streams
**When** the stats endpoint is queried
**Then** `ewma_warmup_samples` reflects the current warmup state and `anomalies_detected` increments when detections fire

**Given** the new fields are added to the Rust stats struct
**When** `cargo test` is run
**Then** serialization tests verify all field names are snake_case and all new fields are present with correct types

---

## Epic 2: Investigation Execution — Signal Gathering & LLM Root Cause

Investigations autonomously gather real Prometheus metrics and Loki logs, query the Knowledge Base for similar incidents, incorporate SLO context, and produce specific, evidence-backed root cause hypotheses with actionable recommendations.

### Story 2.1: Verify/Fix Investigation Lifecycle & Job Management

As a **developer**,
I want the operator to correctly manage investigation lifecycle — spawning Jobs, tracking failures, and cleaning up,
So that investigations progress reliably from detection to completion.

**Acceptance Criteria:**

**Given** an Investigation CRD is created with status `Pending`
**When** the operator's investigation controller reconciles it
**Then** the status transitions to `Running` and a Kubernetes Job is spawned for the investigator (FR10, FR11)

**Given** an investigator Job fails (non-zero exit code)
**When** the operator detects the Job failure
**Then** the investigation status transitions to `Failed` with failure details surfaced within 30 seconds (FR12, NFR10)
**And** no orphaned Jobs remain in the namespace

**Given** an investigator Job completes successfully
**When** the operator detects Job completion
**Then** the investigation status transitions to `Completed` and the completed Job is cleaned up (FR13)

**Given** the operator pod restarts
**When** it reconciles existing Investigation CRDs
**Then** it resumes processing without creating duplicate investigations or duplicate Jobs (NFR12 — verified at integration level)

### Story 2.2: Fix Investigator Signal Gathering (Prometheus & Loki)

As a **developer**,
I want the investigator to successfully query Prometheus and Loki for real signal data within the cluster,
So that investigation steps are backed by actual infrastructure metrics and logs, not empty results.

**Acceptance Criteria:**

**Given** an investigator Job is running inside the kind cluster
**When** it constructs a PromQL query for the anomalous service's metrics
**Then** it resolves the Prometheus endpoint via cluster DNS (NFR14) and receives non-empty metric results (FR14)

**Given** an investigator Job queries Loki for relevant logs
**When** it constructs a LogQL query for the anomalous service
**Then** it resolves the Loki endpoint via cluster DNS and receives relevant log entries (FR15)

**Given** signal queries return results
**When** the investigator evaluates data availability
**Then** it confirms sufficient data exists before proceeding to LLM analysis (FR16)
**And** if Prometheus or Loki returns empty results, the step reports the absence rather than failing silently

### Story 2.3: Fix Knowledge Base Integration in Investigations

As a **developer**,
I want the investigator to search Qdrant for similar past incidents and store outcomes for future reference,
So that investigations benefit from accumulated institutional knowledge.

**Acceptance Criteria:**

**Given** an investigator is executing a KB query step
**When** it searches the Qdrant `investigations` collection for the anomalous service
**Then** it returns relevant past incidents (or an empty result set) without errors (FR17)
**And** the KB query step results are stored in the investigation's step data (AD-5 verification)

**Given** an investigation completes with a root cause conclusion
**When** the investigator stores the outcome
**Then** a new Knowledge Base entry is created in Qdrant with the investigation context, service name, and resolution (FR30)

**Given** Qdrant is upgraded to v1.15.0 in the Helm chart
**When** KB operations execute
**Then** all read/write operations function correctly with the new Qdrant version

### Story 2.4: Fix LLM Root Cause Analysis & Recommendations

As a **demo operator (Eric)**,
I want investigations to produce specific, evidence-backed root cause hypotheses and actionable recommendations,
So that Diana sees a real AI reasoning about infrastructure problems, not generic guesses.

**Acceptance Criteria:**

**Given** the investigator has gathered Prometheus metrics, Loki logs, and KB results
**When** it sends context to the LLM for root cause analysis
**Then** the LLM prompt includes actual signal data (metric values, log excerpts) — not just service names (FR18)
**And** the response contains a specific root cause hypothesis referencing the observed evidence

**Given** the LLM generates a root cause hypothesis
**When** the investigator requests resolution recommendations
**Then** the response includes specific, actionable recommendations (e.g., "Scale payment service replicas from 2 to 4") rather than generic advice (e.g., "Check the service") (FR19)

**Given** the LiteLLM provider is configured for Anthropic Claude
**When** the investigator makes LLM calls
**Then** calls complete successfully within 10 minutes total investigation time at p95 (NFR3, NFR15)

**Given** the full investigation pipeline has executed
**When** all steps complete
**Then** non-LLM steps complete within 2 minutes of CRD creation (NFR2)

### Story 2.5: Verify/Fix ServiceLevel CRD Integration

As a **developer**,
I want the operator to read ServiceLevel CRDs and the investigator to incorporate SLO breach data,
So that investigations include customer impact context when SLOs are breached.

**Acceptance Criteria:**

**Given** ServiceLevel CRDs are deployed in the cluster defining SLO targets per service
**When** the operator's servicelevel controller reconciles them
**Then** SLO targets are read and available for investigation context (FR20)

**Given** an investigation is running for a service with a defined ServiceLevel CRD
**When** the investigator gathers context for LLM analysis
**Then** SLO breach data (if any) is included in the investigation context passed to the LLM (FR21)

**Given** no ServiceLevel CRD exists for the anomalous service
**When** the investigator gathers context
**Then** the investigation proceeds normally without SLO data — absence is handled gracefully, not as an error

---

## Epic 3: UI Layout Shell & Sidebar Navigation

Users navigate Beeper through a collapsible left sidebar organized into Observe/Learn/Manage groups, with responsive layout from 768px to 1920px+. Investigation detail auto-collapses sidebar for maximum evidence real estate.

### Story 3.1: Install Tailwind CSS Build Pipeline

As a **developer**,
I want the Tailwind CSS standalone binary integrated into the build pipeline,
So that new UI components can use Tailwind utility classes alongside the existing CSS.

**Acceptance Criteria:**

**Given** the UI project at `ui/`
**When** Tailwind CLI standalone binary is added to the project
**Then** `make tailwind-watch` runs `tailwindcss --watch` for development with output to `ui/beeper_ui/static/css/tailwind.css`
**And** `make tailwind-build` runs `tailwindcss --minify` for production builds

**Given** the Tailwind config file `ui/tailwind.config.js`
**When** the config is created
**Then** it includes the v0.2.0 design tokens (surface-base, surface-raised, surface-overlay, primary, status colors, text hierarchy) as theme extensions
**And** content paths are set to `['./beeper_ui/templates/**/*.html', './beeper_ui/static/js/**/*.js']` for tree-shaking
**And** breakpoints are configured: sm=768px, lg=1200px, xl=1920px

**Given** the Tailwind input file `ui/beeper_ui/static/css/input.css`
**When** it is created with `@tailwind base; @tailwind components; @tailwind utilities;`
**Then** the generated `tailwind.css` is added to `.gitignore` (build output, not source)

**Given** the UI Dockerfile
**When** a production image is built
**Then** Tailwind CLI runs minification as a build stage and the output CSS is included in the final image

### Story 3.2: Implement Layout Shell & Base Template Migration

As a **user (all personas)**,
I want the UI to have a responsive layout with sidebar and top bar structure,
So that all pages render within a consistent, professional layout shell.

**Acceptance Criteria:**

**Given** the existing `base.html` template
**When** it is rewritten to include the layout shell
**Then** it imports the layout macro from `templates/components/layout.html` providing sidebar + top bar + content area structure
**And** the content area uses `{% block content %}` for page-specific content

**Given** the layout shell uses Tailwind classes
**When** rendered at different viewports
**Then** layout adapts responsively: sidebar 256px expanded / 64px collapsed, top bar 48px height, content area with 24px padding (FR43)
**And** no horizontal scrolling occurs between 768px and 1920px+

**Given** all 29 page templates extend `base.html`
**When** the modified `base.html` is deployed
**Then** every page renders within the new layout shell (AD-3 atomic migration)
**And** `grep -r "extends" ui/beeper_ui/templates/ --include="*.html"` confirms all templates inherit from `base.html`

**Given** the `templates/components/layout.html` macro file is created
**When** it defines the layout structure
**Then** it includes top bar with hamburger icon slot, logo, and `{% block breadcrumb %}` slot
**And** content area wraps `{% block content %}` with proper margin/padding

### Story 3.3: Build Sidebar Navigation Component

As a **user (all personas)**,
I want a left sidebar organized into Observe, Learn, and Manage groups,
So that I can navigate all Beeper views through an intuitive, grouped menu.

**Acceptance Criteria:**

**Given** the `templates/components/sidebar.html` macro
**When** `sidebar_group(label, icon, items, expanded, active_item)` is defined
**Then** it renders a collapsible group with label, icon, and navigation items using Tailwind classes

**Given** the sidebar is rendered in the layout shell
**When** navigation groups are defined
**Then** Observe group contains: Investigations, Sources, Ingestion Stats
**And** Learn group contains: Knowledge Base, Metrics
**And** Manage group contains: Spending (FR40)

**Given** the sidebar is rendered on a viewport >= 1200px
**When** the page loads
**Then** the sidebar is expanded by default showing group labels and item names (FR42)

**Given** the sidebar is rendered on a viewport < 1200px
**When** the page loads
**Then** the sidebar is collapsed to a 64px icon rail with tooltip labels on hover

**Given** the user clicks the hamburger icon
**When** the sidebar is collapsed
**Then** it expands with a 200ms CSS transition (FR41)
**And** on < 1200px viewports, the sidebar overlays content (float) rather than pushing it

### Story 3.4: Implement Sidebar State Management & Route-Driven Collapse

As a **user viewing an investigation**,
I want the sidebar to auto-collapse when I open investigation detail and re-expand when I navigate back,
So that evidence gets maximum screen real estate during review without manual sidebar management.

**Acceptance Criteria:**

**Given** a page template that is NOT investigation detail
**When** it sets `{% block sidebar_state %}auto{% endblock %}`
**Then** the sidebar follows viewport-responsive behavior (expanded >= 1200px, collapsed < 1200px) (AD-6)

**Given** the investigation detail template
**When** it sets `{% block sidebar_state %}collapsed{% endblock %}`
**Then** the sidebar is collapsed regardless of viewport width (FR44)
**And** the hamburger icon remains visible for manual re-expand

**Given** the user manually toggles the sidebar via hamburger or `[` key
**When** the toggle is activated
**Then** the override is stored in `sessionStorage` with key `sidebar-manual-override`
**And** the override is cleared on next full page navigation

**Given** sidebar group expand/collapse state (Observe open, Learn closed, etc.)
**When** the user toggles a group
**Then** the state is stored in `sessionStorage` by group label (e.g., `sidebar-group-observe`)
**And** defaults to all groups expanded

**Given** the sidebar transitions between states
**When** collapse or expand occurs
**Then** the CSS transition renders at 60fps without layout reflow or jank (NFR17)
**And** `transition: width 200ms ease-in-out` on sidebar, `transition: margin-left 200ms ease-in-out` on content area
**And** all animations respect `prefers-reduced-motion` media query

---

## Epic 4: Investigation Display & Real-Time Streaming

Users view and filter investigation lists, watch investigations unfold step-by-step in real-time via SSE with inline evidence (metric values, log excerpts), and see related Knowledge Base entries on the investigation detail page. SSE auto-reconnects on network interruption.

### Story 4.1: Investigation List View with Status Filtering

As an **SRE (Sam)**,
I want to see a list of investigations filterable by status group (active, resolved, failed),
So that I can quickly scan what needs attention and what's been handled.

**Acceptance Criteria:**

**Given** the investigation list page at Observe > Investigations
**When** the page loads
**Then** investigations are displayed as cards using the `investigation_card(inv)` macro from `templates/components/cards.html`
**And** each card shows service name, severity, status, and timestamp

**Given** the `templates/components/status.html` macro
**When** `status_badge(status)` is rendered
**Then** it displays the investigation status with appropriate color (green=active, amber=warning, red=failed, gray=completed)

**Given** investigations exist with different statuses
**When** the user filters by status group
**Then** active (Pending/Running) investigations are shown by default
**And** the user can switch to resolved (Completed) or failed (Failed) groups (FR22)

**Given** active investigations exist
**When** they are rendered in the list
**Then** each card has a 3px left border colored by status (FR22)
**And** completed investigations have reduced opacity with muted border

**Given** no investigations exist
**When** the list page loads
**Then** an explanatory empty state is shown using `empty_state(title, description, icon)` from `templates/components/empty.html`
**And** the message explains investigations will appear when anomalies are detected

### Story 4.2: Investigation Detail with Summary Header & Step Timeline

As an **SRE (Sam)**,
I want to see investigation detail with an immediate summary header and step-by-step evidence timeline,
So that I can assess severity in 2 seconds and review evidence at my own pace.

**Acceptance Criteria:**

**Given** the user clicks into an investigation from the list
**When** the detail page loads
**Then** the `summary_header(inv)` macro renders immediately with service name, severity, signal count, and status — no SSE dependency (FR23)
**And** the top bar shows breadcrumb: "Investigations > INV-{id}"

**Given** the investigation has completed steps
**When** the step timeline renders below the summary header
**Then** each step is rendered using `investigation_step(step, is_first_evidence, order)` from `templates/components/investigation.html`
**And** each step has a 3px left border colored by step type (metric=indigo, log=green, KB=amber, correlation=light indigo, summary=gray)

**Given** a step contains evidence (metric values, log excerpts)
**When** it renders
**Then** evidence values are displayed in monospace font (`ui-monospace`) (FR25)
**And** service names are styled as labels on `surface-raised` background

**Given** the investigation is completed
**When** the conclusion block renders
**Then** `conclusion_block(inv)` displays root cause statement, affected services, and correlated signal count
**And** the block is visually distinct from regular steps

**Given** the investigation detail page is loading
**When** some steps are already complete and others are pending
**Then** completed steps render immediately — the page is never blank (NFR7)

### Story 4.3: SSE Real-Time Streaming & Auto-Reconnection

As a **demo viewer (Diana)**,
I want to watch investigation steps appear in real-time as Beeper investigates,
So that I see the AI doing actual work with live evidence, not a static report.

**Acceptance Criteria:**

**Given** an investigation is in `Running` status
**When** the detail page is open
**Then** an `EventSource` connection is opened from `static/js/sse.js` to the SSE endpoint (FR24)
**And** new steps append to the timeline as `investigation_step` events arrive
**And** the investigation list view receives `investigation_created` and `investigation_status` events

**Given** the SSE connection is active
**When** a new step arrives
**Then** it is rendered at the correct position based on its `order` field
**And** UI updates within 2 seconds of event receipt (NFR4)

**Given** the SSE connection drops (network interruption)
**When** the browser's `EventSource` auto-retries
**Then** on reconnect, the client fetches `GET /api/v1/investigations/{id}` for full current state (AD-4 REST backfill)
**And** missed steps are diffed against already-rendered steps and inserted at correct positions by `order` field

**Given** the SSE connection fails 5 consecutive retries
**When** the retry limit is reached
**Then** a static message "Live updates unavailable — refresh to sync" is displayed below the last step
**And** the investigation detail remains viewable with all previously rendered steps

**Given** SSE events arrive on the investigation list page
**When** a new investigation is created
**Then** a new card appears with a highlight animation that fades over 5 seconds

**Given** SSE is implemented in `static/js/sse.js`
**When** the module is loaded
**Then** it uses the native `EventSource` API — NOT HTMX attributes (AD-4)
**And** the SSE connection auto-reconnects within 5 seconds of interruption (NFR9)

### Story 4.4: Related Knowledge Base Panel on Investigation Detail

As an **SRE (Sam)**,
I want to see related KB entries from past incidents directly on the investigation detail page,
So that I can check for known patterns without navigating away from the evidence.

**Acceptance Criteria:**

**Given** the investigation detail page on a viewport > 1200px
**When** the page renders
**Then** a fixed bottom bar shows "N Related KB Entries" using the `kb_panel(entries, expanded)` macro from `templates/components/kb.html`
**And** clicking the bar expands the panel upward to show KB entry summaries (FR26)

**Given** the investigation detail page on a viewport <= 1200px
**When** the page renders
**Then** the Related KB panel renders inline below the step timeline (not as a fixed bottom bar)

**Given** the investigation's KBQueryStep produced results
**When** the panel queries for related entries
**Then** it reads KBQueryStep results from the investigation record in the `investigations` Qdrant collection (AD-5)
**And** displays matched KB entry titles with relevance context

**Given** the KBQueryStep found 0 related entries
**When** the panel renders
**Then** it shows "0 Related KB Entries" — not hidden (Sam learns this investigation has no historical precedent)

**Given** the user clicks a KB entry in the panel
**When** the entry is selected
**Then** the entry detail expands within the panel showing past incident context, resolution, and service name

---

## Epic 5: Supporting Views — KB Browsing, Diagnostics & Health

Users can browse and search the Knowledge Base, view pipeline diagnostics (ingestion stats with EWMA warmup, detection counts), monitor source connections, and view LLM spending. Eric can diagnose "silent pipeline" issues from the UI.

### Story 5.1: Knowledge Base Browsing, Search & Detail Views

As an **SRE (Sam/Jordan)**,
I want to browse and search the Knowledge Base for past incidents and view entry details,
So that I can learn from Beeper's accumulated institutional knowledge and find relevant patterns.

**Acceptance Criteria:**

**Given** the Knowledge Base page at Learn > Knowledge Base
**When** the page loads
**Then** KB entries are listed with service name, title, and creation date (FR28)

**Given** the KB list page
**When** the user enters a search term (keyword or service name)
**Then** results are filtered to matching entries (FR29)

**Given** the user clicks a KB entry
**When** the detail page loads
**Then** the entry shows full incident context including past root cause, resolution, affected services, and source investigation reference (FR31)

**Given** the Knowledge Base has no entries
**When** the page loads
**Then** an explanatory empty state is shown — not a blank page

### Story 5.2: Pipeline Diagnostic Dashboard (Ingestion Stats & Detection Stats)

As a **demo operator (Eric)**,
I want to see pipeline health at a glance — data flow, detection status, and EWMA warmup progress,
So that I can diagnose "is it broken or warming up?" within 5 seconds before a demo.

**Acceptance Criteria:**

**Given** the Ingestion Stats page at Observe > Ingestion Stats
**When** the page loads
**Then** it displays `metrics_received` and `logs_received` as metric tiles using `metric_tile(label, value, status, trend)` from `templates/components/diagnostic.html` (FR32)

**Given** the detection stats API (FR9/AD-2) is returning data
**When** the diagnostic dashboard renders
**Then** it displays `anomalies_detected`, `anomalies_suppressed`, and `active_metric_detectors` as additional metric tiles (FR33)

**Given** EWMA detectors are warming up (`ewma_warmup_samples < ewma_warmup_minimum`)
**When** the warmup section renders
**Then** `ewma_progress(percentage, status)` macro shows a progress bar with percentage and an amber "Warming Up" status chip
**And** the percentage is calculated as `ewma_warmup_samples / ewma_warmup_minimum * 100`

**Given** EWMA detectors are fully warmed up (`ewma_warmup_samples >= ewma_warmup_minimum`)
**When** the warmup section renders
**Then** the chip shows green "Active" status — visually distinct from the warming state

**Given** `metrics_received = 0` and `logs_received = 0`
**When** the dashboard renders
**Then** a red "No Data" status chip is displayed — visually distinct from both "Warming Up" and "Active"

**Given** the diagnostic dashboard is open
**When** pipeline state changes
**Then** the page auto-refreshes to reflect updated stats

### Story 5.3: Source Connection Status & LLM Spending Views

As a **demo operator (Eric)**,
I want to see data source connection status and LLM spending metrics,
So that I can verify Prometheus and Loki are connected and monitor LLM costs.

**Acceptance Criteria:**

**Given** the Sources page at Observe > Sources
**When** the page loads
**Then** Prometheus and Loki sources show connection status (connected/disconnected) with visual indicators (FR34)

**Given** a source is connected
**When** its status renders
**Then** it shows a green "Connected" indicator with last-seen timestamp

**Given** a source is disconnected
**When** its status renders
**Then** it shows a red "Disconnected" indicator

**Given** the Spending page at Manage > Spending
**When** the page loads
**Then** LLM provider configuration and spending metrics are displayed (FR35)

**Given** the operator pod restarts
**When** it comes back online
**Then** it resumes processing existing Investigation CRDs without duplicates (NFR12 — verified via source and investigation state consistency)

---

## Epic 6: Demo Automation & End-to-End Reliability

Eric can run the full demo lifecycle — deploy, verify pipeline health, inject named faults, watch investigation complete with evidence, recover, repeat — reliably 3/3 consecutive times for investor presentations.

### Story 6.1: Fix Demo Deployment & Port-Forward Automation

As a **demo operator (Eric)**,
I want to deploy the full demo environment and set up port-forwards via single Makefile targets,
So that demo setup is a known quantity — not a debugging session.

**Acceptance Criteria:**

**Given** a kind cluster is running with the Beeper operator deployed
**When** `make demo-deploy` is executed
**Then** the OTEL Astronomy Shop deploys with its 16+ microservices, the Collector is configured to forward to Beeper's ingestion endpoint, and ServiceLevel CRDs are applied (FR36)

**Given** the demo environment is deployed
**When** `make demo-ui` is executed
**Then** port-forwards are established for the Beeper UI (localhost:8080), operator API, and OTEL demo frontend (FR39)
**And** the user can open the Beeper UI in a browser

**Given** the Helm chart's Qdrant version
**When** the chart is deployed
**Then** Qdrant runs at v1.15.0 (matching local development) to prevent version discrepancy issues

**Given** the kind cluster configuration
**When** `kind-config.yaml` is verified
**Then** port mappings are correct for all demo services

### Story 6.2: Fix Fault Injection & Recovery Automation

As a **demo operator (Eric)**,
I want to inject named fault scenarios and recover from them via Makefile targets,
So that I can reliably trigger investigations during demos and reset for repeat runs.

**Acceptance Criteria:**

**Given** the demo environment is deployed and EWMA warmup is complete
**When** `make demo-fault FAULT=payment-failure` is executed
**Then** the payment service fault is injected and anomalous behavior begins within the OTEL demo (FR37)

**Given** a fault is active and an investigation has completed
**When** `make demo-recover` is executed
**Then** the fault condition is removed and the OTEL demo returns to normal operation (FR38)

**Given** multiple fault types are defined
**When** different fault names are used (e.g., `payment-failure`, `cart-failure`, `high-cpu`)
**Then** each produces distinct anomalous behavior that triggers a different investigation

### Story 6.3: End-to-End Demo Validation — 3/3 Repeatability

As a **demo operator (Eric)**,
I want to run the complete demo script 3 consecutive times with reliable results,
So that I join investor calls with confidence that the demo will work.

**Acceptance Criteria:**

**Given** the full pipeline is working (Epics 1-5 complete)
**When** the following sequence is executed 3 consecutive times without cluster restart:
1. `make demo-deploy` (if not already deployed)
2. Verify `GET /api/v1/ingestion/stats` shows data flowing
3. Wait for EWMA warmup (stats show `ewma_warmup_samples >= ewma_warmup_minimum`)
4. `make demo-fault FAULT=payment-failure`
5. Wait for investigation to appear and complete
6. Verify investigation has specific root cause referencing "payment service" and "error rate"
7. Verify evidence includes real Prometheus metric values and Loki log excerpts
8. `make demo-recover`
**Then** all 3 runs complete successfully with evidence-backed findings (NFR8)
**And** zero investigations produce "insufficient data" results when faults are active

**Given** the demo is validated
**When** the demo README is updated
**Then** `demo/README.md` contains the complete demo script with timing expectations (wait 2-3 min for EWMA warmup, investigation completes within 5-10 min)
