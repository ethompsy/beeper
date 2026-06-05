# RFC 0002 — Detection significance gating (Q13c)

- **Status:** Draft — design for review (no code yet)
- **Date:** 2026-06-05
- **Author:** Eng (with Claude)
- **Affects:** Operator (`detection/ewma.rs`, `detection/metrics.rs`, `detection/mod.rs` config)
- **Builds on:** RFC 0001 §10 (Q9–Q12) and the Q13a/Q13b work in PR #21 (infra/static denylist + opt-in absolute stddev floor). This RFC covers **only Q13c**: the residual that neither the denylist nor a global absolute floor can fix.

## 1. Summary

The detection-quality "noise onion" has been peeled from **38,000 → ~11** warmup false-positive investigations across Q5 → Q7 → Q10 → Q12 → Q13a (all live-measured except Q13a, which is unit-tested). The last layer is **near-zero / idle counter-rate streams** that fire on small movements. This RFC argues that the correct fix is **not** another global magnitude constant — count-rate noise and small-but-real GC-duration signal *overlap in absolute magnitude across different units*, so any single floor either lets the noise through or blinds the signal. It proposes a **unit-free temporal-persistence gate** as the primary mechanism, with an **optional unit-aware magnitude gate** as a secondary refinement, both config-gated and default-no-op. It gates the implementation behind a **Phase 0 live characterization** so we choose the mechanism from measured data, not a hypothesis (per the Q10 lesson — see §7).

## 2. Problem (grounded in code + the prior live classification)

After RFC 0001 §10 and PR #21, the metric path is:

- **Q12** (`metrics.rs::process`): cumulative counters (`*_total`/`*_count`/`*_sum`) detect on a **per-second rate**; histogram `*_bucket` is skipped; counter resets return `None`.
- **Q10** (`ewma.rs::update`): the effective stddev has a **relative** floor — `REL_STDDEV_FLOOR (0.05) * |mean|`.
- **Q13a** (PR #21): denylist extended with `otelcol_`, `jvm_memory_limit`, `jvm_memory_init`. GC (`jvm_gc_*`, `dotnet_gc_*`) and dynamic occupancy (`jvm_memory_used`/`committed`) are deliberately **kept**.
- **Q13b** (PR #21): an **absolute** stddev floor (`BEEPER_DETECTION_ABS_STDDEV_FLOOR`), default `0.0` = off.

**The residual class.** On a near-zero / idle stream the relative floor is `0.05 × ~0 ≈ 0`, so a small movement reads as a large σ-deviation and fires. From the prior live classification (post-Q12 baseline of 11), the residual counter-rate offenders were `redis_keyspace_misses_total` (~0.2 ± 0.1 /s), `nginx_connections_handled_total` (~0 /s) — and `otelcol_process_cpu_seconds_total`, now removed by Q13a.

**Why a global floor can't finish the job (the core finding).** Q13b's absolute floor is **unit-dependent**. The two things we must tell apart live at overlapping absolute magnitudes but in different units:

| Stream | Unit (post-Q12 rate) | Healthy → incident | Verdict |
|---|---|---|---|
| `redis_keyspace_misses_total` | events/s | 0.2 → 3 (noise) | suppress |
| `jvm_gc_collection` / `*_count` | events/s | 0.5 → 8 (real) | keep |
| `jvm_gc_duration_seconds_sum` | **seconds/s** | 0.005 → 0.2 (real, ~20 % in GC) | keep |

A floor large enough to quiet the redis blip (~0.5 in events/s) is **100×** the entire GC-duration signal range (0.005→0.2 s/s) → blinds it. A floor small enough to preserve GC-duration (~0.005) does nothing to the redis blip. **No single scalar separates them** because they are different physical quantities that happen to share a numeric neighbourhood. This is exactly the "don't lose GC as a symptom" concern raised in review, and it is real.

## 3. Goals / non-goals

**Goals**
- Quiet the residual idle-counter false positives.
- **Never** blind a real symptom — explicitly including GC pressure (frequency *and* duration), memory leaks, and "canary" low-signal anomalies (per RFC 0001 review Q-C: a low signal may be the first symptom — we suppress *noise*, not *small real signals*).
- Avoid "blind config" — prefer mechanisms whose single knob is *universally meaningful*, not a per-metric magic number.
- Keep it config-gated and **default-no-op** (backward compatible); recommend values for local/single-node.

**Non-goals**
- Re-litigating Q12/Q13a/Q13b (settled).
- A global concurrency cap (that is Q9 / RFC 0001 §10).
- Per-metric hand-tuned thresholds maintained by humans (rejected as blind config — see §5).

## 4. Candidate mechanisms

### A. Temporal persistence ("for:" dwell) — *unit-free*
Fire only after the σ-deviation has held for **K consecutive samples** (a dwell, à la Prometheus `for:`).
- **Pros:** unit-free; one universally-meaningful knob (scrapes / duration); standard alerting practice; kills single-scrape transients; **provably preserves sustained signals** (GC pressure, leaks, and every demo fault are sustained for minutes).
- **Cons:** (1) interacts with EWMA adaptation — the baseline would adapt *toward* the anomaly during the dwell and could absorb a moderate step before K is reached, so the candidate window must **freeze (or slow) baseline adaptation while a breach streak is in progress**; (2) adds detection latency `+K × scrape_interval`; (3) only helps if the residual noise is **transient** — it does nothing for genuinely *sustained* low-level wobble.

### B. Unit-aware magnitude gate — *uses the metric's declared unit*
Suppress an anomaly whose **absolute** movement is below a minimum keyed by the metric's unit, parsed from the OTel name suffix (`…_seconds_(sum|count|total)` → time, `…_bytes_…` → size, else → count). E.g. count-rate min ≈ 1 event/s; seconds-rate min ≈ tiny; bytes-rate min ≈ scale-appropriate.
- **Pros:** targets *material* insignificance directly ("3 cache misses/s is not an incident"); uses the **declared** unit rather than per-metric config, so it is principled, not blind; catches *sustained* low-wobble that persistence (A) misses.
- **Cons:** needs a small unit→threshold table (some config); unit parsing is naming-convention heuristic; does not suppress transients that are *large* in magnitude (acceptable — those merit a look, and A catches them).

### C. Hybrid (A primary + B secondary) — **recommended shape**
Persistence as the default mechanism (unit-free, GC-safe, standard); the unit-aware gate as an optional second filter for any residual sustained-low-wobble. Both default to no-op (`dwell = 1`, gates = `0`).

### D. Rejected alternatives
- **Bigger global absolute floor** — the §2 finding: cannot separate the units. (Q13b stays opt-in for homogeneous-unit deployments only.)
- **Range-relative / coefficient-of-variation / slow-EWMA** floors — an idle stream has ~no scale of its own, so self-relative measures still fire on the first real blip; added complexity, no separation.

## 5. Recommendation

**Hybrid (C), led by persistence (A) — *contingent on Phase 0* (§7).**

Persistence is the right primary because it is unit-free, is the industry-standard way to express "this must be sustained to matter," and is **provably GC-safe** (a sustained GC-rate climb reaches the dwell and fires; a one-scrape idle blip never does). It also *helps* Q11: warmup wobbles on a freshly-restarted operator rarely persist, so the restart re-warm burst shrinks.

**The contingency matters.** Persistence only works if the residual noise is *transient*. We have **not** yet characterized whether `redis_keyspace_misses`/`nginx_connections_handled` fire from sparse single-scrape rate blips (→ A wins) or from sustained low wobble (→ lead with B). We learned in Q10 not to ship on a hypothesis (predicted 23→handful; measured 23→21). So §7 Phase 0 measures this first and §5's "A primary" flips to "B primary" if the data says sustained.

**"No blind config":** A's knob is a dwell count (universally meaningful). B's thresholds are keyed by *declared unit*, not per-metric. Neither is a per-series magic number.

## 6. Design sketch (implementation-ready, pending Phase 0)

**A — persistence in `EwmaDetector`:**
- Add `dwell: u64` (default `1` = current behavior) and in-memory `consec_breaches: u64`.
- In `update()`, after computing `deviation > threshold`:
  - breach → `consec_breaches += 1`; **do not adapt** `ewma`/`ewma_var` this sample (freeze baseline so the streak isn't absorbed); return `Some` only when `consec_breaches >= dwell`.
  - non-breach → `consec_breaches = 0`; adapt as today.
  - after a fire → reset `consec_breaches` and resume adaptation (the existing 600 s cooldown dedups re-fires; baseline then migrates to the new normal).
- Counter reset / warmup / `None` from Q12 → treated as non-breach → resets the streak.
- Config: `BEEPER_DETECTION_DWELL` (default 1). Wire via `MetricDetector::with_dwell` like Q13b's `with_abs_stddev_floor`.

**B — unit-aware gate (optional, second filter):**
- A `fn metric_unit(name) -> Unit { Seconds | Bytes | Count }` classifier on the name suffix.
- A config map `BEEPER_DETECTION_MIN_RATE_{COUNT,SECONDS,BYTES}` (defaults `0` = off). Before firing, require `|observed - expected| >= min_for(unit)`.
- Lives in `metrics.rs` (it knows the metric name) rather than `ewma.rs` (unit-agnostic).

**Interactions:** Q10 relative floor and Q13b absolute floor stay (σ-stage). Persistence and the gate are *post-σ*. Q12 reset → non-breach. Q11 in-memory caveat still applies to the new counters (acceptable; persistence reduces the restart burst). Cooldown unchanged.

## 7. Phase 0 — live characterization (prerequisite, the Q10 lesson)

Before writing code, redeploy the operator (Phase 1 + Q10 + Q12 + Q13a) and, for the residual counter-rate streams, capture over ~10 min: raw values, computed per-second rates, and per-sample σ-deviation. Classify each firing as **transient** (sparse single-scrape rate blip) or **sustained** (persistent low wobble crossing 4σ). Output decides §5:
- mostly transient → ship **A** (dwell 2–3), gate optional.
- mostly sustained → ship **B** first (unit-aware count floor), add A for transients.

This is the live-measure deferred from the Q13 PR; naming it as a gate keeps us honest about what we know vs. assume.

## 8. Acceptance criteria

- **[T]** `dwell = 1` reproduces current firing exactly (backward compatible).
- **[T]** With `dwell = 2`: a single-scrape transient on a near-zero stream does **not** fire; a ≥2-sample sustained breach **does**.
- **[T]** With `dwell = 2`: a sustained GC-frequency-rate climb (0.5 → 8 /s) fires within the dwell (GC-safety regression, extends PR #21's test).
- **[T]** A Q12 counter reset resets the breach streak (no fire).
- **[T]** (if B ships) a sub-floor **count**-rate movement is suppressed while a numerically-equal **seconds**-unit (GC-duration) movement is not (proves unit-awareness, not a global floor).
- **[H]** **Live (the real proof):** demo faults (payment-failure, slow-images, …) still fire within acceptable latency (`≤ dwell × scrape_interval` added delay), **and** the residual idle-counter investigations stop. Measured warmup baseline reported (target: the residual class → ~0 without losing any injected fault).
- **[O]** Post-deploy warmup false-positive count and mean detection latency.

## 9. Rollout

Config-gated, **default no-op** (`dwell = 1`, gates `0`). Recommend `dwell = 2–3` (+ count gate) for local/single-node demos; leave off (or `dwell = 1`) for a real cluster + cloud LLM where a few extra investigations are cheap. Document in `values-dev` alongside the existing detection knobs. Pairs with RFC 0001 §10 Q9 (global work-queue) as defence-in-depth for true wide outages.

## 10. Open questions

- **Dwell vs. M-of-N.** Strict "K consecutive" is simplest; "M of N" tolerates a scrape gap but adds state. Start consecutive; revisit if scrape jitter causes flaps.
- **Freeze vs. slow adaptation during a streak.** Hard freeze is simplest and correct for short dwells (2–3); a very long dwell with hard freeze could miss a slow ramp — out of scope at recommended dwell values.
- **Unit table source.** Parse from name suffix (proposed) vs. carry the OTel unit field through ingestion (cleaner but a larger change). Start with suffix parsing.
