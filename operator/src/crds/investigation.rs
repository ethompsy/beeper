//! Investigation CRD definition
//!
//! Represents an active or completed investigation triggered by
//! anomaly detection. Each investigation spawns an investigator
//! pod to analyze the condition.

use kube::CustomResource;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

/// Specification for an Investigation resource
#[derive(CustomResource, Deserialize, Serialize, Clone, Debug, JsonSchema)]
#[kube(
    group = "beeper.dev",
    version = "v1",
    kind = "Investigation",
    namespaced,
    status = "InvestigationStatus",
    shortname = "inv"
)]
#[serde(rename_all = "snake_case")]
pub struct InvestigationSpec {
    /// Description of the detected condition triggering investigation
    pub condition: String,

    /// Name of the affected service
    pub service: String,

    /// Severity level of the condition
    #[serde(default)]
    pub severity: Severity,

    /// When the condition was first detected (ISO 8601)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub triggered_at: Option<String>,

    /// Customer impact score (0.0–1.0) based on SLO data.
    /// None when no SLO data is available for the service.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub impact_score: Option<f64>,
}

/// Severity level of an investigation
#[derive(Deserialize, Serialize, Clone, Debug, Default, JsonSchema, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum Severity {
    Low,
    #[default]
    Medium,
    High,
    Critical,
}

/// Status of an Investigation resource
#[derive(Deserialize, Serialize, Clone, Debug, Default, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub struct InvestigationStatus {
    /// Current phase of the investigation
    #[serde(skip_serializing_if = "Option::is_none")]
    pub phase: Option<InvestigationPhase>,

    /// When the investigation started (ISO 8601)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub started_at: Option<String>,

    /// When the investigation completed (ISO 8601)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub completed_at: Option<String>,

    /// Name of the K8s Job running the investigator
    #[serde(skip_serializing_if = "Option::is_none")]
    pub job_name: Option<String>,

    /// Error message if investigation failed
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,

    /// Progress message from the investigator pod
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
}

/// Phase of an investigation lifecycle
#[derive(Deserialize, Serialize, Clone, Debug, JsonSchema, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum InvestigationPhase {
    Pending,
    Running,
    #[serde(rename = "awaiting_confirmation")]
    AwaitingConfirmation,
    Completed,
    Failed,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_investigation_spec_serialization() {
        let spec = InvestigationSpec {
            condition: "High error rate detected".to_string(),
            service: "payments".to_string(),
            severity: Severity::High,
            triggered_at: Some("2026-02-09T12:00:00Z".to_string()),
            impact_score: None,
        };

        let json = serde_json::to_string(&spec).unwrap();
        assert!(json.contains("\"condition\":\"High error rate detected\""));
        assert!(json.contains("\"service\":\"payments\""));
        assert!(json.contains("\"severity\":\"high\""));
        assert!(json.contains("\"triggered_at\":\"2026-02-09T12:00:00Z\""));
        // impact_score is None, should be absent from JSON
        assert!(!json.contains("impact_score"));
    }

    #[test]
    fn test_investigation_spec_with_impact_score() {
        let spec = InvestigationSpec {
            condition: "SLO burn rate alert".to_string(),
            service: "payment-service".to_string(),
            severity: Severity::Critical,
            triggered_at: Some("2026-03-14T12:00:00Z".to_string()),
            impact_score: Some(0.85),
        };

        let json = serde_json::to_string(&spec).unwrap();
        assert!(json.contains("\"impact_score\":0.85"));
    }

    #[test]
    fn test_investigation_spec_impact_score_backward_compat() {
        // Deserializing without impact_score should default to None
        let json = r#"{"condition":"test","service":"svc","severity":"medium"}"#;
        let spec: InvestigationSpec = serde_json::from_str(json).unwrap();
        assert!(spec.impact_score.is_none());
    }

    #[test]
    fn test_investigation_status_serialization() {
        let status = InvestigationStatus {
            phase: Some(InvestigationPhase::Running),
            started_at: Some("2026-02-09T12:00:00Z".to_string()),
            completed_at: None,
            job_name: Some("inv-abc123".to_string()),
            error: None,
            message: None,
        };

        let json = serde_json::to_string(&status).unwrap();
        assert!(json.contains("\"phase\":\"running\""));
        assert!(json.contains("\"started_at\":\"2026-02-09T12:00:00Z\""));
        assert!(json.contains("\"job_name\":\"inv-abc123\""));
        assert!(!json.contains("completed_at")); // None should be skipped
        assert!(!json.contains("error")); // None should be skipped
        assert!(!json.contains("message")); // None should be skipped
    }

    #[test]
    fn test_investigation_status_message_serialization() {
        let status = InvestigationStatus {
            phase: Some(InvestigationPhase::Running),
            started_at: None,
            completed_at: None,
            job_name: None,
            error: None,
            message: Some("Correlating signals...".to_string()),
        };

        let json = serde_json::to_string(&status).unwrap();
        assert!(json.contains("\"message\":\"Correlating signals...\""));
    }

    #[test]
    fn test_severity_default() {
        let severity: Severity = Default::default();
        assert_eq!(severity, Severity::Medium);
    }

    #[test]
    fn test_investigation_phase_enum() {
        let pending: InvestigationPhase = serde_json::from_str("\"pending\"").unwrap();
        assert_eq!(pending, InvestigationPhase::Pending);

        let running: InvestigationPhase = serde_json::from_str("\"running\"").unwrap();
        assert_eq!(running, InvestigationPhase::Running);

        let awaiting: InvestigationPhase =
            serde_json::from_str("\"awaiting_confirmation\"").unwrap();
        assert_eq!(awaiting, InvestigationPhase::AwaitingConfirmation);

        let completed: InvestigationPhase = serde_json::from_str("\"completed\"").unwrap();
        assert_eq!(completed, InvestigationPhase::Completed);

        let failed: InvestigationPhase = serde_json::from_str("\"failed\"").unwrap();
        assert_eq!(failed, InvestigationPhase::Failed);
    }

    #[test]
    fn test_awaiting_confirmation_phase_serialization() {
        let status = InvestigationStatus {
            phase: Some(InvestigationPhase::AwaitingConfirmation),
            started_at: Some("2026-03-07T10:00:00Z".to_string()),
            completed_at: None,
            job_name: None,
            error: None,
            message: Some("Awaiting SRE confirmation".to_string()),
        };

        let json = serde_json::to_string(&status).unwrap();
        assert!(json.contains("\"phase\":\"awaiting_confirmation\""));
        assert!(json.contains("\"message\":\"Awaiting SRE confirmation\""));
    }
}
