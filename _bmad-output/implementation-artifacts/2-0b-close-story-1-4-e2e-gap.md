# Story 2.0b: Close Story 1.4 E2E Gap

Status: done

> Preparation task from Epic 1 retrospective — must complete before Epic 2 stories.
> Priority: HIGH | Owner: Amelia (Dev)
> Source: [epic-1-retro-2026-04-18.md](epic-1-retro-2026-04-18.md#technical-debt-resolution)

## Story

As a **developer**,
I want to verify the detection stats API returns all 5 detection fields on a live cluster,
So that Story 1.4's acceptance criteria are fully E2E verified (blocked by OOMKill during Epic 1).

## Background

Story 1.4 added 5 detection metric fields to the `/api/v1/ingestion/stats` endpoint. All 564 unit/integration tests pass, including HTTP round-trip serialization tests. However, the final E2E step — curling the live endpoint on the kind cluster — was HALTED because the operator pod OOMKilled repeatedly (pre-existing 16h+ issue, Exit Code 137). Story 2.0a resolved this by allocating 32GB to Docker Desktop and increasing resource limits.

## Acceptance Criteria

1. **Given** the operator is running on the kind cluster with detection enabled
   **When** `curl http://localhost:<port>/api/v1/ingestion/stats` is called
   **Then** the response includes all 5 detection fields: `anomalies_detected`, `anomalies_suppressed`, `active_metric_detectors`, `ewma_warmup_samples`, `ewma_warmup_minimum`
   **And** the response is valid JSON with correct field types (all u64 integers)

2. **Given** the OTel demo load generator is running and sending metrics
   **When** the detection stats are checked after sufficient warmup time
   **Then** `active_metric_detectors` > 0 (metrics are being tracked)
   **And** `anomalies_detected` >= 0 (detection is running)
   **And** `ewma_warmup_minimum` > 0 (warmup threshold is configured)

## Tasks / Subtasks

- [x] Task 1: Port-forward to operator API (AC: #1)
  - [x] 1.1 Operator Running: `beeper-operator-6c87b4b969-b5dks`, 19h uptime, 0 restarts.
  - [x] 1.2 Stats endpoint is on main API router (port 8080), NOT ingestion port (9090). Port-forward: `kubectl port-forward -n beeper svc/beeper-operator 18080:8080` (port 8080 in use by OTel frontend proxy).
  - [x] 1.3 No Makefile target for operator API port-forward; manual port-forward used.

- [x] Task 2: Curl detection stats endpoint and verify fields (AC: #1, #2)
  - [x] 2.1 `curl -s http://localhost:18080/api/v1/ingestion/stats | jq .` — successful, valid JSON response.
  - [x] 2.2 All 5 detection fields present: anomalies_detected=26911, anomalies_suppressed=2574733, active_metric_detectors=10000, ewma_warmup_samples=1, ewma_warmup_minimum=10.
  - [x] 2.3 All field values are integers (u64). No null or string values.
  - [x] 2.4 `active_metric_detectors` = 10000 > 0. PASS.
  - [x] 2.5 `ewma_warmup_minimum` = 10 > 0. PASS.
  - [x] 2.6 Full response documented in Dev Agent Record below.

- [x] Task 3: Document results (AC: all)
  - [x] 3.1 Story 1.4 E2E gap is CLOSED. All 5 detection fields verified on live cluster.
  - [x] 3.2 Complete API response shape documented below with all field values.

## Dev Notes

### API Endpoint Details

- **Path:** `/api/v1/ingestion/stats`
- **Method:** GET
- **Handler:** `ingestion_stats()` in `operator/src/api.rs:1067-1127`
- **Route registration:** `operator/src/api.rs:129`

### Expected Response Shape

```json
{
  "buffer_size": 10000,
  "buffered_count": 0,
  "dropped_count": 0,
  "is_full": false,
  "metrics_received": 116000000,
  "logs_received": 0,
  "sources": {
    "prometheus": { ... },
    "loki": { ... },
    "otlp": { ... }
  },
  "anomalies_detected": 424,
  "anomalies_suppressed": 0,
  "active_metric_detectors": 23,
  "ewma_warmup_samples": 10,
  "ewma_warmup_minimum": 10
}
```

### 5 Detection Fields (Story 1.4 additions)

| API Field | Source (DetectionStats) | Description |
|-----------|----------------------|-------------|
| `anomalies_detected` | `anomalies_detected` | Total anomalies detected |
| `anomalies_suppressed` | `anomalies_suppressed` | Anomalies suppressed by cooldown |
| `active_metric_detectors` | `metrics_tracked` | Number of active EWMA detectors |
| `ewma_warmup_samples` | `ewma_warmup_samples` | Min sample count across detectors |
| `ewma_warmup_minimum` | `ewma_warmup_minimum` | Configured min_samples threshold |

### Operator Service Ports

- **Main API (stats, health, investigations):** port 8080 via `beeper-operator` svc. Port-forward: `kubectl port-forward -n beeper svc/beeper-operator 18080:8080` (8080 often in use by OTel frontend proxy).
- **Ingestion (metric/log writes):** port 9090 via `beeper-operator-ingestion` svc. In-cluster DNS: `beeper-operator-ingestion.beeper.svc:9090`.

### Previous Intelligence

- **Story 2.0a:** Cluster verified stable — 32GB Docker Desktop, all pods Running, no OOMKills
- **Story 1.4 HALT:** Tasks 5.6-5.7 halted due to OOMKill (Exit Code 137). Code complete, 564 tests pass.
- **Story 2.1 E2E:** Operator successfully processing 15K+ investigations — detection pipeline is active

### References

- [Source: epic-1-retro-2026-04-18.md#Technical Debt Resolution] — Story 1.4 E2E gap: HIGH priority
- [Source: 1-4-extend-ingestion-stats-api-with-detection-metrics.md#Task 5.6-5.7] — HALTED tasks
- [Source: operator/src/api.rs:1049-1127] — IngestionStatsResponse struct and handler
- [Source: operator/src/detection/mod.rs:85-98] — DetectionStats source struct

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- `kubectl get pods -n beeper | grep operator` → beeper-operator-6c87b4b969-b5dks Running 19h 0 restarts
- `kubectl port-forward -n beeper svc/beeper-operator 18080:8080` → port 8080 in use, used 18080
- `curl -s http://localhost:18080/api/v1/ingestion/stats` → full JSON response below

### Full API Response (E2E Verified)

```json
{
  "buffer_size": 10000,
  "buffered_count": 1786317271,
  "dropped_count": 3145352802,
  "is_full": false,
  "metrics_received": 1785842895,
  "logs_received": 474376,
  "sources": {
    "loki": { "bytes_received": 0, "parse_errors": 0, "last_received_ns": 0 },
    "prometheus": { "bytes_received": 195285651304, "parse_errors": 0, "last_received_ns": 1776637161511173251 },
    "otlp": { "bytes_received": 644919786, "parse_errors": 0, "last_received_ns": 1776637161659314834 }
  },
  "anomalies_detected": 26911,
  "anomalies_suppressed": 2574733,
  "active_metric_detectors": 10000,
  "ewma_warmup_samples": 1,
  "ewma_warmup_minimum": 10
}
```

### Completion Notes List

- AC #1 PASS: All 5 detection fields present in JSON response with correct integer types
- AC #2 PASS: active_metric_detectors=10000 > 0, anomalies_detected=26911 > 0, ewma_warmup_minimum=10 > 0
- DISCOVERY: Stats endpoint is on main API router (port 8080 via `beeper-operator` svc), NOT ingestion port (9090). Story Dev Notes corrected.
- Story 1.4 E2E gap is CLOSED. The OOMKill blocker was resolved by Story 2.0a (32GB allocation + resource limit increases).
- Additional observations: 1.78B metrics received, 474K logs received, 195GB prometheus bytes, 26.9K anomalies detected, 2.57M anomalies suppressed by cooldown — detection pipeline is highly active.
- REVIEW OBSERVATION [M2]: ewma_warmup_samples=1 after 19h — minimum across 10K detectors never exceeds 1, likely because new detectors keep being created with fresh warmup. Investigate in Epic 2 detection tuning.
- REVIEW OBSERVATION [M3]: dropped_count (3.1B) exceeds metrics_received (1.78B) — buffer capacity 10K is undersized for demo volume. Detection processes <40% of incoming data. Consider tuning buffer_size or detection throughput in Epic 2.

### Change Log

- 2026-04-19: Verified detection stats API on live cluster — all 5 fields present with real data. No code changes (verification-only task).

### File List

No files modified — verification-only task.
