//! Beeper Operator
//!
//! Kubernetes operator that watches for anomalies and spawns investigator pods.
//! This is the main entry point for the operator process.

use std::env;
use std::sync::Arc;
use std::time::Duration;

use anyhow::Context;
use axum::Router;
use kube::Client;
use tokio::signal;
use tokio::sync::watch;
use tracing::{error, info, warn, Level};
use tracing_subscriber::FmtSubscriber;

/// Grace period for in-flight operations to complete during shutdown
const GRACEFUL_SHUTDOWN_TIMEOUT_SECS: u64 = 10;

use beeper_operator::{
    controllers::{
        run_investigation_controller_with_config, run_servicelevel_controller,
        run_source_controller,
    },
    detection::{DetectionConfig, DetectionConsumer, DetectionStats},
    health::health_router,
    ingestion::{ingestion_router, IngestionBuffer},
    slo::{budget::new_budget_policy_state, new_slo_cache, run_slo_engine},
    InvestigatorConfig,
};

/// Default health server port
const DEFAULT_HEALTH_PORT: u16 = 8080;

/// Default ingestion server port (Prometheus-compatible)
const DEFAULT_INGESTION_PORT: u16 = 9090;

/// Default ingestion buffer size
const DEFAULT_BUFFER_SIZE: usize = 10000;

/// Get configuration from environment variables with defaults
fn get_config() -> (u16, u16, usize) {
    let health_port = env::var("BEEPER_HEALTH_PORT")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(DEFAULT_HEALTH_PORT);

    let ingestion_port = env::var("BEEPER_INGESTION_PORT")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(DEFAULT_INGESTION_PORT);

    let buffer_size = env::var("BEEPER_INGESTION_BUFFER_SIZE")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(DEFAULT_BUFFER_SIZE);

    (health_port, ingestion_port, buffer_size)
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Initialize tracing with structured JSON logging
    FmtSubscriber::builder()
        .with_max_level(Level::INFO)
        .json()
        .init();

    info!("Beeper operator starting up...");

    // Load configuration from environment
    let (health_port, ingestion_port, buffer_size) = get_config();
    info!(
        health_port = health_port,
        ingestion_port = ingestion_port,
        buffer_size = buffer_size,
        "Configuration loaded"
    );

    // Initialize Kubernetes client
    let client = Client::try_default()
        .await
        .context("Failed to create Kubernetes client")?;

    info!("Connected to Kubernetes API");

    let client = Arc::new(client);

    // Create ingestion buffer
    let buffer = Arc::new(IngestionBuffer::new(buffer_size));

    // Load detection configuration
    let detection_config = DetectionConfig::from_env();
    let detection_stats = Arc::new(DetectionStats::new());
    info!(
        enabled = detection_config.enabled,
        namespace = %detection_config.namespace,
        "Detection configuration loaded"
    );

    // Create shutdown signal channel for graceful shutdown (NFR17)
    let (shutdown_tx, _shutdown_rx) = watch::channel(false);

    // Create SLO cache (shared between SLO engine and API server)
    let slo_cache = new_slo_cache();

    // Create budget policy state (shared between SLO engine and API server)
    let budget_policy_state = new_budget_policy_state();

    // Start health + API server in background (combined on same port)
    let health_client = Arc::clone(&client);
    let api_buffer = Arc::clone(&buffer);
    let api_detection_stats = Arc::clone(&detection_stats);
    let api_slo_cache = slo_cache.clone();
    let api_budget_policy_state = budget_policy_state.clone();
    let health_handle = tokio::spawn(async move {
        if let Err(e) =
            start_health_api_server(
                health_client,
                api_buffer,
                api_detection_stats,
                api_slo_cache,
                api_budget_policy_state,
                health_port,
            )
                .await
        {
            error!(error = %e, "Health/API server failed");
        }
    });

    // Start ingestion server on separate port
    let ingestion_buffer = Arc::clone(&buffer);
    let ingestion_handle = tokio::spawn(async move {
        if let Err(e) = start_ingestion_server(ingestion_buffer, ingestion_port).await {
            error!(error = %e, "Ingestion server failed");
        }
    });

    // Start Source controller in background
    let source_client = (*client).clone();
    let source_handle = tokio::spawn(async move {
        if let Err(e) = run_source_controller(source_client).await {
            error!(error = %e, "Source controller failed");
        }
    });

    // Start Investigation controller in background
    let investigator_config = InvestigatorConfig::from_env();
    let investigation_client = (*client).clone();
    let investigation_handle = tokio::spawn(async move {
        if let Err(e) =
            run_investigation_controller_with_config(investigation_client, investigator_config).await
        {
            error!(error = %e, "Investigation controller failed");
        }
    });

    // Start ServiceLevel controller in background
    let servicelevel_client = (*client).clone();
    let servicelevel_handle = tokio::spawn(async move {
        if let Err(e) = run_servicelevel_controller(servicelevel_client).await {
            error!(error = %e, "ServiceLevel controller failed");
        }
    });

    // Start SLO engine in background
    let slo_client = (*client).clone();
    let slo_namespace = detection_config.namespace.clone();
    let prometheus_endpoint = env::var("PROMETHEUS_URL")
        .unwrap_or_else(|_| "http://prometheus:9090".to_string());
    let qdrant_endpoint = env::var("QDRANT_URL")
        .unwrap_or_else(|_| "http://qdrant:6333".to_string());
    let detection_slo_cache = slo_cache.clone();
    let slo_budget_policy_state = budget_policy_state.clone();
    let slo_handle = tokio::spawn(async move {
        run_slo_engine(
            slo_client,
            prometheus_endpoint,
            qdrant_endpoint,
            slo_namespace,
            slo_cache,
            slo_budget_policy_state,
        )
        .await;
    });

    // Start detection consumer in background (if enabled)
    let detection_handle = if detection_config.enabled {
        let detection_buffer = Arc::clone(&buffer);
        let detection_client = (*client).clone();
        let detection_namespace = detection_config.namespace.clone();
        let consumer = DetectionConsumer::new(detection_config, detection_stats);
        Some(tokio::spawn(async move {
            consumer
                .run(
                    detection_buffer,
                    detection_client,
                    detection_namespace,
                    Some(detection_slo_cache),
                )
                .await;
        }))
    } else {
        info!("Detection consumer disabled");
        None
    };

    info!("Beeper operator started");

    // Wait for shutdown signal
    shutdown_signal().await;

    info!("Shutdown signal received, starting graceful shutdown...");

    // Signal all cooperative tasks to stop
    let _ = shutdown_tx.send(true);
    info!("Graceful shutdown: waiting for in-flight operations ({}s grace period)...", GRACEFUL_SHUTDOWN_TIMEOUT_SECS);

    // Give SLO engine and detection consumer time to finish current cycle
    let grace_deadline = tokio::time::sleep(Duration::from_secs(GRACEFUL_SHUTDOWN_TIMEOUT_SECS));

    tokio::select! {
        _ = grace_deadline => {
            warn!("Graceful shutdown: grace period expired, aborting remaining tasks");
        }
        _ = async {
            // Wait for SLO engine and detection consumer to finish gracefully
            let _ = (&slo_handle).await;
            info!("Graceful shutdown: SLO engine stopped");
            if let Some(ref handle) = detection_handle {
                let _ = handle.await;
                info!("Graceful shutdown: detection consumer stopped");
            }
        } => {
            info!("Graceful shutdown: cooperative tasks completed within grace period");
        }
    }

    // Abort remaining infrastructure tasks (servers, controllers)
    health_handle.abort();
    ingestion_handle.abort();
    source_handle.abort();
    investigation_handle.abort();
    servicelevel_handle.abort();
    slo_handle.abort();
    if let Some(handle) = detection_handle {
        handle.abort();
    }

    info!("Graceful shutdown complete — Beeper operator stopped");

    Ok(())
}

/// Start the combined health + API HTTP server
async fn start_health_api_server(
    client: Arc<Client>,
    buffer: Arc<IngestionBuffer>,
    detection_stats: Arc<DetectionStats>,
    slo_cache: beeper_operator::slo::SloCache,
    budget_policy_state: beeper_operator::slo::budget::BudgetPolicyState,
    port: u16,
) -> anyhow::Result<()> {
    use beeper_operator::api::api_router_full;
    // Combine health and API routers
    let health = health_router(Arc::clone(&client));
    let api = api_router_full(client, buffer, None, Some(detection_stats), Some(slo_cache), Some(budget_policy_state));
    let app: Router = health.merge(api);

    let addr = format!("0.0.0.0:{}", port);
    info!(address = %addr, "Starting health/API server");

    let listener = tokio::net::TcpListener::bind(&addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}

/// Start the ingestion HTTP server
async fn start_ingestion_server(buffer: Arc<IngestionBuffer>, port: u16) -> anyhow::Result<()> {
    let app = ingestion_router(buffer);
    let addr = format!("0.0.0.0:{}", port);

    info!(address = %addr, "Starting ingestion server");

    let listener = tokio::net::TcpListener::bind(&addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}

/// Wait for shutdown signal (SIGTERM or SIGINT)
async fn shutdown_signal() {
    let ctrl_c = async {
        signal::ctrl_c()
            .await
            .expect("Failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate())
            .expect("Failed to install SIGTERM handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }
}
