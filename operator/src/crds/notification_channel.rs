//! NotificationChannel CRD definition
//!
//! Represents an outbound notification channel configuration.
//! Users configure channel type (slack/pagerduty/email/webhook),
//! credentials, and routing rules via this CRD.
//! The operator reconciles it, validates the spec, and reports status.

use std::collections::HashMap;

use kube::CustomResource;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

/// Specification for a NotificationChannel resource
#[derive(CustomResource, Deserialize, Serialize, Clone, Debug, JsonSchema)]
#[kube(
    group = "beeper.dev",
    version = "v1",
    kind = "NotificationChannel",
    namespaced,
    status = "NotificationChannelStatus",
    shortname = "nc"
)]
#[serde(rename_all = "snake_case")]
pub struct NotificationChannelSpec {
    /// Channel type: slack, pagerduty, email, or webhook
    #[serde(rename = "type")]
    pub channel_type: ChannelType,

    /// Channel-specific configuration key-value pairs
    pub config: HashMap<String, String>,

    /// Name of the K8s Secret containing channel credentials
    pub credentials_secret: String,

    /// Optional routing rules for this channel
    #[serde(skip_serializing_if = "Option::is_none")]
    pub routing: Option<RoutingConfig>,
}

/// Type of notification channel
#[derive(Deserialize, Serialize, Clone, Debug, JsonSchema, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum ChannelType {
    Slack,
    Pagerduty,
    Email,
    Webhook,
}

/// Routing configuration for a notification channel
#[derive(Deserialize, Serialize, Clone, Debug, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub struct RoutingConfig {
    /// Minimum severity level to route to this channel (e.g., "high", "critical")
    #[serde(skip_serializing_if = "Option::is_none")]
    pub min_severity: Option<String>,

    /// List of services to route to this channel (["*"] for all)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub services: Option<Vec<String>>,

    /// Quiet hours configuration
    #[serde(skip_serializing_if = "Option::is_none")]
    pub quiet_hours: Option<QuietHoursConfig>,
}

/// Quiet hours configuration
#[derive(Deserialize, Serialize, Clone, Debug, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub struct QuietHoursConfig {
    /// Whether quiet hours are enabled
    pub enabled: bool,

    /// Start time in HH:MM format (e.g., "22:00")
    pub start: String,

    /// End time in HH:MM format (e.g., "08:00")
    pub end: String,

    /// IANA timezone string (e.g., "America/New_York")
    pub timezone: String,

    /// Whether critical notifications bypass quiet hours
    pub escalation_override: bool,
}

/// Current condition of a NotificationChannel resource
#[derive(Deserialize, Serialize, Clone, Debug, Default, JsonSchema, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum NotificationChannelCondition {
    /// Channel is properly configured and credentials validated
    #[default]
    Configured,
    /// Channel has a configuration or credential error
    Error,
}

/// Status of a NotificationChannel resource
#[derive(Deserialize, Serialize, Clone, Debug, Default, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub struct NotificationChannelStatus {
    /// Current condition of the channel (configured/error)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub condition: Option<NotificationChannelCondition>,

    /// Last time the channel was validated (ISO 8601)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_validated: Option<String>,

    /// Error message if validation failed
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

/// Validate a NotificationChannelSpec and return an error message if invalid
pub fn validate_spec(spec: &NotificationChannelSpec) -> Result<(), String> {
    if spec.credentials_secret.is_empty() {
        return Err("spec.credentials_secret must not be empty".to_string());
    }

    // Validate channel-type-specific required config keys
    match spec.channel_type {
        ChannelType::Slack => {
            if !spec.config.contains_key("channel") {
                return Err("spec.config.channel is required for slack channel type".to_string());
            }
            if spec
                .config
                .get("channel")
                .map(|v| v.is_empty())
                .unwrap_or(true)
            {
                return Err(
                    "spec.config.channel must not be empty for slack channel type".to_string(),
                );
            }
        }
        ChannelType::Pagerduty => {
            if !spec.config.contains_key("routing_key") {
                return Err(
                    "spec.config.routing_key is required for pagerduty channel type".to_string(),
                );
            }
            if spec
                .config
                .get("routing_key")
                .map(|v| v.is_empty())
                .unwrap_or(true)
            {
                return Err(
                    "spec.config.routing_key must not be empty for pagerduty channel type"
                        .to_string(),
                );
            }
        }
        ChannelType::Email => {
            if !spec.config.contains_key("smtp_host") {
                return Err("spec.config.smtp_host is required for email channel type".to_string());
            }
            if spec
                .config
                .get("smtp_host")
                .map(|v| v.is_empty())
                .unwrap_or(true)
            {
                return Err(
                    "spec.config.smtp_host must not be empty for email channel type".to_string(),
                );
            }
            if !spec.config.contains_key("recipients") {
                return Err("spec.config.recipients is required for email channel type".to_string());
            }
            if spec
                .config
                .get("recipients")
                .map(|v| v.is_empty())
                .unwrap_or(true)
            {
                return Err(
                    "spec.config.recipients must not be empty for email channel type".to_string(),
                );
            }
        }
        ChannelType::Webhook => {
            if !spec.config.contains_key("url") {
                return Err("spec.config.url is required for webhook channel type".to_string());
            }
            if spec.config.get("url").map(|v| v.is_empty()).unwrap_or(true) {
                return Err(
                    "spec.config.url must not be empty for webhook channel type".to_string()
                );
            }
        }
    }

    // Validate quiet hours config if present
    if let Some(routing) = &spec.routing {
        if let Some(quiet_hours) = &routing.quiet_hours {
            if quiet_hours.start.is_empty() {
                return Err("spec.routing.quiet_hours.start must not be empty".to_string());
            }
            if quiet_hours.end.is_empty() {
                return Err("spec.routing.quiet_hours.end must not be empty".to_string());
            }
            if quiet_hours.timezone.is_empty() {
                return Err("spec.routing.quiet_hours.timezone must not be empty".to_string());
            }
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_slack_spec() -> NotificationChannelSpec {
        let mut config = HashMap::new();
        config.insert("channel".to_string(), "#sre-alerts".to_string());
        config.insert("mention_users".to_string(), "true".to_string());

        NotificationChannelSpec {
            channel_type: ChannelType::Slack,
            config,
            credentials_secret: "slack-bot-token".to_string(),
            routing: Some(RoutingConfig {
                min_severity: Some("high".to_string()),
                services: Some(vec!["*".to_string()]),
                quiet_hours: Some(QuietHoursConfig {
                    enabled: true,
                    start: "22:00".to_string(),
                    end: "08:00".to_string(),
                    timezone: "America/New_York".to_string(),
                    escalation_override: true,
                }),
            }),
        }
    }

    fn sample_pagerduty_spec() -> NotificationChannelSpec {
        let mut config = HashMap::new();
        config.insert("routing_key".to_string(), "abc123".to_string());

        NotificationChannelSpec {
            channel_type: ChannelType::Pagerduty,
            config,
            credentials_secret: "pagerduty-token".to_string(),
            routing: None,
        }
    }

    fn sample_email_spec() -> NotificationChannelSpec {
        let mut config = HashMap::new();
        config.insert("smtp_host".to_string(), "smtp.example.com".to_string());
        config.insert("recipients".to_string(), "sre@example.com".to_string());

        NotificationChannelSpec {
            channel_type: ChannelType::Email,
            config,
            credentials_secret: "smtp-credentials".to_string(),
            routing: None,
        }
    }

    fn sample_webhook_spec() -> NotificationChannelSpec {
        let mut config = HashMap::new();
        config.insert(
            "url".to_string(),
            "https://hooks.example.com/notify".to_string(),
        );

        NotificationChannelSpec {
            channel_type: ChannelType::Webhook,
            config,
            credentials_secret: "webhook-secret".to_string(),
            routing: None,
        }
    }

    // ----- Serialization tests -----

    #[test]
    fn test_slack_spec_serialization() {
        let spec = sample_slack_spec();
        let json = serde_json::to_string(&spec).unwrap();
        assert!(json.contains("\"type\":\"slack\""));
        assert!(json.contains("\"credentials_secret\":\"slack-bot-token\""));
    }

    #[test]
    fn test_pagerduty_spec_serialization() {
        let spec = sample_pagerduty_spec();
        let json = serde_json::to_string(&spec).unwrap();
        assert!(json.contains("\"type\":\"pagerduty\""));
        assert!(json.contains("\"credentials_secret\":\"pagerduty-token\""));
    }

    #[test]
    fn test_email_spec_serialization() {
        let spec = sample_email_spec();
        let json = serde_json::to_string(&spec).unwrap();
        assert!(json.contains("\"type\":\"email\""));
        assert!(json.contains("\"smtp_host\":\"smtp.example.com\""));
    }

    #[test]
    fn test_webhook_spec_serialization() {
        let spec = sample_webhook_spec();
        let json = serde_json::to_string(&spec).unwrap();
        assert!(json.contains("\"type\":\"webhook\""));
        assert!(json.contains("\"url\":\"https://hooks.example.com/notify\""));
    }

    #[test]
    fn test_spec_without_routing_omits_field() {
        let spec = sample_pagerduty_spec();
        let json = serde_json::to_string(&spec).unwrap();
        // Check that the "routing" field key is absent (not a substring like "routing_key" in config)
        assert!(!json.contains("\"routing\":"));
    }

    #[test]
    fn test_routing_config_serialization() {
        let spec = sample_slack_spec();
        let json = serde_json::to_string(&spec).unwrap();
        assert!(json.contains("\"min_severity\":\"high\""));
        assert!(json.contains("\"services\":[\"*\"]"));
        assert!(json.contains("\"quiet_hours\""));
        assert!(json.contains("\"escalation_override\":true"));
    }

    #[test]
    fn test_quiet_hours_serialization() {
        let qh = QuietHoursConfig {
            enabled: true,
            start: "22:00".to_string(),
            end: "08:00".to_string(),
            timezone: "America/New_York".to_string(),
            escalation_override: true,
        };
        let json = serde_json::to_string(&qh).unwrap();
        assert!(json.contains("\"enabled\":true"));
        assert!(json.contains("\"start\":\"22:00\""));
        assert!(json.contains("\"end\":\"08:00\""));
        assert!(json.contains("\"timezone\":\"America/New_York\""));
        assert!(json.contains("\"escalation_override\":true"));
    }

    // ----- Deserialization tests -----

    #[test]
    fn test_channel_type_deserialization() {
        let slack: ChannelType = serde_json::from_str("\"slack\"").unwrap();
        assert_eq!(slack, ChannelType::Slack);

        let pd: ChannelType = serde_json::from_str("\"pagerduty\"").unwrap();
        assert_eq!(pd, ChannelType::Pagerduty);

        let email: ChannelType = serde_json::from_str("\"email\"").unwrap();
        assert_eq!(email, ChannelType::Email);

        let webhook: ChannelType = serde_json::from_str("\"webhook\"").unwrap();
        assert_eq!(webhook, ChannelType::Webhook);
    }

    #[test]
    fn test_condition_deserialization() {
        let configured: NotificationChannelCondition =
            serde_json::from_str("\"configured\"").unwrap();
        assert_eq!(configured, NotificationChannelCondition::Configured);

        let error: NotificationChannelCondition = serde_json::from_str("\"error\"").unwrap();
        assert_eq!(error, NotificationChannelCondition::Error);
    }

    #[test]
    fn test_condition_default() {
        let condition: NotificationChannelCondition = Default::default();
        assert_eq!(condition, NotificationChannelCondition::Configured);
    }

    #[test]
    fn test_spec_deserialization_from_json() {
        let json = r##"{
            "type": "slack",
            "config": {
                "channel": "#sre-alerts"
            },
            "credentials_secret": "slack-bot-token",
            "routing": {
                "min_severity": "high",
                "services": ["*"],
                "quiet_hours": {
                    "enabled": true,
                    "start": "22:00",
                    "end": "08:00",
                    "timezone": "America/New_York",
                    "escalation_override": true
                }
            }
        }"##;

        let spec: NotificationChannelSpec = serde_json::from_str(json).unwrap();
        assert_eq!(spec.channel_type, ChannelType::Slack);
        assert_eq!(spec.credentials_secret, "slack-bot-token");
        assert_eq!(spec.config.get("channel").unwrap(), "#sre-alerts");
        let routing = spec.routing.unwrap();
        assert_eq!(routing.min_severity.unwrap(), "high");
        assert_eq!(routing.services.unwrap(), vec!["*"]);
        let qh = routing.quiet_hours.unwrap();
        assert!(qh.enabled);
        assert!(qh.escalation_override);
    }

    #[test]
    fn test_spec_deserialization_minimal() {
        let json = r#"{
            "type": "webhook",
            "config": {"url": "https://example.com"},
            "credentials_secret": "webhook-secret"
        }"#;

        let spec: NotificationChannelSpec = serde_json::from_str(json).unwrap();
        assert_eq!(spec.channel_type, ChannelType::Webhook);
        assert!(spec.routing.is_none());
    }

    // ----- Status tests -----

    #[test]
    fn test_status_serialization_configured() {
        let status = NotificationChannelStatus {
            condition: Some(NotificationChannelCondition::Configured),
            last_validated: Some("2026-03-14T12:00:00Z".to_string()),
            error: None,
        };
        let json = serde_json::to_string(&status).unwrap();
        assert!(json.contains("\"condition\":\"configured\""));
        assert!(json.contains("\"last_validated\":\"2026-03-14T12:00:00Z\""));
        assert!(!json.contains("error"));
    }

    #[test]
    fn test_status_serialization_error() {
        let status = NotificationChannelStatus {
            condition: Some(NotificationChannelCondition::Error),
            last_validated: Some("2026-03-14T12:00:00Z".to_string()),
            error: Some("Secret not found".to_string()),
        };
        let json = serde_json::to_string(&status).unwrap();
        assert!(json.contains("\"condition\":\"error\""));
        assert!(json.contains("\"error\":\"Secret not found\""));
    }

    #[test]
    fn test_status_empty_default() {
        let status = NotificationChannelStatus::default();
        let json = serde_json::to_string(&status).unwrap();
        assert_eq!(json, "{}");
    }

    // ----- Validation tests -----

    #[test]
    fn test_validate_slack_spec_valid() {
        let spec = sample_slack_spec();
        assert!(validate_spec(&spec).is_ok());
    }

    #[test]
    fn test_validate_pagerduty_spec_valid() {
        let spec = sample_pagerduty_spec();
        assert!(validate_spec(&spec).is_ok());
    }

    #[test]
    fn test_validate_email_spec_valid() {
        let spec = sample_email_spec();
        assert!(validate_spec(&spec).is_ok());
    }

    #[test]
    fn test_validate_webhook_spec_valid() {
        let spec = sample_webhook_spec();
        assert!(validate_spec(&spec).is_ok());
    }

    #[test]
    fn test_validate_empty_credentials_secret() {
        let mut spec = sample_slack_spec();
        spec.credentials_secret = "".to_string();
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .contains("credentials_secret must not be empty"));
    }

    #[test]
    fn test_validate_slack_missing_channel() {
        let mut spec = sample_slack_spec();
        spec.config.remove("channel");
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("channel is required"));
    }

    #[test]
    fn test_validate_slack_empty_channel() {
        let mut spec = sample_slack_spec();
        spec.config.insert("channel".to_string(), "".to_string());
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("channel must not be empty"));
    }

    #[test]
    fn test_validate_pagerduty_missing_routing_key() {
        let mut spec = sample_pagerduty_spec();
        spec.config.remove("routing_key");
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("routing_key is required"));
    }

    #[test]
    fn test_validate_pagerduty_empty_routing_key() {
        let mut spec = sample_pagerduty_spec();
        spec.config
            .insert("routing_key".to_string(), "".to_string());
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .contains("routing_key must not be empty"));
    }

    #[test]
    fn test_validate_email_missing_smtp_host() {
        let mut spec = sample_email_spec();
        spec.config.remove("smtp_host");
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("smtp_host is required"));
    }

    #[test]
    fn test_validate_email_missing_recipients() {
        let mut spec = sample_email_spec();
        spec.config.remove("recipients");
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("recipients is required"));
    }

    #[test]
    fn test_validate_email_empty_smtp_host() {
        let mut spec = sample_email_spec();
        spec.config.insert("smtp_host".to_string(), "".to_string());
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("smtp_host must not be empty"));
    }

    #[test]
    fn test_validate_email_empty_recipients() {
        let mut spec = sample_email_spec();
        spec.config.insert("recipients".to_string(), "".to_string());
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("recipients must not be empty"));
    }

    #[test]
    fn test_validate_webhook_missing_url() {
        let mut spec = sample_webhook_spec();
        spec.config.remove("url");
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("url is required"));
    }

    #[test]
    fn test_validate_webhook_empty_url() {
        let mut spec = sample_webhook_spec();
        spec.config.insert("url".to_string(), "".to_string());
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("url must not be empty"));
    }

    #[test]
    fn test_validate_quiet_hours_empty_start() {
        let mut spec = sample_slack_spec();
        spec.routing
            .as_mut()
            .unwrap()
            .quiet_hours
            .as_mut()
            .unwrap()
            .start = "".to_string();
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("start must not be empty"));
    }

    #[test]
    fn test_validate_quiet_hours_empty_end() {
        let mut spec = sample_slack_spec();
        spec.routing
            .as_mut()
            .unwrap()
            .quiet_hours
            .as_mut()
            .unwrap()
            .end = "".to_string();
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("end must not be empty"));
    }

    #[test]
    fn test_validate_quiet_hours_empty_timezone() {
        let mut spec = sample_slack_spec();
        spec.routing
            .as_mut()
            .unwrap()
            .quiet_hours
            .as_mut()
            .unwrap()
            .timezone = "".to_string();
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("timezone must not be empty"));
    }

    #[test]
    fn test_validate_routing_without_quiet_hours() {
        let mut spec = sample_slack_spec();
        spec.routing.as_mut().unwrap().quiet_hours = None;
        assert!(validate_spec(&spec).is_ok());
    }

    #[test]
    fn test_validate_routing_minimal() {
        let mut spec = sample_slack_spec();
        spec.routing = Some(RoutingConfig {
            min_severity: None,
            services: None,
            quiet_hours: None,
        });
        assert!(validate_spec(&spec).is_ok());
    }

    #[test]
    fn test_routing_config_optional_fields_omitted() {
        let routing = RoutingConfig {
            min_severity: None,
            services: None,
            quiet_hours: None,
        };
        let json = serde_json::to_string(&routing).unwrap();
        assert!(!json.contains("min_severity"));
        assert!(!json.contains("services"));
        assert!(!json.contains("quiet_hours"));
    }
}
