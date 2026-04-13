//! Durable notification outbox worker
//!
//! Processes queued notifications from the `notification_outbox` Qdrant collection.
//! Uses a background loop with exponential backoff retry for failed deliveries.
//! Delivers to channels via the UI service delivery endpoint (POST /api/v1/notifications/deliver).

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

/// Response from the UI delivery endpoint
#[derive(Debug, Deserialize)]
pub struct DeliveryResponse {
    /// Delivery status: delivered, failed, skipped
    pub status: String,

    /// Error message if delivery failed
    #[serde(default)]
    pub error: Option<String>,

    /// Whether the error is retryable
    #[serde(default)]
    pub retryable: bool,

    /// Slack thread timestamp (for threading follow-up messages)
    #[serde(default)]
    pub thread_ts: Option<String>,
}

/// Background worker that processes the notification outbox
pub struct OutboxWorker {
    endpoint: String,
    ui_endpoint: String,
    client: reqwest::Client,
    collection_ensured: bool,
}

impl OutboxWorker {
    /// Create a new OutboxWorker
    pub fn new(endpoint: String) -> Self {
        let ui_endpoint = get_ui_endpoint();
        Self {
            endpoint: endpoint.trim_end_matches('/').to_string(),
            ui_endpoint,
            client: reqwest::Client::new(),
            collection_ensured: false,
        }
    }

    /// Create a new OutboxWorker with explicit UI endpoint
    pub fn new_with_ui(endpoint: String, ui_endpoint: String) -> Self {
        Self {
            endpoint: endpoint.trim_end_matches('/').to_string(),
            ui_endpoint: ui_endpoint.trim_end_matches('/').to_string(),
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
            let text = resp.text().await.unwrap_or_else(|_| "unknown".to_string());
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
                    "vector": {},
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
            .map_err(|e| {
                OutboxError::QdrantError(format!("Failed to write notification: {}", e))
            })?;

        if resp.status().is_success() {
            debug!(
                investigation_id = %entry.investigation_id,
                event_type = %entry.event_type,
                "Wrote notification to outbox"
            );
            Ok(())
        } else {
            let status = resp.status();
            let text = resp.text().await.unwrap_or_else(|_| "unknown".to_string());
            Err(OutboxError::QdrantError(format!(
                "Failed to write notification: {} - {}",
                status, text
            )))
        }
    }

    /// Process pending notifications from the outbox
    ///
    /// Queries for notifications with status="pending", delivers via the UI
    /// service delivery endpoint, and updates status accordingly.
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
            let text = resp.text().await.unwrap_or_else(|_| "unknown".to_string());
            return Err(OutboxError::QdrantError(format!(
                "Failed to scroll outbox: {} - {}",
                status, text
            )));
        }

        let scroll_result: serde_json::Value = resp.json().await.map_err(|e| {
            OutboxError::QdrantError(format!("Failed to parse scroll result: {}", e))
        })?;

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
                let payload = &point["payload"];

                // Deliver via UI service endpoint
                let delivery_result = self.deliver_via_ui(payload).await;

                let update_url = format!(
                    "{}/collections/notification_outbox/points/payload",
                    self.endpoint
                );

                let update_body = match &delivery_result {
                    Ok(resp) if resp.status == "delivered" => {
                        // Store thread_ts in payload for future threading
                        let mut update_payload = serde_json::json!({
                            "status": "delivered"
                        });
                        if let Some(thread_ts) = &resp.thread_ts {
                            update_payload["payload"] = serde_json::json!({
                                "slack_thread_ts": thread_ts
                            });
                        }
                        serde_json::json!({
                            "payload": update_payload,
                            "points": [point_id]
                        })
                    }
                    Ok(resp) if resp.status == "skipped" => {
                        // Channel type not yet implemented, mark delivered to avoid retry loop
                        debug!(
                            point_id = ?point_id,
                            reason = ?resp.error,
                            "Notification delivery skipped (channel not yet implemented)"
                        );
                        serde_json::json!({
                            "payload": { "status": "delivered" },
                            "points": [point_id]
                        })
                    }
                    Ok(resp) => {
                        // Failed delivery — check retryable and update accordingly
                        let retry_count = payload
                            .get("retry_count")
                            .and_then(|v| v.as_u64())
                            .unwrap_or(0) as u32;

                        if resp.retryable && should_retry(retry_count + 1) {
                            let next_delay = compute_backoff_delay(retry_count + 1);
                            let next_retry = chrono::Utc::now()
                                + chrono::Duration::seconds(next_delay.as_secs() as i64);
                            warn!(
                                point_id = ?point_id,
                                retry_count = retry_count + 1,
                                next_retry = %next_retry.to_rfc3339(),
                                error = ?resp.error,
                                "Notification delivery failed, scheduling retry"
                            );
                            serde_json::json!({
                                "payload": {
                                    "status": "pending",
                                    "retry_count": retry_count + 1,
                                    "next_retry_at": next_retry.to_rfc3339(),
                                    "last_error": resp.error.as_deref().unwrap_or("unknown error")
                                },
                                "points": [point_id]
                            })
                        } else {
                            warn!(
                                point_id = ?point_id,
                                error = ?resp.error,
                                "Notification delivery permanently failed"
                            );
                            serde_json::json!({
                                "payload": {
                                    "status": "failed",
                                    "last_error": resp.error.as_deref().unwrap_or("unknown error")
                                },
                                "points": [point_id]
                            })
                        }
                    }
                    Err(e) => {
                        // Network error reaching UI service — retryable
                        let retry_count = payload
                            .get("retry_count")
                            .and_then(|v| v.as_u64())
                            .unwrap_or(0) as u32;

                        if should_retry(retry_count + 1) {
                            let next_delay = compute_backoff_delay(retry_count + 1);
                            let next_retry = chrono::Utc::now()
                                + chrono::Duration::seconds(next_delay.as_secs() as i64);
                            warn!(
                                point_id = ?point_id,
                                retry_count = retry_count + 1,
                                error = %e,
                                "UI delivery endpoint unreachable, scheduling retry"
                            );
                            serde_json::json!({
                                "payload": {
                                    "status": "pending",
                                    "retry_count": retry_count + 1,
                                    "next_retry_at": next_retry.to_rfc3339(),
                                    "last_error": format!("UI service error: {}", e)
                                },
                                "points": [point_id]
                            })
                        } else {
                            serde_json::json!({
                                "payload": {
                                    "status": "failed",
                                    "last_error": format!("UI service error: {}", e)
                                },
                                "points": [point_id]
                            })
                        }
                    }
                };

                let update_resp = self
                    .client
                    .post(&update_url)
                    .json(&update_body)
                    .send()
                    .await;

                match update_resp {
                    Ok(r) if r.status().is_success() => {
                        debug!(point_id = ?point_id, "Notification status updated");
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

    /// Deliver a notification via the UI service delivery endpoint.
    ///
    /// Expected payload schema (fields read from outbox entry payload):
    /// - `investigation_id`: String — investigation that triggered the notification
    /// - `event_type`: String — notification event type
    /// - `severity`: String — severity level (defaults to "low")
    /// - `service`: String — service name
    /// - `payload`: Object — nested notification payload (evidence, summary, etc.)
    /// - `channel_type`: String — delivery channel type (defaults to "slack")
    /// - `channel_config`: Object — channel-specific config (e.g., `{"channel": "#sre-alerts"}`)
    /// - `credentials_secret`: String — K8s Secret name for channel credentials
    ///
    /// NOTE: Channel config and routing are currently passed through from the outbox
    /// entry payload. Future work should query K8s NotificationChannel CRDs and call
    /// `NotificationRouter::route()` here to determine target channels dynamically.
    async fn deliver_via_ui(
        &self,
        payload: &serde_json::Value,
    ) -> Result<DeliveryResponse, OutboxError> {
        let delivery_url = format!("{}/api/v1/notifications/deliver", self.ui_endpoint);

        // Build the delivery request body
        let entry = serde_json::json!({
            "investigation_id": payload.get("investigation_id").and_then(|v| v.as_str()).unwrap_or(""),
            "event_type": payload.get("event_type").and_then(|v| v.as_str()).unwrap_or(""),
            "severity": payload.get("severity").and_then(|v| v.as_str()).unwrap_or("low"),
            "service": payload.get("service").and_then(|v| v.as_str()).unwrap_or(""),
            "payload": payload.get("payload").cloned().unwrap_or(serde_json::json!({})),
        });

        // Determine channel type from the payload or use slack as default for now
        let channel_type = payload
            .get("channel_type")
            .and_then(|v| v.as_str())
            .unwrap_or("slack");

        let channel_config = serde_json::json!({
            "channel_type": channel_type,
            "config": payload.get("channel_config").cloned().unwrap_or(serde_json::json!({})),
            "credentials_secret": payload.get("credentials_secret").and_then(|v| v.as_str()).unwrap_or(""),
        });

        let request_body = serde_json::json!({
            "entry": entry,
            "channel_config": channel_config,
        });

        let resp = self
            .client
            .post(&delivery_url)
            .json(&request_body)
            .send()
            .await
            .map_err(|e| {
                OutboxError::QdrantError(format!("Failed to reach UI delivery endpoint: {}", e))
            })?;

        let delivery_resp: DeliveryResponse = resp.json().await.map_err(|e| {
            OutboxError::QdrantError(format!("Failed to parse delivery response: {}", e))
        })?;

        Ok(delivery_resp)
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

        info!(interval_secs = interval_secs, "Outbox worker started");

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

/// Get UI service endpoint from environment
fn get_ui_endpoint() -> String {
    std::env::var("BEEPER_UI_URL")
        .unwrap_or_else(|_| "http://localhost:5050".to_string())
        .trim_end_matches('/')
        .to_string()
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
    fn test_write_notification_body_includes_vector_field() {
        // Qdrant payload-only collections require "vector": {} in upsert points.
        // Regression guard: removing this field causes "missing field vector" errors.
        let entry = OutboxEntry {
            investigation_id: "inv-test".to_string(),
            event_type: "test_event".to_string(),
            severity: "low".to_string(),
            service: "test-svc".to_string(),
            payload: serde_json::json!({}),
            status: "pending".to_string(),
            retry_count: 0,
            created_at: "2026-04-03T12:00:00Z".to_string(),
            next_retry_at: "2026-04-03T12:00:00Z".to_string(),
            last_error: None,
        };
        let point_id = OutboxWorker::point_id(&entry.investigation_id, &entry.created_at);
        let body = serde_json::json!({
            "points": [
                {
                    "id": point_id,
                    "vector": {},
                    "payload": entry
                }
            ]
        });
        let point = &body["points"][0];
        assert!(
            point.get("vector").is_some(),
            "upsert point must include 'vector' field"
        );
        assert_eq!(point["vector"], serde_json::json!({}));
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

    #[test]
    fn test_outbox_worker_new_with_ui() {
        let worker = OutboxWorker::new_with_ui(
            "http://qdrant:6333".to_string(),
            "http://ui:5050".to_string(),
        );
        assert_eq!(worker.endpoint, "http://qdrant:6333");
        assert_eq!(worker.ui_endpoint, "http://ui:5050");
        assert!(!worker.collection_ensured);
    }

    #[test]
    fn test_outbox_worker_new_with_ui_trims_trailing_slash() {
        let worker = OutboxWorker::new_with_ui(
            "http://qdrant:6333/".to_string(),
            "http://ui:5050/".to_string(),
        );
        assert_eq!(worker.endpoint, "http://qdrant:6333");
        assert_eq!(worker.ui_endpoint, "http://ui:5050");
    }

    #[test]
    fn test_delivery_response_deserialization_success() {
        let json = r#"{
            "status": "delivered",
            "thread_ts": "1234567890.123456",
            "retryable": false
        }"#;
        let resp: DeliveryResponse = serde_json::from_str(json).unwrap();
        assert_eq!(resp.status, "delivered");
        assert_eq!(resp.thread_ts.unwrap(), "1234567890.123456");
        assert!(!resp.retryable);
        assert!(resp.error.is_none());
    }

    #[test]
    fn test_delivery_response_deserialization_failure() {
        let json = r#"{
            "status": "failed",
            "error": "Slack API error: channel_not_found",
            "retryable": false
        }"#;
        let resp: DeliveryResponse = serde_json::from_str(json).unwrap();
        assert_eq!(resp.status, "failed");
        assert_eq!(resp.error.unwrap(), "Slack API error: channel_not_found");
        assert!(!resp.retryable);
        assert!(resp.thread_ts.is_none());
    }

    #[test]
    fn test_delivery_response_deserialization_retryable() {
        let json = r#"{
            "status": "failed",
            "error": "rate_limited",
            "retryable": true
        }"#;
        let resp: DeliveryResponse = serde_json::from_str(json).unwrap();
        assert_eq!(resp.status, "failed");
        assert!(resp.retryable);
    }

    #[test]
    fn test_delivery_response_deserialization_skipped() {
        let json = r#"{
            "status": "skipped",
            "error": "Channel type 'pagerduty' not yet implemented",
            "retryable": false
        }"#;
        let resp: DeliveryResponse = serde_json::from_str(json).unwrap();
        assert_eq!(resp.status, "skipped");
        assert!(!resp.retryable);
    }

    #[test]
    fn test_delivery_response_minimal() {
        let json = r#"{"status": "delivered"}"#;
        let resp: DeliveryResponse = serde_json::from_str(json).unwrap();
        assert_eq!(resp.status, "delivered");
        assert!(resp.error.is_none());
        assert!(resp.thread_ts.is_none());
        assert!(!resp.retryable);
    }
}
