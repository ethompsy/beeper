//! ServiceLevel CRD definition
//!
//! Represents an SLO (Service Level Objective) configuration for a service.
//! Admins define SLIs, targets, and burn rate alert thresholds via this CRD.
//! The operator reconciles it, validates the spec, and reports status.

use kube::CustomResource;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

/// Specification for a ServiceLevel resource
#[derive(CustomResource, Deserialize, Serialize, Clone, Debug, JsonSchema)]
#[kube(
    group = "beeper.dev",
    version = "v1",
    kind = "ServiceLevel",
    namespaced,
    status = "ServiceLevelStatus",
    shortname = "slo"
)]
#[serde(rename_all = "snake_case")]
pub struct ServiceLevelSpec {
    /// Name of the service this SLO applies to
    pub service: String,

    /// Service Level Indicator definition
    pub sli: SliSpec,

    /// SLO objective (target and measurement window)
    pub objective: ObjectiveSpec,

    /// Burn rate alert thresholds (optional)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub burn_rate_alerts: Option<Vec<BurnRateAlert>>,
}

/// Service Level Indicator specification
#[derive(Deserialize, Serialize, Clone, Debug, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub struct SliSpec {
    /// Type of SLI: availability, latency, or error_rate
    #[serde(rename = "type")]
    pub sli_type: SliType,

    /// Prometheus metric name to query
    pub metric: String,

    /// PromQL selector for "good" events (e.g., '{status=~"2.."}')
    pub good_selector: String,

    /// PromQL selector for total events (e.g., '{}')
    pub total_selector: String,
}

/// Type of Service Level Indicator
#[derive(Deserialize, Serialize, Clone, Debug, JsonSchema, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum SliType {
    Availability,
    Latency,
    ErrorRate,
}

/// SLO objective specification
#[derive(Deserialize, Serialize, Clone, Debug, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub struct ObjectiveSpec {
    /// Target ratio (0.0 to 1.0, e.g., 0.999 for 99.9%)
    pub target: f64,

    /// Measurement window (e.g., "30d", "7d")
    pub window: String,
}

/// Burn rate alert threshold configuration
#[derive(Deserialize, Serialize, Clone, Debug, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub struct BurnRateAlert {
    /// Alert severity level (e.g., "warning", "critical")
    pub severity: String,

    /// Short observation window (e.g., "5m")
    pub short_window: String,

    /// Long observation window (e.g., "1h", "6h")
    pub long_window: String,

    /// Burn rate factor threshold (e.g., 14.4 for fast burn, 6.0 for slow burn)
    pub factor: f64,
}

/// Current condition of a ServiceLevel resource
#[derive(Deserialize, Serialize, Clone, Debug, Default, JsonSchema, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum ServiceLevelCondition {
    /// SLO is within budget and operating normally
    #[default]
    Healthy,
    /// SLO is approaching budget limits
    Warning,
    /// SLO is breaching or has critical issues
    Critical,
}

/// Status of a ServiceLevel resource
#[derive(Deserialize, Serialize, Clone, Debug, Default, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub struct ServiceLevelStatus {
    /// Current condition of the SLO (healthy/warning/critical)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub condition: Option<ServiceLevelCondition>,

    /// Last time the ServiceLevel was evaluated (ISO 8601)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_evaluated: Option<String>,

    /// Number of burn rate alert thresholds registered
    #[serde(skip_serializing_if = "Option::is_none")]
    pub alerts_registered: Option<u32>,

    /// Error message if validation or reconciliation failed
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

/// Validate a ServiceLevelSpec and return an error message if invalid
pub fn validate_spec(spec: &ServiceLevelSpec) -> Result<(), String> {
    if spec.service.is_empty() {
        return Err("spec.service must not be empty".to_string());
    }

    if spec.sli.metric.is_empty() {
        return Err("spec.sli.metric must not be empty".to_string());
    }

    if spec.sli.good_selector.is_empty() {
        return Err("spec.sli.good_selector must not be empty".to_string());
    }

    if spec.sli.total_selector.is_empty() {
        return Err("spec.sli.total_selector must not be empty".to_string());
    }

    if spec.objective.target.is_nan()
        || spec.objective.target < 0.0
        || spec.objective.target > 1.0
    {
        return Err(format!(
            "spec.objective.target must be between 0.0 and 1.0, got {}",
            spec.objective.target
        ));
    }

    if spec.objective.window.is_empty() {
        return Err("spec.objective.window must not be empty".to_string());
    }

    if let Some(alerts) = &spec.burn_rate_alerts {
        for (i, alert) in alerts.iter().enumerate() {
            if alert.severity.is_empty() {
                return Err(format!(
                    "spec.burn_rate_alerts[{}].severity must not be empty",
                    i
                ));
            }
            if alert.short_window.is_empty() {
                return Err(format!(
                    "spec.burn_rate_alerts[{}].short_window must not be empty",
                    i
                ));
            }
            if alert.long_window.is_empty() {
                return Err(format!(
                    "spec.burn_rate_alerts[{}].long_window must not be empty",
                    i
                ));
            }
            if alert.factor <= 0.0 {
                return Err(format!(
                    "spec.burn_rate_alerts[{}].factor must be positive, got {}",
                    i, alert.factor
                ));
            }
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_spec() -> ServiceLevelSpec {
        ServiceLevelSpec {
            service: "payment-service".to_string(),
            sli: SliSpec {
                sli_type: SliType::Availability,
                metric: "http_requests_total".to_string(),
                good_selector: "{status=~\"2..\"}".to_string(),
                total_selector: "{}".to_string(),
            },
            objective: ObjectiveSpec {
                target: 0.999,
                window: "30d".to_string(),
            },
            burn_rate_alerts: Some(vec![
                BurnRateAlert {
                    severity: "warning".to_string(),
                    short_window: "5m".to_string(),
                    long_window: "1h".to_string(),
                    factor: 14.4,
                },
                BurnRateAlert {
                    severity: "critical".to_string(),
                    short_window: "5m".to_string(),
                    long_window: "6h".to_string(),
                    factor: 6.0,
                },
            ]),
        }
    }

    #[test]
    fn test_servicelevel_spec_serialization() {
        let spec = sample_spec();
        let json = serde_json::to_string(&spec).unwrap();
        assert!(json.contains("\"service\":\"payment-service\""));
        assert!(json.contains("\"type\":\"availability\""));
        assert!(json.contains("\"metric\":\"http_requests_total\""));
        assert!(json.contains("\"target\":0.999"));
        assert!(json.contains("\"window\":\"30d\""));
    }

    #[test]
    fn test_servicelevel_spec_without_burn_rate_alerts() {
        let spec = ServiceLevelSpec {
            service: "auth-service".to_string(),
            sli: SliSpec {
                sli_type: SliType::Latency,
                metric: "http_request_duration_seconds".to_string(),
                good_selector: "{le=\"0.5\"}".to_string(),
                total_selector: "{}".to_string(),
            },
            objective: ObjectiveSpec {
                target: 0.95,
                window: "7d".to_string(),
            },
            burn_rate_alerts: None,
        };

        let json = serde_json::to_string(&spec).unwrap();
        assert!(json.contains("\"service\":\"auth-service\""));
        assert!(json.contains("\"type\":\"latency\""));
        assert!(!json.contains("burn_rate_alerts")); // None should be skipped
    }

    #[test]
    fn test_servicelevel_status_serialization() {
        let status = ServiceLevelStatus {
            condition: Some(ServiceLevelCondition::Healthy),
            last_evaluated: Some("2026-03-14T12:00:00Z".to_string()),
            alerts_registered: Some(2),
            error: None,
        };

        let json = serde_json::to_string(&status).unwrap();
        assert!(json.contains("\"condition\":\"healthy\""));
        assert!(json.contains("\"last_evaluated\":\"2026-03-14T12:00:00Z\""));
        assert!(json.contains("\"alerts_registered\":2"));
        assert!(!json.contains("error")); // None should be skipped
    }

    #[test]
    fn test_servicelevel_status_with_error() {
        let status = ServiceLevelStatus {
            condition: Some(ServiceLevelCondition::Critical),
            last_evaluated: Some("2026-03-14T12:00:00Z".to_string()),
            alerts_registered: None,
            error: Some("spec.objective.target must be between 0.0 and 1.0".to_string()),
        };

        let json = serde_json::to_string(&status).unwrap();
        assert!(json.contains("\"condition\":\"critical\""));
        assert!(json.contains("\"error\":"));
        assert!(!json.contains("alerts_registered")); // None should be skipped
    }

    #[test]
    fn test_servicelevel_status_empty() {
        let status = ServiceLevelStatus::default();
        let json = serde_json::to_string(&status).unwrap();
        assert_eq!(json, "{}");
    }

    #[test]
    fn test_sli_type_enum() {
        let availability: SliType = serde_json::from_str("\"availability\"").unwrap();
        assert_eq!(availability, SliType::Availability);

        let latency: SliType = serde_json::from_str("\"latency\"").unwrap();
        assert_eq!(latency, SliType::Latency);

        let error_rate: SliType = serde_json::from_str("\"error_rate\"").unwrap();
        assert_eq!(error_rate, SliType::ErrorRate);
    }

    #[test]
    fn test_servicelevel_condition_enum() {
        let healthy: ServiceLevelCondition = serde_json::from_str("\"healthy\"").unwrap();
        assert_eq!(healthy, ServiceLevelCondition::Healthy);

        let warning: ServiceLevelCondition = serde_json::from_str("\"warning\"").unwrap();
        assert_eq!(warning, ServiceLevelCondition::Warning);

        let critical: ServiceLevelCondition = serde_json::from_str("\"critical\"").unwrap();
        assert_eq!(critical, ServiceLevelCondition::Critical);
    }

    #[test]
    fn test_servicelevel_condition_default() {
        let condition: ServiceLevelCondition = Default::default();
        assert_eq!(condition, ServiceLevelCondition::Healthy);
    }

    #[test]
    fn test_burn_rate_alert_serialization() {
        let alert = BurnRateAlert {
            severity: "warning".to_string(),
            short_window: "5m".to_string(),
            long_window: "1h".to_string(),
            factor: 14.4,
        };

        let json = serde_json::to_string(&alert).unwrap();
        assert!(json.contains("\"severity\":\"warning\""));
        assert!(json.contains("\"short_window\":\"5m\""));
        assert!(json.contains("\"long_window\":\"1h\""));
        assert!(json.contains("\"factor\":14.4"));
    }

    #[test]
    fn test_sli_spec_serialization() {
        let sli = SliSpec {
            sli_type: SliType::ErrorRate,
            metric: "http_errors_total".to_string(),
            good_selector: "{status!~\"5..\"}".to_string(),
            total_selector: "{}".to_string(),
        };

        let json = serde_json::to_string(&sli).unwrap();
        assert!(json.contains("\"type\":\"error_rate\""));
        assert!(json.contains("\"metric\":\"http_errors_total\""));
        assert!(json.contains("\"good_selector\":"));
        assert!(json.contains("\"total_selector\":\"{}\""));
    }

    #[test]
    fn test_objective_spec_serialization() {
        let objective = ObjectiveSpec {
            target: 0.999,
            window: "30d".to_string(),
        };

        let json = serde_json::to_string(&objective).unwrap();
        assert!(json.contains("\"target\":0.999"));
        assert!(json.contains("\"window\":\"30d\""));
    }

    #[test]
    fn test_spec_deserialization_from_yaml_format() {
        let json = r#"{
            "service": "payment-service",
            "sli": {
                "type": "availability",
                "metric": "http_requests_total",
                "good_selector": "{status=~\"2..\"}",
                "total_selector": "{}"
            },
            "objective": {
                "target": 0.999,
                "window": "30d"
            },
            "burn_rate_alerts": [
                {
                    "severity": "critical",
                    "short_window": "5m",
                    "long_window": "6h",
                    "factor": 6.0
                }
            ]
        }"#;

        let spec: ServiceLevelSpec = serde_json::from_str(json).unwrap();
        assert_eq!(spec.service, "payment-service");
        assert_eq!(spec.sli.sli_type, SliType::Availability);
        assert_eq!(spec.objective.target, 0.999);
        assert_eq!(spec.burn_rate_alerts.as_ref().unwrap().len(), 1);
        assert_eq!(
            spec.burn_rate_alerts.as_ref().unwrap()[0].severity,
            "critical"
        );
    }

    // Validation tests

    #[test]
    fn test_validate_spec_valid() {
        let spec = sample_spec();
        assert!(validate_spec(&spec).is_ok());
    }

    #[test]
    fn test_validate_spec_empty_service() {
        let mut spec = sample_spec();
        spec.service = "".to_string();
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("service must not be empty"));
    }

    #[test]
    fn test_validate_spec_empty_metric() {
        let mut spec = sample_spec();
        spec.sli.metric = "".to_string();
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("metric must not be empty"));
    }

    #[test]
    fn test_validate_spec_empty_good_selector() {
        let mut spec = sample_spec();
        spec.sli.good_selector = "".to_string();
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .contains("good_selector must not be empty"));
    }

    #[test]
    fn test_validate_spec_empty_total_selector() {
        let mut spec = sample_spec();
        spec.sli.total_selector = "".to_string();
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .contains("total_selector must not be empty"));
    }

    #[test]
    fn test_validate_spec_target_too_high() {
        let mut spec = sample_spec();
        spec.objective.target = 1.5;
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("between 0.0 and 1.0"));
    }

    #[test]
    fn test_validate_spec_target_negative() {
        let mut spec = sample_spec();
        spec.objective.target = -0.1;
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("between 0.0 and 1.0"));
    }

    #[test]
    fn test_validate_spec_target_boundary_zero() {
        let mut spec = sample_spec();
        spec.objective.target = 0.0;
        assert!(validate_spec(&spec).is_ok());
    }

    #[test]
    fn test_validate_spec_target_boundary_one() {
        let mut spec = sample_spec();
        spec.objective.target = 1.0;
        assert!(validate_spec(&spec).is_ok());
    }

    #[test]
    fn test_validate_spec_target_nan() {
        let mut spec = sample_spec();
        spec.objective.target = f64::NAN;
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("between 0.0 and 1.0"));
    }

    #[test]
    fn test_validate_spec_empty_window() {
        let mut spec = sample_spec();
        spec.objective.window = "".to_string();
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("window must not be empty"));
    }

    #[test]
    fn test_validate_spec_burn_rate_alert_empty_severity() {
        let mut spec = sample_spec();
        spec.burn_rate_alerts.as_mut().unwrap()[0].severity = "".to_string();
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("severity must not be empty"));
    }

    #[test]
    fn test_validate_spec_burn_rate_alert_zero_factor() {
        let mut spec = sample_spec();
        spec.burn_rate_alerts.as_mut().unwrap()[0].factor = 0.0;
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("factor must be positive"));
    }

    #[test]
    fn test_validate_spec_burn_rate_alert_negative_factor() {
        let mut spec = sample_spec();
        spec.burn_rate_alerts.as_mut().unwrap()[0].factor = -1.0;
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("factor must be positive"));
    }

    #[test]
    fn test_validate_spec_no_burn_rate_alerts() {
        let mut spec = sample_spec();
        spec.burn_rate_alerts = None;
        assert!(validate_spec(&spec).is_ok());
    }

    #[test]
    fn test_validate_spec_empty_burn_rate_alerts_vec() {
        let mut spec = sample_spec();
        spec.burn_rate_alerts = Some(vec![]);
        assert!(validate_spec(&spec).is_ok());
    }
}
