# Test Design for Architecture: Beeper v0.2.0

**Purpose:** Architectural concerns, testability gaps, and NFR requirements for review by Architecture/Dev teams. Serves as a contract between QA and Engineering on what must be addressed before test development begins.

**Date:** 2026-03-13
**Author:** TEA Agent (requested by eric)
**Status:** Architecture Review Pending
**Project:** Beeper
**PRD Reference:** `_bmad-output/planning-artifacts/prd.md`
**ADR Reference:** `_bmad-output/planning-artifacts/architecture.md`

---

## Executive Summary

**Scope:** Full platform testability review for Beeper v0.2.0 — an agentic AI platform for SRE deployed as a K8s operator. v0.2.0 extends a proven v0.1.0 codebase (1,032 passing tests) with 16 net-new FRs across SLO platform, notification engine, trust system, auto-remediation, real-time collaboration, KB enhancement, developer experience, and investor demo application.

**Business Context** (from PRD):
- **Purpose:** Proof-of-existence release — v0.2.0 IS the evidence that "Beeper is inevitable"
- **Problem:** AI-driven development degrades human ability to maintain system context; Beeper closes the full reliability loop
- **Target:** Demo-ready in 3 months, seed round conversations in 6 months

**Architecture** (from ADR):
- **Stack:** Rust (K8s operator) + Python 3.11+ (investigators, Flask UI) + Qdrant (vector DB)
- **Real-time:** Flask-SocketIO (bidirectional) + SSE (unidirectional) two-channel pattern
- **New subsystems:** SLO engine (Rust), trust system (TL1-5), auto-remediation pipeline, durable notification outbox, 3 new CRDs
- **Deployment:** Helm chart, monorepo, GitHub Actions CI

**Expected Scale** (from ADR):
- 50+ concurrent investigations without degradation
- 10,000+ KB entries with <2s semantic search
- 100+ ServiceLevel CRDs per cluster
- 1,000+ notifications/hour processed without drops

**Risk Summary:**
- **Total risks**: 11
- **High-priority (>=6)**: 6 risks requiring immediate mitigation
- **Medium-priority (3-5)**: 3 risks requiring planned mitigation
- **Low-priority (1-2)**: 2 risks to monitor

---

## Quick Guide

### BLOCKERS - Team Must Decide (Can't Proceed Without)

**Sprint 0 Critical Path** — These MUST be completed before QA can write integration tests:

1. **R-001: Trust System Safety Gating** — Trust level enforcement must be provably correct. A misconfigured gate allowing TL5 behavior on a TL1 service is equivalent to a production outage. (recommended owner: Backend)
2. **R-002: Sandbox Network Isolation** — NetworkPolicy must be validated as provably isolating sandbox from production. No test infrastructure for verifying isolation exists yet. (recommended owner: DevOps/Platform)
3. **R-003: PII Scrubbing Completeness** — Regex-based scrubbing must be validated against realistic log/metric content. A missed PII pattern in LLM context is a compliance incident. (recommended owner: Backend/Security)

**What we need from team:** Complete these 3 items in Sprint 0 or test development is blocked.

---

### HIGH PRIORITY - Team Should Validate (We Provide Recommendation, You Approve)

1. **R-004: Auto-Remediation False Positive** — Recommend mandatory sandbox verification for all auto-applied fixes, regardless of trust level. A false positive auto-fix IS a production outage caused by tooling. (Backend/Architecture)
2. **R-005: WebSocket + SSE Two-Channel Reliability** — Recommend integration test harness covering reconnect, room lifecycle, and SSE/SocketIO coexistence. No prior art in codebase for WebSocket. (Backend)

**What we need from team:** Review recommendations and approve (or suggest changes).

---

### INFO ONLY - Solutions Provided (Review, No Decisions Needed)

1. **Test strategy**: Unit-heavy for Rust operator + Python business logic, integration for API contracts and Qdrant operations, E2E for critical user journeys (investigation lifecycle, trust graduation, demo scenario)
2. **Existing foundation**: 1,032 tests across 3 components (pytest + cargo test), GitHub Actions CI
3. **Coverage**: Risk-based P0-P3 prioritization with test scenarios in companion QA doc
4. **Tooling**: pytest (Python), cargo test (Rust), respx (HTTP mocking), pytest-asyncio

**What we need from team:** Just review and acknowledge.

---

## For Architects and Devs - Open Topics

### Risk Assessment

**Total risks identified**: 11 (6 high-priority score >=6, 3 medium, 2 low)

#### High-Priority Risks (Score >=6) - IMMEDIATE ATTENTION

| Risk ID | Category | Description | Probability | Impact | Score | Mitigation | Owner | Timeline |
|---------|----------|-------------|-------------|--------|-------|------------|-------|----------|
| **R-001** | **SEC** | Trust level misconfiguration allows unauthorized autonomous actions (TL5 behavior on TL1 service) | 2 | 3 | **6** | Exhaustive boundary tests for every TL transition; default-deny enforcement | Backend | Sprint 0 |
| **R-002** | **SEC** | Sandbox namespace leaks traffic or data to production; fix testing corrupts production state | 2 | 3 | **6** | NetworkPolicy audit + automated isolation verification test | DevOps | Sprint 0 |
| **R-003** | **SEC** | PII/credentials in logs or metrics sent to LLM provider; compliance violation | 2 | 3 | **6** | Comprehensive regex validation + adversarial test corpus | Backend | Sprint 0 |
| **R-004** | **BUS** | Auto-remediation applies incorrect fix to production; causes outage via tooling | 2 | 3 | **6** | Mandatory sandbox verification gate; rollback within 60s; confidence threshold enforcement | Backend/Arch | Sprint 1 |
| **R-005** | **TECH** | WebSocket layer (Flask-SocketIO) fails under concurrent investigation rooms; data loss during reconnect | 2 | 3 | **6** | Integration test harness for SocketIO rooms, reconnect, broadcast; load test concurrent rooms | Backend | Sprint 1 |
| **R-008** | **PERF** | SLO burn rate calculation lag >5s under 100+ CRDs; Rust operator event loop blocked by Prometheus queries, starving anomaly detection and CRD reconciliation | 2 | 3 | **6** | Benchmark burn rate loop under 100+ CRDs; async Prometheus query batching; isolate SLO calculation from main reconciliation loop | Rust/Backend | Sprint 1 |

#### Medium-Priority Risks (Score 3-5)

| Risk ID | Category | Description | Probability | Impact | Score | Mitigation | Owner |
|---------|----------|-------------|-------------|--------|-------|------------|-------|
| R-006 | DATA | KB entry poisoning — invalid or malicious KB entries degrade future investigation quality | 2 | 2 | 4 | Validation status weighting (human-confirmed > AI-generated > corrected) | Backend |
| R-007 | OPS | Notification delivery failure — Slack/PagerDuty/email drops silently; false pages not tracked | 2 | 2 | 4 | Durable outbox with retry + delivery audit trail + false page metric | Backend |
| R-009 | OPS | LLM provider outage degrades ungracefully — investigations hang instead of queuing | 1 | 3 | 3 | Queue-and-retry pattern; 60s escalation timer; fallback to pattern matching | Backend |

#### Low-Priority Risks (Score 1-2)

| Risk ID | Category | Description | Probability | Impact | Score | Action |
|---------|----------|-------------|-------------|--------|-------|--------|
| R-010 | TECH | Command palette semantic search latency >300ms debounce threshold under 10K+ KB entries | 1 | 1 | 1 | Monitor; optimize Qdrant query if observed |
| R-011 | OPS | Demo app fault injection produces non-deterministic failures across 10 consecutive runs | 1 | 2 | 2 | Seed-based randomization; scripted deterministic scenarios |

#### Risk Category Legend

- **TECH**: Technical/Architecture (flaws, integration, scalability)
- **SEC**: Security (access controls, auth, data exposure)
- **PERF**: Performance (SLA violations, degradation, resource limits)
- **DATA**: Data Integrity (loss, corruption, inconsistency)
- **BUS**: Business Impact (UX harm, logic errors, revenue)
- **OPS**: Operations (deployment, config, monitoring)

---

### Testability Concerns and Architectural Gaps

**ACTIONABLE CONCERNS - Architecture Team Must Address**

#### 1. Blockers to Fast Feedback (WHAT WE NEED FROM ARCHITECTURE)

| Concern | Impact | What Architecture Must Provide | Owner | Timeline |
|---------|--------|--------------------------------|-------|----------|
| **No test data seeding API for Qdrant collections** | Cannot set up trust levels, SLO states, KB entries programmatically for tests; manual setup required | Seeding endpoints or test utilities for all 8 Qdrant collections (dev/test only) | Backend | Sprint 0 |
| **Sandbox namespace creation is manual** | Cannot run auto-remediation integration tests without provisioned sandbox | Automated sandbox provisioning for test environments (or test-mode bypass with mocked sandbox) | DevOps | Sprint 0 |
| **No mock for external SDK integrations** | Cannot test Slack (`slack-sdk` WebClient), PagerDuty (`pdpyras`), or Git provider (`PyGithub`/`python-gitlab`) SDKs without live credentials. Note: raw HTTP mocking via `respx` already exists in UI tests, but notification channels and Git providers use SDK clients, not raw HTTP. | Interface-based abstraction for all external SDK clients with injectable mock implementations; notification channel and Repository CRD handlers must accept pluggable backends | Backend | Sprint 0 |
| **CRD testing requires K8s cluster** | Rust operator CRD tests need a K8s environment; local development testing limited | k3s or kind-based test environment in CI; or mock K8s API client for unit tests | DevOps/Rust | Sprint 0 |

#### 2. Architectural Improvements Needed (WHAT SHOULD BE CHANGED)

1. **External SDK abstraction layer**
   - **Current problem**: Notification channels use SDK clients (`slack-sdk` WebClient, `pdpyras`, `smtplib`) and Git providers use SDK clients (`PyGithub`, `python-gitlab`) — not raw HTTP. The existing `respx` HTTP mocking in `ui/tests/` doesn't intercept SDK-level calls. Testing requires live API credentials or no testing at all.
   - **Required change**: Interface-based abstraction for all external SDK clients with injectable mock implementations. The `NotificationChannel` and `Repository` CRD handlers should accept pluggable backends (e.g., `SlackChannel(client: SlackClientProtocol)`).
   - **Impact if not fixed**: Integration tests for Waves 1-2 notification and auto-PR features are blocked until live credentials are configured in CI.
   - **Owner**: Backend
   - **Timeline**: Sprint 0

2. **Qdrant test isolation**
   - **Current problem**: Tests share Qdrant instance. Parallel test runs may corrupt each other's state across 8+ collections.
   - **Required change**: Test-scoped collection prefixes or per-test-run collection isolation (e.g., `test_{run_id}_investigations`). Alternative: in-memory Qdrant for unit tests.
   - **Impact if not fixed**: Flaky tests from state pollution; cannot parallelize test execution.
   - **Owner**: Backend
   - **Timeline**: Sprint 0

3. **Cross-language trust enforcement validation**
   - **Current problem**: Trust enforcement crosses the Rust/Python boundary. Trust levels are configured via Python UI, stored in Qdrant, and read by both the Rust operator (gating investigation spawning) and Python investigator (gating remediation actions). A trust level test that only validates the Python side misses half the enforcement surface.
   - **Required change**: End-to-end integration test that sets a trust level via the Python API and verifies the Rust operator AND Python investigator both enforce the correct behavior for the same service. Requires a test harness that can observe both components' behavior for a single trust level configuration change.
   - **Impact if not fixed**: Trust enforcement may silently diverge between operator and investigator — Rust spawns an investigation with TL3 expectations but Python investigator applies TL1 behavior (or vice versa).
   - **Owner**: Backend/Rust
   - **Timeline**: Sprint 1

4. **WebSocket test client for Flask-SocketIO**
   - **Current problem**: Flask-SocketIO has a pytest test client, but the two-channel pattern (SocketIO + SSE) needs coordinated testing. No test utilities exist for validating room-based broadcasts alongside SSE partial swaps.
   - **Required change**: Test helper that can join SocketIO rooms AND listen to SSE streams simultaneously for a single investigation lifecycle test.
   - **Impact if not fixed**: Cannot validate the core collaboration experience (real-time evidence + HTMX updates) in a single test.
   - **Owner**: Backend
   - **Timeline**: Sprint 1

---

### Testability Assessment Summary

**CURRENT STATE - FYI**

#### What Works Well

- API-first design (OpenAPI 3.1) — all business logic accessible via REST API, supporting headless test automation
- RFC 7807 error format — consistent, parseable error responses across all endpoints
- Existing test infrastructure — 1,032 tests with CI (cargo test + pytest), proving test-first culture
- Structured JSON logging — observable and parseable for test assertions
- Modular monorepo — independent test suites per component (operator, investigator, UI) with clear boundaries
- Investigation state machine — deterministic state transitions (pending -> started -> investigating -> completed/failed) support assertion-friendly testing
- Pydantic models in Python — automatic validation, serialization guarantees

#### Accepted Trade-offs (No Action Required)

- **2-tier RBAC (admin/user) only** — simplified permission testing. Fine-grained RBAC deferred to v0.3.0.
- **Single-cluster deployment** — no multi-cluster test matrix needed for v0.2.0.
- **Qdrant-only storage** — no SQL database migration testing. Vector DB testing patterns are simpler.
- **Desktop-only UI** — no responsive/mobile test matrix needed.

---

### Risk Mitigation Plans (High-Priority Risks >=6)

#### R-001: Trust Level Misconfiguration (Score: 6) - SECURITY CRITICAL

**Mitigation Strategy:**
1. Implement exhaustive boundary tests for every trust level transition (TL1->TL2, ..., TL4->TL5) verifying gating behavior changes correctly
2. Default-deny enforcement: any trust level lookup failure must fall back to TL1 (advisory only), never escalate
3. Confidence gate validation: verify actions below threshold fall to next lower TL behavior
4. Add audit logging for all trust level changes (who, when, from, to)

**Owner:** Backend
**Timeline:** Sprint 0
**Status:** Planned
**Verification:** Unit tests for every TL boundary; integration test for default-deny fallback; code review of trust enforcement paths

#### R-002: Sandbox Network Isolation Leak (Score: 6) - SECURITY CRITICAL

**Mitigation Strategy:**
1. NetworkPolicy must explicitly deny all egress from sandbox namespace except to sandbox-internal services
2. Automated verification test: deploy a pod in sandbox that attempts to reach production services; verify connection refused
3. DNS isolation: sandbox pods must not resolve production service DNS names

**Owner:** DevOps/Platform
**Timeline:** Sprint 0
**Status:** Planned
**Verification:** Network isolation test in CI; manual audit of NetworkPolicy rules

#### R-003: PII Scrubbing Completeness (Score: 6) - COMPLIANCE CRITICAL

**Mitigation Strategy:**
1. Create adversarial test corpus with realistic PII patterns (emails, IPs, JWT tokens, passwords in env vars, credit card numbers, API keys in log output)
2. Validate scrubber replaces all patterns with tagged placeholders (`[SCRUBBED:type]`)
3. Audit log of scrubbed content must capture what was removed (stored locally, never sent to LLM)
4. Add scrubber to CI — run against sample investigation logs from v0.1.0 production-like data

**Owner:** Backend/Security
**Timeline:** Sprint 0
**Status:** Planned
**Verification:** Unit tests with adversarial corpus (>20 PII patterns); integration test confirming zero PII in outbound LLM requests

#### R-004: Auto-Remediation False Positive (Score: 6) - BUSINESS CRITICAL

**Mitigation Strategy:**
1. Mandatory sandbox verification for all auto-applied fixes, regardless of trust level (even TL5)
2. Rollback mechanism must trigger within 60s if post-fix metrics show degradation (NFR16)
3. Confidence threshold enforcement: only apply fixes meeting the trust level's configured minimum
4. False positive auto-fix treated as critical bug — logged, alerted, trust level frozen

**Owner:** Backend/Architecture
**Timeline:** Sprint 1
**Status:** Planned
**Verification:** Integration test: inject known-bad fix -> verify sandbox catches it -> verify rollback triggers within 60s

#### R-008: SLO Burn Rate Calculation Lag (Score: 6) - PERFORMANCE

**Mitigation Strategy:**
1. Benchmark burn rate calculation loop with 100+ ServiceLevel CRDs, each querying Prometheus on 5s cycle
2. Ensure SLO calculation runs asynchronously (Tokio task) and does not block the main operator reconciliation loop
3. Batch Prometheus queries where possible (multi-target PromQL) to reduce round-trips
4. Add circuit breaker: if Prometheus query latency exceeds 3s, skip cycle and use cached burn rate

**Owner:** Rust/Backend
**Timeline:** Sprint 1
**Status:** Planned
**Verification:** Benchmark test with 100+ CRDs in CI (kind cluster); verify anomaly detection latency unaffected when SLO loop is under load

#### R-005: WebSocket Two-Channel Reliability (Score: 6) - TECHNICAL

**Mitigation Strategy:**
1. Flask-SocketIO pytest test client for room lifecycle (join, leave, broadcast)
2. Reconnect handling test: simulate client disconnect + reconnect -> verify state recovery
3. Concurrent room test: 10+ simultaneous investigation rooms -> verify message isolation
4. SSE + SocketIO coexistence test: verify HTMX partial swaps and SocketIO broadcasts work simultaneously for a single investigation

**Owner:** Backend
**Timeline:** Sprint 1
**Status:** Planned
**Verification:** Integration tests covering room lifecycle, reconnect, concurrent rooms; load test for 50+ concurrent investigation rooms

---

### Assumptions and Dependencies

#### Assumptions

1. v0.1.0's 1,032 tests continue passing throughout v0.2.0 development (stated in PRD/ADR as hard constraint)
2. Qdrant v1.15.0 payload-only collections are sufficient for durable outbox pattern (no message ordering guarantees needed beyond write order)
3. LLM providers (Claude via LiteLLM) have sufficient rate limits for 50+ concurrent investigations each making 2-4 LLM calls
4. K8s cluster in CI (kind or k3s) is available for CRD integration tests

#### Dependencies

1. **Test data seeding utilities for Qdrant** — Required by Sprint 0 for all integration tests
2. **Mock interfaces for external services (Slack, PagerDuty, Git)** — Required by Sprint 0 for notification and remediation tests
3. **Sandbox namespace with NetworkPolicy** — Required by Sprint 1 for auto-remediation tests
4. **Flask-SocketIO test client setup** — Required by Sprint 1 for collaboration tests

#### Risks to Plan

- **Risk**: Solo developer (eric) + AI-assisted development may bottleneck on test infrastructure setup
  - **Impact**: Sprint 0 blockers delay all subsequent test development
  - **Contingency**: Prioritize mock interfaces over full integration; use in-memory Qdrant for unit tests

---

**End of Architecture Document**

**Next Steps for Architecture Team:**
1. Review Quick Guide and prioritize blockers (R-001, R-002, R-003)
2. Assign owners and timelines for high-priority risks (>=6)
3. Validate assumptions and dependencies
4. Provide feedback on testability gaps (seeding APIs, external service mocks, Qdrant isolation)

**Next Steps for QA Team:**
1. Wait for Sprint 0 blockers to be resolved
2. Refer to companion QA doc (test-design-qa.md) for test scenarios
3. Begin test infrastructure setup (factories, fixtures, environments)
