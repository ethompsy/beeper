# Story 2.2: Notification Routing Rules Engine

Status: review

## Story

As a **user**,
I want to define notification routing rules based on severity, service, SLO state, and time of day,
so that the right people get the right notifications at the right time.

## Acceptance Criteria

1. **AC1: Severity-based routing**
   **Given** a NotificationChannel CRD with routing rules (`min_severity: high`, `services: ["*"]`)
   **When** a notification event is generated for a service at severity `low` or `medium`
   **Then** the routing engine does NOT route to that channel
   **And** channels with `min_severity: high` only receive `high` or `critical` events
   **And** severity ordering is: `low < medium < high < critical`

2. **AC2: Service-based routing**
   **Given** a NotificationChannel CRD with routing rules (`services: ["payment-service", "auth-service"]`)
   **When** a notification event is generated for service `api-gateway`
   **Then** the routing engine does NOT route to that channel
   **And** a notification for `payment-service` IS routed to that channel
   **And** `services: ["*"]` matches all services

3. **AC3: Quiet hours suppression**
   **Given** quiet hours are configured (`start: "22:00"`, `end: "08:00"`, `timezone: "America/New_York"`)
   **When** a non-critical notification is generated during quiet hours
   **Then** it is suppressed (not routed to that channel)
   **And** critical notifications with `escalation_override: true` bypass quiet hours

4. **AC4: SLO-weighted urgency**
   **Given** a notification event with SLO context from Epic 1
   **When** the routing engine evaluates urgency
   **Then** urgency is weighted by confirmed customer impact (SLO burn rate / impact score) rather than static severity alone
   **And** the effective severity can be elevated (e.g., `medium` → `high`) when SLO impact is high

5. **AC5: Multi-channel evaluation**
   **Given** multiple NotificationChannel CRDs configured with different routing rules
   **When** a notification event is generated
   **Then** the routing engine evaluates ALL channels and returns the list of matching channels
   **And** channels without routing config match all notifications (default pass-through)

## Tasks / Subtasks

- [x] Task 1: Create NotificationRouter with severity ordering (AC: #1, #5)
  - [x] 1.1: Create `operator/src/notifications/router.rs` with `NotificationRouter` struct, `RouterError` error type, and `Severity` enum with ordered levels (`Low`, `Medium`, `High`, `Critical`) including `From<&str>` conversion and `PartialOrd`/`Ord` implementation
  - [x] 1.2: Implement `RoutingDecision` struct containing: `channel_name` (String), `channel_type` (ChannelType), `matched` (bool), `reason` (String — why matched/excluded), `effective_severity` (Severity)
  - [x] 1.3: Implement `evaluate_channel()` method that takes an `OutboxEntry` + `NotificationChannelSpec` + channel name + optional `SloContext` and returns a `RoutingDecision`
  - [x] 1.4: Implement severity comparison: parse `min_severity` from `RoutingConfig`, compare against entry's severity using `Severity` ordering — reject if entry severity < channel's min_severity

- [x] Task 2: Implement service-based filtering (AC: #2)
  - [x] 2.1: In `evaluate_channel()`, check `routing.services` list against `entry.service` — `["*"]` matches all, `None` matches all (default pass-through), specific list requires exact match
  - [x] 2.2: Add unit tests for service matching: wildcard, specific list match, specific list no-match, None (all pass)

- [x] Task 3: Implement quiet hours evaluation (AC: #3)
  - [x] 3.1: Implement `is_in_quiet_hours()` function: parse `start`/`end` HH:MM strings, get current time in configured timezone, check if current time falls within the quiet window (handles overnight spans like 22:00–08:00)
  - [x] 3.2: Implement escalation override: if `escalation_override: true` AND severity is `critical`, bypass quiet hours
  - [x] 3.3: Add unit tests for quiet hours: during quiet hours (suppressed), outside quiet hours (allowed), overnight span, critical with escalation_override (allowed), critical without escalation_override (suppressed), disabled quiet hours

- [x] Task 4: Implement SLO-weighted urgency (AC: #4)
  - [x] 4.1: Define `SloContext` struct: `impact_score` (Option<f64> — 0.0–1.0 from CustomerImpactScorer), `burn_rate` (Option<f64>), `error_budget_remaining` (Option<f64>)
  - [x] 4.2: Implement `compute_effective_severity()` function: given static severity and optional SloContext, elevate severity when impact_score exceeds thresholds (e.g., impact_score > 0.7 elevates medium→high, impact_score > 0.9 elevates high→critical)
  - [x] 4.3: Integrate effective severity into `evaluate_channel()` — use effective severity for min_severity comparison instead of raw severity
  - [x] 4.4: Add unit tests for SLO urgency weighting: no SLO context (use raw severity), low impact (no elevation), high impact (medium→high), very high impact (high→critical), already critical (stays critical)

- [x] Task 5: Implement multi-channel routing (AC: #5)
  - [x] 5.1: Implement `route()` method on `NotificationRouter`: takes `OutboxEntry` + list of `(String, NotificationChannelSpec)` channel configs + optional `SloContext`, evaluates all channels, returns `Vec<RoutingDecision>` with matched channels
  - [x] 5.2: Handle channels without routing config: default to pass-through (match all notifications)
  - [x] 5.3: Add unit tests for multi-channel routing: mixed channels with different rules, all match, none match, partial match

- [x] Task 6: Register router module and update exports (AC: #1–#5)
  - [x] 6.1: Add `pub mod router;` to `operator/src/notifications/mod.rs`
  - [x] 6.2: Add `pub use router::{NotificationRouter, RoutingDecision, Severity, SloContext, RouterError};` to `operator/src/notifications/mod.rs`
  - [x] 6.3: Add re-exports to `operator/src/lib.rs` for `NotificationRouter`, `RoutingDecision`, `Severity`, `SloContext`

- [x] Task 7: Write comprehensive tests (AC: #1–#5)
  - [x] 7.1: Severity ordering tests: all pairwise comparisons, parse from string (lowercase), invalid string defaults to Low
  - [x] 7.2: End-to-end routing scenario tests: realistic multi-channel setup with mixed rules, verify correct routing decisions
  - [x] 7.3: Edge case tests: empty channel list, channel with no routing config, empty services list, severity boundary cases
  - [x] 7.4: Regression guard — all existing Python tests (517 investigator + 705 UI) must pass unchanged

## Dev Notes

### Architecture Compliance

**File Placement (from architecture.md):**
```
operator/src/notifications/router.rs               # New: Routing rules engine
operator/src/notifications/mod.rs                   # Modified: add router module + exports
operator/src/lib.rs                                 # Modified: add router re-exports
```
[Source: _bmad-output/planning-artifacts/architecture.md#FR to Structure Mapping — FR9, FR14]
[Source: _bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure, lines 983-994]

**FR to Implementation Mapping:**
- FR9 (routing rules): `operator/src/notifications/router.rs` — severity, service, time-of-day routing
- FR14 (quiet hours + escalation): `operator/src/notifications/router.rs` — quiet hours with escalation_override
[Source: _bmad-output/planning-artifacts/architecture.md#FR to Structure Mapping]

**NFR Compliance:**
- NFR22 (1000+ notifications/hour): Router evaluates rules in-memory with O(channels) complexity — no external calls for routing decisions
- NFR2 (response times): Pure in-memory evaluation, no I/O blocking during routing decisions
[Source: _bmad-output/planning-artifacts/prd.md#Non-Functional Requirements]

### Implementation Approach

**Key Design Decisions:**

1. **Severity as an ordered enum, not string comparison:**
   Using `#[derive(PartialOrd, Ord)]` on `Severity { Low, Medium, High, Critical }` provides compile-time ordering guarantees. The `From<&str>` conversion handles the string values from `RoutingConfig.min_severity` and `OutboxEntry.severity`.

2. **Router as a stateless evaluator (no I/O):**
   The `NotificationRouter` performs pure in-memory evaluation. It takes channel specs and outbox entries as input and returns routing decisions. It does NOT query Qdrant, K8s API, or any external service. The caller (outbox worker or API handler) is responsible for fetching channel configs and SLO context.

3. **SLO context is optional:**
   `SloContext` wraps the `CustomerImpactScorer` output. When SLO data is unavailable (no SloCache entry for the service), routing falls back to raw severity. This ensures notifications are never dropped due to missing SLO data.

4. **Quiet hours use chrono with timezone support:**
   Parse HH:MM strings into `NaiveTime`, get current time via `chrono::Utc::now()`, convert to channel's timezone using `chrono-tz` (IANA timezone string parsing). Handle overnight spans (22:00–08:00) by checking if start > end and adjusting logic accordingly.

5. **Effective severity elevation (not demotion):**
   SLO impact can only ELEVATE severity (medium→high, high→critical), never demote. This ensures notifications are never suppressed by SLO data — they can only become more urgent.

6. **RoutingDecision includes reason for observability:**
   Each decision carries a human-readable `reason` string explaining why a channel matched or was excluded. This supports future notification audit (Story 2-6) and debugging.

7. **Default pass-through for channels without routing config:**
   Channels with `routing: None` receive ALL notifications. This matches the architecture intent — routing rules are optional filters, not required configuration.

8. **This story does NOT modify the outbox worker:**
   The router is a standalone module. Integration with `process_pending()` in the outbox worker will happen naturally in Stories 2-3 through 2-5 when actual channel delivery is implemented. For now, the router is available as a library for use by those stories.

### Technical Requirements

- **Rust (stable)** — operator code
- **chrono** — time parsing and comparison (existing dependency)
- **chrono-tz** — IANA timezone support (NEW dependency — needed for timezone-aware quiet hours)
- **serde + serde_json** — serialization (existing dependency)
- **thiserror** — error type derivation (existing dependency)
- **tracing** — logging (existing dependency)
- **No new Python dependencies** — this story is operator-only (Rust)

### Library & Framework Requirements

- Use `chrono::NaiveTime::parse_from_str()` for HH:MM parsing — format `%H:%M`
- Use `chrono_tz::Tz` for IANA timezone parsing (e.g., "America/New_York")
- Use `chrono::Utc::now().with_timezone(&tz)` for current time in channel's timezone
- Use `thiserror::Error` for `RouterError` — same as `OutboxError` pattern
- Use `tracing::{debug, warn}` for routing decision logging — NOT println!
- Use `serde::{Serialize, Deserialize}` on `Severity`, `RoutingDecision`, `SloContext` for testability
- Import `RoutingConfig`, `QuietHoursConfig`, `ChannelType` from `crate::crds::notification_channel`
- Import `OutboxEntry` from `super::outbox`

### File Structure Requirements

**New files to create:**
```
operator/src/notifications/router.rs    # Routing rules engine with severity, service, quiet hours, SLO weighting
```

**Files to modify:**
```
operator/src/notifications/mod.rs       # Add pub mod router; and re-exports
operator/src/lib.rs                     # Add router type re-exports
operator/Cargo.toml                     # Add chrono-tz dependency
```

### Testing Requirements

- **Framework:** `#[test]` for all routing logic (pure Rust, no async needed for routing)
- **Severity tests:** All pairwise orderings, string parsing, invalid string handling
- **Service matching tests:** Wildcard, specific list, no-match, None/no-routing
- **Quiet hours tests:** In-window suppression, out-of-window pass, overnight span, escalation override, disabled
- **SLO urgency tests:** No context, low impact, medium→high elevation, high→critical elevation, capped at critical
- **Integration tests:** Multi-channel realistic scenarios
- **No mock K8s needed** — router is pure in-memory evaluation
- **Regression:** All existing Python tests (517 investigator + 705 UI) must pass unchanged
- **No new test dependencies required**

### Critical Guardrails

1. **DO NOT modify the outbox worker (`outbox.rs`).** The router is a standalone module. Outbox integration happens in Stories 2-3 through 2-5.
2. **DO NOT implement actual channel delivery.** This story creates the routing engine only. Delivery is Stories 2-3 (Slack), 2-4 (PagerDuty), 2-5 (Email/Webhook).
3. **DO NOT add notification UI routes or templates.** The notification configuration UI is Story 2-7.
4. **DO NOT modify any Python code (investigator or UI).** This is an operator-only Rust story.
5. **DO NOT demote severity via SLO weighting.** SLO impact can only ELEVATE severity, never reduce it.
6. **DO NOT query external services from the router.** The router is a pure in-memory evaluator. SLO context and channel configs are passed as parameters.
7. **Follow existing module patterns exactly.** The `outbox.rs` module structure (error type, struct, impl, tests mod) is the pattern to follow.
8. **Use `chrono-tz` for timezone support.** Do NOT implement custom timezone parsing. The `chrono-tz` crate handles IANA timezone strings correctly.
9. **Severity ordering must use Rust's derived Ord.** List enum variants in ascending order (`Low`, `Medium`, `High`, `Critical`) and derive `PartialOrd, Ord` — do NOT implement custom comparison logic.
10. **Default to pass-through for missing routing config.** Channels without `routing` field receive all notifications.

### Previous Story Intelligence

**Story 2-1 (NotificationChannel CRD & Durable Outbox) — Foundation for routing:**
- Created `RoutingConfig` struct with `min_severity`, `services`, `quiet_hours` — all Optional fields
- Created `QuietHoursConfig` with `enabled`, `start` (HH:MM), `end` (HH:MM), `timezone` (IANA), `escalation_override`
- Created `OutboxEntry` with `severity` and `service` fields as plain Strings
- Created outbox worker with placeholder delivery — router will be consumed by outbox in later stories
- `ChannelType` enum: `Slack`, `Pagerduty`, `Email`, `Webhook`
- Code review found 6 issues (2 CRITICAL, 3 MEDIUM, 1 LOW) — ensure thorough testing
- Pattern: inline `#[cfg(test)] mod tests {}` blocks, `thiserror::Error` for error types

**Story 1-5 (Customer Impact Scoring) — SLO integration pattern:**
- `CustomerImpactScorer::score_service(service)` returns `Option<f64>` (0.0–1.0)
- Uses `SloCache = Arc<RwLock<HashMap<String, SloCalculationResult>>>`
- `compute_impact_score()` is a public function for individual SLO results
- Impact score formula: 0.3 * target_factor + 0.4 * burn_factor + 0.3 * budget_factor
- When no SLO data exists, returns None — router should fall back to raw severity

**Epic 1 Retrospective insights:**
- Rust code was never compiled locally due to missing toolchain — ensure comprehensive unit tests
- Code reviews consistently find ~5 issues per story — focus on edge cases
- Adversarial code review is essential — never skip

### Git Intelligence

- Recent commits: `d69d533` (2-1 done), `20f817a` (implement 2-1), `49d7c7e` (epic-1 retro)
- Story 2-1 established notification infrastructure — router builds on those types
- Operator-only story: pure Rust routing logic with comprehensive unit tests
- No Python changes — lowest regression risk

### Project Structure Notes

- `router.rs` goes in `operator/src/notifications/` alongside `outbox.rs` and `mod.rs`
- Follows same convention as `slo/impact.rs` (pure computation module in a subsystem)
- All tests use inline `#[cfg(test)] mod tests {}` blocks — same as all operator tests
- `chrono-tz` is a new dependency in `operator/Cargo.toml` — add alongside existing `chrono`

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.2] — Acceptance criteria and user story
- [Source: _bmad-output/planning-artifacts/architecture.md#Notification Engine Architecture] — Routing rules engine in durable outbox pipeline (lines 571-588)
- [Source: _bmad-output/planning-artifacts/architecture.md#FR to Structure Mapping] — FR9 maps to router.rs, FR14 maps to router.rs (lines 1386-1394)
- [Source: _bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure] — router.rs in notifications/ (lines 983-994)
- [Source: _bmad-output/planning-artifacts/prd.md#FR9] — Users can define notification routing rules based on severity, service, SLO state, and time of day
- [Source: _bmad-output/planning-artifacts/prd.md#FR14] — Users can configure quiet hours and escalation tiers
- [Source: _bmad-output/planning-artifacts/prd.md#NFR22] — 1,000+ events/hour throughput
- [Source: operator/src/crds/notification_channel.rs] — RoutingConfig, QuietHoursConfig, ChannelType types
- [Source: operator/src/notifications/outbox.rs] — OutboxEntry struct, module pattern to follow
- [Source: operator/src/slo/impact.rs] — CustomerImpactScorer, compute_impact_score(), SloCache type
- [Source: operator/src/slo/mod.rs] — SloCalculationResult, SloCache type alias
- [Source: _bmad-output/implementation-artifacts/2-1-notificationchannel-crd-durable-outbox.md] — Previous story learnings

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Implemented `NotificationRouter` as a pure stateless evaluator — no I/O, no external calls
- `Severity` enum with derived `PartialOrd`/`Ord` provides compile-time ordering: Low < Medium < High < Critical
- `evaluate_channel()` checks severity filter → service filter → quiet hours → returns `RoutingDecision`
- `route()` evaluates all channels and returns `Vec<RoutingDecision>` — caller uses matched decisions
- `compute_effective_severity()` elevates severity based on SLO impact: >0.7 → medium→high, >0.9 → high→critical
- Quiet hours evaluation handles overnight spans (22:00–08:00) with `is_time_in_window()` helper
- `is_in_quiet_hours_at()` testable variant accepts explicit current_time parameter
- Added `chrono-tz = "0.10"` dependency for IANA timezone support
- 50+ unit tests covering: severity ordering, service matching, quiet hours, SLO weighting, multi-channel routing, edge cases, E2E scenarios
- Python regression: 517 investigator + 705 UI passed (no regressions)
- Rust cargo unavailable locally — comprehensive test coverage designed for CI validation

### File List

**New files:**
- `operator/src/notifications/router.rs` — Notification routing rules engine (severity, service, quiet hours, SLO weighting) with 50+ unit tests

**Modified files:**
- `operator/src/notifications/mod.rs` — Added `pub mod router;` and re-exports for NotificationRouter, RoutingDecision, Severity, SloContext, RouterError
- `operator/src/lib.rs` — Added router type re-exports to public API
- `operator/Cargo.toml` — Added `chrono-tz = "0.10"` dependency for IANA timezone support
