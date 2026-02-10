//! Investigation controller
//!
//! Watches for Investigation CRDs and reconciles them by spawning
//! investigator pods and tracking their lifecycle.

use std::sync::Arc;
use std::time::Duration;

use futures::StreamExt;
use kube::{
    api::Api,
    runtime::controller::{Action, Controller},
    Client, ResourceExt,
};
use tracing::{error, info, instrument};

use crate::crds::Investigation;

/// Error type for investigation controller operations
#[derive(Debug, thiserror::Error)]
pub enum InvestigationError {
    #[error("Kubernetes API error: {0}")]
    KubeError(#[from] kube::Error),

    #[error("Missing object key: {0}")]
    MissingObjectKey(&'static str),

    #[error("Invalid investigation state: {0}")]
    InvalidState(String),
}

/// Context shared across reconciliation calls
pub struct InvestigationContext {
    pub client: Client,
}

/// Reconcile an Investigation resource
///
/// This function is called whenever an Investigation is created, updated, or deleted.
/// It manages the investigation lifecycle: spawning investigator pods,
/// monitoring their progress, and updating status.
#[instrument(skip(investigation, _ctx), fields(investigation_name = %investigation.name_any(), investigation_namespace = investigation.namespace().unwrap_or_default()))]
async fn reconcile(
    investigation: Arc<Investigation>,
    _ctx: Arc<InvestigationContext>,
) -> Result<Action, InvestigationError> {
    let _name = investigation.name_any();
    let _namespace = investigation.namespace().unwrap_or_default();

    info!(
        condition = %investigation.spec.condition,
        service = %investigation.spec.service,
        severity = ?investigation.spec.severity,
        "Reconciling Investigation"
    );

    // Get current phase or default to Pending
    let phase = investigation
        .status
        .as_ref()
        .and_then(|s| s.phase.clone());

    match phase {
        None => {
            info!("Investigation is new - will transition to Pending");
            // TODO: Update status to Pending in future story
        }
        Some(crate::crds::InvestigationPhase::Pending) => {
            info!("Investigation is Pending - will spawn investigator job");
            // TODO: Spawn investigator Job in Story 1.9
        }
        Some(crate::crds::InvestigationPhase::Running) => {
            info!("Investigation is Running - monitoring job status");
            // TODO: Check Job status and update Investigation status
        }
        Some(crate::crds::InvestigationPhase::Completed) => {
            info!("Investigation is Completed - no action needed");
            // No requeue needed for completed investigations
            return Ok(Action::await_change());
        }
        Some(crate::crds::InvestigationPhase::Failed) => {
            info!("Investigation has Failed - no action needed");
            // No requeue needed for failed investigations
            return Ok(Action::await_change());
        }
    }

    info!(
        "Investigation reconcile stub - job spawning will be implemented in Story 1.9"
    );

    // Requeue after 30 seconds to check status
    Ok(Action::requeue(Duration::from_secs(30)))
}

/// Error policy for handling reconciliation failures
fn error_policy(
    investigation: Arc<Investigation>,
    error: &InvestigationError,
    _ctx: Arc<InvestigationContext>,
) -> Action {
    let name = investigation.name_any();
    error!(
        investigation_name = %name,
        error = %error,
        "Investigation reconciliation failed"
    );

    // Retry after 5 seconds (exponential backoff can be added in future story)
    Action::requeue(Duration::from_secs(5))
}

/// Run the Investigation controller
///
/// This starts watching for Investigation CRDs and reconciling them.
pub async fn run_investigation_controller(client: Client) -> anyhow::Result<()> {
    let investigations: Api<Investigation> = Api::all(client.clone());
    let ctx = Arc::new(InvestigationContext { client });

    info!("Starting Investigation controller");

    Controller::new(investigations, Default::default())
        .run(reconcile, error_policy, ctx)
        .for_each(|res| async move {
            match res {
                Ok(o) => info!(resource = ?o, "Investigation reconciled"),
                Err(e) => error!(error = %e, "Investigation reconciliation error"),
            }
        })
        .await;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_investigation_error_display() {
        let err = InvestigationError::InvalidState("unknown phase".to_string());
        assert_eq!(err.to_string(), "Invalid investigation state: unknown phase");
    }
}
