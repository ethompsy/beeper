//! Investigator Job builder and status management
//!
//! This module handles building K8s Jobs for investigator pods and
//! updating Investigation CR status throughout the lifecycle.

use std::collections::BTreeMap;

use chrono::Utc;
use k8s_openapi::api::batch::v1::{Job, JobSpec};
use k8s_openapi::api::core::v1::{
    Container, EnvVar, EnvVarSource, PodSpec, PodTemplateSpec, ResourceRequirements,
    SecretKeySelector,
};
use k8s_openapi::apimachinery::pkg::api::resource::Quantity;
use k8s_openapi::apimachinery::pkg::apis::meta::v1::ObjectMeta;
use kube::api::{Patch, PatchParams};
use kube::{Api, Client, Resource, ResourceExt};
use serde_json::json;
use tracing::{debug, info, warn};

use crate::crds::{Investigation, InvestigationPhase, InvestigationStatus, WorkflowState};

/// Configuration for investigator Jobs
#[derive(Debug, Clone)]
pub struct InvestigatorConfig {
    /// Container image for the investigator
    pub image: String,
    /// Image pull policy
    pub image_pull_policy: String,
    /// Number of retries before marking Job as failed
    pub backoff_limit: i32,
    /// Maximum time (seconds) for the Job to run
    pub active_deadline_seconds: i64,
    /// Time to keep completed Jobs before cleanup
    pub ttl_seconds_after_finished: i32,
    /// CPU limit for the investigator container
    pub cpu_limit: String,
    /// Memory limit for the investigator container
    pub memory_limit: String,
    /// CPU request for the investigator container
    pub cpu_request: String,
    /// Memory request for the investigator container
    pub memory_request: String,
    /// Qdrant host for KB access
    pub qdrant_host: String,
    /// Qdrant port for KB access
    pub qdrant_port: String,
    /// LLM provider name
    pub llm_provider: String,
    /// LLM model name
    pub llm_model: String,
    /// Name of the Secret containing LLM API key
    pub llm_api_key_secret: String,
    /// Key within the Secret containing LLM API key
    pub llm_api_key_secret_key: String,
    /// ServiceAccount name for investigator pods
    pub service_account_name: String,
    /// Prometheus URL for source queries (empty = not configured)
    pub prometheus_url: String,
    /// Loki URL for source queries (empty = not configured)
    pub loki_url: String,
    /// LLM endpoint URL (empty = use provider default; required for Ollama)
    pub llm_endpoint: String,
}

impl InvestigatorConfig {
    /// Build config from environment variables, falling back to defaults.
    ///
    /// Each field can be overridden via `BEEPER_INVESTIGATOR_*` env vars.
    /// `prometheus_url` and `loki_url` also fall back to the non-prefixed
    /// `PROMETHEUS_URL` / `LOKI_URL` vars already set in the operator
    /// deployment. Similarly, `llm_provider` / `llm_model` fall back to
    /// `LLM_PROVIDER` / `LLM_MODEL`.
    pub fn from_env() -> Self {
        Self {
            image: std::env::var("BEEPER_INVESTIGATOR_IMAGE")
                .unwrap_or_else(|_| "beeper/investigator:latest".to_string()),
            image_pull_policy: std::env::var("BEEPER_INVESTIGATOR_IMAGE_PULL_POLICY")
                .unwrap_or_else(|_| "IfNotPresent".to_string()),
            backoff_limit: std::env::var("BEEPER_INVESTIGATOR_BACKOFF_LIMIT")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(2),
            active_deadline_seconds: std::env::var("BEEPER_INVESTIGATOR_ACTIVE_DEADLINE_SECONDS")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(1800),
            ttl_seconds_after_finished: std::env::var(
                "BEEPER_INVESTIGATOR_TTL_SECONDS_AFTER_FINISHED",
            )
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(3600),
            cpu_limit: std::env::var("BEEPER_INVESTIGATOR_CPU_LIMIT")
                .unwrap_or_else(|_| "1000m".to_string()),
            memory_limit: std::env::var("BEEPER_INVESTIGATOR_MEMORY_LIMIT")
                .unwrap_or_else(|_| "512Mi".to_string()),
            cpu_request: std::env::var("BEEPER_INVESTIGATOR_CPU_REQUEST")
                .unwrap_or_else(|_| "200m".to_string()),
            memory_request: std::env::var("BEEPER_INVESTIGATOR_MEMORY_REQUEST")
                .unwrap_or_else(|_| "256Mi".to_string()),
            qdrant_host: std::env::var("BEEPER_INVESTIGATOR_QDRANT_HOST")
                .unwrap_or_else(|_| "qdrant".to_string()),
            qdrant_port: std::env::var("BEEPER_INVESTIGATOR_QDRANT_PORT")
                .unwrap_or_else(|_| "6333".to_string()),
            llm_provider: std::env::var("BEEPER_INVESTIGATOR_LLM_PROVIDER")
                .or_else(|_| std::env::var("LLM_PROVIDER"))
                .unwrap_or_else(|_| "anthropic".to_string()),
            llm_model: std::env::var("BEEPER_INVESTIGATOR_LLM_MODEL")
                .or_else(|_| std::env::var("LLM_MODEL"))
                .unwrap_or_else(|_| "claude-sonnet-4".to_string()),
            llm_api_key_secret: std::env::var("BEEPER_INVESTIGATOR_LLM_API_KEY_SECRET")
                .unwrap_or_else(|_| "llm-credentials".to_string()),
            llm_api_key_secret_key: std::env::var("BEEPER_INVESTIGATOR_LLM_API_KEY_SECRET_KEY")
                .unwrap_or_else(|_| "api-key".to_string()),
            service_account_name: std::env::var("BEEPER_INVESTIGATOR_SERVICE_ACCOUNT")
                .unwrap_or_else(|_| "beeper-investigator".to_string()),
            prometheus_url: std::env::var("BEEPER_PROMETHEUS_URL")
                .or_else(|_| std::env::var("PROMETHEUS_URL"))
                .unwrap_or_default(),
            loki_url: std::env::var("BEEPER_LOKI_URL")
                .or_else(|_| std::env::var("LOKI_URL"))
                .unwrap_or_default(),
            llm_endpoint: std::env::var("BEEPER_INVESTIGATOR_LLM_ENDPOINT")
                .or_else(|_| std::env::var("LLM_ENDPOINT"))
                .unwrap_or_default(),
        }
    }
}

impl Default for InvestigatorConfig {
    fn default() -> Self {
        Self {
            image: "beeper/investigator:latest".to_string(),
            image_pull_policy: "IfNotPresent".to_string(),
            backoff_limit: 2,
            active_deadline_seconds: 1800,    // 30 minutes
            ttl_seconds_after_finished: 3600, // 1 hour
            cpu_limit: "1000m".to_string(),
            memory_limit: "512Mi".to_string(),
            cpu_request: "200m".to_string(),
            memory_request: "256Mi".to_string(),
            qdrant_host: "qdrant".to_string(),
            qdrant_port: "6333".to_string(),
            llm_provider: "anthropic".to_string(),
            llm_model: "claude-sonnet-4".to_string(),
            llm_api_key_secret: "llm-credentials".to_string(),
            llm_api_key_secret_key: "api-key".to_string(),
            service_account_name: "beeper-investigator".to_string(),
            prometheus_url: String::new(),
            loki_url: String::new(),
            llm_endpoint: String::new(),
        }
    }
}

/// Error type for investigator job operations
#[derive(Debug, thiserror::Error)]
pub enum InvestigatorJobError {
    #[error("Kubernetes API error: {0}")]
    KubeError(#[from] kube::Error),

    #[error("Missing investigation name")]
    MissingName,

    #[error("Missing investigation namespace")]
    MissingNamespace,

    #[error("Serialization error: {0}")]
    SerializationError(#[from] serde_json::Error),
}

/// Build a K8s Job for running an investigator
pub fn build_investigator_job(
    investigation: &Investigation,
    config: &InvestigatorConfig,
) -> Result<Job, InvestigatorJobError> {
    let name = investigation
        .metadata
        .name
        .as_ref()
        .ok_or(InvestigatorJobError::MissingName)?;
    let namespace = investigation
        .metadata
        .namespace
        .as_ref()
        .ok_or(InvestigatorJobError::MissingNamespace)?;

    let job_name = format!("inv-{}", name);
    let investigation_id = name.clone();

    // Build owner reference for garbage collection
    let owner_ref = investigation.controller_owner_ref(&()).unwrap();

    // Build environment variables
    let mut env_vars = vec![
        EnvVar {
            name: "INVESTIGATION_ID".to_string(),
            value: Some(investigation_id.clone()),
            value_from: None,
        },
        EnvVar {
            name: "INVESTIGATION_NAMESPACE".to_string(),
            value: Some(namespace.clone()),
            value_from: None,
        },
        EnvVar {
            name: "BEEPER_LLM_PROVIDER".to_string(),
            value: Some(config.llm_provider.clone()),
            value_from: None,
        },
        EnvVar {
            name: "BEEPER_LLM_MODEL".to_string(),
            value: Some(config.llm_model.clone()),
            value_from: None,
        },
        EnvVar {
            name: "BEEPER_LLM_API_KEY".to_string(),
            value: None,
            value_from: Some(EnvVarSource {
                secret_key_ref: Some(SecretKeySelector {
                    name: config.llm_api_key_secret.clone(),
                    key: config.llm_api_key_secret_key.clone(),
                    optional: Some(true),
                }),
                ..Default::default()
            }),
        },
        EnvVar {
            name: "QDRANT_HOST".to_string(),
            value: Some(config.qdrant_host.clone()),
            value_from: None,
        },
        EnvVar {
            name: "QDRANT_PORT".to_string(),
            value: Some(config.qdrant_port.clone()),
            value_from: None,
        },
        // Pass investigation context
        EnvVar {
            name: "INVESTIGATION_CONDITION".to_string(),
            value: Some(investigation.spec.condition.clone()),
            value_from: None,
        },
        EnvVar {
            name: "INVESTIGATION_SERVICE".to_string(),
            value: Some(investigation.spec.service.clone()),
            value_from: None,
        },
        EnvVar {
            name: "INVESTIGATION_SEVERITY".to_string(),
            value: Some(format!("{:?}", investigation.spec.severity).to_lowercase()),
            value_from: None,
        },
        EnvVar {
            name: "PROMETHEUS_URL".to_string(),
            value: Some(config.prometheus_url.clone()),
            value_from: None,
        },
        EnvVar {
            name: "LOKI_URL".to_string(),
            value: Some(config.loki_url.clone()),
            value_from: None,
        },
    ];

    // Only pass LLM endpoint when configured (required for Ollama, not for cloud providers)
    if !config.llm_endpoint.is_empty() {
        env_vars.push(EnvVar {
            name: "BEEPER_LLM_ENDPOINT".to_string(),
            value: Some(config.llm_endpoint.clone()),
            value_from: None,
        });
    }

    // Build resource requirements
    let resources = ResourceRequirements {
        limits: Some(BTreeMap::from([
            ("cpu".to_string(), Quantity(config.cpu_limit.clone())),
            ("memory".to_string(), Quantity(config.memory_limit.clone())),
        ])),
        requests: Some(BTreeMap::from([
            ("cpu".to_string(), Quantity(config.cpu_request.clone())),
            (
                "memory".to_string(),
                Quantity(config.memory_request.clone()),
            ),
        ])),
        ..Default::default()
    };

    // Build labels
    let labels = BTreeMap::from([
        (
            "app.kubernetes.io/component".to_string(),
            "investigator".to_string(),
        ),
        ("app.kubernetes.io/name".to_string(), "beeper".to_string()),
        (
            "app.kubernetes.io/managed-by".to_string(),
            "beeper-operator".to_string(),
        ),
        (
            "beeper.dev/investigation-id".to_string(),
            investigation_id.clone(),
        ),
    ]);

    let job = Job {
        metadata: ObjectMeta {
            name: Some(job_name.clone()),
            namespace: Some(namespace.clone()),
            labels: Some(labels.clone()),
            owner_references: Some(vec![owner_ref]),
            ..Default::default()
        },
        spec: Some(JobSpec {
            backoff_limit: Some(config.backoff_limit),
            active_deadline_seconds: Some(config.active_deadline_seconds),
            ttl_seconds_after_finished: Some(config.ttl_seconds_after_finished),
            template: PodTemplateSpec {
                metadata: Some(ObjectMeta {
                    labels: Some(labels),
                    ..Default::default()
                }),
                spec: Some(PodSpec {
                    containers: vec![Container {
                        name: "investigator".to_string(),
                        image: Some(config.image.clone()),
                        image_pull_policy: Some(config.image_pull_policy.clone()),
                        env: Some(env_vars),
                        resources: Some(resources),
                        ..Default::default()
                    }],
                    restart_policy: Some("Never".to_string()),
                    service_account_name: Some(config.service_account_name.clone()),
                    ..Default::default()
                }),
            },
            ..Default::default()
        }),
        ..Default::default()
    };

    debug!(
        job_name = %job_name,
        investigation_id = %investigation_id,
        "Built investigator Job spec"
    );

    Ok(job)
}

/// Update the Investigation status with a new phase
pub async fn update_investigation_status(
    client: &Client,
    investigation: &Investigation,
    new_status: InvestigationStatus,
) -> Result<(), InvestigatorJobError> {
    let name = investigation
        .metadata
        .name
        .as_ref()
        .ok_or(InvestigatorJobError::MissingName)?;
    let namespace = investigation
        .metadata
        .namespace
        .as_ref()
        .ok_or(InvestigatorJobError::MissingNamespace)?;

    let api: Api<Investigation> = Api::namespaced(client.clone(), namespace);

    let status_patch = json!({
        "status": new_status
    });

    api.patch_status(
        name,
        &PatchParams::apply("beeper-operator"),
        &Patch::Merge(&status_patch),
    )
    .await?;

    info!(
        investigation_name = %name,
        phase = ?new_status.phase,
        "Updated Investigation status"
    );

    Ok(())
}

/// Set Investigation phase to Pending (for newly created investigations)
pub async fn set_phase_pending(
    client: &Client,
    investigation: &Investigation,
) -> Result<(), InvestigatorJobError> {
    let now = Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string();

    let status = InvestigationStatus {
        phase: Some(InvestigationPhase::Pending),
        started_at: None,
        completed_at: None,
        job_name: None,
        error: None,
        message: None,
        workflow_state: Some(WorkflowState::Detected),
        workflow_state_changed_at: Some(now),
    };

    update_investigation_status(client, investigation, status).await
}

/// Set Investigation phase to Running (when Job is created)
pub async fn set_phase_running(
    client: &Client,
    investigation: &Investigation,
    job_name: &str,
) -> Result<(), InvestigatorJobError> {
    let now = Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string();

    let status = InvestigationStatus {
        phase: Some(InvestigationPhase::Running),
        started_at: Some(now.clone()),
        completed_at: None,
        job_name: Some(job_name.to_string()),
        error: None,
        message: None,
        workflow_state: Some(WorkflowState::Investigating),
        workflow_state_changed_at: Some(now),
    };

    update_investigation_status(client, investigation, status).await
}

/// Set Investigation phase to Completed
pub async fn set_phase_completed(
    client: &Client,
    investigation: &Investigation,
) -> Result<(), InvestigatorJobError> {
    let now = Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string();

    // Preserve started_at and job_name from current status
    let current_status = match investigation.status.as_ref() {
        Some(s) => s.clone(),
        None => {
            warn!(investigation = %investigation.name_any(), "set_phase_completed called with no existing status — started_at and job_name will be lost");
            InvestigationStatus::default()
        }
    };

    // Validate workflow state transition
    if let Some(ref current_ws) = current_status.workflow_state {
        if !current_ws.is_valid_transition(&WorkflowState::Resolved) {
            warn!(investigation = %investigation.name_any(), from = ?current_ws, to = "Resolved", "invalid workflow state transition");
        }
    }

    let status = InvestigationStatus {
        phase: Some(InvestigationPhase::Completed),
        started_at: current_status.started_at,
        completed_at: Some(now.clone()),
        job_name: current_status.job_name,
        error: None,
        message: None,
        workflow_state: Some(WorkflowState::Resolved),
        workflow_state_changed_at: Some(now),
    };

    update_investigation_status(client, investigation, status).await
}

/// Set Investigation phase to Failed with error message
pub async fn set_phase_failed(
    client: &Client,
    investigation: &Investigation,
    error_message: &str,
) -> Result<(), InvestigatorJobError> {
    let now = Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string();

    // Preserve started_at and job_name from current status
    let current_status = match investigation.status.as_ref() {
        Some(s) => s.clone(),
        None => {
            warn!(investigation = %investigation.name_any(), "set_phase_failed called with no existing status — started_at and job_name will be lost");
            InvestigationStatus::default()
        }
    };

    // Validate workflow state transition
    if let Some(ref current_ws) = current_status.workflow_state {
        if !current_ws.is_valid_transition(&WorkflowState::Failed) {
            warn!(investigation = %investigation.name_any(), from = ?current_ws, to = "Failed", "invalid workflow state transition");
        }
    }

    let status = InvestigationStatus {
        phase: Some(InvestigationPhase::Failed),
        started_at: current_status.started_at,
        completed_at: Some(now.clone()),
        job_name: current_status.job_name,
        error: Some(error_message.to_string()),
        message: None,
        workflow_state: Some(WorkflowState::Failed),
        workflow_state_changed_at: Some(now),
    };

    update_investigation_status(client, investigation, status).await
}

/// Check if a Job has completed successfully
pub fn is_job_completed(job: &Job) -> bool {
    job.status
        .as_ref()
        .and_then(|s| s.succeeded)
        .map(|s| s > 0)
        .unwrap_or(false)
}

/// Check if a Job has failed
pub fn is_job_failed(job: &Job) -> bool {
    job.status
        .as_ref()
        .and_then(|s| s.failed)
        .map(|f| f > 0)
        .unwrap_or(false)
}

/// Get failure message from a Job
pub fn get_job_failure_message(job: &Job) -> Option<String> {
    job.status.as_ref().and_then(|status| {
        status.conditions.as_ref().and_then(|conditions| {
            conditions
                .iter()
                .find(|c| c.type_ == "Failed" && c.status == "True")
                .and_then(|c| c.message.clone())
        })
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::crds::{InvestigationSpec, Severity};
    use k8s_openapi::apimachinery::pkg::apis::meta::v1::ObjectMeta;

    fn create_test_investigation(name: &str, namespace: &str) -> Investigation {
        Investigation {
            metadata: ObjectMeta {
                name: Some(name.to_string()),
                namespace: Some(namespace.to_string()),
                uid: Some("test-uid-123".to_string()),
                ..Default::default()
            },
            spec: InvestigationSpec {
                condition: "High error rate detected".to_string(),
                service: "payments".to_string(),
                severity: Severity::High,
                triggered_at: Some("2026-02-12T10:00:00Z".to_string()),
                impact_score: None,
            },
            status: None,
        }
    }

    #[test]
    fn test_build_investigator_job_basic() {
        let investigation = create_test_investigation("test-inv", "default");
        let config = InvestigatorConfig::default();

        let job = build_investigator_job(&investigation, &config).unwrap();

        // Verify job name
        assert_eq!(job.metadata.name, Some("inv-test-inv".to_string()));
        assert_eq!(job.metadata.namespace, Some("default".to_string()));

        // Verify labels
        let labels = job.metadata.labels.as_ref().unwrap();
        assert_eq!(
            labels.get("app.kubernetes.io/component"),
            Some(&"investigator".to_string())
        );
        assert_eq!(
            labels.get("beeper.dev/investigation-id"),
            Some(&"test-inv".to_string())
        );

        // Verify owner reference
        let owner_refs = job.metadata.owner_references.as_ref().unwrap();
        assert_eq!(owner_refs.len(), 1);
        assert_eq!(owner_refs[0].kind, "Investigation");
        assert_eq!(owner_refs[0].name, "test-inv");

        // Verify job spec
        let spec = job.spec.as_ref().unwrap();
        assert_eq!(spec.backoff_limit, Some(2));
        assert_eq!(spec.active_deadline_seconds, Some(1800));
        assert_eq!(spec.ttl_seconds_after_finished, Some(3600));
    }

    #[test]
    fn test_build_investigator_job_env_vars() {
        let investigation = create_test_investigation("test-inv", "default");
        let config = InvestigatorConfig {
            llm_provider: "openai".to_string(),
            llm_model: "gpt-4".to_string(),
            qdrant_host: "qdrant-svc".to_string(),
            qdrant_port: "6333".to_string(),
            ..Default::default()
        };

        let job = build_investigator_job(&investigation, &config).unwrap();

        let container = &job
            .spec
            .as_ref()
            .unwrap()
            .template
            .spec
            .as_ref()
            .unwrap()
            .containers[0];
        let env_vars = container.env.as_ref().unwrap();

        // Check INVESTIGATION_ID
        let inv_id = env_vars
            .iter()
            .find(|e| e.name == "INVESTIGATION_ID")
            .unwrap();
        assert_eq!(inv_id.value, Some("test-inv".to_string()));

        // Check INVESTIGATION_NAMESPACE
        let inv_ns = env_vars
            .iter()
            .find(|e| e.name == "INVESTIGATION_NAMESPACE")
            .unwrap();
        assert_eq!(inv_ns.value, Some("default".to_string()));

        // Check LLM provider
        let provider = env_vars
            .iter()
            .find(|e| e.name == "BEEPER_LLM_PROVIDER")
            .unwrap();
        assert_eq!(provider.value, Some("openai".to_string()));

        // Check LLM model
        let model = env_vars
            .iter()
            .find(|e| e.name == "BEEPER_LLM_MODEL")
            .unwrap();
        assert_eq!(model.value, Some("gpt-4".to_string()));

        // Check LLM API key comes from secret
        let api_key = env_vars
            .iter()
            .find(|e| e.name == "BEEPER_LLM_API_KEY")
            .unwrap();
        assert!(api_key.value.is_none());
        assert!(api_key.value_from.is_some());
        let secret_ref = api_key
            .value_from
            .as_ref()
            .unwrap()
            .secret_key_ref
            .as_ref()
            .unwrap();
        assert_eq!(secret_ref.name, "llm-credentials");
        assert_eq!(secret_ref.key, "api-key");

        // Check Qdrant host and port
        let qdrant_host = env_vars.iter().find(|e| e.name == "QDRANT_HOST").unwrap();
        assert_eq!(qdrant_host.value, Some("qdrant-svc".to_string()));

        let qdrant_port = env_vars.iter().find(|e| e.name == "QDRANT_PORT").unwrap();
        assert_eq!(qdrant_port.value, Some("6333".to_string()));

        // Check investigation context
        let condition = env_vars
            .iter()
            .find(|e| e.name == "INVESTIGATION_CONDITION")
            .unwrap();
        assert_eq!(
            condition.value,
            Some("High error rate detected".to_string())
        );

        let service = env_vars
            .iter()
            .find(|e| e.name == "INVESTIGATION_SERVICE")
            .unwrap();
        assert_eq!(service.value, Some("payments".to_string()));

        let severity = env_vars
            .iter()
            .find(|e| e.name == "INVESTIGATION_SEVERITY")
            .unwrap();
        assert_eq!(severity.value, Some("high".to_string()));
    }

    #[test]
    fn test_build_investigator_job_resources() {
        let investigation = create_test_investigation("test-inv", "default");
        let config = InvestigatorConfig {
            cpu_limit: "2000m".to_string(),
            memory_limit: "1Gi".to_string(),
            cpu_request: "500m".to_string(),
            memory_request: "512Mi".to_string(),
            ..Default::default()
        };

        let job = build_investigator_job(&investigation, &config).unwrap();

        let container = &job
            .spec
            .as_ref()
            .unwrap()
            .template
            .spec
            .as_ref()
            .unwrap()
            .containers[0];
        let resources = container.resources.as_ref().unwrap();

        let limits = resources.limits.as_ref().unwrap();
        assert_eq!(limits.get("cpu"), Some(&Quantity("2000m".to_string())));
        assert_eq!(limits.get("memory"), Some(&Quantity("1Gi".to_string())));

        let requests = resources.requests.as_ref().unwrap();
        assert_eq!(requests.get("cpu"), Some(&Quantity("500m".to_string())));
        assert_eq!(requests.get("memory"), Some(&Quantity("512Mi".to_string())));
    }

    #[test]
    fn test_build_investigator_job_missing_name() {
        let investigation = Investigation {
            metadata: ObjectMeta {
                name: None,
                namespace: Some("default".to_string()),
                ..Default::default()
            },
            spec: InvestigationSpec {
                condition: "test".to_string(),
                service: "test".to_string(),
                severity: Severity::Medium,
                triggered_at: None,
                impact_score: None,
            },
            status: None,
        };
        let config = InvestigatorConfig::default();

        let result = build_investigator_job(&investigation, &config);
        assert!(matches!(result, Err(InvestigatorJobError::MissingName)));
    }

    #[test]
    fn test_build_investigator_job_missing_namespace() {
        let investigation = Investigation {
            metadata: ObjectMeta {
                name: Some("test".to_string()),
                namespace: None,
                ..Default::default()
            },
            spec: InvestigationSpec {
                condition: "test".to_string(),
                service: "test".to_string(),
                severity: Severity::Medium,
                triggered_at: None,
                impact_score: None,
            },
            status: None,
        };
        let config = InvestigatorConfig::default();

        let result = build_investigator_job(&investigation, &config);
        assert!(matches!(
            result,
            Err(InvestigatorJobError::MissingNamespace)
        ));
    }

    #[test]
    fn test_is_job_completed() {
        use k8s_openapi::api::batch::v1::JobStatus;

        let mut job = Job::default();

        // No status = not completed
        assert!(!is_job_completed(&job));

        // succeeded = 0 = not completed
        job.status = Some(JobStatus {
            succeeded: Some(0),
            ..Default::default()
        });
        assert!(!is_job_completed(&job));

        // succeeded = 1 = completed
        job.status = Some(JobStatus {
            succeeded: Some(1),
            ..Default::default()
        });
        assert!(is_job_completed(&job));
    }

    #[test]
    fn test_is_job_failed() {
        use k8s_openapi::api::batch::v1::JobStatus;

        let mut job = Job::default();

        // No status = not failed
        assert!(!is_job_failed(&job));

        // failed = 0 = not failed
        job.status = Some(JobStatus {
            failed: Some(0),
            ..Default::default()
        });
        assert!(!is_job_failed(&job));

        // failed = 1 = failed
        job.status = Some(JobStatus {
            failed: Some(1),
            ..Default::default()
        });
        assert!(is_job_failed(&job));
    }

    // Env-var tests must be serialized because they share process-wide state.
    use std::sync::Mutex;
    static ENV_LOCK: Mutex<()> = Mutex::new(());

    /// Remove all env vars that `InvestigatorConfig::from_env()` reads.
    fn clear_investigator_env_vars() {
        for var in [
            "BEEPER_PROMETHEUS_URL",
            "BEEPER_LOKI_URL",
            "LOKI_URL",
            "PROMETHEUS_URL",
            "LLM_PROVIDER",
            "LLM_MODEL",
            "BEEPER_INVESTIGATOR_IMAGE",
            "BEEPER_INVESTIGATOR_IMAGE_PULL_POLICY",
            "BEEPER_INVESTIGATOR_QDRANT_HOST",
            "BEEPER_INVESTIGATOR_QDRANT_PORT",
            "BEEPER_INVESTIGATOR_LLM_PROVIDER",
            "BEEPER_INVESTIGATOR_LLM_MODEL",
            "BEEPER_INVESTIGATOR_LLM_API_KEY_SECRET",
            "BEEPER_INVESTIGATOR_LLM_API_KEY_SECRET_KEY",
            "BEEPER_INVESTIGATOR_SERVICE_ACCOUNT",
            "BEEPER_INVESTIGATOR_BACKOFF_LIMIT",
            "BEEPER_INVESTIGATOR_ACTIVE_DEADLINE_SECONDS",
            "BEEPER_INVESTIGATOR_TTL_SECONDS_AFTER_FINISHED",
            "BEEPER_INVESTIGATOR_CPU_LIMIT",
            "BEEPER_INVESTIGATOR_MEMORY_LIMIT",
            "BEEPER_INVESTIGATOR_CPU_REQUEST",
            "BEEPER_INVESTIGATOR_MEMORY_REQUEST",
        ] {
            std::env::remove_var(var);
        }
    }

    #[test]
    fn test_investigator_config_from_env() {
        let _guard = ENV_LOCK.lock().unwrap();
        clear_investigator_env_vars();

        // Set all BEEPER_INVESTIGATOR_* env vars
        std::env::set_var("BEEPER_PROMETHEUS_URL", "http://prometheus:9090");
        std::env::set_var("BEEPER_LOKI_URL", "http://loki:3100");
        std::env::set_var("BEEPER_INVESTIGATOR_IMAGE", "custom/investigator:v2");
        std::env::set_var("BEEPER_INVESTIGATOR_IMAGE_PULL_POLICY", "Always");
        std::env::set_var("BEEPER_INVESTIGATOR_QDRANT_HOST", "beeper-qdrant");
        std::env::set_var("BEEPER_INVESTIGATOR_QDRANT_PORT", "6334");
        std::env::set_var("BEEPER_INVESTIGATOR_LLM_PROVIDER", "openai");
        std::env::set_var("BEEPER_INVESTIGATOR_LLM_MODEL", "gpt-4o");
        std::env::set_var("BEEPER_INVESTIGATOR_LLM_API_KEY_SECRET", "my-secret");
        std::env::set_var("BEEPER_INVESTIGATOR_LLM_API_KEY_SECRET_KEY", "my-key");
        std::env::set_var("BEEPER_INVESTIGATOR_SERVICE_ACCOUNT", "custom-sa");
        std::env::set_var("BEEPER_INVESTIGATOR_BACKOFF_LIMIT", "5");
        std::env::set_var("BEEPER_INVESTIGATOR_ACTIVE_DEADLINE_SECONDS", "900");
        std::env::set_var("BEEPER_INVESTIGATOR_TTL_SECONDS_AFTER_FINISHED", "7200");

        let config = InvestigatorConfig::from_env();

        assert_eq!(config.prometheus_url, "http://prometheus:9090");
        assert_eq!(config.loki_url, "http://loki:3100");
        assert_eq!(config.image, "custom/investigator:v2");
        assert_eq!(config.image_pull_policy, "Always");
        assert_eq!(config.qdrant_host, "beeper-qdrant");
        assert_eq!(config.qdrant_port, "6334");
        assert_eq!(config.llm_provider, "openai");
        assert_eq!(config.llm_model, "gpt-4o");
        assert_eq!(config.llm_api_key_secret, "my-secret");
        assert_eq!(config.llm_api_key_secret_key, "my-key");
        assert_eq!(config.service_account_name, "custom-sa");
        assert_eq!(config.backoff_limit, 5);
        assert_eq!(config.active_deadline_seconds, 900);
        assert_eq!(config.ttl_seconds_after_finished, 7200);

        clear_investigator_env_vars();
    }

    #[test]
    fn test_investigator_config_from_env_defaults_when_unset() {
        let _guard = ENV_LOCK.lock().unwrap();
        clear_investigator_env_vars();

        let config = InvestigatorConfig::from_env();

        assert_eq!(config.prometheus_url, "");
        assert_eq!(config.loki_url, "");
        assert_eq!(config.image, "beeper/investigator:latest");
        assert_eq!(config.image_pull_policy, "IfNotPresent");
        assert_eq!(config.qdrant_host, "qdrant");
        assert_eq!(config.qdrant_port, "6333");
        assert_eq!(config.llm_provider, "anthropic");
        assert_eq!(config.llm_model, "claude-sonnet-4");
        assert_eq!(config.llm_api_key_secret, "llm-credentials");
        assert_eq!(config.llm_api_key_secret_key, "api-key");
        assert_eq!(config.service_account_name, "beeper-investigator");
        assert_eq!(config.backoff_limit, 2);
        assert_eq!(config.active_deadline_seconds, 1800);
        assert_eq!(config.ttl_seconds_after_finished, 3600);
    }

    #[test]
    fn test_investigator_config_from_env_fallback_vars() {
        let _guard = ENV_LOCK.lock().unwrap();
        clear_investigator_env_vars();

        // Test that prometheus_url falls back to PROMETHEUS_URL,
        // loki_url falls back to LOKI_URL,
        // and llm_provider/llm_model fall back to LLM_PROVIDER/LLM_MODEL
        std::env::set_var("PROMETHEUS_URL", "http://fallback-prom:9090");
        std::env::set_var("LOKI_URL", "http://fallback-loki:3100");
        std::env::set_var("LLM_PROVIDER", "openai");
        std::env::set_var("LLM_MODEL", "gpt-4-turbo");

        let config = InvestigatorConfig::from_env();

        assert_eq!(config.prometheus_url, "http://fallback-prom:9090");
        assert_eq!(config.loki_url, "http://fallback-loki:3100");
        assert_eq!(config.llm_provider, "openai");
        assert_eq!(config.llm_model, "gpt-4-turbo");

        clear_investigator_env_vars();
    }

    #[test]
    fn test_investigator_config_from_env_prefixed_takes_priority() {
        let _guard = ENV_LOCK.lock().unwrap();
        clear_investigator_env_vars();

        // BEEPER_PROMETHEUS_URL should take priority over PROMETHEUS_URL
        // BEEPER_LOKI_URL should take priority over LOKI_URL
        std::env::set_var("BEEPER_PROMETHEUS_URL", "http://prefixed:9090");
        std::env::set_var("PROMETHEUS_URL", "http://fallback:9090");
        std::env::set_var("BEEPER_LOKI_URL", "http://prefixed-loki:3100");
        std::env::set_var("LOKI_URL", "http://fallback-loki:3100");
        std::env::set_var("BEEPER_INVESTIGATOR_LLM_PROVIDER", "anthropic");
        std::env::set_var("LLM_PROVIDER", "openai");

        let config = InvestigatorConfig::from_env();

        assert_eq!(config.prometheus_url, "http://prefixed:9090");
        assert_eq!(config.loki_url, "http://prefixed-loki:3100");
        assert_eq!(config.llm_provider, "anthropic");

        clear_investigator_env_vars();
    }

    #[test]
    fn test_investigator_config_default() {
        let config = InvestigatorConfig::default();

        assert_eq!(config.image, "beeper/investigator:latest");
        assert_eq!(config.backoff_limit, 2);
        assert_eq!(config.active_deadline_seconds, 1800);
        assert_eq!(config.ttl_seconds_after_finished, 3600);
        assert_eq!(config.llm_provider, "anthropic");
        assert_eq!(config.llm_model, "claude-sonnet-4");
        assert_eq!(config.qdrant_host, "qdrant");
        assert_eq!(config.qdrant_port, "6333");
        assert_eq!(config.service_account_name, "beeper-investigator");
        assert_eq!(config.prometheus_url, "");
        assert_eq!(config.loki_url, "");
    }

    #[test]
    fn test_build_investigator_job_source_url_env_vars() {
        let investigation = create_test_investigation("test-inv", "default");
        let config = InvestigatorConfig {
            prometheus_url: "http://prometheus:9090".to_string(),
            loki_url: "http://loki:3100".to_string(),
            ..Default::default()
        };

        let job = build_investigator_job(&investigation, &config).unwrap();

        let container = &job
            .spec
            .as_ref()
            .unwrap()
            .template
            .spec
            .as_ref()
            .unwrap()
            .containers[0];
        let env_vars = container.env.as_ref().unwrap();

        let prom_url = env_vars
            .iter()
            .find(|e| e.name == "PROMETHEUS_URL")
            .unwrap();
        assert_eq!(prom_url.value, Some("http://prometheus:9090".to_string()));

        let loki_url = env_vars.iter().find(|e| e.name == "LOKI_URL").unwrap();
        assert_eq!(loki_url.value, Some("http://loki:3100".to_string()));
    }

    #[test]
    fn test_build_investigator_job_source_urls_empty_by_default() {
        let investigation = create_test_investigation("test-inv", "default");
        let config = InvestigatorConfig::default();

        let job = build_investigator_job(&investigation, &config).unwrap();

        let container = &job
            .spec
            .as_ref()
            .unwrap()
            .template
            .spec
            .as_ref()
            .unwrap()
            .containers[0];
        let env_vars = container.env.as_ref().unwrap();

        let prom_url = env_vars
            .iter()
            .find(|e| e.name == "PROMETHEUS_URL")
            .unwrap();
        assert_eq!(prom_url.value, Some(String::new()));

        let loki_url = env_vars.iter().find(|e| e.name == "LOKI_URL").unwrap();
        assert_eq!(loki_url.value, Some(String::new()));
    }

    #[test]
    fn test_build_investigator_job_service_account() {
        let investigation = create_test_investigation("test-inv", "default");
        let config = InvestigatorConfig {
            service_account_name: "custom-sa".to_string(),
            ..Default::default()
        };

        let job = build_investigator_job(&investigation, &config).unwrap();

        let pod_spec = job.spec.as_ref().unwrap().template.spec.as_ref().unwrap();
        assert_eq!(pod_spec.service_account_name, Some("custom-sa".to_string()));
    }

    // --- Lifecycle status shape tests (Story 2.1) ---
    // These verify the expected data shape and serialization for each phase's
    // InvestigationStatus. The actual set_phase_*() functions are async (require
    // K8s client) so cannot be unit-tested directly; these ensure the status
    // structs they build serialize correctly for the K8s API.

    #[test]
    fn test_lifecycle_pending_status_fields() {
        // Verifies the status shape that set_phase_pending() constructs:
        // phase=Pending, workflow_state=Detected, no job/times/error
        let status = InvestigationStatus {
            phase: Some(InvestigationPhase::Pending),
            started_at: None,
            completed_at: None,
            job_name: None,
            error: None,
            message: None,
            workflow_state: Some(WorkflowState::Detected),
            workflow_state_changed_at: Some("2026-04-18T10:00:00Z".to_string()),
        };

        assert_eq!(status.phase, Some(InvestigationPhase::Pending));
        assert_eq!(status.workflow_state, Some(WorkflowState::Detected));
        assert!(status.started_at.is_none());
        assert!(status.job_name.is_none());
        assert!(status.error.is_none());

        // Verify serialization produces correct JSON
        let json = serde_json::to_value(&status).unwrap();
        assert_eq!(json["phase"], "pending");
        assert_eq!(json["workflow_state"], "detected");
    }

    #[test]
    fn test_lifecycle_running_status_fields() {
        // Verifies the status shape that set_phase_running() constructs
        let status = InvestigationStatus {
            phase: Some(InvestigationPhase::Running),
            started_at: Some("2026-04-18T10:00:01Z".to_string()),
            completed_at: None,
            job_name: Some("inv-test-lifecycle".to_string()),
            error: None,
            message: None,
            workflow_state: Some(WorkflowState::Investigating),
            workflow_state_changed_at: Some("2026-04-18T10:00:01Z".to_string()),
        };

        assert_eq!(status.phase, Some(InvestigationPhase::Running));
        assert_eq!(status.workflow_state, Some(WorkflowState::Investigating));
        assert!(status.started_at.is_some());
        assert_eq!(status.job_name, Some("inv-test-lifecycle".to_string()));
        assert!(status.error.is_none());

        // Verify serialization produces correct JSON for K8s API
        let json = serde_json::to_value(&status).unwrap();
        assert_eq!(json["phase"], "running");
        assert_eq!(json["workflow_state"], "investigating");
        assert_eq!(json["job_name"], "inv-test-lifecycle");

        // Valid workflow transition: Detected → Investigating
        assert!(WorkflowState::Detected.is_valid_transition(&WorkflowState::Investigating));
    }

    #[test]
    fn test_lifecycle_failed_status_preserves_context() {
        // Verifies the status shape that set_phase_failed() constructs:
        // preserves started_at and job_name from Running phase, adds error and completed_at
        let running_status = InvestigationStatus {
            phase: Some(InvestigationPhase::Running),
            started_at: Some("2026-04-18T10:00:01Z".to_string()),
            completed_at: None,
            job_name: Some("inv-test-failure".to_string()),
            error: None,
            message: None,
            workflow_state: Some(WorkflowState::Investigating),
            workflow_state_changed_at: Some("2026-04-18T10:00:01Z".to_string()),
        };

        // Construct failed status preserving context (mirrors set_phase_failed logic)
        let failed_status = InvestigationStatus {
            phase: Some(InvestigationPhase::Failed),
            started_at: running_status.started_at.clone(),
            completed_at: Some("2026-04-18T10:05:00Z".to_string()),
            job_name: running_status.job_name.clone(),
            error: Some("BackoffLimitExceeded".to_string()),
            message: None,
            workflow_state: Some(WorkflowState::Failed),
            workflow_state_changed_at: Some("2026-04-18T10:05:00Z".to_string()),
        };

        assert_eq!(failed_status.phase, Some(InvestigationPhase::Failed));
        assert_eq!(failed_status.workflow_state, Some(WorkflowState::Failed));
        assert_eq!(
            failed_status.error,
            Some("BackoffLimitExceeded".to_string())
        );
        // started_at and job_name preserved from Running phase
        assert_eq!(
            failed_status.started_at,
            Some("2026-04-18T10:00:01Z".to_string())
        );
        assert_eq!(failed_status.job_name, Some("inv-test-failure".to_string()));
        assert!(failed_status.completed_at.is_some());

        // Verify serialization produces correct JSON for K8s API
        let json = serde_json::to_value(&failed_status).unwrap();
        assert_eq!(json["phase"], "failed");
        assert_eq!(json["workflow_state"], "failed");
        assert_eq!(json["error"], "BackoffLimitExceeded");

        // Valid workflow transition: Investigating → Failed
        assert!(WorkflowState::Investigating.is_valid_transition(&WorkflowState::Failed));
    }

    #[test]
    fn test_lifecycle_completed_status_preserves_context() {
        // Verifies the status shape that set_phase_completed() constructs:
        // preserves started_at and job_name from Running phase
        let running_status = InvestigationStatus {
            phase: Some(InvestigationPhase::Running),
            started_at: Some("2026-04-18T10:00:01Z".to_string()),
            completed_at: None,
            job_name: Some("inv-test-complete".to_string()),
            error: None,
            message: None,
            workflow_state: Some(WorkflowState::Investigating),
            workflow_state_changed_at: Some("2026-04-18T10:00:01Z".to_string()),
        };

        // Construct completed status preserving context (mirrors set_phase_completed logic)
        let completed_status = InvestigationStatus {
            phase: Some(InvestigationPhase::Completed),
            started_at: running_status.started_at.clone(),
            completed_at: Some("2026-04-18T10:03:00Z".to_string()),
            job_name: running_status.job_name.clone(),
            error: None,
            message: None,
            workflow_state: Some(WorkflowState::Resolved),
            workflow_state_changed_at: Some("2026-04-18T10:03:00Z".to_string()),
        };

        assert_eq!(completed_status.phase, Some(InvestigationPhase::Completed));
        assert_eq!(
            completed_status.workflow_state,
            Some(WorkflowState::Resolved)
        );
        assert!(completed_status.error.is_none());
        // started_at and job_name preserved from Running phase
        assert_eq!(
            completed_status.started_at,
            Some("2026-04-18T10:00:01Z".to_string())
        );
        assert_eq!(
            completed_status.job_name,
            Some("inv-test-complete".to_string())
        );
        assert!(completed_status.completed_at.is_some());

        // Verify serialization produces correct JSON for K8s API
        let json = serde_json::to_value(&completed_status).unwrap();
        assert_eq!(json["phase"], "completed");
        assert_eq!(json["workflow_state"], "resolved");

        // Valid workflow transition: Investigating → Resolved
        assert!(WorkflowState::Investigating.is_valid_transition(&WorkflowState::Resolved));
    }

    #[test]
    fn test_deterministic_job_name_prevents_duplicates() {
        // Story 2.1 AC4: Operator restart resilience depends on deterministic Job names.
        // The same investigation_id MUST always produce the same Job name.
        let investigation = create_test_investigation("payment-spike-001", "default");
        let config = InvestigatorConfig::default();

        let job1 = build_investigator_job(&investigation, &config).unwrap();
        let job2 = build_investigator_job(&investigation, &config).unwrap();

        assert_eq!(job1.metadata.name, job2.metadata.name);
        assert_eq!(
            job1.metadata.name,
            Some("inv-payment-spike-001".to_string())
        );

        // Different investigation produces different Job name
        let investigation2 = create_test_investigation("cpu-spike-002", "default");
        let job3 = build_investigator_job(&investigation2, &config).unwrap();
        assert_ne!(job1.metadata.name, job3.metadata.name);
        assert_eq!(job3.metadata.name, Some("inv-cpu-spike-002".to_string()));
    }

    #[test]
    fn test_owner_reference_prevents_orphaned_jobs() {
        // Story 2.1 AC2: Owner reference ensures K8s GC deletes Jobs
        // when Investigation CR is deleted, preventing orphaned Jobs.
        let investigation = create_test_investigation("test-orphan", "default");
        let config = InvestigatorConfig::default();

        let job = build_investigator_job(&investigation, &config).unwrap();

        let owner_refs = job.metadata.owner_references.as_ref().unwrap();
        assert_eq!(owner_refs.len(), 1);
        assert_eq!(owner_refs[0].kind, "Investigation");
        assert_eq!(owner_refs[0].name, "test-orphan");
        // controller=true ensures this is the controlling owner
        assert_eq!(owner_refs[0].controller, Some(true));
    }

    #[test]
    fn test_get_job_failure_message() {
        use k8s_openapi::api::batch::v1::{JobCondition, JobStatus};

        let mut job = Job::default();

        // No status = no message
        assert!(get_job_failure_message(&job).is_none());

        // Status with no conditions = no message
        job.status = Some(JobStatus {
            conditions: None,
            ..Default::default()
        });
        assert!(get_job_failure_message(&job).is_none());

        // Status with non-failed condition = no message
        job.status = Some(JobStatus {
            conditions: Some(vec![JobCondition {
                type_: "Complete".to_string(),
                status: "True".to_string(),
                message: Some("Job completed".to_string()),
                ..Default::default()
            }]),
            ..Default::default()
        });
        assert!(get_job_failure_message(&job).is_none());

        // Status with failed condition = message extracted
        job.status = Some(JobStatus {
            conditions: Some(vec![JobCondition {
                type_: "Failed".to_string(),
                status: "True".to_string(),
                message: Some("BackoffLimitExceeded".to_string()),
                ..Default::default()
            }]),
            ..Default::default()
        });
        assert_eq!(
            get_job_failure_message(&job),
            Some("BackoffLimitExceeded".to_string())
        );
    }
}
