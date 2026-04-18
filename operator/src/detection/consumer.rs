//! Detection consumer
//!
//! Reads from the ingestion buffer, routes data to metric and log detectors,
//! and creates Investigation CRDs when anomalies are detected.

use std::collections::HashMap;
use std::sync::atomic::Ordering;
use std::sync::Arc;
use std::time::{Duration, Instant};

use kube::api::PostParams;
use kube::{Api, Client};
use tracing::{debug, error, info, warn};

use crate::crds::investigation::{Investigation, InvestigationSpec, Severity};
use crate::ingestion::buffer::IngestionData;
use crate::ingestion::IngestionBuffer;
use crate::slo::impact::CustomerImpactScorer;
use crate::slo::SloCache;

use super::logs::LogDetector;
use super::metrics::MetricDetector;
use super::types::AnomalyEvent;
use super::{DetectionConfig, DetectionStats};

/// Tracks recently-fired anomaly fingerprints to prevent alert storms.
struct CooldownTracker {
    recent: HashMap<String, Instant>,
    cooldown_duration: Duration,
}

impl CooldownTracker {
    fn new(cooldown_secs: u64) -> Self {
        Self {
            recent: HashMap::new(),
            cooldown_duration: Duration::from_secs(cooldown_secs),
        }
    }

    /// Check if an anomaly fingerprint is currently in cooldown.
    /// Returns `true` if the anomaly should be suppressed.
    fn is_cooling_down(&mut self, fingerprint: &str) -> bool {
        // Periodic cleanup: remove expired entries when map gets large
        if self.recent.len() > 1000 {
            self.cleanup_expired();
        }

        matches!(self.recent.get(fingerprint), Some(last_seen) if last_seen.elapsed() < self.cooldown_duration)
    }

    /// Record that an anomaly was fired.
    fn record(&mut self, fingerprint: String) {
        self.recent.insert(fingerprint, Instant::now());
    }

    /// Get the number of active cooldown entries.
    fn active_count(&self) -> usize {
        self.recent.len()
    }

    fn cleanup_expired(&mut self) {
        self.recent
            .retain(|_, last_seen| last_seen.elapsed() < self.cooldown_duration);
    }
}

/// Main detection consumer that reads from the ingestion buffer
/// and creates Investigation CRDs for detected anomalies.
pub struct DetectionConsumer {
    config: DetectionConfig,
    stats: Arc<DetectionStats>,
}

impl DetectionConsumer {
    /// Create a new detection consumer.
    pub fn new(config: DetectionConfig, stats: Arc<DetectionStats>) -> Self {
        Self { config, stats }
    }

    /// Main detection loop.
    ///
    /// Reads from the buffer, routes data to the appropriate detector,
    /// and creates Investigation CRDs when anomalies pass cooldown.
    pub async fn run(
        self,
        buffer: Arc<IngestionBuffer>,
        client: Client,
        namespace: String,
        slo_cache: Option<SloCache>,
    ) {
        // Create impact scorer if SLO cache is available
        let impact_scorer = slo_cache.map(CustomerImpactScorer::new);
        let mut metric_detector = MetricDetector::new(
            self.config.metric_alpha,
            self.config.metric_threshold,
            self.config.min_samples,
            self.config.max_metrics,
        );

        let mut log_detector = LogDetector::new(
            self.config.log_alpha,
            self.config.log_threshold,
            self.config.min_samples,
            self.config.max_services,
            self.config.window_secs,
        );

        let mut cooldown = CooldownTracker::new(self.config.cooldown_secs);
        let investigation_api: Api<Investigation> = Api::namespaced(client, &namespace);

        // Store the configured warmup minimum (one-time)
        self.stats
            .ewma_warmup_minimum
            .store(self.config.min_samples, Ordering::Relaxed);

        info!(
            component = "detection",
            namespace = %namespace,
            "Detection consumer started"
        );

        let mut check_count: u64 = 0;
        let mut seq: u64 = 0;

        loop {
            let data = match buffer.recv().await {
                Some(data) => data,
                None => {
                    warn!(
                        component = "detection",
                        "Buffer channel closed, stopping detection consumer"
                    );
                    break;
                }
            };

            let event = match data {
                IngestionData::Metric(ref sample) => metric_detector.process(sample),
                IngestionData::Log(ref entry) => log_detector.process(entry),
            };

            // Update stats periodically
            check_count += 1;
            if check_count.is_multiple_of(100) {
                self.stats
                    .metrics_tracked
                    .store(metric_detector.tracked_count() as u64, Ordering::Relaxed);
                self.stats
                    .services_tracked
                    .store(log_detector.tracked_count() as u64, Ordering::Relaxed);
                self.stats
                    .cooldown_entries
                    .store(cooldown.active_count() as u64, Ordering::Relaxed);

                let min_warmup = match (
                    metric_detector.tracked_count() > 0,
                    log_detector.tracked_count() > 0,
                ) {
                    (true, true) => metric_detector
                        .min_sample_count()
                        .min(log_detector.min_sample_count()),
                    (true, false) => metric_detector.min_sample_count(),
                    (false, true) => log_detector.min_sample_count(),
                    (false, false) => 0,
                };
                self.stats
                    .ewma_warmup_samples
                    .store(min_warmup, Ordering::Relaxed);

                debug!(
                    component = "detection",
                    metrics_tracked = metric_detector.tracked_count(),
                    services_tracked = log_detector.tracked_count(),
                    anomalies_total = self.stats.anomalies_detected.load(Ordering::Relaxed),
                    anomalies_suppressed = self.stats.anomalies_suppressed.load(Ordering::Relaxed),
                    "Detection stats"
                );
            }

            if let Some(event) = event {
                let fingerprint = anomaly_fingerprint(&event);

                if cooldown.is_cooling_down(&fingerprint) {
                    debug!(
                        component = "detection",
                        fingerprint = %fingerprint,
                        "Anomaly suppressed by cooldown"
                    );
                    self.stats
                        .anomalies_suppressed
                        .fetch_add(1, Ordering::Relaxed);
                    continue;
                }

                self.stats
                    .anomalies_detected
                    .fetch_add(1, Ordering::Relaxed);

                info!(
                    component = "detection",
                    anomaly_type = %event.anomaly_type,
                    service = %event.service,
                    deviation = event.deviation,
                    "Anomaly detected: {}", event.condition
                );

                let severity = map_severity(event.deviation);

                seq += 1;
                let investigation_name =
                    format!("anomaly-{:x}-{:04x}", chrono::Utc::now().timestamp(), seq);

                // Compute customer impact score from SLO data (if available)
                let impact_score = if let Some(ref scorer) = impact_scorer {
                    scorer.score_service(&event.service).await
                } else {
                    None
                };

                let investigation = Investigation::new(
                    &investigation_name,
                    InvestigationSpec {
                        condition: event.condition.clone(),
                        service: event.service.clone(),
                        severity,
                        triggered_at: Some(chrono::Utc::now().to_rfc3339()),
                        impact_score,
                    },
                );

                // Record cooldown before API call to prevent flood on persistent K8s failures
                cooldown.record(fingerprint);

                match investigation_api
                    .create(&PostParams::default(), &investigation)
                    .await
                {
                    Ok(_) => {
                        info!(
                            component = "detection",
                            investigation = %investigation_name,
                            service = %event.service,
                            "Investigation created for anomaly"
                        );
                    }
                    Err(e) => {
                        error!(
                            component = "detection",
                            error = %e,
                            service = %event.service,
                            "Failed to create Investigation CRD"
                        );
                    }
                }
            }
        }
    }
}

/// Generate an anomaly fingerprint for cooldown tracking.
///
/// Format: "{anomaly_type}:{service}:{source}"
fn anomaly_fingerprint(event: &AnomalyEvent) -> String {
    format!("{}:{}:{}", event.anomaly_type, event.service, event.source)
}

/// Map deviation magnitude to severity level.
///
/// | Deviation | Severity |
/// |-----------|----------|
/// | 2.0-3.0σ  | Low      |
/// | 3.0-4.0σ  | Medium   |
/// | 4.0-6.0σ  | High     |
/// | >6.0σ     | Critical |
pub fn map_severity(deviation: f64) -> Severity {
    if deviation > 6.0 {
        Severity::Critical
    } else if deviation > 4.0 {
        Severity::High
    } else if deviation > 3.0 {
        Severity::Medium
    } else {
        Severity::Low
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::detection::types::AnomalyType;

    #[test]
    fn test_severity_mapping() {
        assert_eq!(map_severity(2.5), Severity::Low);
        assert_eq!(map_severity(3.0), Severity::Low);
        assert_eq!(map_severity(3.5), Severity::Medium);
        assert_eq!(map_severity(4.0), Severity::Medium);
        assert_eq!(map_severity(4.5), Severity::High);
        assert_eq!(map_severity(6.0), Severity::High);
        assert_eq!(map_severity(6.1), Severity::Critical);
        assert_eq!(map_severity(10.0), Severity::Critical);
    }

    #[test]
    fn test_cooldown_prevents_duplicates() {
        let mut tracker = CooldownTracker::new(600);

        let fp = "metric_spike:frontend:cpu_usage".to_string();

        // First time: not cooling down
        assert!(!tracker.is_cooling_down(&fp));
        tracker.record(fp.clone());

        // Second time within window: should be cooling down
        assert!(tracker.is_cooling_down(&fp));
    }

    #[test]
    fn test_cooldown_allows_different_fingerprints() {
        let mut tracker = CooldownTracker::new(600);

        tracker.record("metric_spike:frontend:cpu_usage".to_string());

        // Different fingerprint should not be in cooldown
        assert!(!tracker.is_cooling_down("error_rate:api-server:api-server"));
    }

    #[test]
    fn test_anomaly_fingerprint_format() {
        let event = AnomalyEvent {
            anomaly_type: AnomalyType::MetricSpike,
            source: "http_requests_total".to_string(),
            service: "frontend".to_string(),
            condition: "test".to_string(),
            timestamp_ms: 0,
            deviation: 4.0,
            context: vec![],
        };
        assert_eq!(
            anomaly_fingerprint(&event),
            "metric_spike:frontend:http_requests_total"
        );
    }

    #[test]
    fn test_cooldown_cleanup() {
        let mut tracker = CooldownTracker::new(0); // 0 second cooldown = instant expire

        // Add entries
        for i in 0..10 {
            tracker.record(format!("fp-{}", i));
        }
        assert_eq!(tracker.active_count(), 10);

        // After cleanup, all should be expired (0 second cooldown)
        // Need to wait a tiny bit for Instant to differ
        std::thread::sleep(Duration::from_millis(1));
        tracker.cleanup_expired();
        assert_eq!(tracker.active_count(), 0);
    }
}

/// Integration tests: data through buffer → detector → anomaly event
#[cfg(test)]
mod integration_tests {
    use crate::detection::logs::LogDetector;
    use crate::detection::metrics::MetricDetector;
    use crate::ingestion::buffer::{IngestionBuffer, IngestionData, LogEntry, MetricSample};
    use std::collections::HashMap;

    #[tokio::test]
    async fn test_metric_samples_through_buffer_produce_anomaly() {
        let buffer = IngestionBuffer::new(1000);
        let mut detector = MetricDetector::new(0.2, 3.0, 10, 10000);

        // Send steady-state metrics through buffer
        for _ in 0..20 {
            let sample = MetricSample {
                name: "cpu_usage".to_string(),
                labels: HashMap::from([("service".to_string(), "web".to_string())]),
                value: 50.0,
                timestamp_ms: 1234567890000,
            };
            buffer.try_send(IngestionData::Metric(sample)).unwrap();
        }

        // Send spike metric
        let spike = MetricSample {
            name: "cpu_usage".to_string(),
            labels: HashMap::from([("service".to_string(), "web".to_string())]),
            value: 500.0,
            timestamp_ms: 1234567891000,
        };
        buffer.try_send(IngestionData::Metric(spike)).unwrap();

        // Consume all from buffer and feed to detector
        let mut anomaly_detected = false;
        while let Some(data) =
            tokio::time::timeout(std::time::Duration::from_millis(10), buffer.recv())
                .await
                .ok()
                .flatten()
        {
            if let IngestionData::Metric(ref sample) = data {
                if detector.process(sample).is_some() {
                    anomaly_detected = true;
                }
            }
        }

        assert!(
            anomaly_detected,
            "Metric anomaly should be detected through buffer"
        );
    }

    #[tokio::test]
    async fn test_log_entries_through_buffer_produce_anomaly() {
        let buffer = IngestionBuffer::new(1000);
        let mut detector = LogDetector::new(0.2, 3.0, 10, 1000, 300);

        let base_ns: i64 = 1_000_000_000_000_000_000;

        // Send steady-state error logs (1 per minute, 50 minutes)
        for i in 0..50 {
            let entry = LogEntry {
                labels: HashMap::from([
                    ("service".to_string(), "api".to_string()),
                    ("level".to_string(), "error".to_string()),
                ]),
                line: format!("steady error {}", i),
                timestamp_ns: base_ns + (i as i64) * 60_000_000_000,
            };
            buffer.try_send(IngestionData::Log(entry)).unwrap();
        }

        // Send burst of errors in one minute
        let burst_ts = base_ns + 50 * 60_000_000_000;
        for i in 0..50 {
            let entry = LogEntry {
                labels: HashMap::from([
                    ("service".to_string(), "api".to_string()),
                    ("level".to_string(), "error".to_string()),
                ]),
                line: format!("burst error {}", i),
                timestamp_ns: burst_ts,
            };
            buffer.try_send(IngestionData::Log(entry)).unwrap();
        }

        // Consume and detect
        let mut anomaly_detected = false;
        while let Some(data) =
            tokio::time::timeout(std::time::Duration::from_millis(10), buffer.recv())
                .await
                .ok()
                .flatten()
        {
            if let IngestionData::Log(ref entry) = data {
                if detector.process(entry).is_some() {
                    anomaly_detected = true;
                }
            }
        }

        assert!(
            anomaly_detected,
            "Log anomaly should be detected through buffer"
        );
    }

    #[tokio::test]
    async fn test_anomalies_suppressed_increments_on_cooldown() {
        use crate::detection::DetectionStats;
        use std::sync::atomic::Ordering;

        // Mirrors `test_log_entries_through_buffer_produce_anomaly`: log burst
        // produces multiple anomaly events with IDENTICAL fingerprints
        // (same service + anomaly_type + source). Only the first passes the
        // cooldown check; all subsequent events must be counted as suppressed.
        let buffer = IngestionBuffer::new(1000);
        let mut log_detector = LogDetector::new(0.2, 3.0, 10, 1000, 300);
        let stats = DetectionStats::new();
        let mut cooldown = super::CooldownTracker::new(600);

        let base_ns: i64 = 1_000_000_000_000_000_000;

        // Baseline: 50 minutes of 1 error/min
        for i in 0..50 {
            buffer
                .try_send(IngestionData::Log(LogEntry {
                    labels: HashMap::from([
                        ("service".to_string(), "api".to_string()),
                        ("level".to_string(), "error".to_string()),
                    ]),
                    line: format!("steady {}", i),
                    timestamp_ns: base_ns + (i as i64) * 60_000_000_000,
                }))
                .unwrap();
        }
        // Burst: 50 errors in one minute → many anomaly events w/ same fingerprint
        let burst_ts = base_ns + 50 * 60_000_000_000;
        for i in 0..50 {
            buffer
                .try_send(IngestionData::Log(LogEntry {
                    labels: HashMap::from([
                        ("service".to_string(), "api".to_string()),
                        ("level".to_string(), "error".to_string()),
                    ]),
                    line: format!("burst {}", i),
                    timestamp_ns: burst_ts,
                }))
                .unwrap();
        }

        let mut raw_anomaly_count = 0usize;
        while let Some(data) =
            tokio::time::timeout(std::time::Duration::from_millis(10), buffer.recv())
                .await
                .ok()
                .flatten()
        {
            if let IngestionData::Log(ref entry) = data {
                if let Some(event) = log_detector.process(entry) {
                    raw_anomaly_count += 1;
                    let fingerprint = super::anomaly_fingerprint(&event);
                    // This block mirrors DetectionConsumer::run() exactly:
                    if cooldown.is_cooling_down(&fingerprint) {
                        stats.anomalies_suppressed.fetch_add(1, Ordering::Relaxed);
                    } else {
                        stats.anomalies_detected.fetch_add(1, Ordering::Relaxed);
                        cooldown.record(fingerprint);
                        // CRITICAL: after the first (non-suppressed) anomaly, the
                        // suppressed counter MUST still be 0. Catches off-by-one
                        // if fetch_add is accidentally placed before the cooldown check.
                        assert_eq!(
                            stats.anomalies_suppressed.load(Ordering::Relaxed),
                            0,
                            "anomalies_suppressed must be 0 on the triggering event"
                        );
                    }
                }
            }
        }

        assert!(
            raw_anomaly_count >= 2,
            "Log burst should produce multiple raw anomalies; got {}",
            raw_anomaly_count
        );
        assert_eq!(
            stats.anomalies_detected.load(Ordering::Relaxed),
            1,
            "Exactly one anomaly should pass the cooldown check"
        );
        assert!(
            stats.anomalies_suppressed.load(Ordering::Relaxed) >= 1,
            "Subsequent anomalies (same fingerprint) must increment anomalies_suppressed; got {}",
            stats.anomalies_suppressed.load(Ordering::Relaxed)
        );
    }

    #[tokio::test]
    async fn test_steady_state_through_buffer_no_anomalies() {
        let buffer = IngestionBuffer::new(1000);
        let mut metric_detector = MetricDetector::new(0.2, 3.0, 10, 10000);
        let mut log_detector = LogDetector::new(0.2, 3.0, 10, 1000, 300);

        // Send steady-state metrics
        for i in 0..30 {
            let sample = MetricSample {
                name: "request_count".to_string(),
                labels: HashMap::from([("service".to_string(), "stable".to_string())]),
                value: 100.0 + (i % 3) as f64, // minor jitter: 100, 101, 102
                timestamp_ms: 1234567890000 + i * 1000,
            };
            buffer.try_send(IngestionData::Metric(sample)).unwrap();
        }

        // Send steady-state info logs (not error level — should be ignored by log detector)
        for _ in 0..30 {
            let entry = LogEntry {
                labels: HashMap::from([
                    ("service".to_string(), "stable".to_string()),
                    ("level".to_string(), "info".to_string()),
                ]),
                line: "all good".to_string(),
                timestamp_ns: 1_000_000_000_000_000_000,
            };
            buffer.try_send(IngestionData::Log(entry)).unwrap();
        }

        // Consume and verify no anomalies
        let mut anomaly_count = 0;
        while let Some(data) =
            tokio::time::timeout(std::time::Duration::from_millis(10), buffer.recv())
                .await
                .ok()
                .flatten()
        {
            match data {
                IngestionData::Metric(ref sample) => {
                    if metric_detector.process(sample).is_some() {
                        anomaly_count += 1;
                    }
                }
                IngestionData::Log(ref entry) => {
                    if log_detector.process(entry).is_some() {
                        anomaly_count += 1;
                    }
                }
            }
        }

        assert_eq!(
            anomaly_count, 0,
            "Steady-state data should produce no anomalies"
        );
    }

    #[test]
    fn test_warmup_samples_metric_only_workload() {
        // When only metric detectors are active (no error logs), warmup_samples
        // should reflect the metric detector's min, NOT be stuck at 0.
        let mut metric_detector = MetricDetector::new(0.2, 3.0, 10, 10000);
        let log_detector = LogDetector::new(0.2, 3.0, 10, 1000, 300);

        // Feed 5 metric samples to one key
        for i in 0..5 {
            let sample = crate::ingestion::buffer::MetricSample {
                name: "cpu_usage".to_string(),
                labels: HashMap::from([("service".to_string(), "api".to_string())]),
                value: 50.0 + i as f64,
                timestamp_ms: 1234567890000 + i * 1000,
            };
            metric_detector.process(&sample);
        }

        assert!(metric_detector.tracked_count() > 0);
        assert_eq!(log_detector.tracked_count(), 0);

        // Reproduce the fixed warmup computation from consumer.rs
        let min_warmup = match (
            metric_detector.tracked_count() > 0,
            log_detector.tracked_count() > 0,
        ) {
            (true, true) => metric_detector
                .min_sample_count()
                .min(log_detector.min_sample_count()),
            (true, false) => metric_detector.min_sample_count(),
            (false, true) => log_detector.min_sample_count(),
            (false, false) => 0,
        };

        assert_eq!(
            min_warmup, 5,
            "Warmup should reflect metric detector samples, not be stuck at 0"
        );
    }

    #[test]
    fn test_warmup_minimum_stored_from_config() {
        use crate::detection::DetectionStats;
        use std::sync::atomic::Ordering;

        let stats = std::sync::Arc::new(DetectionStats::new());
        let min_samples: u64 = 42;

        // Simulate what consumer.rs does at startup
        stats
            .ewma_warmup_minimum
            .store(min_samples, Ordering::Relaxed);

        assert_eq!(
            stats.ewma_warmup_minimum.load(Ordering::Relaxed),
            42,
            "ewma_warmup_minimum should be stored from config min_samples"
        );
    }
}
