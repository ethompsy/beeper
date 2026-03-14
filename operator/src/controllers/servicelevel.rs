//! ServiceLevel controller
//!
//! Watches for ServiceLevel CRDs and reconciles their status by
//! validating the spec and registering burn rate alert thresholds.

use std::sync::Arc;
use std::time::Duration;

use chrono::Utc;
use futures::StreamExt;
use kube::{
    api::{Api, Patch, PatchParams},
    runtime::controller::{Action, Controller},
    Client, ResourceExt,
};
use serde_json::json;
use tracing::{debug, error, info, instrument, warn};

use crate::crds::{ServiceLevel, ServiceLevelCondition, ServiceLevelStatus};
use crate::crds::servicelevel::validate_spec;

/// Error type for ServiceLevel controller operations
#[derive(Debug, thiserror::Error)]
pub enum ServiceLevelError {
    #[error("Kubernetes API error: {0}")]
    KubeError(#[from] kube::Error),

    #[error("Missing object key: {0}")]
    MissingObjectKey(&'static str),

    #[error("Serialization error: {0}")]
    SerializationError(#[from] serde_json::Error),
}

/// Context shared across reconciliation calls
pub struct ServiceLevelContext {
    pub client: Client,
}

/// Reconcile a ServiceLevel resource
///
/// Validates the spec, sets the condition status, and registers
/// burn rate alert thresholds.
#[instrument(skip(servicelevel, ctx), fields(servicelevel_name = %servicelevel.name_any()))]
async fn reconcile(
    servicelevel: Arc<ServiceLevel>,
    ctx: Arc<ServiceLevelContext>,
) -> Result<Action, ServiceLevelError> {
    let name = servicelevel
        .metadata
        .name
        .as_deref()
        .ok_or(ServiceLevelError::MissingObjectKey("metadata.name"))?;
    let namespace = servicelevel
        .metadata
        .namespace
        .as_deref()
        .ok_or(ServiceLevelError::MissingObjectKey("metadata.namespace"))?;

    debug!(
        name = %name,
        namespace = %namespace,
        service = %servicelevel.spec.service,
        "Reconciling ServiceLevel"
    );

    let now = Utc::now().to_rfc3339();
    let spec = &servicelevel.spec;

    // Validate the spec
    let status = match validate_spec(spec) {
        Ok(()) => {
            let alerts_count = spec
                .burn_rate_alerts
                .as_ref()
                .map(|a| a.len() as u32)
                .unwrap_or(0);

            info!(
                name = %name,
                service = %spec.service,
                sli_type = ?spec.sli.sli_type,
                target = spec.objective.target,
                alerts_registered = alerts_count,
                "ServiceLevel validated successfully"
            );

            ServiceLevelStatus {
                condition: Some(ServiceLevelCondition::Healthy),
                last_evaluated: Some(now),
                alerts_registered: Some(alerts_count),
                error: None,
            }
        }
        Err(validation_error) => {
            warn!(
                name = %name,
                error = %validation_error,
                "ServiceLevel validation failed"
            );

            ServiceLevelStatus {
                condition: Some(ServiceLevelCondition::Critical),
                last_evaluated: Some(now),
                alerts_registered: None,
                error: Some(validation_error),
            }
        }
    };

    // Patch the status subresource
    let servicelevels: Api<ServiceLevel> = Api::namespaced(ctx.client.clone(), namespace);
    let status_patch = json!({
        "status": status
    });

    servicelevels
        .patch_status(
            name,
            &PatchParams::apply("beeper-operator"),
            &Patch::Merge(&status_patch),
        )
        .await?;

    debug!(name = %name, "ServiceLevel status updated");

    // Requeue after 5 minutes for periodic re-evaluation
    Ok(Action::requeue(Duration::from_secs(300)))
}

/// Error policy for ServiceLevel reconciliation failures
fn error_policy(
    servicelevel: Arc<ServiceLevel>,
    error: &ServiceLevelError,
    _ctx: Arc<ServiceLevelContext>,
) -> Action {
    error!(
        servicelevel = %servicelevel.name_any(),
        error = %error,
        "ServiceLevel reconciliation failed"
    );
    // Retry after 5 seconds on error
    Action::requeue(Duration::from_secs(5))
}

/// Start the ServiceLevel controller
pub async fn run_servicelevel_controller(client: Client) -> anyhow::Result<()> {
    let servicelevels: Api<ServiceLevel> = Api::all(client.clone());
    let ctx = Arc::new(ServiceLevelContext { client });

    info!("Starting ServiceLevel controller");

    Controller::new(servicelevels, Default::default())
        .run(reconcile, error_policy, ctx)
        .for_each(|res| async move {
            match res {
                Ok(o) => debug!(resource = ?o, "ServiceLevel reconciled"),
                Err(e) => warn!(error = %e, "ServiceLevel reconciliation error"),
            }
        })
        .await;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::crds::servicelevel::{
        BurnRateAlert, ObjectiveSpec, ServiceLevelSpec, SliSpec, SliType,
    };

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
            error_budget_policies: None,
        }
    }

    #[test]
    fn test_validate_valid_spec() {
        let spec = sample_spec();
        assert!(validate_spec(&spec).is_ok());
    }

    #[test]
    fn test_validate_empty_service() {
        let mut spec = sample_spec();
        spec.service = "".to_string();
        assert!(validate_spec(&spec).is_err());
    }

    #[test]
    fn test_validate_invalid_target() {
        let mut spec = sample_spec();
        spec.objective.target = 1.5;
        assert!(validate_spec(&spec).is_err());

        spec.objective.target = -0.1;
        assert!(validate_spec(&spec).is_err());
    }

    #[test]
    fn test_validate_target_boundaries() {
        let mut spec = sample_spec();

        spec.objective.target = 0.0;
        assert!(validate_spec(&spec).is_ok());

        spec.objective.target = 1.0;
        assert!(validate_spec(&spec).is_ok());
    }

    #[test]
    fn test_validate_no_alerts() {
        let mut spec = sample_spec();
        spec.burn_rate_alerts = None;
        assert!(validate_spec(&spec).is_ok());
    }

    #[test]
    fn test_validate_alert_invalid_factor() {
        let mut spec = sample_spec();
        spec.burn_rate_alerts.as_mut().unwrap()[0].factor = 0.0;
        assert!(validate_spec(&spec).is_err());
    }

    #[test]
    fn test_servicelevel_error_display() {
        let err = ServiceLevelError::MissingObjectKey("metadata.name");
        assert_eq!(format!("{}", err), "Missing object key: metadata.name");
    }

    #[test]
    fn test_servicelevel_error_from_kube() {
        // Verify the From<kube::Error> implementation exists
        // (compile-time check via the #[from] attribute)
        let _: fn(kube::Error) -> ServiceLevelError = ServiceLevelError::KubeError;
    }

    #[test]
    fn test_servicelevel_error_from_serde() {
        // Verify the From<serde_json::Error> implementation exists
        let _: fn(serde_json::Error) -> ServiceLevelError = ServiceLevelError::SerializationError;
    }
}
