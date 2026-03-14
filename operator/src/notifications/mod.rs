//! Notification engine subsystem
//!
//! This module contains the notification outbox worker for durable
//! notification delivery with exponential backoff retry, and the
//! routing rules engine for severity, service, quiet hours, and
//! SLO-weighted urgency evaluation.

pub mod outbox;
pub mod router;

pub use outbox::{OutboxWorker, OutboxError};
pub use router::{NotificationRouter, RouterError, RoutingDecision, Severity, SloContext};
