---
stepsCompleted: [1, 2, 3, 4, 5]
inputDocuments:
  - VISION.md
date: 2026-01-27
author: eric
---

# Product Brief: beeper

## Executive Summary

Beeper is an agentic AI that operates as a Tier 1 SRE teammate. At its simplest, it follows human-written runbooks with precision and speed. At its most advanced, it continuously monitors logs and metrics, detects anomalies, investigates root causes across architectural layers, resolves issues with graduated autonomy, analyzes codebases to draft PRs for root cause fixes, and builds a living knowledge system in collaboration with human engineers. Beeper shifts SRE teams from reactive incident response to proactive system improvement.

---

## Core Vision

### Problem Statement

Modern systems operations depends on rare, expert-level investigative reasoning -- the ability to correlate seemingly meaningless signals across architectural layers and tiers to identify root causes of novel failures. This skill cannot be codified in rules, captured in runbooks, or replicated by pattern-matching AIOps tools. The result: alert fatigue, prolonged outages from undiscovered conditions, tribal knowledge locked in senior engineers' heads, and teams stuck in a reactive posture. Meanwhile, AI-accelerated development velocity is compounding system complexity faster than operational capacity can grow.

### Problem Impact

- **Alert fatigue** erodes on-call engineer effectiveness and retention
- **Slow or missed response** to undiscovered problem conditions causes prolonged outages
- **Tribal knowledge loss** when experienced engineers leave creates organizational fragility
- **Reactive posture** means SRE teams spend their time firefighting instead of improving system reliability
- **Accelerating development velocity** (driven by AI-assisted development) is increasing system complexity faster than operational teams can keep up

### Why Existing Solutions Fall Short

Current AIOps and observability tools (e.g., PagerDuty, Moogsoft, BigPanda) address pieces of the problem but none close the full loop. They still require human leadership to assemble tools into a working framework, write SOPs, and run the incident workflow on every event. The deep, multi-tiered investigative process -- correlating seemingly meaningless log messages across systems to identify root causes of intermittent issues -- remains a rare human skill that no existing product has captured or automated.

### Proposed Solution

Beeper is an always-on agentic AI that continuously watches log and metric feeds, investigates anomalies in real time, correlates conditions across architectural layers and tiers, and reasons out resolutions. It executes fixes with graduated autonomy: read-only investigation, safe operational remediations (restart, scale, rollback), environment management, and analyzing the codebase to draft pull requests that fix root causes -- each tier requiring appropriate confidence and approval levels. Beeper operates with explicit confidence levels, acknowledging when signal is insufficient and escalating accordingly. Beeper delivers value from day one through investigation and documentation, even before it builds sufficient confidence for autonomous remediation. As it learns each environment, its capabilities graduate from observer to investigator to active responder to code contributor.

Beeper prioritizes by customer impact: conditions actively degrading customer experience demand immediate action and runbook documentation, while potential future risks are tracked separately at lower priority. SREs remain the voice of the customer, guiding beeper's prioritization.

It takes a document-first approach: every investigation, finding, and remediation feeds into a living knowledge system -- structured, validated against real outcomes, and actively consumed by the agent itself. This creates a compounding feedback loop, not a static wiki. Beeper designs alerts for recurring issues, drafts SOP runbooks, follows existing runbooks, and expands the knowledge base through constant investigation and discovery.

Human SREs collaborate with beeper through collaborative intelligence -- a permanent design principle, not a transitional trust mechanism. Engineers provide business context, deployment awareness, known fragile components, and domain caveats that no amount of telemetry analysis can surface. AI as part of the team, not a replacement.

### Key Differentiators

- **Graduated full-loop autonomy**: From runbook execution to investigation to remediation to code-level fixes -- each tier with appropriate confidence thresholds and approval levels
- **Living knowledge system**: Documentation generated from real incidents, validated by outcomes, and actively consumed by the agent. During active investigations, beeper surfaces relevant past incidents, known caveats, and prior resolutions -- context that would otherwise require paging a senior engineer.
- **Collaborative intelligence**: Human-in-the-loop as a permanent design principle -- SREs provide context AI cannot derive from telemetry alone
- **Deep investigative reasoning**: Gives every team access to principal-level SRE troubleshooting capability that is rare to find and difficult to hire for. Builds environmental understanding by analyzing codebases, CI/CD pipelines, and IaC, supplemented by human expert collaboration.
- **Customer-impact prioritization**: Conditions degrading customer experience drive immediate action; potential future risks are tracked separately. SREs remain the voice of the customer.
- **Open-source community moat**: Community-driven development absorbs contributions from the global SRE community. Incumbents profit from bridging gaps, not closing them -- beeper's incentive is aligned with the practitioner.

### Business Model

Open-source core with a protective license preventing competitive SaaS offerings. Free to use, community-driven development leveraging the collective expertise of the global SRE community. Commercial SaaS offering for teams that want managed, at-scale operation. Think claude-code for SRE teams.

### Risks & Open Questions

- **Cold start**: Time-to-value in new environments is unknown. Tier 1 runbook automation provides immediate value while beeper builds deeper environmental understanding.
- **Trust ceiling**: Some organizations may cap beeper at prescribed-SOP execution. Validating changes in lower environments before production may help build confidence. Open-source community interaction will surface trust patterns.
- **Security posture**: Enterprise security teams may resist beeper's broad access requirements. Community edition enables restricted-environment deployment; SaaS offering will pursue security certifications (SOC2, etc.) as adoption shortcuts.
- **Business model uncertainty**: SaaS differentiation (low onramp, metered billing, managed scaling) versus self-hosted community edition needs validation. Community success may be the primary outcome.

## Target Users

### Primary Users

**Sam -- On-Call SRE**
- **Role:** Mid-level SRE, rotates on-call weekly
- **Context:** Manages a mix of legacy and modern microservices. Gets paged at all hours. Has strong troubleshooting instincts but limited knowledge of some newer services.
- **Current pain:** Drowning in alerts, spends half of on-call shifts investigating non-issues, and the other half scrambling through stale runbooks for real ones. Dreads the 3am page for a system they didn't build.
- **Beeper interaction:** Beeper either takes the first page or works in parallel. Two communication modes: a pull mode (active investigation pane for real-time observation of beeper's reasoning) and a push mode (configurable notifications for decisions requiring human input). Sam reviews investigations, approves complex remediations, and contributes corrections when beeper's understanding is off.
- **Success moment:** Sam wakes up to a summary of three incidents beeper resolved overnight -- all documented, all correct. Sam's morning is spent reviewing and improving, not firefighting.

**Priya -- SRE Team Lead**
- **Role:** Senior SRE / Team Lead overseeing a team of 6
- **Context:** Splits time between incident management, reliability strategy, and mentoring. Constantly asked by leadership "why did that outage happen?" and "how do we prevent the next one?"
- **Current pain:** Tribal knowledge lives in her head and two senior engineers who might leave. Runbooks are outdated. She spends more time in postmortems than prevention.
- **Beeper interaction:** Reviews beeper's knowledge base for systemic patterns, guides prioritization, and uses beeper's documented findings to answer leadership questions with data instead of narrative. Beeper automatically generates adoption metrics (incidents resolved, MTTR improvement, knowledge base growth) that Priya uses to build the business case for broader adoption.
- **Success moment:** Priya presents a quarterly reliability review built entirely from beeper's knowledge base and leadership approves the roadmap without debate.

**Marcus -- Product Team Developer**
- **Role:** Backend developer on the payments service team
- **Context:** Owns code that runs in production but rarely looks at production logs. Gets pulled into incident bridges when his service is implicated.
- **Current pain:** Gets dragged into incidents with no context, spends hours trying to reproduce production conditions locally. Resents ops interruptions during sprint work.
- **Beeper interaction:** First touchpoint isn't a PR -- it's a service health feed. Marcus subscribes to production insights for his service, explained in developer language ("your payments service threw 47 timeout errors correlated with database connection pool exhaustion during peak traffic"). He builds trust through observability before receiving his first PR. When PRs arrive, beeper is friendly, concise, cites production evidence, and follows his team's coding standards.
- **Success moment:** Marcus merges a beeper PR that fixes an intermittent null pointer his team couldn't reproduce for months. The PR includes the exact log correlation that proved the race condition. He starts trusting beeper's PRs.

### Secondary Users

**Jordan -- Junior SRE / New Hire**
- **Role:** Just joined the SRE team 3 months ago
- **Context:** Smart but overwhelmed by the scale and complexity. Doesn't know which alerts matter, which services are fragile, or where the institutional knowledge lives.
- **Current pain:** Asks senior engineers the same questions repeatedly. Stale documentation sends them down wrong paths. Afraid of making a mistake on-call.
- **Beeper interaction:** Uses the knowledge base as a learning resource -- reading beeper's documented investigations to understand how experienced engineers diagnose issues. Also uses service insights to learn what's happening now across the ecosystem alongside what happened historically.
- **Success moment:** Jordan resolves an escalated incident independently because they'd read beeper's documentation of a similar past event. The team notices.

**Diana -- VP of Engineering**
- **Role:** Oversees all engineering, reports to CTO
- **Context:** Needs to justify SRE investment, explain outage impact to the business, and make build-vs-buy decisions on tooling.
- **Current pain:** Gets vague postmortem summaries, can't quantify reliability improvements, and struggles to hire senior SRE talent.
- **Beeper interaction:** Consumes dashboards and reports derived from beeper's knowledge base -- MTTR trends, customer impact metrics, recurring issue categories.
- **Success moment:** Diana shows the board that MTTR dropped 60% since beeper adoption and customer-impacting incidents are down quarter-over-quarter -- with data she didn't have to compile.

**Alex -- Performance / Reliability Engineer**
- **Role:** Designs load tests and chaos engineering experiments
- **Context:** Needs realistic failure scenarios to test against, but production failures are poorly documented and hard to reproduce.
- **Beeper interaction:** Mines beeper's knowledge base for real failure patterns, condition correlations, and edge cases to design test scenarios grounded in actual production behavior.
- **Success moment:** Alex designs a chaos test based on a failure pattern beeper documented. The test catches a regression before it reaches production.

### User Journey

**Discovery:** SRE teams find beeper through the open-source community, word of mouth at SREcon/KubeCon, or engineering blog posts. The "claude-code for SRE teams" pitch resonates immediately with anyone who's used AI-assisted dev tools.

**Onboarding:** Team points beeper at their log/metric feeds and optionally seeds it with existing runbooks. Beeper begins in observation mode -- investigating and documenting without taking action. Value starts immediately through documentation and service health insights.

**Core Usage:** Beeper runs continuously. On-call engineers observe beeper via the active investigation pane (pull) or receive targeted notifications (push). Developers subscribe to service health feeds and review PRs. The knowledge base grows daily. SRE leads review patterns weekly. Beeper generates adoption metrics automatically.

**Success Moment:** The first overnight incident that beeper resolves autonomously without waking anyone. The morning review confirms it was handled correctly and documented thoroughly.

**Long-term:** Beeper becomes the institutional memory of the SRE team. New hires onboard through its knowledge base. Developers trust its service insights and PRs. Leadership makes data-driven reliability decisions. The champion uses beeper's own metrics to justify broader adoption. The team shifts from reactive to proactive. Beeper is the teammate nobody wants to lose.

## Success Metrics

### North Star Metric

**Incidents resolved autonomously** -- The single metric that captures beeper's core value across all user segments. Fewer escalations means less fatigue for Sam, fewer fire drills for Marcus, and a measurable reliability improvement for Priya to report upward.

### User Success Metrics

| Persona | Success Metric | Measurement |
|---|---|---|
| Sam (On-Call SRE) | Reduced alert burden | % of incidents resolved without human escalation |
| Sam (On-Call SRE) | Faster resolution | MTTR reduction vs. pre-beeper baseline |
| Sam (On-Call SRE) | Fewer disruptions | Night/weekend pages requiring human response |
| Marcus (Developer) | Fewer production fire drills | Incident bridge pull-ins per sprint |
| Marcus (Developer) | Actionable code fixes | PR merge rate from beeper-authored PRs |
| Marcus (Developer) | Service health awareness | Developer engagement with service health feed |
| Priya (Team Lead) | Systemic improvement | Recurring incident elimination rate |
| Priya (Team Lead) | Knowledge capture | Knowledge base entries created and validated |
| Priya (Team Lead) | Data-driven reporting | Reliability reviews generated from beeper data |
| Jordan (Junior SRE) | Accelerated onboarding | Time to first independent incident resolution |
| Diana (VP Eng) | Business impact visibility | Customer-impacting incident frequency and MTTR trends |

### Business Objectives

**3-month (open-source traction):**
- Active installations (target TBD)
- GitHub stars and community size (awareness signals)
- Issues filed and external PRs (real usage indicators)
- First community-contributed runbook or integration

**6-month (community health):**
- Repeat contributors and self-sustaining community support
- Active installations growth trajectory
- Third-party integrations or blog posts by practitioners
- Conference mentions (SREcon, KubeCon)

**12-month (commercial validation):**
- First paying SaaS customer
- Community-to-SaaS conversion rate established
- SaaS retention and expansion signals
- Revenue baseline (target TBD)

### Key Performance Indicators

| KPI | Category | Target | Timeframe |
|---|---|---|---|
| Incidents resolved autonomously | North Star | Baseline → measurable growth | Ongoing |
| Active installations | Community adoption | TBD | 3 months |
| MTTR reduction | User value | Measurable improvement vs. baseline | Per deployment |
| PR merge rate | Developer trust | Increasing trend | 6 months |
| External contributors | Community health | Repeat contributors emerging | 6 months |
| First paying SaaS customer | Commercial validation | 1 | 12 months |
| Knowledge base entries validated | Knowledge compounding | Growing per active installation | Ongoing |

## MVP Scope

### Core Features

**1. Log & Metric Ingestion**
- Continuous ingestion of log and metric feeds from the target environment
- Support for common formats and sources (specifics TBD during architecture)

**2. Anomaly Detection & Cross-Layer Investigation**
- Detect anomalous patterns in the data feed
- Correlate signals across architectural layers and tiers
- Reason about root causes using multi-tiered investigative methodology
- Operate with explicit confidence levels -- acknowledge when signal is insufficient

**3. Codebase Analysis**
- Analyze the codebase to correlate runtime behavior with source code
- Identify probable code-level causes of production issues (e.g., memory leaks, race conditions)
- Suggest where in the codebase an issue originates -- investigation only, no PRs yet

**4. Living Knowledge Base**
- Structured, searchable documentation of every investigation
- Findings include: anomaly detected, signals correlated, root cause hypothesis, confidence level, and suggested code-level origin where applicable
- Human-editable -- SREs revise, correct, and annotate beeper's entries directly as the feedback mechanism
- Accepts existing runbooks as seed context to inform beeper's reasoning

**5. Active Investigation Pane**
- Real-time observation UI where on-call engineers can watch beeper's investigation process as it happens
- View current investigation state, reasoning chain, and findings

**6. Service Health in Knowledge Base**
- Beeper publishes per-service metrics and findings to the knowledge base
- Structured by service catalog as beeper builds understanding of the ecosystem
- Foundation for future dedicated service health feeds

### Out of Scope for MVP

- **Autonomous remediation** -- beeper investigates and documents but does not take action on the environment
- **PR drafting** -- beeper identifies code-level causes but does not draft fixes yet
- **Runbook execution** -- beeper ingests runbooks for context but does not execute them
- **Notifications / push integrations** -- no Slack, PagerDuty, or messaging integration unless it proves to be an easy win during development
- **Dedicated service health feed UI** -- per-service insights are published to the KB, not a separate interface
- **Adoption dashboards / reporting** -- no leadership-facing metrics views
- **Alert design** -- beeper does not create or manage alerts
- **SaaS offering** -- MVP is the community edition only

### MVP Success Criteria

- Beeper ingests logs/metrics from a real environment and detects anomalies that a human SRE confirms are real
- Beeper produces investigation documentation that an SRE finds accurate and useful
- Beeper correctly correlates signals across architectural layers in at least one multi-tier investigation
- Beeper identifies a code-level root cause that an SRE validates against the codebase
- An SRE uses the knowledge base to resolve or understand an incident faster than they would have without it
- A human correction to a beeper entry improves beeper's subsequent reasoning

### Future Vision

**Phase 2 -- Autonomous Action:**
- Graduated remediation: safe operational actions (restart, scale, rollback) with approval workflows
- Runbook execution: beeper follows prescribed SOPs autonomously
- PR drafting: beeper writes and submits code fixes with production evidence
- Push notifications to Slack, PagerDuty, and other messaging tools

**Phase 3 -- Proactive Intelligence:**
- Alert design: beeper creates alerts for recurring patterns
- Dedicated service health feeds per service for developers
- Adoption dashboards and reliability reporting for leadership
- Environment management capabilities

**Phase 4 -- Scale & Commercial:**
- SaaS offering with managed hosting, metered billing, and security certifications
- Multi-environment support
- Advanced collaboration features (team workflows, approval chains)
- Community marketplace for shared runbooks, integrations, and investigation patterns
