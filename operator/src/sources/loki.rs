//! Loki client for querying logs
//!
//! Provides async client for executing LogQL queries against a Loki server.

use reqwest::Client;
use serde::Deserialize;
use std::collections::HashMap;
use std::time::Duration;
use thiserror::Error;
use tracing::{debug, warn};

use super::Credentials;

/// Error types for Loki client operations
#[derive(Debug, Error)]
pub enum LokiError {
    #[error("HTTP request failed: {0}")]
    HttpError(#[from] reqwest::Error),

    #[error("Loki API error ({error_type}): {message}")]
    ApiError { error_type: String, message: String },

    #[error("Failed to parse response: {0}")]
    ParseError(String),

    #[error("Connection failed: {message}")]
    ConnectionError { message: String },

    #[error("Authentication failed: {0}")]
    AuthError(String),

    #[error("Query timeout after {0} seconds")]
    Timeout(u64),
}

/// Loki API response wrapper
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct LokiResponse<T> {
    status: String,
    #[serde(default)]
    error_type: Option<String>,
    #[serde(default)]
    error: Option<String>,
    #[serde(default)]
    data: Option<T>,
}

/// Result data from a Loki query
#[derive(Debug, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct LogQueryData {
    pub result_type: String,
    pub result: Vec<LogStream>,
}

/// A single log stream from Loki
#[derive(Debug, Deserialize, Clone)]
pub struct LogStream {
    /// Labels identifying this stream
    pub stream: HashMap<String, String>,
    /// Log entries as [timestamp_nanos, log_line] tuples
    pub values: Vec<(String, String)>,
}

/// Result of an instant LogQL query
#[derive(Debug, Clone)]
pub struct QueryResult {
    pub result_type: String,
    pub streams: Vec<LogStream>,
}

/// Result of a range LogQL query
#[derive(Debug, Clone)]
pub struct RangeResult {
    pub result_type: String,
    pub streams: Vec<LogStream>,
}

/// Client for querying Loki
#[derive(Clone)]
pub struct LokiClient {
    endpoint: String,
    credentials: Option<Credentials>,
    client: Client,
    timeout: Duration,
}

impl LokiClient {
    /// Create a new Loki client
    ///
    /// # Arguments
    /// * `endpoint` - Base URL of Loki server (e.g., "http://loki:3100")
    /// * `credentials` - Optional credentials for Basic Auth
    pub fn new(endpoint: String, credentials: Option<Credentials>) -> Result<Self, LokiError> {
        Self::with_timeout_secs(endpoint, credentials, 30)
    }

    /// Create a new Loki client with custom timeout in seconds
    fn with_timeout_secs(
        endpoint: String,
        credentials: Option<Credentials>,
        timeout_secs: u64,
    ) -> Result<Self, LokiError> {
        let timeout = Duration::from_secs(timeout_secs);
        let client = Client::builder()
            .timeout(timeout)
            .build()
            .map_err(LokiError::HttpError)?;

        // Normalize endpoint - remove trailing slash
        let endpoint = endpoint.trim_end_matches('/').to_string();

        Ok(Self {
            endpoint,
            credentials,
            client,
            timeout,
        })
    }

    /// Create a new Loki client with custom timeout
    ///
    /// Note: This rebuilds the HTTP client with the new timeout.
    pub fn with_timeout(self, timeout: Duration) -> Result<Self, LokiError> {
        let client = Client::builder()
            .timeout(timeout)
            .build()
            .map_err(LokiError::HttpError)?;

        Ok(Self {
            endpoint: self.endpoint,
            credentials: self.credentials,
            client,
            timeout,
        })
    }

    /// Send a request and handle common error cases
    async fn send_request(
        &self,
        request: reqwest::RequestBuilder,
    ) -> Result<reqwest::Response, LokiError> {
        let response = request.send().await.map_err(|e| {
            if e.is_timeout() {
                LokiError::Timeout(self.timeout.as_secs())
            } else if e.is_connect() {
                LokiError::ConnectionError {
                    message: format!(
                        "Connection refused at {} - verify endpoint is accessible",
                        self.endpoint
                    ),
                }
            } else {
                LokiError::HttpError(e)
            }
        })?;

        // Check for auth failure
        if response.status() == reqwest::StatusCode::UNAUTHORIZED {
            return Err(LokiError::AuthError(
                "Authentication failed - verify credentials are correct".to_string(),
            ));
        }

        if response.status() == reqwest::StatusCode::FORBIDDEN {
            return Err(LokiError::AuthError(
                "Access forbidden - verify credentials have read access".to_string(),
            ));
        }

        Ok(response)
    }

    /// Execute an instant LogQL query
    ///
    /// # Arguments
    /// * `logql` - The LogQL query expression
    pub async fn query(&self, logql: &str) -> Result<QueryResult, LokiError> {
        let url = format!("{}/loki/api/v1/query", self.endpoint);
        debug!(query = %logql, url = %url, "Executing instant query");

        let mut request = self.client.get(&url).query(&[("query", logql)]);

        if let Some(ref creds) = self.credentials {
            request = request.header("Authorization", creds.to_basic_auth_header());
        }

        let response = self.send_request(request).await?;

        let loki_response: LokiResponse<LogQueryData> = response.json().await.map_err(|e| {
            LokiError::ParseError(format!("Failed to parse Loki response: {}", e))
        })?;

        if loki_response.status == "error" {
            return Err(LokiError::ApiError {
                error_type: loki_response.error_type.unwrap_or_else(|| "unknown".to_string()),
                message: loki_response.error.unwrap_or_else(|| "Unknown error".to_string()),
            });
        }

        let data = loki_response.data.ok_or_else(|| {
            LokiError::ParseError("Response missing data field".to_string())
        })?;

        Ok(QueryResult {
            result_type: data.result_type,
            streams: data.result,
        })
    }

    /// Execute a range LogQL query
    ///
    /// # Arguments
    /// * `logql` - The LogQL query expression
    /// * `start` - Start timestamp in nanoseconds
    /// * `end` - End timestamp in nanoseconds
    /// * `limit` - Maximum number of entries to return
    pub async fn query_range(
        &self,
        logql: &str,
        start: i64,
        end: i64,
        limit: u32,
    ) -> Result<RangeResult, LokiError> {
        let url = format!("{}/loki/api/v1/query_range", self.endpoint);
        debug!(
            query = %logql,
            start = %start,
            end = %end,
            limit = %limit,
            url = %url,
            "Executing range query"
        );

        let mut request = self.client.get(&url).query(&[
            ("query", logql),
            ("start", &start.to_string()),
            ("end", &end.to_string()),
            ("limit", &limit.to_string()),
        ]);

        if let Some(ref creds) = self.credentials {
            request = request.header("Authorization", creds.to_basic_auth_header());
        }

        let response = self.send_request(request).await?;

        let loki_response: LokiResponse<LogQueryData> = response.json().await.map_err(|e| {
            LokiError::ParseError(format!("Failed to parse Loki response: {}", e))
        })?;

        if loki_response.status == "error" {
            return Err(LokiError::ApiError {
                error_type: loki_response.error_type.unwrap_or_else(|| "unknown".to_string()),
                message: loki_response.error.unwrap_or_else(|| "Unknown error".to_string()),
            });
        }

        let data = loki_response.data.ok_or_else(|| {
            LokiError::ParseError("Response missing data field".to_string())
        })?;

        Ok(RangeResult {
            result_type: data.result_type,
            streams: data.result,
        })
    }

    /// Check if Loki is reachable and responding
    ///
    /// Uses the /ready endpoint which is designed for liveness/readiness probes
    /// and doesn't require authentication.
    pub async fn check_health(&self) -> Result<bool, LokiError> {
        debug!(endpoint = %self.endpoint, "Checking Loki health");

        let url = format!("{}/ready", self.endpoint);

        let response = self.client.get(&url).send().await.map_err(|e| {
            if e.is_timeout() {
                LokiError::Timeout(self.timeout.as_secs())
            } else if e.is_connect() {
                LokiError::ConnectionError {
                    message: format!(
                        "Connection refused at {} - verify endpoint is accessible",
                        self.endpoint
                    ),
                }
            } else {
                LokiError::HttpError(e)
            }
        })?;

        if response.status().is_success() {
            debug!(endpoint = %self.endpoint, "Loki health check passed");
            Ok(true)
        } else {
            warn!(
                endpoint = %self.endpoint,
                status = %response.status(),
                "Loki health check failed"
            );
            Err(LokiError::ApiError {
                error_type: "health_check_failed".to_string(),
                message: format!("Health check returned status {}", response.status()),
            })
        }
    }

    /// Get the endpoint URL
    pub fn endpoint(&self) -> &str {
        &self.endpoint
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_loki_error_display() {
        let err = LokiError::ApiError {
            error_type: "bad_data".to_string(),
            message: "invalid query".to_string(),
        };
        assert_eq!(
            err.to_string(),
            "Loki API error (bad_data): invalid query"
        );
    }

    #[test]
    fn test_loki_client_normalizes_endpoint() {
        let client = LokiClient::new(
            "http://loki:3100/".to_string(),
            None,
        )
        .unwrap();
        assert_eq!(client.endpoint(), "http://loki:3100");
    }

    #[test]
    fn test_with_timeout() {
        let client = LokiClient::new("http://loki:3100".to_string(), None)
            .unwrap()
            .with_timeout(Duration::from_secs(60))
            .unwrap();
        // Verify timeout is stored (used for error messages)
        assert_eq!(client.timeout, Duration::from_secs(60));
    }

    #[test]
    fn test_query_result_parsing() {
        let json = r#"{
            "status": "success",
            "data": {
                "resultType": "streams",
                "result": [
                    {
                        "stream": {"app": "myapp", "level": "error"},
                        "values": [
                            ["1676466135000000000", "error log line here"],
                            ["1676466136000000000", "another error"]
                        ]
                    }
                ]
            }
        }"#;

        let response: LokiResponse<LogQueryData> = serde_json::from_str(json).unwrap();
        assert_eq!(response.status, "success");
        assert!(response.data.is_some());

        let data = response.data.unwrap();
        assert_eq!(data.result_type, "streams");
        assert_eq!(data.result.len(), 1);
        assert_eq!(
            data.result[0].stream.get("app"),
            Some(&"myapp".to_string())
        );
        assert_eq!(data.result[0].values.len(), 2);
        assert_eq!(data.result[0].values[0].1, "error log line here");
    }

    #[test]
    fn test_error_response_parsing() {
        let json = r#"{
            "status": "error",
            "errorType": "bad_data",
            "error": "invalid LogQL expression"
        }"#;

        let response: LokiResponse<LogQueryData> = serde_json::from_str(json).unwrap();
        assert_eq!(response.status, "error");
        assert_eq!(response.error_type, Some("bad_data".to_string()));
        assert_eq!(response.error, Some("invalid LogQL expression".to_string()));
    }

    #[test]
    fn test_log_stream_parsing() {
        let json = r#"{
            "stream": {"namespace": "production", "pod": "api-server-abc123"},
            "values": [
                ["1676466135000000000", "GET /health 200 5ms"],
                ["1676466136000000000", "GET /api/v1/users 200 125ms"],
                ["1676466137000000000", "POST /api/v1/orders 201 89ms"]
            ]
        }"#;

        let stream: LogStream = serde_json::from_str(json).unwrap();
        assert_eq!(stream.stream.get("namespace"), Some(&"production".to_string()));
        assert_eq!(stream.stream.get("pod"), Some(&"api-server-abc123".to_string()));
        assert_eq!(stream.values.len(), 3);

        // Verify timestamp format (nanoseconds as string)
        assert_eq!(stream.values[0].0, "1676466135000000000");
        assert_eq!(stream.values[0].1, "GET /health 200 5ms");
    }

    #[test]
    fn test_timeout_error() {
        let err = LokiError::Timeout(30);
        assert_eq!(err.to_string(), "Query timeout after 30 seconds");
    }

    #[test]
    fn test_connection_error() {
        let err = LokiError::ConnectionError {
            message: "Connection refused at http://loki:3100".to_string(),
        };
        assert!(err.to_string().contains("Connection refused"));
    }

    #[test]
    fn test_auth_error() {
        let err = LokiError::AuthError("Authentication failed".to_string());
        assert_eq!(err.to_string(), "Authentication failed: Authentication failed");
    }
}

#[cfg(test)]
mod integration_tests {
    use super::*;
    use crate::sources::Credentials;
    use wiremock::matchers::{header, method, path, query_param};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    #[tokio::test]
    async fn test_query_success() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/loki/api/v1/query"))
            .and(query_param("query", "{app=\"test\"}"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "status": "success",
                "data": {
                    "resultType": "streams",
                    "result": [
                        {
                            "stream": {"app": "test"},
                            "values": [
                                ["1676466135000000000", "test log line"]
                            ]
                        }
                    ]
                }
            })))
            .mount(&mock_server)
            .await;

        let client = LokiClient::new(mock_server.uri(), None).unwrap();
        let result = client.query("{app=\"test\"}").await.unwrap();

        assert_eq!(result.result_type, "streams");
        assert_eq!(result.streams.len(), 1);
        assert_eq!(
            result.streams[0].stream.get("app"),
            Some(&"test".to_string())
        );
    }

    #[tokio::test]
    async fn test_query_with_auth() {
        let mock_server = MockServer::start().await;

        // Verify Authorization header is sent with correct Basic Auth value
        // "user:pass" in base64 is "dXNlcjpwYXNz"
        Mock::given(method("GET"))
            .and(path("/loki/api/v1/query"))
            .and(header("Authorization", "Basic dXNlcjpwYXNz"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "status": "success",
                "data": {
                    "resultType": "streams",
                    "result": []
                }
            })))
            .mount(&mock_server)
            .await;

        let creds = Credentials::new("user".to_string(), "pass".to_string());
        let client = LokiClient::new(mock_server.uri(), Some(creds)).unwrap();
        let result = client.query("{app=\"test\"}").await;

        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_query_auth_failure() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/loki/api/v1/query"))
            .respond_with(ResponseTemplate::new(401))
            .mount(&mock_server)
            .await;

        let client = LokiClient::new(mock_server.uri(), None).unwrap();
        let result = client.query("{app=\"test\"}").await;

        assert!(matches!(result, Err(LokiError::AuthError(_))));
    }

    #[tokio::test]
    async fn test_query_api_error() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/loki/api/v1/query"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "status": "error",
                "errorType": "bad_data",
                "error": "invalid LogQL expression"
            })))
            .mount(&mock_server)
            .await;

        let client = LokiClient::new(mock_server.uri(), None).unwrap();
        let result = client.query("invalid{").await;

        assert!(matches!(
            result,
            Err(LokiError::ApiError { error_type, .. }) if error_type == "bad_data"
        ));
    }

    #[tokio::test]
    async fn test_query_range_success() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/loki/api/v1/query_range"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "status": "success",
                "data": {
                    "resultType": "streams",
                    "result": [
                        {
                            "stream": {"app": "test"},
                            "values": [
                                ["1676466135000000000", "log line 1"],
                                ["1676466136000000000", "log line 2"]
                            ]
                        }
                    ]
                }
            })))
            .mount(&mock_server)
            .await;

        let client = LokiClient::new(mock_server.uri(), None).unwrap();
        let result = client
            .query_range("{app=\"test\"}", 1676466135000000000, 1676466140000000000, 100)
            .await
            .unwrap();

        assert_eq!(result.result_type, "streams");
        assert_eq!(result.streams.len(), 1);
        assert_eq!(result.streams[0].values.len(), 2);
    }

    #[tokio::test]
    async fn test_health_check_success() {
        let mock_server = MockServer::start().await;

        // /ready endpoint returns simple "ready" text, not JSON
        Mock::given(method("GET"))
            .and(path("/ready"))
            .respond_with(ResponseTemplate::new(200).set_body_string("ready"))
            .mount(&mock_server)
            .await;

        let client = LokiClient::new(mock_server.uri(), None).unwrap();
        let result = client.check_health().await;

        assert!(result.is_ok());
        assert!(result.unwrap());
    }

    #[tokio::test]
    async fn test_health_check_failure() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/ready"))
            .respond_with(ResponseTemplate::new(503).set_body_string("not ready"))
            .mount(&mock_server)
            .await;

        let client = LokiClient::new(mock_server.uri(), None).unwrap();
        let result = client.check_health().await;

        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_health_check_no_auth_required() {
        let mock_server = MockServer::start().await;

        // /ready endpoint doesn't require auth - verify it works without sending auth header
        Mock::given(method("GET"))
            .and(path("/ready"))
            .respond_with(ResponseTemplate::new(200).set_body_string("ready"))
            .mount(&mock_server)
            .await;

        // Even with credentials configured, health check doesn't send them
        let creds = Credentials::new("user".to_string(), "pass".to_string());
        let client = LokiClient::new(mock_server.uri(), Some(creds)).unwrap();
        let result = client.check_health().await;

        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_connection_refused() {
        // Use a port that's not listening
        let client = LokiClient::new("http://127.0.0.1:59998".to_string(), None).unwrap();
        let result = client.query("{app=\"test\"}").await;

        assert!(matches!(
            result,
            Err(LokiError::ConnectionError { .. }) | Err(LokiError::HttpError(_))
        ));
    }
}
