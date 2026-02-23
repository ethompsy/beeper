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
use kube::{Api, Client, Resource};
use serde_json::json;
use tracing::{debug, info};

use crate::crds::{Investigation, InvestigationPhase, InvestigationStatus};

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
}

impl InvestigatorConfig {
    /// Build config from environment variables, falling back to defaults.
    ///
    /// Reads:
    /// - `BEEPER_PROMETHEUS_URL` → `prometheus_url` (default: empty)
    /// - `BEEPER_LOKI_URL` → `loki_url` (default: empty)
    pub fn from_env() -> Self {
        Self {
            prometheus_url: std::env::var("BEEPER_PROMETHEUS_URL").unwrap_or_default(),
            loki_url: std::env::var("BEEPER_LOKI_URL").unwrap_or_default(),
            ..Default::default()
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
    let env_vars = vec![
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
                    optional: Some(false),
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
    let status = InvestigationStatus {
        phase: Some(InvestigationPhase::Pending),
        started_at: None,
        completed_at: None,
        job_name: None,
        error: None,
        message: None,
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
        started_at: Some(now),
        completed_at: None,
        job_name: Some(job_name.to_string()),
        error: None,
        message: None,
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
    let current_status = investigation.status.as_ref().cloned().unwrap_or_default();

    let status = InvestigationStatus {
        phase: Some(InvestigationPhase::Completed),
        started_at: current_status.started_at,
        completed_at: Some(now),
        job_name: current_status.job_name,
        error: None,
        message: None,
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
    let current_status = investigation.status.as_ref().cloned().unwrap_or_default();

    let status = InvestigationStatus {
        phase: Some(InvestigationPhase::Failed),
        started_at: current_status.started_at,
        completed_at: Some(now),
        job_name: current_status.job_name,
        error: Some(error_message.to_string()),
        message: None,
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

    #[test]
    fn test_investigator_config_from_env() {
        // Set env vars before calling from_env
        std::env::set_var("BEEPER_PROMETHEUS_URL", "http://prometheus:9090");
        std::env::set_var("BEEPER_LOKI_URL", "http://loki:3100");

        let config = InvestigatorConfig::from_env();

        assert_eq!(config.prometheus_url, "http://prometheus:9090");
        assert_eq!(config.loki_url, "http://loki:3100");
        // Other fields should be defaults
        assert_eq!(config.image, "beeper/investigator:latest");

        // Clean up env
        std::env::remove_var("BEEPER_PROMETHEUS_URL");
        std::env::remove_var("BEEPER_LOKI_URL");
    }

    #[test]
    fn test_investigator_config_from_env_defaults_when_unset() {
        // Ensure vars are unset
        std::env::remove_var("BEEPER_PROMETHEUS_URL");
        std::env::remove_var("BEEPER_LOKI_URL");

        let config = InvestigatorConfig::from_env();

        assert_eq!(config.prometheus_url, "");
        assert_eq!(config.loki_url, "");
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

        let loki_url = env_vars
            .iter()
            .find(|e| e.name == "LOKI_URL")
            .unwrap();
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

        let loki_url = env_vars
            .iter()
            .find(|e| e.name == "LOKI_URL")
            .unwrap();
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
