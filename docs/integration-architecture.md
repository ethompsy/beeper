# Beeper Integration Architecture

## Overview

Beeper is an open-source agentic AI Site Reliability Engineering (SRE) platform deployed as a Kubernetes operator. The system ingests observability data from Prometheus and Loki, detects anomalies, autonomously launches AI-driven investigations, stores findings in a vector database, and surfaces results through a web UI.

This document describes the integration architecture: how each component communicates, what protocols are used, and how data flows through the system.

---

## Components

| Component | Language / Runtime | Role |
|---|---|---|
| **Operator** | Rust (Axum) | K8s operator, ingestion, anomaly detection, CRD management |
| **Investigator** | Python | AI-driven root cause analysis, runs as K8s Job |
| **UI** | Python (Flask) | Web interface for browsing investigations and knowledge |
| **Qdrant** | Native | Vector database for investigations and knowledge base |
| **LLM API** | External (via LiteLLM) | Language model reasoning for the investigator |
| **Prometheus** | External | Metrics source and remote write target |
| **Loki** | External | Log source and push target |
| **Kubernetes API** | External | CRD management, Job lifecycle, Secret access |

---

## High-Level Data Flow

```
Prometheus/Loki → Operator (ingest + detect) → K8s Job (investigate) → Qdrant (store) → UI (display)
                                                          ↓
                                                     LLM API (reason)
```

Observability signals enter the operator through either pull-based source adapters or push-based ingestion endpoints. The operator buffers and analyzes incoming data; when an anomaly is detected it creates an Investigation CRD and spawns a Kubernetes Job to run the investigator container. The investigator queries live signals, reasons over them using a tiered LLM strategy, and persists findings to Qdrant. The UI reads from Qdrant and the operator API to present a unified dashboard.

---

## Communication Patterns

### 1. Operator → Investigator

**Pattern:** Kubernetes Job creation (no direct HTTP)

The operator does not communicate with the investigator over a network socket. Instead it uses the Kubernetes API as the coordination layer:

1. The operator detects an anomaly in the buffered signal stream.
2. It creates (or updates) an `Investigation` CRD in the cluster to record the event.
3. It submits a `Job` manifest to the Kubernetes API. The Job spec references the investigator container image and injects context (namespace, source name, investigation ID, Qdrant endpoint, LLM config) as environment variables and volume mounts drawn from Kubernetes `Secret` objects.
4. The investigator pod reads its configuration from the environment at startup and proceeds autonomously.
5. Job completion status is observable through the Kubernetes API; the operator can watch Job events to update the Investigation CRD status.

This design decouples the operator from investigator availability: the operator never blocks on an HTTP response, and failed or retried Jobs do not require operator-side retry logic.

### 2. Investigator → Qdrant

**Pattern:** HTTP REST API via `qdrant-client` Python library

The investigator reads from and writes to two Qdrant collections during an investigation run:

| Operation | Collection | Purpose |
|---|---|---|
| Query (read) | `knowledge` | Retrieve prior research relevant to the current anomaly |
| Upsert (write) | `investigations` | Persist the investigation state, findings, and root cause |
| Upsert (write) | `knowledge` | Store new KB entries derived from the investigation |

All vectors are 1536-dimensional, consistent with OpenAI-compatible embedding models.

### 3. Investigator → LLM API

**Pattern:** HTTP via LiteLLM with tiered model selection and SHA-256 response caching

The investigator uses a three-tier model selection strategy that balances cost against reasoning depth:

| Tier | Model (example) | Trigger |
|---|---|---|
| `screening` | Claude Haiku / GPT-3.5-equivalent | Initial triage and signal filtering |
| `investigation` | Claude Sonnet / GPT-4-equivalent | Structured root cause analysis |
| `deep_rca` | Claude Opus / GPT-4o-equivalent | Complex or unresolved incidents |

LiteLLM provides a unified OpenAI-compatible interface in front of multiple provider backends, allowing model selection to be driven by configuration without code changes.

**Caching:** LLM responses are cached using a SHA-256 hash of the prompt content as the cache key. This prevents duplicate API calls when the same signals recur across investigations, reducing latency and cost.

### 4. Investigator → Prometheus / Loki

**Pattern:** HTTP queries during the investigation run

The investigator issues HTTP queries directly to Prometheus (PromQL) and Loki (LogQL) to gather signals relevant to the anomaly window. These queries are scoped to the time range and service labels of the investigation and supplement the signals already buffered by the operator.

### 5. UI → Qdrant

**Pattern:** HTTP REST API (read-heavy, with selective writes)

The UI reads from all Qdrant collections to populate the dashboard and detail views. It also manages several operator-maintained collections:

| Operation | Collection | Purpose |
|---|---|---|
| Read | `investigations` | List and detail views for investigations |
| Read / Write | `knowledge` | Browse and annotate KB entries |
| Read / Write | `knowledge_versions` | View version history of KB entries |
| Read / Write | `corrections` | Record correction conversations |
| Read / Write | `learning_patterns` | Diff analysis and pattern tracking |
| Read / Write | `service_trust_levels` | Per-service trust configuration |

### 6. UI → Operator API

**Pattern:** HTTP REST (port 8080)

The UI polls the operator's Axum-based management API for operational metadata that is not stored in Qdrant:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/sources` | GET | List configured sources with their current status |
| `/api/v1/health/components` | GET | Per-component health breakdown |
| `/api/v1/ingestion/stats` | GET | Buffer utilization and ingestion throughput |
| `/healthz` | GET | Operator liveness check |
| `/readyz` | GET | Operator readiness check |

### 7. Operator → Prometheus / Loki

**Pattern:** Both pull (source adapters) AND push (streaming ingestion endpoints on port 9090)

The operator integrates with the observability stack in two directions:

**Pull (Source Adapters):** The operator reads `Source` CRDs that describe existing Prometheus and Loki instances. Source adapters poll these instances on a configured interval, fetching metrics and log streams into the operator's internal buffer for anomaly detection.

**Push (Ingestion Endpoints):** The operator exposes a second HTTP server on port 9090 that implements standard ingestion protocols, allowing Prometheus and Loki to push data directly:

| Endpoint | Method | Protocol | Format |
|---|---|---|---|
| `/api/v1/write` | POST | Prometheus remote write | Protocol Buffers + Snappy compression |
| `/loki/api/v1/push` | POST | Loki push | JSON (optional Snappy compression) |

This dual-mode integration means Beeper can be deployed as a passive observer (pull only), an active ingestion target (push only), or both simultaneously.

### 8. Operator → Kubernetes API

**Pattern:** Kubernetes controller/watch pattern

The operator uses the Kubernetes API for its core control-plane responsibilities:

- **Watch** `Source` CRDs to discover and reconfigure data source adapters dynamically.
- **Watch** `Investigation` CRDs to track investigation lifecycle.
- **Create / Update / Delete** `Job` resources to launch investigator instances.
- **Read** `Secret` resources to obtain credentials for Qdrant, LLM APIs, Prometheus, and Loki.

---

## API Reference

### Operator Management API (Port 8080)

```
GET  /api/v1/sources               # List all configured sources with status
GET  /api/v1/health/components     # Component-level health breakdown
GET  /api/v1/ingestion/stats       # Buffer statistics and ingestion metrics
GET  /healthz                      # Liveness probe
GET  /readyz                       # Readiness probe
```

### Operator Ingestion API (Port 9090)

```
POST /api/v1/write                 # Prometheus remote write (protobuf + snappy)
POST /loki/api/v1/push             # Loki push (JSON, optional snappy)
```

### OpenAPI-Defined Endpoints (UI / External Consumers)

These endpoints follow the OpenAPI specification and return errors in RFC 7807 Problem Details format.

```
GET  /investigations               # List investigations
POST /investigations               # Create a new investigation record
GET  /investigations/{id}          # Get a specific investigation by ID
GET  /knowledge                    # List knowledge base entries
POST /knowledge                    # Create a knowledge base entry
GET  /sources                      # List sources
GET  /sources/{name}               # Get a specific source by name
```

**Error format (RFC 7807):**
```json
{
  "type": "https://beeper.dev/errors/not-found",
  "title": "Not Found",
  "status": 404,
  "detail": "Investigation abc123 does not exist",
  "instance": "/investigations/abc123"
}
```

---

## Kubernetes Custom Resource Definitions

### Source CRD (`beeper.dev/v1`)

Describes a data source (Prometheus or Loki instance) that the operator should observe. The operator watches for `Source` resource events and reconfigures its source adapters accordingly.

```yaml
apiVersion: beeper.dev/v1
kind: Source
metadata:
  name: production-prometheus
spec:
  # source-specific configuration fields
```

### Investigation CRD (`beeper.dev/v1`)

Records the lifecycle of an investigation: the triggering anomaly, the spawned Job reference, and the current phase. The operator creates this resource when an anomaly is detected and updates it as the Job progresses.

```yaml
apiVersion: beeper.dev/v1
kind: Investigation
metadata:
  name: investigation-abc123
spec:
  # investigation-specific fields
status:
  phase: Running  # Pending | Running | Succeeded | Failed
```

---

## Qdrant Collections

All vector collections use 1536-dimensional embeddings (OpenAI-compatible). Payload-only collections store structured data without vector search.

| Collection | Type | Contents |
|---|---|---|
| `investigations` | Vector (1536d) | Investigation state, findings, root cause summaries |
| `knowledge` | Vector (1536d) | Knowledge base entries with semantic embeddings |
| `knowledge_versions` | Payload-only | Point-in-time snapshots of knowledge entries |
| `corrections` | Payload-only | Correction conversation threads |
| `learning_patterns` | Payload-only | Diff analysis results and recurring pattern data |
| `service_trust_levels` | Payload-only | Per-service trust scores and configuration |

---

## Deployment Topology

```
┌─────────────────────────────────────────────────────────────────┐
│  Kubernetes Cluster                                             │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Operator Pod                                            │   │
│  │  ┌─────────────────┐   ┌──────────────────────────────┐ │   │
│  │  │  Axum API       │   │  Ingestion Server            │ │   │
│  │  │  :8080          │   │  :9090                       │ │   │
│  │  │  /api/v1/*      │   │  /api/v1/write               │ │   │
│  │  │  /healthz       │   │  /loki/api/v1/push           │ │   │
│  │  │  /readyz        │   └──────────────────────────────┘ │   │
│  │  └────────┬────────┘                                     │   │
│  │           │                                              │   │
│  │  ┌────────▼────────┐   ┌──────────────────────────────┐ │   │
│  │  │  Anomaly        │   │  Source Adapters             │ │   │
│  │  │  Detector       │   │  (pull: Prometheus, Loki)    │ │   │
│  │  └────────┬────────┘   └──────────────────────────────┘ │   │
│  └───────────┼──────────────────────────────────────────────┘   │
│              │  creates Job                                      │
│  ┌───────────▼────────────────────────────────────────────────┐ │
│  │  Investigator Job (ephemeral pod)                          │ │
│  │  - Queries Prometheus / Loki                               │ │
│  │  - Calls LLM API via LiteLLM (tiered: haiku/sonnet/opus)  │ │
│  │  - Reads/writes Qdrant                                     │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌─────────────────────┐   ┌───────────────────────────────┐   │
│  │  UI Pod (Flask)     │   │  Qdrant Pod                   │   │
│  │  - Reads Qdrant     │   │  - investigations             │   │
│  │  - Reads operator   │   │  - knowledge                  │   │
│  │    API :8080        │   │  - knowledge_versions         │   │
│  └─────────────────────┘   │  - corrections                │   │
│                            │  - learning_patterns          │   │
│                            │  - service_trust_levels       │   │
│                            └───────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
  External Prometheus/Loki         External LLM API
  (push or pull)                   (via LiteLLM)
```

---

## Security Considerations

- **Secrets management:** All credentials (Qdrant API keys, LLM API keys, Prometheus/Loki auth tokens) are stored as Kubernetes `Secret` objects and mounted into pods at runtime. The operator reads Secrets via the Kubernetes API; the investigator receives them as environment variables.
- **CRD RBAC:** The operator requires RBAC permissions to watch and manage `Source` and `Investigation` CRDs, create and monitor `Job` resources, and read `Secret` objects within its configured namespaces.
- **Network policy:** The ingestion server (port 9090) should be accessible from Prometheus and Loki within the cluster. The management API (port 8080) should be restricted to the UI and cluster operators. The investigator Job requires egress to Qdrant, Prometheus, Loki, and the LLM API endpoint.
- **LLM response caching:** SHA-256-keyed caching of LLM responses reduces exposure of sensitive signal data to external APIs by avoiding redundant calls for identical prompts.

---

## Helm Chart Structure

The `helm/` directory contains the Kubernetes manifests and Helm chart for deploying all components. The chart is expected to manage:

- Operator `Deployment` and associated `ServiceAccount`, `ClusterRole`, and `ClusterRoleBinding`.
- `Service` resources exposing ports 8080 and 9090 for the operator.
- Qdrant `StatefulSet` with persistent volume claims.
- UI `Deployment` and `Service`.
- CRD manifests for `Source` and `Investigation`.
- `ConfigMap` and `Secret` templates for per-environment configuration.

---

*Last updated: 2026-03-08*
