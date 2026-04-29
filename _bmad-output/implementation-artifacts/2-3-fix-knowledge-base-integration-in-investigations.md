# Story 2.3: Fix Knowledge Base Integration in Investigations

Status: ready-for-dev

## Story

As a **developer**,
I want the investigator to search Qdrant for similar past incidents and store outcomes for future reference,
So that investigations benefit from accumulated institutional knowledge.

## Background

Story 2.2 verified signal gathering — Prometheus and Loki URLs are now correctly injected and the investigator can query observability sources. Now the Knowledge Base (KB) integration must work end-to-end: the KBQueryStep (2nd in the 16-step pipeline) searches Qdrant for similar past incidents, and after investigation completion, `AutoKBCreationService` stores outcomes for future reference.

**Epic 2 dependency chain:** 2.1 (lifecycle) → 2.2 (signal gathering) → **2.3 (KB integration)** → 2.4 (LLM RCA) → 2.5 (ServiceLevel CRD)

## Acceptance Criteria

1. **Given** an investigator is executing a KB query step
   **When** it searches the Qdrant `investigations` collection for the anomalous service
   **Then** it returns relevant past incidents (or an empty result set) without errors (FR17)
   **And** the KB query step results are stored in the investigation's step data (AD-5 verification)

2. **Given** an investigation completes with a root cause conclusion
   **When** the investigator stores the outcome
   **Then** a new Knowledge Base entry is created in Qdrant with the investigation context, service name, and resolution (FR30)

3. **Given** Qdrant is upgraded to v1.15.0 in the Helm chart
   **When** KB operations execute
   **Then** all read/write operations function correctly with the new Qdrant version

## Tasks / Subtasks

- [ ] Task 1: Verify current KB integration baseline (AC: all)
  - [ ] 1.1 Run KB test suites: `poetry run pytest tests/test_kb_query.py tests/test_kb_client.py tests/test_auto_kb_creation.py -v` — confirm 104 tests pass (35 + 37 + 32)
  - [ ] 1.2 Review KBQueryStep (`steps/kb_query.py`, 349 lines): verify Qdrant search calls target `investigations` and `knowledge` collections correctly
  - [ ] 1.3 Review KBClient (`kb/client.py`, 324 lines): verify `search_investigations()` and `search_knowledge()` use correct collection names, vector dimensions (1536), and filters
  - [ ] 1.4 Review AutoKBCreationService (`kb/auto_creation.py`, 468 lines): verify `create_or_update_from_investigation()` handles duplicate detection (similarity ≥ 0.85), versioning, and retry with backoff
  - [ ] 1.5 Review agent.py pipeline wiring: verify KBQueryStep is 2nd step (after CustomerImpactStep), receives `kb_client` and `llm_client`, and `_auto_create_kb_entry()` runs in finalization
  - [ ] 1.6 Check operator QDRANT_HOST/QDRANT_PORT env var injection: `investigator_job.rs:224-231` passes config to Job env vars, KBClient reads from `QDRANT_HOST`/`QDRANT_PORT` env vars with localhost defaults

- [ ] Task 2: Upgrade Qdrant from v1.12.0 to v1.15.0 (AC: #3)
  - [ ] 2.1 Update `helm/beeper/values.yaml`: `qdrant.image.tag` from `v1.12.0` to `v1.15.0`
  - [ ] 2.2 Update `helm/beeper/values-dev.yaml`: `qdrant.image.tag` from `v1.12.0` to `v1.15.0` (if overridden)
  - [ ] 2.3 Verify `qdrant-client` Python package version compatibility with Qdrant v1.15.0 — check `pyproject.toml` for version constraint
  - [ ] 2.4 `helm lint helm/beeper/` — clean
  - [ ] 2.5 Verify Qdrant v1.15.0 image exists: `docker pull qdrant/qdrant:v1.15.0`

- [ ] Task 3: Verify/fix KBQueryStep read path (AC: #1)
  - [ ] 3.1 Trace full search flow: KBQueryStep.execute() → _search_kb() → KBClient.search_investigations() / search_knowledge() → Qdrant vector search
  - [ ] 3.2 Verify embedding generation: check how query vectors are created for search (LLM-based or static?)
  - [ ] 3.3 Verify results are stored in step data: StepResult.data should contain `prior_research_summary`, `relevant_matches`, `confidence_boost`
  - [ ] 3.4 Verify empty result handling: KBQueryStep should return valid StepResult with empty matches when no similar incidents exist
  - [ ] 3.5 Verify AD-5 compliance: results from KBQueryStep should be accessible for the Related KB panel (via investigation step data)

- [ ] Task 4: Verify/fix AutoKBCreationService write path (AC: #2)
  - [ ] 4.1 Trace write flow: InvestigatorAgent._auto_create_kb_entry() → AutoKBCreationService.create_or_update_from_investigation() → Qdrant upsert
  - [ ] 4.2 Verify duplicate detection: similarity search with threshold 0.85 before creating new entries
  - [ ] 4.3 Verify enrichment path: when similar entry exists (≥ 0.85), enriches existing entry instead of creating duplicate
  - [ ] 4.4 Verify version snapshots: check that knowledge_versions collection receives point on update
  - [ ] 4.5 Verify file buffering fallback: when Qdrant is unavailable, entries buffer to `/tmp/beeper-buffer`
  - [ ] 4.6 Verify investigation result persistence: `_persist_investigation_result()` upserts to `investigations` collection

- [ ] Task 5: Run full test suite and CI checks (AC: all)
  - [ ] 5.1 `poetry run pytest` → all passed (expect ~1011+, 2 pre-existing failures in git_provider)
  - [ ] 5.2 `cargo test --lib` → all passed (expect 572+)
  - [ ] 5.3 `cargo fmt --check` → clean
  - [ ] 5.4 `cargo clippy -- -D warnings` → clean
  - [ ] 5.5 `helm lint helm/beeper/` → clean

- [ ] Task 6: E2E verification on live cluster (AC: all)
  - [ ] 6.1 `make demo-build` — rebuild images with any changes, load into kind
  - [ ] 6.2 `helm upgrade beeper helm/beeper -n beeper -f helm/beeper/values-dev.yaml` — deploy with Qdrant v1.15.0
  - [ ] 6.3 Verify Qdrant pod is Running with v1.15.0 image
  - [ ] 6.4 Verify existing collections (investigations, knowledge, knowledge_versions) survived upgrade
  - [ ] 6.5 Create test Investigation CRD — verify KBQueryStep executes (check investigator pod logs)
  - [ ] 6.6 Verify investigation result persisted to `investigations` collection in Qdrant
  - [ ] 6.7 Verify KB entry auto-created in `knowledge` collection (if investigation completed successfully)
  - [ ] 6.8 **NOTE:** E2E may be blocked by operator OOMKill (pre-existing SLO engine issue from Story 2.2). Document gap if so.

## Dev Notes

### KB Architecture Overview

```
Investigation Pipeline (agent.py)
├── Step 2: KBQueryStep (kb_query.py, 349 lines)
│   ├── search_investigations() → Qdrant `investigations` collection
│   ├── search_knowledge() → Qdrant `knowledge` collection
│   ├── LLM synthesis of prior research
│   └── StepResult.data: prior_research_summary, relevant_matches, confidence_boost
│
├── Step 16: InvestigationDocumentationStep
│   └── Uses KB client for documentation storage
│
└── Finalization: _auto_create_kb_entry() (agent.py:439-477)
    └── AutoKBCreationService (auto_creation.py, 468 lines)
        ├── Duplicate detection (similarity ≥ 0.85)
        ├── Enrichment of existing entries
        ├── Version snapshots in knowledge_versions
        └── File buffer fallback on failure
```

### Qdrant Collections (6 total, 1536d vectors)

| Collection | Purpose | Used By |
|------------|---------|---------|
| `investigations` | Investigation results for vector search | KBQueryStep (read), _persist_investigation_result (write) |
| `knowledge` | KB entries for similar incident lookup | KBQueryStep (read), AutoKBCreationService (write) |
| `knowledge_versions` | Version history for KB entry updates | AutoKBCreationService (write) |
| `corrections` | Human corrections to KB entries | Not used in pipeline (UI-facing) |
| `learning_patterns` | ML-derived patterns | Not used in pipeline |
| `service_trust_levels` | Trust scores per service | Not used in pipeline |

### Key Source Files

| File | Lines | Purpose |
|------|-------|---------|
| `investigator/beeper_investigator/steps/kb_query.py` | 349 | KBQueryStep: search → LLM synthesis → StepResult |
| `investigator/beeper_investigator/kb/client.py` | 324 | KBClient: Qdrant operations, lazy init, thread-safe |
| `investigator/beeper_investigator/kb/auto_creation.py` | 468 | AutoKBCreationService: create/update with dedup |
| `investigator/beeper_investigator/kb/schemas.py` | — | SearchResult, CollectionInfo dataclasses |
| `investigator/beeper_investigator/agent.py` | — | Pipeline wiring, _persist_investigation_result, _auto_create_kb_entry |
| `investigator/beeper_investigator/main.py` | 161-163 | KB client init from QDRANT_HOST/QDRANT_PORT env vars |
| `operator/src/investigator_job.rs` | 224-231 | QDRANT_HOST/QDRANT_PORT env var injection into Job |
| `helm/beeper/values.yaml` | 59-70 | Qdrant image tag, persistence, collections config |
| `helm/beeper/templates/operator-deployment.yaml` | 48-49 | QDRANT_URL for operator's own Qdrant access |
| `investigator/tests/test_kb_query.py` | 556 | 35 tests: search, synthesis, error handling |
| `investigator/tests/test_kb_client.py` | 648 | 37 tests: schema, search, thread-safety, env vars |
| `investigator/tests/test_auto_kb_creation.py` | 884 | 32 tests: dedup, enrichment, versioning, buffering |

### Environment Variable Flow (KB)

```
Helm values.yaml                    Operator Deployment                  Investigator Job
─────────────────                   ────────────────────                 ────────────────
(Qdrant URL for operator)     →     QDRANT_URL=http://beeper-qdrant:6333
                                    BEEPER_INVESTIGATOR_QDRANT_HOST →    QDRANT_HOST=beeper-qdrant
                                    (from operator-deployment.yaml:74)    (from investigator_job.rs:224)
                                    BEEPER_INVESTIGATOR_QDRANT_PORT  →   (not explicitly set — uses default 6333)
                                    (defaults to "6333")                  (KBClient defaults to 6333)
```

### Qdrant Version Upgrade Risk Assessment

- **Current:** v1.12.0 (Helm chart)
- **Target:** v1.15.0 (per architecture doc)
- **Risk:** Low — Qdrant maintains backward compatibility for REST/gRPC APIs across minor versions. The `qdrant-client` Python SDK abstracts version differences.
- **Migration:** No data migration needed — Qdrant auto-upgrades storage format on startup
- **Verification:** Existing collections + data must survive the upgrade (check point counts)

### What NOT To Do

- Do NOT modify the Investigation CRD schema — it is stable
- Do NOT change the investigator step pipeline order or add new steps
- Do NOT add new Python dependencies (qdrant-client already available)
- Do NOT change KBClient API signatures unless a bug is found
- Do NOT modify AutoKBCreationService's duplicate detection thresholds without justification
- Do NOT change the operator's QDRANT_URL or investigator's QDRANT_HOST env var names
- Do NOT modify Qdrant collection schemas (vector dimensions, distance metrics)

### Testing Strategy

- **Unit tests:** Verify KB read/write operations (test_kb_query.py, test_kb_client.py, test_auto_kb_creation.py — 104 tests total)
- **Integration:** Verify Qdrant v1.15.0 compatibility via `helm lint` and image pull
- **E2E:** Create Investigation on live cluster, verify KBQueryStep logs and Qdrant collections
- Follow established patterns: pytest with fixtures, MagicMock for Qdrant client, helper functions for test setup

### Previous Intelligence

- **Story 2.2:** Signal gathering fixed via Helm template — LOKI_URL injection, PROMETHEUS_URL from values, conditional on `sources.*.enabled`. LOKI_URL fallback chain added to `investigator_job.rs`. E2E blocked by operator OOMKill (SLO engine memory leak).
- **Story 2.1:** Investigation lifecycle verified. 572 operator tests pass. E2E: Pending→Running→Completed in ~31s.
- **Story 2.0d:** Qdrant healthy with 89,877 investigation points in `investigations` collection.
- **Story 2.0e:** LLM config chain verified. Operator OOMKill resolved (memory bumped to 2Gi).
- **Learnings:** `cargo fmt` first, `cargo clippy -- -D warnings`, E2E mandatory (but may be blocked by operator OOMKill — document gap), one commit per story, conditional Helm rendering for optional env vars.

### Project Structure Notes

- KB code lives entirely in `investigator/beeper_investigator/kb/` (client.py, auto_creation.py, schemas.py)
- Step code in `investigator/beeper_investigator/steps/kb_query.py`
- Tests in `investigator/tests/test_kb_*.py` and `investigator/tests/test_auto_kb_creation.py`
- Qdrant Helm config in `helm/beeper/values.yaml` under `qdrant:` key
- No variances with project structure conventions detected

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 2, Story 2.3]
- [Source: _bmad-output/planning-artifacts/architecture.md — FR17, FR30, AD-5, Qdrant version alignment]
- [Source: investigator/beeper_investigator/steps/kb_query.py — KBQueryStep]
- [Source: investigator/beeper_investigator/kb/client.py — KBClient, search_investigations, search_knowledge]
- [Source: investigator/beeper_investigator/kb/auto_creation.py — AutoKBCreationService]
- [Source: investigator/beeper_investigator/agent.py:211-222 — Pipeline wiring, KBQueryStep at position 2]
- [Source: investigator/beeper_investigator/agent.py:439-477 — _auto_create_kb_entry finalization]
- [Source: investigator/beeper_investigator/main.py:161-163 — KB client initialization]
- [Source: operator/src/investigator_job.rs:224-231 — QDRANT_HOST/QDRANT_PORT env var injection]
- [Source: helm/beeper/values.yaml:59-70 — Qdrant configuration]
- [Source: helm/beeper/templates/operator-deployment.yaml:48-49 — QDRANT_URL for operator]
- [Source: investigator/tests/test_kb_query.py — 35 KB query tests]
- [Source: investigator/tests/test_kb_client.py — 37 KB client tests]
- [Source: investigator/tests/test_auto_kb_creation.py — 32 auto KB creation tests]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

### File List
