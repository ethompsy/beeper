//! Repository controller
//!
//! Watches for Repository CRDs and reconciles their status by
//! validating the spec and checking that the referenced credentials Secret exists.
//! Each Repository is independently managed — failures are isolated.

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

use crate::crds::repository::validate_spec;
use crate::crds::{Repository, RepositoryCondition, RepositoryStatus};

/// Error type for Repository controller operations
#[derive(Debug, thiserror::Error)]
pub enum RepositoryError {
    #[error("Kubernetes API error: {0}")]
    KubeError(#[from] kube::Error),

    #[error("Missing object key: {0}")]
    MissingObjectKey(&'static str),

    #[error("Serialization error: {0}")]
    SerializationError(#[from] serde_json::Error),

    #[error("Validation error: {0}")]
    ValidationError(String),

    #[error("Secret not found: {0}")]
    SecretNotFound(String),
}

/// Context shared across reconciliation calls
pub struct RepositoryContext {
    pub client: Client,
}

/// Reconcile a Repository resource
///
/// Validates the spec, checks that credentials_secret exists,
/// and reports repository status (connected/auth_error/not_found/error).
#[instrument(skip(repo, ctx), fields(repository_name = %repo.name_any()))]
async fn reconcile(
    repo: Arc<Repository>,
    ctx: Arc<RepositoryContext>,
) -> Result<Action, RepositoryError> {
    let name = repo
        .metadata
        .name
        .as_deref()
        .ok_or(RepositoryError::MissingObjectKey("metadata.name"))?;
    let namespace = repo
        .metadata
        .namespace
        .as_deref()
        .ok_or(RepositoryError::MissingObjectKey("metadata.namespace"))?;

    debug!(
        name = %name,
        namespace = %namespace,
        provider = ?repo.spec.provider,
        "Reconciling Repository"
    );

    let now = Utc::now().to_rfc3339();
    let spec = &repo.spec;

    // Step 1: Validate the spec
    if let Err(validation_error) = validate_spec(spec) {
        warn!(
            name = %name,
            error = %validation_error,
            "Repository validation failed"
        );

        let status = RepositoryStatus {
            condition: Some(RepositoryCondition::Error),
            last_checked: Some(now),
            error: Some(validation_error),
            ..Default::default()
        };

        patch_status(&ctx.client, namespace, name, &status).await?;
        return Ok(Action::requeue(Duration::from_secs(300)));
    }

    // Step 2: Check that the referenced Secret exists
    let secrets: Api<k8s_openapi::api::core::v1::Secret> =
        Api::namespaced(ctx.client.clone(), namespace);

    match secrets.get(&spec.credentials_secret).await {
        Ok(_) => {
            info!(
                name = %name,
                provider = ?spec.provider,
                credentials_secret = %spec.credentials_secret,
                "Repository validated successfully — credentials secret found"
            );

            let status = RepositoryStatus {
                condition: Some(RepositoryCondition::Connected),
                last_checked: Some(now),
                error: None,
                default_branch_detected: None,
            };

            patch_status(&ctx.client, namespace, name, &status).await?;
        }
        Err(kube::Error::Api(err_resp)) if err_resp.code == 404 => {
            warn!(
                name = %name,
                secret = %spec.credentials_secret,
                "Repository credentials Secret not found"
            );

            let status = RepositoryStatus {
                condition: Some(RepositoryCondition::AuthError),
                last_checked: Some(now),
                error: Some(format!(
                    "credentials_secret '{}' not found in namespace '{}'",
                    spec.credentials_secret, namespace
                )),
                default_branch_detected: None,
            };

            patch_status(&ctx.client, namespace, name, &status).await?;
        }
        Err(e) => {
            warn!(
                name = %name,
                error = %e,
                "Failed to check credentials Secret"
            );

            let status = RepositoryStatus {
                condition: Some(RepositoryCondition::Error),
                last_checked: Some(now),
                error: Some(format!("Failed to verify credentials_secret: {}", e)),
                default_branch_detected: None,
            };

            patch_status(&ctx.client, namespace, name, &status).await?;
        }
    }

    // Requeue after 5 minutes for periodic re-evaluation
    Ok(Action::requeue(Duration::from_secs(300)))
}

/// Patch the status subresource of a Repository
async fn patch_status(
    client: &Client,
    namespace: &str,
    name: &str,
    status: &RepositoryStatus,
) -> Result<(), RepositoryError> {
    let repos: Api<Repository> = Api::namespaced(client.clone(), namespace);
    let status_patch = json!({
        "status": status
    });

    repos
        .patch_status(
            name,
            &PatchParams::apply("beeper-operator"),
            &Patch::Merge(&status_patch),
        )
        .await?;

    debug!(name = %name, "Repository status updated");
    Ok(())
}

/// Compute exponential backoff duration for error retries
fn backoff_duration(attempt: u32) -> Duration {
    let base_secs: u64 = 5;
    let max_secs: u64 = 60;
    let delay = std::cmp::min(base_secs.saturating_mul(1u64 << attempt), max_secs);

    // Deterministic jitter (±25%) using attempt number
    let jitter_factor = match attempt % 4 {
        0 => 100,
        1 => 85,
        2 => 115,
        3 => 90,
        _ => 100,
    };
    let jittered = (delay * jitter_factor) / 100;

    Duration::from_secs(std::cmp::max(jittered, 1))
}

/// Error policy for Repository reconciliation failures
fn error_policy(
    repo: Arc<Repository>,
    error: &RepositoryError,
    _ctx: Arc<RepositoryContext>,
) -> Action {
    error!(
        repository = %repo.name_any(),
        error = %error,
        "Repository reconciliation failed"
    );
    // Exponential backoff: base 5s, factor 2x, max 60s, with jitter
    Action::requeue(backoff_duration(1))
}

/// Start the Repository controller
pub async fn run_repository_controller(client: Client) -> anyhow::Result<()> {
    let repos: Api<Repository> = Api::all(client.clone());
    let ctx = Arc::new(RepositoryContext { client });

    info!("Starting Repository controller");

    Controller::new(repos, Default::default())
        .run(reconcile, error_policy, ctx)
        .for_each(|res| async move {
            match res {
                Ok(o) => debug!(resource = ?o, "Repository reconciled"),
                Err(e) => warn!(error = %e, "Repository reconciliation error"),
            }
        })
        .await;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_repository_error_display_missing_key() {
        let err = RepositoryError::MissingObjectKey("metadata.name");
        assert_eq!(format!("{}", err), "Missing object key: metadata.name");
    }

    #[test]
    fn test_repository_error_display_missing_namespace() {
        let err = RepositoryError::MissingObjectKey("metadata.namespace");
        assert_eq!(format!("{}", err), "Missing object key: metadata.namespace");
    }

    #[test]
    fn test_repository_error_from_kube() {
        // Verify the From<kube::Error> impl compiles
        let _: fn(kube::Error) -> RepositoryError = RepositoryError::KubeError;
    }

    #[test]
    fn test_repository_error_from_serde() {
        // Verify the From<serde_json::Error> impl compiles
        let _: fn(serde_json::Error) -> RepositoryError = RepositoryError::SerializationError;
    }

    #[test]
    fn test_repository_error_display_validation() {
        let err = RepositoryError::ValidationError("url is invalid".to_string());
        assert_eq!(format!("{}", err), "Validation error: url is invalid");
    }

    #[test]
    fn test_repository_error_display_secret_not_found() {
        let err = RepositoryError::SecretNotFound("my-secret".to_string());
        assert_eq!(format!("{}", err), "Secret not found: my-secret");
    }

    #[test]
    fn test_backoff_duration_first_attempt() {
        let d = backoff_duration(0);
        // base 5s, attempt 0 => 5 * 2^0 = 5, jitter factor 100% => 5s
        assert_eq!(d.as_secs(), 5);
    }

    #[test]
    fn test_backoff_duration_second_attempt() {
        let d = backoff_duration(1);
        // base 5s, attempt 1 => 5 * 2^1 = 10, jitter factor 85% => 8s
        assert_eq!(d.as_secs(), 8);
    }

    #[test]
    fn test_backoff_duration_third_attempt() {
        let d = backoff_duration(2);
        // base 5s, attempt 2 => 5 * 2^2 = 20, jitter factor 115% => 23s
        assert_eq!(d.as_secs(), 23);
    }

    #[test]
    fn test_backoff_duration_capped_at_max() {
        let d = backoff_duration(10);
        // 5 * 2^10 = 5120, capped at 60, jitter factor 115% => 69
        assert!(d.as_secs() <= 69);
        assert!(d.as_secs() >= 51); // 60 * 85% = 51
    }

    #[test]
    fn test_backoff_duration_never_zero() {
        for attempt in 0..20 {
            let d = backoff_duration(attempt);
            assert!(d.as_secs() >= 1, "backoff at attempt {} was 0", attempt);
        }
    }
}
