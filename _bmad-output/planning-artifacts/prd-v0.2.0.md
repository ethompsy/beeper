---
stepsCompleted:
  - step-01-init
  - step-02-discovery
  - step-03-success
  - step-04-journeys
  - step-05-domain
  - step-06-innovation
  - step-07-project-type
  - step-08-scoping
  - step-09-functional
  - step-10-nonfunctional
  - step-11-polish
  - step-12-complete
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

# Product Requirements Document - Beeper v0.2.0

**Author:** eric
**Date:** 2026-03-10

## Executive Summary

Beeper is an open-source agentic AI platform for Site Reliability Engineering, deployed as a K8s operator. It autonomously detects anomalies, investigates root causes, proposes evidence-backed fixes, and compounds operational knowledge — closing the full reliability loop that no existing tool addresses.

**Core Thesis:** As AI generates more code and infrastructure, human ability to maintain system context degrades irreversibly. Beeper is the necessary consequence of AI-driven development — inevitable infrastructure, not a nice-to-have.

**Target Users:** SRE teams (on-call engineers, team leads, developers, junior SREs, VP Engineering) operating K8s-based microservices architectures. Beeper serves as the always-on-call team member with perfect memory and continuity across shifts, incidents, and investigations.

**Key Differentiators:**

- **Fourth category creation** — not alerting, not observability, not runbook automation. Autonomous SRE Agent.
- **Self-designed experiments** — formulates and executes its own test plans to validate hypotheses
- **Human-language runbook execution** — zero-friction adoption, no DSL translation required
- **Compounding knowledge flywheel** — every investigation makes Beeper smarter about YOUR infrastructure. The flywheel is the moat.

**v0.2.0 Purpose:** Proof-of-existence release. The investor pitch says "Beeper is inevitable" — v0.2.0 IS the evidence. A purpose-built demo application showcases the full detect → investigate → fix → prove lifecycle on AI-complex infrastructure.

## Success Criteria

### User Success

| Persona | "Worth It" Moment | Measurable Outcome |
|---|---|---|
| Sam (On-Call SRE) | Approves a Beeper fix at 2am based on evidence trail alone — doesn't need to investigate | Time from page to resolution < 5 min with Beeper collaboration |
| Priya (Team Lead) | Graduates first service to Trust Level 3 — the system earned it | At least 1 service at TL3+ within 90 days of deployment |
| Marcus (Developer) | Merges an auto-PR and the service health feed confirms resolution | Auto-PR merge rate > 50% (merged without major revision) |
| Jordan (Junior SRE) | Handles a complex incident on second on-call rotation with Beeper guidance | Time to first independent resolution < 30 days |
| Diana (VP Eng) | Shows investor demo and gets follow-up meeting | Demo runs reliably, end-to-end, every time |
| On-Call Rotation | Shift handoff takes 30 seconds instead of 30 minutes | Handoff summary generated automatically, no Slack archaeology |

### Business Success

**The core thesis: Beeper is inevitable.**

v0.2.0 proves that thesis live. AI-driven applications and infrastructure create complexity only an AI agent can maintain. Beeper closes the full loop.

**3-month (demo-ready):**
- Investor demo runs reliably: fault injection → detection → investigation → evidence-backed fix → sandbox verification → resolution — on an AI-complex test application
- The demo tells the inevitability story: "this system was built by AI, modified by AI, and only Beeper can maintain the context to fix it"
- Full trust ladder visible (TL1-5) with behavior changing at each level
- SLO dashboard with customer impact scoring live

**6-month (community + investor traction):**
- GitHub stars and community adoption growing
- Seed round conversations initiated, backed by working demo
- Conference demo at SREcon or KubeCon
- Architecture spikes complete, Wave 2 features shipping

**12-month (pre-commercial validation):**
- Beta users on real production infrastructure
- Trust level progression data from real deployments
- KB flywheel metrics proving compounding intelligence
- SaaS architecture designed

### Technical Success

- All v0.1.0 tests continue passing (1,032 baseline)
- Demo application reliably produces and recovers from injected faults
- Auto-remediation pipeline functional: detect → investigate → propose fix → test → apply
- Trust level system correctly gates actions by confidence threshold
- SLO engine calculates burn rates and correlates customer impact in real-time
- Notification engine delivers to Slack, PagerDuty, email, webhook without false pages
- KB flywheel: investigations produce reusable entries that surface in subsequent investigations
- Collaboration: real-time investigation interaction without data loss or race conditions

### Measurable Outcomes

| Metric | Target | Validation Method |
|---|---|---|
| Demo reliability | 100% successful end-to-end runs | Scripted demo, repeated 10x |
| MTTR (demo env) | < 5 min from fault injection to verified resolution | Timed demo runs |
| KB reuse rate | > 0 (at least 1 entry referenced in a subsequent investigation) | Demo scenario with recurring fault |
| Trust graduation | TL1 → TL3 demonstrable in single demo session | Trust level progression script |
| Auto-PR accuracy | Fix resolves the injected fault, verified by sandbox test | Automated verification |
| False page rate | 0 in demo environment | Notification audit |
| Inevitability proof | Investor says "there's no other way to do this" | Qualitative — the demo tells the story |

## Product Scope

### MVP — v0.2.0 (All 4 Waves)

All 10 epics ship as v0.2.0, delivered in wave sequence:
- **Wave 1:** SLO Platform + Notification Engine (foundation)
- **Wave 2:** Trust & Anti-Noise + Auto-Remediation (the headline)
- **Wave 3:** Collaborative Investigations + KB Enhancement + Signal Expansion (intelligence)
- **Wave 4:** Developer Experience + Analytics & Gamification (delight)
- **Cross-cutting:** Investor demo application (the proof)
- **Prerequisites:** 3 architecture spikes (pluggable vector backend, WebSocket, agent framework)

### Growth Features (Post-MVP)

SaaS offering, multi-cluster support, advanced RBAC, community marketplace, security certifications. See [Post-MVP Features](#post-mvp-features) for detailed phasing.

### Vision (Future)

Beeper becomes the operating system for AI-era reliability — cross-organization learning, custom agent extensions, enterprise features, mobile companion. As AI generates more of the systems we operate, Beeper's context advantage compounds. The knowledge flywheel is the moat. Beeper is inevitable.

## User Journeys

### Journey 1: Sam — The 3am Page (Primary, Success Path)

**Opening Scene:** It's 3:12am. Sam's phone buzzes. PagerDuty: "Payment service latency spike — SLO burn rate critical." Sam groans, grabs the laptop, and opens Beeper's UI.

**Rising Action:** Beeper's already on it. The investigation pane shows: anomaly detected 47 seconds ago, investigation started immediately. Beeper has correlated the latency spike with a memory leak in the payment-processor pod, cross-referenced a similar incident from the KB three weeks ago, and identified the root cause — a connection pool exhaustion triggered by a deploy 22 minutes earlier. The evidence trail shows exact log lines, metric correlations, and the specific commit that introduced the regression.

**Climax:** Beeper proposes a fix: rollback the deployment, with a confidence score of 94%. It's already designed a test plan and — because Priya configured the payments service sandbox — has executed the rollback in staging and verified latency returned to baseline. Sam sees the green checkmark: "Fix verified in sandbox." Sam clicks "Approve."

**Resolution:** The rollback executes in production. SLO burn rate stabilizes within 90 seconds. Beeper auto-generates a KB entry linking the incident to the commit, the connection pool pattern, and the proven fix. Sam's total engagement time: 4 minutes. Sam goes back to sleep. The morning Slack channel shows a clean summary: "Incident resolved autonomously with human approval. Evidence trail available."

**Requirements revealed:** Real-time investigation UI, evidence presentation with references, confidence scoring, sandbox test execution, one-click approval, auto-KB generation, notification integration (PagerDuty), SLO burn rate alerting.

---

### Journey 2: Sam — The Unknown Failure (Primary, Edge Case)

**Opening Scene:** Sam gets paged for a service they've never touched — the recommendation engine, built by another team using a new ML framework. Sam has zero context.

**Rising Action:** Sam opens Beeper. The investigation is already deep — Beeper has correlated OOM kills with a spike in model inference latency, traced it to a memory leak in the embedding cache, and surfaced a KB entry from a similar pattern in a different service two months ago. But this time, the root cause is novel — the ML framework has a known issue with batch sizes over 512 that nobody on the team documented.

**Climax:** Beeper's confidence score is 72% — below the auto-fix threshold. It presents its hypothesis with evidence and a recommended test plan: "Reduce batch size to 256 in staging and measure memory growth over 15 minutes." Beeper can't fix this one alone, but it's given Sam everything needed to make the call.

**Resolution:** Sam follows the test plan, confirms the hypothesis, and applies the fix manually. Beeper logs the entire investigation, creates a KB entry with the confirmed root cause and proven fix, and tags it for the recommendation engine team. Next time this happens, Beeper's confidence will be 95%.

**Requirements revealed:** Investigation of unfamiliar services, KB cross-referencing, confidence scoring with thresholds, advisory test plans (no sandbox path), manual fix workflow, KB feedback loop, service tagging.

---

### Journey 3: Priya — The Trust Architect (Admin/Configuration)

**Opening Scene:** Priya's team has been running Beeper for 6 weeks. The payments service has had 14 investigations — 12 accurate, 2 corrected by the team. Priya opens the trust configuration dashboard.

**Rising Action:** She reviews the evidence: 86% accuracy on payments, all corrections fed back into the KB. The SLO dashboard shows payments has maintained 99.95% availability. She checks the notification audit — zero false pages in the last 3 weeks. The noise report shows signal-to-noise improving monthly.

**Climax:** Priya graduates the payments service from Trust Level 2 (notify + recommend) to Trust Level 3 (auto-fix with post-action review). She configures the confidence gate: only fixes with 90%+ confidence execute automatically. She sets up the sandbox requirement: all code fixes must pass sandbox verification before production apply.

**Resolution:** That night, Beeper resolves a connection timeout issue on payments autonomously — detected, investigated, fixed, sandbox-verified, applied, documented — without paging anyone. Priya reads the summary with her morning coffee and confirms: correct diagnosis, clean fix, evidence trail solid. She starts thinking about Trust Level 4.

**Requirements revealed:** Trust level configuration UI per service, accuracy tracking, SLO dashboard, notification audit/noise report, confidence gate configuration, sandbox requirement settings, post-action review workflow, trust graduation workflow.

---

### Journey 4: Marcus — The Auto-PR (Developer Path)

**Opening Scene:** Marcus is mid-sprint on the payments service. He gets a Slack notification from Beeper: "I found the cause of the intermittent timeout your team reported last sprint. PR #347 ready for review."

**Rising Action:** Marcus opens the PR. It's clean — follows his team's coding standards, small diff. But what catches his eye is the description: Beeper cites the exact production log correlation that proves the race condition, shows the 3 incidents over the past month that trace to this code path, includes the connection pool metrics that confirm the pattern, and links to the KB entry documenting the investigation chain. The PR also includes sandbox test results: "Ran 500 concurrent requests for 10 minutes — zero timeouts post-fix vs. 23 timeouts pre-fix."

**Climax:** Marcus reviews the code. The fix is exactly what he would have written — it adds a mutex around the pool checkout. But he couldn't reproduce it locally for months. Beeper caught it in production, proved it with data, and tested it at scale.

**Resolution:** Marcus merges the PR. The service health feed confirms: timeout rate drops to zero within the hour. He adds a comment: "Nice catch." He starts checking Beeper's service health feed for his other services, not just when PRs arrive. Trust builds incrementally.

**Requirements revealed:** Auto-PR generation, Repository CRD (coding standards, branch policies), evidence trail in PR description, KB entry linking, sandbox test results in PR, Slack notification for PRs, service health feed, PR-investigation linkage.

---

### Journey 5: Jordan — The Guided First Shift (Secondary, Onboarding)

**Opening Scene:** Jordan starts their third on-call shift. It's the first time they're primary. They open Beeper and ask: "What's the current state?"

**Rising Action:** Beeper delivers a handoff summary: "2 active investigations (auth-service latency trending up, minor; catalog-service error rate spike, resolved 2 hours ago by Sam, TL3 auto-fix). 1 item to watch: deploy scheduled for order-service at 6pm — I'll monitor SLO impact." Jordan has full context in 30 seconds.

**Climax:** At 8pm, the order-service deploy triggers an anomaly. Jordan sees Beeper's investigation in real time — it's correlating the deploy event with a 15% increase in 500 errors. Beeper surfaces a KB entry: "Similar pattern after order-service deploy last month — root cause was missing DB migration." Jordan sees the evidence, sees Beeper's recommended check, and runs the verification. Confirmed — migration was missed.

**Resolution:** Jordan applies the migration fix with Beeper's guidance. The investigation documented everything — Jordan's first independent resolution is clean, fast, and fully auditable. The next morning, Priya reviews and sees Jordan handled it like a veteran. Jordan learned more in one shift with Beeper than a month of reading docs.

**Requirements revealed:** Shift handoff summary, active investigation status, watch list, deploy correlation, KB surfacing during live investigations, guided resolution workflow, investigation documentation, onboarding experience.

---

### Journey 6: Diana — The Investor Demo (Executive/Evaluator)

**Opening Scene:** Diana is presenting to three potential seed investors. She opens Beeper's demo environment — a chaotic microservices application running in K8s, built to showcase the full lifecycle.

**Rising Action:** Diana narrates: "This application was designed by AI and deployed by AI. Watch what happens when things go wrong." She triggers a fault injection — a memory leak in the payment processor, the kind of bug that AI-generated code commonly produces. Beeper detects the anomaly within seconds. The investigation pane shows Beeper correlating memory growth with request latency, cross-referencing the deployment manifest, and identifying the root cause.

**Climax:** Beeper proposes a fix with 96% confidence. It designs a test: "Verify memory stabilization under load in sandbox." The sandbox test runs — green. Beeper opens a PR with the fix, evidence trail, and test results. Diana clicks "Apply." The application recovers. Total time: 3 minutes. Diana says: "This is what AI-maintained reliability looks like. As AI builds more of our systems, only AI can maintain the context to fix them. Beeper is inevitable."

**Resolution:** The investors ask questions. Diana pulls up the SLO dashboard showing customer impact correlation, the KB showing compounding knowledge, the trust level configuration showing graduated autonomy. One investor asks: "What happens if we don't adopt something like this?" Diana: "Your SRE team falls further behind every time AI ships new code. The context gap only grows."

**Requirements revealed:** Demo application with fault injection, scriptable demo scenarios, full lifecycle visibility in UI, investor-friendly presentation flow, SLO dashboard, KB visualization, trust level demonstration.

---

### Journey Requirements Summary

| Journey | Key Capabilities Revealed |
|---|---|
| Sam — 3am Page | Real-time investigation, evidence trail, confidence scoring, sandbox execution, one-click approval, SLO alerting, auto-KB |
| Sam — Unknown Failure | Cross-service investigation, KB cross-reference, advisory test plans, manual fix workflow, feedback loop |
| Priya — Trust Architect | Trust level config UI, accuracy tracking, SLO dashboard, noise report, confidence gates, sandbox requirements |
| Marcus — Auto-PR | Auto-PR generation, Repository CRD, evidence in PR, sandbox test results, Slack notification, service health feed |
| Jordan — First Shift | Shift handoff summary, deploy correlation, KB surfacing, guided resolution, investigation documentation |
| Diana — Investor Demo | Demo app, fault injection, scriptable scenarios, full lifecycle UI, SLO dashboard, KB visualization |

**Cross-cutting capabilities:** Notification engine (Slack, PagerDuty), KB flywheel (create → reuse → improve), trust system (TL1-5), SLO-driven prioritization, collaboration (real-time + async).

## Domain-Specific Requirements

Domain requirements define policies and constraints specific to the Agentic AI for SRE space. These intentionally overlap with Functional Requirements (capability contract) and Non-Functional Requirements (measurable targets) — this traceability ensures domain-critical concerns are addressed at every level.

### Safety & Trust

- Trust level system must be airtight — misconfigured trust levels cannot lead to unauthorized autonomous actions
- Confidence thresholds must be calibrated with conservative defaults (high threshold, team dials down as trust grows)
- Every action Beeper takes must be rollback-capable — no irreversible autonomous actions without explicit human approval
- False positive auto-fix is treated as a critical bug — equivalent to a production outage caused by tooling

### Security

- Beeper requires broad cluster access (logs, metrics, deployments, pod management) — attack surface must be minimized through least-privilege RBAC
- Repository access for auto-PRs requires scoped credentials (per-repo tokens, not org-wide)
- API keys for Slack, PagerDuty, LLM providers stored in K8s Secrets with encryption at rest
- Trust level configuration restricted to authorized roles — not every team member can dial to TL5
- Investigation data may contain sensitive information (PII in logs, credentials in error messages) — scrub before sending to LLM providers

### AI-Specific

- LLM hallucination risk in root cause analysis — evidence trail with specific references (log lines, metrics, KB entries) provides auditability but confidence scoring must reflect uncertainty
- Model provider dependency — Beeper must gracefully degrade if LLM provider is unavailable (queue investigations, fall back to pattern matching, alert humans)
- Tiered model strategy (screening → investigation → remediation) must balance cost, latency, and accuracy
- KB data quality — feedback loop must filter and weight entries by validation status (human-confirmed vs. AI-generated vs. corrected)

### Operational

- Beeper must not become a single point of failure — if Beeper goes down, existing alerting, monitoring, and manual incident response must continue unaffected
- Resource consumption — LLM inference costs tracked and budgetable; investigation depth bounded by configurable limits
- Sandbox environment isolation must be provable — a sandbox test must never leak state, traffic, or data into production
- Demo environment must be fully isolated from any real infrastructure

### Risk Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| False positive auto-fix | Beeper causes outage | Conservative confidence defaults, sandbox verification required, rollback on any degradation |
| LLM provider outage | Investigations stall | Graceful degradation, queue-and-retry, human escalation |
| KB poisoning (bad data) | Future investigations corrupted | Human validation status, correction tracking, weighted trust in KB entries |
| Credential exposure | Security breach | Least-privilege RBAC, scoped tokens, secret encryption, PII scrubbing |
| Runaway resource consumption | Cost spike | Configurable investigation depth limits, LLM cost tracking, budget alerts |
| Sandbox leak to production | Data corruption or outage | Network isolation, separate namespaces, verification before sandbox creation |

## Innovation & Novel Patterns

### Detected Innovation Areas

1. **Fourth Category: Autonomous SRE Agent** — Beeper doesn't compete in existing categories (alerting, observability, runbook automation). It creates a new one by closing the full loop: detect → investigate → hypothesize → fix → prove → learn. No existing tool does this.

2. **Self-Designed Experiments** — Beeper formulates its own test plans to validate hypotheses. Existing tools execute human-written playbooks. Beeper designs the experiment, and when a sandbox is available, executes it autonomously.

3. **Human-Language Runbook Execution** — Teams point Beeper at existing plain-language runbooks — no DSL translation, no YAML rewrite, no playbook migration. Zero-friction adoption that Shoreline and Rundeck can't match.

4. **The Inevitability Thesis** — Market-timing insight: as AI generates more code and infrastructure, human ability to maintain system context degrades irreversibly. Beeper isn't an optional productivity tool — it's the necessary consequence of AI-driven development. This positions Beeper as inevitable infrastructure, not a nice-to-have.

5. **Compounding Knowledge Flywheel** — Every investigation makes Beeper smarter about the specific infrastructure it operates on. This isn't a generic AI model — it's personalized, compounding operational intelligence that becomes harder to replace over time. The flywheel is the moat.

### Market Context & Competitive Landscape

| Competitor Category | Examples | Innovation Gap Beeper Fills |
|---|---|---|
| Alert + Triage | PagerDuty, Rootly, FireHydrant | These notify. Beeper investigates, fixes, and proves. |
| Observability | Datadog, Grafana, New Relic | These visualize. Beeper reasons and acts. |
| Runbook Automation | Shoreline, Rundeck | These require DSLs and human-authored playbooks. Beeper reads English and innovates beyond runbooks. |
| AIOps | Moogsoft, BigPanda | These correlate alerts. Beeper performs deep multi-layer investigation and generates fixes. |

No existing tool combines autonomous investigation, self-designed experiments, human-language runbook execution, auto-remediation with evidence, and compounding knowledge base. Beeper closes the full loop.

### Validation Approach

| Innovation | Validation Method | Success Signal |
|---|---|---|
| Full-loop autonomy | Investor demo: fault → fix → proof in < 5 min | Investor says "there's no other way" |
| Self-designed experiments | Demo scenario with sandbox test execution | Test plan is coherent, test passes, fix is verified |
| Human-language runbooks | Seed Beeper with real team runbooks, measure execution accuracy | Beeper follows runbook steps correctly without DSL translation |
| Inevitability thesis | Demo on AI-generated application specifically | Complexity is visibly beyond human ability to maintain |
| Knowledge flywheel | Recurring fault scenario in demo | Second occurrence resolved faster with KB reuse |

### Risk Mitigation

| Innovation Risk | Fallback |
|---|---|
| Full-loop autonomy too ambitious for v0.2.0 | Trust levels gate risk — TL1 (advisory only) is always safe, teams opt into autonomy |
| Self-designed experiments produce bad tests | Sandbox isolation prevents production impact; human review at lower trust levels |
| Human-language runbook parsing unreliable | Structured runbook format as progressive enhancement; plain-language as best-effort |
| Inevitability thesis doesn't resonate with investors | Fall back to concrete ROI story: MTTR reduction, fewer pages, developer time saved |
| KB compounds bad data | Validation status tracking, human correction weighting, confidence decay on unverified entries |

## SaaS B2B Specific Requirements

### Project-Type Overview

Beeper v0.2.0 is an open-source B2B platform deployed as a single-instance-per-cluster K8s application — collaborative AI SRE agent with web UI, REST APIs, and outbound integrations. Commercial SaaS deferred; v0.2.0 targets investor demo readiness.

### Technical Architecture Considerations

**Tenant Model:** Single-tenant, single-cluster. One Beeper instance manages one K8s cluster. Multi-cluster and multi-tenant architecture deferred to v0.3.0+. No tenant isolation, shared resource pools, or cross-tenant data concerns in v0.2.0.

**Permission Model (2-tier):**

| Role | Capabilities |
|---|---|
| **Admin** | Configure trust levels per service, manage ServiceLevel and Repository CRDs, set confidence gates, manage sandbox settings, access all dashboards and reports, manage user access |
| **User** | View investigations, collaborate during incidents, approve/reject Beeper-proposed fixes (within trust level), view SLO dashboard, configure NotificationChannel CRDs and notification rules, interact with KB, review auto-PRs |

Admin controls the safety envelope (trust levels, confidence gates, what Beeper is allowed to do). Users control the communication layer (how and when they get notified) plus operational interaction (investigations, approvals, KB). Jordan can set up a new Slack channel integration or adjust notification preferences without needing Priya.

**Subscription Tiers:** Not applicable for v0.2.0. Open-source community edition only. No billing, metering, or tier gating. All features available to all users.

### Integration Requirements

| Integration | Type | Protocol | v0.2.0 Scope |
|---|---|---|---|
| **Slack** | Notification + ChatOps | Slack API (Bot Token) | Rich messages, threads, @mentions, action buttons |
| **PagerDuty** | Escalation | PagerDuty Events API v2 | Create/acknowledge/auto-resolve incidents, bidirectional |
| **Email** | Notification | SMTP | Alert digests, investigation summaries |
| **Webhooks** | Generic integration | HTTP POST | Trigger CD pipelines, Jira, status pages |
| **Git Repositories** | Auto-PR | Git provider API (GitHub/GitLab) | Clone, branch, commit, open PR with evidence |
| **LLM Providers** | AI inference | Provider-specific APIs | Tiered model strategy (screening → investigation → remediation) |
| **K8s API** | Cluster operations | K8s API server | Pod management, deployments, CRDs, events, logs, metrics |
| **Qdrant** | Vector DB | gRPC/REST | KB storage, semantic search, investigation vectors |

No additional integrations for v0.2.0. OTel collector compatibility, Jira native integration, and other signal sources deferred to Wave 3+ or v0.3.0.

### Implementation Considerations

- **Existing v0.1.0 architecture** is the foundation: Rust K8s operator + Python investigator + Flask/HTMX UI + Qdrant. v0.2.0 extends, not replaces.
- **CRD additions:** `ServiceLevel`, `NotificationChannel`, `Repository` — all managed by the Rust operator
- **WebSocket spike required** before collaboration features (Wave 3) — HTMX SSE may not be sufficient for real-time bidirectional interaction
- **Agent framework spike required** before auto-remediation (Wave 2) — investigator needs multi-step tool-use capability
- **Admin/user permission enforcement** needed across all APIs and UI routes — implement early in Wave 1 as foundation
- **Integration credentials** stored as K8s Secrets, referenced by CRDs — no credential storage in Beeper's database

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach:** Proof-of-Existence Release

v0.1.0 proved the concept — autonomous anomaly detection and investigation works. v0.2.0 proves the *thesis*: an AI agent can close the full detect-investigate-fix-prove loop, and this capability is inevitable as AI-generated systems grow beyond human ability to maintain.

"Beeper is inevitable" sounds too good to be true without evidence. v0.2.0 IS the evidence. The demo is the product.

**Resource Requirements:** Solo developer (eric) with AI-assisted development. Architecture spikes complete before the features they inform. Waves ship sequentially — each builds on the previous.

### MVP Feature Set (v0.2.0 — All 4 Waves)

**Core User Journeys Supported:**

| Journey | Waves Required | Demo-Critical? |
|---|---|---|
| Sam — 3am Page (success path) | 1, 2, 3 | Yes — this IS the demo |
| Sam — Unknown Failure (edge case) | 1, 2, 3 | Yes — shows advisory mode |
| Priya — Trust Architect | 1, 2 | Yes — shows graduated autonomy |
| Marcus — Auto-PR | 2 | Yes — shows code-level remediation |
| Jordan — Guided First Shift | 3 | Yes — shows continuity/handoff |
| Diana — Investor Demo | All | Yes — the wrapper for everything |

**Must-Have Capabilities (by wave):**

**Wave 1 — Foundation:**
- ServiceLevel CRD, SLO burn rate calculation, customer impact scoring
- SLO compliance dashboard
- NotificationChannel CRD, Slack integration, PagerDuty integration, email, webhooks
- Notification rules engine with customer impact routing
- Admin/user permission model (2-tier)

**Wave 2 — Trust + Action:**
- Architecture spikes complete (agent framework, WebSocket, pluggable vector)
- Trust levels 1-5 per service with confidence gates
- Adaptive alert thresholds, customer impact weighting
- Repository CRD, auto-PR generation with evidence trails
- Human-language runbook execution
- Advisory test plan (always), sandbox test execution (when available)
- Fix verification loop

**Wave 3 — Intelligence:**
- Real-time investigation collaboration (WebSocket-based)
- Evidence presentation with references
- Shift handoff summaries
- KB bi-directional links, investigation-to-KB pipeline
- Unified investigation timeline, deploy correlation
- Topology-aware investigation

**Wave 4 — Delight:**
- Keyboard-first UI (Cmd+K)
- Investigation workflow states
- Remediation tracking
- Service health feed improvements
- Reliability score per service
- MTTR trends, customer impact trends, trust progression dashboards

**Demo Application (cross-cutting):**
- Chaotic microservices app in K8s
- Configurable fault injection
- Scriptable end-to-end demo scenarios
- Full lifecycle: healthy → fault → detect → investigate → fix → prove → recover

### Nice-to-Have (ship if time allows, cut first if tight)

| Feature | Wave | Why Deferrable |
|---|---|---|
| Onboarding quests | 4 | Polish, not proof |
| Team streaks & gamification | 4 | Delight, not evidence |
| KB contribution scores / leaderboard | 4 | Community feature, not demo-critical |
| AI accuracy XP | 4 | Interesting but not investor-facing |
| Notification digest mode | 1 | Convenience, not capability |
| Custom views & saved filters | 3 | Personalization, not proof |

### Post-MVP Features

**Phase 2 (v0.3.0 — Scale & Commercial):**
- SaaS offering with managed hosting and metered billing
- Multi-cluster and multi-environment support
- Advanced RBAC with team-level permissions and approval chains
- Community marketplace for runbooks and integrations
- Security certifications (SOC2)
- Multi-tenant architecture

**Phase 3 (v0.4.0+ — Platform):**
- Third-party integrations ecosystem
- Custom agent extensions for domain-specific investigators
- Cross-organization anonymized learning
- Mobile companion app
- Enterprise features: audit trails, compliance reporting, SSO

### Risk Mitigation Strategy

**Technical Risks:**

| Risk | Impact | Mitigation |
|---|---|---|
| Architecture spikes reveal blockers | Wave 2-3 features delayed | Spikes run first; fallback designs identified before committing |
| WebSocket adds significant complexity | Collaboration features delayed | HTMX SSE as fallback for one-directional updates; WebSocket for full bidirectional |
| Agent framework redesign too large | Auto-remediation delayed | Incremental extension of existing investigator; full agent framework as progressive enhancement |
| Demo app too complex to maintain | Demo unreliable | Keep demo app minimal — 3-4 microservices, 2-3 fault scenarios, scriptable |

**Market Risks:**

| Risk | Impact | Mitigation |
|---|---|---|
| Inevitability thesis doesn't land | Investor pitch falls flat | Fallback to concrete ROI: MTTR reduction, fewer pages, developer hours saved |
| Competitors ship similar capabilities | Differentiation erodes | Open-source moat + compounding KB flywheel = hard to replicate |
| AI trust backlash in SRE community | Adoption resistance | Graduated autonomy + evidence-first = trust is earned, not assumed |

**Resource Risks:**

| Risk | Impact | Mitigation |
|---|---|---|
| Solo developer bandwidth | Waves ship slower than planned | Wave sequence provides natural cut points — ship what's done, demo what's ready |
| AI-assisted development hits limits | Implementation slows | v0.1.0 proved the AI-assisted approach works; architecture spikes de-risk complexity early |
| Scope too ambitious for timeline | Not all waves complete | Nice-to-have list provides clear cut candidates; demo can work with Waves 1-3 if Wave 4 slips |

## Functional Requirements

### SLO & Customer Impact (Wave 1)

- FR1: Admins can define SLIs and SLO targets per service via ServiceLevel CRD
- FR2: System can calculate SLO burn rates in real-time from ingested metrics
- FR3: System can trigger investigations when SLO burn rate exceeds configured thresholds
- FR4: System can score anomalies by customer impact using SLO data rather than static severity labels
- FR5: Admins can define error budget policies that trigger notifications or deployment freezes
- FR6: Users can view SLO compliance, burn rate trends, and error budgets on a dashboard
- FR7: System can prioritize investigations by SLO impact severity

### Notification & Integration (Wave 1)

- FR8: Users can configure outbound notification channels via NotificationChannel CRD (Slack, PagerDuty, email, webhook)
- FR9: Users can define notification routing rules based on severity, service, SLO state, and time of day
- FR10: System can send rich Slack messages with threads, @mentions, and action buttons
- FR11: System can create, acknowledge, and auto-resolve PagerDuty incidents bidirectionally
- FR12: System can send email alert digests and investigation summaries
- FR13: System can trigger webhooks to external systems (CD pipelines, Jira, status pages)
- FR14: Users can configure quiet hours and escalation tiers that respect on-call schedules
- FR15: System can justify every notification with evidence — false pages are tracked as bugs

### Trust & Autonomy (Wave 2)

- FR16: Admins can configure trust levels (1-5) per service, controlling Beeper's autonomy from advisory to fully autonomous
- FR17: System can gate actions by confidence threshold — only act when evidence meets the configured trust level's requirements
- FR18: System can adapt alert thresholds based on investigation outcome feedback from SREs
- FR19: Users can provide one-click investigation feedback (accurate / inaccurate / not-an-issue)
- FR20: Admins can view a noise report showing signal-to-noise ratio and false page trends
- FR21: System can weight escalation urgency by confirmed customer impact rather than theoretical severity
- FR22: Admins can configure confidence gate thresholds per trust level

### Auto-Remediation (Wave 2)

- FR23: Admins can register code repositories via Repository CRD with branch policies and coding standards
- FR24: System can execute human-language runbooks without requiring DSL translation
- FR25: System can generate auto-PRs with full evidence trails (log correlation, root cause analysis, production conditions)
- FR26: System can always produce an advisory test plan describing how to verify a hypothesis
- FR27: System can design sandbox-specific tests and execute them when a sandbox environment is available
- FR28: System can verify that a fix resolves the issue by monitoring post-fix metrics
- FR29: System can gate remediation actions to the configured trust level and confidence tier
- FR30: System can link PRs to investigations with full audit trail (anomaly → investigation → fix → verification)
- FR31: System can accumulate proven fixes in the KB for future reference

### Collaborative Investigation (Wave 3)

- FR32: Users can interact with Beeper in real-time during active investigations
- FR33: System can present evidence with references to specific metrics, logs, and prior KB entries
- FR34: Users can annotate, redirect, and comment on active investigations
- FR35: Users can approve or reject Beeper-proposed fixes within their permission level
- FR36: System can generate shift handoff summaries with active investigations, resolved incidents, and items to watch
- FR37: System can surface relevant past KB entries during live investigations

### Knowledge Base Enhancement (Wave 3)

- FR38: System can create KB entries automatically from resolved investigations
- FR39: System can link KB entries bi-directionally to investigations and related entries
- FR40: System can provide per-service knowledge views through service catalog integration
- FR41: System can weight KB entries by validation status (human-confirmed, AI-generated, corrected)
- FR42: Users can review, edit, and correct Beeper's KB entries as a feedback mechanism

### Signal & Observability (Wave 3)

- FR43: System can display a unified investigation timeline correlating logs, metrics, deploys, and K8s events
- FR44: System can correlate anomalies with recent deployments ("anomaly started 4 min after deploy #847")
- FR45: System can discover and display service dependency topology
- FR46: System can ingest and correlate change events (config changes, scaling, DNS, certs)

### Developer Experience (Wave 4)

- FR47: Users can navigate the UI via keyboard shortcuts and a command palette (Cmd+K)
- FR48: System can track investigations through workflow states (detected → investigating → resolved → verified)
- FR49: Users can track remediation progress from detection through fix verification
- FR50: Users can view per-service health feeds with recent investigations, SLO status, and trends

### Analytics & Reporting (Wave 4)

- FR51: System can calculate a reliability score per service (composite of SLO compliance, incident frequency, MTTR)
- FR52: Users can view MTTR trends, customer impact trends, and trust progression dashboards
- FR53: Diana can view investor-ready reports derived from Beeper's operational data

### Demo Application (Cross-cutting)

- FR54: System can deploy a purpose-built chaotic microservices application in K8s alongside Beeper
- FR55: Admins can trigger configurable fault injections (memory leak, bad deploy, cascading failure, scale-dependent issues)
- FR56: System can demonstrate the full lifecycle: healthy → fault → detect → investigate → fix → prove → recover
- FR57: System can run scripted, repeatable demo scenarios for investor presentations

### Platform & Security (Foundation)

- FR58: System can enforce 2-tier permissions (admin/user) across all APIs and UI routes
- FR59: System can store integration credentials as K8s Secrets with encryption at rest
- FR60: System can scrub sensitive information (PII, credentials) from data before sending to LLM providers
- FR61: System can gracefully degrade if LLM provider is unavailable (queue investigations, escalate to humans)
- FR62: System can rollback any autonomous action if post-action metrics show degradation
- FR63: System can operate without becoming a single point of failure — existing alerting continues if Beeper is down

## Non-Functional Requirements

### Performance

| Requirement | Target | Rationale |
|---|---|---|
| NFR1: Anomaly-to-investigation latency | < 30 seconds from detection to investigation start | Sam needs Beeper already working when he opens the laptop |
| NFR2: UI response time | < 2 seconds for all user interactions | Incident response demands fast navigation |
| NFR3: LLM screening round-trip | < 10 seconds | Tiered model strategy — screening must be fast to triage volume |
| NFR4: LLM deep investigation round-trip | < 30 seconds per reasoning step | Acceptable for thorough root cause analysis |
| NFR5: Real-time collaboration updates | < 500ms delivery (WebSocket) | Live investigation interaction requires near-instant feedback |
| NFR6: SLO burn rate calculation | < 5 second refresh cycle | Dashboard must reflect current state during active incidents |
| NFR7: Demo full lifecycle | < 5 minutes fault-to-resolution | Investor demo must be tight and compelling |

### Security

| Requirement | Target | Rationale |
|---|---|---|
| NFR8: Cluster RBAC | Least-privilege per operation — no cluster-admin | Minimize blast radius of compromised Beeper instance |
| NFR9: Repository credentials | Scoped per-repo tokens, never org-wide | Auto-PR access limited to registered repositories only |
| NFR10: Secret storage | K8s Secrets with encryption at rest | No credential storage in Beeper's own database |
| NFR11: PII/credential scrubbing | Zero sensitive data sent to LLM providers | Logs and error messages scrubbed before LLM context assembly |
| NFR12: Trust level access control | Admin-only for trust level and confidence gate configuration | Prevents unauthorized escalation of Beeper's autonomy |
| NFR13: Sandbox isolation | Network-isolated namespace, provably no production data leakage | Sandbox tests must never affect production state |

### Reliability

| Requirement | Target | Rationale |
|---|---|---|
| NFR14: Non-SPOF operation | Existing alerting/monitoring fully functional if Beeper is down | Beeper enhances — never replaces — existing incident response |
| NFR15: LLM provider degradation | Queue investigations + escalate to humans within 60 seconds of provider failure | Investigation stall cannot become silent failure |
| NFR16: Autonomous action rollback | Any auto-applied fix reversible within 60 seconds | False positive auto-fix is treated as critical bug |
| NFR17: Data integrity | Zero investigation data loss during component restart or upgrade | Investigation continuity through operator lifecycle events |
| NFR18: Demo reliability | 10 consecutive end-to-end demo runs without failure | Diana cannot demo a flaky system to investors |

### Scalability

| Requirement | Target | Rationale |
|---|---|---|
| NFR19: Concurrent investigations | 50+ active investigations without performance degradation | Cluster-wide incident scenarios trigger many simultaneous investigations |
| NFR20: KB capacity | 10,000+ entries with < 2 second semantic search | Compounding flywheel requires KB that grows without slowing down |
| NFR21: ServiceLevel CRDs | 100+ active CRDs per cluster | Enterprise clusters have many services |
| NFR22: Notification throughput | 1,000+ events/hour processed without drops | Cascading incidents generate notification storms |
