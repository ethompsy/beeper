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
- ~4GB RAM available for the demo pods
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

## Available Faults

Faults are injected via [flagd](https://flagd.dev/) feature flags. The built-in
load generator (Locust) continuously sends traffic, so failures appear immediately.

| Fault | Flag | Effect |
|-------|------|--------|
| `payment-failure` | `paymentServiceFailure` | Payment charge method returns errors |
| `cart-failure` | `cartServiceFailure` | Cart EmptyCart method fails |
| `kafka-problems` | `kafkaQueueProblems` | Kafka queue overload + consumer delays |
| `slow-images` | `imageSlowLoad` | Deliberate image loading delays |
| `high-cpu` | `adServiceHighCpu` | Ad service high CPU consumption |

## SLOs

ServiceLevel CRDs are deployed for key services:

| Service | Target | Window |
|---------|--------|--------|
| checkoutservice | 99.9% availability | 30m |
| cartservice | 99.9% availability | 30m |
| paymentservice | 99.95% availability | 30m |
| frontend | 99.5% availability | 30m |
| productcatalogservice | 99.9% availability | 30m |

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
| `demo-ui` | Port-forward Beeper UI, Shop, Jaeger |

## Files

```
demo/
├── otel-demo-values.yaml       # Helm values overlay (collector → Beeper)
├── k8s/
│   ├── slo-checkout.yaml       # ServiceLevel CRDs
│   ├── slo-cart.yaml
│   ├── slo-payment.yaml
│   ├── slo-frontend.yaml
│   ├── slo-productcatalog.yaml
│   └── source-prometheus.yaml  # Source CRD pointing at demo Prometheus
└── README.md
```
