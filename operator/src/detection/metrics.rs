//! Metric anomaly detection
//!
//! Tracks per-metric EWMA state and detects anomalous metric patterns.

use std::collections::HashMap;
use std::time::Instant;

use crate::ingestion::buffer::MetricSample;

use super::ewma::EwmaDetector;
use super::types::{AnomalyEvent, AnomalyType};

/// Key for uniquely identifying a metric time series.
///
/// Only includes discriminating labels (not high-cardinality ones like pod_id)
/// to prevent HashMap explosion.
#[derive(Hash, Eq, PartialEq, Clone, Debug)]
struct MetricKey {
    name: String,
    labels: std::collections::BTreeMap<String, String>,
}

/// Labels to include in metric key (low cardinality, discriminating).
///
/// `service_name` MUST be included — the OTel Collector's `prometheusremotewrite`
/// exporter translates resource attribute `service.name` → label `service_name`
/// (dots to underscores). Without it, metrics from different OTel services with
/// the same metric name collide into a single EWMA state, defeating per-service
/// anomaly detection.
const DISCRIMINATING_LABELS: &[&str] = &[
    "service",
    "service_name",
    "instance",
    "job",
    "namespace",
    "endpoint",
];

/// Label keys checked in order when attributing an anomaly to a service.
/// First match wins (matches `logs.rs` behavior).
const SERVICE_LABELS: &[&str] = &["service", "service_name", "app", "job", "namespace"];

impl MetricKey {
    fn from_sample(sample: &MetricSample) -> Self {
        let labels: std::collections::BTreeMap<String, String> = sample
            .labels
            .iter()
            .filter(|(k, _)| DISCRIMINATING_LABELS.contains(&k.as_str()))
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect();

        Self {
            name: sample.name.clone(),
            labels,
        }
    }
}

/// Per-metric EWMA state with last-updated timestamp for eviction.
struct MetricState {
    detector: EwmaDetector,
    last_updated: Instant,
    /// Previous raw sample value — used to compute the per-second rate for
    /// cumulative (counter) series (Q12). `None` until the first sample.
    prev_value: Option<f64>,
    /// Timestamp (ms) of the previous sample, for the rate denominator.
    prev_ts_ms: i64,
}

/// Detects anomalies in metric streams using per-metric EWMA tracking.
pub struct MetricDetector {
    /// Per-metric EWMA state
    states: HashMap<MetricKey, MetricState>,
    /// Maximum number of tracked metrics
    max_tracked: usize,
    /// EWMA smoothing factor
    alpha: f64,
    /// EWMA threshold (stddev multiplier)
    threshold: f64,
    /// Minimum samples before detection
    min_samples: u64,
    /// Metric-name prefixes that are never tracked/triggered (host/runtime noise).
    denylist_prefixes: Vec<String>,
}

impl MetricDetector {
    /// Create a new metric detector.
    pub fn new(
        alpha: f64,
        threshold: f64,
        min_samples: u64,
        max_tracked: usize,
        denylist_prefixes: Vec<String>,
    ) -> Self {
        Self {
            states: HashMap::new(),
            max_tracked,
            alpha,
            threshold,
            min_samples,
            denylist_prefixes,
        }
    }

    /// Returns true if the metric name matches a denylisted prefix.
    fn is_denylisted(&self, name: &str) -> bool {
        self.denylist_prefixes
            .iter()
            .any(|p| name.starts_with(p.as_str()))
    }

    /// Cumulative (monotonic) series — Prometheus counters and the cumulative
    /// parts of histograms/summaries. Detection runs on their per-second RATE,
    /// not the raw value (Q12).
    fn is_cumulative(name: &str) -> bool {
        name.ends_with("_total") || name.ends_with("_count") || name.ends_with("_sum")
    }

    /// Histogram bucket series. Skipped entirely: the `le` label is not part of
    /// `MetricKey`, so every bucket of a histogram collapses into one stream
    /// (a rate would mix buckets), and raw per-bucket counts are not a
    /// service-health signal. These were the bulk of the observed false
    /// anomalies (Q12).
    fn is_histogram_bucket(name: &str) -> bool {
        name.ends_with("_bucket")
    }

    /// Process a metric sample, returning an anomaly event if detected.
    pub fn process(&mut self, sample: &MetricSample) -> Option<AnomalyEvent> {
        // Host/runtime telemetry (system_*, v8js_*, process_*, …) is not a
        // service-health signal — never track or investigate it. Filtering here
        // also keeps these high-cardinality series out of the EWMA state map.
        if self.is_denylisted(&sample.name) {
            return None;
        }
        // Skip histogram buckets (mis-keyed without `le`; not a health signal — Q12).
        if Self::is_histogram_bucket(&sample.name) {
            return None;
        }

        let key = MetricKey::from_sample(sample);
        let now = Instant::now();

        // Evict least recently updated if at capacity
        if !self.states.contains_key(&key) && self.states.len() >= self.max_tracked {
            self.evict_oldest();
        }

        let cumulative = Self::is_cumulative(&sample.name);
        let alpha = self.alpha;
        let threshold = self.threshold;
        let min_samples = self.min_samples;
        let state = self.states.entry(key).or_insert_with(|| MetricState {
            detector: EwmaDetector::new(alpha, threshold, min_samples),
            last_updated: now,
            prev_value: None,
            prev_ts_ms: 0,
        });
        state.last_updated = now;

        // For cumulative (counter) series, detect on the per-second RATE of
        // change, not the raw monotonic value (Q12). Raw counters only grow and
        // reset to 0 on restart, so EWMA on raw values flags normal growth as
        // spikes and restarts as drops.
        let effective_value = if cumulative {
            let prev = state.prev_value;
            let prev_ts = state.prev_ts_ms;
            state.prev_value = Some(sample.value);
            state.prev_ts_ms = sample.timestamp_ms;
            match prev {
                None => return None, // need two points for a rate
                Some(pv) => {
                    if sample.value < pv {
                        return None; // counter reset (e.g. pod restart) — not an anomaly
                    }
                    let dt_s = (sample.timestamp_ms - prev_ts) as f64 / 1000.0;
                    if dt_s <= 0.0 {
                        return None; // out-of-order / duplicate timestamp
                    }
                    (sample.value - pv) / dt_s
                }
            }
        } else {
            sample.value
        };

        let signal = state.detector.update(effective_value)?;

        let anomaly_type = if signal.observed > signal.expected {
            AnomalyType::MetricSpike
        } else {
            AnomalyType::MetricDrop
        };

        let service = Self::extract_service(sample);

        Some(AnomalyEvent {
            anomaly_type,
            source: sample.name.clone(),
            service,
            condition: format!(
                "Metric {} {}: {:.1}, expected {:.1} ± {:.1}",
                sample.name,
                if signal.observed > signal.expected {
                    "spike"
                } else {
                    "drop"
                },
                signal.observed,
                signal.expected,
                signal.stddev
            ),
            timestamp_ms: sample.timestamp_ms,
            deviation: signal.deviation,
            context: vec![],
        })
    }

    /// Get the number of currently tracked metrics.
    pub fn tracked_count(&self) -> usize {
        self.states.len()
    }

    /// Get the minimum sample count across all tracked metric detectors.
    ///
    /// Returns 0 if no metrics are being tracked.
    pub fn min_sample_count(&self) -> u64 {
        self.states
            .values()
            .map(|s| s.detector.sample_count())
            .min()
            .unwrap_or(0)
    }

    /// Extract service name from metric sample labels.
    ///
    /// Iterates `SERVICE_LABELS` in order and returns the first matching label's value.
    /// Falls back to `"unknown"` if no service-identifying label is present.
    fn extract_service(sample: &MetricSample) -> String {
        for &label in SERVICE_LABELS {
            if let Some(value) = sample.labels.get(label) {
                if !value.is_empty() {
                    return super::normalize_service(value);
                }
            }
        }
        "unknown".to_string()
    }

    /// Evict the least recently updated metric entry.
    fn evict_oldest(&mut self) {
        if let Some(oldest_key) = self
            .states
            .iter()
            .min_by_key(|(_, state)| state.last_updated)
            .map(|(key, _)| key.clone())
        {
            self.states.remove(&oldest_key);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_sample(name: &str, value: f64, labels: Vec<(&str, &str)>) -> MetricSample {
        MetricSample {
            name: name.to_string(),
            labels: labels
                .into_iter()
                .map(|(k, v)| (k.to_string(), v.to_string()))
                .collect(),
            value,
            timestamp_ms: 1234567890000,
        }
    }

    #[test]
    fn test_processes_multiple_metrics_independently() {
        let mut detector = MetricDetector::new(0.2, 3.0, 10, 10000, vec![]);

        // Feed steady state for metric_a
        for _ in 0..20 {
            detector.process(&make_sample("metric_a", 50.0, vec![("service", "svc-a")]));
        }
        // Feed steady state for metric_b at a different level
        for _ in 0..20 {
            detector.process(&make_sample("metric_b", 200.0, vec![("service", "svc-b")]));
        }

        // Spike metric_a — should detect
        let result = detector.process(&make_sample("metric_a", 500.0, vec![("service", "svc-a")]));
        assert!(result.is_some(), "Spike on metric_a should be detected");

        // Normal value for metric_b — should not detect
        let result = detector.process(&make_sample("metric_b", 200.0, vec![("service", "svc-b")]));
        assert!(result.is_none(), "Normal metric_b should not trigger");
    }

    #[test]
    fn test_bounded_hashmap_eviction() {
        let mut detector = MetricDetector::new(0.2, 3.0, 10, 3, vec![]);

        // Add 3 metrics to fill capacity
        detector.process(&make_sample("m1", 1.0, vec![]));
        detector.process(&make_sample("m2", 2.0, vec![]));
        detector.process(&make_sample("m3", 3.0, vec![]));
        assert_eq!(detector.tracked_count(), 3);

        // Adding a 4th should evict one
        detector.process(&make_sample("m4", 4.0, vec![]));
        assert_eq!(detector.tracked_count(), 3);
    }

    #[test]
    fn test_service_extraction_with_app_label() {
        let mut detector = MetricDetector::new(0.2, 3.0, 10, 10000, vec![]);

        // app label should be used when service is not present
        for _ in 0..20 {
            detector.process(&make_sample("cpu", 50.0, vec![("app", "my-app")]));
        }
        let event = detector
            .process(&make_sample("cpu", 500.0, vec![("app", "my-app")]))
            .expect("Should detect anomaly");
        assert_eq!(event.service, "my-app");
    }

    #[test]
    fn test_service_name_label_extraction() {
        // OTel Collector translates resource attribute `service.name` → label `service_name`.
        // `extract_service` must recognize it.
        let sample = make_sample("cpu", 50.0, vec![("service_name", "payment")]);
        assert_eq!(MetricDetector::extract_service(&sample), "payment");

        // Precedence: when BOTH `service` and `service_name` are present,
        // `service` wins (first-match in SERVICE_LABELS order — identical to logs.rs).
        let sample = make_sample(
            "cpu",
            50.0,
            vec![("service", "frontend"), ("service_name", "payment")],
        );
        assert_eq!(MetricDetector::extract_service(&sample), "frontend");

        // Fallback chain: app > job > namespace.
        let sample = make_sample("cpu", 50.0, vec![("app", "my-app"), ("job", "my-job")]);
        assert_eq!(MetricDetector::extract_service(&sample), "my-app");

        // Empty service label should be skipped, falling through to service_name.
        let sample = make_sample(
            "cpu",
            50.0,
            vec![("service", ""), ("service_name", "payment")],
        );
        assert_eq!(MetricDetector::extract_service(&sample), "payment");

        // Unknown when no service-identifying label is present.
        let sample = make_sample("cpu", 50.0, vec![("instance", "pod-xyz")]);
        assert_eq!(MetricDetector::extract_service(&sample), "unknown");
    }

    #[test]
    fn test_service_name_produces_independent_detectors() {
        // Two samples with different `service_name` values MUST produce separate
        // MetricKey entries. Without `service_name` in DISCRIMINATING_LABELS,
        // payment + frontend metrics of the same name collapse into one EWMA state.
        let mut detector = MetricDetector::new(0.2, 3.0, 10, 10000, vec![]);

        detector.process(&make_sample(
            "http_requests_total",
            50.0,
            vec![("service_name", "payment")],
        ));
        detector.process(&make_sample(
            "http_requests_total",
            200.0,
            vec![("service_name", "frontend")],
        ));

        assert_eq!(
            detector.tracked_count(),
            2,
            "Two distinct service_name values must produce independent MetricKeys"
        );
    }

    #[test]
    fn test_min_sample_count_returns_minimum() {
        let mut detector = MetricDetector::new(0.2, 3.0, 100, 10000, vec![]);

        // Empty detector returns 0
        assert_eq!(detector.min_sample_count(), 0);

        // Feed 5 samples to key A
        for _ in 0..5 {
            detector.process(&make_sample("metric_a", 50.0, vec![("service", "svc-a")]));
        }
        assert_eq!(detector.min_sample_count(), 5);

        // Feed 15 samples to key B — min should still be 5 (from key A)
        for _ in 0..15 {
            detector.process(&make_sample("metric_b", 100.0, vec![("service", "svc-b")]));
        }
        assert_eq!(detector.min_sample_count(), 5);
    }

    #[test]
    fn test_anomaly_event_fields() {
        let mut detector = MetricDetector::new(0.2, 3.0, 10, 10000, vec![]);

        let labels = vec![("service", "frontend"), ("instance", "web-1")];

        // Build baseline
        for _ in 0..20 {
            detector.process(&make_sample("cpu_usage", 50.0, labels.clone()));
        }

        // Trigger anomaly
        let event = detector
            .process(&make_sample("cpu_usage", 300.0, labels.clone()))
            .expect("Should detect anomaly");

        assert_eq!(event.source, "cpu_usage");
        assert_eq!(event.service, "frontend");
        assert_eq!(event.anomaly_type, AnomalyType::MetricSpike);
        assert!(event.deviation > 3.0);
        assert!(event.condition.contains("cpu_usage"));
        assert!(event.condition.contains("spike"));
    }

    #[test]
    fn test_denylisted_metrics_never_trigger() {
        // Host/runtime metrics matching a denylist prefix must never produce an
        // anomaly, even on a large spike — and must not be tracked at all.
        let denylist = vec!["system_".to_string(), "v8js_".to_string()];
        let mut detector = MetricDetector::new(0.2, 3.0, 10, 10000, denylist);

        for _ in 0..20 {
            detector.process(&make_sample(
                "v8js_gc_duration_seconds",
                50.0,
                vec![("service", "frontend")],
            ));
        }
        let result = detector.process(&make_sample(
            "v8js_gc_duration_seconds",
            5000.0,
            vec![("service", "frontend")],
        ));
        assert!(result.is_none(), "denylisted metric must not trigger");
        assert_eq!(
            detector.tracked_count(),
            0,
            "denylisted metric must not be tracked"
        );

        // A non-denylisted metric on the same detector still works.
        for _ in 0..20 {
            detector.process(&make_sample(
                "http_errors",
                1.0,
                vec![("service", "frontend")],
            ));
        }
        let ok = detector.process(&make_sample(
            "http_errors",
            500.0,
            vec![("service", "frontend")],
        ));
        assert!(ok.is_some(), "non-denylisted metric should still trigger");
    }

    // --- Q12: rate-based detection for cumulative metrics ---

    fn cumulative_sample(name: &str, value: f64, ts_ms: i64) -> MetricSample {
        MetricSample {
            name: name.to_string(),
            labels: [("service".to_string(), "payment".to_string())]
                .into_iter()
                .collect(),
            value,
            timestamp_ms: ts_ms,
        }
    }

    #[test]
    fn test_cumulative_steady_rate_no_false_positive() {
        // A counter increasing at a CONSTANT rate (+100/s) must NOT fire — its
        // raw value grows monotonically, but its RATE is steady. (Old behaviour:
        // EWMA on the raw growing value flagged it as a perpetual spike → Q12.)
        let mut detector = MetricDetector::new(0.2, 4.0, 10, 10000, vec![]);
        let mut v = 0.0;
        let mut fired = 0;
        for i in 0..60 {
            v += 100.0; // +100 every 1000ms = 100/s, constant
            if detector
                .process(&cumulative_sample("requests_total", v, i * 1000))
                .is_some()
            {
                fired += 1;
            }
        }
        assert_eq!(fired, 0, "a steady counter rate must not fire");
    }

    #[test]
    fn test_cumulative_rate_spike_fires() {
        let mut detector = MetricDetector::new(0.2, 4.0, 10, 10000, vec![]);
        let mut v = 0.0;
        let mut ts = 0i64;
        for _ in 0..30 {
            v += 100.0;
            ts += 1000;
            detector.process(&cumulative_sample("requests_total", v, ts));
        }
        // A sudden 50x jump in the per-interval increase = rate spike.
        v += 5000.0;
        ts += 1000;
        let signal = detector.process(&cumulative_sample("requests_total", v, ts));
        assert!(signal.is_some(), "a real rate spike on a counter must fire");
    }

    #[test]
    fn test_counter_reset_no_false_positive() {
        // A counter reset (value drops, e.g. pod restart) must NOT fire.
        let mut detector = MetricDetector::new(0.2, 4.0, 10, 10000, vec![]);
        let mut v = 0.0;
        let mut ts = 0i64;
        for _ in 0..40 {
            v += 100.0;
            ts += 1000;
            detector.process(&cumulative_sample("requests_total", v, ts));
        }
        // Reset to a small value (counter restarted).
        ts += 1000;
        let signal = detector.process(&cumulative_sample("requests_total", 5.0, ts));
        assert!(signal.is_none(), "a counter reset must not fire (Q12)");
    }

    #[test]
    fn test_histogram_bucket_skipped() {
        // _bucket series are skipped entirely (mis-keyed without `le`; noise).
        let mut detector = MetricDetector::new(0.2, 4.0, 10, 10000, vec![]);
        for i in 0..40 {
            let s = cumulative_sample(
                "http_server_duration_seconds_bucket",
                (i as f64) * 7.0,
                i * 1000,
            );
            assert!(detector.process(&s).is_none());
        }
        assert_eq!(
            detector.tracked_count(),
            0,
            "histogram buckets must not be tracked or fire"
        );
    }
}
