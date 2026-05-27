//! Error Budget Policy Evaluator — threshold-based policy evaluation
//!
//! Evaluates error budget policies defined on ServiceLevel CRDs.
//! Generates policy events when budget consumption crosses configured
//! thresholds. Supports "notify" and "freeze" actions. Events are
//! edge-triggered (fire once per threshold crossing, not every cycle).

use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use chrono::Utc;
use serde::{Deserialize, Serialize};
use tokio::sync::RwLock;
use tracing::{debug, info};

use crate::crds::{BudgetPolicyAction, ErrorBudgetPolicy};

use super::calculator::parse_window_duration;
use super::SloCalculationResult;

/// A triggered budget policy event
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct BudgetPolicyEvent {
    /// Service name
    pub service: String,

    /// ServiceLevel CRD name
    pub servicelevel_name: String,

    /// Threshold that was crossed (0.0–1.0)
    pub threshold: f64,

    /// Budget consumption at time of trigger (0.0–1.0)
    pub current_consumption: f64,

    /// Action type: "notify" or "freeze"
    pub action: String,

    /// Current burn rate at time of trigger
    pub burn_rate: f64,

    /// Projected time to budget exhaustion in seconds (None if not burning)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub projected_exhaustion_secs: Option<f64>,

    /// ISO 8601 timestamp when the policy was triggered
    pub triggered_at: String,
}

/// Maximum number of triggered events kept per ServiceLevel
const MAX_TRIGGERED_EVENTS: usize = 100;

/// Per-ServiceLevel budget status tracking
#[derive(Debug, Clone, Default)]
pub struct ServiceBudgetStatus {
    /// Whether a freeze policy is currently active
    pub is_frozen: bool,

    /// List of triggered policy events (most recent last).
    /// NOTE: Capped at MAX_TRIGGERED_EVENTS in evaluate(). Do not push directly
    /// without applying the same cap logic.
    pub triggered_events: Vec<BudgetPolicyEvent>,

    /// Set of triggered threshold fingerprints for edge-trigger detection
    /// Uses (threshold * 10000) as u64 for comparison
    pub triggered_thresholds: HashSet<u64>,
}

/// Shared budget policy state accessible by API and SLO engine
pub type BudgetPolicyState = Arc<RwLock<HashMap<String, ServiceBudgetStatus>>>;

/// Create a new empty budget policy state
pub fn new_budget_policy_state() -> BudgetPolicyState {
    Arc::new(RwLock::new(HashMap::new()))
}

/// Convert a threshold to a u64 fingerprint for deduplication
fn threshold_fingerprint(threshold: f64) -> u64 {
    (threshold * 10000.0) as u64
}

/// Calculate projected time to budget exhaustion in seconds
///
/// Returns None if not burning (burn_rate <= 0) or already exhausted (budget_remaining <= 0)
pub fn projected_exhaustion_secs(
    error_budget_remaining: f64,
    burn_rate: f64,
    window: &str,
) -> Option<f64> {
    if burn_rate <= 0.0 || error_budget_remaining <= 0.0 {
        return None;
    }

    let window_secs = match parse_window_duration(window) {
        Ok(secs) => secs as f64,
        Err(_) => return None,
    };

    Some((error_budget_remaining * window_secs) / burn_rate)
}

/// Error budget policy evaluator
///
/// Evaluates error budget policies against current SLO calculations.
/// Events are edge-triggered: each threshold fires only once per crossing.
pub struct ErrorBudgetEvaluator {
    state: BudgetPolicyState,
}

impl ErrorBudgetEvaluator {
    /// Create a new evaluator with shared state
    pub fn new(state: BudgetPolicyState) -> Self {
        Self { state }
    }

    /// Evaluate error budget policies for a ServiceLevel
    ///
    /// Compares current budget consumption against configured thresholds.
    /// Generates events on state transitions (edge-triggered).
    pub async fn evaluate(
        &self,
        servicelevel_name: &str,
        service: &str,
        policies: &[ErrorBudgetPolicy],
        result: &SloCalculationResult,
        window: &str,
    ) {
        let consumption = 1.0 - result.error_budget_remaining;
        let mut state = self.state.write().await;
        let status = state.entry(servicelevel_name.to_string()).or_default();

        // Track whether any freeze policy is currently active
        let mut any_freeze_active = false;

        for policy in policies {
            let fp = threshold_fingerprint(policy.threshold);
            let was_triggered = status.triggered_thresholds.contains(&fp);
            let is_exceeded = consumption >= policy.threshold;

            if is_exceeded && !was_triggered {
                // Threshold newly crossed — fire event
                let projected = projected_exhaustion_secs(
                    result.error_budget_remaining,
                    result.burn_rate,
                    window,
                );

                let action_str = match policy.action {
                    BudgetPolicyAction::Notify => "notify",
                    BudgetPolicyAction::Freeze => "freeze",
                };

                let event = BudgetPolicyEvent {
                    service: service.to_string(),
                    servicelevel_name: servicelevel_name.to_string(),
                    threshold: policy.threshold,
                    current_consumption: consumption,
                    action: action_str.to_string(),
                    burn_rate: result.burn_rate,
                    projected_exhaustion_secs: projected,
                    triggered_at: Utc::now().to_rfc3339(),
                };

                info!(
                    service = %service,
                    threshold = policy.threshold,
                    consumption = consumption,
                    action = action_str,
                    burn_rate = result.burn_rate,
                    projected_exhaustion_secs = ?projected,
                    "Error budget policy triggered"
                );

                status.triggered_thresholds.insert(fp);
                status.triggered_events.push(event);

                // Cap triggered_events to prevent unbounded growth
                if status.triggered_events.len() > MAX_TRIGGERED_EVENTS {
                    let excess = status.triggered_events.len() - MAX_TRIGGERED_EVENTS;
                    status.triggered_events.drain(..excess);
                }
            } else if !is_exceeded && was_triggered {
                // Budget recovered below threshold — reset
                debug!(
                    service = %service,
                    threshold = policy.threshold,
                    consumption = consumption,
                    "Error budget recovered below threshold"
                );
                status.triggered_thresholds.remove(&fp);

                // Remove events for this threshold
                status
                    .triggered_events
                    .retain(|e| threshold_fingerprint(e.threshold) != fp);
            }

            // Check if any freeze policy is currently active
            if policy.action == BudgetPolicyAction::Freeze && is_exceeded {
                any_freeze_active = true;
            }
        }

        status.is_frozen = any_freeze_active;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_result(error_budget_remaining: f64, burn_rate: f64) -> SloCalculationResult {
        SloCalculationResult {
            service: "payment-service".to_string(),
            sli_type: "availability".to_string(),
            compliance: 1.0 - (1.0 - 0.999) * (1.0 - error_budget_remaining),
            burn_rate,
            error_budget_remaining,
            good_count: 9990.0,
            total_count: 10000.0,
            timestamp: "2026-03-14T12:00:00Z".to_string(),
        }
    }

    // ----- threshold_fingerprint tests -----

    #[test]
    fn test_threshold_fingerprint_values() {
        assert_eq!(threshold_fingerprint(0.50), 5000);
        assert_eq!(threshold_fingerprint(0.75), 7500);
        assert_eq!(threshold_fingerprint(0.95), 9500);
        assert_eq!(threshold_fingerprint(1.0), 10000);
    }

    #[test]
    fn test_threshold_fingerprint_uniqueness() {
        assert_ne!(threshold_fingerprint(0.50), threshold_fingerprint(0.51));
        assert_ne!(threshold_fingerprint(0.90), threshold_fingerprint(0.95));
    }

    // ----- projected_exhaustion_secs tests -----

    #[test]
    fn test_projected_exhaustion_basic() {
        // 50% remaining, 30d window, 5x burn
        // Expected: (0.5 * 2592000) / 5 = 259200 secs (3 days)
        let result = projected_exhaustion_secs(0.5, 5.0, "30d");
        assert!(result.is_some());
        let secs = result.unwrap();
        assert!((secs - 259200.0).abs() < 1.0);
    }

    #[test]
    fn test_projected_exhaustion_full_budget_normal_burn() {
        // 100% remaining, 30d window, 1x burn
        // Expected: (1.0 * 2592000) / 1.0 = 2592000 secs (30 days)
        let result = projected_exhaustion_secs(1.0, 1.0, "30d");
        assert!(result.is_some());
        let secs = result.unwrap();
        assert!((secs - 2592000.0).abs() < 1.0);
    }

    #[test]
    fn test_projected_exhaustion_zero_burn_rate() {
        let result = projected_exhaustion_secs(0.5, 0.0, "30d");
        assert!(result.is_none());
    }

    #[test]
    fn test_projected_exhaustion_negative_burn_rate() {
        let result = projected_exhaustion_secs(0.5, -1.0, "30d");
        assert!(result.is_none());
    }

    #[test]
    fn test_projected_exhaustion_zero_budget() {
        let result = projected_exhaustion_secs(0.0, 5.0, "30d");
        assert!(result.is_none());
    }

    #[test]
    fn test_projected_exhaustion_invalid_window() {
        let result = projected_exhaustion_secs(0.5, 5.0, "invalid");
        assert!(result.is_none());
    }

    // ----- BudgetPolicyEvent serialization tests -----

    #[test]
    fn test_budget_policy_event_serialization() {
        let event = BudgetPolicyEvent {
            service: "payment-service".to_string(),
            servicelevel_name: "payments-slo".to_string(),
            threshold: 0.75,
            current_consumption: 0.80,
            action: "notify".to_string(),
            burn_rate: 3.0,
            projected_exhaustion_secs: Some(172800.0),
            triggered_at: "2026-03-14T12:00:00Z".to_string(),
        };

        let json = serde_json::to_string(&event).unwrap();
        assert!(json.contains("\"service\":\"payment-service\""));
        assert!(json.contains("\"threshold\":0.75"));
        assert!(json.contains("\"current_consumption\":0.8"));
        assert!(json.contains("\"action\":\"notify\""));
        assert!(json.contains("\"burn_rate\":3.0"));
        assert!(json.contains("\"projected_exhaustion_secs\":172800.0"));
    }

    #[test]
    fn test_budget_policy_event_no_projected_exhaustion() {
        let event = BudgetPolicyEvent {
            service: "payment-service".to_string(),
            servicelevel_name: "payments-slo".to_string(),
            threshold: 0.95,
            current_consumption: 0.96,
            action: "freeze".to_string(),
            burn_rate: 0.0,
            projected_exhaustion_secs: None,
            triggered_at: "2026-03-14T12:00:00Z".to_string(),
        };

        let json = serde_json::to_string(&event).unwrap();
        assert!(!json.contains("projected_exhaustion_secs"));
    }

    // ----- ErrorBudgetEvaluator tests -----

    #[tokio::test]
    async fn test_evaluator_threshold_crossing_generates_event() {
        let state = new_budget_policy_state();
        let evaluator = ErrorBudgetEvaluator::new(state.clone());

        let policies = vec![ErrorBudgetPolicy {
            threshold: 0.5,
            action: BudgetPolicyAction::Notify,
        }];

        // 60% consumed (error_budget_remaining = 0.4)
        let result = sample_result(0.4, 3.0);
        evaluator
            .evaluate("payments-slo", "payment-service", &policies, &result, "30d")
            .await;

        let guard = state.read().await;
        let status = guard.get("payments-slo").unwrap();
        assert_eq!(status.triggered_events.len(), 1);
        assert_eq!(status.triggered_events[0].threshold, 0.5);
        assert_eq!(status.triggered_events[0].action, "notify");
        assert!((status.triggered_events[0].current_consumption - 0.6).abs() < 1e-10);
        assert!(!status.is_frozen);
    }

    #[tokio::test]
    async fn test_evaluator_threshold_not_crossed_no_event() {
        let state = new_budget_policy_state();
        let evaluator = ErrorBudgetEvaluator::new(state.clone());

        let policies = vec![ErrorBudgetPolicy {
            threshold: 0.5,
            action: BudgetPolicyAction::Notify,
        }];

        // Only 30% consumed (error_budget_remaining = 0.7)
        let result = sample_result(0.7, 1.0);
        evaluator
            .evaluate("payments-slo", "payment-service", &policies, &result, "30d")
            .await;

        let guard = state.read().await;
        let status = guard.get("payments-slo").unwrap();
        assert_eq!(status.triggered_events.len(), 0);
        assert!(!status.is_frozen);
    }

    #[tokio::test]
    async fn test_evaluator_edge_triggered_no_duplicate() {
        let state = new_budget_policy_state();
        let evaluator = ErrorBudgetEvaluator::new(state.clone());

        let policies = vec![ErrorBudgetPolicy {
            threshold: 0.5,
            action: BudgetPolicyAction::Notify,
        }];

        // First evaluation: 60% consumed — triggers
        let result = sample_result(0.4, 3.0);
        evaluator
            .evaluate("payments-slo", "payment-service", &policies, &result, "30d")
            .await;

        // Second evaluation: still 60% consumed — should NOT trigger again
        evaluator
            .evaluate("payments-slo", "payment-service", &policies, &result, "30d")
            .await;

        let guard = state.read().await;
        let status = guard.get("payments-slo").unwrap();
        assert_eq!(status.triggered_events.len(), 1); // Only one event, not two
    }

    #[tokio::test]
    async fn test_evaluator_recovery_clears_threshold() {
        let state = new_budget_policy_state();
        let evaluator = ErrorBudgetEvaluator::new(state.clone());

        let policies = vec![ErrorBudgetPolicy {
            threshold: 0.5,
            action: BudgetPolicyAction::Notify,
        }];

        // Trigger: 60% consumed
        let result_high = sample_result(0.4, 3.0);
        evaluator
            .evaluate(
                "payments-slo",
                "payment-service",
                &policies,
                &result_high,
                "30d",
            )
            .await;

        {
            let guard = state.read().await;
            assert_eq!(guard.get("payments-slo").unwrap().triggered_events.len(), 1);
        }

        // Recover: 30% consumed — clears threshold
        let result_low = sample_result(0.7, 0.5);
        evaluator
            .evaluate(
                "payments-slo",
                "payment-service",
                &policies,
                &result_low,
                "30d",
            )
            .await;

        {
            let guard = state.read().await;
            let status = guard.get("payments-slo").unwrap();
            assert_eq!(status.triggered_events.len(), 0);
            assert!(status.triggered_thresholds.is_empty());
        }

        // Re-trigger: 60% consumed again — should fire new event
        evaluator
            .evaluate(
                "payments-slo",
                "payment-service",
                &policies,
                &result_high,
                "30d",
            )
            .await;

        let guard = state.read().await;
        let status = guard.get("payments-slo").unwrap();
        assert_eq!(status.triggered_events.len(), 1); // New event after recovery
    }

    #[tokio::test]
    async fn test_evaluator_freeze_action_sets_is_frozen() {
        let state = new_budget_policy_state();
        let evaluator = ErrorBudgetEvaluator::new(state.clone());

        let policies = vec![ErrorBudgetPolicy {
            threshold: 0.95,
            action: BudgetPolicyAction::Freeze,
        }];

        // 96% consumed
        let result = sample_result(0.04, 10.0);
        evaluator
            .evaluate("payments-slo", "payment-service", &policies, &result, "30d")
            .await;

        let guard = state.read().await;
        let status = guard.get("payments-slo").unwrap();
        assert!(status.is_frozen);
        assert_eq!(status.triggered_events.len(), 1);
        assert_eq!(status.triggered_events[0].action, "freeze");
    }

    #[tokio::test]
    async fn test_evaluator_freeze_recovery_clears_is_frozen() {
        let state = new_budget_policy_state();
        let evaluator = ErrorBudgetEvaluator::new(state.clone());

        let policies = vec![ErrorBudgetPolicy {
            threshold: 0.95,
            action: BudgetPolicyAction::Freeze,
        }];

        // Trigger freeze: 96% consumed
        let result_high = sample_result(0.04, 10.0);
        evaluator
            .evaluate(
                "payments-slo",
                "payment-service",
                &policies,
                &result_high,
                "30d",
            )
            .await;

        {
            let guard = state.read().await;
            assert!(guard.get("payments-slo").unwrap().is_frozen);
        }

        // Recover: 80% consumed — freeze should clear
        let result_low = sample_result(0.2, 2.0);
        evaluator
            .evaluate(
                "payments-slo",
                "payment-service",
                &policies,
                &result_low,
                "30d",
            )
            .await;

        let guard = state.read().await;
        let status = guard.get("payments-slo").unwrap();
        assert!(!status.is_frozen);
    }

    #[tokio::test]
    async fn test_evaluator_multiple_thresholds() {
        let state = new_budget_policy_state();
        let evaluator = ErrorBudgetEvaluator::new(state.clone());

        let policies = vec![
            ErrorBudgetPolicy {
                threshold: 0.50,
                action: BudgetPolicyAction::Notify,
            },
            ErrorBudgetPolicy {
                threshold: 0.75,
                action: BudgetPolicyAction::Notify,
            },
            ErrorBudgetPolicy {
                threshold: 0.95,
                action: BudgetPolicyAction::Freeze,
            },
        ];

        // 80% consumed — should trigger 0.50 and 0.75 but NOT 0.95
        let result = sample_result(0.2, 4.0);
        evaluator
            .evaluate("payments-slo", "payment-service", &policies, &result, "30d")
            .await;

        let guard = state.read().await;
        let status = guard.get("payments-slo").unwrap();
        assert_eq!(status.triggered_events.len(), 2);
        assert!(!status.is_frozen); // 0.95 not reached
    }

    #[tokio::test]
    async fn test_evaluator_projected_exhaustion_in_event() {
        let state = new_budget_policy_state();
        let evaluator = ErrorBudgetEvaluator::new(state.clone());

        let policies = vec![ErrorBudgetPolicy {
            threshold: 0.5,
            action: BudgetPolicyAction::Notify,
        }];

        // 60% consumed, 40% remaining, 5x burn, 30d window
        // Expected: (0.4 * 2592000) / 5.0 = 207360 secs
        let result = sample_result(0.4, 5.0);
        evaluator
            .evaluate("payments-slo", "payment-service", &policies, &result, "30d")
            .await;

        let guard = state.read().await;
        let status = guard.get("payments-slo").unwrap();
        assert_eq!(status.triggered_events.len(), 1);
        let projected = status.triggered_events[0]
            .projected_exhaustion_secs
            .unwrap();
        assert!((projected - 207360.0).abs() < 1.0);
    }

    #[tokio::test]
    async fn test_new_budget_policy_state_is_empty() {
        let state = new_budget_policy_state();
        let inner = state.read().await;
        assert!(inner.is_empty());
    }

    #[tokio::test]
    async fn test_evaluator_partial_recovery_multi_policy() {
        let state = new_budget_policy_state();
        let evaluator = ErrorBudgetEvaluator::new(state.clone());

        let policies = vec![
            ErrorBudgetPolicy {
                threshold: 0.50,
                action: BudgetPolicyAction::Notify,
            },
            ErrorBudgetPolicy {
                threshold: 0.75,
                action: BudgetPolicyAction::Notify,
            },
            ErrorBudgetPolicy {
                threshold: 0.95,
                action: BudgetPolicyAction::Freeze,
            },
        ];

        // 96% consumed — triggers all three
        let result_high = sample_result(0.04, 10.0);
        evaluator
            .evaluate(
                "payments-slo",
                "payment-service",
                &policies,
                &result_high,
                "30d",
            )
            .await;

        {
            let guard = state.read().await;
            let status = guard.get("payments-slo").unwrap();
            assert_eq!(status.triggered_events.len(), 3);
            assert!(status.is_frozen);
        }

        // 60% consumed — recovers below 0.75 and 0.95, still exceeds 0.50
        let result_mid = sample_result(0.4, 2.0);
        evaluator
            .evaluate(
                "payments-slo",
                "payment-service",
                &policies,
                &result_mid,
                "30d",
            )
            .await;

        let guard = state.read().await;
        let status = guard.get("payments-slo").unwrap();
        assert_eq!(status.triggered_events.len(), 1); // Only 0.50 remains
        assert_eq!(status.triggered_events[0].threshold, 0.5);
        assert!(!status.is_frozen); // Freeze threshold recovered
        assert_eq!(status.triggered_thresholds.len(), 1);
        assert!(status
            .triggered_thresholds
            .contains(&threshold_fingerprint(0.5)));
    }

    #[tokio::test]
    async fn test_evaluator_exact_threshold_triggers() {
        let state = new_budget_policy_state();
        let evaluator = ErrorBudgetEvaluator::new(state.clone());

        let policies = vec![ErrorBudgetPolicy {
            threshold: 0.5,
            action: BudgetPolicyAction::Notify,
        }];

        // Exactly 50% consumed (error_budget_remaining = 0.5)
        let result = sample_result(0.5, 2.0);
        evaluator
            .evaluate("payments-slo", "payment-service", &policies, &result, "30d")
            .await;

        let guard = state.read().await;
        let status = guard.get("payments-slo").unwrap();
        assert_eq!(status.triggered_events.len(), 1); // >= threshold triggers
    }

    // ----- Bounded triggered_events tests (Task 3.3, 3.4) -----

    #[test]
    fn test_triggered_events_bounded_at_max() {
        let mut status = ServiceBudgetStatus::default();

        // Push MAX_TRIGGERED_EVENTS + 50 events
        for i in 0..(MAX_TRIGGERED_EVENTS + 50) {
            status.triggered_events.push(BudgetPolicyEvent {
                service: "test-service".to_string(),
                servicelevel_name: "test-slo".to_string(),
                threshold: 0.5,
                current_consumption: 0.6,
                action: "notify".to_string(),
                burn_rate: 3.0,
                projected_exhaustion_secs: None,
                triggered_at: format!("2026-05-04T{:05}Z", i),
            });

            // Apply the same cap logic as evaluate()
            if status.triggered_events.len() > MAX_TRIGGERED_EVENTS {
                let excess = status.triggered_events.len() - MAX_TRIGGERED_EVENTS;
                status.triggered_events.drain(..excess);
            }
        }

        assert_eq!(
            status.triggered_events.len(),
            MAX_TRIGGERED_EVENTS,
            "triggered_events must be capped at MAX_TRIGGERED_EVENTS"
        );
    }

    #[test]
    fn test_triggered_events_oldest_evicted_first() {
        let mut status = ServiceBudgetStatus::default();

        // Push MAX_TRIGGERED_EVENTS + 10 events with sequenced timestamps
        for i in 0..(MAX_TRIGGERED_EVENTS + 10) {
            status.triggered_events.push(BudgetPolicyEvent {
                service: "test-service".to_string(),
                servicelevel_name: "test-slo".to_string(),
                threshold: 0.5,
                current_consumption: 0.6,
                action: "notify".to_string(),
                burn_rate: 3.0,
                projected_exhaustion_secs: None,
                triggered_at: format!("event-{}", i),
            });

            if status.triggered_events.len() > MAX_TRIGGERED_EVENTS {
                let excess = status.triggered_events.len() - MAX_TRIGGERED_EVENTS;
                status.triggered_events.drain(..excess);
            }
        }

        // Oldest 10 events (event-0 through event-9) should have been evicted
        let first = &status.triggered_events[0];
        assert_eq!(
            first.triggered_at, "event-10",
            "oldest events must be evicted first"
        );

        let last = &status.triggered_events[MAX_TRIGGERED_EVENTS - 1];
        assert_eq!(
            last.triggered_at,
            format!("event-{}", MAX_TRIGGERED_EVENTS + 9),
            "newest events must be preserved"
        );
    }
}
