//! CRD definitions for Beeper resources
//!
//! This module contains the Kubernetes Custom Resource Definitions
//! for Beeper's Source, Investigation, and ServiceLevel resources.

pub mod investigation;
pub mod servicelevel;
pub mod source;

pub use investigation::{
    Investigation, InvestigationPhase, InvestigationSpec, InvestigationStatus, Severity,
};
pub use servicelevel::{
    BurnRateAlert, ObjectiveSpec, ServiceLevel, ServiceLevelCondition, ServiceLevelSpec,
    ServiceLevelStatus, SliSpec, SliType,
};
pub use source::{Source, SourceSpec, SourceStatus, SourceType};
