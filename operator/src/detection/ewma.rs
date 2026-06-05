//! Exponentially Weighted Moving Average (EWMA) detector
//!
//! Implements adaptive baseline learning using EWMA for anomaly detection.
//! Uses only standard library f64 operations — no external crates needed.

use super::types::AnomalySignal;

/// EWMA-based anomaly detector
///
/// Relative noise floor for the anomaly threshold. A (near-)constant stream is
/// treated as having an effective stddev of at least this fraction of its mean,
/// so a small wobble on a flat metric is not reported as a huge deviation (Q10).
/// With the default 4σ threshold this means a flat metric must move ~20% of its
/// level to fire — small enough to catch real step-changes, large enough to
/// ignore the post-warmup jitter that previously triggered a false anomaly per
/// service.
const REL_STDDEV_FLOOR: f64 = 0.05;

/// Tracks an exponentially weighted moving average and variance for a single
/// time series. Fires an anomaly signal when a new value deviates beyond
/// `threshold` standard deviations from the expected mean.
#[derive(Debug, Clone)]
pub struct EwmaDetector {
    /// Smoothing factor (0.0-1.0). Higher = faster adaptation.
    alpha: f64,
    /// Standard deviation multiplier for anomaly threshold.
    threshold: f64,
    /// Minimum samples before detection activates.
    min_samples: u64,
    /// Current exponentially weighted mean.
    ewma: f64,
    /// Current exponentially weighted variance.
    ewma_var: f64,
    /// Number of samples processed.
    samples: u64,
    /// Absolute floor on the effective stddev (Q13b). `0.0` = off (default).
    /// Unit-dependent — see `DetectionConfig::abs_stddev_floor`. Set via
    /// [`EwmaDetector::with_abs_stddev_floor`].
    abs_stddev_floor: f64,
}

impl EwmaDetector {
    /// Create a new EWMA detector with the given parameters.
    pub fn new(alpha: f64, threshold: f64, min_samples: u64) -> Self {
        Self {
            alpha,
            threshold,
            min_samples,
            ewma: 0.0,
            ewma_var: 0.0,
            samples: 0,
            abs_stddev_floor: 0.0,
        }
    }

    /// Set an absolute floor on the effective stddev (Q13b). Fluent so existing
    /// `new()` call sites are unchanged. A non-zero floor quiets near-zero
    /// streams; `0.0` (default) is a no-op. See `DetectionConfig::abs_stddev_floor`
    /// for the unit caveat.
    pub fn with_abs_stddev_floor(mut self, floor: f64) -> Self {
        self.abs_stddev_floor = floor.max(0.0);
        self
    }

    /// Update the detector with a new value.
    ///
    /// Returns `Some(AnomalySignal)` if the value is anomalous,
    /// `None` if normal or still in warmup.
    ///
    /// Anomaly check uses the OLD mean and variance (before incorporating
    /// the new value) so that a single spike doesn't inflate the variance
    /// it's measured against.
    pub fn update(&mut self, value: f64) -> Option<AnomalySignal> {
        // Guard against NaN/Infinity inputs that would permanently poison the detector
        if !value.is_finite() {
            return None;
        }

        self.samples += 1;

        if self.samples == 1 {
            // First sample: initialize mean, no variance yet
            self.ewma = value;
            return None;
        }

        let diff = value - self.ewma;
        let old_stddev = self.ewma_var.sqrt();

        // Check for anomaly BEFORE updating statistics.
        //
        // Use a *relative noise floor*: a (near-)constant stream is treated as
        // having an effective stddev of at least `REL_STDDEV_FLOOR * |mean|`,
        // so a tiny wobble on a flat metric no longer reads as a near-infinite
        // deviation. This replaces the previous `stddev == 0 && any change =>
        // 1e6σ` rule, which fired a false anomaly on the first wobble of every
        // flat gauge / steady rate after warmup — the dominant source of the
        // warmup "investigation flood" (Q10). A real step-change still produces
        // a large deviation and fires; a small wobble does not.
        //
        // A stream flat at *exactly* zero has a zero floor and does not fire
        // from the metric detector (effective_stddev == 0 guard); genuine
        // zero-baseline error spikes are covered by the log error-rate detector.
        // Effective stddev = max(observed, relative floor, absolute floor).
        // The relative floor (Q10) quiets flat *non-zero* metrics; the optional
        // absolute floor (Q13b, off by default) quiets near-*zero* streams where
        // 5% of ~0 is still ~0. The absolute floor is unit-dependent and so
        // opt-in — see DetectionConfig::abs_stddev_floor.
        let effective_stddev = old_stddev
            .max(REL_STDDEV_FLOOR * self.ewma.abs())
            .max(self.abs_stddev_floor);
        let anomaly = if self.samples > self.min_samples && effective_stddev > 0.0 {
            let deviation = diff.abs() / effective_stddev;
            if deviation > self.threshold {
                Some(AnomalySignal {
                    observed: value,
                    expected: self.ewma,
                    stddev: effective_stddev,
                    deviation,
                })
            } else {
                None
            }
        } else {
            None
        };

        // Update EWMA statistics after anomaly check
        self.ewma += self.alpha * diff;
        self.ewma_var = (1.0 - self.alpha) * (self.ewma_var + self.alpha * diff * diff);

        anomaly
    }

    /// Get the current EWMA mean.
    pub fn mean(&self) -> f64 {
        self.ewma
    }

    /// Get the number of samples processed.
    pub fn sample_count(&self) -> u64 {
        self.samples
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_spike_detected() {
        let mut detector = EwmaDetector::new(0.2, 3.0, 10);

        // Feed steady state values
        for _ in 0..20 {
            assert!(detector.update(50.0).is_none());
        }

        // Large spike should trigger anomaly
        let signal = detector.update(200.0);
        assert!(signal.is_some(), "Spike should be detected");
        let signal = signal.unwrap();
        assert!(signal.observed > signal.expected);
        assert!(signal.deviation > 3.0);
    }

    #[test]
    fn test_drop_detected() {
        let mut detector = EwmaDetector::new(0.2, 3.0, 10);

        // Feed steady state at 100
        for _ in 0..20 {
            assert!(detector.update(100.0).is_none());
        }

        // Large drop should trigger anomaly
        let signal = detector.update(0.0);
        assert!(signal.is_some(), "Drop should be detected");
        let signal = signal.unwrap();
        assert!(signal.observed < signal.expected);
        assert!(signal.deviation > 3.0);
    }

    #[test]
    fn test_steady_state_no_false_positives() {
        let mut detector = EwmaDetector::new(0.2, 3.0, 10);

        // Feed steady state values with minor variance
        let values = [
            50.0, 51.0, 49.0, 50.5, 49.5, 50.2, 49.8, 50.1, 49.9, 50.0, 50.3, 49.7, 50.1, 49.9,
            50.2, 49.8, 50.0, 50.1, 49.9, 50.0,
        ];

        for &v in &values {
            assert!(
                detector.update(v).is_none(),
                "Steady state value {} should not trigger anomaly",
                v
            );
        }
    }

    #[test]
    fn test_warmup_no_premature_firing() {
        let mut detector = EwmaDetector::new(0.2, 3.0, 10);

        // During warmup, even large values should not fire
        detector.update(50.0);
        for i in 1..10 {
            let result = detector.update(50.0 + (i as f64) * 100.0);
            assert!(
                result.is_none(),
                "Should not fire during warmup (sample {})",
                i + 1
            );
        }
    }

    #[test]
    fn test_baseline_adapts_after_sustained_shift() {
        let mut detector = EwmaDetector::new(0.2, 3.0, 10);

        // Establish baseline at 50
        for _ in 0..20 {
            detector.update(50.0);
        }

        // Shift to 100 — first few may fire, but it should adapt
        let mut fired_count = 0;
        for _ in 0..100 {
            if detector.update(100.0).is_some() {
                fired_count += 1;
            }
        }

        // After many samples at 100, it should have adapted
        // The last values should not fire
        let late_fires: usize = (0..10).filter(|_| detector.update(100.0).is_some()).count();
        assert_eq!(
            late_fires, 0,
            "After sustained shift, baseline should have adapted (fired {} times during shift, {} late)",
            fired_count, late_fires
        );
    }

    #[test]
    fn test_first_sample_initializes_mean() {
        let mut detector = EwmaDetector::new(0.2, 3.0, 10);
        detector.update(42.0);
        assert_eq!(detector.mean(), 42.0);
        assert_eq!(detector.sample_count(), 1);
    }

    #[test]
    fn test_nan_input_ignored() {
        let mut detector = EwmaDetector::new(0.2, 3.0, 10);

        // Establish baseline
        for _ in 0..20 {
            detector.update(50.0);
        }
        let mean_before = detector.mean();
        let count_before = detector.sample_count();

        // NaN should be silently ignored
        assert!(detector.update(f64::NAN).is_none());
        assert_eq!(detector.mean(), mean_before);
        assert_eq!(detector.sample_count(), count_before);

        // Detector should still work normally after NaN
        assert!(detector.update(50.0).is_none());
    }

    #[test]
    fn test_infinity_input_ignored() {
        let mut detector = EwmaDetector::new(0.2, 3.0, 10);

        for _ in 0..20 {
            detector.update(50.0);
        }

        assert!(detector.update(f64::INFINITY).is_none());
        assert!(detector.update(f64::NEG_INFINITY).is_none());

        // Should still detect real anomalies
        let signal = detector.update(500.0);
        assert!(signal.is_some());
    }

    #[test]
    fn test_production_warmup_30_samples() {
        // Validates the production default: min_samples=30
        // Samples 1-30 must NOT fire even with large deviations
        let mut detector = EwmaDetector::new(0.2, 3.0, 30);

        detector.update(50.0); // sample 1: initialize mean
        for i in 1..30 {
            // Feed wildly varying values during warmup
            let value = 50.0 + (i as f64) * 100.0;
            let result = detector.update(value);
            assert!(
                result.is_none(),
                "Should not fire during 30-sample warmup (sample {})",
                i + 1
            );
        }

        // Sample 31+: after warmup, a spike SHOULD be detectable
        // First establish a brief stable baseline post-warmup
        for _ in 0..10 {
            detector.update(50.0);
        }
        let signal = detector.update(5000.0);
        assert!(signal.is_some(), "Post-warmup spike should be detected");
    }

    // --- Q10: zero/near-zero-variance must not fire on a tiny wobble ---

    #[test]
    fn test_flat_metric_tiny_wobble_no_false_positive() {
        // A perfectly flat metric (stddev == 0 after warmup) that wobbles by a
        // negligible amount must NOT fire. Previously this hit the
        // `stddev==0 => 1e6σ` rule and fired a false anomaly — the dominant
        // cause of the per-service warmup investigation flood (Q10).
        let mut detector = EwmaDetector::new(0.2, 4.0, 30);
        for _ in 0..40 {
            assert!(detector.update(1000.0).is_none());
        }
        // 0.1% wobble on a flat metric — must be ignored.
        assert!(
            detector.update(1001.0).is_none(),
            "tiny wobble on a flat metric must not fire (Q10)"
        );
    }

    #[test]
    fn test_flat_metric_real_stepchange_still_fires() {
        // The fix must NOT blind us: a large step-change on a flat metric still
        // fires (the relative noise floor is small).
        let mut detector = EwmaDetector::new(0.2, 4.0, 30);
        for _ in 0..40 {
            assert!(detector.update(1000.0).is_none());
        }
        let signal = detector.update(2000.0); // +100% step
        assert!(
            signal.is_some(),
            "a real step-change on a flat metric must still fire"
        );
        // Deviation is finite/meaningful, not the old sentinel 1e6.
        assert!(signal.unwrap().deviation < 1e6);
    }

    // --- Q13b: opt-in absolute stddev floor for near-zero streams ---

    #[test]
    fn test_abs_floor_suppresses_near_zero_wobble() {
        // Without a floor, a flat near-zero stream fires on a tiny blip because
        // the relative floor (5% of a ~0 mean) is itself ~0. A count-scale
        // absolute floor quiets it. Same input, two detectors → isolates the floor.
        let run = |floor: f64| {
            let mut d = EwmaDetector::new(0.2, 4.0, 30).with_abs_stddev_floor(floor);
            for _ in 0..40 {
                d.update(0.2); // flat ~0.2/sec idle counter rate
            }
            d.update(0.6) // a 0.4 wobble — meaningless on an idle stream
        };
        assert!(
            run(0.0).is_some(),
            "no floor: tiny near-zero blip fires (the residual noise class)"
        );
        assert!(
            run(0.5).is_none(),
            "abs floor 0.5: tiny near-zero blip is suppressed (Q13b)"
        );
    }

    #[test]
    fn test_gc_frequency_rate_still_fires_with_abs_floor() {
        // GC-safety regression. GC *frequency* (collections/sec, via Q12 rate) is
        // count-scale, so a count-scale absolute floor does NOT blind it — heavy
        // GC still fires. This locks in the requirement that quieting idle
        // counters must never hide GC pressure (a real cross-service incident
        // symptom). NOTE: GC *duration* rate (seconds/sec) is small-magnitude and
        // a count-scale floor would mask it — that unit limitation is why the
        // floor is opt-in, and the general case is tracked as Q13c.
        let mut d = EwmaDetector::new(0.2, 4.0, 30).with_abs_stddev_floor(0.5);
        for _ in 0..40 {
            d.update(0.5); // steady ~0.5 GC collections/sec
        }
        let signal = d.update(8.0); // GC storm: 8 collections/sec
        assert!(
            signal.is_some(),
            "heavy GC (count-scale rate spike) must still fire even with the abs floor"
        );
    }
}
