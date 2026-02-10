//! Beeper Operator
//!
//! Kubernetes operator that watches for anomalies and spawns investigator pods.
//! This is the main entry point for the operator process.

use std::sync::Arc;

use anyhow::Context;
use kube::Client;
use tokio::signal;
use tracing::{error, info, Level};
use tracing_subscriber::FmtSubscriber;

use beeper_operator::{
    controllers::{run_investigation_controller, run_source_controller},
    health::start_health_server,
};

/// Health server port
const HEALTH_PORT: u16 = 8080;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Initialize tracing with structured JSON logging
    FmtSubscriber::builder()
        .with_max_level(Level::INFO)
        .json()
        .init();

    info!("Beeper operator starting up...");

    // Initialize Kubernetes client
    let client = Client::try_default()
        .await
        .context("Failed to create Kubernetes client")?;

    info!("Connected to Kubernetes API");

    let client = Arc::new(client);

    // Start health server in background
    let health_client = Arc::clone(&client);
    let health_handle = tokio::spawn(async move {
        if let Err(e) = start_health_server(health_client, HEALTH_PORT).await {
            error!(error = %e, "Health server failed");
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
    let investigation_client = (*client).clone();
    let investigation_handle = tokio::spawn(async move {
        if let Err(e) = run_investigation_controller(investigation_client).await {
            error!(error = %e, "Investigation controller failed");
        }
    });

    info!("Beeper operator started");

    // Wait for shutdown signal
    shutdown_signal().await;

    info!("Shutdown signal received, stopping operator...");

    // Abort all background tasks
    health_handle.abort();
    source_handle.abort();
    investigation_handle.abort();

    info!("Beeper operator stopped");

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
