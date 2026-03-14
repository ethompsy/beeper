//! SLO Calculator — compliance and burn rate computation
//!
//! Queries Prometheus for good/total event counts and computes SLO
//! compliance percentage and burn rate using the Google SRE model.

use chrono::Utc;
use tracing::{debug, warn};

use crate::crds::ServiceLevelSpec;
use crate::sources::PrometheusClient;

use super::{SloCalculationResult, SloError};

/// SLO calculator that queries Prometheus and computes burn rates
pub struct SloCalculator {
    prometheus: PrometheusClient,
}

impl SloCalculator {
    /// Create a new SloCalculator with a Prometheus client
    pub fn new(prometheus: PrometheusClient) -> Self {
        Self { prometheus }
    }

    /// Calculate SLO compliance and burn rate for a ServiceLevel spec over a window
    ///
    /// Queries Prometheus for good/total event counts, computes:
    /// - compliance = good / total
    /// - burn_rate = (1 - compliance) / (1 - target)
    /// - error_budget_remaining = 1 - burn_rate (clamped to 0..1)
    pub async fn calculate(
        &self,
        spec: &ServiceLevelSpec,
        window: &str,
    ) -> Result<SloCalculationResult, SloError> {
        let good_count = self.query_count(spec, &spec.sli.good_selector, window).await?;
        let total_count = self.query_count(spec, &spec.sli.total_selector, window).await?;

        let (compliance, burn_rate, error_budget_remaining) =
            compute_burn_rate(good_count, total_count, spec.objective.target);

        let sli_type = crate::api::sli_type_to_string(&spec.sli.sli_type);

        Ok(SloCalculationResult {
            service: spec.service.clone(),
            sli_type,
            compliance,
            burn_rate,
            error_budget_remaining,
            good_count,
            total_count,
            timestamp: Utc::now().to_rfc3339(),
        })
    }

    /// Calculate burn rate over a specific window (for multi-window alerting)
    pub async fn calculate_burn_rate_for_window(
        &self,
        spec: &ServiceLevelSpec,
        window: &str,
    ) -> Result<f64, SloError> {
        let good_count = self.query_count(spec, &spec.sli.good_selector, window).await?;
        let total_count = self.query_count(spec, &spec.sli.total_selector, window).await?;

        let (_, burn_rate, _) = compute_burn_rate(good_count, total_count, spec.objective.target);
        Ok(burn_rate)
    }

    /// Query Prometheus for the count of events matching a selector over a window
    async fn query_count(
        &self,
        spec: &ServiceLevelSpec,
        selector: &str,
        window: &str,
    ) -> Result<f64, SloError> {
        // Build PromQL: increase(metric{selector}[window])
        let promql = format!("increase({}{}[{}])", spec.sli.metric, selector, window);

        debug!(promql = %promql, "Querying Prometheus for SLO count");

        let result = self.prometheus.query(&promql).await?;

        // Sum all result values (handles multi-instance metrics)
        let mut total = 0.0;
        for item in &result.results {
            if let Some((_, value_str)) = &item.value {
                if let Ok(v) = value_str.parse::<f64>() {
                    if !v.is_nan() && v.is_finite() {
                        total += v;
                    }
                }
            }
        }

        debug!(promql = %promql, total = total, "Prometheus SLO count result");
        Ok(total)
    }
}

/// Compute burn rate from good/total counts and target.
///
/// Returns (compliance, burn_rate, error_budget_remaining).
///
/// - compliance = good / total (1.0 if total == 0)
/// - burn_rate = error_rate / error_budget = (1 - compliance) / (1 - target)
/// - error_budget_remaining = max(0, 1 - burn_rate)
///
/// Edge cases:
/// - total == 0: returns (1.0, 0.0, 1.0) — no data means no errors
/// - target == 1.0: burn_rate is f64::INFINITY if any errors exist, 0.0 otherwise
/// - NaN inputs: treated as 0.0
pub fn compute_burn_rate(good_count: f64, total_count: f64, target: f64) -> (f64, f64, f64) {
    // Sanitize NaN
    let good = if good_count.is_nan() { 0.0 } else { good_count };
    let total = if total_count.is_nan() {
        0.0
    } else {
        total_count
    };

    // No data — assume compliant
    if total <= 0.0 {
        return (1.0, 0.0, 1.0);
    }

    // Compliance: good / total, clamped to [0.0, 1.0]
    let compliance = (good / total).clamp(0.0, 1.0);

    let error_rate = 1.0 - compliance;
    let error_budget = 1.0 - target;

    // Burn rate
    let burn_rate = if error_budget <= 0.0 {
        // Target is 1.0 (or effectively 1.0) — any errors mean infinite burn
        if error_rate > 0.0 {
            f64::INFINITY
        } else {
            0.0
        }
    } else {
        error_rate / error_budget
    };

    // Error budget remaining: 1 - burn_rate, clamped to [0.0, 1.0]
    let error_budget_remaining = if burn_rate.is_infinite() {
        0.0
    } else {
        (1.0 - burn_rate).clamp(0.0, 1.0)
    };

    (compliance, burn_rate, error_budget_remaining)
}

/// Parse a window duration string into seconds
///
/// Supports: "Xs" (seconds), "Xm" (minutes), "Xh" (hours), "Xd" (days)
pub fn parse_window_duration(window: &str) -> Result<u64, SloError> {
    let window = window.trim();
    if window.is_empty() {
        return Err(SloError::WindowParseError(
            "empty window string".to_string(),
        ));
    }

    let (num_str, suffix) = window.split_at(window.len() - 1);
    let num: u64 = num_str.parse().map_err(|_| {
        SloError::WindowParseError(format!("invalid window format: {}", window))
    })?;

    match suffix {
        "s" => Ok(num),
        "m" => Ok(num * 60),
        "h" => Ok(num * 3600),
        "d" => Ok(num * 86400),
        _ => Err(SloError::WindowParseError(format!(
            "unknown window suffix '{}' in '{}'",
            suffix, window
        ))),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // ----- compute_burn_rate tests -----

    #[test]
    fn test_perfect_compliance() {
        let (compliance, burn_rate, budget) = compute_burn_rate(10000.0, 10000.0, 0.999);
        assert_eq!(compliance, 1.0);
        assert_eq!(burn_rate, 0.0);
        assert_eq!(budget, 1.0);
    }

    #[test]
    fn test_99_9_percent_compliance() {
        let (compliance, burn_rate, budget) = compute_burn_rate(9990.0, 10000.0, 0.999);
        assert!((compliance - 0.999).abs() < 1e-10);
        assert!((burn_rate - 1.0).abs() < 1e-10);
        assert!((budget - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_high_burn_rate() {
        // 99% compliance with 99.9% target = burn rate 10x
        let (compliance, burn_rate, _budget) = compute_burn_rate(9900.0, 10000.0, 0.999);
        assert!((compliance - 0.99).abs() < 1e-10);
        assert!((burn_rate - 10.0).abs() < 1e-10);
    }

    #[test]
    fn test_14_4x_burn_rate() {
        // Error rate of 0.0144 with target 0.999 → burn rate = 0.0144 / 0.001 = 14.4
        let good = 10000.0 - 144.0;
        let (compliance, burn_rate, _) = compute_burn_rate(good, 10000.0, 0.999);
        assert!((compliance - 0.9856).abs() < 1e-10);
        assert!((burn_rate - 14.4).abs() < 1e-10);
    }

    #[test]
    fn test_zero_total_count() {
        let (compliance, burn_rate, budget) = compute_burn_rate(0.0, 0.0, 0.999);
        assert_eq!(compliance, 1.0);
        assert_eq!(burn_rate, 0.0);
        assert_eq!(budget, 1.0);
    }

    #[test]
    fn test_negative_total_count() {
        let (compliance, burn_rate, budget) = compute_burn_rate(100.0, -1.0, 0.999);
        assert_eq!(compliance, 1.0);
        assert_eq!(burn_rate, 0.0);
        assert_eq!(budget, 1.0);
    }

    #[test]
    fn test_target_1_0_perfect() {
        let (compliance, burn_rate, budget) = compute_burn_rate(10000.0, 10000.0, 1.0);
        assert_eq!(compliance, 1.0);
        assert_eq!(burn_rate, 0.0);
        assert_eq!(budget, 1.0);
    }

    #[test]
    fn test_target_1_0_with_errors() {
        let (compliance, burn_rate, budget) = compute_burn_rate(9999.0, 10000.0, 1.0);
        assert!((compliance - 0.9999).abs() < 1e-10);
        assert!(burn_rate.is_infinite());
        assert_eq!(budget, 0.0);
    }

    #[test]
    fn test_zero_compliance() {
        let (compliance, burn_rate, budget) = compute_burn_rate(0.0, 10000.0, 0.999);
        assert_eq!(compliance, 0.0);
        assert!((burn_rate - 1000.0).abs() < 1e-10);
        assert_eq!(budget, 0.0);
    }

    #[test]
    fn test_nan_good_count() {
        let (compliance, burn_rate, budget) = compute_burn_rate(f64::NAN, 10000.0, 0.999);
        assert_eq!(compliance, 0.0);
        assert!((burn_rate - 1000.0).abs() < 1e-10);
        assert_eq!(budget, 0.0);
    }

    #[test]
    fn test_nan_total_count() {
        let (compliance, burn_rate, budget) = compute_burn_rate(9000.0, f64::NAN, 0.999);
        assert_eq!(compliance, 1.0);
        assert_eq!(burn_rate, 0.0);
        assert_eq!(budget, 1.0);
    }

    #[test]
    fn test_good_exceeds_total() {
        // Good > total should clamp compliance to 1.0
        let (compliance, burn_rate, budget) = compute_burn_rate(11000.0, 10000.0, 0.999);
        assert_eq!(compliance, 1.0);
        assert_eq!(burn_rate, 0.0);
        assert_eq!(budget, 1.0);
    }

    #[test]
    fn test_95_percent_target() {
        // 90% compliance with 95% target → burn rate = 0.10/0.05 = 2.0
        let (compliance, burn_rate, _) = compute_burn_rate(9000.0, 10000.0, 0.95);
        assert!((compliance - 0.9).abs() < 1e-10);
        assert!((burn_rate - 2.0).abs() < 1e-10);
    }

    // ----- parse_window_duration tests -----

    #[test]
    fn test_parse_seconds() {
        assert_eq!(parse_window_duration("30s").unwrap(), 30);
        assert_eq!(parse_window_duration("1s").unwrap(), 1);
    }

    #[test]
    fn test_parse_minutes() {
        assert_eq!(parse_window_duration("5m").unwrap(), 300);
        assert_eq!(parse_window_duration("1m").unwrap(), 60);
        assert_eq!(parse_window_duration("15m").unwrap(), 900);
    }

    #[test]
    fn test_parse_hours() {
        assert_eq!(parse_window_duration("1h").unwrap(), 3600);
        assert_eq!(parse_window_duration("6h").unwrap(), 21600);
        assert_eq!(parse_window_duration("24h").unwrap(), 86400);
    }

    #[test]
    fn test_parse_days() {
        assert_eq!(parse_window_duration("1d").unwrap(), 86400);
        assert_eq!(parse_window_duration("7d").unwrap(), 604800);
        assert_eq!(parse_window_duration("30d").unwrap(), 2592000);
    }

    #[test]
    fn test_parse_empty() {
        assert!(parse_window_duration("").is_err());
    }

    #[test]
    fn test_parse_invalid_suffix() {
        assert!(parse_window_duration("5x").is_err());
    }

    #[test]
    fn test_parse_invalid_number() {
        assert!(parse_window_duration("abcm").is_err());
    }

    #[test]
    fn test_parse_whitespace() {
        assert_eq!(parse_window_duration(" 5m ").unwrap(), 300);
    }

}
