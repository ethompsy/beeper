//! Prometheus remote_write ingestion handler
//!
//! Implements the Prometheus remote write protocol:
//! - HTTP POST to `/api/v1/write`
//! - Content-Type: `application/x-protobuf`
//! - Content-Encoding: `snappy`
//! - Body: Snappy-compressed protobuf of `prometheus.WriteRequest`

use std::collections::HashMap;
use std::sync::Arc;

use axum::{
    body::Bytes,
    extract::State,
    http::{HeaderMap, StatusCode},
    response::IntoResponse,
};
use prost::Message;
use tracing::{debug, info, warn};

use super::buffer::{IngestionBuffer, IngestionData, MetricSample};

// Prometheus remote write protobuf definitions
// Based on https://github.com/prometheus/prometheus/blob/main/prompb/types.proto

/// WriteRequest represents a batch of samples to be written
#[derive(Clone, PartialEq, Message)]
pub struct WriteRequest {
    #[prost(message, repeated, tag = "1")]
    pub timeseries: Vec<TimeSeries>,
}

/// TimeSeries represents a single time series with labels and samples
#[derive(Clone, PartialEq, Message)]
pub struct TimeSeries {
    #[prost(message, repeated, tag = "1")]
    pub labels: Vec<Label>,
    #[prost(message, repeated, tag = "2")]
    pub samples: Vec<Sample>,
}

/// Label is a key-value pair
#[derive(Clone, PartialEq, Message)]
pub struct Label {
    #[prost(string, tag = "1")]
    pub name: String,
    #[prost(string, tag = "2")]
    pub value: String,
}

/// Sample is a single data point
#[derive(Clone, PartialEq, Message)]
pub struct Sample {
    #[prost(double, tag = "1")]
    pub value: f64,
    #[prost(int64, tag = "2")]
    pub timestamp: i64,
}

/// Handle Prometheus remote_write requests
pub async fn prometheus_write_handler(
    State(buffer): State<Arc<IngestionBuffer>>,
    headers: HeaderMap,
    body: Bytes,
) -> impl IntoResponse {
    // Log the incoming request
    debug!(
        content_length = body.len(),
        "Received Prometheus remote_write request"
    );

    // Validate content type
    let content_type = headers
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");

    if !content_type.contains("application/x-protobuf") {
        warn!(content_type = content_type, "Invalid content type");
        return (
            StatusCode::BAD_REQUEST,
            "Content-Type must be application/x-protobuf",
        );
    }

    // Decompress snappy if Content-Encoding indicates it
    let content_encoding = headers
        .get("content-encoding")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");

    let decompressed = if content_encoding.contains("snappy") {
        match snap::raw::Decoder::new().decompress_vec(&body) {
            Ok(data) => data,
            Err(e) => {
                warn!(error = %e, "Failed to decompress snappy data");
                return (StatusCode::BAD_REQUEST, "Failed to decompress snappy data");
            }
        }
    } else {
        body.to_vec()
    };

    // Parse the protobuf
    let write_request = match WriteRequest::decode(&decompressed[..]) {
        Ok(req) => req,
        Err(e) => {
            warn!(error = %e, "Failed to parse protobuf");
            return (StatusCode::BAD_REQUEST, "Failed to parse protobuf");
        }
    };

    // Convert to ingestion data and buffer
    let mut samples_count = 0;
    let mut buffered_count = 0;

    for ts in write_request.timeseries {
        // Extract labels into a HashMap
        let mut labels: HashMap<String, String> = ts
            .labels
            .iter()
            .map(|l| (l.name.clone(), l.value.clone()))
            .collect();

        // Get metric name from __name__ label
        let name = labels.remove("__name__").unwrap_or_default();

        for sample in ts.samples {
            samples_count += 1;

            let metric = MetricSample {
                name: name.clone(),
                labels: labels.clone(),
                value: sample.value,
                timestamp_ms: sample.timestamp,
            };

            if buffer.try_send(IngestionData::Metric(metric)).is_ok() {
                buffered_count += 1;
            }
        }
    }

    // Check if we're experiencing backpressure
    if buffered_count < samples_count {
        let dropped = samples_count - buffered_count;
        warn!(
            samples = samples_count,
            buffered = buffered_count,
            dropped = dropped,
            "Buffer full, some samples dropped"
        );
        return (StatusCode::SERVICE_UNAVAILABLE, "Buffer full, retry later");
    }

    info!(
        samples = samples_count,
        "Successfully buffered Prometheus samples"
    );

    (StatusCode::OK, "")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_write_request_decode() {
        // Create a sample WriteRequest
        let request = WriteRequest {
            timeseries: vec![TimeSeries {
                labels: vec![
                    Label {
                        name: "__name__".to_string(),
                        value: "test_metric".to_string(),
                    },
                    Label {
                        name: "job".to_string(),
                        value: "test_job".to_string(),
                    },
                ],
                samples: vec![Sample {
                    value: 42.0,
                    timestamp: 1234567890000,
                }],
            }],
        };

        // Encode and decode
        let mut buf = Vec::new();
        request.encode(&mut buf).unwrap();

        let decoded = WriteRequest::decode(&buf[..]).unwrap();
        assert_eq!(decoded.timeseries.len(), 1);
        assert_eq!(decoded.timeseries[0].labels.len(), 2);
        assert_eq!(decoded.timeseries[0].samples.len(), 1);
        assert_eq!(decoded.timeseries[0].samples[0].value, 42.0);
    }

    #[test]
    fn test_snappy_decompress() {
        let data = b"test data for compression";
        let compressed = snap::raw::Encoder::new()
            .compress_vec(data)
            .expect("compression should succeed");

        let decompressed = snap::raw::Decoder::new()
            .decompress_vec(&compressed)
            .expect("decompression should succeed");

        assert_eq!(&decompressed[..], data);
    }

    #[test]
    fn test_write_request_with_multiple_timeseries() {
        let request = WriteRequest {
            timeseries: vec![
                TimeSeries {
                    labels: vec![Label {
                        name: "__name__".to_string(),
                        value: "metric_a".to_string(),
                    }],
                    samples: vec![
                        Sample {
                            value: 1.0,
                            timestamp: 1000,
                        },
                        Sample {
                            value: 2.0,
                            timestamp: 2000,
                        },
                    ],
                },
                TimeSeries {
                    labels: vec![Label {
                        name: "__name__".to_string(),
                        value: "metric_b".to_string(),
                    }],
                    samples: vec![Sample {
                        value: 3.0,
                        timestamp: 3000,
                    }],
                },
            ],
        };

        let mut buf = Vec::new();
        request.encode(&mut buf).unwrap();

        let decoded = WriteRequest::decode(&buf[..]).unwrap();
        assert_eq!(decoded.timeseries.len(), 2);

        // Count total samples
        let total_samples: usize = decoded.timeseries.iter().map(|ts| ts.samples.len()).sum();
        assert_eq!(total_samples, 3);
    }

    #[tokio::test]
    async fn test_handler_with_valid_request() {
        let buffer = Arc::new(IngestionBuffer::new(100));

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

        // Compress with snappy
        let compressed = snap::raw::Encoder::new()
            .compress_vec(&buf)
            .expect("compression should succeed");

        let mut headers = HeaderMap::new();
        headers.insert("content-type", "application/x-protobuf".parse().unwrap());
        headers.insert("content-encoding", "snappy".parse().unwrap());

        let response =
            prometheus_write_handler(State(buffer.clone()), headers, Bytes::from(compressed))
                .await
                .into_response();

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(buffer.buffered_count(), 1);
    }

    #[tokio::test]
    async fn test_handler_invalid_content_type() {
        let buffer = Arc::new(IngestionBuffer::new(100));

        let mut headers = HeaderMap::new();
        headers.insert("content-type", "application/json".parse().unwrap());

        let response = prometheus_write_handler(State(buffer), headers, Bytes::new())
            .await
            .into_response();

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn test_handler_buffer_full() {
        // Create a tiny buffer that will overflow
        let buffer = Arc::new(IngestionBuffer::new(1));

        let request = WriteRequest {
            timeseries: vec![TimeSeries {
                labels: vec![Label {
                    name: "__name__".to_string(),
                    value: "test_metric".to_string(),
                }],
                samples: vec![
                    Sample {
                        value: 1.0,
                        timestamp: 1000,
                    },
                    Sample {
                        value: 2.0,
                        timestamp: 2000,
                    },
                    Sample {
                        value: 3.0,
                        timestamp: 3000,
                    },
                ],
            }],
        };

        let mut buf = Vec::new();
        request.encode(&mut buf).unwrap();

        let compressed = snap::raw::Encoder::new()
            .compress_vec(&buf)
            .expect("compression should succeed");

        let mut headers = HeaderMap::new();
        headers.insert("content-type", "application/x-protobuf".parse().unwrap());
        headers.insert("content-encoding", "snappy".parse().unwrap());

        let response =
            prometheus_write_handler(State(buffer.clone()), headers, Bytes::from(compressed))
                .await
                .into_response();

        // Should return 503 due to buffer overflow
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }
}
