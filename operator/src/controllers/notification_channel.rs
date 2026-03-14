//! NotificationChannel controller
//!
//! Watches for NotificationChannel CRDs and reconciles their status by
//! validating the spec and checking that the referenced credentials Secret exists.

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
use tracing::{debug, error, info, warn};

use crate::crds::{
    NotificationChannel, NotificationChannelCondition, NotificationChannelStatus,
};
use crate::crds::notification_channel::validate_spec;

/// Error type for NotificationChannel controller operations
#[derive(Debug, thiserror::Error)]
pub enum NotificationChannelError {
    #[error("Kubernetes API error: {0}")]
    KubeError(#[from] kube::Error),

    #[error("Missing object key: {0}")]
    MissingObjectKey(&'static str),

    #[error("Serialization error: {0}")]
    SerializationError(#[from] serde_json::Error),
}

/// Context shared across reconciliation calls
pub struct NotificationChannelContext {
    pub client: Client,
}

/// Reconcile a NotificationChannel resource
///
/// Validates the spec, checks that credentials_secret exists,
/// and reports channel status (configured/error).
async fn reconcile(
    channel: Arc<NotificationChannel>,
    ctx: Arc<NotificationChannelContext>,
) -> Result<Action, NotificationChannelError> {
    let name = channel
        .metadata
        .name
        .as_deref()
        .ok_or(NotificationChannelError::MissingObjectKey("metadata.name"))?;
    let namespace = channel
        .metadata
        .namespace
        .as_deref()
        .ok_or(NotificationChannelError::MissingObjectKey(
            "metadata.namespace",
        ))?;

    debug!(
        name = %name,
        namespace = %namespace,
        channel_type = ?channel.spec.channel_type,
        "Reconciling NotificationChannel"
    );

    let now = Utc::now().to_rfc3339();
    let spec = &channel.spec;

    // Step 1: Validate the spec
    if let Err(validation_error) = validate_spec(spec) {
        warn!(
            name = %name,
            error = %validation_error,
            "NotificationChannel validation failed"
        );

        let status = NotificationChannelStatus {
            condition: Some(NotificationChannelCondition::Error),
            last_validated: Some(now),
            error: Some(validation_error),
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
                channel_type = ?spec.channel_type,
                credentials_secret = %spec.credentials_secret,
                "NotificationChannel validated successfully"
            );

            let status = NotificationChannelStatus {
                condition: Some(NotificationChannelCondition::Configured),
                last_validated: Some(now),
                error: None,
            };

            patch_status(&ctx.client, namespace, name, &status).await?;
        }
        Err(kube::Error::Api(err_resp)) if err_resp.code == 404 => {
            warn!(
                name = %name,
                secret = %spec.credentials_secret,
                "NotificationChannel credentials Secret not found"
            );

            let status = NotificationChannelStatus {
                condition: Some(NotificationChannelCondition::Error),
                last_validated: Some(now),
                error: Some(format!(
                    "credentials_secret '{}' not found in namespace '{}'",
                    spec.credentials_secret, namespace
                )),
            };

            patch_status(&ctx.client, namespace, name, &status).await?;
        }
        Err(e) => {
            warn!(
                name = %name,
                error = %e,
                "Failed to check credentials Secret"
            );

            let status = NotificationChannelStatus {
                condition: Some(NotificationChannelCondition::Error),
                last_validated: Some(now),
                error: Some(format!("Failed to verify credentials_secret: {}", e)),
            };

            patch_status(&ctx.client, namespace, name, &status).await?;
        }
    }

    // Requeue after 5 minutes for periodic re-evaluation
    Ok(Action::requeue(Duration::from_secs(300)))
}

/// Patch the status subresource of a NotificationChannel
async fn patch_status(
    client: &Client,
    namespace: &str,
    name: &str,
    status: &NotificationChannelStatus,
) -> Result<(), NotificationChannelError> {
    let channels: Api<NotificationChannel> = Api::namespaced(client.clone(), namespace);
    let status_patch = json!({
        "status": status
    });

    channels
        .patch_status(
            name,
            &PatchParams::apply("beeper-operator"),
            &Patch::Merge(&status_patch),
        )
        .await?;

    debug!(name = %name, "NotificationChannel status updated");
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

/// Error policy for NotificationChannel reconciliation failures
fn error_policy(
    channel: Arc<NotificationChannel>,
    error: &NotificationChannelError,
    _ctx: Arc<NotificationChannelContext>,
) -> Action {
    error!(
        channel = %channel.name_any(),
        error = %error,
        "NotificationChannel reconciliation failed"
    );
    // Exponential backoff: base 5s, factor 2x, max 60s, with jitter
    Action::requeue(backoff_duration(1))
}

/// Start the NotificationChannel controller
pub async fn run_notificationchannel_controller(client: Client) -> anyhow::Result<()> {
    let channels: Api<NotificationChannel> = Api::all(client.clone());
    let ctx = Arc::new(NotificationChannelContext { client });

    info!("Starting NotificationChannel controller");

    Controller::new(channels, Default::default())
        .run(reconcile, error_policy, ctx)
        .for_each(|res| async move {
            match res {
                Ok(o) => debug!(resource = ?o, "NotificationChannel reconciled"),
                Err(e) => warn!(error = %e, "NotificationChannel reconciliation error"),
            }
        })
        .await;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_notificationchannel_error_display_missing_key() {
        let err = NotificationChannelError::MissingObjectKey("metadata.name");
        assert_eq!(format!("{}", err), "Missing object key: metadata.name");
    }

    #[test]
    fn test_notificationchannel_error_from_kube() {
        let _: fn(kube::Error) -> NotificationChannelError =
            NotificationChannelError::KubeError;
    }

    #[test]
    fn test_notificationchannel_error_from_serde() {
        let _: fn(serde_json::Error) -> NotificationChannelError =
            NotificationChannelError::SerializationError;
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
        // 5 * 2^10 = 5120, capped at 60, jitter factor 115% => 69 => capped at 69
        // Actually: min(5 * 1024, 60) = 60, jitter 115% => 69
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
