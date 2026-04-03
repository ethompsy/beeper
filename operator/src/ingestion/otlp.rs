//! OTLP HTTP log ingestion handler
//!
//! Implements the OTLP HTTP log export protocol:
//! - HTTP POST to `/v1/logs`
//! - Content-Type: `application/json`
//! - Body: JSON `ExportLogsServiceRequest`
//!
//! The `otlphttp` exporter in OTel Collector sends JSON by default to
//! `{endpoint}/v1/logs`. This handler parses that format and converts
//! each LogRecord into the existing `LogEntry` struct for buffering.

use std::collections::HashMap;
use std::sync::Arc;

use axum::{
    extract::State,
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use serde::Deserialize;
use tracing::{debug, info, warn};

use super::buffer::{IngestionBuffer, IngestionData, LogEntry};

// --- OTLP JSON structs ---

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ExportLogsServiceRequest {
    #[serde(default)]
    pub resource_logs: Vec<ResourceLogs>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ResourceLogs {
    #[serde(default)]
    pub resource: Option<Resource>,
    #[serde(default)]
    pub scope_logs: Vec<ScopeLogs>,
}

#[derive(Debug, Deserialize)]
pub struct Resource {
    #[serde(default)]
    pub attributes: Vec<KeyValue>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ScopeLogs {
    #[serde(default)]
    pub log_records: Vec<LogRecord>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LogRecord {
    #[serde(default)]
    pub time_unix_nano: Option<String>,
    #[serde(default)]
    pub observed_time_unix_nano: Option<String>,
    #[serde(default)]
    pub severity_text: Option<String>,
    #[serde(default)]
    pub severity_number: Option<u32>,
    #[serde(default)]
    pub body: Option<AnyValue>,
    #[serde(default)]
    pub attributes: Vec<KeyValue>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct KeyValue {
    pub key: String,
    #[serde(default)]
    pub value: Option<AnyValue>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AnyValue {
    #[serde(default)]
    pub string_value: Option<String>,
    #[serde(default)]
    pub int_value: Option<String>,
    #[serde(default)]
    pub bool_value: Option<bool>,
}

impl AnyValue {
    fn as_string(&self) -> Option<String> {
        if let Some(s) = &self.string_value {
            Some(s.clone())
        } else if let Some(i) = &self.int_value {
            Some(i.clone())
        } else if let Some(b) = &self.bool_value {
            Some(b.to_string())
        } else {
            None
        }
    }
}

// --- Helper functions ---

/// Extract `service.name` from resource attributes
fn extract_service_name(resource: &Option<Resource>) -> Option<String> {
    resource.as_ref().and_then(|r| {
        r.attributes.iter().find_map(|kv| {
            if kv.key == "service.name" {
                kv.value.as_ref().and_then(|v| v.as_string())
            } else {
                None
            }
        })
    })
}

/// Map severity number to text if severity_text is missing
fn severity_text_from_number(num: u32) -> &'static str {
    match num {
        1..=4 => "TRACE",
        5..=8 => "DEBUG",
        9..=12 => "INFO",
        13..=16 => "WARN",
        17..=20 => "ERROR",
        21..=24 => "FATAL",
        _ => "UNSPECIFIED",
    }
}

/// Handle OTLP HTTP log export requests
pub async fn otlp_logs_handler(
    State(buffer): State<Arc<IngestionBuffer>>,
    Json(request): Json<ExportLogsServiceRequest>,
) -> impl IntoResponse {
    debug!(
        resource_logs_count = request.resource_logs.len(),
        "Received OTLP logs request"
    );

    let mut buffered_count: u64 = 0;
    let mut total_records: u64 = 0;

    for resource_logs in &request.resource_logs {
        let service_name = extract_service_name(&resource_logs.resource);

        for scope_logs in &resource_logs.scope_logs {
            for record in &scope_logs.log_records {
                total_records += 1;

                // Build labels
                let mut labels = HashMap::new();

                if let Some(ref svc) = service_name {
                    labels.insert("service_name".to_string(), svc.clone());
                }

                // Severity
                let level = record
                    .severity_text
                    .clone()
                    .unwrap_or_else(|| {
                        record
                            .severity_number
                            .map(severity_text_from_number)
                            .unwrap_or("UNSPECIFIED")
                            .to_string()
                    });
                labels.insert("level".to_string(), level);

                // Extra attributes from the log record
                for kv in &record.attributes {
                    if let Some(val) = kv.value.as_ref().and_then(|v| v.as_string()) {
                        labels.insert(kv.key.clone(), val);
                    }
                }

                // Body
                let line = record
                    .body
                    .as_ref()
                    .and_then(|v| v.as_string())
                    .unwrap_or_default();

                // Timestamp: prefer timeUnixNano, fall back to observedTimeUnixNano, then 0
                let timestamp_ns = record
                    .time_unix_nano
                    .as_deref()
                    .or(record.observed_time_unix_nano.as_deref())
                    .and_then(|s| s.parse::<i64>().ok())
                    .unwrap_or(0);

                let entry = LogEntry {
                    labels,
                    line,
                    timestamp_ns,
                };

                if buffer.try_send(IngestionData::Log(entry)).is_ok() {
                    buffered_count += 1;
                }
            }
        }
    }

    if buffered_count < total_records {
        let dropped = total_records - buffered_count;
        warn!(
            total = total_records,
            buffered = buffered_count,
            dropped = dropped,
            "Buffer full, some OTLP log entries dropped"
        );
        return StatusCode::TOO_MANY_REQUESTS;
    }

    info!(entries = buffered_count, "Successfully buffered OTLP log entries");
    StatusCode::OK
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_otlp_logs_request() {
        let json = r#"{
            "resourceLogs": [
                {
                    "resource": {
                        "attributes": [
                            {
                                "key": "service.name",
                                "value": { "stringValue": "cart" }
                            }
                        ]
                    },
                    "scopeLogs": [
                        {
                            "logRecords": [
                                {
                                    "timeUnixNano": "1234567890000000000",
                                    "severityText": "ERROR",
                                    "body": { "stringValue": "something broke" }
                                }
                            ]
                        }
                    ]
                }
            ]
        }"#;

        let req: ExportLogsServiceRequest = serde_json::from_str(json).unwrap();
        assert_eq!(req.resource_logs.len(), 1);
        let rl = &req.resource_logs[0];
        assert_eq!(
            extract_service_name(&rl.resource),
            Some("cart".to_string())
        );
        assert_eq!(rl.scope_logs[0].log_records[0].severity_text, Some("ERROR".to_string()));
    }

    #[test]
    fn test_severity_number_mapping() {
        assert_eq!(severity_text_from_number(1), "TRACE");
        assert_eq!(severity_text_from_number(5), "DEBUG");
        assert_eq!(severity_text_from_number(9), "INFO");
        assert_eq!(severity_text_from_number(13), "WARN");
        assert_eq!(severity_text_from_number(17), "ERROR");
        assert_eq!(severity_text_from_number(21), "FATAL");
        assert_eq!(severity_text_from_number(0), "UNSPECIFIED");
    }

    #[tokio::test]
    async fn test_handler_with_valid_request() {
        let buffer = Arc::new(IngestionBuffer::new(100));

        let request = ExportLogsServiceRequest {
            resource_logs: vec![ResourceLogs {
                resource: Some(Resource {
                    attributes: vec![KeyValue {
                        key: "service.name".to_string(),
                        value: Some(AnyValue {
                            string_value: Some("frontend".to_string()),
                            int_value: None,
                            bool_value: None,
                        }),
                    }],
                }),
                scope_logs: vec![ScopeLogs {
                    log_records: vec![
                        LogRecord {
                            time_unix_nano: Some("1234567890000000000".to_string()),
                            observed_time_unix_nano: None,
                            severity_text: Some("INFO".to_string()),
                            severity_number: Some(9),
                            body: Some(AnyValue {
                                string_value: Some("request handled".to_string()),
                                int_value: None,
                                bool_value: None,
                            }),
                            attributes: vec![],
                        },
                        LogRecord {
                            time_unix_nano: Some("1234567891000000000".to_string()),
                            observed_time_unix_nano: None,
                            severity_text: Some("ERROR".to_string()),
                            severity_number: Some(17),
                            body: Some(AnyValue {
                                string_value: Some("connection refused".to_string()),
                                int_value: None,
                                bool_value: None,
                            }),
                            attributes: vec![],
                        },
                    ],
                }],
            }],
        };

        let response = otlp_logs_handler(State(buffer.clone()), Json(request))
            .await
            .into_response();

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(buffer.buffered_count(), 2);
    }

    #[tokio::test]
    async fn test_handler_empty_request() {
        let buffer = Arc::new(IngestionBuffer::new(100));

        let request = ExportLogsServiceRequest {
            resource_logs: vec![],
        };

        let response = otlp_logs_handler(State(buffer.clone()), Json(request))
            .await
            .into_response();

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(buffer.buffered_count(), 0);
    }

    #[tokio::test]
    async fn test_handler_severity_number_fallback() {
        let buffer = Arc::new(IngestionBuffer::new(100));

        let request = ExportLogsServiceRequest {
            resource_logs: vec![ResourceLogs {
                resource: None,
                scope_logs: vec![ScopeLogs {
                    log_records: vec![LogRecord {
                        time_unix_nano: Some("1000000000".to_string()),
                        observed_time_unix_nano: None,
                        severity_text: None,
                        severity_number: Some(17),
                        body: Some(AnyValue {
                            string_value: Some("error log".to_string()),
                            int_value: None,
                            bool_value: None,
                        }),
                        attributes: vec![],
                    }],
                }],
            }],
        };

        let response = otlp_logs_handler(State(buffer.clone()), Json(request))
            .await
            .into_response();

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(buffer.buffered_count(), 1);
    }

    #[tokio::test]
    async fn test_handler_buffer_full() {
        let buffer = Arc::new(IngestionBuffer::new(1));

        let request = ExportLogsServiceRequest {
            resource_logs: vec![ResourceLogs {
                resource: None,
                scope_logs: vec![ScopeLogs {
                    log_records: vec![
                        LogRecord {
                            time_unix_nano: Some("1000000000".to_string()),
                            observed_time_unix_nano: None,
                            severity_text: Some("INFO".to_string()),
                            severity_number: None,
                            body: Some(AnyValue {
                                string_value: Some("log 1".to_string()),
                                int_value: None,
                                bool_value: None,
                            }),
                            attributes: vec![],
                        },
                        LogRecord {
                            time_unix_nano: Some("2000000000".to_string()),
                            observed_time_unix_nano: None,
                            severity_text: Some("INFO".to_string()),
                            severity_number: None,
                            body: Some(AnyValue {
                                string_value: Some("log 2".to_string()),
                                int_value: None,
                                bool_value: None,
                            }),
                            attributes: vec![],
                        },
                        LogRecord {
                            time_unix_nano: Some("3000000000".to_string()),
                            observed_time_unix_nano: None,
                            severity_text: Some("INFO".to_string()),
                            severity_number: None,
                            body: Some(AnyValue {
                                string_value: Some("log 3".to_string()),
                                int_value: None,
                                bool_value: None,
                            }),
                            attributes: vec![],
                        },
                    ],
                }],
            }],
        };

        let response = otlp_logs_handler(State(buffer.clone()), Json(request))
            .await
            .into_response();

        assert_eq!(response.status(), StatusCode::TOO_MANY_REQUESTS);
    }

    #[tokio::test]
    async fn test_handler_observed_time_fallback() {
        let buffer = Arc::new(IngestionBuffer::new(100));

        let request = ExportLogsServiceRequest {
            resource_logs: vec![ResourceLogs {
                resource: None,
                scope_logs: vec![ScopeLogs {
                    log_records: vec![LogRecord {
                        time_unix_nano: None,
                        observed_time_unix_nano: Some("9999999999000000000".to_string()),
                        severity_text: Some("DEBUG".to_string()),
                        severity_number: None,
                        body: Some(AnyValue {
                            string_value: Some("observed time log".to_string()),
                            int_value: None,
                            bool_value: None,
                        }),
                        attributes: vec![],
                    }],
                }],
            }],
        };

        let response = otlp_logs_handler(State(buffer.clone()), Json(request))
            .await
            .into_response();

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(buffer.buffered_count(), 1);
    }
}
