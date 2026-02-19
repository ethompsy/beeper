# Story 3.1: Anomaly Detection Engine

Status: ready-for-dev

## Story

As **Beeper**,
I want to continuously monitor incoming log and metric streams for anomalous patterns,
So that suspicious conditions are identified for investigation.

## Acceptance Criteria

### AC1: Continuous Anomaly Detection
**Given** data sources are configured and streaming
**When** the operator processes incoming data
**Then** anomaly detection runs continuously (FR1)
**And** detection latency is in seconds from occurrence (NFR-P1)

### AC2: Metric Anomaly Detection
**Given** metrics show unusual patterns (spike, drop, deviation)
**When** the anomaly detector evaluates
**Then** a suspicious condition is flagged
**And** the condition includes: source, metric/log pattern, timestamp, severity estimate

### AC3: Log Anomaly Detection
**Given** logs contain error patterns or unusual frequencies
**When** the anomaly detector evaluates
**Then** log-based anomalies are detected
**And** relevant log lines are captured as context

### AC4: No False Positives
**Given** normal operational patterns
**When** the detector evaluates
**Then** no false positives are generated for expected behavior
**And** baseline learning adapts to environment patterns

## Tasks / Subtasks

- [ ] Task 1: Create detection module with core types and EWMA detector (AC: #1, #2, #4)
  - [ ] 1.1: Create `operator/src/detection/mod.rs` — public module exports and `DetectionConfig` struct with env var loading
  - [ ] 1.2: Create `operator/src/detection/types.rs` — `AnomalyEvent` struct (source, condition, service, severity, timestamp, context fields), `AnomalyType` enum (MetricSpike, MetricDrop, ErrorRateSpike)
  - [ ] 1.3: Create `operator/src/detection/ewma.rs` — `EwmaDetector` struct with `update(value: f64) -> Option<AnomalySignal>` method
  - [ ] 1.4: EWMA implements exponentially weighted mean + variance tracking (inline math, NO external crates — standard library `f64::sqrt()` only)
  - [ ] 1.5: Configurable `alpha` (smoothing factor, default 0.2), `threshold` (stddev multiplier, default 3.0), `min_samples` (warmup count, default 10)
  - [ ] 1.6: Add `pub mod detection;` to `lib.rs`

- [ ] Task 2: Implement metric anomaly detection (AC: #2, #4)
  - [ ] 2.1: Create `operator/src/detection/metrics.rs` — `MetricDetector` struct
  - [ ] 2.2: Maintain per-metric `EwmaDetector` state in bounded `HashMap<MetricKey, (EwmaDetector, Instant)>`
  - [ ] 2.3: `MetricKey` = metric name + sorted subset of discriminating labels (`service`, `instance`, `job`)
  - [ ] 2.4: `process(&mut self, sample: &MetricSample) -> Option<AnomalyEvent>` — update EWMA, return event if anomaly
  - [ ] 2.5: Include in AnomalyEvent: metric name, labels, observed value, expected value (EWMA mean), deviation (in stddevs)
  - [ ] 2.6: Evict least-recently-updated entries when map exceeds `max_tracked_metrics` (default 10000)

- [ ] Task 3: Implement log anomaly detection (AC: #3, #4)
  - [ ] 3.1: Create `operator/src/detection/logs.rs` — `LogDetector` struct
  - [ ] 3.2: Track error-level log count per service using sliding time window (`VecDeque` of timestamp+count buckets, 1-minute granularity)
  - [ ] 3.3: Apply `EwmaDetector` to per-service error rates (errors per window)
  - [ ] 3.4: Extract service name from log labels — check `service` → `app` → `job` → `namespace` in order, fall back to `"unknown"`
  - [ ] 3.5: Detect error-level logs by checking `level` label — match (case-insensitive): `error`, `err`, `fatal`, `critical`, `panic`
  - [ ] 3.6: Capture last N error log lines (default 5) per service as context in `AnomalyEvent` via bounded `VecDeque<String>`
  - [ ] 3.7: Bound tracked services (configurable `max_tracked_services`, default 1000)

- [ ] Task 4: Implement detection consumer and Investigation bridge (AC: #1, #2, #3)
  - [ ] 4.1: Create `operator/src/detection/consumer.rs` — `DetectionConsumer` struct
  - [ ] 4.2: `pub async fn run(self, buffer: Arc<IngestionBuffer>, client: Client, namespace: String)` — main detection loop
  - [ ] 4.3: Read from buffer via `buffer.recv().await`, route `IngestionData::Metric` to `MetricDetector` and `IngestionData::Log` to `LogDetector`
  - [ ] 4.4: On anomaly detected: create Investigation CRD via `kube::Api<Investigation>::create()`
  - [ ] 4.5: Build `InvestigationSpec` from `AnomalyEvent` — condition (descriptive string), service, severity, triggered_at
  - [ ] 4.6: Map severity from deviation magnitude: Low (2-3σ), Medium (3-4σ), High (4-6σ), Critical (>6σ)
  - [ ] 4.7: Implement cooldown tracking — `HashMap<String, Instant>` keyed by anomaly fingerprint, skip if within `cooldown_secs` (default 600s)
  - [ ] 4.8: Structured JSON logging via `tracing` for all anomaly events and investigation creations

- [ ] Task 5: Wire detection into operator and add API (AC: #1)
  - [ ] 5.1: Add `DetectionConfig` loading from environment variables in `main.rs`
  - [ ] 5.2: Spawn `DetectionConsumer::run()` as 5th background task via `tokio::spawn`
  - [ ] 5.3: Pass `Arc<IngestionBuffer>` (shared with ingestion server) and `Client::clone()`
  - [ ] 5.4: Add `GET /api/v1/detection/stats` endpoint to API router — returns metrics_tracked, services_tracked, anomalies_detected, cooldown_entries
  - [ ] 5.5: Share detection stats via `Arc<DetectionStats>` (atomic counters) added to `ApiState`

- [ ] Task 6: Add tests (AC: all)
  - [ ] 6.1: Unit test `EwmaDetector`: spike (large positive deviation) → anomaly signal returned
  - [ ] 6.2: Unit test `EwmaDetector`: drop (large negative deviation) → anomaly signal returned
  - [ ] 6.3: Unit test `EwmaDetector`: steady state values → no false positives (returns None)
  - [ ] 6.4: Unit test `EwmaDetector`: warmup period (< min_samples) → no premature firing
  - [ ] 6.5: Unit test `EwmaDetector`: baseline adapts after sustained shift → stops firing
  - [ ] 6.6: Unit test `MetricDetector`: processes multiple metrics independently
  - [ ] 6.7: Unit test `MetricDetector`: bounded HashMap eviction works at capacity
  - [ ] 6.8: Unit test `MetricDetector`: anomaly event contains correct fields (metric, labels, value, expected, deviation)
  - [ ] 6.9: Unit test `LogDetector`: error rate spike detected after warmup
  - [ ] 6.10: Unit test `LogDetector`: service extraction from labels (service → app → job fallback)
  - [ ] 6.11: Unit test `LogDetector`: context capture includes error log lines
  - [ ] 6.12: Unit test: severity mapping from deviation magnitude (Low/Medium/High/Critical boundaries)
  - [ ] 6.13: Unit test: cooldown prevents duplicate anomaly events within window
  - [ ] 6.14: Integration test: metric samples through buffer → anomaly event produced
  - [ ] 6.15: Integration test: log entries through buffer → anomaly event produced
  - [ ] 6.16: Integration test: steady-state data through buffer → no anomalies

## Dev Notes

### Architecture Compliance

**Source:** [architecture.md - Investigation Engine Architecture]

> Prometheus/Loki → Operator (detect) → K8s Job (investigate) → Qdrant (store) → UI (display)

This story implements the **Operator (detect)** stage. The detection module lives entirely within the Rust operator. It reads from the existing `IngestionBuffer` (Story 1-6) and creates `Investigation` CRDs when anomalies are detected, which the existing Investigation Controller (Story 1-9) then reconciles into K8s Jobs.

**Source:** [architecture.md - Operator Component]

> Language: Rust + kube-rs (memory-safe, async, production-ready)

All code MUST be Rust. No Python, no JavaScript, no FFI.

### Critical Design Decision: EWMA (Not ML)

**Use Exponentially Weighted Moving Average (EWMA) for anomaly detection — DO NOT add ML frameworks, Python bridges, or heavyweight crate dependencies.**

EWMA provides adaptive baseline learning that fulfills AC4 ("baseline learning adapts to environment patterns") with ~32 bytes of state per tracked metric. The math uses only standard library `f64` operations.

**EWMA Algorithm:**
```rust
// Core update — 6 lines of math, zero dependencies:
let diff = value - self.ewma;
self.ewma += self.alpha * diff;
self.ewma_var = (1.0 - self.alpha) * (self.ewma_var + self.alpha * diff * diff);
let stddev = self.ewma_var.sqrt();

// Anomaly check:
if self.samples >= self.min_samples && stddev > 0.0 && diff.abs() > self.threshold * stddev {
    // Anomaly detected — return signal with deviation info
}
```

**Parameters:**
- `alpha` (0.0-1.0): Smoothing factor controlling adaptation speed. 0.2 is a good default — balances sensitivity vs stability. Higher values (0.5+) for bursty metrics.
- `threshold` (stddev multiplier): 3.0 maps to the three-sigma rule (~99.7% of normal data within bounds). Increasing reduces false positives but delays detection.
- `min_samples`: Warmup count before detection activates. Prevents false positives on startup and after eviction.

**Why EWMA over alternatives:**
| Alternative | Why NOT |
|------------|---------|
| Z-score (global mean/stddev) | Doesn't adapt to trends or drift — gradual shifts cause persistent false positives |
| ML / Isolation Forest | Overkill for SRE monitoring, requires Python or ONNX runtime |
| Static thresholds | That's just Prometheus alerting rules — not adaptive |
| External statistics crates | The math is trivial (~30 lines), adds unnecessary dependency |
| Seasonal decomposition (STL) | Batch-oriented, requires full historical period, GPL-licensed crate |

### Data Flow Architecture

```
┌─────────────────────────────────────────┐
│ Ingestion Server (port 9090, Story 1-6) │
│ ├─ POST /api/v1/write (Prometheus)      │
│ └─ POST /loki/api/v1/push (Loki)       │
└──────────────┬──────────────────────────┘
               │ try_send()
               ▼
┌──────────────────────────┐
│ IngestionBuffer (bounded │ ◄── Arc<IngestionBuffer> shared
│ tokio mpsc, cap 10000)   │
└──────────────┬───────────┘
               │ recv().await
               ▼
┌────────────────────────────────────────────┐
│ DetectionConsumer (NEW — this story)        │
│ ├─ IngestionData::Metric → MetricDetector  │
│ │   └─ Per-metric EWMA (bounded HashMap)   │
│ └─ IngestionData::Log → LogDetector        │
│     └─ Per-service error rate EWMA         │
│                                            │
│ On anomaly detected:                       │
│   → Check cooldown                         │
│   → Create Investigation CRD               │
└──────────────┬─────────────────────────────┘
               │ kube::Api<Investigation>::create()
               ▼
┌────────────────────────────────────────────┐
│ Investigation Controller (Story 1-9)       │
│ → Reconciles → Spawns K8s Job              │
└────────────────────────────────────────────┘
```

**Key constraint:** The `IngestionBuffer` uses a **single-consumer** tokio mpsc channel. The `DetectionConsumer` MUST be the only task calling `recv()`. This is by design — the buffer exists specifically to feed the detection pipeline.

### Existing Types to Import (Do NOT Redefine)

**From `operator/src/ingestion/buffer.rs` (Story 1-6):**
```rust
pub enum IngestionData {
    Metric(MetricSample),
    Log(LogEntry),
}

pub struct MetricSample {
    pub name: String,                         // __name__ label value
    pub labels: HashMap<String, String>,      // All labels including __name__
    pub value: f64,
    pub timestamp_ms: i64,                    // Milliseconds since epoch
}

pub struct LogEntry {
    pub labels: HashMap<String, String>,      // Stream labels
    pub line: String,                         // Log line content
    pub timestamp_ns: i64,                    // Nanoseconds since epoch
}
```

**From `operator/src/crds/investigation.rs` (Story 1-9):**
```rust
pub struct InvestigationSpec {
    pub condition: String,                    // e.g., "Metric cpu_usage spike: 95.2, expected 42.3 ± 8.1"
    pub service: String,                      // Affected service name
    pub severity: Severity,                   // Low, Medium, High, Critical
    pub triggered_at: Option<String>,         // ISO 8601 timestamp
}

pub enum Severity { Low, Medium, High, Critical }
```

### Investigation CRD Creation

When an anomaly is detected and passes cooldown, create an Investigation CRD:

```rust
use crate::crds::investigation::{Investigation, InvestigationSpec, Severity};

// Generate unique name: "anomaly-{timestamp_hex}" or "anomaly-{short_random}"
let name = format!("anomaly-{:x}", chrono::Utc::now().timestamp());

let investigation = Investigation::new(&name, InvestigationSpec {
    condition: event.condition.clone(),
    service: event.service.clone(),
    severity: map_severity(event.deviation),
    triggered_at: Some(chrono::Utc::now().to_rfc3339()),
});

let api: Api<Investigation> = Api::namespaced(client.clone(), &namespace);
api.create(&PostParams::default(), &investigation).await?;
```

**Severity mapping from deviation magnitude:**

| Deviation | Severity | Rationale |
|-----------|----------|-----------|
| 2.0-3.0σ | Low | Marginal — could be normal variance |
| 3.0-4.0σ | Medium | Significant — above three-sigma threshold |
| 4.0-6.0σ | High | Serious — strong anomaly signal |
| >6.0σ | Critical | Extreme — immediate attention warranted |

Note: the default threshold is 3.0σ, so the minimum detected anomaly maps to `Medium`. If the developer wants to catch `Low` severity anomalies, they lower the threshold — but this isn't the default behavior.

### Cooldown Strategy

Prevent alert storms by tracking recently-fired anomaly fingerprints:

```rust
struct CooldownTracker {
    recent: HashMap<String, Instant>,
    cooldown_duration: Duration,
}
```

**Anomaly fingerprint** = `"{anomaly_type}:{service}:{source}"` — e.g.:
- `"metric_spike:frontend:http_requests_total"`
- `"error_rate:api-server"`

If the same fingerprint was seen within `cooldown_secs` (default 600s = 10 minutes), skip Investigation creation. Clean up expired entries periodically (e.g., every 100 anomaly checks or when map exceeds 1000 entries).

### Log Detection Details

**Error detection:** Check `level` label on `LogEntry`. Treat as error if value matches (case-insensitive): `error`, `err`, `fatal`, `critical`, `panic`. If no `level` label, skip (non-error by default).

**Service extraction:** Check labels in order: `service` → `app` → `job` → `namespace`. Use first non-empty match. Fall back to `"unknown"`.

**Sliding window:** Use 1-minute buckets in a `VecDeque<(i64, u32)>` (timestamp_ms, count). The window covers `window_secs` (default 300s = 5 minutes). Drop buckets older than the window on each update. Error rate = sum of all bucket counts within window.

**Context capture:** Store the last `max_context_lines` (default 5) error log lines per service in a `VecDeque<String>`. Include these in the `AnomalyEvent` when the error rate anomaly fires. This fulfills AC3 ("relevant log lines are captured as context").

### Metric Key Design

The `MetricKey` determines which metric samples are tracked together as one time series:

```rust
#[derive(Hash, Eq, PartialEq, Clone)]
struct MetricKey {
    name: String,
    // Only include discriminating labels, NOT high-cardinality ones like pod_id
    labels: BTreeMap<String, String>,
}
```

**Label selection:** From `MetricSample.labels`, include only: `service`, `instance`, `job`, `namespace`, `endpoint`. Exclude high-cardinality labels like `pod`, `container_id`, `request_id` to prevent HashMap explosion.

### Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `BEEPER_DETECTION_ENABLED` | `true` | Enable/disable detection consumer |
| `BEEPER_DETECTION_METRIC_ALPHA` | `0.2` | EWMA smoothing factor for metrics |
| `BEEPER_DETECTION_METRIC_THRESHOLD` | `3.0` | Stddev multiplier for metric anomalies |
| `BEEPER_DETECTION_LOG_ALPHA` | `0.2` | EWMA smoothing factor for log error rates |
| `BEEPER_DETECTION_LOG_THRESHOLD` | `3.0` | Stddev multiplier for log anomalies |
| `BEEPER_DETECTION_MIN_SAMPLES` | `10` | Data points before detection activates |
| `BEEPER_DETECTION_COOLDOWN_SECS` | `600` | Seconds between duplicate investigations |
| `BEEPER_DETECTION_MAX_METRICS` | `10000` | Max tracked metric series |
| `BEEPER_DETECTION_MAX_SERVICES` | `1000` | Max tracked services for log detection |
| `BEEPER_DETECTION_WINDOW_SECS` | `300` | Sliding window for log error rates |
| `BEEPER_DETECTION_NAMESPACE` | `default` | K8s namespace for Investigation CRDs |

### Structured Logging

Follow the existing JSON logging pattern established in Stories 1-4 through 1-9:

```rust
tracing::info!(
    component = "detection",
    anomaly_type = %event.anomaly_type,
    service = %event.service,
    severity = %event.severity,
    deviation = event.deviation,
    "Anomaly detected: {}", event.condition
);

tracing::info!(
    component = "detection",
    investigation = %investigation_name,
    service = %event.service,
    "Investigation created for anomaly"
);

tracing::debug!(
    component = "detection",
    metrics_tracked = stats.metrics_tracked,
    services_tracked = stats.services_tracked,
    anomalies_total = stats.anomalies_detected,
    "Detection stats"
);
```

### Performance Considerations

- **EWMA update:** O(1) per data point — single arithmetic operation
- **HashMap lookup:** O(1) amortized per metric/service
- **Memory per metric:** ~80 bytes (EwmaDetector ~32 bytes + MetricKey ~48 bytes avg)
- **10,000 metrics × 80 bytes:** ~800 KB total — negligible
- **Buffer consumption latency:** EWMA update is nanoseconds. The consumer will easily keep up with ingestion rates. If it falls behind, the buffer fills and ingestion returns 503/429 (existing backpressure — this is correct behavior).
- **Investigation creation:** Async K8s API call, non-blocking. Cooldown prevents API overload.
- **NFR-P1 compliance:** Data flows from ingestion → buffer → detection in a single async hop. Latency is bounded by buffer depth and consumer processing speed, both sub-second.

### Security Considerations

- Detection operates on already-ingested data (no new external network inputs)
- Investigation CRD creation requires RBAC: operator ServiceAccount must have `create` permission on `investigations.beeper.dev` (already granted by Story 1-9 RBAC setup)
- No new secrets or credentials needed
- Anomaly condition strings are generated from internal metric/label data — no user input, no injection risk
- Bounded HashMaps prevent memory exhaustion from cardinality explosion

### Project Structure Notes

**New files to create:**
```
operator/src/detection/
├── mod.rs          # Module exports, DetectionConfig, DetectionStats
├── types.rs        # AnomalyEvent, AnomalyType, AnomalySignal
├── ewma.rs         # EwmaDetector (core EWMA algorithm)
├── metrics.rs      # MetricDetector (per-metric EWMA tracking)
├── logs.rs         # LogDetector (per-service error rate tracking)
└── consumer.rs     # DetectionConsumer (buffer reader + investigation bridge)
```

**Files to modify:**
```
operator/src/
├── lib.rs          # Add `pub mod detection;`
├── main.rs         # Spawn detection consumer as 5th background task, load DetectionConfig
├── api.rs          # Add GET /api/v1/detection/stats endpoint, add DetectionStats to ApiState
```

### Testing Strategy

**Unit Tests (inline in each module with `#[cfg(test)]`):**
- `ewma.rs`: Test EWMA math — spike, drop, warmup, adaptation, steady state, parameter sensitivity
- `metrics.rs`: Test per-metric tracking, bounded eviction, MetricKey construction, event fields
- `logs.rs`: Test error rate tracking, sliding window, service extraction, context capture
- `consumer.rs`: Test severity mapping, cooldown logic, anomaly fingerprinting
- `types.rs`: Test AnomalyEvent construction, Display implementations

**Integration Tests (in `operator/src/detection/consumer.rs` or separate test module):**
- Push `MetricSample` data through an `IngestionBuffer` → verify `MetricDetector` produces anomaly
- Push `LogEntry` data through buffer → verify `LogDetector` produces anomaly
- Push steady-state data → verify no false positives
- Use `tokio::test` for async tests
- For CRD creation tests: either mock the K8s API or test the spec construction without actual API calls

**Test Commands:**
```bash
cd operator && cargo test                    # Run all tests
cd operator && cargo test detection          # Run only detection module tests
cd operator && cargo clippy -- -D warnings   # Must pass with zero warnings
```

### Previous Story Learnings

**From Story 1-6 (Streaming Data Ingestion) — Code Review:**
- Backpressure uses `try_send()` returning `Err` when full — consumer must not block
- Environment variables must actually be implemented if documented (was caught missing in review)
- Test descriptions must match what the test actually verifies

**From Story 1-9 (Investigation CRD Pod Spawning) — Code Review:**
- `INVESTIGATION_NAMESPACE` was missing from Job env vars — always pass namespace explicitly
- ServiceAccount must be set on PodSpec for RBAC to work
- Qdrant env vars are `QDRANT_HOST`/`QDRANT_PORT` (NOT `BEEPER_QDRANT_URL`)

**From Story 1-4/1-5 (Source Adapters) — Code Review:**
- Use `chrono` for timestamps, NOT hand-rolled date calculation
- Loki timestamps are **nanoseconds**, Prometheus timestamps are **milliseconds** — must handle both
- Extract helper functions to prevent code duplication across similar operations

### References

- [Source: architecture.md#Investigation Engine Architecture - Data pipeline and operator detection role]
- [Source: architecture.md#Operator Component - Rust + kube-rs requirement]
- [Source: architecture.md#Performance Requirements - NFR-P1 anomaly detection latency in seconds]
- [Source: architecture.md#Data Architecture - Qdrant investigations collection schema]
- [Source: epics.md#Story 3.1 - Acceptance criteria, FR1, FR43, FR45]
- [Source: epics.md#Epic 3 - All 10 stories context and dependencies]
- [Source: 1-6-streaming-data-ingestion.md - IngestionBuffer API, MetricSample, LogEntry types, backpressure]
- [Source: 1-9-investigation-crd-pod-spawning.md - Investigation CRD types, Job spawning, RBAC patterns]
- [Source: 1-4-source-crd-prometheus-adapter.md - Prometheus data structures, timestamp formats]
- [Source: 1-5-loki-adapter.md - Loki data structures, nanosecond timestamps, health check patterns]
- [Research: EWMA for time-series anomaly detection - AnEWMA (SCITEPRESS 2025)]
- [Research: Welford's online algorithm for running variance]

---

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
