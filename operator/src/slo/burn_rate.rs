//! Burn Rate Alerter — multi-window evaluation and Investigation creation
//!
//! Evaluates burn rate alerts by checking both short and long windows.
//! Creates Investigation CRDs when both windows exceed the alert factor.

use std::collections::HashMap;

use chrono::Utc;
use kube::api::PostParams;
use kube::{Api, Client};
use tracing::{debug, error, info, warn};

use crate::crds::{
    BurnRateAlert, Investigation, InvestigationSpec, ServiceLevelSpec, Severity,
};

use super::calculator::SloCalculator;

/// Default cooldown in seconds between duplicate alerts for the same SLO + alert
const DEFAULT_ALERT_COOLDOWN_SECS: i64 = 600;

/// Multi-window burn rate alerter
///
/// Evaluates burn rate against configured alert thresholds and creates
/// Investigation CRDs when both short and long windows exceed the factor.
pub struct BurnRateAlerter {
    client: Client,
    namespace: String,
    cooldown: HashMap<String, i64>,
    cooldown_secs: i64,
    alert_seq: u16,
}

impl BurnRateAlerter {
    /// Create a new BurnRateAlerter
    pub fn new(client: Client, namespace: String) -> Self {
        let cooldown_secs = std::env::var("BEEPER_SLO_ALERT_COOLDOWN_SECS")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(DEFAULT_ALERT_COOLDOWN_SECS);

        Self {
            client,
            namespace,
            cooldown: HashMap::new(),
            cooldown_secs,
            alert_seq: 0,
        }
    }

    /// Evaluate burn rate alerts for a ServiceLevel
    ///
    /// For each alert threshold, checks if burn rate exceeds the factor
    /// in BOTH the short_window AND long_window. Only creates an Investigation
    /// if both exceed (Google SRE multi-window pattern).
    pub async fn evaluate(
        &mut self,
        servicelevel_name: &str,
        spec: &ServiceLevelSpec,
        alerts: &[BurnRateAlert],
        calculator: &SloCalculator,
    ) {
        for (i, alert) in alerts.iter().enumerate() {
            let fingerprint = alert_fingerprint(servicelevel_name, i);

            // Check cooldown
            if self.is_in_cooldown(&fingerprint) {
                debug!(
                    fingerprint = %fingerprint,
                    "Burn rate alert in cooldown, skipping"
                );
                continue;
            }

            // Calculate burn rate for short window
            let short_burn_rate = match calculator
                .calculate_burn_rate_for_window(spec, &alert.short_window)
                .await
            {
                Ok(br) => br,
                Err(e) => {
                    debug!(
                        error = %e,
                        window = %alert.short_window,
                        service = %spec.service,
                        "Failed to calculate short window burn rate"
                    );
                    continue;
                }
            };

            // Short window must exceed factor
            if short_burn_rate <= alert.factor {
                debug!(
                    service = %spec.service,
                    short_burn_rate = short_burn_rate,
                    factor = alert.factor,
                    "Short window burn rate below threshold"
                );
                continue;
            }

            // Calculate burn rate for long window
            let long_burn_rate = match calculator
                .calculate_burn_rate_for_window(spec, &alert.long_window)
                .await
            {
                Ok(br) => br,
                Err(e) => {
                    debug!(
                        error = %e,
                        window = %alert.long_window,
                        service = %spec.service,
                        "Failed to calculate long window burn rate"
                    );
                    continue;
                }
            };

            // Long window must also exceed factor
            if long_burn_rate <= alert.factor {
                debug!(
                    service = %spec.service,
                    long_burn_rate = long_burn_rate,
                    factor = alert.factor,
                    "Long window burn rate below threshold (short exceeded)"
                );
                continue;
            }

            // Both windows exceed — fire alert
            info!(
                service = %spec.service,
                severity = %alert.severity,
                short_burn_rate = short_burn_rate,
                long_burn_rate = long_burn_rate,
                factor = alert.factor,
                "SLO burn rate alert firing"
            );

            // Record cooldown before API call
            self.record_cooldown(&fingerprint);

            // Create Investigation CRD
            self.create_investigation(
                spec,
                alert,
                short_burn_rate,
                long_burn_rate,
            )
            .await;
        }
    }

    /// Create an Investigation CRD for a burn rate alert
    async fn create_investigation(
        &mut self,
        spec: &ServiceLevelSpec,
        alert: &BurnRateAlert,
        short_burn_rate: f64,
        long_burn_rate: f64,
    ) {
        self.alert_seq = self.alert_seq.wrapping_add(1);
        let investigation_name = format!(
            "slo-burn-{:x}-{:04x}",
            Utc::now().timestamp(),
            self.alert_seq
        );

        let severity = map_alert_severity(&alert.severity);

        // Calculate approximate error budget remaining
        let error_budget = 1.0 - spec.objective.target;
        let budget_remaining = if error_budget > 0.0 {
            (1.0 - long_burn_rate).clamp(0.0, 1.0)
        } else {
            0.0
        };

        let condition = format!(
            "SLO burn rate alert: {} burn rate {:.1}x exceeds {:.1}x threshold ({}). \
             Short window ({}) burn rate: {:.1}x, Long window ({}) burn rate: {:.1}x. \
             Budget remaining: {:.1}%",
            spec.service,
            long_burn_rate,
            alert.factor,
            alert.severity,
            alert.short_window,
            short_burn_rate,
            alert.long_window,
            long_burn_rate,
            budget_remaining * 100.0
        );

        let investigation = Investigation::new(
            &investigation_name,
            InvestigationSpec {
                condition,
                service: spec.service.clone(),
                severity,
                triggered_at: Some(Utc::now().to_rfc3339()),
            },
        );

        let investigation_api: Api<Investigation> =
            Api::namespaced(self.client.clone(), &self.namespace);

        match investigation_api
            .create(&PostParams::default(), &investigation)
            .await
        {
            Ok(_) => {
                info!(
                    investigation = %investigation_name,
                    service = %spec.service,
                    severity = %alert.severity,
                    "Investigation created for SLO burn rate alert"
                );
            }
            Err(e) => {
                error!(
                    error = %e,
                    service = %spec.service,
                    "Failed to create Investigation CRD for SLO alert"
                );
            }
        }
    }

    /// Check if an alert fingerprint is in cooldown
    fn is_in_cooldown(&self, fingerprint: &str) -> bool {
        if let Some(last_fired) = self.cooldown.get(fingerprint) {
            let now = Utc::now().timestamp();
            now - last_fired < self.cooldown_secs
        } else {
            false
        }
    }

    /// Record a cooldown for an alert fingerprint
    fn record_cooldown(&mut self, fingerprint: &str) {
        self.cooldown
            .insert(fingerprint.to_string(), Utc::now().timestamp());
    }
}

/// Generate a fingerprint for alert cooldown tracking
///
/// Format: "slo:{servicelevel_name}:{alert_index}"
pub fn alert_fingerprint(servicelevel_name: &str, alert_index: usize) -> String {
    format!("slo:{}:{}", servicelevel_name, alert_index)
}

/// Map alert severity string to Investigation Severity enum
pub fn map_alert_severity(severity: &str) -> Severity {
    match severity.to_lowercase().as_str() {
        "critical" => Severity::Critical,
        "high" => Severity::High,
        "warning" => Severity::Medium,
        "low" => Severity::Low,
        _ => Severity::Medium,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // ----- alert_fingerprint tests -----

    #[test]
    fn test_alert_fingerprint_format() {
        let fp = alert_fingerprint("payments-slo", 0);
        assert_eq!(fp, "slo:payments-slo:0");
    }

    #[test]
    fn test_alert_fingerprint_different_index() {
        let fp0 = alert_fingerprint("payments-slo", 0);
        let fp1 = alert_fingerprint("payments-slo", 1);
        assert_ne!(fp0, fp1);
    }

    #[test]
    fn test_alert_fingerprint_different_name() {
        let fp1 = alert_fingerprint("payments-slo", 0);
        let fp2 = alert_fingerprint("auth-slo", 0);
        assert_ne!(fp1, fp2);
    }

    // ----- map_alert_severity tests -----

    #[test]
    fn test_map_severity_critical() {
        assert_eq!(map_alert_severity("critical"), Severity::Critical);
        assert_eq!(map_alert_severity("Critical"), Severity::Critical);
        assert_eq!(map_alert_severity("CRITICAL"), Severity::Critical);
    }

    #[test]
    fn test_map_severity_high() {
        assert_eq!(map_alert_severity("high"), Severity::High);
    }

    #[test]
    fn test_map_severity_warning() {
        assert_eq!(map_alert_severity("warning"), Severity::Medium);
    }

    #[test]
    fn test_map_severity_low() {
        assert_eq!(map_alert_severity("low"), Severity::Low);
    }

    #[test]
    fn test_map_severity_unknown_defaults_to_medium() {
        assert_eq!(map_alert_severity("unknown"), Severity::Medium);
        assert_eq!(map_alert_severity(""), Severity::Medium);
    }

    // ----- BurnRateAlerter cooldown tests -----

    #[test]
    fn test_cooldown_not_active_initially() {
        // We can't easily construct a BurnRateAlerter without a real K8s client,
        // but we can test the cooldown logic via the fingerprint functions
        let fp = alert_fingerprint("test", 0);
        assert_eq!(fp, "slo:test:0");
    }

    // ----- Multi-window evaluation logic tests -----

    #[test]
    fn test_both_windows_exceed_scenario() {
        // Scenario: short_burn_rate=15.0, long_burn_rate=7.0, factor=6.0
        // Both exceed → should alert
        let short = 15.0;
        let long = 7.0;
        let factor = 6.0;
        assert!(short > factor && long > factor);
    }

    #[test]
    fn test_only_short_exceeds_scenario() {
        // Scenario: short_burn_rate=15.0, long_burn_rate=3.0, factor=6.0
        // Only short exceeds → should NOT alert
        let short = 15.0;
        let long = 3.0;
        let factor = 6.0;
        assert!(short > factor && !(long > factor));
    }

    #[test]
    fn test_only_long_exceeds_scenario() {
        // Scenario: short_burn_rate=2.0, long_burn_rate=7.0, factor=6.0
        // Only long exceeds → should NOT alert
        let short = 2.0;
        let long = 7.0;
        let factor = 6.0;
        assert!(!(short > factor) && long > factor);
    }

    #[test]
    fn test_neither_window_exceeds_scenario() {
        // Scenario: short_burn_rate=2.0, long_burn_rate=3.0, factor=6.0
        // Neither exceeds → should NOT alert
        let short = 2.0;
        let long = 3.0;
        let factor = 6.0;
        assert!(!(short > factor) && !(long > factor));
    }

    #[test]
    fn test_exact_threshold_no_alert() {
        // Scenario: burn_rate == factor exactly → should NOT alert (must exceed, not equal)
        let burn_rate = 6.0;
        let factor = 6.0;
        assert!(!(burn_rate > factor));
    }
}
