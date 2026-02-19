//! Anomaly detection types
//!
//! Core types for representing detected anomalies and signals.

use std::fmt;

/// Type of anomaly detected
#[derive(Debug, Clone, PartialEq)]
pub enum AnomalyType {
    /// Metric value spiked above expected range
    MetricSpike,
    /// Metric value dropped below expected range
    MetricDrop,
    /// Error rate for a service spiked
    ErrorRateSpike,
}

impl fmt::Display for AnomalyType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            AnomalyType::MetricSpike => write!(f, "metric_spike"),
            AnomalyType::MetricDrop => write!(f, "metric_drop"),
            AnomalyType::ErrorRateSpike => write!(f, "error_rate_spike"),
        }
    }
}

/// Raw signal from an EWMA detector indicating a statistical anomaly
#[derive(Debug, Clone)]
pub struct AnomalySignal {
    /// Observed value that triggered the anomaly
    pub observed: f64,
    /// Expected value (EWMA mean)
    pub expected: f64,
    /// Standard deviation at the time of detection
    pub stddev: f64,
    /// Deviation in number of standard deviations
    pub deviation: f64,
}

/// Full anomaly event with context for investigation creation
#[derive(Debug, Clone)]
pub struct AnomalyEvent {
    /// Type of anomaly
    pub anomaly_type: AnomalyType,
    /// Source identifier (metric name or service name)
    pub source: String,
    /// Affected service name
    pub service: String,
    /// Human-readable description of the condition
    pub condition: String,
    /// Timestamp of the anomaly (milliseconds since epoch)
    pub timestamp_ms: i64,
    /// Deviation magnitude in standard deviations
    pub deviation: f64,
    /// Additional context lines (e.g., error log lines)
    pub context: Vec<String>,
}

impl fmt::Display for AnomalyEvent {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "{} on {} (service: {}, deviation: {:.1}σ)",
            self.anomaly_type, self.source, self.service, self.deviation
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_anomaly_type_display() {
        assert_eq!(AnomalyType::MetricSpike.to_string(), "metric_spike");
        assert_eq!(AnomalyType::MetricDrop.to_string(), "metric_drop");
        assert_eq!(AnomalyType::ErrorRateSpike.to_string(), "error_rate_spike");
    }

    #[test]
    fn test_anomaly_event_display() {
        let event = AnomalyEvent {
            anomaly_type: AnomalyType::MetricSpike,
            source: "http_requests_total".to_string(),
            service: "frontend".to_string(),
            condition: "Metric spike detected".to_string(),
            timestamp_ms: 1234567890000,
            deviation: 4.5,
            context: vec![],
        };
        assert_eq!(
            event.to_string(),
            "metric_spike on http_requests_total (service: frontend, deviation: 4.5σ)"
        );
    }

    #[test]
    fn test_anomaly_signal_construction() {
        let signal = AnomalySignal {
            observed: 100.0,
            expected: 50.0,
            stddev: 10.0,
            deviation: 5.0,
        };
        assert_eq!(signal.observed, 100.0);
        assert_eq!(signal.expected, 50.0);
        assert_eq!(signal.stddev, 10.0);
        assert_eq!(signal.deviation, 5.0);
    }
}
