# RFC 0001 — Per-service-incident investigations (with cross-service correlation)

- **Status:** Draft v2 — core model accepted; sub-questions open (see §9)
- **Date:** 2026-06-03 (v2 incorporates review decisions Q-A…Q-E)
- **Author:** Eng (with Claude)
- **Affects:** Operator (`detection/consumer.rs`, investigation lifecycle), Investigator (signal scope, cross-incident correlation, progress/checkpointing), Investigation CRD, demo viability on resource-constrained / local-LLM setups
- **Supersedes (as the root cause of):** the symptom-level patches Q5 (metric/service filtering), Q7 (service-attribution dedup), the 3σ→4σ default, and **Q8 (blunt investigator-Job concurrency cap — now explicitly dropped, see §6/Q-E)**.

## 1. Summary

Today the operator opens **one Investigation per anomaly signal**, deduplicated only by an in-memory time cooldown. It should instead open **one active Investigation per service incident** — a single investigation that collates *all* anomalous signals for a service while that service is unhealthy — **and those investigations should be aware of one another and correlate across services** (a downstream service's errors are often *caused* by an upstream service's incident; that causal link is the most valuable output Beeper can produce).

Concurrency across *different* failing services is expected; concurrency for the *same* service is a bug. This RFC defines the model, a phased plan, a progress-based (not wall-clock) liveness model with checkpointing, and the cross-service correlation capability.

## 2. Problem (grounded in code + live evidence)

- **Creation** — `operator/src/detection/consumer.rs`: every `AnomalyEvent` past a time cooldown creates an Investigation CRD + investigator Job.
- **Dedup** — `anomaly_fingerprint = event.service` checked against an **in-memory** `CooldownTracker` (600 s). **No check for an already-active Investigation.**
- **Two structural failures:**
  1. **Duration ≫ cooldown.** A full investigation takes ~12–15 min (~7 sequential LLM steps); cooldown is 10 min → a still-unhealthy service re-fires duplicates **before the first finishes**.
  2. **In-memory cooldown is not durable** — lost on operator restart → immediate re-fire for every service.
- **Live blast radius (2026-06-02/03):** ~22–27 services trip at warmup → with the overlap, **48–106 concurrent investigator pods**, which **self-DOSed the host** (RAM free → ~78 MB / ~18 GB compressed) → local qwen throttled ~37→~15 tok/s, Ollama overloaded → LLM calls exceeded the client window → `litellm.APIConnectionError` → retries restart the slow calls → **0/48 completed**. Isolated, the same pipeline completes fine (RCA step ~70 s). **The system was failing itself, not hitting a model limit.**
- **The investigator already gathers a service's signals broadly** (`signal_correlation.py`: PromQL/LogQL across app/platform/infra/business layers for the service) — so the redundancy is purely upstream, in *creation granularity*.

Q5/Q7/4σ/Q8 each shaved a layer; the unit of work is still wrong, so the pressure keeps resurfacing. **This is the one recurring issue.**

## 3. Target model

| Aspect | Current | Target |
|---|---|---|
| Unit of investigation | per anomaly signal | **per service incident** |
| Concurrent investigations | anomalies × (duration ÷ cooldown overlap) | **= # distinct currently-failing services** |
| New signal for a service already under investigation | spawns a duplicate | **folded into the open investigation** (Phase 2) |
| New incident after the prior resolved | re-fires on cooldown regardless | fresh investigation (gated on terminal state + re-open debounce) |
| Restart durability | in-memory (lost) | **derived from API state** |
| **Relationship between investigations** | **none** | **causal correlation across services** (Phase 3) |
| Liveness / stuck handling | none | **progress-watchdog + checkpointing** (not wall-clock) |
| Max concurrency | unbounded (needed Q8 cap) | naturally bounded by reality — **no separate cap (Q-E)** |

### 3.1 Incident lifecycle

```
   anomaly for service S, no active Investigation(S)
   ──────────────────────────────────────────────►  OPEN (Pending→Running)
                                                        │
   further anomalies for S while OPEN ── attach signal ─┤ (no new CRD; bump severity if higher — Q-C)
   correlate against other active incidents ───────────┤ (Phase 3)
                                                        ▼
                        investigator completes ─────►  RESOLVED (Completed/Failed)
                                                        │
   anomaly for S after RESOLVED + re-open debounce ─────┘ ► new incident → OPEN
```

## 4. Design — phases

### Phase 1 — Active-investigation guard (small, high-impact)
In `consumer.rs`, before creating an Investigation for service S:
1. Query the K8s API for a non-terminal (Pending/Running) Investigation for S (via a new `beeper.dev/service: <normalized>` label selector; cache "active services" briefly in-memory to bound API calls).
2. If one exists → **skip** (the running one already gathers S's signals).
3. Else create it (apply the label; record namespace(s) — Q-D).
4. Re-scope the cooldown to a **post-resolution re-open debounce** (clock starts when the investigation goes terminal, not at creation).

Collapses per-signal→per-service-incident; fixes duration>cooldown overlap; survives restarts (state is in the API, not memory); makes max-concurrency = # failing services. **No CRD schema change.**

### Phase 2 — Signal attachment
Fold subsequent anomalies for an open incident into the Investigation CR (`spec.conditions: []` / `status.observed_signals: []`) so it *aggregates* the incident. On a higher-severity signal, **bump the open CR's severity and merge** (Q-C — "the low signal may be the canary"). UI can then show "N signals on this incident."

### Phase 3 — Cross-service incident correlation (first-class goal, per Q-A)
**Motivating example (from review):** an active investigation finds DB connection-pool exhaustion. A second service starts erroring; those errors are *DB timeouts caused by* the pool exhaustion. Beeper must surface that **B's incident is downstream of A's** — not two unrelated investigations.

Mechanism (builds on existing pieces):
- The investigator can now **`list` Investigations** (the Q6 RBAC fix already enables this) → it can discover other **active/recent** incidents.
- The **Service Topology** step already produces a `service_dependency_chain`; combine it with temporal overlap to find candidate upstream incidents.
- When B's anomalous signals (e.g. DB timeouts) point at a dependency A that has a concurrent/recent incident, the investigator **links them**: B's investigation references A's as the probable upstream root cause; A's can reference its downstream blast radius.
- **Representation (to design):** a `related_investigations` / causal-edge field on the CR (e.g. `caused_by: <investigation-id>`, `downstream: [...]`), enabling an incident graph / "parent incident" view.

This is a real capability and likely warrants its **own detailed RFC** (correlation heuristics: dependency direction, temporal windows, signal-type matching like "timeouts to host X" ↔ "X saturation"; how to avoid false links; UI for the incident graph). Captured here as the accepted direction; Phase 3 design TBD.

### Liveness: progress-watchdog + checkpointing (replaces blind TTL — per Q-B)
"Stuck" ≠ wall-clock age. An investigation may legitimately take a while. Define **stuck = not making progress**, detected via activity signals:
- the investigator emits a **heartbeat / step-progress** (already logs per-step) and records `last_progress_at`;
- progress = active LLM calls (litellm) and/or Qdrant interactions and/or step transitions.

If `now - last_progress_at` exceeds a **no-progress** threshold (not a total-duration cap), the operator treats it as stuck — **but first triggers a checkpoint: the investigator dumps in-progress work (gathered signals, partial analysis, completed steps) to durable storage (Qdrant `investigations` collection)** so nothing is lost, then the CR goes Failed-(stalled) and the service can re-open (resuming from the checkpoint if feasible). No work is discarded on timeout.

## 5. What does NOT change (Phase 1)
- Investigator signal-gathering breadth (already per-service, 4 layers).
- The Pending→Running→Completed/Failed state machine (we *read* phase; Phase 1 adds no states).
- SSE/UI entity model (strictly fewer, simpler investigations).

## 6. Resolved decisions (review 2026-06-03)
- **Q-A → Phases 1 + 2, and add Phase 3 cross-service correlation as a first-class goal.** Investigators must be cross-service-aware and surface causal links between incidents.
- **Q-B → No blind timeout.** "Stuck" = no-progress (LLM/Qdrant/step activity). On stall, **checkpoint in-progress work to durable storage** before failing; never lose investigator work.
- **Q-C → Bump severity + merge the signal** into the existing investigation (canary principle).
- **Q-D → Identity = normalized bare service name; record namespace(s) (a list) on the event/CR** for context and multi-namespace services.
- **Q-E → Truly per-service; drop the blunt concurrency cap (Q8).** The per-service guard *is* the concurrency control.

## 7. Test strategy
- **Operator unit (cargo):** guard suppresses a 2nd investigation while one is non-terminal for S; allows a new one once terminal + past re-open debounce; restart still suppresses (reads API, no in-memory state); no-progress watchdog triggers checkpoint→Failed; namespace list recorded on the event.
- **Investigator unit (pytest):** severity bump+merge on higher-severity signal; cross-service correlation links B→A when B's signals implicate dependency A with a concurrent incident; checkpoint writes partial work to Qdrant.
- **Integration (AD-8, live):** warmup opens ≤ one investigation per anomalous service; concurrent pods ≈ # failing services (not 48–106); host RAM healthy; investigations complete on local qwen; the DB-pool→downstream scenario produces two *linked* incidents, not two orphans.

## 8. Rollout
1. **Phase 1** (active guard + drop Q8 cap + re-scope cooldown) — behind `BEEPER_DETECTION_ACTIVE_GUARD` (default on). Re-run the live demo profile; confirm concurrency = # failing services and completion on local qwen.
2. **Phase 2** (signal attachment + severity bump/merge).
3. **Liveness watchdog + checkpointing.**
4. **Phase 3** (cross-service correlation) — own RFC.

## 9. Open sub-questions (need answers before/within each phase)
- **S1 (Phase 3):** correlation representation — `caused_by` edge + `downstream[]` on the CR, vs a separate "Incident" parent object grouping member investigations? (Affects CRD schema + UI.)
- **S2 (Phase 3):** correlation heuristics — how strict before asserting causality (dependency-direction + temporal-overlap + signal-type match)? How to present low-confidence links without overclaiming?
- **S3 (liveness):** no-progress threshold value + how the investigator surfaces a heartbeat the operator can observe (CR `status.last_progress_at` updated each step? a Qdrant write?). Is checkpoint-resume in scope, or checkpoint-for-forensics only (v1)?
- **S4 (Phase 2):** CR shape for multiple signals (`spec.conditions[]` vs `status.observed_signals[]`) — spec (desired/trigger) vs status (observed) semantics.
- **S5 (Phase 1):** label-selector + active-services cache invalidation details; behaviour if the API list call fails (fail-open = create, or fail-closed = skip?). **[RESOLVED in Phase 1 impl, PR #17: fail-open.]**

## 10. Detection-quality follow-ups — the baseline isn't actually calm (Q9–Q11)

Live runs of the merged Phase 1 guard (2026-06-03/04) surfaced that **Phase 1 alone does not produce a calm baseline.** On a clean-slate restart, ~**every** service (23/25) opened one investigation simultaneously. Investigating *why* (the guard correctly capped it at 1/service) revealed these are **warmup false-positives, not real incidents** — and that on a single node with a local LLM, ~23 concurrent investigations re-starve the host (RAM free → ~92 MB, 0/23 complete). Three findings, in priority order:

### Q10 — Zero-variance → 1e6σ false anomalies *(highest impact, smallest fix)*
`ewma.rs::update()` (lines ~81–88): once warm, if a metric had near-zero variance (a flat gauge/steady rate — extremely common) and then changes *at all*, it emits `deviation = 1e6` → instant anomaly. So the first wobble of nearly every service's flat metrics fires a false anomaly → ~one per service → the 23.
**Fix:** require a **minimum absolute deviation** (and/or N corroborating consecutive breaches) before firing on a (near-)zero-variance stream, instead of an unconditional 1e6σ. Expected to sharply cut the warmup burst.

### Q11 — EWMA state is in-memory; every operator restart re-warms → false-positive burst
The detectors live in a `HashMap` rebuilt in `DetectionConsumer::run()`, so **every operator restart wipes all baselines** and re-warms from scratch — and each re-warm produces a Q10 burst. Operator restarts are routine (rolling updates, crashes, scaling). During this session's repeated restarts, this burst recurred every time.
**Fix options:** persist/warm-start EWMA state (e.g. periodic snapshot to Qdrant/configmap), **or** a startup grace period that suppresses firing until streams have a stable variance estimate (cheaper; no persistence). Pairs with Q10.

### Q9 — No *global* concurrency limit (refines Q-E) *(safety net, not the root cause)*
Phase 1 bounds duplicates **per service** but not **global** concurrent investigations. A genuine wide outage (or, today, the Q10/Q11 false-positive burst) → ~#services concurrent investigator pods → on a single node + local LLM, RAM starvation. The "blunt cap" dropped under Q-E is, for **this resource class**, legitimately needed — but as a **work-queue that processes N at a time and *defers* (not drops) the rest**, not a blind anomaly-dropper.
**Resolution of the tension:** Fix Q10/Q11 first (then the baseline is genuinely calm and local qwen handles the few *real* investigations); keep Q9's work-queue as a **safety net** for true wide outages on resource-constrained nodes. On a real cluster + cloud LLM, per-service-only (no global cap) is correct — so make the global limit **opt-in/config-gated**, default off, recommended on for local/single-node.

**Priority:** Q10 → Q11 → Q9. With Q10+Q11, the recurring "investigation flood / qwen self-DOS" is addressed at its true source (false anomalies), making the local-qwen 3/3 witnessable; Q9 is defence-in-depth. These are detection-quality items distinct from the per-service-incident *granularity* model above, but share the goal of a calm, trustworthy baseline.
