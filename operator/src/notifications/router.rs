//! Notification Routing Rules Engine
//!
//! Evaluates notification routing rules against outbox entries to determine
//! which channels should receive each notification. Supports severity filtering,
//! service matching, quiet hours suppression, and SLO-weighted urgency elevation.
//!
//! The router is a pure in-memory evaluator — no I/O or external calls.
//! Channel configs and SLO context are passed as parameters by the caller.

use chrono::{NaiveTime, Timelike, Utc};
use serde::{Deserialize, Serialize};
use tracing::{debug, warn};

use super::outbox::OutboxEntry;
use crate::crds::notification_channel::{ChannelType, NotificationChannelSpec, QuietHoursConfig};

/// Error type for routing operations
#[derive(Debug, thiserror::Error)]
pub enum RouterError {
    #[error("Invalid time format: {0}")]
    InvalidTimeFormat(String),

    #[error("Invalid timezone: {0}")]
    InvalidTimezone(String),
}

/// Severity levels with natural ordering (Low < Medium < High < Critical)
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Severity {
    Low,
    Medium,
    High,
    Critical,
}

impl Severity {
    /// Parse severity from a string (case-insensitive)
    pub fn from_str_lossy(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "critical" => Severity::Critical,
            "high" => Severity::High,
            "medium" => Severity::Medium,
            "low" => Severity::Low,
            _ => {
                warn!(severity = %s, "Unknown severity string, defaulting to Low");
                Severity::Low
            }
        }
    }
}

impl std::fmt::Display for Severity {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Severity::Low => write!(f, "low"),
            Severity::Medium => write!(f, "medium"),
            Severity::High => write!(f, "high"),
            Severity::Critical => write!(f, "critical"),
        }
    }
}

/// SLO context for urgency weighting
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SloContext {
    /// Customer impact score (0.0–1.0) from CustomerImpactScorer
    pub impact_score: Option<f64>,

    /// Current SLO burn rate
    pub burn_rate: Option<f64>,

    /// Remaining error budget as a fraction (0.0–1.0)
    pub error_budget_remaining: Option<f64>,
}

/// Threshold for elevating medium → high
const SLO_ELEVATE_MEDIUM_THRESHOLD: f64 = 0.7;

/// Threshold for elevating high → critical
const SLO_ELEVATE_HIGH_THRESHOLD: f64 = 0.9;

/// Result of evaluating a single channel against a notification
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RoutingDecision {
    /// Name of the notification channel
    pub channel_name: String,

    /// Type of channel
    pub channel_type: ChannelType,

    /// Whether the notification should be routed to this channel
    pub matched: bool,

    /// Human-readable reason for the decision
    pub reason: String,

    /// Effective severity after SLO weighting
    pub effective_severity: Severity,
}

/// Stateless notification routing engine
///
/// Evaluates outbox entries against channel routing rules to determine
/// which channels should receive each notification.
pub struct NotificationRouter;

impl NotificationRouter {
    /// Evaluate a single channel against a notification entry
    ///
    /// Returns a `RoutingDecision` indicating whether the notification
    /// should be routed to this channel and why.
    pub fn evaluate_channel(
        entry: &OutboxEntry,
        channel_name: &str,
        spec: &NotificationChannelSpec,
        slo_context: Option<&SloContext>,
    ) -> RoutingDecision {
        let raw_severity = Severity::from_str_lossy(&entry.severity);
        let effective_severity = compute_effective_severity(raw_severity, slo_context);

        // No routing config → pass-through (match all)
        let routing = match &spec.routing {
            Some(r) => r,
            None => {
                debug!(
                    channel = %channel_name,
                    severity = %effective_severity,
                    "No routing config — pass-through"
                );
                return RoutingDecision {
                    channel_name: channel_name.to_string(),
                    channel_type: spec.channel_type.clone(),
                    matched: true,
                    reason: "No routing config — pass-through (matches all)".to_string(),
                    effective_severity,
                };
            }
        };

        // Check severity filter
        if let Some(min_severity_str) = &routing.min_severity {
            let min_severity = Severity::from_str_lossy(min_severity_str);
            if effective_severity < min_severity {
                return RoutingDecision {
                    channel_name: channel_name.to_string(),
                    channel_type: spec.channel_type.clone(),
                    matched: false,
                    reason: format!(
                        "Severity {} below minimum {} for channel",
                        effective_severity, min_severity
                    ),
                    effective_severity,
                };
            }
        }

        // Check service filter
        if !matches_service(&entry.service, &routing.services) {
            return RoutingDecision {
                channel_name: channel_name.to_string(),
                channel_type: spec.channel_type.clone(),
                matched: false,
                reason: format!("Service '{}' not in channel's service list", entry.service),
                effective_severity,
            };
        }

        // Check quiet hours
        if let Some(quiet_hours) = &routing.quiet_hours {
            if quiet_hours.enabled {
                match is_in_quiet_hours(quiet_hours) {
                    Ok(true) => {
                        // Check escalation override
                        if quiet_hours.escalation_override
                            && effective_severity == Severity::Critical
                        {
                            debug!(
                                channel = %channel_name,
                                "Critical notification bypasses quiet hours via escalation_override"
                            );
                        } else {
                            return RoutingDecision {
                                channel_name: channel_name.to_string(),
                                channel_type: spec.channel_type.clone(),
                                matched: false,
                                reason: "Suppressed during quiet hours".to_string(),
                                effective_severity,
                            };
                        }
                    }
                    Ok(false) => {
                        // Not in quiet hours, continue
                    }
                    Err(e) => {
                        // On error parsing quiet hours, log warning and allow through
                        warn!(
                            channel = %channel_name,
                            error = %e,
                            "Failed to evaluate quiet hours, allowing notification through"
                        );
                    }
                }
            }
        }

        // All checks passed
        RoutingDecision {
            channel_name: channel_name.to_string(),
            channel_type: spec.channel_type.clone(),
            matched: true,
            reason: "All routing rules matched".to_string(),
            effective_severity,
        }
    }

    /// Route a notification entry across all configured channels
    ///
    /// Evaluates each channel's routing rules and returns decisions for all channels.
    /// Only channels with `matched: true` should receive the notification.
    pub fn route(
        entry: &OutboxEntry,
        channels: &[(String, NotificationChannelSpec)],
        slo_context: Option<&SloContext>,
    ) -> Vec<RoutingDecision> {
        let mut decisions = Vec::with_capacity(channels.len());

        for (name, spec) in channels {
            let decision = Self::evaluate_channel(entry, name, spec, slo_context);
            debug!(
                channel = %name,
                matched = decision.matched,
                reason = %decision.reason,
                effective_severity = %decision.effective_severity,
                "Routing decision"
            );
            decisions.push(decision);
        }

        decisions
    }
}

/// Check if a service matches the channel's service filter
fn matches_service(service: &str, services: &Option<Vec<String>>) -> bool {
    match services {
        None => true,                          // No service filter → match all
        Some(list) if list.is_empty() => true, // Empty list → match all
        Some(list) => list.iter().any(|s| s == "*" || s == service),
    }
}

/// Compute effective severity after SLO urgency weighting
///
/// SLO impact can only ELEVATE severity, never demote:
/// - impact_score > 0.7 → medium elevated to high
/// - impact_score > 0.9 → high elevated to critical
pub fn compute_effective_severity(
    raw_severity: Severity,
    slo_context: Option<&SloContext>,
) -> Severity {
    let impact_score = match slo_context {
        Some(ctx) => ctx.impact_score.unwrap_or(0.0),
        None => return raw_severity,
    };

    match raw_severity {
        Severity::Low => {
            if impact_score > SLO_ELEVATE_HIGH_THRESHOLD {
                Severity::Medium
            } else {
                Severity::Low
            }
        }
        Severity::Medium => {
            if impact_score > SLO_ELEVATE_HIGH_THRESHOLD {
                Severity::Critical
            } else if impact_score > SLO_ELEVATE_MEDIUM_THRESHOLD {
                Severity::High
            } else {
                Severity::Medium
            }
        }
        Severity::High => {
            if impact_score > SLO_ELEVATE_HIGH_THRESHOLD {
                Severity::Critical
            } else {
                Severity::High
            }
        }
        Severity::Critical => Severity::Critical, // Already max
    }
}

/// Check if the current time falls within quiet hours for the given configuration
///
/// Handles overnight spans (e.g., 22:00–08:00) correctly.
pub fn is_in_quiet_hours(config: &QuietHoursConfig) -> Result<bool, RouterError> {
    let start = parse_hh_mm(&config.start)?;
    let end = parse_hh_mm(&config.end)?;

    let tz: chrono_tz::Tz = config
        .timezone
        .parse()
        .map_err(|_| RouterError::InvalidTimezone(config.timezone.clone()))?;

    let now_in_tz = Utc::now().with_timezone(&tz);
    let current_time = NaiveTime::from_hms_opt(now_in_tz.hour(), now_in_tz.minute(), 0)
        .unwrap_or(NaiveTime::from_hms_opt(0, 0, 0).unwrap());

    Ok(is_time_in_window(current_time, start, end))
}

/// Check if the current time falls within quiet hours using an explicit "now" time
///
/// This is the testable version — takes current_time as a parameter.
pub fn is_in_quiet_hours_at(
    config: &QuietHoursConfig,
    current_time: NaiveTime,
) -> Result<bool, RouterError> {
    let start = parse_hh_mm(&config.start)?;
    let end = parse_hh_mm(&config.end)?;

    // Validate timezone is parseable — ensures error reporting is consistent
    // with is_in_quiet_hours() even though this testable variant doesn't need the tz value
    let _tz: chrono_tz::Tz = config
        .timezone
        .parse()
        .map_err(|_| RouterError::InvalidTimezone(config.timezone.clone()))?;

    Ok(is_time_in_window(current_time, start, end))
}

/// Check if a time falls within a window, handling overnight spans
fn is_time_in_window(current: NaiveTime, start: NaiveTime, end: NaiveTime) -> bool {
    if start <= end {
        // Same-day window (e.g., 09:00–17:00)
        current >= start && current < end
    } else {
        // Overnight window (e.g., 22:00–08:00)
        current >= start || current < end
    }
}

/// Parse an "HH:MM" string into NaiveTime
fn parse_hh_mm(s: &str) -> Result<NaiveTime, RouterError> {
    NaiveTime::parse_from_str(s, "%H:%M").map_err(|_| RouterError::InvalidTimeFormat(s.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::crds::notification_channel::RoutingConfig;
    use std::collections::HashMap;

    // ===== Helper functions =====

    fn make_entry(severity: &str, service: &str) -> OutboxEntry {
        OutboxEntry {
            investigation_id: "inv-test".to_string(),
            event_type: "investigation_started".to_string(),
            severity: severity.to_string(),
            service: service.to_string(),
            payload: serde_json::json!({"summary": "test"}),
            status: "pending".to_string(),
            retry_count: 0,
            created_at: "2026-03-14T12:00:00Z".to_string(),
            next_retry_at: "2026-03-14T12:00:00Z".to_string(),
            last_error: None,
        }
    }

    fn make_channel_spec(
        channel_type: ChannelType,
        routing: Option<RoutingConfig>,
    ) -> NotificationChannelSpec {
        let mut config = HashMap::new();
        match channel_type {
            ChannelType::Slack => {
                config.insert("channel".to_string(), "#alerts".to_string());
            }
            ChannelType::Pagerduty => {
                config.insert("routing_key".to_string(), "key123".to_string());
            }
            ChannelType::Email => {
                config.insert("smtp_host".to_string(), "smtp.example.com".to_string());
                config.insert("recipients".to_string(), "sre@example.com".to_string());
            }
            ChannelType::Webhook => {
                config.insert("url".to_string(), "https://hooks.example.com".to_string());
            }
        }

        NotificationChannelSpec {
            channel_type,
            config,
            credentials_secret: "test-secret".to_string(),
            routing,
        }
    }

    fn make_quiet_hours(
        enabled: bool,
        start: &str,
        end: &str,
        escalation_override: bool,
    ) -> QuietHoursConfig {
        QuietHoursConfig {
            enabled,
            start: start.to_string(),
            end: end.to_string(),
            timezone: "America/New_York".to_string(),
            escalation_override,
        }
    }

    // ===== Severity ordering tests =====

    #[test]
    fn test_severity_ordering_low_less_than_medium() {
        assert!(Severity::Low < Severity::Medium);
    }

    #[test]
    fn test_severity_ordering_medium_less_than_high() {
        assert!(Severity::Medium < Severity::High);
    }

    #[test]
    fn test_severity_ordering_high_less_than_critical() {
        assert!(Severity::High < Severity::Critical);
    }

    #[test]
    fn test_severity_ordering_low_less_than_critical() {
        assert!(Severity::Low < Severity::Critical);
    }

    #[test]
    fn test_severity_ordering_all_pairwise() {
        let levels = [
            Severity::Low,
            Severity::Medium,
            Severity::High,
            Severity::Critical,
        ];
        for i in 0..levels.len() {
            for j in 0..levels.len() {
                if i < j {
                    assert!(
                        levels[i] < levels[j],
                        "{:?} should be < {:?}",
                        levels[i],
                        levels[j]
                    );
                } else if i > j {
                    assert!(
                        levels[i] > levels[j],
                        "{:?} should be > {:?}",
                        levels[i],
                        levels[j]
                    );
                } else {
                    assert_eq!(levels[i], levels[j]);
                }
            }
        }
    }

    #[test]
    fn test_severity_from_str_lossy_valid() {
        assert_eq!(Severity::from_str_lossy("low"), Severity::Low);
        assert_eq!(Severity::from_str_lossy("medium"), Severity::Medium);
        assert_eq!(Severity::from_str_lossy("high"), Severity::High);
        assert_eq!(Severity::from_str_lossy("critical"), Severity::Critical);
    }

    #[test]
    fn test_severity_from_str_lossy_case_insensitive() {
        assert_eq!(Severity::from_str_lossy("LOW"), Severity::Low);
        assert_eq!(Severity::from_str_lossy("Medium"), Severity::Medium);
        assert_eq!(Severity::from_str_lossy("HIGH"), Severity::High);
        assert_eq!(Severity::from_str_lossy("Critical"), Severity::Critical);
    }

    #[test]
    fn test_severity_from_str_lossy_invalid_defaults_to_low() {
        assert_eq!(Severity::from_str_lossy("unknown"), Severity::Low);
        assert_eq!(Severity::from_str_lossy(""), Severity::Low);
        assert_eq!(Severity::from_str_lossy("urgent"), Severity::Low);
    }

    #[test]
    fn test_severity_display() {
        assert_eq!(format!("{}", Severity::Low), "low");
        assert_eq!(format!("{}", Severity::Medium), "medium");
        assert_eq!(format!("{}", Severity::High), "high");
        assert_eq!(format!("{}", Severity::Critical), "critical");
    }

    // ===== Service matching tests =====

    #[test]
    fn test_matches_service_wildcard() {
        let services = Some(vec!["*".to_string()]);
        assert!(matches_service("any-service", &services));
        assert!(matches_service("payment-service", &services));
    }

    #[test]
    fn test_matches_service_specific_match() {
        let services = Some(vec![
            "payment-service".to_string(),
            "auth-service".to_string(),
        ]);
        assert!(matches_service("payment-service", &services));
        assert!(matches_service("auth-service", &services));
    }

    #[test]
    fn test_matches_service_specific_no_match() {
        let services = Some(vec![
            "payment-service".to_string(),
            "auth-service".to_string(),
        ]);
        assert!(!matches_service("api-gateway", &services));
    }

    #[test]
    fn test_matches_service_none_matches_all() {
        assert!(matches_service("any-service", &None));
    }

    #[test]
    fn test_matches_service_empty_list_matches_all() {
        let services = Some(vec![]);
        assert!(matches_service("any-service", &services));
    }

    // ===== Quiet hours tests =====

    #[test]
    fn test_is_time_in_window_same_day_inside() {
        let start = NaiveTime::from_hms_opt(9, 0, 0).unwrap();
        let end = NaiveTime::from_hms_opt(17, 0, 0).unwrap();
        let current = NaiveTime::from_hms_opt(12, 0, 0).unwrap();
        assert!(is_time_in_window(current, start, end));
    }

    #[test]
    fn test_is_time_in_window_same_day_outside() {
        let start = NaiveTime::from_hms_opt(9, 0, 0).unwrap();
        let end = NaiveTime::from_hms_opt(17, 0, 0).unwrap();
        let current = NaiveTime::from_hms_opt(20, 0, 0).unwrap();
        assert!(!is_time_in_window(current, start, end));
    }

    #[test]
    fn test_is_time_in_window_overnight_inside_late() {
        let start = NaiveTime::from_hms_opt(22, 0, 0).unwrap();
        let end = NaiveTime::from_hms_opt(8, 0, 0).unwrap();
        let current = NaiveTime::from_hms_opt(23, 30, 0).unwrap();
        assert!(is_time_in_window(current, start, end));
    }

    #[test]
    fn test_is_time_in_window_overnight_inside_early() {
        let start = NaiveTime::from_hms_opt(22, 0, 0).unwrap();
        let end = NaiveTime::from_hms_opt(8, 0, 0).unwrap();
        let current = NaiveTime::from_hms_opt(3, 0, 0).unwrap();
        assert!(is_time_in_window(current, start, end));
    }

    #[test]
    fn test_is_time_in_window_overnight_outside() {
        let start = NaiveTime::from_hms_opt(22, 0, 0).unwrap();
        let end = NaiveTime::from_hms_opt(8, 0, 0).unwrap();
        let current = NaiveTime::from_hms_opt(12, 0, 0).unwrap();
        assert!(!is_time_in_window(current, start, end));
    }

    #[test]
    fn test_is_time_in_window_at_start_boundary() {
        let start = NaiveTime::from_hms_opt(22, 0, 0).unwrap();
        let end = NaiveTime::from_hms_opt(8, 0, 0).unwrap();
        let current = NaiveTime::from_hms_opt(22, 0, 0).unwrap();
        assert!(is_time_in_window(current, start, end));
    }

    #[test]
    fn test_is_time_in_window_at_end_boundary_excluded() {
        let start = NaiveTime::from_hms_opt(22, 0, 0).unwrap();
        let end = NaiveTime::from_hms_opt(8, 0, 0).unwrap();
        let current = NaiveTime::from_hms_opt(8, 0, 0).unwrap();
        assert!(!is_time_in_window(current, start, end));
    }

    #[test]
    fn test_parse_hh_mm_valid() {
        let time = parse_hh_mm("22:00").unwrap();
        assert_eq!(time.hour(), 22);
        assert_eq!(time.minute(), 0);
    }

    #[test]
    fn test_parse_hh_mm_midnight() {
        let time = parse_hh_mm("00:00").unwrap();
        assert_eq!(time.hour(), 0);
        assert_eq!(time.minute(), 0);
    }

    #[test]
    fn test_parse_hh_mm_invalid() {
        assert!(parse_hh_mm("25:00").is_err());
        assert!(parse_hh_mm("abc").is_err());
        assert!(parse_hh_mm("").is_err());
    }

    #[test]
    fn test_is_in_quiet_hours_at_during_quiet() {
        let config = make_quiet_hours(true, "22:00", "08:00", false);
        let current = NaiveTime::from_hms_opt(23, 0, 0).unwrap();
        assert!(is_in_quiet_hours_at(&config, current).unwrap());
    }

    #[test]
    fn test_is_in_quiet_hours_at_outside_quiet() {
        let config = make_quiet_hours(true, "22:00", "08:00", false);
        let current = NaiveTime::from_hms_opt(12, 0, 0).unwrap();
        assert!(!is_in_quiet_hours_at(&config, current).unwrap());
    }

    #[test]
    fn test_is_in_quiet_hours_at_invalid_timezone() {
        let mut config = make_quiet_hours(true, "22:00", "08:00", false);
        config.timezone = "Invalid/Timezone".to_string();
        let current = NaiveTime::from_hms_opt(23, 0, 0).unwrap();
        assert!(is_in_quiet_hours_at(&config, current).is_err());
    }

    // ===== SLO urgency weighting tests =====

    #[test]
    fn test_effective_severity_no_slo_context() {
        assert_eq!(
            compute_effective_severity(Severity::Medium, None),
            Severity::Medium
        );
        assert_eq!(
            compute_effective_severity(Severity::Low, None),
            Severity::Low
        );
        assert_eq!(
            compute_effective_severity(Severity::Critical, None),
            Severity::Critical
        );
    }

    #[test]
    fn test_effective_severity_low_impact_no_elevation() {
        let ctx = SloContext {
            impact_score: Some(0.3),
            burn_rate: Some(1.0),
            error_budget_remaining: Some(0.9),
        };
        assert_eq!(
            compute_effective_severity(Severity::Medium, Some(&ctx)),
            Severity::Medium
        );
        assert_eq!(
            compute_effective_severity(Severity::High, Some(&ctx)),
            Severity::High
        );
    }

    #[test]
    fn test_effective_severity_medium_elevated_to_high() {
        let ctx = SloContext {
            impact_score: Some(0.75),
            burn_rate: Some(5.0),
            error_budget_remaining: Some(0.3),
        };
        assert_eq!(
            compute_effective_severity(Severity::Medium, Some(&ctx)),
            Severity::High
        );
    }

    #[test]
    fn test_effective_severity_medium_elevated_to_critical_very_high_impact() {
        let ctx = SloContext {
            impact_score: Some(0.95),
            burn_rate: Some(9.0),
            error_budget_remaining: Some(0.05),
        };
        assert_eq!(
            compute_effective_severity(Severity::Medium, Some(&ctx)),
            Severity::Critical
        );
    }

    #[test]
    fn test_effective_severity_high_elevated_to_critical() {
        let ctx = SloContext {
            impact_score: Some(0.95),
            burn_rate: Some(8.0),
            error_budget_remaining: Some(0.1),
        };
        assert_eq!(
            compute_effective_severity(Severity::High, Some(&ctx)),
            Severity::Critical
        );
    }

    #[test]
    fn test_effective_severity_critical_stays_critical() {
        let ctx = SloContext {
            impact_score: Some(0.3),
            burn_rate: Some(1.0),
            error_budget_remaining: Some(0.9),
        };
        assert_eq!(
            compute_effective_severity(Severity::Critical, Some(&ctx)),
            Severity::Critical
        );
    }

    #[test]
    fn test_effective_severity_low_with_very_high_impact() {
        let ctx = SloContext {
            impact_score: Some(0.95),
            burn_rate: Some(9.0),
            error_budget_remaining: Some(0.05),
        };
        // Low gets elevated to Medium when impact > 0.9
        assert_eq!(
            compute_effective_severity(Severity::Low, Some(&ctx)),
            Severity::Medium
        );
    }

    #[test]
    fn test_effective_severity_none_impact_score_uses_raw() {
        let ctx = SloContext {
            impact_score: None,
            burn_rate: Some(5.0),
            error_budget_remaining: Some(0.3),
        };
        assert_eq!(
            compute_effective_severity(Severity::Medium, Some(&ctx)),
            Severity::Medium
        );
    }

    // ===== Channel evaluation tests =====

    #[test]
    fn test_evaluate_channel_no_routing_passes_through() {
        let entry = make_entry("low", "any-service");
        let spec = make_channel_spec(ChannelType::Slack, None);
        let decision = NotificationRouter::evaluate_channel(&entry, "sre-slack", &spec, None);
        assert!(decision.matched);
        assert!(decision.reason.contains("pass-through"));
    }

    #[test]
    fn test_evaluate_channel_severity_filter_rejects_low() {
        let entry = make_entry("low", "payment-service");
        let routing = RoutingConfig {
            min_severity: Some("high".to_string()),
            services: Some(vec!["*".to_string()]),
            quiet_hours: None,
        };
        let spec = make_channel_spec(ChannelType::Slack, Some(routing));
        let decision = NotificationRouter::evaluate_channel(&entry, "sre-slack", &spec, None);
        assert!(!decision.matched);
        assert!(decision.reason.contains("below minimum"));
    }

    #[test]
    fn test_evaluate_channel_severity_filter_accepts_high() {
        let entry = make_entry("high", "payment-service");
        let routing = RoutingConfig {
            min_severity: Some("high".to_string()),
            services: Some(vec!["*".to_string()]),
            quiet_hours: None,
        };
        let spec = make_channel_spec(ChannelType::Slack, Some(routing));
        let decision = NotificationRouter::evaluate_channel(&entry, "sre-slack", &spec, None);
        assert!(decision.matched);
    }

    #[test]
    fn test_evaluate_channel_severity_filter_accepts_critical() {
        let entry = make_entry("critical", "payment-service");
        let routing = RoutingConfig {
            min_severity: Some("high".to_string()),
            services: Some(vec!["*".to_string()]),
            quiet_hours: None,
        };
        let spec = make_channel_spec(ChannelType::Slack, Some(routing));
        let decision = NotificationRouter::evaluate_channel(&entry, "sre-slack", &spec, None);
        assert!(decision.matched);
    }

    #[test]
    fn test_evaluate_channel_service_filter_rejects() {
        let entry = make_entry("high", "api-gateway");
        let routing = RoutingConfig {
            min_severity: None,
            services: Some(vec!["payment-service".to_string()]),
            quiet_hours: None,
        };
        let spec = make_channel_spec(ChannelType::Slack, Some(routing));
        let decision = NotificationRouter::evaluate_channel(&entry, "sre-slack", &spec, None);
        assert!(!decision.matched);
        assert!(decision.reason.contains("not in channel's service list"));
    }

    #[test]
    fn test_evaluate_channel_service_filter_accepts() {
        let entry = make_entry("high", "payment-service");
        let routing = RoutingConfig {
            min_severity: None,
            services: Some(vec![
                "payment-service".to_string(),
                "auth-service".to_string(),
            ]),
            quiet_hours: None,
        };
        let spec = make_channel_spec(ChannelType::Slack, Some(routing));
        let decision = NotificationRouter::evaluate_channel(&entry, "sre-slack", &spec, None);
        assert!(decision.matched);
    }

    #[test]
    fn test_evaluate_channel_slo_elevation_enables_routing() {
        // Medium severity would be rejected by min_severity: high
        // But SLO impact elevates it to high
        let entry = make_entry("medium", "payment-service");
        let routing = RoutingConfig {
            min_severity: Some("high".to_string()),
            services: Some(vec!["*".to_string()]),
            quiet_hours: None,
        };
        let spec = make_channel_spec(ChannelType::Pagerduty, Some(routing));
        let ctx = SloContext {
            impact_score: Some(0.8),
            burn_rate: Some(6.0),
            error_budget_remaining: Some(0.2),
        };
        let decision =
            NotificationRouter::evaluate_channel(&entry, "sre-pagerduty", &spec, Some(&ctx));
        assert!(decision.matched);
        assert_eq!(decision.effective_severity, Severity::High);
    }

    // ===== Multi-channel routing tests =====

    #[test]
    fn test_route_multi_channel_mixed_results() {
        let entry = make_entry("medium", "payment-service");

        let channels = vec![
            (
                "sre-slack".to_string(),
                make_channel_spec(ChannelType::Slack, None), // No routing → pass-through
            ),
            (
                "sre-pagerduty".to_string(),
                make_channel_spec(
                    ChannelType::Pagerduty,
                    Some(RoutingConfig {
                        min_severity: Some("high".to_string()),
                        services: Some(vec!["*".to_string()]),
                        quiet_hours: None,
                    }),
                ), // min_severity: high → rejects medium
            ),
            (
                "team-webhook".to_string(),
                make_channel_spec(
                    ChannelType::Webhook,
                    Some(RoutingConfig {
                        min_severity: Some("low".to_string()),
                        services: Some(vec!["payment-service".to_string()]),
                        quiet_hours: None,
                    }),
                ), // min_severity: low, service matches → passes
            ),
        ];

        let decisions = NotificationRouter::route(&entry, &channels, None);
        assert_eq!(decisions.len(), 3);
        assert!(decisions[0].matched); // sre-slack: pass-through
        assert!(!decisions[1].matched); // sre-pagerduty: severity too low
        assert!(decisions[2].matched); // team-webhook: all rules match
    }

    #[test]
    fn test_route_empty_channels() {
        let entry = make_entry("high", "payment-service");
        let decisions = NotificationRouter::route(&entry, &[], None);
        assert!(decisions.is_empty());
    }

    #[test]
    fn test_route_all_channels_match() {
        let entry = make_entry("critical", "payment-service");

        let channels = vec![
            (
                "slack".to_string(),
                make_channel_spec(ChannelType::Slack, None),
            ),
            (
                "pagerduty".to_string(),
                make_channel_spec(
                    ChannelType::Pagerduty,
                    Some(RoutingConfig {
                        min_severity: Some("high".to_string()),
                        services: Some(vec!["*".to_string()]),
                        quiet_hours: None,
                    }),
                ),
            ),
        ];

        let decisions = NotificationRouter::route(&entry, &channels, None);
        assert!(decisions.iter().all(|d| d.matched));
    }

    #[test]
    fn test_route_none_match() {
        let entry = make_entry("low", "unknown-service");

        let channels = vec![(
            "pagerduty".to_string(),
            make_channel_spec(
                ChannelType::Pagerduty,
                Some(RoutingConfig {
                    min_severity: Some("critical".to_string()),
                    services: Some(vec!["payment-service".to_string()]),
                    quiet_hours: None,
                }),
            ),
        )];

        let decisions = NotificationRouter::route(&entry, &channels, None);
        assert!(decisions.iter().all(|d| !d.matched));
    }

    // ===== End-to-end scenario tests =====

    #[test]
    fn test_e2e_realistic_setup() {
        // Realistic: Slack for all high+, PagerDuty for critical only, webhook for payment-service
        let channels = vec![
            (
                "sre-slack".to_string(),
                make_channel_spec(
                    ChannelType::Slack,
                    Some(RoutingConfig {
                        min_severity: Some("high".to_string()),
                        services: Some(vec!["*".to_string()]),
                        quiet_hours: None,
                    }),
                ),
            ),
            (
                "sre-pagerduty".to_string(),
                make_channel_spec(
                    ChannelType::Pagerduty,
                    Some(RoutingConfig {
                        min_severity: Some("critical".to_string()),
                        services: Some(vec!["*".to_string()]),
                        quiet_hours: None,
                    }),
                ),
            ),
            (
                "payments-webhook".to_string(),
                make_channel_spec(
                    ChannelType::Webhook,
                    Some(RoutingConfig {
                        min_severity: None,
                        services: Some(vec!["payment-service".to_string()]),
                        quiet_hours: None,
                    }),
                ),
            ),
        ];

        // Low severity payment-service event → only webhook
        let entry = make_entry("low", "payment-service");
        let decisions = NotificationRouter::route(&entry, &channels, None);
        assert!(!decisions[0].matched); // Slack: min_severity high
        assert!(!decisions[1].matched); // PagerDuty: min_severity critical
        assert!(decisions[2].matched); // Webhook: service matches, no min_severity

        // Critical payment-service event → all three
        let entry = make_entry("critical", "payment-service");
        let decisions = NotificationRouter::route(&entry, &channels, None);
        assert!(decisions[0].matched); // Slack: high or above
        assert!(decisions[1].matched); // PagerDuty: critical
        assert!(decisions[2].matched); // Webhook: payment-service

        // High auth-service event → only Slack
        let entry = make_entry("high", "auth-service");
        let decisions = NotificationRouter::route(&entry, &channels, None);
        assert!(decisions[0].matched); // Slack: high or above, all services
        assert!(!decisions[1].matched); // PagerDuty: needs critical
        assert!(!decisions[2].matched); // Webhook: wrong service
    }

    #[test]
    fn test_e2e_slo_escalation_scenario() {
        // Medium severity but high SLO impact → elevated to high → Slack fires
        let channels = vec![(
            "sre-slack".to_string(),
            make_channel_spec(
                ChannelType::Slack,
                Some(RoutingConfig {
                    min_severity: Some("high".to_string()),
                    services: Some(vec!["*".to_string()]),
                    quiet_hours: None,
                }),
            ),
        )];

        let entry = make_entry("medium", "payment-service");
        let slo_ctx = SloContext {
            impact_score: Some(0.85),
            burn_rate: Some(7.0),
            error_budget_remaining: Some(0.15),
        };

        // Without SLO: medium < high → rejected
        let decisions = NotificationRouter::route(&entry, &channels, None);
        assert!(!decisions[0].matched);

        // With SLO: medium elevated to high → accepted
        let decisions = NotificationRouter::route(&entry, &channels, Some(&slo_ctx));
        assert!(decisions[0].matched);
        assert_eq!(decisions[0].effective_severity, Severity::High);
    }

    // ===== Edge case tests =====

    #[test]
    fn test_channel_with_empty_routing_config() {
        let entry = make_entry("low", "any-service");
        let routing = RoutingConfig {
            min_severity: None,
            services: None,
            quiet_hours: None,
        };
        let spec = make_channel_spec(ChannelType::Slack, Some(routing));
        let decision = NotificationRouter::evaluate_channel(&entry, "test", &spec, None);
        assert!(decision.matched);
    }

    #[test]
    fn test_severity_boundary_medium_at_high_min() {
        let entry = make_entry("medium", "svc");
        let routing = RoutingConfig {
            min_severity: Some("high".to_string()),
            services: None,
            quiet_hours: None,
        };
        let spec = make_channel_spec(ChannelType::Slack, Some(routing));
        let decision = NotificationRouter::evaluate_channel(&entry, "test", &spec, None);
        assert!(!decision.matched); // medium < high
    }

    #[test]
    fn test_severity_boundary_high_at_high_min() {
        let entry = make_entry("high", "svc");
        let routing = RoutingConfig {
            min_severity: Some("high".to_string()),
            services: None,
            quiet_hours: None,
        };
        let spec = make_channel_spec(ChannelType::Slack, Some(routing));
        let decision = NotificationRouter::evaluate_channel(&entry, "test", &spec, None);
        assert!(decision.matched); // high >= high
    }

    // ===== RoutingDecision serialization tests =====

    #[test]
    fn test_routing_decision_serialization() {
        let decision = RoutingDecision {
            channel_name: "sre-slack".to_string(),
            channel_type: ChannelType::Slack,
            matched: true,
            reason: "All routing rules matched".to_string(),
            effective_severity: Severity::High,
        };
        let json = serde_json::to_string(&decision).unwrap();
        assert!(json.contains("\"channel_name\":\"sre-slack\""));
        assert!(json.contains("\"matched\":true"));
        assert!(json.contains("\"effective_severity\":\"high\""));
    }

    #[test]
    fn test_slo_context_serialization() {
        let ctx = SloContext {
            impact_score: Some(0.85),
            burn_rate: Some(5.0),
            error_budget_remaining: Some(0.3),
        };
        let json = serde_json::to_string(&ctx).unwrap();
        assert!(json.contains("\"impact_score\":0.85"));
        assert!(json.contains("\"burn_rate\":5.0"));
    }

    // ===== Router error tests =====

    // ===== Quiet hours through evaluate_channel tests =====

    #[test]
    fn test_evaluate_channel_quiet_hours_disabled_passes_through() {
        let entry = make_entry("medium", "payment-service");
        let routing = RoutingConfig {
            min_severity: None,
            services: None,
            quiet_hours: Some(make_quiet_hours(false, "00:00", "23:59", false)),
        };
        let spec = make_channel_spec(ChannelType::Slack, Some(routing));
        let decision = NotificationRouter::evaluate_channel(&entry, "test", &spec, None);
        assert!(decision.matched);
        assert!(decision.reason.contains("All routing rules matched"));
    }

    #[test]
    fn test_evaluate_channel_combined_severity_service_quiet_hours() {
        // Combined filter: severity high+, service payment-service, quiet hours disabled
        let entry = make_entry("high", "payment-service");
        let routing = RoutingConfig {
            min_severity: Some("high".to_string()),
            services: Some(vec!["payment-service".to_string()]),
            quiet_hours: Some(make_quiet_hours(false, "22:00", "08:00", true)),
        };
        let spec = make_channel_spec(ChannelType::Pagerduty, Some(routing));
        let decision = NotificationRouter::evaluate_channel(&entry, "sre-pd", &spec, None);
        assert!(decision.matched);

        // Same setup but wrong service → should be rejected by service filter
        let entry_wrong_svc = make_entry("high", "api-gateway");
        let decision2 =
            NotificationRouter::evaluate_channel(&entry_wrong_svc, "sre-pd", &spec, None);
        assert!(!decision2.matched);
        assert!(decision2.reason.contains("not in channel's service list"));

        // Same setup but low severity → should be rejected by severity filter
        let entry_low = make_entry("low", "payment-service");
        let decision3 = NotificationRouter::evaluate_channel(&entry_low, "sre-pd", &spec, None);
        assert!(!decision3.matched);
        assert!(decision3.reason.contains("below minimum"));
    }

    #[test]
    fn test_effective_severity_impact_score_above_one_still_elevates() {
        // Out-of-range impact_score (>1.0) — should still elevate since it exceeds thresholds
        let ctx = SloContext {
            impact_score: Some(5.0),
            burn_rate: None,
            error_budget_remaining: None,
        };
        assert_eq!(
            compute_effective_severity(Severity::Medium, Some(&ctx)),
            Severity::Critical
        );
        assert_eq!(
            compute_effective_severity(Severity::High, Some(&ctx)),
            Severity::Critical
        );
        assert_eq!(
            compute_effective_severity(Severity::Low, Some(&ctx)),
            Severity::Medium
        );
    }

    #[test]
    fn test_effective_severity_negative_impact_score_no_elevation() {
        // Negative impact_score — should not elevate
        let ctx = SloContext {
            impact_score: Some(-0.5),
            burn_rate: None,
            error_budget_remaining: None,
        };
        assert_eq!(
            compute_effective_severity(Severity::Medium, Some(&ctx)),
            Severity::Medium
        );
        assert_eq!(
            compute_effective_severity(Severity::High, Some(&ctx)),
            Severity::High
        );
    }

    // ===== Router error tests =====

    #[test]
    fn test_router_error_display() {
        let err = RouterError::InvalidTimeFormat("25:00".to_string());
        assert_eq!(err.to_string(), "Invalid time format: 25:00");

        let err = RouterError::InvalidTimezone("Bad/Zone".to_string());
        assert_eq!(err.to_string(), "Invalid timezone: Bad/Zone");
    }
}
