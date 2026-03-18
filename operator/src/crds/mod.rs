//! CRD definitions for Beeper resources
//!
//! This module contains the Kubernetes Custom Resource Definitions
//! for Beeper's Source, Investigation, ServiceLevel, NotificationChannel, and Repository resources.

pub mod investigation;
pub mod notification_channel;
pub mod repository;
pub mod servicelevel;
pub mod source;

pub use investigation::{
    Investigation, InvestigationPhase, InvestigationSpec, InvestigationStatus, Severity,
    WorkflowState,
};
pub use notification_channel::{
    ChannelType, NotificationChannel, NotificationChannelCondition, NotificationChannelSpec,
    NotificationChannelStatus, QuietHoursConfig, RoutingConfig,
};
pub use repository::{
    BranchPolicy, CodingStandards, Repository, RepositoryCondition, RepositoryProvider,
    RepositorySpec, RepositoryStatus,
};
pub use servicelevel::{
    BudgetPolicyAction, BurnRateAlert, ErrorBudgetPolicy, ObjectiveSpec, ServiceLevel,
    ServiceLevelCondition, ServiceLevelSpec, ServiceLevelStatus, SliSpec, SliType,
};
pub use source::{Source, SourceSpec, SourceStatus, SourceType};
