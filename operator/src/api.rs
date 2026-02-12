//! API endpoints for the Beeper UI
//!
//! Provides REST API endpoints for the UI to fetch source status,
//! health information, and ingestion statistics.

use axum::{
    extract::State,
    http::StatusCode,
    response::IntoResponse,
    routing::get,
    Json, Router,
};
use kube::{api::ListParams, Api, Client};
use serde::Serialize;
use std::sync::Arc;
use tracing::{debug, warn};

use crate::crds::Source;
use crate::ingestion::IngestionBuffer;

/// Shared state for API endpoints
#[derive(Clone)]
pub struct ApiState {
    pub client: Arc<Client>,
    pub buffer: Arc<IngestionBuffer>,
}

/// Create the API router
pub fn api_router(client: Arc<Client>, buffer: Arc<IngestionBuffer>) -> Router {
    let state = ApiState { client, buffer };

    Router::new()
        .route("/api/v1/sources", get(list_sources))
        .route("/api/v1/health/components", get(health_components))
        .route("/api/v1/ingestion/stats", get(ingestion_stats))
        .with_state(state)
}

// ----- Source API -----

/// Response for a single source
#[derive(Debug, Serialize)]
pub struct SourceResponse {
    pub name: String,
    #[serde(rename = "type")]
    pub source_type: String,
    pub endpoint: String,
    pub status: String,
    pub last_check: Option<String>,
    pub error: Option<SourceErrorResponse>,
}

/// Error details for a source
#[derive(Debug, Serialize)]
pub struct SourceErrorResponse {
    #[serde(rename = "type")]
    pub error_type: String,
    pub message: String,
    pub details: Option<String>,
}

/// Response for listing all sources
#[derive(Debug, Serialize)]
pub struct SourceListResponse {
    pub sources: Vec<SourceResponse>,
}

/// List all configured sources with their status
async fn list_sources(State(state): State<ApiState>) -> impl IntoResponse {
    // Try to list Source CRDs from the cluster
    let sources_api: Api<Source> = Api::all((*state.client).clone());

    match sources_api.list(&ListParams::default()).await {
        Ok(source_list) => {
            let sources: Vec<SourceResponse> = source_list
                .items
                .into_iter()
                .map(|source| {
                    let name = source.metadata.name.unwrap_or_default();
                    let spec = source.spec;
                    let status = source.status.unwrap_or_default();

                    // Convert SourceType enum to string
                    let source_type = format!("{:?}", spec.source_type).to_lowercase();

                    // Determine connection status from the status fields
                    let (connection_status, error) = match (status.connected, &status.error) {
                        (Some(true), _) => ("connected".to_string(), None),
                        (Some(false), Some(err_msg)) => {
                            let error = SourceErrorResponse {
                                error_type: "connection_error".to_string(),
                                message: err_msg.clone(),
                                details: None,
                            };
                            ("error".to_string(), Some(error))
                        }
                        (Some(false), None) => ("error".to_string(), None),
                        (None, _) => ("unknown".to_string(), None),
                    };

                    SourceResponse {
                        name,
                        source_type,
                        endpoint: spec.endpoint,
                        status: connection_status,
                        last_check: status.last_checked,
                        error,
                    }
                })
                .collect();

            debug!(count = sources.len(), "Listed sources");
            (StatusCode::OK, Json(SourceListResponse { sources })).into_response()
        }
        Err(e) => {
            warn!(error = %e, "Failed to list sources");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ProblemDetails {
                    error_type: "https://beeper.io/errors/source-list-failed".to_string(),
                    title: "Failed to list sources".to_string(),
                    status: 500,
                    detail: format!("Could not retrieve source list: {}", e),
                }),
            )
                .into_response()
        }
    }
}

// ----- Health Components API -----

/// Response for a single component
#[derive(Debug, Serialize)]
pub struct ComponentStatusResponse {
    pub status: String,
    pub message: String,
}

/// Response for health components
#[derive(Debug, Serialize)]
pub struct HealthComponentsResponse {
    pub components: std::collections::HashMap<String, ComponentStatusResponse>,
    pub overall: String,
}

/// Get detailed health status of all components
async fn health_components(State(state): State<ApiState>) -> impl IntoResponse {
    let mut components = std::collections::HashMap::new();
    let mut overall_healthy = true;

    // Check operator (always healthy if we're responding)
    components.insert(
        "operator".to_string(),
        ComponentStatusResponse {
            status: "healthy".to_string(),
            message: "Running".to_string(),
        },
    );

    // Check Kubernetes API connectivity
    match state.client.apiserver_version().await {
        Ok(_) => {
            components.insert(
                "kubernetes".to_string(),
                ComponentStatusResponse {
                    status: "healthy".to_string(),
                    message: "Connected to API server".to_string(),
                },
            );
        }
        Err(e) => {
            overall_healthy = false;
            components.insert(
                "kubernetes".to_string(),
                ComponentStatusResponse {
                    status: "unhealthy".to_string(),
                    message: format!("Cannot reach API server: {}", e),
                },
            );
        }
    }

    // Check ingestion buffer status
    let buffer_count = state.buffer.buffered_count();
    let buffer_capacity = state.buffer.capacity();
    let is_full = state.buffer.is_full();

    let ingestion_status = if is_full { "warning" } else { "healthy" };
    components.insert(
        "ingestion".to_string(),
        ComponentStatusResponse {
            status: ingestion_status.to_string(),
            message: format!("Buffer: {}/{}", buffer_count, buffer_capacity),
        },
    );

    let overall = if overall_healthy { "healthy" } else { "unhealthy" };

    (
        StatusCode::OK,
        Json(HealthComponentsResponse {
            components,
            overall: overall.to_string(),
        }),
    )
}

// ----- Ingestion Stats API -----

/// Response for ingestion statistics
#[derive(Debug, Serialize)]
pub struct IngestionStatsResponse {
    pub buffer_size: usize,
    pub buffered_count: u64,
    pub dropped_count: u64,
    pub is_full: bool,
}

/// Get ingestion buffer statistics
async fn ingestion_stats(State(state): State<ApiState>) -> impl IntoResponse {
    let stats = IngestionStatsResponse {
        buffer_size: state.buffer.capacity(),
        buffered_count: state.buffer.buffered_count(),
        dropped_count: state.buffer.dropped_count(),
        is_full: state.buffer.is_full(),
    };

    debug!(
        buffer_size = stats.buffer_size,
        buffered = stats.buffered_count,
        dropped = stats.dropped_count,
        "Ingestion stats requested"
    );

    (StatusCode::OK, Json(stats))
}

// ----- RFC 7807 Problem Details -----

/// RFC 7807 Problem Details response
#[derive(Debug, Serialize)]
pub struct ProblemDetails {
    #[serde(rename = "type")]
    pub error_type: String,
    pub title: String,
    pub status: u16,
    pub detail: String,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_source_response_serialization() {
        let response = SourceResponse {
            name: "test".to_string(),
            source_type: "prometheus".to_string(),
            endpoint: "http://localhost:9090".to_string(),
            status: "connected".to_string(),
            last_check: Some("2026-02-10T12:00:00Z".to_string()),
            error: None,
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"type\":\"prometheus\""));
        assert!(json.contains("\"status\":\"connected\""));
    }

    #[test]
    fn test_source_response_with_error() {
        let response = SourceResponse {
            name: "loki-prod".to_string(),
            source_type: "loki".to_string(),
            endpoint: "http://loki:3100".to_string(),
            status: "error".to_string(),
            last_check: Some("2026-02-10T12:00:00Z".to_string()),
            error: Some(SourceErrorResponse {
                error_type: "connection_error".to_string(),
                message: "Connection refused".to_string(),
                details: Some("dial tcp: connection refused".to_string()),
            }),
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"status\":\"error\""));
        assert!(json.contains("\"message\":\"Connection refused\""));
    }

    #[test]
    fn test_source_error_serialization() {
        let error = SourceErrorResponse {
            error_type: "connection_refused".to_string(),
            message: "Connection refused".to_string(),
            details: Some("dial tcp: connection refused".to_string()),
        };

        let json = serde_json::to_string(&error).unwrap();
        assert!(json.contains("\"type\":\"connection_refused\""));
    }

    #[test]
    fn test_ingestion_stats_serialization() {
        let stats = IngestionStatsResponse {
            buffer_size: 10000,
            buffered_count: 150,
            dropped_count: 0,
            is_full: false,
        };

        let json = serde_json::to_string(&stats).unwrap();
        assert!(json.contains("\"buffer_size\":10000"));
        assert!(json.contains("\"is_full\":false"));
    }

    #[test]
    fn test_health_components_serialization() {
        let mut components = std::collections::HashMap::new();
        components.insert(
            "operator".to_string(),
            ComponentStatusResponse {
                status: "healthy".to_string(),
                message: "Running".to_string(),
            },
        );
        components.insert(
            "ingestion".to_string(),
            ComponentStatusResponse {
                status: "warning".to_string(),
                message: "Buffer: 10000/10000".to_string(),
            },
        );

        let response = HealthComponentsResponse {
            components,
            overall: "healthy".to_string(),
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"overall\":\"healthy\""));
        assert!(json.contains("\"operator\""));
        assert!(json.contains("\"ingestion\""));
    }

    #[test]
    fn test_problem_details_serialization() {
        let problem = ProblemDetails {
            error_type: "https://beeper.io/errors/test".to_string(),
            title: "Test Error".to_string(),
            status: 500,
            detail: "Test error details".to_string(),
        };

        let json = serde_json::to_string(&problem).unwrap();
        assert!(json.contains("\"type\":\"https://beeper.io/errors/test\""));
        assert!(json.contains("\"status\":500"));
    }

    #[test]
    fn test_source_list_response_serialization() {
        let response = SourceListResponse {
            sources: vec![
                SourceResponse {
                    name: "prometheus-main".to_string(),
                    source_type: "prometheus".to_string(),
                    endpoint: "http://prometheus:9090".to_string(),
                    status: "connected".to_string(),
                    last_check: Some("2026-02-10T12:00:00Z".to_string()),
                    error: None,
                },
            ],
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"sources\":["));
        assert!(json.contains("\"name\":\"prometheus-main\""));
    }
}

#[cfg(test)]
mod integration_tests {
    use super::*;

    fn create_test_buffer() -> Arc<IngestionBuffer> {
        Arc::new(IngestionBuffer::new(1000))
    }

    #[tokio::test]
    async fn test_ingestion_stats_endpoint() {
        // Create a mock client - we can't easily create a real one in tests
        // So we test the response structure directly
        let stats = IngestionStatsResponse {
            buffer_size: 1000,
            buffered_count: 0,
            dropped_count: 0,
            is_full: false,
        };

        let json = serde_json::to_string(&stats).unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&json).unwrap();

        assert_eq!(parsed["buffer_size"], 1000);
        assert_eq!(parsed["buffered_count"], 0);
        assert_eq!(parsed["dropped_count"], 0);
        assert_eq!(parsed["is_full"], false);
    }

    #[tokio::test]
    async fn test_buffer_stats_after_ingestion() {
        let buffer = create_test_buffer();

        // Add some items
        use crate::ingestion::buffer::{IngestionData, MetricSample};
        use std::collections::HashMap;

        for i in 0..5 {
            let sample = IngestionData::Metric(MetricSample {
                name: format!("test_metric_{}", i),
                labels: HashMap::new(),
                value: i as f64,
                timestamp_ms: 1234567890000,
            });
            buffer.try_send(sample).unwrap();
        }

        // Verify counts
        assert_eq!(buffer.buffered_count(), 5);
        assert_eq!(buffer.dropped_count(), 0);
        assert!(!buffer.is_full());
    }
}
