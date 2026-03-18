# Beeper Demo Application

Purpose-built chaotic microservices application for demonstrating Beeper's
detect → investigate → fix → prove lifecycle during investor presentations.

## Architecture

Four services running from a single Docker image, differentiated by `SERVICE_ROLE`:

| Service | Role | Port | Purpose |
|---------|------|------|---------|
| API Gateway | `api-gateway` | 8080 | Routes requests, exposes `/api/v1/orders` |
| Backend | `backend` | 8081 | Business logic, processes orders |
| Database | `database` | 8082 | Simulated data store with query latency |
| Worker | `worker` | 8083 | Background job processor |

## Quick Start

```bash
# Deploy to Kubernetes
make demo-deploy

# Check status
make demo-status

# View logs
make demo-logs

# Tear down
make demo-teardown
```

## Local Development

```bash
# Run a single service locally
cd demo/app
pip install -r requirements.txt
SERVICE_ROLE=backend SERVICE_PORT=8080 python server.py
```

## Endpoints

All services expose:
- `GET /health` — Health check (JSON)
- `GET /metrics` — Prometheus metrics

Role-specific:
- **api-gateway:** `GET/POST /api/v1/orders`, `GET /api/v1/health`
- **backend:** `POST /process`
- **database:** `GET/POST /query?table=orders`
- **worker:** `GET /jobs`

## Prometheus Metrics

- `demo_request_total{service, method, endpoint, status}` — request counter
- `demo_request_duration_seconds{service, endpoint}` — latency histogram
- `demo_error_total{service, error_type}` — error counter
- `demo_active_connections{service}` — connection gauge

## Fault Injection

Faults are controlled via environment variables (see Story 8-2):
- `FAULT_ENABLED=true` — Enable fault injection
- `FAULT_TYPE=memory-leak|error-rate|latency|resource-exhaustion`

## ServiceLevel CRDs

Pre-configured SLOs are deployed alongside the application:
- API Gateway: 99.5% availability, 500ms p99 latency
- Backend: 99.9% availability, 200ms p99 latency
- Database: 99.95% availability, 50ms p99 latency
- Worker: 99% availability
