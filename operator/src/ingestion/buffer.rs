//! Async ingestion buffer for streaming data
//!
//! Provides a bounded async channel for buffering incoming metric and log data.
//! Implements backpressure handling when the buffer is full.

use std::collections::HashMap;
use std::sync::atomic::{AtomicI64, AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::sync::mpsc;
use tracing::{debug, warn};

/// Default buffer capacity (number of items)
pub const DEFAULT_BUFFER_SIZE: usize = 10000;

/// Data types that can be ingested
#[derive(Debug, Clone)]
pub enum IngestionData {
    /// Prometheus metric sample
    Metric(MetricSample),
    /// Loki log entry
    Log(LogEntry),
}

/// A single metric sample from Prometheus
#[derive(Debug, Clone)]
pub struct MetricSample {
    /// Metric name (from __name__ label)
    pub name: String,
    /// Labels associated with the metric
    pub labels: HashMap<String, String>,
    /// Sample value
    pub value: f64,
    /// Timestamp in milliseconds since epoch
    pub timestamp_ms: i64,
}

/// A single log entry from Loki
#[derive(Debug, Clone)]
pub struct LogEntry {
    /// Labels associated with the log stream
    pub labels: HashMap<String, String>,
    /// Log line content
    pub line: String,
    /// Timestamp in nanoseconds since epoch
    pub timestamp_ns: i64,
}

/// Per-source health tracking (FR4)
pub struct SourceHealth {
    /// Total bytes received from this source
    pub bytes_received: AtomicU64,
    /// Count of parse errors from this source
    pub parse_errors: AtomicU64,
    /// Last received timestamp in nanoseconds since epoch
    pub last_received_ns: AtomicI64,
}

impl SourceHealth {
    fn new() -> Self {
        Self {
            bytes_received: AtomicU64::new(0),
            parse_errors: AtomicU64::new(0),
            last_received_ns: AtomicI64::new(0),
        }
    }

    /// Record a successful request (bytes received + update timestamp)
    pub fn record_request(&self, bytes: u64) {
        self.bytes_received.fetch_add(bytes, Ordering::Relaxed);
        let now_ns = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos() as i64;
        self.last_received_ns.store(now_ns, Ordering::Relaxed);
    }

    /// Record a parse error
    pub fn record_parse_error(&self) {
        self.parse_errors.fetch_add(1, Ordering::Relaxed);
    }

    /// Get snapshot of health stats
    pub fn snapshot(&self) -> SourceHealthSnapshot {
        SourceHealthSnapshot {
            bytes_received: self.bytes_received.load(Ordering::Relaxed),
            parse_errors: self.parse_errors.load(Ordering::Relaxed),
            last_received_ns: self.last_received_ns.load(Ordering::Relaxed),
        }
    }
}

/// Immutable snapshot of source health for serialization
#[derive(Debug, Clone)]
pub struct SourceHealthSnapshot {
    pub bytes_received: u64,
    pub parse_errors: u64,
    pub last_received_ns: i64,
}

/// Async buffer for ingestion data with backpressure support
pub struct IngestionBuffer {
    sender: mpsc::Sender<IngestionData>,
    receiver: tokio::sync::Mutex<mpsc::Receiver<IngestionData>>,
    capacity: usize,
    /// Count of items dropped due to buffer overflow
    dropped_count: AtomicU64,
    /// Count of items successfully buffered
    buffered_count: AtomicU64,
    /// Count of metric samples received (across all sources)
    metrics_received: AtomicU64,
    /// Count of log entries received (across all sources)
    logs_received: AtomicU64,
    /// Per-source health tracking
    prometheus_health: SourceHealth,
    loki_health: SourceHealth,
    otlp_health: SourceHealth,
}

impl IngestionBuffer {
    /// Create a new ingestion buffer with the specified capacity
    pub fn new(capacity: usize) -> Self {
        let (sender, receiver) = mpsc::channel(capacity);
        Self {
            sender,
            receiver: tokio::sync::Mutex::new(receiver),
            capacity,
            dropped_count: AtomicU64::new(0),
            buffered_count: AtomicU64::new(0),
            metrics_received: AtomicU64::new(0),
            logs_received: AtomicU64::new(0),
            prometheus_health: SourceHealth::new(),
            loki_health: SourceHealth::new(),
            otlp_health: SourceHealth::new(),
        }
    }

    /// Create a new buffer with default capacity
    pub fn with_default_capacity() -> Self {
        Self::new(DEFAULT_BUFFER_SIZE)
    }

    /// Try to send data to the buffer
    ///
    /// Returns Ok(()) if the data was buffered successfully.
    /// Returns Err(IngestionData) if the buffer is full (for backpressure signaling).
    pub fn try_send(&self, data: IngestionData) -> Result<(), IngestionData> {
        match self.sender.try_send(data) {
            Ok(()) => {
                self.buffered_count.fetch_add(1, Ordering::Relaxed);
                debug!("Data buffered successfully");
                Ok(())
            }
            Err(mpsc::error::TrySendError::Full(data)) => {
                self.dropped_count.fetch_add(1, Ordering::Relaxed);
                let dropped = self.dropped_count.load(Ordering::Relaxed);
                warn!(dropped_count = dropped, "Buffer full, dropping data");
                Err(data)
            }
            Err(mpsc::error::TrySendError::Closed(data)) => {
                // Channel closed, treat as full
                self.dropped_count.fetch_add(1, Ordering::Relaxed);
                warn!("Buffer channel closed");
                Err(data)
            }
        }
    }

    /// Try to send multiple items, returning count of successfully buffered items
    pub fn try_send_batch(&self, items: Vec<IngestionData>) -> usize {
        let mut success_count = 0;
        for item in items {
            if self.try_send(item).is_ok() {
                success_count += 1;
            } else {
                // Once buffer is full, remaining items will also fail
                // but we continue to count them as dropped
                break;
            }
        }
        success_count
    }

    /// Receive the next item from the buffer
    ///
    /// Returns None if the channel is closed.
    pub async fn recv(&self) -> Option<IngestionData> {
        let mut receiver = self.receiver.lock().await;
        receiver.recv().await
    }

    /// Get the buffer capacity
    pub fn capacity(&self) -> usize {
        self.capacity
    }

    /// Get count of dropped items
    pub fn dropped_count(&self) -> u64 {
        self.dropped_count.load(Ordering::Relaxed)
    }

    /// Get count of buffered items
    pub fn buffered_count(&self) -> u64 {
        self.buffered_count.load(Ordering::Relaxed)
    }

    /// Check if buffer is likely full (best-effort check)
    pub fn is_full(&self) -> bool {
        self.sender.capacity() == 0
    }

    /// Record metrics received (call from prometheus handler)
    pub fn record_metrics(&self, count: u64) {
        self.metrics_received.fetch_add(count, Ordering::Relaxed);
    }

    /// Record logs received (call from otlp/loki handlers)
    pub fn record_logs(&self, count: u64) {
        self.logs_received.fetch_add(count, Ordering::Relaxed);
    }

    /// Get total metrics received
    pub fn metrics_received(&self) -> u64 {
        self.metrics_received.load(Ordering::Relaxed)
    }

    /// Get total logs received
    pub fn logs_received(&self) -> u64 {
        self.logs_received.load(Ordering::Relaxed)
    }

    /// Access prometheus source health
    pub fn prometheus_health(&self) -> &SourceHealth {
        &self.prometheus_health
    }

    /// Access loki source health
    pub fn loki_health(&self) -> &SourceHealth {
        &self.loki_health
    }

    /// Access otlp source health
    pub fn otlp_health(&self) -> &SourceHealth {
        &self.otlp_health
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_buffer_send_receive() {
        let buffer = IngestionBuffer::new(10);

        let sample = IngestionData::Metric(MetricSample {
            name: "test_metric".to_string(),
            labels: HashMap::new(),
            value: 42.0,
            timestamp_ms: 1234567890000,
        });

        // Send should succeed
        assert!(buffer.try_send(sample.clone()).is_ok());
        assert_eq!(buffer.buffered_count(), 1);
        assert_eq!(buffer.dropped_count(), 0);

        // Receive should return the item
        let received = buffer.recv().await;
        assert!(received.is_some());
    }

    #[tokio::test]
    async fn test_buffer_overflow() {
        let buffer = IngestionBuffer::new(2);

        let sample = IngestionData::Metric(MetricSample {
            name: "test_metric".to_string(),
            labels: HashMap::new(),
            value: 1.0,
            timestamp_ms: 1234567890000,
        });

        // Fill the buffer
        assert!(buffer.try_send(sample.clone()).is_ok());
        assert!(buffer.try_send(sample.clone()).is_ok());

        // Third send should fail due to buffer full
        assert!(buffer.try_send(sample.clone()).is_err());
        assert_eq!(buffer.dropped_count(), 1);
    }

    #[tokio::test]
    async fn test_buffer_batch_send() {
        let buffer = IngestionBuffer::new(3);

        let items: Vec<IngestionData> = (0..5)
            .map(|i| {
                IngestionData::Metric(MetricSample {
                    name: format!("metric_{}", i),
                    labels: HashMap::new(),
                    value: i as f64,
                    timestamp_ms: 1234567890000,
                })
            })
            .collect();

        // Only 3 should succeed
        let success_count = buffer.try_send_batch(items);
        assert_eq!(success_count, 3);
        assert_eq!(buffer.buffered_count(), 3);
    }

    #[test]
    fn test_default_capacity() {
        let buffer = IngestionBuffer::with_default_capacity();
        assert_eq!(buffer.capacity(), DEFAULT_BUFFER_SIZE);
    }

    #[tokio::test]
    async fn test_log_entry_buffer() {
        let buffer = IngestionBuffer::new(10);

        let log = IngestionData::Log(LogEntry {
            labels: HashMap::from([("app".to_string(), "test".to_string())]),
            line: "test log line".to_string(),
            timestamp_ns: 1234567890000000000,
        });

        assert!(buffer.try_send(log).is_ok());
        assert_eq!(buffer.buffered_count(), 1);
    }

    #[test]
    fn test_metrics_received_counter_increments() {
        let buffer = IngestionBuffer::new(100);
        assert_eq!(buffer.metrics_received(), 0);

        buffer.record_metrics(3);
        assert_eq!(buffer.metrics_received(), 3);

        buffer.record_metrics(2);
        assert_eq!(buffer.metrics_received(), 5);
    }

    #[test]
    fn test_logs_received_counter_increments() {
        let buffer = IngestionBuffer::new(100);
        assert_eq!(buffer.logs_received(), 0);

        buffer.record_logs(2);
        assert_eq!(buffer.logs_received(), 2);

        buffer.record_logs(4);
        assert_eq!(buffer.logs_received(), 6);
    }

    #[test]
    fn test_per_source_health_bytes_tracking() {
        let buffer = IngestionBuffer::new(100);

        buffer.prometheus_health().record_request(512);
        buffer.prometheus_health().record_request(256);
        buffer.otlp_health().record_request(1024);

        let prom = buffer.prometheus_health().snapshot();
        assert_eq!(prom.bytes_received, 768);
        assert_eq!(prom.parse_errors, 0);
        assert!(prom.last_received_ns > 0);

        let otlp = buffer.otlp_health().snapshot();
        assert_eq!(otlp.bytes_received, 1024);

        // Loki untouched
        let loki = buffer.loki_health().snapshot();
        assert_eq!(loki.bytes_received, 0);
        assert_eq!(loki.last_received_ns, 0);
    }

    #[test]
    fn test_per_source_health_parse_errors() {
        let buffer = IngestionBuffer::new(100);

        buffer.loki_health().record_parse_error();
        buffer.loki_health().record_parse_error();
        buffer.prometheus_health().record_parse_error();

        let loki = buffer.loki_health().snapshot();
        assert_eq!(loki.parse_errors, 2);

        let prom = buffer.prometheus_health().snapshot();
        assert_eq!(prom.parse_errors, 1);

        // OTLP untouched
        let otlp = buffer.otlp_health().snapshot();
        assert_eq!(otlp.parse_errors, 0);
    }

    #[test]
    fn test_source_health_last_received_updates() {
        let buffer = IngestionBuffer::new(100);

        let before = buffer.prometheus_health().snapshot().last_received_ns;
        assert_eq!(before, 0);

        buffer.prometheus_health().record_request(100);
        let after = buffer.prometheus_health().snapshot().last_received_ns;
        assert!(
            after > 0,
            "last_received_ns should be set after record_request"
        );
    }
}
