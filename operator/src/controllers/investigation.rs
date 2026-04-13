//! Investigation controller
//!
//! Watches for Investigation CRDs and reconciles them by spawning
//! investigator pods and tracking their lifecycle.

use std::sync::Arc;
use std::time::Duration;

use futures::StreamExt;
use k8s_openapi::api::batch::v1::Job;
use kube::{
    api::Api,
    runtime::controller::{Action, Controller},
    Client, ResourceExt,
};
use tracing::{debug, error, info, instrument, warn};

use crate::crds::{Investigation, InvestigationPhase};
use crate::investigator_job::{
    build_investigator_job, get_job_failure_message, is_job_completed, is_job_failed,
    set_phase_completed, set_phase_failed, set_phase_pending, set_phase_running,
    InvestigatorConfig,
};

/// Error type for investigation controller operations
#[derive(Debug, thiserror::Error)]
pub enum InvestigationError {
    #[error("Kubernetes API error: {0}")]
    KubeError(#[from] kube::Error),

    #[error("Missing object key: {0}")]
    MissingObjectKey(&'static str),

    #[error("Invalid investigation state: {0}")]
    InvalidState(String),

    #[error("Job build error: {0}")]
    JobBuildError(#[from] crate::investigator_job::InvestigatorJobError),
}

/// Context shared across reconciliation calls
pub struct InvestigationContext {
    pub client: Client,
    pub config: InvestigatorConfig,
}

/// Reconcile an Investigation resource
///
/// This function is called whenever an Investigation is created, updated, or deleted.
/// It manages the investigation lifecycle: spawning investigator pods,
/// monitoring their progress, and updating status.
#[instrument(skip(investigation, ctx), fields(investigation_name = %investigation.name_any(), investigation_namespace = investigation.namespace().unwrap_or_default()))]
async fn reconcile(
    investigation: Arc<Investigation>,
    ctx: Arc<InvestigationContext>,
) -> Result<Action, InvestigationError> {
    let name = investigation.name_any();
    let namespace = investigation.namespace().unwrap_or_default();

    info!(
        condition = %investigation.spec.condition,
        service = %investigation.spec.service,
        severity = ?investigation.spec.severity,
        "Reconciling Investigation"
    );

    // Get current phase or default to None (new investigation)
    let phase = investigation.status.as_ref().and_then(|s| s.phase.clone());

    match phase {
        None => {
            // New investigation - set phase to Pending
            info!("Investigation is new - transitioning to Pending");
            set_phase_pending(&ctx.client, &investigation).await?;
            // Requeue immediately to process Pending phase
            return Ok(Action::requeue(Duration::from_secs(1)));
        }

        Some(InvestigationPhase::Pending) => {
            info!("Investigation is Pending - spawning investigator Job");

            // Build the investigator Job
            let job = build_investigator_job(&investigation, &ctx.config)?;
            let job_name = job.metadata.name.clone().unwrap_or_default();

            // Create the Job
            let jobs_api: Api<Job> = Api::namespaced(ctx.client.clone(), &namespace);

            // Check if Job already exists
            match jobs_api.get(&job_name).await {
                Ok(_existing_job) => {
                    // Job exists - transition to Running
                    info!(job_name = %job_name, "Job already exists - transitioning to Running");
                    set_phase_running(&ctx.client, &investigation, &job_name).await?;
                }
                Err(kube::Error::Api(err)) if err.code == 404 => {
                    // Job doesn't exist - create it
                    info!(job_name = %job_name, "Creating investigator Job");
                    jobs_api.create(&Default::default(), &job).await?;
                    set_phase_running(&ctx.client, &investigation, &job_name).await?;
                }
                Err(e) => {
                    error!(error = %e, "Failed to check for existing Job");
                    return Err(InvestigationError::KubeError(e));
                }
            }

            // Requeue to monitor Job status
            return Ok(Action::requeue(Duration::from_secs(10)));
        }

        Some(InvestigationPhase::Running) => {
            info!("Investigation is Running - checking Job status");

            // Get the Job name from status
            let job_name = investigation
                .status
                .as_ref()
                .and_then(|s| s.job_name.clone())
                .unwrap_or_else(|| format!("inv-{}", name));

            // Check Job status
            let jobs_api: Api<Job> = Api::namespaced(ctx.client.clone(), &namespace);

            match jobs_api.get(&job_name).await {
                Ok(job) => {
                    if is_job_completed(&job) {
                        info!(job_name = %job_name, "Job completed successfully - transitioning to Completed");
                        set_phase_completed(&ctx.client, &investigation).await?;
                        return Ok(Action::await_change());
                    } else if is_job_failed(&job) {
                        let error_msg = get_job_failure_message(&job).unwrap_or_else(|| {
                            "Job failed without specific error message".to_string()
                        });
                        warn!(job_name = %job_name, error = %error_msg, "Job failed - transitioning to Failed");
                        set_phase_failed(&ctx.client, &investigation, &error_msg).await?;
                        return Ok(Action::await_change());
                    } else {
                        // Job still running - requeue to check again
                        debug!(job_name = %job_name, "Job still running - requeuing");
                        return Ok(Action::requeue(Duration::from_secs(10)));
                    }
                }
                Err(kube::Error::Api(err)) if err.code == 404 => {
                    // Job was deleted - mark as failed
                    warn!(job_name = %job_name, "Job not found - marking investigation as Failed");
                    set_phase_failed(
                        &ctx.client,
                        &investigation,
                        "Investigator Job was deleted unexpectedly",
                    )
                    .await?;
                    return Ok(Action::await_change());
                }
                Err(e) => {
                    error!(error = %e, "Failed to get Job status");
                    return Err(InvestigationError::KubeError(e));
                }
            }
        }

        Some(InvestigationPhase::AwaitingConfirmation) => {
            info!("Investigation is AwaitingConfirmation - waiting for human confirmation");
            // Requeue to check if confirmation has been provided
            return Ok(Action::requeue(Duration::from_secs(10)));
        }

        Some(InvestigationPhase::Completed) => {
            info!("Investigation is Completed - no action needed");
            // No requeue needed for completed investigations
            return Ok(Action::await_change());
        }

        Some(InvestigationPhase::Failed) => {
            info!("Investigation has Failed - no action needed");
            // No requeue needed for failed investigations
            return Ok(Action::await_change());
        }
    }
}

/// Base delay for exponential backoff on reconciliation errors
const BACKOFF_BASE_SECS: u64 = 5;

/// Maximum delay cap for exponential backoff
const BACKOFF_MAX_SECS: u64 = 60;

/// Compute exponential backoff duration with jitter for a given attempt.
///
/// Formula: min(base * 2^attempt, max) ± 25% jitter.
/// Attempt 0 gives ~5s, attempt 1 gives ~10s, attempt 2 gives ~20s, etc.
pub fn backoff_duration(attempt: u32) -> Duration {
    let delay = std::cmp::min(
        BACKOFF_BASE_SECS.saturating_mul(1u64.wrapping_shl(attempt)),
        BACKOFF_MAX_SECS,
    );
    // Deterministic jitter: use attempt as seed for ±25% variation.
    // Avoids adding rand crate. Note: all operator instances with the same
    // attempt count get the same delay — provides varied spacing per attempt,
    // not true anti-thundering-herd randomization (acceptable for single-operator).
    let jitter_factor = match attempt % 4 {
        0 => 100u64, // +0%
        1 => 125u64, // +25%
        2 => 75u64,  // -25%
        _ => 110u64, // +10%
    };
    let jittered = delay.saturating_mul(jitter_factor) / 100;
    Duration::from_secs(std::cmp::max(1, jittered))
}

/// Error policy for handling reconciliation failures with exponential backoff.
///
/// Uses exponential backoff with jitter to avoid thundering herd on repeated
/// reconciliation failures. Attempt count is derived from the investigation's
/// status.message retry prefix when available.
fn error_policy(
    investigation: Arc<Investigation>,
    error: &InvestigationError,
    _ctx: Arc<InvestigationContext>,
) -> Action {
    let name = investigation.name_any();

    // Extract retry count from status message if available (format: "[retry:N] ...")
    let attempt = investigation
        .status
        .as_ref()
        .and_then(|s| s.message.as_ref())
        .and_then(|msg| {
            msg.strip_prefix("[retry:")
                .and_then(|rest| rest.split(']').next())
                .and_then(|n| n.parse::<u32>().ok())
        })
        .unwrap_or(0);

    let delay = backoff_duration(attempt);
    error!(
        investigation_name = %name,
        error = %error,
        attempt = attempt,
        retry_delay_secs = delay.as_secs(),
        "Investigation reconciliation failed — retrying with backoff"
    );

    Action::requeue(delay)
}

/// Run the Investigation controller
///
/// This starts watching for Investigation CRDs and reconciling them.
pub async fn run_investigation_controller(client: Client) -> anyhow::Result<()> {
    run_investigation_controller_with_config(client, InvestigatorConfig::default()).await
}

/// Run the Investigation controller with custom configuration
///
/// This starts watching for Investigation CRDs and reconciling them
/// with the provided investigator configuration.
pub async fn run_investigation_controller_with_config(
    client: Client,
    config: InvestigatorConfig,
) -> anyhow::Result<()> {
    let investigations: Api<Investigation> = Api::all(client.clone());
    let jobs: Api<Job> = Api::all(client.clone());

    let ctx = Arc::new(InvestigationContext { client, config });

    info!("Starting Investigation controller");

    // Watch both Investigations and Jobs (for status updates)
    Controller::new(investigations, Default::default())
        .owns(jobs, Default::default())
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
        assert_eq!(
            err.to_string(),
            "Invalid investigation state: unknown phase"
        );
    }

    #[test]
    fn test_investigation_error_kube() {
        // Test that kube errors can be converted
        let kube_err = kube::Error::Service(Box::new(std::io::Error::new(
            std::io::ErrorKind::Other,
            "test error",
        )));
        let err: InvestigationError = kube_err.into();
        assert!(err.to_string().contains("Kubernetes API error"));
    }

    #[test]
    fn test_investigation_error_missing_key() {
        let err = InvestigationError::MissingObjectKey("test_key");
        assert_eq!(err.to_string(), "Missing object key: test_key");
    }

    #[test]
    fn test_backoff_duration_first_attempt() {
        let d = backoff_duration(0);
        // attempt 0: base=5, jitter_factor=100 → 5s
        assert_eq!(d.as_secs(), 5);
    }

    #[test]
    fn test_backoff_duration_second_attempt() {
        let d = backoff_duration(1);
        // attempt 1: base=5*2=10, jitter_factor=125 → 12s
        assert_eq!(d.as_secs(), 12);
    }

    #[test]
    fn test_backoff_duration_third_attempt() {
        let d = backoff_duration(2);
        // attempt 2: base=5*4=20, jitter_factor=75 → 15s
        assert_eq!(d.as_secs(), 15);
    }

    #[test]
    fn test_backoff_duration_capped_at_max() {
        let d = backoff_duration(10);
        // attempt 10: base would be 5*1024=5120, capped at 60, jitter_factor=75 → 45s
        assert!(d.as_secs() <= BACKOFF_MAX_SECS * 125 / 100);
    }

    #[test]
    fn test_backoff_duration_never_zero() {
        for attempt in 0..20 {
            let d = backoff_duration(attempt);
            assert!(
                d.as_secs() >= 1,
                "Duration must be at least 1 second, got {} for attempt {}",
                d.as_secs(),
                attempt
            );
        }
    }
}
