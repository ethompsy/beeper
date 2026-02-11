//! Beeper Operator Library
//!
//! This crate provides the core functionality for the Beeper Kubernetes operator.
//! The operator watches for anomalies detected by observability sources and spawns
//! investigator pods to analyze and generate root cause hypotheses.

/// CRD definitions for Beeper resources
pub mod crds;

/// Controllers for reconciling Beeper resources
pub mod controllers;

/// Health check endpoints
pub mod health;

/// Streaming data ingestion endpoints
pub mod ingestion;

/// Data source adapters (Prometheus, Loki)
pub mod sources;

/// Re-export commonly used types
pub use crds::{Investigation, InvestigationSpec, InvestigationStatus, Source, SourceSpec, SourceStatus};
pub use controllers::{run_investigation_controller, run_source_controller};
pub use health::{health_router, start_health_server};
pub use ingestion::{ingestion_router, IngestionBuffer, IngestionData};
pub use sources::{LokiClient, LokiError, PrometheusClient, PrometheusError};
