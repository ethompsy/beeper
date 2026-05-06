# Story 3.0e: Fix Investigation Startup Flood

Status: done

## Story

As a **developer**,
I want the EWMA detector to not trigger investigations during cluster startup,
So that the system reaches a stable baseline before creating investigations and the UI isn't flooded with false positives.

## Background

**Origin:** Story 3-0c walkthrough failure (2026-05-06). 23+ investigations were created before otel-demo pods even finished starting.

**Root cause:** `BEEPER_DETECTION_MIN_SAMPLES` defaults to 10. With Prometheus scraping every 15-30s, that's only ~2.5-5 minutes of data. During startup, services going from 0→running creates massive metric shifts that look like anomalies. Each otel-demo service triggers its own investigation since cooldown is per-service.

## Acceptance Criteria

1. **Given** the Beeper operator starts while otel-demo pods are still initializing
   **When** metrics start flowing from partially-started services
   **Then** no investigations are created until the EWMA has a stable baseline (min 5 minutes of data)

2. **Given** the EWMA detector has accumulated enough baseline data
   **When** a genuine anomaly occurs (e.g., via `make demo-fault`)
   **Then** the detector still triggers an investigation within 10 minutes (NFR1 preserved)

3. **Given** default configuration
   **When** the operator starts
   **Then** the default `min_samples` is high enough to prevent startup floods (~20-30 samples, configurable)

## Tasks / Subtasks

- [x] Task 1: Increase `min_samples` default from 10 to 30
  - [x] 1.1 Update default in `operator/src/detection/mod.rs` (`BEEPER_DETECTION_MIN_SAMPLES` default)
  - [x] 1.2 Update default in EWMA constructor if hardcoded elsewhere
  - [x] 1.3 Update any tests that assume `min_samples = 10`

- [x] Task 2: Add startup grace period (optional, evaluate)
  - [x] 2.1 Evaluate whether `min_samples = 30` alone is sufficient (~7.5-15 min warmup) — YES, sufficient
  - [x] 2.2 If not, add `BEEPER_DETECTION_STARTUP_GRACE_SECS` env var with default 300 (5 min) — NOT NEEDED
  - [x] 2.3 Skip all anomaly creation during grace period regardless of sample count — NOT NEEDED

- [x] Task 3: Run tests and verify
  - [x] 3.1 `cargo test --lib` — 578 passed, 0 failed
  - [x] 3.2 `cargo clippy` — clean
  - [x] 3.3 Verify `test_warmup_no_premature_firing` still passes with new defaults — passes

## Dev Notes

### Key Files

- `operator/src/detection/ewma.rs` — EWMA detector, `min_samples` guard at line 75
- `operator/src/detection/mod.rs` — `DetectionConfig`, env var parsing for `BEEPER_DETECTION_MIN_SAMPLES`
- `operator/src/detection/consumer.rs` — Cooldown tracker, fingerprint = service name only

### Detection Config Env Vars

| Parameter | Default | Env Variable |
|-----------|---------|--------------|
| min_samples | 30 | `BEEPER_DETECTION_MIN_SAMPLES` |
| cooldown_secs | 600 | `BEEPER_DETECTION_COOLDOWN_SECS` |
| threshold | 3.0 | `BEEPER_DETECTION_METRIC_THRESHOLD` |

### From Story 3-0c

- 23+ investigations created before otel-demo even started
- UI crowded with investigations at launch
- Cooldown (10 min per-service) doesn't help when 12+ services each trigger simultaneously

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

### Completion Notes List

- Increased `min_samples` default from 10 to 30 in `DetectionConfig::from_env()` and `DetectionConfig::default()`
- Removed dead `EwmaDetector::with_defaults()` method (never used in production; defaults live in `DetectionConfig`)
- Added `test_production_warmup_30_samples` — validates 30-sample warmup window and post-warmup detection
- Updated test assertions for new default value
- Task 2 evaluation: `min_samples=30` gives ~7.5-15 min warmup (at 15-30s scrape intervals), covering typical otel-demo startup. No separate grace period needed — keeps the mechanism simple and configurable via `BEEPER_DETECTION_MIN_SAMPLES` env var.
- 578 tests pass, clippy clean
- Code review fixes applied: behavioral test added (M1), dead code removed (M2), stale docs fixed (L1)

### Change Log

- 2026-05-06: Increased EWMA min_samples default from 10 to 30 to prevent investigation flood at cluster startup

### File List

- `operator/src/detection/mod.rs` — Updated `from_env()` default, `Default` impl, and test assertion
- `operator/src/detection/ewma.rs` — Updated `with_defaults()` doc/value and test assertion
