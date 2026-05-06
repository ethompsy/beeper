# Story 3.0c: Full Demo Walkthrough

Status: failed

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to execute a complete demo walkthrough (deploy → fault inject → detect → investigate → RCA → UI display),
So that the full Beeper pipeline is validated end-to-end including the UI layer, deliberate fault injection is proven, and Epic 3 UI work is unblocked with confidence.

## Background

**Origin:** Epic 2 retrospective (2026-05-01) — HIGH priority action item. The full demo walkthrough was Epic 1's exit criteria but was never met due to the SLO memory leak.

**epic's directive (from Epic 1 retro):** "Full demo walkthrough as Epic 2 exit criteria"

**Why this is distinct from Story 3-0b:**
- Story 3-0b verified the **backend pipeline** (1,310+ organic EWMA investigations completed)
- Story 3-0b **NEVER tested deliberate fault injection** (`make demo-fault FAULT=payment-failure`) — all investigations were organic detections
- Story 3-0c validates the **complete demo experience** including:
  1. Deliberate fault injection via the flagd feature flag mechanism
  2. Detection of the injected fault specifically (not just organic anomalies)
  3. Investigation RCA quality for the specific injected fault
  4. **UI display** of the investigation (list view + detail view + findings + recommendations)

**Dependencies:**
- Story 3-0a (memory leak fix) — DONE (commit `16ffce3`)
- Story 3-0b (E2E pipeline verification) — DONE (commit `a4c86ce`)

## Acceptance Criteria

1. **Given** the full Beeper stack is deployed via `make demo-up`
   **When** all pods in `beeper` and `otel-demo` namespaces are running
   **Then** the operator, investigator image, UI, Qdrant, OTel Collector, Prometheus, and all OTel demo services are healthy

2. **Given** the stack has been running for 10+ minutes (EWMA baseline warmup)
   **When** a fault is deliberately injected via `make demo-fault FAULT=payment-failure`
   **Then** the EWMA detector detects an anomaly in the payment service within 10 minutes (NFR1)
   **And** an Investigation CRD is created automatically

3. **Given** an Investigation CRD is created from the deliberate fault injection
   **When** the investigator Job executes
   **Then** it gathers Prometheus signals (real metric data from the payment service)
   **And** LLM RCA identifies the fault as related to payment service failures
   **And** recommendations reference the payment service specifically

4. **Given** the investigation has completed
   **When** the user navigates to `http://localhost:5050/investigations/` in a browser
   **Then** the investigation list shows the completed investigation with correct service name and status
   **And** clicking the investigation shows the detail page with:
     - Investigation header (service, status, severity, timestamps)
     - Step progress timeline showing completed steps
     - Findings section with RCA hypothesis
     - Recommendations section with resolution steps

5. **Given** the demo walkthrough has completed successfully
   **When** the fault is recovered via `make demo-recover`
   **Then** no new anomalies are created for the payment service after recovery stabilizes (~2 min)
   **And** the system returns to normal operation

## Tasks / Subtasks

- [ ] Task 1: Deploy full stack and verify health (AC: #1)
  - [ ] 1.1 Ensure Docker Desktop has sufficient resources (16GB+ RAM, recommend 32GB)
  - [ ] 1.2 Export `ANTHROPIC_API_KEY` environment variable
  - [ ] 1.3 Run `make demo-up` — creates kind cluster, builds images, deploys everything
  - [ ] 1.4 Wait for all pods to reach Running: `kubectl get pods -n beeper && kubectl get pods -n otel-demo`
  - [ ] 1.5 Verify operator pod is running with Story 3-0a/3-0b fixes (latest main)
  - [ ] 1.6 Verify UI pod is running: `kubectl get pods -n beeper -l app=beeper-ui`
  - [ ] 1.7 Verify ServiceLevel CRDs are deployed: `kubectl get servicelevels -n otel-demo`
  - [ ] 1.8 Start port-forwarding: `make demo-ui` (Beeper UI → localhost:5050)
  - [ ] 1.9 Verify UI loads in browser at http://localhost:5050

- [ ] Task 2: Wait for EWMA baseline and verify detection readiness (AC: #2)
  - [ ] 2.1 Wait 10+ minutes for EWMA baseline data to accumulate
  - [ ] 2.2 Verify operator logs show "SLO calculation complete" entries (SLO engine active)
  - [ ] 2.3 Verify operator is receiving metrics: check `/api/v1/ingestion/stats` via port-forward or logs
  - [ ] 2.4 Optionally check `make demo-fault-status` shows all flags at defaults

- [ ] Task 3: Inject fault and verify detection (AC: #2)
  - [ ] 3.1 Inject fault: `make demo-fault FAULT=payment-failure`
  - [ ] 3.2 Verify fault flag is set: `make demo-fault-status`
  - [ ] 3.3 Watch for anomaly detection: `kubectl get investigations -n beeper -w`
  - [ ] 3.4 Verify an Investigation CRD is created within 10 minutes
  - [ ] 3.5 Note the Investigation name for tracking
  - [ ] 3.6 **If no detection after 10 min:** Check operator logs for EWMA activity, verify Prometheus is receiving payment service metrics. SURFACE TO ERIC IMMEDIATELY.

- [ ] Task 4: Verify investigation quality (AC: #3)
  - [ ] 4.1 Watch Investigation transition: Pending → Running → Completed
  - [ ] 4.2 Check investigator Job logs: `kubectl logs -n beeper job/<job-name>`
  - [ ] 4.3 Verify Prometheus signal gathering (should show payment service metrics)
  - [ ] 4.4 Verify LLM RCA mentions payment service / payment failures
  - [ ] 4.5 Verify recommendations are relevant to the injected fault
  - [ ] 4.6 Record: Investigation name, duration, RCA summary, recommendation count
  - [ ] 4.7 **Known limitations (NOT failures):** Loki queries may return empty (Loki not deployed). KB queries may be skipped (embedding model not configured).

- [ ] Task 5: Verify UI display (AC: #4)
  - [ ] 5.1 Navigate to http://localhost:5050/investigations/ in browser
  - [ ] 5.2 Verify investigation list shows the completed investigation
  - [ ] 5.3 Verify list shows correct: service name, status (completed), severity
  - [ ] 5.4 Click the investigation to open detail view
  - [ ] 5.5 Verify detail page shows:
    - Header with investigation ID, service, status, timestamps
    - Step progress timeline with completed steps
    - Findings section (RCA hypothesis, confidence level)
    - Recommendations section (resolution steps)
  - [ ] 5.6 Take note of any rendering issues or missing data (but do NOT fix — that's Epic 3)
  - [ ] 5.7 **If UI returns 500 or fails to display:** Check Flask logs, note the error. This is informational — the UI may have issues from the 16 pre-existing test failures. Document but do not block.

- [ ] Task 6: Recover and verify stability (AC: #5)
  - [ ] 6.1 Recover from fault: `make demo-recover`
  - [ ] 6.2 Verify fault flags reset: `make demo-fault-status`
  - [ ] 6.3 Wait ~2 minutes for stabilization
  - [ ] 6.4 Verify no spurious investigations created after recovery
  - [ ] 6.5 Record final operator memory usage and restart count

- [ ] Task 7: Document results (AC: all)
  - [ ] 7.1 Document full walkthrough results in Dev Agent Record
  - [ ] 7.2 Record any UI rendering issues found (for Epic 3 context)
  - [ ] 7.3 Record fault injection → detection timing (for NFR validation)
  - [ ] 7.4 Run `cargo test --lib` to confirm no regressions
  - [ ] 7.5 Run `cd ui && python -m pytest tests/ -x -q 2>&1 | tail -20` to document UI test baseline
  - [ ] 7.6 **SURFACE TO ERIC:** Final walkthrough result (pass/fail), any issues found, UI readiness assessment for Epic 3

## Dev Notes

### What This Story Proves

This story validates the **complete user-facing demo experience** that has been the project's north star since Epic 1. Specifically:

1. **Deliberate fault injection works** — `make demo-fault` → flagd → OTel demo service behavior change → metric anomaly
2. **Detection is responsive** — EWMA picks up payment service degradation from injected fault (not just random organic anomalies)
3. **RCA is contextual** — LLM identifies the payment service issue specifically (not generic "something is wrong")
4. **UI displays results** — The investigation lifecycle is visible to users through the web interface

### Pipeline Architecture (full path being verified)

```
[User runs: make demo-fault FAULT=payment-failure]
    ↓
[flagd: enables paymentServiceFailure flag]
    ↓
[OTel Demo: payment service starts throwing errors]
    ↓
[OTel Collector: scrapes payment service metrics]
    ↓
[Prometheus: stores metrics]
    ↓
[Beeper Operator: EWMA detector reads from Prometheus via remote write]
    ↓
[EWMA: detects anomaly in payment service error rate]
    ↓
[Operator: creates Investigation CRD]
    ↓
[Operator: reconciles CRD → spawns investigator Job]
    ↓
[Investigator (Python): queries Prometheus for payment service signals]
    ↓
[Investigator: calls Anthropic LLM for RCA]
    ↓
[Investigator: generates recommendations, stores to Qdrant]
    ↓
[Investigation CRD: transitions to Completed]
    ↓
[UI: displays investigation in list + detail views]
```

### Key Commands

```bash
# Full one-command deploy (creates cluster, builds, deploys everything)
make demo-up

# Port-forward UIs to localhost
make demo-ui
# Beeper UI: http://localhost:5050
# OTel Shop: http://localhost:8080

# Fault injection
make demo-fault FAULT=payment-failure
make demo-fault-status
make demo-recover

# Monitor
kubectl get investigations -n beeper -w
kubectl get pods -n beeper
kubectl logs -n beeper deploy/beeper-operator -f | grep -E "(anomaly|Investigation|payment)"

# Status
make demo-status
```

### Timing Expectations

| Phase | Expected Duration |
|-------|------------------|
| `make demo-up` (first time) | 5-10 minutes |
| EWMA baseline warmup | ~10 minutes |
| Fault detection latency | < 10 minutes (NFR1) |
| Investigation pipeline | < 10 minutes (NFR3) |
| Recovery stabilization | ~2 minutes |
| **Total walkthrough** | **~30-45 minutes** |

### Environment Requirements

- Docker Desktop: 16GB+ RAM (32GB recommended for kind + OTel demo)
- `ANTHROPIC_API_KEY` exported (required for LLM steps)
- Internet access (Anthropic API + Helm chart downloads)
- Ports free: 5050 (Beeper UI), 8080 (OTel Shop), 16686 (Jaeger)
- macOS or Linux with Docker Desktop

### Known Limitations (NOT failures)

These are documented from Story 3-0b and should NOT be treated as test failures:
- **Loki not deployed** in OTel demo → log queries return empty
- **KB query skipped** without embedding model configured → no prior incident matching
- **Cost tracking shows $0** — litellm lacks pricing data for newer model IDs
- **RBAC Forbidden** for some K8s resources (events, HPAs, services) in investigator service account
- **16 pre-existing UI test failures** — may affect rendering in some views

### Key Difference from Story 3-0b

| Aspect | Story 3-0b | Story 3-0c |
|--------|-----------|-----------|
| Goal | Verify backend pipeline | Verify full demo experience |
| Fault type | Organic EWMA detections | Deliberate `make demo-fault` |
| UI involved | No | Yes — must view in browser |
| Pass criteria | 3/3 consecutive backend runs | 1 complete walkthrough including UI |
| Who cares | Developer confidence | Stakeholder demo-ability |

### Patterns from Previous Stories

**From Story 3-0b:**
- Operator stable at 60 MB memory with ~1,330 CRDs (no OOMKill risk)
- LLM prefix bug fixed (litellm routing works now)
- Model ID must be full identifier (e.g., `claude-3-5-haiku-20241022`)
- values-dev.yaml: Memory 2Gi, Loki disabled, model = haiku for cost

**From Story 3-0a:**
- SLO engine bounded: cooldown pruning, budget event cap, cache cleanup
- `run_slo_engine` loop prunes orphaned entries each cycle
- Investigation CRD accumulation is the real OOMKill risk (not SLO data)

**Team agreements:**
- Fix bugs when found, don't defer
- Surface blockers in prompt output immediately with clear language
- Document everything for institutional memory
- eric reads prompt output, not story files

### UI Architecture (for reference, NOT to modify)

- Framework: Flask + Jinja2 + HTMX + SSE
- Templates: `ui/beeper_ui/templates/`
- Investigation list: `templates/investigations/list.html`
- Investigation detail: `templates/investigations/detail.html`
- Investigation detail content: `templates/investigations/partials/_detail_content.html`
- Routes: `ui/beeper_ui/routes/investigations.py`
- Port: 5000 internal, 5050 via port-forward

### Project Structure Notes

- Alignment with unified project structure: demo targets in Makefile, ServiceLevel CRDs in `demo/k8s/`
- UI in `ui/` directory (Flask app)
- Operator in `operator/` (Rust)
- Investigator in `investigator/` (Python)
- Helm charts in `helm/beeper/`
- No conflicts or variances detected

### References

- [Source: epic-2-retro-2026-05-01.md#Epic 3 Preparation Tasks — "3-0c | Full demo walkthrough | Deploy → fault inject → investigate → RCA → UI display"]
- [Source: epic-2-retro-2026-05-01.md#Previous Retrospective Follow-Through — "Full demo walkthrough as Epic 2 exit criteria"]
- [Source: Makefile — demo-up, demo-fault, demo-recover, demo-ui, demo-status targets]
- [Source: demo/k8s/ — ServiceLevel CRDs (4) + source-prometheus.yaml]
- [Source: ui/beeper_ui/routes/investigations.py — Investigation route handlers]
- [Source: ui/beeper_ui/templates/investigations/ — List and detail templates]
- [Source: Story 3-0b Completion Notes — Fault injection path unverified, known limitations]
- [Source: helm/beeper/values-dev.yaml — Dev deployment configuration]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

**Walkthrough Result: FAIL** (2026-05-06)

Walkthrough attempted with Ollama (qwen3:8b) via `host.docker.internal:11434`. All 5 acceptance criteria failed.

**Critical Issues Found:**

1. **Investigation flood at startup (23+ before otel-demo started)**
   - EWMA detector triggers investigations during pod startup
   - `min_samples` default of 10 is too low — accumulates in ~2.5 minutes
   - Each otel-demo service triggers its own investigation (cooldown is per-service)
   - **Ticket:** 3-0e-fix-investigation-startup-flood

2. **UI "Investigation not found" on every detail click**
   - Root cause: `operator/src/api.rs:418` uses `Api::all()` for the detail endpoint
   - `Api::all().get()` fails on namespaced resources — kube-rs can't resolve namespace
   - `Api::all().list()` works (list view) but `get()` does not (detail view)
   - **Ticket:** 3-0f-fix-ui-investigation-detail-not-found

3. **Investigators stall — Ollama connection timeout**
   - `litellm.Timeout: Connection timed out after 600.0 seconds`
   - Ollama defaults to `127.0.0.1:11434` — not reachable from kind cluster
   - Requires `OLLAMA_HOST=0.0.0.0 ollama serve` — not documented
   - Also: `Failed to parse LLM response as JSON` — LiteLLM/Ollama integration issue
   - **Ticket:** 3-0g-fix-ollama-litellm-integration

4. **Investigator RBAC insufficient**
   - `Failed to list events in namespace beeper: Forbidden` for many K8s resource types
   - Investigator SA lacks permissions for events, HPAs, services, etc.
   - Investigators cannot gather K8s signals, reducing RCA quality
   - **Ticket:** 3-0h-fix-investigator-rbac-permissions

5. **UI cannot sort by time, no investigation numbering**
   - Noted for Epic 3 (UI) — not a blocker ticket

**Conclusion:** Demo walkthrough cannot succeed until issues 1-4 are resolved. Story 3-0c should be re-attempted after fix stories are completed.

### File List

No code files modified — walkthrough-only story.
