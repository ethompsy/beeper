---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
status: 'complete'
completedAt: '2026-03-13'
inputDocuments:
  - prd.md
  - architecture.md
  - ux-design-specification.md
previousVersion:
  completedAt: '2026-02-03'
  context: 'v0.1.0'
  epics: 6
  stories: 39
---

# Beeper - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for Beeper v0.2.0, decomposing the requirements from the PRD, Architecture, and UX Design Specification into implementable stories organized by the 4-wave delivery model.

**Context:** Brownfield project. v0.1.0 is fully implemented with 1,032 passing tests (162 Rust + 375 Python investigator + 495 Python UI). v0.2.0 adds 16 net-new FRs and restructures existing FRs into the wave delivery model.

## Requirements Inventory

### Functional Requirements

**SLO & Customer Impact — Wave 1 (FR1-7):**
- FR1: Admins can define SLIs and SLO targets per service via ServiceLevel CRD
- FR2: System can calculate SLO burn rates in real-time from ingested metrics
- FR3: System can trigger investigations when SLO burn rate exceeds configured thresholds
- FR4: System can score anomalies by customer impact using SLO data rather than static severity labels
- FR5: Admins can define error budget policies that trigger notifications or deployment freezes
- FR6: Users can view SLO compliance, burn rate trends, and error budgets on a dashboard
- FR7: System can prioritize investigations by SLO impact severity

**Notification & Integration — Wave 1 (FR8-15):**
- FR8: Users can configure outbound notification channels via NotificationChannel CRD (Slack, PagerDuty, email, webhook)
- FR9: Users can define notification routing rules based on severity, service, SLO state, and time of day
- FR10: System can send rich Slack messages with threads, @mentions, and action buttons
- FR11: System can create, acknowledge, and auto-resolve PagerDuty incidents bidirectionally
- FR12: System can send email alert digests and investigation summaries
- FR13: System can trigger webhooks to external systems (CD pipelines, Jira, status pages)
- FR14: Users can configure quiet hours and escalation tiers that respect on-call schedules
- FR15: System can justify every notification with evidence — false pages are tracked as bugs

**Trust & Autonomy — Wave 2 (FR16-22):**
- FR16: Admins can configure trust levels (1-5) per service, controlling Beeper's autonomy from advisory to fully autonomous
- FR17: System can gate actions by confidence threshold — only act when evidence meets the configured trust level's requirements
- FR18: System can adapt alert thresholds based on investigation outcome feedback from SREs
- FR19: Users can provide one-click investigation feedback (accurate / inaccurate / not-an-issue)
- FR20: Admins can view a noise report showing signal-to-noise ratio and false page trends
- FR21: System can weight escalation urgency by confirmed customer impact rather than theoretical severity
- FR22: Admins can configure confidence gate thresholds per trust level

**Auto-Remediation — Wave 2 (FR23-31):**
- FR23: Admins can register code repositories via Repository CRD with branch policies and coding standards
- FR24: System can execute human-language runbooks without requiring DSL translation
- FR25: System can generate auto-PRs with full evidence trails (log correlation, root cause analysis, production conditions)
- FR26: System can always produce an advisory test plan describing how to verify a hypothesis
- FR27: System can design sandbox-specific tests and execute them when a sandbox environment is available
- FR28: System can verify that a fix resolves the issue by monitoring post-fix metrics
- FR29: System can gate remediation actions to the configured trust level and confidence tier
- FR30: System can link PRs to investigations with full audit trail (anomaly → investigation → fix → verification)
- FR31: System can accumulate proven fixes in the KB for future reference

**Collaborative Investigation — Wave 3 (FR32-37):**
- FR32: Users can interact with Beeper in real-time during active investigations
- FR33: System can present evidence with references to specific metrics, logs, and prior KB entries
- FR34: Users can annotate, redirect, and comment on active investigations
- FR35: Users can approve or reject Beeper-proposed fixes within their permission level
- FR36: System can generate shift handoff summaries with active investigations, resolved incidents, and items to watch
- FR37: System can surface relevant past KB entries during live investigations

**Knowledge Base Enhancement — Wave 3 (FR38-42):**
- FR38: System can create KB entries automatically from resolved investigations
- FR39: System can link KB entries bi-directionally to investigations and related entries
- FR40: System can provide per-service knowledge views through service catalog integration
- FR41: System can weight KB entries by validation status (human-confirmed, AI-generated, corrected)
- FR42: Users can review, edit, and correct Beeper's KB entries as a feedback mechanism

**Signal & Observability — Wave 3 (FR43-46):**
- FR43: System can display a unified investigation timeline correlating logs, metrics, deploys, and K8s events
- FR44: System can correlate anomalies with recent deployments ("anomaly started 4 min after deploy #847")
- FR45: System can discover and display service dependency topology
- FR46: System can ingest and correlate change events (config changes, scaling, DNS, certs)

**Developer Experience — Wave 4 (FR47-50):**
- FR47: Users can navigate the UI via keyboard shortcuts and a command palette (Cmd+K)
- FR48: System can track investigations through workflow states (detected → investigating → resolved → verified)
- FR49: Users can track remediation progress from detection through fix verification
- FR50: Users can view per-service health feeds with recent investigations, SLO status, and trends

**Analytics & Reporting — Wave 4 (FR51-53):**
- FR51: System can calculate a reliability score per service (composite of SLO compliance, incident frequency, MTTR)
- FR52: Users can view MTTR trends, customer impact trends, and trust progression dashboards
- FR53: Diana can view investor-ready reports derived from Beeper's operational data

**Demo Application — Cross-cutting (FR54-57):**
- FR54: System can deploy a purpose-built chaotic microservices application in K8s alongside Beeper
- FR55: Admins can trigger configurable fault injections (memory leak, bad deploy, cascading failure, scale-dependent issues)
- FR56: System can demonstrate the full lifecycle: healthy → fault → detect → investigate → fix → prove → recover
- FR57: System can run scripted, repeatable demo scenarios for investor presentations

**Platform & Security — Foundation (FR58-63):**
- FR58: System can enforce 2-tier permissions (admin/user) across all APIs and UI routes
- FR59: System can store integration credentials as K8s Secrets with encryption at rest
- FR60: System can scrub sensitive information (PII, credentials) from data before sending to LLM providers
- FR61: System can gracefully degrade if LLM provider is unavailable (queue investigations, escalate to humans)
- FR62: System can rollback any autonomous action if post-action metrics show degradation
- FR63: System can operate without becoming a single point of failure — existing alerting continues if Beeper is down

### NonFunctional Requirements

**Performance (NFR1-7):**
- NFR1: Anomaly-to-investigation latency < 30 seconds from detection to investigation start
- NFR2: UI response time < 2 seconds for all user interactions
- NFR3: LLM screening round-trip < 10 seconds
- NFR4: LLM deep investigation round-trip < 30 seconds per reasoning step
- NFR5: Real-time collaboration updates < 500ms delivery (WebSocket)
- NFR6: SLO burn rate calculation < 5 second refresh cycle
- NFR7: Demo full lifecycle < 5 minutes fault-to-resolution

**Security (NFR8-13):**
- NFR8: Cluster RBAC — least-privilege per operation, no cluster-admin
- NFR9: Repository credentials — scoped per-repo tokens, never org-wide
- NFR10: Secret storage — K8s Secrets with encryption at rest
- NFR11: PII/credential scrubbing — zero sensitive data sent to LLM providers
- NFR12: Trust level access control — admin-only for trust level and confidence gate configuration
- NFR13: Sandbox isolation — network-isolated namespace, provably no production data leakage

**Reliability (NFR14-18):**
- NFR14: Non-SPOF operation — existing alerting fully functional if Beeper is down
- NFR15: LLM provider degradation — queue investigations + escalate within 60 seconds
- NFR16: Autonomous action rollback — any auto-applied fix reversible within 60 seconds
- NFR17: Data integrity — zero investigation data loss during component restart or upgrade
- NFR18: Demo reliability — 10 consecutive end-to-end demo runs without failure

**Scalability (NFR19-22):**
- NFR19: Concurrent investigations — 50+ active without performance degradation
- NFR20: KB capacity — 10,000+ entries with < 2 second semantic search
- NFR21: ServiceLevel CRDs — 100+ active CRDs per cluster
- NFR22: Notification throughput — 1,000+ events/hour processed without drops

### Additional Requirements

**From Architecture:**
- Brownfield project — all v0.1.0 tests (1,032) must continue passing throughout v0.2.0 development
- No starter template — extending existing codebase, not scaffolding new
- Permission model (`@require_role` decorator + middleware) must be implemented before any new API endpoint
- 3 new CRD schemas (ServiceLevel, NotificationChannel, Repository) must be defined in Rust operator
- 2 new Qdrant collections (slo_snapshots, notification_outbox) to initialize
- Existing Qdrant collections (investigations, knowledge, service_trust_levels) require schema extensions
- Flask-SocketIO integration requires two-channel pattern: SocketIO for collaboration, SSE for everything else
- Durable notification outbox pattern using Qdrant payload collection (not in-process async)
- Auto-remediation extends existing 6-step investigation pipeline with conditional remediation steps
- Tailwind CSS standalone CLI binary — no Node.js in build chain
- PII scrubber must be applied before every LLM call
- Sandbox namespace with NetworkPolicy isolation for fix testing
- Demo application in own `demo/` monorepo directory with pytest harness
- Architecture spikes must complete before the features they inform (Flask-SocketIO+gunicorn, Qdrant payload perf, Tailwind+Jinja2, Git provider auth, sandbox NetworkPolicy)
- Implementation sequence: permissions → CRDs → SLO → notifications → trust → WebSocket → remediation → auto-PR → demo → Tailwind (incremental)

**From UX Design Specification:**
- Desktop-first responsive strategy: laptop (1024-1440px) primary, desktop (1440px+) secondary, no mobile
- WCAG 2.1 AA accessibility compliance — axe-core CI gate on every PR
- Dark-first design system with indigo primary (#6366f1), 5-level surface hierarchy
- Keyboard-first design: every action has a keyboard shortcut, command palette (Cmd+K)
- 4-tier component strategy aligned with waves: Tier 1 (investigation core), Tier 2 (navigation), Tier 3 (data display), Tier 4 (config/handoff)
- Investigation as narrative — streaming evidence timeline with progressive detail
- Optimistic UI scoped to approve action only; all other HTMX interactions are pessimistic
- Sidebar navigation: Incident Mode + Learning Mode groups, collapsed (64px) / expanded (240px)
- `prefers-reduced-motion` support for all streaming animations
- Screen reader support with ARIA roles (feed, meter, combobox, live regions)
- Semantic HTML5 elements throughout (nav, main, article, section, time)
- Component file organization under `ui/beeper_ui/templates/components/` with subdirectories

### FR Coverage Map

| FR | Epic | Description |
|----|------|------------|
| FR1 | Epic 1 | Define SLIs/SLO targets via ServiceLevel CRD |
| FR2 | Epic 1 | Calculate SLO burn rates in real-time |
| FR3 | Epic 1 | Trigger investigations on SLO burn rate breach |
| FR4 | Epic 1 | Score anomalies by customer impact using SLO data |
| FR5 | Epic 1 | Define error budget policies |
| FR6 | Epic 1 | SLO compliance dashboard |
| FR7 | Epic 1 | Prioritize investigations by SLO impact |
| FR8 | Epic 2 | Configure notification channels via CRD |
| FR9 | Epic 2 | Define notification routing rules |
| FR10 | Epic 2 | Rich Slack messages |
| FR11 | Epic 2 | PagerDuty bidirectional incidents |
| FR12 | Epic 2 | Email alert digests |
| FR13 | Epic 2 | Webhook triggers |
| FR14 | Epic 2 | Quiet hours and escalation tiers |
| FR15 | Epic 2 | Evidence-justified notifications, false page tracking |
| FR16 | Epic 3 | Configure trust levels (1-5) per service |
| FR17 | Epic 3 | Confidence gate actions |
| FR18 | Epic 3 | Adaptive alert thresholds from feedback |
| FR19 | Epic 3 | One-click investigation feedback |
| FR20 | Epic 3 | Noise report |
| FR21 | Epic 3 | Impact-weighted escalation urgency |
| FR22 | Epic 3 | Confidence gate threshold config |
| FR23 | Epic 4 | Register repositories via Repository CRD |
| FR24 | Epic 4 | Execute human-language runbooks |
| FR25 | Epic 4 | Auto-PRs with evidence trails |
| FR26 | Epic 4 | Advisory test plans |
| FR27 | Epic 4 | Sandbox test execution |
| FR28 | Epic 4 | Post-fix metric verification |
| FR29 | Epic 4 | Trust-gated remediation actions |
| FR30 | Epic 4 | PR-to-investigation audit trail |
| FR31 | Epic 4 | Accumulate proven fixes in KB |
| FR32 | Epic 5 | Real-time investigation interaction |
| FR33 | Epic 5 | Evidence with references |
| FR34 | Epic 5 | Annotate, redirect, comment on investigations |
| FR35 | Epic 5 | Approve/reject fixes within permission level |
| FR36 | Epic 5 | Shift handoff summaries |
| FR37 | Epic 5 | Surface KB entries during live investigations |
| FR38 | Epic 6 | Auto-create KB entries from resolved investigations |
| FR39 | Epic 6 | Bi-directional KB-investigation links |
| FR40 | Epic 6 | Per-service knowledge views |
| FR41 | Epic 6 | KB entry validation weighting |
| FR42 | Epic 6 | Review, edit, correct KB entries |
| FR43 | Epic 6 | Unified investigation timeline |
| FR44 | Epic 6 | Deploy correlation |
| FR45 | Epic 6 | Service dependency topology |
| FR46 | Epic 6 | Change event ingestion and correlation |
| FR47 | Epic 7 | Command palette (Cmd+K) |
| FR48 | Epic 7 | Investigation workflow states |
| FR49 | Epic 7 | Remediation progress tracking |
| FR50 | Epic 7 | Per-service health feeds |
| FR51 | Epic 7 | Reliability score per service |
| FR52 | Epic 7 | MTTR/impact/trust trend dashboards |
| FR53 | Epic 7 | Investor-ready reports |
| FR54 | Epic 8 | Deploy chaotic demo application |
| FR55 | Epic 8 | Configurable fault injection |
| FR56 | Epic 8 | Full lifecycle demonstration |
| FR57 | Epic 8 | Scripted repeatable demo scenarios |
| FR58 | Epic 1 | 2-tier permissions (admin/user) |
| FR59 | Epic 1 | K8s Secrets for integration credentials |
| FR60 | Epic 1 | PII scrubbing before LLM |
| FR61 | Epic 1 | Graceful LLM degradation |
| FR62 | Epic 4 | Autonomous action rollback |
| FR63 | Epic 1 | Non-SPOF operation |

**Coverage: 63/63 FRs mapped. Zero gaps.**

## Epic List

### Epic 1: SLO Platform & Permissions Foundation (Wave 1)
Admins can define SLOs per service, see customer impact scoring and burn rates on a dashboard, all protected by role-based permissions. The platform is resilient — Beeper never becomes a single point of failure.
**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR58, FR59, FR60, FR61, FR63

### Epic 2: Intelligent Notification Engine (Wave 1)
Users receive justified notifications through Slack, PagerDuty, email, and webhooks when things matter — with routing rules, quiet hours, and false page tracking. Every notification carries evidence.
**FRs covered:** FR8, FR9, FR10, FR11, FR12, FR13, FR14, FR15

### Epic 3: Graduated Trust & Autonomy (Wave 2)
Admins can control how autonomous Beeper is per service (TL1-5), configure confidence gates, and track accuracy over time. SREs provide investigation feedback that tunes Beeper's behavior. Signal-to-noise improves measurably.
**FRs covered:** FR16, FR17, FR18, FR19, FR20, FR21, FR22

### Epic 4: Autonomous Remediation Pipeline (Wave 2)
Beeper can propose fixes, test them in a sandbox, verify resolution, and create auto-PRs with full evidence trails. Actions are trust-gated and reversible. Proven fixes compound in the KB.
**FRs covered:** FR23, FR24, FR25, FR26, FR27, FR28, FR29, FR30, FR31, FR62

### Epic 5: Real-Time Investigation Collaboration (Wave 3)
Teams can interact with Beeper during live investigations — annotating, redirecting, approving fixes in real-time. Shift handoffs happen in 30 seconds instead of 30 minutes.
**FRs covered:** FR32, FR33, FR34, FR35, FR36, FR37

### Epic 6: Knowledge & Signal Intelligence (Wave 3)
The KB compounds automatically from resolved investigations with bi-directional links. Beeper correlates anomalies with deploys, config changes, and service topology — building institutional knowledge that gets smarter over time.
**FRs covered:** FR38, FR39, FR40, FR41, FR42, FR43, FR44, FR45, FR46

### Epic 7: Developer Experience & Analytics (Wave 4)
Power users navigate with keyboard shortcuts and a command palette. Reliability scores, MTTR trends, and trust progression dashboards give leadership visibility. Diana gets investor-ready reports.
**FRs covered:** FR47, FR48, FR49, FR50, FR51, FR52, FR53

### Epic 8: Investor Demo Platform (Cross-cutting)
Diana can run a scripted, repeatable demo that showcases the full detect → investigate → fix → prove lifecycle on a purpose-built chaotic application. 10 consecutive runs without failure.
**FRs covered:** FR54, FR55, FR56, FR57

## Epic 1: SLO Platform & Permissions Foundation

**Goal:** Admins can define SLOs per service, see customer impact scoring and burn rates on a dashboard, all protected by role-based permissions. The platform is resilient — Beeper never becomes a single point of failure.

**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR58, FR59, FR60, FR61, FR63
**NFRs addressed:** NFR1, NFR6, NFR8, NFR10, NFR11, NFR14, NFR15, NFR21

### Story 1.1: Permission Model Enforcement

As an **admin**,
I want role-based access control enforced across all UI routes and APIs,
So that only authorized users can configure trust levels, SLOs, and other safety-critical settings.

**Acceptance Criteria:**

**Given** a Flask route decorated with `@require_role("admin")`
**When** a user with role "user" attempts to access it
**Then** the request is rejected with HTTP 403 and an RFC 7807 error response
**And** the rejection is logged with the user context

**Given** the UI application starts up
**When** the permission middleware initializes
**Then** user role is determined from K8s ServiceAccount token (production), X-Beeper-Role header (development), or defaults to "user"
**And** the role is set on Flask `g.user_role` for the request lifecycle

**Given** all existing UI routes (investigations, knowledge, sources, metrics, spending)
**When** the permission model is applied
**Then** all existing routes remain accessible to role "user" (no regression)
**And** all existing tests (495 UI tests) continue passing

### Story 1.2: Secrets Management & PII Scrubbing

As a **platform operator**,
I want integration credentials stored securely and sensitive data scrubbed before LLM calls,
So that Beeper never leaks PII or credentials to external providers.

**Acceptance Criteria:**

**Given** a new integration (Slack, PagerDuty, Git) requires credentials
**When** the credential is configured
**Then** it is stored as a K8s Secret with encryption at rest
**And** never stored in Qdrant or application config

**Given** investigation context containing email addresses, IP addresses, tokens, or passwords
**When** the investigator prepares context for an LLM call
**Then** the PII scrubber replaces sensitive data with tagged placeholders (e.g., `[SCRUBBED:email]`)
**And** an audit log of scrubbed content is stored locally (never sent to LLM)
**And** the scrubber runs before every LLM call regardless of tier

**Given** a configurable scrub rule set
**When** a new pattern is added
**Then** it applies to all subsequent LLM calls without restart

### Story 1.3: ServiceLevel CRD & Controller

As an **admin**,
I want to define SLIs and SLO targets per service via a ServiceLevel custom resource,
So that Beeper can calculate burn rates and score anomalies by customer impact.

**Acceptance Criteria:**

**Given** a ServiceLevel CRD YAML with service, SLI type (availability/latency/error_rate), metric selectors, objective target, and window
**When** the CRD is applied to the K8s cluster
**Then** the operator reconciles it and reports status (healthy/warning/critical)
**And** the CRD is validated for required fields before acceptance

**Given** a ServiceLevel CRD with burn_rate_alerts configured
**When** the CRD is reconciled
**Then** the operator registers the burn rate alert thresholds (severity, short_window, long_window, factor)

**Given** the operator is running
**When** 100+ ServiceLevel CRDs exist in the cluster
**Then** all CRDs are reconciled without performance degradation (NFR21)

### Story 1.4: SLO Burn Rate Calculation Engine

As the **system**,
I want to calculate SLO burn rates in real-time from ingested Prometheus metrics,
So that investigations can be triggered when burn rates exceed configured thresholds.

**Acceptance Criteria:**

**Given** a ServiceLevel CRD with a configured SLI metric and objective target
**When** Prometheus metrics are ingested by the operator
**Then** the SLO calculator computes compliance percentage and burn rate within a < 5 second refresh cycle (NFR6)
**And** burn rate snapshots are written to the `slo_snapshots` Qdrant collection

**Given** a burn rate that exceeds the configured alert factor for both short and long windows
**When** the burn rate alerter evaluates
**Then** an Investigation CRD is created with SLO context (service, burn rate, budget remaining)
**And** the investigation is triggered within 30 seconds of detection (NFR1)

**Given** the `slo_snapshots` Qdrant collection does not exist
**When** the operator starts up
**Then** the collection is created automatically as payload-only

### Story 1.5: Customer Impact Scoring & Investigation Priority

As an **SRE**,
I want anomalies scored by customer impact using SLO data rather than static severity labels,
So that I can focus on issues that actually affect users first.

**Acceptance Criteria:**

**Given** an anomaly detected on a service with an active ServiceLevel CRD
**When** the detection consumer scores the anomaly
**Then** customer impact is calculated based on SLO breach severity and error budget remaining
**And** an anomaly affecting a 99.9% SLO with 50% budget remaining scores higher than one affecting a 99% SLO with 90% budget remaining

**Given** multiple investigations are active simultaneously
**When** an SRE views the investigation list
**Then** investigations are sorted by SLO impact severity (highest impact first)
**And** the impact score is visible on each investigation card

### Story 1.6: Error Budget Policies

As an **admin**,
I want to define error budget policies that trigger notifications or deployment freezes,
So that teams are proactively alerted before SLO budgets are exhausted.

**Acceptance Criteria:**

**Given** a ServiceLevel CRD with error budget policy configuration
**When** error budget consumption crosses a configured threshold (e.g., 50%, 75%, 90%)
**Then** a notification event is generated with budget status and recommended action
**And** the event includes the burn rate trend and projected budget exhaustion time

**Given** an error budget policy with a "freeze" action at 95% consumption
**When** budget consumption reaches 95%
**Then** the system records a deployment freeze recommendation visible in the SLO dashboard
**And** a critical notification is queued (when notification engine is available in Epic 2)

### Story 1.7: SLO Compliance Dashboard

As a **user**,
I want to view SLO compliance, burn rate trends, and error budgets on a dashboard,
So that I can understand the reliability posture of all services at a glance.

**Acceptance Criteria:**

**Given** services with active ServiceLevel CRDs
**When** a user navigates to the SLO dashboard (`/slo`)
**Then** all services are listed with current compliance percentage, burn rate, and error budget remaining
**And** the page responds within 2 seconds (NFR2)

**Given** a specific service on the SLO dashboard
**When** a user clicks to view service detail (`/slo/services/{name}`)
**Then** burn rate trends, compliance history, and error budget consumption are displayed
**And** active investigations related to SLO breaches are linked

**Given** the SLO dashboard route
**When** accessed by any authenticated user (admin or user role)
**Then** the dashboard is visible (read-only — SLO configuration is admin-only via CRD)

### Story 1.8: Platform Resilience

As a **platform operator**,
I want Beeper to gracefully degrade when the LLM provider is unavailable and never become a single point of failure,
So that existing alerting continues and investigations don't silently stall.

**Acceptance Criteria:**

**Given** the LLM provider (via LiteLLM) becomes unavailable
**When** the investigator attempts an LLM call
**Then** the investigation is queued for retry and a human escalation notification is generated within 60 seconds (NFR15)
**And** the investigation status reflects "LLM unavailable — queued for retry"

**Given** the Beeper operator is down or restarting
**When** an anomaly occurs in the monitored cluster
**Then** existing Prometheus alerting and Loki-based alerts continue to function unaffected (NFR14)
**And** no investigation data is lost during the restart (NFR17)

**Given** the Beeper UI is temporarily unavailable
**When** an SRE checks their existing monitoring tools
**Then** all pre-Beeper alerting pathways remain operational

## Epic 2: Intelligent Notification Engine

**Goal:** Users receive justified notifications through Slack, PagerDuty, email, and webhooks when things matter — with routing rules, quiet hours, and false page tracking.

**FRs covered:** FR8, FR9, FR10, FR11, FR12, FR13, FR14, FR15
**NFRs addressed:** NFR22, NFR2

### Story 2.1: NotificationChannel CRD & Durable Outbox

As a **user**,
I want to configure outbound notification channels via a NotificationChannel custom resource,
So that Beeper can send alerts through my team's existing communication tools.

**Acceptance Criteria:**

**Given** a NotificationChannel CRD YAML with type (slack/pagerduty/email/webhook), config, credentials_secret, and routing rules
**When** the CRD is applied to the K8s cluster
**Then** the operator validates the credentials_secret exists and reports channel status (configured/error)
**And** the CRD is validated for required fields per channel type

**Given** the notification system initializes
**When** the `notification_outbox` Qdrant collection does not exist
**Then** it is created automatically as payload-only
**And** the background outbox worker starts processing queued notifications

**Given** a notification event is generated (investigation started/completed/fix proposed)
**When** the notification is written to the outbox
**Then** it persists in Qdrant and survives process restart
**And** failed deliveries retry with exponential backoff

### Story 2.2: Notification Routing Rules Engine

As a **user**,
I want to define notification routing rules based on severity, service, SLO state, and time of day,
So that the right people get the right notifications at the right time.

**Acceptance Criteria:**

**Given** a NotificationChannel CRD with routing rules (min_severity, services list, quiet_hours)
**When** a notification event is generated for a service at a given severity
**Then** the routing engine evaluates all configured channels and routes to matching channels only
**And** channels with `min_severity: high` do not receive `low` or `medium` events

**Given** quiet hours are configured (start: "22:00", end: "08:00", timezone)
**When** a non-critical notification is generated during quiet hours
**Then** it is suppressed until quiet hours end
**And** critical notifications with `escalation_override: true` bypass quiet hours

**Given** a notification event with SLO context from Epic 1
**When** the routing engine evaluates urgency
**Then** urgency is weighted by confirmed customer impact (SLO burn rate) rather than static severity

### Story 2.3: Slack Channel Integration

As a **user**,
I want Beeper to send rich Slack messages with investigation context,
So that I can assess and act on incidents directly from Slack.

**Acceptance Criteria:**

**Given** a configured Slack NotificationChannel with a channel and credentials_secret
**When** an investigation event is routed to the Slack channel
**Then** a rich block message is sent with investigation summary, evidence highlights, and confidence score
**And** the message includes action buttons (View Investigation, Approve Fix if applicable)

**Given** a Slack notification for an ongoing investigation
**When** updates occur (new evidence, confidence change, fix proposed)
**Then** updates are posted as threaded replies to the original message
**And** relevant users are @mentioned per channel configuration

**Given** the notification throughput target
**When** 1,000+ notification events are generated per hour
**Then** all Slack deliveries complete without drops (NFR22)

### Story 2.4: PagerDuty Bidirectional Integration

As a **user**,
I want Beeper to create, acknowledge, and resolve PagerDuty incidents automatically,
So that my on-call workflow integrates seamlessly with Beeper's investigation lifecycle.

**Acceptance Criteria:**

**Given** a configured PagerDuty NotificationChannel
**When** a critical investigation starts
**Then** a PagerDuty incident is created with investigation context and evidence summary

**Given** a PagerDuty incident created by Beeper
**When** Beeper begins investigating the root cause
**Then** the PagerDuty incident is acknowledged automatically

**Given** a PagerDuty incident created by Beeper
**When** the investigation resolves (fix verified or manually resolved)
**Then** the PagerDuty incident is resolved with resolution summary
**And** the resolution includes a link to the full investigation evidence trail

### Story 2.5: Email & Webhook Channels

As a **user**,
I want Beeper to send email digests and trigger webhooks to external systems,
So that I can integrate Beeper with CI/CD pipelines, Jira, and status pages.

**Acceptance Criteria:**

**Given** a configured email NotificationChannel with SMTP settings
**When** a critical notification is routed to email
**Then** an immediate email is sent with investigation summary and evidence links

**Given** a configured email channel with digest mode
**When** the digest interval elapses (e.g., daily)
**Then** a summary email is sent with all investigations, resolutions, and SLO status for the period

**Given** a configured webhook NotificationChannel with a target URL
**When** a notification event matches the webhook routing rules
**Then** a POST request is sent with the investigation payload (JSON, RFC 7807 error format on failure)
**And** failed webhook deliveries retry with exponential backoff

### Story 2.6: Notification Audit & False Page Tracking

As an **admin**,
I want every notification justified with evidence and false pages tracked as bugs,
So that I can measure and improve Beeper's notification accuracy over time.

**Acceptance Criteria:**

**Given** a notification is sent through any channel
**When** the notification is delivered
**Then** an audit record is stored with: channel, timestamp, investigation_id, evidence summary, delivery status

**Given** an SRE marks an investigation as "not-an-issue" or "inaccurate"
**When** that investigation had generated notifications
**Then** those notifications are flagged as false pages in the audit trail
**And** the false page count is trackable per service and per time period

**Given** a user navigates to the notification audit view (`/notifications/audit`)
**When** the page loads
**Then** notification history is displayed with delivery status, false page flags, and evidence justification
**And** filtering by service, channel, and date range is available

### Story 2.7: Notification Configuration UI

As a **user**,
I want to view and test notification channels from the UI,
So that I can verify my notification setup works before relying on it during incidents.

**Acceptance Criteria:**

**Given** a user navigates to `/notifications`
**When** the page loads
**Then** all configured NotificationChannel CRDs are listed with status (configured/error)
**And** routing rules summary is visible per channel

**Given** a configured notification channel
**When** a user clicks "Send Test Notification"
**Then** a test notification is delivered through the channel with sample investigation data
**And** the test result (success/failure with error detail) is displayed in the UI

**Given** the notification configuration page
**When** accessed by role "user"
**Then** channel viewing and test sending are available
**And** channel creation/deletion requires CRD management (kubectl)

## Epic 3: Graduated Trust & Autonomy

**Goal:** Admins can control how autonomous Beeper is per service (TL1-5), configure confidence gates, and track accuracy over time. SREs provide investigation feedback that tunes Beeper's behavior. Signal-to-noise improves measurably.

**FRs covered:** FR16, FR17, FR18, FR19, FR20, FR21, FR22
**NFRs addressed:** NFR12, NFR19

### Story 3.1: Trust Level Configuration & Persistence

As an **admin**,
I want to configure trust levels (1-5) per service controlling Beeper's autonomy,
So that I can gradually increase Beeper's autonomy as it proves reliable for each service.

**Acceptance Criteria:**

**Given** the existing `service_trust_levels` Qdrant collection
**When** an admin updates a service's trust level via the API (`PUT /api/services/{name}/trust`)
**Then** the trust level is stored with the new value (1-5) and an audit timestamp
**And** the endpoint requires `@require_role("admin")` (NFR12)

**Given** trust level definitions: TL1 (advisory only), TL2 (suggest with evidence), TL3 (act with approval), TL4 (act and notify), TL5 (fully autonomous)
**When** any component queries a service's trust level
**Then** the behavior boundary is enforced per the trust level definition
**And** a service without a configured trust level defaults to TL1 (advisory only)

**Given** the trust level API
**When** accessed by a user with role "user"
**Then** read access is allowed but write access is rejected with HTTP 403

### Story 3.2: Confidence Gate Engine

As the **system**,
I want to gate actions by confidence threshold so only sufficiently confident conclusions trigger actions,
So that Beeper doesn't act on uncertain evidence.

**Acceptance Criteria:**

**Given** an investigation reaches a conclusion with a confidence score (0.0-1.0)
**When** the confidence gate evaluates the action
**Then** the action is permitted only if the confidence score meets or exceeds the gate threshold for the service's trust level
**And** below-threshold conclusions are presented as advisory recommendations only

**Given** the confidence gate thresholds per trust level (e.g., TL3 requires 0.85, TL4 requires 0.75, TL5 requires 0.60)
**When** the same conclusion (confidence: 0.80) is evaluated for services at TL3 vs TL4
**Then** the TL3 service gets an advisory recommendation while the TL4 service gets an automatic action

**Given** an action is blocked by the confidence gate
**When** the investigation result is displayed
**Then** the UI shows "Confidence: 80% — below threshold (85%) for auto-action — advisory only"
**And** the SRE can manually approve the action regardless

### Story 3.3: Confidence Gate Threshold Configuration

As an **admin**,
I want to configure confidence gate thresholds per trust level,
So that I can tune how much evidence Beeper needs before acting autonomously.

**Acceptance Criteria:**

**Given** the confidence gate configuration endpoint (`PUT /api/config/confidence-gates`)
**When** an admin sets thresholds (e.g., TL3: 0.85, TL4: 0.75, TL5: 0.60)
**Then** the thresholds are persisted and immediately effective for new evaluations
**And** the endpoint requires `@require_role("admin")` (NFR12)

**Given** the trust configuration UI page (`/settings/trust`)
**When** an admin views the page
**Then** current thresholds are displayed per trust level with explanations of each level's behavior
**And** the admin can adjust thresholds with a slider or input field

**Given** a threshold is set to an unreasonable value (e.g., 0.0 or > 1.0)
**When** the admin submits the change
**Then** validation rejects the value with a clear error message

### Story 3.4: One-Click Investigation Feedback

As an **SRE**,
I want to provide one-click feedback on investigation accuracy (accurate / inaccurate / not-an-issue),
So that Beeper can learn from my expertise and improve over time.

**Acceptance Criteria:**

**Given** a completed investigation displayed in the UI
**When** the SRE clicks one of the feedback buttons (accurate / inaccurate / not-an-issue)
**Then** the feedback is recorded against the investigation in Qdrant with the user, timestamp, and feedback type
**And** the interaction is a single click — no modal, no form, no confirmation required

**Given** feedback is submitted
**When** the investigation detail page refreshes
**Then** the selected feedback is highlighted and changing feedback is allowed (last feedback wins)
**And** an SSE event updates other viewers in real-time

**Given** the feedback endpoint (`POST /api/investigations/{id}/feedback`)
**When** accessed by any authenticated user (admin or user)
**Then** the feedback is accepted (not admin-only — all SREs should provide feedback)

### Story 3.5: Adaptive Alert Threshold Tuning

As the **system**,
I want to adapt alert thresholds based on investigation outcome feedback from SREs,
So that Beeper reduces false positives and improves signal quality over time.

**Acceptance Criteria:**

**Given** a service has accumulated 10+ investigation feedback entries
**When** the adaptive tuning process evaluates the feedback
**Then** alert thresholds are adjusted: services with high "not-an-issue" rates get higher thresholds, services with high "accurate" rates maintain or lower thresholds
**And** threshold adjustments are logged with reasoning (e.g., "Raised threshold 15%: 6/10 recent alerts marked not-an-issue")

**Given** an adaptive threshold adjustment is proposed
**When** the service's trust level is TL1 or TL2
**Then** the adjustment is presented as a recommendation to the admin (not auto-applied)
**And** at TL3+ the adjustment is applied automatically with notification to admin

**Given** an admin views the threshold adjustment history
**When** navigating to `/settings/trust/history`
**Then** all adjustments are listed with before/after values, feedback evidence, and timestamp

### Story 3.6: Impact-Weighted Escalation Urgency

As the **system**,
I want to weight escalation urgency by confirmed customer impact rather than theoretical severity,
So that SREs are interrupted proportionally to actual user impact.

**Acceptance Criteria:**

**Given** an investigation with SLO context (burn rate, budget remaining) from Epic 1
**When** escalation urgency is calculated
**Then** urgency = f(burn_rate, budget_remaining, affected_users) rather than static severity mapping
**And** a fast-burning SLO with 10% budget remaining escalates higher than a slow-burning SLO with 80% budget remaining

**Given** escalation urgency is calculated for a service with investigation feedback history
**When** the service has a high "accurate" feedback rate (>80%)
**Then** urgency is preserved as-is (trusted signal)
**And** a service with a low "accurate" rate (<50%) has urgency dampened with a "low confidence" flag

**Given** the investigation list view
**When** sorted by urgency
**Then** the impact-weighted urgency score is displayed alongside the investigation
**And** tooltips explain the urgency calculation factors

### Story 3.7: Noise Report Dashboard

As an **admin**,
I want to view a noise report showing signal-to-noise ratio and false page trends,
So that I can measure whether Beeper's alerting is improving and identify noisy services.

**Acceptance Criteria:**

**Given** accumulated investigation feedback data
**When** an admin navigates to the noise report (`/reports/noise`)
**Then** the dashboard shows: signal-to-noise ratio (accurate / total), false page rate trend over time, and per-service breakdown
**And** the page responds within 2 seconds (NFR2)

**Given** the noise report dashboard
**When** filtering by service or time period
**Then** the metrics recalculate for the filtered view
**And** the worst-performing services (highest false page rate) are highlighted

**Given** the noise report page
**When** accessed by a user with role "user"
**Then** the page is visible (read-only) — noise metrics benefit all SREs, not just admins

## Epic 4: Autonomous Remediation Pipeline

**Goal:** Beeper can propose fixes, test them in a sandbox, verify resolution, and create auto-PRs with full evidence trails. Actions are trust-gated and reversible. Proven fixes compound in the KB.

**FRs covered:** FR23, FR24, FR25, FR26, FR27, FR28, FR29, FR30, FR31, FR62
**NFRs addressed:** NFR9, NFR13, NFR16

### Story 4.1: Repository CRD & Git Provider Integration

As an **admin**,
I want to register code repositories via a Repository CRD with branch policies and coding standards,
So that Beeper knows which repos to target for auto-PRs and how to comply with team conventions.

**Acceptance Criteria:**

**Given** a Repository CRD YAML with repo_url, provider (github/gitlab), credentials_secret, default_branch, branch_policy, and coding_standards
**When** the CRD is applied to the K8s cluster
**Then** the operator validates the credentials_secret exists and tests repository access
**And** the CRD status reports (connected/auth-error/not-found)

**Given** a Repository CRD with branch_policy configured (e.g., prefix: "beeper/fix-", require_pr: true)
**When** Beeper creates a fix branch
**Then** the branch name conforms to the policy and a PR is created against default_branch
**And** repository credentials are scoped per-repo tokens, never org-wide (NFR9)

**Given** multiple Repository CRDs across different providers
**When** the operator reconciles
**Then** each repository connection is independently managed and failures are isolated

### Story 4.2: Human-Language Runbook Execution

As the **system**,
I want to execute human-language runbooks without requiring DSL translation,
So that SREs can write remediation procedures in plain English and Beeper follows them.

**Acceptance Criteria:**

**Given** a KB entry tagged as a runbook with human-language steps (e.g., "1. Check if the pod is OOMKilled. 2. Increase memory limit by 25%. 3. Verify pod restarts successfully.")
**When** an investigation matches the runbook's trigger conditions
**Then** the LLM interprets the runbook steps and maps them to executable actions
**And** each step's interpretation is logged with the original runbook text for audit

**Given** a runbook step that requires a cluster action (e.g., "increase memory limit")
**When** the action is evaluated
**Then** it is gated by the service's trust level and confidence threshold (from Epic 3)
**And** at TL1-2, the interpreted steps are presented as advisory recommendations only

**Given** a runbook execution in progress
**When** a step fails or produces unexpected results
**Then** execution halts and the SRE is notified with the failure context and remaining steps

### Story 4.3: Advisory Test Plan Generation

As the **system**,
I want to always produce an advisory test plan describing how to verify a hypothesis,
So that even without a sandbox, SREs know exactly how to validate Beeper's conclusions.

**Acceptance Criteria:**

**Given** an investigation that reaches a root cause hypothesis
**When** the investigation conclusion is generated
**Then** an advisory test plan is included with: hypothesis statement, verification steps, expected outcomes, and metrics to watch
**And** the test plan is generated regardless of trust level or sandbox availability

**Given** an advisory test plan
**When** displayed in the investigation detail view
**Then** steps are numbered, actionable, and reference specific metrics/endpoints
**And** the SRE can mark steps as completed or skipped

**Given** the advisory test plan
**When** a sandbox environment is available (Story 4.5)
**Then** the test plan can be promoted to automated sandbox execution

### Story 4.4: Auto-PR Generation with Evidence Trail

As the **system**,
I want to generate auto-PRs with full evidence trails linking back to the investigation,
So that code reviewers have complete context on why the fix is proposed and what evidence supports it.

**Acceptance Criteria:**

**Given** an investigation that identifies a code-level fix in a registered Repository
**When** the fix is generated at TL3+ or manually approved
**Then** a branch is created per the repository's branch_policy, the fix is committed, and a PR is opened
**And** the PR description includes: investigation link, root cause analysis, log correlation evidence, production conditions at time of incident

**Given** an auto-PR is created
**When** the PR is viewed on the Git provider
**Then** the audit trail is complete: anomaly → investigation → fix → PR
**And** the PR is linked back to the investigation in Qdrant (FR30)

**Given** an auto-PR for a service at TL3 (act with approval)
**When** the PR is created
**Then** the PR is marked as draft/WIP and the SRE is notified for review
**And** at TL4-5, the PR is opened as ready for merge (per branch policy)

### Story 4.5: Sandbox Test Execution

As the **system**,
I want to design sandbox-specific tests and execute them in an isolated environment,
So that fixes are validated before reaching production.

**Acceptance Criteria:**

**Given** a sandbox namespace configured with NetworkPolicy isolation (NFR13)
**When** a fix is ready for testing
**Then** the fix is deployed to the sandbox namespace and sandbox-specific tests are executed
**And** the sandbox has no access to production data or services (network-isolated)

**Given** sandbox test execution
**When** the tests run
**Then** results are captured with pass/fail status, logs, and metric comparisons
**And** the results are attached to the investigation evidence trail

**Given** no sandbox environment is configured
**When** a fix is generated
**Then** only the advisory test plan (Story 4.3) is produced
**And** the investigation notes "No sandbox available — manual verification recommended"

### Story 4.6: Post-Fix Metric Verification

As the **system**,
I want to verify that a fix resolves the issue by monitoring post-fix metrics,
So that we have evidence-based confirmation that the problem is actually solved.

**Acceptance Criteria:**

**Given** a fix has been applied (either in sandbox or production at TL4-5)
**When** the post-fix verification window elapses (configurable, default 15 minutes)
**Then** the system compares pre-fix and post-fix metrics for the affected SLOs
**And** verification result is: confirmed (metrics improved), inconclusive (no change), degraded (metrics worsened)

**Given** post-fix metrics show degradation
**When** the verification result is "degraded"
**Then** the autonomous action is rolled back within 60 seconds (NFR16, FR62)
**And** the SRE is immediately notified with pre-fix and post-fix metric comparison

**Given** post-fix metrics confirm resolution
**When** the verification result is "confirmed"
**Then** the investigation status moves to "verified" and the fix is marked as proven
**And** the proven fix is eligible for KB accumulation (Story 4.8)

### Story 4.7: Trust-Gated Remediation Actions

As the **system**,
I want remediation actions gated to the configured trust level and confidence tier,
So that Beeper never exceeds the autonomy boundary an admin has set.

**Acceptance Criteria:**

**Given** a remediation action (runbook step, auto-PR, sandbox deploy) for a service at TL1
**When** the action is evaluated
**Then** only advisory output is produced — no code changes, no cluster mutations
**And** the advisory includes what Beeper would do at higher trust levels

**Given** a remediation action for a service at TL3 with confidence 0.82 and gate threshold 0.85
**When** the confidence gate evaluates
**Then** the action is blocked and presented as "requires manual approval" with confidence explanation
**And** the SRE can one-click approve to override

**Given** a remediation action for a service at TL5 with confidence above threshold
**When** the action executes autonomously
**Then** a notification is sent to the admin with action details
**And** a rollback path is registered for the action (FR62)

### Story 4.8: Proven Fix Accumulation in KB

As the **system**,
I want proven fixes accumulated in the KB for future reference,
So that Beeper builds a library of verified solutions that compound over time.

**Acceptance Criteria:**

**Given** a fix that has been verified as "confirmed" (Story 4.6)
**When** the KB accumulation process runs
**Then** a KB entry is created with: fix description, root cause pattern, verification evidence, and link to the source investigation
**And** the entry is tagged with validation_status: "proven" and the service name

**Given** a future investigation on the same service with a similar anomaly pattern
**When** the investigator searches the KB
**Then** the proven fix entry is surfaced as a high-confidence recommendation
**And** the recommendation includes the original verification evidence

**Given** a proven fix entry in the KB
**When** viewed by an SRE
**Then** the full audit trail is navigable: anomaly → investigation → fix → PR → verification → KB entry

## Epic 5: Real-Time Investigation Collaboration

**Goal:** Teams can interact with Beeper during live investigations — annotating, redirecting, approving fixes in real-time. Shift handoffs happen in 30 seconds instead of 30 minutes.

**FRs covered:** FR32, FR33, FR34, FR35, FR36, FR37
**NFRs addressed:** NFR5, NFR2

### Story 5.1: WebSocket Collaboration Channel

As a **user**,
I want to interact with Beeper in real-time during active investigations via WebSocket,
So that I can collaborate with the AI agent as if it were a team member on a live call.

**Acceptance Criteria:**

**Given** a user opens an active investigation detail page
**When** the page loads
**Then** a Flask-SocketIO WebSocket connection is established for that investigation room
**And** the connection uses the two-channel pattern: SocketIO for collaboration, SSE for all other real-time updates

**Given** an active WebSocket connection to an investigation
**When** the user sends a message (question, direction, comment)
**Then** the message is delivered to all connected users within 500ms (NFR5)
**And** Beeper processes the message and responds with relevant context

**Given** the WebSocket connection drops (network issue, tab close)
**When** the user reconnects
**Then** message history is preserved and the user sees all messages since their last connection

### Story 5.2: Evidence Presentation with References

As the **system**,
I want to present evidence with references to specific metrics, logs, and prior KB entries,
So that SREs can verify Beeper's reasoning by clicking through to source data.

**Acceptance Criteria:**

**Given** an investigation step produces evidence (metric anomaly, log pattern, KB match)
**When** the evidence is displayed in the investigation timeline
**Then** each evidence item includes a clickable reference to the source (Prometheus query, Loki log line, KB entry ID)
**And** hovering shows a preview; clicking navigates to the full source

**Given** evidence references a prior KB entry
**When** the KB entry is displayed inline
**Then** the entry's validation status (proven/AI-generated/human-confirmed) is visible
**And** the relevance score (semantic similarity) is shown

**Given** an investigation with multiple evidence items
**When** displayed in the timeline
**Then** evidence is ordered chronologically with the investigation narrative
**And** each item is tagged by type (metric, log, deploy, KB, config change)

### Story 5.3: Investigation Annotation & Redirection

As a **user**,
I want to annotate, redirect, and comment on active investigations,
So that I can steer Beeper's investigation when I have domain knowledge it lacks.

**Acceptance Criteria:**

**Given** an active investigation
**When** a user adds an annotation (free-text comment)
**Then** the annotation is attached to the current investigation step with user, timestamp, and context
**And** all connected users see the annotation in real-time via WebSocket

**Given** an active investigation heading in a wrong direction
**When** a user sends a redirect command (e.g., "Focus on the database connection pool, not the API gateway")
**Then** Beeper acknowledges the redirect, adjusts its investigation focus, and explains what changed
**And** the redirect is logged in the investigation timeline as a human intervention

**Given** investigation annotations and redirects
**When** the investigation is later reviewed
**Then** all human interventions are visible in the timeline, distinguished from Beeper's autonomous steps

### Story 5.4: Fix Approval & Rejection

As a **user**,
I want to approve or reject Beeper-proposed fixes within my permission level,
So that I maintain control over what changes are applied to my services.

**Acceptance Criteria:**

**Given** Beeper proposes a fix for a service at TL3 (act with approval)
**When** the fix is presented in the investigation view
**Then** "Approve" and "Reject" buttons are displayed with the fix details, evidence, and test plan
**And** the approve action uses optimistic UI (immediate visual feedback, server confirmation follows)

**Given** a user with role "user" approves a fix
**When** the approval is submitted
**Then** the fix proceeds to execution (auto-PR, sandbox test, or direct apply per trust level)
**And** the approval is logged with user, timestamp, and the fix version approved

**Given** a user rejects a fix
**When** the rejection is submitted
**Then** the investigation records the rejection with optional rejection reason
**And** Beeper can propose an alternative approach if the user provides guidance

### Story 5.5: Shift Handoff Summaries

As a **user**,
I want Beeper to generate shift handoff summaries with active investigations, resolved incidents, and items to watch,
So that incoming SREs are productive in 30 seconds instead of spending 30 minutes catching up.

**Acceptance Criteria:**

**Given** a user requests a handoff summary (`/handoff` or via the UI at `/handoff`)
**When** the summary is generated
**Then** it includes: active investigations (status, last update, assigned), resolved incidents (past 8 hours), SLO status changes, and items to watch (elevated burn rates, pending fixes)
**And** the summary is generated within 2 seconds (NFR2)

**Given** the handoff summary
**When** displayed in the UI
**Then** each item is clickable to navigate to the full investigation or SLO detail
**And** the summary can be copied to clipboard or sent to a Slack channel (if configured)

**Given** no active investigations or incidents
**When** a handoff summary is requested
**Then** the summary reports "All clear" with current SLO compliance overview

### Story 5.6: KB Entry Surfacing During Live Investigations

As the **system**,
I want to surface relevant past KB entries during live investigations,
So that Beeper and the SRE can leverage institutional knowledge in real-time.

**Acceptance Criteria:**

**Given** an active investigation with identified symptoms
**When** the investigator reaches the analysis phase
**Then** semantically similar KB entries are retrieved and displayed as "Related Knowledge" in the investigation view
**And** entries are ranked by relevance score and validation status (proven > human-confirmed > AI-generated)

**Given** a surfaced KB entry during a live investigation
**When** the SRE clicks on the entry
**Then** the full KB entry is displayed with its evidence trail and prior investigation links
**And** the SRE can flag the entry as "relevant" or "not relevant" to improve future surfacing

**Given** no relevant KB entries exist
**When** the KB search returns empty
**Then** the investigation notes "No prior knowledge found — this may be a novel issue"
**And** the investigation outcome is marked as a candidate for new KB entry creation

## Epic 6: Knowledge & Signal Intelligence

**Goal:** The KB compounds automatically from resolved investigations with bi-directional links. Beeper correlates anomalies with deploys, config changes, and service topology — building institutional knowledge that gets smarter over time.

**FRs covered:** FR38, FR39, FR40, FR41, FR42, FR43, FR44, FR45, FR46
**NFRs addressed:** NFR2, NFR20

### Story 6.1: Automatic KB Entry Creation from Resolved Investigations

As the **system**,
I want to create KB entries automatically from resolved investigations,
So that every investigation outcome contributes to Beeper's institutional knowledge without manual effort.

**Acceptance Criteria:**

**Given** an investigation transitions to "resolved" or "verified" status
**When** the KB auto-creation process triggers
**Then** a KB entry is created with: root cause summary, symptoms, evidence references, resolution steps, and affected service
**And** the entry is tagged with validation_status: "AI-generated" and linked to the source investigation

**Given** a resolved investigation that closely matches an existing KB entry
**When** the auto-creation process evaluates similarity
**Then** the existing entry is updated/enriched rather than creating a duplicate
**And** the update is versioned in the `knowledge_versions` collection

**Given** the KB has 10,000+ entries
**When** semantic search is performed
**Then** results return within 2 seconds (NFR20)

### Story 6.2: Bi-Directional KB-Investigation Links

As the **system**,
I want KB entries linked bi-directionally to investigations and related entries,
So that navigating between knowledge and incidents is seamless in both directions.

**Acceptance Criteria:**

**Given** a KB entry created from investigation #42
**When** a user views the KB entry
**Then** a "Source Investigation" link navigates to investigation #42
**And** a "Related Entries" section lists semantically similar KB entries with relevance scores

**Given** investigation #42 that produced a KB entry
**When** a user views investigation #42
**Then** a "Knowledge Created" link navigates to the resulting KB entry
**And** "Related Knowledge" shows entries that were referenced during the investigation

**Given** a KB entry is updated or corrected
**When** the update is saved
**Then** all bi-directional links are preserved and the link metadata includes the relationship type (source, related, supersedes)

### Story 6.3: Per-Service Knowledge Views

As a **user**,
I want per-service knowledge views through service catalog integration,
So that I can see all institutional knowledge related to a specific service in one place.

**Acceptance Criteria:**

**Given** a user navigates to a service detail page (`/services/{name}/knowledge`)
**When** the page loads
**Then** all KB entries tagged with that service are displayed, sorted by relevance and recency
**And** entries are grouped by category (root causes, runbooks, proven fixes, patterns)

**Given** the service knowledge view
**When** filtered by validation status
**Then** the user can view only "proven" entries, or only "AI-generated" entries needing review
**And** entry counts per validation status are shown as filter badges

**Given** a service with no KB entries
**When** the knowledge view loads
**Then** a helpful empty state is shown: "No knowledge entries yet — entries are created automatically as investigations resolve"

### Story 6.4: KB Entry Validation Weighting

As the **system**,
I want KB entries weighted by validation status (human-confirmed, AI-generated, corrected),
So that proven knowledge ranks higher than unverified AI conclusions.

**Acceptance Criteria:**

**Given** KB entries with different validation statuses
**When** the investigator performs a semantic search for relevant knowledge
**Then** results are ranked with weighting: proven (1.0x) > human-confirmed (0.9x) > corrected (0.8x) > AI-generated (0.6x)
**And** the weighting is applied as a multiplier on the semantic similarity score

**Given** an SRE confirms an AI-generated KB entry as accurate
**When** the confirmation is recorded
**Then** the entry's validation_status changes from "AI-generated" to "human-confirmed"
**And** the change is versioned with the confirming user and timestamp

**Given** an SRE corrects a KB entry
**When** the correction is saved
**Then** the validation_status changes to "corrected" with the original and corrected content preserved
**And** future investigations referencing this entry see the corrected version

### Story 6.5: KB Entry Review, Edit & Correction

As a **user**,
I want to review, edit, and correct Beeper's KB entries as a feedback mechanism,
So that I can fix errors and improve the quality of Beeper's institutional knowledge.

**Acceptance Criteria:**

**Given** a user views a KB entry detail page (`/knowledge/{id}`)
**When** the user clicks "Edit"
**Then** an inline editor allows modifying the entry's content, tags, and category
**And** the edit is saved as a new version in `knowledge_versions` with the editor and timestamp

**Given** a user edits a KB entry
**When** the edit is saved
**Then** the validation_status is updated to "corrected" if content changed, or preserved if only tags changed
**And** the `corrections` collection records the diff for learning purposes

**Given** a KB entry with version history
**When** a user clicks "History"
**Then** all versions are displayed with diffs, authors, and timestamps
**And** the user can revert to a previous version

### Story 6.6: Unified Investigation Timeline

As a **user**,
I want a unified investigation timeline correlating logs, metrics, deploys, and K8s events,
So that I can see the complete picture of what happened around an incident in one view.

**Acceptance Criteria:**

**Given** an investigation detail page
**When** the timeline view loads
**Then** events are displayed chronologically: metric anomalies, log patterns, K8s events (pod restarts, OOMs, scaling), deploy events, config changes
**And** each event type has a distinct visual indicator (icon + color)

**Given** a timeline with multiple event types
**When** the user filters by event type (e.g., "deploys only")
**Then** only matching events are shown while maintaining the time axis
**And** the page responds within 2 seconds (NFR2)

**Given** a timeline event
**When** the user clicks on it
**Then** the full event detail is shown inline (log content, metric graph, deploy diff, K8s event details)

### Story 6.7: Deploy Correlation

As the **system**,
I want to correlate anomalies with recent deployments,
So that SREs can immediately see if a deploy likely caused the issue.

**Acceptance Criteria:**

**Given** an anomaly detected on a service
**When** the investigator analyzes the anomaly
**Then** recent deployments to that service (within a configurable lookback window, default 1 hour) are retrieved
**And** temporal correlation is calculated (e.g., "anomaly started 4 min after deploy #847")

**Given** a deploy is correlated with an anomaly
**When** the correlation is displayed in the investigation
**Then** the deploy details are shown: commit hash, author, changed files, deploy timestamp
**And** the correlation confidence is rated (strong: <5 min gap, moderate: 5-30 min, weak: 30-60 min)

**Given** no recent deployments exist for the affected service
**When** the deploy correlation check runs
**Then** the investigation notes "No recent deployments found — likely not deploy-related"

### Story 6.8: Service Dependency Topology

As the **system**,
I want to discover and display service dependency topology,
So that SREs can understand blast radius and identify cascading failure paths.

**Acceptance Criteria:**

**Given** K8s service definitions and network traffic patterns
**When** the topology discovery process runs
**Then** service-to-service dependencies are identified and stored
**And** the topology is refreshable on demand or via periodic background process

**Given** a user navigates to the topology view (`/topology`)
**When** the page loads
**Then** services are displayed as a graph with dependency edges
**And** services with active investigations or SLO breaches are highlighted

**Given** an investigation on a specific service
**When** the investigation detail shows dependencies
**Then** upstream and downstream services are listed with their current health status
**And** potential blast radius is indicated

### Story 6.9: Change Event Ingestion & Correlation

As the **system**,
I want to ingest and correlate change events (config changes, scaling, DNS, certs),
So that Beeper can identify non-deploy changes that may have caused anomalies.

**Acceptance Criteria:**

**Given** K8s watch events for ConfigMaps, Secrets, HPA scaling, Ingress/DNS, and cert-manager resources
**When** a change event occurs
**Then** the event is stored with: resource type, namespace, name, change diff, timestamp
**And** the event is available for timeline correlation

**Given** an anomaly under investigation
**When** the investigator checks for correlated changes
**Then** all change events within the lookback window for the affected service and its dependencies are surfaced
**And** temporal correlation is calculated (same as deploy correlation)

**Given** change events are accumulating
**When** storage grows beyond the retention window (configurable, default 30 days)
**Then** older events are pruned automatically

## Epic 7: Developer Experience & Analytics

**Goal:** Power users navigate with keyboard shortcuts and a command palette. Reliability scores, MTTR trends, and trust progression dashboards give leadership visibility. Diana gets investor-ready reports.

**FRs covered:** FR47, FR48, FR49, FR50, FR51, FR52, FR53
**NFRs addressed:** NFR2

### Story 7.1: Command Palette & Keyboard Shortcuts

As a **user**,
I want to navigate the UI via keyboard shortcuts and a command palette (Cmd+K),
So that I can work at speed without reaching for the mouse during incidents.

**Acceptance Criteria:**

**Given** a user presses Cmd+K (or Ctrl+K) anywhere in the UI
**When** the command palette opens
**Then** a search input with ARIA combobox role is displayed, matching commands and navigation targets as the user types
**And** the palette closes on Escape or clicking outside

**Given** the command palette is open
**When** the user types a query (e.g., "inv" or "slo" or "hand")
**Then** matching items are filtered in real-time: navigation targets, recent investigations, actions (e.g., "Request Handoff", "View SLO Dashboard")
**And** the user can select with arrow keys + Enter

**Given** keyboard shortcuts are defined for common actions
**When** a user presses a shortcut (e.g., `g i` for go-to-investigations, `g s` for go-to-SLO, `?` for shortcut help)
**Then** the action executes immediately
**And** shortcuts are discoverable via the `?` help overlay and the command palette

### Story 7.2: Investigation Workflow States

As the **system**,
I want to track investigations through workflow states (detected → investigating → resolved → verified),
So that every investigation has a clear lifecycle and status is always unambiguous.

**Acceptance Criteria:**

**Given** a new anomaly triggers an investigation
**When** the Investigation CRD is created
**Then** the status is set to "detected" with a timestamp

**Given** an investigation in "detected" status
**When** the investigator begins analysis
**Then** the status transitions to "investigating" with investigation start timestamp
**And** invalid transitions (e.g., detected → verified) are rejected

**Given** an investigation reaches a conclusion
**When** the conclusion is recorded (root cause identified, fix proposed, or no action needed)
**Then** the status transitions to "resolved" with resolution details
**And** if post-fix verification confirms the fix (Story 4.6), the status transitions to "verified"

**Given** the investigation list view
**When** filtered by workflow state
**Then** users can view investigations grouped by state with counts per state
**And** state badges are color-coded (detected: yellow, investigating: blue, resolved: green, verified: purple)

### Story 7.3: Remediation Progress Tracking

As a **user**,
I want to track remediation progress from detection through fix verification,
So that I can see at a glance where each incident stands in the fix lifecycle.

**Acceptance Criteria:**

**Given** an investigation with an associated remediation action (auto-PR, runbook, sandbox test)
**When** the user views the investigation detail
**Then** a progress tracker shows the remediation pipeline: proposed → approved → testing → applied → verifying → verified/rolled-back
**And** the current stage is highlighted with timestamps for completed stages

**Given** the investigation list view
**When** investigations have active remediations
**Then** a remediation status badge is visible (e.g., "PR open", "sandbox testing", "verifying")
**And** clicking the badge navigates to the remediation detail

**Given** a remediation that was rolled back
**When** the progress tracker displays
**Then** the rollback stage is shown with the reason (metric degradation, manual rollback, timeout)
**And** the pre-rollback and post-rollback metric comparison is accessible

### Story 7.4: Per-Service Health Feeds

As a **user**,
I want to view per-service health feeds with recent investigations, SLO status, and trends,
So that I can get a complete picture of any service's operational health in one view.

**Acceptance Criteria:**

**Given** a user navigates to a service health page (`/services/{name}`)
**When** the page loads
**Then** the feed shows: current SLO compliance, active investigations, recent resolved investigations (last 7 days), trust level, and reliability trend
**And** the page responds within 2 seconds (NFR2)

**Given** the service health feed
**When** new investigation events occur for that service
**Then** the feed updates via SSE without page reload
**And** the feed uses ARIA feed role for accessibility

**Given** the service list view (`/services`)
**When** the page loads
**Then** all services are listed with health summary badges (healthy/warning/critical based on SLO status)
**And** services with active investigations are highlighted

### Story 7.5: Reliability Score per Service

As the **system**,
I want to calculate a reliability score per service as a composite of SLO compliance, incident frequency, and MTTR,
So that leadership can compare service reliability at a glance.

**Acceptance Criteria:**

**Given** a service with SLO data, investigation history, and resolution timestamps
**When** the reliability score is calculated
**Then** the score (0-100) is a weighted composite: SLO compliance (40%), incident frequency trend (30%), MTTR trend (30%)
**And** the score is recalculated on a configurable interval (default: hourly)

**Given** the service health page
**When** the reliability score is displayed
**Then** it includes the composite score, a trend indicator (improving/stable/declining), and a breakdown of contributing factors
**And** the score uses ARIA meter role for accessibility

**Given** the service list view
**When** sorted by reliability score
**Then** services are ranked from lowest to highest reliability
**And** services below a configurable threshold (default: 70) are flagged with a warning indicator

### Story 7.6: MTTR, Impact & Trust Trend Dashboards

As a **user**,
I want to view MTTR trends, customer impact trends, and trust progression dashboards,
So that I can measure whether Beeper is making operations better over time.

**Acceptance Criteria:**

**Given** a user navigates to the analytics dashboard (`/analytics`)
**When** the page loads
**Then** three dashboard sections are displayed: MTTR trends, customer impact trends, and trust level progression
**And** the page responds within 2 seconds (NFR2)

**Given** the MTTR trends section
**When** the user views the chart
**Then** MTTR is plotted over time (weekly aggregation) for all services or filtered by service
**And** the trend line shows improvement or degradation with percentage change

**Given** the trust progression section
**When** the user views trust level changes
**Then** a timeline shows when services moved between trust levels (TL1→TL2, TL2→TL3, etc.)
**And** the dashboard shows the distribution of services across trust levels

### Story 7.7: Investor-Ready Reports

As **Diana** (founder/CEO),
I want investor-ready reports derived from Beeper's operational data,
So that I can demonstrate Beeper's value with real metrics during fundraising conversations.

**Acceptance Criteria:**

**Given** Diana navigates to the reports page (`/reports/executive`)
**When** the page loads
**Then** a report is displayed with: total investigations resolved, MTTR improvement percentage, SLO compliance across all services, trust level progression, and false page reduction trend
**And** the report is formatted for presentation (clean layout, exportable)

**Given** the executive report
**When** Diana clicks "Export PDF"
**Then** a PDF is generated with the current report data, Beeper branding, and date range
**And** the PDF is suitable for investor slide decks

**Given** the executive report
**When** filtered by time period (last 30 days, last 90 days, all time)
**Then** all metrics recalculate for the selected period
**And** comparison to previous period is shown (e.g., "MTTR improved 35% vs previous 90 days")

## Epic 8: Investor Demo Platform

**Goal:** Diana can run a scripted, repeatable demo that showcases the full detect → investigate → fix → prove lifecycle on a purpose-built chaotic application. 10 consecutive runs without failure.

**FRs covered:** FR54, FR55, FR56, FR57
**NFRs addressed:** NFR7, NFR18

### Story 8.1: Chaotic Demo Application Deployment

As an **admin**,
I want to deploy a purpose-built chaotic microservices application in K8s alongside Beeper,
So that there is a realistic target environment for demonstrating Beeper's capabilities.

**Acceptance Criteria:**

**Given** the `demo/` directory in the Beeper monorepo
**When** an admin runs the demo deployment command (Helm install or `make demo-deploy`)
**Then** a multi-service application is deployed in a dedicated namespace with: API gateway, backend service, database, and worker
**And** each service has Prometheus metrics, structured logging, and ServiceLevel CRDs pre-configured

**Given** the demo application is deployed
**When** no faults are injected
**Then** all services are healthy, SLOs are met, and the application serves synthetic traffic
**And** the demo app does not interfere with Beeper's monitoring of real workloads

**Given** the demo application
**When** an admin runs `make demo-teardown`
**Then** all demo resources are cleanly removed from the cluster with no orphaned resources

### Story 8.2: Configurable Fault Injection

As an **admin**,
I want to trigger configurable fault injections (memory leak, bad deploy, cascading failure, scale-dependent issues),
So that I can demonstrate specific failure scenarios during investor presentations.

**Acceptance Criteria:**

**Given** the demo application is running healthy
**When** an admin triggers a fault via the demo CLI (`make demo-fault TYPE=memory-leak SERVICE=backend`)
**Then** the specified fault is injected into the target service within 10 seconds
**And** the fault manifests as observable symptoms (metrics degrade, logs show errors, SLO burn rate increases)

**Given** configurable fault types
**When** the available faults are listed
**Then** at minimum: memory leak (gradual OOM), bad deploy (error rate spike), cascading failure (upstream → downstream), and scale-dependent latency (load-triggered)
**And** each fault type has a description and expected Beeper response

**Given** an active fault injection
**When** the admin triggers fault recovery (`make demo-recover`)
**Then** the fault is removed and the service returns to healthy state
**And** recovery can also happen automatically when Beeper applies a fix (at appropriate trust level)

### Story 8.3: Full Lifecycle Demonstration

As the **system**,
I want to demonstrate the full lifecycle: healthy → fault → detect → investigate → fix → prove → recover,
So that investors can see Beeper's complete value proposition in a single continuous flow.

**Acceptance Criteria:**

**Given** the demo application is healthy and Beeper is monitoring it
**When** a fault is injected
**Then** Beeper detects the anomaly, starts an investigation, identifies root cause, proposes a fix, verifies resolution, and creates a KB entry
**And** the full lifecycle completes in under 5 minutes (NFR7)

**Given** the full lifecycle is running
**When** viewed in the Beeper UI
**Then** each stage is visible in real-time: detection alert → investigation timeline streaming → fix proposal → verification metrics → KB entry creation
**And** the narrative is coherent and explainable to a non-technical audience

**Given** the demo application's trust level
**When** set to TL4 or TL5 for the demo
**Then** Beeper acts autonomously through the full lifecycle without human intervention
**And** each autonomous action is logged and visible in the UI for the audience

### Story 8.4: Scripted Repeatable Demo Scenarios

As **Diana**,
I want scripted, repeatable demo scenarios for investor presentations,
So that I can run a polished demo confidently without worrying about reliability or setup.

**Acceptance Criteria:**

**Given** a demo scenario script (e.g., `demo/scenarios/memory-leak.yaml`)
**When** Diana runs `make demo-scenario SCENARIO=memory-leak`
**Then** the scenario executes end-to-end: deploy (if needed) → healthy baseline → fault inject → wait for Beeper lifecycle → verify → cleanup
**And** console output narrates each stage with timestamps and status

**Given** a demo scenario
**When** run 10 consecutive times
**Then** all 10 runs complete successfully without failure (NFR18)
**And** each run produces consistent results (same detection time range, same root cause, same fix type)

**Given** multiple demo scenarios
**When** listed via `make demo-list`
**Then** available scenarios are shown with: name, description, duration estimate, and fault type
**And** scenarios can be run in sequence for extended demos (`make demo-all`)

**Given** the demo pytest harness
**When** CI runs the demo test suite
**Then** all scenarios pass as integration tests
**And** failures produce clear diagnostics (which stage failed, logs, metric snapshots)
