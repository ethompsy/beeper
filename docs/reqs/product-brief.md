---
stepsCompleted: [1, 2, 3, 4, 5]
inputDocuments:
  - brainstorming-session-2026-03-08.md
  - product-brief-beeper-2026-01-27.md
  - project-overview.md
  - integration-architecture.md
  - source-tree-analysis.md
  - development-guide.md
  - deployment-guide.md
  - api-contracts.md
  - index.md
date: 2026-03-09
author: eric
---

# Product Brief: Beeper v0.2.0

## Executive Summary

**As software is built, tested, and deployed by AI on infrastructure designed and implemented by AI, no human will be able to maintain the context. Beeper is inevitable.**

Beeper v0.2.0 evolves from an autonomous anomaly detection platform into a **collaborative AI SRE agent** — a reliable sidekick that's already halfway through the investigation when you get paged. Where v0.1.0 observes and reports, v0.2.0 collaborates, proves, and acts.

Beeper operates in two modes: **Incident Mode** — decisive action in the fire (detect, investigate, correlate, fix) — and **Learning Mode** — rigorous post-incident work (RCA, hypothesis testing, proof, KB update, prevention). Both feed a compounding knowledge flywheel that makes Beeper smarter about your specific infrastructure with every incident.

The release is anchored by four product pillars — a cohesive investigative experience, real-time human-AI collaboration, proactive remediation with graduated trust, and an SLO-driven customer impact lens — plus a purpose-built demo environment that showcases the full detect-to-fix lifecycle for investors and evaluators.

The core bet: SRE teams don't need another dashboard. They need an AI colleague that earns trust through transparency, acts decisively during incidents, and gradually takes on more responsibility as confidence grows.

---

## Core Vision

### Problem Statement

SRE teams can't trust AI to act because AI can't show its work.

Modern infrastructure generates overwhelming observability data, but when an outage hits, engineers still scramble across dozens of dashboards, correlate signals manually, and apply fixes under pressure based on instinct. Existing tools automate alerting and visualization, but the critical cognitive work — investigation, root cause analysis, and verified remediation — remains entirely manual.

As AI increasingly generates the code, configurations, and infrastructure that teams operate, human ability to maintain full system context is degrading. The complexity curve is outpacing SRE headcount. This context gap is accelerating, and only an AI agent embedded in the operational loop can close it.

### Problem Impact

- **The Context Gap** — AI-generated systems are growing faster than human ability to understand them; SRE teams are falling behind
- **Trust deficit** — Teams won't adopt AI tools that can't show their reasoning or prove their fixes are safe
- **MTTR ceiling** — Humans still perform all remediation, capping resolution speed regardless of detection quality
- **Alert fatigue** — Equal attention to all signals regardless of customer impact erodes trust in tooling
- **Recurrent incidents** — Same problems resurface because root causes are patched, not proven fixed
- **Knowledge silos** — One engineer's hard-won insight during an outage doesn't transfer

### Why Existing Solutions Fall Short

| Category | Examples | Where They Stop |
|---|---|---|
| Alert + Triage | PagerDuty, Rootly, FireHydrant | Humans still investigate |
| Dashboards + Correlation | Datadog, Grafana | Humans still connect the dots |
| Runbook Automation | Shoreline, Rundeck | Humans still write the playbooks (in DSLs) |

No existing tool closes the full loop: **detect → investigate → hypothesize → fix → prove → learn**. None design their own experiments. None can follow human-language runbooks without requiring translation to a DSL. None operate as a collaborative partner that compounds knowledge over time. Beeper creates a **fourth category: Autonomous SRE Agent.**

### Proposed Solution

Beeper v0.2.0 becomes a collaborative AI SRE agent — specifically designed to support SRE work in the heat of an outage. It operates in two complementary modes:

**Incident Mode (in the fire):** Beeper acts decisively. It can follow human-language runbooks, innovate based on its growing understanding of the system through the KB, collaborate in real-time on findings and RCA, and — at full trust — apply the fix directly.

**Learning Mode (after the fire):** Beeper is rigorous. It conducts root cause analysis, designs test plans to validate hypotheses, and when a sandbox environment is available, executes those tests and measures results to prove fixes before they're promoted.

**The trust mechanism:**

| Environment | Beeper Provides |
|---|---|
| Always (no sandbox) | Evidence trail with references + confidence score + advisory test plan |
| With sandbox | All of the above + sandbox-specific test design + auto-execute + verified fix |

The advisory test plan is always present — Beeper always tells you how to validate its thinking, even in locked-down environments. The sandbox unlocks execution. Trust levels (1-5) let teams dial autonomy from advisory to fully autonomous at their own pace.

The platform also introduces SLO-driven customer impact scoring (replacing severity-label guesswork), a notification engine that justifies every interruption, and a purpose-built demo application showcasing the full lifecycle for investors.

### Key Differentiators

| Level | Differentiator |
|---|---|
| **Thesis** | AI-maintained systems require AI-maintained reliability. Beeper is inevitable. |
| **Moat** | Compounding knowledge flywheel — every incident makes Beeper smarter about YOUR infrastructure |
| **Capability** | Dual-mode agent: decisive in the fire, rigorous in the post-mortem |
| **Adoption** | Follows human-language runbooks — zero-friction onboarding, no DSL translation |
| **Trust** | Graduated autonomy from advisory to autonomous, at the team's pace |
| **Proof** | Self-designed experiments that validate fixes with evidence |
| **Openness** | Fully open source — complete transparency into reasoning and decisions |

## Target Users

### Primary Users

**Sam — On-Call SRE**
- **Role:** Mid-level SRE, rotates on-call weekly
- **v0.2.0 evolution:** Sam no longer just observes Beeper investigating — they collaborate in real-time during incidents. Beeper surfaces evidence with references, proposes fixes with confidence scores, and presents advisory test plans. Sam reviews, approves, or redirects. As trust grows, Sam approves less and reviews more. The sandbox test results give Sam the confidence to let go.
- **Success moment:** Sam approves a Beeper-proposed fix at 2am after reviewing the evidence trail and sandbox test results. Total time from page to resolution: 4 minutes. Sam goes back to sleep.

**Priya — SRE Team Lead**
- **Role:** Senior SRE / Team Lead overseeing a team of 6
- **v0.2.0 evolution:** Priya is the trust architect. She configures trust levels per service, defines SLOs that drive customer impact scoring, sets up notification channels (Slack, PagerDuty, email), and decides when to graduate Beeper's autonomy. She reviews Beeper's auto-PRs for systemic fixes and uses the SLO dashboard to replace narrative-based postmortems with data.
- **Success moment:** Priya raises Beeper to Trust Level 4 on the payments service after reviewing three months of verified fixes. The next incident is resolved autonomously, documented, and she reads about it with her morning coffee.

**Marcus — Product Team Developer**
- **Role:** Backend developer on the payments service team
- **v0.2.0 evolution:** Marcus now receives auto-PRs from Beeper with full evidence trails — the exact log correlation, the production conditions that triggered the bug, and a test plan he can run to verify. The PRs follow his team's coding standards. He's been watching the service health feed for weeks, so the PR isn't a surprise — it's a confirmation of what he already suspected.
- **Success moment:** Marcus merges a Beeper PR that fixes an intermittent connection pool exhaustion his team couldn't reproduce. The PR includes sandbox test results proving the fix holds under load.

### Secondary Users

**Jordan — Junior SRE / New Hire**
- **Role:** Joined the SRE team 3 months ago
- **v0.2.0 evolution:** Collaboration features transform Jordan's on-call experience. Instead of floundering alone at 3am, Beeper is the senior engineer in the room — showing its reasoning, surfacing relevant past incidents from the KB, and suggesting next steps. Jordan learns by working alongside Beeper. The KB is now a structured learning platform, not a static wiki.
- **Success moment:** Jordan handles a complex cascading failure on their second on-call rotation because Beeper guided the investigation, surfaced a similar past incident, and proposed a fix with evidence. The team lead reviews the incident and sees Jordan handled it like a veteran.

**Diana — VP of Engineering**
- **Role:** Oversees all engineering, reports to CTO
- **v0.2.0 evolution:** Diana now has SLO compliance dashboards, customer impact trends, and MTTR analytics — all generated from Beeper's operational data. She's also the audience for the investor demo, watching the full detect-to-fix lifecycle in real time.
- **Success moment:** Diana shows the board that customer-impacting incidents are down 40% and MTTR dropped by 60% — with data she didn't have to compile. The board approves the next funding round.

**Alex — Performance / Reliability Engineer**
- **Role:** Designs load tests and chaos engineering experiments
- **v0.2.0 evolution:** Beeper's self-designed test plans are Alex's dream input — real production failure patterns with specific conditions for reproduction, including scale-dependent triggers. Alex mines these to design chaos tests grounded in actual production behavior rather than theoretical scenarios.
- **Success moment:** Alex builds a chaos test suite directly from Beeper's documented failure patterns. It catches two regressions in staging that would have been P1 incidents in production.

### The On-Call Rotation (Collective User)

**The rotation as a team — with Beeper as continuity glue.**

Beeper is always on-call. It doesn't go home, doesn't forget, doesn't lose context between shifts. When Sam hands off to Jordan at 6pm, Beeper carries forward:
- Active investigation state and reasoning chain
- Full context of the last 24 hours of anomalies and resolutions
- Which issues are trending, which are resolved, which need watching
- What was tried, what worked, what didn't

The on-call rotation stops being a chain of isolated shifts and becomes a **continuous operational thread** with Beeper as the persistent memory. Shift handoffs go from "here's a wall of text in Slack" to "Beeper, catch Jordan up."

**Success moment:** Jordan starts their on-call shift and asks Beeper for a handoff summary. In 30 seconds, Jordan has full context on two active investigations, one resolved incident, and a trending metric to watch. No Slack archaeology required.

### User Journey

**Discovery:** SRE teams find Beeper through the open-source community, word of mouth at SREcon/KubeCon, or the investor demo video showing the full detect-to-fix lifecycle. The "AI SRE teammate" pitch resonates immediately with anyone who's been paged at 3am.

**Onboarding:** Team points Beeper at their log/metric feeds, defines SLOs, and optionally seeds it with existing runbooks (in plain language — no DSL required). Beeper begins in observation mode at Trust Level 1. Value starts immediately through investigation documentation and service health insights.

**Core Usage:** Beeper runs continuously in dual mode. In the fire: real-time collaboration, evidence-backed fixes, decisive action. After the fire: RCA, test plan design, KB updates, auto-PRs for systemic fixes. SRE leads configure trust levels and review the SLO dashboard weekly. The knowledge flywheel compounds daily.

**Success Moment:** The first overnight incident that Beeper resolves autonomously — investigated, fixed, tested in sandbox, documented — without waking anyone. The morning review confirms it was handled correctly.

**Long-term:** Beeper becomes the institutional memory and always-on teammate. New hires onboard through its KB. Developers trust its PRs. The on-call rotation operates as a continuous thread. Leadership makes data-driven reliability decisions. The team shifts from reactive to proactive. Beeper is the teammate nobody wants to lose.

## Success Metrics

### North Star Metric

**Incidents resolved at Trust Level 3+** — Beeper acted with minimal or no human intervention, from detection through verified fix. This captures the full value chain: the knowledge flywheel is compounding (Beeper knows enough to act), the trust system is working (teams are graduating autonomy), and the platform delivers on its promise (a teammate, not a dashboard).

*Why evolved from v0.1.0:* "Incidents resolved autonomously" didn't distinguish between Beeper handling a trivial restart versus executing a complex, evidence-backed fix. Trust Level 3+ means Beeper earned the right to act.

### User Success Metrics

| Persona | Success Metric | Measurement |
|---|---|---|
| Sam (On-Call SRE) | Faster, calmer resolution | MTTR reduction + time spent in active collaboration vs. solo scrambling |
| Sam (On-Call SRE) | Trust progression | Trust level graduation timeline per service |
| Sam (On-Call SRE) | Fewer disruptions | Night/weekend pages requiring human response |
| Priya (Team Lead) | SLO compliance | % of SLOs met, burn rate trends |
| Priya (Team Lead) | Trust architecture | Number of services at Trust Level 3+ |
| Priya (Team Lead) | Data-driven reporting | Reliability reviews generated from Beeper data |
| Marcus (Developer) | Actionable fixes | Auto-PR merge rate and time-to-merge |
| Marcus (Developer) | Evidence quality | % of PRs where developer confirms evidence was sufficient |
| Jordan (Junior SRE) | Accelerated capability | Time to first independent incident resolution |
| Jordan (Junior SRE) | Collaboration value | Incidents where Beeper KB surfaced relevant past context |
| Diana (VP Eng) | Business impact visibility | Customer-impacting incident frequency and MTTR trends |
| Diana (VP Eng) | Investor story | End-to-end demo completion (detect → fix → prove) |
| Alex (Reliability Eng) | Test plan quality | Chaos tests derived from Beeper's documented failure patterns |
| On-Call Rotation | Continuity | Shift handoff time reduction, context carry-forward rate |

### Knowledge Flywheel Health

| Metric | What It Measures | Why It Matters |
|---|---|---|
| KB entries created per week | Flywheel input rate | Is Beeper learning? |
| KB reuse rate | Entries referenced in subsequent investigations | Is past knowledge compounding? |
| Human correction rate | % of KB entries edited by SREs | Feedback loop health (some correction is healthy; declining over time means accuracy is improving) |
| Investigation-to-KB ratio | % of investigations that produce reusable knowledge | Is the flywheel converting incidents into durable value? |

### Business Objectives

**3-month (demo-ready):**
- End-to-end demo app operational: fault injection → detection → investigation → fix → proof
- Full trust ladder demonstrable (Trust Levels 1-5) in demo environment
- SLO dashboard with customer impact scoring functional
- Collaboration features live: real-time investigation interaction
- Investor pitch deck backed by working demo

**6-month (community traction + investor conversations):**
- Active open-source installations growing
- GitHub stars, community contributions, and external blog posts emerging
- Conference presence (SREcon, KubeCon) with demo
- First architecture spikes completed (pluggable vector backend, WebSocket collaboration)
- Seed round conversations informed by demo metrics

**12-month (pre-commercial validation):**
- Beta users running Beeper on real production infrastructure
- Trust level progression data from real deployments (proving the graduation model works)
- KB flywheel metrics from real environments (proving compounding intelligence)
- SaaS architecture designed and prototyped
- Commercial launch plan defined with pricing model

### Key Performance Indicators

| KPI | Category | Target | Timeframe |
|---|---|---|---|
| Incidents resolved at TL3+ | North Star | Demonstrable in demo env | 3 months |
| Demo completion rate | Investor readiness | 100% reliable end-to-end | 3 months |
| MTTR reduction | User value | Measurable in demo; validated in beta | 6 months |
| Auto-PR merge rate | Developer trust | Tracked from first beta deployment | 6 months |
| KB reuse rate | Flywheel health | Increasing trend per active deployment | Ongoing |
| Trust level graduation | Adoption signal | At least 1 beta team at TL3+ | 12 months |
| Active installations | Community adoption | Growth trajectory established | 6 months |
| Beta deployments | Real-world validation | 3-5 teams on real infrastructure | 12 months |

## MVP Scope

### Scope Philosophy

v0.2.0 is not an incremental update — it's the release that transforms Beeper from observer to collaborator. All four waves ship as v0.2.0, delivered sequentially. The waves define the build order, not the release boundary. Every wave builds on the previous, and the demo app threads through all of them.

### Core Features

**Wave 1 — Foundation: SLO Platform + Notification Engine**

1. **SLO Platform**
   - `ServiceLevel` CRD for defining SLIs and SLOs per service
   - Burn rate calculation and alerting on SLO budget consumption
   - Customer impact scoring that correlates anomalies with SLO breach severity
   - SLO compliance dashboard for Priya and Diana

2. **Notification Engine**
   - `NotificationChannel` CRD for configuring outbound channels
   - Slack integration with @mention support
   - PagerDuty integration for escalations correlated with customer impact
   - Email and webhook channels
   - Design principle: **every notification must justify the interruption — false pages are bugs**

**Wave 2 — Trust + Action: Anti-Noise + Auto-Remediation**

3. **Trust & Anti-Noise System**
   - Trust levels 1-5 per service (advisory → fully autonomous)
   - Adaptive alert thresholds that learn from SRE feedback
   - Confidence gates — Beeper only acts when evidence meets the threshold for the configured trust level
   - Customer impact weighting — severity driven by SLO data, not static labels

4. **Auto-Remediation**
   - `Repository` CRD for code-aware fixes
   - Runbook execution — follow human-language runbooks without DSL translation
   - Auto-PR generation with full evidence trails (log correlation, root cause analysis, production conditions)
   - Advisory test plan (always): "here's how to verify this hypothesis"
   - Sandbox test execution (when available): design, run, and measure environment-specific tests
   - Fix verification — prove the fix resolves the issue before promoting
   - Confidence tiers gating remediation actions to trust level

**Wave 3 — Intelligence: Collaboration + KB + Signals**

5. **Collaborative Investigations**
   - Real-time investigation interaction — SREs work alongside Beeper during incidents
   - Evidence presentation with references to specific metrics, logs, and prior KB entries
   - Investigation threads with human annotations and redirections
   - Shift handoff summaries — Beeper as continuity glue for the on-call rotation

6. **Living Knowledge Base Enhancement**
   - KB entries linked to investigations with bi-directional references
   - Investigation-to-KB pipeline: every resolved incident produces reusable knowledge
   - Template-driven KB entries for common patterns
   - Service catalog integration — per-service knowledge views

7. **Signal Expansion**
   - Unified investigation timeline correlating logs, metrics, and events
   - Deploy correlation — link anomalies to recent deployments
   - Topology-aware investigation — understand service dependencies

**Wave 4 — Delight: Developer Experience + Analytics**

8. **Developer Experience**
   - Keyboard-first UI enhancements
   - Investigation workflow states (open → investigating → resolved → verified)
   - Remediation tracking from detection through fix verification
   - Service health feed improvements for Marcus's workflow

9. **Analytics & Gamification**
   - Reliability score per service (composite of SLO compliance, incident frequency, MTTR)
   - Onboarding quests for new Beeper users (Jordan's guided learning path)
   - Team streaks and recognition for reliability improvements
   - MTTR trends, customer impact trends, trust progression dashboards

**Across All Waves — Demo Application**

10. **Investor Demo Environment**
    - Purpose-built chaotic microservices application running in K8s alongside Beeper
    - Configurable fault injection (memory leak, bad deploy, cascading failure, scale-dependent issues)
    - Full lifecycle demonstration: healthy app → fault injected → Beeper detects → investigates → correlates → proposes fix with evidence → tests in sandbox → applies fix → app recovers
    - Scriptable for repeatable investor demos
    - Showcases trust levels, SLO dashboard, collaboration, and auto-PR in one narrative arc

### Architecture Spikes (Required Before Implementation)

Three architecture deep-dives needed before specific features can be built:

| Spike | Scope | Blocks |
|---|---|---|
| Pluggable vector backend | Evaluate abstracting beyond Qdrant to support multiple vector DBs | Signal expansion, future scalability |
| WebSocket infrastructure | Design real-time communication layer for collaboration features | Collaborative investigations |
| Agent framework evolution | Evaluate investigator architecture for multi-step remediation workflows | Auto-remediation, test execution |

### Out of Scope for v0.2.0

- **SaaS offering** — v0.2.0 is the open-source community edition; SaaS architecture is designed but not built
- **Multi-cluster support** — single cluster deployment only
- **Third-party marketplace** — no shared runbook/integration marketplace yet
- **Environment management** — Beeper doesn't provision or manage infrastructure
- **Advanced RBAC** — basic trust level configuration; fine-grained role-based access deferred
- **Mobile interface** — web UI only
- **Billing/metering** — no commercial instrumentation
- **Epic 10 ideas** (from brainstorming) — deferred to v0.3.0+

### MVP Success Criteria

- **Demo story complete:** An investor watches Beeper detect a fault, investigate, correlate with SLO impact, propose a fix with evidence, test it in sandbox, and apply it — all in one continuous flow
- **Trust ladder functional:** Trust levels 1-5 configurable and demonstrable, with Beeper's behavior visibly changing at each level
- **SLO-driven prioritization working:** Customer impact scoring drives notification urgency and remediation priority, not static severity labels
- **KB flywheel spinning:** Investigations produce KB entries that are reused in subsequent investigations (demonstrable compounding)
- **Collaboration is real:** An SRE can interact with Beeper during an active investigation — redirect, annotate, approve — not just watch
- **Auto-PR with proof:** A developer receives a PR with evidence trail and (when sandbox available) test results proving the fix
- **On-call continuity:** Shift handoff summary demonstrates Beeper as persistent team memory

### Future Vision (v0.3.0+)

**Phase 3 — Scale & Commercial:**
- SaaS offering with managed hosting, metered billing, and security certifications (SOC2)
- Multi-cluster and multi-environment support
- Advanced RBAC with team-level permissions and approval chains
- Community marketplace for shared runbooks, integrations, and investigation patterns

**Phase 4 — Platform:**
- Third-party integrations ecosystem
- Custom agent extensions — teams build specialized investigators for their domain
- Cross-organization anonymized learning — opt-in patterns shared across deployments
- Mobile companion app for on-call SREs
- Enterprise features: audit trails, compliance reporting, SSO

**The long game:** As AI generates more of the systems we operate, Beeper's context advantage compounds. Every deployment makes it harder to replace. The knowledge flywheel is the moat. Beeper becomes the operating system for AI-era reliability.
