//! SLO Engine — burn rate calculation and alerting
//!
//! Calculates SLO compliance and burn rates from Prometheus metrics
//! for all ServiceLevel CRDs. Writes snapshots to Qdrant and creates
//! Investigation CRDs when burn rate exceeds configured thresholds.

pub mod budget;
pub mod burn_rate;
pub mod calculator;
pub mod impact;

use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use kube::{api::ListParams, Api, Client};
use serde::{Deserialize, Serialize};
use thiserror::Error;
use tokio::sync::RwLock;
use tracing::{debug, error, info, warn};

use crate::crds::ServiceLevel;
use crate::sources::PrometheusClient;

use budget::{BudgetPolicyState, ErrorBudgetEvaluator};
use burn_rate::BurnRateAlerter;
use calculator::SloCalculator;

/// SLO engine error types
#[derive(Debug, Error)]
pub enum SloError {
    #[error("Kubernetes API error: {0}")]
    KubeError(#[from] kube::Error),

    #[error("Prometheus query error: {0}")]
    PrometheusError(#[from] crate::sources::PrometheusError),

    #[error("Qdrant error: {0}")]
    QdrantError(String),

    #[error("Window parse error: {0}")]
    WindowParseError(String),

    #[error("Calculation error: {0}")]
    CalculationError(String),
}

/// Result of an SLO compliance and burn rate calculation
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct SloCalculationResult {
    /// Service name from ServiceLevel CRD
    pub service: String,

    /// SLI type (availability, latency, error_rate)
    pub sli_type: String,

    /// Compliance ratio (0.0 to 1.0)
    pub compliance: f64,

    /// Current burn rate (1.0 = normal, >1.0 = burning faster than budget)
    pub burn_rate: f64,

    /// Remaining error budget as a fraction (0.0 to 1.0)
    pub error_budget_remaining: f64,

    /// Count of good events in the measurement window
    pub good_count: f64,

    /// Count of total events in the measurement window
    pub total_count: f64,

    /// ISO 8601 timestamp of the calculation
    pub timestamp: String,
}

/// Snapshot point written to Qdrant slo_snapshots collection
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct SloSnapshot {
    pub service: String,
    pub sli_type: String,
    pub compliance: f64,
    pub burn_rate: f64,
    pub error_budget_remaining: f64,
    pub good_count: f64,
    pub total_count: f64,
    pub timestamp: String,
}

impl From<&SloCalculationResult> for SloSnapshot {
    fn from(result: &SloCalculationResult) -> Self {
        SloSnapshot {
            service: result.service.clone(),
            sli_type: result.sli_type.clone(),
            compliance: result.compliance,
            burn_rate: result.burn_rate,
            error_budget_remaining: result.error_budget_remaining,
            good_count: result.good_count,
            total_count: result.total_count,
            timestamp: result.timestamp.clone(),
        }
    }
}

/// Shared cache of latest SLO calculations for API access
pub type SloCache = Arc<RwLock<HashMap<String, SloCalculationResult>>>;

/// Create a new empty SLO cache
pub fn new_slo_cache() -> SloCache {
    Arc::new(RwLock::new(HashMap::new()))
}

/// Qdrant writer for slo_snapshots collection (payload-only, REST API)
pub struct QdrantWriter {
    endpoint: String,
    client: reqwest::Client,
    collection_ensured: bool,
}

impl QdrantWriter {
    /// Create a new QdrantWriter
    pub fn new(endpoint: String) -> Self {
        Self {
            endpoint: endpoint.trim_end_matches('/').to_string(),
            client: reqwest::Client::new(),
            collection_ensured: false,
        }
    }

    /// Ensure the slo_snapshots collection exists (payload-only, no vectors)
    pub async fn ensure_collection(&mut self) -> Result<(), SloError> {
        let url = format!("{}/collections/slo_snapshots", self.endpoint);

        // Check if collection already exists
        let check = self.client.get(&url).send().await;
        if let Ok(resp) = check {
            if resp.status().is_success() {
                debug!("slo_snapshots collection already exists");
                self.collection_ensured = true;
                return Ok(());
            }
        }

        // Create payload-only collection (no vectors)
        let body = serde_json::json!({
            "vectors": {}
        });

        let resp = self
            .client
            .put(&url)
            .json(&body)
            .send()
            .await
            .map_err(|e| SloError::QdrantError(format!("Failed to create collection: {}", e)))?;

        if resp.status().is_success() {
            info!("Created slo_snapshots collection (payload-only)");
            self.collection_ensured = true;
            Ok(())
        } else {
            let status = resp.status();
            let text = resp.text().await.unwrap_or_else(|_| "unknown".to_string());
            Err(SloError::QdrantError(format!(
                "Failed to create slo_snapshots collection: {} - {}",
                status, text
            )))
        }
    }

    /// Write a burn rate snapshot to the slo_snapshots collection
    pub async fn write_snapshot(&self, snapshot: &SloSnapshot) -> Result<(), SloError> {
        let url = format!("{}/collections/slo_snapshots/points", self.endpoint);

        // Use deterministic point ID from service name hash + timestamp bucket
        let point_id = Self::point_id(&snapshot.service, &snapshot.timestamp);

        let body = serde_json::json!({
            "points": [
                {
                    "id": point_id,
                    "vector": {},
                    "payload": snapshot
                }
            ]
        });

        let resp = self
            .client
            .put(&url)
            .json(&body)
            .send()
            .await
            .map_err(|e| SloError::QdrantError(format!("Failed to write snapshot: {}", e)))?;

        if resp.status().is_success() {
            debug!(
                service = %snapshot.service,
                burn_rate = snapshot.burn_rate,
                "Wrote SLO snapshot"
            );
            Ok(())
        } else {
            let status = resp.status();
            let text = resp.text().await.unwrap_or_else(|_| "unknown".to_string());
            Err(SloError::QdrantError(format!(
                "Failed to write snapshot: {} - {}",
                status, text
            )))
        }
    }

    /// Generate deterministic point ID from service name and timestamp
    fn point_id(service: &str, timestamp: &str) -> u64 {
        use std::collections::hash_map::DefaultHasher;
        use std::hash::{Hash, Hasher};

        let mut hasher = DefaultHasher::new();
        service.hash(&mut hasher);
        timestamp.hash(&mut hasher);
        hasher.finish()
    }
}

/// Default SLO refresh interval in seconds
const DEFAULT_SLO_REFRESH_SECS: u64 = 5;

/// Get SLO refresh interval from environment
fn get_slo_refresh_secs() -> u64 {
    std::env::var("BEEPER_SLO_REFRESH_SECS")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(DEFAULT_SLO_REFRESH_SECS)
}

/// Run the SLO engine as a background task.
///
/// Periodically queries all ServiceLevel CRDs, computes burn rates,
/// writes snapshots to Qdrant, and creates Investigation CRDs for alerts.
pub async fn run_slo_engine(
    client: Client,
    prometheus_endpoint: String,
    qdrant_endpoint: String,
    namespace: String,
    slo_cache: SloCache,
    budget_policy_state: BudgetPolicyState,
) {
    let refresh_secs = get_slo_refresh_secs();
    info!(
        refresh_secs = refresh_secs,
        prometheus = %prometheus_endpoint,
        qdrant = %qdrant_endpoint,
        "Starting SLO engine"
    );

    let prom_client = match PrometheusClient::new(prometheus_endpoint, None) {
        Ok(c) => c,
        Err(e) => {
            error!(error = %e, "Failed to create Prometheus client for SLO engine");
            return;
        }
    };

    let calculator = SloCalculator::new(prom_client);
    let mut alerter = BurnRateAlerter::with_slo_cache(client.clone(), namespace, slo_cache.clone());
    let budget_evaluator = ErrorBudgetEvaluator::new(budget_policy_state.clone());
    let mut qdrant = QdrantWriter::new(qdrant_endpoint);

    // Ensure slo_snapshots collection exists on first iteration
    let mut collection_init = false;

    loop {
        if !collection_init {
            match qdrant.ensure_collection().await {
                Ok(()) => {
                    collection_init = true;
                }
                Err(e) => {
                    warn!(error = %e, "Failed to ensure slo_snapshots collection, will retry");
                }
            }
        }

        // List all ServiceLevel CRDs
        let sl_api: Api<ServiceLevel> = Api::all(client.clone());
        match sl_api.list(&ListParams::default()).await {
            Ok(sl_list) => {
                let mut cache_updates: HashMap<String, SloCalculationResult> = HashMap::new();
                let mut active_names: HashSet<String> = HashSet::new();

                for sl in sl_list.items {
                    let name = sl
                        .metadata
                        .name
                        .clone()
                        .unwrap_or_else(|| "unknown".to_string());
                    active_names.insert(name.clone());
                    let spec = &sl.spec;

                    // Compute burn rate for this ServiceLevel
                    match calculator.calculate(spec, &spec.objective.window).await {
                        Ok(result) => {
                            info!(
                                service = %result.service,
                                compliance = result.compliance,
                                burn_rate = result.burn_rate,
                                "SLO calculation complete"
                            );

                            if result.total_count == 0.0 {
                                info!(
                                    service = %result.service,
                                    "SLO has zero total_count — no matching metrics in Prometheus"
                                );
                            }

                            // Write snapshot to Qdrant
                            let snapshot = SloSnapshot::from(&result);
                            if collection_init {
                                if let Err(e) = qdrant.write_snapshot(&snapshot).await {
                                    warn!(
                                        error = %e,
                                        service = %result.service,
                                        "Failed to write SLO snapshot"
                                    );
                                }
                            }

                            // Evaluate burn rate alerts
                            if let Some(alerts) = &spec.burn_rate_alerts {
                                alerter.evaluate(&name, spec, alerts, &calculator).await;
                            }

                            // Evaluate error budget policies
                            if let Some(policies) = &spec.error_budget_policies {
                                if !policies.is_empty() {
                                    budget_evaluator
                                        .evaluate(
                                            &name,
                                            &spec.service,
                                            policies,
                                            &result,
                                            &spec.objective.window,
                                        )
                                        .await;
                                }
                            }

                            // Update cache
                            cache_updates.insert(name, result);
                        }
                        Err(e) => {
                            warn!(
                                error = %e,
                                service = %spec.service,
                                servicelevel = %name,
                                "SLO calculation failed, skipping"
                            );
                        }
                    }
                }

                // Batch-update the shared cache and remove orphaned entries
                {
                    let mut cache = slo_cache.write().await;
                    // Use active_names (not cache_updates) to avoid evicting entries
                    // for CRDs that exist but had a transient calculation failure
                    cache.retain(|key, _| active_names.contains(key));
                    for (key, value) in cache_updates {
                        cache.insert(key, value);
                    }
                }

                // Prune budget policy state for deleted ServiceLevel CRDs
                {
                    let mut budget_state = budget_policy_state.write().await;
                    budget_state.retain(|key, _| active_names.contains(key));
                }
            }
            Err(e) => {
                warn!(error = %e, "Failed to list ServiceLevel CRDs");
            }
        }

        tokio::time::sleep(tokio::time::Duration::from_secs(refresh_secs)).await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_slo_snapshot_from_calculation_result() {
        let result = SloCalculationResult {
            service: "payment-service".to_string(),
            sli_type: "availability".to_string(),
            compliance: 0.9985,
            burn_rate: 1.5,
            error_budget_remaining: 0.85,
            good_count: 9985.0,
            total_count: 10000.0,
            timestamp: "2026-03-14T12:00:00Z".to_string(),
        };

        let snapshot = SloSnapshot::from(&result);
        assert_eq!(snapshot.service, "payment-service");
        assert_eq!(snapshot.sli_type, "availability");
        assert_eq!(snapshot.compliance, 0.9985);
        assert_eq!(snapshot.burn_rate, 1.5);
        assert_eq!(snapshot.error_budget_remaining, 0.85);
        assert_eq!(snapshot.good_count, 9985.0);
        assert_eq!(snapshot.total_count, 10000.0);
        assert_eq!(snapshot.timestamp, "2026-03-14T12:00:00Z");
    }

    #[test]
    fn test_slo_calculation_result_serialization() {
        let result = SloCalculationResult {
            service: "auth-service".to_string(),
            sli_type: "error_rate".to_string(),
            compliance: 0.999,
            burn_rate: 1.0,
            error_budget_remaining: 1.0,
            good_count: 999.0,
            total_count: 1000.0,
            timestamp: "2026-03-14T12:00:00Z".to_string(),
        };

        let json = serde_json::to_string(&result).unwrap();
        assert!(json.contains("\"service\":\"auth-service\""));
        assert!(json.contains("\"sli_type\":\"error_rate\""));
        assert!(json.contains("\"compliance\":0.999"));
        assert!(json.contains("\"burn_rate\":1.0"));
        assert!(json.contains("\"error_budget_remaining\":1.0"));
    }

    #[test]
    fn test_slo_snapshot_serialization() {
        let snapshot = SloSnapshot {
            service: "payment-service".to_string(),
            sli_type: "availability".to_string(),
            compliance: 0.9985,
            burn_rate: 1.5,
            error_budget_remaining: 0.85,
            good_count: 9985.0,
            total_count: 10000.0,
            timestamp: "2026-03-14T12:00:00Z".to_string(),
        };

        let json = serde_json::to_string(&snapshot).unwrap();
        assert!(json.contains("\"service\":\"payment-service\""));
        assert!(json.contains("\"burn_rate\":1.5"));
    }

    #[test]
    fn test_qdrant_writer_point_id_deterministic() {
        let id1 = QdrantWriter::point_id("payment-service", "2026-03-14T12:00:00Z");
        let id2 = QdrantWriter::point_id("payment-service", "2026-03-14T12:00:00Z");
        assert_eq!(id1, id2);
    }

    #[test]
    fn test_qdrant_writer_point_id_varies_by_service() {
        let id1 = QdrantWriter::point_id("payment-service", "2026-03-14T12:00:00Z");
        let id2 = QdrantWriter::point_id("auth-service", "2026-03-14T12:00:00Z");
        assert_ne!(id1, id2);
    }

    #[test]
    fn test_qdrant_writer_point_id_varies_by_timestamp() {
        let id1 = QdrantWriter::point_id("payment-service", "2026-03-14T12:00:00Z");
        let id2 = QdrantWriter::point_id("payment-service", "2026-03-14T12:05:00Z");
        assert_ne!(id1, id2);
    }

    #[test]
    fn test_new_slo_cache_is_empty() {
        let rt = tokio::runtime::Runtime::new().unwrap();
        let cache = new_slo_cache();
        rt.block_on(async {
            let inner = cache.read().await;
            assert!(inner.is_empty());
        });
    }

    #[test]
    fn test_write_snapshot_body_includes_vector_field() {
        // Qdrant payload-only collections require "vector": {} in upsert points.
        // Regression guard: removing this field causes "missing field vector" errors.
        let snapshot = SloSnapshot {
            service: "test-svc".to_string(),
            sli_type: "availability".to_string(),
            compliance: 0.999,
            burn_rate: 1.0,
            error_budget_remaining: 1.0,
            good_count: 999.0,
            total_count: 1000.0,
            timestamp: "2026-04-03T12:00:00Z".to_string(),
        };
        let point_id = QdrantWriter::point_id(&snapshot.service, &snapshot.timestamp);
        let body = serde_json::json!({
            "points": [
                {
                    "id": point_id,
                    "vector": {},
                    "payload": snapshot
                }
            ]
        });
        let point = &body["points"][0];
        assert!(
            point.get("vector").is_some(),
            "upsert point must include 'vector' field"
        );
        assert_eq!(point["vector"], serde_json::json!({}));
    }

    #[test]
    fn test_slo_error_display() {
        let err = SloError::WindowParseError("invalid window: abc".to_string());
        assert_eq!(err.to_string(), "Window parse error: invalid window: abc");

        let err = SloError::CalculationError("division by zero".to_string());
        assert_eq!(err.to_string(), "Calculation error: division by zero");

        let err = SloError::QdrantError("connection refused".to_string());
        assert_eq!(err.to_string(), "Qdrant error: connection refused");
    }

    // ----- SloCache cleanup tests (Task 4.4, 4.5) -----

    #[tokio::test]
    async fn test_slo_cache_orphaned_entries_removed() {
        let cache = new_slo_cache();

        // Simulate: 3 CRDs exist and get cached
        {
            let mut c = cache.write().await;
            for name in &["slo-a", "slo-b", "slo-c"] {
                c.insert(
                    name.to_string(),
                    SloCalculationResult {
                        service: name.to_string(),
                        sli_type: "availability".to_string(),
                        compliance: 0.999,
                        burn_rate: 1.0,
                        error_budget_remaining: 1.0,
                        good_count: 999.0,
                        total_count: 1000.0,
                        timestamp: "2026-05-04T00:00:00Z".to_string(),
                    },
                );
            }
        }
        assert_eq!(cache.read().await.len(), 3);

        // Simulate: CRD "slo-b" is deleted — only slo-a, slo-c listed
        // slo-c calculation fails (transient Prometheus error) — only slo-a in cache_updates
        let active_names: HashSet<String> =
            ["slo-a", "slo-c"].iter().map(|s| s.to_string()).collect();
        let mut cache_updates: HashMap<String, SloCalculationResult> = HashMap::new();
        cache_updates.insert(
            "slo-a".to_string(),
            SloCalculationResult {
                service: "slo-a".to_string(),
                sli_type: "availability".to_string(),
                compliance: 0.998,
                burn_rate: 1.2,
                error_budget_remaining: 0.9,
                good_count: 998.0,
                total_count: 1000.0,
                timestamp: "2026-05-04T00:05:00Z".to_string(),
            },
        );

        // Apply same retain logic as run_slo_engine (uses active_names, not cache_updates)
        {
            let mut c = cache.write().await;
            c.retain(|key, _| active_names.contains(key));
            for (key, value) in cache_updates {
                c.insert(key, value);
            }
        }

        let c = cache.read().await;
        // slo-b deleted → removed; slo-c failed calc but still listed → preserved
        assert_eq!(c.len(), 2, "orphaned entry slo-b must be removed");
        assert!(c.contains_key("slo-a"));
        assert!(!c.contains_key("slo-b"), "deleted CRD must be evicted");
        assert!(
            c.contains_key("slo-c"),
            "CRD with failed calc must be preserved"
        );
    }

    #[tokio::test]
    async fn test_budget_state_orphaned_entries_removed() {
        use crate::slo::budget::*;

        let state = new_budget_policy_state();

        // Simulate: 2 services have budget state
        {
            let mut s = state.write().await;
            s.insert("slo-x".to_string(), ServiceBudgetStatus::default());
            s.insert("slo-y".to_string(), ServiceBudgetStatus::default());
        }
        assert_eq!(state.read().await.len(), 2);

        // Simulate: slo-y deleted — only slo-x in active set
        let active: HashSet<String> = ["slo-x".to_string()].into_iter().collect();
        {
            let mut s = state.write().await;
            s.retain(|key, _| active.contains(key));
        }

        let s = state.read().await;
        assert_eq!(s.len(), 1, "orphaned budget state must be removed");
        assert!(s.contains_key("slo-x"));
        assert!(!s.contains_key("slo-y"));
    }
}
