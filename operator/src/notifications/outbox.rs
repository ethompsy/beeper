//! Durable notification outbox worker
//!
//! Processes queued notifications from the `notification_outbox` Qdrant collection.
//! Uses a background loop with exponential backoff retry for failed deliveries.
//! Actual channel delivery is a placeholder — implemented in Stories 2-3 through 2-5.

use std::time::Duration;

use serde::{Deserialize, Serialize};
use tokio::sync::watch;
use tracing::{debug, error, info, warn};

/// Error type for outbox operations
#[derive(Debug, thiserror::Error)]
pub enum OutboxError {
    #[error("Qdrant error: {0}")]
    QdrantError(String),

    #[error("Serialization error: {0}")]
    SerializationError(#[from] serde_json::Error),
}

/// Notification event stored in the outbox
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OutboxEntry {
    /// Investigation that triggered the notification
    pub investigation_id: String,

    /// Type of notification event
    pub event_type: String,

    /// Severity level (low, medium, high, critical)
    pub severity: String,

    /// Service name that triggered the event
    pub service: String,

    /// Notification payload (JSON object)
    pub payload: serde_json::Value,

    /// Delivery status: pending, in_progress, delivered, failed
    pub status: String,

    /// Number of delivery attempts
    pub retry_count: u32,

    /// When the notification was created (ISO 8601)
    pub created_at: String,

    /// When the next retry should occur (ISO 8601)
    pub next_retry_at: String,

    /// Error message from last failed delivery attempt
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_error: Option<String>,
}

/// Default processing interval in seconds
const DEFAULT_OUTBOX_INTERVAL_SECS: u64 = 5;

/// Maximum number of delivery retries before marking as failed
const MAX_RETRY_COUNT: u32 = 10;

/// Base delay for exponential backoff (seconds)
const BACKOFF_BASE_SECS: u64 = 30;

/// Maximum delay for exponential backoff (seconds)
const BACKOFF_MAX_SECS: u64 = 3600;

/// Backoff multiplication factor
const BACKOFF_FACTOR: u64 = 2;

/// Background worker that processes the notification outbox
pub struct OutboxWorker {
    endpoint: String,
    client: reqwest::Client,
    collection_ensured: bool,
}

impl OutboxWorker {
    /// Create a new OutboxWorker
    pub fn new(endpoint: String) -> Self {
        Self {
            endpoint: endpoint.trim_end_matches('/').to_string(),
            client: reqwest::Client::new(),
            collection_ensured: false,
        }
    }

    /// Ensure the notification_outbox collection exists (payload-only, no vectors)
    pub async fn ensure_collection(&mut self) -> Result<(), OutboxError> {
        let url = format!("{}/collections/notification_outbox", self.endpoint);

        // Check if collection already exists
        let check = self.client.get(&url).send().await;
        if let Ok(resp) = check {
            if resp.status().is_success() {
                debug!("notification_outbox collection already exists");
                self.collection_ensured = true;
                return Ok(());
            }
        }

        // Create payload-only collection (no vectors)
        let body = serde_json::json!({
            "vectors": {}
        });

        let resp = self
            .client
            .put(&url)
            .json(&body)
            .send()
            .await
            .map_err(|e| OutboxError::QdrantError(format!("Failed to create collection: {}", e)))?;

        if resp.status().is_success() {
            info!("Created notification_outbox collection (payload-only)");
            self.collection_ensured = true;
            Ok(())
        } else {
            let status = resp.status();
            let text = resp
                .text()
                .await
                .unwrap_or_else(|_| "unknown".to_string());
            Err(OutboxError::QdrantError(format!(
                "Failed to create notification_outbox collection: {} - {}",
                status, text
            )))
        }
    }

    /// Write a notification event to the outbox
    pub async fn write_notification(&self, entry: &OutboxEntry) -> Result<(), OutboxError> {
        let url = format!("{}/collections/notification_outbox/points", self.endpoint);

        let point_id = Self::point_id(&entry.investigation_id, &entry.created_at);

        let body = serde_json::json!({
            "points": [
                {
                    "id": point_id,
                    "payload": entry
                }
            ]
        });

        let resp = self
            .client
            .put(&url)
            .json(&body)
            .send()
            .await
            .map_err(|e| OutboxError::QdrantError(format!("Failed to write notification: {}", e)))?;

        if resp.status().is_success() {
            debug!(
                investigation_id = %entry.investigation_id,
                event_type = %entry.event_type,
                "Wrote notification to outbox"
            );
            Ok(())
        } else {
            let status = resp.status();
            let text = resp
                .text()
                .await
                .unwrap_or_else(|_| "unknown".to_string());
            Err(OutboxError::QdrantError(format!(
                "Failed to write notification: {} - {}",
                status, text
            )))
        }
    }

    /// Process pending notifications from the outbox
    ///
    /// Queries for notifications with status="pending", attempts delivery
    /// (placeholder for now), and updates status accordingly.
    pub async fn process_pending(&self) -> Result<u32, OutboxError> {
        let url = format!(
            "{}/collections/notification_outbox/points/scroll",
            self.endpoint
        );

        // Query for pending notifications whose next_retry_at has passed
        let now = chrono::Utc::now().to_rfc3339();
        let body = serde_json::json!({
            "filter": {
                "must": [
                    {
                        "key": "status",
                        "match": { "value": "pending" }
                    },
                    {
                        "key": "next_retry_at",
                        "range": { "lte": now }
                    }
                ]
            },
            "limit": 100,
            "with_payload": true
        });

        let resp = self
            .client
            .post(&url)
            .json(&body)
            .send()
            .await
            .map_err(|e| {
                OutboxError::QdrantError(format!("Failed to query pending notifications: {}", e))
            })?;

        if !resp.status().is_success() {
            let status = resp.status();
            let text = resp
                .text()
                .await
                .unwrap_or_else(|_| "unknown".to_string());
            return Err(OutboxError::QdrantError(format!(
                "Failed to scroll outbox: {} - {}",
                status, text
            )));
        }

        let scroll_result: serde_json::Value = resp
            .json()
            .await
            .map_err(|e| OutboxError::QdrantError(format!("Failed to parse scroll result: {}", e)))?;

        let points = scroll_result["result"]["points"]
            .as_array()
            .map(|arr| arr.len() as u32)
            .unwrap_or(0);

        if points == 0 {
            return Ok(0);
        }

        // Process each pending notification
        if let Some(point_array) = scroll_result["result"]["points"].as_array() {
            for point in point_array {
                let point_id = &point["id"];

                // Placeholder delivery: mark as delivered
                // Actual channel delivery will be implemented in Stories 2-3 through 2-5
                let update_url = format!(
                    "{}/collections/notification_outbox/points/payload",
                    self.endpoint
                );

                let update_body = serde_json::json!({
                    "payload": {
                        "status": "delivered"
                    },
                    "points": [point_id]
                });

                let update_resp = self
                    .client
                    .post(&update_url)
                    .json(&update_body)
                    .send()
                    .await;

                match update_resp {
                    Ok(r) if r.status().is_success() => {
                        debug!(point_id = ?point_id, "Notification marked as delivered");
                    }
                    Ok(r) => {
                        warn!(
                            point_id = ?point_id,
                            status = ?r.status(),
                            "Failed to update notification status"
                        );
                    }
                    Err(e) => {
                        warn!(
                            point_id = ?point_id,
                            error = %e,
                            "Failed to update notification status"
                        );
                    }
                }
            }
        }

        debug!(count = points, "Processed pending notifications");
        Ok(points)
    }

    /// Run the outbox worker as a background loop
    ///
    /// Periodically checks for pending notifications and processes them.
    /// Respects the graceful shutdown signal from the watch channel.
    pub async fn run(&mut self, mut shutdown_rx: watch::Receiver<bool>) -> Result<(), OutboxError> {
        // Ensure collection exists before starting
        self.ensure_collection().await?;

        let interval_secs = get_outbox_interval_secs();
        let mut interval = tokio::time::interval(Duration::from_secs(interval_secs));

        info!(
            interval_secs = interval_secs,
            "Outbox worker started"
        );

        loop {
            tokio::select! {
                _ = interval.tick() => {
                    match self.process_pending().await {
                        Ok(count) => {
                            if count > 0 {
                                info!(processed = count, "Outbox processing cycle complete");
                            }
                        }
                        Err(e) => {
                            error!(error = %e, "Outbox processing cycle failed");
                        }
                    }
                }
                _ = shutdown_rx.changed() => {
                    if *shutdown_rx.borrow() {
                        info!("Outbox worker received shutdown signal");
                        break;
                    }
                }
            }
        }

        info!("Outbox worker stopped");
        Ok(())
    }

    /// Generate deterministic point ID from investigation_id and timestamp
    fn point_id(investigation_id: &str, timestamp: &str) -> u64 {
        use std::collections::hash_map::DefaultHasher;
        use std::hash::{Hash, Hasher};

        let mut hasher = DefaultHasher::new();
        investigation_id.hash(&mut hasher);
        timestamp.hash(&mut hasher);
        "notification".hash(&mut hasher);
        hasher.finish()
    }
}

/// Compute exponential backoff delay for notification retry
pub fn compute_backoff_delay(retry_count: u32) -> Duration {
    let delay = std::cmp::min(
        BACKOFF_BASE_SECS.saturating_mul(BACKOFF_FACTOR.saturating_pow(retry_count)),
        BACKOFF_MAX_SECS,
    );
    Duration::from_secs(delay)
}

/// Check if a notification should be retried based on retry count
pub fn should_retry(retry_count: u32) -> bool {
    retry_count < MAX_RETRY_COUNT
}

/// Get outbox processing interval from environment
fn get_outbox_interval_secs() -> u64 {
    std::env::var("BEEPER_OUTBOX_INTERVAL_SECS")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(DEFAULT_OUTBOX_INTERVAL_SECS)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_outbox_entry_serialization() {
        let entry = OutboxEntry {
            investigation_id: "inv-123".to_string(),
            event_type: "investigation_started".to_string(),
            severity: "high".to_string(),
            service: "payment-service".to_string(),
            payload: serde_json::json!({"summary": "test"}),
            status: "pending".to_string(),
            retry_count: 0,
            created_at: "2026-03-14T12:00:00Z".to_string(),
            next_retry_at: "2026-03-14T12:00:00Z".to_string(),
            last_error: None,
        };

        let json = serde_json::to_string(&entry).unwrap();
        assert!(json.contains("\"investigation_id\":\"inv-123\""));
        assert!(json.contains("\"event_type\":\"investigation_started\""));
        assert!(json.contains("\"severity\":\"high\""));
        assert!(json.contains("\"status\":\"pending\""));
        assert!(json.contains("\"retry_count\":0"));
        assert!(!json.contains("last_error"));
    }

    #[test]
    fn test_outbox_entry_with_error() {
        let entry = OutboxEntry {
            investigation_id: "inv-456".to_string(),
            event_type: "investigation_completed".to_string(),
            severity: "medium".to_string(),
            service: "auth-service".to_string(),
            payload: serde_json::json!({}),
            status: "failed".to_string(),
            retry_count: 3,
            created_at: "2026-03-14T12:00:00Z".to_string(),
            next_retry_at: "2026-03-14T12:30:00Z".to_string(),
            last_error: Some("Connection refused".to_string()),
        };

        let json = serde_json::to_string(&entry).unwrap();
        assert!(json.contains("\"status\":\"failed\""));
        assert!(json.contains("\"retry_count\":3"));
        assert!(json.contains("\"last_error\":\"Connection refused\""));
    }

    #[test]
    fn test_outbox_entry_deserialization() {
        let json = r#"{
            "investigation_id": "inv-789",
            "event_type": "fix_proposed",
            "severity": "critical",
            "service": "api-gateway",
            "payload": {"fix": "restart"},
            "status": "pending",
            "retry_count": 0,
            "created_at": "2026-03-14T12:00:00Z",
            "next_retry_at": "2026-03-14T12:00:00Z"
        }"#;

        let entry: OutboxEntry = serde_json::from_str(json).unwrap();
        assert_eq!(entry.investigation_id, "inv-789");
        assert_eq!(entry.event_type, "fix_proposed");
        assert_eq!(entry.severity, "critical");
        assert_eq!(entry.status, "pending");
        assert!(entry.last_error.is_none());
    }

    #[test]
    fn test_compute_backoff_delay_first_retry() {
        let d = compute_backoff_delay(0);
        // 30 * 2^0 = 30
        assert_eq!(d.as_secs(), 30);
    }

    #[test]
    fn test_compute_backoff_delay_second_retry() {
        let d = compute_backoff_delay(1);
        // 30 * 2^1 = 60
        assert_eq!(d.as_secs(), 60);
    }

    #[test]
    fn test_compute_backoff_delay_third_retry() {
        let d = compute_backoff_delay(2);
        // 30 * 2^2 = 120
        assert_eq!(d.as_secs(), 120);
    }

    #[test]
    fn test_compute_backoff_delay_fourth_retry() {
        let d = compute_backoff_delay(3);
        // 30 * 2^3 = 240
        assert_eq!(d.as_secs(), 240);
    }

    #[test]
    fn test_compute_backoff_delay_capped_at_max() {
        let d = compute_backoff_delay(8);
        // 30 * 2^8 = 7680, capped at 3600
        assert_eq!(d.as_secs(), 3600);
    }

    #[test]
    fn test_compute_backoff_delay_high_retry_stays_capped() {
        let d = compute_backoff_delay(20);
        assert_eq!(d.as_secs(), 3600);
    }

    #[test]
    fn test_should_retry_within_limit() {
        for i in 0..MAX_RETRY_COUNT {
            assert!(should_retry(i), "should_retry({}) returned false", i);
        }
    }

    #[test]
    fn test_should_retry_at_limit() {
        assert!(!should_retry(MAX_RETRY_COUNT));
    }

    #[test]
    fn test_should_retry_over_limit() {
        assert!(!should_retry(MAX_RETRY_COUNT + 1));
    }

    #[test]
    fn test_point_id_deterministic() {
        let id1 = OutboxWorker::point_id("inv-123", "2026-03-14T12:00:00Z");
        let id2 = OutboxWorker::point_id("inv-123", "2026-03-14T12:00:00Z");
        assert_eq!(id1, id2);
    }

    #[test]
    fn test_point_id_different_inputs() {
        let id1 = OutboxWorker::point_id("inv-123", "2026-03-14T12:00:00Z");
        let id2 = OutboxWorker::point_id("inv-456", "2026-03-14T12:00:00Z");
        assert_ne!(id1, id2);
    }

    #[test]
    fn test_point_id_different_timestamps() {
        let id1 = OutboxWorker::point_id("inv-123", "2026-03-14T12:00:00Z");
        let id2 = OutboxWorker::point_id("inv-123", "2026-03-14T13:00:00Z");
        assert_ne!(id1, id2);
    }

    #[test]
    fn test_outbox_error_display() {
        let err = OutboxError::QdrantError("connection failed".to_string());
        assert_eq!(format!("{}", err), "Qdrant error: connection failed");
    }

    #[test]
    fn test_outbox_worker_new() {
        let worker = OutboxWorker::new("http://qdrant:6333".to_string());
        assert_eq!(worker.endpoint, "http://qdrant:6333");
        assert!(!worker.collection_ensured);
    }

    #[test]
    fn test_outbox_worker_new_trims_trailing_slash() {
        let worker = OutboxWorker::new("http://qdrant:6333/".to_string());
        assert_eq!(worker.endpoint, "http://qdrant:6333");
    }
}
