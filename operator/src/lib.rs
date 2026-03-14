//! Beeper Operator Library
//!
//! This crate provides the core functionality for the Beeper Kubernetes operator.
//! The operator watches for anomalies detected by observability sources and spawns
//! investigator pods to analyze and generate root cause hypotheses.

/// API endpoints for UI
pub mod api;

/// Anomaly detection engine
pub mod detection;

/// CRD definitions for Beeper resources
pub mod crds;

/// Controllers for reconciling Beeper resources
pub mod controllers;

/// Health check endpoints
pub mod health;

/// Streaming data ingestion endpoints
pub mod ingestion;

/// Investigator Job building and lifecycle management
pub mod investigator_job;

/// LLM provider configuration and management
pub mod llm;

/// Notification engine — outbox worker and delivery
pub mod notifications;

/// SLO engine — burn rate calculation and alerting
pub mod slo;

/// Data source adapters (Prometheus, Loki)
pub mod sources;

/// Re-export commonly used types
pub use api::{api_router, api_router_full, api_router_with_llm};
pub use controllers::{
    run_investigation_controller, run_investigation_controller_with_config,
    run_notificationchannel_controller, run_servicelevel_controller, run_source_controller,
};
pub use crds::{
    Investigation, InvestigationSpec, InvestigationStatus, NotificationChannel,
    NotificationChannelSpec, NotificationChannelStatus, ServiceLevel, ServiceLevelSpec,
    ServiceLevelStatus, Source, SourceSpec, SourceStatus,
};
pub use notifications::{NotificationRouter, OutboxError, OutboxWorker, RouterError, RoutingDecision, Severity, SloContext};
pub use health::{health_router, start_health_server};
pub use ingestion::{ingestion_router, IngestionBuffer, IngestionData};
pub use investigator_job::{
    build_investigator_job, is_job_completed, is_job_failed, set_phase_completed, set_phase_failed,
    set_phase_pending, set_phase_running, InvestigatorConfig, InvestigatorJobError,
};
pub use llm::{LlmConfig, LlmConfigError, LlmManager, LlmProvider};
pub use sources::{LokiClient, LokiError, PrometheusClient, PrometheusError};
pub use detection::{DetectionConfig, DetectionConsumer, DetectionStats};
pub use slo::{new_slo_cache, run_slo_engine, SloCache, SloCalculationResult};
