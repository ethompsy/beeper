//! Standalone ingestion server for testing
//!
//! Run with: cargo run --example test_ingestion
//! Then test with curl commands shown at startup.

use beeper_operator::ingestion::{ingestion_router, IngestionBuffer};
use std::sync::Arc;
use tracing::{info, Level};
use tracing_subscriber::FmtSubscriber;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Initialize logging
    FmtSubscriber::builder()
        .with_max_level(Level::DEBUG)
        .init();

    let port = 9090;
    let buffer = Arc::new(IngestionBuffer::new(1000));
    let app = ingestion_router(buffer.clone());

    println!("\n========================================");
    println!("  Beeper Ingestion Server (Test Mode)");
    println!("========================================\n");
    println!("Listening on http://0.0.0.0:{}\n", port);
    println!("Test with:\n");
    println!("# Prometheus remote_write:");
    println!(r#"curl -X POST http://localhost:9090/api/v1/write \
  -H "Content-Type: application/x-protobuf" \
  -d "test" --write-out "%{{http_code}}\n""#);
    println!("\n# Loki push:");
    println!(r#"curl -X POST http://localhost:9090/loki/api/v1/push \
  -H "Content-Type: application/json" \
  -d '{{"streams":[{{"stream":{{"app":"test"}},"values":[["1234567890000000000","Hello from test"]]}}]}}'"#);
    println!("\n========================================\n");

    info!(port = port, "Starting ingestion server");

    let listener = tokio::net::TcpListener::bind(format!("0.0.0.0:{}", port)).await?;

    // Spawn a task to periodically show buffer stats
    let stats_buffer = buffer.clone();
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(tokio::time::Duration::from_secs(5)).await;
            let buffered = stats_buffer.buffered_count();
            let dropped = stats_buffer.dropped_count();
            if buffered > 0 || dropped > 0 {
                println!("Buffer stats: {} buffered, {} dropped", buffered, dropped);
            }
        }
    });

    axum::serve(listener, app).await?;

    Ok(())
}
