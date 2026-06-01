# Beeper Demo Environment

Uses the [OpenTelemetry Astronomy Shop](https://github.com/open-telemetry/opentelemetry-demo)
as a real-world polyglot microservices application for Beeper to monitor and investigate.

## Architecture

16+ microservices (Go, Python, Java, .NET, Rust, C++, etc.) forming an e-commerce
application with built-in fault injection via feature flags.

**Signal flow:**
```
OTel Astronomy Shop → OTel Collector → Beeper Operator (:9090 ingestion)
                                            ↓
                                    Investigation CRDs → Investigator Jobs
```

## Prerequisites

- Docker (for building images)
- `helm` 3.x
- `kind` (installed automatically by `make demo-cluster`)
- ~12GB RAM allocated to Docker Desktop (Settings → Resources → Memory)
- `ANTHROPIC_API_KEY` env var — required for investigations to complete (without it, SLO monitoring and fault injection still work, but investigator jobs will fail)

## Quick Start

```bash
# Set your LLM API key (required for investigations)
export ANTHROPIC_API_KEY=sk-ant-...

# One command: kind cluster + build images + deploy Beeper + OTel demo
make demo-up

# Open the UIs
make demo-ui
# → Beeper UI:     http://localhost:5050
# → Operator API:  http://localhost:8081   (e.g. /api/v1/ingestion/stats)
# → OTel Shop:     http://localhost:8080
# → Feature Flags: http://localhost:8080/feature
# → Jaeger:        http://localhost:16686

# Inject a fault
make demo-fault FAULT=payment-failure

# Check fault status
make demo-fault-status

# Recover
make demo-recover

# Tear down (deletes kind cluster)
make demo-down
```

## Full Demo Script — 3/3 Validation (NFR8)

The acceptance demo: a `payment-failure` fault produces an evidence-backed
investigation, **3 consecutive times without restarting the cluster**. Budget
**~10–15 min per cycle** (EWMA warmup ~2–3 min after deploy/operator restart;
investigation ~5–10 min once the fault fires).

**One-time setup (~10–15 min):**
```bash
export ANTHROPIC_API_KEY=sk-ant-...      # or configure the local LLM (see values-dev.yaml)
make demo-up                             # cluster + images + Beeper + OTel demo
make demo-ui                             # port-forwards (keep this running in a second terminal)
```

**Per cycle (repeat 3×, no cluster restart between cycles):**

1. **Verify ingestion is live** — operator is receiving telemetry:
   ```bash
   curl -s localhost:8081/api/v1/ingestion/stats | jq '{metrics_received, logs_received}'
   # both should be > 0 and climbing
   ```
2. **Await EWMA warmup (~2–3 min)** — detectors need a baseline before they can
   fire. On the first cycle, wait after `demo-up`; later cycles stay warm.
   ```bash
   curl -s localhost:8081/api/v1/ingestion/stats | jq '{ewma_warmup_samples, ewma_warmup_minimum, active_metric_detectors}'
   # ewma_warmup_samples >= ewma_warmup_minimum  ⇒ warmed up
   ```
3. **Inject the fault:**
   ```bash
   make demo-fault FAULT=payment-failure      # sets paymentFailure → 100%
   ```
4. **Watch the investigation (~5–10 min)** — at `http://localhost:5050/investigations/`
   a new investigation appears (status flips Pending → Running → Completed; steps
   stream in live via SSE). It must **complete**, not stall.
5. **Verify the conclusion is evidence-backed** (the `[H]` judgement):
   - Root cause references the **payment service** and an **error-rate / charge
     failure** signal — not a generic guess.
   - Evidence steps show **real Prometheus metrics and Loki log excerpts** (actual
     values/log lines), and **zero "insufficient data" / "no data" results** while
     the fault is active.
6. **Recover:**
   ```bash
   make demo-recover                          # all flags → DISABLED/off
   ```
7. **Confirm clean** before the next cycle:
   ```bash
   make demo-fault-status                     # every fault [off]
   ```

**Pass criteria (NFR8):** all 3 cycles produce a completed, evidence-backed
investigation that names the payment service, with no "insufficient data" results
while faulted, and no cluster restart in between.

> **Tip:** keep `make demo-ui` running throughout — its port-forwards (incl. the
> operator API on :8081) are how the Beeper UI and the `curl` checks above reach
> the in-cluster services.

## Available Faults

Faults are injected via [flagd](https://flagd.dev/) feature flags. The built-in
load generator (Locust) continuously sends traffic, so failures appear immediately.

| Fault | Flag (`defaultVariant` when enabled) | Effect |
|-------|------|--------|
| `payment-failure` | `paymentFailure` → `100%` | Payment charge method returns errors |
| `cart-failure` | `cartFailure` → `on` | Cart EmptyCart method fails |
| `kafka-problems` | `kafkaQueueProblems` → `on` | Kafka queue overload + consumer delays |
| `slow-images` | `imageSlowLoad` → `10sec` | Deliberate image loading delays |
| `high-cpu` | `adHighCpu` → `on` | Ad service high CPU consumption |

> Flag names + variants match the OTel demo's flagd config exactly (verified
> against the live cluster). The `make demo-fault FAULT=<name>` mapping and these
> are guarded by `demo/tests/test_demo_automation.py`.

## SLOs

ServiceLevel CRDs are deployed for key services:

| Service | Target | Window |
|---------|--------|--------|
| checkout | 99.9% availability | 30m |
| cart | 99.9% availability | 30m |
| frontend | 99.5% availability | 30m |
| product-catalog | 99.9% availability | 30m |

> **Note:** The payment service has no SLO — it lacks suitable server-side request metrics.
> Payment errors are detected via the OTLP log error rate detection path instead.

## Makefile Targets

| Target | Description |
|--------|-------------|
| **`demo-up`** | **Full setup: cluster + images + Beeper + OTel demo** |
| **`demo-down`** | **Delete kind cluster entirely** |
| `demo-cluster` | Create kind cluster (installs kind if missing) |
| `demo-build` | Build Docker images + load into kind |
| `demo-beeper` | Deploy Beeper Helm chart (operator, UI, Qdrant, CRDs) |
| `demo-helm-repo` | Add OTel Helm chart repo (run once) |
| `demo-deploy` | Deploy OTel demo + SLOs + Source CRD |
| `demo-teardown` | Uninstall OTel demo + Beeper releases |
| `demo-status` | Show pods, services, SLOs |
| `demo-logs` | Tail demo pod logs |
| `demo-fault FAULT=<name>` | Enable a fault via feature flag |
| `demo-recover` | Reset all feature flags |
| `demo-fault-status` | Show current flag states |
| `demo-fault-list` | List available faults |
| `demo-ui` | Port-forward Beeper UI (:5050), operator API (:8081), Shop (:8080), Jaeger (:16686) |

## Files

```
demo/
├── otel-demo-values.yaml       # Helm values overlay (collector → Beeper)
├── k8s/
│   ├── slo-checkout.yaml       # ServiceLevel CRDs
│   ├── slo-cart.yaml
│   ├── slo-frontend.yaml
│   ├── slo-productcatalog.yaml
│   └── source-prometheus.yaml  # Source CRD pointing at demo Prometheus
└── README.md
```
