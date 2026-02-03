//! Beeper Operator Library
//!
//! This crate provides the core functionality for the Beeper Kubernetes operator.
//! The operator watches for anomalies detected by observability sources and spawns
//! investigator pods to analyze and generate root cause hypotheses.

/// CRD definitions for Beeper resources
pub mod crds {
    // Placeholder for future CRD definitions
    // - Source CRD
    // - Investigation CRD
    // - LLMProvider CRD
}

/// Controllers for reconciling Beeper resources
pub mod controllers {
    // Placeholder for future controllers
    // - Source controller
    // - Investigation controller
}

/// Adapters for observability data sources
pub mod adapters {
    // Placeholder for future adapters
    // - Prometheus adapter
    // - Loki adapter
}

#[cfg(test)]
mod tests {
    #[test]
    fn it_works() {
        assert!(true);
    }
}
