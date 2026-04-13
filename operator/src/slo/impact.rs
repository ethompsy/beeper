//! Customer Impact Scorer — SLO-based anomaly prioritization
//!
//! Scores anomalies by customer impact using SLO data rather than
//! static severity labels. Considers SLO target stringency, burn rate
//! severity, and error budget depletion.

use tracing::debug;

use super::{SloCache, SloCalculationResult};

/// Default weights for the composite impact scoring formula
const W_TARGET: f64 = 0.3;
const W_BURN: f64 = 0.4;
const W_BUDGET: f64 = 0.3;

/// Maximum burn rate value for normalization (capped at 10x)
const MAX_BURN_RATE: f64 = 10.0;

/// Customer impact scorer that computes a normalized 0.0–1.0 score
/// based on SLO data from the shared cache.
pub struct CustomerImpactScorer {
    cache: SloCache,
}

impl CustomerImpactScorer {
    /// Create a new CustomerImpactScorer with access to the SLO cache
    pub fn new(cache: SloCache) -> Self {
        Self { cache }
    }

    /// Score a service's customer impact based on SLO data.
    ///
    /// Returns `Some(score)` where score is 0.0–1.0 (higher = more impact),
    /// or `None` if no SLO data exists for the service.
    ///
    /// When multiple ServiceLevel CRDs reference the same service,
    /// returns the HIGHEST impact score.
    pub async fn score_service(&self, service: &str) -> Option<f64> {
        let guard = self.cache.read().await;

        let mut max_score: Option<f64> = None;

        for result in guard.values() {
            if result.service == service {
                let score = compute_impact_score(result);
                max_score = Some(match max_score {
                    Some(current) => current.max(score),
                    None => score,
                });
            }
        }

        if let Some(score) = max_score {
            debug!(
                service = %service,
                impact_score = score,
                "Customer impact scored"
            );
        }

        max_score
    }
}

/// Compute the composite impact score for a single SLO calculation result.
///
/// Formula:
///   target_factor = clamp((target - 0.9) / 0.1, 0.0, 1.0)
///   burn_factor   = clamp(burn_rate / 10.0, 0.0, 1.0)
///   budget_factor = clamp(1.0 - error_budget_remaining, 0.0, 1.0)
///   impact_score  = 0.3 * target_factor + 0.4 * burn_factor + 0.3 * budget_factor
///
/// The target is extracted from the compliance/burn_rate relationship:
///   target = 1.0 - (1.0 - compliance) / burn_rate  (when burn_rate > 0)
pub fn compute_impact_score(result: &SloCalculationResult) -> f64 {
    let target = infer_target(result);
    let target_factor = compute_target_factor(target);
    let burn_factor = compute_burn_factor(result.burn_rate);
    let budget_factor = compute_budget_factor(result.error_budget_remaining);

    let score = W_TARGET * target_factor + W_BURN * burn_factor + W_BUDGET * budget_factor;
    score.clamp(0.0, 1.0)
}

/// Infer the SLO target from the calculation result.
///
/// Since SloCalculationResult doesn't store the target directly,
/// we derive it: target = 1.0 - (1.0 - compliance) / burn_rate
/// When burn_rate is 0 or NaN, assume a default target of 0.99.
fn infer_target(result: &SloCalculationResult) -> f64 {
    if result.burn_rate.is_nan() || result.burn_rate <= 0.0 {
        // No meaningful burn rate — assume a standard target
        0.99
    } else {
        let error_rate = 1.0 - result.compliance;
        let target = 1.0 - error_rate / result.burn_rate;
        // Clamp to reasonable range
        target.clamp(0.0, 1.0)
    }
}

/// Compute the target stringency factor (0.0–1.0).
///
/// Maps SLO target to a factor where higher targets = higher factor:
///   90% (0.9)  → 0.0
///   95% (0.95) → 0.5
///   99% (0.99) → 0.9
///   99.9% (0.999) → 0.99
fn compute_target_factor(target: f64) -> f64 {
    if target.is_nan() {
        return 0.0;
    }
    ((target - 0.9) / 0.1).clamp(0.0, 1.0)
}

/// Compute the burn rate severity factor (0.0–1.0).
///
/// Normalizes burn rate to 0.0–1.0 range, capped at 10x:
///   1x burn  → 0.1
///   5x burn  → 0.5
///   10x+ burn → 1.0
fn compute_burn_factor(burn_rate: f64) -> f64 {
    if burn_rate.is_nan() || burn_rate < 0.0 {
        return 0.0;
    }
    (burn_rate / MAX_BURN_RATE).clamp(0.0, 1.0)
}

/// Compute the error budget depletion factor (0.0–1.0).
///
/// Less budget remaining = higher impact:
///   90% remaining → 0.1 (low impact)
///   50% remaining → 0.5 (medium impact)
///   10% remaining → 0.9 (high impact)
fn compute_budget_factor(error_budget_remaining: f64) -> f64 {
    if error_budget_remaining.is_nan() {
        return 0.0;
    }
    (1.0 - error_budget_remaining).clamp(0.0, 1.0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;
    use std::sync::Arc;
    use tokio::sync::RwLock;

    fn make_result(
        service: &str,
        compliance: f64,
        burn_rate: f64,
        budget: f64,
    ) -> SloCalculationResult {
        SloCalculationResult {
            service: service.to_string(),
            sli_type: "availability".to_string(),
            compliance,
            burn_rate,
            error_budget_remaining: budget,
            good_count: 9990.0,
            total_count: 10000.0,
            timestamp: "2026-03-14T12:00:00Z".to_string(),
        }
    }

    // ----- compute_target_factor tests -----

    #[test]
    fn test_target_factor_90_percent() {
        assert!((compute_target_factor(0.9) - 0.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_target_factor_95_percent() {
        assert!((compute_target_factor(0.95) - 0.5).abs() < 1e-10);
    }

    #[test]
    fn test_target_factor_99_percent() {
        assert!((compute_target_factor(0.99) - 0.9).abs() < 1e-10);
    }

    #[test]
    fn test_target_factor_999_percent() {
        assert!((compute_target_factor(0.999) - 0.99).abs() < 1e-10);
    }

    #[test]
    fn test_target_factor_below_90_clamps_to_zero() {
        assert!((compute_target_factor(0.8)).abs() < f64::EPSILON);
    }

    #[test]
    fn test_target_factor_above_100_clamps_to_one() {
        assert!((compute_target_factor(1.1) - 1.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_target_factor_nan() {
        assert!((compute_target_factor(f64::NAN)).abs() < f64::EPSILON);
    }

    // ----- compute_burn_factor tests -----

    #[test]
    fn test_burn_factor_1x() {
        assert!((compute_burn_factor(1.0) - 0.1).abs() < f64::EPSILON);
    }

    #[test]
    fn test_burn_factor_5x() {
        assert!((compute_burn_factor(5.0) - 0.5).abs() < f64::EPSILON);
    }

    #[test]
    fn test_burn_factor_10x() {
        assert!((compute_burn_factor(10.0) - 1.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_burn_factor_exceeds_10x_clamped() {
        assert!((compute_burn_factor(20.0) - 1.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_burn_factor_zero() {
        assert!((compute_burn_factor(0.0)).abs() < f64::EPSILON);
    }

    #[test]
    fn test_burn_factor_negative() {
        assert!((compute_burn_factor(-1.0)).abs() < f64::EPSILON);
    }

    #[test]
    fn test_burn_factor_nan() {
        assert!((compute_burn_factor(f64::NAN)).abs() < f64::EPSILON);
    }

    // ----- compute_budget_factor tests -----

    #[test]
    fn test_budget_factor_90_remaining() {
        assert!((compute_budget_factor(0.9) - 0.1).abs() < f64::EPSILON);
    }

    #[test]
    fn test_budget_factor_50_remaining() {
        assert!((compute_budget_factor(0.5) - 0.5).abs() < f64::EPSILON);
    }

    #[test]
    fn test_budget_factor_10_remaining() {
        assert!((compute_budget_factor(0.1) - 0.9).abs() < f64::EPSILON);
    }

    #[test]
    fn test_budget_factor_zero_remaining() {
        assert!((compute_budget_factor(0.0) - 1.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_budget_factor_full_remaining() {
        assert!((compute_budget_factor(1.0)).abs() < f64::EPSILON);
    }

    #[test]
    fn test_budget_factor_nan() {
        assert!((compute_budget_factor(f64::NAN)).abs() < f64::EPSILON);
    }

    // ----- compute_impact_score tests -----

    #[test]
    fn test_impact_score_high_impact() {
        // 99.9% SLO target, 5x burn rate, 50% budget remaining
        // infer_target: 1.0 - (1.0 - 0.995) / 5.0 = 1.0 - 0.001 = 0.999
        // target_factor = (0.999 - 0.9) / 0.1 = 0.99
        // burn_factor = 5.0 / 10.0 = 0.5
        // budget_factor = 1.0 - 0.5 = 0.5
        // score = 0.3*0.99 + 0.4*0.5 + 0.3*0.5 = 0.297 + 0.2 + 0.15 = 0.647
        let result = SloCalculationResult {
            service: "payment-service".to_string(),
            sli_type: "availability".to_string(),
            compliance: 0.995, // infer_target → 0.999 (99.9% SLO)
            burn_rate: 5.0,
            error_budget_remaining: 0.5,
            good_count: 9950.0,
            total_count: 10000.0,
            timestamp: "2026-03-14T12:00:00Z".to_string(),
        };
        let score = compute_impact_score(&result);
        let expected = 0.3 * 0.99 + 0.4 * 0.5 + 0.3 * 0.5;
        assert!(
            (score - expected).abs() < 1e-10,
            "High impact: expected {:.4}, got {:.4}",
            expected,
            score
        );
        assert!(score <= 1.0);
    }

    #[test]
    fn test_impact_score_low_impact() {
        // 99% SLO target, 1x burn rate, 90% budget remaining
        // target_factor = 0.9, burn_factor = 0.1, budget_factor = 0.1
        // score = 0.3*0.9 + 0.4*0.1 + 0.3*0.1 = 0.27 + 0.04 + 0.03 = 0.34
        let result = SloCalculationResult {
            service: "internal-service".to_string(),
            sli_type: "availability".to_string(),
            compliance: 0.99,
            burn_rate: 1.0,
            error_budget_remaining: 0.9,
            good_count: 990.0,
            total_count: 1000.0,
            timestamp: "2026-03-14T12:00:00Z".to_string(),
        };
        let score = compute_impact_score(&result);
        let expected = 0.3 * 0.9 + 0.4 * 0.1 + 0.3 * 0.1;
        assert!(
            (score - expected).abs() < 1e-10,
            "Low impact: expected {:.4}, got {:.4}",
            expected,
            score
        );
        assert!(score > 0.0);
    }

    #[test]
    fn test_ac1_ordering_999_50_higher_than_99_90() {
        // AC1: 99.9% SLO with 50% budget > 99% SLO with 90% budget
        let high_impact = make_result("critical-svc", 0.995, 5.0, 0.5);
        let low_impact = make_result("internal-svc", 0.99, 1.0, 0.9);

        let high_score = compute_impact_score(&high_impact);
        let low_score = compute_impact_score(&low_impact);

        assert!(
            high_score > low_score,
            "99.9% SLO/50% budget ({:.3}) must score higher than 99% SLO/90% budget ({:.3})",
            high_score,
            low_score
        );
    }

    #[test]
    fn test_impact_score_clamped_to_0_1() {
        let result = make_result("test-svc", 0.0, 100.0, 0.0);
        let score = compute_impact_score(&result);
        assert!(
            score >= 0.0 && score <= 1.0,
            "Score must be [0,1], got {}",
            score
        );
    }

    #[test]
    fn test_impact_score_with_zero_burn_rate() {
        let result = make_result("healthy-svc", 1.0, 0.0, 1.0);
        let score = compute_impact_score(&result);
        assert!(score >= 0.0 && score <= 1.0);
        // With zero burn rate and full budget, impact should be low
        assert!(
            score < 0.5,
            "Healthy service should have low impact, got {}",
            score
        );
    }

    // ----- infer_target tests -----

    #[test]
    fn test_infer_target_normal_case() {
        // compliance = 0.999, burn_rate = 1.0
        // error_rate = 0.001, target = 1.0 - 0.001/1.0 = 0.999
        let result = make_result("svc", 0.999, 1.0, 0.9);
        let target = infer_target(&result);
        assert!(
            (target - 0.999).abs() < 0.001,
            "Expected ~0.999, got {}",
            target
        );
    }

    #[test]
    fn test_infer_target_zero_burn_rate_defaults() {
        let result = make_result("svc", 0.999, 0.0, 1.0);
        let target = infer_target(&result);
        assert!((target - 0.99).abs() < f64::EPSILON);
    }

    #[test]
    fn test_infer_target_nan_burn_rate_defaults() {
        let result = make_result("svc", 0.999, f64::NAN, 1.0);
        let target = infer_target(&result);
        assert!((target - 0.99).abs() < f64::EPSILON);
    }

    // ----- CustomerImpactScorer async tests -----

    #[tokio::test]
    async fn test_scorer_no_slo_data_returns_none() {
        let cache = Arc::new(RwLock::new(HashMap::new()));
        let scorer = CustomerImpactScorer::new(cache);
        assert!(scorer.score_service("unknown-service").await.is_none());
    }

    #[tokio::test]
    async fn test_scorer_empty_cache_returns_none() {
        let cache = Arc::new(RwLock::new(HashMap::new()));
        let scorer = CustomerImpactScorer::new(cache);
        assert!(scorer.score_service("payment-service").await.is_none());
    }

    #[tokio::test]
    async fn test_scorer_returns_score_for_matching_service() {
        let mut map = HashMap::new();
        map.insert(
            "payments-slo".to_string(),
            make_result("payment-service", 0.999, 5.0, 0.5),
        );

        let cache = Arc::new(RwLock::new(map));
        let scorer = CustomerImpactScorer::new(cache);

        let score = scorer.score_service("payment-service").await;
        assert!(score.is_some());
        let score = score.unwrap();
        assert!(score > 0.0 && score <= 1.0);
    }

    #[tokio::test]
    async fn test_scorer_multi_slo_returns_highest() {
        let mut map = HashMap::new();
        // Two SLOs for the same service — availability (high impact) and latency (low impact)
        map.insert(
            "payments-avail".to_string(),
            make_result("payment-service", 0.995, 5.0, 0.5),
        );
        map.insert(
            "payments-latency".to_string(),
            make_result("payment-service", 0.99, 1.0, 0.9),
        );

        let cache = Arc::new(RwLock::new(map));
        let scorer = CustomerImpactScorer::new(cache);

        let score = scorer.score_service("payment-service").await;
        assert!(score.is_some());

        // Should be the higher of the two
        let avail_score = compute_impact_score(&make_result("payment-service", 0.995, 5.0, 0.5));
        let latency_score = compute_impact_score(&make_result("payment-service", 0.99, 1.0, 0.9));
        assert!(avail_score > latency_score);
        assert!((score.unwrap() - avail_score).abs() < f64::EPSILON);
    }

    #[tokio::test]
    async fn test_scorer_does_not_match_different_service() {
        let mut map = HashMap::new();
        map.insert(
            "payments-slo".to_string(),
            make_result("payment-service", 0.999, 5.0, 0.5),
        );

        let cache = Arc::new(RwLock::new(map));
        let scorer = CustomerImpactScorer::new(cache);

        assert!(scorer.score_service("auth-service").await.is_none());
    }
}
