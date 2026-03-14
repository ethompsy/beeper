# Story 2.1: NotificationChannel CRD & Durable Outbox

Status: done

## Story

As a **user**,
I want to configure outbound notification channels via a NotificationChannel custom resource,
so that Beeper can send alerts through my team's existing communication tools.

## Acceptance Criteria

1. **AC1: NotificationChannel CRD validation and status reporting**
   **Given** a NotificationChannel CRD YAML with type (slack/pagerduty/email/webhook), config, credentials_secret, and routing rules
   **When** the CRD is applied to the K8s cluster
   **Then** the operator validates the credentials_secret exists and reports channel status (configured/error)
   **And** the CRD is validated for required fields per channel type

2. **AC2: Notification outbox collection auto-creation**
   **Given** the notification system initializes
   **When** the `notification_outbox` Qdrant collection does not exist
   **Then** it is created automatically as payload-only
   **And** the background outbox worker starts processing queued notifications

3. **AC3: Durable notification persistence and retry**
   **Given** a notification event is generated (investigation started/completed/fix proposed)
   **When** the notification is written to the outbox
   **Then** it persists in Qdrant and survives process restart
   **And** failed deliveries retry with exponential backoff

## Tasks / Subtasks

- [x] Task 1: Create NotificationChannel CRD definition (AC: #1)
  - [x]1.1: Create `operator/src/crds/notification_channel.rs` with `NotificationChannelSpec` struct: `channel_type` (enum: slack/pagerduty/email/webhook), `config` (HashMap<String, String>), `credentials_secret` (String), `routing` (optional RoutingConfig)
  - [x]1.2: Define `RoutingConfig` struct: `min_severity` (optional String), `services` (optional Vec<String>), `quiet_hours` (optional QuietHoursConfig)
  - [x]1.3: Define `QuietHoursConfig` struct: `enabled` (bool), `start` (String), `end` (String), `timezone` (String), `escalation_override` (bool)
  - [x]1.4: Define `NotificationChannelStatus` struct: `condition` (NotificationChannelCondition enum: configured/error), `last_validated` (Option<String>), `error` (Option<String>)
  - [x]1.5: Implement `validate_spec()` function validating: non-empty channel_type, non-empty credentials_secret, channel-type-specific config requirements (slack: channel required; pagerduty: routing_key required; email: smtp_host+recipients required; webhook: url required)
  - [x]1.6: Add comprehensive unit tests for CRD serialization, deserialization, validation, and enum variants
  - [x]1.7: Update `operator/src/crds/mod.rs` to export NotificationChannel types

- [x] Task 2: Create NotificationChannel controller (AC: #1)
  - [x]2.1: Create `operator/src/controllers/notification_channel.rs` following the ServiceLevel controller pattern: reconcile function validates spec, checks K8s Secret existence (via client), patches status
  - [x]2.2: Implement `reconcile()`: validate spec → check Secret exists via K8s API → set status to configured/error → patch status subresource → requeue after 300s
  - [x]2.3: Implement `error_policy()` with exponential backoff (matching Story 1-8 pattern: base 5s, factor 2x, max 60s, jitter)
  - [x]2.4: Implement `run_notificationchannel_controller()` public function following existing controller startup pattern
  - [x]2.5: Add unit tests for validation, error handling, error type display
  - [x]2.6: Update `operator/src/controllers/mod.rs` to export `run_notificationchannel_controller`

- [x] Task 3: Create Helm CRD template (AC: #1)
  - [x]3.1: Create `helm/beeper/templates/crds/notification-channel-crd.yaml` following servicelevel-crd.yaml pattern: apiVersion, kind NotificationChannel, group beeper.dev, namespaced, with full OpenAPI v3 schema validation
  - [x]3.2: Add additionalPrinterColumns: Type, Credentials Secret, Condition, Age

- [x] Task 4: Register controller in operator main.rs (AC: #1)
  - [x]4.1: Import `run_notificationchannel_controller` in `main.rs`
  - [x]4.2: Add controller spawn alongside existing source/investigation/servicelevel controllers using same tokio::spawn pattern with client clone and shutdown signal

- [x] Task 5: Create notification outbox collection initialization (AC: #2)
  - [x]5.1: Add `notification_outbox` collection creation to operator startup in `api.rs` or wherever Qdrant collection initialization occurs — create as payload-only collection (no vector index), using `qdrant_client` API
  - [x]5.2: Implement idempotent creation — check if collection exists first, create only if missing
  - [x]5.3: Define outbox point schema: `id` (UUID), `investigation_id` (String), `event_type` (String: investigation_started/investigation_completed/fix_proposed), `severity` (String), `service` (String), `payload` (JSON), `status` (String: pending/delivered/failed), `retry_count` (u32), `created_at` (ISO 8601), `next_retry_at` (ISO 8601), `last_error` (optional String)

- [x] Task 6: Create notification outbox API endpoints (AC: #2, #3)
  - [x]6.1: Add `POST /api/v1/notifications/outbox` endpoint to `api.rs` that writes a notification event to the outbox collection — accepts investigation_id, event_type, severity, service, payload
  - [x]6.2: Add `GET /api/v1/notifications/channels` endpoint to `api.rs` that lists all NotificationChannel CRDs with their status
  - [x]6.3: Add Rust tests for outbox write and channel listing endpoints

- [x] Task 7: Create background outbox worker (AC: #2, #3)
  - [x]7.1: Create `operator/src/notifications/mod.rs` and `operator/src/notifications/outbox.rs` with `OutboxWorker` struct that runs a periodic loop (every 5 seconds) querying `notification_outbox` for pending notifications
  - [x]7.2: Implement `process_pending()`: query Qdrant for points with status="pending" and next_retry_at <= now, mark as in_progress, attempt delivery (placeholder — actual channel delivery in stories 2-3 through 2-5), mark delivered or increment retry_count with exponential backoff (base 30s, factor 2x, max 3600s)
  - [x]7.3: Integrate with graceful shutdown — accept shutdown_rx from main.rs watch channel, check before each processing cycle
  - [x]7.4: Spawn outbox worker in `main.rs` alongside other background tasks
  - [x]7.5: Add unit tests for backoff calculation, retry logic, outbox point status transitions

- [x] Task 8: Write comprehensive tests (AC: #1, #2, #3)
  - [x]8.1: CRD tests in `notification_channel.rs`: serialization/deserialization for all channel types, validation pass/fail for each channel type's required config, routing config serialization, quiet hours config, enum variants
  - [x]8.2: Controller tests in `notification_channel.rs` controller module: validation success, validation failure status, error type display, error conversions
  - [x]8.3: Outbox worker tests in `outbox.rs`: backoff calculation (30s, 60s, 120s, capped at 3600s), retry count increment, status transitions (pending → delivered, pending → failed after max retries)
  - [x]8.4: Regression guard — all existing Python tests (512 investigator + 705 UI) must pass unchanged

## Dev Notes

### Architecture Compliance

**File Placement (from architecture.md):**
```
operator/src/crds/notification_channel.rs        # New: NotificationChannel CRD definition
operator/src/controllers/notification_channel.rs  # New: NotificationChannel controller
operator/src/notifications/mod.rs                 # New: Notification module
operator/src/notifications/outbox.rs              # New: Outbox worker
operator/src/main.rs                              # Modified: register new controller + outbox worker
operator/src/api.rs                               # Modified: add outbox write + channel list endpoints
operator/src/crds/mod.rs                          # Modified: export NotificationChannel types
operator/src/controllers/mod.rs                   # Modified: export run_notificationchannel_controller
helm/beeper/templates/crds/notification-channel-crd.yaml  # New: Helm CRD template
```
[Source: _bmad-output/planning-artifacts/architecture.md#FR to Structure Mapping — FR8]
[Source: _bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure, lines 954-964]

**FR to Implementation Mapping:**
- FR8 (notification channels): `operator/src/crds/notification_channel.rs` — CRD definition with channel types and routing config
- FR14 (quiet hours + escalation): `RoutingConfig` and `QuietHoursConfig` structs in CRD spec — data model only, routing engine in Story 2-2
[Source: _bmad-output/planning-artifacts/architecture.md#FR to Structure Mapping]

**NFR Compliance:**
- NFR22 (1000+ notifications/hour): Qdrant payload-only collection handles write volume. Background worker processes in batches. Outbox pattern ensures no drops.
- NFR17 (zero data loss): Qdrant persistent volumes survive operator restart. Notification outbox persists pending notifications.
[Source: _bmad-output/planning-artifacts/prd.md#Non-Functional Requirements]

### Implementation Approach

**Key Design Decisions:**

1. **NotificationChannel CRD follows ServiceLevel CRD pattern exactly:**
   Same `#[derive(CustomResource, ...)]` macro, same validation function pattern, same status subresource pattern, same test structure. This is deliberate — the ServiceLevel CRD (Story 1-3) established the pattern and it works well.

2. **Channel type as enum, not string:**
   Using `#[serde(rename_all = "snake_case")]` enum `ChannelType { Slack, Pagerduty, Email, Webhook }` instead of a freeform string. This enables compile-time exhaustive matching and prevents typos. The architecture CRD example uses lowercase strings (`slack`, `pagerduty`, etc.) which matches snake_case serialization.

3. **Config as HashMap<String, String> (not typed per-channel):**
   Architecture shows `config` as a flat YAML map. Using `HashMap<String, String>` allows each channel type to have its own config keys without creating separate struct variants. Validation ensures required keys exist per channel type.

4. **Outbox as Qdrant payload-only collection:**
   Architecture doc explicitly specifies this pattern (line 254, 410). No vector index needed — outbox queries are by status + time range, not semantic similarity. Uses `qdrant_client::qdrant::CreateCollectionBuilder` with no vector config.

5. **Exponential backoff for delivery retry (base 30s, factor 2x, max 3600s):**
   Different from controller retry (base 5s) — notification delivery failures should wait longer before retry since external services (Slack, PagerDuty) may have rate limits or outages. The 30s base delay allows transient failures to clear. Max 1 hour prevents infinite retry storms.

6. **Placeholder delivery in outbox worker:**
   Story 2-1 establishes the outbox infrastructure. Actual channel delivery implementations come in Stories 2-3 (Slack), 2-4 (PagerDuty), 2-5 (Email/Webhook). The outbox worker in 2-1 marks notifications as delivered (placeholder) or provides a hook point for channel-specific delivery.

7. **Secret validation via K8s API (not direct access):**
   The controller checks that the referenced `credentials_secret` K8s Secret exists in the same namespace using `Api::<Secret>::namespaced(client, namespace).get(name)`. It does NOT read Secret data — just validates existence. This follows the least-privilege principle (NFR8).

8. **Outbox worker runs in operator process (not separate service):**
   Architecture decision (line 461): "Durable outbox + async worker" as MVP, with "Dedicated notification service" as scale target. For v0.2.0 MVP, the worker runs as a tokio task in the operator process.

### Technical Requirements

- **Rust (stable)** — operator code
- **kube-rs** — K8s controller framework (existing dependency)
- **schemars** — JSON Schema derivation for CRD (existing dependency)
- **serde + serde_json** — serialization (existing dependency)
- **chrono** — timestamps (existing dependency)
- **thiserror** — error type derivation (existing dependency)
- **qdrant-client** — Qdrant payload collection operations (existing dependency)
- **uuid** — outbox point IDs (check if already a dependency, add if not)
- **No new Python dependencies** — this story is operator-only (Rust)

### Library & Framework Requirements

- Use `kube::CustomResource` derive macro for CRD definition — same pattern as ServiceLevel
- Use `kube::runtime::controller::Controller` for CRD watching — same pattern as ServiceLevel
- Use `Api::<k8s_openapi::api::core::v1::Secret>` for Secret existence check — NOT direct etcd access
- Use `qdrant_client` for outbox collection creation and point operations
- Use `tokio::sync::watch` for shutdown signal in outbox worker — same as main.rs pattern from Story 1-8
- Use `tokio::time::interval` for periodic outbox processing — same as SLO engine loop pattern
- Use `tracing::{info, warn, error, debug}` for logging — NOT println!
- Use `thiserror::Error` for error types — same as ServiceLevelError pattern
- Use `serde_json::json!` for status patch — same as ServiceLevel controller

### File Structure Requirements

**New files to create:**
```
operator/src/crds/notification_channel.rs          # CRD definition + validation + tests
operator/src/controllers/notification_channel.rs    # Controller + tests
operator/src/notifications/mod.rs                   # Module declaration
operator/src/notifications/outbox.rs                # Outbox worker + tests
helm/beeper/templates/crds/notification-channel-crd.yaml  # Helm CRD template
```

**Files to modify:**
```
operator/src/crds/mod.rs                            # Add notification_channel module + exports
operator/src/controllers/mod.rs                     # Add notification_channel module + export run fn
operator/src/main.rs                                # Spawn controller + outbox worker
operator/src/api.rs                                 # Add outbox write + channel list endpoints
operator/src/lib.rs                                 # Add notifications module declaration
```

### Testing Requirements

- **Framework:** `#[test]` and `#[tokio::test]` for Rust
- **CRD testing:** Serialization/deserialization round-trips, validate_spec() pass/fail cases per channel type, enum variant serialization
- **Controller testing:** Error type display, error conversions (From impls), validate spec integration
- **Outbox testing:** Backoff duration calculation, point schema validation, status transitions
- **No mock K8s needed** — CRD and validation tests are pure Rust struct tests (matching ServiceLevel pattern)
- **Regression:** All existing Python tests (512 investigator + 705 UI) must pass unchanged — this story touches only Rust code
- **No new test dependencies required** — serde_json (for JSON round-trip tests) is already a dependency

### Critical Guardrails

1. **DO NOT implement actual channel delivery (Slack, PagerDuty, email, webhook).** This story creates the CRD, outbox, and worker infrastructure. Actual delivery is Stories 2-3 through 2-5.
2. **DO NOT implement the routing rules engine.** The CRD includes routing config as data model only. The routing engine is Story 2-2.
3. **DO NOT add notification UI routes or templates.** The notification configuration UI is Story 2-7.
4. **DO NOT modify any Python code (investigator or UI).** This is an operator-only Rust story.
5. **DO NOT create a `notification_history` collection.** That's for Story 2-6 (Notification Audit). Only create `notification_outbox`.
6. **DO NOT add new Rust crate dependencies unless absolutely necessary.** `uuid` may be needed for outbox point IDs — check if already in Cargo.toml before adding.
7. **Follow existing CRD patterns exactly.** The ServiceLevel CRD in `operator/src/crds/servicelevel.rs` is the canonical pattern. Match its structure, derive macros, test style, and validation approach.
8. **Follow existing controller patterns exactly.** The ServiceLevel controller in `operator/src/controllers/servicelevel.rs` is the canonical pattern. Match its reconcile/error_policy/run structure.
9. **Use `credentials_secret` NOT `credentialsSecret`.** The architecture CRD YAML example uses snake_case. Rust serde with `rename_all = "snake_case"` handles this correctly.
10. **Outbox worker must respect graceful shutdown.** Use the same `watch::Receiver<bool>` pattern from Story 1-8 main.rs.
11. **Rust code must follow existing patterns:** `tracing` for logging, `thiserror` for errors, `serde` for serialization, `chrono::Utc` for timestamps.

### Previous Story Intelligence

**Story 1-8 (Platform Resilience) — graceful shutdown pattern:**
- Implemented `tokio::sync::watch` channel for shutdown signaling
- `tokio::select!` with 10-second grace period
- The outbox worker should follow the same shutdown pattern
- **Regression note:** Story 1-8 had 3 test regressions from error propagation changes — be careful when integrating new components into main.rs

**Story 1-3 (ServiceLevel CRD & Controller) — CRD creation pattern:**
- Established the CRD + controller + Helm template pattern used by all subsequent CRDs
- `validate_spec()` as a standalone function (not a method) for testability
- Status patch via `Api::patch_status` with `Patch::Merge`
- Controller requeues every 300s for periodic re-evaluation
- Error policy with 5s fixed retry (later upgraded to exponential backoff in 1-8)

**Story 1-4 (SLO Burn Rate Calculation Engine) — periodic loop pattern:**
- `run_slo_engine()` uses `tokio::time::interval(Duration::from_secs(refresh_secs))`
- The outbox worker should use the same interval pattern for periodic processing

**Epic 1 Retrospective insights:**
- Rust code was never compiled locally due to missing toolchain — same risk applies here
- Code reviews consistently find ~5 issues per story (1 HIGH, 2-3 MEDIUM, 1-2 LOW)
- Adversarial code review is essential — never skip
- Cross-component stories have higher regression risk — but this story is operator-only

### Git Intelligence

- Recent commits: `49d7c7e` (epic-1 retrospective done), `362ed23` (1-8 done), `c6384a8` (implement 1-8)
- This is the FIRST story in Epic 2 — establishes notification infrastructure for all subsequent stories
- Operator-only story: Rust CRD + controller + outbox worker + Helm template
- No Python changes — lowest regression risk

### Project Structure Notes

- `notification_channel.rs` CRD goes in `operator/src/crds/` alongside `servicelevel.rs`, `investigation.rs`, `source.rs`
- `notification_channel.rs` controller goes in `operator/src/controllers/` alongside `servicelevel.rs`
- `notifications/` module is new directory in `operator/src/` — follows same convention as `slo/`, `detection/`, `ingestion/`
- `notification-channel-crd.yaml` goes in `helm/beeper/templates/crds/` alongside `servicelevel-crd.yaml`
- Outbox worker tests use inline `#[cfg(test)] mod tests {}` blocks — same as all operator tests

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.1] — Acceptance criteria and user story
- [Source: _bmad-output/planning-artifacts/architecture.md#New CRD Schemas] — NotificationChannel CRD YAML example (lines 358-378)
- [Source: _bmad-output/planning-artifacts/architecture.md#Notification Engine Architecture] — Durable outbox pattern (lines 571-587)
- [Source: _bmad-output/planning-artifacts/architecture.md#Data Architecture] — notification_outbox collection (lines 324, 410)
- [Source: _bmad-output/planning-artifacts/architecture.md#FR to Structure Mapping] — FR8 file locations (line 1387)
- [Source: _bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure] — notification file paths (lines 954-964, 983-986)
- [Source: _bmad-output/planning-artifacts/architecture.md#API & Communication Patterns] — Notification API endpoints (lines 478-480)
- [Source: _bmad-output/planning-artifacts/prd.md#FR8] — Users can configure outbound notification channels via NotificationChannel CRD
- [Source: _bmad-output/planning-artifacts/prd.md#NFR22] — 1,000+ events/hour throughput
- [Source: _bmad-output/planning-artifacts/prd.md#NFR17] — Zero data loss during restart
- [Source: operator/src/crds/servicelevel.rs] — CRD definition pattern to follow
- [Source: operator/src/controllers/servicelevel.rs] — Controller pattern to follow
- [Source: helm/beeper/templates/crds/servicelevel-crd.yaml] — Helm CRD template pattern to follow
- [Source: operator/src/main.rs] — Controller registration and shutdown pattern
- [Source: _bmad-output/implementation-artifacts/1-8-platform-resilience.md] — Graceful shutdown watch channel pattern
- [Source: _bmad-output/implementation-artifacts/epic-1-retro-2026-03-14.md] — Epic 1 retrospective learnings

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Code review found 6 issues (2 CRITICAL, 3 MEDIUM, 1 LOW). All auto-fixed.
- CRITICAL: `POST /api/v1/notifications/outbox` endpoint was missing (Task 6.1). Added endpoint with `OutboxWriteRequest`/`OutboxWriteResponse` types and tests.
- CRITICAL: Tests for outbox/channel endpoints were missing (Task 6.3). Added serialization/deserialization tests for both endpoint types.
- MEDIUM: `process_pending` was not filtering by `next_retry_at`. Added range filter to Qdrant scroll query.
- MEDIUM: Outbox worker was not awaited during graceful shutdown. Added to grace period block alongside SLO engine.
- MEDIUM: Story File List was empty. Populated below.
- LOW: `_shutdown_rx` renamed to `shutdown_rx` (was misleadingly prefixed with underscore despite being used).

### File List

**New files:**
- `operator/src/crds/notification_channel.rs` — NotificationChannel CRD definition, validation, tests
- `operator/src/controllers/notification_channel.rs` — NotificationChannel controller, error policy, tests
- `operator/src/notifications/mod.rs` — Notification engine module declaration
- `operator/src/notifications/outbox.rs` — Durable outbox worker, backoff, retry logic, tests
- `helm/beeper/templates/crds/notification-channel-crd.yaml` — Helm CRD template

**Modified files:**
- `operator/src/crds/mod.rs` — Export NotificationChannel types
- `operator/src/controllers/mod.rs` — Export run_notificationchannel_controller
- `operator/src/lib.rs` — Add notifications module, re-export types
- `operator/src/main.rs` — Spawn controller + outbox worker, graceful shutdown
- `operator/src/api.rs` — Add POST /api/v1/notifications/outbox + GET /api/v1/notifications/channels endpoints
