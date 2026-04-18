//! Log anomaly detection
//!
//! Tracks per-service error rates using sliding windows and EWMA
//! to detect error rate spikes.

use std::collections::{HashMap, VecDeque};

use crate::ingestion::buffer::LogEntry;

use super::ewma::EwmaDetector;
use super::types::{AnomalyEvent, AnomalyType};

/// Error-level log labels (case-insensitive match)
const ERROR_LEVELS: &[&str] = &["error", "err", "fatal", "critical", "panic"];

/// Labels to check for service name extraction (in priority order)
const SERVICE_LABELS: &[&str] = &["service", "service_name", "app", "job", "namespace"];

/// Per-service error tracking state
struct ServiceState {
    /// Sliding window of (bucket_start_ms, count) for error rate tracking
    window: VecDeque<(i64, u32)>,
    /// EWMA detector for error rate
    detector: EwmaDetector,
    /// Recent error log lines for context
    context_lines: VecDeque<String>,
}

/// Detects anomalies in log streams by tracking per-service error rates.
pub struct LogDetector {
    /// Per-service error tracking state
    states: HashMap<String, ServiceState>,
    /// Maximum tracked services
    max_services: usize,
    /// Window bucket granularity in milliseconds (1 minute)
    bucket_ms: i64,
    /// Total window duration in milliseconds
    window_ms: i64,
    /// Maximum context lines to retain per service
    max_context_lines: usize,
    /// EWMA smoothing factor
    alpha: f64,
    /// EWMA threshold
    threshold: f64,
    /// Minimum samples before detection
    min_samples: u64,
}

impl LogDetector {
    /// Create a new log detector.
    pub fn new(
        alpha: f64,
        threshold: f64,
        min_samples: u64,
        max_services: usize,
        window_secs: u64,
    ) -> Self {
        Self {
            states: HashMap::new(),
            max_services,
            bucket_ms: 60_000, // 1-minute granularity
            window_ms: (window_secs * 1000) as i64,
            max_context_lines: 5,
            alpha,
            threshold,
            min_samples,
        }
    }

    /// Process a log entry, returning an anomaly event if an error rate spike is detected.
    pub fn process(&mut self, entry: &LogEntry) -> Option<AnomalyEvent> {
        // Only track error-level logs
        if !Self::is_error_log(entry) {
            return None;
        }

        let service = Self::extract_service(entry);
        let timestamp_ms = entry.timestamp_ns / 1_000_000;
        let bucket_start = timestamp_ms - (timestamp_ms % self.bucket_ms);

        // Evict least-recently-seen service if at capacity
        if !self.states.contains_key(&service) && self.states.len() >= self.max_services {
            self.evict_oldest_service();
        }

        let state = self
            .states
            .entry(service.clone())
            .or_insert_with(|| ServiceState {
                window: VecDeque::new(),
                detector: EwmaDetector::new(self.alpha, self.threshold, self.min_samples),
                context_lines: VecDeque::new(),
            });

        // Capture error log line as context
        state.context_lines.push_back(entry.line.clone());
        if state.context_lines.len() > self.max_context_lines {
            state.context_lines.pop_front();
        }

        // Update sliding window: find or create the right bucket
        // (handles out-of-order timestamps by maintaining sorted order)
        match state.window.iter_mut().find(|(ts, _)| *ts == bucket_start) {
            Some((_, count)) => {
                *count += 1;
            }
            None => {
                let pos = state.window.partition_point(|(ts, _)| *ts < bucket_start);
                state.window.insert(pos, (bucket_start, 1));
            }
        }

        // Remove expired buckets (cutoff based on latest bucket, not current entry)
        if let Some(&(latest_ts, _)) = state.window.back() {
            let cutoff = latest_ts - self.window_ms;
            while state.window.front().is_some_and(|(ts, _)| *ts < cutoff) {
                state.window.pop_front();
            }
        }

        // Calculate total error count in window
        let error_count: u32 = state.window.iter().map(|(_, c)| c).sum();

        // Feed error rate to EWMA
        let signal = state.detector.update(error_count as f64)?;

        let context: Vec<String> = state.context_lines.iter().cloned().collect();

        Some(AnomalyEvent {
            anomaly_type: AnomalyType::ErrorRateSpike,
            source: service.clone(),
            service,
            condition: format!(
                "Error rate spike: {} errors in window, expected {:.1} ± {:.1}",
                error_count, signal.expected, signal.stddev
            ),
            timestamp_ms,
            deviation: signal.deviation,
            context,
        })
    }

    /// Get the number of currently tracked services.
    pub fn tracked_count(&self) -> usize {
        self.states.len()
    }

    /// Get the minimum sample count across all tracked log detectors.
    ///
    /// Returns 0 if no services are being tracked.
    pub fn min_sample_count(&self) -> u64 {
        self.states
            .values()
            .map(|s| s.detector.sample_count())
            .min()
            .unwrap_or(0)
    }

    /// Check if a log entry is error-level.
    fn is_error_log(entry: &LogEntry) -> bool {
        entry
            .labels
            .get("level")
            .map(|level| {
                let lower = level.to_ascii_lowercase();
                ERROR_LEVELS.iter().any(|&e| lower == e)
            })
            .unwrap_or(false)
    }

    /// Extract service name from log entry labels.
    fn extract_service(entry: &LogEntry) -> String {
        for &label in SERVICE_LABELS {
            if let Some(value) = entry.labels.get(label) {
                if !value.is_empty() {
                    return value.clone();
                }
            }
        }
        "unknown".to_string()
    }

    /// Evict the service with the oldest last window entry.
    fn evict_oldest_service(&mut self) {
        if let Some(oldest_key) = self
            .states
            .iter()
            .min_by_key(|(_, state)| state.window.back().map_or(i64::MIN, |(ts, _)| *ts))
            .map(|(key, _)| key.clone())
        {
            self.states.remove(&oldest_key);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap as StdHashMap;

    fn make_error_log(
        service_label: &str,
        service_value: &str,
        line: &str,
        ts_ns: i64,
    ) -> LogEntry {
        let mut labels = StdHashMap::new();
        labels.insert(service_label.to_string(), service_value.to_string());
        labels.insert("level".to_string(), "error".to_string());
        LogEntry {
            labels,
            line: line.to_string(),
            timestamp_ns: ts_ns,
        }
    }

    fn make_log_with_level(level: &str, ts_ns: i64) -> LogEntry {
        let mut labels = StdHashMap::new();
        labels.insert("service".to_string(), "test-svc".to_string());
        labels.insert("level".to_string(), level.to_string());
        LogEntry {
            labels,
            line: "test log line".to_string(),
            timestamp_ns: ts_ns,
        }
    }

    #[test]
    fn test_error_rate_spike_detected() {
        let mut detector = LogDetector::new(0.2, 3.0, 10, 1000, 300);

        // Feed steady-state: 1 error per minute for 50 minutes.
        // After ~5 minutes the sliding window stabilizes at ~6 errors,
        // and 44 more constant readings let the EWMA variance decay
        // close to zero, making even a small deviation detectable.
        let base_ns: i64 = 1_000_000_000_000_000_000;
        for i in 0..50 {
            let ts = base_ns + (i as i64) * 60_000_000_000;
            detector.process(&make_error_log("service", "api", "error occurred", ts));
        }

        // Burst: 50 errors in the next minute bucket.
        // Each call adds +1 to the window total, so the EWMA sees 7, 8, 9...
        // With near-zero variance from the stable baseline, the first increment
        // already produces a large deviation.
        let burst_ts = base_ns + 50 * 60_000_000_000;
        let mut detected = false;
        for _ in 0..50 {
            if detector
                .process(&make_error_log("service", "api", "burst error", burst_ts))
                .is_some()
            {
                detected = true;
            }
        }
        assert!(detected, "Error rate spike should be detected");
    }

    #[test]
    fn test_service_extraction_priority() {
        // service label takes priority
        let mut labels = StdHashMap::new();
        labels.insert("service".to_string(), "svc-from-service".to_string());
        labels.insert("app".to_string(), "svc-from-app".to_string());
        labels.insert("level".to_string(), "error".to_string());
        let entry = LogEntry {
            labels,
            line: "test".to_string(),
            timestamp_ns: 1_000_000_000,
        };
        assert_eq!(LogDetector::extract_service(&entry), "svc-from-service");

        // app label if no service
        let mut labels = StdHashMap::new();
        labels.insert("app".to_string(), "svc-from-app".to_string());
        labels.insert("job".to_string(), "svc-from-job".to_string());
        labels.insert("level".to_string(), "error".to_string());
        let entry = LogEntry {
            labels,
            line: "test".to_string(),
            timestamp_ns: 1_000_000_000,
        };
        assert_eq!(LogDetector::extract_service(&entry), "svc-from-app");

        // job label fallback
        let mut labels = StdHashMap::new();
        labels.insert("job".to_string(), "svc-from-job".to_string());
        labels.insert("level".to_string(), "error".to_string());
        let entry = LogEntry {
            labels,
            line: "test".to_string(),
            timestamp_ns: 1_000_000_000,
        };
        assert_eq!(LogDetector::extract_service(&entry), "svc-from-job");

        // unknown fallback
        let mut labels = StdHashMap::new();
        labels.insert("level".to_string(), "error".to_string());
        let entry = LogEntry {
            labels,
            line: "test".to_string(),
            timestamp_ns: 1_000_000_000,
        };
        assert_eq!(LogDetector::extract_service(&entry), "unknown");
    }

    #[test]
    fn test_context_capture() {
        let mut detector = LogDetector::new(0.2, 3.0, 5, 1000, 300);
        let base_ns: i64 = 1_000_000_000_000_000_000;

        // Feed enough errors to pass warmup and trigger
        for i in 0..5 {
            let ts = base_ns + (i as i64) * 60_000_000_000;
            detector.process(&make_error_log(
                "service",
                "api",
                &format!("steady error {}", i),
                ts,
            ));
        }

        // Burst to trigger detection
        let burst_ts = base_ns + 5 * 60_000_000_000;
        let mut event = None;
        for i in 0..30 {
            let result = detector.process(&make_error_log(
                "service",
                "api",
                &format!("burst error {}", i),
                burst_ts,
            ));
            if result.is_some() {
                event = result;
            }
        }

        if let Some(event) = event {
            assert!(
                !event.context.is_empty(),
                "Context should contain error log lines"
            );
            assert!(
                event.context.len() <= 5,
                "Context should be bounded to max_context_lines"
            );
        }
    }

    #[test]
    fn test_non_error_logs_ignored() {
        let mut detector = LogDetector::new(0.2, 3.0, 10, 1000, 300);

        // Info-level logs should be ignored
        let result = detector.process(&make_log_with_level("info", 1_000_000_000));
        assert!(result.is_none());

        // Debug-level logs should be ignored
        let result = detector.process(&make_log_with_level("debug", 1_000_000_000));
        assert!(result.is_none());

        // Warning-level logs should be ignored
        let result = detector.process(&make_log_with_level("warn", 1_000_000_000));
        assert!(result.is_none());

        assert_eq!(
            detector.tracked_count(),
            0,
            "No services should be tracked for non-error logs"
        );
    }

    #[test]
    fn test_error_level_variants_detected() {
        // All error level variants should be recognized
        for level in &[
            "error", "Error", "ERROR", "err", "fatal", "FATAL", "critical", "CRITICAL", "panic",
            "PANIC",
        ] {
            let entry = make_log_with_level(level, 1_000_000_000);
            assert!(
                LogDetector::is_error_log(&entry),
                "Level '{}' should be recognized as error",
                level
            );
        }
    }

    #[test]
    fn test_out_of_order_timestamps() {
        let mut detector = LogDetector::new(0.2, 3.0, 10, 1000, 300);
        let base_ns: i64 = 1_000_000_000_000_000_000;

        // Send entries out of order: minute 3, minute 1, minute 2
        detector.process(&make_error_log(
            "service",
            "api",
            "error 3",
            base_ns + 3 * 60_000_000_000,
        ));
        detector.process(&make_error_log(
            "service",
            "api",
            "error 1",
            base_ns + 1 * 60_000_000_000,
        ));
        detector.process(&make_error_log(
            "service",
            "api",
            "error 2",
            base_ns + 2 * 60_000_000_000,
        ));

        assert_eq!(detector.tracked_count(), 1);

        // Send more entries to verify detector still works normally
        for i in 4..15 {
            detector.process(&make_error_log(
                "service",
                "api",
                &format!("error {}", i),
                base_ns + i * 60_000_000_000,
            ));
        }

        // No panic, no corruption — detector continues operating
        assert_eq!(detector.tracked_count(), 1);
    }

    #[test]
    fn test_service_name_with_underscore() {
        let mut labels = StdHashMap::new();
        labels.insert("service_name".to_string(), "cartservice".to_string());
        labels.insert("level".to_string(), "error".to_string());
        let entry = LogEntry {
            labels,
            line: "test".to_string(),
            timestamp_ns: 1_000_000_000,
        };
        assert_eq!(LogDetector::extract_service(&entry), "cartservice");
    }

    #[test]
    fn test_min_sample_count_returns_minimum() {
        let mut detector = LogDetector::new(0.2, 3.0, 100, 1000, 300);

        // Empty detector returns 0
        assert_eq!(detector.min_sample_count(), 0);

        let base_ns: i64 = 1_000_000_000_000_000_000;

        // Feed 5 error logs to service A
        for i in 0..5 {
            detector.process(&make_error_log(
                "service",
                "svc-a",
                "error",
                base_ns + (i as i64) * 60_000_000_000,
            ));
        }
        assert_eq!(detector.min_sample_count(), 5);

        // Feed 15 error logs to service B — min should still be 5 (from svc-a)
        for i in 0..15 {
            detector.process(&make_error_log(
                "service",
                "svc-b",
                "error",
                base_ns + (i as i64) * 60_000_000_000,
            ));
        }
        assert_eq!(detector.min_sample_count(), 5);
    }

    #[test]
    fn test_bounded_services() {
        let mut detector = LogDetector::new(0.2, 3.0, 10, 3, 300);

        for i in 0..3 {
            detector.process(&make_error_log(
                "service",
                &format!("svc-{}", i),
                "error",
                (i as i64 + 1) * 60_000_000_000,
            ));
        }
        assert_eq!(detector.tracked_count(), 3);

        // Adding a 4th should evict one
        detector.process(&make_error_log(
            "service",
            "svc-new",
            "error",
            4 * 60_000_000_000,
        ));
        assert_eq!(detector.tracked_count(), 3);
    }
}
