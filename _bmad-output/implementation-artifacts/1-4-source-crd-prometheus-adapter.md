# Story 1.4: Source CRD & Prometheus Adapter

Status: done

## Story

As an **Admin**,
I want to configure Prometheus as a metrics data source via CRD,
So that Beeper can query metrics for anomaly detection.

## Acceptance Criteria

### AC1: Source CRD Configuration
**Given** the Source CRD is defined
**When** I apply a Source manifest:
```yaml
apiVersion: beeper.dev/v1
kind: Source
metadata:
  name: prometheus-main
spec:
  type: prometheus
  endpoint: http://prometheus:9090
  credentialsSecret: prometheus-creds
```
**Then** the operator reconciles and validates the configuration
**And** the Source status shows `connected: true` or error details

### AC2: Read-Only Credentials
**Given** a valid Prometheus source is configured
**When** the operator queries Prometheus
**Then** it uses read-only credentials from K8s Secret (FR26)
**And** PromQL queries execute successfully

### AC3: Connection Error Handling
**Given** invalid credentials are provided
**When** the operator attempts connection
**Then** the Source status shows `connected: false`
**And** error details explain the failure

### AC4: PromQL Query Execution
**Given** a connected Prometheus source
**When** the operator executes a PromQL query
**Then** the query returns valid metric data
**And** the response is parsed correctly for anomaly detection

## Tasks / Subtasks

- [x] Task 1: Implement Prometheus client in Rust (AC: #2, #4)
  - [x] 1.1: Add `reqwest` dependency to Cargo.toml for HTTP client
  - [x] 1.2: Create `operator/src/sources/mod.rs` module structure
  - [x] 1.3: Create `operator/src/sources/prometheus.rs` with PromQL client
  - [x] 1.4: Implement `PrometheusClient::new(endpoint, credentials)` constructor
  - [x] 1.5: Implement `query(promql: &str) -> Result<QueryResult>` for instant queries
  - [x] 1.6: Implement `query_range(promql: &str, start, end, step) -> Result<RangeResult>` for range queries
  - [x] 1.7: Add proper error types for Prometheus API errors (PrometheusError enum)

- [x] Task 2: Implement K8s Secret credential loading (AC: #2)
  - [x] 2.1: Add function to read Secret by name in namespace
  - [x] 2.2: Parse `username` and `password` fields from Secret data
  - [x] 2.3: Support optional authentication (credentials_secret is optional)
  - [x] 2.4: Implement Basic Auth header construction for authenticated requests
  - [x] 2.5: Handle Secret not found error gracefully with clear message

- [x] Task 3: Update Source controller with connectivity check (AC: #1, #3)
  - [x] 3.1: Replace reconcile stub with actual connectivity logic
  - [x] 3.2: On reconcile, attempt connection to Prometheus endpoint
  - [x] 3.3: Execute simple health query (`up` metric) to validate connectivity
  - [x] 3.4: Update Source status with connected=true on success
  - [x] 3.5: Update Source status with connected=false and error message on failure
  - [x] 3.6: Update last_checked timestamp on every check

- [x] Task 4: Implement status subresource updates (AC: #1, #3)
  - [x] 4.1: Add PATCH status subresource capability to Source controller
  - [x] 4.2: Implement `update_status(source: &Source, status: SourceStatus)` function
  - [x] 4.3: Handle status update conflicts with retry logic
  - [x] 4.4: Log status transitions (connected->disconnected, disconnected->connected)

- [x] Task 5: Add connection retry and backoff (AC: #3)
  - [x] 5.1: Implement exponential backoff for failed connections (5s, 10s, 20s, 60s max)
  - [x] 5.2: Add configurable retry count before marking permanently failed
  - [x] 5.3: Reset backoff on successful connection
  - [x] 5.4: Requeue reconciliation with appropriate delay based on status

- [x] Task 6: Add unit tests for Prometheus client (AC: #2, #4)
  - [x] 6.1: Add test for successful query response parsing
  - [x] 6.2: Add test for query range response parsing
  - [x] 6.3: Add test for authentication header construction
  - [x] 6.4: Add test for error response handling (invalid query, timeout, auth failure)
  - [x] 6.5: Add test for credential parsing from Secret data

- [x] Task 7: Add integration tests with mock server (AC: #1, #2, #3, #4)
  - [x] 7.1: Add `wiremock` or similar for HTTP mocking
  - [x] 7.2: Test full reconciliation flow with mocked Prometheus
  - [x] 7.3: Test status update on successful connection
  - [x] 7.4: Test status update on connection failure
  - [x] 7.5: Mark integration tests with `#[ignore]` for CI without K8s

- [x] Task 8: Documentation and validation (AC: #1, #2, #3, #4)
  - [x] 8.1: Update README with Prometheus source configuration examples
  - [x] 8.2: Document required Secret format for credentials
  - [x] 8.3: Add troubleshooting section for common connection errors
  - [x] 8.4: Run `cargo test` to verify all tests pass
  - [x] 8.5: Run `cargo clippy` to verify no linting issues

## Dev Notes

### Architecture Compliance

**Source:** [architecture.md - Technology Stack Decisions]

The Prometheus adapter uses:
- **Rust + kube-rs**: Production-ready, async, memory-safe operators
- **reqwest**: Async HTTP client for Rust (widely used, well-maintained)
- **serde_json**: JSON parsing for PromQL responses

**Source:** [architecture.md - Project Structure & Boundaries]

File location: `operator/src/sources/prometheus.rs`
- Matches architecture spec: `operator/src/sources/prometheus.rs # FR24: Prometheus adapter`

### Previous Story Learnings (1-3)

**Source:** [1-3-k8s-operator-scaffold.md - Dev Agent Record]

Key patterns established:
- CRD structs use `#[serde(rename_all = "snake_case")]` for JSON field naming
- Controller uses `Arc<Context>` pattern for shared state
- Error types use `thiserror` for derive macros
- Status updates must use status subresource (not full resource update)
- Tests use `#[ignore]` attribute for integration tests requiring K8s
- Log levels: debug for routine operations, info for state changes, warn/error for problems

**Code Review Fixes Applied:**
- Comments should accurately reflect implementation (no "exponential backoff" if fixed delay)
- Readiness checks use debug! level, not info!
- Controller logs should clearly indicate stub vs actual implementation

### Prometheus API Patterns

**Source:** [Prometheus HTTP API Documentation]

PromQL API endpoints:
- Instant query: `GET /api/v1/query?query=<expr>&time=<rfc3339|unix>`
- Range query: `GET /api/v1/query_range?query=<expr>&start=<rfc3339>&end=<rfc3339>&step=<duration>`

Response format:
```json
{
  "status": "success",
  "data": {
    "resultType": "vector" | "matrix" | "scalar" | "string",
    "result": [...]
  }
}
```

Error response:
```json
{
  "status": "error",
  "errorType": "bad_data" | "timeout" | "canceled" | "execution" | "internal",
  "error": "error message"
}
```

### Credential Secret Format

The credentials Secret should contain:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: prometheus-creds
type: kubernetes.io/basic-auth
data:
  username: <base64-encoded-username>
  password: <base64-encoded-password>
```

### Error Handling Strategy

**Source:** [architecture.md - Process Patterns]

Error messages should be:
- Actionable: "Connection refused at http://prometheus:9090 - verify endpoint is accessible"
- Specific: Include HTTP status code, timeout duration, or auth failure type
- Non-exposing: Don't leak sensitive credential information

### Existing Source CRD Definition

**Source:** [operator/src/crds/source.rs]

The Source CRD is already defined with:
```rust
pub struct SourceSpec {
    pub source_type: SourceType,  // Prometheus or Loki
    pub endpoint: String,
    pub credentials_secret: Option<String>,
}

pub struct SourceStatus {
    pub connected: Option<bool>,
    pub last_checked: Option<String>,
    pub error: Option<String>,
}
```

This story implements the actual connectivity check logic for Prometheus sources.

### Dependencies to Add

```toml
# Cargo.toml additions for this story
reqwest = { version = "0.11", features = ["json"] }
```

Note: tokio, serde, serde_json already present from Story 1.3.

### Project Structure Notes

Files to create/modify:
```
operator/src/
├── sources/
│   ├── mod.rs                 # NEW: Source adapters module
│   └── prometheus.rs          # NEW: Prometheus client
├── controllers/
│   └── source.rs              # MODIFY: Add actual connectivity logic
└── lib.rs                     # MODIFY: Export sources module
```

### Testing Strategy

**Unit Tests:**
- Prometheus response parsing (success and error cases)
- Credential extraction from Secret
- Auth header construction
- Error type conversions

**Integration Tests (mock server):**
- Full reconciliation with mocked Prometheus
- Status update flow

**Integration Tests (real K8s):**
- Mark with `#[ignore]` for CI
- Test with actual Prometheus if available locally

### Dependencies

This story depends on:
- Story 1.3 (K8s Operator Scaffold) - COMPLETED ✅
  - Source CRD definition
  - Source controller scaffold
  - Helm templates for CRD

This story blocks:
- Story 1.5 (Loki Adapter) - same pattern for Loki
- Story 1.6 (Streaming Data Ingestion) - needs working source adapters
- Story 1.7 (Source Status UI) - needs source status updates

### References

- [Source: architecture.md#Technology Stack Decisions]
- [Source: architecture.md#Project Structure & Boundaries]
- [Source: architecture.md#Implementation Patterns & Consistency Rules]
- [Source: epics.md#Story 1.4: Source CRD & Prometheus Adapter]
- [Source: 1-3-k8s-operator-scaffold.md#Dev Agent Record]
- [Prometheus HTTP API](https://prometheus.io/docs/prometheus/latest/querying/api/)
- [reqwest crate documentation](https://docs.rs/reqwest/)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- Added Default derive to QueryData to fix deserialization issue with PrometheusResponse
- Removed unused Serialize import from prometheus.rs
- Fixed type inference issue in error formatting by adding explicit type annotation
- Added Credentials export to sources/mod.rs

### Completion Notes List

- ✅ Created PrometheusClient with async query() and query_range() methods
- ✅ Implemented Credentials struct with base64 decoding and Basic Auth header construction
- ✅ Added PrometheusError enum with actionable error messages
- ✅ Implemented load_credentials() to read K8s Secrets for authentication
- ✅ Updated Source controller with actual connectivity check logic using check_health()
- ✅ Implemented update_source_status() with PATCH on status subresource
- ✅ Added BackoffConfig with exponential backoff (5s, 10s, 20s, 40s, 60s max)
- ✅ Logs state transitions (connected/disconnected) at appropriate levels
- ✅ All 37 tests pass including 8 integration tests with wiremock
- ✅ cargo clippy passes with no warnings
- ✅ Updated README with Prometheus configuration examples, Secret format, and troubleshooting

### File List

**New Files:**
- operator/src/sources/mod.rs
- operator/src/sources/prometheus.rs

**Modified Files:**
- operator/Cargo.toml (added reqwest, base64, chrono, wiremock)
- operator/src/lib.rs (added sources module export)
- operator/src/controllers/source.rs (replaced stub with connectivity logic)
- operator/src/crds/source.rs (added retry_count to SourceStatus)
- README.md (added Prometheus configuration documentation)

### Code Review Fixes Applied

**Reviewer:** Claude Opus 4.5 (adversarial code review)

1. **[HIGH] Fixed broken timestamp generation** - Replaced hand-rolled date calculation with chrono crate for correct ISO 8601 timestamps
2. **[MEDIUM] Implemented retry count persistence** - Added `retry_count` field to SourceStatus, now properly increments on failure and resets on success
3. **[MEDIUM] Removed dead BackoffConfig._retry_count field** - Eliminated unused struct field
4. **[MEDIUM] Fixed integration test to verify auth header** - Added header matcher to wiremock test to actually verify Authorization header is sent
5. **[MEDIUM] Updated File List** - Added missing files to documentation

## Change Log

- 2026-02-10: Story created via create-story workflow with comprehensive context from Story 1.3
- 2026-02-10: Story implementation completed - all 8 tasks with 40 subtasks finished
- 2026-02-10: Code review completed - 5 issues fixed (1 HIGH, 4 MEDIUM)
