//! CRD definitions for Beeper resources
//!
//! This module contains the Kubernetes Custom Resource Definitions
//! for Beeper's Source, Investigation, ServiceLevel, and NotificationChannel resources.

pub mod investigation;
pub mod notification_channel;
pub mod servicelevel;
pub mod source;

pub use investigation::{
    Investigation, InvestigationPhase, InvestigationSpec, InvestigationStatus, Severity,
};
pub use notification_channel::{
    ChannelType, NotificationChannel, NotificationChannelCondition, NotificationChannelSpec,
    NotificationChannelStatus, QuietHoursConfig, RoutingConfig,
};
pub use servicelevel::{
    BudgetPolicyAction, BurnRateAlert, ErrorBudgetPolicy, ObjectiveSpec, ServiceLevel,
    ServiceLevelCondition, ServiceLevelSpec, ServiceLevelStatus, SliSpec, SliType,
};
pub use source::{Source, SourceSpec, SourceStatus, SourceType};
