//! Source CRD definition
//!
//! Represents a data source (Prometheus or Loki) that Beeper monitors
//! for anomalies and queries during investigations.

use kube::CustomResource;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

/// Specification for a Source resource
#[derive(CustomResource, Deserialize, Serialize, Clone, Debug, JsonSchema)]
#[kube(
    group = "beeper.dev",
    version = "v1",
    kind = "Source",
    namespaced,
    status = "SourceStatus",
    shortname = "src"
)]
#[serde(rename_all = "snake_case")]
pub struct SourceSpec {
    /// Type of data source: "prometheus" or "loki"
    pub source_type: SourceType,

    /// URL endpoint for the data source
    pub endpoint: String,

    /// Name of the K8s Secret containing credentials (optional)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub credentials_secret: Option<String>,
}

/// Type of observability data source
#[derive(Deserialize, Serialize, Clone, Debug, JsonSchema, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum SourceType {
    Prometheus,
    Loki,
}

/// Status of a Source resource
#[derive(Deserialize, Serialize, Clone, Debug, Default, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub struct SourceStatus {
    /// Whether the source is currently connected
    #[serde(skip_serializing_if = "Option::is_none")]
    pub connected: Option<bool>,

    /// Last time the connection was checked (ISO 8601)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_checked: Option<String>,

    /// Error message if connection failed
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,

    /// Retry count for exponential backoff (resets on successful connection)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub retry_count: Option<u32>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_source_spec_serialization() {
        let spec = SourceSpec {
            source_type: SourceType::Prometheus,
            endpoint: "http://prometheus:9090".to_string(),
            credentials_secret: Some("prometheus-creds".to_string()),
        };

        let json = serde_json::to_string(&spec).unwrap();
        assert!(json.contains("\"source_type\":\"prometheus\""));
        assert!(json.contains("\"endpoint\":\"http://prometheus:9090\""));
        assert!(json.contains("\"credentials_secret\":\"prometheus-creds\""));
    }

    #[test]
    fn test_source_status_serialization() {
        let status = SourceStatus {
            connected: Some(true),
            last_checked: Some("2026-02-09T12:00:00Z".to_string()),
            error: None,
            retry_count: None,
        };

        let json = serde_json::to_string(&status).unwrap();
        assert!(json.contains("\"connected\":true"));
        assert!(json.contains("\"last_checked\":\"2026-02-09T12:00:00Z\""));
        assert!(!json.contains("error")); // None should be skipped
        assert!(!json.contains("retry_count")); // None should be skipped
    }

    #[test]
    fn test_source_type_enum() {
        let prometheus: SourceType = serde_json::from_str("\"prometheus\"").unwrap();
        assert_eq!(prometheus, SourceType::Prometheus);

        let loki: SourceType = serde_json::from_str("\"loki\"").unwrap();
        assert_eq!(loki, SourceType::Loki);
    }
}
