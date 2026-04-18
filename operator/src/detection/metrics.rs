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
}

impl MetricDetector {
    /// Create a new metric detector.
    pub fn new(alpha: f64, threshold: f64, min_samples: u64, max_tracked: usize) -> Self {
        Self {
            states: HashMap::new(),
            max_tracked,
            alpha,
            threshold,
            min_samples,
        }
    }

    /// Process a metric sample, returning an anomaly event if detected.
    pub fn process(&mut self, sample: &MetricSample) -> Option<AnomalyEvent> {
        let key = MetricKey::from_sample(sample);
        let now = Instant::now();

        // Evict least recently updated if at capacity
        if !self.states.contains_key(&key) && self.states.len() >= self.max_tracked {
            self.evict_oldest();
        }

        let state = self.states.entry(key).or_insert_with(|| MetricState {
            detector: EwmaDetector::new(self.alpha, self.threshold, self.min_samples),
            last_updated: now,
        });
        state.last_updated = now;

        let signal = state.detector.update(sample.value)?;

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
                    return value.clone();
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
        let mut detector = MetricDetector::new(0.2, 3.0, 10, 10000);

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
        let mut detector = MetricDetector::new(0.2, 3.0, 10, 3);

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
        let mut detector = MetricDetector::new(0.2, 3.0, 10, 10000);

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
        let mut detector = MetricDetector::new(0.2, 3.0, 10, 10000);

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
        let mut detector = MetricDetector::new(0.2, 3.0, 100, 10000);

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
        let mut detector = MetricDetector::new(0.2, 3.0, 10, 10000);

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
}
