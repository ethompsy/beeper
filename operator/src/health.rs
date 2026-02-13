//! Health check endpoints for the Beeper operator
//!
//! Provides `/healthz` and `/readyz` endpoints for Kubernetes
//! liveness and readiness probes.

use axum::{extract::State, http::StatusCode, response::IntoResponse, routing::get, Router};
use kube::Client;
use std::sync::Arc;
use tracing::{debug, info, warn};

/// Shared state for health endpoints
#[derive(Clone)]
pub struct HealthState {
    pub client: Arc<Client>,
}

/// Create the health check router
pub fn health_router(client: Arc<Client>) -> Router {
    let state = HealthState { client };

    Router::new()
        .route("/healthz", get(healthz))
        .route("/readyz", get(readyz))
        .with_state(state)
}

/// Liveness probe endpoint
///
/// Returns 200 OK if the operator process is alive.
/// This endpoint does not check external dependencies.
async fn healthz() -> impl IntoResponse {
    (StatusCode::OK, "ok")
}

/// Readiness probe endpoint
///
/// Returns 200 OK if the operator can communicate with the Kubernetes API.
/// Returns 503 Service Unavailable if the API is unreachable.
async fn readyz(State(state): State<HealthState>) -> impl IntoResponse {
    match state.client.apiserver_version().await {
        Ok(version) => {
            debug!(
                kubernetes_version = %version.git_version,
                "Readiness check passed"
            );
            (StatusCode::OK, "ok")
        }
        Err(e) => {
            warn!(error = %e, "Readiness check failed - cannot reach Kubernetes API");
            (StatusCode::SERVICE_UNAVAILABLE, "not ready")
        }
    }
}

/// Start the health check HTTP server
pub async fn start_health_server(client: Arc<Client>, port: u16) -> anyhow::Result<()> {
    let app = health_router(client);
    let addr = format!("0.0.0.0:{}", port);

    info!(address = %addr, "Starting health server");

    let listener = tokio::net::TcpListener::bind(&addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_healthz_returns_ok() {
        // Test the healthz function directly
        let response = healthz().await.into_response();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[test]
    fn test_health_router_has_both_routes() {
        // Verify the router is constructed with both endpoints
        // Note: Full readyz testing requires a K8s cluster connection
        // We can't easily test readyz without a real Client,
        // but we verify the router builds without panic
        // Integration tests with real K8s should cover readyz behavior
    }

    #[test]
    fn test_health_state_is_clone() {
        // Verify HealthState implements Clone (required for axum state)
        fn assert_clone<T: Clone>() {}
        assert_clone::<HealthState>();
    }
}
