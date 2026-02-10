//! Data source adapters for Beeper
//!
//! This module contains clients for querying observability data sources
//! like Prometheus and Loki.

pub mod prometheus;

pub use prometheus::{Credentials, PrometheusClient, PrometheusError};
