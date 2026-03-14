//! Beeper Operator
//!
//! Kubernetes operator that watches for anomalies and spawns investigator pods.
//! This is the main entry point for the operator process.

use std::env;
use std::sync::Arc;

use anyhow::Context;
use axum::Router;
use kube::Client;
use tokio::signal;
use tracing::{error, info, Level};
use tracing_subscriber::FmtSubscriber;

use beeper_operator::{
    controllers::{
        run_investigation_controller_with_config, run_servicelevel_controller,
        run_source_controller,
    },
    detection::{DetectionConfig, DetectionConsumer, DetectionStats},
    health::health_router,
    ingestion::{ingestion_router, IngestionBuffer},
    slo::{new_slo_cache, run_slo_engine},
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

    // Start health + API server in background (combined on same port)
    let health_client = Arc::clone(&client);
    let api_buffer = Arc::clone(&buffer);
    let api_detection_stats = Arc::clone(&detection_stats);
    let health_handle = tokio::spawn(async move {
        if let Err(e) =
            start_health_api_server(health_client, api_buffer, api_detection_stats, health_port)
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
    let slo_cache = new_slo_cache();
    let slo_handle = tokio::spawn(async move {
        run_slo_engine(
            slo_client,
            prometheus_endpoint,
            qdrant_endpoint,
            slo_namespace,
            slo_cache,
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
                .run(detection_buffer, detection_client, detection_namespace)
                .await;
        }))
    } else {
        info!("Detection consumer disabled");
        None
    };

    info!("Beeper operator started");

    // Wait for shutdown signal
    shutdown_signal().await;

    info!("Shutdown signal received, stopping operator...");

    // Abort all background tasks
    health_handle.abort();
    ingestion_handle.abort();
    source_handle.abort();
    investigation_handle.abort();
    servicelevel_handle.abort();
    slo_handle.abort();
    if let Some(handle) = detection_handle {
        handle.abort();
    }

    info!("Beeper operator stopped");

    Ok(())
}

/// Start the combined health + API HTTP server
async fn start_health_api_server(
    client: Arc<Client>,
    buffer: Arc<IngestionBuffer>,
    detection_stats: Arc<DetectionStats>,
    port: u16,
) -> anyhow::Result<()> {
    use beeper_operator::api::api_router_with_detection;
    // Combine health and API routers
    let health = health_router(Arc::clone(&client));
    let api = api_router_with_detection(client, buffer, None, Some(detection_stats));
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
