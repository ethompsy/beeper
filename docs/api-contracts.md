# Beeper API Contracts

## Overview

This document defines the API contracts for the Beeper agentic AI SRE platform. Beeper exposes three distinct services:

- **Operator REST API** — management and query endpoints (port 8080)
- **Ingestion API** — telemetry ingestion endpoints (port 9090)
- **UI** — Flask web application (port 5000)

All REST APIs follow consistent conventions. Error responses use RFC 7807 Problem Details. All timestamps are ISO 8601 UTC. All JSON field names use `snake_case`.

---

## Table of Contents

1. [Conventions](#conventions)
2. [Error Format](#error-format)
3. [Data Models](#data-models)
4. [Operator REST API (port 8080)](#operator-rest-api-port-8080)
   - [Health Probes](#health-probes)
   - [Source Management](#source-management)
   - [Health Components](#health-components)
   - [Ingestion Stats](#ingestion-stats)
   - [Investigations](#investigations)
   - [Knowledge Base](#knowledge-base)
5. [Ingestion API (port 9090)](#ingestion-api-port-9090)
   - [Prometheus Remote Write](#prometheus-remote-write)
   - [Loki Push](#loki-push)
6. [UI Routes (port 5000)](#ui-routes-port-5000)

---

## Conventions

| Convention | Value |
|---|---|
| JSON field naming | `snake_case` |
| Timestamp format | ISO 8601 UTC — `YYYY-MM-DDTHH:MM:SSZ` |
| Query parameter naming | `snake_case` |
| Pagination style | `limit` / `offset` |
| List response envelope | `{ "items": [], "total": <int> }` |
| Error format | RFC 7807 Problem Details |
| Error content type | `application/problem+json` |
| OpenAPI specification | `openapi/beeper-api.yaml` (OpenAPI 3.1) |

---

## Error Format

All API errors are returned as [RFC 7807 Problem Details](https://www.rfc-editor.org/rfc/rfc7807) with `Content-Type: application/problem+json`.

```json
{
  "type": "https://beeper.dev/errors/investigation-not-found",
  "title": "Investigation Not Found",
  "status": 404,
  "detail": "Investigation inv-abc123 does not exist",
  "instance": "/api/v1/investigations/inv-abc123"
}
```

| Field | Type | Description |
|---|---|---|
| `type` | string (URI) | Machine-readable error type identifier |
| `title` | string | Human-readable short summary of the problem |
| `status` | integer | HTTP status code |
| `detail` | string | Human-readable explanation specific to this occurrence |
| `instance` | string | URI reference identifying the specific request |

### Common HTTP Status Codes

| Status | Meaning |
|---|---|
| `200 OK` | Successful GET or operation |
| `201 Created` | Resource created successfully |
| `204 No Content` | Successful operation with no response body |
| `400 Bad Request` | Malformed request body or invalid parameters |
| `404 Not Found` | Resource does not exist |
| `429 Too Many Requests` | Rate limit exceeded |
| `503 Service Unavailable` | Downstream dependency unavailable or buffer full |

---

## Data Models

### Investigation

Represents an active or historical AI-driven incident investigation.

| Field | Type | Required | Description |
|---|---|---|---|
| `investigation_id` | string (UUID) | yes | Unique identifier |
| `status` | enum | yes | Current lifecycle state (see values below) |
| `condition` | string | yes | Human-readable description of the triggering condition |
| `service` | string | yes | Name of the affected service |
| `severity` | enum | yes | `low`, `medium`, `high`, or `critical` |
| `started_at` | string (ISO 8601 UTC) | yes | When the investigation began |
| `completed_at` | string (ISO 8601 UTC) | no | When the investigation concluded; absent if still active |
| `root_cause_hypothesis` | string | no | AI-generated root cause hypothesis; absent until reasoning completes |
| `confidence_level` | float (0–1) | no | Confidence score for the root cause hypothesis |
| `steps` | InvestigationStep[] | yes | Ordered list of steps taken during the investigation |
| `recommendations` | Resolution[] | yes | Recommended remediation actions |

**`status` enum values:**

| Value | Description |
|---|---|
| `pending` | Investigation queued, not yet started |
| `started` | Investigation has begun |
| `investigating` | Actively gathering data |
| `correlating` | Correlating signals across data sources |
| `querying_kb` | Querying the knowledge base for relevant context |
| `reasoning` | LLM reasoning over collected evidence |
| `completed` | Investigation finished successfully |
| `failed` | Investigation failed to complete |

---

### KnowledgeEntry

Represents an entry in the operational knowledge base (runbooks, past investigations, manual notes).

| Field | Type | Required | Description |
|---|---|---|---|
| `entry_id` | string | yes | Unique identifier |
| `title` | string | yes | Entry title |
| `content` | string (markdown) | yes | Full content, formatted as markdown |
| `entry_type` | enum | yes | `investigation`, `runbook`, or `manual` |
| `service` | string | yes | Associated service name |
| `tags` | string[] | yes | Searchable tags |
| `created_at` | string (ISO 8601 UTC) | yes | Creation timestamp |
| `updated_at` | string (ISO 8601 UTC) | yes | Last modification timestamp |
| `version` | integer | yes | Monotonically increasing version number |
| `author` | string | yes | `beeper` for AI-generated entries, or a human author name |
| `trust_level` | enum | yes | `draft`, `reviewed`, or `trusted` |

**`trust_level` enum values:**

| Value | Description |
|---|---|
| `draft` | Unreviewed; treat with caution |
| `reviewed` | Human-reviewed but not yet promoted |
| `trusted` | Approved for use in automated reasoning |

---

### Source

Represents a configured telemetry source (Prometheus or Loki).

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Unique source name |
| `source_type` | enum | yes | `prometheus` or `loki` |
| `endpoint` | string (URL) | yes | Remote endpoint URL |
| `connected` | boolean | yes | Whether the last connectivity check succeeded |
| `last_check` | string (ISO 8601 UTC) | yes | Timestamp of the most recent connectivity check |
| `error` | string | no | Last error message; absent when `connected` is `true` |
| `credentials_secret` | string | no | Kubernetes secret name containing source credentials |

---

### InvestigationCreate

Request body for manually creating an investigation.

| Field | Type | Required | Description |
|---|---|---|---|
| `condition` | string | yes | Description of the condition to investigate |
| `service` | string | yes | Name of the affected service |
| `severity` | enum | yes | `low`, `medium`, `high`, or `critical` |

---

### KnowledgeEntryCreate

Request body for creating a knowledge base entry.

| Field | Type | Required | Description |
|---|---|---|---|
| `title` | string | yes | Entry title |
| `content` | string (markdown) | yes | Entry content |
| `entry_type` | enum | yes | `investigation`, `runbook`, or `manual` |
| `service` | string | yes | Associated service name |
| `tags` | string[] | no | Searchable tags |
| `trust_level` | enum | no | Defaults to `draft` |

---

## Operator REST API (port 8080)

Base URL: `http://<operator-host>:8080`

All management and query endpoints are served on this port.

---

### Health Probes

#### GET /healthz

Liveness probe. Always returns `200 OK` if the process is running. Intended for Kubernetes liveness checks.

**Request**

```
GET /healthz
```

No request parameters or body.

**Response — 200 OK**

```
Content-Type: text/plain

ok
```

---

#### GET /readyz

Readiness probe. Returns `200 OK` if the operator is ready to serve traffic, including successful connectivity to the Kubernetes API. Returns `503 Service Unavailable` if the operator is not yet ready.

**Request**

```
GET /readyz
```

No request parameters or body.

**Response — 200 OK**

```
Content-Type: text/plain

ok
```

**Response — 503 Service Unavailable**

```
Content-Type: application/problem+json

{
  "type": "https://beeper.dev/errors/not-ready",
  "title": "Service Not Ready",
  "status": 503,
  "detail": "Kubernetes API connectivity check failed",
  "instance": "/readyz"
}
```

---

### Source Management

#### GET /api/v1/sources

List all configured telemetry sources with their current connectivity status.

**Request**

```
GET /api/v1/sources
```

No query parameters or request body.

**Response — 200 OK**

```
Content-Type: application/json

{
  "items": [
    {
      "name": "prometheus-prod",
      "source_type": "prometheus",
      "endpoint": "http://prometheus.monitoring.svc:9090",
      "connected": true,
      "last_check": "2026-03-08T14:22:01Z",
      "credentials_secret": "prometheus-credentials"
    },
    {
      "name": "loki-prod",
      "source_type": "loki",
      "endpoint": "http://loki.monitoring.svc:3100",
      "connected": false,
      "last_check": "2026-03-08T14:22:01Z",
      "error": "connection refused"
    }
  ],
  "total": 2
}
```

---

#### GET /api/v1/sources/{name}

Retrieve details for a specific named source.

**Request**

```
GET /api/v1/sources/{name}
```

| Path Parameter | Type | Description |
|---|---|---|
| `name` | string | The unique name of the source |

**Response — 200 OK**

```
Content-Type: application/json

{
  "name": "prometheus-prod",
  "source_type": "prometheus",
  "endpoint": "http://prometheus.monitoring.svc:9090",
  "connected": true,
  "last_check": "2026-03-08T14:22:01Z",
  "credentials_secret": "prometheus-credentials"
}
```

**Response — 404 Not Found**

```
Content-Type: application/problem+json

{
  "type": "https://beeper.dev/errors/source-not-found",
  "title": "Source Not Found",
  "status": 404,
  "detail": "Source 'prometheus-staging' does not exist",
  "instance": "/api/v1/sources/prometheus-staging"
}
```

---

### Health Components

#### GET /api/v1/health/components

Returns the health status of all operator sub-components, including the LLM integration.

**Request**

```
GET /api/v1/health/components
```

No query parameters or request body.

**Response — 200 OK**

```
Content-Type: application/json

{
  "components": {
    "kubernetes_api": "healthy",
    "llm": "healthy",
    "ingestion_buffer": "healthy"
  }
}
```

**LLM component status values:**

| Value | Meaning |
|---|---|
| `healthy` | LLM provider is reachable and responding |
| `unconfigured` | No LLM provider has been configured |
| `unhealthy` | LLM provider is configured but unreachable or returning errors |

---

### Ingestion Stats

#### GET /api/v1/ingestion/stats

Returns current statistics for the operator's internal ingestion buffer. Useful for monitoring backpressure and data flow health.

**Request**

```
GET /api/v1/ingestion/stats
```

No query parameters or request body.

**Response — 200 OK**

```
Content-Type: application/json

{
  "buffer_size": 1024,
  "buffer_used": 312,
  "buffer_utilization_pct": 30.5,
  "metrics_received": 48291,
  "logs_received": 12043,
  "dropped_metrics": 0,
  "dropped_logs": 0
}
```

---

### Investigations

#### GET /api/v1/investigations

List investigations with optional filtering and pagination.

**Request**

```
GET /api/v1/investigations
```

| Query Parameter | Type | Default | Description |
|---|---|---|---|
| `status` | enum | (all) | Filter by status: `active`, `resolved`, or `stale` |
| `limit` | integer | `20` | Number of results to return. Maximum: `100` |
| `offset` | integer | `0` | Number of results to skip for pagination |

**Response — 200 OK**

```
Content-Type: application/json

{
  "items": [
    {
      "investigation_id": "inv-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "status": "completed",
      "condition": "High error rate on payment-service",
      "service": "payment-service",
      "severity": "high",
      "started_at": "2026-03-08T13:00:00Z",
      "completed_at": "2026-03-08T13:07:30Z",
      "root_cause_hypothesis": "Database connection pool exhausted due to slow queries from a recent schema migration.",
      "confidence_level": 0.87,
      "steps": [],
      "recommendations": []
    }
  ],
  "total": 1
}
```

---

#### POST /api/v1/investigations

Manually trigger a new investigation.

**Request**

```
POST /api/v1/investigations
Content-Type: application/json

{
  "condition": "Elevated latency on checkout-service",
  "service": "checkout-service",
  "severity": "medium"
}
```

**Response — 201 Created**

```
Content-Type: application/json
Location: /api/v1/investigations/inv-a1b2c3d4-e5f6-7890-abcd-ef1234567890

{
  "investigation_id": "inv-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "pending",
  "condition": "Elevated latency on checkout-service",
  "service": "checkout-service",
  "severity": "medium",
  "started_at": "2026-03-08T14:30:00Z",
  "steps": [],
  "recommendations": []
}
```

**Response — 400 Bad Request**

```
Content-Type: application/problem+json

{
  "type": "https://beeper.dev/errors/invalid-request",
  "title": "Invalid Request",
  "status": 400,
  "detail": "Field 'service' is required",
  "instance": "/api/v1/investigations"
}
```

---

#### GET /api/v1/investigations/{id}

Retrieve full details of a single investigation, including all steps, findings, the root cause hypothesis, and recommendations.

**Request**

```
GET /api/v1/investigations/{id}
```

| Path Parameter | Type | Description |
|---|---|---|
| `id` | string (UUID) | The unique investigation identifier |

**Response — 200 OK**

```
Content-Type: application/json

{
  "investigation_id": "inv-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "completed",
  "condition": "High error rate on payment-service",
  "service": "payment-service",
  "severity": "high",
  "started_at": "2026-03-08T13:00:00Z",
  "completed_at": "2026-03-08T13:07:30Z",
  "root_cause_hypothesis": "Database connection pool exhausted due to slow queries from a recent schema migration.",
  "confidence_level": 0.87,
  "steps": [
    {
      "step_id": "step-001",
      "description": "Queried Prometheus for HTTP error rate",
      "started_at": "2026-03-08T13:00:05Z",
      "completed_at": "2026-03-08T13:00:07Z",
      "findings": "HTTP 5xx error rate at 34% over the past 10 minutes"
    },
    {
      "step_id": "step-002",
      "description": "Searched knowledge base for payment-service incidents",
      "started_at": "2026-03-08T13:00:08Z",
      "completed_at": "2026-03-08T13:00:10Z",
      "findings": "Found 2 prior incidents involving DB connection pool exhaustion"
    }
  ],
  "recommendations": [
    {
      "action": "Increase database connection pool size for payment-service",
      "priority": "high",
      "runbook": "https://wiki.internal/runbooks/db-pool-exhaustion"
    },
    {
      "action": "Review and optimize slow queries introduced in migration v42",
      "priority": "medium"
    }
  ]
}
```

**Response — 404 Not Found**

```
Content-Type: application/problem+json

{
  "type": "https://beeper.dev/errors/investigation-not-found",
  "title": "Investigation Not Found",
  "status": 404,
  "detail": "Investigation inv-abc123 does not exist",
  "instance": "/api/v1/investigations/inv-abc123"
}
```

---

### Knowledge Base

#### GET /api/v1/knowledge

Search the knowledge base using a full-text query. Returns matching entries ordered by relevance.

**Request**

```
GET /api/v1/knowledge?q=<query>
```

| Query Parameter | Type | Default | Required | Description |
|---|---|---|---|---|
| `q` | string | — | yes | Full-text search query |
| `limit` | integer | `10` | no | Number of results to return. Maximum: `50` |

**Response — 200 OK**

```
Content-Type: application/json

{
  "items": [
    {
      "entry_id": "kb-001",
      "title": "DB Connection Pool Exhaustion — payment-service",
      "content": "## Summary\n\nThis runbook describes how to diagnose and resolve connection pool exhaustion...",
      "entry_type": "runbook",
      "service": "payment-service",
      "tags": ["database", "connection-pool", "performance"],
      "created_at": "2026-01-15T09:00:00Z",
      "updated_at": "2026-03-01T11:30:00Z",
      "version": 3,
      "author": "beeper",
      "trust_level": "trusted"
    }
  ],
  "total": 1
}
```

**Response — 400 Bad Request** (missing required `q` parameter)

```
Content-Type: application/problem+json

{
  "type": "https://beeper.dev/errors/invalid-request",
  "title": "Invalid Request",
  "status": 400,
  "detail": "Query parameter 'q' is required",
  "instance": "/api/v1/knowledge"
}
```

---

#### POST /api/v1/knowledge

Create a new knowledge base entry.

**Request**

```
POST /api/v1/knowledge
Content-Type: application/json

{
  "title": "Checkout Service Latency Runbook",
  "content": "## Overview\n\nThis runbook covers diagnosis of elevated p99 latency on checkout-service...",
  "entry_type": "runbook",
  "service": "checkout-service",
  "tags": ["latency", "performance", "checkout"],
  "trust_level": "draft"
}
```

**Response — 201 Created**

```
Content-Type: application/json
Location: /api/v1/knowledge/kb-002

{
  "entry_id": "kb-002",
  "title": "Checkout Service Latency Runbook",
  "content": "## Overview\n\nThis runbook covers diagnosis of elevated p99 latency on checkout-service...",
  "entry_type": "runbook",
  "service": "checkout-service",
  "tags": ["latency", "performance", "checkout"],
  "created_at": "2026-03-08T14:35:00Z",
  "updated_at": "2026-03-08T14:35:00Z",
  "version": 1,
  "author": "human",
  "trust_level": "draft"
}
```

**Response — 400 Bad Request**

```
Content-Type: application/problem+json

{
  "type": "https://beeper.dev/errors/invalid-request",
  "title": "Invalid Request",
  "status": 400,
  "detail": "Field 'entry_type' must be one of: investigation, runbook, manual",
  "instance": "/api/v1/knowledge"
}
```

---

## Ingestion API (port 9090)

Base URL: `http://<operator-host>:9090`

Telemetry ingestion endpoints are served on a separate port from the management API. These endpoints are designed to be compatible with standard Prometheus and Loki client protocols.

---

### Prometheus Remote Write

#### POST /api/v1/write

Receive a Prometheus Remote Write payload. The body must be a Snappy-compressed protobuf `WriteRequest` as defined by the Prometheus Remote Write specification.

**Request**

```
POST /api/v1/write
Content-Type: application/x-protobuf
Content-Encoding: snappy
X-Prometheus-Remote-Write-Version: 0.1.0

<snappy-compressed protobuf WriteRequest body>
```

| Header | Required | Description |
|---|---|---|
| `Content-Type` | yes | Must be `application/x-protobuf` |
| `Content-Encoding` | recommended | Should be `snappy`; uncompressed is also accepted |
| `X-Prometheus-Remote-Write-Version` | recommended | Remote write protocol version |

**Response — 200 OK**

Payload accepted and queued in the ingestion buffer.

**Response — 400 Bad Request**

```
Content-Type: application/problem+json

{
  "type": "https://beeper.dev/errors/invalid-payload",
  "title": "Invalid Payload",
  "status": 400,
  "detail": "Failed to decode protobuf WriteRequest: unexpected end of data",
  "instance": "/api/v1/write"
}
```

**Response — 429 Too Many Requests**

Rate limit exceeded. The client should back off and retry.

```
Content-Type: application/problem+json

{
  "type": "https://beeper.dev/errors/rate-limited",
  "title": "Rate Limited",
  "status": 429,
  "detail": "Ingestion rate limit exceeded; retry after backoff",
  "instance": "/api/v1/write"
}
```

**Response — 503 Service Unavailable**

Ingestion buffer is full. The client should back off and retry.

```
Content-Type: application/problem+json

{
  "type": "https://beeper.dev/errors/buffer-full",
  "title": "Buffer Full",
  "status": 503,
  "detail": "Ingestion buffer capacity exceeded; retry after backoff",
  "instance": "/api/v1/write"
}
```

---

### Loki Push

#### POST /loki/api/v1/push

Receive a Loki log push payload. Compatible with the Loki HTTP push API, enabling standard Loki clients and Promtail to forward logs to Beeper.

**Request**

```
POST /loki/api/v1/push
Content-Type: application/json

{
  "streams": [
    {
      "stream": {
        "app": "payment-service",
        "env": "production",
        "level": "error"
      },
      "values": [
        ["1741441200000000000", "ERROR: database connection refused at pool limit"],
        ["1741441201000000000", "ERROR: retry attempt 1 of 3 failed"]
      ]
    }
  ]
}
```

| Header | Required | Description |
|---|---|---|
| `Content-Type` | yes | Must be `application/json` |
| `Content-Encoding` | optional | `snappy` compression is accepted |

**`streams` array items:**

| Field | Type | Description |
|---|---|---|
| `stream` | object | Key-value label set identifying the log stream |
| `values` | array | Array of `["<timestamp_ns>", "<log_line>"]` tuples. Timestamps are Unix nanoseconds as strings. |

**Response — 204 No Content**

Payload accepted and queued in the ingestion buffer. No response body.

**Response — 400 Bad Request**

```
Content-Type: application/problem+json

{
  "type": "https://beeper.dev/errors/invalid-payload",
  "title": "Invalid Payload",
  "status": 400,
  "detail": "Failed to parse log push body: 'values' must be an array of [timestamp, line] pairs",
  "instance": "/loki/api/v1/push"
}
```

**Response — 429 Too Many Requests**

```
Content-Type: application/problem+json

{
  "type": "https://beeper.dev/errors/rate-limited",
  "title": "Rate Limited",
  "status": 429,
  "detail": "Ingestion rate limit exceeded; retry after backoff",
  "instance": "/loki/api/v1/push"
}
```

**Response — 503 Service Unavailable**

```
Content-Type: application/problem+json

{
  "type": "https://beeper.dev/errors/buffer-full",
  "title": "Buffer Full",
  "status": 503,
  "detail": "Ingestion buffer capacity exceeded; retry after backoff",
  "instance": "/loki/api/v1/push"
}
```

---

## UI Routes (port 5000)

Base URL: `http://<ui-host>:5000`

The Beeper UI is a server-rendered Flask web application. All routes return `text/html` unless noted otherwise. These routes are not REST API endpoints and are intended for browser consumption.

| Route | Method | Description |
|---|---|---|
| `/` | GET | Home page — platform overview and status summary |
| `/sources/` | GET | Source status view — connectivity state for all configured telemetry sources |
| `/health/` | GET | Operator component health view |
| `/health/api` | GET | UI health check endpoint; returns `200 OK` with JSON `{"status": "ok"}` |
| `/investigations/` | GET | Investigation list view with filtering by status |
| `/investigations/{id}` | GET | Investigation detail view with real-time updates via Server-Sent Events (SSE) |
| `/knowledge/` | GET | Knowledge base wiki index |
| `/knowledge/{id}` | GET | Knowledge base entry view |
| `/knowledge/{id}/edit` | GET | Knowledge base entry edit form |
| `/knowledge/{id}/diff` | GET | Version diff view for a knowledge base entry |
| `/metrics/` | GET | MTTR trends dashboard |
| `/spending/` | GET | Cost visibility dashboard — LLM and infrastructure spend |

### Real-Time Updates

The investigation detail route (`/investigations/{id}`) uses **Server-Sent Events (SSE)** to push live status updates to the browser as an investigation progresses through its lifecycle stages. No additional API calls are required from the client; the page subscribes to the SSE stream on load.

### UI Health Check

`GET /health/api` returns a minimal JSON health response intended for load balancer and uptime checks:

```
HTTP/1.1 200 OK
Content-Type: application/json

{"status": "ok"}
```
