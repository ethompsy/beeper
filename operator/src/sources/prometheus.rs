//! Prometheus client for querying metrics
//!
//! Provides async client for executing PromQL queries against a Prometheus server.

use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use reqwest::Client;
use serde::Deserialize;
use std::collections::HashMap;
use std::time::Duration;
use thiserror::Error;
use tracing::{debug, warn};

/// Error types for Prometheus client operations
#[derive(Debug, Error)]
pub enum PrometheusError {
    #[error("HTTP request failed: {0}")]
    HttpError(#[from] reqwest::Error),

    #[error("Prometheus API error ({error_type}): {message}")]
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

/// Credentials for Prometheus authentication
#[derive(Clone, Debug)]
pub struct Credentials {
    pub username: String,
    pub password: String,
}

impl Credentials {
    /// Create credentials from base64-encoded username and password
    pub fn from_base64(username_b64: &str, password_b64: &str) -> Result<Self, PrometheusError> {
        let username =
            String::from_utf8(BASE64.decode(username_b64).map_err(|e| {
                PrometheusError::AuthError(format!("Invalid base64 username: {}", e))
            })?)
            .map_err(|e| PrometheusError::AuthError(format!("Invalid UTF-8 username: {}", e)))?;

        let password =
            String::from_utf8(BASE64.decode(password_b64).map_err(|e| {
                PrometheusError::AuthError(format!("Invalid base64 password: {}", e))
            })?)
            .map_err(|e| PrometheusError::AuthError(format!("Invalid UTF-8 password: {}", e)))?;

        Ok(Self { username, password })
    }

    /// Create credentials from plain text username and password
    pub fn new(username: String, password: String) -> Self {
        Self { username, password }
    }

    /// Build the Basic Auth header value
    pub fn to_basic_auth_header(&self) -> String {
        let credentials = format!("{}:{}", self.username, self.password);
        format!("Basic {}", BASE64.encode(credentials.as_bytes()))
    }
}

/// Prometheus API response wrapper
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct PrometheusResponse<T> {
    status: String,
    #[serde(default)]
    error_type: Option<String>,
    #[serde(default)]
    error: Option<String>,
    #[serde(default)]
    data: Option<T>,
}

/// Result of an instant query
#[derive(Debug, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct QueryData {
    pub result_type: String,
    pub result: Vec<QueryResultItem>,
}

/// Single result item from a query
#[derive(Debug, Deserialize, Clone)]
pub struct QueryResultItem {
    pub metric: HashMap<String, String>,
    pub value: Option<(f64, String)>,
    pub values: Option<Vec<(f64, String)>>,
}

/// Result of an instant PromQL query
#[derive(Debug, Clone)]
pub struct QueryResult {
    pub result_type: String,
    pub results: Vec<QueryResultItem>,
}

/// Result of a range PromQL query
#[derive(Debug, Clone)]
pub struct RangeResult {
    pub result_type: String,
    pub results: Vec<QueryResultItem>,
}

/// Client for querying Prometheus
#[derive(Clone)]
pub struct PrometheusClient {
    endpoint: String,
    credentials: Option<Credentials>,
    client: Client,
    timeout: Duration,
}

impl PrometheusClient {
    /// Create a new Prometheus client
    ///
    /// # Arguments
    /// * `endpoint` - Base URL of Prometheus server (e.g., "http://prometheus:9090")
    /// * `credentials` - Optional credentials for Basic Auth
    pub fn new(
        endpoint: String,
        credentials: Option<Credentials>,
    ) -> Result<Self, PrometheusError> {
        let client = Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .map_err(PrometheusError::HttpError)?;

        // Normalize endpoint - remove trailing slash
        let endpoint = endpoint.trim_end_matches('/').to_string();

        Ok(Self {
            endpoint,
            credentials,
            client,
            timeout: Duration::from_secs(30),
        })
    }

    /// Create a new Prometheus client with custom timeout
    pub fn with_timeout(mut self, timeout: Duration) -> Self {
        self.timeout = timeout;
        self
    }

    /// Execute an instant PromQL query
    ///
    /// # Arguments
    /// * `promql` - The PromQL query expression
    pub async fn query(&self, promql: &str) -> Result<QueryResult, PrometheusError> {
        let url = format!("{}/api/v1/query", self.endpoint);
        debug!(query = %promql, url = %url, "Executing instant query");

        let mut request = self.client.get(&url).query(&[("query", promql)]);

        if let Some(ref creds) = self.credentials {
            request = request.header("Authorization", creds.to_basic_auth_header());
        }

        let response = request.send().await.map_err(|e| {
            if e.is_timeout() {
                PrometheusError::Timeout(self.timeout.as_secs())
            } else if e.is_connect() {
                PrometheusError::ConnectionError {
                    message: format!(
                        "Connection refused at {} - verify endpoint is accessible",
                        self.endpoint
                    ),
                }
            } else {
                PrometheusError::HttpError(e)
            }
        })?;

        // Check for auth failure
        if response.status() == reqwest::StatusCode::UNAUTHORIZED {
            return Err(PrometheusError::AuthError(
                "Authentication failed - verify credentials are correct".to_string(),
            ));
        }

        if response.status() == reqwest::StatusCode::FORBIDDEN {
            return Err(PrometheusError::AuthError(
                "Access forbidden - verify credentials have read access".to_string(),
            ));
        }

        let prom_response: PrometheusResponse<QueryData> = response.json().await.map_err(|e| {
            PrometheusError::ParseError(format!("Failed to parse Prometheus response: {}", e))
        })?;

        if prom_response.status == "error" {
            return Err(PrometheusError::ApiError {
                error_type: prom_response
                    .error_type
                    .unwrap_or_else(|| "unknown".to_string()),
                message: prom_response
                    .error
                    .unwrap_or_else(|| "Unknown error".to_string()),
            });
        }

        let data = prom_response.data.ok_or_else(|| {
            PrometheusError::ParseError("Response missing data field".to_string())
        })?;

        Ok(QueryResult {
            result_type: data.result_type,
            results: data.result,
        })
    }

    /// Execute a range PromQL query
    ///
    /// # Arguments
    /// * `promql` - The PromQL query expression
    /// * `start` - Start timestamp (RFC3339 or Unix timestamp)
    /// * `end` - End timestamp (RFC3339 or Unix timestamp)
    /// * `step` - Query resolution step (e.g., "15s", "1m", "5m")
    pub async fn query_range(
        &self,
        promql: &str,
        start: &str,
        end: &str,
        step: &str,
    ) -> Result<RangeResult, PrometheusError> {
        let url = format!("{}/api/v1/query_range", self.endpoint);
        debug!(
            query = %promql,
            start = %start,
            end = %end,
            step = %step,
            url = %url,
            "Executing range query"
        );

        let mut request = self.client.get(&url).query(&[
            ("query", promql),
            ("start", start),
            ("end", end),
            ("step", step),
        ]);

        if let Some(ref creds) = self.credentials {
            request = request.header("Authorization", creds.to_basic_auth_header());
        }

        let response = request.send().await.map_err(|e| {
            if e.is_timeout() {
                PrometheusError::Timeout(self.timeout.as_secs())
            } else if e.is_connect() {
                PrometheusError::ConnectionError {
                    message: format!(
                        "Connection refused at {} - verify endpoint is accessible",
                        self.endpoint
                    ),
                }
            } else {
                PrometheusError::HttpError(e)
            }
        })?;

        // Check for auth failure
        if response.status() == reqwest::StatusCode::UNAUTHORIZED {
            return Err(PrometheusError::AuthError(
                "Authentication failed - verify credentials are correct".to_string(),
            ));
        }

        if response.status() == reqwest::StatusCode::FORBIDDEN {
            return Err(PrometheusError::AuthError(
                "Access forbidden - verify credentials have read access".to_string(),
            ));
        }

        let prom_response: PrometheusResponse<QueryData> = response.json().await.map_err(|e| {
            PrometheusError::ParseError(format!("Failed to parse Prometheus response: {}", e))
        })?;

        if prom_response.status == "error" {
            return Err(PrometheusError::ApiError {
                error_type: prom_response
                    .error_type
                    .unwrap_or_else(|| "unknown".to_string()),
                message: prom_response
                    .error
                    .unwrap_or_else(|| "Unknown error".to_string()),
            });
        }

        let data = prom_response.data.ok_or_else(|| {
            PrometheusError::ParseError("Response missing data field".to_string())
        })?;

        Ok(RangeResult {
            result_type: data.result_type,
            results: data.result,
        })
    }

    /// Check if Prometheus is reachable and responding
    ///
    /// Executes a simple `up` query to verify connectivity.
    pub async fn check_health(&self) -> Result<bool, PrometheusError> {
        debug!(endpoint = %self.endpoint, "Checking Prometheus health");

        match self.query("up").await {
            Ok(_) => {
                debug!(endpoint = %self.endpoint, "Prometheus health check passed");
                Ok(true)
            }
            Err(e) => {
                warn!(endpoint = %self.endpoint, error = %e, "Prometheus health check failed");
                Err(e)
            }
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
    fn test_credentials_new() {
        let creds = Credentials::new("user".to_string(), "pass".to_string());
        assert_eq!(creds.username, "user");
        assert_eq!(creds.password, "pass");
    }

    #[test]
    fn test_credentials_from_base64() {
        // "user" in base64 is "dXNlcg=="
        // "pass" in base64 is "cGFzcw=="
        let creds = Credentials::from_base64("dXNlcg==", "cGFzcw==").unwrap();
        assert_eq!(creds.username, "user");
        assert_eq!(creds.password, "pass");
    }

    #[test]
    fn test_credentials_from_base64_invalid() {
        let result = Credentials::from_base64("not-valid-base64!", "cGFzcw==");
        assert!(result.is_err());
    }

    #[test]
    fn test_basic_auth_header() {
        let creds = Credentials::new("user".to_string(), "pass".to_string());
        let header = creds.to_basic_auth_header();
        // "user:pass" in base64 is "dXNlcjpwYXNz"
        assert_eq!(header, "Basic dXNlcjpwYXNz");
    }

    #[test]
    fn test_prometheus_error_display() {
        let err = PrometheusError::ApiError {
            error_type: "bad_data".to_string(),
            message: "invalid query".to_string(),
        };
        assert_eq!(
            err.to_string(),
            "Prometheus API error (bad_data): invalid query"
        );
    }

    #[test]
    fn test_prometheus_client_normalizes_endpoint() {
        let client = PrometheusClient::new("http://prometheus:9090/".to_string(), None).unwrap();
        assert_eq!(client.endpoint(), "http://prometheus:9090");
    }

    #[test]
    fn test_query_result_parsing() {
        let json = r#"{
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {
                        "metric": {"__name__": "up", "job": "prometheus"},
                        "value": [1234567890.123, "1"]
                    }
                ]
            }
        }"#;

        let response: PrometheusResponse<QueryData> = serde_json::from_str(json).unwrap();
        assert_eq!(response.status, "success");
        assert!(response.data.is_some());

        let data = response.data.unwrap();
        assert_eq!(data.result_type, "vector");
        assert_eq!(data.result.len(), 1);
        assert_eq!(
            data.result[0].metric.get("__name__"),
            Some(&"up".to_string())
        );
    }

    #[test]
    fn test_error_response_parsing() {
        let json = r#"{
            "status": "error",
            "errorType": "bad_data",
            "error": "invalid expression"
        }"#;

        let response: PrometheusResponse<QueryData> = serde_json::from_str(json).unwrap();
        assert_eq!(response.status, "error");
        assert_eq!(response.error_type, Some("bad_data".to_string()));
        assert_eq!(response.error, Some("invalid expression".to_string()));
    }

    #[test]
    fn test_range_result_parsing() {
        let json = r#"{
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"__name__": "up", "job": "prometheus"},
                        "values": [
                            [1234567890.123, "1"],
                            [1234567900.123, "1"]
                        ]
                    }
                ]
            }
        }"#;

        let response: PrometheusResponse<QueryData> = serde_json::from_str(json).unwrap();
        assert_eq!(response.status, "success");
        assert!(response.data.is_some());

        let data = response.data.unwrap();
        assert_eq!(data.result_type, "matrix");
        assert_eq!(data.result.len(), 1);
        assert!(data.result[0].values.is_some());
        assert_eq!(data.result[0].values.as_ref().unwrap().len(), 2);
    }
}

#[cfg(test)]
mod integration_tests {
    use super::*;
    use wiremock::matchers::{method, path, query_param};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    #[tokio::test]
    async fn test_query_success() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/api/v1/query"))
            .and(query_param("query", "up"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {
                            "metric": {"__name__": "up", "job": "prometheus"},
                            "value": [1234567890.123, "1"]
                        }
                    ]
                }
            })))
            .mount(&mock_server)
            .await;

        let client = PrometheusClient::new(mock_server.uri(), None).unwrap();
        let result = client.query("up").await.unwrap();

        assert_eq!(result.result_type, "vector");
        assert_eq!(result.results.len(), 1);
        assert_eq!(
            result.results[0].metric.get("__name__"),
            Some(&"up".to_string())
        );
    }

    #[tokio::test]
    async fn test_query_with_auth() {
        use wiremock::matchers::header;

        let mock_server = MockServer::start().await;

        // Verify Authorization header is sent with correct Basic Auth value
        // "user:pass" in base64 is "dXNlcjpwYXNz"
        Mock::given(method("GET"))
            .and(path("/api/v1/query"))
            .and(header("Authorization", "Basic dXNlcjpwYXNz"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": []
                }
            })))
            .mount(&mock_server)
            .await;

        let creds = Credentials::new("user".to_string(), "pass".to_string());
        let client = PrometheusClient::new(mock_server.uri(), Some(creds)).unwrap();
        let result = client.query("up").await;

        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_query_auth_failure() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/api/v1/query"))
            .respond_with(ResponseTemplate::new(401))
            .mount(&mock_server)
            .await;

        let client = PrometheusClient::new(mock_server.uri(), None).unwrap();
        let result = client.query("up").await;

        assert!(matches!(result, Err(PrometheusError::AuthError(_))));
    }

    #[tokio::test]
    async fn test_query_api_error() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/api/v1/query"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "status": "error",
                "errorType": "bad_data",
                "error": "invalid expression"
            })))
            .mount(&mock_server)
            .await;

        let client = PrometheusClient::new(mock_server.uri(), None).unwrap();
        let result = client.query("invalid{").await;

        assert!(matches!(
            result,
            Err(PrometheusError::ApiError { error_type, .. }) if error_type == "bad_data"
        ));
    }

    #[tokio::test]
    async fn test_query_range_success() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/api/v1/query_range"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "status": "success",
                "data": {
                    "resultType": "matrix",
                    "result": [
                        {
                            "metric": {"__name__": "up"},
                            "values": [
                                [1234567890.0, "1"],
                                [1234567900.0, "1"]
                            ]
                        }
                    ]
                }
            })))
            .mount(&mock_server)
            .await;

        let client = PrometheusClient::new(mock_server.uri(), None).unwrap();
        let result = client
            .query_range("up", "1234567890", "1234567900", "10s")
            .await
            .unwrap();

        assert_eq!(result.result_type, "matrix");
        assert_eq!(result.results.len(), 1);
        assert!(result.results[0].values.is_some());
    }

    #[tokio::test]
    async fn test_health_check_success() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/api/v1/query"))
            .and(query_param("query", "up"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [{"metric": {}, "value": [0, "1"]}]
                }
            })))
            .mount(&mock_server)
            .await;

        let client = PrometheusClient::new(mock_server.uri(), None).unwrap();
        let result = client.check_health().await;

        assert!(result.is_ok());
        assert!(result.unwrap());
    }

    #[tokio::test]
    async fn test_health_check_failure() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/api/v1/query"))
            .respond_with(ResponseTemplate::new(500))
            .mount(&mock_server)
            .await;

        let client = PrometheusClient::new(mock_server.uri(), None).unwrap();
        let result = client.check_health().await;

        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_connection_refused() {
        // Use a port that's not listening
        let client = PrometheusClient::new("http://127.0.0.1:59999".to_string(), None).unwrap();
        let result = client.query("up").await;

        assert!(matches!(
            result,
            Err(PrometheusError::ConnectionError { .. }) | Err(PrometheusError::HttpError(_))
        ));
    }
}
