//! Notification engine subsystem
//!
//! This module contains the notification outbox worker for durable
//! notification delivery with exponential backoff retry.

pub mod outbox;

pub use outbox::{OutboxWorker, OutboxError};
