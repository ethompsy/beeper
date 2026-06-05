//! Anomaly detection module
//!
//! Provides continuous monitoring of incoming metric and log streams,
//! detecting anomalous patterns using Exponentially Weighted Moving Average (EWMA).
//! When anomalies are detected, Investigation CRDs are created for further analysis.

pub mod consumer;
pub mod ewma;
pub mod logs;
pub mod metrics;
pub mod types;

pub use consumer::DetectionConsumer;
pub use ewma::EwmaDetector;
pub use types::{AnomalyEvent, AnomalySignal, AnomalyType};

use std::env;

/// Configuration for the detection module, loaded from environment variables.
#[derive(Debug, Clone)]
pub struct DetectionConfig {
    /// Whether detection is enabled
    pub enabled: bool,
    /// EWMA smoothing factor for metrics
    pub metric_alpha: f64,
    /// Stddev multiplier for metric anomalies
    pub metric_threshold: f64,
    /// EWMA smoothing factor for log error rates
    pub log_alpha: f64,
    /// Stddev multiplier for log anomalies
    pub log_threshold: f64,
    /// Minimum data points before detection activates
    pub min_samples: u64,
    /// Seconds between duplicate investigation creations
    pub cooldown_secs: u64,
    /// Maximum tracked metric series
    pub max_metrics: usize,
    /// Maximum tracked services for log detection
    pub max_services: usize,
    /// Sliding window duration in seconds for log error rates
    pub window_secs: u64,
    /// Kubernetes namespace for Investigation CRDs
    pub namespace: String,
    /// Skip anomalies that cannot be attributed to a named service
    /// (`service == "unknown"`). An incident-response investigation that can't
    /// name a service isn't actionable — these are almost always
    /// infrastructure/host metrics with no `service`-identifying label.
    pub skip_unknown_service: bool,
    /// Metric-name prefixes whose anomalies never trigger investigations.
    /// These are observability-stack/host telemetry and *static* runtime config
    /// (collector self-metrics, process stats, heap ceilings), not service-health
    /// SLIs — investigating them is noise. Note: dynamic GC metrics (`jvm_gc_*`,
    /// `dotnet_gc_*`) are deliberately NOT denylisted — heavy GC is a real
    /// incident symptom (stop-the-world pauses → latency → cascading errors), and
    /// Q12 already surfaces it as a per-second rate. Set the env var to an empty
    /// string to disable filtering.
    pub metric_denylist_prefixes: Vec<String>,
    /// Absolute floor on the EWMA effective stddev (Q13b). Suppresses
    /// division-by-near-zero instability on flat/idle streams so a negligible
    /// wobble on a metric whose mean is ~0 is not read as a huge deviation.
    ///
    /// Default `0.0` (off): the floor is **unit-dependent** — the same constant
    /// means very different things for a count/sec rate vs a seconds/sec GC-time
    /// rate vs a bytes gauge — so a non-zero default could blind small-magnitude
    /// signals (e.g. GC pause-time rate). Operators with homogeneous-unit metrics
    /// may opt in via `BEEPER_DETECTION_ABS_STDDEV_FLOOR`. A count-scale value
    /// (e.g. 0.5) preserves GC *frequency* detection (collections/sec is
    /// count-scale) while quieting sub-1/sec idle-counter blips. The general
    /// sparse-near-zero-counter case is tracked as Q13c (per-metric significance
    /// thresholds / temporal persistence), not solvable by a single global floor.
    pub abs_stddev_floor: f64,
    /// Re-open debounce (seconds) after a service's investigation goes terminal
    /// as **Completed**: don't open a fresh investigation for that service until
    /// this long after it resolved. Default 1800 (30 min).
    ///
    /// This is the durable, API-derived re-open debounce (RFC 0001 Phase 1 step
    /// 4): the anchor is the Investigation's `completed_at` in the API, so it
    /// survives operator restart (the in-memory cooldown does not — Q11).
    pub reopen_debounce_secs: u64,
    /// Re-open debounce (seconds) after a service's investigation goes terminal
    /// as **Failed**. Default 3600 (1 h) — deliberately *longer* than the
    /// Completed window: a failed investigation on a persistent (often
    /// non-actionable) signal will just fail again, so we back off harder
    /// instead of re-firing every ~investigation-duration. This breaks the
    /// observed fail→re-fire accumulation (a service re-investigating every
    /// ~30 min for hours).
    pub failed_reopen_debounce_secs: u64,
}

impl DetectionConfig {
    /// Load configuration from environment variables with defaults.
    pub fn from_env() -> Self {
        Self {
            enabled: env_bool("BEEPER_DETECTION_ENABLED", true),
            metric_alpha: env_f64("BEEPER_DETECTION_METRIC_ALPHA", 0.2),
            metric_threshold: env_f64("BEEPER_DETECTION_METRIC_THRESHOLD", 4.0),
            log_alpha: env_f64("BEEPER_DETECTION_LOG_ALPHA", 0.2),
            log_threshold: env_f64("BEEPER_DETECTION_LOG_THRESHOLD", 4.0),
            min_samples: env_u64("BEEPER_DETECTION_MIN_SAMPLES", 30),
            cooldown_secs: env_u64("BEEPER_DETECTION_COOLDOWN_SECS", 600),
            max_metrics: env_usize("BEEPER_DETECTION_MAX_METRICS", 10000),
            max_services: env_usize("BEEPER_DETECTION_MAX_SERVICES", 1000),
            window_secs: env_u64("BEEPER_DETECTION_WINDOW_SECS", 300),
            namespace: env::var("BEEPER_DETECTION_NAMESPACE")
                .unwrap_or_else(|_| "default".to_string()),
            skip_unknown_service: env_bool("BEEPER_DETECTION_SKIP_UNKNOWN_SERVICE", true),
            metric_denylist_prefixes: env_csv(
                "BEEPER_DETECTION_METRIC_DENYLIST",
                DEFAULT_METRIC_DENYLIST,
            ),
            abs_stddev_floor: env_f64("BEEPER_DETECTION_ABS_STDDEV_FLOOR", 0.0),
            reopen_debounce_secs: env_u64("BEEPER_DETECTION_REOPEN_DEBOUNCE_SECS", 1800),
            failed_reopen_debounce_secs: env_u64(
                "BEEPER_DETECTION_FAILED_REOPEN_DEBOUNCE_SECS",
                3600,
            ),
        }
    }
}

impl Default for DetectionConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            metric_alpha: 0.2,
            metric_threshold: 4.0,
            log_alpha: 0.2,
            log_threshold: 4.0,
            min_samples: 30,
            cooldown_secs: 600,
            max_metrics: 10000,
            max_services: 1000,
            window_secs: 300,
            namespace: "default".to_string(),
            skip_unknown_service: true,
            metric_denylist_prefixes: DEFAULT_METRIC_DENYLIST
                .iter()
                .map(|s| s.to_string())
                .collect(),
            abs_stddev_floor: 0.0,
            reopen_debounce_secs: 1800,
            failed_reopen_debounce_secs: 3600,
        }
    }
}

/// Default metric-name prefixes filtered from investigation triggers:
/// observability-stack/host telemetry and *static* runtime config that is not a
/// service-health signal.
///
/// - `system_`, `process_`, `runtime_`, `v8js_` — host/runtime internals.
/// - `otelcol_` — the OpenTelemetry Collector's own self-telemetry (the
///   observability stack, not a monitored service).
/// - `jvm_memory_limit`, `jvm_memory_init` — static heap ceilings/init sizes
///   (config, not dynamic health).
///
/// Deliberately NOT denylisted: `jvm_gc_*` / `dotnet_gc_*` (heavy GC is a real
/// incident symptom — Q12 surfaces it as a rate) and `jvm_memory_used` /
/// `jvm_memory_committed` (a sustained climb is a leak signal).
const DEFAULT_METRIC_DENYLIST: &[&str] = &[
    "system_",
    "v8js_",
    "process_",
    "runtime_",
    "otelcol_",
    "jvm_memory_limit",
    "jvm_memory_init",
];

/// Normalise a service-identifying label value to a bare service name by
/// stripping any `namespace/` prefix. The same logical service can be attributed
/// differently depending on which label carries it — e.g. an OTel-collector
/// metric labels it `service=otel-demo/payment` while the app's own metric uses
/// `service_name=payment`. Collapsing to the last path segment gives one
/// identity (and one cooldown fingerprint) per service.
pub(crate) fn normalize_service(value: &str) -> String {
    value.rsplit('/').next().unwrap_or(value).to_string()
}

#[cfg(test)]
mod normalize_tests {
    use super::normalize_service;

    #[test]
    fn test_normalize_service_strips_namespace_prefix() {
        assert_eq!(normalize_service("otel-demo/payment"), "payment");
        assert_eq!(normalize_service("payment"), "payment");
        assert_eq!(normalize_service("a/b/checkout"), "checkout");
        assert_eq!(normalize_service(""), "");
    }
}

/// Detection statistics shared via atomic counters.
pub struct DetectionStats {
    pub metrics_tracked: std::sync::atomic::AtomicU64,
    pub services_tracked: std::sync::atomic::AtomicU64,
    pub anomalies_detected: std::sync::atomic::AtomicU64,
    pub cooldown_entries: std::sync::atomic::AtomicU64,
    /// Cumulative count of anomaly events suppressed by cooldown (never decreases).
    /// Distinct from `cooldown_entries` which tracks the current SIZE of the cooldown map.
    pub anomalies_suppressed: std::sync::atomic::AtomicU64,
    /// Minimum sample_count() across all active EWMA detectors (metric + log).
    /// Represents conservative warmup progress — 0 until all detectors have data.
    pub ewma_warmup_samples: std::sync::atomic::AtomicU64,
    /// Configured min_samples threshold that detectors must reach before firing.
    pub ewma_warmup_minimum: std::sync::atomic::AtomicU64,
}

impl DetectionStats {
    pub fn new() -> Self {
        use std::sync::atomic::AtomicU64;
        Self {
            metrics_tracked: AtomicU64::new(0),
            services_tracked: AtomicU64::new(0),
            anomalies_detected: AtomicU64::new(0),
            cooldown_entries: AtomicU64::new(0),
            anomalies_suppressed: AtomicU64::new(0),
            ewma_warmup_samples: AtomicU64::new(0),
            ewma_warmup_minimum: AtomicU64::new(0),
        }
    }
}

impl Default for DetectionStats {
    fn default() -> Self {
        Self::new()
    }
}

fn env_bool(key: &str, default: bool) -> bool {
    env::var(key)
        .ok()
        .map(|v| v.eq_ignore_ascii_case("true") || v == "1")
        .unwrap_or(default)
}

fn env_f64(key: &str, default: f64) -> f64 {
    env::var(key)
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(default)
}

fn env_u64(key: &str, default: u64) -> u64 {
    env::var(key)
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(default)
}

fn env_usize(key: &str, default: usize) -> usize {
    env::var(key)
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(default)
}

/// Parse a comma-separated env var into a Vec of trimmed, non-empty strings.
/// If the var is unset, returns `default`. If set to an empty/blank string,
/// returns an empty Vec (i.e. an explicit way to disable the list).
fn env_csv(key: &str, default: &[&str]) -> Vec<String> {
    match env::var(key) {
        Ok(v) => v
            .split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect(),
        Err(_) => default.iter().map(|s| s.to_string()).collect(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let config = DetectionConfig::default();
        assert!(config.enabled);
        assert_eq!(config.metric_alpha, 0.2);
        assert_eq!(config.metric_threshold, 4.0);
        assert_eq!(config.log_alpha, 0.2);
        assert_eq!(config.log_threshold, 4.0);
        assert_eq!(config.min_samples, 30);
        assert_eq!(config.cooldown_secs, 600);
        assert_eq!(config.max_metrics, 10000);
        assert_eq!(config.max_services, 1000);
        assert_eq!(config.window_secs, 300);
        assert_eq!(config.namespace, "default");
        assert!(config.skip_unknown_service);
        assert_eq!(
            config.metric_denylist_prefixes,
            vec![
                "system_",
                "v8js_",
                "process_",
                "runtime_",
                "otelcol_",
                "jvm_memory_limit",
                "jvm_memory_init"
            ]
        );
        assert_eq!(config.abs_stddev_floor, 0.0);
        assert_eq!(config.reopen_debounce_secs, 1800);
        assert_eq!(config.failed_reopen_debounce_secs, 3600);
    }

    #[test]
    fn test_env_csv_parsing() {
        // unset → default
        assert_eq!(
            env_csv("BEEPER_TEST_UNSET_CSV_XYZ", &["a", "b"]),
            vec!["a", "b"]
        );
    }
}
