//! Streaming data ingestion module
//!
//! Provides HTTP endpoints for receiving pushed metric and log data:
//! - Prometheus remote_write at `/api/v1/write`
//! - Loki push at `/loki/api/v1/push`
//!
//! Data is buffered asynchronously for processing by the investigation engine.

pub mod buffer;
pub mod loki;
pub mod prometheus;

pub use buffer::{IngestionBuffer, IngestionData};
pub use loki::loki_push_handler;
pub use prometheus::prometheus_write_handler;

use axum::{routing::post, Router};
use std::sync::Arc;

/// Create the ingestion router with all endpoints
pub fn ingestion_router(buffer: Arc<IngestionBuffer>) -> Router {
    Router::new()
        .route("/api/v1/write", post(prometheus_write_handler))
        .route("/loki/api/v1/push", post(loki_push_handler))
        .with_state(buffer)
}

#[cfg(test)]
mod integration_tests {
    use super::*;
    use axum::{
        body::Body,
        http::{Request, StatusCode},
    };
    use prometheus::{Label, Sample, TimeSeries, WriteRequest};
    use prost::Message;
    use tower::ServiceExt;

    #[tokio::test]
    async fn test_prometheus_endpoint_full_flow() {
        let buffer = Arc::new(IngestionBuffer::new(100));
        let app = ingestion_router(buffer.clone());

        // Create a WriteRequest with multiple timeseries
        let request = WriteRequest {
            timeseries: vec![
                TimeSeries {
                    labels: vec![
                        Label {
                            name: "__name__".to_string(),
                            value: "http_requests_total".to_string(),
                        },
                        Label {
                            name: "method".to_string(),
                            value: "GET".to_string(),
                        },
                    ],
                    samples: vec![
                        Sample {
                            value: 100.0,
                            timestamp: 1234567890000,
                        },
                        Sample {
                            value: 150.0,
                            timestamp: 1234567891000,
                        },
                    ],
                },
                TimeSeries {
                    labels: vec![Label {
                        name: "__name__".to_string(),
                        value: "http_latency_seconds".to_string(),
                    }],
                    samples: vec![Sample {
                        value: 0.5,
                        timestamp: 1234567890000,
                    }],
                },
            ],
        };

        let mut buf = Vec::new();
        request.encode(&mut buf).unwrap();

        // Compress with snappy
        let compressed = snap::raw::Encoder::new()
            .compress_vec(&buf)
            .expect("compression should succeed");

        let request = Request::builder()
            .method("POST")
            .uri("/api/v1/write")
            .header("content-type", "application/x-protobuf")
            .header("content-encoding", "snappy")
            .body(Body::from(compressed))
            .unwrap();

        let response = app.oneshot(request).await.unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(buffer.buffered_count(), 3); // 2 + 1 samples
    }

    #[tokio::test]
    async fn test_loki_endpoint_full_flow() {
        let buffer = Arc::new(IngestionBuffer::new(100));
        let app = ingestion_router(buffer.clone());

        let json = r#"{
            "streams": [
                {
                    "stream": {
                        "app": "frontend",
                        "namespace": "production"
                    },
                    "values": [
                        ["1676466135000000000", "User login successful"],
                        ["1676466136000000000", "User session started"]
                    ]
                },
                {
                    "stream": {
                        "app": "backend",
                        "namespace": "production"
                    },
                    "values": [
                        ["1676466137000000000", "Database query executed"]
                    ]
                }
            ]
        }"#;

        let request = Request::builder()
            .method("POST")
            .uri("/loki/api/v1/push")
            .header("content-type", "application/json")
            .body(Body::from(json))
            .unwrap();

        let response = app.oneshot(request).await.unwrap();

        assert_eq!(response.status(), StatusCode::NO_CONTENT);
        assert_eq!(buffer.buffered_count(), 3); // 2 + 1 log entries
    }

    #[tokio::test]
    async fn test_concurrent_ingestion() {
        let buffer = Arc::new(IngestionBuffer::new(100));

        // Create multiple requests in parallel
        let mut handles = vec![];

        for i in 0..5 {
            let buffer_clone = buffer.clone();
            let handle = tokio::spawn(async move {
                let app = ingestion_router(buffer_clone);

                let json = format!(
                    r#"{{"streams":[{{"stream":{{"batch":"{}"}},"values":[["1234567890000000000","log {}"]]}}]}}"#,
                    i, i
                );

                let request = Request::builder()
                    .method("POST")
                    .uri("/loki/api/v1/push")
                    .header("content-type", "application/json")
                    .body(Body::from(json))
                    .unwrap();

                app.oneshot(request).await.unwrap()
            });
            handles.push(handle);
        }

        // Wait for all requests to complete
        for handle in handles {
            let response = handle.await.unwrap();
            assert_eq!(response.status(), StatusCode::NO_CONTENT);
        }

        // All 5 log entries should be buffered
        assert_eq!(buffer.buffered_count(), 5);
    }

    #[tokio::test]
    async fn test_mixed_prometheus_and_loki_ingestion() {
        let buffer = Arc::new(IngestionBuffer::new(100));

        // First send Prometheus metrics
        let app = ingestion_router(buffer.clone());

        let request = WriteRequest {
            timeseries: vec![TimeSeries {
                labels: vec![Label {
                    name: "__name__".to_string(),
                    value: "test_metric".to_string(),
                }],
                samples: vec![Sample {
                    value: 42.0,
                    timestamp: 1234567890000,
                }],
            }],
        };

        let mut buf = Vec::new();
        request.encode(&mut buf).unwrap();
        let compressed = snap::raw::Encoder::new().compress_vec(&buf).unwrap();

        let prom_request = Request::builder()
            .method("POST")
            .uri("/api/v1/write")
            .header("content-type", "application/x-protobuf")
            .header("content-encoding", "snappy")
            .body(Body::from(compressed))
            .unwrap();

        let prom_response = app.oneshot(prom_request).await.unwrap();
        assert_eq!(prom_response.status(), StatusCode::OK);

        // Then send Loki logs
        let app = ingestion_router(buffer.clone());

        let loki_json = r#"{"streams":[{"stream":{"app":"test"},"values":[["1234567890000000000","test log"]]}]}"#;

        let loki_request = Request::builder()
            .method("POST")
            .uri("/loki/api/v1/push")
            .header("content-type", "application/json")
            .body(Body::from(loki_json))
            .unwrap();

        let loki_response = app.oneshot(loki_request).await.unwrap();
        assert_eq!(loki_response.status(), StatusCode::NO_CONTENT);

        // Both should be buffered
        assert_eq!(buffer.buffered_count(), 2);
    }
}
