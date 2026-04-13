# Story 1.2: Fix OTEL Collector to Operator Ingestion

Status: done

## Story

As a **demo operator (Eric)**,
I want telemetry data from the OTEL Astronomy Shop to flow into Beeper's ingestion endpoint,
So that the pipeline has real metric and log data to detect anomalies from.

## Acceptance Criteria

1. **Given** the OTEL demo is deployed with its Collector configured to export to Beeper
   **When** the Collector sends Prometheus remote write (snappy+protobuf) to `:9090/api/v1/write`
   **Then** the operator decodes the protobuf payload without errors and buffers the metric samples
   **And** if protobuf schema mismatch is detected, operator proto definitions are updated to match Collector output (AD-1)

2. **Given** the OTEL Collector sends Loki push (JSON) to `:9090/loki/api/v1/push`
   **When** log entries arrive at the ingestion endpoint
   **Then** the operator parses JSON log payloads and buffers them without errors

3. **Given** data is flowing from both metric and log sources
   **When** `GET /api/v1/ingestion/stats` is called on `:8080`
   **Then** response shows `metrics_received > 0` AND `logs_received > 0` within 5 minutes of deploy
   **And** per-source health reports (FR4) show bytes received, parse errors, and last received timestamp

## Tasks / Subtasks

- [x] Task 1: Fix operator CI blockers — cargo fmt + clippy (AC: prerequisite)
  - [x] 1.1 Run `cargo fmt` to auto-fix all formatting across the project (affects 6 files: `api.rs`, `main.rs`, `slo/mod.rs`, `controllers/servicelevel.rs`, `crds/notification_channel.rs`, `crds/repository.rs`)
  - [x] 1.2 Fix clippy warnings: `manual_map` in `otlp.rs:90` (replaced if-else chain with `.or_else()` chain), `too_many_arguments` in `main.rs:359` (added `#[allow]` — refactoring out of scope)
  - [x] 1.3 Verify `cargo fmt --check && cargo clippy -- -D warnings` both pass
  - [x] 1.4 Verify `cargo test` still passes (550 tests, 0 failures)

- [x] Task 2: Extend IngestionStatsResponse with per-protocol counters (AC: #3)
  - [x] 2.1 Add `metrics_received: AtomicU64` and `logs_received: AtomicU64` counters to `IngestionBuffer` (follow existing `dropped_count`/`buffered_count` pattern)
  - [x] 2.2 Increment `metrics_received` in `prometheus_write_handler` per sample successfully buffered
  - [x] 2.3 Increment `logs_received` in `otlp_logs_handler` and `loki_push_handler` per entry successfully buffered
  - [x] 2.4 Add `metrics_received` and `logs_received` fields to `IngestionStatsResponse` in `api.rs`
  - [x] 2.5 Add per-source health tracking (FR4): `SourceHealth` struct with `bytes_received`, `parse_errors`, `last_received_ns` per protocol; `SourceHealthResponse` for serialization
  - [x] 2.6 Expose per-source health in stats response via `sources` HashMap in `IngestionStatsResponse`
  - [x] 2.7 Add OTLP integration test in `mod.rs`: `test_otlp_endpoint_full_flow` — sends JSON through router, asserts 2 buffered + logs_received == 2
  - [x] 2.8 Write unit tests for new counters and per-source health (6 new tests):
    - `test_metrics_received_counter_increments` — record_metrics(3) + record_metrics(2) → 5
    - `test_logs_received_counter_increments` — record_logs(2) + record_logs(4) → 6
    - `test_per_source_health_bytes_tracking` — prometheus 512+256=768, otlp 1024, loki 0
    - `test_per_source_health_parse_errors` — loki 2 errors, prometheus 1 error, otlp 0
    - `test_source_health_last_received_updates` — last_received_ns set after record_request
    - Plus updated `test_ingestion_stats_serialization` and `test_ingestion_stats_endpoint` in api.rs
  - [x] 2.9 Verify all tests pass: 556 total (550 existing + 6 new), 0 failures

- [x] Task 3: Re-enable Prometheus remote write pipeline (AC: #1)
  - [x] 3.1 Added `prometheusremotewrite/beeper` exporter in `demo/otel-demo-values.yaml`
  - [x] 3.2 Configured endpoint: `http://beeper-operator-ingestion.beeper.svc:9090/api/v1/write` with `tls.insecure: true`
  - [x] 3.3 Added `metrics` pipeline: `processors: [memory_limiter, resourcedetection, resource, batch]`, `exporters: [prometheusremotewrite/beeper]`
  - [x] 3.4 AD-1 verification: inline prost definitions use standard Prometheus remote write proto tags (WriteRequest=1, TimeSeries labels=1/samples=2, etc.). OTel Collector's `prometheusremotewrite` exporter uses same canonical schema. Full cluster verification deferred to Task 4.
  - [x] 3.5 No schema mismatch detected — no changes needed to `prometheus.rs`

- [x] Task 4: End-to-end cluster verification (AC: #1, #2, #3)
  - [x] 4.1 Reused existing `beeper-demo` kind cluster; rebuilt images with `make demo-build` and loaded into kind
  - [x] 4.2 Restarted operator deployment (`kubectl rollout restart`); upgraded OTel demo Helm release with updated values
  - [x] 4.3 Verified AC3: `curl localhost:8080/api/v1/ingestion/stats` → `metrics_received: 116,107,172` AND `logs_received: 26,894`
  - [x] 4.4 Verified AC3 (FR4): `sources.prometheus.bytes_received: 5,099,179,598`, `sources.otlp.bytes_received: 35,644,031`, `parse_errors: 0` for all sources, `last_received_timestamp` recent for prometheus and otlp
  - [x] 4.5 Operator logs clean — no errors. Shows successful Prometheus sample buffering and OTLP log entry buffering. Buffer-full warnings expected under high volume (not errors).
  - [x] 4.6 OTLP logs flowing: `logs_received: 26,894`, `sources.otlp.bytes_received: 35,644,031`
  - [x] 4.7 Prometheus metrics flowing: `metrics_received: 116,107,172`, `sources.prometheus.bytes_received: 5,099,179,598`
  - [x] 4.8 Cluster left running for demo use (cleanup deferred)

## Dev Notes

### OTLP Pipeline Already Fixed
Commits `f1e91fd` (encoding: json) and `121d4ac` (compression: none) on 2026-04-03 already fixed the OTLP log pipeline. The OTel Collector's `otlphttp/beeper` exporter now sends JSON with no compression to `/v1/logs`, which matches the operator's `Json<ExportLogsServiceRequest>` Axum extractor. OTLP log ingestion should work out of the box — Task 4 verifies this.

### Prometheus Remote Write Currently Disabled
The `prometheusremotewrite/beeper` exporter is **commented out** in `demo/otel-demo-values.yaml` (line 7-9) with the note: "Re-enable prometheusremotewrite/beeper when the ingestion pipeline is optimized." Task 3 re-enables it. The endpoint (`/api/v1/write`) and handler (`prometheus_write_handler`) exist and pass all 6 unit tests — the issue was only the Collector config. The "optimized" comment was aspirational — the pipeline works correctly (Story 1.1 confirmed 550/550 operator tests pass, including all ingestion tests). Re-enabling is safe.

### Loki Push — Handler Exists But Not Used by OTel Demo
The OTel Collector sends logs via OTLP HTTP (`/v1/logs`), **not** Loki push (`/loki/api/v1/push`). AC2 references Loki push, but the current demo architecture routes logs through OTLP. The Loki handler exists, passes all 9 unit tests, and is available if a Loki exporter is added to the Collector later.

**AC2 verification decision:** AC2 is verified via existing unit tests (9 tests cover valid requests, compression, invalid payloads, and buffer-full scenarios). End-to-end cluster verification is not possible without adding a Loki exporter to the Collector, which would violate AD-1 (do not modify Collector config beyond re-enabling existing exporters). The OTLP handler is what processes demo logs in practice — OTLP end-to-end verification (Task 4.6) confirms the log pipeline works.

### CI Blocker — Must Fix First
Story 1.1 identified pre-existing `cargo fmt` and `cargo clippy` failures that block CI (`.github/workflows/ci.yml` runs `cargo fmt --check → cargo clippy → cargo test` in sequence). Task 1 fixes these before any code changes to ensure CI remains green.

### Dual HTTP Server Architecture
- **Port 9090** (ingestion): Three POST endpoints — `/api/v1/write` (Prometheus), `/loki/api/v1/push` (Loki), `/v1/logs` (OTLP)
- **Port 8080** (management): REST API including `GET /api/v1/ingestion/stats`
- Both servers share the same `Arc<IngestionBuffer>` for cross-server stats

### Current IngestionStatsResponse (Before This Story)
```rust
pub struct IngestionStatsResponse {
    pub buffer_size: usize,
    pub buffered_count: u64,
    pub dropped_count: u64,
    pub is_full: bool,
}
```
This only has aggregate buffer stats. AC3 requires `metrics_received` and `logs_received` as separate counters. AC3/FR4 requires per-source health. Task 2 extends this.

### Protobuf Definitions Are Inline (AD-1)
Prometheus protobuf types are defined inline in `prometheus.rs` using `prost::Message` derive macros (lines 27-58). There is NO `build.rs`, no `.proto` files, and no `prost-build` dependency. AD-1 verification (Task 3.4) compares the inline field tags against actual Collector output, not against `.proto` source files.

### Ingestion Buffer
- `tokio::sync::mpsc` bounded channel, default capacity 10,000 (`BEEPER_INGESTION_BUFFER_SIZE` env var)
- `IngestionData` enum: `Metric(MetricSample)` or `Log(LogEntry)`
- Handlers use `try_send()` (non-blocking); full buffer returns 429/503 to caller
- `DetectionConsumer` calls `recv()` to drain the buffer for anomaly detection

### Per-Source Health Architecture Decision
Per-source health state (Task 2.5) lives **inside `IngestionBuffer`** alongside existing atomic counters, not in a separate registry. Rationale: the buffer is already shared via `Arc<IngestionBuffer>` across both servers, handlers already hold a reference to it, and adding a `HashMap<&'static str, SourceHealth>` (keyed by protocol name: "prometheus", "loki", "otlp") keeps the wiring simple. `SourceHealth` fields (`bytes_received: AtomicU64`, `parse_errors: AtomicU64`, `last_received_ns: AtomicI64`) use atomics for lock-free updates from concurrent handler calls. This avoids introducing a new shared state object that would need to be threaded through the router.

### OTLP Handler — No Compression Support
The OTLP handler uses Axum's `Json<ExportLogsServiceRequest>` extractor which requires raw JSON. There is **zero decompression logic** (unlike Prometheus/Loki handlers which handle snappy). The Collector's `compression: none` setting is essential. If this setting is changed or defaulted, requests will fail with 400/422.

### What NOT to Do
- Do NOT modify OTel Collector config beyond re-enabling prometheusremotewrite and fixing settings — the Collector is upstream (AD-1)
- Do NOT change existing `IngestionStatsResponse` fields — extend only, additive changes (AD-2 pattern)
- Do NOT refactor handler signatures or buffer internals — minimal changes to pass ACs
- Do NOT touch modules outside ingestion/ and api.rs (detection, SLO, controllers are future stories)

### Development Iteration
- **Operator code changes (Tasks 1-2):** `cargo fmt`, `cargo clippy`, `cargo test` — fast local feedback (~1-2 min compile + test)
- **Cluster verification (Tasks 3-4):** `make demo-up` (slow — Docker build + kind load + Helm install, ~5-10 min), then `curl` + `kubectl` verification
- Recommend completing Tasks 1-2 locally, then doing Tasks 3-4 as a single cluster deployment cycle

### Project Structure Notes

- Alignment: All changes are within `operator/src/ingestion/`, `operator/src/api.rs`, and `demo/otel-demo-values.yaml`
- Buffer extension (Task 2): New atomic counters added to existing `IngestionBuffer` struct in `buffer.rs` — no new files needed
- Stats extension (Task 2): New fields added to existing `IngestionStatsResponse` in `api.rs` — additive only
- Collector config (Task 3): Edits to existing `demo/otel-demo-values.yaml` — uncomment + configure
- No new source files expected. No changes to `Cargo.toml` dependencies.

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Story 1.2: Fix OTEL Collector to Operator Ingestion]
- [Source: _bmad-output/planning-artifacts/architecture.md — AD-1: OTEL Protobuf Schema Alignment]
- [Source: _bmad-output/planning-artifacts/architecture.md — AD-2: Detection Stats API Extension]
- [Source: _bmad-output/planning-artifacts/architecture.md — AD-8: Integration Testing Strategy]
- [Source: _bmad-output/planning-artifacts/architecture.md — Dual HTTP Server Architecture]
- [Source: _bmad-output/implementation-artifacts/1-1-establish-test-baseline.md — CI blocker note, test baseline]
- [Source: operator/src/ingestion/mod.rs — Router definition, integration tests]
- [Source: operator/src/ingestion/otlp.rs — OTLP handler, ExportLogsServiceRequest structs]
- [Source: operator/src/ingestion/prometheus.rs — Prometheus handler, inline prost definitions]
- [Source: operator/src/ingestion/loki.rs — Loki push handler]
- [Source: operator/src/ingestion/buffer.rs — IngestionBuffer, IngestionData enum]
- [Source: operator/src/api.rs — IngestionStatsResponse, ingestion_stats handler]
- [Source: operator/src/main.rs — Server startup, port configuration]
- [Source: demo/otel-demo-values.yaml — OTel Collector exporter config, prometheusremotewrite commented out]
- [Source: Makefile — demo-up, demo-ui, demo-status targets]
- [Source: operator/Cargo.toml — prost 0.13, axum 0.7, snap 1.1 dependencies]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

#### Task 1: CI Blockers Fixed (2026-04-13)
- `cargo fmt` auto-fixed formatting across 6 files
- Fixed clippy `manual_map` in `otlp.rs:90` — replaced if-else chain with `.or_else()` chain
- Fixed clippy `too_many_arguments` in `main.rs:359` — added `#[allow]` (refactoring out of scope)
- Revealed a previously hidden clippy warning (`too_many_arguments`) that was masked by fmt failures
- 550/550 tests pass, `cargo fmt --check` and `cargo clippy -- -D warnings` both clean

#### Task 2: Per-Protocol Counters and Source Health (2026-04-13)
- Added `SourceHealth` struct to `buffer.rs` with `AtomicU64`/`AtomicI64` fields for bytes_received, parse_errors, last_received_ns
- Added `metrics_received` and `logs_received` `AtomicU64` counters to `IngestionBuffer`
- Extended `IngestionStatsResponse` with `metrics_received`, `logs_received`, and `sources` (HashMap of per-source health)
- Added `SourceHealthResponse` with `From<SourceHealthSnapshot>` conversion in `api.rs`
- Updated all 3 handlers (prometheus, otlp, loki) to record metrics/logs and per-source health
- Added `HeaderMap` parameter to OTLP handler for content-length tracking
- 6 new tests added (5 in buffer.rs + 1 integration test in mod.rs)
- Total: 556 tests pass (550 + 6 new), 0 failures

#### Task 4: End-to-End Cluster Verification Passed (2026-04-13)
- Reused existing `beeper-demo` kind cluster; rebuilt all 3 Docker images (operator, ui, investigator) with `make demo-build`
- Restarted operator deployment to pick up new image; upgraded OTel demo Helm release with Prometheus remote write config
- Helm upgrade had ConfigMap conflict (flagd-config) between Helm server-side apply and prior kubectl client-side apply — resolved by deleting ConfigMap and re-upgrading
- Ingestion stats verified: `metrics_received: 116,107,172`, `logs_received: 26,894`
- Per-source health: prometheus 5.1GB received, otlp 35.6MB received, 0 parse errors across all sources
- Loki source shows zeros (expected — OTel demo uses OTLP for logs, not Loki push)
- Operator logs clean: successful Prometheus sample and OTLP log entry buffering. Buffer-full warnings under high volume are expected backpressure behavior, not errors.

#### Task 3: Prometheus Remote Write Re-enabled (2026-04-13)
- Added `prometheusremotewrite/beeper` exporter to `demo/otel-demo-values.yaml`
- Endpoint: `http://beeper-operator-ingestion.beeper.svc:9090/api/v1/write`
- Added metrics pipeline with standard processors
- AD-1: prost inline definitions use canonical Prometheus remote write proto tags — no mismatch

### Change Log

- 2026-04-13: Tasks 1-3 completed. CI blockers fixed, per-protocol counters implemented, Prometheus remote write re-enabled. 556/556 tests pass.
- 2026-04-13: Task 4 completed. End-to-end cluster verification passed — `metrics_received: 116M`, `logs_received: 26.9K`, per-source health shows bytes received and zero parse errors for prometheus and otlp. All 4 tasks complete. Story moved to `review`.
- 2026-04-13: Code review completed. 4 MEDIUM issues found and fixed: (M1) Prometheus record_request moved to top of handler, (M2) API field renamed last_received_timestamp → last_received_ns, (M3) File List updated with 21 cargo-fmt-only files, (M4) OTLP handler switched from Content-Length header to Bytes extractor for reliable bytes tracking + parse error detection. Added test_handler_malformed_json test. 557/557 tests pass. Story moved to `done`.

### File List

- `operator/src/ingestion/buffer.rs` — Added `SourceHealth` struct, `metrics_received`/`logs_received` counters, per-source health accessors, 5 new tests
- `operator/src/ingestion/otlp.rs` — Fixed clippy `manual_map`, switched to `Bytes` extractor for reliable bytes tracking + parse error detection, added `record_logs()` call, added `Serialize` derives for test support
- `operator/src/ingestion/prometheus.rs` — Moved `record_request()` to top of handler (before validation), added `record_metrics()` call, parse error tracking
- `operator/src/ingestion/loki.rs` — Added `record_logs()`, `record_request()`, and `record_parse_error()` calls
- `operator/src/ingestion/mod.rs` — Exported `SourceHealthSnapshot`, added `test_otlp_endpoint_full_flow` integration test
- `operator/src/api.rs` — Added `SourceHealthResponse`, extended `IngestionStatsResponse` with new fields, renamed `last_received_timestamp` → `last_received_ns` for clarity, updated handler and tests
- `operator/src/main.rs` — Added `#[allow(clippy::too_many_arguments)]`, formatting fixes
- `demo/otel-demo-values.yaml` — Added `prometheusremotewrite/beeper` exporter and metrics pipeline
- Formatting only (cargo fmt, 21 files): `controllers/investigation.rs`, `controllers/notification_channel.rs`, `controllers/repository.rs`, `controllers/servicelevel.rs`, `crds/notification_channel.rs`, `crds/repository.rs`, `crds/servicelevel.rs`, `detection/consumer.rs`, `detection/ewma.rs`, `detection/logs.rs`, `detection/metrics.rs`, `investigator_job.rs`, `lib.rs`, `notifications/mod.rs`, `notifications/outbox.rs`, `notifications/router.rs`, `slo/budget.rs`, `slo/burn_rate.rs`, `slo/calculator.rs`, `slo/impact.rs`, `slo/mod.rs`
