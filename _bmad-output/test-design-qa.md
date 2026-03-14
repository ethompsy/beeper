# Test Design for QA: Beeper v0.2.0

**Purpose:** Test execution recipe for QA team. Defines what to test, how to test it, and what QA needs from other teams.

**Date:** 2026-03-13
**Author:** TEA Agent (requested by eric)
**Status:** Draft
**Project:** Beeper

**Related:** See Architecture doc ([test-design-architecture.md](test-design-architecture.md)) for testability concerns and architectural blockers.

---

## Executive Summary

**Scope:** Comprehensive test plan for Beeper v0.2.0 covering 63 FRs across 8 epics (SLO platform, notifications, trust system, auto-remediation, collaboration, KB enhancement, developer experience, demo application) and 22 NFRs (performance, security, reliability, scalability).

**Risk Summary:**
- Total Risks: 11 (6 high-priority score >=6, 3 medium, 2 low)
- Critical Categories: SEC (trust, sandbox, PII), BUS (auto-remediation), TECH (WebSocket), PERF (SLO engine)

**Coverage Summary:**
- P0 tests: ~28 (critical paths, security, trust enforcement)
- P1 tests: ~35 (important features, integration, notification)
- P2 tests: ~22 (edge cases, secondary features)
- P3 tests: ~10 (exploratory, benchmarks, accessibility)
- **Total**: ~95 tests (~4-7 weeks with 1 QA engineer)

**Test Stack:**
- Python: pytest + pytest-flask + pytest-asyncio + respx
- Rust: cargo test
- CI: GitHub Actions (cargo test + poetry run pytest per component)

---

## Dependencies & Test Blockers

**CRITICAL:** QA cannot proceed without these items from other teams.

### Backend/Architecture Dependencies (Sprint 0)

**Source:** See [Architecture doc "Quick Guide"](test-design-architecture.md#blockers---team-must-decide-cant-proceed-without) for detailed mitigation plans

1. **Test data seeding utilities for Qdrant** — Backend — Sprint 0
   - Need programmatic seeding for all 8 Qdrant collections (investigations, knowledge, service_trust_levels, slo_snapshots, notification_outbox, knowledge_versions, corrections, learning_patterns)
   - Without this, every integration test requires manual collection setup — blocks all P0/P1 tests

2. **External SDK abstraction with mock implementations** — Backend — Sprint 0
   - Notification channels use SDK clients (`slack-sdk`, `pdpyras`, `smtplib`) not raw HTTP
   - Git providers use SDK clients (`PyGithub`, `python-gitlab`)
   - Need interface-based abstraction with injectable mocks (existing `respx` only covers raw HTTP)
   - Blocks: all notification integration tests, auto-PR tests

3. **K8s test environment in CI** — DevOps — Sprint 0
   - CRD tests (ServiceLevel, NotificationChannel, Repository) require K8s API
   - Recommend: kind cluster in GitHub Actions workflow
   - Blocks: operator integration tests, CRD validation tests

### QA Infrastructure Setup (Sprint 0)

1. **Qdrant test fixtures** — QA
   - Factory functions for each collection with faker-based randomization
   - Auto-cleanup via pytest fixtures (yield + teardown)
   - Collection isolation strategy (test-scoped prefixes or sequential execution)

2. **Flask-SocketIO test client setup** — QA
   - pytest-compatible SocketIO client for room join/leave/broadcast assertions
   - Coordinated SSE + SocketIO test helper for investigation lifecycle tests

**Example factory pattern (pytest):**

```python
import pytest
from faker import Faker
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

fake = Faker()

@pytest.fixture
def seed_investigation(qdrant_client: QdrantClient):
    """Create a test investigation with cleanup."""
    investigations = []

    def _create(overrides: dict = None):
        inv = {
            "investigation_id": f"test-inv-{fake.uuid4()[:8]}",
            "service": fake.word(),
            "status": "investigating",
            "started_at": fake.iso8601(),
            "trust_level": 1,
            **(overrides or {}),
        }
        point = PointStruct(
            id=fake.uuid4(),
            vector=[0.0] * 1536,
            payload=inv,
        )
        qdrant_client.upsert("investigations", [point])
        investigations.append(point.id)
        return inv

    yield _create

    # Cleanup
    for inv_id in investigations:
        qdrant_client.delete("investigations", [inv_id])
```

---

## Risk Assessment

**Note:** Full risk details in [Architecture doc](test-design-architecture.md#risk-assessment). This section summarizes risks relevant to QA test planning.

### High-Priority Risks (Score >=6)

| Risk ID | Category | Description | Score | QA Test Coverage |
|---------|----------|-------------|-------|------------------|
| **R-001** | SEC | Trust level misconfiguration allows unauthorized autonomous actions | **6** | Boundary tests for every TL transition (P0-001 to P0-005); default-deny fallback test; cross-language enforcement test |
| **R-002** | SEC | Sandbox namespace leaks to production | **6** | Network isolation verification test (P0-006); DNS isolation test (P0-007) |
| **R-003** | SEC | PII/credentials sent to LLM provider | **6** | Adversarial PII corpus tests (P0-008 to P0-010); scrubber regression suite |
| **R-004** | BUS | Auto-remediation applies incorrect fix | **6** | Sandbox gate enforcement (P0-011); rollback trigger test (P0-012); confidence threshold test (P0-013) |
| **R-005** | TECH | WebSocket fails under concurrent rooms | **6** | Room lifecycle tests (P1-001 to P1-003); reconnect test (P1-004); concurrent rooms load test (P1-005) |
| **R-008** | PERF | SLO burn rate lag blocks operator event loop | **6** | Burn rate benchmark under 100+ CRDs (P1-006); operator responsiveness under SLO load (P1-007) |

### Medium/Low-Priority Risks

| Risk ID | Category | Description | Score | QA Test Coverage |
|---------|----------|-------------|-------|------------------|
| R-006 | DATA | KB entry poisoning degrades investigations | 4 | Validation status weighting tests (P1-014, P1-015) |
| R-007 | OPS | Notification delivery drops silently | 4 | Outbox retry tests (P1-008 to P1-010); false page tracking (P1-011) |
| R-009 | OPS | LLM provider outage — ungraceful degradation | 3 | Queue-and-retry test (P1-012); escalation timer test (P1-013) |
| R-010 | TECH | Command palette search latency | 1 | Semantic search latency benchmark (P3-001) |
| R-011 | OPS | Demo non-deterministic across 10 runs | 2 | 10-run demo reliability test (P2-018) |

---

## Test Coverage Plan

**Note:** All timing estimates assume Sprint 0 blockers resolved. P0/P1/P2/P3 = priority and risk level, NOT execution timing.

### P0 (Critical)

**Criteria:** Blocks core functionality + High risk (>=6) + No workaround + Affects majority of users

| Test ID | Requirement | Test Level | Risk Link | Notes |
|---------|-------------|------------|-----------|-------|
| **P0-001** | Trust level TL1 gates all autonomous actions | Integration | R-001 | Verify TL1 service: investigation runs but no auto-fix, no auto-PR |
| **P0-002** | Trust level TL3 auto-fixes only above confidence gate | Integration | R-001 | Set TL3 + 90% gate; inject fix with 89% confidence -> blocked; 91% -> allowed |
| **P0-003** | Trust level TL5 allows full autonomy within configured scope | Integration | R-001 | Verify TL5 permits all actions without approval |
| **P0-004** | Trust level default-deny on lookup failure | Unit | R-001 | Qdrant unavailable -> falls back to TL1, never escalates |
| **P0-005** | Trust level cross-language enforcement | Integration | R-001 | Set TL via Python API -> verify Rust operator spawns investigation with correct TL context -> verify Python investigator reads same TL |
| **P0-006** | Sandbox namespace blocks egress to production | Integration | R-002 | Deploy test pod in sandbox -> attempt HTTP to production service -> connection refused |
| **P0-007** | Sandbox DNS isolation from production | Integration | R-002 | Sandbox pod cannot resolve production service DNS names |
| **P0-008** | PII scrubber catches email addresses in logs | Unit | R-003 | Input: log line with emails -> output: `[SCRUBBED:email]` |
| **P0-009** | PII scrubber catches JWT tokens and API keys | Unit | R-003 | Input: log with `Bearer eyJ...`, `AKIA...` -> all scrubbed |
| **P0-010** | PII scrubber catches passwords in env vars | Unit | R-003 | Input: `DB_PASSWORD=secret123` -> scrubbed |
| **P0-011** | Auto-remediation requires sandbox verification | Integration | R-004 | Fix proposed -> sandbox test must run before production apply; skip sandbox -> blocked |
| **P0-012** | Auto-remediation rollback triggers on degradation | Integration | R-004 | Apply fix -> post-fix metrics show degradation -> rollback within 60s |
| **P0-013** | Auto-remediation respects confidence threshold | Unit | R-004 | TL3 with 90% gate: fix at 85% confidence -> blocked |
| **P0-014** | Permission model: admin-only routes reject user role | Integration | R-001 | User role -> PUT /api/v1/trust/services/{name} -> 403 |
| **P0-015** | Permission model: require_role decorator enforces on all new endpoints | Integration | R-001 | Enumerate all v0.2.0 routes -> verify each has role enforcement |
| **P0-016** | Investigation lifecycle: detect -> investigate -> complete | Integration | — | End-to-end investigation state machine: pending -> started -> investigating -> completed |
| **P0-017** | Investigation lifecycle: failure state | Integration | — | Investigation encounters unrecoverable error -> status = failed, no hang |
| **P0-018** | v0.1.0 regression: all existing 1,032 tests pass | Unit/Integration | — | Run full existing test suite — zero regressions |
| **P0-019** | Non-SPOF: Beeper down does not affect existing alerting | Integration | — | Beeper operator pod killed -> Prometheus/Loki alerting continues unaffected |
| **P0-020** | PII scrubber adversarial corpus (20+ patterns) | Unit | R-003 | Corpus includes: SSNs, credit cards, phone numbers, IPs, connection strings, AWS keys, GCP tokens, OAuth secrets, K8s tokens |

**Total P0:** ~20 tests

---

### P1 (High)

**Criteria:** Important features + Medium risk (3-4) + Common workflows + Workaround exists but difficult

| Test ID | Requirement | Test Level | Risk Link | Notes |
|---------|-------------|------------|-----------|-------|
| **P1-001** | SocketIO: join investigation room + receive broadcasts | Integration | R-005 | Flask-SocketIO test client joins room -> server emits evidence_update -> client receives |
| **P1-002** | SocketIO: leave room stops broadcasts | Integration | R-005 | Leave room -> subsequent broadcasts not received |
| **P1-003** | SocketIO: annotate event reaches room members | Integration | R-005 | Client A annotates -> Client B in same room receives annotation |
| **P1-004** | SocketIO: client reconnect recovers state | Integration | R-005 | Disconnect -> reconnect -> rejoin room -> receive pending updates |
| **P1-005** | SocketIO: 10+ concurrent investigation rooms isolated | Integration | R-005 | 10 rooms open -> broadcast to room 3 -> only room 3 clients receive |
| **P1-006** | SLO burn rate calculation under 100+ CRDs | Integration | R-008 | 100 ServiceLevel CRDs -> burn rate loop completes in <5s |
| **P1-007** | Operator responsiveness during SLO calculation | Integration | R-008 | SLO loop running -> new anomaly detected -> investigation spawned without delay |
| **P1-008** | Notification outbox: delivery with retry on failure | Integration | R-007 | Write to outbox -> channel fails -> retry with backoff -> succeeds on retry |
| **P1-009** | Notification outbox: durable across process restart | Integration | R-007 | Write to outbox -> kill worker -> restart -> pending notifications delivered |
| **P1-010** | Notification routing: severity + service + time-of-day rules | Integration | R-007 | Configure routing rules -> inject events -> verify correct channel receives correct notifications |
| **P1-011** | False page tracking: notification marked as false page | Integration | R-007 | User marks notification as false page -> tracked in audit -> noise report reflects it |
| **P1-012** | LLM provider outage: investigation queued | Integration | R-009 | Mock LLM timeout -> investigation enters queue -> human escalation within 60s |
| **P1-013** | LLM provider recovery: queued investigations resume | Integration | R-009 | LLM recovers -> queued investigations dequeued and processed |
| **P1-014** | KB entry validation status weighting | Unit | R-006 | Human-confirmed entry scores higher than AI-generated in search relevance |
| **P1-015** | KB entry correction tracked and weighted | Unit | R-006 | Corrected entry updates weight; correction history preserved |
| **P1-016** | SLO dashboard: burn rate, error budget, compliance | Integration | — | Create ServiceLevel CRD -> ingest metrics -> dashboard endpoint returns correct burn rate and budget |
| **P1-017** | Customer impact scoring: SLO-based anomaly prioritization | Integration | — | Two anomalies, different SLO severity -> higher SLO impact ranked first |
| **P1-018** | Notification: Slack rich message with evidence links | Integration | — | Investigation completed -> Slack channel receives block-formatted message with evidence |
| **P1-019** | Notification: PagerDuty bidirectional incident lifecycle | Integration | — | Create incident on critical -> acknowledge on investigation start -> resolve on fix verified |
| **P1-020** | Notification: quiet hours respected | Unit | — | Notification triggered during quiet hours -> suppressed (unless critical + escalation override) |
| **P1-021** | Auto-PR: evidence trail in PR description | Integration | — | Investigation resolves -> PR created -> description contains log correlations, KB references, sandbox results |
| **P1-022** | Trust level configuration: admin can change TL per service | Integration | — | Admin PUT /api/v1/trust/services/payments -> TL changes from 2 to 3 -> audit logged |
| **P1-023** | Trust level accuracy tracking | Integration | — | 10 investigations: 8 accurate, 2 corrected -> accuracy = 80% |
| **P1-024** | Investigation feedback: one-click accurate/inaccurate | Integration | — | POST /api/v1/investigations/{id}/feedback -> feedback recorded -> accuracy updated |
| **P1-025** | Shift handoff summary generation | Integration | — | Active investigations + resolved in last 8h + watch items -> summary endpoint returns structured handoff |
| **P1-026** | KB auto-creation from resolved investigation | Integration | — | Investigation resolves -> KB entry auto-created with bi-directional link |
| **P1-027** | ServiceLevel CRD validation | Integration | — | Invalid CRD spec -> operator rejects with status condition; valid CRD -> reconciled |
| **P1-028** | NotificationChannel CRD validation | Integration | — | Invalid CRD -> rejected; valid CRD with credentials_secret -> channel registered |
| **P1-029** | Repository CRD validation | Integration | — | Invalid CRD -> rejected; valid CRD with scoped credentials -> repository registered |
| **P1-030** | Error budget policy: notification on budget exhaustion | Integration | — | SLO budget drops below threshold -> notification triggered |

**Total P1:** ~30 tests

---

### P2 (Medium)

**Criteria:** Secondary features + Low risk (1-2) + Edge cases + Regression prevention

| Test ID | Requirement | Test Level | Risk Link | Notes |
|---------|-------------|------------|-----------|-------|
| **P2-001** | Notification: email digest formatting | Unit | — | Daily digest includes investigation summaries, SLO status |
| **P2-002** | Notification: webhook payload structure | Unit | — | POST body matches documented schema (investigation_id, evidence, status) |
| **P2-003** | KB version history preserved on edit | Integration | — | Edit KB entry -> previous version stored in knowledge_versions |
| **P2-004** | KB bi-directional links between entries | Integration | — | Entry A links to entry B -> B shows backlink to A |
| **P2-005** | KB per-service knowledge view | Integration | — | Filter KB by service -> returns only entries for that service |
| **P2-006** | Investigation timeline: correlate logs + metrics + deploys | Integration | — | Investigation correlates deploy event with anomaly start time |
| **P2-007** | Deploy correlation: anomaly within 10 min of deploy flagged | Unit | — | Anomaly at T+4min after deploy -> "anomaly started 4 min after deploy #847" |
| **P2-008** | Command palette: client-side navigation instant | Unit | — | Known routes matched in <50ms client-side |
| **P2-009** | Command palette: async Qdrant search with 300ms debounce | Integration | R-010 | Type query -> 300ms debounce -> Qdrant semantic search returns results |
| **P2-010** | Investigation workflow states visible in UI | Integration | — | Investigation transitions -> API returns correct state at each transition |
| **P2-011** | Remediation progress tracking endpoint | Integration | — | Detection -> investigation -> fix -> verification -> each stage queryable |
| **P2-012** | Per-service health feed | Integration | — | Service has 3 recent investigations + SLO status -> health feed aggregates correctly |
| **P2-013** | Reliability score calculation (composite) | Unit | — | SLO compliance + incident frequency + MTTR -> composite score formula correct |
| **P2-014** | MTTR trend calculation | Unit | — | 10 investigations with resolution times -> MTTR trend computed correctly |
| **P2-015** | Service dependency topology discovery | Integration | — | K8s service mesh data -> topology graph endpoint returns connected services |
| **P2-016** | Change event ingestion (config, scaling, DNS) | Integration | — | Emit config change event -> event stored and correlatable with anomalies |
| **P2-017** | Noise report: signal-to-noise ratio calculation | Unit | — | N investigations, M false pages -> ratio = (N-M)/N |
| **P2-018** | Demo app: 10 consecutive lifecycle runs | E2E | R-011 | Scripted demo: inject fault -> detect -> investigate -> fix -> verify -> recover — 10x without failure |
| **P2-019** | Demo app: configurable fault injection types | Integration | — | Memory leak, bad deploy, cascading failure -> each type injectable and detectable |
| **P2-020** | Runbook execution: human-language runbook parsed and executed | Integration | — | Plain-text runbook -> investigator interprets steps -> executes without DSL |
| **P2-021** | Error budget policy: deployment freeze trigger | Integration | — | Budget exhausted -> deployment freeze notification sent |
| **P2-022** | Adaptive alert thresholds from feedback | Unit | — | Multiple "not-an-issue" feedbacks -> alert threshold adjusts upward |

**Total P2:** ~22 tests

---

### P3 (Low)

**Criteria:** Nice-to-have + Exploratory + Performance benchmarks + Documentation validation

| Test ID | Requirement | Test Level | Notes |
|---------|-------------|------------|-------|
| **P3-001** | Semantic search latency under 10K+ KB entries | Integration | Benchmark: <2s response time with 10K entries |
| **P3-002** | Concurrent investigations: 50+ without degradation | Integration | Load test: spawn 50 investigations simultaneously |
| **P3-003** | Notification throughput: 1000+ events/hour | Integration | Load test: inject 1000 notification events in <1 hour |
| **P3-004** | Anomaly-to-investigation latency <30s | Integration | NFR1: time from anomaly detection to investigation start |
| **P3-005** | UI response time <2s for all endpoints | Integration | NFR2: benchmark all v0.2.0 API endpoints |
| **P3-006** | LLM screening round-trip <10s | Integration | NFR3: mock LLM with realistic latency |
| **P3-007** | WebSocket delivery <500ms | Integration | NFR5: measure SocketIO event delivery time |
| **P3-008** | WCAG 2.1 AA: axe-core validation on key pages | E2E | Accessibility audit on investigation, dashboard, trust config pages |
| **P3-009** | Structured JSON logging validation | Unit | All log statements include required fields (timestamp, level, component, message) |
| **P3-010** | OpenAPI spec: all v0.2.0 endpoints documented | Unit | Compare implemented routes against openapi/beeper-api.yaml |

**Total P3:** ~10 tests

---

## Execution Strategy

**Philosophy:** Run everything in PRs unless there's significant infrastructure overhead. pytest with parallel execution is fast for unit and integration tests.

**Organized by TOOL TYPE:**

### Every PR: pytest + cargo test (~5-10 min)

All functional tests (from any priority level):
- **Rust:** `cargo test` — operator unit + integration tests
- **Python investigator:** `poetry run pytest` — investigator unit + integration tests
- **Python UI:** `poetry run pytest` — UI unit + integration + Flask test client tests
- Includes P0, P1, P2, P3 tests that don't require K8s cluster or external infrastructure
- Total: ~80 tests across 3 components

**Why run in PRs:** Fast feedback, no expensive infrastructure, existing CI pattern

### Nightly: K8s integration tests (~15-30 min)

Tests requiring kind/k3s cluster:
- CRD validation tests (ServiceLevel, NotificationChannel, Repository)
- Sandbox network isolation verification (P0-006, P0-007)
- Operator + investigator cross-language trust enforcement (P0-005)
- SLO burn rate benchmark under 100+ CRDs (P1-006, P1-007)
- Total: ~10 tests

**Why defer to nightly:** K8s cluster setup overhead (~2-3 min), longer execution time

### Weekly: Load + E2E demo (~1-2 hours)

Long-running and resource-intensive tests:
- Demo app 10-consecutive-run reliability (P2-018)
- Concurrent investigations load test — 50+ simultaneous (P3-002)
- Notification throughput 1000+ events/hour (P3-003)
- NFR benchmark suite (P3-004 to P3-007)

**Why defer to weekly:** Long-running (10-run demo), resource-intensive (50+ concurrent investigations), infrequent validation sufficient

---

## QA Effort Estimate

**QA test development effort only** (excludes DevOps, Backend infrastructure work):

| Priority | Count | Effort Range | Notes |
|----------|-------|--------------|-------|
| P0 | ~20 | ~2-3.5 weeks | Complex setup (trust boundaries, PII corpus, sandbox isolation, cross-language) |
| P1 | ~30 | ~2-3.5 weeks | Standard integration (SocketIO, notifications, SLO, KB, CRDs) |
| P2 | ~22 | ~1-2 weeks | Edge cases, secondary features, straightforward validation |
| P3 | ~10 | ~0.5-1 week | Benchmarks, exploratory, accessibility |
| **Total** | **~82** | **~5.5-10 weeks** | **1 QA engineer, full-time** |

**Note:** With 2 QA engineers working in parallel (P0+P1 split): ~3-5 weeks.

**Assumptions:**
- Includes test design, implementation, debugging, CI integration
- Excludes ongoing maintenance (~10% effort)
- Assumes Sprint 0 blockers resolved (seeding utilities, SDK mocks, K8s CI environment)
- Assumes existing pytest infrastructure reusable (conftest.py patterns, Flask test client)

**Dependencies from other teams:**
- See "Dependencies & Test Blockers" section for what QA needs from Backend, DevOps

---

## Appendix A: Code Examples & Tagging

**pytest markers for selective execution:**

```python
# conftest.py - Test markers
import pytest

def pytest_configure(config):
    config.addinivalue_line("markers", "p0: Critical priority tests")
    config.addinivalue_line("markers", "p1: High priority tests")
    config.addinivalue_line("markers", "p2: Medium priority tests")
    config.addinivalue_line("markers", "p3: Low priority tests")
    config.addinivalue_line("markers", "security: Security-related tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "k8s: Requires K8s cluster")
    config.addinivalue_line("markers", "load: Load/performance tests")
```

```python
# Example P0 security test
import pytest

@pytest.mark.p0
@pytest.mark.security
def test_trust_level_default_deny_on_lookup_failure(
    mock_qdrant_unavailable, trust_service
):
    """R-001: Trust level lookup failure falls back to TL1, never escalates."""
    result = trust_service.get_trust_level("payment-service")

    assert result.level == 1  # TL1 = advisory only
    assert result.allows_auto_fix is False
    assert result.allows_auto_pr is False
```

```python
# Example P0 PII scrubbing test
@pytest.mark.p0
@pytest.mark.security
def test_pii_scrubber_catches_jwt_tokens(pii_scrubber):
    """R-003: JWT tokens scrubbed before LLM context."""
    log_line = 'Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig'
    result = pii_scrubber.scrub(log_line)

    assert "eyJ" not in result
    assert "[SCRUBBED:jwt]" in result
```

```python
# Example P1 SocketIO test
@pytest.mark.p1
@pytest.mark.integration
def test_socketio_room_broadcast_isolation(socketio_client_factory):
    """R-005: Broadcast to room 3 only reaches room 3 clients."""
    client_a = socketio_client_factory(room="inv-001")
    client_b = socketio_client_factory(room="inv-002")

    # Server broadcasts to inv-001 room
    emit_to_room("inv-001", "evidence_update", {"step": "correlating"})

    assert client_a.received("evidence_update")
    assert not client_b.received("evidence_update")
```

**Run specific markers:**

```bash
# Run only P0 tests
poetry run pytest -m p0

# Run P0 + P1 tests
poetry run pytest -m "p0 or p1"

# Run only security tests
poetry run pytest -m security

# Run everything except K8s-dependent tests (PR pipeline)
poetry run pytest -m "not k8s and not load"

# Run K8s integration tests (nightly)
poetry run pytest -m k8s
```

---

## Appendix B: Knowledge Base References

- **Risk Governance**: `risk-governance.md` — Risk scoring methodology (probability x impact = 1-9)
- **Test Priorities Matrix**: `test-priorities-matrix.md` — P0-P3 criteria and classification
- **Test Levels Framework**: `test-levels-framework.md` — Unit vs integration vs E2E selection
- **Test Quality**: `test-quality.md` — Definition of Done (no hard waits, <300 lines, <1.5 min, deterministic)
- **ADR Quality Checklist**: `adr-quality-readiness-checklist.md` — 8-category 29-criteria NFR framework

---

**Generated by:** BMad TEA Agent
**Workflow:** `_bmad/bmm/testarch/test-design`
**Version:** 4.0 (BMad v6)
