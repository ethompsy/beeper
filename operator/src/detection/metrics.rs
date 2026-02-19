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

/// Labels to include in metric key (low cardinality, discriminating)
const DISCRIMINATING_LABELS: &[&str] = &["service", "instance", "job", "namespace", "endpoint"];

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

        let service = sample
            .labels
            .get("service")
            .or_else(|| sample.labels.get("app"))
            .or_else(|| sample.labels.get("job"))
            .or_else(|| sample.labels.get("namespace"))
            .cloned()
            .unwrap_or_else(|| "unknown".to_string());

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
        let result =
            detector.process(&make_sample("metric_b", 200.0, vec![("service", "svc-b")]));
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
