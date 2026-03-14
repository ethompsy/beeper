---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
inputDocuments:
  - prd.md
  - product-brief-beeper-2026-03-09.md
  - product-brief-beeper-2026-01-27.md
  - ux-design-specification.md
  - project-overview.md
  - integration-architecture.md
  - source-tree-analysis.md
  - development-guide.md
  - deployment-guide.md
  - api-contracts.md
workflowType: 'architecture'
lastStep: 1
status: 'complete'
completedAt: '2026-03-13'
previousVersion:
  completedAt: '2026-02-03'
  context: 'v0.1.0'
project_name: 'beeper'
user_name: 'eric'
date: '2026-03-13'
classification:
  projectType: Agentic Platform
  domain: DevOps/SRE
  complexity: high
  projectContext: brownfield
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
- 63 FRs across 11 capability areas, up from 47 in v0.1.0
- v0.1.0's 47 FRs are fully implemented and tested (1,032 tests). v0.2.0 adds 16 net-new FRs and restructures the existing FRs into the wave delivery model
- Core loop extended: Detect → Investigate → Correlate → **Score by SLO impact** → **Propose fix with evidence** → **Test in sandbox** → **Apply with trust gating** → Document to KB → **Notify with justification**
- New capability areas: SLO Platform (FR1-7), Notification Engine (FR8-15), Trust System (FR16-22), Auto-Remediation (FR23-31), Collaboration (FR32-37), Demo Application (FR54-57), Platform Security (FR58-63)
- Multi-actor system expanded: Beeper agent, Investigator (spawned), SRE (user), SRE Lead (admin), Developer (auto-PR consumer), VP Eng (demo viewer)

**Non-Functional Requirements:**
- 22 NFRs across Performance (7), Security (6), Reliability (5), Scalability (4)
- **Performance:** < 30s anomaly-to-investigation, < 500ms WebSocket delivery, < 5 min demo lifecycle
- **Security:** Least-privilege RBAC, PII scrubbing before LLM, scoped repo tokens, sandbox network isolation
- **Reliability:** Non-SPOF, autonomous action rollback within 60s, 10 consecutive reliable demo runs
- **Scalability:** 50+ concurrent investigations, 10K+ KB entries, 100+ ServiceLevel CRDs, 1000+ notifications/hour

**UX Architectural Implications (from UX Design Specification):**
- **WebSocket required:** Real-time bidirectional investigation collaboration (SSE insufficient for annotations/redirections)
- **Tailwind CSS migration:** Incremental adoption over ~3,900 lines existing custom CSS
- **Command palette (Cmd+K):** Client-side instant results + async Qdrant semantic search (300ms debounce)
- **Streaming narrative UX:** Investigation reasoning displayed in real-time — core signature pattern
- **18+ routes (up from 6):** SLO dashboard, trust config, notification config, topology, analytics, demo controls, shift handoffs, auto-PR views, service health feeds
- **WCAG 2.1 AA compliance:** axe-core CI gate, keyboard-first navigation
- **Desktop-only:** No responsive mobile design needed (md:1024, lg:1280, xl:1440 breakpoints)
- **Dark-first:** Non-negotiable for 3am incident response

**Scale & Complexity:**

| Dimension | v0.1.0 | v0.2.0 |
|-----------|--------|--------|
| Primary domain | Backend/Platform | Backend/Platform + Real-time Collaboration + External Integrations |
| Complexity level | High | High (increased by trust system, auto-remediation, external integrations) |
| Deployment model | K8s operator spawning investigator pods | Same + demo app pods + sandbox namespaces |
| CRDs | 2 (Source, Investigation) | 5 (+ ServiceLevel, NotificationChannel, Repository) |
| Qdrant collections | 6 | 8+ (+ slo_data, notification_history) |
| UI routes | 6 | 18+ |
| External integrations | 3 (Prometheus, Loki, LLM) | 8+ (+ Slack, PagerDuty, email, webhooks, Git providers) |
| FRs | 47 | 63 |
| NFRs | 16 | 22 |

### Technical Constraints & Dependencies

**Hard Constraints (carried from v0.1.0):**
- K8s-only deployment
- Prometheus/Loki as primary data sources
- LLM API access required (Claude default, configurable via LiteLLM)
- Vector-only KB via Qdrant
- Monorepo structure with Rust operator + Python investigator + Flask UI

**New v0.2.0 Constraints:**
- v0.1.0 codebase is the foundation — extend, don't replace (1,032 tests must continue passing)
- 3 architecture spikes required before specific features: pluggable vector backend, WebSocket infrastructure, agent framework evolution
- Solo developer (eric) + AI-assisted development — wave sequence provides natural cut points
- Demo application must be fully isolated from real infrastructure
- Sandbox environment must be provably network-isolated from production
- 2-tier permission model (admin/user) must be enforced from Wave 1

**Dependencies:**
- Customer's existing K8s cluster (unchanged)
- Customer's Prometheus/Loki stack (unchanged)
- LLM API access via LiteLLM (unchanged)
- Qdrant for KB and vector search (unchanged)
- **New:** Git provider API access (GitHub/GitLab) for auto-PRs
- **New:** Slack Bot Token for rich notifications
- **New:** PagerDuty Events API v2 for bidirectional incident management
- **New:** SMTP for email notifications
- **New:** Sandbox K8s namespace with network isolation for test execution

### Cross-Cutting Concerns Identified

| Concern | Impact | v0.1.0 Status |
|---------|--------|---------------|
| **WebSocket Infrastructure** | Collaboration, streaming narrative, real-time updates | New — SSE exists but insufficient for bidirectional |
| **Permission Model** | All APIs, all UI routes, CRD management, trust level config | New — v0.1.0 had no auth |
| **Trust System** | Investigation decisions, auto-remediation gating, notification urgency | New — foundational to v0.2.0 thesis |
| **Notification Routing** | Multi-channel delivery, customer impact correlation, quiet hours | New |
| **SLO Engine** | Burn rate calculation, investigation prioritization, dashboard | New |
| **PII Scrubbing** | LLM context assembly, investigation logs, KB entries | New — NFR11 |
| **Sandbox Isolation** | Auto-remediation testing, network policies, data separation | New — NFR13 |
| **Streaming Architecture** | Three patterns: ingestion (existing), WebSocket (new), SSE (existing) | Extended |
| **LLM Abstraction** | Provider flexibility, tiered model selection, cost tracking | Existing — unchanged |
| **Error Handling** | KB unavailability buffering, LLM failure fallbacks, notification retry | Extended with new failure modes |
| **Observability** | Beeper's own health, investigation metrics, cost reporting, SLO metrics | Extended |
| **Configuration** | CRDs (5 types now), K8s-native config, credentials management | Extended with 3 new CRDs |

### Critical Path Analysis

**Knowledge Base remains highest risk** — now serving even more access patterns:
1. Write destination (investigations documenting findings) — existing
2. Read source (investigators querying for prior art) — existing
3. Human interface (wiki for SREs) — existing
4. Learning substrate (corrections feeding back) — existing
5. **Auto-PR evidence source** — new: evidence trails pulled into PR descriptions
6. **Notification context source** — new: KB entries referenced in notification justifications
7. **Handoff summary source** — new: active investigation context for shift transitions

**Architecture Spikes are on critical path:**

| Spike | Blocks | Risk if Delayed |
|-------|--------|-----------------|
| WebSocket infrastructure | Wave 3 collaboration features | Must design before Wave 2 completes |
| Agent framework evolution | Wave 2 auto-remediation | Multi-step tool-use beyond current 6-step pipeline |
| Pluggable vector backend | Future scalability | Low immediate risk — can proceed with Qdrant |

**Key Architecture Decisions Needed (v0.2.0 additions):**

| Decision | Options | Assessment |
|----------|---------|------------|
| WebSocket implementation | Native WebSocket / Socket.IO / HTMX ws extension | Must support Flask, HTMX stack |
| Trust system storage | Qdrant collection / CRD status / hybrid | Per-service config + historical data |
| Notification queue | In-process async / Redis / K8s Job | Reliability vs. complexity trade-off |
| Sandbox orchestration | Namespace isolation / separate cluster / virtual cluster | Network isolation provability |
| Auto-PR generation | Direct Git API / CI trigger / K8s Job | Credential scoping, audit trail |
| Permission enforcement | Middleware / decorator / CRD-level RBAC | Consistent across Rust + Python |

**Acceptable MVP Trade-offs (v0.2.0):**

| Trade-off | Rationale |
|-----------|-----------|
| Single-cluster only | Multi-cluster deferred to v0.3.0 |
| Basic RBAC (admin/user) | Fine-grained roles deferred |
| Pluggable vector spike but ship with Qdrant | Abstract interface, one implementation |
| Demo app is simple (3-4 microservices) | Proves thesis without maintenance burden |
| No mobile | Desktop-only per UX spec |

### Component Risk Assessment

| Component | Risk | Change from v0.1.0 |
|-----------|------|---------------------|
| K8s Operator | Medium | Extended with 3 new CRDs, SLO engine, notification engine |
| LLM Integration | Medium | Extended with remediation-tier reasoning |
| **Knowledge Base** | **High** | More access patterns, auto-PR evidence, handoff context |
| Prometheus/Loki Adapters | Low | Unchanged |
| **WebSocket Layer** | **High** | Entirely new — bidirectional collaboration, no prior art in codebase |
| **Trust System** | **High** | Novel concept, gating auto-remediation, per-service state |
| **Auto-Remediation** | **High** | Git integration, sandbox execution, multi-step agent workflow |
| **Notification Engine** | **Medium** | Standard integration patterns, but multi-channel reliability matters |
| **SLO Engine** | **Medium** | Burn rate math is straightforward, but real-time dashboard adds complexity |
| UI (Flask/HTMX) | **High** | Route count triples, Tailwind migration, WebSocket integration, command palette |
| **Demo Application** | **Medium** | Self-contained but must be reliable (NFR18: 10 consecutive runs) |

## Starter Template Evaluation

### Primary Technology Domain

Backend/Platform with K8s Operator + Agentic Services + Web UI — **brownfield** (v0.1.0 fully implemented)

### Technology Stack — Validated & Extended

The v0.1.0 stack is proven with 1,032 passing tests. v0.2.0 extends, not replaces.

**Core Stack (unchanged, validated in v0.1.0):**

| Component | Technology | Version | Status |
|-----------|------------|---------|--------|
| K8s Controller | Rust + kube-rs | 0.95 | Proven |
| Investigator Agents | Python 3.11+ | ^3.11 | Proven |
| Vector Database | Qdrant | v1.15.0 | Proven |
| Web UI | Flask + HTMX + SSE | Flask ^3.0 | Proven — staying on Flask (see decision below) |
| LLM Client | LiteLLM | ^1.30 | Proven |
| Infrastructure | Helm 3 + GitHub Actions | - | Proven |
| API Specification | OpenAPI 3.1 | - | Proven |

**v0.2.0 Additions:**

| Addition | Technology | Rationale |
|----------|------------|-----------|
| CSS Framework | **Tailwind CSS (standalone CLI)** | UX spec decision — utility-first, dark-first. Standalone CLI binary avoids Node.js dependency in Python build chain. JIT mode configured to scan Jinja2 templates. |
| WebSocket | **Flask-SocketIO (async mode)** | Real-time bidirectional collaboration; rooms per investigation, broadcasting, reconnect handling, pytest-compatible test client |
| Slack Integration | slack-sdk (Python) | Rich messages, threads, @mentions, action buttons (FR10) |
| PagerDuty Integration | pdpyras or Events API v2 direct | Bidirectional incident management (FR11) |
| Git Provider Integration | PyGithub / python-gitlab | Auto-PR generation with evidence trails (FR25) |
| Email | smtplib (stdlib) | Alert digests, investigation summaries (FR12) |
| SLO Calculation | Custom (in Rust operator) | Burn rate, customer impact scoring — no external dependency |
| Demo Application | Python + Flask (lightweight) | Purpose-built chaotic microservices, fault injection. Own `demo/` monorepo directory with Dockerfile + pytest harness. |
| Command Palette | **Vanilla JS (~200 lines)** | Dual-mode: instant client-side navigation + async Qdrant semantic search (300ms debounce). No JS framework — compatible with HTMX architecture. |

### Flask vs. Django Decision

**Decision: Stay on Flask.** Evaluated Django migration for v0.2.0 and rejected unanimously.

| Factor | Flask (stay) | Django (migrate) |
|--------|-------------|-----------------|
| Existing tests | 495 passing | All need rewriting |
| ORM benefit | N/A (Qdrant, no SQL DB) | Wasted — no relational database |
| Admin panel | Build what we need | Can't use — data lives in Qdrant |
| Auth/permissions | `require_role()` decorator (~200 lines) | Built-in (strongest argument, but overkill for 2-tier) |
| WebSocket | Flask-SocketIO (proven, pytest test client) | Django Channels (ASGI layer, new complexity) |
| Templates | Jinja2 (UX spec designed for it) | Django templates (syntax migration for every partial) |
| Migration cost | Zero | Full UI rewrite blocking all waves |

**Revisit trigger:** If Flask hits structural limits in v0.3.0+ (e.g., need for relational DB, fine-grained RBAC, multi-tenant isolation), Django migration becomes viable. For v0.2.0 with Qdrant-only data and 2-tier permissions, Flask is the right choice.

### Vector Database Decision (Reaffirmed)

Qdrant remains the correct choice. v0.1.0 validated across 6 collections with 1,032 tests. v0.2.0 extends to 8+ collections.

**Pluggable vector backend spike** (required before Wave 3): Introduce an abstraction layer over Qdrant to enable future backend swaps. Ship v0.2.0 with Qdrant as the sole implementation.

### Frontend Approach (Updated)

**v0.1.0:** Flask + HTMX + SSE with custom CSS (~3,900 lines)
**v0.2.0:** Flask + HTMX + SSE + **Flask-SocketIO** + **Tailwind CSS**

**Tailwind CSS Integration:**
- **Standalone CLI binary** — no Node.js in the build chain. Downloaded as part of Docker multi-stage build.
- **JIT mode** — `content` config includes `beeper_ui/templates/**/*.html` so Tailwind tree-shakes unused classes from Jinja2 templates.
- **`@apply` escape hatch** — existing BEM classes can be incrementally migrated by mapping to Tailwind utilities. New components use Tailwind directly.
- **Dark-first configuration** — custom design tokens from UX spec (indigo primary #6366f1, 5-level surface hierarchy).

**WebSocket Architecture (two-channel pattern):**
- **Flask-SocketIO** owns the bidirectional channel: investigation collaboration (annotations, redirections, approvals), real-time evidence streaming. Uses SocketIO JavaScript client on the frontend. Room-per-investigation for broadcasting.
- **HTMX + SSE** owns the request-response channel: investigation list updates, progress streaming, standard partial swaps, form submissions.
- Two patterns, cleanly separated by concern. SocketIO client for collaboration, HTMX for everything else. No attempt to merge them.

**Notification Delivery (durable outbox pattern):**
- Notifications to external systems (Slack, PagerDuty, email, webhooks) are **externally visible actions** — cannot be lost on process crash.
- **Qdrant payload collection** (`notification_outbox`) as durable outbox. Notifications written to outbox, background worker processes and marks delivered.
- No Redis dependency. Leverages existing Qdrant infrastructure.

**Demo Application:**
- Own `demo/` directory in monorepo with own Dockerfile.
- Fault injection driven by **pytest + httpx harness** — scriptable, deterministic, repeatable (NFR18: 10 consecutive runs).
- Demo app is both a product feature AND a test fixture.

### Architectural Decisions Established by Stack

**Language & Runtime (unchanged):**
- Rust (stable) for K8s operator — memory safety for long-running controller
- Python 3.11+ for investigators, UI, and demo app — rapid iteration, LLM ecosystem

**Vector Storage (unchanged):**
- Qdrant for semantic search and KB storage
- Metadata filtering for structured queries
- 1536-dimensional embeddings (OpenAI-compatible)

**Real-Time Updates (extended):**
- Server-Sent Events (SSE) for unidirectional streaming (investigation progress, list updates) — existing
- **Flask-SocketIO** for bidirectional collaboration (annotations, redirections, live interaction) — new
- HTMX for dynamic UI partial swaps — existing
- Optimistic UI scoped to approve action only; all other HTMX interactions are pessimistic (server round-trip) — per UX spec

**Build & Deployment (extended):**
- Cargo for Rust, Poetry for Python
- Docker multi-stage builds (now including Tailwind CLI standalone binary step)
- Helm charts for K8s deployment
- GitHub Actions for CI/CD
- ghcr.io for container registry

## Core Architectural Decisions

### Decision Priority Analysis

**Already Decided (v0.1.0, validated):**
- Rust + kube-rs operator, Python investigator, Flask + HTMX UI, Qdrant, LiteLLM
- Monorepo, Helm deployment, OpenAPI 3.1, RFC 7807 errors, snake_case everywhere
- K8s Job-based investigation spawning

**Critical Decisions (v0.2.0 — block implementation):**
- Permission model enforcement across Rust + Python
- Trust system storage and gating logic
- WebSocket architecture (Flask-SocketIO + SocketIO client)
- Notification delivery with durable outbox
- Auto-remediation pipeline (agent framework evolution)
- New CRD schemas (ServiceLevel, NotificationChannel, Repository)

**Important Decisions (shape architecture):**
- SLO engine placement (operator — decided)
- Sandbox namespace orchestration
- Demo application architecture
- Command palette search architecture

**Deferred Decisions (post v0.2.0):**
- Multi-cluster support
- Fine-grained RBAC (beyond admin/user)
- SaaS multi-tenancy
- Mobile application
- Graph DB for KB (evaluate in v0.3.0)

### Data Architecture

| Decision | Choice | Version/Details |
|----------|--------|-----------------|
| Vector Database | Qdrant (unchanged) | v1.15.0 |
| Investigation State | Qdrant `investigations` collection | Existing — extended with trust/SLO fields |
| KB Documents | Qdrant `knowledge` collection | Existing — extended with bi-directional links |
| SLO Data | Qdrant `slo_snapshots` collection (payload-only) | New — burn rate snapshots for dashboard |
| Notification Outbox | Qdrant `notification_outbox` collection (payload-only) | New — durable delivery queue |
| Trust Configuration | Qdrant `service_trust_levels` collection | Existing — extended with confidence gates + accuracy history |
| CRD State | K8s etcd (via CRD status) | Existing + 3 new CRDs |

**New CRD Schemas:**

```yaml
# ServiceLevel CRD (Wave 1)
apiVersion: beeper.dev/v1
kind: ServiceLevel
metadata:
  name: payments-slo
spec:
  service: payment-service
  sli:
    type: availability  # availability | latency | error_rate
    metric: http_requests_total
    good_selector: '{status=~"2.."}'
    total_selector: '{}'
  objective:
    target: 0.999        # 99.9%
    window: 30d
  burn_rate_alerts:
    - severity: warning
      short_window: 5m
      long_window: 1h
      factor: 14.4
    - severity: critical
      short_window: 5m
      long_window: 6h
      factor: 6
```

```yaml
# NotificationChannel CRD (Wave 1)
apiVersion: beeper.dev/v1
kind: NotificationChannel
metadata:
  name: sre-slack
spec:
  type: slack            # slack | pagerduty | email | webhook
  config:
    channel: "#sre-alerts"
    mention_users: true
  credentials_secret: slack-bot-token
  routing:
    min_severity: high   # only high/critical
    services: ["*"]      # all services, or specific list
    quiet_hours:
      enabled: true
      start: "22:00"
      end: "08:00"
      timezone: "America/New_York"
      escalation_override: true  # critical bypasses quiet hours
```

```yaml
# Repository CRD (Wave 2)
apiVersion: beeper.dev/v1
kind: Repository
metadata:
  name: payments-repo
spec:
  url: "https://github.com/org/payment-service"
  provider: github       # github | gitlab
  credentials_secret: github-token-payments
  branch_policy:
    base_branch: main
    pr_branch_prefix: "beeper/"
  coding_standards:
    language: python
    linter: ruff
    test_command: "pytest"
```

**Qdrant Collections (v0.2.0 complete):**

| Collection | Type | Contents | New/Existing |
|------------|------|----------|-------------|
| `investigations` | Vector (1536d) | Investigation state, findings, root cause, SLO impact, trust level context | Extended |
| `knowledge` | Vector (1536d) | KB entries with bi-directional investigation links | Extended |
| `knowledge_versions` | Payload-only | Version snapshots | Existing |
| `corrections` | Payload-only | Correction conversations | Existing |
| `learning_patterns` | Payload-only | Diff analysis patterns | Existing |
| `service_trust_levels` | Payload-only | Trust config + confidence gates + accuracy history | Extended |
| `slo_snapshots` | Payload-only | Burn rate snapshots, error budget data | **New** |
| `notification_outbox` | Payload-only | Durable notification delivery queue | **New** |

### Authentication & Security

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Permission Model | 2-tier admin/user via `require_role()` decorator | Simple, sufficient for v0.2.0. Flask middleware sets user context from K8s ServiceAccount or header. |
| Trust Level Access | Admin-only for trust config, confidence gates | NFR12 — prevents unauthorized autonomy escalation |
| API Security | Network policies + role enforcement | Operator API restricted to UI pod; external access via UI only |
| Secrets Storage | K8s Secrets (unchanged) | All integration credentials (Slack, PagerDuty, Git tokens, LLM keys) |
| Repo Credentials | Scoped per-repo tokens via Repository CRD | NFR9 — never org-wide tokens |
| PII Scrubbing | Pre-LLM context filter in investigator | NFR11 — regex + pattern-based scrub before any LLM call |
| Sandbox Isolation | K8s NetworkPolicy-isolated namespace | NFR13 — provably no production data leakage |

**Permission Enforcement Pattern:**

```python
# Flask decorator — applied to every route
@require_role("admin")  # or "user" (default)
def configure_trust_level(service_name):
    ...

# Middleware sets g.user_role from:
# 1. K8s ServiceAccount token (production)
# 2. X-Beeper-Role header (development)
# 3. Default "user" if no auth configured
```

**Admin-only operations:**
- Trust level configuration (FR16, FR22)
- ServiceLevel CRD management (FR1, FR5)
- Repository CRD management (FR23)
- Error budget policies (FR5)
- Noise report access (FR20)

**User operations:**
- View/interact with investigations (FR32-35)
- Configure notification channels (FR8-9)
- KB read/write/correct (FR38-42)
- Approve/reject fixes within trust level (FR35)
- View dashboards (FR6, FR50, FR52)

### API & Communication Patterns

| Decision | MVP | Scale Target |
|----------|-----|--------------|
| Inter-service | REST/HTTP + K8s Jobs (unchanged) | NATS JetStream |
| API Specification | OpenAPI 3.1 (unchanged) | Generated clients for Rust + Python |
| Error Format | RFC 7807 Problem Details (unchanged) | Standard `type`, `title`, `status`, `detail` |
| UI Real-time (unidirectional) | SSE (unchanged) | SSE or NATS subscription |
| UI Real-time (bidirectional) | **Flask-SocketIO** | WebSocket native or NATS |
| Notification Delivery | **Durable outbox + async worker** | Dedicated notification service |

**New Operator API Endpoints (v0.2.0):**

```
# SLO (Wave 1)
GET  /api/v1/slo/services                    # List services with SLO status
GET  /api/v1/slo/services/{name}             # Service SLO detail + burn rate
GET  /api/v1/slo/services/{name}/budget      # Error budget status

# Trust (Wave 2)
GET  /api/v1/trust/services                  # List trust levels per service
GET  /api/v1/trust/services/{name}           # Trust config + accuracy history
PUT  /api/v1/trust/services/{name}           # Update trust level (admin)
GET  /api/v1/trust/services/{name}/accuracy  # Accuracy metrics

# Notifications (Wave 1)
GET  /api/v1/notifications/channels          # List configured channels
POST /api/v1/notifications/test              # Send test notification
GET  /api/v1/notifications/audit             # Notification history + false page tracking

# Investigations (extended)
POST /api/v1/investigations/{id}/approve     # Approve proposed fix
POST /api/v1/investigations/{id}/reject      # Reject with reason
POST /api/v1/investigations/{id}/annotate    # Add human annotation
GET  /api/v1/investigations/{id}/evidence    # Evidence trail with references
GET  /api/v1/investigations/{id}/handoff     # Shift handoff summary

# Remediation (Wave 2)
GET  /api/v1/remediation/{id}                # Remediation status
GET  /api/v1/remediation/{id}/pr             # Auto-PR details + evidence
GET  /api/v1/remediation/{id}/sandbox        # Sandbox test results

# Search (for command palette)
GET  /api/v1/search?q={query}                # Semantic search across investigations + KB
```

**WebSocket Events (Flask-SocketIO):**

```
# Client → Server
join_investigation(investigation_id)      # Join investigation room
leave_investigation(investigation_id)     # Leave room
annotate(investigation_id, text)          # Human annotation
redirect(investigation_id, instruction)   # Redirect investigation
approve_fix(investigation_id)             # Approve proposed fix
reject_fix(investigation_id, reason)      # Reject with reason

# Server → Client (broadcast to room)
evidence_update(step, finding, reference) # New evidence found
confidence_update(score, breakdown)       # Confidence score change
fix_proposed(fix_details, confidence)     # Fix ready for review
fix_applied(result, metrics)              # Fix execution result
investigation_complete(summary)           # Investigation concluded
```

### LLM Integration (Extended)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| LLM Client | LiteLLM (unchanged) | Provider flexibility, streaming |
| Default Provider | Anthropic Claude (unchanged) | Per PRD specification |
| Tiered Models | Haiku → Sonnet → Opus (unchanged) | Cost optimization |
| **New tier** | `remediation` | Fix generation, PR writing, test plan design — uses deep_rca model |

**Model Routing (v0.2.0):**
- `screening`: claude-3-haiku (fast triage, notification justification)
- `investigation`: claude-sonnet-4 (balanced RCA, signal correlation)
- `deep_rca`: claude-opus-4 (complex multi-layer correlation)
- `remediation`: claude-opus-4 (fix generation, test plan design, PR writing)

**PII Scrubbing (new — NFR11):**
Applied before every LLM call in the investigator:
1. Regex patterns for common PII (emails, IPs, tokens, passwords in env vars)
2. Configurable per-service scrub rules via investigation context
3. Replacement with tagged placeholders (`[SCRUBBED:email]`) to preserve context
4. Audit log of scrubbed content (stored locally, never sent to LLM)

### Trust System Architecture (New)

**Trust Levels:**

| Level | Name | Beeper Behavior | Approval Required |
|-------|------|-----------------|-------------------|
| TL1 | Advisory | Investigate + document + recommend | All actions need human |
| TL2 | Notify + Recommend | All of TL1 + proactive notification with evidence | All actions need human |
| TL3 | Auto-fix + Review | All of TL2 + auto-apply fixes above confidence gate | Post-action review |
| TL4 | Autonomous + Audit | All of TL3 + expanded fix scope | Audit trail only |
| TL5 | Fully Autonomous | Full autonomy within configured scope | None (logged) |

**Confidence Gating:**
- Each trust level has a configurable minimum confidence threshold (default: TL3=90%, TL4=85%, TL5=80%)
- Actions below threshold fall back to the next lower trust level's behavior
- Confidence score is composite: LLM confidence + KB match quality + signal correlation strength

**Storage:** `service_trust_levels` Qdrant collection stores per-service config + accuracy history. Trust level changes are versioned (who changed, when, from/to).

### SLO Engine Architecture (New)

**Placement:** Rust operator — SLO burn rate calculation runs alongside anomaly detection in the operator process. No separate service.

**Data Flow:**
```
Prometheus metrics → Operator ingestion → SLO calculator → slo_snapshots (Qdrant)
                                                         → Investigation priority scoring
                                                         → Notification urgency weighting
```

**Customer Impact Scoring:** Anomalies correlated with SLO breach severity. An anomaly affecting a 99.9% SLO with 50% budget remaining scores higher than one affecting a 99% SLO with 90% budget remaining.

### Notification Engine Architecture (New)

**Durable Outbox Pattern:**
```
Event (investigation started/completed/fix proposed)
    → Notification rules engine (severity, service, time of day, quiet hours)
    → Write to notification_outbox collection (Qdrant)
    → Background worker reads outbox, delivers to channel, marks delivered
    → Failed deliveries retry with exponential backoff
    → False pages tracked in notification audit (FR15)
```

**Channel Implementations:**
- **Slack:** Rich blocks with investigation summary, evidence links, action buttons (approve/view)
- **PagerDuty:** Create incident on critical; acknowledge on investigation start; resolve on fix verified
- **Email:** SMTP digests — daily summary or immediate for critical
- **Webhook:** POST with investigation payload for CI/CD triggers, Jira, status pages

### Auto-Remediation Architecture (New)

**Agent Framework Evolution:**
The v0.1.0 investigator uses a fixed 6-step pipeline. v0.2.0 extends this with a **tool-use pattern** for remediation:

```
Existing pipeline: Impact → KB Query → Signal Correlation → RCA → Recommendations → Documentation

New remediation extension (after RCA, when trust level allows):
  → Fix Generation (LLM designs fix based on RCA)
  → Test Plan Design (LLM designs verification test)
  → Sandbox Execution (if sandbox available: deploy fix + run test)
  → Fix Verification (monitor post-fix metrics)
  → PR Generation (if Repository CRD configured)
  → KB Update (document proven fix)
```

The remediation steps are **conditional** — they only execute when trust level and confidence gate allow. The existing 6-step pipeline remains the core; remediation is an extension, not a replacement.

**Auto-PR Flow:**
```
Investigator (Python)
    → Clone repo (from Repository CRD config)
    → Create branch (beeper/{investigation_id})
    → Generate fix (LLM + coding standards from CRD)
    → Commit with evidence metadata
    → Push + create PR via Git provider API
    → PR body includes: evidence trail, KB references, sandbox test results
```

### Infrastructure & Deployment (Extended)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Repository | Monorepo (unchanged) | Single repo, solo developer |
| Packaging | Helm chart (unchanged) | Single install, all components |
| CI/CD | GitHub Actions (unchanged) | Open source friendly |
| Registry | ghcr.io (unchanged) | Public for open source |
| **Demo App** | `demo/` monorepo directory | Own Dockerfile, pytest harness, fault injection |
| **Sandbox** | NetworkPolicy-isolated K8s namespace | Provable isolation for test execution |
| **Tailwind Build** | Standalone CLI in Docker multi-stage | No Node.js dependency |

**K8s Resources (v0.2.0):**
- `Deployment: beeper-operator` — Rust controller (1 replica, unchanged)
- `Deployment: beeper-ui` — Flask UI (1+ replicas, unchanged)
- `Job: beeper-investigator-{id}` — Spawned per investigation (extended with remediation steps)
- `StatefulSet: qdrant` — Vector database (unchanged)
- **New:** `Deployment: beeper-demo-*` — Demo app microservices (3-4 pods)
- **New:** `Namespace: beeper-sandbox` — NetworkPolicy-isolated sandbox
- **New:** CRDs: `ServiceLevel`, `NotificationChannel`, `Repository`

### Decision Impact Analysis

**Implementation Sequence:**
1. Permission model (decorator + middleware) — foundation for everything
2. New CRD schemas (ServiceLevel, NotificationChannel, Repository)
3. SLO engine in operator + slo_snapshots collection
4. Notification outbox + channel implementations
5. Trust system storage + confidence gating
6. WebSocket (Flask-SocketIO) infrastructure
7. Agent framework extension for remediation
8. Auto-PR pipeline
9. Demo application
10. Tailwind CSS migration (incremental, parallel with above)

**Cross-Component Dependencies:**
- Permission model must exist before any new API endpoints
- SLO engine feeds into notification urgency AND investigation priority
- Trust system gates auto-remediation AND notification behavior
- WebSocket infrastructure needed before collaboration features
- Repository CRD must exist before auto-PR generation
- Sandbox namespace must exist before fix verification

## Implementation Patterns & Consistency Rules

### Pattern Categories Defined

**Critical Conflict Points Identified:** 6 areas where AI agents could make different choices across Rust/Python polyglot codebase.

### Naming Patterns

**JSON Field Naming:**
- **Convention:** `snake_case` everywhere
- **Rust:** Use `#[serde(rename_all = "snake_case")]` on all structs
- **Python:** Native (Pydantic models use snake_case by default)

```rust
// Rust
#[derive(Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
struct Investigation {
    investigation_id: String,
    started_at: DateTime<Utc>,
    root_cause_hypothesis: Option<String>,
}
```

```python
# Python
class Investigation(BaseModel):
    investigation_id: str
    started_at: datetime
    root_cause_hypothesis: str | None
```

**API Endpoint Naming:**
- **Base path:** `/api/v1/`
- **Resources:** Plural nouns (`/investigations`, `/sources`)
- **Actions:** Verb suffixes where needed (`/investigations/{id}/resolve`)
- **Query params:** `snake_case` (`?service_name=payments`)

| Resource | Endpoints |
|----------|-----------|
| Investigations | `GET /api/v1/investigations`, `GET /api/v1/investigations/{id}` |
| Knowledge | `GET /api/v1/knowledge`, `POST /api/v1/knowledge`, `PATCH /api/v1/knowledge/{id}` |
| Sources | `GET /api/v1/sources`, `POST /api/v1/sources`, `DELETE /api/v1/sources/{id}` |

**Qdrant Naming:**
- **Collections:** `snake_case` (`investigations`, `knowledge`)
- **Fields:** `snake_case` (`investigation_id`, `created_at`, `confidence_level`)
- **Payload fields:** Match JSON field naming exactly

**Code Naming by Language:**

| Language | Functions/Methods | Variables | Files | Classes/Structs |
|----------|-------------------|-----------|-------|-----------------|
| Rust | `snake_case` | `snake_case` | `snake_case.rs` | `PascalCase` |
| Python | `snake_case` | `snake_case` | `snake_case.py` | `PascalCase` |

### Structure Patterns

**Monorepo Organization:**
```
beeper/
├── operator/                 # Rust K8s operator
│   ├── src/
│   │   ├── main.rs
│   │   ├── controller.rs
│   │   └── crd.rs
│   ├── tests/               # Rust tests (separate directory)
│   └── Cargo.toml
├── investigator/            # Python investigator agent
│   ├── beeper_investigator/
│   │   ├── __init__.py
│   │   ├── agent.py
│   │   ├── llm.py
│   │   └── kb.py
│   ├── tests/               # Python tests (separate directory)
│   └── pyproject.toml
├── ui/                      # Flask web UI
│   ├── beeper_ui/
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── routes/
│   │   └── templates/
│   ├── tests/
│   └── pyproject.toml
├── openapi/                 # Shared API specifications
│   └── beeper-api.yaml
├── helm/                    # Helm chart
│   └── beeper/
└── .github/workflows/       # CI/CD
```

**Test Organization:**
- Tests in separate `tests/` directory per component
- Test files mirror source structure
- Integration tests in `tests/integration/`

### Format Patterns

**API Response Format:**

Success responses return data directly:
```json
{
  "investigation_id": "inv-abc123",
  "status": "investigating",
  "started_at": "2026-01-28T14:30:00Z"
}
```

List responses include metadata:
```json
{
  "items": [...],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

**Error Response Format (RFC 7807):**
```json
{
  "type": "https://beeper.dev/errors/investigation-not-found",
  "title": "Investigation Not Found",
  "status": 404,
  "detail": "Investigation inv-abc123 does not exist",
  "instance": "/api/v1/investigations/inv-abc123"
}
```

**Date/Time Format:**
- **Always:** ISO 8601 with UTC timezone
- **Format:** `YYYY-MM-DDTHH:MM:SSZ`
- **Example:** `2026-01-28T14:30:00Z`
- **Rust:** `chrono::DateTime<Utc>`
- **Python:** `datetime.datetime` with `timezone.utc`

### Communication Patterns

**Event Naming (for NATS at scale):**
- **Pattern:** `beeper.{component}.{action}`
- **Examples:**
  - `beeper.investigation.started`
  - `beeper.investigation.progress`
  - `beeper.investigation.completed`
  - `beeper.kb.entry_created`

**Event Payload Structure:**
```json
{
  "event_id": "evt-xyz789",
  "event_type": "beeper.investigation.progress",
  "timestamp": "2026-01-28T14:30:00Z",
  "data": {
    "investigation_id": "inv-abc123",
    "step": "correlating_signals",
    "progress_pct": 45
  }
}
```

**Investigation State Machine:**
```
pending → started → investigating → [correlating|querying_kb|reasoning] → completed
                                                                      ↘ failed
```

### Process Patterns

**Logging Format (Structured JSON):**
```json
{
  "timestamp": "2026-01-28T14:30:00Z",
  "level": "INFO",
  "component": "investigator",
  "investigation_id": "inv-abc123",
  "message": "Starting signal correlation",
  "context": {
    "service": "payments",
    "signal_count": 47
  }
}
```

**Required Log Fields:**
- `timestamp` (ISO 8601 UTC)
- `level` (DEBUG, INFO, WARN, ERROR)
- `component` (operator, investigator, ui)
- `message` (human-readable)

**Optional Context Fields:**
- `investigation_id` (when applicable)
- `service` (target service being investigated)
- `error` (error details when level=ERROR)

**Error Handling:**
- Use RFC 7807 for all API errors
- Log errors with full context before returning
- Never expose internal details in user-facing errors
- Include `request_id` for correlation

**HTTP Status Code Usage:**

| Code | Usage |
|------|-------|
| 200 | Successful GET, PATCH |
| 201 | Successful POST (created) |
| 204 | Successful DELETE |
| 400 | Invalid request (validation failed) |
| 404 | Resource not found |
| 409 | Conflict (duplicate, invalid state) |
| 500 | Internal server error |

### Enforcement Guidelines

**All AI Agents MUST:**
1. Use `snake_case` for all JSON fields, API params, and Qdrant fields
2. Include required log fields in all log statements
3. Return RFC 7807 error responses for all error cases
4. Use ISO 8601 UTC for all timestamps
5. Follow the file/directory structure defined above

**Pattern Verification:**
- OpenAPI spec validates API patterns
- Pydantic/serde enforce JSON field naming
- CI linting enforces code naming conventions
- Log aggregation validates log format

### Anti-Patterns to Avoid

| Anti-Pattern | Correct Pattern |
|--------------|-----------------|
| `camelCase` JSON fields | `snake_case` |
| `/api/investigation` (singular) | `/api/v1/investigations` (plural) |
| Plain text logs | Structured JSON logs |
| Local timestamps | UTC timestamps |
| Custom error format | RFC 7807 |
| `userId` in Python | `user_id` |

## Project Structure & Boundaries

### Complete Project Directory Structure

```
beeper/
├── README.md
├── LICENSE                              # Apache 2.0
├── CONTRIBUTING.md
├── VISION.md
├── .gitignore
├── docker-compose.yaml                  # Local dev: Qdrant + demo app services
├── tailwind.config.js                   # Tailwind standalone CLI config (scans Jinja2 templates)
│
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                       # Matrix: Rust (fmt+clippy+test), Python investigator
│   │   │                                # (ruff+pytest), Python UI (ruff+pytest), Helm lint,
│   │   │                                # Tailwind build, demo app build
│   │   ├── release.yml                  # Build + push containers to ghcr.io on tag
│   │   └── helm-lint.yml                # Validate Helm chart
│   └── CODEOWNERS
│
├── openapi/                             # Shared API specifications
│   ├── beeper-api.yaml                  # OpenAPI 3.1 spec (extended with SLO, trust,
│   │                                    # notification, remediation, search endpoints)
│   └── schemas/
│       ├── investigation.yaml           # Extended with trust/SLO fields
│       ├── knowledge.yaml
│       ├── source.yaml
│       ├── service-level.yaml           # New: SLO schema definitions
│       ├── notification.yaml            # New: Notification channel + outbox schemas
│       ├── trust.yaml                   # New: Trust level + confidence gate schemas
│       └── remediation.yaml             # New: Remediation + PR schemas
│
├── operator/                            # Rust K8s operator
│   ├── Cargo.toml
│   ├── Cargo.lock
│   ├── Dockerfile
│   ├── src/
│   │   ├── main.rs                      # Entry point: wires all subsystems, spawns tokio tasks
│   │   ├── lib.rs                       # Library exports
│   │   ├── api.rs                       # axum REST API (extended: SLO, trust, notification,
│   │   │                                # remediation, search endpoints)
│   │   ├── health.rs                    # GET /healthz, GET /readyz
│   │   ├── investigator_job.rs          # Job spawning (extended with remediation env vars)
│   │   ├── llm.rs                       # LLM provider config from K8s Secrets
│   │   ├── controllers/
│   │   │   ├── mod.rs
│   │   │   ├── investigation.rs         # Investigation CRD controller (existing)
│   │   │   ├── source.rs                # Source CRD controller (existing)
│   │   │   ├── service_level.rs         # New: ServiceLevel CRD controller — reconciles
│   │   │   │                            # SLO targets, wires burn rate alerts
│   │   │   ├── notification_channel.rs  # New: NotificationChannel CRD controller —
│   │   │   │                            # validates credentials, registers channel
│   │   │   └── repository.rs            # New: Repository CRD controller — validates
│   │   │                                # connectivity, caches branch policies
│   │   ├── crds/
│   │   │   ├── mod.rs
│   │   │   ├── investigation.rs         # Investigation struct (extended status fields)
│   │   │   ├── source.rs                # Source struct (existing)
│   │   │   ├── service_level.rs         # New: ServiceLevel CRD definition
│   │   │   ├── notification_channel.rs  # New: NotificationChannel CRD definition
│   │   │   └── repository.rs            # New: Repository CRD definition
│   │   ├── detection/
│   │   │   ├── mod.rs                   # DetectionConfig, DetectionStats
│   │   │   ├── consumer.rs              # DetectionConsumer (extended with SLO scoring)
│   │   │   ├── ewma.rs                  # EwmaDetector (existing)
│   │   │   ├── logs.rs                  # LogDetector (existing)
│   │   │   ├── metrics.rs               # MetricDetector (existing)
│   │   │   └── types.rs                 # AnomalySignal (extended with slo_impact field)
│   │   ├── ingestion/
│   │   │   ├── mod.rs
│   │   │   ├── buffer.rs                # IngestionBuffer with backpressure (existing)
│   │   │   ├── loki.rs                  # POST /loki/api/v1/push (existing)
│   │   │   └── prometheus.rs            # POST /api/v1/write (existing)
│   │   ├── slo/                         # New: SLO engine (runs in operator process)
│   │   │   ├── mod.rs
│   │   │   ├── calculator.rs            # SLO compliance + burn rate computation
│   │   │   ├── burn_rate.rs             # Multi-window burn rate alerting
│   │   │   ├── budget.rs                # Error budget tracking + policy enforcement
│   │   │   └── impact.rs                # Customer impact scoring for anomaly prioritization
│   │   ├── notifications/               # New: Notification routing (operator-side)
│   │   │   ├── mod.rs
│   │   │   ├── router.rs               # Rule engine: severity, service, time, quiet hours
│   │   │   └── audit.rs                # False page tracking (FR15)
│   │   └── sources/
│   │       ├── mod.rs
│   │       ├── loki.rs                  # LokiClient (existing)
│   │       └── prometheus.rs            # PrometheusClient (existing)
│   └── tests/
│       ├── controller_test.rs
│       ├── slo_test.rs                  # New: SLO calculator + burn rate tests
│       ├── notification_test.rs         # New: Routing rules + audit tests
│       └── integration/
│           ├── crd_test.rs
│           └── slo_integration_test.rs  # New: End-to-end SLO → priority scoring
│
├── investigator/                        # Python investigator agent
│   ├── pyproject.toml
│   ├── poetry.lock
│   ├── Dockerfile
│   ├── beeper_investigator/
│   │   ├── __init__.py
│   │   ├── main.py                      # Entry point (K8s Job)
│   │   ├── agent.py                     # InvestigatorAgent (extended: remediation steps)
│   │   ├── context.py                   # InvestigationContext (extended: trust, SLO fields)
│   │   ├── k8s/
│   │   │   ├── __init__.py
│   │   │   └── status.py               # InvestigationStatusUpdater (existing)
│   │   ├── kb/
│   │   │   ├── __init__.py
│   │   │   ├── client.py               # KBClient (extended: new collections)
│   │   │   └── schemas.py              # Pydantic models (extended: bi-directional links)
│   │   ├── llm/
│   │   │   ├── __init__.py
│   │   │   ├── cache.py                # LRU response cache (existing)
│   │   │   ├── client.py              # LlmClient (extended: remediation tier)
│   │   │   ├── cost.py                # CostTracker (existing)
│   │   │   ├── spending_cap.py        # SpendingCapEnforcer (existing)
│   │   │   ├── prompts.py             # Investigation prompts (existing)
│   │   │   └── scrubber.py            # New: PII scrubbing — regex patterns, tagged
│   │   │                              # placeholders, audit log (NFR11)
│   │   ├── sources/
│   │   │   ├── __init__.py
│   │   │   ├── loki.py                # LokiClient (existing)
│   │   │   └── prometheus.py          # PrometheusClient (existing)
│   │   ├── correlation/
│   │   │   ├── __init__.py
│   │   │   └── signals.py             # Signal correlation (existing)
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── investigation.py       # Investigation model (extended: trust_level, slo_impact)
│   │   │   └── finding.py             # Finding/hypothesis models (existing)
│   │   ├── steps/
│   │   │   ├── __init__.py            # InvestigationStep protocol + StepResult
│   │   │   ├── impact_assessment.py   # Step 1: CustomerImpactStep (extended: SLO scoring)
│   │   │   ├── kb_query.py            # Step 2: KBQueryStep (existing)
│   │   │   ├── signal_correlation.py  # Step 3: SignalCorrelationStep (existing)
│   │   │   ├── rca_hypothesis.py      # Step 4: RCAHypothesisStep (existing)
│   │   │   ├── resolution_recommendations.py  # Step 5: ResolutionRecommendationStep (existing)
│   │   │   └── investigation_documentation.py # Step 6: InvestigationDocumentationStep (existing)
│   │   └── remediation/               # New: Auto-remediation steps (conditional, trust-gated)
│   │       ├── __init__.py
│   │       ├── fix_generator.py       # LLM-driven fix generation from RCA
│   │       ├── test_planner.py        # LLM-designed verification test plans
│   │       ├── sandbox_executor.py    # Deploy fix to sandbox, run tests
│   │       ├── verifier.py            # Post-fix metric monitoring
│   │       └── pr_generator.py        # Clone repo, create branch, commit, push, open PR
│   └── tests/
│       ├── __init__.py
│       ├── test_agent.py
│       ├── test_context.py
│       ├── test_impact_assessment.py
│       ├── test_investigation_documentation.py
│       ├── test_k8s_status.py
│       ├── test_kb_client.py
│       ├── test_kb_query.py
│       ├── test_llm_cache.py
│       ├── test_llm_client.py
│       ├── test_llm_embedding.py
│       ├── test_llm_screening.py
│       ├── test_main.py
│       ├── test_rca_hypothesis.py
│       ├── test_resolution_recommendations.py
│       ├── test_signal_correlation.py
│       ├── test_sources.py
│       ├── test_spending_caps.py
│       ├── test_step_pipeline.py
│       ├── test_scrubber.py           # New: PII scrubbing tests
│       ├── test_remediation.py        # New: Remediation pipeline tests
│       └── integration/
│           ├── test_investigation_flow.py
│           └── test_remediation_flow.py  # New: End-to-end remediation integration
│
├── ui/                                  # Flask web UI
│   ├── pyproject.toml                   # Extended: flask-socketio, slack-sdk, pagerduty deps
│   ├── poetry.lock
│   ├── Dockerfile                       # Extended: Tailwind CLI build stage
│   ├── beeper_ui/
│   │   ├── __init__.py
│   │   ├── app.py                       # Flask app factory (extended: SocketIO init,
│   │   │                                # permission middleware registration)
│   │   ├── config.py                    # Config classes (extended: SocketIO, notification settings)
│   │   ├── auth/                        # New: Permission enforcement
│   │   │   ├── __init__.py
│   │   │   ├── decorators.py            # @require_role("admin"|"user") decorator
│   │   │   └── middleware.py            # User context from K8s SA / X-Beeper-Role header
│   │   ├── routes/
│   │   │   ├── __init__.py              # register_blueprints() — extended
│   │   │   ├── health.py               # GET /health (existing)
│   │   │   ├── investigations.py       # /investigations (extended: approve/reject, annotate,
│   │   │   │                           # evidence trail, handoff summary)
│   │   │   ├── knowledge.py            # /knowledge (extended: bi-directional links, service views)
│   │   │   ├── metrics.py              # /metrics: MTTR trends (existing)
│   │   │   ├── sources.py              # /sources (existing)
│   │   │   ├── spending.py             # /spending (existing)
│   │   │   ├── slo.py                  # New: /slo — SLO dashboard, burn rates, error budgets
│   │   │   ├── trust.py               # New: /trust — trust level config, accuracy history,
│   │   │   │                          # noise reports (admin)
│   │   │   ├── notifications.py       # New: /notifications — channel config, routing rules,
│   │   │   │                          # test send, audit trail
│   │   │   ├── remediation.py         # New: /remediation — status, PRs, sandbox results
│   │   │   ├── analytics.py           # New: /analytics — reliability scores, trends, investor
│   │   │   │                          # reports
│   │   │   ├── handoff.py             # New: /handoff — shift handoff summaries
│   │   │   ├── demo.py               # New: /demo — demo control panel, scenario execution
│   │   │   └── search.py             # New: /search — command palette backend (Qdrant search)
│   │   ├── websocket/                 # New: Flask-SocketIO event handlers
│   │   │   ├── __init__.py            # SocketIO initialization + namespace registration
│   │   │   └── investigation.py       # join/leave room, annotate, redirect, approve/reject,
│   │   │                              # server-side evidence/confidence/fix broadcasts
│   │   ├── notifications/             # New: Notification channel implementations
│   │   │   ├── __init__.py
│   │   │   ├── outbox.py             # Durable outbox: write to Qdrant, background worker,
│   │   │   │                         # retry with exponential backoff
│   │   │   ├── slack.py              # Rich blocks, threads, @mentions, action buttons
│   │   │   ├── pagerduty.py          # Create/acknowledge/resolve incidents
│   │   │   ├── email.py              # SMTP digests + immediate critical alerts
│   │   │   └── webhook.py            # POST payloads to external systems
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── investigation_service.py  # Extended: approve/reject, annotate, evidence
│   │   │   ├── kb_service.py             # Extended: bi-directional links, service views
│   │   │   ├── correction_service.py     # Existing
│   │   │   ├── embedding_service.py      # Existing
│   │   │   ├── health_service.py         # Existing
│   │   │   ├── import_service.py         # Existing
│   │   │   ├── learning_service.py       # Existing
│   │   │   ├── metrics_service.py        # Existing
│   │   │   ├── source_service.py         # Existing
│   │   │   ├── spending_service.py       # Existing
│   │   │   ├── slo_service.py            # New: SLO data from operator API
│   │   │   ├── trust_service.py          # New: Trust level CRUD via operator API
│   │   │   └── search_service.py         # New: Qdrant semantic search for command palette
│   │   ├── templates/
│   │   │   ├── base.html                # Extended: Tailwind classes, SocketIO script,
│   │   │   │                            # command palette markup
│   │   │   ├── components/              # New: Shared Jinja2 partials (HTMX fragments)
│   │   │   │   ├── command-palette.html # Cmd+K overlay
│   │   │   │   ├── notification-toast.html
│   │   │   │   └── trust-badge.html
│   │   │   ├── investigations/
│   │   │   │   ├── list.html            # Extended: SLO impact column, trust badge
│   │   │   │   ├── detail.html          # Extended: evidence trail, SocketIO collaboration,
│   │   │   │   │                        # approve/reject buttons, annotation input
│   │   │   │   ├── evidence.html        # New: Evidence trail panel
│   │   │   │   └── handoff.html         # New: Shift handoff summary
│   │   │   ├── knowledge/
│   │   │   │   ├── index.html           # Existing
│   │   │   │   ├── entry.html           # Extended: bi-directional links, validation status
│   │   │   │   ├── edit.html            # Existing
│   │   │   │   └── diff.html            # Existing
│   │   │   ├── sources/
│   │   │   │   └── status.html          # Existing
│   │   │   ├── slo/                     # New: SLO views
│   │   │   │   ├── dashboard.html       # Compliance, burn rates, error budgets
│   │   │   │   └── service.html         # Per-service SLO detail
│   │   │   ├── trust/                   # New: Trust management views
│   │   │   │   ├── overview.html        # Per-service trust levels, accuracy
│   │   │   │   └── configure.html       # Admin: trust level + confidence gate config
│   │   │   ├── notifications/           # New: Notification views
│   │   │   │   ├── channels.html        # Channel config list
│   │   │   │   └── audit.html           # Notification history, false page tracking
│   │   │   ├── remediation/             # New: Remediation views
│   │   │   │   ├── status.html          # Fix progress: generation → test → sandbox → PR
│   │   │   │   └── pr.html              # Auto-PR detail with evidence
│   │   │   ├── analytics/               # New: Analytics views
│   │   │   │   ├── dashboard.html       # Reliability scores, MTTR trends, trust progression
│   │   │   │   └── investor.html        # Diana-facing investor report
│   │   │   └── demo/                    # New: Demo control panel
│   │   │       └── control.html         # Scenario selection, fault injection, lifecycle view
│   │   ├── static/
│   │   │   ├── css/
│   │   │   │   ├── main.css             # Existing custom CSS (~3,900 lines)
│   │   │   │   └── tailwind.css         # New: Tailwind output (built by CLI)
│   │   │   └── js/
│   │   │       ├── htmx.min.js          # Existing
│   │   │       ├── socketio.min.js      # New: Socket.IO client
│   │   │       └── command-palette.js   # New: Vanilla JS command palette (~200 lines)
│   │   └── utils/
│   │       ├── __init__.py
│   │       └── markdown_utils.py        # Existing: Markdown rendering + XSS sanitization
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_app.py
│       ├── test_corrections.py
│       ├── test_cost_insights.py
│       ├── test_embedding_service.py
│       ├── test_import_service.py
│       ├── test_investigation_routes.py
│       ├── test_investigation_service.py
│       ├── test_kb_routes.py
│       ├── test_kb_service.py
│       ├── test_learning.py
│       ├── test_markdown.py
│       ├── test_metrics.py
│       ├── test_routes.py
│       ├── test_services.py
│       ├── test_spending.py
│       ├── test_trust.py
│       ├── test_auth.py               # New: Permission decorator + middleware tests
│       ├── test_websocket.py          # New: SocketIO event handler tests
│       ├── test_notifications.py      # New: Outbox + channel delivery tests
│       ├── test_slo_routes.py         # New: SLO dashboard route tests
│       ├── test_search.py             # New: Command palette search tests
│       └── integration/
│           └── test_notification_delivery.py  # New: End-to-end notification flow
│
├── demo/                               # New: Purpose-built chaotic demo application
│   ├── Dockerfile                       # Multi-service demo app container
│   ├── README.md                        # Demo architecture + scenario descriptions
│   ├── pyproject.toml                   # Demo app dependencies
│   ├── demo_app/
│   │   ├── __init__.py
│   │   ├── services/                    # Chaotic microservices (3-4 services)
│   │   │   ├── gateway.py              # API gateway with cascading failure paths
│   │   │   ├── processor.py            # Data processor with memory leak injection
│   │   │   └── storage.py              # Storage service with latency injection
│   │   └── faults/
│   │       ├── __init__.py
│   │       ├── memory_leak.py          # Configurable memory leak fault
│   │       ├── bad_deploy.py           # Bad deployment simulation
│   │       ├── cascade.py              # Cascading failure across services
│   │       └── scale_dependent.py      # Issues that only appear at scale
│   ├── scenarios/                       # Scripted demo scenarios (YAML)
│   │   ├── investor_demo.yaml          # Full lifecycle: fault → detect → fix → prove
│   │   ├── trust_progression.yaml      # TL1 → TL3 trust escalation demo
│   │   └── cascade_failure.yaml        # Multi-service cascading incident
│   ├── k8s/                            # Demo-specific K8s manifests
│   │   ├── deployment.yaml
│   │   ├── service-levels.yaml         # ServiceLevel CRDs for demo services
│   │   └── notification-channels.yaml  # Demo notification channels
│   └── tests/
│       ├── test_scenarios.py           # Pytest harness for scripted demo runs
│       └── test_reliability.py         # NFR18: 10 consecutive runs without failure
│
├── helm/                               # Helm chart for deployment
│   └── beeper/
│       ├── Chart.yaml                   # version: 0.2.0, appVersion: 0.2.0
│       ├── values.yaml                  # Extended: SocketIO, notification, demo settings
│       ├── values-dev.yaml              # Development overrides
│       ├── templates/
│       │   ├── _helpers.tpl
│       │   ├── operator-deployment.yaml
│       │   ├── operator-rbac.yaml       # Extended: new CRD permissions
│       │   ├── operator-serviceaccount.yaml
│       │   ├── operator-role.yaml
│       │   ├── operator-rolebinding.yaml
│       │   ├── ui-deployment.yaml       # Extended: SocketIO port, Tailwind env
│       │   ├── ui-service.yaml
│       │   ├── qdrant-statefulset.yaml
│       │   ├── qdrant-service.yaml
│       │   ├── configmap.yaml
│       │   ├── secrets.yaml
│       │   ├── investigator-rbac.yaml
│       │   ├── sandbox-namespace.yaml   # New: NetworkPolicy-isolated sandbox
│       │   ├── sandbox-networkpolicy.yaml # New: Deny all except Qdrant + K8s API
│       │   ├── demo-deployment.yaml     # New: Demo app services (conditional)
│       │   └── crds/
│       │       ├── investigation-crd.yaml
│       │       ├── source-crd.yaml
│       │       ├── service-level-crd.yaml       # New
│       │       ├── notification-channel-crd.yaml # New
│       │       └── repository-crd.yaml           # New
│       └── README.md
│
├── scripts/                            # Development scripts
│   ├── setup-dev.sh                    # Local dev environment setup (extended)
│   ├── generate-clients.sh             # Generate clients from OpenAPI
│   ├── seed-kb.sh                      # Seed KB with sample data
│   ├── init-collections.py             # Create Qdrant collections (extended: new collections)
│   ├── seed_kb.py                      # Insert sample KB entries
│   ├── demo.sh                         # End-to-end demo orchestration
│   ├── local-testing.sh                # Full local test suite
│   └── build-tailwind.sh               # New: Tailwind CLI build + watch script
│
└── docs/                               # Documentation
    ├── index.md                         # Documentation suite index
    ├── project-overview.md              # Architecture overview
    ├── development-guide.md             # Local dev guide
    ├── deployment-guide.md              # Production deployment guide
    ├── api-contracts.md                 # API documentation
    ├── source-tree-analysis.md          # Annotated source tree
    └── integration-architecture.md      # Component communication patterns
```

### Architectural Boundaries

**API Boundaries:**

| Boundary | Protocol | Location | New/Existing |
|----------|----------|----------|-------------|
| External → UI | HTTP/HTTPS | `ui/routes/*` | Existing (expanded) |
| External → UI (bidirectional) | WebSocket (SocketIO) | `ui/websocket/*` | **New** |
| UI → Qdrant | HTTP (Qdrant API) | `ui/services/*_service.py` | Existing (expanded) |
| UI → Operator API | HTTP | `ui/services/investigation_service.py` etc. | Existing (expanded) |
| Operator → K8s API | K8s client | `operator/src/controllers/*` | Existing (expanded) |
| Investigator → Qdrant | HTTP | `investigator/kb/client.py` | Existing |
| Investigator → LLM | HTTP (LiteLLM) | `investigator/llm/client.py` | Existing |
| Investigator → Git Provider | HTTPS (GitHub/GitLab API) | `investigator/remediation/pr_generator.py` | **New** |
| Operator → Prometheus | HTTP (PromQL) | `operator/src/sources/prometheus.rs` | Existing |
| Operator → Loki | HTTP (LogQL) | `operator/src/sources/loki.rs` | Existing |
| UI → Slack | HTTPS (Slack API) | `ui/notifications/slack.py` | **New** |
| UI → PagerDuty | HTTPS (PD API) | `ui/notifications/pagerduty.py` | **New** |
| UI → Email | SMTP | `ui/notifications/email.py` | **New** |
| UI → Webhooks | HTTPS (outbound) | `ui/notifications/webhook.py` | **New** |

**Component Boundaries:**

```
┌──────────────────────────────────────────────────────────────────────────┐
│                             K8s Cluster                                  │
│                                                                          │
│  ┌──────────────────────┐                                                │
│  │  beeper-operator     │──────────┐                                     │
│  │     (Rust)           │          │ spawns Job                           │
│  │ • CRD Controllers    │          ▼                                     │
│  │ • SLO Engine         │    ┌──────────────────┐                        │
│  │ • Detection          │    │  investigator     │                        │
│  │ • Notification Rules │    │   Job (Python)    │                        │
│  └─────────┬────────────┘    │ • 6-step pipeline │                        │
│            │                 │ • Remediation ext  │──── Git Provider API   │
│    watches │                 │ • PII scrubber     │     (auto-PRs)         │
│    5 CRDs  │                 └────────┬───────────┘                        │
│            │                          │ writes findings                   │
│            ▼                          ▼                                   │
│  ┌──────────────────┐   ┌──────────────────────────┐                     │
│  │ CRDs (etcd)      │   │        Qdrant             │                     │
│  │ • Investigation   │   │ • investigations          │                     │
│  │ • Source          │   │ • knowledge (+versions)   │                     │
│  │ • ServiceLevel    │   │ • corrections             │                     │
│  │ • NotifChannel    │   │ • learning_patterns       │                     │
│  │ • Repository      │   │ • service_trust_levels    │                     │
│  └──────────────────┘   │ • slo_snapshots           │                     │
│                          │ • notification_outbox     │                     │
│                          └────────────┬─────────────┘                     │
│                                       │ queries                          │
│                                       ▼                                  │
│                          ┌──────────────────────────┐                     │
│                          │      beeper-ui            │                     │
│                          │       (Flask)             │──── Slack API       │
│                          │ • SSE (unidirectional)    │──── PagerDuty API   │
│                          │ • SocketIO (bidirectional)│──── Email (SMTP)    │
│                          │ • Notification outbox     │──── Webhooks        │
│                          │ • Permission middleware   │                     │
│                          └──────────────────────────┘                     │
│                                                                          │
│  ┌──────────────────┐   ┌──────────────────────────┐                     │
│  │ beeper-sandbox   │   │   beeper-demo-*           │                     │
│  │ (isolated NS)    │   │   (demo app pods)         │                     │
│  │ • NetworkPolicy  │   │ • gateway, processor,     │                     │
│  │ • Fix testing    │   │   storage services        │                     │
│  │ • No prod access │   │ • Fault injection         │                     │
│  └──────────────────┘   └──────────────────────────┘                     │
└──────────────────────────────────────────────────────────────────────────┘
```

**Data Boundaries:**

| Data Type | Storage | Access Pattern | New/Existing |
|-----------|---------|----------------|-------------|
| Investigation state | Qdrant `investigations` | Read-your-writes | Extended |
| KB entries + versions | Qdrant `knowledge`, `knowledge_versions` | Eventually consistent | Extended |
| Corrections + learning | Qdrant `corrections`, `learning_patterns` | Eventually consistent | Existing |
| Trust configuration | Qdrant `service_trust_levels` | Read-your-writes | Extended |
| SLO snapshots | Qdrant `slo_snapshots` | Write-heavy, time-series queries | **New** |
| Notification outbox | Qdrant `notification_outbox` | Outbox pattern (write → process → mark) | **New** |
| CRD state (5 CRDs) | K8s etcd | Operator reconciliation | Extended |
| Secrets (integrations) | K8s Secrets | Mounted to pods / read by operator | Existing |
| Config | ConfigMap + env vars | Injected at deploy | Existing |
| Sandbox state | Isolated K8s namespace | Ephemeral per test execution | **New** |

### FR to Structure Mapping

**SLO & Customer Impact — Wave 1 (FR1-7):**
- FR1 (define SLIs/SLOs): `operator/src/crds/service_level.rs`, `helm/templates/crds/service-level-crd.yaml`
- FR2 (burn rates): `operator/src/slo/calculator.rs`, `operator/src/slo/burn_rate.rs`
- FR3 (SLO-triggered investigations): `operator/src/slo/burn_rate.rs` → `operator/src/controllers/investigation.rs`
- FR4 (SLO-based scoring): `operator/src/slo/impact.rs`, `operator/src/detection/consumer.rs`
- FR5 (error budget policies): `operator/src/slo/budget.rs`
- FR6 (SLO dashboard): `ui/routes/slo.py`, `ui/services/slo_service.py`, `ui/templates/slo/`
- FR7 (investigation priority): `operator/src/slo/impact.rs` → `operator/src/detection/consumer.rs`

**Notification & Integration — Wave 1 (FR8-15):**
- FR8 (notification channels): `operator/src/crds/notification_channel.rs`, `helm/templates/crds/notification-channel-crd.yaml`
- FR9 (routing rules): `operator/src/notifications/router.rs`, `ui/routes/notifications.py`
- FR10 (Slack): `ui/notifications/slack.py`
- FR11 (PagerDuty): `ui/notifications/pagerduty.py`
- FR12 (email): `ui/notifications/email.py`
- FR13 (webhooks): `ui/notifications/webhook.py`
- FR14 (quiet hours + escalation): `operator/src/notifications/router.rs`
- FR15 (false page tracking): `operator/src/notifications/audit.rs`, `ui/templates/notifications/audit.html`

**Trust & Autonomy — Wave 2 (FR16-22):**
- FR16 (trust levels per service): `ui/routes/trust.py`, `ui/services/trust_service.py`, `ui/templates/trust/configure.html`
- FR17 (confidence gating): `investigator/steps/__init__.py` (gate check), `investigator/remediation/__init__.py`
- FR18 (adaptive thresholds): `operator/src/detection/ewma.rs` (feedback integration)
- FR19 (one-click feedback): `ui/routes/investigations.py`, `ui/templates/investigations/detail.html`
- FR20 (noise report): `ui/routes/trust.py`, `ui/templates/trust/overview.html`
- FR21 (impact-weighted urgency): `operator/src/slo/impact.rs` → `operator/src/notifications/router.rs`
- FR22 (confidence gate config): `ui/routes/trust.py` (admin), `ui/templates/trust/configure.html`

**Auto-Remediation — Wave 2 (FR23-31):**
- FR23 (register repos): `operator/src/crds/repository.rs`, `helm/templates/crds/repository-crd.yaml`
- FR24 (runbook execution): `investigator/remediation/fix_generator.py`
- FR25 (auto-PRs): `investigator/remediation/pr_generator.py`
- FR26 (advisory test plan): `investigator/remediation/test_planner.py`
- FR27 (sandbox testing): `investigator/remediation/sandbox_executor.py`
- FR28 (post-fix verification): `investigator/remediation/verifier.py`
- FR29 (trust-gated remediation): `investigator/remediation/__init__.py` (gate check before steps)
- FR30 (PR ↔ investigation link): `investigator/remediation/pr_generator.py` (evidence metadata in PR body)
- FR31 (KB proven fixes): `investigator/steps/investigation_documentation.py` (extended)

**Collaborative Investigation — Wave 3 (FR32-37):**
- FR32 (real-time interaction): `ui/websocket/investigation.py`, `ui/static/js/socketio.min.js`
- FR33 (evidence with references): `ui/routes/investigations.py`, `ui/templates/investigations/evidence.html`
- FR34 (annotate/redirect): `ui/websocket/investigation.py` (`annotate`, `redirect` events)
- FR35 (approve/reject fixes): `ui/websocket/investigation.py` (`approve_fix`, `reject_fix`)
- FR36 (shift handoff): `ui/routes/handoff.py`, `ui/templates/investigations/handoff.html`
- FR37 (surface past KB): `investigator/steps/kb_query.py` (extended: real-time KB push via SocketIO)

**Knowledge Base Enhancement — Wave 3 (FR38-42):**
- FR38 (auto KB entries): `investigator/steps/investigation_documentation.py`
- FR39 (bi-directional links): `investigator/kb/schemas.py`, `investigator/kb/client.py`
- FR40 (per-service KB views): `ui/routes/knowledge.py` (service filter), `ui/services/kb_service.py`
- FR41 (validation weighting): `investigator/kb/schemas.py` (validation_status field)
- FR42 (KB edit/correct): `ui/routes/knowledge.py`, `ui/services/correction_service.py` (existing)

**Signal & Observability — Wave 3 (FR43-46):**
- FR43 (unified timeline): `ui/routes/investigations.py` (timeline view), `ui/templates/investigations/detail.html`
- FR44 (deploy correlation): `investigator/correlation/signals.py` (extended)
- FR45 (service topology): `ui/routes/analytics.py`, `operator/src/api.rs` (topology endpoint)
- FR46 (change event ingestion): `operator/src/ingestion/` (extended for change events)

**Developer Experience — Wave 4 (FR47-50):**
- FR47 (command palette): `ui/static/js/command-palette.js`, `ui/templates/components/command-palette.html`, `ui/routes/search.py`
- FR48 (workflow states): `ui/routes/investigations.py` (state machine visualization)
- FR49 (remediation progress): `ui/routes/remediation.py`, `ui/templates/remediation/status.html`
- FR50 (service health feeds): `ui/routes/analytics.py`, `ui/templates/analytics/dashboard.html`

**Analytics & Reporting — Wave 4 (FR51-53):**
- FR51 (reliability score): `ui/services/metrics_service.py` (extended), `ui/routes/analytics.py`
- FR52 (trend dashboards): `ui/routes/analytics.py`, `ui/templates/analytics/dashboard.html`
- FR53 (investor reports): `ui/routes/analytics.py`, `ui/templates/analytics/investor.html`

**Demo Application — Cross-cutting (FR54-57):**
- FR54 (deploy demo app): `demo/`, `helm/templates/demo-deployment.yaml`
- FR55 (fault injection): `demo/demo_app/faults/`
- FR56 (full lifecycle demo): `demo/scenarios/investor_demo.yaml`
- FR57 (scripted scenarios): `demo/scenarios/`, `demo/tests/test_scenarios.py`

**Platform & Security — Foundation (FR58-63):**
- FR58 (2-tier permissions): `ui/auth/decorators.py`, `ui/auth/middleware.py`
- FR59 (K8s Secrets): `helm/templates/secrets.yaml`, `operator/src/llm.rs`
- FR60 (PII scrubbing): `investigator/llm/scrubber.py`
- FR61 (LLM degradation): `investigator/llm/client.py` (circuit breaker), `ui/notifications/outbox.py`
- FR62 (action rollback): `investigator/remediation/verifier.py`, `operator/src/controllers/investigation.rs`
- FR63 (non-SPOF): Helm deployment design — no dependency on Beeper for existing alerting

### Integration Points

**Internal Communication:**

| From | To | Mechanism | Data |
|------|----|-----------|------|
| Operator | Investigator | K8s Job creation (env vars) | Investigation context, trust level, SLO data |
| Investigator | Qdrant | HTTP (qdrant-client) | Findings, KB entries, notification outbox |
| Investigator | Git Provider | HTTPS (API) | Auto-PRs with evidence |
| Investigator | Sandbox | K8s API (deploy + monitor) | Fix deployment, test execution |
| UI | Qdrant | HTTP (qdrant-client) | Queries, notification outbox writes |
| UI | Operator API | HTTP | SLO data, trust config, investigation control |
| UI | Client (browser) | SSE | Live investigation updates (unidirectional) |
| UI | Client (browser) | SocketIO | Collaboration events (bidirectional) |
| Operator | Qdrant | HTTP (qdrant-client) | SLO snapshots (from Rust via reqwest) |

**External Integrations:**

| Integration | Component | Protocol | Purpose |
|-------------|-----------|----------|---------|
| Prometheus | Operator (ingestion + query) | HTTP (remote write + PromQL) | Metric ingestion + SLO calculation |
| Loki | Operator (ingestion + query) | HTTP (push + LogQL) | Log ingestion + anomaly detection |
| Claude / LLM | Investigator (via LiteLLM) | HTTP | Investigation reasoning, fix generation |
| Slack | UI (notifications) | HTTPS (Slack API) | Rich investigation notifications |
| PagerDuty | UI (notifications) | HTTPS (PD API) | Incident lifecycle management |
| GitHub/GitLab | Investigator (remediation) | HTTPS (Git API) | Auto-PR creation |
| SMTP | UI (notifications) | SMTP | Email digests + alerts |

**Data Flow (v0.2.0 Extended):**
```
Prometheus/Loki → Operator (detect + SLO score) → K8s Job (investigate + remediate)
                         ↓                                    ↓
                   SLO snapshots                        Claude API (reason + fix)
                   (Qdrant)                                   ↓
                                                        Qdrant (store findings)
                                                              ↓
                                        ┌─────────────────────┼──────────────────┐
                                        ↓                     ↓                  ↓
                                 Notification Outbox    UI (display)       Git Provider
                                 (Qdrant)                    ↓             (auto-PR)
                                        ↓              SocketIO + SSE
                                 Slack / PD / Email    (live collaboration)
```

### Development Workflow

**Local Development:**
```bash
# Start local stack
docker-compose up -d  # Qdrant + demo app services

# Operator (Rust)
cd operator && cargo run

# Investigator (Python) - run manually for testing
cd investigator && poetry run python -m beeper_investigator.main

# UI (Flask) with SocketIO support
cd ui && poetry run flask run --reload

# Tailwind CSS (watch mode)
./scripts/build-tailwind.sh --watch

# Demo app (optional — for full lifecycle testing)
cd demo && poetry run python -m demo_app
```

**Build Process:**
```bash
# All containers (includes Tailwind build in UI Dockerfile)
docker build -t beeper-operator:dev ./operator
docker build -t beeper-investigator:dev ./investigator
docker build -t beeper-ui:dev ./ui           # Tailwind CLI runs in build stage
docker build -t beeper-demo:dev ./demo

# Helm install (local K8s)
helm install beeper ./helm/beeper -f helm/beeper/values-dev.yaml

# Run demo scenario
cd demo && poetry run pytest tests/test_scenarios.py -k investor_demo
```

**Test Execution:**
```bash
# Full suite (1,032 existing + new tests)
./scripts/local-testing.sh

# By component
cd operator && cargo test                    # Rust tests (162 existing + new SLO/notification)
cd investigator && poetry run pytest         # Python tests (375 existing + remediation/scrubber)
cd ui && poetry run pytest                   # Python tests (495 existing + auth/ws/notif/slo)
cd demo && poetry run pytest                 # Demo scenario tests
```

## Architecture Validation

### Coherence Validation

**Decision Compatibility:**

| Decision Pair | Compatibility | Notes |
|---------------|---------------|-------|
| Rust Operator + Python Investigator | ✅ | K8s Job isolation, no tight coupling (unchanged) |
| Qdrant (all 8 collections) + no SQL DB | ✅ | Payload-only collections cover SLO/notification/trust without adding a new datastore |
| Flask-SocketIO + HTMX/SSE | ✅ | Two-channel architecture: SocketIO for bidirectional collaboration, SSE for unidirectional updates. No conflict — cleanly separated by concern |
| Flask + @require_role decorator | ✅ | ~200 line permission model, no framework change needed |
| Tailwind CLI + existing CSS | ✅ | Standalone binary, no Node.js. `@apply` escape hatch for incremental migration |
| SLO engine in operator + Qdrant snapshots | ✅ | Rust operator already has Prometheus metric access; snapshots are payload-only Qdrant writes |
| Durable notification outbox (Qdrant) + channel implementations (UI) | ✅ | Outbox uses existing Qdrant infrastructure; background worker runs in Flask process |
| Auto-remediation (investigator) + Repository CRD (operator) | ✅ | CRD provides config; investigator reads via K8s API (existing pattern from Investigation CRD) |
| Trust gating (investigator) + trust config (Qdrant) | ✅ | Investigator already reads Qdrant; trust config is a simple payload lookup |
| Demo app (demo/) + Helm deployment | ✅ | Conditional Helm template; demo has own Dockerfile in monorepo pattern |
| Sandbox namespace + NetworkPolicy | ✅ | Standard K8s isolation pattern; no custom networking required |

**No Incompatibilities Found.** All v0.2.0 additions follow existing architectural patterns (CRD-based config, Qdrant storage, Python service layer, Helm deployment).

**Pattern Consistency:**

| Pattern Area | Consistent? | Verification |
|-------------|------------|-------------|
| Naming conventions (snake_case everywhere) | ✅ | All new endpoints, Qdrant fields, CRD fields follow established convention |
| API patterns (REST + versioned endpoints) | ✅ | All new endpoints under `/api/v1/` with RFC 7807 errors |
| CRD patterns (CustomResource derive in Rust) | ✅ | 3 new CRDs follow Investigation/Source pattern exactly |
| Test organization (tests/ directory per component) | ✅ | New test files mirror source structure |
| Service layer pattern (services/ in UI) | ✅ | New slo_service, trust_service, search_service follow existing pattern |
| Blueprint pattern (routes/ in UI) | ✅ | 8 new route files follow existing Blueprint registration pattern |

**Structure Alignment:**

| Check | Status |
|-------|--------|
| Project structure supports all decisions | ✅ Every decision maps to specific files/directories |
| Component boundaries clear | ✅ Operator (Rust), Investigator (Python), UI (Flask), Demo (Python) — each independently buildable |
| Integration points structured | ✅ All boundary crossings documented in API/Data Boundaries tables |
| New subsystems fit existing monorepo pattern | ✅ `slo/`, `notifications/`, `remediation/` follow existing `detection/`, `ingestion/`, `steps/` patterns |

### Requirements Coverage

**Functional Requirements: 63/63 covered**

| FR Group | Count | Coverage | Primary Location |
|----------|-------|----------|-----------------|
| SLO & Customer Impact (FR1-7) | 7 | ✅ 100% | `operator/src/slo/`, `ui/routes/slo.py` |
| Notification & Integration (FR8-15) | 8 | ✅ 100% | `operator/src/notifications/`, `ui/notifications/` |
| Trust & Autonomy (FR16-22) | 7 | ✅ 100% | `ui/routes/trust.py`, `investigator/steps/` |
| Auto-Remediation (FR23-31) | 9 | ✅ 100% | `investigator/remediation/`, `operator/src/crds/repository.rs` |
| Collaborative Investigation (FR32-37) | 6 | ✅ 100% | `ui/websocket/`, `ui/routes/handoff.py` |
| Knowledge Base Enhancement (FR38-42) | 5 | ✅ 100% | `investigator/kb/`, `ui/routes/knowledge.py` |
| Signal & Observability (FR43-46) | 4 | ✅ 100% | `investigator/correlation/`, `operator/src/ingestion/` |
| Developer Experience (FR47-50) | 4 | ✅ 100% | `ui/static/js/command-palette.js`, `ui/routes/remediation.py` |
| Analytics & Reporting (FR51-53) | 3 | ✅ 100% | `ui/routes/analytics.py` |
| Demo Application (FR54-57) | 4 | ✅ 100% | `demo/` |
| Platform & Security (FR58-63) | 6 | ✅ 100% | `ui/auth/`, `investigator/llm/scrubber.py`, `helm/` |

**Non-Functional Requirements: 22/22 covered**

| NFR | Target | Architectural Support |
|-----|--------|----------------------|
| NFR1: Anomaly-to-investigation < 30s | ✅ | Async Rust operator + tokio; SLO scoring adds < 1ms overhead |
| NFR2: UI response < 2s | ✅ | Flask + HTMX partials; Qdrant sub-second queries |
| NFR3: LLM screening < 10s | ✅ | Haiku tier for fast triage (existing, unchanged) |
| NFR4: LLM deep RCA < 30s/step | ✅ | Opus tier for deep reasoning (existing, unchanged) |
| NFR5: WebSocket delivery < 500ms | ✅ | Flask-SocketIO rooms with in-process event loop |
| NFR6: SLO burn rate < 5s refresh | ✅ | Rust operator calculates inline with metric ingestion |
| NFR7: Demo lifecycle < 5 min | ✅ | Scripted scenarios with pytest harness; fault → fix pipeline |
| NFR8: Least-privilege RBAC | ✅ | K8s roles per component; 2-tier admin/user in UI |
| NFR9: Scoped repo tokens | ✅ | Repository CRD stores per-repo credentials_secret |
| NFR10: K8s Secrets encryption | ✅ | All credentials in K8s Secrets (existing pattern) |
| NFR11: PII scrubbing | ✅ | `scrubber.py` pre-LLM filter with regex + tagged placeholders |
| NFR12: Admin-only trust config | ✅ | `@require_role("admin")` on all trust/confidence endpoints |
| NFR13: Sandbox isolation | ✅ | NetworkPolicy-isolated namespace; deny-all except Qdrant + K8s API |
| NFR14: Non-SPOF | ✅ | Helm design — Beeper failure doesn't affect existing alerting |
| NFR15: LLM degradation handling | ✅ | Queue + escalate within 60s; notification outbox ensures human awareness |
| NFR16: Action rollback < 60s | ✅ | `verifier.py` monitors post-fix metrics; operator can revert investigation state |
| NFR17: Zero data loss on restart | ✅ | Qdrant persistent volumes; durable outbox pattern |
| NFR18: 10 consecutive demo runs | ✅ | `demo/tests/test_reliability.py` — pytest harness with scripted scenarios |
| NFR19: 50+ concurrent investigations | ✅ | Async Rust operator + K8s Job isolation (existing, validated at scale) |
| NFR20: 10K+ KB entries < 2s search | ✅ | Qdrant HNSW index (existing, validated) |
| NFR21: 100+ ServiceLevel CRDs | ✅ | Operator controller pattern handles CRD volume natively |
| NFR22: 1000+ notifications/hour | ✅ | Durable outbox with background worker; Qdrant handles write volume |

### Implementation Readiness

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Technology stack fully specified | ✅ | All libraries, versions, and tools documented |
| All CRD schemas defined | ✅ | ServiceLevel, NotificationChannel, Repository — full YAML examples |
| API endpoints documented | ✅ | All new endpoints with methods, paths, and semantics |
| WebSocket events specified | ✅ | Client→Server and Server→Client events with payloads |
| Qdrant collections defined | ✅ | 8 collections with type (vector/payload-only) and purpose |
| Project structure complete | ✅ | Full annotated directory tree with FR mapping |
| Permission model defined | ✅ | Decorator + middleware pattern with admin/user operations listed |
| Integration boundaries mapped | ✅ | All API, component, and data boundaries in tables |
| Pattern examples provided | ✅ | Permission check, notification delivery, trust gate, state machines |
| Build/deploy process outlined | ✅ | Docker, Helm, Tailwind, local dev, test execution |

### Gap Analysis

**Critical Gaps: 0**

**Moderate Gaps: 0**

**Informational Notes (resolve during epic breakdown, not architecture blockers):**

1. **Qdrant index configuration for new collections** — `slo_snapshots` and `notification_outbox` are payload-only (no vector index needed), but exact field indexes for time-range queries will be defined during implementation
2. **Sandbox namespace lifecycle** — Creation/cleanup of sandbox namespace and deployed test fixtures will be detailed in auto-remediation epic stories
3. **Demo app service mesh** — Exact microservice count (3-4) and inter-service communication patterns will be refined during demo epic design
4. **Tailwind migration scope per wave** — Which templates get Tailwind classes in each wave will be decided by UX implementation stories
5. **Notification worker concurrency** — Single-threaded background worker in Flask process is sufficient for v0.2.0 targets (1,000/hour = ~17/min); scaling strategy deferred to post-MVP

### Architecture Completeness Checklist

**Requirements Analysis**
- [x] Project context thoroughly analyzed (63 FRs, 22 NFRs, 6 user journeys)
- [x] Scale and complexity assessed (brownfield, v0.1.0 with 1,032 tests)
- [x] Technical constraints identified (no SQL DB, no Node.js, K8s-only deployment)
- [x] Cross-cutting concerns mapped (permissions, PII scrubbing, trust gating)

**Architectural Decisions**
- [x] Critical decisions documented with versions and rationale
- [x] Technology stack fully specified (Rust + Python + Flask + Qdrant + 3 new CRDs)
- [x] Integration patterns defined (REST, SSE, SocketIO, K8s Jobs, durable outbox)
- [x] Performance considerations addressed (all 7 performance NFRs)
- [x] Security considerations addressed (all 6 security NFRs)

**Implementation Patterns**
- [x] Naming conventions established (snake_case everywhere, per-language rules)
- [x] Structure patterns defined (monorepo, component directories, test organization)
- [x] Communication patterns specified (SSE, SocketIO, REST, K8s events)
- [x] Process patterns documented (logging, error handling, state machines)
- [x] Enforcement guidelines with anti-patterns documented

**Project Structure**
- [x] Complete directory structure defined with file-level detail
- [x] Component boundaries established (5 independently buildable sub-projects)
- [x] Integration points mapped (14 API boundaries, 9 internal communication paths)
- [x] All 63 FRs mapped to specific files/directories

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level: High** — Brownfield project with validated v0.1.0 foundation. All v0.2.0 additions follow established patterns. No new datastores, no framework migrations, no breaking changes.

**Key Strengths:**
- Every v0.2.0 feature builds on validated v0.1.0 patterns — no architectural rewrites
- Party Mode validated Flask-SocketIO, Tailwind CLI, durable outbox, and Django rejection with multi-perspective analysis
- All 63 FRs mapped to specific files with explicit directory locations
- Permission model, trust gating, and notification delivery patterns have code-level examples
- 4-wave delivery structure aligns with architectural dependency chain

**Areas for Future Enhancement (post v0.2.0):**
- Multi-cluster support (requires NATS or similar message bus)
- Fine-grained RBAC beyond admin/user (evaluate if community needs it)
- Graph DB for KB relationships (evaluate Qdrant payload links vs. dedicated graph)
- SaaS multi-tenancy architecture
- Dedicated notification microservice (if outbox throughput exceeds single-process capacity)

## Implementation Handoff

### Wave-Based Delivery Structure

v0.2.0 uses a 4-wave delivery model aligned with architectural dependencies. Each wave builds on the previous.

**Wave 1: SLO + Notifications (Foundation for everything)**
- Permission model (`ui/auth/`) — foundation for all new endpoints
- 3 new CRD schemas (ServiceLevel, NotificationChannel, Repository)
- SLO engine in operator (`operator/src/slo/`)
- 2 new Qdrant collections (`slo_snapshots`, `notification_outbox`)
- Notification outbox + channel implementations (`ui/notifications/`)
- SLO dashboard (`ui/routes/slo.py`)
- Notification config + audit views (`ui/routes/notifications.py`)
- **Covers:** FR1-15, FR58-60, NFR1, NFR5-6, NFR8-12, NFR22

**Wave 2: Trust + Auto-Remediation (Intelligence layer)**
- Trust system storage + confidence gating
- Trust management UI (`ui/routes/trust.py`)
- Remediation pipeline (`investigator/remediation/`)
- Repository CRD controller
- Sandbox namespace + NetworkPolicy
- PII scrubber (`investigator/llm/scrubber.py`)
- **Covers:** FR16-31, NFR9, NFR11, NFR13, NFR16

**Wave 3: Collaboration + KB Enhancement (User-facing evolution)**
- Flask-SocketIO integration (`ui/websocket/`)
- Real-time investigation interaction
- Shift handoff summaries
- KB bi-directional links + service views
- Signal correlation extensions (deploy correlation, change events)
- **Covers:** FR32-46, NFR5

**Wave 4: DX + Analytics + Demo (Polish + proof)**
- Command palette (`ui/static/js/command-palette.js`)
- Analytics + investor reports (`ui/routes/analytics.py`)
- Demo application (`demo/`)
- Tailwind CSS migration (incremental, parallel)
- **Covers:** FR47-57, NFR7, NFR18

### Critical Path

```
Permission model → New CRDs → SLO engine → Notification outbox
                                    ↓                ↓
                              Trust system → Auto-remediation → Sandbox
                                    ↓
                              WebSocket → Collaboration features
                                                     ↓
                              Command palette → Analytics → Demo app
```

**Dependency chain highlights:**
- Permission model must exist before ANY new API endpoint
- SLO engine feeds notification urgency AND investigation priority
- Trust system gates auto-remediation behavior
- WebSocket infrastructure needed before collaboration features
- Repository CRD must exist before auto-PR generation
- Demo app is last — it validates the entire stack

### Architecture Spikes (resolve early in each wave)

| Spike | Wave | Risk | Resolution Approach |
|-------|------|------|-------------------|
| Flask-SocketIO + gunicorn compatibility | 3 | Medium | Spike before WebSocket stories — test with eventlet worker |
| Qdrant payload-only collection performance at scale | 1 | Low | Benchmark `notification_outbox` write throughput early |
| Tailwind CLI + Jinja2 template scanning | 4 | Low | Configure JIT mode, verify class detection in `.html` files |
| Git provider API auth (GitHub/GitLab) | 2 | Medium | Spike with test repo before auto-PR stories |
| Sandbox NetworkPolicy + investigator K8s API access | 2 | Medium | Validate investigator can deploy to sandbox namespace |

### Architecture as Single Source of Truth

This document serves as the definitive reference for:
- Technology choices (no re-debates — Flask stays, no Django)
- Naming conventions (enforced via linting — snake_case everywhere)
- API patterns (validated via OpenAPI — all endpoints under `/api/v1/`)
- Project structure (followed by all agents — FR-to-file mapping is authoritative)
- CRD schemas (3 new CRDs with full YAML examples)
- Communication patterns (SSE for unidirectional, SocketIO for bidirectional)
- Permission boundaries (admin vs. user operations explicitly listed)

Any deviation should be documented as an ADR (Architecture Decision Record) with explicit rationale.

