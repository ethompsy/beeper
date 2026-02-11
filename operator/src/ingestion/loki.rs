//! Loki push ingestion handler
//!
//! Implements the Loki push protocol:
//! - HTTP POST to `/loki/api/v1/push`
//! - Content-Type: `application/json`
//! - Body: JSON with streams array

use std::collections::HashMap;
use std::sync::Arc;

use axum::{
    body::Bytes,
    extract::State,
    http::{HeaderMap, StatusCode},
    response::IntoResponse,
};
use serde::Deserialize;
use tracing::{debug, info, warn};

use super::buffer::{IngestionBuffer, IngestionData, LogEntry};

/// Loki push request format
#[derive(Debug, Deserialize)]
pub struct LokiPushRequest {
    pub streams: Vec<LokiStream>,
}

/// A single log stream with labels and values
#[derive(Debug, Deserialize)]
pub struct LokiStream {
    /// Stream labels
    pub stream: HashMap<String, String>,
    /// Log entries as [timestamp_ns, log_line] tuples
    pub values: Vec<(String, String)>,
}

/// Handle Loki push requests
pub async fn loki_push_handler(
    State(buffer): State<Arc<IngestionBuffer>>,
    headers: HeaderMap,
    body: Bytes,
) -> impl IntoResponse {
    // Log the incoming request
    debug!(content_length = body.len(), "Received Loki push request");

    // Validate content type (must be JSON or protobuf)
    let content_type = headers
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");

    // Accept application/json or no content-type (for compatibility)
    // Reject other content types explicitly
    if !content_type.is_empty()
        && !content_type.contains("application/json")
        && !content_type.contains("application/x-protobuf")
    {
        warn!(content_type = content_type, "Invalid content type for Loki push");
        return (
            StatusCode::BAD_REQUEST,
            "Content-Type must be application/json",
        );
    }

    // Check for snappy compression
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

    // Parse the JSON body
    let push_request: LokiPushRequest = match serde_json::from_slice(&decompressed) {
        Ok(req) => req,
        Err(e) => {
            warn!(error = %e, "Failed to parse JSON body");
            return (StatusCode::BAD_REQUEST, "Invalid JSON format");
        }
    };

    // Convert to ingestion data and buffer
    let mut valid_entries_count = 0;
    let mut buffered_count = 0;
    let mut parse_errors = 0;

    for stream in push_request.streams {
        let labels = stream.stream;

        for (timestamp_str, line) in stream.values {
            // Parse timestamp (nanoseconds as string)
            let timestamp_ns = match timestamp_str.parse::<i64>() {
                Ok(ts) => ts,
                Err(e) => {
                    warn!(
                        error = %e,
                        timestamp = timestamp_str,
                        "Failed to parse timestamp, skipping entry"
                    );
                    parse_errors += 1;
                    continue;
                }
            };

            valid_entries_count += 1;

            let log_entry = LogEntry {
                labels: labels.clone(),
                line,
                timestamp_ns,
            };

            if buffer.try_send(IngestionData::Log(log_entry)).is_ok() {
                buffered_count += 1;
            }
        }
    }

    // Check if we're experiencing backpressure (only for valid entries)
    if buffered_count < valid_entries_count {
        let dropped = valid_entries_count - buffered_count;
        warn!(
            valid_entries = valid_entries_count,
            buffered = buffered_count,
            dropped = dropped,
            parse_errors = parse_errors,
            "Buffer full, some log entries dropped"
        );
        return (StatusCode::TOO_MANY_REQUESTS, "Buffer full, retry later");
    }

    if parse_errors > 0 {
        debug!(
            buffered = buffered_count,
            parse_errors = parse_errors,
            "Buffered Loki log entries with some parse errors"
        );
    } else {
        info!(
            entries = buffered_count,
            "Successfully buffered Loki log entries"
        );
    }

    // Loki expects 204 No Content on success
    (StatusCode::NO_CONTENT, "")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_loki_push_request() {
        let json = r#"{
            "streams": [
                {
                    "stream": {
                        "app": "myapp",
                        "level": "error"
                    },
                    "values": [
                        ["1676466135000000000", "log line 1"],
                        ["1676466136000000000", "log line 2"]
                    ]
                }
            ]
        }"#;

        let request: LokiPushRequest = serde_json::from_str(json).unwrap();
        assert_eq!(request.streams.len(), 1);
        assert_eq!(request.streams[0].stream.get("app").unwrap(), "myapp");
        assert_eq!(request.streams[0].values.len(), 2);
        assert_eq!(request.streams[0].values[0].1, "log line 1");
    }

    #[test]
    fn test_parse_multiple_streams() {
        let json = r#"{
            "streams": [
                {
                    "stream": {"app": "service-a"},
                    "values": [["1000000000", "log a"]]
                },
                {
                    "stream": {"app": "service-b"},
                    "values": [["2000000000", "log b"]]
                }
            ]
        }"#;

        let request: LokiPushRequest = serde_json::from_str(json).unwrap();
        assert_eq!(request.streams.len(), 2);
    }

    #[tokio::test]
    async fn test_handler_with_valid_request() {
        let buffer = Arc::new(IngestionBuffer::new(100));

        let json = r#"{
            "streams": [
                {
                    "stream": {"app": "test"},
                    "values": [["1234567890000000000", "test log line"]]
                }
            ]
        }"#;

        let mut headers = HeaderMap::new();
        headers.insert("content-type", "application/json".parse().unwrap());

        let response = loki_push_handler(State(buffer.clone()), headers, Bytes::from(json))
            .await
            .into_response();

        assert_eq!(response.status(), StatusCode::NO_CONTENT);
        assert_eq!(buffer.buffered_count(), 1);
    }

    #[tokio::test]
    async fn test_handler_with_snappy_compression() {
        let buffer = Arc::new(IngestionBuffer::new(100));

        let json = r#"{"streams":[{"stream":{"app":"test"},"values":[["1234567890000000000","compressed log"]]}]}"#;

        let compressed = snap::raw::Encoder::new()
            .compress_vec(json.as_bytes())
            .expect("compression should succeed");

        let mut headers = HeaderMap::new();
        headers.insert("content-type", "application/json".parse().unwrap());
        headers.insert("content-encoding", "snappy".parse().unwrap());

        let response = loki_push_handler(State(buffer.clone()), headers, Bytes::from(compressed))
            .await
            .into_response();

        assert_eq!(response.status(), StatusCode::NO_CONTENT);
        assert_eq!(buffer.buffered_count(), 1);
    }

    #[tokio::test]
    async fn test_handler_invalid_json() {
        let buffer = Arc::new(IngestionBuffer::new(100));

        let mut headers = HeaderMap::new();
        headers.insert("content-type", "application/json".parse().unwrap());

        let response = loki_push_handler(
            State(buffer),
            headers,
            Bytes::from("not valid json"),
        )
        .await
        .into_response();

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn test_handler_invalid_content_type() {
        let buffer = Arc::new(IngestionBuffer::new(100));

        let mut headers = HeaderMap::new();
        headers.insert("content-type", "text/plain".parse().unwrap());

        let response = loki_push_handler(
            State(buffer),
            headers,
            Bytes::from(r#"{"streams":[]}"#),
        )
        .await
        .into_response();

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn test_handler_no_content_type_accepted() {
        // Loki clients may not always send content-type, so we should accept it
        let buffer = Arc::new(IngestionBuffer::new(100));

        let headers = HeaderMap::new(); // No content-type header

        let json = r#"{"streams":[{"stream":{"app":"test"},"values":[["1234567890000000000","log"]]}]}"#;

        let response = loki_push_handler(State(buffer.clone()), headers, Bytes::from(json))
            .await
            .into_response();

        assert_eq!(response.status(), StatusCode::NO_CONTENT);
        assert_eq!(buffer.buffered_count(), 1);
    }

    #[tokio::test]
    async fn test_handler_buffer_full() {
        // Create a tiny buffer that will overflow
        let buffer = Arc::new(IngestionBuffer::new(1));

        let json = r#"{
            "streams": [
                {
                    "stream": {"app": "test"},
                    "values": [
                        ["1000000000", "log 1"],
                        ["2000000000", "log 2"],
                        ["3000000000", "log 3"]
                    ]
                }
            ]
        }"#;

        let mut headers = HeaderMap::new();
        headers.insert("content-type", "application/json".parse().unwrap());

        let response = loki_push_handler(State(buffer.clone()), headers, Bytes::from(json))
            .await
            .into_response();

        // Should return 429 due to buffer overflow
        assert_eq!(response.status(), StatusCode::TOO_MANY_REQUESTS);
    }

    #[tokio::test]
    async fn test_handler_invalid_timestamp() {
        let buffer = Arc::new(IngestionBuffer::new(100));

        // Invalid timestamp should be skipped but not fail the whole request
        let json = r#"{
            "streams": [
                {
                    "stream": {"app": "test"},
                    "values": [
                        ["invalid", "bad timestamp log"],
                        ["1234567890000000000", "valid log"]
                    ]
                }
            ]
        }"#;

        let mut headers = HeaderMap::new();
        headers.insert("content-type", "application/json".parse().unwrap());

        let response = loki_push_handler(State(buffer.clone()), headers, Bytes::from(json))
            .await
            .into_response();

        // Should succeed (only the valid entry is buffered)
        assert_eq!(response.status(), StatusCode::NO_CONTENT);
        assert_eq!(buffer.buffered_count(), 1);
    }
}
