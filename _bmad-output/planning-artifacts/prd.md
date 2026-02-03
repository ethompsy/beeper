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
inputDocuments:
  - product-brief-beeper-2026-01-27.md
workflowType: 'prd'
documentCounts:
  briefs: 1
  research: 0
  brainstorming: 0
  projectDocs: 0
classification:
  projectType: Agentic Platform
  domain: DevOps/SRE
  complexity: high
  projectContext: greenfield
---

# Product Requirements Document - Beeper

**Author:** Eric
**Date:** 2026-01-27
**Version:** 1.0

## Executive Summary

### Vision

Beeper is an open-source agentic AI that operates as a Tier 1 SRE teammate. It continuously monitors logs and metrics, detects anomalies, investigates root causes across architectural layers, and builds a living knowledge system in collaboration with human engineers. Beeper shifts SRE teams from reactive incident response to proactive system improvement.

### Key Differentiators

| Differentiator | Description |
|----------------|-------------|
| **Open-Source** | First open-source agentic SRE platform vs. proprietary competitors (Datadog Bits AI, PagerDuty SRE Agent) |
| **Living Knowledge System** | KB that agent documents, consumes, and learns from - compounding intelligence over time |
| **Collaborative Intelligence** | Human-in-the-loop as permanent design principle - force multiplier, not replacement |
| **Self-Hosted First** | Data never leaves customer premises; SaaS becomes attractive after proving value |

### Target Users

- **Sam (On-Call SRE):** Consumes investigations, uses KB for faster incident resolution
- **Priya (SRE Team Lead):** Curates KB, imports runbooks, guides team learning
- **Admin (Platform Engineer):** Deploys and configures Beeper
- **Security Reviewer:** Approves access scope for production deployment

### MVP Philosophy

Platform MVP: Prove the core investigation + knowledge base value loop works before adding autonomous capabilities. If we cannot demonstrate investigative accuracy, we cannot trust full autonomy.

**Team:** 1-2 humans + Claude as AI development partner

## Success Criteria

### User Success

**Sam (On-Call SRE):**
- Investigations include relevant context that accelerates understanding
- Knowledge base contains accurate, actionable documentation for known issues
- Reduced time spent manually correlating logs across systems

**Priya (SRE Team Lead):**
- Knowledge base captures institutional knowledge that previously lived in senior engineers' heads
- Investigation documentation supports postmortem and pattern analysis
- Data-driven visibility into recurring issues and systemic patterns

**Marcus (Product Team Developer):**
- Service health insights explained in developer-friendly language
- Clear correlation between runtime behavior and code/config origins
- Reduced time spent in incident bridges trying to understand production conditions

**Jordan (Junior SRE):**
- Knowledge base serves as learning resource for understanding diagnostic approaches
- Past investigations provide context for handling similar future issues

### Business Success

**3-month (open-source traction):**
- Active installations (target TBD)
- GitHub stars and community engagement
- Issues filed and external PRs indicating real usage
- First community-contributed runbook or integration

**6-month (community health):**
- Repeat contributors and self-sustaining community support
- Active installations growth trajectory
- Third-party integrations or practitioner blog posts
- Conference mentions (SREcon, KubeCon)

**12-month (commercial validation):**
- First paying SaaS customer
- Community-to-SaaS conversion rate established
- SaaS retention and expansion signals

### Technical Success

- **Detection latency:** Time from anomaly occurrence to Beeper identification (establish baseline, then improve)
- **False positive rate:** % of Beeper-flagged anomalies that humans determine are not real issues (establish baseline, target reduction)
- **System uptime:** Beeper availability and reliability as a monitoring component
- **Investigation completeness:** Beeper surfaces relevant signals across architectural layers without manual prompting

### Measurable Outcomes

**North Star (MVP):** Investigation accuracy rate - % of Beeper's root cause hypotheses validated by humans

| Metric | Description | MVP Target |
|--------|-------------|------------|
| Layer accuracy | % of investigations where Beeper correctly identifies the originating system layer | Establish baseline |
| Specific cause accuracy | % where Beeper identifies the specific root cause | Establish baseline |
| Known issue detection | Customer-impacting issues where Beeper alerts before human detection | Establish baseline |
| Novel issue discovery | New undocumented customer-impacting issues identified and validated | Track count and accuracy |
| Documentation utility | SRE-reported usefulness of investigation docs (qualitative) | Positive feedback |

## User Journeys

### Journey 1: Sam - The 2am Page

**Opening Scene:**
It's 2:17am on a Tuesday. Sam's phone buzzes with a PagerDuty alert: "Elevated error rate on payments service - P1." Sam groans, opens their laptop, and reflexively starts the familiar ritual: three terminal windows, log aggregator, metrics dashboard, the mental checklist of "what changed recently?"

**Rising Action:**
But this time, Sam also opens the Beeper console. The single pane of glass shows something remarkable:
- **Issue detected:** 2:14am - 3 minutes before the page fired
- **Current status:** "Investigating root cause - database connection pool exhaustion identified in application logs"
- **Correlation:** Beeper has already connected the error rate spike to connection pool timeouts, and is now examining what's causing the pool exhaustion

Sam starts their traditional troubleshooting in parallel. Within minutes, they're confirming what Beeper already found - the same log patterns, the same metrics correlation. But Beeper got there faster. Much faster.

**Climax:**
Beeper surfaces a recommendation: "Similar pattern observed in past incident KB-2024-0847. Resolution: Restart the connection pool manager service. Confidence: High based on log signature match."

Sam pulls up the KB entry. It's a documented incident from three months ago that Sam never saw - different on-call rotation. The symptoms match exactly. Sam executes the restart. Error rates normalize within 90 seconds.

**Resolution:**
Sam documents a quick confirmation in Beeper ("Resolution confirmed effective") and goes back to bed by 2:35am. Total incident time: 18 minutes. Their last thought before sleep: "I just wish Beeper could have run those commands so I didn't have to wake up at all."

**Capabilities Revealed:**
- Real-time investigation pane showing Beeper's active reasoning
- Faster-than-human log correlation across services
- Knowledge base with past incident matching
- Recommended resolutions with confidence levels
- Human confirmation workflow

### Journey 2: Priya - The Team That Levels Up

**Opening Scene:**
Priya has a folder of runbooks that haven't been updated in 18 months. The real procedures live in Slack threads, senior engineers' heads, and scattered Google Docs. Every postmortem ends with "update the runbook" as an action item that never gets done. Two senior engineers are thinking about leaving, and Priya dreads what walks out the door with them.

**Rising Action:**
Priya exports the team's existing runbooks from Confluence and imports them into Beeper's knowledge base. It's imperfect - some formatting issues, some outdated content - but it's a starting point. Beeper now has seed context for investigations.

Over the next few weeks, Beeper starts documenting its own investigations. Priya reviews the first few entries. Some are spot-on. Others miss context only a human would know. She has two options:
- Edit the entry directly (Beeper sees the diff and learns)
- Talk to Beeper in the KB: "The root cause wasn't the load balancer config - it was a deployment that changed the health check timeout. Update this entry to reflect that." Beeper revises the doc.

It feels less like fixing a junior's mistakes and more like mentoring them.

**Climax:**
Three months in, something shifts. Jordan (the new hire) resolves a P2 incident independently - they found a matching pattern in the KB that Priya never wrote. It was a Beeper-documented investigation that Priya had corrected once, and now it saved 40 minutes of escalation.

Then Priya notices the MTTR trend line. It's down 35% since Beeper adoption.

But the real moment comes in a team meeting. The engineers are debating a Beeper RCA finding. "I think the memory pressure was a symptom, not the cause." "Look at the correlation Beeper found with the batch job timing." They're learning. They're teaching each other. They're using Beeper's investigations as a shared reference point.

**Resolution:**
Priya realizes that Beeper hasn't just captured tribal knowledge - it's *distributing* it. The team is having better conversations about system behavior. Junior engineers are leveling up faster. Senior engineers are spending less time explaining the same things repeatedly.

When leadership asks about reliability improvements, Priya generates a quarterly review from Beeper's data in 10 minutes instead of two days of spreadsheet archaeology.

She thinks: "Beeper isn't replacing my team. It's making them better."

**Capabilities Revealed:**
- Runbook import (various formats for MVP)
- Two-way KB curation (direct edit or conversational correction)
- Version history with diff tracking
- Beeper learning from human corrections
- MTTR trend visibility
- Team collaboration around shared investigation findings

### Journey 3: Admin - Getting Beeper Running

**Opening Scene:**
Alex (the platform engineer) has been tasked with getting Beeper running in the staging environment for a proof-of-concept. The SRE team is excited but skeptical. Alex has seen plenty of tools that promise the world and deliver configuration nightmares.

**Rising Action:**
Alex checks the Beeper repo. Multiple deployment paths available:
- Build from source on their Ubuntu servers
- Dockerfile with build instructions
- Pre-built container from the public registry (CI/CD publishes on every release)
- Helm chart for their Kubernetes cluster

Alex goes with the Helm chart - matches their existing deployment patterns. The install is straightforward.

Next: connecting data sources. The team already runs Datadog agents and has a Prometheus/Loki stack for some services. Beeper doesn't need its own collectors - it bolts onto what's already there. Alex configures:
- Loki connection for the Kubernetes workloads
- Prometheus for metrics
- Read-only credentials for each source

**Climax:**
Alex opens the Beeper UI. The Sources panel shows both integrations with green status indicators. Log events are flowing. One source shows an amber warning: "Missing metric labels for service discovery - enrichment may be limited." Clear, actionable feedback.

Alex fixes the label configuration, refreshes. All green.

Within an hour, Beeper's investigation pane shows its first finding: a memory pressure pattern on one of the staging services that nobody had noticed. It's not critical, but it's real. Beeper is working.

**Resolution:**
Alex schedules the production deployment for next week and sends a screenshot to the SRE Slack channel: "Beeper is live in staging. Already found something."

The skeptics are intrigued.

**Capabilities Revealed:**
- Multiple deployment options (source, Docker, container registry, Helm)
- Integration with existing observability stack (not replacing collectors)
- UI-based source configuration with status indicators
- Clear error/warning surfacing for configuration issues
- Immediate visibility when data is flowing

### Journey 4: Security Reviewer - The Green Light

**Opening Scene:**
Dana from the security team gets a request: "Review and approve Beeper for production deployment." She's seen this before - another tool that wants broad access and vague justifications. She opens the ticket expecting a fight.

**Rising Action:**
Dana reviews the Beeper documentation. The access scope is clear and narrow:
- **Logs & Metrics:** Read-only, via existing collectors (Prometheus, Loki). No new agents, no new egress paths.
- **No write access** to any production systems. MVP Beeper observes and documents - it doesn't act.

Self-hosted deployment means:
- No data leaves the organization's infrastructure
- Credentials stored in their existing secrets management (Vault, K8s secrets, etc.)
- Runs inside their security perimeter with their network policies

Dana's main concerns dissolve quickly:
- **Credential storage?** Uses their existing secrets infrastructure.
- **Data exfiltration?** Self-hosted, no external calls required.
- **Blast radius if compromised?** Read-only access limits impact to information disclosure, same as any observability tool.

**Climax:**
Dana schedules a 30-minute call expecting to negotiate scope. Instead, she spends 15 minutes confirming what the docs already said. The access model is sensible. The self-hosted architecture means standard controls apply.

She adds one request: "Add audit logging of Beeper's access patterns to the roadmap. Not blocking for MVP, but I want it before we expand to more sensitive systems."

**Resolution:**
Dana approves the production deployment with a note: "Approved for production. Access scope is appropriate for MVP. Recommend audit logging before Phase 2 capabilities."

The SRE team has their green light.

**Capabilities Revealed:**
- Clear documentation of access scope and permissions
- Self-hosted architecture keeping data in customer control
- Integration with existing secrets management
- Read-only access model limiting blast radius
- (Stretch goal) Audit logging of Beeper's actions

### Secondary User Journeys (Post-MVP)

**Marcus (Developer):** Subscribes to service health insights in the KB for his payments service. Sees production behavior explained in developer terms. Builds trust through observability before ever receiving a Beeper-authored PR in Phase 2.

**Jordan (Junior SRE):** Uses the knowledge base as a learning resource. Reads past investigations to understand how experienced engineers diagnose issues. Resolves their first incident independently using a KB entry they didn't write.

**Diana (VP Engineering):** Post-MVP user. Will consume dashboards and reliability reports generated from Beeper's data. For MVP, gets visibility through Priya's manually-shared summaries.

**Alex (Performance Engineer):** Mines the KB for real failure patterns to design chaos engineering tests grounded in actual production behavior.

### Journey Requirements Summary

| Capability | Sam | Priya | Admin | Security | Marcus | Jordan |
|------------|-----|-------|-------|----------|--------|--------|
| Real-time investigation pane | ✓ | | | | | |
| Log/metric correlation | ✓ | | | | | |
| Knowledge base with past incidents | ✓ | ✓ | | | ✓ | ✓ |
| Recommended resolutions | ✓ | | | | | |
| Human confirmation workflow | ✓ | | | | | |
| Runbook import | | ✓ | | | | |
| KB curation (edit + conversational) | | ✓ | | | | |
| Version history with diff tracking | | ✓ | | | | |
| MTTR trend visibility | | ✓ | | | | |
| Multiple deployment options | | | ✓ | | | |
| Observability stack integration | | | ✓ | | | |
| Source status UI with errors | | | ✓ | | | |
| Access scope documentation | | | | ✓ | | |
| Self-hosted architecture | | | | ✓ | | |
| (Stretch) Audit logging | | | | ✓ | | |

## Project Scope & Phased Development

### MVP Feature Set (Phase 1)

**Deployment Target:** Kubernetes operator (self-hosted)

**Must-Have Capabilities:**

| Capability | Description |
|------------|-------------|
| K8s Operator | Spawns investigator agents per suspicious condition |
| Prometheus/Loki Ingestion | Push/stream from standard observability stack |
| Anomaly Detection | Detect patterns in logs and metrics |
| Cross-Layer Investigation | Correlate signals across architectural layers |
| Vector-Based KB | Semantic search, wiki interface, human-editable |
| Active Investigation Pane | Real-time UI showing Beeper's reasoning |
| Single LLM Provider | Claude API (configurable for other providers later) |
| Runbook Import | Seed KB with existing documentation |

**MVP Success Criteria:**
- Beeper detects anomalies that human SREs confirm are real
- Investigation documentation is accurate and useful to SREs
- Beeper correlates signals across architectural layers in multi-tier investigations
- Beeper identifies root causes (any layer) that humans validate
- Knowledge base helps humans resolve incidents faster
- Human corrections improve Beeper's subsequent reasoning

**Explicitly Deferred from MVP:**
- Codebase analysis (GitHub integration)
- Service health views in KB
- Graph relationships in KB (vector-only for MVP)
- Additional observability adapters (Datadog, CloudWatch)
- Daemon deployment model (non-K8s)
- Autonomous remediation
- PR drafting
- Push notifications
- SaaS offering

### Phase 2 (v1.1 - Foundation Expansion)

- Codebase analysis via GitHub App
- Service health views per service
- Graph relationships in KB
- Datadog adapter
- CloudWatch adapter
- Daemon deployment model for non-K8s environments
- Role-based access control (admin vs user)

### Phase 3 (v2.0 - Autonomous Action)

- Graduated remediation (restart, scale, rollback) with approval workflows
- Runbook execution
- PR drafting with production evidence
- Push notifications (Slack, PagerDuty)
- Spending caps and rate limit UI

### Phase 4 (v3.0 - Scale & Commercial)

- Multi-tenant SaaS offering
- Edge agent with sanitization layer
- Community intelligence (opt-in pattern sharing)
- Adoption dashboards and reliability reporting
- Additional LLM provider integrations (BYOM)

### Risk Mitigation Strategy

**Technical Risks:**

| Risk | Mitigation |
|------|------------|
| LLM costs explode in noisy environments | Tiered models, spending caps, memoization, surface noisy environments to users |
| RCA accuracy insufficient | Fallback to symptom-based safe actions; validate with chaos engineering in test environments |
| Vector-only KB limits correlation | Semantic search still powerful; graph adds relationships in v1.1 |
| K8s operator complexity | Well-understood pattern with good tooling (kubebuilder, operator-sdk) |

**Market Risks:**

| Risk | Mitigation |
|------|------------|
| Competitors move faster | Open-source community velocity; different value prop (freedom vs. convenience) |
| Enterprise security blocks adoption | Self-hosted, clear access documentation, read-only access model |
| Community doesn't form | MVP still valuable to individual teams; community is upside, not dependency |

**Resource Risks:**

| Risk | Mitigation |
|------|------------|
| 2-person team too small | Aggressive MVP scope; Claude as force multiplier; open-source contributions post-launch |
| Scope creep | Clear phase boundaries; defer ruthlessly; v1.1 is close behind |

## Domain-Specific Requirements

### Deployment Architecture

**MVP (Self-Hosted):**
- All components run on customer infrastructure
- Logs, metrics, and KB data never leave customer premises
- Customer owns security, compliance, and operational posture
- Beeper provides documentation for customer security reviews

**SaaS Architecture (Future):**
- Edge agent runs on customer infrastructure adjacent to applications
- Agent sanitizes findings before transmission to SaaS platform
- KB and UI hosted in SaaS platform
- Raw logs/metrics never leave customer environment - only sanitized investigation findings

### Data Sensitivity & Privacy

**Customer Responsibility (MVP):**
- PII detection and handling in log data
- Data retention policies for KB
- Access control to Beeper UI and data

**Product Responsibility (SaaS):**
- Sanitization layer in edge agent to strip sensitive data before transmission
- Design for SOC2, HIPAA, PCI-DSS, GDPR compatibility
- Clear data flow documentation for customer compliance reviews

### Compliance Approach

**MVP:**
- Compliance documentation explaining access scope and data handling
- Self-hosted model inherits customer's existing compliance posture
- Identify compliance blockers early in design phase

**SaaS:**
- SOC2 certification as table stakes for enterprise adoption
- Additional certifications based on customer requirements (HIPAA BAA, etc.)
- Compliance as a SaaS differentiator over self-hosted

### Community Intelligence (Opt-In)

**Reciprocity Model:**
- Customers may opt-in to anonymized pattern sharing
- Opt-in customers benefit from community-improved detection patterns
- Opt-out customers are fully isolated but don't receive community improvements
- "All in is best" - incentivizes participation

## Innovation & Competitive Analysis

### Detected Innovation Areas

**1. Open-Source Agentic SRE**
The competitive landscape (Datadog Bits AI, PagerDuty SRE Agent, Neubird Hawkeye, incident.io) is entirely proprietary SaaS. Beeper is the first open-source agentic SRE platform, enabling:
- Community-driven development and contributions
- Transparency in how the agent reasons and learns
- No vendor lock-in
- Self-hosted deployment for security-conscious organizations

**2. Living Knowledge System**
Competitors retrieve runbooks from static sources (Confluence, GitHub). Beeper's KB is different:
- Agent documents its own investigations
- Agent consumes and learns from the KB
- Human corrections improve agent reasoning
- Compounding intelligence over time, not static lookup

**3. Collaborative Intelligence**
Human-in-the-loop as a permanent design principle, not a transitional trust mechanism:
- SREs provide business context AI cannot derive from telemetry
- Engineers and Beeper learn together
- "Beeper makes SRE teams BETTER" - force multiplier, not replacement

**4. Reciprocity Community Model**
Opt-in anonymized pattern sharing with reciprocity:
- Contribute patterns, benefit from community intelligence
- Opt-out users are isolated but don't receive improvements
- "All in is best" - aligned incentives vs. proprietary training data

### Competitive Landscape

| Competitor | Weakness Beeper Exploits |
|------------|-------------------------|
| Datadog Bits AI | Proprietary, SaaS-only, locked to Datadog ecosystem |
| PagerDuty SRE Agent | Commercial, charges extra for AI, enterprise pricing |
| Neubird Hawkeye | Integration layer, not a platform - dependent on others |
| incident.io | Proprietary, no self-hosted option |

**Market timing:** Space is moving fast (Bits AI went GA Dec 2025). Open-source alternative entering now can capture community mindshare before market consolidates around proprietary players.

### Validation Approach

**RCA Accuracy Validation:**
- Chaos engineering in test environments
- Cause known issues, measure if Beeper correctly identifies root cause
- Track layer accuracy and specific cause accuracy over time
- Human validation of Beeper's hypotheses

**Graceful Degradation:**
- **Best case:** Beeper finds root cause AND recommends fix
- **Fallback:** Beeper surfaces relevant signals and suggests safe actions based on symptoms
- **Minimum value:** Faster investigation documentation than manual process

## Agentic Platform Architecture

### Agent Architecture

**Deployment Models:**
- **Kubernetes (MVP):** Operator pattern spawns investigator agents per suspicious condition
- **Non-Kubernetes (v1.1):** Daemon process spawns investigator child processes
- **Separation of concerns:** UI/KB tier can be co-located or deployed separately from agent tier

**Investigation Flow:**
1. Agent detects suspicious condition in log/metric stream
2. Spawns dedicated investigator for that condition
3. Investigator first assesses: Is there detectable customer impact?
4. If yes, proceeds with RCA and troubleshooting
5. Documents findings to KB throughout investigation

### LLM Integration

**Model Flexibility:**
- **OSS:** Supports any model (full flexibility for self-hosted users)
- **SaaS:** Bring Your Own Model (BYOM) support
- **Tiered usage:** Lightweight models (Haiku, GPT-4 Mini) for screening; powerful models for deep RCA

**Cost Management:**
- Spending caps and rate limits per customer/environment
- Surface noisy environments that drive excessive investigation costs
- Memoization and caching to avoid rehashing known problems
- Investigation continuity: recurring issues consume and extend prior research

### Knowledge Base Architecture

**Hybrid Data Model:**
- Vector store for semantic similarity and embedding-based retrieval (MVP)
- Graph database for entity relationships - services, incidents, causes, remediations (v1.1)
- Wiki-style interface for human readability and editing

**Multi-Modal Retrieval:**
- Semantic search via embeddings
- Structured queries (by service, error type, date range, severity)
- Extensible for future retrieval methods

**Graduated Authoring Trust:**
- **Initial state:** Beeper drafts → human reviews → approved/corrected
- **Earned trust:** Beeper publishes directly as accuracy is validated over time
- Full version history with diff tracking for all entries

### Integration Architecture

**Log/Metric Ingestion:**
- Push and streaming patterns preferred (Kafka, NATS, webhook)
- Integration with existing observability infrastructure (not replacing collectors)
- MVP: Prometheus and Loki

**Adapter Model:**
- Built-in adapters for common stacks: Prometheus, Loki (MVP); Datadog, CloudWatch (v1.1)
- Plugin architecture for community-contributed adapters
- Generic webhook/API adapter for custom integrations

**Codebase Access (v1.1):**
- GitHub App for repository access via API
- Similar approaches for GitLab, Bitbucket, and other providers
- CI/CD integration for deployment awareness and change correlation

## Functional Requirements

### Investigation Management

- **FR1:** Beeper can continuously monitor incoming log and metric streams for anomalous patterns
- **FR2:** Beeper can spawn a dedicated Investigator for each detected suspicious condition
- **FR3:** Investigator can assess whether a detected condition has customer impact
- **FR4:** Investigator can correlate signals across multiple architectural layers (infrastructure, platform, application, data)
- **FR5:** Investigator can query the Knowledge Base for similar past incidents
- **FR6:** Investigator can build on prior research when investigating recurring conditions
- **FR7:** Investigator can generate a root cause hypothesis with an explicit confidence level
- **FR8:** Investigator can recommend resolution actions based on investigation findings
- **FR9:** Investigator can document its investigation process and findings to the Knowledge Base
- **FR10:** SRE can observe an Investigator's reasoning process in real-time
- **FR11:** SRE can confirm or reject an Investigator's resolution recommendation
- **FR12:** SRE can mark an investigation as resolved with outcome confirmation

### Knowledge Base

- **FR13:** SRE Lead can import existing runbooks into the Knowledge Base
- **FR14:** SRE can search the Knowledge Base using natural language queries (semantic search)
- **FR15:** SRE can search the Knowledge Base using structured filters (service, error type, date range)
- **FR16:** SRE can view investigation documentation in a human-readable wiki format
- **FR17:** SRE Lead can directly edit Knowledge Base entries
- **FR18:** SRE Lead can provide conversational corrections to Beeper ("update this entry to reflect X")
- **FR19:** Beeper can revise Knowledge Base entries based on conversational corrections
- **FR20:** Beeper can learn from the diff between its documentation and human corrections
- **FR21:** SRE can view version history of any Knowledge Base entry
- **FR22:** SRE can compare versions of a Knowledge Base entry (diff view)
- **FR23:** Beeper can publish entries directly as trust is established (graduated authoring)

### Observability Integration

- **FR24:** Admin can configure Prometheus as a metrics data source
- **FR25:** Admin can configure Loki as a log data source
- **FR26:** Admin can provide read-only credentials for each data source
- **FR27:** Beeper can receive pushed log and metric data via streaming connections
- **FR28:** Admin can view the status of all configured data sources
- **FR29:** Admin can view errors and warnings for misconfigured data sources
- **FR30:** Beeper can ingest data without adding latency to the monitored systems

### User Interface

- **FR31:** SRE can view a list of active investigations
- **FR32:** SRE can view the real-time reasoning of any active Investigator (investigation pane)
- **FR33:** SRE can view recommended resolutions with confidence levels
- **FR34:** SRE can navigate from an investigation to related Knowledge Base entries
- **FR35:** SRE Lead can view MTTR trends over time
- **FR36:** SRE can access the Knowledge Base wiki interface

### Deployment & Operations

- **FR37:** Admin can deploy Beeper as a Kubernetes operator
- **FR38:** Beeper can spawn Investigator pods within the Kubernetes cluster
- **FR39:** Admin can configure Beeper via Kubernetes custom resources
- **FR40:** Admin can view Beeper's operational health status
- **FR41:** Beeper can operate with all data remaining on customer premises (self-hosted)

### LLM Management

- **FR42:** Admin can configure which LLM provider Beeper uses
- **FR43:** Beeper can use lightweight models for initial screening tasks
- **FR44:** Beeper can escalate to more powerful models for deep RCA
- **FR45:** Beeper can cache and memoize results to avoid redundant LLM calls
- **FR46:** Admin can set spending caps or rate limits for LLM usage
- **FR47:** Beeper can surface environments with excessive investigation costs to the Admin

## Non-Functional Requirements

### Performance

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| **NFR-P1:** Anomaly detection latency | Seconds from occurrence to detection | SREs need near-real-time awareness of issues |
| **NFR-P2:** Investigation pane updates | Real-time streaming | SREs watching active investigations expect live updates |
| **NFR-P3:** KB search response | Sub-second | Fast lookup during active incidents is critical |
| **NFR-P4:** Data ingestion overhead | Zero added latency to monitored systems | Beeper must not degrade the systems it observes |

### Security

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| **NFR-S1:** Data residency | All data remains on customer premises (MVP) | Self-hosted architecture; no external data transmission |
| **NFR-S2:** Credential storage | Use K8s secrets or external secrets operator | Leverage existing infrastructure; no custom credential store |
| **NFR-S3:** Access model | Read-only access to all data sources | Limits blast radius if Beeper is compromised |
| **NFR-S4:** UI access control (MVP) | Internal network only (VPN/private network) | Defer authn/authz to v1.1 |
| **NFR-S5:** UI access control (v1.1) | Role-based access (admin vs user) | Separate configuration access from observation access |

### Reliability

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| **NFR-R1:** Component independence | Each component operates independently where possible | Compartmentalized failure domains |
| **NFR-R2:** KB unavailability handling | Investigator buffers findings locally until KB returns | Investigation work not lost if KB temporarily down |
| **NFR-R3:** Graceful degradation | SREs can use traditional tools if Beeper fails | Beeper is additive, not a single point of failure |
| **NFR-R4:** Investigation durability | Completed investigations persisted to KB | In-progress durability deferred (prove capability first) |

### Integration

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| **NFR-I1:** Observability stack compatibility | Prometheus and Loki for MVP | Standard open-source stack; additional adapters in v1.1 |
| **NFR-I2:** LLM provider flexibility | Configurable provider (Claude API default) | Support model experimentation and cost optimization |
| **NFR-I3:** K8s native deployment | Operator pattern with CRDs | Kubernetes-native configuration and lifecycle |
| **NFR-I4:** Streaming data ingestion | Push/stream protocols (not polling) | Real-time data flow for timely detection |

### Deferred (Post-MVP)

- **Scalability targets:** Design sanely, optimize when needed
- **Accessibility (WCAG):** Basic usability for MVP; full accessibility for SaaS
- **Multi-tenancy:** SaaS-only concern
- **Audit logging:** Stretch goal per security reviewer feedback
