//! Source controller
//!
//! Watches for Source CRDs and reconciles their status by
//! testing connectivity to the configured data sources.

use std::collections::BTreeMap;
use std::sync::Arc;
use std::time::Duration;

use futures::StreamExt;
use k8s_openapi::api::core::v1::Secret;
use kube::{
    api::{Api, Patch, PatchParams},
    runtime::controller::{Action, Controller},
    Client, ResourceExt,
};
use serde_json::json;
use tracing::{debug, error, info, instrument, warn};

use crate::crds::{Source, SourceStatus, SourceType};
use crate::sources::{Credentials, LokiClient, LokiError, PrometheusClient, PrometheusError};

/// Error type for source controller operations
#[derive(Debug, thiserror::Error)]
pub enum SourceError {
    #[error("Kubernetes API error: {0}")]
    KubeError(#[from] kube::Error),

    #[error("Missing object key: {0}")]
    MissingObjectKey(&'static str),

    #[error("Secret not found: {0}")]
    SecretNotFound(String),

    #[error("Invalid secret format: {0}")]
    InvalidSecret(String),

    #[error("Prometheus error: {0}")]
    PrometheusError(#[from] PrometheusError),

    #[error("Loki error: {0}")]
    LokiError(#[from] LokiError),

    #[error("Serialization error: {0}")]
    SerializationError(#[from] serde_json::Error),
}

/// Context shared across reconciliation calls
pub struct SourceContext {
    pub client: Client,
}

/// Backoff configuration for connection retries
struct BackoffConfig {
    /// Base delay for retries
    base_delay: Duration,
    /// Maximum delay between retries
    max_delay: Duration,
}

impl Default for BackoffConfig {
    fn default() -> Self {
        Self {
            base_delay: Duration::from_secs(5),
            max_delay: Duration::from_secs(60),
        }
    }
}

impl BackoffConfig {
    /// Calculate delay based on retry count using exponential backoff
    fn calculate_delay(&self, retry_count: u32) -> Duration {
        // Exponential backoff: 5s, 10s, 20s, 40s, 60s (max)
        let delay_secs = self.base_delay.as_secs() * 2u64.pow(retry_count.min(4));
        Duration::from_secs(delay_secs.min(self.max_delay.as_secs()))
    }
}

/// Load credentials from a Kubernetes Secret
async fn load_credentials(
    client: &Client,
    namespace: &str,
    secret_name: &str,
) -> Result<Credentials, SourceError> {
    debug!(
        namespace = %namespace,
        secret = %secret_name,
        "Loading credentials from Secret"
    );

    let secrets: Api<Secret> = Api::namespaced(client.clone(), namespace);

    let secret = secrets.get(secret_name).await.map_err(|e| {
        if e.to_string().contains("NotFound") {
            SourceError::SecretNotFound(format!(
                "Secret '{}' not found in namespace '{}'",
                secret_name, namespace
            ))
        } else {
            SourceError::KubeError(e)
        }
    })?;

    let data = secret
        .data
        .ok_or_else(|| SourceError::InvalidSecret("Secret has no data field".to_string()))?;

    // Try to get username and password from the secret
    let username = extract_secret_field(&data, "username")?;
    let password = extract_secret_field(&data, "password")?;

    Ok(Credentials::new(username, password))
}

/// Extract a field from secret data (base64-decoded)
fn extract_secret_field(
    data: &BTreeMap<String, k8s_openapi::ByteString>,
    field: &str,
) -> Result<String, SourceError> {
    let bytes = data
        .get(field)
        .ok_or_else(|| SourceError::InvalidSecret(format!("Secret missing '{}' field", field)))?;

    String::from_utf8(bytes.0.clone()).map_err(|e| {
        SourceError::InvalidSecret(format!("Invalid UTF-8 in '{}' field: {}", field, e))
    })
}

/// Get current timestamp in ISO 8601 format
fn current_timestamp() -> String {
    chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string()
}

/// Update the status subresource of a Source
async fn update_source_status(
    client: &Client,
    source: &Source,
    status: SourceStatus,
) -> Result<(), SourceError> {
    let name = source.name_any();
    let namespace = source.namespace().unwrap_or_else(|| "default".to_string());

    let sources: Api<Source> = Api::namespaced(client.clone(), &namespace);

    let patch = json!({
        "status": status
    });

    sources
        .patch_status(
            &name,
            &PatchParams::apply("beeper-operator"),
            &Patch::Merge(&patch),
        )
        .await?;

    debug!(
        source = %name,
        namespace = %namespace,
        connected = ?status.connected,
        "Updated Source status"
    );

    Ok(())
}

/// Check connectivity to a Prometheus source
async fn check_prometheus_connectivity(
    endpoint: &str,
    credentials: Option<Credentials>,
) -> Result<(), PrometheusError> {
    let client = PrometheusClient::new(endpoint.to_string(), credentials)?;
    client.check_health().await?;
    Ok(())
}

/// Check connectivity to a Loki source
async fn check_loki_connectivity(
    endpoint: &str,
    credentials: Option<Credentials>,
) -> Result<(), LokiError> {
    let client = LokiClient::new(endpoint.to_string(), credentials)?;
    client.check_health().await?;
    Ok(())
}

/// Reconcile a Source resource
///
/// This function is called whenever a Source is created, updated, or deleted.
/// It validates the source configuration and updates the status accordingly.
#[instrument(skip(source, ctx), fields(source_name = %source.name_any(), source_namespace = source.namespace().unwrap_or_default()))]
async fn reconcile(source: Arc<Source>, ctx: Arc<SourceContext>) -> Result<Action, SourceError> {
    let name = source.name_any();
    let namespace = source.namespace().unwrap_or_else(|| "default".to_string());

    info!(
        source_type = ?source.spec.source_type,
        endpoint = %source.spec.endpoint,
        "Reconciling Source"
    );

    // Load credentials if specified
    let credentials = if let Some(ref secret_name) = source.spec.credentials_secret {
        match load_credentials(&ctx.client, &namespace, secret_name).await {
            Ok(creds) => {
                debug!(secret = %secret_name, "Loaded credentials from Secret");
                Some(creds)
            }
            Err(e) => {
                warn!(
                    source = %name,
                    error = %e,
                    "Failed to load credentials"
                );

                // Get current retry count from status and increment
                let current_retry = source
                    .status
                    .as_ref()
                    .and_then(|s| s.retry_count)
                    .unwrap_or(0);
                let new_retry = current_retry.saturating_add(1);

                // Update status with error
                let status = SourceStatus {
                    connected: Some(false),
                    last_checked: Some(current_timestamp()),
                    error: Some(e.to_string()),
                    retry_count: Some(new_retry),
                };
                update_source_status(&ctx.client, &source, status).await?;

                // Retry after backoff
                let backoff = BackoffConfig::default();
                return Ok(Action::requeue(backoff.calculate_delay(new_retry)));
            }
        }
    } else {
        None
    };

    // Check connectivity based on source type
    let check_result: Result<(), String> = match source.spec.source_type {
        SourceType::Prometheus => check_prometheus_connectivity(&source.spec.endpoint, credentials)
            .await
            .map_err(|e| format_prometheus_error(&e)),
        SourceType::Loki => check_loki_connectivity(&source.spec.endpoint, credentials)
            .await
            .map_err(|e| format_loki_error(&e)),
    };

    // Update status based on result
    let (status, requeue_delay) = match check_result {
        Ok(()) => {
            // Get previous status to detect transitions
            let was_connected = source
                .status
                .as_ref()
                .and_then(|s| s.connected)
                .unwrap_or(false);

            if !was_connected {
                info!(
                    source = %name,
                    endpoint = %source.spec.endpoint,
                    "Source connection established"
                );
            }

            let status = SourceStatus {
                connected: Some(true),
                last_checked: Some(current_timestamp()),
                error: None,
                retry_count: None, // Reset on successful connection
            };

            // Requeue after 5 minutes for periodic health check
            (status, Duration::from_secs(300))
        }
        Err(error_msg) => {
            // Get previous status to detect transitions
            let was_connected = source
                .status
                .as_ref()
                .and_then(|s| s.connected)
                .unwrap_or(true);

            if was_connected {
                warn!(
                    source = %name,
                    endpoint = %source.spec.endpoint,
                    error = %error_msg,
                    "Source connection lost"
                );
            } else {
                debug!(
                    source = %name,
                    endpoint = %source.spec.endpoint,
                    error = %error_msg,
                    "Source still disconnected"
                );
            }

            // Get current retry count from status and increment
            let current_retry = source
                .status
                .as_ref()
                .and_then(|s| s.retry_count)
                .unwrap_or(0);
            let new_retry = current_retry.saturating_add(1);

            let status = SourceStatus {
                connected: Some(false),
                last_checked: Some(current_timestamp()),
                error: Some(error_msg),
                retry_count: Some(new_retry),
            };

            // Use exponential backoff for retries
            let backoff = BackoffConfig::default();
            (status, backoff.calculate_delay(new_retry))
        }
    };

    update_source_status(&ctx.client, &source, status).await?;

    Ok(Action::requeue(requeue_delay))
}

/// Format Prometheus error message for user display
///
/// Makes errors actionable without exposing sensitive information
fn format_prometheus_error(error: &PrometheusError) -> String {
    match error {
        PrometheusError::ConnectionError { message } => message.clone(),
        PrometheusError::AuthError(msg) => msg.clone(),
        PrometheusError::Timeout(secs) => {
            format!("Connection timed out after {} seconds", secs)
        }
        PrometheusError::ApiError {
            error_type,
            message,
        } => {
            format!("Prometheus API error ({}): {}", error_type, message)
        }
        PrometheusError::HttpError(e) => {
            if e.is_connect() {
                "Connection refused - verify endpoint is accessible".to_string()
            } else if e.is_timeout() {
                "Connection timed out".to_string()
            } else {
                format!("HTTP error: {}", e)
            }
        }
        PrometheusError::ParseError(msg) => {
            format!("Invalid response from Prometheus: {}", msg)
        }
    }
}

/// Format Loki error message for user display
///
/// Makes errors actionable without exposing sensitive information
fn format_loki_error(error: &LokiError) -> String {
    match error {
        LokiError::ConnectionError { message } => message.clone(),
        LokiError::AuthError(msg) => msg.clone(),
        LokiError::Timeout(secs) => {
            format!("Connection timed out after {} seconds", secs)
        }
        LokiError::ApiError {
            error_type,
            message,
        } => {
            format!("Loki API error ({}): {}", error_type, message)
        }
        LokiError::HttpError(e) => {
            if e.is_connect() {
                "Connection refused - verify endpoint is accessible".to_string()
            } else if e.is_timeout() {
                "Connection timed out".to_string()
            } else {
                format!("HTTP error: {}", e)
            }
        }
        LokiError::ParseError(msg) => {
            format!("Invalid response from Loki: {}", msg)
        }
    }
}

/// Error policy for handling reconciliation failures
fn error_policy(source: Arc<Source>, error: &SourceError, _ctx: Arc<SourceContext>) -> Action {
    let name = source.name_any();
    error!(
        source_name = %name,
        error = %error,
        "Source reconciliation failed"
    );

    // Use exponential backoff for retries
    let backoff = BackoffConfig::default();
    Action::requeue(backoff.calculate_delay(0))
}

/// Run the Source controller
///
/// This starts watching for Source CRDs and reconciling them.
pub async fn run_source_controller(client: Client) -> anyhow::Result<()> {
    let sources: Api<Source> = Api::all(client.clone());
    let ctx = Arc::new(SourceContext { client });

    info!("Starting Source controller");

    Controller::new(sources, Default::default())
        .run(reconcile, error_policy, ctx)
        .for_each(|res| async move {
            match res {
                Ok(o) => debug!(resource = ?o, "Source reconciled"),
                Err(e) => error!(error = %e, "Source reconciliation error"),
            }
        })
        .await;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_source_error_display() {
        let err = SourceError::MissingObjectKey("name");
        assert_eq!(err.to_string(), "Missing object key: name");
    }

    #[test]
    fn test_secret_not_found_error() {
        let err = SourceError::SecretNotFound("my-secret in default".to_string());
        assert_eq!(err.to_string(), "Secret not found: my-secret in default");
    }

    #[test]
    fn test_invalid_secret_error() {
        let err = SourceError::InvalidSecret("missing password".to_string());
        assert_eq!(err.to_string(), "Invalid secret format: missing password");
    }

    #[test]
    fn test_backoff_calculation() {
        let config = BackoffConfig::default();

        assert_eq!(config.calculate_delay(0), Duration::from_secs(5));
        assert_eq!(config.calculate_delay(1), Duration::from_secs(10));
        assert_eq!(config.calculate_delay(2), Duration::from_secs(20));
        assert_eq!(config.calculate_delay(3), Duration::from_secs(40));
        assert_eq!(config.calculate_delay(4), Duration::from_secs(60)); // max
        assert_eq!(config.calculate_delay(5), Duration::from_secs(60)); // capped at max
        assert_eq!(config.calculate_delay(10), Duration::from_secs(60)); // still capped
    }

    #[test]
    fn test_format_prometheus_error_connection() {
        let err = PrometheusError::ConnectionError {
            message: "Connection refused at http://prometheus:9090".to_string(),
        };
        assert!(format_prometheus_error(&err).contains("Connection refused"));
    }

    #[test]
    fn test_format_prometheus_error_auth() {
        let err = PrometheusError::AuthError("Authentication failed".to_string());
        assert_eq!(format_prometheus_error(&err), "Authentication failed");
    }

    #[test]
    fn test_format_prometheus_error_timeout() {
        let err = PrometheusError::Timeout(30);
        assert_eq!(
            format_prometheus_error(&err),
            "Connection timed out after 30 seconds"
        );
    }

    #[test]
    fn test_format_prometheus_error_api_error() {
        let err = PrometheusError::ApiError {
            error_type: "bad_data".to_string(),
            message: "invalid query".to_string(),
        };
        assert_eq!(
            format_prometheus_error(&err),
            "Prometheus API error (bad_data): invalid query"
        );
    }

    #[test]
    fn test_format_loki_error_connection() {
        let err = LokiError::ConnectionError {
            message: "Connection refused at http://loki:3100".to_string(),
        };
        assert!(format_loki_error(&err).contains("Connection refused"));
    }

    #[test]
    fn test_format_loki_error_auth() {
        let err = LokiError::AuthError("Authentication failed".to_string());
        assert_eq!(format_loki_error(&err), "Authentication failed");
    }

    #[test]
    fn test_format_loki_error_timeout() {
        let err = LokiError::Timeout(30);
        assert_eq!(
            format_loki_error(&err),
            "Connection timed out after 30 seconds"
        );
    }

    #[test]
    fn test_format_loki_error_api_error() {
        let err = LokiError::ApiError {
            error_type: "bad_request".to_string(),
            message: "invalid LogQL query".to_string(),
        };
        assert_eq!(
            format_loki_error(&err),
            "Loki API error (bad_request): invalid LogQL query"
        );
    }

    #[test]
    fn test_current_timestamp_format() {
        let ts = current_timestamp();
        // Should be in ISO 8601 format
        assert!(ts.contains("T"));
        assert!(ts.ends_with("Z"));
    }
}

#[cfg(test)]
mod integration_tests {
    use super::*;
    use wiremock::matchers::{method, path};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    #[tokio::test]
    async fn test_check_loki_connectivity_success() {
        let mock_server = MockServer::start().await;

        // Mock the /ready endpoint
        Mock::given(method("GET"))
            .and(path("/ready"))
            .respond_with(ResponseTemplate::new(200).set_body_string("ready"))
            .mount(&mock_server)
            .await;

        let result = check_loki_connectivity(&mock_server.uri(), None).await;
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_check_loki_connectivity_failure() {
        let mock_server = MockServer::start().await;

        // Mock the /ready endpoint returning 503
        Mock::given(method("GET"))
            .and(path("/ready"))
            .respond_with(ResponseTemplate::new(503).set_body_string("not ready"))
            .mount(&mock_server)
            .await;

        let result = check_loki_connectivity(&mock_server.uri(), None).await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_check_loki_connectivity_connection_refused() {
        // Use a port that's not listening
        let result = check_loki_connectivity("http://127.0.0.1:59997", None).await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_check_prometheus_connectivity_success() {
        use wiremock::matchers::query_param;
        let mock_server = MockServer::start().await;

        // Mock the Prometheus query endpoint for health check (uses "up" query)
        Mock::given(method("GET"))
            .and(path("/api/v1/query"))
            .and(query_param("query", "up"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [{"metric": {}, "value": [0, "1"]}]
                }
            })))
            .mount(&mock_server)
            .await;

        let result = check_prometheus_connectivity(&mock_server.uri(), None).await;
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_check_prometheus_connectivity_failure() {
        let mock_server = MockServer::start().await;

        // Mock the Prometheus query endpoint returning an error
        Mock::given(method("GET"))
            .and(path("/api/v1/query"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "status": "error",
                "errorType": "bad_data",
                "error": "invalid query"
            })))
            .mount(&mock_server)
            .await;

        let result = check_prometheus_connectivity(&mock_server.uri(), None).await;
        assert!(result.is_err());
    }
}
