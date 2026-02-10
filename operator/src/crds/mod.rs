//! CRD definitions for Beeper resources
//!
//! This module contains the Kubernetes Custom Resource Definitions
//! for Beeper's Source and Investigation resources.

pub mod investigation;
pub mod source;

pub use investigation::{
    Investigation, InvestigationPhase, InvestigationSpec, InvestigationStatus, Severity,
};
pub use source::{Source, SourceSpec, SourceStatus, SourceType};
