# RFC 0001 — Per-service-incident investigations

- **Status:** Draft (for review)
- **Date:** 2026-06-03
- **Author:** Eng (with Claude)
- **Affects:** Operator (`detection/consumer.rs`), Investigation CRD lifecycle, Investigator (signal scope), demo viability on resource-constrained / local-LLM setups
- **Supersedes (as the root cause of):** the symptom-level patches Q5 (metric/service filtering), Q7 (service-attribution dedup), the 3σ→4σ default, and Q8 (unbounded investigator-Job concurrency). Those remain useful defence-in-depth but do not address the underlying granularity flaw.

## 1. Summary

Today the operator opens **one Investigation per anomaly signal**, deduplicated only by an in-memory time cooldown. It should instead open **one active Investigation per service incident** — a single investigation that collates *all* anomalous signals for a service while that service is unhealthy, and closes/re-opens on incident boundaries. Concurrency across *different* failing services is expected and fine; concurrency for the *same* service is not.

This RFC proposes the model change, a phased implementation (a small, high-impact "active-investigation guard" first), and the lifecycle/edge-case decisions that need sign-off before coding.

## 2. Problem

### 2.1 Current behaviour (grounded in code)

- **Creation** — `operator/src/detection/consumer.rs`: every `AnomalyEvent` that passes a time cooldown creates an Investigation CRD + investigator Job.
- **Dedup** — `anomaly_fingerprint(event) = event.service` (consumer.rs:279) checked against an **in-memory** `CooldownTracker` (`recent: HashMap<service, Instant>`, default 600 s). There is **no check for an already-active Investigation** for the service.
- **Investigator** — `investigator/.../steps/signal_correlation.py` already generates PromQL/LogQL across 4 layers (app / platform / infra / business) **for the whole service**. So the investigator is *already* designed to collate a service's signals; the redundancy is created upstream.

### 2.2 Why this is the root cause

Two structural failures fall out of "per-anomaly + time-cooldown, no active guard":

1. **Duration ≫ cooldown overlap.** A full investigation takes ~12–15 min (≈7 sequential LLM steps); the cooldown is 10 min. So a still-unhealthy service **re-fires a second investigation before the first finishes** → overlapping duplicates of the *same* incident. Measured live: ~22–27 services trip at warmup → with this overlap, **48–106 concurrent investigator pods**.
2. **In-memory cooldown is not durable.** An operator restart forgets `recent` and immediately re-fires for every service.

### 2.3 Observed blast radius (live, 2026-06-02/03)

The duplicate flood **self-DOSes the host**: dozens of investigator pods exhausted RAM (free → ~78 MB, ~18 GB compressed), which throttled the local LLM (qwen3:8b: ~37 → ~15 tok/s) and overloaded Ollama → LLM calls exceeded the client window → `litellm.APIConnectionError` → retries restarted the slow calls → **0 of 48 investigations completed**. Isolated (one investigation, memory freed) the same pipeline completes fine (RCA step ~70 s). **The system was failing itself, not hitting a model limit.**

Q5/Q7/4σ/Q8 each shaved a layer of this (fewer false trips, deduped attribution, a blunt concurrency cap) — but the unit of work is still wrong, so the pressure keeps resurfacing. This is "the one issue that keeps coming up."

## 3. Target model

| Aspect | Current | Target |
|---|---|---|
| Unit of investigation | one per anomaly signal | **one active per service incident** |
| Concurrent investigations | anomalies × (duration ÷ cooldown overlap) | **= # distinct currently-failing services** |
| New signal for a service already under investigation | spawns a duplicate | **folded into the open investigation** |
| New incident on a service after the prior one resolved | (re-fires on cooldown expiry regardless) | **a fresh investigation opens** (gated on terminal state) |
| Restart durability | in-memory (lost on restart) | **derived from API state** (Investigation CRDs) |
| Max concurrency | unbounded | naturally bounded by reality (subsumes Q8) |

### 3.1 Incident lifecycle (proposed state machine)

```
        anomaly for service S, no active Investigation(S)
   ────────────────────────────────────────────────────────►  OPEN  (Pending→Running)
                                                                 │
   further anomalies for S while OPEN ──► attach signal/condition │ (no new CRD)
                                                                 ▼
                                          investigator completes ──► RESOLVED (Completed/Failed)
                                                                 │
   anomaly for S after RESOLVED + re-open debounce window ───────┘  ► new incident → OPEN
```

- **OPEN guard:** "is there a non-terminal (Pending/Running) Investigation for S?" replaces the duplicate-suppression role of the time cooldown.
- **Re-open debounce:** a (short) cooldown still applies *after* an investigation reaches a terminal state, so a flapping service doesn't immediately re-open. This is the cooldown's *correct* remaining job.

## 4. Design

### 4.1 Phase 1 — Active-investigation guard (small, high-impact)

In `consumer.rs`, before creating an Investigation for service S:
1. Query the K8s API for non-terminal Investigations for S (label/field selector on a new `beeper.dev/service` label, or list+filter on `spec.service` + `status.phase ∉ {Completed, Failed}`).
2. If one exists → **skip** (debug-log "service S already under investigation"); the running investigation already gathers S's signals.
3. Else create it, and apply a `beeper.dev/service: <normalized>` label for cheap lookup.
4. Keep the cooldown but **re-scope it to post-resolution re-open debounce** (start the clock when an investigation goes terminal, not when it's created).

Properties: collapses per-signal→per-service-incident; fixes duration>cooldown overlap; survives restarts (state is in the API, not memory); makes max-concurrency = # failing services (subsumes Q8); with Q5/4σ cutting false trips, the flood is gone *at the source*. ~No CRD schema change required.

**Cost:** an API list/get per anomaly (mitigate with a label selector + a short in-memory cache of "active services").

### 4.2 Phase 2 (optional) — True signal attachment

Fold subsequent anomalies for an open incident into the Investigation CR (e.g. `spec.conditions: []` / `status.observed_signals: []`) so it *aggregates* the incident rather than just deduping. The investigator already queries the whole service, so Phase 1 captures most of the value; Phase 2 improves fidelity (the RCA prompt sees every observed symptom, not just the first) and the UI can show "5 signals on this incident."

### 4.3 What does NOT change

- The investigator's signal-gathering (already per-service across 4 layers).
- The Pending→Running→Completed/Failed CRD state machine (we *read* phase; we don't add states in Phase 1).
- SSE/UI (one investigation per service is strictly fewer, simpler entities).

## 5. Edge cases / decisions to confirm

1. **Service identity.** The guard keys on the (Q7-normalized) service name. Confirm normalization is the right identity (e.g. should namespace be part of identity for multi-namespace?). Proposed: normalized bare service name.
2. **Cross-service incidents.** A failing dependency can make several services anomalous → several investigations. That's acceptable (one per service) — the investigator already records a `service_dependency_chain`. Do we later want a "parent incident" grouping? Out of scope for Phase 1.
3. **Long-running / stuck investigations.** If an investigation hangs, the guard would suppress *all* new investigations for that service indefinitely. Need a **max investigation age / TTL** (operator marks it Failed after N min) so the service can re-open. Propose a configurable timeout (e.g. 20 min).
4. **Re-open debounce window.** Value? Proposed: reuse `BEEPER_DETECTION_COOLDOWN_SECS` but measured from terminal time.
5. **Severity escalation.** If a `low` investigation is open and a `critical` signal arrives for the same service, do we (a) ignore, (b) bump the open investigation's severity, (c) open a new one? Proposed: (b) bump severity on the open CR; no new CR.
6. **Backwards-compat / migration.** Pure behaviour change in the operator; no data migration. Existing CRDs unaffected.

## 6. Test strategy

- **Operator unit (cargo):** guard suppresses a 2nd investigation while one is Pending/Running for S; allows a new one once terminal; re-open debounce respected; restart (no in-memory state) still suppresses because it reads the API; TTL marks a stuck investigation Failed.
- **Integration (AD-8, manual/live):** warmup on the demo cluster opens **≤ one investigation per anomalous service**, concurrent pods ≈ # failing services (not 48–106); inject `payment-failure` → exactly one `payment` investigation; host RAM stays healthy; investigations complete on local qwen.

## 7. Rollout

1. Land Phase 1 behind the existing config (guard on by default; `BEEPER_DETECTION_ACTIVE_GUARD=false` to fall back).
2. Re-run the live demo profile; confirm concurrency = # failing services and completion on local qwen.
3. Decide on Phase 2 (signal attachment) and the optional "parent incident" grouping separately.

## 8. Open questions (need sign-off before implementation)

- Q-A: Phase 1 only, or Phase 1 + Phase 2 together?
- Q-B: Stuck-investigation TTL value (proposed 20 min) and behaviour (mark Failed → allow re-open).
- Q-C: Severity-escalation behaviour (proposed: bump open CR).
- Q-D: Service identity = normalized bare name (drop namespace)? Confirm.
- Q-E: Keep Q8's blunt concurrency cap as a backstop, or rely solely on the per-service guard?
