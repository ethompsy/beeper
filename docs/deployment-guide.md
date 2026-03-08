# Beeper Deployment Guide

## Overview

Beeper is an open-source agentic AI SRE platform that runs on Kubernetes. It uses the operator pattern to manage investigations into your observability data, automatically querying Prometheus metrics and Loki logs to diagnose issues using LLM-powered agents.

This guide covers everything needed to deploy Beeper in a Kubernetes environment, from prerequisites through production configuration.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Architecture Overview](#architecture-overview)
3. [Quick Start](#quick-start)
4. [Installation](#installation)
5. [Configuration Reference](#configuration-reference)
6. [Configuring Data Sources](#configuring-data-sources)
7. [LLM Provider Configuration](#llm-provider-configuration)
8. [RBAC and Security](#rbac-and-security)
9. [Health and Observability](#health-and-observability)
10. [Ingestion Endpoints](#ingestion-endpoints)
11. [Development Deployment](#development-deployment)
12. [Uninstalling](#uninstalling)
13. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before deploying Beeper, ensure the following are available:

| Requirement | Minimum Version | Notes |
|---|---|---|
| Kubernetes | 1.24+ | Operator uses k8s-openapi v1_30 API features |
| Helm | 3.0+ | Used for packaging and installation |
| kubectl | Any recent | Must be configured against the target cluster |
| LLM API Key | N/A | Anthropic recommended; see [LLM Provider Configuration](#llm-provider-configuration) |

Verify your cluster and tooling:

```bash
kubectl version --client
helm version
kubectl cluster-info
```

---

## Architecture Overview

Beeper deploys the following components into your cluster:

**Operator (Rust)** — The core control plane. Watches CRD resources (`Source`, `Investigation`), manages the lifecycle of investigator jobs, and exposes HTTP endpoints for health checks and streaming ingestion.

**Investigator (Python)** — A short-lived Kubernetes Job spawned per investigation. Queries configured data sources, runs LLM-powered analysis, and writes results back to the investigation status.

**UI (Flask)** — A web interface for viewing investigation results and managing sources.

**Qdrant** — A vector database deployed as a StatefulSet. Stores embeddings generated during investigations for semantic search and retrieval.

```
┌─────────────────────────────────────────────────┐
│                  Kubernetes Cluster             │
│                                                 │
│  ┌──────────────┐      ┌──────────────────────┐ │
│  │  beeper-ui   │      │   beeper-operator    │ │
│  │  (Flask)     │      │   (Rust)             │ │
│  │  port 80     │      │   port 8080 (health) │ │
│  └──────────────┘      │   port 9090 (ingest) │ │
│                        └──────────┬───────────┘ │
│                                   │ spawns      │
│  ┌──────────────┐      ┌──────────▼───────────┐ │
│  │    qdrant    │◄─────│  investigator (Job)  │ │
│  │ (StatefulSet)│      │  (Python, ephemeral) │ │
│  └──────────────┘      └──────────────────────┘ │
└─────────────────────────────────────────────────┘
```

### Kubernetes Resources Created by Helm

| Resource | Kind | Details |
|---|---|---|
| `beeper-operator` | Deployment | 1 replica; 100m–500m CPU, 128–256Mi memory |
| `beeper-ui` | Deployment | 1 replica; 100m–500m CPU, 128–256Mi memory |
| `qdrant` | StatefulSet | 1 replica; 100m–500m CPU, 512Mi–1Gi memory, 10Gi PVC |
| `beeper-operator` | ServiceAccount | Used by the operator pod |
| `beeper-investigator` | ServiceAccount | Used by investigator jobs |
| `beeper-operator` | ClusterRole / ClusterRoleBinding | See [RBAC and Security](#rbac-and-security) |
| `sources.beeper.dev` | CRD | Defines observability data sources |
| `investigations.beeper.dev` | CRD | Defines investigation requests |
| Investigator | Job (per investigation) | Ephemeral; 200m–1000m CPU, 256–512Mi memory |

---

## Quick Start

The fastest path to a running Beeper deployment:

```bash
# 1. Install the Helm chart
helm install beeper ./helm/beeper

# 2. Create the LLM credentials secret
kubectl create secret generic llm-credentials \
  --from-literal=api-key=YOUR_ANTHROPIC_API_KEY

# 3. Register a Prometheus data source
kubectl apply -f - <<EOF
apiVersion: beeper.dev/v1
kind: Source
metadata:
  name: prometheus-main
spec:
  source_type: prometheus
  endpoint: http://prometheus:9090
EOF

# 4. Verify the operator is running
kubectl get pods -l app.kubernetes.io/component=operator
```

---

## Installation

### Step 1 — Install the Helm Chart

From the repository root:

```bash
helm install beeper ./helm/beeper
```

To install into a specific namespace:

```bash
kubectl create namespace beeper
helm install beeper ./helm/beeper --namespace beeper
```

To override values at install time:

```bash
helm install beeper ./helm/beeper \
  --set llm.model=claude-3-haiku \
  --set qdrant.persistence.size=20Gi
```

### Step 2 — Create the LLM Credentials Secret

Beeper reads the LLM API key from a Kubernetes Secret. The secret name and key must match the values in `values.yaml` (defaults: secret name `llm-credentials`, key `api-key`).

For Anthropic (default):

```bash
kubectl create secret generic llm-credentials \
  --from-literal=api-key=YOUR_ANTHROPIC_API_KEY
```

For OpenAI:

```bash
kubectl create secret generic llm-credentials \
  --from-literal=api-key=YOUR_OPENAI_API_KEY
```

For Azure OpenAI:

```bash
kubectl create secret generic llm-credentials \
  --from-literal=api-key=YOUR_AZURE_OPENAI_API_KEY
```

For Ollama, no API key is required. See [LLM Provider Configuration](#llm-provider-configuration).

### Step 3 — Register Data Sources

Apply `Source` CRDs to tell Beeper where to find your observability data. See [Configuring Data Sources](#configuring-data-sources) for full examples.

### Step 4 — Verify the Deployment

```bash
# Check all Beeper pods
kubectl get pods -l app.kubernetes.io/name=beeper

# Check the operator specifically
kubectl get pods -l app.kubernetes.io/component=operator

# Check operator logs
kubectl logs -l app.kubernetes.io/component=operator --follow

# Verify CRDs were installed
kubectl get crds | grep beeper.dev

# Check Qdrant is up
kubectl get pods -l app=qdrant
```

The operator exposes a readiness endpoint. Wait until the operator pod shows `Running` and `1/1 READY` before proceeding.

---

## Configuration Reference

All configuration is managed through `values.yaml`. The following tables document all significant options.

### Operator

```yaml
operator:
  replicaCount: 1
  image:
    repository: ghcr.io/your-org/beeper-operator
    tag: "0.1.0"
    pullPolicy: IfNotPresent
  resources:
    requests:
      cpu: 100m
      memory: 128Mi
    limits:
      cpu: 500m
      memory: 256Mi
```

| Key | Default | Description |
|---|---|---|
| `operator.replicaCount` | `1` | Number of operator replicas (1 recommended; operator uses leader election) |
| `operator.image.repository` | `ghcr.io/...` | Operator container image repository |
| `operator.image.tag` | `0.1.0` | Image tag |

### UI

```yaml
ui:
  replicaCount: 1
  image:
    repository: ghcr.io/your-org/beeper-ui
    tag: "0.1.0"
  service:
    type: ClusterIP
    port: 80
  ingress:
    enabled: false
    # hostname: beeper.example.com
    # tls: ...
```

| Key | Default | Description |
|---|---|---|
| `ui.replicaCount` | `1` | Number of UI replicas |
| `ui.service.type` | `ClusterIP` | Kubernetes service type |
| `ui.service.port` | `80` | Service port |
| `ui.ingress.enabled` | `false` | Enable Ingress resource for external access |

To expose the UI externally, enable the ingress and set a hostname:

```yaml
ui:
  ingress:
    enabled: true
    hostname: beeper.example.com
    annotations:
      kubernetes.io/ingress.class: nginx
    tls:
      - hosts:
          - beeper.example.com
        secretName: beeper-tls
```

### Qdrant

```yaml
qdrant:
  enabled: true
  persistence:
    size: 10Gi
    storageClass: ""  # Uses cluster default
  collections:
    vectorDimension: 1536
  resources:
    requests:
      cpu: 100m
      memory: 512Mi
    limits:
      cpu: 500m
      memory: 1Gi
```

| Key | Default | Description |
|---|---|---|
| `qdrant.enabled` | `true` | Deploy the Qdrant StatefulSet |
| `qdrant.persistence.size` | `10Gi` | PVC size for vector storage |
| `qdrant.persistence.storageClass` | `""` | StorageClass; empty uses cluster default |
| `qdrant.collections.vectorDimension` | `1536` | Embedding vector dimension (must match LLM embedding model) |

Note: `vectorDimension: 1536` is correct for OpenAI `text-embedding-3-small` and Anthropic's embedding outputs. If you switch embedding models, this value must be updated and the collection recreated.

### Investigator Jobs

```yaml
investigator:
  image:
    repository: ghcr.io/your-org/beeper-investigator
    tag: "0.1.0"
  backoffLimit: 2
  ttlSecondsAfterFinished: 3600   # 1 hour
  activeDeadlineSeconds: 1800     # 30 minutes
  resources:
    requests:
      cpu: 200m
      memory: 256Mi
    limits:
      cpu: 1000m
      memory: 512Mi
```

| Key | Default | Description |
|---|---|---|
| `investigator.backoffLimit` | `2` | Number of retry attempts before marking an investigation failed |
| `investigator.ttlSecondsAfterFinished` | `3600` | How long completed job objects are retained before garbage collection |
| `investigator.activeDeadlineSeconds` | `1800` | Maximum duration for a single investigation (30 minutes) |

### LLM

```yaml
llm:
  provider: anthropic
  model: claude-sonnet-4
  apiKeySecret: llm-credentials
  maxTokensPerInvestigation: 100000
  maxConcurrentInvestigations: 5
```

| Key | Default | Description |
|---|---|---|
| `llm.provider` | `anthropic` | LLM provider (`anthropic`, `openai`, `azure`, `ollama`) |
| `llm.model` | `claude-sonnet-4` | Model name; see [LLM Provider Configuration](#llm-provider-configuration) |
| `llm.apiKeySecret` | `llm-credentials` | Name of the Kubernetes Secret holding the API key |
| `llm.maxTokensPerInvestigation` | `100000` | Token budget per investigation |
| `llm.maxConcurrentInvestigations` | `5` | Maximum simultaneous investigator jobs |

### Sources (Default Endpoints)

```yaml
sources:
  prometheus:
    enabled: false
    endpoint: http://prometheus:9090
  loki:
    enabled: false
    endpoint: http://loki:3100
```

These `values.yaml` settings configure default endpoints. Source CRDs (applied via `kubectl apply`) are the primary mechanism for registering sources and support credentials secrets. See [Configuring Data Sources](#configuring-data-sources).

### Security Context

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  fsGroup: 1000
```

All pods run as UID 1000 and are prohibited from running as root. This applies to the operator, UI, investigator jobs, and Qdrant.

---

## Configuring Data Sources

Data sources are registered by applying `Source` custom resources. The operator watches these resources and makes them available to investigator jobs.

### Prometheus Source

```yaml
apiVersion: beeper.dev/v1
kind: Source
metadata:
  name: prometheus-main
spec:
  source_type: prometheus
  endpoint: http://prometheus:9090
```

With authentication:

```yaml
apiVersion: beeper.dev/v1
kind: Source
metadata:
  name: prometheus-main
spec:
  source_type: prometheus
  endpoint: https://prometheus.example.com
  credentials_secret: prometheus-creds
```

The referenced secret should contain the credentials expected by your Prometheus instance (for example, a bearer token or basic auth credentials).

### Loki Source

```yaml
apiVersion: beeper.dev/v1
kind: Source
metadata:
  name: loki-main
spec:
  source_type: loki
  endpoint: http://loki:3100
```

### Managing Sources

```bash
# List all registered sources
kubectl get sources.beeper.dev

# Inspect a source and its status
kubectl describe source prometheus-main

# Remove a source
kubectl delete source prometheus-main
```

---

## LLM Provider Configuration

Beeper supports multiple LLM providers. The provider and model are set in `values.yaml`, and the API key is stored in a Kubernetes Secret.

### Anthropic (Default)

Recommended for production use. Supports the full agentic investigation loop.

```yaml
llm:
  provider: anthropic
  model: claude-sonnet-4  # or claude-3-haiku, claude-opus-4
  apiKeySecret: llm-credentials
```

| Model | Notes |
|---|---|
| `claude-sonnet-4` | Default; balanced capability and cost |
| `claude-3-haiku` | Fastest and lowest cost |
| `claude-opus-4` | Highest capability |

### OpenAI

```yaml
llm:
  provider: openai
  model: gpt-4o  # or gpt-4-turbo
  apiKeySecret: llm-credentials
```

### Azure OpenAI

```yaml
llm:
  provider: azure
  model: azure/your-deployment-name
  apiKeySecret: llm-credentials
```

Create the secret with your Azure OpenAI key:

```bash
kubectl create secret generic llm-credentials \
  --from-literal=api-key=YOUR_AZURE_KEY
```

You may also need to set the Azure endpoint via additional environment variables depending on your configuration.

### Ollama (Local, No API Key)

Ollama allows fully air-gapped deployments with no external API calls.

```yaml
llm:
  provider: ollama
  model: ollama/llama3
```

No API key secret is needed. Ensure your Ollama instance is reachable from within the cluster and update the endpoint configuration accordingly.

---

## RBAC and Security

### Operator ClusterRole

The operator is granted the following cluster-level permissions:

| API Group | Resources | Verbs |
|---|---|---|
| `beeper.dev` | `sources`, `investigations` | get, list, watch, create, update, patch, delete |
| `beeper.dev` | `sources/status`, `investigations/status` | get, update, patch |
| `batch` | `jobs` | get, list, watch, create, update, patch, delete |
| `` (core) | `pods` | get, list, watch |
| `` (core) | `secrets` | get, list, watch |
| `` (core) | `configmaps` | get, list, watch |
| `` (core) | `events` | create, patch |

The operator needs `secrets` access to read LLM credentials and data source credentials before passing them to investigator jobs. No secret data is persisted by Beeper.

### Investigator ServiceAccount

Each investigator job runs under a dedicated ServiceAccount (`beeper-investigator`) with scoped permissions appropriate for reading source configuration and writing investigation results.

### Pod Security

All Beeper components enforce the following security context:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  fsGroup: 1000
```

Pods will fail to start if the container image attempts to run as root.

### Network Security

Beeper for MVP does not include an authentication or authorization layer on its API endpoints. The operator's HTTP ports (8080, 9090) should not be exposed outside the cluster without additional controls such as a network policy or an authenticated ingress.

All data processed by Beeper stays within the cluster. No telemetry or investigation data is sent externally unless your configured LLM provider is an external API (Anthropic, OpenAI, Azure).

### Credentials Management

All secrets are injected via Kubernetes Secrets and are never written to disk or logged. To rotate an LLM API key:

```bash
kubectl create secret generic llm-credentials \
  --from-literal=api-key=NEW_KEY \
  --dry-run=client -o yaml | kubectl apply -f -
```

Running investigator jobs will pick up the new key on their next execution; no operator restart is required.

---

## Health and Observability

The operator exposes health endpoints on port `8080`.

### Liveness Probe

```
GET /healthz
```

Always returns `200 OK`. Used by Kubernetes to determine if the operator process is alive.

### Readiness Probe

```
GET /readyz
```

Returns `200 OK` when the operator has a healthy connection to the Kubernetes API. Returns non-200 during startup or if the API connection is lost. Kubernetes will stop routing traffic to the pod while this probe is failing.

### Component Health

```
GET /api/v1/health/components
```

Returns a JSON payload describing the health status of individual components (Qdrant connectivity, source reachability, etc.). Useful for debugging.

Example:

```bash
kubectl port-forward svc/beeper-operator 8080:8080
curl http://localhost:8080/api/v1/health/components
```

---

## Ingestion Endpoints

The operator accepts streaming observability data on port `9090`. This allows Prometheus and Loki to push data directly to Beeper rather than having Beeper poll them.

### Prometheus Remote Write

```
POST /api/v1/write
```

Configure your Prometheus instance to remote-write to the operator service:

```yaml
# prometheus.yml (snippet)
remote_write:
  - url: http://beeper-operator:9090/api/v1/write
```

### Loki Push

```
POST /loki/api/v1/push
```

Configure Promtail or Alloy to push logs to the operator:

```yaml
# promtail config (snippet)
clients:
  - url: http://beeper-operator:9090/loki/api/v1/push
```

### Backpressure Responses

| HTTP Status | Meaning |
|---|---|
| `200 OK` | Data accepted |
| `429 Too Many Requests` | Rate limit exceeded; retry with backoff |
| `503 Service Unavailable` | Internal buffer full; reduce send rate |

Clients should implement exponential backoff when receiving `429` or `503` responses.

---

## Development Deployment

### Helm with Dev Values

A `values-dev.yaml` file is provided with settings appropriate for local or development clusters (reduced resource requests, debug logging, etc.):

```bash
helm install beeper ./helm/beeper -f ./helm/beeper/values-dev.yaml
```

### Docker Compose (Qdrant Only)

For local development without a Kubernetes cluster, a Docker Compose configuration is provided that runs only Qdrant with persistent storage:

```bash
docker compose up -d
```

Qdrant will be available at:
- HTTP API: `http://localhost:6333`
- gRPC: `localhost:6334`

Data is persisted to a named Docker volume across restarts.

When running locally, the operator and investigator can be run directly as processes targeting the local Qdrant instance and a kubeconfig pointing at a local cluster (such as kind or minikube).

### Building Images Locally

To build and load images into a local kind cluster:

```bash
# Build images
docker build -t beeper-operator:dev ./operator
docker build -t beeper-investigator:dev ./investigator
docker build -t beeper-ui:dev ./ui

# Load into kind
kind load docker-image beeper-operator:dev
kind load docker-image beeper-investigator:dev
kind load docker-image beeper-ui:dev

# Install with local image tags
helm install beeper ./helm/beeper \
  --set operator.image.repository=beeper-operator \
  --set operator.image.tag=dev \
  --set operator.image.pullPolicy=Never \
  --set investigator.image.repository=beeper-investigator \
  --set investigator.image.tag=dev \
  --set ui.image.repository=beeper-ui \
  --set ui.image.tag=dev \
  -f ./helm/beeper/values-dev.yaml
```

---

## Uninstalling

Remove the Helm release and all associated Kubernetes resources:

```bash
helm uninstall beeper
```

This removes all Deployments, Services, ServiceAccounts, ClusterRoles, and ClusterRoleBindings created by the chart.

**CRDs and PVCs are not removed by `helm uninstall`** to prevent accidental data loss. To remove them manually:

```bash
# Delete CRDs (this also deletes all Source and Investigation objects)
kubectl delete crd sources.beeper.dev
kubectl delete crd investigations.beeper.dev

# Delete the Qdrant PVC (destroys all stored vectors)
kubectl delete pvc -l app=qdrant
```

To remove all investigation and source objects before uninstalling:

```bash
kubectl delete investigations.beeper.dev --all
kubectl delete sources.beeper.dev --all
helm uninstall beeper
```

---

## Troubleshooting

### Operator Pod Not Starting

```bash
kubectl describe pod -l app.kubernetes.io/component=operator
kubectl logs -l app.kubernetes.io/component=operator --previous
```

Common causes:
- LLM credentials secret does not exist or has the wrong key name. Verify: `kubectl get secret llm-credentials -o yaml`
- CRDs not installed. Verify: `kubectl get crds | grep beeper.dev`
- Insufficient cluster permissions for the operator ServiceAccount.

### Investigator Jobs Failing

```bash
# List recent investigator jobs
kubectl get jobs -l app.kubernetes.io/component=investigator

# Inspect a failing job
kubectl describe job <job-name>

# Check job pod logs
kubectl logs -l app.kubernetes.io/component=investigator
```

Common causes:
- LLM API key is invalid or rate-limited.
- Data source endpoint is unreachable from within the cluster.
- Investigation exceeded `activeDeadlineSeconds` (30 minutes by default). Consider increasing the deadline for complex investigations or scoping down the investigation query.
- `backoffLimit` (2) exceeded. The investigation will be marked as failed after 3 total attempts.

### Qdrant Not Ready

```bash
kubectl describe statefulset qdrant
kubectl logs -l app=qdrant
```

Common causes:
- PVC provisioning is pending; check that a StorageClass is available: `kubectl get storageclass`
- Insufficient memory; ensure nodes have at least 1Gi available for the Qdrant pod.

### Source Not Reachable

```bash
kubectl describe source <source-name>
curl http://localhost:8080/api/v1/health/components  # after port-forwarding
```

Verify the endpoint URL is correct and reachable from within the cluster. Service DNS follows the pattern `<service-name>.<namespace>.svc.cluster.local`.

### Checking the LLM Secret

```bash
# Verify the secret exists and has the expected key
kubectl get secret llm-credentials -o jsonpath='{.data}' | python3 -c "
import sys, json, base64
d = json.load(sys.stdin)
for k, v in d.items():
    print(k, '=', base64.b64decode(v).decode()[:8] + '...')
"
```

### Port-Forwarding for Local Access

```bash
# Access the UI locally
kubectl port-forward svc/beeper-ui 8080:80
# Open http://localhost:8080

# Access operator health endpoints
kubectl port-forward svc/beeper-operator 9080:8080
curl http://localhost:9080/healthz
curl http://localhost:9080/readyz
curl http://localhost:9080/api/v1/health/components
```
