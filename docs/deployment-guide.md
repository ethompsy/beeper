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

### Authentication & Identity

Task 8.9 / [ADR 0002](specs/decisions/0002-oidc-scim-and-local-fallback-identity.md). One `ui.auth` values tree drives the UI's identity posture. **Default (`mode: none`) is completely unaffected — this whole section is opt-in**, and `make demo-up`/`make demo-deploy` never touch it (see [Beeper UI authentication & identity](#beeper-ui-authentication--identity-adr-0002) below for the operational detail this table doesn't cover).

```yaml
ui:
  auth:
    mode: none                    # none | local | oidc
    existingSecret: ""            # name of a pre-existing Secret — see below; never put secret VALUES here
    externalScheme: https         # https | http — drives the session cookie's Secure flag
    sessionLifetimeHours: 8
    adminGroups: "Admins,beeper-admin"
    userGroups: ""
    oidc:
      issuer: ""
      clientId: ""
      redirectUrl: ""             # empty = derived from the request Host (covers kubectl port-forward)
      scopes: "openid profile email groups"
      groupsClaim: "groups"
      postLogoutRedirectUrl: ""
    scim:
      enabled: false               # valid ONLY when mode: oidc
      strict: false
      networkPolicy:
        enabled: false
        allowFrom: []
    bootstrap:
      enabled: true
```

| Key | Default | Description |
|---|---|---|
| `ui.auth.mode` | `none` | `none` (today's zero-config demo/dev posture — anonymous, no admin path in production), `local` (admin-managed username/password accounts), or `oidc` (SSO via an external IdP, optionally with SCIM provisioning) |
| `ui.auth.existingSecret` | `""` | Name of ONE pre-existing Kubernetes Secret (not templated by this chart) carrying whichever of `secretKey`/`clientSecret`/`scimToken`/`scimTokenSecondary`/`bootstrapUsername`/`bootstrapPassword` the enabled features need. See [Credentials Management](#credentials-management) and [`helm/beeper/examples/identity-secret.yaml`](../helm/beeper/examples/identity-secret.yaml). |
| `ui.auth.externalScheme` | `https` | Drives `BEEPER_EXTERNAL_SCHEME`, which explicitly sets the session cookie's `Secure` flag — never inferred from the request, so a TLS-terminating ingress speaking plain HTTP to the pod can't silently strip it. Set `http` only for the plain-HTTP kind-demo / `kubectl port-forward` path. |
| `ui.auth.sessionLifetimeHours` | `8` | Absolute session lifetime (no sliding refresh). In `oidc` mode without SCIM, this is also the deprovisioning-propagation bound — see the mode comparison below. |
| `ui.auth.adminGroups` / `ui.auth.userGroups` | `"Admins,beeper-admin"` / `""` | Comma-separated, case-insensitive IdP group names mapped to the `admin`/`user` roles — shared by OIDC login and SCIM. Empty `userGroups` = any authenticated principal not in `adminGroups` is `user`. |
| `ui.auth.oidc.*` | — | Standard OIDC RP settings; see [IdP setup notes](#idp-setup-notes-okta--entra-id--keycloak) below for provider-specific values. |
| `ui.auth.scim.enabled` | `false` | Registers the `/scim/v2` provisioning surface. Valid **only** when `mode: oidc` — the chart doesn't enforce this (the application does, refusing to boot), but setting it under `local`/`none` is always a mistake. |
| `ui.auth.scim.networkPolicy.*` | disabled | Optional defense-in-depth NetworkPolicy — see [Optional SCIM NetworkPolicy](#optional-scim-networkpolicy-defense-in-depth-not-path-isolation) below for what it actually does and doesn't restrict. |
| `ui.auth.bootstrap.enabled` | `true` | In `local` mode, whether to wire `bootstrapUsername`/`bootstrapPassword` from `existingSecret`. Set `false` if you'd rather seed the first admin purely via `flask create-admin` (see [Bootstrap & lockout recovery](#bootstrap--lockout-recovery)). |

**Three modes at a glance:**

| Mode | Who authenticates | Where role comes from | When to use |
|---|---|---|---|
| `none` (default) | nobody — anonymous | `X-Beeper-Role` dev header if `ALLOW_ROLE_HEADER` (dev/test only); production has no admin path | demo/dev, or any deployment that doesn't need role-gated admin actions |
| `local` | admin-managed username/password accounts | assigned directly by an admin via `/app/admin/users` | production/staging without an IdP |
| `oidc` | your IdP, via an authorization-code flow | SCIM-provisioned group membership (recommended — propagates within 60 s) or, if SCIM is disabled, the login-time group-claims snapshot (bounded by `sessionLifetimeHours`) | production with an existing IdP (Okta, Entra ID, Keycloak, etc.) |

Ready-to-use per-mode values overlays live in [`helm/beeper/examples/`](../helm/beeper/examples/) (`values-identity-local.yaml`, `values-identity-oidc.yaml`, `values-identity-oidc-scim.yaml`), e.g.:

```bash
helm upgrade --install beeper ./helm/beeper \
  -f ./helm/beeper/values.yaml \
  -f ./helm/beeper/examples/values-identity-oidc-scim.yaml
```

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

### Beeper UI authentication & identity (ADR 0002)

The Beeper UI has a two-tier `user`/`admin` permission model
(`beeper_ui/middleware/permissions.py`) gating admin-tier mutations (trust-level
writes, gate-threshold writes, adjustment apply/reject). Since Task 6.2a,
production refuses the `X-Beeper-Role` header that development/testing use to
set a role, because it is a trivially spoofable identity source — any HTTP
client can set an arbitrary header (background:
[ADR 0001](specs/decisions/0001-rbac-and-realtime-collaboration-in-react-ui.md)).

**Historical note, superseded below:** between Task 6.2a and Task 8.9,
production had *no* path to the `admin` role at all — every
`@require_role("admin")` route returned `403` for every caller, and
admin-tier changes had to go through `kubectl`/Helm directly. **This is no
longer true.** [ADR 0002](specs/decisions/0002-oidc-scim-and-local-fallback-identity.md)
adds two verified identity sources; ADR 0001 §8 has been updated with a
closing note pointing here.

#### Two admin paths, and the one case that still has none

| `ui.auth.mode` | Admin path in production | Notes |
|---|---|---|
| `none` (default) | **None — unchanged from 6.2a.** | The header stays refused; this is deliberate, not a gap — see [Authentication & Identity](#authentication--identity) above. Choose `local` or `oidc` if you need role-gated admin actions in production. |
| `local` | Admin-managed username/password accounts, assigned via `/app/admin/users`. | The directive's SSO-off fallback. No self-registration, no MFA, no password self-service — see the bootstrap/recovery notes below. |
| `oidc` | IdP group membership (`ui.auth.adminGroups`, default `Admins,beeper-admin`), via SCIM-provisioned role (recommended) or the login-time claims snapshot. | See [IdP setup notes](#idp-setup-notes-okta--entra-id--keycloak) below. |

Both `local` and `oidc` require a `SECRET_KEY` supplied via `ui.auth.existingSecret`'s `secretKey` — the application refuses to boot without it (sessions must survive pod restarts and stay consistent across replicas). `oidc` mode additionally requires `oidc.issuer`/`oidc.clientId`/a `clientSecret` key.

#### The SCIM token is an admin-equivalent secret

Because group membership *is* the admin grant, **`ui.auth.existingSecret`'s `scimToken`/`scimTokenSecondary` keys must be handled with exactly the same rigor as `secretKey`**: never logged (Beeper only ever logs an 8-character `sha256` fingerprint — logger `beeper_ui.scim.audit` — never the token itself), never committed to a values file, and rotated on the same cadence you'd rotate any other admin credential.

**Dual-token zero-downtime rotation runbook** — both `scimToken` and `scimTokenSecondary` are accepted simultaneously by every `/scim/v2/*` request for as long as both are set, which is what makes this sequence zero-downtime:

1. Generate a new token: `python3 -c "import secrets; print(secrets.token_hex(32))"`.
2. Set the **secondary** slot to the new value, leaving the primary (current, IdP-configured) value untouched:
   ```bash
   kubectl patch secret beeper-identity --type=merge \
     -p "{\"stringData\":{\"scimTokenSecondary\":\"$NEW_TOKEN\"}}"
   ```
3. Roll the UI pods so they pick up the new secondary value: `kubectl rollout restart deployment/<release>-ui`.
4. Repoint your IdP's SCIM connector at the new token value. During this window, both the outgoing (primary) and incoming (new, now-secondary) tokens authenticate successfully — no provisioning downtime regardless of which value the IdP is mid-transition on.
5. Confirm the IdP's next SCIM push succeeds (check `beeper_ui.scim.audit` logs for the new token's fingerprint).
6. **Promote:** move the new value into the primary slot and clear the secondary:
   ```bash
   kubectl patch secret beeper-identity --type=merge \
     -p "{\"stringData\":{\"scimToken\":\"$NEW_TOKEN\",\"scimTokenSecondary\":\"\"}}"
   ```
7. Roll the UI pods again. The old token no longer authenticates (verify with a `401` from a request using it, if you want positive confirmation).

An enabled-but-unconfigured SCIM surface (neither key set) fails closed with `403` on every request, naming the misconfiguration — never a silent `401`-retry-forever or an open surface.

#### Optional SCIM NetworkPolicy (defense-in-depth, not path isolation)

`ui.auth.scim.networkPolicy.enabled` (default `false`) templates a `NetworkPolicy` scoped to the UI pod. **Read this before enabling it:** Kubernetes `NetworkPolicy` operates at L3/L4 (IP address and port) only — it has no concept of an HTTP path. Beeper serves `/scim/v2/*` on the exact same port as every browser and API route, so this policy **cannot** restrict ingress to just SCIM traffic; it restricts **all** ingress to the UI's port to `ui.auth.scim.networkPolicy.allowFrom`. Only enable it if `allowFrom` also covers every other legitimate source that needs to reach the UI (your ingress controller's namespace, etc.) — otherwise you will lock out real users, not just protect the SCIM token. This is genuinely useful as defense-in-depth for the SCIM token's blast radius (ADR 0002 §4, security HIGH-5) when your topology allows a tight peer allow-list; it is not, and cannot be, per-path SCIM isolation. See `helm/beeper/examples/values-identity-oidc-scim.yaml` for a worked `allowFrom` example. The chart refuses to render (`helm template`/`helm install` hard error) if you set `enabled: true` with an empty `allowFrom` — an empty NetworkPolicy ingress `from` list means "allow all sources" in Kubernetes, the opposite of what enabling this feature implies.

#### Bootstrap & lockout recovery

**Seeding the first `local`-mode admin** happens automatically, idempotently, on boot from `ui.auth.existingSecret`'s `bootstrapUsername`/`bootstrapPassword` keys (`ui.auth.bootstrap.enabled: true`, the default): if the username doesn't exist yet it's created as an active admin; if it already exists it is **never touched** (a password you've since rotated through the admin UI is never reverted by a pod restart). No bootstrap configuration + no active admin ⇒ a prominent startup ERROR log line plus a `zero_active_admins: true` flag on `/health/api` — not a crash.

**Recovering from zero active admins** (bootstrap never configured, or the last admin was demoted/deactivated by mistake — the admin UI itself refuses a last-admin demotion/deactivation with `409`, but a SCIM push that would orphan admins alarms rather than blocking, per ADR §5.3):

```bash
# Promote/reactivate an existing user, or create a new admin if it doesn't exist yet.
echo "$NEW_PASSWORD" | kubectl exec -i deploy/<release>-ui -- \
  flask --app beeper_ui create-admin <username> --password-stdin
```

`flask create-admin` works from a `kubectl exec` shell regardless of the currently-configured `BEEPER_AUTH_MODE` — it's registered unconditionally, precisely so it's available while troubleshooting a broken auth config. If the username already exists, it is promoted-and-reactivated (role set to `admin`, `active` set to `true`) rather than erroring — the common case is "someone got demoted/deactivated by mistake," not "nobody was ever seeded."

**There is no break-glass local-password login in `oidc` mode** (ADR §12 D4, deliberate) — the CLI above, via `kubectl exec`, is the only recovery path when your IdP itself is unreachable or misconfigured. Watch for the `zero_active_admins` health flag; it's the signal this situation has occurred.

#### IdP setup notes (Okta / Entra ID / Keycloak)

All three: register a confidential OIDC client with redirect URI `<externalScheme>://<host>/auth/callback`, request scopes `openid profile email groups` (or your `ui.auth.oidc.scopes` override), and ensure a `groups` claim (or your `ui.auth.oidc.groupsClaim` override) is present in either the ID token or the UserInfo response — Beeper falls back to a one-shot UserInfo fetch if the ID token omits it.

- **Okta:** Applications → Create App Integration → OIDC, Web Application, Authorization Code grant. Add a `groups` claim under Security → API → Authorization Servers → (your server) → Claims, filtering to the group names you'll use in `ui.auth.adminGroups`/`userGroups`. For SCIM: Applications → (your app) → Provisioning → configure API integration with Base URL `https://<host>/scim/v2` and the `scimToken` value as the bearer credential; enable "Push Groups" for the groups you want provisioned.
- **Entra ID (Azure AD):** App registration → Authentication → add a Web platform redirect URI. Token configuration → add a `groups` claim (Entra's default groups claim silently drops above ~200 group memberships per user — a known overflow Beeper's UserInfo fallback works around, but only if UserInfo is reachable; keep admin/user groups small and dedicated rather than relying on a user's full group closure). For SCIM: Enterprise Applications → (your app) → Provisioning → set Tenant URL `https://<host>/scim/v2` and Secret Token to the `scimToken` value. **Map the SCIM `externalId` attribute to `objectId`, not `sub`.** Entra's OIDC `sub` claim is pairwise (unique per application registration), while Beeper's identity join key uses `oid`/`objectId` (stable, tenant-wide) specifically so SCIM-provisioned records adopt-link correctly against users who log in before or after being provisioned — mapping `externalId` to `sub` instead breaks that join silently (a user's SCIM record and their OIDC login never match). **RP-initiated logout caveat:** Beeper never retains the `id_token` (tokens are validated at the callback and discarded), so `POST /auth/logout`'s best-effort `end_session_endpoint` redirect (only built when `ui.auth.oidc.postLogoutRedirectUrl` is set) omits `id_token_hint`. Entra tolerates this but may prompt the user to pick an account or confirm sign-out rather than silently completing SSO logout — Beeper's own session is always cleared regardless; only the IdP-side SSO session's behavior is affected.
- **Keycloak:** create a realm, then a client with "Standard flow" enabled and your redirect URI. Add the built-in `groups` client scope (or a custom group-membership protocol mapper) so group names appear in the token. **Keycloak does not ship a SCIM 2.0 provisioning connector out of the box** (as of Keycloak 26.x) — use Keycloak for OIDC-login validation (with or without a manually-assigned role via the login-time claims snapshot, i.e. `scim.enabled: false`), and validate the SCIM surface itself directly against Beeper with the curl scripts in [`docs/runbooks/identity-live-validation.md`](runbooks/identity-live-validation.md) rather than through a live Keycloak SCIM push. See that runbook for a disposable dev-Keycloak `kubectl` manifest.

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

Identity/auth secrets (`SECRET_KEY`, OIDC client secret, SCIM token(s), bootstrap admin credentials) follow the same never-written-to-disk, never-logged discipline, via the single `ui.auth.existingSecret` — see [Authentication & Identity](#authentication--identity) for the values reference, [`helm/beeper/examples/identity-secret.yaml`](../helm/beeper/examples/identity-secret.yaml) for a template, and the SCIM dual-token rotation runbook under [Beeper UI authentication & identity](#beeper-ui-authentication--identity-adr-0002) — **do not** rotate `scimToken` with a single-step delete-and-replace the way the LLM key rotation above works; that causes IdP-visible provisioning downtime.

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

## Demo Environment

Beeper includes a demo environment that deploys the [OpenTelemetry Astronomy Shop](https://github.com/open-telemetry/opentelemetry-demo) — a polyglot e-commerce application with 16+ microservices — as a real-world target for Beeper to monitor and investigate.

### Deploying the Demo

```bash
# One-time: add the OTel Helm chart repo
make demo-helm-repo

# Deploy the OTel Astronomy Shop + ServiceLevel CRDs + Source CRD
make demo-deploy

# Port-forward UIs for local access
make demo-ui
```

This deploys the OTel demo into the `otel-demo` namespace and configures its OTel Collector to forward metrics and logs to Beeper's operator ingestion endpoint (port 9090).

### Signal Flow

```
OTel Astronomy Shop services
  → OTel Collector (in otel-demo namespace)
    → prometheusremotewrite exporter → Beeper operator :9090/api/v1/write
    → loki exporter                  → Beeper operator :9090/loki/api/v1/push
```

### Injecting Faults

The OTel demo uses [flagd](https://flagd.dev/) feature flags for fault injection. The Makefile wraps this into simple commands:

```bash
make demo-fault FAULT=payment-failure   # Payment service errors
make demo-fault FAULT=cart-failure      # Cart service failures
make demo-fault FAULT=kafka-problems    # Kafka queue overload
make demo-fault FAULT=slow-images       # Image loading delays
make demo-fault FAULT=high-cpu          # Ad service CPU spike

make demo-fault-status                  # Show active faults
make demo-recover                       # Reset all flags
```

The demo includes a Locust-based load generator that runs continuously, so injected faults produce real error metrics and traces immediately.

### ServiceLevel CRDs

Pre-configured SLOs are applied for key services:

| Service | SLO Target | Metric |
|---------|-----------|--------|
| checkoutservice | 99.9% availability | `http_server_request_duration_seconds_count` |
| cartservice | 99.9% availability | `http_server_request_duration_seconds_count` |
| paymentservice | 99.95% availability | `http_server_request_duration_seconds_count` |
| frontend | 99.5% availability | `http_server_request_duration_seconds_count` |
| productcatalogservice | 99.9% availability | `http_server_request_duration_seconds_count` |

### Tearing Down

```bash
make demo-teardown
```

This uninstalls the Helm release, deletes the `otel-demo` namespace, and removes the Source CRD.

### Resource Requirements

The OTel demo requires approximately 4GB RAM and 4 CPU cores. It works on Docker Desktop Kubernetes, minikube, kind, or any cloud K8s cluster.

See [demo/README.md](../demo/README.md) for full details.

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
